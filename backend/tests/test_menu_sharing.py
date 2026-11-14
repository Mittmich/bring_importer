"""Menu sharing: invitations, the viewer/editor/owner matrix, recipe read-through,
and revocation (remove, leave, unfriend, user delete)."""

import sqlite3
from unittest.mock import patch

import pytest
from passlib.context import CryptContext

from api import create_access_token
from api.prep_steps import PrepStepDraft

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
DRAFT = [PrepStepDraft(name="Bake", duration=40, lead=10)]


@pytest.fixture(autouse=True)
def drafted():
    with patch("api.routers.menus.draft_prep_steps", return_value=DRAFT) as mock:
        yield mock


def _mkuser(db, email):
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)", (email, _pwd.hash("pw"))
        )
        conn.commit()
        uid = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
    finally:
        conn.close()
    return uid, {"Authorization": f"Bearer {create_access_token(data={'sub': email})}"}


def _befriend(client, a_headers, b_email, b_headers):
    client.post("/friends/requests", headers=a_headers, json={"email": b_email})
    req = client.get("/friends/requests?direction=incoming", headers=b_headers).json()[0]["id"]
    client.post(f"/friends/requests/{req}/accept", headers=b_headers)


def _recipe(client, headers):
    resp = client.post("/recipes/parse", headers=headers, data={"image": "aGVsbG8="})
    assert resp.status_code == 200
    return resp.json()["uuid"]


def _invite(client, headers, mid, friend_id, role):
    return client.post(
        f"/menus/{mid}/members", headers=headers, json={"friend_id": friend_id, "role": role}
    )


@pytest.fixture
def shared(client, auth_headers, tmp_db_path, mocked_openai):
    """A's menu with one course (A's recipe), plus friend B who is invited but not
    yet accepted. Returns a factory: call it with the role to invite B at."""

    def make(role="viewer", accept=True):
        b_id, b = _mkuser(tmp_db_path, "b@example.com")
        _befriend(client, auth_headers, "b@example.com", b)
        r = _recipe(client, auth_headers)
        mid = client.post("/menus", headers=auth_headers, json={"title": "Dinner"}).json()["id"]
        menu = client.post(
            f"/menus/{mid}/courses", headers=auth_headers, json={"recipe_uuid": r}
        ).json()
        assert _invite(client, auth_headers, mid, b_id, role).status_code == 200
        if accept:
            assert client.post(f"/menus/invitations/{mid}/accept", headers=b).status_code == 200
        return {"mid": mid, "r": r, "b_id": b_id, "b": b, "menu": menu}

    return make


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


def test_invite_requires_friendship(client, auth_headers, tmp_db_path):
    stranger_id, _ = _mkuser(tmp_db_path, "s@example.com")
    mid = client.post("/menus", headers=auth_headers, json={"title": "Dinner"}).json()["id"]
    assert _invite(client, auth_headers, mid, stranger_id, "viewer").status_code == 403


def test_invite_rejects_bad_role_and_self(client, auth_headers, shared):
    s = shared(accept=False)
    assert _invite(client, auth_headers, s["mid"], s["b_id"], "manager").status_code == 422
    me = client.get(f"/menus/{s['mid']}", headers=auth_headers).json()["owner"]["user_id"]
    assert _invite(client, auth_headers, s["mid"], me, "viewer").status_code == 422


def test_pending_invite_grants_nothing(client, shared):
    s = shared(accept=False)
    b = s["b"]
    assert client.get(f"/menus/{s['mid']}", headers=b).status_code == 404
    assert client.get("/menus", headers=b).json() == []
    assert client.get(f"/recipes/{s['r']}.json", headers=b).status_code == 404
    invites = client.get("/menus/invitations", headers=b).json()
    assert [i["menu_id"] for i in invites] == [s["mid"]]
    assert invites[0]["owner"]["email"] == "test@example.com"


def test_decline_removes_invite(client, auth_headers, shared):
    s = shared(accept=False)
    assert client.post(f"/menus/invitations/{s['mid']}/decline", headers=s["b"]).status_code == 204
    assert client.get("/menus/invitations", headers=s["b"]).json() == []
    assert client.get(f"/menus/{s['mid']}/members", headers=auth_headers).json()["members"] == []
    # Nothing left to accept.
    resp = client.post(f"/menus/invitations/{s['mid']}/accept", headers=s["b"])
    assert resp.status_code == 404


