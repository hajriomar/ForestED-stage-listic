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

FADE      = "rgba(203,213,225,0.35)"
FADE_LINE = "rgba(203,213,225,0.15)"

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
    {   # 3 — cyan/teal (remplace l'ancien navy #0C447C, trop proche du violet)
        "n1_fill":"#ECFEFF","n1_border":"#A5F3FC","n1_text":"#164E63",
        "n2_fill":"#22D3EE","n2_text":"#083344",
        "n3_fill":"#0E7490","n3_text":"#ECFEFF",
        "root_fill":"#164E63","root_text":"#ECFEFF","line":"#164E63",
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

COMP_PALETTE = PALETTE_ESS


def _comp_scheme(index):
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


def wrap_label(text, max_chars_per_line=28, max_lines=3):
    """
    Coupe un texte long en plusieurs lignes pour l'affichage Plotly.
    Ajoute … si le texte original est plus long que ce qui est affiché.
    """
    if not text:
        return ""
    words = str(text).strip().split()
    lines = []
    current_line = ""
    for word in words:
        candidate = f"{current_line} {word}".strip()
        if len(candidate) <= max_chars_per_line:
            current_line = candidate
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
        if len(lines) >= max_lines:
            break
    if current_line and len(lines) < max_lines:
        lines.append(current_line)
    displayed = " ".join(lines)
    if len(displayed) < len(str(text).strip()):
        lines[-1] = lines[-1].rstrip(".,;:") + "…"
    return "<br>".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

Y_COMP      = 0.0
Y_COMP_DESC = -1.3   # sous le losange (-0.45 code + espace + description)
Y_NIV       = 2.5
Y_BAR_BASE  = 3.5
BAR_MAX_H   = 4.0

Y_RANGE_MIN = -2.5   # espace pour 3 lignes de description

BAR_W    = 0.28
BAR_GAP  = 0.10
NIV_GAP  = 0.65
COMP_GAP = 2.8
MIN_X_SPAN_FULL = 34
MIN_X_SPAN_FOCUS = 22


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
        ue_type = ue.get("type")
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
                "ue_type": ue_type,
                "parcours": parcours_val,
            })
    return rows


def build_forest_rows(rows):
    result = []

    for r in rows:
        cc = r.get("competence_code")
        ac = r.get("ac_code")
        mc = r.get("module_code") or r.get("module_id")

        if not cc or not ac:
            continue

        try:
            niv = int(r.get("niveau") or 1)
        except Exception:
            niv = 1

        sem = r.get("semestre")
        sem_lbl = f"S{sem}" if sem and not str(sem).startswith("S") else str(sem or "?")

        result.append({
            "semestre": sem_lbl,
            "competence_code": cc,
            "competence_name": r.get("competence_name") or cc,
            "niveau": niv,
            "ac_code": ac,
            "ac_description": r.get("ac_description") or "",
            "module_code": mc,
            "module_name": r.get("module_name") or mc or "",
            "orphan": r.get("orphan", False),
            "ue_type": r.get("ue_type"),
            "parcours": r.get("parcours"),
        })

    # Couleur stable par compétence, calculée UNE SEULE FOIS sur toutes les lignes.
    # Important : la couleur ne dépend plus du filtre actif.
    all_comps = sorted({
        r.get("competence_code")
        for r in result
        if r.get("competence_code")
    })

    comp_color_index = {
        comp: i
        for i, comp in enumerate(all_comps)
    }

    for r in result:
        r["color_index"] = comp_color_index.get(
            r.get("competence_code"),
            0
        )

    return result


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


# FIX 1 : _max_mods — retourner au minimum 1
# max() sur une séquence de 0 retourne 0, pas la valeur par défaut.
# On force le minimum à 1 pour éviter une division par zéro dans
# compute_layout() quand tous les ACs n'ont aucun module référencé.
def _max_mods(trees):
    m = max(
        (len(a["mods"])
         for t in trees.values()
         for lvl in t["levels"].values()
         for a in lvl["acs"].values()),
        default=0,
    )
    return max(m, 1)


def _level_group_width(acs):
    n = len(acs)
    return n * BAR_W + max(0, n - 1) * BAR_GAP


