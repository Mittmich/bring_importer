"""Tests for the ``manage_users.py`` CLI module.

These tests exercise the module-level functions directly (not via
subprocess). They use a tmp SQLite file and monkeypatch both
``manage_users.DB_PATH`` (used by ``check_db``) and
``manage_users.get_db_connection`` (used by the CRUD functions), plus
``api.get_db_connection`` (used by the foreign-key cascade path).
"""

import sqlite3
from unittest.mock import patch

import pytest

import api
import manage_users

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manage_db(tmp_db_path, monkeypatch):
    """Wire up ``manage_users`` to use a per-test tmp db file.

    Returns the path so individual tests can inspect it directly.
    """
    monkeypatch.setattr(manage_users, "DB_PATH", str(tmp_db_path))

    def _get_db_connection():
        conn = sqlite3.connect(str(tmp_db_path))
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(manage_users, "get_db_connection", _get_db_connection)
    monkeypatch.setattr(api, "get_db_connection", _get_db_connection)
    # Build the schema in the tmp file.
    api.init_db()
    return tmp_db_path


def _count(table, db_path, where=None, params=()):
    conn = sqlite3.connect(str(db_path))
    try:
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# check_db
# ---------------------------------------------------------------------------


def test_check_db_missing_file_returns_false(tmp_path, monkeypatch):
    """If the db file does not exist, check_db returns False."""
    missing = tmp_path / "does-not-exist.db"
    monkeypatch.setattr(manage_users, "DB_PATH", str(missing))
    assert manage_users.check_db() is False


def test_check_db_existing_with_users_table_returns_true(manage_db):
    """An existing db file that has the users table is OK."""
    # The fixture already created the schema via api.init_db().
    assert manage_users.check_db() is True


def test_check_db_existing_without_users_table_returns_false(manage_db, capsys):
    """An existing db file that has no users table returns False (with a message)."""
    # Drop the users table the fixture created.
    conn = sqlite3.connect(str(manage_db))
    conn.execute("DROP TABLE users")
    conn.commit()
    conn.close()
    assert manage_users.check_db() is False
    captured = capsys.readouterr()
    assert "users" in captured.out


# ---------------------------------------------------------------------------
# add_user
# ---------------------------------------------------------------------------


def test_add_user_inserts_new(manage_db):
    assert manage_users.add_user("a@example.com", "pw1") is True
    assert _count("users", manage_db) == 1
    conn = sqlite3.connect(str(manage_db))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT email, hashed_password FROM users WHERE email = ?",
            ("a@example.com",),
        ).fetchone()
    finally:
        conn.close()
    assert row["email"] == "a@example.com"
    # verify_password against the stored hash must succeed
    assert api.verify_password("pw1", row["hashed_password"]) is True


def test_add_user_updates_existing(manage_db):
    assert manage_users.add_user("a@example.com", "pw1") is True
    assert manage_users.add_user("a@example.com", "pw2") is True
    assert _count("users", manage_db) == 1  # still one row
    conn = sqlite3.connect(str(manage_db))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT hashed_password FROM users WHERE email = ?", ("a@example.com",)
        ).fetchone()
    finally:
        conn.close()
    # The hash is now for pw2, not pw1.
    assert api.verify_password("pw1", row["hashed_password"]) is False
    assert api.verify_password("pw2", row["hashed_password"]) is True


# ---------------------------------------------------------------------------
# remove_user
# ---------------------------------------------------------------------------


def test_remove_user_no_recipes_removes(manage_db):
    manage_users.add_user("a@example.com", "pw1")
    assert _count("users", manage_db) == 1
    assert manage_users.remove_user("a@example.com") is True
    assert _count("users", manage_db) == 0


def test_remove_user_unknown_returns_false(manage_db, capsys):
    assert manage_users.remove_user("ghost@example.com") is False
    captured = capsys.readouterr()
    assert "not found" in captured.out.lower()


def test_remove_user_with_recipes_confirm_n_does_not_remove(manage_db):
    """If user has recipes and confirm='n', the user (and recipes) stay."""
    # Need a real schema and a real user_id for the FK to point at.
    api.init_db()
    manage_users.add_user("a@example.com", "pw1")
    user_id = api.get_user_id("a@example.com")
    conn = sqlite3.connect(str(manage_db))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "INSERT INTO recipes (uuid, user_id, title, recipe_json) VALUES (?, ?, ?, ?)",
            ("abc-123", user_id, "Test Recipe", "{}"),
        )
        conn.commit()
    finally:
        conn.close()
    assert _count("recipes", manage_db) == 1

    with patch("builtins.input", return_value="n"):
        assert manage_users.remove_user("a@example.com") is False

    assert _count("users", manage_db) == 1
    assert _count("recipes", manage_db) == 1  # recipes still there


def test_remove_user_with_recipes_confirm_y_removes_user_and_recipes(manage_db):
    api.init_db()
    manage_users.add_user("a@example.com", "pw1")
    user_id = api.get_user_id("a@example.com")
    conn = sqlite3.connect(str(manage_db))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "INSERT INTO recipes (uuid, user_id, title, recipe_json) VALUES (?, ?, ?, ?)",
            ("abc-123", user_id, "Test Recipe", "{}"),
        )
        conn.commit()
    finally:
        conn.close()
    assert _count("recipes", manage_db) == 1

    with patch("builtins.input", return_value="y"):
        assert manage_users.remove_user("a@example.com") is True

    assert _count("users", manage_db) == 0
    assert _count("recipes", manage_db) == 0  # cascade delete


# ---------------------------------------------------------------------------
# list_users
# ---------------------------------------------------------------------------


def test_list_users_empty_db_prints_no_users_found(manage_db, capsys):
    manage_users.list_users()
    captured = capsys.readouterr()
    assert "No users found" in captured.out


def test_list_users_with_seed_prints_table(manage_db, capsys):
    api.init_db()
    manage_users.add_user("a@example.com", "pw1")
    user_id = api.get_user_id("a@example.com")
    conn = sqlite3.connect(str(manage_db))
    try:
        conn.execute(
            "INSERT INTO recipes (uuid, user_id, title, recipe_json) VALUES (?, ?, ?, ?)",
            ("abc-123", user_id, "Test Recipe", "{}"),
        )
        conn.commit()
    finally:
        conn.close()

    manage_users.list_users()
    captured = capsys.readouterr()
    assert "a@example.com" in captured.out
    assert "1" in captured.out  # recipe count
    assert "Total users: 1" in captured.out
