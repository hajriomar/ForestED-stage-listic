"""
normalizer_factory.py
======================
Factory des normalizers ETL ForestED — registry déclarative.

Symétrique à TransformerFactory : même signature, même normalisation
(strip + lower), même mécanisme de registry avec imports paresseux.

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
Une seule ligne à ajouter dans NORMALIZERS :

    ("competence", "unita"): (
        "app.etl.normalize.unita_competence_normalizer",
        "UNITACompetenceNormalizer",
    ),

Passthrough (comportement CONSERVÉ)
-----------------------------------
Contrairement à TransformerFactory (qui refuse une source inconnue),
cette factory ne lève JAMAIS : si aucun normalizer dédié n'existe pour
(domain, source), elle retourne un PassthroughNormalizer. Celui-ci
DÉPLIE l'enveloppe JSON de l'extractor ({"file_type": "json",
"content": ...}) car les transformers "ancienne génération" attendent
le contenu brut :
- content dict : fusionné avec file_name (nécessaire à la résolution
  d'identité programme des transformers curriculum) ;
- content list : transmis tel quel ;
- Excel/CSV : enveloppes transmises telles quelles ("sheets"/"rows",
  déjà comprises par les transformers).
"""

import logging
from importlib import import_module

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry déclarative : (domain, source) -> (module, classe)
# ---------------------------------------------------------------------------

NORMALIZERS = {
    ("competence", "but"): (
        "app.etl.normalize.but_competence_normalizer",
        "BUTCompetenceNormalizer",
    ),
    ("competence", "polytech"): (
        "app.etl.normalize.polytech_competence_normalizer",
        "PolytechCompetenceNormalizer",
    ),
    ("competence", "usmb_licence"): (
        "app.etl.normalize.usmb_licence_competence_normalizer",
        "USMBLicenceCompetenceNormalizer",
    ),
    ("curriculum", "usmb_licence"): (
        # MÊME normalizer que le domaine competence : il extrait déjà
        # semestre / UA / EC / module_code / parcours dans les liens.
        "app.etl.normalize.usmb_licence_competence_normalizer",
        "USMBLicenceCompetenceNormalizer",
    ),
    # curriculum BUT/Polytech : aucun normalizer dédié -> Passthrough.
}


def _normalize_key(domain, source_name):
    return (str(domain).strip().lower(), str(source_name).strip().lower())


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
    def known_sources():
        """Couples ayant un normalizer DÉDIÉ (les autres → Passthrough)."""
        return sorted(f"{d}/{s}" for (d, s) in NORMALIZERS)

    @staticmethod
    def get_normalizer(domain: str, source_name: str):
        """
        Retourne le normalizer correspondant au domaine et à la source.

        Args:
            domain      : "competence" | "curriculum"
            source_name : "but" | "polytech" | …

        Returns:
            Instance du normalizer dédié, ou PassthroughNormalizer
            si aucun normalizer dédié n'est enregistré (jamais d'erreur).
        """
        key = _normalize_key(domain, source_name)

        entry = NORMALIZERS.get(key)
        if entry is not None:
            module_path, class_name = entry
            module = import_module(module_path)      # import paresseux
            return getattr(module, class_name)()

        logger.info(
            "NormalizerFactory : pas de normalizer dédié pour %s/%s, "
            "passthrough vers le transformer.",
            key[0], key[1],
        )
        return PassthroughNormalizer()