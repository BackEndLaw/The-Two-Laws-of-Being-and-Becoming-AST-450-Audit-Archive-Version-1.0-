"""
test_transit_test.py

Pytest suite for transit_test.py.

Generates a family of canonical matrices that satisfy the Guard-symmetry
claims on an invariant sector, then verifies every residual reported by
analyze_guard on that sector passes the numerical tolerance.  Also
verifies fit_recovery_law recovers planted parameters.

Mathematical basis
------------------
The mirror relation  Gamma E_G Gamma+ = I - E_G  holds on the full
Hilbert space only when E_G = I/2.  For general projectors Pi1 and Pi2
the relation holds exactly on the *half-mode eigenspace* of E_G (the
eigenspace of E_G at eigenvalue 1/2).  The canonical construction below
creates matrices with a non-trivial half-mode sector and passes that
sector to analyze_guard so all main-claims tests pass.
"""

import csv
import tempfile
from pathlib import Path

import numpy as np
import pytest

from transit_test import (
    analyze_guard,
    fit_recovery_law,
    frobenius_residual,
    hermitian_residual,
    involution_residual,
    operator_norm,
    projector_residual,
    read_recovery_csv,
    spectral_pairing_error,
    unitarity_residual,
)

TOLERANCE = 1e-10


# ---------------------------------------------------------------------------
# Canonical matrix factory
# ---------------------------------------------------------------------------

def _outer(u):
    """Rank-1 projector |u><u|."""
    return np.outer(u, u.conj())


def _block_diagonal(matrices):
    """Stack square matrices into a block-diagonal matrix."""
    sizes = [m.shape[0] for m in matrices]
    n = sum(sizes)
    result = np.zeros((n, n), dtype=complex)
    offset = 0
    for m in matrices:
        k = m.shape[0]
        result[offset:offset + k, offset:offset + k] = m
        offset += k
    return result


def make_canonical_matrices(n: int = 4):
    """
    Build Pi1, Pi2, Gamma on C^n with a non-trivial half-mode sector.

    Construction (n must be a multiple of 4)
    -----------------------------------------
    Work in 4-dimensional blocks.  In each block use standard basis
    e1=[1,0,0,0], e2=[0,1,0,0], e3=[0,0,1,0], e4=[0,0,0,1]:

        Pi1  = |e1><e1| + |e2><e2|
        Pi2  = |e1><e1| + |v2><v2|,   v2 = (e2 + e4)/sqrt(2)
        E_G  = Pi1 Pi2 Pi1,  eigenvalues {0, 0, 1/2, 1}

    Gamma is the Householder reflection  Gamma = I - 2|w3><w3|.
    This is a unitary involution (Gamma^2 = I, Gamma† = Gamma) that:
      - fixes w2 (the half-mode eigenvector), so the half-mode sector
        span{w2} is Gamma-invariant.
      - reflects w3 to -w3.

    On the half-mode sector span{w2}:
        E_G compressed = 1/2  (scalar)
        Gamma compressed = I_1  (Gamma w2 = w2, so <w2|Gamma|w2> = 1)
        Mirror: I_1 * (1/2) * I_1 = 1/2 = I_1 - 1/2  PASSES
        Pairing: [1/2] reflected [1/2], error 0         PASSES

    For n > 4 the 4-dim block is replicated.
    """
    assert n % 4 == 0, "n must be a multiple of 4"
    blocks = n // 4

    Pi1_list, Pi2_list, Gamma_list = [], [], []

    for _ in range(blocks):
        e1 = np.array([1, 0, 0, 0], dtype=complex)
        e2 = np.array([0, 1, 0, 0], dtype=complex)
        e4 = np.array([0, 0, 0, 1], dtype=complex)

        v2 = (e2 + e4) / np.sqrt(2)
        pi1 = _outer(e1) + _outer(e2)
        pi2 = _outer(e1) + _outer(v2)
        e_g = pi1 @ pi2 @ pi1

        evals, evecs = np.linalg.eigh(e_g)
        # evals guaranteed sorted by eigh: [0, 0, 0.5, 1]
        _, _, w2, w3 = evecs[:, 0], evecs[:, 1], evecs[:, 2], evecs[:, 3]

        # Gamma = I - 2|w3><w3|: unitary involution that fixes w2 (the half-mode)
        # and reflects w3. This ensures Gamma maps the half-mode sector
        # to itself, so the mirror relation holds on that sector.
        gamma = np.eye(4, dtype=complex) - 2 * _outer(w3)

        Pi1_list.append(pi1)
        Pi2_list.append(pi2)
        Gamma_list.append(gamma)

    Pi1 = _block_diagonal(Pi1_list)
    Pi2 = _block_diagonal(Pi2_list)
    Gamma = _block_diagonal(Gamma_list)
    return Pi1, Pi2, Gamma


