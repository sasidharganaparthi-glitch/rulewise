"""Comprehensive test suite for the RuleWise AI Declarative Rule Engine (Phase 3)."""

from typing import Any, Dict
import pytest

from backend.core.exceptions import (
    FactResolutionError,
    InvalidComparisonError,
    MalformedRuleError,
    UnknownConditionTypeError,
    UnsupportedOperatorError,
)
from backend.engine.condition_evaluator import evaluate_condition
from backend.engine.inference_engine import InferenceEngine, apply_rule, evaluate_rule
from backend.engine.operators import evaluate_operator
from backend.engine.rule_matcher import RuleMatcher, matches
from backend.engine.working_memory import WorkingMemory
from backend.schemas.rule import (
    ComparisonOperator,
    CompoundCondition,
    LogicalOperator,
    Rule,
    RuleConsequence,
    RuleExecutionResult,
    RuleStatus,
    SimpleCondition,
)


# =============================================================================
# 1. Operators & Comparisons
# =============================================================================

def test_operators_numeric_comparisons():
    """Verify numeric comparisons with all supported operators."""
    assert evaluate_operator(8.5, ">=", 7.0) is True
    assert evaluate_operator(7.0, ">=", 7.0) is True
    assert evaluate_operator(6.9, ">=", 7.0) is False

    assert evaluate_operator(8.5, ">", 7.0) is True
    assert evaluate_operator(7.0, ">", 7.0) is False

    assert evaluate_operator(5.0, "<=", 6.0) is True
    assert evaluate_operator(6.0, "<=", 6.0) is True
    assert evaluate_operator(6.1, "<=", 6.0) is False

    assert evaluate_operator(5.0, "<", 6.0) is True
    assert evaluate_operator(6.0, "<", 6.0) is False

    assert evaluate_operator(10, "==", 10) is True
    assert evaluate_operator(10, "==", 20) is False

    assert evaluate_operator(10, "!=", 20) is True
    assert evaluate_operator(10, "!=", 10) is False


def test_operators_string_comparisons():
    """Verify string equality, inequality, and lexicographical comparisons."""
    assert evaluate_operator("active", "==", "active") is True
    assert evaluate_operator("active", "!=", "probation") is True
    assert evaluate_operator("alpha", "<", "beta") is True
    assert evaluate_operator("beta", ">", "alpha") is True


def test_operators_in_membership():
    """Verify membership operator with collections and scalar targets."""
    # Target in list
    assert evaluate_operator("python", "IN", ["python", "java"]) is True
    assert evaluate_operator("c++", "IN", ["python", "java"]) is False

    # Inverted fact: fact is list, value is element
    assert evaluate_operator(["python", "java"], "IN", "python") is True
    assert evaluate_operator(["python", "java"], "IN", "c++") is False

    # Substring in string
    assert evaluate_operator("py", "IN", "python") is True
    assert evaluate_operator("ruby", "IN", "python") is False


def test_invalid_operator_rejected():
    """Verify that unsupported operators raise UnsupportedOperatorError."""
    with pytest.raises(UnsupportedOperatorError) as exc_info:
        evaluate_operator(10, "LIKE", "%test%")

    assert "Unsupported comparison operator" in str(exc_info.value)

    with pytest.raises(UnsupportedOperatorError):
        evaluate_operator(10, "MAGIC", 10)


def test_invalid_comparison_types():
    """Verify that comparing incompatible types raises InvalidComparisonError."""
    with pytest.raises(InvalidComparisonError) as exc_info:
        evaluate_operator("high_gpa", ">", 8.0)

    assert "Cannot evaluate '>'" in str(exc_info.value)

    # Membership against non-iterable
    with pytest.raises(InvalidComparisonError) as exc_info:
        evaluate_operator(10, "IN", 20)

    assert "requires an iterable" in str(exc_info.value)


# =============================================================================
# 2. Fact Resolution & Working Memory
# =============================================================================

@pytest.fixture
def sample_working_memory() -> WorkingMemory:
    """Fixture providing populated WorkingMemory for academic domain."""
    return WorkingMemory(
        {
            "student": {
                "id": "student_001",
                "name": "Arun Sharma",
                "gpa": 8.7,
                "completed_courses": ["CS101", "MA101"],
                "skills": ["python", "data_structures"],
                "academic_status": "active",
            },
            "course": {
                "id": "AI101",
                "minimum_gpa": 7.0,
            },
        }
    )


