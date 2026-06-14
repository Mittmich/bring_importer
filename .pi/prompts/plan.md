---
description: Create a new plan as a markdown file under .pi/plans/
argument-hint: "<topic>"
---

You are creating a plan for the **Recipe to Bring Importer** repo. The plan must be a durable markdown file under `.pi/plans/` so it can be reviewed, version-controlled, and later executed by `/plan-execute`.

**Topic:** $1

## Process

1. **Explore first.** Read `AGENTS.md` (if present) and any code relevant to the topic. Do not invent files or APIs — verify with `read` / `grep` / `ls`.
2. **Ask clarifying questions** if the scope is ambiguous (use the `question` tool, not the editor). Limit to questions you cannot resolve from the codebase.
3. **Choose a filename:** `.pi/plans/YYYY-MM-DD-<kebab-slug>.md` where the date is today (use `date +%Y-%m-%d` via bash if needed) and the slug is a short kebab-case summary of the topic. If a plan with the same slug already exists, pick a disambiguating suffix (`-v2`, `-alt`).
4. **Write the plan** using the standard template at `.pi/plans/_template.md`. Fill in every section. Steps must be concrete, ordered, and individually verifiable (each one should describe a single, checkable change). Mark unfinished steps with `- [ ]`.
5. **Show the user** the file path and a brief summary of the plan's top-level steps. Do not begin execution.

## Plan status lifecycle

Use one of these statuses in the frontmatter:

- `draft` — being written or awaiting review
- `active` — approved and being executed
- `done` — all steps checked off
- `archived` — superseded, abandoned, or kept for reference

New plans you create start as `draft`. They become `active` only after the user explicitly approves them (e.g. via `/plan-execute`).

## Conventions for the plan body

- **Context** — 1–3 sentences on *why* this is being done. Link to issues/tickets if mentioned.
- **Goals** — bullet list of outcomes, not tasks.
- **Non-goals** — explicit out-of-scope items to prevent scope creep.
- **Steps** — numbered checklist. Each step is one verifiable change. Order matters; later steps may depend on earlier ones.
- **Files to touch** — bullet list of paths under `backend/` and/or `frontend/` you expect to modify. Mark unknowns with `?`.
- **Verification** — concrete commands or manual checks that prove the plan worked. Prefer existing test/lint commands (see `AGENTS.md`).
- **Notes / risks** — open questions, gotchas, or things to revisit during execution.

## Hard rules

- Plans are **markdown only** — no code blocks of "the implementation". The plan describes what to do; the implementation lives in real commits.
- Plans must be **self-contained**: another agent reading only the plan file should understand what to do.
- Do **not** start editing source files. Stop after writing the plan and reporting the path.
- If the topic is trivial (one-line change), still create a plan file but keep it short — the file is the unit of record, not the size.
