"""
polytech_competence_normalizer.py
==================================
Normalizer Polytech Compétences — couche entre l'Extractor et le Transformer.

Rôle
----
Convertit les exports Polytech (phpMyAdmin JSON) en une liste de rows
au schéma stable que PolytechTransformer sait lire :

    code_competence, libelle_competence, description,
    id_composante_essentielle, libelle_composante_essentielle,
    niveau, libelle_niveau,
    id_apprentissage_critique, libelle_apprentissage,
    code_module (optionnel : lien AC -> module explicite)

Formats détectés (logs explicites)
----------------------------------
1. "ancien"  : rows avec id_apprentissage_critique / id_composante_essentielle
               (ex. IDU_competence_LNM_enseignant.json) -> passés tels quels.
2. "nouveau" : rows avec code_ac / code_ce et jointure maquette
               (code_module, ects, hCM...) (ex. IDU_competence-4.json)
               -> mappés vers le schéma stable ; une ligne par couple
               AC x module, le transformer agrège les modules.

Excel/CSV : enveloppe transmise telle quelle (le transformer les gère).
Rien n'est hardcodé sur un nom de fichier.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


class PolytechCompetenceNormalizer:
    """Normalise les exports compétence Polytech vers un schéma de rows stable."""

    def normalize(self, extracted: dict) -> list | dict:
        # Sources non-JSON (Excel/CSV) : le transformer gère leurs enveloppes.
        if not (isinstance(extracted, dict) and extracted.get("file_type") == "json"):
            logger.info(
                "PolytechCompetenceNormalizer : source non-JSON, "
                "transmission directe au transformer."
            )
            return extracted

        file_name = extracted.get("file_name", "?")
        content = extracted.get("content")

        rows = self._extract_phpmyadmin_rows(content)

        if rows is None:
            # Contenu déjà sous forme de liste de rows plate ?
            if (
                isinstance(content, list)
                and content
                and isinstance(content[0], dict)
                and "code_competence" in content[0]
            ):
                rows = content
            else:
                raise ValueError(
                    f"PolytechCompetenceNormalizer : structure JSON non "
                    f"reconnue dans {file_name} (ni export phpMyAdmin, "
                    f"ni liste de rows)."
                )

        fmt = self._detect_format(rows, file_name)

        if fmt == "nouveau":
            normalized = [self._map_new_row(r) for r in rows if r]
            logger.info(
                "PolytechCompetenceNormalizer : format NOUVEAU détecté "
                "(code_ac/code_ce + maquette) dans %s — %d rows mappées.",
                file_name, len(normalized),
            )
            return normalized

        logger.info(
            "PolytechCompetenceNormalizer : format ANCIEN détecté "
            "(id_apprentissage_critique) dans %s — %d rows transmises.",
            file_name, len(rows),
        )
        return rows

    # ------------------------------------------------------------------
    # Détection
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_phpmyadmin_rows(content) -> list | None:
        """Extrait les rows d'un export phpMyAdmin.

        Structure attendue : liste dont un élément est un dict contenant
        une clé "data" (liste de rows). Retourne None si non conforme.
        """
        if not isinstance(content, list):
            return None

        for element in content:
            if isinstance(element, dict) and isinstance(element.get("data"), list):
                return element["data"]

        return None

    @staticmethod
    def _detect_format(rows: list, file_name: str) -> str:
        first = next((r for r in rows if isinstance(r, dict) and r), None)

        if first is None:
            raise ValueError(
                f"PolytechCompetenceNormalizer : aucune row exploitable "
                f"dans {file_name}."
            )

        keys = set(first.keys())

        if "code_ac" in keys or "code_ce" in keys:
            return "nouveau"

        if "id_apprentissage_critique" in keys:
            return "ancien"

        raise ValueError(
            f"PolytechCompetenceNormalizer : format de rows inconnu dans "
            f"{file_name}. Clés trouvées : {sorted(keys)}"
        )

    # ------------------------------------------------------------------
    # Mapping nouveau format -> schéma stable
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_trailing_id(code: str | None, prefix: str) -> str:
        """COMP_IDU1_N1_AC12 -> "12" (prefix="AC"). Sinon code inchangé."""
        if not code:
            return ""
        match = re.search(rf"{prefix}(\d+)\s*$", str(code))
        return match.group(1) if match else str(code)

    def _map_new_row(self, row: dict) -> dict:
        return {
            "code_competence": row.get("code_competence"),
            "libelle_competence": row.get("libelle_competence"),
            "description": row.get("description"),
            "id_composante_essentielle": self._extract_trailing_id(
                row.get("code_ce"), "CE"
            ),
            "libelle_composante_essentielle": row.get(
                "libelle_composante_essentielle"
            ),
            "niveau": row.get("niveau"),
            "libelle_niveau": row.get("libelle_niveau") or "",
            "id_apprentissage_critique": self._extract_trailing_id(
                row.get("code_ac"), "AC"
            ),
            "libelle_apprentissage": row.get("libelle_apprentissage"),
            # Lien AC -> module explicite (jointure maquette) :
            # une row par couple AC x module, agrégé par le transformer.
            "code_module": (row.get("code_module") or "").strip(),
        }