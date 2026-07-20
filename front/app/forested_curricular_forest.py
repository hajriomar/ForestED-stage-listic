"""
forested_curricular_forest.py
──────────────────────────────
Forêt curriculaire APC : Semestre → UE → Module → AC.

Lecture inverse de la forêt pédagogique (forested_forest.py) : au lieu de
partir des compétences, on part de l'organisation curriculaire (semestre
puis UE) pour voir quels modules existent et quels AC ils couvrent.

Ce module est volontairement AUTONOME (aucun import depuis
forested_forest.py) pour éviter tout risque d'import circulaire. La
palette de couleurs et quelques petits utilitaires génériques sont donc
dupliqués ici en copies indépendantes plutôt que ré-importés.

Affichage : les 4 couches Semestre → UE → Module → AC sont TOUJOURS
dessinées, y compris en vue globale. Les AC sont de vrais nœuds (petits
points), toujours visibles. Le clic sert uniquement à réduire le
sous-arbre affiché (zoom / focus), pas à révéler une couche qui serait
sinon masquée.

v4 : couleur AC stabilisée (_comp_stable_color_index) + libellé "AC".
v5 : remplissage AC passé à n2_fill (plus vif), contour niveau en
     épaisseur + nuance de gris, sélection en rouge.
v6 : contour niveau dans la teinte de la compétence (plus de gris/rouge),
     sélection signalée par la taille seule, points espacés + agrandis.
v7/v8 : tentatives de filtre parcours basées sur des noms de champs
     supposés ("parcours", "ue_type", ...) sans connaître le vrai schéma
     de build_visualisation_rows. Toujours sans effet observé.

v9 — abandon de toute hypothèse sur le schéma des lignes. Le filtre
Parcours de la forêt curriculaire n'invente plus SA PROPRE logique : il
réutilise EXACTEMENT le mécanisme déjà utilisé et déjà fonctionnel côté
forêt pédagogique (get_allowed_competence_codes_for_parcours, basé sur la
convention de code de compétence "COMP_PARCOURS_N", identique à celle de
forested_forest.py). _curricular_row_parcours (v7/v8, basée sur des noms
de champs jamais confirmés) est supprimée.

Point important conservé de l'audit demandé : cette logique ne peut
filtrer QUE les lignes qui portent un competence_code (un AC). Les lignes
"module sans AC" (pas de competence_code) n'ont par construction aucune
information de parcours à évaluer par ce mécanisme — elles sont donc
conservées telles quelles quel que soit le parcours sélectionné, pour ne
pas faire disparaître un module simplement parce qu'il n'a pas encore
d'AC rattaché. C'est la même règle que celle déjà appliquée par le filtre
Compétence plus bas dans cette fonction.

Le VRAI filtrage parcours pour la forêt curriculaire est maintenant piloté
depuis forested_forest.py, qui appelle filter_forest_rows_by_parcours (la
fonction pédagogique, prouvée fonctionnelle) sur les lignes AC avant
d'appeler filter_curricular_rows(..., parcours_filter="ALL") — voir le
correctif correspondant dans forested_forest.py. La logique ci-dessous
n'est donc plus le chemin utilisé en production, mais reste correcte et
alignée si filter_curricular_rows est appelée directement avec un
parcours_filter réel (usage autonome / tests).
"""

import re
import plotly.graph_objects as go
from dash import html

from forested_visualisations import empty_figure


# ══════════════════════════════════════════════════════════════════════════════
#  PALETTE COULEURS — copie volontairement indépendante de celle de
#  forested_forest.py (voir note en tête de fichier).
# ══════════════════════════════════════════════════════════════════════════════

PALETTE_ESS = [
    {"n1_fill":"#EEEDFE","n1_border":"#CECBF6","n1_text":"#3C3489",
     "n2_fill":"#AFA9EC","n2_text":"#26215C",
     "n3_fill":"#534AB7","n3_text":"#EEEDFE",
     "root_fill":"#3C3489","root_text":"#EEEDFE","line":"#3C3489"},
    {"n1_fill":"#E1F5EE","n1_border":"#9FE1CB","n1_text":"#085041",
     "n2_fill":"#5DCAA5","n2_text":"#04342C",
     "n3_fill":"#0F6E56","n3_text":"#E1F5EE",
     "root_fill":"#085041","root_text":"#E1F5EE","line":"#085041"},
    {"n1_fill":"#FAECE7","n1_border":"#F5C4B3","n1_text":"#712B13",
     "n2_fill":"#F0997B","n2_text":"#4A1B0C",
     "n3_fill":"#993C1D","n3_text":"#FAECE7",
     "root_fill":"#712B13","root_text":"#FAECE7","line":"#712B13"},
    {"n1_fill":"#ECFEFF","n1_border":"#A5F3FC","n1_text":"#164E63",
     "n2_fill":"#22D3EE","n2_text":"#083344",
     "n3_fill":"#0E7490","n3_text":"#ECFEFF",
     "root_fill":"#164E63","root_text":"#ECFEFF","line":"#164E63"},
    {"n1_fill":"#FAEEDA","n1_border":"#FAC775","n1_text":"#633806",
     "n2_fill":"#EF9F27","n2_text":"#412402",
     "n3_fill":"#854F0B","n3_text":"#FAEEDA",
     "root_fill":"#633806","root_text":"#FAEEDA","line":"#633806"},
    {"n1_fill":"#EAF3DE","n1_border":"#C0DD97","n1_text":"#27500A",
     "n2_fill":"#97C459","n2_text":"#173404",
     "n3_fill":"#3B6D11","n3_text":"#EAF3DE",
     "root_fill":"#27500A","root_text":"#EAF3DE","line":"#27500A"},
    {"n1_fill":"#FBEAF0","n1_border":"#F4C0D1","n1_text":"#72243E",
     "n2_fill":"#ED93B1","n2_text":"#4B1528",
     "n3_fill":"#993556","n3_text":"#FBEAF0",
     "root_fill":"#72243E","root_text":"#FBEAF0","line":"#72243E"},
    {"n1_fill":"#F1EFE8","n1_border":"#D3D1C7","n1_text":"#444441",
     "n2_fill":"#B4B2A9","n2_text":"#2C2C2A",
     "n3_fill":"#5F5E5A","n3_text":"#F1EFE8",
     "root_fill":"#444441","root_text":"#F1EFE8","line":"#444441"},
]


