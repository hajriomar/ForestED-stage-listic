# -*- coding: utf-8 -*-
"""
usmb_licence_competence_normalizer.py
======================================
Normalizer Compétences pour les référentiels APC des Licences USMB.

Rôle
----
Convertit l'enveloppe Excel de l'extractor (rows + visible + filled_cells,
voir excel_extractor.py) en records homogènes pour
USMBLicenceCompetenceTransformer. TOUTE l'intelligence Excel est ici :
le transformer ne voit jamais une feuille, une croix ni une couleur.

Gabarit reconnu (détection par MARQUEURS textuels, jamais par positions
fixes — le bloc varie de la ligne 5 à la ligne 14 selon les fichiers) :

    "Titre de la compétence"      -> titre (A2, fusionné)
    "Composantes essentielles"    -> puces "en ..."
    "N° Fiche RNCP" / RNCPxxxxx   -> n° de fiche
    "Acquis d'apprentissage"      -> ANCRE du bloc matrice (colonne AC)
    bande "période n"/"semestre n" (fusionnée) -> semestres
                                    ("période 5 / Privé" -> parcours)
    1-2 lignes d'en-têtes colonnes -> UA (type/code) et EC (code/libellé)
    "Niveau k : ..." (col A, fusionnée) | entier nu (STAPS)
    croix x/X/×/✓  OU  cellule COLORÉE (STAPS) -> lien AC x EC

Sortie
------
    {"records": list[dict], "quality_report": dict}

Record (schéma validé) :
    programme_id, programme_nom, source_name, competence_ordre,
    competence_nom, composantes, rncp, niveau, niveau_description,
    ac_ordre, ac_description, liens[{semestre, ua_type, ua_code,
    ec_code, ec_libelle, parcours}], source_sheet, source_row

Cas particuliers gérés
----------------------
- feuilles cachées                    -> ignorées (raison "feuille cachée") ;
- Règles et exemples / RNCP / Blocs RNCP / Profil du diplômé -> ignorées ;
- STAPS : aucune croix textuelle mais des remplissages dans la zone
  matrice -> les cellules colorées deviennent les liens (auto) ;
- STAPS feuilles "<PARCOURS> L3"      -> parcours + niveau 3 déduits du
  nom de feuille (warning explicite, jamais silencieux) ;
- Droit : bandes "période 5 / Privé"  -> parcours porté par les liens ;
- lignes fantômes (~1000 rows)        -> bornage après N lignes vides ;
- MATH (hors gabarit : pas d'ancre tabulaire ni de bande de périodes)
  -> feuille ignorée ; si AUCUNE feuille exploitable dans le classeur,
  ValueError explicite (=> 422 propre au pipeline, raw nettoyé).

Rien n'est inventé : pas d'ECTS, pas d'heures, pas de compétences déduites.
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration par défaut (surchargeable via source_config)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "sheet_ignore_patterns": [
        r"r[eè]gles",              # Règles et exemples
        r"^rncp\b",                # RNCP
        r"blocs?\s*rncp",          # Blocs RNCP
        r"profil\s+du\s+dipl",     # Profil du diplômé
    ],
    "cross_markers": {"x", "×", "✓", "✔"},   # comparés en minuscules/strip
    "phantom_row_limit": 15,       # lignes vides consécutives avant arrêt
    "max_header_scan_rows": 40,    # zone de recherche des marqueurs
    "use_fill_as_cross": "auto",   # True | False | "auto" (STAPS)
    # tokens retirés du nom de fichier pour déduire le programme
    "filename_stopwords": {
        "referentiel", "ref", "reference", "apc", "competence", "competences",
        "comp", "licence", "usmb", "version", "finale", "vfinale", "derniere",
        "reunion", "copie", "parcours", "janvier", "fevrier", "mars", "avril",
        "mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre",
        "decembre",
    },
}

_BAND_RE = re.compile(r"(?:p[ée]riode|semestre)\s*(\d+)\s*(?:/\s*(.+))?",
                      re.IGNORECASE)
_NIVEAU_RE = re.compile(r"niveau\s*(\d)\s*:?\s*(.*)", re.IGNORECASE | re.DOTALL)
_UA_CODE_RE = re.compile(r"\bUA[A-Z]?\s*\.?\s*(\d{1,3})\b")
_UA_TYPE_RE = re.compile(
    r"\bUA\.?\s*(maj|indiv|transv|applic|fond)|^UA[FIMT]\b|\bFOND\.?\s",
    re.IGNORECASE,
)
_EC_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]{1,}\d{2,}(?:[_-][A-Z0-9]+)*$")
_DISC_CODE_RE = re.compile(r"^[A-Z]{3,6}$")          # CULT, EAUH (Géographie)
_NUMERO_RE = re.compile(r"^\d{2,3}$")                # 101, 202 (LLCER)
_RNCP_RE = re.compile(r"\b(?:RNCP|CNCP)\s*-?\s*(\d{4,})", re.IGNORECASE)
_SHEET_L3_RE = re.compile(r"^(.*\S)\s+L3\s*$", re.IGNORECASE)
_FOOTER_RE = re.compile(r"^(rncp|cncp)\b", re.IGNORECASE)


def _norm(value) -> str:
    """minuscules, sans accents, espaces réduits."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().lower()


