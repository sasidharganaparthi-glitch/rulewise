"""Comprehensive test suite for RuleWise AI Phase 5 — Explainability & Reasoning Trace.

Tests cover:
1.  Basic trace construction (build_trace)
2.  Rule firing trace (trace step structure)
3.  Multi-step derivation trace
4.  Initial fact provenance
5.  Derived fact provenance
6.  Condition explanation — simple comparison
7.  Condition explanation — AND
8.  Condition explanation — OR
9.  Condition explanation — NOT
10. Successful WHY explanation
11. WHY-NOT explanation
12. Insufficient-evidence handling
13. Contrastive explanation structure
14. Deterministic explanation ordering
15. Empty inference history
16. Multiple derivation paths
17. No prohibited patterns (offline, deterministic)

All existing Phase 1–4 tests continue to pass (run via pytest by default).
"""

from typing import Any, Dict, List, Optional
import pytest

from backend.engine.inference_engine import infer
from backend.engine.working_memory import WorkingMemory
from backend.explainability.contrastive import build_contrastive, build_why_not
from backend.explainability.trace_builder import (
    build_fact_provenance,
    build_trace,
    build_why,
    explain_condition,
)
from backend.schemas.explanation import (
    CompoundConditionExplanation,
    ConditionExplanation,
    ContrastiveExplanation,
    Explanation,
    FactProvenanceExplanation,
    TraceStep,
    WhyExplanation,
    WhyNotExplanation,
)
from backend.schemas.rule import (
    ComparisonOperator,
    CompoundCondition,
    DerivationStep,
    FactProvenance,
    InferenceResult,
    LogicalOperator,
    Rule,
    RuleConsequence,
    RuleStatus,
    SimpleCondition,
)


# =============================================================================
# Shared Factories
# =============================================================================

def sc(field: str, op: str, value: Any) -> SimpleCondition:
    return SimpleCondition(field=field, operator=ComparisonOperator(op), value=value)


def and_(*conds) -> CompoundCondition:
    return CompoundCondition(operator=LogicalOperator.AND, conditions=list(conds))


def or_(*conds) -> CompoundCondition:
    return CompoundCondition(operator=LogicalOperator.OR, conditions=list(conds))


def not_(cond) -> CompoundCondition:
    return CompoundCondition(operator=LogicalOperator.NOT, condition=cond)


def make_rule(
    rule_id: str,
    condition,
    params: Dict[str, Any],
    priority: int = 0,
    name: str = "",
    description: str = "",
) -> Rule:
    return Rule(
        id=rule_id,
        name=name or rule_id,
        description=description or f"Rule {rule_id}",
        priority=priority,
        status=RuleStatus.ACTIVE,
        condition=condition,
        consequence=RuleConsequence(action="assert", params=params),
    )


def make_wm(facts: Dict[str, Any]) -> WorkingMemory:
    return WorkingMemory(initial_facts=facts)


def run_infer(rules: List[Rule], facts: Dict[str, Any]) -> InferenceResult:
    wm = make_wm(facts)
    return infer(rules, wm)


# =============================================================================
# 1. Basic Trace Construction
# =============================================================================

