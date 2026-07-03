"""
Factory des transformers ETL.

Sélectionne automatiquement le transformer adapté selon :
- le domaine  : competence / curriculum
- la source   : polytech / but / futures sources

Important :
Les imports sont faits à l'intérieur de get_transformer pour éviter
qu'un transformer cassé bloque les autres transformers.

Identité du programme BUT :
    Extraite automatiquement depuis le nom de fichier source.
    Convention : QLIO_BUT_*.xlsx → programme_id="BUT_QLIO"
    Le pipeline injecte "source_file" dans raw_data pour permettre
    cette résolution automatique.
"""


class TransformerFactory:

    @staticmethod
    def get_transformer(domain, source_name):

        domain = domain.strip().lower()
        source_name = source_name.strip().lower()

        if domain == "competence":

            if source_name == "polytech":
                from app.etl.transform.competence.Polytech_competence_transformer import (
                    PolytechTransformer,
                )
                return PolytechTransformer()

            if source_name == "but":
                from app.etl.transform.competence.BUT_competence_transformer import (
                    BUTCompetenceTransformer,
                )
                return BUTCompetenceTransformer()

        if domain == "curriculum":

            if source_name == "polytech":
                from app.etl.transform.curriculum.Polytech_curriculum_transformer import (
                    PolytechCurriculumTransformer,
                )
                return PolytechCurriculumTransformer()

            if source_name == "but":
                from app.etl.transform.curriculum.BUT_curriculum_transformer import (
                    BUTCurriculumTransformer,
                )
                return BUTCurriculumTransformer()

        raise ValueError(
            f"No transformer for {domain}/{source_name}"
        )