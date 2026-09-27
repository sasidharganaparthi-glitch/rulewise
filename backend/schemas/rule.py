"""Declarative rule schema and data structures for RuleWise AI.

This module defines the structural Pydantic models for declarative rules,
conditions, and consequences. Rules are stored and validated as pure structured data.
NO rule execution, condition evaluation, or inference occurs in this layer.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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
    """Atomic condition comparing an entity field against a target value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str = Field(
        ...,
        min_length=1,
        description="Path to entity field, e.g. 'student.gpa' or 'student.completed_courses'",
    )
    operator: ComparisonOperator = Field(
        ...,
        description="Comparison operator for predicate evaluation",
    )
    value: Any = Field(
        ...,
        description="Target literal value or collection against which the field is tested",
    )


class CompoundCondition(BaseModel):
    """Compound condition combining multiple sub-conditions via Boolean logic."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operator: LogicalOperator = Field(
        ...,
        description="Boolean operator ('AND', 'OR', 'NOT') governing sub-conditions",
    )
    conditions: List[Union[SimpleCondition, "CompoundCondition"]] = Field(
        ...,
        min_length=1,
        description="Collection of child conditions evaluated under the logical operator",
    )


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
