import math

import pytest

from qrtc.boat import BoatCodec, canonicalize_interface, envelope_digest
from qrtc.transit import AuthorizationDecision, TransitEnvelope


def test_canonical_bytes_are_deterministic() -> None:
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}

    left_bytes = canonicalize_interface(
        left,
        schema_version="schema-v1",
        encoding_version="json-v1",
    )
    right_bytes = canonicalize_interface(
        right,
        schema_version="schema-v1",
        encoding_version="json-v1",
    )

    assert left_bytes == right_bytes
    assert envelope_digest(left_bytes) == envelope_digest(right_bytes)


def test_non_finite_json_values_are_rejected() -> None:
    with pytest.raises(ValueError):
        canonicalize_interface(
            {"temperature": math.nan},
            schema_version="schema-v1",
            encoding_version="json-v1",
        )


def test_codec_attaches_digest_to_envelope() -> None:
    envelope = TransitEnvelope(
        transit_id="t-1",
        principal="alice",
        predecessor_class="equipment",
        declared_future="telemetry-payload",
        destination="archive",
        policy_version="policy-v1",
        route_version="route-v1",
        schema_version="schema-v1",
        encoding_version="json-v1",
        authorization=AuthorizationDecision(
            qualified=True,
            key_id="demo-key",
            policy_version="policy-v1",
            reason="matched",
            principal="alice",
        ),
        interface={"temperature": 64},
    )

    codec = BoatCodec(schema_version="schema-v1", encoding_version="json-v1")
    encoded = codec.encode(envelope)

    assert encoded.payload_bytes is not None
    assert encoded.payload_digest is not None
    assert encoded.payload_digest == envelope_digest(encoded.payload_bytes)
