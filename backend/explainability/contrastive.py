"""Contrastive reasoning generator for 'Why X instead of Y?' explanations (Phase 5).

Uses existing Phase 4 inference evidence ONLY.  No what-if simulation,
no rule re-execution, no LLM calls, no eval(), no exec(), no network.

Public surface:
    build_contrastive(result, rules, conclusion_a, conclusion_b)
        -> ContrastiveExplanation
    build_why_not(result, rules, conclusion, expected_value)
        -> WhyNotExplanation
"""

from typing import Any, Dict, List, Optional

from backend.explainability.trace_builder import (
    build_why,
    build_fact_provenance,
    _normalize_operator_str,
)
from backend.schemas.explanation import (
    ConditionExplanation,
    ContrastiveExplanation,
    WhyNotExplanation,
)
from backend.schemas.rule import (
    CompoundCondition,
    InferenceResult,
    Rule,
    SimpleCondition,
)


# =============================================================================
# Internal Helpers
# =============================================================================

def _rule_by_id(rules: List[Rule], rule_id: str) -> Optional[Rule]:
    """Return the Rule object whose id matches rule_id, or None."""
    for rule in rules:
        if rule.id == rule_id:
            return rule
    return None


def _collect_candidate_rule_ids(
    result: InferenceResult,
    rules: List[Rule],
    conclusion: str,
) -> List[str]:
    """Return rule IDs whose consequence could assert the conclusion fact.

    A rule is a 'candidate' if extracting its consequence would yield the
    conclusion path.  This mirrors Phase 3 extract_derived_facts logic
    without executing any inference.
    """
    candidates: List[str] = []
    for rule in rules:
        params = rule.consequence.params
        if "fact" in params and str(params["fact"]) == conclusion:
            candidates.append(rule.id)
        elif conclusion in params:
            candidates.append(rule.id)
        elif not params and f"action.{rule.consequence.action}" == conclusion:
            candidates.append(rule.id)
    return candidates


def _extract_blocking_conditions(
    result: InferenceResult,
    rules: List[Rule],
    conclusion: str,
) -> List[ConditionExplanation]:
    """Identify specific conditions that prevented candidate rules from firing.

    For each candidate rule (one whose consequence would set `conclusion`):
    - If it did NOT fire, examine its conditions against final working memory.
    - Report any SimpleCondition that evaluates to False as a blocking condition.

    Only SimpleConditions are reported as leaf failures; compound analysis
    is left for the condition explanation layer.
    """
    blocking: List[ConditionExplanation] = []
    candidate_ids = _collect_candidate_rule_ids(result, rules, conclusion)
    fired_ids = set(result.fired_rule_ids)
    final_facts = result.final_facts

    for rule_id in candidate_ids:
        if rule_id in fired_ids:
            # Rule fired — not a blocking candidate
            continue
        rule = _rule_by_id(rules, rule_id)
        if rule is None:
            continue
        _collect_failing_leaves(rule.condition, final_facts, blocking)

    return blocking


def _collect_failing_leaves(
    condition: Any,
    facts: Dict[str, Any],
    acc: List[ConditionExplanation],
) -> None:
    """Recursively collect SimpleCondition leaves that evaluate to False."""
    if isinstance(condition, SimpleCondition):
        op_str = _normalize_operator_str(condition.operator)
        actual = facts.get(condition.field)
        result = _eval_op(actual, op_str, condition.value)
        if not result:
            acc.append(ConditionExplanation(
                fact=condition.field,
                actual_value=actual,
                operator=op_str,
                expected_value=condition.value,
                result=False,
            ))
    elif isinstance(condition, CompoundCondition):
        for sub in (condition.conditions or []):
            _collect_failing_leaves(sub, facts, acc)
        if condition.condition:
            _collect_failing_leaves(condition.condition, facts, acc)
    elif isinstance(condition, dict):
        raw_op = condition.get("operator") or condition.get("type") or ""
        op = _normalize_operator_str(raw_op).upper()
        is_compound = (
            op in ("AND", "OR", "NOT")
            or "conditions" in condition
            or (condition.get("condition") is not None)
        )
        if is_compound:
            for sub in condition.get("conditions") or []:
                _collect_failing_leaves(sub, facts, acc)
            sub = condition.get("condition")
            if sub:
                _collect_failing_leaves(sub, facts, acc)
        else:
            fact_path = condition.get("field") or condition.get("fact") or ""
            raw_leaf_op = condition.get("operator")
            operator = _normalize_operator_str(raw_leaf_op)
            expected = condition.get("value")
            actual = facts.get(fact_path)
            result = _eval_op(actual, operator, expected)
            if not result:
                acc.append(ConditionExplanation(
                    fact=fact_path,
                    actual_value=actual,
                    operator=operator,
                    expected_value=expected,
                    result=False,
                ))


