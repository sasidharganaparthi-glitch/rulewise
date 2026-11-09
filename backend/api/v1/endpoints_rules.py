"""Endpoints for authoring, staging, validating, testing, and retrieving rules."""

import logging
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.core.exceptions import FactResolutionError, MalformedRuleError
from backend.core.security import get_current_user_optional, require_admin
from backend.db.database import get_db_manager
from backend.db.repositories import DomainRepository, RuleRepository
from backend.engine.condition_evaluator import evaluate_condition
from backend.engine.inference_engine import apply_rule, extract_derived_facts, extract_referenced_fact_paths
from backend.engine.working_memory import WorkingMemory
from backend.schemas.api import (
    RuleCreateRequest,
    RuleTestRequest,
    RuleTestResponse,
    RuleUpdateRequest,
    RuleValidateRequest,
    RuleValidateResponse,
)
from backend.schemas.rule import Rule, RuleConsequence, RuleStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rules", tags=["Rule Authoring & Management"])


def _validate_rule_structure(condition_data: Dict[str, Any], consequence_data: Dict[str, Any]) -> Tuple[List[str], List[str], List[str]]:
    """Validate condition and consequence schemas without saving."""
    errors = []
    warnings = []
    referenced_facts = []

    if not condition_data:
        errors.append("Rule condition cannot be empty.")
    if not consequence_data:
        errors.append("Rule consequence cannot be empty.")
    if "action" not in consequence_data or not consequence_data["action"]:
        errors.append("Consequence requires an 'action' string.")

    try:
        referenced_facts = extract_referenced_fact_paths(condition_data)
        if not referenced_facts:
            warnings.append("No specific facts referenced in condition tree.")
    except Exception as exc:
        errors.append(f"Condition structure is invalid: {exc}")

    # Check for disallowed dynamic keys
    raw_str = str(condition_data) + str(consequence_data)
    for forbidden in ("__", "import", "exec", "eval", "os.", "sys.", "subprocess"):
        if forbidden in raw_str:
            errors.append(f"Security violation: dangerous token '{forbidden}' detected in rule definition.")

    return errors, warnings, referenced_facts


@router.get("", response_model=List[Dict[str, Any]], summary="List rules")
def list_rules(
    domain_id: Optional[str] = Query(None, description="Filter rules by domain ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (active/staged/retired)"),
    is_official: Optional[bool] = Query(None, description="Filter by official status"),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> List[Dict[str, Any]]:
    """Retrieve rules according to filters."""
    db = get_db_manager()
    rule_repo = RuleRepository(db)
    user_id = current_user.get("sub") if current_user else None
    return rule_repo.list_rules(
        domain_id=domain_id,
        status=status_filter,
        is_official=is_official,
        created_by=user_id,
    )


@router.get("/{rule_id}", response_model=Dict[str, Any], summary="Get rule by ID")
def get_rule(rule_id: str) -> Dict[str, Any]:
    """Retrieve full details of a specific rule."""
    db = get_db_manager()
    rule_repo = RuleRepository(db)
    rule = rule_repo.get_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule '{rule_id}' not found.")
    return rule


@router.post("", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED, summary="Create a new rule")
def create_rule(
    req: RuleCreateRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    """Create a validated rule in a domain.

    Enforces strict structural validation and security policies.
    Ordinary users cannot add rules to official system collections.
    """
    db = get_db_manager()
    dom_repo = DomainRepository(db)
    rule_repo = RuleRepository(db)

    domain = dom_repo.get_by_id(req.domain_id)
    if not domain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Target domain '{req.domain_id}' does not exist.")

    is_admin = bool(current_user and current_user.get("role") == "admin")
    if domain["is_official"] and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Official rule libraries can only be modified by system administrators.",
        )

    # Validate condition & consequence
    errors, warnings, _ = _validate_rule_structure(req.condition, req.consequence)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Rule validation failed: {'; '.join(errors)}",
        )

    user_id = current_user.get("sub") if current_user else "guest"
    is_official = domain["is_official"] and is_admin

    created = rule_repo.create_rule(
        domain_id=req.domain_id,
        name=req.name,
        description=req.description,
        priority=req.priority,
        status=req.status,
        is_official=is_official,
        condition=req.condition,
        consequence=req.consequence,
        metadata=req.metadata,
        created_by=user_id,
    )
    return created


@router.put("/{rule_id}", response_model=Dict[str, Any], summary="Update existing rule")
def update_rule(
    rule_id: str,
    req: RuleUpdateRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    """Update rule definition. Protected if rule belongs to official library."""
    db = get_db_manager()
    rule_repo = RuleRepository(db)
    existing = rule_repo.get_by_id(rule_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule '{rule_id}' not found.")

    is_admin = bool(current_user and current_user.get("role") == "admin")
    if existing["is_official"] and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Official rules cannot be modified by non-admin users.",
        )

    if req.condition is not None or req.consequence is not None:
        c_cond = req.condition if req.condition is not None else existing["condition"]
        c_cons = req.consequence if req.consequence is not None else existing["consequence"]
        errors, _, _ = _validate_rule_structure(c_cond, c_cons)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Rule validation failed: {'; '.join(errors)}",
            )

    updated = rule_repo.update_rule(
        rule_id=rule_id,
        name=req.name,
        description=req.description,
        priority=req.priority,
        status=req.status,
        condition=req.condition,
        consequence=req.consequence,
        metadata=req.metadata,
    )
    return updated  # type: ignore[return-value]


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete rule")
def delete_rule(
    rule_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> None:
    """Delete a rule."""
    db = get_db_manager()
    rule_repo = RuleRepository(db)
    existing = rule_repo.get_by_id(rule_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule '{rule_id}' not found.")

    is_admin = bool(current_user and current_user.get("role") == "admin")
    if existing["is_official"] and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Official rules cannot be deleted.",
        )

    rule_repo.delete_rule(rule_id)


@router.post("/validate", response_model=RuleValidateResponse, summary="Validate rule syntax and conditions")
def validate_rule(req: RuleValidateRequest) -> RuleValidateResponse:
    """Validate a rule structure prior to persistence."""
    errors, warnings, referenced = _validate_rule_structure(req.condition, req.consequence)
    return RuleValidateResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        referenced_facts=referenced,
    )


@router.post("/test", response_model=RuleTestResponse, summary="Test rule against hypothetical facts")
def test_rule(req: RuleTestRequest) -> RuleTestResponse:
    """Execute a single rule against a given facts dictionary and report whether it fires."""
    try:
        rule_data = req.rule
        rule_obj = Rule(
            id=rule_data.get("id", "TEST_RULE"),
            name=rule_data.get("name", "Test Rule"),
            description=rule_data.get("description", ""),
            priority=rule_data.get("priority", 50),
            status=RuleStatus(rule_data.get("status", "active")),
            condition=rule_data["condition"],
            consequence=RuleConsequence(**rule_data["consequence"]),
            metadata=rule_data.get("metadata", {}),
        )

        wm = WorkingMemory()
        for k, v in req.facts.items():
            wm.add_fact(k, v)

        res = apply_rule(rule_obj, wm)
        return RuleTestResponse(
            matched=res.matched,
            derived_facts=res.derived_facts,
        )
    except Exception as exc:
        return RuleTestResponse(
            matched=False,
            derived_facts={},
            errors=str(exc),
        )
