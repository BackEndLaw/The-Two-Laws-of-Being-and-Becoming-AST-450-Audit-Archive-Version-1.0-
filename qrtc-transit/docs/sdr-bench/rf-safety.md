# SDR Bench RF Safety Document

**Document ID:** sdr-bench-rf-safety-v1  
**Date:** 2026-08-03  
**Status:** DRAFT — requires qualified bench review before physical connection  
**Protocol:** sdr-bench-candidate-a-v1  

---

## 1. Scope and Purpose

This document defines the RF safety requirements, worst-case power calculations, and operating procedures for the SDR observation-only bench (Candidate A: HackRF One transmitter + RTL-SDR Blog V3 receiver). It must be reviewed and signed off by a qualified RF engineer or bench supervisor before any hardware is connected.

**This document does not authorise physical connection.** It provides the information needed for a qualified reviewer to make that authorisation.

---

## 2. Hardware Under Review

| Device | Role | Connector |
|---|---|---|
| HackRF One (r9 or later) | Transmitter | SMA female |
| RTL-SDR Blog V3 | Receiver | SMA female |
| Mini-Circuits or equivalent fixed 20 dB attenuator, SMA, 1 W | Fixed protective attenuation | SMA |
| Programmable/stepped 0–30 dB attenuator, SMA | Sweep attenuation | SMA |
| SMA DC block | Bias/DC isolation | SMA |
| RG-316 50-ohm coaxial cable, SMA-SMA, 0.5 m × 2 | Signal path | SMA |
| 50-ohm SMA terminator × 2 | Unused port loads | SMA |

---

## 3. Connection Diagram

```
[HackRF One TX port]
    │
    │ SMA coax (0.5 m, RG-316)
    │
[DC Block]  ← prevents bias/DC propagation from HackRF to attenuator chain
    │
    │ SMA
    │
[Fixed 20 dB attenuator, 1 W SMA]  ← ALWAYS IN-CIRCUIT; never bypassed
    │
    │ SMA
    │
[Programmable 0–30 dB attenuator]  ← stepped per scenario script
    │
    │ SMA coax (0.5 m, RG-316)
    │
[RTL-SDR Blog V3 RX port]

All unused SMA ports → 50-ohm terminators
HackRF antenna port → 50-ohm terminator (no radiation)
RTL-SDR antenna port → connected only through attenuator chain above
```

---

## 4. Power Calculations

### Manufacturer-Specified Limits

> **IMPORTANT:** The values below are derived from manufacturer datasheets and public documentation for the specific hardware revisions listed. They must be verified against the actual datasheets for the hardware on-hand before use.

#### HackRF One (r9)

| Parameter | Value | Source |
|---|---|---|
| Maximum TX output power at 433 MHz | +10 dBm (10 mW) | HackRF One datasheet, Great Scott Gadgets |
| TX power range | −40 to +10 dBm (software controlled via TX VGA gain) | HackRF One documentation |
| TX frequency range | 1 MHz – 6 GHz | HackRF One datasheet |
| TX connector | SMA female, 50 Ω | Physical inspection + datasheet |

#### RTL-SDR Blog V3

| Parameter | Value | Source |
|---|---|---|
| Absolute maximum RX input power | +10 dBm | RTL-SDR Blog V3 product page and datasheet |
| Recommended operating range | −50 to 0 dBm | RTL-SDR Blog V3 documentation |
| Noise figure at 433 MHz | approx. 3.5 dB (with LNA enabled) | RTL-SDR Blog V3 measured characterisation |
| Noise floor at 433 MHz, 1 MHz bandwidth | approx. −100 to −105 dBm | Computed: kTB + noise_figure |
| Frequency range | 500 kHz – 1766 MHz (direct sampling) | RTL-SDR Blog V3 datasheet |

#### Fixed 20 dB Attenuator

