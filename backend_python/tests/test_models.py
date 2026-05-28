"""
Unit tests for ForestED Backend
"""
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from app.models.competency_models import (
    Competence,
    NiveauDeveloppement,
    ApprentissageCritique,
    ReferentielCompetences
)

from app.models.curriculum_models import (
    Programme,
    PeriodeProgramme,
    ElementPedagogique,
    Enseignant
)


class TestCompetencyModels:
    """Tests for competency models."""
    
    def test_apprentissage_critique_creation(self):
        """Test creating an apprentissage critique."""
        ac = ApprentissageCritique(
            id="AC001",
            description="Test apprentissage",
            modules=["MOD1", "MOD2"]
        )
        assert ac.id == "AC001"
        assert ac.description == "Test apprentissage"
        assert len(ac.modules) == 2
    
    def test_niveau_developpement_creation(self):
        """Test creating a niveau developpement."""
        ac = ApprentissageCritique(id="AC001", description="Test")
        niveau = NiveauDeveloppement(
            niveau="Niveau 1",
            apprentissages_critiques=[ac]
        )
        assert niveau.niveau == "Niveau 1"
        assert len(niveau.apprentissages_critiques) == 1
    
    def test_competence_creation(self):
        """Test creating a competence."""
        competence = Competence(
            code="COMP001",
            nom="Data Science",
            niveaux=[]
        )
        assert competence.code == "COMP001"
        assert competence.nom == "Data Science"
    
    def test_referentiel_competences_creation(self):
        """Test creating a referentiel competences."""
        ref = ReferentielCompetences(
            nom="Referentiel IDU",
            competences=[]
        )
        assert ref.nom == "Referentiel IDU"
        assert len(ref.competences) == 0


class TestCurriculumModels:
    """Tests for curriculum models."""
    
    def test_enseignant_creation(self):
        """Test creating an enseignant."""
        ens = Enseignant(
            id="ENS001",
            nom="John Doe",
            email="john@example.com",
            role="Professeur"
        )
        assert ens.id == "ENS001"
        assert ens.nom == "John Doe"
        assert ens.email == "john@example.com"
    
    def test_element_pedagogique_creation(self):
        """Test creating an element pedagogique."""
        elem = ElementPedagogique(
            id="ELEM001",
            nom="Data Structures",
            type="Cours",
            ects=3.0,
            cm=24.0,
            td=12.0,
            tp=12.0,
            projet=0.0
        )
        assert elem.id == "ELEM001"
        assert elem.ects == 3.0
        assert elem.volume_total == 48.0  # cm + td + tp
    
    def test_element_pedagogique_negative_hours_validation(self):
        """Test that negative hours are rejected."""
        with pytest.raises(ValueError):
            ElementPedagogique(
                id="ELEM001",
                nom="Test",
                cm=-5.0
            )
    
    def test_programme_creation(self):
        """Test creating a programme."""
        programme = Programme(
            id="PROG001",
            nom="Ingénierie des Données",
            niveau="Bac+5",
            ects_total=180,
            duree=3
        )
        assert programme.id == "PROG001"
        assert programme.ects_total == 180


class TestValidation:
    """Tests for data validation."""
    
    def test_strict_model_forbids_extra_fields(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(ValueError):
            Competence(
                code="COMP001",
                nom="Test",
                extra_field="should_fail"
            )


# ==========================================
# Integration tests would go here
# ==========================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
