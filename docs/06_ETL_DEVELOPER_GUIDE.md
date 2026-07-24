# 06 — Guide développeur ETL : ajouter ou maintenir une source

**Sommaire** : [Architecture](#architecture-etl) · [Registry](#registry-déclarative) ·
[Ajouter une source](#ajouter-une-nouvelle-source-pas-à-pas) · [Modèles](#les-modèles-canoniques) ·
[Cas USMB](#le-cas-usmb-référence-dimplémentation) · [Cas UNITA](#le-cas-unita--joint-degree-scrl) ·
[Visualisations](#impact-sur-les-visualisations) · [Règles d'or](#règles-dor)

## Architecture ETL

```text
raw/<domaine>/<source>/FICHIER
   │
   ├─ Extractor   : lit le format technique (json/xlsx/csv)
   │
   ├─ Normalizer  : connaît la structure de la source
   │
   ├─ Transformer : construit le modèle canonique + flat + quality_report
   │
   └─ Loader      : écrit processed/ et analytics/
```

| Étape | Sait quoi | Ne sait pas |
|---|---|---|
| **Extractor** | Format technique : JSON, Excel, CSV. | Métier, compétences, UE, MLO. |
| **Normalizer** | Structure de la source : feuilles, colonnes, marqueurs, correspondances. | Modèle canonique Pydantic complet. |
| **Transformer** | Métamodèle : competence ou curriculum. | Format brut Excel/JSON. |
| **Loader / Upsert** | Où écrire, comment fusionner une source multi-fichiers. | Sémantique fine de la source. |

Le pipeline reste générique : il enchaîne les factories et ne doit pas contenir de logique spécifique à une source.

## Registry déclarative

Les factories `TransformerFactory` et `NormalizerFactory` sélectionnent les classes par couple :

```python
(domain, source) -> (module_python, classe)
```

Ajouter une source doit rester localisé : normalizer dédié, transformer(s) dédié(s), entrée registry, tests et documentation.

## Ajouter une nouvelle source, pas à pas

1. **Analyser les vrais fichiers** : feuilles, colonnes, valeurs vides, couleurs, cellules fusionnées, lignes fantômes, feuilles cachées.
2. **Identifier les domaines alimentés** : competence, curriculum, ou les deux.
3. **Réutiliser l'extractor existant** quand le format est déjà supporté.
4. **Créer un normalizer source-spécifique** : toute l'intelligence de parsing vit ici.
5. **Créer un transformer par domaine** : il reçoit des records normalisés, jamais le fichier brut.
6. **Produire canonical + flat + quality_report**.
7. **Mettre à jour la registry**.
8. **Tester** : normalizer, transformer, pipeline, contrats R4, non-régression frontend.
9. **Documenter** : source, limites, ordre d'import, qualité, règles de visualisation.

## Les modèles canoniques

### Competence

```text
ReferentielCompetences
→ SousClassification
→ Competence
→ NiveauDeveloppement
→ ApprentissageCritique
```

`ApprentissageCritique.modules` est une liste de codes de modules. Ce sont des références, pas des objets curriculum.

### Curriculum

```text
Programme
→ PeriodeProgramme
→ GroupeElementsPedagogiques
→ ElementPedagogique
→ AcquisApprentissage
```

Les éléments pédagogiques réels appartiennent au curriculum : ECTS, heures, enseignants, institution, ressources, acquis d'apprentissage, etc.

### Modèles stricts

Les modèles sont stricts. Ne pas ajouter un champ au JSON canonique sans l'ajouter officiellement au modèle et sans tests. Pour UNITA, aucun champ `references_elements` n'a été ajouté : la liaison passe par les MLO dans `acquis_apprentissage`.

## Le cas USMB (référence d'implémentation)

`usmb_licence` utilise un même normalizer pour extraire les informations utiles aux deux domaines : compétences, niveaux, AC, liens AC↔EC, semestre, UA, parcours et module code.

Le domaine curriculum est un **curriculum-lite** :

```text
Semestre → UA → EC
ECTS/heures = 0.0 quand absents
quality_report explicite
```

La clé de jointure est le `module_code`, calculé une seule fois dans le normalizer.

## Le cas UNITA / Joint Degree SCRL

UNITA combine une couche générique et une couche institutionnelle.

### Données d'entrée

| Fichier | Domaine | Rôle |
|---|---|---|
| Référentiel générique PLO/MLO | `competence` | Produit PLO, MLO et AC canoniques `PLOx__MLO`. |
| Curriculum générique UNITA | `curriculum` | Catalogue des modules génériques qui portent les MLO. |
| Excel USMB | `curriculum` | Maquette institutionnelle réelle : semestres, UE/groupes, modules spécifiques. |

### Principe validé

```text
PLO / compétence
→ AC canonique PLOx__MLO
→ MLO
→ module spécifique USMB
```

La colonne Excel `Correspondance générique` ne crée pas une relation métier directe module-module. Elle sert uniquement à savoir de quel module générique hériter les MLO.

### Valeurs acceptées dans l'Excel

```text
Business
Economics
Finance
HR
Marketing
Language B
Language C
```

Le normalizer résout :

```text
Business  -> UNITA_BUSINESS
Economics -> UNITA_ECONOMICS
Finance   -> UNITA_FINANCE
HR        -> UNITA_HR
Marketing -> UNITA_MARKETING
```

Pour les langues, la résolution dépend de l'année :

```text
JD L1 + Language B -> UNITA_M1
JD L1 + Language C -> UNITA_M2
JD L2 + Language B -> UNITA_M3
JD L2 + Language C -> UNITA_M4
JD L3 + Language C -> UNITA_M5
```

Une cellule vide signifie : ne pas hériter de MLO. C'est utile pour S6 ou pour les modules sans équivalent générique fiable.

### Où se fait l'héritage ?

- Le normalizer lit la colonne `Correspondance générique` et produit un `generic_module_code` dans les records/flat techniques.
- Le transformer curriculum garde le canonical propre et conserve les métadonnées utiles dans le flat/upsert.
- Le service d'upsert curriculum copie les MLO du module générique dans `acquis_apprentissage` du module spécifique.
- Le modèle curriculum n'est pas modifié.

### Exemple attendu

```json
{
  "id": "USMB_S1_E02",
  "nom": "Economie générale 1",
  "acquis_apprentissage": [
    {"id": "UNITA_ECONOMICS_MLO01", "description": "..."}
  ]
}
```

## Impact sur les visualisations

Les visualisations doivent utiliser deux chemins :

```text
Chemin classique : AC.modules -> module
Chemin UNITA : module.acquis_apprentissage[MLO] -> AC canonique PLOx__MLO -> compétence
```

Ne pas faire dépendre toutes les sources du chemin UNITA. Polytech, BUT et USMB licence doivent continuer à fonctionner par `ac.modules`.

Pour UNITA, le catalogue générique peut être masqué en vue globale quand des modules spécifiques portent déjà ses MLO. Cela relève de l'affichage, pas du modèle.

## Tests minimaux recommandés

```bash
# Backend
docker exec -it forested_backend python -m pytest tests/ -q

# Frontend
docker compose exec frontend python -m py_compile /app/forested_visualisations.py
```

Vérification spécifique UNITA : compter les modules `USMB_*` avec `acquis_apprentissage` non vide dans `SCRL_processed.json`.

## Règles d'or

1. **Ne pas inventer une donnée absente.** Une cellule vide, un ECTS absent ou un mapping incertain doit être signalé ou laissé vide.
2. **Ne pas mélanger competence et curriculum.** Les vrais modules restent dans le curriculum.
3. **Ne pas ajouter de champ canonique sans raison métier forte.** Préférer les `quality_report`, flat ou index analytics pour la traçabilité technique.
4. **Valider sur les vrais fichiers.** Les fixtures ne suffisent pas.
5. **Protéger les autres sources.** Une correction UNITA ne doit pas changer le comportement Polytech, BUT ou USMB licence.
6. **Documenter chaque règle source-spécifique.** Ce qui est évident dans le code aujourd'hui doit être compréhensible par le prochain développeur.
