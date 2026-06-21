"""Builds the four-section system prompt for the requirement completion engine."""

from __future__ import annotations

import json
from collections import defaultdict

from src.completion.schemas import RequirementCompletionResult
from src.schemas.intent import ImprovedIntentDict

ROLE_SECTION = """You are a senior electronics design engineer with deep expertise in precision
analog circuits, low-noise design, RF systems, and power electronics.

Your task is to analyze a structured PCB design intent and:
1. Identify all implied engineering requirements not explicitly stated
2. Quantify vague specifications into engineering values where possible
3. Detect contradictions between stated requirements
4. Identify missing specifications that are critical for design completion
5. Flag any assumption you would make about operating environment, supply
   voltage, or temperature range — do NOT assume these silently

You reason from first principles and domain knowledge, not pattern matching.
Every inference must have a traceable reasoning chain.
"""

REASONING_RULES_SECTION = """Confidence banding (assign based on universality of the implication):
  0.95–1.00 : Physically necessary — cannot be false for this topology
  0.85–0.94 : True for virtually all implementations
  0.70–0.84 : True in most contexts given stated constraints
  0.60–0.69 : Likely but context-dependent
  < 0.60    : Do NOT report

For dangerous_assumptions: if you would assume operating_environment,
supply_voltage, or temperature_range, populate dangerous_assumptions instead
of assuming silently. Leave those fields unquantified.

Fewer high-confidence implications are more useful than many uncertain ones.
"""


def _build_domain_knowledge_section(axioms: list[dict]) -> str:
    if not axioms:
        return "--- Domain knowledge ---\nNo applicable topology axioms loaded.\n"

    by_topology: dict[str, list[dict]] = defaultdict(list)
    noise_by_topology: dict[str, list] = {}
    for axiom in axioms:
        topo = axiom.get("_source_topology", "unknown")
        by_topology[topo].append(axiom)
        if "_noise_sources" in axiom:
            noise_by_topology[topo] = axiom["_noise_sources"]

    parts: list[str] = []
    for topo, topo_axioms in by_topology.items():
        parts.append(f"--- Domain knowledge: {topo} ---")
        noise_sources = noise_by_topology.get(topo, [])
        if noise_sources:
            ranked = ", ".join(
                f"{n.get('rank')}. {n.get('source')}" for n in noise_sources
            )
            parts.append(f"Noise sources (ranked): {ranked}")
        parts.append("Applicable engineering axioms:")
        for axiom in topo_axioms:
            implies = axiom.get("implies", {})
            citations = axiom.get("source_citations", [])
            parts.append(
                f"  - {axiom.get('id')}: {implies.get('requirement')}\n"
                f"    Reasoning: {implies.get('reasoning', '').strip()}\n"
                f"    Confidence: {axiom.get('default_confidence')}\n"
                f"    Citations: {citations}"
            )
        parts.append("")
    return "\n".join(parts)


def _build_conflicts_section(axiom_conflicts: list[dict]) -> str:
    if not axiom_conflicts:
        return ""
    lines = ["--- Conflicts between topologies ---"]
    for conflict in axiom_conflicts:
        lines.append(
            f"  - {conflict.get('axiom_a_id')} vs {conflict.get('axiom_b_id')}: "
            f"{conflict.get('description')}"
        )
    lines.append("")
    return "\n".join(lines)


def _build_output_schema_section() -> str:
    schema = RequirementCompletionResult.model_json_schema()
    return (
        "--- Output schema ---\n"
        "Return ONLY valid JSON matching this schema with no preamble:\n"
        f"{json.dumps(schema, indent=2)}\n"
    )


def build_system_prompt(
    intent: ImprovedIntentDict,
    axioms: list[dict],
    axiom_conflicts: list[dict],
) -> str:
    """Build the four-section system prompt string."""
    sections = [
        ROLE_SECTION,
        _build_domain_knowledge_section(axioms),
        _build_conflicts_section(axiom_conflicts),
        _build_output_schema_section(),
        REASONING_RULES_SECTION,
    ]
    return "\n".join(sections)
