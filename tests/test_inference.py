"""Comprehensive test suite for the RuleWise AI Forward-Chaining Inference Engine (Phase 4).

Tests cover:
- Multi-step forward chaining
- Fixed-point termination
- Derived-fact propagation and provenance
- Derivation history (DerivationStep records)
- Salience / priority conflict resolution
- Specificity conflict resolution
- Recency conflict resolution
- Rule-ID lexicographic tie-breaking
- Negative preclusion (True then False → False)
- Negative preclusion reversed (False then True → False)
- Cycle detection
- Max depth enforcement
- Determinism (50 identical runs produce identical results)
- State isolation (original WorkingMemory unchanged after infer())
- Empty rule set → immediate fixed point
- No-matching rules → immediate fixed point
- Multiple independent derivations
- Helper utilities (compute_rule_specificity, compute_rule_recency,
  extract_referenced_fact_paths, extract_derived_facts)
"""

import copy
from typing import Any, Dict, List

import pytest

from backend.engine.inference_engine import (
    InferenceEngine,
    compute_rule_recency,
    compute_rule_specificity,
    extract_derived_facts,
    extract_referenced_fact_paths,
    infer,
)
from backend.engine.working_memory import WorkingMemory
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
# Helper Factories
# =============================================================================

def make_simple_condition(field: str, op: str, value: Any) -> SimpleCondition:
    """Create a SimpleCondition with the given field, operator, and value."""
    return SimpleCondition(field=field, operator=ComparisonOperator(op), value=value)


def make_and(*conditions) -> CompoundCondition:
    """Create a CompoundCondition with AND logic."""
    return CompoundCondition(operator=LogicalOperator.AND, conditions=list(conditions))


def make_or(*conditions) -> CompoundCondition:
    """Create a CompoundCondition with OR logic."""
    return CompoundCondition(operator=LogicalOperator.OR, conditions=list(conditions))


def make_rule(
    rule_id: str,
    condition,
    consequence_params: Dict[str, Any],
    action: str = "assert",
    priority: int = 0,
    status: RuleStatus = RuleStatus.ACTIVE,
    name: str = "",
    description: str = "",
) -> Rule:
    """Build a Rule from simplified parameters."""
    return Rule(
        id=rule_id,
        name=name or rule_id,
        description=description or f"Test rule {rule_id}",
        priority=priority,
        status=status,
        condition=condition,
        consequence=RuleConsequence(action=action, params=consequence_params),
    )


def make_wm(facts: Dict[str, Any]) -> WorkingMemory:
    """Create a WorkingMemory pre-loaded with the supplied facts dict."""
    return WorkingMemory(initial_facts=facts)


# =============================================================================
# 1. Helper Utilities
# =============================================================================

class TestComputeRuleSpecificity:
    """Tests for compute_rule_specificity()."""

    def test_simple_condition_has_specificity_one(self):
        cond = make_simple_condition("student.gpa", ">=", 7.0)
        assert compute_rule_specificity(cond) == 1

    def test_and_of_three_specificity_three(self):
        cond = make_and(
            make_simple_condition("student.gpa", ">=", 7.0),
            make_simple_condition("student.academic_status", "==", "active"),
            make_simple_condition("student.completed_courses", "IN", "CS101"),
        )
        assert compute_rule_specificity(cond) == 3

    def test_or_of_two_specificity_two(self):
        cond = make_or(
            make_simple_condition("student.gpa", ">=", 7.0),
            make_simple_condition("student.gpa", ">=", 8.0),
        )
        assert compute_rule_specificity(cond) == 2

    def test_nested_compound_specificity_sums_recursively(self):
        inner = make_and(
            make_simple_condition("student.gpa", ">=", 7.0),
            make_simple_condition("student.skills", "IN", "python"),
        )
        outer = make_and(inner, make_simple_condition("student.academic_status", "==", "active"))
        assert compute_rule_specificity(outer) == 3

    def test_none_condition_returns_zero(self):
        assert compute_rule_specificity(None) == 0


