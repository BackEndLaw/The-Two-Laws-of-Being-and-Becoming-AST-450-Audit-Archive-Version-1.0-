from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_SCENARIO_FIELDS = {
    "schema_version",
    "scenario_id",
    "name",
    "simulator",
    "initial_conditions",
    "fault",
    "expected_authority_transitions",
    "terminal_conditions",
    "acceptance_criteria",
    "expected",
    "native_carla_physics",
}


@dataclass(frozen=True)
class CampaignRun:
    scenario_id: str
    seed: int
    seed_class: str
    events: tuple[dict[str, Any], ...]

    def write_jsonl(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in self.events),
            encoding="utf-8",
        )


class SemanticTrace:
    def __init__(self, scenario: dict[str, Any], seed: int, seed_class: str) -> None:
        initial = scenario["initial_conditions"]
        self.scenario = scenario
        self.seed = seed
        self.seed_class = seed_class
        self.authority = initial["authority"]
        self.admitted = False
        self.passage_requested = False
        self.passage_executed = False
        self.destination_realized = False
        self.fallback_invoked = False
        self.minimal_risk = False
        self.events: list[dict[str, Any]] = []

    def record(
        self,
        event: str,
        *,
        accepted_command: str | None = None,
        terminal_state: str | None = None,
        **details: Any,
    ) -> None:
        self.events.append(
            {
                "schema_version": "graph-fault-witness-v1",
                "scenario_id": self.scenario["scenario_id"],
                "simulator": "graph",
                "native_carla_physics": "NOT_EVALUATED",
                "seed": self.seed,
                "seed_class": self.seed_class,
                "sequence": len(self.events),
                "event": event,
                "authority": self.authority,
                "authority_count": 1,
                "admitted": self.admitted,
                "passage_requested": self.passage_requested,
                "passage_executed": self.passage_executed,
                "destination_realized": self.destination_realized,
                "fallback_invoked": self.fallback_invoked,
                "minimal_risk": self.minimal_risk,
                "accepted_command": accepted_command,
                "terminal_state": terminal_state,
                "collision": False,
                "illegal_graph_transition": False,
                "witness_complete": True,
                **details,
            }
        )

    def transition(self, authority: str, reason: str) -> None:
        previous = self.authority
        self.authority = authority
        self.record(
            "authority_transition",
            previous_authority=previous,
            next_authority=authority,
            reason=reason,
        )


