"""
normalizer_factory.py
======================
Factory des normalizers ETL ForestED.

Symétrique à TransformerFactory : même signature, même logique de sélection.

Flux d'utilisation
------------------
    extractor = ExtractorFactory.get_extractor(file_path)
    extracted  = extractor(file_path)                           # {"file_type", ...}

    normalizer = NormalizerFactory.get_normalizer(domain, source_name)
    records    = normalizer.normalize(extracted)                # list[dict]

    transformer = TransformerFactory.get_transformer(domain, source_name)
    result      = transformer.transform(records)

Ajouter un normalizer
---------------------
1. Créer la classe dans le bon sous-dossier (competence/ ou curriculum/).
2. L'importer ici et l'enregistrer dans get_normalizer().
Le reste du pipeline ne change pas.
"""


class NormalizerFactory:

    @staticmethod
    def get_normalizer(domain: str, source_name: str):
        """
        Retourne le normalizer correspondant au domaine et à la source.

        Args:
            domain      : "competence" | "curriculum"
            source_name : "but" | "polytech" | …

        Returns:
            Instance du normalizer correspondant.

        Raises:
            ValueError: si aucun normalizer n'est trouvé.
        """
        domain      = domain.strip().lower()
        source_name = source_name.strip().lower()

        if domain == "competence":

            if source_name == "but":
                from app.etl.normalize.but_competence_normalizer import (
                    BUTCompetenceNormalizer,
                )
                return BUTCompetenceNormalizer()

            # Ajouter ici les prochains normalizers compétence :
            # if source_name == "polytech":
            #     from app.etl.normalize.competence.polytech_competence_normalizer import ...
            #     return PolytechCompetenceNormalizer()

        if domain == "curriculum":
            pass
            # Ajouter ici les normalizers curriculum :
            # if source_name == "but":
            #     from app.etl.normalize.curriculum.but_curriculum_normalizer import ...
            #     return BUTCurriculumNormalizer()

        raise ValueError(
            f"NormalizerFactory : aucun normalizer pour domain='{domain}' "
            f"source='{source_name}'.\n"
            "Pour ajouter une source : créer la classe et l'enregistrer ici."
        )