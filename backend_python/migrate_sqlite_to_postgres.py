# -*- coding: utf-8 -*-
"""
Reprise des données auth : SQLite (forested.db) -> PostgreSQL (Patch B, v2).

v2 :
- insertion LIGNE PAR LIGNE (21 lignes au total : instantané) avec, après
  chaque table, un COUNT(*) de contrôle DANS la transaction — toute
  anomalie devient visible immédiatement ;
- scopes (permissions) : SQLite stocke le JSON en texte -> décodé en vraie
  liste avant insertion dans la colonne JSON PostgreSQL ;
- en cas d'erreur sur une ligne, la ligne fautive est affichée puis
  l'erreur relancée (transaction annulée : la cible reste propre).

Toujours : DRY-RUN par défaut (--apply pour écrire), idempotent (ids déjà
présents ignorés), séquences PostgreSQL recalées après insertion,
forested.db jamais modifié.

Usage (depuis backend_python, la cible vient de DATABASE_URL) :
    python migrate_sqlite_to_postgres.py                # dry-run
    python migrate_sqlite_to_postgres.py --apply        # écrit
"""

import argparse
import json

from sqlalchemy import MetaData, create_engine, func, select, text

from app.config import DATABASE_URL

TABLES = ("users", "api_keys", "permissions")   # ordre FK
JSON_COLUMNS = {"permissions": {"scopes"}}      # colonnes JSON à décoder

# SQLite n'applique PAS les clés étrangères par défaut : forested.db peut
# contenir des api_keys dont le créateur (created_by_user_id) a été
# supprimé depuis. PostgreSQL refuse à juste titre ces orphelines : on les
# réaffecte au premier admin actif (champ purement informatif), avec un
# message explicite par clé réaffectée.


def _decode_json_cols(table_name: str, row: dict) -> dict:
    for col in JSON_COLUMNS.get(table_name, ()):
        value = row.get(col)
        if isinstance(value, str):
            row[col] = json.loads(value)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="./forested.db")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    src_engine = create_engine(
        f"sqlite:///{args.source}",
        connect_args={"check_same_thread": False},
    )
    dst_engine = create_engine(DATABASE_URL)

    if DATABASE_URL.startswith("sqlite") and args.apply:
        raise SystemExit("DATABASE_URL pointe encore vers SQLite — cible "
                         "PostgreSQL attendue (docker-compose/.env).")

    src_meta, dst_meta = MetaData(), MetaData()
    src_meta.reflect(bind=src_engine, only=list(TABLES))
    dst_meta.reflect(bind=dst_engine, only=list(TABLES))

    mode = "APPLY" if args.apply else "DRY-RUN (rien n'est écrit)"
    print(f"Source : {args.source}\nCible  : {DATABASE_URL}\nMode   : {mode}\n")

    with src_engine.connect() as src, dst_engine.begin() as dst:
        for table_name in TABLES:
            src_table = src_meta.tables[table_name]
            dst_table = dst_meta.tables[table_name]

            rows = [dict(r._mapping) for r in src.execute(select(src_table))]
            existing = {r[0] for r in dst.execute(select(dst_table.c.id))}
            to_copy = [r for r in rows if r["id"] not in existing]
            print(f"{table_name:12} {len(rows):>3} source · "
                  f"{len(to_copy):>3} à copier · "
                  f"{len(rows) - len(to_copy)} déjà présente(s)")

            if not (args.apply and to_copy):
                continue

            common = [c.name for c in src_table.columns
                      if c.name in dst_table.columns]

            # ids utilisateurs valides + admin de secours (orphelines)
            if table_name == "users":
                valid_user_ids = {r["id"] for r in rows}
                admins = [r for r in rows if r.get("role") == "admin"
                          and r.get("is_active", True)]
                fallback_admin_id = admins[0]["id"] if admins else None

            for row in to_copy:
                payload = _decode_json_cols(
                    table_name, {k: row[k] for k in common})

                if table_name == "api_keys" and \
                        payload.get("created_by_user_id") not in valid_user_ids:
                    print(f"{'':12} clé id={payload['id']} "
                          f"({payload.get('name')!r}) : créateur "
                          f"id={payload['created_by_user_id']} supprimé "
                          f"-> réaffectée à l'admin id={fallback_admin_id}")
                    payload["created_by_user_id"] = fallback_admin_id
                try:
                    dst.execute(dst_table.insert().values(**payload))
                except Exception:
                    print(f"\nÉCHEC sur {table_name} id={row.get('id')} : "
                          f"{payload}")
                    raise

            count = dst.execute(
                select(func.count()).select_from(dst_table)).scalar()
            print(f"{'':12} -> contrôle : {count} ligne(s) dans la cible "
                  f"(transaction en cours)")

        if args.apply and dst_engine.dialect.name == "postgresql":
            for table_name in TABLES:
                dst.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table_name}), 1))"
                ))
            print("\nSéquences PostgreSQL recalées sur max(id).")

    if not args.apply:
        print("\nDry-run terminé. Relancer avec --apply pour écrire.")
    else:
        print("Reprise terminée. Vérifier : login admin + page admin.")


if __name__ == "__main__":
    main()