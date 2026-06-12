"""
forested_visualisations.py
──────────────────────────
Optimisations de performance :
- Batching d'arêtes : ~5 000 traces → 6 traces (rendu ~100x plus rapide)
- dcc.Store pour éviter de recalculer les données à chaque interaction
- Logique focus découplée du layout

Correctifs du nouveau méta-modèle curriculum :
- build_visualisation_rows : compatible Polytech (type MODULE) et BUT (type UE_COMMUNE/optionnelle)
- ue_display_code : pour Polytech, le regroupement se fait par semestre
  (car chaque groupe Polytech = 1 module, pas une vraie UE)
- Pour BUT, on utilise le vrai code UE (UE_1_1, UE_1_2...)
- normalize_module_code : extrait correctement les codes Polytech depuis les IDs
"""

from dash import html, dcc, Input, Output, State, ctx
import plotly.graph_objects as go
import re

from app_tools import load_processed_files, build_programmes_summary


# ══════════════════════════════════════════════════════════════════════════════
#  DESIGN TOKENS
# ══════════════════════════════════════════════════════════════════════════════

PAGE_STYLE = {
    "backgroundColor": "#F8FAFB",
    "minHeight": "100vh",
    "padding": "28px 36px",
    "fontFamily": "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
}

CARD_STYLE = {
    "backgroundColor": "#FFFFFF",
    "padding": "18px 24px",
    "borderRadius": "10px",
    "boxShadow": "0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)",
    "marginBottom": "14px",
    "border": "1px solid #E4E9F0"
}

LABEL_STYLE = {
    "color": "#5A6478", "fontWeight": "700", "fontSize": "10px",
    "letterSpacing": "1px", "textTransform": "uppercase",
    "marginBottom": "7px", "display": "block"
}

# Palette sémantique
C_COMP   = "#6D28D9"
C_AC_N1  = "#10B981"
C_AC_N2  = "#F59E0B"
C_AC_N3  = "#EF4444"
C_MODULE = "#1D4ED8"

# Arêtes
EDGE_DEFAULT_CA = "rgba(109,40,217,0.30)"
EDGE_DEFAULT_AM = "rgba(29,78,216,0.28)"
EDGE_FOCUS_CA   = "rgba(109,40,217,0.85)"
EDGE_FOCUS_AM   = "rgba(29,78,216,0.80)"

FADE_OP   = 0.09
EDGE_FADE = 0.06


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def _niveau_color(niveau):
    try:
        return {1: C_AC_N1, 2: C_AC_N2, 3: C_AC_N3}.get(int(niveau), "#94A3B8")
    except Exception:
        return "#94A3B8"


def _niveau_label(niveau):
    return {"1": "Débutant", "2": "Intermédiaire", "3": "Avancé"}.get(str(niveau), "–")


def sort_semester(value):
    try:
        return int(str(value).replace("S", ""))
    except Exception:
        return 999


def normalize_module_code(code):
    """
    Normalise les codes modules pour le matching curriculum ↔ compétences.

    Supporte :
    - IDs longs BUT  : S1_UE_1_1_SAE1_01 → SAE1.01
                       S1_UE_1_1_R1_01   → R1.01
    - Codes BUT nets : SAE1.01, R1.01
    - IDs longs Poly : S5_INFO501_PACY   → INFO501
    - Codes Polytech : INFO501, DATA601
    """
    if not code:
        return None

    text = str(code).strip().upper()
    text = text.replace("SAÉ", "SAE")
    text = text.replace("-", "_")
    text = text.replace(" ", "_")

    # BUT — IDs avec underscores : SAE1_01 / R1_01
    match = re.search(r"(SAE|R)_?([1-6])_([0-9]{2})", text)
    if match:
        return f"{match.group(1)}{match.group(2)}.{match.group(3)}"

    # BUT — codes déjà propres : SAE1.01 / R1.01
    match = re.search(r"(SAE|R)([1-6])\.([0-9]{2})", text)
    if match:
        return f"{match.group(1)}{match.group(2)}.{match.group(3)}"

    # Polytech — codes [A-Z]{2,6}[0-9]{3} : INFO501, DATA601, SHES901
    match = re.search(r"[A-Z]{2,6}[0-9]{3}", text)
    if match:
        return match.group(0)

    return text


def _is_polytech_source(groupe_type):
    """
    Détecte si on est dans un curriculum Polytech.
    Dans Polytech, les groupes ont type='MODULE' ou type='STAGE'.
    Dans BUT, ils ont type='UE_COMMUNE' ou type='UE_OPTIONNELLE'.
    """
    return groupe_type in ("MODULE", "STAGE", None)


def _ue_display_key(groupe, semestre):
    """
    Retourne le code UE sémantique à utiliser dans le graphe.

    - BUT  : le vrai code UE (ex: UE_1_1)
    - Poly : le semestre (ex: S5), car chaque groupe Polytech = 1 module
    """
    groupe_type = groupe.get("type")
    if groupe_type in ("UE_COMMUNE", "UE_OPTIONNELLE", "OPTION_PARCOURS"):
        # BUT : vrai code UE
        return groupe.get("code", "UE?"), groupe.get("intitule", groupe.get("code", "?"))
    else:
        # Polytech : regrouper par semestre
        sem_str = f"S{semestre}" if semestre is not None else "?"
        return sem_str, sem_str


def get_level_color(niveau):
    return _niveau_color(niveau)


def get_programme_options():
    datasets = load_processed_files()
    programmes = build_programmes_summary(datasets)
    return [
        {"label": f"{item['source']} — {item['programme']}",
         "value": f"{item['source']}::{item['programme']}"}
        for item in programmes
    ]


def get_selected_data(selected_programme):
    datasets = load_processed_files()
    if not selected_programme:
        return None, None
    source, programme = selected_programme.split("::")
    comp = next((i["data"] for i in datasets["competence"]
                 if i["source"] == source and i["programme"] == programme), None)
    curr = next((i["data"] for i in datasets["curriculum"]
                 if i["source"] == source and i["programme"] == programme), None)
    return comp, curr


