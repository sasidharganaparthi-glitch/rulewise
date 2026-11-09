"""Delta analyzer computing divergence between baseline and simulated scenario outcomes (Phase 4+).

Compares baseline inference results against forked simulation results to report:
- Newly fired rules (rules activated by the change)
- Ceased rules (rules deactivated by the change)
- Fact deltas (added, removed, modified derived facts)
- Final decision change
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from backend.schemas.rule import InferenceResult


class FactDelta(BaseModel):
    """Represents a change in a single fact between baseline and simulation."""

    path: str
    baseline_value: Any = None
    simulated_value: Any = None
    change_type: str = Field(description="added, removed, or modified")


class SimulationDelta(BaseModel):
    """Structured report comparing baseline vs simulation inference executions."""

    newly_fired_rules: List[str] = Field(default_factory=list, description="Rule IDs that fired only in simulation")
    ceased_rules: List[str] = Field(default_factory=list, description="Rule IDs that fired in baseline but not in simulation")
    unchanged_rules: List[str] = Field(default_factory=list, description="Rule IDs that fired in both")
    fact_changes: List[FactDelta] = Field(default_factory=list, description="Differences in derived and asserted facts")
    baseline_conclusion: bool
    simulated_conclusion: bool
    conclusion_changed: bool
    summary: str


class DeltaAnalyzer:
    """Computes transparent deltas between baseline and simulated scenario evaluations."""

    @staticmethod
    def compare(
        baseline: InferenceResult,
        simulated: InferenceResult,
    ) -> SimulationDelta:
        """Analyze differences between two InferenceResults."""
        base_fired = set(baseline.fired_rule_ids)
        sim_fired = set(simulated.fired_rule_ids)

        newly_fired = sorted(list(sim_fired - base_fired))
        ceased = sorted(list(base_fired - sim_fired))
        unchanged = sorted(list(base_fired & sim_fired))

        # Fact changes
        fact_changes: List[FactDelta] = []
        base_facts = baseline.final_facts
        sim_facts = simulated.final_facts

        all_keys = set(base_facts.keys()) | set(sim_facts.keys())
        for k in sorted(all_keys):
            in_base = k in base_facts
            in_sim = k in sim_facts

            if in_sim and not in_base:
                fact_changes.append(
                    FactDelta(
                        path=k,
                        baseline_value=None,
                        simulated_value=sim_facts[k],
                        change_type="added",
                    )
                )
            elif in_base and not in_sim:
                fact_changes.append(
                    FactDelta(
                        path=k,
                        baseline_value=base_facts[k],
                        simulated_value=None,
                        change_type="removed",
                    )
                )
            elif base_facts[k] != sim_facts[k]:
                fact_changes.append(
                    FactDelta(
                        path=k,
                        baseline_value=base_facts[k],
                        simulated_value=sim_facts[k],
                        change_type="modified",
                    )
                )

        # Determine conclusion from fired rules / derived assertions
        base_conclusion = len(baseline.fired_rule_ids) > 0
        sim_conclusion = len(simulated.fired_rule_ids) > 0

        # If any explicit approval/eligible fact was derived
        for k, v in base_facts.items():
            if ("eligible" in k.lower() or "approved" in k.lower() or "granted" in k.lower()) and v is True:
                base_conclusion = True
        for k, v in sim_facts.items():
            if ("eligible" in k.lower() or "approved" in k.lower() or "granted" in k.lower()) and v is True:
                sim_conclusion = True

        conclusion_changed = (base_conclusion != sim_conclusion)

        summary_parts = []
        if conclusion_changed:
            summary_parts.append(
                f"Conclusion flipped from {base_conclusion} to {sim_conclusion}."
            )
        else:
            summary_parts.append(
                f"Conclusion remained {sim_conclusion}."
            )

        if newly_fired:
            summary_parts.append(f"{len(newly_fired)} new rule(s) fired ({', '.join(newly_fired)}).")
        if ceased:
            summary_parts.append(f"{len(ceased)} rule(s) ceased firing ({', '.join(ceased)}).")
        if not newly_fired and not ceased and not fact_changes:
            summary_parts.append("No behavioural divergence detected.")

        return SimulationDelta(
            newly_fired_rules=newly_fired,
            ceased_rules=ceased,
            unchanged_rules=unchanged,
            fact_changes=fact_changes,
            baseline_conclusion=base_conclusion,
            simulated_conclusion=sim_conclusion,
            conclusion_changed=conclusion_changed,
            summary=" ".join(summary_parts),
        )
