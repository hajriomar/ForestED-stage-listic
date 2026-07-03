"""
forested_sunburst.py — ForestED : Sunburst APC
════════════════════════════════════════════════

Objectif
--------
Créer une visualisation circulaire et quantitative de la structure APC :

    Formation / référentiel
        -> Compétence
            -> Niveau de développement
                -> Apprentissage critique
                    -> Module / ressource / SAE

Principes data
--------------
- Le Sunburst est construit à partir des données déjà transformées par l'ETL.
- Aucune compétence, aucun parcours et aucun code module n'est hardcodé.
- Les modules sont toujours affichés dans l'anneau externe.
- La taille d'un AC correspond au nombre de modules uniques liés à cet AC.
- Les tailles des niveaux et compétences sont calculées automatiquement.

Architecture des callbacks (v2)
--------------------------------
- clickData NE régénère PLUS la figure directement.
- Le clic met à jour un dcc.Store (sunburst-selected-competence-store).
- La figure dépend du Store, pas de clickData.
- L'ordre des compétences est calculé GLOBALEMENT avant tout filtrage par
  compétence, ce qui garantit la stabilité des couleurs.
- Le nœud racine en vue détail reçoit la couleur de la compétence (pas noir).
"""
import re
from dash import html, dcc, Input, Output, State, no_update, ctx
import plotly.graph_objects as go

from forested_palette import PALETTE_COMPETENCES
from forested_sunburst_semester import (
    create_semester_sunburst_figure,
    get_semester_node_info,
    build_semester_nodes,
    SEMESTER_RING_COLORS,
)
from forested_visualisations import (
    PAGE_STYLE,
    CARD_STYLE,
    LABEL_STYLE,
    get_programme_options,
    get_selected_data,
    build_visualisation_rows,
    get_specialite_options_from_rows,
    filter_rows_by_specialite,
    sort_semester,
    empty_figure,
)


# ══════════════════════════════════════════════════════════════════════════════
#  STYLE LOCAL
# ══════════════════════════════════════════════════════════════════════════════

STAT_LABEL_STYLE = {
    "fontSize": "11px",
    "fontWeight": "700",
    "color": "#64748B",
    "textTransform": "uppercase",
    "letterSpacing": "0.6px",
    "marginBottom": "5px",
}

STAT_VALUE_STYLE = {
    "fontSize": "27px",
    "fontWeight": "800",
    "color": "#0F172A",
    "lineHeight": "1.1",
}


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITAIRES DATA
# ══════════════════════════════════════════════════════════════════════════════

def _extract_ac_order(ac_code):
    if not ac_code:
        return 9999
    match = re.search(r"AC(\d+)$", str(ac_code))
    if match:
        return int(match.group(1))
    return 9999


def _clean(value, default="Non renseigné"):
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _safe_int(value, default=99):
    try:
        return int(value)
    except Exception:
        return default


def _shorten(text, max_len=68):
    text = _clean(text, "")
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _hex_to_rgb(hex_color):
    """Convertit une couleur hexadécimale en tuple RGB."""
    if not hex_color:
        return 255, 255, 255
    hex_color = str(hex_color).strip().lstrip("#")
    if len(hex_color) != 6:
        return 255, 255, 255
    try:
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return 255, 255, 255


