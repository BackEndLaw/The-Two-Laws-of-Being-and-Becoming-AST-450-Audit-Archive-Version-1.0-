#!/usr/bin/env python3
"""
transit_test.py

Tests the proposed Guard symmetry and fits the Transit recovery law.

Dependencies:
    pip install numpy

Expected NPZ entries:
    Pi1      First projector, shape (N, N)
    Pi2      Second projector, shape (N, N)
    Gamma    Proposed mirror operator, shape (N, N)

Optional:
    sector   Isometry whose columns span the claimed invariant sector,
             shape (N, K)

Example:
    python transit_test.py matrices.npz
    python transit_test.py matrices.npz --recovery recovery.csv
"""

import argparse
import csv
from pathlib import Path

import numpy as np


def dagger(a):
    """Hermitian conjugate."""
    return np.asarray(a).conj().T


def frobenius_residual(lhs, rhs):
    """Relative Frobenius residual ||lhs-rhs||_F / max(||rhs||_F, 1)."""
    numerator = np.linalg.norm(lhs - rhs, ord="fro")
    denominator = max(np.linalg.norm(rhs, ord="fro"), 1.0)
    return float(numerator / denominator)


def operator_norm(a):
    """Largest singular value."""
    return float(np.linalg.norm(a, ord=2))


def hermitian_residual(a):
    return frobenius_residual(a, dagger(a))


def projector_residual(p):
    return frobenius_residual(p @ p, p)


def unitarity_residual(u):
    identity = np.eye(u.shape[0], dtype=complex)
    return frobenius_residual(dagger(u) @ u, identity)


def involution_residual(gamma):
    identity = np.eye(gamma.shape[0], dtype=complex)
    return frobenius_residual(gamma @ gamma, identity)


def compress(operator, sector):
    """Compress an operator to the column space of an isometry."""
    return dagger(sector) @ operator @ sector


def validate_sector(sector):
    k = sector.shape[1]
    identity = np.eye(k, dtype=complex)
    return frobenius_residual(dagger(sector) @ sector, identity)


def spectral_pairing_error(eigenvalues):
    """
    If eigenvalues are sorted increasingly, mirror symmetry requires

        lambda_i = 1 - lambda_{n-1-i}.
    """
    values = np.sort(np.real_if_close(eigenvalues).real)
    reflected = 1.0 - values[::-1]
    errors = np.abs(values - reflected)

    return {
        "maximum": float(np.max(errors)),
        "mean": float(np.mean(errors)),
        "errors": errors,
    }


def analyze_guard(pi1, pi2, gamma, sector=None, tolerance=1e-8):
    n = pi1.shape[0]

    if pi1.shape != (n, n):
        raise ValueError("Pi1 must be square.")
    if pi2.shape != (n, n):
        raise ValueError("Pi2 must have the same shape as Pi1.")
    if gamma.shape != (n, n):
        raise ValueError("Gamma must have the same shape as Pi1.")

    guard = pi1 @ pi2 @ pi1
    commutator = pi1 @ pi2 - pi2 @ pi1

    if sector is None:
        sector_guard = guard
        sector_gamma = gamma
        sector_label = "full Hilbert space"
        sector_error = None
        leakage = None
    else:
        if sector.shape[0] != n:
            raise ValueError("The sector basis has an incompatible dimension.")

        sector_error = validate_sector(sector)
        sector_guard = compress(guard, sector)
        sector_gamma = compress(gamma, sector)
        sector_label = f"{sector.shape[1]}-dimensional supplied sector"

        projector_onto_sector = sector @ dagger(sector)
        leakage = operator_norm(
            (np.eye(n, dtype=complex) - projector_onto_sector)
            @ gamma
            @ sector
        )

    k = sector_guard.shape[0]
    identity = np.eye(k, dtype=complex)

    # Use Gamma E Gamma^\dagger. If Gamma is Hermitian and involutory,
    # this is equivalent to Gamma E Gamma.
    mirror_lhs = sector_gamma @ sector_guard @ dagger(sector_gamma)
    mirror_rhs = identity - sector_guard

    eigenvalues = np.linalg.eigvalsh(
        0.5 * (sector_guard + dagger(sector_guard))
    )
    pairing = spectral_pairing_error(eigenvalues)

    half_modes = np.flatnonzero(np.abs(eigenvalues - 0.5) <= tolerance)

    return {
        "dimension": n,
        "sector_label": sector_label,
        "sector_error": sector_error,
        "sector_leakage": leakage,
        "pi1_hermitian": hermitian_residual(pi1),
        "pi2_hermitian": hermitian_residual(pi2),
        "pi1_projector": projector_residual(pi1),
        "pi2_projector": projector_residual(pi2),
        "gamma_unitarity": unitarity_residual(gamma),
        "gamma_involution": involution_residual(gamma),
        "guard_hermitian": hermitian_residual(guard),
        "mirror_residual": frobenius_residual(mirror_lhs, mirror_rhs),
        "pairing_max_error": pairing["maximum"],
        "pairing_mean_error": pairing["mean"],
        "half_mode_count": int(len(half_modes)),
        "half_mode_indices": half_modes.tolist(),
        "commutator_norm": operator_norm(commutator),
        "eigenvalues": eigenvalues,
    }


