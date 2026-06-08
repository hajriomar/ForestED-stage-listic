from statistics import mode

from dash import html, dcc, Input, Output, State, ctx
import plotly.graph_objects as go
import networkx as nx

from app_tools import load_processed_files, build_programmes_summary


PAGE_STYLE = {
    "backgroundColor": "#F4F6F9",
    "minHeight": "100vh",
    "padding": "35px",
    "fontFamily": "Segoe UI, Arial, sans-serif"
}

CARD_STYLE = {
    "backgroundColor": "white",
    "padding": "24px",
    "borderRadius": "16px",
    "boxShadow": "0 6px 18px rgba(0,0,0,0.08)",
    "marginBottom": "24px"
}

#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! A verifier pour mettre un format generic !!!!!!!!!!!!!!!!!!!!!!!!!!!!!
def normalize_module_code(code):
    if not code:
        return None

    text = str(code).strip().upper()
    text = text.replace("SAÉ", "SAE")

    # "R1.01 - Anglais" -> "R1.01"
    if " - " in text:
        text = text.split(" - ")[0].strip()

    
    # "R1_01_ANGLAIS" -> "R1.01"
    if text.startswith("SAE") or text.startswith("R"):
        parts = text.split("_")

        if len(parts) >= 2 and parts[1].isdigit():
            return f"{parts[0]}.{parts[1]}"

    # "INFO502_PACY" -> "INFO502"
    if "_" in text:
        return text.split("_")[0].strip()

    return text


def sort_semester(value):
    try:
        return int(str(value).replace("S", ""))
    except Exception:
        return 999


def get_programme_options():
    datasets = load_processed_files()
    programmes = build_programmes_summary(datasets)

    return [
        {
            "label": f"{item['source']} - {item['programme']}",
            "value": f"{item['source']}::{item['programme']}"
        }
        for item in programmes
    ]


programme_options = get_programme_options()
default_programme = programme_options[0]["value"] if programme_options else None


def get_selected_data(selected_programme):
    datasets = load_processed_files()

    if not selected_programme:
        return None, None

    source, programme = selected_programme.split("::")

    competence_data = None
    curriculum_data = None

    for item in datasets["competence"]:
        if item["source"] == source and item["programme"] == programme:
            competence_data = item["data"]

    for item in datasets["curriculum"]:
        if item["source"] == source and item["programme"] == programme:
            curriculum_data = item["data"]

    return competence_data, curriculum_data


def build_visualisation_rows(competence_data, curriculum_data):
    rows = []

    if not competence_data or not curriculum_data:
        return rows

    competence_items = []

    for sous in competence_data.get("sous_classifications", []):
        sous_code = sous.get("code")

        for comp in sous.get("competences", []):
            comp_code = comp.get("code")
            comp_name = comp.get("nom")

            for niveau in comp.get("niveaux_developpement", []):
                niveau_value = niveau.get("niveau")

                for ac in niveau.get("apprentissages_critiques", []):
                    modules = ac.get("modules", [])

                    for module_code in modules:
                        competence_items.append({
                            "sous_classification": sous_code,
                            "competence_code": comp_code,
                            "competence_name": comp_name,
                            "niveau": niveau_value,
                            "ac_code": ac.get("code"),
                            "ac_description": ac.get("description"),
                            "module_code": normalize_module_code(module_code)
                        })

    for periode in curriculum_data.get("periodes", []):
        semestre = periode.get("numero") or periode.get("id")

        for ue in periode.get("unites_enseignement", []):
            ue_code = ue.get("code")
            ue_name = ue.get("intitule")

            for element in ue.get("elements_pedagogiques", []):
                module_id = element.get("id")
                module_code = normalize_module_code(module_id)
                module_name = element.get("nom")
                acquis = element.get("acquis", [])

                linked_competences = [
                    item for item in competence_items
                    if item["module_code"] == module_code
                ]

                for comp in linked_competences:
                    if acquis:
                        for acq in acquis:
                            rows.append({
                                "semestre": semestre,
                                "ue_code": ue_code,
                                "ue_name": ue_name,
                                "module_id": module_id,
                                "module_code": module_code,
                                "module_name": module_name,
                                "acquis_id": acq.get("id"),
                                "acquis_description": acq.get("description"),
                                **comp
                            })
                    else:
                        rows.append({
                            "semestre": semestre,
                            "ue_code": ue_code,
                            "ue_name": ue_name,
                            "module_id": module_id,
                            "module_code": module_code,
                            "module_name": module_name,
                            "acquis_id": None,
                            "acquis_description": None,
                            **comp
                        })

    return rows


