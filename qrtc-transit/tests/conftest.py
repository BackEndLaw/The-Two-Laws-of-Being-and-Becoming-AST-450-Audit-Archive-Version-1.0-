"""
pytest configuration for qrtc-transit tests.

Defines the ``live`` marker for tests that require an actual CARLA server.
Live tests are excluded from the default test run and skip cleanly unless
the ``--live`` flag is provided and CARLA is importable.
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="include tests that require a live CARLA simulator",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: mark test as requiring a live CARLA simulator (excluded by default)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--live", default=False):
        return
    skip_live = pytest.mark.skip(reason="live CARLA test; pass --live to run")
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip_live)
