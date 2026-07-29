from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import replace
import json
import math
from pathlib import Path
import random
import statistics
from typing import Any, Iterable

from rescueos.adapters.simulator import SimulatorAdapter
from rescueos.audit.event_log import AuditEventLog
from rescueos.compiler.graph_compiler import compile_graph
from rescueos.compiler.loader import load_system_spec
from rescueos.core.belief import SimpleBeliefUpdater
from rescueos.core.controller import RescueController, RescueResult
from rescueos.core.distinctions import ActionOutcome, Intervention
from rescueos.core.planner import BoundedLookaheadPlanner, PlannerConfig
from rescueos.core.transition import TransitionModel
from rescueos.experiments.hidden_transfer import (
    fit_end_to_end_weights,
    iter_scenarios,
    load_manifest,
    scenario_faults,
    validate_manifests,
    verify_hidden_lock,
)
from rescueos.policies import greedy, qrtc, qrtc_untyped
from rescueos.policies.end_to_end import LearnedEndToEndPolicy
from rescueos.policies.random_policy import RandomPolicy
from rescueos.simulator.communication_link import CommunicationLinkSimulator


POLICIES = (
    "qrtc",
    "qrtc_untyped",
    "end_to_end",
    "greedy_expected_gain",
    "random",
    "oracle",
)
COMPARATORS = ("qrtc_untyped", "end_to_end", "greedy_expected_gain", "random")
BREAKDOWNS = (
    "mechanism_split",
    "mechanism_family",
    "affected_stage",
    "fault_count",
    "severity",
    "severity_band",
    "observation_noise",
    "intervention_reliability",
)
DISTINCTION_STAGES = {
    "symbol_identity": "source",
    "encoded_amplitude": "transmitter",
    "encoded_phase": "transmitter",
    "timing": "transmitter",
    "received_amplitude": "channel",
    "received_phase": "channel",
    "symbol_estimate": "receiver",
    "confidence": "receiver",
    "decoded_message": "decision",
}


class NoisyPolicyAdapter(SimulatorAdapter):
    def __init__(self, simulator, *, noise: float, seed: int, oracle: bool) -> None:
        super().__init__(simulator, oracle_observations=oracle)
        self._noise = noise
        self._rng = random.Random(seed + 700_001)

    def observe(self) -> dict:
        observation = super().observe()
        if self._noise <= 0.0 or "distinction_health" not in observation:
            return observation
        noisy = dict(observation)
        noisy["distinction_health"] = {
            name: min(1.0, max(0.0, float(value) + self._rng.gauss(0.0, self._noise)))
            for name, value in observation["distinction_health"].items()
        }
        return noisy

    def apply(self, action_id: str) -> ActionOutcome:
        outcome = super().apply(action_id)
        return replace(outcome, observation={})


def _configured_interventions(
    interventions: Iterable[Intervention], reliability: float
) -> list[Intervention]:
    return [
        replace(
            action,
            success_probability=min(1.0, action.success_probability * reliability),
        )
        for action in interventions
    ]


def _scenario_metadata(
    mechanism: dict[str, Any], scenario: dict[str, Any], split: str
) -> dict[str, Any]:
    faults = scenario["faults"]
    affected = {
        DISTINCTION_STAGES.get(name, "unknown")
        for fault in faults
        for name in fault["affected_distinctions"]
    }
    mean_severity = statistics.fmean(float(fault["severity"]) for fault in faults)
    severity_band = "low" if mean_severity < 0.35 else "medium" if mean_severity < 0.5 else "high"
    family = str(mechanism["mechanism_id"])
    for prefix in ("dev_", "hidden_"):
        if family.startswith(prefix):
            family = family[len(prefix) :]
    return {
        "mechanism_split": "known" if split == "development" else "hidden",
        "mechanism_family": family,
        "affected_stage": "+".join(sorted(affected)),
        "fault_count": len(faults),
        "severity": mean_severity,
        "severity_band": severity_band,
    }


