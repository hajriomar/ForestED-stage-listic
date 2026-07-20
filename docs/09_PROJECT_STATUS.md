# 09 — État du projet

*Dernière mise à jour : juillet 2026.*

## Résumé

ForestED est **fonctionnel en local** : trois sources chargées et visualisées,
administration complète, base PostgreSQL avec migrations, API versionnée,
**219/219 tests verts**. La configuration de déploiement serveur (Caddy HTTPS) est
**prête côté applicatif** mais dormante jusqu'à disposer d'un vrai serveur.
Rien de bloquant n'est en attente.

## Terminé et validé

- **Backend sécurisé** : JWT (login par nom OU email, Argon2id), clés API
  SHA-256 (secret montré une fois, expiration, désactivation définitive),
  permissions par source (wildcard `*`), garde-fous anti-lockout, anti-SSRF
  (import API), anti-path-traversal (upload), 401/403 distincts.
- **API versionnée `/api/v1`** ; `/health` non préfixé ; Swagger en dev,
  désactivé en production ; `TrustedHostMiddleware` configurable (hosts
  internes ajoutés automatiquement).
- **PostgreSQL 16 + Alembic** : baseline `0001_baseline` appliquée et
  tamponnée (`alembic current` = head) ; migrations exécutées à chaque
  démarrage ; données reprises depuis l'ancien SQLite (avec réparation d'une
  incohérence FK héritée — clés orphelines réaffectées).
- **ETL multi-sources** : registry déclarative, contrats R4 testés,
  quality_report sauvegardé, séparation stricte competence/curriculum.
- **Administration complète** : utilisateurs (actions par ligne
  activer/désactiver/supprimer + formulaire de modification), permissions
  (retrait par ligne), clés API (badges d'état, désactivation par ligne),
  confirmations sur toutes les actions destructives, upload de fichiers,
  import API JSON, bouton « Relancer le pipeline », dropdown de sources
  alimenté par la registry.
- **Frontend** : deux forêts cohérentes (couleurs unifiées, légende par mode,
  focus préservé), labels UE réels, dashboard partagé invité
  (`/access/<clé>`).
- **Ops** : `restart: unless-stopped` sur les 3 services ; Caddy/C1 livré
  (Caddyfile, compose prod avec `ports: !reset`, doc de déploiement).
- **Tests : 219/219 verts** (auth, permissions, clés, upload, import, registry,
  contrats, normalizers/transformers, pipeline). Un fichier de 8 tests de
  séparation stricte des domaines (`test_usmb_domain_separation.py`) a été
  livré mais n'est **pas encore ajouté** à `tests/` — une fois copié, la suite
  passe à 227.

## Sources en production (locale)

| Source | competence | curriculum | Notes |
|---|---|---|---|
| **BUT** | ✅ | ✅ | Excel « Annexe », parcours/UE optionnelles |
| **Polytech** | ✅ (2 formats) | ✅ | JSON phpMyAdmin + maquette |
| **usmb_licence** | ✅ (17 licences) | ✅ **lite** | croix + couleurs, parcours ; ECTS/heures à 0.0 signalés ; **MATH exclu** (hors gabarit, 422 clair) |

## Reste à faire (non bloquant)

| Item | Nature |
|---|---|
| Mail de demande de vraies maquettes USMB (Pégase / ROF CDM-fr / Excel scolarité) | démarche externe — remplacera le curriculum-lite |
| C2 — rate limiting (proxy) | préparation possible en avance |
| C3 — sauvegardes (dump postgres + data/) | préparation possible en avance |
| Fiche client courte / version commerciale de [05_API_CLIENT.md](05_API_CLIENT.md) | rédaction optionnelle |
| Ajouter `test_usmb_domain_separation.py` dans `tests/` (livré, +8 tests → 227) | copie du fichier livré |
| Déploiement serveur réel + validation des 10 critères C1 | attend VPS + domaine |
| Parseur MATH | optionnel |
| Refactors R2/R3 (audit transformers) | optionnels |
| Migration lifespan FastAPI (4 DeprecationWarning au démarrage) | optionnel |

## Pour un développeur qui reprend le projet

1. Lire [01_ARCHITECTURE.md](01_ARCHITECTURE.md) puis
   [06_ETL_DEVELOPER_GUIDE.md](06_ETL_DEVELOPER_GUIDE.md).
2. Démarrer en local ([02_INSTALLATION_LOCALE.md](02_INSTALLATION_LOCALE.md))
   et vérifier : `pytest` 219/219 verts, `alembic current` = head, login OK.
3. Points d'entrée du code : `backend_python/app/main.py` (routes),
   `app/etl/pipeline.py` (ETL), `app/etl/transform/flat_contract.py`
   (contrats), `front/app/main.py` (Dash) et `front/app/api_client.py`
   (unique point de contact frontend→API).
4. Toute nouvelle source suit le pas-à-pas du guide ETL — le couple
   normalizer/transformer USMB est l'implémentation de référence la plus
   récente et la plus complète.
5. Invariants à ne jamais casser : permissions par source côté serveur,
   secret des clés montré une fois, séparation competence/curriculum,
   contrats R4, aucune donnée inventée par l'ETL.
