"""
api_client.py — client HTTP vers l'API FastAPI sécurisée.

Deux modes d'authentification (exclusifs) :
- token   : JWT d'un utilisateur connecté  -> Authorization: Bearer
- api_key : clé d'accès invité (dashboard) -> X-API-Key

Erreurs typées :
    AuthExpired    : 401 (token/clé absents, expirés, révoqués) -> retour login
    Forbidden      : 403 (authentifié mais interdit)
    ApiUnavailable : backend injoignable
    ApiError       : autres erreurs (409, 422...), message affichable.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

API_BASE_URL = os.getenv("API_BASE_URL", "http://backend:8000")
TIMEOUT = float(os.getenv("API_TIMEOUT_SECONDS", "15"))
# L'upload traite le fichier dans la requête (pipeline) : délai plus long.
UPLOAD_TIMEOUT = float(os.getenv("API_UPLOAD_TIMEOUT_SECONDS", "120"))


class ApiError(Exception):
    """Erreur générique de l'API (le message est affichable à l'utilisateur)."""


class AuthExpired(ApiError):
    """401 : token/clé absent, expiré, révoqué ou invalide."""


class Forbidden(ApiError):
    """403 : authentifié mais accès interdit."""


class ApiUnavailable(ApiError):
    """Backend injoignable (connexion, timeout)."""


def _detail(response) -> str:
    try:
        detail = response.json().get("detail")
    except Exception:
        detail = None
    if detail is None:
        return f"Erreur API {response.status_code}"
    return detail if isinstance(detail, str) else str(detail)


def _auth_headers(token=None, api_key=None) -> dict:
    if api_key:
        return {"X-API-Key": api_key}
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _map_errors(response) -> dict:
    if response.status_code == 401:
        raise AuthExpired(_detail(response))
    if response.status_code == 403:
        raise Forbidden(_detail(response))
    if response.status_code >= 400:
        raise ApiError(_detail(response))
    return response.json()


def _request(method: str, path: str, token=None, api_key=None,
             json_body=None) -> dict:
    """Requête authentifiée générique avec mapping d'erreurs."""
    try:
        response = requests.request(
            method,
            f"{API_BASE_URL}{path}",
            headers=_auth_headers(token, api_key),
            json=json_body,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.error("API injoignable (%s %s) : %s", method, path, exc)
        raise ApiUnavailable("Le serveur de données est indisponible.") from exc

    return _map_errors(response)


def _get(path: str, token=None, api_key=None) -> dict:
    return _request("GET", path, token=token, api_key=api_key)


# =====================================================
# Authentification
# =====================================================

def login(username: str, password: str) -> dict:
    """Tente un login. Retourne {"ok": True, "token": ...}
    ou {"ok": False, "error": message}. Lève ApiUnavailable si backend down."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            data={"username": username, "password": password},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.error("API injoignable (login) : %s", exc)
        raise ApiUnavailable(str(exc)) from exc

    if response.status_code == 200:
        return {"ok": True, "token": response.json()["access_token"]}

    if response.status_code in (401, 403):
        return {"ok": False, "error": _detail(response)}

    return {"ok": False, "error": f"Erreur serveur ({response.status_code})"}


def get_me(token: str) -> dict:
    """Profil de l'utilisateur courant ({id, username, email, role, ...})."""
    return _get("/auth/me", token=token)


def get_key_info(api_key: str) -> dict:
    """Valide une clé et retourne {name, kind, sources}.

    Lève AuthExpired si la clé est inconnue, révoquée ou expirée.
    Utilisé pour ouvrir/valider une session invitée (dashboard partagé).
    """
    return _get("/auth/key-info", api_key=api_key)


# =====================================================
# Données (filtrées par source côté backend)
# =====================================================

def get_competences(token=None, api_key=None) -> dict:
    return _get("/competences", token=token, api_key=api_key)


def get_curricula(token=None, api_key=None) -> dict:
    return _get("/curricula", token=token, api_key=api_key)


def _to_frontend_items(api_response: dict, domain: str) -> list:
    """Convertit une réponse API vers le format historique du frontend.

    API  : {"status", "count", "data": [{source, programme, file, data}]}
    Dash : [{domain, source, programme, file_name, path, data}]
    """
    items = []
    for item in api_response.get("data", []):
        items.append({
            "domain": domain,
            "source": item.get("source", ""),
            "programme": item.get("programme", ""),   # informatif uniquement
            "file_name": item.get("file", ""),        # mapping file -> file_name
            "path": "",                               # plus de chemin disque
            "data": item.get("data"),
        })
    return items


def load_processed_files_from_api(token=None, api_key=None) -> dict:
    """Équivalent API de l'ancien app_tools.load_processed_files().

    Retourne exactement le même format :
        {"competence": [items], "curriculum": [items]}
    Les données sont déjà filtrées par source selon les droits
    du token OU de la clé d'accès invité.
    """
    return {
        "competence": _to_frontend_items(
            get_competences(token=token, api_key=api_key), "competence"),
        "curriculum": _to_frontend_items(
            get_curricula(token=token, api_key=api_key), "curriculum"),
    }


# =====================================================
# Administration (routes /admin/*, rôle admin requis —
# le backend re-vérifie chaque appel de toute façon)
# =====================================================

def admin_list_users(token: str) -> list:
    return _get("/admin/users", token=token)


def admin_create_user(token: str, username: str, email: str,
                      password: str, role: str) -> dict:
    return _request("POST", "/admin/users", token=token, json_body={
        "username": username, "email": email,
        "password": password, "role": role,
    })


def admin_update_user(token: str, user_id: int, fields: dict) -> dict:
    return _request("PATCH", f"/admin/users/{user_id}", token=token,
                    json_body=fields)


def admin_delete_user(token: str, user_id: int) -> dict:
    return _request("DELETE", f"/admin/users/{user_id}", token=token)


def admin_list_permissions(token: str, user_id: int) -> list:
    return _get(f"/admin/users/{user_id}/permissions", token=token)


def admin_upsert_permission(token: str, user_id: int,
                            source_name: str, scopes: list) -> dict:
    return _request("POST", f"/admin/users/{user_id}/permissions",
                    token=token,
                    json_body={"source_name": source_name, "scopes": scopes})


def admin_delete_permission(token: str, permission_id: int) -> dict:
    return _request("DELETE", f"/admin/permissions/{permission_id}",
                    token=token)


def admin_list_api_keys(token: str) -> list:
    return _get("/admin/api-keys", token=token)


def admin_create_api_key(token: str, name: str, expires_in_days,
                         permissions: list, kind: str = "data") -> dict:
    payload = {"name": name, "kind": kind, "permissions": permissions}
    if expires_in_days:
        payload["expires_in_days"] = int(expires_in_days)
    return _request("POST", "/admin/api-keys", token=token,
                    json_body=payload)


def admin_revoke_api_key(token: str, api_key_id: int) -> dict:
    return _request("DELETE", f"/admin/api-keys/{api_key_id}", token=token)


def admin_upload_source(token: str, domain: str, source_name: str,
                        formation_name: str, filename: str,
                        file_bytes: bytes) -> dict:
    """Téléverse un fichier source ; le backend traite UNIQUEMENT ce
    fichier (process_file), jamais le pipeline complet."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/admin/sources/upload",
            headers=_auth_headers(token=token),
            data={
                "domain": domain,
                "source_name": source_name,
                "formation_name": formation_name,
            },
            files={"file": (filename, file_bytes)},
            timeout=UPLOAD_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.error("API injoignable (upload) : %s", exc)
        raise ApiUnavailable("Le serveur de données est indisponible.") from exc

    return _map_errors(response)