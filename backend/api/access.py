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


def effective_role(cursor: Any, user_id: int, recipe_uuid: str) -> str:
    """The user's strongest role over a recipe: direct owner, else the best role
    across any cookbook that contains it and that the user can access."""
    row = cursor.execute("SELECT user_id FROM recipes WHERE uuid = ?", (recipe_uuid,)).fetchone()
    if row is None:
        return "none"
    if row["user_id"] == user_id:
        return "owner"

    rows = cursor.execute(
        "SELECT c.owner_id AS owner_id, m.role AS role, m.status AS status "
        "FROM cookbook_recipes cr "
        "JOIN cookbooks c ON c.id = cr.cookbook_id "
        "LEFT JOIN cookbook_members m ON m.cookbook_id = c.id AND m.user_id = ? "
        "WHERE cr.recipe_uuid = ?",
        (user_id, recipe_uuid),
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
    return best