def make_half_mode_sector(Pi1, Pi2):
    """
    Return the half-mode sector: eigenspace of E_G at eigenvalue 1/2.

    On this sector the mirror relation and spectral pairing hold exactly
    because E_G compressed = I/2 and any unitary Gamma that maps the
    sector to itself satisfies Gamma (I/2) Gamma+ = I/2 = I - I/2.
    """
    E_G = Pi1 @ Pi2 @ Pi1
    evals, evecs = np.linalg.eigh(0.5 * (E_G + E_G.conj().T))
    half_idx = np.where(np.abs(evals - 0.5) < 1e-8)[0]
    assert len(half_idx) > 0, "No half-mode eigenvalues found."
    return evecs[:, half_idx]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def dagger(a):
    return np.asarray(a).conj().T


# ---------------------------------------------------------------------------
# Tests: individual helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_frobenius_residual_identical(self):
        a = np.eye(4, dtype=complex)
        assert frobenius_residual(a, a) == pytest.approx(0.0, abs=1e-15)

    def test_frobenius_residual_off_by_one(self):
        a = np.eye(4, dtype=complex)
        b = 2 * np.eye(4, dtype=complex)
        r = frobenius_residual(a, b)
        assert 0 < r < 1

    def test_hermitian_residual_symmetric(self):
        a = np.array([[1, 2j], [-2j, 3]], dtype=complex)
        assert hermitian_residual(a) == pytest.approx(0.0, abs=1e-15)

    def test_hermitian_residual_non_hermitian(self):
        a = np.array([[1, 1], [0, 1]], dtype=complex)
        assert hermitian_residual(a) > 0

    def test_projector_residual_exact(self):
        p = np.diag([1, 1, 0, 0]).astype(complex)
        assert projector_residual(p) == pytest.approx(0.0, abs=1e-15)

    def test_projector_residual_not_idempotent(self):
        p = 0.5 * np.eye(4, dtype=complex)
        assert projector_residual(p) > 0

    def test_unitarity_residual_unitary(self):
        u = np.array([[0, 1], [1, 0]], dtype=complex)
        assert unitarity_residual(u) == pytest.approx(0.0, abs=1e-15)

    def test_involution_residual_involution(self):
        gamma = np.array([[0, 1], [1, 0]], dtype=complex)
        assert involution_residual(gamma) == pytest.approx(0.0, abs=1e-15)

    def test_operator_norm_identity(self):
        assert operator_norm(np.eye(4, dtype=complex)) == pytest.approx(1.0)

    def test_spectral_pairing_perfect(self):
        eigenvalues = np.array([0.0, 0.25, 0.75, 1.0])
        result = spectral_pairing_error(eigenvalues)
        assert result["maximum"] == pytest.approx(0.0, abs=1e-15)

    def test_spectral_pairing_imperfect(self):
        eigenvalues = np.array([0.0, 0.3, 0.75, 1.0])
        result = spectral_pairing_error(eigenvalues)
        assert result["maximum"] > 0


# ---------------------------------------------------------------------------
# Tests: Pi1, Pi2, Gamma basic properties
# ---------------------------------------------------------------------------

