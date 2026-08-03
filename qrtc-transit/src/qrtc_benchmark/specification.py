"""qrtc_benchmark.specification — minimal criterion-ID definitions for Phase IV-B.

This module re-establishes the ``CriterionId`` enumeration needed by
``phase4b.py``.  It was recovered from the Phase IV-B pair-spec table in
``phase4b.py`` itself: the three values PI1, PI2, PI3 appear as explicit
``CriterionId.PI*`` references in ``DEFAULT_PHASE4B_PAIRS``.

Phase IV-B is historical/non-runnable in the current package (see
PHASE4B_STATUS.md).  This stub exists only to allow ``phase4b.py`` to be
imported without a ``ModuleNotFoundError``.  Do not add new semantics here
beyond what is needed for the import to succeed.
"""

from __future__ import annotations

from enum import Enum


class CriterionId(str, Enum):
    """Criterion identifier used in Phase IV-B pair specifications."""

    PI1 = "PI1"
    PI2 = "PI2"
    PI3 = "PI3"
