"""
design_tokens.py
─────────────────
Design system centralisé pour ForestED.

Objectif : une seule source de vérité pour les couleurs, la typographie,
les espacements et les ombres, afin que toutes les pages (Accueil,
Visualisations, ForestED, Sunburst APC) partagent une identité visuelle
cohérente — style académique / institutionnel (proche identité
Université Savoie Mont Blanc / LISTIC).

Toutes les pages doivent importer leurs styles d'ici plutôt que de
redéfinir des couleurs en dur. Cela centralise toute évolution de
charte graphique en un seul fichier.
"""

# ══════════════════════════════════════════════════════════════════════════════
#  COULEURS
# ══════════════════════════════════════════════════════════════════════════════

COLORS = {
    # Identité institutionnelle — bleu pétrole / teal foncé (écho LISTIC/USMB)
    "primary": "#0E4D52",         # bleu pétrole — couleur de marque principale
    "primary_dark": "#0A363A",    # navbar, headers — teal très foncé, pas marine
    "primary_light": "#E6F0EF",   # fonds teintés, hover léger
    "accent": "#3FAE96",          # teal clair vif — accents, liens actifs, highlights
    "accent_light": "#E4F3F0",

    # Neutres — base du style académique sobre
    "bg_page": "#F5F6F8",
    "bg_surface": "#FFFFFF",
    "border": "#DDE2EA",
    "border_strong": "#C5CCD8",

    # Texte
    "text_primary": "#1A2333",
    "text_secondary": "#5B6576",
    "text_muted": "#8993A4",
    "text_on_dark": "#F4F6FA",
    "text_on_dark_muted": "#AEB9CC",

    # États sémantiques
    "success": "#1F8A5F",
    "success_bg": "#E5F4ED",
    "warning": "#B7791F",
    "warning_bg": "#FDF3E0",
    "danger": "#B33636",
    "danger_bg": "#FBEAEA",
    "info": "#2563A8",
    "info_bg": "#E7F0FA",
}

# ══════════════════════════════════════════════════════════════════════════════
#  TYPOGRAPHIE
# ══════════════════════════════════════════════════════════════════════════════

FONT_FAMILY = "'Source Sans Pro', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
FONT_FAMILY_SERIF_TITLE = "'Source Serif Pro', Georgia, 'Times New Roman', serif"

TYPE = {
    "h1": {
        "fontFamily": FONT_FAMILY_SERIF_TITLE,
        "fontSize": "30px",
        "fontWeight": "700",
        "color": COLORS["text_primary"],
        "letterSpacing": "-0.3px",
        "margin": "0",
    },
    "h2": {
        "fontFamily": FONT_FAMILY_SERIF_TITLE,
        "fontSize": "21px",
        "fontWeight": "700",
        "color": COLORS["text_primary"],
        "margin": "0",
    },
    "h3": {
        "fontFamily": FONT_FAMILY,
        "fontSize": "16px",
        "fontWeight": "700",
        "color": COLORS["text_primary"],
        "margin": "0",
    },
    "body": {
        "fontFamily": FONT_FAMILY,
        "fontSize": "14.5px",
        "color": COLORS["text_secondary"],
        "lineHeight": "1.6",
    },
    "small": {
        "fontFamily": FONT_FAMILY,
        "fontSize": "12.5px",
        "color": COLORS["text_muted"],
    },
    "eyebrow": {
        "fontFamily": FONT_FAMILY,
        "fontSize": "11px",
        "fontWeight": "700",
        "letterSpacing": "1.1px",
        "textTransform": "uppercase",
        "color": COLORS["accent"],
    },
}

# ══════════════════════════════════════════════════════════════════════════════
#  ESPACEMENTS & RAYONS
# ══════════════════════════════════════════════════════════════════════════════

SPACE = {"xs": "6px", "sm": "10px", "md": "16px", "lg": "24px", "xl": "36px", "xxl": "48px"}
RADIUS = {"sm": "6px", "md": "10px", "lg": "14px"}

SHADOW = {
    "card": "0 1px 2px rgba(16,24,40,0.04), 0 1px 6px rgba(16,24,40,0.05)",
    "card_hover": "0 2px 4px rgba(16,24,40,0.06), 0 8px 20px rgba(16,24,40,0.08)",
    "navbar": "0 1px 0 rgba(16,24,40,0.06), 0 2px 10px rgba(16,24,40,0.04)",
}

# ══════════════════════════════════════════════════════════════════════════════
#  STYLES DE COMPOSANTS PARTAGÉS
# ══════════════════════════════════════════════════════════════════════════════

PAGE_STYLE = {
    "backgroundColor": COLORS["bg_page"],
    "minHeight": "calc(100vh - 64px)",
    "padding": f"{SPACE['xl']} {SPACE['xxl']}",
    "fontFamily": FONT_FAMILY,
}

CARD_STYLE = {
    "backgroundColor": COLORS["bg_surface"],
    "border": f"1px solid {COLORS['border']}",
    "borderRadius": RADIUS["md"],
    "boxShadow": SHADOW["card"],
    "padding": SPACE["lg"],
}

BADGE_BASE = {
    "display": "inline-flex",
    "alignItems": "center",
    "padding": "3px 11px",
    "borderRadius": "999px",
    "fontSize": "11.5px",
    "fontWeight": "600",
    "letterSpacing": "0.2px",
    "marginRight": "8px",
}


def badge_style(kind="info"):
    """kind: success | warning | danger | info | neutral"""
    mapping = {
        "success": (COLORS["success_bg"], COLORS["success"]),
        "warning": (COLORS["warning_bg"], COLORS["warning"]),
        "danger": (COLORS["danger_bg"], COLORS["danger"]),
        "info": (COLORS["info_bg"], COLORS["info"]),
        "neutral": (COLORS["primary_light"], COLORS["text_secondary"]),
    }
    bg, fg = mapping.get(kind, mapping["neutral"])
    return {**BADGE_BASE, "backgroundColor": bg, "color": fg}


def button_style(variant="primary"):
    base = {
        "fontFamily": FONT_FAMILY,
        "fontSize": "13.5px",
        "fontWeight": "600",
        "padding": "9px 18px",
        "borderRadius": RADIUS["sm"],
        "border": "none",
        "cursor": "pointer",
        "transition": "all 0.15s ease",
    }
    if variant == "primary":
        return {**base, "backgroundColor": COLORS["primary"], "color": COLORS["text_on_dark"]}
    if variant == "secondary":
        return {
            **base,
            "backgroundColor": COLORS["bg_surface"],
            "color": COLORS["primary"],
            "border": f"1px solid {COLORS['border_strong']}",
        }
    return base