from pydantic import BaseModel, Field


class ClarityJudgment(BaseModel):
    score: int = Field(
        ...,
        ge=0,
        le=10,
        description=(
            "Klarheit der Ausgabe auf einer Skala von 0 (unverständlich) "
            "bis 10 (sehr klar und gut strukturiert für Fachpersonal)."
        ),
    )
    explanation: str = Field(
        ...,
        description="Kurze Begründung (1–2 Sätze) für die Klarheitsbewertung.",
    )


class CoherenceJudgment(BaseModel):
    score: int = Field(
        ...,
        ge=0,
        le=10,
        description=(
            "Kohärenz zwischen Eingabe und Ausgabe auf einer Skala von 0 "
            "(widersprüchlich oder nicht aus der Eingabe ableitbar) "
            "bis 10 (vollständig konsistent und belegbar)."
        ),
    )
    explanation: str = Field(
        ...,
        description="Kurze Begründung (1–2 Sätze) für die Kohärenzbewertung.",
    )
