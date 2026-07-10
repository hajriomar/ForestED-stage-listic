"""
Gestion CLI des permissions par source (en attendant l'API admin, Phase 4).

Usage :
    # Donner accès à une source
    python -m app.scripts.grant_permission grant --username userA \
        --source Polytech --scopes read:competence,read:curriculum,read:analytics

    # Accès total (toutes sources, toutes actions)
    python -m app.scripts.grant_permission grant --username userD --source "*" --scopes "*"

    # Lister les permissions
    python -m app.scripts.grant_permission list
    python -m app.scripts.grant_permission list --username userA

    # Révoquer une permission par id
    python -m app.scripts.grant_permission revoke --id 3
"""

import argparse
import sys

from app.auth.database import SessionLocal, init_db
from app.auth.models import SUBJECT_USER, Permission, User
from app.auth.permissions import KNOWN_SCOPES


def _get_user(db, username: str) -> User:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        print(f"Erreur : utilisateur introuvable : {username}")
        sys.exit(1)
    return user


def cmd_grant(db, args) -> int:
    user = _get_user(db, args.username)
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]

    if not scopes:
        print("Erreur : aucun scope fourni.")
        return 1

    unknown = [s for s in scopes if s not in KNOWN_SCOPES]
    if unknown:
        print(f"Attention : scopes inconnus {unknown} "
              f"(scopes connus : {sorted(KNOWN_SCOPES)})")

    existing = (
        db.query(Permission)
        .filter(
            Permission.subject_type == SUBJECT_USER,
            Permission.subject_id == user.id,
            Permission.source_name == args.source,
        )
        .first()
    )

    if existing is not None:
        existing.scopes = scopes
        action = "mise à jour"
    else:
        db.add(Permission(
            subject_type=SUBJECT_USER,
            subject_id=user.id,
            source_name=args.source,
            scopes=scopes,
        ))
        action = "créée"

    db.commit()
    print(f"Permission {action} : {user.username} → source={args.source!r} scopes={scopes}")
    return 0


def cmd_list(db, args) -> int:
    query = db.query(Permission)

    if args.username:
        user = _get_user(db, args.username)
        query = query.filter(
            Permission.subject_type == SUBJECT_USER,
            Permission.subject_id == user.id,
        )

    permissions = query.order_by(Permission.subject_id, Permission.id).all()

    if not permissions:
        print("Aucune permission.")
        return 0

    users = {u.id: u.username for u in db.query(User).all()}
    for p in permissions:
        subject = (
            users.get(p.subject_id, f"user#{p.subject_id}")
            if p.subject_type == SUBJECT_USER
            else f"{p.subject_type}#{p.subject_id}"
        )
        print(f"[{p.id}] {subject:20s} source={p.source_name!r:15s} scopes={p.scopes}")
    return 0


def cmd_revoke(db, args) -> int:
    permission = db.get(Permission, args.id)
    if permission is None:
        print(f"Erreur : permission id={args.id} introuvable.")
        return 1

    db.delete(permission)
    db.commit()
    print(f"Permission id={args.id} révoquée.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gestion des permissions par source ForestED"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_grant = sub.add_parser("grant", help="Donner accès à une source")
    p_grant.add_argument("--username", required=True)
    p_grant.add_argument("--source", required=True,
                         help='Nom de source (ex. Polytech, BUT) ou "*"')
    p_grant.add_argument("--scopes", required=True,
                         help='Scopes séparés par des virgules, ou "*"')

    p_list = sub.add_parser("list", help="Lister les permissions")
    p_list.add_argument("--username")

    p_revoke = sub.add_parser("revoke", help="Révoquer une permission")
    p_revoke.add_argument("--id", type=int, required=True)

    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.command == "grant":
            return cmd_grant(db, args)
        if args.command == "list":
            return cmd_list(db, args)
        if args.command == "revoke":
            return cmd_revoke(db, args)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())