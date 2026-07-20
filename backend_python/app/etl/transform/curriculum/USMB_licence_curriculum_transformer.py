# -*- coding: utf-8 -*-
"""
USMB_licence_curriculum_transformer.py
=======================================
Transformer Curriculum "lite" pour les Licences USMB.

Place dans le pipeline
----------------------
    extract_excel -> USMBLicenceCompetenceNormalizer -> [ce fichier] -> Loader
                     (MÊME normalizer que le domaine competence : il extrait
                      déjà semestre / UA / EC / parcours dans les liens)

Principe (validé)
-----------------
Les référentiels USMB contiennent un SQUELETTE curriculaire (bandes de
périodes, en-têtes UA et EC de la matrice AC×EC) mais AUCUNE donnée
quantitative : pas d'ECTS, pas de CM/TD/TP/projet, pas de coefficients.
Ce transformer construit donc un curriculum « lite », strictement conforme
à curriculum_models :

    Programme (Licence, Bac+3, 180 ECTS réglementaires, 3 ans)
      └─ PeriodeProgramme S1..S6           (ects=0.0 — non renseigné)
           └─ GroupeElementsPedagogiquesElementaire  (UA ; parcours en
              contrainte, à la manière des options BUT)
                └─ ElementPedagogiqueFormatif        (EC ; credits=0.0,
                   cm/td/tp/projet=0.0 — non renseignés, signalés)

RIEN n'est inventé : les zéros signifient « absent de la source » et le
quality_report l'affiche explicitement (curriculum_type="lite").

Séparation des domaines (validée)
---------------------------------
Les liens AC↔EC restent portés par le domaine competence
(ApprentissageCritique.modules) ; les éléments construits ici n'embarquent
PAS d'acquis d'apprentissage. La jointure est garantie par le
`module_code` DÉFINITIF calculé par le normalizer (C1) : les ids des
éléments curriculum correspondent exactement aux références des AC —
comme pour BUT et Polytech.

Remplacement futur : le jour où une vraie maquette (export Pégase, ROF/
CDM-fr, Excel scolarité) est disponible pour un programme, son traitement
remplace ce squelette sous le même programme_id — rien à jeter.
"""

import logging
import re
import unicodedata

from app.etl.transform.base_transformer import BaseTransformer
from app.models.curriculum_models import (
    ElementPedagogiqueFormatif,
    GroupeElementsPedagogiquesElementaire,
    PeriodeProgramme,
    Programme,
)

logger = logging.getLogger(__name__)

# Constantes réglementaires d'une Licence (conventions, PAS des données
# de la source — documentées dans le quality_report).
_LICENCE_TYPE = "Licence"
_LICENCE_NIVEAU = "Bac+3"
_LICENCE_ECTS_TOTAL = 180.0
_LICENCE_DUREE = 3

_QUALITY_WARNING = (
    "Squelette curriculaire issu du référentiel de compétences ; "
    "ECTS et volumes horaires absents de la source."
)

_UA_FAMILY_RE = re.compile(r"^UA([A-Z])?", re.IGNORECASE)


def _norm_code(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "_", text.upper()).strip("_")


