from __future__ import annotations

import json

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from qrtc.boat import canonicalize_interface  # noqa: E402

json_scalars = st.one_of(st.integers(), st.text(max_size=20), st.booleans(), st.none())
flat_mapping = st.dictionaries(
    keys=st.text(min_size=1, max_size=10),
    values=json_scalars,
    min_size=0,
    max_size=8,
)


@given(flat_mapping)
def test_equal_interfaces_have_equal_canonical_bytes(
    mapping: dict[str, object],
) -> None:
    left = dict(mapping)
    right = dict(reversed(list(mapping.items())))

    left_bytes = canonicalize_interface(
        left,
        schema_version="schema-v1",
        encoding_version="json-v1",
    )
    right_bytes = canonicalize_interface(
        right,
        schema_version="schema-v1",
        encoding_version="json-v1",
    )

    assert left_bytes == right_bytes


@given(flat_mapping)
def test_decode_reencode_preserves_canonical_form(mapping: dict[str, object]) -> None:
    encoded = canonicalize_interface(
        mapping,
        schema_version="schema-v1",
        encoding_version="json-v1",
    )
    decoded = json.loads(encoded.decode("utf-8"))
    reencoded = canonicalize_interface(
        decoded["interface"],
        schema_version=decoded["schema_version"],
        encoding_version=decoded["encoding_version"],
    )
    assert encoded == reencoded
