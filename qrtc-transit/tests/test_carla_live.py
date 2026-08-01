"""
Live CARLA smoke test
=====================
This test is **excluded from the default test run** because it requires a
separately running CARLA server that is not available in ordinary CI.

To execute it manually (Windows PowerShell):

  $env:CARLA_TICKS = "100"
  pytest -m carla_live qrtc-transit/tests/test_carla_live.py -v

Ensure CARLA is running before invoking:
  .\\CarlaUE4.exe -carla-port=2000 -quality-level=Low -windowed -ResX=800 -ResY=600
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qrtc.carla_harness import HarnessConfig, run_drive


@pytest.mark.carla_live
def test_live_drive_completes_and_writes_evidence(tmp_path: Path) -> None:
    """
    Smoke-test the full drive loop against a real CARLA server.

    Reads connection parameters from environment variables; falls back to
    localhost defaults.  Uses a short 100-tick run to keep wall time low.
    """
    cfg = HarnessConfig.from_env()
    # Override ticks to keep the smoke test short even if CARLA_TICKS is unset
    if cfg.ticks > 100:
        import os

        cfg = HarnessConfig(
            host=cfg.host,
            port=cfg.port,
            tm_port=cfg.tm_port,
            timeout=cfg.timeout,
            ticks=100,
            spawn_point_index=cfg.spawn_point_index,
            output_path=tmp_path / "live-result.json",
        )
    else:
        cfg = HarnessConfig(
            host=cfg.host,
            port=cfg.port,
            tm_port=cfg.tm_port,
            timeout=cfg.timeout,
            ticks=cfg.ticks,
            spawn_point_index=cfg.spawn_point_index,
            output_path=tmp_path / "live-result.json",
        )

    exit_code = run_drive(cfg)
    assert exit_code == 0, "run_drive returned nonzero — check stderr for diagnostics"

    evidence_path = cfg.output_path
    assert evidence_path.exists(), f"Evidence file not found at {evidence_path}"

    data = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert data["ticks_completed"] == cfg.ticks
    assert data["error"] is None
    assert len(data["records"]) > 0
    assert data["map_name"] != ""
    assert data["vehicle_blueprint"] != ""
