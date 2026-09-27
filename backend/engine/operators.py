"""Deterministic and secure comparison operators for the RuleWise AI rule engine.

This module provides explicit operator dispatch for comparison evaluation.
Arbitrary execution (eval, exec, compile) is strictly prohibited.
"""

from typing import Any, Callable, Dict
from backend.core.exceptions import InvalidComparisonError, UnsupportedOperatorError


def _op_eq(left: Any, right: Any) -> bool:
    """Safe equality comparison (==)."""
    return bool(left == right)


def _op_ne(left: Any, right: Any) -> bool:
    """Safe inequality comparison (!=)."""
    return bool(left != right)


def _op_gt(left: Any, right: Any) -> bool:
    """Safe strictly greater-than comparison (>)."""
    try:
        return bool(left > right)
    except TypeError as exc:
        raise InvalidComparisonError(
            f"Cannot evaluate '>' between incompatible types: {type(left).__name__} and {type(right).__name__}"
        ) from exc


def _op_gte(left: Any, right: Any) -> bool:
    """Safe greater-than-or-equal comparison (>=)."""
    try:
        return bool(left >= right)
    except TypeError as exc:
        raise InvalidComparisonError(
            f"Cannot evaluate '>=' between incompatible types: {type(left).__name__} and {type(right).__name__}"
        ) from exc


def _op_lt(left: Any, right: Any) -> bool:
    """Safe strictly less-than comparison (<)."""
    try:
        return bool(left < right)
    except TypeError as exc:
        raise InvalidComparisonError(
            f"Cannot evaluate '<' between incompatible types: {type(left).__name__} and {type(right).__name__}"
        ) from exc


def _op_lte(left: Any, right: Any) -> bool:
    """Safe less-than-or-equal comparison (<=)."""
    try:
        return bool(left <= right)
    except TypeError as exc:
        raise InvalidComparisonError(
            f"Cannot evaluate '<=' between incompatible types: {type(left).__name__} and {type(right).__name__}"
        ) from exc


def _op_in(left: Any, right: Any) -> bool:
    """Safe membership comparison (IN).

    Supports:
    1. Standard membership: `left IN right` (e.g. element in list/set/tuple/string).
    2. Inverted collection fact: if `left` is a collection and `right` is an element
       (e.g. resolved `student.skills` IN `"python"`), checks if `right` is inside `left`.
    """
    # Case 1: right is an iterable container (list, tuple, set, dict, str)
    if isinstance(right, (list, tuple, set, dict, str)) and not isinstance(left, (list, tuple, set)):
        try:
            return bool(left in right)
        except TypeError as exc:
            raise InvalidComparisonError(
                f"Cannot test membership of {type(left).__name__} in {type(right).__name__}: {exc}"
            ) from exc

    # Case 2: left is a collection fact and right is a target scalar
    if isinstance(left, (list, tuple, set)):
        try:
            return bool(right in left)
        except TypeError as exc:
            raise InvalidComparisonError(
                f"Cannot test membership of {type(right).__name__} in {type(left).__name__}: {exc}"
            ) from exc

    # Case 3: right is a collection and left is also a collection
    if isinstance(right, (list, tuple, set)):
        try:
            return bool(left in right)
        except TypeError as exc:
            raise InvalidComparisonError(
                f"Cannot test membership of {type(left).__name__} in {type(right).__name__}: {exc}"
            ) from exc

    raise InvalidComparisonError(
        f"Operator 'IN' requires an iterable collection operand; got left={type(left).__name__}, right={type(right).__name__}"
    )


# Explicit operator dispatch map (no eval, no exec, no dynamic lookups)
SUPPORTED_OPERATORS: Dict[str, Callable[[Any, Any], bool]] = {
    "==": _op_eq,
    "!=": _op_ne,
    ">": _op_gt,
    ">=": _op_gte,
    "<": _op_lt,
    "<=": _op_lte,
    "IN": _op_in,
}


def evaluate_operator(left: Any, operator: str, right: Any) -> bool:
    """Evaluate a comparison operator against two resolved operands.

    Args:
        left: Left operand value.
        operator: Supported comparison operator string ('==', '!=', '>', '>=', '<', '<=', 'IN').
        right: Right operand value.

    Returns:
        Boolean result of the comparison.

    Raises:
        UnsupportedOperatorError: If the operator is not supported.
        InvalidComparisonError: If the operand types cannot be compared with the operator.
    """
    if operator not in SUPPORTED_OPERATORS:
        raise UnsupportedOperatorError(
            f"Unsupported comparison operator: '{operator}'. Supported operators: {list(SUPPORTED_OPERATORS.keys())}"
        )

    handler = SUPPORTED_OPERATORS[operator]
    return handler(left, right)
