from dash import html, dcc, Input, Output, State
import plotly.graph_objects as go

from app_tools import load_processed_files, build_programmes_summary
from forested_visualisations import (
    get_selected_data,
    build_visualisation_rows,
    empty_figure,
)


# ══════════════════════════════════════════════════════════════════════════════
# DESIGN TOKENS
# ══════════════════════════════════════════════════════════════════════════════

PAGE_STYLE = {
    "backgroundColor": "#F8FAFB",
    "minHeight": "100vh",
    "padding": "28px 36px",
    "fontFamily": "'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
}

CARD_STYLE = {
    "backgroundColor": "#FFFFFF",
    "padding": "18px 24px",
    "borderRadius": "12px",
    "boxShadow": "0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)",
    "marginBottom": "16px",
    "border": "1px solid #E4E9F0",
}

LABEL_STYLE = {
    "color": "#5A6478",
    "fontWeight": "700",
    "fontSize": "10px",
    "letterSpacing": "1px",
    "textTransform": "uppercase",
    "marginBottom": "7px",
    "display": "block",
}

COLOR_COMPETENCE = "#1E40AF"
COLOR_COMP_BORDER = "#93C5FD"

COLOR_LEVEL = "#64748B"
COLOR_LEVEL_BORDER = "#CBD5E1"

COLOR_MODULE = "#059669"
COLOR_MODULE_BORDER = "#34D399"

NIVEAU_COLORS = {
    "1": "#10B981",
    "2": "#F59E0B",
    "3": "#EF4444",
}

FADE_NODE = "rgba(203,213,225,0.35)"
FADE_LINE = "rgba(203,213,225,0.14)"

LINE_COMP_LEVEL = "rgba(30,64,175,0.45)"
LINE_LEVEL_AC = "rgba(100,116,139,0.36)"
LINE_AC_MODULE = "rgba(5,150,105,0.28)"


# ══════════════════════════════════════════════════════════════════════════════
# PARAMÈTRES DE LAYOUT
# ══════════════════════════════════════════════════════════════════════════════

Y_COMP = 0.0
Y_LEVEL = 3.1
Y_AC = 6.0
Y_MODULE = 9.2
Y_SEMESTER = -1.6

COMP_GAP = 7.5
LEVEL_GAP = 3.0
AC_GAP = 1.25
MODULE_GAP = 0.62

MIN_AC_WIDTH = 1.6
MIN_LEVEL_WIDTH = 3.0
MIN_TREE_WIDTH = 7.0

MAX_MODULES_DEFAULT = 6


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS GÉNÉRAUX
# ══════════════════════════════════════════════════════════════════════════════

def sort_semester(value):
    try:
        return int(str(value).replace("S", ""))
    except Exception:
        return 999


def semester_label(value):
    if value is None:
        return "S?"
    text = str(value).strip()
    if text.upper().startswith("S"):
        return text.upper()
    return f"S{text}"


def normalize_level(value):
    if value is None:
        return "N?"
    text = str(value).strip().upper()
    if text.startswith("N"):
        return text
    return f"N{text}"


def level_number(value):
    text = str(value).upper().replace("N", "")
    try:
        return int(text)
    except Exception:
        return 99


def level_color(value):
    number = str(value).upper().replace("N", "")
    return NIVEAU_COLORS.get(number, "#94A3B8")


def level_label(value):
    labels = {
        "1": "Débutant",
        "2": "Intermédiaire",
        "3": "Avancé",
    }
    number = str(value).upper().replace("N", "")
    return labels.get(number, "Niveau")


def hex_to_rgb(hex_color):
    value = hex_color.lstrip("#")

    if len(value) != 6:
        return "100,100,100"

    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)

    return f"{r},{g},{b}"


def get_programme_options():
    datasets = load_processed_files()
    programmes = build_programmes_summary(datasets)

    return [
        {
            "label": f"{item['source']} — {item['programme']}",
            "value": f"{item['source']}::{item['programme']}",
        }
        for item in programmes
    ]


programme_options = get_programme_options()
default_programme = programme_options[0]["value"] if programme_options else None


# ══════════════════════════════════════════════════════════════════════════════
# NORMALISATION DES LIGNES
# ══════════════════════════════════════════════════════════════════════════════

