from __future__ import annotations

from rescueos.core.distinctions import Intervention
from rescueos.core.planner import BoundedLookaheadPlanner, PlannerConfig


def build_policy(interventions: list[Intervention]) -> BoundedLookaheadPlanner:
    return BoundedLookaheadPlanner(
        interventions=interventions,
        config=PlannerConfig(lambda_cost=0.05, beta_harm=0.25, gamma_unsafe=0.2),
    )
