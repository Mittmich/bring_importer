"""Access resolution for shared recipes and cookbooks (Phase 3).

Every recipe endpoint routes its permission check through ``effective_role``
instead of the bare ``recipes.user_id == me`` check, so shared access is honored
uniformly. Roles form a ladder; ``role_at_least`` compares them.

- ``owner``   — the recipe's owner (recipes.user_id) / the cookbook's owner.
- ``manager`` — can curate a cookbook (add/remove recipes), rename it, and manage
                its members. Over a *recipe* reached via a cookbook, manager can
                edit it but cannot destroy it (only the recipe owner can).
- ``editor``  — can edit recipe content; cannot curate cookbooks.
- ``viewer``  — read only.

Menus (``menu_members``) have their own small ladder — owner / editor / viewer —
and grant ``viewer`` over the recipes in their courses (``_menu_grants_recipe``).
"""

from typing import Any

ROLE_ORDER = {"none": 0, "viewer": 1, "editor": 2, "manager": 3, "owner": 4}


def role_rank(role: str) -> int:
    return ROLE_ORDER.get(role, 0)


def role_at_least(role: str, minimum: str) -> bool:
    return role_rank(role) >= role_rank(minimum)


def cookbook_role(cursor: Any, user_id: int, cookbook_id: int) -> str:
    """The user's role on a cookbook: owner / manager / editor / viewer / none.

    Only ``accepted`` memberships count; a pending invitation grants nothing.
    """
    row = cursor.execute("SELECT owner_id FROM cookbooks WHERE id = ?", (cookbook_id,)).fetchone()
    if row is None:
        return "none"
    if row["owner_id"] == user_id:
        return "owner"
    m = cursor.execute(
        "SELECT role FROM cookbook_members "
        "WHERE cookbook_id = ? AND user_id = ? AND status = 'accepted'",
        (cookbook_id, user_id),
    ).fetchone()
    return m["role"] if m else "none"


def accessible_recipes_sql(alias: str = "r") -> str:
    """A SQL boolean for "recipes the user can access", with **4** ``?``
    placeholders that all take the user's id. The recipe is accessible if:
      - they own it,
      - it's in a cookbook they own or are an accepted member of, or
      - its owner shared an auto ``kind='all'`` cookbook with them.
    """
    return (
        f"({alias}.user_id = ? "
        f"OR {alias}.uuid IN ("
        "SELECT cr.recipe_uuid FROM cookbook_recipes cr "
        "JOIN cookbooks c ON c.id = cr.cookbook_id "
        "LEFT JOIN cookbook_members m ON m.cookbook_id = c.id AND m.user_id = ? "
        "AND m.status = 'accepted' WHERE c.owner_id = ? OR m.user_id IS NOT NULL) "
        f"OR {alias}.user_id IN ("
        "SELECT c2.owner_id FROM cookbooks c2 "
        "JOIN cookbook_members m2 ON m2.cookbook_id = c2.id "
        "AND m2.user_id = ? AND m2.status = 'accepted' WHERE c2.kind = 'all'))"
    )


MENU_ROLES = ("viewer", "editor")


def menu_role(cursor: Any, user_id: int, menu_id: int) -> str:
    """The user's role on a menu: owner / editor / viewer / none.

    Only ``accepted`` memberships count; a pending invitation grants nothing.
    """
    row = cursor.execute("SELECT user_id FROM menus WHERE id = ?", (menu_id,)).fetchone()
    if row is None:
        return "none"
    if row["user_id"] == user_id:
        return "owner"
    m = cursor.execute(
        "SELECT role FROM menu_members WHERE menu_id = ? AND user_id = ? AND status = 'accepted'",
        (menu_id, user_id),
    ).fetchone()
    return m["role"] if m else "none"