def build_development_trials(
    development: dict[str, Any],
    hidden: dict[str, Any],
    *,
    replicates: int,
    noise_levels: tuple[float, ...],
    reliability_levels: tuple[float, ...],
) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    config_index = 0
    for manifest in (development, hidden):
        split = str(manifest["split"])
        for mechanism in manifest["mechanisms"]:
            for scenario in mechanism["scenarios"]:
                metadata = _scenario_metadata(mechanism, scenario, split)
                for noise in noise_levels:
                    for reliability in reliability_levels:
                        cluster_id = (
                            f"{split}:{mechanism['mechanism_id']}:{scenario['scenario_id']}:"
                            f"n{noise:.3f}:r{reliability:.3f}"
                        )
                        for replicate in range(replicates):
                            trials.append(
                                {
                                    **scenario,
                                    **metadata,
                                    "mechanism_id": mechanism["mechanism_id"],
                                    "cluster_id": cluster_id,
                                    "replicate": replicate,
                                    "trial_seed": int(scenario["seed"]) + 10_000 * config_index + replicate,
                                    "observation_noise": noise,
                                    "intervention_reliability": reliability,
                                }
                            )
                        config_index += 1
    return trials


def _policy(
    name: str,
    interventions: list[Intervention],
    graph,
    weights: dict[str, dict[str, float]],
    seed: int,
):
    if name == "qrtc":
        return qrtc.build_policy(interventions, graph=graph)
    if name == "qrtc_untyped":
        return qrtc_untyped.build_policy(interventions)
    if name == "end_to_end":
        return LearnedEndToEndPolicy(interventions, weights)
    if name == "greedy_expected_gain":
        return greedy.build_policy(interventions)
    if name == "random":
        return RandomPolicy(interventions, seed=seed + 900_001)
    return BoundedLookaheadPlanner(
        interventions,
        config=PlannerConfig(lambda_cost=0.0, beta_harm=0.0, gamma_unsafe=0.0),
        graph=graph,
    )


def _run_policy(
    name: str,
    trial: dict[str, Any],
    base_interventions: list[Intervention],
    task,
    graph,
    weights: dict[str, dict[str, float]],
    max_actions: int,
) -> tuple[RescueResult, AuditEventLog]:
    interventions = _configured_interventions(
        base_interventions, float(trial["intervention_reliability"])
    )
    transition = TransitionModel(graph)
    simulator = CommunicationLinkSimulator(
        interventions,
        seed=int(trial["trial_seed"]),
        faults=scenario_faults(trial),
        graph=graph,
        transition_model=transition,
    )
    audit_log = AuditEventLog()
    controller = RescueController(
        adapter=NoisyPolicyAdapter(
            simulator,
            noise=float(trial["observation_noise"]),
            seed=int(trial["trial_seed"]),
            oracle=name == "oracle",
        ),
        inference=SimpleBeliefUpdater(),
        planner=_policy(name, interventions, graph, weights, int(trial["trial_seed"])),
        audit_log=audit_log,
    )
    return controller.rescue(task, max_actions=max_actions), audit_log


def _row(
    name: str,
    trial: dict[str, Any],
    result: RescueResult,
    audit_log: AuditEventLog,
    evidence_action_ids: set[str],
    *,
    lambda_cost: float,
    eta_actions: float,
    beta_harm: float,
) -> dict[str, Any]:
    total_cost = sum(float(outcome.cost) for outcome in result.history)
    total_harm = sum(float(outcome.harm) for outcome in result.history)
    unsafe = float(any(bool(outcome.unsafe) for outcome in result.history))
    utility = (
        float(result.status == "recovered")
        - lambda_cost * total_cost
        - eta_actions * result.actions_executed
        - beta_harm * total_harm
    )
    return {
        **{key: trial[key] for key in BREAKDOWNS},
        "mechanism_id": trial["mechanism_id"],
        "scenario_id": trial["scenario_id"],
        "cluster_id": trial["cluster_id"],
        "replicate": trial["replicate"],
        "seed": trial["trial_seed"],
        "policy": name,
        "selected_actions": [outcome.action_id for outcome in result.history],
        "first_action": result.history[0].action_id if result.history else "stop",
        "first_predicted_recovery": (
            float(audit_log.decisions[0]["decision"]["expected_recovery_probability"])
            if audit_log.decisions
            else 0.0
        ),
        "first_predicted_utility": (
            float(audit_log.decisions[0]["decision"]["expected_utility"])
            if audit_log.decisions
            else 0.0
        ),
        "utility": utility,
        "recovered": float(result.status == "recovered"),
        "cost": total_cost,
        "harm": total_harm,
        "unsafe_event": unsafe,
        "abstain_event": float(result.status == "abstained"),
        "evidence_requests": sum(
            outcome.action_id in evidence_action_ids for outcome in result.history
        ),
        "action_count": result.actions_executed,
    }


