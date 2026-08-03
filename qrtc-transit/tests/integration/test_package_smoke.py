"""CLI, packaging, and archival import smoke tests."""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_SRC = _PACKAGE_ROOT / "src"


def _project_scripts() -> dict[str, str]:
    with (_PACKAGE_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    return dict(pyproject["project"]["scripts"])


def _entry_point_modules() -> dict[str, str]:
    return {
        script_name: target.split(":", 1)[0]
        for script_name, target in _project_scripts().items()
    }


def _source_smoke_invocations() -> dict[str, list[str]]:
    return {
        "qrtc": ["--help"],
        "qrtc-demo": [],
        "carla-live-drive": ["--help"],
        "qrtc-benchmark-phase5": ["--help"],
        "qrtc-controller": ["--help"],
        "qrtc-selection": ["--help"],
        "qrtc-benchmark-phase5b-dev": ["--help"],
    }


def _assert_script_coverage() -> dict[str, str]:
    scripts = _project_scripts()
    smoke_invocations = _source_smoke_invocations()
    assert set(smoke_invocations) == set(scripts), (
        "Update test_package_smoke.py so every [project.scripts] entry has a "
        f"documented smoke invocation. Missing={set(scripts) - set(smoke_invocations)} "
        f"Extra={set(smoke_invocations) - set(scripts)}"
    )
    return scripts


_PROJECT_SCRIPTS = _assert_script_coverage()
_ENTRY_POINT_MODULES = _entry_point_modules()
_SOURCE_SMOKE_INVOCATIONS = _source_smoke_invocations()


def _source_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(_SRC) if not existing else os.pathsep.join((str(_SRC), existing))
    )
    return env


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return env


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=timeout,
        check=False,
    )