def read_recovery_csv(filename):
    """
    CSV format:

        p_G,t_rec
        0.8,2.1
        0.5,2.8
        0.25,3.5
    """
    probabilities = []
    recovery_times = []

    with open(filename, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        required = {"p_G", "t_rec"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                f"Recovery CSV must contain columns {sorted(required)}."
            )

        for row in reader:
            probabilities.append(float(row["p_G"]))
            recovery_times.append(float(row["t_rec"]))

    return np.asarray(probabilities), np.asarray(recovery_times)


def fit_recovery_law(probabilities, recovery_times):
    """
    Fits

        t_rec = t0 + c(-log p_G),

    where the proposed law identifies c = alpha / Gamma_R.
    """
    probabilities = np.asarray(probabilities, dtype=float)
    recovery_times = np.asarray(recovery_times, dtype=float)

    if len(probabilities) != len(recovery_times):
        raise ValueError("p_G and t_rec must have equal lengths.")
    if len(probabilities) < 3:
        raise ValueError("At least three observations are required.")
    if np.any(probabilities <= 0) or np.any(probabilities > 1):
        raise ValueError("Each probability must satisfy 0 < p_G <= 1.")

    x = -np.log(probabilities)
    design = np.column_stack([np.ones_like(x), x])

    coefficients, _, _, _ = np.linalg.lstsq(
        design, recovery_times, rcond=None
    )
    t0, slope = coefficients

    predictions = design @ coefficients
    residuals = recovery_times - predictions

    sum_squared_residuals = float(np.sum(residuals**2))
    centered = recovery_times - np.mean(recovery_times)
    total_sum_squares = float(np.sum(centered**2))

    if total_sum_squares > 0:
        r_squared = 1.0 - sum_squared_residuals / total_sum_squares
    else:
        r_squared = float("nan")

    degrees_of_freedom = len(x) - 2

    if degrees_of_freedom > 0:
        variance = sum_squared_residuals / degrees_of_freedom
        covariance = variance * np.linalg.inv(design.T @ design)
        standard_errors = np.sqrt(np.diag(covariance))
        t0_error, slope_error = standard_errors
    else:
        t0_error = float("nan")
        slope_error = float("nan")

    return {
        "t0": float(t0),
        "t0_standard_error": float(t0_error),
        "slope": float(slope),
        "slope_standard_error": float(slope_error),
        "r_squared": float(r_squared),
        "predictions": predictions,
        "residuals": residuals,
    }


def print_guard_report(results, tolerance):
    print("\n=== Guard Mathematics Test ===")
    print(f"Hilbert-space dimension:       {results['dimension']}")
    print(f"Tested domain:                 {results['sector_label']}")
    print(f"Numerical tolerance:           {tolerance:.2e}")

    if results["sector_error"] is not None:
        print(
            "Sector-isometry residual:      "
            f"{results['sector_error']:.3e}"
        )
        print(
            "Gamma sector leakage:          "
            f"{results['sector_leakage']:.3e}"
        )

    print("\n--- Input validation ---")
    print(f"Pi1 Hermiticity residual:      {results['pi1_hermitian']:.3e}")
    print(f"Pi2 Hermiticity residual:      {results['pi2_hermitian']:.3e}")
    print(f"Pi1 projector residual:        {results['pi1_projector']:.3e}")
    print(f"Pi2 projector residual:        {results['pi2_projector']:.3e}")
    print(f"Gamma unitarity residual:      {results['gamma_unitarity']:.3e}")
    print(f"Gamma involution residual:     {results['gamma_involution']:.3e}")

    print("\n--- Main claims ---")
    print(f"Guard Hermiticity residual:    {results['guard_hermitian']:.3e}")
    print(f"Mirror-relation residual:      {results['mirror_residual']:.3e}")
    print(f"Maximum pairing error:         {results['pairing_max_error']:.3e}")
    print(f"Mean pairing error:            {results['pairing_mean_error']:.3e}")
    print(f"Half-mode count:               {results['half_mode_count']}")
    print(f"||[Pi1, Pi2]||_2:              {results['commutator_norm']:.8f}")

    mirror_pass = results["mirror_residual"] <= tolerance
    pairing_pass = results["pairing_max_error"] <= tolerance

    print("\n--- Verdict at selected tolerance ---")
    print(f"Mirror relation:               {'PASS' if mirror_pass else 'FAIL'}")
    print(f"Spectral pairing:              {'PASS' if pairing_pass else 'FAIL'}")

    if results["half_mode_count"] > 0:
        commutator_half_error = abs(results["commutator_norm"] - 0.5)
        print(
            "Distance of global commutator norm from 1/2: "
            f"{commutator_half_error:.3e}"
        )

    print("\nEigenvalues of E_G on tested domain:")
    print(
        np.array2string(
            results["eigenvalues"],
            precision=8,
            suppress_small=True,
            max_line_width=120,
        )
    )


def print_recovery_report(fit):
    print("\n=== Recovery-Law Fit ===")
    print("Model: t_rec = t0 + c(-log p_G)")
    print(f"t0:             {fit['t0']:.8f}")
    print(f"SE(t0):         {fit['t0_standard_error']:.8f}")
    print(f"c = alpha/G_R:  {fit['slope']:.8f}")
    print(f"SE(c):          {fit['slope_standard_error']:.8f}")
    print(f"R^2:            {fit['r_squared']:.8f}")

    if fit["slope"] <= 0:
        print(
            "Warning: fitted slope is nonpositive, contrary to the "
            "proposed positive-delay law."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Test Guard symmetry and the Transit recovery law."
    )
    parser.add_argument(
        "matrices",
        type=Path,
        help="NPZ file containing Pi1, Pi2, Gamma, and optional sector.",
    )
    parser.add_argument(
        "--recovery",
        type=Path,
        help="Optional CSV containing p_G and t_rec columns.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-8,
        help="Numerical pass/fail tolerance.",
    )
    args = parser.parse_args()

    data = np.load(args.matrices)

    required = {"Pi1", "Pi2", "Gamma"}
    missing = required.difference(data.files)

    if missing:
        raise KeyError(f"NPZ file is missing entries: {sorted(missing)}")

    sector = data["sector"] if "sector" in data.files else None

    results = analyze_guard(
        pi1=data["Pi1"],
        pi2=data["Pi2"],
        gamma=data["Gamma"],
        sector=sector,
        tolerance=args.tolerance,
    )
    print_guard_report(results, args.tolerance)

    if args.recovery is not None:
        p_g, t_rec = read_recovery_csv(args.recovery)
        fit = fit_recovery_law(p_g, t_rec)
        print_recovery_report(fit)


if __name__ == "__main__":
    main()
