---
description: List all plans under .pi/plans/ grouped by status
---

List every plan under `.pi/plans/` (skip files starting with `_` — those are templates).

For each plan, parse the YAML frontmatter and extract at minimum: `title` (or first H1), `status`, `created`, `updated`, and the count of `- [ ]` vs `- [x]` steps.

## Output format

Group plans by status in this order: `active`, `draft`, `done`, `archived`. Within each group, sort newest first by `updated` (fall back to `created`).

For each plan, print one block:

```
<status-badge> <title-or-filename>   <updated-date>   <N>/<M> steps done
       .pi/plans/<file>
       <one-line summary from the Context section, if present>
```

Use these short status badges:

- `active`   → `[ACTIVE]`
- `draft`    → `[DRAFT ]`
- `done`     → `[DONE  ]`
- `archived` → `[ARCH  ]`

If the directory is empty or missing, say so plainly and remind the user that `/plan <topic>` creates one.

## How to extract data

- Use `ls .pi/plans/*.md` to enumerate files.
- Use the `read` tool to fetch each file. Frontmatter is between the first pair of `---` lines; status is the value of `status:`.
- Count step checkboxes with a single pass over the file body: `- [ ]` = open, `- [x]` / `- [X]` = done.
- Don't summarize content beyond the one-line Context line — the user can open the file for details.

End the output with a one-line summary: `N active, M draft, K done, J archived.`
