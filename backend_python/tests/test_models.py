"""
Tests des méta-modèles Pydantic ForestED (compétences et curriculum).

Version alignée sur les modèles actuels :
- ApprentissageCritique : code (pas id), description, modules
- Competence : composantes_essentielles, situations_professionnelles,
  niveaux_developpement
- ReferentielCompetences : intitule, sous_classifications
- ElementPedagogiqueFormatif : credits, cm/td/tp/projet,
  volume_total calculé automatiquement
"""

import pytest
from pydantic import ValidationError

from app.models.competency_models import (
    ApprentissageCritique,
    Competence,
    ComposanteEssentielle,
    NiveauDeveloppement,
    ReferentielCompetences,
    SousClassification,
)
from app.models.curriculum_models import (
    ElementPedagogiqueFormatif,
    Enseignant,
    PeriodeProgramme,
    Programme,
)


class TestCompetencyModels:

    def test_apprentissage_critique_creation(self):
        ac = ApprentissageCritique(
            code="AC001",
            description="Analyser un besoin client",
            modules=["MOD1", "MOD2"],
        )
        assert ac.code == "AC001"
        assert ac.modules == ["MOD1", "MOD2"]

    def test_niveau_developpement_creation(self):
        ac = ApprentissageCritique(code="AC001", description="Test")
        niveau = NiveauDeveloppement(
            niveau=1,
            description="Niveau de base",
            apprentissages_critiques=[ac],
        )
        assert niveau.niveau == 1
        assert len(niveau.apprentissages_critiques) == 1
        assert niveau.apprentissages_critiques[0].code == "AC001"

    def test_competence_creation(self):
        competence = Competence(
            code="COMP1",
            nom="Concevoir",
            definition="Concevoir des solutions techniques",
            composantes_essentielles=[
                ComposanteEssentielle(code="CE1", formulation="En autonomie")
            ],
            niveaux_developpement=[],
        )
        assert competence.code == "COMP1"
        assert competence.composantes_essentielles[0].code == "CE1"
        assert competence.niveaux_developpement == []

    def test_referentiel_competences_creation(self):
        ref = ReferentielCompetences(
            intitule="Referentiel IDU",
            sous_classifications=[
                SousClassification(code="SC1", nom="Tronc commun", competences=[])
            ],
        )
        assert ref.intitule == "Referentiel IDU"
        assert len(ref.sous_classifications) == 1


class TestCurriculumModels:

    def test_enseignant_creation(self):
        ens = Enseignant(
            id="ENS1",
            nom="Dupont",
            email="dupont@univ.fr",
            role="responsable",
        )
        assert ens.nom == "Dupont"

    def test_element_pedagogique_creation(self):
        elem = ElementPedagogiqueFormatif(
            id="EP1",
            nom="Programmation",
            credits=3.0,
            cm=24.0,
            td=12.0,
            tp=12.0,
            projet=0.0,
        )
        assert elem.credits == 3.0
        # volume_total est calculé automatiquement (cm + td + tp + projet)
        assert elem.volume_total == 48.0

    def test_element_pedagogique_negative_hours_validation(self):
        with pytest.raises(ValidationError):
            ElementPedagogiqueFormatif(
                id="EP1",
                nom="Programmation",
                cm=-5.0,
            )

    def test_programme_creation(self):
        programme = Programme(
            id="BUT_QLIO",
            nom="BUT QLIO",
            type="BUT",
            ects_total=180.0,
            duree=6,
            periodes=[PeriodeProgramme(id="S1", numero=1, ects=30.0)],
        )
        assert programme.id == "BUT_QLIO"
        assert programme.periodes[0].numero == 1


class TestValidation:

    def test_strict_model_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            Enseignant(
                id="ENS1",
                nom="Dupont",
                champ_inconnu="interdit",
            )