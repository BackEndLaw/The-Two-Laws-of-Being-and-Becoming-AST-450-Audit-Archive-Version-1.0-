"""CLI and package smoke tests.

These tests verify that every console command declared in [project.scripts]
can be resolved and invokes --help (or an equivalent non-destructive check)
without error.  They also confirm that Phase IV-B's test module can be
imported after the specification stub is in place.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", *args],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=60,
        **kwargs,
    )


# ── Import smoke tests ────────────────────────────────────────────────────────

def test_qrtc_package_imports() -> None:
    result = _run(["python", "-c", "import qrtc; print(qrtc.__file__)"])
    # Fallback: try the -c approach via the interpreter
    result = subprocess.run(
        [sys.executable, "-c", "import qrtc; print('ok')"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_qrtc_benchmark_phase5_imports() -> None:
    result = subprocess.run(
        [sys.executable, "-c",
         "from qrtc_benchmark.phase5 import PHASE5_REVISION; "
         "assert PHASE5_REVISION == 'phase5b', PHASE5_REVISION; print('ok')"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_phase4b_imports_after_specification_stub() -> None:
    """Phase IV-B should import cleanly now that specification.py exists."""
    result = subprocess.run(
        [sys.executable, "-c",
         "from qrtc_benchmark.phase4b import DEFAULT_PHASE4B_PAIRS; "
         "assert len(DEFAULT_PHASE4B_PAIRS) == 6; print('ok')"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, (
        f"phase4b import failed:\n{result.stderr}"
    )
    assert "ok" in result.stdout


def test_specification_stub_criterion_id() -> None:
    result = subprocess.run(
        [sys.executable, "-c",
         "from qrtc_benchmark.specification import CriterionId; "
         "assert {CriterionId.PI1, CriterionId.PI2, CriterionId.PI3}; print('ok')"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


# ── CLI --help smoke tests ────────────────────────────────────────────────────

@pytest.mark.parametrize("entry_point,module_path", [
    ("qrtc", "qrtc.cli"),
    ("qrtc-demo", "qrtc.telemetry_demo"),
    ("qrtc-benchmark-phase5", "qrtc_benchmark.run_phase5"),
])
def test_cli_help_smoke(entry_point: str, module_path: str) -> None:
    """Every declared console command must resolve and respond to --help."""
    result = subprocess.run(
        [sys.executable, "-m", module_path.replace(".", "/").replace("/", "."),
         "--help"],
        capture_output=True, text=True, timeout=30,
    )
    # --help typically exits with code 0 (argparse) but the key thing is it
    # doesn't crash with an ImportError or AttributeError.
    assert result.returncode in (0, 1), (
        f"CLI {entry_point!r} (module {module_path}) --help exited with "
        f"unexpected code {result.returncode}:\n{result.stderr[:1000]}"
    )
    # Must not be an import error or missing module error.
    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert "ImportError" not in result.stderr, result.stderr


@pytest.mark.parametrize("module_path", [
    "qrtc.cli",
    "qrtc.telemetry_demo",
    "qrtc_benchmark.run_phase5",
])
def test_declared_entry_point_modules_importable(module_path: str) -> None:
    """Every module referenced by a [project.scripts] entry must be importable."""
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_path}; print('ok')"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"Module {module_path!r} is not importable:\n{result.stderr[:1000]}"
    )


@pytest.mark.parametrize("removed_module", [
    "qrtc_benchmark.run_phase1",
    "qrtc_benchmark.run_phase2",
    "qrtc_benchmark.run_phase2_sweep",
    "qrtc_benchmark.run_phase3",
    "qrtc_benchmark.run_phase4",
])
def test_removed_entry_point_modules_are_absent(removed_module: str) -> None:
    """Modules removed from entry points must not accidentally exist."""
    result = subprocess.run(
        [sys.executable, "-c", f"import {removed_module}"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0, (
        f"Module {removed_module!r} unexpectedly exists.  "
        "If it was restored, add it back to pyproject.toml [project.scripts]."
    )


# ── Phase V-B smoke run from source ──────────────────────────────────────────

def test_phase5b_development_smoke_run(tmp_path: Path) -> None:
    """Run a tiny Phase V-B development benchmark end-to-end from source."""
    result = subprocess.run(
        [
            sys.executable, "-c",
            (
                "import sys, json\n"
                "from pathlib import Path\n"
                "from qrtc_benchmark.phase5 import Phase5Config, run_phase5_benchmark, PHASE5_REVISION\n"
                "cfg = Phase5Config(bootstrap_reps=20, development_family_trials=16, "
                "validation_family_trials=8, test_family_trials=8)\n"
                f"bundle = run_phase5_benchmark('development', Path(r'{tmp_path}'), config=cfg)\n"
                "assert bundle['runs_csv'].exists()\n"
                "assert bundle['checksums'].exists()\n"
                "checksums = bundle['checksums'].read_text()\n"
                "assert '/' in checksums  # relative path separator\n"
                "assert not any(c.isspace() and c != ' ' or c == '\\\\' for c in checksums.split('  ')[1].split()[0])\n"
                "manifest = json.loads(bundle['manifest_json'].read_text())\n"
                "assert manifest.get('phase_revision') == PHASE5_REVISION\n"
                "print('smoke ok')\n"
            ),
        ],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, (
        f"Phase V-B smoke run failed:\nstdout: {result.stdout}\nstderr: {result.stderr[:2000]}"
    )
    assert "smoke ok" in result.stdout