def load_campaign_scenario(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as source:
        scenario = json.load(source)
    validate_campaign_scenario(scenario)
    return scenario


def validate_campaign_scenario(scenario: dict[str, Any]) -> None:
    missing = REQUIRED_SCENARIO_FIELDS - set(scenario)
    if missing:
        raise ValueError(f"Scenario is missing required fields: {sorted(missing)}")
    if scenario["schema_version"] != "graph-fault-campaign-v1":
        raise ValueError("Unsupported graph fault campaign schema")
    if scenario["simulator"] != "graph":
        raise ValueError("Graph fault scenarios must use simulator=graph")
    if scenario["native_carla_physics"] != "NOT_EVALUATED":
        raise ValueError("Native CARLA physics must remain NOT_EVALUATED")


def run_campaign_scenario(
    scenario: dict[str, Any], *, seed: int, seed_class: str
) -> CampaignRun:
    validate_campaign_scenario(scenario)
    trace = SemanticTrace(scenario, seed, seed_class)
    trace.record("initial_state")
    fault_type = scenario["fault"]["type"]
    handler = _FAULT_HANDLERS.get(fault_type)
    if handler is None:
        raise ValueError(f"Unsupported graph fault type: {fault_type}")
    handler(trace)
    return CampaignRun(scenario["scenario_id"], seed, seed_class, tuple(trace.events))


def replay_campaign_run(scenario: dict[str, Any], run: CampaignRun) -> bool:
    replayed = run_campaign_scenario(
        scenario,
        seed=run.seed,
        seed_class=run.seed_class,
    )
    return replayed.events == run.events


def evaluate_campaign_run(scenario: dict[str, Any], run: CampaignRun) -> dict[str, Any]:
    terminal = run.events[-1]
    violations: list[str] = []
    for event in run.events:
        if not event["admitted"] and (
            event["passage_executed"] or event["destination_realized"]
        ):
            violations.append("denied_transfer_claimed_passage_or_destination")
        if not event["passage_executed"] and event["destination_realized"]:
            violations.append("destination_realized_without_executed_passage")
        if event["destination_realized"] and not event["admitted"]:
            violations.append("destination_realized_without_admission")
        if event["authority_count"] != 1:
            violations.append("simultaneous_or_missing_authority")
        if event["accepted_command"] and event.get("command_issuer") != event["authority"]:
            violations.append("command_accepted_from_non_authority")
        if not event["witness_complete"]:
            violations.append("incomplete_witness")
        if event["collision"] or event["illegal_graph_transition"]:
            violations.append("unsafe_graph_transition")

    expected = scenario["expected"]
    expected_fields = {
        "admitted": terminal["admitted"],
        "passage_requested": terminal["passage_requested"],
        "passage_executed": terminal["passage_executed"],
        "destination_realized": terminal["destination_realized"],
        "fallback_required": terminal["fallback_invoked"],
        "terminal_state": terminal["terminal_state"],
    }
    for field, actual in expected_fields.items():
        if expected[field] != actual:
            violations.append(f"expectation_mismatch:{field}")

    transitions = [
        [event["previous_authority"], event["next_authority"]]
        for event in run.events
        if event["event"] == "authority_transition"
    ]
    if transitions != scenario["expected_authority_transitions"]:
        violations.append("authority_transition_mismatch")
    if not replay_campaign_run(scenario, run):
        violations.append("replay_mismatch")

    return {
        "passed": not violations,
        "violations": sorted(set(violations)),
        "terminal_state": terminal["terminal_state"],
        "authority": terminal["authority"],
        "witness_complete": all(event["witness_complete"] for event in run.events),
        "replay_verified": "replay_mismatch" not in violations,
        "collision": any(event["collision"] for event in run.events),
        "illegal_graph_transition": any(
            event["illegal_graph_transition"] for event in run.events
        ),
    }


def _run_handoff_timeout(trace: SemanticTrace) -> None:
    trace.record("fault_detected", fault_type="handoff_timeout")
    trace.admitted = True
    trace.passage_requested = True
    trace.record("gate_admitted_and_passage_requested")
    trace.record("handoff_timeout", timeout_step=trace.scenario["fault"]["injection_step"])
    trace.fallback_invoked = True
    trace.record(
        "fallback_invoked",
        terminal_state="safe",
        reason="handoff_timeout",
    )


def _run_blockage_before_passage(trace: SemanticTrace) -> None:
    trace.record("initial_blockage_detected")
    trace.admitted = True
    trace.passage_requested = True
    trace.record("gate_admitted_and_passage_requested")
    trace.record("post_admission_blockage_detected")
    trace.fallback_invoked = True
    trace.record(
        "transfer_revalidated_and_rejected",
        terminal_state="safe",
        reason="alternate_route_became_unsafe",
    )


def _run_specialist_interruption(trace: SemanticTrace) -> None:
    trace.record("route_blockage_detected")
    trace.admitted = True
    trace.passage_requested = True
    trace.record("gate_admitted_and_passage_requested")
    trace.transition("specialist", "activation_acknowledged")
    trace.passage_executed = True
    trace.record(
        "specialist_command_executed",
        accepted_command="follow_alternate_route",
        command_issuer="specialist",
    )
    trace.record("specialist_interrupted")
    trace.fallback_invoked = True
    trace.transition("baseline_v2", "specialist_interrupted")
    trace.record(
        "controlled_stop",
        accepted_command="controlled_stop",
        command_issuer="baseline_v2",
        terminal_state="safe",
    )


def _run_no_safe_alternate(trace: SemanticTrace) -> None:
    trace.record("route_blockage_detected")
    trace.record("gate_denied", reason="no_safe_alternate_route")
    trace.fallback_invoked = True
    trace.minimal_risk = True
    trace.record(
        "controlled_stop",
        accepted_command="controlled_stop",
        command_issuer="baseline_v2",
        terminal_state="minimal_risk",
    )


def _run_repeated_blockage(trace: SemanticTrace) -> None:
    trace.record("initial_blockage_detected")
    trace.admitted = True
    trace.passage_requested = True
    trace.record("first_passage_requested")
    trace.record("repeated_blockage_detected")
    trace.record("stale_commitment_revoked")
    trace.record("replacement_route_admitted")
    trace.transition("specialist", "replacement_route_acknowledged")
    trace.passage_executed = True
    trace.record(
        "replacement_route_command_executed",
        accepted_command="follow_replanned_route",
        command_issuer="specialist",
    )
    trace.destination_realized = True
    trace.record("destination_realized", terminal_state="route_recovered")


def _run_invalid_observation(trace: SemanticTrace) -> None:
    for subcase in trace.scenario["fault"]["subcases"]:
        trace.record(
            "observation_rejected",
            subcase=subcase["id"],
            reason=subcase["type"],
        )
    trace.fallback_invoked = True
    trace.record(
        "wait_safely",
        accepted_command="hold_position",
        command_issuer="baseline_v2",
        terminal_state="safe_wait",
    )


def _run_conflicting_map(trace: SemanticTrace) -> None:
    trace.record("conflicting_map_evidence_detected")
    trace.record("gate_denied", reason="evidence_conflict")
    trace.fallback_invoked = True
    trace.minimal_risk = True
    trace.record(
        "controlled_stop",
        accepted_command="controlled_stop",
        command_issuer="baseline_v2",
        terminal_state="minimal_risk",
        private_map_detail_exposed=False,
    )


def _run_stale_authority(trace: SemanticTrace) -> None:
    trace.record(
        "stale_command_rejected",
        rejected_controller="expired_specialist",
        rejected_command="follow_old_route",
    )
    trace.record(
        "baseline_hold",
        accepted_command="hold_position",
        command_issuer="baseline_v2",
        terminal_state="safe",
    )


def _run_baseline_failure(trace: SemanticTrace) -> None:
    trace.record(
        "baseline_command_rejected",
        rejected_controller="baseline_v2",
        rejected_command="controlled_stop",
    )
    trace.fallback_invoked = True
    trace.transition("recovery_controller", "baseline_controller_failed")
    trace.minimal_risk = True
    trace.record(
        "recovery_stop",
        accepted_command="minimal_risk_stop",
        command_issuer="recovery_controller",
        terminal_state="minimal_risk",
    )


def _run_fallback_failure(trace: SemanticTrace) -> None:
    trace.admitted = True
    trace.passage_requested = True
    trace.record("gate_admitted_and_passage_requested")
    trace.transition("specialist", "activation_acknowledged")
    trace.passage_executed = True
    trace.record(
        "specialist_command_executed",
        accepted_command="follow_alternate_route",
        command_issuer="specialist",
    )
    trace.record("specialist_failed")
    trace.fallback_invoked = True
    trace.transition("fallback_controller", "specialist_failed")
    trace.record(
        "fallback_command_rejected",
        rejected_controller="fallback_controller",
        rejected_command="controlled_stop",
    )
    trace.transition("minimal_risk_controller", "fallback_controller_failed")
    trace.minimal_risk = True
    trace.record(
        "final_minimal_risk_state",
        accepted_command="emergency_hold",
        command_issuer="minimal_risk_controller",
        terminal_state="degraded_minimal_risk",
    )


_FAULT_HANDLERS = {
    "blockage_before_passage": _run_blockage_before_passage,
    "handoff_timeout": _run_handoff_timeout,
    "specialist_interruption": _run_specialist_interruption,
    "no_safe_alternate_route": _run_no_safe_alternate,
    "repeated_route_blockage": _run_repeated_blockage,
    "invalid_observation": _run_invalid_observation,
    "conflicting_map_information": _run_conflicting_map,
    "stale_controller_authority": _run_stale_authority,
    "baseline_controller_failure": _run_baseline_failure,
    "fallback_controller_failure": _run_fallback_failure,
}