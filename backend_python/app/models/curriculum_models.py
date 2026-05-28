"""
Méta-modèle curriculum du projet ForestED.

Ce module définit les modèles Pydantic utilisés pour représenter
la structure pédagogique d’un programme de formation.

La hiérarchie principale est :

Programme
    -> PériodeProgramme
        -> UniteEnseignement
            -> ElementPedagogique
                -> AcquisApprentissage
                -> ActivitePedagogique
                -> RessourcePedagogique
                -> Evaluation
                -> Enseignant

Ces modèles servent de structure canonique après transformation
des données brutes issues des fiches de cours.
"""
from pydantic import BaseModel,Field, field_validator,model_validator,EmailStr
from typing import List, Optional

class StrictBaseModel(BaseModel):

    model_config = {
        "extra": "forbid"
    }



class RessourcePedagogique(StrictBaseModel):

    """
    Représente une ressource utilisée dans un enseignement.

    Exemple : support de cours, livre, dataset, lien Moodle.
    """

    id: str
    titre: str
    type: Optional[str] = None



class ActivitePedagogique(StrictBaseModel):

    
    id: str
    titre: str
    type: Optional[str] = None



class Evaluation(StrictBaseModel):

    id: str
    type: str
    ponderation: Optional[float] = None



class AcquisApprentissage(StrictBaseModel):

    """
    Représente un acquis d’apprentissage attendu
    à l’issue d’un élément pédagogique.
    """

    id: str
    description: str


class Enseignant(StrictBaseModel):
    """
    Représente un enseignant ou responsable pédagogique
    associé à un élément pédagogique.
    """

    id: str

    nom: str

    email: Optional[EmailStr] = None

    telephone: Optional[str] = None

    role: Optional[str] = None



class ElementPedagogique(StrictBaseModel):

    """
    Représente un cours, module ou élément pédagogique.

    Il contient les volumes horaires, les acquis,
    les ressources, les évaluations et les enseignants.
    """

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



class UniteEnseignement(StrictBaseModel):

    """
    Représente une unité d’enseignement.

    Une UE regroupe un ou plusieurs éléments pédagogiques.
    """

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



class PeriodeProgramme(StrictBaseModel):

    """
    Représente une période pédagogique du programme.

    Elle correspond généralement à un semestre,
    mais peut aussi représenter une période spéciale
    comme TRANSVERSE pour les modules non rattachés
    à un semestre précis.
    """

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



class Programme(StrictBaseModel):
    """
    Représente un programme de formation complet.

    Exemple : IDU, BUT Informatique ou autre parcours.
    Il contient les périodes pédagogiques du programme.
    """

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

