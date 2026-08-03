# Phase V-B Selection-Validation Report

**Stage:** selection-validation  
**Protocol:** `phase5b-selection-v1`  
**Protocol hash:** `fc6b86912182d216be4d381992732345cc5d6a38299d6c5946ab1b8fe2bfe77c`  
**Source commit:** `8f06e2271c58b624ee210df504056a7862dbf30e`  
**Implementation commit:** `6aa56a7abae975274e95a9ba2941fe2002794592`  
**Outcome:** `provisional_selection`  
**Selected controller:** `qrtc`  

Selection-validation was executed under the frozen preregistered protocol.
Exact decision: **provisional selection: `qrtc`**.

## Required safety statements

- Any selected controller is **provisional only**.
- `oracle` is **not deployable** and was never eligible.
- Final-validation remains **locked and not executed**.
- No hardware authority is granted.

## Eligibility

| Candidate | Deployable | Eligible | Superior vs greedy_gain | Reasons |
|---|---:|---:|---:|---|
| qrtc | yes | yes | yes | — |
| qrtc_no_abstention | yes | yes | yes | — |
| qrtc_untyped | yes | yes | yes | — |
| greedy_gain | yes | no | no | gate3: overall unsafe-commitment rate 0.25 != 0.0; gate4: unsafe-commitment count 1200 in OOD family 'V4' > 0 |
| oracle | no | no | yes | oracle is non-deployable and never eligible to win |

## Candidate summary

| Candidate | Mean utility | Recovery rate | Mean cost | Mean harm | Unsafe rate |
|---|---:|---:|---:|---:|---:|
| qrtc | 0.369781 | 0.615417 | 4.801250 | 0.022292 | 0.000000 |
| qrtc_no_abstention | 0.057286 | 0.301042 | 3.743333 | 0.226354 | 0.000000 |
| qrtc_untyped | 0.164385 | 0.433958 | 5.263333 | 0.025625 | 0.000000 |
| greedy_gain | -0.030214 | 0.301042 | 4.493333 | 0.226354 | 0.250000 |
| oracle | 0.484885 | 0.666250 | 3.593958 | 0.006667 | 0.000000 |

## Paired bootstrap comparisons

| Comparison | Mean Δ | CI low | CI high |
|---|---:|---:|---:|
| greedy_gain vs greedy_gain | 0.000000 | 0.000000 | 0.000000 |
| greedy_gain vs qrtc | -0.399995 | -0.412671 | -0.388023 |
| qrtc_no_abstention vs greedy_gain | 0.087500 | 0.082238 | 0.092938 |
| qrtc_no_abstention vs qrtc | -0.312495 | -0.324942 | -0.301197 |
| qrtc_untyped vs greedy_gain | 0.194599 | 0.182115 | 0.207486 |
| qrtc_untyped vs qrtc | -0.205396 | -0.218303 | -0.192998 |
| qrtc vs greedy_gain | 0.399995 | 0.387934 | 0.412555 |
| qrtc vs qrtc_untyped | 0.205396 | 0.192975 | 0.218221 |
