---
name: friends-cookbooks-sharing
status: active
---

# Multi-user Sharing: Friends + Cookbooks

## Goal

Let users share recipes with each other — single recipes or whole collections
— at three permission levels (read / write / delete), gated behind a friend
relationship. Chosen shape (decided 2026-07-11):

- **Folder model (Option B):** the unit of sharing is a **cookbook** (a named
  collection of recipes). Sharing a single recipe wraps it in a lightweight
  "quick-share" cookbook, so there is exactly **one** sharing primitive.
- **Safe delete:** the highest shared role (`manager`) can remove a recipe
  *from a shared cookbook* and manage members, but **only the recipe's owner**
  can permanently destroy the recipe. Destructive delete is never delegated.
- **Friends only:** you can only invite people you're already friends with.
- **Live, not copies:** a shared recipe is the owner's single row; grantees act
  on the same recipe (contrast the existing `clone`, which makes a private copy).

Roles map to the requested read/write/delete ladder:

| Role      | Can…                                                                                  |
|-----------|----------------------------------------------------------------------------------------|
| `viewer`  | read recipes in the cookbook                                                            |
| `editor`  | + edit recipe content (fields, image) of recipes already in the cookbook                |
| `manager` | + add/remove recipes, rename the cookbook, invite/change/remove members                  |
| owner     | (implicit) everything, incl. permanently deleting the underlying recipe / the cookbook   |

Only the owner and managers **curate** a cookbook's contents; editors edit
recipe content but cannot add or remove recipes.

---

## Data model

All tables created idempotently in `init_db()` (guarded `CREATE TABLE IF NOT
EXISTS` + `PRAGMA table_info` for later column adds), matching the existing
schema-bootstrap style.

```sql
-- Social graph. One canonical row per pair; query both directions.
friendships(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  requester_id INTEGER NOT NULL,
  addressee_id INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','accepted','blocked')),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  responded_at TIMESTAMP,
  UNIQUE(requester_id, addressee_id)
)

cookbooks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'normal',   -- 'normal' | 'quickshare'
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(owner_id) REFERENCES users(id)
)

cookbook_recipes(
  cookbook_id INTEGER NOT NULL,
  recipe_uuid TEXT NOT NULL,
  added_by INTEGER,
  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(cookbook_id, recipe_uuid)
)

-- Grantees only. The cookbook owner is implicit (cookbooks.owner_id), never a row here.
cookbook_members(
  cookbook_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('viewer','editor','manager')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted')),
  invited_by INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  responded_at TIMESTAMP,
  PRIMARY KEY(cookbook_id, user_id)
)
```

Indexes: `cookbook_recipes(recipe_uuid)`, `cookbook_members(user_id, status)`,
`friendships(addressee_id, status)` for the hot lookups below.

---

## Permission resolution — the core primitive

A new module `api/access.py` owns one function every recipe endpoint routes
through instead of the current bare `row.user_id == me` check:

```
ROLE_ORDER = {none:0, viewer:1, editor:2, manager:3, owner:4}

effective_role(user_id, recipe_uuid) -> str:
  if recipe.owner (recipes.user_id) == user_id:  return 'owner'
  best = 'none'
  for each cookbook c that contains recipe_uuid AND user_id can access c:
     # owner of the cookbook acts as 'manager' over its contents;
     # an accepted member contributes their own role
     r = 'manager' if c.owner_id == user_id else member_role(c, user_id)   # accepted only
     best = max(best, r)                                                    # by ROLE_ORDER
  return best
```

Rules that fall out of this:
- **Read** a recipe: `effective_role >= viewer` **or** `recipes.is_public` (public
  link path unchanged).
- **Edit** (`PUT /recipes/{uuid}`, image PUT/DELETE): `effective_role >= editor`.
- **Add / remove a recipe in a cookbook** (`POST`/`DELETE /cookbooks/{id}/recipes`):
  `manager` on that cookbook (or owner). Editors cannot curate contents.
- **Permanently delete** (`DELETE /recipes/{uuid}`): recipe **owner only**.
- Keep the existing **404-not-403** convention everywhere so UUIDs/membership
  don't leak.

`member_role` only counts `status='accepted'` rows — a pending invite grants
nothing until accepted.

---

## Single-recipe sharing (sugar over the one primitive)

`POST /recipes/{uuid}/share {friend_id, role}`:
1. Assert requester owns (or manages) the recipe and `friend_id` is an accepted friend.
2. Find-or-create a `kind='quickshare'` cookbook owned by the requester, named
   after the recipe; ensure the recipe is in it.
3. Upsert `cookbook_members(friend_id, role, status='pending')`.

The frontend flattens single-recipe (`kind='quickshare'`) cookbooks into a
"Shared with me / Shared by me" recipe list, so the user never has to think
about the wrapper.

---

## API surface

