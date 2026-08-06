from __future__ import annotations


def expected_utility(
    recovery_probability: float,
    expected_cost: float,
    expected_harm: float,
    unsafe_probability: float,
    *,
    lambda_cost: float,
    beta_harm: float,
    gamma_unsafe: float,
) -> float:
    return (
        recovery_probability
        - lambda_cost * expected_cost
        - beta_harm * expected_harm
        - gamma_unsafe * unsafe_probability
    )


def value_of_information(
    expected_best_with_evidence: float,
    expected_best_without_evidence: float,
    evidence_cost: float,
) -> float:
    return expected_best_with_evidence - expected_best_without_evidence - evidence_cost
