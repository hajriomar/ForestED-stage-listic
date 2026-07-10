"""
forested_admin.py — page Administration du dashboard.

Visible et utilisable uniquement par les admins (le lien navbar est masqué
pour les autres, la page affiche « Accès non autorisé », et de toute façon
le backend re-vérifie le rôle sur chaque appel /admin/*).

Layout : sidebar de navigation à gauche + zone de contenu pleine largeur.
Les 4 sections (Utilisateurs, Permissions, Clés API, Fichiers sources)
restent toutes montées dans le DOM — seule leur visibilité change
(display none/block), si bien que TOUS les callbacks existants
fonctionnent sans modification.
"""

import base64
import logging
import os
from datetime import datetime, timezone

from dash import ALL, Input, Output, State, ctx, dcc, html, no_update

import api_client
import auth_ui
from design_tokens import COLORS, FONT_FAMILY

logger = logging.getLogger(__name__)

DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL", "http://127.0.0.1:8050")

SCOPE_OPTIONS = [
    {"label": " lecture compétences (read:competence)", "value": "read:competence"},
    {"label": " lecture curricula (read:curriculum)", "value": "read:curriculum"},
    {"label": " lecture analytics (read:analytics)", "value": "read:analytics"},
    {"label": " tous les droits de lecture (*)", "value": "*"},
]
DEFAULT_SCOPES = ["read:competence", "read:curriculum", "read:analytics"]

KIND_OPTIONS = [
    {"label": " API données (script / application externe)", "value": "data"},
    {"label": " Dashboard partagé (lien d'accès invité)", "value": "dashboard"},
]
KIND_LABELS = {"data": "données", "dashboard": "dashboard"}

DOMAIN_OPTIONS = [
    {"label": "Compétences", "value": "competence"},
    {"label": "Curriculum", "value": "curriculum"},
]
UPLOAD_EXTENSIONS = ".json, .xlsx, .xls, .csv"

# ── Styles ────────────────────────────────────────────────────────────────

CARD = {
    "backgroundColor": "#FFFFFF", "borderRadius": "12px",
    "padding": "22px 26px", "marginBottom": "22px",
    "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
}
H3 = {"fontFamily": FONT_FAMILY, "fontSize": "17px", "fontWeight": "700",
      "color": "#0F172A", "margin": "0 0 14px"}
H4 = {"fontFamily": FONT_FAMILY, "fontSize": "13.5px", "fontWeight": "700",
      "color": "#334155", "margin": "18px 0 8px"}
LABEL = {"fontFamily": FONT_FAMILY, "fontSize": "12.5px", "fontWeight": "600",
         "color": "#475569", "display": "block", "marginBottom": "4px"}
INPUT = {"width": "100%", "padding": "8px 10px", "border": "1px solid #D5DBE1",
         "borderRadius": "7px", "fontSize": "13px", "fontFamily": FONT_FAMILY,
         "boxSizing": "border-box"}
BTN = {"padding": "9px 16px", "backgroundColor": COLORS["primary_dark"],
       "color": "#FFF", "border": "none", "borderRadius": "7px",
       "fontSize": "13px", "fontWeight": "700", "cursor": "pointer",
       "fontFamily": FONT_FAMILY}
BTN_DANGER = {**BTN, "backgroundColor": "#B4232A"}
BTN_ROW_DANGER = {**BTN_DANGER, "padding": "5px 12px", "fontSize": "12px"}
BTN_ROW_DISABLED = {**BTN_ROW_DANGER, "backgroundColor": "#CBD5E1",
                    "color": "#64748B", "cursor": "default"}
BTN_ROW_SECONDARY = {"padding": "4px 10px", "fontSize": "11.5px",
                     "fontFamily": FONT_FAMILY, "fontWeight": "600",
                     "backgroundColor": "transparent", "color": "#B4232A",
                     "border": "1px solid #E2A0A4", "borderRadius": "6px",
                     "cursor": "pointer"}
TH = {"textAlign": "left", "padding": "7px 10px", "borderBottom": "2px solid #E2E8F0",
      "fontSize": "12px", "color": "#64748B", "fontFamily": FONT_FAMILY}
TD = {"padding": "7px 10px", "borderBottom": "1px solid #F1F5F9",
      "fontSize": "13px", "fontFamily": FONT_FAMILY, "color": "#0F172A"}
MSG_OK = {"color": "#2E7D32", "fontSize": "13px", "fontFamily": FONT_FAMILY,
          "marginTop": "8px", "minHeight": "18px"}
MSG_ERR = {**MSG_OK, "color": "#C0392B"}

UPLOAD_ZONE = {
    "width": "100%", "minHeight": "64px", "lineHeight": "1.5",
    "borderWidth": "2px", "borderStyle": "dashed",
    "borderColor": "#94A3B8", "borderRadius": "10px",
    "textAlign": "center", "padding": "18px 12px",
    "fontFamily": FONT_FAMILY, "fontSize": "13px", "color": "#475569",
    "cursor": "pointer", "backgroundColor": "#F8FAFC",
    "boxSizing": "border-box",
}

