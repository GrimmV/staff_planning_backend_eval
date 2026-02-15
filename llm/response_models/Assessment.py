from pydantic import BaseModel, Field
from typing import Literal

class Assessment(BaseModel):
    score: Literal["akzeptieren", "prüfen", "ablehnen"] = Field(..., description="Bewertung der Konsequenzen durch die Änderung.")
    assessment: str = Field(..., description="Begründung für den Score.")
    short_assessment: str = Field(..., description="Begründung in 1-2 Sätzen.")