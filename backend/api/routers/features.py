"""Feature-flag endpoints.

- ``GET /features`` — auth; the current flags, e.g. ``{"planner": "weekly"}``.
- ``PUT /admin/features`` — admin; change flags, returns the new flags.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api import features
from api.auth import get_current_admin, get_current_user
from api.models import UserInDB

router = APIRouter(tags=["features"])


class FeaturesUpdate(BaseModel):
    planner: Optional[Literal["weekly", "menus"]] = None


@router.get("/features")
async def read_features(_user: UserInDB = Depends(get_current_user)):  # noqa: B008
    return features.all_flags()


@router.put("/admin/features")
async def update_features(
    body: FeaturesUpdate,
    _admin: UserInDB = Depends(get_current_admin),  # noqa: B008
):
    if body.planner is not None:
        features.set_planner(body.planner)
    return features.all_flags()
