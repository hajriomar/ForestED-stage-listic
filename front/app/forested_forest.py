"""
forested_forest.py — ForestED : Forêt pédagogique APC
═══════════════════════════════════════════════════════

Hiérarchie visuelle (bas → haut) :

    ████ ███ █████  ← BARRES AC  (hauteur ∝ nb modules, colorées par niveau)
      │   │    │
    [N1] [N2] [N3]  ← NŒUDS NIVEAU  (carrés colorés, espacés horizontalement)
         │
        ◆           ← RACINE COMPÉTENCE  (losange bleu)

Interaction :
  - Clic sur une barre → panneau détail (AC + modules)
  - Clic sur un niveau → panneau détail (tous les AC du niveau)
  - Clic sur la racine → panneau détail (toute la compétence)
  - Double-clic ou re-clic → reset focus
  - Bouton Réinitialiser → reset

Sources :
  - Polytech : référentiel + curriculum → build_visualisation_rows
  - BUT       : curriculum seul          → build_rows_from_curriculum
"""

import re
from dash import html, dcc, Input, Output, State, ctx
import plotly.graph_objects as go

from app_tools import load_processed_files, build_programmes_summary
from forested_visualisations import (
    get_selected_data,
    build_visualisation_rows,
    empty_figure,
)

try:
    from forested_visualisations import normalize_module_code, iter_curriculum_elements
    _HAS_HELPERS = True
except Exception:
    _HAS_HELPERS = False


# ══════════════════════════════════════════════════════════════════════════════
#  DESIGN TOKENS
# ══════════════════════════════════════════════════════════════════════════════

PAGE_STYLE = {
    "backgroundColor": "#F8FAFB", "minHeight": "100vh",
    "padding": "28px 36px",
    "fontFamily": "'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
}
CARD_STYLE = {
    "backgroundColor": "#FFFFFF", "padding": "18px 24px",
    "borderRadius": "12px",
    "boxShadow": "0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)",
    "marginBottom": "16px", "border": "1px solid #E4E9F0",
}
LABEL_STYLE = {
    "color": "#5A6478", "fontWeight": "700", "fontSize": "10px",
    "letterSpacing": "1px", "textTransform": "uppercase",
    "marginBottom": "7px", "display": "block",
}

C_WOOD    = "#92766A"
FADE      = "rgba(203,213,225,0.35)"
FADE_LINE = "rgba(203,213,225,0.15)"


# ── Deux palettes séparées : essentielles et optionnelles ─────────────────────
# Les optionnelles ont leur propre set de couleurs distinctes des essentielles.
# Visuellement : fill très pâle + contour en tirets (symbol tiret dans Plotly).

# Palette essentielles : couleurs saturées, bien différenciées
PALETTE_ESS = [
    {   # 0 — purple
        "n1_fill":"#EEEDFE","n1_border":"#CECBF6","n1_text":"#3C3489",
        "n2_fill":"#AFA9EC","n2_text":"#26215C",
        "n3_fill":"#534AB7","n3_text":"#EEEDFE",
        "root_fill":"#3C3489","root_text":"#EEEDFE","line":"#3C3489",
    },
    {   # 1 — teal
        "n1_fill":"#E1F5EE","n1_border":"#9FE1CB","n1_text":"#085041",
        "n2_fill":"#5DCAA5","n2_text":"#04342C",
        "n3_fill":"#0F6E56","n3_text":"#E1F5EE",
        "root_fill":"#085041","root_text":"#E1F5EE","line":"#085041",
    },
    {   # 2 — coral
        "n1_fill":"#FAECE7","n1_border":"#F5C4B3","n1_text":"#712B13",
        "n2_fill":"#F0997B","n2_text":"#4A1B0C",
        "n3_fill":"#993C1D","n3_text":"#FAECE7",
        "root_fill":"#712B13","root_text":"#FAECE7","line":"#712B13",
    },
    {   # 3 — blue
        "n1_fill":"#E6F1FB","n1_border":"#B5D4F4","n1_text":"#0C447C",
        "n2_fill":"#85B7EB","n2_text":"#042C53",
        "n3_fill":"#185FA5","n3_text":"#E6F1FB",
        "root_fill":"#0C447C","root_text":"#E6F1FB","line":"#0C447C",
    },
    {   # 4 — amber
        "n1_fill":"#FAEEDA","n1_border":"#FAC775","n1_text":"#633806",
        "n2_fill":"#EF9F27","n2_text":"#412402",
        "n3_fill":"#854F0B","n3_text":"#FAEEDA",
        "root_fill":"#633806","root_text":"#FAEEDA","line":"#633806",
    },
    {   # 5 — green
        "n1_fill":"#EAF3DE","n1_border":"#C0DD97","n1_text":"#27500A",
        "n2_fill":"#97C459","n2_text":"#173404",
        "n3_fill":"#3B6D11","n3_text":"#EAF3DE",
        "root_fill":"#27500A","root_text":"#EAF3DE","line":"#27500A",
    },
    {   # 6 — pink
        "n1_fill":"#FBEAF0","n1_border":"#F4C0D1","n1_text":"#72243E",
        "n2_fill":"#ED93B1","n2_text":"#4B1528",
        "n3_fill":"#993556","n3_text":"#FBEAF0",
        "root_fill":"#72243E","root_text":"#FBEAF0","line":"#72243E",
    },
    {   # 7 — gray
        "n1_fill":"#F1EFE8","n1_border":"#D3D1C7","n1_text":"#444441",
        "n2_fill":"#B4B2A9","n2_text":"#2C2C2A",
        "n3_fill":"#5F5E5A","n3_text":"#F1EFE8",
        "root_fill":"#444441","root_text":"#F1EFE8","line":"#444441",
    },
]

# Palette optionnelles : les tirets sont le différenciateur PRINCIPAL.
# Les couleurs sont choisies pour minimiser la confusion avec les essentielles.
# Règle : éviter la même hue qu'une essentielle dans la même formation.
# En pratique, une formation a max 3-4 essentielles + max 5 optionnelles
# → les 8 stops couvrent largement sans conflit dans un contexte réel.
PALETTE_OPT = [
    {   # 0 opt — violet (hue 270°, décalé de purple 250°)
        "fill":"rgba(0,0,0,0)","border":"#7C3AED","text":"#4C1D95","line":"#7C3AED",
    },
    {   # 1 opt — cyan foncé (hue 190°, décalé de teal 160°)
        "fill":"rgba(0,0,0,0)","border":"#0E7490","text":"#164E63","line":"#0E7490",
    },
    {   # 2 opt — orange vif (hue 25°, décalé de coral 10° et amber 42°)
        "fill":"rgba(0,0,0,0)","border":"#C2410C","text":"#7C2D12","line":"#C2410C",
    },
    {   # 3 opt — bleu roi (hue 245°, décalé de blue 220°)
        "fill":"rgba(0,0,0,0)","border":"#3730A3","text":"#1E1B4B","line":"#3730A3",
    },
    {   # 4 opt — vert sauge (hue 145°, décalé de green 110°)
        "fill":"rgba(0,0,0,0)","border":"#047857","text":"#064E3B","line":"#047857",
    },
    {   # 5 opt — magenta (hue 310°, décalé de pink 340°)
        "fill":"rgba(0,0,0,0)","border":"#A21CAF","text":"#701A75","line":"#A21CAF",
    },
    {   # 6 opt — brun (hue 30°, décalé de coral 10° et amber 42°)
        "fill":"rgba(0,0,0,0)","border":"#92400E","text":"#451A03","line":"#92400E",
    },
    {   # 7 opt — acier (hue 210°, décalé de gray 0° et blue 220°)
        "fill":"rgba(0,0,0,0)","border":"#1E40AF","text":"#1E3A5F","line":"#1E40AF",
    },
]

