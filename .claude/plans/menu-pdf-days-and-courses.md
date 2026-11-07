---
title: Menu PDF — split by day and by course
status: done
created: 2026-11-07
updated: 2026-11-07
---

# Menu PDF — split by day and by course

User request: day-before steps show up in the PDF timeline as (cut-off) blocks that take
space. Split the report into "the day before" and "on the day", and add a part split by course.

## Layout

1. Page 1: title, date/guests, menu card (unchanged).
2. **The day before** (only if there are day-before steps): run sheet, then a landscape
   timeline of the day before only. Its window is set by the day-before steps; long or
   overnight steps are cut off at the right edge ("until 10:00 on the day").
3. **On the day**: run sheet with serving times, then a landscape timeline of the cooking day.
   Day-before / overnight steps no longer appear as bars here.
4. **By course** (revised after feedback: a *visual* timeline per course, not a list):
   landscape page(s) with one block per course — heading (course, recipe, served at), a
   day-before chart if the course has such steps, then the cooking-day chart, each on the
   course's own time scale.

## Steps

- [x] `menu_pdf.py`: day-before window + bars (right-cut), drop overnight bars from the day timeline, generalise the timeline page per day, oven clashes per day.
- [x] `menu_pdf.py`: restructure the run sheet into day sections + by-course section; restore auto page break after a timeline page.
- [x] i18n keys (en/de): `by_course`, `until_on_the_day`, `continues_later`.
- [x] Tests: update overnight test, add day-before window/bars test, PDF page orientation sequence.
- [x] Lint (ruff, black, isort), ty, pytest; render a sample PDF and look at it.

## Outcome

- The report is now: menu card → *The day before* (run sheet + landscape timeline of that day,
  only when there are day-before steps) → *On the day* (run sheet + timeline, no day-before bars)
  → *By course*: landscape timeline blocks per course, each on its own time scale
  (`day_window(..., earliest=None)`), in the course's colour, blocks flow across pages.
- Day-before window: first step → end of the last short/hands-on step; long fridge/overnight steps
  are cut off at the right edge ("bis 07:30 am Tag selbst"). Legend shows torn-edge entries only
  when used. `step_start` now defaults a missing day-before `at` to 18:00, like the app.
- Tests: 407 passed (new: day-before timeline, cut-bar text, page order per part). Ruff/black/isort
  clean, ty at baseline 7. Sample 3-course German menu rendered and checked visually (5 pages).
