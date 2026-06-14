---
description: Read a plan from .pi/plans/ and execute it, updating the plan as you go
argument-hint: "<plan-name-or-path>"
---

You are executing a plan for the **Recipe to Bring Importer** repo. The plan lives as a markdown file under `.pi/plans/`.

**Target plan:** $1

## Process

1. **Locate the plan.**
   - If `$1` is an absolute or repo-relative path ending in `.md`, use it directly.
   - Otherwise treat `$1` as a slug or filename and look in `.pi/plans/`. Use `ls .pi/plans/` to see what's there. If ambiguous, ask the user to disambiguate.
2. **Read the plan in full** with the `read` tool. Do not skim — re-read after any prior execution markers if you find them.
3. **Confirm with the user** before doing any destructive work. Show:
   - The plan path and current `status:` value.
   - The remaining unchecked steps.
   - Any sections marked as open questions or risks.
   Ask whether to proceed, refine the plan, or cancel.
4. **Update status.** If the plan is `draft`, set it to `active` (and add a `started: YYYY-MM-DD` field if absent) once the user approves.
5. **Execute steps in order.** For each step:
   - Do the work using the regular tools (`read`, `edit`, `write`, `bash`, `grep`, `find`, `ls`).
   - Follow the conventions in `AGENTS.md` (no new build step for frontend, bump `service-worker.js` cache on frontend changes, keep secrets out of logs, etc.).
   - Run the project's verification commands (`ruff check .`, `black --check .`, `isort --check-only .`, `python3 -c "import api"`, etc.) where appropriate.
   - After the step is verifiably complete, edit the plan file to flip `- [ ]` → `- [x]` on that step's line. Add a one-line `> _Done YYYY-MM-DD:_ <one-sentence outcome>` note under the step if non-obvious.
   - Persist the updated plan after every step (don't batch).
6. **Update the plan's `updated:` field** to today's date whenever you change the file.
7. **Finish.** When every step is checked:
   - Set `status: done` in the frontmatter.
   - Append a `## Outcome` section at the bottom with a short summary of what shipped, files changed, and any deviations from the original plan.
   - Tell the user the plan is complete and link to the final state.

## If something blocks you

- **Plan is wrong / outdated:** pause, surface the discrepancy, propose a refinement, and let the user decide. Do not silently rewrite the plan.
- **Step reveals new work:** add new `- [ ]` items to the plan under a `## Discovered during execution` sub-section, then continue.
- **Step is impossible / wrong call:** mark it `- [x] ~~step~~ (reverted: <reason>)` and surface to the user.
- **Verification fails:** stop, do not mark the step done, report the failure with the exact error.

## Hard rules

- The plan file is the **source of truth for progress**. Never rely on chat history — if a step isn't checked in the file, it's not done.
- One plan at a time. If the user wants to run multiple plans in parallel, they should switch sessions.
- Do not start a second plan mid-execution without explicit user approval.
