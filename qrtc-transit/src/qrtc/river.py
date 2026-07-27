from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

from qrtc.limits import DEFAULT_LIMITS
from qrtc.transit import DeliveryStatus, TransitEnvelope


@dataclass(frozen=True)
class RiverSendReceipt:
    route_id: str
    transit_id: str
    sequence_number: int
    sent_at: datetime
    payload_digest: str
    delivery_status: DeliveryStatus = DeliveryStatus.SENT


@dataclass(frozen=True)
class RiverReceiveReceipt:
    route_id: str
    transit_id: str
    sequence_number: int
    sent_at: datetime
    received_at: datetime
    payload_digest: str
    envelope: TransitEnvelope
    delivery_status: DeliveryStatus = DeliveryStatus.DELIVERED


@dataclass
class SimulatedDirectedRiver:
    route_id: str
    sender_id: str
    receiver_id: str
    max_queue_size: int = DEFAULT_LIMITS.max_river_queue_size
    _queue: deque[tuple[int, TransitEnvelope, datetime]] = field(default_factory=deque)
    _next_sequence_number: int = 1

    def sender(self) -> RiverSender:
        return RiverSender(self)

    def receiver(self) -> RiverReceiver:
        return RiverReceiver(self)


@dataclass(frozen=True)
class RiverSender:
    river: SimulatedDirectedRiver

    def send(self, envelope: TransitEnvelope) -> RiverSendReceipt:
        if envelope.payload_bytes is None or envelope.payload_digest is None:
            raise ValueError("envelope must be encoded before sending")
        if len(self.river._queue) >= self.river.max_queue_size:
            raise ValueError("river queue limit reached")

        sent_at = datetime.now(UTC)
        sequence_number = self.river._next_sequence_number
        self.river._next_sequence_number += 1
        self.river._queue.append((sequence_number, envelope, sent_at))

        return RiverSendReceipt(
            route_id=self.river.route_id,
            transit_id=envelope.transit_id,
            sequence_number=sequence_number,
            sent_at=sent_at,
            payload_digest=envelope.payload_digest,
        )


@dataclass(frozen=True)
class RiverReceiver:
    river: SimulatedDirectedRiver

    def receive(self) -> RiverReceiveReceipt:
        if not self.river._queue:
            raise LookupError("no delivered envelope available")

        sequence_number, envelope, sent_at = self.river._queue.popleft()
        received_at = datetime.now(UTC)

        return RiverReceiveReceipt(
            route_id=self.river.route_id,
            transit_id=envelope.transit_id,
            sequence_number=sequence_number,
            sent_at=sent_at,
            received_at=received_at,
            payload_digest=envelope.payload_digest or "",
            envelope=envelope,
        )
