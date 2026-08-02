from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from qrtc.boat import BoatCodec
from qrtc.config import TransitInputRecord
from qrtc.destination import DefaultRealizer, DefaultStabilizer
from qrtc.guards import GuardRule
from qrtc.key import TransitKey
from qrtc.policy import TransitPolicy
from qrtc.transit import AuthorizationDecision, TransitEnvelope

# Recognized CARLA run completion statuses accepted by the schema guard.
_CARLA_RECOGNIZED_STATUSES = frozenset({"completed", "failed", "aborted", "partial"})


class PolicyResolutionError(ValueError):
    pass


KeyPolicyFactory = Callable[[TransitPolicy, TransitInputRecord], TransitKey]
GateFactory = Callable[
    [TransitPolicy, TransitInputRecord], Callable[[Any, Any], TransitEnvelope]
]


@dataclass(frozen=True)
class ComponentMetadata:
    component_id: str
    component_kind: str
    version: str
    deterministic: bool = True
    replayable: bool = True


@dataclass(frozen=True)
class FrozenComponentRegistry:
    gates: Mapping[str, Callable[[Any, Any], TransitEnvelope]]
    guards: Mapping[str, GuardRule]
    boats: Mapping[str, BoatCodec]
    key_policies: Mapping[str, KeyPolicyFactory]
    realizers: Mapping[str, DefaultRealizer]
    stabilizers: Mapping[str, DefaultStabilizer]
    metadata: Mapping[str, ComponentMetadata]

    def resolve_key_policy(self, component_id: str) -> KeyPolicyFactory:
        return _resolve(self.key_policies, component_id, "key policy")

    def resolve_gate(self, component_id: str) -> Callable[[Any, Any], TransitEnvelope]:
        return _resolve(self.gates, component_id, "gate")

    def resolve_guard(self, component_id: str) -> GuardRule:
        return _resolve(self.guards, component_id, "guard")

    def resolve_boat(self, component_id: str) -> BoatCodec:
        return _resolve(self.boats, component_id, "boat")

    def resolve_realizer(self, component_id: str) -> DefaultRealizer:
        return _resolve(self.realizers, component_id, "realizer")

    def resolve_stabilizer(self, component_id: str) -> DefaultStabilizer:
        return _resolve(self.stabilizers, component_id, "stabilizer")


def _resolve(mapping: Mapping[str, Any], component_id: str, kind: str) -> Any:
    try:
        return mapping[component_id]
    except KeyError as error:
        raise PolicyResolutionError(f"unknown {kind}: {component_id}") from error