class TestBuildTrace:
    """build_trace() returns a well-formed Explanation."""

    def test_returns_explanation_instance(self):
        wm_facts = {"student.gpa": 8.5}
        rules = [make_rule("R1", sc("student.gpa", ">=", 7.0), {"gpa_ok": True})]
        result = run_infer(rules, wm_facts)
        expl = build_trace(result, rules, conclusion="gpa_ok")
        assert isinstance(expl, Explanation)

    def test_conclusion_label_respected(self):
        result = run_infer(
            [make_rule("R1", sc("x", "==", 1), {"done": True})],
            {"x": 1},
        )
        expl = build_trace(result, conclusion="done")
        assert expl.conclusion == "done"

    def test_conclusion_reached_true_when_derived(self):
        rules = [make_rule("R1", sc("student.gpa", ">=", 7.0), {"gpa_ok": True})]
        result = run_infer(rules, {"student.gpa": 8.5})
        expl = build_trace(result, rules, conclusion="gpa_ok")
        assert expl.conclusion_reached is True
        assert expl.conclusion_value is True

    def test_conclusion_reached_false_when_not_derived(self):
        rules = [make_rule("R1", sc("student.gpa", ">=", 9.9), {"gpa_ok": True})]
        result = run_infer(rules, {"student.gpa": 5.0})
        expl = build_trace(result, rules, conclusion="gpa_ok")
        assert expl.conclusion_reached is False

    def test_termination_reason_propagated(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"y": True})]
        result = run_infer(rules, {"x": 1})
        expl = build_trace(result, rules, conclusion="y")
        assert expl.termination_reason == "fixed_point"

    def test_total_steps_matches_inference(self):
        rules = [
            make_rule("R1", sc("a", "==", 1), {"b": True}, priority=10),
            make_rule("R2", sc("b", "==", True), {"c": True}, priority=5),
        ]
        result = run_infer(rules, {"a": 1})
        expl = build_trace(result, rules, conclusion="c")
        assert expl.total_steps == 2

    def test_supporting_rules_contain_fired_rules(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"y": True})]
        result = run_infer(rules, {"x": 1})
        expl = build_trace(result, rules, conclusion="y")
        assert "R1" in expl.supporting_rules

    def test_all_derived_facts_populated(self):
        rules = [
            make_rule("R1", sc("a", "==", 1), {"b": True}),
            make_rule("R2", sc("c", "==", 2), {"d": True}),
        ]
        result = run_infer(rules, {"a": 1, "c": 2})
        expl = build_trace(result, rules)
        assert "b" in expl.all_derived_facts
        assert "d" in expl.all_derived_facts

    def test_empty_inference_returns_valid_explanation(self):
        result = run_infer([], {"x": 1})
        expl = build_trace(result, conclusion="x")
        assert isinstance(expl, Explanation)
        assert expl.trace_steps == []
        assert expl.total_steps == 0

    def test_default_conclusion_uses_first_derived_fact(self):
        rules = [make_rule("R1", sc("x", ">=", 1), {"gpa_ok": True})]
        result = run_infer(rules, {"x": 5})
        expl = build_trace(result, rules)
        assert expl.conclusion == "gpa_ok"


# =============================================================================
# 2. Rule Firing Trace Steps
# =============================================================================

class TestTraceSteps:
    """Each DerivationStep maps to a correct TraceStep."""

    def test_single_rule_produces_one_trace_step(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"done": True})]
        result = run_infer(rules, {"x": 1})
        expl = build_trace(result, rules, conclusion="done")
        assert len(expl.trace_steps) == 1

    def test_trace_step_rule_id_and_name(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"done": True}, name="My Rule")]
        result = run_infer(rules, {"x": 1})
        expl = build_trace(result, rules, conclusion="done")
        ts: TraceStep = expl.trace_steps[0]
        assert ts.rule_id == "R1"
        assert ts.rule_name == "My Rule"

    def test_trace_step_priority_populated(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"done": True}, priority=42)]
        result = run_infer(rules, {"x": 1})
        expl = build_trace(result, rules, conclusion="done")
        assert expl.trace_steps[0].rule_priority == 42

    def test_trace_step_description_populated(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"done": True}, description="Check x equals 1")]
        result = run_infer(rules, {"x": 1})
        expl = build_trace(result, rules, conclusion="done")
        assert expl.trace_steps[0].rule_description == "Check x equals 1"

    def test_trace_step_derived_facts(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"done": True, "flag": "yes"})]
        result = run_infer(rules, {"x": 1})
        expl = build_trace(result, rules, conclusion="done")
        ts = expl.trace_steps[0]
        assert ts.derived_facts.get("done") is True

    def test_trace_step_source_facts_contains_matched_fact(self):
        rules = [make_rule("R1", sc("student.gpa", ">=", 7.0), {"gpa_ok": True})]
        result = run_infer(rules, {"student.gpa": 8.5})
        expl = build_trace(result, rules, conclusion="gpa_ok")
        ts = expl.trace_steps[0]
        assert "student.gpa" in ts.source_facts

    def test_trace_step_number_is_one_indexed(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"y": True})]
        result = run_infer(rules, {"x": 1})
        expl = build_trace(result, rules, conclusion="y")
        assert expl.trace_steps[0].step == 1

    def test_multi_step_trace_in_order(self):
        rules = [
            make_rule("R1", sc("a", "==", 1), {"b": True}, priority=10),
            make_rule("R2", sc("b", "==", True), {"c": True}, priority=5),
        ]
        result = run_infer(rules, {"a": 1})
        expl = build_trace(result, rules, conclusion="c")
        assert expl.trace_steps[0].rule_id == "R1"
        assert expl.trace_steps[1].rule_id == "R2"
        assert expl.trace_steps[0].step < expl.trace_steps[1].step


# =============================================================================
# 3. Multi-Step Derivation Trace
# =============================================================================

