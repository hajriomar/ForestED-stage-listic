"""
Tests pour l'ajout minimal d'Institution / InstitutionDiplomante /
InstitutionMobilite dans app/models/curriculum_models.py.

Couvre :
- non-regression : les objets "anciens" (BUT/Polytech/USMB-like), sans champ
  institutions, restent valides, y compris un JSON deserialise qui ne
  contient pas du tout la cle "institutions" (cas des fichiers deja generes
  avant ce patch).
- nouveaux cas : Programme et ElementPedagogique(Formatif) avec institutions.
- le modele reste strict (extra="forbid") : Institution n'accepte aucun
  champ non declare.
"""
import json
import pytest
from app.models.curriculum_models import (
    Programme,
    PeriodeProgramme,
    GroupeElementsPedagogiquesElementaire,
    ElementPedagogiqueFormatif,
    ElementPedagogiqueProfessionnel,
    ElementPedagogiqueExterne,
    Institution,
    InstitutionDiplomante,
    InstitutionMobilite,
)


def make_minimal_element(**overrides):
    data = dict(id="EL1", nom="Element test", type="cours", credits=3.0)
    data.update(overrides)
    return ElementPedagogiqueFormatif(**data)


def make_minimal_groupe(elements=None):
    return GroupeElementsPedagogiquesElementaire(
        id="G1", code="G1", intitule="Groupe test", credits=3.0,
        elements_pedagogiques=elements or [],
    )


def make_minimal_periode(groupes=None):
    return PeriodeProgramme(id="P1", numero=1, ects=3.0,
                             groupes_elements_pedagogiques=groupes or [])


# ---------------------------------------------------------------------------
# Non-regression : sources existantes (BUT / Polytech / USMB) sans Institution
# ---------------------------------------------------------------------------

def test_programme_sans_institutions_reste_valide():
    el = make_minimal_element()
    groupe = make_minimal_groupe([el])
    periode = make_minimal_periode([groupe])
    prog = Programme(
        id="BUT_QLIO", nom="BUT QLIO", type="BUT", niveau="Bac+3",
        ects_total=180.0, duree=3, periodes=[periode],
    )
    assert prog.institutions == []
    assert prog.periodes[0].groupes_elements_pedagogiques[0].elements_pedagogiques[0].institutions == []


def test_ancien_json_sans_cle_institutions_reste_valide():
    """Simule un fichier JSON existant (Polytech/USMB) genere AVANT le patch :
    la cle 'institutions' est totalement absente du JSON."""
    old_style_json = {
        "id": "POLYTECH_IDU",
        "nom": "Polytech IDU",
        "type": "Ingenieur",
        "niveau": None,
        "ects_total": 300.0,
        "duree": 5,
        "periodes": [
            {
                "id": "S1",
                "numero": 1,
                "ects": 30.0,
                "groupes_elements_pedagogiques": [
                    {
                        "id": "G1",
                        "code": "UE1",
                        "intitule": "UE de test",
                        "credits": 30.0,
                        "type": None,
                        "contrainte": None,
                        "elements_pedagogiques": [
                            {
                                "id": "EL1",
                                "nom": "Cours de test",
                                "type": None,
                                "credits": 3.0,
                                "volume_total": 0.0,
                                "acquis_apprentissage": [],
                                "enseignants": [],
                                "cm": 10.0, "td": 0.0, "tp": 0.0, "projet": 0.0,
                                "ressources": [], "activites": [], "evaluations": [],
                                "acquis_apprentissage_elementaires": [],
                            }
                        ],
                    }
                ],
            }
        ],
        # pas de cle "institutions" du tout -> doit fonctionner grace au default
    }
    prog = Programme(**old_style_json)
    assert prog.institutions == []
    assert prog.periodes[0].groupes_elements_pedagogiques[0].elements_pedagogiques[0].institutions == []


def test_element_pedagogique_professionnel_sans_institutions():
    el = ElementPedagogiqueProfessionnel(id="STAGE1", nom="Stage", credits=10.0, duree=12.0)
    assert el.institutions == []


def test_element_pedagogique_externe_sans_institutions():
    el = ElementPedagogiqueExterne(id="EXT1", nom="Element externe", credits=3.0)
    assert el.institutions == []


# ---------------------------------------------------------------------------
# Nouveaux cas : Institution / InstitutionDiplomante / InstitutionMobilite
# ---------------------------------------------------------------------------

def test_programme_avec_institution_diplomante():
    prog = Programme(
        id="UNITA_JOINT_BA_LANGUAGE", nom="Test", ects_total=75.0, duree=3,
        institutions=[InstitutionDiplomante(nom="Universite Savoie Mont Blanc")],
    )
    assert len(prog.institutions) == 1
    assert isinstance(prog.institutions[0], InstitutionDiplomante)
    assert prog.institutions[0].nom == "Universite Savoie Mont Blanc"


def test_element_pedagogique_formatif_avec_institution_mobilite():
    el = make_minimal_element(institutions=[InstitutionMobilite(nom="UPPA")])
    assert len(el.institutions) == 1
    assert isinstance(el.institutions[0], InstitutionMobilite)
    assert el.institutions[0].nom == "UPPA"


def test_programme_avec_plusieurs_institutions_mixtes():
    prog = Programme(
        id="P1", nom="Programme test", ects_total=60.0, duree=2,
        institutions=[
            InstitutionDiplomante(nom="USMB"),
            InstitutionMobilite(nom="UPPA"),
            InstitutionMobilite(nom="HES-SO"),
        ],
    )
    assert len(prog.institutions) == 3
    kinds = [type(i).__name__ for i in prog.institutions]
    assert kinds == ["InstitutionDiplomante", "InstitutionMobilite", "InstitutionMobilite"]


def test_institution_de_base_utilisable_directement():
    inst = Institution(nom="Institution generique")
    assert inst.nom == "Institution generique"


def test_institution_extra_field_forbidden():
    """Le modele reste strict (extra='forbid') : aucun champ non declare
    ne doit etre accepte sur Institution, meme apres ce patch."""
    with pytest.raises(Exception):
        Institution(nom="X", pays="France")


def test_roundtrip_json_avec_institutions():
    prog = Programme(
        id="P1", nom="Programme test", ects_total=15.0, duree=1,
        institutions=[InstitutionDiplomante(nom="USMB")],
        periodes=[make_minimal_periode([make_minimal_groupe([
            make_minimal_element(institutions=[InstitutionMobilite(nom="UPPA")])
        ])])],
    )
    dumped = json.loads(prog.model_dump_json())
    reloaded = Programme(**dumped)
    assert reloaded.institutions[0].nom == "USMB"
    assert reloaded.periodes[0].groupes_elements_pedagogiques[0].elements_pedagogiques[0].institutions[0].nom == "UPPA"
