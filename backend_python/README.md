# ForestED Backend

Platform de gestion de données pédagogiques pour l'éducation en foresterie.

## 🎯 Description

ForestED est un système ETL (Extract-Transform-Load) pour transformer et valider les données pédagogiques:
- **Compétences** : Référentiels de compétences par domaine
- **Curricula** : Programmes d'études avec périodes, UE et éléments pédagogiques

## 📦 Structure

```
backend_python/
├── app/
│   ├── models/              # Modèles Pydantic (validation)
│   │   ├── competency_models.py
│   │   └── curriculum_models.py
│   ├── etl/                 # Pipeline ETL
│   │   ├── extract/         # Extraction JSON
│   │   ├── transform/       # Transformations spécifiques au domaine
│   │   │   ├── competence/
│   │   │   └── curriculum/
│   │   └── load/            # Sauvegarde JSON
│   └── data/
│       ├── raw/             # Données brutes
│       ├── processed/       # Données transformées (canoniques)
│       └── analytics/       # Données aplaties (analytics)
├── requirements.txt
└── Dockerfile
```

## 🚀 Installation

### 1. Cloner le projet
```bash
cd backend_python
```

### 2. Créer un environnement virtuel
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate     # Windows
```

### 3. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 4. Créer le fichier .env
```bash
cp .env.example .env
```

## 🔧 Configuration

Voir `.env.example` pour les variables d'environnement disponibles.

## 🏃 Utilisation

### Lancer le pipeline ETL
```python
from app.etl.pipeline import run_pipeline

run_pipeline()
```

### Traiter un domaine spécifique
```python
from app.etl.pipeline import run_domain_pipeline

run_domain_pipeline("competence")
run_domain_pipeline("curriculum")
```

## 📝 Format des données

### Données d'entrée (JSON)
Placer les fichiers JSON dans `app/data/raw/{domain}/`

#### Competence
```json
{
  "id": "IDU",
  "data": [...]
}
```

#### Curriculum
```json
{
  "fiches": [
    {
      "code": "IDU201",
      "nom": "Data Science",
      "semestre": "S1",
      "CM": "12h",
      "TD": "8h",
      ...
    }
  ]
}
```

## 🧪 Tests

```bash
pytest
```

Avec couverture:
```bash
pytest --cov=app
```

## 🛠️ Développement

### Format du code
```bash
black app/
isort app/
```

### Linting
```bash
flake8 app/
```

## 🐳 Docker

### Build
```bash
docker build -t forested-backend .
```

### Run
```bash
docker run -v $(pwd):/app forested-backend python -m app.etl.pipeline
```

## 📚 Documentation des modèles

### Competency Models
- `ReferentielCompetences` : Référentiel global
- `Competence` : Compétence individuelle
- `NiveauDeveloppement` : Niveau de développement
- `ApprentissageCritique` : Apprentissage critique

### Curriculum Models
- `Programme` : Programme d'études
- `PeriodeProgramme` : Période (semestre)
- `UniteEnseignement` : Unité d'enseignement (UE)
- `ElementPedagogique` : Élément pédagogique (cours)
- `Enseignant` : Informations enseignant

## 🔐 Validation

Toutes les données sont validées avec Pydantic:
- Types strictes
- Valeurs requises/optionnelles
- Validateurs personnalisés (ex: heures positives)
- Mode stricte (forbid extra fields)

## ⚠️ Erreurs courantes

### FileNotFoundError
Vérifier que les fichiers JSON existent dans `app/data/raw/{domain}/`

### JSONDecodeError
Vérifier le format JSON du fichier d'entrée

### ValueError (Transformer)
Vérifier que le domaine et source_name correspondent au TransformerFactory

## 🤝 Contribution

TODO: Ajouter guidelines

## 📄 License

TODO: Définir la license
