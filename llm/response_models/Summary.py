from pydantic import BaseModel, Field
from typing import List, Literal
from utils.diff_features import features_default

default_features = features_default.copy()
default_features.remove("Klient")
default_features.remove("Mitarbeiter")

class RelevantChange(BaseModel):
    relevant_spalte: Literal[*default_features] = Field(..., description="Spalte mit relevanter Konsequenz auf den Mitarbeiter.")
    änderung: str = Field(..., description="Beschreibung der Veränderung: 'vorher: <wert> -> nachher: <wert>'")
    effect: Literal["positiv", "neutral", "negativ"] = Field(..., description="Ist die individuelle Änderung eher positiv, negativ oder neutral?")

class AssignmentChange(BaseModel):
    ma: str = Field(..., description="Mitarbeitername der Zuordnung")
    relevant_changes: List[RelevantChange] = Field(..., max_items=3, description="Spalten mit den relevantesten Konsequenzen auf den Mitarbeiter.")
    effect: Literal["positiv", "neutral", "negativ"] = Field(..., description="Ist die Gesamtänderung eher positiv, negativ oder neutral?")
    

class TabelleSummary(BaseModel):
    änderungen: List[AssignmentChange] = Field(..., description="Schaue dir nacheinander jeden Mitarbeiter in der Vorher-Tabelle an und erläutere die wichtigsten Konsequenzen auf den Mitarbeiter in der Nachher-Tabelle.")