def _counterfactual_probes(
    trial: dict[str, Any],
    base_interventions: list[Intervention],
    task,
    graph,
    *,
    lambda_cost: float,
    beta_harm: float,
    gamma_unsafe: float,
) -> list[dict[str, Any]]:
    interventions = _configured_interventions(
        base_interventions, float(trial["intervention_reliability"])
    )
    initial_simulator = CommunicationLinkSimulator(
        interventions,
        seed=int(trial["trial_seed"]),
        faults=scenario_faults(trial),
        graph=graph,
    )
    initial_adapter = NoisyPolicyAdapter(
        initial_simulator,
        noise=float(trial["observation_noise"]),
        seed=int(trial["trial_seed"]),
        oracle=False,
    )
    observation = initial_adapter.observe()
    belief = SimpleBeliefUpdater().update(observation, [], task)
    planner = qrtc.build_policy(interventions, graph=graph)
    action_by_id = {action.action_id: action for action in interventions}
    probes: list[dict[str, Any]] = []
    for prediction in planner.predict_actions(belief, task):
        if not bool(prediction["graph_admissible"]):
            continue
        action_id = str(prediction["action_id"])
        action = action_by_id[action_id]
        simulator = CommunicationLinkSimulator(
            interventions,
            seed=int(trial["trial_seed"]),
            faults=scenario_faults(trial),
            graph=graph,
        )
        outcome = simulator.apply(action_id)
        realized_recovery = float(simulator.evaluate_task(task) <= task.recovery_threshold)
        realized_utility = (
            realized_recovery
            - lambda_cost * action.cost
            - beta_harm * float(outcome.harm)
            - gamma_unsafe * float(outcome.unsafe)
        )
        probes.append(
            {
                "mechanism_family": trial["mechanism_family"],
                "mechanism_split": trial["mechanism_split"],
                "cluster_id": trial["cluster_id"],
                "replicate": trial["replicate"],
                "action_id": action_id,
                "action_kind": prediction["action_kind"],
                "graph_admissible": True,
                "public_observation": {
                    "distinction_health": dict(observation["distinction_health"]),
                    "confidence": float(observation["confidence"]),
                    "unknown_probability": float(observation["unknown_probability"]),
                },
                "predicted_recovery": float(prediction["predicted_recovery"]),
                "realized_recovery": realized_recovery,
                "predicted_utility": float(prediction["predicted_utility"]),
                "realized_utility": realized_utility,
                "utility_error": float(prediction["predicted_utility"]) - realized_utility,
            }
        )
    return probes


