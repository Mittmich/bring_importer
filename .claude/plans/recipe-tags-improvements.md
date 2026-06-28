---
name: recipe-tags-improvements
status: active
---

# Recipe Tags — Improvements (management page, colours, row visibility, chip-select editor)

Builds on the already-shipped tag foundation (see [recipe-tags.md](recipe-tags.md)): the
`tags` / `recipe_tags` tables, `PUT /recipes/{uuid}` accepting `tags`, `GET /recipes/tags`
(in-use tags with counts), tag filtering on `GET /recipes`, detail chips, and a datalist-based
editor. This plan layers four improvements on top.

## Requirements

1. Tags editable from a **separate page** (rename / recolour / delete), nested under Account at
   `/account/tags`, and reachable via a link from the recipe edit screen's tag editor.
2. Tags have a **colour**: an assigned colour, defaulting to a nice palette **derived from the
   current theme**.
3. A recipe's tags are **visible on the rows** of the recipe overview list (display-only).
4. The add-tags UX shows **existing tags as chips to quick-select**, with a **text input** to add
   new ones.

## Key design decision — where colour lives

The stored colour is **nullable**. When a tag has no explicit colour, the **frontend derives a
stable default** from the tag name against a palette defined alongside the theme. This keeps the
palette in exactly one place (frontend, next to `index.css`), so it genuinely tracks the theme and
the backend never needs to know about colours beyond storing an optional string. Setting a colour
on the management page persists an explicit choice that overrides the derived default.

---

## Backend

### [db.py](../../backend/api/db.py)
- Add `color TEXT` (nullable) to the `tags` `CREATE TABLE` for fresh DBs.
- **Migration for existing DBs** (the table already exists, so `CREATE TABLE IF NOT EXISTS` won't
  add the column): after the create, check `PRAGMA table_info(tags)` and `ALTER TABLE tags ADD
  COLUMN color TEXT` if absent. Idempotent, runs on startup like the other table creation.

### [models.py](../../backend/api/models.py)
- `Tag { id: int, name: str, count: int, color: str | None }` — for the list/management responses.
- `TagUpdate { name: str | None, color: str | None }` — partial update for rename/recolour.
- Recipe-embedded tags become `{ name, color }` objects (see router note below). Keep the existing
  `RecipeUpdate.tags: list[str]` (the editor still sends names; colours are managed separately).

### [routers/recipes.py](../../backend/api/routers/recipes.py)
- **`GET /recipes/tags`** (`list_tags`): currently `JOIN recipe_tags` so it only returns *in-use*
  tags and has no id/colour. Change to **`LEFT JOIN`** so orphaned tags appear (needed for the
  management page), and select `t.id`, `t.color`, and `COUNT(rt.recipe_uuid) AS count`. Returns
  `list[Tag]`.
- **`_tags_for(cursor, uuids)`**: also select `t.color`; return `{uuid: [{name, color}, ...]}`
  instead of `{uuid: [name, ...]}`. Update both call sites (`list_recipes` item `tags` and
  `get_recipe`). Detail/list payloads now carry colour so chips render correctly everywhere.
