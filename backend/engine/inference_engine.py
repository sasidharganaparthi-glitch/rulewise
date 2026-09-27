"""Declarative inference primitives and consequence generation for RuleWise AI.

Phase 3 Boundary:
Provides single-rule evaluation and structured consequence assertion.
Full forward-chaining loops, conflict resolution agendas, specificity ranking,
and multi-pass cycle detection belong strictly to Phase 4.
"""

from typing import Any, Dict
from backend.core.exceptions import MalformedRuleError
from backend.engine.rule_matcher import RuleMatcher
from backend.engine.working_memory import WorkingMemory
from backend.schemas.rule import Rule, RuleConsequence, RuleExecutionResult


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


class InferenceEngine:
    """Deterministic Phase 3 single-rule execution and consequence generator.

    Provides core primitive execution operations for single rules.
    Forward chaining, conflict resolution, and agenda scheduling are deferred to Phase 4.
    """

    @staticmethod
    def evaluate_rule(rule: Rule, working_memory: WorkingMemory) -> RuleExecutionResult:
        """Evaluate a single rule without modifying working memory state."""
        return evaluate_rule(rule, working_memory)

    @staticmethod
    def apply_rule(rule: Rule, working_memory: WorkingMemory) -> RuleExecutionResult:
        """Evaluate a single rule and assert its derived facts if matched."""
        return apply_rule(rule, working_memory)
