"""``GET /health`` — liveness probe (no auth)."""

import time

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}
