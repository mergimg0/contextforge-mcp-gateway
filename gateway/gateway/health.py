"""Health check endpoints for Docker/K8s readiness probes."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "mcp-gateway"}


@router.get("/ready")
async def ready():
    return {"status": "ready", "service": "mcp-gateway"}
