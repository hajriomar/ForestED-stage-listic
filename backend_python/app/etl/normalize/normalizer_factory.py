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

Passthrough
-----------
Si aucun normalizer dédié n'existe pour (domain, source), la factory
retourne un PassthroughNormalizer. Celui-ci DÉPLIE l'enveloppe JSON de
l'extractor ({"file_type": "json", "content": ...}) car les transformers
"ancienne génération" attendent le contenu brut :
- content dict : fusionné avec file_name (nécessaire à la résolution
  d'identité programme des transformers curriculum) ;
- content list : transmis tel quel ;
- Excel/CSV : enveloppes transmises telles quelles ("sheets"/"rows",
  déjà comprises par les transformers).
"""

import logging

logger = logging.getLogger(__name__)


class PassthroughNormalizer:
    """Transmet la sortie de l'extractor au transformer, en dépliant
    l'enveloppe JSON que les transformers historiques ne connaissent pas."""

    def normalize(self, extracted_data):
        if (
            isinstance(extracted_data, dict)
            and extracted_data.get("file_type") == "json"
        ):
            content = extracted_data.get("content")

            if isinstance(content, dict):
                merged = dict(content)
                merged.setdefault(
                    "file_name", extracted_data.get("file_name", "")
                )
                logger.info(
                    "PassthroughNormalizer : enveloppe JSON dépliée "
                    "(dict + file_name=%s).", merged.get("file_name"),
                )
                return merged

            logger.info(
                "PassthroughNormalizer : enveloppe JSON dépliée (%s).",
                type(content).__name__,
            )
            return content

        return extracted_data


class NormalizerFactory:

    @staticmethod
    def get_normalizer(domain: str, source_name: str):
        """
        Retourne le normalizer correspondant au domaine et à la source.

        Args:
            domain      : "competence" | "curriculum"
            source_name : "but" | "polytech" | …

        Returns:
            Instance du normalizer correspondant, ou PassthroughNormalizer
            si aucun normalizer dédié n'est enregistré.
        """
        domain      = domain.strip().lower()
        source_name = source_name.strip().lower()

        if domain == "competence":

            if source_name == "but":
                from app.etl.normalize.but_competence_normalizer import (
                    BUTCompetenceNormalizer,
                )
                return BUTCompetenceNormalizer()

            if source_name == "polytech":
                from app.etl.normalize.polytech_competence_normalizer import (
                    PolytechCompetenceNormalizer,
                )
                return PolytechCompetenceNormalizer()

        if domain == "curriculum":
            pass
            # Ajouter ici les normalizers curriculum :
            # if source_name == "but":
            #     from app.etl.normalize.curriculum.but_curriculum_normalizer import ...
            #     return BUTCurriculumNormalizer()

        # Aucun normalizer dédié : passthrough (avec dépliage d'enveloppe JSON).
        logger.info(
            "NormalizerFactory : pas de normalizer dédié pour %s/%s, "
            "passthrough vers le transformer.",
            domain, source_name,
        )
        return PassthroughNormalizer()