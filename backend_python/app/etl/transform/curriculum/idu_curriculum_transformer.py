from app.models.curriculum_models import (
    Programme,
    PeriodeProgramme,
    UniteEnseignement,
    ElementPedagogique,
    AcquisApprentissage,
    Enseignant,
)

import re


class IDUCurriculumTransformer:

        # ==========================================
    # FLATTEN PROGRAMME
    # ==========================================

    def flatten_programme(self, programme):

        rows = []

        for periode in programme.periodes:

            for ue in periode.unites_enseignement:

                for element in ue.elements_pedagogiques:

                    enseignants = []

                    for ens in element.enseignants:

                        enseignants.append(
                            ens.nom
                        )

                    row = {

                        # ==========================
                        # PROGRAMME
                        # ==========================

                        "programme_id": programme.id,
                        "programme_nom": programme.nom,
                        "programme_niveau": programme.niveau,

                        # ==========================
                        # SEMESTER
                        # ==========================

                        "periode_id": periode.id,
                        "semestre": periode.numero,

                        # ==========================
                        # UE
                        # ==========================

                        "ue_id": ue.id,
                        "ue_code": ue.code,
                        "ue_nom": ue.intitule,

                        # ==========================
                        # ELEMENT
                        # ==========================

                        "element_id": element.id,
                        "element_nom": element.nom,
                        "element_type": element.type,

                        # ==========================
                        # HOURS
                        # ==========================

                        "ects": element.ects,
                        "cm": element.cm,
                        "td": element.td,
                        "tp": element.tp,
                        "projet": element.projet,
                        "volume_total": element.volume_total,

                        # ==========================
                        # TEACHERS
                        # ==========================

                        "enseignants": ", ".join(
                            enseignants
                        )
                    }

                    rows.append(row)

        return rows
    
    # ============================== ============
    # PARSE HOURS
    # ==========================================

    @staticmethod
    def parse_hours(value):
        """Parse hours from string format (e.g., '12h' or '12,5')."""
        if not value:
            return 0.0

        try:
            value = str(value).strip()
            value = value.replace("h", "")
            value = value.replace(",", ".")
            return float(value)
        except (ValueError, AttributeError):
            return 0.0

    # ==========================================
    # TRANSFORM
    # ==========================================

    def transform(self, data):

        # ==========================================
        # PROGRAMME
        # ==========================================

        programme = Programme(
            id="IDU",
            nom="Ingénierie des Données et des Usages",
            type="Cycle ingénieur",
            niveau="Bac+5",
            ects_total=180,
            duree=3,
            periodes=[]
        )

        # ==========================================
        # MAP SEMESTRES
        # ==========================================

        periodes_map = {}

        # ==========================================
        # FICHES
        # ==========================================

        fiches = data.get("fiches", [])

        # ==========================================
        # LOOP COURSES
        # ==========================================

        for item in fiches:

            # ==========================================
            # COURSE NAME
            # ==========================================

            nom_cours = item.get(
                "nom",
                "Cours inconnu"
            )

            # ==========================================
            # COURSE CODE
            # ==========================================

            code = item.get(
                "code",
                "UNKNOWN"
            )
            # ==========================================
            # VALID MODULE CODE
            # ==========================================

            if not re.search(
                r'[A-Z]{2,}\d{3}',
                code
                ):

                print(
                    f"Invalid module skipped: {code}"
                )

                continue

            # ==========================================
            # SEMESTER DETECTION
            # ==========================================

            semestre_num = None

            semestre = item.get(
                "semestre"
            )

            # ==========================================
            # USE EXISTING SEMESTER
            # ==========================================

            if semestre and semestre != "S0":

                semestre_match = re.search(
                    r'(\d)',
                    semestre
                )

                if semestre_match:

                    semestre_num = int(
                        semestre_match.group(1)
                    )

            # ==========================================
            # SPECIAL TRANSVERSAL MODULES
            # ==========================================

            is_transverse = any(
                prefix in code
                for prefix in [
                    "ALLE",
                    "ESPA",
                    "ITAL",
                    "CHIN",
                    "JAPO",
                    "RUSS"
                ]
            )

    
            # ==========================================
            # INFER FROM CODE
            # ==========================================

            if semestre_num is None and not is_transverse:

                match = re.search(
                 r'(\d{3})',
                  code
                )

                if match:

                    digits = match.group(1)

                    first_digit = digits[0]

                    if first_digit == "0":

                        semestre_num = 10

                    else:

                        semestre_num = int(
                            first_digit
                        )

            # ==========================================
            # FINAL FALLBACK
            # ==========================================

            if semestre_num is None:

                semestre_num = 0
            if is_transverse:

                semestre_num = -1

                periode_id = "TRANSVERSE"

            else:

                periode_id = f"S{semestre_num}"
                
            # ==========================================
            # CREATE SEMESTER
            # ==========================================

            if periode_id not in periodes_map:

                periode = PeriodeProgramme(
                    id=periode_id,
                    numero=semestre_num,
                    ects=30,
                    unites_enseignement=[],
                    stages=[]
                )

                periodes_map[periode_id] = periode

                programme.periodes.append(
                    periode
                )

            # ==========================================
            # UE
            # ==========================================

            ue = UniteEnseignement(
                id=f"UE_{code}",
                code=f"UE_{code}",
                intitule=nom_cours,
                ects=0,
                type="UE",
                elements_pedagogiques=[]
            )

            # ==========================================
            # HOURS
            # ==========================================

            cm = self.parse_hours(
                item.get("CM")
            )

            td = self.parse_hours(
                item.get("TD")
            )

            tp = self.parse_hours(
                item.get("TP")
            )

            projet = self.parse_hours(
                item.get("Projet")
            )

            # ==========================================
            # LEARNING OUTCOMES
            # ==========================================

            acquis_list = []

            objectifs = item.get(
                "objectifs",
                ""
            )

            if objectifs:

                acquis = AcquisApprentissage(
                    id=f"AC_{code}",
                    description=objectifs
                )

                acquis_list.append(acquis)


            # ==========================================
            # ENSEIGNANTS
            # ==========================================
            seen_emails = set()
            enseignants = []

            contacts = item.get(
                "contacts",
                []
            )

            for index, contact in enumerate(contacts):

                # ==========================
                # CLEAN EMAIL
                # ==========================

                raw_email = contact.get("email")

                email = None

                if raw_email:

                    raw_email = raw_email.strip()

                    if raw_email != "":
                        email = raw_email

                # ==========================
                # DUPLICATE CHECK
                # ==========================

                if email in seen_emails:
                    continue

                seen_emails.add(email)

                # ==========================
                # CREATE TEACHER
                # ==========================

                enseignant = Enseignant(

                    id=f"ENS_{code}_{index}",

                    nom=contact.get(
                        "nom",
                        ""
                    ),

                    email=email,

                    telephone=contact.get(
                        "telephone",    
                    ),

                    role="Responsable pédagogique"
                )

                enseignants.append(
                    enseignant
                )
            # ==========================================
            # PEDAGOGICAL ELEMENT
            # ==========================================

            element = ElementPedagogique(
                id=code,
                nom=nom_cours,
                type="Cours",

                ects=0,

                cm=cm,
                td=td,
                tp=tp,
                projet=projet,
                acquis=acquis_list,
                enseignants=enseignants
            )

            # ==========================================
            # ADD ELEMENT TO UE
            # ==========================================

            ue.elements_pedagogiques.append(
                element
            )

            # ==========================================
            # ADD UE TO SEMESTER
            # ==========================================

            periodes_map[
                periode_id
            ].unites_enseignement.append(
                ue
            )

        # ==========================================
        # FLATTEN & RETURN
        # ==========================================

        flat_rows = self.flatten_programme(
            programme
        )

        return {
            "canonical": programme,
            "flat": flat_rows
        }