class TestExtractReferencedFactPaths:
    """Tests for extract_referenced_fact_paths()."""

    def test_simple_condition_returns_single_path(self):
        cond = make_simple_condition("student.gpa", ">=", 7.0)
        assert extract_referenced_fact_paths(cond) == ["student.gpa"]

    def test_and_condition_returns_all_paths(self):
        cond = make_and(
            make_simple_condition("student.gpa", ">=", 7.0),
            make_simple_condition("student.academic_status", "==", "active"),
        )
        paths = extract_referenced_fact_paths(cond)
        assert "student.gpa" in paths
        assert "student.academic_status" in paths
        assert len(paths) == 2

    def test_none_returns_empty_list(self):
        assert extract_referenced_fact_paths(None) == []


class TestExtractDerivedFacts:
    """Tests for extract_derived_facts()."""

    def test_fact_value_pattern(self):
        consequence = RuleConsequence(
            action="assert", params={"fact": "eligible", "value": True}
        )
        assert extract_derived_facts(consequence) == {"eligible": True}

    def test_direct_kv_pattern(self):
        consequence = RuleConsequence(
            action="assert", params={"gpa_eligible": True, "status": "ok"}
        )
        result = extract_derived_facts(consequence)
        assert result["gpa_eligible"] is True
        assert result["status"] == "ok"

    def test_empty_params_uses_action_key(self):
        consequence = RuleConsequence(action="flag_review", params={})
        result = extract_derived_facts(consequence)
        assert "action.flag_review" in result
        assert result["action.flag_review"] is True


class TestComputeRuleRecency:
    """Tests for compute_rule_recency()."""

    def test_initial_facts_have_step_zero(self):
        wm = make_wm({"student.gpa": 8.5})
        cond = make_simple_condition("student.gpa", ">=", 7.0)
        assert compute_rule_recency(cond, wm) == 0

    def test_derived_fact_at_step_two_returns_two(self):
        wm = make_wm({})
        wm.add_derived_fact("gpa_eligible", True, step=2, source_rule_id="R1")
        cond = make_simple_condition("gpa_eligible", "==", True)
        assert compute_rule_recency(cond, wm) == 2

    def test_max_step_returned_for_and_condition(self):
        wm = make_wm({"student.gpa": 8.5})
        wm.add_derived_fact("gpa_eligible", True, step=3, source_rule_id="R1")
        cond = make_and(
            make_simple_condition("student.gpa", ">=", 7.0),
            make_simple_condition("gpa_eligible", "==", True),
        )
        assert compute_rule_recency(cond, wm) == 3


# =============================================================================
# 2. Empty / No-Match Cases
# =============================================================================

class TestEmptyRuleSet:
    """Inference over an empty rule list should terminate at fixed point immediately."""

    def test_empty_rules_fixed_point(self):
        wm = make_wm({"student.gpa": 8.5})
        result = infer([], wm)
        assert result.fixed_point_reached is True
        assert result.termination_reason == "fixed_point"
        assert result.inference_step_count == 0
        assert result.fired_rule_ids == []
        assert result.derivation_history == []

    def test_empty_wm_empty_rules(self):
        wm = WorkingMemory()
        result = infer([], wm)
        assert result.fixed_point_reached is True
        assert result.inference_step_count == 0


class TestNoMatchingRules:
    """When no rules match the current facts, inference stops at fixed point immediately."""

    def test_no_match_stops_immediately(self):
        wm = make_wm({"student.gpa": 3.0})
        rule = make_rule(
            "R_HIGH_GPA",
            make_simple_condition("student.gpa", ">=", 9.0),
            {"gpa_ok": True},
        )
        result = infer([rule], wm)
        assert result.fixed_point_reached is True
        assert result.inference_step_count == 0
        assert result.fired_rule_ids == []
        assert "gpa_ok" not in result.derived_facts


# =============================================================================
# 3. Multi-Step Forward Chaining
# =============================================================================

