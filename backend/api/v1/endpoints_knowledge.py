"""Endpoints for knowledge statistics, data import/export, and knowledge base entities."""

import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from backend.core.security import get_current_user_optional
from backend.db.database import get_db_manager
from backend.db.repositories import DomainRepository, EvaluationRepository, RuleRepository
from backend.nlp.provider import get_language_model_provider
from backend.schemas.api import KnowledgeStatsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base & Statistics"])


@router.get("/stats", response_model=KnowledgeStatsResponse, summary="System-wide statistics")
def get_stats() -> KnowledgeStatsResponse:
    """Retrieve operational and domain statistics."""
    db = get_db_manager()
    dom_repo = DomainRepository(db)
    rule_repo = RuleRepository(db)
    eval_repo = EvaluationRepository(db)

    domains = dom_repo.list_domains()
    all_rules = rule_repo.list_rules()
    official_rules = [r for r in all_rules if r.get("is_official")]
    custom_rules = [r for r in all_rules if not r.get("is_official")]
    evaluations = eval_repo.list_evaluations(limit=1000)

    provider = get_language_model_provider()
    ai_status = "Available" if provider.is_available() else "Offline Fallback"

    return KnowledgeStatsResponse(
        domains_count=len(domains),
        official_rules_count=len(official_rules),
        custom_rules_count=len(custom_rules),
        total_rules_count=len(all_rules),
        evaluations_count=len(evaluations),
        ai_status=ai_status,
    )


@router.get("/export", summary="Export domain and rules to JSON")
def export_domain(domain_id: str) -> Dict[str, Any]:
    """Export a domain along with all associated rules as portable JSON."""
    db = get_db_manager()
    dom_repo = DomainRepository(db)
    rule_repo = RuleRepository(db)

    domain = dom_repo.get_by_id(domain_id) or dom_repo.get_by_slug(domain_id)
    if not domain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found.")

    rules = rule_repo.list_rules(domain_id=domain["id"])
    return {
        "domain": domain,
        "rules": rules,
        "exported_at": "2026-11-09T22:00:00Z",
        "format_version": "1.0",
    }


@router.post("/import", status_code=status.HTTP_201_CREATED, summary="Import domain and rules from JSON")
def import_domain(
    payload: Dict[str, Any],
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    """Import a custom domain and rules from a JSON structure."""
    if "domain" not in payload or "rules" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed import package. Expected 'domain' and 'rules' objects.",
        )

    db = get_db_manager()
    dom_repo = DomainRepository(db)
    rule_repo = RuleRepository(db)

    d_info = payload["domain"]
    user_id = current_user.get("sub") if current_user else "guest"

    # Ensure unique slug
    base_slug = d_info.get("slug", "imported-domain")
    slug = base_slug
    idx = 1
    while dom_repo.get_by_slug(slug):
        slug = f"{base_slug}-{idx}"
        idx += 1

    created_domain = dom_repo.create_domain(
        name=d_info.get("name", "Imported Domain"),
        slug=slug,
        description=d_info.get("description", ""),
        category=d_info.get("category", "general"),
        is_official=False,
        schema_fields=d_info.get("schema_fields", []),
        created_by=user_id,
    )

    imported_count = 0
    for r in payload["rules"]:
        try:
            rule_repo.create_rule(
                domain_id=created_domain["id"],
                name=r.get("name", "Imported Rule"),
                description=r.get("description", ""),
                priority=r.get("priority", 50),
                status=r.get("status", "active"),
                is_official=False,
                condition=r["condition"],
                consequence=r["consequence"],
                metadata=r.get("metadata", {}),
                created_by=user_id,
            )
            imported_count += 1
        except Exception as exc:
            logger.warning("Skipping invalid rule in import: %s", exc)

    return {
        "status": "imported",
        "domain_id": created_domain["id"],
        "slug": slug,
        "rules_imported": imported_count,
    }


@router.post("/upload", summary="Upload structured document to extract facts")
async def upload_document(
    request: Request,
    filename: Optional[str] = Header(None, alias="X-Filename"),
) -> Dict[str, Any]:
    """Upload and validate a file (JSON, TXT, CSV) for knowledge facts."""
    content_bytes = await request.body()
    if not content_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request body cannot be empty.")

    file_name = filename or "document.json"
    allowed = (".json", ".txt", ".csv")
    if not any(file_name.lower().endswith(ext) for ext in allowed):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload .json, .txt, or .csv files.",
        )

    if len(content_bytes) > 5 * 1024 * 1024:  # 5 MB limit
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum permitted limit (5MB).",
        )

    try:
        text_content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be encoded in UTF-8 text.",
        )

    extracted_facts = {}
    if file_name.lower().endswith(".json"):
        try:
            parsed = json.loads(text_content)
            if isinstance(parsed, dict):
                extracted_facts = parsed
            elif isinstance(parsed, list):
                extracted_facts = {"records": parsed}
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON content: {exc}")
    else:
        # Simple line-based text or CSV preview
        lines = [line.strip() for line in text_content.splitlines() if line.strip()]
        extracted_facts = {"line_count": len(lines), "sample_lines": lines[:5]}

    return {
        "filename": file_name,
        "size_bytes": len(content_bytes),
        "facts_preview": extracted_facts,
        "message": "File verified and parsed successfully.",
    }