def empty_figure(message):
    fig = go.Figure()
    fig.update_layout(
        title=message,
        height=600,
        plot_bgcolor="white",
        paper_bgcolor="white"
    )
    return fig


def create_global_heatmap(rows):
    if not rows:
        return empty_figure("Aucun lien module-compétence détecté")

    semesters = sorted(
        {r["semestre"] for r in rows if r["semestre"] is not None},
        key=sort_semester
    )

    competences = sorted(
        {r["competence_code"] for r in rows if r["competence_code"]}
    )

    z = []

    for sem in semesters:
        line = []
        for comp in competences:
            count = len({
                r["module_id"]
                for r in rows
                if r["semestre"] == sem and r["competence_code"] == comp
            })
            line.append(count)
        z.append(line)

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=competences,
            y=[f"S{sem}" for sem in semesters],
            colorscale="Blues",
            hoverongaps=False
        )
    )

    fig.update_layout(
        title="Heatmap globale : Semestres × Compétences",
        xaxis_title="Compétences",
        yaxis_title="Semestres",
        height=700,
        paper_bgcolor="white",
        plot_bgcolor="white"
    )

    return fig


def create_semester_heatmap(rows, semester):
    semester_rows = [
        r for r in rows
        if str(r["semestre"]) == str(semester)
    ]

    if not semester_rows:
        return empty_figure(f"Aucune donnée pour le semestre {semester}")

    modules = sorted({
        r["module_id"]
        for r in semester_rows
        if r["module_id"]
    })

    competences = sorted({
        r["competence_code"]
        for r in semester_rows
        if r["competence_code"]
    })

    z = []

    for module in modules:
        line = []
        for comp in competences:
            count = len([
                r for r in semester_rows
                if r["module_id"] == module
                and r["competence_code"] == comp
            ])
            line.append(count)
        z.append(line)

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=competences,
            y=modules,
            colorscale="Blues",
            hoverongaps=False
        )
    )

    fig.update_layout(
        title=f"Heatmap semestre {semester} : Modules × Compétences",
        xaxis_title="Compétences",
        yaxis_title="Modules",
        height=800,
        paper_bgcolor="white",
        plot_bgcolor="white"
    )

    return fig


def create_module_heatmap(rows, module_id):
    module_rows = [
        r for r in rows
        if r["module_id"] == module_id
    ]

    if not module_rows:
        return empty_figure(f"Aucune donnée pour le module {module_id}")

    acquis = sorted({
        r["acquis_id"] or "Acquis non renseigné"
        for r in module_rows
    })

    competences = sorted({
        r["competence_code"]
        for r in module_rows
        if r["competence_code"]
    })

    z = []

    for acq in acquis:
        line = []
        for comp in competences:
            count = len([
                r for r in module_rows
                if (r["acquis_id"] or "Acquis non renseigné") == acq
                and r["competence_code"] == comp
            ])
            line.append(count)
        z.append(line)

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=competences,
            y=acquis,
            colorscale="Blues",
            hoverongaps=False
        )
    )

    fig.update_layout(
        title=f"Heatmap module {module_id} : Acquis × Compétences",
        xaxis_title="Compétences",
        yaxis_title="Acquis d’apprentissage",
        height=750,
        paper_bgcolor="white",
        plot_bgcolor="white"
    )

    return fig


