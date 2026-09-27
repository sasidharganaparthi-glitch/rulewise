"""RuleWise AI - Main FastAPI Application.

Phase 1 development skeleton providing base application setup and health verification.
"""

from typing import Any, Dict
from fastapi import FastAPI

app = FastAPI(
    title="RuleWise AI",
    description="Explainable hybrid Neuro-Symbolic AI Rule Engine and Advisory Assistant",
    version="0.1.0",
)


@app.get("/health", tags=["Health"])
def health_check() -> Dict[str, Any]:
    """Health check endpoint for Phase 1 verification."""
    return {
        "status": "ok",
        "project": "RuleWise AI",
        "phase": 1,
    }
