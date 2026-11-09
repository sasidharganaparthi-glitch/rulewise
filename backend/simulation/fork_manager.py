"""Fork manager for isolating working memory states during what-if simulations (Phase 4+).

Provides isolated working memory branching to evaluate hypothetical scenarios
without mutating production facts, active rules, or database records.
"""

from typing import Any, Dict, List, Optional
from backend.engine.inference_engine import infer
from backend.engine.working_memory import WorkingMemory
from backend.schemas.rule import InferenceResult, Rule


class SimulationFork:
    """An isolated simulation branch containing forked working memory and candidate rules."""

    def __init__(
        self,
        baseline_memory: WorkingMemory,
        rules: List[Rule],
        fact_overrides: Optional[Dict[str, Any]] = None,
        rule_overrides: Optional[List[Rule]] = None,
    ) -> None:
        """Create an isolated simulation fork.

        Args:
            baseline_memory: Base working memory to clone.
            rules: Active rule set to evaluate.
            fact_overrides: Specific facts to replace or add in the fork.
            rule_overrides: Optional alternative rule collection to test.
        """
        self.memory = baseline_memory.clone()
        if fact_overrides:
            for path, val in fact_overrides.items():
                self.memory.add_fact(path, val)

        self.rules = list(rule_overrides) if rule_overrides is not None else list(rules)

    def run_simulation(self, max_depth: int = 50) -> InferenceResult:
        """Execute deterministic forward chaining on the isolated forked state."""
        return infer(self.rules, self.memory, max_depth=max_depth)


class ForkManager:
    """Manager for creating and orchestrating scenario simulation forks."""

    @staticmethod
    def create_fork(
        baseline_memory: WorkingMemory,
        rules: List[Rule],
        fact_overrides: Optional[Dict[str, Any]] = None,
        rule_overrides: Optional[List[Rule]] = None,
    ) -> SimulationFork:
        """Branch working memory into an isolated scenario fork."""
        return SimulationFork(
            baseline_memory=baseline_memory,
            rules=rules,
            fact_overrides=fact_overrides,
            rule_overrides=rule_overrides,
        )
