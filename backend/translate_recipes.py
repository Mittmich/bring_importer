"""One-off backfill: detect the language of existing recipes and translate them.

Recipes created before language support have no ``inLanguage`` and no
``translations``. For each recipe this script:

  1. Detects the base language if it is unknown (one small LLM call) and stores
     it as ``inLanguage`` — only for languages the app supports.
  2. Translates the base content into every target language the recipe is
     missing (one LLM call per language) and stores it under ``translations``.

Usage (inside the backend container, or ``uv run`` from backend/):
  python translate_recipes.py [--inspect | --dry-run] [--detect-only] [--redetect]
                              [--limit N] [--languages en,de] [--uuid UUID]

Flags:
  --inspect       Read-only: print each recipe's recorded language, its
                  translations and a sample of their text. No LLM calls.
  --dry-run       Make no LLM calls and no writes; report what would be done.
  --detect-only   Only detect and store base languages; don't translate.
  --redetect      Also re-detect recipes whose language is already recorded,
                  correcting wrong labels (and dropping a "translation" into the
                  corrected language, which is just a copy of the original).
  --limit N       Stop after N recipes that needed work.
  --languages     Comma-separated target languages (default: all supported).
  --uuid UUID     Process a single recipe.

Idempotent: languages already detected and translations already present are
skipped, so it is safe to re-run (e.g. after a partial failure). Each recipe is
committed on its own, and a recipe edited while it was being translated is
left alone (reported as "changed meanwhile") rather than overwritten.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure the backend package is importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).parent))

from api import db as api_db  # noqa: E402 (after sys.path patch)
from api.config import OPENAI_API_KEY  # noqa: E402
from api.i18n import SUPPORTED_LANGUAGES, normalize_language  # noqa: E402
from api.translation import (  # noqa: E402
    TranslationError,
    add_translation,
    detect_recipe_language,
    recipe_content,
    set_base_language,
)


def parse_languages(value: Optional[str]) -> List[str]:
    """``"en, de"`` → ``["en", "de"]``; rejects unsupported codes."""
    if not value:
        return list(SUPPORTED_LANGUAGES)
    langs: List[str] = []
    for raw in value.split(","):
        code = normalize_language(raw)
        if code is None:
            raise SystemExit(f"Unsupported language '{raw.strip()}'")
        if code not in langs:
            langs.append(code)
    return langs


def missing_targets(stored: Dict[str, Any], targets: List[str]) -> List[str]:
    """Target languages this recipe has no content in yet."""
    base = normalize_language(stored.get("inLanguage"))
    have = set((stored.get("translations") or {}).keys())
    return [t for t in targets if t != base and t not in have]


def _snippet(variant: Dict[str, Any]) -> str:
    """First step + first ingredient names — enough to eyeball the language."""
    steps = variant.get("instructions") or []
    step = (steps[0].get("text", "") if steps and isinstance(steps[0], dict) else "") or ""
    names = [str(i.get("name", "")) for i in (variant.get("ingredients") or [])[:3]]
    step = " ".join(step.split())
    return f"ingredients: {', '.join(names)!s} | step 1: {step[:90]}"


def inspect(stored: Dict[str, Any], label: str) -> None:
    translations = stored.get("translations") or {}
    print(
        f"  {label} base={stored.get('inLanguage') or '?'} "
        f"translations={','.join(translations) or '-'}"
    )
    print(f"      base: {_snippet(recipe_content(stored))}")
    for code, variant in translations.items():
        print(f"      {code}: {variant.get('name')!r} {_snippet(variant)}")


def run(
    dry_run: bool = False,
    detect_only: bool = False,
    redetect: bool = False,
    inspect_only: bool = False,
    limit: Optional[int] = None,
    targets: Optional[List[str]] = None,
    only_uuid: Optional[str] = None,
) -> Dict[str, int]:
    targets = targets or list(SUPPORTED_LANGUAGES)
    stats = {
        "processed": 0,
        "detected": 0,
        "corrected": 0,
        "translations": 0,
        "complete": 0,
        "changed_meanwhile": 0,
        "errors": 0,
    }

    conn = api_db.get_db_connection()
    cursor = conn.cursor()
    sql = "SELECT uuid, title, recipe_json, updated_at FROM recipes"
    params: tuple = ()
    if only_uuid:
        sql += " WHERE uuid = ?"
        params = (only_uuid,)
    rows = cursor.execute(sql + " ORDER BY created_at ASC", params).fetchall()
    print(f"{len(rows)} recipe(s); target languages: {', '.join(targets)}")

    for row in rows:
        if limit is not None and stats["processed"] >= limit:
            print(f"Reached --limit {limit}.")
            break

        uuid = row["uuid"]
        label = f"[{uuid}] {row['title']!r}"
        try:
            stored = json.loads(row["recipe_json"])
        except Exception:
            print(f"  {label} SKIP — could not parse recipe_json")
            stats["errors"] += 1
            continue

        if inspect_only:
            inspect(stored, label)
            continue

        base = normalize_language(stored.get("inLanguage"))
        missing = missing_targets(stored, targets)
        needs_detect = (base is None and bool(missing)) or redetect
        needs_translate = bool(missing) and not detect_only
        if not needs_detect and not needs_translate:
            stats["complete"] += 1
            continue

        stats["processed"] += 1
        if dry_run:
            plan = []
            if needs_detect:
                plan.append("detect language")
            if needs_translate:
                plan.append(f"translate → {', '.join(missing)}")
            print(f"  {label} would {' then '.join(plan)}")
            continue

        before = json.dumps(stored, sort_keys=True)
        try:
            if needs_detect:
                raw = detect_recipe_language(stored)
                detected = normalize_language(raw)
                if base is None:
                    print(f"  {label} detected: {raw or 'unknown'}")
                    if detected:
                        stored["inLanguage"] = detected
                        stats["detected"] += 1
                elif detected and detected != base:
                    print(f"  {label} corrected language: {base} → {detected}")
                    set_base_language(stored, detected)
                    stats["corrected"] += 1
                missing = missing_targets(stored, targets)

            if not detect_only:
                for target in missing:
                    lang_before = stored.get("inLanguage")
                    if add_translation(stored, target):
                        stats["translations"] += 1
                        print(f"  {label} translated → {target}")
                    elif stored.get("inLanguage") != lang_before:
                        # The translator found the text already in `target`.
                        print(
                            f"  {label} already in {target} — "
                            f"corrected language: {lang_before or '?'} → {target}"
                        )
                        stats["corrected"] += 1
        except TranslationError as e:
            # Keep whatever succeeded before the failure (e.g. a detection or an
            # earlier language); the next run picks up the rest.
            print(f"  {label} ERROR — {e}")
            stats["errors"] += 1

        if json.dumps(stored, sort_keys=True) == before:
            continue

        # Don't clobber an edit that landed while the LLM calls were running.
        current = cursor.execute(
            "SELECT updated_at FROM recipes WHERE uuid = ?", (uuid,)
        ).fetchone()
        if current is None or current["updated_at"] != row["updated_at"]:
            print(f"  {label} SKIP write — recipe changed meanwhile; re-run to retry")
            stats["changed_meanwhile"] += 1
            continue
        cursor.execute(
            "UPDATE recipes SET recipe_json = ?, updated_at = ? WHERE uuid = ?",
            (json.dumps(stored), datetime.now(timezone.utc).isoformat(), uuid),
        )
        conn.commit()

    conn.close()
    if inspect_only:
        return stats
    verb = "would process" if dry_run else "processed"
    print(
        f"\nDone. {verb}: {stats['processed']}, already complete: {stats['complete']}, "
        f"languages detected: {stats['detected']}, corrected: {stats['corrected']}, "
        f"translations added: {stats['translations']}, "
        f"changed meanwhile: {stats['changed_meanwhile']}, errors: {stats['errors']}"
    )
    return stats


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Detect recipe languages and add translations")
    parser.add_argument("--inspect", action="store_true", help="Read-only: show languages + text")
    parser.add_argument("--dry-run", action="store_true", help="No LLM calls, no writes")
    parser.add_argument("--redetect", action="store_true", help="Re-check recorded languages")
    parser.add_argument("--detect-only", action="store_true", help="Only detect base languages")
    parser.add_argument("--limit", type=int, default=None, help="Max recipes to process")
    parser.add_argument("--languages", default=None, help="Comma-separated targets, e.g. en,de")
    parser.add_argument("--uuid", default=None, help="Process a single recipe")
    args = parser.parse_args(argv)

    if not (args.dry_run or args.inspect) and not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
        return 1

    stats = run(
        dry_run=args.dry_run,
        detect_only=args.detect_only,
        redetect=args.redetect,
        inspect_only=args.inspect,
        limit=args.limit,
        targets=parse_languages(args.languages),
        only_uuid=args.uuid,
    )
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
