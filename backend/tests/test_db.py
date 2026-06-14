"""Unit tests for ``api.init_db()`` — schema, idempotency, foreign keys.

These tests use the ``tmp_db_path`` fixture (a real on-disk SQLite file in a
per-test temp directory). They do not go through the FastAPI app — they
exercise the raw ``init_db`` function directly, so they're independent of the
route layer.
"""

import sqlite3

import pytest

import api


@pytest.fixture
def fresh_db(tmp_db_path, monkeypatch):
    """A tmp db file with no schema; ``init_db`` hasn't been called yet.

    Monkeypatches ``api.get_db_connection`` to point at the tmp file (same
    pattern as the ``app`` fixture in conftest.py).
    """

    def _get_db_connection():
        conn = sqlite3.connect(str(tmp_db_path))
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(api, "get_db_connection", _get_db_connection)
    return tmp_db_path


def test_init_db_creates_users_table(fresh_db):
    api.init_db()
    conn = sqlite3.connect(str(fresh_db))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchall()
    finally:
        conn.close()
    assert [r[0] for r in rows] == ["users"]


def test_init_db_creates_recipes_table(fresh_db):
    api.init_db()
    conn = sqlite3.connect(str(fresh_db))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recipes'"
        ).fetchall()
    finally:
        conn.close()
    assert [r[0] for r in rows] == ["recipes"]


def test_users_table_has_expected_columns(fresh_db):
    api.init_db()
    conn = sqlite3.connect(str(fresh_db))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    finally:
        conn.close()
    assert {"id", "email", "hashed_password"}.issubset(cols)


def test_recipes_table_has_expected_columns(fresh_db):
    api.init_db()
    conn = sqlite3.connect(str(fresh_db))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(recipes)").fetchall()}
    finally:
        conn.close()
    assert {"uuid", "user_id", "title", "recipe_json", "created_at"}.issubset(cols)


def test_email_column_is_unique(fresh_db):
    api.init_db()
    pwd = api.get_password_hash("pw")
    conn = sqlite3.connect(str(fresh_db))
    try:
        conn.execute("INSERT INTO users (email, hashed_password) VALUES (?, ?)", ("a@b.c", pwd))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
                ("a@b.c", pwd),
            )
            conn.commit()
    finally:
        conn.close()


def test_init_db_is_idempotent(fresh_db):
    """Calling init_db twice must not raise and must not drop the schema."""
    api.init_db()
    api.init_db()
    conn = sqlite3.connect(str(fresh_db))
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    finally:
        conn.close()
    assert {"users", "recipes"}.issubset(tables)


def test_recipes_user_id_foreign_key_registered(fresh_db):
    """``PRAGMA foreign_key_list(recipes)`` should list users(id)."""
    api.init_db()
    conn = sqlite3.connect(str(fresh_db))
    try:
        fks = conn.execute("PRAGMA foreign_key_list(recipes)").fetchall()
    finally:
        conn.close()
    # Each FK row: (id, seq, table, from, to, on_update, on_delete, match)
    assert len(fks) == 1, f"expected 1 FK on recipes, got {len(fks)}"
    fk = fks[0]
    assert fk[2] == "users"  # table
    assert fk[3] == "user_id"  # from
    assert fk[4] == "id"  # to