def iter_curriculum_elements(programme):
    """
    Itère sur tous les éléments pédagogiques.

    Retourne pour chaque élément :
      periode, semestre, ue (groupe parent), ue_display_code, ue_display_name,
      option, parcours, element

    Compatible :
    1. Polytech nouveau modèle : periode → groupes (type MODULE/STAGE) → elements
    2. BUT nouveau modèle UE commune : periode → groupes (type UE_COMMUNE) → elements
    3. BUT nouveau modèle UE optionnelle : periode → groupes → sous-groupes → elements
    4. Ancien modèle (compat) : periode → unites_enseignement → elements
    """
    for periode in programme.get("periodes", []):
        semestre = (
            periode.get("numero")
            or periode.get("semestre")
            or periode.get("id")
        )

        # === Ancien modèle (compat) ===
        for ue in periode.get("unites_enseignement", []):
            for element in ue.get("elements_pedagogiques", []):
                yield {
                    "periode": periode,
                    "semestre": semestre,
                    "ue": ue,
                    "ue_display_code": ue.get("code", "?"),
                    "ue_display_name": ue.get("intitule", ue.get("code", "?")),
                    "option": None,
                    "parcours": "COMMUN",
                    "element": element,
                }

        # === Nouveau modèle ===
        for groupe in periode.get("groupes_elements_pedagogiques", []):
            ue_code, ue_name = _ue_display_key(groupe, semestre)

            # -- UE élémentaire directe (BUT UE_COMMUNE ou Polytech MODULE)
            if "elements_pedagogiques" in groupe:
                parcours = groupe.get("contrainte") or "COMMUN"
                for element in groupe.get("elements_pedagogiques", []):
                    yield {
                        "periode": periode,
                        "semestre": semestre,
                        "ue": groupe,
                        "ue_display_code": ue_code,
                        "ue_display_name": ue_name,
                        "option": None,
                        "parcours": parcours,
                        "element": element,
                    }

            # -- UE composite (BUT UE_OPTIONNELLE avec parcours)
            elif "groupes_elements_pedagogiques" in groupe:
                for option in groupe.get("groupes_elements_pedagogiques", []):
                    opt_code, opt_name = _ue_display_key(option, semestre)
                    parcours = option.get("contrainte") or "COMMUN"
                    for element in option.get("elements_pedagogiques", []):
                        yield {
                            "periode": periode,
                            "semestre": semestre,
                            "ue": groupe,
                            "ue_display_code": ue_code,
                            "ue_display_name": ue_name,
                            "option": option,
                            "parcours": parcours,
                            "element": element,
                        }


def get_element_acquis(element):
    if "acquis_apprentissage" in element:
        return element.get("acquis_apprentissage", [])
    return element.get("acquis", [])


def get_element_credits(element):
    return (
        element.get("credits")
        if element.get("credits") is not None
        else element.get("ects", 0.0)
    )


def get_ue_credits(ue):
    return (
        ue.get("credits")
        if ue.get("credits") is not None
        else ue.get("ects", 0.0)
    )


def build_competence_items(competence_data):
    """
    Construit la liste des liens AC → module_code normalisé.
    Compatible Polytech et BUT.
    """
    comp_items = []

    for sous in competence_data.get("sous_classifications", []):
        for comp in sous.get("competences", []):
            competence_code = comp.get("code")
            competence_name = comp.get("nom")

            # CompetenceComposite (BUT) : itérer sur les compétences associées
            sub_comps = comp.get("competences_associees", [])
            targets = sub_comps if sub_comps else [comp]

            for target in targets:
                for niveau in target.get("niveaux_developpement", []):
                    niveau_value = niveau.get("niveau")

                    for ac in niveau.get("apprentissages_critiques", []):
                        modules = list(dict.fromkeys(
                            ac.get("modules", [])
                            + ac.get("ressources", [])
                            + ac.get("saes", [])
                        ))

                        for module_code in modules:
                            normalized = normalize_module_code(module_code)
                            if not normalized:
                                continue

                            comp_items.append({
                                "sous_classification": sous.get("code"),
                                "competence_code": competence_code,
                                "competence_name": competence_name,
                                "niveau": niveau_value,
                                "ac_code": ac.get("code"),
                                "ac_description": ac.get("description"),
                                "module_code": normalized,
                            })

    return comp_items


def build_visualisation_rows(competence_data, curriculum_data):
    """
    Construit les lignes utilisées par tous les graphes.

    Chaque ligne = un lien (élément pédagogique ↔ AC de compétence).
    Compatible Polytech et BUT, ancien et nouveau méta-modèle.
    """
    rows = []

    if not competence_data or not curriculum_data:
        return rows

    competence_items = build_competence_items(competence_data)

    # Index module_code → liste d'items compétence
    comp_index = {}
    for item in competence_items:
        mc = item["module_code"]
        comp_index.setdefault(mc, []).append(item)

    for row_ctx in iter_curriculum_elements(curriculum_data):
        periode  = row_ctx["periode"]
        semestre = row_ctx["semestre"]
        ue       = row_ctx["ue"]
        option   = row_ctx["option"]
        parcours = row_ctx["parcours"]
        element  = row_ctx["element"]
        ue_display_code = row_ctx["ue_display_code"]
        ue_display_name = row_ctx["ue_display_name"]

        element_id = element.get("id")
        # Priorité : champ code > dériver depuis l'id
        element_raw = element.get("code") or element_id
        element_code = normalize_module_code(element_raw)

        if not element_code:
            continue

        linked_competences = comp_index.get(element_code, [])
        if not linked_competences:
            continue

        acquis_list = get_element_acquis(element)

        for linked in linked_competences:
            base_row = {
                "semestre": semestre,
                "periode_id": periode.get("id"),

                # UE sémantique (lisible, pas MODULE_INFO501_PACY)
                "ue_id":          ue.get("id"),
                "ue_code":        ue_display_code,
                "ue_name":        ue_display_name,
                "ue_type":        ue.get("type"),
                "ue_credits":     get_ue_credits(ue),

                "option_id":      option.get("id")       if option else None,
                "option_code":    option.get("code")     if option else None,
                "option_name":    option.get("intitule") if option else None,

                "parcours":       parcours,

                "module_id":      element_id,
                "module_code":    element_code,
                "module_name":    element.get("nom"),
                "module_type":    element.get("type"),
                "module_credits": get_element_credits(element),
                "module_volume_total": element.get("volume_total", 0.0),

                **linked,
            }

            if acquis_list:
                for acquis in acquis_list:
                    rows.append({
                        **base_row,
                        "acquis_id":          acquis.get("id"),
                        "acquis_description": acquis.get("description"),
                    })
            else:
                rows.append({
                    **base_row,
                    "acquis_id":          None,
                    "acquis_description": None,
                })

    return rows


