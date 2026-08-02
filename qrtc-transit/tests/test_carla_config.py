"""Unit tests for qrtc.carla_config — env parsing and validation."""
from __future__ import annotations

import os

import pytest

from qrtc.carla_config import (
    CarlaConfig,
    LidarConfig,
    carla_config_from_env,
    lidar_config_from_env,
    validate_carla_config,
)


# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------

def test_default_carla_config_has_expected_values() -> None:
    cfg = CarlaConfig()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 2000
    assert cfg.tm_port == 8000
    assert cfg.timeout == 15.0
    assert cfg.ticks == 300
    assert cfg.spawn_point == 0
    assert cfg.output == "carla-live-drive-result.json"
    assert cfg.fixed_delta == 0.05
    assert cfg.preferred_blueprint == "vehicle.tesla.model3"
    assert cfg.submit_to_qrtc is False


def test_default_lidar_config_is_conservative() -> None:
    lidar = LidarConfig()
    assert lidar.enabled is True
    assert lidar.channels == 16
    assert lidar.range_m == 30.0
    assert lidar.points_per_second == 56_000
    assert lidar.rotation_frequency == 10.0
    assert lidar.upper_fov == 10.0
    assert lidar.lower_fov == -30.0
    assert lidar.retain_raw is False
    assert lidar.max_raw_frames == 10


# ---------------------------------------------------------------------------
# Environment variable parsing
# ---------------------------------------------------------------------------

def test_carla_config_from_env_reads_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_HOST", "192.168.1.5")
    cfg = carla_config_from_env()
    assert cfg.host == "192.168.1.5"


def test_carla_config_from_env_reads_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_PORT", "3000")
    monkeypatch.setenv("CARLA_TM_PORT", "9000")
    cfg = carla_config_from_env()
    assert cfg.port == 3000
    assert cfg.tm_port == 9000


def test_carla_config_from_env_reads_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_TICKS", "100")
    cfg = carla_config_from_env()
    assert cfg.ticks == 100


def test_carla_config_from_env_reads_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_OUTPUT", "my-drive.json")
    cfg = carla_config_from_env()
    assert cfg.output == "my-drive.json"


def test_carla_config_from_env_reads_fixed_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_FIXED_DELTA", "0.033")
    cfg = carla_config_from_env()
    assert abs(cfg.fixed_delta - 0.033) < 1e-9


def test_lidar_config_from_env_reads_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_LIDAR_CHANNELS", "32")
    lidar = lidar_config_from_env()
    assert lidar.channels == 32


def test_lidar_config_from_env_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_LIDAR_ENABLED", "false")
    lidar = lidar_config_from_env()
    assert lidar.enabled is False


def test_lidar_config_from_env_enabled_variations(monkeypatch: pytest.MonkeyPatch) -> None:
    for val in ("1", "true", "yes", "on", "True", "YES"):
        monkeypatch.setenv("CARLA_LIDAR_ENABLED", val)
        assert lidar_config_from_env().enabled is True


def test_lidar_config_from_env_disabled_variations(monkeypatch: pytest.MonkeyPatch) -> None:
    for val in ("0", "false", "no", "off", "False", "NO"):
        monkeypatch.setenv("CARLA_LIDAR_ENABLED", val)
        assert lidar_config_from_env().enabled is False


def test_env_bool_invalid_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_LIDAR_ENABLED", "maybe")
    with pytest.raises(ValueError, match="CARLA_LIDAR_ENABLED"):
        lidar_config_from_env()


def test_env_int_invalid_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_PORT", "not-a-number")
    with pytest.raises(ValueError, match="CARLA_PORT"):
        carla_config_from_env()


def test_env_float_invalid_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_TIMEOUT", "fast")
    with pytest.raises(ValueError, match="CARLA_TIMEOUT"):
        carla_config_from_env()


def test_submit_to_qrtc_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CARLA_SUBMIT_QRTC", raising=False)
    cfg = carla_config_from_env()
    assert cfg.submit_to_qrtc is False


