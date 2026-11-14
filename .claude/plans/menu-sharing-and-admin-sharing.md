---
name: menu-sharing-and-admin-sharing
status: done
created: 2026-11-14
updated: 2026-11-14
---

# Menu sharing + admin control over sharing and friendships

## Goal

1. Users can share a **menu** (title, courses, prep plan) with friends.
2. Admins can see and control **what is shared with whom** (menus and cookbooks/recipes)
   and **who is friends with whom**.

Builds on `friends-cookbooks-sharing` (friend graph, cookbook roles, `api/access.py`) and
`admin-control-plane` (`get_current_admin`, `/admin` page).

## Decisions (user, 2026-11-14)

- **Menu roles:** `viewer` / `editor`, using the same ladder as cookbooks.
  - viewer: sees the menu, prep plan, cook mode and PDF export.
  - editor: everything a viewer can do, plus edit title/date/guests, courses and steps, tick
    steps done, AI redraft/revise, and push the menu to their own Bring! list.
  - owner only: delete the menu and manage who it's shared with. There is no `manager`.
- **Recipes in a shared menu are readable through it.** Members can read the recipe behind
  each course, but not edit it, for as long as the share lasts.
- **Friendships:** users keep self-service requests. Admins can also see the whole friend
  graph, connect any two users directly, and remove any friendship.
- **Admin share control covers menus and cookbooks** (including quick-share recipes and
  "all my recipes"). Admins can list, change roles, revoke, and create shares for any user.

## Proposed defaults (flag in review if wrong)

- **User-initiated menu shares are invitations** (`pending` → accept/decline), the same as
  cookbooks. **Admin-created shares and friendships are `accepted` immediately**, because the
  admin is the authority.
- **Shares stay friends-only, including admin-created ones.** This keeps the existing rule that
  unfriending cuts every share between two people. The admin "create share" dialog has an
  "Also make them friends" checkbox that connects the pair in the same transaction.
- **Recipes added to a shared menu become visible to everyone on the menu.** If an editor adds
  one of their own recipes as a course, the owner and the other members can read it through
  the menu. The add-course dialog shows a one-line hint when the menu is shared.

## Design

### Schema (`init_db`, `CREATE TABLE IF NOT EXISTS`)

```sql
menu_members(
  menu_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('viewer','editor')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted')),
  invited_by INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  responded_at TIMESTAMP,
  PRIMARY KEY(menu_id, user_id)
)
-- index: menu_members(user_id, status)
```

### Access (`api/access.py`)

- `menu_role(cursor, user_id, menu_id)` returns `owner` / `editor` / `viewer` / `none`.
  Only accepted memberships count.
- `accessible_recipes_sql` gets a fifth clause: the recipe is a course of a menu the user owns
  or is an accepted member of. Today all ~15 callers hand-count four `?` user ids. Add
  `accessible_recipes_params(user_id)` and switch every caller to it, so the placeholder count
  lives in one place.
- `effective_role`: access through a menu grants at most `viewer`. Any cookbook role still
  wins if it is higher.

### Menus router (`api/routers/menus.py`)

- Replace `_owned_menu` with `_menu_for(cursor, menu_id, user_id, minimum)`. It returns the
  row and the user's role, and raises 404 below `minimum`, keeping the existing 404-not-403
  convention.
  - `viewer`: GET menu, `plan.pdf`.
  - `editor`: PATCH menu, all course, step, redraft and revise endpoints, and `shopping-list`
    (which pushes to the caller's own Bring! list, never the owner's).
  - `owner`: DELETE menu, member management.
