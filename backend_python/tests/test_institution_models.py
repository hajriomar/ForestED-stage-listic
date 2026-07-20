"""
Tests du patch Institution v2 (avec discriminant `type` en Literal).

Vérifie :
- backward-compat : Programme / ElementPedagogiqueFormatif sans institutions
  restent valides, y compris depuis un dict sans la clé (JSON processed
  existants) ;
- les trois sous-types avec leur valeur de `type` sérialisée ;
- l'ALLER-RETOUR JSON : après model_dump puis revalidation, le sous-type
  exact est retrouvé grâce au discriminant ;
- le modèle strict refuse toujours champs inconnus et `type` incohérent.
"""

import pytest
from pydantic import ValidationError

from app.models.curriculum_models import (
    ElementPedagogiqueFormatif,
    Institution,
    InstitutionDiplomante,
    InstitutionMobilite,
    Programme,
)


# ---------------------------------------------------------------------------
# Backward-compatibilité (sources existantes)
# ---------------------------------------------------------------------------

def test_programme_sans_institutions_reste_valide():
    prog = Programme(id="BUT_INFO", nom="BUT Informatique")

    assert prog.institutions == []


def test_programme_depuis_dict_sans_cle_institutions():
    """Un JSON processed existant (sans la clé 'institutions') se
    revalide sans erreur — aucun besoin de relancer le pipeline."""
    data = {
        "id": "USMB_DROIT",
        "nom": "Licence Droit",
        "type": "Licence",
        "niveau": "Bac+3",
        "ects_total": 180.0,
        "duree": 3,
        "periodes": [],
    }
    prog = Programme(**data)

    assert prog.institutions == []


def test_element_formatif_sans_institutions_reste_valide():
    ec = ElementPedagogiqueFormatif(id="S1_INTRO", nom="Introduction")

    assert ec.institutions == []
    assert ec.volume_total == 0.0


# ---------------------------------------------------------------------------
# Nouveaux usages (préparation UNITA)
# ---------------------------------------------------------------------------

def test_programme_avec_institution_diplomante():
    prog = Programme(
        id="UNITA_X",
        nom="Programme UNITA",
        institutions=[InstitutionDiplomante(nom="Université Savoie Mont Blanc")],
    )

    assert len(prog.institutions) == 1
    assert prog.institutions[0].nom == "Université Savoie Mont Blanc"
    assert prog.institutions[0].type == "diplomante"
    assert isinstance(prog.institutions[0], Institution)


def test_element_formatif_avec_institution_mobilite():
    ec = ElementPedagogiqueFormatif(
        id="S2_MOB",
        nom="Module de mobilité",
        credits=3.0,
        institutions=[InstitutionMobilite(nom="Universidade Beira Interior")],
    )

    assert len(ec.institutions) == 1
    assert ec.institutions[0].type == "mobilite"
    assert isinstance(ec.institutions[0], Institution)


def test_institutions_mixtes_et_model_dump():
    """Plusieurs institutions ; model_dump sérialise nom ET type."""
    prog = Programme(
        id="UNITA_Y",
        nom="Programme mixte",
        institutions=[
            InstitutionDiplomante(nom="USMB"),
            InstitutionMobilite(nom="Universidad de Zaragoza"),
            Institution(nom="Partenaire générique"),
        ],
    )
    dump = prog.model_dump()

    assert dump["institutions"][0] == {"nom": "USMB", "type": "diplomante"}
    assert dump["institutions"][1] == {"nom": "Universidad de Zaragoza",
                                       "type": "mobilite"}
    assert dump["institutions"][2] == {"nom": "Partenaire générique",
                                       "type": "institution"}


def test_round_trip_json_conserve_le_sous_type():
    """Le point clé du discriminant : dump -> revalidation -> le sous-type
    exact est retrouvé (impossible sans le champ `type`)."""
    prog = Programme(
        id="UNITA_Z",
        nom="Round trip",
        institutions=[
            InstitutionDiplomante(nom="USMB"),
            InstitutionMobilite(nom="UPNA"),
            Institution(nom="Partenaire"),
        ],
    )
    reloaded = Programme(**prog.model_dump())

    assert isinstance(reloaded.institutions[0], InstitutionDiplomante)
    assert isinstance(reloaded.institutions[1], InstitutionMobilite)
    assert type(reloaded.institutions[2]) is Institution
    assert [i.type for i in reloaded.institutions] == [
        "diplomante", "mobilite", "institution",
    ]


def test_institution_ambiguous_dict_defaults_to_generique():
    """Une entrée sans champ `type` (dict incomplet, ex. saisie manuelle ou
    ancienne donnée partielle) doit être résolue comme Institution générique,
    jamais supposée diplômante ou de mobilité par défaut. Ce comportement
    dépend de l'ordre du Union : Institution doit être en première position."""
    prog = Programme(
        id="UNITA_AMBIGU",
        nom="Cas ambigu",
        institutions=[{"nom": "Sans type précisé"}],
    )

    assert type(prog.institutions[0]) is Institution
    assert prog.institutions[0].type == "institution"


# ---------------------------------------------------------------------------
# Le modèle reste strict
# ---------------------------------------------------------------------------

def test_institution_refuse_champ_inconnu():
    with pytest.raises(ValidationError):
        Institution(nom="USMB", pays="France")  # extra="forbid"


def test_institution_nom_obligatoire():
    with pytest.raises(ValidationError):
        InstitutionDiplomante()


def test_type_incoherent_refuse():
    """Le Literal verrouille la valeur : impossible de créer une
    InstitutionDiplomante avec type='mobilite'."""
    with pytest.raises(ValidationError):
        InstitutionDiplomante(nom="USMB", type="mobilite")