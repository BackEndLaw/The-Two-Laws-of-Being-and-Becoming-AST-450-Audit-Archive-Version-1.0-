from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from qrtc.kernel import Future, analyze_gate


class HasAsDict(Protocol):
    def as_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class EquipmentState:
    equipment_id: str
    temperature: int
    pressure: int
    alarm_state: bool
    operator_name: str


def generate_states() -> list[EquipmentState]:
    states: list[EquipmentState] = []

    for equipment_id in ("pump-1", "pump-2"):
        for temperature in (60, 90):
            for pressure in (30, 70):
                for alarm_state in (False, True):
                    for operator_name in ("Alice", "Bob"):
                        states.append(
                            EquipmentState(
                                equipment_id=equipment_id,
                                temperature=temperature,
                                pressure=pressure,
                                alarm_state=alarm_state,
                                operator_name=operator_name,
                            )
                        )

    return states


FUTURES: tuple[Future[EquipmentState], ...] = (
    Future(
        name="equipment_identity",
        function=lambda state: state.equipment_id,
    ),
    Future(
        name="alarm_classification",
        function=lambda state: (
            "critical" if state.alarm_state or state.temperature >= 80 else "normal"
        ),
    ),
)


def exact_gate(state: EquipmentState) -> tuple[str, str]:
    """
    Retains exactly the distinctions visible to the declared futures.
    """

    classification = (
        "critical" if state.alarm_state or state.temperature >= 80 else "normal"
    )

    return state.equipment_id, classification


def insufficient_gate(state: EquipmentState) -> str:
    """
    Loses alarm classification.
    """

    return state.equipment_id


def excessive_gate(
    state: EquipmentState,
) -> tuple[str, str, str]:
    """
    Retains operator identity even though no declared future uses it.
    """

    classification = (
        "critical" if state.alarm_state or state.temperature >= 80 else "normal"
    )

    return (
        state.equipment_id,
        classification,
        state.operator_name,
    )


def print_report(name: str, report: HasAsDict) -> None:
    print(f"\n=== {name} ===")
    print(json.dumps(report.as_dict(), indent=2, default=str))


def main() -> None:
    states = generate_states()

    print_report(
        "Exact Gate",
        analyze_gate(states, FUTURES, exact_gate, max_witnesses=2),
    )

    print_report(
        "Insufficient Gate",
        analyze_gate(
            states,
            FUTURES,
            insufficient_gate,
            max_witnesses=2,
        ),
    )

    print_report(
        "Excessive Gate",
        analyze_gate(
            states,
            FUTURES,
            excessive_gate,
            max_witnesses=2,
        ),
    )


if __name__ == "__main__":
    main()
