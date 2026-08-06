from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable

from rescueos.compiler.schema import CompiledGraph
from rescueos.core.distinctions import ActionKind, ActionOutcome, Intervention, Task
from rescueos.core.transition import RealizedOutcome, SystemState, TransitionModel, evaluate_task
from rescueos.simulator.fault_injector import Fault, apply_faults
from rescueos.simulator.observations import make_snapshot


@dataclass(frozen=True)
class SimulatorCheckpoint:
    state: SystemState
    rng_state: object
    stopped: bool


class CommunicationLinkSimulator:
    def __init__(
        self,
        interventions: Iterable[Intervention],
        *,
        seed: int = 0,
        initial_health: dict[str, float] | None = None,
        faults: list[Fault] | None = None,
        graph: CompiledGraph | None = None,
        transition_model: TransitionModel | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self._interventions = {action.action_id: action for action in interventions}
        self._transition_model = transition_model or TransitionModel(graph)
        if graph is not None and self._transition_model.graph_checksum != graph.checksum:
            raise ValueError("Simulator and transition model graph checksums differ")
        self._base_health = initial_health or {
            "decoded_message": 1.0,
            "confidence": 1.0,
            "timing": 1.0,
            "symbol_estimate": 1.0,
            "received_amplitude": 1.0,
            "received_phase": 1.0,
            "encoded_amplitude": 1.0,
            "encoded_phase": 1.0,
            "symbol_identity": 1.0,
        }
        self._faults = faults or []
        local_health = apply_faults(self._base_health, self._faults)
        self._state = SystemState.from_health(local_health)
        if self._transition_model.graph is not None:
            self._transition_model.graph.propagate(
                self._state,
                frozenset(self._transition_model.graph.topological_order),
            )
        self._stopped = False

    @property
    def graph_checksum(self) -> str | None:
        return self._transition_model.graph_checksum

    @property
    def state(self) -> SystemState:
        return self._state.copy()

    def checkpoint(self) -> SimulatorCheckpoint:
        return SimulatorCheckpoint(
            state=self._state.copy(),
            rng_state=self._rng.getstate(),
            stopped=self._stopped,
        )

    def restore(self, checkpoint: SimulatorCheckpoint) -> None:
        self._state = checkpoint.state.copy()
        self._rng.setstate(checkpoint.rng_state)
        self._stopped = checkpoint.stopped

    def observe(self) -> dict:
        confidence = float(self._state.distinction_quality.get("confidence", 0.0))
        unknown_probability = max(0.0, 1.0 - confidence)
        fault_probabilities = {fault.fault_id: min(1.0, fault.severity) for fault in self._faults}
        snapshot = make_snapshot(
            distinction_health=self._state.distinction_quality,
            confidence=confidence,
            unknown_probability=unknown_probability,
            fault_probabilities=fault_probabilities,
        )
        snapshot["local_health"] = dict(self._state.local_health)
        return snapshot

    def evaluate_task(self, task: Task) -> float:
        return evaluate_task(self._state, task)

    def apply(self, action_id: str) -> ActionOutcome:
        if self._stopped:
            raise RuntimeError("System is emergency-stopped")

        if action_id not in self._interventions:
            raise KeyError(f"Undeclared action: {action_id}")

        action = self._interventions[action_id]
        succeeded = self._rng.random() <= action.success_probability
        self._state = self._transition_model.apply(
            state=self._state,
            action=action,
            realized_outcome=RealizedOutcome(succeeded=succeeded),
        )

        unsafe = action.kind == ActionKind.REPAIR and self._rng.random() < action.harm_risk
        harm = 1.0 if unsafe else 0.0
        observation = self.observe()
        return ActionOutcome(
            action_id=action.action_id,
            succeeded=succeeded,
            task_loss=0.0,
            cost=action.cost,
            harm=harm,
            unsafe=unsafe,
            observation=observation,
        )

    def emergency_stop(self) -> None:
        self._stopped = True
