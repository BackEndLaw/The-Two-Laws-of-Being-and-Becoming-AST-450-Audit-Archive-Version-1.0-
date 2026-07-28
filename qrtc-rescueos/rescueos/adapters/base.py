from __future__ import annotations

from typing import Protocol

from rescueos.core.distinctions import ActionOutcome, Task


class SystemAdapter(Protocol):
    def observe(self) -> dict:
        ...

    def evaluate_task(self, task: Task) -> float:
        ...

    def apply(self, action_id: str) -> ActionOutcome:
        ...

    def emergency_stop(self) -> None:
        ...