| Parameter | Value |
|---|---|
| Nominal attenuation | 20 dB |
| Power rating | 1 W (30 dBm) |
| Connector | SMA, 50 Ω |
| Frequency range | DC – 6 GHz (typical for SMA pad attenuator) |

#### Programmable/Stepped Attenuator

| Parameter | Value |
|---|---|
| Attenuation range | 0 – 30 dB |
| Step size | 5 dB |
| Power rating | Minimum 0.5 W; use only with fixed attenuator in-circuit |

---

### Normal Operation Power Budget (Node-Level)

All power levels in dBm.

| Node | Value (dBm) | Notes |
|---|---|---|
| HackRF TX output (max) | +10 | Manufacturer maximum |
| After DC block | +9.5 | −0.5 dB typical insertion loss |
| After fixed 20 dB attenuator | −10.5 | −20 dB |
| After programmable at 0 dB step | −10.5 | No additional attenuation |
| After programmable at 30 dB step | −40.5 | Maximum attenuation |
| After 0.5 m RG-316 coax | −10.7 to −40.7 | −0.2 dB typical |
| RTL-SDR RX input | **−10.7 to −40.7** | Well within operating range |
| RTL-SDR absolute maximum input | +10 | Datasheet limit |
| **Protection margin (worst case)** | **+10 − (−10.7) = 20.7 dB** | At 0 dB programmable attenuation |

**Conclusion: PASS.** The protection margin is 20.7 dB even with no programmable attenuation. The RTL-SDR input is safe at all attenuator states.

---

### Single-Fault Cases

| Fault scenario | RTL-SDR input | Above limit? | Action |
|---|---|---|---|
| Fixed attenuator removed, 0 dB prog. | +9.5 dBm | NO (10 − 9.5 = 0.5 dB margin) | CRITICAL — fixed attenuator must never be removed |
| Fixed attenuator removed, 30 dB prog. | −20.5 dBm | NO | Still safe, but fixed attenuator must never be removed |
| DC block fails short | +9.5 dBm | NO, but DC on line | Replace DC block; verify no damage to attenuator |
| Coax disconnects at RX | RX open | N/A | HackRF transmits to open; no damage; reconnect |
| HackRF TX gain misconfigured (+20 dBm attempted) | +20 dBm is above HackRF spec | HackRF clips at +10 dBm; hardware maximum | Verify HackRF TX gain does not exceed +10 dBm |
| Both attenuators fail short | +9.5 dBm | NO (0.5 dB margin) | Marginal; replace components before use |

**Critical safety rule: The fixed 20 dB attenuator must remain in-circuit at all times. There is no software interlock for this — it is a physical hardware requirement.**

---

## 5. Protective Attenuation Configuration

### Required Protective Elements (in order from HackRF to RTL-SDR)

1. **Fixed 20 dB attenuator** — always in-circuit; cannot be bypassed or removed
2. **DC block** — placed between HackRF and the fixed attenuator
3. **Programmable attenuator** — adds 0–30 dB of additional attenuation per scenario script

The fixed attenuator is the primary protection element. The programmable attenuator is for scenario control, not for primary receiver protection.

---

## 6. Cables, Adapters, DC Block, and Terminations

| Component | Purpose | Notes |
|---|---|---|
| RG-316 SMA-SMA, 0.5 m | HackRF TX to attenuator chain | Low-loss; rated to 3 GHz |
| RG-316 SMA-SMA, 0.5 m | Attenuator chain to RTL-SDR RX | Same spec |
| DC block (SMA) | Block DC bias/path from HackRF | Prevents DC from HackRF bias-T reaching attenuator and receiver |
| 50-ohm SMA terminator | HackRF antenna port (unused) | Prevents unintended radiation |
| 50-ohm SMA terminator | RTL-SDR antenna port (unused) | Prevents unintended radiation |

All SMA connectors must be torqued to 3–5 in-lbs (0.34–0.56 N·m) using a torque wrench. Do not use bare hands only for critical connections.

