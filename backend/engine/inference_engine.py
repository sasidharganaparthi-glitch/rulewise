"""Deterministic forward-chaining inference engine for RuleWise AI.

Phase 4:
Provides genuine forward-chaining rule execution, deterministic conflict resolution
(salience, specificity, recency, rule ID), cycle detection, maximum inference depth
enforcement, negative preclusion handling, and comprehensive derivation history.
No LLM, no network, completely offline and deterministic.
"""

import json
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from backend.core.exceptions import FactResolutionError, MalformedRuleError
from backend.engine.rule_matcher import RuleMatcher
from backend.engine.working_memory import WorkingMemory
from backend.schemas.rule import (
    CompoundCondition,
    DerivationStep,
    InferenceResult,
    Rule,
    RuleCondition,
    RuleConsequence,
    RuleExecutionResult,
    SimpleCondition,
)


# -----------------------------------------------------------------------------
# Specificity, Recency, and Fact Extraction Helpers
# -----------------------------------------------------------------------------

def compute_rule_specificity(condition: Union[RuleCondition, Dict[str, Any], None]) -> int:
    """Compute the specificity score of a rule condition tree.

    Specificity is measured as the total count of atomic comparison predicates
    in the condition structure. Higher count denotes higher specificity.
    """
    if condition is None:
        return 0

    if isinstance(condition, SimpleCondition):
        return 1

    if isinstance(condition, CompoundCondition):
        total = 0
        if condition.conditions:
            for sub in condition.conditions:
                total += compute_rule_specificity(sub)
        if condition.condition:
            total += compute_rule_specificity(condition.condition)
        return max(1, total)

    if isinstance(condition, dict):
        cond_type = str(condition.get("type") or condition.get("operator") or "").upper()
        if cond_type in ("AND", "OR"):
            subs = condition.get("conditions", [])
            return max(1, sum(compute_rule_specificity(s) for s in subs))
        elif cond_type == "NOT":
            sub = condition.get("condition") or (condition.get("conditions", [None])[0])
            return max(1, compute_rule_specificity(sub))
        else:
            return 1

    return 1


def extract_referenced_fact_paths(condition: Union[RuleCondition, Dict[str, Any], None]) -> List[str]:
    """Extract all dot-separated fact paths referenced by a condition tree."""
    if condition is None:
        return []

    if isinstance(condition, SimpleCondition):
        return [condition.field]

    if isinstance(condition, CompoundCondition):
        paths: List[str] = []
        if condition.conditions:
            for sub in condition.conditions:
                paths.extend(extract_referenced_fact_paths(sub))
        if condition.condition:
            paths.extend(extract_referenced_fact_paths(condition.condition))
        return paths

    if isinstance(condition, dict):
        paths = []
        fact_path = condition.get("fact") or condition.get("field")
        if fact_path and isinstance(fact_path, str):
            paths.append(fact_path)
        for sub in condition.get("conditions", []):
            paths.extend(extract_referenced_fact_paths(sub))
        if "condition" in condition:
            paths.extend(extract_referenced_fact_paths(condition["condition"]))
        return paths

    return []


def compute_rule_recency(
    condition: Union[RuleCondition, Dict[str, Any], None],
    working_memory: WorkingMemory,
) -> int:
    """Determine the recency rank of a rule based on its condition dependencies.

    Returns the maximum sequence step index among all facts referenced by the rule's conditions.
    """
    paths = extract_referenced_fact_paths(condition)
    if not paths:
        return 0
    return max((working_memory.get_fact_step(p) for p in paths), default=0)


def extract_derived_facts(consequence: RuleConsequence) -> Dict[str, Any]:
    """Extract structured derived facts from a rule's consequence definition.

    Args:
        consequence: A validated RuleConsequence instance.

    Returns:
        Dictionary mapping fact paths to their asserted values.

    Raises:
        MalformedRuleError: If the consequence is missing or malformed.
    """
    if consequence is None or not isinstance(consequence, RuleConsequence):
        raise MalformedRuleError("Rule consequence must be a valid RuleConsequence instance.")

    derived: Dict[str, Any] = {}
    params = consequence.params

    # Pattern A: Explicit {"fact": "path", "value": val}
    if "fact" in params and "value" in params:
        fact_path = str(params["fact"])
        derived[fact_path] = params["value"]
        return derived

    # Pattern B: Direct key-value assertions
    if params:
        for k, v in params.items():
            derived[str(k)] = v
    else:
        # Default action assertion if no parameters given
        derived[f"action.{consequence.action}"] = True

    return derived


# -----------------------------------------------------------------------------
# Phase 3 Single-Rule Primitives (Preserved for Backward Compatibility)
# -----------------------------------------------------------------------------

def evaluate_rule(rule: Rule, working_memory: WorkingMemory) -> RuleExecutionResult:
    """Evaluate a single rule against working memory without asserting derived facts.

    Args:
        rule: Validated Rule instance.
        working_memory: WorkingMemory containing current facts.

    Returns:
        RuleExecutionResult indicating match status and potential derived facts.
    """
    matched = RuleMatcher.matches(rule, working_memory)
    if not matched:
        return RuleExecutionResult(
            rule_id=rule.id,
            rule_name=rule.name,
            matched=False,
            derived_facts={},
        )

    derived = extract_derived_facts(rule.consequence)
    return RuleExecutionResult(
        rule_id=rule.id,
        rule_name=rule.name,
        matched=True,
        derived_facts=derived,
    )


def apply_rule(rule: Rule, working_memory: WorkingMemory) -> RuleExecutionResult:
    """Evaluate a single rule and, if matched, assert its derived facts into working memory.

    Args:
        rule: Validated Rule instance.
        working_memory: WorkingMemory to test and update with derived facts.

    Returns:
        RuleExecutionResult indicating match status and asserted derived facts.
    """
    result = evaluate_rule(rule, working_memory)
    if result.matched:
        for fact_path, fact_val in result.derived_facts.items():
            working_memory.add_derived_fact(fact_path, fact_val)
    return result