def test_submit_to_qrtc_can_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_SUBMIT_QRTC", "true")
    cfg = carla_config_from_env()
    assert cfg.submit_to_qrtc is True


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_valid_default_config_passes_validation() -> None:
    assert validate_carla_config(CarlaConfig()) == []


def test_invalid_port_fails_validation() -> None:
    errors = validate_carla_config(CarlaConfig(port=0))
    assert any("port" in e for e in errors)


def test_invalid_ticks_fails_validation() -> None:
    errors = validate_carla_config(CarlaConfig(ticks=0))
    assert any("ticks" in e for e in errors)


def test_invalid_timeout_fails_validation() -> None:
    errors = validate_carla_config(CarlaConfig(timeout=-1.0))
    assert any("timeout" in e for e in errors)


def test_invalid_fixed_delta_fails_validation() -> None:
    errors = validate_carla_config(CarlaConfig(fixed_delta=0.0))
    assert any("fixed_delta" in e for e in errors)

    errors = validate_carla_config(CarlaConfig(fixed_delta=1.0))
    assert any("fixed_delta" in e for e in errors)


def test_invalid_spawn_point_fails_validation() -> None:
    errors = validate_carla_config(CarlaConfig(spawn_point=-1))
    assert any("spawn_point" in e for e in errors)


def test_invalid_lidar_fov_fails_validation() -> None:
    lidar = LidarConfig(upper_fov=-10.0, lower_fov=5.0)
    errors = validate_carla_config(CarlaConfig(lidar=lidar))
    assert any("upper_fov" in e or "lower_fov" in e for e in errors)


def test_config_as_dict_is_complete() -> None:
    cfg = CarlaConfig()
    d = cfg.as_dict()
    for key in (
        "host", "port", "tm_port", "timeout", "ticks",
        "spawn_point", "output", "fixed_delta", "preferred_blueprint",
        "principal", "destination", "submit_to_qrtc", "qrtc_db", "lidar",
    ):
        assert key in d, f"missing key: {key}"


def test_lidar_as_dict_is_complete() -> None:
    lidar = LidarConfig()
    d = lidar.as_dict()
    for key in (
        "enabled", "channels", "range_m", "points_per_second",
        "rotation_frequency", "upper_fov", "lower_fov",
        "retain_raw", "max_raw_frames", "drop_frame_index",
    ):
        assert key in d, f"missing key: {key}"


# ---------------------------------------------------------------------------
# drop_frame_index — default, env parsing, and validation
# ---------------------------------------------------------------------------

def test_default_lidar_drop_frame_index_is_disabled() -> None:
    lidar = LidarConfig()
    assert lidar.drop_frame_index == -1


def test_lidar_drop_frame_index_in_as_dict() -> None:
    lidar = LidarConfig(drop_frame_index=150)
    assert lidar.as_dict()["drop_frame_index"] == 150


def test_lidar_drop_frame_index_env_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_LIDAR_DROP_FRAME_INDEX", "0")
    lidar = lidar_config_from_env()
    assert lidar.drop_frame_index == 0


def test_lidar_drop_frame_index_env_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_LIDAR_DROP_FRAME_INDEX", "150")
    lidar = lidar_config_from_env()
    assert lidar.drop_frame_index == 150


def test_lidar_drop_frame_index_env_minus_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_LIDAR_DROP_FRAME_INDEX", "-1")
    lidar = lidar_config_from_env()
    assert lidar.drop_frame_index == -1


def test_lidar_drop_frame_index_below_minus_one_fails_validation() -> None:
    lidar = LidarConfig(drop_frame_index=-2)
    errors = validate_carla_config(CarlaConfig(lidar=lidar))
    assert any("drop_frame_index" in e for e in errors)


def test_lidar_drop_frame_index_nonneg_passes_validation() -> None:
    lidar = LidarConfig(drop_frame_index=0)
    errors = validate_carla_config(CarlaConfig(lidar=lidar))
    assert not any("drop_frame_index" in e for e in errors)


def test_lidar_drop_frame_index_disabled_passes_validation() -> None:
    lidar = LidarConfig(drop_frame_index=-1)
    errors = validate_carla_config(CarlaConfig(lidar=lidar))
    assert not any("drop_frame_index" in e for e in errors)
