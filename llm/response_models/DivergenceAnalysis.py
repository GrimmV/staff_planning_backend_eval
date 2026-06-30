from typing import List, Literal

from pydantic import BaseModel, Field

DivergenceType = Literal[
    "critical_omission",
    "harmful_optimism",
    "over_caution",
    "abstraction_drift",
    "count_level_misinterpretation",
    "priority_miscalibration",
    "experience_over_weighting",
    "distance_over_weighting",
    "context_overload",
    "unsupported_hallucinated_claim",
    "no_reason_found",
    "other",
]

DIVERGENCE_TYPE_DESCRIPTIONS: dict[DivergenceType, str] = {
    "critical_omission": (
        "A high-priority or coverage-critical effect is not mentioned."
    ),
    "harmful_optimism": (
        "The score is too positive relative to the reference policy."
    ),
    "over_caution": (
        "The score is too negative despite no critical risk."
    ),
    "abstraction_drift": (
        "Intermediate summaries lose decisive evidence."
    ),
    "count_level_misinterpretation": (
        "Added/removed counts are interpreted without checking affected clients."
    ),
    "priority_miscalibration": (
        "Priority effects are over- or under-weighted."
    ),
    "experience_over_weighting": (
        "Familiarity dominates despite stronger coverage evidence."
    ),
    "distance_over_weighting": (
        "Commute dominates despite weak practical relevance."
    ),
    "context_overload": (
        "Many changes cause relevant facts to be ignored."
    ),
    "unsupported_hallucinated_claim": (
        "The explanation mentions facts not present in the data."
    ),
    "no_reason_found": (
        "No clear divergence pattern can be identified from the available evidence."
    ),
    "other": (
        "A divergence is present but does not fit the predefined categories."
    ),
}


class DivergenceAnalysis(BaseModel):
    primary_divergence_type: DivergenceType = Field(
        ...,
        description=(
            "The primary divergence type that best explains why the LLM assessment "
            "deviates from the reference policy. Use 'no_reason_found' only when no "
            "other category applies."
        ),
    )
    secondary_divergence_type: DivergenceType = Field(
        ...,
        description=(
            "A secondary divergence type that partially explains why the LLM assessment "
            "deviates from the reference policy. Use 'no_reason_found' only when no "
            "other category applies."
        ),
    )
    explanation: str = Field(
        ...,
        description=(
            "Concise justification (2–4 sentences) referencing concrete "
            "facts from the ground-truth diff and the LLM assessment."
        ),
    )
