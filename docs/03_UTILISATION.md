# 03 — Utilisation du dashboard

## Connexion

Ouvrir <http://127.0.0.1:8050> en local, ou `https://app.<domaine>` en production.

Connexion possible avec :

```text
nom d'utilisateur OU email + mot de passe
```

La session est portée par un cookie signé. Un invité qui ouvre un lien `/access/<clé>` accède directement aux visualisations autorisées, en lecture seule.

## Pages principales

| Page | Contenu |
|---|---|
| **Vue d'ensemble** | Indicateurs globaux sur les formations accessibles. |
| **Cartographie APC** | Vue croisée compétences ↔ modules, avec graphe ou heatmap. |
| **Forêt pédagogique** | Lecture compétence-first : compétences → niveaux → AC. Inclut aussi la forêt curriculaire. |
| **Exploration circulaire** | Sunburst : lecture circulaire des relations compétences / AC / modules ou semestres / modules. |
| **Parcours** | Visualisation orientée parcours quand la source porte cette information. |
| **Administration** | Visible uniquement pour les admins. |

## Filtres communs

| Filtre | Rôle |
|---|---|
| **Formation** | Source + formation, par exemple `Polytech — IDU`, `unita — SCRL`. |
| **Semestre** | Restreint l'affichage à un semestre. Très utile pour les graphes denses. |
| **Spécialité / parcours** | Filtre par parcours quand les compétences suivent la convention de code attendue. |
| **Compétence** | Restreint l'affichage à une compétence/PLO. Recommandé pour analyser UNITA. |

## Forêt pédagogique

Lecture bas → haut :

```text
Compétence ◆ → Niveau ■ → AC / barres → Modules
```

Cette vue répond à la question :

```text
Quels modules contribuent aux AC d'une compétence ?
```

Le compteur affiché sur une barre AC indique le nombre de modules liés à cet AC.

## Forêt curriculaire

Lecture bas → haut :

```text
Semestre ◆ → UE/Groupe ◇ → Module ■ → AC ●
```

Cette vue répond à la question :

```text
Dans un semestre ou une UE, quels modules travaillent quels AC ?
```

Cliquer sur un semestre, une UE ou un module réduit le graphe au sous-arbre sélectionné.

## Exploration circulaire / Sunburst

Deux lectures principales :

| Mode | Lecture |
|---|---|
| **APC par compétence** | Compétence → niveau → AC → modules. |
| **Distribution semestrielle** | Formation → semestre → modules → AC. |

La distribution semestrielle est utile pour vérifier que les modules sont placés dans les bons semestres.

## Lecture de la source UNITA / SCRL

La source `unita — SCRL` est un cas de Joint Degree. Elle combine :

```text
catalogue générique UNITA : PLO, MLO, modules génériques
maquette USMB : semestres, UE/groupes, modules réels
```

Dans les vues, il faut interpréter les modules comme suit :

| Élément affiché | Interprétation |
|---|---|
| `USMB_Sx_Ex` | Module réel extrait de la maquette USMB. |
| `UNITA_BUSINESS`, `UNITA_ECONOMICS`, etc. | Module générique de référence. Il ne doit rester visible que s'il n'a pas encore de module spécifique correspondant. |
| `Language B`, `Language C` | Valeur de correspondance générique utilisée pour résoudre les MLO de langue selon JD L1/L2/L3. Ce n'est pas une UE réelle. |
| `S-1` ou `COMMON=-1` | Ne doit pas être présenté comme un semestre réel. C'est une couche générique technique. |

### Règle de lecture validée pour UNITA

```text
PLO → AC canonique → MLO → module spécifique USMB
```

Un module USMB est relié aux compétences parce qu'il contient des MLO hérités dans `acquis_apprentissage`.

### Bonnes pratiques de lecture UNITA

- Utiliser le filtre **Compétence** pour analyser un PLO précis.
- Utiliser le filtre **Semestre** pour analyser la maquette USMB progressivement.
- En vue globale, le graphe peut être dense : ce n'est pas forcément une erreur de données.
- Un module générique peut rester visible quand aucun module spécifique n'est encore mappé vers lui, par exemple `Finance` si l'Excel n'a aucune correspondance `Finance`.

## Limites normales du curriculum-lite USMB

Pour `usmb_licence`, le curriculum est reconstruit depuis un référentiel APC et non depuis une maquette complète. Il est donc normal de voir :

- ECTS et volumes horaires à `0.0` ;
- pas de coefficients ;
- pas d'enseignants ;
- certains codes de modules générés ;
- des rapports qualité signalant les informations manquantes.

Ne pas présenter ce curriculum-lite comme une maquette administrative complète.
