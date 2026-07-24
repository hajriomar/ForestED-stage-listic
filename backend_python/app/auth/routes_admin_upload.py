"""
Routes admin d'ajout de fichiers sources.

POST /admin/sources/upload      : téléverser un fichier local
                                  (.json/.xlsx/.xls/.csv, max 20 Mo)
POST /admin/sources/import-api  : importer un JSON depuis une API externe
                                  (GET uniquement, anti-SSRF, max 20 Mo)

Dans les deux cas : sauvegarde dans raw/{domain}/{source}/, puis
traitement du SEUL fichier créé via process_file — JAMAIS de run global,
les autres fichiers/sources/domaines et leurs outputs ne sont pas touchés.
Échec du pipeline -> fichier raw supprimé + 422 clair.
Fichier existant -> 409, pas d'écrasement silencieux.

Réservé au rôle admin (require_admin) : viewer -> 403,
API key / invité / lien partagé -> 403, sans token -> 401.
"""

import logging
import re
from pathlib import Path
from typing import Dict, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.auth import admin_api_import_service as api_import
from app.auth.dependencies import require_admin
from app.auth.models import User
from app.config import RAW_DATA_FOLDER, SUPPORTED_DOMAINS
from app.etl.pipeline import process_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

ALLOWED_EXTENSIONS = {".json", ".xlsx", ".xls", ".csv"}
MAX_UPLOAD_MB = 20

# Composants de chemin sûrs : alphanumérique, tiret, underscore.
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")


def _validate_component(value: str, label: str) -> str:
    """Valide un composant de chemin (source_name, formation_name)."""
    value = (value or "").strip()
    if not value or not _SAFE_COMPONENT.match(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} invalide : caractères autorisés "
                   f"A-Z a-z 0-9 _ - (reçu : {value!r})",
        )
    return value


def _validate_domain(domain: str) -> str:
    domain = (domain or "").strip().lower()
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Domaine inconnu : {domain!r}. "
                   f"Attendu : {SUPPORTED_DOMAINS}",
        )
    return domain


def _sanitize_stem(stem: str) -> str:
    """Nettoie le nom de fichier original (sans extension)."""
    cleaned = re.sub(r"[^A-Za-z0-9_\-]+", "_", stem).strip("_")
    return cleaned or "fichier"


# ══════════════════════════════════════════════════════════════════════════
#  Upload d'un fichier local
# ══════════════════════════════════════════════════════════════════════════