class USMBLicenceCurriculumTransformer(BaseTransformer):
    """Records normalisés USMB Licence -> Programme curriculum « lite »."""

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def transform(self, normalized) -> dict:
        if not (isinstance(normalized, dict) and "records" in normalized):
            raise TypeError(
                "USMBLicenceCurriculumTransformer.transform() attend la "
                "sortie du normalizer {'records': [...], 'quality_report': "
                f"{{...}}}}, reçu : {type(normalized).__name__}.\n"
                "Vérifier que USMBLicenceCompetenceNormalizer est appelé "
                "en amont (NormalizerFactory, domaine curriculum)."
            )

        records = normalized["records"]
        report = dict(normalized.get("quality_report") or {})
        report.setdefault("warnings", [])
        report.setdefault("errors", [])

        if not records:
            raise ValueError(
                "USMBLicenceCurriculumTransformer : aucun record reçu."
            )

        programme_id = records[0]["programme_id"]
        programme_nom = records[0]["programme_nom"]

        programme = Programme(
            id=programme_id,
            nom=programme_nom,
            type=_LICENCE_TYPE,
            niveau=_LICENCE_NIVEAU,
            ects_total=_LICENCE_ECTS_TOTAL,
            duree=_LICENCE_DUREE,
            periodes=[],
        )

        # (semestre)                     -> PeriodeProgramme
        # (semestre, ua_key, parcours)   -> Groupe Elementaire
        # (semestre, module_code)        -> Element (dédupliqué)
        periodes: dict = {}
        groupes: dict = {}
        elements: dict = {}
        liens_sans_module = 0

        for rec in records:
            for lien in rec["liens"]:
                sem = lien.get("semestre")
                module_code = lien.get("module_code")
                if not sem or not module_code:
                    liens_sans_module += 1
                    continue

                periode = self._get_or_create_periode(
                    programme, periodes, sem)
                groupe = self._get_or_create_groupe(
                    periode, groupes, sem, lien)
                self._get_or_create_element(
                    groupe, elements, sem, module_code,
                    lien.get("ec_libelle"))

        if not elements:
            raise ValueError(
                f"USMBLicenceCurriculumTransformer : aucun EC exploitable "
                f"dans les records de {programme_id} (aucun lien avec "
                f"semestre + module_code)."
            )

        programme.periodes.sort(key=lambda p: p.numero)
        for periode in programme.periodes:
            periode.groupes_elements_pedagogiques.sort(key=lambda g: g.code)
            for groupe in periode.groupes_elements_pedagogiques:
                groupe.elements_pedagogiques.sort(key=lambda e: e.id)

        flat_rows = self._flatten(programme)

        # Rapport qualité "lite" (décisions validées)
        report.update({
            "curriculum_type": "lite",
            "data_origin": "reconstructed_from_competence_matrix",
            "ects_renseignes": False,
            "heures_renseignees": False,
            "periodes": len(programme.periodes),
            "uas": len(groupes),
            "ecs": len(elements),
        })
        if _QUALITY_WARNING not in report["warnings"]:
            report["warnings"].append(_QUALITY_WARNING)
        if liens_sans_module:
            report["warnings"].append(
                f"{liens_sans_module} lien(s) sans semestre ou sans "
                f"module_code ignorés côté curriculum.")

        logger.info(
            "USMBLicenceCurriculumTransformer : %s -> %d périodes, %d UA, "
            "%d EC (curriculum lite, ECTS/heures non renseignés).",
            programme_id, len(programme.periodes), len(groupes),
            len(elements),
        )
        return {"canonical": programme, "flat": flat_rows,
                "quality_report": report}

    # ------------------------------------------------------------------
    # Get-or-create
    # ------------------------------------------------------------------

    def _get_or_create_periode(self, programme, periodes, sem):
        if sem not in periodes:
            periode = PeriodeProgramme(
                id=f"S{sem}", numero=int(sem), ects=0.0,
                groupes_elements_pedagogiques=[])
            periodes[sem] = periode
            programme.periodes.append(periode)
        return periodes[sem]

    def _get_or_create_groupe(self, periode, groupes, sem, lien):
        """UA -> Groupe Elementaire. Le parcours (bandes Droit, feuilles
        L3 STAPS) devient la `contrainte` du groupe — même mécanique que
        les options BUT, lisible par le frontend."""
        ua_code = lien.get("ua_code")
        ua_type = lien.get("ua_type")
        parcours = lien.get("parcours")

        base = _norm_code(ua_code or ua_type or "UA")
        key = (sem, base, parcours)
        if key in groupes:
            return groupes[key]

        code = f"{base}_{parcours}" if parcours else base
        groupe = GroupeElementsPedagogiquesElementaire(
            id=f"S{sem}_{code}",
            code=code,
            intitule=(f"{ua_code or ua_type or 'UA'} — {parcours}"
                      if parcours else (ua_code or ua_type or "UA")),
            credits=0.0,                      # non renseigné (lite)
            type=self._ua_family(ua_code, ua_type),
            contrainte=parcours,
            elements_pedagogiques=[],
        )
        periode.groupes_elements_pedagogiques.append(groupe)
        groupes[key] = groupe
        return groupe

    def _get_or_create_element(self, groupe, elements, sem, module_code,
                               ec_libelle):
        """EC -> ElementPedagogiqueFormatif. id aligné sur le module_code
        du normalizer (jointure avec ac.modules côté competence). Un EC
        peut être coché par plusieurs AC : dédupliqué par (sem, code)."""
        key = (sem, module_code)
        if key in elements:
            return elements[key]

        # les codes GÉNÉRÉS portent déjà leur préfixe S<sem>_
        element_id = (module_code if module_code.startswith(f"S{sem}_")
                      else f"S{sem}_{module_code}")
        element = ElementPedagogiqueFormatif(
            id=element_id,
            nom=ec_libelle or module_code,
            type="EC",
            credits=0.0,                      # non renseigné (lite)
            cm=0.0, td=0.0, tp=0.0, projet=0.0,
            acquis_apprentissage=[],          # liens AC↔EC : domaine
            enseignants=[],                   # competence (séparation)
            ressources=[], activites=[], evaluations=[],
            acquis_apprentissage_elementaires=[],
        )
        groupe.elements_pedagogiques.append(element)
        elements[key] = element
        return element

    @staticmethod
    def _ua_family(ua_code, ua_type):
        """UAF101 -> 'UAF' ; 'UA Transv.' -> 'UAT' ; défaut 'UA'."""
        for value in (ua_code, ua_type):
            if not value:
                continue
            m = _UA_FAMILY_RE.match(str(value).strip())
            if m and m.group(1):
                return f"UA{m.group(1).upper()}"
            v = str(value).lower()
            for word, fam in (("maj", "UAM"), ("fond", "UAF"),
                              ("indiv", "UAI"), ("transv", "UAT"),
                              ("applic", "UAM")):
                if word in v:
                    return fam
        return "UA"

    # ------------------------------------------------------------------
    # Flat (contrat R4, dialecte "ue")
    # ------------------------------------------------------------------

    def _flatten(self, programme):
        """Une ligne par EC. ac_id/ac_description sont présents mais VIDES :
        les liens AC↔EC sont portés par le domaine competence (validé —
        le contrat R4 exige les clés, pas leur contenu, comme pour les
        éléments sans AC de BUT/Polytech)."""
        rows = []
        for periode in programme.periodes:
            for groupe in periode.groupes_elements_pedagogiques:
                for element in groupe.elements_pedagogiques:
                    rows.append({
                        "programme_id": programme.id,
                        "programme_nom": programme.nom,
                        "programme_type": programme.type,
                        "programme_niveau": programme.niveau,
                        "periode_id": periode.id,
                        "semestre": periode.numero,
                        "ue_id": groupe.id,
                        "ue_code": groupe.code,
                        "ue_intitule": groupe.intitule,
                        "ue_type": groupe.type,
                        "parcours": groupe.contrainte or "COMMUN",
                        "element_id": element.id,
                        "element_nom": element.nom,
                        "element_type": element.type,
                        "element_credits": element.credits,
                        "volume_total": element.volume_total,
                        "cm": element.cm,
                        "td": element.td,
                        "tp": element.tp,
                        "projet": element.projet,
                        "ac_id": "",
                        "ac_description": "",
                    })
        return rows