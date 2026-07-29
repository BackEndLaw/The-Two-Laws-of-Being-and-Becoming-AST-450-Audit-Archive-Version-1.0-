from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

import pytest

from rescueos.core.distinctions import ActionOutcome
from rescueos.experiments.lock_v2_reporting import build_reporting_lock
from rescueos.experiments.targeted_v3_benchmark import run_targeted_v3
from rescueos.policies.conservative_hybrid_qrtc import ConservativeTemporalResidualModel


REPO_ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _payload() -> dict:
    protocol = json.loads((REPO_ROOT / "configs" / "adaptive_v3_protocol.json").read_text())
    protocol["design"]["replicates_per_cluster"] = 1
    protocol["bootstrap"]["resamples"] = 100
    temporary = REPO_ROOT / "artifacts" / "phase6" / ".adaptive_v3_test_protocol.json"
    temporary.write_text(json.dumps(protocol), encoding="utf-8")
    try:
        return run_targeted_v3(
            REPO_ROOT / "configs" / "communication_system.yaml",
            REPO_ROOT / "configs" / "development_mechanisms.json",
            REPO_ROOT / "configs" / "hidden_mechanisms.json",
            REPO_ROOT / "configs" / "hidden_mechanisms.lock.json",
            temporary,
        )
    finally:
        temporary.unlink(missing_ok=True)


def _record(health: float, realized: float) -> dict:
    return {
        "action_id": "repair",
        "action_kind": "repair",
        "predicted_recovery": 0.4,
        "realized_recovery": realized,
        "public_observation": {
            "distinction_health": {"output": health},
            "confidence": health,
            "unknown_probability": 1.0 - health,
        },
        "public_history": [],
    }


def test_conservative_residual_shrinks_outside_training_support() -> None:
    model = ConservativeTemporalResidualModel.fit(
        [_record(0.4, 1.0), _record(0.5, 1.0), _record(0.6, 1.0)]
    )
    in_support = model.predict(_record(0.5, 1.0)["public_observation"], [], "repair")
    shifted = model.predict(_record(1.0, 1.0)["public_observation"], [], "repair")

    assert 0.0 <= shifted.alpha <= 1.0
    assert shifted.alpha < in_support.alpha
    assert abs(shifted.residual) <= abs(shifted.raw_residual)


def test_temporal_model_uses_public_history_without_hidden_fields() -> None:
    model = ConservativeTemporalResidualModel.fit(
        [_record(0.4, 1.0), _record(0.6, 0.0)]
    )
    outcome = ActionOutcome(
        action_id="inspect",
        succeeded=True,
        task_loss=0.2,
        cost=0.1,
        harm=0.0,
        unsafe=False,
        observation={
            "distinction_health": {"output": 0.3},
            "confidence": 0.7,
            "unknown_probability": 0.3,
        },
    )
    model.predict(_record(0.6, 0.0)["public_observation"], [outcome], "repair")
    serialized = repr(model.parameters())

    assert "mechanism_id" not in serialized
    assert "hidden_parameters" not in serialized
    assert "local_health" not in serialized
    assert "oracle" not in serialized


def test_targeted_v3_requires_frozen_protocol(tmp_path: Path) -> None:
    protocol = json.loads((REPO_ROOT / "configs" / "adaptive_v3_protocol.json").read_text())
    protocol["frozen_before_execution"] = False
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")

    with pytest.raises(ValueError, match="frozen"):
        run_targeted_v3(
            REPO_ROOT / "configs" / "communication_system.yaml",
            REPO_ROOT / "configs" / "development_mechanisms.json",
            REPO_ROOT / "configs" / "hidden_mechanisms.json",
            REPO_ROOT / "configs" / "hidden_mechanisms.lock.json",
            path,
        )


def test_targeted_v3_reports_every_family_diagnostic_and_stays_closed() -> None:
    payload = _payload()
    required_metrics = {
        "utility",
        "recovery_rate",
        "stopping_rate",
        "evidence_request_rate",
        "first_action_oracle_agreement",
        "oracle_regret",
        "mean_cost",
        "mean_harm",
        "unsafe_rate",
        "action_selection_distribution",
    }

    assert len(payload["family_diagnostics"]) == 4
    for family in payload["family_diagnostics"].values():
        assert {"paired_utility_difference", "policies", "calibration"} <= set(family)
        assert all(required_metrics <= set(metrics) for metrics in family["policies"].values())
        assert {"graph_brier", "conservative_brier", "expected_calibration_error"} <= set(family["calibration"])
    assert payload["development_acceptance"]["graph_invalid_action_rate_zero"]
    assert payload["hardware_actuation_enabled"] is False
    assert payload["hardware_gate"] == "NOT READY"


def test_v2_reporting_lock_names_comparator_and_design() -> None:
    artifact = REPO_ROOT / "artifacts" / "phase6" / "ADAPTIVE_QRTC_DEVELOPMENT_V2.json"
    payload = json.loads(artifact.read_text())
    lock = build_reporting_lock(payload, artifact_sha256="digest")

    assert lock["primary_comparison"]["comparator"] == "end_to_end"
    assert lock["design"]["matched_trials_per_policy"] == 128
    assert lock["design"]["independent_cluster_count"] == 16
    assert lock["bootstrap"]["resamples"] == 2000
    assert lock["bootstrap"]["seed"] == 1450
    assert len(lock["per_family_intervals"]) == 4