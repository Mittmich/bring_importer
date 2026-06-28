"""Tests for opt-in training-data collection on image import."""

import json
import os

import api.config as config


def _parse(client, auth_headers, image="aGVsbG8="):  # "hello"
    return client.post("/recipes/parse", headers=auth_headers, data={"image": image})


def test_collection_off_by_default(client, auth_headers, mocked_openai, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRAINING_DATA_DIR", str(tmp_path / "td"))
    # COLLECT_TRAINING_DATA defaults off; do not enable it.
    resp = _parse(client, auth_headers)
    assert resp.status_code == 200
    assert not (tmp_path / "td").exists()


def test_collection_persists_image_and_raw_snapshot(
    client, auth_headers, mocked_openai, tmp_path, monkeypatch
):
    td = tmp_path / "td"
    monkeypatch.setattr(config, "COLLECT_TRAINING_DATA", True)
    monkeypatch.setattr(config, "TRAINING_DATA_DIR", str(td))

    resp = _parse(client, auth_headers)
    assert resp.status_code == 200
    uuid = resp.json()["uuid"]

    image_path = td / "images" / f"{uuid}.jpg"
    raw_path = td / "raw" / f"{uuid}.json"
    assert image_path.exists()
    assert image_path.read_bytes() == b"hello"  # decoded from the base64 form field

    snapshot = json.loads(raw_path.read_text(encoding="utf-8"))
    assert snapshot["uuid"] == uuid
    assert snapshot["model"]  # records the model used
    assert snapshot["prompt_version"]
    assert "ts" in snapshot
    # Raw extraction is captured as the pre-edit label baseline.
    assert snapshot["raw_recipe"]["title"] == "Test Pancakes"
    assert [i["name"] for i in snapshot["raw_recipe"]["ingredients"]] == ["flour", "eggs", "milk"]


def test_collection_skips_oversized_image(
    client, auth_headers, mocked_openai, tmp_path, monkeypatch
):
    import base64

    from api import data_collection

    monkeypatch.setattr(config, "COLLECT_TRAINING_DATA", True)
    monkeypatch.setattr(config, "TRAINING_DATA_DIR", str(tmp_path / "td"))
    monkeypatch.setattr(data_collection, "MAX_IMAGE_BYTES", 4)  # tiny cap

    big = base64.b64encode(b"way too many bytes").decode()
    resp = _parse(client, auth_headers, image=big)
    assert resp.status_code == 200
    # Import still succeeds, but nothing is written for the oversized upload.
    uuid = resp.json()["uuid"]
    assert not os.path.exists(tmp_path / "td" / "images" / f"{uuid}.jpg")
