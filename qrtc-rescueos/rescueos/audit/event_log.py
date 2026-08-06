from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AuditEventLog:
    decisions: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[dict[str, Any]] = field(default_factory=list)

    def record_decision(self, *, step: int, observation: dict, belief, decision) -> None:
        self.decisions.append(
            {
                "step": step,
                "observation": observation,
                "belief": asdict(belief),
                "decision": asdict(decision),
            }
        )

    def record_outcome(self, *, step: int, outcome, decision=None) -> None:
        record = {
            "step": step,
            "outcome": asdict(outcome),
        }
        transit = getattr(decision, "transit", None)
        if transit is not None:
            passage_executed = transit.passage_committed
            record["transit_witness"] = {
                **asdict(transit),
                "passage_executed": passage_executed,
                "destination_branch": (
                    transit.candidate_branch if passage_executed else None
                ),
                "destination_realized": passage_executed,
                "ingress_erased": passage_executed,
                "v2_retained_jurisdiction": (
                    transit.retained_jurisdiction == "baseline_v2"
                ),
                "resulting_action": outcome.action_id,
                "action_succeeded": outcome.succeeded,
            }
        self.outcomes.append(record)

    def reconstructable(self) -> bool:
        if not self.decisions:
            return True
        for index, item in enumerate(self.decisions):
            if item.get("step") != index:
                return False
            if "decision" not in item:
                return False
        return True
