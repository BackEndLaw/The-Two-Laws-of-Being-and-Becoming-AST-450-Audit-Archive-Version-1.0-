from __future__ import annotations

from qrtc.river import SimulatedDirectedRiver
from qrtc.transit import AuthorizationDecision, TransitEnvelope


def test_river_queue_limit_prevents_unbounded_growth() -> None:
    river = SimulatedDirectedRiver(
        route_id="r-1",
        sender_id="s",
        receiver_id="r",
        max_queue_size=1,
    )
    sender = river.sender()
    envelope = TransitEnvelope(
        transit_id="t-1",
        principal="authorized-operator",
        predecessor_class="equipment",
        declared_future="f",
        destination="archive",
        policy_version="1",
        route_version="1",
        schema_version="1",
        encoding_version="1",
        authorization=AuthorizationDecision(
            qualified=True,
            key_id="k",
            policy_version="1",
            reason="ok",
            principal="authorized-operator",
        ),
        interface={"x": 1},
        payload_bytes=b"{}",
        payload_digest="abc",
    )

    sender.send(envelope)
    failed = False
    try:
        sender.send(envelope)
    except ValueError:
        failed = True

    assert failed
