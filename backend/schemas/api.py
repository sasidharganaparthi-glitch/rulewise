"""API request and response schemas for RuleWise AI."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Health check response payload schema."""

    model_config = ConfigDict(frozen=True)

    status: str = Field(..., description="Service health indicator (e.g. 'ok')")
    project: str = Field(..., description="Project name")
    phase: int = Field(..., description="Current development phase number")


class ProviderStatusResponse(BaseModel):
    """Operational status of the language model provider and reasoning engine."""

    model_config = ConfigDict(frozen=True)

    status: str = Field(..., description="Overall operational status")
    provider_class: str = Field(..., description="Class name of the active language model provider")
    provider_available: bool = Field(..., description="Whether the language model provider is configured and available")
    symbolic_engine: str = Field(..., description="Operational status of the symbolic reasoning engine")
    fallback_ready: bool = Field(..., description="Whether deterministic offline fallback is active")


class ErrorResponse(BaseModel):
    """Standardized API error response payload."""

    model_config = ConfigDict(frozen=True)

    detail: str = Field(..., description="Human-readable error description")
    error_code: Optional[str] = Field(default=None, description="Domain error classification code")


# -----------------------------------------------------------------------------
# Auth Schemas
# -----------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    email: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str
    is_admin_login: bool = False


class GoogleAuthRequest(BaseModel):
    credential: str = Field(..., description="Google ID Token issued by Google Identity Services")


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=100)


class AdminUserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(...)
    password: str = Field(..., min_length=6, max_length=100)
    role: str = Field("user", pattern="^(admin|user)$")


class AdminUserStatusUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = Field(None, pattern="^(admin|user)$")


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool = True
    picture: Optional[str] = None
    google_id: Optional[str] = None
    created_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# -----------------------------------------------------------------------------
# Domain Schemas
# -----------------------------------------------------------------------------

class DomainFieldSchema(BaseModel):
    name: str = Field(..., description="Dot-path field name, e.g. 'applicant.credit_score'")
    type: str = Field("string", description="number, string, boolean, or list")
    label: Optional[str] = None
    description: Optional[str] = None
    default_value: Optional[Any] = None


class DomainCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=50)
    description: str = ""
    category: str = "general"
    schema_fields: List[DomainFieldSchema] = Field(default_factory=list)


class DomainResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = ""
    category: str
    is_official: bool
    version: str
    schema_fields: List[Dict[str, Any]] = Field(default_factory=list)
    created_by: Optional[str] = None
    created_at: str
    updated_at: str
    rule_count: Optional[int] = 0


# -----------------------------------------------------------------------------
# Rule Authoring & Testing Schemas
# -----------------------------------------------------------------------------

class RuleCreateRequest(BaseModel):
    domain_id: str
    name: str = Field(..., min_length=2, max_length=150)
    description: str = ""
    priority: int = Field(50, ge=1, le=100)
    status: str = Field("active", pattern="^(active|staged|retired)$")
    condition: Dict[str, Any]
    consequence: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class RuleUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=100)
    status: Optional[str] = Field(None, pattern="^(active|staged|retired)$")
    condition: Optional[Dict[str, Any]] = None
    consequence: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class RuleValidateRequest(BaseModel):
    condition: Dict[str, Any]
    consequence: Dict[str, Any]


class RuleValidateResponse(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    referenced_facts: List[str] = Field(default_factory=list)


class RuleTestRequest(BaseModel):
    rule: Dict[str, Any]
    facts: Dict[str, Any]


class RuleTestResponse(BaseModel):
    matched: bool
    derived_facts: Dict[str, Any] = Field(default_factory=dict)
    errors: Optional[str] = None


# -----------------------------------------------------------------------------
# Simulation Schemas
# -----------------------------------------------------------------------------

class SimulationRequest(BaseModel):
    domain_id: str
    baseline_facts: Dict[str, Any]
    fact_overrides: Dict[str, Any] = Field(default_factory=dict)


class SimulationResponse(BaseModel):
    domain_id: str
    baseline_decision: str
    simulated_decision: str
    delta: Any


# -----------------------------------------------------------------------------
# History & Stats Schemas
# -----------------------------------------------------------------------------

class EvaluationHistoryResponse(BaseModel):
    id: str
    domain_id: str
    user_id: Optional[str] = None
    question: Optional[str] = None
    confidence: Optional[float] = 1.0
    input_facts: Dict[str, Any]
    conclusion_reached: bool
    final_decision: str
    decision_status: str
    fired_rules: List[str]
    derived_facts: Dict[str, Any]
    explanation: Dict[str, Any]
    created_at: str


class KnowledgeStatsResponse(BaseModel):
    domains_count: int
    official_rules_count: int
    custom_rules_count: int
    total_rules_count: int
    evaluations_count: int
    ai_status: str
