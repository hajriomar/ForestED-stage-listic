"""
forested_visualisations.py
──────────────────────────
Optimisations de performance appliquées :

AVANT  : 1 go.Scatter par arête  → ~5 000 traces → navigateur bloqué
APRÈS  : batching total           →       4 traces → rendu instantané

Technique : toutes les arêtes sont concaténées dans 3 listes (x, y, couleur)
avec `None` comme séparateur de segments. Plotly trace tout en un seul appel WebGL.
Les nœuds sont également regroupés en traces uniques par type (3 traces).
Total rendu : ~7 traces au lieu de ~5 400.

Autres bonnes pratiques appliquées :
- dcc.Store pour éviter de recalculer les données à chaque interaction
- Logique focus découplée du layout (calcul séparé)
- Aucun import inutilisé (networkx supprimé)
- Fonctions utilitaires factorisées et réutilisables
"""

from dash import html, dcc, Input, Output, State, ctx
import plotly.graph_objects as go
import re

from app_tools import load_processed_files, build_programmes_summary
from forested_palette import PALETTE_COMPETENCES


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
C_MODULE = "#1D4ED8"

# Arêtes — 2 niveaux : défaut visible, focus coloré
EDGE_DEFAULT_CA = "rgba(109,40,217,0.22)"
EDGE_DEFAULT_AM = "rgba(29,78,216,0.12)"
EDGE_FOCUS_CA = "rgba(109,40,217,0.90)"
EDGE_FOCUS_AM = "rgba(29,78,216,0.85)"

FADE_OP  = 0.09   # opacité noeuds non focalisés
EDGE_FADE = 0.06  # opacité arêtes non focalisées


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def get_competence_color_scheme(competence_code, comp_order):
    """
    Retourne la famille de couleurs associée à une compétence.
    Une compétence = une couleur principale + dégradés N1/N2/N3.
    """

    try:
        index = comp_order.index(competence_code)
    except ValueError:
        index = 0

    return PALETTE_COMPETENCES[index % len(PALETTE_COMPETENCES)]


def get_ac_color_from_competence(competence_code, niveau, comp_order):
    """
    Retourne la couleur d'un AC selon :
    - sa compétence parente,
    - son niveau de développement.
    """

    scheme = get_competence_color_scheme(
        competence_code,
        comp_order
    )

    try:
        niveau = int(niveau)
    except Exception:
        niveau = 1

    if niveau == 1:
        return scheme["n1"]

    if niveau == 2:
        return scheme["n2"]

    if niveau == 3:
        return scheme["n3"]

    return "#CBD5E1"

def _niveau_label(niveau):
    return {"1": "Débutant", "2": "Intermédiaire", "3": "Avancé"}.get(str(niveau), "–")

def sort_semester(value):
    try:
        return int(str(value).replace("S", ""))
    except Exception:
        return 999

def normalize_module_code(code):
    """
    Normalise les codes modules pour matcher :
    - Polytech : INFO501, DATA601, SHES901...
    - BUT : R1.01, SAE1.01
    - IDs longs : S1_COMMUN_R1_01, S3_MP_SAE3_41, S4_COMMUN_R_4_11
    """

    if not code:
        return None

    text = str(code).strip().upper()
    text = text.replace("SAÉ", "SAE")
    text = text.replace("-", "_")
    text = text.replace(" ", "_")

    # Cas BUT avec underscores :
    # S1_COMMUN_R1_01      -> R1.01
    # S1_COMMUN_SAE1_01    -> SAE1.01
    # S4_COMMUN_R_4_11     -> R4.11
    # S5_MPBS_R5_42        -> R5.42
    match = re.search(r"(SAE|R)_?([1-6])_?([0-9]{2})", text)
    if match:
        prefix = match.group(1)
        semester = match.group(2)
        number = match.group(3)
        return f"{prefix}{semester}.{number}"

    # Cas BUT déjà propre :
    # R1.01 / SAE1.01
    match = re.search(r"(SAE|R)([1-6])\.([0-9]{2})", text)
    if match:
        return f"{match.group(1)}{match.group(2)}.{match.group(3)}"

    # Cas Polytech :
    # INFO501 / DATA701 / SHES901
    match = re.search(r"[A-Z]{2,6}\d{3}", text)
    if match:
        return match.group(0)

    return text

