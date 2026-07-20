# -*- coding: utf-8 -*-
"""
flat_contract.py — R4
======================
Mini-spec des sorties des transformers ForestED + helpers de validation.

Pourquoi ce module
------------------
Chaque transformer retourne {"canonical": <modèle Pydantic>, "flat": list[dict]}.
Deux consommateurs, deux contrats :

1. Le CANONIQUE (data/processed) est ce que consomment les VISUALISATIONS :
   le frontend (`build_visualisation_rows` dans forested_visualisations.py)
   parcourt directement la structure canonique. C'est LUI qui casse
   silencieusement si une nouvelle source produit une structure incomplète
   (précédent réel : curriculum Polytech resté vide).

2. Le FLAT (data/analytics) est destiné à l'analyse ; ses clés doivent
   rester stables mais peuvent varier légèrement selon les métadonnées
   disponibles par source.

Ce module est la source de vérité UNIQUE des deux contrats. Les tests de
contrat (tests/test_flat_contract.py) l'appliquent aux 4 transformers
existants ; tout transformer d'une NOUVELLE source (UNITA…) devra passer
les mêmes tests.

═══════════════════════════════════════════════════════════════════════
CONTRAT CANONIQUE (consommé par build_visualisation_rows)
═══════════════════════════════════════════════════════════════════════

Domaine competence — ReferentielCompetences :
    sous_classifications[]        .code, .nom
      competences[]               .code, .nom
        niveaux_developpement[]   .niveau (int)
          apprentissages_critiques[]  .code, .description,
                                      .modules (list[str], peut être vide)

Domaine curriculum — Programme :
    periodes[]                    .id, .numero (int, -1 = TRANSVERSE)
      groupes_elements_pedagogiques[]   .code, .intitule, .type
        ├─ Elementaire : .elements_pedagogiques[]
        └─ Composite   : .groupes_elements_pedagogiques[] (Elementaires,
                          .contrainte = parcours)
          éléments      .id, .nom, .type, .credits
                        (.code optionnel : le frontend retombe sur .id)
                        .acquis_apprentissage[]  .id, .description

Convention de codes compétence (dépendance du FRONTEND, filtre parcours) :
    COMP_<n>            → compétence du tronc commun
    COMP_<PARCOURS>_<n> → compétence de parcours (ex. COMP_ATN_1)
Tout autre pattern est classé "unknown" par le frontend → filtre parcours
inopérant pour cette source. Une nouvelle source doit soit respecter ce
pattern, soit ne pas proposer de filtre parcours.

═══════════════════════════════════════════════════════════════════════
CONTRAT FLAT (data/analytics)
═══════════════════════════════════════════════════════════════════════

Domaine competence — clés OBLIGATOIRES (présentes dans BUT ET Polytech) :
    referentiel, sous_classification_code, sous_classification_nom,
    competence_code, competence_nom, niveau, ac_code, ac_description, modules

Clés RECOMMANDÉES (présentes quand la source le permet) :
    source        (Polytech l'a ; à généraliser)
    parcours, semestre, ue, niveau_description   (BUT les a)

NB : "programme" n'apparaît pas dans le flat competence — l'identité
programme/formation est portée par l'ARBORESCENCE de fichiers
(analytics/<domain>/<source>/<formation>_… ) et par "referentiel".

Domaine curriculum — clés OBLIGATOIRES :
    programme_id, programme_nom, semestre,
    element_id, element_nom, element_type, element_credits,
    cm, td, tp, projet, ac_id, ac_description

Identité du groupe parent — DEUX dialectes admis (au moins un complet) :
    dialecte "ue"     (BUT, référence pour les nouvelles sources) :
        ue_id, ue_code, ue_intitule, ue_type  (+ option_*, parcours)
    dialecte "groupe" (Polytech historique) :
        groupe_id, groupe_code, groupe_intitule, groupe_type

Clés RECOMMANDÉES : programme_type, programme_niveau, periode_id,
    parcours, volume_total, enseignants, ects/credits détaillés.

Les tests NE vérifient QUE les clés obligatoires + un dialecte complet :
une source peut ajouter librement ses métadonnées.
"""

# ---------------------------------------------------------------------------
# Clés du contrat FLAT
# ---------------------------------------------------------------------------

COMPETENCE_FLAT_REQUIRED = frozenset({
    "referentiel",
    "sous_classification_code", "sous_classification_nom",
    "competence_code", "competence_nom",
    "niveau",
    "ac_code", "ac_description",
    "modules",
})

COMPETENCE_FLAT_RECOMMENDED = frozenset({
    "source", "parcours", "semestre", "ue", "niveau_description",
})

CURRICULUM_FLAT_REQUIRED = frozenset({
    "programme_id", "programme_nom",
    "semestre",
    "element_id", "element_nom", "element_type", "element_credits",
    "cm", "td", "tp", "projet",
    "ac_id", "ac_description",
})

