# 08 — Troubleshooting

Premier réflexe : lire les logs, pas deviner.

```bash
docker compose ps -a
docker logs forested_backend --tail 100
docker logs forested_frontend --tail 100
```

## 1. Build impossible : `TLS handshake timeout` / `no such host`

Problème réseau Docker Hub. Utiliser les images locales :

```bash
docker compose up -d
```

`--build` n'est nécessaire que si `requirements.txt` ou un Dockerfile a changé.

## 2. Conteneur bloqué en `Removing`

Symptôme :

```text
Container forested_frontend Removing
```

Solution sûre :

```bash
Ctrl+C
docker ps -a
docker rm -f forested_frontend
docker compose down
docker compose up -d
```

Si Docker Desktop / WSL reste bloqué :

```bash
wsl --shutdown
```

Puis redémarrer Docker Desktop.

À ne pas faire pour ce cas :

```bash
docker compose down -v
docker volume prune
```

car cela peut supprimer le volume PostgreSQL.

## 3. Backend attaque SQLite au lieu de PostgreSQL

Symptôme : erreurs SQLite pendant Alembic.

Cause probable : `DATABASE_URL=sqlite:///...` dans `.env`.

Solution : supprimer cette ligne et relancer le backend.

## 4. `forested_backend Exited (1)`

Lire la première erreur :

```bash
docker compose logs --no-color --tail=150 backend
```

| Symptôme | Cause probable | Action |
|---|---|---|
| `No module named app` | mauvais chemin Alembic | vérifier `prepend_sys_path = .` |
| `password authentication failed` | mot de passe PostgreSQL changé avec volume existant | restaurer l'ancien mot de passe ou recréer volontairement le volume |
| `RuntimeError AUTH_SECRET_KEY` | `APP_ENV=production` en local | retirer `APP_ENV=production` |
| erreur Pydantic `extra_forbidden` | champ non prévu dans le modèle | ne pas injecter de champ canonique non déclaré |

## 5. `/docs` renvoie 404

En production, c'est normal. En local, vérifier que `APP_ENV=production` n'est pas actif.

## 6. Upload USMB MATH → 422

Comportement voulu si le fichier est hors gabarit. Le fichier raw rejeté doit être nettoyé automatiquement.

## 7. UNITA : les modules spécifiques USMB ne s'affichent pas

Vérifier d'abord le processed : les modules `USMB_*` doivent avoir des `acquis_apprentissage` non vides quand la colonne `Correspondance générique` est remplie.

Si aucun module USMB n'a de MLO :

- vérifier la colonne `Correspondance générique` dans l'Excel ;
- vérifier l'ordre d'import : compétence générique, curriculum générique, Excel USMB ;
- relancer le pipeline après correction.

Si les MLO existent dans le processed mais pas dans la vue :

- vérifier `front/app/forested_visualisations.py` ;
- relancer le frontend ;
- vider le cache navigateur si nécessaire.

## 8. UNITA : apparition de `S-1` ou `COMMON=-1`

`S-1` vient du catalogue générique UNITA. Ce n'est pas un vrai semestre institutionnel.

Correction attendue : côté visualisation, masquer ou neutraliser le catalogue générique quand les modules spécifiques USMB existent. Ne pas modifier le modèle pour résoudre ce problème d'affichage.

## 9. UNITA : graphe trop dense

Normal si la vue affiche toutes les compétences, tous les MLO et tous les modules. Utiliser :

- filtre Compétence ;
- filtre Semestre ;
- forêt curriculaire avec clic sur UE/module ;
- sunburst en mode distribution semestrielle.

La densité n'est pas automatiquement un bug. Il faut distinguer :

```text
données fausses      → problème ETL
liens corrects mais vue illisible → problème visualisation/ergonomie
```

## 10. Rappels de prudence

- `docker compose down` : OK.
- `docker compose down -v` : dangereux pour PostgreSQL.
- Ne pas supprimer `data/processed` ou `data/analytics` sans savoir quels fichiers doivent être régénérés.
- Après modification frontend : `docker compose restart frontend` suffit souvent.
- Après modification backend/ETL : relancer le backend ou le pipeline selon le fichier modifié.
