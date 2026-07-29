from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from rescueos.adapters.simulator import (
    NONORACLE_OBSERVATION_FIELDS,
    SimulatorAdapter,
)
from rescueos.compiler.graph_compiler import compile_graph
from rescueos.compiler.loader import load_system_spec
from rescueos.core.distinctions import ActionKind, Intervention
from rescueos.experiments.hidden_transfer import (
    ALL_POLICIES,
    iter_scenarios,
    load_manifest,
    manifest_values,
    run_hidden_transfer_gate,
    validate_manifests,
    verify_hidden_lock,
)
from rescueos.simulator.communication_link import CommunicationLinkSimulator
from rescueos.simulator.fault_injector import Fault


REPO_ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_PATH = REPO_ROOT / "configs" / "development_mechanisms.json"
HIDDEN_PATH = REPO_ROOT / "configs" / "hidden_mechanisms.json"
LOCK_PATH = REPO_ROOT / "configs" / "hidden_mechanisms.lock.json"


def _manifests() -> tuple[dict, dict]:
    return load_manifest(DEVELOPMENT_PATH), load_manifest(HIDDEN_PATH)


def _adapter(*, oracle: bool = False) -> SimulatorAdapter:
    intervention = Intervention(
        action_id="repair",
        kind=ActionKind.REPAIR,
        targets=frozenset({"receiver"}),
        restores=frozenset({"decoded_message"}),
        cost=0.0,
        success_probability=1.0,
    )
    simulator = CommunicationLinkSimulator(
        [intervention],
        faults=[Fault("hidden_mechanism_17", ("decoded_message",), 0.4)],
    )
    return SimulatorAdapter(simulator, oracle_observations=oracle)


def test_hidden_ids_are_absent_from_policy_observations() -> None:
    observation = _adapter().observe()

    assert tuple(observation) == NONORACLE_OBSERVATION_FIELDS
    assert "hidden_mechanism_17" not in repr(observation)


def test_policy_cannot_access_latent_simulator_state() -> None:
    adapter = _adapter()

    assert "local_health" not in adapter.observe()
    assert "local_health" not in adapter.apply("repair").observation


def test_oracle_fields_are_removed_for_nonoracle_policies() -> None:
    nonoracle = _adapter().observe()
    oracle = _adapter(oracle=True).observe()

    assert "fault_probabilities" not in nonoracle
    assert "local_health" not in nonoracle
    assert "fault_probabilities" in oracle
    assert "local_health" in oracle


def test_development_and_hidden_mechanisms_are_disjoint() -> None:
    development, hidden = _manifests()

    assert manifest_values(development, "mechanism_id").isdisjoint(
        manifest_values(hidden, "mechanism_id")
    )
    assert manifest_values(development, "scenario_id").isdisjoint(
        manifest_values(hidden, "scenario_id")
    )


def test_development_and_hidden_seeds_are_disjoint() -> None:
    development, hidden = _manifests()

    assert manifest_values(development, "seed").isdisjoint(
        manifest_values(hidden, "seed")
    )


def test_hidden_parameters_are_absent_from_features() -> None:
    _, hidden = _manifests()

    for scenario in iter_scenarios(hidden):
        observation = _adapter().observe()
        assert "hidden_parameters" not in repr(observation)
        assert "mechanism_id" not in repr(observation)
        assert scenario["scenario_id"] not in repr(observation)


def test_observation_schema_is_identical_across_mechanisms() -> None:
    development, hidden = _manifests()
    schemas = set()
    spec = load_system_spec(REPO_ROOT / "configs" / "communication_system.yaml")
    graph = compile_graph(spec)

    for manifest in (development, hidden):
        for scenario in iter_scenarios(manifest):
            faults = [
                Fault(item["fault_id"], tuple(item["affected_distinctions"]), item["severity"])
                for item in scenario["faults"]
            ]
            adapter = SimulatorAdapter(
                CommunicationLinkSimulator(spec.interventions, faults=faults, graph=graph),
                oracle_observations=False,
            )
            observation = adapter.observe()
            schemas.add(
                (
                    tuple(observation),
                    tuple(sorted(observation["distinction_health"])),
                )
            )

    assert len(schemas) == 1


def test_hidden_manifest_is_frozen_before_evaluation(tmp_path: Path) -> None:
    verify_hidden_lock(HIDDEN_PATH, LOCK_PATH)
    tampered = tmp_path / "hidden.json"
    tampered.write_text(HIDDEN_PATH.read_text() + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="digest"):
        verify_hidden_lock(tampered, LOCK_PATH)


def test_manifest_validation_rejects_overlap() -> None:
    development, hidden = _manifests()
    overlapping = deepcopy(hidden)
    overlapping["mechanisms"][0]["scenarios"][0]["seed"] = next(
        iter(manifest_values(development, "seed"))
    )

    with pytest.raises(ValueError, match="seed"):
        validate_manifests(development, overlapping)


def test_hidden_gate_uses_matched_trials_and_bootstrap() -> None:
    payload = run_hidden_transfer_gate(
        REPO_ROOT / "configs" / "communication_system.yaml",
        DEVELOPMENT_PATH,
        HIDDEN_PATH,
        LOCK_PATH,
        max_actions=2,
        bootstrap_samples=100,
    )
    grouped: dict[str, set[tuple[int, str]]] = {}
    for row in payload["trials"]:
        grouped.setdefault(row["scenario_id"], set()).add((row["seed"], row["policy"]))

    assert payload["deterministic_hidden_transfer_passed"]
    assert payload["matched_policy_trials"]
    assert payload["paired_cluster_bootstrap_available"]
    assert all({policy for _, policy in values} == set(ALL_POLICIES) for values in grouped.values())
    assert all(len({seed for seed, _ in values}) == 1 for values in grouped.values())
    assert set(payload["paired_cluster_bootstrap"]) == {"qrtc_untyped", "end_to_end"}
    assert payload["hardware_actuation_enabled"] is False