from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
from typing import Any

from rescueos.audit.event_log import AuditEventLog
from rescueos.compiler.graph_compiler import compile_graph
from rescueos.compiler.loader import load_system_spec
from rescueos.core.belief import SimpleBeliefUpdater
from rescueos.core.controller import RescueController
from rescueos.core.planner import BoundedLookaheadPlanner, PlannerConfig
from rescueos.core.transition import TransitionModel
from rescueos.experiments.adaptive_benchmark import (
    _combined_manifest,
    _paired_differences,
    stratified_cluster_bootstrap,
)
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
from rescueos.policies.conservative_hybrid_qrtc import (
    ConservativeHybridQRTCPolicy,
    ConservativeTemporalResidualModel,
)
from rescueos.policies.end_to_end import LearnedEndToEndPolicy
from rescueos.policies.hybrid_qrtc import HybridQRTCPolicy, LearnedResidualActionModel
from rescueos.simulator.communication_link import CommunicationLinkSimulator


POLICIES = (
    "qrtc",
    "hybrid_qrtc_v2",
    "conservative_hybrid_qrtc",
    "qrtc_untyped",
    "end_to_end",
    "greedy_expected_gain",
    "oracle",
)
COMPARATORS = (
    "qrtc",
    "hybrid_qrtc_v2",
    "qrtc_untyped",
    "end_to_end",
    "greedy_expected_gain",
)


def _temporal_probes(trial, interventions, task, graph) -> list[dict[str, Any]]:
    probes = _counterfactual_probes(
        trial,
        interventions,
        task,
        graph,
        lambda_cost=0.05,
        beta_harm=0.25,
        gamma_unsafe=0.2,
    )
    for probe in probes:
        probe["public_history"] = []
        probe["probe_phase"] = "initial"
    configured = _configured_interventions(
        interventions, float(trial["intervention_reliability"])
    )
    evidence_actions = [action for action in configured if action.kind.value == "evidence"]
    action_by_id = {action.action_id: action for action in configured}
    for evidence in evidence_actions:
        base_simulator = CommunicationLinkSimulator(
            configured,
            seed=int(trial["trial_seed"]),
            faults=scenario_faults(trial),
            graph=graph,
        )
        base_adapter = NoisyPolicyAdapter(
            base_simulator,
            noise=float(trial["observation_noise"]),
            seed=int(trial["trial_seed"]),
            oracle=False,
        )
        base_adapter.observe()
        evidence_outcome = base_adapter.apply(evidence.action_id)
        observation = base_adapter.observe()
        history = [evidence_outcome]
        belief = SimpleBeliefUpdater().update(observation, history, task)
        planner = qrtc.build_policy(configured, graph=graph)
        for prediction in planner.predict_actions(belief, task):
            action_id = str(prediction["action_id"])
            action = action_by_id[action_id]
            if not bool(prediction["graph_admissible"]) or action.kind.value != "repair":
                continue
            simulator = CommunicationLinkSimulator(
                configured,
                seed=int(trial["trial_seed"]),
                faults=scenario_faults(trial),
                graph=graph,
            )
            adapter = NoisyPolicyAdapter(
                simulator,
                noise=float(trial["observation_noise"]),
                seed=int(trial["trial_seed"]),
                oracle=False,
            )
            adapter.observe()
            replay_evidence = adapter.apply(evidence.action_id)
            replay_observation = adapter.observe()
            outcome = adapter.apply(action_id)
            realized_recovery = float(adapter.evaluate_task(task) <= task.recovery_threshold)
            realized_utility = (
                realized_recovery
                - 0.05 * action.cost
                - 0.25 * float(outcome.harm)
                - 0.2 * float(outcome.unsafe)
            )
            probes.append(
                {
                    "mechanism_family": trial["mechanism_family"],
                    "mechanism_split": trial["mechanism_split"],
                    "cluster_id": trial["cluster_id"],
                    "replicate": trial["replicate"],
                    "action_id": action_id,
                    "action_kind": action.kind.value,
                    "graph_admissible": True,
                    "public_observation": replay_observation,
                    "public_history": [replay_evidence],
                    "predicted_recovery": float(prediction["predicted_recovery"]),
                    "realized_recovery": realized_recovery,
                    "predicted_utility": float(prediction["predicted_utility"]),
                    "realized_utility": realized_utility,
                    "utility_error": float(prediction["predicted_utility"]) - realized_utility,
                    "probe_phase": "post_evidence",
                }
            )
    return probes


