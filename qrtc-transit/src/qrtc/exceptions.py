from __future__ import annotations


class QRTCError(Exception):
    """Base class for expected QRTC product failures."""


class PolicyError(QRTCError):
    pass


class AuthorizationError(QRTCError):
    pass


class GuardError(QRTCError):
    pass


class EncodingError(QRTCError):
    pass


class DeliveryError(QRTCError):
    pass


class DeliveryUncertainError(DeliveryError):
    pass


class IntegrityError(QRTCError):
    pass


class RealizationError(QRTCError):
    pass


class StabilizationError(QRTCError):
    pass


class EvidenceError(QRTCError):
    pass


class ResourceLimitError(QRTCError):
    pass


class IdempotencyConflictError(QRTCError):
    pass


class RecoveryError(QRTCError):
    pass
