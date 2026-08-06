from __future__ import annotations

from integrations.vehicle.controller import HandoffCoordinator


class FakeRouteController:
    def __init__(self, *, accepts: bool = True, destination_step: int | None = None) -> None:
        self.accepts = accepts
        self.destination_step = destination_step
        self.active = False
        self.steps = 0

    def activate(self, _route: list[str], _vehicle_state: dict) -> bool:
        self.active = self.accepts
        return self.accepts

    def step(self, _observation: dict) -> dict:
        self.steps += 1
        return {"destination_reached": self.steps == self.destination_step}

    def is_active(self) -> bool:
        return self.active

    def deactivate(self) -> None:
        self.active = False


def test_activation_acknowledgment_transfers_exclusive_authority_without_destination() -> None:
    coordinator = HandoffCoordinator(FakeRouteController(), timeout_steps=2)

    assert coordinator.activate(["B", "C", "D"], {"position": "B"}) is True
    state = coordinator.state()

    assert state.authority == "specialist"
    assert state.passage_committed is True
    assert state.passage_executed is False
    assert state.destination_realized is False
    assert [witness["event"] for witness in state.witnesses] == [
        "activation_acknowledged",
        "authority_transferred",
    ]


def test_rejected_activation_retains_baseline_and_invokes_fallback() -> None:
    coordinator = HandoffCoordinator(
        FakeRouteController(accepts=False), timeout_steps=2
    )

    assert coordinator.activate(["B", "C", "D"], {"position": "B"}) is False
    state = coordinator.state()

    assert state.authority == "baseline_v2"
    assert state.passage_executed is False
    assert state.destination_realized is False
    assert state.fallback_invoked is True


def test_destination_requires_an_executed_specialist_step() -> None:
    coordinator = HandoffCoordinator(
        FakeRouteController(destination_step=1), timeout_steps=2
    )
    coordinator.activate(["B", "C", "D"], {"position": "B"})

    state = coordinator.step({"position": "D"})

    assert state.authority == "specialist"
    assert state.passage_executed is True
    assert state.destination_realized is True
    assert state.status == "destination_realized"


def test_timeout_revokes_specialist_and_restores_baseline() -> None:
    controller = FakeRouteController()
    coordinator = HandoffCoordinator(controller, timeout_steps=2)
    coordinator.activate(["B", "C", "D"], {"position": "B"})

    coordinator.step({"position": "B"})
    state = coordinator.step({"position": "C"})

    assert state.authority == "baseline_v2"
    assert state.destination_realized is False
    assert state.fallback_invoked is True
    assert state.status == "controller_timeout"
    assert controller.is_active() is False


def test_interrupted_controller_revokes_stale_commitment() -> None:
    controller = FakeRouteController()
    coordinator = HandoffCoordinator(controller, timeout_steps=2)
    coordinator.activate(["B", "C", "D"], {"position": "B"})
    controller.deactivate()

    state = coordinator.step({"position": "B"})

    assert state.authority == "baseline_v2"
    assert state.passage_executed is False
    assert state.destination_realized is False
    assert state.status == "controller_interrupted"