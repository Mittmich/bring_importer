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
    # display_name — optional friendly name shown instead of email in the
    # friends/members/owner UIs. Guarded add for pre-existing DBs.
    _user_cols = {row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}
    if "display_name" not in _user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
    # language — preferred UI / recipe language code (see api/i18n.py). NULL means
    # "not chosen yet": the client falls back to the browser language.
    if "language" not in _user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN language TEXT")
    # Admin control plane (see .claude/plans/admin-control-plane.md):
    # is_admin / disabled flags; token_version is embedded in JWTs as ``ver`` so
    # bumping it revokes every session; created_at is NULL for pre-existing users
    # (SQLite can't ADD COLUMN with a non-constant default).
    if "is_admin" not in _user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    if "disabled" not in _user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
    if "token_version" not in _user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0")
    if "created_at" not in _user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP")
    if "last_login_at" not in _user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP")
    if "invited_by" not in _user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN invited_by INTEGER")

    # One-time links: admin-issued sign-up invites and password resets. Only a
    # SHA-256 of the token is stored, so the table never holds a usable link.
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS auth_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CHECK(kind IN ('signup', 'reset')),
        token_hash TEXT UNIQUE NOT NULL,
        email TEXT,
        user_id INTEGER,
        note TEXT,
        created_by INTEGER,
        created_at TIMESTAMP NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        used_at TIMESTAMP,
        used_by INTEGER,
        revoked_at TIMESTAMP
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

    # Create meal_plan_entries table — one row per recipe assigned to a day.
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS meal_plan_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,  -- ISO 'YYYY-MM-DD'
        recipe_uuid TEXT NOT NULL,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """
    )

    # Create shopping_lists table — caches a merged ingredient list under an
    # unguessable token so the public Bring HTML endpoint can serve it without
    # auth (Bring fetches the URL from its own servers).
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS shopping_lists (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        items_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """
    )

    # Create tags + recipe_tags tables — user-defined tags, many-to-many with
    # recipes. Tag names are unique per user, case-insensitively.
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        color TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_user_name "
        "ON tags(user_id, name COLLATE NOCASE)"
    )
    # Migrate older DBs created before tags carried a colour. CREATE TABLE
    # IF NOT EXISTS won't add the column, so add it idempotently here.
    existing_tag_cols = {r["name"] for r in cursor.execute("PRAGMA table_info(tags)").fetchall()}
    if "color" not in existing_tag_cols:
        cursor.execute("ALTER TABLE tags ADD COLUMN color TEXT")
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS recipe_tags (
        recipe_uuid TEXT NOT NULL,
        tag_id INTEGER NOT NULL,
        PRIMARY KEY (recipe_uuid, tag_id),
        FOREIGN KEY (tag_id) REFERENCES tags (id)
    )
    """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_tags_tag ON recipe_tags(tag_id)")

    # Create friendships table — the social graph behind recipe sharing. One
    # canonical row per pair (requester -> addressee); query both directions.
    # A 'pending' row is an outstanding friend request; 'accepted' is a
    # friendship. See .claude/plans/friends-cookbooks-sharing.md.
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS friendships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requester_id INTEGER NOT NULL,
        addressee_id INTEGER NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending', 'accepted', 'blocked')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        responded_at TIMESTAMP,
        UNIQUE(requester_id, addressee_id),
        FOREIGN KEY (requester_id) REFERENCES users (id),
        FOREIGN KEY (addressee_id) REFERENCES users (id)
    )
    """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_friendships_addressee "
        "ON friendships(addressee_id, status)"
    )

    # Create cookbooks + cookbook_recipes — a cookbook is a named collection of
    # recipes owned by one user (the unit of sharing in later phases). Phase 2
    # is personal-only; sharing (cookbook_members) arrives in Phase 3. See
    # .claude/plans/friends-cookbooks-sharing.md.
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS cookbooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'normal',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (owner_id) REFERENCES users (id)
    )
    """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cookbooks_owner ON cookbooks(owner_id)")
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS cookbook_recipes (
        cookbook_id INTEGER NOT NULL,
        recipe_uuid TEXT NOT NULL,
        added_by INTEGER,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (cookbook_id, recipe_uuid),
        FOREIGN KEY (cookbook_id) REFERENCES cookbooks (id)
    )
    """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cookbook_recipes_recipe ON cookbook_recipes(recipe_uuid)"
    )

    # Create cookbook_members — grantees a cookbook is shared with (Phase 3).
    # The cookbook owner is implicit (cookbooks.owner_id), never a row here. A
    # 'pending' row is an outstanding invitation; 'accepted' is active access.
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS cookbook_members (
        cookbook_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('viewer', 'editor', 'manager')),
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'accepted')),
        invited_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        responded_at TIMESTAMP,
        PRIMARY KEY (cookbook_id, user_id),
        FOREIGN KEY (cookbook_id) REFERENCES cookbooks (id),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cookbook_members_user "
        "ON cookbook_members(user_id, status)"
    )

    # Create google_integrations table — one row per user holding the Google
    # OAuth refresh token and the chosen target calendar for meal-plan sync.
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS google_integrations (
        user_id INTEGER PRIMARY KEY,
        refresh_token TEXT NOT NULL,
        calendar_id TEXT NOT NULL DEFAULT 'primary',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """
    )

    # app_settings — global key/value switches (e.g. the ``planner`` feature
    # flag, see api/features.py). A missing key means "use the default".
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )

    # Menus — recipes cooked together for one occasion, with an editable prep
    # plan. See .claude/plans/menus-prep-planning.md. Times are minutes after
    # midnight; a same-day step is anchored to its course's serving time by
    # ``lead`` (minutes before serving it must be finished), a day-before step
    # (day = -1) by its absolute start ``at``.
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS menus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        date TEXT,  -- ISO 'YYYY-MM-DD' or NULL
        guests INTEGER NOT NULL DEFAULT 4,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_menus_user ON menus(user_id)")
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS menu_courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_id INTEGER NOT NULL,
        recipe_uuid TEXT NOT NULL,
        name TEXT NOT NULL,
        serve INTEGER NOT NULL,
        position INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (menu_id) REFERENCES menus (id)
    )
    """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_menu_courses_menu ON menu_courses(menu_id)")
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS menu_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        duration INTEGER NOT NULL,
        day INTEGER NOT NULL DEFAULT 0,
        lead INTEGER NOT NULL DEFAULT 0,
        at INTEGER,
        hands INTEGER NOT NULL DEFAULT 1,
        equipment TEXT NOT NULL DEFAULT '',
        temp INTEGER,
        done INTEGER NOT NULL DEFAULT 0,
        position INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (menu_id) REFERENCES menus (id),
        FOREIGN KEY (course_id) REFERENCES menu_courses (id)
    )
    """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_menu_steps_menu ON menu_steps(menu_id)")

    # ---- in-place migrations for pre-existing recipes.db (step 3) ----
    # Each migration is guarded: skip if the column already exists.
    _existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(recipes)").fetchall()}
    if "note" not in _existing_cols:
        cursor.execute("ALTER TABLE recipes ADD COLUMN note TEXT")
    if "source" not in _existing_cols:
        cursor.execute("ALTER TABLE recipes ADD COLUMN source TEXT")
    if "updated_at" not in _existing_cols:
        # SQLite forbids non-constant defaults on ADD COLUMN, so add it
        # without a DEFAULT and backfill from created_at below. The app
        # always sets updated_at explicitly on UPDATE (see
        # api/routers/recipes.py), so this backfill only needs to cover
        # rows that pre-date the column.
        cursor.execute("ALTER TABLE recipes ADD COLUMN updated_at TIMESTAMP")
        cursor.execute("UPDATE recipes SET updated_at = created_at WHERE updated_at IS NULL")
    if "is_public" not in _existing_cols:
        cursor.execute("ALTER TABLE recipes ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0")
    # training_verified — user-confirmed that this recipe is a correct extraction,
    # so its (image, recipe) pair is eligible for the image-ingestion eval set.
    if "training_verified" not in _existing_cols:
        cursor.execute(
            "ALTER TABLE recipes ADD COLUMN training_verified INTEGER NOT NULL DEFAULT 0"
        )
    # has_image — 1 when the user has uploaded a hero photo for this recipe.
    # The image bytes live on disk (config.RECIPE_IMAGES_DIR), not in the DB.
    if "has_image" not in _existing_cols:
        cursor.execute("ALTER TABLE recipes ADD COLUMN has_image INTEGER NOT NULL DEFAULT 0")

    # meal_plan_entries.google_event_id — the synced Google Calendar event id
    # (NULL until the entry is synced). Guarded; the table may not exist yet on
    # a brand-new db, but CREATE TABLE above runs first so it always does here.
    _mp_cols = {row[1] for row in cursor.execute("PRAGMA table_info(meal_plan_entries)").fetchall()}
    if "google_event_id" not in _mp_cols:
        cursor.execute("ALTER TABLE meal_plan_entries ADD COLUMN google_event_id TEXT")

    conn.commit()
    conn.close()
