"""
Création du premier compte admin ForestED.

Usage :
    python -m app.scripts.create_admin --username admin --email admin@example.com
    (le mot de passe est demandé de façon masquée si --password est absent)

Jamais de credentials par défaut : ce script est le seul moyen
de créer le premier admin.
"""

import argparse
import getpass
import sys

from app.auth.database import SessionLocal, init_db
from app.auth.models import ROLE_ADMIN, User
from app.auth.security import hash_password

MIN_PASSWORD_LENGTH = 10


def main() -> int:
    parser = argparse.ArgumentParser(description="Créer un compte admin ForestED")
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--password",
        help="Déconseillé (visible dans l'historique shell). "
             "Si absent : saisie masquée.",
    )
    args = parser.parse_args()

    password = args.password or getpass.getpass("Mot de passe admin : ")

    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Erreur : mot de passe trop court (minimum {MIN_PASSWORD_LENGTH} caractères).")
        return 1

    init_db()

    db = SessionLocal()
    try:
        existing = (
            db.query(User)
            .filter(
                (User.username == args.username) | (User.email == args.email)
            )
            .first()
        )
        if existing is not None:
            print(f"Erreur : un utilisateur existe déjà (username={existing.username}).")
            return 1

        user = User(
            username=args.username,
            email=args.email,
            hashed_password=hash_password(password),
            role=ROLE_ADMIN,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Admin créé : {args.username} <{args.email}>")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
