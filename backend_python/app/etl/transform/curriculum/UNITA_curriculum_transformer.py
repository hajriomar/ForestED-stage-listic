# -*- coding: utf-8 -*-
"""
UNITA_curriculum_transformer.py
===============================
Transformer curriculum UNITA (Joint Bachelor JB_SCRL).

Place dans le pipeline
----------------------
    extract_* -> UNITACurriculumNormalizer -> [ce fichier] -> (loader plus tard)

Rôle
----
Transforme la structure curriculum normalisée (générique ou USMB) vers le
modèle canonique curriculum ForestED (`curriculum_models`) :

    Programme
      └─ PeriodeProgramme (id, numero, ects)
          └─ GroupeElementsPedagogiquesElementaire | ...Composite
              └─ ElementPedagogiqueFormatif (id, nom, type, credits, ...)
                  └─ AcquisApprentissage (id, description)   <- MLO, SANS PLO

Règles validées (docs/UNITA_DATA_REDESIGN_AUDIT.md) :
- le curriculum ne porte AUCUN PLO ni `aligned_plos` : les MLO deviennent
  des `acquis_apprentissage` (id + description) — garde-fou vérifié ici ;
- le transformer ne fait AUCUN merge / upsert : il produit une sortie
  « prête à l'upsert » (clés composites + scope/institution résolus) que
  le loader/service consommera plus tard SANS écraser les autres
  institutions.

Clé d'upsert (portée par la sortie, appliquée par le loader) :
    programme_id + scope + (institution_code | "__GENERIC__")
                 + periode_id + groupe_code + element_id

Sortie : {"canonical": Programme, "flat": [...], "quality_report": {...},
          "upsert": {...}} — même esprit R4 que les autres sources.
"""

import logging

from app.etl.transform.base_transformer import BaseTransformer
from app.models.curriculum_models import (
    Programme,
    PeriodeProgramme,
    GroupeElementsPedagogiquesElementaire,
    GroupeElementsPedagogiquesComposite,
    ElementPedagogiqueFormatif,
    AcquisApprentissage,
    Institution,
)

logger = logging.getLogger(__name__)

_UPSERT_KEY_TEMPLATE = (
    "programme_id + scope + (institution_code|__GENERIC__) "
    "+ periode_id + groupe_code + element_id"
)