class TestMultiStepForwardChaining:
    """Forward-chaining must propagate derived facts across multiple steps."""

    def test_three_step_chain(self):
        """
        Rule 1: IF gpa >= 7.0 THEN gpa_eligible = True
        Rule 2: IF CS101 IN completed_courses THEN prerequisite_eligible = True
        Rule 3: IF gpa_eligible==True AND prerequisite_eligible==True AND python IN skills
                THEN ai_course_eligible = True
        """
        wm = make_wm({
            "student.gpa": 8.7,
            "student.skills": ["python", "sql"],
            "student.completed_courses": ["CS101", "CS102"],
            "student.academic_status": "active",
        })

        rule1 = make_rule(
            "RULE_GPA",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"gpa_eligible": True},
            priority=10,
        )
        rule2 = make_rule(
            "RULE_PREREQ",
            make_simple_condition("student.completed_courses", "IN", "CS101"),
            {"prerequisite_eligible": True},
            priority=10,
        )
        rule3 = make_rule(
            "RULE_AI",
            make_and(
                make_simple_condition("gpa_eligible", "==", True),
                make_simple_condition("prerequisite_eligible", "==", True),
                make_simple_condition("student.skills", "IN", "python"),
            ),
            {"ai_course_eligible": True},
            priority=5,
        )

        result = infer([rule1, rule2, rule3], wm)

        assert result.fixed_point_reached is True
        assert result.termination_reason == "fixed_point"
        assert result.derived_facts.get("gpa_eligible") is True
        assert result.derived_facts.get("prerequisite_eligible") is True
        assert result.derived_facts.get("ai_course_eligible") is True
        assert "RULE_GPA" in result.fired_rule_ids
        assert "RULE_PREREQ" in result.fired_rule_ids
        assert "RULE_AI" in result.fired_rule_ids
        # Rule3 must fire AFTER Rule1 and Rule2
        ai_step = result.fired_rule_ids.index("RULE_AI")
        gpa_step = result.fired_rule_ids.index("RULE_GPA")
        prereq_step = result.fired_rule_ids.index("RULE_PREREQ")
        assert ai_step > gpa_step
        assert ai_step > prereq_step

    def test_chain_does_not_fire_rule3_without_prerequisite(self):
        """Rule3 must not fire if prerequisite_eligible is not derived."""
        wm = make_wm({
            "student.gpa": 8.7,
            "student.skills": ["python"],
            "student.completed_courses": ["CS202"],  # No CS101
        })
        rule1 = make_rule(
            "RULE_GPA",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"gpa_eligible": True},
        )
        rule2 = make_rule(
            "RULE_PREREQ",
            make_simple_condition("student.completed_courses", "IN", "CS101"),
            {"prerequisite_eligible": True},
        )
        rule3 = make_rule(
            "RULE_AI",
            make_and(
                make_simple_condition("gpa_eligible", "==", True),
                make_simple_condition("prerequisite_eligible", "==", True),
                make_simple_condition("student.skills", "IN", "python"),
            ),
            {"ai_course_eligible": True},
        )
        result = infer([rule1, rule2, rule3], wm)
        assert "ai_course_eligible" not in result.derived_facts
        assert "RULE_AI" not in result.fired_rule_ids


# =============================================================================
# 4. Derivation History and Provenance
# =============================================================================

class TestDerivationHistory:
    """DerivationStep records must accurately capture each firing step."""

    def test_single_rule_derivation_step_recorded(self):
        wm = make_wm({"student.gpa": 8.5})
        rule = make_rule(
            "RULE_GPA",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"gpa_eligible": True},
        )
        result = infer([rule], wm)
        assert len(result.derivation_history) == 1
        step: DerivationStep = result.derivation_history[0]
        assert step.step == 1
        assert step.rule_id == "RULE_GPA"
        assert step.derived_facts == {"gpa_eligible": True}
        assert "student.gpa" in step.source_facts

    def test_multi_step_history_in_order(self):
        wm = make_wm({"student.gpa": 8.7, "student.completed_courses": ["CS101"]})
        rule1 = make_rule(
            "RULE_GPA",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"gpa_eligible": True},
            priority=10,
        )
        rule2 = make_rule(
            "RULE_PREREQ",
            make_simple_condition("student.completed_courses", "IN", "CS101"),
            {"prerequisite_eligible": True},
            priority=5,
        )
        result = infer([rule1, rule2], wm)
        assert len(result.derivation_history) == 2
        assert result.derivation_history[0].rule_id == "RULE_GPA"
        assert result.derivation_history[1].rule_id == "RULE_PREREQ"
        assert result.derivation_history[0].step == 1
        assert result.derivation_history[1].step == 2

    def test_step_numbers_monotonically_increasing(self):
        wm = make_wm({"student.gpa": 8.7, "student.completed_courses": ["CS101"]})
        rules = [
            make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True}, priority=10),
            make_rule("R2", make_simple_condition("student.completed_courses", "IN", "CS101"), {"prereq_ok": True}, priority=5),
        ]
        result = infer(rules, wm)
        steps = [h.step for h in result.derivation_history]
        assert steps == sorted(steps)


