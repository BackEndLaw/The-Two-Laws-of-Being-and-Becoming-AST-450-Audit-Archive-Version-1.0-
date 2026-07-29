from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import statistics
from typing import Any

from rescueos.audit.event_log import AuditEventLog
from rescueos.compiler.graph_compiler import compile_graph
from rescueos.compiler.loader import load_system_spec
from rescueos.core.belief import SimpleBeliefUpdater
from rescueos.core.controller import RescueController
from rescueos.core.planner import BoundedLookaheadPlanner, PlannerConfig
from rescueos.core.transition import TransitionModel
from rescueos.experiments.adaptive_benchmark import stratified_cluster_bootstrap
from rescueos.experiments.development_benchmark import (
    NoisyPolicyAdapter,
    _configured_interventions,
    _row,
    build_development_trials,
)
from rescueos.experiments.hidden_transfer import (
    load_manifest,
    scenario_faults,
    validate_manifests,
    verify_hidden_lock,
)
from rescueos.experiments.targeted_v3_benchmark import _temporal_probes
from rescueos.policies.conservative_hybrid_qrtc import (
    ConservativeHybridQRTCPolicy,
    ConservativeTemporalResidualModel,
)
from rescueos.policies.hybrid_qrtc import HybridQRTCPolicy, LearnedResidualActionModel
from rescueos.policies.routed_hybrid_qrtc import (
    PublicIncrementalUtilityRouter,
    RoutedHybridQRTCPolicy,
)
from rescueos.simulator.communication_link import CommunicationLinkSimulator


POLICIES = ("hybrid_qrtc_v2", "conservative_hybrid_qrtc_v3", "routed_hybrid_qrtc_v4", "oracle")


def _utility(result) -> float:
    return (
        float(result.status == "recovered")
        - 0.05 * sum(float(outcome.cost) for outcome in result.history)
        - 0.02 * result.actions_executed
        - 0.25 * sum(float(outcome.harm) for outcome in result.history)
    )


def _policy(name, interventions, graph, v2_model, v3_model, router):
    if name == "hybrid_qrtc_v2":
        return HybridQRTCPolicy(interventions, graph, v2_model)
    if name == "conservative_hybrid_qrtc_v3":
        return ConservativeHybridQRTCPolicy(interventions, graph, v3_model)
    if name == "routed_hybrid_qrtc_v4":
        return RoutedHybridQRTCPolicy(
            HybridQRTCPolicy(interventions, graph, v2_model),
            ConservativeHybridQRTCPolicy(interventions, graph, v3_model),
            router,
        )
    return BoundedLookaheadPlanner(
        interventions,
        config=PlannerConfig(lambda_cost=0.0, beta_harm=0.0, gamma_unsafe=0.0),
        graph=graph,
    )


def _evaluate(name, trial, interventions, task, graph, v2_model, v3_model, router, max_actions=4):
    configured = _configured_interventions(interventions, float(trial["intervention_reliability"]))
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
        planner=_policy(name, configured, graph, v2_model, v3_model, router),
        audit_log=audit,
    )
    return controller.rescue(task, max_actions=max_actions), audit


def _cross_fitted_router_records(all_trials, interventions, task, graph, protocol):
    families = sorted({trial["mechanism_family"] for trial in all_trials})
    records = []
    for heldout in families:
        training = [trial for trial in all_trials if trial["mechanism_family"] != heldout]
        heldout_trials = [trial for trial in all_trials if trial["mechanism_family"] == heldout]
        probes = [probe for trial in training for probe in _temporal_probes(trial, interventions, task, graph)]
        v2_model = LearnedResidualActionModel.fit(probes)
        fallback = protocol["router"]
        v3_model = ConservativeTemporalResidualModel.fit(probes)
        dummy_router = PublicIncrementalUtilityRouter(
            tuple(), tuple(), tuple(), 1.0, tuple(), tuple(),
            float(fallback["lcb_z"]), float(fallback["activation_threshold"]),
        )
        for trial in heldout_trials:
            v2_result, v2_audit = _evaluate(
                "hybrid_qrtc_v2", trial, interventions, task, graph, v2_model, v3_model, dummy_router
            )
            v3_result, v3_audit = _evaluate(
                "conservative_hybrid_qrtc_v3", trial, interventions, task, graph, v2_model, v3_model, dummy_router
            )
            v2_decision = v2_audit.decisions[0]["decision"]
            v3_decision = v3_audit.decisions[0]["decision"]
            records.append(
                {
                    "heldout_family": heldout,
                    "public_observation": v2_audit.decisions[0]["observation"],
                    "history_length": 0.0,
                    "v2_action": v2_decision["action_id"],
                    "v3_action": v3_decision["action_id"],
                    "v2_expected_utility": v2_decision["expected_utility"],
                    "v3_expected_utility": v3_decision["expected_utility"],
                    "incremental_utility": _utility(v3_result) - _utility(v2_result),
                }
            )
    return records