def _relative_luminance(hex_color):
    """Calcule la luminance relative WCAG d'une couleur (0 = noir, 1 = blanc)."""
    r, g, b = _hex_to_rgb(hex_color)
    def linearize(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def _text_color_for_bg(bg_color):
    """
    Retourne '#FFFFFF' sur fond sombre, '#0F172A' sur fond clair.
    Seuil à 0.25 : compromis entre WCAG (0.179) et lisibilité dataviz.
    """
    return "#FFFFFF" if _relative_luminance(bg_color) < 0.25 else "#0F172A"


def _extract_ac_label(ac_code, ac_description, max_desc_len=38):
    match = re.search(r"(AC\d+)$", str(ac_code))
    suffix = match.group(1) if match else _clean(ac_code, ac_code)
    description = _clean(ac_description, "")
    if not description or description == "Non renseigné":
        return suffix
    return f"{suffix} : {_shorten(description, max_desc_len)}"


def _extract_ac_suffix(ac_code):
    match = re.search(r"(AC\d+)$", str(ac_code))
    return match.group(1) if match else _clean(ac_code, ac_code)


def _module_display_label(module_code, module_name, max_len=15):
    name = _clean(module_name, "")
    if not name or name == "Non renseigné" or name == module_code:
        return _shorten(module_code, max_len)
    return _shorten(name, max_len)


def _competence_color(competence_code, competence_order):
    try:
        index = competence_order.index(competence_code)
    except ValueError:
        index = 0
    return PALETTE_COMPETENCES[index % len(PALETTE_COMPETENCES)]


def _node_color(node_id, node_meta, competence_order):
    meta = node_meta.get(node_id, {})
    node_type = meta.get("type")
    comp_code = meta.get("competence_code")
    if node_type == "root" and not comp_code:
        return "#0F172A"
    if not comp_code:
        return "#0F172A"
    scheme = _competence_color(comp_code, competence_order)
    if node_type in ("competence", "competence_root"):
        return scheme["root"]
    # Centre de la vue AC detail : on utilise la couleur du niveau de l'AC
    # pour que n1 soit clair, n2 medium et n3 foncé — cohérent avec les anneaux.
    if node_type == "ac_root":
        niveau = _safe_int(meta.get("niveau"), default=2)
        if niveau == 1:
            return scheme["n1"]
        if niveau == 3:
            return scheme["n3"]
        return scheme["n2"]
    niveau = _safe_int(meta.get("niveau"), default=1)
    if niveau == 1:
        return scheme["n1"]
    if niveau == 2:
        return scheme["n2"]
    if niveau == 3:
        return scheme["n3"]
    return scheme["n2"]


def _format_semestre(value):
    if value is None or value == "all":
        return "Tous les semestres"
    text = str(value)
    if text.upper().startswith("S"):
        return text
    return f"S{text}"


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITAIRES COMPÉTENCES
# ══════════════════════════════════════════════════════════════════════════════

def get_competence_name_from_rows(rows, competence_code):
    for row in rows or []:
        if row.get("competence_code") == competence_code:
            name = row.get("competence_name")
            if name:
                return name
    return competence_code


def get_competence_order(rows):
    return sorted(
        {
            row.get("competence_code")
            for row in rows or []
            if row.get("competence_code")
        }
    )


def filter_rows_by_competence(rows, competence_code):
    if not competence_code:
        return rows
    return [
        row
        for row in rows or []
        if row.get("competence_code") == competence_code
    ]


def filter_rows_by_ac(rows, ac_code):
    """Garde uniquement les lignes liées à un AC donné."""
    if not ac_code:
        return rows
    return [
        row
        for row in rows or []
        if _clean(row.get("ac_code"), "") == ac_code
    ]


def build_ac_detail_nodes(rows, ac_code, competence_order=None):
    """
    Construit les nœuds du Sunburst pour la vue détail d'un AC.

    Structure :
        Centre (root) : "AC3 : description courte"  ← label enrichi spécifique à cette vue
        Anneau externe : modules liés à cet AC

    Ce mode est déclenché par le callback (Store), pas par la navigation
    native de Plotly — c'est ce qui permet d'avoir un label différent au centre.
    """
    ac_description = ""
    comp_code = ""
    niveau_ac = None
    modules = {}

    for row in rows or []:
        if _clean(row.get("ac_code"), "") != ac_code:
            continue
        ac_description = _clean(row.get("ac_description"), ac_code)
        comp_code = _clean(row.get("competence_code"), "")
        # Capturer le niveau dès la première ligne valide
        if niveau_ac is None and row.get("niveau") is not None:
            niveau_ac = row.get("niveau")
        module_code = _clean(row.get("module_code") or row.get("module_id"), "")
        module_name = _clean(row.get("module_name"), module_code)
        if module_code:
            modules[module_code] = module_name

    root_id = "ROOT::APC"
    # Label enrichi réservé au centre de cette vue dédiée
    root_label = _extract_ac_label(ac_code, ac_description, max_desc_len=40)

    node_parent = {root_id: ""}
    node_label = {root_id: root_label}
    node_value = {}
    node_hover = {
        root_id: (
            f"<b>{root_label}</b><br>"
            f"<b>Code complet :</b> {ac_code}<br>"
            f"<b>Compétence :</b> {comp_code}<br>"
            f"<b>Niveau :</b> {niveau_ac if niveau_ac is not None else 'Non renseigné'}"
        )
    }
    node_meta = {
        root_id: {
            "type": "ac_root",
            "competence_code": comp_code,
            # Le niveau est stocké ici pour que _node_color choisisse n1/n2/n3
            "niveau": niveau_ac,
        }
    }

    if competence_order is None:
        competence_order = [comp_code] if comp_code else []

    for module_code, module_name in sorted(modules.items()):
        module_id = f"MOD::AC::{ac_code}::{module_code}"
        node_parent[module_id] = root_id
        node_label[module_id] = _module_display_label(module_code, module_name)
        node_value[module_id] = 1
        node_hover[module_id] = (
            f"<b>{module_name}</b><br>"
            f"<b>Code :</b> {module_code}<br>"
            f"<b>AC :</b> {ac_code}<br>"
            f"<b>Compétence :</b> {comp_code}"
        )
        node_meta[module_id] = {
            "type": "module",
            "competence_code": comp_code,
            "niveau": None,
        }

    node_value[root_id] = len(modules)

    ids = list(node_parent.keys())
    colors = [_node_color(node_id, node_meta, competence_order) for node_id in ids]
    text_colors = [_text_color_for_bg(color) for color in colors]

    return {
        "ids": ids,
        "labels": [node_label[node_id] for node_id in ids],
        "parents": [node_parent[node_id] for node_id in ids],
        "values": [node_value.get(node_id, 0) for node_id in ids],
        "hovertexts": [node_hover.get(node_id, node_label[node_id]) for node_id in ids],
        "colors": colors,
        "text_colors": text_colors,
        "node_meta": node_meta,
        "ac_index": {},
    }


def create_ac_detail_figure(rows, ac_code, semester="all", competence_order=None):
    """
    Crée la figure Plotly Sunburst pour la vue détail d'un AC.

    Centre = "AC3 : description" (label enrichi, possible car figure régénérée).
    Anneau = modules liés.
    Navigation retour : clic sur le centre (ROOT::) → callback remet ac_store à None.
    """
    if not rows:
        return empty_figure("Aucune donnée disponible pour cet AC")

    data = build_ac_detail_nodes(rows, ac_code, competence_order=competence_order)

    if len(data["ids"]) <= 1:
        return empty_figure("Aucun module lié à cet AC")

    title_suffix = _format_semestre(semester)

    fig = go.Figure(
        go.Sunburst(
            ids=data["ids"],
            labels=data["labels"],
            parents=data["parents"],
            values=data["values"],
            branchvalues="total",
            sort=False,
            marker=dict(
                colors=data["colors"],
                line=dict(color="#FFFFFF", width=1.4),
            ),
            insidetextfont=dict(
                color=data["text_colors"],
                # Pas de taille forcée : Plotly auto-dimensionne selon la surface.
                # Le centre (grand) aura un texte plus lisible.
            ),
            hovertext=data["hovertexts"],
            hoverinfo="text",
            insidetextorientation="radial",
            maxdepth=3,
        )
    )

    fig.update_traces(
        textinfo="label",
        hoverlabel=dict(
            bgcolor="#0F172A",
            font=dict(color="#FFFFFF", size=12),
        ),
    )

    fig.update_layout(
        title=dict(
            text=(
                "<b>Sunburst approche par compétence</b><br>"
                f"<span style='font-size:12px;color:#64748B'>"
                f"AC → modules · {title_suffix}"
                "</span>"
            ),
            x=0.02,
            y=0.98,
            font=dict(size=18, color="#0F172A", family="Segoe UI, sans-serif"),
        ),
        height=940,
        paper_bgcolor="#F8FAFB",
        margin=dict(t=80, l=20, r=20, b=20),
        uniformtext=dict(minsize=8, mode="hide"),
        uirevision=f"ac-{ac_code}-{semester}",
    )

    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  CONSTRUCTION DU SUNBURST
# ══════════════════════════════════════════════════════════════════════════════

def build_sunburst_nodes(
    rows,
    root_label="APC",
    show_levels=False,
    selected_competence_code=None,
    competence_order=None,
):
    root_id = "ROOT::APC"
    node_parent = {root_id: ""}
    node_label = {root_id: root_label}
    node_value = {}
    node_hover = {root_id: f"<b>{root_label}</b><br>Structure APC"}
    node_meta = {
        root_id: {
            "type": "competence_root" if selected_competence_code else "root",
            "competence_code": selected_competence_code,
            "niveau": None,
        }
    }

    ac_index = {}

    for row in rows or []:
        comp_code = _clean(row.get("competence_code"), "")
        ac_code = _clean(row.get("ac_code"), "")
        module_code = _clean(
            row.get("module_code") or row.get("module_id"),
            ""
        )
        # FIX : on accepte les lignes sans module_code (AC sans module référencé).
        # Cela permet d'afficher Compétence → Niveau → AC même quand le
        # fichier compétences ne liste pas de modules pour cet AC (ex: BUT INFO).
        if not comp_code or not ac_code:
            continue

        niveau = row.get("niveau")
        comp_name = _clean(row.get("competence_name"), comp_code)
        ac_description = _clean(row.get("ac_description"), ac_code)
        module_name = _clean(row.get("module_name"), module_code)

        comp_id = f"COMP::{comp_code}"
        niveau_id = f"NIV::{comp_code}::N{niveau}"
        ac_id = f"AC::{ac_code}"

        if ac_id not in ac_index:
            ac_index[ac_id] = {
                "competence_id": comp_id,
                "competence_code": comp_code,
                "competence_name": comp_name,
                "niveau_id": niveau_id,
                "niveau": niveau,
                "ac_code": ac_code,
                "ac_description": ac_description,
                "modules": {},
            }

        # N'ajouter le module que s'il existe réellement
        if module_code:
            ac_index[ac_id]["modules"][module_code] = module_name

    if competence_order is None:
        competence_order = sorted(
            {
                info["competence_code"]
                for info in ac_index.values()
            }
        )

    sorted_ac_items = sorted(
        ac_index.items(),
        key=lambda item: (
            competence_order.index(item[1]["competence_code"])
            if item[1]["competence_code"] in competence_order else 999,
            _safe_int(item[1]["niveau"], default=99),
            _extract_ac_order(item[1]["ac_code"]),
            item[1]["ac_code"],
        ),
    )

    for ac_id, info in sorted_ac_items:
        comp_id = info["competence_id"]
        niveau_id = info["niveau_id"]
        comp_code = info["competence_code"]
        niveau = info["niveau"]

        if show_levels and selected_competence_code:
            if niveau_id not in node_parent:
                node_parent[niveau_id] = root_id
                node_label[niveau_id] = f"Niveau {niveau}"
                node_hover[niveau_id] = (
                    f"<b>{comp_code} — Niveau {niveau}</b><br>"
                    f"{info['competence_name']}"
                )
                node_meta[niveau_id] = {
                    "type": "niveau",
                    "competence_code": comp_code,
                    "niveau": niveau,
                }
            ac_parent = niveau_id
        else:
            if comp_id not in node_parent:
                node_parent[comp_id] = root_id
                node_label[comp_id] = _clean(comp_code, comp_code)
                node_hover[comp_id] = (
                    f"<b>{comp_code}</b><br>"
                    f"<b>Nom :</b> {info['competence_name']}"
                )
                node_meta[comp_id] = {
                    "type": "competence",
                    "competence_code": comp_code,
                    "niveau": None,
                }
            ac_parent = comp_id

        module_count = len(info["modules"])

        node_parent[ac_id] = ac_parent
        # Label court dans l'anneau (ex: "AC3").
        # La description complète est disponible dans le hover et le panneau détail.
        # Plotly ne permet pas d'avoir un label différent selon la position du nœud
        # (anneau vs centre) — un seul tableau labels pour les deux états.
        node_label[ac_id] = _extract_ac_suffix(info["ac_code"])
        node_value[ac_id] = max(module_count, 1)
        node_hover[ac_id] = (
            f"<b>{_extract_ac_label(info['ac_code'], info['ac_description'], max_desc_len=80)}</b><br>"
            f"<b>Code :</b> {info['ac_code']}<br>"
            f"<b>Niveau :</b> {niveau}<br>"
            f"<b>Modules liés :</b> {module_count}"
        )
        node_meta[ac_id] = {
            "type": "ac",
            "competence_code": comp_code,
            "niveau": niveau,
        }

        for module_code, module_name in sorted(info["modules"].items()):
            module_id = f"MOD::{ac_id}::{module_code}"
            node_parent[module_id] = ac_id
            node_label[module_id] = _module_display_label(module_code, module_name)
            node_value[module_id] = 1
            node_hover[module_id] = (
                f"<b>{module_name}</b><br>"
                f"<b>Code :</b> {module_code}<br>"
                f"<b>Compétence :</b> {comp_code}<br>"
                f"<b>AC parent :</b> {info['ac_code']}<br>"
                f"<b>Niveau :</b> {niveau}"
            )
            node_meta[module_id] = {
                "type": "module",
                "competence_code": comp_code,
                "niveau": niveau,
            }

    # Calcul des valeurs agrégées pour les nœuds non-feuilles
    for node_id in reversed(list(node_parent.keys())):
        if node_id in node_value:
            continue
        children = [
            child_id
            for child_id, parent_id in node_parent.items()
            if parent_id == node_id
        ]
        node_value[node_id] = sum(
            node_value.get(child_id, 0)
            for child_id in children
        )

    ids = list(node_parent.keys())

    # CHANGEMENT 2 : calcul des couleurs + couleurs de texte
    colors = [
        _node_color(node_id, node_meta, competence_order)
        for node_id in ids
    ]

    text_colors = [
        _text_color_for_bg(color)
        for color in colors
    ]

    return {
        "ids": ids,
        "labels": [node_label[node_id] for node_id in ids],
        "parents": [node_parent[node_id] for node_id in ids],
        "values": [node_value.get(node_id, 0) for node_id in ids],
        "hovertexts": [node_hover.get(node_id, node_label[node_id]) for node_id in ids],
        "colors": colors,
        "text_colors": text_colors,
        "node_meta": node_meta,
        "ac_index": ac_index,
    }


def create_sunburst_figure(
    rows,
    selected_programme=None,
    semester="all",
    show_levels=False,
    selected_competence_code=None,
    competence_order=None,
):
    if not rows:
        return empty_figure("Aucune donnée disponible pour le Sunburst APC")

    root_label = "APC"

    if selected_competence_code:
        root_label = get_competence_name_from_rows(
            rows,
            selected_competence_code
        )
    elif selected_programme:
        root_label = selected_programme.split("::")[-1]

    data = build_sunburst_nodes(
        rows,
        root_label=root_label,
        show_levels=show_levels,
        selected_competence_code=selected_competence_code,
        competence_order=competence_order,
    )

    if len(data["ids"]) <= 1:
        return empty_figure(
            "Aucun lien compétence → AC → module détecté"
        )

    title_suffix = _format_semestre(semester)

    # CHANGEMENT 3 : ajout de insidetextfont avec les couleurs calculées
    fig = go.Figure(
        go.Sunburst(
            ids=data["ids"],
            labels=data["labels"],
            parents=data["parents"],
            values=data["values"],
            branchvalues="total",
            sort=False,
            marker=dict(
                colors=data["colors"],
                line=dict(
                    color="#FFFFFF",
                    width=1.4,
                ),
            ),
            insidetextfont=dict(
                color=data["text_colors"],
                size=11,
            ),
            hovertext=data["hovertexts"],
            hoverinfo="text",
            insidetextorientation="radial",
            maxdepth=4,
        )
    )

    fig.update_traces(
        textinfo="label",
        hoverlabel=dict(
            bgcolor="#0F172A",
            font=dict(
                color="#FFFFFF",
                size=12
            ),
        ),
    )

    subtitle = (
        f"Compétences → niveaux → AC → modules · {title_suffix}"
        if show_levels
        else f"Compétences → AC → modules · {title_suffix}"
    )

    fig.update_layout(
        title=dict(
            text=(
                "<b>Sunburst approche par compétence</b><br>"
                f"<span style='font-size:12px;color:#64748B'>"
                f"{subtitle}"
                "</span>"
            ),
            x=0.02,
            y=0.98,
            font=dict(
                size=18,
                color="#0F172A",
                family="Segoe UI, sans-serif"
            ),
        ),
        height=940,
        paper_bgcolor="#F8FAFB",
        margin=dict(t=80, l=20, r=20, b=20),
        uniformtext=dict(minsize=8, mode="hide"),
        uirevision=f"{selected_programme}-{semester}-{selected_competence_code}",
    )

    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  PANNEAU DÉTAIL AU CLIC
# ══════════════════════════════════════════════════════════════════════════════

def get_clicked_node_id(click_data):
    if not click_data:
        return None
    points = click_data.get("points", [])
    if not points:
        return None
    return points[0].get("id")


def build_detail_index(rows):
    index = {
        "root": {
            "competences": set(),
            "niveaux": set(),
            "acs": set(),
            "modules": set(),
        },
        "competences": {},
        "niveaux": {},
        "acs": {},
        "modules": {},
    }

    for row in rows or []:
        comp_code = _clean(row.get("competence_code"), "")
        comp_name = _clean(row.get("competence_name"), comp_code)
        niveau = row.get("niveau")
        ac_code = _clean(row.get("ac_code"), "")
        ac_description = _clean(row.get("ac_description"), ac_code)
        module_code = _clean(
            row.get("module_code") or row.get("module_id"),
            ""
        )
        module_name = _clean(row.get("module_name"), module_code)
        semestre = row.get("semestre")
        specialite = (
            row.get("specialite")
            or row.get("parcours")
            or row.get("sous_classification")
            or row.get("sous_classification_code")
        )

        # FIX : accepter les lignes sans module_code (AC sans module)
        if not comp_code or not ac_code:
            continue

        comp_id = f"COMP::{comp_code}"
        niveau_id = f"NIV::{comp_code}::N{niveau}"
        ac_id = f"AC::{ac_code}"
        module_id = f"MOD::{ac_id}::{module_code}" if module_code else None

        index["root"]["competences"].add(comp_code)
        index["root"]["niveaux"].add((comp_code, niveau))
        index["root"]["acs"].add(ac_code)
        if module_code:
            index["root"]["modules"].add(module_code)

        if comp_id not in index["competences"]:
            index["competences"][comp_id] = {
                "code": comp_code,
                "nom": comp_name,
                "niveaux": set(),
                "acs": set(),
                "modules": set(),
                "semestres": set(),
                "specialites": set(),
            }
        index["competences"][comp_id]["niveaux"].add(niveau)
        index["competences"][comp_id]["acs"].add(ac_code)
        if module_code:
            index["competences"][comp_id]["modules"].add(module_code)
        if semestre is not None:
            index["competences"][comp_id]["semestres"].add(semestre)
        if specialite:
            index["competences"][comp_id]["specialites"].add(specialite)

        if niveau_id not in index["niveaux"]:
            index["niveaux"][niveau_id] = {
                "competence_code": comp_code,
                "competence_nom": comp_name,
                "niveau": niveau,
                "acs": set(),
                "modules": set(),
                "semestres": set(),
            }
        index["niveaux"][niveau_id]["acs"].add(ac_code)
        if module_code:
            index["niveaux"][niveau_id]["modules"].add(module_code)
        if semestre is not None:
            index["niveaux"][niveau_id]["semestres"].add(semestre)

        if ac_id not in index["acs"]:
            index["acs"][ac_id] = {
                "code": ac_code,
                "description": ac_description,
                "competence_code": comp_code,
                "competence_nom": comp_name,
                "niveau": niveau,
                "modules": {},
                "semestres": set(),
            }
        if module_code:
            index["acs"][ac_id]["modules"][module_code] = module_name
        if semestre is not None:
            index["acs"][ac_id]["semestres"].add(semestre)

        if module_code and module_id:
            index["modules"][module_id] = {
                "code": module_code,
                "nom": module_name,
                "ac_code": ac_code,
                "ac_description": ac_description,
                "competence_code": comp_code,
                "competence_nom": comp_name,
                "niveau": niveau,
                "semestre": semestre,
            }

    return index


def detail_line(label, value):
    return html.Div(
        [
            html.Div(
                label,
                style={
                    "fontSize": "11px",
                    "fontWeight": "800",
                    "color": "#64748B",
                    "textTransform": "uppercase",
                    "letterSpacing": "0.5px",
                    "marginBottom": "2px",
                },
            ),
            html.Div(
                value,
                style={
                    "fontSize": "13px",
                    "fontWeight": "600",
                    "color": "#0F172A",
                    "lineHeight": "1.35",
                },
            ),
        ],
        style={"marginBottom": "12px"},
    )


def tag(text, bg="#F1F5F9", color="#334155"):
    return html.Span(
        text,
        style={
            "display": "inline-block",
            "backgroundColor": bg,
            "color": color,
            "borderRadius": "999px",
            "padding": "3px 9px",
            "fontSize": "11px",
            "fontWeight": "600",
            "marginRight": "5px",
            "marginBottom": "5px",
        },
    )


def module_badges(modules, max_items=40):
    if isinstance(modules, dict):
        modules = list(modules.keys())
    modules = sorted(list(modules or []))
    if not modules:
        return html.P(
            "Aucun module lié.",
            style={"fontSize": "12px", "color": "#94A3B8", "margin": "0"},
        )
    visible_modules = modules[:max_items]
    hidden_count = max(len(modules) - max_items, 0)
    return html.Div(
        [
            html.Div([tag(module, "#DBEAFE", "#1E3A8A") for module in visible_modules]),
            html.Div(
                f"+ {hidden_count} autre(s) module(s)" if hidden_count > 0 else "",
                style={"fontSize": "11px", "color": "#64748B", "fontWeight": "600", "marginTop": "6px"},
            ),
        ]
    )


def build_empty_detail_panel():
    return html.Div(
        [
            html.H3(
                "Détail de la sélection",
                style={"margin": "0 0 8px", "fontSize": "17px", "color": "#0F172A"},
            ),
            html.P(
                "Clique sur une compétence, un niveau, un AC ou un module dans le Sunburst pour afficher le détail ici.",
                style={"fontSize": "13px", "color": "#64748B", "lineHeight": "1.5", "margin": "0 0 14px"},
            ),
            html.Div(
                [
                    html.Div("Lecture", style=STAT_LABEL_STYLE),
                    html.P(
                        "La taille d'un segment représente le nombre de modules liés. Une zone plus grande signifie donc une couverture pédagogique plus forte dans les données.",
                        style={"fontSize": "12px", "color": "#334155", "lineHeight": "1.5", "margin": "0"},
                    ),
                ],
                style={
                    "backgroundColor": "#F8FAFC",
                    "border": "1px solid #E2E8F0",
                    "borderRadius": "10px",
                    "padding": "12px",
                },
            ),
        ],
        style={**CARD_STYLE, "height": "100%", "marginBottom": 0},
    )


def build_selection_detail_panel(rows, click_data):
    node_id = get_clicked_node_id(click_data)
    if not node_id:
        return build_empty_detail_panel()

    index = build_detail_index(rows)

    if node_id.startswith("ROOT::"):
        return html.Div(
            [
                html.H3("Vue globale APC", style={"margin": "0 0 12px", "fontSize": "17px", "color": "#0F172A"}),
                detail_line("Compétences", len(index["root"]["competences"])),
                detail_line("Niveaux", len(index["root"]["niveaux"])),
                detail_line("AC", len(index["root"]["acs"])),
                detail_line("Modules liés", len(index["root"]["modules"])),
                html.H4("Interprétation", style={"fontSize": "13px", "margin": "14px 0 6px", "color": "#0F172A"}),
                html.P(
                    "Cette vue permet de comparer la couverture pédagogique globale des compétences par les modules, ressources ou SAE.",
                    style={"fontSize": "12px", "color": "#64748B", "lineHeight": "1.5"},
                ),
            ],
            style={**CARD_STYLE, "height": "100%", "marginBottom": 0},
        )

    if node_id.startswith("COMP::"):
        item = index["competences"].get(node_id)
        if not item:
            return build_empty_detail_panel()
        return html.Div(
            [
                html.H3("Compétence sélectionnée", style={"margin": "0 0 12px", "fontSize": "17px", "color": "#0F172A"}),
                detail_line("Code", item["code"]),
                detail_line("Nom", item["nom"]),
                detail_line("Niveaux", len(item["niveaux"])),
                detail_line("AC liés", len(item["acs"])),
                detail_line("Modules liés", len(item["modules"])),
                detail_line(
                    "Semestres",
                    ", ".join(map(str, sorted(item["semestres"], key=sort_semester))) if item["semestres"] else "Non renseigné"
                ),
                html.H4("Modules liés", style={"fontSize": "13px", "margin": "14px 0 8px", "color": "#0F172A"}),
                module_badges(item["modules"]),
            ],
            style={**CARD_STYLE, "height": "100%", "marginBottom": 0, "overflowY": "auto"},
        )

    if node_id.startswith("NIV::"):
        item = index["niveaux"].get(node_id)
        if not item:
            return build_empty_detail_panel()
        return html.Div(
            [
                html.H3("Niveau sélectionné", style={"margin": "0 0 12px", "fontSize": "17px", "color": "#0F172A"}),
                detail_line("Compétence", item["competence_code"]),
                detail_line("Nom compétence", item["competence_nom"]),
                detail_line("Niveau", item["niveau"]),
                detail_line("AC liés", len(item["acs"])),
                detail_line("Modules liés", len(item["modules"])),
                html.H4("Modules liés", style={"fontSize": "13px", "margin": "14px 0 8px", "color": "#0F172A"}),
                module_badges(item["modules"]),
            ],
            style={**CARD_STYLE, "height": "100%", "marginBottom": 0, "overflowY": "auto"},
        )

    if node_id.startswith("AC::"):
        item = index["acs"].get(node_id)
        if not item:
            return build_empty_detail_panel()
        return html.Div(
            [
                html.H3("Apprentissage critique sélectionné", style={"margin": "0 0 12px", "fontSize": "17px", "color": "#0F172A"}),
                detail_line("AC", item["code"]),
                detail_line("Compétence", item["competence_code"]),
                detail_line("Niveau", item["niveau"]),
                detail_line("Modules liés", len(item["modules"])),
                html.H4("Description", style={"fontSize": "13px", "margin": "14px 0 6px", "color": "#0F172A"}),
                html.P(
                    item["description"],
                    style={
                        "fontSize": "12px", "color": "#334155", "lineHeight": "1.5",
                        "backgroundColor": "#F8FAFC", "border": "1px solid #E2E8F0",
                        "borderRadius": "10px", "padding": "10px",
                    },
                ),
                html.H4("Modules liés", style={"fontSize": "13px", "margin": "14px 0 8px", "color": "#0F172A"}),
                module_badges(item["modules"]),
            ],
            style={**CARD_STYLE, "height": "100%", "marginBottom": 0, "overflowY": "auto"},
        )

    if node_id.startswith("MOD::"):
        item = index["modules"].get(node_id)
        if not item:
            return build_empty_detail_panel()
        return html.Div(
            [
                html.H3("Module sélectionné", style={"margin": "0 0 12px", "fontSize": "17px", "color": "#0F172A"}),
                detail_line("Code module", item["code"]),
                detail_line("Nom module", item["nom"]),
                detail_line("AC parent", item["ac_code"]),
                detail_line("Compétence", item["competence_code"]),
                detail_line("Niveau", item["niveau"]),
                detail_line("Semestre", item["semestre"] if item["semestre"] is not None else "Non renseigné"),
                html.H4("AC associé", style={"fontSize": "13px", "margin": "14px 0 6px", "color": "#0F172A"}),
                html.P(
                    item["ac_description"],
                    style={
                        "fontSize": "12px", "color": "#334155", "lineHeight": "1.5",
                        "backgroundColor": "#F8FAFC", "border": "1px solid #E2E8F0",
                        "borderRadius": "10px", "padding": "10px",
                    },
                ),
            ],
            style={**CARD_STYLE, "height": "100%", "marginBottom": 0, "overflowY": "auto"},
        )

    return build_empty_detail_panel()


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT DASH
# ══════════════════════════════════════════════════════════════════════════════

programme_options = get_programme_options()

forested_sunburst_layout = html.Div(
    [
        html.Div(
            [
                html.Div(
                    [
                        html.Span("☀️", style={"fontSize": "34px", "marginRight": "12px"}),
                        html.Div(
                            [
                                html.H1(
                                    "Sunburst APC",
                                    style={
                                        "color": "#0F172A",
                                        "fontSize": "28px",
                                        "fontWeight": "700",
                                        "margin": "0 0 3px",
                                        "fontFamily": "Segoe UI, sans-serif",
                                    },
                                ),
                                html.P(
                                    "Analyse circulaire de la couverture compétences → niveaux → AC → modules.",
                                    style={"color": "#64748B", "fontSize": "13px", "margin": "0"},
                                ),
                            ]
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center"},
                )
            ],
            style={"marginBottom": "18px"},
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Label("Formation", style=LABEL_STYLE),
                        dcc.Dropdown(
                            id="sunburst-programme-selector",
                            options=programme_options,
                            value=None,
                            clearable=False,
                            style={"fontSize": "14px"},
                        ),
                    ],
                    style={"width": "38%", "minWidth": "250px"},
                ),
                html.Div(
                    [
                        html.Label("Semestre", style=LABEL_STYLE),
                        dcc.Dropdown(
                            id="sunburst-semester-filter",
                            options=[{"label": "Tous les semestres", "value": "all"}],
                            value="all",
                            clearable=False,
                            style={"fontSize": "14px"},
                        ),
                    ],
                    style={"width": "18%", "minWidth": "150px"},
                ),
                html.Div(
                    [
                        html.Label("Spécialité / parcours", style=LABEL_STYLE),
                        dcc.Dropdown(
                            id="sunburst-specialite-filter",
                            options=[{"label": "Toutes les spécialités", "value": "all"}],
                            value="all",
                            clearable=False,
                            style={"fontSize": "14px"},
                        ),
                    ],
                    style={"width": "24%", "minWidth": "210px"},
                ),
                html.Div(
                    [
                        html.Label("Lecture", style=LABEL_STYLE),
                        html.Div(
                            "Taille = modules liés · niveaux visibles après sélection d'une compétence",
                            style={
                                "fontSize": "12px",
                                "fontWeight": "600",
                                "color": "#334155",
                                "backgroundColor": "#F1F5F9",
                                "border": "1px solid #E2E8F0",
                                "borderRadius": "999px",
                                "padding": "8px 12px",
                            },
                        ),
                    ],
                    style={"minWidth": "260px"},
                ),
            ],
            style={**CARD_STYLE, "display": "flex", "alignItems": "flex-end", "flexWrap": "wrap", "gap": "16px"},
        ),
        dcc.Store(id="sunburst-rows-store"),
        dcc.Store(id="sunburst-selected-competence-store", data=None),
        dcc.Store(id="sunburst-selected-ac-store", data=None),
        # Store de l'onglet actif : "apc" ou "semester"
        dcc.Store(id="sunburst-active-tab", data="apc"),

        # ── Navigation entre les deux vues ────────────────────────────────
        html.Div(
            [
                html.Div(
                    "Vue :",
                    style={
                        "fontSize": "11px",
                        "fontWeight": "700",
                        "color": "#64748B",
                        "textTransform": "uppercase",
                        "letterSpacing": "0.8px",
                        "marginRight": "12px",
                        "alignSelf": "center",
                    },
                ),
                dcc.RadioItems(
                    id="sunburst-view-selector",
                    options=[
                        {"label": "  ☀️  APC par compétence", "value": "apc"},
                        {"label": "  📅  Distribution semestrielle", "value": "semester"},
                    ],
                    value="apc",
                    inline=True,
                    inputStyle={"marginRight": "5px"},
                    labelStyle={
                        "marginRight": "24px",
                        "fontSize": "13.5px",
                        "fontWeight": "600",
                        "color": "#334155",
                        "cursor": "pointer",
                    },
                ),
            ],
            style={
                "display": "flex",
                "alignItems": "center",
                "backgroundColor": "#F1F5F9",
                "border": "1px solid #E2E8F0",
                "borderRadius": "10px",
                "padding": "10px 18px",
                "marginBottom": "14px",
            },
        ),

        # ── Vue APC ───────────────────────────────────────────────────────
        html.Div(
            id="sunburst-apc-container",
            children=[
                html.Div(
                    [
                        dcc.Graph(
                            id="sunburst-graph",
                            style={"height": "980px"},
                            config={
                                "displayModeBar": True,
                                "displaylogo": False,
                                "responsive": True,
                                "scrollZoom": True,
                            },
                        )
                    ],
                    style={**CARD_STYLE, "flex": "3", "marginBottom": 0, "minWidth": "720px"},
                ),
                html.Div(
                    id="sunburst-detail-panel",
                    style={"flex": "1", "minWidth": "320px", "maxHeight": "980px"},
                ),
            ],
            style={"display": "flex", "gap": "16px", "alignItems": "stretch", "flexWrap": "wrap"},
        ),

        # ── Vue Semestre ──────────────────────────────────────────────────
        html.Div(
            id="sunburst-semester-container",
            children=[
                html.Div(
                    [
                        dcc.Graph(
                            id="sunburst-semester-graph",
                            style={"height": "980px"},
                            config={
                                "displayModeBar": True,
                                "displaylogo": False,
                                "responsive": True,
                                "scrollZoom": True,
                            },
                        )
                    ],
                    style={**CARD_STYLE, "flex": "3", "marginBottom": 0, "minWidth": "720px"},
                ),
                html.Div(
                    id="sunburst-semester-detail-panel",
                    style={"flex": "1", "minWidth": "320px", "maxHeight": "980px"},
                ),
            ],
            style={"display": "none", "gap": "16px", "alignItems": "stretch", "flexWrap": "wrap"},
        ),
    ],
    style=PAGE_STYLE,
)


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITAIRES FILTRAGE
# ══════════════════════════════════════════════════════════════════════════════

