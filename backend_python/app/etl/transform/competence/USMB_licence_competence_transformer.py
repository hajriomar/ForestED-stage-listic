# -*- coding: utf-8 -*-
"""
USMB_licence_competence_transformer.py
=======================================
Transformer Compétences pour les référentiels APC des Licences USMB.

Place dans le pipeline
----------------------
    extract_excel -> USMBLicenceCompetenceNormalizer -> [ce fichier] -> Loader

Ce transformer ne connaît NI Excel, NI openpyxl, NI les croix, NI les
couleurs : il reçoit la sortie du normalizer
    {"records": list[dict], "quality_report": dict}
et construit le méta-modèle ForestED (canonique + flat + quality_report).

Codage (convention frontend, documentée dans flat_contract.py — R4)
-------------------------------------------------------------------
    Compétence commune    : COMP_1, COMP_2, ...
    Compétence de parcours: COMP_<PARCOURS>_1, ... (ex. COMP_ERGO_PM_1)
    AC                    : <comp_code>_N<k>_AC<j>  (j séquentiel par niveau)
    Modules liés (ac.modules) :
        code EC réel si présent (MATH101_MPC, SOCI101, UAM101...),
        sinon code stable généré S<semestre>_<SLUG_LIBELLE>
        (le libellé original est conservé dans le flat "modules_libelles"
         et les codes générés listés dans quality_report.ec_without_code).

Les descriptions d'AC viennent du fichier Excel telles quelles (le
normalizer retire seulement puces et espaces) — jamais reformulées.

Cas particulier : AC sans niveau détecté (rare — STAPS). Le canonique
exige un niveau ; ces AC sont rattachés au NIVEAU 1 avec un warning
explicite dans le quality_report (jamais silencieux, rien d'inventé
au-delà de ce rattachement par défaut).

Retour : {"canonical": ReferentielCompetences, "flat": list[dict],
          "quality_report": dict}
La clé "quality_report" est ignorée par le pipeline tant que le Patch 4
(sauvegarde *_quality.json) n'est pas appliqué.
"""

import logging
import re
import unicodedata

from app.etl.transform.base_transformer import BaseTransformer
from app.models.competency_models import (
    ApprentissageCritique,
    Competence,
    ComposanteEssentielle,
    NiveauDeveloppement,
    ReferentielCompetences,
    SousClassification,
)

logger = logging.getLogger(__name__)