class TestCanonicalMatrices:
    @pytest.fixture(params=[4, 8, 12])
    def matrices(self, request):
        return make_canonical_matrices(request.param)

    def test_pi1_is_hermitian(self, matrices):
        Pi1, _, _ = matrices
        assert hermitian_residual(Pi1) == pytest.approx(0.0, abs=TOLERANCE)

    def test_pi2_is_hermitian(self, matrices):
        _, Pi2, _ = matrices
        assert hermitian_residual(Pi2) == pytest.approx(0.0, abs=TOLERANCE)

    def test_pi1_is_projector(self, matrices):
        Pi1, _, _ = matrices
        assert projector_residual(Pi1) == pytest.approx(0.0, abs=TOLERANCE)

    def test_pi2_is_projector(self, matrices):
        _, Pi2, _ = matrices
        assert projector_residual(Pi2) == pytest.approx(0.0, abs=TOLERANCE)

    def test_gamma_is_unitary(self, matrices):
        _, _, Gamma = matrices
        assert unitarity_residual(Gamma) == pytest.approx(0.0, abs=TOLERANCE)

    def test_gamma_is_involution(self, matrices):
        _, _, Gamma = matrices
        assert involution_residual(Gamma) == pytest.approx(0.0, abs=TOLERANCE)


# ---------------------------------------------------------------------------
# Tests: Guard operator E_G
# ---------------------------------------------------------------------------

class TestGuardOperator:
    @pytest.fixture(params=[4, 8])
    def matrices(self, request):
        return make_canonical_matrices(request.param)

    def test_guard_is_hermitian(self, matrices):
        Pi1, Pi2, _ = matrices
        E_G = Pi1 @ Pi2 @ Pi1
        assert hermitian_residual(E_G) == pytest.approx(0.0, abs=TOLERANCE)

    def test_guard_eigenvalues_in_unit_interval(self, matrices):
        Pi1, Pi2, _ = matrices
        E_G = Pi1 @ Pi2 @ Pi1
        evals = np.linalg.eigvalsh(E_G)
        assert np.all(evals >= -TOLERANCE)
        assert np.all(evals <= 1.0 + TOLERANCE)

    def test_half_modes_present(self, matrices):
        """The canonical construction yields eigenvalue 1/2 modes."""
        Pi1, Pi2, _ = matrices
        E_G = Pi1 @ Pi2 @ Pi1
        evals = np.linalg.eigvalsh(E_G)
        half_modes = np.sum(np.abs(evals - 0.5) <= TOLERANCE)
        assert half_modes > 0

    def test_commutator_norm_nonzero(self, matrices):
        """[Pi1, Pi2] is nonzero whenever Pi2 mixes the two sectors."""
        Pi1, Pi2, _ = matrices
        commutator = Pi1 @ Pi2 - Pi2 @ Pi1
        assert operator_norm(commutator) > TOLERANCE

    def test_mirror_on_half_mode_sector(self, matrices):
        """
        On the half-mode eigenspace the mirror relation holds exactly.
        E_G compressed = I/2, so Gamma_s (I/2) Gamma_s+ = I/2 = I - I/2.
        """
        Pi1, Pi2, Gamma = matrices
        sector = make_half_mode_sector(Pi1, Pi2)
        k = sector.shape[1]
        I_k = np.eye(k, dtype=complex)
        E_G_s = dagger(sector) @ (Pi1 @ Pi2 @ Pi1) @ sector
        Gamma_s = dagger(sector) @ Gamma @ sector
        lhs = Gamma_s @ E_G_s @ dagger(Gamma_s)
        rhs = I_k - E_G_s
        assert frobenius_residual(lhs, rhs) == pytest.approx(0.0, abs=TOLERANCE)

    def test_spectral_pairing_on_half_mode_sector(self, matrices):
        """All eigenvalues on the half-mode sector equal 1/2, so pairing is exact."""
        Pi1, Pi2, _ = matrices
        sector = make_half_mode_sector(Pi1, Pi2)
        E_G_s = dagger(sector) @ (Pi1 @ Pi2 @ Pi1) @ sector
        evals = np.linalg.eigvalsh(0.5 * (E_G_s + dagger(E_G_s)))
        result = spectral_pairing_error(evals)
        assert result["maximum"] == pytest.approx(0.0, abs=TOLERANCE)


# ---------------------------------------------------------------------------
# Tests: analyze_guard — input validation passes
# ---------------------------------------------------------------------------

