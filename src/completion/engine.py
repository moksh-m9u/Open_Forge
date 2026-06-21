"""Stage 2 requirement completion engine — main entry point."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Type

from src.completion.axiom_loader import (
    detect_axiom_conflicts,
    load_axioms_for_intent,
)
from src.completion.contradiction_checker import run_rule_checker
from src.completion.schemas import RequirementCompletionResult
from src.completion.system_prompt import build_system_prompt
from src.schemas.common import Ambiguity
from src.schemas.intent import ImprovedIntentDict

if TYPE_CHECKING:
    from pydantic import BaseModel

    from src.config import Config

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.80
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1, 2, 4)


class CompletionEngineError(Exception):
    """Raised when the completion engine cannot produce a result after retries."""
    pass


def _resolve_completion_config(config: "Config") -> tuple[Path, str, str]:
    project_root = Path(__file__).resolve().parents[2]
    data_dir = getattr(config, "domain_knowledge_dir", None) or (
        project_root / "data" / "domain_knowledge"
    )
    base_url = getattr(config, "llm_base_url", "http://localhost:8000/v1")
    model = getattr(config, "llm_model", "Qwen/Qwen2.5-7B-Instruct")
    return Path(data_dir), base_url, model


def call_llm_with_instructor(
    system_prompt: str,
    intent: ImprovedIntentDict,
    config: "Config",
    output_schema: Type["BaseModel"],
) -> RequirementCompletionResult:
    """Call LLM via Instructor with retries and exponential backoff."""
    _, base_url, model = _resolve_completion_config(config)
    api_key = getattr(config, "llm_api_key", "not-needed")

    try:
        import instructor
        from openai import OpenAI
    except ImportError as exc:
        raise CompletionEngineError(
            "instructor or openai package not installed"
        ) from exc

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=60.0,
    )
    instructor_client = instructor.from_openai(client)

    user_message = (
        f"Analyze this PCB design intent:\n\n{intent.model_dump_json(indent=2)}"
    )

    last_exc: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            result = instructor_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_model=output_schema,
                max_retries=0,
            )
            return result  # type: ignore[return-value]
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Completion LLM attempt %d/%d failed: %s",
                attempt + 1,
                MAX_ATTEMPTS,
                exc,
            )
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(BACKOFF_SECONDS[attempt])

    raise CompletionEngineError(str(last_exc))


def run_completion_engine(
    intent: ImprovedIntentDict,
    config: "Config",
) -> ImprovedIntentDict:
    """Run Stage 2 requirement completion and merge results into the intent dict."""
    data_dir, _, _ = _resolve_completion_config(config)

    # 1. Load and evaluate axioms from all topologies >= 0.6 confidence
    axioms = load_axioms_for_intent(intent, data_dir)
    axiom_conflicts = detect_axiom_conflicts(axioms)

    # 2. Build system prompt
    system_prompt = build_system_prompt(intent, axioms, axiom_conflicts)

    # 3. Call LLM via Instructor — RequirementCompletionResult enforced
    result: RequirementCompletionResult = call_llm_with_instructor(
        system_prompt=system_prompt,
        intent=intent,
        config=config,
        output_schema=RequirementCompletionResult,
    )

    # 4. Run rule-based contradiction checker — appends to result.contradictions
    rule_contradictions = run_rule_checker(intent, result)
    result = result.model_copy(update={
        "contradictions": result.contradictions + rule_contradictions,
    })

    # 5. Escalate dangerous assumptions to blocking Ambiguity entries
    new_ambiguities = list(intent.ambiguities)
    for da in result.dangerous_assumptions:
        new_ambiguities.append(Ambiguity(
            field=da.field,
            description=(
                f"Stage 2 would have assumed {da.field}={da.assumed_value!r} "
                f"({da.reasoning}). Must be confirmed by engineer before proceeding."
            ),
            severity="ERROR",
            candidate_resolutions=[
                f"Specify {da.field} explicitly in the prompt",
                f"Accept assumed value: {da.assumed_value}",
            ],
            blocking=True,
        ))

    clarification_required = intent.clarification_required or any(
        a.blocking for a in new_ambiguities
    )

    # 6. Merge result back into ImprovedIntentDict
    return intent.model_copy(update={
        "implied_requirements": result.implied_requirements,
        "missing_critical_specs": result.missing_critical_specs,
        "contradictions_detected": [c.description for c in result.contradictions],
        "inferred_constraints": [
            r.requirement for r in result.implied_requirements
            if r.confidence >= CONFIDENCE_THRESHOLD
        ],
        "ambiguities": new_ambiguities,
        "clarification_required": clarification_required,
    })
