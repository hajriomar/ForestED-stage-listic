# 08 — Troubleshooting

Problèmes réellement rencontrés sur ce projet, avec leur solution. Premier
réflexe dans tous les cas :

```bash
docker compose ps -a                          # qui tourne, qui a quitté ?
docker logs forested_backend --tail 50        # la vraie cause est ici
```

## 1. Build impossible : `TLS handshake timeout` / `no such host` (Docker Hub)

Problème réseau entre ta machine et Docker Hub (Internet coupé, VPN, proxy
Docker Desktop). Solutions :

```bash
docker compose up -d          # SANS --build : les images locales suffisent
docker pull python:3.11-slim  # test de connectivité quand le réseau revient
```

Rappel : `--build` n'est nécessaire que si `requirements.txt` ou un
`Dockerfile` a changé. Vérifier aussi Docker Desktop → Settings → Resources →
Proxies.

## 2. `alembic heads` ne retourne rien

Alembic ne voit aucune migration. Causes constatées : la baseline n'est pas
dans `alembic/versions/` (elle doit y être, pas à la racine d'`alembic/`),
et/ou le gabarit s'appelle `script.py` au lieu de **`script.py.mako`**
(extension perdue à la copie). Corriger l'arborescence puis :

```bash
docker exec -it forested_backend alembic heads      # 0001_baseline (head)
docker exec -it forested_backend alembic current    # 0001_baseline (head)
```

Si les tables existent déjà mais que la base n'est pas tamponnée :
`alembic stamp head` (n'exécute rien, enregistre juste la version).

## 3. Backend attaque SQLite au lieu de PostgreSQL

Symptôme dans les logs : `sqlite3.OperationalError: table users already
exists` pendant la migration. Cause : une ligne `DATABASE_URL=sqlite:///...`
active dans `.env` (elle écrase le défaut PostgreSQL du compose). Solution :
supprimer ou recommenter cette ligne, puis `docker compose up -d backend`.
Attendu ensuite dans les logs : `Context impl PostgresqlImpl`.

## 4. `forested_backend Exited (1)`

Le backend a planté au démarrage (souvent pendant `alembic upgrade`).

```bash
docker compose logs --no-color --tail=100 backend
```

Lire la PREMIÈRE erreur : `No module named 'app'` → `prepend_sys_path = .`
manquant dans `alembic.ini` ; `password authentication failed` →
`POSTGRES_PASSWORD` modifié dans `.env` alors que le volume `pgdata` a été
créé avec l'ancien ; erreurs sqlite → voir n°3 ; `RuntimeError AUTH_SECRET_KEY`
→ `APP_ENV=production` traîne dans le `.env` local (à retirer).

## 5. `required variable APP_DOMAIN is missing a value`

**Normal en local** : c'est le garde-fou du compose de production. Ce fichier
est réservé au serveur. En local : `docker compose up -d` tout court. Pour
seulement vérifier la fusion : `docker compose -f docker-compose.yml -f
docker-compose.prod.yml config` (avec des variables fictives dans `.env`).

## 6. Un service `Exited (255)` après un redémarrage de Docker/PC

Historique : il manquait la politique de redémarrage. Résolu — les trois
services portent `restart: unless-stopped`. Si cela se reproduit :
`docker compose up -d` relance tout ; vérifier la politique avec
`docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' forested_backend`.

## 7. Tests en échec avec des chemins `/api/v1/api/v1/...`

Erreur historique : le script de migration des tests vers `/api/v1` avait
doublé les préfixes (il s'était auto-modifié en vivant dans `tests/`).
Résolu — si un double préfixe réapparaît quelque part, chercher la chaîne
`/api/v1/api/v1` et la réduire à `/api/v1`. Côté frontend, vérifier que
`API_BASE_URL` contient UNE fois `/api/v1`
(`http://backend:8000/api/v1`) et que les chemins d'appel n'en rajoutent pas.

## 8. Upload USMB « MATH » → 422

**Comportement voulu.** Le fichier MATH est hors gabarit (3 compétences côte
à côte, sans matrice AC×EC) : il est refusé avec un message explicite et le
fichier raw est nettoyé. Exclu en v1/v2 — ne pas chercher à le forcer.

## 9. `/docs` renvoie 404

En **production** (`APP_ENV=production`), c'est **normal** : Swagger, ReDoc
et openapi.json sont désactivés volontairement. En dev, `/docs` doit
répondre — sinon vérifier qu'`APP_ENV=production` ne traîne pas dans `.env`.

## 10. Rappels de prudence

- `docker compose down` : OK. **`docker compose down -v` : JAMAIS** sans
  vouloir effacer la base (volume `pgdata`).
- `forested.db` (racine backend) : ancien SQLite conservé comme secours de
  rollback — ne pas le confondre avec la base active (PostgreSQL).
