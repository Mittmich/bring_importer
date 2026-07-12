"""Integration tests for cookbook sharing (Phase 3): membership lifecycle,
the permission matrix (viewer/editor/manager/owner), isolation, quick-share,
and unfriend revocation."""

import sqlite3

import pytest
from passlib.context import CryptContext

from api import create_access_token

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _mkuser(tmp_db_path, email):
    conn = sqlite3.connect(str(tmp_db_path))
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
    return client.post("/recipes/parse", headers=headers, data={"image": "aGVsbG8="}).json()["uuid"]


def _cookbook(client, headers, name="Shared"):
    return client.post("/cookbooks", headers=headers, json={"name": name}).json()["id"]


def _share(client, owner_headers, cid, friend_id, role):
    return client.post(
        f"/cookbooks/{cid}/members",
        headers=owner_headers,
        json={"friend_id": friend_id, "role": role},
    )


def _shared_cookbook(client, auth_headers, tmp_db_path, role, mocked_openai):
    """A owns a cookbook with one recipe, shared with an accepted friend B at ``role``.
    Returns (cid, recipe_uuid, b_id, b_headers)."""
    b_id, b_headers = _mkuser(tmp_db_path, "b@example.com")
    _befriend(client, auth_headers, "b@example.com", b_headers)
    cid = _cookbook(client, auth_headers)
    r = _recipe(client, auth_headers)
    client.post(f"/cookbooks/{cid}/recipes", headers=auth_headers, json={"recipe_uuid": r})
    assert _share(client, auth_headers, cid, b_id, role).status_code == 200
    client.post(f"/cookbooks/invitations/{cid}/accept", headers=b_headers)
    return cid, r, b_id, b_headers


# ---------------------------------------------------------------------------
# invitation lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_invite_requires_friendship(client, auth_headers, tmp_db_path, mocked_openai):
    stranger_id, _ = _mkuser(tmp_db_path, "stranger@example.com")
    cid = _cookbook(client, auth_headers)
    assert _share(client, auth_headers, cid, stranger_id, "viewer").status_code == 403


@pytest.mark.integration
def test_invite_accept_grants_access(client, auth_headers, tmp_db_path, mocked_openai):
    cid, r, b_id, b_headers = _shared_cookbook(
        client, auth_headers, tmp_db_path, "viewer", mocked_openai
    )
    # Appears in B's cookbook list as shared, and is readable.
    books = {c["id"]: c for c in client.get("/cookbooks", headers=b_headers).json()}
    assert books[cid]["shared"] is True and books[cid]["role"] == "viewer"
    detail = client.get(f"/cookbooks/{cid}", headers=b_headers).json()
    assert detail["role"] == "viewer" and [i["uuid"] for i in detail["recipes"]] == [r]
    assert client.get(f"/recipes/{r}.json", headers=b_headers).status_code == 200


@pytest.mark.integration
def test_decline_invitation_no_access(client, auth_headers, tmp_db_path, mocked_openai):
    b_id, b_headers = _mkuser(tmp_db_path, "b@example.com")
    _befriend(client, auth_headers, "b@example.com", b_headers)
    cid = _cookbook(client, auth_headers)
    r = _recipe(client, auth_headers)
    client.post(f"/cookbooks/{cid}/recipes", headers=auth_headers, json={"recipe_uuid": r})
    _share(client, auth_headers, cid, b_id, "viewer")

    assert (
        client.post(f"/cookbooks/invitations/{cid}/decline", headers=b_headers).status_code == 204
    )
    assert client.get(f"/cookbooks/{cid}", headers=b_headers).status_code == 404
    assert client.get(f"/recipes/{r}.json", headers=b_headers).status_code == 404


@pytest.mark.integration
def test_pending_member_has_no_access(client, auth_headers, tmp_db_path, mocked_openai):
    b_id, b_headers = _mkuser(tmp_db_path, "b@example.com")
    _befriend(client, auth_headers, "b@example.com", b_headers)
    cid = _cookbook(client, auth_headers)
    _share(client, auth_headers, cid, b_id, "editor")
    # Not accepted yet → no access.
    assert client.get(f"/cookbooks/{cid}", headers=b_headers).status_code == 404


# ---------------------------------------------------------------------------
# permission matrix
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_viewer_cannot_edit_or_curate(client, auth_headers, tmp_db_path, mocked_openai):
    cid, r, b_id, b_headers = _shared_cookbook(
        client, auth_headers, tmp_db_path, "viewer", mocked_openai
    )
    assert client.put(f"/recipes/{r}", headers=b_headers, json={"title": "Hax"}).status_code == 404
    assert client.delete(f"/cookbooks/{cid}/recipes/{r}", headers=b_headers).status_code == 404
    other = _recipe(client, b_headers)
    assert (
        client.post(
            f"/cookbooks/{cid}/recipes", headers=b_headers, json={"recipe_uuid": other}
        ).status_code
        == 404
    )


@pytest.mark.integration
def test_editor_can_edit_but_not_curate_or_destroy(
    client, auth_headers, tmp_db_path, mocked_openai
):
    cid, r, b_id, b_headers = _shared_cookbook(
        client, auth_headers, tmp_db_path, "editor", mocked_openai
    )
    # Can edit content.
    assert (
        client.put(f"/recipes/{r}", headers=b_headers, json={"title": "Edited"}).status_code == 200
    )
    assert client.get(f"/recipes/{r}.json", headers=b_headers).json()["name"] == "Edited"
    # Cannot remove from cookbook, nor destroy the recipe.
    assert client.delete(f"/cookbooks/{cid}/recipes/{r}", headers=b_headers).status_code == 404
    assert client.delete(f"/recipes/{r}", headers=b_headers).status_code == 404