def build_forest_rows(rows):
    """
    Transforme les rows du graphe relationnel en rows dédiées à ForestED.

    Structure cible :
    semestre -> compétence -> niveau -> AC -> modules
    """

    result = []

    for r in rows:
        competence_code = r.get("competence_code")
        ac_code = r.get("ac_code")
        module_code = r.get("module_code") or r.get("module_id")

        if not competence_code or not ac_code:
            continue

        result.append({
            "semestre": semester_label(r.get("semestre")),
            "competence_code": competence_code,
            "competence_name": r.get("competence_name") or competence_code,

            "niveau": normalize_level(r.get("niveau")),

            "ac_code": ac_code,
            "ac_description": r.get("ac_description") or "",

            "module_key": module_code,
            "module_id": r.get("module_id") or module_code,
            "module_code": module_code,
            "module_name": r.get("module_name") or module_code,
            "module_type": r.get("module_type"),
            "ue_code": r.get("ue_code"),
            "parcours": r.get("parcours") or "COMMUN",
        })

    return result


# ══════════════════════════════════════════════════════════════════════════════
# CONSTRUCTION HIÉRARCHIQUE
# ══════════════════════════════════════════════════════════════════════════════

def build_forest_hierarchy(
    forest_rows,
    semester_filter="ALL",
    competence_filter="ALL",
    max_modules_per_ac=MAX_MODULES_DEFAULT,
):
    """
    Construit une vraie hiérarchie :

    Compétence
        -> Niveau
            -> AC
                -> Modules

    Les modules sont dédupliqués sous chaque AC.
    """

    forest = {}

    for row in forest_rows:
        if semester_filter and semester_filter != "ALL":
            if row.get("semestre") != semester_filter:
                continue

        if competence_filter and competence_filter != "ALL":
            if row.get("competence_code") != competence_filter:
                continue

        comp_code = row["competence_code"]
        level_key = row["niveau"]
        ac_code = row["ac_code"]
        module_key = row.get("module_key")

        if comp_code not in forest:
            forest[comp_code] = {
                "type": "competence",
                "code": comp_code,
                "label": row.get("competence_name") or comp_code,
                "levels": {},
            }

        comp_node = forest[comp_code]

        if level_key not in comp_node["levels"]:
            comp_node["levels"][level_key] = {
                "type": "level",
                "code": level_key,
                "label": level_key,
                "acs": {},
            }

        level_node = comp_node["levels"][level_key]

        if ac_code not in level_node["acs"]:
            level_node["acs"][ac_code] = {
                "type": "ac",
                "code": ac_code,
                "label": ac_code,
                "description": row.get("ac_description") or "",
                "niveau": level_key,
                "modules": {},
                "all_modules": {},
            }

        ac_node = level_node["acs"][ac_code]

        if module_key:
            ac_node["all_modules"][module_key] = {
                "type": "module",
                "code": row.get("module_code") or module_key,
                "id": row.get("module_id") or module_key,
                "label": row.get("module_name") or module_key,
                "module_type": row.get("module_type"),
                "ue_code": row.get("ue_code"),
                "parcours": row.get("parcours"),
            }

    # Limite de feuilles visibles par AC
    for comp_node in forest.values():
        for level_node in comp_node["levels"].values():
            for ac_node in level_node["acs"].values():
                modules = list(ac_node["all_modules"].items())

                if len(modules) <= max_modules_per_ac:
                    ac_node["modules"] = dict(modules)
                else:
                    kept = dict(modules[:max_modules_per_ac])
                    hidden_count = len(modules) - max_modules_per_ac

                    kept[f"MORE::{ac_node['code']}"] = {
                        "type": "more",
                        "code": f"+{hidden_count}",
                        "id": f"MORE::{ac_node['code']}",
                        "label": f"+{hidden_count} autres modules",
                    }

                    ac_node["modules"] = kept

    return forest


# ══════════════════════════════════════════════════════════════════════════════
# CALCUL DES LARGEURS
# ══════════════════════════════════════════════════════════════════════════════

def compute_ac_width(ac_node):
    modules_count = max(1, len(ac_node.get("modules", {})))
    return max(MIN_AC_WIDTH, modules_count * MODULE_GAP)


def compute_level_width(level_node):
    acs = level_node.get("acs", {})

    if not acs:
        return MIN_LEVEL_WIDTH

    widths = [
        compute_ac_width(ac_node)
        for ac_node in acs.values()
    ]

    return max(
        MIN_LEVEL_WIDTH,
        sum(widths) + max(0, len(widths) - 1) * AC_GAP
    )


def compute_tree_width(comp_node):
    levels = comp_node.get("levels", {})

    if not levels:
        return MIN_TREE_WIDTH

    widths = [
        compute_level_width(level_node)
        for level_node in levels.values()
    ]

    return max(
        MIN_TREE_WIDTH,
        sum(widths) + max(0, len(widths) - 1) * LEVEL_GAP
    )


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT DES NŒUDS
# ══════════════════════════════════════════════════════════════════════════════

