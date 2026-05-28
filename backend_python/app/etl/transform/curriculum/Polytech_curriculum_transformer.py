"""
Transformer curriculum pour les données Polytech.

Ce module transforme les fiches de cours brutes au format JSON
vers deux représentations :

1. Une représentation canonique respectant le méta-modèle curriculum :
   Programme -> Période -> UE -> Élément pédagogique.

2. Une représentation plate destinée aux usages analytics,
   visualisation ou BI.

Le transformer applique aussi quelques règles métier :
- validation des codes modules,
- déduction du semestre depuis le code module,
- gestion des modules transverses,
- extraction des volumes horaires,
- extraction des enseignants depuis les contacts.
"""

from app.models.curriculum_models import (
    Programme,
    PeriodeProgramme,
    UniteEnseignement,
    ElementPedagogique,
    AcquisApprentissage,
    Enseignant,
)

import re


class PolytechCurriculumTransformer:

    """
    Transformer des données curriculum Polytech.

    Cette classe prend en entrée les fiches de cours brutes
    et produit un modèle canonique curriculum ainsi qu'un format flat.
    """


    def flatten_programme(self, programme):
        
        """
        Convertir un programme canonique en liste plate.

        Args:
            programme (Programme): Programme curriculum structuré.

        Returns:
            list[dict]: Liste de lignes plates contenant les informations
            principales du programme, des périodes, des UE, des éléments
            pédagogiques, des heures et des enseignants.
        """

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


                        "enseignants": ", ".join(
                            enseignants
                        )
                    }

                    rows.append(row)

        return rows


    @staticmethod
    def parse_hours(value):

        """
        Convertir une valeur horaire brute en nombre flottant.

        Cette méthode accepte des formats comme :
        - "12h"
        - "12,5h"
        - "12.5"
        - valeur vide ou absente.

        Args:
            value: Valeur horaire brute provenant du JSON.

        Returns:
            float: Nombre d'heures converti. Retourne 0.0 si la valeur
            est absente ou non convertible.
        """

        if not value:
            return 0.0

        try:
            value = str(value).strip()
            value = value.replace("h", "")
            value = value.replace(",", ".")
            return float(value)
        except (ValueError, AttributeError):
            return 0.0


    def transform(self, data):

        """
        Transformer les fiches de cours brutes en modèle curriculum.

        Args:
            data (dict): Données JSON brutes contenant une clé "fiches".

        Returns:
            dict: Dictionnaire contenant :
                - "canonical": objet Programme structuré.
                - "flat": liste plate pour analytics.
        """

        programme = Programme(
            id="IDU",
            nom="Ingénierie des Données et des Usages",
            type="Cycle ingénieur",
            niveau="Bac+5",
            ects_total=180,
            duree=3,
            periodes=[]
        )


        periodes_map = {}


        fiches = data.get("fiches", [])


        for item in fiches:


            nom_cours = item.get(
                "nom",
                "Cours inconnu"
            )


            code = item.get(
                "code",
                "UNKNOWN"
            )


            if not re.search(
                r'[A-Z]{2,}\d{3}',
                code
                ):

                print(
                    f"Invalid module skipped: {code}"
                )

                continue



            semestre_num = None

            semestre = item.get(
                "semestre"
            )



            if semestre and semestre != "S0":

                semestre_match = re.search(
                    r'(\d)',
                    semestre
                )

                if semestre_match:

                    semestre_num = int(
                        semestre_match.group(1)
                    )


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


            if semestre_num is None:

                semestre_num = 0
            if is_transverse:

                semestre_num = -1

                periode_id = "TRANSVERSE"

            else:

                periode_id = f"S{semestre_num}"
                

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


            ue = UniteEnseignement(
                id=f"UE_{code}",
                code=f"UE_{code}",
                intitule=nom_cours,
                ects=0,
                type="UE",
                elements_pedagogiques=[]
            )


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


            seen_emails = set()
            enseignants = []

            contacts = item.get(
                "contacts",
                []
            )

            for index, contact in enumerate(contacts):


                raw_email = contact.get("email")

                email = None

                if raw_email:

                    raw_email = raw_email.strip()

                    if raw_email != "":
                        email = raw_email


                if email in seen_emails:
                    continue

                seen_emails.add(email)


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


            ue.elements_pedagogiques.append(
                element
            )


            periodes_map[
                periode_id
            ].unites_enseignement.append(
                ue
            )


        flat_rows = self.flatten_programme(
            programme
        )

        return {
            "canonical": programme,
            "flat": flat_rows
        }