_BADGE_BASE = {"display": "inline-block", "padding": "3px 10px",
               "borderRadius": "999px", "fontSize": "12px",
               "fontWeight": "700", "fontFamily": FONT_FAMILY,
               "whiteSpace": "nowrap"}
BADGE_STYLES = {
    "actif": {**_BADGE_BASE, "backgroundColor": "#E6F4EA", "color": "#1E7B34"},
    "desactive": {**_BADGE_BASE, "backgroundColor": "#FDE8E8", "color": "#B4232A"},
    "expire": {**_BADGE_BASE, "backgroundColor": "#FFF4E5", "color": "#B45309"},
}
BADGE_LABELS = {"actif": "Actif", "desactive": "Désactivé", "expire": "Expiré"}

_FIELD = lambda width: {"width": width, "minWidth": "140px"}
_ROW = {"display": "flex", "gap": "14px", "flexWrap": "wrap",
        "alignItems": "flex-end"}

# ── Sidebar / sections ────────────────────────────────────────────────────

SECTIONS = ["users", "perms", "keys", "upload"]
SECTION_LABELS = {
    "users": "Utilisateurs",
    "perms": "Permissions par source",
    "keys": "Clés API",
    "upload": "Fichiers sources",
}

NAV_BTN = {
    "display": "block", "width": "100%", "textAlign": "left",
    "padding": "10px 14px", "marginBottom": "6px",
    "backgroundColor": "transparent", "color": "#334155",
    "border": "none", "borderRadius": "8px",
    "fontSize": "13.5px", "fontWeight": "600",
    "fontFamily": FONT_FAMILY, "cursor": "pointer",
}
NAV_BTN_ACTIVE = {
    **NAV_BTN,
    "backgroundColor": COLORS["primary_dark"], "color": "#FFFFFF",
    "fontWeight": "700",
}
SECTION_VISIBLE = {}
SECTION_HIDDEN = {"display": "none"}

_TWO_COLS = {"display": "grid",
             "gridTemplateColumns": "minmax(0, 1.6fr) minmax(0, 1fr)",
             "gap": "18px", "alignItems": "start"}
_SUBCARD = {"border": "1px solid #E2E8F0", "borderRadius": "10px",
            "padding": "14px 16px", "marginBottom": "14px"}


# ── Helpers d'état des clés (affichage uniquement) ───────────────────────

def _parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def key_state(key: dict) -> str:
    """Retourne "actif" | "desactive" | "expire" pour l'affichage."""
    if key.get("revoked_at"):
        return "desactive"
    expires = _parse_dt(key.get("expires_at"))
    if expires and expires <= datetime.now(timezone.utc):
        return "expire"
    return "actif"


def _state_badge(state: str):
    return html.Span(BADGE_LABELS[state], style=BADGE_STYLES[state])


def _expiration_cell(key: dict) -> str:
    expires = _parse_dt(key.get("expires_at"))
    if not expires:
        return "Jamais"
    date_str = expires.strftime("%d/%m/%Y")
    if expires <= datetime.now(timezone.utc):
        return f"Expiré le {date_str}"
    return f"Expire le {date_str}"


def _usage_cell(kind: str) -> str:
    if kind == "dashboard":
        return ("Dashboard partagé — lien affiché une seule fois "
                "à la création")
    return "API données — utiliser le header X-API-Key"


def _action_cell(key: dict, state: str):
    if state == "actif":
        return html.Button(
            "Désactiver",
            id={"type": "admin-key-disable", "index": key["id"]},
            n_clicks=0, style=BTN_ROW_DANGER,
        )
    if state == "desactive":
        return html.Button("Désactivé", disabled=True,
                           style=BTN_ROW_DISABLED)
    # Expiré : action secondaire (nettoyage), l'état parle de lui-même
    return html.Button(
        "Désactiver",
        id={"type": "admin-key-disable", "index": key["id"]},
        n_clicks=0, style=BTN_ROW_SECONDARY,
        title="Clé expirée — désactiver définitivement",
    )


def _available_source_options(token, include_wildcard=True):
    """Options du dropdown Source : sources réellement présentes dans les
    données (dérivées de l'API, jamais hardcodées), '*' en option."""
    sources = set()
    try:
        for response in (api_client.get_competences(token=token),
                         api_client.get_curricula(token=token)):
            for item in response.get("data", []):
                if item.get("source"):
                    sources.add(item["source"])
    except api_client.ApiError:
        pass

    options = [{"label": s, "value": s} for s in sorted(sources)]
    if include_wildcard:
        options = ([{"label": "* — toutes les sources (actuelles et futures)",
                     "value": "*"}] + options)
    return options


def _table(headers, rows):
    if not rows:
        return html.Div("Aucun élément.", style={
            "fontSize": "13px", "fontFamily": FONT_FAMILY,
            "color": "#94A3B8", "padding": "6px 0"})
    return html.Table(
        [html.Thead(html.Tr([html.Th(h, style=TH) for h in headers])),
         html.Tbody([
             html.Tr([html.Td(cell, style=TD) for cell in row])
             for row in rows
         ])],
        style={"width": "100%", "borderCollapse": "collapse"},
    )