def compute_forest_layout(forest):
    """
    Calcule les positions x/y.

    Chaque compétence est un arbre.
    Chaque arbre contient :
    - racine compétence en bas,
    - niveaux au-dessus,
    - AC au-dessus,
    - modules en feuilles.
    """

    positions = {}
    meta = {}
    edges = []

    tree_widths = {
        comp_code: compute_tree_width(comp_node)
        for comp_code, comp_node in forest.items()
    }

    total_width = (
        sum(tree_widths.values())
        + max(0, len(tree_widths) - 1) * COMP_GAP
    )

    cursor = -total_width / 2

    for comp_code, comp_node in sorted(forest.items()):
        tree_width = tree_widths[comp_code]
        tree_center = cursor + tree_width / 2

        comp_id = f"COMP::{comp_code}"

        positions[comp_id] = (tree_center, Y_COMP)
        meta[comp_id] = {
            "type": "competence",
            "code": comp_code,
            "label": comp_node["label"],
            "hover": (
                f"<b>Compétence : {comp_code}</b><br>"
                f"{comp_node['label']}"
            ),
        }

        level_items = sorted(
            comp_node["levels"].items(),
            key=lambda item: level_number(item[0])
        )

        level_widths = [
            compute_level_width(level_node)
            for _, level_node in level_items
        ]

        level_total_width = (
            sum(level_widths)
            + max(0, len(level_widths) - 1) * LEVEL_GAP
        )

        level_cursor = tree_center - level_total_width / 2

        for level_index, (level_code, level_node) in enumerate(level_items):
            level_width = level_widths[level_index]
            level_center = level_cursor + level_width / 2

            level_id = f"LEVEL::{comp_code}::{level_code}"

            positions[level_id] = (level_center, Y_LEVEL)
            meta[level_id] = {
                "type": "level",
                "code": level_code,
                "label": level_code,
                "competence_code": comp_code,
                "hover": (
                    f"<b>{level_code}</b><br>"
                    f"{level_label(level_code)}<br>"
                    f"Compétence : {comp_code}"
                ),
            }

            edges.append((comp_id, level_id, "comp_level", level_code))

            ac_items = sorted(
                level_node["acs"].items(),
                key=lambda item: item[0]
            )

            ac_widths = [
                compute_ac_width(ac_node)
                for _, ac_node in ac_items
            ]

            ac_total_width = (
                sum(ac_widths)
                + max(0, len(ac_widths) - 1) * AC_GAP
            )

            ac_cursor = level_center - ac_total_width / 2

            for ac_index, (ac_code, ac_node) in enumerate(ac_items):
                ac_width = ac_widths[ac_index]
                ac_center = ac_cursor + ac_width / 2

                ac_id = f"AC::{ac_code}"

                positions[ac_id] = (ac_center, Y_AC)
                meta[ac_id] = {
                    "type": "ac",
                    "code": ac_code,
                    "label": ac_code,
                    "niveau": level_code,
                    "description": ac_node.get("description", ""),
                    "competence_code": comp_code,
                    "all_modules": ac_node.get("all_modules", {}),
                    "hover": (
                        f"<b>AC : {ac_code}</b><br>"
                        f"{level_code} — {level_label(level_code)}<br>"
                        f"Compétence : {comp_code}<br><br>"
                        f"<i>{ac_node.get('description', '')}</i>"
                    ),
                }

                edges.append((level_id, ac_id, "level_ac", level_code))

                module_items = sorted(ac_node["modules"].items())
                module_count = len(module_items)

                if module_count == 0:
                    ac_cursor += ac_width + AC_GAP
                    continue

                module_start = (
                    ac_center
                    - ((module_count - 1) * MODULE_GAP) / 2
                )

                for module_index, (module_key, module_node) in enumerate(module_items):
                    module_x = module_start + module_index * MODULE_GAP

                    if module_node["type"] == "more":
                        module_id = f"MORE::{ac_code}"
                        node_type = "more"
                    else:
                        module_id = f"MODULE::{comp_code}::{ac_code}::{module_key}"
                        node_type = "module"

                    positions[module_id] = (module_x, Y_MODULE)

                    meta[module_id] = {
                        "type": node_type,
                        "code": module_node.get("code") or module_key,
                        "label": module_node.get("label") or module_key,
                        "module_id": module_node.get("id") or module_key,
                        "ac_code": ac_code,
                        "competence_code": comp_code,
                        "niveau": level_code,
                        "hover": (
                            f"<b>{'Modules masqués' if node_type == 'more' else 'Module'} : "
                            f"{module_node.get('code') or module_key}</b><br>"
                            f"{module_node.get('label') or ''}<br>"
                            f"AC : {ac_code}<br>"
                            f"Compétence : {comp_code}"
                        ),
                    }

                    edges.append((ac_id, module_id, "ac_module", level_code))

                ac_cursor += ac_width + AC_GAP

            level_cursor += level_width + LEVEL_GAP

        cursor += tree_width + COMP_GAP

    return positions, meta, edges


