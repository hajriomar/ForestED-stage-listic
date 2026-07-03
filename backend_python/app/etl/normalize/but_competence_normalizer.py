"""
but_competence_normalizer.py
=============================
Normalizer BUT Compétences — couche entre l'Extractor et le Transformer.

Rôle
----
Convertit les données extraites brutes (Excel QLIO ou JSON INFO BUT)
en une liste de records métier homogènes.

Ce module connaît la STRUCTURE des sources BUT.
Il ne connaît pas le méta-modèle ForestED (c'est le rôle du Transformer).

Structure d'un record normalisé (NormalizedRecord)
---------------------------------------------------
{
    "competence_nom"      : str,
    "competence_desc"     : str,
    "parcours"            : str,          # "COMMUN" | "ATN" | "MPBS" | …
    "semestre"            : int | None,
    "niveau"              : int,          # 1 | 2 | 3
    "niveau_description"  : str,
    "composantes"         : list[str],
    "ac_id"               : str,          # prédéfini ou ""
    "ac_description"      : str,
    "ressources"          : list[str],
    "saes"                : list[str],
    "ue"                  : str,
}

Ajouter une source BUT
-----------------------
1. Implémenter une méthode `_normalize_<source>(self, extracted_data)`.
2. Ajouter la clé de détection dans `normalize()`.
Aucune modification du Transformer n'est nécessaire.

Aliases JSON (FIELD_MAP)
------------------------
Chaque concept métier accepte plusieurs noms de champs.
Si un établissement utilise "critical_learning" au lieu de
"apprentissages_critiques", il suffit d'ajouter l'alias dans FIELD_MAP.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ===================================================================== #
#  Aliases de champs JSON (robustesse multi-établissements)              #
# ===================================================================== #

FIELD_MAP: dict[str, list[str]] = {
    # Sections du bundle JSON
    "competences":              ["competences", "competency", "blocs_competences"],
    "composantes_essentielles": ["composantes_essentielles", "essential_components", "composantes"],
    "niveaux_developpement":    ["niveaux_developpement", "development_levels", "levels", "niveaux"],
    "apprentissages_critiques": ["apprentissages_critiques", "critical_learning", "acs", "ac_list"],
    # Champs d'un Apprentissage Critique
    "ac_id":          ["id", "code", "ac_id"],
    "ac_nom":         ["nom", "name", "description", "texte", "libelle"],
    "ac_niveau":      ["niveau", "level", "niv"],
    "ac_competence":  ["nom_competence", "competence", "competence_name", "bloc"],
    # Champs d'une composante essentielle
    "ce_competence":  ["competence", "nom_competence", "bloc"],
    "ce_description": ["description", "formulation", "texte"],
    # Champs d'un niveau de développement
    "niv_competence": ["competence", "nom_competence"],
    "niv_numero":     ["niveau", "level", "niv"],
    "niv_description":["description", "intitule", "texte"],
}


# ===================================================================== #
#  Normalizer BUT Compétences                                             #
# ===================================================================== #

class BUTCompetenceNormalizer:
    """
    Normalizer générique pour les référentiels BUT compétences.

    Détecte la source (Excel QLIO · JSON INFO BUT) depuis file_type
    et produit une liste homogène de records métier.

    Configuration Excel (surcharger pour un autre BUT)
    ---------------------------------------------------
    COL_PARCOURS, COL_UE, COL_COMPETENCE, COL_NIVEAU_DESC,
    COL_COMPOSANTES_ST, COL_COMPOSANTES_END, COL_AC,
    COL_PEDAGOGY_START, ROW_HEADERS, ROW_DATA_START,
    COMMUN_SEMESTERS

    Pour un BUT GMP avec AC en colonne 10 :

        class GMPCompetenceNormalizer(BUTCompetenceNormalizer):
            COL_AC = 10
    """

    # --- Configuration colonnes Excel (0-indexé) ---
    COL_PARCOURS         = 0
    COL_UE               = 1
    COL_COMPETENCE       = 2
    COL_NIVEAU_DESC      = 3
    COL_COMPOSANTES_ST   = 4
    COL_COMPOSANTES_END  = 9
    COL_AC               = 9
    COL_PEDAGOGY_START   = 10

    # --- Configuration lignes Excel ---
    ROW_HEADERS    = 3
    ROW_DATA_START = 6

    # --- Règle métier parcours ---
    COMMUN_SEMESTERS = [1, 2]

    # --- Mots-clés des lignes à ignorer ---
    METADATA_KEYWORDS = [
        "volume horaire", "dont cm", "dont td", "dont tp",
        "heures de projet", "type de b.u.t", "portfolio",
    ]

    # ----------------------------------------------------------------- #

    def normalize(self, extracted_data: dict) -> list[dict]:
        """
        Point d'entrée.  Détecte la source depuis file_type et délègue.

        Args:
            extracted_data: sortie d'un Extractor (avec file_type)

        Returns:
            list[dict] — records normalisés (un par AC)

        Raises:
            ValueError: si file_type n'est pas reconnu
        """
        file_type = extracted_data.get("file_type", "")

        if file_type == "excel":
            records = self._normalize_excel(extracted_data)
        elif file_type == "json":
            records = self._normalize_json(extracted_data.get("content", {}))
        else:
            raise ValueError(
                f"BUTCompetenceNormalizer : file_type '{file_type}' non reconnu. "
                "Valeurs acceptées : 'excel', 'json'."
            )

        # Contrôle qualité
        records = self._quality_check(records)

        logger.info(
            f"BUTCompetenceNormalizer : {len(records)} records normalisés "
            f"(source : {file_type})"
        )
        return records

    # ================================================================= #
    #  Normalisation Excel QLIO                                           #
    # ================================================================= #

    def _normalize_excel(self, extracted_data: dict) -> list[dict]:
        """
        Parcourt les feuilles Excel BUT et produit un record par AC.

        Structure colonnes Excel BUT QLIO :
          col 0   : parcours (cellules fusionnées → propagé)
          col 1   : UE
          col 2   : nom de la compétence
          col 3   : description du niveau
          col 4–8 : composantes essentielles
          col 9   : texte de l'Apprentissage Critique
          col 10+ : marqueurs "x" SAÉ / Ressources
        """
        records: list[dict] = []

        for sheet in extracted_data.get("sheets", []):
            sheet_records = self._process_excel_sheet(sheet)
            records.extend(sheet_records)

        return records

    def _process_excel_sheet(self, sheet: dict) -> list[dict]:
        sheet_name = sheet.get("sheet_name", "")
        rows       = sheet.get("rows", [])

        semestre = self._extract_semestre(sheet_name)
        if semestre == 0:
            logger.debug(f"Feuille ignorée (non reconnue comme semestre) : '{sheet_name}'")
            return []

        headers  = self._get_pedagogy_headers(rows)
        records: list[dict] = []

        # État courant (propagation des cellules fusionnées Excel)
        cur: dict = {
            "parcours":    "",
            "ue":          "",
            "competence":  "",
            "niveau_desc": "",
            "composantes": [],
        }

        for raw_row in rows[self.ROW_DATA_START:]:
            row = self._pad_row(raw_row)

            if self._is_empty_row(row) or self._is_metadata_row(row):
                continue

            # Mise à jour de l'état courant
            for key, col in [
                ("parcours",    self.COL_PARCOURS),
                ("ue",          self.COL_UE),
                ("competence",  self.COL_COMPETENCE),
                ("niveau_desc", self.COL_NIVEAU_DESC),
            ]:
                val = self._clean(row[col])
                if val:
                    cur[key] = val

            composantes = [
                self._clean(v)
                for v in row[self.COL_COMPOSANTES_ST:self.COL_COMPOSANTES_END]
                if self._clean(v)
            ]
            if composantes:
                cur["composantes"] = composantes

            ac_text = self._clean(row[self.COL_AC])

            # Contrôles de qualité inline
            if not ac_text:
                continue
            if ac_text.lower() == "x":
                logger.debug(f"AC ignoré : marqueur 'x' détecté (feuille={sheet_name})")
                continue
            if ac_text.lower().startswith("coefficients"):
                continue
            if not cur["competence"]:
                logger.warning(f"AC sans compétence ignoré (feuille={sheet_name}) : {ac_text[:60]}")
                continue

            records.append({
                "competence_nom":      cur["competence"],
                "competence_desc":     "",
                "parcours":            self._resolve_parcours(cur["parcours"], semestre),
                "semestre":            semestre,
                "niveau":              self._semestre_to_niveau(semestre),
                "niveau_description":  cur["niveau_desc"],
                "composantes":         list(cur["composantes"]),
                "ac_id":               "",
                "ac_description":      ac_text,
                "ressources":          self._extract_ressources(row, headers),
                "saes":                self._extract_saes(row, headers),
                "ue":                  cur["ue"],
            })

        return records

    # ================================================================= #
    #  Normalisation JSON INFO BUT                                        #
    # ================================================================= #

    def _normalize_json(self, content: dict) -> list[dict]:
        """
        Lit le bundle JSON INFO BUT et produit le même format de records.

        Utilise FIELD_MAP pour accepter différents noms de champs
        selon l'établissement ou la version du fichier.
        """
        # Support des deux structures : {"files": {...}} ou directement {...}
        data = content.get("files", content)

        composantes_idx = self._build_composantes_index(data)
        niveau_desc_idx = self._build_niveau_desc_index(data)

        records: list[dict] = []

        for ac in self._get_list(data, FIELD_MAP["apprentissages_critiques"]):
            comp   = self._field(ac, "ac_competence")
            niveau = self._int_field(ac, "ac_niveau")
            texte  = self._field(ac, "ac_nom")

            if not comp or niveau == 0 or not texte:
                logger.debug(f"AC JSON ignoré (données manquantes) : {ac}")
                continue

            records.append({
                "competence_nom":      comp,
                "competence_desc":     "",
                "parcours":            "COMMUN",
                "semestre":            None,
                "niveau":              niveau,
                "niveau_description":  niveau_desc_idx.get((comp, niveau), ""),
                "composantes":         composantes_idx.get(comp, []),
                "ac_id":               self._field(ac, "ac_id"),
                "ac_description":      texte,
                "ressources":          [],
                "saes":                [],
                "ue":                  "",
            })

        return records

    def _build_composantes_index(self, data: dict) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for ce in self._get_list(data, FIELD_MAP["composantes_essentielles"]):
            comp = self._field(ce, "ce_competence")
            desc = self._field(ce, "ce_description")
            if comp and desc:
                index.setdefault(comp, []).append(desc)
        return index

    def _build_niveau_desc_index(self, data: dict) -> dict[tuple, str]:
        index: dict[tuple, str] = {}
        for niv in self._get_list(data, FIELD_MAP["niveaux_developpement"]):
            comp = self._field(niv, "niv_competence")
            num  = self._int_field(niv, "niv_numero")
            desc = self._field(niv, "niv_description")
            if comp and num:
                index[(comp, num)] = desc
        return index

    # ================================================================= #
    #  Contrôle qualité                                                   #
    # ================================================================= #

    def _quality_check(self, records: list[dict]) -> list[dict]:
        """
        Filtre les records invalides et logue les anomalies.
        Retourne uniquement les records exploitables.
        """
        valid: list[dict] = []
        for r in records:
            if not r.get("ac_description"):
                logger.warning("Record ignoré : ac_description vide")
                continue
            if not r.get("competence_nom"):
                logger.warning(f"Record ignoré : competence_nom vide (AC={r.get('ac_description','')[:40]})")
                continue
            if r.get("niveau", 0) == 0:
                logger.warning(f"Record ignoré : niveau=0 (AC={r.get('ac_description','')[:40]})")
                continue
            valid.append(r)

        n_ignored = len(records) - len(valid)
        if n_ignored > 0:
            logger.info(f"Contrôle qualité : {n_ignored} record(s) ignoré(s) sur {len(records)}")

        return valid

    # ================================================================= #
    #  Helpers Excel                                                      #
    # ================================================================= #

    def _resolve_parcours(self, parcours_raw: str, semestre: int) -> str:
        """
        Règle métier BUT standard :
          S1/S2 → COMMUN   (pas de spécialisation en 1re année)
          S3+  vide  → COMMUN
          S3+  non vide → code parcours (ATN · MPBS · MP · PCLG · QPSMI · …)
        Surcharger pour un BUT avec une autre organisation.
        """
        if semestre in self.COMMUN_SEMESTERS:
            return "COMMUN"
        code = self._clean(parcours_raw).upper()
        return code if code else "COMMUN"

    def _semestre_to_niveau(self, semestre: int) -> int:
        if semestre in [1, 2]: return 1
        if semestre in [3, 4]: return 2
        if semestre in [5, 6]: return 3
        return 0

    def _extract_semestre(self, sheet_name: str) -> int:
        """Accepte : "Semestre 5", "S5", "BUT S5", "sem5", "S 5", …"""
        name = sheet_name.strip()
        m = re.search(r"semestre\s*(\d+)", name, re.IGNORECASE)
        if m:
            return int(m.group(1))
        m = re.search(r"\bS\s*(\d)\b", name, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return 0

    def _get_pedagogy_headers(self, rows: list) -> list[str]:
        return [self._clean(v) for v in rows[self.ROW_HEADERS]] if len(rows) > self.ROW_HEADERS else []

    def _extract_ressources(self, row: list, headers: list[str]) -> list[str]:
        return [
            self._clean(headers[i])
            for i in range(self.COL_PEDAGOGY_START, min(len(row), len(headers)))
            if self._clean(row[i]).lower() == "x"
            and bool(re.match(r"^R\d+", self._clean(headers[i]).upper()))
        ]

    def _extract_saes(self, row: list, headers: list[str]) -> list[str]:
        return [
            self._clean(headers[i])
            for i in range(self.COL_PEDAGOGY_START, min(len(row), len(headers)))
            if self._clean(row[i]).lower() == "x"
            and (
                self._clean(headers[i]).upper().startswith("SAE")
                or self._clean(headers[i]).upper().startswith("SAÉ")
            )
        ]

    def _is_metadata_row(self, row: list) -> bool:
        text = " ".join(self._clean(v).lower() for v in row if v is not None)
        return any(kw in text for kw in self.METADATA_KEYWORDS)

    def _is_empty_row(self, row: list) -> bool:
        return all(self._clean(v) == "" for v in row)

    def _pad_row(self, row) -> list:
        row = list(row)
        if len(row) < 10:
            row += [None] * (10 - len(row))
        return row

    # ================================================================= #
    #  Helpers JSON (FIELD_MAP)                                          #
    # ================================================================= #

    def _get_list(self, data: dict, aliases: list[str]) -> list:
        for alias in aliases:
            val = data.get(alias)
            if isinstance(val, list):
                return val
        return []

    def _field(self, obj: dict, key: str) -> str:
        for alias in FIELD_MAP.get(key, []):
            val = obj.get(alias)
            if val is not None:
                return self._clean(str(val))
        return ""

    def _int_field(self, obj: dict, key: str) -> int:
        val = self._field(obj, key)
        try:
            return int(val) if val else 0
        except (ValueError, TypeError):
            return 0

    # ================================================================= #
    #  Utilitaire commun                                                  #
    # ================================================================= #

    def _clean(self, value) -> str:
        if value is None:
            return ""
        return str(value).replace("\n", " ").replace("\xa0", " ").strip()