def _router_cross_fit(records, protocol):
    router_config = protocol["router"]
    predictions = []
    for family in sorted({row["heldout_family"] for row in records}):
        training = [row for row in records if row["heldout_family"] != family]
        heldout = [row for row in records if row["heldout_family"] == family]
        model = PublicIncrementalUtilityRouter.fit(
            training,
            lcb_z=float(router_config["lcb_z"]),
            threshold=float(router_config["activation_threshold"]),
        )
        for row in heldout:
            prediction = model.predict(row)
            predictions.append(
                {
                    "family": family,
                    "activated": prediction.lower_confidence_bound > model.threshold,
                    "predicted_increment": prediction.mean,
                    "predicted_lcb": prediction.lower_confidence_bound,
                    "realized_increment": row["incremental_utility"],
                }
            )
    activated = [row for row in predictions if row["activated"]]
    return {
        "record_count": len(predictions),
        "activation_rate": len(activated) / len(predictions),
        "activated_incremental_utility": (
            statistics.fmean(row["realized_increment"] for row in activated)
            if activated else 0.0
        ),
        "activation_precision": (
            statistics.fmean(row["realized_increment"] > 0.0 for row in activated)
            if activated else 0.0
        ),
        "mean_absolute_increment_error": statistics.fmean(
            abs(row["predicted_increment"] - row["realized_increment"])
            for row in predictions
        ),
        "by_family": {
            family: {
                "activation_rate": statistics.fmean(row["activated"] for row in selected),
                "mean_realized_increment": statistics.fmean(row["realized_increment"] for row in selected),
            }
            for family in sorted({row["family"] for row in predictions})
            for selected in [[row for row in predictions if row["family"] == family]]
        },
    }


def _fresh_trials(manifest, protocol):
    design = protocol["design"]
    trials = []
    config_index = 0
    for mechanism in manifest["mechanisms"]:
        for scenario in mechanism["scenarios"]:
            for noise in design["noise_levels"]:
                for reliability in design["intervention_reliability_levels"]:
                    cluster = (
                        f"{mechanism['mechanism_id']}:{scenario['scenario_id']}:"
                        f"n{float(noise):.3f}:r{float(reliability):.3f}"
                    )
                    for replicate in range(int(design["replicates_per_cluster"])):
                        trials.append(
                            {
                                **scenario,
                                "mechanism_split": "fresh_development_v4",
                                "mechanism_family": mechanism["dynamical_class"],
                                "mechanism_id": mechanism["mechanism_id"],
                                "cluster_id": cluster,
                                "replicate": replicate,
                                "trial_seed": int(scenario["seed"]) + 10_000 * config_index + replicate,
                                "observation_noise": float(noise),
                                "intervention_reliability": float(reliability),
                                "affected_stage": "fresh",
                                "fault_count": len(scenario["faults"]),
                                "severity": statistics.fmean(float(fault["severity"]) for fault in scenario["faults"]),
                                "severity_band": "fresh",
                            }
                        )
                    config_index += 1
    return trials


def _parse_route(audit):
    decisions = [item["decision"]["reason"] for item in audit.decisions]
    activated = any("route=specialist" in reason for reason in decisions)
    lcb_values = [
        float(match.group(1))
        for reason in decisions
        for match in [re.search(r"incremental_lcb=([-0-9.]+)", reason)]
        if match
    ]
    return activated, (lcb_values[0] if lcb_values else None)


