"""
forested_pathway.py
───────────────────────────────────────────────────────────────────
Page "Carte des parcours de formation" dans ForestED.

Visualise le curriculum comme une carte horizontale :
  - Tronc commun : boîte englobante haute (couvre toutes les lignes)
  - Point de bifurcation : losange ◇
  - Parcours/options : une ligne colorée distincte par parcours
  - Zone pointillée autour des choix alternatifs

Compatible avec :
  - Polytech IDU (aucun parcours optionnel → chemin linéaire simple)
  - BUT QLIO   (parcours MP / PCLG / QPSMI)
  - Toute future source respectant le méta-modèle curriculum

Imports clés :
  - iter_curriculum_elements depuis forested_visualisations
    (version complète qui expose le champ "semestre" directement)
  - get_programme_options / get_selected_data pour la sélection
"""

from dash import html, dcc, Input, Output, State, ctx
import plotly.graph_objects as go

from forested_visualisations import (
    get_programme_options,
    get_selected_data,
    iter_curriculum_elements,
    sort_semester,
    empty_figure,
    get_ue_credits,
)
from design_tokens import (
    COLORS,
    FONT_FAMILY,
    FONT_FAMILY_SERIF_TITLE,
    SPACE,
    RADIUS,
    SHADOW,
    TYPE,
)


# ══════════════════════════════════════════════════════════════════════════════
#  DESIGN CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

PAGE_BG   = COLORS["bg_page"]
CARD_BG   = COLORS["bg_surface"]
BORDER    = COLORS["border"]

COMMUN_FILL   = COLORS["primary_light"]    # "#E6F0EF"
COMMUN_BORDER = COLORS["primary"]          # "#0E4D52"

DIAMOND_FILL   = "#EDE9FE"
DIAMOND_BORDER = "#7C3AED"

# Palette (fill, border) — 8 parcours max, stable and accessible
PARCOURS_PALETTE = [
    ("#EFF6FF", "#1D4ED8"),   # bleu
    ("#F0FDF4", "#15803D"),   # vert
    ("#FFF7ED", "#C2410C"),   # orange
    ("#FDF4FF", "#7E22CE"),   # violet
    ("#FFF1F2", "#BE123C"),   # rose
    ("#F0FDFA", "#0F766E"),   # teal vif
    ("#FEFCE8", "#A16207"),   # ambre/or
    ("#FFF5F5", "#9B1C1C"),   # rouge sombre
]

LABEL_STYLE = {
    "color": COLORS["text_secondary"],
    "fontWeight": "700",
    "fontSize": "10px",
    "letterSpacing": "1px",
    "textTransform": "uppercase",
    "marginBottom": "7px",
    "display": "block",
    "fontFamily": FONT_FAMILY,
}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _sem_label(s):
    """Normalise un identifiant de semestre en chaîne 'Sx'."""
    s_str = str(s).strip().upper()
    if s_str.startswith("S"):
        return s_str
    try:
        return f"S{int(s_str)}"
    except Exception:
        return s_str


def _bezier_h(x0, y0, x1, y1):
    """Chemin Bézier cubique avec tangentes horizontales (S-curve)."""
    cx = (x0 + x1) / 2.0
    return f"M {x0},{y0} C {cx},{y0} {cx},{y1} {x1},{y1}"


def _legend_item(fill, border, label):
    """Petit badge coloré pour la légende."""
    return html.Div([
        html.Div(style={
            "width": "14px", "height": "10px",
            "backgroundColor": fill,
            "border": f"2px solid {border}",
            "borderRadius": "3px",
            "display": "inline-block",
            "marginRight": "6px",
            "verticalAlign": "middle",
            "flexShrink": "0",
        }),
        html.Span(label, style={
            "fontSize": "11px",
            "color": COLORS["text_secondary"],
            "fontFamily": FONT_FAMILY,
            "verticalAlign": "middle",
        }),
    ], style={"display": "flex", "alignItems": "center"})


# ══════════════════════════════════════════════════════════════════════════════
#  DONNÉES — build_pathway_data
# ══════════════════════════════════════════════════════════════════════════════

