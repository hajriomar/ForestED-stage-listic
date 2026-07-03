"""
forested_sunburst_semester.py — ForestED : Sunburst distribution semestrielle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Visualisation : Centre → Semestre → Module → AC

Principe fondateur
──────────────────
Vue orthogonale au Sunburst APC :
  • APC      : Compétence → Niveau → AC → Module  (axe pédagogique)
  • Semestre : Semestre → Module → AC              (axe temporel)

Règles de dataviz structurantes
────────────────────────────────
1. Zéro duplication de module
   Un module est assigné à UN SEUL semestre — celui où il apparaît le plus
   souvent dans les données. En cas d'ex-aequo : le semestre le plus petit.
   Comme le module est le nœud intermédiaire (et non plus accroché à un AC
   précis), un seul semestre suffit à le placer sans ambiguïté.
   Ses AC réels apparaissent tous en enfants directs (anneau externe) — un
   AC peut donc se répéter sous plusieurs modules, ce qui est normal et
   attendu (un même AC est souvent travaillé par plusieurs modules).

2. Encodage couleur sémantique — SANS AUCUNE COULEUR INVENTÉE
   • Semestre  → DÉGRADÉ DE GRIS NEUTRE (zéro teinte, uniquement la
                 luminosité varie), du plus clair (premier semestre) au
                 plus foncé (dernier semestre). Volontairement achromatique
                 pour ne jamais entrer en concurrence visuelle avec les
                 8 teintes de PALETTE_COMPETENCES : le semestre encode le
                 TEMPS, un axe structurel, pas une compétence.
   • Module    → NEUTRE (une seule couleur claire fixe). Plotly ne permet
                 pas de peindre un seul arc avec plusieurs couleurs : la
                 "vraie" composition du module (quelles compétences, dans
                 quelles proportions) est donc portée par l'anneau AC juste
                 à côté, qui est le prolongement direct du module. Chaque
                 AC y garde sa vraie couleur (compétence × niveau, aucun
                 mélange) et son poids réel (1 AC = 1 part) : l'ensemble
                 des arcs AC d'un module forme visuellement, collé à sa
                 bordure, exactement le "camembert par AC, au pourcentage
                 réel" demandé — sans ajouter de niveau de hiérarchie et
                 sans jamais fabriquer de teinte qui n'existe nulle part
                 ailleurs.
   • AC        → couleur de COMPÉTENCE × NIVEAU (root/n1/n2/n3 selon le
                 niveau réel de l'AC). C'est cet anneau qui porte la vraie
                 information de composition d'un module, en pourcentage
                 exact (via branchvalues="total" sur les valeurs réelles).

Ce fichier n'importe AUCUN composant Dash.
Il exporte uniquement des fonctions de données et de figure Plotly.
"""

import re
from collections import Counter

import plotly.graph_objects as go

from forested_palette import PALETTE_COMPETENCES


# ══════════════════════════════════════════════════════════════════════════════
#  PALETTES
# ══════════════════════════════════════════════════════════════════════════════

ROOT_COLOR = "#0F172A"

# Anneau "Semestre" : dégradé de GRIS NEUTRE, du plus clair (premier
# semestre) au plus foncé (dernier). Échelle "zinc" — volontairement
# achromatique (saturation ≈ 0) pour ne jamais entrer en compétition avec
# les 8 teintes saturées de PALETTE_COMPETENCES (dont aucune n'est un vrai
# gris neutre). Le temps se lit donc comme un axe structurel, distinct par
# nature — pas juste par teinte — de l'axe pédagogique (compétence).
SEMESTER_RING_COLORS = [
    "#E4E4E7",   # S1 — le plus clair
    "#D4D4D8",   # S2
    "#A1A1AA",   # S3
    "#71717A",   # S4
    "#52525B",   # S5
    "#3F3F46",   # S6
    "#27272A",   # S7
    "#18181B",   # S8 — le plus foncé
]

# Anneau "Module" : couleur neutre fixe, identique pour tous les modules.
# Aucune teinte inventée / mélangée — la vraie composition (par compétence,
# en pourcentage réel) se lit sur l'anneau AC juste à côté (voir docstring).
MODULE_NEUTRAL_COLOR = "#EDEFF3"