def test_fact_resolution_nested(sample_working_memory: WorkingMemory):
    """Verify resolution of nested dotted fact paths."""
    assert sample_working_memory.get_fact("student.gpa") == 8.7
    assert sample_working_memory.get_fact("student.name") == "Arun Sharma"
    assert sample_working_memory.get_fact("student.skills") == ["python", "data_structures"]
    assert sample_working_memory.get_fact("student.completed_courses") == ["CS101", "MA101"]
    assert sample_working_memory.get_fact("course.minimum_gpa") == 7.0

    # List index traversal
    assert sample_working_memory.get_fact("student.skills.0") == "python"
    assert sample_working_memory.get_fact("student.skills.1") == "data_structures"


def test_fact_existence_check(sample_working_memory: WorkingMemory):
    """Verify has_fact checks."""
    assert sample_working_memory.has_fact("student.gpa") is True
    assert sample_working_memory.has_fact("student.nonexistent") is False
    assert sample_working_memory.has_fact("department.code") is False


def test_missing_fact_raises_error(sample_working_memory: WorkingMemory):
    """Verify that resolving a non-existent fact path raises FactResolutionError."""
    with pytest.raises(FactResolutionError) as exc_info:
        sample_working_memory.get_fact("student.nonexistent_field")

    assert "nonexistent_field" in str(exc_info.value)

    with pytest.raises(FactResolutionError) as exc_info:
        sample_working_memory.get_fact("unknown_entity.field")

    assert "root key 'unknown_entity' does not exist" in str(exc_info.value)


def test_working_memory_mutations(sample_working_memory: WorkingMemory):
    """Verify adding, updating, and clearing facts in working memory."""
    # Update existing
    sample_working_memory.update_fact("student.gpa", 9.1)
    assert sample_working_memory.get_fact("student.gpa") == 9.1

    # Add new root fact
    sample_working_memory.add_fact("term", "Fall 2026")
    assert sample_working_memory.get_fact("term") == "Fall 2026"

    # Add derived fact
    sample_working_memory.add_derived_fact("student.eligible", True)
    assert sample_working_memory.get_fact("student.eligible") is True
    assert sample_working_memory.get_derived_facts() == {"student.eligible": True}

    # Verify deep copy isolation
    all_facts = sample_working_memory.get_all_facts()
    all_facts["student"]["gpa"] = 0.0
    assert sample_working_memory.get_fact("student.gpa") == 9.1

    # Clear
    sample_working_memory.clear()
    assert sample_working_memory.has_fact("student.gpa") is False
    assert len(sample_working_memory.get_derived_facts()) == 0


# =============================================================================
# 3. Boolean Logic & Condition Evaluator
# =============================================================================

def test_boolean_and_evaluator(sample_working_memory: WorkingMemory):
    """Verify AND condition evaluation (all conditions must be true)."""
    # True AND True -> True
    cond_true = {
        "type": "AND",
        "conditions": [
            {"fact": "student.gpa", "operator": ">=", "value": 7.0},
            {"fact": "student.academic_status", "operator": "==", "value": "active"},
        ],
    }
    assert evaluate_condition(cond_true, sample_working_memory) is True

    # True AND False -> False
    cond_false = {
        "type": "AND",
        "conditions": [
            {"fact": "student.gpa", "operator": ">=", "value": 7.0},
            {"fact": "student.academic_status", "operator": "==", "value": "probation"},
        ],
    }
    assert evaluate_condition(cond_false, sample_working_memory) is False


def test_boolean_or_evaluator(sample_working_memory: WorkingMemory):
    """Verify OR condition evaluation (at least one condition must be true)."""
    # True OR False -> True
    cond_true = {
        "type": "OR",
        "conditions": [
            {"fact": "student.gpa", "operator": ">=", "value": 9.5},
            {"fact": "student.academic_status", "operator": "==", "value": "active"},
        ],
    }
    assert evaluate_condition(cond_true, sample_working_memory) is True

    # False OR False -> False
    cond_false = {
        "type": "OR",
        "conditions": [
            {"fact": "student.gpa", "operator": ">=", "value": 9.5},
            {"fact": "student.academic_status", "operator": "==", "value": "suspended"},
        ],
    }
    assert evaluate_condition(cond_false, sample_working_memory) is False


