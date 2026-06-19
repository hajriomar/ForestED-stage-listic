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
"""



from dash import html, dcc, Input, Output, State
import plotly.graph_objects as go

from forested_visualisations import (
    PAGE_STYLE,
    CARD_STYLE,
    LABEL_STYLE,
    PALETTE_COMPETENCES,
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

def _clean(value, default="Non renseigné"):
    """
    Nettoie une valeur textuelle.

    Objectif :
    éviter les None, les chaînes vides et les labels cassés dans Plotly.
    """
    if value is None:
        return default

    text = str(value).strip()
    return text if text else default


def _safe_int(value, default=99):
    """
    Convertit une valeur en entier sans casser l'application.

    Utilisé pour trier les niveaux de développement.
    """
    try:
        return int(value)
    except Exception:
        return default


def _shorten(text, max_len=68):
    """
    Raccourcit les labels longs pour garder le Sunburst lisible.
    """
    text = _clean(text, "")

    if len(text) <= max_len:
        return text

    return text[: max_len - 1].rstrip() + "…"


def _competence_color(competence_code, competence_order):
    """
    Retourne la palette associée à une compétence.

    Aucun hardcoding :
    on attribue une couleur selon l'ordre des compétences détectées.
    """
    try:
        index = competence_order.index(competence_code)
    except ValueError:
        index = 0

    return PALETTE_COMPETENCES[index % len(PALETTE_COMPETENCES)]


def _node_color(node_id, node_meta, competence_order):
    """
    Attribue une couleur à chaque nœud du Sunburst.

    Règle :
    - root : couleur neutre ;
    - compétence : couleur principale ;
    - niveau / AC / module : dégradé selon la compétence parente.
    """
    meta = node_meta.get(node_id, {})
    node_type = meta.get("type")
    comp_code = meta.get("competence_code")

    if node_type == "root":
        return "#0F172A"

    scheme = _competence_color(comp_code, competence_order)

    if node_type == "competence":
        return scheme["root"]

    niveau = _safe_int(meta.get("niveau"), default=1)

    if niveau == 1:
        return scheme["n1"]

    if niveau == 2:
        return scheme["n2"]

    if niveau == 3:
        return scheme["n3"]

    return scheme["n2"]


def _format_semestre(value):
    """
    Formate le semestre pour l'affichage.
    """
    if value is None or value == "all":
        return "Tous les semestres"

    text = str(value)

    if text.upper().startswith("S"):
        return text

    return f"S{text}"


# ══════════════════════════════════════════════════════════════════════════════
#  CONSTRUCTION DU SUNBURST
# ══════════════════════════════════════════════════════════════════════════════

def build_sunburst_nodes(rows, root_label="APC"):
    """
    Construit les listes nécessaires à go.Sunburst :

    - ids
    - labels
    - parents
    - values
    - hovertexts
    - colors

    Entrée :
    rows = lignes issues de build_visualisation_rows()

    Règle analytique :
    - chaque module vaut 1 ;
    - un AC vaut le nombre de modules uniques liés à cet AC ;
    - un niveau vaut la somme de ses AC ;
    - une compétence vaut la somme de ses niveaux.

    Important :
    le même module peut apparaître sous plusieurs AC.
    On crée donc un ID module dépendant de son AC parent.
    """

    root_id = "ROOT::APC"

    node_parent = {
        root_id: ""
    }

    node_label = {
        root_id: root_label
    }

    node_value = {}

    node_hover = {
        root_id: f"<b>{root_label}</b><br>Structure APC de la formation"
    }

    node_meta = {
        root_id: {
            "type": "root",
            "competence_code": None
        }
    }

    # ac_index permet de dédupliquer les modules à l'intérieur de chaque AC.
    ac_index = {}

    for row in rows or []:
        comp_code = _clean(row.get("competence_code"), "")
        ac_code = _clean(row.get("ac_code"), "")
        module_code = _clean(
            row.get("module_code") or row.get("module_id"),
            ""
        )

        if not comp_code or not ac_code or not module_code:
            continue

        niveau = row.get("niveau")

        comp_name = _clean(
            row.get("competence_name"),
            comp_code
        )

        ac_description = _clean(
            row.get("ac_description"),
            ac_code
        )

        module_name = _clean(
            row.get("module_name"),
            module_code
        )

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

        # Dédoublonnage : un module ne compte qu'une seule fois dans un AC.
        ac_index[ac_id]["modules"][module_code] = module_name

    competence_order = sorted(
        {
            info["competence_code"]
            for info in ac_index.values()
        }
    )

    for ac_id, info in sorted(
        ac_index.items(),
        key=lambda item: (
            item[1]["competence_code"],
            _safe_int(item[1]["niveau"]),
            item[1]["ac_code"],
        ),
    ):
        comp_id = info["competence_id"]
        niveau_id = info["niveau_id"]
        comp_code = info["competence_code"]
        niveau = info["niveau"]

        # Compétence
        if comp_id not in node_parent:
            node_parent[comp_id] = root_id
            node_label[comp_id] = _shorten(
                info["competence_name"],
                45
            )
            node_hover[comp_id] = (
                f"<b>{comp_code}</b><br>"
                f"{info['competence_name']}"
            )
            node_meta[comp_id] = {
                "type": "competence",
                "competence_code": comp_code,
            }

        # Niveau
        if niveau_id not in node_parent:
            node_parent[niveau_id] = comp_id
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

        # AC
        module_count = len(info["modules"])

        node_parent[ac_id] = niveau_id
        node_label[ac_id] = info["ac_code"]
        node_value[ac_id] = max(module_count, 1)

        node_hover[ac_id] = (
            f"<b>{info['ac_code']}</b><br>"
            f"{info['ac_description']}<br>"
            f"Modules liés : {module_count}"
        )

        node_meta[ac_id] = {
            "type": "ac",
            "competence_code": comp_code,
            "niveau": niveau,
        }

        # Modules toujours affichés dans l'anneau externe.
        for module_code, module_name in sorted(info["modules"].items()):
            module_id = f"MOD::{ac_id}::{module_code}"

            node_parent[module_id] = ac_id
            node_label[module_id] = module_code
            node_value[module_id] = 1

            node_hover[module_id] = (
                f"<b>{module_code}</b><br>"
                f"{module_name}<br>"
                f"AC parent : {info['ac_code']}"
            )

            node_meta[module_id] = {
                "type": "module",
                "competence_code": comp_code,
                "niveau": niveau,
            }

    # Calcul des valeurs des parents.
    # On remonte depuis les modules vers les AC, niveaux, compétences, root.
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

    colors = [
        _node_color(node_id, node_meta, competence_order)
        for node_id in ids
    ]

    return {
        "ids": ids,
        "labels": [
            node_label[node_id]
            for node_id in ids
        ],
        "parents": [
            node_parent[node_id]
            for node_id in ids
        ],
        "values": [
            node_value.get(node_id, 0)
            for node_id in ids
        ],
        "hovertexts": [
            node_hover.get(node_id, node_label[node_id])
            for node_id in ids
        ],
        "colors": colors,
        "node_meta": node_meta,
        "ac_index": ac_index,
    }


def create_sunburst_figure(rows, selected_programme=None, semester="all"):
    """
    Crée la figure Plotly Sunburst.
    """

    if not rows:
        return empty_figure("Aucune donnée disponible pour le Sunburst APC")

    root_label = "APC"

    if selected_programme:
        root_label = selected_programme.split("::")[-1]

    data = build_sunburst_nodes(
        rows,
        root_label=root_label
    )

    if len(data["ids"]) <= 1:
        return empty_figure(
            "Aucun lien compétence → AC → module détecté"
        )

    title_suffix = _format_semestre(semester)

    fig = go.Figure(
        go.Sunburst(
            ids=data["ids"],
            labels=data["labels"],
            parents=data["parents"],
            values=data["values"],
            branchvalues="total",
            marker=dict(
                colors=data["colors"],
                line=dict(
                    color="#FFFFFF",
                    width=1.2
                ),
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

    fig.update_layout(
    title=dict(
        text=(
            "<b>Sunburst APC</b><br>"
            f"<span style='font-size:12px;color:#64748B'>"
            f"Compétences → niveaux → AC → modules · {title_suffix}"
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
    margin=dict(
        t=80,
        l=20,
        r=20,
        b=20
    ),
    uniformtext=dict(
        minsize=9,
        mode="hide"
    ),

    
    uirevision=f"{selected_programme}-{semester}",
)

    return fig

# ══════════════════════════════════════════════════════════════════════════════
#  PANNEAU DÉTAIL AU CLIC
# ══════════════════════════════════════════════════════════════════════════════

def get_clicked_node_id(click_data):
    """
    Récupère l'identifiant du nœud cliqué dans le Sunburst.

    Plotly renvoie les informations du clic dans clickData.
    Sur un Sunburst, l'id du point est normalement disponible dans :
    clickData["points"][0]["id"].
    """
    if not click_data:
        return None

    points = click_data.get("points", [])

    if not points:
        return None

    return points[0].get("id")


def build_detail_index(rows):
    """
    Construit un index analytique à partir des lignes plates APC.

    Cet index permet de retrouver rapidement :
    - les informations d'une compétence ;
    - les informations d'un niveau ;
    - les informations d'un AC ;
    - les informations d'un module.

    Aucun hardcoding :
    tout est reconstruit depuis les rows produites par build_visualisation_rows().
    """

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

        if not comp_code or not ac_code or not module_code:
            continue

        comp_id = f"COMP::{comp_code}"
        niveau_id = f"NIV::{comp_code}::N{niveau}"
        ac_id = f"AC::{ac_code}"
        module_id = f"MOD::{ac_id}::{module_code}"

        index["root"]["competences"].add(comp_code)
        index["root"]["niveaux"].add((comp_code, niveau))
        index["root"]["acs"].add(ac_code)
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

        index["acs"][ac_id]["modules"][module_code] = module_name

        if semestre is not None:
            index["acs"][ac_id]["semestres"].add(semestre)

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
    """
    Ligne simple dans le panneau détail.
    """
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
        style={
            "marginBottom": "12px"
        },
    )


def module_badges(modules, max_items=40):
    """
    Affiche les modules sous forme de badges.
    """
    if isinstance(modules, dict):
        modules = list(modules.keys())

    modules = sorted(list(modules or []))

    if not modules:
        return html.P(
            "Aucun module lié.",
            style={
                "fontSize": "12px",
                "color": "#94A3B8",
                "margin": "0",
            },
        )

    visible_modules = modules[:max_items]
    hidden_count = max(len(modules) - max_items, 0)

    return html.Div(
        [
            html.Div(
                [
                    tag(
                        module,
                        "#DBEAFE",
                        "#1E3A8A"
                    )
                    for module in visible_modules
                ]
            ),
            html.Div(
                f"+ {hidden_count} autre(s) module(s)"
                if hidden_count > 0
                else "",
                style={
                    "fontSize": "11px",
                    "color": "#64748B",
                    "fontWeight": "600",
                    "marginTop": "6px",
                },
            ),
        ]
    )


def build_empty_detail_panel():
    """
    Panneau affiché avant le premier clic.
    """
    return html.Div(
        [
            html.H3(
                "Détail de la sélection",
                style={
                    "margin": "0 0 8px",
                    "fontSize": "17px",
                    "color": "#0F172A",
                },
            ),
            html.P(
                "Clique sur une compétence, un niveau, un AC ou un module dans le Sunburst pour afficher le détail ici.",
                style={
                    "fontSize": "13px",
                    "color": "#64748B",
                    "lineHeight": "1.5",
                    "margin": "0 0 14px",
                },
            ),
            html.Div(
                [
                    html.Div("Lecture", style=STAT_LABEL_STYLE),
                    html.P(
                        "La taille d’un segment représente le nombre de modules liés. Une zone plus grande signifie donc une couverture pédagogique plus forte dans les données.",
                        style={
                            "fontSize": "12px",
                            "color": "#334155",
                            "lineHeight": "1.5",
                            "margin": "0",
                        },
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
        style={
            **CARD_STYLE,
            "height": "100%",
            "marginBottom": 0,
        },
    )


def build_selection_detail_panel(rows, click_data):
    """
    Construit le panneau détail selon le nœud cliqué dans le Sunburst.
    """

    node_id = get_clicked_node_id(click_data)

    if not node_id:
        return build_empty_detail_panel()

    index = build_detail_index(rows)

    # Racine
    if node_id.startswith("ROOT::"):
        return html.Div(
            [
                html.H3(
                    "Vue globale APC",
                    style={
                        "margin": "0 0 12px",
                        "fontSize": "17px",
                        "color": "#0F172A",
                    },
                ),
                detail_line(
                    "Compétences",
                    len(index["root"]["competences"])
                ),
                detail_line(
                    "Niveaux",
                    len(index["root"]["niveaux"])
                ),
                detail_line(
                    "AC",
                    len(index["root"]["acs"])
                ),
                detail_line(
                    "Modules liés",
                    len(index["root"]["modules"])
                ),
                html.H4(
                    "Interprétation",
                    style={
                        "fontSize": "13px",
                        "margin": "14px 0 6px",
                        "color": "#0F172A",
                    },
                ),
                html.P(
                    "Cette vue permet de comparer la couverture pédagogique globale des compétences par les modules, ressources ou SAE.",
                    style={
                        "fontSize": "12px",
                        "color": "#64748B",
                        "lineHeight": "1.5",
                    },
                ),
            ],
            style={
                **CARD_STYLE,
                "height": "100%",
                "marginBottom": 0,
            },
        )

    # Compétence
    if node_id.startswith("COMP::"):
        item = index["competences"].get(node_id)

        if not item:
            return build_empty_detail_panel()

        return html.Div(
            [
                html.H3(
                    "Compétence sélectionnée",
                    style={
                        "margin": "0 0 12px",
                        "fontSize": "17px",
                        "color": "#0F172A",
                    },
                ),
                detail_line("Code", item["code"]),
                detail_line("Nom", item["nom"]),
                detail_line("Niveaux", len(item["niveaux"])),
                detail_line("AC liés", len(item["acs"])),
                detail_line("Modules liés", len(item["modules"])),
                detail_line(
                    "Semestres",
                    ", ".join(map(str, sorted(item["semestres"], key=sort_semester)))
                    if item["semestres"]
                    else "Non renseigné"
                ),
                html.H4(
                    "Modules liés",
                    style={
                        "fontSize": "13px",
                        "margin": "14px 0 8px",
                        "color": "#0F172A",
                    },
                ),
                module_badges(item["modules"]),
            ],
            style={
                **CARD_STYLE,
                "height": "100%",
                "marginBottom": 0,
                "overflowY": "auto",
            },
        )

    # Niveau
    if node_id.startswith("NIV::"):
        item = index["niveaux"].get(node_id)

        if not item:
            return build_empty_detail_panel()

        return html.Div(
            [
                html.H3(
                    "Niveau sélectionné",
                    style={
                        "margin": "0 0 12px",
                        "fontSize": "17px",
                        "color": "#0F172A",
                    },
                ),
                detail_line("Compétence", item["competence_code"]),
                detail_line("Nom compétence", item["competence_nom"]),
                detail_line("Niveau", item["niveau"]),
                detail_line("AC liés", len(item["acs"])),
                detail_line("Modules liés", len(item["modules"])),
                html.H4(
                    "Modules liés",
                    style={
                        "fontSize": "13px",
                        "margin": "14px 0 8px",
                        "color": "#0F172A",
                    },
                ),
                module_badges(item["modules"]),
            ],
            style={
                **CARD_STYLE,
                "height": "100%",
                "marginBottom": 0,
                "overflowY": "auto",
            },
        )

    # AC
    if node_id.startswith("AC::"):
        item = index["acs"].get(node_id)

        if not item:
            return build_empty_detail_panel()

        return html.Div(
            [
                html.H3(
                    "Apprentissage critique sélectionné",
                    style={
                        "margin": "0 0 12px",
                        "fontSize": "17px",
                        "color": "#0F172A",
                    },
                ),
                detail_line("AC", item["code"]),
                detail_line("Compétence", item["competence_code"]),
                detail_line("Niveau", item["niveau"]),
                detail_line("Modules liés", len(item["modules"])),
                html.H4(
                    "Description",
                    style={
                        "fontSize": "13px",
                        "margin": "14px 0 6px",
                        "color": "#0F172A",
                    },
                ),
                html.P(
                    item["description"],
                    style={
                        "fontSize": "12px",
                        "color": "#334155",
                        "lineHeight": "1.5",
                        "backgroundColor": "#F8FAFC",
                        "border": "1px solid #E2E8F0",
                        "borderRadius": "10px",
                        "padding": "10px",
                    },
                ),
                html.H4(
                    "Modules liés",
                    style={
                        "fontSize": "13px",
                        "margin": "14px 0 8px",
                        "color": "#0F172A",
                    },
                ),
                module_badges(item["modules"]),
            ],
            style={
                **CARD_STYLE,
                "height": "100%",
                "marginBottom": 0,
                "overflowY": "auto",
            },
        )

    # Module
    if node_id.startswith("MOD::"):
        item = index["modules"].get(node_id)

        if not item:
            return build_empty_detail_panel()

        return html.Div(
            [
                html.H3(
                    "Module sélectionné",
                    style={
                        "margin": "0 0 12px",
                        "fontSize": "17px",
                        "color": "#0F172A",
                    },
                ),
                detail_line("Code module", item["code"]),
                detail_line("Nom module", item["nom"]),
                detail_line("AC parent", item["ac_code"]),
                detail_line("Compétence", item["competence_code"]),
                detail_line("Niveau", item["niveau"]),
                detail_line(
                    "Semestre",
                    item["semestre"] if item["semestre"] is not None else "Non renseigné"
                ),
                html.H4(
                    "AC associé",
                    style={
                        "fontSize": "13px",
                        "margin": "14px 0 6px",
                        "color": "#0F172A",
                    },
                ),
                html.P(
                    item["ac_description"],
                    style={
                        "fontSize": "12px",
                        "color": "#334155",
                        "lineHeight": "1.5",
                        "backgroundColor": "#F8FAFC",
                        "border": "1px solid #E2E8F0",
                        "borderRadius": "10px",
                        "padding": "10px",
                    },
                ),
            ],
            style={
                **CARD_STYLE,
                "height": "100%",
                "marginBottom": 0,
                "overflowY": "auto",
            },
        )

    return build_empty_detail_panel()

# ══════════════════════════════════════════════════════════════════════════════
#  STATISTIQUES DATA ANALYSTE
# ══════════════════════════════════════════════════════════════════════════════



def tag(text, bg="#F1F5F9", color="#334155"):
    """
    Badge utilisé pour afficher les modules d'un AC.
    """
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
                        html.Span(
                            "☀️",
                            style={
                                "fontSize": "34px",
                                "marginRight": "12px"
                            }
                        ),
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
                                    style={
                                        "color": "#64748B",
                                        "fontSize": "13px",
                                        "margin": "0",
                                    },
                                ),
                            ]
                        ),
                    ],
                    style={
                        "display": "flex",
                        "alignItems": "center"
                    },
                )
            ],
            style={
                "marginBottom": "18px"
            },
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Label(
                            "Formation",
                            style=LABEL_STYLE
                        ),
                        dcc.Dropdown(
                            id="sunburst-programme-selector",
                            options=programme_options,
                            value=None,
                            clearable=False,
                            style={
                                "fontSize": "14px"
                            },
                        ),
                    ],
                    style={
                        "width": "38%",
                        "minWidth": "250px"
                    },
                ),
                html.Div(
                    [
                        html.Label(
                            "Semestre",
                            style=LABEL_STYLE
                        ),
                        dcc.Dropdown(
                            id="sunburst-semester-filter",
                            options=[
                                {
                                    "label": "Tous les semestres",
                                    "value": "all"
                                }
                            ],
                            value="all",
                            clearable=False,
                            style={
                                "fontSize": "14px"
                            },
                        ),
                    ],
                    style={
                        "width": "18%",
                        "minWidth": "150px"
                    },
                ),
                html.Div(
                    [
                        html.Label(
                            "Spécialité / parcours",
                            style=LABEL_STYLE
                        ),
                        dcc.Dropdown(
                            id="sunburst-specialite-filter",
                            options=[
                                {
                                    "label": "Toutes les spécialités",
                                    "value": "all"
                                }
                            ],
                            value="all",
                            clearable=False,
                            style={
                                "fontSize": "14px"
                            },
                        ),
                    ],
                    style={
                        "width": "24%",
                        "minWidth": "210px"
                    },
                ),
                html.Div(
                    [
                        html.Label(
                            "Lecture",
                            style=LABEL_STYLE
                        ),
                        html.Div(
                            "Taille = nombre de modules uniques liés à chaque AC",
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
                    style={
                        "minWidth": "260px"
                    },
                ),
            ],
            style={
                **CARD_STYLE,
                "display": "flex",
                "alignItems": "flex-end",
                "flexWrap": "wrap",
                "gap": "16px",
            },
        ),
        dcc.Store(
            id="sunburst-rows-store"
        ),
        html.Div(
    [
        html.Div(
            [
                dcc.Graph(
                    id="sunburst-graph",
                    style={
                        "height": "980px"
                    },
                    config={
                        "displayModeBar": True,
                        "displaylogo": False,
                        "responsive": True,
                        "scrollZoom": True,
                    },
                )
            ],
            style={
                **CARD_STYLE,
                "flex": "3",
                "marginBottom": 0,
                "minWidth": "720px",
            },
        ),
        html.Div(
            id="sunburst-detail-panel",
            style={
                "flex": "1",
                "minWidth": "320px",
                "maxHeight": "980px",
            },
        ),
    ],
    style={
        "display": "flex",
        "gap": "16px",
        "alignItems": "stretch",
        "flexWrap": "wrap",
    },
),
    ],
    style=PAGE_STYLE,
)

def get_filtered_sunburst_rows(stored_rows, semester, specialite):
    """
    Applique les filtres de spécialité/parcours et de semestre.

    Cette fonction évite de dupliquer la même logique dans plusieurs callbacks.
    """
    if not stored_rows:
        return []

    filtered_rows = filter_rows_by_specialite(
        stored_rows,
        specialite
    )

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
    """
    Enregistre les callbacks de la page Sunburst APC.
    """

    @app.callback(
        Output("sunburst-programme-selector", "value"),
        Input("sunburst-programme-selector", "options"),
        State("sunburst-programme-selector", "value"),
        prevent_initial_call=False,
    )
    def init_sunburst_programme_selector(options, current_value):
        """
        Initialise le sélecteur de formation avec le premier programme disponible.
        """
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
        """
        Charge les lignes APC pour la formation sélectionnée.
        """
        comp_data, curr_data = get_selected_data(selected_programme)

        rows = build_visualisation_rows(
            comp_data,
            curr_data
        )

        semestres = sorted(
            {
                row.get("semestre")
                for row in rows
                if row.get("semestre") is not None
            },
            key=sort_semester,
        )

        semester_options = [
            {
                "label": "Tous les semestres",
                "value": "all"
            }
        ] + [
            {
                "label": f"Semestre {semestre}",
                "value": str(semestre)
            }
            for semestre in semestres
        ]

        specialite_options = get_specialite_options_from_rows(rows)

        return rows, semester_options, specialite_options, "all"

    @app.callback(
    Output("sunburst-graph", "figure"),
    Input("sunburst-rows-store", "data"),
    Input("sunburst-programme-selector", "value"),
    Input("sunburst-semester-filter", "value"),
    Input("sunburst-specialite-filter", "value"),
    )
    def update_sunburst_figure(
        stored_rows,
        selected_programme,
        semester,
        specialite
    ):
        """
        Met à jour uniquement la figure Sunburst.

        Important :
        ce callback ne dépend PAS de clickData.
        Sinon, chaque clic recrée la figure et annule la navigation native du Sunburst.
        """

        filtered_rows = get_filtered_sunburst_rows(
            stored_rows,
            semester,
            specialite
        )

        if not filtered_rows:
            return empty_figure(
                "Aucune donnée pour les filtres sélectionnés"
            )

        return create_sunburst_figure(
            filtered_rows,
            selected_programme=selected_programme,
            semester=semester,
        )
    @app.callback(
    Output("sunburst-detail-panel", "children"),
    Input("sunburst-graph", "clickData"),
    Input("sunburst-rows-store", "data"),
    Input("sunburst-semester-filter", "value"),
    Input("sunburst-specialite-filter", "value"),
    )
    def update_sunburst_detail_panel(
        click_data,
        stored_rows,
        semester,
        specialite
    ):
        """
        Met à jour uniquement le panneau détail.

        Le Sunburst n'est pas régénéré ici.
        La navigation Plotly reste donc fluide :
        - clic sur compétence ;
        - clic sur niveau ;
        - clic sur AC ;
        - clic sur module.
        """

        filtered_rows = get_filtered_sunburst_rows(
            stored_rows,
            semester,
            specialite
        )

        if not filtered_rows:
            return build_empty_detail_panel()

        return build_selection_detail_panel(
            filtered_rows,
            click_data
        )