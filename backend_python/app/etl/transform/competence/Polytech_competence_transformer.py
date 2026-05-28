"""
Transformer compétences pour les données Polytech.

Ce module transforme les données brutes du référentiel de compétences
vers deux représentations :

1. Une représentation canonique respectant le méta-modèle compétences :
   Référentiel -> Sous-classification -> Compétence ->
   Niveau de développement -> Apprentissages critiques.

2. Une représentation flat destinée aux usages analytics,
   visualisation et BI.

Le transformer applique aussi plusieurs règles métier :
- regroupement des compétences,
- regroupement des niveaux de développement,
- détection des apprentissages critiques,
- extraction automatique des codes modules depuis le texte,
- normalisation des codes modules.
"""

import logging
import re

from app.models.competency_models import (
    ReferentielCompetences,
    Competence,
    NiveauDeveloppement,
    ApprentissageCritique,
    SousClassification,
)

from app.etl.transform.base_transformer import (
    BaseTransformer
)

logger = logging.getLogger(__name__)


class PolytechTransformer(BaseTransformer):

    """
    Transformer des référentiels compétences Polytech.

    Cette classe transforme les données brutes compétences
    vers :
    - un modèle canonique respectant le méta-modèle,
    - un format flat simplifié pour analytics.
    """

    def transform(self, raw_data):

        """
        Transformer les données compétences brutes.

        Args:
            raw_data (dict): Données JSON brutes.

        Returns:
            dict:
                - canonical : modèle compétences structuré.
                - flat : représentation plate analytics.
        """

        referentiel = transform_polytech_referentiel(
            raw_data
        )

        flat_rows = self.flatten_referentiel(
            referentiel
        )

        return {
            "canonical": referentiel,
            "flat": flat_rows
        }

    def flatten_referentiel(self, referentiel):

        """
        Convertir un référentiel compétences en format plat.

        Cette méthode simplifie la structure hiérarchique
        du méta-modèle afin de faciliter :
        - l'analyse,
        - les exports,
        - les visualisations,
        - les traitements BI.

        Args:
            referentiel (ReferentielCompetences):
                Référentiel structuré.

        Returns:
            list[dict]:
                Liste de lignes plates analytics.
        """

        rows = []

        for sous_classification in referentiel.sous_classifications:

            for competence in sous_classification.competences:

                for niveau in competence.niveaux_developpement:

                    for ac in niveau.apprentissages_critiques:

                        row = {
                            "sous_classification_code": sous_classification.code,
                            "sous_classification_nom": sous_classification.nom,

                            "competence_code": competence.code,
                            "competence_nom": competence.nom,

                            "niveau": niveau.niveau,

                            "ac_code": ac.code,
                            "ac_description": ac.description,

                            "modules": ", ".join(
                                ac.modules
                            )
                        }

                        rows.append(row)

        return rows


def extract_modules_from_text(text):

    """
    Extraire automatiquement les codes modules
    depuis le texte d'un apprentissage critique.

    Cette fonction détecte les modules même
    lorsqu'ils sont :
    - entourés de texte,
    - séparés par des virgules,
    - suivis de suffixes comme _IDU,
    - écrits avec espace avant les chiffres.

    Exemples :
        INFO734_IDU -> INFO734
        SHES 901 -> SHES901

    Args:
        text (str): Texte contenant des références modules.

    Returns:
        list[str]:
            Liste des codes modules normalisés.
    """


    if not text:
        return []

    matches = re.findall(
        r'\b[A-Z]{3,5}\s?\d{3}',
        text
    )

    modules = []

    for match in matches:

        normalized = match.replace(
            " ",
            ""
        )

        modules.append(
            normalized
        )

    return list(dict.fromkeys(modules))


def transform_polytech_referentiel(raw_data):

    """
    Construire le référentiel compétences canonique.

    Cette fonction :
    - regroupe les compétences,
    - crée les niveaux de développement,
    - crée les apprentissages critiques,
    - extrait les modules associés,
    - construit la structure complète du méta-modèle.

    Args:
        raw_data (dict): Données JSON brutes compétences.

    Returns:
        ReferentielCompetences:
            Référentiel compétences structuré.
    """

    rows = raw_data[2]["data"]

    competence_dict = {}

    for row in rows:

        comp_code = row["code_competence"]
        comp_nom = row["libelle_competence"]
        niveau = int(row["niveau"])

        ac_code = (
            f"{comp_code}_N{niveau}_AC"
            f"{row['id_apprentissage_critique']}"
        )

        ac_label = row["libelle_apprentissage"]

        parsed_modules = extract_modules_from_text(
            ac_label
        )

        if comp_code not in competence_dict:

            competence_dict[comp_code] = Competence(
                code=comp_code,
                nom=comp_nom,
                definition=row.get("description")
            )

        competence = competence_dict[comp_code]

        niveau_obj = None

        for n in competence.niveaux_developpement:

            if n.niveau == niveau:
                niveau_obj = n
                break

        if niveau_obj is None:

            niveau_obj = NiveauDeveloppement(
                niveau=niveau
            )

            competence.niveaux_developpement.append(
                niveau_obj
            )

        ac_obj = None

        for ac in niveau_obj.apprentissages_critiques:

            if ac.code == ac_code:
                ac_obj = ac
                break

        if ac_obj is None:

            ac_obj = ApprentissageCritique(
                code=ac_code,
                description=ac_label
            )

            niveau_obj.apprentissages_critiques.append(
                ac_obj
            )

        for module in parsed_modules:

            if module not in ac_obj.modules:

                ac_obj.modules.append(
                    module
                )

    sous_classification = SousClassification(
        code="Polytech",
        nom="Polytech",
        competences=list(
            competence_dict.values()
        )
    )

    referentiel = ReferentielCompetences(
        intitule="Référentiel de compétences Polytech",
        sous_classifications=[
            sous_classification
        ]
    )

    return referentiel