# ══════════════════════════════════════════════════════════════════════════════
# FOCUS / CLICK
# ══════════════════════════════════════════════════════════════════════════════

def parse_click(click_data):
    if not click_data:
        return None

    try:
        points = click_data.get("points", [])
        if not points:
            return None

        customdata = points[0].get("customdata")

        if isinstance(customdata, list) and len(customdata) >= 2:
            return {
                "type": customdata[0],
                "id": customdata[1],
            }

    except Exception:
        return None

    return None


def resolve_focus(selected, meta, edges):
    """
    Focus / traçabilité robuste.

    Compétence :
        Compétence -> Niveaux -> AC -> Modules

    Niveau :
        Compétence -> Niveau -> AC du niveau -> Modules

    AC :
        Compétence -> Niveau -> AC -> Modules

    Module :
        Compétence -> Niveau -> AC -> Module

    Si le nœud sélectionné n'existe plus après filtre :
        reset du focus.
    """

    if not selected:
        return None, None

    selected_id = selected.get("id")

    if not selected_id:
        return None, None

    # Sécurité importante contre les anciens clickData
    if selected_id not in meta:
        return None, None

    active_nodes = set()
    active_edges = set()

    children = {}
    parents = {}

    for source, target, edge_type, level_code in edges:
        children.setdefault(source, set()).add(target)
        parents.setdefault(target, set()).add(source)

    def add_descendants(node_id):
        active_nodes.add(node_id)

        for child in children.get(node_id, set()):
            active_edges.add((node_id, child))
            add_descendants(child)

    def add_ancestors(node_id):
        active_nodes.add(node_id)

        for parent in parents.get(node_id, set()):
            active_edges.add((parent, node_id))
            add_ancestors(parent)

    selected_type = meta[selected_id].get("type")

    if selected_type == "competence":
        add_descendants(selected_id)

    elif selected_type == "level":
        add_ancestors(selected_id)
        add_descendants(selected_id)

    elif selected_type == "ac":
        add_ancestors(selected_id)
        add_descendants(selected_id)

    elif selected_type in ["module", "more"]:
        add_ancestors(selected_id)
        active_nodes.add(selected_id)

    else:
        return None, None

    return active_nodes, active_edges

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE PLOTLY
# ══════════════════════════════════════════════════════════════════════════════