def empty_figure(message="Aucune donnée"):
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=16, color="#94A3B8"))
    fig.update_layout(height=600, paper_bgcolor="#F8FAFB", plot_bgcolor="#F8FAFB",
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  GRAPHE PÉDAGOGIQUE
# ══════════════════════════════════════════════════════════════════════════════

def _build_graph_data(rows):
    """
    Construit les structures de données pour le graphe.

    Clé de nœud module : (module_code, semestre)
    → dédoublonne les SAE/Ressources BUT qui apparaissent dans plusieurs UEs
      d'un même semestre (ex: SAE1.01 dans UE_1_1, UE_1_2, UE_1_3 → 1 nœud)
    → conserve les distinctions inter-semestres (SAE1.01_S1 ≠ SAE1.01_S2)
    → sans impact sur Polytech où chaque module n'apparaît qu'une fois par semestre
    """
    comps, acs, modules = {}, {}, {}
    edges_ca, edges_am  = [], []
    seen_ca, seen_am    = set(), set()

    for r in rows:
        cc  = r.get("competence_code")
        ac  = r.get("ac_code")
        mc  = r.get("module_code")   # code normalisé (ex: SAE1.01, INFO501)
        sem = r.get("semestre")
        if not cc or not ac or not mc:
            continue

        # Clé de nœud module : code + semestre (évite l'explosion BUT multi-UE)
        mk = f"{mc}::{sem}" if sem is not None else mc

        comps[cc] = r.get("competence_name", "")

        if ac not in acs:
            acs[ac] = {
                "niveau":    r.get("niveau"),
                "desc":      r.get("ac_description", ""),
                "comp_code": cc,
            }

        if mk not in modules:
            modules[mk] = {
                "name":    r.get("module_name", ""),
                "code":    mc,
                "sem":     sem,
                "ue_code": r.get("ue_code", ""),
                "ue_name": r.get("ue_name", ""),
            }

        if (cc, ac) not in seen_ca:
            edges_ca.append((cc, ac)); seen_ca.add((cc, ac))
        if (ac, mk) not in seen_am:
            edges_am.append((ac, mk)); seen_am.add((ac, mk))

    return comps, acs, modules, edges_ca, edges_am


def _build_layout(comps, acs, modules):
    Y_COMP, Y_AC, Y_MODULE = 0.0, 5.5, 11.0
    COMP_GAP   = 9.0
    AC_GAP     = 1.3
    MODULE_GAP = 0.85
    UE_GAP     = 2.5

    pos, node_meta = {}, {}

    # Compétences
    comp_list = sorted(comps.keys())
    n_comp    = len(comp_list)
    comp_x    = {}
    for i, cc in enumerate(comp_list):
        x = (i - (n_comp - 1) / 2) * COMP_GAP
        comp_x[cc] = x
        key = f"COMP::{cc}"
        pos[key]       = (x, Y_COMP)
        node_meta[key] = {"type": "competence", "code": cc, "name": comps[cc]}

    # AC — groupés par compétence, triés par niveau
    for cc in comp_list:
        acs_c = sorted(
            [a for a, m in acs.items() if m["comp_code"] == cc],
            key=lambda a: (int(acs[a]["niveau"] or 99), a)
        )
        n_ac, base_x = len(acs_c), comp_x[cc]
        for j, ac in enumerate(acs_c):
            x   = base_x + (j - (n_ac - 1) / 2) * AC_GAP
            key = f"AC::{ac}"
            pos[key]       = (x, Y_AC)
            node_meta[key] = {
                "type":   "ac",
                "code":   ac,
                "niveau": acs[ac]["niveau"],
                "desc":   acs[ac]["desc"],
                "comp":   cc,
            }

    # Modules — groupés par UE (ue_code lisible), triés par UE puis code module
    # mk = clé déduplication = "module_code::semestre" (ex: "SAE1.01::1", "INFO501::5")
    ue_groups = {}
    for mk, meta in modules.items():
        ue = meta["ue_code"] or "Sans UE"
        ue_groups.setdefault(ue, {"name": meta.get("ue_name", ue), "mods": []})
        ue_groups[ue]["mods"].append(mk)

    # Tri des UE : ordre naturel (S5 < S6 < S7 ou UE_1_1 < UE_1_2...)
    def _ue_sort_key(ue_code):
        nums = re.findall(r"\d+", str(ue_code))
        return [int(n) for n in nums] if nums else [999]

    ue_sorted = sorted(ue_groups.keys(), key=_ue_sort_key)
    total_w   = (sum(len(ue_groups[u]["mods"]) for u in ue_sorted) * MODULE_GAP
                 + max(0, len(ue_groups) - 1) * UE_GAP)
    cursor_x  = -total_w / 2

    ue_display, ue_x_ranges = {}, {}
    for ue_code in ue_sorted:
        ue_info  = ue_groups[ue_code]
        ue_label = ue_info["name"]
        ue_display[ue_code] = ue_label          # ← clé présente dans ue_x_ranges

        # Tri par code normalisé pour ordre stable (SAE1.01 < SAE1.11 < R1.01...)
        mods_ue = sorted(ue_info["mods"], key=lambda mk: modules[mk]["code"])
        x_start = cursor_x

        for mk in mods_ue:
            key = f"MOD::{mk}"
            pos[key]       = (cursor_x, Y_MODULE)
            node_meta[key] = {
                "type": "module",
                "id":   mk,
                "name": modules[mk]["name"],
                "code": modules[mk]["code"],
                "ue":   ue_label,
            }
            cursor_x += MODULE_GAP

        x_end = cursor_x - MODULE_GAP
        ue_x_ranges[ue_code] = (
            x_start - MODULE_GAP * 0.4,
            x_end   + MODULE_GAP * 0.4,
        )
        cursor_x += UE_GAP

    return pos, node_meta, ue_display, ue_x_ranges


def _resolve_focus(node_key, node_meta, acs, edges_am):
    if not node_key or node_key not in node_meta:
        return set(), set()

    focus_nodes = {node_key}
    focus_edges = set()
    ntype = node_meta[node_key]["type"]

    if ntype == "competence":
        cc = node_meta[node_key]["code"]
        for ac, meta in acs.items():
            if meta["comp_code"] == cc:
                ak = f"AC::{ac}"
                focus_nodes.add(ak)
                focus_edges.add(frozenset([node_key, ak]))
                for _, mk in [(e0, e1) for e0, e1 in edges_am if e0 == ac]:
                    mnk = f"MOD::{mk}"
                    focus_nodes.add(mnk)
                    focus_edges.add(frozenset([ak, mnk]))

    elif ntype == "ac":
        ac = node_meta[node_key]["code"]
        cc = acs[ac]["comp_code"]
        ck = f"COMP::{cc}"
        focus_nodes.add(ck)
        focus_edges.add(frozenset([node_key, ck]))
        for _, mk in [(e0, e1) for e0, e1 in edges_am if e0 == ac]:
            mnk = f"MOD::{mk}"
            focus_nodes.add(mnk)
            focus_edges.add(frozenset([node_key, mnk]))

    elif ntype == "module":
        # mk = clé dédup "code::sem"
        mk = node_meta[node_key]["id"]
        for ac, mk2 in edges_am:
            if mk2 == mk:
                ak = f"AC::{ac}"
                focus_nodes.add(ak)
                focus_edges.add(frozenset([node_key, ak]))
                cc = acs[ac]["comp_code"]
                ck = f"COMP::{cc}"
                focus_nodes.add(ck)
                focus_edges.add(frozenset([ak, ck]))

    return focus_nodes, focus_edges


def create_forest_graph(rows, selected_node=None, semester_filter=None):
    AC_GAP = 1.3

    if not rows:
        return empty_figure("Aucune donnée disponible")

    if semester_filter and semester_filter != "all":
        rows = [r for r in rows if str(r.get("semestre")) == str(semester_filter)]
    if not rows:
        return empty_figure("Aucune donnée pour ce semestre")

    comps, acs, modules, edges_ca, edges_am = _build_graph_data(rows)
    if not comps:
        return empty_figure("Aucun lien trouvé")

    pos, node_meta, ue_display, ue_x_ranges = _build_layout(comps, acs, modules)

    focus_nodes, focus_edges = _resolve_focus(selected_node, node_meta, acs, edges_am)
    has_focus = bool(focus_nodes)

    def node_op(key):
        if not has_focus: return 1.0
        return 1.0 if key in focus_nodes else FADE_OP

    def edge_is_focus(a, b):
        return has_focus and frozenset([a, b]) in focus_edges

    # ── Batching d'arêtes ────────────────────────────────────────────
    ex_ca_off, ey_ca_off = [], []
    ex_ca_on,  ey_ca_on  = [], []
    ex_am_off, ey_am_off = [], []
    ex_am_on,  ey_am_on  = [], []

    for cc, ac in edges_ca:
        ck, ak = f"COMP::{cc}", f"AC::{ac}"
        if ck not in pos or ak not in pos: continue
        x0, y0 = pos[ck]; x1, y1 = pos[ak]
        if edge_is_focus(ck, ak):
            ex_ca_on  += [x0, x1, None]; ey_ca_on  += [y0, y1, None]
        else:
            ex_ca_off += [x0, x1, None]; ey_ca_off += [y0, y1, None]

    for ac, mi in edges_am:
        ak, mk = f"AC::{ac}", f"MOD::{mi}"
        if ak not in pos or mk not in pos: continue
        x0, y0 = pos[ak]; x1, y1 = pos[mk]
        if edge_is_focus(ak, mk):
            ex_am_on  += [x0, x1, None]; ey_am_on  += [y0, y1, None]
        else:
            ex_am_off += [x0, x1, None]; ey_am_off += [y0, y1, None]

    op_off_ca = EDGE_FADE if has_focus else 1.0
    op_off_am = EDGE_FADE if has_focus else 1.0

    traces = []

    if ex_ca_off:
        traces.append(go.Scatter(x=ex_ca_off, y=ey_ca_off, mode="lines",
            line=dict(color=EDGE_DEFAULT_CA, width=0.9),
            opacity=op_off_ca, hoverinfo="none", showlegend=False))
    if ex_ca_on:
        traces.append(go.Scatter(x=ex_ca_on, y=ey_ca_on, mode="lines",
            line=dict(color=EDGE_FOCUS_CA, width=2.4),
            opacity=1.0, hoverinfo="none", showlegend=False))
    if ex_am_off:
        traces.append(go.Scatter(x=ex_am_off, y=ey_am_off, mode="lines",
            line=dict(color=EDGE_DEFAULT_AM, width=0.8),
            opacity=op_off_am, hoverinfo="none", showlegend=False))
    if ex_am_on:
        traces.append(go.Scatter(x=ex_am_on, y=ey_am_on, mode="lines",
            line=dict(color=EDGE_FOCUS_AM, width=2.2),
            opacity=1.0, hoverinfo="none", showlegend=False))

    # ── Nœuds compétences ────────────────────────────────────────────
    cx, cy, ct, chov, ccd, csz, cop = [], [], [], [], [], [], []
    for key, m in node_meta.items():
        if m["type"] != "competence": continue
        x, y = pos[key]
        cx.append(x); cy.append(y)
        ct.append(f"<b>{m['code']}</b>")
        chov.append(
            f"<b>Compétence : {m['code']}</b><br>"
            f"<i>{m['name']}</i><br><br>🖱 Cliquez pour explorer"
        )
        ccd.append(key)
        csz.append(20 if key == selected_node else 14)
        cop.append(node_op(key))

    traces.append(go.Scatter(
        x=cx, y=cy, mode="markers+text",
        marker=dict(color=C_COMP, size=csz, symbol="diamond",
                    opacity=cop, line=dict(width=1.8, color="#A78BFA")),
        text=ct, textposition="bottom center",
        textfont=dict(size=9, color=C_COMP),
        hovertext=chov, hoverinfo="text",
        hoverlabel=dict(bgcolor="#4C1D95", bordercolor="#A78BFA",
                        font=dict(color="white", size=12)),
        customdata=ccd, name="Compétences", showlegend=True
    ))

    # ── Nœuds AC ─────────────────────────────────────────────────────
    ax, ay, ahov, acd, asz, aop, acol = [], [], [], [], [], [], []
    for key, m in node_meta.items():
        if m["type"] != "ac": continue
        x, y = pos[key]
        col = _niveau_color(m["niveau"])
        ax.append(x); ay.append(y); acol.append(col)
        ahov.append(
            f"<b>AC : {m['code']}</b><br>"
            f"Niveau {m['niveau']} — {_niveau_label(m['niveau'])}<br>"
            f"Compétence : {m['comp']}<br><br>"
            f"<i>{m['desc']}</i><br><br>"
            f"🖱 Cliquez pour explorer"
        )
        acd.append(key)
        asz.append(13 if key == selected_node else 9)
        aop.append(node_op(key))

    traces.append(go.Scatter(
        x=ax, y=ay, mode="markers",
        marker=dict(color=acol, size=asz, symbol="circle",
                    opacity=aop, line=dict(width=1.2, color="white")),
        hovertext=ahov, hoverinfo="text",
        hoverlabel=dict(bgcolor="#1F2937", bordercolor="#6B7280",
                        font=dict(color="white", size=12)),
        customdata=acd, name="AC", showlegend=True
    ))

    # ── Nœuds modules ─────────────────────────────────────────────────
    mx, my, mhov, mcd, msz, mop = [], [], [], [], [], []
    for key, m in node_meta.items():
        if m["type"] != "module": continue
        x, y = pos[key]
        mx.append(x); my.append(y)
        mhov.append(
            f"<b>{m['code']}</b><br>"
            f"<i>{m['name']}</i><br>"
            f"{m['ue']}<br><br>"
            f"🖱 Cliquez pour explorer"
        )
        mcd.append(key)
        msz.append(12 if key == selected_node else 8)
        mop.append(node_op(key))

    traces.append(go.Scatter(
        x=mx, y=my, mode="markers",
        marker=dict(color=C_MODULE, size=msz, symbol="square",
                    opacity=mop, line=dict(width=1.2, color="#93C5FD")),
        hovertext=mhov, hoverinfo="text",
        hoverlabel=dict(bgcolor="#1E3A8A", bordercolor="#93C5FD",
                        font=dict(color="white", size=12)),
        customdata=mcd, name="Modules", showlegend=True
    ))

    # ── Labels couches ────────────────────────────────────────────────
    if pos:
        x_left = min(x for x, _ in pos.values()) - 8
        traces.append(go.Scatter(
            x=[x_left] * 3, y=[0.0, 5.5, 11.0], mode="text",
            text=["<b>Compétences</b>", "<b>AC</b>", "<b>Modules</b>"],
            textfont=dict(size=13, color=[C_COMP, "#4B5563", C_MODULE]),
            hoverinfo="none", showlegend=False
        ))

    # ── Labels UE (noms lisibles) ─────────────────────────────────────
    ue_lx = [(x0 + x1) / 2 for x0, x1 in ue_x_ranges.values()]
    ue_lt = [f"<b>{ue_display[uc]}</b>" for uc in ue_x_ranges]
    if ue_lx:
        traces.append(go.Scatter(
            x=ue_lx, y=[12.0] * len(ue_lx), mode="text",
            text=ue_lt, textfont=dict(size=10, color="#64748B"),
            hoverinfo="none", showlegend=False
        ))

    # ── Shapes ───────────────────────────────────────────────────────
    shapes = []
    ue_bgs = ["rgba(219,234,254,0.35)", "rgba(237,233,254,0.28)"]
    for i, (uc, (x0, x1)) in enumerate(ue_x_ranges.items()):
        shapes.append(dict(type="rect", x0=x0, x1=x1,
                           y0=10.5, y1=11.7,
                           fillcolor=ue_bgs[i % 2],
                           line=dict(color="rgba(148,163,184,0.25)", width=1),
                           layer="below"))

    if pos:
        xm = min(x for x, _ in pos.values()) - 10
        xx = max(x for x, _ in pos.values()) + 10
        for yv, fc in [(0.0, "rgba(109,40,217,0.08)"),
                       (5.5, "rgba(75,85,99,0.06)"),
                       (11.0, "rgba(29,78,216,0.07)")]:
            shapes.append(dict(type="rect", x0=xm, x1=xx,
                               y0=yv - 0.55, y1=yv + 0.55,
                               fillcolor=fc, line=dict(width=0), layer="below"))

        comp_list = sorted(comps.keys())
        comp_bgs  = ["rgba(237,233,254,0.14)", "rgba(248,250,252,0.0)"]
        for i, cc in enumerate(comp_list):
            xs = [pos[f"AC::{a}"][0] for a, m in acs.items()
                  if m["comp_code"] == cc and f"AC::{a}" in pos]
            if not xs: continue
            shapes.append(dict(type="rect",
                               x0=min(xs) - AC_GAP * 0.6, x1=max(xs) + AC_GAP * 0.6,
                               y0=-0.8, y1=6.3,
                               fillcolor=comp_bgs[i % 2],
                               line=dict(width=0), layer="below"))

    # ── Layout Plotly ─────────────────────────────────────────────────
    sem_lbl   = f" · S{semester_filter}" if semester_filter and semester_filter != "all" else ""
    focus_lbl = ""
    if selected_node and selected_node in node_meta:
        nd   = node_meta[selected_node]
        tp   = {"competence": "Compétence", "ac": "AC", "module": "Module"}
        code = nd.get("code") or nd.get("id", "")
        focus_lbl = (f"  <span style='color:#7C3AED;font-weight:600'>"
                     f"Focus : {tp[nd['type']]} {code}</span>")

    n_c, n_a, n_m = len(comps), len(acs), len(modules)
    subtitle = (
        f"<span style='font-size:12px;color:#94A3B8'>"
        f"{n_c} compétences · {n_a} AC · {n_m} modules"
        f"{sem_lbl}{focus_lbl}</span>"
    )

    xr = ([min(x for x, _ in pos.values()) - 12,
           max(x for x, _ in pos.values()) + 10] if pos else [-20, 20])

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(
            text=f"<b>Graphe pédagogique APC</b><br>{subtitle}",
            font=dict(size=16, color="#0F172A", family="Segoe UI, sans-serif"),
            x=0.01, y=0.99
        ),
        height=820,
        paper_bgcolor="#F8FAFB", plot_bgcolor="#FFFFFF",
        showlegend=True,
        legend=dict(orientation="v", x=1.01, y=0.98,
                    bgcolor="rgba(255,255,255,0.92)",
                    bordercolor="#E4E9F0", borderwidth=1,
                    font=dict(size=12, color="#374151"),
                    itemsizing="constant"),
        margin=dict(l=160, r=150, t=85, b=60),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=xr),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=[-1.5, 13.0]),
        shapes=shapes,
        clickmode="event",
        hovermode="closest"
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  HEATMAPS
# ══════════════════════════════════════════════════════════════════════════════

