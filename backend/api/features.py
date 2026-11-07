"""Global feature flags, stored in ``app_settings`` and switchable by admins.

Flags:

- ``planner``: which planner the app shows in its "Plan" area — ``weekly`` (the
  weekly meal plan) or ``menus`` (menus with prep planning). Until an admin sets
  it, the default comes from ``PLANNER_MODE`` (env), falling back to ``weekly``.
  The flag only switches the UI; both features keep their data.
"""

from typing import Dict

from api import config, db

PLANNER_MODES = ("weekly", "menus")


def _default_planner() -> str:
    return config.PLANNER_MODE if config.PLANNER_MODE in PLANNER_MODES else "weekly"


def get_planner() -> str:
    conn = db.get_db_connection()
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key = 'planner'").fetchone()
    finally:
        conn.close()
    if row is not None and row["value"] in PLANNER_MODES:
        return row["value"]
    return _default_planner()


def set_planner(mode: str) -> None:
    if mode not in PLANNER_MODES:
        raise ValueError(f"planner must be one of {PLANNER_MODES}")
    conn = db.get_db_connection()
    try:
        conn.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES ('planner', ?, "
            "CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = CURRENT_TIMESTAMP",
            (mode,),
        )
        conn.commit()
    finally:
        conn.close()


def all_flags() -> Dict[str, str]:
    return {"planner": get_planner()}