def create_forest_graph(rows, selected_node=None):
    if not rows:
        return empty_figure("Aucun lien module-compétence détecté")

    graph = nx.Graph()

    for r in rows:
        module_node = f"MODULE::{r['module_id']}"
        ac_node = f"AC::{r['ac_code']}"
        comp_node = f"COMP::{r['competence_code']}"

        graph.add_node(
            module_node,
            label=r["module_code"],
            type="module",
            hover=f"Module : {r['module_id']}<br>{r.get('module_name', '')}"
        )

        graph.add_node(
            ac_node,
            label="",
            type="ac",
            hover=f"AC : {r['ac_code']}<br>{r.get('ac_description', '')}"
        )

        graph.add_node(
            comp_node,
            label=r["competence_code"],
            type="competence",
            hover=f"Compétence : {r['competence_code']}<br>{r.get('competence_name', '')}"
        )

        graph.add_edge(module_node, ac_node)
        graph.add_edge(ac_node, comp_node)

    highlighted_nodes = set()
    highlighted_edges = set()

    if selected_node and selected_node in graph:
        highlighted_nodes.add(selected_node)

        selected_type = graph.nodes[selected_node]["type"]

        if selected_type == "competence":
            for ac_node in graph.neighbors(selected_node):
                highlighted_nodes.add(ac_node)
                highlighted_edges.add(tuple(sorted([selected_node, ac_node])))

                for module_node in graph.neighbors(ac_node):
                    if graph.nodes[module_node]["type"] == "module":
                        highlighted_nodes.add(module_node)
                        highlighted_edges.add(tuple(sorted([ac_node, module_node])))

        elif selected_type == "ac":
            for neighbor in graph.neighbors(selected_node):
                highlighted_nodes.add(neighbor)
                highlighted_edges.add(tuple(sorted([selected_node, neighbor])))

        elif selected_type == "module":
            for ac_node in graph.neighbors(selected_node):
                highlighted_nodes.add(ac_node)
                highlighted_edges.add(tuple(sorted([selected_node, ac_node])))

                for comp_node in graph.neighbors(ac_node):
                    if graph.nodes[comp_node]["type"] == "competence":
                        highlighted_nodes.add(comp_node)
                        highlighted_edges.add(tuple(sorted([ac_node, comp_node])))
    pos = {}

    row_y = {
        "module": 10,
        "ac": 5,
        "competence": 0
    }

    x_spacing = {
        "module": 1.8,
        "ac": 1.4,
        "competence": 6
    }

    for node_type in ["module", "ac", "competence"]:
        nodes = sorted([
            node for node, data in graph.nodes(data=True)
            if data["type"] == node_type
        ])

        for index, node in enumerate(nodes):
            pos[node] = (
                (index - (len(nodes) - 1) / 2) * x_spacing[node_type],
                row_y[node_type]
            )

    active_edges_x = []
    active_edges_y = []
    inactive_edges_x = []
    inactive_edges_y = []

    for source, target in graph.edges():
        x0, y0 = pos[source]
        x1, y1 = pos[target]

        edge_key = tuple(sorted([source, target]))

        is_active = (
            selected_node
            and edge_key in highlighted_edges
        )

        if is_active:
            active_edges_x.extend([x0, x1, None])
            active_edges_y.extend([y0, y1, None])
        else:
            inactive_edges_x.extend([x0, x1, None])
            inactive_edges_y.extend([y0, y1, None])

    inactive_edge_trace = go.Scatter(
        x=inactive_edges_x,
        y=inactive_edges_y,
        mode="lines",
        line=dict(
            width=0.8,
            color="rgba(120,120,120,0.28)"
        ),
        hoverinfo="none",
        showlegend=False
    )

    active_edge_trace = go.Scatter(
        x=active_edges_x,
        y=active_edges_y,
        mode="lines",
        line=dict(
            width=2.2,
            color="rgba(30,41,59,0.75)"
        ),
        hoverinfo="none",
        showlegend=False
    )

    styles = {
        "module": {
            "color": "#2563EB",
            "size": 10,
            "symbol": "square",
            "name": "Modules"
        },
        "ac": {
            "color": "#22C55E",
            "size": 7,
            "symbol": "circle",
            "name": "Apprentissages critiques"
        },
        "competence": {
            "color": "#F97316",
            "size": 15,
            "symbol": "diamond",
            "name": "Compétences"
        }
    }

    traces = []

    for node_type, style in styles.items():
        x_values = []
        y_values = []
        hover_texts = []
        customdata = []
        opacity_values = []
        sizes = []

        for node, data in graph.nodes(data=True):
            if data["type"] != node_type:
                continue

            x, y = pos[node]

            is_active = (
                not selected_node
                or node in highlighted_nodes
            )

            x_values.append(x)
            y_values.append(y)
            hover_texts.append(data["hover"])
            customdata.append(node)
            opacity_values.append(1.0 if is_active else 0.15)
            sizes.append(style["size"] + 5 if node == selected_node else style["size"])

        traces.append(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="markers",
                customdata=customdata,
                hovertext=hover_texts,
                hoverinfo="text",
                name=style["name"],
                marker=dict(
                    color=style["color"],
                    size=sizes,
                    opacity=opacity_values,
                    symbol=style["symbol"],
                    line=dict(
                        width=1,
                        color="#111827"
                    )
                )
            )
        )

    row_labels = go.Scatter(
        x=[min(x for x, y in pos.values()) - 5] * 3,
        y=[row_y["module"], row_y["ac"], row_y["competence"]],
        text=[
            "Modules",
            "Apprentissages critiques",
            "Compétences"
        ],
        mode="text",
        textfont=dict(
            size=16,
            color="#334155"
        ),
        hoverinfo="none",
        showlegend=False
    )

    fig = go.Figure(
        data=[
            inactive_edge_trace,
            active_edge_trace
        ] + traces + [row_labels]
    )

    fig.update_layout(
        title="Graphe de relations pédagogiques",
        height=850,
        clickmode="event+select",
        showlegend=True,
        paper_bgcolor="white",
        plot_bgcolor="#F8FAFC",
        margin=dict(l=120, r=40, t=80, b=40),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[-1.5, 11.5]
        )
    )

    return fig


