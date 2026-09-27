"""Deterministic condition evaluation engine for RuleWise AI.

Evaluates structured Boolean condition trees (AND, OR, NOT) and comparison
predicates against WorkingMemory facts.
No eval, no exec, no dynamic code execution.
"""

from typing import Any, Dict, List, Union
from backend.core.exceptions import (
    MalformedRuleError,
    UnknownConditionTypeError,
)
from backend.engine.operators import evaluate_operator
from backend.engine.working_memory import WorkingMemory
from backend.schemas.rule import (
    CompoundCondition,
    LogicalOperator,
    RuleCondition,
    SimpleCondition,
)


def evaluate_condition(
    condition: Union[RuleCondition, Dict[str, Any]],
    working_memory: WorkingMemory,
) -> bool:
    """Evaluate a structured condition or condition tree against working memory.

    Supports:
    - Simple comparison condition (Pydantic model or dict):
      `{"type": "comparison", "fact": "student.gpa", "operator": ">=", "value": 7.0}`
    - Logical AND (Pydantic model or dict):
      `{"type": "AND", "conditions": [...]}`
    - Logical OR (Pydantic model or dict):
      `{"type": "OR", "conditions": [...]}`
    - Logical NOT (Pydantic model or dict):
      `{"type": "NOT", "condition": {...}}`

    Args:
        condition: Validated condition model or structured dictionary.
        working_memory: WorkingMemory instance containing facts.

    Returns:
        Boolean result of evaluating the condition tree.

    Raises:
        UnknownConditionTypeError: If condition type or structure is unrecognized.
        MalformedRuleError: If required fields or sub-conditions are missing.
        FactResolutionError: If a referenced fact path does not exist.
        UnsupportedOperatorError: If a comparison operator is unsupported.
        InvalidComparisonError: If operand types are incompatible.
    """
    if condition is None:
        raise MalformedRuleError("Condition cannot be None.")

    # -------------------------------------------------------------------------
    # 1. Pydantic Model Evaluation
    # -------------------------------------------------------------------------
    if isinstance(condition, SimpleCondition):
        resolved_val = working_memory.get_fact(condition.field)
        op_str = condition.operator.value if hasattr(condition.operator, "value") else str(condition.operator)
        return evaluate_operator(resolved_val, op_str, condition.value)

    if isinstance(condition, CompoundCondition):
        if condition.operator == LogicalOperator.AND:
            if not condition.conditions:
                raise MalformedRuleError("AND condition requires a non-empty list of sub-conditions.")
            return all(evaluate_condition(sub, working_memory) for sub in condition.conditions)

        if condition.operator == LogicalOperator.OR:
            if not condition.conditions:
                raise MalformedRuleError("OR condition requires a non-empty list of sub-conditions.")
            return any(evaluate_condition(sub, working_memory) for sub in condition.conditions)

        if condition.operator == LogicalOperator.NOT:
            sub = condition.condition or (condition.conditions[0] if condition.conditions else None)
            if sub is None:
                raise MalformedRuleError("NOT condition requires a single sub-condition.")
            return not evaluate_condition(sub, working_memory)

        raise UnknownConditionTypeError(f"Unsupported logical operator: {condition.operator}")

    # -------------------------------------------------------------------------
    # 2. Dictionary Representation Evaluation
    # -------------------------------------------------------------------------
    if isinstance(condition, dict):
        cond_type = condition.get("type") or condition.get("operator")

        # Normalize string representation
        norm_type = str(cond_type).upper() if cond_type is not None else ""

        # Case A: AND condition
        if norm_type == "AND":
            subs = condition.get("conditions")
            if not subs or not isinstance(subs, list):
                raise MalformedRuleError("AND condition requires a non-empty 'conditions' list.")
            return all(evaluate_condition(sub, working_memory) for sub in subs)

        # Case B: OR condition
        if norm_type == "OR":
            subs = condition.get("conditions")
            if not subs or not isinstance(subs, list):
                raise MalformedRuleError("OR condition requires a non-empty 'conditions' list.")
            return any(evaluate_condition(sub, working_memory) for sub in subs)

        # Case C: NOT condition
        if norm_type == "NOT":
            sub = condition.get("condition")
            if sub is None:
                subs = condition.get("conditions")
                if subs and isinstance(subs, list) and len(subs) == 1:
                    sub = subs[0]
            if sub is None:
                raise MalformedRuleError("NOT condition requires a target 'condition'.")
            return not evaluate_condition(sub, working_memory)

        # Case D: Comparison condition
        is_comparison = (
            norm_type == "COMPARISON"
            or "fact" in condition
            or "field" in condition
            or ("operator" in condition and norm_type not in ("AND", "OR", "NOT"))
        )

        if is_comparison:
            fact_path = condition.get("fact") or condition.get("field")
            op = condition.get("operator")

            if not fact_path or not isinstance(fact_path, str) or not fact_path.strip():
                raise MalformedRuleError(f"Comparison condition missing or invalid 'fact'/'field': {condition}")
            if not op or not isinstance(op, str):
                raise MalformedRuleError(f"Comparison condition missing 'operator': {condition}")
            if "value" not in condition:
                raise MalformedRuleError(f"Comparison condition missing 'value': {condition}")

            target_val = condition["value"]
            resolved_val = working_memory.get_fact(fact_path)
            return evaluate_operator(resolved_val, str(op), target_val)

        raise UnknownConditionTypeError(
            f"Unrecognized condition structure: {condition}. Expected 'AND', 'OR', 'NOT', or a comparison predicate."
        )

    raise UnknownConditionTypeError(
        f"Unsupported condition object type: {type(condition).__name__}. Expected RuleCondition or dict."
    )