@pytest.mark.integration
def test_editor_cannot_change_owner_only_fields(client, auth_headers, tmp_db_path, mocked_openai):
    cid, r, b_id, b_headers = _shared_cookbook(
        client, auth_headers, tmp_db_path, "editor", mocked_openai
    )
    client.put(f"/recipes/{r}", headers=b_headers, json={"is_public": True, "tags": ["x"]})
    data = client.get(f"/recipes/{r}.json", headers=auth_headers).json()
    assert data["is_public"] is False
    assert data["tags"] == []


@pytest.mark.integration
def test_manager_can_curate_but_not_delete_cookbook_or_recipe(
    client, auth_headers, tmp_db_path, mocked_openai
):
    cid, r, b_id, b_headers = _shared_cookbook(
        client, auth_headers, tmp_db_path, "manager", mocked_openai
    )
    # Manager can remove a recipe from the cookbook and rename it.
    assert client.delete(f"/cookbooks/{cid}/recipes/{r}", headers=b_headers).status_code == 204
    assert (
        client.patch(f"/cookbooks/{cid}", headers=b_headers, json={"name": "Renamed"}).status_code
        == 200
    )
    # But cannot delete the cookbook (owner only) nor destroy the owner's recipe.
    assert client.delete(f"/cookbooks/{cid}", headers=b_headers).status_code == 404
    assert client.delete(f"/recipes/{r}", headers=b_headers).status_code == 404


# ---------------------------------------------------------------------------
# member management, isolation, revocation
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_remove_member_revokes_access(client, auth_headers, tmp_db_path, mocked_openai):
    cid, r, b_id, b_headers = _shared_cookbook(
        client, auth_headers, tmp_db_path, "viewer", mocked_openai
    )
    assert (
        client.delete(f"/cookbooks/{cid}/members/{b_id}", headers=auth_headers).status_code == 204
    )
    assert client.get(f"/cookbooks/{cid}", headers=b_headers).status_code == 404
    assert client.get(f"/recipes/{r}.json", headers=b_headers).status_code == 404


@pytest.mark.integration
def test_member_can_leave(client, auth_headers, tmp_db_path, mocked_openai):
    cid, r, b_id, b_headers = _shared_cookbook(
        client, auth_headers, tmp_db_path, "viewer", mocked_openai
    )
    assert client.delete(f"/cookbooks/{cid}/members/{b_id}", headers=b_headers).status_code == 204
    assert client.get(f"/cookbooks/{cid}", headers=b_headers).status_code == 404


@pytest.mark.integration
def test_manager_can_change_role(client, auth_headers, tmp_db_path, mocked_openai):
    cid, r, b_id, b_headers = _shared_cookbook(
        client, auth_headers, tmp_db_path, "viewer", mocked_openai
    )
    assert (
        client.patch(
            f"/cookbooks/{cid}/members/{b_id}", headers=auth_headers, json={"role": "editor"}
        ).status_code
        == 200
    )
    assert (
        client.put(f"/recipes/{r}", headers=b_headers, json={"title": "Now editable"}).status_code
        == 200
    )


@pytest.mark.integration
def test_unfriend_revokes_shares(client, auth_headers, tmp_db_path, mocked_openai):
    cid, r, b_id, b_headers = _shared_cookbook(
        client, auth_headers, tmp_db_path, "editor", mocked_openai
    )
    assert client.delete(f"/friends/{b_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/cookbooks/{cid}", headers=b_headers).status_code == 404
    assert client.get(f"/recipes/{r}.json", headers=b_headers).status_code == 404


@pytest.mark.integration
def test_quick_share_single_recipe(client, auth_headers, tmp_db_path, mocked_openai):
    b_id, b_headers = _mkuser(tmp_db_path, "b@example.com")
    _befriend(client, auth_headers, "b@example.com", b_headers)
    r = _recipe(client, auth_headers)

    resp = client.post(
        f"/recipes/{r}/share", headers=auth_headers, json={"friend_id": b_id, "role": "viewer"}
    )
    assert resp.status_code == 200
    cid = resp.json()["cookbook_id"]
    # B has a pending invite; before accepting, no access.
    invites = client.get("/cookbooks/invitations", headers=b_headers).json()
    assert [i["cookbook_id"] for i in invites] == [cid]
    assert client.get(f"/recipes/{r}.json", headers=b_headers).status_code == 404
    # After accepting, B can view the recipe.
    client.post(f"/cookbooks/invitations/{cid}/accept", headers=b_headers)
    assert client.get(f"/recipes/{r}.json", headers=b_headers).status_code == 200


@pytest.mark.integration
def test_quick_share_requires_friendship(client, auth_headers, tmp_db_path, mocked_openai):
    stranger_id, _ = _mkuser(tmp_db_path, "stranger@example.com")
    r = _recipe(client, auth_headers)
    resp = client.post(
        f"/recipes/{r}/share",
        headers=auth_headers,
        json={"friend_id": stranger_id, "role": "viewer"},
    )
    assert resp.status_code == 403


@pytest.mark.integration
def test_shared_recipe_appears_in_member_recipe_list(
    client, auth_headers, tmp_db_path, mocked_openai
):
    cid, r, b_id, b_headers = _shared_cookbook(
        client, auth_headers, tmp_db_path, "viewer", mocked_openai
    )
    # The shared recipe shows up in B's main recipe list, tagged as not-owned.
    items = {i["uuid"]: i for i in client.get("/recipes", headers=b_headers).json()["items"]}
    assert r in items
    assert items[r]["owned"] is False
    assert items[r]["owner_email"] == "test@example.com"
    # And it's marked owned for A.
    a_items = {i["uuid"]: i for i in client.get("/recipes", headers=auth_headers).json()["items"]}
    assert a_items[r]["owned"] is True
