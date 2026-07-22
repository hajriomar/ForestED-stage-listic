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
    GroupeElementsPedagogiquesComposite,
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
# Token de FAMILLE d'UA (UAF/UAI/UAM/UAT) isolé — sert à détecter les
# en-têtes aberrants concaténant deux familles (ex. « UAI UAM »).
_UA_FAMILY_TOKEN_RE = re.compile(r"\bUA[FIMT]\b", re.IGNORECASE)


def _norm_code(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "_", text.upper()).strip("_")


def _strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in text if not unicodedata.combining(c))


def _canonical_group_code(ua_code, ua_type) -> str:
    """Code de groupe STABLE et générique (USMB Licence).

    - Un code EC/UA explicite avec chiffres (autres licences : UAF101…)
      reste prioritaire et normalisé tel quel.
    - Sinon on dérive le code de l'en-tête textuel : FAMILLE (UAF/UAI/UAM/
      UAT) + reste concaténé. Cela FUSIONNE les variantes d'orthographe et
      de casse d'une même unité entre les feuilles d'un même classeur
      (« UAI Eco Entreprise » / « UAI EcoEntreprise » -> UAI_ECOENTREPRISE ;
      « UAF droit » / « UAF Droit » -> UAF_DROIT ; « UAI EcodevLoc » /
      « UAI EcoDevLoc » -> UAI_ECODEVLOC). Aucune table par module : la
      vérité vient de la structure de la source.
    """
    if ua_code:
        return _norm_code(ua_code)
    raw = _strip_accents(str(ua_type or "").strip())
    if not raw:
        return "UA"
    m = re.match(r"^(UA[FIMT]?)\b\s*(.*)$", raw, re.IGNORECASE)
    if not m:
        return _norm_code(raw)
    family = m.group(1).upper()
    rest = re.sub(r"[^A-Za-z0-9]+", "", m.group(2)).upper()
    return f"{family}_{rest}" if rest else family


