from pydantic import BaseModel,Field, field_validator,model_validator,EmailStr
from typing import List, Optional

class StrictBaseModel(BaseModel):

    model_config = {
        "extra": "forbid"
    }


# =========================
# Ressource pédagogique
# =========================
class RessourcePedagogique(StrictBaseModel):

   
    id: str
    titre: str
    type: Optional[str] = None


# =========================
# Activité pédagogique
# =========================
class ActivitePedagogique(StrictBaseModel):

    
    id: str
    titre: str
    type: Optional[str] = None


# =========================
# Evaluation
# =========================
class Evaluation(StrictBaseModel):

    id: str
    type: str
    ponderation: Optional[float] = None


# =========================
# Acquis d’apprentissage
# =========================
class AcquisApprentissage(StrictBaseModel):

    id: str
    description: str


class Enseignant(StrictBaseModel):

    id: str

    nom: str

    email: Optional[EmailStr] = None

    telephone: Optional[str] = None

    role: Optional[str] = None


# =========================
# Élément pédagogique
# =========================
class ElementPedagogique(StrictBaseModel):

    id: str
    nom: str

    type: Optional[str] = None

    ects: float = 0.0
    cm: float = 0.0
    td: float = 0.0
    tp: float = 0.0
    projet: float= 0.0

    volume_total: float = 0.0

    activites: List[ActivitePedagogique] = Field(default_factory=list)
    ressources: List[RessourcePedagogique] = Field(default_factory=list)
    acquis: List[AcquisApprentissage] = Field(default_factory=list)
    evaluations: List[Evaluation] = Field(default_factory=list)
    enseignants: List[Enseignant] = Field(default_factory=list)

    @field_validator("cm", "td", "tp", "projet")
    @classmethod
    def validate_hours(cls, v):

        if v < 0:
            raise ValueError(
                "Hours cannot be negative"
            )

        return v
    
    @field_validator("ects")
    @classmethod
    def validate_ects(cls, v):

        if v < 0:
            raise ValueError(
                "ECTS cannot be negative"
            )

        return v
    
    @model_validator(mode="after")
    def compute_total(self):

        self.volume_total = (
        self.cm +
        self.td +
        self.tp +
        self.projet
        )

        return self


# =========================
# UE
# =========================
class UniteEnseignement(StrictBaseModel):

    id: str
    code: str
    intitule: str

    ects: float = 0.0
    type: Optional[str] = None

    elements_pedagogiques: List[ElementPedagogique] = Field(default_factory=list)

    @field_validator("ects")
    @classmethod
    def validate_ects(cls, v):

        if v < 0:
            raise ValueError(
                "ECTS cannot be negative"
            )

        return v


# =========================
# Stage
# =========================
class Stage(StrictBaseModel):

    id: str

    type: Optional[str] = None
    duree: float = 0.0
    ects: float = 0.0

    @field_validator("ects", "duree")
    @classmethod
    def validate_positive_values(cls, v):

        if v < 0:
            raise ValueError(
                "ECTS and duration cannot be negative"
            )

        return v


# =========================
# Période programme
# =========================
class PeriodeProgramme(StrictBaseModel):

    id: str

    numero: int
    ects: float = 0.0

    unites_enseignement: List[UniteEnseignement] = Field(default_factory=list)
    stages: List[Stage] = Field(default_factory=list)

    @field_validator("ects")
    @classmethod
    def validate_ects(cls, v):

        if v < 0:
            raise ValueError(
                "ECTS cannot be negative"
            )

        return v


# =========================
# Programme
# =========================
class Programme(StrictBaseModel):

    id: str

    nom: str
    type: Optional[str] = None

    niveau: Optional[str] = None
    
    ects_total: float = 0.0
    duree: int = 0

    periodes: List[PeriodeProgramme] = Field(default_factory=list)

    @field_validator("ects_total", "duree")
    @classmethod
    def validate_positive_values(cls, v):

        if v < 0:
            raise ValueError(
                "ECTS and duration cannot be negative"
            )

        return v

