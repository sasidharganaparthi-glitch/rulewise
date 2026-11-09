"""Endpoints for accessing decision history and detailed evaluation traces."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.core.security import get_current_user_optional
from backend.db.database import get_db_manager
from backend.db.repositories import EvaluationRepository
from backend.schemas.api import EvaluationHistoryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["Decision History & Traces"])


@router.get("", response_model=List[EvaluationHistoryResponse], summary="List past rule evaluations")
def list_history(
    domain_id: Optional[str] = Query(None, description="Filter evaluations by domain"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> List[EvaluationHistoryResponse]:
    """Retrieve historical decision records."""
    db = get_db_manager()
    eval_repo = EvaluationRepository(db)

    user_id = current_user.get("sub") if current_user else None
    evaluations = eval_repo.list_evaluations(domain_id=domain_id, user_id=user_id, limit=limit)
    return [EvaluationHistoryResponse(**ev) for ev in evaluations]


@router.get("/{evaluation_id}", response_model=EvaluationHistoryResponse, summary="Get full evaluation trace")
def get_evaluation_trace(evaluation_id: str) -> EvaluationHistoryResponse:
    """Retrieve full traceable explanation of an individual rule evaluation."""
    db = get_db_manager()
    eval_repo = EvaluationRepository(db)

    record = eval_repo.get_by_id(evaluation_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation record '{evaluation_id}' not found.",
        )
    return EvaluationHistoryResponse(**record)