def get_filtered_sunburst_rows(stored_rows, semester, specialite):
    if not stored_rows:
        return []
    filtered_rows = filter_rows_by_specialite(stored_rows, specialite)
    if semester and semester != "all":
        filtered_rows = [
            row
            for row in filtered_rows
            if str(row.get("semestre")) == str(semester)
        ]
    return filtered_rows


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def register_callbacks(app):

    @app.callback(
        Output("sunburst-programme-selector", "value"),
        Input("sunburst-programme-selector", "options"),
        State("sunburst-programme-selector", "value"),
        prevent_initial_call=False,
    )
    def init_sunburst_programme_selector(options, current_value):
        if current_value is not None:
            return current_value
        if options:
            return options[0]["value"]
        return None

    @app.callback(
        Output("sunburst-rows-store", "data"),
        Output("sunburst-semester-filter", "options"),
        Output("sunburst-specialite-filter", "options"),
        Output("sunburst-specialite-filter", "value"),
        Input("sunburst-programme-selector", "value"),
    )
    def load_sunburst_rows(selected_programme):
        comp_data, curr_data = get_selected_data(selected_programme)
        rows = build_visualisation_rows(comp_data, curr_data)
        semestres = sorted(
            {row.get("semestre") for row in rows if row.get("semestre") is not None},
            key=sort_semester,
        )
        semester_options = [{"label": "Tous les semestres", "value": "all"}] + [
            {"label": f"Semestre {semestre}", "value": str(semestre)}
            for semestre in semestres
        ]
        specialite_options = get_specialite_options_from_rows(rows)
        return rows, semester_options, specialite_options, "all"

    @app.callback(
        Output("sunburst-selected-competence-store", "data"),
        Output("sunburst-selected-ac-store", "data"),
        Input("sunburst-graph", "clickData"),
        Input("sunburst-programme-selector", "value"),
        Input("sunburst-semester-filter", "value"),
        Input("sunburst-specialite-filter", "value"),
        State("sunburst-selected-competence-store", "data"),
        State("sunburst-selected-ac-store", "data"),
        prevent_initial_call=True,
    )
    def update_selected_competence(
        click_data,
        selected_programme,
        semester,
        specialite,
        current_competence,
        current_ac,
    ):
        """
        Gère la navigation à trois niveaux via les deux Stores.

        Niveaux :
            Global      : competence=None, ac=None
            Comp detail : competence=COMP_CODE, ac=None
            AC detail   : competence=COMP_CODE, ac=AC_CODE

        Règles de navigation :
            filtre change         → (None, None)               global
            clic COMP::           → (COMP_CODE, None)          entrer dans comp
            clic AC::             → (no_update, AC_CODE)       entrer dans AC (comp conservée)
            clic ROOT:: en AC     → (no_update, None)          retour comp
            clic ROOT:: en comp   → (None, None)               retour global
            clic NIV:: / MOD::   → (no_update, no_update)      pas de changement de vue
        """
        triggered_id = ctx.triggered_id

        # Changement de filtre : retour à la vue globale dans tous les cas
        if triggered_id in (
            "sunburst-programme-selector",
            "sunburst-semester-filter",
            "sunburst-specialite-filter",
        ):
            return None, None

        node_id = get_clicked_node_id(click_data)

        if not node_id:
            return no_update, no_update

        # Clic sur ROOT:: : navigation "retour"
        if node_id.startswith("ROOT::"):
            if current_ac:
                # Vue AC → retour vue comp (comp conservée)
                return no_update, None
            if current_competence:
                # Vue comp → retour vue globale
                return None, None
            return no_update, no_update

        # Clic sur une compétence : entrer en vue comp, fermer la vue AC si ouverte
        if node_id.startswith("COMP::"):
            return node_id.replace("COMP::", ""), None

        # Clic sur un AC : entrer en vue AC (compétence courante conservée)
        if node_id.startswith("AC::"):
            return no_update, node_id.replace("AC::", "")

        # Clic sur NIV:: ou MOD:: : aucun changement de vue
        return no_update, no_update

    @app.callback(
        Output("sunburst-graph", "figure"),
        Input("sunburst-rows-store", "data"),
        Input("sunburst-programme-selector", "value"),
        Input("sunburst-semester-filter", "value"),
        Input("sunburst-specialite-filter", "value"),
        Input("sunburst-selected-competence-store", "data"),
        Input("sunburst-selected-ac-store", "data"),
    )
    def update_sunburst_figure(
        stored_rows,
        selected_programme,
        semester,
        specialite,
        selected_competence_code,
        selected_ac_code,
    ):
        """
        Met à jour la figure selon le niveau de navigation actif.

        Priorité :
            1. Vue AC detail  (selected_ac_code défini)
            2. Vue comp detail (selected_competence_code défini)
            3. Vue globale

        Ordre des opérations :
            - Filtrer par semestre/spécialité.
            - Calculer competence_order GLOBAL (avant filtrage par comp/AC)
              pour garantir la stabilité des couleurs entre les vues.
            - Générer la figure selon le niveau.
        """
        filtered_rows = get_filtered_sunburst_rows(stored_rows, semester, specialite)
        if not filtered_rows:
            return empty_figure("Aucune donnée pour les filtres sélectionnés")

        # Ordre global calculé sur TOUTES les compétences — stabilité des couleurs
        competence_order = get_competence_order(filtered_rows)

        # Vue AC detail : centre = "AC3 : desc", anneau = modules
        if selected_ac_code:
            ac_rows = filter_rows_by_ac(filtered_rows, selected_ac_code)
            return create_ac_detail_figure(
                ac_rows,
                ac_code=selected_ac_code,
                semester=semester,
                competence_order=competence_order,
            )

        # Vue comp detail : centre = compétence, anneaux = niveaux → AC → modules
        if selected_competence_code:
            figure_rows = filter_rows_by_competence(filtered_rows, selected_competence_code)
            return create_sunburst_figure(
                figure_rows,
                selected_programme=selected_programme,
                semester=semester,
                show_levels=True,
                selected_competence_code=selected_competence_code,
                competence_order=competence_order,
            )

        # Vue globale : centre = formation, anneaux = comp → AC → modules
        return create_sunburst_figure(
            filtered_rows,
            selected_programme=selected_programme,
            semester=semester,
            show_levels=False,
            selected_competence_code=None,
            competence_order=competence_order,
        )

    @app.callback(
        Output("sunburst-detail-panel", "children"),
        Input("sunburst-graph", "clickData"),
        Input("sunburst-rows-store", "data"),
        Input("sunburst-programme-selector", "value"),
        Input("sunburst-semester-filter", "value"),
        Input("sunburst-specialite-filter", "value"),
    )
    def update_sunburst_detail_panel(
        click_data,
        stored_rows,
        selected_programme,
        semester,
        specialite,
    ):
        triggered_id = ctx.triggered_id
        if triggered_id in (
            "sunburst-programme-selector",
            "sunburst-semester-filter",
            "sunburst-specialite-filter",
        ):
            return build_empty_detail_panel()
        filtered_rows = get_filtered_sunburst_rows(stored_rows, semester, specialite)
        if not filtered_rows:
            return build_empty_detail_panel()
        return build_selection_detail_panel(filtered_rows, click_data)

    # ── 5. Switching entre les deux vues (APC ↔ Semestre) ────────────────────

    @app.callback(
        Output("sunburst-active-tab", "data"),
        Input("sunburst-view-selector", "value"),
    )
    def update_active_tab(selected):
        return selected or "apc"

    @app.callback(
        Output("sunburst-apc-container", "style"),
        Output("sunburst-semester-container", "style"),
        Input("sunburst-active-tab", "data"),
    )
    def toggle_view_containers(active_tab):
        flex_style = {"display": "flex", "gap": "16px", "alignItems": "stretch", "flexWrap": "wrap"}
        hidden_style = {"display": "none"}
        if active_tab == "semester":
            return hidden_style, flex_style
        return flex_style, hidden_style

    # ── 6. Figure du sunburst semestriel ─────────────────────────────────────

    @app.callback(
        Output("sunburst-semester-graph", "figure"),
        Input("sunburst-rows-store", "data"),
        Input("sunburst-programme-selector", "value"),
        Input("sunburst-semester-filter", "value"),
        Input("sunburst-specialite-filter", "value"),
        Input("sunburst-active-tab", "data"),
    )
    def update_semester_figure(stored_rows, selected_programme, semester, specialite, active_tab):
        """
        Génère la figure du sunburst semestriel.

        Ne calcule rien si l'onglet APC est actif (optimisation).
        Le filtre semestre s'applique normalement : si S3 est sélectionné,
        seuls les modules du S3 apparaissent dans la vue semestrielle.
        """
        if active_tab != "semester":
            return no_update

        filtered_rows = get_filtered_sunburst_rows(stored_rows, semester, specialite)
        if not filtered_rows:
            return empty_figure("Aucune donnée pour les filtres sélectionnés")

        competence_order = get_competence_order(filtered_rows)

        return create_semester_sunburst_figure(
            filtered_rows,
            selected_programme=selected_programme,
            semester=semester,
            competence_order=competence_order,
        )

    # ── 7. Panneau détail du sunburst semestriel ─────────────────────────────

    @app.callback(
        Output("sunburst-semester-detail-panel", "children"),
        Input("sunburst-semester-graph", "clickData"),
        Input("sunburst-rows-store", "data"),
        Input("sunburst-programme-selector", "value"),
        Input("sunburst-semester-filter", "value"),
        Input("sunburst-specialite-filter", "value"),
    )
    def update_semester_detail_panel(
        click_data, stored_rows, selected_programme, semester, specialite
    ):
        """
        Panneau détail pour la vue semestrielle.

        Stale clickData : quand les filtres changent, on réinitialise le panneau.
        """
        triggered_id = ctx.triggered_id
        if triggered_id in (
            "sunburst-programme-selector",
            "sunburst-semester-filter",
            "sunburst-specialite-filter",
        ):
            return _semester_empty_panel()

        if not click_data:
            return _semester_empty_panel()

        filtered_rows = get_filtered_sunburst_rows(stored_rows, semester, specialite)
        if not filtered_rows:
            return _semester_empty_panel()

        node_id = click_data.get("points", [{}])[0].get("id")
        info = get_semester_node_info(filtered_rows, node_id)

        if info is None:
            return _semester_empty_panel()

        return _semester_detail_content(info)


