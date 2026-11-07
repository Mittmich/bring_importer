---
name: menus-prep-planning
status: done
created: 2026-11-07
updated: 2026-11-07
---

# Menus with prep planning (behind a feature flag)

## Goal

A **menu** is a set of recipes (courses) cooked for one occasion. Each course has a
serving time. Prep steps (duration, hands-on or not, equipment, oven temperature) are
drafted by GPT from each recipe's instructions and are fully editable. The plan is
visualized and drives a live cook mode. A global feature flag switches the "Plan" area
between the existing **weekly plan** and the new **menus**.

Design studies: scratchpad `design-options/menu-studies.html` (A timeline, B run sheet,
C cook mode, D menu card). Chosen: D as the menu page; plan shown as A on desktop and
B on mobile (switchable on desktop); C as "Start cooking".

## Decisions

- **Feature flag:** global, admin-controlled, stored in a new `app_settings` table
  (`planner` = `weekly` | `menus`). Default comes from env `PLANNER_MODE` (default
  `weekly`, so production doesn't change until an admin flips it). `GET /features`
  (auth) returns it; `PUT /admin/features` (admin) sets it. The flag only switches the
  UI (nav entry + `/plan` route); weekly-plan and menu data both stay intact.
- **Timing model:** a same-day step stores `lead` = minutes before its course is served
  by which it must be finished, plus `duration`; start = serve − lead − duration, so
  moving a serving time moves its steps. Day-before steps store an absolute start (`at`).
- **Recipes:** any recipe the user can access (own or shared via cookbook).
- **Guests** scale ingredient amounts (shopping list), never durations.
- **Shopping list:** reuse `shopping_lists` + the public Bring HTML page and
  `merge_ingredients`; amounts scaled per course by guests ÷ recipe yield.
- **PDF export** (requested mid-build): `GET /menus/{id}/plan.pdf` renders the menu card and
  the run sheet with fpdf2, reusing the recipe PDF's page setup (`api/menu_pdf.py`).

## Steps

- [x] 1. Backend schema: `app_settings`, `menus`, `menu_courses`, `menu_steps` (+ admin user deletion cleans them up).
- [x] 2. Feature flag: `api/features.py`, `GET /features`, `PUT /admin/features`, `PLANNER_MODE` in config + `.env.example`.
- [x] 3. Prep-step drafting: `api/prep_steps.py` (structured output + deterministic fallback + sanitising).
- [x] 4. Menus router `api/routers/menus.py`: menu CRUD, courses (add drafts steps, redraft), steps CRUD, shopping list.
- [x] 4b. Menu PDF export `api/menu_pdf.py` + `GET /menus/{id}/plan.pdf` (+ en/de labels).
- [x] 5. Backend tests (`tests/test_menus.py`, `tests/test_features.py`), lint, ty.
- [x] 6. Frontend API client + types + `useFeatures` hook; `lib/menuPlan.ts` (timing, clashes, workload).
- [x] 7. Menus list page + menu page (card, guests, courses, recipe picker, stats, workload chart, actions).
- [x] 8. Plan views: timeline with drag + step editor (desktop), run sheet (mobile/print), toggle.
- [x] 9. Cook mode page.
- [x] 10. Flag wiring: nav (Sidebar/BottomNav), `/plan` switch, routes, admin toggle; i18n en/de.
- [x] 11. Build, lint baseline, screenshots at desktop + phone width against a local backend.

## Outcome

- Backend: `app_settings` + `menus`/`menu_courses`/`menu_steps` tables; `api/features.py` +
  `GET /features`, `PUT /admin/features`; `api/prep_steps.py` (GPT draft, sanitised, with a
  one-step-per-instruction fallback); `api/routers/menus.py` (menus, courses, steps, redraft,
  shopping list scaled to guests); `api/menu_pdf.py` + `GET /menus/{id}/plan.pdf`.
  The shared Bring page is now titled "Shopping List" (was "Weekly Shopping List").
- Frontend: `/plan` shows the weekly plan or the menus list depending on the flag; `/menus/:id`
  (menu card, guests, courses, stats, workload chart, timeline with drag + step editor on
  desktop, run sheet on phones/list view), `/menus/:id/cook` (cook mode). Admin › Features
  switches the flag. en/de strings.
- Checks: 387 backend tests pass (23 new); ruff/black/isort clean; ty at its 7-diagnostic
  baseline; `npm run build` passes; eslint at its 18-error baseline. Exercised end to end
  against a local backend with a throwaway DB: screenshots of the menu page (desktop +
  500 px phone), cook mode, menus list, admin, and the weekly plan after switching back.
- Default flag is `weekly`, so deploying changes nothing until an admin switches it.
- Not verified: drafting with a real OpenAI key (only the fallback ran locally), dragging and
  editing by hand in a real browser, the Bring import with a real list.

