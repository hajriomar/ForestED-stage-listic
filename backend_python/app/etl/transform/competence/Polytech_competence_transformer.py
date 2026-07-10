"""
Transformer compétences pour les données Polytech.

Structures acceptées par normalize() (logs explicites) :
1. rows déjà normalisés (sortie de PolytechCompetenceNormalizer) ;
2. export phpMyAdmin brut (liste, data en position idx 2) ;
3. enveloppe Excel ("sheets") ;
4. enveloppe CSV ("rows").

Modules d'un AC :
- extraction regex depuis le libellé (comportement historique) ;
- ET champ explicite "code_module" si présent dans la row
  (nouveau format Polytech : une row par couple AC x module).
"""

import logging
import re

from app.models.competency_models import (
    ReferentielCompetences,
    Competence,
    NiveauDeveloppement,
    ApprentissageCritique,
    SousClassification,
    ComposanteEssentielle,
)

from app.etl.transform.base_transformer import BaseTransformer

logger = logging.getLogger(__name__)


class PolytechTransformer(BaseTransformer):

    def transform(self, raw_data):
        normalized_rows = self.normalize(raw_data)

        referentiel = self.build_referentiel(
            normalized_rows
        )

        flat_rows = self.flatten_referentiel(
            referentiel
        )

        return {
            "canonical": referentiel,
            "flat": flat_rows
        }

    # =====================================================
    # NORMALIZATION
    # =====================================================

    def normalize(self, raw_data):
        if self.is_normalized_rows(raw_data):
            logger.info(
                "PolytechTransformer : structure détectée = rows déjà "
                "normalisés (%d rows, normalizer dédié en amont).",
                len(raw_data),
            )
            return raw_data

        if self.is_phpmyadmin_json(raw_data):
            logger.info(
                "PolytechTransformer : structure détectée = export "
                "phpMyAdmin brut."
            )
            return self.normalize_phpmyadmin_json(raw_data)

        if self.is_excel_data(raw_data):
            logger.info(
                "PolytechTransformer : structure détectée = enveloppe Excel."
            )
            return self.normalize_excel(raw_data)

        if self.is_csv_data(raw_data):
            logger.info(
                "PolytechTransformer : structure détectée = enveloppe CSV."
            )
            return self.normalize_csv(raw_data)

        raise ValueError("Structure Polytech competence non reconnue")

    def is_normalized_rows(self, raw_data):
        """Liste plate de rows au schéma stable (sortie du normalizer)."""
        return (
            isinstance(raw_data, list)
            and len(raw_data) > 0
            and isinstance(raw_data[0], dict)
            and "code_competence" in raw_data[0]
            and "libelle_apprentissage" in raw_data[0]
        )

    def is_phpmyadmin_json(self, raw_data):
        return (
            isinstance(raw_data, list)
            and len(raw_data) > 2
            and isinstance(raw_data[2], dict)
            and "data" in raw_data[2]
        )

    def normalize_phpmyadmin_json(self, raw_data):
        return raw_data[2]["data"]

    def is_excel_data(self, raw_data):
        return (
            isinstance(raw_data, dict)
            and "sheets" in raw_data
        )

    def normalize_excel(self, raw_data):
        rows = []

        for sheet in raw_data.get("sheets", []):
            rows.extend(
                sheet.get("rows", [])
            )

        return rows

    def is_csv_data(self, raw_data):
        return (
            isinstance(raw_data, dict)
            and "rows" in raw_data
        )

    def normalize_csv(self, raw_data):
        return raw_data.get("rows", [])

    # =====================================================
    # BUILD CANONICAL MODEL
    # =====================================================

    def build_referentiel(self, rows):
        competence_dict = {}

        for row in rows:
            if not row:
                continue

            comp_code = self.clean_value(
                row.get("code_competence")
            )

            comp_nom = self.clean_value(
                row.get("libelle_competence")
            )

            niveau_raw = self.clean_value(
                row.get("niveau")
            )

            ac_id = self.clean_value(
                row.get("id_apprentissage_critique")
            )

            ac_label = self.clean_value(
                row.get("libelle_apprentissage")
            )

            if not comp_code or not comp_nom or not niveau_raw or not ac_id or not ac_label:
                continue

            try:
                niveau = int(float(niveau_raw))
            except ValueError:
                logger.warning(
                    f"Niveau invalide ignoré : {niveau_raw}"
                )
                continue

            ac_code = f"{comp_code}_N{niveau}_AC{ac_id}"

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

            ce_id = self.clean_value(
                row.get("id_composante_essentielle")
                )

            ce_label = self.clean_value(
            row.get("libelle_composante_essentielle")
            )

            if ce_id and ce_label:
                ce_code = f"{comp_code}_CE{ce_id}"

                existing_ce_codes = {
                    ce.code
                    for ce in competence.composantes_essentielles
                }

                if ce_code not in existing_ce_codes:
                    competence.composantes_essentielles.append(
                        ComposanteEssentielle(
                            code=ce_code,
                            formulation=ce_label
                        )
                    )

            niveau_description = self.clean_value(
            row.get("libelle_niveau")
            )

            niveau_obj = self.get_or_create_niveau(
                competence,
                niveau,
                niveau_description
            )

            ac_obj = self.get_or_create_ac(
                niveau_obj,
                ac_code,
                ac_label
            )

            for module in parsed_modules:
                if module not in ac_obj.modules:
                    ac_obj.modules.append(module)

            # Lien AC -> module explicite (nouveau format Polytech :
            # une row par couple AC x module, agrégation par dédup).
            module_code = self.clean_value(row.get("code_module"))
            if module_code and module_code not in ac_obj.modules:
                ac_obj.modules.append(module_code)

        sous_classification = SousClassification(
            code="Polytech",
            nom="Polytech",
            competences=list(competence_dict.values())
        )

        return ReferentielCompetences(
            intitule="Référentiel de compétences Polytech",
            sous_classifications=[sous_classification]
        )

    def get_or_create_niveau(self, competence, niveau, description=None):
        for niveau_obj in competence.niveaux_developpement:
            if niveau_obj.niveau == niveau:
                if not niveau_obj.description and description:
                    niveau_obj.description = description
                return niveau_obj

        niveau_obj = NiveauDeveloppement(
            niveau=niveau,
            description=description
        )

        competence.niveaux_developpement.append(
            niveau_obj
        )

        return niveau_obj

    def get_or_create_ac(self, niveau_obj, ac_code, ac_label):
        for ac in niveau_obj.apprentissages_critiques:
            if ac.code == ac_code:
                return ac

        ac_obj = ApprentissageCritique(
            code=ac_code,
            description=ac_label
        )

        niveau_obj.apprentissages_critiques.append(
            ac_obj
        )

        return ac_obj

    def clean_value(self, value):
        if value is None:
            return ""

        return str(value).strip()

    # =====================================================
    # FLATTEN
    # =====================================================

    def flatten_referentiel(self, referentiel):
        rows = []

        for sous_classification in referentiel.sous_classifications:
            for competence in sous_classification.competences:
                for niveau in competence.niveaux_developpement:
                    for ac in niveau.apprentissages_critiques:
                        rows.append({
                            "referentiel": referentiel.intitule,
                            "source": "Polytech",
                            "sous_classification_code": sous_classification.code,
                            "sous_classification_nom": sous_classification.nom,
                            "competence_code": competence.code,
                            "competence_nom": competence.nom,
                            "niveau": niveau.niveau,
                            "niveau_description": niveau.description,
                            "ac_code": ac.code,
                            "ac_description": ac.description,
                            "modules": ", ".join(ac.modules)
                        })

        return rows


def extract_modules_from_text(text):
    if not text:
        return []

    matches = re.findall(
        r"\b[A-Z]{3,5}\s?\d{3}",
        str(text)
    )

    modules = []

    for match in matches:
        normalized = match.replace(" ", "")
        modules.append(normalized)

    return list(dict.fromkeys(modules))