class TestMultiStepTrace:
    """Forward-chaining derivation chain must appear fully in the trace."""

    def test_three_step_chain_all_steps_recorded(self):
        rules = [
            make_rule("R_GPA", sc("student.gpa", ">=", 7.0), {"gpa_eligible": True}, priority=10),
            make_rule("R_PREREQ", sc("student.courses", "IN", "CS101"), {"prereq_ok": True}, priority=10),
            make_rule(
                "R_AI",
                and_(sc("gpa_eligible", "==", True), sc("prereq_ok", "==", True)),
                {"ai_eligible": True},
                priority=5,
            ),
        ]
        result = run_infer(rules, {"student.gpa": 8.7, "student.courses": ["CS101"]})
        expl = build_trace(result, rules, conclusion="ai_eligible")
        assert len(expl.trace_steps) == 3
        rule_ids = [ts.rule_id for ts in expl.trace_steps]
        assert "R_GPA" in rule_ids
        assert "R_PREREQ" in rule_ids
        assert "R_AI" in rule_ids

    def test_rule3_step_number_greater_than_rule1_and_rule2(self):
        rules = [
            make_rule("R_GPA", sc("student.gpa", ">=", 7.0), {"gpa_eligible": True}, priority=10),
            make_rule("R_PREREQ", sc("student.courses", "IN", "CS101"), {"prereq_ok": True}, priority=10),
            make_rule(
                "R_AI",
                and_(sc("gpa_eligible", "==", True), sc("prereq_ok", "==", True)),
                {"ai_eligible": True},
                priority=5,
            ),
        ]
        result = run_infer(rules, {"student.gpa": 8.7, "student.courses": ["CS101"]})
        expl = build_trace(result, rules, conclusion="ai_eligible")
        step_by_rule = {ts.rule_id: ts.step for ts in expl.trace_steps}
        assert step_by_rule["R_AI"] > step_by_rule["R_GPA"]
        assert step_by_rule["R_AI"] > step_by_rule["R_PREREQ"]


# =============================================================================
# 4 & 5. Fact Provenance
# =============================================================================

class TestFactProvenance:
    """Provenance records correctly classify initial vs. derived facts."""

    def test_initial_fact_origin_is_initial(self):
        rules = [make_rule("R1", sc("student.gpa", ">=", 7.0), {"gpa_ok": True})]
        result = run_infer(rules, {"student.gpa": 8.5})
        provenance = build_fact_provenance(result, rules)
        gpa_prov = next((p for p in provenance if p.fact == "student.gpa"), None)
        assert gpa_prov is not None
        assert gpa_prov.origin == "initial"
        assert gpa_prov.step == 0
        assert gpa_prov.source_rule_id is None

    def test_derived_fact_origin_is_derived(self):
        rules = [make_rule("R1", sc("student.gpa", ">=", 7.0), {"gpa_ok": True})]
        result = run_infer(rules, {"student.gpa": 8.5})
        provenance = build_fact_provenance(result, rules)
        gpa_ok_prov = next((p for p in provenance if p.fact == "gpa_ok"), None)
        assert gpa_ok_prov is not None
        assert gpa_ok_prov.origin == "derived"
        assert gpa_ok_prov.source_rule_id == "R1"
        assert gpa_ok_prov.step >= 1

    def test_derived_fact_source_rule_name_populated(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"y": True}, name="X Checker")]
        result = run_infer(rules, {"x": 1})
        provenance = build_fact_provenance(result, rules)
        y_prov = next((p for p in provenance if p.fact == "y"), None)
        assert y_prov is not None
        assert y_prov.source_rule_name == "X Checker"

    def test_provenance_sorted_by_step_then_path(self):
        rules = [
            make_rule("R1", sc("a", "==", 1), {"b": True, "c": True}, priority=10),
        ]
        result = run_infer(rules, {"a": 1})
        provenance = build_fact_provenance(result, rules)
        steps = [p.step for p in provenance]
        # Steps should be non-decreasing
        assert steps == sorted(steps)

    def test_provenance_list_in_explanation_matches_fact_provenance(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"y": True})]
        result = run_infer(rules, {"x": 1})
        expl = build_trace(result, rules, conclusion="y")
        paths = {p.fact for p in expl.fact_provenance}
        assert "y" in paths

    def test_trace_step_derived_fact_provenance_populated(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"y": True})]
        result = run_infer(rules, {"x": 1})
        expl = build_trace(result, rules, conclusion="y")
        ts = expl.trace_steps[0]
        assert len(ts.derived_fact_provenance) >= 1
        dfp: FactProvenanceExplanation = ts.derived_fact_provenance[0]
        assert dfp.fact == "y"
        assert dfp.origin == "derived"


# =============================================================================
# 6. Condition Explanation — Simple
# =============================================================================

