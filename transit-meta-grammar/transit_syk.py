from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.linalg import expm, eigh


SEED = 314159
DISORDER_SEED = SEED + 1
ISOMETRY_SEED = SEED + 2
TOL = 1e-9
DEFAULT_N_MAJORANAS_PER_SIDE = 6
DEFAULT_J = 1.0
DEFAULT_MU = 0.08
DEFAULT_BETA = 1.5
DEFAULT_GUARD_ENERGY_FRACTION = 0.20
DEFAULT_GUARD_CORRELATION_FRACTION = 0.20
DEFAULT_TIME_GRID = np.linspace(0.0, 6.0, 31)

PAULI_X = np.array([[0, 1], [1, 0]], dtype=complex)
PAULI_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
PAULI_Z = np.array([[1, 0], [0, -1]], dtype=complex)
IDENTITY_2 = np.eye(2, dtype=complex)


@dataclass(frozen=True)
class Partition:
    dims: tuple[int, ...]
    left_indices: tuple[int, ...]
    right_indices: tuple[int, ...]


def kron_all(operators: Sequence[np.ndarray]) -> np.ndarray:
    result = np.array([[1.0 + 0.0j]])
    for operator in operators:
        result = np.kron(result, operator)
    return result


def hermitize(matrix: np.ndarray) -> np.ndarray:
    return 0.5 * (matrix + matrix.conj().T)


def clip_probability(value: float, atol: float = 1e-12) -> float:
    if value < 0 and abs(value) <= atol:
        return 0.0
    if value > 1 and abs(value - 1) <= atol:
        return 1.0
    return min(max(value, 0.0), 1.0)


def safe_barrier(probability: float) -> float:
    return float(-math.log(max(probability, 1e-15)))


def matrix_entropy(matrix: np.ndarray, atol: float = 1e-12) -> float:
    eigenvalues = np.linalg.eigvalsh(hermitize(matrix))
    eigenvalues = np.clip(np.real_if_close(eigenvalues), 0.0, 1.0)
    eigenvalues = eigenvalues[eigenvalues > atol]
    if eigenvalues.size == 0:
        return 0.0
    return float(-np.sum(eigenvalues * np.log(eigenvalues)))


def thermal_state(hamiltonian: np.ndarray, beta: float) -> np.ndarray:
    eigenvalues, eigenvectors = eigh(hermitize(hamiltonian))
    shifted = eigenvalues - np.min(eigenvalues)
    weights = np.exp(-beta * shifted)
    partition = float(np.sum(weights))
    rho = eigenvectors @ np.diag(weights / partition) @ eigenvectors.conj().T
    return hermitize(rho)


def spectral_projector(operator: np.ndarray, fraction: float, largest: bool = False) -> tuple[np.ndarray, np.ndarray]:
    eigenvalues, eigenvectors = eigh(hermitize(operator))
    count = max(1, int(math.ceil(len(eigenvalues) * fraction)))
    order = np.argsort(eigenvalues)
    if largest:
        selected = order[-count:]
    else:
        selected = order[:count]
    basis = eigenvectors[:, selected]
    projector = basis @ basis.conj().T
    return hermitize(projector), eigenvalues[selected]


def jordan_wigner_majoranas(n_majoranas: int) -> list[np.ndarray]:
    if n_majoranas % 2 != 0:
        raise ValueError("Number of Majoranas must be even.")
    n_qubits = n_majoranas // 2
    majoranas: list[np.ndarray] = []
    for qubit in range(n_qubits):
        z_prefix = [PAULI_Z] * qubit
        suffix = [IDENTITY_2] * (n_qubits - qubit - 1)
        gamma_x = kron_all([*z_prefix, PAULI_X, *suffix])
        gamma_y = kron_all([*z_prefix, PAULI_Y, *suffix])
        majoranas.append(gamma_x / math.sqrt(2.0))
        majoranas.append(gamma_y / math.sqrt(2.0))
    return majoranas


