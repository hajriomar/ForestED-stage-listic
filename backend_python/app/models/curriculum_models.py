"""
Méta-modèle curriculum du projet ForestED.

Hiérarchie principale :

Programme
    -> PeriodeProgramme
        -> GroupeElementsPedagogiques
            -> GroupeElementsPedagogiquesComposite
            -> GroupeElementsPedagogiquesElementaire
                -> ElementPedagogique
                    -> ElementPedagogiqueFormatif
                    -> ElementPedagogiqueProfessionnel
                    -> ElementPedagogiqueExterne
                        -> AcquisApprentissage
                        -> ActivitePedagogique
                        -> RessourcePedagogique
                        -> Evaluation
                        -> Enseignant
"""

from abc import ABC
from typing import List, Optional, Union

from pydantic import (
    BaseModel,
    Field,
    EmailStr,
    field_validator,
    model_validator,
)


class StrictBaseModel(BaseModel):
    model_config = {
        "extra": "forbid"
    }


class RessourcePedagogique(StrictBaseModel):
    id: str
    type: Optional[str] = None
    titre: str


class ActivitePedagogique(StrictBaseModel):
    id: str
    type: Optional[str] = None
    titre: str


class Evaluation(StrictBaseModel):
    id: str
    type: Optional[str] = None
    ponderation: Optional[float] = None

    @field_validator("ponderation")
    @classmethod
    def validate_ponderation(cls, v):
        if v is not None and v < 0:
            raise ValueError("Ponderation cannot be negative")

        return v


class AcquisApprentissageElementaire(StrictBaseModel):
    id: str
    description: str


class AcquisApprentissage(StrictBaseModel):
    id: str
    description: str


class Enseignant(StrictBaseModel):
    id: str
    nom: str
    email: Optional[EmailStr] = None
    telephone: Optional[str] = None
    role: Optional[str] = None


class ElementPedagogique(StrictBaseModel, ABC):
    id: str
    nom: str
    type: Optional[str] = None
    credits: float = 0.0
    volume_total: float = 0.0

    acquis_apprentissage: List[AcquisApprentissage] = Field(default_factory=list)
    enseignants: List[Enseignant] = Field(default_factory=list)
    
    @field_validator("credits", "volume_total")
    @classmethod
    def validate_positive_values(cls, v):
        if v < 0:
            raise ValueError("Credits and volume cannot be negative")

        return v


class ElementPedagogiqueFormatif(ElementPedagogique):
    cm: float = 0.0
    td: float = 0.0
    tp: float = 0.0
    projet: float = 0.0

    ressources: List[RessourcePedagogique] = Field(default_factory=list)
    activites: List[ActivitePedagogique] = Field(default_factory=list)
    evaluations: List[Evaluation] = Field(default_factory=list)
    acquis_apprentissage_elementaires: List[AcquisApprentissageElementaire] = Field(
        default_factory=list
    )

    @field_validator("cm", "td", "tp", "projet")
    @classmethod
    def validate_hours(cls, v):
        if v < 0:
            raise ValueError("Hours cannot be negative")

        return v

    @model_validator(mode="after")
    def compute_total(self):
        self.volume_total = (
            self.cm
            + self.td
            + self.tp
            + self.projet
        )

        return self


class ElementPedagogiqueProfessionnel(ElementPedagogique):
    duree: float = 0.0
    modalite: Optional[str] = None

    @field_validator("duree")
    @classmethod
    def validate_duree(cls, v):
        if v < 0:
            raise ValueError("Duration cannot be negative")

        return v


class ElementPedagogiqueExterne(ElementPedagogique):
    source: Optional[str] = None
    organisme: Optional[str] = None



class GroupeElementsPedagogiques(StrictBaseModel, ABC):
    id: str
    code: str
    intitule: str
    credits: float = 0.0
    type: Optional[str] = None
    contrainte: Optional[str] = None

    @field_validator("credits")
    @classmethod
    def validate_credits(cls, v):
        if v < 0:
            raise ValueError("Credits cannot be negative")

        return v


class GroupeElementsPedagogiquesElementaire(
    GroupeElementsPedagogiques
):
    elements_pedagogiques: List[Union[ElementPedagogiqueFormatif,
    ElementPedagogiqueProfessionnel,
    ElementPedagogiqueExterne,]] = Field(
        default_factory=list
    )


class GroupeElementsPedagogiquesComposite(
    GroupeElementsPedagogiques
):
    groupes_elements_pedagogiques: List[
        Union[
            GroupeElementsPedagogiquesElementaire,
            "GroupeElementsPedagogiquesComposite",
        ]
    ] = Field(default_factory=list)





class PeriodeProgramme(StrictBaseModel):
    id: str
    numero: int
    ects: float = 0.0

    groupes_elements_pedagogiques: List[Union[GroupeElementsPedagogiquesElementaire,
    GroupeElementsPedagogiquesComposite,]] = Field(
        default_factory=list
    )

    @field_validator("ects")
    @classmethod
    def validate_ects(cls, v):
        if v < 0:
            raise ValueError("ECTS cannot be negative")

        return v


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
            raise ValueError("ECTS and duration cannot be negative")

        return v