def _assert_success(result: subprocess.CompletedProcess[str], description: str) -> None:
    assert result.returncode == 0, (
        f"{description} failed with exit code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def _venv_python(venv_dir: Path) -> Path:
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    python_name = "python.exe" if os.name == "nt" else "python"
    return venv_dir / scripts_dir / python_name


def _venv_script(venv_dir: Path, script_name: str) -> Path:
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    return venv_dir / scripts_dir / f"{script_name}{suffix}"


def test_qrtc_package_imports() -> None:
    result = _run(
        [sys.executable, "-c", "import qrtc; print('ok')"],
        cwd=_PACKAGE_ROOT,
        env=_source_env(),
        timeout=10,
    )
    _assert_success(result, "import qrtc from source")
    assert "ok" in result.stdout


def test_qrtc_benchmark_phase5_imports() -> None:
    result = _run(
        [
            sys.executable,
            "-c",
            (
                "from qrtc_benchmark.phase5 import PHASE5_REVISION; "
                "assert PHASE5_REVISION == 'phase5b', PHASE5_REVISION; print('ok')"
            ),
        ],
        cwd=_PACKAGE_ROOT,
        env=_source_env(),
        timeout=10,
    )
    _assert_success(result, "import qrtc_benchmark.phase5 from source")
    assert "ok" in result.stdout


def test_phase4b_imports_for_archival_verification() -> None:
    """Phase IV-B remains importable/runnable for archival verification only."""
    result = _run(
        [
            sys.executable,
            "-c",
            (
                "from qrtc_benchmark.phase4b import DEFAULT_PHASE4B_PAIRS; "
                "assert len(DEFAULT_PHASE4B_PAIRS) == 6; print('ok')"
            ),
        ],
        cwd=_PACKAGE_ROOT,
        env=_source_env(),
        timeout=10,
    )
    _assert_success(result, "import qrtc_benchmark.phase4b from source")
    assert "ok" in result.stdout


def test_specification_stub_criterion_id() -> None:
    result = _run(
        [
            sys.executable,
            "-c",
            (
                "from qrtc_benchmark.specification import CriterionId; "
                "assert {CriterionId.PI1, CriterionId.PI2, CriterionId.PI3}; print('ok')"
            ),
        ],
        cwd=_PACKAGE_ROOT,
        env=_source_env(),
        timeout=10,
    )
    _assert_success(result, "import CriterionId stub from source")
    assert "ok" in result.stdout


@pytest.mark.parametrize(
    ("entry_point", "module_path"),
    sorted(_ENTRY_POINT_MODULES.items()),
)
def test_declared_entry_point_modules_importable(
    entry_point: str, module_path: str
) -> None:
    """Every module referenced by a [project.scripts] entry must be importable."""
    result = _run(
        [sys.executable, "-c", f"import {module_path}; print('ok')"],
        cwd=_PACKAGE_ROOT,
        env=_source_env(),
        timeout=30,
    )
    _assert_success(result, f"import entry point module for {entry_point!r}")
    assert "ok" in result.stdout


@pytest.mark.parametrize(
    ("entry_point", "module_path"),
    sorted(_ENTRY_POINT_MODULES.items()),
)
def test_cli_smoke_from_source(entry_point: str, module_path: str) -> None:
    """Every declared console command must have a successful source smoke path."""
    result = _run(
        [sys.executable, "-m", module_path, *_SOURCE_SMOKE_INVOCATIONS[entry_point]],
        cwd=_PACKAGE_ROOT,
        env=_source_env(),
        timeout=60,
    )
    _assert_success(result, f"source smoke for {entry_point!r}")


@pytest.mark.parametrize(
    "removed_module",
    [
        "qrtc_benchmark.run_phase1",
        "qrtc_benchmark.run_phase2",
        "qrtc_benchmark.run_phase2_sweep",
        "qrtc_benchmark.run_phase3",
        "qrtc_benchmark.run_phase4",
    ],
)
def test_removed_entry_point_modules_are_absent(removed_module: str) -> None:
    """Modules removed from entry points must not accidentally exist."""
    result = _run(
        [sys.executable, "-c", f"import {removed_module}"],
        cwd=_PACKAGE_ROOT,
        env=_source_env(),
        timeout=10,
    )
    assert result.returncode != 0, (
        f"Module {removed_module!r} unexpectedly exists. "
        "If it was restored, add it back to pyproject.toml [project.scripts]."
    )


def test_phase5b_development_smoke_run(tmp_path: Path) -> None:
    """Run a tiny Phase V-B development benchmark end-to-end from source."""
    output_dir = tmp_path / "phase5-source-smoke"
    result = _run(
        [
            sys.executable,
            "-c",
            (
                "import json\n"
                "from pathlib import Path\n"
                "from qrtc_benchmark.phase5 import Phase5Config, PHASE5_REVISION, run_phase5_benchmark\n"
                "cfg = Phase5Config(bootstrap_reps=20, development_family_trials=16, "
                "validation_family_trials=8, test_family_trials=8)\n"
                f"bundle = run_phase5_benchmark('development', Path(r'{output_dir}'), config=cfg)\n"
                "assert bundle['runs_csv'].exists()\n"
                "assert bundle['checksums'].exists()\n"
                "manifest = json.loads(bundle['manifest_json'].read_text())\n"
                "assert manifest.get('phase_revision') == PHASE5_REVISION\n"
                "print('smoke ok')\n"
            ),
        ],
        cwd=_PACKAGE_ROOT,
        env=_source_env(),
        timeout=120,
    )
    _assert_success(result, "source Phase V-B development smoke")
    assert "smoke ok" in result.stdout


def test_clean_wheel_install_smoke(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    workspace = tmp_path / "installed-smoke"
    venv_dir = tmp_path / "venv"
    dist_dir.mkdir()
    workspace.mkdir()

    build_result = _run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--sdist",
            "--outdir",
            str(dist_dir),
        ],
        cwd=_PACKAGE_ROOT,
        env=_source_env(),
        timeout=180,
    )
    _assert_success(
        build_result,
        "build wheel and sdist (install the local 'build' package if this fails)",
    )

    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    assert len(wheels) == 1, f"Expected one wheel in {dist_dir}, found {wheels}"
    assert len(sdists) == 1, f"Expected one sdist in {dist_dir}, found {sdists}"

    venv_result = _run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        cwd=workspace,
        env=_clean_env(),
        timeout=120,
    )
    _assert_success(venv_result, "create clean virtual environment")

    venv_python = _venv_python(venv_dir)
    install_result = _run(
        [str(venv_python), "-m", "pip", "install", str(wheels[0])],
        cwd=workspace,
        env=_clean_env(),
        timeout=180,
    )
    _assert_success(
        install_result, "install built wheel into clean virtual environment"
    )

    pip_check_result = _run(
        [str(venv_python), "-m", "pip", "check"],
        cwd=workspace,
        env=_clean_env(),
        timeout=60,
    )
    _assert_success(pip_check_result, "pip check inside clean virtual environment")

    import_result = _run(
        [
            str(venv_python),
            "-c",
            (
                "from pathlib import Path\n"
                "import qrtc, qrtc_benchmark\n"
                f"repo_root = Path(r'{_PACKAGE_ROOT.resolve()}')\n"
                "qrtc_path = Path(qrtc.__file__).resolve()\n"
                "benchmark_path = Path(qrtc_benchmark.__file__).resolve()\n"
                "assert repo_root not in qrtc_path.parents\n"
                "assert repo_root not in benchmark_path.parents\n"
                "assert 'site-packages' in str(qrtc_path)\n"
                "assert 'site-packages' in str(benchmark_path)\n"
                "print('imports ok')\n"
            ),
        ],
        cwd=workspace,
        env=_clean_env(),
        timeout=30,
    )
    _assert_success(import_result, "import installed qrtc packages")
    assert "imports ok" in import_result.stdout

    for entry_point, args in sorted(_SOURCE_SMOKE_INVOCATIONS.items()):
        result = _run(
            [str(_venv_script(venv_dir, entry_point)), *args],
            cwd=workspace,
            env=_clean_env(),
            timeout=60,
        )
        _assert_success(result, f"installed smoke for {entry_point!r}")

    installed_output_dir = workspace / "phase5-installed-smoke"
    benchmark_result = _run(
        [
            str(_venv_script(venv_dir, "qrtc-benchmark-phase5")),
            "--split",
            "development",
            "--output-dir",
            str(installed_output_dir),
            "--bootstrap-reps",
            "20",
        ],
        cwd=workspace,
        env=_clean_env(),
        timeout=180,
    )
    _assert_success(benchmark_result, "installed Phase V-B development smoke")
    assert installed_output_dir.exists()
    assert (installed_output_dir / "development" / "phase5_runs.csv").exists()