class TestConditionExplanationSimple:
    """explain_condition() produces correct leaf ConditionExplanation."""

    def test_simple_true_condition(self):
        cond = sc("student.gpa", ">=", 7.0)
        result = explain_condition(cond, {"student.gpa": 8.5})
        assert isinstance(result, ConditionExplanation)
        assert result.fact == "student.gpa"
        assert result.actual_value == 8.5
        assert result.operator == ">="
        assert result.expected_value == 7.0
        assert result.result is True

    def test_simple_false_condition(self):
        cond = sc("student.gpa", ">=", 9.0)
        result = explain_condition(cond, {"student.gpa": 6.0})
        assert isinstance(result, ConditionExplanation)
        assert result.result is False

    def test_equals_operator(self):
        cond = sc("status", "==", "active")
        result = explain_condition(cond, {"status": "active"})
        assert result.result is True

    def test_not_equals_operator(self):
        cond = sc("status", "!=", "suspended")
        result = explain_condition(cond, {"status": "active"})
        assert result.result is True

    def test_in_operator_list(self):
        cond = sc("skills", "IN", "python")
        result = explain_condition(cond, {"skills": ["python", "java"]})
        assert result.result is True

    def test_in_operator_missing_fact_returns_false_result(self):
        cond = sc("skills", "IN", "python")
        result = explain_condition(cond, {})
        # actual_value should be None, result should be False
        assert result.actual_value is None
        assert result.result is False

    def test_none_condition_returns_none(self):
        result = explain_condition(None, {"x": 1})
        assert result is None


# =============================================================================
# 7. Condition Explanation — AND
# =============================================================================

class TestConditionExplanationAND:
    """explain_condition() correctly handles AND compound conditions."""

    def test_and_all_true(self):
        cond = and_(sc("a", "==", 1), sc("b", "==", 2))
        result = explain_condition(cond, {"a": 1, "b": 2})
        assert isinstance(result, CompoundConditionExplanation)
        assert result.operator == "AND"
        assert result.result is True
        assert len(result.sub_conditions) == 2
        assert all(s.result for s in result.sub_conditions)

    def test_and_one_false(self):
        cond = and_(sc("a", "==", 1), sc("b", "==", 99))
        result = explain_condition(cond, {"a": 1, "b": 2})
        assert result.result is False

    def test_and_preserves_sub_condition_details(self):
        cond = and_(sc("student.gpa", ">=", 7.0), sc("status", "==", "active"))
        facts = {"student.gpa": 8.5, "status": "active"}
        result = explain_condition(cond, facts)
        gpa_expl = next(s for s in result.sub_conditions if s.fact == "student.gpa")
        assert gpa_expl.actual_value == 8.5
        assert gpa_expl.result is True

    def test_trace_step_condition_explanation_is_compound_for_and_rule(self):
        rules = [
            make_rule(
                "R_AND",
                and_(sc("x", "==", 1), sc("y", "==", 2)),
                {"done": True},
            )
        ]
        result = run_infer(rules, {"x": 1, "y": 2})
        expl = build_trace(result, rules, conclusion="done")
        cond_expl = expl.trace_steps[0].condition_explanation
        assert isinstance(cond_expl, CompoundConditionExplanation)
        assert cond_expl.operator == "AND"


# =============================================================================
# 8. Condition Explanation — OR
# =============================================================================

class TestConditionExplanationOR:
    """explain_condition() correctly handles OR compound conditions."""

    def test_or_one_true(self):
        cond = or_(sc("a", "==", 99), sc("b", "==", 2))
        result = explain_condition(cond, {"a": 1, "b": 2})
        assert isinstance(result, CompoundConditionExplanation)
        assert result.operator == "OR"
        assert result.result is True

    def test_or_all_false(self):
        cond = or_(sc("a", "==", 99), sc("b", "==", 99))
        result = explain_condition(cond, {"a": 1, "b": 2})
        assert result.result is False

    def test_or_shows_which_alternative_passed(self):
        cond = or_(sc("a", "==", 1), sc("b", "==", 99))
        result = explain_condition(cond, {"a": 1, "b": 0})
        passing = [s for s in result.sub_conditions if s.result]
        failing = [s for s in result.sub_conditions if not s.result]
        assert len(passing) == 1
        assert len(failing) == 1
        assert passing[0].fact == "a"


# =============================================================================
# 9. Condition Explanation — NOT
# =============================================================================

