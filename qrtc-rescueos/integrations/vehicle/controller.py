from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class RouteFollowingController(Protocol):
    def activate(self, route: list[str], vehicle_state: dict[str, Any]) -> bool: ...

    def step(self, observation: dict[str, Any]) -> dict[str, Any]: ...

    def is_active(self) -> bool: ...

    def deactivate(self) -> None: ...


@dataclass(frozen=True)
class HandoffState:
    authority: str
    passage_committed: bool
    passage_executed: bool
    destination_realized: bool
    fallback_invoked: bool
    status: str
    witnesses: tuple[dict[str, Any], ...]


class HandoffCoordinator:
    """Own semantic authority transfer without asserting vehicle physics."""

    def __init__(self, controller: RouteFollowingController, *, timeout_steps: int) -> None:
        if timeout_steps < 1:
            raise ValueError("timeout_steps must be positive")
        self._controller = controller
        self._timeout_steps = timeout_steps
        self._steps = 0
        self._authority = "baseline_v2"
        self._passage_committed = False
        self._passage_executed = False
        self._destination_realized = False
        self._fallback_invoked = False
        self._status = "idle"
        self._witnesses: list[dict[str, Any]] = []

    def activate(self, route: list[str], vehicle_state: dict[str, Any]) -> bool:
        self._passage_committed = True
        acknowledged = self._controller.activate(route, vehicle_state)
        self._record("activation_acknowledged" if acknowledged else "activation_rejected")
        if not acknowledged or not self._controller.is_active():
            self._fallback("activation_rejected")
            return False
        self._authority = "specialist"
        self._status = "active"
        self._record("authority_transferred")
        return True

    def step(self, observation: dict[str, Any]) -> HandoffState:
        if self._authority != "specialist":
            return self.state()
        if not self._controller.is_active():
            self._fallback("controller_interrupted")
            return self.state()

        try:
            outcome = self._controller.step(observation)
        except Exception:
            self._fallback("controller_failed")
            return self.state()

        self._passage_executed = True
        self._steps += 1
        self._record("specialist_step_executed")
        if bool(outcome.get("destination_reached", False)):
            self._destination_realized = True
            self._status = "destination_realized"
            self._record("destination_realized")
        elif self._steps >= self._timeout_steps:
            self._fallback("controller_timeout")
        return self.state()

    def state(self) -> HandoffState:
        return HandoffState(
            authority=self._authority,
            passage_committed=self._passage_committed,
            passage_executed=self._passage_executed,
            destination_realized=self._destination_realized,
            fallback_invoked=self._fallback_invoked,
            status=self._status,
            witnesses=tuple(self._witnesses),
        )

    def _fallback(self, reason: str) -> None:
        if self._controller.is_active():
            self._controller.deactivate()
        self._authority = "baseline_v2"
        self._fallback_invoked = True
        self._status = reason
        self._record("fallback_invoked", reason=reason)

    def _record(self, event: str, **details: Any) -> None:
        self._witnesses.append(
            {
                "event": event,
                "authority": self._authority,
                "sequence": len(self._witnesses),
                **details,
            }
        )