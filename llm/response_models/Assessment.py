from pydantic import BaseModel, Field, ValidationInfo, field_validator
from typing import Literal, List
from id_handling.name_generator import load_name_mappings
from utils.diff_features import features_default

name_mappings = load_name_mappings()

class SignificantAssignment(BaseModel):
    ma: str = Field(..., description="Mitarbeitername")
    
    spalten_namen: List[Literal[*features_default]] = Field(..., description="Liste der entsprechenden signifikanten Spalten")
    
    # @field_validator("ma")
    # def validate_ma(cls, v, info: ValidationInfo) -> str:
    #     mas_from_context = info.context.get("mas", [])
    #     mas_from_context = [name_mappings[a] for a in mas_from_context]
    #     ma = next((a for a in mas_from_context if any(a in b for b in v)), None)
    #     if ma is None:
    #         raise ValueError(f"Mitarbeiter {v} nicht gefunden. Vorhandene Mitarbeiter: {mas_from_context}")
    #     return ma

class Assessment(BaseModel):
    score: Literal["akzeptieren", "prüfen", "ablehnen"] = Field(..., description="Bewertung der Konsequenzen durch die Änderung.")
    assessment: str = Field(..., description="Begründung für den Score.")
    short_assessment: str = Field(..., description="Begründung in 1-2 Sätzen.")
    significant_assignments: List[SignificantAssignment] = Field(..., description="Zuordnungen mit großem Einfluss via Mitarbeiternamen.")
    