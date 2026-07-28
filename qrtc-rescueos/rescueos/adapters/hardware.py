from __future__ import annotations

from rescueos.core.distinctions import ActionOutcome, Task


class HardwareAdapter:
    """Placeholder adapter for HIL/physical integration without controller changes."""

    def observe(self) -> dict:
        raise NotImplementedError("Hardware observe adapter is not implemented yet")

    def evaluate_task(self, task: Task) -> float:
        raise NotImplementedError("Hardware task evaluation adapter is not implemented yet")

    def apply(self, action_id: str) -> ActionOutcome:
        raise NotImplementedError("Hardware apply adapter is not implemented yet")

    def emergency_stop(self) -> None:
        raise NotImplementedError("Hardware emergency stop adapter is not implemented yet")
