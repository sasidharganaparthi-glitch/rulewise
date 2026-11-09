"""Endpoints for domain management (official and user-defined custom domains)."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.core.security import get_current_user_optional, get_current_user_required, require_admin
from backend.db.database import get_db_manager
from backend.db.repositories import DomainRepository, RuleRepository
from backend.schemas.api import DomainCreateRequest, DomainResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/domains", tags=["Domain Management"])


@router.get("", response_model=List[DomainResponse], summary="List all domains")
def list_domains(
    is_official: Optional[bool] = Query(None, description="Filter by official status"),
    category: Optional[str] = Query(None, description="Filter by category"),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> List[DomainResponse]:
    """List available official and personal domains."""
    db = get_db_manager()
    dom_repo = DomainRepository(db)
    rule_repo = RuleRepository(db)

    user_id = current_user.get("sub") if current_user else None
    domains = dom_repo.list_domains(is_official=is_official, created_by=user_id, category=category)

    res = []
    for d in domains:
        rules = rule_repo.list_rules(domain_id=d["id"])
        d["rule_count"] = len(rules)
        res.append(DomainResponse(**d))
    return res


@router.get("/{domain_id_or_slug}", response_model=DomainResponse, summary="Get domain by ID or slug")
def get_domain(domain_id_or_slug: str) -> DomainResponse:
    """Retrieve details and schema fields of a domain."""
    db = get_db_manager()
    dom_repo = DomainRepository(db)
    rule_repo = RuleRepository(db)

    domain = dom_repo.get_by_id(domain_id_or_slug) or dom_repo.get_by_slug(domain_id_or_slug)
    if not domain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Domain '{domain_id_or_slug}' not found.")

    rules = rule_repo.list_rules(domain_id=domain["id"])
    domain["rule_count"] = len(rules)
    return DomainResponse(**domain)


@router.post("", response_model=DomainResponse, status_code=status.HTTP_201_CREATED, summary="Create a new custom domain")
def create_domain(
    req: DomainCreateRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> DomainResponse:
    """Create a new domain. Guest users can create domains; registered users own them permanently."""
    db = get_db_manager()
    dom_repo = DomainRepository(db)

    # Check for existing slug
    existing = dom_repo.get_by_slug(req.slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A domain with slug '{req.slug}' already exists. Please choose a unique slug.",
        )

    user_id = current_user.get("sub") if current_user else "guest"
    is_official = False
    if current_user and current_user.get("role") == "admin":
        # Admins can optionally create official domains
        is_official = False

    schema_dicts = [f.model_dump() for f in req.schema_fields]

    created = dom_repo.create_domain(
        name=req.name,
        slug=req.slug,
        description=req.description,
        category=req.category,
        is_official=is_official,
        schema_fields=schema_dicts,
        created_by=user_id,
    )
    created["rule_count"] = 0
    return DomainResponse(**created)


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete custom domain")
def delete_domain(
    domain_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> None:
    """Delete a user-created domain. Official domains cannot be deleted through this endpoint."""
    db = get_db_manager()
    dom_repo = DomainRepository(db)

    domain = dom_repo.get_by_id(domain_id)
    if not domain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found.")

    if domain["is_official"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Official rule libraries are protected and cannot be deleted.",
        )

    user_id = current_user.get("sub") if current_user else None
    deleted = dom_repo.delete_domain(domain_id, requesting_user_id=user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this domain.",
        )

