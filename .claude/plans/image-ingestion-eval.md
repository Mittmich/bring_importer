---
name: image-ingestion-eval
status: active
---

# Image Ingestion — Prompt & Model Optimisation via an Eval Harness

Optimise the recipe-from-image extraction ([parse_recipe_with_openai](../../backend/api/recipe_extraction.py))
— both the **prompt** and the **model** — by building a labelled dataset and a repeatable
evaluation harness that scores extractions with structured + LLM-judge metrics, then comparing a
matrix of `model × prompt` variants.

## Decisions (locked)

- **Models**: OpenAI tiers only — `gpt-5.4-nano`, `gpt-5.4-mini` (current), `gpt-5.4` (full). Make
  the model a parameter; compare quality vs cost vs latency.
- **Dataset**: **hybrid** — bulk of perfectly-labelled pairs by *rendering existing structured
  recipes to images* (free ground truth), plus a small hand-verified set of **real photos** for
  realism.
- **Languages**: German + English (the app's real usage; tests language *preservation*).
- **Eval is opt-in**, never in CI: it makes real paid API calls and needs `OPENAI_API_KEY`. Marked
  with a pytest marker that is deselected by default; outputs cached to disk.

## What we're scoring

The image call returns this schema ([recipe_extraction.py](../../backend/api/recipe_extraction.py)
`_RecipeOutput`):
`title`, `recipeYield`, `description`, `ingredients[{amount, name}]`,
`instructions[{text, ingredients: [0-based indices]}]`.

The **ingredient→step index mapping** is a distinctive, error-prone feature and gets its own metric.

---

## Phase 1 — Make model & prompt injectable (small refactor)

Currently model and prompt are hardcoded in `parse_recipe_with_openai`. Refactor so the eval (and
prod) can swap them without duplicating call logic:

- Extract prompt strings into named constants / a small registry (e.g. `IMAGE_PROMPTS: dict[str,
  PromptSpec]` where `PromptSpec = {system, user}`), starting with the current prompt as `"v1"`.
- `parse_recipe_with_openai(image_base64, *, model="gpt-5.4-mini", prompt="v1")` — defaults preserve
  today's behaviour. The [parse endpoint](../../backend/api/routers/recipes.py) keeps calling it with
  defaults; the model could later be read from config/env.
- This is a genuine code improvement (de-hardcodes config) and the seam the harness needs.

## Phase 2 — Dataset generation (hybrid)

Target ~**80–120 labelled pairs**: an image + ground-truth `Recipe` JSON in the *same output schema*,
so metrics compare like-for-like.

### 2a. Rendered set (bulk, free labels)
Pipeline `backend/evals/dataset/render.py`:
1. **Source structured recipes** as ground truth from:
   - existing recipes in `recipes.db` / public recipes (already structured by the JSON-LD path), and
   - a handful of curated German + English recipes (varying length/complexity).
   The ground truth is the structured `Recipe` we already trust — no labelling needed.
2. **Render to images** via a headless browser (Playwright) using **several HTML/CSS templates**
   that mimic real recipe surfaces: cookbook page, blog screenshot, index card, plain printout,
   two-column layout. Vary fonts (incl. a handwriting-style font), font size, and colour.
3. **Augment** for robustness: slight rotation, blur, JPEG compression, lighting/contrast shifts,
   crop — to approximate phone photos. Keep an un-augmented copy too.
   - Difficulty tiers (`clean`, `noisy`, `hard`) tagged in the manifest so we can read scores per
     tier.

This gives controlled coverage of layout/quality variation with exact labels, cheaply and at scale.
Caveat (documented): rendered images under-represent true handwriting and real lighting — hence:

### 2b. Real golden set — collected in-app (preferred)
Rather than hand-photographing + hand-labelling, **collect labelled pairs as a byproduct of normal
use**. The edit screen already lets the user correct an extraction, so the corrected recipe *is*
human-verified ground truth for the image that produced it — in true real-world distribution.

- **Config flag** `COLLECT_TRAINING_DATA` (env, default **off**). Additive: the
  [parse endpoint](../../backend/api/routers/recipes.py) currently discards the uploaded image
  (`source.value == ""` for image imports).
- **At parse time** (flag on): persist the uploaded image to a mounted volume **plus a sidecar
  snapshot of the raw extraction** (`{model, prompt_version, raw_recipe_json, ts}`), keyed by recipe
  `uuid`. Write *after* returning the response so import latency is unaffected; downscale/cap image
  size.
- **Label = the recipe's current stored JSON** after the user's edits (via the existing
  [EditRecipePage](../../frontend-react/src/pages/EditRecipePage.tsx)), pulled by `uuid` at export
  time — no separate labelling step.
- **Verified signal**: only cases the user has confirmed enter the eval set. Add a lightweight
  "looks correct / verified" toggle in the edit flow (or, minimally, treat *edited* recipes as the
  high-confidence subset). Avoids polluting ground truth with un-reviewed extractions.
- **Export script** `backend/evals/collect_export.py` joins `image + raw-extraction + current
  recipe_json` → manifest rows (`tier="real"`, `source="collected"`, lang auto-detected). This is the
  realism anchor; report its scores separately.

**Bonus — production quality signal**: the snapshotted raw extraction vs the final corrected recipe
gives a real-world **correction rate / edit distance** per import, trackable over time independent of
the formal eval (an early read on quality before the full harness exists).

Infra notes: collected data (and `recipes.db`) must live on a **persisted docker volume** so it
survives deploys; keep collection opt-in with a short retention/consent note (low stakes on a
self-hosted single-tenant instance).

### Layout on disk
```
backend/evals/
  dataset/
    manifest.jsonl        # one row per case: {id, image_path, lang, tier, source, label_path}
    images/<id>.jpg
    labels/<id>.json      # ground-truth Recipe (output schema)
    render.py             # rendered-set generator
    templates/*.html.j2
  collected/              # in-app collected pairs (volume-mounted, gitignored)
    images/<uuid>.jpg
    raw/<uuid>.json       # raw extraction snapshot {model, prompt_version, raw_recipe_json, ts}
  collect_export.py       # joins collected + current recipe_json -> manifest rows
```

## Phase 3 — Metrics (deterministic-first, deepeval-wrapped)

Deterministic comparators are more reliable than an LLM judge for the precise fields; wrap them as
**deepeval custom metrics** (`BaseMetric` subclasses) so everything reports through one harness, and
use **GEval** (LLM-as-judge) only for genuinely fuzzy comparisons.

Custom deterministic metrics (`backend/evals/metrics/`):
- **Ingredient faithfulness (precision)** — fraction of *extracted* ingredients that match a
  ground-truth ingredient (penalises hallucinated/invented items). Matching by normalised name
  (lowercase, singularise, strip descriptors) with a fuzzy/embedding fallback threshold.
- **Ingredient completeness (recall)** + **F1** — coverage of GT ingredients.
- **Amount accuracy** — for matched ingredients, is the quantity right after unit normalisation
  (`"200 g"`==`"200g"`==`"200 grams"`; handle ranges, fractions, "to taste" → empty). 
- **Index-mapping accuracy** — for aligned steps, do the referenced ingredient indices match GT
  (set IoU per step, averaged).
- **Instruction count / order** — step-count delta and ordering correctness.
- **Title / yield exactness** — normalised title match; servings number extraction.
- **Schema validity & parse-success rate** — did the call return valid structured output at all.

LLM-judge metrics via **GEval** (one strong judge model; cached):
- **Instruction semantic coverage** — does each GT step's meaning appear, regardless of wording
  (handles paraphrase/merged steps better than string compare).
- **Description quality** — soft, low weight.

> Note: deepeval's built-in `FaithfulnessMetric` is RAG-shaped (claims vs retrieval context). We model
> the **ground-truth recipe as the context** for any reused built-ins, but the ingredient/amount/index
> metrics are custom and deterministic — that's where the real signal is.

A weighted **composite score** (config-driven weights) ranks variants; per-metric tables expose
trade-offs.

## Phase 4 — The eval harness & model/prompt matrix

`backend/evals/run_eval.py` (+ `pytest -m eval` entry):
- Parametrise over `models × prompts × dataset`.
- **Cache model outputs** to disk keyed by `(image_hash, model, prompt_version)` so metric iteration
  is free and reruns don't re-spend. Record **token usage, $ cost, latency** per call.
- Compute all metrics per case; aggregate overall, **per language**, and **per difficulty tier** and
  **rendered vs real**.
- **Report**: a leaderboard (composite + per-metric + cost + latency) written to
  `backend/evals/reports/<timestamp>.md`, plus a failures view dumping the worst cases (image ref,
  expected vs got diff) for qualitative inspection.

### Prompt variants to try (initial)
- `v1` — current terse prompt (baseline).
- `v2` — explicit rules: separate amount/name, normalise units, **don't invent** ingredients,
  preserve source **language**, handle multi-column/handwriting, "to taste" → empty amount, extract
  servings, 0-based indices, every step maps its ingredients.
- `v3` — `v2` + 1–2 **few-shot** examples (a worked image→JSON pair).
- `v4` — structure/strategy hint (read ingredient block then steps; reconcile) within structured-output
  constraints.

### Model options
- `gpt-5.4-nano`, `gpt-5.4-mini`, `gpt-5.4` across the winning prompt(s); pick the best
  quality-per-cost point. Also sanity-check the helper calls
  (`_parse_ingredient_strings`, `_map_ingredients_to_instructions`) reuse the chosen tier sensibly.

## Phase 5 — Decide & apply
- Pick the `model × prompt` that maximises the composite at acceptable cost/latency, especially on the
  **real golden set**.
- Update the defaults in `parse_recipe_with_openai` (and config if model becomes env-driven).
- Commit the eval harness + dataset manifest; document how to run it (`README`/`TESTING.md`).
- Re-run on the golden set as a regression checkpoint for future prompt/model changes.

---

## Tooling / deps
- New **dev/eval optional-dependency group** in [pyproject.toml](../../backend/pyproject.toml):
  `deepeval`, `playwright`, `pillow`, `rapidfuzz` (fuzzy match), maybe `pint` (units). Kept out of the
  runtime deps and out of CI.
- Per [feedback_uv_tooling] all of this runs via `uv run`.

## Open questions
- "Verified" capture: explicit toggle in the edit flow vs treating "was edited" as the confident
  subset (lean: a small toggle, only verified cases enter the eval set).
- Where the collected volume lives on the Lightsail deploy + retention policy.
- Composite-score weights (ingredient faithfulness likely highest).
- Judge model for GEval (a strong OpenAI tier; budget per run).
- Embedding-based ingredient matching vs pure fuzzy — start with `rapidfuzz`, add embeddings only if
  matching is the bottleneck.
- Do we also want a tiny **mocked** smoke test of the harness wiring that *can* run in CI (no real API)?