def _tree_width(tree):
    n_niv  = len(tree["levels"])
    max_gw = max((_level_group_width(lvl["acs"]) for lvl in tree["levels"].values()), default=BAR_W)
    return n_niv * max_gw + max(0, n_niv - 1) * NIV_GAP


def compute_layout(trees, max_mods_g):
    comp_list = sorted(trees.keys())
    widths    = {cc: _tree_width(trees[cc]) for cc in comp_list}
    total     = sum(widths.values()) + max(0, len(comp_list)-1) * COMP_GAP

    cursor   = -total / 2
    pos_comp = {}
    pos_niv  = {}
    pos_bar  = {}
    meta_ac  = {}

    for cc in comp_list:
        tree = trees[cc]
        tw   = widths[cc]
        cx   = cursor + tw / 2
        pos_comp[cc] = cx

        niv_list = sorted(tree["levels"].keys())
        n_niv    = len(niv_list)
        gws      = [_level_group_width(tree["levels"][nv]["acs"]) for nv in niv_list]
        total_gw = sum(gws) + max(0, n_niv-1) * NIV_GAP
        gx_start = cx - total_gw / 2

        for i, niv in enumerate(niv_list):
            gw  = gws[i]
            gcx = gx_start + gw / 2
            pos_niv[(cc, niv)] = (gcx, Y_NIV)

            acs      = tree["levels"][niv]["acs"]
            n_ac     = len(acs)
            bar_total = n_ac * BAR_W + max(0, n_ac-1) * BAR_GAP
            bar_start = gcx - bar_total / 2

            for j, (ac, acd) in enumerate(sorted(acs.items(), key=lambda x: (len(x[1]["mods"]), x[0]))):
                bx    = bar_start + j * (BAR_W + BAR_GAP) + BAR_W / 2
                n_mod = len(acd["mods"])
                # FIX 2 : hauteur minimale de 25 % quand aucun module n'est référencé,
                # pour que la barre reste visible (AC présent mais non lié à un module).
                bar_val = n_mod if n_mod > 0 else max_mods_g * 0.25
                h     = (bar_val / max_mods_g) * BAR_MAX_H
                pos_bar[(cc, niv, ac)] = (bx, Y_BAR_BASE, Y_BAR_BASE + h)
                meta_ac[(cc, niv, ac)] = acd

            gx_start += gw + NIV_GAP

        cursor += tw + COMP_GAP

    return pos_comp, pos_niv, pos_bar, meta_ac


def _parse_sel(sel):
    if not sel or not isinstance(sel, dict):
        return None, None
    return sel.get("type"), sel.get("id")


def _active_set(sel, trees):
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

def filter_rows_by_click_selection(forest_rows, selected):
    """
    Crée une vraie vue focus à partir d'un clic.

    Au lieu de garder toute la forêt en arrière-plan avec transparence,
    on garde uniquement les lignes nécessaires :
    - compétence cliquée ;
    - niveau cliqué ;
    - AC cliqué.
    """

    kind, sid = _parse_sel(selected)

    if not kind:
        return forest_rows

    if kind == "comp":
        return [
            r for r in forest_rows
            if r.get("competence_code") == sid
        ]

    if kind == "niv":
        cc, niv_s = sid.split("::", 1)

        try:
            niv = int(niv_s)
        except Exception:
            return forest_rows

        return [
            r for r in forest_rows
            if r.get("competence_code") == cc
            and r.get("niveau") == niv
        ]

    if kind == "bar":
        cc, niv_s, ac = sid.split("::", 2)

        try:
            niv = int(niv_s)
        except Exception:
            return forest_rows

        return [
            r for r in forest_rows
            if r.get("competence_code") == cc
            and r.get("niveau") == niv
            and r.get("ac_code") == ac
        ]

    return forest_rows


def apply_min_x_span(xmin, xmax, min_span):
    """
    Empêche une vue focus de devenir trop zoomée.

    Exemple :
    si on affiche une seule compétence, on garde une largeur minimale
    pour éviter que les barres deviennent énormes.
    """

    current_span = xmax - xmin

    if current_span >= min_span:
        return xmin, xmax

    center = (xmin + xmax) / 2
    half = min_span / 2

    return center - half, center + half

