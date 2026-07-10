"""
Route admin d'upload de fichiers sources.

POST /admin/sources/upload (multipart) :
    domain         : "competence" | "curriculum"
    source_name    : source (ex. Polytech, BUT) — [A-Za-z0-9_-] uniquement
    formation_name : préfixe du fichier (ex. SNI, QLIO) — [A-Za-z0-9_-]
    file           : .json / .xlsx / .xls / .csv (max 20 Mo)

Comportement :
1. validations strictes (extension, taille, anti path-traversal) ;
2. sauvegarde sous RAW_DATA_FOLDER/{domain}/{source}/{FORMATION}_{nom}.ext ;
3. traitement du SEUL fichier uploadé via process_file — JAMAIS de run
   global : les autres fichiers, sources et domaines ne sont pas touchés
   et les anciens outputs ne sont pas modifiés ;
4. si le pipeline rejette le fichier : suppression du fichier de raw/
   (pas de fichier cassé qui casserait un futur run complet) + 422 clair ;
5. fichier déjà existant : 409, pas d'écrasement silencieux.

Réservé au rôle admin (require_admin) : viewer -> 403, API key/invité -> 403,
sans token -> 401.
"""

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

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


def _sanitize_stem(stem: str) -> str:
    """Nettoie le nom de fichier original (sans extension)."""
    cleaned = re.sub(r"[^A-Za-z0-9_\-]+", "_", stem).strip("_")
    return cleaned or "fichier"


@router.post("/sources/upload")
async def upload_source(
    domain: str = Form(...),
    source_name: str = Form(...),
    formation_name: str = Form(...),
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
) -> dict:
    """Téléverse un fichier source et traite UNIQUEMENT ce fichier."""

    # --- Validations ------------------------------------------------------
    domain = (domain or "").strip().lower()
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Domaine inconnu : {domain!r}. "
                   f"Attendu : {SUPPORTED_DOMAINS}",
        )

    source_name = _validate_component(source_name, "source_name")
    formation_name = _validate_component(formation_name, "formation_name")

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
        process_file(domain, source_name, destination)
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

    return {
        "status": "success",
        "file": f"{domain}/{source_name}/{final_name}",
        "outputs": {
            "processed": f"processed/{domain}/{source_name}/"
                         f"{stem}_processed.json",
            "analytics": f"analytics/{domain}/{source_name}/"
                         f"{stem}_flat.json",
        },
    }