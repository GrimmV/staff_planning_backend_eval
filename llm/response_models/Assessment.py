from pydantic import BaseModel, Field
from typing import Literal
from id_handling.name_generator import load_name_mappings

class Assessment(BaseModel):
    score: Literal["akzeptieren", "eher akzeptieren", "eher ablehnen", "ablehnen"] = Field(..., description="Bewertung der Konsequenzen durch die Änderung. Sei schohnungslos ehrlich und kritisch.")
    assessment: str = Field(..., description="Begründung für den Score.")
    short_assessment: str = Field(..., description="Begründung in 1-2 Sätzen.")
    