# -----------------------------------------------------------------------------
# Phase 4 Full Forward-Chaining Inference System
# -----------------------------------------------------------------------------

def _get_state_signature(facts: Dict[str, Any]) -> str:
    """Serialize facts dictionary into a deterministic canonical string for state matching."""
    try:
        return json.dumps(facts, sort_keys=True, default=str)
    except Exception:
        return str(sorted(facts.items()))


def infer(
    rules: List[Rule],
    working_memory: WorkingMemory,
    max_depth: int = 50,
) -> InferenceResult:
    """Execute deterministic forward chaining on working memory until fixed point or limit.

    Conflict Resolution Strategy:
        1. Salience (Priority) - Higher integer wins.
        2. Specificity - More atomic conditions win.
        3. Recency - Rules depending on more recently derived facts win.
        4. Rule ID - Lexicographical ascending sort as final deterministic tie-breaker.

    Args:
        rules: Collection of validated Rule instances to consider.
        working_memory: WorkingMemory containing baseline initial facts (remains unmutated).
        max_depth: Maximum inference cycles before terminating (default 50).

    Returns:
        InferenceResult with final facts, derivations, fired rules, and termination reason.
    """
    # Isolate inference run using a deep clone
    wm = working_memory.clone()

    fired_rules: Set[str] = set()
    fired_rule_ids: List[str] = []
    derivation_history: List[DerivationStep] = []

    seen_states: Set[str] = set()
    initial_signature = _get_state_signature(wm.get_all_facts())
    seen_states.add(initial_signature)

    step_count = 0
    termination_reason = "fixed_point"

    while step_count < max_depth:
        candidates: List[Tuple[Rule, int, int, Dict[str, Any]]] = []

        # Find matching rules that have not yet fired
        for rule in rules:
            if rule.id in fired_rules:
                continue

            try:
                matched = RuleMatcher.matches(rule, wm)
            except FactResolutionError:
                # A referenced fact does not yet exist → rule does not match this step
                matched = False

            if not matched:
                continue

            derived = extract_derived_facts(rule.consequence)
            specificity = compute_rule_specificity(rule.condition)
            recency = compute_rule_recency(rule.condition, wm)

            candidates.append((rule, specificity, recency, derived))

        # Check for fixed point termination
        if not candidates:
            termination_reason = "fixed_point"
            break

        # Conflict Resolution:
        # Sort key: (-priority, -specificity, -recency, rule.id)
        candidates.sort(
            key=lambda c: (-c[0].priority, -c[1], -c[2], c[0].id)
        )
        selected_rule, specificity, recency, derived_facts = candidates[0]

        # Fire selected rule
        step_count += 1
        fired_rules.add(selected_rule.id)
        fired_rule_ids.append(selected_rule.id)

        # Capture source facts that satisfied the rule
        referenced_paths = extract_referenced_fact_paths(selected_rule.condition)
        source_facts = {
            p: wm.get_fact(p) for p in referenced_paths if wm.has_fact(p)
        }

        # Assert derived facts with recency and provenance
        for fact_path, fact_val in derived_facts.items():
            wm.add_derived_fact(
                fact_path,
                fact_val,
                step=step_count,
                source_rule_id=selected_rule.id,
            )

        # Record step in derivation history
        serialized_condition = (
            selected_rule.condition.model_dump()
            if hasattr(selected_rule.condition, "model_dump")
            else selected_rule.condition
        )
        derivation_history.append(
            DerivationStep(
                step=step_count,
                rule_id=selected_rule.id,
                rule_name=selected_rule.name,
                matched_condition=serialized_condition,
                derived_facts=derived_facts,
                source_facts=source_facts,
            )
        )

        # Cycle / Repeated state detection
        current_signature = _get_state_signature(wm.get_all_facts())
        if current_signature in seen_states:
            termination_reason = "cycle_detected"
            break
        seen_states.add(current_signature)

    else:
        # Loop exited because step_count reached max_depth
        if termination_reason != "cycle_detected":
            termination_reason = "max_depth_reached"

    return InferenceResult(
        final_facts=wm.get_all_facts(),
        derived_facts=wm.get_derived_facts(),
        fired_rule_ids=fired_rule_ids,
        inference_step_count=step_count,
        termination_reason=termination_reason,
        fixed_point_reached=(termination_reason == "fixed_point"),
        cycle_detected=(termination_reason == "cycle_detected"),
        max_depth_reached=(termination_reason == "max_depth_reached"),
        derivation_history=derivation_history,
        fact_provenance=wm.get_all_provenance(),
    )


class InferenceEngine:
    """Deterministic forward-chaining symbolic inference engine for RuleWise AI.

    Combines single-rule primitive execution with full forward chaining,
    conflict resolution, and cycle detection.
    """

    @staticmethod
    def evaluate_rule(rule: Rule, working_memory: WorkingMemory) -> RuleExecutionResult:
        """Evaluate a single rule without modifying working memory state."""
        return evaluate_rule(rule, working_memory)

    @staticmethod
    def apply_rule(rule: Rule, working_memory: WorkingMemory) -> RuleExecutionResult:
        """Evaluate a single rule and assert its derived facts if matched."""
        return apply_rule(rule, working_memory)

    @staticmethod
    def infer(
        rules: List[Rule],
        working_memory: WorkingMemory,
        max_depth: int = 50,
    ) -> InferenceResult:
        """Execute full forward-chaining inference over the given rules and working memory."""
        return infer(rules, working_memory, max_depth=max_depth)