def create_global_heatmap(rows):
    if not rows:
        return empty_figure("Aucun lien module-compétence détecté")
    sems  = sorted({r["semestre"] for r in rows if r["semestre"]}, key=sort_semester)
    comps = sorted({r["competence_code"] for r in rows if r["competence_code"]})
    z, hover = [], []
    for s in sems:
        line, h = [], []
        for c in comps:
            n = len({r["module_id"] for r in rows
                     if r["semestre"] == s and r["competence_code"] == c})
            line.append(n)
            h.append(f"<b>S{s} × {c}</b><br>{n} module(s)")
        z.append(line); hover.append(h)
    fig = go.Figure(go.Heatmap(
        z=z, x=comps, y=[f"S{s}" for s in sems],
        colorscale="Blues", hoverongaps=False,
        hovertext=hover, hoverinfo="text",
        colorbar=dict(title=dict(text="Modules", side="right"), thickness=14)
    ))
    fig.update_layout(
        title=dict(text="<b>Heatmap globale</b> — Semestres × Compétences",
                   font=dict(size=15, color="#0F172A")),
        xaxis_title="Compétences", yaxis_title="Semestres",
        height=560, paper_bgcolor="#F8FAFB", plot_bgcolor="#FFFFFF",
        margin=dict(l=80, r=80, t=70, b=80)
    )
    return fig


