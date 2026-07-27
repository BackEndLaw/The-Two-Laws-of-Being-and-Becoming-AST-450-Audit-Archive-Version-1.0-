from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from qrtc.transit import AuthorizationDecision, TransitRequest


@dataclass(frozen=True)
class TransitKey:
    key_id: str
    principal: str
    predecessor_class: str
    declared_future: str
    destination: str
    expiration: datetime
    policy_version: str

    def authorize(
        self,
        request: TransitRequest,
        *,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        current_time = now or datetime.now(UTC)

        matches = (
            request.principal == self.principal
            and request.predecessor_class == self.predecessor_class
            and request.declared_future == self.declared_future
            and request.destination == self.destination
            and request.policy_version == self.policy_version
            and current_time <= self.expiration
        )

        if matches:
            reason = (
                "identity, class, future, destination, expiration, and policy matched"
            )
        else:
            reason = "authorization constraints failed"

        return AuthorizationDecision(
            qualified=matches,
            key_id=self.key_id,
            policy_version=self.policy_version,
            reason=reason,
            principal=request.principal,
        )


def authorize_transit(
    request: TransitRequest,
    key: TransitKey,
    *,
    now: datetime | None = None,
) -> AuthorizationDecision:
    return key.authorize(request, now=now)
