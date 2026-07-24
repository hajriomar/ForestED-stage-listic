# 10 — Source UNITA : Joint Degree SCRL

## Objectif du document

Ce document explique l'intégration de la source **UNITA — SCRL** dans ForestED.
Il doit permettre à un développeur ou à un futur stagiaire de comprendre :

- ce que représente un Joint Degree dans ForestED ;
- quelles données sont génériques et quelles données sont institutionnelles ;
- comment la colonne `Correspondance générique` est utilisée ;
- pourquoi les MLO sont hérités dans les modules spécifiques ;
- quelles règles ne doivent pas être cassées.

## Idée métier

UNITA / SCRL est une formation commune portée par plusieurs établissements. Dans ForestED, on la représente avec deux couches complémentaires.

| Couche | Contenu | Rôle |
|---|---|---|
| **Générique UNITA** | PLO, MLO, modules génériques. | Décrit les compétences et acquis communs du diplôme. |
| **Institutionnelle USMB** | Semestres, UE/groupes, modules réels de l'Excel USMB. | Décrit la maquette réellement suivie par les étudiants USMB. |

Le but n'est pas de remplacer la maquette USMB par le catalogue générique. Le but est de relier les modules USMB aux PLO à travers les MLO.

## Principe validé

La liaison finale est :

```text
PLO / compétence
→ AC canonique construit à partir du PLO et du MLO
→ MLO
→ module spécifique USMB
```

La relation suivante ne doit pas être utilisée comme relation métier finale :

```text
module USMB → module générique UNITA
```

La correspondance générique sert seulement d'indication d'ETL pour hériter les MLO.

## Fichiers sources

### 1. Référentiel compétence générique

Domaine :

```text
competence
```

Source :

```text
unita
```

Rôle : produire les PLO, les MLO et les AC canoniques.

Exemple d'AC canonique :

```text
PLO2__UNITA_ECONOMICS_MLO01
```

La partie avant `__` indique le PLO. La partie après `__` indique le MLO.

### 2. Curriculum générique UNITA

Domaine :

```text
curriculum
```

Rôle : porter le catalogue des modules génériques et leurs MLO.

Exemples :

```text
UNITA_BUSINESS
UNITA_ECONOMICS
UNITA_FINANCE
UNITA_HR
UNITA_MARKETING
UNITA_M1
UNITA_M2
UNITA_M3
UNITA_M4
UNITA_M5
```

Ces modules ne sont pas des UE institutionnelles USMB. Ils servent de référence.

### 3. Maquette institutionnelle Excel USMB

Domaine :

```text
curriculum
```

Rôle : créer les vrais modules curriculum : semestres, UE/groupes, ECTS, heures, modules spécifiques.

Exemples :

```text
USMB_S1_E02 — Economie générale 1
USMB_S1_E03 — Introduction au management des organisations
USMB_S1_E10 — Espagnol : Structures de la langue - Théorie
```

## Colonne `Correspondance générique`

L'Excel USMB contient une colonne ajoutée :

```text
Correspondance générique
```

Elle contient une valeur lisible, pas un code technique.

Valeurs autorisées :

```text
Business
Economics
Finance
HR
Marketing
Language B
Language C
```

À éviter dans l'Excel utilisateur :

```text
UNITA_BUSINESS
UNITA_M1
UNITA_ECONOMICS
```

Ces codes sont internes au pipeline.

## Résolution des correspondances

### Modules métier

| Valeur Excel | Code interne |
|---|---|
| `Business` | `UNITA_BUSINESS` |
| `Economics` | `UNITA_ECONOMICS` |
| `Finance` | `UNITA_FINANCE` |
| `HR` | `UNITA_HR` |
| `Marketing` | `UNITA_MARKETING` |

### Modules de langue

Les langues dépendent de l'année de la feuille.

| Feuille | Valeur Excel | Code interne |
|---|---|---|
| JD L1 | `Language B` | `UNITA_M1` |
| JD L1 | `Language C` | `UNITA_M2` |
| JD L2 | `Language B` | `UNITA_M3` |
| JD L2 | `Language C` | `UNITA_M4` |
| JD L3 | `Language C` | `UNITA_M5` |

Une cellule vide signifie :

```text
ne pas hériter de MLO
```