class TestFactProvenance:
    """Fact provenance records must accurately track derivation origin."""

    def test_initial_facts_have_is_derived_false(self):
        wm = make_wm({"student.gpa": 8.5})
        rule = make_rule(
            "RULE_GPA",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"gpa_eligible": True},
        )
        result = infer([rule], wm)
        prov: FactProvenance = result.fact_provenance.get("student.gpa")
        assert prov is not None
        assert prov.is_derived is False
        assert prov.step == 0
        assert prov.rule_id is None

    def test_derived_facts_have_is_derived_true(self):
        wm = make_wm({"student.gpa": 8.5})
        rule = make_rule(
            "RULE_GPA",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"gpa_eligible": True},
        )
        result = infer([rule], wm)
        prov: FactProvenance = result.fact_provenance.get("gpa_eligible")
        assert prov is not None
        assert prov.is_derived is True
        assert prov.rule_id == "RULE_GPA"
        assert prov.step == 1

    def test_provenance_paths_match_derived_facts(self):
        wm = make_wm({"student.gpa": 8.7, "student.completed_courses": ["CS101"]})
        rules = [
            make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True}),
            make_rule("R2", make_simple_condition("student.completed_courses", "IN", "CS101"), {"prereq_ok": True}),
        ]
        result = infer(rules, wm)
        for path in result.derived_facts:
            assert path in result.fact_provenance


# =============================================================================
# 5. Conflict Resolution
# =============================================================================

class TestSalienceConflictResolution:
    """Higher priority (salience) rules must fire before lower priority rules."""

    def test_high_priority_fires_first(self):
        wm = make_wm({"student.gpa": 8.5})
        # Both match, but R_HIGH should fire before R_LOW
        r_low = make_rule(
            "R_LOW",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"low_triggered": True},
            priority=1,
        )
        r_high = make_rule(
            "R_HIGH",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"high_triggered": True},
            priority=100,
        )
        result = infer([r_low, r_high], wm)
        # R_HIGH must appear first in fired_rule_ids
        assert result.fired_rule_ids[0] == "R_HIGH"
        assert result.fired_rule_ids[1] == "R_LOW"


class TestSpecificityConflictResolution:
    """More specific rules (more atomic conditions) must win over less specific ones."""

    def test_more_specific_rule_fires_first_at_equal_priority(self):
        wm = make_wm({"student.gpa": 8.5, "student.academic_status": "active"})
        r_generic = make_rule(
            "R_GENERIC",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"generic_match": True},
            priority=0,
        )
        r_specific = make_rule(
            "R_SPECIFIC",
            make_and(
                make_simple_condition("student.gpa", ">=", 7.0),
                make_simple_condition("student.academic_status", "==", "active"),
            ),
            {"specific_match": True},
            priority=0,
        )
        result = infer([r_generic, r_specific], wm)
        # R_SPECIFIC (specificity=2) must fire before R_GENERIC (specificity=1)
        assert result.fired_rule_ids[0] == "R_SPECIFIC"


class TestRecencyConflictResolution:
    """Rules depending on more recently derived facts should fire preferentially."""

    def test_rule_depending_on_recent_fact_fires_first(self):
        """
        Setup: Both R_A and R_B match at equal priority and specificity.
        R_A depends on gpa_eligible (step=1, recently derived).
        R_B depends on student.gpa (step=0, initial).
        R_A should be selected over R_B when they compete.
        """
        wm = make_wm({"student.gpa": 8.5, "student.academic_status": "active"})

        # Step 1: Derive gpa_eligible first by running a bootstrap rule
        r_bootstrap = make_rule(
            "R_BOOTSTRAP",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"gpa_eligible": True},
            priority=100,
        )
        r_recent = make_rule(
            "R_RECENT",
            make_simple_condition("gpa_eligible", "==", True),
            {"recent_win": True},
            priority=0,
        )
        r_old = make_rule(
            "R_OLD",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"old_win": True},
            priority=0,
        )
        result = infer([r_bootstrap, r_recent, r_old], wm)
        # R_BOOTSTRAP fires first (priority 100), then R_RECENT vs R_OLD both at priority 0
        # R_RECENT depends on gpa_eligible (step=1) → higher recency → fires first
        idx_recent = result.fired_rule_ids.index("R_RECENT")
        idx_old = result.fired_rule_ids.index("R_OLD")
        assert idx_recent < idx_old


