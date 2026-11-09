"""Endpoints for executing what-if simulations and analyzing scenario impacts (Phase 4+)."""

import logging
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status

from backend.db.database import get_db_manager
from backend.db.repositories import DomainRepository, RuleRepository
from backend.engine.inference_engine import infer
from backend.engine.working_memory import WorkingMemory
from backend.schemas.api import SimulationRequest, SimulationResponse
from backend.simulation.delta_analyzer import DeltaAnalyzer
from backend.simulation.fork_manager import ForkManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["What-If Simulation Sandbox"])


@router.post("/run", response_model=SimulationResponse, summary="Run scenario simulation and analyze delta")
def run_simulation(req: SimulationRequest) -> SimulationResponse:
    """Simulate what-if changes against a domain's rules and evaluate delta divergences."""
    db = get_db_manager()
    dom_repo = DomainRepository(db)
    rule_repo = RuleRepository(db)

    domain = dom_repo.get_by_id(req.domain_id) or dom_repo.get_by_slug(req.domain_id)
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain '{req.domain_id}' not found.",
        )

    rules = rule_repo.get_as_pydantic_rules(domain["id"], active_only=True)
    if not rules:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Domain '{domain['name']}' has no active rules to simulate.",
        )

    # 1. Baseline Evaluation
    baseline_wm = WorkingMemory()
    for k, v in req.baseline_facts.items():
        baseline_wm.add_fact(k, v)

    baseline_result = infer(rules, baseline_wm)

    # 2. Forked Simulation Evaluation
    fork = ForkManager.create_fork(
        baseline_memory=baseline_wm,
        rules=rules,
        fact_overrides=req.fact_overrides,
    )
    simulated_result = fork.run_simulation()

    # 3. Delta Analysis
    delta = DeltaAnalyzer.compare(baseline=baseline_result, simulated=simulated_result)

    base_decision = "Eligible / Approved" if delta.baseline_conclusion else "Ineligible / Unmatched"
    sim_decision = "Eligible / Approved" if delta.simulated_conclusion else "Ineligible / Unmatched"

    return SimulationResponse(
        domain_id=domain["id"],
        baseline_decision=base_decision,
        simulated_decision=sim_decision,
        delta=delta,
    )
