"""
Factory des transformers ETL.

Ce module implémente le Factory Pattern afin de sélectionner
automatiquement le transformer adapté selon :

- le domaine de données :
    - competence
    - curriculum

- la source des données :
    - Polytech
    - futures sources (BUT, autres écoles, etc.)

Cette architecture permet d'ajouter facilement de nouvelles
sources sans modifier le pipeline principal.
"""

from app.etl.transform.competence.Polytech_competence_transformer import (
    PolytechTransformer
)

from app.etl.transform.curriculum.Polytech_curriculum_transformer import (
    PolytechCurriculumTransformer
)


class TransformerFactory:

    """
    Factory responsable de la sélection des transformers.

    Cette classe centralise la logique de choix des transformers
    selon le domaine et la source des données.
    """

    @staticmethod
    def get_transformer(domain, source_name):

        """
        Retourner le transformer adapté.

        Args:
            domain (str):
                Domaine des données :
                - competence
                - curriculum

            source_name (str):
                Source des données :
                - Polytech
                - autres futures sources

        Returns:
            BaseTransformer:
                Instance du transformer correspondant.

        Raises:
            ValueError:
                Si aucun transformer n'existe
                pour le domaine/source demandé.
        """
        
        # ==========================================
        # COMPETENCE
        # ==========================================

        if domain == "competence":

            if source_name == "Polytech":
                return PolytechTransformer()

        # ==========================================
        # CURRICULUM
        # ==========================================

        if domain == "curriculum":

            if source_name == "Polytech":
                return PolytechCurriculumTransformer()

        raise ValueError(
            f"No transformer for "
            f"{domain}/{source_name}"
        )