def _niv_key(niv):
    try:
        n = int(niv)
    except Exception:
        return "n1"
    return {1: "n1", 2: "n2", 3: "n3"}.get(n, "n3")


_NIV_BORDER_W = {"n1": 1.0, "n2": 2.0, "n3": 3.2}
_NIV_LABEL = {"n1": "N1 — Débutant", "n2": "N2 — Intermédiaire", "n3": "N3 — Avancé"}

# Contour niveau neutre (AC sans compétence rattachée uniquement) — tons
# de gris doux, jamais noir pur ni rouge.
_NIV_NEUTRAL_BORDER = {"n1": "#E2E8F0", "n2": "#94A3B8", "n3": "#475569"}

CURR_SEM_COLOR = {"fill": "#334155", "text": "#F8FAFC", "border": "#1E293B"}
CURR_UE_COLOR  = {"fill": "#E9EEF5", "text": "#1E293B", "border": "#64748B"}
CURR_MOD_COLOR = {"fill": "#3B82F6", "text": "#FFFFFF", "border": "#1D4ED8"}
CURR_AC_NEUTRAL_FILL = "#94A3B8"
CURR_AC_BASE_SIZE = 14
CURR_AC_SEL_SIZE = 23


def _niv_border_color(cfg, nk):
    """
    Couleur de contour pour un niveau donné, dans la même famille de
    teinte que la compétence (cfg = entrée de PALETTE_ESS), plutôt qu'une
    couleur neutre (gris/noir) ou d'alerte (rouge) qui casserait
    l'harmonie de couleur de la compétence.
    """
    if cfg is None:
        return _NIV_NEUTRAL_BORDER[nk]
    return {"n1": cfg["n1_border"], "n2": cfg["n2_text"], "n3": cfg["line"]}[nk]


def _comp_stable_color_index(competence_code):
    """
    Index de couleur stable pour une compétence, indépendant du
    sous-ensemble de lignes actuellement affiché.

    Pourquoi : calculer l'index via un `sorted(...) + enumerate` sur les
    seules compétences présentes dans la vue courante fait changer la
    couleur d'une compétence selon qu'on est en vue globale ou zoomée,
    puisque son rang dans le sous-ensemble visible change. Ici on dérive
    l'index directement du code lui-même (ex. "COMP_5" -> 5), donc la
    couleur d'une compétence donnée est TOUJOURS la même, quelle que soit
    la vue.
    """
    if not competence_code:
        return 0
    m = re.search(r"(\d+)\s*$", str(competence_code))
    if m:
        return (int(m.group(1)) - 1) % len(PALETTE_ESS)
    return abs(hash(str(competence_code))) % len(PALETTE_ESS)


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITAIRES GÉNÉRIQUES — copies locales (voir note en tête de fichier)
# ══════════════════════════════════════════════════════════════════════════════

def _sort_sem(s):
    try:
        return int(str(s).replace("S", "").replace("s", ""))
    except Exception:
        return 999


def _apply_min_x_span(xmin, xmax, min_span):
    current_span = xmax - xmin
    if current_span >= min_span:
        return xmin, xmax
    center = (xmin + xmax) / 2
    half = min_span / 2
    return center - half, center + half


def _get_competence_family(competence_code):
    """
    Identique à forested_forest.get_competence_family. Dupliquée ici
    (fichier autonome) — voir note en tête de fichier sur le choix de
    duplication plutôt que d'import croisé.
    """
    if not competence_code:
        return "unknown", None
    code = str(competence_code).strip().upper()
    if re.match(r"^COMP_\d+$", code):
        return "essential", None
    match = re.match(r"^COMP_([A-Z][A-Z0-9]*)_\d+$", code)
    if match:
        return "parcours", match.group(1)
    return "unknown", None


def _normalize_selected_parcours(selected_parcours):
    """Identique à forested_forest.normalize_selected_parcours."""
    if not selected_parcours or selected_parcours == "ALL":
        return "ALL"
    value = str(selected_parcours).strip().upper()
    value = value.replace("-", "_").replace(" ", "_")
    if value.startswith("BUT_"):
        value = value.replace("BUT_", "", 1)
    return value


