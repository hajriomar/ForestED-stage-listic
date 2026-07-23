# -*- coding: utf-8 -*-
"""
unita_curriculum_normalizer.py
==============================
Normalizer curriculum UNITA (Joint Bachelor JB_SCRL).

Place dans le pipeline
----------------------
    extract_json / extract_excel  ->  UNITACurriculumNormalizer
                                  ->  UNITACurriculumTransformer  ->  (loader plus tard)

Rôle
----
Lit l'enveloppe de l'extractor et produit une structure curriculum
NORMALISÉE, uniforme, prête pour le transformer — quelle que soit la
source :

- JSON générique (`JB_SCRL_curriculum_generic.json`)  -> parsing COMPLET ;
- Excel institutionnel USMB (`MAQUETTE JD ...xlsx`)    -> parsing MINIMAL
  (routage + squelette années, extraction fine encore TODO — voir
  docs/UNITA_USMB_EXCEL_INPUT_PLAN.md) ;
- d'autres fichiers institutionnels plus tard (même normalizer).

Décisions validées (docs/UNITA_DATA_REDESIGN_AUDIT.md) respectées ici :
- le curriculum ne contient JAMAIS de PLO ni d'`aligned_plos` ; on garde
  les MLO comme `acquis_apprentissage` (id + description) ;
- rien n'est inventé : l'Excel non encore parsé ne crée aucun module ;
- `institution_code` représente une VRAIE institution (jamais "__GENERIC__") :
  générique -> scope="generic",              institution_code=None, institutions=[] ;
  USMB      -> scope="institution_specific", institution_code="USMB", institutions=["USMB"].
- `upsert_institution_key` sert UNIQUEMENT à construire la clé technique
  d'upsert sans composant vide : "__GENERIC__" en générique, "USMB" pour USMB.
  Le merge/upsert lui-même est géré par le loader (pas ici).

Ce normalizer ne touche NI au domaine competence, NI aux autres sources,
NI aux modèles.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_EXPECTED_SOURCE = "unita"
_DEFAULT_PROGRAMME_ID = "JB_SCRL"

GENERIC_SCOPE = "generic"
# Clé TECHNIQUE d'upsert (jamais une institution) : évite un composant vide.
GENERIC_UPSERT_KEY = "__GENERIC__"

USMB_SCOPE = "institution_specific"
USMB_INSTITUTION = "USMB"

# Clés interdites dans un curriculum (garde-fou anti-PLO).
_FORBIDDEN_PLO_KEYS = ("aligned_plos", "plos", "plo", "module_level_plos")


class UNITACurriculumNormalizer:
    """Enveloppe extractor UNITA -> structure curriculum normalisée."""

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def normalize(self, extracted) -> dict:
        file_type, payload, file_name = self._sniff(extracted)

        if file_type == "json":
            return self._normalize_generic_json(payload, file_name)
        if file_type == "excel":
            return self._normalize_usmb_excel(payload, file_name)

        raise ValueError(
            "UNITACurriculumNormalizer : enveloppe non supportée "
            f"(file_type={file_type!r}). Attendu 'json' (générique) ou "
            "'excel' (USMB)."
        )

    # ------------------------------------------------------------------
    # Détection d'enveloppe
    # ------------------------------------------------------------------

    @staticmethod
    def _sniff(extracted):
        """Retourne (file_type, payload, file_name).

        - JSON  : payload = content (dict)
        - Excel : payload = sheets (list)
        Accepte aussi un dict brut (déballé par un Passthrough) : traité
        comme du JSON générique s'il porte 'periodes'.
        """
        if isinstance(extracted, dict) and extracted.get("file_type") == "json":
            return "json", extracted.get("content"), extracted.get("file_name", "")
        if isinstance(extracted, dict) and extracted.get("file_type") == "excel":
            return "excel", extracted.get("sheets") or [], extracted.get("file_name", "")
        if isinstance(extracted, dict) and "periodes" in extracted:
            return "json", extracted, extracted.get("file_name", "")
        return "unknown", extracted, ""

    # ==================================================================
    # Chemin 1 : JSON générique (parsing COMPLET)
    # ==================================================================

    def _normalize_generic_json(self, content, file_name) -> dict:
        if not isinstance(content, dict):
            raise ValueError(
                "UNITACurriculumNormalizer : contenu JSON attendu (dict), "
                f"reçu {type(content).__name__}."
            )

        report = {"warnings": [], "errors": [], "todo": []}

        source = str(content.get("source_name") or "").strip().lower()
        if source and source != _EXPECTED_SOURCE:
            report["warnings"].append(
                f"source_name attendu '{_EXPECTED_SOURCE}', reçu "
                f"'{content.get('source_name')}'."
            )

        scope = str(content.get("scope") or GENERIC_SCOPE).strip().lower()
        if scope != GENERIC_SCOPE:
            report["warnings"].append(
                f"scope attendu '{GENERIC_SCOPE}' pour le JSON générique, "
                f"reçu '{scope}'."
            )
        # Générique = AUCUNE institution réelle. "__GENERIC__" ne sert QUE de
        # composant technique dans la clé d'upsert.
        institution_code = None
        upsert_institution_key = GENERIC_UPSERT_KEY
        institutions = []

        programme_id = str(content.get("programme_id") or _DEFAULT_PROGRAMME_ID).strip()
        programme_nom = str(content.get("programme_nom") or programme_id).strip()

        periodes_raw = content.get("periodes")
        if not isinstance(periodes_raw, list) or not periodes_raw:
            raise ValueError(
                "UNITACurriculumNormalizer : bloc 'periodes' absent ou vide."
            )

        periodes = [self._norm_periode(p, report) for p in periodes_raw]

        n_groupes = sum(len(p["groupes"]) for p in periodes)
        n_elements = sum(self._count_elements(g) for p in periodes for g in p["groupes"])
        n_acquis = sum(self._count_acquis(g) for p in periodes for g in p["groupes"])

        report.update({
            "input_kind": "generic_json",
            "source_file": file_name,
            "scope": scope,
            "institution_code": institution_code,          # None : pas d'institution
            "upsert_institution_key": upsert_institution_key,
            "institutions": institutions,                  # []
            "periode_count": len(periodes),
            "groupe_count": n_groupes,
            "element_count": n_elements,
            "acquis_count": n_acquis,
            "plo_free": True,   # garanti par _norm_element (garde-fou)
        })

        logger.info(
            "UNITACurriculumNormalizer[JSON générique] : %s -> %d périodes, "
            "%d groupes, %d éléments, %d acquis, %d warnings.",
            programme_id, len(periodes), n_groupes, n_elements, n_acquis,
            len(report["warnings"]),
        )

        return {
            "source_name": _EXPECTED_SOURCE,
            "input_kind": "generic_json",
            "programme_id": programme_id,
            "programme_nom": programme_nom,
            "type": content.get("type"),
            "niveau": content.get("niveau"),
            "scope": scope,
            "institution_code": institution_code,          # None
            "upsert_institution_key": upsert_institution_key,
            "institutions": institutions,                  # []
            "periodes": periodes,
            "quality_report": report,
        }

    # ---- sous-normalisation période / groupe / élément ---------------

    def _norm_periode(self, p, report) -> dict:
        p = p or {}
        try:
            numero = int(p.get("numero"))
        except (TypeError, ValueError):
            numero = -1
            report["warnings"].append(
                f"Période '{p.get('id')}' sans numero entier -> -1 (transverse)."
            )
        groupes = [self._norm_groupe(g, report)
                   for g in (p.get("groupes_elements_pedagogiques") or [])]
        return {
            "id": str(p.get("id") or f"P{numero}"),
            "numero": numero,
            "ects": self._as_float(p.get("ects")),
            "groupes": groupes,
        }

    def _norm_groupe(self, g, report) -> dict:
        g = g or {}
        base = {
            "id": str(g.get("id") or g.get("code") or ""),
            "code": str(g.get("code") or g.get("id") or ""),
            "intitule": str(g.get("intitule") or g.get("code") or ""),
            "type": g.get("type"),
            "contrainte": g.get("contrainte"),
            "credits": self._as_float(g.get("credits")),
        }
        sous = g.get("groupes_elements_pedagogiques")
        if isinstance(sous, list) and sous:
            base["kind"] = "composite"
            base["sous_groupes"] = [self._norm_groupe(sg, report) for sg in sous]
            base["elements"] = []
        else:
            base["kind"] = "elementaire"
            base["sous_groupes"] = []
            base["elements"] = [self._norm_element(e, report)
                                for e in (g.get("elements_pedagogiques") or [])]
        return base

    def _norm_element(self, e, report) -> dict:
        e = e or {}
        # Garde-fou anti-PLO : aucun champ PLO ne doit transiter.
        for k in _FORBIDDEN_PLO_KEYS:
            if k in e:
                report["warnings"].append(
                    f"Élément '{e.get('id') or e.get('code')}' : champ interdit "
                    f"'{k}' retiré (le curriculum ne porte pas de PLO)."
                )
        acquis = []
        for a in (e.get("acquis_apprentissage") or []):
            a = a or {}
            aid = str(a.get("id") or "").strip()
            desc = str(a.get("description") or "").strip()
            if not aid or not desc:
                report["warnings"].append(
                    f"Acquis incomplet ignoré dans '{e.get('id')}' (id/description)."
                )
                continue
            # garde-fou : on ne recopie QUE id + description (jamais aligned_plos)
            acquis.append({"id": aid, "description": desc})
        return {
            "id": str(e.get("id") or e.get("code") or ""),
            "code": str(e.get("code") or e.get("id") or ""),
            "nom": str(e.get("nom") or e.get("id") or ""),
            "type": e.get("type"),
            "credits": self._as_float(e.get("credits")),
            "cm": self._as_float(e.get("cm")),
            "td": self._as_float(e.get("td")),
            "tp": self._as_float(e.get("tp")),
            "projet": self._as_float(e.get("projet")),
            "acquis": acquis,
        }

    # ==================================================================
    # Chemin 2 : Excel institutionnel USMB (parsing MINIMAL)
    # ==================================================================

    def _normalize_usmb_excel(self, sheets, file_name) -> dict:
        """Routage + squelette années. Aucun module n'est inventé : le
        parsing fin (blocs semestre, groupes, modules, ECTS, heures,
        Langue B/C, ambiguïté « 2 > 3 ? ») reste TODO (U3-bis)."""
        report = {"warnings": [], "errors": [], "todo": []}

        # USMB = institution réelle. Ici institution_code ET clé technique
        # d'upsert valent "USMB".
        upsert_institution_key = USMB_INSTITUTION
        institutions = [USMB_INSTITUTION]

        visible = [s for s in sheets if isinstance(s, dict)
                   and s.get("visible", True)]
        sheet_names = [s.get("sheet_name") for s in visible]

        periodes = []
        for s in visible:
            name = str(s.get("sheet_name") or "")
            numero = self._year_from_sheet_name(name)
            if numero is None:
                report["warnings"].append(
                    f"Feuille '{name}' non reconnue comme année (JD L1/L2/L3) "
                    "-> ignorée."
                )
                continue
            periodes.append({
                "id": f"USMB_Y{numero}",
                "numero": numero,
                "ects": 0.0,
                "groupes": [],   # rien inventé : parsing fin à venir
            })
        periodes.sort(key=lambda p: p["numero"])

        report.update({
            "input_kind": "usmb_excel",
            "source_file": file_name,
            "scope": USMB_SCOPE,                           # institution_specific
            "institution_code": USMB_INSTITUTION,          # USMB (vraie institution)
            "upsert_institution_key": upsert_institution_key,
            "institutions": institutions,                  # ["USMB"]
            "sheets_detected": sheet_names,
            "periode_count": len(periodes),
            "groupe_count": 0,
            "element_count": 0,
            "acquis_count": 0,
            "plo_free": True,
        })
        report["todo"].extend([
            "USMB Excel : parsing MINIMAL (routage + squelette années "
            "seulement). Aucun groupe/module/ECTS/heure extrait.",
            "TODO U3-bis : parser les blocs semestre (4 colonnes), les "
            "groupes, les modules + ECTS + heures, les choix Langue B/C, "
            "et l'ambiguïté « 2 > 3 ? » (voir "
            "docs/UNITA_USMB_EXCEL_INPUT_PLAN.md).",
        ])
        report["warnings"].append(
            "USMB Excel non entièrement parsé : curriculum institutionnel "
            "vide (aucun module inventé). Voir quality_report['todo']."
        )

        logger.info(
            "UNITACurriculumNormalizer[Excel USMB] : %s -> %d feuilles, "
            "%d années (parsing minimal, 0 module).",
            file_name, len(sheet_names), len(periodes),
        )

        return {
            "source_name": _EXPECTED_SOURCE,
            "input_kind": "usmb_excel",
            "programme_id": _DEFAULT_PROGRAMME_ID,
            "programme_nom": _DEFAULT_PROGRAMME_ID,
            "type": None,
            "niveau": None,
            "scope": USMB_SCOPE,                           # institution_specific
            "institution_code": USMB_INSTITUTION,          # USMB
            "upsert_institution_key": upsert_institution_key,
            "institutions": institutions,                  # ["USMB"]
            "periodes": periodes,
            "quality_report": report,
        }

    @staticmethod
    def _year_from_sheet_name(name):
        """'JD L1' -> 1, 'JD L2' -> 2, 'JD L3' -> 3, sinon None."""
        up = (name or "").upper().replace(" ", "")
        for n in (1, 2, 3):
            if f"L{n}" in up:
                return n
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _as_float(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    def _count_elements(self, g) -> int:
        if g.get("kind") == "composite":
            return sum(self._count_elements(sg) for sg in g.get("sous_groupes", []))
        return len(g.get("elements", []))

    def _count_acquis(self, g) -> int:
        if g.get("kind") == "composite":
            return sum(self._count_acquis(sg) for sg in g.get("sous_groupes", []))
        return sum(len(e.get("acquis", [])) for e in g.get("elements", []))
