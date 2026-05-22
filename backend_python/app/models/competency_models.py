from pydantic import BaseModel,Field
from typing import List, Optional

class StrictBaseModel(BaseModel):

    model_config = {
        "extra": "forbid"
    }

class ApprentissageCritique(StrictBaseModel):

    id: str

    description: str

    modules: List[str] = Field(default_factory=list)


class NiveauDeveloppement(StrictBaseModel):
    
    niveau: str

    apprentissages_critiques: List[ApprentissageCritique] = Field(default_factory=list)


class Competence(StrictBaseModel):
    

    code: str

    nom: str

    description: Optional[str] = None

    niveaux: List[NiveauDeveloppement] = Field(default_factory=list)


class ReferentielCompetences(StrictBaseModel):
    
    nom: str = "Référentiel ForestED"

    competences: List[Competence] = Field(default_factory=list)