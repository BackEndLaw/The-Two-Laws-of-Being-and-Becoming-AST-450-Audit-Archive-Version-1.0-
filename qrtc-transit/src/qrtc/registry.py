from __future__ import annotations

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


def build_default_registry() -> FrozenComponentRegistry:
    builder = ComponentRegistry()

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

    return builder.freeze()
