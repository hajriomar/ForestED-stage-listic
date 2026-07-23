# -*- coding: utf-8 -*-
"""
UNITA_competence_transformer.py
===============================
Transformer competence UNITA (Joint Bachelor JB_SCRL).

Place dans le pipeline
----------------------
    extract_json -> UNITACompetenceNormalizer -> [ce fichier] -> Loader

Rôle
----
Transforme la structure normalisée PLO/MLO UNITA vers le modèle canonique
competence ForestED (`competency_models`) :

    ReferentielCompetences
      └─ SousClassification (JB_SCRL)
          └─ Competence          <- 1 par PLO (source-aware : PLO = compétence)
              └─ NiveauDeveloppement (niveau 1)
                  └─ ApprentissageCritique   <- 1 par couple (MLO x PLO)
                     .modules = [module_code]   (clé de jointure future)

Règles validées (docs/UNITA_DATA_REDESIGN_AUDIT.md) :
- PLO = équivalent source-aware de « compétence » ; MLO = équivalent
  source-aware d'« AC ».
- Un MLO avec plusieurs `aligned_plos` est DÉVELOPPÉ en plusieurs liens
  canoniques (un AC par couple MLO x PLO).
- Un MLO SANS `aligned_plos` n'est ni inventé ni rattaché artificiellement
  (aucun AC créé) — il est compté au quality_report.
- Modules métier : `aligned_plos` = `module_level_plos` (projection déjà
  portée par la source) -> développés comme les autres. La provenance
  (`module_projected` vs `source_declared`) est tracée au flat et au
  quality_report.
- Aucun PLO non déclaré n'est ajouté ; M3 (to_validate, sans MLO) et les
  MLO non liés (M2/M4/M5) sont signalés au quality_report.

Sortie : {"canonical": ReferentielCompetences, "flat": [...],
          "quality_report": {...}} — même contrat R4 que les autres sources.
"""

import logging

from app.etl.transform.base_transformer import BaseTransformer
from app.models.competency_models import (
    ReferentielCompetences,
    SousClassification,
    Competence,
    NiveauDeveloppement,
    ApprentissageCritique,
)

logger = logging.getLogger(__name__)

_SOURCE_LABEL = "UNITA"
_NIVEAU_UNIQUE = 1                 # UNITA n'a pas de niveaux : niveau 1 unique
_NIVEAU_DESCRIPTION = "MLO"        # vocabulaire source-aware


