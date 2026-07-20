# 03 — Utilisation du dashboard

## Connexion

Ouvrir <http://127.0.0.1:8050> (en production : `https://app.<domaine>`) et se
connecter avec son **nom d'utilisateur OU son email** + mot de passe. La
session est portée par un cookie signé ; le bouton « Déconnexion » est dans la
barre de navigation. Un invité (lien `/access/<clé>`) accède directement aux
visualisations, en lecture seule, sans login.

## Pages principales

| Page | Contenu |
|---|---|
| **Vue d'ensemble** | Accueil / indicateurs généraux sur les formations accessibles. |
| **Cartographie APC** | Vue croisée compétences ↔ modules (heatmap/cartographie). |
| **Forêt pédagogique** | La page des deux forêts (voir ci-dessous), avec un bouton radio pour basculer entre forêt pédagogique et forêt curriculaire. |
| **Exploration circulaire** | Sunburst hiérarchique des données. |
| **Parcours** | Visualisation orientée parcours. |
| **Administration** | Visible uniquement pour le rôle admin — voir [04_ADMINISTRATION.md](04_ADMINISTRATION.md). |

*(Les intitulés correspondent à la barre de navigation actuelle du frontend.)*

## Filtres

- **Formation** (source — programme) : seules les formations autorisées par
  vos permissions apparaissent dans la liste.
- **Semestre** : filtre les éléments rattachés au semestre choisi.
- **Parcours** : tronc commun + parcours détectés (convention
  `COMP_n` / `COMP_<PARCOURS>_n` — ex. BUT : ATN… ; USMB Droit :
  PRIVE/PUBLIC ; USMB STAPS : EM/ERGO_PM/ES).
- **Compétence** : restreint l'affichage à une compétence.

## Les deux forêts

**Forêt pédagogique** — lecture bas → haut : `Compétence ◆ → Niveaux ■ →
Barres AC`. Chaque compétence a une couleur stable ; les niveaux N1/N2/N3 vont
du pâle au saturé ; les barres représentent les AC (hover = description +
modules référencés). Cliquer sur un élément ouvre un panneau de détail
(focus) ; « Réinitialiser » le referme.

**Forêt curriculaire** — lecture bas → haut : `Semestre ◆ → UE ◇ → Module ■ →
AC ●`. Les AC portent la MÊME couleur que leur compétence dans la forêt
pédagogique ; le niveau de l'AC est codé par l'épaisseur du contour du point
(fin = N1, épais = N3). Le clic zoome sur un sous-arbre ; le focus pédagogique
est conservé quand on bascule entre les deux forêts.

## Limites NORMALES du curriculum-lite USMB

Pour les formations `usmb_licence`, le curriculum est un **squelette**
reconstruit depuis le référentiel de compétences (les fichiers source ne
contiennent pas de maquette complète). Il est donc normal d'observer :

- **ECTS et volumes horaires à 0.0** (non renseignés dans la source) ;
- pas de coefficients ;
- pas d'enseignants ;
- des codes de modules générés (`S1_INTRO_DRT_PRIVE`…) pour les licences dont
  les fichiers n'ont pas de codes EC officiels ;
- ESET/TRI : très peu de liens AC↔EC (fidèle aux fichiers source) ;
- MATH : absent (fichier hors gabarit, exclu en v1/v2 avec erreur claire à
  l'upload).

Le détail de ce qui a été lu et de ce qui manque est consultable dans le
rapport qualité : `data/analytics/<domaine>/usmb_licence/<FORMATION>_ref_quality.json`.
Ces limites disparaîtront lorsque de vraies maquettes (ECTS/heures) seront
fournies et chargées pour ces formations.