class UNITACurriculumTransformer(BaseTransformer):
    """Structure curriculum normalisée UNITA -> Programme canonique."""

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def transform(self, normalized) -> dict:
        if not (isinstance(normalized, dict) and "periodes" in normalized):
            raise TypeError(
                "UNITACurriculumTransformer.transform() attend la sortie du "
                "UNITACurriculumNormalizer ({'periodes': [...], ...}), reçu : "
                f"{type(normalized).__name__}."
            )

        scope = str(normalized.get("scope") or "generic")
        # institution_code = VRAIE institution (None/"" en générique).
        institution_code = normalized.get("institution_code")
        # Clé technique d'upsert (jamais vide) : "__GENERIC__" si pas d'institution.
        upsert_institution_key = str(
            normalized.get("upsert_institution_key")
            or (institution_code if institution_code else "__GENERIC__")
        )
        institutions = list(normalized.get("institutions") or [])
        # Le modèle Programme possède un champ `institutions` : on le renseigne
        # dans le canonical. generic -> [] ; USMB -> [Institution(nom="USMB")].
        programme_institutions = [Institution(nom=str(n)) for n in institutions if n]
        programme_id = str(normalized.get("programme_id") or "JB_SCRL")
        programme_nom = str(normalized.get("programme_nom") or programme_id)

        report = dict(normalized.get("quality_report") or {})
        report.setdefault("warnings", [])
        report.setdefault("errors", [])

        # 1) Construire le Programme canonique.
        periodes = []
        real_periods = 0
        for p in normalized["periodes"]:
            groupes = [self._build_groupe(g, report) for g in p.get("groupes", [])]
            periode = PeriodeProgramme(
                id=p["id"],
                numero=int(p.get("numero", -1)),
                ects=self._as_float(p.get("ects")),
                groupes_elements_pedagogiques=groupes,
            )
            if periode.numero > 0:
                real_periods += 1
            periodes.append(periode)

        programme = Programme(
            id=programme_id,
            nom=programme_nom,
            type=normalized.get("type"),
            niveau=normalized.get("niveau"),
            ects_total=0.0,           # total non asserté au niveau générique
            duree=real_periods,
            periodes=periodes,
            institutions=programme_institutions,
        )

        # 2) Aplatir + construire la sortie prête à l'upsert.
        #    Métadonnées techniques (generic_module_code, match_status,
        #    source_sheet, source_cell) indexées par element_id : portées au
        #    flat/upsert, JAMAIS dans le canonical.
        elem_meta = self._index_elem_meta(normalized)
        flat_rows = self._flatten(
            programme, scope, institution_code, upsert_institution_key, elem_meta)
        upsert = self._build_upsert(
            programme, scope, institution_code, upsert_institution_key,
            programme_id, elem_meta)

        # 3) Traçabilité (le quality_report reste produit par l'ETL).
        credits_sum = sum(
            e["element_credits"] for e in flat_rows_unique_elements(flat_rows)
        )
        report.update({
            "canonical_source": "unita_curriculum",
            "scope": scope,
            "institution_code": institution_code,          # vraie institution (None si générique)
            "upsert_institution_key": upsert_institution_key,
            "institutions": institutions,                  # [] en générique, ["USMB"] pour USMB
            "periode_count": len(programme.periodes),
            "groupe_count": upsert["counts"]["groupes"],
            "element_count": upsert["counts"]["elements"],
            "acquis_count": upsert["counts"]["acquis"],
            "credits_sum_indicative": credits_sum,
            "plo_free": True,
            "merge_done_by_transformer": False,
        })

        logger.info(
            "UNITACurriculumTransformer : %s [scope=%s inst=%s] -> "
            "%d périodes, %d groupes, %d éléments, %d acquis (0 PLO).",
            programme_id, scope, institution_code, len(programme.periodes),
            upsert["counts"]["groupes"], upsert["counts"]["elements"],
            upsert["counts"]["acquis"],
        )

        # Le modèle Programme porte un champ `institutions` : il est renseigné
        # dans le canonical (generic -> [] ; USMB -> [Institution(nom="USMB")]).
        # La liste de noms est aussi exposée au niveau du résultat (métadonnée).
        return {
            "canonical": programme,
            "flat": flat_rows,
            "quality_report": report,
            "upsert": upsert,
            "institutions": institutions,
        }

    # ------------------------------------------------------------------
    # Construction canonique (groupes récursifs, éléments, acquis)
    # ------------------------------------------------------------------

    def _build_groupe(self, g, report):
        if g.get("kind") == "composite":
            sous = [self._build_groupe(sg, report) for sg in g.get("sous_groupes", [])]
            return GroupeElementsPedagogiquesComposite(
                id=g["id"],
                code=g["code"],
                intitule=g["intitule"],
                credits=self._as_float(g.get("credits")),
                type=g.get("type"),
                contrainte=g.get("contrainte"),
                groupes_elements_pedagogiques=sous,
            )
        elements = [self._build_element(e, report) for e in g.get("elements", [])]
        return GroupeElementsPedagogiquesElementaire(
            id=g["id"],
            code=g["code"],
            intitule=g["intitule"],
            credits=self._as_float(g.get("credits")),
            type=g.get("type"),
            contrainte=g.get("contrainte"),
            elements_pedagogiques=elements,
        )

    def _build_element(self, e, report):
        # Acquis = MLO (id + description). JAMAIS de PLO/aligned_plos :
        # le modèle AcquisApprentissage n'a que id + description (extra=forbid),
        # et la normalisation a déjà retiré tout champ PLO.
        acquis = [
            AcquisApprentissage(id=a["id"], description=a["description"])
            for a in e.get("acquis", [])
        ]
        # NB : 'code' de l'élément n'est PAS un champ du modèle (extra=forbid) ;
        # il est porté par l'id (id == code côté UNITA) et par le flat/upsert.
        return ElementPedagogiqueFormatif(
            id=e["id"],
            nom=e.get("nom") or e["id"],
            type=e.get("type"),
            credits=self._as_float(e.get("credits")),
            cm=self._as_float(e.get("cm")),
            td=self._as_float(e.get("td")),
            tp=self._as_float(e.get("tp")),
            projet=self._as_float(e.get("projet")),
            acquis_apprentissage=acquis,
        )

    # ------------------------------------------------------------------
    # Flat (contrat curriculum) + traçabilité upsert
    # ------------------------------------------------------------------

    def _flatten(self, programme, scope, institution_code,
                 upsert_institution_key, elem_meta=None):
        elem_meta = elem_meta or {}
        rows = []
        for periode in programme.periodes:
            for groupe in self._iter_leaf_groups(periode.groupes_elements_pedagogiques):
                for element in getattr(groupe, "elements_pedagogiques", []):
                    acquis_list = element.acquis_apprentissage or [None]
                    for ac in acquis_list:
                        rows.append(self._flat_row(
                            programme, periode, groupe, element, ac,
                            scope, institution_code, upsert_institution_key,
                            elem_meta.get(element.id, {}),
                        ))
        return rows

    @staticmethod
    def _flat_row(programme, periode, groupe, element, ac, scope,
                  institution_code, upsert_institution_key, meta=None):
        meta = meta or {}
        # La clé d'upsert utilise la clé TECHNIQUE (jamais vide) ; la colonne
        # institution_code reflète la VRAIE institution ("" si générique).
        upsert_key = "::".join([
            programme.id, scope, upsert_institution_key,
            periode.id, groupe.code, element.id,
        ])
        return {
            # Programme
            "programme_id": programme.id,
            "programme_nom": programme.nom,
            "programme_type": programme.type,
            "programme_niveau": programme.niveau,
            # Portée / institution (prêt à l'upsert)
            "scope": scope,
            "institution_code": institution_code if institution_code else "",
            # Période
            "periode_id": periode.id,
            "semestre": periode.numero,
            # Groupe
            "groupe_id": groupe.id,
            "groupe_code": groupe.code,
            "groupe_intitule": groupe.intitule,
            "groupe_type": groupe.type,
            "groupe_credits": groupe.credits,
            # Élément
            "element_id": element.id,
            "element_nom": element.nom,
            "element_type": element.type,
            "element_credits": element.credits,
            "volume_total": getattr(element, "volume_total", 0.0),
            "cm": getattr(element, "cm", 0.0),
            "td": getattr(element, "td", 0.0),
            "tp": getattr(element, "tp", 0.0),
            "projet": getattr(element, "projet", 0.0),
            # Acquis (MLO) — jamais de PLO
            "ac_id": ac.id if ac else "",
            "ac_description": ac.description if ac else "",
            # Métadonnées techniques (générique<->spécifique) — JAMAIS canonical
            "generic_module_code": meta.get("generic_module_code", ""),
            "generic_ref_label": meta.get("generic_ref_label", ""),
            "match_status": meta.get("match_status", ""),
            "source_sheet": meta.get("source_sheet", ""),
            "source_cell": meta.get("source_cell", ""),
            # Clé d'upsert (appliquée par le loader, pas ici)
            "upsert_institution_key": upsert_institution_key,
            "upsert_key": upsert_key,
        }

    def _build_upsert(self, programme, scope, institution_code,
                      upsert_institution_key, programme_id, elem_meta=None):
        """Sortie « prête à l'upsert » : une entrée par ÉLÉMENT (unité
        d'upsert), avec sa clé composite. Le transformer ne fusionne rien.

        - institution_code   : VRAIE institution (None si générique) ;
        - upsert_institution_key : composant TECHNIQUE de la clé (jamais vide,
          "__GENERIC__" en générique)."""
        elem_meta = elem_meta or {}
        elements = []
        n_groupes = 0
        n_acquis = 0
        for periode in programme.periodes:
            for groupe in self._iter_leaf_groups(periode.groupes_elements_pedagogiques):
                n_groupes += 1
                for element in getattr(groupe, "elements_pedagogiques", []):
                    n_acquis += len(element.acquis_apprentissage or [])
                    meta = elem_meta.get(element.id, {})
                    elements.append({
                        "programme_id": programme_id,
                        "scope": scope,
                        "institution_code": institution_code,
                        "upsert_institution_key": upsert_institution_key,
                        "periode_id": periode.id,
                        "groupe_code": groupe.code,
                        "element_id": element.id,
                        "generic_module_code": meta.get("generic_module_code", ""),
                        "generic_ref_label": meta.get("generic_ref_label", ""),
                        "match_status": meta.get("match_status", ""),
                        "source_sheet": meta.get("source_sheet", ""),
                        "source_cell": meta.get("source_cell", ""),
                        "upsert_key": "::".join([
                            programme_id, scope, upsert_institution_key,
                            periode.id, groupe.code, element.id,
                        ]),
                    })
        return {
            "key_template": _UPSERT_KEY_TEMPLATE,
            "scope": scope,
            "institution_code": institution_code,
            "upsert_institution_key": upsert_institution_key,
            "merge_strategy": "handled_by_loader",   # explicitement pas ici
            "elements": elements,
            "counts": {
                "groupes": n_groupes,
                "elements": len(elements),
                "acquis": n_acquis,
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _iter_leaf_groups(self, groupes):
        """Aplati les composites : ne renvoie que les groupes élémentaires
        (ceux qui portent des elements_pedagogiques)."""
        for g in groupes:
            sous = getattr(g, "groupes_elements_pedagogiques", None)
            if sous:
                yield from self._iter_leaf_groups(sous)
            else:
                yield g

    @staticmethod
    def _index_elem_meta(normalized):
        """element_id -> métadonnées techniques portées par le normalizer
        (generic_module_code, match_status, source_sheet, source_cell).
        Le générique n'en fournit pas -> défauts vides au flat/upsert."""
        meta = {}

        def walk(groupes):
            for g in (groupes or []):
                walk(g.get("sous_groupes"))
                for e in (g.get("elements") or []):
                    if e.get("id"):
                        meta[e["id"]] = {
                            "generic_module_code": e.get("generic_module_code", ""),
                            "generic_ref_label": e.get("generic_ref_label", ""),
                            "match_status": e.get("match_status", ""),
                            "source_sheet": e.get("source_sheet", ""),
                            "source_cell": e.get("source_cell", ""),
                        }

        for p in (normalized.get("periodes") or []):
            walk(p.get("groupes"))
        return meta

    @staticmethod
    def _as_float(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0


def flat_rows_unique_elements(flat_rows):
    """Déduplique les lignes flat par element_id pour sommer les crédits
    une seule fois par élément (un élément = plusieurs lignes acquis)."""
    seen = {}
    for r in flat_rows:
        seen.setdefault(r["element_id"], r)
    return list(seen.values())