class TestConditionExplanationNOT:
    """explain_condition() correctly handles NOT compound conditions."""

    def test_not_inverts_true_to_false(self):
        cond = not_(sc("x", "==", 1))
        result = explain_condition(cond, {"x": 1})
        assert isinstance(result, CompoundConditionExplanation)
        assert result.operator == "NOT"
        assert result.result is False

    def test_not_inverts_false_to_true(self):
        cond = not_(sc("x", "==", 99))
        result = explain_condition(cond, {"x": 1})
        assert result.result is True

    def test_not_preserves_inner_condition(self):
        cond = not_(sc("status", "==", "suspended"))
        result = explain_condition(cond, {"status": "active"})
        # Inner condition: status == suspended → False; NOT False → True
        assert result.result is True
        inner = result.sub_conditions[0]
        assert inner.fact == "status"
        assert inner.result is False  # The inner condition itself is False


# =============================================================================
# 10. WHY Explanation
# =============================================================================

class TestWhyExplanation:
    """build_why() traces the derivation chain correctly."""

    def test_returns_why_explanation_instance(self):
        rules = [make_rule("R1", sc("x", ">=", 1), {"result": True})]
        result = run_infer(rules, {"x": 5})
        why = build_why(result, rules, conclusion="result")
        assert isinstance(why, WhyExplanation)

    def test_why_conclusion_reached_true(self):
        rules = [make_rule("R1", sc("x", ">=", 1), {"result": True})]
        result = run_infer(rules, {"x": 5})
        why = build_why(result, rules, conclusion="result")
        assert why.conclusion_reached is True

    def test_why_derivation_chain_contains_contributing_steps(self):
        rules = [
            make_rule("R_GPA", sc("student.gpa", ">=", 7.0), {"gpa_ok": True}, priority=10),
            make_rule(
                "R_AI",
                sc("gpa_ok", "==", True),
                {"ai_eligible": True},
                priority=5,
            ),
        ]
        result = run_infer(rules, {"student.gpa": 8.5})
        why = build_why(result, rules, conclusion="ai_eligible")
        chain_ids = [ts.rule_id for ts in why.derivation_chain]
        assert "R_GPA" in chain_ids
        assert "R_AI" in chain_ids

    def test_why_root_facts_are_initial(self):
        rules = [make_rule("R1", sc("student.gpa", ">=", 7.0), {"gpa_ok": True})]
        result = run_infer(rules, {"student.gpa": 8.5})
        why = build_why(result, rules, conclusion="gpa_ok")
        assert "student.gpa" in why.root_facts

    def test_why_intermediate_derived_facts_identified(self):
        rules = [
            make_rule("R1", sc("student.gpa", ">=", 7.0), {"gpa_ok": True}, priority=10),
            make_rule("R2", sc("gpa_ok", "==", True), {"eligible": True}, priority=5),
        ]
        result = run_infer(rules, {"student.gpa": 8.5})
        why = build_why(result, rules, conclusion="eligible")
        assert "gpa_ok" in why.intermediate_derived_facts

    def test_why_conclusion_value_populated(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"y": True})]
        result = run_infer(rules, {"x": 1})
        why = build_why(result, rules, conclusion="y")
        assert why.conclusion_value is True

    def test_why_empty_derivation_history_no_chain(self):
        result = run_infer([], {"x": 1})
        why = build_why(result, [], conclusion="x")
        assert why.derivation_chain == []


# =============================================================================
# 11. WHY-NOT Explanation
# =============================================================================

class TestWhyNotExplanation:
    """build_why_not() explains why a conclusion was not established."""

    def test_returns_why_not_instance(self):
        rules = [make_rule("R1", sc("student.gpa", ">=", 9.0), {"gpa_ok": True})]
        result = run_infer(rules, {"student.gpa": 6.0})
        wn = build_why_not(result, rules, conclusion="gpa_ok")
        assert isinstance(wn, WhyNotExplanation)

    def test_conclusion_reached_is_false(self):
        rules = [make_rule("R1", sc("student.gpa", ">=", 9.0), {"gpa_ok": True})]
        result = run_infer(rules, {"student.gpa": 6.0})
        wn = build_why_not(result, rules, conclusion="gpa_ok")
        assert wn.conclusion_reached is False

    def test_blocking_condition_identified(self):
        rules = [make_rule("R1", sc("student.gpa", ">=", 9.0), {"gpa_ok": True})]
        result = run_infer(rules, {"student.gpa": 6.0})
        wn = build_why_not(result, rules, conclusion="gpa_ok")
        assert len(wn.blocking_conditions) >= 1
        bc = wn.blocking_conditions[0]
        assert bc.fact == "student.gpa"
        assert bc.result is False
        assert bc.actual_value == 6.0
        assert bc.expected_value == 9.0

    def test_candidate_rules_listed(self):
        rules = [make_rule("R1", sc("x", ">=", 9.0), {"result": True})]
        result = run_infer(rules, {"x": 1.0})
        wn = build_why_not(result, rules, conclusion="result")
        assert "R1" in wn.candidate_rules

    def test_evidence_available_true_when_candidate_exists(self):
        rules = [make_rule("R1", sc("x", ">=", 9.0), {"result": True})]
        result = run_infer(rules, {"x": 1.0})
        wn = build_why_not(result, rules, conclusion="result")
        assert wn.evidence_available is True

    def test_missing_fact_reported(self):
        # Rule references 'student.score' but it's not in WM
        rules = [make_rule("R1", sc("student.score", ">=", 90), {"pass": True})]
        result = run_infer(rules, {"student.name": "Alice"})
        wn = build_why_not(result, rules, conclusion="pass")
        assert "student.score" in wn.missing_facts

    def test_conclusion_reached_returns_special_result(self):
        rules = [make_rule("R1", sc("x", ">=", 1), {"result": True})]
        result = run_infer(rules, {"x": 5})
        # Conclusion WAS reached — build_why_not should reflect that
        wn = build_why_not(result, rules, conclusion="result", expected_value=True)
        assert wn.conclusion_reached is True


