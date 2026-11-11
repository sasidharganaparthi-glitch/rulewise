"""Endpoints for accessing persistent decision history, explanations, and trace evidence.

Strict user data isolation: Normal users can only access their own decision history.
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.core.security import get_current_user_optional, get_current_user_required
from backend.db.database import get_db_manager
from backend.db.repositories import EvaluationRepository
from backend.schemas.api import EvaluationHistoryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["Decision History & Traces"])


@router.get("", response_model=List[EvaluationHistoryResponse], summary="List past rule evaluations for user")
@router.get("/evaluations", response_model=List[EvaluationHistoryResponse], summary="List past rule evaluations for user (alias)")
def list_history(
    domain_id: Optional[str] = Query(None, description="Filter evaluations by domain"),
    decision: Optional[str] = Query(None, description="Filter by decision (Approved, Rejected, etc.)"),
    search: Optional[str] = Query(None, description="Search term in facts or decision"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    offset: int = Query(0, ge=0),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> List[EvaluationHistoryResponse]:
    """Retrieve historical decision records with strict user isolation."""
    db = get_db_manager()
    eval_repo = EvaluationRepository(db)

    # Determine user scope
    user_id = None
    if current_user:
        is_admin = (current_user.get("role") == "admin")
        if not is_admin:
            user_id = current_user.get("sub")
    else:
        # Unauthenticated / guest without token sees no private history
        return []

    evaluations = eval_repo.list_evaluations(
        domain_id=domain_id,
        user_id=user_id,
        search=search,
        decision=decision,
        limit=limit,
        offset=offset,
    )
    return [EvaluationHistoryResponse(**ev) for ev in evaluations]


@router.get("/{evaluation_id}", response_model=EvaluationHistoryResponse, summary="Get full evaluation trace")
def get_evaluation_trace(
    evaluation_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> EvaluationHistoryResponse:
    """Retrieve full traceable explanation of an individual rule evaluation with access verification."""
    db = get_db_manager()
    eval_repo = EvaluationRepository(db)

    record = eval_repo.get_by_id(evaluation_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation record '{evaluation_id}' not found.",
        )

    # Verify authorization
    if record.get("user_id"):
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required to view this decision.")
        is_admin = (current_user.get("role") == "admin")
        if not is_admin and record["user_id"] != current_user.get("sub"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this decision trace.")

    return EvaluationHistoryResponse(**record)


@router.delete("/{evaluation_id}", summary="Delete decision from personal history")
def delete_evaluation(
    evaluation_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_required),
) -> Dict[str, Any]:
    """Remove a decision evaluation from history."""
    db = get_db_manager()
    eval_repo = EvaluationRepository(db)

    record = eval_repo.get_by_id(evaluation_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision record not found.")

    is_admin = (current_user.get("role") == "admin")
    if not is_admin and record.get("user_id") != current_user.get("sub"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete decisions belonging to other accounts.")

    eval_repo.delete_evaluation(evaluation_id, user_id=None if is_admin else current_user.get("sub"))
    return {"status": "deleted", "evaluation_id": evaluation_id}
