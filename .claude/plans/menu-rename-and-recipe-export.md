---
title: Menu — visible rename + export with recipes
status: done
created: 2026-11-11
updated: 2026-11-11
---

# Menu — visible rename + export with recipes

User request: make the menu name editable; export the recipes together with the menu plan.

## Steps

- [x] Rename: the card title was already an input but looked static. Add a pencil button and hover state on the card title, make the header title a button, add "Rename menu" to the header ⋯ menu (all focus + select the card title).
- [x] Backend: `GET /menus/{id}/plan.pdf?recipes=true` appends each course's recipe (course name as kicker, scaled to the guests, with photo). Recipes the user can no longer access are skipped. `recipe_pdf.draw_recipe` factored out of `render_pdf`.
- [x] Frontend: "Export PDF" becomes a dropdown — "Plan only" / "Plan with recipes"; i18n en/de.
- [x] Tests + lint + browser check.

## Outcome

- New test `test_menu_pdf_with_recipes` (default is plan only; `recipes=true` draws one recipe per course, scaled to 6 guests). Backend tests, ruff/black/isort, ty baseline, tsc + vite build, eslint baseline (17) all OK.
- Browser (local, fake OpenAI): renamed via ⋯ → "Rename menu", survives reload, header updates; both exports download as `<menu title>.pdf` — 5 pages plan only, 7 with recipes; recipe page shows "STARTER / Lemon tart / 4 servings" with amounts scaled from 8 to 4.