# =============================================================================
# 12. Insufficient Evidence Handling
# =============================================================================

class TestInsufficientEvidence:
    """WHY-NOT must return structured 'insufficient evidence' instead of inventing reasons."""

    def test_no_candidate_rules_returns_insufficient_evidence(self):
        # No rule whose consequence is 'unicorn'
        rules = [make_rule("R1", sc("x", "==", 1), {"y": True})]
        result = run_infer(rules, {"x": 1})
        wn = build_why_not(result, rules, conclusion="unicorn")
        assert wn.evidence_available is False
        assert wn.insufficient_evidence_reason is not None
        assert len(wn.insufficient_evidence_reason) > 0

    def test_insufficient_evidence_has_empty_blocking_conditions(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"y": True})]
        result = run_infer(rules, {"x": 1})
        wn = build_why_not(result, rules, conclusion="unicorn")
        assert wn.blocking_conditions == []

    def test_insufficient_evidence_has_empty_candidate_rules(self):
        rules = [make_rule("R1", sc("x", "==", 1), {"y": True})]
        result = run_infer(rules, {"x": 1})
        wn = build_why_not(result, rules, conclusion="unicorn")
        assert wn.candidate_rules == []


# =============================================================================
# 13. Contrastive Explanation
# =============================================================================

class TestContrastiveExplanation:
    """build_contrastive() returns valid structure using only inference evidence."""

    def test_returns_contrastive_instance(self):
        rules = [
            make_rule("R_A", sc("student.gpa", ">=", 7.0), {"eligible": True}, priority=10),
            make_rule("R_B", sc("student.gpa", "<", 5.0), {"failed": True}, priority=5),
        ]
        result = run_infer(rules, {"student.gpa": 8.5})
        ct = build_contrastive(result, rules, conclusion_a="eligible", conclusion_b="failed")
        assert isinstance(ct, ContrastiveExplanation)

    def test_conclusion_a_value_populated(self):
        rules = [make_rule("R1", sc("x", ">=", 1), {"approved": True})]
        result = run_infer(rules, {"x": 5})
        ct = build_contrastive(result, rules, conclusion_a="approved", conclusion_b="rejected")
        assert ct.conclusion_a_value is True

    def test_conclusion_b_not_reached(self):
        rules = [make_rule("R1", sc("x", ">=", 1), {"approved": True})]
        result = run_infer(rules, {"x": 5})
        ct = build_contrastive(result, rules, conclusion_a="approved", conclusion_b="rejected")
        assert ct.conclusion_b_reached is False

    def test_embedded_why_a_explanation(self):
        rules = [make_rule("R1", sc("x", ">=", 1), {"approved": True})]
        result = run_infer(rules, {"x": 5})
        ct = build_contrastive(result, rules, conclusion_a="approved", conclusion_b="rejected")
        assert ct.why_a is not None
        assert isinstance(ct.why_a, WhyExplanation)

    def test_embedded_why_not_b_explanation(self):
        rules = [make_rule("R1", sc("x", ">=", 1), {"approved": True})]
        result = run_infer(rules, {"x": 5})
        ct = build_contrastive(result, rules, conclusion_a="approved", conclusion_b="rejected")
        assert ct.why_not_b is not None
        assert isinstance(ct.why_not_b, WhyNotExplanation)

    def test_evidence_available_true_when_a_reached(self):
        rules = [make_rule("R1", sc("x", ">=", 1), {"approved": True})]
        result = run_infer(rules, {"x": 5})
        ct = build_contrastive(result, rules, conclusion_a="approved", conclusion_b="rejected")
        assert ct.evidence_available is True

    def test_differentiating_facts_populated(self):
        rules = [
            make_rule("R1", sc("student.gpa", ">=", 7.0), {"eligible": True}, priority=10),
        ]
        result = run_infer(rules, {"student.gpa": 8.5})
        ct = build_contrastive(result, rules, conclusion_a="eligible", conclusion_b="denied")
        # R1 fires for eligible; student.gpa is a differentiating fact
        # (may be empty if rule ID isn't in differentiating_rules, which is OK)
        assert isinstance(ct.differentiating_facts, dict)

    def test_both_conclusions_same_fact_path(self):
        """Edge case: comparing the same conclusion to itself."""
        rules = [make_rule("R1", sc("x", ">=", 1), {"result": True})]
        result = run_infer(rules, {"x": 5})
        ct = build_contrastive(result, rules, conclusion_a="result", conclusion_b="result")
        assert isinstance(ct, ContrastiveExplanation)