@router.post("/sources/upload")
async def upload_source(
    domain: str = Form(...),
    source_name: str = Form(...),
    formation_name: str = Form(...),
    institution: Optional[str] = Form(None),
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
) -> dict:
    """Téléverse un fichier source et traite UNIQUEMENT ce fichier.

    `institution` (optionnel) : laissé vide -> curriculum générique ;
    renseigné (ex. USMB, HESSO, UPPA) -> partie institution-specific.
    N'a d'effet que pour les sources qui l'exploitent (curriculum/unita)."""

    # --- Validations ------------------------------------------------------
    domain = _validate_domain(domain)
    source_name = _validate_component(source_name, "source_name")
    formation_name = _validate_component(formation_name, "formation_name")

    institution = (institution or "").strip()
    if institution and not _SAFE_COMPONENT.match(institution):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Institution invalide : lettres/chiffres/_/- uniquement "
                   "(ex. USMB, HESSO, UPPA). Laissez vide pour le générique.",
        )

    original = Path(file.filename or "")
    extension = original.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extension non autorisée : {extension or '(aucune)'}. "
                   f"Formats acceptés : {sorted(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Fichier trop volumineux (max {MAX_UPLOAD_MB} Mo).",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fichier vide.",
        )

    # --- Chemin de destination (défense en profondeur) --------------------
    final_name = f"{formation_name}_{_sanitize_stem(original.stem)}{extension}"

    target_dir = (Path(RAW_DATA_FOLDER) / domain / source_name).resolve()
    destination = (target_dir / final_name).resolve()

    if destination.parent != target_dir:
        # Impossible après validation, mais on ne fait jamais confiance
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chemin de destination invalide.",
        )

    if destination.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Le fichier {final_name} existe déjà dans "
                   f"{domain}/{source_name}. Renommez le fichier ou "
                   f"supprimez l'ancien.",
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    logger.info(
        "Upload par admin=%s : %s/%s/%s (%d octets)",
        admin.username, domain, source_name, final_name, len(content),
    )

    # --- Traitement du SEUL fichier uploadé (jamais de run global) --------
    try:
        summary = process_file(
            domain,
            source_name,
            destination,
            institution=institution or None,
            formation=formation_name,
        )
    except Exception as exc:
        # Fichier rejeté : on ne laisse pas un fichier cassé dans raw/
        destination.unlink(missing_ok=True)
        logger.error(
            "Pipeline a rejeté l'upload %s (fichier supprimé de raw/) : %s",
            final_name, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Fichier rejeté par le pipeline : {exc}",
        ) from exc

    stem = destination.stem
    logger.info(
        "Upload traité avec succès : %s (processed + analytics générés)",
        final_name,
    )

    # Réponse historique (status/file/outputs) CONSERVÉE pour compat, +
    # résumé pipeline remonté (curriculum/unita : add/update/scopes/
    # institutions ; autres sources : programme_id/output_path).
    response = {
        "status": "success",
        "file": f"{domain}/{source_name}/{final_name}",
        "outputs": {
            "processed": f"processed/{domain}/{source_name}/"
                         f"{stem}_processed.json",
            "analytics": f"analytics/{domain}/{source_name}/"
                         f"{stem}_flat.json",
        },
    }
    if isinstance(summary, dict):
        response["domain"] = summary.get("domain", domain)
        response["source"] = summary.get("source", source_name)
        response["programme_id"] = summary.get("programme_id")
        for key in ("output_path", "added", "updated", "total_elements",
                    "scopes", "institutions", "quality_summary"):
            if key in summary:
                response[key] = summary[key]
    return response


# ══════════════════════════════════════════════════════════════════════════
#  Import depuis une API JSON externe
# ══════════════════════════════════════════════════════════════════════════

class ApiImportRequest(BaseModel):
    domain: str
    source_name: str
    formation_name: str
    url: str = Field(..., min_length=8)
    method: Literal["GET"] = "GET"       # v1 : GET uniquement
    output_filename: Optional[str] = None
    headers: Optional[Dict[str, str]] = None


@router.post("/sources/import-api")
def import_api_source(
    payload: ApiImportRequest,
    admin: User = Depends(require_admin),
) -> dict:
    """Importe un JSON depuis une API externe et traite UNIQUEMENT
    le fichier créé (voir admin_api_import_service pour la sécurité)."""

    domain = _validate_domain(payload.domain)
    source_name = _validate_component(payload.source_name, "source_name")
    formation_name = _validate_component(
        payload.formation_name, "formation_name")

    # Log SANS les valeurs de headers, et jamais les headers sensibles
    logger.info(
        "Import API demandé par admin=%s : %s/%s/%s url=%s headers=%s",
        admin.username, domain, source_name, formation_name,
        payload.url, api_import.safe_header_names(payload.headers),
    )

    try:
        result = api_import.import_api_source_and_process(
            domain=domain,
            source_name=source_name,
            formation_name=formation_name,
            url=payload.url,
            headers=payload.headers,
            output_filename=payload.output_filename,
        )
    except api_import.ApiImportError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=str(exc),
        ) from exc

    logger.info(
        "Import API traité avec succès : %s", result["raw_file"],
    )
    return result


@router.get("/sources/supported")
def supported_sources(admin: User = Depends(require_admin)):
    """
    Sources supportées par le pipeline (registry des transformers).

    Utilisé par la page admin pour proposer une nouvelle source dans le
    dropdown d'upload AVANT son premier fichier (ex. usmb_licence).
    Import paresseux : cohérent avec la philosophie de la factory.
    """
    from app.etl.transform.transformer_factory import TRANSFORMERS

    by_domain: dict = {}
    for (domain, source) in TRANSFORMERS:
        by_domain.setdefault(domain, set()).add(source)

    return {
        "sources": sorted({s for (_d, s) in TRANSFORMERS}),
        "by_domain": {d: sorted(s) for d, s in by_domain.items()},
    }