# 04 — Administration

**Sommaire** : [Rôles](#rôles) · [Utilisateurs](#utilisateurs) ·
[Permissions](#permissions-par-source) · [Clés API](#clés-api) ·
[Upload de fichiers](#upload-de-fichiers-sources) · [Import API](#import-depuis-une-api-json) ·
[Pipeline](#relancer-le-pipeline-complet) · [Bonnes pratiques](#bonnes-pratiques)

La page **Administration** (sidebar : Utilisateurs · Permissions par source ·
Clés API · Fichiers sources) n'est visible que pour le rôle `admin`. Chaque
action est re-vérifiée côté backend. Toutes les actions destructives passent
par un **panneau de confirmation** ; « Annuler » ne déclenche rien.

## Rôles

- **admin** : accès total (données de toutes les sources, administration,
  pipeline).
- **viewer** : accès en lecture aux seules sources autorisées par ses
  permissions.

## Utilisateurs

- **Créer** : formulaire (nom, email, mot de passe ≥ 10 caractères, rôle).
- **Modifier** : formulaire « Modifier un utilisateur » — nouveau nom, nouvel
  email, rôle, mot de passe (unicité vérifiée par le backend).
- **Activer / Désactiver** : boutons par ligne dans le tableau (vert/orange).
  Un utilisateur désactivé ne peut plus se connecter ; réactivable à tout
  moment.
- **Supprimer** : bouton rouge par ligne — supprime aussi ses permissions.
- Garde-fous anti-lockout (backend) : impossible de se désactiver soi-même,
  de se rétrograder soi-même, ou de supprimer/désactiver le **dernier admin
  actif** — l'erreur est affichée explicitement.

## Permissions (par source)

Sélectionner un utilisateur → son tableau de permissions s'affiche.

- **Ajouter / mettre à jour** : choisir une ou plusieurs sources + scopes
  (`read:competence`, `read:curriculum`, `read:analytics`, ou « tous les
  droits de lecture `*` »).
- **Retirer** : bouton rouge par ligne (avec confirmation) — l'utilisateur
  perd immédiatement l'accès à la source.
- La source **`*`** = toutes les sources, actuelles ET futures. À réserver
  aux comptes de confiance.

## Clés API

Deux types :

| Type | Usage |
|---|---|
| **data** | Intégration technique : le client appelle l'API avec le header `X-API-Key` (voir [05_API_CLIENT.md](05_API_CLIENT.md)). |
| **dashboard** | Partage du dashboard : la création affiche un **lien** `/access/<clé>` à transmettre au client (session invitée, lecture seule). |

Règles importantes :

- Le **secret est affiché UNE SEULE FOIS** à la création (seule son empreinte
  SHA-256 est stockée). En cas de perte : désactiver et recréer.
- **La désactivation est DÉFINITIVE** : pas de réactivation ni de
  prolongation (choix de sécurité assumé). Le tableau affiche l'état
  (Actif / Désactivé / Expiré), l'expiration et le dernier usage.
- Une clé n'est **jamais** admin (ni routes `/admin`, ni pipeline).
- Expiration optionnelle à la création (« Expire dans N jours », vide =
  jamais).

## Upload de fichiers sources

Section **Fichiers sources → Fichier local** :

- **Domaine** : Compétences ou Curricula ;
- **Source** : le dropdown propose les sources présentes dans les données ET
  les sources supportées par le pipeline (registry) — une nouvelle source est
  donc proposable avant son premier fichier ;
- **Formation** : préfixe du fichier (`[A-Za-z0-9_-]`, ex. `DROIT`, `QLIO`) ;
- **Fichier** : `.json`, `.xlsx`, `.xls`, `.csv` — 20 Mo max.

Le fichier est enregistré dans `raw/<domaine>/<source>/<FORMATION>_<nom>` puis
**traité immédiatement — lui seul** (jamais de relance globale). Erreurs :

- **409** : un fichier du même nom existe déjà (pas d'écrasement silencieux) ;
- **422** : le pipeline a rejeté le fichier (format non reconnu, ex. USMB
  MATH hors gabarit) — le fichier raw est alors **supprimé automatiquement**,
  aucun résidu.

## Import depuis une API JSON

Section **Fichiers sources → API JSON** : mêmes champs + URL (http/https,
GET uniquement). Protections intégrées : refus des adresses privées/localhost
(anti-SSRF), redirections refusées, réponse JSON obligatoire, 20 Mo max,
en-têtes sensibles jamais journalisés. Comportement 409/422 identique à
l'upload.

## Relancer le pipeline complet

Bouton « Relancer le pipeline » (section Fichiers sources, avec
confirmation) : retraite **tous** les fichiers de `raw/` (toutes sources,
tous domaines) et régénère `processed/` et `analytics/` — sans rien supprimer
ni re-téléverser. Utile après une mise à jour des transformers. L'opération
peut prendre plusieurs minutes (un spinner s'affiche).

## Bonnes pratiques

- Ne pas donner la source `*` à tout le monde — attribuer les sources au cas
  par cas.
- **Partage d'un dashboard** → clé de type `dashboard` (lien) ;
  **intégration technique** → clé de type `data` (header X-API-Key).
- Conserver le principe « un client = une clé » : la désactivation coupe
  alors un seul client.
- Vérifier le `*_quality.json` dans `analytics/` après l'upload d'une
  nouvelle source USMB.
