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
- Excel institutionnel USMB (`MAQUETTE JD ...xlsx`)    -> parsing réel
  (semestres, groupes, modules, volumes, et colonne de correspondance
  générique quand elle existe) ;
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
import re
import unicodedata

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

# Valeurs autorisées dans la colonne Excel "Correspondance générique".
# L'utilisateur écrit des noms lisibles ; le normalizer les convertit en
# codes internes UNITA utilisés par le référentiel générique.
_GENERIC_REF_TO_CODE = {
    "business": "UNITA_BUSINESS",
    "economics": "UNITA_ECONOMICS",
    "economie": "UNITA_ECONOMICS",
    "économie": "UNITA_ECONOMICS",
    "finance": "UNITA_FINANCE",
    "hr": "UNITA_HR",
    "human resources": "UNITA_HR",
    "human resource": "UNITA_HR",
    "ressources humaines": "UNITA_HR",
    "marketing": "UNITA_MARKETING",
}

_TO_VALIDATE_VALUES = {
    "a valider",
    "à valider",
    "to validate",
    "to_validate",
    "to-validate",
    "non mappe",
    "non mappé",
}


class UNITACurriculumNormalizer:
    """Enveloppe extractor UNITA -> structure curriculum normalisée."""

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def normalize(self, extracted) -> dict:
        # Indice d'institution optionnel (formulaire admin). Permet de traiter
        # d'autres institutions (HES-SO, UPPA…) sans hardcoder USMB. Absent
        # -> USMB par défaut (rétro-compatibilité).
        institution = None
        if isinstance(extracted, dict):
            institution = extracted.get("institution_hint")

        file_type, payload, file_name = self._sniff(extracted)

        if file_type == "json":
            return self._normalize_generic_json(payload, file_name)
        if file_type == "excel":
            return self._normalize_usmb_excel(payload, file_name, institution)

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

    # --- regex de classification (maquette USMB) -----------------------
    _UE_CODE_RE = re.compile(r"^\s*(UA[FMI]\s?\d{3})\b", re.I)
    _COURSE_CODE_RE = re.compile(r"^\s*([A-Z]{4}\d{3}_[A-Z]{2,4})\b")
    _CHOIX_RE = re.compile(r"choix\s+langue", re.I)
    _SEMESTRE_RE = re.compile(r"SEMESTRE\s*(\d+)", re.I)
    _HOUR_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*h?\s*([A-Za-zÀ-ÿ]+)")

    def _normalize_usmb_excel(self, sheets, file_name, institution=None) -> dict:
        """Parsing RÉEL de la maquette institution-specific (ex. USMB).

        1 feuille = 1 année ; 2 semestres côte à côte (colonnes A-D = semestre
        impair, E-H = semestre pair). Hiérarchie SEMESTRE -> UE (groupe) ->
        modules. Rien n'est inventé : toute cellule douteuse va au
        quality_report['ambiguities']. Les métadonnées techniques
        (generic_module_code, match_status, source_sheet, source_cell) sont
        portées par chaque élément normalisé pour le flat/upsert — jamais
        dans le canonical.
        """
        report = {"warnings": [], "errors": [], "todo": [], "ambiguities": []}

        # Institution réelle : fournie par le formulaire admin, sinon USMB
        # par défaut (première maquette disponible). Jamais "__GENERIC__".
        inst = self._sanitize_institution(institution)
        upsert_institution_key = inst
        institutions = [inst]

        visible = [s for s in sheets if isinstance(s, dict)
                   and s.get("visible", True)]
        sheet_names = [s.get("sheet_name") for s in visible]

        periodes = []
        for s in visible:
            name = str(s.get("sheet_name") or "")
            year = self._year_from_sheet_name(name)
            if year is None:
                report["warnings"].append(
                    f"Feuille '{name}' non reconnue comme année (JD L1/L2/L3) "
                    "-> ignorée.")
                continue
            rows = s.get("rows") or []
            for band in self._detect_semester_bands(rows, name, report):
                periodes.append(
                    self._parse_semester_band(
                        rows, band, year, name, report, inst))

        periodes.sort(key=lambda p: p["numero"])

        n_groupes = sum(len(p["groupes"]) for p in periodes)
        n_elements = sum(self._count_elements(g)
                         for p in periodes for g in p["groupes"])

        report.update({
            "input_kind": "usmb_excel",
            "source_file": file_name,
            "scope": USMB_SCOPE,                           # institution_specific
            "institution_code": inst,                      # vraie institution
            "upsert_institution_key": upsert_institution_key,
            "institutions": institutions,                  # [inst]
            "sheets_detected": sheet_names,
            "periode_count": len(periodes),
            "groupe_count": n_groupes,
            "element_count": n_elements,
            "acquis_count": 0,          # l'Excel USMB ne fournit pas de MLO
            "plo_free": True,
        })

        logger.info(
            "UNITACurriculumNormalizer[Excel USMB] : %s -> %d semestres, "
            "%d groupes, %d modules, %d ambiguïtés.",
            file_name, len(periodes), n_groupes, n_elements,
            len(report["ambiguities"]),
        )

        return {
            "source_name": _EXPECTED_SOURCE,
            "input_kind": "usmb_excel",
            "programme_id": _DEFAULT_PROGRAMME_ID,
            "programme_nom": _DEFAULT_PROGRAMME_ID,
            "type": None,
            "niveau": None,
            "scope": USMB_SCOPE,                           # institution_specific
            "institution_code": inst,                      # vraie institution
            "upsert_institution_key": upsert_institution_key,
            "institutions": institutions,                  # [inst]
            "periodes": periodes,
            "quality_report": report,
        }

    @staticmethod
    def _sanitize_institution(value) -> str:
        """Code institution normalisé (MAJUSCULES alphanum). Vide -> USMB."""
        code = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
        return code or USMB_INSTITUTION

    # ---- détection des bandes semestre --------------------------------

    def _detect_semester_bands(self, rows, sheet_name, report) -> list:
        """Repère chaque cellule 'SEMESTRE n' et en déduit une bande.

        Ancien format supporté :
            Intitulé | ECTS | VOL HOR | ENSEIGNANTS

        Nouveau format supporté :
            Intitulé | ECTS | VOL HOR | ENSEIGNANTS | Correspondance générique

        La colonne "Correspondance générique" est détectée par son en-tête.
        On ne suppose pas aveuglément c+4, afin de ne pas casser les anciennes
        maquettes où la colonne suivante peut être le semestre de droite.
        """
        markers = []
        for r, row in enumerate(rows or []):
            for c, val in enumerate(row or []):
                m = self._SEMESTRE_RE.search(str(val or ""))
                if m:
                    markers.append((r, c, int(m.group(1))))

        bands = []
        for r, c, semester_no in markers:
            same_row_next_cols = [c2 for r2, c2, _s in markers if r2 == r and c2 > c]
            right_limit = min(same_row_next_cols) if same_row_next_cols else None

            header_row_idx = r + 1
            header_row = rows[header_row_idx] if 0 <= header_row_idx < len(rows) else []

            # Défauts historiques : A/B/C/D ou F/G/H/I selon la bande.
            ects_col = c + 1
            hours_col = c + 2
            teachers_col = c + 3
            generic_ref_col = None

            scan_stop = right_limit if right_limit is not None else len(header_row)
            for hc in range(c + 1, scan_stop):
                hnorm = self._normalize_header(self._cell(rows, header_row_idx, hc))
                if not hnorm:
                    continue
                if hnorm == "ects":
                    ects_col = hc
                elif "vol" in hnorm and "hor" in hnorm:
                    hours_col = hc
                elif "enseign" in hnorm:
                    teachers_col = hc
                elif "correspondance" in hnorm and "generique" in hnorm:
                    generic_ref_col = hc

            bands.append({
                "semester_no": semester_no,
                "label_col": c,
                "ects_col": ects_col,
                "hours_col": hours_col,
                "teachers_col": teachers_col,
                "generic_ref_col": generic_ref_col,
                "start": r + 2,        # saute la ligne SEMESTRE + en-têtes
                "end": len(rows),
            })

        if not bands:
            report["warnings"].append(
                f"Feuille '{sheet_name}' : aucun repère 'SEMESTRE n'.")
        return bands

    # ---- parsing d'une bande semestre ---------------------------------

    def _parse_semester_band(self, rows, band, year, sheet_name, report,
                             inst="USMB") -> dict:
        sem = band["semester_no"]
        periode = {"id": f"S{sem}", "numero": sem, "ects": 0.0, "groupes": []}
        current_group = None       # dict elementaire courant
        current_composite = None   # dict composite courant (CHOIX LANGUE)
        channel = None             # "B"/"C" langue en cours (inférence)
        seq = 0

        for r in range(band["start"], band["end"]):
            label = str(self._cell(rows, r, band["label_col"]) or "").strip()
            ects_raw = self._cell(rows, r, band["ects_col"])
            hours_raw = self._cell(rows, r, band["hours_col"])
            generic_ref_raw = self._cell(rows, r, band.get("generic_ref_col"))
            has_hours = bool(str(hours_raw or "").strip())
            if not label and not self._has_number(ects_raw) and not has_hours:
                continue
            coord = f"{self._col_letter(band['label_col'])}{r + 1}"

            # 1) En-tête CHOIX LANGUE -> Composite (groupe de choix)
            if self._CHOIX_RE.search(label):
                ch = re.search(r"langue\s+([BC])", label, re.I)
                channel = ch.group(1).upper() if ch else None
                current_composite = {
                    "kind": "composite",
                    "id": f"{inst}_S{sem}_CHOIX_LANGUE_{channel or 'X'}",
                    "code": f"S{sem}_CHOIX_LANGUE_{channel or 'X'}",
                    "intitule": label,
                    "type": "CHOIX_LANGUE",
                    "contrainte": label,
                    "credits": self._parse_ects(label.split(":")[-1]),
                    "sous_groupes": [],
                    "elements": [],
                }
                periode["groupes"].append(current_composite)
                current_group = None
                continue

            # 2) En-tête de groupe (UE / total sans intitulé)
            if self._is_group_header(label, ects_raw, has_hours):
                code = self._group_code(label, sem, seq)
                grp = {
                    "kind": "elementaire",
                    "id": f"{inst}_{code}",
                    "code": code,
                    "intitule": label or f"Groupe {code}",
                    "type": self._classify_discipline(label) if label else "UE",
                    "contrainte": None,
                    "credits": self._parse_ects(ects_raw),
                    "sous_groupes": [],
                    "elements": [],
                }
                if not label:
                    report["ambiguities"].append(
                        f"{sheet_name}!{coord} : groupe sans intitulé "
                        f"(ECTS={ects_raw!r}) -> code généré {code}.")
                if current_composite is not None:
                    current_composite["sous_groupes"].append(grp)
                else:
                    periode["groupes"].append(grp)
                current_group = grp
                seq += 1
                continue

            # 3) Module (cours)
            if self._is_module(label, ects_raw, has_hours):
                seq += 1
                if current_group is None:
                    current_group = {
                        "kind": "elementaire", "id": f"{inst}_S{sem}_DIVERS",
                        "code": f"S{sem}_DIVERS", "intitule": "Modules divers",
                        "type": "UE", "contrainte": None, "credits": 0.0,
                        "sous_groupes": [], "elements": []}
                    periode["groupes"].append(current_group)
                hours, unknown = self._parse_hours(hours_raw)
                disc = self._classify_discipline(label)
                manual_code, manual_status = self._resolve_generic_reference(
                    generic_ref_raw, year, report, sheet_name, coord
                )
                if manual_code:
                    gcode, mstatus = manual_code, manual_status
                elif manual_status:
                    # Valeur explicite mais non reliée : on respecte le choix
                    # manuel et on n'applique pas l'inférence automatique.
                    gcode, mstatus = "", manual_status
                else:
                    # Rétro-compatibilité : ancienne maquette sans colonne
                    # Correspondance générique -> inférence prudente des langues.
                    gcode, mstatus = self._infer_link(year, channel, disc)
                elem_id = f"{inst}_S{sem}_E{seq:02d}"
                element = {
                    "id": elem_id,
                    "code": self._course_code(label) or elem_id,
                    "nom": label,
                    "type": disc,
                    "credits": self._parse_ects(ects_raw),
                    "cm": hours["cm"], "td": hours["td"],
                    "tp": hours["tp"], "projet": hours["projet"],
                    "acquis": [],   # l'Excel ne fournit pas de MLO
                    # --- métadonnées techniques (flat/upsert, JAMAIS canonical)
                    "generic_module_code": gcode,
                    "generic_ref_label": str(generic_ref_raw or "").strip(),
                    "match_status": mstatus,
                    "source_sheet": sheet_name,
                    "source_cell": coord,
                }
                current_group["elements"].append(element)
                if re.search(r"\?|>|\bou\b", label, re.I) or ">" in str(ects_raw):
                    report["ambiguities"].append(
                        f"{sheet_name}!{coord} : '{label}' ECTS={ects_raw!r} -> "
                        f"credits={element['credits']} (valeur déterministe, "
                        f"à vérifier).")
                if unknown:
                    report["ambiguities"].append(
                        f"{sheet_name}!{coord} : volumes non mappés {unknown} "
                        f"(seuls CM/TD/TP retenus).")
                continue

            # 4) Texte libre / note -> quality_report
            report["ambiguities"].append(
                f"{sheet_name}!{coord} : texte ignoré '{label}'.")

        periode["groupes"] = self._prune_empty_groups(
            periode["groupes"], report, sheet_name)
        return periode

    # ---- classification / extraction ----------------------------------

    def _is_group_header(self, label, ects_raw, has_hours) -> bool:
        if has_hours:
            return False                      # un module porte des heures
        if self._UE_CODE_RE.match(label):
            return True
        if re.match(r"^\s*PBL\b", label, re.I):
            return True
        if re.search(r"\b(modulaire|applications)\b", label, re.I):
            return True
        if not label and self._has_number(ects_raw):
            return True                       # total de groupe sans intitulé
        return False

    def _is_module(self, label, ects_raw, has_hours) -> bool:
        return bool(label) and (has_hours or self._has_number(ects_raw))

    def _group_code(self, label, sem, seq) -> str:
        m = self._UE_CODE_RE.match(label or "")
        if m:
            return re.sub(r"\s+", "", m.group(1)).upper()
        if re.match(r"^\s*PBL\b", label or "", re.I):
            return f"S{sem}_PBL"
        return f"S{sem}_GRP{seq:02d}"

    def _course_code(self, label):
        m = self._COURSE_CODE_RE.match(label or "")
        return m.group(1) if m else None

    @staticmethod
    def _classify_discipline(label) -> str:
        lo = (label or "").lower()
        lang = ("langue", "espagnol", "italien", "français", "francais",
                "language", "intercompréhension", "intercomprehension",
                "prononciation", "laboratoire", "sociétés et cultures",
                "societes et cultures", "structures de la langue",
                "renforcement", "communication", "affaires", "lv3", "teds",
                "specialized lenguage")
        proj = ("pbl", "project", "internship", "thesis", "software", "stage",
                "mémoire", "memoire", "socio-economical")
        if any(k in lo for k in lang):
            return "language_module"
        if any(k in lo for k in proj):
            return "project_module"
        return "management_module"

    @staticmethod
    def _normalize_header(value) -> str:
        """Normalise un en-tête Excel pour une détection robuste."""
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        raw = unicodedata.normalize("NFKD", raw)
        raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
        raw = re.sub(r"\s+", " ", raw)
        return raw

    @classmethod
    def _normalize_generic_ref(cls, value) -> str:
        """Normalise une valeur de la colonne Correspondance générique."""
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        raw = unicodedata.normalize("NFKD", raw)
        raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
        raw = raw.replace("_", "-")
        raw = re.sub(r"\s+", " ", raw)
        return raw.strip()

    @classmethod
    def _resolve_generic_reference(cls, raw, year, report, sheet_name, coord):
        """Convertit la valeur lisible de l'Excel en code module générique.

        Retourne (code, statut). Si la cellule est vide, retourne ("", "")
        pour laisser l'ancienne inférence de langue fonctionner. Si la cellule
        contient une valeur explicite non reliée (ex. "À valider" ou inconnue),
        retourne un statut non vide afin de bloquer l'inférence automatique.
        """
        value = str(raw or "").strip()
        normalized = cls._normalize_generic_ref(value)

        if not normalized:
            return "", ""

        if normalized in _TO_VALIDATE_VALUES:
            return "", "to_validate"

        if normalized in _GENERIC_REF_TO_CODE:
            return _GENERIC_REF_TO_CODE[normalized], "manual"

        if normalized in {"language b", "langue b"}:
            code = cls._infer_generic_language(year, "B")
            if code:
                return code, "manual_language"
            report["ambiguities"].append(
                f"{sheet_name}!{coord} : correspondance '{value}' impossible "
                f"pour l'année {year}."
            )
            return "", "unresolved"

        if normalized in {"language c", "langue c"}:
            code = cls._infer_generic_language(year, "C")
            if code:
                return code, "manual_language"
            report["ambiguities"].append(
                f"{sheet_name}!{coord} : correspondance '{value}' impossible "
                f"pour l'année {year}."
            )
            return "", "unresolved"

        report["ambiguities"].append(
            f"{sheet_name}!{coord} : correspondance générique inconnue '{value}'."
        )
        return "", "unresolved"

    @staticmethod
    def _infer_generic_language(year, channel):
        table = {(1, "B"): "UNITA_M1", (1, "C"): "UNITA_M2",
                 (2, "B"): "UNITA_M3", (2, "C"): "UNITA_M4",
                 (3, "C"): "UNITA_M5"}
        return table.get((year, channel))

    @classmethod
    def _infer_link(cls, year, channel, disc):
        """Inférence prudente générique<->spécifique. Jamais 'exact'."""
        if disc == "language_module":
            code = cls._infer_generic_language(year, channel)
            if code:
                return code, "inferred"
            return "", "to_validate"
        # management/project : pas d'auto-link sans équivalence explicite.
        return "", ""

    @staticmethod
    def _parse_ects(raw) -> float:
        """Valeur déterministe : dernier nombre lisible (\"2 > 3?\"->3.0,
        \"6\"->6.0, sinon 0.0). credits reste toujours un float."""
        if raw is None:
            return 0.0
        if isinstance(raw, (int, float)):
            return float(raw)
        nums = re.findall(r"\d+(?:[.,]\d+)?", str(raw))
        if not nums:
            return 0.0
        return float(nums[-1].replace(",", "."))

    def _parse_hours(self, raw):
        """'7,5h CM + 9h TD' -> {cm,td,tp,projet} + volumes non mappés."""
        res = {"cm": 0.0, "td": 0.0, "tp": 0.0, "projet": 0.0}
        unknown = []
        for part in re.split(r"[+/]", str(raw or "")):
            m = self._HOUR_RE.search(part.strip())
            if not m:
                continue
            val = float(m.group(1).replace(",", "."))
            kind = m.group(2).upper()
            if kind.startswith("CM"):
                res["cm"] += val
            elif kind.startswith("TD"):
                res["td"] += val
            elif kind.startswith("TP"):
                res["tp"] += val
            elif kind.startswith("PROJ"):
                res["projet"] += val
            else:
                unknown.append(f"{val:g}h {kind}")
        return res, unknown

    def _prune_empty_groups(self, groups, report, sheet):
        kept = []
        for g in groups:
            if g.get("kind") == "composite":
                g["sous_groupes"] = [sg for sg in g["sous_groupes"]
                                     if sg["elements"]]
                if g["sous_groupes"]:
                    kept.append(g)
                else:
                    report["ambiguities"].append(
                        f"{sheet} : composite '{g['code']}' vidé (aucun module).")
            elif g["elements"]:
                kept.append(g)
            else:
                report["ambiguities"].append(
                    f"{sheet} : groupe '{g['code']}' sans module -> retiré.")
        return kept

    # ---- petits utilitaires cellule -----------------------------------

    @staticmethod
    def _cell(rows, r, c):
        if c is None:
            return None
        if 0 <= r < len(rows):
            row = rows[r]
            if 0 <= c < len(row):
                return row[c]
        return None

    @staticmethod
    def _has_number(raw) -> bool:
        if raw is None:
            return False
        if isinstance(raw, (int, float)):
            return True
        return bool(re.search(r"\d", str(raw)))

    @staticmethod
    def _col_letter(idx0) -> str:
        idx = idx0 + 1
        out = ""
        while idx:
            idx, rem = divmod(idx - 1, 26)
            out = chr(65 + rem) + out
        return out

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