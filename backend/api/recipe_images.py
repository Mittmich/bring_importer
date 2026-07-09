"""On-disk storage for recipe hero images.

One JPEG per recipe, named ``{uuid}.jpg`` under ``config.RECIPE_IMAGES_DIR``.
The directory is created lazily on first write. Kept deliberately tiny — the
router owns auth/ownership; this module only moves bytes.

The client crops to landscape and downscales before upload, so the server just
validates the size and persists the bytes as-is.
"""

import base64
import os

import api.config as config

# A cropped, downscaled landscape JPEG is well under this; anything larger is
# almost certainly not the image we asked the client to send.
MAX_IMAGE_BYTES = 4 * 1024 * 1024


def _path_for(recipe_uuid: str) -> str:
    return os.path.join(config.RECIPE_IMAGES_DIR, f"{recipe_uuid}.jpg")


def decode_image(image_base64: str) -> bytes:
    """Decode a base64 (optionally data-URL) JPEG payload to raw bytes.

    Raises ``ValueError`` if the payload is empty, undecodable, or too large.
    """
    if "base64," in image_base64:
        image_base64 = image_base64.split("base64,", 1)[1]
    try:
        raw = base64.b64decode(image_base64, validate=True)
    except Exception as e:  # binascii.Error and friends
        raise ValueError("Image is not valid base64") from e
    if not raw:
        raise ValueError("Image is empty")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Image is too large")
    return raw


def save_image(recipe_uuid: str, raw: bytes) -> None:
    """Write the image bytes for ``recipe_uuid``, creating the dir if needed."""
    os.makedirs(config.RECIPE_IMAGES_DIR, exist_ok=True)
    with open(_path_for(recipe_uuid), "wb") as f:
        f.write(raw)


def image_path(recipe_uuid: str) -> str | None:
    """Return the on-disk path if an image exists for ``recipe_uuid``, else None."""
    path = _path_for(recipe_uuid)
    return path if os.path.exists(path) else None


def delete_image(recipe_uuid: str) -> None:
    """Remove the stored image for ``recipe_uuid``; no-op if there isn't one."""
    try:
        os.remove(_path_for(recipe_uuid))
    except FileNotFoundError:
        pass
