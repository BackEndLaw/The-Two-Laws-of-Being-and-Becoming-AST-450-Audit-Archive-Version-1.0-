# Hardware Acquisition Decision Package — SDR Bench Candidate A

**Document ID:** sdr-bench-acquisition-v1  
**Date:** 2026-08-03  
**Status:** PENDING — for review and authorisation before purchase  
**Protocol:** sdr-bench-candidate-a-v1  

---

## 1. Purpose

This package defines the exact hardware to purchase for the SDR observation-only bench, itemised costs, acceptable substitutions, and conditions that must be met before purchase is authorised.

**Do not purchase hardware before the desk-side prerequisites (observation mapping, protocol, harness, RF safety review) have passed review.** The estimated total is small relative to the preceding software work, but purchase creates physical commitments and should follow confirmed desk-side approval.

---

## 2. Whether Any Equipment Is Already Available

Before purchase, verify whether any of the following items are already in-lab:

- [ ] HackRF One or similar full-duplex SDR (capable of TX at 433 MHz)
- [ ] RTL-SDR receiver dongle (any revision with SMA connector)
- [ ] SMA attenuators (fixed and/or programmable)
- [ ] SMA coaxial cables, DC blocks, terminators
- [ ] Host PC running Linux with USB 3.0+ port

If a suitable transmitter-capable SDR is already available, the largest cost item ($340) is eliminated.

---

## 3. Bill of Materials

### Required — No Substitution

| # | Item | Manufacturer / Model | Specification | Quantity | Unit cost (USD, approx.) | Total (USD) | Vendor example |
|---|---|---|---|---|---|---|---|
| 1 | Software-Defined Radio (TX+RX) | Great Scott Gadgets **HackRF One** | 1 MHz – 6 GHz, +10 dBm TX max, SMA, open-source hardware | 1 | $340 | $340 | greatscottgadgets.com; Mouser; Digi-Key |
| 2 | RTL-SDR Receiver | RTL-SDR Blog **V3** | 500 kHz – 1766 MHz, direct sampling, SMA, ~3.5 dB NF | 1 | $32 | $32 | rtl-sdr.com; Amazon |
| 3 | Fixed SMA attenuator, 20 dB | Mini-Circuits **VAT-20W2+** or equivalent | 20 dB, 2 W, SMA, DC – 3 GHz, 50 Ω | 1 | $12 | $12 | minicircuits.com; Mouser |
| 4 | SMA DC block | Mini-Circuits **BLK-89-S+** or Fairview FMDC0016 | DC – 3 GHz, SMA, ≤ 0.5 dB insertion loss | 1 | $25 | $25 | minicircuits.com; Mouser |
| 5 | 50-ohm SMA terminator (2-pack) | Generic SMA 50 Ω load terminator | SMA male, 1 W, DC – 3 GHz | 1 pack | $8 | $8 | Mouser; Amazon |
| 6 | RG-316 SMA-SMA coax, 50 cm | Generic or Mini-Circuits CBL-0.5FT-SMSM+ | RG-316, SMA male both ends, 50 cm (or two 50 cm pieces) | 2 | $8 | $16 | minicircuits.com; Amazon |

**Required subtotal: $433**

---

### Strongly Recommended — Controllable Attenuation Sweep

| # | Item | Manufacturer / Model | Specification | Quantity | Unit cost (USD) | Total (USD) | Notes |
|---|---|---|---|---|---|---|---|
| 7 | Fixed SMA attenuator, 10 dB | Mini-Circuits **VAT-10W2+** or equivalent | 10 dB, 2 W, SMA, DC – 3 GHz | 1 | $10 | $10 | Creates a 0/10/20/30 dB stepped cascade with item #3 |
| 8 | Fixed SMA attenuator, 5 dB | Mini-Circuits **VAT-5W2+** or equivalent | 5 dB, 2 W, SMA | 1 | $10 | $10 | For 5 dB steps |
| 9 | SMA T-connector or 2-way switch | Generic SMA T-adapter | For bypassing attenuators during setup verification | 1 | $6 | $6 | |
| 10 | SMA torque wrench | 5 in-lbs SMA torque wrench | Ensures consistent connector torque | 1 | $35 | $35 | Optional but recommended for repeatable connections |

**Strongly recommended subtotal: $61**

---

### Alternative: Programmable Attenuator (replaces items 7–9)

| # | Item | Manufacturer / Model | Specification | Quantity | Unit cost (USD) | Total (USD) | Notes |
|---|---|---|---|---|---|---|---|
| A | Programmable step attenuator | Mini-Circuits **RCDAT-4000-30** (USB-controlled) or **ZX76-31R75-PP+** (mechanical) | 0–31.75 dB, 0.25 dB steps, USB or manual, SMA | 1 | $150–$550 | $150–$550 | USB-controlled version allows automated sweep; required for automated scenario B |

A programmable attenuator simplifies the attenuation sweep (Scenario B) automation. Without it, manual attenuator substitution is required between steps, which introduces timing uncertainty.