def _calibration_metrics(probes: list[dict[str, Any]]) -> dict[str, Any]:
    def summarize(selected: list[dict[str, Any]]) -> dict[str, float]:
        brier = statistics.fmean(
            (float(row["predicted_recovery"]) - float(row["realized_recovery"])) ** 2
            for row in selected
        )
        utility_errors = [float(row["utility_error"]) for row in selected]
        bins: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in selected:
            bins[min(9, int(float(row["predicted_recovery"]) * 10))].append(row)
        calibration_curve = [
            {
                "bin": index,
                "count": len(group),
                "mean_predicted": statistics.fmean(float(row["predicted_recovery"]) for row in group),
                "mean_realized": statistics.fmean(float(row["realized_recovery"]) for row in group),
            }
            for index, group in sorted(bins.items())
        ]
        ece = sum(
            item["count"] / len(selected)
            * abs(item["mean_predicted"] - item["mean_realized"])
            for item in calibration_curve
        )
        return {
            "count": float(len(selected)),
            "brier_score": brier,
            "expected_calibration_error": ece,
            "mean_utility_error": statistics.fmean(utility_errors),
            "mean_absolute_utility_error": statistics.fmean(abs(value) for value in utility_errors),
        }

    by_family = {
        family: summarize([row for row in probes if row["mechanism_family"] == family])
        for family in sorted({str(row["mechanism_family"]) for row in probes})
    }
    overall = summarize(probes)
    bins: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in probes:
        bins[min(9, int(float(row["predicted_recovery"]) * 10))].append(row)
    curve = [
        {
            "bin": index,
            "count": len(group),
            "mean_predicted": statistics.fmean(float(row["predicted_recovery"]) for row in group),
            "mean_realized": statistics.fmean(float(row["realized_recovery"]) for row in group),
        }
        for index, group in sorted(bins.items())
    ]
    return {"overall": overall, "by_mechanism_family": by_family, "calibration_curve": curve}


def _utility_deficit(
    rows: list[dict[str, Any]],
    baseline: str,
    *,
    lambda_cost: float,
    eta_actions: float,
    beta_harm: float,
    gamma_unsafe: float,
) -> list[dict[str, Any]]:
    output = []
    for mechanism in sorted({str(row["mechanism_id"]) for row in rows}):
        qrtc_rows = [row for row in rows if row["mechanism_id"] == mechanism and row["policy"] == "qrtc"]
        baseline_rows = [row for row in rows if row["mechanism_id"] == mechanism and row["policy"] == baseline]
        delta_recovery = statistics.fmean(row["recovered"] for row in qrtc_rows) - statistics.fmean(row["recovered"] for row in baseline_rows)
        delta_cost = statistics.fmean(row["cost"] for row in qrtc_rows) - statistics.fmean(row["cost"] for row in baseline_rows)
        delta_harm = statistics.fmean(row["harm"] for row in qrtc_rows) - statistics.fmean(row["harm"] for row in baseline_rows)
        delta_unsafe = statistics.fmean(row["unsafe_event"] for row in qrtc_rows) - statistics.fmean(row["unsafe_event"] for row in baseline_rows)
        delta_actions = statistics.fmean(row["action_count"] for row in qrtc_rows) - statistics.fmean(row["action_count"] for row in baseline_rows)
        output.append(
            {
                "mechanism_id": mechanism,
                "baseline": baseline,
                "delta_recovery": delta_recovery,
                "delta_cost": delta_cost,
                "delta_harm": delta_harm,
                "delta_unsafe": delta_unsafe,
                "delta_action_count": delta_actions,
                "recovery_component": delta_recovery,
                "cost_component": -lambda_cost * delta_cost,
                "harm_component": -beta_harm * delta_harm,
                "unsafe_component": -gamma_unsafe * delta_unsafe,
                "action_component": -eta_actions * delta_actions,
                "safety_adjusted_delta_utility": (
                    delta_recovery
                    - lambda_cost * delta_cost
                    - beta_harm * delta_harm
                    - gamma_unsafe * delta_unsafe
                    - eta_actions * delta_actions
                ),
                "qrtc_evidence_requests": statistics.fmean(row["evidence_requests"] for row in qrtc_rows),
                "qrtc_abstention_rate": statistics.fmean(row["abstain_event"] for row in qrtc_rows),
                "qrtc_oracle_regret": statistics.fmean(row["oracle_regret"] for row in qrtc_rows),
            }
        )
    return output


