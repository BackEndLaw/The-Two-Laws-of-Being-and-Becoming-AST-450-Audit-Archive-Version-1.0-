# Controller Candidate Inventory v1

Selection status: all entries below are **candidates**. No controller has been selected yet.

`qrtc` is the provisional primary candidate.

Final validation remains locked. This PR does not execute controller selection.

“Hybrid QRTC V2” is not an implemented controller.

| candidate_id | version | role | deployable | abstention / evidence behavior | causal / dependency awareness | implementation location | selection status |
|---|---|---|---|---|---|---|---|
| `qrtc` | `phase5b-rule-policy-v1` | primary | yes | unknown faults request evidence (`r0`) | yes (relation + dependency aware) | `src/qrtc_benchmark/controllers.py` | candidate |
| `qrtc_no_abstention` | `phase5b-rule-policy-v1` | ablation | yes | no abstention on unknown faults (cheapest non-`r0`) | limited | `src/qrtc_benchmark/controllers.py` | candidate |
| `qrtc_untyped` | `phase5b-rule-policy-v1` | ablation | yes | unknown faults request evidence (`r0`) | reduced (cost-sorted, untyped behavior) | `src/qrtc_benchmark/controllers.py` | candidate |
| `greedy_gain` | `phase5b-rule-policy-v1` | baseline | yes | unknown faults choose `rB` | minimal | `src/qrtc_benchmark/controllers.py` | candidate |
| `oracle` | `phase5b-rule-policy-v1` | oracle | no | benchmark-only utility ceiling | uses benchmark oracle evaluator | `src/qrtc_benchmark/controllers.py` + `src/qrtc_benchmark/phase5.py` | candidate |
| `end_to_end` | `phase5b-rule-policy-v1` | baseline | yes | unknown faults choose `rD` | none | `src/qrtc_benchmark/controllers.py` | optional descriptive baseline |
| `highest_stage_posterior` | `phase5b-rule-policy-v1` | baseline | yes | unknown faults choose `rJ` | none | `src/qrtc_benchmark/controllers.py` | optional descriptive baseline |
| `cheapest_first` | `phase5b-rule-policy-v1` | baseline | yes | cheapest action bias | no causal typing | `src/qrtc_benchmark/controllers.py` | optional descriptive baseline |
| `random` | `phase5b-rule-policy-v1` | baseline | yes | random one-step action | none | `src/qrtc_benchmark/controllers.py` | optional descriptive baseline |

Oracle caveat: `oracle` is non-deployable and must not be loaded for deployable advisor use unless explicitly allowed for benchmark analysis.