---

## 7. Power-On Sequence

1. **Verify fixed 20 dB attenuator is in-circuit** — visual inspection.
2. **Verify DC block is in-circuit** — visual inspection.
3. **Verify all unused SMA ports have 50-ohm terminators** — visual inspection.
4. **Connect coaxial cable** from HackRF TX through attenuator chain to RTL-SDR RX.
5. Power on host PC.
6. Start RTL-SDR driver: `rtl_power` or GNU Radio `RTL-SDR Source` block.
7. Start HackRF driver at minimum TX gain (TX disabled or −40 dBm equivalent).
8. Enable HackRF TX at protocol power level (+10 dBm maximum).
9. **Measure RTL-SDR input power before any scenario begins.** It must be ≤ −10 dBm.
10. If measurement confirms safe power level: proceed with warm-up and testing.

---

## 8. Power-Off Sequence

1. Run the GNU Radio flowgraph stop command.
2. Set HackRF TX gain to minimum (disable transmit).
3. Close RTL-SDR driver gracefully.
4. Disconnect coaxial cable between HackRF and attenuator chain.
5. Power off HackRF.
6. Power off host PC.

---

## 9. Emergency Power Isolation

An **emergency power isolation switch** must be accessible to the bench operator at all times without requiring software interaction. Options:

- A switched mains power strip that cuts power to the HackRF host PC (which controls HackRF via USB).
- A physical USB switch between the host PC and HackRF.

The switch must be tested (power off and confirm HackRF stops transmitting) before any scenario begins.

**The emergency stop switch is a prerequisite for running any physical test. Do not begin testing without a tested emergency stop.**

---

## 10. Receiver Protection Margin Summary

| Condition | RTL-SDR input | Margin to +10 dBm limit | Status |
|---|---|---|---|
| Normal: max HackRF, 0 dB prog. | −10.7 dBm | 20.7 dB | ✅ SAFE |
| Normal: max HackRF, 30 dB prog. | −40.7 dBm | 50.7 dB | ✅ SAFE |
| Single fault: fixed att. removed, 0 dB prog. | +9.5 dBm | 0.5 dB | ⚠️ CRITICAL — do not operate without fixed attenuator |
| Single fault: both att. fail short | +9.5 dBm | 0.5 dB | ⚠️ CRITICAL — replace components |

---

## 11. Known Limitations of This Document

1. Power values for the HackRF One and RTL-SDR V3 are from manufacturer documentation and public characterisation reports. They must be verified against the specific hardware revisions and serial numbers on-hand before use.
2. This document does not substitute for an on-bench measurement with a calibrated power meter before any scenario begins.
3. The RTL-SDR V3 noise floor value (approx. −100 dBm) is frequency- and bandwidth-dependent. It must be measured on-bench for the specific frequency (433.92 MHz) and bandwidth (25 kHz) in use.
4. Cable insertion loss values are approximate (−0.2 dB per 0.5 m at 433 MHz). They should be verified with a VNA if available.
5. This document has not been reviewed by a qualified RF engineer. **It must be reviewed before any hardware is connected.**

---

## 12. Review and Sign-Off

This document requires review and written sign-off by a qualified RF engineer or bench supervisor before physical connection. The reviewer must verify:

- [ ] Manufacturer power limits confirmed from actual datasheets for hardware on-hand
- [ ] Fixed attenuator rating verified (≥ 20 dB, ≥ 1 W power handling)
- [ ] RTL-SDR V3 absolute maximum input confirmed from datasheet (not assumed to be +10 dBm)
- [ ] Protection margin confirmed ≥ 20 dB at all attenuator states
- [ ] Emergency stop switch tested
- [ ] All SMA connectors torqued correctly
- [ ] No substitutions or omissions from the component list

**Reviewer:** ___________________________  
**Date:** ___________________________  
**Qualification:** ___________________________  
**Signature:** ___________________________
