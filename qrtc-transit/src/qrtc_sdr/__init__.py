"""
qrtc_sdr — SDR observation-only harness for RescueOS Advisor.

This package provides:

- ``SdrTelemetry``: typed SDR telemetry record collected from an RTL-SDR receiver.
- ``SdrObservationMapper``: maps a ``SdrTelemetry`` record to a ``Phase5OODCase``
  compatible with the frozen Advisor observation schema (``phase5-ood-case-v1``).
- ``SdrBenchHarness``: offline bench-harness skeleton that enforces one-way data
  flow into the Advisor and records audit events.

Architecture constraints (enforced at module level):

- The Advisor may only *consume* observation records produced by this package.
- No function in this package accepts an Advisor output and routes it to a
  transmitter-control interface.
- No function in this package opens a socket, serial port, or USB device that
  can send commands to a transmitter.
- ``SdrBenchHarness.advisor_transmitter_bytes`` must remain zero for the entire
  duration of any bench run.

This package does NOT modify the frozen controller, causal graph, thresholds,
action allowlist, or Advisor schemas.  It is a pure adapter layer.
"""
