"""Declarative rule schema and data structures for RuleWise AI.

This module defines the structural Pydantic models for declarative rules,
conditions, consequences, and execution/inference results. Rules are stored
and validated as pure structured data.
Executable code (eval, exec, compile, arbitrary imports) is strictly prohibited.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class ComparisonOperator(str, Enum):
    """Supported comparison operators for rule conditions."""

    EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    IN = "IN"


class LogicalOperator(str, Enum):
    """Supported logical Boolean connectives for compound conditions."""

    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class RuleStatus(str, Enum):
    """Lifecycle status of a declarative rule."""

    ACTIVE = "active"
    STAGED = "staged"
    ARCHIVED = "archived"
    DISABLED = "disabled"


class SimpleCondition(BaseModel):
    """Atomic condition comparing an entity fact against a target value."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )

    type: Optional[str] = Field(
        default="comparison",
        description="Condition type identifier (e.g. 'comparison')",
    )
    field: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("field", "fact"),
        description="Path to entity fact, e.g. 'student.gpa' or 'student.skills'",
    )
    operator: ComparisonOperator = Field(
        ...,
        description="Comparison operator for predicate evaluation",
    )
    value: Any = Field(
        ...,
        description="Target literal value or collection against which the fact is tested",
    )


class CompoundCondition(BaseModel):
    """Compound condition combining multiple sub-conditions via Boolean logic."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )

    type: Optional[str] = Field(
        default=None,
        description="Optional type identifier matching the logical operator (e.g. 'AND', 'OR', 'NOT')",
    )
    operator: LogicalOperator = Field(
        ...,
        validation_alias=AliasChoices("operator", "type", "logical_operator"),
        description="Boolean operator ('AND', 'OR', 'NOT') governing sub-conditions",
    )
    conditions: Optional[List[Union[SimpleCondition, "CompoundCondition"]]] = Field(
        default=None,
        description="Collection of child conditions evaluated under AND/OR logic",
    )
    condition: Optional[Union[SimpleCondition, "CompoundCondition"]] = Field(
        default=None,
        description="Single target condition evaluated under NOT logic",
    )

    @model_validator(mode="after")
    def validate_structure(self) -> "CompoundCondition":
        """Validate logical operator constraints against supplied sub-conditions."""
        if self.operator == LogicalOperator.NOT:
            # NOT must have exactly one sub-condition via either 'condition' or 'conditions'
            if self.condition is None and (not self.conditions or len(self.conditions) != 1):
                raise ValueError("NOT condition requires exactly one sub-condition")
        else:
            # AND/OR must have at least one sub-condition in 'conditions'
            if not self.conditions or len(self.conditions) < 1:
                raise ValueError(
                    f"{self.operator.value} condition requires a non-empty list of sub-conditions"
                )
        return self


# Enable recursive model references for nested compound conditions (e.g. AND(OR(...), ...))
CompoundCondition.model_rebuild()

RuleCondition = Union[SimpleCondition, CompoundCondition]


class RuleConsequence(BaseModel):
    """Declarative specification of an action or assertion triggered by rule satisfaction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str = Field(
        ...,
        min_length=1,
        description="Identifier of the resulting action or fact assertion",
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured parameters or payload associated with the consequence",
    )
    description: Optional[str] = Field(
        None,
        description="Optional human-readable description of the consequence outcome",
    )


class Rule(BaseModel):
    """Declarative business rule definition stored and managed as structured data."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )

    id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the rule (e.g. 'RULE_MIN_GPA')",
    )
    name: str = Field(
        ...,
        min_length=1,
        description="Human-readable title describing the policy",
    )
    description: str = Field(
        ...,
        description="Detailed explanation of the rule intent and regulatory rationale",
    )
    priority: int = Field(
        default=0,
        validation_alias=AliasChoices("priority", "salience"),
        description="Rule precedence or salience score (higher integer values evaluate first)",
    )
    status: RuleStatus = Field(
        default=RuleStatus.ACTIVE,
        description="Lifecycle status indicating whether the rule is active, staged, or disabled",
    )
    condition: Union[SimpleCondition, CompoundCondition] = Field(
        ...,
        description="Structured Boolean condition tree required for rule triggering",
    )
    consequence: RuleConsequence = Field(
        ...,
        description="Declarative action or assertion triggered when condition is satisfied",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Operational metadata such as authority, tags, version, and timestamps",
    )


class RuleExecutionResult(BaseModel):
    """Structured result returned by evaluating or applying a single declarative rule."""

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(..., description="Identifier of the evaluated rule")
    rule_name: str = Field(..., description="Name of the evaluated rule")
    matched: bool = Field(..., description="Whether all rule conditions were satisfied")
    derived_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured facts asserted/derived upon rule match",
    )


# -----------------------------------------------------------------------------
# Phase 4 Forward-Chaining Inference Models
# -----------------------------------------------------------------------------

class FactProvenance(BaseModel):
    """Audit metadata tracking the origin and derivation step of a fact."""

    model_config = ConfigDict(frozen=True)

    path: str = Field(..., description="Dotted fact path in working memory")
    value: Any = Field(..., description="Value of the fact")
    is_derived: bool = Field(default=False, description="True if inferred by a rule; False if initial")
    step: int = Field(default=0, description="Inference sequence step when the fact was asserted")
    rule_id: Optional[str] = Field(default=None, description="Identifier of the rule that produced this fact")


class DerivationStep(BaseModel):
    """Record of a single rule firing step during forward chaining."""

    model_config = ConfigDict(frozen=True)

    step: int = Field(..., description="Deterministic sequence step number (1-indexed)")
    rule_id: str = Field(..., description="Identifier of the fired rule")
    rule_name: str = Field(..., description="Name of the fired rule")
    matched_condition: Optional[Any] = Field(default=None, description="Serialized condition structure that matched")
    derived_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary of facts asserted by this rule firing",
    )
    source_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of facts that satisfied the rule conditions",
    )


class InferenceResult(BaseModel):
    """Comprehensive result produced by a forward-chaining inference run."""

    model_config = ConfigDict(frozen=True)

    final_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Complete working memory facts after inference completion",
    )
    derived_facts: Dict[str, Any] = Field(
        default_factory=dict,
        description="All newly derived facts generated during the inference run",
    )
    fired_rule_ids: List[str] = Field(
        default_factory=list,
        description="Ordered list of rule identifiers that fired during the run",
    )
    inference_step_count: int = Field(
        default=0,
        description="Total number of inference rule firing steps executed",
    )
    termination_reason: str = Field(
        default="fixed_point",
        description="Reason for inference termination: 'fixed_point', 'cycle_detected', or 'max_depth_reached'",
    )
    fixed_point_reached: bool = Field(
        default=True,
        description="True if inference reached a natural stable fixed point",
    )
    cycle_detected: bool = Field(
        default=False,
        description="True if an inference cycle or repeated state was encountered",
    )
    max_depth_reached: bool = Field(
        default=False,
        description="True if the configured maximum inference depth was reached",
    )
    derivation_history: List[DerivationStep] = Field(
        default_factory=list,
        description="Chronological sequence of rule firing steps",
    )
    fact_provenance: Dict[str, FactProvenance] = Field(
        default_factory=dict,
        description="Provenance audit trail mapping fact paths to origin details",
    )