def test_boolean_not_evaluator(sample_working_memory: WorkingMemory):
    """Verify NOT condition evaluation (inverts sub-condition)."""
    # NOT(False) -> True
    cond_not_false = {
        "type": "NOT",
        "condition": {
            "fact": "student.academic_status",
            "operator": "==",
            "value": "probation",
        },
    }
    assert evaluate_condition(cond_not_false, sample_working_memory) is True

    # NOT(True) -> False
    cond_not_true = {
        "type": "NOT",
        "condition": {
            "fact": "student.academic_status",
            "operator": "==",
            "value": "active",
        },
    }
    assert evaluate_condition(cond_not_true, sample_working_memory) is False


def test_nested_boolean_conditions(sample_working_memory: WorkingMemory):
    """Verify nested Boolean condition tree: AND(gpa >= 7.0, OR('python' IN skills, 'java' IN skills))."""
    nested_cond = {
        "type": "AND",
        "conditions": [
            {"fact": "student.gpa", "operator": ">=", "value": 7.0},
            {
                "type": "OR",
                "conditions": [
                    {"fact": "student.skills", "operator": "IN", "value": "python"},
                    {"fact": "student.skills", "operator": "IN", "value": "java"},
                ],
            },
        ],
    }
    assert evaluate_condition(nested_cond, sample_working_memory) is True

    # Fail the OR branch by requiring unavailable skills
    nested_cond_fail_or = {
        "type": "AND",
        "conditions": [
            {"fact": "student.gpa", "operator": ">=", "value": 7.0},
            {
                "type": "OR",
                "conditions": [
                    {"fact": "student.skills", "operator": "IN", "value": "rust"},
                    {"fact": "student.skills", "operator": "IN", "value": "scala"},
                ],
            },
        ],
    }
    assert evaluate_condition(nested_cond_fail_or, sample_working_memory) is False


def test_pydantic_condition_model_evaluation(sample_working_memory: WorkingMemory):
    """Verify that condition evaluator directly evaluates Pydantic condition model instances."""
    simple = SimpleCondition(field="student.gpa", operator=ComparisonOperator.GREATER_THAN_OR_EQUAL, value=7.0)
    assert evaluate_condition(simple, sample_working_memory) is True

    compound = CompoundCondition(
        operator=LogicalOperator.AND,
        conditions=[
            SimpleCondition(field="student.gpa", operator=ComparisonOperator.GREATER_THAN_OR_EQUAL, value=7.0),
            SimpleCondition(field="student.academic_status", operator=ComparisonOperator.EQUALS, value="active"),
        ],
    )
    assert evaluate_condition(compound, sample_working_memory) is True


# =============================================================================
# 4. Error Handling & Malformed Condition Validation
# =============================================================================

def test_unknown_condition_type_raises_error(sample_working_memory: WorkingMemory):
    """Verify that unknown condition type raises UnknownConditionTypeError."""
    with pytest.raises(UnknownConditionTypeError) as exc_info:
        evaluate_condition({"type": "XOR_UNKNOWN", "conditions": []}, sample_working_memory)

    assert "Unrecognized condition structure" in str(exc_info.value)


def test_malformed_conditions_rejected(sample_working_memory: WorkingMemory):
    """Verify that malformed conditions fail clearly with MalformedRuleError."""
    # Empty AND conditions
    with pytest.raises(MalformedRuleError):
        evaluate_condition({"type": "AND", "conditions": []}, sample_working_memory)

    # Empty OR conditions
    with pytest.raises(MalformedRuleError):
        evaluate_condition({"type": "OR", "conditions": []}, sample_working_memory)

    # Missing NOT target
    with pytest.raises(MalformedRuleError):
        evaluate_condition({"type": "NOT"}, sample_working_memory)

    # Comparison missing operator
    with pytest.raises(MalformedRuleError):
        evaluate_condition({"fact": "student.gpa", "value": 7.0}, sample_working_memory)

    # Comparison missing value
    with pytest.raises(MalformedRuleError):
        evaluate_condition({"fact": "student.gpa", "operator": ">="}, sample_working_memory)

    # None condition
    with pytest.raises(MalformedRuleError):
        evaluate_condition(None, sample_working_memory)


# =============================================================================
# 5. Rule Matcher & Inference Primitives
# =============================================================================

