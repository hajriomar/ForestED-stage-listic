# -*- coding: utf-8 -*-
"""
curriculum_upsert_service.py
============================

Service d'UPSERT curriculum multi-scope / multi-institution.

Objectif :
- garder un seul fichier processed par programme ;
- ne pas écraser le générique quand on importe une institution ;
- ne pas écraser une institution quand une autre institution arrive ;
- écrire le fichier *_processed.json au format canonique Programme.

Règle importante :
    data/processed/... = modèle canonique ForestED
    data/analytics/... = flat, quality, index technique d'upsert

Exemple UNITA :
    processed/curriculum/unita/SCRL_processed.json
        -> Programme canonique strict

    analytics/curriculum/unita/SCRL_upsert_index.json
        -> index technique : scopes, institutions, upsert_key, logs
"""

from __future__ import annotations

import copy
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app.models.curriculum_models import Programme

logger = logging.getLogger(__name__)

_GENERIC_TEXT_VALUES = {"", "__GENERIC__"}


class CurriculumUpsertService:
    """Fusionne plusieurs imports curriculum dans un Programme canonique."""

    DEFAULT_ROOT = os.path.join("data", "processed", "curriculum")

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def default_output_path(self, source_name: str, programme_id: str) -> str:
        """Retourne data/processed/curriculum/<source>/<programme_id>_processed.json."""
        return os.path.join(
            self.DEFAULT_ROOT,
            str(source_name),
            f"{programme_id}_processed.json",
        )

    def upsert_result(
        self,
        result: Dict[str, Any],
        output_path: str,
        programme_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fusionne result["canonical"] dans un fichier processed partagé.

        Le fichier output_path reste TOUJOURS un Programme canonique.
        L'index technique est écrit à côté dans analytics/.
        """
        if not isinstance(result, dict):
            raise TypeError(
                "CurriculumUpsertService.upsert_result attend un dict result."
            )

        if "canonical" not in result or "flat" not in result:
            raise TypeError(
                "CurriculumUpsertService.upsert_result attend une sortie "
                "transformer contenant au minimum 'canonical' et 'flat'."
            )

        incoming = self._canonical_to_dict(result["canonical"])
        source_programme_id = incoming.get("id")

        effective_programme_id = (
            str(programme_key).strip()
            if programme_key
            else str(source_programme_id or "").strip()
        )

        if not effective_programme_id:
            raise ValueError(
                "CurriculumUpsertService : impossible de déterminer l'id "
                "du programme à stocker."
            )

        # La formation du formulaire devient la clé principale de stockage.
        incoming["id"] = effective_programme_id

        if programme_key:
            incoming["nom"] = effective_programme_id
        else:
            incoming["nom"] = incoming.get("nom") or effective_programme_id

        records = self._records_from_result(
            result,
            programme_key=effective_programme_id,
        )

        # Enrichissement canonique avec les institutions réelles.
        self._apply_programme_institutions(incoming, records)
        self._apply_element_institutions(incoming, records)

        existing = self._read_canonical_programme(output_path)

        existing_keys = self._element_natural_keys(existing)
        incoming_keys = self._record_natural_keys(records)

        added = len(incoming_keys - existing_keys)
        updated = len(incoming_keys & existing_keys)

        if existing:
            merged = self._merge_programmes(existing, incoming)
        else:
            merged = incoming

        merged["id"] = effective_programme_id

        if programme_key:
            merged["nom"] = effective_programme_id

        # L'index existant contient les anciennes correspondances
        # institution-specific -> module générique. On le lit AVANT la
        # validation afin de pouvoir recalculer les acquis hérités même si
        # l'ordre d'import est USMB puis générique. Les records du nouvel
        # import écrasent les anciens records de même clé.
        index_path = self._upsert_index_path(output_path)
        index = self._read_upsert_index(index_path)
        all_records = dict(index.get("elements") or {})
        all_records.update(records)

        self._inherit_generic_acquis(
            programme=merged,
            all_records=all_records,
        )

        # Validation stricte : aucun champ technique au top-level.
        validated = Programme.model_validate(merged).model_dump()

        # Écriture du processed canonique.
        self._write_json(validated, output_path)

        # Écriture de l'index technique séparé.
        index.setdefault("elements", {})
        for key, rec in records.items():
            index["elements"][key] = rec

        self._refresh_upsert_index(
            index=index,
            result=result,
            records=records,
            programme_id=effective_programme_id,
            source_programme_id=source_programme_id,
        )

        self._write_json(index, index_path)

        institutions = self._institution_names(
            validated.get("institutions", [])
        )
        scopes = sorted(
            {
                rec.get("scope")
                for rec in index.get("elements", {}).values()
                if rec.get("scope")
            }
        )

        summary = {
            "output_path": str(output_path),
            "upsert_index_path": str(index_path),
            "added": added,
            "updated": updated,
            "total_elements": self._count_elements(validated),
            "scopes": scopes,
            "institutions": institutions,
        }

        logger.info(
            "CurriculumUpsertService : %s -> +%d / ~%d total=%d scopes=%s institutions=%s",
            output_path,
            added,
            updated,
            summary["total_elements"],
            scopes,
            institutions,
        )

        return summary

    # ------------------------------------------------------------------
    # Construction de l'index technique depuis le flat
    # ------------------------------------------------------------------

    @staticmethod
    def _records_from_result(
        result: Dict[str, Any],
        programme_key: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Construit un index technique upsert_key -> record.

        Cet index ne doit PAS devenir le contenu principal du processed.
        Il sert uniquement à l'idempotence, aux scopes, aux institutions
        et à la traçabilité.
        """
        flat = result.get("flat") or []
        upsert_elements = (result.get("upsert") or {}).get("elements") or []

        wanted = {
            item.get("upsert_key")
            for item in upsert_elements
            if item.get("upsert_key")
        }
        wanted = wanted or None

        records: Dict[str, Dict[str, Any]] = {}

        for row in flat:
            original_key = row.get("upsert_key")
            if not original_key:
                continue

            if wanted is not None and original_key not in wanted:
                continue

            source_programme_id = row.get("programme_id")
            effective_programme_id = programme_key or source_programme_id

            scope = row.get("scope") or ""
            institution_key = (
                row.get("upsert_institution_key") or "__GENERIC__"
            )
            periode_id = row.get("periode_id")
            groupe_code = row.get("groupe_code")
            element_id = row.get("element_id")

            key = "::".join(
                [
                    str(effective_programme_id),
                    str(scope),
                    str(institution_key),
                    str(periode_id),
                    str(groupe_code),
                    str(element_id),
                ]
            )

            rec = records.get(key)

            if rec is None:
                rec = {
                    "upsert_key": key,
                    "programme_id": effective_programme_id,
                    "source_programme_id": source_programme_id,
                    "scope": scope,
                    "institution_code": row.get("institution_code", ""),
                    "upsert_institution_key": institution_key,
                    "periode_id": periode_id,
                    "semestre": row.get("semestre"),
                    "groupe_id": row.get("groupe_id"),
                    "groupe_code": groupe_code,
                    "groupe_intitule": row.get("groupe_intitule"),
                    "groupe_type": row.get("groupe_type"),
                    "element_id": element_id,
                    "element_nom": row.get("element_nom"),
                    "element_type": row.get("element_type"),
                    "element_credits": row.get("element_credits"),
                    "cm": row.get("cm"),
                    "td": row.get("td"),
                    "tp": row.get("tp"),
                    "projet": row.get("projet"),
                    "generic_module_code": row.get(
                        "generic_module_code", ""
                    ),
                    "generic_ref_label": row.get("generic_ref_label", ""),
                    "match_status": row.get("match_status", ""),
                    "source_sheet": row.get("source_sheet", ""),
                    "source_cell": row.get("source_cell", ""),
                    "acquis": [],
                }
                records[key] = rec

            ac_id = row.get("ac_id")
            if ac_id:
                acquis = {
                    "id": ac_id,
                    "description": row.get("ac_description", ""),
                }

                if acquis not in rec["acquis"]:
                    rec["acquis"].append(acquis)

        return records

    # ------------------------------------------------------------------
    # Lecture / écriture du Programme canonique
    # ------------------------------------------------------------------

    def _read_canonical_programme(self, output_path: str) -> Dict[str, Any]:
        """
        Lit un Programme canonique existant.

        Si un ancien fichier au mauvais format elements{} existe, il est
        migré en mémoire vers le modèle Programme.
        """
        path = Path(output_path)

        if not path.exists():
            return {}

        with open(path, encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return {}

        # Nouveau format correct.
        if "periodes" in data:
            return Programme.model_validate(data).model_dump()

        # Ancien format technique à migrer.
        if "elements" in data and isinstance(data["elements"], dict):
            migrated = self._programme_from_records(
                records=data["elements"].values(),
                programme_id=data.get("programme_id") or data.get("id"),
                programme_nom=data.get("programme_nom") or data.get("nom"),
                institutions=data.get("institutions") or [],
            )
            return Programme.model_validate(migrated).model_dump()

        return {}

    @staticmethod
    def _write_json(data: Dict[str, Any], output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)

    @staticmethod
    def _canonical_to_dict(canonical: Any) -> Dict[str, Any]:
        if hasattr(canonical, "model_dump"):
            return canonical.model_dump()

        if isinstance(canonical, dict):
            return copy.deepcopy(canonical)

        raise TypeError(
            "CurriculumUpsertService : canonical doit être un modèle "
            "Pydantic ou un dict."
        )

    # ------------------------------------------------------------------
    # Migration ancien format elements{} -> Programme canonique
    # ------------------------------------------------------------------

    def _programme_from_records(
        self,
        records: Iterable[Dict[str, Any]],
        programme_id: Optional[str],
        programme_nom: Optional[str] = None,
        institutions: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        programme_id = str(programme_id or "PROGRAMME")

        programme = {
            "id": programme_id,
            "nom": str(programme_nom or programme_id),
            "type": None,
            "niveau": None,
            "ects_total": 0.0,
            "duree": 0,
            "periodes": [],
            "institutions": self._institution_dicts(institutions or []),
        }

        periode_map: Dict[str, Dict[str, Any]] = {}
        groupe_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for rec in records:
            if not isinstance(rec, dict):
                continue

            periode_id = str(
                rec.get("periode_id")
                or f"S{rec.get('semestre') or 0}"
            )
            numero = self._as_int(rec.get("semestre"), default=-1)

            if periode_id not in periode_map:
                periode = {
                    "id": periode_id,
                    "numero": numero,
                    "ects": 0.0,
                    "groupes_elements_pedagogiques": [],
                }
                periode_map[periode_id] = periode
                programme["periodes"].append(periode)

            periode = periode_map[periode_id]

            groupe_id = str(
                rec.get("groupe_id")
                or rec.get("groupe_code")
                or f"{periode_id}_GROUPE"
            )
            group_key = (periode_id, groupe_id)

            if group_key not in groupe_map:
                groupe = {
                    "id": groupe_id,
                    "code": str(rec.get("groupe_code") or groupe_id),
                    "intitule": str(
                        rec.get("groupe_intitule")
                        or rec.get("groupe_code")
                        or groupe_id
                    ),
                    "credits": 0.0,
                    "type": rec.get("groupe_type"),
                    "contrainte": None,
                    "elements_pedagogiques": [],
                }
                groupe_map[group_key] = groupe
                periode["groupes_elements_pedagogiques"].append(groupe)

            groupe = groupe_map[group_key]

            element_id = rec.get("element_id")
            if not element_id:
                continue

            if not self._element_exists(groupe, element_id):
                groupe["elements_pedagogiques"].append(
                    self._element_from_record(rec)
                )

        programme["periodes"].sort(key=self._period_sort_key)
        programme["duree"] = self._compute_duree(programme)

        return programme

    def _element_from_record(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        institution = rec.get("institution_code")
        institutions = [] if self._is_generic_value(institution) else [institution]

        return {
            "id": str(rec.get("element_id")),
            "nom": str(rec.get("element_nom") or rec.get("element_id")),
            "type": rec.get("element_type"),
            "credits": self._as_float(rec.get("element_credits")),
            "volume_total": 0.0,
            "acquis_apprentissage": self._unique_acquis(
                rec.get("acquis") or []
            ),
            "enseignants": [],
            "institutions": self._institution_dicts(institutions),
            "cm": self._as_float(rec.get("cm")),
            "td": self._as_float(rec.get("td")),
            "tp": self._as_float(rec.get("tp")),
            "projet": self._as_float(rec.get("projet")),
            "ressources": [],
            "activites": [],
            "evaluations": [],
            "acquis_apprentissage_elementaires": [],
        }

    # ------------------------------------------------------------------
    # Fusion Programme / périodes / groupes / éléments
    # ------------------------------------------------------------------

    def _merge_programmes(
        self,
        existing: Dict[str, Any],
        incoming: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = copy.deepcopy(existing)

        merged["id"] = incoming.get("id") or existing.get("id")
        merged["nom"] = incoming.get("nom") or existing.get("nom") or merged["id"]
        merged["type"] = existing.get("type") or incoming.get("type")
        merged["niveau"] = existing.get("niveau") or incoming.get("niveau")

        merged["ects_total"] = max(
            self._as_float(existing.get("ects_total")),
            self._as_float(incoming.get("ects_total")),
        )

        merged["duree"] = max(
            self._as_int(existing.get("duree")),
            self._as_int(incoming.get("duree")),
        )

        merged["institutions"] = self._merge_institutions(
            existing.get("institutions", []),
            incoming.get("institutions", []),
        )

        merged["periodes"] = self._merge_periods(
            existing.get("periodes", []),
            incoming.get("periodes", []),
        )

        merged["duree"] = max(merged["duree"], self._compute_duree(merged))

        return merged

    def _merge_periods(
        self,
        existing_periods: List[Dict[str, Any]],
        incoming_periods: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = copy.deepcopy(existing_periods or [])
        index = {self._period_key(period): i for i, period in enumerate(result)}

        for incoming in incoming_periods or []:
            key = self._period_key(incoming)

            if key not in index:
                index[key] = len(result)
                result.append(copy.deepcopy(incoming))
                continue

            current = result[index[key]]

            if not current.get("numero") and incoming.get("numero"):
                current["numero"] = incoming["numero"]

            current["ects"] = max(
                self._as_float(current.get("ects")),
                self._as_float(incoming.get("ects")),
            )

            current["groupes_elements_pedagogiques"] = self._merge_groups(
                current.get("groupes_elements_pedagogiques", []),
                incoming.get("groupes_elements_pedagogiques", []),
            )

        result.sort(key=self._period_sort_key)
        return result

    def _merge_groups(
        self,
        existing_groups: List[Dict[str, Any]],
        incoming_groups: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = copy.deepcopy(existing_groups or [])
        index = {self._group_key(group): i for i, group in enumerate(result)}

        for incoming in incoming_groups or []:
            key = self._group_key(incoming)

            if key not in index:
                index[key] = len(result)
                result.append(copy.deepcopy(incoming))
                continue

            current = result[index[key]]
            result[index[key]] = self._merge_group(current, incoming)

        result.sort(key=self._group_sort_key)
        return result

    def _merge_group(
        self,
        existing: Dict[str, Any],
        incoming: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = copy.deepcopy(existing)

        for field in ("code", "intitule", "type", "contrainte"):
            if not merged.get(field) and incoming.get(field):
                merged[field] = incoming[field]

        merged["credits"] = max(
            self._as_float(merged.get("credits")),
            self._as_float(incoming.get("credits")),
        )

        if "elements_pedagogiques" in incoming:
            merged.setdefault("elements_pedagogiques", [])
            merged["elements_pedagogiques"] = self._merge_elements(
                merged.get("elements_pedagogiques", []),
                incoming.get("elements_pedagogiques", []),
            )

        if "groupes_elements_pedagogiques" in incoming:
            merged.setdefault("groupes_elements_pedagogiques", [])
            merged["groupes_elements_pedagogiques"] = self._merge_groups(
                merged.get("groupes_elements_pedagogiques", []),
                incoming.get("groupes_elements_pedagogiques", []),
            )

        return merged

    def _merge_elements(
        self,
        existing_elements: List[Dict[str, Any]],
        incoming_elements: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = copy.deepcopy(existing_elements or [])
        index = {
            element.get("id"): i
            for i, element in enumerate(result)
            if element.get("id")
        }

        for incoming in incoming_elements or []:
            element_id = incoming.get("id")

            if not element_id or element_id not in index:
                result.append(copy.deepcopy(incoming))
                if element_id:
                    index[element_id] = len(result) - 1
                continue

            current = result[index[element_id]]
            result[index[element_id]] = self._merge_element(current, incoming)

        result.sort(key=lambda element: str(element.get("id") or ""))
        return result

    def _merge_element(
        self,
        existing: Dict[str, Any],
        incoming: Dict[str, Any],
    ) -> Dict[str, Any]:
        # UPDATE : les données entrantes sont la vérité la plus récente.
        merged = copy.deepcopy(incoming)

        merged["institutions"] = self._merge_institutions(
            existing.get("institutions", []),
            incoming.get("institutions", []),
        )

        merged["acquis_apprentissage"] = self._merge_by_id(
            existing.get("acquis_apprentissage", []),
            incoming.get("acquis_apprentissage", []),
        )

        return merged

    # ------------------------------------------------------------------
    # Enrichissement institutions
    # ------------------------------------------------------------------

    def _apply_programme_institutions(
        self,
        programme: Dict[str, Any],
        records: Dict[str, Dict[str, Any]],
    ) -> None:
        institutions = list(programme.get("institutions", []) or [])

        for rec in records.values():
            institution = rec.get("institution_code")
            if not self._is_generic_value(institution):
                institutions.append(institution)

        programme["institutions"] = self._institution_dicts(institutions)

    def _apply_element_institutions(
        self,
        programme: Dict[str, Any],
        records: Dict[str, Dict[str, Any]],
    ) -> None:
        element_to_institutions: Dict[str, Set[str]] = {}

        for rec in records.values():
            institution = rec.get("institution_code")
            element_id = rec.get("element_id")

            if element_id and not self._is_generic_value(institution):
                element_to_institutions.setdefault(element_id, set()).add(
                    str(institution)
                )

        if not element_to_institutions:
            return

        for _periode, _groupe, element in self._iter_elements(programme):
            element_id = element.get("id")
            institutions = element_to_institutions.get(element_id)

            if not institutions:
                continue

            element["institutions"] = self._merge_institutions(
                element.get("institutions", []),
                self._institution_dicts(sorted(institutions)),
            )

    # ------------------------------------------------------------------
    # Héritage des acquis génériques vers les modules institutionnels
    # ------------------------------------------------------------------

    def _inherit_generic_acquis(
        self,
        programme: Dict[str, Any],
        all_records: Dict[str, Dict[str, Any]],
    ) -> None:
        """Copie les MLO/acquis des modules génériques vers les modules
        institutionnels quand une correspondance générique a été validée.

        Important :
        - aucune relation technique module -> module n'est écrite dans le
          processed ;
        - le processed reste un Programme canonique strict ;
        - la liaison finale passe par les acquis/MLO copiés dans
          `acquis_apprentissage` ;
        - si une correspondance est supprimée dans l'Excel puis réimportée,
          les anciens acquis hérités du module institutionnel sont retirés.
        """
        if not programme or not all_records:
            return

        # Records institutionnels : ce sont eux qui portent
        # generic_module_code depuis le flat/upsert.
        specific_records_by_element: Dict[str, Dict[str, Any]] = {}
        for rec in all_records.values():
            if not isinstance(rec, dict):
                continue

            scope = str(rec.get("scope") or "")
            element_id = str(rec.get("element_id") or "").strip()

            if scope != "institution_specific" or not element_id:
                continue

            # Si le même élément est réimporté, le record récent a déjà écrasé
            # l'ancien dans all_records via sa clé d'upsert.
            specific_records_by_element[element_id] = rec

        if not specific_records_by_element:
            return

        referenced_generic_codes = {
            str(rec.get("generic_module_code") or "").strip()
            for rec in specific_records_by_element.values()
            if str(rec.get("generic_module_code") or "").strip()
        }

        if not referenced_generic_codes:
            # Aucun mapping actif : on nettoie les acquis des modules
            # institutionnels connus, car l'Excel institutionnel ne fournit pas
            # directement de MLO.
            for _periode, _groupe, element in self._iter_elements(programme):
                element_id = str(element.get("id") or "")
                if element_id in specific_records_by_element:
                    element["acquis_apprentissage"] = []
            return

        generic_acquis_by_module: Dict[str, List[Dict[str, Any]]] = {}
        for _periode, _groupe, element in self._iter_elements(programme):
            element_id = str(element.get("id") or "").strip()
            if element_id not in referenced_generic_codes:
                continue

            acquis = self._unique_acquis(element.get("acquis_apprentissage") or [])
            if acquis:
                generic_acquis_by_module[element_id] = copy.deepcopy(acquis)

        for _periode, _groupe, element in self._iter_elements(programme):
            element_id = str(element.get("id") or "").strip()
            rec = specific_records_by_element.get(element_id)

            if not rec:
                continue

            generic_code = str(rec.get("generic_module_code") or "").strip()

            if not generic_code:
                # Mapping retiré ou absent : pas d'acquis hérités.
                element["acquis_apprentissage"] = []
                continue

            inherited = generic_acquis_by_module.get(generic_code)

            if not inherited:
                # Mapping présent mais module générique introuvable ou sans MLO.
                # On évite de garder d'anciens acquis potentiellement obsolètes.
                element["acquis_apprentissage"] = []
                continue

            # Les acquis hérités deviennent la vérité calculée pour ce module
            # institutionnel. Cela évite les doublons et les anciens MLO après
            # changement de correspondance dans l'Excel.
            element["acquis_apprentissage"] = copy.deepcopy(inherited)

    # ------------------------------------------------------------------
    # Index technique séparé
    # ------------------------------------------------------------------

    @staticmethod
    def _upsert_index_path(output_path: str | Path) -> Path:
        """
        L'index technique ne doit pas être dans processed/.

        processed/ = modèle canonique Programme
        analytics/ = index technique, flat, quality
        """
        path = Path(output_path)

        name = path.name
        if name.endswith("_processed.json"):
            name = name.replace("_processed.json", "_upsert_index.json")
        else:
            name = f"{path.stem}_upsert_index.json"

        parts = list(path.parts)

        if "processed" in parts:
            index = parts.index("processed")
            parts[index] = "analytics"
            analytics_path = Path(*parts)
        else:
            analytics_path = path.with_name(name)

        return analytics_path.with_name(name)

    @staticmethod
    def _read_upsert_index(index_path: str | Path) -> Dict[str, Any]:
        path = Path(index_path)

        if not path.exists():
            return {
                "programme_id": None,
                "source_programme_ids": [],
                "scopes": [],
                "institutions": [],
                "elements": {},
                "loads": [],
                "updated_at": None,
            }

        with open(path, encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            data = {}

        data.setdefault("programme_id", None)
        data.setdefault("source_programme_ids", [])
        data.setdefault("scopes", [])
        data.setdefault("institutions", [])
        data.setdefault("elements", {})
        data.setdefault("loads", [])
        data.setdefault("updated_at", None)

        return data

    def _refresh_upsert_index(
        self,
        index: Dict[str, Any],
        result: Dict[str, Any],
        records: Dict[str, Dict[str, Any]],
        programme_id: str,
        source_programme_id: Optional[str],
    ) -> None:
        index["programme_id"] = programme_id

        source_ids = set(index.get("source_programme_ids") or [])
        if source_programme_id:
            source_ids.add(source_programme_id)

        scopes = set(index.get("scopes") or [])
        institutions = set(index.get("institutions") or [])

        for rec in records.values():
            if rec.get("source_programme_id"):
                source_ids.add(rec["source_programme_id"])

            if rec.get("scope"):
                scopes.add(rec["scope"])

            institution = rec.get("institution_code")
            if not self._is_generic_value(institution):
                institutions.add(str(institution))

        now = datetime.now(timezone.utc).isoformat()

        index["source_programme_ids"] = sorted(source_ids)
        index["scopes"] = sorted(scopes)
        index["institutions"] = sorted(institutions)
        index["updated_at"] = now

        flat0 = (result.get("flat") or [{}])[0]
        quality = result.get("quality_report") or {}

        index.setdefault("loads", [])
        index["loads"].append(
            {
                "scope": flat0.get("scope"),
                "institution_code": flat0.get("institution_code", ""),
                "input_kind": quality.get("input_kind"),
                "elements": len(records),
                "source_programme_id": source_programme_id,
                "at": now,
            }
        )

    # ------------------------------------------------------------------
    # Comptages / clés naturelles
    # ------------------------------------------------------------------

    @staticmethod
    def _period_key(period: Dict[str, Any]) -> str:
        return str(period.get("id") or period.get("numero"))

    @staticmethod
    def _group_key(group: Dict[str, Any]) -> str:
        return str(group.get("id") or group.get("code"))

    @staticmethod
    def _period_sort_key(period: Dict[str, Any]) -> Tuple[int, int, str]:
        numero = period.get("numero")

        try:
            numero_int = int(numero)
        except (TypeError, ValueError):
            numero_int = 999

        # Les périodes négatives ou transverses à la fin.
        is_negative = 1 if numero_int < 0 else 0

        return is_negative, numero_int, str(period.get("id") or "")

    @staticmethod
    def _group_sort_key(group: Dict[str, Any]) -> str:
        return str(group.get("code") or group.get("id") or "")

    def _record_natural_keys(
        self,
        records: Dict[str, Dict[str, Any]],
    ) -> Set[Tuple[Any, Any, Any]]:
        return {
            (
                rec.get("periode_id"),
                rec.get("groupe_code"),
                rec.get("element_id"),
            )
            for rec in records.values()
            if rec.get("element_id")
        }

    def _element_natural_keys(
        self,
        programme: Dict[str, Any],
    ) -> Set[Tuple[Any, Any, Any]]:
        if not programme:
            return set()

        keys = set()

        for periode, groupe, element in self._iter_elements(programme):
            keys.add(
                (
                    periode.get("id"),
                    groupe.get("code"),
                    element.get("id"),
                )
            )

        return keys

    def _count_elements(self, programme: Dict[str, Any]) -> int:
        return sum(
            1
            for _periode, _groupe, _element in self._iter_elements(programme)
        )

    def _iter_elements(self, programme: Dict[str, Any]):
        for periode in programme.get("periodes", []) or []:
            groups = periode.get("groupes_elements_pedagogiques", []) or []
            for groupe in self._iter_leaf_groups(groups):
                for element in groupe.get("elements_pedagogiques", []) or []:
                    yield periode, groupe, element

    def _iter_leaf_groups(self, groups: List[Dict[str, Any]]):
        for group in groups or []:
            if "elements_pedagogiques" in group:
                yield group

            sub_groups = group.get("groupes_elements_pedagogiques", []) or []
            for sub_group in sub_groups:
                yield from self._iter_leaf_groups([sub_group])

    # ------------------------------------------------------------------
    # Helpers génériques
    # ------------------------------------------------------------------

    @staticmethod
    def _element_exists(group: Dict[str, Any], element_id: str) -> bool:
        return any(
            element.get("id") == element_id
            for element in group.get("elements_pedagogiques", []) or []
        )

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            if value in ("", None):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_int(value: Any, default: int = 0) -> int:
        try:
            if value in ("", None):
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _is_generic_value(value: Any) -> bool:
        """
        True si la valeur représente le générique, sans institution réelle.

        Important :
        - ne jamais faire `value in set(...)` si value peut être un dict ;
        - cela évite l'erreur unhashable type: 'dict'.
        """
        if value is None:
            return True

        if isinstance(value, str):
            return value.strip() in _GENERIC_TEXT_VALUES

        return False

    def _merge_by_id(
        self,
        existing: List[Dict[str, Any]],
        incoming: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = copy.deepcopy(existing or [])
        index = {
            item.get("id"): i
            for i, item in enumerate(result)
            if item.get("id")
        }

        for item in incoming or []:
            item_id = item.get("id")

            if item_id and item_id in index:
                result[index[item_id]] = copy.deepcopy(item)
            else:
                result.append(copy.deepcopy(item))

        return result

    def _merge_institutions(
        self,
        existing: List[Any],
        incoming: List[Any],
    ) -> List[Dict[str, str]]:
        return self._institution_dicts(
            list(existing or []) + list(incoming or [])
        )

    @staticmethod
    def _institution_dicts(values: Iterable[Any]) -> List[Dict[str, str]]:
        """
        Normalise une liste d'institutions.

        Accepte :
        - "USMB"
        - {"nom": "USMB", "type": "institution"}

        Ignore :
        - None
        - ""
        - "__GENERIC__"
        """
        result: Dict[str, Dict[str, str]] = {}

        for value in values or []:
            if isinstance(value, dict):
                name = str(
                    value.get("nom")
                    or value.get("name")
                    or ""
                ).strip()
                institution_type = str(
                    value.get("type") or "institution"
                ).strip()
            else:
                if CurriculumUpsertService._is_generic_value(value):
                    continue

                name = str(value).strip()
                institution_type = "institution"

            if CurriculumUpsertService._is_generic_value(name):
                continue

            result[name] = {
                "nom": name,
                "type": institution_type or "institution",
            }

        return [result[name] for name in sorted(result)]

    @staticmethod
    def _institution_names(values: Iterable[Any]) -> List[str]:
        """Retourne uniquement les noms d'institutions réelles."""
        names: List[str] = []

        for value in values or []:
            if isinstance(value, dict):
                name = str(
                    value.get("nom")
                    or value.get("name")
                    or ""
                ).strip()
            else:
                name = str(value or "").strip()

            if CurriculumUpsertService._is_generic_value(name):
                continue

            if name not in names:
                names.append(name)

        return sorted(names)

    @staticmethod
    def _unique_acquis(acquis: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
        result: Dict[str, Dict[str, str]] = {}

        for item in acquis or []:
            if not isinstance(item, dict):
                continue

            item_id = item.get("id")
            description = item.get("description")

            if not item_id:
                continue

            result[str(item_id)] = {
                "id": str(item_id),
                "description": str(description or ""),
            }

        return list(result.values())

    @staticmethod
    def _compute_duree(programme: Dict[str, Any]) -> int:
        numeros = []

        for periode in programme.get("periodes", []) or []:
            numero = periode.get("numero")

            if isinstance(numero, int) and numero > 0:
                numeros.append(numero)

        return max(numeros) if numeros else 0