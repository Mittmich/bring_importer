---
name: recipe-pdf-export
status: done
updated: 2026-11-05
---

# Recipe PDF export

## Goal

An "Export PDF" action on a recipe that produces a clean, printable PDF of what the
user sees: photo, title, servings (scaled to the current servings selector),
ingredients, numbered steps with the ingredients each step uses, note, tags — in the
current language. Works the same on phone (share sheet) and desktop (download).

## Decision

Server-side generation (user choice, 2026-11-05) rather than the browser print dialog.

- Library: **fpdf2** (pure Python; brings Pillow + fontTools). No system packages needed
  in the Docker image.
- Font: **DejaVu Sans** regular + bold, vendored in `backend/api/fonts/` and *subset* with
  fontTools to Latin + punctuation + fractions + symbols (~50 KB each), so it passes the
  repo's 500 KB `check-added-large-files` hook. Licence vendored alongside. Characters
  outside the subset (e.g. emoji) are replaced/dropped by a sanitiser rather than
  rendering as tofu.

## Design

- `GET /recipes/{uuid}.pdf?servings=N` — same access rule as `.json` (public, or viewer+);
  localized via `Accept-Language` / `?lang=`. Returns `application/pdf` with a
  `Content-Disposition` filename derived from the title (RFC 5987 for non-ASCII).
- `api/recipe_pdf.py`: `build_document(recipe, servings, lang)` (pure: scaled
  ingredients, steps, labels — unit-tested) → `render_pdf(doc, image_path)` (fpdf2 layout).
- Servings scaling ported from `frontend-react/src/lib/scaling.ts` so PDF amounts match
  the screen.
- PDF labels (Ingredients/Zutaten, …) in a small backend string table in `api/i18n.py`.
- Frontend: `api.downloadRecipePdf(uuid, servings)` fetches with auth + language;
  `saveOrShare()` uses the Web Share API with a file on touch devices, otherwise a
  download. Buttons in `RecipeDetail` (desktop + mobile top bar) and `PublicRecipePage`.

## Steps

- [x] 1. Add fpdf2 dependency; vendor subset DejaVu fonts + licence
- [x] 2. Backend: scaling port, backend PDF labels, `api/recipe_pdf.py` (model + renderer)
- [x] 3. Backend: `GET /recipes/{uuid}.pdf` endpoint
- [x] 4. Backend tests + visual check of generated PDFs (en/de, with/without photo, long recipe)
- [x] 5. Frontend: API helper, save/share helper, buttons, i18n keys
- [x] 6. Frontend typecheck/lint/build; docs

## Outcome

- `GET /recipes/{uuid}.pdf?servings=N` (same visibility as `.json`, shared via
  `_visible_recipe`), localized, `Cache-Control: private, no-store`, RFC 5987 filename;
  CORS now exposes `Content-Disposition` for cross-origin dev.
- `api/recipe_pdf.py`: scaling port (parity-tested against the frontend's rules), document
  model, fpdf2 renderer (full-width centre-cropped photo embedded as JPEG; ingredient rows
  and steps never split across pages; heading kept with content; footer with page x/y).
- Fonts: DejaVu Sans regular/bold subset to ~50 KB each (+ licence) — under the 500 KB hook.
- Frontend: `ExportPdfButton` (desktop row + mobile top bar on the recipe view, header of the
  public page), `api.downloadRecipePdf`, `saveOrShare` (share sheet on touch, else download).
- Tests: 26 in `tests/test_recipe_pdf.py`; 281 backend tests pass. Visual checks of en/de,
  long multi-page and photo PDFs; end-to-end over HTTP against a running backend.