def syk_hamiltonian(majoranas: Sequence[np.ndarray], coupling_scale: float, rng: np.random.Generator) -> np.ndarray:
    n_majoranas = len(majoranas)
    dimension = majoranas[0].shape[0]
    hamiltonian = np.zeros((dimension, dimension), dtype=complex)
    variance = math.factorial(3) * (coupling_scale**2) / (n_majoranas**3)
    stddev = math.sqrt(variance)
    for j in range(n_majoranas - 3):
        for k in range(j + 1, n_majoranas - 2):
            for l in range(k + 1, n_majoranas - 1):
                for m in range(l + 1, n_majoranas):
                    coefficient = rng.normal(0.0, stddev)
                    term = majoranas[j] @ majoranas[k] @ majoranas[l] @ majoranas[m]
                    hamiltonian += coefficient * term
    return hermitize(hamiltonian)


def embed_side_operator(operator: np.ndarray, left_dim: int, right_dim: int, side: str) -> np.ndarray:
    if side == "L":
        return np.kron(operator, np.eye(right_dim, dtype=complex))
    if side == "R":
        return np.kron(np.eye(left_dim, dtype=complex), operator)
    raise ValueError(f"Unknown side: {side}")


def partial_trace_density(matrix: np.ndarray, dims: Sequence[int], keep: Sequence[int]) -> np.ndarray:
    dims = tuple(dims)
    keep = tuple(keep)
    trace_out = tuple(index for index in range(len(dims)) if index not in keep)
    reshaped = matrix.reshape(*dims, *dims)
    current_n = len(dims)
    for axis in sorted(trace_out, reverse=True):
        reshaped = np.trace(reshaped, axis1=axis, axis2=axis + current_n)
        current_n -= 1
    kept_dims = [dims[index] for index in keep]
    final_dim = int(np.prod(kept_dims)) if kept_dims else 1
    return reshaped.reshape(final_dim, final_dim)


def partial_trace_vector_density(vector: np.ndarray, dims: Sequence[int], keep: Sequence[int]) -> np.ndarray:
    density = np.outer(vector, vector.conj())
    return hermitize(partial_trace_density(density, dims, keep))


def random_isometry(target_dim: int, source_dim: int, rng: np.random.Generator) -> np.ndarray:
    raw = rng.normal(size=(target_dim, source_dim)) + 1j * rng.normal(size=(target_dim, source_dim))
    q_matrix, _ = np.linalg.qr(raw)
    return q_matrix[:, :source_dim]


def maximally_entangled_vector(dim: int) -> np.ndarray:
    omega = np.zeros(dim * dim, dtype=complex)
    for index in range(dim):
        omega[index * dim + index] = 1.0
    return omega / math.sqrt(dim)


def apply_operator_to_subsystem(vector: np.ndarray, operator: np.ndarray, dims: Sequence[int], target_index: int) -> np.ndarray:
    operators = [np.eye(dim, dtype=complex) for dim in dims]
    operators[target_index] = operator
    return kron_all(operators) @ vector


def apply_operator_to_tail(vector: np.ndarray, head_dim: int, operator: np.ndarray) -> np.ndarray:
    return np.kron(np.eye(head_dim, dtype=complex), operator) @ vector


def normalized_branch_density(kraus_operator: np.ndarray, state: np.ndarray) -> tuple[float, np.ndarray]:
    effect = hermitize(kraus_operator.conj().T @ kraus_operator)
    probability = clip_probability(float(np.real(np.trace(effect @ state))))
    if probability <= 0.0:
        return 0.0, np.zeros_like(state)
    branch = hermitize(kraus_operator @ state @ kraus_operator.conj().T)
    branch /= np.trace(branch)
    return probability, branch


def build_bilinear_operator(left_majoranas: Sequence[np.ndarray], right_majoranas: Sequence[np.ndarray]) -> np.ndarray:
    total = np.zeros((left_majoranas[0].shape[0] * right_majoranas[0].shape[0],) * 2, dtype=complex)
    n_majoranas = len(left_majoranas)
    left_dim = left_majoranas[0].shape[0]
    right_dim = right_majoranas[0].shape[0]
    for left_op, right_op in zip(left_majoranas, right_majoranas):
        total += 1j * np.kron(left_op, right_op)
    return hermitize(total / n_majoranas)


