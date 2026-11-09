from typing import Literal

from pydantic import BaseModel, Field

Explicitness = Literal["explicit", "implicit", "not_present"]


class TriggerFactJudgment(BaseModel):
    fact_id: str = Field(
        ...,
        description="Identifier of the must-mention fact that was evaluated.",
    )
    mentioned: bool = Field(
        ...,
        description=(
            "Whether the explanation mentions the semantic content of the fact at all. "
            "This can still be true when the polarity is wrong."
        ),
    )
    polarity_correct: bool = Field(
        ...,
        description=(
            "Whether the explanation states the fact with the correct direction/polarity. "
            "Use false for contradictions or reversals."
        ),
    )
    explicitness: Explicitness = Field(
        ...,
        description=(
            "How directly the fact is stated. Use 'explicit' only when the explanation "
            "clearly communicates the fact; 'implicit' for weaker paraphrases; "
            "'not_present' when the fact is absent."
        ),
    )
    contradiction: bool = Field(
        ...,
        description=(
            "Whether the explanation explicitly contradicts the fact or claims the "
            "opposite meaning."
        ),
    )
    evidence_quote: str = Field(
        ...,
        description=(
            "A short quote or excerpt from the explanation that supports the judgment. "
            "Use an empty string if there is no relevant evidence."
        ),
    )
    reason: str = Field(
        ...,
        description=(
            "Brief justification focused only on whether the must-mention fact is "
            "communicated in the explanation."
        ),
    )
