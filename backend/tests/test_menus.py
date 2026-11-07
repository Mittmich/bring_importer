"""Menus with prep planning: CRUD, step drafting, editing, isolation, shopping list."""

import sqlite3
from unittest.mock import patch

import pytest
from passlib.context import CryptContext

from api import create_access_token
from api.models import Ingredient
from api.prep_steps import PrepStepDraft, _LlmStep, fallback_steps, sanitize

DRAFT = [
    PrepStepDraft(name="Make dough", duration=30, day=-1, at=18 * 60),
    PrepStepDraft(name="Bake", duration=40, hands=False, equipment="oven", temp=200, lead=10),
    PrepStepDraft(name="Plate", duration=10, lead=0),
]


@pytest.fixture
def drafted():
    with patch("api.routers.menus.draft_prep_steps", return_value=DRAFT) as mock:
        yield mock


def _recipe(client, auth_headers, mocked_openai) -> str:
    resp = client.post("/recipes/parse", headers=auth_headers, data={"image": "aGVsbG8="})
    assert resp.status_code == 200
    return resp.json()["uuid"]


def _menu(client, auth_headers, **body):
    resp = client.post(
        "/menus", headers=auth_headers, json={"title": "Autumn dinner", "guests": 6, **body}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _other_user(db, email="eve@example.com"):
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
            (email, CryptContext(schemes=["bcrypt"]).hash("pw")),
        )
        conn.commit()
    finally:
        conn.close()
    return {"Authorization": f"Bearer {create_access_token(data={'sub': email})}"}


# ---------------------------------------------------------------------------
# Menus
# ---------------------------------------------------------------------------


def test_create_list_update_delete_menu(client, auth_headers):
    menu = _menu(client, auth_headers, date="2026-11-14")
    assert menu["title"] == "Autumn dinner"
    assert menu["guests"] == 6
    assert menu["date"] == "2026-11-14"
    assert menu["courses"] == [] and menu["steps"] == []

    listed = client.get("/menus", headers=auth_headers).json()
    assert [m["id"] for m in listed] == [menu["id"]]

    updated = client.patch(
        f"/menus/{menu['id']}", headers=auth_headers, json={"title": "Dinner", "guests": 8}
    ).json()
    assert updated["title"] == "Dinner" and updated["guests"] == 8
    assert updated["date"] == "2026-11-14"  # untouched

    cleared = client.patch(f"/menus/{menu['id']}", headers=auth_headers, json={"date": ""})
    assert cleared.json()["date"] is None

    assert client.delete(f"/menus/{menu['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/menus/{menu['id']}", headers=auth_headers).status_code == 404


def test_menu_validation(client, auth_headers):
    assert client.post("/menus", headers=auth_headers, json={"title": ""}).status_code == 422
    bad_date = client.post("/menus", headers=auth_headers, json={"title": "x", "date": "14.11."})
    assert bad_date.status_code == 422
    too_many = client.post("/menus", headers=auth_headers, json={"title": "x", "guests": 500})
    assert too_many.status_code == 422


def test_menus_need_auth(client):
    assert client.get("/menus").status_code == 401


# ---------------------------------------------------------------------------
# Courses + drafted steps
# ---------------------------------------------------------------------------


