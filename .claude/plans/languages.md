---
name: languages
status: done
updated: 2026-11-04
---

# Languages (i18n)

## Goal

Language support with three effects:

1. **UI translation** — deterministic translation keys drive every UI string.
2. **Extraction translates** — image / URL imports produce the recipe in the user's target language.
3. **Localized display** — recipes are shown in the target language when a version in it exists.

If a recipe has no version in the target language, the **edit screen** offers an
"Translate with AI" action that calls the LLM provider and stores the translation.

Supported languages: `en`, `de` (registry is one list in backend + frontend; adding one is
a dictionary file + a registry entry).

## Design

### Language selection
- `users.language` column (nullable). Exposed/updated via `GET/PUT /account/profile`.
- Frontend: `I18nProvider` holds the current language. Initial value: `localStorage.ui_language`
  → browser language → `en`. After login the profile language wins; changing it in Account
  saves to the profile and localStorage.
- Every API request sends `Accept-Language: <lang>`. Backend dependency `request_language`
  resolves `?lang=` → `Accept-Language` → `None`. React Query cache is reset on language change.

### Recipe storage (backwards compatible)
`recipe_json` keeps its base content at the top level and gains:
- `inLanguage` — language of the base content (schema.org field); absent/`null` for legacy recipes.
- `translations` — `{lang: {name, description, recipeYield, ingredients, instructions}}`.
  Each variant is self-contained (own ingredient indices) so it can be edited independently.

`api/i18n.py::localize_recipe(stored, lang)` returns the variant for `lang` merged on top of the
base, plus `language` (content language), `inLanguage`, `available_languages`,
`requested_language`, `translation_available`.

Legacy recipes with unknown base language are displayed as-is and are *not* flagged as missing
(we can't know); the edit screen still offers translation, and the LLM's detected source
language is then stored as `inLanguage`.

### Endpoints
- `GET /recipes/{uuid}.json`, `GET /recipes`, `GET /cookbooks/{id}`, `GET /meal-plan`,
  `POST /meal-plan/shopping-list`, `GET /recipes/{uuid}.html` → localized by request language.
- `PUT /recipes/{uuid}` gains `language` (which variant is being edited; default base) and
  `inLanguage` (declare the base language).
- `POST /recipes/{uuid}/translate {language}` (editor+) → LLM translation stored in
  `translations[language]`; returns the localized recipe.
- `POST /recipes/parse` (form field `language`) and `POST /recipes/import-url` (`language`) →
  extraction writes output in that language (default: request language); stored as `inLanguage`.
- Search haystack includes all translations.

### LLM provider
`api/translation.py` with a small provider seam (`TRANSLATION_PROVIDER`, default `openai`) so
another provider can be plugged in without touching routers. OpenAI implementation uses
structured output, preserving ingredient/step counts and indices.

## Steps

- [x] 1. Backend: language registry + `request_language` dependency + `localize_recipe` (`api/i18n.py`)
- [x] 2. Backend: `users.language` migration + profile GET/PUT
- [x] 3. Backend: extraction prompts take a target language (image, HTML, JSON-LD via translation); bump prompt version
- [x] 4. Backend: translation provider module + `POST /recipes/{uuid}/translate`
- [x] 5. Backend: localized reads (recipe json/html, list, cookbook, meal plan, shopping list), language-aware PUT, clone, search
- [x] 6. Backend tests + lint
- [x] 7. Frontend: i18n core (dictionaries en/de, provider, `useI18n`, Accept-Language header, language picker)
- [x] 8. Frontend: replace UI strings in all pages/components with keys
- [x] 9. Frontend: recipe language display + edit screen translate banner + import passes language
- [x] 10. Frontend build + lint; docs (`.env.example`, README)

## Outcome

- Backend: `api/i18n.py` (registry, `request_language`, `localize_recipe`), `api/translation.py`
  (provider seam, OpenAI implementation, structure-preserving), `users.language`, language-aware
  extraction prompts (`IMAGE_PROMPT_VERSION` → v2), `POST /recipes/{uuid}/translate`, localized
  reads across recipes / cookbooks / meal plan / shopping list / Bring HTML, language-aware PUT,
  search over all translations. 25 new tests in `tests/test_languages.py`; 240 pass, 88.5% coverage.
- Frontend (`frontend-react`): `src/i18n/` (typed en/de dictionaries — a missing German key fails
  `tsc`), `useI18n()` with `t` / `tp` (plurals) / `tx` (JSX placeholders), `Accept-Language` on
  every request, language picker on Account + Login, profile sync, locale-aware dates, import
  dialogs with a target-language field, "not available in your language" notice on the recipe
  view, and a Language section with "Translate with AI" / re-translate on the edit screen.
  `tsc -b` + `vite build` pass; eslint unchanged at the 18 pre-existing errors.
- Not done: the legacy vanilla `frontend/` (not served by docker-compose) was left untranslated.
  Only the OpenAI translation provider exists; others plug into `_PROVIDERS`.

### Follow-up: backfill for existing recipes (2026-11-04)

- `backend/translate_recipes.py` + `.github/workflows/translate-recipes.yml` (manual trigger,
  modes dry-run / detect-only / translate, optional languages / limit / uuid). Idempotent;
  skips recipes edited mid-run. Shared logic moved into `api/translation.py`
  (`recipe_content`, `detect_recipe_language`, `add_translation`, `Provider` with
  translate + detect). 10 tests in `tests/test_translate_recipes.py`.