- Adding a course still requires the **acting** user to have access to that recipe.
- The menu payload gains `role`, `owner {user_id, email, display_name}` and `member_count`.
- `GET /menus` returns my menus plus accepted shared ones, each with `role` and `owner`.
- Sharing endpoints, modelled on the cookbook ones:
  - `GET /menus/{id}/members` (owner)
  - `POST /menus/{id}/members {friend_id, role}` (owner, friends-only, creates `pending`)
  - `PATCH /menus/{id}/members/{user_id} {role}` (owner)
  - `DELETE /menus/{id}/members/{user_id}` (owner, or the member themselves to leave)
  - `GET /menus/invitations`, `POST /menus/invitations/{menu_id}/accept|decline`

### Shared revocation helper

- Move the "unfriend cuts every share" logic into `access.revoke_shares_between(cursor, a, b)`.
  It now covers `cookbook_members` **and** `menu_members`, in both directions.
- Used by `DELETE /friends/{id}` and by the admin friendship delete.
- `admin._delete_user_data` also deletes `menu_members` rows for owned menus and the user's
  own memberships, and nulls `invited_by`.

### Admin API (`api/routers/admin.py`, `get_current_admin`)

Friendships:

- `GET /admin/friendships?user_id=&status=` returns every pair (or one user's pairs) with
  both users' emails and display names, the status, and who requested.
- `POST /admin/friendships {user_a, user_b}` creates an accepted friendship, or upgrades a
  pending one. Self-pairs → 422; already friends → 409.
- `DELETE /admin/friendships/{id}` deletes the pair and calls `revoke_shares_between`.

Shares (one unified list):

- `GET /admin/shares?user_id=&type=menu|cookbook` returns rows like
  `{type, resource_id, resource_name, cookbook_kind?, owner{…}, grantee{…}, role, status, created_at}`.
  Quick-share cookbooks show the recipe title; `kind='all'` shows as "All recipes".
- `POST /admin/shares {type, resource_id, user_id, role, ensure_friends?}` creates an accepted
  share. Roles are validated per type (menu: viewer/editor; cookbook: viewer/editor/manager).
  It returns 409 when the two users aren't friends, unless `ensure_friends` is set. The owner
  can't be added as a grantee.
- `PATCH /admin/shares/{type}/{resource_id}/{user_id} {role}`
- `DELETE /admin/shares/{type}/{resource_id}/{user_id}`
- `GET /admin/users/{id}/resources?type=` returns that user's menus or cookbooks, for the
  picker in the create-share dialog.

### Frontend (`frontend-react/src`)

- **`lib/api.ts`:** types and calls for menu members and invitations, plus admin friendships
  and shares. `Menu` / `MenuSummary` gain `role`, `owner` and `member_count`.
- **MenuPage:**
  - a **Share** button for the owner opens `ShareMenuModal` (friend picker + role, current
    members with role change and remove, pending badge), reusing patterns from
    `CookbookMembersSection` / `ShareRecipeModal`.
  - Members who aren't the owner see a "Shared by …" chip and a **Leave** action.
  - Viewers get a read-only page: no edit inputs, add/remove/reorder, AI actions, step
    editor or done toggles.
- **CookModePage:** viewers can follow along. Ticking steps done requires editor.
- **MenusPage:** a "Shared with me" section with owner and role badges, plus pending
  invitations with accept/decline. `useNotifications` counts menu invitations in its badge.
- **AdminPage:**
  - **Friends tab:** searchable list of pairs (user ↔ user, status, since), a "Connect two
    users" dialog with two user pickers, and remove with a confirm that warns all shares
    between them are revoked.
  - **Sharing tab:** filter by user and type, rows like owner → grantee · resource · role ·
    status, an inline role select, revoke, and a "New share" dialog (owner → resource picker
    → grantee → role → "Also make them friends").
- **i18n:** all new strings in en and de.

## Changes while building (2026-11-14)

- **Menu read-through is point access, not browse.** `accessible_recipes_sql` (the recipe list
  and tag filter) is unchanged. Menus only add to `effective_role`, so shared menus don't fill
  people's recipe lists. No params helper was needed.
- **A menu passes on a recipe only when its owner is on that menu** (as owner or accepted
  member). If someone puts a recipe they only reach through another person's cookbook into a
  shared menu, the menu's members don't get it.
- **Menu access can't be copied into a cookbook.** Adding a recipe to a cookbook uses
  `effective_role(..., via_menus=False)`.
- **Viewers can build a shopping list.** It goes to their own Bring! list, so it needs only
  `viewer`, not `editor`.

## Steps

- [x] 1. Schema: `menu_members` + index; `_delete_user_data` cascade
- [x] 2. `access.py`: `menu_role`, menu clause in `accessible_recipes_sql`,
       `accessible_recipes_params` (migrate all callers), `effective_role` menu grant,
       `revoke_shares_between` (used by unfriend)
- [x] 3. Menus router: role-based `_menu_for` on every endpoint, list shared menus,
       payload `role`/`owner`, member + invitation endpoints
- [x] 4. Backend tests `tests/test_menu_sharing.py`: invite lifecycle, friends-only,
       viewer/editor/owner matrix on every menu endpoint, recipe read-through (and no edit),
       revoke/leave/unfriend cut access immediately, user delete cascade
- [x] 5. Admin API: friendships list/create/delete, shares list/create/patch/delete,
       user resources; tests in `tests/test_admin.py` (non-admin 403, ensure_friends,
       role validation, revoke cascade)
- [x] 6. Frontend: api types; MenuPage share modal + role-aware read-only mode; CookModePage;
       MenusPage shared section + invitations; notifications badge
- [x] 7. Frontend: AdminPage Friends + Sharing tabs and dialogs
- [x] 8. i18n en/de; ruff/black/isort, `ty check` baseline, pytest, tsc + vite build, eslint
       vs. main baseline; browser check with two users (share, accept, viewer read-only,
       editor edits, admin revoke → access gone)

## Deferred

- An audit log of admin actions on shares and friendships.
- Live updates while two people edit a menu at once. A later save wins, the same as recipes
  today; an `updated_at` guard can come later.
- A global switch to turn off self-service friend requests (the friendships decision didn't
  ask for it).

## Outcome

- **Backend:**
  - New `menu_members` table.
  - `access.menu_role` and menu read-through in `effective_role` (viewer only; the recipe's
    owner must be on the menu; `via_menus=False` for adding recipes to cookbooks).
  - `revoke_shares_between` is used by unfriend and by the admin friendship delete.
  - Menus router: role checks on every endpoint, shared menus in `GET /menus`, `role`/`owner`/
    `member_count` in the payload, member and invitation endpoints.
  - Admin: friendships list/create/delete, shares list/create/patch/delete across menus and
    cookbooks, user resources.
  - User delete also removes menu shares.
- **Tests:** 436 backend tests pass (19 new in `tests/test_menu_sharing.py`, 9 new in
  `tests/test_admin.py`). ruff/black/isort are clean and `ty` matches main (7).
- **Frontend:**
  - `ShareMenuDialog` (owner).
  - Viewers get a read-only MenuPage, timeline, run sheet, step editor and cook mode.
  - Members see a "Shared by …" chip and a Leave action.
  - MenusPage gets "Shared with me" and invitations; the plan nav item shows a badge for menu
    invitations.
  - AdminPage gets Friends and Sharing tabs (`components/admin/SharingTabs.tsx`).
  - en and de strings.
  - tsc and vite build pass; eslint has no errors in touched files (17 overall, same as main).
- **Verified** end to end over HTTP against a throwaway server (19 checks): invite → pending
  has no access → accept; viewer reads menu, recipe and PDF but can't edit; admin promotes to
  editor and the edit works; admin share returns 409 without friendship, and `ensure_friends`
  creates it; admin removing the friendship cuts access; non-admin gets 403.
- **Not verified:** a visual check in a browser, because no browser tool was available.
- **Unrelated finding:** `RECIPE_TEST_MOCKS=1` crashes at import (`openai` subclasses a patched
  `httpx.AsyncClient`).
