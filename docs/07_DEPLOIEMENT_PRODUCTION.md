# 07 — Déploiement production (Caddy HTTPS)

> ⚠️ **Statut : préparé côté applicatif, NON testé en conditions réelles**
> tant qu'aucun serveur public n'est disponible. Tout est prêt (fichiers,
> variables, procédure) ; la validation des critères se fera au premier
> déploiement.

## Local vs serveur — la règle absolue

```bash
# LOCAL (PC de dev) — la seule commande du quotidien :
docker compose up -d

# SERVEUR (avec domaine + DNS) — et UNIQUEMENT là :
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Lancer le compose de production en local échoue volontairement (variables
`APP_DOMAIN`… exigées) : c'est un garde-fou. En local, seule la commande de
vérification est autorisée (elle ne lance rien) :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

## Prérequis serveur

1. **VPS** avec Docker + Docker Compose ≥ 2.24 (requis pour `ports: !reset`).
2. **Nom de domaine** + 2 enregistrements DNS **A** vers l'IP du serveur :
   `app.<domaine>` et `api.<domaine>` (vérifier la propagation avec
   `nslookup` avant de lancer, sinon Let's Encrypt échoue).
3. **Pare-feu** : ports entrants **80 et 443 uniquement** (+ 443/UDP
   optionnel pour HTTP/3). Ne pas ouvrir 8000/8050/5432.

## Variables `.env` (sur le serveur, jamais commité)

```env
APP_ENV=production
AUTH_SECRET_KEY=<généré : python -c "import secrets; print(secrets.token_urlsafe(48))">
FLASK_SECRET_KEY=<généré, différent du précédent>
POSTGRES_PASSWORD=<mot de passe fort>
DOMAIN=exemple.fr
APP_DOMAIN=app.exemple.fr
API_DOMAIN=api.exemple.fr
ACME_EMAIL=contact@exemple.fr
TRUSTED_HOSTS=app.exemple.fr,api.exemple.fr
# DASHBOARD_BASE_URL est fixé automatiquement par docker-compose.prod.yml
# à https://APP_DOMAIN (liens invités corrects).
```

Note : les hosts internes (`localhost`, `127.0.0.1`, `backend`) sont ajoutés
automatiquement à `TRUSTED_HOSTS` par l'application — ne lister que les
domaines publics.

## Ce que fait Caddy

- **HTTPS automatique** (certificats Let's Encrypt, renouvellement auto,
  persistés dans le volume `caddy_data`) + redirection HTTP→HTTPS.
- **Reverse proxy** : `app.<domaine>` → frontend:8050, `api.<domaine>` →
  backend:8000.
- Seuls **80/443** sont publics : `docker-compose.prod.yml` retire les ports
  de backend et frontend (`ports: !reset []`) ; postgres n'a jamais eu de
  port public. Tout le trafic interne passe par le réseau Docker.
- Compression (zstd/gzip), en-têtes de sécurité (HSTS, nosniff…), logs
  d'accès JSON (`docker logs forested_caddy`).
- En production, l'API désactive `/docs`, `/redoc` et `/openapi.json`, le
  backend tourne sans `--reload` avec 4 workers, et les cookies de session
  passent en `Secure`.

## Procédure et vérifications

Procédure détaillée : voir `DOC_C1_deploiement.md` (à la racine, livré avec le
Caddyfile). Résumé des vérifications après `up -d --build` :

```bash
docker logs forested_caddy --tail 50        # "certificate obtained" x2
curl -I https://api.exemple.fr/health       # 200
curl -I https://app.exemple.fr              # 200 (dashboard)
curl -I https://api.exemple.fr/docs         # 404 attendu (prod)
curl -I http://IP_DU_SERVEUR:8000           # échec attendu (port fermé)
```

Puis au navigateur : login sur `https://app.<domaine>`, navigation complète,
un lien invité `/access/<clé>`, et un appel client
`https://api.<domaine>/api/v1/competences` avec `X-API-Key`.

## Étapes suivantes (après C1)

| Étape | Contenu | Statut |
|---|---|---|
| **C2** | Rate limiting (login / API) au niveau proxy | à préparer |
| **C3** | Sauvegardes : dump PostgreSQL quotidien + copie de `data/` | à préparer |
| **C4** | Monitoring : uptime sur `/health`, alerting | à préparer |
