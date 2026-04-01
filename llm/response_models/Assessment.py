from pydantic import BaseModel, Field
from typing import Literal
from id_handling.name_generator import load_name_mappings



class Assessment(BaseModel):
    score: Literal["eher akzeptieren", "eher ablehnen", "ablehnen"] = (
        Field(
            ...,
            description="Bewertung der Konsequenzen durch die Änderung."
            + """
                - 'eher akzeptieren':
                Es gibt negative Auswirkungen, aber insgesamt ist die Änderung vertretbar.

                - 'eher ablehnen':
                Es gibt klare negative Auswirkungen, aber keine kritischen Auswirkungen.

                - 'ablehnen':
                Die Änderung verschlechtert mehrere priorisierte Kriterien deutlich oder führt zu kritischen Problemen.""",
        )
    )
    general_assessment: str = Field(..., description="Generelle, Begründung für den Score in 1-2 Sätzen.")
    detail_level_1_assessment: str = Field(..., description="Erläuterung der Effekte auf hohe Priorität Klienten in 1-2 Sätzen.")
    detail_level_2_assessment: str = Field(..., description="Erläuterung der Effekte auf die einzelne Zuordnung mit den stärksten Auswirkungen.")
