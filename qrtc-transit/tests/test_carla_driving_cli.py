from __future__ import annotations

from qrtc import carla_driving_cli


def test_main_returns_success_for_passing_assessment(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        carla_driving_cli,
        "run_live_driving_test",
        lambda config: {"assessment": {"passed": True}},
    )
    assert carla_driving_cli.main() == 0
    assert '"passed": true' in capsys.readouterr().out


def test_main_returns_failure_for_failed_assessment(monkeypatch) -> None:
    monkeypatch.setattr(
        carla_driving_cli,
        "run_live_driving_test",
        lambda config: {"assessment": {"passed": False}},
    )
    assert carla_driving_cli.main() == 1
