"""Integration tests for recipe hero images (upload / fetch / delete).

Images are stored on disk under ``config.RECIPE_IMAGES_DIR``; the ``image_dir``
fixture points that at a per-test tmp directory so nothing touches the repo.
"""

import base64
import os

import pytest

import api.config as config

# Arbitrary bytes — the server stores what the client sends (the client crops
# to a JPEG) and never re-decodes the image, so real JPEG data isn't needed.
RAW_IMAGE = b"\xff\xd8\xff\xe0fake-jpeg-bytes\xff\xd9"
IMAGE_B64 = base64.b64encode(RAW_IMAGE).decode()


@pytest.fixture
def image_dir(tmp_path, monkeypatch):
    """Point the recipe-images storage dir at a per-test tmp directory."""
    d = tmp_path / "recipe_images"
    monkeypatch.setattr(config, "RECIPE_IMAGES_DIR", str(d))
    return d


def _make_recipe(client, auth_headers) -> str:
    """Create a recipe via the mocked parse endpoint and return its uuid."""
    resp = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert resp.status_code == 200
    return resp.json()["uuid"]


@pytest.mark.integration
def test_set_get_image_roundtrip(client, auth_headers, mocked_openai, image_dir):
    uuid = _make_recipe(client, auth_headers)

    resp = client.put(f"/recipes/{uuid}/image", headers=auth_headers, json={"image": IMAGE_B64})
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_image"] is True
    assert body["image_url"].startswith(f"/recipes/{uuid}/image")

    # The recipe JSON now advertises the image.
    j = client.get(f"/recipes/{uuid}.json", headers=auth_headers).json()
    assert j["has_image"] is True
    assert j["image_url"].startswith(f"/recipes/{uuid}/image")

    # And the bytes come back verbatim as image/jpeg.
    img = client.get(f"/recipes/{uuid}/image", headers=auth_headers)
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"
    assert img.content == RAW_IMAGE


@pytest.mark.integration
def test_set_image_accepts_data_url_prefix(client, auth_headers, mocked_openai, image_dir):
    uuid = _make_recipe(client, auth_headers)
    data_url = f"data:image/jpeg;base64,{IMAGE_B64}"
    resp = client.put(f"/recipes/{uuid}/image", headers=auth_headers, json={"image": data_url})
    assert resp.status_code == 200
    img = client.get(f"/recipes/{uuid}/image", headers=auth_headers)
    assert img.content == RAW_IMAGE


@pytest.mark.integration
def test_get_image_404_when_none(client, auth_headers, mocked_openai, image_dir):
    uuid = _make_recipe(client, auth_headers)
    assert client.get(f"/recipes/{uuid}/image", headers=auth_headers).status_code == 404


@pytest.mark.integration
def test_set_image_requires_auth(client, auth_headers, mocked_openai, image_dir):
    uuid = _make_recipe(client, auth_headers)
    assert client.put(f"/recipes/{uuid}/image", json={"image": IMAGE_B64}).status_code == 401


@pytest.mark.integration
def test_set_image_unknown_uuid_404(client, auth_headers, image_dir):
    resp = client.put(
        "/recipes/does-not-exist/image", headers=auth_headers, json={"image": IMAGE_B64}
    )
    assert resp.status_code == 404


@pytest.mark.integration
def test_set_image_invalid_base64_422(client, auth_headers, mocked_openai, image_dir):
    uuid = _make_recipe(client, auth_headers)
    resp = client.put(
        f"/recipes/{uuid}/image", headers=auth_headers, json={"image": "not base64!!"}
    )
    assert resp.status_code == 422


@pytest.mark.integration
def test_delete_image(client, auth_headers, mocked_openai, image_dir):
    uuid = _make_recipe(client, auth_headers)
    client.put(f"/recipes/{uuid}/image", headers=auth_headers, json={"image": IMAGE_B64})

    resp = client.delete(f"/recipes/{uuid}/image", headers=auth_headers)
    assert resp.status_code == 204
    assert not os.path.exists(image_dir / f"{uuid}.jpg")
    assert client.get(f"/recipes/{uuid}/image", headers=auth_headers).status_code == 404
    j = client.get(f"/recipes/{uuid}.json", headers=auth_headers).json()
    assert j["has_image"] is False
    assert j["image_url"] is None


@pytest.mark.integration
def test_private_image_not_served_anonymously(client, auth_headers, mocked_openai, image_dir):
    uuid = _make_recipe(client, auth_headers)
    client.put(f"/recipes/{uuid}/image", headers=auth_headers, json={"image": IMAGE_B64})

    # Private by default: anonymous request is refused with 404 (not 403).
    assert client.get(f"/recipes/{uuid}/image").status_code == 404

    # Make it public, then the same anonymous request succeeds.
    client.put(f"/recipes/{uuid}", headers=auth_headers, json={"is_public": True})
    anon = client.get(f"/recipes/{uuid}/image")
    assert anon.status_code == 200
    assert anon.content == RAW_IMAGE


@pytest.mark.integration
def test_deleting_recipe_removes_image_file(client, auth_headers, mocked_openai, image_dir):
    uuid = _make_recipe(client, auth_headers)
    client.put(f"/recipes/{uuid}/image", headers=auth_headers, json={"image": IMAGE_B64})
    assert os.path.exists(image_dir / f"{uuid}.jpg")

    assert client.delete(f"/recipes/{uuid}", headers=auth_headers).status_code == 204
    assert not os.path.exists(image_dir / f"{uuid}.jpg")


@pytest.mark.integration
def test_list_recipes_includes_image_fields(client, auth_headers, mocked_openai, image_dir):
    with_img = _make_recipe(client, auth_headers)
    without_img = _make_recipe(client, auth_headers)
    client.put(f"/recipes/{with_img}/image", headers=auth_headers, json={"image": IMAGE_B64})

    items = {r["uuid"]: r for r in client.get("/recipes", headers=auth_headers).json()["items"]}
    assert items[with_img]["has_image"] is True
    assert items[with_img]["image_url"].startswith(f"/recipes/{with_img}/image")
    assert items[without_img]["has_image"] is False
    assert items[without_img]["image_url"] is None