# Identité du groupe parent : au moins UN des deux dialectes complet.
CURRICULUM_GROUP_DIALECT_UE = frozenset({"ue_id", "ue_code", "ue_intitule", "ue_type"})
CURRICULUM_GROUP_DIALECT_GROUPE = frozenset({"groupe_id", "groupe_code",
                                             "groupe_intitule", "groupe_type"})

CURRICULUM_FLAT_RECOMMENDED = frozenset({
    "programme_type", "programme_niveau", "periode_id",
    "parcours", "volume_total",
})


# ---------------------------------------------------------------------------
# Helpers de validation (retournent une liste de problèmes ; vide = OK)
# ---------------------------------------------------------------------------

def _get(obj, name, default=None):
    """Accès uniforme attribut (modèle Pydantic) ou clé (dict)."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def validate_flat_rows(rows, domain):
    """Vérifie les clés obligatoires du flat pour un domaine donné."""
    problems = []
    if not isinstance(rows, list):
        return [f"flat doit être une liste, reçu {type(rows).__name__}"]
    if not rows:
        return ["flat vide : aucune ligne produite"]

    required = (COMPETENCE_FLAT_REQUIRED if domain == "competence"
                else CURRICULUM_FLAT_REQUIRED)

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"row {i} : pas un dict")
            continue
        missing = required - set(row.keys())
        if missing:
            problems.append(f"row {i} : clés obligatoires absentes {sorted(missing)}")

        if domain == "curriculum":
            has_ue = CURRICULUM_GROUP_DIALECT_UE <= set(row.keys())
            has_groupe = CURRICULUM_GROUP_DIALECT_GROUPE <= set(row.keys())
            if not (has_ue or has_groupe):
                problems.append(
                    f"row {i} : aucun dialecte d'identité de groupe complet "
                    f"(ue_* ou groupe_*)"
                )
    return problems


def validate_competence_canonical(referentiel):
    """Vérifie que le canonique competence est exploitable par
    build_visualisation_rows (structure + champs lus par le frontend)."""
    problems = []
    sous_list = _get(referentiel, "sous_classifications")
    if not sous_list:
        return ["canonique : sous_classifications vide ou absent"]

    n_ac = 0
    for sous in sous_list:
        if not _get(sous, "code"):
            problems.append("sous_classification sans code")
        for comp in _get(sous, "competences") or []:
            if not _get(comp, "code") or not _get(comp, "nom"):
                problems.append(f"compétence sans code/nom : {_get(comp, 'code')}")
            for niveau in _get(comp, "niveaux_developpement") or []:
                if not isinstance(_get(niveau, "niveau"), int):
                    problems.append(
                        f"{_get(comp, 'code')} : niveau non entier "
                        f"({_get(niveau, 'niveau')!r})"
                    )
                for ac in _get(niveau, "apprentissages_critiques") or []:
                    n_ac += 1
                    if not _get(ac, "code") or not _get(ac, "description"):
                        problems.append(f"AC sans code/description sous {_get(comp, 'code')}")
                    if not isinstance(_get(ac, "modules", []), list):
                        problems.append(f"AC {_get(ac, 'code')} : modules n'est pas une liste")
    if n_ac == 0:
        problems.append("canonique : aucun apprentissage critique")
    return problems


def validate_curriculum_canonical(programme):
    """Vérifie que le canonique curriculum est exploitable par
    build_visualisation_rows / iter_curriculum_elements."""
    problems = []
    if not _get(programme, "id") or not _get(programme, "nom"):
        problems.append("programme sans id/nom")

    periodes = _get(programme, "periodes")
    if not periodes:
        return problems + ["canonique : aucune période"]

    n_elements = 0
    for periode in periodes:
        if not isinstance(_get(periode, "numero"), int):
            problems.append(f"période {_get(periode, 'id')} : numero non entier")

        for groupe in _get(periode, "groupes_elements_pedagogiques") or []:
            if not _get(groupe, "code") or _get(groupe, "type") is None:
                problems.append(f"groupe sans code/type dans {_get(periode, 'id')}")

            # Elementaire direct OU Composite -> Elementaires
            sub_groups = _get(groupe, "groupes_elements_pedagogiques")
            elementaires = sub_groups if sub_groups else [groupe]

            for elem_groupe in elementaires:
                for element in _get(elem_groupe, "elements_pedagogiques") or []:
                    n_elements += 1
                    if not _get(element, "id") or not _get(element, "nom"):
                        problems.append(
                            f"élément sans id/nom dans {_get(elem_groupe, 'code')}"
                        )
                    if _get(element, "type") is None:
                        problems.append(f"élément {_get(element, 'id')} sans type")
                    for ac in _get(element, "acquis_apprentissage") or []:
                        if not _get(ac, "id") or not _get(ac, "description"):
                            problems.append(
                                f"AC sans id/description sur {_get(element, 'id')}"
                            )
    if n_elements == 0:
        problems.append("canonique : aucun élément pédagogique")
    return problems