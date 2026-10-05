"""Execution trace builder for constructing structured reasoning logs (Phase 5).

Converts a Phase 4 InferenceResult into structured, auditable Explanation
objects.  All interpretation is derived purely from the recorded inference
data — no rules are re-evaluated, no facts are changed, no LLM is called.

Public surface:
    build_trace(result, rules)           -> Explanation
    build_why(result, rules, conclusion) -> WhyExplanation
    explain_condition(condition, facts)  -> AnyConditionExplanation
    build_fact_provenance(result, rules) -> List[FactProvenanceExplanation]
"""

from typing import Any, Dict, List, Optional, Union

from backend.core.exceptions import FactResolutionError
from backend.schemas.explanation import (
    AnyConditionExplanation,
    CompoundConditionExplanation,
    ConditionExplanation,
    Explanation,
    FactProvenanceExplanation,
    TraceStep,
    WhyExplanation,
)
from backend.schemas.rule import (
    ComparisonOperator,
    CompoundCondition,
    DerivationStep,
    FactProvenance,
    InferenceResult,
    LogicalOperator,
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


def _normalize_operator_str(raw_op: Any) -> str:
    """Normalize operator representation to a clean string.

    Handles enum instances (e.g. LogicalOperator.AND -> 'AND',
    ComparisonOperator.EQUALS -> '=='), stringified enums (e.g.
    'LogicalOperator.AND' -> 'AND'), and direct strings ('AND', '==').
    """
    if raw_op is None:
        return ""
    if hasattr(raw_op, "value"):
        return str(raw_op.value)
    s = str(raw_op).strip()
    if s.startswith("LogicalOperator."):
        return s.split(".", 1)[1]
    if s.startswith("ComparisonOperator."):
        op_name = s.split(".", 1)[1]
        try:
            return ComparisonOperator[op_name].value
        except (KeyError, AttributeError):
            return op_name
    return s


def _explain_simple_condition(
    condition: SimpleCondition,
    facts: Dict[str, Any],
) -> ConditionExplanation:
    """Build a leaf ConditionExplanation from a SimpleCondition and the fact snapshot."""
    actual = facts.get(condition.field)
    op_str = _normalize_operator_str(condition.operator)

    # Determine the result from the snapshot rather than re-evaluating
    result = _evaluate_operator_safe(actual, op_str, condition.value)

    return ConditionExplanation(
        fact=condition.field,
        actual_value=actual,
        operator=op_str,
        expected_value=condition.value,
        result=result,
    )


def _evaluate_operator_safe(fact_val: Any, op: str, target: Any) -> bool:
    """Re-evaluate a single comparison safely without import of the operators module
    at module level (avoids circular imports).  This mirrors Phase 3 logic and
    is only used here to fill in condition results when the snapshot is available.

    Returns False (rather than raising) if the comparison is incompatible.
    """
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


def _explain_condition(
    condition: Union[SimpleCondition, CompoundCondition, Dict[str, Any], None],
    facts: Dict[str, Any],
) -> Optional[AnyConditionExplanation]:
    """Recursively build a structured condition explanation from any condition form.

    Args:
        condition: A SimpleCondition, CompoundCondition, raw dict, or None.
        facts: Snapshot of working-memory facts at the time the rule was evaluated.

    Returns:
        A ConditionExplanation (leaf) or CompoundConditionExplanation (branch), or None.
    """
    if condition is None:
        return None

    if isinstance(condition, SimpleCondition):
        return _explain_simple_condition(condition, facts)

    if isinstance(condition, CompoundCondition):
        op_str = _normalize_operator_str(condition.operator).upper()
        sub_expls: List[AnyConditionExplanation] = []

        if op_str == "NOT":
            sub = condition.condition or (condition.conditions[0] if condition.conditions else None)
            if sub is not None:
                child = _explain_condition(sub, facts)
                if child is not None:
                    sub_expls.append(child)
            result = not (sub_expls[0].result if sub_expls else True)
        else:
            for sub in (condition.conditions or []):
                child = _explain_condition(sub, facts)
                if child is not None:
                    sub_expls.append(child)
            if op_str == "AND":
                result = all(c.result for c in sub_expls)
            else:  # OR
                result = any(c.result for c in sub_expls)

        return CompoundConditionExplanation(
            operator=op_str,
            sub_conditions=sub_expls,
            result=result,
        )

    if isinstance(condition, dict):
        # Raw dict form (serialised condition from DerivationStep.matched_condition)
        raw_op = condition.get("operator") or condition.get("type") or ""
        op_str = _normalize_operator_str(raw_op).upper()

        is_compound = (
            op_str in ("AND", "OR", "NOT")
            or "conditions" in condition
            or (condition.get("condition") is not None)
        )

        if is_compound:
            if op_str not in ("AND", "OR", "NOT"):
                op_str = "AND" if "conditions" in condition else "NOT"

            sub_expls = []
            if op_str == "NOT":
                sub = condition.get("condition") or (
                    (condition.get("conditions") or [None])[0]
                )
                if sub is not None:
                    child = _explain_condition(sub, facts)
                    if child is not None:
                        sub_expls.append(child)
                result = not (sub_expls[0].result if sub_expls else True)
            else:
                for sub in condition.get("conditions") or []:
                    child = _explain_condition(sub, facts)
                    if child is not None:
                        sub_expls.append(child)
                result = all(c.result for c in sub_expls) if op_str == "AND" else any(c.result for c in sub_expls)
            return CompoundConditionExplanation(
                operator=op_str,
                sub_conditions=sub_expls,
                result=result,
            )

        # Leaf comparison dict
        fact_path = condition.get("field") or condition.get("fact") or ""
        raw_leaf_op = condition.get("operator")
        operator = _normalize_operator_str(raw_leaf_op)
        expected = condition.get("value")
        actual = facts.get(fact_path)
        result = _evaluate_operator_safe(actual, operator, expected)
        return ConditionExplanation(
            fact=fact_path,
            actual_value=actual,
            operator=operator,
            expected_value=expected,
            result=result,
        )

    return None


# =============================================================================
# Fact Provenance Builder
# =============================================================================

def build_fact_provenance(
    result: InferenceResult,
    rules: Optional[List[Rule]] = None,
) -> List[FactProvenanceExplanation]:
    """Convert the Phase 4 FactProvenance map into explanation-layer records.

    Args:
        result: A completed InferenceResult from the Phase 4 inference engine.
        rules: Optional list of Rule objects for enriching provenance with rule names.

    Returns:
        List of FactProvenanceExplanation instances, one per tracked fact.
    """
    rules = rules or []
    records: List[FactProvenanceExplanation] = []

    # Build rule-id → name lookup
    rule_names: Dict[str, str] = {r.id: r.name for r in rules}

    for path, prov in result.fact_provenance.items():
        source_rule_name = rule_names.get(prov.rule_id) if prov.rule_id else None
        records.append(
            FactProvenanceExplanation(
                fact=path,
                value=prov.value,
                origin="derived" if prov.is_derived else "initial",
                step=prov.step,
                source_rule_id=prov.rule_id,
                source_rule_name=source_rule_name,
            )
        )

    # Sort deterministically by (step, fact path)
    records.sort(key=lambda r: (r.step, r.fact))
    return records


# =============================================================================
# Trace Step Builder
# =============================================================================

def _build_trace_step(
    derivation_step: DerivationStep,
    rules: List[Rule],
    provenance_map: Dict[str, FactProvenance],
    rule_names: Dict[str, str],
) -> TraceStep:
    """Convert a single DerivationStep into a TraceStep explanation record."""
    rule = _rule_by_id(rules, derivation_step.rule_id)
    priority = rule.priority if rule else 0
    description = rule.description if rule else None

    # Build condition explanation from the recorded source facts
    condition_expl: Optional[AnyConditionExplanation] = None
    if rule is not None and rule.condition is not None:
        condition_expl = _explain_condition(rule.condition, derivation_step.source_facts)
    elif derivation_step.matched_condition is not None:
        condition_expl = _explain_condition(
            derivation_step.matched_condition, derivation_step.source_facts
        )

    # Build per-derived-fact provenance
    derived_provenance: List[FactProvenanceExplanation] = []
    for path in derivation_step.derived_facts:
        prov = provenance_map.get(path)
        if prov is not None:
            source_name = rule_names.get(prov.rule_id) if prov.rule_id else None
            derived_provenance.append(
                FactProvenanceExplanation(
                    fact=path,
                    value=prov.value,
                    origin="derived",
                    step=prov.step,
                    source_rule_id=prov.rule_id,
                    source_rule_name=source_name,
                )
            )
        else:
            # Fact existed but provenance was not recorded (defensive)
            derived_provenance.append(
                FactProvenanceExplanation(
                    fact=path,
                    value=derivation_step.derived_facts[path],
                    origin="derived",
                    step=derivation_step.step,
                    source_rule_id=derivation_step.rule_id,
                    source_rule_name=rule_names.get(derivation_step.rule_id),
                )
            )

    return TraceStep(
        step=derivation_step.step,
        rule_id=derivation_step.rule_id,
        rule_name=derivation_step.rule_name,
        rule_description=description,
        rule_priority=priority,
        condition_explanation=condition_expl,
        source_facts=dict(derivation_step.source_facts),
        derived_facts=dict(derivation_step.derived_facts),
        derived_fact_provenance=derived_provenance,
    )


# =============================================================================
# Main Trace Builder
# =============================================================================

def build_trace(
    result: InferenceResult,
    rules: Optional[List[Rule]] = None,
    conclusion: Optional[str] = None,
) -> Explanation:
    """Build a complete structured Explanation from a Phase 4 InferenceResult.

    Args:
        result: Completed InferenceResult from the forward-chaining engine.
        rules: Optional list of Rule objects for name/priority/description enrichment.
        conclusion: Optional fact path to use as the 'conclusion' label.
                    If None, defaults to the first derived fact path, or 'inference'.

    Returns:
        A fully populated, frozen Explanation instance.
    """
    rules = rules or []
    rule_names: Dict[str, str] = {r.id: r.name for r in rules}

    # Build trace steps
    trace_steps: List[TraceStep] = [
        _build_trace_step(ds, rules, result.fact_provenance, rule_names)
        for ds in result.derivation_history
    ]

    # Determine conclusion label and value
    if conclusion is None:
        conclusion = next(iter(result.derived_facts), "inference")
    conclusion_value = result.final_facts.get(conclusion)
    conclusion_reached = bool(conclusion_value) if conclusion_value is not None else False

    # Collect supporting rules (all that fired)
    supporting_rules = list(result.fired_rule_ids)

    # Collect supporting facts: all source_facts across all trace steps
    supporting_facts: Dict[str, Any] = {}
    for ts in trace_steps:
        supporting_facts.update(ts.source_facts)

    # Build provenance list
    provenance_list = build_fact_provenance(result, rules)

    return Explanation(
        conclusion=conclusion,
        conclusion_value=conclusion_value,
        conclusion_reached=conclusion_reached,
        trace_steps=trace_steps,
        supporting_rules=supporting_rules,
        supporting_facts=supporting_facts,
        all_derived_facts=dict(result.derived_facts),
        fact_provenance=provenance_list,
        termination_reason=result.termination_reason,
        total_steps=result.inference_step_count,
    )


# =============================================================================
# WHY Explanation
# =============================================================================

def _find_contributing_steps(
    conclusion: str,
    trace_steps: List[TraceStep],
    derived_facts: Dict[str, Any],
) -> List[TraceStep]:
    """Return the ordered subset of trace steps that contributed to `conclusion`.

    A step contributes if:
    - It directly derived `conclusion`, OR
    - It derived an intermediate fact that was later used by a contributing step.
    """
    # Work backwards: start from steps that directly derived the conclusion
    contributing_rule_ids: set = set()
    contributing_paths: set = {conclusion}

    # Iterate derivation_history in reverse to trace back dependencies
    for step in reversed(trace_steps):
        # Did this step derive something in our dependency set?
        if any(p in contributing_paths for p in step.derived_facts):
            contributing_rule_ids.add(step.rule_id)
            # Add all facts this step consumed as new dependencies
            contributing_paths.update(step.source_facts.keys())

    # Return steps in chronological order, filtered to contributors
    return [s for s in trace_steps if s.rule_id in contributing_rule_ids]


def build_why(
    result: InferenceResult,
    rules: Optional[List[Rule]] = None,
    conclusion: Optional[str] = None,
) -> WhyExplanation:
    """Build a WHY explanation for a specific conclusion fact.

    Traces backwards through the derivation history to find the chain
    of rules and initial facts that produced the conclusion.

    Args:
        result: Completed InferenceResult.
        rules: Optional Rule objects for enrichment.
        conclusion: Fact path to explain.  Defaults to first derived fact.

    Returns:
        WhyExplanation with derivation chain, root facts, and intermediates.
    """
    rules = rules or []
    rule_names: Dict[str, str] = {r.id: r.name for r in rules}

    if conclusion is None:
        conclusion = next(iter(result.derived_facts), "inference")

    conclusion_value = result.final_facts.get(conclusion)
    conclusion_reached = (
        conclusion in result.derived_facts or conclusion in result.final_facts
    ) and bool(conclusion_value) if conclusion_value is not None else False

    # Build full trace steps first
    trace_steps: List[TraceStep] = [
        _build_trace_step(ds, rules, result.fact_provenance, rule_names)
        for ds in result.derivation_history
    ]

    # Find contributing steps
    contributing = _find_contributing_steps(conclusion, trace_steps, result.derived_facts)

    # Root facts: initial facts (step == 0) referenced by contributing steps
    root_facts: Dict[str, Any] = {}
    for step in contributing:
        for path, val in step.source_facts.items():
            prov = result.fact_provenance.get(path)
            if prov is None or not prov.is_derived:
                root_facts[path] = val

    # Intermediate derived facts: derived facts used as inputs to later contributing steps
    intermediate: Dict[str, Any] = {}
    for step in contributing:
        for path, val in step.source_facts.items():
            prov = result.fact_provenance.get(path)
            if prov is not None and prov.is_derived and path != conclusion:
                intermediate[path] = val

    return WhyExplanation(
        conclusion=conclusion,
        conclusion_value=conclusion_value,
        conclusion_reached=conclusion_reached,
        derivation_chain=contributing,
        root_facts=root_facts,
        intermediate_derived_facts=intermediate,
    )


# =============================================================================
# Public convenience wrapper
# =============================================================================

def explain_condition(
    condition: Union[SimpleCondition, CompoundCondition, Dict[str, Any], None],
    facts: Dict[str, Any],
) -> Optional[AnyConditionExplanation]:
    """Public API: Build a structured condition explanation given facts.

    Args:
        condition: Any condition form (Pydantic model or dict).
        facts: Working-memory snapshot at evaluation time.

    Returns:
        ConditionExplanation or CompoundConditionExplanation, or None.
    """
    return _explain_condition(condition, facts)
