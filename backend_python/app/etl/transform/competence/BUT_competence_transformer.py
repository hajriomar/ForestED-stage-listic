import logging
import re

from app.models.competency_models import (
    ReferentielCompetences,
    SousClassification,
    Competence,
    ComposanteEssentielle,
    NiveauDeveloppement,
    ApprentissageCritique,
)

logger = logging.getLogger(__name__)


class BUTCompetenceTransformer:
    def __init__(self, source_config=None):
        self.source_config = source_config or {}

        self.referentiel_label = self.source_config.get(
            "referentiel_label",
            "Référentiel de compétences BUT"
        )

        self.parcours_aliases = self.source_config.get(
            "parcours_aliases",
            {}
        )

    def transform(self, raw_data):
        referentiel, flat_rows = self.transform_but_referentiel(raw_data)

        return {
            "canonical": referentiel,
            "flat": flat_rows
        }

    def transform_but_referentiel(self, raw_data):
        sous_classifications = {}
        competence_codes = {}
        ac_counters = {}
        flat_rows = []

        for sheet in raw_data.get("sheets", []):
            sheet_name = sheet.get("sheet_name", "")
            rows = sheet.get("rows", [])

            semestre = self.extract_semestre(sheet_name)

            if semestre == 0:
                continue

            pedagogical_headers = self.get_pedagogical_headers(rows)
            coefficients = self.extract_coefficients(rows, pedagogical_headers)

            current_parcours = ""
            current_ue = ""
            current_competence = ""
            current_niveau_description = ""
            current_composantes = []

            for row in rows[6:]:
                row = self.normalize_row(row)

                if self.is_empty_row(row):
                    continue

                if self.is_metadata_row(row):
                    continue

                parcours_raw = self.clean(row[0])
                ue = self.clean(row[1])
                competence_name = self.clean(row[2])
                niveau_description = self.clean(row[3])
                apprentissage = self.clean(row[9])

                if parcours_raw:
                    current_parcours = parcours_raw

                if ue:
                    current_ue = ue

                if competence_name:
                    current_competence = competence_name

                if niveau_description:
                    current_niveau_description = niveau_description

                composantes = [
                    self.clean(value)
                    for value in row[4:9]
                    if self.clean(value)
                ]

                if composantes:
                    current_composantes = composantes

                if not apprentissage:
                    continue

                if apprentissage.lower().startswith("coefficients"):
                    continue

                if not current_competence:
                    continue

                sous_code = self.get_sous_classification_code(
                    current_parcours,
                    semestre
                )

                sous_nom = self.get_sous_classification_name(
                    current_parcours,
                    semestre
                )

                sous_classification = self.get_or_create_sous_classification(
                    sous_classifications,
                    sous_code,
                    sous_nom
                )

                comp_code = self.get_or_create_competence_code(
                    competence_codes,
                    sous_code,
                    current_competence
                )

                competence = self.get_or_create_competence(
                    sous_classification,
                    comp_code,
                    current_competence
                )

                self.add_composantes(
                    competence,
                    current_composantes
                )

                niveau_number = self.semestre_to_niveau(semestre)

                niveau_obj = self.get_or_create_niveau(
                    competence,
                    niveau_number,
                    current_niveau_description
                )

                ac_key = (comp_code, niveau_number)

                ac_counters[ac_key] = ac_counters.get(ac_key, 0) + 1

                ac_code = (
                    f"{comp_code}_N{niveau_number}_AC"
                    f"{ac_counters[ac_key]}"
                )

                ressources = self.extract_linked_ressources(
                    row,
                    pedagogical_headers
                )

                saes = self.extract_linked_saes(
                    row,
                    pedagogical_headers
                )

                ac_coefficients = {
                    sae: coefficients.get(sae)
                    for sae in saes
                    if sae in coefficients
                }

                linked_modules = list(dict.fromkeys(
                saes + ressources
                ))

                ac_obj = ApprentissageCritique(
                code=ac_code,
                description=apprentissage,
                modules=linked_modules,
                )

                niveau_obj.apprentissages_critiques.append(ac_obj)

                flat_rows.append(
                    {
                        "referentiel": self.referentiel_label,
                        "semestre": semestre,
                        "niveau": niveau_number,
                        "niveau_description": current_niveau_description,
                        "sous_classification_code": sous_code,
                        "sous_classification_nom": sous_nom,
                        "parcours_code_original": current_parcours or "COMMUN",
                        "ue": current_ue,
                        "competence_code": comp_code,
                        "competence_nom": current_competence,
                        "ac_code": ac_code,
                        "ac_description": apprentissage,
                        "modules": ", ".join(linked_modules),
                    }
                )

        referentiel = ReferentielCompetences(
            intitule=self.referentiel_label,
            sous_classifications=list(sous_classifications.values())
        )

        return referentiel, flat_rows

    def get_pedagogical_headers(self, rows):
        if len(rows) < 4:
            return []

        return [
            self.clean(value)
            for value in rows[3]
        ]

    def extract_coefficients(self, rows, headers):
        coefficients = {}

        for row in rows:
            row = self.normalize_row(row)

            row_text = " ".join(
                self.clean(value).lower()
                for value in row
                if value is not None
            )

            if "coefficients" not in row_text:
                continue

            for index in range(10, min(len(row), len(headers))):
                header = self.clean(headers[index])
                value = row[index]

                if not header:
                    continue

                if not self.is_sae(header):
                    continue

                try:
                    if value is not None and self.clean(value) != "":
                        coefficients[header] = float(value)
                except ValueError:
                    continue

        return coefficients

    def extract_linked_ressources(self, row, headers):
        ressources = []

        for index in range(10, min(len(row), len(headers))):
            value = self.clean(row[index])
            header = self.clean(headers[index])

            if not header:
                continue

            if value.lower() != "x":
                continue

            if self.is_ressource(header):
                ressources.append(header)

        return ressources

    def extract_linked_saes(self, row, headers):
        saes = []

        for index in range(10, min(len(row), len(headers))):
            value = self.clean(row[index])
            header = self.clean(headers[index])

            if not header:
                continue

            if value.lower() != "x":
                continue

            if self.is_sae(header):
                saes.append(header)

        return saes

    def is_ressource(self, header):
        header = self.clean(header).upper()
        return bool(re.match(r"^R\d+", header))

    def is_sae(self, header):
        header = self.clean(header).upper()
        return (
            header.startswith("SAE")
            or header.startswith("SAÉ")
        )

    def get_sous_classification_code(self, parcours_raw, semestre):
        parcours_code = self.normalize_parcours_code(
            parcours_raw,
            semestre
        )

        return f"BUT_{parcours_code}"

    def get_sous_classification_name(self, parcours_raw, semestre):
        parcours_code = self.normalize_parcours_code(
            parcours_raw,
            semestre
        )

        if parcours_code == "COMMUN":
            return "Tronc commun"

        return parcours_code

    def normalize_parcours_code(self, parcours_raw, semestre):
        if semestre in [1, 2]:
            return "COMMUN"

        parcours = self.clean(parcours_raw).upper()

        if not parcours:
            return "COMMUN"

        return self.parcours_aliases.get(
            parcours,
            parcours
        )

    def get_or_create_sous_classification(
        self,
        sous_classifications,
        sous_code,
        sous_nom
    ):
        if sous_code not in sous_classifications:
            sous_classifications[sous_code] = SousClassification(
                code=sous_code,
                nom=sous_nom,
                competences=[]
            )

        return sous_classifications[sous_code]

    def get_or_create_competence_code(
        self,
        competence_codes,
        sous_code,
        competence_name
    ):
        key = (sous_code, competence_name)

        if key not in competence_codes:
            existing_codes = [
                code
                for (existing_sous_code, _), code
                in competence_codes.items()
                if existing_sous_code == sous_code
            ]

            index = len(existing_codes) + 1
            parcours_suffix = sous_code.replace("BUT_", "")

            if parcours_suffix == "COMMUN":
                competence_codes[key] = f"COMP_{index}"
            else:
                competence_codes[key] = (
                    f"COMP_{parcours_suffix}_{index}"
                )

        return competence_codes[key]

    def get_or_create_competence(
        self,
        sous_classification,
        comp_code,
        competence_name
    ):
        for competence in sous_classification.competences:
            if competence.code == comp_code:
                return competence

        competence = Competence(
            code=comp_code,
            nom=competence_name,
            definition=competence_name,
            composantes_essentielles=[],
            situations_professionnelles=[],
            niveaux_developpement=[]
        )

        sous_classification.competences.append(competence)

        return competence

    def add_composantes(self, competence, composantes):
        existing = {
            composante.formulation
            for composante in competence.composantes_essentielles
        }

        for formulation in composantes:
            if not formulation:
                continue

            if formulation in existing:
                continue

            code = (
                f"{competence.code}_CE"
                f"{len(existing) + 1}"
            )

            competence.composantes_essentielles.append(
                ComposanteEssentielle(
                    code=code,
                    formulation=formulation
                )
            )

            existing.add(formulation)

    def get_or_create_niveau(
        self,
        competence,
        niveau_number,
        niveau_description=None
    ):
        for niveau in competence.niveaux_developpement:
            if niveau.niveau == niveau_number:
                if not niveau.description and niveau_description:
                    niveau.description = niveau_description
                return niveau

        niveau = NiveauDeveloppement(
            niveau=niveau_number,
            description=niveau_description,
            apprentissages_critiques=[]
        )

        competence.niveaux_developpement.append(niveau)

        return niveau

    def semestre_to_niveau(self, semestre):
        if semestre in [1, 2]:
            return 1

        if semestre in [3, 4]:
            return 2

        if semestre in [5, 6]:
            return 3

        return 0

    def extract_semestre(self, sheet_name):
        match = re.search(
            r"semestre\s*(\d+)",
            sheet_name,
            re.IGNORECASE
        )

        if match:
            return int(match.group(1))

        return 0

    def is_metadata_row(self, row):
        text = " ".join(
            self.clean(value).lower()
            for value in row
            if value is not None
        )

        ignored_keywords = [
            "volume horaire",
            "dont cm",
            "dont td",
            "dont tp",
            "heures de projet",
            "type de b.u.t",
            "portfolio"
        ]

        return any(
            keyword in text
            for keyword in ignored_keywords
        )

    def is_empty_row(self, row):
        return all(
            self.clean(value) == ""
            for value in row
        )

    def normalize_row(self, row):
        row = list(row)

        if len(row) < 10:
            row = row + [None] * (10 - len(row))

        return row

    def clean(self, value):
        if value is None:
            return ""

        return (
            str(value)
            .replace("\n", " ")
            .replace("\xa0", " ")
            .strip()
        )