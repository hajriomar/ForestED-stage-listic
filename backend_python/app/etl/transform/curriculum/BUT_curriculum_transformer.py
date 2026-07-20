"""
Transformer générique BUT → Méta-modèle ForestED.

Mapping lexique BUT → ForestED :
  ProgrammeBUT          →  Programme
  Parcours              →  contrainte sur GroupeElementsPedagogiquesElementaire
  Semestre              →  PeriodeProgramme
  UniteEnseignement     →  GroupeElementsPedagogiquesComposite
    (1 parcours)              └── GroupeElementsPedagogiquesElementaire (fils unique)
    (N parcours)              └── N × GroupeElementsPedagogiquesElementaire
  SAE / Ressource       →  ElementPedagogiqueFormatif
  Portfolio             →  ElementPedagogiqueFormatif  (type="PORTFOLIO")
  Stage                 →  ElementPedagogiqueProfessionnel
  AcquisApprentissage   →  AcquisApprentissage  (attaché à chaque élément)

Design :
  • BUTCurriculumTransformer — transformer générique pour tous les programmes
    BUT (QLIO, INFO, GEA…). Aucun code programme ni code parcours n'est
    hardcodé : l'identité du programme est résolue automatiquement depuis le
    nom du fichier source (voir _resolve_programme_identity), PAS via une
    classe de configuration.

  • Signature réelle : __init__(source_file_path=None).
    Il n'existe PAS de BUTCurriculumConfig, PAS de paramètre config=,
    PAS de sous-classe QLIOCurriculumTransformer.

  • Le layout Excel (positions de colonnes et de lignes) est SPÉCIFIQUE au
    format « Annexe » national BUT. Il est centralisé dans
    _get_column_layout() : c'est le seul point à surcharger (par
    sous-classe) si un programme BUT arrivait avec un layout différent.

  • Détection automatique :
      - codes parcours  → valeurs courtes MAJ en col 0 détectées à l'exécution
      - début des données → première ligne avec "UE X.X" en col 1
      - layout colonnes  → surchargeable via _get_column_layout()

  • NOUVELLE SOURCE (UNITA, autre établissement…) : ne PAS copier ce
    transformer. Ce fichier parse un layout Excel BUT précis. Si le format
    d'entrée est différent, créer un Normalizer dédié (app/etl/normalize/)
    qui produit des records homogènes, plus un Transformer sans connaissance
    du format — sur le modèle du couple BUTCompetenceNormalizer /
    BUTCompetenceTransformer — puis les enregistrer dans les factories.

  • IDs stables :
      - Élément  : S{sem}_{element_code}            (sans parcours)
      - AC       : AC_S{sem}_{ue_code}_{elem_code}_{slug_description}
      - Option   : {ue_code}_{parcours}
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.curriculum_models import (
    AcquisApprentissage,
    ElementPedagogiqueFormatif,
    ElementPedagogiqueProfessionnel,
    GroupeElementsPedagogiquesComposite,
    GroupeElementsPedagogiquesElementaire,
    PeriodeProgramme,
    Programme,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structures de parsing internes
# ---------------------------------------------------------------------------

class _ColumnLayout:
    """
    Décrit le positionnement des colonnes fixes d'une feuille BUT.
    Peut être surchargé pour d'autres formations.
    """
    __slots__ = (
        "col_parcours",
        "col_ue",
        "col_ac",
        "header_row",
        "data_start_row",
        "element_start_col",
    )

    def __init__(
        self,
        col_parcours: int = 0,
        col_ue: int = 1,
        col_ac: int = 9,
        header_row: int = 3,
        data_start_row: int = 6,
        element_start_col: int = 10,
    ):
        self.col_parcours = col_parcours
        self.col_ue = col_ue
        self.col_ac = col_ac
        self.header_row = header_row
        self.data_start_row = data_start_row
        self.element_start_col = element_start_col


class _ElementMeta:
    """Métadonnées d'un élément pédagogique extraites de la ligne d'en-têtes."""
    __slots__ = ("col_idx", "header", "code", "type_")

    def __init__(self, col_idx: int, header: str):
        self.col_idx = col_idx
        self.header = header                          # libellé complet original
        self.code = BUTCurriculumTransformer.static_extract_element_code(header)
        self.type_ = BUTCurriculumTransformer.static_detect_element_type(header)


class _ParsedRow:
    """Ligne de données normalisée (context hérité + contributions)."""
    __slots__ = ("parcours", "ue_label", "ac_description", "contributions")

    def __init__(
        self,
        parcours: str,
        ue_label: str,
        ac_description: str,
        contributions: Dict[str, bool],  # element_code → True si croix
    ):
        self.parcours = parcours
        self.ue_label = ue_label
        self.ac_description = ac_description
        self.contributions = contributions


# ---------------------------------------------------------------------------
# Classe de base générique
# ---------------------------------------------------------------------------

class BUTCurriculumTransformer:
    """
    Transformer générique pour tous les programmes BUT.

    Signature réelle :
        BUTCurriculumTransformer(source_file_path: str | None = None)

    L'identité du programme (id, nom) n'est PAS injectée par une classe de
    configuration : elle est résolue automatiquement depuis le nom du
    fichier source (source_file_path, ou raw_data["file_name"] /
    raw_data["source_file"] injecté par le pipeline) — voir
    _resolve_programme_identity(). Ex. "QLIO_BUT__ANNEXE.xlsx" → "BUT_QLIO".

    Instanciation via le TransformerFactory (recommandé) :
        transformer = BUTCurriculumTransformer()
        result = transformer.transform(raw_data)   # raw_data contient file_name

    Usage direct :
        transformer = BUTCurriculumTransformer(source_file_path="INFO_BUT.xlsx")
        result = transformer.transform(raw_data)

    Le layout Excel (colonnes parcours/UE/AC, ligne d'en-têtes…) est
    spécifique au format Annexe BUT et centralisé dans _get_column_layout().
    Pour une source à format différent : ne pas copier ce transformer,
    créer un Normalizer + Transformer dédiés (voir docstring du module).
    """

    # Marqueurs de contribution reconnus dans les cellules (croix APC)
    CONTRIBUTION_MARKERS: frozenset = frozenset(
        {"x", "×", "✓", "✔", "oui", "yes", "1"}
    )

    # Mots-clés des lignes de métadonnées (volumes, totaux…)
    # Ne PAS inclure "coefficients" ici : il est géré séparément.
    METADATA_KEYWORDS: tuple = (
        "volume horaire",
        "dont cm",
        "dont td",
        "dont tp",
        "heures de projet",
        "type de b.u.t",
        "dont htp",
        "rapport ",
        "taux minimum",
        "total volumes",
    )

    # ---------------------------------------------------------------------------
    # Point d'entrée public
    # ---------------------------------------------------------------------------

    def transform(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        raw_data : {"sheets": [{"sheet_name": str, "rows": List[List]}]}
        Retourne : {"canonical": Programme, "flat": List[dict]}
        """
        programme = self._build_programme(raw_data)
        flat_rows = self._flatten_programme(programme)
        return {"canonical": programme, "flat": flat_rows}

    # ---------------------------------------------------------------------------
    # Construction du Programme
    # ---------------------------------------------------------------------------

    def __init__(self, source_file_path: Optional[str] = None) -> None:
        """
        source_file_path : chemin optionnel vers le fichier source Excel.
            Le programme_id et le nom sont extraits automatiquement
            depuis le nom de fichier (préfixe avant le premier '_').

            Ex: "QLIO_BUT__referentiel.xlsx" → programme_id="BUT_QLIO"

            Si absent, le programme_id sera résolu lors du transform()
            depuis la clé "source_file" de raw_data.
        """
        self._source_file_path = source_file_path
        self._element_nom_cache: Dict[str, str] = {}
        self._element_type_cache: Dict[str, str] = {}

    # ---------------------------------------------------------------------------
    # Résolution automatique de l'identité du programme
    # ---------------------------------------------------------------------------

    def _resolve_programme_identity(
        self, raw_data: Dict[str, Any]
    ) -> tuple:
        """
        Extrait programme_id et nom automatiquement depuis :
          1. self._source_file_path (passé au constructeur)
          2. raw_data["source_file"] (injecté par le pipeline ETL)
          3. Fallback générique si aucun chemin disponible

        Convention de nommage attendue :
          QLIO_BUT__ANNEXE_A__.xlsx  → BUT_QLIO
          INFO_referentiel.xlsx      → BUT_INFO
          GEA_BUT_referentiel.xlsx   → BUT_GEA

        Le préfixe est le premier segment avant '_' du nom de fichier.
        Si le préfixe vaut "BUT" (fichier commençant par BUT_),
        on prend le second segment.
        """
        # "file_name" est injecté automatiquement par extract_excel
        # "source_file" est le fallback pour les autres extracteurs
        file_path = (
            self._source_file_path
            or raw_data.get("file_name", "")
            or raw_data.get("source_file", "")
        )

        if file_path:
            from pathlib import Path
            import re as _re
            stem = Path(file_path).stem
            parts = _re.split(r'[_-]+', stem)
            parts = [p for p in parts if p]

            # Ignorer "BUT" s'il est en première position
            prefix = parts[0].upper()
            if prefix == "BUT" and len(parts) > 1:
                prefix = parts[1].upper()

            programme_id = f"BUT_{prefix}"
            programme_nom = f"BUT {prefix}"
            logger.debug("Programme résolu depuis fichier : %s → %s", file_path, programme_id)
            return programme_id, programme_nom

        logger.warning(
            "Aucun fichier source disponible — programme_id générique utilisé. "
            "Passer source_file dans raw_data ou au constructeur."
        )
        return "BUT_GENERIQUE", "BUT Générique"

    def _build_programme(self, raw_data: Dict[str, Any]) -> Programme:
        programme_id, programme_nom = self._resolve_programme_identity(raw_data)

        programme = Programme(
            id=programme_id,
            nom=programme_nom,
            type="BUT",
            niveau="Bac+3",
            ects_total=180,
            duree=3,
            periodes=[],
        )

        periodes_map: Dict[str, PeriodeProgramme] = {}

        for sheet in raw_data.get("sheets", []):
            self._process_sheet(programme, periodes_map, sheet)

        programme.periodes.sort(key=lambda p: p.numero)
        return programme

    def _process_sheet(
        self,
        programme: Programme,
        periodes_map: Dict[str, PeriodeProgramme],
        sheet: Dict[str, Any],
    ) -> None:
        sheet_name = sheet.get("sheet_name", "")
        rows = self._normalize_sheet_rows(sheet.get("rows", []))
        semestre = self._extract_semestre(sheet_name)

        if semestre == 0 or not rows:
            logger.debug("Feuille ignorée : '%s'", sheet_name)
            return

        layout = self._get_column_layout(rows)
        headers = self._get_headers(rows, layout.header_row)

        # Colonnes pédagogiques (SAE, Ressources, Portfolio, Stage)
        element_columns: List[_ElementMeta] = [
            _ElementMeta(idx, self._clean(h))
            for idx, h in enumerate(headers)
            if idx >= layout.element_start_col
            and self._is_pedagogical_element(h)
        ]

        if not element_columns:
            logger.warning("S%d : aucune colonne pédagogique", semestre)
            return

        # Enregistrer les libellés complets et types dans le cache (nom + type)
        self._register_element_columns(element_columns)

        # Volumes horaires par element_code
        hours_by_code = self._extract_hours(rows, element_columns)

        # Coefficients par (ue_code, parcours) — pour les crédits des groupes
        credits_by_option = self._extract_credits(rows, element_columns, layout)

        # Lignes de données parsées
        parsed_rows = self._parse_data_rows(rows, element_columns, layout)

        if not parsed_rows:
            logger.warning("S%d : aucune ligne de données parsée", semestre)
            return

        periode = self._get_or_create_periode(programme, periodes_map, semestre)
        self._build_subtree(
            periode, semestre, parsed_rows, hours_by_code, credits_by_option
        )

    # ---------------------------------------------------------------------------
    # Détection du layout (surchargeable pour d'autres formations)
    # ---------------------------------------------------------------------------

    def _get_column_layout(self, rows: List[List[Any]]) -> _ColumnLayout:
        """
        Retourne le layout par défaut BUT.
        À surcharger si une autre formation a un layout différent.
        """
        # Détecter dynamiquement la première ligne de données
        data_start = self._detect_data_start(rows)
        return _ColumnLayout(
            col_parcours=0,
            col_ue=1,
            col_ac=9,
            header_row=3,
            data_start_row=data_start,
            element_start_col=10,
        )

    def _detect_data_start(self, rows: List[List[Any]]) -> int:
        """
        Détecte la première ligne avec un label 'UE X.X' en col 1.
        Fallback sur 6 (convention BUT).
        """
        for ri, row in enumerate(rows):
            v = self._clean(row[1]) if len(row) > 1 else ""
            if re.match(r"^UE\s*\d+", v, re.IGNORECASE):
                return ri
        return 6

    # ---------------------------------------------------------------------------
    # Parsing des lignes de données
    # ---------------------------------------------------------------------------

    def _parse_data_rows(
        self,
        rows: List[List[Any]],
        element_columns: List[_ElementMeta],
        layout: _ColumnLayout,
    ) -> List[_ParsedRow]:
        """
        Parcourt les lignes de données en propageant vers le bas
        les valeurs de parcours / UE / AC quand une cellule est vide.
        """
        result: List[_ParsedRow] = []
        current_parcours = "COMMUN"
        current_ue_label = ""
        current_ac_description = ""

        for raw_row in rows[layout.data_start_row:]:
            row = self._normalize_row(raw_row, min_size=max(layout.col_ac + 1, 10))

            if self._is_empty_row(row):
                continue

            # Séparer les lignes de volumes/totaux des lignes AC
            # La ligne "Coefficients" n'est PAS une métadonnée : elle sert
            # à extraire les crédits, donc on la passe ici silencieusement.
            col9_text = self._clean(row[layout.col_ac]).lower()
            if col9_text == "coefficients":
                continue
            if self._is_metadata_row(row):
                continue

            parcours_cell = self._clean(row[layout.col_parcours])
            ue_cell = self._clean(row[layout.col_ue])
            ac_cell = self._clean(row[layout.col_ac])

            # Propagation du contexte
            if parcours_cell:
                current_parcours = self._normalize_parcours(parcours_cell)
            if ue_cell:
                current_ue_label = ue_cell
            if ac_cell and ac_cell.lower() not in (
                "apprentissages critiques", "ue", "compétences associées"
            ):
                current_ac_description = ac_cell

            if not current_ue_label or not current_ac_description:
                continue

            # Contributions (croix ×) par element_code
            contributions: Dict[str, bool] = {
                em.code: self._clean(row[em.col_idx]).lower()
                in self.CONTRIBUTION_MARKERS
                for em in element_columns
                if em.col_idx < len(row)
            }

            # N'émettre la ligne que si au moins une contribution existe
            if not any(contributions.values()):
                continue

            result.append(
                _ParsedRow(
                    parcours=current_parcours,
                    ue_label=current_ue_label,
                    ac_description=current_ac_description,
                    contributions=contributions,
                )
            )

        return result

    # ---------------------------------------------------------------------------
    # Construction du sous-arbre Pydantic
    # ---------------------------------------------------------------------------

    def _scan_optional_ues(self, parsed_rows: List[_ParsedRow]) -> Set[str]:
        """
        Passe 1 : détecte les UE qui ont plusieurs parcours distincts.
        Ces UE nécessitent un Composite parent.
        Les UE avec un seul parcours (COMMUN) restent des Elementaire directs.
        """
        parcours_par_ue: Dict[str, Set[str]] = {}
        for pr in parsed_rows:
            ue_code = self._normalize_ue_code(pr.ue_label)
            parcours_par_ue.setdefault(ue_code, set()).add(pr.parcours)
        return {
            ue_code
            for ue_code, parcours_set in parcours_par_ue.items()
            if len(parcours_set) > 1
        }

    def _build_subtree(
        self,
        periode: PeriodeProgramme,
        semestre: int,
        parsed_rows: List[_ParsedRow],
        hours_by_code: Dict[str, Dict[str, float]],
        credits_by_option: Dict[Tuple[str, str], float],
    ) -> None:
        # Passe 1 : détecter les UE optionnelles (multi-parcours)
        optional_ue_codes: Set[str] = self._scan_optional_ues(parsed_rows)

        # Caches locaux
        elementaires_directs: Dict[str, GroupeElementsPedagogiquesElementaire] = {}
        composites: Dict[str, GroupeElementsPedagogiquesComposite] = {}
        elementaires_options: Dict[str, GroupeElementsPedagogiquesElementaire] = {}

        # Pré-charger l'existant (feuilles multiples sur la même période)
        for g in periode.groupes_elements_pedagogiques:
            if isinstance(g, GroupeElementsPedagogiquesComposite):
                composites[g.code] = g
                for sub in g.groupes_elements_pedagogiques:
                    elementaires_options[f"{g.code}__{sub.contrainte}"] = sub
            elif isinstance(g, GroupeElementsPedagogiquesElementaire):
                elementaires_directs[g.code] = g

        for pr in parsed_rows:
            ue_code = self._normalize_ue_code(pr.ue_label)
            credits = credits_by_option.get(
                (ue_code, pr.parcours),
                credits_by_option.get((ue_code, "COMMUN"), 0.0),
            )

            if ue_code in optional_ue_codes:
                # ── UE optionnelle : Composite → Elementaire ────────────
                elementaire = self._get_or_create_elementaire_sous_composite(
                    periode=periode,
                    composites=composites,
                    elementaires_options=elementaires_options,
                    semestre=semestre,
                    ue_code=ue_code,
                    ue_label=pr.ue_label,
                    parcours=pr.parcours,
                    credits=credits,
                )
            else:
                # ── UE standard : Elementaire directement dans la période ─
                elementaire = self._get_or_create_elementaire_direct(
                    periode=periode,
                    elementaires_directs=elementaires_directs,
                    semestre=semestre,
                    ue_code=ue_code,
                    ue_label=pr.ue_label,
                    credits=credits,
                )

            elementaire = elementaire

            # -- Niveau 3 : Éléments pédagogiques + AC --
            for element_code, contributed in pr.contributions.items():
                if not contributed:
                    continue

                element_id = self._make_element_id(semestre, elementaire.code, element_code)
                element_nom = self._element_nom_cache.get(element_code, element_code)
                element_type = self._element_type_cache.get(element_code, "ELEMENT_PEDAGOGIQUE")

                element = self._get_or_create_element(
                    elementaire=elementaire,
                    element_id=element_id,
                    element_nom=element_nom,
                    element_type=element_type,
                    hours=hours_by_code.get(element_code, {}),
                    credits=credits_by_option.get(
                        (ue_code, pr.parcours), 0.0
                    ),
                )

                ac_id = self._make_ac_id(
                    semestre=semestre,
                    parcours=pr.parcours,
                    ue_code=ue_code,
                    element_code=element_code,
                    ac_description=pr.ac_description,
                )
                self._add_ac_to_element(element, ac_id, pr.ac_description)

    # ---------------------------------------------------------------------------
    # Extraction des volumes horaires
    # ---------------------------------------------------------------------------

    def _extract_hours(
        self,
        rows: List[List[Any]],
        element_columns: List[_ElementMeta],
    ) -> Dict[str, Dict[str, float]]:
        """
        Retourne : element_code → {"cm": x, "td": x, "tp": x, "projet": x}
        Cherche les labels dans les 10 premières colonnes de chaque ligne.
        """
        result: Dict[str, Dict[str, float]] = {}

        hour_patterns = (
            ("dont cm",         "cm"),
            ("dont td",         "td"),
            ("dont tp",         "tp"),
            ("heures de projet","projet"),
        )

        for raw_row in rows:
            row_text = " ".join(
                self._clean(v).lower()
                for v in (raw_row[:10] if len(raw_row) >= 10 else raw_row)
            )

            hour_type: Optional[str] = next(
                (ht for kw, ht in hour_patterns if kw in row_text),
                None,
            )
            if not hour_type:
                continue

            for em in element_columns:
                val = raw_row[em.col_idx] if em.col_idx < len(raw_row) else None
                result.setdefault(
                    em.code,
                    {"cm": 0.0, "td": 0.0, "tp": 0.0, "projet": 0.0},
                )
                result[em.code][hour_type] = self._parse_float(val)

        return result

    # ---------------------------------------------------------------------------
    # Extraction des crédits / coefficients par (ue_code, parcours)
    # ---------------------------------------------------------------------------

    def _extract_credits(
        self,
        rows: List[List[Any]],
        element_columns: List[_ElementMeta],
        layout: _ColumnLayout,
    ) -> Dict[Tuple[str, str], float]:
        """
        Lit les lignes "Coefficients" pour associer à chaque (ue_code, parcours)
        la somme des coefficients de ses éléments — utilisée comme crédits du groupe.
        La ligne Coefficients est TOUJOURS en col 9 avec le label exact.
        Le parcours courant est propagé depuis les lignes précédentes.
        """
        result: Dict[Tuple[str, str], float] = {}
        current_parcours = "COMMUN"
        current_ue = ""

        for raw_row in rows:
            row = self._normalize_row(raw_row, min_size=layout.col_ac + 1)

            parcours_cell = self._clean(row[layout.col_parcours])
            ue_cell = self._clean(row[layout.col_ue])
            col9 = self._clean(row[layout.col_ac]).lower()

            if parcours_cell:
                current_parcours = self._normalize_parcours(parcours_cell)
            if ue_cell and re.match(r"^UE\s*\d+", ue_cell, re.IGNORECASE):
                current_ue = self._normalize_ue_code(ue_cell)

            if col9 != "coefficients" or not current_ue:
                continue

            total = sum(
                self._parse_float(
                    raw_row[em.col_idx] if em.col_idx < len(raw_row) else None
                )
                for em in element_columns
            )

            key = (current_ue, current_parcours)
            result[key] = total

        return result

    # ---------------------------------------------------------------------------
    # Gestion des éléments et AC
    # ---------------------------------------------------------------------------

    def _get_or_create_elementaire_direct(
        self,
        periode: PeriodeProgramme,
        elementaires_directs: Dict[str, GroupeElementsPedagogiquesElementaire],
        semestre: int,
        ue_code: str,
        ue_label: str,
        credits: float,
    ) -> GroupeElementsPedagogiquesElementaire:
        """UE standard : Elementaire posé directement dans la période."""
        if ue_code in elementaires_directs:
            return elementaires_directs[ue_code]

        elementaire = GroupeElementsPedagogiquesElementaire(
            id=f"S{semestre}_{ue_code}",
            code=ue_code,
            intitule=ue_label,
            credits=credits,
            type="UE_COMMUNE",
            contrainte=None,
            elements_pedagogiques=[],
        )
        periode.groupes_elements_pedagogiques.append(elementaire)
        elementaires_directs[ue_code] = elementaire
        return elementaire

    def _get_or_create_elementaire_sous_composite(
        self,
        periode: PeriodeProgramme,
        composites: Dict[str, GroupeElementsPedagogiquesComposite],
        elementaires_options: Dict[str, GroupeElementsPedagogiquesElementaire],
        semestre: int,
        ue_code: str,
        ue_label: str,
        parcours: str,
        credits: float,
    ) -> GroupeElementsPedagogiquesElementaire:
        """UE optionnelle : Composite parent + Elementaire par parcours."""
        if ue_code not in composites:
            composite = GroupeElementsPedagogiquesComposite(
                id=f"S{semestre}_{ue_code}",
                code=ue_code,
                intitule=ue_label,
                credits=0.0,
                type="UE_OPTIONNELLE",
                contrainte="choix_parcours",
                groupes_elements_pedagogiques=[],
            )
            periode.groupes_elements_pedagogiques.append(composite)
            composites[ue_code] = composite

        composite = composites[ue_code]
        option_key = f"{ue_code}__{parcours}"

        if option_key in elementaires_options:
            return elementaires_options[option_key]

        option_code = f"{ue_code}_{parcours}"
        elementaire = GroupeElementsPedagogiquesElementaire(
            id=f"S{semestre}_{option_code}",
            code=option_code,
            intitule=f"{ue_label} — {parcours}",
            credits=credits,
            type="OPTION_PARCOURS",
            contrainte=parcours,
            elements_pedagogiques=[],
        )
        composite.groupes_elements_pedagogiques.append(elementaire)
        elementaires_options[option_key] = elementaire
        return elementaire

    def _get_or_create_element(
        self,
        elementaire: GroupeElementsPedagogiquesElementaire,
        element_id: str,
        element_nom: str,
        element_type: str,
        hours: Dict[str, float],
        credits: float,
    ):
        for el in elementaire.elements_pedagogiques:
            if el.id == element_id:
                return el

        if element_type == "STAGE":
            # SAE4.02 - Stage → type métier STAGE → ElementPedagogiqueProfessionnel
            # La durée est la somme de tous les volumes (stage = immersion complète)
            duree = sum([
                hours.get("cm", 0.0),
                hours.get("td", 0.0),
                hours.get("tp", 0.0),
                hours.get("projet", 0.0),
            ])
            element = ElementPedagogiqueProfessionnel(
                id=element_id,
                nom=element_nom,
                type="STAGE",
                credits=credits,
                duree=duree,
                modalite="stage",
                acquis_apprentissage=[],
                enseignants=[],
            )
        else:
            # SAE, RESSOURCE, PORTFOLIO → ElementPedagogiqueFormatif
            element = ElementPedagogiqueFormatif(
                id=element_id,
                nom=element_nom,
                type=element_type,
                credits=credits,
                cm=hours.get("cm", 0.0),
                td=hours.get("td", 0.0),
                tp=hours.get("tp", 0.0),
                projet=hours.get("projet", 0.0),
                acquis_apprentissage=[],
                enseignants=[],
                ressources=[],
                activites=[],
                evaluations=[],
                acquis_apprentissage_elementaires=[],
            )

        elementaire.elements_pedagogiques.append(element)
        return element

    def _add_ac_to_element(
        self,
        element,
        ac_id: str,
        description: str,
    ) -> None:
        for ac in element.acquis_apprentissage:
            if ac.id == ac_id:
                return
        element.acquis_apprentissage.append(
            AcquisApprentissage(id=ac_id, description=description)
        )

    # ---------------------------------------------------------------------------
    # Aplatissement pour le dashboard APC
    # ---------------------------------------------------------------------------

    def _flatten_programme(self, programme: Programme) -> List[Dict[str, Any]]:
        """
        Une ligne par lien Élément ↔ AC.
        Gère les deux topologies :
          - Elementaire direct (UE commune)        → composite=None
          - Composite → Elementaire (UE optionnelle) → composite=Composite
        """
        rows: List[Dict[str, Any]] = []

        for periode in programme.periodes:
            for groupe in periode.groupes_elements_pedagogiques:

                if isinstance(groupe, GroupeElementsPedagogiquesElementaire):
                    # UE commune : Elementaire directement dans la période
                    self._flatten_elementaire(
                        rows, programme, periode,
                        composite=None,
                        elementaire=groupe,
                    )

                elif isinstance(groupe, GroupeElementsPedagogiquesComposite):
                    # UE optionnelle : Composite → Elementaires
                    for elementaire in groupe.groupes_elements_pedagogiques:
                        self._flatten_elementaire(
                            rows, programme, periode,
                            composite=groupe,
                            elementaire=elementaire,
                        )

        return rows

    def _flatten_elementaire(
        self,
        rows: List[Dict[str, Any]],
        programme: Programme,
        periode: PeriodeProgramme,
        composite: Optional[GroupeElementsPedagogiquesComposite],
        elementaire: GroupeElementsPedagogiquesElementaire,
    ) -> None:
        for element in elementaire.elements_pedagogiques:
            acquis = element.acquis_apprentissage or []
            if acquis:
                for ac in acquis:
                    rows.append(self._build_flat_row(
                        programme, periode, composite, elementaire, element, ac
                    ))
            else:
                rows.append(self._build_flat_row(
                    programme, periode, composite, elementaire, element, None
                ))

    def _build_flat_row(
        self,
        programme: Programme,
        periode: PeriodeProgramme,
        composite: Optional[GroupeElementsPedagogiquesComposite],
        elementaire: GroupeElementsPedagogiquesElementaire,
        element,
        ac: Optional[AcquisApprentissage],
    ) -> Dict[str, Any]:
        """
        Champs ue_* : pointent vers l'UE de référence canonique.
          - UE commune    : composite=None → l'Elementaire porte l'identité de l'UE
          - UE optionnelle: composite≠None → le Composite porte l'identité de l'UE
        """
        return {
            # Programme
            "programme_id":       programme.id,
            "programme_nom":      programme.nom,
            "programme_type":     programme.type,
            "programme_niveau":   programme.niveau,
            # Période
            "periode_id":         periode.id,
            "semestre":           periode.numero,
            # UE (référence canonique — composite si optionnelle, elementaire sinon)
            "ue_id": (
                composite.id if composite else elementaire.id
            ),
            "ue_code": (
                composite.code if composite else elementaire.code
            ),
            "ue_intitule": (
                composite.intitule if composite else elementaire.intitule
            ),
            "ue_type": (
                composite.type if composite else elementaire.type
            ),
            "ue_est_optionnelle": (
                composite.type == "UE_OPTIONNELLE" if composite else False
            ),
            "ue_contrainte": (
                composite.contrainte if composite and composite.contrainte else ""
            ),
            # Groupe élémentaire (option ou UE directe)
            "option_id":          elementaire.id,
            "option_code":        elementaire.code,
            "option_intitule":    elementaire.intitule,
            "parcours":           elementaire.contrainte or "COMMUN",
            "option_credits":     elementaire.credits,
            # Élément pédagogique
            "element_id":         element.id,
            "element_nom":        element.nom,
            "element_type":       element.type,
            "element_credits":    element.credits,
            "volume_total":       getattr(element, "volume_total", 0.0),
            "cm":                 getattr(element, "cm", 0.0),
            "td":                 getattr(element, "td", 0.0),
            "tp":                 getattr(element, "tp", 0.0),
            "projet":             getattr(element, "projet", 0.0),
            # Acquis d'Apprentissage
            "ac_id":              ac.id if ac else "",
            "ac_description":     ac.description if ac else "",
        }


    def _get_or_create_periode(
        self,
        programme: Programme,
        periodes_map: Dict[str, PeriodeProgramme],
        semestre: int,
    ) -> PeriodeProgramme:
        pid = f"S{semestre}"
        if pid not in periodes_map:
            periode = PeriodeProgramme(
                id=pid,
                numero=semestre,
                ects=30,
                groupes_elements_pedagogiques=[],
            )
            programme.periodes.append(periode)
            periodes_map[pid] = periode
        return periodes_map[pid]

    # ---------------------------------------------------------------------------
    # Helpers : identification des éléments pédagogiques
    # ---------------------------------------------------------------------------

    def _is_pedagogical_element(self, value: Any) -> bool:
        return (
            self._is_sae(value)
            or self._is_ressource(value)
            or self._is_portfolio(value)
            or self._is_stage(value)
        )

    def _is_sae(self, value: Any) -> bool:
        v = self._clean(value).upper()
        return v.startswith("SAE") or v.startswith("SAÉ")

    def _is_ressource(self, value: Any) -> bool:
        return bool(re.match(r"^R\s*\d+", self._clean(value).upper()))

    def _is_portfolio(self, value: Any) -> bool:
        return "PORTFOLIO" in self._clean(value).upper()

    def _is_stage(self, value: Any) -> bool:
        return "STAGE" in self._clean(value).upper()

    @staticmethod
    def static_detect_element_type(value: Any) -> str:
        """
        Détecte le type métier d'un élément depuis son libellé.
        Utilisée par _ElementMeta à la construction.

        Règle BUT → méta-modèle ForestED :
          SAE + "Stage" dans le nom → STAGE  (ElementPedagogiqueProfessionnel)
          SAE + "Portfolio" dans le nom → PORTFOLIO (ElementPedagogiqueFormatif)
          SAE seul → SAE (ElementPedagogiqueFormatif)
          R[0-9]+ → RESSOURCE
        """
        v = str(value).upper().replace("\n", " ").replace("\xa0", " ").strip()

        # SAE avec sémantique stage professionnel
        if (v.startswith("SAE") or v.startswith("SAÉ")) and "STAGE" in v:
            return "STAGE"

        # SAE avec sémantique portfolio
        if (v.startswith("SAE") or v.startswith("SAÉ")) and "PORTFOLIO" in v:
            return "PORTFOLIO"

        # SAE standard
        if v.startswith("SAE") or v.startswith("SAÉ"):
            return "SAE"

        if bool(re.match(r"^R\s*\d+", v)):
            return "RESSOURCE"

        if "PORTFOLIO" in v:
            return "PORTFOLIO"

        if "STAGE" in v:
            return "STAGE"

        return "ELEMENT_PEDAGOGIQUE"

    @staticmethod
    def static_extract_element_code(value: Any) -> str:
        """Version statique utilisée par _ElementMeta à la construction."""
        v = str(value).upper()
        v = v.replace("É", "E").replace("È", "E").replace("Ê", "E")
        v = v.replace("À", "A").replace("Â", "A")
        match = re.search(
            r"(SA[EE]\s*\d+(?:[._]\w+)*"
            r"|R\s*\d+(?:[._]\w+)*"
            r"|STAGE(?:[._]\w+)*"
            r"|PORTFOLIO)",
            v,
        )
        raw = match.group(1) if match else v
        raw = re.sub(r"\s+", "_", raw)
        raw = re.sub(r"[.\-]+", "_", raw)
        raw = re.sub(r"_+", "_", raw)
        return raw.strip("_")

    # ---------------------------------------------------------------------------
    # Helpers : normalisation des codes et identifiants
    # ---------------------------------------------------------------------------

    def _normalize_code(self, value: Any) -> str:
        v = self._clean(value).upper()
        v = v.replace("É", "E").replace("È", "E").replace("Ê", "E")
        v = v.replace("À", "A").replace("Â", "A")
        v = re.sub(r"\s+", "_", v)
        v = re.sub(r"[.\-]+", "_", v)
        v = re.sub(r"_+", "_", v)
        return v.strip("_")

    def _normalize_ue_code(self, value: Any) -> str:
        v = self._clean(value).upper()
        match = re.search(r"UE\s*\d+(?:\.\d+)?", v)
        return self._normalize_code(match.group(0) if match else v)

    def _normalize_parcours(self, value: Any) -> str:
        """
        Normalise un code parcours.
        Aucun alias hardcodé ici : les valeurs brutes MAJ sont utilisées
        directement après normalisation. Surcharger dans la sous-classe si
        des aliases spécifiques sont nécessaires.
        """
        v = self._clean(value).upper().strip()
        if not v:
            return "COMMUN"
        # Détection générique du tronc commun
        if v in ("TRONC COMMUN", "COMMUN", "TC", "COMMON"):
            return "COMMUN"
        return self._normalize_code(v)

    def _make_element_id(self, semestre: int, elementaire_code: str, element_code: str) -> str:
        """
        ID unique d'un élément dans son contexte pédagogique complet :
        S{semestre}_{elementaire_code}_{element_code}

        On passe le code de l'Elementaire (pas du Composite) car il porte
        déjà le parcours pour les UE optionnelles :
          - UE standard   : elementaire.code = "UE_1_1"
          - UE optionnelle: elementaire.code = "UE_3_4_MP"

        Garantit l'unicité dans tous les cas :
          SAE1.01 dans UE1.1 → S1_UE_1_1_SAE1_01
          SAE1.01 dans UE1.2 → S1_UE_1_2_SAE1_01
          SAE3.41 dans UE3.4/MP   → S3_UE_3_4_MP_SAE3_41
          SAE3.41 dans UE3.4/PCLG → S3_UE_3_4_PCLG_SAE3_41
        """
        return self._normalize_code(f"S{semestre}_{elementaire_code}_{element_code}")

    def _make_ac_id(
        self,
        semestre: int,
        parcours: str,
        ue_code: str,
        element_code: str,
        ac_description: str,
    ) -> str:
        slug = self._normalize_code(ac_description[:50])
        return f"AC_S{semestre}_{parcours}_{ue_code}_{element_code}_{slug}"

    # ---------------------------------------------------------------------------
    # Helpers : extraction depuis les feuilles
    # ---------------------------------------------------------------------------

    def _extract_semestre(self, sheet_name: str) -> int:
        for pattern in (r"semestre\s*(\d+)", r"\bS(\d+)\b"):
            m = re.search(pattern, sheet_name, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return 0

    def _get_headers(self, rows: List[List[Any]], header_row: int) -> List[str]:
        if len(rows) <= header_row:
            return []
        return [self._clean(v) for v in rows[header_row]]

    def _normalize_sheet_rows(self, raw_rows: List[Any]) -> List[List[Any]]:
        result = []
        for row in raw_rows:
            result.append(list(row.values()) if isinstance(row, dict) else list(row))
        return result

    def _normalize_row(self, row: List[Any], min_size: int = 10) -> List[Any]:
        row = list(row)
        if len(row) < min_size:
            row.extend([None] * (min_size - len(row)))
        return row

    def _is_empty_row(self, row: List[Any]) -> bool:
        return all(self._clean(v) == "" for v in row)

    def _is_metadata_row(self, row: List[Any]) -> bool:
        """
        Détecte les lignes de volumes horaires et totaux.
        Ne filtre PAS "coefficients" (géré séparément dans _parse_data_rows).
        Ne filtre PAS "portfolio" (c'est un type d'élément, pas une métadonnée).
        """
        text = " ".join(self._clean(v).lower() for v in row)
        return any(kw in text for kw in self.METADATA_KEYWORDS)

    # ---------------------------------------------------------------------------
    # Helpers : parsing de valeurs
    # ---------------------------------------------------------------------------

    def _clean(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).replace("\n", " ").replace("\xa0", " ").strip()

    def _parse_float(self, value: Any) -> float:
        v = self._clean(value).replace("h", "").replace(",", ".")
        v = re.sub(r"[^0-9.]", "", v)
        try:
            return float(v) if v else 0.0
        except ValueError:
            return 0.0

    # ---------------------------------------------------------------------------
    # Cache des noms et types par code élément (rempli lors du parsing headers)
    # ---------------------------------------------------------------------------

    def _register_element_columns(
        self, element_columns: List[_ElementMeta]
    ) -> None:
        """Enregistre les libellés complets et types dans les caches."""
        for em in element_columns:
            self._element_nom_cache[em.code] = em.header
            self._element_type_cache[em.code] = em.type_