class UNITACompetenceTransformer(BaseTransformer):
    """Structure normalisée UNITA -> ReferentielCompetences canonique."""

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def transform(self, normalized) -> dict:
        if not (isinstance(normalized, dict) and "plos" in normalized
                and "modules" in normalized):
            raise TypeError(
                "UNITACompetenceTransformer.transform() attend la sortie du "
                "UNITACompetenceNormalizer ({'plos': [...], 'modules': [...], "
                f"...}}), reçu : {type(normalized).__name__}.")

        plos = normalized["plos"]
        modules = normalized["modules"]
        programme_id = normalized.get("programme_id") or "JB_SCRL"
        programme_nom = normalized.get("programme_nom") or programme_id
        intitule = (normalized.get("reference_framework_name")
                    or programme_nom)

        report = dict(normalized.get("quality_report") or {})
        report.setdefault("warnings", [])
        report.setdefault("errors", [])

        # 1) Une Competence par PLO (dans l'ordre du référentiel).
        competences = {}
        for plo in plos:
            competences[plo["code"]] = Competence(
                code=plo["code"],
                nom=plo["label"] or plo["code"],
                definition=None,
            )

        # 2) Développer les MLO en AC (un AC par couple MLO x PLO).
        links_created = 0
        links_by_alignment = {}          # alignment_level -> nb liens
        unlinked_mlo = []                # (module_code, mlo_code)
        modules_to_validate = []         # modules sans MLO exploitable (M3)
        skipped_unknown_plo = 0

        for module in modules:
            mcode = module["module_code"]
            align = module.get("alignment_level") or "unknown"
            mlos = module.get("module_learning_outcomes") or []

            if not mlos:
                # Cas M3 : table désalignée -> aucun MLO. Signalé, jamais
                # inventé.
                if str(module.get("mlo_status") or "").lower() == "to_validate":
                    modules_to_validate.append(mcode)
                continue

            for mlo in mlos:
                aligned = mlo.get("aligned_plos") or []
                if not aligned:
                    # MLO sans PLO -> NON rattaché (règle stricte).
                    unlinked_mlo.append((mcode, mlo["code"]))
                    continue
                for plo_code in aligned:
                    comp = competences.get(plo_code)
                    if comp is None:
                        # PLO déclaré mais absent du bloc plos -> écarté.
                        skipped_unknown_plo += 1
                        report["warnings"].append(
                            f"{mcode}/{mlo['code']} : lien vers PLO absent "
                            f"du référentiel ({plo_code}) écarté.")
                        continue
                    niveau = self._get_or_create_niveau(comp)
                    ac_code = f"{plo_code}__{mlo['code']}"
                    if self._get_or_create_ac(
                            niveau, ac_code, mlo["text"], mcode, align):
                        links_created += 1
                        links_by_alignment[align] = (
                            links_by_alignment.get(align, 0) + 1)

        # 3) Ne garder que les compétences ayant au moins un AC ? NON :
        #    on garde les 12 PLO comme compétences même sans AC (le
        #    référentiel PLO est complet et attendu par l'affichage) ; les
        #    PLO sans AC seront simplement des compétences sans AC.
        sous = SousClassification(
            code=programme_id,
            nom=programme_nom,
            competences=list(competences.values()),
        )
        referentiel = ReferentielCompetences(
            intitule=intitule,
            sous_classifications=[sous],
        )

        # PLO sans AUCUN AC canonique : simple information tracée (aucun
        # faux AC créé, aucun lien inventé).
        plos_without_ac = [
            code for code, comp in competences.items()
            if not any(niv.apprentissages_critiques
                       for niv in comp.niveaux_developpement)
        ]

        # 4) Traçabilité au quality_report.
        report.update({
            "canonical_source": "unita_plo_mlo",
            "competences_plo": len(competences),
            "ac_links_created": links_created,
            "ac_links_by_alignment_level": links_by_alignment,
            "mlo_unlinked_count": len(unlinked_mlo),
            "mlo_unlinked": [f"{m}/{c}" for (m, c) in unlinked_mlo],
            "modules_to_validate": modules_to_validate,
            "skipped_links_unknown_plo": skipped_unknown_plo,
            "plos_without_ac": plos_without_ac,
        })
        if plos_without_ac:
            report["warnings"].append(
                f"PLO sans AC canonique (aucun MLO lié) : {plos_without_ac} "
                "— information seule, aucun AC inventé.")
        if modules_to_validate:
            report["warnings"].append(
                "Modules langue sans MLO exploitable (to_validate) : "
                f"{modules_to_validate} — aucun lien créé, à revalider "
                "avec une source propre.")
        if unlinked_mlo:
            report["warnings"].append(
                f"{len(unlinked_mlo)} MLO sans PLO conservés côté source "
                "mais NON rattachés (aucun lien inventé).")

        flat_rows = self._flatten(referentiel, modules)

        logger.info(
            "UNITACompetenceTransformer : %s -> %d compétences (PLO), "
            "%d liens AC (par alignement : %s), %d MLO non liés, "
            "modules to_validate=%s.",
            programme_id, len(competences), links_created,
            links_by_alignment, len(unlinked_mlo), modules_to_validate,
        )

        return {
            "canonical": referentiel,
            "flat": flat_rows,
            "quality_report": report,
        }

    # ------------------------------------------------------------------
    # Construction canonique
    # ------------------------------------------------------------------

    @staticmethod
    def _get_or_create_niveau(competence):
        for niv in competence.niveaux_developpement:
            if niv.niveau == _NIVEAU_UNIQUE:
                return niv
        niv = NiveauDeveloppement(
            niveau=_NIVEAU_UNIQUE, description=_NIVEAU_DESCRIPTION)
        competence.niveaux_developpement.append(niv)
        return niv

    @staticmethod
    def _get_or_create_ac(niveau, ac_code, description, module_code, align):
        """Ajoute un AC (MLO développé). Retourne True si créé, False si
        déjà présent (dédup). Le module est porté par ac.modules (jointure)."""
        for ac in niveau.apprentissages_critiques:
            if ac.code == ac_code:
                if module_code and module_code not in ac.modules:
                    ac.modules.append(module_code)
                return False
        ac = ApprentissageCritique(
            code=ac_code,
            description=description,
            modules=[module_code] if module_code else [],
        )
        niveau.apprentissages_critiques.append(ac)
        return True

    # ------------------------------------------------------------------
    # Flat (contrat R4 competence) + traçabilité d'alignement
    # ------------------------------------------------------------------

    def _flatten(self, referentiel, modules):
        # module_code -> alignment_level (pour tracer la provenance au flat)
        align_by_module = {
            m["module_code"]: (m.get("alignment_level") or "unknown")
            for m in modules
        }
        rows = []
        for sous in referentiel.sous_classifications:
            for comp in sous.competences:
                for niveau in comp.niveaux_developpement:
                    for ac in niveau.apprentissages_critiques:
                        module_code = ac.modules[0] if ac.modules else ""
                        rows.append({
                            "referentiel": referentiel.intitule,
                            "source": _SOURCE_LABEL,
                            "sous_classification_code": sous.code,
                            "sous_classification_nom": sous.nom,
                            "competence_code": comp.code,
                            "competence_nom": comp.nom,
                            "niveau": niveau.niveau,
                            "niveau_description": niveau.description,
                            "ac_code": ac.code,
                            "ac_description": ac.description,
                            "modules": ", ".join(ac.modules),
                            # extra (autorisé) : traçabilité de projection
                            "module_code": module_code,
                            "alignment_level": align_by_module.get(
                                module_code, "unknown"),
                        })
        return rows
