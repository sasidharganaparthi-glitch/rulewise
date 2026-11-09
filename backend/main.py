"""RuleWise AI - Main FastAPI Application.

Explainable hybrid Neuro-Symbolic AI Rule Engine and Advisory Assistant.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.v1.router import api_v1_router
from backend.core.config import get_settings
from backend.core.exceptions import RuleWiseError
from backend.db.database import get_db_manager
from backend.db.seeder import seed_database
from backend.schemas.api import ErrorResponse, HealthResponse

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for database initialization and seeding."""
    try:
        db = get_db_manager()
        seed_database(db)
        logger.info("RuleWise AI initialized and database verified.")
    except Exception as exc:
        logger.error("Failed to initialize database during startup: %s", exc)
    yield


app = FastAPI(
    title="RuleWise AI",
    description=(
        "Explainable hybrid Neuro-Symbolic AI Rule Engine and Advisory Assistant. "
        "Integrates deterministic forward chaining symbolic reasoning with conversational AI."
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "Health",
            "description": "System health and liveness verification endpoints.",
        },
        {
            "name": "Chat & Advisory",
            "description": "Natural language query processing, neuro-symbolic advisory, and provider status.",
        },
    ],
)

# Enable CORS for web frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v1 router
app.include_router(api_v1_router, prefix="/api/v1")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard HTTP exceptions with clean details."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RuleWiseError)
async def rulewise_error_handler(request: Request, exc: RuleWiseError) -> JSONResponse:
    """Handle domain-specific RuleWise errors safely without exposing internals."""
    logger.error("Domain RuleWiseError encountered at %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": str(exc),
            "error_code": exc.__class__.__name__,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected server errors without leaking tracebacks or sensitive data."""
    logger.exception("Unhandled server exception at %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred while processing the request.",
            "error_code": "INTERNAL_SERVER_ERROR",
        },
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Root health check",
    responses={
        200: {
            "description": "Service is healthy and operational",
            "model": HealthResponse,
        },
    },
)
def health_check() -> Dict[str, Any]:
    """Health check endpoint for verification."""
    return {
        "status": "ok",
        "project": "RuleWise AI",
        "phase": 1,
    }


# Static file serving & Frontend Web UI mount (Phase 8)
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    css_dir = os.path.join(frontend_dir, "css")
    js_dir = os.path.join(frontend_dir, "js")
    assets_dir = os.path.join(frontend_dir, "assets")
    if os.path.exists(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if os.path.exists(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        """Serve the RuleWise AI frontend web application."""
        return FileResponse(os.path.join(frontend_dir, "index.html"))