def build_pathway_data(curriculum_data):
    """
    Transforme un curriculum (dict méta-modèle) en liste de dicts
    représentant chaque cellule (semestre × parcours) de la carte.

    Retourne une liste de dicts :
    {
        "semestre"     : valeur brute (int ou str),
        "semestre_str" : str(semestre),
        "parcours"     : "COMMUN" | "MP" | "PCLG" | ...,
        "type"         : "TRONC_COMMUN" | "PARCOURS",
        "ue_count"     : int,
        "module_count" : int,
        "credits"      : float,
        "ue_codes"     : [str, ...],
        "module_codes" : [str, ...],
    }
    """
    if not curriculum_data:
        return []

    pathway = {}           # (semestre_str, parcours) -> dict
    ue_credits_seen = {}   # (key, ue_code) -> bool  (pour ne pas doubler les crédits)

    for row in iter_curriculum_elements(curriculum_data):
        periode  = row["periode"]
        ue       = row["ue"]
        parcours = row.get("parcours") or "COMMUN"
        element  = row["element"]

        # semestre : priorité au champ "semestre" déjà calculé par iter_curriculum_elements
        semestre = row.get("semestre")
        if semestre is None:
            semestre = (
                periode.get("numero")
                or periode.get("semestre")
                or periode.get("id")
            )

        key = (str(semestre), parcours)

        if key not in pathway:
            pathway[key] = {
                "semestre":     semestre,
                "semestre_str": str(semestre),
                "parcours":     parcours,
                "type":         "TRONC_COMMUN" if parcours == "COMMUN" else "PARCOURS",
                "ue_codes":     set(),
                "module_codes": set(),
                "credits":      0.0,
            }

        ue_code = ue.get("code") or ue.get("id")
        if ue_code:
            pathway[key]["ue_codes"].add(ue_code)
            ue_credit_key = (key, ue_code)
            if ue_credit_key not in ue_credits_seen:
                ue_credits_seen[ue_credit_key] = True
                pathway[key]["credits"] += float(get_ue_credits(ue) or 0.0)

        module_id = element.get("id")
        if module_id:
            pathway[key]["module_codes"].add(module_id)

    result = []
    for item in pathway.values():
        result.append({
            "semestre":      item["semestre"],
            "semestre_str":  item["semestre_str"],
            "parcours":      item["parcours"],
            "type":          item["type"],
            "ue_count":      len(item["ue_codes"]),
            "module_count":  len(item["module_codes"]),
            "credits":       round(item["credits"], 1),
            "ue_codes":      sorted(item["ue_codes"]),
            "module_codes":  sorted(item["module_codes"]),
        })

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  FIGURE — create_pathway_figure
# ══════════════════════════════════════════════════════════════════════════════

