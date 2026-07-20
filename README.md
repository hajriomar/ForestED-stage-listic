# ForestED

**Plateforme de visualisation de curricula orientés compétences (APC).**

ForestED ingère des référentiels de compétences et des maquettes pédagogiques
(exports Excel, JSON, CSV, API), les normalise vers un méta-modèle commun,
et les restitue sous forme de visualisations interactives : forêt pédagogique
(Compétence → Niveaux → Apprentissages Critiques), forêt curriculaire
(Semestre → UE → Modules → AC), cartographie APC, exploration circulaire.
L'accès aux données est contrôlé **par source**, pour des utilisateurs
authentifiés comme pour des clients techniques (clés API) et des dashboards
partagés en lecture seule.

## Stack technique

| Couche | Technologie |
|---|---|
| Backend / API | FastAPI — API versionnée `/api/v1` |
| Frontend | Dash (Flask) — session par cookie signé |
| Authentification | JWT (utilisateurs) · `X-API-Key` (clients techniques) |
| Base d'authentification | PostgreSQL 16 · migrations Alembic |
| Données pédagogiques | Fichiers `processed/` + `analytics/` (jamais en base SQL) |
| ETL | Extract → Normalize → Transform → Load, registry déclarative |
| Exécution locale | Docker Compose |
| Déploiement serveur (préparé) | Caddy HTTPS via `docker-compose.prod.yml` |

## Architecture en une phrase

```
Navigateur ──► Dash :8050 ──► FastAPI /api/v1 ──► PostgreSQL (auth)
                                        └───────► fichiers processed/analytics (ETL)
```

Deux domaines de données strictement séparés : **competence** (référentiels)
et **curriculum** (maquettes) — voir [docs/01_ARCHITECTURE.md](docs/01_ARCHITECTURE.md).

## Démarrage rapide

```bash
docker compose up -d                                             # tout démarrer
docker exec -it forested_backend python -m pytest tests/ -q     # suite de tests
docker exec -it forested_backend alembic current                # 0001_baseline (head)
```

URLs locales :

- Dashboard : <http://127.0.0.1:8050>
- Swagger (dev uniquement) : <http://127.0.0.1:8000/docs>
- Healthcheck : <http://127.0.0.1:8000/health>

> ⚠️ `docker compose up -d --build` uniquement si `requirements.txt` ou un
> `Dockerfile` a changé. Le fichier `docker-compose.prod.yml` est réservé au
> serveur — ne jamais le lancer en local (voir
> [docs/07_DEPLOIEMENT_PRODUCTION.md](docs/07_DEPLOIEMENT_PRODUCTION.md)).

## Documentation

| Fichier | Contenu |
|---|---|
| [docs/01_ARCHITECTURE.md](docs/01_ARCHITECTURE.md) | Composants, domaines competence/curriculum, permissions, registry ETL |
| [docs/02_INSTALLATION_LOCALE.md](docs/02_INSTALLATION_LOCALE.md) | Prérequis, démarrage, vérifications, PostgreSQL/Alembic |
| [docs/03_UTILISATION.md](docs/03_UTILISATION.md) | Pages du dashboard, filtres, les deux forêts, limites du curriculum-lite |
| [docs/04_ADMINISTRATION.md](docs/04_ADMINISTRATION.md) | Utilisateurs, permissions, clés API, upload, import API, pipeline |
| [docs/05_API_CLIENT.md](docs/05_API_CLIENT.md) | Utiliser l'API avec une clé — endpoints, exemples curl/Python |
| [docs/06_ETL_DEVELOPER_GUIDE.md](docs/06_ETL_DEVELOPER_GUIDE.md) | Ajouter une source : extractor/normalizer/transformer, contrats R4 |
| [docs/07_DEPLOIEMENT_PRODUCTION.md](docs/07_DEPLOIEMENT_PRODUCTION.md) | Déploiement serveur avec Caddy (préparé, dormant) |
| [docs/08_TROUBLESHOOTING.md](docs/08_TROUBLESHOOTING.md) | Problèmes rencontrés et solutions |
| [docs/09_PROJECT_STATUS.md](docs/09_PROJECT_STATUS.md) | État du projet, sources en production, reste à faire |

## Statut actuel

**Plateforme fonctionnelle en local** : 3 sources chargées (BUT, Polytech,
usmb_licence) sur les deux domaines, administration complète, 219 tests verts.
Le déploiement serveur (Caddy HTTPS) est **prêt côté applicatif mais dormant**
jusqu'à disposer d'un vrai serveur et d'un nom de domaine.
