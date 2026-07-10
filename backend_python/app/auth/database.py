"""
Base de données du module auth.

SQLite en dev (DATABASE_URL par défaut), PostgreSQL en production
via la variable d'environnement DATABASE_URL.

Création des tables via create_all + migrations légères additives
(nouvelles colonnes avec défaut). Alembic prendra le relais en
pré-production avec une baseline couvrant le schéma complet.
"""

import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

# check_same_thread=False requis pour SQLite avec FastAPI (multi-thread)
_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency FastAPI : fournit une session DB fermée après la requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _apply_light_migrations() -> None:
    """Migrations additives simples (colonnes avec défaut) sur base existante.

    create_all ne modifie jamais une table existante : on ajoute ici les
    colonnes introduites après coup, de façon idempotente.
    """
    inspector = inspect(engine)

    if "api_keys" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("api_keys")}
        if "kind" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE api_keys "
                    "ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'data'"
                ))
            logger.info(
                "Migration légère : colonne api_keys.kind ajoutée "
                "(clés existantes -> kind='data')."
            )


def init_db() -> None:
    """Crée les tables auth si elles n'existent pas + migrations légères."""
    # Import local pour enregistrer les modèles sur Base
    # sans créer d'import circulaire.
    from app.auth import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_light_migrations()
    logger.info("Auth database initialized (%s)", engine.url.drivername)