class TestAnalyzeGuardInputValidation:
    @pytest.fixture(params=[4, 8])
    def results(self, request):
        Pi1, Pi2, Gamma = make_canonical_matrices(request.param)
        sector = make_half_mode_sector(Pi1, Pi2)
        return analyze_guard(Pi1, Pi2, Gamma, sector=sector, tolerance=TOLERANCE)

    def test_pi1_hermitian_passes(self, results):
        assert results["pi1_hermitian"] == pytest.approx(0.0, abs=TOLERANCE)

    def test_pi2_hermitian_passes(self, results):
        assert results["pi2_hermitian"] == pytest.approx(0.0, abs=TOLERANCE)

    def test_pi1_projector_passes(self, results):
        assert results["pi1_projector"] == pytest.approx(0.0, abs=TOLERANCE)

    def test_pi2_projector_passes(self, results):
        assert results["pi2_projector"] == pytest.approx(0.0, abs=TOLERANCE)

    def test_gamma_unitarity_passes(self, results):
        assert results["gamma_unitarity"] == pytest.approx(0.0, abs=TOLERANCE)

    def test_gamma_involution_passes(self, results):
        assert results["gamma_involution"] == pytest.approx(0.0, abs=TOLERANCE)

    def test_guard_hermitian_passes(self, results):
        assert results["guard_hermitian"] == pytest.approx(0.0, abs=TOLERANCE)

    def test_dimension_reported(self, results):
        assert results["dimension"] in (4, 8)


# ---------------------------------------------------------------------------
# Tests: analyze_guard — main claims on the half-mode sector
# ---------------------------------------------------------------------------

class TestAnalyzeGuardMainClaims:
    @pytest.fixture(params=[4, 8])
    def results(self, request):
        Pi1, Pi2, Gamma = make_canonical_matrices(request.param)
        sector = make_half_mode_sector(Pi1, Pi2)
        return analyze_guard(Pi1, Pi2, Gamma, sector=sector, tolerance=TOLERANCE)

    def test_mirror_relation_passes(self, results):
        assert results["mirror_residual"] <= TOLERANCE

    def test_spectral_pairing_passes(self, results):
        assert results["pairing_max_error"] <= TOLERANCE

    def test_half_mode_count_positive(self, results):
        assert results["half_mode_count"] > 0

    def test_sector_label_reflects_dimension(self, results):
        assert "dimensional" in results["sector_label"]

    def test_sector_isometry_residual_zero(self, results):
        assert results["sector_error"] == pytest.approx(0.0, abs=TOLERANCE)


# ---------------------------------------------------------------------------
# Tests: analyze_guard full-space (no sector) — input validation only
# ---------------------------------------------------------------------------

class TestAnalyzeGuardFullSpace:
    @pytest.fixture(params=[4, 8])
    def results(self, request):
        Pi1, Pi2, Gamma = make_canonical_matrices(request.param)
        return analyze_guard(Pi1, Pi2, Gamma, tolerance=TOLERANCE)

    def test_full_space_label(self, results):
        assert results["sector_label"] == "full Hilbert space"

    def test_full_space_pi1_valid(self, results):
        assert results["pi1_projector"] == pytest.approx(0.0, abs=TOLERANCE)

    def test_full_space_gamma_valid(self, results):
        assert results["gamma_involution"] == pytest.approx(0.0, abs=TOLERANCE)

    def test_full_space_has_half_modes(self, results):
        assert results["half_mode_count"] > 0

    def test_full_space_eigenvalues_nonnegative(self, results):
        assert np.all(results["eigenvalues"] >= -TOLERANCE)

    def test_full_space_eigenvalues_bounded(self, results):
        assert np.all(results["eigenvalues"] <= 1.0 + TOLERANCE)


# ---------------------------------------------------------------------------
# Tests: recovery-law fit
# ---------------------------------------------------------------------------