# ══════════════════════════════════════════════════════════════════════════
#  SECTIONS (contenu identique à la version précédente, réorganisé)
# ══════════════════════════════════════════════════════════════════════════

_section_users = html.Div([
    html.H3("Utilisateurs", style=H3),
    html.Div([
        # Colonne gauche : la liste
        html.Div([
            html.Div(id="admin-users-table"),
        ], style=_SUBCARD),

        # Colonne droite : les actions
        html.Div([
            html.Div([
                html.H4("Créer un utilisateur",
                        style={**H4, "marginTop": "0"}),
                html.Div([html.Label("Nom d'utilisateur", style=LABEL),
                          dcc.Input(id="admin-new-username", type="text",
                                    style=INPUT)],
                         style={"marginBottom": "10px"}),
                html.Div([html.Label("Email", style=LABEL),
                          dcc.Input(id="admin-new-email", type="email",
                                    style=INPUT)],
                         style={"marginBottom": "10px"}),
                html.Div([html.Label("Mot de passe (min 10)", style=LABEL),
                          dcc.Input(id="admin-new-password", type="password",
                                    style=INPUT)],
                         style={"marginBottom": "10px"}),
                html.Div([html.Label("Rôle", style=LABEL),
                          dcc.Dropdown(id="admin-new-role",
                                       options=[{"label": "viewer",
                                                 "value": "viewer"},
                                                {"label": "admin",
                                                 "value": "admin"}],
                                       value="viewer", clearable=False,
                                       style={"fontSize": "13px"})],
                         style={"marginBottom": "12px"}),
                html.Button("Créer", id="admin-create-user-btn", n_clicks=0,
                            style=BTN),
                html.Div(id="admin-create-user-msg", style=MSG_OK),
            ], style=_SUBCARD),

            html.Div([
                html.H4("Modifier / supprimer",
                        style={**H4, "marginTop": "0"}),
                html.Div([html.Label("Utilisateur", style=LABEL),
                          dcc.Dropdown(id="admin-user-selector",
                                       placeholder="Choisir...",
                                       style={"fontSize": "13px"})],
                         style={"marginBottom": "10px"}),
                html.Div([html.Label("Nouveau rôle", style=LABEL),
                          dcc.Dropdown(id="admin-edit-role",
                                       options=[{"label": "(inchangé)",
                                                 "value": ""},
                                                {"label": "viewer",
                                                 "value": "viewer"},
                                                {"label": "admin",
                                                 "value": "admin"}],
                                       value="", clearable=False,
                                       style={"fontSize": "13px"})],
                         style={"marginBottom": "10px"}),
                html.Div([html.Label("Statut", style=LABEL),
                          dcc.Dropdown(id="admin-edit-active",
                                       options=[{"label": "(inchangé)",
                                                 "value": ""},
                                                {"label": "actif",
                                                 "value": "true"},
                                                {"label": "désactivé",
                                                 "value": "false"}],
                                       value="", clearable=False,
                                       style={"fontSize": "13px"})],
                         style={"marginBottom": "10px"}),
                html.Div([html.Label("Nouveau mot de passe (optionnel)",
                                     style=LABEL),
                          dcc.Input(id="admin-edit-password", type="password",
                                    style=INPUT)],
                         style={"marginBottom": "12px"}),
                html.Div([
                    html.Button("Appliquer", id="admin-apply-user-btn",
                                n_clicks=0, style=BTN),
                    html.Button("Supprimer", id="admin-delete-user-btn",
                                n_clicks=0,
                                style={**BTN_DANGER, "marginLeft": "10px"}),
                ]),
                html.Div(id="admin-edit-user-msg", style=MSG_OK),
            ], style=_SUBCARD),
        ]),
    ], style=_TWO_COLS),
], style=CARD)


_section_perms = html.Div([
    html.H3("Permissions par source", style=H3),
    html.P("L'accès à une source donne accès à tous ses programmes, "
           "actuels et futurs. \"*\" = toutes les sources.",
           style={"fontFamily": FONT_FAMILY, "fontSize": "12.5px",
                  "color": "#64748B", "margin": "0 0 12px"}),
    html.Div([
        # Colonne gauche : utilisateur + ses permissions
        html.Div([
            html.Div([html.Label("Utilisateur", style=LABEL),
                      dcc.Dropdown(id="admin-perm-user",
                                   placeholder="Choisir un utilisateur...",
                                   style={"fontSize": "13px"})],
                     style={"marginBottom": "12px"}),
            html.Div(id="admin-perms-table"),
        ], style=_SUBCARD),

        # Colonne droite : ajouter / retirer
        html.Div([
            html.Div([
                html.H4("Ajouter / mettre à jour",
                        style={**H4, "marginTop": "0"}),
                html.Div([html.Label("Source(s)", style=LABEL),
                          dcc.Dropdown(id="admin-perm-source", multi=True,
                                       placeholder="Choisir...",
                                       style={"fontSize": "13px"})],
                         style={"marginBottom": "10px"}),
                html.Div([html.Label("Scopes", style=LABEL),
                          dcc.Checklist(id="admin-perm-scopes",
                                        options=SCOPE_OPTIONS,
                                        value=DEFAULT_SCOPES,
                                        style={"fontSize": "12.5px",
                                               "fontFamily": FONT_FAMILY})],
                         style={"marginBottom": "12px"}),
                html.Button("Enregistrer", id="admin-add-perm-btn",
                            n_clicks=0, style=BTN),
            ], style=_SUBCARD),

            html.Div([
                html.H4("Retirer une permission",
                        style={**H4, "marginTop": "0"}),
                html.Div([dcc.Dropdown(id="admin-perm-delete",
                                       placeholder="Choisir la permission...",
                                       style={"fontSize": "13px"})],
                         style={"marginBottom": "12px"}),
                html.Button("Retirer", id="admin-del-perm-btn", n_clicks=0,
                            style=BTN_DANGER),
            ], style=_SUBCARD),
            html.Div(id="admin-perm-msg", style=MSG_OK),
        ]),
    ], style=_TWO_COLS),
], style=CARD)


