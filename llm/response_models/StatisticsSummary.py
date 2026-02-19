from pydantic import BaseModel, Field
from typing import Literal, List
from utils.stats_feature_mapping import feature_mapping_dr

statistics_features = list(feature_mapping_dr.values())

class StatisticsChange(BaseModel):
    relevant_feature: Literal[*statistics_features] = Field(..., description="Feature Name")
    änderung: str = Field(..., description="Beschreibung der Veränderung des Feature-Properties: '<Property>: vorher: <wert> -> nachher: <wert>, ...'. Beinhaltet nur Properties, die sich geändert haben.")
    effect: Literal["positiv", "neutral", "negativ"] = Field(..., description="Ist die individuelle Änderung eher positiv, negativ oder neutral?")

class StatisticsSummary(BaseModel):
    relevant_changes: List[StatisticsChange] = Field(..., description="Features und deren Konsequenzen.")
    effect: Literal["positiv", "neutral", "negativ"] = Field(..., description="Ist die Gesamtänderung eher positiv, negativ oder neutral?")
    