# ══════════════════════════════════════════════════════════════════════════════
#  PANNEAU DÉTAIL — VUE SEMESTRIELLE
# ══════════════════════════════════════════════════════════════════════════════

def _semester_empty_panel():
    """Panneau vide pour la vue semestrielle."""
    return html.Div(
        [
            html.H3(
                "Détail de la sélection",
                style={"margin": "0 0 8px", "fontSize": "17px", "color": "#0F172A"},
            ),
            html.P(
                "Clique sur un semestre, un AC ou un module dans le Sunburst pour afficher le détail ici.",
                style={"fontSize": "13px", "color": "#64748B", "lineHeight": "1.5", "margin": "0 0 14px"},
            ),
            html.Div(
                [
                    html.Div(
                        "Lecture",
                        style={
                            "fontSize": "11px", "fontWeight": "700", "color": "#64748B",
                            "textTransform": "uppercase", "letterSpacing": "0.6px", "marginBottom": "5px",
                        },
                    ),
                    html.P(
                        "La couleur des AC et modules encode leur compétence. "
                        "La taille d'un segment représente le nombre de modules couverts. "
                        "Chaque module n'apparaît qu'une seule fois, sous son AC principal.",
                        style={"fontSize": "12px", "color": "#334155", "lineHeight": "1.5", "margin": "0"},
                    ),
                ],
                style={
                    "backgroundColor": "#F8FAFC", "border": "1px solid #E2E8F0",
                    "borderRadius": "10px", "padding": "12px",
                },
            ),
        ],
        style={**CARD_STYLE, "height": "100%", "marginBottom": 0},
    )


