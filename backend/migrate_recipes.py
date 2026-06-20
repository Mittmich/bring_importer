"""One-time migration: convert old flat-string recipe format to structured format.

Old format stored in recipe_json:
  recipeIngredient: List[str]   e.g. ["2 cups flour", "3 eggs"]
  recipeInstructions: List[str] e.g. ["Mix flour and eggs.", "Cook for 10 min."]

New format:
  ingredients: List[{amount, name}]
  instructions: List[{text, ingredients: List[int]}]

Usage:
  python migrate_recipes.py [--dry-run] [--limit N]

Flags:
  --dry-run   Print what would be changed without writing to the DB.
  --limit N   Only process the first N un-migrated recipes (useful for testing).

The script is idempotent: recipes that already have an "ingredients" key are skipped.
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure the backend package is importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).parent))

from api.config import OPENAI_API_KEY  # noqa: E402 (after sys.path patch)
from api.db import get_db_connection  # noqa: E402
from api.recipe_extraction import (  # noqa: E402
    _map_ingredients_to_instructions,
    _parse_ingredient_strings,
)


def migrate(dry_run: bool = False, limit: int | None = None) -> None:
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT uuid, recipe_json FROM recipes ORDER BY created_at ASC")
    rows = cursor.fetchall()

    migrated = 0
    skipped = 0
    errors = 0

    for row in rows:
        if limit is not None and migrated >= limit:
            break

        uuid = row["uuid"]
        try:
            data = json.loads(row["recipe_json"])
        except Exception:
            print(f"  [{uuid}] SKIP — could not parse recipe_json")
            skipped += 1
            continue

        # Already migrated
        if "ingredients" in data:
            skipped += 1
            continue

        raw_ingredients: list = data.get("recipeIngredient") or []
        raw_instructions: list = data.get("recipeInstructions") or []

        if not raw_ingredients:
            print(f"  [{uuid}] SKIP — no ingredients to migrate")
            skipped += 1
            continue

        print(
            f"  [{uuid}] '{data.get('name', '?')}' — {len(raw_ingredients)} ingredients, "
            f"{len(raw_instructions)} steps"
        )

        try:
            ingredients = _parse_ingredient_strings(raw_ingredients)
            instructions = _map_ingredients_to_instructions(ingredients, raw_instructions)
        except Exception as exc:
            print(f"    ERROR during LLM calls: {exc}")
            errors += 1
            continue

        # Build new blob
        new_data = {
            k: v
            for k, v in data.items()
            if k not in ("recipeIngredient", "recipeInstructions", "html_content")
        }
        new_data["ingredients"] = [ing.model_dump() for ing in ingredients]
        new_data["instructions"] = [step.model_dump() for step in instructions]

        if dry_run:
            print(
                f"    DRY-RUN: would write {len(ingredients)} ingredients, "
                f"{len(instructions)} steps"
            )
            for i, ing in enumerate(ingredients):
                print(f"      [{i}] {ing.amount!r} {ing.name!r}")
            for i, step in enumerate(instructions):
                print(f"      step {i}: uses {step.ingredients}")
        else:
            cursor.execute(
                "UPDATE recipes SET recipe_json = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE uuid = ?",
                (json.dumps(new_data), uuid),
            )
            conn.commit()
            print(f"    OK — {len(ingredients)} ingredients, {len(instructions)} steps written")

        migrated += 1

    conn.close()

    print(
        f"\nDone. Migrated: {migrated}, Skipped (already done / empty): {skipped}, "
        f"Errors: {errors}"
    )
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate recipes to structured format")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--limit", type=int, default=None, help="Max recipes to migrate")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run, limit=args.limit)
