# Physical Communication-Link Bench Selection

**Document type:** Bench-selection decision package  
**Stage:** Step 6 — first physical test preparation  
**Date:** 2026-08-03  
**Status:** Decision package only. No hardware has been purchased or connected. No tests have been executed.

---

## 1. Context and Constraints

RescueOS Advisor operates under `authority = recommend_only` and `hardware_actuation_enabled = false`. The first physical test must be **observation-only**:

```
Physical communication link
→ controlled degradation
→ real telemetry
→ RescueOS Advisor observation
→ explained recommendation or abstention
→ audit record
```

No command path from the Advisor to physical hardware is permitted at this stage.

### Frozen observation schema (`phase5-ood-case-v1`)

The Advisor ingests structured fault observations with the following fields:

| Field | Type | Values |
|-------|------|--------|
| `family` | enum | V1, V2, V3, V4 |
| `mechanism_id` | str | arbitrary |
| `composition_id` | str | arbitrary |
| `relation_type` | enum | strict_masking, soft_masking, independent, synergistic |
| `criterion` | str | arbitrary |
| `severity` | float | [0, 1] |
| `noise` | float | [0, 1] |
| `dependency_type` | enum | none, chain, fork, partial_sufficiency |
| `unknown_fault` | bool | — |
| `evidence_initially_insufficient` | bool | — |
| `required_actions` | list[enum] | rG, rB, rR, rW, rD, rJ, r0, stop |

A **schema adapter** maps physical telemetry to these fields. The adapter is outside the frozen controller and may be written without modifying any validated artifact.

---

## 2. Minimum Bench Requirements

1. Real communication transmitter and receiver, or representative physical radio/modem hardware.
2. Accessible receiver/transmitter telemetry (RSSI, SNR, BER, packet-loss rate, latency, link-state flags).
3. Timestamped observation collection at ≥ 1 Hz, exported in JSON or CSV.
4. Documented communication protocol (modulation, frequency, data rate, frame format).
5. Controllable and repeatable impairment source (attenuator, interference generator, or range extension).
6. Safe, isolated, or appropriately licensed operation (shielded room, licensed band with appropriate coordination, or sub-GHz ISM band at low power).
7. Ability to record ground truth (known impairment level vs. measured degradation).
8. External emergency stop or power isolation switch accessible without software.
9. No autonomous actuation: Advisor output is logged only; no feedback path to the transmitter.
10. Data-export format compatible with, or deterministically mappable to, `phase5-ood-case-v1`.

---

## 3. Bench Candidates

### Candidate A — Software-Defined Radio (SDR) Loopback Bench

**Exact hardware**
- 2× RTL-SDR v3 (or HackRF One) USB dongles — transmit/receive pair
- Attenuator: Mini-Circuits VAT series, 0–30 dB programmable (or fixed-step Pi-pad)
- Host PC running GNU Radio 3.10 + Python 3.11
- SMA cables, low-power coaxial setup (no antenna radiation required)

**Communication medium and frequencies**
- ISM 433 MHz or 868 MHz; fully contained coax connection, no radiation licence required at bench
- Data rate: 9.6–38.4 kbit/s FSK or OOK

**Telemetry available**
- RSSI (dBm), SNR (dB), BER (bit errors / frame), packet-loss rate, frame sequence number, timestamp (µs resolution from GNU Radio)
- Link state: CONNECTED / DEGRADED / LOST derived from loss threshold

**Impairments that can be introduced safely**
- Step attenuation 0–30 dB (simulates range / path loss)
- Gaussian noise injection via GNU Radio block
- Duty-cycle jamming at adjustable power level (contained within the coax link)
- Channel blocking (transmitter disabled)

**Schema-mapping effort**
- `severity` ← normalised path-loss ratio (measured RSSI / baseline RSSI)
- `noise` ← BER or PER
- `family` ← V3 (three-fault causal chain: path-loss → SNR degradation → packet loss)
- `dependency_type` ← chain
- `relation_type` ← independent (attenuation and noise sources are separable)
- `required_actions` ← mapped from impairment level bands
- Adapter: ~150 lines of Python; 1–2 days

**Estimated equipment cost**
- 2× RTL-SDR v3: ~$60
- HackRF One (if TX needed): ~$350
- Attenuator + cables: ~$80
- Total: $140–$490