class TestRuleIDTieBreaking:
    """When all other factors are equal, rules must be sorted lexicographically by ID."""

    def test_lexicographic_id_order(self):
        wm = make_wm({"x": 1})
        # Both match, same priority, same specificity, same recency
        r_b = make_rule("B_RULE", make_simple_condition("x", "==", 1), {"b_fired": True}, priority=0)
        r_a = make_rule("A_RULE", make_simple_condition("x", "==", 1), {"a_fired": True}, priority=0)
        result = infer([r_b, r_a], wm)
        # A_RULE < B_RULE lexicographically → A_RULE fires first
        assert result.fired_rule_ids[0] == "A_RULE"
        assert result.fired_rule_ids[1] == "B_RULE"


# =============================================================================
# 6. Negative Preclusion
# =============================================================================

class TestNegativePreclusion:
    """Once a fact is precluded (False), a later True assertion must NOT override it."""

    def test_true_then_false_yields_false(self):
        """
        Rule A fires first (higher priority): eligible = True
        Rule B fires second: eligible = False (precluded)
        Final: eligible must be False
        """
        wm = make_wm({"student.gpa": 8.7, "student.academic_status": "suspended"})
        rule_a = make_rule(
            "RULE_GPA_ELIGIBLE",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"eligible": True},
            priority=100,
        )
        rule_b = make_rule(
            "RULE_SUSPENDED",
            make_simple_condition("student.academic_status", "==", "suspended"),
            {"eligible": False},
            priority=50,
        )
        result = infer([rule_a, rule_b], wm)
        assert "RULE_GPA_ELIGIBLE" in result.fired_rule_ids
        assert "RULE_SUSPENDED" in result.fired_rule_ids
        assert result.final_facts.get("eligible") is False

    def test_false_then_true_still_yields_false(self):
        """
        Rule B fires first (higher priority): eligible = False
        Rule A fires second: eligible = True
        Preclusion must still enforce eligible = False
        """
        wm = make_wm({"student.gpa": 8.7, "student.academic_status": "suspended"})
        rule_b = make_rule(
            "RULE_SUSPENDED",
            make_simple_condition("student.academic_status", "==", "suspended"),
            {"eligible": False},
            priority=100,
        )
        rule_a = make_rule(
            "RULE_GPA_ELIGIBLE",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"eligible": True},
            priority=50,
        )
        result = infer([rule_a, rule_b], wm)
        assert result.final_facts.get("eligible") is False

    def test_both_preclusion_rules_recorded_in_history(self):
        """Both the positive and negative rules should appear in fired_rule_ids."""
        wm = make_wm({"student.gpa": 8.7, "student.academic_status": "suspended"})
        rule_a = make_rule(
            "RULE_GPA",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"eligible": True},
            priority=100,
        )
        rule_b = make_rule(
            "RULE_SUSP",
            make_simple_condition("student.academic_status", "==", "suspended"),
            {"eligible": False},
            priority=50,
        )
        result = infer([rule_a, rule_b], wm)
        assert "RULE_GPA" in result.fired_rule_ids
        assert "RULE_SUSP" in result.fired_rule_ids


# =============================================================================
# 7. Cycle Detection
# =============================================================================

class TestCycleDetection:
    """Mutual derivation cycles (A→B→A) must be detected and terminate cleanly."""

    def test_mutual_derivation_cycle_terminates(self):
        """
        Rule A: IF flag_a == True THEN flag_b = True
        Rule B: IF flag_b == True THEN flag_a = True
        After step 1: flag_b = True (state changes)
        After step 2: flag_a = True (state changes — but flag_a was already True initially)
        State hash repeats → cycle detected
        """
        wm = make_wm({"flag_a": True})
        rule_a = make_rule(
            "R_A",
            make_simple_condition("flag_a", "==", True),
            {"flag_b": True},
            priority=10,
        )
        rule_b = make_rule(
            "R_B",
            make_simple_condition("flag_b", "==", True),
            {"flag_a": True},
            priority=5,
        )
        result = infer([rule_a, rule_b], wm)
        assert result.cycle_detected is True
        assert result.termination_reason == "cycle_detected"
        assert result.fixed_point_reached is False

    def test_cycle_detection_does_not_raise(self):
        """Cycle detection must terminate without exception."""
        wm = make_wm({"x": True})
        r1 = make_rule("CY1", make_simple_condition("x", "==", True), {"y": True}, priority=10)
        r2 = make_rule("CY2", make_simple_condition("y", "==", True), {"x": True}, priority=5)
        # Should not raise any exception
        result = infer([r1, r2], wm)
        assert isinstance(result, InferenceResult)

    def test_cycle_fired_rules_recorded(self):
        """Rules that fired before cycle detection must be recorded."""
        wm = make_wm({"flag_a": True})
        rule_a = make_rule("R_A", make_simple_condition("flag_a", "==", True), {"flag_b": True})
        rule_b = make_rule("R_B", make_simple_condition("flag_b", "==", True), {"flag_a": True})
        result = infer([rule_a, rule_b], wm)
        assert len(result.fired_rule_ids) > 0
        assert "R_A" in result.fired_rule_ids


