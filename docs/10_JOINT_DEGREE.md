# 10 — Source UNITA : Joint Degree SCRL

## Objectif

Ce document décrit l’intégration de la source **UNITA — SCRL** dans ForestED.
Le cas UNITA est un exemple de **Joint Degree** : une formation commune est décrite à deux niveaux :

1. un niveau **générique** : PLO, MLO et modules génériques du diplôme commun ;
2. un niveau **institutionnel** : maquette réelle d’un établissement, ici USMB, avec semestres, UE/groupes et modules spécifiques.

L’objectif n’est pas de remplacer la maquette USMB par des modules génériques, mais de relier les modules USMB aux compétences/PLO à travers les MLO.

## Principe métier validé

La liaison finale utilisée par ForestED est :

```text
PLO / compétence
→ AC canonique construit depuis le PLO et le MLO
→ MLO hérité
→ module spécifique USMB
```

Il ne faut pas créer de relation métier directe de type :

```text
module USMB → module générique UNITA
```

La correspondance avec un module générique sert seulement à transmettre les MLO dans `acquis_apprentissage` du module spécifique.

## Données sources

### Domaine competence

Le domaine competence décrit le référentiel générique UNITA :

```text
Référentiel UNITA
→ PLO
→ MLO
→ modules génériques
```

Les AC canoniques sont construits sous une forme proche de :

```text
PLO2__UNITA_ECONOMICS_MLO01
```

Le suffixe après `__` correspond au MLO. C’est cette partie qui permet ensuite la jointure avec les modules spécifiques.

### Domaine curriculum

Le domaine curriculum contient deux couches :

1. **Catalogue générique UNITA** : modules comme `UNITA_BUSINESS`, `UNITA_ECONOMICS`, `UNITA_M1`, etc. Il sert de source de MLO.
2. **Maquette institutionnelle USMB** : semestres, UE/groupes, modules réels extraits de l’Excel.

Les modules génériques ne doivent pas être affichés comme de vraies UE USMB quand des modules spécifiques existent déjà.

## Colonne “Correspondance générique” dans l’Excel

L’Excel USMB contient une colonne ajoutée :

```text
Correspondance générique
```

Elle permet de dire à quel module générique un module spécifique correspond.

Valeurs utilisées :

```text
Business
Economics
Finance
HR
Marketing
Language B
Language C
```

Règles :

- `Business`, `Economics`, `Finance`, `HR`, `Marketing` sont résolus vers les modules génériques métier correspondants.
- `Language B` et `Language C` sont résolus selon l’année de la feuille : JD L1, JD L2 ou JD L3.
- Une cellule vide signifie : aucun héritage de MLO.
- S6 peut rester vide si les modules ne sont pas encore stabilisés ou s’il n’existe pas de module générique correspondant.

## Héritage des MLO

Quand une ligne Excel contient :

```text
Economie générale 1 → Economics
```

le pipeline résout :

```text
Economics → UNITA_ECONOMICS
```

Puis il copie les MLO de `UNITA_ECONOMICS` dans le champ :

```json
"acquis_apprentissage": []
```

du module spécifique USMB.

Exemple attendu dans le curriculum processed :

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

Ce choix respecte le modèle existant : aucun champ supplémentaire n’a été ajouté au modèle curriculum.

## Visualisation

La visualisation utilise deux chemins de jointure :

### Chemin historique

```text
AC.modules → module curriculum
```

Ce chemin continue de fonctionner pour Polytech, BUT et les sources classiques.

### Chemin UNITA / Joint Degree

```text
module.acquis_apprentissage[MLO]
→ AC canonique PLOx__MLO
→ compétence/PLO
```

Ce chemin permet d’afficher les modules spécifiques USMB au lieu d’afficher uniquement les modules génériques UNITA.

## Catalogue générique et affichage

Dans les vues, le catalogue générique UNITA est traité comme une couche technique.

Règles d’affichage :

- si des modules spécifiques USMB portent déjà les MLO, on masque les modules génériques correspondants ;
- si un module générique n’a pas encore de module spécifique correspondant, il peut rester visible comme élément à mapper ;
- le faux semestre `S-1` / `COMMON=-1` ne doit pas être présenté comme un semestre réel.

## Fichiers modifiés

Fichiers concernés par l’intégration UNITA :

```text
app/etl/normalize/unita_curriculum_normalizer.py
app/etl/transform/curriculum/UNITA_curriculum_transformer.py
app/etl/load/curriculum_upsert_service.py
front/app/forested_visualisations.py
```

Fichiers à ne pas modifier pour cette logique :

```text
app/models/curriculum_models.py
app/models/competency_models.py
app/etl/extract/excel_extractor.py
app/etl/pipeline.py
front/app/api_client.py
```

## Points de contrôle

Après import UNITA, vérifier :

```text
1. Les modules USMB existent dans SCRL_processed.json.
2. Les modules USMB mappés ont des acquis_apprentissage non vides.
3. Les modules S6 laissés vides restent sans acquis_apprentissage.
4. Les vues affichent des modules USMB et pas seulement UNITA_BUSINESS / UNITA_ECONOMICS / etc.
5. Polytech et BUT continuent à s’afficher comme avant.
```

Commandes utiles :

```bash
python -m py_compile front/app/forested_visualisations.py
python -m pytest tests/ -q
```

Dans Docker :

```bash
docker compose exec frontend python -m py_compile /app/forested_visualisations.py
docker exec -it forested_backend python -m pytest tests/ -q
```

## Limites connues

- La vue globale UNITA peut être dense, car un même MLO peut être relié à plusieurs PLO et plusieurs modules spécifiques.
- Les filtres par semestre, UE ou compétence sont importants pour une lecture détaillée.
- `Finance` restera générique tant qu’aucun module spécifique n’est mappé vers `Finance` dans l’Excel.
- S6 reste volontairement incomplet si l’Excel n’est pas stabilisé.