@pytest.fixture
def eligibility_rule() -> Rule:
    """Fixture providing a complete validated academic eligibility rule."""
    return Rule(
        id="RULE_AI_ELIGIBILITY",
        name="AI Course Eligibility Policy",
        description="Student must have GPA >= 7.0, completed CS101, and possess python skill.",
        priority=85,
        status=RuleStatus.ACTIVE,
        condition=CompoundCondition(
            operator=LogicalOperator.AND,
            conditions=[
                SimpleCondition(field="student.gpa", operator=ComparisonOperator.GREATER_THAN_OR_EQUAL, value=7.0),
                SimpleCondition(field="student.completed_courses", operator=ComparisonOperator.IN, value="CS101"),
                SimpleCondition(field="student.skills", operator=ComparisonOperator.IN, value="python"),
            ],
        ),
        consequence=RuleConsequence(
            action="grant_ai_eligibility",
            params={"student.eligible_for_ai": True, "clearance": "full"},
            description="Student is cleared for AI course enrollment.",
        ),
        metadata={"department": "CS", "version": "1.0"},
    )


def test_rule_matcher_matching(eligibility_rule: Rule, sample_working_memory: WorkingMemory):
    """Verify rule matcher returns True for a matching student."""
    assert RuleMatcher.matches(eligibility_rule, sample_working_memory) is True
    assert matches(eligibility_rule, sample_working_memory) is True


def test_rule_matcher_non_matching(eligibility_rule: Rule):
    """Verify rule matcher returns False when conditions are not satisfied."""
    non_matching_wm = WorkingMemory(
        {
            "student": {
                "id": "student_003",
                "name": "Carlos Gomez",
                "gpa": 6.4,  # Below 7.0
                "completed_courses": ["MA101"],  # Missing CS101
                "skills": ["calculus"],  # Missing python
                "academic_status": "probation",
            }
        }
    )
    assert RuleMatcher.matches(eligibility_rule, non_matching_wm) is False
    assert matches(eligibility_rule, non_matching_wm) is False


def test_inference_engine_evaluate_rule(eligibility_rule: Rule, sample_working_memory: WorkingMemory):
    """Verify evaluate_rule produces structured result without mutating working memory."""
    result: RuleExecutionResult = InferenceEngine.evaluate_rule(eligibility_rule, sample_working_memory)

    assert result.rule_id == "RULE_AI_ELIGIBILITY"
    assert result.rule_name == "AI Course Eligibility Policy"
    assert result.matched is True
    assert result.derived_facts == {"student.eligible_for_ai": True, "clearance": "full"}

    # Working memory must remain unmutated by evaluate_rule
    assert sample_working_memory.has_fact("student.eligible_for_ai") is False


def test_inference_engine_apply_rule(eligibility_rule: Rule, sample_working_memory: WorkingMemory):
    """Verify apply_rule asserts derived facts into working memory upon match."""
    result: RuleExecutionResult = InferenceEngine.apply_rule(eligibility_rule, sample_working_memory)

    assert result.matched is True
    assert result.derived_facts == {"student.eligible_for_ai": True, "clearance": "full"}

    # Working memory now contains derived facts
    assert sample_working_memory.has_fact("student.eligible_for_ai") is True
    assert sample_working_memory.get_fact("student.eligible_for_ai") is True
    assert sample_working_memory.get_derived_facts()["student.eligible_for_ai"] is True


def test_inference_engine_non_matching_application(eligibility_rule: Rule):
    """Verify apply_rule does not assert facts when rule does not match."""
    wm = WorkingMemory({"student": {"gpa": 5.0, "completed_courses": [], "skills": []}})
    result = apply_rule(eligibility_rule, wm)

    assert result.matched is False
    assert result.derived_facts == {}
    assert len(wm.get_derived_facts()) == 0


# =============================================================================
# 6. Security & Determinism
# =============================================================================

def test_security_against_executable_code_in_rules():
    """Verify that attempting to include executable code or eval expressions is rejected."""
    # Attempting to supply unapproved fields fails Pydantic schema validation
    with pytest.raises(Exception):
        Rule.model_validate(
            {
                "id": "RULE_EXPLOIT",
                "name": "Exploit Attempt",
                "description": "Malicious payload injection",
                "condition": {
                    "field": "student.gpa",
                    "operator": "==",
                    "value": "__import__('os').system('echo hacked')",
                },
                "consequence": {
                    "action": "run",
                    "eval": "exec('import os')",
                },
            }
        )


def test_evaluation_determinism(eligibility_rule: Rule, sample_working_memory: WorkingMemory):
    """Verify that repeated evaluation produces 100% identical results."""
    baseline_result = evaluate_rule(eligibility_rule, sample_working_memory)

    for _ in range(50):
        run_result = evaluate_rule(eligibility_rule, sample_working_memory)
        assert run_result.matched == baseline_result.matched
        assert run_result.derived_facts == baseline_result.derived_facts
        assert run_result.rule_id == baseline_result.rule_id
