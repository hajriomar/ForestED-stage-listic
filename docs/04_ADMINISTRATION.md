# 04 — Administration

**Sommaire** : [Rôles](#rôles) · [Utilisateurs](#utilisateurs) ·
[Permissions](#permissions-par-source) · [Clés API](#clés-api) ·
[Upload](#upload-de-fichiers-sources) · [UNITA](#ordre-dimport-recommandé-pour-unita--scrl) ·
[Import API](#import-depuis-une-api-json) · [Pipeline](#relancer-le-pipeline-complet) ·
[Bonnes pratiques](#bonnes-pratiques)

La page **Administration** est réservée au rôle `admin`. Les contrôles sont aussi refaits côté backend : cacher un bouton dans le frontend ne suffit jamais à autoriser une action.

## Rôles

| Rôle | Droits |
|---|---|
| **admin** | Accès total aux données, utilisateurs, permissions, clés API, upload/import, pipeline. |
| **viewer** | Lecture seule des sources autorisées. |

## Utilisateurs

Actions disponibles : créer, modifier, activer/désactiver et supprimer.

Garde-fous backend : impossible de se désactiver soi-même, de se rétrograder soi-même, ou de supprimer/désactiver le dernier admin actif.

## Permissions par source

Une permission s'applique à une source :

```text
BUT
Polytech
usmb_licence
unita
*
```

Scopes possibles :

```text
read:competence
read:curriculum
read:analytics
*
```

La source `*` donne accès à toutes les sources actuelles et futures. À réserver aux comptes de confiance.

## Clés API

| Type | Usage |
|---|---|
| **data** | Intégration technique avec header `X-API-Key`. |
| **dashboard** | Lien invité `/access/<clé>` pour partager une visualisation en lecture seule. |

Règles : le secret est affiché une seule fois ; une clé désactivée ne se réactive pas ; une clé n'est jamais admin ; une clé par client permet de couper un seul accès en cas de problème.

## Upload de fichiers sources

Section : **Fichiers sources → Fichier local**.

| Champ | Rôle |
|---|---|
| **Domaine** | `competence` ou `curriculum`. |
| **Source** | Source du pipeline : `Polytech`, `BUT`, `usmb_licence`, `unita`, etc. |
| **Formation** | Préfixe logique du fichier, par exemple `IDU`, `QLIO`, `SCRL`. |
| **Fichier** | `.json`, `.xlsx`, `.xls`, `.csv`, 20 Mo max. |

Le fichier est enregistré dans :

```text
raw/<domaine>/<source>/<FORMATION>_<nom_fichier>
```

Puis traité immédiatement. Une erreur 422 supprime le fichier raw rejeté pour éviter les résidus.

## Ordre d'import recommandé pour UNITA / SCRL

Pour la source `unita`, respecter l'ordre suivant :

```text
1. Domaine competence / source unita / formation SCRL
   → référentiel générique UNITA : PLO, MLO, modules génériques.

2. Domaine curriculum / source unita / formation SCRL
   → curriculum générique UNITA corrigé : catalogue de modules génériques.

3. Domaine curriculum / source unita / formation SCRL
   → Excel institutionnel USMB avec la colonne Correspondance générique.
```

La colonne `Correspondance générique` permet d'hériter les MLO dans les modules spécifiques USMB. Une cellule vide signifie : aucun héritage.

Valeurs attendues dans cette colonne :

```text
Business
Economics
Finance
HR
Marketing
Language B
Language C
```

Ne pas écrire les codes techniques `UNITA_M1`, `UNITA_BUSINESS`, etc. dans l'Excel utilisateur, sauf décision explicite de changer la règle métier.

## Import depuis une API JSON

L'import API accepte une URL HTTP/HTTPS en GET, avec protections : refus des adresses privées/localhost, redirections refusées, JSON obligatoire, taille max 20 Mo, mêmes règles 409/422 que l'upload local.

## Relancer le pipeline complet

Le bouton **Relancer le pipeline** retraite tous les fichiers présents dans `raw/` et régénère `processed/` et `analytics/`.

À utiliser après modification d'un normalizer, d'un transformer, de la registry ou après correction de données sources.

## Bonnes pratiques

- Attribuer les permissions au plus petit périmètre possible.
- Préférer une clé par client.
- Vérifier les fichiers `*_quality.json` après chaque nouvelle source.
- Pour UNITA, vérifier que les modules USMB mappés ont des `acquis_apprentissage` après l'import.
- Ne jamais utiliser `docker compose down -v` pour résoudre un simple problème d'affichage ou de redémarrage.