def create_semester_heatmap(rows, semester):
    sr = [r for r in rows if str(r["semestre"]) == str(semester)]
    if not sr:
        return empty_figure(f"Aucune donnée pour S{semester}")
    mods  = sorted({r["module_id"] for r in sr if r["module_id"]})
    comps = sorted({r["competence_code"] for r in sr if r["competence_code"]})
    z = [[len([r for r in sr if r["module_id"] == m and r["competence_code"] == c])
          for c in comps] for m in mods]
    fig = go.Figure(go.Heatmap(
        z=z, x=comps, y=mods, colorscale="Blues", hoverongaps=False,
        colorbar=dict(title=dict(text="Liens", side="right"), thickness=14)
    ))
    fig.update_layout(
        title=dict(text=f"<b>Heatmap S{semester}</b> — Modules × Compétences",
                   font=dict(size=15, color="#0F172A")),
        xaxis_title="Compétences", yaxis_title="Modules",
        height=700, paper_bgcolor="#F8FAFB", plot_bgcolor="#FFFFFF",
        margin=dict(l=120, r=80, t=70, b=80)
    )
    return fig


def create_module_heatmap(rows, module_id):
    mr = [r for r in rows if r["module_id"] == module_id]
    if not mr:
        return empty_figure(f"Aucune donnée pour {module_id}")
    acquis = sorted({r["acquis_id"] or "Non renseigné" for r in mr})
    comps  = sorted({r["competence_code"] for r in mr if r["competence_code"]})
    z = [[len([r for r in mr
               if (r["acquis_id"] or "Non renseigné") == a and r["competence_code"] == c])
          for c in comps] for a in acquis]
    fig = go.Figure(go.Heatmap(
        z=z, x=comps, y=acquis, colorscale="Blues", hoverongaps=False,
        colorbar=dict(title=dict(text="Liens", side="right"), thickness=14)
    ))
    fig.update_layout(
        title=dict(text=f"<b>Module {module_id}</b> — Acquis × Compétences",
                   font=dict(size=15, color="#0F172A")),
        xaxis_title="Compétences", yaxis_title="Acquis",
        height=650, paper_bgcolor="#F8FAFB", plot_bgcolor="#FFFFFF",
        margin=dict(l=120, r=80, t=70, b=80)
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT DASH
# ══════════════════════════════════════════════════════════════════════════════

programme_options = get_programme_options()
default_programme = programme_options[0]["value"] if programme_options else None

forested_visualisations_layout = html.Div([

    html.Div([
        html.Div([
            html.Span("🔗", style={"fontSize": "34px", "marginRight": "12px"}),
            html.Div([
                html.H1("Exploration des formations", style={
                    "color": "#0F172A", "fontSize": "28px", "fontWeight": "700",
                    "margin": "0 0 3px", "fontFamily": "Segoe UI, sans-serif"}),
                html.P(
                    "Relations entre compétences, apprentissages critiques et modules.",
                    style={"color": "#64748B", "fontSize": "13px", "margin": "0"})
            ])
        ], style={"display": "flex", "alignItems": "center"})
    ], style={"marginBottom": "18px"}),

    html.Div([
        html.Div([
            html.Label("Formation", style=LABEL_STYLE),
            dcc.Dropdown(id="programme-selector", options=programme_options,
                         value=default_programme, clearable=False,
                         style={"fontSize": "14px"})
        ], style={"width": "34%", "minWidth": "200px"}),

        html.Div([
            html.Label("Semestre", style=LABEL_STYLE),
            dcc.Dropdown(id="semester-filter",
                         options=[{"label": "Tous", "value": "all"}],
                         value="all", clearable=False,
                         style={"fontSize": "14px"})
        ], style={"width": "16%", "minWidth": "120px"}),

        html.Div([
            html.Label("Vue", style=LABEL_STYLE),
            dcc.RadioItems(id="visualisation-mode",
                options=[{"label": "  Graphe",  "value": "graph"},
                         {"label": "  Heatmap", "value": "heatmap"}],
                value="graph", inline=True,
                inputStyle={"marginRight": "4px"},
                labelStyle={"marginRight": "16px", "fontSize": "13px", "color": "#374151"})
        ], style={"display": "flex", "flexDirection": "column"}),

        html.Div([
            html.Label("Niveaux AC", style=LABEL_STYLE),
            html.Div([
                html.Span([
                    html.Span(style={"width": "9px", "height": "9px", "borderRadius": "50%",
                                     "backgroundColor": col, "display": "inline-block",
                                     "marginRight": "4px"}),
                    html.Span(lbl, style={"fontSize": "11px", "color": "#374151"})
                ], style={"display": "flex", "alignItems": "center", "marginRight": "12px"})
                for col, lbl in [(C_AC_N1, "N1 Débutant"),
                                 (C_AC_N2, "N2 Intermédiaire"),
                                 (C_AC_N3, "N3 Avancé")]
            ], style={"display": "flex", "flexWrap": "wrap"})
        ]),

        html.Div([
            html.Label("\u00a0", style={**LABEL_STYLE, "visibility": "hidden"}),
            html.Button("✕ Réinitialiser", id="visualisation-back", n_clicks=0,
                style={"height": "34px", "padding": "0 14px",
                       "backgroundColor": "#F1F5F9", "color": "#475569",
                       "border": "1px solid #CBD5E1", "borderRadius": "6px",
                       "cursor": "pointer", "fontSize": "12px", "fontWeight": "600"})
        ], style={"display": "flex", "flexDirection": "column"}),

    ], style={**CARD_STYLE, "display": "flex", "alignItems": "flex-end",
               "flexWrap": "wrap", "gap": "16px"}),

    dcc.Store(id="selected-forest-node"),
    dcc.Store(id="vis-rows-store"),
    dcc.Store(id="visualisation-state",
              data={"level": 0, "semester": None, "module": None}),
    html.Div(id="vis-focus-panel"),

    html.Div([
        dcc.Graph(id="forest-graph",
            config={"displayModeBar": True, "displaylogo": False,
                    "scrollZoom": True,
                    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"]})
    ], style=CARD_STYLE)

], style=PAGE_STYLE)


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def register_callbacks(app):

    @app.callback(
        Output("vis-rows-store", "data"),
        Output("semester-filter", "options"),
        Input("programme-selector", "value")
    )
    def load_rows(selected_programme):
        comp_data, curr_data = get_selected_data(selected_programme)
        rows = build_visualisation_rows(comp_data, curr_data)
        sems = sorted(
            {r["semestre"] for r in rows if r.get("semestre") is not None},
            key=sort_semester
        )
        opts = [{"label": "Tous les semestres", "value": "all"}] + [
            {"label": f"Semestre {s}", "value": str(s)} for s in sems
        ]
        return rows, opts

    @app.callback(
        Output("forest-graph", "figure"),
        Output("selected-forest-node", "data"),
        Input("vis-rows-store", "data"),
        Input("forest-graph", "clickData"),
        Input("semester-filter", "value"),
        Input("visualisation-mode", "value"),
        Input("visualisation-back", "n_clicks"),
        State("selected-forest-node", "data"),
    )
    def update_graph(stored_rows, click_data, semester, mode, n_reset, selected_node):
        if not stored_rows:
            return empty_figure("Aucune donnée disponible"), None

        triggered = ctx.triggered_id
        if triggered in ["visualisation-back", "programme-selector",
                         "semester-filter", "visualisation-mode"]:
            selected_node = None

        if mode == "heatmap":
            return (create_semester_heatmap(stored_rows, semester)
                    if semester and semester != "all"
                    else create_global_heatmap(stored_rows)), None

        if triggered == "forest-graph" and click_data:
            clicked = click_data["points"][0].get("customdata")
            selected_node = None if clicked == selected_node else clicked

        return create_forest_graph(stored_rows, selected_node, semester), selected_node

    @app.callback(
        Output("vis-focus-panel", "children"),
        Input("selected-forest-node", "data"),
        State("vis-rows-store", "data"),
    )
    def update_panel(selected_node, stored_rows):
        if not selected_node or not stored_rows:
            return html.Div()

        comps_m, acs_m, mods_m = {}, {}, {}
        for r in stored_rows:
            cc  = r.get("competence_code")
            ac  = r.get("ac_code")
            mc  = r.get("module_code")
            sem = r.get("semestre")
            mk  = f"{mc}::{sem}" if (mc and sem is not None) else mc
            if cc: comps_m[cc] = r.get("competence_name", "")
            if ac and ac not in acs_m:
                acs_m[ac] = {"niveau": r.get("niveau"),
                              "desc": r.get("ac_description", ""), "comp": cc}
            if mk and mk not in mods_m:
                mods_m[mk] = {"name": r.get("module_name", ""),
                               "code": mc or ""}

        def _mk(r):
            mc  = r.get("module_code")
            sem = r.get("semestre")
            return f"{mc}::{sem}" if (mc and sem is not None) else mc

        if selected_node.startswith("COMP::"):
            code    = selected_node[6:]
            ac_set  = sorted([a for a, m in acs_m.items() if m["comp"] == code])
            mod_set = sorted({_mk(r) for r in stored_rows
                              if r.get("competence_code") == code and r.get("module_code")})
            border, title = C_COMP, f"Compétence : {code}"
            body = [
                _p(comps_m.get(code, ""), italic=True),
                _sec(f"📌 {len(ac_set)} AC", "#7C3AED"),
                _tags([(a, "#EDE9FE", "#5B21B6") for a in ac_set]),
                _sec(f"📦 {len(mod_set)} modules", C_MODULE),
                _tags([(mods_m.get(m, {}).get("code", m), "#DBEAFE", "#1E3A8A") for m in mod_set]),
            ]

        elif selected_node.startswith("AC::"):
            code = selected_node[4:]
            meta = acs_m.get(code, {})
            niv  = meta.get("niveau"); col = _niveau_color(niv)
            mods = sorted({_mk(r) for r in stored_rows
                           if r.get("ac_code") == code and r.get("module_code")})
            border, title = col, f"AC : {code}"
            body = [
                html.Span(f"Niveau {niv} — {_niveau_label(niv)}",
                          style={"backgroundColor": col, "color": "white",
                                 "borderRadius": "4px", "padding": "2px 10px",
                                 "fontSize": "11px", "display": "inline-block",
                                 "marginBottom": "8px"}),
                _p(meta.get("desc", ""), italic=True),
                _sec("🎯 Compétence", C_COMP),
                _tags([(meta.get("comp", ""), "#EDE9FE", "#5B21B6")]),
                _sec(f"📦 {len(mods)} modules", C_MODULE),
                _tags([(mods_m.get(m, {}).get("code", m), "#DBEAFE", "#1E3A8A") for m in mods]),
            ]

        elif selected_node.startswith("MOD::"):
            mk    = selected_node[5:]   # "module_code::semestre"
            meta  = mods_m.get(mk, {})
            comps_ = sorted({r["competence_code"] for r in stored_rows
                             if _mk(r) == mk and r.get("competence_code")})
            acs_   = sorted({r["ac_code"] for r in stored_rows
                             if _mk(r) == mk and r.get("ac_code")})
            border, title = C_MODULE, f"Module : {meta.get('code', mk)}"
            body = [
                _p(meta.get("name", ""), italic=True),
                _sec(f"🎯 {len(comps_)} compétence(s)", C_COMP),
                _tags([(c, "#EDE9FE", "#5B21B6") for c in comps_]),
                _sec(f"📌 {len(acs_)} AC", "#4B5563"),
                _tags([(a, "#F3F4F6", "#374151") for a in acs_]),
            ]
        else:
            return html.Div()

        return html.Div([html.Div([
            html.Div([
                html.Span(style={"width": "10px", "height": "10px", "borderRadius": "2px",
                                  "backgroundColor": border, "display": "inline-block",
                                  "marginRight": "8px"}),
                html.Span(title, style={"fontWeight": "700", "fontSize": "14px",
                                        "color": "#0F172A"})
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "10px"}),
            *body,
            html.P("Cliquez sur le même nœud ou ✕ Réinitialiser pour effacer.",
                   style={"fontSize": "11px", "color": "#94A3B8",
                          "margin": "12px 0 0", "fontStyle": "italic"})
        ], style={
            "backgroundColor": "#FFFFFF",
            "border": "1px solid #E2E8F0",
            "borderLeft": f"4px solid {border}",
            "borderRadius": "8px",
            "padding": "14px 18px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.05)"
        })], style={"marginBottom": "14px"})


def _p(text, italic=False):
    if not text: return html.Div()
    s = {"color": "#6B7280", "fontSize": "12px", "margin": "0 0 8px"}
    if italic: s["fontStyle"] = "italic"
    return html.P(text, style=s)


def _sec(label, color):
    return html.P(label, style={"fontWeight": "600", "color": color,
                                  "fontSize": "12px", "margin": "8px 0 5px"})


def _tags(items):
    return html.Div([
        html.Span(t, style={"backgroundColor": bg, "color": fc, "borderRadius": "4px",
                             "padding": "2px 7px", "fontSize": "11px",
                             "marginRight": "4px", "marginBottom": "4px",
                             "display": "inline-block"})
        for t, bg, fc in items
    ], style={"display": "flex", "flexWrap": "wrap", "marginBottom": "4px"})