def _sem_detail_line(label, value):
    return html.Div(
        [
            html.Div(label, style={
                "fontSize": "11px", "fontWeight": "800", "color": "#64748B",
                "textTransform": "uppercase", "letterSpacing": "0.5px", "marginBottom": "2px",
            }),
            html.Div(str(value), style={
                "fontSize": "13px", "fontWeight": "600", "color": "#0F172A", "lineHeight": "1.35",
            }),
        ],
        style={"marginBottom": "12px"},
    )


def _sem_badges(items, bg="#DBEAFE", fg="#1E3A8A"):
    if not items:
        return html.P("Aucun", style={"fontSize": "12px", "color": "#94A3B8", "margin": "0"})
    return html.Div([
        html.Span(item, style={
            "display": "inline-block", "backgroundColor": bg, "color": fg,
            "borderRadius": "999px", "padding": "3px 9px", "fontSize": "11px",
            "fontWeight": "600", "marginRight": "5px", "marginBottom": "5px",
        })
        for item in sorted(items)
    ])


def _semester_detail_content(info):
    """Construit le contenu du panneau détail selon le type de nœud cliqué."""
    ntype = info.get("type")
    style = {**CARD_STYLE, "height": "100%", "marginBottom": 0, "overflowY": "auto"}

    if ntype == "root":
        return html.Div([
            html.H3("Vue d'ensemble", style={"margin": "0 0 12px", "fontSize": "17px", "color": "#0F172A"}),
            _sem_detail_line("Semestres", len(info.get("semestres", set()))),
            _sem_detail_line("Modules uniques", len(info.get("modules", set()))),
            _sem_detail_line("AC couverts", len(info.get("acs", set()))),
            _sem_detail_line("Compétences", len(info.get("competences", set()))),
            html.H4("Compétences présentes", style={"fontSize": "13px", "margin": "14px 0 8px", "color": "#0F172A"}),
            _sem_badges(info.get("competences", set()), "#EDE9FE", "#5B21B6"),
        ], style=style)

    if ntype == "semester":
        return html.Div([
            html.H3(
                f"Semestre {info['semestre']}",
                style={"margin": "0 0 12px", "fontSize": "17px", "color": "#0F172A"},
            ),
            _sem_detail_line("Modules", len(info.get("modules", set()))),
            _sem_detail_line("AC couverts", len(info.get("acs", set()))),
            _sem_detail_line("Compétences", len(info.get("competences", set()))),
            html.H4("Compétences", style={"fontSize": "13px", "margin": "14px 0 8px", "color": "#0F172A"}),
            _sem_badges(info.get("competences", set()), "#EDE9FE", "#5B21B6"),
            html.H4("Modules", style={"fontSize": "13px", "margin": "14px 0 8px", "color": "#0F172A"}),
            _sem_badges(info.get("modules", set())),
        ], style=style)

    if ntype == "ac":
        return html.Div([
            html.H3("Apprentissage critique", style={"margin": "0 0 12px", "fontSize": "17px", "color": "#0F172A"}),
            _sem_detail_line("AC", info.get("ac_code", "")),
            _sem_detail_line("Compétence", info.get("competence_code", "Non renseigné")),
            _sem_detail_line("Semestre", info.get("semestre", "")),
            _sem_detail_line("Modules dans ce semestre", len(info.get("modules_in_semester", set()))),
            html.H4("Description", style={"fontSize": "13px", "margin": "14px 0 6px", "color": "#0F172A"}),
            html.P(
                info.get("description", "Non renseigné"),
                style={
                    "fontSize": "12px", "color": "#334155", "lineHeight": "1.5",
                    "backgroundColor": "#F8FAFC", "border": "1px solid #E2E8F0",
                    "borderRadius": "10px", "padding": "10px",
                },
            ),
            html.H4("Modules", style={"fontSize": "13px", "margin": "14px 0 8px", "color": "#0F172A"}),
            _sem_badges(info.get("modules_in_semester", set())),
        ], style=style)

    if ntype == "module":
        all_comps = info.get("all_competences", [])
        all_acs = info.get("all_acs", [])
        multi_comp = len(all_comps) > 1

        return html.Div([
            html.H3("Module", style={"margin": "0 0 12px", "fontSize": "17px", "color": "#0F172A"}),
            _sem_detail_line("Code", info.get("module_code", "")),
            _sem_detail_line("Nom", info.get("module_name", "")),
            _sem_detail_line("Semestre", info.get("semestre", "")),
            _sem_detail_line("AC principal", info.get("primary_ac", "")),
            _sem_detail_line("Compétence principale", info.get("primary_competence", "Non renseigné")),
            # Badge "multi-compétence" si le module couvre plusieurs compétences
            html.Div(
                "⚡ Ce module couvre plusieurs compétences",
                style={
                    "fontSize": "11px", "fontWeight": "700", "color": "#B45309",
                    "backgroundColor": "#FEF3C7", "border": "1px solid #FDE68A",
                    "borderRadius": "6px", "padding": "5px 10px",
                    "marginBottom": "12px",
                },
            ) if multi_comp else html.Div(),
            html.H4(
                f"Toutes les compétences liées ({len(all_comps)})",
                style={"fontSize": "13px", "margin": "14px 0 8px", "color": "#0F172A"},
            ),
            _sem_badges(all_comps, "#EDE9FE", "#5B21B6"),
            html.H4(
                f"Tous les AC liés ({len(all_acs)})",
                style={"fontSize": "13px", "margin": "14px 0 8px", "color": "#0F172A"},
            ),
            _sem_badges(all_acs, "#F3F4F6", "#374151"),
        ], style=style)

    return _semester_empty_panel()