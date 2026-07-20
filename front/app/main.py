import os

import dash
import flask
from dash import html, dcc, Input, Output

import auth_ui
from design_tokens import COLORS, FONT_FAMILY, FONT_FAMILY_SERIF_TITLE, SHADOW

from forested_home import (
    forested_home_layout,
    register_callbacks as register_home_callbacks
)

from forested_visualisations import (
    forested_visualisations_layout,
    get_programme_options,
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
from forested_admin import (
    forested_admin_layout,
    register_callbacks as register_admin_callbacks
)

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "ForestED"

# Session Flask : cookie signé httponly (token JWT ou clé d'accès invité).
# FLASK_SECRET_KEY doit être défini en production (docker-compose / .env).
server = app.server
server.secret_key = os.getenv(
    "FLASK_SECRET_KEY", "dev-flask-secret-change-me"
)

# Cookies de session (Patch A) : HttpOnly + SameSite toujours ;
# Secure UNIQUEMENT en production (HTTPS derrière le reverse proxy) —
# en dev http://127.0.0.1, un cookie Secure ne serait jamais envoyé.
server.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
if os.getenv("APP_ENV", "development") == "production":
    server.config.update(SESSION_COOKIE_SECURE=True)


# ══════════════════════════════════════════════════════════════════════════════
#  ACCÈS INVITÉ (dashboard partagé, patch 5.5)
#
#  Lien opaque /access/<clé> : Dash valide la clé auprès du backend
#  (kind="dashboard" requis), ouvre une session invitée côté Flask,
#  puis redirige vers / — la clé disparaît de l'URL.
# ══════════════════════════════════════════════════════════════════════════════

@server.route("/access/<access_key>")
def guest_access(access_key):
    status = auth_ui.open_guest_session(access_key)

    if status == "ok":
        return flask.redirect("/")

    # Message affiché sur la page de login au retour
    flask.session["login_message"] = (
        "Le serveur de données est indisponible. Réessayez plus tard."
        if status == "api_down"
        else "Lien d'accès invalide, expiré ou révoqué."
    )
    return flask.redirect("/")


# ══════════════════════════════════════════════════════════════════════════════
#  PAGES
#  "admin_only": True -> lien navbar masqué et page bloquée pour les
#  non-admins (le backend re-vérifie de toute façon chaque appel /admin/*).
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
    "admin": {
        "label": "Administration",
        "layout": forested_admin_layout,
        "register": register_admin_callbacks,
        "admin_only": True,
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


def build_user_zone():
    """Badge utilisateur/invité + lien de sortie (droite de la navbar)."""
    if auth_ui.is_guest():
        guest = auth_ui.current_guest() or {}
        label = guest.get("label", "?")
        return html.Div([
            html.Div([
                html.Div(f"Accès invité — {label}", style={
                    "fontFamily": FONT_FAMILY, "fontSize": "13px",
                    "fontWeight": "700", "color": COLORS["text_on_dark"],
                    "lineHeight": "1.2", "textAlign": "right",
                }),
                html.Div("lecture seule", style={
                    "fontFamily": FONT_FAMILY, "fontSize": "11px",
                    "color": COLORS["text_on_dark_muted"],
                    "lineHeight": "1.2", "textAlign": "right",
                }),
            ]),
            dcc.Link("Quitter", href="/logout", style={
                "fontFamily": FONT_FAMILY, "fontSize": "12.5px",
                "fontWeight": "600", "color": COLORS["text_on_dark"],
                "textDecoration": "none", "padding": "7px 12px",
                "borderRadius": "7px",
                "border": "1px solid rgba(255,255,255,0.35)",
                "whiteSpace": "nowrap",
            }),
        ], style={
            "display": "flex", "alignItems": "center", "gap": "14px",
            "marginLeft": "auto",
        })

    user = auth_ui.current_user() or {}
    username = user.get("username", "?")
    role = user.get("role", "")

    return html.Div([
        html.Div([
            html.Div(username, style={
                "fontFamily": FONT_FAMILY, "fontSize": "13px",
                "fontWeight": "700", "color": COLORS["text_on_dark"],
                "lineHeight": "1.2", "textAlign": "right",
            }),
            html.Div(role, style={
                "fontFamily": FONT_FAMILY, "fontSize": "11px",
                "color": COLORS["text_on_dark_muted"],
                "lineHeight": "1.2", "textAlign": "right",
            }),
        ]),
        dcc.Link("Déconnexion", href="/logout", style={
            "fontFamily": FONT_FAMILY, "fontSize": "12.5px",
            "fontWeight": "600", "color": COLORS["text_on_dark"],
            "textDecoration": "none", "padding": "7px 12px",
            "borderRadius": "7px", "border": "1px solid rgba(255,255,255,0.35)",
            "whiteSpace": "nowrap",
        }),
    ], style={
        "display": "flex", "alignItems": "center", "gap": "14px",
        "marginLeft": "auto",
    })


def build_navbar(active_key):
    is_admin = auth_ui.is_admin()

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
            # Navigation (Administration : admins uniquement — jamais
            # pour les invités ; le backend re-vérifie de toute façon)
            html.Div([
                nav_link(key, page, active_key)
                for key, page in PAGES.items()
                if not page.get("admin_only") or is_admin
            ], style={
                "display": "flex",
                "alignItems": "center",
                "gap": "8px",
                "marginLeft": "42px",
            }),
            # Utilisateur / invité + sortie
            build_user_zone(),
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


auth_ui.register_callbacks(app)
for page in PAGES.values():
    page["register"](app)


# ══════════════════════════════════════════════════════════════════════════════
#  DROPDOWNS FORMATION — remplis PAR SESSION (utilisateur ou invité)
#
#  Les layouts des pages sont construits à l'import du serveur, sans
#  utilisateur : leurs dropdowns démarrent vides. Ces callbacks les
#  remplissent à chaque navigation avec les seules formations que le
#  backend autorise pour la session courante (filtrage par source).
# ══════════════════════════════════════════════════════════════════════════════

_PROGRAMME_DROPDOWN_IDS = [
    "programme-selector",           # Cartographie APC
    "forested-programme-selector",  # Forêt pédagogique
    "sunburst-programme-selector",  # Exploration circulaire
    "pathway-programme-selector",   # Parcours
]


def _register_programme_options_refresh(dash_app, dropdown_id):
    @dash_app.callback(
        Output(dropdown_id, "options"),
        Input("url", "pathname"),
    )
    def _refresh_options(_pathname):
        # get_programme_options -> load_processed_files -> API filtrée
        # par source selon la session courante (JWT ou clé invitée).
        return get_programme_options()


for _dropdown_id in _PROGRAMME_DROPDOWN_IDS:
    _register_programme_options_refresh(app, _dropdown_id)


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTAGE
# ══════════════════════════════════════════════════════════════════════════════

def resolve_key(pathname):
    key = pathname.strip("/") if pathname else "home"
    return key if key in PAGES else "home"


@app.callback(
    Output("navbar-container", "children"),
    Input("url", "pathname")
)
def render_navbar(pathname):
    # Pas de navbar tant qu'aucune session (utilisateur ou invité)
    if not auth_ui.has_session():
        return None
    return build_navbar(resolve_key(pathname))


@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname")
)
def render_page(pathname):
    path = (pathname or "").strip("/")

    # Déconnexion explicite (utilisateur ou invité)
    if path == "logout":
        auth_ui.clear_session()
        return auth_ui.login_layout(
            "Vous êtes déconnecté.", message_color="#2E7D32"
        )

    # Vérification de session (JWT ou clé invitée, encore valide)
    status = auth_ui.validate_session()

    if status == "anonymous":
        # message éventuel déposé par /access/<clé> (lien refusé)
        message = flask.session.pop("login_message", "")
        return auth_ui.login_layout(message)

    if status == "expired":
        return auth_ui.login_layout(
            "Session expirée ou accès révoqué, veuillez vous reconnecter."
        )

    if status == "api_down":
        return auth_ui.error_layout(
            "Serveur de données indisponible",
            "Le backend ne répond pas. Vérifiez qu'il est démarré, "
            "puis rechargez la page.",
        )

    key = resolve_key(pathname)

    # Pages réservées aux admins (jamais accessibles aux invités)
    if PAGES[key].get("admin_only") and not auth_ui.is_admin():
        return auth_ui.error_layout(
            "Accès non autorisé",
            "Cette page est réservée aux administrateurs.",
        )

    return PAGES[key]["layout"]


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8050,
        debug=False,
        use_reloader=False,
        threaded=True
    )