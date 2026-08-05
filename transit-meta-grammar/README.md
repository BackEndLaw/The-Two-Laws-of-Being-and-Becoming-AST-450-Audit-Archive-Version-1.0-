# Transit Meta-Grammar MVP

This directory contains a focused, runnable finite-
`N` two-sided coupled-SYK Transit MVP.

## Setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r transit-meta-grammar/requirements.txt
```

## Run

From the subdirectory:

```bash
cd transit-meta-grammar
python transit_syk.py
```

From the repository root:

```bash
python transit-meta-grammar/transit_syk.py
```

The script derives its output directory from `__file__`, so both invocations write to `transit-meta-grammar/results/`.

## Generated artifacts

Runtime creates `transit-meta-grammar/results/` and writes:

- `guard_summary.csv` — scalar guard probabilities, barriers, commutator norm, Choi/guard comparison, and runtime objective flags.
- `guard_spectrum.csv` — eigenvalue spectrum of the forward effect `E_forward = K^dagger K = Pi_1 Pi_2 Pi_1`, reported as `lambda = cos^2(theta)` with principal angles and barrier values.
- `information_flow.csv` — conditioned successful-branch information quantities `I(A:D)`, `I(A:E)`, `2S(A)`, and the residual in the pure-state balance identity.
- `otoc.csv` — exact finite-dimensional Hermitian-bilinear OTOC samples over the configured time grid.
- `guard_barrier_spectrum.png` — plot of guard spectral barrier values.
- `information_balance.png` — bar chart comparing `I(A:D)`, `I(A:E)`, and `2S(A)` after conditioning.
- `otoc_growth.png` — OTOC trajectory under exact time evolution.

Generated CSV and PNG outputs are saved under `transit-meta-grammar/results/` in this repository and may be committed when you want to preserve a deterministic run.

## Mathematical definitions

Let the River Hilbert space be `H_River = H_L \otimes H_R`, with `N=6` Majoranas per side, Jordan-Wigner Majoranas normalized as `chi = gamma / sqrt(2)`, and shared-disorder `q=4` SYK Hamiltonians on the two sides (the deterministic realization intentionally reuses the same coupling draw for left and right). The coupled River Hamiltonian is

```text
H_River = H_L + H_R + i mu sum_j chi_L^j chi_R^j.
```

The low-energy Guard is the spectral projector

```text
Pi_1 = projector onto a low-energy band of H_L + H_R,
```

and the high-correlation Guard is the spectral projector

```text
Pi_2 = projector onto a high-eigenvalue band of C_LR = (i/N) sum_j chi_L^j chi_R^j.
```

The ordered forward success map is `K = Pi_2 Pi_1`, with forward effect

```text
E_forward = Pi_1 Pi_2 Pi_1,
```

while the reverse effect is

```text
E_reverse = Pi_2 Pi_1 Pi_2.
```

A random logical-qubit isometric encoding `V_B` embeds a two-dimensional code space into `H_River`. For the maximally entangled reference state `|Omega> = d^{-1/2} sum_a |a>_A |a>_B`, the successful Choi branch is

```text
|Psi_success> = (I_A tensor K V_B) |Omega>.
```

The script reports the Choi branch norm and compares it against the forward-Guard probability of the encoded maximally mixed state. After conditioning on success and normalizing, the branch is pure, so the identity `I(A:D) + I(A:E) = 2S(A)` is expected for the chosen partition; this does not assume state-independent heralding.

## Scope note

This MVP establishes a finite-dimensional, deterministic pipeline for the coupled-SYK Transit construction, exact evolution, guard ordering diagnostics, Choi-branch checks, and information-flow reporting. It does **not** by itself establish the logarithmic recovery-law hypothesis.

A follow-up sweep should vary `N`, `beta`, `mu`, guard fractions, and seed; use a persistence-window recovery threshold; compare logarithmic and inverse-power retry-law fits; and include uncoupled, free-fermion, and commuting-Guard controls.