def _planner(name, interventions, graph, v2_model, v3_model, end_to_end_weights):
    if name == "qrtc":
        return qrtc.build_policy(interventions, graph=graph)
    if name == "hybrid_qrtc_v2":
        return HybridQRTCPolicy(interventions, graph, v2_model)
    if name == "conservative_hybrid_qrtc":
        return ConservativeHybridQRTCPolicy(interventions, graph, v3_model)
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


def _evaluate(name, trial, interventions, task, graph, v2_model, v3_model, weights, max_actions):
    configured = _configured_interventions(
        interventions, float(trial["intervention_reliability"])
    )
    transition = TransitionModel(graph)
    simulator = CommunicationLinkSimulator(
        configured,
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
        planner=_planner(name, configured, graph, v2_model, v3_model, weights),
        audit_log=audit,
    )
    return controller.rescue(task, max_actions=max_actions), audit


def _calibration(probes, model) -> dict[str, Any]:
    rows = []
    for probe in probes:
        prediction = model.predict(
            probe["public_observation"],
            probe.get("public_history", []),
            str(probe["action_id"]),
        )
        graph_prediction = float(probe["predicted_recovery"])
        calibrated = min(1.0, max(0.0, graph_prediction + prediction.residual))
        realized = float(probe["realized_recovery"])
        rows.append(
            {
                "phase": probe["probe_phase"],
                "graph_error": (graph_prediction - realized) ** 2,
                "calibrated_error": (calibrated - realized) ** 2,
                "predicted": calibrated,
                "realized": realized,
                "alpha": prediction.alpha,
                "uncertainty": prediction.uncertainty,
                "support_distance": prediction.support_distance,
            }
        )
    bins: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        bins[min(9, int(row["predicted"] * 10))].append(row)
    ece = sum(
        len(group) / len(rows)
        * abs(
            statistics.fmean(row["predicted"] for row in group)
            - statistics.fmean(row["realized"] for row in group)
        )
        for group in bins.values()
    )
    by_phase = {
        phase: {
            "count": len(selected),
            "brier": statistics.fmean(row["calibrated_error"] for row in selected),
            "mean_alpha": statistics.fmean(row["alpha"] for row in selected),
            "mean_uncertainty": statistics.fmean(row["uncertainty"] for row in selected),
            "mean_support_distance": statistics.fmean(row["support_distance"] for row in selected),
        }
        for phase in sorted({row["phase"] for row in rows})
        for selected in [[row for row in rows if row["phase"] == phase]]
    }
    graph_brier = statistics.fmean(row["graph_error"] for row in rows)
    calibrated_brier = statistics.fmean(row["calibrated_error"] for row in rows)
    return {
        "graph_brier": graph_brier,
        "conservative_brier": calibrated_brier,
        "brier_improvement": graph_brier - calibrated_brier,
        "expected_calibration_error": ece,
        "by_phase": by_phase,
    }


def _family_diagnostics(rows, primary, comparator, family_intervals, calibration):
    output = {}
    for family in sorted(family_intervals):
        family_rows = [row for row in rows if row["mechanism_family"] == family]
        oracle_actions = {
            (row["cluster_id"], row["replicate"]): row["first_action"]
            for row in family_rows
            if row["policy"] == "oracle"
        }
        for row in family_rows:
            row["first_action_accuracy"] = float(
                row["first_action"]
                == oracle_actions[(row["cluster_id"], row["replicate"])]
            )
        metrics = {}
        for policy in (primary, comparator):
            selected = [row for row in family_rows if row["policy"] == policy]
            actions: dict[str, int] = defaultdict(int)
            for row in selected:
                actions[row["first_action"]] += 1
            metrics[policy] = {
                "utility": statistics.fmean(row["utility"] for row in selected),
                "recovery_rate": statistics.fmean(row["recovered"] for row in selected),
                "stopping_rate": statistics.fmean(row["first_action"] == "stop" for row in selected),
                "evidence_request_rate": statistics.fmean(row["evidence_requests"] > 0 for row in selected),
                "first_action_oracle_agreement": statistics.fmean(row["first_action_accuracy"] for row in selected),
                "oracle_regret": statistics.fmean(max(0.0, row.get("oracle_regret", 0.0)) for row in selected),
                "mean_cost": statistics.fmean(row["cost"] for row in selected),
                "mean_harm": statistics.fmean(row["harm"] for row in selected),
                "unsafe_rate": statistics.fmean(row["unsafe_event"] for row in selected),
                "action_selection_distribution": dict(sorted(actions.items())),
            }
        output[family] = {
            "paired_utility_difference": family_intervals[family],
            "policies": metrics,
            "calibration": calibration[family],
        }
    return output