# =============================================================================
# 8. Max Depth Enforcement
# =============================================================================

class TestMaxDepthEnforcement:
    """Inference must stop at max_depth without crashing."""

    def _make_chain_rules(self, length: int) -> List[Rule]:
        """Create a chain: IF step_0==True THEN step_1=True, IF step_1==True THEN step_2=True, ..."""
        rules = []
        for i in range(length):
            rules.append(make_rule(
                f"R_CHAIN_{i}",
                make_simple_condition(f"step_{i}", "==", True),
                {f"step_{i + 1}": True},
                priority=length - i,
            ))
        return rules

    def test_max_depth_stops_early(self):
        """A chain that needs 10 steps, limited to max_depth=3, must stop at max_depth."""
        wm = make_wm({"step_0": True})
        rules = self._make_chain_rules(10)
        result = infer(rules, wm, max_depth=3)
        assert result.max_depth_reached is True
        assert result.termination_reason == "max_depth_reached"
        assert result.fixed_point_reached is False
        assert result.inference_step_count == 3

    def test_max_depth_one_fires_exactly_one_rule(self):
        wm = make_wm({"step_0": True})
        rules = self._make_chain_rules(5)
        result = infer(rules, wm, max_depth=1)
        assert result.max_depth_reached is True
        assert result.inference_step_count == 1
        assert len(result.fired_rule_ids) == 1

    def test_chain_completes_within_depth(self):
        """A 3-step chain with max_depth=10 should complete naturally (fixed_point)."""
        wm = make_wm({"step_0": True})
        rules = self._make_chain_rules(3)
        result = infer(rules, wm, max_depth=10)
        assert result.fixed_point_reached is True
        assert result.inference_step_count == 3


# =============================================================================
# 9. Determinism
# =============================================================================

class TestDeterminism:
    """Identical inputs must produce bit-for-bit identical InferenceResult across runs."""

    def test_fifty_runs_identical_output(self):
        wm = make_wm({
            "student.gpa": 8.7,
            "student.skills": ["python", "sql"],
            "student.completed_courses": ["CS101"],
            "student.academic_status": "active",
        })
        rules = [
            make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True}, priority=10),
            make_rule("R2", make_simple_condition("student.completed_courses", "IN", "CS101"), {"prereq_ok": True}, priority=5),
            make_rule(
                "R3",
                make_and(
                    make_simple_condition("gpa_ok", "==", True),
                    make_simple_condition("prereq_ok", "==", True),
                ),
                {"eligible": True},
                priority=1,
            ),
        ]

        first = infer(rules, wm)
        for _ in range(49):
            run = infer(rules, wm)
            assert run.fired_rule_ids == first.fired_rule_ids
            assert run.derived_facts == first.derived_facts
            assert run.termination_reason == first.termination_reason
            assert run.inference_step_count == first.inference_step_count


# =============================================================================
# 10. State Isolation
# =============================================================================