def heisenberg_evolve(operator: np.ndarray, eigenvalues: np.ndarray, eigenvectors: np.ndarray, time: float) -> np.ndarray:
    phases = np.exp(-1j * eigenvalues * time)
    unitary = eigenvectors @ np.diag(phases) @ eigenvectors.conj().T
    evolved = unitary.conj().T @ operator @ unitary
    return hermitize(evolved)


def operator_norm(matrix: np.ndarray) -> float:
    return float(np.linalg.norm(matrix, ord=2))


def main() -> None:
    script_path = Path(__file__).resolve()
    base_dir = script_path.parent
    results_dir = base_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(ISOMETRY_SEED)
    n_majoranas = DEFAULT_N_MAJORANAS_PER_SIDE
    left_majoranas_local = jordan_wigner_majoranas(n_majoranas)
    right_majoranas_local = jordan_wigner_majoranas(n_majoranas)
    left_dim = left_majoranas_local[0].shape[0]
    right_dim = right_majoranas_local[0].shape[0]

    # Shared disorder is intentional: both sides use the same deterministic coupling draw.
    disorder_rng = np.random.default_rng(DISORDER_SEED)
    h_left_local = syk_hamiltonian(left_majoranas_local, DEFAULT_J, disorder_rng)
    disorder_rng = np.random.default_rng(DISORDER_SEED)
    h_right_local = syk_hamiltonian(right_majoranas_local, DEFAULT_J, disorder_rng)

    left_majoranas = [embed_side_operator(op, left_dim, right_dim, "L") for op in left_majoranas_local]
    right_majoranas = [embed_side_operator(op, left_dim, right_dim, "R") for op in right_majoranas_local]

    h_left = embed_side_operator(h_left_local, left_dim, right_dim, "L")
    h_right = embed_side_operator(h_right_local, left_dim, right_dim, "R")
    correlation_operator = build_bilinear_operator(left_majoranas_local, right_majoranas_local)
    coupling_term = DEFAULT_MU * correlation_operator
    h_river = hermitize(h_left + h_right + coupling_term)
    h_uncoupled = hermitize(h_left + h_right)

    pi_1, energy_window = spectral_projector(h_uncoupled, DEFAULT_GUARD_ENERGY_FRACTION, largest=False)
    pi_2, correlation_window = spectral_projector(correlation_operator, DEFAULT_GUARD_CORRELATION_FRACTION, largest=True)

    success_map = pi_2 @ pi_1
    effect_forward = hermitize(success_map.conj().T @ success_map)
    effect_reverse = hermitize((pi_1 @ pi_2).conj().T @ (pi_1 @ pi_2))
    commutator_norm = operator_norm(pi_1 @ pi_2 - pi_2 @ pi_1)

    rho_beta = thermal_state(h_river, DEFAULT_BETA)
    p1 = clip_probability(float(np.real(np.trace(pi_1 @ rho_beta))))
    if p1 > 0.0:
        rho_after_pi1 = hermitize(pi_1 @ rho_beta @ pi_1) / p1
        p2_given_1 = clip_probability(float(np.real(np.trace(pi_2 @ rho_after_pi1))))
    else:
        rho_after_pi1 = np.zeros_like(rho_beta)
        p2_given_1 = 0.0
    p_success = clip_probability(float(np.real(np.trace(effect_forward @ rho_beta))))
    p_reverse = clip_probability(float(np.real(np.trace(effect_reverse @ rho_beta))))

    logical_dim = 2
    river_dim = left_dim * right_dim
    v_b = random_isometry(river_dim, logical_dim, rng)
    rho_encoded = hermitize(v_b @ (np.eye(logical_dim, dtype=complex) / logical_dim) @ v_b.conj().T)
    choi_seed = np.kron(np.eye(logical_dim, dtype=complex), success_map @ v_b)
    omega_ab = maximally_entangled_vector(logical_dim)
    choi_vector = choi_seed @ omega_ab
    choi_probability = float(np.vdot(choi_vector, choi_vector).real)
    encoded_forward_probability = clip_probability(float(np.real(np.trace(effect_forward @ rho_encoded))))
    choi_mismatch = abs(choi_probability - encoded_forward_probability)

    branch_probability, branch_rho = normalized_branch_density(success_map, rho_encoded)

    eigenvalues_river, eigenvectors_river = eigh(h_river)
    times = DEFAULT_TIME_GRID
    bilinear_left = hermitize(1j * left_majoranas[0] @ left_majoranas[1])
    bilinear_right = hermitize(1j * right_majoranas[0] @ right_majoranas[1])
    otoc_values = []
    for time in times:
        w_t = heisenberg_evolve(bilinear_right, eigenvalues_river, eigenvectors_river, float(time))
        otoc = np.trace(rho_beta @ w_t @ bilinear_left @ w_t @ bilinear_left)
        otoc_values.append(float(np.real_if_close(otoc)))

    guard_eigenvalues = np.linalg.eigvalsh(effect_forward)
    guard_eigenvalues = np.clip(np.real_if_close(guard_eigenvalues), 0.0, 1.0)
    active_guard_eigs = np.sort(guard_eigenvalues[guard_eigenvalues > 1e-12])[::-1]
    if active_guard_eigs.size == 0:
        active_guard_eigs = np.array([0.0])
    guard_angles = np.arccos(np.sqrt(np.clip(active_guard_eigs, 0.0, 1.0)))
    guard_barriers = np.array([safe_barrier(float(value)) for value in active_guard_eigs])

    a_dim = logical_dim
    d_dim = right_dim
    e_dim = left_dim
    total_dims = (a_dim, e_dim, d_dim)
    state_adjoined = np.kron(np.eye(a_dim, dtype=complex), v_b) @ omega_ab
    successful_vector = apply_operator_to_tail(state_adjoined, a_dim, success_map)
    success_norm = float(np.vdot(successful_vector, successful_vector).real)
    if success_norm > 0.0:
        successful_vector /= math.sqrt(success_norm)
    rho_ad = partial_trace_vector_density(successful_vector, total_dims, keep=(0, 2))
    rho_ae = partial_trace_vector_density(successful_vector, total_dims, keep=(0, 1))
    rho_a = partial_trace_vector_density(successful_vector, total_dims, keep=(0,))
    rho_d = partial_trace_vector_density(successful_vector, total_dims, keep=(2,))
    rho_e = partial_trace_vector_density(successful_vector, total_dims, keep=(1,))
    mutual_ad = matrix_entropy(rho_a) + matrix_entropy(rho_d) - matrix_entropy(rho_ad)
    mutual_ae = matrix_entropy(rho_a) + matrix_entropy(rho_e) - matrix_entropy(rho_ae)
    two_s_a = 2.0 * matrix_entropy(rho_a)
    balance_residual = abs((mutual_ad + mutual_ae) - two_s_a)

    guard_summary = pd.DataFrame(
        [
            {
                "seed": SEED,
                "disorder_seed": DISORDER_SEED,
                "isometry_seed": ISOMETRY_SEED,
                "n_majoranas_per_side": n_majoranas,
                "left_dim": left_dim,
                "right_dim": right_dim,
                "river_dim": river_dim,
                "beta": DEFAULT_BETA,
                "mu": DEFAULT_MU,
                "p1": p1,
                "p2_given_1": p2_given_1,
                "p_success": p_success,
                "barrier_p1": safe_barrier(p1),
                "barrier_p2_given_1": safe_barrier(p2_given_1),
                "barrier_success": safe_barrier(p_success),
                "p_reverse": p_reverse,
                "barrier_reverse": safe_barrier(p_reverse),
                "forward_minus_reverse": p_success - p_reverse,
                "commutator_norm": commutator_norm,
                "choi_success_probability": choi_probability,
                "encoded_forward_probability": encoded_forward_probability,
                "choi_probability_mismatch": choi_mismatch,
                "objective_forward_in_unit_interval": bool(TOL < p_success < 1.0 - TOL),
                "objective_noncommuting_guards": bool(commutator_norm > TOL),
                "objective_forward_reverse_gap": bool(abs(p_success - p_reverse) > TOL),
                "objective_choi_guard_match": bool(choi_mismatch <= 1e-9),
            }
        ]
    )
    guard_summary.to_csv(results_dir / "guard_summary.csv", index=False)

    guard_spectrum = pd.DataFrame(
        {
            "index": np.arange(active_guard_eigs.size),
            "lambda": active_guard_eigs,
            "theta": guard_angles,
            "barrier": guard_barriers,
        }
    )
    guard_spectrum.to_csv(results_dir / "guard_spectrum.csv", index=False)

    information_flow = pd.DataFrame(
        [
            {
                "success_probability": branch_probability,
                "I_A_D": mutual_ad,
                "I_A_E": mutual_ae,
                "two_S_A": two_s_a,
                "balance_residual": balance_residual,
                "information_balance_ok": bool(balance_residual <= 1e-8),
            }
        ]
    )
    information_flow.to_csv(results_dir / "information_flow.csv", index=False)

    otoc_df = pd.DataFrame({"time": times, "otoc": otoc_values})
    otoc_df.to_csv(results_dir / "otoc.csv", index=False)

    plt.figure(figsize=(7, 4))
    plt.plot(guard_spectrum["index"], guard_spectrum["barrier"], marker="o")
    plt.xlabel("Guard principal-angle mode")
    plt.ylabel("Barrier = -log(lambda)")
    plt.title("Guard barrier spectrum")
    plt.tight_layout()
    plt.savefig(results_dir / "guard_barrier_spectrum.png", dpi=160)
    plt.close()

    plt.figure(figsize=(6, 4))
    labels = ["I(A:D)", "I(A:E)", "2 S(A)"]
    values = [mutual_ad, mutual_ae, two_s_a]
    plt.bar(labels, values, color=["#4c72b0", "#dd8452", "#55a868"])
    plt.ylabel("Nats")
    plt.title("Conditioned information balance")
    plt.tight_layout()
    plt.savefig(results_dir / "information_balance.png", dpi=160)
    plt.close()

    plt.figure(figsize=(7, 4))
    plt.plot(times, otoc_values, marker="o")
    plt.xlabel("time")
    plt.ylabel("Tr[rho_beta W(t) V W(t) V] (Hermitian OTOC)")
    plt.title("Transit Hermitian-bilinear OTOC")
    plt.tight_layout()
    plt.savefig(results_dir / "otoc_growth.png", dpi=160)
    plt.close()

    print(f"Physical dimensions: river={river_dim}, left={left_dim}, right={right_dim}")
    print(f"Forward guards: p1={p1:.10f}, p2|1={p2_given_1:.10f}, p_success={p_success:.10f}")
    print(
        "Forward barriers: "
        f"B1={safe_barrier(p1):.10f}, B2|1={safe_barrier(p2_given_1):.10f}, Bsuccess={safe_barrier(p_success):.10f}"
    )
    print(
        f"Reverse guard: p_reverse={p_reverse:.10f}, barrier={safe_barrier(p_reverse):.10f}, "
        f"forward-minus-reverse={p_success - p_reverse:.10f}"
    )
    print(f"Guard commutator norm: {commutator_norm:.10e}")
    print(
        f"Choi success probability: {choi_probability:.10f}; "
        f"encoded guard probability: {encoded_forward_probability:.10f}; mismatch={choi_mismatch:.3e}"
    )
    print(
        f"Objective checks: 0<p_success<1 -> {0.0 < p_success < 1.0}; "
        f"||[Pi1,Pi2]||>tol -> {commutator_norm > TOL}; "
        f"|p_forward-p_reverse|>tol -> {abs(p_success - p_reverse) > TOL}; "
        f"Choi/Guard match -> {choi_mismatch <= 1e-9}; "
        f"balance residual <= 1e-8 -> {balance_residual <= 1e-8}"
    )
    print(f"Information balance max residual: {balance_residual:.3e}")
    print(f"Results path: {results_dir}")
    print(
        "Conditioned branch note: I(A:D)+I(A:E)=2S(A) is expected for the normalized successful pure branch; "
        "state-independent heralding is not assumed."
    )
    print(
        f"Guard windows: low-energy eigenvalue range [{energy_window.min():.6f}, {energy_window.max():.6f}], "
        f"high-correlation range [{correlation_window.min():.6f}, {correlation_window.max():.6f}]"
    )


if __name__ == "__main__":
    main()
