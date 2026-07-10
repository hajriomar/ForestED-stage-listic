"""
Moteur de décision d'accès ForestED.

Règle métier (v1) :
- L'accès est géré PAR SOURCE uniquement. Un sujet ayant accès à une
  source voit tous ses programmes, actuels et futurs.
- source_name "*" = toutes les sources. Scope "*" = toutes les actions.
- Comparaison des sources insensible à la casse et aux espaces.
- Le rôle admin donne accès à tout.

Aucune source n'est hardcodée : toute nouvelle source apparaissant dans
data/processed ou data/analytics fonctionne automatiquement.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.auth.models import SUBJECT_USER, Permission, User

logger = logging.getLogger(__name__)

WILDCARD = "*"

# Scopes de lecture des données
SCOPE_READ_COMPETENCE = "read:competence"
SCOPE_READ_CURRICULUM = "read:curriculum"
SCOPE_READ_ANALYTICS = "read:analytics"

# Réservé (non utilisé en v1 : pipeline = admin uniquement)
SCOPE_RUN_PIPELINE = "run:pipeline"

KNOWN_SCOPES = {
    SCOPE_READ_COMPETENCE,
    SCOPE_READ_CURRICULUM,
    SCOPE_READ_ANALYTICS,
    SCOPE_RUN_PIPELINE,
    WILDCARD,
}


def _norm(value: str) -> str:
    return value.strip().lower()


def get_subject_permissions(
    db: Session,
    subject_type: str,
    subject_id: int,
) -> List[Permission]:
    """Charge les permissions d'un sujet (une requête par appel)."""
    return (
        db.query(Permission)
        .filter(
            Permission.subject_type == subject_type,
            Permission.subject_id == subject_id,
        )
        .all()
    )


def get_user_permissions(db: Session, user: User) -> List[Permission]:
    return get_subject_permissions(db, SUBJECT_USER, user.id)


def can_access(
    permissions: List[Permission],
    source_name: str,
    scope: str,
    *,
    is_admin: bool = False,
) -> bool:
    """Décide si l'accès à (source, scope) est autorisé.

    Args:
        permissions : permissions déjà chargées du sujet
        source_name : source demandée (ex. "Polytech", "BUT")
        scope       : action demandée (ex. "read:competence")
        is_admin    : True si le sujet a le rôle admin (accès total)
    """
    if is_admin:
        return True

    requested_source = _norm(source_name)

    for permission in permissions:
        permission_source = _norm(permission.source_name)

        source_ok = (
            permission_source == WILDCARD
            or permission_source == requested_source
        )

        scopes = permission.scopes or []
        scope_ok = WILDCARD in scopes or scope in scopes

        if source_ok and scope_ok:
            return True

    return False


def filter_items_by_access(
    items: List[Dict[str, Any]],
    permissions: List[Permission],
    scope: str,
    *,
    is_admin: bool = False,
) -> List[Dict[str, Any]]:
    """Filtre une liste d'items {source, programme, file, data} selon les droits.

    Le filtrage se fait uniquement sur item["source"] :
    le champ "programme" est informatif et n'intervient pas
    dans la décision d'accès (décision métier v1).
    """
    if is_admin:
        return items

    return [
        item for item in items
        if can_access(permissions, item.get("source", ""), scope)
    ]