def _menu_grants_recipe(cursor: Any, user_id: int, recipe_uuid: str, owner_id: int) -> bool:
    """Whether a shared menu lets ``user_id`` read the recipe.

    True when the recipe is a course of a menu where **both** the user and the
    recipe's owner take part (owner or accepted member). Requiring the recipe's
    owner to be on the menu means a menu can't pass on recipes its people only
    reached through someone else's cookbook.
    """
    participants = (
        "SELECT id FROM menus WHERE user_id = ? "
        "UNION SELECT menu_id FROM menu_members WHERE user_id = ? AND status = 'accepted'"
    )
    row = cursor.execute(
        "SELECT 1 FROM menu_courses WHERE recipe_uuid = ? "
        f"AND menu_id IN ({participants}) AND menu_id IN ({participants}) LIMIT 1",
        (recipe_uuid, user_id, user_id, owner_id, owner_id),
    ).fetchone()
    return row is not None


def effective_role(cursor: Any, user_id: int, recipe_uuid: str, via_menus: bool = True) -> str:
    """The user's strongest role over a recipe: direct owner, else the best role
    across any cookbook that grants access (one that contains it, or an auto
    ``kind='all'`` cookbook owned by the recipe's owner), else ``viewer`` if a
    shared menu grants it (see ``_menu_grants_recipe``).

    Pass ``via_menus=False`` where menu access must not count — e.g. adding a
    recipe to a cookbook, which would otherwise turn a menu's read access into a
    lasting, re-shareable one.
    """
    row = cursor.execute("SELECT user_id FROM recipes WHERE uuid = ?", (recipe_uuid,)).fetchone()
    if row is None:
        return "none"
    owner_id = row["user_id"]
    if owner_id == user_id:
        return "owner"

    rows = cursor.execute(
        "SELECT c.owner_id AS owner_id, m.role AS role, m.status AS status "
        "FROM cookbook_recipes cr "
        "JOIN cookbooks c ON c.id = cr.cookbook_id "
        "LEFT JOIN cookbook_members m ON m.cookbook_id = c.id AND m.user_id = ? "
        "WHERE cr.recipe_uuid = ?",
        (user_id, recipe_uuid),
    ).fetchall()

    # Auto 'all' cookbooks owned by the recipe's owner grant their role over
    # every recipe that owner has.
    rows += cursor.execute(
        "SELECT c.owner_id AS owner_id, m.role AS role, m.status AS status "
        "FROM cookbooks c LEFT JOIN cookbook_members m "
        "ON m.cookbook_id = c.id AND m.user_id = ? "
        "WHERE c.kind = 'all' AND c.owner_id = ?",
        (user_id, owner_id),
    ).fetchall()

    best = "none"
    for r in rows:
        if r["owner_id"] == user_id:
            cand = "manager"  # owns the cookbook holding another user's recipe
        elif r["role"] and r["status"] == "accepted":
            cand = r["role"]
        else:
            cand = "none"
        if role_rank(cand) > role_rank(best):
            best = cand
    if best == "none" and via_menus and _menu_grants_recipe(cursor, user_id, recipe_uuid, owner_id):
        best = "viewer"
    return best


def revoke_shares_between(cursor: Any, a: int, b: int) -> None:
    """Remove every cookbook and menu share between two users, both directions."""
    cursor.execute(
        "DELETE FROM cookbook_members WHERE "
        "(user_id = ? AND cookbook_id IN (SELECT id FROM cookbooks WHERE owner_id = ?)) OR "
        "(user_id = ? AND cookbook_id IN (SELECT id FROM cookbooks WHERE owner_id = ?))",
        (b, a, a, b),
    )
    cursor.execute(
        "DELETE FROM menu_members WHERE "
        "(user_id = ? AND menu_id IN (SELECT id FROM menus WHERE user_id = ?)) OR "
        "(user_id = ? AND menu_id IN (SELECT id FROM menus WHERE user_id = ?))",
        (b, a, a, b),
    )


def are_friends(cursor: Any, a: int, b: int) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM friendships WHERE status = 'accepted' AND "
        "((requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?))",
        (a, b, b, a),
    ).fetchone()
    return row is not None