def create_pathway_figure(pathway_data, programme_label=""):
    """
    Construit la figure Plotly de la carte des parcours.

    Layout :
    ┌──────────────────────────────────────────────────────────┐
    │  S1         S2          ◇        S3    S4    S5    S6    │
    │                                                          │
    │  ┌─────────────────┐        ┌─────┐ ┌─────┐ ...  MP    │
    │  │                 │  ────► │     │ │     │            │
    │  │  Tronc commun   │  ────► ├─────┤ ├─────┤ ... PCLG  │
    │  │                 │  ────► │     │ │     │            │
    │  └─────────────────┘        └─────┘ └─────┘ ... QPSMI │
    └──────────────────────────────────────────────────────────┘
    """
    if not pathway_data:
        return empty_figure("Aucune donnée de curriculum disponible")

    # ── 1. Indexation ──────────────────────────────────────────────────────
    semestres_data = {}   # str(sem) -> { parcours -> item }
    for item in pathway_data:
        s = item["semestre_str"]
        p = item["parcours"]
        semestres_data.setdefault(s, {})[p] = item

    semestres_sorted = sorted(semestres_data.keys(), key=sort_semester)

    all_parcours = sorted({
        p
        for s_data in semestres_data.values()
        for p in s_data
        if p != "COMMUN"
    })
    N = len(all_parcours)

    # ── 2. Point de bifurcation ────────────────────────────────────────────
    split_idx = len(semestres_sorted)  # défaut : pas de bifurcation
    for i, s in enumerate(semestres_sorted):
        if any(p != "COMMUN" for p in semestres_data[s]):
            split_idx = i
            break

    commun_sems   = semestres_sorted[:split_idx]
    parcours_sems = semestres_sorted[split_idx:]

    # ── 3. Constantes de mise en page ──────────────────────────────────────
    ROW_HEIGHT    = 2.8   # espace vertical entre lignes de parcours
    BOX_HW        = 1.15  # demi-largeur des boîtes
    BOX_HH        = 0.70  # demi-hauteur des boîtes de parcours
    DIAM_R        = 0.60  # rayon du losange
    X_GAP         = 3.4   # espacement standard entre colonnes
    X_SPLIT_PAD   = 2.0   # espace extra autour du point de bifurcation

    # Positions Y
    if N == 0:
        y_center  = 0.0
        parcours_y = {}
        y_top     = BOX_HH
        y_bottom  = -BOX_HH
    else:
        # Parcours : ligne 0 en haut, ligne N-1 en bas
        parcours_y = {p: (N - 1 - i) * ROW_HEIGHT for i, p in enumerate(all_parcours)}
        y_center   = (N - 1) * ROW_HEIGHT / 2.0
        y_top      = max(parcours_y.values()) + BOX_HH
        y_bottom   = min(parcours_y.values()) - BOX_HH

    # Positions X avec espace supplémentaire à la bifurcation
    sem_x  = {}
    cursor = 0.0
    for i, s in enumerate(semestres_sorted):
        sem_x[s] = cursor
        if i == split_idx - 1 and split_idx < len(semestres_sorted):
            cursor += X_GAP + X_SPLIT_PAD * 2
        else:
            cursor += X_GAP

    # Position du losange (milieu entre dernière boîte COMMUN et première PARCOURS)
    diamond_x = None
    if commun_sems and parcours_sems:
        x_left  = sem_x[commun_sems[-1]]  + BOX_HW
        x_right = sem_x[parcours_sems[0]] - BOX_HW
        diamond_x = (x_left + x_right) / 2.0

    # Couleurs des parcours
    parcours_colors = {
        p: PARCOURS_PALETTE[i % len(PARCOURS_PALETTE)]
        for i, p in enumerate(all_parcours)
    }

    # ── 4. Construction des formes et annotations ──────────────────────────
    shapes      = []
    annotations = []

    # ── 4a. En-têtes de colonnes (semestres) ──────────────────────────────
    y_header = y_top + 1.3
    for s in semestres_sorted:
        annotations.append(dict(
            x=sem_x[s], y=y_header,
            text=f"<b>{_sem_label(s)}</b>",
            showarrow=False,
            font=dict(size=13, color=COLORS["text_primary"], family=FONT_FAMILY),
            xanchor="center", yanchor="bottom",
        ))

    # ── 4b. Lignes guides des parcours (fond de la zone de choix) ──────────
    if parcours_sems and all_parcours:
        for p in all_parcours:
            y_p = parcours_y[p]
            fill, border = parcours_colors[p]
            shapes.append(dict(
                type="line",
                x0=sem_x[parcours_sems[0]] - BOX_HW - 0.3,
                y0=y_p,
                x1=sem_x[parcours_sems[-1]] + BOX_HW + 0.3,
                y1=y_p,
                line=dict(color=border, width=0.8, dash="dot"),
                layer="below",
            ))

    # ── 4c. Zone pointillée (rectangle des choix) ──────────────────────────
    if parcours_sems and all_parcours:
        x0z = sem_x[parcours_sems[0]]  - BOX_HW - 0.7
        x1z = sem_x[parcours_sems[-1]] + BOX_HW + 0.7
        y0z = y_bottom - 0.7
        y1z = y_top    + 0.7
        shapes.append(dict(
            type="rect",
            x0=x0z, y0=y0z, x1=x1z, y1=y1z,
            fillcolor="rgba(109, 40, 217, 0.03)",
            line=dict(color="rgba(109, 40, 217, 0.35)", width=1.5, dash="dash"),
            layer="below",
        ))
        annotations.append(dict(
            x=(x0z + x1z) / 2,
            y=y1z + 0.3,
            text="<i>Zone de choix — un seul parcours à choisir</i>",
            showarrow=False,
            font=dict(size=9, color=DIAMOND_BORDER, family=FONT_FAMILY),
            xanchor="center", yanchor="bottom",
        ))

    # ── 4d. Boîtes TRONC COMMUN (hauteur = toute la zone parcours) ─────────
    for sem in commun_sems:
        x     = sem_x[sem]
        item  = semestres_data[sem].get("COMMUN", {})
        box_h = (y_top - y_bottom) / 2.0 if N > 0 else BOX_HH

        shapes.append(dict(
            type="rect",
            x0=x - BOX_HW, y0=y_center - box_h,
            x1=x + BOX_HW, y1=y_center + box_h,
            fillcolor=COMMUN_FILL,
            line=dict(color=COMMUN_BORDER, width=2.0),
            layer="above",
        ))

        credits_str = f"· {item.get('credits', 0):.0f} ECTS" if item.get("credits") else ""
        annotations.append(dict(
            x=x, y=y_center,
            text=(
                f"<b>{_sem_label(sem)}</b><br>"
                f"<span style='font-size:9px;color:{COMMUN_BORDER}'>"
                f"Tronc commun</span><br>"
                f"<span style='font-size:9px;color:#6B7280'>"
                f"{item.get('ue_count', 0)} UE · {item.get('module_count', 0)} mod. {credits_str}</span>"
            ),
            showarrow=False,
            font=dict(size=11, color=COMMUN_BORDER, family=FONT_FAMILY_SERIF_TITLE),
            xanchor="center", yanchor="middle",
        ))

    # ── 4e. Connexions COMMUN → COMMUN ─────────────────────────────────────
    for i in range(len(commun_sems) - 1):
        shapes.append(dict(
            type="line",
            x0=sem_x[commun_sems[i]]     + BOX_HW,
            y0=y_center,
            x1=sem_x[commun_sems[i + 1]] - BOX_HW,
            y1=y_center,
            line=dict(color=COMMUN_BORDER, width=2.0),
        ))

    # ── 4f. Losange ◇ ─────────────────────────────────────────────────────
    if diamond_x is not None:
        d = DIAM_R
        shapes.append(dict(
            type="path",
            path=(
                f"M {diamond_x},{y_center + d} "
                f"L {diamond_x + d},{y_center} "
                f"L {diamond_x},{y_center - d} "
                f"L {diamond_x - d},{y_center} Z"
            ),
            fillcolor=DIAMOND_FILL,
            line=dict(color=DIAMOND_BORDER, width=2.0),
            layer="above",
        ))
        annotations.append(dict(
            x=diamond_x, y=y_center,
            text=f"<b style='color:{DIAMOND_BORDER}'>Choix</b>",
            showarrow=False,
            font=dict(size=8, color=DIAMOND_BORDER, family=FONT_FAMILY),
            xanchor="center", yanchor="middle",
        ))

    # ── 4g. Connexion dernier COMMUN → losange ─────────────────────────────
    if diamond_x is not None and commun_sems:
        shapes.append(dict(
            type="line",
            x0=sem_x[commun_sems[-1]] + BOX_HW,
            y0=y_center,
            x1=diamond_x - DIAM_R,
            y1=y_center,
            line=dict(color=COMMUN_BORDER, width=2.0),
        ))

    # ── 4h. Connexions losange → premières boîtes parcours (Bézier) ────────
    if diamond_x is not None and parcours_sems and all_parcours:
        x_to = sem_x[parcours_sems[0]] - BOX_HW
        for p in all_parcours:
            if p not in semestres_data.get(parcours_sems[0], {}):
                continue
            y_p = parcours_y[p]
            fill, border = parcours_colors[p]
            shapes.append(dict(
                type="path",
                path=_bezier_h(diamond_x + DIAM_R, y_center, x_to, y_p),
                fillcolor="rgba(0,0,0,0)",
                line=dict(color=border, width=1.8),
            ))

    # ── 4i. Boîtes PARCOURS ────────────────────────────────────────────────
    for sem in parcours_sems:
        x = sem_x[sem]
        for p in all_parcours:
            item = semestres_data.get(sem, {}).get(p)
            if item is None:
                continue
            fill, border = parcours_colors[p]
            y_p = parcours_y[p]

            shapes.append(dict(
                type="rect",
                x0=x - BOX_HW, y0=y_p - BOX_HH,
                x1=x + BOX_HW, y1=y_p + BOX_HH,
                fillcolor=fill,
                line=dict(color=border, width=1.8),
                layer="above",
            ))

            credits_str = f"· {item.get('credits', 0):.0f} ECTS" if item.get("credits") else ""
            annotations.append(dict(
                x=x, y=y_p,
                text=(
                    f"<b>{_sem_label(sem)}</b><br>"
                    f"<span style='font-size:9px;color:#6B7280'>"
                    f"{item.get('ue_count', 0)} UE · {item.get('module_count', 0)} mod. {credits_str}</span>"
                ),
                showarrow=False,
                font=dict(size=10, color=border, family=FONT_FAMILY),
                xanchor="center", yanchor="middle",
            ))

    # ── 4j. Connexions entre boîtes de parcours consécutives ────────────────
    for i in range(len(parcours_sems) - 1):
        s_from = parcours_sems[i]
        s_to   = parcours_sems[i + 1]
        for p in all_parcours:
            if p not in semestres_data.get(s_from, {}):
                continue
            if p not in semestres_data.get(s_to, {}):
                continue
            y_p = parcours_y[p]
            _, border = parcours_colors[p]
            shapes.append(dict(
                type="line",
                x0=sem_x[s_from] + BOX_HW, y0=y_p,
                x1=sem_x[s_to]   - BOX_HW, y1=y_p,
                line=dict(color=border, width=1.8),
            ))

    # ── 4k. Étiquettes des parcours (à gauche) ─────────────────────────────
    if all_parcours and (commun_sems or parcours_sems):
        ref_s = commun_sems[-1] if commun_sems else parcours_sems[0]
        x_labels = sem_x[ref_s] - BOX_HW - 0.9
        for p in all_parcours:
            _, border = parcours_colors[p]
            y_p = parcours_y[p]
            annotations.append(dict(
                x=x_labels, y=y_p,
                text=f"<b>{p}</b>",
                showarrow=False,
                font=dict(size=10, color=border, family=FONT_FAMILY),
                xanchor="right", yanchor="middle",
            ))

    # ── 4l. Étiquette "COMMUN" si pas de parcours (formation linéaire) ──────
    if N == 0 and commun_sems:
        x_label = sem_x[commun_sems[0]] - BOX_HW - 0.9
        annotations.append(dict(
            x=x_label, y=y_center,
            text=f"<b>Tronc commun</b>",
            showarrow=False,
            font=dict(size=10, color=COMMUN_BORDER, family=FONT_FAMILY),
            xanchor="right", yanchor="middle",
        ))

    # ── 5. Points invisibles pour hover et clic ────────────────────────────
    hover_x, hover_y, hover_text, hover_custom = [], [], [], []

    for sem_str, sdata in semestres_data.items():
        for parcours, item in sdata.items():
            x = sem_x.get(sem_str, 0)
            y = parcours_y.get(parcours, y_center) if parcours != "COMMUN" else y_center

            credits_line = (
                f"<br>ECTS : {item.get('credits', 0):.0f}"
                if item.get("credits") else ""
            )
            ue_preview = ", ".join(item.get("ue_codes", [])[:3])
            if len(item.get("ue_codes", [])) > 3:
                ue_preview += f" … (+{len(item['ue_codes']) - 3})"

            hover_text.append(
                f"<b>{_sem_label(sem_str)} — {parcours}</b><br>"
                f"UE : {item.get('ue_count', 0)}"
                f"{credits_line}<br>"
                f"Modules : {item.get('module_count', 0)}<br>"
                + (f"<span style='color:#94A3B8;font-size:10px'>{ue_preview}</span><br>" if ue_preview else "")
                + f"<span style='color:#94A3B8;font-size:10px'>Cliquez pour le détail</span>"
            )
            hover_x.append(x)
            hover_y.append(y)
            hover_custom.append(f"{sem_str}::{parcours}")

    traces = []
    if hover_x:
        traces.append(go.Scatter(
            x=hover_x,
            y=hover_y,
            mode="markers",
            marker=dict(
                size=40,
                color="rgba(0,0,0,0)",
                symbol="square",
            ),
            hovertext=hover_text,
            hoverinfo="text",
            hoverlabel=dict(
                bgcolor=COLORS["primary_dark"],
                bordercolor=COLORS["accent"],
                font=dict(color="white", size=12, family=FONT_FAMILY),
            ),
            customdata=hover_custom,
            showlegend=False,
        ))

    # ── 6. Layout Plotly ───────────────────────────────────────────────────
    x_vals    = list(sem_x.values())
    x_min_fig = (min(x_vals) if x_vals else 0) - BOX_HW - 3.0
    x_max_fig = (max(x_vals) if x_vals else 0) + BOX_HW + 1.5
    y_min_fig = y_bottom - 1.8
    y_max_fig = y_header + 1.5

    fig_height = max(420, 200 + max(N, 1) * 160)

    subtitle_parts = [f"{len(semestres_sorted)} semestre(s)"]
    if N > 0:
        subtitle_parts.append(f"{N} parcours")
        subtitle_parts.append(
            f"tronc commun jusqu'à {_sem_label(commun_sems[-1])}"
            if commun_sems else "pas de tronc commun détecté"
        )
    else:
        subtitle_parts.append("formation sans parcours optionnel")

    subtitle = (
        f"<span style='font-size:12px;color:{COLORS['text_secondary']}'>"
        + " · ".join(subtitle_parts)
        + "</span>"
    )

    title_label = f" — {programme_label}" if programme_label else ""

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(
            text=(
                f"<b>Carte des parcours{title_label}</b><br>{subtitle}"
            ),
            font=dict(
                size=15,
                color=COLORS["text_primary"],
                family=FONT_FAMILY_SERIF_TITLE,
            ),
            x=0.01, y=0.99, xanchor="left",
        ),
        shapes=shapes,
        annotations=annotations,
        height=fig_height,
        paper_bgcolor=PAGE_BG,
        plot_bgcolor=CARD_BG,
        xaxis=dict(
            range=[x_min_fig, x_max_fig],
            showgrid=False, zeroline=False, showticklabels=False,
            constrain="domain",
        ),
        yaxis=dict(
            range=[y_min_fig, y_max_fig],
            showgrid=False, zeroline=False, showticklabels=False,
            scaleanchor=None,
        ),
        margin=dict(l=160, r=40, t=80, b=40),
        hovermode="closest",
        clickmode="event",
        showlegend=False,
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  PANNEAU DÉTAIL
# ══════════════════════════════════════════════════════════════════════════════

