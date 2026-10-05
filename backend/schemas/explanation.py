"""Schemas for reasoning traces, audit records, and contrastive explanations (Phase 5).

All models are frozen Pydantic v2 structures.  They hold structured explanation
data derived purely from Phase 4 inference output.

No LLM, no eval(), no exec(), no network calls, no randomness.
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Condition-Level Explanation
# =============================================================================

class ConditionExplanation(BaseModel):
    """Structured record explaining the evaluation of a single comparison predicate.

    Captures the fact path, the actual value found in working memory, the comparison
    operator, the expected (target) value, and the Boolean result.
    """

    model_config = ConfigDict(frozen=True)

    fact: str = Field(..., description="Dotted fact path evaluated (e.g. 'student.gpa')")
    actual_value: Any = Field(..., description="Value resolved from working memory at evaluation time")
    operator: str = Field(..., description="Comparison operator applied (e.g. '>=', '==', 'IN')")
    expected_value: Any = Field(..., description="Target value or collection from the rule condition")
    result: bool = Field(..., description="Boolean outcome: True if the comparison was satisfied")


class CompoundConditionExplanation(BaseModel):
    """Structured record explaining a Boolean (AND / OR / NOT) compound condition.

    Sub-conditions are represented recursively as either ConditionExplanation
    (leaf) or nested CompoundConditionExplanation (branch) instances.
    """

    model_config = ConfigDict(frozen=True)

    operator: str = Field(..., description="Logical connective: 'AND', 'OR', or 'NOT'")
    sub_conditions: List[Union[ConditionExplanation, "CompoundConditionExplanation"]] = Field(
        default_factory=list,
        description="Ordered list of child condition explanations",
    )
    result: bool = Field(..., description="Boolean outcome of the compound condition")


# Allow recursive self-reference
CompoundConditionExplanation.model_rebuild()

# Convenience alias
AnyConditionExplanation = Union[ConditionExplanation, CompoundConditionExplanation]


# =============================================================================
# Fact Provenance Record
# =============================================================================

class FactProvenanceExplanation(BaseModel):
    """Human-readable provenance record for a single fact.

    Indicates whether the fact was part of the initial working memory or was
    derived by a specific rule, at which inference step.
    """

    model_config = ConfigDict(frozen=True)

    fact: str = Field(..., description="Dotted fact path")
    value: Any = Field(..., description="Fact value")
    origin: Literal["initial", "derived"] = Field(
        ..., description="'initial' if provided at start; 'derived' if asserted by a rule"
    )
    step: int = Field(default=0, description="Inference step at which the fact was established (0 = initial)")
    source_rule_id: Optional[str] = Field(
        default=None,
        description="Rule identifier that produced this fact (None for initial facts)",
    )
    source_rule_name: Optional[str] = Field(
        default=None,
        description="Human-readable rule name that produced this fact (None for initial facts)",
    )


# =============================================================================
# Trace Step
# =============================================================================

class TraceStep(BaseModel):
    """Complete record of a single rule firing step within the reasoning trace.

    Contains full context: which rule fired, what conditions were evaluated,
    which facts triggered the match, and what new facts were derived.
    """

    model_config = ConfigDict(frozen=True)

    step: int = Field(..., description="1-indexed inference sequence number")
    rule_id: str = Field(..., description="Identifier of the fired rule")
    rule_name: str = Field(..., description="Human-readable name of the fired rule")
    rule_description: Optional[str] = Field(
        default=None, description="Optional detailed description of the rule's intent"
    )
    rule_priority: int = Field(default=0, description="Salience/priority score of the fired rule")
    condition_explanation: Optional[AnyConditionExplanation] = Field(
        default=None,
        description="Structured explanation of the matched condition tree",
    )
    source_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Facts from working memory that satisfied the rule conditions",
    )
    derived_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="New facts asserted by the rule consequence",
    )
    derived_fact_provenance: List[FactProvenanceExplanation] = Field(
        default_factory=list,
        description="Provenance records for each fact derived at this step",
    )


# =============================================================================
# Explanation Root Models
# =============================================================================

class Explanation(BaseModel):
    """Root structured explanation produced from a Phase 4 InferenceResult.

    Captures the full audit trail: what was concluded, why, which rules fired,
    which facts were used, how derived facts were chained, and how the inference
    terminated.
    """

    model_config = ConfigDict(frozen=True)

    conclusion: str = Field(
        ...,
        description="The query or conclusion fact path being explained (e.g. 'student.ai_course_eligible')",
    )
    conclusion_value: Any = Field(
        ..., description="The final value of the conclusion fact in working memory"
    )
    conclusion_reached: bool = Field(
        ..., description="True if the conclusion fact exists and evaluates to a truthy value"
    )
    trace_steps: List[TraceStep] = Field(
        default_factory=list,
        description="Chronologically ordered list of rule-firing trace steps",
    )
    supporting_rules: List[str] = Field(
        default_factory=list,
        description="Rule IDs that contributed (directly or transitively) to the conclusion",
    )
    supporting_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Facts (initial and derived) that were referenced by supporting rules",
    )
    all_derived_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="All facts derived during the inference run",
    )
    fact_provenance: List[FactProvenanceExplanation] = Field(
        default_factory=list,
        description="Provenance records for all facts in the final working memory",
    )
    termination_reason: str = Field(
        default="fixed_point",
        description="Reason inference stopped: 'fixed_point', 'cycle_detected', 'max_depth_reached'",
    )
    total_steps: int = Field(default=0, description="Total number of rule firing steps executed")


class WhyExplanation(BaseModel):
    """Structured explanation of WHY a specific conclusion was reached.

    Traces the derivation chain backwards from the conclusion through
    each contributing rule to the initial facts that enabled it.
    """

    model_config = ConfigDict(frozen=True)

    conclusion: str = Field(..., description="The fact path whose conclusion is being explained")
    conclusion_value: Any = Field(..., description="The value of the conclusion fact")
    conclusion_reached: bool = Field(..., description="Whether the conclusion was established")
    derivation_chain: List[TraceStep] = Field(
        default_factory=list,
        description="Ordered sequence of rule-firing steps that led to the conclusion",
    )
    root_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Initial (non-derived) facts that ultimately enabled the conclusion",
    )
    intermediate_derived_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Derived facts that acted as intermediate enablers for the conclusion",
    )


class WhyNotExplanation(BaseModel):
    """Structured explanation of WHY a specific conclusion was NOT reached.

    Reports evidence-backed analysis of which conditions failed, preventing
    specific rules from firing.  If evidence is insufficient, returns a
    structured 'insufficient_evidence' result rather than inventing reasoning.
    """

    model_config = ConfigDict(frozen=True)

    conclusion: str = Field(..., description="The fact path that was NOT established")
    expected_value: Any = Field(default=True, description="The value that was expected but not found")
    conclusion_reached: bool = Field(default=False, description="Always False for why-not explanations")
    evidence_available: bool = Field(
        ...,
        description="True if there is enough inference evidence to explain the failure",
    )
    insufficient_evidence_reason: Optional[str] = Field(
        default=None,
        description="Human-readable reason why evidence is insufficient (if applicable)",
    )
    blocking_conditions: List[ConditionExplanation] = Field(
        default_factory=list,
        description="Specific conditions that evaluated to False, preventing rules from firing",
    )
    missing_facts: List[str] = Field(
        default_factory=list,
        description="Fact paths that were referenced by relevant rules but absent from working memory",
    )
    candidate_rules: List[str] = Field(
        default_factory=list,
        description="IDs of rules whose consequence could have established the conclusion if conditions had matched",
    )


class ContrastiveExplanation(BaseModel):
    """Structural foundation for 'Why X instead of Y?' explanations.

    Uses existing inference evidence only.  Does NOT run what-if simulation.
    Identifies which facts/rules are responsible for achieving conclusion_a
    and which, by their absence or different values, prevented conclusion_b.
    """

    model_config = ConfigDict(frozen=True)

    conclusion_a: str = Field(..., description="The conclusion that WAS reached")
    conclusion_a_value: Any = Field(..., description="Value of conclusion_a in final working memory")
    conclusion_b: str = Field(..., description="The alternative conclusion that was NOT reached")
    conclusion_b_value: Any = Field(
        default=None, description="Value of conclusion_b in final working memory (None if absent)"
    )
    conclusion_b_reached: bool = Field(
        default=False, description="Whether conclusion_b was present in final working memory"
    )
    differentiating_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Facts that are referenced by rules for conclusion_a but not conclusion_b",
    )
    differentiating_rules: List[str] = Field(
        default_factory=list,
        description="Rule IDs that fired and produced conclusion_a but not conclusion_b",
    )
    why_a: Optional[WhyExplanation] = Field(
        default=None,
        description="Full WHY explanation for conclusion_a",
    )
    why_not_b: Optional[WhyNotExplanation] = Field(
        default=None,
        description="Full WHY-NOT explanation for conclusion_b",
    )
    evidence_available: bool = Field(
        ...,
        description="True if there is sufficient inference evidence to support the contrast",
    )
