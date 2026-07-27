from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from qrtc.transit import TransitEnvelope


@dataclass(frozen=True)
class BoatCodec:
    schema_version: str
    encoding_version: str

    def encode(self, envelope: TransitEnvelope) -> TransitEnvelope:
        payload_bytes = canonicalize_interface(
            envelope.interface,
            schema_version=self.schema_version,
            encoding_version=self.encoding_version,
        )
        return envelope.with_payload(
            payload_bytes=payload_bytes,
            payload_digest=envelope_digest(payload_bytes),
        )


def canonicalize_interface(
    interface: Mapping[str, Any],
    *,
    schema_version: str,
    encoding_version: str,
) -> bytes:
    payload = {
        "schema_version": schema_version,
        "encoding_version": encoding_version,
        "interface": dict(interface),
    }

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def envelope_digest(payload_bytes: bytes) -> str:
    return hashlib.sha256(payload_bytes).hexdigest()
