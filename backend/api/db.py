"""SQLite connection helpers and the schema bootstrap.

The schema lives in two ``CREATE TABLE IF NOT EXISTS`` statements and is
idempotent. The schema migration for the comprehensive-recipe-management
plan (adding ``note``, ``source``, ``created_at``, ``updated_at`` columns)
lives in step 3 of the plan and is not in this file yet.
"""

import sqlite3

DB_PATH = "recipes.db"


def get_db_connection():
    """Open a fresh SQLite connection to the on-disk database file."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the ``users`` and ``recipes`` tables if they don't exist.

    Safe to call repeatedly; both statements use ``IF NOT EXISTS``. Also
    runs the in-place migration that adds ``note``, ``source``, and
    ``updated_at`` columns (SQLite has no ``ADD COLUMN IF NOT EXISTS``,
    so we guard with ``PRAGMA table_info``).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create users table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL
    )
    """
    )

    # Create recipes table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS recipes (
        uuid TEXT PRIMARY KEY,
        user_id INTEGER,
        title TEXT,
        recipe_json TEXT,  -- This can store large text including HTML content
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """
    )

    # ---- in-place migrations for pre-existing recipes.db (step 3) ----
    # Each migration is guarded: skip if the column already exists.
    _existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(recipes)").fetchall()}
    if "note" not in _existing_cols:
        cursor.execute("ALTER TABLE recipes ADD COLUMN note TEXT")
    if "source" not in _existing_cols:
        cursor.execute("ALTER TABLE recipes ADD COLUMN source TEXT")
    if "updated_at" not in _existing_cols:
        cursor.execute(
            "ALTER TABLE recipes ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        )

    conn.commit()
    conn.close()
