import dash
from dash import html, dcc, Input, Output

from design_tokens import COLORS, FONT_FAMILY, FONT_FAMILY_SERIF_TITLE, SHADOW

from forested_home import (
    forested_home_layout,
    register_callbacks as register_home_callbacks
)

from forested_visualisations import (
    forested_visualisations_layout,
    register_callbacks as register_visualisations_callbacks
)
from forested_forest import (
    forested_forest_layout,
    register_callbacks as register_forest_callbacks
)
from forested_sunburst import (
    forested_sunburst_layout,
    register_callbacks as register_sunburst_callbacks
)
from forested_pathway import (
    forested_pathway_layout,
    register_callbacks as register_pathway_callbacks
)

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "ForestED"

# ══════════════════════════════════════════════════════════════════════════════
#  PAGES
# ══════════════════════════════════════════════════════════════════════════════

PAGES = {
    "home": {
        "label": "Vue d'ensemble",
        "layout": forested_home_layout,
        "register": register_home_callbacks
    },
    "visualisations": {
        "label": "Cartographie APC",
        "layout": forested_visualisations_layout,
        "register": register_visualisations_callbacks
    },
    "forested": {
        "label": "Forêt pédagogique",
        "layout": forested_forest_layout,
        "register": register_forest_callbacks
    },
    "sunburst": {
        "label": "Exploration circulaire",
        "layout": forested_sunburst_layout,
        "register": register_sunburst_callbacks
    },
    "pathway": {
        "label": "Parcours",
        "layout": forested_pathway_layout,
        "register": register_pathway_callbacks
    },
}

NAVBAR_HEIGHT = "80px"


# ══════════════════════════════════════════════════════════════════════════════
#  NAVBAR
# ══════════════════════════════════════════════════════════════════════════════

def nav_link(key, page, active_key):
    is_active = key == active_key
    return dcc.Link(
        page["label"],
        href=f"/{key}",
        style={
            "fontFamily": FONT_FAMILY,
            "fontSize": "13.5px",
            "fontWeight": "700" if is_active else "500",
            "color": COLORS["text_on_dark"] if is_active else COLORS["text_on_dark_muted"],
            "textDecoration": "none",
            "padding": "8px 14px",
            "borderRadius": "7px",
            "backgroundColor": "rgba(255,255,255,0.12)" if is_active else "transparent",
            "transition": "background-color 0.15s ease, color 0.15s ease",
            "whiteSpace": "nowrap",
            "letterSpacing": "0.1px",
        },
        className="forested-nav-link",
    )


def build_navbar(active_key):
    return html.Div([
        html.Div([
            # Bloc identité vraiment à gauche
            html.Div([
                html.Div("ForestED", style={
                    "fontFamily": FONT_FAMILY_SERIF_TITLE,
                    "fontSize": "24px",
                    "fontWeight": "800",
                    "color": COLORS["text_on_dark"],
                    "lineHeight": "1.05",
                    "letterSpacing": "0.2px",
                    "margin": "0",
                }),
                html.Div(
                    "Curricula & référentiels de compétences",
                    style={
                        "fontFamily": FONT_FAMILY,
                        "fontSize": "11.5px",
                        "fontWeight": "500",
                        "color": COLORS["text_on_dark_muted"],
                        "lineHeight": "1.2",
                        "marginTop": "4px",
                        "whiteSpace": "nowrap",
                    }
                ),
            ], style={
                "display": "flex",
                "flexDirection": "column",
                "justifyContent": "center",
                "alignItems": "flex-start",
                "minWidth": "260px",
            }),
            # Navigation
            html.Div([
                nav_link(key, page, active_key)
                for key, page in PAGES.items()
            ], style={
                "display": "flex",
                "alignItems": "center",
                "gap": "8px",
                "marginLeft": "42px",
            }),
        ], style={
            "width": "100%",
            "height": NAVBAR_HEIGHT,
            "padding": "0 28px",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "flex-start",
            "boxSizing": "border-box",
        }),
    ], style={
        "backgroundColor": COLORS["primary_dark"],
        "boxShadow": SHADOW["navbar"],
        "position": "sticky",
        "top": "0",
        "zIndex": "100",
    })


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT GLOBAL
# ══════════════════════════════════════════════════════════════════════════════

app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    html.Div(id="navbar-container"),
    html.Div(id="page-content"),
], style={
    "fontFamily": FONT_FAMILY,
    "backgroundColor": COLORS["bg_page"],
    "minHeight": "100vh",
})


for page in PAGES.values():
    page["register"](app)


def resolve_key(pathname):
    key = pathname.strip("/") if pathname else "home"
    return key if key in PAGES else "home"


@app.callback(
    Output("navbar-container", "children"),
    Input("url", "pathname")
)
def render_navbar(pathname):
    return build_navbar(resolve_key(pathname))


@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname")
)
def render_page(pathname):
    return PAGES[resolve_key(pathname)]["layout"]


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8050,
        debug=False,
        use_reloader=False,
        threaded=True
    )