class TestStateIsolation:
    """infer() must not mutate the caller's original WorkingMemory."""

    def test_original_wm_unchanged_after_infer(self):
        initial = {"student.gpa": 8.5, "student.academic_status": "active"}
        wm = make_wm(initial)
        original_facts_before = wm.get_all_facts()

        rule = make_rule(
            "RULE_GPA",
            make_simple_condition("student.gpa", ">=", 7.0),
            {"gpa_eligible": True},
        )
        infer([rule], wm)

        original_facts_after = wm.get_all_facts()
        assert original_facts_before == original_facts_after
        assert "gpa_eligible" not in original_facts_after

    def test_derived_facts_only_in_result_not_original_wm(self):
        wm = make_wm({"x": 5})
        rule = make_rule("R_X", make_simple_condition("x", ">", 3), {"x_big": True})
        result = infer([rule], wm)
        assert result.derived_facts.get("x_big") is True
        assert not wm.has_fact("x_big")

    def test_multiple_independent_infer_calls_same_wm(self):
        """Multiple infer() calls on the same WorkingMemory must return same results."""
        wm = make_wm({"student.gpa": 8.5})
        rule = make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True})
        r1 = infer([rule], wm)
        r2 = infer([rule], wm)
        assert r1.derived_facts == r2.derived_facts
        assert r1.fired_rule_ids == r2.fired_rule_ids


# =============================================================================
# 11. Multiple Independent Derivations
# =============================================================================

class TestMultipleIndependentDerivations:
    """Multiple independent rules must all fire and assert their facts correctly."""

    def test_three_independent_rules_all_fire(self):
        wm = make_wm({
            "student.gpa": 8.5,
            "student.age": 22,
            "student.academic_status": "active",
        })
        rules = [
            make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True}),
            make_rule("R2", make_simple_condition("student.age", ">=", 18), {"adult": True}),
            make_rule("R3", make_simple_condition("student.academic_status", "==", "active"), {"active_ok": True}),
        ]
        result = infer(rules, wm)
        assert result.derived_facts.get("gpa_ok") is True
        assert result.derived_facts.get("adult") is True
        assert result.derived_facts.get("active_ok") is True
        assert len(result.fired_rule_ids) == 3

    def test_only_matching_independent_rules_fire(self):
        wm = make_wm({
            "student.gpa": 6.0,  # Below 7.0 → R1 should NOT match
            "student.age": 22,
            "student.academic_status": "active",
        })
        rules = [
            make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True}),
            make_rule("R2", make_simple_condition("student.age", ">=", 18), {"adult": True}),
            make_rule("R3", make_simple_condition("student.academic_status", "==", "active"), {"active_ok": True}),
        ]
        result = infer(rules, wm)
        assert "gpa_ok" not in result.derived_facts
        assert result.derived_facts.get("adult") is True
        assert result.derived_facts.get("active_ok") is True
        assert "R1" not in result.fired_rule_ids


# =============================================================================
# 12. InferenceEngine Class Interface
# =============================================================================

class TestInferenceEngineClass:
    """InferenceEngine static methods must delegate correctly to module-level functions."""

    def test_engine_infer_static_method(self):
        wm = make_wm({"student.gpa": 8.5})
        rule = make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True})
        result = InferenceEngine.infer([rule], wm)
        assert isinstance(result, InferenceResult)
        assert result.derived_facts.get("gpa_ok") is True

    def test_engine_evaluate_rule_preserved(self):
        """Phase 3 evaluate_rule must still work via InferenceEngine."""
        from backend.schemas.rule import RuleExecutionResult
        wm = make_wm({"student.gpa": 8.5})
        rule = make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True})
        result = InferenceEngine.evaluate_rule(rule, wm)
        assert isinstance(result, RuleExecutionResult)
        assert result.matched is True
        assert result.derived_facts == {"gpa_ok": True}

    def test_engine_apply_rule_preserved(self):
        """Phase 3 apply_rule must still work via InferenceEngine."""
        from backend.schemas.rule import RuleExecutionResult
        wm = make_wm({"student.gpa": 8.5})
        rule = make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True})
        result = InferenceEngine.apply_rule(rule, wm)
        assert isinstance(result, RuleExecutionResult)
        assert result.matched is True
        assert wm.has_fact("gpa_ok")


# =============================================================================
# 13. InferenceResult Model Integrity
# =============================================================================

