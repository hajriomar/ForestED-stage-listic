"""
auth_ui.py — page de login Dash et gestion de session.

Deux types de session (exclusifs), stockés dans la session Flask
(cookie signé par FLASK_SECRET_KEY, httponly — jamais exposé au JS) :
- utilisateur : session["token"] (JWT) + session["user"] {username, role}
- invité      : session["guest_key"] (clé dashboard) + session["guest"]
                {name, label} — viewer strict, jamais admin.
"""

import logging

from dash import Input, Output, State, dcc, html
from flask import session

import api_client
from design_tokens import COLORS, FONT_FAMILY, FONT_FAMILY_SERIF_TITLE, SHADOW

logger = logging.getLogger(__name__)


# =====================================================
# Session helpers
# =====================================================

def current_token():
    return session.get("token")


def current_guest_key():
    return session.get("guest_key")


def is_guest() -> bool:
    return bool(session.get("guest_key"))

def has_session() -> bool:
    return bool(current_token() or current_guest_key())


def current_user():
    """{username, role} ou None (les invités n'ont pas de user)."""
    return session.get("user")


def current_guest():
    """{name, label} ou None."""
    return session.get("guest")


def is_admin() -> bool:
    user = current_user()
    return bool(user) and user.get("role") == "admin"


def clear_session() -> None:
    for key in ("token", "user", "guest_key", "guest"):
        session.pop(key, None)


def guest_label_from_sources(sources) -> str:
    """Libellé du badge invité selon les sources autorisées."""
    sources = sources or []
    if "*" in sources:
        return "toutes les sources"
    if not sources:
        return "aucune source"
    if len(sources) == 1:
        return sources[0]
    if len(sources) == 2:
        return " + ".join(sorted(sources))
    return "sources multiples"


def open_guest_session(api_key: str) -> str:
    """Valide une clé dashboard et ouvre la session invitée.

    Returns:
        "ok" | "invalid" (clé inconnue/révoquée/expirée ou kind != dashboard)
        | "api_down"
    """
    try:
        info = api_client.get_key_info(api_key)
    except api_client.AuthExpired as exc:
        logger.info("Lien d'accès refusé : %s", exc)
        return "invalid"
    except api_client.ApiUnavailable:
        return "api_down"

    if info.get("kind") != "dashboard":
        logger.info(
            "Lien d'accès refusé : clé %r de kind=%r (dashboard requis)",
            info.get("name"), info.get("kind"),
        )
        return "invalid"

    clear_session()
    session["guest_key"] = api_key
    session["guest"] = {
        "name": info.get("name", "?"),
        "label": guest_label_from_sources(info.get("sources")),
    }
    logger.info(
        "Session invitée ouverte : clé %r (%s)",
        info.get("name"), session["guest"]["label"],
    )
    return "ok"


def validate_session() -> str:
    """Vérifie la session auprès de l'API à chaque navigation.

    Returns: "ok" | "guest" | "anonymous" | "expired" | "api_down"
    """
    # --- Session invitée (clé dashboard) ---
    guest_key = current_guest_key()
    if guest_key:
        try:
            info = api_client.get_key_info(guest_key)
        except api_client.AuthExpired:
            # clé révoquée ou expirée entre-temps
            clear_session()
            return "expired"
        except api_client.ApiUnavailable:
            return "api_down"

        if info.get("kind") != "dashboard":
            clear_session()
            return "expired"

        session["guest"] = {
            "name": info.get("name", "?"),
            "label": guest_label_from_sources(info.get("sources")),
        }
        return "guest"

    # --- Session utilisateur (JWT) ---
    token = current_token()
    if not token:
        return "anonymous"

    try:
        me = api_client.get_me(token)
        session["user"] = {"username": me["username"], "role": me["role"]}
        return "ok"
    except api_client.AuthExpired:
        clear_session()
        return "expired"
    except api_client.ApiUnavailable:
        return "api_down"


# =====================================================
# Layouts
# =====================================================

_INPUT_STYLE = {
    "width": "100%",
    "padding": "11px 14px",
    "marginBottom": "14px",
    "border": "1px solid #D5DBE1",
    "borderRadius": "8px",
    "fontSize": "14px",
    "fontFamily": FONT_FAMILY,
    "boxSizing": "border-box",
}


