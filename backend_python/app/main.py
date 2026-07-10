import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import (
    ANALYTICS_DATA_FOLDER,
    PROCESSED_DATA_FOLDER,
    SUPPORTED_DOMAINS,
)
from app.etl.pipeline import (
    run_pipeline,
    run_domain_pipeline,
)
from app.auth.database import get_db, init_db
from app.auth.dependencies import (
    Principal,
    get_current_principal,
    require_admin,
)
from app.auth.models import User
from app.auth.permissions import (
    SCOPE_READ_ANALYTICS,
    SCOPE_READ_COMPETENCE,
    SCOPE_READ_CURRICULUM,
    filter_items_by_access,
    get_subject_permissions,
)
from app.auth.routes_auth import router as auth_router
from app.auth.routes_admin_api_keys import router as api_keys_router
from app.auth.routes_admin_users import router as admin_users_router
from app.auth.routes_admin_upload import router as admin_upload_router

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="ForestED Backend API",
    description="API for pedagogical data management",
    version="0.1.0"
)

# Routers
app.include_router(auth_router)
app.include_router(api_keys_router)
app.include_router(admin_users_router)
app.include_router(admin_upload_router)

# ==========================================
# DATA HELPERS
# ==========================================

def extract_programme_from_file_name(file_name: str) -> str:
    """Deduit le programme depuis le nom de fichier.

    Convention projet (identique au frontend app_tools.py) :
    le programme est le premier segment du nom de fichier.
    Ex : QLIO_BUT_referentiel_processed.json -> "QLIO"

    NB : champ purement informatif. L'acces est decide par SOURCE
    uniquement (voir app/auth/permissions.py), jamais par programme.

    TODO: remplacer cette deduction par une metadonnee explicite
    si un fichier contient plusieurs programmes ou si la convention
    de nommage change.
    """
    return file_name.split("_")[0].strip()


def load_domain_files(base_folder: str, domain: str) -> Optional[List[Dict[str, Any]]]:
    """Lit recursivement les JSON d'un domaine ({base}/{domain}/{source}/*.json).

    Returns:
        None si le dossier domaine n'existe pas,
        sinon une liste d'items {source, programme, file, data}.
    """
    import json

    domain_path = Path(base_folder) / domain
    if not domain_path.exists():
        return None

    items: List[Dict[str, Any]] = []
    for file_path in sorted(domain_path.rglob("*.json")):
        relative = file_path.relative_to(domain_path)
        # processed/{domain}/{source}/fichier.json -> source = 1er dossier
        source_name = relative.parts[0] if len(relative.parts) > 1 else "unknown"

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items.append({
            "source": source_name,
            "programme": extract_programme_from_file_name(file_path.name),
            "file": file_path.stem,
            "data": data,
        })

    return items


def domain_data_response(
    base_folder: str,
    domain: str,
    label: str,
    scope: str,
    principal: Principal,
    db: Session,
) -> Dict[str, Any]:
    """Construit la reponse API pour un domaine, filtree selon les droits.

    Filtrage PAR SOURCE uniquement, identique pour un utilisateur (JWT)
    et une API key : le Principal unifie les deux.
    """
    try:
        items = load_domain_files(base_folder, domain)

        if items is None:
            return {
                "status": "no_data",
                "message": f"No {label} data available. Run pipeline first."
            }

        permissions = (
            [] if principal.is_admin
            else get_subject_permissions(
                db, principal.subject_type, principal.subject_id
            )
        )
        allowed = filter_items_by_access(
            items, permissions, scope, is_admin=principal.is_admin
        )

        logger.info(
            "Data access principal=%s domain=%s: %d/%d items autorises",
            principal.name, domain, len(allowed), len(items),
        )

        if not allowed:
            return {"status": "empty", "data": []}

        return {"status": "success", "count": len(allowed), "data": allowed}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving {label} data: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving data"
        )

# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/health", tags=["health"])
async def health_check() -> Dict[str, str]:
    """Health check endpoint (public)."""
    return {"status": "ok", "service": "forested-backend"}

# ==========================================
# PIPELINE ENDPOINTS (admin uniquement)
# ==========================================

@app.post("/pipeline/run", tags=["pipeline"])
async def run_full_pipeline(
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    """Run the complete ETL pipeline for all domains. Admin only."""
    try:
        logger.info("Full ETL pipeline started by admin=%s", admin.username)
        run_pipeline()
        return {
            "status": "success",
            "message": "Pipeline completed successfully"
        }
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Pipeline failed"
        )

@app.post("/pipeline/domain/{domain}", tags=["pipeline"])
async def run_domain_etl(
    domain: str,
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    """Run ETL pipeline for a specific domain. Admin only."""
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown domain: {domain}"
        )

    try:
        logger.info(
            "ETL pipeline for domain=%s started by admin=%s",
            domain, admin.username,
        )
        run_domain_pipeline(domain)
        return {
            "status": "success",
            "message": f"Pipeline for domain '{domain}' completed successfully"
        }
    except Exception as e:
        logger.error(f"Pipeline for {domain} failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Pipeline failed"
        )

# ==========================================
# DATA ENDPOINTS (JWT ou X-API-Key, filtres par source)
# ==========================================

@app.get("/competences", tags=["competence"])
async def get_competences(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get processed competence data (sources autorisees uniquement)."""
    return domain_data_response(
        PROCESSED_DATA_FOLDER, "competence", "competence",
        SCOPE_READ_COMPETENCE, principal, db,
    )

@app.get("/curricula", tags=["curriculum"])
async def get_curricula(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get processed curriculum data (sources autorisees uniquement)."""
    return domain_data_response(
        PROCESSED_DATA_FOLDER, "curriculum", "curriculum",
        SCOPE_READ_CURRICULUM, principal, db,
    )

@app.get("/analytics/{domain}", tags=["analytics"])
async def get_analytics(
    domain: str,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get flattened analytics data (sources autorisees uniquement)."""
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown domain: {domain}"
        )
    return domain_data_response(
        ANALYTICS_DATA_FOLDER, domain, f"analytics/{domain}",
        SCOPE_READ_ANALYTICS, principal, db,
    )

# ==========================================
# ERROR HANDLERS
# ==========================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# ==========================================
# STARTUP/SHUTDOWN
# ==========================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    init_db()
    logger.info("ForestED Backend started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("ForestED Backend stopped")

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))

    logger.info(f"Starting server on {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )