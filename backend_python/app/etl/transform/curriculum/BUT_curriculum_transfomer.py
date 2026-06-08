import logging
import re

from app.models.curriculum_models import (
    Programme,
    PeriodeProgramme,
    UniteEnseignement,
    ElementPedagogique,
)

logger = logging.getLogger(__name__)


class BUTCurriculumTransformer:
    def transform(self, raw_data):
        programme = self.build_programme(raw_data)

        flat_rows = self.flatten_programme(
            programme
        )

        return {
            "canonical": programme,
            "flat": flat_rows
        }

    def build_programme(self, raw_data):
        programme = Programme(
            id="QLIO",
            nom="BUT Qualité, Logistique Industrielle et Organisation",
            type="BUT",
            niveau="Bac+3",
            ects_total=180,
            duree=3,
            periodes=[]
        )

        periodes_map = {}

        for sheet in raw_data.get("sheets", []):
            sheet_name = sheet.get("sheet_name", "")
            rows = sheet.get("rows", [])

            semestre = self.extract_semestre(
                sheet_name
            )

            if semestre == 0:
                continue

            periode = self.get_or_create_periode(
                programme,
                periodes_map,
                semestre
            )

            headers = self.get_pedagogical_headers(
                rows
            )

            current_ue = ""

            for row in rows[6:]:
                row = self.normalize_row(row)

                if self.is_empty_row(row):
                    continue

                if self.is_metadata_row(row):
                    continue

                ue = self.clean(row[1])

                if ue:
                    current_ue = ue

                if not current_ue:
                    continue

                for index in range(10, min(len(row), len(headers))):
                    header = self.clean(headers[index])

                    if not header:
                        continue

                    if not self.is_pedagogical_element(header):
                        continue

                    element_id = self.normalize_element_id(
                        header
                    )

                    element_type = self.detect_element_type(
                        header
                    )

                    ue_obj = self.get_or_create_ue(
                        periode,
                        current_ue
                    )

                    self.get_or_create_element(
                        ue_obj,
                        element_id,
                        header,
                        element_type
                    )

        return programme

    def flatten_programme(self, programme):
        rows = []

        for periode in programme.periodes:
            for ue in periode.unites_enseignement:
                for element in ue.elements_pedagogiques:
                    rows.append({
                        "programme_id": programme.id,
                        "programme_nom": programme.nom,
                        "programme_niveau": programme.niveau,

                        "periode_id": periode.id,
                        "semestre": periode.numero,

                        "ue_id": ue.id,
                        "ue_code": ue.code,
                        "ue_nom": ue.intitule,

                        "element_id": element.id,
                        "element_nom": element.nom,
                        "element_type": element.type,

                        "ects": element.ects,
                        "cm": element.cm,
                        "td": element.td,
                        "tp": element.tp,
                        "projet": element.projet,
                        "volume_total": element.volume_total,

                        "enseignants": ""
                    })

        return rows

    def get_or_create_periode(self, programme, periodes_map, semestre):
        periode_id = f"S{semestre}"

        if periode_id in periodes_map:
            return periodes_map[periode_id]

        periode = PeriodeProgramme(
            id=periode_id,
            numero=semestre,
            ects=30,
            unites_enseignement=[]
        )

        programme.periodes.append(
            periode
        )

        periodes_map[periode_id] = periode

        return periode

    def get_or_create_ue(self, periode, ue_label):
        ue_code = self.normalize_ue_code(
            ue_label
        )

        for ue in periode.unites_enseignement:
            if ue.code == ue_code:
                return ue

        ue = UniteEnseignement(
            id=ue_code,
            code=ue_code,
            intitule=ue_label,
            ects=0.0,
            type="UE",
            elements_pedagogiques=[]
        )

        periode.unites_enseignement.append(
            ue
        )

        return ue

    def get_or_create_element(self, ue, element_id, element_name, element_type):
        for element in ue.elements_pedagogiques:
            if element.id == element_id:
                return element

        element = ElementPedagogique(
            id=element_id,
            nom=element_name,
            type=element_type,
            ects=0.0,
            cm=0.0,
            td=0.0,
            tp=0.0,
            projet=0.0
        )

        ue.elements_pedagogiques.append(
            element
        )

        return element

    def get_pedagogical_headers(self, rows):
        if len(rows) < 4:
            return []

        return [
            self.clean(value)
            for value in rows[3]
        ]

    def is_pedagogical_element(self, header):
        return (
            self.is_sae(header)
            or self.is_ressource(header)
        )

    def is_sae(self, value):
        value = self.clean(value).upper()

        return (
            value.startswith("SAE")
            or value.startswith("SAÉ")
        )

    def is_ressource(self, value):
        value = self.clean(value).upper()

        return bool(
            re.match(r"^R\d+", value)
        )

    def detect_element_type(self, value):
        if self.is_sae(value):
            return "SAE"

        if self.is_ressource(value):
            return "Ressource"

        return "Element pédagogique"

    def normalize_element_id(self, value):
        value = self.clean(value)
        value = value.replace(" ", "_")
        value = value.replace(".", "_")
        value = value.replace("-", "_")
        value = re.sub(r"_+", "_", value)

        return value.upper()

    def normalize_ue_code(self, value):
        value = self.clean(value)
        value = value.replace(" ", "_")
        value = value.replace(".", "_")

        return value.upper()

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
            "portfolio",
            "coefficients"
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