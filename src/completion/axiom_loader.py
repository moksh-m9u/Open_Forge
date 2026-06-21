"""
Loads domain knowledge YAML files by topology slug and evaluates axiom
preconditions against an ImprovedIntentDict to produce a filtered axiom list.

For multi-topology designs, loads axioms from all topologies above
confidence threshold 0.6 and merges them. Conflicts (two axioms implying
contradictory requirements) are surfaced as Contradiction entries.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

from src.schemas.intent import ImprovedIntentDict

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.6

_EQ_RE = re.compile(r"^(.+?)\s*==\s*(.+)$")
_LT_RE = re.compile(r"^(.+?)\s*<\s*([0-9.]+)$")
_GTE_RE = re.compile(r"^(.+?)\s*>=\s*([0-9.]+)$")
_CONTAINS_RE = re.compile(r"^(.+?)\s+contains\s+'(.+)'$", re.IGNORECASE)
_COMP_PREF_RE = re.compile(
    r"^component_preferences\s+contains\s+(.+)$", re.IGNORECASE
)
_GOAL_TOPO_RE = re.compile(
    r"^goal_topology\s+contains\s+'(.+)'$", re.IGNORECASE
)


def _get_nested(obj: Any, path: str) -> Any:
    current = obj
    for part in path.strip().split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def _coerce(value: str) -> Any:
    value = value.strip().strip("'\"")
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _evaluate_condition(condition: str, intent: ImprovedIntentDict) -> bool:
    condition = condition.strip()

    match = _COMP_PREF_RE.match(condition)
    if match:
        type_token = match.group(1).strip().strip("'\"")
        for pref in intent.component_preferences:
            for field_val in (pref.component_type, pref.required_attribute):
                if field_val is None:
                    continue
                if field_val == type_token:
                    return True
                if type_token in field_val or field_val in type_token:
                    return True
        return False

    match = _GOAL_TOPO_RE.match(condition)
    if match:
        slug = match.group(1)
        if intent.goal_topology == slug:
            return True
        return any(t.name == slug for t in intent.goal_topologies)

    match = _CONTAINS_RE.match(condition)
    if match:
        path, text = match.group(1).strip(), match.group(2)
        nested = _get_nested(intent, path)
        if nested is None:
            return False
        return text.lower() in str(nested).lower()

    match = _GTE_RE.match(condition)
    if match:
        path, num_str = match.group(1).strip(), match.group(2)
        nested = _get_nested(intent, path)
        if nested is None:
            return False
        try:
            return float(nested) >= float(num_str)
        except (TypeError, ValueError):
            return False

    match = _LT_RE.match(condition)
    if match:
        path, num_str = match.group(1).strip(), match.group(2)
        nested = _get_nested(intent, path)
        if nested is None:
            return False
        try:
            return float(nested) < float(num_str)
        except (TypeError, ValueError):
            return False

    match = _EQ_RE.match(condition)
    if match:
        path, raw_val = match.group(1).strip(), match.group(2).strip()
        nested = _get_nested(intent, path)
        if nested is None:
            return False
        return nested == _coerce(raw_val)

    logger.warning("Unrecognized precondition condition: %r", condition)
    return False


def evaluate_preconditions(
    preconditions: dict,
    intent: ImprovedIntentDict,
) -> bool:
    """Evaluate any_of / all_of precondition blocks against an intent."""
    if "any_of" in preconditions:
        return any(
            _evaluate_condition(c, intent) for c in preconditions["any_of"]
        )
    if "all_of" in preconditions:
        return all(
            _evaluate_condition(c, intent) for c in preconditions["all_of"]
        )
    return False


def load_axioms_for_intent(
    intent: ImprovedIntentDict,
    data_dir: Path,
) -> list[dict]:
    """Load and filter axioms from all qualifying topologies."""
    slugs: list[str] = [
        t.name for t in intent.goal_topologies if t.confidence >= CONFIDENCE_THRESHOLD
    ]
    if not slugs and not intent.goal_topologies and intent.goal_topology:
        slugs = [intent.goal_topology]

    merged: list[dict] = []
    for slug in slugs:
        yaml_path = data_dir / f"{slug}.yaml"
        if not yaml_path.exists():
            logger.warning("Domain knowledge file not found: %s", yaml_path)
            continue

        with open(yaml_path, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}

        noise_sources = doc.get("noise_sources_ranked", [])
        for axiom in doc.get("axioms", []):
            if evaluate_preconditions(axiom.get("preconditions", {}), intent):
                entry = dict(axiom)
                entry["_source_topology"] = slug
                entry["_noise_sources"] = noise_sources
                merged.append(entry)

    return merged


def _normalized_requirement(text: str) -> str:
    return " ".join(text.lower().split())


def detect_axiom_conflicts(merged_axioms: list[dict]) -> list[dict]:
    """Detect conflicting requirements sharing the same component_implication."""
    by_implication: dict[str, list[dict]] = {}
    for axiom in merged_axioms:
        implication = axiom.get("implies", {}).get("component_implication", "")
        by_implication.setdefault(implication, []).append(axiom)

    conflicts: list[dict] = []
    for implication, group in by_implication.items():
        if not implication or len(group) < 2:
            continue
        for i, ax_a in enumerate(group):
            req_a = _normalized_requirement(
                ax_a.get("implies", {}).get("requirement", "")
            )
            for ax_b in group[i + 1 :]:
                req_b = _normalized_requirement(
                    ax_b.get("implies", {}).get("requirement", "")
                )
                if req_a == req_b:
                    continue
                ratio = SequenceMatcher(None, req_a, req_b).ratio()
                if ratio < 0.6:
                    conflicts.append({
                        "axiom_a_id": ax_a.get("id", "unknown"),
                        "axiom_b_id": ax_b.get("id", "unknown"),
                        "description": (
                            f"Topology axioms conflict on {implication!r}: "
                            f"{ax_a.get('implies', {}).get('requirement')} vs "
                            f"{ax_b.get('implies', {}).get('requirement')}"
                        ),
                    })
    return conflicts