def _eval_op(fact_val: Any, op: str, target: Any) -> bool:
    """Safe single-operator evaluation mirroring Phase 3 logic."""
    try:
        if op == "==":
            return fact_val == target
        if op == "!=":
            return fact_val != target
        if op == ">":
            return fact_val > target
        if op == ">=":
            return fact_val >= target
        if op == "<":
            return fact_val < target
        if op == "<=":
            return fact_val <= target
        if op == "IN":
            if isinstance(fact_val, (list, tuple, set)):
                return target in fact_val
            if isinstance(target, (list, tuple, set)):
                return fact_val in target
            return fact_val in target
    except (TypeError, ValueError):
        pass
    return False


def _collect_missing_fact_paths(
    result: InferenceResult,
    rules: List[Rule],
    conclusion: str,
) -> List[str]:
    """Return fact paths referenced by candidate rules but absent from final working memory."""
    missing: List[str] = []
    candidate_ids = _collect_candidate_rule_ids(result, rules, conclusion)
    fired_ids = set(result.fired_rule_ids)
    final_facts = result.final_facts

    for rule_id in candidate_ids:
        if rule_id in fired_ids:
            continue
        rule = _rule_by_id(rules, rule_id)
        if rule is None:
            continue
        paths = _extract_leaf_paths(rule.condition)
        for path in paths:
            if path not in final_facts and path not in missing:
                missing.append(path)

    return sorted(missing)


def _extract_leaf_paths(condition: Any) -> List[str]:
    """Collect all fact paths referenced in a condition tree."""
    paths: List[str] = []
    if isinstance(condition, SimpleCondition):
        paths.append(condition.field)
    elif isinstance(condition, CompoundCondition):
        for sub in (condition.conditions or []):
            paths.extend(_extract_leaf_paths(sub))
        if condition.condition:
            paths.extend(_extract_leaf_paths(condition.condition))
    elif isinstance(condition, dict):
        f = condition.get("field") or condition.get("fact")
        if f:
            paths.append(f)
        for sub in condition.get("conditions") or []:
            paths.extend(_extract_leaf_paths(sub))
        sub = condition.get("condition")
        if sub:
            paths.extend(_extract_leaf_paths(sub))
    return paths


# =============================================================================
# WHY-NOT Builder
# =============================================================================

