from qrtc.boat import BoatCodec
from qrtc.river import SimulatedDirectedRiver
from qrtc.transit import AuthorizationDecision, TransitEnvelope


def _encoded_envelope() -> TransitEnvelope:
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
        interface={"sequence": 1},
    )
    return BoatCodec(schema_version="schema-v1", encoding_version="json-v1").encode(
        envelope
    )


def test_river_is_fifo_and_directional() -> None:
    river = SimulatedDirectedRiver(
        route_id="route-v1",
        sender_id="sender-v1",
        receiver_id="receiver-v1",
    )
    sender = river.sender()
    receiver = river.receiver()

    first = _encoded_envelope()
    second = first.with_payload(first.payload_bytes or b"", first.payload_digest or "")

    first_receipt = sender.send(first)
    second_receipt = sender.send(second)
    first_received = receiver.receive()
    second_received = receiver.receive()

    assert first_receipt.sequence_number == 1
    assert second_receipt.sequence_number == 2
    assert first_received.sequence_number == 1
    assert second_received.sequence_number == 2
    assert hasattr(sender, "send")
    assert not hasattr(sender, "receive")
    assert hasattr(receiver, "receive")
    assert not hasattr(receiver, "send")
