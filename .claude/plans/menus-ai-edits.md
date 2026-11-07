---
title: Menus — instructions for drafting, "Edit with AI", course order and names
status: done
created: 2026-11-07
updated: 2026-11-07
---

## Goal

Let the cook steer the AI:

1. **Instructions when drafting** — an optional note when adding a course or drafting its steps
   again ("make the dough the day before", "we have a sous-vide", "keep it under an hour").
2. **Edit with AI** — one text box for the whole menu ("serve dessert at 21:30", "do the
   marinade the day before", "split the roasting into two steps"); the AI rewrites the plan.

## Steps

- [x] Backend: `draft_prep_steps(..., instructions)`; `instructions` on `POST /courses` and
      `POST /courses/{id}/redraft` (optional body), max 500 chars.
- [x] Backend: `revise_plan` in `prep_steps.py` + `POST /menus/{id}/revise {request}`. Courses
      may get new serving times and steps; courses the AI leaves out stay as they are; unknown
      course ids are ignored. LLM failure → 502, plan unchanged.
- [x] Tests for both.
- [x] Frontend: notes field in the course picker and a redraft dialog with notes; "Edit with AI"
      dialog on the prep plan with example prompts. i18n en/de.
- [x] Lint, ty, tests, eslint, build; screenshots.

## Outcome

- `draft_prep_steps(recipe, language, instructions)` appends the cook's notes to the prompt.
  `POST /courses` takes `instructions`; `POST /courses/{id}/redraft` takes an optional body.
- `revise_plan` + `POST /menus/{id}/revise`: the AI returns only the courses it changes (all their
  steps + serving time). Unknown/duplicate course ids are dropped, a course is never wiped, and
  day-before start times are kept. AI failure → 502, plan unchanged. 400 on an empty menu.
- UI: notes field in the course picker; the redraft dialog has a notes box (replaces the
  confirm); "Edit with AI" dialog on the prep plan with three example prompts.
- Tests: 5 new (396 total). E2E with Playwright against a fake OpenAI server: notes reach
  the prompt, the revision moves the main course +30 min and replaces its steps, redraft
  with notes works, and the AI-down path returns 502 with the plan unchanged.
- Not verified: the real model's answers to edit requests.

## Follow-up: course order and names (2026-11-07)

- `PUT /menus/{id}/courses/order {course_ids}` sets positions 0..n; it must list every course
  once (else 400). Serving times are not changed by reordering.
- Course ⋯ menu: Rename course (focuses the inline name field), Move up, Move down; the
  name field shows a hover state so it reads as editable. Optimistic reorder in `useMenu`.
- 1 new test; verified in the browser (move + rename survive a reload).