# Index séparés : on compte essentielles et optionnelles indépendamment
# pour éviter tout conflit de couleur entre les deux familles.

COMP_PALETTE = PALETTE_ESS   # conservé pour compat légende


def _comp_scheme(index):
    """
    Retourne le schéma couleur d'une compétence — toujours la palette
    essentielle pleine, dégradé N1→N2→N3, identique pour toutes les
    compétences (BUT comme Polytech).
    """
    cfg = PALETTE_ESS[index % len(PALETTE_ESS)]
    return {
        "n1":   (cfg["n1_fill"], cfg["n1_text"], cfg["n1_border"]),
        "n2":   (cfg["n2_fill"], cfg["n2_text"], cfg["n2_fill"]),
        "n3":   (cfg["n3_fill"], cfg["n3_text"], cfg["n3_fill"]),
        "root": (cfg["root_fill"], cfg["root_text"], cfg["root_fill"]),
        "line": cfg["line"],
    }


def _niv_key(niv):
    return {1:"n1",2:"n2",3:"n3"}.get(
        int(niv) if str(niv).isdigit() else 99, "n3")


def _sort_sem(s):
    try:
        return int(str(s).replace("S","").replace("s",""))
    except Exception:
        return 999


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

Y_COMP      = 0.0   # racine
Y_NIV       = 2.5   # nœuds niveau
Y_BAR_BASE  = 3.5   # pied des barres AC
BAR_MAX_H   = 4.0   # hauteur max d'une barre (pour max_mods_global)

BAR_W       = 0.28  # largeur d'une barre (unités Plotly)
BAR_GAP     = 0.10  # gap entre barres d'un même niveau
NIV_GAP     = 0.65  # gap entre groupes de niveaux (horizontal)
COMP_GAP    = 2.8   # gap entre arbres


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE BUT
# ══════════════════════════════════════════════════════════════════════════════

def _ue_to_comp(ue_code, parcours=None):
    m = re.search(r"UE_\d+_(\d+)", str(ue_code))
    if not m:
        return None
    n = m.group(1)
    if parcours and parcours not in ("COMMUN", "", None):
        return f"COMP_{parcours}_{n}"
    return f"COMP_{n}"


def _is_common_parcours(parcours):
    return parcours in (None, "", "COMMUN", "TRONC_COMMUN", "Tronc commun")


def _sem_to_niveau(sem):
    try:
        s = int(str(sem))
    except Exception:
        return 1
    return 1 if s <= 2 else 2 if s <= 4 else 3


def build_rows_from_curriculum(curriculum_data):
    if not curriculum_data or not _HAS_HELPERS:
        return []
    ac_reg = {}

    def _ac(cc, desc):
        k = (cc, desc[:60])
        if k not in ac_reg:
            ac_reg[k] = f"{cc}_AC{len(ac_reg)+1:03d}"
        return ac_reg[k]

    rows = []
    for rc in iter_curriculum_elements(curriculum_data):
        sem, ue, parcours, el = rc["semestre"], rc["ue"], rc["parcours"], rc["element"]
        cc = _ue_to_comp(ue.get("code", ""), parcours if parcours != "COMMUN" else None)
        if not cc:
            continue
        mc = normalize_module_code(el.get("code") or el.get("id"))
        if not mc:
            continue
        niv = _sem_to_niveau(sem)
        ue_type = ue.get("type")  # UE_COMMUNE ou UE_OPTIONNELLE
        parcours_val = parcours if parcours and parcours != "COMMUN" else None
        for aa in el.get("acquis_apprentissage", []):
            desc = (aa.get("description") or "").strip()
            if not desc:
                continue
            rows.append({
                "competence_code": cc,
                "competence_name": f"Compétence {cc.replace('COMP_', '')}",
                "ac_code": _ac(cc, desc), "ac_description": desc,
                "niveau": niv, "module_code": mc,
                "module_name": el.get("nom", ""), "semestre": sem,
                "ue_type":  ue_type,
                "parcours": parcours_val,
            })
    return rows


# ══════════════════════════════════════════════════════════════════════════════
#  NORMALISATION ROWS
# ══════════════════════════════════════════════════════════════════════════════

def build_forest_rows(rows):
    result = []
    for r in rows:
        cc  = r.get("competence_code")
        ac  = r.get("ac_code")
        mc  = r.get("module_code") or r.get("module_id")
        if not cc or not ac:
            continue
        try:
            niv = int(r.get("niveau") or 1)
        except Exception:
            niv = 1
        sem     = r.get("semestre")
        sem_lbl = f"S{sem}" if sem and not str(sem).startswith("S") else str(sem or "?")
        result.append({
            "semestre":        sem_lbl,
            "competence_code": cc,
            "competence_name": r.get("competence_name") or cc,
            "niveau":          niv,
            "ac_code":         ac,
            "ac_description":  r.get("ac_description") or "",
            "module_code":     mc,
            "module_name":     r.get("module_name") or mc or "",
            "orphan":          r.get("orphan", False),

            "ue_type":         r.get("ue_type"),
            "parcours":        r.get("parcours"),

            "sous_classification":      r.get("sous_classification"),
            "sous_classification_nom":  r.get("sous_classification_nom"),
        })
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  AGRÉGATION
# ══════════════════════════════════════════════════════════════════════════════

def build_trees(forest_rows, sem_filter="ALL", comp_filter="ALL"):
    """
    trees[cc] = {
      "name": str,
      "levels": { niv: { "acs": { ac: {"desc","mods","names"} } } }
    }
    """
    trees = {}
    for r in forest_rows:
        sem = r.get("semestre", "?")
        if sem_filter not in (None, "ALL") and sem != sem_filter:
            continue
        if comp_filter not in (None, "ALL") and r.get("competence_code") != comp_filter:
            continue

        cc  = r["competence_code"]
        ac  = r["ac_code"]
        mc  = r.get("module_code")
        niv = r["niveau"]

        if cc not in trees:
            trees[cc] = {
                "name":   r.get("competence_name", ""),
                "levels": {},
            }

        lvl = trees[cc]["levels"].setdefault(niv, {"acs": {}})
        acd = lvl["acs"].setdefault(ac, {
            "desc":  r.get("ac_description", ""),
            "mods":  set(),
            "names": {},
        })
        if mc:
            acd["mods"].add(mc)
            acd["names"][mc] = r.get("module_name", "") or mc

    return trees


