from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import statistics
from typing import Any

from rescueos.adapters.simulator import SimulatorAdapter
from rescueos.audit.event_log import AuditEventLog
from rescueos.compiler.graph_compiler import compile_graph
from rescueos.compiler.loader import load_system_spec
from rescueos.core.belief import SimpleBeliefUpdater
from rescueos.core.controller import RescueController
from rescueos.core.planner import BoundedLookaheadPlanner, PlannerConfig
from rescueos.core.transition import TransitionModel
from rescueos.experiments.development_benchmark import (
    NoisyPolicyAdapter,
    _configured_interventions,
    _counterfactual_probes,
    _row,
    build_development_trials,
)
from rescueos.experiments.hidden_transfer import (
    fit_end_to_end_weights,
    load_manifest,
    scenario_faults,
    validate_manifests,
    verify_hidden_lock,
)
from rescueos.policies import greedy, qrtc, qrtc_untyped
from rescueos.policies.end_to_end import LearnedEndToEndPolicy
from rescueos.policies.hybrid_qrtc import HybridQRTCPolicy, LearnedResidualActionModel
from rescueos.simulator.communication_link import CommunicationLinkSimulator


POLICIES = (
    "qrtc",
    "hybrid_qrtc",
    "qrtc_untyped",
    "end_to_end",
    "greedy_expected_gain",
    "oracle",
)
COMPARATORS = ("qrtc", "qrtc_untyped", "end_to_end", "greedy_expected_gain")


def _combined_manifest(
    development: dict[str, Any], hidden: dict[str, Any], excluded_family: str
) -> dict[str, Any]:
    mechanisms = []
    for manifest in (development, hidden):
        for mechanism in manifest["mechanisms"]:
            family = str(mechanism["mechanism_id"])
            if family.startswith("dev_"):
                family = family[4:]
            if family.startswith("hidden_"):
                family = family[7:]
            if family != excluded_family:
                mechanisms.append(mechanism)
    return {"mechanisms": mechanisms}


def _planner(
    name: str,
    interventions,
    graph,
    residual_model: LearnedResidualActionModel,
    end_to_end_weights,
):
    if name == "qrtc":
        return qrtc.build_policy(interventions, graph=graph)
    if name == "hybrid_qrtc":
        return HybridQRTCPolicy(interventions, graph, residual_model)
    if name == "qrtc_untyped":
        return qrtc_untyped.build_policy(interventions)
    if name == "end_to_end":
        return LearnedEndToEndPolicy(interventions, end_to_end_weights)
    if name == "greedy_expected_gain":
        return greedy.build_policy(interventions)
    return BoundedLookaheadPlanner(
        interventions,
        config=PlannerConfig(lambda_cost=0.0, beta_harm=0.0, gamma_unsafe=0.0),
        graph=graph,
    )


def _evaluate(
    name: str,
    trial: dict[str, Any],
    base_interventions,
    task,
    graph,
    residual_model,
    end_to_end_weights,
    max_actions: int,
):
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
    audit = AuditEventLog()
    controller = RescueController(
        adapter=NoisyPolicyAdapter(
            simulator,
            noise=float(trial["observation_noise"]),
            seed=int(trial["trial_seed"]),
            oracle=name == "oracle",
        ),
        inference=SimpleBeliefUpdater(),
        planner=_planner(
            name,
            interventions,
            graph,
            residual_model,
            end_to_end_weights,
        ),
        audit_log=audit,
    )
    return controller.rescue(task, max_actions=max_actions), audit


def stratified_cluster_bootstrap(
    differences: dict[str, dict[str, float]], *, samples: int, seed: int
) -> dict[str, float]:
    rng = random.Random(seed)
    families = sorted(differences)
    draws = []
    for _ in range(samples):
        family_means = []
        for family in families:
            values = list(differences[family].values())
            family_means.append(statistics.fmean(rng.choice(values) for _ in values))
        draws.append(statistics.fmean(family_means))
    draws.sort()
    family_estimates = {
        family: statistics.fmean(values.values())
        for family, values in differences.items()
    }
    estimate = statistics.fmean(family_estimates.values())
    lower = draws[int(0.025 * samples)]
    upper = draws[min(samples - 1, int(0.975 * samples))]
    return {
        "estimate": estimate,
        "lower_95": lower,
        "upper_95": upper,
        "half_width": (upper - lower) / 2.0,
        "per_family": family_estimates,
    }


