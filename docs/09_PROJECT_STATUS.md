# 09 — État du projet

*Dernière mise à jour : juillet 2026.*

## Résumé

ForestED est fonctionnel en local avec authentification, permissions par source, API versionnée, administration, upload/import, pipeline ETL multi-sources et visualisations interactives.

Le projet supporte maintenant quatre familles de sources en local :

```text
BUT
Polytech
usmb_licence
unita
```

La configuration de déploiement serveur avec Caddy HTTPS est prête côté applicatif, mais reste à valider sur un vrai serveur public.

## Terminé et validé fonctionnellement

- **Backend sécurisé** : login par nom ou email, JWT, clés API hashées, permissions par source, garde-fous anti-lockout, 401/403 séparés.
- **API `/api/v1`** : endpoints de données filtrés par source, `/health` hors préfixe, Swagger seulement en dev.
- **PostgreSQL + Alembic** : base d'authentification séparée des données pédagogiques.
- **ETL multi-sources** : extractor, normalizer, transformer, loader, registry déclarative, contrats R4, quality reports.
- **Séparation competence/curriculum** : les référentiels et les curricula restent dans leurs modèles respectifs.
- **Administration** : utilisateurs, permissions, clés API, upload/import, relance pipeline.
- **Frontend** : cartographie, forêts, sunburst, parcours, dashboard invité.
- **UNITA / SCRL** : intégration Joint Degree avec PLO/MLO génériques + maquette institutionnelle USMB, liaison via MLO hérités dans les modules spécifiques.
- **Ops local** : Docker Compose avec `restart: unless-stopped`, Caddy préparé pour production.

## Sources en production locale

| Source | competence | curriculum | Notes |
|---|---|---|---|
| **BUT** | ✅ | ✅ | Excel Annexe, parcours, UE, ressources/SAÉ selon source. |
| **Polytech** | ✅ | ✅ | Référentiel compétences + catalogue/maquette IDU. |
| **usmb_licence** | ✅ | ✅ lite | Référentiels APC reconstruits en curriculum-lite ; ECTS/heures absents signalés. |
| **unita** | ✅ | ✅ | Joint Degree SCRL : PLO/MLO génériques + maquette USMB ; modules spécifiques reliés via MLO hérités. |

## État de la source UNITA

Fait :

- lecture du référentiel générique PLO/MLO ;
- lecture du curriculum générique UNITA ;
- lecture de l'Excel USMB avec colonne `Correspondance générique` ;
- héritage des MLO dans `acquis_apprentissage` des modules USMB ;
- visualisation des modules spécifiques USMB via jointure MLO ;
- masquage/neutralisation du catalogue générique quand il ne doit pas être présenté comme une vraie maquette.

À surveiller :

- les vues globales restent denses ;
- S6 peut rester incomplet si les modules ne sont pas stabilisés ;
- `Finance` reste générique tant qu'aucune ligne Excel n'est mappée vers `Finance` ;
- les tests dédiés UNITA doivent être consolidés si la source devient critique.

## Tests et vérifications

Base documentaire précédente : `240/240` tests attendus sur la suite existante.

Commandes de vérification :

```bash
docker exec -it forested_backend python -m pytest tests/ -q
docker compose exec frontend python -m py_compile /app/forested_visualisations.py
```

Vérification UNITA recommandée : compter les modules `USMB_*` avec `acquis_apprentissage` non vide dans `SCRL_processed.json`.

## Reste à faire non bloquant

| Item | Nature |
|---|---|
| Ajouter des tests automatisés dédiés UNITA | sécuriser normalizer, upsert MLO, visualisation MLO-based. |
| Améliorer l'ergonomie des vues globales UNITA | graphe dense, labels, regroupement par UE/semestre. |
| Demander de vraies maquettes USMB licence | remplacer le curriculum-lite par des maquettes complètes. |
| C2 rate limiting | sécurité proxy. |
| C3 sauvegardes | dump PostgreSQL + sauvegarde `data/`. |
| Déploiement serveur réel | valider Caddy HTTPS avec domaine. |
| Parser MATH USMB | optionnel, fichier hors gabarit. |
| Refactors R2/R3 | optionnels. |
| Migration lifespan FastAPI | optionnel. |

## Pour un développeur qui reprend le projet

1. Lire [01_ARCHITECTURE.md](01_ARCHITECTURE.md) pour comprendre les invariants.
2. Lire [06_ETL_DEVELOPER_GUIDE.md](06_ETL_DEVELOPER_GUIDE.md) avant de modifier une source.
3. Lire [10_JOINT_DEGREE.md](10_JOINT_DEGREE.md) avant de toucher à UNITA.
4. Démarrer en local avec [02_INSTALLATION_LOCALE.md](02_INSTALLATION_LOCALE.md).
5. Vérifier les tests backend et la compilation frontend.
6. Ne jamais casser : permissions par source, séparation competence/curriculum, modèles stricts, contrats R4, non-invention de données.