def _get_allowed_competence_codes_for_parcours(rows, selected_parcours):
    """
    Identique à forested_forest.get_allowed_competence_codes_for_parcours
    (même logique, même résultat pour les mêmes lignes) : c'est le
    mécanisme déjà prouvé fonctionnel côté forêt pédagogique. Dupliqué ici
    à l'identique plutôt qu'une heuristique différente basée sur des noms
    de champs non confirmés (voir note de version v9 en tête de fichier).
    """
    if not rows:
        return set()
    selected = _normalize_selected_parcours(selected_parcours)
    all_competences = {r.get("competence_code") for r in rows if r.get("competence_code")}
    if selected == "ALL":
        return all_competences
    allowed = set()
    for competence_code in all_competences:
        family, parcours = _get_competence_family(competence_code)
        if family == "essential":
            allowed.add(competence_code)
        elif family == "parcours" and parcours == selected:
            allowed.add(competence_code)
    return allowed


def _sem_label(sem):
    """Normalise une valeur de semestre (ex. 5 -> "S5"), fallback "Sans semestre"."""
    if sem is None or str(sem).strip() in ("", "None"):
        return "Sans semestre"
    s = str(sem).strip()
    if s.upper().startswith("S") and s[1:].isdigit():
        return s.upper()
    if s.lstrip("-").isdigit():
        return f"S{s}"
    return s


def _sel_get(selected, key, default=None):
    return selected.get(key, default) if isinstance(selected, dict) else default


# ══════════════════════════════════════════════════════════════════════════════
#  PRÉPARATION DES DONNÉES
# ══════════════════════════════════════════════════════════════════════════════

def filter_curricular_rows(rows, sem_filter="ALL", parcours_filter="ALL", comp_filter="ALL"):
    """
    Applique les filtres Semestre / Parcours / Compétence déjà présents sur
    la page à des lignes BRUTES (build_visualisation_rows).

    Parcours (v9) : MÊME logique que filter_forest_rows_by_parcours côté
    forêt pédagogique (get_allowed_competence_codes_for_parcours), appliquée
    uniquement aux lignes qui portent un competence_code. Une ligne "module
    sans AC" (competence_code absent) n'a par construction aucune
    information de parcours à évaluer par cette convention : elle est donc
    toujours conservée, comme le fait déjà le filtre Compétence ci-dessous.

    En production, ce filtre est appliqué en amont par forested_forest.py
    (qui appelle directement filter_forest_rows_by_parcours) et cette
    fonction reçoit alors parcours_filter="ALL" — ce bloc reste néanmoins
    correct et cohérent pour un usage direct/autonome de cette fonction.
    """
    if not rows:
        return []
    result = rows
    if sem_filter not in (None, "ALL"):
        result = [r for r in result if _sem_label(r.get("semestre")) == sem_filter]
    if parcours_filter not in (None, "ALL"):
        ac_rows = [r for r in result if r.get("competence_code")]
        module_only_rows = [r for r in result if not r.get("competence_code")]
        allowed = _get_allowed_competence_codes_for_parcours(ac_rows, parcours_filter)
        filtered_ac_rows = [r for r in ac_rows if r.get("competence_code") in allowed]
        result = filtered_ac_rows + module_only_rows
    if comp_filter not in (None, "ALL"):
        result = [r for r in result if not r.get("competence_code") or r.get("competence_code") == comp_filter]
    return result


def filter_curricular_rows_by_click_selection(rows, selected):
    """
    Réduit les lignes brutes au sous-arbre cliqué, à la manière de
    filter_rows_by_click_selection() côté pédagogique : on garde uniquement
    ce qui est nécessaire pour dessiner le sous-arbre sélectionné, pas
    toute la forêt en arrière-plan.
    """
    if not selected or not isinstance(selected, dict):
        return rows
    kind = selected.get("type")

    if kind == "semester":
        sem = selected.get("semester") or selected.get("id")
        return [r for r in rows if _sem_label(r.get("semestre")) == sem]

    if kind == "ue":
        sem, ue = selected.get("semester"), selected.get("ue_code")
        return [
            r for r in rows
            if _sem_label(r.get("semestre")) == sem
            and (r.get("ue_code") or "Sans UE") == ue
        ]

    if kind in ("module", "ac"):
        sem, ue, mod = selected.get("semester"), selected.get("ue_code"), selected.get("module_code")
        return [
            r for r in rows
            if _sem_label(r.get("semestre")) == sem
            and (r.get("ue_code") or "Sans UE") == ue
            and (r.get("module_code") or r.get("module_id")) == mod
        ]

    return rows