def test_add_course_drafts_steps(client, auth_headers, mocked_openai, drafted):
    uuid = _recipe(client, auth_headers, mocked_openai)
    menu = _menu(client, auth_headers)
    resp = client.post(
        f"/menus/{menu['id']}/courses",
        headers=auth_headers,
        json={"recipe_uuid": uuid, "name": "Main"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    [course] = body["courses"]
    assert course["name"] == "Main"
    assert course["recipe_title"] == "Test Pancakes"
    assert course["serve"] == 19 * 60
    assert course["servings"] == 4
    assert [s["name"] for s in body["steps"]] == ["Make dough", "Bake", "Plate"]
    bake = body["steps"][1]
    assert bake["hands"] is False and bake["equipment"] == "oven" and bake["temp"] == 200
    assert bake["course_id"] == course["id"]
    dough = body["steps"][0]
    assert dough["day"] == -1 and dough["at"] == 18 * 60
    # The draft ran on the stored recipe.
    assert drafted.call_args.args[0]["name"] == "Test Pancakes"


def test_next_course_defaults(client, auth_headers, mocked_openai, drafted):
    uuid = _recipe(client, auth_headers, mocked_openai)
    menu = _menu(client, auth_headers)
    client.post(f"/menus/{menu['id']}/courses", headers=auth_headers, json={"recipe_uuid": uuid})
    body = client.post(
        f"/menus/{menu['id']}/courses", headers=auth_headers, json={"recipe_uuid": uuid}
    ).json()
    assert [c["serve"] for c in body["courses"]] == [19 * 60, 19 * 60 + 45]
    assert [c["name"] for c in body["courses"]] == ["Course 1", "Course 2"]
    assert len(body["steps"]) == 6


def test_add_course_with_inaccessible_recipe_404(client, auth_headers, mocked_openai, drafted):
    menu = _menu(client, auth_headers)
    resp = client.post(
        f"/menus/{menu['id']}/courses", headers=auth_headers, json={"recipe_uuid": "nope"}
    )
    assert resp.status_code == 404
    drafted.assert_not_called()


def test_update_and_delete_course(client, auth_headers, mocked_openai, drafted):
    uuid = _recipe(client, auth_headers, mocked_openai)
    menu = _menu(client, auth_headers)
    body = client.post(
        f"/menus/{menu['id']}/courses", headers=auth_headers, json={"recipe_uuid": uuid}
    ).json()
    cid = body["courses"][0]["id"]
    body = client.patch(
        f"/menus/{menu['id']}/courses/{cid}",
        headers=auth_headers,
        json={"serve": 20 * 60 + 15, "name": "Dessert"},
    ).json()
    assert body["courses"][0]["serve"] == 20 * 60 + 15
    assert body["courses"][0]["name"] == "Dessert"

    body = client.delete(f"/menus/{menu['id']}/courses/{cid}", headers=auth_headers).json()
    assert body["courses"] == [] and body["steps"] == []


def test_redraft_replaces_steps(client, auth_headers, mocked_openai, drafted):
    uuid = _recipe(client, auth_headers, mocked_openai)
    menu = _menu(client, auth_headers)
    body = client.post(
        f"/menus/{menu['id']}/courses", headers=auth_headers, json={"recipe_uuid": uuid}
    ).json()
    cid = body["courses"][0]["id"]
    client.delete(f"/menus/{menu['id']}/steps/{body['steps'][0]['id']}", headers=auth_headers)
    body = client.post(f"/menus/{menu['id']}/courses/{cid}/redraft", headers=auth_headers).json()
    assert [s["name"] for s in body["steps"]] == ["Make dough", "Bake", "Plate"]


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def test_add_edit_delete_step(client, auth_headers, mocked_openai, drafted):
    uuid = _recipe(client, auth_headers, mocked_openai)
    menu = _menu(client, auth_headers)
    body = client.post(
        f"/menus/{menu['id']}/courses", headers=auth_headers, json={"recipe_uuid": uuid}
    ).json()
    cid = body["courses"][0]["id"]

    body = client.post(
        f"/menus/{menu['id']}/steps",
        headers=auth_headers,
        json={"course_id": cid, "name": "Whip cream", "duration": 10, "lead": 5},
    ).json()
    step = body["steps"][-1]
    assert step["name"] == "Whip cream" and step["lead"] == 5 and step["hands"] is True

    url = f"/menus/{menu['id']}/steps/{step['id']}"
    step = client.patch(
        url, headers=auth_headers, json={"duration": 15, "equipment": "oven", "done": True}
    ).json()["steps"][-1]
    assert step["duration"] == 15 and step["done"] is True
    assert step["equipment"] == "oven" and step["temp"] == 180  # default temperature

    step = client.patch(url, headers=auth_headers, json={"temp": 220}).json()["steps"][-1]
    assert step["temp"] == 220
    step = client.patch(url, headers=auth_headers, json={"equipment": ""}).json()["steps"][-1]
    assert step["temp"] is None  # only oven steps have a temperature

    step = client.patch(url, headers=auth_headers, json={"day": -1}).json()["steps"][-1]
    assert step["day"] == -1 and step["at"] == 18 * 60

    body = client.delete(url, headers=auth_headers).json()
    assert step["id"] not in [s["id"] for s in body["steps"]]


def test_step_validation(client, auth_headers, mocked_openai, drafted):
    uuid = _recipe(client, auth_headers, mocked_openai)
    menu = _menu(client, auth_headers)
    body = client.post(
        f"/menus/{menu['id']}/courses", headers=auth_headers, json={"recipe_uuid": uuid}
    ).json()
    url = f"/menus/{menu['id']}/steps/{body['steps'][0]['id']}"
    assert client.patch(url, headers=auth_headers, json={"duration": 0}).status_code == 422
    assert client.patch(url, headers=auth_headers, json={"equipment": "grill"}).status_code == 422
    assert client.patch(url, headers=auth_headers, json={"day": 3}).status_code == 422
    other = client.post(
        f"/menus/{menu['id']}/steps",
        headers=auth_headers,
        json={"course_id": 999, "name": "x"},
    )
    assert other.status_code == 404


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_other_users_cannot_touch_a_menu(client, auth_headers, mocked_openai, drafted, tmp_db_path):
    uuid = _recipe(client, auth_headers, mocked_openai)
    menu = _menu(client, auth_headers)
    body = client.post(
        f"/menus/{menu['id']}/courses", headers=auth_headers, json={"recipe_uuid": uuid}
    ).json()
    cid, sid = body["courses"][0]["id"], body["steps"][0]["id"]
    eve = _other_user(tmp_db_path)
    mid = menu["id"]

    assert client.get("/menus", headers=eve).json() == []
    assert client.get(f"/menus/{mid}", headers=eve).status_code == 404
    assert client.patch(f"/menus/{mid}", headers=eve, json={"title": "x"}).status_code == 404
    assert client.delete(f"/menus/{mid}", headers=eve).status_code == 404
    assert client.patch(f"/menus/{mid}/steps/{sid}", headers=eve, json={}).status_code == 404
    assert client.delete(f"/menus/{mid}/courses/{cid}", headers=eve).status_code == 404
    assert client.post(f"/menus/{mid}/shopping-list", headers=eve).status_code == 404
    # Eve can't add someone else's (unshared) recipe to her own menu either.
    eve_menu = client.post("/menus", headers=eve, json={"title": "Mine"}).json()
    resp = client.post(f"/menus/{eve_menu['id']}/courses", headers=eve, json={"recipe_uuid": uuid})
    assert resp.status_code == 404


def test_step_ids_are_scoped_to_their_menu(client, auth_headers, mocked_openai, drafted):
    uuid = _recipe(client, auth_headers, mocked_openai)
    first = _menu(client, auth_headers)
    second = _menu(client, auth_headers)
    body = client.post(
        f"/menus/{first['id']}/courses", headers=auth_headers, json={"recipe_uuid": uuid}
    ).json()
    sid = body["steps"][0]["id"]
    resp = client.patch(
        f"/menus/{second['id']}/steps/{sid}", headers=auth_headers, json={"name": "x"}
    )
    assert resp.status_code == 404


def test_deleted_recipe_drops_out_of_menu(client, auth_headers, mocked_openai, drafted):
    uuid = _recipe(client, auth_headers, mocked_openai)
    menu = _menu(client, auth_headers)
    client.post(f"/menus/{menu['id']}/courses", headers=auth_headers, json={"recipe_uuid": uuid})
    assert client.delete(f"/recipes/{uuid}", headers=auth_headers).status_code in (200, 204)
    body = client.get(f"/menus/{menu['id']}", headers=auth_headers).json()
    assert body["courses"] == [] and body["steps"] == []


# ---------------------------------------------------------------------------
# Shopping list
# ---------------------------------------------------------------------------


def test_shopping_list_scales_to_guests(client, auth_headers, mocked_openai, drafted):
    uuid = _recipe(client, auth_headers, mocked_openai)  # "4 servings": 1 cup flour, 2 eggs
    menu = _menu(client, auth_headers)  # 6 guests
    client.post(f"/menus/{menu['id']}/courses", headers=auth_headers, json={"recipe_uuid": uuid})

    merged = [Ingredient(amount="1 ½ cup", name="flour")]
    with patch("api.routers.menus.merge_ingredients", return_value=merged) as mock_merge:
        resp = client.post(f"/menus/{menu['id']}/shopping-list", headers=auth_headers)
    assert resp.status_code == 200
    sent = mock_merge.call_args.args[0]
    assert [(i.amount, i.name) for i in sent] == [
        ("1½ cup", "flour"),
        ("3", "eggs"),
        ("1½ cup", "milk"),
    ]
    body = resp.json()
    assert body["items"] == [{"amount": "1 ½ cup", "name": "flour"}]
    page = client.get(f"/meal-plan/shopping-list/{body['token']}.html")
    assert page.status_code == 200 and "1 ½ cup flour" in page.text


# ---------------------------------------------------------------------------
# Drafting helpers
# ---------------------------------------------------------------------------


def test_fallback_lays_steps_back_to_back():
    steps = fallback_steps(
        {"name": "Soup", "instructions": [{"text": "Chop."}, {"text": "Cook."}, "Serve."]}
    )
    assert [s.name for s in steps] == ["Chop.", "Cook.", "Serve."]
    assert [s.lead for s in steps] == [20, 10, 0]
    assert all(s.duration == 10 and s.day == 0 for s in steps)


def test_sanitize_clamps_and_rounds():
    raw = [
        _LlmStep(
            name="  Roast   veg ",
            duration_minutes=43,
            hands_on=False,
            equipment="oven",
            oven_temp_c=None,
            make_day_before=False,
            ready_minutes_before_serving=-20,
        ),
        _LlmStep(
            name="",
            duration_minutes=5,
            hands_on=True,
            equipment="",
            oven_temp_c=None,
            make_day_before=False,
            ready_minutes_before_serving=0,
        ),
        _LlmStep(
            name="Marinate",
            duration_minutes=2,
            hands_on=True,
            equipment="stove",
            oven_temp_c=250,
            make_day_before=True,
            ready_minutes_before_serving=0,
        ),
    ]
    steps = sanitize(raw)
    assert [s.name for s in steps] == ["Roast veg", "Marinate"]
    roast, marinate = steps
    assert roast.duration == 45 and roast.lead == 0 and roast.temp == 180
    assert marinate.duration == 5 and marinate.day == -1 and marinate.temp is None


def test_draft_falls_back_when_llm_fails():
    from api import prep_steps

    with patch.object(prep_steps, "_get_client", side_effect=RuntimeError("down")):
        steps = prep_steps.draft_prep_steps({"name": "Soup", "instructions": [{"text": "Cook."}]})
    assert [s.name for s in steps] == ["Cook."]


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------


def test_plan_rows_order_serving_first_on_ties():
    from api.menu_pdf import plan_rows

    menu = {
        "courses": [{"id": 1, "serve": 19 * 60 + 30, "name": "Starter"}],
        "steps": [
            {"id": 1, "course_id": 1, "day": 0, "lead": 0, "duration": 10, "at": None},
            {"id": 2, "course_id": 1, "day": 0, "lead": -40, "duration": 40, "at": None},
            {"id": 3, "course_id": 1, "day": -1, "lead": 0, "duration": 30, "at": 18 * 60},
        ],
    }
    before, day = plan_rows(menu)
    assert [r.step["id"] for r in before if r.step] == [3]
    assert [(r.time, r.step["id"] if r.step else "serve") for r in day] == [
        (19 * 60 + 20, 1),
        (19 * 60 + 30, "serve"),
        (19 * 60 + 30, 2),
    ]


def test_menu_pdf_export(client, auth_headers, mocked_openai, drafted):
    uuid = _recipe(client, auth_headers, mocked_openai)
    menu = _menu(client, auth_headers, title="Herbst-Menü", date="2026-11-14")
    client.post(
        f"/menus/{menu['id']}/courses",
        headers=auth_headers,
        json={"recipe_uuid": uuid, "name": "Hauptgang"},
    )
    resp = client.get(
        f"/menus/{menu['id']}/plan.pdf", headers={**auth_headers, "Accept-Language": "de"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")
    assert "Herbst-Men" in resp.headers["content-disposition"]


def test_empty_menu_pdf_and_isolation(client, auth_headers, tmp_db_path):
    menu = _menu(client, auth_headers)
    assert client.get(f"/menus/{menu['id']}/plan.pdf", headers=auth_headers).status_code == 200
    eve = _other_user(tmp_db_path)
    assert client.get(f"/menus/{menu['id']}/plan.pdf", headers=eve).status_code == 404