_section_keys = html.Div([
    html.H3("Clés API", style=H3),
    html.P("Le secret (clé ou lien) est affiché UNE SEULE FOIS à la "
           "création, puis n'est plus jamais réaffiché — seule son "
           "empreinte est conservée. En cas de perte : désactiver la "
           "clé et en créer une nouvelle.",
           style={"fontFamily": FONT_FAMILY, "fontSize": "12.5px",
                  "color": "#64748B", "margin": "0 0 12px"}),
    html.Div(id="admin-keys-table"),
    html.Div(id="admin-key-msg", style=MSG_OK),

    html.H4("Créer une clé", style=H4),
    html.Div([
        html.Div([html.Label("Type", style=LABEL),
                  dcc.RadioItems(id="admin-key-kind",
                                 options=KIND_OPTIONS, value="data",
                                 style={"fontSize": "12.5px",
                                        "fontFamily": FONT_FAMILY})],
                 style=_FIELD("30%")),
        html.Div([html.Label("Nom (ex. intranet-polytech)", style=LABEL),
                  dcc.Input(id="admin-key-name", type="text",
                            style=INPUT)], style=_FIELD("18%")),
        html.Div([html.Label("Expire dans (jours, vide = jamais)",
                             style=LABEL),
                  dcc.Input(id="admin-key-days", type="number", min=1,
                            style=INPUT)], style=_FIELD("14%")),
    ], style=_ROW),
    html.Div([
        html.Div([html.Label("Source(s) autorisée(s)", style=LABEL),
                  dcc.Dropdown(id="admin-key-source", multi=True,
                               placeholder="Choisir...",
                               style={"fontSize": "13px"})],
                 style=_FIELD("28%")),
        html.Div([html.Label("Scopes", style=LABEL),
                  dcc.Checklist(id="admin-key-scopes",
                                options=SCOPE_OPTIONS,
                                value=DEFAULT_SCOPES,
                                style={"fontSize": "12.5px",
                                       "fontFamily": FONT_FAMILY})],
                 style=_FIELD("34%")),
        html.Button("Générer", id="admin-create-key-btn", n_clicks=0,
                    style=BTN),
    ], style={**_ROW, "marginTop": "10px"}),
    html.Div(id="admin-key-created"),
], style=CARD)


_section_upload = html.Div([
    html.H3("Ajouter un fichier source", style=H3),
    html.P("Le fichier est enregistré dans "
           "raw/{domaine}/{source}/{FORMATION}_{nom} puis traité "
           "immédiatement — lui seul : les autres fichiers et leurs "
           "résultats ne sont pas touchés. Formats : " +
           UPLOAD_EXTENSIONS + " (max 20 Mo).",
           style={"fontFamily": FONT_FAMILY, "fontSize": "12.5px",
                  "color": "#64748B", "margin": "0 0 12px"}),

    html.Div([
        html.Div([
            html.Div([html.Label("Domaine", style=LABEL),
                      dcc.Dropdown(id="admin-upload-domain",
                                   options=DOMAIN_OPTIONS,
                                   value="competence", clearable=False,
                                   style={"fontSize": "13px"})],
                     style={"marginBottom": "10px"}),
            html.Div([html.Label("Source", style=LABEL),
                      dcc.Dropdown(id="admin-upload-source",
                                   placeholder="Choisir...",
                                   style={"fontSize": "13px"})],
                     style={"marginBottom": "10px"}),
            html.Div([html.Label("Formation (ex. SNI, QLIO)", style=LABEL),
                      dcc.Input(id="admin-upload-formation", type="text",
                                placeholder="lettres/chiffres/_/-",
                                style=INPUT)],
                     style={"marginBottom": "10px"}),
        ]),
        html.Div([
            dcc.Upload(
                id="admin-upload-file",
                children=html.Div([
                    "Glissez un fichier ici, ou ",
                    html.Span("cliquez pour choisir", style={
                        "fontWeight": "700",
                        "textDecoration": "underline"}),
                ]),
                style=UPLOAD_ZONE,
                multiple=False,
            ),
            html.Div(id="admin-upload-filename", style={
                "fontFamily": FONT_FAMILY, "fontSize": "12.5px",
                "color": "#334155", "marginTop": "6px",
                "minHeight": "16px"}),
            html.Button("Téléverser et traiter", id="admin-upload-btn",
                        n_clicks=0, style={**BTN, "marginTop": "12px"}),
            html.Div(id="admin-upload-msg", style=MSG_OK),
        ]),
    ], style={**_TWO_COLS,
              "gridTemplateColumns": "minmax(0, 1fr) minmax(0, 1.4fr)",
              "maxWidth": "860px"}),
], style=CARD)