def _build_detail_panel(clicked_key, pathway_data):
    """Construit le panneau détail latéral après clic sur une boîte."""
    if not clicked_key or not pathway_data:
        return html.Div()

    parts = clicked_key.split("::", 1)
    if len(parts) != 2:
        return html.Div()

    sem_str, parcours = parts
    matching = [
        item for item in pathway_data
        if item["semestre_str"] == sem_str and item["parcours"] == parcours
    ]
    if not matching:
        return html.Div()

    item = matching[0]

    # Couleur du bord selon parcours
    border_color = COMMUN_BORDER
    if parcours != "COMMUN":
        all_parcours_sorted = sorted({
            i["parcours"] for i in pathway_data if i["parcours"] != "COMMUN"
        })
        idx = all_parcours_sorted.index(parcours) if parcours in all_parcours_sorted else 0
        _, border_color = PARCOURS_PALETTE[idx % len(PARCOURS_PALETTE)]

    ue_list  = item.get("ue_codes", [])
    mod_list = item.get("module_codes", [])
    mod_count = item.get("module_count", 0)
    show_mod  = mod_list[:20]
    has_more  = mod_count > 20
    credits_line = f" · {item.get('credits', 0):.0f} ECTS" if item.get("credits") else ""

    def tag(text, bg, fg):
        return html.Span(text, style={
            "backgroundColor": bg, "color": fg,
            "borderRadius": "4px", "padding": "2px 7px",
            "fontSize": "11px", "marginRight": "4px",
            "marginBottom": "4px", "display": "inline-block",
            "fontFamily": FONT_FAMILY,
        })

    return html.Div([
        html.Div([
            html.Span(style={
                "width": "10px", "height": "10px", "borderRadius": "2px",
                "backgroundColor": border_color,
                "display": "inline-block", "marginRight": "8px",
            }),
            html.Span(
                f"{_sem_label(sem_str)} — {parcours}",
                style={
                    "fontWeight": "700", "fontSize": "14px",
                    "color": COLORS["text_primary"],
                    "fontFamily": FONT_FAMILY_SERIF_TITLE,
                }
            ),
            html.Span(
                f"  {item.get('ue_count', 0)} UE · {mod_count} modules{credits_line}",
                style={
                    "fontSize": "12px", "color": COLORS["text_secondary"],
                    "marginLeft": "8px", "fontFamily": FONT_FAMILY,
                }
            ),
        ], style={
            "display": "flex", "alignItems": "center", "marginBottom": "12px"
        }),

        html.P(
            f"📚 {len(ue_list)} unité(s) d'enseignement",
            style={
                "fontWeight": "700", "color": COMMUN_BORDER,
                "fontSize": "12px", "margin": "0 0 6px",
            }
        ),
        html.Div([
            tag(ue, COMMUN_FILL, COMMUN_BORDER)
            for ue in ue_list
        ], style={"display": "flex", "flexWrap": "wrap", "marginBottom": "10px"}),

        html.P(
            f"📦 {mod_count} module(s)"
            + (" (20 premiers affichés)" if has_more else ""),
            style={
                "fontWeight": "700", "color": COLORS["info"],
                "fontSize": "12px", "margin": "0 0 6px",
            }
        ),
        html.Div([
            tag(m, "#DBEAFE", "#1E3A8A")
            for m in show_mod
        ], style={"display": "flex", "flexWrap": "wrap"}),

        html.P(
            "Cliquez sur la même boîte ou sur ✕ Effacer pour fermer.",
            style={
                "fontSize": "11px", "color": COLORS["text_muted"],
                "margin": "12px 0 0", "fontStyle": "italic",
                "fontFamily": FONT_FAMILY,
            }
        ),
    ], style={
        "backgroundColor": CARD_BG,
        "border": f"1px solid {BORDER}",
        "borderLeft": f"4px solid {border_color}",
        "borderRadius": RADIUS["md"],
        "padding": "14px 18px",
        "boxShadow": SHADOW["card"],
        "marginBottom": "16px",
    })


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT DASH
# ══════════════════════════════════════════════════════════════════════════════