**Friends**
- `POST /friends/requests {email}` — create a request (404/422 if no such user; no-op/409 if already friends or pending).
- `GET /friends` — accepted friends (id, email/display).
- `GET /friends/requests?direction=incoming|outgoing` — pending.
- `POST /friends/requests/{id}/accept` · `/decline`.
- `DELETE /friends/{user_id}` — unfriend; **auto-revokes** every cookbook membership between the two users, in both directions, so unfriending is a clean cutoff.

**Cookbooks**
- `POST /cookbooks {name}` · `GET /cookbooks` (mine + accepted-shared, each with my `role`) · `GET /cookbooks/{id}` (recipes + members) · `PATCH /cookbooks/{id} {name}` (manager+) · `DELETE /cookbooks/{id}` (owner).
- `POST /cookbooks/{id}/recipes {recipe_uuid}` (manager+; requester must have ≥viewer on the recipe being added) · `DELETE /cookbooks/{id}/recipes/{uuid}` (manager+).
- `POST /cookbooks/{id}/members {friend_id, role}` (manager+, friend-gated → pending) · `PATCH /cookbooks/{id}/members/{user_id} {role}` (manager+) · `DELETE /cookbooks/{id}/members/{user_id}` (manager+, or self to leave).
- `GET /cookbooks/invitations` (my pending) · `POST /cookbooks/invitations/{id}/accept|decline`.

**Recipe sugar**
- `POST /recipes/{uuid}/share {friend_id, role}` (quick-share, above).

**Changed existing endpoints** (route through `effective_role`)
- `GET /recipes/{uuid}.json`, `GET /recipes/{uuid}/image` — allow public **or** ≥viewer.
- `GET /recipes` — add `?scope=mine|shared|all` (default `mine` to preserve current behavior); `shared`/`all` union in recipes reachable via accepted shared cookbooks.
- `PUT /recipes/{uuid}`, image PUT/DELETE — require ≥editor.
- `DELETE /recipes/{uuid}` — owner only (unchanged in effect, but now explicitly "owner", not "any accessor").
- Meal plan — allow adding a recipe you have ≥viewer on; ensure the title lookup for plan entries works for recipes you don't own.

---

## Frontend

- **Friends** screen under Account: add by email, incoming/outgoing requests with accept/decline, friends list, unfriend.
- **Cookbooks**: a new section (bottom-nav / sidebar entry). List of my cookbooks + "Shared with me"; cookbook detail = recipe grid + member list + role controls; "Add recipe to cookbook" from a recipe.
- **Share affordance** on `RecipeDetail`: "Share" → pick a friend + role (quick-share) or "Add to a shared cookbook".
- **Shared-with-me** surfaced as a shelf on the (new tag-shelves) home and a filter in the list.
- **Badges** for pending friend requests + cookbook invitations.
- API/types in `lib/api.ts`; reuse `useRecipeImage`, tag chips, etc.

---

## Phased delivery

Each phase is independently shippable through the usual branch → CI → PR → deploy flow.

1. **Friends.** `friendships` table + endpoints + Friends UI. No sharing yet.
2. **Cookbooks (personal).** `cookbooks` + `cookbook_recipes` + CRUD + add/remove
   + cookbook UI. Useful on its own (organize your own recipes), no sharing yet.
3. **Share cookbooks with friends.** `cookbook_members`, invitations,
   `api/access.py` + rewire recipe endpoints to `effective_role`, "shared with
   me", single-recipe quick-share. This is the big one.
4. **Polish.** Notifications inbox + badges, member/role management UI, and an
   optimistic-concurrency guard on `PUT /recipes/{uuid}` (version/`updated_at`
   check → 409) now that multiple people can edit one recipe.

---

## Testing (per phase)

- Friend request lifecycle (send/accept/decline/duplicate/self); friends-only enforcement on invites.
- Cookbook CRUD + membership; add/remove recipes; rename/delete authorization.
- **Permission matrix**: viewer can't edit; editor edits content but can't add/remove cookbook recipes or destroy; manager can add/remove/manage but can't destroy the owner's recipe; owner can destroy.
- Access isolation: non-member gets 404 on a private shared recipe/cookbook; revoking a member cuts access immediately.
- **Unfriend revokes** all shares between the two users in both directions; each loses access immediately.
- `scope=shared|all` listing correctness; quick-share round-trip.
- Preserve existing behavior when `scope` is omitted.

---

## Deferred / out of scope (candidate follow-ups)

- **Per-user tags on shared recipes** — tags stay per-user; on a shared recipe you
  see the owner's tags read-only. Your own tagging of others' recipes is a follow-up.
- **Groups/teams** as a grantee type (the schema leaves room, but not built now).
- **Email invite to non-users** (we chose friends-only; would need a pending-invite-by-email flow).
- **Real-time collaboration / presence.** Phase 4's version check prevents silent clobbers; live cursors are out of scope.
- **Activity feed / notifications beyond in-app badges.**

## Resolved decisions (2026-07-11)

- **Unfriend auto-revokes** every share between the two users, in both directions.
- **Editors cannot add recipes** to a cookbook — only the owner and managers curate
  contents; editors only edit the content of recipes already in it.
- **Identity is email only** — no display-name/username field on `users`; the friends
  and share UI shows email.
