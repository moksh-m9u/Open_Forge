"""Ambiguity detector — identify fields needing clarification.

Detects underspecified or conflicting fields in the parsed intent and generates
Ambiguity objects for user resolution.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.schemas.common import Ambiguity
    from src.schemas.intent import DesignMethodology, FrequencySpec, IntentDict

logger = logging.getLogger(__name__)

# Generic/vague goals that need clarification
_VAGUE_GOALS = {"circuit", "board", "pcb", "device", "thing", "design", "something"}


def _is_vague_goal(goal: str) -> bool:
    """Check if the goal is too generic/vague."""
    goal_normalized = goal.lower().replace("_", " ").strip()
    goal_words = set(goal_normalized.split())
    return bool(goal_words & _VAGUE_GOALS) or len(goal_normalized) < 3


def _is_rf_without_frequency(
    methodology: "DesignMethodology", frequency: "FrequencySpec | None"
) -> bool:
    """Check if RF design lacks frequency specification."""
    return methodology.value == "RF_highfreq" and frequency is None


def detect_ambiguities(
    intent: "IntentDict",
    prompt: str,
) -> list["Ambiguity"]:
    """Detect fields that need clarification.

    Creates Ambiguity objects for various underspecified conditions:
    - Goal is too generic ("circuit", "board", etc.)
    - Application is unspecified
    - RF design without frequency
    - Any fields the LLM flagged as ambiguous

    Args:
        intent: Parsed design intent with goal, application, methodology, frequency
        prompt: Original user prompt for context

    Returns:
        List of Ambiguity objects

    Example:
        >>> from src.schemas.intent import DesignMethodology, IntentDict
        >>> intent = IntentDict(
        ...     goal="circuit", application="unspecified",
        ...     design_methodology=DesignMethodology.STANDARD_SMD,
        ...     board_type="standard_SMD", raw_prompt="build something",
        ... )
        >>> flags = detect_ambiguities(intent, intent.raw_prompt)
        >>> len(flags) >= 1
        True
    """
    from src.schemas.common import Ambiguity

    goal = intent.goal
    application = intent.application
    methodology = intent.design_methodology
    frequency = intent.frequency
    llm_ambiguities = [
        flag.description for flag in intent.ambiguities
    ]

    flags: list[Ambiguity] = []

    # Check 1: goal is too generic
    if _is_vague_goal(goal):
        flags.append(
            Ambiguity(
                field="goal",
                description="Goal is too generic",
                severity="ERROR",
                blocking=True,
            )
        )
        logger.debug(f"Ambiguity detected: goal '{goal}' is too vague")

    # Check 2: application is unspecified
    if application.lower() in ("unspecified", "", "unknown"):
        flags.append(
            Ambiguity(
                field="application",
                description="Application context not specified",
                severity="WARNING",
            )
        )

    # Check 3: RF design without frequency
    if _is_rf_without_frequency(methodology, frequency):
        flags.append(
            Ambiguity(
                field="frequency",
                description="RF design requires a target frequency",
                severity="ERROR",
                candidate_resolutions=["2.4 GHz", "5 GHz", "433 MHz", "915 MHz", "868 MHz"],
                blocking=True,
            )
        )
        logger.debug(f"Ambiguity detected: RF design without frequency")

    # Check 4: LLM-reported ambiguities
    for ambiguity in llm_ambiguities:
        flags.append(
            Ambiguity(
                field="unknown",
                description=ambiguity,
                severity="WARNING",
            )
        )

    return flags