def run_routed_v4(spec_path, development_path, hidden_path, hidden_lock_path, fresh_path, protocol_path):
    protocol = load_manifest(protocol_path)
    if not protocol.get("frozen_before_execution") or not protocol.get("one_shot_execution"):
        raise ValueError("V4 protocol must be frozen and one-shot before execution")
    development = load_manifest(development_path)
    hidden = load_manifest(hidden_path)
    fresh = load_manifest(fresh_path)
    validate_manifests(development, hidden)
    verify_hidden_lock(hidden_path, hidden_lock_path)
    prior_ids = {
        mechanism["mechanism_id"]
        for manifest in (development, hidden)
        for mechanism in manifest["mechanisms"]
    }
    prior_seeds = {
        scenario["seed"]
        for manifest in (development, hidden)
        for mechanism in manifest["mechanisms"]
        for scenario in mechanism["scenarios"]
    }
    fresh_ids = {mechanism["mechanism_id"] for mechanism in fresh["mechanisms"]}
    fresh_seeds = {
        scenario["seed"]
        for mechanism in fresh["mechanisms"]
        for scenario in mechanism["scenarios"]
    }
    if not fresh_ids.isdisjoint(prior_ids) or not fresh_seeds.isdisjoint(prior_seeds):
        raise ValueError("Fresh V4 mechanisms and seeds must be disjoint from prior development")
    spec = load_system_spec(spec_path)
    graph = compile_graph(spec)
    task = spec.tasks[0]
    interventions = list(spec.interventions)
    prior_trials = build_development_trials(
        development, hidden, replicates=8, noise_levels=(0.0, 0.05), reliability_levels=(0.8, 1.0)
    )
    records = _cross_fitted_router_records(prior_trials, interventions, task, graph, protocol)
    router_diagnostics = _router_cross_fit(records, protocol)
    router = PublicIncrementalUtilityRouter.fit(
        records,
        lcb_z=float(protocol["router"]["lcb_z"]),
        threshold=float(protocol["router"]["activation_threshold"]),
    )
    all_probes = [probe for trial in prior_trials for probe in _temporal_probes(trial, interventions, task, graph)]
    v2_model = LearnedResidualActionModel.fit(all_probes)
    v3_model = ConservativeTemporalResidualModel.fit(all_probes)
    fresh_trials = _fresh_trials(fresh, protocol)
    evidence_ids = {action.action_id for action in interventions if action.kind.value == "evidence"}
    rows = []
    audits = {}
    for trial in fresh_trials:
        for policy in POLICIES:
            result, audit = _evaluate(policy, trial, interventions, task, graph, v2_model, v3_model, router)
            row = _row(policy, trial, result, audit, evidence_ids, lambda_cost=0.05, eta_actions=0.02, beta_harm=0.25)
            activated, lcb = _parse_route(audit) if policy == "routed_hybrid_qrtc_v4" else (False, None)
            row["router_activated"] = activated
            row["router_incremental_lcb"] = lcb
            rows.append(row)
            audits[(trial["cluster_id"], trial["replicate"], policy)] = audit
    indexed = {
        (row["cluster_id"], row["replicate"], row["policy"]): row for row in rows
    }
    paired_by_cluster: dict[tuple[str, str], list[float]] = defaultdict(list)
    activation_rows = []
    for trial in fresh_trials:
        key = (trial["cluster_id"], trial["replicate"])
        v4 = indexed[(*key, "routed_hybrid_qrtc_v4")]
        v2 = indexed[(*key, "hybrid_qrtc_v2")]
        delta = v4["utility"] - v2["utility"]
        paired_by_cluster[(trial["mechanism_family"], trial["cluster_id"])].append(delta)
        if v4["router_activated"]:
            v3 = indexed[(*key, "conservative_hybrid_qrtc_v3")]
            activation_rows.append({"class": trial["mechanism_family"], "increment": v3["utility"] - v2["utility"]})
    differences: dict[str, dict[str, float]] = defaultdict(dict)
    for (family, cluster), deltas in paired_by_cluster.items():
        differences[family][cluster] = statistics.fmean(deltas)
    bootstrap = protocol["bootstrap"]
    primary = stratified_cluster_bootstrap(
        dict(differences), samples=int(bootstrap["resamples"]), seed=int(bootstrap["seed"])
    )
    family_intervals = {
        family: stratified_cluster_bootstrap(
            {family: clusters}, samples=int(bootstrap["resamples"]), seed=int(bootstrap["seed"]) + index + 1
        )
        for index, (family, clusters) in enumerate(sorted(differences.items()))
    }
    v4_rows = [row for row in rows if row["policy"] == "routed_hybrid_qrtc_v4"]
    v2_rows = [row for row in rows if row["policy"] == "hybrid_qrtc_v2"]
    activation_by_class = {
        family: statistics.fmean(row["router_activated"] for row in selected)
        for family in sorted({row["mechanism_family"] for row in v4_rows})
        for selected in [[row for row in v4_rows if row["mechanism_family"] == family]]
    }
    activated_increment = statistics.fmean(row["increment"] for row in activation_rows) if activation_rows else 0.0
    thresholds = protocol["acceptance"]
    unsafe_increase = statistics.fmean(row["unsafe_event"] for row in v4_rows) - statistics.fmean(row["unsafe_event"] for row in v2_rows)
    graph_invalid = []
    for row in v4_rows:
        audit = audits[(row["cluster_id"], row["replicate"], "routed_hybrid_qrtc_v4")]
        if audit.decisions:
            candidates = audit.decisions[0]["decision"]["candidate_utilities"]
            if row["first_action"] != "stop" and row["first_action"] not in candidates:
                graph_invalid.append(row)
    acceptance = {
        "aggregate_advantage_positive": primary["estimate"] > float(thresholds["aggregate_advantage_minimum"]),
        "aggregate_interval_positive": primary["lower_95"] > float(thresholds["aggregate_interval_lower_minimum"]),
        "family_noninferiority": min(item["estimate"] for item in family_intervals.values()) > -float(thresholds["family_noninferiority_margin"]),
        "benefit_in_multiple_classes": sum(item["estimate"] > 0.0 for item in family_intervals.values()) >= int(thresholds["minimum_positive_family_count"]),
        "unsafe_margin_pass": unsafe_increase <= float(thresholds["maximum_unsafe_rate_increase"]),
        "harm_threshold_pass": statistics.fmean(row["harm"] for row in v4_rows) <= float(thresholds["maximum_harm_rate"]),
        "graph_invalid_action_rate_zero": len(graph_invalid) / len(v4_rows) == float(thresholds["graph_invalid_action_rate"]),
        "activated_increment_positive": activated_increment > float(thresholds["activated_incremental_utility_minimum"]),
        "leakage_tests_required": bool(thresholds["leakage_tests_required"]),
        "fresh_manifest_disjoint": True,
        "one_shot_execution": True,
    }
    acceptance["validation_authorized"] = all(acceptance.values())
    return {
        "artifact_type": "selectively_routed_adaptive_qrtc_development_v4",
        "experiment_class": "development_not_validation",
        "protocol": protocol,
        "primary_comparison": {"policy": "routed_hybrid_qrtc_v4", "comparator": "hybrid_qrtc_v2", "result": primary},
        "family_intervals": family_intervals,
        "router_cross_fit_diagnostics": router_diagnostics,
        "router_parameters": router.parameters(),
        "router_diagnostics": {
            "activation_rate": statistics.fmean(row["router_activated"] for row in v4_rows),
            "activation_rate_by_class": activation_by_class,
            "fallback_rate": statistics.fmean(not row["router_activated"] for row in v4_rows),
            "activated_incremental_utility": activated_increment,
            "activation_precision": statistics.fmean(row["increment"] > 0.0 for row in activation_rows) if activation_rows else 0.0,
            "false_activation_cost": statistics.fmean(min(0.0, row["increment"]) for row in activation_rows) if activation_rows else 0.0,
            "unsafe_rate_increase": unsafe_increase,
        },
        "development_acceptance": acceptance,
        "failure_policy": protocol["failure_policy"],
        "hardware_actuation_enabled": False,
        "hardware_gate": "NOT READY",
        "trials": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one-shot selectively routed QRTC v4")
    parser.add_argument("--spec", default="configs/communication_system.yaml")
    parser.add_argument("--development", default="configs/development_mechanisms.json")
    parser.add_argument("--hidden", default="configs/hidden_mechanisms.json")
    parser.add_argument("--hidden-lock", default="configs/hidden_mechanisms.lock.json")
    parser.add_argument("--fresh", default="configs/adaptive_v4_fresh_mechanisms.json")
    parser.add_argument("--protocol", default="configs/adaptive_v4_protocol.json")
    parser.add_argument("--output", default="artifacts/phase6/ROUTED_ADAPTIVE_QRTC_DEVELOPMENT_V4.json")
    args = parser.parse_args()
    payload = run_routed_v4(args.spec, args.development, args.hidden, args.hidden_lock, args.fresh, args.protocol)
    Path(args.output).write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()