def build_curricular_forest_data(rows):
    """
    Construit la hiérarchie Semestre → UE → Module → AC à partir des lignes
    retournées par build_visualisation_rows(competence_data, curriculum_data).

    Règles de fallback :
      - semestre absent        -> "Sans semestre"
      - ue_code absent         -> "Sans UE"
      - module_code absent     -> ligne ignorée (module obligatoire ici)
      - ac_code absent         -> le module est gardé, sans AC
      - competence_code absent -> AC gardé, couleur neutre en figure

    Semestres triés pédagogiquement, UE et modules triés par code. Les AC
    sont dédupliqués PAR MODULE (clé = ac_code à l'intérieur du dict
    "acs" du module) : si les lignes brutes contiennent plusieurs fois le
    même (module, ac_code) — par ex. parce que build_visualisation_rows a
    produit une ligne par compétence rattachée — un seul point AC est
    dessiné pour ce couple. Si un même ac_code apparaît sous deux modules
    différents, c'est en revanche affiché comme deux points distincts :
    cela reflète un AC réellement travaillé dans deux modules, pas un bug
    de duplication.
    """
    semesters = {}

    for r in rows or []:
        module_code = r.get("module_code") or r.get("module_id")
        if not module_code:
            continue

        sem_label   = _sem_label(r.get("semestre"))
        ue_code     = r.get("ue_code") or "Sans UE"
        ue_name     = r.get("ue_name") or ue_code
        module_name = r.get("module_name") or module_code

        sem_entry = semesters.setdefault(sem_label, {"label": sem_label, "ues": {}})
        ue_entry = sem_entry["ues"].setdefault(ue_code, {"code": ue_code, "name": ue_name, "modules": {}})
        if ue_name and ue_name != ue_code and ue_entry["name"] == ue_code:
            ue_entry["name"] = ue_name

        mod_entry = ue_entry["modules"].setdefault(module_code, {"code": module_code, "name": module_name, "acs": {}})

        ac_code = r.get("ac_code")
        if ac_code and ac_code not in mod_entry["acs"]:
            mod_entry["acs"][ac_code] = {
                "code": ac_code,
                "description": r.get("ac_description") or "",
                "competence_code": r.get("competence_code"),
                "competence_name": r.get("competence_name") or r.get("competence_code") or "",
                "niveau": r.get("niveau"),
            }

    sorted_semesters = {}
    for sem_label in sorted(semesters.keys(), key=_sort_sem):
        sem_entry = semesters[sem_label]
        sorted_ues = {}
        for ue_code in sorted(sem_entry["ues"].keys()):
            ue_entry = sem_entry["ues"][ue_code]
            ue_entry["modules"] = {mc: ue_entry["modules"][mc] for mc in sorted(ue_entry["modules"].keys())}
            sorted_ues[ue_code] = ue_entry
        sem_entry["ues"] = sorted_ues
        sorted_semesters[sem_label] = sem_entry

    return {"semesters": sorted_semesters}


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT — cascade de largeurs. Les AC sont TOUJOURS dessinés
#  (show_ac_detail=True partout), donc chaque module s'élargit selon son
#  nombre d'AC — c'est ce qui garantit que les points ne se chevauchent
#  jamais, plutôt qu'un slot fixe qui masquerait le détail.
# ══════════════════════════════════════════════════════════════════════════════

CURR_AC_STEP     = 0.44
CURR_MOD_SLOT    = 0.95
CURR_MODULE_GAP  = 0.60
CURR_UE_GAP      = 1.40
CURR_SEM_GAP     = 2.80
CURR_MIN_X_SPAN_FULL  = 30
CURR_MIN_X_SPAN_FOCUS = 12

# Lecture bottom-up (même esprit que la forêt pédagogique) : le semestre
# joue le rôle de racine (peu nombreux, structurants, comme les
# compétences), l'AC joue le rôle de canopée (nombreux, fins, feuilles).
CURR_Y_SEM = 0.0
CURR_Y_UE  = 1.8
CURR_Y_MOD = 3.6
CURR_Y_AC  = 5.0


def _curr_mod_width(mod, show_ac_detail=True):
    if show_ac_detail:
        n_ac = max(len(mod["acs"]), 1)
        return max(n_ac * CURR_AC_STEP, CURR_MOD_SLOT * 0.6)
    return CURR_MOD_SLOT


def _curr_ue_width(ue, show_ac_detail=True):
    mods = list(ue["modules"].values())
    if not mods:
        return CURR_MOD_SLOT
    widths = [_curr_mod_width(m, show_ac_detail) for m in mods]
    return sum(widths) + max(0, len(mods) - 1) * CURR_MODULE_GAP


def _curr_sem_width(sem, show_ac_detail=True):
    ues = list(sem["ues"].values())
    if not ues:
        return CURR_MOD_SLOT
    widths = [_curr_ue_width(ue, show_ac_detail) for ue in ues]
    return sum(widths) + max(0, len(ues) - 1) * CURR_UE_GAP


def _compute_curricular_layout(semesters, show_ac_detail=True):
    sem_labels = list(semesters.keys())
    sem_widths = {s: _curr_sem_width(semesters[s], show_ac_detail) for s in sem_labels}
    total = sum(sem_widths.values()) + max(0, len(sem_labels) - 1) * CURR_SEM_GAP

    cursor = -total / 2
    pos_sem, pos_ue, pos_mod, pos_ac = {}, {}, {}, {}

    for sem_label in sem_labels:
        sem = semesters[sem_label]
        sw = sem_widths[sem_label]
        pos_sem[sem_label] = cursor + sw / 2

        ue_cursor = cursor
        for ue_code, ue in sem["ues"].items():
            uw = _curr_ue_width(ue, show_ac_detail)
            ue_cx = ue_cursor + uw / 2
            pos_ue[(sem_label, ue_code)] = ue_cx

            mod_cursor = ue_cursor
            for mod_code, mod in ue["modules"].items():
                mw = _curr_mod_width(mod, show_ac_detail)
                mod_cx = mod_cursor + mw / 2
                pos_mod[(sem_label, ue_code, mod_code)] = mod_cx

                if show_ac_detail:
                    ac_items = list(mod["acs"].items())
                    if ac_items:
                        ac_total_w = len(ac_items) * CURR_AC_STEP
                        ac_cursor = mod_cx - ac_total_w / 2
                        for ac_code, _ac in ac_items:
                            pos_ac[(sem_label, ue_code, mod_code, ac_code)] = ac_cursor + CURR_AC_STEP / 2
                            ac_cursor += CURR_AC_STEP

                mod_cursor += mw + CURR_MODULE_GAP
            ue_cursor += uw + CURR_UE_GAP
        cursor += sw + CURR_SEM_GAP

    return pos_sem, pos_ue, pos_mod, pos_ac