# Couleur de repli pour un AC sans compétence renseignée.
UNKNOWN_COLOR = "#94A3B8"


def _hex_to_rgb(hex_color):
    if not hex_color:
        return 255, 255, 255
    h = str(hex_color).strip().lstrip("#")
    if len(h) != 6:
        return 255, 255, 255
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return 255, 255, 255


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITAIRES (réimplantés ici pour éviter les imports circulaires)
# ══════════════════════════════════════════════════════════════════════════════

def _clean(value, default=""):
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _shorten(text, max_len=68):
    text = _clean(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _safe_int(value, default=99):
    try:
        return int(value)
    except Exception:
        return default


def _sort_semester_key(sem):
    """Tri numérique des semestres (gère '1', 'S1', 1)."""
    try:
        return int(str(sem).replace("S", "").strip())
    except Exception:
        return 999


def _relative_luminance(hex_color):
    r, g, b = _hex_to_rgb(hex_color)
    def _lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _text_color_for_bg(bg_color):
    """Blanc sur fond sombre, foncé sur fond clair (seuil 0.25)."""
    return "#FFFFFF" if _relative_luminance(bg_color) < 0.25 else "#0F172A"


def _extract_ac_suffix(ac_code):
    match = re.search(r"(AC\d+)$", str(ac_code))
    return match.group(1) if match else _clean(ac_code, ac_code)


def _extract_ac_label(ac_code, description, max_len=80):
    suffix = _extract_ac_suffix(ac_code)
    desc = _clean(description)
    if not desc or desc == "Non renseigné":
        return suffix
    return f"{suffix} : {_shorten(desc, max_len)}"


def _module_display_label(code, name, max_len=15):
    name = _clean(name)
    if not name or name == code:
        return _shorten(code, max_len)
    return _shorten(name, max_len)


def _format_semestre(value):
    if value is None or value == "all":
        return "Tous les semestres"
    text = str(value)
    return text if text.upper().startswith("S") else f"S{text}"


# ══════════════════════════════════════════════════════════════════════════════
#  LOGIQUE DE DÉDUPLICATION DES MODULES
# ══════════════════════════════════════════════════════════════════════════════

def _build_module_semester_assignment(rows):
    """
    Pour chaque module, détermine son unique semestre d'assignation.

    Règle : le semestre où le module apparaît le plus souvent dans les
    données. En cas d'ex-aequo, le semestre le plus petit (numériquement)
    l'emporte.

    Retourne :
        assignments : dict module_code → semestre
        module_meta : dict module_code → {name, comps, acs}
    """
    occurrence_counts = {}   # module_code → {semestre: count}
    module_meta = {}         # module_code → {name, comps, acs}

    for row in rows or []:
        mc = _clean(row.get("module_code") or row.get("module_id"))
        if not mc:
            continue

        sem = row.get("semestre")
        ac = _clean(row.get("ac_code"))
        comp = _clean(row.get("competence_code"))

        if mc not in occurrence_counts:
            occurrence_counts[mc] = {}
            module_meta[mc] = {
                "name": _clean(row.get("module_name"), mc),
                "comps": set(),
                "acs": set(),
            }

        if row.get("module_name"):
            module_meta[mc]["name"] = _clean(row["module_name"], mc)

        if comp:
            module_meta[mc]["comps"].add(comp)
        if ac:
            module_meta[mc]["acs"].add(ac)

        if sem is not None:
            occurrence_counts[mc][sem] = occurrence_counts[mc].get(sem, 0) + 1

    assignments = {}
    for mc, counts in occurrence_counts.items():
        if not counts:
            continue
        # Tri : d'abord par count décroissant, puis semestre le plus petit.
        primary = max(
            counts.keys(),
            key=lambda s: (counts[s], -_sort_semester_key(s))
        )
        assignments[mc] = primary

    return assignments, module_meta


# ══════════════════════════════════════════════════════════════════════════════
#  COULEUR DES NŒUDS
# ══════════════════════════════════════════════════════════════════════════════

def _competence_color_scheme(comp_code, competence_order):
    """Retourne le schéma de couleurs d'une compétence."""
    try:
        idx = competence_order.index(comp_code)
    except ValueError:
        idx = 0
    return PALETTE_COMPETENCES[idx % len(PALETTE_COMPETENCES)]


def _ac_color(comp_code, niveau, competence_order):
    """Couleur d'un AC : compétence × niveau (N1=clair, N2=moyen, N3=foncé)."""
    if not comp_code:
        return UNKNOWN_COLOR
    scheme = _competence_color_scheme(comp_code, competence_order)
    niv = _safe_int(niveau, default=2)
    if niv == 1:
        return scheme["n1"]
    if niv == 3:
        return scheme["n3"]
    return scheme["n2"]


# ══════════════════════════════════════════════════════════════════════════════
#  CONSTRUCTION DES NŒUDS DU SUNBURST
# ══════════════════════════════════════════════════════════════════════════════

def build_semester_nodes(rows, competence_order=None, root_label="Semestres"):
    """
    Construit la structure Sunburst : Centre → Semestre → Module → AC.

    Points clés :
    - Chaque module apparaît EXACTEMENT UNE FOIS (voir
      _build_module_semester_assignment).
    - Un même AC peut apparaître sous plusieurs modules (normal : un AC est
      souvent travaillé par plusieurs modules).
    - Les IDs sont préfixés pour éviter les collisions avec l'APC sunburst.
    - Le module n'a pas de couleur "de compétence" : c'est l'anneau AC,
      juste après, qui porte la vraie composition (couleur réelle de
      chaque AC, taille = sa part réelle parmi les AC du module).

    Format des IDs :
        root     : "ROOT::SEM"
        semestre : "SEM::{semestre}"
        module   : "MOD::SEM::{semestre}::{module_code}"
        ac       : "AC::SEM::{semestre}::{module_code}::{ac_code}"
    """
    if competence_order is None:
        competence_order = sorted({
            _clean(r.get("competence_code"))
            for r in rows or []
            if r.get("competence_code")
        })

    # ── Pré-calcul : info des ACs ──────────────────────────────────────────

    ac_info = {}   # ac_code → {competence_code, description, niveau}
    for row in rows or []:
        ac = _clean(row.get("ac_code"))
        comp = _clean(row.get("competence_code"))
        if not ac or not comp:
            continue
        if ac not in ac_info:
            ac_info[ac] = {
                "competence_code": comp,
                "description": _clean(row.get("ac_description"), ac),
                "niveau": row.get("niveau"),   # N1 / N2 / N3 du référentiel
            }
        if row.get("ac_description"):
            ac_info[ac]["description"] = _clean(row["ac_description"], ac)
        if row.get("niveau") is not None and ac_info[ac]["niveau"] is None:
            ac_info[ac]["niveau"] = row.get("niveau")

    # ── Assignation unique des modules à un semestre ───────────────────────

    assignments, module_meta = _build_module_semester_assignment(rows)

    # ── Semestres utilisés (triés numériquement) ───────────────────────────

    used_semesters = sorted(
        {sem for sem in assignments.values() if sem is not None},
        key=_sort_semester_key
    )
    semester_to_index = {sem: i for i, sem in enumerate(used_semesters)}

    # ── Construction des nœuds ─────────────────────────────────────────────

    root_id = "ROOT::SEM"
    node_parent   = {root_id: ""}
    node_label    = {root_id: root_label}
    node_value    = {}
    node_hover    = {root_id: f"<b>{root_label}</b><br>Distribution temporelle"}
    node_color    = {root_id: ROOT_COLOR}
    node_type_map = {root_id: "root"}  # id → type ("root" | "semester" | "module" | "ac")

    # Modules par semestre (pour les compteurs de hover du nœud semestre)
    modules_by_sem = {}
    for mc, sem in assignments.items():
        modules_by_sem.setdefault(sem, set()).add(mc)

    # Nœuds semestre
    for sem in used_semesters:
        sem_id = f"SEM::{sem}"
        sem_modules = modules_by_sem.get(sem, set())
        sem_acs = set()
        sem_comps = set()
        for mc in sem_modules:
            sem_acs |= module_meta.get(mc, {}).get("acs", set())
        for ac in sem_acs:
            comp = ac_info.get(ac, {}).get("competence_code")
            if comp:
                sem_comps.add(comp)

        node_parent[sem_id] = root_id
        node_label[sem_id] = _format_semestre(sem)
        node_hover[sem_id] = (
            f"<b>Semestre {sem}</b><br>"
            f"<b>Modules :</b> {len(sem_modules)}<br>"
            f"<b>AC couverts :</b> {len(sem_acs)}<br>"
            f"<b>Compétences :</b> {len(sem_comps)}"
        )
        node_type_map[sem_id] = "semester"
        sem_idx = semester_to_index.get(sem, 0)
        node_color[sem_id] = SEMESTER_RING_COLORS[sem_idx % len(SEMESTER_RING_COLORS)]

    # Nœuds module (enfants directs du semestre)
    for mc, sem in sorted(assignments.items(), key=lambda kv: (_sort_semester_key(kv[1]), str(kv[0]))):
        sem_id = f"SEM::{sem}"
        module_id = f"MOD::SEM::{sem}::{mc}"

        meta = module_meta.get(mc, {})
        module_name = meta.get("name", mc)
        module_acs = sorted(meta.get("acs", set()))

        node_parent[module_id] = sem_id
        node_label[module_id] = _module_display_label(mc, module_name)
        node_type_map[module_id] = "module"
        node_color[module_id] = MODULE_NEUTRAL_COLOR

        if not module_acs:
            # Module sans AC connu : il devient sa propre feuille.
            node_value[module_id] = 1
            node_hover[module_id] = (
                f"<b>{module_name}</b><br>"
                f"<b>Code :</b> {mc}<br>"
                f"<b>Semestre :</b> {sem}<br>"
                f"<b>AC liés :</b> 0"
            )
            continue

        # Répartition par compétence — affichée en hover seulement (texte),
        # jamais transformée en couleur : la vraie couleur/pourcentage se
        # voit directement sur l'anneau AC juste à côté.
        comp_counts = Counter(
            ac_info.get(ac, {}).get("competence_code") or "Non renseigné"
            for ac in module_acs
        )
        total_acs = len(module_acs)
        breakdown_txt = ", ".join(
            f"{comp} : {n} AC ({round(100 * n / total_acs)}%)"
            for comp, n in comp_counts.most_common()
        )

        node_hover[module_id] = (
            f"<b>{module_name}</b><br>"
            f"<b>Code :</b> {mc}<br>"
            f"<b>Semestre :</b> {sem}<br>"
            f"<b>AC liés :</b> {total_acs}<br>"
            f"<b>Répartition par compétence :</b> {breakdown_txt}"
        )

        # Nœuds AC (feuilles, enfants directs du module). C'est cet anneau
        # qui affiche, en vraies couleurs et en vrai pourcentage (1 AC = sa
        # part réelle), la composition du module.
        for ac in module_acs:
            ac_id = f"AC::SEM::{sem}::{mc}::{ac}"
            info = ac_info.get(ac, {})
            comp = info.get("competence_code", "")
            desc = info.get("description", ac)
            niveau_ac = info.get("niveau")

            node_parent[ac_id] = module_id
            node_label[ac_id] = _extract_ac_suffix(ac)
            node_value[ac_id] = 1
            node_hover[ac_id] = (
                f"<b>{_extract_ac_label(ac, desc, max_len=80)}</b><br>"
                f"<b>Compétence :</b> {comp}<br>"
                f"<b>Niveau :</b> {niveau_ac if niveau_ac is not None else '—'}<br>"
                f"<b>Module :</b> {module_name} ({mc})<br>"
                f"<b>Semestre :</b> {sem}"
            )
            node_type_map[ac_id] = "ac"
            node_color[ac_id] = _ac_color(comp, niveau_ac, competence_order)

    # ── Agrégation des valeurs pour les nœuds non-feuilles ─────────────────

    for node_id in reversed(list(node_parent.keys())):
        if node_id in node_value:
            continue
        children = [c for c, p in node_parent.items() if p == node_id]
        node_value[node_id] = sum(node_value.get(c, 0) for c in children)

    # ── Couleurs ───────────────────────────────────────────────────────────

    ids = list(node_parent.keys())
    colors = [node_color.get(node_id, UNKNOWN_COLOR) for node_id in ids]
    text_colors = [_text_color_for_bg(c) for c in colors]

    return {
        "ids": ids,
        "labels": [node_label[node_id] for node_id in ids],
        "parents": [node_parent[node_id] for node_id in ids],
        "values": [node_value.get(node_id, 0) for node_id in ids],
        "hovertexts": [node_hover.get(node_id, node_label[node_id]) for node_id in ids],
        "colors": colors,
        "text_colors": text_colors,
        "node_type_map": node_type_map,
        "used_semesters": used_semesters,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  FIGURE PLOTLY
# ══════════════════════════════════════════════════════════════════════════════

def create_semester_sunburst_figure(
    rows,
    selected_programme=None,
    semester="all",
    competence_order=None,
):
    """
    Crée la figure Plotly Sunburst semestrielle.

    Si aucun module n'est assigné, retourne une figure vide.
    """
    if not rows:
        return _empty_figure("Aucune donnée disponible pour la vue semestrielle")

    if competence_order is None:
        competence_order = sorted({
            _clean(r.get("competence_code"))
            for r in rows
            if r.get("competence_code")
        })

    # Label du centre : nom du programme
    root_label = "Semestres"
    if selected_programme:
        root_label = selected_programme.split("::")[-1]

    data = build_semester_nodes(rows, competence_order=competence_order, root_label=root_label)

    # Minimum viable : root + au moins un enfant
    if len(data["ids"]) <= 1:
        return _empty_figure("Aucun module trouvé pour cette configuration")

    title_suffix = _format_semestre(semester)
    n_modules = sum(1 for entry in data["node_type_map"].values() if entry == "module")
    n_sems = len(data["used_semesters"])

    subtitle = (
        f"Semestres → modules → AC · {title_suffix} · "
        f"{n_modules} modules uniques · {n_sems} semestre(s)"
    )

    fig = go.Figure(
        go.Sunburst(
            ids=data["ids"],
            labels=data["labels"],
            parents=data["parents"],
            values=data["values"],
            branchvalues="total",
            sort=False,
            marker=dict(
                colors=data["colors"],
                line=dict(color="#FFFFFF", width=1.4),
            ),
            insidetextfont=dict(
                color=data["text_colors"],
                size=11,
            ),
            hovertext=data["hovertexts"],
            hoverinfo="text",
            insidetextorientation="radial",
            maxdepth=4,
        )
    )

    fig.update_traces(
        textinfo="label",
        hoverlabel=dict(
            bgcolor="#0F172A",
            font=dict(color="#FFFFFF", size=12),
        ),
    )

    fig.update_layout(
        title=dict(
            text=(
                "<b>Distribution semestrielle</b><br>"
                f"<span style='font-size:12px;color:#64748B'>{subtitle}</span>"
            ),
            x=0.02,
            y=0.98,
            font=dict(size=18, color="#0F172A", family="Segoe UI, sans-serif"),
        ),
        height=940,
        paper_bgcolor="#F8FAFB",
        margin=dict(t=80, l=20, r=20, b=20),
        uniformtext=dict(minsize=8, mode="hide"),
        uirevision=f"semester-{selected_programme}-{semester}",
    )

    return fig


def _empty_figure(message="Aucune donnée"):
    """Figure vide utilisée quand il n'y a rien à afficher."""
    fig = go.Figure()
    fig.add_annotation(
        text=message, x=0.5, y=0.5,
        xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=16, color="#94A3B8"),
    )
    fig.update_layout(
        height=600,
        paper_bgcolor="#F8FAFB",
        plot_bgcolor="#F8FAFB",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  DONNÉES POUR LE PANNEAU DÉTAIL (utilisé depuis forested_sunburst.py)
# ══════════════════════════════════════════════════════════════════════════════

def get_semester_node_info(rows, node_id):
    """
    Retourne les informations sur un nœud cliqué dans le sunburst semestriel.

    Utilisé par forested_sunburst.py pour construire le panneau détail.
    Renvoie un dict {type, ...} ou None si le nœud n'est pas géré.

    Types retournés : "root", "semester", "module", "ac"
    """
    if not node_id:
        return None

    rows = rows or []

    # ── Root ──────────────────────────────────────────────────────────────
    if node_id == "ROOT::SEM":
        all_mods = {_clean(r.get("module_code") or r.get("module_id")) for r in rows if r.get("module_code") or r.get("module_id")}
        all_acs = {_clean(r.get("ac_code")) for r in rows if r.get("ac_code")}
        all_comps = {_clean(r.get("competence_code")) for r in rows if r.get("competence_code")}
        all_sems = {r.get("semestre") for r in rows if r.get("semestre") is not None}
        return {
            "type": "root",
            "modules": all_mods,
            "acs": all_acs,
            "competences": all_comps,
            "semestres": all_sems,
        }

    # ── Semestre ──────────────────────────────────────────────────────────
    if node_id.startswith("SEM::"):
        sem = node_id[5:]
        sem_rows = [r for r in rows if str(r.get("semestre")) == str(sem)]
        mods = {_clean(r.get("module_code") or r.get("module_id")) for r in sem_rows if r.get("module_code") or r.get("module_id")}
        acs = {_clean(r.get("ac_code")) for r in sem_rows if r.get("ac_code")}
        comps = {_clean(r.get("competence_code")) for r in sem_rows if r.get("competence_code")}
        return {
            "type": "semester",
            "semestre": sem,
            "modules": mods,
            "acs": acs,
            "competences": comps,
        }

    # ── Module ────────────────────────────────────────────────────────────
    if node_id.startswith("MOD::SEM::"):
        # Format : "MOD::SEM::{sem}::{module_code}"
        rest = node_id[10:]                 # après "MOD::SEM::"
        parts = rest.split("::", 1)
        if len(parts) < 2:
            return None
        sem, mc = parts[0], parts[1]

        mod_rows = [
            r for r in rows
            if _clean(r.get("module_code") or r.get("module_id")) == mc
        ]
        module_name = next(
            (r.get("module_name", mc) for r in mod_rows if r.get("module_name")),
            mc
        )
        all_comps = sorted({_clean(r.get("competence_code")) for r in mod_rows if r.get("competence_code")})
        all_acs = sorted({_clean(r.get("ac_code")) for r in mod_rows if r.get("ac_code")})

        return {
            "type": "module",
            "semestre": sem,
            "module_code": mc,
            "module_name": _clean(module_name, mc),
            "all_competences": all_comps,
            "all_acs": all_acs,
        }

    # ── AC ────────────────────────────────────────────────────────────────
    if node_id.startswith("AC::SEM::"):
        # Format : "AC::SEM::{sem}::{module_code}::{ac_code}"
        rest = node_id[9:]                  # après "AC::SEM::"
        parts = rest.split("::", 2)
        if len(parts) < 3:
            return None
        sem, mc, ac = parts[0], parts[1], parts[2]

        ac_rows = [r for r in rows if _clean(r.get("ac_code")) == ac]
        desc = next((r.get("ac_description", "") for r in ac_rows if r.get("ac_description")), ac)
        comp = next((r.get("competence_code", "") for r in ac_rows if r.get("competence_code")), "")
        niveau = next((r.get("niveau") for r in ac_rows if r.get("niveau") is not None), None)

        mod_rows = [r for r in rows if _clean(r.get("module_code") or r.get("module_id")) == mc]
        module_name = next(
            (r.get("module_name", mc) for r in mod_rows if r.get("module_name")),
            mc
        )

        return {
            "type": "ac",
            "semestre": sem,
            "ac_code": ac,
            "description": _clean(desc, ac),
            "competence_code": _clean(comp),
            "niveau": niveau,
            "module_code": mc,
            "module_name": _clean(module_name, mc),
        }

    return None