_pathway_programme_options = get_programme_options()

forested_pathway_layout = html.Div([

    # ── En-tête ─────────────────────────────────────────────────────────────
    html.Div([
        html.H1(
            "Carte des parcours de formation",
            style={
                **TYPE["h1"],
                "marginBottom": SPACE["xs"],
            }
        ),
        html.P(
            "Visualisation du tronc commun, des bifurcations et des parcours possibles semestre par semestre.",
            style={
                "fontFamily": FONT_FAMILY,
                "fontSize": "14px",
                "color": COLORS["text_secondary"],
                "margin": "0",
            }
        ),
    ], style={"marginBottom": SPACE["xl"]}),

    # ── Barre de contrôles ──────────────────────────────────────────────────
    html.Div([
        html.Div([
            html.Label("Formation", style=LABEL_STYLE),
            dcc.Dropdown(
                id="pathway-programme-selector",
                options=_pathway_programme_options,
                value=None,
                clearable=False,
                style={"fontSize": "14px"},
            ),
        ], style={"width": "42%", "minWidth": "220px"}),

        html.Div([
            html.Label("\u00a0", style={**LABEL_STYLE, "visibility": "hidden"}),
            html.Button(
                "✕ Effacer la sélection",
                id="pathway-reset",
                n_clicks=0,
                style={
                    "height": "34px",
                    "padding": "0 14px",
                    "backgroundColor": "#F1F5F9",
                    "color": COLORS["text_secondary"],
                    "border": f"1px solid {COLORS['border_strong']}",
                    "borderRadius": RADIUS["sm"],
                    "cursor": "pointer",
                    "fontSize": "12px",
                    "fontWeight": "600",
                    "fontFamily": FONT_FAMILY,
                }
            ),
        ], style={"display": "flex", "flexDirection": "column"}),

    ], style={
        "backgroundColor": CARD_BG,
        "border": f"1px solid {BORDER}",
        "padding": f"{SPACE['md']} {SPACE['lg']}",
        "borderRadius": RADIUS["md"],
        "boxShadow": SHADOW["card"],
        "marginBottom": SPACE["md"],
        "display": "flex",
        "alignItems": "flex-end",
        "flexWrap": "wrap",
        "gap": SPACE["md"],
    }),

    # ── Légende ─────────────────────────────────────────────────────────────
    html.Div([
        _legend_item(COMMUN_FILL, COMMUN_BORDER, "Tronc commun"),
        _legend_item(DIAMOND_FILL, DIAMOND_BORDER, "Point de bifurcation"),
    ] + [
        _legend_item(PARCOURS_PALETTE[i][0], PARCOURS_PALETTE[i][1], f"Parcours {i + 1}")
        for i in range(min(4, len(PARCOURS_PALETTE)))
    ], style={
        "display": "flex",
        "gap": "16px",
        "flexWrap": "wrap",
        "marginBottom": SPACE["md"],
        "padding": f"10px {SPACE['lg']}",
        "backgroundColor": CARD_BG,
        "border": f"1px solid {BORDER}",
        "borderRadius": RADIUS["md"],
    }),

    # ── Stores ──────────────────────────────────────────────────────────────
    dcc.Store(id="pathway-data-store"),
    dcc.Store(id="pathway-selected-cell"),

    # ── Panneau détail ──────────────────────────────────────────────────────
    html.Div(id="pathway-detail-panel"),

    # ── Graphique principal ──────────────────────────────────────────────────
    html.Div([
        dcc.Graph(
            id="pathway-graph",
            config={
                "displayModeBar": True,
                "displaylogo": False,
                "scrollZoom": True,
                "responsive": True,
                "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
            },
        )
    ], style={
        "backgroundColor": CARD_BG,
        "border": f"1px solid {BORDER}",
        "borderRadius": RADIUS["md"],
        "boxShadow": SHADOW["card"],
        "overflow": "hidden",
    }),

], style={
    "backgroundColor": PAGE_BG,
    "minHeight": "100vh",
    "padding": "48px 56px",
    "fontFamily": FONT_FAMILY,
})


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def register_callbacks(app):

    @app.callback(
        Output("pathway-programme-selector", "value"),
        Input("pathway-programme-selector", "options"),
        State("pathway-programme-selector", "value"),
        prevent_initial_call=False,
    )
    def _init_pathway_selector(options, current):
        """Initialise le dropdown au premier programme disponible."""
        if current is not None:
            return current
        if options:
            return options[0]["value"]
        return None

    @app.callback(
        Output("pathway-data-store", "data"),
        Input("pathway-programme-selector", "value"),
    )
    def _load_pathway_data(selected_programme):
        """Charge et transforme le curriculum sélectionné."""
        if not selected_programme:
            return []
        _, curr_data = get_selected_data(selected_programme)
        if not curr_data:
            return []
        return build_pathway_data(curr_data)

    @app.callback(
        Output("pathway-graph", "figure"),
        Output("pathway-selected-cell", "data"),
        Input("pathway-data-store", "data"),
        Input("pathway-graph", "clickData"),
        Input("pathway-reset", "n_clicks"),
        Input("pathway-programme-selector", "value"),
        State("pathway-selected-cell", "data"),
    )
    def _update_graph(pathway_data, click_data, _n_reset, selected_programme, selected_cell):
        """Redessine le graphe et gère la sélection d'une cellule."""
        triggered = ctx.triggered_id

        if triggered in ("pathway-reset", "pathway-programme-selector"):
            selected_cell = None

        if triggered == "pathway-graph" and click_data:
            clicked = click_data["points"][0].get("customdata")
            # Toggle : second clic sur la même cellule = désélection
            selected_cell = None if clicked == selected_cell else clicked

        # Label programme pour le titre du graphe
        label = ""
        if selected_programme:
            parts = selected_programme.split("::", 1)
            if len(parts) == 2:
                label = f"{parts[0]} — {parts[1]}"

        fig = create_pathway_figure(pathway_data or [], label)
        return fig, selected_cell

    @app.callback(
        Output("pathway-detail-panel", "children"),
        Input("pathway-selected-cell", "data"),
        State("pathway-data-store", "data"),
    )
    def _update_detail_panel(selected_cell, pathway_data):
        """Affiche le panneau de détail pour la cellule sélectionnée."""
        return _build_detail_panel(selected_cell, pathway_data or [])