**Setup time**: 1–2 days (software only after hardware arrives)

**Safety or licensing constraints**
- No radiation if coax loopback used; no licence required
- GNU Radio is free software; no export restriction at these power levels

**Reproducibility**: High — attenuation steps are deterministic; GNU Radio replay available

**Command capability physically disabled**: Yes — transmitter is a passive test signal generator; no back-channel to SDR from Advisor

**Principal risks**
- RTL-SDR cannot transmit (receive-only); HackRF required for full duplex; adds cost
- SDR timing jitter ±50 µs; acceptable for ≥ 1 Hz telemetry
- Mapping `required_actions` from RF metrics requires domain calibration run

---

### Candidate B — Wi-Fi 802.11 Access-Point Bench with Traffic Shaping

**Exact hardware**
- 1× Raspberry Pi 5 (AP, hostapd 2.10)
- 1× Raspberry Pi 5 or laptop (client)
- 2.4 GHz or 5 GHz 802.11n/ac, restricted to lab channel
- tc-netem (Linux kernel traffic-control) for latency/loss injection
- iw / iwconfig / iw survey for RSSI, noise floor
- iperf3 for throughput measurement

**Communication medium and frequencies**
- 2.4 GHz 802.11b/g/n channel 1 (or 5 GHz channel 36); isolated SSID, WPA2-PSK, no internet

**Telemetry available**
- RSSI (dBm), noise floor, MCS index, tx/rx rate, retransmit count, beacon interval, associated station count — available via `iw dev wlan0 station dump` at 1 Hz
- tc-netem reports: injected delay, jitter, loss percentage — ground truth

**Impairments that can be introduced safely**
- tc-netem: packet-loss 0–100%, latency 0–500 ms, corruption, reorder
- Transmit power reduction via `iw set txpower`
- Physical: microwave oven (2.4 GHz) or co-channel AP for interference — used only inside RF-attenuated enclosure or lab isolation

**Schema-mapping effort**
- `severity` ← normalised RSSI degradation
- `noise` ← packet-loss rate (netem setting matches measurement)
- `family`, `dependency_type`, `relation_type` mapped as Candidate A
- Adapter: ~120 lines; 1 day (Raspberry Pi software stack well documented)

**Estimated equipment cost**
- 2× Raspberry Pi 5 (4 GB): ~$160
- USB Wi-Fi adapters + cables: ~$30
- Total: ~$190

**Setup time**: 0.5–1 day (if Raspberry Pis already available)

**Safety or licensing constraints**
- 2.4 GHz ISM — no licence required; keep to ≤ 20 dBm and within a room or RF enclosure
- No external interference to licensed bands

**Reproducibility**: Medium-high — netem parameters are scripted and deterministic; RF environment can vary if not shielded

**Command capability physically disabled**: Yes — Advisor reads log files; no Wi-Fi send path from Advisor

**Principal risks**
- Wi-Fi RSSI measurements are noisy (±3–5 dB variation between polls); averaging required
- netem and RF-channel impairments are not independent: mapping to schema requires calibration
- Lab RF environment may introduce uncontrolled variation

---

### Candidate C — Dedicated Sub-GHz LoRa Bench (SX1276 / SX1262)

**Exact hardware**
- 2× Adafruit FeatherM0 with LoRa (SX1276) or RAK4631 (SX1262)
- Host PC with Python 3.11 + pyserial for telemetry collection
- Variable attenuator: RFMD/Skyworks 0–30 dB (or fixed pads)
- SMA coaxial connection, 868 MHz or 915 MHz sub-GHz ISM band

**Communication medium and frequencies**
- 868 MHz (EU ISM) or 915 MHz (US ISM); spreading factor SF7–SF12 adjustable
- Data rate: 0.25–50 kbit/s; link budget > 140 dB

**Telemetry available**
- RSSI (dBm), SNR (dB), packet count, CRC-error count, spreading-factor setting — exposed by SX1276 register reads after each packet receive
- Timestamp: host-side microsecond-resolution reception time

**Impairments that can be introduced safely**
- Step attenuation 0–30 dB (coax, no radiation)
- SF change (increases/decreases sensitivity deterministically)
- TX power reduction (SX1276 PA_CONFIG register, 2–20 dBm)
- Duty-cycle pause (suspend transmitter) to simulate link loss