# ══════════════════════════════════════════════════════════════════════════
#  LAYOUT (sidebar gauche + contenu ; sections masquées par CSS,
#  tous les composants restent montés -> callbacks inchangés)
# ══════════════════════════════════════════════════════════════════════════

forested_admin_layout = html.Div([
    dcc.Store(id="admin-refresh", data=0),

    html.H1("Administration", style={
        "fontFamily": FONT_FAMILY, "fontSize": "26px", "fontWeight": "800",
        "color": "#0F172A", "margin": "0 0 4px"}),
    html.P("Utilisateurs, permissions par source, clés API et fichiers "
           "sources. Chaque action est re-vérifiée par le backend.",
           style={"fontFamily": FONT_FAMILY, "fontSize": "13px",
                  "color": "#64748B", "margin": "0 0 18px"}),

    html.Div([
        # ── Sidebar de navigation ──
        html.Div([
            html.Button(SECTION_LABELS[section],
                        id=f"admin-nav-{section}", n_clicks=0,
                        style=NAV_BTN_ACTIVE if section == "users"
                        else NAV_BTN)
            for section in SECTIONS
        ], style={
            "width": "210px", "flexShrink": "0",
            "backgroundColor": "#FFFFFF", "borderRadius": "12px",
            "padding": "12px",
            "boxShadow": "0 2px 10px rgba(15,23,42,0.06)",
            "alignSelf": "flex-start",
            "position": "sticky", "top": "96px",
        }),

        # ── Contenu (pleine largeur restante) ──
        html.Div([
            html.Div(_section_users, id="admin-section-users",
                     style=SECTION_VISIBLE),
            html.Div(_section_perms, id="admin-section-perms",
                     style=SECTION_HIDDEN),
            html.Div(_section_keys, id="admin-section-keys",
                     style=SECTION_HIDDEN),
            html.Div(_section_upload, id="admin-section-upload",
                     style=SECTION_HIDDEN),
        ], style={"flex": "1", "minWidth": "0"}),
    ], style={"display": "flex", "gap": "20px",
              "alignItems": "flex-start"}),

], style={"padding": "26px 34px"})


# ══════════════════════════════════════════════════════════════════════════
#  CALLBACKS
# ══════════════════════════════════════════════════════════════════════════

def _err(exc) -> tuple:
    """(message, style) rouge pour une exception API."""
    return str(exc), MSG_ERR