def test_accept_lists_menu_with_role_and_owner(client, auth_headers, shared):
    s = shared("editor")
    listed = client.get("/menus", headers=s["b"]).json()
    assert [(m["id"], m["role"]) for m in listed] == [(s["mid"], "editor")]
    assert listed[0]["owner"]["email"] == "test@example.com"
    mine = client.get("/menus", headers=auth_headers).json()
    assert mine[0]["role"] == "owner" and mine[0]["member_count"] == 1


# ---------------------------------------------------------------------------
# Permission matrix
# ---------------------------------------------------------------------------


def _mutations(client, s, headers):
    """Status codes of every editor-level call on the shared menu."""
    mid = s["mid"]
    course = s["menu"]["courses"][0]["id"]
    step = s["menu"]["steps"][0]["id"]
    with patch("api.routers.menus.revise_plan", return_value=[]):
        return {
            "patch": client.patch(f"/menus/{mid}", headers=headers, json={"guests": 3}),
            "course": client.patch(
                f"/menus/{mid}/courses/{course}", headers=headers, json={"name": "Main"}
            ),
            "order": client.put(
                f"/menus/{mid}/courses/order", headers=headers, json={"course_ids": [course]}
            ),
            "step": client.patch(
                f"/menus/{mid}/steps/{step}", headers=headers, json={"done": True}
            ),
            "add_step": client.post(
                f"/menus/{mid}/steps",
                headers=headers,
                json={"course_id": course, "name": "Plate", "duration": 5},
            ),
            # Last: these replace the steps.
            "redraft": client.post(f"/menus/{mid}/courses/{course}/redraft", headers=headers),
            "revise": client.post(f"/menus/{mid}/revise", headers=headers, json={"request": "x"}),
        }


def test_viewer_reads_but_cannot_edit(client, shared):
    s = shared("viewer")
    b, mid = s["b"], s["mid"]
    menu = client.get(f"/menus/{mid}", headers=b).json()
    assert menu["role"] == "viewer" and len(menu["courses"]) == 1
    assert client.get(f"/menus/{mid}/plan.pdf", headers=b).status_code == 200
    with patch("api.routers.menus.merge_ingredients", return_value=[]):
        assert client.post(f"/menus/{mid}/shopping-list", headers=b).status_code == 200
    for name, resp in _mutations(client, s, b).items():
        assert resp.status_code == 404, name
    assert client.delete(f"/menus/{mid}", headers=b).status_code == 404


def test_editor_edits_but_cannot_delete_or_share(client, shared, tmp_db_path, auth_headers):
    s = shared("editor")
    b, mid = s["b"], s["mid"]
    for name, resp in _mutations(client, s, b).items():
        assert resp.status_code == 200, (name, resp.text)
    assert client.get(f"/menus/{mid}", headers=auth_headers).json()["guests"] == 3
    assert client.delete(f"/menus/{mid}", headers=b).status_code == 404
    c_id, _ = _mkuser(tmp_db_path, "c@example.com")
    assert _invite(client, b, mid, c_id, "viewer").status_code == 404
    resp = client.patch(f"/menus/{mid}/members/{s['b_id']}", headers=b, json={"role": "viewer"})
    assert resp.status_code == 404


def test_viewer_cannot_trigger_revise_ai(client, shared):
    s = shared("viewer")
    with patch("api.routers.menus.revise_plan") as revise:
        resp = client.post(f"/menus/{s['mid']}/revise", headers=s["b"], json={"request": "x"})
    assert resp.status_code == 404
    revise.assert_not_called()


def test_owner_changes_role(client, auth_headers, shared):
    s = shared("viewer")
    resp = client.patch(
        f"/menus/{s['mid']}/members/{s['b_id']}", headers=auth_headers, json={"role": "editor"}
    )
    assert resp.status_code == 200
    assert resp.json()["members"][0]["role"] == "editor"
    assert client.get(f"/menus/{s['mid']}", headers=s["b"]).json()["role"] == "editor"


# ---------------------------------------------------------------------------
# Recipes through the menu
# ---------------------------------------------------------------------------


def test_member_reads_course_recipe_but_cannot_edit(client, shared):
    s = shared("editor")
    b, r = s["b"], s["r"]
    assert client.get(f"/recipes/{r}.json", headers=b).status_code == 200
    resp = client.put(f"/recipes/{r}", headers=b, json={"recipe": {"name": "Hacked"}})
    assert resp.status_code == 404
    # Read-through is point access only: it doesn't fill B's recipe list.
    assert client.get("/recipes", headers=b).json()["total"] == 0