def _slug(text: str, max_len: int = 40) -> str:
    """'Introduction au droit privé' -> 'INTRODUCTION_AU_DROIT_PRIVE'."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", "_", text.upper()).strip("_")
    return text[:max_len].rstrip("_")


class USMBLicenceCompetenceTransformer(BaseTransformer):
    """Records normalisés USMB Licence -> méta-modèle ForestED."""

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def transform(self, normalized) -> dict:
        if not (isinstance(normalized, dict) and "records" in normalized):
            raise TypeError(
                "USMBLicenceCompetenceTransformer.transform() attend la "
                "sortie du normalizer {'records': [...], 'quality_report': "
                f"{{...}}}}, reçu : {type(normalized).__name__}.\n"
                "Vérifier que USMBLicenceCompetenceNormalizer est appelé "
                "en amont (NormalizerFactory)."
            )

        records = normalized["records"]
        report = dict(normalized.get("quality_report") or {})
        report.setdefault("warnings", [])
        report.setdefault("errors", [])

        if not records:
            raise ValueError(
                "USMBLicenceCompetenceTransformer : aucun record reçu."
            )

        programme_id = records[0]["programme_id"]
        programme_nom = records[0]["programme_nom"]

        # 1) codes compétences : COMP_n / COMP_<PARCOURS>_n
        comp_codes = self._assign_competence_codes(records)

        # 2) construction du canonique + flat
        sous_cls = SousClassification(
            code=programme_id, nom=programme_nom, competences=[])
        competences: dict = {}
        ac_counters: dict = {}
        flat_rows: list = []
        generated_codes = 0

        for rec in records:
            comp_code = comp_codes[(rec["source_sheet"],
                                    rec["competence_ordre"])]
            competence = self._get_or_create_competence(
                competences, sous_cls, comp_code, rec)

            niveau_num = rec["niveau"]
            if niveau_num is None:
                niveau_num = 1
                msg = (f"[{rec['source_sheet']}] AC sans niveau détecté "
                       f"(r{rec['source_row']}) : rattaché au NIVEAU 1 "
                       f"par défaut.")
                if msg not in report["warnings"]:
                    report["warnings"].append(msg)

            niveau_obj = self._get_or_create_niveau(
                competence, niveau_num, rec.get("niveau_description"))

            key = (comp_code, niveau_num)
            ac_counters[key] = ac_counters.get(key, 0) + 1
            ac_code = f"{comp_code}_N{niveau_num}_AC{ac_counters[key]}"

            modules, libelles, gen = self._resolve_modules(rec["liens"])
            generated_codes += gen

            niveau_obj.apprentissages_critiques.append(
                ApprentissageCritique(
                    code=ac_code,
                    description=rec["ac_description"],   # texte Excel brut
                    modules=modules,
                )
            )

            sems = sorted({l["semestre"] for l in rec["liens"]
                           if l.get("semestre")})
            ues = sorted({l["ua_code"] or l["ua_type"] for l in rec["liens"]
                          if l.get("ua_code") or l.get("ua_type")})
            parcours = rec.get("parcours") or next(
                (l["parcours"] for l in rec["liens"] if l.get("parcours")),
                None)

            flat_rows.append({
                "referentiel": (f"Référentiel de compétences "
                                f"{programme_nom} — USMB"),
                "source": "usmb_licence",
                "sous_classification_code": programme_id,
                "sous_classification_nom": programme_nom,
                "competence_code": comp_code,
                "competence_nom": rec["competence_nom"],
                "niveau": niveau_num,
                "niveau_description": rec.get("niveau_description") or "",
                "ac_code": ac_code,
                "ac_description": rec["ac_description"],
                "modules": ", ".join(modules),
                "modules_libelles": ", ".join(libelles),
                "semestre": sems[0] if sems else None,
                "parcours": parcours,
                "ue": ", ".join(ues),
                "rncp": rec.get("rncp"),
            })

        referentiel = ReferentielCompetences(
            intitule=f"Référentiel de compétences {programme_nom} — USMB",
            sous_classifications=[sous_cls],
        )

        # 3) rapport final (fusion normalizer + compteurs transformer)
        report["competences"] = len(competences)
        report["niveaux"] = sum(len(c.niveaux_developpement)
                                for c in competences.values())
        report["acs"] = len(flat_rows)
        if generated_codes:
            report["warnings"].append(
                f"{generated_codes} lien(s) AC×EC sans code EC réel : "
                f"code stable généré S<sem>_<slug> (libellés conservés "
                f"dans le flat).")

        logger.info(
            "USMBLicenceCompetenceTransformer : %s -> %d compétences, "
            "%d AC, %d lignes flat.",
            programme_id, report["competences"], report["acs"],
            len(flat_rows),
        )
        return {"canonical": referentiel, "flat": flat_rows,
                "quality_report": report}

    # ------------------------------------------------------------------
    # Codes compétences
    # ------------------------------------------------------------------

    def _assign_competence_codes(self, records) -> dict:
        """(source_sheet, competence_ordre) -> COMP_n / COMP_<PARCOURS>_n.
        Numérotation séquentielle PAR groupe de parcours (les compétences
        communes gardent COMP_1..n, chaque parcours a sa propre série),
        dans l'ordre d'apparition des feuilles."""
        codes: dict = {}
        counters: dict = {}
        for rec in records:
            key = (rec["source_sheet"], rec["competence_ordre"])
            if key in codes:
                continue
            group = rec.get("parcours")  # None = tronc commun
            counters[group] = counters.get(group, 0) + 1
            n = counters[group]
            codes[key] = (f"COMP_{group}_{n}" if group else f"COMP_{n}")
        return codes

    # ------------------------------------------------------------------
    # Helpers get-or-create (mêmes patterns que BUTCompetenceTransformer)
    # ------------------------------------------------------------------

    def _get_or_create_competence(self, index, sous_cls, comp_code, rec):
        if comp_code in index:
            return index[comp_code]
        competence = Competence(
            code=comp_code,
            nom=rec["competence_nom"],
            definition=rec["competence_nom"],
            composantes_essentielles=[],
            situations_professionnelles=[],
            niveaux_developpement=[],
        )
        for i, formulation in enumerate(rec.get("composantes") or [], 1):
            competence.composantes_essentielles.append(
                ComposanteEssentielle(code=f"{comp_code}_CE{i}",
                                      formulation=formulation))
        sous_cls.competences.append(competence)
        index[comp_code] = competence
        return competence

    def _get_or_create_niveau(self, competence, numero, description):
        for niveau in competence.niveaux_developpement:
            if niveau.niveau == numero:
                if not niveau.description and description:
                    niveau.description = description
                return niveau
        niveau = NiveauDeveloppement(
            niveau=numero, description=description or None,
            apprentissages_critiques=[])
        competence.niveaux_developpement.append(niveau)
        return niveau

    # ------------------------------------------------------------------
    # Modules liés
    # ------------------------------------------------------------------

    def _resolve_modules(self, liens):
        """Retourne (codes_modules, libelles_originaux, nb_codes_generes).

        Depuis C1, le code définitif est fourni par le NORMALIZER
        (lien["module_code"] — source de vérité unique, partagée avec le
        transformer curriculum). Le fallback local (même règle) est
        conservé pour la rétro-compatibilité avec d'anciens records."""
        modules, libelles = [], []
        generated = 0
        for lien in liens or []:
            libelle = lien.get("ec_libelle")
            code = lien.get("module_code")
            if code is None and "module_code" not in lien:
                # records pré-C1 : ancienne génération locale (identique)
                code = lien.get("ec_code")
                if not code and libelle:
                    sem = lien.get("semestre")
                    code = (f"S{sem}_{_slug(libelle)}" if sem
                            else f"SX_{_slug(libelle)}")
            if not code:
                continue  # lien sans code ni libellé : inexploitable
            if not lien.get("ec_code"):
                generated += 1
            if code not in modules:
                modules.append(code)
            if libelle and libelle not in libelles:
                libelles.append(libelle)
        return modules, libelles, generated