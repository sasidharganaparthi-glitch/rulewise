"""Centralized API router aggregating all v1 sub-routers (Phase 6, 7 & 8)."""

from fastapi import APIRouter

from backend.api.v1.endpoints_admin import router as admin_router
from backend.api.v1.endpoints_auth import router as auth_router
from backend.api.v1.endpoints_chat import router as chat_router
from backend.api.v1.endpoints_domains import router as domains_router
from backend.api.v1.endpoints_files import router as files_router
from backend.api.v1.endpoints_history import router as history_router
from backend.api.v1.endpoints_knowledge import router as knowledge_router
from backend.api.v1.endpoints_rules import router as rules_router
from backend.api.v1.endpoints_simulation import router as simulation_router
from backend.schemas.api import HealthResponse

api_v1_router = APIRouter()

# Mount feature sub-routers
api_v1_router.include_router(chat_router)
api_v1_router.include_router(files_router)
api_v1_router.include_router(domains_router)
api_v1_router.include_router(rules_router)
api_v1_router.include_router(simulation_router)
api_v1_router.include_router(history_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(knowledge_router)


@api_v1_router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="API v1 health verification",
    responses={
        200: {
            "description": "API v1 subsystem is healthy and operational",
            "model": HealthResponse,
        },
    },
)
def api_v1_health() -> HealthResponse:
    """Verify health and operational readiness of the API v1 namespace."""
    return HealthResponse(
        status="ok",
        project="RuleWise AI",
        phase=1,
    )