def build_why_not(
    result: InferenceResult,
    rules: Optional[List[Rule]] = None,
    conclusion: Optional[str] = None,
    expected_value: Any = True,
) -> WhyNotExplanation:
    """Build a structured WHY-NOT explanation for a conclusion that was not reached.

    Searches for candidate rules whose consequence would have established
    `conclusion = expected_value`, then reports which conditions failed and
    which facts were missing.

    If no candidate rules exist, returns an 'insufficient_evidence' result.

    Args:
        result: Completed InferenceResult from the Phase 4 engine.
        rules: Optional Rule objects used during inference.
        conclusion: The fact path that was expected but not established.
        expected_value: The value that was expected (default True).

    Returns:
        WhyNotExplanation — always has conclusion_reached=False.
    """
    rules = rules or []
    conclusion = conclusion or "unknown"

    # Check if the conclusion was actually reached
    final_val = result.final_facts.get(conclusion)
    if final_val == expected_value:
        # Conclusion WAS reached — why-not does not apply
        return WhyNotExplanation(
            conclusion=conclusion,
            expected_value=expected_value,
            conclusion_reached=True,
            evidence_available=True,
            insufficient_evidence_reason="The conclusion was actually reached.",
            blocking_conditions=[],
            missing_facts=[],
            candidate_rules=[],
        )

    candidate_ids = _collect_candidate_rule_ids(result, rules, conclusion)

    if not candidate_ids:
        return WhyNotExplanation(
            conclusion=conclusion,
            expected_value=expected_value,
            conclusion_reached=False,
            evidence_available=False,
            insufficient_evidence_reason=(
                f"No rules found whose consequence would establish '{conclusion}'. "
                "Cannot determine why it was not reached from the available inference evidence."
            ),
            blocking_conditions=[],
            missing_facts=[],
            candidate_rules=[],
        )

    blocking = _extract_blocking_conditions(result, rules, conclusion)
    missing = _collect_missing_fact_paths(result, rules, conclusion)

    # Evidence is available if at least one unfired candidate rule was found
    fired_ids = set(result.fired_rule_ids)
    unfired_candidates = [rid for rid in candidate_ids if rid not in fired_ids]
    evidence_available = len(unfired_candidates) > 0 or len(blocking) > 0

    insufficient_reason: Optional[str] = None
    if not evidence_available:
        insufficient_reason = (
            "All candidate rules fired, but none established the conclusion. "
            "This may indicate a negative preclusion conflict."
        )

    return WhyNotExplanation(
        conclusion=conclusion,
        expected_value=expected_value,
        conclusion_reached=False,
        evidence_available=evidence_available,
        insufficient_evidence_reason=insufficient_reason,
        blocking_conditions=blocking,
        missing_facts=missing,
        candidate_rules=candidate_ids,
    )


# =============================================================================
# Contrastive Explanation Builder
# =============================================================================

def build_contrastive(
    result: InferenceResult,
    rules: Optional[List[Rule]] = None,
    conclusion_a: Optional[str] = None,
    conclusion_b: Optional[str] = None,
) -> ContrastiveExplanation:
    """Build a 'Why X instead of Y?' contrastive explanation.

    Uses existing inference evidence only.  Does NOT run what-if simulation.

    Args:
        result: Completed InferenceResult from the Phase 4 engine.
        rules: Optional Rule objects for enrichment.
        conclusion_a: The conclusion that WAS reached.
        conclusion_b: The alternative conclusion that was NOT reached.

    Returns:
        ContrastiveExplanation with differentiating facts/rules and embedded
        WHY / WHY-NOT sub-explanations.
    """
    rules = rules or []
    conclusion_a = conclusion_a or next(iter(result.derived_facts), "unknown_a")
    conclusion_b = conclusion_b or "unknown_b"

    val_a = result.final_facts.get(conclusion_a)
    val_b = result.final_facts.get(conclusion_b)
    b_reached = conclusion_b in result.final_facts and bool(val_b) if val_b is not None else False

    # Determine if we have enough evidence for contrast
    a_reached = conclusion_a in result.derived_facts or (val_a is not None and bool(val_a))
    evidence_available = a_reached  # minimum requirement

    # Differentiating rules: rules that fired AND whose consequence mentions conclusion_a
    candidate_a = set(_collect_candidate_rule_ids(result, rules, conclusion_a))
    candidate_b = set(_collect_candidate_rule_ids(result, rules, conclusion_b))
    fired_set = set(result.fired_rule_ids)

    differentiating_rules = sorted(candidate_a & fired_set - candidate_b)

    # Differentiating facts: facts used by conclusion_a rules but not conclusion_b rules
    diff_facts: Dict[str, Any] = {}
    for ds in result.derivation_history:
        if ds.rule_id in differentiating_rules:
            diff_facts.update(ds.source_facts)

    # Build embedded WHY and WHY-NOT
    why_a = build_why(result, rules, conclusion_a)
    why_not_b = build_why_not(result, rules, conclusion_b)

    return ContrastiveExplanation(
        conclusion_a=conclusion_a,
        conclusion_a_value=val_a,
        conclusion_b=conclusion_b,
        conclusion_b_value=val_b,
        conclusion_b_reached=b_reached,
        differentiating_facts=diff_facts,
        differentiating_rules=differentiating_rules,
        why_a=why_a,
        why_not_b=why_not_b,
        evidence_available=evidence_available,
    )