def _max_mods(trees):
    return max(
        (len(a["mods"])
         for t in trees.values()
         for lvl in t["levels"].values()
         for a in lvl["acs"].values()),
        default=1,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT GÉOMÉTRIQUE
# ══════════════════════════════════════════════════════════════════════════════

def _level_group_width(acs):
    n = len(acs)
    return n * BAR_W + max(0, n - 1) * BAR_GAP


def _tree_width(tree):
    n_niv  = len(tree["levels"])
    max_gw = max((_level_group_width(lvl["acs"]) for lvl in tree["levels"].values()), default=BAR_W)
    return n_niv * max_gw + max(0, n_niv - 1) * NIV_GAP


def compute_layout(trees, max_mods_g):
    """
    Retourne :
      pos_comp  {cc: cx}
      pos_niv   {(cc, niv): (x, y)}
      pos_bar   {(cc, niv, ac): (x, y_base, y_top)}
      meta_ac   {(cc, niv, ac): {desc, mods, names}}
    """
    comp_list = sorted(trees.keys())
    widths    = {cc: _tree_width(trees[cc]) for cc in comp_list}
    total     = sum(widths.values()) + max(0, len(comp_list)-1) * COMP_GAP

    cursor    = -total / 2
    pos_comp  = {}
    pos_niv   = {}
    pos_bar   = {}
    meta_ac   = {}

    for cc in comp_list:
        tree = trees[cc]
        tw   = widths[cc]
        cx   = cursor + tw / 2
        pos_comp[cc] = cx

        niv_list = sorted(tree["levels"].keys())
        n_niv    = len(niv_list)

        # Largeurs de chaque groupe de niveau
        gws = [_level_group_width(tree["levels"][nv]["acs"]) for nv in niv_list]
        total_gw = sum(gws) + max(0, n_niv-1) * NIV_GAP

        gx_start = cx - total_gw / 2

        for i, niv in enumerate(niv_list):
            gw  = gws[i]
            gcx = gx_start + gw / 2      # centre du groupe de niveaux
            pos_niv[(cc, niv)] = (gcx, Y_NIV)

            acs     = tree["levels"][niv]["acs"]
            n_ac    = len(acs)
            bar_total = n_ac * BAR_W + max(0, n_ac-1) * BAR_GAP
            bar_start = gcx - bar_total / 2

            for j, (ac, acd) in enumerate(sorted(acs.items())):
                bx    = bar_start + j * (BAR_W + BAR_GAP) + BAR_W / 2
                n_mod = len(acd["mods"])
                h     = (n_mod / max_mods_g) * BAR_MAX_H
                pos_bar[(cc, niv, ac)] = (bx, Y_BAR_BASE, Y_BAR_BASE + h)
                meta_ac[(cc, niv, ac)] = acd

            gx_start += gw + NIV_GAP

        cursor += tw + COMP_GAP

    return pos_comp, pos_niv, pos_bar, meta_ac


# ══════════════════════════════════════════════════════════════════════════════
#  FOCUS
# ══════════════════════════════════════════════════════════════════════════════

def _parse_sel(sel):
    if not sel or not isinstance(sel, dict):
        return None, None
    return sel.get("type"), sel.get("id")


def _active_set(sel, trees):
    """
    Retourne un set de clés actives : {"COMP::cc", "NIV::cc::niv", "BAR::cc::niv::ac"}
    None = tout actif.
    """
    kind, sid = _parse_sel(sel)
    if not kind:
        return None

    active = set()

    if kind == "comp":
        cc = sid
        if cc in trees:
            active.add(f"COMP::{cc}")
            for niv, lvl in trees[cc]["levels"].items():
                active.add(f"NIV::{cc}::{niv}")
                for ac in lvl["acs"]:
                    active.add(f"BAR::{cc}::{niv}::{ac}")

    elif kind == "niv":
        cc, niv_s = sid.split("::", 1)
        try:
            niv = int(niv_s)
        except Exception:
            return None
        active.add(f"COMP::{cc}")
        active.add(f"NIV::{cc}::{niv}")
        if cc in trees and niv in trees[cc]["levels"]:
            for ac in trees[cc]["levels"][niv]["acs"]:
                active.add(f"BAR::{cc}::{niv}::{ac}")

    elif kind == "bar":
        cc, niv_s, ac = sid.split("::", 2)
        try:
            niv = int(niv_s)
        except Exception:
            return None
        active.add(f"COMP::{cc}")
        active.add(f"NIV::{cc}::{niv}")
        active.add(f"BAR::{cc}::{niv}::{ac}")

    return active if active else None


# ══════════════════════════════════════════════════════════════════════════════
#  FIGURE
# ══════════════════════════════════════════════════════════════════════════════

def create_forest_figure(forest_rows, sem_filter="ALL", comp_filter="ALL",
                         selected=None):
    if not forest_rows:
        return empty_figure("Aucune donnée ForestED disponible")

    trees = build_trees(forest_rows, sem_filter, comp_filter)
    if not trees:
        return empty_figure("Aucune donnée disponible pour ce filtre")

    mg     = _max_mods(trees)
    pos_comp, pos_niv, pos_bar, meta_ac = compute_layout(trees, mg)

    active = _active_set(selected, trees)
    has_focus = active is not None

    def _on(key):
        return (not has_focus) or (key in active)

    fig = go.Figure()
    shapes = []  # alimenté pendant les traces, appliqué en fin de fonction

    # Une seule palette, toutes les compétences traitées de façon identique
    comp_order = sorted(trees.keys())
    comp_schemes = {cc: _comp_scheme(i) for i, cc in enumerate(comp_order)}

    def _scheme(cc):
        return comp_schemes[cc]

    # ── 1. TRONCS (racine → nœuds niveau, couleur par compétence) ────────────
    lx_off, ly_off = [], []
    # Un batch par compétence pour conserver la couleur
    for cc, cx in pos_comp.items():
        sch = _scheme(cc)
        line_col = sch["line"] if _on(f"COMP::{cc}") else FADE_LINE
        lw = 3.0 if _on(f"COMP::{cc}") else 0.7
        lx, ly = [], []
        for (cc2, niv), (nx, ny) in pos_niv.items():
            if cc2 != cc: continue
            lx.extend([cx, nx, None])
            ly.extend([Y_COMP + 0.25, Y_NIV - 0.25, None])
        if lx:
            fig.add_trace(go.Scatter(x=lx, y=ly, mode="lines",
                line=dict(color=line_col, width=lw), opacity=0.55,
                hoverinfo="none", showlegend=False))

    # ── 2. TIGES niveau → barres (couleur par compétence × niveau) ───────────
    for cc in comp_order:
        sch = _scheme(cc)
        for niv_ref in (1, 2, 3):
            nk = _niv_key(niv_ref)
            _, _, tige_col = sch[nk]
            tx, ty = [], []
            for (cc2, niv), (nx, _) in pos_niv.items():
                if cc2 != cc or niv != niv_ref: continue
                for (cc3, nv3, ac), (bx, yb, yt) in pos_bar.items():
                    if cc3 != cc or nv3 != niv_ref: continue
                    if not _on(f"BAR::{cc}::{niv_ref}::{ac}"): continue
                    tx.extend([nx, bx, None])
                    ty.extend([Y_NIV + 0.22, yb, None])
            if tx:
                fig.add_trace(go.Scatter(x=tx, y=ty, mode="lines",
                    line=dict(color=tige_col if _on(f"NIV::{cc}::{niv_ref}") else FADE_LINE,
                              width=1.1), opacity=0.45,
                    hoverinfo="none", showlegend=False))

    # ── 3. BARRES AC (couleur par compétence × niveau) ────────────────────────
    for cc in comp_order:
        sch = _scheme(cc)
        for niv_ref in (1, 2, 3):
            nk = _niv_key(niv_ref)
            bar_fill, bar_text, bar_border = sch[nk]
            niv_labels = {1: "Débutant", 2: "Intermédiaire", 3: "Avancé"}
            bx_on, by_on, bh_on, hov_on, cd_on = [], [], [], [], []
            bx_off, by_off, bh_off, hov_off, cd_off = [], [], [], [], []

            for (cc2, niv, ac), (bx, yb, yt) in pos_bar.items():
                if cc2 != cc or niv != niv_ref: continue
                acd   = meta_ac[(cc, niv, ac)]
                n_mod = len(acd["mods"])
                h     = yt - yb
                on    = _on(f"BAR::{cc}::{niv}::{ac}")
                hover = (f"<b>{ac}</b><br>N{niv} — {niv_labels[niv_ref]}<br>"
                         f"Compétence : {cc}<br>{n_mod} module(s)<br><br>"
                         f"<i>{acd['desc'][:100]}{'…' if len(acd['desc'])>100 else ''}</i><br>"
                         f"🖱 Cliquez pour les modules")
                cd = ["bar", f"{cc}::{niv}::{ac}"]
                if on:
                    bx_on.append(bx); by_on.append(yb); bh_on.append(h)
                    hov_on.append(hover); cd_on.append(cd)
                else:
                    bx_off.append(bx); by_off.append(yb); bh_off.append(h)
                    hov_off.append(hover); cd_off.append(cd)

            if bx_on:
                bar_marker = dict(
                    color=bar_fill, opacity=0.90,
                    line=dict(width=0.8, color=bar_border),
                )
                fig.add_trace(go.Bar(
                    x=bx_on, y=bh_on, base=by_on,
                    width=[BAR_W * 0.9] * len(bx_on),
                    marker=bar_marker,
                    text=[""] * len(bx_on),
                    hovertext=hov_on, hoverinfo="text",
                    hoverlabel=dict(bgcolor=bar_border, bordercolor="white",
                                    font=dict(color=bar_text, size=12)),
                    customdata=cd_on,
                    name=f"{cc} N{niv_ref}", showlegend=False,
                ))
            if bx_off:
                fig.add_trace(go.Bar(
                    x=bx_off, y=bh_off, base=by_off,
                    width=[BAR_W * 0.9] * len(bx_off),
                    marker=dict(color=FADE, opacity=0.20, line=dict(width=0)),
                    text=[""] * len(bx_off),
                    hovertext=hov_off, hoverinfo="text",
                    customdata=cd_off, showlegend=False,
                ))

    # ── 4. COMPTEUR barres ────────────────────────────────────────────────────
    tx_cnt, ty_cnt, ttxt, tcol = [], [], [], []
    for (cc, niv, ac), (bx, yb, yt) in pos_bar.items():
        acd = meta_ac[(cc, niv, ac)]
        n   = len(acd["mods"])
        on  = _on(f"BAR::{cc}::{niv}::{ac}")
        sch = _scheme(cc)
        nk  = _niv_key(niv)
        _, txt_col, _ = sch[nk]
        tx_cnt.append(bx); ty_cnt.append(yt + 0.15); ttxt.append(str(n))
        tcol.append(txt_col if on else "rgba(148,163,184,0.45)")
    if tx_cnt:
        fig.add_trace(go.Scatter(x=tx_cnt, y=ty_cnt, mode="text", text=ttxt,
            textfont=dict(size=9, color=tcol),
            hoverinfo="none", showlegend=False))

    # ── 5. NŒUDS NIVEAU (carrés, couleur par compétence) ─────────────────────
    for cc in comp_order:
        sch = _scheme(cc)
        niv_labels = {1: "Débutant", 2: "Intermédiaire", 3: "Avancé"}
        for niv_ref in (1, 2, 3):
            nk = _niv_key(niv_ref)
            fill, txt, bdr = sch[nk]
            nx_, ny_, nhov, ncd, ncol, nsz, nbdr = [], [], [], [], [], [], []
            for (cc2, niv), (nx, ny) in pos_niv.items():
                if cc2 != cc or niv != niv_ref: continue
                on = _on(f"NIV::{cc}::{niv}")
                lvl   = trees[cc]["levels"].get(niv, {"acs": {}})
                n_ac  = len(lvl["acs"])
                n_mod = sum(len(a["mods"]) for a in lvl["acs"].values())
                nx_.append(nx); ny_.append(ny)
                nhov.append(f"<b>N{niv_ref} — {niv_labels[niv_ref]}</b><br>"
                            f"Compétence : {cc}<br>{n_ac} AC · {n_mod} module(s)")
                ncd.append(["niv", f"{cc}::{niv}"])
                ncol.append(fill if on else FADE)
                nbdr.append(bdr if on else FADE)
                nsz.append(16 if on else 9)
            if not nx_: continue
            fig.add_trace(go.Scatter(
                x=nx_, y=ny_, mode="markers+text",
                marker=dict(symbol="square", size=nsz, color=ncol,
                            line=dict(width=1.2, color=nbdr)),
                text=[f"N{niv_ref}"] * len(nx_),
                textposition="middle center",
                textfont=dict(size=9, color=[txt if on else "#94A3B8"
                                             for on in [_on(f"NIV::{cc}::{niv_ref}")]
                                             for _ in nx_]),
                hovertext=nhov, hoverinfo="text",
                hoverlabel=dict(bgcolor=bdr, bordercolor="white",
                                font=dict(size=12)),
                customdata=ncd, showlegend=False,
            ))

    # ── 6. RACINES COMPÉTENCES (losanges colorés) ─────────────────────────────
    for cc, cx in pos_comp.items():
        sch  = _scheme(cc)
        on   = _on(f"COMP::{cc}")
        tree = trees[cc]
        root_fill, root_txt, root_bdr = sch["root"]
        n_ac = sum(len(l["acs"]) for l in tree["levels"].values())
        n_m  = len({m for l in tree["levels"].values()
                    for a in l["acs"].values() for m in a["mods"]})
        col   = root_fill if on else FADE
        bdr_c = root_bdr  if on else FADE
        sz    = 20 if on else 11
        fig.add_trace(go.Scatter(
            x=[cx], y=[Y_COMP], mode="markers+text",
            marker=dict(symbol="diamond", size=sz, color=col,
                        line=dict(width=2.5, color=bdr_c)),
            text=[f"<b>{cc}</b>" if on else ""],
            textposition="bottom center",
            textfont=dict(size=10, color=root_bdr),
            hovertext=[f"<b>{cc}</b><br><i>{tree['name']}</i><br>"
                       f"{n_ac} AC · {n_m} modules"],
            hoverinfo="text",
            hoverlabel=dict(bgcolor=root_bdr, bordercolor="white",
                            font=dict(color=root_txt, size=12)),
            customdata=[["comp", cc]], showlegend=False,
        ))

    # ── 7. LABELS DE COUCHE (gauche) ─────────────────────────────────────────
    all_x = [cx for cx in pos_comp.values()]
    xmin  = min(all_x) - 4.0
    xmax  = max(all_x) + 4.0
    bar_mid = Y_BAR_BASE + BAR_MAX_H / 2

    for y_val, lbl, col in [
        (bar_mid, "AC (barres)", "#475569"),
        (Y_NIV,   "Niveaux",     "#475569"),
        (Y_COMP,  "Compétences", "#475569"),
    ]:
        fig.add_trace(go.Scatter(
            x=[xmin - 0.5], y=[y_val], mode="text",
            text=[f"<b>{lbl}</b>"],
            textfont=dict(size=11, color=col),
            textposition="middle right",
            hoverinfo="none", showlegend=False,
        ))

    # ── SHAPES : fonds discrets ───────────────────────────────────────────────
    shapes += [
        dict(type="rect", x0=xmin, x1=xmax,
             y0=Y_BAR_BASE - 0.1, y1=Y_BAR_BASE + BAR_MAX_H + 0.4,
             fillcolor="rgba(107,114,128,0.04)", line=dict(width=0), layer="below"),
        dict(type="rect", x0=xmin, x1=xmax,
             y0=Y_NIV - 0.4, y1=Y_NIV + 0.4,
             fillcolor="rgba(107,114,128,0.04)", line=dict(width=0), layer="below"),
        dict(type="line", x0=xmin, x1=xmax,
             y0=Y_BAR_BASE, y1=Y_BAR_BASE,
             line=dict(color="rgba(148,163,184,0.30)", width=0.8), layer="below"),
    ]

    # ── TITRE & LAYOUT ────────────────────────────────────────────────────────
    kind, sid = _parse_sel(selected)
    focus_lbl = ""
    if kind == "comp":
        focus_lbl = f" · <b>{sid}</b>"
    elif kind == "niv":
        cc, nv = sid.split("::", 1)
        focus_lbl = f" · <b>{cc} N{nv}</b>"
    elif kind == "bar":
        cc, nv, ac = sid.split("::", 2)
        focus_lbl = f" · <b>{ac}</b>"

    n_comp  = len(trees)
    n_ac    = sum(len(l["acs"]) for t in trees.values() for l in t["levels"].values())
    n_mods  = len({m for t in trees.values() for l in t["levels"].values()
                   for a in l["acs"].values() for m in a["mods"]})

    fig.update_layout(
        title=dict(
            text=(f"<b>ForestED — Forêt pédagogique APC</b>"
                  f"<span style='color:#94A3B8;font-size:13px'>"
                  f" · {n_comp} compétences · {n_ac} AC · {n_mods} modules"
                  f"{focus_lbl}</span>"),
            x=0.01, y=0.98, font=dict(size=16, color="#0F172A")),
        height=720,
        paper_bgcolor="#F8FAFB", plot_bgcolor="#FFFFFF",
        barmode="overlay",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    xanchor="right", x=1, bgcolor="rgba(255,255,255,0.94)",
                    bordercolor="#E4E9F0", borderwidth=1,
                    font=dict(size=12, color="#374151")),
        margin=dict(l=120, r=50, t=75, b=30),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=[xmin - 1.5, xmax + 0.5]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=[Y_COMP - 0.9, Y_BAR_BASE + BAR_MAX_H + 0.8]),
        shapes=shapes, clickmode="event", hovermode="closest",
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  PANNEAU DE DÉTAIL
# ══════════════════════════════════════════════════════════════════════════════