def create_forest_figure(
    forest_rows,
    sem_filter="ALL",
    comp_filter="ALL",
    selected=None,
    min_x_span=MIN_X_SPAN_FULL
):
    if not forest_rows:
        return empty_figure("Aucune donnée ForestED disponible")

    trees = build_trees(forest_rows, sem_filter, comp_filter)
    if not trees:
        return empty_figure("Aucune donnée disponible pour ce filtre")

    mg     = _max_mods(trees)
    pos_comp, pos_niv, pos_bar, meta_ac = compute_layout(trees, mg)

    active    = _active_set(selected, trees)
    has_focus = active is not None

    def _on(key):
        return (not has_focus) or (key in active)

    fig        = go.Figure()
    shapes     = []
    comp_order = sorted(trees.keys())

    # Récupérer l'index couleur stable depuis les données complètes.
    # Cet index a été calculé dans build_forest_rows().
    comp_color_index = {}

    for row in forest_rows:
        cc = row.get("competence_code")
        if cc and cc not in comp_color_index:
            comp_color_index[cc] = row.get("color_index", 0)

    comp_schemes = {
        cc: _comp_scheme(comp_color_index.get(cc, 0))
        for cc in comp_order
    }

    def _scheme(cc):
        return comp_schemes[cc]

    # ── 1. TRONCS ────────────────────────────────────────────────────────────
    for cc, cx in pos_comp.items():
        sch      = _scheme(cc)
        line_col = sch["line"] if _on(f"COMP::{cc}") else FADE_LINE
        lw       = 3.0 if _on(f"COMP::{cc}") else 0.7
        lx, ly   = [], []
        for (cc2, niv), (nx, ny) in pos_niv.items():
            if cc2 != cc: continue
            lx.extend([cx, nx, None])
            ly.extend([Y_COMP + 0.25, Y_NIV - 0.25, None])
        if lx:
            fig.add_trace(go.Scatter(x=lx, y=ly, mode="lines",
                line=dict(color=line_col, width=lw), opacity=0.55,
                hoverinfo="none", showlegend=False))

    # ── 2. TIGES ─────────────────────────────────────────────────────────────
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

    # ── 3. BARRES AC ─────────────────────────────────────────────────────────
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
                fig.add_trace(go.Bar(
                    x=bx_on, y=bh_on, base=by_on,
                    width=[BAR_W * 0.9] * len(bx_on),
                    marker=dict(color=bar_fill, opacity=0.90,
                                line=dict(width=0.8, color=bar_border)),
                    text=[""] * len(bx_on),
                    hovertext=hov_on, hoverinfo="text",
                    hoverlabel=dict(bgcolor=bar_border, bordercolor="white",
                                    font=dict(color=bar_text, size=12)),
                    customdata=cd_on, name=f"{cc} N{niv_ref}", showlegend=False,
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

    # ── 4. COMPTEURS ─────────────────────────────────────────────────────────
    # Couleur du compteur : bar_fill pour N2/N3 (foncé, lisible sur fond blanc),
    # bar_border pour N1 (fill trop pâle sur fond blanc).
    tx_cnt, ty_cnt, ttxt, tcol = [], [], [], []
    for (cc, niv, ac), (bx, yb, yt) in pos_bar.items():
        acd = meta_ac[(cc, niv, ac)]
        n   = len(acd["mods"])
        on  = _on(f"BAR::{cc}::{niv}::{ac}")
        sch = _scheme(cc)
        nk  = _niv_key(niv)
        bar_fill, _, bar_border = sch[nk]
        # N1 = fill pâle → utiliser border (plus foncé) ; N2/N3 = fill déjà foncé
        cnt_col = bar_border if nk == "n1" else bar_fill
        tx_cnt.append(bx); ty_cnt.append(yt + 0.15); ttxt.append(str(n))
        tcol.append(cnt_col if on else "rgba(148,163,184,0.45)")
    if tx_cnt:
        fig.add_trace(go.Scatter(x=tx_cnt, y=ty_cnt, mode="text", text=ttxt,
            textfont=dict(size=9, color=tcol),
            hoverinfo="none", showlegend=False))

    # ── 5. NŒUDS NIVEAU ──────────────────────────────────────────────────────
    for cc in comp_order:
        sch = _scheme(cc)
        niv_labels = {1: "Débutant", 2: "Intermédiaire", 3: "Avancé"}
        for niv_ref in (1, 2, 3):
            nk = _niv_key(niv_ref)
            fill, txt, bdr = sch[nk]
            nx_, ny_, nhov, ncd, ncol, nsz, nbdr = [], [], [], [], [], [], []
            for (cc2, niv), (nx, ny) in pos_niv.items():
                if cc2 != cc or niv != niv_ref: continue
                on  = _on(f"NIV::{cc}::{niv}")
                lvl = trees[cc]["levels"].get(niv, {"acs": {}})
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
                hoverlabel=dict(bgcolor=bdr, bordercolor="white", font=dict(size=12)),
                customdata=ncd, showlegend=False,
            ))

    # ── 6. RACINES + DESCRIPTION ─────────────────────────────────────────────
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

        # Losange (marker seul, sans texte intégré)
        fig.add_trace(go.Scatter(
            x=[cx], y=[Y_COMP], mode="markers",
            marker=dict(symbol="diamond", size=sz, color=col,
                        line=dict(width=2.5, color=bdr_c)),
            hovertext=[f"<b>{cc}</b><br><i>{tree['name']}</i><br>"
                       f"{n_ac} AC · {n_m} modules"],
            hoverinfo="text",
            hoverlabel=dict(bgcolor=root_bdr, bordercolor="white",
                            font=dict(color=root_txt, size=12)),
            customdata=[["comp", cc]], showlegend=False,
        ))

        # Code compétence — juste sous le losange, centré
        if on:
            fig.add_trace(go.Scatter(
                x=[cx], y=[Y_COMP - 0.45],
                mode="text",
                text=[f"<b>{cc}</b>"],
                textposition="middle center",
                textfont=dict(size=10, color=root_bdr),
                hoverinfo="none",
                showlegend=False,
            ))

        # Description compacte dans un cadre sous le losange
        # Largeur du cadre basée sur la largeur réelle de l'arbre, avec min/max
        tree_w     = _tree_width(tree)
        half_w     = max(1.5, min(tree_w * 0.46, 3.5))
        # max_chars proportionnel (1 unité Plotly ≈ 13 caractères à 9px)
        max_chars  = max(24, int(half_w * 13))
        desc_text  = wrap_label(tree.get("name", ""), max_chars_per_line=max_chars, max_lines=3)
        if desc_text:
            n_lines   = desc_text.count("<br>") + 1
            half_h    = 0.22 + (n_lines - 1) * 0.18
            txt_col   = root_bdr if on else "rgba(148,163,184,0.6)"
            frame_col = f"rgba({int(root_bdr[1:3], 16)},{int(root_bdr[3:5], 16)},{int(root_bdr[5:7], 16)},0.25)" \
                        if root_bdr.startswith("#") and len(root_bdr) == 7 \
                        else "rgba(203,213,225,0.8)"
            shapes.append(dict(
                type="rect",
                x0=cx - half_w, x1=cx + half_w,
                y0=Y_COMP_DESC - half_h, y1=Y_COMP_DESC + half_h,
                fillcolor="rgba(255,255,255,0.96)",
                line=dict(color=frame_col, width=1),
                layer="below",
            ))
            fig.add_trace(go.Scatter(
                x=[cx], y=[Y_COMP_DESC],
                mode="text",
                text=[desc_text],
                textposition="middle center",
                textfont=dict(size=9, color=txt_col),
                hovertext=[f"<b>{cc}</b><br>{tree.get('name', '')}"],
                hoverinfo="text",
                showlegend=False,
            ))


    # ── 7. LABELS DE COUCHE ───────────────────────────────────────────────────
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

    # ── SHAPES ────────────────────────────────────────────────────────────────
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

    n_comp = len(trees)
    n_ac   = sum(len(l["acs"]) for t in trees.values() for l in t["levels"].values())
    n_mods = len({m for t in trees.values() for l in t["levels"].values()
                  for a in l["acs"].values() for m in a["mods"]})
    x_min = xmin - 1.5
    x_max = xmax + 0.5
    x_min, x_max = apply_min_x_span(x_min, x_max, min_x_span)
    fig.update_layout(
        title=dict(
            text=(f"<b>ForestED — Forêt pédagogique APC</b>"
                  f"<span style='color:#94A3B8;font-size:13px'>"
                  f" · {n_comp} compétences · {n_ac} AC · {n_mods} modules"
                  f"{focus_lbl}</span>"),
            x=0.01, y=0.98, font=dict(size=16, color="#0F172A")),
        height=760,
        paper_bgcolor="#F8FAFB", plot_bgcolor="#FFFFFF",
        barmode="overlay",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    xanchor="right", x=1, bgcolor="rgba(255,255,255,0.94)",
                    bordercolor="#E4E9F0", borderwidth=1,
                    font=dict(size=12, color="#374151")),
        margin=dict(l=120, r=50, t=75, b=30),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[x_min, x_max]
        ),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=[Y_RANGE_MIN, Y_BAR_BASE + BAR_MAX_H + 0.8]),
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

    def _sem_ok(r):
        if sem_filter in (None, "ALL"):
            return True
        return r.get("semestre") == sem_filter

    def _comp_border(cc, niv=None):
        color_index = next(
            (
                r.get("color_index", 0)
                for r in forest_rows
                if r.get("competence_code") == cc
            ),
            0
        )

        sch = _comp_scheme(color_index)

        if niv is None:
            return sch["root"][2]

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
    sems = sorted(
        {r["semestre"] for r in forest_rows
         if r.get("semestre") and r["semestre"] != "?"},
        key=_sort_sem,
    )
    return [{"label": "Tous les semestres", "value": "ALL"}] + \
           [{"label": s, "value": s} for s in sems]


