from dash import html

from app_tools import (
    load_processed_files,
    build_programmes_summary,
    compute_global_stats,
    count_competence_modules
)


CARD_STYLE = {
    "backgroundColor": "white",
    "padding": "25px",
    "borderRadius": "14px",
    "boxShadow": "0 4px 12px rgba(0,0,0,0.10)",
    "width": "220px",
    "textAlign": "center",
}

TITLE_STYLE = {
    "fontSize": "16px",
    "color": "#666",
    "marginBottom": "10px",
}

NUMBER_STYLE = {
    "fontSize": "42px",
    "fontWeight": "700",
    "color": "#1F6FEB",
}


def stat_card(title, value):
    return html.Div([
        html.Div(title, style=TITLE_STYLE),
        html.Div(value, style=NUMBER_STYLE),
    ], style=CARD_STYLE)


def status_badge(label, active):
    return html.Span(
        label,
        style={
            "backgroundColor": "#DCFCE7" if active else "#FEE2E2",
            "color": "#166534" if active else "#991B1B",
            "padding": "5px 12px",
            "borderRadius": "999px",
            "fontSize": "13px",
            "fontWeight": "600",
            "marginRight": "8px"
        }
    )


def programme_card(item):
    return html.Div([
        html.Div([
            html.Div(
                item["source"],
                style={
                    "fontSize": "14px",
                    "fontWeight": "700",
                    "color": "#1F6FEB",
                    "textTransform": "uppercase"
                }
            ),
            html.H3(
                item["programme"],
                style={
                    "margin": "6px 0 14px 0",
                    "fontSize": "26px",
                    "color": "#1F2A35"
                }
            ),
        ]),

        html.Div([
            status_badge("Compétence", item["has_competence"]),
            status_badge("Curriculum", item["has_curriculum"]),
        ], style={"marginBottom": "18px"}),

        html.Div([
            html.Div(f"Compétences : {item['competences']}"),
            html.Div(f"AC : {item['ac']}"),
            html.Div(f"Modules liés aux compétences : {item['modules']}"),
            html.Div(f"Éléments pédagogiques extraits : {item['elements_pedagogiques']}"),
            html.Div(f"UE : {item['ue']}"),
        ], style={
            "lineHeight": "1.8",
            "fontSize": "15px",
            "color": "#374151"
        })
    ], style={
        "backgroundColor": "white",
        "padding": "24px",
        "borderRadius": "14px",
        "boxShadow": "0 4px 12px rgba(0,0,0,0.08)",
        "minWidth": "260px",
        "flex": "1"
    })


forested_home_layout = html.Div([

    html.Div([
        html.H1(
            "ForestED Dashboard",
            style={
                "margin": "0",
                "fontSize": "36px",
                "color": "#1F2A35"
            }
        ),
        html.P(
            "Visualisation des compétences et des curricula à partir des données transformées du pipeline ETL.",
            style={
                "fontSize": "17px",
                "color": "#5F6B7A",
                "marginTop": "8px"
            }
        ),
    ], style={
        "marginBottom": "35px"
    }),

    html.Div(id="home-stats"),

    html.Div([
        html.H3(
            "Sources et formations détectées",
            style={
                "marginTop": "35px",
                "marginBottom": "20px",
                "color": "#1F2A35"
            }
        ),
        html.Div(id="home-programmes-list")
    ])

], style={
    "backgroundColor": "#F4F6F9",
    "minHeight": "100vh",
    "padding": "35px",
    "fontFamily": "Segoe UI, Arial, sans-serif"
})


def register_callbacks(app):
    from dash import Input, Output

    @app.callback(
        Output("home-stats", "children"),
        Output("home-programmes-list", "children"),
        Input("url", "pathname")
    )
    def update_home(_):
        datasets = load_processed_files()
        programmes = build_programmes_summary(datasets)
        stats = compute_global_stats(programmes)

        stats_cards = html.Div([
            stat_card("Référentiels", stats["sources"]),
            stat_card("Formations", stats["formations"]),
            stat_card("Compétences", stats["competences"]),
            stat_card("Apprentissages critiques", stats["ac"]),
        ], style={
            "display": "flex",
            "gap": "25px",
            "flexWrap": "wrap",
            "marginBottom": "30px"
        })

        if not programmes:
            programmes_view = html.Div(
                "Aucun fichier processed détecté.",
                style={
                    "backgroundColor": "white",
                    "padding": "24px",
                    "borderRadius": "14px"
                }
            )
        else:
            programmes_view = html.Div([
                programme_card(item)
                for item in programmes
            ], style={
                "display": "flex",
                "gap": "20px",
                "flexWrap": "wrap"
            })

        return stats_cards, programmes_view