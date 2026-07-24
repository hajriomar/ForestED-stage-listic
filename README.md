# ForestED

**Plateforme de visualisation de curricula orientés compétences (APC).**

ForestED permet d’ingérer des référentiels de compétences et des maquettes pédagogiques issus de plusieurs sources, de les transformer vers des modèles canoniques communs, puis de les explorer avec des visualisations interactives.

L’objectif du projet est de rendre lisibles les relations entre :

```text
formations → semestres → UE/groupes → modules
et
compétences → niveaux → apprentissages critiques / acquis
```

ForestED est conçu pour supporter plusieurs établissements, plusieurs formats de fichiers et plusieurs niveaux de maturité des données pédagogiques.

---

## Fonctionnalités principales

- Pipeline ETL multi-sources : `Extract → Normalize → Transform → Load`.
- Deux domaines strictement séparés :
  - `competence` : référentiels de compétences, PLO, AC, MLO ;
  - `curriculum` : programmes, semestres, UE/groupes, modules, ECTS, heures.
- Visualisations interactives :
  - cartographie APC ;
  - forêt pédagogique : `Compétence → Niveaux → AC` ;
  - forêt curriculaire : `Semestre → UE → Modules → AC` ;
  - exploration circulaire / sunburst ;
  - visualisations par parcours.
- Administration complète :
  - utilisateurs ;
  - permissions par source ;
  - clés API ;
  - upload/import de fichiers ;
  - relance du pipeline.
- Accès sécurisé :
  - authentification utilisateur ;
  - clés API pour clients techniques ;
  - liens invités pour dashboard partagé en lecture seule.
- Support de sources hétérogènes :
  - fichiers JSON ;
  - fichiers Excel ;
  - fichiers CSV ;
  - import API JSON.

---

## Stack technique

| Couche | Technologie |
|---|---|
| Backend / API | FastAPI, API versionnée `/api/v1` |
| Frontend | Dash / Flask |
| Authentification | JWT pour utilisateurs, `X-API-Key` pour clients techniques |
| Base d’authentification | PostgreSQL 16 |
| Migrations | Alembic |
| Données pédagogiques | Fichiers JSON dans `processed/` et `analytics/` |
| ETL | Python, factories déclaratives, normalizers et transformers par source |
| Visualisations | Plotly / Dash |
| Exécution locale | Docker Compose |
| Production préparée | Caddy HTTPS avec `docker-compose.prod.yml` |

---

## Architecture générale

```text
Navigateur
   │
   ▼
Dash / Flask :8050
   │
   ▼
FastAPI /api/v1 :8000
   ├── PostgreSQL 16
   │      └── utilisateurs, permissions, clés API
   │
   └── fichiers pédagogiques
          ├── raw/
          ├── processed/
          └── analytics/
```

Principe important :

```text
PostgreSQL = authentification et autorisations
Fichiers JSON = données pédagogiques
```

Les données pédagogiques ne sont pas stockées dans PostgreSQL. Elles restent sous forme de fichiers générés par l’ETL.

---

## Sources actuellement supportées

| Source | Domaine competence | Domaine curriculum | Particularités |
|---|---:|---:|---|
| `BUT` | ✅ | ✅ | Référentiels et maquettes BUT, parcours, UE, ressources/SAÉ selon la source. |
| `Polytech` | ✅ | ✅ | Référentiel compétences IDU + catalogue/maquette IDU. |
| `usmb_licence` | ✅ | ✅ | Référentiels APC reconstruits en curriculum; ECTS/heures parfois absents. |
| `unita` | ✅ | ✅ | Joint Degree SCRL : PLO/MLO génériques + maquette institutionnelle USMB. |

---

## Cas particulier : UNITA / Joint Degree SCRL

UNITA est le cas le plus avancé du projet, car il combine deux couches :

| Couche | Rôle |
|---|---|
| Générique UNITA | PLO, MLO et modules génériques du diplôme commun. |
| Institutionnelle USMB | Semestres, UE/groupes et modules réels de la maquette USMB. |

La liaison métier validée est :

```text
PLO / compétence
→ AC canonique construit depuis le PLO et le MLO
→ MLO
→ module spécifique USMB
```

Il ne faut pas interpréter la relation comme un lien direct final :

```text
module USMB → module générique UNITA
```

La colonne Excel `Correspondance générique` sert seulement à indiquer au pipeline quel catalogue générique utiliser pour hériter les MLO dans le module spécifique.

