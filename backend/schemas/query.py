"""Pydantic schemas for user queries, intent classification, and chat responses.

Phase 6: Defines validated structured query representations for natural language
interaction with the deterministic rule engine.
"""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class UserIntent(str, Enum):
    """Categorization of incoming user messages."""

    GENERAL_CHAT = "GENERAL_CHAT"
    RULE_QUERY = "RULE_QUERY"


class QueryAction(str, Enum):
    """Specific rule-evaluation or explanation action requested by the user."""

    COURSE_ELIGIBILITY = "course_eligibility"
    WHY_ELIGIBLE = "why_eligible"
    WHY_NOT_ELIGIBLE = "why_not_eligible"
    ACADEMIC_STANDING = "academic_standing"
    PREREQUISITE_CHECK = "prerequisite_check"
    SKILL_CHECK = "skill_check"
    GENERAL_EVALUATION = "general_evaluation"


class IntentClassificationResult(BaseModel):
    """Validated structured output from intent classification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: UserIntent = Field(..., description="Classified intent: GENERAL_CHAT or RULE_QUERY")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reasoning: Optional[str] = Field(default=None, description="Optional brief classification rationale")


class StructuredRuleQuery(BaseModel):
    """Validated structured query extracted from natural language rule requests.

    Captures the student subject, target course/policy, and requested evaluation action.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: UserIntent = Field(default=UserIntent.RULE_QUERY, description="Always RULE_QUERY for structured queries")
    subject: str = Field(
        ...,
        min_length=1,
        description="Target student name or identifier (e.g. 'Arun', 'Priya', 'student_001')",
    )
    action: QueryAction = Field(
        default=QueryAction.COURSE_ELIGIBILITY,
        description="Target evaluation or explanation action",
    )
    target: Optional[str] = Field(
        default=None,
        description="Target course name, course code, or policy aspect (e.g. 'AI', 'CS101')",
    )
    raw_query: Optional[str] = Field(
        default=None,
        description="Original user message for reference",
    )


class ChatRequest(BaseModel):
    """API payload for user chat inquiries."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        ...,
        min_length=1,
        max_length=20000,
        description="User's natural language input message",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Optional conversation thread identifier",
    )
    domain_id: Optional[str] = Field(
        default=None,
        description="Optional target domain ID for rule evaluation",
    )
    attachments: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Optional attached files with extracted text or metadata",
    )
    attached_files: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Alias for attached files sent by web clients",
    )


class ChatResponse(BaseModel):
    """API response model returned to the user."""

    model_config = ConfigDict(frozen=True)

    message: str = Field(..., description="Natural language response to the user")
    intent: UserIntent = Field(..., description="Classified intent of the request")
    structured_query: Optional[StructuredRuleQuery] = Field(
        default=None,
        description="Extracted structured query if intent was RULE_QUERY",
    )
    symbolic_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Deterministic conclusion and derivation summary from the symbolic engine",
    )
    explanation: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Phase 5 structured explanation details (trace, why, or why-not)",
    )
    used_fallback: bool = Field(
        default=False,
        description="True if deterministic fallback was used instead of Gemini",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error details if query parsing or execution encountered an issue",
    )
