"""
Transformer curriculum Polytech → méta-modèle générique ForestED.

Mapping lexique Polytech → ForestED :
  Programme             →  Programme
  Semestre              →  PeriodeProgramme
  UniteEnseignement     →  GroupeElementsPedagogiquesElementaire  (type="UE")
  Module (cours/TP/...) →  ElementPedagogiqueFormatif
  Stage                 →  ElementPedagogiqueProfessionnel
                            dans un groupe dédié  (type="STAGE")
  Mobilité / Externe    →  ElementPedagogiqueExterne
  AcquisApprentissage   →  AcquisApprentissage  (sur l'élément)
  Ressource             →  RessourcePedagogique
  Activite              →  ActivitePedagogique
  Evaluation            →  Evaluation
  Contact               →  Enseignant

Notes de design :
  • Polytech n'a pas de parcours optionnels → jamais de Composite.
  • PeriodeProgramme contient directement des Elementaire.
  • Les stages sont regroupés dans un Elementaire dédié par semestre (type="STAGE").
  • programme_id et programme_nom sont résolus depuis file_name (injecté par
    extract_excel) ou source_config — aucun hardcode.
  • field_map configurable pour adapter aux variantes IDU / SNI / MECA / etc.
"""

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.models.curriculum_models import (
    ActivitePedagogique,
    AcquisApprentissage,
    AcquisApprentissageElementaire,
    ElementPedagogiqueExterne,
    ElementPedagogiqueFormatif,
    ElementPedagogiqueProfessionnel,
    Enseignant,
    Evaluation,
    GroupeElementsPedagogiquesElementaire,
    PeriodeProgramme,
    Programme,
    RessourcePedagogique,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes programme Polytech (valables pour toutes les spécialités)
# ---------------------------------------------------------------------------

_DEFAULT_PROGRAMME_TYPE   = "Cycle ingénieur"
_DEFAULT_PROGRAMME_NIVEAU = "Bac+5"
_DEFAULT_ECTS_TOTAL       = 180
_DEFAULT_DUREE            = 3
_DEFAULT_ECTS_SEMESTRE    = 30

# Préfixes des modules transverses Polytech (langues LV2 communes à toutes
# les spécialités : IDU, SNI, MECA, etc.).
# Ces préfixes sont une convention institutionnelle Polytech, pas un hardcode
# lié à une formation particulière.
#
# Règle d'application (dans _resolve_period) :
#   SI préfixe transverse ET semestre ABSENT dans les données source → TRANSVERSE
#   SI préfixe transverse ET semestre PRÉSENT dans les données ("S5") → respecté
#
# Exemple :
#   ALLE101 sans semestre → TRANSVERSE  ✅
#   LANG501 avec semestre="S5"  → S5     ✅  (passe 1 gagne avant la passe 3)
_DEFAULT_TRANSVERSE_PREFIXES = (
    "ALLE", "ESPA", "ITAL", "CHIN", "JAPO", "RUSS",
)

# field_map par défaut : clés JSON connues pour chaque champ sémantique
_DEFAULT_FIELD_MAP: Dict[str, List[str]] = {
    "code":       ["code", "Code", "module_code", "code_module"],
    "nom":        ["nom", "Nom", "titre", "intitule", "name"],
    "semestre":   ["semestre", "Semestre", "periode", "période", "semester"],
    "credits":    ["ects", "ECTS", "credits", "crédits", "credit"],
    "cm":         ["CM", "cm", "cours_magistral"],
    "td":         ["TD", "td", "travaux_diriges"],
    "tp":         ["TP", "tp", "travaux_pratiques"],
    "projet":     ["Projet", "projet", "heures_projet", "project"],
    "objectifs":  ["objectifs", "Objectifs", "acquis", "learning_outcomes",
                   "competences", "description"],
    "contacts":   ["contacts", "enseignants", "responsables", "teachers"],
    "ue_code":    ["ue_code", "code_ue", "UE", "ue", "unite_enseignement"],
    "ue_nom":     ["ue_nom", "intitule_ue", "nom_ue", "ue_intitule"],
    "evaluation": ["evaluation", "évaluation", "modalites_evaluation",
                   "modalites"],
    "ressources": ["ressources", "bibliographie", "supports", "references"],
    "activites":  ["activites", "activités", "activites_pedagogiques"],
    "type":       ["type", "categorie", "catégorie", "category"],
    "source":     ["source", "etablissement", "établissement", "institution"],
    "organisme":  ["organisme", "partenaire", "partner"],
}


# ---------------------------------------------------------------------------
# Transformer
# ---------------------------------------------------------------------------

class PolytechCurriculumTransformer:
    """
    Transformer générique pour les curricula Polytech (toutes spécialités).

    Instanciation via le TransformerFactory (aucun argument obligatoire) :
        transformer = PolytechCurriculumTransformer()

    Avec config spécifique pour une spécialité :
        transformer = PolytechCurriculumTransformer(source_config={
            "programme_id":  "POLYTECH_IDU",
            "programme_nom": "Ingénierie des Données et des Usages",
        })
    """

    def __init__(
        self,
        source_config: Optional[Dict[str, Any]] = None,
        source_file_path: Optional[str] = None,
    ) -> None:
        cfg = source_config or {}

        self._source_file_path = source_file_path

        # Identité programme (peut rester None → résolution automatique)
        self._programme_id:  Optional[str] = cfg.get("programme_id")
        self._programme_nom: Optional[str] = cfg.get("programme_nom")

        # Constantes Polytech (surchargeable via source_config)
        self._programme_type   = cfg.get("programme_type",    _DEFAULT_PROGRAMME_TYPE)
        self._programme_niveau = cfg.get("programme_niveau",  _DEFAULT_PROGRAMME_NIVEAU)
        self._ects_total       = float(cfg.get("ects_total",  _DEFAULT_ECTS_TOTAL))
        self._duree            = int(cfg.get("duree",         _DEFAULT_DUREE))
        self._ects_semestre    = float(cfg.get("ects_par_semestre", _DEFAULT_ECTS_SEMESTRE))

        # Préfixes transverses configurables
        self._transverse_prefixes: Tuple[str, ...] = tuple(
            cfg.get("transverse_prefixes", _DEFAULT_TRANSVERSE_PREFIXES)
        )

        # field_map : fusion défaut + surcharges du source_config
        user_map: Dict[str, List[str]] = cfg.get("field_map", {})
        self._field_map: Dict[str, List[str]] = {
            **_DEFAULT_FIELD_MAP,
            **user_map,
        }

    # ---------------------------------------------------------------------------
    # Point d'entrée public
    # ---------------------------------------------------------------------------

    def transform(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        raw_data : dict issu de extract_excel / extract_json.
            Clés attendues : "fiches" | "modules" | "cours" | "items" | "data"
            + "file_name" (injecté automatiquement par extract_excel)

        Retourne : {"canonical": Programme, "flat": List[dict]}
        """
        programme = self._build_programme(raw_data)
        flat_rows = self._flatten_programme(programme)
        return {"canonical": programme, "flat": flat_rows}

    # ---------------------------------------------------------------------------
    # Construction du Programme canonique
    # ---------------------------------------------------------------------------

    def _build_programme(self, raw_data: Dict[str, Any]) -> Programme:
        programme_id, programme_nom = self._resolve_programme_identity(raw_data)

        programme = Programme(
            id=programme_id,
            nom=programme_nom,
            type=self._programme_type,
            niveau=self._programme_niveau,
            ects_total=self._ects_total,
            duree=self._duree,
            periodes=[],
        )

        periodes_map:  Dict[str, PeriodeProgramme] = {}
        groupes_map:   Dict[Tuple[str, str], GroupeElementsPedagogiquesElementaire] = {}
        stage_groups:  Dict[str, GroupeElementsPedagogiquesElementaire] = {}

        _invalid_codes_warned: set = set()

        for item in self._extract_fiches(raw_data):
            raw_code = self._clean(self._get_first(item, self._field_map["code"]))
            if not raw_code:
                logger.warning("Fiche ignorée : code module absent → %s", item)
                continue

            code = self._normalize_code(raw_code)

            if not self._is_valid_module_code(code):
                if raw_code not in _invalid_codes_warned:
                    logger.warning(
                        "Fiche ignorée : code invalide '%s' (attendu: ≥2 lettres + chiffres)",
                        raw_code,
                    )
                    _invalid_codes_warned.add(raw_code)
                continue
            nom      = self._get_first(item, self._field_map["nom"],
                                       default=f"Module {code}")
            credits  = self._parse_float(
                self._get_first(item, self._field_map["credits"])
            )

            semestre_num, periode_id = self._resolve_period(item, code)
            periode = self._get_or_create_periode(
                programme, periodes_map, periode_id, semestre_num
            )

            element_type = self._detect_element_type(item, code, nom)

            # --- Stage : groupe dédié, pas dans une UE normale ---
            if element_type == "STAGE":
                groupe = self._get_or_create_stage_group(
                    periode, stage_groups, semestre_num, periode_id
                )
            else:
                groupe = self._get_or_create_ue_group(
                    periode, groupes_map, item, code, nom,
                    periode_id, credits
                )

            element = self._build_element(
                item, code, nom, periode_id, credits, element_type
            )

            if not self._element_exists(groupe, element.id):
                groupe.elements_pedagogiques.append(element)
                if groupe.credits == 0.0 and credits > 0.0:
                    groupe.credits = credits

        programme.periodes.sort(key=lambda p: p.numero)
        return programme

    # ---------------------------------------------------------------------------
    # Résolution de l'identité programme
    # ---------------------------------------------------------------------------

    def _resolve_programme_identity(
        self, raw_data: Dict[str, Any]
    ) -> Tuple[str, str]:
        """
        Priorité :
          1. source_config (self._programme_id explicite)
          2. source_file_path ou raw_data["file_name"] (injecté par extract_excel)
          3. fallback générique
        """
        if self._programme_id and self._programme_nom:
            return self._programme_id, self._programme_nom

        # Fallback : certains JSON sources ont déjà un programme_id ou id explicite
        raw_prog_id = raw_data.get("programme_id") or raw_data.get("prog_id")
        if raw_prog_id:
            return str(raw_prog_id), self._programme_nom or str(raw_prog_id)

        file_path = (
            self._source_file_path
            or raw_data.get("file_name", "")
            or raw_data.get("source_file", "")
        )

        if file_path:
            stem  = Path(file_path).stem
            parts = [p for p in re.split(r"[_\-]+", stem) if p]
            if parts:
                prefix = parts[0].upper()
                programme_id  = self._programme_id  or f"POLYTECH_{prefix}"
                programme_nom = self._programme_nom or f"Polytech {prefix}"
                logger.debug("Programme résolu depuis fichier : %s → %s",
                             file_path, programme_id)
                return programme_id, programme_nom

        fallback_id  = self._programme_id  or "POLYTECH_GENERIQUE"
        fallback_nom = self._programme_nom or "Polytech Générique"
        logger.warning(
            "Aucune source pour résoudre le programme_id — fallback '%s'. "
            "Passer file_name dans raw_data ou source_file_path au constructeur.",
            fallback_id,
        )
        return fallback_id, fallback_nom

    # ---------------------------------------------------------------------------
    # Groupes pédagogiques
    # ---------------------------------------------------------------------------

    def _get_or_create_ue_group(
        self,
        periode: PeriodeProgramme,
        groupes_map: Dict[Tuple[str, str], GroupeElementsPedagogiquesElementaire],
        item: Dict[str, Any],
        code: str,
        nom: str,
        periode_id: str,
        credits: float,
    ) -> GroupeElementsPedagogiquesElementaire:
        """
        Crée ou récupère le GroupeElementsPedagogiquesElementaire d'un module.

        Cas 1 — UE explicite dans le JSON :
            Plusieurs modules rattachés au même groupe UE.
        Cas 2 — Pas d'UE dans le JSON :
            Un groupe par module (chaque module est son propre groupe).
        """
        ue_raw = self._get_first(item, self._field_map["ue_code"])
        ue_nom = self._get_first(item, self._field_map["ue_nom"])

        if ue_raw:
            group_code    = self._normalize_code(ue_raw)
            group_id      = self._normalize_code(f"{periode_id}_{group_code}")
            group_intitule = ue_nom or ue_raw
            group_type    = "UE"
        else:
            group_code    = self._normalize_code(f"MODULE_{code}")
            group_id      = self._normalize_code(f"{periode_id}_{group_code}")
            group_intitule = nom
            group_type    = "MODULE"

        key = (periode_id, group_code)
        if key in groupes_map:
            return groupes_map[key]

        groupe = GroupeElementsPedagogiquesElementaire(
            id=group_id,
            code=group_code,
            intitule=group_intitule,
            credits=credits,
            type=group_type,
            contrainte=None,
            elements_pedagogiques=[],
        )
        periode.groupes_elements_pedagogiques.append(groupe)
        groupes_map[key] = groupe
        return groupe

    def _get_or_create_stage_group(
        self,
        periode: PeriodeProgramme,
        stage_groups: Dict[str, GroupeElementsPedagogiquesElementaire],
        semestre_num: int,
        periode_id: str,
    ) -> GroupeElementsPedagogiquesElementaire:
        """
        Groupe dédié aux stages d'une période.
        Les stages sont frères des UE dans la période (comme dans le modèle Polytech).
        """
        group_id = f"{periode_id}_STAGES"

        existing_group = stage_groups.get(group_id)
        if existing_group:
            return existing_group

        groupe = GroupeElementsPedagogiquesElementaire(
            id=group_id,
            code="STAGES",
            intitule="Stages",
            credits=0.0,
            type="STAGE",
            contrainte=None,
            elements_pedagogiques=[],
        )
        periode.groupes_elements_pedagogiques.append(groupe)
        stage_groups[group_id] = groupe
        return groupe

    # ---------------------------------------------------------------------------
    # Éléments pédagogiques
    # ---------------------------------------------------------------------------

    def _build_element(
        self,
        item: Dict[str, Any],
        code: str,
        nom: str,
        periode_id: str,
        credits: float,
        element_type: str,
    ):
        element_id  = self._normalize_code(f"{periode_id}_{code}")
        enseignants = self._extract_enseignants(item, code)
        acquis      = self._extract_acquis(item, code)

        if element_type == "STAGE":
            cm = self._parse_float(self._get_first(item, self._field_map["cm"]))
            td = self._parse_float(self._get_first(item, self._field_map["td"]))
            tp = self._parse_float(self._get_first(item, self._field_map["tp"]))
            pj = self._parse_float(self._get_first(item, self._field_map["projet"]))
            return ElementPedagogiqueProfessionnel(
                id=element_id,
                nom=nom,
                type="STAGE",
                credits=credits,
                duree=cm + td + tp + pj,
                modalite="stage",
                acquis_apprentissage=acquis,
                enseignants=enseignants,
            )

        if element_type == "EXTERNE":
            cm = self._parse_float(self._get_first(item, self._field_map["cm"]))
            td = self._parse_float(self._get_first(item, self._field_map["td"]))
            tp = self._parse_float(self._get_first(item, self._field_map["tp"]))
            pj = self._parse_float(self._get_first(item, self._field_map["projet"]))
            return ElementPedagogiqueExterne(
                id=element_id,
                nom=nom,
                type="EXTERNE",
                credits=credits,
                volume_total=cm + td + tp + pj,
                source=self._get_first(item, self._field_map["source"]),
                organisme=self._get_first(item, self._field_map["organisme"]),
                acquis_apprentissage=acquis,
                enseignants=enseignants,
            )

        # SAE, COURS, TP, TD, PROJET → ElementPedagogiqueFormatif
        return ElementPedagogiqueFormatif(
            id=element_id,
            nom=nom,
            type=element_type,
            credits=credits,
            cm=self._parse_float(self._get_first(item, self._field_map["cm"])),
            td=self._parse_float(self._get_first(item, self._field_map["td"])),
            tp=self._parse_float(self._get_first(item, self._field_map["tp"])),
            projet=self._parse_float(
                self._get_first(item, self._field_map["projet"])
            ),
            acquis_apprentissage=acquis,
            enseignants=enseignants,
            ressources=self._extract_ressources(item, code),
            activites=self._extract_activites(item, code),
            evaluations=self._extract_evaluations(item, code),
            acquis_apprentissage_elementaires=[],
        )

    def _detect_element_type(
        self,
        item: Dict[str, Any],
        code: str,
        nom: str,
    ) -> str:
        """
        Détecte le type d'élément depuis le code, le nom et les champs
        type/categorie du JSON.
        Ordre de priorité : STAGE > EXTERNE > PROJET > TP > TD > COURS

        Cas Polytech : certains stages ont un nom générique
        ("Evolution en entreprise") mais un code préfixé STAG + chiffres.
        On teste donc AUSSI le pattern STAG + chiffres dans le code brut.
        """
        text = " ".join([
            str(code),
            str(nom),
            str(self._get_first(item, self._field_map["type"]) or ""),
        ]).upper()

        code_upper = str(code).upper()

        # STAGE : mot entier dans le texte OU code préfixé STAG + chiffres
        stag_in_code = bool(re.search(r"STAG[0-9]+", code_upper))
        if "STAGE" in text or stag_in_code:
            return "STAGE"
        if "MOBIL" in text or "ECHANGE" in text or "EXTERNE" in text:
            return "EXTERNE"
        if "PROJET" in text:
            return "PROJET"
        if re.search(r"\bTP\b", text):
            return "TP"
        if re.search(r"\bTD\b", text):
            return "TD"
        return "COURS"

    # ---------------------------------------------------------------------------
    # Extraction des sous-éléments
    # ---------------------------------------------------------------------------

    def _extract_acquis(
        self, item: Dict[str, Any], code: str
    ) -> List[AcquisApprentissage]:
        raw = self._get_first(item, self._field_map["objectifs"])
        acquis = []
        for idx, desc in enumerate(self._to_text_list(raw), start=1):
            acquis.append(
                AcquisApprentissage(
                    id=self._normalize_code(f"AC_{code}_{idx}"),
                    description=desc,
                )
            )
        return acquis

    def _extract_enseignants(
        self, item: Dict[str, Any], code: str
    ) -> List[Enseignant]:
        contacts = self._get_first(item, self._field_map["contacts"], default=[])
        if not isinstance(contacts, list):
            contacts = [contacts]

        enseignants: List[Enseignant] = []
        seen: set = set()

        for idx, contact in enumerate(contacts, start=1):
            if isinstance(contact, dict):
                nom_ens   = str(contact.get("nom", "")).strip()
                email     = self._clean_email(contact.get("email"))
                telephone = contact.get("telephone")
            else:
                nom_ens   = str(contact).strip()
                email     = None
                telephone = None

            if not nom_ens and not email:
                continue

            key = email or nom_ens
            if key in seen:
                continue
            seen.add(key)

            enseignants.append(
                Enseignant(
                    id=self._normalize_code(f"ENS_{code}_{idx}"),
                    nom=nom_ens or email or "Inconnu",
                    email=email,
                    telephone=telephone,
                    role="Responsable pédagogique",
                )
            )
        return enseignants

    def _extract_ressources(
        self, item: Dict[str, Any], code: str
    ) -> List[RessourcePedagogique]:
        raw = self._get_first(item, self._field_map["ressources"])
        return [
            RessourcePedagogique(
                id=self._normalize_code(f"RES_{code}_{idx}"),
                type="support",
                titre=titre,
            )
            for idx, titre in enumerate(self._to_text_list(raw), start=1)
        ]

    def _extract_activites(
        self, item: Dict[str, Any], code: str
    ) -> List[ActivitePedagogique]:
        raw = self._get_first(item, self._field_map["activites"])
        return [
            ActivitePedagogique(
                id=self._normalize_code(f"ACT_{code}_{idx}"),
                type="activité pédagogique",
                titre=titre,
            )
            for idx, titre in enumerate(self._to_text_list(raw), start=1)
        ]

    def _extract_evaluations(
        self, item: Dict[str, Any], code: str
    ) -> List[Evaluation]:
        raw = self._get_first(item, self._field_map["evaluation"])
        return [
            Evaluation(
                id=self._normalize_code(f"EVAL_{code}_{idx}"),
                type=label,
                ponderation=None,
            )
            for idx, label in enumerate(self._to_text_list(raw), start=1)
        ]

    # ---------------------------------------------------------------------------
    # Résolution de la période
    # ---------------------------------------------------------------------------

    def _resolve_period(
        self, item: Dict[str, Any], code: str
    ) -> Tuple[int, str]:
        """
        Résolution de la période en 4 passes :

        1. Champ semestre explicite dans les données.
           "TRANSVERSE" / "TRANSVERSAL" → TRANSVERSE.
           Numéro (S5, 5, Semestre 5) → semestre direct.

        2. Préfixe langue Polytech (ALLE, ESPA, ITAL…) sans semestre dans
           les données → TRANSVERSE.
           ALLE101 sans semestre dans les données → TRANSVERSE ✅
           LANG501 avec semestre="S5" dans les données → S5 ✅ (passe 1 gagne)

        3. Inférence depuis le code module.
           IDU301 → S3, LANG602 → S6.
           Convention Polytech : premier chiffre du bloc de 3 = semestre.

        4. Fallback S0 si impossible à déterminer.
        """
        # 1. Champ semestre explicite dans le JSON
        semestre_raw = self._get_first(item, self._field_map["semestre"])
        semestre_num = self._parse_semestre(semestre_raw)

        # TRANSVERSE explicite dans les données
        if semestre_num == -1:
            return -1, "TRANSVERSE"

        # Semestre numérique trouvé dans les données → fin
        if semestre_num is not None:
            return semestre_num, f"S{semestre_num}"

        # 2. Semestre ABSENT dans les données :
        #    préfixe langue Polytech → TRANSVERSE
        if self._is_transverse(code):
            return -1, "TRANSVERSE"

        # 3. Inférence depuis le code (IDU301 → S3, LANG602 → S6)
        semestre_num = self._infer_semestre_from_code(code)
        if semestre_num is not None:
            return semestre_num, f"S{semestre_num}"

        # 4. Fallback S0
        return 0, "S0"

    def _parse_semestre(self, value: Any) -> Optional[int]:
        if not value:
            return None
        text = str(value).upper().strip()
        if text in ("TRANSVERSE", "TRANSVERSAL"):
            return -1
        match = re.search(r"(\d+)", text)
        return int(match.group(1)) if match else None

    def _infer_semestre_from_code(self, code: str) -> Optional[int]:
        """
        Déduit le semestre depuis le code module Polytech.
        Convention : premier bloc de 3 chiffres → premier chiffre = semestre.
        Ex: IDU301 → 3, IDU101 → 1, IDU001 → 10 (S10 = dernière année)
        """
        match = re.search(r"(\d{3})", code)
        if not match:
            return None
        first = match.group(1)[0]
        return 10 if first == "0" else int(first)

    def _is_transverse(self, code: str) -> bool:
        """
        Retourne True si le code commence par un préfixe langue Polytech.
        N'est appelé que quand le champ semestre est ABSENT des données source —
        donc LANG501 avec semestre="S5" dans les données ne passe jamais ici.

        La liste peut être surchargée via source_config["force_transverse_codes"].
        """
        if not self._transverse_prefixes:
            return False
        code_upper = self._normalize_code(code)
        return any(code_upper.startswith(p) for p in self._transverse_prefixes)

    # ---------------------------------------------------------------------------
    # Aplatissement pour le dashboard
    # ---------------------------------------------------------------------------

    def _flatten_programme(self, programme: Programme) -> List[Dict[str, Any]]:
        """
        Une ligne par lien Élément ↔ AC.
        Si un élément n'a aucun AC, une ligne est émise avec ac vides.
        Gère tous les types d'éléments via getattr (robuste).
        """
        rows: List[Dict[str, Any]] = []

        for periode in programme.periodes:
            for groupe in periode.groupes_elements_pedagogiques:
                for element in groupe.elements_pedagogiques:
                    acquis = element.acquis_apprentissage or []
                    if acquis:
                        for ac in acquis:
                            rows.append(
                                self._build_flat_row(
                                    programme, periode, groupe, element, ac
                                )
                            )
                    else:
                        rows.append(
                            self._build_flat_row(
                                programme, periode, groupe, element, None
                            )
                        )
        return rows

    def _build_flat_row(
        self,
        programme: Programme,
        periode: PeriodeProgramme,
        groupe: GroupeElementsPedagogiquesElementaire,
        element,
        ac: Optional[AcquisApprentissage],
    ) -> Dict[str, Any]:
        enseignants_str = ", ".join(
            ens.nom for ens in (element.enseignants or [])
        )
        return {
            # Programme
            "programme_id":     programme.id,
            "programme_nom":    programme.nom,
            "programme_type":   programme.type,
            "programme_niveau": programme.niveau,
            # Période
            "periode_id":       periode.id,
            "semestre":         periode.numero,
            # Groupe (UE / MODULE / STAGE)
            "groupe_id":        groupe.id,
            "groupe_code":      groupe.code,
            "groupe_intitule":  groupe.intitule,
            "groupe_type":      groupe.type,
            "groupe_credits":   groupe.credits,
            # Élément pédagogique
            "element_id":       element.id,
            "element_nom":      element.nom,
            "element_type":     element.type,
            "element_credits":  element.credits,
            "volume_total":     getattr(element, "volume_total",  0.0),
            "cm":               getattr(element, "cm",            0.0),
            "td":               getattr(element, "td",            0.0),
            "tp":               getattr(element, "tp",            0.0),
            "projet":           getattr(element, "projet",        0.0),
            "duree":            getattr(element, "duree",         0.0),
            "enseignants":      enseignants_str,
            # Acquis d'Apprentissage
            "ac_id":            ac.id          if ac else "",
            "ac_description":   ac.description if ac else "",
        }

    # ---------------------------------------------------------------------------
    # Helpers : périodes
    # ---------------------------------------------------------------------------

    def _get_or_create_periode(
        self,
        programme: Programme,
        periodes_map: Dict[str, PeriodeProgramme],
        periode_id: str,
        numero: int,
    ) -> PeriodeProgramme:
        if periode_id not in periodes_map:
            periode = PeriodeProgramme(
                id=periode_id,
                numero=numero,
                ects=self._ects_semestre if numero > 0 else 0.0,
                groupes_elements_pedagogiques=[],
            )
            periodes_map[periode_id] = periode
            programme.periodes.append(periode)
        return periodes_map[periode_id]

    # ---------------------------------------------------------------------------
    # Helpers : extraction JSON
    # ---------------------------------------------------------------------------

    def _extract_fiches(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if isinstance(data, list):
            return data
        for key in ("fiches", "modules", "cours", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        logger.warning("Aucune liste de fiches trouvée dans la source")
        return []

    def _get_first(
        self,
        item: Dict[str, Any],
        keys: List[str],
        default: Any = None,
    ) -> Any:
        for key in keys:
            if key in item and item[key] not in (None, ""):
                return item[key]
        return default

    def _to_text_list(self, value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, list):
            result = []
            for v in value:
                text = (
                    v.get("description") or v.get("titre") or v.get("nom") or ""
                    if isinstance(v, dict) else str(v)
                ).strip()
                if text:
                    result.append(text)
            return result
        text = str(value).strip()
        if not text:
            return []
        parts = re.split(r"\n+|(?:^|\n)\s*[-•]\s*", text)
        return [p.strip(" -\t\r\n") for p in parts if p.strip(" -\t\r\n")]

    def _element_exists(
        self,
        groupe: GroupeElementsPedagogiquesElementaire,
        element_id: str,
    ) -> bool:
        return any(e.id == element_id for e in groupe.elements_pedagogiques)

    # ---------------------------------------------------------------------------
    # Helpers : normalisation
    # ---------------------------------------------------------------------------

    def _is_valid_module_code(self, code: str) -> bool:
        """
        Valide qu'un code module Polytech est bien formé.
        Convention : au moins 2 lettres consécutives + au moins 1 chiffre.
        Exemples valides  : IDU301, MATH500, LANG601, STAG501, SHES505
        Exemples invalides : "74", "Annecy-le-Vieux", "", "MODULE"
        """
        return bool(re.search(r"[A-Z]{2,}[0-9]+", code.upper()))

    def _normalize_code(self, value: Any) -> str:
        text = str(value or "").upper().strip()
        text = text.replace("Œ", "OE").replace("Æ", "AE")
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = re.sub(r"[^A-Z0-9]+", "_", text)
        text = re.sub(r"_+", "_", text)
        return text.strip("_")

    def _clean(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).replace("\n", " ").replace("\xa0", " ").strip()

    def _parse_float(self, value: Any) -> float:
        v = self._clean(value).replace("h", "").replace("H", "").replace(",", ".")
        v = re.sub(r"[^0-9.]", "", v)
        try:
            return float(v) if v else 0.0
        except ValueError:
            return 0.0

    def _clean_email(self, value: Any) -> Optional[str]:
        if not value:
            return None
        email = str(value).strip()
        if not email:
            return None
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return None
        return email