C'est volontaire pour les lignes non stabilisées ou sans équivalent générique fiable.

## Héritage des MLO

Exemple Excel :

```text
Economie générale 1 → Economics
```

Le pipeline fait :

```text
Economics → UNITA_ECONOMICS
UNITA_ECONOMICS → liste de MLO
USMB_S1_E02 reçoit ces MLO dans acquis_apprentissage
```

Exemple processed attendu :

```json
{
  "id": "USMB_S1_E02",
  "nom": "Economie générale 1",
  "acquis_apprentissage": [
    {
      "id": "UNITA_ECONOMICS_MLO01",
      "description": "..."
    }
  ]
}
```

Le modèle curriculum n'a pas été modifié. On utilise le champ existant `acquis_apprentissage`.

## Pipeline détaillé

```text
1. Extractor
   lit JSON ou Excel.

2. Normalizer UNITA
   lit la structure source.
   détecte la colonne Correspondance générique.
   produit des records avec generic_module_code.

3. Transformer competence UNITA
   produit les PLO, niveaux et AC canoniques PLOx__MLO.

4. Transformer curriculum UNITA
   produit le Programme canonique et les lignes flat/upsert.

5. Upsert curriculum
   fusionne catalogue générique + maquette USMB.
   copie les MLO génériques vers les modules spécifiques.

6. Visualisation
   joint les PLO aux modules spécifiques via les MLO.
```

## Visualisations

### Chemin classique

Pour Polytech, BUT et beaucoup de sources classiques :

```text
AC.modules → module curriculum
```

### Chemin Joint Degree

Pour UNITA :

```text
module.acquis_apprentissage[MLO]
→ AC canonique PLOx__MLO
→ PLO / compétence
```

Les vues doivent afficher prioritairement les modules spécifiques USMB. Le catalogue générique peut rester visible seulement pour signaler une zone encore non mappée, par exemple `UNITA_FINANCE` si aucun module spécifique n'est encore mappé à `Finance`.

## Import recommandé

Dans l'administration :

```text
1. competence / unita / SCRL / référentiel générique PLO-MLO
2. curriculum / unita / SCRL / curriculum générique corrigé
3. curriculum / unita / SCRL / Excel USMB avec Correspondance générique
```

Après modification d'un normalizer ou transformer : relancer le pipeline ou réimporter dans le même ordre.

## Vérifications

### Vérifier la compilation frontend

```bash
docker compose exec frontend python -m py_compile /app/forested_visualisations.py
```

### Vérifier les tests backend

```bash
docker exec -it forested_backend python -m pytest tests/ -q
```

### Vérifier les MLO hérités

Vérifier dans `data/processed/curriculum/unita/SCRL_processed.json` que les modules `USMB_*` mappés ont un champ `acquis_apprentissage` non vide.

## Limites connues

- Les vues globales UNITA sont denses parce qu'un MLO peut être lié à plusieurs PLO et plusieurs modules.
- S6 peut rester vide si la maquette n'est pas encore stabilisée.
- `Finance` peut rester générique si aucun module USMB n'est mappé vers `Finance`.
- Les modules génériques ne doivent pas être interprétés comme de vraies UE USMB.

## À ne pas faire

```text
❌ Ajouter references_elements au modèle sans décision métier officielle.
❌ Mettre les codes UNITA_* directement dans l'Excel utilisateur.
❌ Copier des MLO quand Correspondance générique est vide.
❌ Présenter COMMON=-1 / S-1 comme un vrai semestre.
❌ Modifier le backend API pour résoudre un problème purement visuel.
❌ Casser le chemin classique AC.modules utilisé par Polytech, BUT et USMB licence.
```

## Fichiers concernés

À connaître pour maintenir UNITA :

```text
app/etl/normalize/unita_curriculum_normalizer.py
app/etl/transform/competence/UNITA_competence_transformer.py
app/etl/transform/curriculum/UNITA_curriculum_transformer.py
app/etl/load/curriculum_upsert_service.py
front/app/forested_visualisations.py
```

Fichiers normalement non concernés :

```text
app/models/curriculum_models.py
app/models/competency_models.py
app/etl/extract/excel_extractor.py
app/etl/pipeline.py
front/app/api_client.py
```
