"""Rule matching component for RuleWise AI.

Evaluates whether a validated declarative rule's condition matches the current
facts in WorkingMemory. Does not perform forward chaining or consequence generation.
"""

from backend.core.exceptions import MalformedRuleError
from backend.engine.condition_evaluator import evaluate_condition
from backend.engine.working_memory import WorkingMemory
from backend.schemas.rule import Rule


class RuleMatcher:
    """Evaluates whether a declarative rule's condition matches working memory facts."""

    @staticmethod
    def matches(rule: Rule, working_memory: WorkingMemory) -> bool:
        """Determine whether the specified rule matches the facts in working memory.

        Args:
            rule: A validated Rule model instance.
            working_memory: WorkingMemory instance containing facts to test.

        Returns:
            True if all rule conditions evaluate to True, False otherwise.

        Raises:
            MalformedRuleError: If the rule has no condition defined.
            ConditionEvaluationError: If condition evaluation or fact resolution encounters an error.
        """
        if not isinstance(rule, Rule):
            raise MalformedRuleError(f"Expected a validated Rule instance, got {type(rule).__name__}")

        if rule.condition is None:
            raise MalformedRuleError(f"Rule '{rule.id}' does not have a condition defined.")

        return evaluate_condition(rule.condition, working_memory)


def matches(rule: Rule, working_memory: WorkingMemory) -> bool:
    """Convenience functional interface to test if a rule matches working memory.

    Args:
        rule: A validated Rule model instance.
        working_memory: WorkingMemory instance containing facts.

    Returns:
        True if the rule condition is satisfied, False otherwise.
    """
    return RuleMatcher.matches(rule, working_memory)