def create_forest_figure(
    forest_rows,
    semester_filter="ALL",
    competence_filter="ALL",
    max_modules_per_ac=MAX_MODULES_DEFAULT,
    selected_node=None,
):
    if not forest_rows:
        return empty_figure("Aucune donnée ForestED disponible")

    forest = build_forest_hierarchy(
        forest_rows,
        semester_filter=semester_filter,
        competence_filter=competence_filter,
        max_modules_per_ac=max_modules_per_ac,
    )

    if not forest:
        return empty_figure("Aucune donnée disponible pour ce filtre")

    positions, meta, edges = compute_forest_layout(forest)
    selected = selected_node
    active_nodes, active_edges = resolve_focus(selected, meta, edges)

    has_focus = active_nodes is not None

    fig = go.Figure()

    # Liens
    for source, target, edge_type, level_code in edges:
        x0, y0 = positions[source]
        x1, y1 = positions[target]

        is_active = (
            not has_focus
            or (source, target) in active_edges
        )

        if edge_type == "comp_level":
            color = LINE_COMP_LEVEL if is_active else FADE_LINE
            width = 2.6 if is_active else 0.7

        elif edge_type == "level_ac":
            color_base = level_color(level_code)
            alpha = 0.46 if is_active else 0.08
            color = f"rgba({hex_to_rgb(color_base)},{alpha})"
            width = 1.8 if is_active else 0.6

        else:
            color = LINE_AC_MODULE if is_active else FADE_LINE
            width = 1.1 if is_active else 0.45

        fig.add_trace(go.Scatter(
            x=[x0, x1],
            y=[y0, y1],
            mode="lines",
            line=dict(color=color, width=width),
            hoverinfo="none",
            showlegend=False,
        ))

    # Nœuds par type
    traces_by_type = {
        "competence": {
            "x": [], "y": [], "customdata": [], "hover": [],
            "text": [], "color": [], "size": [],
        },
        "level": {
            "x": [], "y": [], "customdata": [], "hover": [],
            "text": [], "color": [], "size": [],
        },
        "ac": {
            "x": [], "y": [], "customdata": [], "hover": [],
            "text": [], "color": [], "size": [],
        },
        "module": {
            "x": [], "y": [], "customdata": [], "hover": [],
            "text": [], "color": [], "size": [],
        },
        "more": {
            "x": [], "y": [], "customdata": [], "hover": [],
            "text": [], "color": [], "size": [],
        },
    }

    for node_id, node_meta in meta.items():
        node_type = node_meta["type"]
        x, y = positions[node_id]

        is_active = (
            not has_focus
            or node_id in active_nodes
        )

        if node_type == "competence":
            color = COLOR_COMPETENCE if is_active else FADE_NODE
            size = 20 if is_active else 12
            text = f"<b>{node_meta['code']}</b>" if is_active else ""

        elif node_type == "level":
            color = COLOR_LEVEL if is_active else FADE_NODE
            size = 15 if is_active else 9
            text = node_meta["code"] if is_active else ""

        elif node_type == "ac":
            color = level_color(node_meta.get("niveau")) if is_active else FADE_NODE
            size = 12 if is_active else 7
            text = ""

        elif node_type == "more":
            color = "#F8FAFC" if is_active else FADE_NODE
            size = 17 if is_active else 10
            text = node_meta["code"] if is_active else ""

        else:
            color = COLOR_MODULE if is_active else FADE_NODE
            size = 8 if is_active else 5
            text = ""

        traces_by_type[node_type]["x"].append(x)
        traces_by_type[node_type]["y"].append(y)
        traces_by_type[node_type]["customdata"].append([node_type, node_id])
        traces_by_type[node_type]["hover"].append(node_meta["hover"])
        traces_by_type[node_type]["text"].append(text)
        traces_by_type[node_type]["color"].append(color)
        traces_by_type[node_type]["size"].append(size)

    def add_node_trace(node_type, name, symbol, border_color, text_position):
        data = traces_by_type[node_type]

        if not data["x"]:
            return

        fig.add_trace(go.Scatter(
            x=data["x"],
            y=data["y"],
            mode="markers+text" if any(data["text"]) else "markers",
            text=data["text"],
            textposition=text_position,
            textfont=dict(size=9, color="#0F172A"),
            marker=dict(
                color=data["color"],
                size=data["size"],
                symbol=symbol,
                line=dict(width=1.2, color=border_color),
            ),
            customdata=data["customdata"],
            hovertext=data["hover"],
            hoverinfo="text",
            name=name,
        ))

    add_node_trace("competence", "Compétence", "diamond", COLOR_COMP_BORDER, "bottom center")
    add_node_trace("level", "Niveau", "circle", COLOR_LEVEL_BORDER, "middle center")
    add_node_trace("ac", "AC", "circle", "white", "top center")
    add_node_trace("module", "Module", "square", COLOR_MODULE_BORDER, "top center")
    add_node_trace("more", "+N modules", "circle", "#CBD5E1", "middle center")

    xs = [x for x, _ in positions.values()]
    x_min = min(xs) - 5
    x_max = max(xs) + 5

    # Bandes horizontales discrètes
    for y_value, color in [
        (Y_COMP, "rgba(30,64,175,0.05)"),
        (Y_LEVEL, "rgba(100,116,139,0.04)"),
        (Y_AC, "rgba(245,158,11,0.04)"),
        (Y_MODULE, "rgba(5,150,105,0.05)"),
    ]:
        fig.add_shape(
            type="rect",
            x0=x_min,
            x1=x_max,
            y0=y_value - 0.45,
            y1=y_value + 0.45,
            fillcolor=color,
            line=dict(width=0),
            layer="below",
        )

    # Libellés à gauche
    label_x = x_min - 1.5

    labels = [
        (Y_MODULE, "Modules", COLOR_MODULE),
        (Y_AC, "AC", "#475569"),
        (Y_LEVEL, "Niveaux", "#475569"),
        (Y_COMP, "Compétences", COLOR_COMPETENCE),
    ]

    for y, label, color in labels:
        fig.add_trace(go.Scatter(
            x=[label_x],
            y=[y],
            text=[f"<b>{label}</b>"],
            mode="text",
            textfont=dict(size=12, color=color),
            hoverinfo="none",
            showlegend=False,
        ))

    # Label semestre si un seul semestre sélectionné
    if semester_filter and semester_filter != "ALL":
        fig.add_trace(go.Scatter(
            x=[(x_min + x_max) / 2],
            y=[Y_SEMESTER],
            text=[f"<b>{semester_filter}</b>"],
            mode="text",
            textfont=dict(size=18, color=COLOR_COMPETENCE),
            hoverinfo="none",
            showlegend=False,
        ))

    focus_text = ""

    if selected and selected.get("id") in meta:
        focus_text = (
            f" · Focus : "
            f"<b>{meta[selected['id']].get('code', '')}</b>"
        )

    fig.update_layout(
        title=dict(
            text=(
                "<b>ForestED — Forêt hiérarchique APC</b>"
                "<span style='color:#94A3B8;font-size:13px'>"
                " · Compétence → Niveau → AC → Modules"
                f"{focus_text}"
                "</span>"
            ),
            x=0.01,
            y=0.98,
            font=dict(size=17, color="#0F172A"),
        ),
        height=880,
        paper_bgcolor="#F8FAFB",
        plot_bgcolor="#FFFFFF",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(255,255,255,0.94)",
            bordercolor="#E4E9F0",
            borderwidth=1,
            font=dict(size=12, color="#374151"),
        ),
        margin=dict(l=170, r=60, t=80, b=80),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[x_min - 3, x_max + 2],
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[-2.2, 10.6],
        ),
        clickmode="event",
        hovermode="closest",
    )

    return fig


