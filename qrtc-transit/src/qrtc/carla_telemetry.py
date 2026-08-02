"""
CARLA live-drive harness — QRTC-compatible telemetry projection.

Builds a QRTC TransitInputRecord from a completed drive report and,
optionally, submits it through the configured transit pipeline.

No CARLA imports are required here. This module depends only on the
existing qrtc-transit pipeline utilities.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from qrtc.limits import canonical_json


# ---------------------------------------------------------------------------
# Evidence projection
# ---------------------------------------------------------------------------

_POLICY_VERSION = "1.0.0"
_PREDECESSOR_CLASS = "carla-telemetry"
_FUTURE_FAMILY = "carla-drive-evidence"

# Fields accepted as interface_projection in the QRTC evidence record.
# Lidar fields that are richer than the core schema go into a separate
# namespaced section inside ``context``.
_QRTC_INTERFACE_FIELDS = frozenset(
    {
        "run_id",
        "principal",
        "destination",
        "run_timestamp_utc",
        "map_name",
        "client_version",
        "server_version",
        "blueprint",
        "spawn_point_index",
        "fixed_delta",
        "ticks_requested",
        "ticks_completed",
        "collision_count",
        "displacement_m",
        "mean_speed_mps",
        "max_speed_mps",
        "lidar_enabled",
        "lidar_frames_received",
        "lidar_frames_dropped",
        "lidar_frames_natural_dropped",
        "lidar_frames_injected_dropped",
        "lidar_callback_errors",
        "lidar_nearest_obstacle_m",
        "lidar_nearest_front_m",
        "missing_data_count",
        "status",
    }
)


def _truncate_samples(
    samples: list[dict[str, Any]],
    max_count: int = 10,
) -> list[dict[str, Any]]:
    """Return up to ``max_count`` evenly-spaced samples."""
    if len(samples) <= max_count:
        return list(samples)
    step = len(samples) / max_count
    return [samples[int(i * step)] for i in range(max_count)]


def _config_digest(config_dict: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(config_dict).encode("utf-8")).hexdigest()


def _evidence_digest(evidence_dict: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(evidence_dict).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class QrtcProjection:
    """QRTC-compatible projection of a CARLA drive run."""

    transit_id: str
    principal: str
    destination: str
    expiration: datetime
    interface_projection: dict[str, Any]
    context: dict[str, Any]
    config_digest: str
    evidence_digest: str

    def as_input_dict(self) -> dict[str, Any]:
        """Return the structure expected by ``load_input_document``."""
        return {
            "transit_id": self.transit_id,
            "principal": self.principal,
            "destination": self.destination,
            "expiration": self.expiration.isoformat(),
            "interface_projection": self.interface_projection,
            "context": self.context,
        }

    def as_dict(self) -> dict[str, Any]:
        base = self.as_input_dict()
        base["config_digest"] = self.config_digest
        base["evidence_digest"] = self.evidence_digest
        return base


def build_qrtc_projection(
    run_report: dict[str, Any],
    *,
    principal: str | None = None,
    destination: str | None = None,
    expiration: datetime | None = None,
    max_samples: int = 10,
) -> QrtcProjection:
    """
    Build a QRTC-compatible telemetry projection from a CARLA run report.

    ``run_report`` is the dict produced by the harness (the same document
    written to the JSON output file).  This function does not import carla.
    """
    run_id = run_report.get("run_id") or str(uuid.uuid4())
    principal = principal or run_report.get("principal", "carla-operator")
    destination = destination or run_report.get("destination", "carla-drive-record")
    expiration = expiration or datetime(2099, 1, 1, tzinfo=UTC)

    cfg = run_report.get("config", {})
    summary = run_report.get("summary", {})
    lidar = run_report.get("lidar_summary", {})
    run_ts = run_report.get("run_timestamp_utc", datetime.now(UTC).isoformat())

    collision_count = int(summary.get("collision_count", 0))
    ticks_completed = int(run_report.get("ticks_completed", 0))
    ticks_requested = int(cfg.get("ticks", run_report.get("ticks_requested", 0)))
    displacement_m = float(summary.get("displacement_m", 0.0))
    mean_speed_mps = summary.get("mean_speed_mps")
    max_speed_mps = summary.get("max_speed_mps")
    missing_data_count = int(run_report.get("missing_data_count", 0))
    status = run_report.get("status", "unknown")

    lidar_enabled = bool(lidar.get("frames_received", 0)) or cfg.get("lidar", {}).get(
        "enabled", False
    )
    lidar_frames = int(lidar.get("frames_received", 0))
    lidar_dropped = int(lidar.get("frames_dropped", 0))
    lidar_natural_dropped = int(lidar.get("natural_drops", 0))
    lidar_injected_dropped = int(lidar.get("injected_drops", 0))
    lidar_cb_errors = int(lidar.get("callback_errors", 0))
    lidar_nearest = lidar.get("nearest_obstacle_overall")
    lidar_nearest_front = lidar.get("nearest_obstacle_front")

    interface_projection: dict[str, Any] = {
        "run_id": run_id,
        "principal": principal,
        "destination": destination,
        "run_timestamp_utc": run_ts,
        "map_name": run_report.get("map_name", ""),
        "client_version": run_report.get("client_version", ""),
        "server_version": run_report.get("server_version", ""),
        "blueprint": run_report.get("blueprint", ""),
        "spawn_point_index": int(run_report.get("spawn_point_index", 0)),
        "fixed_delta": float(cfg.get("fixed_delta", 0.05)),
        "ticks_requested": ticks_requested,
        "ticks_completed": ticks_completed,
        "collision_count": collision_count,
        "displacement_m": displacement_m,
        "mean_speed_mps": mean_speed_mps,
        "max_speed_mps": max_speed_mps,
        "lidar_enabled": lidar_enabled,
        "lidar_frames_received": lidar_frames,
        "lidar_frames_dropped": lidar_dropped,
        "lidar_frames_natural_dropped": lidar_natural_dropped,
        "lidar_frames_injected_dropped": lidar_injected_dropped,
        "lidar_callback_errors": lidar_cb_errors,
        "lidar_nearest_obstacle_m": lidar_nearest,
        "lidar_nearest_front_m": lidar_nearest_front,
        "missing_data_count": missing_data_count,
        "status": status,
    }

    # Bounded position/velocity samples
    raw_samples = run_report.get("samples", [])
    bounded_samples = _truncate_samples(raw_samples, max_count=max_samples)

    # Full lidar evidence goes into a namespaced context section
    lidar_context: dict[str, Any] = {
        "summary": lidar,
        "per_frame_evidence": _truncate_samples(
            run_report.get("lidar_frame_evidence", []), max_count=max_samples
        ),
        "dropped_frames": int(lidar.get("frames_dropped", 0)),
        "callback_errors": int(lidar.get("callback_errors", 0)),
    }

    context: dict[str, Any] = {
        "samples": bounded_samples,
        "collision_events": run_report.get("collision_events", []),
        "config_snapshot": cfg,
        "carla_lidar": lidar_context,
        "actor_id": run_report.get("actor_id"),
        "actor_type_id": run_report.get("actor_type_id"),
    }

    config_digest = _config_digest(cfg)
    evidence_digest = _evidence_digest(interface_projection)

    return QrtcProjection(
        transit_id=run_id,
        principal=principal,
        destination=destination,
        expiration=expiration,
        interface_projection=interface_projection,
        context=context,
        config_digest=config_digest,
        evidence_digest=evidence_digest,
    )


# ---------------------------------------------------------------------------
# Optional QRTC submission
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QrtcSubmissionResult:
    submitted: bool
    transit_id: str | None
    status: str
    failure_stage: str | None
    failure_reason: str | None
    db_path: str | None
    evidence_preserved: bool
    # Detailed authorization and guard decision information (may be None
    # when the pipeline did not reach the relevant stage).
    authorization_reason: str | None = None
    guard_reasons: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "submitted": self.submitted,
            "transit_id": self.transit_id,
            "status": self.status,
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "db_path": self.db_path,
            "evidence_preserved": self.evidence_preserved,
            "authorization_reason": self.authorization_reason,
            "guard_reasons": list(self.guard_reasons),
        }


def submit_to_qrtc_pipeline(
    projection: QrtcProjection,
    *,
    db_path: str = "qrtc_evidence.sqlite3",
    policy_path: str | None = None,
    carla_principal: str | None = None,
) -> QrtcSubmissionResult:
    """
    Attempt to submit ``projection`` through the configured QRTC pipeline.

    Returns a result describing acceptance/rejection, stage, and evidence DB
    location.  The evidence is *always* preserved regardless of outcome.

    If ``policy_path`` is None the function locates the bundled CARLA-specific
    policy (``examples/carla-policy.json``) shipped with qrtc-transit.

    ``carla_principal`` is forwarded to :func:`~qrtc.registry.build_default_registry`
    so the CARLA key policy authorises the same principal used in the projection.
    When *None* the value is read from the ``CARLA_PRINCIPAL`` environment
    variable (default ``"carla-operator"``), matching the behaviour of
    :func:`~qrtc.carla_config.carla_config_from_env`.
    """
    import json
    import tempfile
    from pathlib import Path

    from qrtc.config import load_input_document
    from qrtc.evidence_store import EvidenceStore
    from qrtc.pipeline import execute_configured_transit
    from qrtc.policy import load_policy_document
    from qrtc.registry import build_default_registry
    from qrtc.transit import TransitFailureState

    # Locate the CARLA-specific policy when none is explicitly provided
    if policy_path is None:
        _here = Path(__file__).resolve().parent
        candidate = _here.parent.parent / "examples" / "carla-policy.json"
        if not candidate.exists():
            # Fall back gracefully rather than silently using the wrong policy
            return QrtcSubmissionResult(
                submitted=False,
                transit_id=projection.transit_id,
                status="skipped",
                failure_stage="policy_load",
                failure_reason="no policy path provided and bundled carla-policy.json not found",
                db_path=db_path,
                evidence_preserved=False,
            )
        policy_path = str(candidate)

    try:
        policy = load_policy_document(policy_path)
    except Exception as exc:  # noqa: BLE001
        return QrtcSubmissionResult(
            submitted=False,
            transit_id=projection.transit_id,
            status="rejected",
            failure_stage="policy_load",
            failure_reason=str(exc),
            db_path=db_path,
            evidence_preserved=False,
        )

    # Write projection as a temporary input document
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(projection.as_input_dict(), tmp)
        tmp_path = tmp.name

    try:
        input_record = load_input_document(tmp_path)
    except Exception as exc:  # noqa: BLE001
        return QrtcSubmissionResult(
            submitted=False,
            transit_id=projection.transit_id,
            status="rejected",
            failure_stage="input_validation",
            failure_reason=str(exc),
            db_path=db_path,
            evidence_preserved=False,
        )
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    try:
        registry = build_default_registry(carla_principal=carla_principal)
        configured, outcome = execute_configured_transit(policy, input_record, registry)
    except Exception as exc:  # noqa: BLE001
        return QrtcSubmissionResult(
            submitted=False,
            transit_id=projection.transit_id,
            status="error",
            failure_stage="pipeline_execution",
            failure_reason=str(exc),
            db_path=db_path,
            evidence_preserved=False,
        )

    # Record the outcome in the evidence database.  A serialization error
    # (e.g. NaN in the interface) must not suppress the pipeline result.
    evidence_preserved = False
    try:
        store = EvidenceStore(db_path)
        store.record_transit(
            policy,
            input_record,
            configured.request,
            outcome,
            policy_hash=configured.policy_digest,
            registry_snapshot_id=configured.registry_snapshot_id,
            resolved_components=configured.resolved_component_ids,
        )
        evidence_preserved = True
    except Exception:  # noqa: BLE001
        pass

    accepted = outcome.failure_state is None

    # Extract authorization and guard reasons for richer reporting
    auth_reason: str | None = outcome.authorization.reason
    guard_reasons: tuple[dict[str, Any], ...] = tuple(
        {
            "guard_id": d.guard_id,
            "qualified": d.qualified,
            "reason": d.reason,
        }
        for d in outcome.guard_decisions
    )

    return QrtcSubmissionResult(
        submitted=True,
        transit_id=outcome.transit_id,
        status="accepted" if accepted else "rejected",
        failure_stage=outcome.failure_state.value if outcome.failure_state else None,
        failure_reason=None
        if accepted
        else (
            outcome.authorization.reason
            if outcome.failure_state is TransitFailureState.REJECTED_BY_KEY
            else (
                guard_reasons[-1]["reason"]
                if guard_reasons
                else str(outcome.failure_state)
            )
        ),
        db_path=db_path,
        evidence_preserved=evidence_preserved,
        authorization_reason=auth_reason,
        guard_reasons=guard_reasons,
    )