def login_layout(message: str = "", message_color: str = "#C0392B"):
    """Page de connexion."""
    return html.Div([
        dcc.Location(id="login-redirect", refresh=True),
        html.Div([
            html.Div("ForestED", style={
                "fontFamily": FONT_FAMILY_SERIF_TITLE,
                "fontSize": "30px", "fontWeight": "800",
                "color": COLORS["primary_dark"],
                "textAlign": "center", "marginBottom": "4px",
            }),
            html.Div("Curricula & référentiels de compétences", style={
                "fontFamily": FONT_FAMILY, "fontSize": "12.5px",
                "color": "#7A8794", "textAlign": "center",
                "marginBottom": "28px",
            }),

            html.Label("Nom d'utilisateur ou email", style={
                "fontFamily": FONT_FAMILY, "fontSize": "13px",
                "fontWeight": "600", "marginBottom": "6px",
                "display": "block",
            }),
            dcc.Input(
                id="login-username", type="text",
                placeholder="utilisateur", autoFocus=True,
                n_submit=0, style=_INPUT_STYLE,
            ),

            html.Label("Mot de passe", style={
                "fontFamily": FONT_FAMILY, "fontSize": "13px",
                "fontWeight": "600", "marginBottom": "6px",
                "display": "block",
            }),
            dcc.Input(
                id="login-password", type="password",
                placeholder="••••••••", n_submit=0, style=_INPUT_STYLE,
            ),

            html.Button("Se connecter", id="login-button", n_clicks=0, style={
                "width": "100%", "padding": "12px",
                "backgroundColor": COLORS["primary_dark"],
                "color": "#FFFFFF", "border": "none",
                "borderRadius": "8px", "fontSize": "14.5px",
                "fontWeight": "700", "cursor": "pointer",
                "fontFamily": FONT_FAMILY, "marginTop": "6px",
            }),

            html.Div(message, id="login-error", style={
                "color": message_color, "fontSize": "13px",
                "fontFamily": FONT_FAMILY, "marginTop": "14px",
                "textAlign": "center", "minHeight": "18px",
            }),
        ], style={
            "width": "360px", "padding": "38px 34px",
            "backgroundColor": "#FFFFFF", "borderRadius": "14px",
            "boxShadow": SHADOW.get("navbar", "0 4px 18px rgba(0,0,0,0.10)"),
        }),
    ], style={
        "display": "flex", "alignItems": "center",
        "justifyContent": "center", "minHeight": "88vh",
        "backgroundColor": COLORS["bg_page"],
    })


def error_layout(title: str, detail: str = ""):
    """Page d'erreur pleine largeur (API indisponible, accès refusé...)."""
    return html.Div([
        html.Div(title, style={
            "fontSize": "22px", "fontWeight": "700",
            "fontFamily": FONT_FAMILY, "color": "#C0392B",
            "marginBottom": "10px",
        }),
        html.Div(detail, style={
            "fontSize": "14px", "fontFamily": FONT_FAMILY,
            "color": "#5D6B79",
        }),
    ], style={"padding": "60px", "textAlign": "center"})


# =====================================================
# Callbacks
# =====================================================

def register_callbacks(app):

    @app.callback(
        Output("login-redirect", "href"),
        Output("login-error", "children"),
        Input("login-button", "n_clicks"),
        Input("login-password", "n_submit"),
        State("login-username", "value"),
        State("login-password", "value"),
        prevent_initial_call=True,
    )
    def do_login(n_clicks, n_submit, username, password):
        if not username or not password:
            return None, "Renseignez le nom d'utilisateur et le mot de passe."

        try:
            result = api_client.login(username.strip(), password)
        except api_client.ApiUnavailable:
            return None, "Le serveur de données est indisponible. Réessayez plus tard."

        if not result["ok"]:
            logger.info("Login refusé pour %r", username)
            return None, result["error"]

        token = result["token"]

        try:
            me = api_client.get_me(token)
        except api_client.ApiError:
            return None, "Connexion impossible (profil inaccessible)."

        clear_session()
        session["token"] = token
        session["user"] = {"username": me["username"], "role": me["role"]}
        logger.info("Login OK pour %r (role=%s)", me["username"], me["role"])

        return "/home", ""