import dash
from dash import html, dcc, Input, Output

from forested_home import (
    forested_home_layout,
    register_callbacks as register_home_callbacks
)

from forested_visualisations import (
    forested_visualisations_layout,
    register_callbacks as register_visualisations_callbacks
)


app = dash.Dash(__name__, suppress_callback_exceptions=True)

PAGES = {
    "home": {
        "label": "Accueil",
        "layout": forested_home_layout,
        "register": register_home_callbacks
    },

    "visualisations": {
        "label": "Visualisations",
        "layout": forested_visualisations_layout,
        "register": register_visualisations_callbacks
    }
}

app.layout = html.Div([
    dcc.Location(id="url", refresh=False),

    html.Div([
        dcc.Link( 
            page["label"],
            href=f"/{key}",
            style={"marginRight": "20px"}
        )
        for key, page in PAGES.items()
    ], style={"padding": "20px"}),

    html.Div(id="page-content")
])


for page in PAGES.values():
    page["register"](app)


@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname")
)
def render_page(pathname):
    key = pathname.strip("/") if pathname else "home"

    if key not in PAGES:
        key = "home"

    return PAGES[key]["layout"]


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=True)