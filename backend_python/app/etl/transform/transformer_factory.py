"""
Factory des transformers ETL — registry déclarative.

Sélectionne le transformer adapté selon :
- le domaine  : competence / curriculum
- la source   : but / polytech / usmb_licence / futures sources

Ajouter une source
------------------
Une seule ligne à ajouter dans TRANSFORMERS :

    ("curriculum", "unita"): (
        "app.etl.transform.curriculum.UNITA_curriculum_transformer",
        "UNITACurriculumTransformer",
    ),

Important :
- Les imports restent PARESSEUX (import_module au moment de la demande) :
  un transformer cassé ne bloque ni les autres transformers ni l'import
  de cette factory.
- domain et source_name sont normalisés (strip + lower) : "Polytech",
  " POLYTECH " et "polytech" désignent la même source.
- Source inconnue → ValueError avec la liste des couples supportés
  (message remonté en 422 par les routes d'upload/import admin).

Identité du programme BUT :
    Extraite automatiquement depuis le nom de fichier source.
    Convention : QLIO_BUT_*.xlsx → programme_id="BUT_QLIO"
    Le pipeline injecte "source_file" dans raw_data pour permettre
    cette résolution automatique.
"""

from importlib import import_module

# ---------------------------------------------------------------------------
# Registry déclarative : (domain, source) -> (module, classe)
# Les chemins sont des chaînes pour préserver les imports paresseux.
# ---------------------------------------------------------------------------

TRANSFORMERS = {
    ("competence", "polytech"): (
        "app.etl.transform.competence.Polytech_competence_transformer",
        "PolytechTransformer",
    ),
    ("competence", "but"): (
        "app.etl.transform.competence.BUT_competence_transformer",
        "BUTCompetenceTransformer",
    ),
    ("competence", "usmb_licence"): (
        "app.etl.transform.competence.USMB_licence_competence_transformer",
        "USMBLicenceCompetenceTransformer",
    ),
    ("competence", "unita"): (
        "app.etl.transform.competence.UNITA_competence_transformer",
        "UNITACompetenceTransformer",
    ),
    ("curriculum", "polytech"): (
        "app.etl.transform.curriculum.Polytech_curriculum_transformer",
        "PolytechCurriculumTransformer",
    ),
    ("curriculum", "but"): (
        "app.etl.transform.curriculum.BUT_curriculum_transformer",
        "BUTCurriculumTransformer",
    ),
    ("curriculum", "unita"): (
        "app.etl.transform.curriculum.UNITA_curriculum_transformer",
        "UNITACurriculumTransformer",
    ),
    ("curriculum", "usmb_licence"): (
        # Curriculum « LITE » (v2) : squelette Semestre→UA→EC reconstruit
        # depuis la matrice du référentiel — ECTS/heures à 0.0, signalés
        # dans le quality_report. Remplacé le jour où une vraie maquette
        # (Pégase / ROF CDM-fr / Excel scolarité) est disponible.
        "app.etl.transform.curriculum.USMB_licence_curriculum_transformer",
        "USMBLicenceCurriculumTransformer",
    ),
}


def _normalize_key(domain, source_name):
    return (str(domain).strip().lower(), str(source_name).strip().lower())


class TransformerFactory:

    @staticmethod
    def known_sources():
        """Couples supportés, triés : ["competence/but", ...]."""
        return sorted(f"{d}/{s}" for (d, s) in TRANSFORMERS)

    @staticmethod
    def is_supported(domain, source_name):
        """True si un transformer est enregistré pour (domain, source)."""
        return _normalize_key(domain, source_name) in TRANSFORMERS

    @staticmethod
    def get_transformer(domain, source_name):
        key = _normalize_key(domain, source_name)

        entry = TRANSFORMERS.get(key)
        if entry is None:
            known = "\n".join(f"- {k}" for k in TransformerFactory.known_sources())
            raise ValueError(
                f"No transformer registered for domain='{key[0]}', "
                f"source='{key[1]}'.\n"
                f"Known transformers:\n{known}"
            )

        module_path, class_name = entry
        module = import_module(module_path)          # import paresseux
        return getattr(module, class_name)()