class TestInferenceResultModel:
    """Verify InferenceResult fields are correctly populated in various scenarios."""

    def test_result_fields_populated_on_match(self):
        wm = make_wm({"student.gpa": 8.5})
        rule = make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True})
        result = infer([rule], wm)
        assert isinstance(result.final_facts, dict)
        assert isinstance(result.derived_facts, dict)
        assert isinstance(result.fired_rule_ids, list)
        assert isinstance(result.derivation_history, list)
        assert isinstance(result.fact_provenance, dict)
        assert isinstance(result.inference_step_count, int)
        assert isinstance(result.termination_reason, str)

    def test_final_facts_contains_initial_and_derived(self):
        wm = make_wm({"student.gpa": 8.5})
        rule = make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True})
        result = infer([rule], wm)
        # Final facts should include both initial facts and derived facts
        assert "student.gpa" in result.final_facts or "student" in result.final_facts
        assert "gpa_ok" in result.final_facts

    def test_derived_facts_subset_of_final_facts(self):
        wm = make_wm({"student.gpa": 8.5})
        rule = make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True})
        result = infer([rule], wm)
        for path, value in result.derived_facts.items():
            assert path in result.final_facts

    def test_inference_step_count_matches_fired_rules(self):
        wm = make_wm({"student.gpa": 8.7, "student.completed_courses": ["CS101"]})
        rules = [
            make_rule("R1", make_simple_condition("student.gpa", ">=", 7.0), {"gpa_ok": True}),
            make_rule("R2", make_simple_condition("student.completed_courses", "IN", "CS101"), {"prereq_ok": True}),
        ]
        result = infer(rules, wm)
        assert result.inference_step_count == len(result.fired_rule_ids)
        assert result.inference_step_count == len(result.derivation_history)


# =============================================================================
# 14. WorkingMemory Phase 4 Extensions
# =============================================================================

class TestWorkingMemoryPhase4:
    """Tests for new Phase 4 WorkingMemory features (clone, provenance, preclusion)."""

    def test_clone_is_independent(self):
        wm = make_wm({"student.gpa": 8.5})
        cloned = wm.clone()
        cloned.add_fact("extra", 42)
        assert not wm.has_fact("extra")

    def test_clone_preserves_all_facts(self):
        wm = make_wm({"student.gpa": 8.5, "student.academic_status": "active"})
        cloned = wm.clone()
        assert cloned.has_fact("student.gpa")
        assert cloned.get_fact("student.gpa") == 8.5

    def test_clone_preserves_derived_facts(self):
        wm = WorkingMemory()
        wm.add_derived_fact("eligible", True, step=1, source_rule_id="R1")
        cloned = wm.clone()
        assert cloned.has_fact("eligible")
        assert cloned.get_derived_facts().get("eligible") is True

    def test_preclusion_sets_false_on_add_derived_false(self):
        wm = WorkingMemory()
        wm.add_derived_fact("eligible", True, step=1, source_rule_id="R1")
        wm.add_derived_fact("eligible", False, step=2, source_rule_id="R2")
        assert wm.get_fact("eligible") is False

    def test_preclusion_true_after_false_stays_false(self):
        wm = WorkingMemory()
        wm.add_derived_fact("eligible", False, step=1, source_rule_id="R1")
        wm.add_derived_fact("eligible", True, step=2, source_rule_id="R2")
        assert wm.get_fact("eligible") is False

    def test_provenance_recorded_for_derived_fact(self):
        wm = WorkingMemory()
        wm.add_derived_fact("gpa_ok", True, step=3, source_rule_id="RULE_GPA")
        prov = wm.get_provenance("gpa_ok")
        assert prov is not None
        assert prov.is_derived is True
        assert prov.step == 3
        assert prov.rule_id == "RULE_GPA"
        assert prov.path == "gpa_ok"

    def test_get_fact_step_returns_correct_step(self):
        wm = WorkingMemory()
        wm.add_derived_fact("x", True, step=5, source_rule_id="R1")
        assert wm.get_fact_step("x") == 5

    def test_get_fact_step_returns_zero_for_initial(self):
        wm = make_wm({"student.gpa": 8.5})
        assert wm.get_fact_step("student.gpa") == 0

    def test_get_all_provenance_returns_all_entries(self):
        wm = make_wm({"student.gpa": 8.5})
        wm.add_derived_fact("gpa_ok", True, step=1, source_rule_id="R1")
        prov_map = wm.get_all_provenance()
        assert "student.gpa" in prov_map
        assert "gpa_ok" in prov_map

    def test_clear_resets_phase4_state(self):
        wm = make_wm({"student.gpa": 8.5})
        wm.add_derived_fact("gpa_ok", True, step=1, source_rule_id="R1")
        wm.clear()
        assert wm.get_all_facts() == {}
        assert wm.get_derived_facts() == {}
        assert wm.get_all_provenance() == {}
