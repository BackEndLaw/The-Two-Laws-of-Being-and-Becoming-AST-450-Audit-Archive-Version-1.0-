from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from rescueos.core.distinctions import ActionKind, Task


@dataclass(frozen=True)
class RescueResult:
    status: str
    history: tuple[Any, ...]
    task_loss: float
    actions_executed: int


class RescueController:
    def __init__(self, adapter, inference, planner, audit_log) -> None:
        self.adapter = adapter
        self.inference = inference
        self.planner = planner
        self.audit_log = audit_log

    def rescue(self, task: Task, max_actions: int = 4) -> RescueResult:
        history: list[Any] = []

        for step in range(max_actions + 1):
            observation = self.adapter.observe()
            task_loss = self.adapter.evaluate_task(task)

            if task_loss <= task.recovery_threshold:
                return self._finish("recovered", history, task_loss)

            belief = self.inference.update(observation, history, task)
            decision = self.planner.choose(belief, task, history)

            self.audit_log.record_decision(
                step=step,
                observation=observation,
                belief=belief,
                decision=decision,
            )

            if decision.kind == ActionKind.ABSTAIN:
                return self._finish("abstained", history, task_loss)
            if decision.kind == ActionKind.STOP:
                return self._finish("stopped", history, task_loss)

            outcome = self.adapter.apply(decision.action_id)
            history.append(outcome)
            self.audit_log.record_outcome(step=step, outcome=outcome)

            post_action_loss = self.adapter.evaluate_task(task)
            if post_action_loss <= task.recovery_threshold:
                return self._finish("recovered", history, post_action_loss)

        final_loss = self.adapter.evaluate_task(task)
        return self._finish("budget_exhausted", history, final_loss)

    @staticmethod
    def _finish(status: str, history: list[Any], task_loss: float) -> RescueResult:
        return RescueResult(
            status=status,
            history=tuple(history),
            task_loss=task_loss,
            actions_executed=len(history),
        )
