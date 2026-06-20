---
name: recipe-sharing
status: done
---

# Recipe Sharing via Public Link

## Goal

Allow a user to make a recipe public via a toggle, then share it via a link. Anyone with the link can view the recipe. A logged-in user can clone (save) it to their own collection via `POST /recipes/{uuid}/clone`.

---

## What is already done

### Backend — fully implemented

**`backend/api/db.py`**
- `is_public INTEGER NOT NULL DEFAULT 0` column added to `recipes` table via in-place migration in `init_db()`.

**`backend/api/models.py`**
- `RecipeUpdate.is_public: Optional[bool] = None` field added — the PUT body can now flip the flag.

**`backend/api/auth.py`**
- `get_current_user_optional` dependency added — returns `None` instead of raising 401, used by endpoints that serve both authenticated and anonymous users.

**`backend/api/routers/recipes.py`**
- `GET /recipes/{uuid}.json` — uses optional auth. Public recipes are world-readable; private ones 404 for non-owners.
- `PUT /recipes/{uuid}` — persists `is_public` from the request body; returns `is_public` in the response blob.
- `GET /recipes` (list) — returns `is_public: bool` per recipe item.
- `POST /recipes/{uuid}/clone` — new endpoint. Auth required. Clones a public recipe (new UUID, caller's `user_id`). Returns 404 if recipe is missing or private.

**`backend/tests/test_recipes.py`**
- `test_get_recipe_json_private_recipe_returns_404_for_unauthenticated` — private recipe blocks unauthenticated access.
- `test_get_recipe_json_public_recipe_accessible_without_auth` — public recipe is readable by anyone.
- `test_get_recipe_json_returns_stored_payload` — now asserts `is_public: false` in the JSON response.

---

## What still needs to be done — ✅ ALL DONE

### ✅ 1. Frontend type & API layer (`frontend-react/src/lib/api.ts`)

- Add `is_public?: boolean` to `RecipeListItem` interface.
- Add `is_public?: boolean` to `Recipe` interface.
- Add `is_public?: boolean` to `RecipeUpdate` interface.
- Add `cloneRecipe(uuid: string)` method → `POST /recipes/{uuid}/clone`, returns `{ uuid: string; url: string }`.

### ✅ 2. Public toggle in Edit page (`frontend-react/src/pages/EditRecipePage.tsx`)

Add a "Sharing" section at the bottom of the edit form (below the Note section):

- Local state `isPublic: boolean` initialized from `recipe.is_public ?? false`.
- A toggle switch (or checkbox styled as a toggle) with label "Make recipe public".
- When toggled on, show a subtle hint: "Anyone with the link can view this recipe."
- Include `is_public: isPublic` in the `updateRecipe` call inside `saveMutation`.

> **UX note:** The share link is surfaced after saving (on the detail/recipe view), not inline in the edit form, to keep the edit flow simple.

### ✅ 3. Share button on RecipeDetail (`frontend-react/src/components/RecipeDetail.tsx`)

- The detail view receives the recipe data which now includes `is_public`.
- When `is_public === true`, show a "Share" button (e.g., `Share2` icon from lucide-react) in the header action area.
- Clicking "Share" copies `window.location.origin + /recipes/{uuid}` to the clipboard and shows a brief "Link copied!" toast/confirmation (inline state, no toast library needed — a transient `copied` state that resets after 2 s is sufficient).

### ✅ 4. Public recipe page (new route `/share/:uuid`)

This is the page a recipient sees when they open a shared link. It must work for:
- Anonymous visitors (no token)
- Logged-in users who don't own the recipe
- The owner (show a different CTA)

**New file: `frontend-react/src/pages/PublicRecipePage.tsx`** ← created

Behavior:
- Calls `api.getRecipe(uuid)` (which hits `GET /recipes/{uuid}.json` — no auth header needed if the token is absent, returns 404 for private).
- Shows a read-only recipe view: title, description, yield, ingredient list, instruction steps.
- If the viewer is **logged in and not the owner**: show a "Save to my collection" button → calls `api.cloneRecipe(uuid)` → on success, navigate to the cloned recipe detail (`/recipes/{newUuid}`).
- If the viewer is **not logged in**: show "Log in to save this recipe" button → navigates to `/login`.
- If the viewer **is the owner**: show "Edit" button → navigates to `/recipes/{uuid}/edit`.
- On 404 (private or missing): show "Recipe not found or not shared" message.

> The owner check: compare `recipe.source` or, better, maintain a lightweight `isOwner` flag. Since the JSON endpoint doesn't return the owning user's email, the simplest approach is: after fetching the recipe, also call `api.listRecipes()` (already cached in React Query) and check if the uuid appears in the list. If yes → owner.

**Routing (`frontend-react/src/App.tsx`):**
- Added route `path="/share/:uuid"` → `<PublicRecipePage />` (top-level, no auth guard).
- Share links use `/share/{uuid}` (not `/recipes/:uuid`) to avoid conflict with the guarded owner detail view.
- Existing `/recipes/:uuid/edit` route is already guarded and remains unchanged.

### ✅ 5. Missing backend test: clone endpoint

Added to `backend/tests/test_recipes.py` (all 25 tests pass):
- `test_clone_public_recipe_creates_new_recipe` — clone succeeds, returns new uuid, new recipe appears in cloner's list.
- `test_clone_private_recipe_returns_404` — cloning a private recipe returns 404.
- `test_clone_nonexistent_recipe_returns_404` — missing uuid returns 404.
- Fixed `test_delete_recipe_then_public_endpoints_404` — pre-deletion check now uses auth headers (private recipe was incorrectly expected to be public).

---

## Out of scope

- No public recipe listing / discovery page.
- No share-by-email flow.
- No expiry on public links.
- No public access to `.html` endpoint gating (it remains ungated, used only by Bring deeplink).