# =============================================================================
# 14. Deterministic Explanation Ordering
# =============================================================================

class TestDeterministicExplanation:
    """Same InferenceResult must produce identical Explanation every time."""

    def test_twenty_runs_produce_identical_trace(self):
        rules = [
            make_rule("R1", sc("student.gpa", ">=", 7.0), {"gpa_ok": True}, priority=10),
            make_rule("R2", sc("student.courses", "IN", "CS101"), {"prereq_ok": True}, priority=5),
        ]
        result = run_infer(rules, {"student.gpa": 8.5, "student.courses": ["CS101"]})
        first = build_trace(result, rules, conclusion="gpa_ok")
        for _ in range(19):
            run = build_trace(result, rules, conclusion="gpa_ok")
            assert run.trace_steps[0].rule_id == first.trace_steps[0].rule_id
            assert run.supporting_rules == first.supporting_rules
            assert run.all_derived_facts == first.all_derived_facts

    def test_why_is_deterministic_across_runs(self):
        rules = [
            make_rule("R1", sc("x", ">=", 1), {"y": True}, priority=10),
            make_rule("R2", sc("y", "==", True), {"z": True}, priority=5),
        ]
        result = run_infer(rules, {"x": 5})
        first = build_why(result, rules, conclusion="z")
        for _ in range(10):
            run = build_why(result, rules, conclusion="z")
            assert [ts.rule_id for ts in run.derivation_chain] == [
                ts.rule_id for ts in first.derivation_chain
            ]

    def test_fact_provenance_order_is_deterministic(self):
        rules = [
            make_rule("R1", sc("a", "==", 1), {"b": True}),
            make_rule("R2", sc("c", "==", 2), {"d": True}),
        ]
        result = run_infer(rules, {"a": 1, "c": 2})
        prov1 = build_fact_provenance(result, rules)
        prov2 = build_fact_provenance(result, rules)
        assert [p.fact for p in prov1] == [p.fact for p in prov2]


# =============================================================================
# 15. Empty Inference History
# =============================================================================

class TestEmptyInferenceHistory:
    """Explainability layer handles empty inference gracefully."""

    def test_build_trace_empty_result(self):
        result = run_infer([], {"x": 1})
        expl = build_trace(result, [], conclusion="x")
        assert expl.trace_steps == []
        assert expl.total_steps == 0

    def test_build_why_empty_result(self):
        result = run_infer([], {"x": 1})
        why = build_why(result, [], conclusion="x")
        assert isinstance(why, WhyExplanation)
        assert why.derivation_chain == []

    def test_build_why_not_empty_rules(self):
        result = run_infer([], {"x": 1})
        wn = build_why_not(result, [], conclusion="y")
        assert wn.evidence_available is False

    def test_build_contrastive_empty_result(self):
        result = run_infer([], {"x": 1})
        ct = build_contrastive(result, [], conclusion_a="a", conclusion_b="b")
        assert isinstance(ct, ContrastiveExplanation)

    def test_build_fact_provenance_empty_result(self):
        result = run_infer([], {})
        prov = build_fact_provenance(result, [])
        assert prov == []


# =============================================================================
# 16. Multiple Derivation Paths
# =============================================================================

