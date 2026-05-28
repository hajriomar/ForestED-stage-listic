# ForestED 

## Présentation du projet

ForestED est un projet de transformation et de structuration de données pédagogiques académiques.

L’objectif principal est de construire un pipeline ETL capable de :

* extraire des données pédagogiques provenant de différentes sources,
* transformer ces données vers des méta-modèles canoniques communs,
* générer des formats exploitables pour l’analyse, la visualisation et les outils BI.

Le projet a été conçu autour d’une architecture générique et extensible afin de supporter plusieurs établissements ou référentiels pédagogiques.

---

# Objectifs du projet

Le pipeline ETL permet de :

* centraliser plusieurs sources de données académiques,
* normaliser les structures hétérogènes,
* respecter un méta-modèle métier commun,
* produire une représentation canonique unifiée,
* générer des données analytiques simplifiées,
* préparer les données pour des usages IA, RAG, analytics ou visualisation.

---

# Architecture générale

Le pipeline suit une architecture ETL classique :

1. Extraction des données JSON brutes
2. Sélection automatique du transformer
3. Transformation métier vers le méta-modèle
4. Génération des outputs canonical et flat
5. Sauvegarde des résultats

L’architecture repose sur un système de transformers spécialisés sélectionnés automatiquement grâce au Factory Pattern.

---

# Structure du projet

```text
app/
│
├── data/
│   ├── raw/
│   │   ├── competence/
│   │   │   └── Polytech/
│   │   └── curriculum/
│   │       └── Polytech/
│   │
│   ├── processed/
│   │
│   └── analytics/
│
├── etl/
│   ├── extract/
│   ├── transform/
│   ├── load/
│   └── pipeline.py
│
├── models/
│   ├── competency_models.py
│   └── curriculum_models.py
```

---

# Organisation des données

Les données brutes sont organisées selon :

* le domaine :

  * competence
  * curriculum

* la source :

  * Polytech
  * futures sources (BUT, autres écoles, etc.)

Cette organisation permet au pipeline de détecter automatiquement la provenance des données et de sélectionner le transformer adapté.

---

# Meta-models

Le projet repose sur deux méta-modèles principaux :

## 1. Meta-model compétences

Structure hiérarchique :

```text
ReferentielCompetences
    └── SousClassification
            └── Competence
                    └── NiveauDeveloppement
                            └── ApprentissageCritique
```

Ce modèle permet de représenter :

* les compétences,
* les niveaux de développement,
* les apprentissages critiques,
* les modules associés.

---

## 2. Meta-model curriculum

Structure hiérarchique :

```text
Programme
    └── PeriodeProgramme
            └── UniteEnseignement
                    └── ElementPedagogique
```

Le modèle curriculum contient également :

* les acquis d’apprentissage,
* les ressources pédagogiques,
* les activités pédagogiques,
* les évaluations,
* les enseignants.

---

# Factory Pattern

Le projet utilise un Factory Pattern afin de sélectionner automatiquement le transformer adapté selon :

* le domaine,
* la source des données.

Exemple :

```python
TransformerFactory.get_transformer(
    domain="competence",
    source_name="Polytech"
)
```

Cette architecture permet d’ajouter facilement :

* de nouveaux transformers,
* de nouvelles sources,
* de nouveaux référentiels.

---

# Outputs générés

Chaque transformer produit deux formats :

## 1. Canonical JSON

Structure complète respectant le méta-modèle métier.

Utilisée pour :

* la normalisation,
* l’interopérabilité,
* les traitements IA,
* les graphes de connaissances.

---

## 2. Flat JSON

Structure simplifiée destinée à :

* l’analyse,
* les dashboards,
* la BI,
* les exports tabulaires.

---

# Fonctionnalités principales

Le pipeline implémente plusieurs règles métier :

* extraction automatique des modules depuis le texte,
* normalisation des codes modules,
* détection automatique des semestres,
* gestion des modules transverses,
* déduplication des enseignants,
* calcul automatique des volumes horaires,
* validation des données via Pydantic.

---

# Technologies utilisées

* Python
* Pydantic
* JSON
* Logging
* Regex
* Architecture ETL
* Factory Pattern

---

# Validation des données

Les modèles Pydantic sont utilisés afin de :

* valider les structures,
* garantir la conformité au méta-modèle,
* empêcher les champs invalides,
* sécuriser les transformations.

---

# Logging

Le pipeline utilise un système de logging centralisé permettant de suivre :

* l’extraction,
* les transformations,
* les erreurs,
* les fichiers générés,
* les problèmes de données.

---

# Extensibilité

L’architecture a été conçue pour supporter facilement :

* de nouvelles sources académiques,
* de nouveaux formats de données,
* de nouveaux transformers,
* de nouveaux méta-modèles.

Pour ajouter une nouvelle source :

1. Créer un dossier dans `data/raw`
2. Créer le transformer correspondant
3. L’ajouter dans `TransformerFactory`

Aucune modification du pipeline principal n’est nécessaire.

---

# Exécution du pipeline

Lancer le pipeline :

```bash
python -m app.etl.pipeline
```

---

# Résultats générés

Les outputs sont automatiquement sauvegardés dans :

```text
app/data/processed/
```

et :

```text
app/data/analytics/
```

---