def run_targeted_v3(
    spec_path: str | Path,
    development_path: str | Path,
    hidden_path: str | Path,
    lock_path: str | Path,
    protocol_path: str | Path,
    *,
    max_actions: int = 4,
) -> dict[str, Any]:
    protocol = load_manifest(protocol_path)
    if not protocol.get("frozen_before_execution"):
        raise ValueError("Adaptive v3 protocol must be frozen before execution")
    development = load_manifest(development_path)
    hidden = load_manifest(hidden_path)
    validate_manifests(development, hidden)
    verify_hidden_lock(hidden_path, lock_path)
    spec = load_system_spec(spec_path)
    graph = compile_graph(spec)
    task = spec.tasks[0]
    interventions = list(spec.interventions)
    design = protocol["design"]
    all_trials = build_development_trials(
        development,
        hidden,
        replicates=int(design["replicates_per_cluster"]),
        noise_levels=tuple(float(value) for value in design["noise_levels"]),
        reliability_levels=tuple(
            float(value) for value in design["intervention_reliability_levels"]
        ),
    )
    families = sorted({trial["mechanism_family"] for trial in all_trials})
    rows = []
    calibration_by_family = {}
    parameters_by_fold = {}
    evidence_ids = {action.action_id for action in interventions if action.kind.value == "evidence"}
    fallback = protocol["residual_fallback"]
    for heldout_family in families:
        training_trials = [trial for trial in all_trials if trial["mechanism_family"] != heldout_family]
        heldout_trials = [trial for trial in all_trials if trial["mechanism_family"] == heldout_family]
        training_probes = [probe for trial in training_trials for probe in _temporal_probes(trial, interventions, task, graph)]
        heldout_probes = [probe for trial in heldout_trials for probe in _temporal_probes(trial, interventions, task, graph)]
        v2_model = LearnedResidualActionModel.fit(training_probes)
        v3_model = ConservativeTemporalResidualModel.fit(
            training_probes,
            uncertainty_scale=float(fallback["uncertainty_scale"]),
            support_distance_scale=float(fallback["support_distance_scale"]),
        )
        weights = fit_end_to_end_weights(
            _combined_manifest(development, hidden, heldout_family),
            interventions,
            task,
            graph,
        )
        calibration_by_family[heldout_family] = _calibration(heldout_probes, v3_model)
        parameters_by_fold[heldout_family] = v3_model.parameters()
        for trial in heldout_trials:
            for policy in POLICIES:
                result, audit = _evaluate(
                    policy,
                    trial,
                    interventions,
                    task,
                    graph,
                    v2_model,
                    v3_model,
                    weights,
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
    oracle_utility = {
        (row["cluster_id"], row["replicate"]): row["utility"]
        for row in rows
        if row["policy"] == "oracle"
    }
    for row in rows:
        gap = oracle_utility[(row["cluster_id"], row["replicate"])] - row["utility"]
        row["oracle_regret"] = max(0.0, gap)
    means = {
        policy: statistics.fmean(row["utility"] for row in rows if row["policy"] == policy)
        for policy in POLICIES
    }
    comparator = max(COMPARATORS, key=means.get)
    bootstrap = protocol["bootstrap"]
    differences = _paired_differences(rows, "conservative_hybrid_qrtc", comparator)
    primary = stratified_cluster_bootstrap(
        differences,
        samples=int(bootstrap["resamples"]),
        seed=int(bootstrap["seed"]),
    )
    family_intervals = {
        family: stratified_cluster_bootstrap(
            {family: clusters},
            samples=int(bootstrap["resamples"]),
            seed=int(bootstrap["seed"]) + index + 1,
        )
        for index, (family, clusters) in enumerate(sorted(differences.items()))
    }
    primary_rows = [row for row in rows if row["policy"] == "conservative_hybrid_qrtc"]
    graph_invalid = [
        row
        for row in primary_rows
        if row["first_action"] not in {"stop", *evidence_ids}
        and not graph.action_can_influence(row["first_action"], task.task_id)
    ]
    thresholds = protocol["acceptance"]
    aggregate_brier = statistics.fmean(
        item["conservative_brier"] for item in calibration_by_family.values()
    )
    worst_family_brier = max(
        item["conservative_brier"] for item in calibration_by_family.values()
    )
    acceptance = {
        "aggregate_advantage_positive": primary["estimate"] > float(thresholds["aggregate_advantage_minimum"]),
        "aggregate_interval_positive": primary["lower_95"] > float(thresholds["aggregate_interval_lower_minimum"]),
        "interval_sufficiently_precise": primary["half_width"] <= float(thresholds["maximum_interval_half_width"]),
        "no_catastrophic_family": all(value["estimate"] > float(thresholds["catastrophic_family_floor"]) for value in family_intervals.values()),
        "benefit_broadly_distributed": sum(value["estimate"] > 0.0 for value in family_intervals.values()) >= int(thresholds["minimum_positive_family_count"]),
        "aggregate_calibration_limit": aggregate_brier <= float(thresholds["maximum_aggregate_brier"]),
        "worst_family_calibration_limit": worst_family_brier <= float(thresholds["maximum_worst_family_brier"]),
        "calibration_improves_every_family": all(item["brier_improvement"] > 0.0 for item in calibration_by_family.values()),
        "safety_thresholds_pass": (
            statistics.fmean(row["unsafe_event"] for row in primary_rows) <= float(thresholds["maximum_unsafe_rate"])
            and statistics.fmean(row["harm"] for row in primary_rows) <= float(thresholds["maximum_harm_rate"])
        ),
        "graph_invalid_action_rate_zero": len(graph_invalid) / len(primary_rows) == float(thresholds["graph_invalid_action_rate"]),
        "leakage_tests_required": bool(thresholds["leakage_tests_required"]),
        "protocol_frozen_before_execution": True,
    }
    acceptance["validation_authorized"] = all(acceptance.values())
    return {
        "artifact_type": "targeted_adaptive_qrtc_development_v3",
        "experiment_class": "development_not_validation",
        "protocol": protocol,
        "policies": list(POLICIES),
        "strongest_nonoracle": comparator,
        "primary_delta": primary,
        "family_diagnostics": _family_diagnostics(
            rows,
            "conservative_hybrid_qrtc",
            comparator,
            family_intervals,
            calibration_by_family,
        ),
        "aggregate_calibration": {
            "brier": aggregate_brier,
            "worst_family_brier": worst_family_brier,
        },
        "learned_parameters_by_fold": parameters_by_fold,
        "mean_utility": means,
        "development_acceptance": acceptance,
        "hardware_actuation_enabled": False,
        "hardware_gate": "NOT READY",
        "trials": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run targeted adaptive QRTC development v3")
    parser.add_argument("--spec", default="configs/communication_system.yaml")
    parser.add_argument("--development", default="configs/development_mechanisms.json")
    parser.add_argument("--hidden", default="configs/hidden_mechanisms.json")
    parser.add_argument("--lock", default="configs/hidden_mechanisms.lock.json")
    parser.add_argument("--protocol", default="configs/adaptive_v3_protocol.json")
    parser.add_argument("--output", default="artifacts/phase6/TARGETED_ADAPTIVE_QRTC_DEVELOPMENT_V3.json")
    args = parser.parse_args()
    payload = run_targeted_v3(
        args.spec,
        args.development,
        args.hidden,
        args.lock,
        args.protocol,
    )
    output = Path(args.output)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()