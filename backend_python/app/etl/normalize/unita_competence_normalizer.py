# -*- coding: utf-8 -*-
"""
unita_competence_normalizer.py
==============================
Normalizer competence UNITA (Joint Bachelor JB_SCRL).

Place dans le pipeline
----------------------
    extract_json  ->  UNITACompetenceNormalizer  ->  UNITACompetenceTransformer

Rôle
----
Lit l'enveloppe JSON de l'extractor générique
({"file_type": "json", "content": {...}}), VALIDE le fichier source
PLO/MLO UNITA (`JB_SCRL_plo_mlo_source.json`), et produit une structure
normalisée propre pour le transformer. Ne fabrique aucun lien : il se
contente de valider et de recopier fidèlement ce que la source déclare
(y compris `aligned_plos=[]` quand la source ne fournit pas de lien).

Décisions validées (docs/UNITA_DATA_REDESIGN_AUDIT.md) respectées ici :
- 12 PLO (PLO1..PLO12) ;
- 10 modules génériques (langue M1..M5, métier BUSINESS/ECONOMICS/
  FINANCE/HR/MARKETING) ;
- un MLO reste UNE entrée avec `aligned_plos=[...]` (le DÉVELOPPEMENT en
  liens canoniques est fait plus tard, par le transformer) ;
- rien n'est inventé : un `aligned_plos` vide reste vide ;
- les `aligned_plos` doivent être un sous-ensemble des 12 PLO ; tout PLO
  inconnu est signalé au quality_report et écarté (jamais ajouté au
  hasard) ;
- les `quality_notes` de la source sont conservées.

Ce normalizer ne touche NI au curriculum, NI à l'auto-linking, NI aux
autres sources.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_EXPECTED_SOURCE = "unita"
_EXPECTED_PROGRAMME = "JB_SCRL"
_EXPECTED_PLO_COUNT = 12
_EXPECTED_PLO_CODES = [f"PLO{i}" for i in range(1, _EXPECTED_PLO_COUNT + 1)]

# Catalogue générique attendu (docs/UNITA_DATA_REDESIGN_AUDIT.md, U1A).
_EXPECTED_MODULE_CODES = [
    "UNITA_M1", "UNITA_M2", "UNITA_M3", "UNITA_M4", "UNITA_M5",
    "UNITA_BUSINESS", "UNITA_ECONOMICS", "UNITA_FINANCE",
    "UNITA_HR", "UNITA_MARKETING",
]
# Modules « métier » : chaque MLO doit hériter des PLO cochés du module
# (projection module_projected). aligned_plos == module_level_plos.
_BUSINESS_MODULE_CODES = {
    "UNITA_BUSINESS", "UNITA_ECONOMICS", "UNITA_FINANCE",
    "UNITA_HR", "UNITA_MARKETING",
}


class UNITACompetenceNormalizer:
    """Enveloppe JSON UNITA -> structure normalisée pour le transformer."""

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def normalize(self, extracted) -> dict:
        content = self._unwrap(extracted)

        report = {
            "source_name": content.get("source_name"),
            "programme_id": content.get("programme_id"),
            "warnings": [],
            "errors": [],
        }

        self._validate_identity(content, report)

        plos = self._normalize_plos(content, report)
        plo_codes = {p["code"] for p in plos}

        modules = self._normalize_modules(content, plo_codes, report)

        # Report qualité : on repart des quality_notes de la source puis on
        # ajoute les constats de validation/normalisation.
        source_notes = list(content.get("quality_notes") or [])
        report["source_quality_notes"] = source_notes
        report["plo_count"] = len(plos)
        report["module_count"] = len(modules)
        report["mlo_total"] = sum(
            len(m["module_learning_outcomes"]) for m in modules)
        report["mlo_with_aligned_plos"] = sum(
            1 for m in modules for mlo in m["module_learning_outcomes"]
            if mlo["aligned_plos"])
        report["mlo_without_aligned_plos"] = sum(
            1 for m in modules for mlo in m["module_learning_outcomes"]
            if not mlo["aligned_plos"])

        logger.info(
            "UNITACompetenceNormalizer : %s/%s -> %d PLO, %d modules, "
            "%d MLO (%d liés, %d non liés), %d warnings.",
            report["source_name"], report["programme_id"],
            report["plo_count"], report["module_count"], report["mlo_total"],
            report["mlo_with_aligned_plos"], report["mlo_without_aligned_plos"],
            len(report["warnings"]),
        )

        return {
            "source_name": content.get("source_name"),
            "programme_id": content.get("programme_id"),
            "programme_nom": content.get("programme_nom"),
            "reference_framework_name": content.get("reference_framework_name"),
            "vocabulary": content.get("vocabulary") or {},
            "plos": plos,
            "modules": modules,
            "quality_report": report,
        }

    # ------------------------------------------------------------------
    # Déballage / identité
    # ------------------------------------------------------------------

    @staticmethod
    def _unwrap(extracted) -> dict:
        """Accepte l'enveloppe extractor {"file_type":"json","content":...}
        OU directement le contenu (dict), pour rester robuste."""
        if isinstance(extracted, dict) and extracted.get("file_type") == "json":
            content = extracted.get("content")
        else:
            content = extracted
        if not isinstance(content, dict):
            raise ValueError(
                "UNITACompetenceNormalizer : contenu JSON attendu (dict), "
                f"reçu {type(content).__name__}."
            )
        return content

    def _validate_identity(self, content, report):
        source = str(content.get("source_name") or "").strip().lower()
        if source != _EXPECTED_SOURCE:
            raise ValueError(
                "UNITACompetenceNormalizer : source_name attendu "
                f"'{_EXPECTED_SOURCE}', reçu '{content.get('source_name')}'."
            )
        programme = str(content.get("programme_id") or "").strip()
        if programme != _EXPECTED_PROGRAMME:
            # non bloquant : un autre programme UNITA reste possible un jour,
            # mais on le signale explicitement.
            report["warnings"].append(
                f"programme_id attendu '{_EXPECTED_PROGRAMME}', reçu "
                f"'{content.get('programme_id')}'.")

    # ------------------------------------------------------------------
    # PLO
    # ------------------------------------------------------------------

    def _normalize_plos(self, content, report) -> list:
        raw = content.get("plos")
        if not isinstance(raw, list) or not raw:
            raise ValueError(
                "UNITACompetenceNormalizer : bloc 'plos' absent ou vide.")

        plos = []
        seen = set()
        for p in raw:
            code = str((p or {}).get("code") or "").strip()
            label = str((p or {}).get("label") or "").strip()
            if not code:
                report["warnings"].append("PLO sans code ignoré.")
                continue
            if code in seen:
                report["warnings"].append(f"PLO en double ignoré : {code}.")
                continue
            seen.add(code)
            plos.append({"code": code, "label": label})

        missing = [c for c in _EXPECTED_PLO_CODES if c not in seen]
        extra = [c for c in seen if c not in _EXPECTED_PLO_CODES]
        if missing:
            report["warnings"].append(
                f"PLO attendus manquants : {missing}.")
        if extra:
            report["warnings"].append(
                f"PLO hors référentiel attendu (PLO1..PLO12) : {extra}.")
        if len(plos) != _EXPECTED_PLO_COUNT:
            report["warnings"].append(
                f"{len(plos)} PLO trouvés (12 attendus).")
        return plos

    # ------------------------------------------------------------------
    # Modules + MLO
    # ------------------------------------------------------------------

    def _normalize_modules(self, content, plo_codes, report) -> list:
        raw = content.get("modules")
        if not isinstance(raw, list) or not raw:
            raise ValueError(
                "UNITACompetenceNormalizer : bloc 'modules' absent ou vide.")

        modules = []
        seen_codes = set()
        for m in raw:
            m = m or {}
            code = str(m.get("module_code") or "").strip()
            if not code:
                report["warnings"].append("Module sans module_code ignoré.")
                continue
            if code in seen_codes:
                report["warnings"].append(f"Module en double ignoré : {code}.")
                continue
            seen_codes.add(code)

            module_level_plos = self._clean_plo_list(
                m.get("module_level_plos"), plo_codes, code,
                "module_level_plos", report)

            mlos = []
            for mlo in (m.get("module_learning_outcomes") or []):
                mlo = mlo or {}
                mlo_code = str(mlo.get("code") or "").strip()
                text = str(mlo.get("text") or "").strip()
                if not mlo_code or not text:
                    report["warnings"].append(
                        f"MLO incomplet ignoré dans {code} "
                        f"(code/text manquant).")
                    continue
                aligned = self._clean_plo_list(
                    mlo.get("aligned_plos"), plo_codes, code,
                    f"{mlo_code}.aligned_plos", report)
                mlos.append({
                    "code": mlo_code,
                    "text": text,
                    "aligned_plos": aligned,
                })

            # Cohérence modules métier : chaque MLO doit hériter des PLO
            # cochés du module (projection module_projected). On signale
            # toute divergence, sans jamais la « corriger » en silence.
            if code in _BUSINESS_MODULE_CODES:
                for mlo in mlos:
                    if mlo["aligned_plos"] != module_level_plos:
                        report["warnings"].append(
                            f"{code}/{mlo['code']} : aligned_plos "
                            f"({mlo['aligned_plos']}) != module_level_plos "
                            f"({module_level_plos}) — projection "
                            f"module_projected attendue.")

            modules.append({
                "module_code": code,
                "scope": str(m.get("scope") or "generic"),
                "track": str(m.get("track") or ""),
                "title": str(m.get("title") or code),
                "mlo_status": m.get("mlo_status"),
                "alignment_level": m.get("alignment_level"),
                "alignment_source": m.get("alignment_source"),
                "module_level_plos": module_level_plos,
                "module_learning_outcomes": mlos,
            })

        # Vérification du catalogue générique attendu (10 modules).
        found = {mm["module_code"] for mm in modules}
        missing = [c for c in _EXPECTED_MODULE_CODES if c not in found]
        unknown = [c for c in found if c not in _EXPECTED_MODULE_CODES]
        if missing:
            report["warnings"].append(
                f"Modules génériques attendus manquants : {missing}.")
        if unknown:
            report["warnings"].append(
                f"Modules hors catalogue générique attendu : {unknown}.")
        if len(modules) != len(_EXPECTED_MODULE_CODES):
            report["warnings"].append(
                f"{len(modules)} modules trouvés (10 attendus).")

        return modules

    @staticmethod
    def _clean_plo_list(raw, plo_codes, module_code, where, report) -> list:
        """Garde uniquement des codes PLO valides (sous-ensemble des 12).
        Un PLO inconnu est écarté ET signalé — jamais ajouté au hasard."""
        if not raw:
            return []
        out = []
        for code in raw:
            c = str(code or "").strip()
            if not c:
                continue
            if c not in plo_codes:
                report["warnings"].append(
                    f"{module_code}/{where} : PLO inconnu écarté ({c}).")
                continue
            if c not in out:
                out.append(c)
        return out