**Schema-mapping effort**
- `severity` ← (RSSI – sensitivity_floor) / dynamic_range, normalised
- `noise` ← CRC-error rate over window
- `family` ← V3; `dependency_type` ← chain; `relation_type` ← independent
- `required_actions` ← banded from RSSI+SNR joint threshold
- Adapter: ~200 lines; 2–3 days (custom serial framing required)

**Estimated equipment cost**
- 2× FeatherM0 LoRa: ~$80
- Attenuator + SMA cables: ~$80
- Total: ~$160

**Setup time**: 2–3 days (custom firmware telemetry export needed)

**Safety or licensing constraints**
- 868/915 MHz sub-GHz ISM; no licence at ≤ 25 mW; coax eliminates radiation
- EU duty-cycle limit (1%) irrelevant in lab coax configuration

**Reproducibility**: High — SF and TX power are register-controlled and stable; spreading-factor sweep is fully scripted

**Command capability physically disabled**: Yes — host PC reads serial telemetry only; no write path from Advisor to hardware

**Principal risks**
- FeatherM0 firmware requires custom telemetry-export code (no off-the-shelf RSSI stream)
- 2–3 day adapter development vs. 1 day for Wi-Fi bench
- LoRa packets at SF12 are slow (several seconds per packet); may require reduced impairment granularity

---

## 4. Recommended Bench

**Recommendation: Candidate A — SDR Loopback Bench (HackRF One + RTL-SDR)**

### Selection criteria and scores

| Criterion | Weight | A (SDR) | B (Wi-Fi) | C (LoRa) |
|-----------|--------|---------|-----------|----------|
| Schema compatibility | High | ✅ Direct mapping | ✅ Direct mapping | ✅ Direct mapping |
| Observation quality | High | ✅ µs timestamps, deterministic RF | ⚠️ RSSI noisy ±5 dB | ✅ SNR/RSSI stable |
| Repeatability | High | ✅ Scripted attenuation | ⚠️ RF environment varies | ✅ Register-controlled |
| Safety | High | ✅ Coax only, no radiation | ✅ No licence required | ✅ Coax only |
| Cost | Medium | ⚠️ $490 if HackRF needed | ✅ $190 | ✅ $160 |
| Setup time | Medium | ✅ 1–2 days | ✅ 0.5–1 day | ⚠️ 2–3 days |
| Auditability | High | ✅ GNU Radio records raw IQ | ✅ pcap + netem logs | ✅ Serial log |
| Actuation isolation | High | ✅ SDR is passive on RX path | ✅ Log-only Advisor | ✅ Log-only Advisor |

**Rationale:** The SDR bench offers the highest observation quality and repeatability because (a) the attenuation step is applied at the RF level with no software-induced jitter, (b) GNU Radio timestamps packets to microsecond resolution, (c) raw IQ captures provide an independent audit trail, and (d) the receive-only nature of the RTL-SDR ensures there is no physical command path from the Advisor. The Wi-Fi bench is faster to set up but introduces uncontrolled RF variation. The LoRa bench is equally clean but requires more custom firmware work.

---

## 5. First Physical Test Definition

### Test: Observation-Only Communication-Link Degradation Assessment

**Data flow:**
```
SDR receiver (RTL-SDR)
→ GNU Radio telemetry collector (RSSI, SNR, BER, timestamp)
→ schema adapter (Python, ~150 lines)
→ RescueOS Advisor (load_selected_controller_bundle, no source repo)
→ recommendation / evidence-request / abstention
→ JSON audit record (decision_sha256 verified)
```

**No command path:** The Advisor process has no network or serial connection to the SDR transmitter.

---

## 6. Entry Criteria

Before executing the bench test, all of the following must be satisfied:

1. RELEASE_RECORD.json is committed and its checksum is recorded.
2. `qrtc_transit-0.1.0-py3-none-any.whl` SHA-256 verified: `c3a37c7a3e134d73523bc2d073732b871902a65606563dd2b1d6986a16b0b7c0`.
3. `phase5b-rule-policy-v1/manifest.json` SHA-256 verified: `3a5845cbcda7260497050dfd027787fa06d0e3f02dc49e23d7ea2af8a868bcc1`.
4. Decision checksum reproduced: `2928653190c53335bd7b78862283d1118aba3b63c83eb0126f3b63c8c0f12f47`.
5. Schema adapter produces byte-identical output for two identical input vectors (adapter determinism confirmed).
6. SDR bench hardware assembled and baseline RSSI stable ± 1 dB at 0 dB attenuation over 60 s.
7. Attenuation sweep 0–30 dB produces monotonic RSSI decrease verified against expected path-loss model.
8. Emergency power isolation accessible and tested (removes transmitter power without software command).
9. Advisor process has no open socket or serial port to the transmitter host.
10. All test scripts committed to a feature branch; no modifications to validated artifacts.