forested_visualisations_layout = html.Div([

    html.H1("Exploration des formations"),

    html.P(
        """
        Analyse des relations entre modules,
        apprentissages critiques et compétences.
        """,
        style={"fontSize": "17px", "color": "#64748B"}
    ),

    html.Div([

        html.Div([
            html.Label("Formation", style={"fontWeight": "700"}),

            dcc.Dropdown(
                id="programme-selector",
                options=programme_options,
                value=default_programme,
                clearable=False
            )
        ], style={"width": "35%"}),

        html.Div([
            html.Label("Mode", style={"fontWeight": "700"}),

            dcc.RadioItems(
                id="visualisation-mode",
                options=[
                    {"label": "Graphe de relations", "value": "graph"},
                    {"label": "Heatmap", "value": "heatmap"}
                ],
                value="graph",
                inline=True
            )
        ], style={"width": "25%"}),

        html.Button(
            "Retour",
            id="visualisation-back",
            n_clicks=0,
            style={
                "height": "38px",
                "marginTop": "18px"
            }
        )

    ], style={
        **CARD_STYLE,
        "display": "flex",
        "gap": "35px",
        "alignItems": "center"
    }),

    dcc.Store(
        id="visualisation-state",
        data={
            "level": 0,
            "semester": None,
            "module": None
        }
    ),
    dcc.Store(id="selected-forest-node"),

    html.Div([
        dcc.Graph(
            id="forest-graph",
            config={"displayModeBar": True}
        )
    ], style=CARD_STYLE)

], style=PAGE_STYLE)


def register_callbacks(app):

    @app.callback(
    Output("forest-graph", "figure"),
    Output("selected-forest-node", "data"),
    Input("forest-graph", "clickData"),
    Input("programme-selector", "value"),
    Input("visualisation-mode", "value"),
    State("selected-forest-node", "data")
    )
    def update_forest_graph(click_data, selected_programme, mode, selected_node):
        competence_data, curriculum_data = get_selected_data(selected_programme)

        rows = build_visualisation_rows(
        competence_data,
        curriculum_data
        )

        triggered = ctx.triggered_id

        if triggered in ["programme-selector", "visualisation-mode"]:
            selected_node = None

        if mode == "heatmap":
            return create_global_heatmap(rows), None

        if click_data and mode == "graph":
            clicked_node = click_data["points"][0].get("customdata")

            if clicked_node == selected_node:
                return create_forest_graph(rows), None

            return create_forest_graph(rows, clicked_node), clicked_node

        return create_forest_graph(rows, selected_node), selected_node