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

    def record_outcome(self, *, step: int, outcome) -> None:
        self.outcomes.append(
            {
                "step": step,
                "outcome": asdict(outcome),
            }
        )

    def reconstructable(self) -> bool:
        if not self.decisions:
            return True
        for index, item in enumerate(self.decisions):
            if item.get("step") != index:
                return False
            if "decision" not in item:
                return False
        return True
