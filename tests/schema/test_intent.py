"""Schema fix tests — one test per fix (passing + failing case each)."""

import pytest
from pydantic import ValidationError

from src.schemas.common import (
    Ambiguity,
    DesignRequest,
    NoiseSpec,
    OutOfScopeRequest,
    ProductionVolume,
    TopologyGuess,
)
from src.schemas.intent import (
    CostConstraints,
    DesignMethodology,
    ImprovedIntentDict,
    MAX_PROMPT_TOKENS,
)


def _minimal_intent(**overrides) -> dict:
    base = {
        "goal": "current_source",
        "application": "lab",
        "design_methodology": DesignMethodology.MIXED_SIGNAL,
        "board_type": "double_sided_SMD",
        "raw_prompt": "test",
    }
    base.update(overrides)
    return base


def test_fix_1_multi_topology():
    """goal_topologies auto-populates goal_topology compat field."""
    intent = ImprovedIntentDict(
        **_minimal_intent(),
        goal_topologies=[
            TopologyGuess(name="libbrecht_hall", confidence=0.9, evidence=["hall effect"]),
        ],
    )
    assert intent.goal_topology == "libbrecht_hall"

    with pytest.raises(ValidationError):
        TopologyGuess(name="bad", confidence=1.5, evidence=[])


def test_fix_2_typed_ambiguity():
    """Ambiguity list accepts typed entries with severity and blocking."""
    intent = ImprovedIntentDict(
        **_minimal_intent(),
        ambiguities=[
            Ambiguity(
                field="goal",
                description="too vague",
                severity="WARNING",
            ),
        ],
    )
    assert intent.ambiguities[0].severity == "WARNING"

    with pytest.raises(ValidationError):
        Ambiguity(
            field="goal",
            description="bad",
            severity="CRITICAL",  # type: ignore[arg-type]
        )


def test_fix_3_quantification_source():
    """quantification_source traces grounded specs to document pages."""
    spec = NoiseSpec(raw_text="ultra low noise", quantification_source="TI_SLVA882:12")
    assert spec.quantification_source == "TI_SLVA882:12"

    with pytest.raises(ValidationError):
        NoiseSpec(raw_text="noise", quantification_source=123)  # type: ignore[arg-type]


def test_fix_4_clarification_protocol():
    """clarification_required requires at least one blocking ambiguity."""
    ImprovedIntentDict(
        **_minimal_intent(),
        clarification_required=True,
        ambiguities=[
            Ambiguity(
                field="goal",
                description="too vague",
                severity="ERROR",
                blocking=True,
            ),
        ],
    )

    with pytest.raises(ValueError, match="clarification_required=True but no blocking"):
        ImprovedIntentDict(
            **_minimal_intent(),
            clarification_required=True,
            ambiguities=[
                Ambiguity(
                    field="goal",
                    description="advisory only",
                    severity="WARNING",
                    blocking=False,
                ),
            ],
        )


def test_fix_5_explicit_constraints():
    """ImprovedIntentDict rejects removed explicit_constraints field."""
    with pytest.raises(ValidationError):
        ImprovedIntentDict(
            **_minimal_intent(),
            explicit_constraints=["low_power"],  # type: ignore[call-arg]
        )


def test_fix_6_production_volume():
    """production_volume is a typed enum, not a free string."""
    cost = CostConstraints(production_volume=ProductionVolume.PROTOTYPE)
    assert cost.production_volume == ProductionVolume.PROTOTYPE

    with pytest.raises(ValidationError):
        CostConstraints(production_volume="made_up_volume")  # type: ignore[arg-type]


def test_fix_7_common_imports():
    """Shared types are importable from common and re-exported from intent."""
    from src.schemas import common
    from src.schemas.intent import Ambiguity as IntentAmbiguity
    from src.schemas.intent import TopologyGuess as IntentTopologyGuess

    assert common.TopologyGuess is IntentTopologyGuess
    assert common.Ambiguity is IntentAmbiguity


def test_fix_8_prompt_length_guard():
    """raw_prompt rejects prompts exceeding MAX_PROMPT_TOKENS estimate."""
    short_prompt = "x" * (MAX_PROMPT_TOKENS * 4)
    ImprovedIntentDict(**_minimal_intent(raw_prompt=short_prompt))

    with pytest.raises(ValidationError, match="raw_prompt exceeds MAX_PROMPT_TOKENS"):
        ImprovedIntentDict(**_minimal_intent(raw_prompt="x" * ((MAX_PROMPT_TOKENS + 1) * 4)))


def test_fix_9_scope_separation():
    """In-scope and out-of-scope requests use separate typed lists."""
    intent = ImprovedIntentDict(
        **_minimal_intent(),
        in_scope_requests=[
            DesignRequest(request_type="bom", in_scope=True),
        ],
        out_of_scope_requests=[
            OutOfScopeRequest(
                request_type="python_gui",
                reason="not in v1 scope",
            ),
        ],
    )
    assert len(intent.in_scope_requests) == 1
    assert intent.out_of_scope_requests[0].request_type == "python_gui"

    with pytest.raises(ValidationError):
        DesignRequest(request_type="python_gui", in_scope=False)  # type: ignore[arg-type]
