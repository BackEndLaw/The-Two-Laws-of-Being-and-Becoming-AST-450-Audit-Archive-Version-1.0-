from __future__ import annotations

from copy import deepcopy
from typing import Protocol


class VehicleAdapter(Protocol):
    def observe(self) -> dict:
        """Return position, route graph, obstacles, and controller state."""

    def apply(self, action: dict) -> dict:
        """Apply a selected command and return its realized outcome."""

    def safe_stop(self) -> None:
        """Enter the simulator's minimal-risk state."""


class GraphVehicleAdapter:
    """Deterministic road-graph environment with no policy authority."""

    def __init__(self, scenario: dict) -> None:
        self._scenario = deepcopy(scenario)
        self._position = scenario["initial_state"]["position"]
        self._controller = scenario["initial_state"]["controller"]
        self._stopped = False
        self._collision = False

    def observe(self) -> dict:
        return {
            "position": self._position,
            "route": list(self._scenario["route"]),
            "route_graph": deepcopy(self._scenario["route_graph"]),
            "blocked_edges": deepcopy(self._scenario["blocked_edges"]),
            "controller": self._controller,
            "stopped": self._stopped,
            "collision": self._collision,
        }

    def apply(self, action: dict) -> dict:
        action_type = action["type"]
        if action_type == "controlled_stop":
            self.safe_stop()
            return {"executed": True, "succeeded": True, "collision": False}
        if action_type != "handoff":
            raise ValueError(f"Unsupported vehicle action: {action_type}")

        if not action.get("succeeds", True):
            return {"executed": True, "succeeded": False, "collision": False}

        route = action["route"]
        blocked = {tuple(edge) for edge in self._scenario["blocked_edges"]}
        traversed = set(zip(route, route[1:]))
        if traversed & blocked:
            self._collision = True
            return {"executed": True, "succeeded": False, "collision": True}

        self._position = route[-1]
        self._controller = action["controller"]
        return {"executed": True, "succeeded": True, "collision": False}

    def safe_stop(self) -> None:
        self._stopped = True
        self._controller = "baseline_v2"