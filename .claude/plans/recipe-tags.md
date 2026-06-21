---
name: recipe-tags
status: active
---

# Recipe Tags (user-defined) + Filtering

User-defined tags on recipes, with the ability to filter the recipe list by one or more tags.
Builds on the paginated `GET /recipes` route (implemented alongside this plan).

## Decisions / approach

- **Normalized storage** (not a JSON blob on the recipe), so we can list all of a user's tags, rename/
  delete a tag across recipes, and filter efficiently with pagination:
  - `tags(id INTEGER PK, user_id INTEGER, name TEXT)` — unique per `(user_id, lower(name))`.
  - `recipe_tags(recipe_uuid TEXT, tag_id INTEGER, PRIMARY KEY(recipe_uuid, tag_id))`.
- Tags are **per-user** and created on demand (typing a new tag name creates it).
- Filtering is **AND** by default (a recipe must have all selected tags) — match the mental model of
  narrowing down. (Open to OR; AND is the safer default.)
- Reuses the paginated list endpoint: `GET /recipes?...&tag=<name>&tag=<name>` (repeatable).

## Backend

### db.py
Add `tags` and `recipe_tags` tables (`CREATE TABLE IF NOT EXISTS`). Index `recipe_tags(tag_id)` and
`tags(user_id)`.

### models.py
`TagAssign { tags: list[str] }` (set the full tag list for a recipe). `Tag { id, name, count }` for listing.

### routers/recipes.py
- Extend `GET /recipes` (already paginated) with a repeatable `tag` query param → filter to recipes
  having **all** named tags (JOIN/`GROUP BY ... HAVING COUNT(DISTINCT tag)=N`). `q` + `tag` combine.
- Include each recipe's `tags: list[str]` in the list items and in `GET /recipes/{uuid}.json`.
- `PUT /recipes/{uuid}/tags` (auth, body `TagAssign`) → upsert tag names for the user, replace the
  recipe's tag set. Normalizes names (trim, collapse whitespace; case-insensitive de-dupe).
- `GET /tags` (auth) → the user's tags with usage counts (for the filter UI / autocomplete).
- (Optional) `DELETE /tags/{id}` and `PATCH /tags/{id}` (rename) for tag management.
- Clean up `recipe_tags` rows on recipe delete; drop now-orphaned tags or leave them (decide — leaving is
  simpler, orphans show count 0).

## Frontend

### api.ts
`getTags()`, `setRecipeTags(uuid, names)`, and extend the list query to pass `tag` params. `RecipeListItem`
and `Recipe` gain `tags: string[]`.

### Edit screen ([EditRecipePage](frontend-react/src/pages/EditRecipePage.tsx))
A tag editor: chips with remove + an input with autocomplete from `getTags()` (free text creates a new
tag). Saved via `PUT /recipes/{uuid}/tags` (either on save or immediately).

### List ([RecipeListPanel](frontend-react/src/components/RecipeListPanel.tsx))
- A tag filter bar (chips from `getTags()`); selecting tags adds `tag=` params to the infinite query
  (resets pagination). Show selected tags as removable chips; "clear".
- Show each recipe's tags as small chips on the row (optional, space-permitting).

### Detail ([RecipeDetail](frontend-react/src/components/RecipeDetail.tsx))
Render the recipe's tags as chips.

## Tests
- CRUD: assign tags (creates new, reuses existing, case-insensitive), list tags with counts, filter list
  by one/multiple tags (AND), `q`+`tag` combined, ownership isolation, tag cleanup on recipe delete.

## Open questions (resolve before implementing)
- AND vs OR filtering (default AND).
- Delete orphaned tags automatically, or keep them?
- Edit tags inline on save, or a dedicated immediate `PUT /tags` on each change?
