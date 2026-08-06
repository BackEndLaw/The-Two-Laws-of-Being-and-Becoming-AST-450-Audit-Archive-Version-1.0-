from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from rescueos.compiler.graph_compiler import compile_graph
from rescueos.compiler.schema import StageSpec, SystemSpec
from rescueos.core.distinctions import ActionKind, BeliefState, Intervention, Task
from rescueos.experiments.adaptive_benchmark import (
    POLICIES,
    run_adaptive_benchmark,
    stratified_cluster_bootstrap,
)
from rescueos.policies.hybrid_qrtc import HybridQRTCPolicy, LearnedResidualActionModel


REPO_ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _payload() -> dict:
    return run_adaptive_benchmark(
        REPO_ROOT / "configs" / "communication_system.yaml",
        REPO_ROOT / "configs" / "development_mechanisms.json",
        REPO_ROOT / "configs" / "hidden_mechanisms.json",
        REPO_ROOT / "configs" / "hidden_mechanisms.lock.json",
        replicates=1,
        bootstrap_samples=100,
    )


def test_adaptive_benchmark_holds_out_each_family_and_matches_policies() -> None:
    payload = _payload()
    folds = set(payload["fold_calibration"])
    grouped: dict[tuple[str, int], set[str]] = {}

    for row in payload["trials"]:
        assert row["mechanism_family"] == row["heldout_family"]
        grouped.setdefault((row["cluster_id"], row["replicate"]), set()).add(
            row["policy"]
        )

    assert folds == {row["heldout_family"] for row in payload["trials"]}
    assert all(policies == set(POLICIES) for policies in grouped.values())
    assert payload["evaluation"] == "leave_one_mechanism_family_out"


def test_adaptive_benchmark_reports_calibration_and_blocks_validation() -> None:
    payload = _payload()

    assert all("brier_improvement" in row for row in payload["fold_calibration"].values())
    assert payload["bootstrap"]["method"] == "family-stratified paired cluster bootstrap"
    assert payload["development_acceptance"]["protocol_frozen_before_validation"] is False
    assert payload["development_acceptance"]["validation_authorized"] is False
    assert payload["hardware_actuation_enabled"] is False
    assert payload["design"]["balanced_clusters"] is True


def test_stratified_bootstrap_weights_families_equally() -> None:
    interval = stratified_cluster_bootstrap(
        {
            "family_a": {"a1": 1.0, "a2": 1.0},
            "family_b": {"b1": -1.0},
        },
        samples=100,
        seed=9,
    )

    assert interval["estimate"] == 0.0
    assert interval["per_family"] == {"family_a": 1.0, "family_b": -1.0}


def test_residual_model_uses_only_public_observation_features() -> None:
    model = LearnedResidualActionModel.fit(
        [
            {
                "action_id": "repair",
                "action_kind": "repair",
                "predicted_recovery": 0.4,
                "realized_recovery": 1.0,
                "public_observation": {
                    "distinction_health": {"output": 0.2},
                    "confidence": 0.8,
                    "unknown_probability": 0.2,
                },
            }
        ]
    )
    serialized = repr(model.parameters())

    assert "mechanism_id" not in serialized
    assert "hidden_parameters" not in serialized
    assert "local_health" not in serialized
    assert "oracle" not in serialized


def test_hybrid_policy_cannot_select_graph_invalid_action() -> None:
    task = Task("deliver", {"output": 0.9}, 0.05)
    relevant = Intervention(
        "repair_output",
        ActionKind.REPAIR,
        frozenset({"decision"}),
        frozenset({"output"}),
        0.1,
        success_probability=1.0,
    )
    irrelevant = Intervention(
        "repair_branch",
        ActionKind.REPAIR,
        frozenset({"branch"}),
        frozenset({"branch_output"}),
        0.0,
        success_probability=1.0,
    )
    graph = compile_graph(
        SystemSpec(
            "constraint_test",
            False,
            (
                StageSpec("decision", (), ("output",)),
                StageSpec("branch", (), ("branch_output",)),
            ),
            (task,),
            (relevant, irrelevant),
        )
    )
    model = LearnedResidualActionModel(
        feature_names=("branch_output", "output"),
        weights={
            "repair_output": (0.0, 0.0, 0.0, 0.0, 0.0),
            "repair_branch": (10.0, 0.0, 0.0, 0.0, 0.0),
        },
        uncertainty={"repair_output": 0.05, "repair_branch": 0.05},
    )
    policy = HybridQRTCPolicy([irrelevant, relevant], graph, model)
    belief = BeliefState(
        distinction_health={"output": 0.1, "branch_output": 0.1},
        fault_probabilities={},
        unknown_probability=0.0,
        confidence=1.0,
    )

    assert policy.choose(belief, task, []).action_id == "repair_output"