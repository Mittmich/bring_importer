# Testing the Recipe Parser API

This directory contains the FastAPI backend and its pytest-based test suite.

## Quick start

```bash
# Install dev/test deps (uses the uv venv at backend/.venv)
cd backend
uv pip install -e ".[dev]"

# Run the full suite with coverage
pytest --cov=api --cov=manage_users --cov-fail-under=80
```

## Coverage threshold: 80%

The `pytest` invocation above fails if total line coverage drops below **80%**.
This is enforced in CI (`.github/workflows/ci.yml`).

The threshold is a floor for the *combined* coverage of `api.py` and
`manage_users.py`, not for each file individually. As of this writing:

| File             | Stmts | Cover |
|------------------|-------|-------|
| `api.py`         | ~230  | ~95%  |
| `manage_users.py`| ~130  | ~65%  |

The `manage_users.py` gap is mostly the `argparse` setup and the `main()`
CLI entry point; those are exercised manually via `./manage_users.py`,
not by the test suite.

## Test layout

```
tests/
├── __init__.py
├── conftest.py            # shared fixtures: tmp_db, app, client, seed_user,
│                          #   auth_headers, mocked_openai
├── test_password.py       # 7 tests — bcrypt hashing helpers
├── test_db.py             # 7 tests — init_db schema and idempotency
├── test_html_parser.py    # 10 tests — _extract_recipe_from_html
├── test_health.py         # 5 tests — GET /health
├── test_auth.py           # 14 tests — /token + JWT verification
├── test_recipes.py        # 10 integration tests — recipe endpoints
└── test_manage_users.py   # 11 tests — manage_users CLI module
```

Total: **64 tests** as of the initial pass. New tests should be added in
`tests/test_<topic>.py` (the `test_*.py` pattern is configured in
`[tool.pytest.ini_options]`).

## How the fixtures work

- **`tmp_db_path`** — per-test on-disk SQLite file in pytest's `tmp_path`.
  File-based, **not** `:memory:`, because `get_db_connection()` opens a
  fresh connection per call and `:memory:` dbs don't share state across
  connections.
- **`app`** — FastAPI app with `api.get_db_connection` monkeypatched to
  point at `tmp_db_path`; `init_db()` called once.
- **`client`** — `fastapi.testclient.TestClient(app)`.
- **`seed_user`** — inserts `test@example.com` (password
  `correctpassword`) into the tmp db.
- **`auth_headers`** — `{"Authorization": "Bearer <token>"}` for
  `seed_user`.
- **`mocked_openai`** — `responses.RequestsMock` mocking
  `POST https://api.openai.com/v1/chat/completions` to return a canonical
  `schema.org/Recipe` HTML payload (see `CANONICAL_RECIPE_HTML`).

## Markers

- **`integration`** — end-to-end tests that go through the FastAPI
  `TestClient` and exercise the real request/response cycle. Run with:
  ```bash
  pytest -m integration
  ```
  The default `pytest` run (no `-m`) executes **all** tests including
  integration. Add `@pytest.mark.integration` to any new test that hits
  multiple layers (auth + db + HTTP).

## A note on `bcrypt`

`passlib 1.7.4` (the version pinned in `pyproject.toml`) is **incompatible**
with `bcrypt >= 4.0`. We pin `bcrypt<4.0` in the main dependencies as a
workaround. If passlib is ever upgraded, drop the pin and re-run the
`test_password.py` suite to confirm.