# ══════════════════════════════════════════════════════════════════════════════
# OPTIONS FILTRES
# ══════════════════════════════════════════════════════════════════════════════

def build_semester_options(forest_rows):
    semesters = sorted(
        {row["semestre"] for row in forest_rows if row.get("semestre")},
        key=sort_semester,
    )

    return [{"label": "Tous les semestres", "value": "ALL"}] + [
        {"label": semester, "value": semester}
        for semester in semesters
    ]


def build_competence_options(forest_rows, semester_filter="ALL"):
    rows = forest_rows

    if semester_filter and semester_filter != "ALL":
        rows = [
            row for row in forest_rows
            if row.get("semestre") == semester_filter
        ]

    competences = {}

    for row in rows:
        code = row.get("competence_code")
        name = row.get("competence_name") or code

        if code:
            competences[code] = name

    return [{"label": "Toutes les compétences", "value": "ALL"}] + [
        {
            "label": f"{code} — {name}",
            "value": code,
        }
        for code, name in sorted(competences.items())
    ]


# ══════════════════════════════════════════════════════════════════════════════
# PANEL DÉTAIL
# ══════════════════════════════════════════════════════════════════════════════

def build_focus_panel(forest_rows, click_data):
    selected = parse_click(click_data)

    if not selected:
        return html.Div()
    if not selected.get("id"):
        return html.Div()

    selected_type = selected["type"]
    selected_id = selected["id"]

    related = []

    if selected_type == "competence":
        comp_code = selected_id.replace("COMP::", "")
        related = [
            row for row in forest_rows
            if row.get("competence_code") == comp_code
        ]
        title = f"Compétence : {comp_code}"

    elif selected_type == "level":
        parts = selected_id.split("::")
        comp_code = parts[1] if len(parts) > 1 else ""
        level_code = parts[2] if len(parts) > 2 else ""
        related = [
            row for row in forest_rows
            if row.get("competence_code") == comp_code
            and row.get("niveau") == level_code
        ]
        title = f"{level_code} — {level_label(level_code)}"

    elif selected_type == "ac":
        ac_code = selected_id.replace("AC::", "")
        related = [
            row for row in forest_rows
            if row.get("ac_code") == ac_code
        ]
        title = f"AC : {ac_code}"

    elif selected_type == "module":
        module_key = selected_id.split("::")[-1]
        related = [
            row for row in forest_rows
            if row.get("module_key") == module_key
        ]
        title = f"Module : {module_key}"

    elif selected_type == "more":
        title = "Modules masqués"
        related = []

    else:
        return html.Div()

    competences = sorted({
        row.get("competence_code")
        for row in related
        if row.get("competence_code")
    })

    acs = sorted({
        row.get("ac_code")
        for row in related
        if row.get("ac_code")
    })

    modules = sorted({
        row.get("module_code")
        for row in related
        if row.get("module_code")
    })

    return html.Div([
        html.Div([
            html.H4(title, style={
                "margin": "0 0 8px",
                "color": "#0F172A",
                "fontSize": "15px",
            }),

            html.P(
                f"{len(competences)} compétence(s) · {len(acs)} AC · {len(modules)} module(s)",
                style={
                    "margin": "0 0 10px",
                    "fontSize": "12px",
                    "color": "#64748B",
                }
            ),

            html.Div([
                detail_section("Compétences", competences, "#DBEAFE", "#1E40AF"),
                detail_section("AC", acs, "#EDE9FE", "#6D28D9"),
                detail_section("Modules", modules, "#D1FAE5", "#065F46"),
            ])
        ], style={
            "backgroundColor": "#FFFFFF",
            "border": "1px solid #E2E8F0",
            "borderLeft": "4px solid #1E40AF",
            "borderRadius": "8px",
            "padding": "14px 18px",
            "marginBottom": "14px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.05)",
        })
    ])


