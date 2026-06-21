"""Gate tests for Stage 2 requirement completion engine."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.completion.axiom_loader import (
    evaluate_preconditions,
    load_axioms_for_intent,
)
from src.completion.contradiction_checker import run_rule_checker
from src.completion.engine import CompletionEngineError, run_completion_engine
from src.completion.schemas import (
    DangerousAssumption,
    RequirementCompletionResult,
)
from src.completion.system_prompt import build_system_prompt
from src.schemas.common import ImpliedRequirement, TopologyGuess
from src.schemas.intent import (
    ComponentPreference,
    DesignMethodology,
    ElectricalConstraints,
    ImprovedIntentDict,
    NoiseSpec,
    PerformanceRequirements,
)

_VALID_INTENT_KWARGS = dict(
    goal="current_source",
    application="lab",
    design_methodology=DesignMethodology.MIXED_SIGNAL,
    board_type="double_sided_SMD",
    raw_prompt="build a libbrecht hall current source 100mA ultra low noise",
    goal_topologies=[
        TopologyGuess(name="libbrecht_hall", confidence=0.95, evidence=["libbrecht hall"])
    ],
)


def _make_intent(**overrides) -> ImprovedIntentDict:
    kwargs = dict(_VALID_INTENT_KWARGS)
    kwargs.update(overrides)
    return ImprovedIntentDict(**kwargs)


def _rich_libbrecht_intent() -> ImprovedIntentDict:
    return _make_intent(
        performance=PerformanceRequirements(
            noise=NoiseSpec(raw_text="ultra low noise", target_value=0.5),
            output_current_ma=100.0,
        ),
        electrical=ElectricalConstraints(supply_topology="single_dc"),
        component_preferences=[
            ComponentPreference(
                component_type="op_amp",
                required_attribute="zero_drift",
            ),
        ],
    )


def _domain_knowledge_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "domain_knowledge"


def test_axiom_loader_loads_libbrecht_hall():
    intent = _rich_libbrecht_intent()
    axioms = load_axioms_for_intent(intent, _domain_knowledge_dir())
    assert len(axioms) >= 5


def test_axiom_loader_skips_below_threshold():
    intent = _make_intent(
        goal_topologies=[
            TopologyGuess(name="libbrecht_hall", confidence=0.5, evidence=["x"])
        ],
    )
    axioms = load_axioms_for_intent(intent, _domain_knowledge_dir())
    assert len(axioms) == 0


def test_axiom_loader_skips_missing_yaml():
    intent = _make_intent(
        goal_topologies=[
            TopologyGuess(name="nonexistent_topology", confidence=0.9, evidence=["x"])
        ],
    )
    axioms = load_axioms_for_intent(intent, _domain_knowledge_dir())
    assert len(axioms) == 0


def test_precondition_evaluator_any_of():
    intent = _make_intent(
        component_preferences=[
            ComponentPreference(
                component_type="op_amp",
                required_attribute="zero_drift",
            ),
        ],
    )
    assert evaluate_preconditions(
        {"any_of": ["component_preferences contains zero_drift_op_amp"]},
        intent,
    )


def test_rule_checker_negative_rail_contradiction():
    intent = _make_intent(
        electrical=ElectricalConstraints(supply_topology="single_dc"),
    )
    result = RequirementCompletionResult(
        implied_requirements=[
            ImpliedRequirement(
                requirement="Use zero-drift op-amp",
                component_implication="zero_drift_op_amp",
                reasoning="Precision current source",
                confidence=0.9,
                source_constraint="topology",
            ),
        ],
    )
    contradictions = run_rule_checker(intent, result)
    assert any(c.severity == "CRITICAL" for c in contradictions)


@patch("src.completion.engine.call_llm_with_instructor")
def test_dangerous_assumption_becomes_blocking_ambiguity(mock_llm):
    mock_llm.return_value = RequirementCompletionResult(
        dangerous_assumptions=[
            DangerousAssumption(
                field="operating_environment",
                assumed_value="laboratory",
                reasoning="No environment specified",
                confidence=0.7,
            ),
        ],
    )
    config = SimpleNamespace(domain_knowledge_dir=_domain_knowledge_dir())
    result = run_completion_engine(_rich_libbrecht_intent(), config)

    assert result.clarification_required is True
    blocking = [a for a in result.ambiguities if a.blocking]
    assert any(a.field == "operating_environment" for a in blocking)


@patch("src.completion.engine.call_llm_with_instructor")
def test_inferred_constraints_unified_threshold(mock_llm):
    high = ImpliedRequirement(
        requirement="Kelvin sensing required",
        reasoning="High current precision",
        confidence=0.85,
        source_constraint="axiom",
    )
    low = ImpliedRequirement(
        requirement="Optional shielding",
        reasoning="Maybe useful",
        confidence=0.75,
        source_constraint="heuristic",
    )
    mock_llm.return_value = RequirementCompletionResult(
        implied_requirements=[high, low],
    )
    config = SimpleNamespace(domain_knowledge_dir=_domain_knowledge_dir())
    result = run_completion_engine(_rich_libbrecht_intent(), config)

    assert high.requirement in result.inferred_constraints
    assert low.requirement not in result.inferred_constraints
    assert len(result.implied_requirements) == 2


@patch("instructor.from_openai")
@patch("openai.OpenAI")
def test_completion_engine_error_on_llm_failure(mock_openai, mock_from_openai):
    mock_client = mock_from_openai.return_value
    mock_client.chat.completions.create.side_effect = RuntimeError("LLM unavailable")
    config = SimpleNamespace(domain_knowledge_dir=_domain_knowledge_dir())

    with pytest.raises(CompletionEngineError):
        run_completion_engine(_rich_libbrecht_intent(), config)


def test_system_prompt_contains_all_topology_sections():
    axioms = [
        {
            "id": "a1",
            "_source_topology": "libbrecht_hall",
            "_noise_sources": [],
            "implies": {"requirement": "req1", "reasoning": "r1"},
            "default_confidence": 0.9,
            "source_citations": [],
        },
        {
            "id": "a2",
            "_source_topology": "boost_converter",
            "_noise_sources": [],
            "implies": {"requirement": "req2", "reasoning": "r2"},
            "default_confidence": 0.9,
            "source_citations": [],
        },
    ]
    prompt = build_system_prompt(_make_intent(), axioms, [])
    assert "--- Domain knowledge: libbrecht_hall ---" in prompt
    assert "--- Domain knowledge: boost_converter ---" in prompt
