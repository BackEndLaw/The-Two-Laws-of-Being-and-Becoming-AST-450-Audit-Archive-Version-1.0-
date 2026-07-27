from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from qrtc.transit import GuardDecision, TransitEnvelope


@dataclass(frozen=True)
class GuardRule:
    guard_id: str
    policy_version: str
    predicate: Callable[[TransitEnvelope], bool]
    pass_reason: str
    fail_reason: str

    def evaluate(self, envelope: TransitEnvelope) -> GuardDecision:
        qualified = self.predicate(envelope)
        return GuardDecision(
            qualified=qualified,
            guard_id=self.guard_id,
            policy_version=self.policy_version,
            reason=self.pass_reason if qualified else self.fail_reason,
        )


def evaluate_guards(
    envelope: TransitEnvelope,
    guards: Iterable[GuardRule],
) -> tuple[GuardDecision, ...]:
    decisions: list[GuardDecision] = []

    for guard in guards:
        decision = guard.evaluate(envelope)
        decisions.append(decision)
        if not decision.qualified:
            break

    return tuple(decisions)
