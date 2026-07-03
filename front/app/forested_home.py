from dash import html

from app_tools import (
    load_processed_files,
    build_programmes_summary,
    compute_global_stats,
    count_competence_modules
)

from design_tokens import (
    COLORS,
    FONT_FAMILY,
    FONT_FAMILY_SERIF_TITLE,
    SPACE,
    RADIUS,
    SHADOW,
    TYPE,
    badge_style,
)


# ══════════════════════════════════════════════════════════════════════════════
#  STATS — grille 4 colonnes égales, centrée
# ══════════════════════════════════════════════════════════════════════════════

STATS_GRID_STYLE = {
    "display": "grid",
    "gridTemplateColumns": "repeat(4, 1fr)",
    "gap": SPACE["lg"],
    "marginBottom": SPACE["xxl"],
}

STAT_CARD_STYLE = {
    "backgroundColor": COLORS["bg_surface"],
    "border": f"1px solid {COLORS['border']}",
    "padding": "40px 28px",
    "borderRadius": RADIUS["lg"],
    "boxShadow": SHADOW["card"],
    "textAlign": "center",
}

STAT_TITLE_STYLE = {
    "fontFamily": FONT_FAMILY,
    "fontSize": "15px",
    "fontWeight": "600",
    "color": COLORS["text_secondary"],
    "letterSpacing": "0.3px",
    "marginBottom": "14px",
}

STAT_NUMBER_STYLE = {
    "fontFamily": FONT_FAMILY_SERIF_TITLE,
    "fontSize": "52px",
    "fontWeight": "700",
    "color": COLORS["primary"],
    "lineHeight": "1",
}


def stat_card(title, value):
    return html.Div([
        html.Div(title, style=STAT_TITLE_STYLE),
        html.Div(value, style=STAT_NUMBER_STYLE),
    ], style=STAT_CARD_STYLE)


# ══════════════════════════════════════════════════════════════════════════════
#  BADGES & CARTES PROGRAMME
# ══════════════════════════════════════════════════════════════════════════════

def status_badge(label, active):
    return html.Span(label, style=badge_style("success" if active else "danger"))


def programme_card(item):
    return html.Div([
        html.Div([
            html.Div(item["source"], style={
                "fontFamily": FONT_FAMILY,
                "fontSize": "12.5px",
                "fontWeight": "700",
                "color": COLORS["text_muted"],
                "textTransform": "uppercase",
                "letterSpacing": "0.5px",
            }),
            html.H3(item["programme"], style={
                "fontFamily": FONT_FAMILY_SERIF_TITLE,
                "margin": "6px 0 16px 0",
                "fontSize": "28px",
                "fontWeight": "700",
                "color": COLORS["text_primary"],
            }),
        ]),

        html.Div([
            status_badge("Compétence", item["has_competence"]),
            status_badge("Curriculum", item["has_curriculum"]),
        ], style={"marginBottom": "20px"}),

        html.Div([
            html.Div(f"Compétences : {item['competences']}"),
            html.Div(f"AC : {item['ac']}"),
            html.Div(f"Modules liés aux compétences : {item['modules']}"),
            html.Div(f"Éléments pédagogiques extraits : {item['elements_pedagogiques']}"),
            html.Div(f"UE : {item['ue']}"),
        ], style={
            "fontFamily": FONT_FAMILY,
            "lineHeight": "2",
            "fontSize": "15px",
            "color": COLORS["text_secondary"],
        })
    ], style={
        "backgroundColor": COLORS["bg_surface"],
        "border": f"1px solid {COLORS['border']}",
        "padding": SPACE["xl"],
        "borderRadius": RADIUS["lg"],
        "boxShadow": SHADOW["card"],
        "minWidth": "260px",
        "flex": "1",
    })


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT
# ══════════════════════════════════════════════════════════════════════════════

forested_home_layout = html.Div([

    html.Div([
        html.H1(
            "Vue d'ensemble des curricula et compétences",
            style={
                "fontFamily": FONT_FAMILY_SERIF_TITLE,
                "margin": "0",
                "fontSize": "34px",
                "fontWeight": "800",
                "color": COLORS["text_primary"],
                "letterSpacing": "-0.4px",
                "textAlign": "center",
            }
        ),
        html.P(
            "Synthèse des référentiels, formations, compétences et apprentissages critiques issus du pipeline ETL ForestED.",
            style={
                "fontFamily": FONT_FAMILY,
                "fontSize": "16px",
                "color": COLORS["text_secondary"],
                "marginTop": "10px",
                "textAlign": "center",
            }
        ),
    ], style={"marginBottom": SPACE["xxl"]}),

    html.Div(id="home-stats"),

    html.Div([
        html.H3("Sources et formations détectées", style={
            **TYPE["h3"],
            "marginBottom": SPACE["lg"],
            "fontSize": "18px",
        }),
        html.Div(id="home-programmes-list")
    ]),

], style={
    "backgroundColor": COLORS["bg_page"],
    "minHeight": "100vh",
    "padding": "48px 56px",
    "fontFamily": FONT_FAMILY,
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
        ], style=STATS_GRID_STYLE)

        if not programmes:
            programmes_view = html.Div(
                "Aucun fichier processed détecté.",
                style={
                    "backgroundColor": COLORS["bg_surface"],
                    "border": f"1px solid {COLORS['border']}",
                    "padding": SPACE["lg"],
                    "borderRadius": RADIUS["lg"],
                    "textAlign": "center",
                    "color": COLORS["text_secondary"],
                }
            )
        else:
            programmes_view = html.Div([
                programme_card(item)
                for item in programmes
            ], style={
                "display": "flex",
                "gap": SPACE["lg"],
                "flexWrap": "wrap",
            })

        return stats_cards, programmes_view