# ══════════════════════════════════════════════════════════════════════════════
#  FIGURES
# ══════════════════════════════════════════════════════════════════════════════

def create_curricular_forest_figure(rows, selected=None, comp_color_index=None):
    """
    Point d'entrée unique appelé depuis forested_forest.py. Le clic ne
    révèle plus une couche cachée (les 4 couches sont toujours dessinées) :
    il sert uniquement à zoomer sur un sous-arbre plus petit. `rows` est
    déjà réduit au sous-arbre cliqué par forested_forest.py quand une
    sélection est active (via filter_curricular_rows_by_click_selection).
    """
    if not rows:
        return empty_figure("Aucune donnée disponible pour cette formation.")

    kind = _sel_get(selected, "type")

    if kind in ("ue", "module", "ac"):
        return create_curricular_forest_focus_figure(
            rows, selected, min_x_span=CURR_MIN_X_SPAN_FOCUS,
            comp_color_index=comp_color_index)

    if kind == "semester":
        return create_curricular_forest_global_figure(
            rows, min_x_span=CURR_MIN_X_SPAN_FOCUS, highlight=selected,
            comp_color_index=comp_color_index)

    return create_curricular_forest_global_figure(
        rows, min_x_span=CURR_MIN_X_SPAN_FULL, highlight=None,
        comp_color_index=comp_color_index)


def create_curricular_forest_global_figure(rows, min_x_span=CURR_MIN_X_SPAN_FULL,
                                           highlight=None, comp_color_index=None):
    """
    Vue Semestre → UE → Module → AC. `highlight` (optionnel) met en avant
    un semestre précis (losange agrandi) — utilisé quand l'utilisateur
    vient de cliquer un semestre (rows déjà filtrées sur ce seul semestre
    par l'appelant, donc la vue reste lisible).
    """
    return _render_curricular_tree(rows, selected=highlight, min_x_span=min_x_span,
                                   comp_color_index=comp_color_index)


def create_curricular_forest_focus_figure(rows, selected,
                                          min_x_span=CURR_MIN_X_SPAN_FOCUS,
                                          comp_color_index=None):
    """
    Vue zoomée : utilisée quand la sélection porte sur une UE, un module ou
    un AC. Les lignes reçues sont déjà réduites au sous-arbre cliqué par
    filter_curricular_rows_by_click_selection() (appelé côté
    forested_forest.py), donc la densité reste faible même si la formation
    entière compte des dizaines de modules.
    """
    return _render_curricular_tree(rows, selected=selected, min_x_span=min_x_span,
                                   comp_color_index=comp_color_index)