---

## 7. Exit Criteria (numerical)

All ten categories must pass for the bench test to be declared complete:

| Category | Pass threshold |
|----------|---------------|
| **Observation integrity** | ≥ 99% of 1 Hz telemetry frames collected; timestamp gap ≤ 2 s in any 60 s window |
| **Schema mapping** | Adapter output is byte-identical for 100% of repeat runs on the same input vector |
| **Detection** | Advisor produces non-`stop` recommendation for ≥ 95% of attenuation steps ≥ 15 dB (known degradation) |
| **Recommendation admissibility** | 100% of Advisor outputs pass `load_selected_controller_bundle` causal-graph check |
| **Abstention** | Advisor outputs `r0` (abstain) or flags `evidence_initially_insufficient = true` for ≥ 90% of injected ambiguous states (SNR 0–3 dB, simultaneous high attenuation and noise) |
| **Latency** | End-to-end Advisor response (telemetry receipt → JSON audit record written) ≤ 500 ms at p99 over 100 observations |
| **Repeatability** | Identical attenuation-step sequences produce the same Advisor action sequence on ≥ 95% of runs (across ≥ 3 replays) |
| **Auditability** | 100% of Advisor outputs have a recorded `decision_sha256` that can be independently recomputed from the stored inputs |
| **Isolation** | Zero bytes transmitted from Advisor host to SDR transmitter host during entire test (verified by network monitor) |
| **Recovery** | Advisor action sequence returns to baseline (`stop` or low-cost single action) within 3 telemetry cycles after impairment removal in ≥ 95% of recovery trials |

---

## 8. Pre-Purchase Cost Summary

| Item | Unit cost | Quantity | Total |
|------|-----------|----------|-------|
| HackRF One (TX capable SDR) | $350 | 1 | $350 |
| RTL-SDR v3 (RX SDR) | $30 | 1 | $30 |
| Mini-Circuits 0–30 dB step attenuator (or fixed pads + SMA T) | $60 | 1 | $60 |
| SMA coaxial cables (30 cm) | $15 | 4 | $60 |
| Total | | | **$500** |

*If a suitable SDR already exists in the lab, cost reduces to attenuator + cables: ~$120.*

**Exact proposed tests:**
1. Baseline RSSI stability (60 s, 0 dB attenuation, 100 observations)
2. Monotonic attenuation sweep (0→30 dB in 5 dB steps, 30 observations per step, 3 replays)
3. Ambiguous-state injection (SNR 0–3 dB, 50 observations, check abstention rate)
4. Recovery test (15 dB attenuation → 0 dB, 30 cycles)
5. Schema determinism check (100 identical input vectors, 2 back-to-back runs)

**Expected duration:** 4–6 hours of bench time after hardware setup (1–2 days setup).

**Evidence each test will produce:**
- JSON telemetry log (timestamped RSSI/SNR/BER per observation)
- JSON adapter output log (schema-mapped observation per telemetry frame)
- JSON Advisor output log (action sequence, decision_sha256, causal explanation per observation)
- Pass/fail summary against numerical exit criteria above

---

## 9. What Follows a Passing Bench Test

```
observation-only SDR bench (this document)
→ stationary secured vehicle integration (shadow mode)
→ real-driving shadow mode (observe, no actuation)
→ human-authorized low-risk actions (only if required)
→ closed-course bounded automation (only if required)
```

No step may begin until the preceding step's exit criteria are met and documented.

---

## 10. Verification Against Release Record

Before executing any bench test, verify the release record checksum:

```bash
sha256sum RELEASE_RECORD.json
# expected: ffe9fae80bf1940fd729e8ff1466ee4079a4f799847abf159e407130330d973a
```

If the checksum does not match, halt and report **RELEASE SEAL FAILED**.