def test_menu_access_cannot_be_laundered_into_a_cookbook(client, shared):
    s = shared("viewer")
    cid = client.post("/cookbooks", headers=s["b"], json={"name": "Mine"}).json()["id"]
    resp = client.post(f"/cookbooks/{cid}/recipes", headers=s["b"], json={"recipe_uuid": s["r"]})
    assert resp.status_code == 404


def test_editor_added_recipe_is_readable_by_owner(client, auth_headers, shared):
    s = shared("editor")
    b_recipe = _recipe(client, s["b"])
    assert client.get(f"/recipes/{b_recipe}.json", headers=auth_headers).status_code == 404
    resp = client.post(f"/menus/{s['mid']}/courses", headers=s["b"], json={"recipe_uuid": b_recipe})
    assert resp.status_code == 200
    assert client.get(f"/recipes/{b_recipe}.json", headers=auth_headers).status_code == 200


def test_editor_cannot_add_recipe_they_cannot_read(client, shared, tmp_db_path):
    s = shared("editor")
    _, c = _mkuser(tmp_db_path, "c@example.com")
    c_recipe = _recipe(client, c)
    resp = client.post(f"/menus/{s['mid']}/courses", headers=s["b"], json={"recipe_uuid": c_recipe})
    assert resp.status_code == 404


def test_menu_does_not_pass_on_recipes_reached_via_cookbook(
    client, auth_headers, shared, tmp_db_path
):
    """A reads C's recipe through C's cookbook and puts it in a menu shared with B.
    C isn't on the menu, so B doesn't get C's recipe."""
    s = shared("viewer")
    c_id, c = _mkuser(tmp_db_path, "c@example.com")
    _befriend(client, c, "test@example.com", auth_headers)
    c_recipe = _recipe(client, c)
    cid = client.post("/cookbooks", headers=c, json={"name": "C's"}).json()["id"]
    client.post(f"/cookbooks/{cid}/recipes", headers=c, json={"recipe_uuid": c_recipe})
    a_id = client.get(f"/menus/{s['mid']}", headers=auth_headers).json()["owner"]["user_id"]
    client.post(f"/cookbooks/{cid}/members", headers=c, json={"friend_id": a_id, "role": "viewer"})
    client.post(f"/cookbooks/invitations/{cid}/accept", headers=auth_headers)
    resp = client.post(
        f"/menus/{s['mid']}/courses", headers=auth_headers, json={"recipe_uuid": c_recipe}
    )
    assert resp.status_code == 200
    assert client.get(f"/recipes/{c_recipe}.json", headers=s["b"]).status_code == 404


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------


def test_owner_removes_member(client, auth_headers, shared):
    s = shared("viewer")
    resp = client.delete(f"/menus/{s['mid']}/members/{s['b_id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert client.get(f"/menus/{s['mid']}", headers=s["b"]).status_code == 404
    assert client.get(f"/recipes/{s['r']}.json", headers=s["b"]).status_code == 404


def test_member_leaves(client, auth_headers, shared):
    s = shared("editor")
    resp = client.delete(f"/menus/{s['mid']}/members/{s['b_id']}", headers=s["b"])
    assert resp.status_code == 204
    assert client.get("/menus", headers=s["b"]).json() == []


def test_member_cannot_remove_others(client, auth_headers, shared, tmp_db_path):
    s = shared("editor")
    c_id, c = _mkuser(tmp_db_path, "c@example.com")
    _befriend(client, auth_headers, "c@example.com", c)
    _invite(client, auth_headers, s["mid"], c_id, "viewer")
    assert client.delete(f"/menus/{s['mid']}/members/{c_id}", headers=s["b"]).status_code == 404


def test_unfriend_revokes_menu_share(client, auth_headers, shared):
    s = shared("editor")
    assert client.delete(f"/friends/{s['b_id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/menus/{s['mid']}", headers=s["b"]).status_code == 404


def test_delete_menu_removes_members(client, auth_headers, shared, tmp_db_path):
    s = shared("viewer")
    assert client.delete(f"/menus/{s['mid']}", headers=auth_headers).status_code == 204
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM menu_members").fetchone()[0] == 0
    finally:
        conn.close()