@dataclass
class ComponentRegistry:
    gates: dict[str, Callable[[Any, Any], TransitEnvelope]] = field(
        default_factory=dict
    )
    guards: dict[str, GuardRule] = field(default_factory=dict)
    boats: dict[str, BoatCodec] = field(default_factory=dict)
    key_policies: dict[str, KeyPolicyFactory] = field(default_factory=dict)
    realizers: dict[str, DefaultRealizer] = field(default_factory=dict)
    stabilizers: dict[str, DefaultStabilizer] = field(default_factory=dict)
    _metadata: dict[str, ComponentMetadata] = field(default_factory=dict)

    def register_gate(
        self,
        component_id: str,
        gate: Callable[[Any, Any], TransitEnvelope],
        *,
        version: str = "v1",
        deterministic: bool = True,
    ) -> None:
        self._register(self.gates, component_id, gate, "gate", version, deterministic)

    def register_guard(
        self,
        component_id: str,
        guard: GuardRule,
        *,
        version: str = "v1",
        deterministic: bool = True,
    ) -> None:
        self._register(
            self.guards, component_id, guard, "guard", version, deterministic
        )

    def register_boat(
        self,
        component_id: str,
        boat: BoatCodec,
        *,
        version: str = "v1",
        deterministic: bool = True,
    ) -> None:
        self._register(self.boats, component_id, boat, "boat", version, deterministic)

    def register_key_policy(
        self,
        component_id: str,
        key_policy: KeyPolicyFactory,
        *,
        version: str = "v1",
        deterministic: bool = True,
    ) -> None:
        self._register(
            self.key_policies,
            component_id,
            key_policy,
            "key_policy",
            version,
            deterministic,
        )

    def register_realizer(
        self,
        component_id: str,
        realizer: DefaultRealizer,
        *,
        version: str = "v1",
        deterministic: bool = True,
    ) -> None:
        self._register(
            self.realizers, component_id, realizer, "realizer", version, deterministic
        )

    def register_stabilizer(
        self,
        component_id: str,
        stabilizer: DefaultStabilizer,
        *,
        version: str = "v1",
        deterministic: bool = True,
    ) -> None:
        self._register(
            self.stabilizers,
            component_id,
            stabilizer,
            "stabilizer",
            version,
            deterministic,
        )

    def _register(
        self,
        mapping: dict[str, Any],
        component_id: str,
        component: Any,
        kind: str,
        version: str,
        deterministic: bool,
    ) -> None:
        if component_id in self._metadata:
            raise ValueError(f"duplicate component identifier: {component_id}")

        mapping[component_id] = component
        self._metadata[component_id] = ComponentMetadata(
            component_id=component_id,
            component_kind=kind,
            version=version,
            deterministic=deterministic,
            replayable=deterministic,
        )

    def freeze(self) -> FrozenComponentRegistry:
        return FrozenComponentRegistry(
            gates=MappingProxyType(dict(self.gates)),
            guards=MappingProxyType(dict(self.guards)),
            boats=MappingProxyType(dict(self.boats)),
            key_policies=MappingProxyType(dict(self.key_policies)),
            realizers=MappingProxyType(dict(self.realizers)),
            stabilizers=MappingProxyType(dict(self.stabilizers)),
            metadata=MappingProxyType(dict(self._metadata)),
        )


def _carla_schema_guard(envelope: TransitEnvelope) -> bool:
    """
    Accept a CARLA interface projection when:
    - ``status`` is a recognized string
    - ``ticks_requested`` is a positive integer
    - ``ticks_completed == ticks_requested`` for a completed run
    - ``collision_count`` and ``missing_data_count`` are nonnegative integers
    """
    iface = envelope.interface
    status = iface.get("status")
    if not isinstance(status, str) or status not in _CARLA_RECOGNIZED_STATUSES:
        return False

    ticks_requested = iface.get("ticks_requested")
    if not (type(ticks_requested) is int) or ticks_requested <= 0:
        return False

    ticks_completed = iface.get("ticks_completed")
    if not (type(ticks_completed) is int) or ticks_completed < 0:
        return False

    if status == "completed" and ticks_completed != ticks_requested:
        return False

    collision_count = iface.get("collision_count")
    if not (type(collision_count) is int) or collision_count < 0:
        return False

    missing_data_count = iface.get("missing_data_count")
    if not (type(missing_data_count) is int) or missing_data_count < 0:
        return False

    return True


