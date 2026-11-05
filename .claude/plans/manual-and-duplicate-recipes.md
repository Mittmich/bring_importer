---
name: manual-and-duplicate-recipes
status: done
updated: 2026-11-05
---

# Manual recipe creation + duplicating recipes

## Goal

1. Add a recipe by hand (no photo/URL, no LLM call).
2. Duplicate an existing recipe the user can see (own, shared via cookbook, or public).

## Design

- `POST /recipes` (auth): body `ManualRecipe` — `title` required, everything else optional
  (`ingredients`, `instructions`, `recipeYield`, `description`, `note`, `language`, `ingredients_text`).
  Stored via `_store_recipe` with `source={"kind":"manual","value":""}` and `inLanguage` =
  explicit language > request language > profile language.
- `POST /recipes/{uuid}/clone` widened: allowed when the recipe is public **or** the caller
  has viewer+ access (still 404 otherwise). Copies content + translations + hero image.
  When the caller owns the original it's a "duplicate": title gets a localized
  " (copy)" / " (Kopie)" suffix (base + translations), and note + tags are copied too.
- Frontend (design option B, chosen 2026-11-05 from mockups):
  - "Add recipe" opens a chooser (From a photo / From a website / Write it yourself) instead
    of jumping straight into the photo dialog.
  - "Write it yourself" form: title, servings, language, optional ingredients pasted one
    per line (split into amount/name server-side via `ingredients_text`) → create → editor.
  - Recipe view: secondary actions (Duplicate, Export PDF, Share with friend, Copy public
    link, Delete) move into a "⋯" overflow menu; the mobile top bar shrinks accordingly.
    Duplicate → clone → open the copy.
- Recipes without a photo get a warm gradient cover (palette picked deterministically from
  the uuid) everywhere covers are shown (`RecipeCover`).

## Steps

- [x] 1. Backend: `ManualRecipe` model + `POST /recipes`
- [x] 2. Backend: widen clone (access, image, owner duplicate suffix/note/tags)
- [x] 3. Backend tests
- [x] 4. Backend: `ingredients_text` line parser (+ tests)
- [x] 5. Frontend: api helpers, chooser + manual form, overflow menu with Duplicate, i18n
- [x] 6. Frontend: gradient `RecipeCover` for recipes without a photo
- [x] 7. Typecheck/lint/build, tests, docs

## Outcome

- Backend: `POST /recipes` (`ManualRecipe`, `ingredients_text` split by
  `api/ingredient_lines.py`, source `manual`); clone widened to viewer+/public with image
  copy, and for own recipes a localized "(copy)/(Kopie)" suffix on every variant plus note
  and tags. 307 backend tests pass (new: `tests/test_manual_and_duplicate.py`); smoke-tested
  over HTTP against a throwaway server (create → duplicate → PDF → delete original).
- Frontend: `AddRecipeModal` chooser + `ManualRecipeModal` (→ editor); "Import" labels
  became "Add"; recipe view secondary actions in a `Menu` ("⋯": Duplicate / Save a copy,
  Export PDF, Share with a friend, Copy public link, Delete); mobile top bar is now
  Keep-awake + Edit + ⋯; `useExportPdf` hook; `RecipeCover` gradient for photo-less recipes in
  the list, home shelves, cookbook grid, recipe view and public page. tsc + build pass;
  eslint stays at the 18-error baseline.
- Not done: visual check in a browser (no browser tooling in this session).

## Follow-up (2026-11-05): manual → editor draft

User feedback: the "Write it yourself" form was too many clicks. Now the chooser goes
straight to `/recipes/new`, the editor in draft mode (language picker instead of the
translation section; Save disabled until there's a title; Back asks before discarding a
non-empty draft). First Save → `POST /recipes` with the whole draft (now also `tags`,
`is_public`) → photo upload → replaces history with the new recipe. `ManualRecipeModal`
and its strings are gone; `ingredients_text` stays as an API convenience.
