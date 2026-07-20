# 05 — Guide client de l'API

Guide destiné aux intégrations techniques utilisant une **clé API de type
`data`** fournie par un administrateur ForestED.

## Base URL

```
Local        : http://127.0.0.1:8000/api/v1
Production   : https://api.<domaine>/api/v1
```

Le healthcheck est volontairement HORS préfixe : `GET /health` (sans
`/api/v1`).

## Authentification

Chaque requête porte la clé dans le header :

```
X-API-Key: fed_xxxxxxxxxxxxxxxx
```

> ⚠️ La clé est un secret : ne jamais la mettre dans une URL, un dépôt git ou
> un code JavaScript côté navigateur. Elle a été affichée UNE SEULE FOIS à sa
> création ; en cas de perte ou de fuite, demander sa désactivation et une
> nouvelle clé.

**Les réponses sont automatiquement filtrées par source** : la clé ne voit
que les données des sources qui lui ont été accordées (et selon ses scopes
`read:competence` / `read:curriculum` / `read:analytics`). Aucun paramètre à
passer — le serveur décide.

## Endpoints principaux

| Méthode & chemin | Description |
|---|---|
| `GET /api/v1/competences` | Référentiels de compétences (fichiers processed) des sources autorisées |
| `GET /api/v1/curricula` | Curricula/maquettes des sources autorisées |
| `GET /api/v1/analytics/{domain}` | Tables plates (`domain` = `competence` ou `curriculum`) |
| `GET /api/v1/auth/key-info` | Métadonnées de la clé courante (nom, type, sources) — utile pour valider une clé |
| `GET /health` | État du service (public, sans clé) |

Format de réponse des endpoints de données :

```json
{
  "status": "success",
  "count": 2,
  "data": [
    {"source": "Polytech", "programme": "IDU", "file": "…_processed.json", "data": { … }},
    …
  ]
}
```

## Exemples curl

```bash
# Santé du service (sans clé)
curl https://api.exemple.fr/health

# Valider sa clé
curl -H "X-API-Key: fed_XXXX" https://api.exemple.fr/api/v1/auth/key-info

# Récupérer les référentiels de compétences autorisés
curl -H "X-API-Key: fed_XXXX" https://api.exemple.fr/api/v1/competences

# Table plate curriculum
curl -H "X-API-Key: fed_XXXX" https://api.exemple.fr/api/v1/analytics/curriculum
```

## Exemple Python (requests)

```python
import requests

BASE = "https://api.exemple.fr/api/v1"      # local : http://127.0.0.1:8000/api/v1
HEADERS = {"X-API-Key": "fed_XXXX"}          # depuis une variable d'env, jamais en dur

info = requests.get(f"{BASE}/auth/key-info", headers=HEADERS, timeout=15)
info.raise_for_status()
print("Clé :", info.json())                  # {"name": ..., "kind": ..., "sources": [...]}

resp = requests.get(f"{BASE}/competences", headers=HEADERS, timeout=30)
resp.raise_for_status()
payload = resp.json()
for item in payload["data"]:
    print(item["source"], item["programme"], item["file"])
```

## Codes d'erreur

| Code | Signification | Que faire |
|---|---|---|
| **401** | Non authentifié : clé absente, inconnue, expirée ou désactivée | Vérifier le header ; demander une nouvelle clé si besoin |
| **403** | Authentifié mais non autorisé (scope/route hors droits de la clé — ex. routes admin) | Utiliser uniquement les endpoints de données |
| **404** | Route absente — souvent un chemin sans `/api/v1`, ou `/docs` en production | Vérifier la base URL |
| **422** | Requête ou contenu invalide (concerne surtout les routes admin d'upload) | Consulter le champ `detail` de la réponse |

Toutes les erreurs sont renvoyées en JSON : `{"detail": "message"}`.
