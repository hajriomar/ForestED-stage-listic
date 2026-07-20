"""
Configuration module for ForestED Backend
"""
import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "app" / "data"

RAW_DATA_FOLDER = os.getenv("RAW_DATA_FOLDER", str(DATA_DIR / "raw"))
PROCESSED_DATA_FOLDER = os.getenv("PROCESSED_DATA_FOLDER", str(DATA_DIR / "processed"))
ANALYTICS_DATA_FOLDER = os.getenv("ANALYTICS_DATA_FOLDER", str(DATA_DIR / "analytics"))

# Application
APP_NAME = os.getenv("APP_NAME", "ForestED Backend")
APP_ENV = os.getenv("APP_ENV", "development")
IS_PRODUCTION = APP_ENV == "production"

# Hôtes autorisés (TrustedHostMiddleware — Patch A).
# En production : TRUSTED_HOSTS=api.mondomaine.fr,app.mondomaine.fr
# Les hosts INTERNES (localhost, 127.0.0.1, backend — appels Dash->backend
# et healthchecks Docker, plus "testserver" pour pytest) sont TOUJOURS
# ajoutés à la liste : les oublier dans TRUSTED_HOSTS casserait le
# dashboard en production sans que rien ne le signale.
_INTERNAL_HOSTS = ["localhost", "127.0.0.1", "backend", "testserver"]
_env_hosts = [h.strip() for h in os.getenv("TRUSTED_HOSTS", "").split(",")
              if h.strip()]
TRUSTED_HOSTS = _env_hosts + [h for h in _INTERNAL_HOSTS
                              if h not in _env_hosts]
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# API
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./forested.db")

# Security
# AUTH_SECRET_KEY (nouveau nom) prioritaire, SECRET_KEY (ancien nom) accepte.
SECRET_KEY = (
    os.getenv("AUTH_SECRET_KEY")
    or os.getenv("SECRET_KEY")
    or "change-me-in-production"
)
ALGORITHM = os.getenv("AUTH_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
API_KEY_PREFIX = os.getenv("API_KEY_PREFIX", "fed_")

# Refuse les secrets par defaut en production
if APP_ENV == "production" and SECRET_KEY == "change-me-in-production":
    raise RuntimeError(
        "AUTH_SECRET_KEY (ou SECRET_KEY) must be set via environment "
        "variable in production."
    )

# Supported domains
SUPPORTED_DOMAINS = ["competence", "curriculum"]