def _means(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {
        field: statistics.fmean(float(row[field]) for row in rows)
        for field in (
            "utility",
            "recovered",
            "cost",
            "harm",
            "unsafe_event",
            "abstain_event",
            "oracle_regret",
        )
    }


def summarize(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    overall = []
    for policy in POLICIES:
        selected = [row for row in rows if row["policy"] == policy]
        overall.append({"policy": policy, "n_trials": len(selected), **_means(selected)})
    breakdowns: dict[str, list[dict[str, Any]]] = {}
    for dimension in BREAKDOWNS:
        grouped: dict[tuple[Any, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[(row[dimension], row["policy"])].append(row)
        breakdowns[dimension] = [
            {dimension: value, "policy": policy, "n_trials": len(group), **_means(group)}
            for (value, policy), group in sorted(grouped.items(), key=lambda item: str(item[0]))
        ]
    return overall, breakdowns


def cluster_differences(
    rows: list[dict[str, Any]], policy: str, baseline: str
) -> dict[str, float]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row["cluster_id"], row["policy"])].append(float(row["utility"]))
    clusters = sorted({cluster for cluster, _ in grouped})
    return {
        cluster: statistics.fmean(grouped[(cluster, policy)])
        - statistics.fmean(grouped[(cluster, baseline)])
        for cluster in clusters
    }


def cluster_bootstrap(
    differences: dict[str, float], *, samples: int, seed: int
) -> dict[str, float]:
    values = list(differences.values())
    rng = random.Random(seed)
    draws = sorted(
        statistics.fmean(rng.choice(values) for _ in values) for _ in range(samples)
    )
    return {
        "estimate": statistics.fmean(values),
        "lower_95": draws[int(0.025 * samples)],
        "upper_95": draws[min(samples - 1, int(0.975 * samples))],
        "half_width": (draws[min(samples - 1, int(0.975 * samples))] - draws[int(0.025 * samples)]) / 2.0,
    }


def _width_diagnostics(
    rows: list[dict[str, Any]], differences: dict[str, float], target_half_width: float
) -> dict[str, Any]:
    cluster_sizes: dict[str, int] = defaultdict(int)
    for row in rows:
        if row["policy"] == "qrtc":
            cluster_sizes[row["cluster_id"]] += 1
    sizes = list(cluster_sizes.values())
    values = list(differences.values())
    standard_deviation = statistics.stdev(values) if len(values) > 1 else 0.0
    prospective_clusters = (
        math.ceil((1.96 * standard_deviation / target_half_width) ** 2)
        if target_half_width > 0.0
        else len(values)
    )
    mechanism_effects: dict[str, list[float]] = defaultdict(list)
    mechanism_by_cluster = {
        row["cluster_id"]: row["mechanism_id"] for row in rows if row["policy"] == "qrtc"
    }
    for cluster, difference in differences.items():
        mechanism_effects[mechanism_by_cluster[cluster]].append(difference)
    end_to_end_values = [float(row["utility"]) for row in rows if row["policy"] == "end_to_end"]
    return {
        "matched_trial_count": sum(sizes),
        "independent_cluster_count": len(sizes),
        "cluster_size_distribution": {
            "minimum": min(sizes),
            "median": statistics.median(sizes),
            "maximum": max(sizes),
            "sizes": sorted(sizes),
        },
        "paired_cluster_difference_sd": standard_deviation,
        "per_mechanism_effects": {
            mechanism: statistics.fmean(effect) for mechanism, effect in sorted(mechanism_effects.items())
        },
        "width_drivers": {
            "too_few_independent_clusters": len(sizes) < 30,
            "highly_unequal_cluster_sizes": max(sizes) > 1.5 * min(sizes),
            "rare_high_impact_outcomes": bool(standard_deviation and max(abs(value) for value in values) > 2.5 * standard_deviation),
            "heterogeneity_across_mechanisms": len({round(statistics.fmean(effect), 3) for effect in mechanism_effects.values()}) > 1,
            "unstable_end_to_end_behavior": statistics.pstdev(end_to_end_values) > 0.25,
            "correlated_random_streams": False,
        },
        "common_random_numbers": True,
        "random_stream_note": "Common trial seeds are intentional for paired comparisons; RNG state is isolated in one simulator instance per policy.",
        "prospective_cluster_count_for_target_half_width": max(len(values), prospective_clusters),
        "target_half_width": target_half_width,
    }


def run_development_benchmark(
    spec_path: str | Path,
    development_path: str | Path,
    hidden_path: str | Path,
    lock_path: str | Path,
    *,
    replicates: int = 8,
    noise_levels: tuple[float, ...] = (0.0, 0.05),
    reliability_levels: tuple[float, ...] = (0.8, 1.0),
    max_actions: int = 4,
    bootstrap_samples: int = 2000,
    bootstrap_seed: int = 450,
    target_half_width: float = 0.10,
    lambda_cost: float = 0.05,
    eta_actions: float = 0.02,
    beta_harm: float = 0.25,
    gamma_unsafe: float = 0.2,
) -> dict[str, Any]:
    development = load_manifest(development_path)
    hidden = load_manifest(hidden_path)
    validate_manifests(development, hidden)
    verify_hidden_lock(hidden_path, lock_path)
    spec = load_system_spec(spec_path)
    graph = compile_graph(spec)
    task = spec.tasks[0]
    interventions = list(spec.interventions)
    weights = fit_end_to_end_weights(development, interventions, task, graph)
    trial_specs = build_development_trials(
        development,
        hidden,
        replicates=replicates,
        noise_levels=noise_levels,
        reliability_levels=reliability_levels,
    )
    evidence_action_ids = {
        action.action_id for action in interventions if action.kind.value == "evidence"
    }
    rows: list[dict[str, Any]] = []
    for trial in trial_specs:
        for policy in POLICIES:
            result, audit_log = _run_policy(
                policy,
                trial,
                interventions,
                task,
                graph,
                weights,
                max_actions,
            )
            rows.append(
                _row(
                    policy,
                    trial,
                    result,
                    audit_log,
                    evidence_action_ids,
                    lambda_cost=lambda_cost,
                    eta_actions=eta_actions,
                    beta_harm=beta_harm,
                )
            )
    oracle_utility = {
        (row["cluster_id"], row["replicate"]): row["utility"]
        for row in rows
        if row["policy"] == "oracle"
    }
    for row in rows:
        signed_gap = oracle_utility[(row["cluster_id"], row["replicate"])] - row["utility"]
        row["signed_oracle_gap"] = signed_gap
        row["oracle_regret"] = max(0.0, signed_gap)
    oracle_first_actions = {
        (row["cluster_id"], row["replicate"]): row["first_action"]
        for row in rows
        if row["policy"] == "oracle"
    }
    qrtc_probes = [
        probe
        for trial in trial_specs
        for probe in _counterfactual_probes(
            trial,
            interventions,
            task,
            graph,
            lambda_cost=lambda_cost,
            beta_harm=beta_harm,
            gamma_unsafe=gamma_unsafe,
        )
    ]
    admissible_actions = {
        (probe["cluster_id"], probe["replicate"], probe["action_id"])
        for probe in qrtc_probes
    }
    for row in rows:
        oracle_action = oracle_first_actions[(row["cluster_id"], row["replicate"])]
        row["oracle_first_action"] = oracle_action
        row["first_action_accuracy"] = float(row["first_action"] == oracle_action)
        row["graph_coverage_error"] = float(
            row["policy"] == "qrtc"
            and oracle_action != "stop"
            and (row["cluster_id"], row["replicate"], oracle_action)
            not in admissible_actions
        )
    overall, breakdowns = summarize(rows)
    mean_utility = {row["policy"]: row["utility"] for row in overall}
    strongest = max(COMPARATORS, key=lambda policy: mean_utility[policy])
    primary_differences = cluster_differences(rows, "qrtc", strongest)
    typed_differences = cluster_differences(rows, "qrtc", "qrtc_untyped")
    primary_interval = cluster_bootstrap(primary_differences, samples=bootstrap_samples, seed=bootstrap_seed)
    typed_interval = cluster_bootstrap(typed_differences, samples=bootstrap_samples, seed=bootstrap_seed + 1)
    diagnostics = _width_diagnostics(rows, primary_differences, target_half_width)
    action_distribution: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        if row["policy"] == "qrtc":
            action_distribution[row["mechanism_id"]][row["first_action"]] += 1
    diagnostics["qrtc_selected_action_distribution"] = {
        mechanism: dict(sorted(counts.items()))
        for mechanism, counts in sorted(action_distribution.items())
    }
    diagnostics["qrtc_first_action_accuracy"] = statistics.fmean(
        row["first_action_accuracy"] for row in rows if row["policy"] == "qrtc"
    )
    diagnostics["qrtc_graph_coverage_error_rate"] = statistics.fmean(
        row["graph_coverage_error"] for row in rows if row["policy"] == "qrtc"
    )
    diagnostics["counterfactual_calibration"] = _calibration_metrics(qrtc_probes)
    diagnostics["counterfactual_probe_count"] = len(qrtc_probes)
    utility_deficit = _utility_deficit(
        rows,
        strongest,
        lambda_cost=lambda_cost,
        eta_actions=eta_actions,
        beta_harm=beta_harm,
        gamma_unsafe=gamma_unsafe,
    )
    qrtc_domains = [row for dimension in breakdowns.values() for row in dimension if row["policy"] == "qrtc"]
    acceptance = {
        "aggregate_advantage_positive": primary_interval["estimate"] > 0.0,
        "interval_sufficiently_precise": primary_interval["half_width"] <= target_half_width,
        "no_catastrophic_domain": all(row["utility"] > -0.5 for row in qrtc_domains),
        "typed_beats_or_complements_untyped": typed_interval["estimate"] >= 0.0,
        "safety_within_frozen_thresholds": (
            next(row for row in overall if row["policy"] == "qrtc")["unsafe_event"] <= 0.05
            and next(row for row in overall if row["policy"] == "qrtc")["harm"] <= 0.05
        ),
        "not_concentrated_in_one_family": sum(
            value > 0.0 for value in diagnostics["per_mechanism_effects"].values()
        )
        >= max(2, math.ceil(len(diagnostics["per_mechanism_effects"]) / 2)),
        "leakage_tests_required": True,
    }
    acceptance["proceed_to_fresh_validation"] = all(acceptance.values())
    return {
        "artifact_type": "hidden_mechanism_development_benchmark",
        "experiment_class": "development_not_validation",
        "policies": list(POLICIES),
        "matched_trial_count": len(trial_specs),
        "total_policy_runs": len(rows),
        "strongest_nonoracle": strongest,
        "primary_delta_u_hidden": primary_interval,
        "delta_u_typed_minus_untyped": typed_interval,
        "bootstrap": {
            "method": "paired cluster bootstrap",
            "cluster_definition": "mechanism/scenario/noise/reliability configuration",
            "resamples": bootstrap_samples,
            "seed": bootstrap_seed,
        },
        "utility_weights": {
            "lambda_cost": lambda_cost,
            "eta_actions": eta_actions,
            "beta_harm": beta_harm,
            "gamma_unsafe": gamma_unsafe,
        },
        "frozen_safety_thresholds": {"maximum_unsafe_rate": 0.05, "maximum_harm_rate": 0.05},
        "overall": overall,
        "breakdowns": breakdowns,
        "precision_diagnostics": diagnostics,
        "utility_deficit_by_mechanism": utility_deficit,
        "counterfactual_action_probes": qrtc_probes,
        "development_acceptance": acceptance,
        "hardware_actuation_enabled": False,
        "hardware_gate": "NOT READY",
        "trials": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the hidden-mechanism development benchmark")
    parser.add_argument("--spec", default="configs/communication_system.yaml")
    parser.add_argument("--development", default="configs/development_mechanisms.json")
    parser.add_argument("--hidden", default="configs/hidden_mechanisms.json")
    parser.add_argument("--lock", default="configs/hidden_mechanisms.lock.json")
    parser.add_argument("--output", default="artifacts/phase6/HIDDEN_MECHANISM_DEVELOPMENT_BENCHMARK.json")
    parser.add_argument("--replicates", type=int, default=8)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=450)
    args = parser.parse_args()
    payload = run_development_benchmark(
        args.spec,
        args.development,
        args.hidden,
        args.lock,
        replicates=args.replicates,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()