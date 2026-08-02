"""
CARLA live-drive harness — environment configuration.

All CARLA imports are lazy so ordinary installs and CI remain unaffected.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default).strip() or default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name}={raw!r} is not a valid integer") from exc
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name}={raw!r} is not a valid float") from exc
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"Environment variable {name}={raw!r} is not a valid boolean")


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LidarConfig:
    """Conservative lidar defaults suitable for low-resource live testing."""
    enabled: bool = True
    channels: int = 16
    range_m: float = 30.0
    points_per_second: int = 56_000
    rotation_frequency: float = 10.0
    upper_fov: float = 10.0
    lower_fov: float = -30.0
    # Raw point-cloud retention: disabled by default, bounded when enabled.
    retain_raw: bool = False
    max_raw_frames: int = 10
    # TEST-ONLY fault injection: zero-based callback index to intentionally
    # drop.  -1 (default) disables fault injection entirely.  Set via
    # CARLA_LIDAR_DROP_FRAME_INDEX to test fail-safe behaviour without
    # altering any preserved baseline evidence.
    drop_frame_index: int = -1

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "channels": self.channels,
            "range_m": self.range_m,
            "points_per_second": self.points_per_second,
            "rotation_frequency": self.rotation_frequency,
            "upper_fov": self.upper_fov,
            "lower_fov": self.lower_fov,
            "retain_raw": self.retain_raw,
            "max_raw_frames": self.max_raw_frames,
            "drop_frame_index": self.drop_frame_index,
        }


@dataclass(frozen=True)
class CarlaConfig:
    host: str = "127.0.0.1"
    port: int = 2000
    tm_port: int = 8000
    timeout: float = 15.0
    ticks: int = 300
    spawn_point: int = 0
    output: str = "carla-live-drive-result.json"
    fixed_delta: float = 0.05
    preferred_blueprint: str = "vehicle.tesla.model3"
    # QRTC submission
    principal: str = "carla-operator"
    destination: str = "carla-drive-record"
    submit_to_qrtc: bool = False
    qrtc_db: str = "qrtc_evidence.sqlite3"
    lidar: LidarConfig = field(default_factory=LidarConfig)
    # Opt-in runtime protection (disabled by default)
    runtime_protection_enabled: bool = False
    runtime_stop_speed_mps: float = 0.10
    runtime_required_stopped_ticks: int = 5
    runtime_maximum_braking_ticks: int = 100

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "tm_port": self.tm_port,
            "timeout": self.timeout,
            "ticks": self.ticks,
            "spawn_point": self.spawn_point,
            "output": self.output,
            "fixed_delta": self.fixed_delta,
            "preferred_blueprint": self.preferred_blueprint,
            "principal": self.principal,
            "destination": self.destination,
            "submit_to_qrtc": self.submit_to_qrtc,
            "qrtc_db": self.qrtc_db,
            "lidar": self.lidar.as_dict(),
            "runtime_protection_enabled": self.runtime_protection_enabled,
            "runtime_stop_speed_mps": self.runtime_stop_speed_mps,
            "runtime_required_stopped_ticks": self.runtime_required_stopped_ticks,
            "runtime_maximum_braking_ticks": self.runtime_maximum_braking_ticks,
        }


# ---------------------------------------------------------------------------
# Factory from environment
# ---------------------------------------------------------------------------

def lidar_config_from_env() -> LidarConfig:
    return LidarConfig(
        enabled=_env_bool("CARLA_LIDAR_ENABLED", True),
        channels=_env_int("CARLA_LIDAR_CHANNELS", 16),
        range_m=_env_float("CARLA_LIDAR_RANGE", 30.0),
        points_per_second=_env_int("CARLA_LIDAR_POINTS_PER_SECOND", 56_000),
        rotation_frequency=_env_float("CARLA_LIDAR_ROTATION_FREQUENCY", 10.0),
        upper_fov=_env_float("CARLA_LIDAR_UPPER_FOV", 10.0),
        lower_fov=_env_float("CARLA_LIDAR_LOWER_FOV", -30.0),
        retain_raw=_env_bool("CARLA_LIDAR_RETAIN_RAW", False),
        max_raw_frames=_env_int("CARLA_LIDAR_MAX_RAW_FRAMES", 10),
        drop_frame_index=_env_int("CARLA_LIDAR_DROP_FRAME_INDEX", -1),
    )


def carla_config_from_env() -> CarlaConfig:
    return CarlaConfig(
        host=_env_str("CARLA_HOST", "127.0.0.1"),
        port=_env_int("CARLA_PORT", 2000),
        tm_port=_env_int("CARLA_TM_PORT", 8000),
        timeout=_env_float("CARLA_TIMEOUT", 15.0),
        ticks=_env_int("CARLA_TICKS", 300),
        spawn_point=_env_int("CARLA_SPAWN_POINT", 0),
        output=_env_str("CARLA_OUTPUT", "carla-live-drive-result.json"),
        fixed_delta=_env_float("CARLA_FIXED_DELTA", 0.05),
        preferred_blueprint=_env_str("CARLA_BLUEPRINT", "vehicle.tesla.model3"),
        principal=_env_str("CARLA_PRINCIPAL", "carla-operator"),
        destination=_env_str("CARLA_DESTINATION", "carla-drive-record"),
        submit_to_qrtc=_env_bool("CARLA_SUBMIT_QRTC", False),
        qrtc_db=_env_str("CARLA_QRTC_DB", "qrtc_evidence.sqlite3"),
        lidar=lidar_config_from_env(),
        runtime_protection_enabled=_env_bool(
            "CARLA_RUNTIME_PROTECTION_ENABLED", False
        ),
        runtime_stop_speed_mps=_env_float("CARLA_RUNTIME_STOP_SPEED_MPS", 0.10),
        runtime_required_stopped_ticks=_env_int("CARLA_RUNTIME_STOPPED_TICKS", 5),
        runtime_maximum_braking_ticks=_env_int("CARLA_RUNTIME_MAX_BRAKING_TICKS", 100),
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_carla_config(cfg: CarlaConfig) -> list[str]:
    """Return a list of validation error messages (empty means valid)."""
    errors: list[str] = []
    if cfg.port <= 0 or cfg.port > 65535:
        errors.append(f"port must be 1–65535, got {cfg.port}")
    if cfg.tm_port <= 0 or cfg.tm_port > 65535:
        errors.append(f"tm_port must be 1–65535, got {cfg.tm_port}")
    if cfg.timeout <= 0:
        errors.append(f"timeout must be positive, got {cfg.timeout}")
    if cfg.ticks <= 0:
        errors.append(f"ticks must be positive, got {cfg.ticks}")
    if cfg.spawn_point < 0:
        errors.append(f"spawn_point must be non-negative, got {cfg.spawn_point}")
    if not (0.001 <= cfg.fixed_delta <= 0.5):
        errors.append(f"fixed_delta must be 0.001–0.5, got {cfg.fixed_delta}")
    if not cfg.output:
        errors.append("output path must not be empty")
    lidar = cfg.lidar
    if lidar.channels < 1:
        errors.append(f"lidar channels must be >= 1, got {lidar.channels}")
    if lidar.range_m <= 0:
        errors.append(f"lidar range_m must be positive, got {lidar.range_m}")
    if lidar.points_per_second < 1:
        errors.append(f"lidar points_per_second must be >= 1, got {lidar.points_per_second}")
    if lidar.rotation_frequency <= 0:
        errors.append(f"lidar rotation_frequency must be positive, got {lidar.rotation_frequency}")
    if lidar.upper_fov <= lidar.lower_fov:
        errors.append(
            f"lidar upper_fov ({lidar.upper_fov}) must be > lower_fov ({lidar.lower_fov})"
        )
    if lidar.drop_frame_index < -1:
        errors.append(
            f"lidar drop_frame_index must be -1 (disabled) or nonnegative, "
            f"got {lidar.drop_frame_index}"
        )
    if cfg.runtime_stop_speed_mps < 0.0:
        errors.append(
            f"runtime_stop_speed_mps must be >= 0, got {cfg.runtime_stop_speed_mps}"
        )
    if cfg.runtime_required_stopped_ticks < 1:
        errors.append(
            f"runtime_required_stopped_ticks must be >= 1, "
            f"got {cfg.runtime_required_stopped_ticks}"
        )
    if cfg.runtime_maximum_braking_ticks < 1:
        errors.append(
            f"runtime_maximum_braking_ticks must be >= 1, "
            f"got {cfg.runtime_maximum_braking_ticks}"
        )
    return errors