def _carla_health_guard(envelope: TransitEnvelope) -> bool:
    """
    Accept a CARLA interface projection when:
    - ``displacement_m`` is a finite, nonnegative number
    - ``mean_speed_mps`` and ``max_speed_mps`` are finite, nonnegative or None
    - If lidar is enabled:
      - ``lidar_frames_received`` is a positive integer
      - ``ticks_completed`` is a positive integer
      - ``lidar_frames_received`` equals ``ticks_completed``
      - ``lidar_frames_dropped`` is integer zero
      - ``lidar_callback_errors`` is integer zero
      - any reported nearest ranges are finite and nonnegative
    - No NaN or infinite values for the numeric fields
    """
    iface = envelope.interface

    def _finite_nonneg(v: Any) -> bool:
        return isinstance(v, (int, float)) and math.isfinite(v) and v >= 0.0

    def _finite_nonneg_or_none(v: Any) -> bool:
        return v is None or _finite_nonneg(v)

    displacement_m = iface.get("displacement_m")
    if not _finite_nonneg(displacement_m):
        return False

    if not _finite_nonneg_or_none(iface.get("mean_speed_mps")):
        return False
    if not _finite_nonneg_or_none(iface.get("max_speed_mps")):
        return False

    lidar_enabled = iface.get("lidar_enabled")
    if lidar_enabled:
        lidar_frames = iface.get("lidar_frames_received")
        if not (type(lidar_frames) is int) or lidar_frames <= 0:
            return False

        ticks_completed = iface.get("ticks_completed")
        if not (type(ticks_completed) is int) or ticks_completed <= 0:
            return False

        if lidar_frames != ticks_completed:
            return False

        lidar_dropped = iface.get("lidar_frames_dropped")
        if not (type(lidar_dropped) is int) or lidar_dropped != 0:
            return False

        lidar_cb_errors = iface.get("lidar_callback_errors")
        if not (type(lidar_cb_errors) is int) or lidar_cb_errors != 0:
            return False

        # Validate optional natural/injected drop counters when present.
        lidar_natural_dropped = iface.get("lidar_frames_natural_dropped")
        if lidar_natural_dropped is not None:
            if not (type(lidar_natural_dropped) is int) or lidar_natural_dropped != 0:
                return False

        lidar_injected_dropped = iface.get("lidar_frames_injected_dropped")
        if lidar_injected_dropped is not None:
            if not (type(lidar_injected_dropped) is int) or lidar_injected_dropped != 0:
                return False

        if not _finite_nonneg_or_none(iface.get("lidar_nearest_obstacle_m")):
            return False
        if not _finite_nonneg_or_none(iface.get("lidar_nearest_front_m")):
            return False

    return True


