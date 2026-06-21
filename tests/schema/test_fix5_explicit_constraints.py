"""Tests for FIX 5 — explicit_constraints removal and schema version guard."""

import pytest

from src.intent.parser import ParsedIntent, _typed_constraints_as_strings
from src.schemas.intent import (
    DesignMethodology,
    ImprovedIntentDict,
    SchemaVersionError,
    assert_schema_version,
)


def test_improved_intent_dict_has_no_explicit_constraints():
    """ImprovedIntentDict must not accept explicit_constraints."""
    with pytest.raises(Exception):
        ImprovedIntentDict(
            goal="current_source",
            application="lab",
            design_methodology=DesignMethodology.MIXED_SIGNAL,
            board_type="double_sided_SMD",
            raw_prompt="test",
            explicit_constraints=["low_power"],
        )


def test_assert_schema_version_passes_on_v2():
    assert_schema_version({"schema_version": "2.0"})


def test_assert_schema_version_raises_on_v1():
    with pytest.raises(SchemaVersionError):
        assert_schema_version({"schema_version": "1.0"})


def test_assert_schema_version_raises_on_missing():
    with pytest.raises(SchemaVersionError):
        assert_schema_version({})


def test_typed_constraints_as_strings_includes_remainder():
    """Unclassified strings still flow through as remainder."""
    parsed = ParsedIntent(
        goal="current_source",
        application="lab",
        design_methodology=DesignMethodology.MIXED_SIGNAL,
        board_type="double_sided_SMD",
        explicit_constraints=["some_unknown_constraint"],
    )
    result = _typed_constraints_as_strings(parsed)
    assert "some_unknown_constraint" in result
