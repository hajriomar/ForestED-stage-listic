# 02 — Installation locale

## Prérequis

- **Docker Desktop** (avec Docker Compose ≥ 2.24 — vérifier : `docker compose version`)
- **Git**
- Aucun Python local nécessaire : tout s'exécute dans les conteneurs.

## Démarrage

Depuis la racine du projet :

```bash
docker compose up -d
```

Cela démarre trois services : `forested_postgres` (base d'auth, healthcheck),
`forested_backend` (exécute `alembic upgrade head` PUIS uvicorn) et
`forested_frontend` (Dash). Les trois portent `restart: unless-stopped` :
ils redémarrent seuls après un reboot de Docker ou du PC ; un
`docker compose stop` volontaire reste respecté.

> ⚠️ **`--build` uniquement quand `requirements.txt` ou un `Dockerfile`
> change** :
>
> ```bash
> docker compose up -d --build
> ```
>
> Au quotidien, `docker compose up -d` suffit et fonctionne même sans accès
> à Internet (images locales).

## Vérifications

```bash
docker ps                                    # 3 conteneurs Up (postgres healthy)
docker logs forested_backend --tail 20       # attendu : "Context impl PostgresqlImpl"
                                             # puis "Uvicorn running on ...:8000"
```

Navigateur :

- <http://127.0.0.1:8050> — page de login du dashboard
- <http://127.0.0.1:8000/docs> — Swagger (dev)
- <http://127.0.0.1:8000/health> — `{"status":"ok",...}`

## PostgreSQL local

La base vit dans le **volume Docker `pgdata`** (persistant entre les
redémarrages). Aucun port n'est publié : seuls les conteneurs y accèdent.

> ⚠️ **Ne jamais lancer `docker compose down -v`** : le `-v` supprime le
> volume `pgdata`, donc TOUTE la base d'authentification (utilisateurs,
> permissions, clés API). `docker compose down` sans `-v` est sans danger.

## Alembic (migrations de la base)

Les migrations s'appliquent automatiquement au démarrage du backend. Pour
vérifier l'état :

```bash
docker exec -it forested_backend alembic current
```

Attendu : `0001_baseline (head)`. Le dossier `backend_python/alembic/` et le
fichier `alembic.ini` sont **permanents** (ne pas les supprimer) : la
structure de la base y est versionnée, et le backend les utilise à chaque
démarrage.

## Fichier `.env` local

Copier `.env.example` en `.env` si nécessaire. Règles pour le `.env` LOCAL :

```env
# Ce qui peut y figurer en local :
AUTH_SECRET_KEY=...            # optionnel en dev
FLASK_SECRET_KEY=...           # optionnel en dev
# + éventuellement les variables domaines fictives pour tester
#   `docker compose ... config` (voir 07_DEPLOIEMENT_PRODUCTION.md)

# À NE JAMAIS mettre dans le .env local :
# APP_ENV=production        -> casserait le dev (docs off, cookies Secure)
# DATABASE_URL=sqlite:...   -> détournerait Alembic vers l'ancien SQLite
# POSTGRES_PASSWORD modifié -> mismatch avec le volume pgdata existant
```

## Tests

```bash
docker exec -it forested_backend python -m pytest tests/ -q
```

Attendu : **219 tests verts**. Les tests utilisent une base SQLite dédiée
(isolée par `tests/conftest.py`) — ils ne touchent jamais à PostgreSQL ni aux
données réelles.
