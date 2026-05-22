from app.etl.transform.competence.idu_competence_transformer import (
    IDUTransformer
)

from app.etl.transform.curriculum.idu_curriculum_transformer import (
    IDUCurriculumTransformer
)


class TransformerFactory:

    @staticmethod
    def get_transformer(domain, source_name):

        # ==========================================
        # COMPETENCE
        # ==========================================

        if domain == "competence":

            if source_name == "IDU":
                return IDUTransformer()

        # ==========================================
        # CURRICULUM
        # ==========================================

        if domain == "curriculum":

            if source_name == "IDU":
                return IDUCurriculumTransformer()

        raise ValueError(
            f"No transformer for "
            f"{domain}/{source_name}"
        )