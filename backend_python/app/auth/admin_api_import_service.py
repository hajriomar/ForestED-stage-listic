"""
Service d'import d'une source depuis une API JSON externe.

Flux (identique à l'upload fichier, pour traçabilité et reproductibilité) :
    fetch API (GET) -> validation JSON -> sauvegarde dans raw/
    -> process_file (CE fichier uniquement) -> processed + analytics

Sécurité :
- schémas http/https uniquement (file://, ftp://... refusés) ;
- protection SSRF réelle : le nom d'hôte est RÉSOLU en DNS et toutes les
  adresses obtenues doivent être publiques (loopback, privées 10/172.16-31/
  192.168, link-local, réservées... refusées) — vérifier la chaîne de l'URL
  ne suffit pas, un domaine public peut résoudre vers 127.0.0.1 ;
- redirections refusées (une redirection pourrait pointer vers l'interne) ;
- timeout 10 s, taille max 20 Mo lue en flux ;
- les headers sensibles (Authorization, API-Key, X-API-Key, Cookie)
  ne sont JAMAIS loggés ;
- aucun fichier raw partiel en cas d'échec ; raw supprimé si le pipeline
  rejette le contenu.
"""

import ipaddress
import json
import logging
import socket
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import RAW_DATA_FOLDER
from app.etl.pipeline import process_file

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
MAX_BYTES = 20 * 1024 * 1024  # 20 Mo, comme l'upload fichier

SENSITIVE_HEADERS = {"authorization", "api-key", "x-api-key", "cookie"}


class ApiImportError(Exception):
    """Erreur d'import API, avec code HTTP à retourner au client."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def safe_header_names(headers) -> list:
    """Noms de headers loggables (jamais les valeurs, jamais les sensibles)."""
    return sorted(
        name for name in (headers or {})
        if name.lower() not in SENSITIVE_HEADERS
    )


# ──────────────────────────────────────────────────────────────────────────
# 1. Validation de l'URL (anti-SSRF)
# ──────────────────────────────────────────────────────────────────────────

def validate_api_url(url: str) -> None:
    parsed = urlparse((url or "").strip())

    if parsed.scheme not in ("http", "https"):
        raise ApiImportError(
            "URL interdite : seuls les schémas http et https sont autorisés."
        )

    host = parsed.hostname
    if not host:
        raise ApiImportError("URL invalide : hôte manquant.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # Résolution DNS : TOUTES les adresses doivent être publiques.
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ApiImportError(f"Hôte introuvable (DNS) : {host}") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            logger.warning(
                "Import API refusé (SSRF) : %s résout vers %s", host, ip,
            )
            raise ApiImportError(
                "URL interdite : l'hôte résout vers une adresse locale ou "
                "privée (protection SSRF)."
            )


# ──────────────────────────────────────────────────────────────────────────
# 2. Récupération du JSON (GET, flux, taille bornée)
# ──────────────────────────────────────────────────────────────────────────

def fetch_json_from_api(url: str, headers=None,
                        timeout: float = TIMEOUT_SECONDS,
                        max_bytes: int = MAX_BYTES) -> bytes:
    """GET l'URL et retourne les octets d'une réponse JSON valide."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            with client.stream("GET", url, headers=headers or {}) as response:

                if 300 <= response.status_code < 400:
                    raise ApiImportError(
                        "Redirection refusée (protection SSRF) : "
                        "utilisez l'URL finale.", 400,
                    )
                if response.status_code >= 400:
                    raise ApiImportError(
                        f"API inaccessible : réponse HTTP "
                        f"{response.status_code}.", 502,
                    )

                content = b""
                for chunk in response.iter_bytes():
                    content += chunk
                    if len(content) > max_bytes:
                        raise ApiImportError(
                            "Réponse trop volumineuse (max 20 Mo).", 413,
                        )

    except ApiImportError:
        raise
    except httpx.TimeoutException as exc:
        raise ApiImportError(
            "API inaccessible : délai dépassé (10 s).", 504,
        ) from exc
    except httpx.HTTPError as exc:
        raise ApiImportError(
            f"API inaccessible : {exc.__class__.__name__}.", 502,
        ) from exc

    # Content-Type application/json OU contenu parseable en JSON
    try:
        json.loads(content)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiImportError(
            "La réponse de l'API n'est pas du JSON valide.", 422,
        ) from exc

    return content


# ──────────────────────────────────────────────────────────────────────────
# 3. Sauvegarde dans raw/ (mêmes règles que l'upload fichier)
# ──────────────────────────────────────────────────────────────────────────

def _sanitize_stem(stem: str) -> str:
    import re
    cleaned = re.sub(r"[^A-Za-z0-9_\-]+", "_", stem).strip("_")
    return cleaned or "api"


def save_api_json_to_raw(domain: str, source_name: str,
                         formation_name: str, output_filename,
                         content: bytes) -> Path:
    """Écrit le JSON dans raw/{domain}/{source}/{FORMATION}_{nom}.json."""
    if output_filename:
        stem = Path(str(output_filename)).stem  # neutralise ../, /, \\
        stem = _sanitize_stem(stem)
    else:
        stem = f"api_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    final_name = f"{formation_name}_{stem}.json"  # extension .json forcée

    target_dir = (Path(RAW_DATA_FOLDER) / domain / source_name).resolve()
    destination = (target_dir / final_name).resolve()

    if destination.parent != target_dir:
        raise ApiImportError("Chemin de destination invalide.")

    if destination.exists():
        raise ApiImportError(
            f"Le fichier {final_name} existe déjà dans "
            f"{domain}/{source_name}. Choisissez un autre nom de sortie.",
            409,
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


# ──────────────────────────────────────────────────────────────────────────
# 4. Orchestration complète
# ──────────────────────────────────────────────────────────────────────────

def import_api_source_and_process(domain: str, source_name: str,
                                  formation_name: str, url: str,
                                  headers=None, output_filename=None) -> dict:
    """fetch API -> save raw -> process_file (ce fichier UNIQUEMENT)."""
    validate_api_url(url)

    content = fetch_json_from_api(url, headers=headers)

    destination = save_api_json_to_raw(
        domain, source_name, formation_name, output_filename, content,
    )
    logger.info(
        "Import API : %s/%s/%s sauvegardé (%d octets, headers=%s)",
        domain, source_name, destination.name, len(content),
        safe_header_names(headers),
    )

    try:
        process_file(domain, source_name, destination)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        logger.error(
            "Pipeline a rejeté l'import API %s (raw supprimé) : %s",
            destination.name, exc,
        )
        raise ApiImportError(
            f"Fichier rejeté par le pipeline : {exc}", 422,
        ) from exc

    stem = destination.stem
    return {
        "message": "API source imported and processed successfully",
        "raw_file": f"{domain}/{source_name}/{destination.name}",
        "processed_file": f"processed/{domain}/{source_name}/"
                          f"{stem}_processed.json",
        "analytics_file": f"analytics/{domain}/{source_name}/"
                          f"{stem}_flat.json",
    }