def build_focus_panel(forest_rows, selected, trees, sem_filter="ALL"):
    kind, sid = _parse_sel(selected)
    if not kind:
        return html.Div()

    # Filtrer les rows par semestre actif (les orphelins passent toujours)
    def _sem_ok(r):
        if sem_filter in (None, "ALL"):
            return True
        # Filtre strict : même les orphelins ont maintenant un semestre déduit
        return r.get("semestre") == sem_filter

    # Trouver l'index de la compétence pour la palette dynamique
    def _comp_border(cc, niv=None):
        """Retourne la couleur de bordure du panneau selon la compétence et le niveau."""
        all_comps = sorted({r.get("competence_code") for r in forest_rows
                            if r.get("competence_code")})
        idx = all_comps.index(cc) if cc in all_comps else 0
        sch = _comp_scheme(idx)
        if niv is None:
            return sch["root"][2]   # border root (plus visible que fill)
        return sch[_niv_key(niv)][2]

    if kind == "comp":
        cc      = sid
        related = [r for r in forest_rows if r.get("competence_code") == cc and _sem_ok(r)]
        border  = _comp_border(cc)
        title   = f"Compétence : {cc}"
        name    = (related[0].get("competence_name","") if related else "")
        comps_  = [cc]
        acs_    = sorted({r["ac_code"] for r in related})
        mods_   = sorted({r["module_code"] for r in related if r.get("module_code")})

    elif kind == "niv":
        cc, nv_s = sid.split("::", 1)
        try:
            niv = int(nv_s)
        except Exception:
            return html.Div()
        niv_labels = {1: "Débutant", 2: "Intermédiaire", 3: "Avancé"}
        related = [r for r in forest_rows
                   if r.get("competence_code") == cc
                   and r.get("niveau") == niv
                   and _sem_ok(r)]
        border  = _comp_border(cc, niv)
        title   = f"Niveau {niv} — {niv_labels.get(niv, str(niv))}"
        name    = cc
        comps_  = [cc]
        acs_    = sorted({r["ac_code"] for r in related})
        mods_   = sorted({r["module_code"] for r in related if r.get("module_code")})

    elif kind == "bar":
        cc, nv_s, ac = sid.split("::", 2)
        try:
            niv = int(nv_s)
        except Exception:
            return html.Div()
        related = [r for r in forest_rows if r.get("ac_code") == ac and _sem_ok(r)]
        border  = _comp_border(cc, niv)
        title   = f"AC : {ac}"
        name    = next((r.get("ac_description","") for r in related), "")
        comps_  = sorted({r["competence_code"] for r in related})
        acs_    = [ac]
        mods_   = sorted({r["module_code"] for r in related if r.get("module_code")})

    else:
        return html.Div()

    def _tags(items, bg, color):
        return html.Div([
            html.Span(it, style={
                "backgroundColor": bg, "color": color, "borderRadius": "5px",
                "padding": "3px 8px", "fontSize": "11px",
                "marginRight": "5px", "marginBottom": "5px",
                "display": "inline-block",
            }) for it in items[:80]
        ], style={"display": "flex", "flexWrap": "wrap"})

    def _section(lbl, items, bg, col):
        if not items:
            return html.Div()
        return html.Div([
            html.P(f"{lbl} ({len(items)})",
                   style={"fontWeight": "700", "fontSize": "12px",
                          "color": col, "margin": "8px 0 5px"}),
            _tags(items, bg, col),
        ])

    body = []
    if name and name != title:
        body.append(html.P(name, style={"fontSize": "13px", "color": "#475569",
                                         "fontStyle": "italic", "margin": "0 0 10px"}))
    body.append(html.P(
        f"{len(comps_)} compétence(s) · {len(acs_)} AC · {len(mods_)} module(s)",
        style={"fontSize": "12px", "color": "#64748B", "margin": "0 0 10px"}))
    body.append(_section("Compétences", comps_, "#DBEAFE", "#1E40AF"))
    body.append(_section("AC", acs_, "#EDE9FE", "#6D28D9"))
    body.append(_section("Modules", mods_, "#D1FAE5", "#065F46"))
    body.append(html.P("Cliquez le même élément ou ✕ Réinitialiser pour effacer.",
                       style={"fontSize": "11px", "color": "#94A3B8",
                              "margin": "10px 0 0", "fontStyle": "italic"}))

    return html.Div([html.Div([
        html.Div([
            html.Span(style={"width": "10px", "height": "10px", "borderRadius": "2px",
                              "backgroundColor": border, "display": "inline-block",
                              "marginRight": "8px"}),
            html.Span(title, style={"fontWeight": "700", "fontSize": "14px",
                                     "color": "#0F172A"}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),
        *body,
    ], style={"backgroundColor": "#FFFFFF", "border": "1px solid #E2E8F0",
               "borderLeft": f"4px solid {border}", "borderRadius": "8px",
               "padding": "14px 18px", "marginBottom": "14px",
               "boxShadow": "0 2px 8px rgba(0,0,0,0.05)"})])


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIONS FILTRES
# ══════════════════════════════════════════════════════════════════════════════

def build_semester_options(forest_rows):
    # Exclure "?" : les orphelins (sem=None → "?") ne doivent pas apparaître
    # comme semestre sélectionnable — ils sont toujours inclus dans tous les filtres.
    sems = sorted(
        {r["semestre"] for r in forest_rows
         if r.get("semestre") and r["semestre"] != "?"},
        key=_sort_sem,
    )
    return [{"label": "Tous les semestres", "value": "ALL"}] + \
           [{"label": s, "value": s} for s in sems]


def build_competence_options(forest_rows, sem="ALL"):
    # Les orphelins (sem="?") sont inclus dans tous les filtres semestre :
    # on les inclut dans les options compétences même avec un filtre spécifique.
    if sem in (None, "ALL"):
        rows = forest_rows
    else:
        rows = [r for r in forest_rows if r.get("semestre") == sem]
    comps = {}
    for r in rows:
        c = r.get("competence_code")
        if c: comps[c] = r.get("competence_name") or c
    return [{"label": "Toutes les compétences", "value": "ALL"}] + \
           [{"label": f"{c} — {n}", "value": c} for c, n in sorted(comps.items())]



def normalize_text(value):
    """
    Normalisation robuste pour comparer les codes.
    Exemple :
    BUT_MP, but-mp, But MP => BUT MP
    """
    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .upper()
        .replace("_", " ")
        .replace("-", " ")
    )


def compact_code(value):
    """
    Version compacte pour comparer les codes.
    Exemple :
    BUT_MP => BUTMP
    BUT MP => BUTMP
    """
    return normalize_text(value).replace(" ", "")


def clean_parcours_label(value):
    """
    Nettoyage visuel du label affiché dans le dropdown.
    Exemple :
    BUT_MP => MP
    BUT_PCLG => PCLG
    """
    if not value:
        return ""

    text = str(value).strip()

    for prefix in ("BUT_", "BUT-", "BUT "):
        if text.upper().startswith(prefix):
            return text[len(prefix):]

    return text


def is_common_sous_classification(code, label):
    """
    Détecte le tronc commun sans hardcoder COMP_1, COMP_2, COMP_3.
    On se base sur les métadonnées du référentiel.
    """
    text = normalize_text(f"{code or ''} {label or ''}")

    return (
        "TRONC COMMUN" in text
        or "COMMUN" in text
        or text.strip() == "TC"
        or text.endswith(" TC")
        or " TC " in f" {text} "
    )


def is_essential_competence_code(competence_code):
    """
    Détecte une compétence essentielle/générique par convention de nommage.

    Exemples :
    COMP_1      => essentielle
    COMP_2      => essentielle
    COMP_MP_1   => parcours MP
    COMP_PCLG_1 => parcours PCLG

    Ce n'est pas du hardcoding métier : on ne liste pas COMP_1, COMP_2, COMP_3.
    On détecte seulement la forme générique COMP_<nombre>.
    """
    if not competence_code:
        return False

    return re.match(r"^COMP_\d+$", str(competence_code).strip().upper()) is not None


def extract_parcours_from_competence_code(competence_code):
    """
    Extrait le parcours depuis un code compétence optionnel.

    Exemples :
    COMP_MP_1   => MP
    COMP_PCLG_1 => PCLG
    COMP_ATN_1  => ATN
    COMP_1      => None
    """
    if not competence_code:
        return None

    match = re.match(
        r"^COMP_([A-Z][A-Z0-9]*)_\d+$",
        str(competence_code).strip().upper()
    )

    if not match:
        return None

    return match.group(1)


def row_matches_selected_parcours(row, selected_parcours):
    """
    Vérifie si une ligne appartient au parcours sélectionné.

    Compatible avec :
    - selected = MP
    - selected = BUT_MP
    - sous_classification = BUT_MP
    - competence_code = COMP_MP_1
    """
    if not selected_parcours or selected_parcours == "ALL":
        return True

    selected_norm = compact_code(selected_parcours)
    selected_short = selected_norm.replace("BUT", "", 1) if selected_norm.startswith("BUT") else selected_norm

    sous_code = compact_code(row.get("sous_classification"))
    parcours = compact_code(row.get("parcours"))

    values = {
        sous_code,
        parcours,
    }

    # Ajouter versions sans préfixe BUT
    values |= {
        v.replace("BUT", "", 1)
        for v in values
        if v.startswith("BUT")
    }

    comp_parcours = extract_parcours_from_competence_code(
        row.get("competence_code")
    )

    if comp_parcours:
        values.add(compact_code(comp_parcours))

    return selected_norm in values or selected_short in values

def get_competence_family(competence_code):
    """
    Analyse un code compétence.

    Retourne :
    - ("essential", None) pour COMP_1, COMP_2, COMP_3...
    - ("parcours", "MP") pour COMP_MP_1
    - ("parcours", "MPBS") pour COMP_MPBS_1
    - ("unknown", None) sinon

    Cette logique est générique :
    on ne hardcode pas COMP_1, COMP_2, COMP_3.
    On utilise uniquement la convention de nommage.
    """

    if not competence_code:
        return "unknown", None

    code = str(competence_code).strip().upper()

    # Compétence essentielle : COMP_1, COMP_2, COMP_3...
    if re.match(r"^COMP_\d+$", code):
        return "essential", None

    # Compétence de parcours : COMP_MP_1, COMP_MPBS_1, COMP_PCLG_1...
    match = re.match(r"^COMP_([A-Z][A-Z0-9]*)_\d+$", code)

    if match:
        return "parcours", match.group(1)

    return "unknown", None


def normalize_selected_parcours(selected_parcours):
    """
    Normalise la valeur sélectionnée dans le dropdown.

    Exemples :
    - MP      => MP
    - BUT_MP  => MP
    - but-mpbs => MPBS
    """

    if not selected_parcours or selected_parcours == "ALL":
        return "ALL"

    value = str(selected_parcours).strip().upper()
    value = value.replace("-", "_").replace(" ", "_")

    if value.startswith("BUT_"):
        value = value.replace("BUT_", "", 1)

    return value


def get_allowed_competence_codes_for_parcours(forest_rows, selected_parcours):
    """
    Détermine les compétences à afficher.

    Règle métier :
    - Tous les parcours : toutes les compétences.
    - Parcours sélectionné : compétences essentielles + compétences du parcours.

    Exemple :
    selected_parcours = MP
    => COMP_1, COMP_2, COMP_3, COMP_MP_1
    """

    if not forest_rows:
        return set()

    selected = normalize_selected_parcours(selected_parcours)

    all_competences = {
        row.get("competence_code")
        for row in forest_rows
        if row.get("competence_code")
    }

    if selected == "ALL":
        return all_competences

    allowed = set()

    for competence_code in all_competences:
        family, parcours = get_competence_family(competence_code)

        if family == "essential":
            allowed.add(competence_code)

        elif family == "parcours" and parcours == selected:
            allowed.add(competence_code)

    return allowed


def filter_forest_rows_by_parcours(forest_rows, selected_parcours):
    """
    Filtre ForestED au niveau compétence.

    Important :
    On ne filtre pas ligne par ligne selon module/parcours/UE.
    On choisit d'abord les compétences visibles,
    puis on garde toutes les lignes AC/modules liées à ces compétences.
    """

    if not forest_rows:
        return []

    allowed_competences = get_allowed_competence_codes_for_parcours(
        forest_rows,
        selected_parcours
    )

    return [
        row
        for row in forest_rows
        if row.get("competence_code") in allowed_competences
    ]


def build_parcours_options(forest_rows, sem="ALL"):
    """
    Construit le dropdown parcours à partir des codes compétences.

    Exemple :
    COMP_MP_1   => MP
    COMP_MPBS_1 => MPBS
    COMP_PCLG_1 => PCLG

    Les compétences essentielles COMP_1, COMP_2, COMP_3
    ne deviennent pas des options, elles sont ajoutées automatiquement.
    """

    if not forest_rows:
        return [{"label": "Tous les parcours", "value": "ALL"}]

    if sem not in (None, "ALL"):
        rows = [
            row for row in forest_rows
            if row.get("semestre") == sem
        ]
    else:
        rows = forest_rows

    parcours_values = set()

    for row in rows:
        competence_code = row.get("competence_code")
        family, parcours = get_competence_family(competence_code)

        if family == "parcours" and parcours:
            parcours_values.add(parcours)

    options = [{"label": "Tous les parcours", "value": "ALL"}]

    for parcours in sorted(parcours_values):
        options.append({
            "label": parcours,
            "value": parcours
        })

    return options

# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT DASH
# ══════════════════════════════════════════════════════════════════════════════

def _get_programme_options():
    summary = build_programmes_summary(load_processed_files())
    # Trier : Polytech en premier, BUT ensuite, reste par ordre alpha
    def _sort_key(item):
        src = item["source"].lower()
        if src == "polytech": return 0
        if src == "but":      return 1
        return 2
    return [
        {"label": f"{i['source']} — {i['programme']}",
         "value": f"{i['source']}::{i['programme']}"}
        for i in sorted(summary, key=_sort_key)
    ]

programme_options = _get_programme_options()
default_programme = programme_options[0]["value"] if programme_options else None

forested_forest_layout = html.Div([

    html.Div([
        html.Div([
            html.Span("🌳", style={"fontSize": "36px", "marginRight": "12px", "lineHeight": "1"}),
            html.Div([
                html.H1("ForestED", style={"color": "#0F172A", "fontSize": "28px",
                                            "fontWeight": "700", "margin": "0 0 3px",
                                            "letterSpacing": "-0.3px"}),
                html.P("Forêt pédagogique APC — racine (bas) → niveaux → barres AC → modules. "
                       "Hauteur d'une barre = nombre de modules liés. "
                       "Cliquez une barre pour voir ses modules.",
                       style={"color": "#64748B", "fontSize": "13px", "margin": "0"}),
            ]),
        ], style={"display": "flex", "alignItems": "center"}),
    ], style={"marginBottom": "18px"}),

    html.Div([
        html.Div([
            html.Label("Formation", style=LABEL_STYLE),
            dcc.Dropdown(id="forested-programme-selector", options=programme_options,
                         value=None, clearable=False, style={"fontSize": "14px"}),
        ], style={"width": "28%", "minWidth": "220px"}),

        html.Div([
            html.Label("Semestre", style=LABEL_STYLE),
            dcc.Dropdown(id="forested-semester-selector",
                         options=[{"label": "Tous les semestres", "value": "ALL"}],
                         value="ALL", clearable=False, style={"fontSize": "14px"}),
        ], style={"width": "14%", "minWidth": "150px"}),
        html.Div([
        html.Label("Parcours", style=LABEL_STYLE),
        dcc.Dropdown(
            id="forested-parcours-selector",
            options=[{"label": "Tous les parcours", "value": "ALL"}],
            value="ALL",
            clearable=False,
            style={"fontSize": "14px"}
        ),
        ], style={"width": "16%", "minWidth": "170px"}),

        html.Div([
            html.Label("Compétence", style=LABEL_STYLE),
            dcc.Dropdown(id="forested-competence-selector",
                         options=[{"label": "Toutes les compétences", "value": "ALL"}],
                         value="ALL", clearable=False, style={"fontSize": "14px"}),
        ], style={"width": "22%", "minWidth": "200px"}),

        html.Div([
            html.Label("\u00a0", style={**LABEL_STYLE, "visibility": "hidden"}),
            html.Button("✕ Réinitialiser", id="forested-reset-btn", n_clicks=0,
                style={"height": "38px", "padding": "0 16px", "borderRadius": "8px",
                       "border": "1px solid #CBD5E1", "backgroundColor": "#F8FAFC",
                       "color": "#0F172A", "fontWeight": "700", "cursor": "pointer"}),
        ], style={"display": "flex", "flexDirection": "column"}),

    ], style={**CARD_STYLE, "display": "flex", "alignItems": "flex-end",
               "flexWrap": "wrap", "gap": "14px"}),

    html.Div([
        html.Div(id="forested-legend-div", style={"display": "flex", "alignItems": "center",
                                                   "flexWrap": "wrap", "gap": "12px"}),
    ], style={**CARD_STYLE, "display": "flex", "alignItems": "center",
               "flexWrap": "wrap", "gap": "12px"}),

    dcc.Store(id="forested-rows-store"),
    dcc.Store(id="forested-sel-store"),
    html.Div(id="forested-focus-panel"),

    html.Div([
        dcc.Graph(id="forested-forest-graph",
            config={"displayModeBar": True, "displaylogo": False, "scrollZoom": True,
                    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"]}),
    ], style=CARD_STYLE),

], style=PAGE_STYLE)


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def register_callbacks(app):

    @app.callback(
        Output("forested-programme-selector", "value"),
        Input("forested-programme-selector", "options"),
        State("forested-programme-selector", "value"),
        prevent_initial_call=False,
    )
    def init_programme_selector(options, current_value):
        """Initialise le dropdown au premier programme dispo si aucune valeur."""
        if current_value is not None:
            return current_value
        if options:
            return options[0]["value"]
        return None

    @app.callback(
        Output("forested-rows-store", "data"),
        Input("forested-programme-selector", "value"),
    )
    def store_rows(prog):
        comp_data, curr_data = get_selected_data(prog)
        rows = build_visualisation_rows(comp_data, curr_data)
        if not rows and curr_data:
            rows = build_rows_from_curriculum(curr_data)
        return build_forest_rows(rows)

    @app.callback(
        Output("forested-semester-selector", "options"),
        Output("forested-semester-selector", "value"),
        Input("forested-rows-store", "data"),
    )
    def update_sem(rows):
        if not rows:
            return [{"label": "Tous les semestres", "value": "ALL"}], "ALL"
        return build_semester_options(rows), "ALL"

    @app.callback(
        Output("forested-parcours-selector", "options"),
        Output("forested-parcours-selector", "value"),
        Input("forested-rows-store", "data"),
        Input("forested-semester-selector", "value"),
    )
    def update_parcours(rows, sem):
        """
        Met à jour la liste des parcours disponibles selon la formation
        et éventuellement le semestre sélectionné.
        """
        if not rows:
            return [{"label": "Tous les parcours", "value": "ALL"}], "ALL"

        return build_parcours_options(rows, sem), "ALL"
    
    @app.callback(
    Output("forested-competence-selector", "options"),
    Output("forested-competence-selector", "value"),
    Input("forested-rows-store", "data"),
    Input("forested-semester-selector", "value"),
    Input("forested-parcours-selector", "value"),
    )
    def update_comp(rows, sem, parcours):
        """
        Met à jour les compétences après application du filtre parcours.

        Exemple :
        parcours = MP
        => options compétences = compétences communes + compétences MP.
        """
        if not rows:
            return [{"label": "Toutes les compétences", "value": "ALL"}], "ALL"

        filtered_rows = filter_forest_rows_by_parcours(rows, parcours)

        return build_competence_options(filtered_rows, sem), "ALL"

    @app.callback(
    Output("forested-sel-store", "data"),
    Input("forested-forest-graph", "clickData"),
    Input("forested-reset-btn", "n_clicks"),
    Input("forested-programme-selector", "value"),
    Input("forested-semester-selector", "value"),
    Input("forested-parcours-selector", "value"),
    Input("forested-competence-selector", "value"),
    State("forested-sel-store", "data"),
    prevent_initial_call=True,
    )
    def handle_click(click_data, reset, prog, sem, parcours, comp, current):
        if ctx.triggered_id in (
            "forested-reset-btn",
            "forested-programme-selector",
            "forested-semester-selector",
            "forested-parcours-selector",
            "forested-competence-selector"
        ):
            return None

        if not click_data:
            return current

        try:
            cd = click_data["points"][0].get("customdata")

            if not cd or not isinstance(cd, list) or len(cd) < 2:
                return None

            sel = {
                "type": cd[0],
                "id": cd[1]
            }

            if current and current.get("type") == sel["type"] and current.get("id") == sel["id"]:
                return None

            return sel

        except Exception:
            return None

    @app.callback(
    Output("forested-forest-graph", "figure"),
    Input("forested-rows-store", "data"),
    Input("forested-semester-selector", "value"),
    Input("forested-parcours-selector", "value"),
    Input("forested-competence-selector", "value"),
    Input("forested-sel-store", "data"),
    )
    def update_fig(rows, sem, parcours, comp, sel):
        """
        Crée la forêt après application du filtre parcours.

        Important :
        On filtre les lignes avant create_forest_figure.
        La fonction create_forest_figure reste générique.
        """
        if not rows:
            return empty_figure("Aucune donnée disponible")

        filtered_rows = filter_forest_rows_by_parcours(rows, parcours)

        if not filtered_rows:
            return empty_figure("Aucune donnée pour ce parcours")

        return create_forest_figure(
            filtered_rows,
            sem or "ALL",
            comp or "ALL",
            sel
        )

    @app.callback(
    Output("forested-focus-panel", "children"),
    Input("forested-sel-store", "data"),
    State("forested-rows-store", "data"),
    State("forested-semester-selector", "value"),
    State("forested-parcours-selector", "value"),
    State("forested-competence-selector", "value"),
    )
    def update_panel(sel, rows, sem, parcours, comp):
        """
        Met à jour le panneau détail en respectant le filtre parcours.
        """
        if not rows or not sel:
            return html.Div()

        filtered_rows = filter_forest_rows_by_parcours(rows, parcours)

        trees = build_trees(
            filtered_rows,
            sem or "ALL",
            comp or "ALL"
        )

        return build_focus_panel(
            filtered_rows,
            sel,
            trees,
            sem_filter=sem or "ALL"
        )
    @app.callback(
        Output("forested-legend-div", "children"),
        Input("forested-rows-store", "data"),
        Input("forested-semester-selector", "value"),
        Input("forested-parcours-selector", "value"),
        Input("forested-competence-selector", "value"),
    )
    def update_legend(rows, sem, parcours, comp):
        """
        Légende dynamique : affiche uniquement les compétences réellement visibles
        après application des filtres semestre, parcours et compétence.
        """
        if not rows:
            return []

        rows = filter_forest_rows_by_parcours(rows, parcours)

        if sem not in (None, "ALL"):
            rows = [
                r for r in rows
                if r.get("semestre") == sem
            ]

        if comp not in (None, "ALL"):
            rows = [
                r for r in rows
                if r.get("competence_code") == comp
            ]

        all_comps = sorted({
            r.get("competence_code")
            for r in rows
            if r.get("competence_code")
        })

        comp_badges = []

        for i, cc in enumerate(all_comps):
            cfg = PALETTE_ESS[i % len(PALETTE_ESS)]
            fill = cfg["n3_fill"]

            badge_style = {
                "width": "10px",
                "height": "10px",
                "borderRadius": "2px",
                "backgroundColor": fill,
                "display": "inline-block",
                "marginRight": "4px",
            }

            comp_badges.append(
                html.Span([
                    html.Span(style=badge_style),
                    html.Span(
                        cc,
                        style={
                            "fontSize": "11px",
                            "color": "#374151"
                        }
                    ),
                ], style={
                    "display": "flex",
                    "alignItems": "center",
                    "marginRight": "10px"
                })
            )

        return [
            html.Div([
                html.Label("Couleurs compétences", style=LABEL_STYLE),
                html.Div(
                    comp_badges,
                    style={
                        "display": "flex",
                        "flexWrap": "wrap"
                    }
                ),
            ]),
            html.Div([
                html.Label("Niveaux", style=LABEL_STYLE),
                html.Span(
                    "N1 pâle → N2 moyen → N3 saturé",
                    style={
                        "fontSize": "11px",
                        "color": "#374151"
                    }
                ),
            ], style={"marginLeft": "20px"}),
            html.Div([
                html.Label("Lecture", style=LABEL_STYLE),
                html.Span(
                    "Bas → haut : Compétence ◆ → Niveaux ■ → Barres AC",
                    style={
                        "fontSize": "11px",
                        "color": "#475569"
                    }
                ),
            ], style={"marginLeft": "20px"}),
        ]