def _render_curricular_tree(rows, selected=None, min_x_span=CURR_MIN_X_SPAN_FULL,
                            comp_color_index=None):
    """
    Moteur de rendu unique pour la forêt curriculaire : dessine toujours les
    4 couches Semestre → UE → Module → AC.

    AC : petit point, couleur de remplissage = compétence parente (teinte
    vive et STABLE quelle que soit la vue, via _comp_stable_color_index),
    contour = niveau, dans la même famille de teinte que la compétence
    (voir _niv_border_color). La hauteur n'est PAS utilisée pour coder le
    niveau. La sélection ne change pas de couleur : uniquement la taille.
    """
    if not rows:
        return empty_figure("Aucune donnée disponible pour cette sélection.")

    data = build_curricular_forest_data(rows)
    semesters = data["semesters"]

    n_mod_total = sum(len(ue["modules"]) for sem in semesters.values() for ue in sem["ues"].values())
    if n_mod_total == 0:
        return empty_figure(
            "La forêt curriculaire nécessite des données curriculum avec "
            "semestres, UE et modules."
        )
    n_ac_total = sum(
        len(mod["acs"])
        for sem in semesters.values() for ue in sem["ues"].values()
        for mod in ue["modules"].values()
    )
    if n_ac_total == 0:
        return empty_figure("Les modules existent, mais aucun lien module → AC n'a été trouvé.")

    pos_sem, pos_ue, pos_mod, pos_ac = _compute_curricular_layout(semesters, show_ac_detail=True)

    fig = go.Figure()

    # ── Troncs : Semestre → UE ───────────────────────────────────────────
    tx, ty = [], []
    for (sl, uc), ux in pos_ue.items():
        tx.extend([pos_sem[sl], ux, None]); ty.extend([CURR_Y_SEM + 0.32, CURR_Y_UE - 0.26, None])
    if tx:
        fig.add_trace(go.Scatter(x=tx, y=ty, mode="lines",
            line=dict(color="#475569", width=2.2), opacity=0.5, hoverinfo="none", showlegend=False))

    # ── Tiges : UE → Module ────────────────────────────────────────────────
    tx2, ty2 = [], []
    for (sl, uc, mc), mx in pos_mod.items():
        tx2.extend([pos_ue[(sl, uc)], mx, None]); ty2.extend([CURR_Y_UE + 0.24, CURR_Y_MOD - 0.22, None])
    if tx2:
        fig.add_trace(go.Scatter(x=tx2, y=ty2, mode="lines",
            line=dict(color="#94A3B8", width=1.1), opacity=0.45, hoverinfo="none", showlegend=False))

    # ── Tiges : Module → AC ────────────────────────────────────────────────
    tx3, ty3 = [], []
    for (sl, uc, mc, ac), ax in pos_ac.items():
        tx3.extend([pos_mod[(sl, uc, mc)], ax, None]); ty3.extend([CURR_Y_MOD + 0.22, CURR_Y_AC - 0.14, None])
    if tx3:
        fig.add_trace(go.Scatter(x=tx3, y=ty3, mode="lines",
            line=dict(color="#CBD5E1", width=0.9), opacity=0.4, hoverinfo="none", showlegend=False))

    # ── AC : petits points — remplissage = compétence, contour = niveau ──────
    ac_code_sel = selected.get("ac_code") if _sel_get(selected, "type") == "ac" else None
    ax_, ay_, ahov, acd, asize, alw, afill, abrd = [], [], [], [], [], [], [], []
    for (sl, uc, mc, ac_code), x in pos_ac.items():
        ac = semesters[sl]["ues"][uc]["modules"][mc]["acs"][ac_code]
        cc = ac.get("competence_code")
        niv = ac.get("niveau")
        nk = _niv_key(niv)
        if cc:
            # Priorité au mapping unifié transmis par forested_forest.py
            # (même couleur que la forêt pédagogique) ; repli sur l'index
            # dérivé du code pour un usage autonome de ce module.
            if comp_color_index and cc in comp_color_index:
                idx = comp_color_index[cc] % len(PALETTE_ESS)
            else:
                idx = _comp_stable_color_index(cc)
            cfg = PALETTE_ESS[idx]
            fill = cfg["n2_fill"]
            border = _niv_border_color(cfg, nk)
        else:
            fill = CURR_AC_NEUTRAL_FILL
            border = _niv_border_color(None, nk)
        desc = ac.get("description", "")
        is_sel = ac_code == ac_code_sel
        ax_.append(x); ay_.append(CURR_Y_AC)
        ahov.append(
            f"<b>{ac_code}</b><br>Description : {desc[:100]}{'…' if len(desc) > 100 else ''}<br>"
            f"Compétence : {cc or '—'}<br>Niveau : {_NIV_LABEL[nk]}<br>"
            f"Module : {mc}<br>UE : {uc}<br>Semestre : {sl}"
        )
        acd.append({"type": "ac", "id": f"{sl}::{uc}::{mc}::{ac_code}",
                    "semester": sl, "ue_code": uc, "module_code": mc, "ac_code": ac_code})
        asize.append(CURR_AC_SEL_SIZE if is_sel else CURR_AC_BASE_SIZE)
        alw.append(_NIV_BORDER_W[nk])
        afill.append(fill)
        abrd.append(border)
    if ax_:
        fig.add_trace(go.Scatter(x=ax_, y=ay_, mode="markers",
            marker=dict(symbol="circle", size=asize, color=afill, line=dict(width=alw, color=abrd)),
            hovertext=ahov, hoverinfo="text",
            hoverlabel=dict(bgcolor="#1E293B", bordercolor="white", font=dict(color="white", size=12)),
            customdata=acd, showlegend=False, name="AC"))

    # ── Nœuds module (carré bleu) ──────────────────────────────────────────
    mx_, my_, mhov, mcd = [], [], [], []
    for (sl, uc, mc), x in pos_mod.items():
        ue = semesters[sl]["ues"][uc]; mod = ue["modules"][mc]
        n_ac = len(mod["acs"])
        comp_codes = sorted({a["competence_code"] for a in mod["acs"].values() if a.get("competence_code")})
        mx_.append(x); my_.append(CURR_Y_MOD)
        mhov.append(
            f"<b>{mc} — {mod['name']}</b><br>Semestre : {sl}<br>UE : {uc} — {ue['name']}<br>"
            f"AC liés : {n_ac}<br>Compétences couvertes : {', '.join(comp_codes) if comp_codes else '—'}<br>"
            f"🖱 Cliquez pour zoomer"
        )
        mcd.append({"type": "module", "id": f"{sl}::{uc}::{mc}", "semester": sl, "ue_code": uc, "module_code": mc})
    if mx_:
        fig.add_trace(go.Scatter(x=mx_, y=my_, mode="markers",
            marker=dict(symbol="square", size=14, color=CURR_MOD_COLOR["fill"],
                        line=dict(width=1.3, color=CURR_MOD_COLOR["border"])),
            hovertext=mhov, hoverinfo="text",
            hoverlabel=dict(bgcolor=CURR_MOD_COLOR["border"], bordercolor="white", font=dict(color="white", size=12)),
            customdata=mcd, showlegend=False, name="Modules"))

    # ── Nœuds UE (losange clair) ─────────────────────────────────────────────
    ux_, uy_, uhov, ucd = [], [], [], []
    for (sl, uc), x in pos_ue.items():
        ue = semesters[sl]["ues"][uc]
        n_mod = len(ue["modules"]); n_ac = sum(len(m["acs"]) for m in ue["modules"].values())
        ux_.append(x); uy_.append(CURR_Y_UE)
        uhov.append(f"<b>{uc} — {ue['name']}</b><br>Semestre : {sl}<br>Modules : {n_mod}<br>"
                     f"AC couverts : {n_ac}<br>🖱 Cliquez pour zoomer")
        ucd.append({"type": "ue", "id": f"{sl}::{uc}", "semester": sl, "ue_code": uc})
    if ux_:
        fig.add_trace(go.Scatter(x=ux_, y=uy_, mode="markers",
            marker=dict(symbol="diamond", size=18, color=CURR_UE_COLOR["fill"],
                        line=dict(width=1.4, color=CURR_UE_COLOR["border"])),
            hovertext=uhov, hoverinfo="text",
            hoverlabel=dict(bgcolor=CURR_UE_COLOR["border"], bordercolor="white", font=dict(color="#0F172A", size=12)),
            customdata=ucd, showlegend=False, name="UE"))

    # ── Racine : Semestre (losange sombre) ───────────────────────────────────
    hl_sem = selected.get("semester") if _sel_get(selected, "type") == "semester" else None
    sx, sy, shov, scd, stxt, ssz = [], [], [], [], [], []
    for sl, x in pos_sem.items():
        sem = semesters[sl]
        n_ue = len(sem["ues"])
        n_mod = sum(len(ue["modules"]) for ue in sem["ues"].values())
        n_ac = sum(len(m["acs"]) for ue in sem["ues"].values() for m in ue["modules"].values())
        sx.append(x); sy.append(CURR_Y_SEM)
        shov.append(f"<b>{sl}</b><br>UE : {n_ue}<br>Modules : {n_mod}<br>AC couverts : {n_ac}<br>🖱 Cliquez pour zoomer")
        scd.append({"type": "semester", "id": sl, "semester": sl})
        stxt.append(sl)
        ssz.append(30 if sl == hl_sem else 24)
    if sx:
        fig.add_trace(go.Scatter(x=sx, y=sy, mode="markers",
            marker=dict(symbol="diamond", size=ssz, color=CURR_SEM_COLOR["fill"],
                        line=dict(width=2.2, color=CURR_SEM_COLOR["border"])),
            hovertext=shov, hoverinfo="text",
            hoverlabel=dict(bgcolor=CURR_SEM_COLOR["border"], bordercolor="white", font=dict(color=CURR_SEM_COLOR["text"], size=12)),
            customdata=scd, showlegend=False))
        fig.add_trace(go.Scatter(x=sx, y=[CURR_Y_SEM - 0.46] * len(sx), mode="text",
            text=[f"<b>{t}</b>" for t in stxt], textposition="middle center",
            textfont=dict(size=10, color=CURR_SEM_COLOR["border"]), hoverinfo="none", showlegend=False))

    all_x = (list(pos_ac.values()) or list(pos_mod.values()) or list(pos_sem.values()) or [0])
    xmin, xmax = min(all_x) - 1.6, max(all_x) + 1.6

    shapes = [
        dict(type="rect", x0=xmin, x1=xmax, y0=CURR_Y_AC - 0.35, y1=CURR_Y_AC + 0.5,
             fillcolor="rgba(107,114,128,0.04)", line=dict(width=0), layer="below"),
        dict(type="rect", x0=xmin, x1=xmax, y0=CURR_Y_MOD - 0.4, y1=CURR_Y_MOD + 0.4,
             fillcolor="rgba(107,114,128,0.035)", line=dict(width=0), layer="below"),
        dict(type="rect", x0=xmin, x1=xmax, y0=CURR_Y_UE - 0.38, y1=CURR_Y_UE + 0.38,
             fillcolor="rgba(107,114,128,0.03)", line=dict(width=0), layer="below"),
    ]

    for y_val, lbl in [
        (CURR_Y_AC,  "AC"),
        (CURR_Y_MOD, "Modules"),
        (CURR_Y_UE,  "UE"),
        (CURR_Y_SEM, "Semestres"),
    ]:
        fig.add_annotation(xref="paper", x=-0.012, yref="y", y=y_val,
            text=f"<b>{lbl}</b>", showarrow=False, xanchor="right", yanchor="middle",
            font=dict(size=11, color="#475569"))

    x_min, x_max = _apply_min_x_span(xmin - 1.0, xmax + 1.0, min_x_span)

    kind = _sel_get(selected, "type")
    focus_lbl = ""
    if kind == "semester":
        focus_lbl = f" · <b>{selected.get('semester')}</b>"
    elif kind == "ue":
        focus_lbl = f" · <b>{selected.get('ue_code')}</b>"
    elif kind == "module":
        focus_lbl = f" · <b>{selected.get('module_code')}</b>"
    elif kind == "ac":
        focus_lbl = f" · <b>{selected.get('ac_code')}</b>"

    n_sem = len(semesters)
    n_ue = sum(len(sem["ues"]) for sem in semesters.values())
    fig.update_layout(
        title=dict(
            text=(f"<b>ForestED — Forêt curriculaire APC</b>"
                  f"<span style='color:#94A3B8;font-size:13px'>"
                  f" · Semestres · UE · modules · AC"
                  f" — {n_sem} semestre(s) · {n_ue} UE · {n_mod_total} modules · {n_ac_total} AC"
                  f"{focus_lbl}</span>"),
            x=0.01, y=0.98, font=dict(size=16, color="#0F172A")),
        height=760, paper_bgcolor="#F8FAFB", plot_bgcolor="#FFFFFF",
        showlegend=False, margin=dict(l=140, r=50, t=75, b=30),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[x_min, x_max]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=[-1.0, CURR_Y_AC + 0.9]),
        shapes=shapes, clickmode="event", hovermode="closest",
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  PANNEAU DE DÉTAIL
# ══════════════════════════════════════════════════════════════════════════════