- **`PATCH /recipes/tags/{tag_id}`** (auth, body `TagUpdate`): ownership-checked; rename (normalize
  + reject case-insensitive collision with another of the user's tags → 409) and/or set colour.
- **`DELETE /recipes/tags/{tag_id}`** (auth, status 204): ownership-checked; delete the tag and its
  `recipe_tags` rows.
- The tag-filter query in `list_recipes` is unaffected (still filters by name).

> Note: tag routes live under the `/recipes` prefix (`/recipes/tags`), matching the existing
> `GET /recipes/tags`. Keep that prefix for consistency rather than introducing a new `/tags` router.

---

## Frontend

### Palette + helper — new `src/lib/tagColors.ts`
- Export `TAG_PALETTE`: ~10 theme-harmonious hex swatches at consistent saturation/lightness, anchored
  on the primary indigo (`hsl(239 84% 67%)` ≈ `#6366f1`). Suggested hues: indigo, violet, blue,
  cyan/teal, emerald, amber, orange, rose, pink, slate.
- `tagColor(name: string, explicit?: string | null): string` — returns `explicit` if set, else a
  **stable** palette pick via a simple string hash of the lowercased name (deterministic, no server
  state). This is the single source of truth used by every chip.
- A small `TagChip` component (in `src/components/ui/`) rendering a soft tinted chip: background at
  the colour's ~12% alpha, colour-toned text, subtle border — legible on white for the whole palette.
  Optional `onRemove` for the editor.

### [api.ts](../../frontend-react/src/lib/api.ts)
- `TagInfo` → `{ id, name, count, color: string | null }`.
- `RecipeListItem.tags` / `Recipe.tags` → `{ name: string; color: string | null }[]`.
- Add `updateTag(id, { name?, color? })` → `PATCH /recipes/tags/{id}` and `deleteTag(id)` →
  `DELETE /recipes/tags/{id}`. `setRecipeTags`/list params keep sending **names** (`string[]`).

### Tag management page — new `src/pages/TagsPage.tsx`, route `/account/tags`
- Lists all of the user's tags (`getTags`, now includes orphans + counts + colour) as rows, each
  showing the `TagChip`, usage count, a **palette swatch picker** (curated swatches only — clicking a
  swatch `PATCH`es the colour), an inline **rename** input, and a **delete** button (confirm).
- Mutations invalidate `['tags']` and `['recipes']` queries so chips refresh everywhere.
- Wire route in [App.tsx](../../frontend-react/src/App.tsx) under the authed layout.
- Add a "Manage tags" link on [AccountPage.tsx](../../frontend-react/src/pages/AccountPage.tsx).

### Edit screen — [EditRecipePage.tsx](../../frontend-react/src/pages/EditRecipePage.tsx)
- Replace the `<datalist>` autocomplete with the requested UX:
  - **Selected tags**: `TagChip`s with a remove (×) button.
  - **Quick-select**: all of the user's existing tags (from `getTags`) rendered as toggleable chips;
    clicking adds/removes from the selection. Hide ones already selected, or show them as active.
  - **New tag**: keep the text input — Enter (or comma) creates a new tag name and adds it.
  - Small **"Manage tags →"** link to `/account/tags`.
- Still saves names via the existing `PUT /recipes/{uuid}` `tags` field.

### Recipe list rows — [RecipeListPanel.tsx](../../frontend-react/src/components/RecipeListPanel.tsx)
- In `RecipeRow`, render the recipe's tags as small `TagChip`s under the title/meta line
  (display-only — no click handlers, so row navigation is unaffected). Cap visible chips (e.g. show
  first 3 + "+N") to protect the 300px-wide panel layout.

### Recipe detail — [RecipeDetail.tsx](../../frontend-react/src/components/RecipeDetail.tsx)
- Swap the existing plain tag chips for `TagChip` so detail matches list/edit colouring.

---

## Tests (backend — [backend/tests](../../backend/tests))
- `list_tags` now returns id + colour + count and **includes orphaned** tags (LEFT JOIN).
- `PATCH /recipes/tags/{id}`: rename success; case-insensitive collision → 409; set colour; ownership
  isolation (404 for another user's tag).
- `DELETE /recipes/tags/{id}`: removes tag + its `recipe_tags`; ownership isolation.
- Recipe list/detail payloads include `tags` as `{name, color}` objects.
- Migration: `color` column present after `init_db` on a DB created without it.

## Verification
- Backend: `uv run` test suite (per [feedback_uv_tooling]); colour migration on the existing
  `recipes.db`.
- Frontend: manual pass — create tags via edit page chips, recolour/rename/delete on `/account/tags`,
  confirm chips recolour live on list rows, detail, and edit; confirm derived default colour is stable
  for an uncoloured tag.

## Open questions
- Palette exact hex values (tune visually once `TagChip` renders).
- Comma-as-separator in the new-tag input — include or Enter-only? (Enter-only is fine to start.)