def _is_aberrant_header(ua_type) -> bool:
    """En-tête concaténant DEUX familles d'UA distinctes (ex. « UAI UAM »,
    fusion mal saisie dans la source). Générique : pas de nom hardcodé."""
    fams = {t.upper() for t in _UA_FAMILY_TOKEN_RE.findall(str(ua_type or ""))}
    return len(fams) >= 2


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
        aberrant_liens = 0
        aberrant_headers: set = set()

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
                    periode, groupes, sem, lien, report)
                if groupe is None:
                    # en-tête aberrant (deux familles) : lien ignoré, le
                    # module reste porté par son groupe valide (dédup).
                    aberrant_liens += 1
                    continue
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
        dropped_empty: list = []
        uai_composites: list = []
        for periode in programme.periodes:
            # 1) supprimer les groupes élémentaires VIDES (ex. en-tête
            #    résiduel, groupe dont tous les EC ont été dédupliqués
            #    ailleurs) — aucun groupe vide ne doit subsister.
            kept = []
            for g in periode.groupes_elements_pedagogiques:
                if g.elements_pedagogiques:
                    kept.append(g)
                else:
                    dropped_empty.append(f"{periode.id}_{g.code}")
            periode.groupes_elements_pedagogiques = kept
            # 2) trier les EC de chaque groupe élémentaire
            for g in periode.groupes_elements_pedagogiques:
                g.elements_pedagogiques.sort(key=lambda e: e.id)
            # 3) RÈGLE UAI (générique USMB Licence) : si le semestre
            #    contient >= 2 groupes UAI, les regrouper sous un composite
            #    « choix d'individualisation ». UAF/UAM/UA restent directs.
            if self._wrap_uai_choice(periode):
                uai_composites.append(periode.id)
            # 4) trier les groupes de tête par code
            periode.groupes_elements_pedagogiques.sort(key=lambda g: g.code)

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
        if aberrant_liens:
            report["warnings"].append(
                f"{aberrant_liens} lien(s) d'en-tête aberrant ignorés.")
        report["dropped_empty_groups"] = dropped_empty
        report["uai_composites"] = uai_composites
        if uai_composites:
            report["warnings"].append(
                "Règle métier USMB : les groupes UAI (individualisation) "
                "d'un semestre sont regroupés sous un composite « choix » "
                f"quand il y en a plusieurs — semestres : {uai_composites}.")

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

    def _get_or_create_groupe(self, periode, groupes, sem, lien, report):
        """UA -> Groupe Elementaire. Le parcours (bandes Droit, feuilles
        L3 STAPS) devient la `contrainte` du groupe — même mécanique que
        les options BUT, lisible par le frontend.

        Le code est CANONIQUE (fusionne les variantes d'orthographe/casse
        d'un même groupe entre feuilles). Un en-tête aberrant (deux
        familles d'UA concaténées, ex. « UAI UAM ») n'est PAS matérialisé
        en groupe : il est signalé au quality_report et son lien ignoré."""
        ua_code = lien.get("ua_code")
        ua_type = lien.get("ua_type")
        parcours = lien.get("parcours")

        if _is_aberrant_header(ua_type):
            report.setdefault("aberrant_headers", [])
            label = f"S{sem} : {ua_type!r}"
            if label not in report["aberrant_headers"]:
                report["aberrant_headers"].append(label)
                report["warnings"].append(
                    f"En-tête de groupe aberrant ignoré (deux familles "
                    f"d'UA concaténées) : {label}. Module rattaché à son "
                    f"groupe valide par ailleurs.")
            return None

        base = _canonical_group_code(ua_code, ua_type)
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

    def _wrap_uai_choice(self, periode) -> bool:
        """Regroupe les groupes UAI d'un semestre sous un composite quand
        il y en a AU MOINS DEUX (règle métier USMB validée : UAI = unité
        d'individualisation / choix). UAF, UAM et UA restent des groupes
        directs, jamais enfants du composite. Un seul UAI -> reste direct
        (pas de composite inutile). Générique, aucune spécificité programme.

        Retourne True si un composite a été créé."""
        groups = periode.groupes_elements_pedagogiques
        uai = [g for g in groups if getattr(g, "type", None) == "UAI"]
        if len(uai) < 2:
            return False
        others = [g for g in groups if getattr(g, "type", None) != "UAI"]
        uai.sort(key=lambda g: g.code)
        composite = GroupeElementsPedagogiquesComposite(
            id=f"S{periode.numero}_UAI_CHOIX",
            code="UAI",
            intitule="UAI \u2014 choix d'individualisation",
            credits=0.0,
            type="UAI",
            contrainte="Choix d'une UAI parmi les groupes proposés",
            groupes_elements_pedagogiques=uai,
        )
        periode.groupes_elements_pedagogiques = others + [composite]
        return True

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

    def _iter_leaf_elements(self, groupe):
        """Yield (groupe_elementaire, element) en descendant les composites."""
        sub = getattr(groupe, "groupes_elements_pedagogiques", None)
        if sub is not None:
            for child in sub:
                yield from self._iter_leaf_elements(child)
        else:
            for element in groupe.elements_pedagogiques:
                yield groupe, element

    def _flatten(self, programme):
        """Une ligne par EC. ac_id/ac_description sont présents mais VIDES :
        les liens AC↔EC sont portés par le domaine competence (validé —
        le contrat R4 exige les clés, pas leur contenu, comme pour les
        éléments sans AC de BUT/Polytech)."""
        rows = []
        # _iter_leaf_elements descend les composites (règle UAI) pour émettre
        # une ligne par EC en portant le groupe ÉLÉMENTAIRE réel (UAI_*).
        for periode in programme.periodes:
            for groupe in periode.groupes_elements_pedagogiques:
                for leaf, element in self._iter_leaf_elements(groupe):
                    rows.append({
                        "programme_id": programme.id,
                        "programme_nom": programme.nom,
                        "programme_type": programme.type,
                        "programme_niveau": programme.niveau,
                        "periode_id": periode.id,
                        "semestre": periode.numero,
                        "ue_id": leaf.id,
                        "ue_code": leaf.code,
                        "ue_intitule": leaf.intitule,
                        "ue_type": leaf.type,
                        "parcours": leaf.contrainte or "COMMUN",
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