def build_competence_options(forest_rows, sem="ALL"):
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


def get_competence_family(competence_code):
    if not competence_code:
        return "unknown", None
    code = str(competence_code).strip().upper()
    if re.match(r"^COMP_\d+$", code):
        return "essential", None
    match = re.match(r"^COMP_([A-Z][A-Z0-9]*)_\d+$", code)
    if match:
        return "parcours", match.group(1)
    return "unknown", None


def normalize_selected_parcours(selected_parcours):
    if not selected_parcours or selected_parcours == "ALL":
        return "ALL"
    value = str(selected_parcours).strip().upper()
    value = value.replace("-", "_").replace(" ", "_")
    if value.startswith("BUT_"):
        value = value.replace("BUT_", "", 1)
    return value


def get_allowed_competence_codes_for_parcours(forest_rows, selected_parcours):
    if not forest_rows:
        return set()
    selected = normalize_selected_parcours(selected_parcours)
    all_competences = {r.get("competence_code") for r in forest_rows if r.get("competence_code")}
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
    if not forest_rows:
        return []
    allowed = get_allowed_competence_codes_for_parcours(forest_rows, selected_parcours)
    return [r for r in forest_rows if r.get("competence_code") in allowed]


def build_parcours_options(forest_rows, sem="ALL"):
    if not forest_rows:
        return [{"label": "Tous les parcours", "value": "ALL"}]
    rows = forest_rows if sem in (None, "ALL") else \
           [r for r in forest_rows if r.get("semestre") == sem]
    parcours_values = set()
    for row in rows:
        family, parcours = get_competence_family(row.get("competence_code"))
        if family == "parcours" and parcours:
            parcours_values.add(parcours)
    options = [{"label": "Tous les parcours", "value": "ALL"}]
    for p in sorted(parcours_values):
        options.append({"label": p, "value": p})
    return options


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT DASH
# ══════════════════════════════════════════════════════════════════════════════

