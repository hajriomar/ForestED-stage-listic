# 06 — Guide développeur ETL : ajouter une source

**Sommaire** : [Architecture](#architecture-etl) · [Registry](#registry-déclarative) ·
[Ajouter une source](#ajouter-une-nouvelle-source-pas-à-pas) · [Modèles](#les-modèles-canoniques) ·
[Cas USMB](#le-cas-usmb-référence-dimplémentation) · [Règles d'or](#règles-dor)

## Architecture ETL

```
raw/<domaine>/<source>/FICHIER
   │  Extractor   : lit le FORMAT technique (json/xlsx/csv) -> enveloppe brute
   ▼
   │  Normalizer  : connaît la STRUCTURE de la source -> records homogènes
   ▼
   │  Transformer : connaît le MÉTA-MODÈLE -> {"canonical", "flat"[, "quality_report"]}
   ▼
   │  Loader      : sérialise -> processed/ + analytics/ (+ *_quality.json)
```

| Étape | Sait quoi | Ne sait pas |
|---|---|---|
| **Extractor** (`app/etl/extract/`) | lire un type de fichier (ex. `extract_excel` : feuilles + `visible` + `filled_cells`) | le métier |
| **Normalizer** (`app/etl/normalize/`) | la structure de LA source (positions, marqueurs, croix, variantes) | le méta-modèle |
| **Transformer** (`app/etl/transform/`) | construire le méta-modèle et les tables plates | Excel/JSON — il ne voit que des records |

Le pipeline (`app/etl/pipeline.py`) est générique : `process_file(domaine,
source, fichier)` enchaîne les factories, ne connaît aucune source, et
sauvegarde le `quality_report` si le transformer en fournit un.

## Registry déclarative

`app/etl/transform/transformer_factory.py` et
`app/etl/normalize/normalizer_factory.py` contiennent des dicts :

```python
TRANSFORMERS = {
    ("competence", "usmb_licence"): (
        "app.etl.transform.competence.USMB_licence_competence_transformer",
        "USMBLicenceCompetenceTransformer",
    ),
    ...
}
```

**Ajouter une source = ajouter une entrée.** Imports paresseux (un transformer
cassé ne bloque pas les autres) ; `domain`/`source` normalisés (strip+lower) ;
source inconnue → `ValueError` explicite listant les couples supportés (remonté
en 422 à l'admin). Côté normalizers, une source sans entrée reçoit un
`PassthroughNormalizer` (jamais d'erreur).

## Ajouter une nouvelle source, pas à pas

1. **Analyser la donnée AVANT de coder** : inspecter programmatiquement les
   fichiers réels (feuilles, colonnes, marqueurs, pièges — feuilles cachées,
   couleurs porteuses de sens, lignes fantômes…). Décider quel(s) domaine(s)
   la source peut alimenter. Ne rien promettre que la donnée ne contient pas.
2. **Extractor** : réutiliser l'existant (json/xlsx/csv) dans la grande
   majorité des cas. N'en créer un que pour un nouveau format technique.
3. **Normalizer** (`app/etl/normalize/<source>_..._normalizer.py`) : toute
   l'intelligence « format source » vit ici. Sortie = records homogènes
   documentés (+ `quality_report` recommandé). Préférer la détection par
   MARQUEURS aux positions fixes.
4. **Transformer(s)** (`app/etl/transform/competence/` et/ou `curriculum/`)
   selon ce que la source contient réellement : entrée = records du
   normalizer, sortie = `{"canonical", "flat", "quality_report"}`. S'inspirer
   de `BUT_competence_transformer.py` (le modèle de référence).
5. **Registry** : une entrée par (domaine, source) dans chaque factory.
6. **Tests** : unitaires normalizer (mini-fichiers générés), unitaires
   transformer, test pipeline (upload → 200 + fichiers générés), et **mise à
   jour de `tests/test_factories_registry.py`** (liste `known_sources`).
7. **Contrat R4** : les sorties doivent passer
   `validate_competence_canonical` / `validate_curriculum_canonical` et
   `validate_flat_rows` (`app/etl/transform/flat_contract.py`). Respecter la
   convention `COMP_n` / `COMP_<PARCOURS>_n` (le filtre parcours du frontend
   en dépend).

## Les modèles canoniques

- `app/models/competency_models.py` — Référentiel → SousClassification →
  Compétence (→ ComposantesEssentielles) → NiveauxDeveloppement →
  ApprentissagesCritiques. `ac.modules` = **liste de codes** (références vers
  des modules), jamais des objets. Pydantic strict (`extra="forbid"`) : tout
  champ inventé fait échouer la validation.
- `app/models/curriculum_models.py` — Programme → PériodesProgramme →
  Groupes (Élémentaire/Composite, `contrainte` = parcours) → Éléments
  pédagogiques (Formatif/Professionnel/Externe : ECTS, cm/td/tp/projet…).
  Validators : valeurs négatives refusées (0.0 accepté = « non renseigné »).

## Le cas USMB (référence d'implémentation)

- **Un seul normalizer pour les deux domaines**
  (`usmb_licence_competence_normalizer.py`, enregistré pour competence ET
  curriculum) : il extrait tout — compétences, niveaux, AC, et pour chaque
  lien AC↔EC : semestre, UA, EC, parcours, et le **`module_code` définitif**
  (code réel si présent, sinon code stable généré `S<sem>_<SLUG>`).
- **Deux transformers séparés** : competence (référentiel complet) et
  curriculum (« lite » : Semestre → UA → EC à 0.0, `quality_report` avec
  `curriculum_type: "lite"`).
- **`module_code` = clé de jointure** entre les deux domaines : les
  références `ac.modules` (competence) correspondent exactement aux ids des
  éléments du curriculum — calculée UNE fois, dans le normalizer.
- Particularités gérées : liens par croix (`x/X/×/✓`) ET par **couleur de
  cellule** (STAPS, via `filled_cells` de l'extractor), feuilles cachées
  ignorées, parcours par bandes de période (Droit) et par nom de feuille
  (STAPS `* L3`), bornage des lignes fantômes, MATH hors gabarit → erreur
  claire.
- La séparation des domaines est verrouillée par des tests dédiés
  (`tests/test_usmb_domain_separation.py` — à vérifier qu'il est bien présent
  dans `tests/`).

## Règles d'or

1. **Jamais d'UE/ECTS/heures dans le domaine competence** — les modules réels
   appartiennent au curriculum ; les AC ne portent que des références.
2. **Ne jamais inventer une donnée absente** (pas d'ECTS fictifs, pas de
   niveaux déduits sans le signaler).
3. **Signaler les manques** dans le `quality_report` (warnings explicites,
   jamais silencieux) — signaler sans bloquer, sauf si rien n'est exploitable.
4. **Valider sur les vraies données** avant livraison, pas seulement sur des
   fixtures (2 corrections du normalizer USMB viennent de là).
5. Ne PAS copier un transformer existant tel quel pour une nouvelle source :
   créer le couple normalizer/transformer dédié, sur le modèle du couple BUT
   compétence.