def _clean(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _strip_bullet(text) -> str:
    return re.sub(r"^[\s•\-\*·–—]+", "", _clean(text)).strip()


def _slug(text: str, max_len: int = 40) -> str:
    """'Introduction au droit privé' -> 'INTRODUCTION_AU_DROIT_PRIVE'.
    IDENTIQUE au _slug historique du transformer competence : les codes
    générés restent stables (flat inchangé)."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", "_", text.upper()).strip("_")
    return text[:max_len].rstrip("_")


class USMBLicenceCompetenceNormalizer:
    """Normalise les référentiels de compétences Licence USMB (xlsx)."""

    def __init__(self, source_config: dict | None = None):
        self.config = {**DEFAULT_CONFIG, **(source_config or {})}
        self._ignore_res = [re.compile(p, re.IGNORECASE)
                            for p in self.config["sheet_ignore_patterns"]]

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def normalize(self, extracted) -> dict:
        if not (isinstance(extracted, dict)
                and extracted.get("file_type") == "excel"):
            got = (extracted.get("file_type")
                   if isinstance(extracted, dict) else type(extracted).__name__)
            raise ValueError(
                "USMBLicenceCompetenceNormalizer : source usmb_licence = "
                f"fichiers Excel (.xlsx) uniquement — reçu '{got}'."
            )

        file_name = extracted.get("file_name", "")
        programme_id, programme_nom = self._resolve_programme(file_name)

        report = {
            "input_file": file_name,
            "sheets_read": [], "sheets_ignored": [],
            "competences": 0, "niveaux": 0, "acs": 0, "liens_ac_module": 0,
            "ec_columns_detected": 0, "ec_without_code": [],
            "ua_without_code": [], "acs_without_lien": [],
            "semestres_detected": [], "parcours_detected": [],
            "warnings": [], "errors": [],
        }

        records: list[dict] = []
        ordre = 0

        for sheet in extracted.get("sheets", []):
            name = sheet.get("sheet_name", "?")

            if not sheet.get("visible", True):
                report["sheets_ignored"].append(
                    {"sheet": name, "raison": "feuille cachée"})
                continue
            if any(rx.search(_norm(name)) for rx in self._ignore_res):
                report["sheets_ignored"].append(
                    {"sheet": name, "raison": "feuille hors référentiel"})
                continue

            parsed = self._parse_sheet(sheet, report)
            if parsed is None:
                report["sheets_ignored"].append(
                    {"sheet": name, "raison": "hors gabarit (pas d'ancre "
                     "'Acquis d'apprentissage' + bande de périodes)"})
                continue

            ordre += 1
            report["sheets_read"].append(name)
            records.extend(self._to_records(
                parsed, ordre, programme_id, programme_nom))

        if not records:
            raise ValueError(
                f"USMBLicenceCompetenceNormalizer : aucune feuille compétence "
                f"exploitable dans {file_name}. Format hors gabarit USMB — "
                f"cas connu : Référentiel MATH (3 compétences côte à côte, "
                f"sans matrice AC×EC), exclu en v1. Feuilles ignorées : "
                f"{[s['sheet'] for s in report['sheets_ignored']]}"
            )

        self._finalize_report(records, report)
        logger.info(
            "USMBLicenceCompetenceNormalizer : %s -> %d compétences, %d AC, "
            "%d liens (%d warnings).",
            file_name, report["competences"], report["acs"],
            report["liens_ac_module"], len(report["warnings"]),
        )
        return {"records": records, "quality_report": report}

    # ------------------------------------------------------------------
    # Identité programme (nom de fichier — convention upload Phase 6)
    # ------------------------------------------------------------------

    def _resolve_programme(self, file_name: str):
        stem = re.sub(r"\.[^.]+$", "", str(file_name or ""))
        stem = _norm(stem)
        tokens = [t for t in re.split(r"[^a-z0-9]+", stem) if t]
        keep = []
        for t in tokens:
            if t in self.config["filename_stopwords"]:
                continue
            if any(ch.isdigit() for ch in t) and not re.match(r"^l\d[a-z]+$", t):
                continue  # dates/versions ("v2", "2024"...) — garde "l1eg"
            if t.startswith("licence") and len(t) > len("licence"):
                t = t[len("licence"):]  # "licenceic" -> "ic"
            keep.append(t)
        slug = "_".join(keep).upper() or "LICENCE"
        prog_id = f"USMB_{slug}"
        prog_nom = ("Licence " + " ".join(k.upper() if len(k) <= 4
                                          else k.capitalize() for k in keep)
                    if keep else "Licence USMB")
        return prog_id, prog_nom

    # ------------------------------------------------------------------
    # Parsing d'une feuille compétence
    # ------------------------------------------------------------------

    def _parse_sheet(self, sheet: dict, report: dict):
        rows = sheet.get("rows") or []
        name = sheet.get("sheet_name", "?")
        scan = min(len(rows), self.config["max_header_scan_rows"])

        def val(r, c):
            if 0 <= r < len(rows) and rows[r] and 0 <= c < len(rows[r]):
                return rows[r][c]
            return None

        # 1) ANCRE : "Acquis d'apprentissage" / "apprentissages critiques"
        anchor_row = ac_col = None
        for r in range(scan):
            for c, v in enumerate(rows[r] or []):
                n = _norm(v)
                if "acquis d'apprentissage" in n \
                        or "apprentissages critiques" in n \
                        or "apprentisage" in n:  # typo réelle (STAPS)
                    anchor_row, ac_col = r, c
                    break
            if anchor_row is not None:
                break
        if anchor_row is None:
            return None
        if ac_col == 0:
            ac_col = 1  # sécurité : jamais la colonne des niveaux

        # STAPS : l'ancre "Apprentissages critiques" est en B10 mais une
        # mention libre existe plus haut — on prend la ligne qui a AUSSI
        # "niveau" ou "ressources" sur la même ligne si elle existe.
        for r in range(anchor_row, scan):
            row_norm = [_norm(v) for v in (rows[r] or [])]
            if any("apprentissage" in v or "apprentisage" in v
                   for v in row_norm):
                if any(v.startswith("niveau") or v == "ressources"
                       for v in row_norm):
                    anchor_row = r
                    for c, v in enumerate(row_norm):
                        if "apprentissage" in v or "apprentisage" in v:
                            ac_col = c
                            break
                    break

        # 2) BANDE de périodes : fenêtre anchor-2 .. anchor+5 (la bande peut
        #    être AU-DESSUS de l'ancre — AES C3bis — et peut être ÉCLATÉE
        #    sur plusieurs lignes par des fusions mal ancrées — ESET/TRI).
        #    On FUSIONNE les ancres de toutes les lignes candidates.
        band_anchors: dict = {}      # col -> (semestre, parcours)
        band_rows: list = []
        for r in range(max(0, anchor_row - 2),
                       min(anchor_row + 6, len(rows))):
            row_hits = 0
            for c, v in enumerate(rows[r] or []):
                m = _BAND_RE.match(_clean(v))
                if not m:
                    continue
                row_hits += 1
                if c not in band_anchors:      # 1re déclaration gagne
                    parcours = _clean(m.group(2)) or None
                    if parcours:
                        parcours = re.sub(r"[^A-Z0-9]+", "_",
                                          _norm(parcours).upper()).strip("_")
                    band_anchors[c] = (int(m.group(1)), parcours)
            if row_hits:
                band_rows.append(r)
        if not band_anchors:
            return None
        band_row = max(band_rows + [anchor_row])

        width = max((len(rw or []) for rw in rows[:max(scan, band_row + 4)]),
                    default=0)

        # bandes -> (semestre, parcours) par colonne, propagées à droite
        col_band: list = [None] * width
        current = None
        for c in range(ac_col + 1, width):
            if c in band_anchors:
                current = band_anchors[c]
            col_band[c] = current

        # 3) EN-TÊTES colonnes : lignes band_row+1.. jusqu'à la 1re ligne
        #    de données (Niveau en col A ou description AC en colonne AC)
        header_rows = []
        first_data = None
        for r in range(band_row + 1, min(band_row + 6, len(rows))):
            colA = _clean(val(r, 0))
            acv = _strip_bullet(val(r, ac_col))
            if _NIVEAU_RE.match(colA) or re.match(r"^[123]$", colA) or \
                    len(acv) > 15:
                first_data = r
                break
            non_empty = sum(1 for c in range(ac_col + 1, width)
                            if _clean(val(r, c)))
            if non_empty >= 2:
                header_rows.append(r)
        if first_data is None:
            first_data = band_row + 1 + len(header_rows)

        # Récupération des en-têtes de GROUPE fusionnées avec la ligne
        # d'ancre. Cas générique USMB Licence (révélé par AES « Compétence
        # 3 bis ») : la ligne des groupes (UAF/UAI/UAM…) est la MÊME que la
        # ligne d'ancre « Acquis d'apprentissage » ; le scan ci-dessus
        # démarre SOUS l'ancre et perd donc TOUS les ua_type de la feuille
        # (chaque colonne retombe alors sur le bucket « UA » côté
        # transformer). On rattrape ici toute ligne entre l'ancre et
        # band_row qui porte de vraies en-têtes de groupe (tokens UA*) dans
        # les colonnes EC, même si sa colonne A/B porte l'ancre ou une
        # bande de période. Aucune règle spécifique à un programme.
        def _row_carries_group_headers(r):
            for c in range(ac_col + 1, width):
                raw = _clean(val(r, c))
                if not raw:
                    continue
                up = raw.upper()
                if _UA_CODE_RE.search(up) or \
                        (_UA_TYPE_RE.search(raw) and len(raw) < 30):
                    return True
            return False

        for r in range(max(0, min(anchor_row, band_row)), band_row + 1):
            if r not in header_rows and _row_carries_group_headers(r):
                header_rows.append(r)
        header_rows = sorted(set(header_rows))

        columns = self._classify_columns(rows, header_rows, ac_col,
                                         width, col_band, val)
        if not columns:
            return None
        report["ec_columns_detected"] += len(columns)

        # 4) En-tête de feuille : titre / composantes / RNCP / parcours L3
        titre = self._find_titre(rows, anchor_row, name, report, val)
        composantes = self._find_composantes(rows, anchor_row)
        rncp = self._find_rncp(rows, scan)

        sheet_parcours, sheet_niveau = None, None
        m = _SHEET_L3_RE.match(name)
        if m:
            sheet_parcours = re.sub(r"[^A-Z0-9]+", "_",
                                    _norm(m.group(1)).upper()).strip("_")
            sheet_niveau = 3
            report["warnings"].append(
                f"[{name}] parcours '{sheet_parcours}' et niveau 3 déduits "
                f"du nom de feuille '<parcours> L3'.")

        # 5) Corps de matrice (croix textuelles d'abord)
        filled = set(sheet.get("filled_cells") or [])
        crosses_found = 0
        acs = []
        niveau, niveau_desc = sheet_niveau, None
        empty_streak = 0
        r = first_data
        while r < len(rows):
            colA = _clean(val(r, 0))
            if _FOOTER_RE.match(colA):
                break
            mniv = _NIVEAU_RE.match(colA)
            if mniv:
                niveau = int(mniv.group(1))
                niveau_desc = _clean(mniv.group(2)) or None
            elif re.match(r"^[123]$", colA):
                niveau, niveau_desc = int(colA), None

            desc = _strip_bullet(val(r, ac_col))
            if desc and len(desc) > 3 and not _NIVEAU_RE.match(desc):
                marks = [c for c in columns
                         if _norm(val(r, c)) in self.config["cross_markers"]]
                empty_streak = 0
                acs.append({"row": r, "description": desc, "niveau": niveau,
                            "niveau_description": niveau_desc,
                            "mark_cols": marks})
                crosses_found += len(marks)
            else:
                empty_streak += 1
                if empty_streak >= self.config["phantom_row_limit"]:
                    break
            r += 1

        # 6) STAPS : aucune croix textuelle -> liens par cellules COLORÉES
        use_fill = self.config["use_fill_as_cross"]
        if crosses_found == 0 and filled and use_fill in (True, "auto"):
            recolored = 0
            for ac in acs:
                ac["mark_cols"] = [c for c in columns
                                   if self._coord(ac["row"], c) in filled]
                recolored += len(ac["mark_cols"])
            if recolored:
                report["warnings"].append(
                    f"[{name}] aucun 'x' détecté : liens AC×EC lus depuis "
                    f"les cellules COLORÉES ({recolored} liens).")

        if not acs:
            return None

        return {"sheet": name, "titre": titre, "composantes": composantes,
                "rncp": rncp, "parcours": sheet_parcours,
                "columns": columns, "acs": acs}

    # ------------------------------------------------------------------

    @staticmethod
    def _coord(r: int, c: int) -> str:
        """(row, col) 0-indexés -> coordonnée A1 ("D14")."""
        col, letters = c + 1, ""
        while col:
            col, rem = divmod(col - 1, 26)
            letters = chr(65 + rem) + letters
        return f"{letters}{r + 1}"

    def _classify_columns(self, rows, header_rows, ac_col, width,
                          col_band, val) -> dict:
        """Colonne -> {semestre, parcours, ua_type, ua_code, ec_code,
        ec_libelle}. ua_code/ua_type sont propagés à droite (fusions)."""
        columns: dict = {}
        last_ua_code = last_ua_type = None
        for c in range(ac_col + 1, width):
            if col_band[c] is None:
                continue
            info = {"semestre": col_band[c][0], "parcours": col_band[c][1],
                    "ua_type": None, "ua_code": None,
                    "ec_code": None, "ec_libelle": None}
            fresh_ua = False
            for hr in header_rows:
                raw = _clean(val(hr, c))
                if not raw:
                    continue
                up = raw.upper()
                mua = _UA_CODE_RE.search(up)
                if mua and not info["ua_code"]:
                    info["ua_code"] = re.sub(r"[\s.]", "", mua.group(0))
                    fresh_ua = True
                    continue
                if _UA_TYPE_RE.search(raw) and not info["ua_type"] \
                        and len(raw) < 30:
                    info["ua_type"] = raw
                    fresh_ua = True
                    continue
                compact = up.replace(" ", "")
                if (_EC_CODE_RE.match(compact) or _DISC_CODE_RE.match(compact)) \
                        and not info["ec_code"]:
                    info["ec_code"] = compact
                    continue
                if _NUMERO_RE.match(compact):
                    info["ec_libelle"] = info["ec_libelle"] or raw
                    continue
                if not info["ec_libelle"]:
                    info["ec_libelle"] = raw

            # propagation UA (codes/types fusionnés sur plusieurs colonnes EC)
            if fresh_ua:
                last_ua_code, last_ua_type = info["ua_code"], info["ua_type"]
            else:
                info["ua_code"] = info["ua_code"] or last_ua_code
                info["ua_type"] = info["ua_type"] or last_ua_type

            if any(info[k] for k in ("ec_code", "ec_libelle",
                                     "ua_code", "ua_type")):
                columns[c] = info
        return columns

    def _find_titre(self, rows, anchor_row, sheet_name, report, val):
        for r in range(min(anchor_row, 10)):
            for c, v in enumerate(rows[r] or []):
                if "titre de la comp" in _norm(v):
                    for rr in range(r + 1, min(r + 8, anchor_row + 1)):
                        t = _clean(val(rr, c)) or _clean(val(rr, c + 1))
                        if len(t) > 10:
                            return t
        # fallback heuristique (STAPS : pas de marqueur "Titre ...")
        for r in range(min(anchor_row, 8)):
            for c in range(4):
                t = _clean(val(r, c))
                n = _norm(t)
                if len(t) > 25 and not n.startswith(
                        ("en ", "composante", "acquis", "niveau", "titre")):
                    report["warnings"].append(
                        f"[{sheet_name}] titre sans marqueur — heuristique : "
                        f"'{t[:50]}…'")
                    return t
        report["warnings"].append(
            f"[{sheet_name}] titre introuvable — nom de feuille utilisé.")
        return sheet_name

    def _find_composantes(self, rows, anchor_row):
        out, seen = [], set()
        for r in range(1, anchor_row):
            for v in rows[r] or []:
                t = _strip_bullet(v)
                if _norm(t).startswith("en ") and len(t) > 8 and t not in seen:
                    seen.add(t)
                    out.append(t)
        return out

    def _find_rncp(self, rows, scan):
        for r in range(scan):
            for v in rows[r] or []:
                m = _RNCP_RE.search(_clean(v))
                if m:
                    return f"RNCP{m.group(1)}"
        return None

    # ------------------------------------------------------------------
    # Records + rapport
    # ------------------------------------------------------------------

    def _to_records(self, parsed, ordre, programme_id, programme_nom):
        records = []
        ac_ordre = 0
        for ac in parsed["acs"]:
            ac_ordre += 1
            liens = []
            for c in ac["mark_cols"]:
                col = parsed["columns"].get(c)
                if not col:
                    continue
                liens.append({
                    "semestre": col["semestre"],
                    "ua_type": col["ua_type"],
                    "ua_code": col["ua_code"],
                    "ec_code": col["ec_code"],
                    "ec_libelle": col["ec_libelle"],
                    # module_code DÉFINITIF : source de vérité unique,
                    # consommée à l'identique par les transformers
                    # competence (ac.modules) ET curriculum (entités EC).
                    "module_code": self._module_code(col),
                    "parcours": col["parcours"] or parsed["parcours"],
                })
            records.append({
                "programme_id": programme_id,
                "programme_nom": programme_nom,
                "source_name": "usmb_licence",
                "competence_ordre": ordre,
                "competence_nom": parsed["titre"],
                "composantes": parsed["composantes"],
                "rncp": parsed["rncp"],
                "niveau": ac["niveau"],
                "niveau_description": ac["niveau_description"],
                "ac_ordre": ac_ordre,
                "ac_description": ac["description"],
                "liens": liens,
                "parcours": parsed["parcours"],
                "source_sheet": parsed["sheet"],
                "source_row": ac["row"] + 1,
            })
        return records

    @staticmethod
    def _module_code(col):
        """Code module définitif : code EC réel prioritaire, sinon code
        stable généré S<semestre>_<SLUG_LIBELLE> (même règle que le
        transformer competence historique), sinon None (lien inexploitable
        — signalé en aval)."""
        if col["ec_code"]:
            return col["ec_code"]
        if col["ec_libelle"]:
            sem = col["semestre"]
            prefix = f"S{sem}_" if sem else "SX_"
            return prefix + _slug(col["ec_libelle"])
        return None

    def _finalize_report(self, records, report):
        comps, nivs, sems, parcs = set(), set(), set(), set()
        for rec in records:
            comps.add(rec["competence_ordre"])
            if rec["niveau"] is not None:
                nivs.add((rec["competence_ordre"], rec["niveau"]))
            report["acs"] += 1
            if not rec["liens"]:
                report["acs_without_lien"].append(
                    f"{rec['source_sheet']} r{rec['source_row']} : "
                    f"{rec['ac_description'][:60]}")
            for lien in rec["liens"]:
                report["liens_ac_module"] += 1
                if lien["semestre"]:
                    sems.add(lien["semestre"])
                if lien["parcours"]:
                    parcs.add(lien["parcours"])
                if not lien["ec_code"]:
                    lbl = lien["ec_libelle"] or "?"
                    if lbl not in report["ec_without_code"]:
                        report["ec_without_code"].append(lbl)
                if not lien["ua_code"] and not lien["ua_type"]:
                    lbl = lien["ec_libelle"] or lien["ec_code"] or "?"
                    if lbl not in report["ua_without_code"]:
                        report["ua_without_code"].append(lbl)
            if rec["parcours"]:
                parcs.add(rec["parcours"])
            if rec["niveau"] is None:
                msg = (f"[{rec['source_sheet']}] AC sans niveau "
                       f"(r{rec['source_row']}).")
                if msg not in report["warnings"]:
                    report["warnings"].append(msg)
        report["competences"] = len(comps)
        report["niveaux"] = len(nivs)
        report["semestres_detected"] = sorted(sems)
        report["parcours_detected"] = sorted(parcs)