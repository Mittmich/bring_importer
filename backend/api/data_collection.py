"""Optional training-data collection for the image-ingestion eval.

When ``COLLECT_TRAINING_DATA`` is enabled, every image import persists the
uploaded image alongside a snapshot of the *raw* model extraction, keyed by the
recipe's uuid. The user's later edits to that recipe (the stored ``recipe_json``)
become the verified ground-truth label at export time — no separate labelling
step. See ``.claude/plans/image-ingestion-eval.md``.

Design notes:
- Config is read at call time (via the ``config`` module) so it can be toggled
  per-process and monkeypatched in tests.
- Strictly best-effort: any failure here must never break a recipe import, so
  the whole body is guarded. Intended to run as a FastAPI background task.
"""

import base64
import json
import os
from datetime import datetime, timezone

import api.config as config
from api.models import Recipe

# Skip absurdly large uploads — a real recipe photo is well under this.
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def collect_image_extraction(
    recipe_uuid: str,
    image_base64: str,
    recipe: Recipe,
    model: str,
    prompt_version: str,
) -> None:
    """Persist ``(image, raw-extraction snapshot)`` for one image import.

    No-op unless ``config.COLLECT_TRAINING_DATA`` is set. Never raises.
    """
    if not config.COLLECT_TRAINING_DATA:
        return
    try:
        if "base64," in image_base64:
            image_base64 = image_base64.split("base64,")[1]
        raw = base64.b64decode(image_base64)
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            return

        base_dir = config.TRAINING_DATA_DIR
        images_dir = os.path.join(base_dir, "images")
        raw_dir = os.path.join(base_dir, "raw")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(raw_dir, exist_ok=True)

        with open(os.path.join(images_dir, f"{recipe_uuid}.jpg"), "wb") as f:
            f.write(raw)

        snapshot = {
            "uuid": recipe_uuid,
            "model": model,
            "prompt_version": prompt_version,
            "ts": datetime.now(timezone.utc).isoformat(),
            "raw_recipe": recipe.model_dump(),
        }
        with open(os.path.join(raw_dir, f"{recipe_uuid}.json"), "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception:
        # Best-effort only: collection must never break an import.
        return