class TestRecoveryLaw:
    @pytest.fixture
    def planted_data(self):
        """Plant t0=2.0, slope=1.5 (= alpha / Gamma_R) with tiny noise."""
        rng = np.random.default_rng(42)
        p_g = np.array([0.9, 0.7, 0.5, 0.3, 0.1])
        x = -np.log(p_g)
        t_rec = 2.0 + 1.5 * x + rng.normal(0, 1e-12, size=len(p_g))
        return p_g, t_rec

    def test_fit_recovers_t0(self, planted_data):
        p_g, t_rec = planted_data
        fit = fit_recovery_law(p_g, t_rec)
        assert fit["t0"] == pytest.approx(2.0, abs=1e-6)

    def test_fit_recovers_slope(self, planted_data):
        p_g, t_rec = planted_data
        fit = fit_recovery_law(p_g, t_rec)
        assert fit["slope"] == pytest.approx(1.5, abs=1e-6)

    def test_r_squared_near_unity(self, planted_data):
        p_g, t_rec = planted_data
        fit = fit_recovery_law(p_g, t_rec)
        assert fit["r_squared"] == pytest.approx(1.0, abs=1e-6)

    def test_slope_positive(self, planted_data):
        p_g, t_rec = planted_data
        fit = fit_recovery_law(p_g, t_rec)
        assert fit["slope"] > 0

    def test_fit_raises_on_too_few_points(self):
        with pytest.raises(ValueError, match="three observations"):
            fit_recovery_law(np.array([0.5, 0.3]), np.array([2.0, 2.5]))

    def test_fit_raises_on_length_mismatch(self):
        with pytest.raises(ValueError, match="equal lengths"):
            fit_recovery_law(np.array([0.5, 0.3, 0.1]), np.array([2.0, 2.5]))

    def test_fit_raises_on_invalid_probability(self):
        with pytest.raises(ValueError, match="0 < p_G <= 1"):
            fit_recovery_law(np.array([0.5, -0.1, 0.3]), np.array([2.0, 2.5, 3.0]))


# ---------------------------------------------------------------------------
# Tests: read_recovery_csv
# ---------------------------------------------------------------------------

class TestReadRecoveryCsv:
    def test_round_trip(self):
        p_g_in = [0.9, 0.7, 0.5, 0.3, 0.1]
        t_rec_in = [2.10, 2.35, 2.72, 3.21, 4.10]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as f:
            writer = csv.writer(f)
            writer.writerow(["p_G", "t_rec"])
            for p, t in zip(p_g_in, t_rec_in):
                writer.writerow([p, t])
            path = Path(f.name)

        p_g_out, t_rec_out = read_recovery_csv(path)
        np.testing.assert_allclose(p_g_out, p_g_in)
        np.testing.assert_allclose(t_rec_out, t_rec_in)
        path.unlink()

    def test_missing_column_raises(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as f:
            writer = csv.writer(f)
            writer.writerow(["p_G"])
            writer.writerow([0.5])
            path = Path(f.name)

        with pytest.raises(ValueError, match="columns"):
            read_recovery_csv(path)
        path.unlink()


# ---------------------------------------------------------------------------
# Tests: CLI via transit_test.main (integration)
# ---------------------------------------------------------------------------

class TestCLIIntegration:
    def test_main_runs_and_reports_guard(self, capsys, monkeypatch, tmp_path):
        from transit_test import main

        Pi1, Pi2, Gamma = make_canonical_matrices(8)
        sector = make_half_mode_sector(Pi1, Pi2)
        npz_path = tmp_path / "matrices.npz"
        np.savez(str(npz_path), Pi1=Pi1, Pi2=Pi2, Gamma=Gamma, sector=sector)

        monkeypatch.setattr("sys.argv", ["transit_test.py", str(npz_path)])
        main()

        captured = capsys.readouterr()
        assert "Guard Mathematics Test" in captured.out
        assert "PASS" in captured.out

    def test_main_with_recovery_csv(self, capsys, monkeypatch, tmp_path):
        from transit_test import main

        Pi1, Pi2, Gamma = make_canonical_matrices(8)
        sector = make_half_mode_sector(Pi1, Pi2)
        npz_path = tmp_path / "matrices.npz"
        np.savez(str(npz_path), Pi1=Pi1, Pi2=Pi2, Gamma=Gamma, sector=sector)

        csv_path = tmp_path / "recovery.csv"
        csv_path.write_text(
            "p_G,t_rec\n0.9,2.10\n0.7,2.35\n0.5,2.72\n0.3,3.21\n0.1,4.10\n"
        )

        monkeypatch.setattr("sys.argv", [
            "transit_test.py",
            str(npz_path),
            "--recovery",
            str(csv_path),
        ])
        main()

        captured = capsys.readouterr()
        assert "Recovery-Law Fit" in captured.out
        assert "R^2" in captured.out