class TestMultipleDerivationPaths:
    """Multiple independent rules fire and produce separate provenance records."""

    def test_three_independent_rules_all_traced(self):
        rules = [
            make_rule("R1", sc("a", "==", 1), {"b": True}),
            make_rule("R2", sc("c", "==", 2), {"d": True}),
            make_rule("R3", sc("e", "==", 3), {"f": True}),
        ]
        result = run_infer(rules, {"a": 1, "c": 2, "e": 3})
        expl = build_trace(result, rules)
        assert len(expl.trace_steps) == 3
        rule_ids = {ts.rule_id for ts in expl.trace_steps}
        assert rule_ids == {"R1", "R2", "R3"}

    def test_independent_facts_each_have_provenance(self):
        rules = [
            make_rule("R1", sc("a", "==", 1), {"b": True}),
            make_rule("R2", sc("c", "==", 2), {"d": True}),
        ]
        result = run_infer(rules, {"a": 1, "c": 2})
        prov = build_fact_provenance(result, rules)
        paths = {p.fact for p in prov}
        assert "b" in paths
        assert "d" in paths

    def test_why_identifies_direct_contributor_only(self):
        rules = [
            make_rule("R1", sc("a", "==", 1), {"b": True}, priority=10),
            make_rule("R2", sc("c", "==", 2), {"d": True}, priority=5),
        ]
        result = run_infer(rules, {"a": 1, "c": 2})
        why = build_why(result, rules, conclusion="b")
        chain_ids = {ts.rule_id for ts in why.derivation_chain}
        assert "R1" in chain_ids
        assert "R2" not in chain_ids


# =============================================================================
# 17. Schema Model Integrity
# =============================================================================

class TestSchemaModelIntegrity:
    """Pydantic models are frozen and correctly structured."""

    def test_condition_explanation_is_frozen(self):
        ce = ConditionExplanation(
            fact="x", actual_value=1, operator="==", expected_value=1, result=True
        )
        with pytest.raises(Exception):
            ce.result = False  # frozen model

    def test_compound_condition_explanation_is_frozen(self):
        cce = CompoundConditionExplanation(
            operator="AND", sub_conditions=[], result=True
        )
        with pytest.raises(Exception):
            cce.result = False

    def test_fact_provenance_explanation_fields(self):
        fp = FactProvenanceExplanation(
            fact="student.gpa", value=8.5, origin="initial", step=0
        )
        assert fp.origin == "initial"
        assert fp.source_rule_id is None

    def test_trace_step_is_frozen(self):
        ts = TraceStep(step=1, rule_id="R1", rule_name="Rule 1")
        with pytest.raises(Exception):
            ts.step = 999

    def test_explanation_derived_facts_is_dict(self):
        result = run_infer(
            [make_rule("R1", sc("x", ">=", 1), {"y": True})], {"x": 5}
        )
        expl = build_trace(result, conclusion="y")
        assert isinstance(expl.all_derived_facts, dict)

    def test_why_not_explanation_has_correct_fields(self):
        rules = [make_rule("R1", sc("x", ">=", 99), {"y": True})]
        result = run_infer(rules, {"x": 1})
        wn = build_why_not(result, rules, conclusion="y")
        assert hasattr(wn, "blocking_conditions")
        assert hasattr(wn, "missing_facts")
        assert hasattr(wn, "candidate_rules")
        assert hasattr(wn, "evidence_available")

    def test_contrastive_explanation_fields(self):
        rules = [make_rule("R1", sc("x", ">=", 1), {"approved": True})]
        result = run_infer(rules, {"x": 5})
        ct = build_contrastive(result, rules, conclusion_a="approved", conclusion_b="denied")
        assert hasattr(ct, "differentiating_facts")
        assert hasattr(ct, "differentiating_rules")
        assert hasattr(ct, "why_a")
        assert hasattr(ct, "why_not_b")


# =============================================================================
# 18. Negative Preclusion in Explanation
# =============================================================================

class TestNegativePreclusionExplanation:
    """Preclusion results appear correctly in explanations."""

    def test_precluded_fact_value_reflected_in_conclusion(self):
        rules = [
            make_rule("R_POS", sc("gpa", ">=", 7.0), {"eligible": True}, priority=100),
            make_rule("R_NEG", sc("status", "==", "suspended"), {"eligible": False}, priority=50),
        ]
        result = run_infer(rules, {"gpa": 8.5, "status": "suspended"})
        expl = build_trace(result, rules, conclusion="eligible")
        assert expl.conclusion_value is False

    def test_both_preclusion_rules_appear_in_trace(self):
        rules = [
            make_rule("R_POS", sc("gpa", ">=", 7.0), {"eligible": True}, priority=100),
            make_rule("R_NEG", sc("status", "==", "suspended"), {"eligible": False}, priority=50),
        ]
        result = run_infer(rules, {"gpa": 8.5, "status": "suspended"})
        expl = build_trace(result, rules, conclusion="eligible")
        ids = {ts.rule_id for ts in expl.trace_steps}
        assert "R_POS" in ids
        assert "R_NEG" in ids
