---
name: backend-frontend-adaptation
status: done
---

# Backend Adaptation for React Frontend

## Goal

Fix three concrete issues between the current backend and the new React frontend:

1. **Title update bug** — `PUT /recipes/{uuid}` writes to `stored["title"]` but the stored JSON uses `"name"` as the key. After an edit, the recipe detail (which reads `recipe.name` from the `.json` endpoint) still shows the old name.
2. **Unstructured instructions** — `html_content` stores the full schema.org HTML; the frontend's `InstructionsDisplay` does `querySelectorAll('li')` which picks up ingredient list items too. Need a `recipeInstructions: string[]` field parallel to `recipeIngredient`.
3. **Missing `created_at` in list** — the list endpoint omits `created_at` from the DB row, so the frontend has no reliable "imported at" timestamp (only `datePublished`, which is fine today but is a fragile dependency on the extraction setting it correctly).

---

## Steps

### ✅ 1. Fix `name`/`title` inconsistency in `PUT /recipes/{uuid}`

**File:** `backend/api/routers/recipes.py` — lines 309–315.

The update loop writes `stored["title"]` but the JSON blob key is `"name"` (set at store time by `schema_recipe["name"] = recipe.title`).

**Fix:** Map the update field to the correct stored-JSON key:

```python
# before
for field in ("title", "recipeIngredient", "recipeYield", "description", "html_content"):
    value = getattr(body, field)
    if value is not None:
        stored[field] = value
if body.note is not None:
    stored["note"] = body.note
new_title = stored.get("title", "")

# after
_JSON_KEY = {"title": "name"}   # RecipeUpdate field → stored JSON key
for field in ("title", "recipeIngredient", "recipeYield", "description",
              "html_content", "recipeInstructions"):
    value = getattr(body, field, None)
    if value is not None:
        stored[_JSON_KEY.get(field, field)] = value
if body.note is not None:
    stored["note"] = body.note
new_title = stored.get("name", "")   # was stored.get("title", "")
```

After this change, `stored["name"]` is always the authoritative title for the `.json` endpoint, and the DB `title` column stays in sync.

---

### ✅ 2. Add `recipeInstructions: Optional[List[str]]` to models

**File:** `backend/api/models.py`

Add the field to both `Recipe` (the internal extraction model) and `RecipeUpdate` (the PUT body):

```python
class Recipe(BaseModel):
    title: str
    recipeIngredient: List[str]
    recipeYield: str = "4 servings"
    datePublished: Optional[str] = None
    description: Optional[str] = None
    html_content: Optional[str] = None
    recipeInstructions: Optional[List[str]] = None   # ← add

class RecipeUpdate(BaseModel):
    title: Optional[str] = None
    recipeIngredient: Optional[List[str]] = None
    recipeYield: Optional[str] = None
    description: Optional[str] = None
    note: Optional[str] = None
    html_content: Optional[str] = None
    recipeInstructions: Optional[List[str]] = None   # ← add
```

---

### ✅ 3. Extract `recipeInstructions` in `_extract_recipe_from_html`

**File:** `backend/api/recipe_extraction.py`

After extracting ingredients, extract instruction steps from the schema.org HTML:

```python
# after the description extraction, before the return
instruction_elements = recipe_element.find_all(attrs={"itemprop": "recipeInstructions"})
instructions: List[str] = []
for el in instruction_elements:
    # Each element may itself contain <li> sub-steps or just be a text node
    sub_steps = el.find_all("li")
    if sub_steps:
        instructions.extend(li.get_text(" ", strip=True) for li in sub_steps if li.get_text(strip=True))
    else:
        text = el.get_text(" ", strip=True)
        if text:
            instructions.append(text)

# fallback: if the HTML has an <ol> not tagged with itemprop, use its <li> items
if not instructions:
    ol = recipe_element.find("ol")
    if ol:
        instructions = [li.get_text(" ", strip=True) for li in ol.find_all("li") if li.get_text(strip=True)]

return Recipe(
    ...
    recipeInstructions=instructions or None,
)
```

---

### ✅ 4. Extract `recipeInstructions` in `extract_recipe_from_jsonld`

**File:** `backend/api/recipe_extraction.py`

The JSON-LD `recipeInstructions` can be a `string`, a list of strings, or a list of `HowToStep` objects:

```python
raw_instructions = found.get("recipeInstructions") or []
instructions: List[str] = []
if isinstance(raw_instructions, str):
    instructions = [raw_instructions] if raw_instructions else []
elif isinstance(raw_instructions, list):
    for step in raw_instructions:
        if isinstance(step, str):
            instructions.append(step)
        elif isinstance(step, dict):
            # HowToStep: {"@type": "HowToStep", "text": "...", "name": "..."}
            text = step.get("text") or step.get("name") or ""
            if text:
                instructions.append(text)

return Recipe(
    ...
    recipeInstructions=instructions or None,
)
```

---

### ✅ 5. Store `recipeInstructions` in the JSON blob

**File:** `backend/api/routers/recipes.py` — `_store_recipe` function.

```python
schema_recipe = {
    "@context": "https://schema.org/",
    "@type": "Recipe",
    "name": recipe.title,
    "recipeIngredient": recipe.recipeIngredient,
    "recipeInstructions": recipe.recipeInstructions,   # ← add
    "recipeYield": recipe.recipeYield,
    "datePublished": recipe.datePublished,
    "description": recipe.description,
    "html_content": recipe.html_content,
    "source": source,
    "note": note,
}
```

No DB schema change needed — `recipeInstructions` lives in the `recipe_json` blob.

---

### ✅ 6. Add `created_at` to the list endpoint response

**File:** `backend/api/routers/recipes.py` — `list_recipes` function.

Update the SELECT and the returned dict:

```python
cursor.execute(
    "SELECT uuid, title, recipe_json, created_at FROM recipes "   # ← add created_at
    "WHERE user_id = ? ORDER BY created_at DESC",
    (user_id,),
)
...
recipes.append(
    {
        "uuid": row["uuid"],
        "title": row["title"],
        "datePublished": recipe_json.get("datePublished"),
        "createdAt": row["created_at"],   # ← add
        "source": source,
    }
)
```

---

### ✅ 7. Update frontend API types and `RecipeListPanel`

**File:** `frontend-react/src/lib/api.ts`

```typescript
export interface RecipeListItem {
  uuid: string
  title: string
  datePublished?: string
  createdAt?: string        // ← add
  source?: { kind: string; value: string }
}

export interface Recipe {
  name: string
  recipeIngredient: string[]
  recipeInstructions?: string[]   // ← add
  recipeYield?: string
  description?: string
  html_content?: string
  source?: { kind: string; value: string }
  note?: string
  datePublished?: string
}
```

**File:** `frontend-react/src/components/RecipeListPanel.tsx`

Use `createdAt` as the fallback date:

```tsx
const displayDate = item.datePublished ?? item.createdAt
```

---

### ✅ 8. Update `RecipeDetail.tsx` to prefer `recipeInstructions`

**File:** `frontend-react/src/components/RecipeDetail.tsx`

`InstructionsDisplay` currently runs `querySelectorAll('li')` over the full HTML, which picks up ingredient `<li>` items too. When `recipeInstructions` is available, skip the HTML parse entirely:

```tsx
{/* Instructions */}
{(recipe.recipeInstructions?.length || recipe.html_content) && (
  <div className="bg-white rounded-lg border border-border overflow-hidden">
    <div className="px-4 py-3 border-b border-border">
      <h2 className="...">Instructions</h2>
    </div>
    {recipe.recipeInstructions?.length
      ? <StructuredInstructions steps={recipe.recipeInstructions} />
      : <InstructionsDisplay html={recipe.html_content!} />
    }
  </div>
)}
```

Add a `StructuredInstructions` component that renders the plain string array directly (same numbered-step style as the existing `InstructionsDisplay`).

---

### ✅ 9. Update `EditRecipePage.tsx` to edit instructions as a list

**File:** `frontend-react/src/pages/EditRecipePage.tsx`

The edit page currently sends only `{title, recipeYield, description, recipeIngredient, note}`.

Add an instructions textarea (one step per line, same pattern as ingredients):

```tsx
// load
const instructionsText = (recipe.recipeInstructions ?? []).join('\n')

// save — convert back to array, filter blank lines
recipeInstructions: instructionsField
  .split('\n')
  .map(s => s.trim())
  .filter(Boolean)
```

---

## Out of scope

- Migrating existing stored recipes to backfill `recipeInstructions` from `html_content` — old recipes fall back to the HTML parser, which is acceptable.
- Editing `html_content` directly — the edit form drops it (the structured `recipeInstructions` field replaces it for new recipes).
- `recipeYield` normalisation (unit variance across sources) — not blocking.