def _paired_differences(
    rows: list[dict[str, Any]], policy: str, baseline: str
) -> dict[str, dict[str, float]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    family_by_cluster = {}
    for row in rows:
        grouped[(row["cluster_id"], row["policy"])].append(float(row["utility"]))
        family_by_cluster[row["cluster_id"]] = row["mechanism_family"]
    output: dict[str, dict[str, float]] = defaultdict(dict)
    for cluster in sorted(family_by_cluster):
        output[family_by_cluster[cluster]][cluster] = (
            statistics.fmean(grouped[(cluster, policy)])
            - statistics.fmean(grouped[(cluster, baseline)])
        )
    return dict(output)


def _calibration_comparison(
    heldout_probes: list[dict[str, Any]], model: LearnedResidualActionModel
) -> dict[str, float]:
    current_errors = []
    hybrid_errors = []
    for probe in heldout_probes:
        current = float(probe["predicted_recovery"])
        residual = model.predict(probe["public_observation"], [], str(probe["action_id"]))
        hybrid = min(1.0, max(0.0, current + residual.residual))
        realized = float(probe["realized_recovery"])
        current_errors.append((current - realized) ** 2)
        hybrid_errors.append((hybrid - realized) ** 2)
    return {
        "current_qrtc_brier": statistics.fmean(current_errors),
        "hybrid_qrtc_brier": statistics.fmean(hybrid_errors),
        "brier_improvement": statistics.fmean(current_errors) - statistics.fmean(hybrid_errors),
    }


def run_adaptive_benchmark(
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
    bootstrap_seed: int = 1450,
    target_half_width: float = 0.10,
) -> dict[str, Any]:
    development = load_manifest(development_path)
    hidden = load_manifest(hidden_path)
    validate_manifests(development, hidden)
    verify_hidden_lock(hidden_path, lock_path)
    spec = load_system_spec(spec_path)
    graph = compile_graph(spec)
    task = spec.tasks[0]
    interventions = list(spec.interventions)
    all_trials = build_development_trials(
        development,
        hidden,
        replicates=replicates,
        noise_levels=noise_levels,
        reliability_levels=reliability_levels,
    )
    families = sorted({str(trial["mechanism_family"]) for trial in all_trials})
    rows: list[dict[str, Any]] = []
    calibration_by_fold = {}
    parameters_by_fold = {}
    evidence_ids = {
        action.action_id for action in interventions if action.kind.value == "evidence"
    }
    for heldout_family in families:
        training_trials = [
            trial for trial in all_trials if trial["mechanism_family"] != heldout_family
        ]
        heldout_trials = [
            trial for trial in all_trials if trial["mechanism_family"] == heldout_family
        ]
        training_probes = [
            probe
            for trial in training_trials
            for probe in _counterfactual_probes(
                trial,
                interventions,
                task,
                graph,
                lambda_cost=0.05,
                beta_harm=0.25,
                gamma_unsafe=0.2,
            )
        ]
        residual_model = LearnedResidualActionModel.fit(training_probes)
        training_manifest = _combined_manifest(development, hidden, heldout_family)
        end_to_end_weights = fit_end_to_end_weights(
            training_manifest, interventions, task, graph
        )
        heldout_probes = [
            probe
            for trial in heldout_trials
            for probe in _counterfactual_probes(
                trial,
                interventions,
                task,
                graph,
                lambda_cost=0.05,
                beta_harm=0.25,
                gamma_unsafe=0.2,
            )
        ]
        calibration_by_fold[heldout_family] = _calibration_comparison(
            heldout_probes, residual_model
        )
        parameters_by_fold[heldout_family] = residual_model.parameters()
        for trial in heldout_trials:
            for policy in POLICIES:
                result, audit = _evaluate(
                    policy,
                    trial,
                    interventions,
                    task,
                    graph,
                    residual_model,
                    end_to_end_weights,
                    max_actions,
                )
                row = _row(
                    policy,
                    trial,
                    result,
                    audit,
                    evidence_ids,
                    lambda_cost=0.05,
                    eta_actions=0.02,
                    beta_harm=0.25,
                )
                row["heldout_family"] = heldout_family
                rows.append(row)
    means = {
        policy: statistics.fmean(
            float(row["utility"]) for row in rows if row["policy"] == policy
        )
        for policy in POLICIES
    }
    strongest = max(COMPARATORS, key=means.get)
    primary = stratified_cluster_bootstrap(
        _paired_differences(rows, "hybrid_qrtc", strongest),
        samples=bootstrap_samples,
        seed=bootstrap_seed,
    )
    structure = stratified_cluster_bootstrap(
        _paired_differences(rows, "hybrid_qrtc", "qrtc_untyped"),
        samples=bootstrap_samples,
        seed=bootstrap_seed + 1,
    )
    hybrid_rows = [row for row in rows if row["policy"] == "hybrid_qrtc"]
    calibration_improved = all(
        item["brier_improvement"] > 0.0 for item in calibration_by_fold.values()
    )
    cluster_counts = {
        family: len(
            {
                row["cluster_id"]
                for row in rows
                if row["mechanism_family"] == family
            }
        )
        for family in families
    }
    acceptance = {
        "aggregate_advantage_positive": primary["estimate"] > 0.0,
        "interval_sufficiently_precise": primary["half_width"] <= target_half_width,
        "no_catastrophic_family": all(value > -0.5 for value in primary["per_family"].values()),
        "benefit_not_concentrated": sum(value > 0.0 for value in primary["per_family"].values()) >= max(2, len(families) // 2),
        "typed_structure_beats_untyped": structure["estimate"] > 0.0,
        "safety_thresholds_pass": (
            statistics.fmean(row["unsafe_event"] for row in hybrid_rows) <= 0.05
            and statistics.fmean(row["harm"] for row in hybrid_rows) <= 0.05
        ),
        "calibration_improved": calibration_improved,
        "leakage_tests_required": True,
        "protocol_frozen_before_validation": False,
    }
    acceptance["validation_authorized"] = all(acceptance.values())
    return {
        "artifact_type": "graph_constrained_adaptive_qrtc_development_v2",
        "experiment_class": "development_not_validation",
        "evaluation": "leave_one_mechanism_family_out",
        "policies": list(POLICIES),
        "strongest_nonoracle": strongest,
        "primary_hybrid_delta": primary,
        "hybrid_minus_untyped": structure,
        "bootstrap": {
            "method": "family-stratified paired cluster bootstrap",
            "resamples": bootstrap_samples,
            "seed": bootstrap_seed,
        },
        "design": {
            "matched_trials_per_policy": len(all_trials),
            "total_policy_runs": len(rows),
            "independent_cluster_count": sum(cluster_counts.values()),
            "clusters_by_family": cluster_counts,
            "replicates_per_cluster": replicates,
            "balanced_clusters": len(set(cluster_counts.values())) == 1,
        },
        "fold_calibration": calibration_by_fold,
        "learned_parameters_by_fold": parameters_by_fold,
        "mean_utility": means,
        "development_acceptance": acceptance,
        "hardware_actuation_enabled": False,
        "hardware_gate": "NOT READY",
        "trials": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run graph-constrained adaptive QRTC development v2")
    parser.add_argument("--spec", default="configs/communication_system.yaml")
    parser.add_argument("--development", default="configs/development_mechanisms.json")
    parser.add_argument("--hidden", default="configs/hidden_mechanisms.json")
    parser.add_argument("--lock", default="configs/hidden_mechanisms.lock.json")
    parser.add_argument("--output", default="artifacts/phase6/ADAPTIVE_QRTC_DEVELOPMENT_V2.json")
    parser.add_argument("--replicates", type=int, default=8)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=1450)
    args = parser.parse_args()
    payload = run_adaptive_benchmark(
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