def build_default_registry(*, carla_principal: str | None = None) -> FrozenComponentRegistry:
    """
    Build the default component registry.

    ``carla_principal`` sets the principal that the CARLA key policy authorises.
    When *None* the value is taken from the ``CARLA_PRINCIPAL`` environment
    variable, defaulting to ``"carla-operator"``.  The equipment telemetry
    components are registered unchanged alongside the new CARLA components.
    """
    builder = ComponentRegistry()

    # ------------------------------------------------------------------
    # Equipment telemetry components (unchanged)
    # ------------------------------------------------------------------

    def key_policy(
        policy: TransitPolicy, input_record: TransitInputRecord
    ) -> TransitKey:
        return TransitKey(
            key_id=policy.key_policy,
            principal="authorized-operator",
            predecessor_class=policy.predecessor_class,
            declared_future=policy.future_family,
            destination=input_record.destination,
            expiration=input_record.expiration,
            policy_version=policy.policy_version,
        )

    def telemetry_gate(
        request: Any, authorization: AuthorizationDecision
    ) -> TransitEnvelope:
        return TransitEnvelope(
            transit_id=request.transit_id,
            principal=request.principal,
            predecessor_class=request.predecessor_class,
            declared_future=request.declared_future,
            destination=request.destination,
            policy_version=request.policy_version,
            route_version=request.route_version,
            schema_version=request.schema_version,
            encoding_version=request.encoding_version,
            authorization=authorization,
            interface=request.interface,
        )

    def schema_guard(envelope: TransitEnvelope) -> bool:
        return "temperature" in envelope.interface and "pressure" in envelope.interface

    def ranges_guard(envelope: TransitEnvelope) -> bool:
        temperature = envelope.interface.get("temperature")
        pressure = envelope.interface.get("pressure")
        return (
            isinstance(temperature, (int, float))
            and isinstance(pressure, (int, float))
            and 0 <= pressure <= 200
            and -50 <= temperature <= 200
        )

    builder.register_key_policy("telemetry-key-v1", key_policy, version="1.0.0")
    builder.register_gate("telemetry-gate-v1", telemetry_gate, version="1.0.0")
    builder.register_guard(
        "telemetry-schema-v1",
        GuardRule(
            guard_id="telemetry-schema-v1",
            policy_version="1.0.0",
            predicate=schema_guard,
            pass_reason="schema accepted",
            fail_reason="schema rejected",
        ),
        version="1.0.0",
    )
    builder.register_guard(
        "telemetry-ranges-v1",
        GuardRule(
            guard_id="telemetry-ranges-v1",
            policy_version="1.0.0",
            predicate=ranges_guard,
            pass_reason="ranges accepted",
            fail_reason="ranges rejected",
        ),
        version="1.0.0",
    )
    builder.register_boat(
        "canonical-json-v1",
        BoatCodec(
            schema_version="telemetry-interface-v1",
            encoding_version="canonical-json-v1",
        ),
        version="1.0.0",
    )
    builder.register_realizer(
        "alarm-record-v1",
        DefaultRealizer(
            destination="alarm-record",
            policy_version="1.0.0",
            route_version="operations-route-v1",
        ),
        version="1.0.0",
    )
    builder.register_stabilizer(
        "alarm-persistence-v1",
        DefaultStabilizer(
            stabilizer_id="alarm-persistence-v1",
            policy_version="1.0.0",
            route_version="operations-route-v1",
        ),
        version="1.0.0",
    )

    # ------------------------------------------------------------------
    # CARLA drive telemetry components
    # ------------------------------------------------------------------

    # The CARLA key authorises the principal carried by the CARLA run
    # configuration.  By construction, ``carla_config_from_env()`` reads
    # CARLA_PRINCIPAL and sets it on both the run report *and* the
    # projection, so the key and the input always use the same value when
    # the pipeline is invoked through the normal harness path.
    _carla_principal: str = carla_principal or os.environ.get(
        "CARLA_PRINCIPAL", "carla-operator"
    )

    def carla_key_policy(
        policy: TransitPolicy, input_record: TransitInputRecord
    ) -> TransitKey:
        return TransitKey(
            key_id=policy.key_policy,
            principal=_carla_principal,
            predecessor_class=policy.predecessor_class,
            declared_future=policy.future_family,
            destination=input_record.destination,
            expiration=input_record.expiration,
            policy_version=policy.policy_version,
        )

    def carla_gate(
        request: Any, authorization: AuthorizationDecision
    ) -> TransitEnvelope:
        return TransitEnvelope(
            transit_id=request.transit_id,
            principal=request.principal,
            predecessor_class=request.predecessor_class,
            declared_future=request.declared_future,
            destination=request.destination,
            policy_version=request.policy_version,
            route_version=request.route_version,
            schema_version=request.schema_version,
            encoding_version=request.encoding_version,
            authorization=authorization,
            interface=request.interface,
        )

    builder.register_key_policy("carla-key-v1", carla_key_policy, version="1.0.0")
    builder.register_gate("carla-gate-v1", carla_gate, version="1.0.0")
    builder.register_guard(
        "carla-schema-v1",
        GuardRule(
            guard_id="carla-schema-v1",
            policy_version="1.0.0",
            predicate=_carla_schema_guard,
            pass_reason="CARLA schema accepted",
            fail_reason=(
                "CARLA schema rejected: missing or invalid status, ticks, "
                "collision_count, or missing_data_count"
            ),
        ),
        version="1.0.0",
    )
    builder.register_guard(
        "carla-health-v1",
        GuardRule(
            guard_id="carla-health-v1",
            policy_version="1.0.0",
            predicate=_carla_health_guard,
            pass_reason="CARLA health accepted",
            fail_reason=(
                "CARLA health rejected: non-finite/negative displacement or speed, "
                "or lidar health failure (frame count mismatch, dropped frames, "
                "callback errors, or invalid range) when lidar is enabled"
            ),
        ),
        version="1.0.0",
    )
    builder.register_boat(
        "carla-json-v1",
        BoatCodec(
            schema_version="carla-interface-v1",
            encoding_version="carla-json-v1",
        ),
        version="1.0.0",
    )
    builder.register_realizer(
        "carla-drive-record-v1",
        DefaultRealizer(
            destination="carla-drive-record",
            policy_version="1.0.0",
            route_version="carla-drive-route-v1",
        ),
        version="1.0.0",
    )
    builder.register_stabilizer(
        "carla-persistence-v1",
        DefaultStabilizer(
            stabilizer_id="carla-persistence-v1",
            policy_version="1.0.0",
            route_version="carla-drive-route-v1",
        ),
        version="1.0.0",
    )

    return builder.freeze()