Exemple :

```text
Economie générale 1 → Economics
```

devient :

```text
UNITA_ECONOMICS → MLO
USMB_S1_E02 reçoit ces MLO dans acquis_apprentissage
```

La visualisation exploite ensuite les MLO pour afficher les modules USMB reliés aux PLO.

Documentation dédiée : [`docs/10_JOINT_DEGREE.md`](docs/10_JOINT_DEGREE.md).

---

## Démarrage rapide

Depuis la racine du projet :

```bash
docker compose up -d
```

Vérifier les conteneurs :

```bash
docker compose ps
```

URLs locales :

| Service | URL |
|---|---|
| Dashboard | <http://127.0.0.1:8050> |
| Swagger API dev | <http://127.0.0.1:8000/docs> |
| Healthcheck | <http://127.0.0.1:8000/health> |

Vérifications utiles :

```bash
docker exec -it forested_backend alembic current
docker exec -it forested_backend python -m pytest tests/ -q
docker compose exec frontend python -m py_compile /app/forested_visualisations.py
```

Attendu pour Alembic :

```text
0001_baseline (head)
```

La base documentaire précédente indiquait `240/240` tests sur la suite existante. Après ajout de nouveaux tests, le nombre peut évoluer ; l’important est que la suite soit verte.

---

## Commandes courantes

Démarrer :

```bash
docker compose up -d
```

Arrêter sans supprimer les volumes :

```bash
docker compose down
```

Reconstruire seulement si un Dockerfile ou `requirements.txt` change :

```bash
docker compose up -d --build
```

Afficher les logs backend :

```bash
docker logs forested_backend --tail 100
```

Afficher les logs frontend :

```bash
docker logs forested_frontend --tail 100
```

Relancer un service :

```bash
docker compose restart frontend
docker compose restart backend
```

---

## Attention Docker

Ne jamais lancer cette commande sans décision explicite :

```bash
docker compose down -v
```

Le `-v` supprime les volumes Docker, donc la base PostgreSQL locale avec les utilisateurs, permissions et clés API.

En local, ne pas lancer le compose de production :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Le compose de production est réservé au serveur avec domaine, DNS et variables `.env` de production.

---

## Structure du projet

La structure exacte peut varier selon l’organisation du dépôt, mais les points d’entrée principaux sont :

```text
backend_python/
├── app/
│   ├── main.py
│   ├── models/
│   ├── etl/
│   │   ├── extract/
│   │   ├── normalize/
│   │   ├── transform/
│   │   └── load/
│   └── data/
│       ├── raw/
│       ├── processed/
│       └── analytics/
├── alembic/
└── tests/

front/
└── app/
    ├── main.py
    ├── api_client.py
    └── visualisations/

docs/
├── 01_ARCHITECTURE.md
├── 02_INSTALLATION_LOCALE.md
├── 03_UTILISATION.md
├── 04_ADMINISTRATION.md
├── 05_API_CLIENT.md
├── 06_ETL_DEVELOPER_GUIDE.md
├── 07_DEPLOIEMENT_PRODUCTION.md
├── 08_TROUBLESHOOTING.md
├── 09_PROJECT_STATUS.md
└── 10_JOINT_DEGREE.md
```

---

## Documentation

| Document | Rôle |
|---|---|
| [`docs/01_ARCHITECTURE.md`](docs/01_ARCHITECTURE.md) | Architecture globale, domaines, permissions, registry ETL, invariants. |
| [`docs/02_INSTALLATION_LOCALE.md`](docs/02_INSTALLATION_LOCALE.md) | Installation locale, Docker, PostgreSQL, Alembic, tests. |
| [`docs/03_UTILISATION.md`](docs/03_UTILISATION.md) | Utilisation du dashboard, filtres, forêts, sunburst, lecture UNITA. |
| [`docs/04_ADMINISTRATION.md`](docs/04_ADMINISTRATION.md) | Gestion admin, utilisateurs, permissions, clés, upload/import. |
| [`docs/05_API_CLIENT.md`](docs/05_API_CLIENT.md) | Utilisation de l’API avec clé `X-API-Key`. |
| [`docs/06_ETL_DEVELOPER_GUIDE.md`](docs/06_ETL_DEVELOPER_GUIDE.md) | Ajouter ou maintenir une source ETL. |
| [`docs/07_DEPLOIEMENT_PRODUCTION.md`](docs/07_DEPLOIEMENT_PRODUCTION.md) | Déploiement serveur avec Caddy HTTPS. |
| [`docs/08_TROUBLESHOOTING.md`](docs/08_TROUBLESHOOTING.md) | Problèmes rencontrés et solutions. |
| [`docs/09_PROJECT_STATUS.md`](docs/09_PROJECT_STATUS.md) | État du projet, sources intégrées, reste à faire. |
| [`docs/10_JOINT_DEGREE.md`](docs/10_JOINT_DEGREE.md) | Source UNITA / Joint Degree SCRL. |