def register_callbacks(app):

    # ── Navigation sidebar : affiche une section, masque les autres ──────
    @app.callback(
        [Output(f"admin-section-{section}", "style")
         for section in SECTIONS]
        + [Output(f"admin-nav-{section}", "style")
           for section in SECTIONS],
        [Input(f"admin-nav-{section}", "n_clicks")
         for section in SECTIONS],
    )
    def switch_section(*_clicks):
        trigger = ctx.triggered_id or "admin-nav-users"
        active = str(trigger).replace("admin-nav-", "")
        if active not in SECTIONS:
            active = "users"

        section_styles = [
            SECTION_VISIBLE if section == active else SECTION_HIDDEN
            for section in SECTIONS
        ]
        nav_styles = [
            NAV_BTN_ACTIVE if section == active else NAV_BTN
            for section in SECTIONS
        ]
        return section_styles + nav_styles

    # ── Rafraîchissement global (tables + dropdowns) ─────────────────────
    @app.callback(
        Output("admin-users-table", "children"),
        Output("admin-user-selector", "options"),
        Output("admin-perm-user", "options"),
        Output("admin-keys-table", "children"),
        Output("admin-perm-source", "options"),
        Output("admin-key-source", "options"),
        Output("admin-upload-source", "options"),
        Input("url", "pathname"),
        Input("admin-refresh", "data"),
    )
    def refresh_all(_pathname, _tick):
        token = auth_ui.current_token()
        if not token or not auth_ui.is_admin():
            return None, [], [], None, [], [], []

        try:
            users = api_client.admin_list_users(token)
            keys = api_client.admin_list_api_keys(token)
        except api_client.ApiError as exc:
            err = html.Div(str(exc), style=MSG_ERR)
            return err, [], [], err, [], [], []

        source_options = _available_source_options(token)
        # Upload : sources concrètes uniquement (pas de "*")
        upload_source_options = _available_source_options(
            token, include_wildcard=False)

        users_table = _table(
            ["id", "utilisateur", "email", "rôle", "statut", "créé le"],
            [[u["id"], u["username"], u["email"], u["role"],
              "actif" if u["is_active"] else "désactivé",
              str(u["created_at"])[:10]] for u in users],
        )
        user_options = [
            {"label": f'{u["username"]} ({u["role"]}'
                      f'{", désactivé" if not u["is_active"] else ""})',
             "value": u["id"]}
            for u in users
        ]

        keys_rows = []
        for k in keys:
            state = key_state(k)
            keys_rows.append([
                k["id"],
                k["name"],
                KIND_LABELS.get(k.get("kind", "data"), k.get("kind")),
                k["key_prefix"] + "…",
                _usage_cell(k.get("kind", "data")),
                _expiration_cell(k),
                _state_badge(state),
                str(k["last_used_at"])[:16] if k["last_used_at"] else "—",
                _action_cell(k, state),
            ])

        keys_table = _table(
            ["id", "nom", "type", "préfixe", "usage", "expiration",
             "état", "dernier usage", "action"],
            keys_rows,
        )

        return (users_table, user_options, user_options, keys_table,
                source_options, source_options, upload_source_options)

    # ── Utilisateurs : créer ─────────────────────────────────────────────
    @app.callback(
        Output("admin-create-user-msg", "children"),
        Output("admin-create-user-msg", "style"),
        Output("admin-refresh", "data", allow_duplicate=True),
        Input("admin-create-user-btn", "n_clicks"),
        State("admin-new-username", "value"),
        State("admin-new-email", "value"),
        State("admin-new-password", "value"),
        State("admin-new-role", "value"),
        State("admin-refresh", "data"),
        prevent_initial_call=True,
    )
    def create_user(_n, username, email, password, role, tick):
        if not username or not email or not password:
            return "Tous les champs sont requis.", MSG_ERR, tick
        try:
            user = api_client.admin_create_user(
                auth_ui.current_token(), username.strip(),
                email.strip(), password, role,
            )
            return (f'Utilisateur "{user["username"]}" créé (id {user["id"]}). '
                    f'Pensez à lui donner des permissions.',
                    MSG_OK, (tick or 0) + 1)
        except api_client.ApiError as exc:
            msg, style = _err(exc)
            return msg, style, tick

    # ── Utilisateurs : modifier ──────────────────────────────────────────
    @app.callback(
        Output("admin-edit-user-msg", "children"),
        Output("admin-edit-user-msg", "style"),
        Output("admin-refresh", "data", allow_duplicate=True),
        Input("admin-apply-user-btn", "n_clicks"),
        State("admin-user-selector", "value"),
        State("admin-edit-role", "value"),
        State("admin-edit-active", "value"),
        State("admin-edit-password", "value"),
        State("admin-refresh", "data"),
        prevent_initial_call=True,
    )
    def update_user(_n, user_id, role, active, password, tick):
        if not user_id:
            return "Choisissez un utilisateur.", MSG_ERR, tick

        fields = {}
        if role:
            fields["role"] = role
        if active:
            fields["is_active"] = (active == "true")
        if password:
            fields["password"] = password

        if not fields:
            return "Aucune modification demandée.", MSG_ERR, tick

        try:
            user = api_client.admin_update_user(
                auth_ui.current_token(), int(user_id), fields,
            )
            return (f'Utilisateur "{user["username"]}" mis à jour '
                    f'({", ".join(sorted(fields))}).',
                    MSG_OK, (tick or 0) + 1)
        except api_client.ApiError as exc:
            msg, style = _err(exc)
            return msg, style, tick

    # ── Utilisateurs : supprimer ─────────────────────────────────────────
    @app.callback(
        Output("admin-edit-user-msg", "children", allow_duplicate=True),
        Output("admin-edit-user-msg", "style", allow_duplicate=True),
        Output("admin-refresh", "data", allow_duplicate=True),
        Input("admin-delete-user-btn", "n_clicks"),
        State("admin-user-selector", "value"),
        State("admin-refresh", "data"),
        prevent_initial_call=True,
    )
    def delete_user(_n, user_id, tick):
        if not user_id:
            return "Choisissez un utilisateur.", MSG_ERR, tick
        try:
            result = api_client.admin_delete_user(
                auth_ui.current_token(), int(user_id),
            )
            return (f'Utilisateur {result["id"]} supprimé '
                    f'({result.get("permissions_deleted", 0)} permission(s) '
                    f'retirée(s)).', MSG_OK, (tick or 0) + 1)
        except api_client.ApiError as exc:
            msg, style = _err(exc)
            return msg, style, tick

    # ── Permissions : liste par utilisateur ──────────────────────────────
    @app.callback(
        Output("admin-perms-table", "children"),
        Output("admin-perm-delete", "options"),
        Input("admin-perm-user", "value"),
        Input("admin-refresh", "data"),
    )
    def load_permissions(user_id, _tick):
        if not user_id or not auth_ui.is_admin():
            return html.Div("Choisissez un utilisateur pour voir ses "
                            "permissions.", style={
                                "fontSize": "13px", "color": "#94A3B8",
                                "fontFamily": FONT_FAMILY}), []
        try:
            perms = api_client.admin_list_permissions(
                auth_ui.current_token(), int(user_id),
            )
        except api_client.ApiError as exc:
            return html.Div(str(exc), style=MSG_ERR), []

        table = _table(
            ["id", "source", "scopes"],
            [[p["id"], p["source_name"], ", ".join(p["scopes"])]
             for p in perms],
        )
        options = [
            {"label": f'{p["source_name"]} — {", ".join(p["scopes"])}',
             "value": p["id"]}
            for p in perms
        ]
        return table, options

    # ── Permissions : ajouter / mettre à jour ────────────────────────────
    @app.callback(
        Output("admin-perm-msg", "children"),
        Output("admin-perm-msg", "style"),
        Output("admin-refresh", "data", allow_duplicate=True),
        Input("admin-add-perm-btn", "n_clicks"),
        State("admin-perm-user", "value"),
        State("admin-perm-source", "value"),
        State("admin-perm-scopes", "value"),
        State("admin-refresh", "data"),
        prevent_initial_call=True,
    )
    def add_permission(_n, user_id, sources, scopes, tick):
        if not user_id:
            return "Choisissez un utilisateur.", MSG_ERR, tick
        if not sources:
            return "Choisissez au moins une source.", MSG_ERR, tick
        if not scopes:
            return "Choisissez au moins un scope.", MSG_ERR, tick

        # "*" couvre tout : inutile de créer d'autres permissions à côté
        if "*" in sources:
            sources = ["*"]

        try:
            token = auth_ui.current_token()
            saved = []
            for source in sources:
                perm = api_client.admin_upsert_permission(
                    token, int(user_id), source, scopes,
                )
                saved.append(perm["source_name"])
            return (f'Permission(s) enregistrée(s) : {", ".join(saved)} '
                    f'→ {", ".join(scopes)}.',
                    MSG_OK, (tick or 0) + 1)
        except api_client.ApiError as exc:
            msg, style = _err(exc)
            return msg, style, tick

    # ── Permissions : retirer ────────────────────────────────────────────
    @app.callback(
        Output("admin-perm-msg", "children", allow_duplicate=True),
        Output("admin-perm-msg", "style", allow_duplicate=True),
        Output("admin-refresh", "data", allow_duplicate=True),
        Input("admin-del-perm-btn", "n_clicks"),
        State("admin-perm-delete", "value"),
        State("admin-refresh", "data"),
        prevent_initial_call=True,
    )
    def delete_permission(_n, permission_id, tick):
        if not permission_id:
            return "Choisissez une permission.", MSG_ERR, tick
        try:
            api_client.admin_delete_permission(
                auth_ui.current_token(), int(permission_id),
            )
            return "Permission retirée.", MSG_OK, (tick or 0) + 1
        except api_client.ApiError as exc:
            msg, style = _err(exc)
            return msg, style, tick

    # ── Clés API : créer ─────────────────────────────────────────────────
    @app.callback(
        Output("admin-key-created", "children"),
        Output("admin-refresh", "data", allow_duplicate=True),
        Input("admin-create-key-btn", "n_clicks"),
        State("admin-key-kind", "value"),
        State("admin-key-name", "value"),
        State("admin-key-days", "value"),
        State("admin-key-source", "value"),
        State("admin-key-scopes", "value"),
        State("admin-refresh", "data"),
        prevent_initial_call=True,
    )
    def create_key(_n, kind, name, days, sources, scopes, tick):
        if not name or not name.strip():
            return html.Div("Renseignez le nom de la clé.",
                            style=MSG_ERR), tick

        if kind == "dashboard" and not sources:
            return html.Div("Un dashboard partagé doit avoir au moins "
                            "une source autorisée.", style=MSG_ERR), tick

        if sources and "*" in sources:
            sources = ["*"]

        permissions = [
            {"source_name": source, "scopes": scopes or DEFAULT_SCOPES}
            for source in (sources or [])
        ]

        try:
            created = api_client.admin_create_api_key(
                auth_ui.current_token(), name.strip(), days,
                permissions, kind=kind or "data",
            )
        except api_client.ApiError as exc:
            return html.Div(str(exc), style=MSG_ERR), tick

        if created["kind"] == "dashboard":
            access_link = f'{DASHBOARD_BASE_URL}/access/{created["api_key"]}'
            box = html.Div([
                html.Div("Lien d'accès invité créé — copiez-le MAINTENANT, "
                         "il ne sera plus jamais affiché :",
                         style={"fontFamily": FONT_FAMILY, "fontSize": "13px",
                                "fontWeight": "700", "color": "#92400E",
                                "marginBottom": "6px"}),
                html.Code(access_link, style={
                    "display": "block", "padding": "10px 12px",
                    "backgroundColor": "#FFFBEB",
                    "border": "1px solid #F59E0B",
                    "borderRadius": "7px", "fontSize": "13px",
                    "wordBreak": "break-all", "userSelect": "all",
                }),
                html.Div("À intégrer dans un intranet (lien ou iframe). "
                         "Accès viewer strict, lecture seule, filtré par "
                         "source. Désactivable à tout moment dans le "
                         "tableau ci-dessus.",
                         style={"fontFamily": FONT_FAMILY,
                                "fontSize": "12px", "color": "#64748B",
                                "marginTop": "6px"}),
            ], style={"marginTop": "12px"})
        else:
            box = html.Div([
                html.Div("Clé créée — copiez-la MAINTENANT, elle ne sera "
                         "plus jamais affichée :",
                         style={"fontFamily": FONT_FAMILY, "fontSize": "13px",
                                "fontWeight": "700", "color": "#92400E",
                                "marginBottom": "6px"}),
                html.Code(created["api_key"], style={
                    "display": "block", "padding": "10px 12px",
                    "backgroundColor": "#FFFBEB",
                    "border": "1px solid #F59E0B",
                    "borderRadius": "7px", "fontSize": "13px",
                    "wordBreak": "break-all", "userSelect": "all",
                }),
                html.Div('Usage : header "X-API-Key" sur les endpoints '
                         'de données.',
                         style={"fontFamily": FONT_FAMILY,
                                "fontSize": "12px", "color": "#64748B",
                                "marginTop": "6px"}),
            ], style={"marginTop": "12px"})

        return box, (tick or 0) + 1

    # ── Clés API : désactiver (bouton par ligne du tableau) ──────────────
    @app.callback(
        Output("admin-key-msg", "children"),
        Output("admin-key-msg", "style"),
        Output("admin-refresh", "data", allow_duplicate=True),
        Input({"type": "admin-key-disable", "index": ALL}, "n_clicks"),
        State("admin-refresh", "data"),
        prevent_initial_call=True,
    )
    def disable_key(_n_clicks_list, tick):
        # Garde : le rendu du tableau (re)crée les boutons avec n_clicks=0,
        # ce qui déclenche le callback sans clic réel.
        triggered = ctx.triggered
        if not triggered or not triggered[0].get("value"):
            return no_update, no_update, no_update

        trigger_id = ctx.triggered_id
        if not trigger_id or "index" not in trigger_id:
            return no_update, no_update, no_update

        key_id = int(trigger_id["index"])

        try:
            api_client.admin_revoke_api_key(auth_ui.current_token(), key_id)
            logger.info("Clé %s désactivée depuis la page admin.", key_id)
            return (f"Clé {key_id} désactivée.", MSG_OK, (tick or 0) + 1)
        except api_client.ApiError as exc:
            msg, style = _err(exc)
            return msg, style, tick

    # ── Fichiers sources : nom du fichier choisi ─────────────────────────
    @app.callback(
        Output("admin-upload-filename", "children"),
        Input("admin-upload-file", "filename"),
    )
    def show_selected_filename(filename):
        if not filename:
            return ""
        return f"Fichier sélectionné : {filename}"

    # ── Fichiers sources : téléverser et traiter ─────────────────────────
    @app.callback(
        Output("admin-upload-msg", "children"),
        Output("admin-upload-msg", "style"),
        Output("admin-upload-file", "contents"),
        Output("admin-refresh", "data", allow_duplicate=True),
        Input("admin-upload-btn", "n_clicks"),
        State("admin-upload-domain", "value"),
        State("admin-upload-source", "value"),
        State("admin-upload-formation", "value"),
        State("admin-upload-file", "contents"),
        State("admin-upload-file", "filename"),
        State("admin-refresh", "data"),
        prevent_initial_call=True,
    )
    def upload_source(_n, domain, source, formation, contents,
                      filename, tick):
        if not domain:
            return "Choisissez un domaine.", MSG_ERR, no_update, tick
        if not source:
            return "Choisissez une source.", MSG_ERR, no_update, tick
        if not formation or not formation.strip():
            return ("Renseignez le nom de la formation (ex. SNI).",
                    MSG_ERR, no_update, tick)
        if not contents or not filename:
            return "Choisissez un fichier.", MSG_ERR, no_update, tick

        try:
            file_bytes = base64.b64decode(contents.split(",", 1)[1])
        except Exception:
            return ("Fichier illisible, réessayez.",
                    MSG_ERR, no_update, tick)

        try:
            result = api_client.admin_upload_source(
                auth_ui.current_token(), domain, source,
                formation.strip(), filename, file_bytes,
            )
        except api_client.ApiError as exc:
            msg, style = _err(exc)
            return msg, style, no_update, tick

        outputs = result.get("outputs", {})
        message = html.Div([
            html.Div(f'Fichier traité avec succès : {result.get("file")}',
                     style={"fontWeight": "700"}),
            html.Div(f'→ {outputs.get("processed", "")}'),
            html.Div(f'→ {outputs.get("analytics", "")}'),
            html.Div("Seul ce fichier a été traité ; les autres données "
                     "n'ont pas été modifiées.",
                     style={"color": "#64748B", "fontSize": "12px"}),
        ])
        logger.info("Upload OK depuis la page admin : %s",
                    result.get("file"))
        # contents remis à zéro pour éviter un double envoi accidentel
        return message, MSG_OK, None, (tick or 0) + 1