"""API endpoints for natural language queries and interactive advisory sessions (Phase 6, 7 & 8)."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.core.security import get_current_user_optional
from backend.db.database import get_db_manager
from backend.db.repositories import ConversationRepository, DomainRepository, EvaluationRepository
from backend.nlp.orchestrator import RuleWiseOrchestrator
from backend.nlp.provider import get_language_model_provider
from backend.schemas.api import ErrorResponse, ProviderStatusResponse
from backend.schemas.query import ChatRequest, ChatResponse, UserIntent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat & Advisory"])


def get_orchestrator() -> RuleWiseOrchestrator:
    """Dependency provider for RuleWiseOrchestrator."""
    return RuleWiseOrchestrator()


@router.post(
    "",
    response_model=ChatResponse,
    summary="Process user natural language inquiry",
    responses={
        200: {
            "description": "Evaluation or conversational response successfully generated",
            "model": ChatResponse,
        },
        422: {
            "description": "Validation error for malformed request payload",
        },
        500: {
            "description": "Internal server error safely handled without exposing sensitive internals",
            "model": ErrorResponse,
        },
    },
)
def chat_endpoint(
    request: ChatRequest,
    orchestrator: RuleWiseOrchestrator = Depends(get_orchestrator),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> ChatResponse:
    """Evaluate natural language user inquiry.

    Dispatches GENERAL_CHAT inquiries through conversational guidance and
    RULE_QUERY inquiries strictly through the deterministic symbolic reasoning engine.
    Never allows the language model to override deterministic rule engine results.
    """
    try:
        db = get_db_manager()
        conv_repo = ConversationRepository(db)
        eval_repo = EvaluationRepository(db)
        dom_repo = DomainRepository(db)
        user_id = current_user.get("sub") if current_user else None

        conv_id = request.conversation_id
        past_messages: List[Dict[str, Any]] = []
        if conv_id:
            try:
                past_messages = conv_repo.get_messages(conv_id)
            except Exception:
                past_messages = []

        effective_message = request.message
        if request.attachments:
            attachment_notes = []
            for att in request.attachments:
                fname = att.get("name", "attachment")
                content = att.get("content") or att.get("summary") or ""
                if content:
                    attachment_notes.append(f"--- [Attached File: {fname}] ---\n{content}")
            if attachment_notes:
                effective_message = f"{request.message}\n\n" + "\n\n".join(attachment_notes)

        try:
            response = orchestrator.process_message(
                effective_message,
                conversation_history=past_messages,
            )
        except TypeError as type_err:
            if "conversation_history" in str(type_err):
                response = orchestrator.process_message(effective_message)
            else:
                raise

        # Persist conversation & messages if requested or user active
        try:
            title = request.message[:40] + ("..." if len(request.message) > 40 else "")
            if not conv_id:
                new_conv = conv_repo.create_conversation(title=title, user_id=user_id)
                conv_id = new_conv["id"]
            else:
                conv_repo.ensure_conversation(conversation_id=conv_id, title=title, user_id=user_id)

            conv_repo.add_message(
                conversation_id=conv_id,
                sender="user",
                content=request.message,
            )
            conv_repo.add_message(
                conversation_id=conv_id,
                sender="assistant",
                content=response.message,
                intent=response.intent.value if hasattr(response.intent, "value") else str(response.intent),
                symbolic_result=response.symbolic_result,
                explanation=response.explanation,
            )

            # Record evaluation in history if a deterministic result was reached
            if response.symbolic_result:
                domain_id = request.domain_id or "dom_academic"
                if not dom_repo.get_by_id(domain_id):
                    domain_id = "dom_academic"
                eval_repo.record_evaluation(
                    domain_id=domain_id,
                    input_facts=response.symbolic_result.get("initial_facts", {}),
                    conclusion_reached=bool(response.symbolic_result.get("conclusion_reached")),
                    final_decision=response.symbolic_result.get("decision", "Evaluated"),
                    fired_rules=response.symbolic_result.get("fired_rule_ids", []),
                    derived_facts=response.symbolic_result.get("derived_facts", {}),
                    explanation=response.explanation or {},
                    user_id=user_id,
                )
        except Exception as persist_err:
            logger.warning("Failed to persist conversation trace (non-fatal): %s", persist_err)

        return response
    except Exception as exc:
        logger.exception("Unexpected error processing chat message: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the inquiry. Please try again later.",
        )


@router.get(
    "/status",
    response_model=ProviderStatusResponse,
    summary="Check NLP and language provider status",
    responses={
        200: {
            "description": "Provider readiness and symbolic engine status safely reported",
            "model": ProviderStatusResponse,
        },
    },
)
def chat_status_endpoint() -> ProviderStatusResponse:
    """Return status of NLP provider, fallback readiness, and symbolic engine.

    Never exposes API keys, credentials, environment secrets, or internal stack traces.
    """
    provider = get_language_model_provider()
    return ProviderStatusResponse(
        status="operational",
        provider_class=provider.__class__.__name__,
        provider_available=provider.is_available(),
        symbolic_engine="operational",
        fallback_ready=True,
    )


@router.get("/conversations", summary="List chat conversation sessions")
def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> List[Dict[str, Any]]:
    """List recent conversation threads."""
    db = get_db_manager()
    conv_repo = ConversationRepository(db)
    user_id = current_user.get("sub") if current_user else None
    return conv_repo.list_conversations(user_id=user_id, limit=limit)


@router.get("/conversations/{conv_id}/messages", summary="Get messages in conversation thread")
def get_conversation_messages(conv_id: str) -> List[Dict[str, Any]]:
    """Retrieve message transcript for a specific conversation."""
    db = get_db_manager()
    conv_repo = ConversationRepository(db)
    return conv_repo.get_messages(conv_id)
