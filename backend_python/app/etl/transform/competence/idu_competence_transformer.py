import logging

from app.models.competency_models import (
    ReferentielCompetences,
    Competence,
    NiveauDeveloppement,
    ApprentissageCritique
)

from app.etl.transform.base_transformer import (
    BaseTransformer
)

logger = logging.getLogger(__name__)


class IDUTransformer(BaseTransformer):

    # ==========================================
    # TRANSFORM
    # ==========================================

    def transform(self, raw_data):

        referentiel = transform_idu_referentiel(
            raw_data
        )

        flat_rows = self.flatten_referentiel(
            referentiel
        )

        return {

            "canonical": referentiel,

            "flat": flat_rows
        }

    # ==========================================
    # FLATTEN REFERENTIEL
    # ==========================================

    def flatten_referentiel(
        self,
        referentiel
    ):

        rows = []

        for competence in referentiel.competences:

            for niveau in competence.niveaux:

                for ac in niveau.apprentissages_critiques:

                    row = {

                        # ==========================
                        # COMPETENCE
                        # ==========================

                        "competence_code":
                            competence.code,

                        "competence_nom":
                            competence.nom,

                        # ==========================
                        # NIVEAU
                        # ==========================

                        "niveau":
                            niveau.niveau,

                        # ==========================
                        # APPRENTISSAGE CRITIQUE
                        # ==========================

                        "ac_id":
                            ac.id,

                        "ac_description":
                            ac.description,

                        # ==========================
                        # MODULES
                        # ==========================

                        "modules":
                            ", ".join(
                                ac.modules
                            )
                    }

                    rows.append(row)

        return rows


# ==========================================
# BUILD REFERENTIEL
# ==========================================

def transform_idu_referentiel(raw_data):

    rows = raw_data[2]["data"]

    competence_dict = {}

    for row in rows:

        comp_code = row[
            "code_competence"
        ]

        comp_nom = row[
            "libelle_competence"
        ]

        niveau = row[
            "niveau"
        ]

        ac_id = row[
            'concat(APC_competence.code_competence,"_N",APC_niveau.niveau,"_AC",APC_apprentissage_critique.id_apprentissage_critique)'
        ]

        ac_label = row[
            "libelle_apprentissage"
        ]

        module = row[
            "code_module"
        ]

        # ==========================================
        # COMPETENCE
        # ==========================================

        if comp_code not in competence_dict:

            competence_dict[
                comp_code
            ] = Competence(

                code=comp_code,

                nom=comp_nom
            )

        competence = competence_dict[
            comp_code
        ]

        # ==========================================
        # NIVEAU
        # ==========================================

        niveau_obj = None

        for n in competence.niveaux:

            if n.niveau == niveau:

                niveau_obj = n

                break

        if niveau_obj is None:

            niveau_obj = NiveauDeveloppement(
                niveau=niveau
            )

            competence.niveaux.append(
                niveau_obj
            )

        # ==========================================
        # APPRENTISSAGE CRITIQUE
        # ==========================================

        ac_obj = None

        for ac in niveau_obj.apprentissages_critiques:

            if ac.id == ac_id:

                ac_obj = ac

                break

        if ac_obj is None:

            ac_obj = ApprentissageCritique(

                id=ac_id,

                description=ac_label
            )

            niveau_obj.apprentissages_critiques.append(
                ac_obj
            )

        # ==========================================
        # MODULES
        # ==========================================

        if module not in ac_obj.modules:

            ac_obj.modules.append(
                module
            )

    # ==========================================
    # REFERENTIEL
    # ==========================================

    referentiel = ReferentielCompetences(

        competences=list(
            competence_dict.values()
        )
    )

    return referentiel