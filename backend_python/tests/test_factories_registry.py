"""
Tests R1 — registry déclarative des factories ETL.

Vérifie :
- les 4 couples (domain, source) existants retournent le bon transformer ;
- normalisation strip/lower ("  Polytech " == "polytech") ;
- source inconnue -> ValueError explicite listant les couples connus ;
- NormalizerFactory : normalizers dédiés + Passthrough conservé pour
  les couples sans normalizer (JAMAIS d'erreur) ;
- known_sources() expose les couples supportés.

Lancer depuis backend_python :
    python -m pytest tests/test_factories_registry.py -v
"""

import pytest

from app.etl.normalize.normalizer_factory import (
    NormalizerFactory,
    PassthroughNormalizer,
)
from app.etl.transform.transformer_factory import TransformerFactory


# =====================================================
# TransformerFactory — couples existants (non-régression)
# =====================================================

def test_transformer_competence_polytech():
    from app.etl.transform.competence.Polytech_competence_transformer import (
        PolytechTransformer,
    )
    assert isinstance(
        TransformerFactory.get_transformer("competence", "Polytech"),
        PolytechTransformer,
    )


def test_transformer_competence_but():
    from app.etl.transform.competence.BUT_competence_transformer import (
        BUTCompetenceTransformer,
    )
    assert isinstance(
        TransformerFactory.get_transformer("competence", "BUT"),
        BUTCompetenceTransformer,
    )


def test_transformer_curriculum_polytech():
    from app.etl.transform.curriculum.Polytech_curriculum_transformer import (
        PolytechCurriculumTransformer,
    )
    assert isinstance(
        TransformerFactory.get_transformer("curriculum", "polytech"),
        PolytechCurriculumTransformer,
    )


def test_transformer_curriculum_but():
    from app.etl.transform.curriculum.BUT_curriculum_transformer import (
        BUTCurriculumTransformer,
    )
    assert isinstance(
        TransformerFactory.get_transformer("curriculum", "but"),
        BUTCurriculumTransformer,
    )


def test_normalisation_strip_lower():
    """'  POLYTECH  ' et 'polytech' désignent la même source (idem avant R1)."""
    t1 = TransformerFactory.get_transformer("  Competence ", "  POLYTECH  ")
    t2 = TransformerFactory.get_transformer("competence", "polytech")
    assert type(t1) is type(t2)


# =====================================================
# TransformerFactory — source inconnue : erreur explicite
# =====================================================

def test_unknown_source_error_message():
    with pytest.raises(ValueError) as exc:
        TransformerFactory.get_transformer("curriculum", "unita")
    msg = str(exc.value)
    assert "No transformer registered for domain='curriculum', source='unita'" in msg
    assert "Known transformers:" in msg
    # Les 4 couples connus sont listés
    for known in ("competence/but", "competence/polytech",
                  "curriculum/but", "curriculum/polytech"):
        assert known in msg


def test_unknown_domain_error():
    with pytest.raises(ValueError):
        TransformerFactory.get_transformer("evaluation", "but")


def test_known_sources_and_is_supported():
    assert TransformerFactory.known_sources() == [
        "competence/but",
        "competence/polytech",
        "competence/usmb_licence",
        "curriculum/but",
        "curriculum/polytech",
        "curriculum/usmb_licence",
    ]
    assert TransformerFactory.is_supported("Curriculum", " BUT ")
    assert not TransformerFactory.is_supported("curriculum", "unita")


# =====================================================
# NormalizerFactory — dédiés + passthrough conservé
# =====================================================

def test_normalizer_competence_but():
    from app.etl.normalize.but_competence_normalizer import (
        BUTCompetenceNormalizer,
    )
    assert isinstance(
        NormalizerFactory.get_normalizer("competence", "BUT"),
        BUTCompetenceNormalizer,
    )


def test_normalizer_competence_polytech():
    from app.etl.normalize.polytech_competence_normalizer import (
        PolytechCompetenceNormalizer,
    )
    assert isinstance(
        NormalizerFactory.get_normalizer("competence", "Polytech"),
        PolytechCompetenceNormalizer,
    )


def test_normalizer_unknown_source_is_passthrough_never_raises():
    """Comportement conservé : source inconnue -> Passthrough, pas d'erreur.
    (C'est le TRANSFORMER qui refuse les sources inconnues.)"""
    for domain, source in [("curriculum", "but"), ("curriculum", "polytech"),
                           ("curriculum", "unita"), ("competence", "unita")]:
        norm = NormalizerFactory.get_normalizer(domain, source)
        assert isinstance(norm, PassthroughNormalizer)


def test_passthrough_unwraps_json_envelope():
    """Non-régression du dépliage d'enveloppe JSON (fix Polytech)."""
    norm = PassthroughNormalizer()

    out = norm.normalize(
        {"file_type": "json", "file_name": "IDU_x.json",
         "content": {"fiches": [{"code": "IDU301"}]}}
    )
    assert out["fiches"] == [{"code": "IDU301"}]
    assert out["file_name"] == "IDU_x.json"

    out_list = norm.normalize(
        {"file_type": "json", "file_name": "x.json", "content": [1, 2]}
    )
    assert out_list == [1, 2]

    excel = {"file_type": "excel", "sheets": []}
    assert norm.normalize(excel) is excel