---

## 4. Total Cost Estimates

| Configuration | Total (USD) |
|---|---|
| Minimum (items 1–6 only, manual sweep) | $433 |
| Recommended (items 1–9, manual stepped sweep) | $494 |
| Automated (items 1–6 + item A, USB-controlled sweep) | $594–$984 |

**If a suitable SDR transmitter is already in-lab:** subtract $340 from the above totals.

---

## 5. Acceptable Substitutions

| Item | Original | Acceptable substitution | Conditions |
|---|---|---|---|
| HackRF One | Great Scott Gadgets HackRF One r9 | Any revision HackRF One (r6a or later) | Verify +10 dBm max TX output specification from datasheet; do not use with higher-power variants |
| RTL-SDR Blog V3 | RTL-SDR Blog V3 | RTL-SDR Blog V4 | V4 has improved LNA; verify SMA connector compatibility and +10 dBm max input specification |
| Fixed 20 dB attenuator | Mini-Circuits VAT-20W2+ | Any SMA 20 dB fixed attenuator with ≥ 1 W power rating and DC – 3 GHz coverage | Do NOT substitute with a lower power-rated attenuator; do NOT use 10 dB as the only fixed attenuator |
| DC block | Mini-Circuits BLK-89-S+ | Any SMA DC block with ≤ 1 dB insertion loss at 433 MHz | Verify insertion loss from datasheet |
| Coax | RG-316 SMA-SMA | RG-58 SMA-SMA 50-ohm (50 cm or shorter) | Higher loss per metre; acceptable at 433 MHz for ≤ 50 cm |

**Unacceptable substitutions:**
- Removing the DC block (required for HackRF bias-T isolation)
- Using a 10 dB fixed attenuator as the sole primary protection (insufficient margin)
- Using non-50-ohm coaxial cable or adapters
- Using BNC or F-type adapters without confirming RF impedance match

---

## 6. Vendor Sources

| Vendor | Items | Notes |
|---|---|---|
| **greatscottgadgets.com** | HackRF One | Official source; hardware revision guaranteed |
| **rtl-sdr.com** | RTL-SDR Blog V3 | Official source for V3/V4 |
| **minicircuits.com** | Attenuators, DC block, coax, cables | Technical specifications on website; SMA parts ship from US |
| **mouser.com** | All passive RF components | Wide selection; datasheet links available |
| **digikey.com** | All passive RF components | Alternative to Mouser |
| **amazon.com** | RTL-SDR, generic SMA cables, terminators | Faster delivery; verify seller and specification |

---

## 7. Delivery Estimate

| Item | Typical delivery (US) | Notes |
|---|---|---|
| HackRF One (greatscottgadgets.com) | 3–7 business days | In stock as of 2026-08 (verify) |
| RTL-SDR Blog V3 (rtl-sdr.com) | 3–10 business days | In stock typically |
| Mini-Circuits components (minicircuits.com) | 2–5 business days | Fast domestic shipping |
| Generic SMA cables and terminators (Amazon) | 1–3 business days (Prime) | Verify 50-ohm spec |

Total lead time to receive all items: **approximately 5–10 business days** if ordered simultaneously.

---

## 8. Return Policy

| Vendor | Return policy (approximate) |
|---|---|
| greatscottgadgets.com | Contact vendor; limited returns on electronic components |
| rtl-sdr.com | 30-day return for unopened items; contact vendor |
| minicircuits.com | Contact vendor; no return on opened RF components |
| mouser.com | 30-day return for unused, unopened components |
| amazon.com | 30-day return (Prime); varies by seller |

---

## 9. Purchase Authorisation Conditions

Purchase is authorised only when ALL of the following conditions are met:

- [ ] Desk-side prerequisites have been reviewed and accepted:
  - [ ] `artifacts/sdr-bench-v1/observation-mapping-spec.json` (SHA-256: `35b488eb41b96b06c2f93ddad301d3596524362e68f10ed187c8e44a384e49b2`)
  - [ ] `artifacts/sdr-bench-v1/protocol.json` accepted by reviewer
  - [ ] RF safety document (`docs/sdr-bench/rf-safety.md`) reviewed and signed off by a qualified RF engineer
  - [ ] Harness offline tests pass (55 tests in `tests/qrtc_sdr/`)
- [ ] Release asset discrepancy resolved (wheel either located or rebuild authorised)
- [ ] In-lab equipment inventory completed (no duplicate purchase)
- [ ] Specific vendor and revision confirmed (HackRF One r9, RTL-SDR Blog V3)

---

## 10. Estimated Hardware Purchase Total

| Configuration | Total (USD) |
|---|---|
| Minimum (manual sweep) | **$433** |
| Recommended (manual stepped) | **$494** |
| With automated sweep | **$594 – $984** |

*Excludes taxes, shipping, and torque wrench.*

This is a small desk-side cost compared to the preceding software work. The recommended configuration ($494) provides sufficient capability for all five protocol scenarios with manually-stepped attenuation.
