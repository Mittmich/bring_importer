# Plans

This directory holds plan files for the **Recipe to Bring Importer** project. Each plan is a single markdown file with a standard frontmatter and section structure.

Plans are **version-controlled alongside the code** so they can be reviewed, diffed, and referenced from commits. They are the source of truth for in-flight work.

## Conventions

- **One plan per file.** Filename: `YYYY-MM-DD-<kebab-slug>.md`. The date is the day the plan was created.
- **Files starting with `_`** (e.g. `_template.md`) are not plans and are skipped by the tooling. Use them for templates and reference docs only.
- **Frontmatter** uses these fields:
  - `title` — short, verb-led summary
  - `status` — one of `draft`, `active`, `done`, `archived`
  - `created`, `updated` — ISO dates (`YYYY-MM-DD`)
  - `scope` — `backend`, `frontend`, `fullstack`, or `infra`
- **Steps** are markdown checkboxes: `- [ ]` open, `- [x]` done. One verifiable change per step.

## Status lifecycle

```
draft  →  active  →  done
                  ↘  archived   (superseded, abandoned, or kept for reference)
```

A plan moves from `draft` to `active` only when someone runs `/plan-execute` on it and the user confirms.

## Workflow

1. `/plan <topic>` — creates a new plan file in `draft` status. The agent explores the codebase, asks clarifying questions if needed, and writes the file.
2. `/plan-execute <name-or-path>` — reads the plan, confirms with you, then walks through the steps. After each step, the plan file is updated (`- [x]`, plus a `> _Done:_` note if non-obvious). When all steps are done, status flips to `done` and an `## Outcome` section is appended.
3. `/plan-list` — lists every plan grouped by status, with step progress.

The **active-plans extension** also injects a short summary of `active` and `draft` plans into every turn, so the agent always knows what's in flight even if you don't mention it.

## Starting a new plan

Copy `_template.md`, fill in the frontmatter and sections, and save with a date-prefixed filename. Or just type `/plan <topic>` in the editor and let the agent do it.

## Why markdown?

- Diffs cleanly in code review.
- Renders in any Git host (GitHub, GitLab, etc.).
- No special tooling required to read or write.
- The same file is human-readable, agent-readable, and grep-able.
