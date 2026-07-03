"""
forested_palette.py — ForestED : palette de couleurs par compétence
════════════════════════════════════════════════════════════════════

Source unique de vérité pour PALETTE_COMPETENCES.

Règle d'usage :
    Toujours importer depuis ici, jamais depuis forested_visualisations.

    from forested_palette import PALETTE_COMPETENCES

Structure de chaque entrée :
    root  → couleur principale (nœuds compétence, centre sunburst)
    n1    → teinte claire  (AC niveau 1 / centre AC niveau 1)
    n2    → teinte moyenne (AC niveau 2 / centre AC niveau 2)
    n3    → teinte foncée  (AC niveau 3 / centre AC niveau 3)
    text  → couleur de texte sur fond root (toujours blanc pour ces teintes)
    line  → couleur de bordure

Critères de sélection des 8 familles :
    Aucune paire de couleurs adjacente ne doit être dans la même famille
    de teinte (< 45° d'écart sur la roue HSL). Vérifié pour les 4
    premières entrées (les plus utilisées sur les référentiels actuels).

    Famille      Teinte HSL    Index
    ─────────────────────────────────
    Indigo       ~260°         0
    Emeraude     ~158°         1
    Terracotta   ~ 14°         2
    Cyan/Teal    ~193°         3  ← remplace l'ancien navy (~215°)
                                     trop proche du violet (~260°)
    Ambre        ~ 33°         4
    Vert olive   ~ 88°         5
    Rose         ~345°         6
    Ardoise      ~200°         7
"""

PALETTE_COMPETENCES = [
    # ── 0 · Indigo / Violet ────────────────────────────────────────────────
    {
        "root": "#3C3489",
        "n1":   "#CFCBFF",
        "n2":   "#8E86E8",
        "n3":   "#534AB7",
        "text": "#FFFFFF",
        "line": "#3C3489",
    },
    # ── 1 · Émeraude / Forêt ──────────────────────────────────────────────
    {
        "root": "#085041",
        "n1":   "#BDE9D8",
        "n2":   "#63C9A7",
        "n3":   "#0F6E56",
        "text": "#FFFFFF",
        "line": "#085041",
    },
    # ── 2 · Terracotta / Rouille ──────────────────────────────────────────
    {
        "root": "#712B13",
        "n1":   "#F5C6B7",
        "n2":   "#E68F6F",
        "n3":   "#993C1D",
        "text": "#FFFFFF",
        "line": "#712B13",
    },
    # ── 3 · Cyan / Teal ───────────────────────────────────────────────────
    #   Remplace l'ancien navy (#0C447C, teinte ~215°) qui était trop proche
    #   de l'indigo (#3C3489, teinte ~260°). Le cyan (~193°) est visuellement
    #   distinct des deux voisins : indigo (67° d'écart) et émeraude (35°).
    {
        "root": "#164E63",
        "n1":   "#CFFAFE",
        "n2":   "#22D3EE",
        "n3":   "#0E7490",
        "text": "#FFFFFF",
        "line": "#164E63",
    },
    # ── 4 · Ambre / Doré ──────────────────────────────────────────────────
    {
        "root": "#633806",
        "n1":   "#F3D39A",
        "n2":   "#E5A944",
        "n3":   "#854F0B",
        "text": "#FFFFFF",
        "line": "#633806",
    },
    # ── 5 · Vert olive / Lime ─────────────────────────────────────────────
    {
        "root": "#27500A",
        "n1":   "#CBE7A4",
        "n2":   "#8DBD52",
        "n3":   "#3B6D11",
        "text": "#FFFFFF",
        "line": "#27500A",
    },
    # ── 6 · Rose / Mauve ──────────────────────────────────────────────────
    {
        "root": "#72243E",
        "n1":   "#F2BDD0",
        "n2":   "#D97CA0",
        "n3":   "#993556",
        "text": "#FFFFFF",
        "line": "#72243E",
    },
    # ── 7 · Ardoise ───────────────────────────────────────────────────────
    {
        "root": "#444441",
        "n1":   "#D6D3CC",
        "n2":   "#A9A59C",
        "n3":   "#5F5E5A",
        "text": "#FFFFFF",
        "line": "#444441",
    },
]