def build_curricular_focus_panel(rows, selected):
    """
    Panneau latéral affiché sous le radio button, piloté par
    curricular-selected-node-store. Mirroir de build_focus_panel() côté
    pédagogique, avec son propre schéma de sélection (dict, pas tuple encodé
    en string).
    """
    if not selected or not isinstance(selected, dict):
        return html.Div()
    kind = selected.get("type")
    data = build_curricular_forest_data(rows)
    semesters = data["semesters"]

    def _tags(items, bg, color):
        return html.Div([
            html.Span(it, style={
                "backgroundColor": bg, "color": color, "borderRadius": "5px",
                "padding": "3px 8px", "fontSize": "11px",
                "marginRight": "5px", "marginBottom": "5px",
                "display": "inline-block",
            }) for it in items[:80]
        ], style={"display": "flex", "flexWrap": "wrap"})

    def _wrap(border, title, name, body):
        return html.Div([html.Div([
            html.Div([
                html.Span(style={"width": "10px", "height": "10px", "borderRadius": "2px",
                                  "backgroundColor": border, "display": "inline-block",
                                  "marginRight": "8px"}),
                html.Span(title, style={"fontWeight": "700", "fontSize": "14px", "color": "#0F172A"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),
            *([html.P(name, style={"fontSize": "13px", "color": "#475569",
                                    "fontStyle": "italic", "margin": "0 0 10px"})] if name else []),
            *body,
        ], style={"backgroundColor": "#FFFFFF", "border": "1px solid #E2E8F0",
                   "borderLeft": f"4px solid {border}", "borderRadius": "8px",
                   "padding": "14px 18px", "marginBottom": "14px",
                   "boxShadow": "0 2px 8px rgba(0,0,0,0.05)"})])

    if kind == "semester":
        sl = selected.get("semester") or selected.get("id")
        sem = semesters.get(sl)
        if not sem:
            return html.Div()
        n_ue = len(sem["ues"])
        n_mod = sum(len(u["modules"]) for u in sem["ues"].values())
        n_ac = sum(len(m["acs"]) for u in sem["ues"].values() for m in u["modules"].values())
        body = [
            html.P(f"{n_ue} UE · {n_mod} module(s) · {n_ac} AC",
                   style={"fontSize": "12px", "color": "#64748B", "margin": "0 0 10px"}),
            _tags(sorted(sem["ues"].keys()), "#E9EEF5", "#334155"),
        ]
        return _wrap(CURR_SEM_COLOR["border"], f"Semestre : {sl}", "", body)

    if kind == "ue":
        sl, uc = selected.get("semester"), selected.get("ue_code")
        sem = semesters.get(sl) or {}
        ue = (sem.get("ues") or {}).get(uc)
        if not ue:
            return html.Div()
        mods = sorted(ue["modules"].keys())
        n_ac = sum(len(m["acs"]) for m in ue["modules"].values())
        body = [
            html.P(f"{len(mods)} module(s) · {n_ac} AC",
                   style={"fontSize": "12px", "color": "#64748B", "margin": "0 0 10px"}),
            _tags(mods, "#DBEAFE", "#1E40AF"),
        ]
        return _wrap(CURR_UE_COLOR["border"], f"UE : {uc}", ue.get("name", ""), body)

    if kind in ("module", "ac"):
        sl, uc, mc = selected.get("semester"), selected.get("ue_code"), selected.get("module_code")
        sem = semesters.get(sl) or {}
        ue = (sem.get("ues") or {}).get(uc) or {}
        mod = (ue.get("modules") or {}).get(mc)
        if not mod:
            return html.Div()
        acs = mod["acs"]
        comp_codes = sorted({a["competence_code"] for a in acs.values() if a.get("competence_code")})
        body = [
            html.P(f"Semestre {sl} · UE {uc} · {len(acs)} AC",
                   style={"fontSize": "12px", "color": "#64748B", "margin": "0 0 10px"}),
        ]
        if comp_codes:
            body.append(_tags(comp_codes, "#DBEAFE", "#1E40AF"))

        ac_code_sel = selected.get("ac_code") if kind == "ac" else None
        for code, ac in sorted(acs.items()):
            emphasis = code == ac_code_sel
            niv_lbl = _NIV_LABEL[_niv_key(ac.get("niveau"))].split(" — ")[0]
            body.append(html.Div([
                html.Span(f"{code} · {niv_lbl}", style={
                    "fontWeight": "700" if emphasis else "600",
                    "fontSize": "12px", "color": "#0F172A" if emphasis else "#475569",
                }),
                html.P(ac.get("description", ""), style={
                    "fontSize": "11.5px", "color": "#64748B", "margin": "2px 0 8px",
                }),
            ], style={
                "padding": "6px 10px", "marginBottom": "4px",
                "backgroundColor": "#F8FAFC" if emphasis else "transparent",
                "borderRadius": "6px",
                "border": "1px solid #CBD5E1" if emphasis else "1px solid transparent",
            }))
        return _wrap(CURR_MOD_COLOR["border"], f"Module : {mc}", mod.get("name", ""), body)

    return html.Div()