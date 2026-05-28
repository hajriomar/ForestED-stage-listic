"""
Méta-modèle compétences du projet ForestED.

Ce module définit les structures de données canoniques
utilisées pour représenter les référentiels de compétences.

Le modèle est générique afin de supporter plusieurs
sources de données :
- Polytech,
- BUT,
- futures sources académiques.

Le méta-modèle suit une structure hiérarchique :

Référentiel
    -> Sous-classification
        -> Compétence
            -> Niveau de développement
                -> Apprentissages critiques
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class StrictBaseModel(BaseModel):

    """
    Classe de base stricte pour tous les modèles.

    Interdit les champs non définis afin
    de garantir la conformité du schéma.
    """

    model_config = {
        "extra": "forbid"
    }


class ApprentissageCritique(StrictBaseModel):

    """
    Représente un apprentissage critique.

    Un apprentissage critique correspond
    à une capacité opérationnelle attendue
    dans un niveau de compétence donné.
    """
    
    code: str
    description: str
    modules: List[str] = Field(default_factory=list)


class NiveauDeveloppement(StrictBaseModel):
    """
    Représente un niveau de développement
    d'une compétence.

    Chaque niveau contient plusieurs
    apprentissages critiques.
    """

    niveau: int
    apprentissages_critiques: List[ApprentissageCritique] = Field(default_factory=list)


class ComposanteEssentielle(StrictBaseModel):

    """
    Représente une composante essentielle
    d'une compétence.
    """

    code: str
    formulation: str


class SituationProfessionnelle(StrictBaseModel):
    """
    Représente une situation professionnelle
    dans laquelle une compétence est mobilisée.
    """

    description: str


class CompetenceAbstract(StrictBaseModel):

    """
    Classe de base commune aux différentes formes
    de compétences du méta-modèle.

    Elle contient uniquement les attributs partagés
    par toutes les compétences, quelle que soit
    leur source ou leur niveau de détail.
    """

    code: str
    nom: str
    definition: Optional[str] = None


class CompetenceAssociee(CompetenceAbstract):
    """
    Représente une compétence associée à une compétence
    plus générale dans certains référentiels.

    Cette forme peut être utilisée pour des sources où
    les compétences sont structurées en compétence globale
    et compétences associées, par exemple un autre modèle
    de données comme BUT.

    Elle reste volontairement légère car les relations
    détaillées peuvent dépendre de la source.
    """

    pass


class Competence(CompetenceAbstract):

    """
    Représente une compétence détaillée du référentiel.

    Cette forme est utilisée lorsque la source fournit
    une compétence avec ses composantes, ses situations,
    ses niveaux de développement et ses apprentissages
    critiques, comme dans le cas Polytech.
    """

    composantes_essentielles: List[ComposanteEssentielle] = Field(default_factory=list)

    situations_professionnelles: List[SituationProfessionnelle] = Field(default_factory=list)

    niveaux_developpement: List[NiveauDeveloppement] = Field(default_factory=list)


class SousClassification(StrictBaseModel):

    """
    Représente une sous-classification
    de compétences dans le référentiel.
    """

    code: str
    nom: str
    competences: List[Competence] = Field(default_factory=list)


class ReferentielCompetences(StrictBaseModel):

    """
    Représente le référentiel global
    de compétences.
    """
    
    intitule: str = "Référentiel de compétences Polytech"

    sous_classifications: List[SousClassification] = Field(default_factory=list)