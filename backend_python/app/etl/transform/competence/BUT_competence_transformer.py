"""
BUT_competence_transformer.py
==============================
Transformer BUT Compétences — couche canonique ForestED.

Ce transformer ne connaît NI Excel NI JSON NI les positions de colonnes.
Il reçoit une liste de records normalisés (sortie du Normalizer) et
construit le méta-modèle ForestED.

Place dans le pipeline
----------------------
    Extractor → Normalizer → [ce fichier] → Loader

Records attendus en entrée (list[dict])
----------------------------------------
Chaque dict contient :
    competence_nom      str
    competence_desc     str
    parcours            str         "COMMUN" | code parcours
    semestre            int | None
    niveau              int         1 · 2 · 3
    niveau_description  str
    composantes         list[str]
    ac_id               str         identifiant prédéfini ou ""
    ac_description      str
    ressources          list[str]
    saes                list[str]
    ue                  str

Modèle ForestED produit
------------------------
    ReferentielCompetences
      └─ SousClassification   BUT_COMMUN · BUT_ATN · …
           └─ Competence       COMP_1 · COMP_ATN_1 · …
                └─ NiveauDeveloppement  N1 · N2 · N3
                     └─ ApprentissageCritique

Extensibilité
-------------
Pour ajouter une nouvelle source (BUT GMP, Polytech, API …) :
→ Créer un Normalizer dans app/etl/normalize/
→ L'enregistrer dans NormalizerFactory
→ Ce fichier ne change PAS.
"""

import logging
from typing import Any

from app.models.competency_models import (
    ApprentissageCritique,
    Competence,
    ComposanteEssentielle,
    NiveauDeveloppement,
    ReferentielCompetences,
    SousClassification,
)

logger = logging.getLogger(__name__)


class BUTCompetenceTransformer:
    """
    Construit le méta-modèle ForestED depuis des records normalisés.
    Zéro connaissance du format source.
    """

    def __init__(self, source_config: dict | None = None):
        self.source_config     = source_config or {}
        self.referentiel_label = self.source_config.get(
            "referentiel_label", "Référentiel de compétences BUT"
        )

    # ================================================================= #
    #  Point d'entrée                                                      #
    # ================================================================= #

    def transform(self, records: list[dict]) -> dict[str, Any]:
        """
        Construit le modèle canonique ForestED depuis les records normalisés.

        Args:
            records: list[dict] — sortie de BUTCompetenceNormalizer.normalize()

        Returns:
            {
                "canonical": ReferentielCompetences,
                "flat":      list[dict]               # données plates pour analytics
            }
        """
        if not isinstance(records, list):
            raise TypeError(
                "BUTCompetenceTransformer.transform() attend une list[dict] "
                f"(sortie du Normalizer), reçu : {type(records).__name__}.\n"
                "Vérifier que le Normalizer est appelé avant le Transformer."
            )

        logger.info(f"BUTCompetenceTransformer : {len(records)} records reçus")

        sous_classifications: dict[str, SousClassification] = {}
        competence_codes:     dict[tuple, str]               = {}
        ac_counters:          dict[tuple, int]               = {}
        flat_rows:            list[dict]                     = []

        for r in records:
            sous_code = f"BUT_{r['parcours']}"
            sous_nom  = "Tronc commun" if r["parcours"] == "COMMUN" else r["parcours"]

            sous_cls   = self._get_ou_creer_sous_cls(sous_classifications, sous_code, sous_nom)
            comp_code  = self._get_ou_creer_code_comp(competence_codes, sous_code, r["competence_nom"])
            competence = self._get_ou_creer_competence(sous_cls, comp_code, r["competence_nom"])
            self._ajouter_composantes(competence, r.get("composantes", []))
            niveau_obj = self._get_ou_creer_niveau(
                competence, r["niveau"], r.get("niveau_description", "")
            )

            # Code AC : id fourni par la source ou généré séquentiellement
            ac_key  = (comp_code, r["niveau"])
            ac_counters[ac_key] = ac_counters.get(ac_key, 0) + 1
            ac_code = r.get("ac_id") or f"{comp_code}_N{r['niveau']}_AC{ac_counters[ac_key]}"

            linked_modules = list(dict.fromkeys(
                r.get("saes", []) + r.get("ressources", [])
            ))

            niveau_obj.apprentissages_critiques.append(
                ApprentissageCritique(
                    code        = ac_code,
                    description = r["ac_description"],
                    modules     = linked_modules,
                )
            )

            flat_rows.append({
                "referentiel":              self.referentiel_label,
                "semestre":                 r.get("semestre"),
                "niveau":                   r["niveau"],
                "niveau_description":       r.get("niveau_description", ""),
                "sous_classification_code": sous_code,
                "sous_classification_nom":  sous_nom,
                "parcours":                 r["parcours"],
                "ue":                       r.get("ue", ""),
                "competence_code":          comp_code,
                "competence_nom":           r["competence_nom"],
                "ac_code":                  ac_code,
                "ac_description":           r["ac_description"],
                "modules":                  ", ".join(linked_modules),
            })

        n_comp = sum(len(sc.competences) for sc in sous_classifications.values())
        logger.info(f"BUTCompetenceTransformer : {n_comp} compétences · {len(flat_rows)} ACs")

        referentiel = ReferentielCompetences(
            intitule             = self.referentiel_label,
            sous_classifications = list(sous_classifications.values()),
        )
        return {"canonical": referentiel, "flat": flat_rows}

    # ================================================================= #
    #  Helpers get-or-create (modèle canonique)                           #
    # ================================================================= #

    def _get_ou_creer_sous_cls(
        self, index: dict, code: str, nom: str
    ) -> SousClassification:
        if code not in index:
            index[code] = SousClassification(code=code, nom=nom, competences=[])
        return index[code]

    def _get_ou_creer_code_comp(
        self, index: dict, sous_code: str, nom_comp: str
    ) -> str:
        key = (sous_code, nom_comp)
        if key not in index:
            existants  = [c for (sc, _), c in index.items() if sc == sous_code]
            numero     = len(existants) + 1
            suffix     = sous_code.replace("BUT_", "")
            index[key] = (
                f"COMP_{numero}"
                if suffix == "COMMUN"
                else f"COMP_{suffix}_{numero}"
            )
        return index[key]

    def _get_ou_creer_competence(
        self, sous_cls: SousClassification, code: str, nom: str
    ) -> Competence:
        for c in sous_cls.competences:
            if c.code == code:
                return c
        c = Competence(
            code                     = code,
            nom                      = nom,
            definition               = nom,
            composantes_essentielles  = [],
            situations_professionnelles = [],
            niveaux_developpement    = [],
        )
        sous_cls.competences.append(c)
        return c

    def _ajouter_composantes(
        self, competence: Competence, composantes: list[str]
    ) -> None:
        existantes = {ce.formulation for ce in competence.composantes_essentielles}
        for formulation in composantes:
            if not formulation or formulation in existantes:
                continue
            code = f"{competence.code}_CE{len(existantes) + 1}"
            competence.composantes_essentielles.append(
                ComposanteEssentielle(code=code, formulation=formulation)
            )
            existantes.add(formulation)

    def _get_ou_creer_niveau(
        self,
        competence:  Competence,
        numero:      int,
        description: str = "",
    ) -> NiveauDeveloppement:
        for n in competence.niveaux_developpement:
            if n.niveau == numero:
                if not n.description and description:
                    n.description = description
                return n
        n = NiveauDeveloppement(
            niveau                   = numero,
            description              = description,
            apprentissages_critiques = [],
        )
        competence.niveaux_developpement.append(n)
        return n