---

## Ajouter une nouvelle source

Le principe est de ne pas modifier le pipeline principal. Une nouvelle source doit être ajoutée par configuration et par composants spécialisés.

Étapes générales :

1. Analyser les fichiers réels.
2. Choisir le ou les domaines concernés : `competence`, `curriculum`, ou les deux.
3. Réutiliser un extractor existant si le format est déjà supporté.
4. Créer un normalizer dédié à la source.
5. Créer un transformer dédié au domaine.
6. Ajouter l’entrée dans les registries/factories.
7. Produire :
   - un canonique `processed/` ;
   - un flat `analytics/` ;
   - un `quality_report` quand la source le justifie.
8. Ajouter les tests.
9. Vérifier les visualisations.

Règles à respecter :

```text
ne pas inventer de données absentes ;
ne pas mélanger competence et curriculum ;
ne pas ajouter des champs hors modèle sans décision explicite ;
signaler les manques dans le quality_report ;
tester sur les vrais fichiers, pas seulement sur une fixture.
```

Voir [`docs/06_ETL_DEVELOPER_GUIDE.md`](docs/06_ETL_DEVELOPER_GUIDE.md).

---

## Sécurité et permissions

Les autorisations sont gérées par source.

Exemples de sources :

```text
Polytech
BUT
usmb_licence
unita
```

Un utilisateur ou une clé API peut avoir accès à une source sans avoir accès aux autres. Le filtrage est effectué côté serveur.

Types d’accès :

| Type | Usage |
|---|---|
| Utilisateur admin | Administration complète et accès aux sources. |
| Utilisateur viewer | Lecture des sources autorisées. |
| Clé API `data` | Intégration technique via `X-API-Key`. |
| Clé API `dashboard` | Lien invité `/access/<clé>` en lecture seule. |

---

## État actuel

ForestED est fonctionnel en local avec :

- authentification ;
- permissions par source ;
- API versionnée ;
- administration ;
- upload/import ;
- pipeline ETL multi-sources ;
- visualisations interactives ;
- source UNITA / Joint Degree SCRL intégrée fonctionnellement.

Le déploiement production avec Caddy HTTPS est préparé côté applicatif, mais doit encore être validé sur un vrai serveur public avec domaine et DNS.

---

## Reste à faire

Éléments non bloquants identifiés :

- consolider des tests automatisés dédiés UNITA ;
- améliorer encore l’ergonomie des vues globales très denses ;
- ajouter de vraies maquettes USMB licence pour remplacer le curriculum-lite ;
- préparer le rate limiting côté proxy ;
- préparer les sauvegardes PostgreSQL + `data/`;
- valider le déploiement serveur réel ;
- traiter éventuellement le fichier USMB MATH hors gabarit ;
- poursuivre les refactors techniques non bloquants.

---

## Reprendre le projet

Pour un nouveau développeur ou stagiaire :

1. Lire [`docs/01_ARCHITECTURE.md`](docs/01_ARCHITECTURE.md).
2. Démarrer le projet avec [`docs/02_INSTALLATION_LOCALE.md`](docs/02_INSTALLATION_LOCALE.md).
3. Lire [`docs/06_ETL_DEVELOPER_GUIDE.md`](docs/06_ETL_DEVELOPER_GUIDE.md) avant de modifier l’ETL.
4. Lire [`docs/10_JOINT_DEGREE.md`](docs/10_JOINT_DEGREE.md) avant de modifier UNITA.
5. Lancer les tests backend.
6. Vérifier la compilation frontend.
7. Ne jamais casser les invariants :
   - permissions par source ;
   - séparation `competence` / `curriculum` ;
   - modèles Pydantic stricts ;
   - non-invention des données ;
   - contrats R4.