def detail_section(title, items, bg, color):
    if not items:
        return html.Div()

    return html.Div([
        html.P(
            f"{title} ({len(items)})",
            style={
                "fontWeight": "700",
                "fontSize": "12px",
                "color": color,
                "margin": "8px 0 5px",
            }
        ),
        html.Div([
            html.Span(
                item,
                style={
                    "backgroundColor": bg,
                    "color": color,
                    "borderRadius": "5px",
                    "padding": "3px 8px",
                    "fontSize": "11px",
                    "marginRight": "5px",
                    "marginBottom": "5px",
                    "display": "inline-block",
                }
            )
            for item in items[:60]
        ])
    ])


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT DASH
# ══════════════════════════════════════════════════════════════════════════════

forested_forest_layout = html.Div([

    html.Div([
        html.Div([
            html.Span(
                "🌳",
                style={
                    "fontSize": "36px",
                    "marginRight": "12px",
                    "lineHeight": "1",
                }
            ),

            html.Div([
                html.H1(
                    "ForestED",
                    style={
                        "color": "#0F172A",
                        "fontSize": "28px",
                        "fontWeight": "700",
                        "margin": "0 0 3px",
                        "letterSpacing": "-0.3px",
                    }
                ),

                html.P(
                    "Forêt pédagogique APC : une compétence est une racine, "
                    "les niveaux sont les branches principales, les AC sont les branches, "
                    "les modules sont les feuilles.",
                    style={
                        "color": "#64748B",
                        "fontSize": "13px",
                        "margin": "0",
                    }
                )
            ])
        ], style={
            "display": "flex",
            "alignItems": "center",
        })
    ], style={
        "marginBottom": "18px",
    }),

    html.Div([

        html.Div([
            html.Label("Formation", style=LABEL_STYLE),
            dcc.Dropdown(
                id="forested-programme-selector",
                options=programme_options,
                value=default_programme,
                clearable=False,
                style={"fontSize": "14px"},
            )
        ], style={
            "width": "32%",
            "minWidth": "260px",
        }),

        html.Div([
            html.Label("Semestre", style=LABEL_STYLE),
            dcc.Dropdown(
                id="forested-semester-selector",
                options=[{"label": "Tous les semestres", "value": "ALL"}],
                value="ALL",
                clearable=False,
                style={"fontSize": "14px"},
            )
        ], style={
            "width": "20%",
            "minWidth": "190px",
        }),

        html.Div([
            html.Label("Compétence", style=LABEL_STYLE),
            dcc.Dropdown(
                id="forested-competence-selector",
                options=[{"label": "Toutes les compétences", "value": "ALL"}],
                value="ALL",
                clearable=False,
                style={"fontSize": "14px"},
            )
        ], style={
            "width": "28%",
            "minWidth": "250px",
        }),

        html.Div([
            html.Label("Feuilles / AC", style=LABEL_STYLE),
            dcc.Dropdown(
                id="forested-max-modules-selector",
                options=[
                    {"label": "4 modules", "value": 4},
                    {"label": "6 modules", "value": 6},
                    {"label": "8 modules", "value": 8},
                    {"label": "12 modules", "value": 12},
                ],
                value=MAX_MODULES_DEFAULT,
                clearable=False,
                style={"fontSize": "14px"},
            )
        ], style={
            "width": "12%",
            "minWidth": "130px",
        }),
        html.Button(
    "✕ Réinitialiser",
    id="forested-reset-selection-button",
    n_clicks=0,
    style={
        "height": "38px",
        "padding": "0 16px",
        "borderRadius": "8px",
        "border": "1px solid #CBD5E1",
        "backgroundColor": "#F8FAFC",
        "color": "#0F172A",
        "fontWeight": "700",
        "cursor": "pointer",
    }
),

    ], style={
        **CARD_STYLE,
        "display": "flex",
        "alignItems": "flex-end",
        "flexWrap": "wrap",
        "gap": "14px",
    }),

    html.Div([
        html.Div([
            html.Label("Niveaux AC", style=LABEL_STYLE),

            html.Div([
                html.Span([
                    html.Span(style={
                        "width": "10px",
                        "height": "10px",
                        "borderRadius": "50%",
                        "backgroundColor": color,
                        "display": "inline-block",
                        "marginRight": "5px",
                    }),
                    html.Span(
                        f"N{key} — {level_label(key)}",
                        style={
                            "fontSize": "12px",
                            "color": "#374151",
                        }
                    )
                ], style={
                    "display": "flex",
                    "alignItems": "center",
                    "marginRight": "16px",
                })
                for key, color in NIVEAU_COLORS.items()
            ], style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "4px",
            })
        ]),

        html.Div([
            html.Label("Lecture", style=LABEL_STYLE),
            html.Div(
                "Bas → haut : Compétence → Niveau → AC → Modules",
                style={
                    "fontSize": "12px",
                    "color": "#475569",
                }
            )
        ], style={
            "marginLeft": "28px",
        }),

    ], style={
        **CARD_STYLE,
        "display": "flex",
        "alignItems": "center",
        "flexWrap": "wrap",
        "gap": "12px",
    }),
    

    dcc.Store(id="forested-rows-store"),

    dcc.Store(id="forested-selected-node-store"),

    html.Div(id="forested-focus-panel"),

    html.Div([
        dcc.Graph(
            id="forested-forest-graph",
            config={
                "displayModeBar": True,
                "displaylogo": False,
                "scrollZoom": True,
                "modeBarButtonsToRemove": [
                    "select2d",
                    "lasso2d",
                    "autoScale2d",
                ],
            }
        )
    ], style=CARD_STYLE)

], style=PAGE_STYLE)


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def register_callbacks(app):


    @app.callback(
        Output("forested-selected-node-store", "data"),
        Input("forested-forest-graph", "clickData"),
        Input("forested-reset-selection-button", "n_clicks"),
        Input("forested-programme-selector", "value"),
        Input("forested-semester-selector", "value"),
        Input("forested-competence-selector", "value"),
        Input("forested-max-modules-selector", "value"),
        State("forested-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def update_selected_node(
        click_data,
        reset_clicks,
        selected_programme,
        semester_filter,
        competence_filter,
        max_modules_per_ac,
        current_selection,
    ):
        from dash import ctx

        triggered_id = ctx.triggered_id

        # Reset si bouton ou changement de filtre
        if triggered_id in [
            "forested-reset-selection-button",
            "forested-programme-selector",
            "forested-semester-selector",
            "forested-competence-selector",
            "forested-max-modules-selector",
        ]:
            return None

        selected = parse_click(click_data)

        if not selected:
            return None

        selected_id = selected.get("id")

        # Deuxième clic sur le même nœud => reset
        if current_selection and current_selection.get("id") == selected_id:
            return None

        return selected

    @app.callback(
        Output("forested-rows-store", "data"),
        Input("forested-programme-selector", "value"),
    )
    def store_rows(selected_programme):
        competence_data, curriculum_data = get_selected_data(selected_programme)

        rows = build_visualisation_rows(
            competence_data,
            curriculum_data,
        )

        return build_forest_rows(rows)

    @app.callback(
        Output("forested-semester-selector", "options"),
        Output("forested-semester-selector", "value"),
        Input("forested-rows-store", "data"),
    )
    def update_semester_options(stored_rows):
        if not stored_rows:
            return [{"label": "Tous les semestres", "value": "ALL"}], "ALL"

        return build_semester_options(stored_rows), "ALL"

    @app.callback(
        Output("forested-competence-selector", "options"),
        Output("forested-competence-selector", "value"),
        Input("forested-rows-store", "data"),
        Input("forested-semester-selector", "value"),
    )
    def update_competence_options(stored_rows, semester_filter):
        if not stored_rows:
            return [{"label": "Toutes les compétences", "value": "ALL"}], "ALL"

        return build_competence_options(stored_rows, semester_filter), "ALL"

    @app.callback(
    Output("forested-forest-graph", "figure"),
    Input("forested-rows-store", "data"),
    Input("forested-semester-selector", "value"),
    Input("forested-competence-selector", "value"),
    Input("forested-max-modules-selector", "value"),
    Input("forested-selected-node-store", "data"),
    )
    def update_figure(
    stored_rows,
    semester_filter,
    competence_filter,
    max_modules_per_ac,
    selected_node,
    ):
        if not stored_rows:
            return empty_figure("Aucune donnée disponible")

        return create_forest_figure(
        forest_rows=stored_rows,
        semester_filter=semester_filter or "ALL",
        competence_filter=competence_filter or "ALL",
        max_modules_per_ac=max_modules_per_ac or MAX_MODULES_DEFAULT,
        selected_node=selected_node,
        )

    @app.callback(
    Output("forested-focus-panel", "children"),
    Input("forested-selected-node-store", "data"),
    State("forested-rows-store", "data"),
    )
    def update_focus_panel(selected_node, stored_rows):
        if not stored_rows or not selected_node:
            return html.Div()

        fake_click_data = {
            "points": [
                {
                    "customdata": [
                        selected_node["type"],
                    selected_node["id"]
                ]
            }
        ]
        }

        return build_focus_panel(stored_rows, fake_click_data)