def get_programme_options():
    datasets = load_processed_files()
    programmes = build_programmes_summary(datasets)
    # Trier : Polytech en premier, BUT ensuite, reste par ordre alpha
    def _sort_key(item):
        src = item["source"].lower()
        if src == "polytech": return 0
        if src == "but":      return 1
        return 2
    return [
        {"label": f"{item['source']} — {item['programme']}",
         "value": f"{item['source']}::{item['programme']}"}
        for item in sorted(programmes, key=_sort_key)
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
    Itère sur tous les éléments pédagogiques du curriculum
    en supportant :

    1. Ancien modèle :
       periode -> unites_enseignement -> elements_pedagogiques

    2. Nouveau modèle :
       periode -> groupes_elements_pedagogiques -> elements_pedagogiques

    3. Nouveau modèle avec options :
       periode -> groupes_elements_pedagogiques
              -> groupes_elements_pedagogiques
              -> elements_pedagogiques
    """

    for periode in programme.get("periodes", []):
        semestre = (
            periode.get("numero")
            or periode.get("semestre")
            or periode.get("id")
        )

        # ==========================================================
        # CAS ANCIEN MODELE POLYTECH
        # periode -> unites_enseignement -> elements_pedagogiques
        # ==========================================================

        for ue in periode.get("unites_enseignement", []):
            for element in ue.get("elements_pedagogiques", []):
                yield {
                    "periode": periode,
                    "semestre": semestre,
                    "ue": ue,
                    "option": None,
                    "parcours": "COMMUN",
                    "element": element,
                }

        # ==========================================================
        # CAS NOUVEAU MODELE
        # periode -> groupes_elements_pedagogiques
        # ==========================================================

        for group in periode.get("groupes_elements_pedagogiques", []):

            # ------------------------------------------------------
            # Cas 1 : UE élémentaire directe
            # group -> elements_pedagogiques
            # ------------------------------------------------------

            if "elements_pedagogiques" in group:
                parcours = group.get("contrainte") or "COMMUN"

                for element in group.get("elements_pedagogiques", []):
                    yield {
                        "periode": periode,
                        "semestre": semestre,
                        "ue": group,
                        "option": None,
                        "parcours": parcours,
                        "element": element,
                    }

            # ------------------------------------------------------
            # Cas 2 : UE composite avec options de parcours
            # group -> groupes_elements_pedagogiques -> elements
            # ------------------------------------------------------

            elif "groupes_elements_pedagogiques" in group:
                ue = group

                for option in group.get("groupes_elements_pedagogiques", []):
                    parcours = option.get("contrainte") or "COMMUN"

                    for element in option.get("elements_pedagogiques", []):
                        yield {
                            "periode": periode,
                            "semestre": semestre,
                            "ue": ue,
                            "option": option,
                            "parcours": parcours,
                            "element": element,
                        }


def get_element_acquis(element):
    """
    Supporte les deux noms possibles :
    - ancien : acquis
    - nouveau : acquis_apprentissage
    """

    if "acquis_apprentissage" in element:
        return element.get("acquis_apprentissage", [])

    return element.get("acquis", [])


def get_element_credits(element):
    """
    Supporte :
    - ancien : ects
    - nouveau : credits
    """

    return (
        element.get("credits")
        if element.get("credits") is not None
        else element.get("ects", 0.0)
    )


def get_ue_credits(ue):
    """
    Supporte :
    - ancien : ects
    - nouveau : credits
    """

    return (
        ue.get("credits")
        if ue.get("credits") is not None
        else ue.get("ects", 0.0)
    )


def _extract_mlo_id_from_ac_code(ac_code):
    """
    Extrait l'identifiant MLO porté par un AC canonique UNITA.

    Exemple UNITA :
        PLO2__UNITA_FINANCE_MLO01 -> UNITA_FINANCE_MLO01

    Pour les sources historiques (Polytech/BUT), les codes AC ne suivent pas
    cette convention : on retourne None et la jointure module directe reste
    utilisée comme avant.
    """
    if not ac_code:
        return None

    text = str(ac_code).strip()
    if "__" not in text:
        return None

    mlo_id = text.rsplit("__", 1)[1].strip()
    return mlo_id or None


def _acquis_id(acquis):
    """Retourne l'id d'un acquis/MLO curriculum sous forme stable."""
    if not isinstance(acquis, dict):
        return ""
    return str(acquis.get("id") or "").strip()


def build_competence_items(competence_data):
    """
    Construit les liens issus du référentiel de compétences.

    Sortie : une ligne par lien AC -> module déclaré dans le référentiel.

    Supporte :
    - Polytech : ac.modules
    - BUT      : ac.modules, ac.ressources, ac.saes
    - UNITA    : ac.modules vers modules génériques + extraction du MLO
                 depuis le code AC (PLOx__UNITA_..._MLOyy)

    Important sources MLO : le champ `mlo_id` permet ensuite de relier un module
    spécifique USMB à un AC/PLO via ses `acquis_apprentissage`, sans créer de
    lien direct module spécifique -> module générique dans le modèle.
    """

    comp_items = []

    if not competence_data:
        return comp_items

    for sous in competence_data.get("sous_classifications", []):
        for comp in sous.get("competences", []):
            competence_code = comp.get("code")
            competence_name = comp.get("nom")

            for niveau in comp.get("niveaux_developpement", []):
                niveau_value = niveau.get("niveau")

                for ac in niveau.get("apprentissages_critiques", []):
                    ac_code = ac.get("code")
                    ac_description = ac.get("description")
                    mlo_id = _extract_mlo_id_from_ac_code(ac_code)

                    modules = []
                    modules.extend(ac.get("modules", []))
                    modules.extend(ac.get("ressources", []))
                    modules.extend(ac.get("saes", []))

                    # Dédoublonnage en gardant l'ordre.
                    modules = list(dict.fromkeys(m for m in modules if m))

                    for module_code in modules:
                        normalized_module_code = normalize_module_code(module_code)

                        if not normalized_module_code:
                            continue

                        comp_items.append({
                            "sous_classification": sous.get("code"),
                            "sous_classification_nom": sous.get("nom"),

                            "competence_code": competence_code,
                            "competence_name": competence_name,

                            "niveau": niveau_value,

                            "ac_code": ac_code,
                            "ac_description": ac_description,

                            # Module déclaré dans le référentiel de compétences
                            # (module générique UNITA, module réel Polytech/BUT).
                            "module_code": normalized_module_code,

                            # MLO porté par l'AC canonique UNITA.
                            # None pour les sources qui n'utilisent pas ce format.
                            "mlo_id": mlo_id,
                        })

    return comp_items


def build_visualisation_rows(competence_data, curriculum_data):
    """
    Construit les lignes utilisées par :
    - graphe pédagogique
    - heatmap
    - forêt pédagogique
    - forêt curriculaire
    - sunburst

    Compatible avec :
    - données compétences seules (sans curriculum)
    - données curriculum seules (sans compétences)
    - les deux combinées
    - ancien modèle curriculum Polytech
    - nouveau modèle curriculum BUT/Polytech/UNITA

    Point clé Joint Degree / sources MLO :
    ----------------
    Les modules spécifiques USMB ne sont pas liés directement aux modules
    génériques. Ils héritent des MLO dans `acquis_apprentissage`.

    La jointure complète fait donc deux chemins :
      A. chemin historique : AC.modules -> module curriculum
      B. chemin par MLO       : module.acquis_apprentissage[MLO] -> AC/PLO

    Ainsi la visualisation affiche les modules spécifiques USMB quand ils
    portent les mêmes MLO que les AC canoniques PLOx__MLO.
    """

    rows = []

    if not competence_data and not curriculum_data:
        return rows

    # ── Cas : uniquement Compétences (pas de curriculum) ─────────────────────
    # On itère directement les ACs pour produire des lignes même quand
    # les ACs n'ont aucune référence de module (ressources/saes/modules vides).
    if competence_data and not curriculum_data:
        for sous in competence_data.get("sous_classifications", []):
            for comp in sous.get("competences", []):
                comp_code = comp.get("code")
                comp_name = comp.get("nom")

                for niveau in comp.get("niveaux_developpement", []):
                    niveau_value = niveau.get("niveau")

                    for ac in niveau.get("apprentissages_critiques", []):
                        ac_code        = ac.get("code")
                        ac_description = ac.get("description")

                        # Collecter les références de modules (peut être vide)
                        modules = []
                        modules.extend(ac.get("modules", []))
                        modules.extend(ac.get("ressources", []))
                        modules.extend(ac.get("saes", []))
                        modules = list(dict.fromkeys(m for m in modules if m))

                        base = {
                            "periode_id":  None,
                            "ue_id":       None,
                            "ue_code":     None,
                            "ue_name":     None,
                            "ue_type":     None,
                            "ue_credits":  0.0,
                            "option_id":   None,
                            "option_code": None,
                            "option_name": None,
                            "option_type": None,
                            "parcours":    None,
                            "module_type":         None,
                            "module_credits":      0.0,
                            "module_volume_total": 0.0,
                            "orphan": True,
                            "acquis_id":          None,
                            "acquis_description": None,
                            "sous_classification":     sous.get("code"),
                            "sous_classification_nom": sous.get("nom"),
                            "competence_code": comp_code,
                            "competence_name": comp_name,
                            "niveau":          niveau_value,
                            "ac_code":         ac_code,
                            "ac_description":  ac_description,
                        }

                        if modules:
                            for module_code in modules:
                                norm = normalize_module_code(module_code)
                                if not norm:
                                    continue
                                sem_match = re.search(r'[A-Z]+([0-9])[0-9]{2}', norm)
                                sem_deduit = int(sem_match.group(1)) if sem_match else None
                                rows.append({
                                    **base,
                                    "semestre":    sem_deduit,
                                    "module_id":   norm,
                                    "module_code": norm,
                                    "module_name": norm,
                                })
                        else:
                            # AC sans module : ligne avec module_code = None
                            rows.append({
                                **base,
                                "semestre":    None,
                                "module_id":   None,
                                "module_code": None,
                                "module_name": None,
                            })
        return rows

    # ── Cas : uniquement Curriculum (pas de compétences) ─────────────────────
    if curriculum_data and not competence_data:
        for item in iter_curriculum_elements(curriculum_data):
            periode  = item["periode"]
            semestre = item["semestre"]
            ue       = item["ue"]
            option   = item["option"]
            parcours = item["parcours"]
            element  = item["element"]

            element_id       = element.get("id")
            element_raw_code = element.get("code") or element.get("id")
            element_code     = normalize_module_code(element_raw_code)
            element_name     = element.get("nom")
            element_type     = element.get("type")

            if not element_code:
                continue

            rows.append({
                "semestre":    semestre,
                "periode_id":  periode.get("id"),
                "ue_id":       ue.get("id"),
                "ue_code":     ue.get("code"),
                "ue_name":     ue.get("intitule"),
                "ue_type":     ue.get("type"),
                "ue_credits":  get_ue_credits(ue),
                "option_id":   option.get("id")       if option else None,
                "option_code": option.get("code")     if option else None,
                "option_name": option.get("intitule") if option else None,
                "option_type": option.get("type")     if option else None,
                "parcours":    parcours,
                "module_id":           element_id,
                "module_code":         element_code,
                "module_name":         element_name,
                "module_type":         element_type,
                "module_credits":      get_element_credits(element),
                "module_volume_total": element.get("volume_total", 0.0),
                "orphan": False,
                "acquis_id":          None,
                "acquis_description": None,
                "sous_classification":     None,
                "sous_classification_nom": None,
                "competence_code":         None,
                "competence_name":         None,
                "niveau":                  None,
                "ac_code":                 None,
                "ac_description":          None,
            })
        return rows

    # ── Cas complet : Compétences + Curriculum ────────────────────────────────
    competence_items = build_competence_items(competence_data)

    # Index module_code -> liste de comp_items (chemin historique direct).
    comp_index = {}
    # Index MLO_ID -> liste de comp_items (chemin par MLO via acquis_apprentissage).
    mlo_index = {}

    for item in competence_items:
        mc = item.get("module_code")
        if mc:
            comp_index.setdefault(mc, []).append(item)

        mlo_id = item.get("mlo_id")
        if mlo_id:
            mlo_index.setdefault(mlo_id, []).append(item)

    # Modules du référentiel déjà couverts par le curriculum. Sert uniquement
    # à éviter d'ajouter en fin de fonction des faux "orphelins" génériques.
    curriculum_codes_found = set()

    # Parcourir une seule fois le curriculum : cela permet de construire des
    # indices génériques sans hypothèse sur le nom de la source.
    curriculum_items = list(iter_curriculum_elements(curriculum_data))

    def _element_has_institution(element):
        """
        Indique si un élément appartient explicitement à une couche
        institutionnelle. Ce champ est optionnel dans le modèle, donc les
        anciennes sources restent compatibles.
        """
        institutions = element.get("institutions") if isinstance(element, dict) else None
        return bool(institutions)

    def _period_key(periode):
        return (
            str(periode.get("id") or ""),
            str(periode.get("numero") or ""),
        )

    # Un Joint Degree peut contenir deux couches dans le même programme :
    # - une couche de référence/catalogue : modules génériques, MLO, blocs communs ;
    # - une couche institutionnelle : vraie maquette d'un établissement.
    # La détection ci-dessous est volontairement générique : elle ne dépend
    # ni du nom de la source, ni du préfixe des modules, ni d'un établissement.
    period_has_institutional_elements = {}
    programme_has_institutional_layer = False

    for cur_item in curriculum_items:
        cur_period = cur_item.get("periode") or {}
        cur_element = cur_item.get("element") or {}
        key = _period_key(cur_period)
        has_inst = _element_has_institution(cur_element)
        period_has_institutional_elements[key] = (
            period_has_institutional_elements.get(key, False) or has_inst
        )
        programme_has_institutional_layer = programme_has_institutional_layer or has_inst

    def _safe_int(value):
        try:
            return int(value)
        except Exception:
            return None

    def _is_reference_period(periode):
        """
        Détecte une période technique de référence/catalogue sans hardcoding
        source. Cette période doit rester affichable, mais elle ne doit pas
        apparaître comme un vrai semestre S-1/S0.
        """
        numero = _safe_int(periode.get("numero"))
        if numero is not None and numero < 1:
            return True

        period_text = normalize_label(
            f"{periode.get('id') or ''} "
            f"{periode.get('code') or ''} "
            f"{periode.get('nom') or ''} "
            f"{periode.get('intitule') or ''}"
        )
        reference_tokens = (
            "COMMON", "COMMUN", "GENERIC", "GENERIQUE", "GÉNÉRIQUE",
            "CATALOG", "CATALOGUE", "REFERENCE", "RÉFÉRENCE",
            "REFERENTIEL", "RÉFÉRENTIEL",
        )
        if any(token in period_text for token in reference_tokens):
            return True

        # Cas Joint Degree générique : si un programme contient une couche
        # institutionnelle, toute période sans élément institutionnel est une
        # couche de référence. Cela couvre les catalogues par années, modules
        # génériques ou blocs de correspondance, sans dépendre d'un préfixe.
        if programme_has_institutional_layer:
            return not period_has_institutional_elements.get(_period_key(periode), False)

        return False

    def _curriculum_layer_for(periode, element):
        if _is_reference_period(periode):
            return "reference"
        if _element_has_institution(element):
            return "institutional"
        return "standard"

    def _base_row(periode, semestre, ue, option, parcours, element,
                  element_id, element_code, element_name, element_type,
                  linked, curriculum_layer="standard"):
        return {
            # Données référentiel / AC / compétence.
            # Attention : `linked` contient aussi un `module_code` historique
            # (= module déclaré dans le référentiel de compétences). On le
            # conserve sous un autre nom, puis on réécrit ensuite le vrai
            # module curriculum à afficher.
            **linked,
            "referentiel_module_code": linked.get("module_code"),

            "semestre":    semestre,
            "periode_id":  periode.get("id"),

            "ue_id":       ue.get("id"),
            "ue_code":     ue.get("code"),
            "ue_name":     ue.get("intitule"),
            "ue_type":     ue.get("type"),
            "ue_credits":  get_ue_credits(ue),

            "option_id":   option.get("id")       if option else None,
            "option_code": option.get("code")     if option else None,
            "option_name": option.get("intitule") if option else None,
            "option_type": option.get("type")     if option else None,

            "parcours":    parcours,

            # IMPORTANT : le module affiché est TOUJOURS le module curriculum.
            # Pour un Joint Degree, c'est donc le module institutionnel, pas le module de référence.
            "module_id":           element_id,
            "module_code":         element_code,
            "module_name":         element_name,
            "module_type":         element_type,
            "module_credits":      get_element_credits(element),
            "module_volume_total": element.get("volume_total", 0.0),

            "orphan": False,
            "curriculum_layer": curriculum_layer,
        }

    # ── Parcours du curriculum ────────────────────────────────────────────────
    for item in curriculum_items:
        periode  = item["periode"]
        semestre = item["semestre"]
        ue       = item["ue"]
        option   = item["option"]
        parcours = item["parcours"]
        element  = item["element"]

        element_id = element.get("id")
        curriculum_layer = _curriculum_layer_for(periode, element)

        # Une couche de référence/catalogue reste visible, mais n'est jamais
        # présentée comme un semestre réel. Cela évite S-1/S0 sans masquer le
        # catalogue générique utile à la compréhension du mapping.
        if curriculum_layer == "reference":
            semestre = None

        element_raw_code = element.get("code") or element.get("id")
        element_code     = normalize_module_code(element_raw_code)
        element_name     = element.get("nom")
        element_type     = element.get("type")

        if not element_code:
            continue

        acquis_list = get_element_acquis(element)
        acquis_by_id = {
            _acquis_id(acquis): acquis
            for acquis in acquis_list
            if _acquis_id(acquis)
        }

        # Liste de couples (linked_competence_item, acquis_associe_ou_None).
        # On combine :
        # - jointure directe par module_code (historique Polytech/BUT/générique) ;
        # - jointure indirecte par MLO contenu dans l'élément (UNITA/USMB).
        linked_pairs = []

        # Chemin A — ancien : AC.modules -> module curriculum.
        direct_links = comp_index.get(element_code, [])
        if direct_links:
            curriculum_codes_found.add(element_code)

        for linked in direct_links:
            mlo_id = linked.get("mlo_id")
            if mlo_id and mlo_id in acquis_by_id:
                linked_pairs.append((linked, acquis_by_id[mlo_id]))
            else:
                # Sources historiques ou AC sans MLO identifiable : on conserve
                # le comportement précédent sans fabriquer d'acquis.
                linked_pairs.append((linked, None))

        # Chemin B — MLO : element.acquis_apprentissage[MLO] -> AC/PLO.
        for acquis_id, acquis in acquis_by_id.items():
            for linked in mlo_index.get(acquis_id, []):
                linked_pairs.append((linked, acquis))
                # Le module générique déclaré côté compétence est considéré
                # couvert par un module curriculum spécifique ; cela évite de
                # l'ajouter ensuite comme orphelin générique.
                if linked.get("module_code"):
                    curriculum_codes_found.add(linked["module_code"])

        if not linked_pairs:
            continue

        seen_rows = set()
        for linked, acquis in linked_pairs:
            acquis_id = _acquis_id(acquis)
            dedupe_key = (
                element_code,
                linked.get("competence_code"),
                linked.get("ac_code"),
                acquis_id,
            )
            if dedupe_key in seen_rows:
                continue
            seen_rows.add(dedupe_key)

            base_row = _base_row(
                periode, semestre, ue, option, parcours, element,
                element_id, element_code, element_name, element_type,
                linked,
                curriculum_layer=curriculum_layer,
            )
            rows.append({
                **base_row,
                "acquis_id":          acquis_id or None,
                "acquis_description": (
                    acquis.get("description") if isinstance(acquis, dict) else None
                ),
            })

    # ── Modules orphelins : présents dans le référentiel mais pas dans le curriculum ─
    # On déduit leur semestre depuis le code du module (chiffre des centaines).
    # Règle validée sur tous les modules IDU connus : INFO5xx→S5, INFO6xx→S6, etc.
    # Ils s'affichent normalement dans la forêt, filtrés par semestre comme les autres.
    for mc, items in comp_index.items():
        if mc in curriculum_codes_found:
            continue
        # Déduire le semestre depuis le code : [A-Z]+([0-9])[0-9]{2}
        sem_match = re.search(r'[A-Z]+([0-9])[0-9]{2}', mc)
        sem_deduit = int(sem_match.group(1)) if sem_match else None

        for linked in items:
            rows.append({
                "semestre":    sem_deduit,   # semestre déduit du code, pas None
                "periode_id":  None,

                "ue_id":       None,
                "ue_code":     None,
                "ue_name":     None,
                "ue_type":     None,
                "ue_credits":  0.0,

                "option_id":   None,
                "option_code": None,
                "option_name": None,
                "option_type": None,

                "parcours":    None,

                "module_id":           mc,
                "module_code":         mc,
                "module_name":         mc,
                "module_type":         None,
                "module_credits":      0.0,
                "module_volume_total": 0.0,

                "orphan": True,
                "acquis_id":          None,
                "acquis_description": None,
                **linked,
            })

    return rows

def normalize_label(value):
    """
    Normalise un texte pour faciliter les comparaisons.
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


def is_common_sous_classification(code, label):
    """
    Détecte le tronc commun de manière générique.

    On ne hardcode pas COMP_1, COMP_2, COMP_3.
    On détecte seulement si la sous-classification correspond
    à un tronc commun.
    """

    text = f"{normalize_label(code)} {normalize_label(label)}"

    return (
        "TRONC COMMUN" in text
        or "TC COMMUN" in text
        or "COMMUN" in text
        or text.strip() == "TC"
        or " BUT TC " in f" {text} "
        or text.endswith(" TC")
    )


def get_specialite_options_from_rows(rows):
    """
    Construit la liste des spécialités/parcours.

    Le tronc commun n'est pas affiché dans la liste,
    car il doit être ajouté automatiquement à chaque parcours.
    """

    sous_classifications = {}

    for r in rows:
        code = r.get("sous_classification")
        nom = r.get("sous_classification_nom")

        if not code:
            continue

        code = str(code).strip()
        label = str(nom or code).strip()

        if not code:
            continue

        # On masque le tronc commun dans le dropdown
        if is_common_sous_classification(code, label):
            continue

        sous_classifications[code] = label

    options = [
        {
            "label": "Toutes les spécialités",
            "value": "all"
        }
    ]

    for code, label in sorted(sous_classifications.items()):
        options.append({
            "label": label,
            "value": code
        })

    return options

def filter_rows_by_specialite(rows, selected_specialite):
    """
    Filtre les lignes par spécialité.

    Règle :
    - all : afficher tout ;
    - sinon : afficher le tronc commun + la spécialité sélectionnée.

    Exemple :
    MP => TC commun + BUT_MP
    MPBS => TC commun + BUT_MPBS
    """

    if not selected_specialite or selected_specialite == "all":
        return rows

    selected = str(selected_specialite).strip()

    # 1. Détecter toutes les sous-classifications communes
    common_sous_classifications = set()

    for r in rows:
        code = r.get("sous_classification")
        label = r.get("sous_classification_nom")

        if is_common_sous_classification(code, label):
            common_sous_classifications.add(str(code).strip())

    # 2. Garder tronc commun + spécialité choisie
    filtered_rows = []

    for r in rows:
        code = str(r.get("sous_classification") or "").strip()

        is_selected = code == selected
        is_common = code in common_sous_classifications

        if is_selected or is_common:
            filtered_rows.append(r)

    return filtered_rows

def empty_figure(message="Aucune donnée"):
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=16, color="#94A3B8"))
    fig.update_layout(height=600, paper_bgcolor="#F8FAFB", plot_bgcolor="#F8FAFB",
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  GRAPHE PÉDAGOGIQUE — OPTIMISÉ (batching d'arêtes)
#
#  CLEF PERF : au lieu de 1 trace par arête, on construit 4 listes
#  [x0, x1, None, x2, x3, None, ...] et on crée UNE SEULE trace Plotly.
#  Réduction : ~5 400 traces → 6 traces. Rendu ~100x plus rapide.
# ══════════════════════════════════════════════════════════════════════════════

def _build_graph_data(rows):
    """
    Extrait et déduplique toutes les entités depuis les lignes de données.
    Retourne (comps, acs, modules, edges_ca, edges_am).
    Séparé de create_forest_graph pour être testable et réutilisable.
    """
    comps, acs, modules = {}, {}, {}
    edges_ca, edges_am  = [], []
    seen_ca, seen_am    = set(), set()

    for r in rows:
        cc = r.get("competence_code")
        ac = r.get("ac_code")
        mi = r.get("module_id")
        if not cc or not ac or not mi:
            continue

        comps[cc] = r.get("competence_name", "")

        if ac not in acs:
            acs[ac] = {"niveau": r.get("niveau"),
                       "desc": r.get("ac_description", ""),
                       "comp_code": cc}

        if mi not in modules:
            # Affichage seul : un module non rattaché à une vraie UE reçoit
            # de l'ETL un pseudo-groupe "MODULE_<code>" (type "MODULE").
            # Ce ne sont PAS des modules légitimement sans UE : leur UE
            # existe côté source (learning_unit_code) mais n'a pas été
            # reportée sur eux (trou de rattachement ETL — voir
            # docs/IDU_UE_RATTACHEMENT_DIAGNOSTIC.md). On les regroupe donc
            # sous "Sans UE" plutôt que de les afficher chacun comme sa
            # propre UE. Ne change aucune donnée : uniquement le regroupement
            # d'affichage dans le graphe pédagogique.
            _ue_code = r.get("ue_code", "") or ""
            _ue_type = str(r.get("ue_type") or "").upper()
            _ue_name = r.get("ue_name", "")
            if _ue_type == "MODULE" or _ue_code.startswith("MODULE_"):
                _ue_code = ""       # -> "Sans UE" en aval
                _ue_name = ""
            modules[mi] = {"name": r.get("module_name", ""),
                           "code": r.get("module_code", ""),
                           "ue_code": _ue_code,
                           "ue_name": _ue_name,
                           "ue_layer": r.get("curriculum_layer", "standard")}

        if (cc, ac) not in seen_ca:
            edges_ca.append((cc, ac)); seen_ca.add((cc, ac))
        if (ac, mi) not in seen_am:
            edges_am.append((ac, mi)); seen_am.add((ac, mi))

    return comps, acs, modules, edges_ca, edges_am


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT — avec clustering des modules par UE quand le volume est trop élevé
#
#  PROBLÈME RÉSOLU (cas BUT : 349 modules / 167 AC) :
#  - Avant : 1 nœud "module" par module → ~350 marqueurs alignés sur une
#    largeur disproportionnée par rapport au bloc compétences/AC, ce qui
#    force des centaines d'arêtes à converger en éventail → effet "halo".
#  - Après : si une UE dépasse CLUSTER_THRESHOLD modules, ses modules sont
#    regroupés en 1 seul nœud "cluster" (carré plus grand, libellé "UEx · N").
#    Cliquer sur un cluster le déplie (focus) sans changer le reste du layout.
#  - Les UE avec peu de modules (cas IDU) restent affichées en détail,
#    comme avant : aucune régression sur le cas qui fonctionne déjà bien.
# ══════════════════════════════════════════════════════════════════════════════

CLUSTER_THRESHOLD = 6        # nb de modules dans une UE au-delà duquel on regroupe
MAX_DETAIL_MODULES = 80      # si total modules > ce seuil, on force le clustering global
MAX_EXPANDABLE_MODULES = 25  # au-delà, le dépliage manuel reste bloqué (trop dense pour
                              # rester lisible en détail) ; le détail passe alors par le
                              # panneau latéral plutôt que par le graphe lui-même.


def _should_cluster_ue(ue_module_ids, total_modules):
    """
    Décide si une UE doit être affichée en cluster (1 nœud) plutôt
    qu'en détail (1 nœud par module).

    Règle générique (pas de hardcode par programme) :
    - une UE individuellement "grosse" (> CLUSTER_THRESHOLD modules), OU
    - le programme est globalement dense (> MAX_DETAIL_MODULES modules)
      ET cette UE contribue significativement à l'encombrement
      (> 2 modules). Les UE à 1 ou 2 modules restent toujours en détail,
      même sur un programme dense : elles ne créent pas l'effet de halo
      et le clustering n'apporterait aucun gain de lisibilité.
    """
    n = len(ue_module_ids)
    if n > CLUSTER_THRESHOLD:
        return True
    if total_modules > MAX_DETAIL_MODULES and n > 2:
        return True
    return False


def format_ue_label(ue_code, ue_name=None, ue_layer=None):
    """Libellé complet d'UE pour les hovers/panneaux de détail."""
    if not ue_code or str(ue_code).strip() == "":
        return "Sans UE"
    code = str(ue_code).strip()
    name = str(ue_name or "").strip()

    if ue_layer == "reference":
        base = name if name and name != code else code
        return f"Catalogue générique — {base}" if base else "Catalogue générique"

    if name and name != code:
        return f"{code} — {name}"
    return code


def compact_ue_label(ue_code, ue_name=None, max_chars=12, ue_layer=None):
    """
    Libellé court pour le graphe.

    Ne modifie aucune donnée : uniquement l'affichage.
    Objectif : éviter les labels bruts/synthétiques ou trop longs.
    Le libellé complet reste disponible dans le hover via format_ue_label().
    """
    raw_code = str(ue_code or "").strip()
    raw_name = str(ue_name or "").strip()

    if not raw_code:
        return "Sans UE"
    if raw_code == "Sans UE":
        return "Sans UE"

    # Préférer le nom métier quand le code est synthétique (S1_GRP04, etc.).
    is_synthetic_group = bool(re.match(r"^S\d+[_\s-]*GRP\d+$", raw_code, flags=re.I))
    label = raw_name if is_synthetic_group and raw_name else raw_code

    label = label.replace("_", " ").strip()
    label = re.sub(r"^S-?\d+\s*[-–—_ ]+", "", label, flags=re.I).strip()

    # Couche de référence/catalogue : règle générique, indépendante de la
    # source et des codes de modules. On préfixe seulement le libellé visible.
    if ue_layer == "reference":
        reference_label = raw_name if raw_name and raw_name != raw_code else label
        reference_label = reference_label.replace("_", " ").strip()
        if len(reference_label) > max_chars:
            reference_label = reference_label[: max_chars - 1].rstrip() + "…"
        return f"Gén. {reference_label}" if reference_label else "Générique"

    # Groupes de langues : afficher une information courte et lisible.
    m = re.search(r"CHOIX\s+LANG(?:UE)?\s*([ABC])", label, flags=re.I)
    if m:
        return f"Langue {m.group(1).upper()}"

    m = re.search(r"\bLANG(?:UE)?\s*([ABC])\b", label, flags=re.I)
    if m:
        return f"Langue {m.group(1).upper()}"

    key = re.sub(r"\s+", " ", label.upper()).strip()

    # Codes pédagogiques usuels : garder le code court.
    m = re.search(r"\b(UAF|UAM|UAI|UA|LV|FRAN|ESPA|ITAL)\d+[A-Z0-9_]*\b", key)
    if m:
        return m.group(0)

    if re.match(r"^GRP\d+$", key):
        return "Groupe"

    if len(label) > max_chars:
        return label[: max_chars - 1].rstrip() + "…"

    return label


def _build_layout(comps, acs, modules, edges_am, expanded_clusters=None):
    """
    Layout amélioré pour le graphe pédagogique APC.

    Objectif :
    - Chaque compétence possède son bloc horizontal.
    - Les AC sont placés sous leur compétence parente.
    - Les AC sont triés par niveau : N1, puis N2, puis N3.
    - La compétence est centrée sous ses AC.
    - Les modules sont regroupés par UE. Une UE volumineuse est représentée
      par un seul nœud "cluster" (sauf si l'utilisateur l'a explicitement
      dépliée via `expanded_clusters`), ce qui réduit drastiquement le
      nombre de marqueurs/arêtes sur les programmes denses (ex. BUT).

    Retourne :
        pos          : dict node_key -> (x, y)
        node_meta    : dict node_key -> métadonnées (type, code, ue, etc.)
        ue_display   : dict ue_code -> label affiché ("UE1", "UE2"...)
        ue_x_ranges  : dict ue_code -> (x0, x1) emprise horizontale de l'UE
        ue_module_map: dict ue_code -> liste des module_id qu'elle contient
                       (utile pour le focus/dépliage d'un cluster)
    """
    expanded_clusters = expanded_clusters or set()

    Y_COMP, Y_AC, Y_MODULE = 0.0, 5.5, 11.0

    AC_GAP = 2.2               # espace entre AC d'un même niveau
    LEVEL_GAP = 3.0            # espace entre N1 / N2 / N3
    COMP_BLOCK_GAP = 10.0      # espace entre blocs de compétences
    MIN_COMP_BLOCK_WIDTH = 10.0

    MODULE_GAP = 0.65          # espace minimal entre modules détaillés
    CLUSTER_GAP = 1.4          # espace minimal entre clusters d'UE
    UE_BLOCK_GAP = 1.1         # marge entre deux blocs d'UE distincts

    pos, node_meta = {}, {}

    comp_list = sorted(comps.keys())

    # ------------------------------------------------------------------
    # 1. Préparer les AC par compétence et par niveau
    # ------------------------------------------------------------------

    comp_blocks = {}

    for cc in comp_list:
        levels = {}

        acs_for_comp = [
            ac for ac, meta in acs.items()
            if meta.get("comp_code") == cc
        ]

        for ac in acs_for_comp:
            niveau = acs[ac].get("niveau")

            try:
                niveau_key = int(niveau)
            except Exception:
                niveau_key = 99

            levels.setdefault(niveau_key, []).append(ac)

        # Tri des AC dans chaque niveau
        for niveau_key in levels:
            levels[niveau_key] = sorted(levels[niveau_key])

        # Calcul largeur du bloc compétence
        level_widths = []

        for niveau_key in sorted(levels.keys()):
            n_ac = len(levels[niveau_key])
            width = max(1, n_ac) * AC_GAP
            level_widths.append(width)

        block_width = (
            sum(level_widths)
            + max(0, len(level_widths) - 1) * LEVEL_GAP
        )

        block_width = max(MIN_COMP_BLOCK_WIDTH, block_width)

        comp_blocks[cc] = {
            "levels": levels,
            "width": block_width,
        }

    # ------------------------------------------------------------------
    # 2. Positionner les blocs de compétences
    # ------------------------------------------------------------------

    total_width = (
        sum(block["width"] for block in comp_blocks.values())
        + max(0, len(comp_blocks) - 1) * COMP_BLOCK_GAP
    )

    cursor_x = -total_width / 2

    for cc in comp_list:
        block = comp_blocks[cc]
        block_width = block["width"]

        block_start = cursor_x
        block_end = cursor_x + block_width
        block_center = (block_start + block_end) / 2

        # Compétence centrée sous son bloc
        comp_key = f"COMP::{cc}"
        pos[comp_key] = (block_center, Y_COMP)

        node_meta[comp_key] = {
            "type": "competence",
            "code": cc,
            "name": comps[cc],
        }

        # ------------------------------------------------------------------
        # 3. Positionner les AC par niveau dans le bloc compétence
        # ------------------------------------------------------------------

        levels = block["levels"]

        level_widths = {}

        for niveau_key, ac_list in levels.items():
            level_widths[niveau_key] = max(1, len(ac_list)) * AC_GAP

        total_levels_width = (
            sum(level_widths.values())
            + max(0, len(level_widths) - 1) * LEVEL_GAP
        )

        level_cursor = block_center - total_levels_width / 2

        for niveau_key in sorted(levels.keys()):
            ac_list = levels[niveau_key]
            level_width = level_widths[niveau_key]
            level_center = level_cursor + level_width / 2

            for j, ac in enumerate(ac_list):
                x = level_center + (j - (len(ac_list) - 1) / 2) * AC_GAP

                ac_key = f"AC::{ac}"
                pos[ac_key] = (x, Y_AC)

                node_meta[ac_key] = {
                    "type": "ac",
                    "code": ac,
                    "niveau": acs[ac]["niveau"],
                    "desc": acs[ac]["desc"],
                    "comp": cc,
                }

            level_cursor += level_width + LEVEL_GAP

        cursor_x += block_width + COMP_BLOCK_GAP

    # ------------------------------------------------------------------
    # 4. Regrouper les modules par UE et décider cluster vs détail
    # ------------------------------------------------------------------

    ue_module_map = {}
    for mi, meta in modules.items():
        ue = meta.get("ue_code") or "Sans UE"
        ue_module_map.setdefault(ue, []).append(mi)

    total_modules = len(modules)

    ue_is_clustered = {}
    ue_expansion_blocked = set()

    for ue, mids in ue_module_map.items():
        should_cluster = _should_cluster_ue(mids, total_modules)
        user_expanded = ue in expanded_clusters

        if should_cluster and user_expanded and len(mids) > MAX_EXPANDABLE_MODULES:
            ue_is_clustered[ue] = True
            ue_expansion_blocked.add(ue)
        else:
            ue_is_clustered[ue] = should_cluster and not user_expanded

    # ------------------------------------------------------------------
    # 5. Calculer la position "gravité" de chaque UE selon ses AC liés
    # ------------------------------------------------------------------

    module_to_ac_x = {}
    for ac, mi in edges_am:
        ac_key = f"AC::{ac}"
        if ac_key not in pos:
            continue
        ac_x, _ = pos[ac_key]
        module_to_ac_x.setdefault(mi, []).append(ac_x)

    def _gravity(mi):
        xs = module_to_ac_x.get(mi, [])
        return sum(xs) / len(xs) if xs else 0.0

    ue_gravity = {}
    for ue, mids in ue_module_map.items():
        gxs = [_gravity(mi) for mi in mids]
        ue_gravity[ue] = sum(gxs) / len(gxs) if gxs else 0.0

    # ------------------------------------------------------------------
    # 6. Construire les "unités de largeur" à placer sur l'axe X
    # ------------------------------------------------------------------

    sorted_ues = sorted(ue_module_map.keys(), key=lambda ue: (ue_gravity[ue], str(ue)))

    placements = []

    for ue in sorted_ues:
        mids = sorted(ue_module_map[ue], key=lambda mi: (_gravity(mi), str(mi)))
        if ue_is_clustered[ue]:
            placements.append({"ue": ue, "kind": "cluster", "mids": mids, "width": CLUSTER_GAP})
        else:
            for mi in mids:
                placements.append({"ue": ue, "kind": "module", "mi": mi, "width": MODULE_GAP})

    # ------------------------------------------------------------------
    # 7. Placer séquentiellement avec marge supplémentaire entre blocs d'UE
    # ------------------------------------------------------------------

    module_positions = {}
    cluster_positions = {}
    ue_x_ranges = {}

    cursor = 0.0
    prev_ue = None

    for item in placements:
        ue = item["ue"]
        if prev_ue is not None and ue != prev_ue:
            cursor += UE_BLOCK_GAP
        half = item["width"] / 2
        cursor += half
        x = cursor
        cursor += half

        if item["kind"] == "cluster":
            cluster_positions[ue] = x
        else:
            module_positions[item["mi"]] = x

        ue_x_ranges.setdefault(ue, [x, x])
        ue_x_ranges[ue][0] = min(ue_x_ranges[ue][0], x)
        ue_x_ranges[ue][1] = max(ue_x_ranges[ue][1], x)

        prev_ue = ue

    # Correction du bloc modules basée sur des mesures RÉELLES
    all_x_raw = list(module_positions.values()) + list(cluster_positions.values())
    all_comp_x = [pos[f"COMP::{cc}"][0] for cc in comp_list if f"COMP::{cc}" in pos]

    if all_x_raw:
        raw_min, raw_max = min(all_x_raw), max(all_x_raw)
        raw_span = max(raw_max - raw_min, 1e-6)

        comp_span_real = (max(all_comp_x) - min(all_comp_x)) if all_comp_x else raw_span
        comp_span_real = max(comp_span_real, 1.0)

        PLOT_WIDTH_PX = 1100.0
        CLUSTER_MARKER_PX = 34.0
        CHAR_WIDTH_PX = 6.0
        LABEL_PADDING_PX = 14.0

        n_ues = len(ue_x_ranges) if ue_x_ranges else 1
        max_label_chars = max((len(str(ue)) for ue in ue_x_ranges.keys()), default=4)
        label_width_px = max_label_chars * CHAR_WIDTH_PX + LABEL_PADDING_PX
        min_slot_px = max(CLUSTER_MARKER_PX, label_width_px)

        estimated_final_span = max(comp_span_real, raw_span)
        estimated_px_per_unit = PLOT_WIDTH_PX / estimated_final_span

        min_modules_span_for_slots = (n_ues * min_slot_px) / estimated_px_per_unit

        target_span = max(raw_span, min_modules_span_for_slots)
        scale = target_span / raw_span if raw_span > 1e-9 else 1.0

        if scale > 1.0 + 1e-6:
            module_positions = {k: raw_min + (v - raw_min) * scale for k, v in module_positions.items()}
            cluster_positions = {k: raw_min + (v - raw_min) * scale for k, v in cluster_positions.items()}
            ue_x_ranges = {
                k: (raw_min + (v[0] - raw_min) * scale, raw_min + (v[1] - raw_min) * scale)
                for k, v in ue_x_ranges.items()
            }

    # Recentrer l'ensemble (clusters + modules) sur le centre des compétences
    all_x = list(module_positions.values()) + list(cluster_positions.values())

    if all_x and all_comp_x:
        target_center = (min(all_comp_x) + max(all_comp_x)) / 2
        current_center = (min(all_x) + max(all_x)) / 2
        shift = target_center - current_center

        module_positions = {k: v + shift for k, v in module_positions.items()}
        cluster_positions = {k: v + shift for k, v in cluster_positions.items()}
        ue_x_ranges = {k: (v[0] + shift, v[1] + shift) for k, v in ue_x_ranges.items()}
    else:
        ue_x_ranges = {k: tuple(v) for k, v in ue_x_ranges.items()}

    # ------------------------------------------------------------------
    # 8. Insérer modules détaillés et clusters dans pos / node_meta
    # ------------------------------------------------------------------

    for mi, x in module_positions.items():
        mod_key = f"MOD::{mi}"
        pos[mod_key] = (x, Y_MODULE)
        node_meta[mod_key] = {
            "type": "module",
            "id": mi,
            "name": modules[mi]["name"],
            "code": modules[mi]["code"],
            "ue": modules[mi].get("ue_code") or "Sans UE",
            "ue_name": modules[mi].get("ue_name", ""),
            "ue_layer": modules[mi].get("ue_layer", "standard"),
        }

    for ue, x in cluster_positions.items():
        cluster_key = f"CLUSTER::{ue}"
        pos[cluster_key] = (x, Y_MODULE)
        mids = ue_module_map[ue]
        node_meta[cluster_key] = {
            "type": "cluster",
            "id": ue,
            "ue": ue,
            "count": len(mids),
            "module_ids": mids,
        }

    # ------------------------------------------------------------------
    # 9. Construire les libellés d'UE
    # ------------------------------------------------------------------

    # Labels d'UE : les VRAIS codes issus du curriculum (UE503, UE603...),
    # tries pour stabilite visuelle. "Sans UE" reste tel quel.
    ue_display = {
        ue_code: str(ue_code)
        for ue_code in sorted(ue_x_ranges.keys(), key=str)
    }

    return pos, node_meta, ue_display, ue_x_ranges, ue_module_map, ue_is_clustered, ue_expansion_blocked


def _resolve_label_overlaps(centers, min_gap):
    """
    Étale une liste de centres de labels (triés ou non) pour qu'aucun
    label ne soit à moins de `min_gap` du suivant, en coordonnées data.
    """
    order = sorted(range(len(centers)), key=lambda i: centers[i])
    adjusted = {}
    last = None
    for i in order:
        c = centers[i]
        if last is not None and c < last + min_gap:
            c = last + min_gap
        adjusted[i] = c
        last = c
    return adjusted


def _resolve_focus(node_key, node_meta, acs, edges_am):
    """
    Calcule l'ensemble des nœuds et arêtes à mettre en focus
    à partir d'un nœud cliqué.
    """
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
                for _, mi in [(e0, e1) for e0, e1 in edges_am if e0 == ac]:
                    mk = f"MOD::{mi}"
                    focus_nodes.add(mk)
                    focus_edges.add(frozenset([ak, mk]))

    elif ntype == "ac":
        ac = node_meta[node_key]["code"]
        cc = acs[ac]["comp_code"]
        ck = f"COMP::{cc}"
        focus_nodes.add(ck)
        focus_edges.add(frozenset([node_key, ck]))
        for _, mi in [(e0, e1) for e0, e1 in edges_am if e0 == ac]:
            mk = f"MOD::{mi}"
            focus_nodes.add(mk)
            focus_edges.add(frozenset([node_key, mk]))

    elif ntype == "module":
        mi = node_meta[node_key]["id"]
        for ac, mi2 in edges_am:
            if mi2 == mi:
                ak = f"AC::{ac}"
                focus_nodes.add(ak)
                focus_edges.add(frozenset([node_key, ak]))
                cc = acs[ac]["comp_code"]
                ck = f"COMP::{cc}"
                focus_nodes.add(ck)
                focus_edges.add(frozenset([ak, ck]))

    elif ntype == "cluster":
        member_ids = set(node_meta[node_key].get("module_ids", []))
        related_acs = {ac for ac, mi in edges_am if mi in member_ids}
        for ac in related_acs:
            ak = f"AC::{ac}"
            focus_nodes.add(ak)
            focus_edges.add(frozenset([node_key, ak]))
            cc = acs.get(ac, {}).get("comp_code")
            if cc:
                ck = f"COMP::{cc}"
                focus_nodes.add(ck)
                focus_edges.add(frozenset([ak, ck]))

    return focus_nodes, focus_edges


def _hex_to_rgba(hex_color, alpha):
    """Convertit '#RRGGBB' en chaîne rgba(...) exploitable par Plotly shapes."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def create_forest_graph(rows, selected_node=None, semester_filter=None, expanded_clusters=None):
    """
    ┌─────────────────────────────────────────────────────────────────┐
    │  PERF : batching d'arêtes + clustering des UE volumineuses       │
    │  Toutes les arêtes inactives → 1 trace (listes x/y avec None)   │
    │  Toutes les arêtes actives   → 2 traces (CA et AM colorées)     │
    │  Modules d'une UE dense      → 1 nœud cluster au lieu de N      │
    └─────────────────────────────────────────────────────────────────┘
    """

    if not rows:
        return empty_figure("Aucune donnée disponible")

    if semester_filter and semester_filter != "all":
        rows = [r for r in rows if str(r.get("semestre")) == str(semester_filter)]
    if not rows:
        return empty_figure("Aucune donnée pour ce semestre")

    # ── Extraction des données ────────────────────────────────────────
    comps, acs, modules, edges_ca, edges_am = _build_graph_data(rows)

    if not comps:
        return empty_figure("Aucun lien trouvé")

    comp_order = sorted(comps.keys())
    comp_list = comp_order

    # ── Layout (avec clustering UE) ────────────────────────────────────
    pos, node_meta, ue_display, ue_x_ranges, ue_module_map, ue_is_clustered, ue_expansion_blocked = _build_layout(
        comps, acs, modules, edges_am, expanded_clusters
    )

    _ac_xs_for_gap = sorted(v[0] for k, v in pos.items() if k.startswith("AC::"))
    _ac_gaps_for_gap = [b - a for a, b in zip(_ac_xs_for_gap, _ac_xs_for_gap[1:]) if b - a > 1e-6]
    AC_GAP = min(_ac_gaps_for_gap) if _ac_gaps_for_gap else 3.0

    mi_to_node_key = {}
    for ue, mids in ue_module_map.items():
        if ue_is_clustered.get(ue):
            ck = f"CLUSTER::{ue}"
            for mi in mids:
                mi_to_node_key[mi] = ck
        else:
            for mi in mids:
                mi_to_node_key[mi] = f"MOD::{mi}"

    # ── Focus ────────────────────────────────────────────────────────
    focus_nodes, focus_edges = _resolve_focus(selected_node, node_meta, acs, edges_am)
    has_focus = bool(focus_nodes)

    def node_op(key):
        if not has_focus: return 1.0
        return 1.0 if key in focus_nodes else FADE_OP

    def edge_is_focus(a, b):
        return has_focus and frozenset([a, b]) in focus_edges

    # ══════════════════════════════════════════════════════════════════
    #  BATCHING D'ARÊTES
    # ══════════════════════════════════════════════════════════════════

    ex_ca_off, ey_ca_off = [], []
    ex_ca_on,  ey_ca_on  = [], []
    ex_am_off, ey_am_off = [], []
    ex_am_on,  ey_am_on  = [], []

    for cc, ac in edges_ca:
        ck, ak = f"COMP::{cc}", f"AC::{ac}"
        if ck not in pos or ak not in pos: continue
        x0, y0 = pos[ck];  x1, y1 = pos[ak]
        if edge_is_focus(ck, ak):
            ex_ca_on  += [x0, x1, None]; ey_ca_on  += [y0, y1, None]
        else:
            ex_ca_off += [x0, x1, None]; ey_ca_off += [y0, y1, None]

    seen_am_visual = set()
    for ac, mi in edges_am:
        ak = f"AC::{ac}"
        mk = mi_to_node_key.get(mi)
        if ak not in pos or not mk or mk not in pos:
            continue
        visual_edge = (ak, mk)
        if visual_edge in seen_am_visual:
            continue
        seen_am_visual.add(visual_edge)

        x0, y0 = pos[ak];  x1, y1 = pos[mk]
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

    # ══════════════════════════════════════════════════════════════════
    #  NŒUDS
    # ══════════════════════════════════════════════════════════════════

    # ── Compétences ───────────────────────────────────────────────────
    cx, cy, ct, chov, ccd, csz, cop, ccol = [], [], [], [], [], [], [], []
    for key, m in node_meta.items():
        if m["type"] != "competence": continue
        x, y = pos[key]
        cx.append(x); cy.append(y)
        ct.append(f"<b>{m['code']}</b>")
        chov.append(f"<b>Compétence : {m['code']}</b><br><i>{m['name']}</i><br><br>🖱 Cliquez pour explorer")
        ccd.append(key)
        csz.append(24 if key == selected_node else 22)
        cop.append(node_op(key))
        scheme = get_competence_color_scheme(m["code"], comp_order)
        ccol.append(scheme["root"])

    traces.append(go.Scatter(
        x=cx, y=cy, mode="markers+text",
        marker=dict(
            color=ccol, size=csz, symbol="diamond", opacity=cop,
            line=dict(width=1.8, color="#FFFFFF")
        ),
        text=ct, textposition="bottom center",
        textfont=dict(size=9, color="#334155"),
        hovertext=chov, hoverinfo="text",
        hoverlabel=dict(bgcolor="#4C1D95", bordercolor="#A78BFA",
                        font=dict(color="white", size=12)),
        customdata=ccd, name="Compétences", showlegend=True
    ))

    # ── AC ────────────────────────────────────────────────────────────
    ax, ay, ahov, acd, asz, aop, acol = [], [], [], [], [], [], []
    for key, m in node_meta.items():
        if m["type"] != "ac": continue
        x, y = pos[key]
        col = get_ac_color_from_competence(m["comp"], m["niveau"], comp_order)
        ax.append(x); ay.append(y); acol.append(col)
        ahov.append(
            f"<b>AC : {m['code']}</b><br>"
            f"Niveau {m['niveau']} — {_niveau_label(m['niveau'])}<br>"
            f"Compétence : {m['comp']}<br><br><i>{m['desc']}</i><br><br>"
            f"🖱 Cliquez pour explorer"
        )
        acd.append(key)
        asz.append(11 if key == selected_node else 9)
        aop.append(node_op(key))

    traces.append(go.Scatter(
        x=ax, y=ay, mode="markers",
        marker=dict(color=acol, size=asz, symbol="circle",
                    opacity=aop, line=dict(width=1.2, color="#64748B")),
        hovertext=ahov, hoverinfo="text",
        hoverlabel=dict(bgcolor="#1F2937", bordercolor="#6B7280",
                        font=dict(color="white", size=12)),
        customdata=acd, name="AC", showlegend=True
    ))

    # ── Modules détaillés ───────────────────────────────────────────────
    mx, my, mhov, mcd, msz, mop = [], [], [], [], [], []
    for key, m in node_meta.items():
        if m["type"] != "module": continue
        x, y = pos[key]
        mx.append(x); my.append(y)
        mhov.append(
            f"<b>{m['code'] or m['id']}</b><br>"
            f"<i>{m['name']}</i><br>{format_ue_label(m['ue'], m.get('ue_name'), m.get('ue_layer'))}<br><br>"
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

    # Mapping ue_code -> ue_name / ue_layer (depuis les modules) pour les hovers
    ue_names = {}
    ue_layers = {}
    for _m in node_meta.values():
        if _m.get("type") == "module":
            if _m.get("ue_name"):
                ue_names.setdefault(_m["ue"], _m["ue_name"])
            layer = _m.get("ue_layer", "standard")
            if _m["ue"] not in ue_layers or ue_layers[_m["ue"]] == "standard":
                ue_layers[_m["ue"]] = layer

    # ── Clusters d'UE ───────────────────────────────────────────────────
    klx, kly, klhov, klcd, klsz, klop, kltxt = [], [], [], [], [], [], []
    for key, m in node_meta.items():
        if m["type"] != "cluster": continue
        x, y = pos[key]
        klx.append(x); kly.append(y)
        ue_label = format_ue_label(m["ue"], ue_names.get(m["ue"]), ue_layers.get(m["ue"]))
        kltxt.append(str(m["count"]))
        if m["ue"] in ue_expansion_blocked:
            klhov.append(
                f"<b>{ue_label}</b><br>{m['count']} modules regroupés<br><br>"
                f"⚠ Trop de modules pour un dépliage lisible dans le graphe.<br>"
                f"🖱 Cliquez pour voir le détail dans le panneau latéral."
            )
        else:
            klhov.append(
                f"<b>{ue_label}</b><br>{m['count']} modules regroupés<br><br>"
                f"🖱 Cliquez pour déplier le détail"
            )
        klcd.append(key)
        klsz.append(34 if key == selected_node else 30)
        klop.append(node_op(key))

    if klx:
        traces.append(go.Scatter(
            x=klx, y=kly, mode="markers+text",
            marker=dict(color="#1D4ED8", size=klsz, symbol="square",
                        opacity=klop, line=dict(width=2, color="#FFFFFF")),
            text=kltxt, textposition="middle center",
            textfont=dict(size=11, color="#FFFFFF", family="Segoe UI, sans-serif"),
            hovertext=klhov, hoverinfo="text",
            hoverlabel=dict(bgcolor="#1E3A8A", bordercolor="#93C5FD",
                            font=dict(color="white", size=12)),
            customdata=klcd, name="Modules regroupés (UE)", showlegend=True
        ))

    # ── Libellés de couches ──────────────────────────────────────────────

    if pos:
        all_x_values = [x for x, _ in pos.values()]
        x_min, x_max = min(all_x_values), max(all_x_values)
        span = max(x_max - x_min, 1.0)
        margin = span * 0.10
        x_left = x_min - margin

        traces.append(go.Scatter(
            x=[x_left]*3, y=[0.0, 5.5, 11.0], mode="text",
            text=["<b>Compétences</b>", "<b>AC</b>", "<b>Modules</b>"],
            textposition="middle right",
            textfont=dict(size=13, color=[C_COMP, "#4B5563", C_MODULE]),
            hoverinfo="none", showlegend=False
        ))
    else:
        x_min, x_max, span, margin = -20, 20, 40, 4

    # ── Cadres d'UE ──────────────────────────────────────────────────────

    UE_PALETTE = ["#2563EB", "#7C3AED", "#0F766E", "#B45309",
                  "#BE185D", "#15803D", "#1D4ED8", "#9D174D"]

    ue_codes_sorted = sorted(ue_x_ranges.keys(), key=lambda c: ue_x_ranges[c][0])
    raw_centers = [ (ue_x_ranges[uc][0] + ue_x_ranges[uc][1]) / 2 for uc in ue_codes_sorted ]

    PLOT_WIDTH_PX = 1100.0
    CHAR_WIDTH_PX = 6.0
    LABEL_PADDING_PX = 14.0
    reference_data_per_px = span / PLOT_WIDTH_PX

    max_label_chars = max(
        (len(compact_ue_label(uc, ue_names.get(uc), ue_layer=ue_layers.get(uc))) for uc in ue_codes_sorted),
        default=4
    )
    label_width_px = max_label_chars * CHAR_WIDTH_PX + LABEL_PADDING_PX
    min_label_gap = label_width_px * reference_data_per_px

    adjusted = _resolve_label_overlaps(raw_centers, min_label_gap)
    label_centers = {ue_codes_sorted[i]: adjusted[i] for i in range(len(ue_codes_sorted))}

    Y_UE_BAND_BOTTOM, Y_UE_BAND_TOP = 10.35, 11.65
    Y_UE_LABEL = 12.35

    # Troncature de sécurité pour un code UE anormalement long (le hover
    # garde toujours le libellé complet via format_ue_label). N'affecte
    # que l'affichage, jamais la position, la couleur ni les données.
    UE_LABEL_MAX_CHARS = 14

    def _short_ue_label(label):
        if len(label) > UE_LABEL_MAX_CHARS:
            return label[:UE_LABEL_MAX_CHARS - 1] + "…"
        return label

    ue_lx, ue_ly, ue_lt, ue_lcolor = [], [], [], []
    for i, uc in enumerate(ue_codes_sorted):
        color = UE_PALETTE[i % len(UE_PALETTE)]
        label = compact_ue_label(uc, ue_names.get(uc), ue_layer=ue_layers.get(uc))
        ue_lx.append(label_centers[uc])
        ue_ly.append(Y_UE_LABEL)
        ue_lt.append(f"<b>{_short_ue_label(label)}</b>")
        ue_lcolor.append(color)

    if ue_lx:
        traces.append(go.Scatter(
            x=ue_lx, y=ue_ly, mode="text",
            text=ue_lt, textfont=dict(size=10, color=ue_lcolor),
            hovertext=[
                f"<b>{format_ue_label(uc, ue_names.get(uc), ue_layers.get(uc))}</b><br>{len(ue_module_map.get(uc, []))} module(s)"
                f"{' (groupée)' if ue_is_clustered.get(uc) else ''}"
                for uc in ue_codes_sorted
            ],
            hoverinfo="text",
            hoverlabel=dict(bgcolor="#1E293B", font=dict(color="white", size=11)),
            showlegend=False
        ))

    shapes = []
    annotations = []

    for i, uc in enumerate(ue_codes_sorted):
        x0, x1 = ue_x_ranges[uc]
        pad = 0.55 if ue_is_clustered.get(uc) else 0.35
        color = UE_PALETTE[i % len(UE_PALETTE)]

        shapes.append(dict(
            type="rect", x0=x0 - pad, x1=x1 + pad,
            y0=Y_UE_BAND_BOTTOM, y1=Y_UE_BAND_TOP,
            fillcolor=_hex_to_rgba(color, 0.10),
            line=dict(color=_hex_to_rgba(color, 0.55), width=1.4),
            layer="below"
        ))

        label_x = label_centers[uc]
        ue_center = (x0 + x1) / 2
        # Sur les graphes denses (UNITA), les traits pointillés de décalage
        # créent plus de bruit que d'information. On les garde seulement
        # quand le nombre de labels est raisonnable.
        if len(ue_codes_sorted) <= 18 and abs(label_x - ue_center) > min_label_gap * 0.3:
            shapes.append(dict(
                type="line", x0=ue_center, x1=label_x,
                y0=Y_UE_BAND_TOP, y1=Y_UE_LABEL - 0.25,
                line=dict(color=_hex_to_rgba(color, 0.45), width=1, dash="dot"),
                layer="below"
            ))

    xm = x_min - margin * 1.4
    xx = x_max + margin * 1.4
    for yv, fc in [(0.0, "rgba(109,40,217,0.08)"),
                   (5.5, "rgba(75,85,99,0.06)"),
                   (11.0, "rgba(29,78,216,0.05)")]:
        shapes.append(dict(type="rect", x0=xm, x1=xx,
                           y0=yv-0.55, y1=yv+0.55,
                           fillcolor=fc, line=dict(width=0), layer="below"))

    comp_bgs = ["rgba(237,233,254,0.14)", "rgba(248,250,252,0.0)"]
    for i, cc in enumerate(comp_list):
        xs = [pos[f"AC::{a}"][0] for a, m in acs.items()
              if m["comp_code"] == cc and f"AC::{a}" in pos]
        if not xs: continue
        shapes.append(dict(type="rect",
                           x0=min(xs)-AC_GAP*0.6, x1=max(xs)+AC_GAP*0.6,
                           y0=-0.8, y1=6.3,
                           fillcolor=comp_bgs[i % 2],
                           line=dict(width=0), layer="below"))

    # ── Layout Plotly ─────────────────────────────────────────────────
    sem_lbl   = f" · S{semester_filter}" if semester_filter and semester_filter != "all" else ""
    focus_lbl = ""
    if selected_node and selected_node in node_meta:
        nd   = node_meta[selected_node]
        tp   = {"competence": "Compétence", "ac": "AC", "module": "Module", "cluster": "Groupe UE"}
        code = nd.get("code") or nd.get("id", "")
        focus_lbl = (f"  <span style='color:#7C3AED;font-weight:600'>"
                     f"Focus : {tp.get(nd['type'], nd['type'])} {code}</span>")

    n_c, n_a, n_m = len(comps), len(acs), len(modules)
    n_visible_module_nodes = len(mx) + len(klx)
    subtitle = (f"<span style='font-size:12px;color:#94A3B8'>"
                f"{n_c} compétences · {n_a} AC · {n_m} modules "
                f"({n_visible_module_nodes} nœuds affichés)"
                f"{sem_lbl}{focus_lbl}</span>")

    all_x_for_range = [x_min, x_max] + list(label_centers.values())
    range_min = min(all_x_for_range)
    range_max = max(all_x_for_range)

    xr = [range_min - margin * 2.6, range_max + margin * 1.8]
    yr = [-1.8, Y_UE_LABEL + 1.0]

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(
            text=f"<b>Graphe pédagogique APC</b><br>{subtitle}",
            font=dict(size=16, color="#0F172A", family="Segoe UI, sans-serif"),
            x=0.01, y=0.99
        ),
        height=900,
        paper_bgcolor="#F8FAFB", plot_bgcolor="#FFFFFF",
        showlegend=True,
        legend=dict(orientation="v", x=1.01, y=0.98,
                    bgcolor="rgba(255,255,255,0.92)",
                    bordercolor="#E4E9F0", borderwidth=1,
                    font=dict(size=12, color="#374151"),
                    itemsizing="constant"),
        margin=dict(l=160, r=150, t=85, b=60),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=xr, constrain="domain"),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=yr, scaleanchor=None),
        shapes=shapes,
        annotations=annotations,
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
            n = len({r["module_id"] for r in rows if r["semestre"]==s and r["competence_code"]==c})
            line.append(n); h.append(f"<b>S{s} × {c}</b><br>{n} module(s)")
        z.append(line); hover.append(h)
    fig = go.Figure(go.Heatmap(z=z, x=comps, y=[f"S{s}" for s in sems],
        colorscale="Blues", hoverongaps=False,
        hovertext=hover, hoverinfo="text",
        colorbar=dict(title=dict(text="Modules", side="right"), thickness=14)))
    fig.update_layout(
        title=dict(text="<b>Heatmap globale</b> — Semestres × Compétences",
                   font=dict(size=15, color="#0F172A")),
        xaxis_title="Compétences", yaxis_title="Semestres",
        height=560, paper_bgcolor="#F8FAFB", plot_bgcolor="#FFFFFF",
        margin=dict(l=80, r=80, t=70, b=80))
    return fig


def create_semester_heatmap(rows, semester):
    sr = [r for r in rows if str(r["semestre"]) == str(semester)]
    if not sr: return empty_figure(f"Aucune donnée pour S{semester}")
    mods  = sorted({r["module_id"] for r in sr if r["module_id"]})
    comps = sorted({r["competence_code"] for r in sr if r["competence_code"]})
    z = [[len([r for r in sr if r["module_id"]==m and r["competence_code"]==c])
          for c in comps] for m in mods]
    fig = go.Figure(go.Heatmap(z=z, x=comps, y=mods, colorscale="Blues",
        hoverongaps=False,
        colorbar=dict(title=dict(text="Liens", side="right"), thickness=14)))
    fig.update_layout(
        title=dict(text=f"<b>Heatmap S{semester}</b> — Modules × Compétences",
                   font=dict(size=15, color="#0F172A")),
        xaxis_title="Compétences", yaxis_title="Modules",
        height=700, paper_bgcolor="#F8FAFB", plot_bgcolor="#FFFFFF",
        margin=dict(l=120, r=80, t=70, b=80))
    return fig


def create_module_heatmap(rows, module_id):
    mr = [r for r in rows if r["module_id"] == module_id]
    if not mr: return empty_figure(f"Aucune donnée pour {module_id}")
    acquis = sorted({r["acquis_id"] or "Non renseigné" for r in mr})
    comps  = sorted({r["competence_code"] for r in mr if r["competence_code"]})
    z = [[len([r for r in mr if (r["acquis_id"] or "Non renseigné")==a and r["competence_code"]==c])
          for c in comps] for a in acquis]
    fig = go.Figure(go.Heatmap(z=z, x=comps, y=acquis, colorscale="Blues",
        hoverongaps=False,
        colorbar=dict(title=dict(text="Liens", side="right"), thickness=14)))
    fig.update_layout(
        title=dict(text=f"<b>Module {module_id}</b> — Acquis × Compétences",
                   font=dict(size=15, color="#0F172A")),
        xaxis_title="Compétences", yaxis_title="Acquis",
        height=650, paper_bgcolor="#F8FAFB", plot_bgcolor="#FFFFFF",
        margin=dict(l=120, r=80, t=70, b=80))
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT DASH
# ══════════════════════════════════════════════════════════════════════════════

programme_options = get_programme_options()
default_programme = programme_options[0]["value"] if programme_options else None

forested_visualisations_layout = html.Div([

    html.Div([
        html.Div([
            html.Span("🔗", style={"fontSize":"34px","marginRight":"12px"}),
            html.Div([
                html.H1("Exploration des formations", style={
                    "color":"#0F172A","fontSize":"28px","fontWeight":"700",
                    "margin":"0 0 3px","fontFamily":"Segoe UI, sans-serif"}),
                html.P("Relations entre compétences, apprentissages critiques et modules.",
                       style={"color":"#64748B","fontSize":"13px","margin":"0"})
            ])
        ], style={"display":"flex","alignItems":"center"})
    ], style={"marginBottom":"18px"}),

    html.Div([
        html.Div([
            html.Label("Formation", style=LABEL_STYLE),
            dcc.Dropdown(id="programme-selector", options=programme_options,
                         value=None, clearable=False,
                         style={"fontSize":"14px"})
        ], style={"width":"34%","minWidth":"200px"}),

        html.Div([
            html.Label("Semestre", style=LABEL_STYLE),
            dcc.Dropdown(id="semester-filter",
                         options=[{"label":"Tous","value":"all"}],
                         value="all", clearable=False,
                         style={"fontSize":"14px"})
        ], style={"width":"16%","minWidth":"120px"}),

        html.Div([
        html.Label("Spécialité / parcours", style=LABEL_STYLE),
        dcc.Dropdown(
            id="specialite-filter",
            options=[{"label": "Toutes les spécialités", "value": "all"}],
            value="all",
            clearable=False,
            style={"fontSize": "14px"}
        )
        ], style={"width": "18%", "minWidth": "160px"}),

        html.Div([
            html.Label("Vue", style=LABEL_STYLE),
            dcc.RadioItems(id="visualisation-mode",
                options=[{"label":"  Graphe","value":"graph"},
                         {"label":"  Heatmap","value":"heatmap"}],
                value="graph", inline=True,
                inputStyle={"marginRight":"4px"},
                labelStyle={"marginRight":"16px","fontSize":"13px","color":"#374151"})
        ], style={"display":"flex","flexDirection":"column"}),

        html.Div([
            html.Label("Lecture des couleurs", style=LABEL_STYLE),
            html.Div([
                html.Span("Compétence = couleur principale",
                  style={"fontSize": "11px", "color": "#374151", "marginRight": "14px"}),
                html.Span("AC N1 = clair",
                  style={"fontSize": "11px", "color": "#374151", "marginRight": "14px"}),
                html.Span("AC N2 = moyen",
                  style={"fontSize": "11px", "color": "#374151", "marginRight": "14px"}),
                html.Span("AC N3 = foncé",
                  style={"fontSize": "11px", "color": "#374151"}),
                html.Span("🟦 carré numéroté = UE groupée",
                  style={"fontSize": "11px", "color": "#374151"}),
            ], style={"display": "flex", "flexWrap": "wrap"})
        ]),

        html.Div([
            html.Label(" ", style={**LABEL_STYLE,"visibility":"hidden"}),
            html.Button("✕ Réinitialiser", id="visualisation-back", n_clicks=0,
                style={"height":"34px","padding":"0 14px",
                       "backgroundColor":"#F1F5F9","color":"#475569",
                       "border":"1px solid #CBD5E1","borderRadius":"6px",
                       "cursor":"pointer","fontSize":"12px","fontWeight":"600"})
        ], style={"display":"flex","flexDirection":"column"}),

    ], style={**CARD_STYLE,"display":"flex","alignItems":"flex-end",
               "flexWrap":"wrap","gap":"16px"}),

    dcc.Store(id="selected-forest-node"),
    dcc.Store(id="vis-rows-store"),
    dcc.Store(id="expanded-clusters-store", data=[]),
    html.Div(id="vis-focus-panel"),

    html.Div([
        dcc.Graph(id="forest-graph",
            config={"displayModeBar":True,"displaylogo":False,
                    "scrollZoom":True,
                    "responsive":True,
                    "modeBarButtonsToRemove":["select2d","lasso2d","autoScale2d"]})
    ], style=CARD_STYLE)

], style=PAGE_STYLE)


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def register_callbacks(app):

    @app.callback(
        Output("programme-selector", "value"),
        Input("programme-selector", "options"),
        State("programme-selector", "value"),
        prevent_initial_call=False,
    )
    def init_programme_selector_visu(options, current_value):
        """Initialise le dropdown au premier programme disponible si aucune valeur."""
        if current_value is not None:
            return current_value
        if options:
            return options[0]["value"]
        return None

    @app.callback(
    Output("vis-rows-store", "data"),
    Output("semester-filter", "options"),
    Output("specialite-filter", "options"),
    Output("specialite-filter", "value"),
    Input("programme-selector", "value")
    )
    def load_rows(selected_programme):
        comp_data, curr_data = get_selected_data(selected_programme)

        rows = build_visualisation_rows(
            comp_data,
            curr_data
        )

        sems = sorted(
            {
                r["semestre"]
                for r in rows
                if r.get("semestre") is not None
            },
            key=sort_semester
        )

        semester_options = [
            {
                "label": "Tous les semestres",
                "value": "all"
            }
        ] + [
            {
                "label": f"Semestre {s}",
                "value": str(s)
            }
            for s in sems
        ]

        specialite_options = get_specialite_options_from_rows(rows)

        return rows, semester_options, specialite_options, "all"

    @app.callback(
    Output("forest-graph", "figure"),
    Output("selected-forest-node", "data"),
    Output("expanded-clusters-store", "data"),
    Input("vis-rows-store", "data"),
    Input("forest-graph", "clickData"),
    Input("semester-filter", "value"),
    Input("specialite-filter", "value"),
    Input("visualisation-mode", "value"),
    Input("visualisation-back", "n_clicks"),
    State("selected-forest-node", "data"),
    State("expanded-clusters-store", "data"),
    )
    def update_graph(
        stored_rows,
        click_data,
        semester,
        specialite,
        mode,
        n_reset,
        selected_node,
        expanded_clusters
    ):
        expanded_clusters = set(expanded_clusters or [])

        if not stored_rows:
            return empty_figure("Aucune donnée disponible"), None, []

        filtered_rows = filter_rows_by_specialite(
            stored_rows,
            specialite
        )

        if not filtered_rows:
            return empty_figure("Aucune donnée pour cette spécialité"), None, []

        triggered = ctx.triggered_id

        if triggered in [
        "visualisation-back",
        "programme-selector",
        "semester-filter",
        "specialite-filter",
        "visualisation-mode"
        ]:
            selected_node = None
            expanded_clusters = set()

            if mode == "heatmap":
                return (
                create_semester_heatmap(filtered_rows, semester)
                if semester and semester != "all"
                else create_global_heatmap(filtered_rows)
                ), None, []

        if triggered == "forest-graph" and click_data:
            clicked = click_data["points"][0].get("customdata")

            if clicked and str(clicked).startswith("CLUSTER::"):
                ue_code = clicked[len("CLUSTER::"):]
                mids_for_ue = [
                    r.get("module_id") for r in filtered_rows
                    if (r.get("ue_code") or "Sans UE") == ue_code and r.get("module_id")
                ]
                n_mods = len({m for m in mids_for_ue if m})

                if n_mods > MAX_EXPANDABLE_MODULES:
                    selected_node = clicked
                else:
                    if ue_code in expanded_clusters:
                        expanded_clusters.discard(ue_code)
                    else:
                        expanded_clusters.add(ue_code)
                    selected_node = None
            else:
                selected_node = None if clicked == selected_node else clicked

        fig = create_forest_graph(
            filtered_rows,
            selected_node,
            semester,
            expanded_clusters
        )
        return fig, selected_node, sorted(expanded_clusters)

    @app.callback(
    Output("vis-focus-panel", "children"),
    Input("selected-forest-node", "data"),
    State("vis-rows-store", "data"),
    State("specialite-filter", "value"),
    )
    def update_panel(selected_node, stored_rows, specialite):
        if not selected_node or not stored_rows:
            return html.Div()
        stored_rows = filter_rows_by_specialite(
        stored_rows,
        specialite
        )
        comps_m, acs_m, mods_m = {}, {}, {}
        for r in stored_rows:
            cc, ac, mi = r.get("competence_code"), r.get("ac_code"), r.get("module_id")
            if cc: comps_m[cc] = r.get("competence_name","")
            if ac and ac not in acs_m:
                acs_m[ac] = {"niveau":r.get("niveau"),
                              "desc":r.get("ac_description",""),"comp":cc}
            if mi and mi not in mods_m:
                mods_m[mi] = {"name":r.get("module_name",""),
                               "code":r.get("module_code","")}

        if selected_node.startswith("COMP::"):
            code   = selected_node[6:]
            ac_set = sorted([a for a,m in acs_m.items() if m["comp"]==code])
            mod_set= sorted({r["module_id"] for r in stored_rows
                             if r.get("competence_code")==code and r.get("module_id")})
            border, title = C_COMP, f"Compétence : {code}"
            body = [_p(comps_m.get(code,""), italic=True),
                    _sec(f"📌 {len(ac_set)} AC","#7C3AED"),
                    _tags([(a,"#EDE9FE","#5B21B6") for a in ac_set]),
                    _sec(f"📦 {len(mod_set)} modules",C_MODULE),
                    _tags([(m,"#DBEAFE","#1E3A8A") for m in mod_set])]

        elif selected_node.startswith("AC::"):
            code  = selected_node[4:]
            meta  = acs_m.get(code,{})
            niv = meta.get("niveau")

            comp_order = sorted(comps_m.keys())

            col = get_ac_color_from_competence(
            meta.get("comp"),
            niv,
            comp_order
            )
            mods  = sorted({r["module_id"] for r in stored_rows
                            if r.get("ac_code")==code and r.get("module_id")})
            border, title = col, f"AC : {code}"
            body = [html.Span(f"Niveau {niv} — {_niveau_label(niv)}",
                              style={"backgroundColor":col,"color":"white",
                                     "borderRadius":"4px","padding":"2px 10px",
                                     "fontSize":"11px","display":"inline-block",
                                     "marginBottom":"8px"}),
                    _p(meta.get("desc",""), italic=True),
                    _sec("🎯 Compétence",C_COMP),
                    _tags([(meta.get("comp",""),"#EDE9FE","#5B21B6")]),
                    _sec(f"📦 {len(mods)} modules",C_MODULE),
                    _tags([(m,"#DBEAFE","#1E3A8A") for m in mods])]

        elif selected_node.startswith("MOD::"):
            mid   = selected_node[5:]
            meta  = mods_m.get(mid,{})
            comps_= sorted({r["competence_code"] for r in stored_rows
                            if r.get("module_id")==mid and r.get("competence_code")})
            acs_  = sorted({r["ac_code"] for r in stored_rows
                            if r.get("module_id")==mid and r.get("ac_code")})
            border, title = C_MODULE, f"Module : {meta.get('code', mid)}"
            body = [_p(meta.get("name",""), italic=True),
                    _sec(f"🎯 {len(comps_)} compétence(s)",C_COMP),
                    _tags([(c,"#EDE9FE","#5B21B6") for c in comps_]),
                    _sec(f"📌 {len(acs_)} AC","#4B5563"),
                    _tags([(a,"#F3F4F6","#374151") for a in acs_])]

        elif selected_node.startswith("CLUSTER::"):
            ue_code = selected_node[len("CLUSTER::"):]
            mod_set = sorted({r["module_id"] for r in stored_rows
                              if (r.get("ue_code") or "Sans UE") == ue_code and r.get("module_id")})
            border, title = C_MODULE, f"UE groupée : {ue_code}"
            body = [_p(f"{len(mod_set)} modules regroupés dans cette UE. "
                       f"Cliquez sur le carré dans le graphe pour déplier le détail.", italic=True),
                    _sec(f"📦 {len(mod_set)} modules", C_MODULE),
                    _tags([(m,"#DBEAFE","#1E3A8A") for m in mod_set])]
        else:
            return html.Div()

        return html.Div([html.Div([
            html.Div([
                html.Span(style={"width":"10px","height":"10px","borderRadius":"2px",
                                  "backgroundColor":border,"display":"inline-block",
                                  "marginRight":"8px"}),
                html.Span(title, style={"fontWeight":"700","fontSize":"14px","color":"#0F172A"})
            ], style={"display":"flex","alignItems":"center","marginBottom":"10px"}),
            *body,
            html.P("Cliquez sur le même nœud ou ✕ Réinitialiser pour effacer.",
                   style={"fontSize":"11px","color":"#94A3B8","margin":"12px 0 0","fontStyle":"italic"})
        ], style={"backgroundColor":"#FFFFFF","border":"1px solid #E2E8F0",
                   "borderLeft":f"4px solid {border}","borderRadius":"8px",
                   "padding":"14px 18px","boxShadow":"0 2px 8px rgba(0,0,0,0.05)"})
        ], style={"marginBottom":"14px"})


def _p(text, italic=False):
    if not text: return html.Div()
    s = {"color":"#6B7280","fontSize":"12px","margin":"0 0 8px"}
    if italic: s["fontStyle"] = "italic"
    return html.P(text, style=s)

def _sec(label, color):
    return html.P(label, style={"fontWeight":"600","color":color,
                                  "fontSize":"12px","margin":"8px 0 5px"})

def _tags(items):
    return html.Div([
        html.Span(t, style={"backgroundColor":bg,"color":fc,"borderRadius":"4px",
                             "padding":"2px 7px","fontSize":"11px",
                             "marginRight":"4px","marginBottom":"4px",
                             "display":"inline-block"})
        for t, bg, fc in items
    ], style={"display":"flex","flexWrap":"wrap","marginBottom":"4px"})