def _get_programme_options():
    summary = build_programmes_summary(load_processed_files())
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
                html.H1("Forêt pédagogique APC", style={
                    "color": "#0F172A", "fontSize": "26px", "fontWeight": "800",
                    "margin": "0 0 4px", "letterSpacing": "-0.3px"}),
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
            dcc.Dropdown(id="forested-parcours-selector",
                         options=[{"label": "Tous les parcours", "value": "ALL"}],
                         value="ALL", clearable=False, style={"fontSize": "14px"}),
        ], style={"width": "16%", "minWidth": "170px"}),

        html.Div([
            html.Label("Compétence", style=LABEL_STYLE),
            dcc.Dropdown(id="forested-competence-selector",
                         options=[{"label": "Toutes les compétences", "value": "ALL"}],
                         value="ALL", clearable=False, style={"fontSize": "14px"}),
        ], style={"width": "22%", "minWidth": "200px"}),

        html.Div([
            html.Label(" ", style={**LABEL_STYLE, "visibility": "hidden"}),
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
        if ctx.triggered_id in ("forested-reset-btn", "forested-programme-selector",
                                "forested-semester-selector", "forested-parcours-selector",
                                "forested-competence-selector"):
            return None
        if not click_data:
            return current
        try:
            cd = click_data["points"][0].get("customdata")
            if not cd or not isinstance(cd, list) or len(cd) < 2:
                return None
            sel = {"type": cd[0], "id": cd[1]}
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
        if not rows:
            return empty_figure("Aucune donnée disponible")

        # 1. Filtre métier : parcours
        filtered_rows = filter_forest_rows_by_parcours(rows, parcours)

        if not filtered_rows:
            return empty_figure("Aucune donnée pour ce parcours")

        # 2. Si l'utilisateur filtre une compétence avec le dropdown,
        # on garde la logique de filtre classique.
        if comp not in (None, "ALL"):
            return create_forest_figure(
                filtered_rows,
                sem_filter=sem or "ALL",
                comp_filter=comp,
                selected=None,
                min_x_span=MIN_X_SPAN_FULL
            )

        # 3. Si l'utilisateur clique dans la forêt,
        # on crée une vraie vue focus.
        if sel:
            focus_rows = filter_rows_by_click_selection(filtered_rows, sel)

            if focus_rows:
                return create_forest_figure(
                    focus_rows,
                    sem_filter=sem or "ALL",
                    comp_filter="ALL",
                    selected=None,
                    min_x_span=MIN_X_SPAN_FOCUS
                )

        # 4. Vue globale normale
        return create_forest_figure(
            filtered_rows,
            sem_filter=sem or "ALL",
            comp_filter="ALL",
            selected=None,
            min_x_span=MIN_X_SPAN_FULL
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
        if not rows or not sel:
            return html.Div()
        filtered_rows = filter_forest_rows_by_parcours(rows, parcours)
        trees = build_trees(filtered_rows, sem or "ALL", comp or "ALL")
        return build_focus_panel(filtered_rows, sel, trees, sem_filter=sem or "ALL")

    @app.callback(
        Output("forested-legend-div", "children"),
        Input("forested-rows-store", "data"),
        Input("forested-semester-selector", "value"),
        Input("forested-parcours-selector", "value"),
        Input("forested-competence-selector", "value"),
    )
    def update_legend(rows, sem, parcours, comp):
        if not rows:
            return []
        rows = filter_forest_rows_by_parcours(rows, parcours)
        if sem not in (None, "ALL"):
            rows = [r for r in rows if r.get("semestre") == sem]
        if comp not in (None, "ALL"):
            rows = [r for r in rows if r.get("competence_code") == comp]
        all_comps = sorted({r.get("competence_code") for r in rows if r.get("competence_code")})
        comp_badges = []
        for cc in all_comps:
            color_index = next(
                (
                    r.get("color_index", 0)
                    for r in rows
                    if r.get("competence_code") == cc
                ),
                0
            )

            cfg = PALETTE_ESS[color_index % len(PALETTE_ESS)]
            fill = cfg["n3_fill"]
            badge_style = {"width": "10px", "height": "10px", "borderRadius": "2px",
                           "backgroundColor": fill, "display": "inline-block", "marginRight": "4px"}
            comp_badges.append(
                html.Span([
                    html.Span(style=badge_style),
                    html.Span(cc, style={"fontSize": "11px", "color": "#374151"}),
                ], style={"display": "flex", "alignItems": "center", "marginRight": "10px"})
            )
        return [
            html.Div([
                html.Label("Couleurs compétences", style=LABEL_STYLE),
                html.Div(comp_badges, style={"display": "flex", "flexWrap": "wrap"}),
            ]),
            html.Div([
                html.Label("Niveaux", style=LABEL_STYLE),
                html.Span("N1 pâle → N2 moyen → N3 saturé",
                          style={"fontSize": "11px", "color": "#374151"}),
            ], style={"marginLeft": "20px"}),
            html.Div([
                html.Label("Lecture", style=LABEL_STYLE),
                html.Span("Bas → haut : Compétence ◆ → Niveaux ■ → Barres AC",
                          style={"fontSize": "11px", "color": "#475569"}),
            ], style={"marginLeft": "20px"}),
        ]