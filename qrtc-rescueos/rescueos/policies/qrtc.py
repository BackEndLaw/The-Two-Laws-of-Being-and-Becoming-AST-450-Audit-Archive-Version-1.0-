from __future__ import annotations

from rescueos.compiler.schema import CompiledGraph
from rescueos.core.distinctions import Intervention
from rescueos.core.planner import BoundedLookaheadPlanner, PlannerConfig
from rescueos.core.transition import TransitionModel


def build_policy(
    interventions: list[Intervention],
    graph: CompiledGraph | None = None,
    transition_model: TransitionModel | None = None,
) -> BoundedLookaheadPlanner:
    return BoundedLookaheadPlanner(
        interventions=interventions,
        config=PlannerConfig(lambda_cost=0.05, beta_harm=0.25, gamma_unsafe=0.2),
        graph=graph,
        transition_model=transition_model,
    )
