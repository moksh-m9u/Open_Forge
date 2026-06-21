from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.schemas.common import ImpliedRequirement


class QuantifiedSpec(BaseModel):
    original_text: str
    quantified_value: str
    unit: str
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    quantification_source: Optional[str] = None


class Contradiction(BaseModel):
    constraint_a: str
    constraint_b: str
    description: str
    severity: Literal["CRITICAL", "WARNING"]
    suggested_resolution: Optional[str] = None
    detected_by: Literal["llm", "rule_checker"] = "llm"


class DangerousAssumption(BaseModel):
    """
    An assumption about a DRDO-critical field that Stage 2 cannot silently make.
    These are promoted to blocking Ambiguity entries on the returned ImprovedIntentDict.
    """
    field: Literal["operating_environment", "supply_voltage", "temperature_range"]
    assumed_value: str
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class RequirementCompletionResult(BaseModel):
    implied_requirements: list[ImpliedRequirement] = Field(default_factory=list)
    quantified_specs: list[QuantifiedSpec] = Field(default_factory=list)
    missing_critical_specs: list[str] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    dangerous_assumptions: list[DangerousAssumption] = Field(default_factory=list)
