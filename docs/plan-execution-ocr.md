# Plan d'exécution : OCR, découpage et travail avec deux modèles

État : proposition, 7 novembre 2026. Aucun code écrit.
But : réaliser la fonctionnalité OCR de `docs/plan-ocr.md` avec Claude Sonnet et DeepSeek v4 pro, en limitant les tokens et les reprises.

---

## 1. Verdict sur l'envergure

Oui, l'envergure est certaine. Le volume de code reste raisonnable, mais la fonctionnalité touche plusieurs zones sensibles :

- le rendu PDF et la superposition d'une couche de texte ;
- l'état de synchronisation, `deja_present`, `pdf_range` et `index_existant` ;
- une file de travail avec reprise après fermeture ;
- une interface qui doit expliquer la valeur sans jargon ;
- le packaging Windows et macOS avec deux dépendances de plus ;
- les tests et la documentation.

Le coût principal ne vient pas du nombre de lignes. Il vient des allers-retours, des cas limites et du contexte relu à chaque session. Un découpage flou coûtera plus cher qu'un mauvais choix de modèle.

Ordre de grandeur : 20 tâches, 7 à 10 jours de travail concentré, ou 2 à 3 semaines à temps partiel.

---

## 2. Règles de collaboration entre les modèles

1. **Un seul propriétaire par tâche.** Un modèle écrit, l'autre relit. Jamais deux modèles qui modifient le même fichier dans la même tâche.
2. **Alternance aux frontières de tâches**, pas au milieu d'un fichier.
3. **Un contrat avant le code.** `docs/ocr-contrat.md` fixe les structures, les signatures, les invariants et les messages. Les deux modèles lisent ce contrat, pas tout le dépôt.
4. **Une tâche, une session.** Repartir d'un contexte neuf à chaque tâche, avec le contrat, les fichiers exacts et le test qui échoue.
5. **Les tests sont la spécification exécutable.** Écrire ou faire échouer le test avant l'implémentation. Le test est plus court qu'un long paragraphe.
6. **Revue ciblée.** Un second modèle ne relit que les diffs à risque, avec le contrat et les tests. Pas de relecture complète du dépôt.
7. **Handoff court.** Chaque tâche finit par 10 lignes : fait, fichiers, tests, décisions, doutes, suivant.
8. **Interfaces gelées tôt.** Noms de fonctions, clés JSON, identifiants DOM, classes CSS. Changer une interface en cours de route coûte très cher.
9. **Pas de parallélisme sur les mêmes fichiers.** Deux tâches qui touchent `moteur.py` ou `application.py` passent l'une après l'autre.
10. **Docs et tests en dernier, mais pas trop tard.** Ils stabilisent les interfaces et évitent de les redécouvrir.

---

## 3. Découpage recommandé

Légende : S = Claude Sonnet, D = DeepSeek v4 pro.

| ID | Tâche | Propriétaire | Dépend de | Livrable | Porte de sortie |
|---|---|---|---|---|---|
| E0 | Écrire `docs/ocr-contrat.md` | S | plan OCR | contrat de 3 pages | structures, signatures, invariants, messages |
| S1 | Spike `pypdfium2` et Tesseract TSV | D | E0 | `docs/spike-ocr.md` | une page en moins de 3 s, pas de console, TSV lisible |
| C1 | Détection Tesseract et configuration | D | E0, S1 | `moodlesync/ocr.py` partie détection | registre, chemins, langues, `--tessdata-dir`, erreurs lisibles |
| C2 | Texte natif, OCR, TSV, Markdown par document | S | E0, S1 | `ocr.py` partie extraction | page native sans OCR, page scannée avec confiance |
| C3 | Cache, empreinte, reprise, file | S | C2 | `ocr.py` partie état | reprise après arrêt au milieu d'un document |
| C4 | PDF cherchable, superposition, vérification | S | C2 | `ocr.py` partie PDF | page count, annotations, liens, remplacement atomique |
| C5 | Markdown de cours, index, qualité, JSONL | D | C2 | `ocr.py` partie sorties | fichiers lisibles et cohérents |
| Y1 | État de synchronisation et `deja_present` | S | C3, C4 | `moteur.py` adapté | PDF déplacé reconnu, aucun retéléchargement |
| Y2 | Republication, restauration, file après sync | S | Y1 | `moteur.py` et `ocr.py` | contenu identique conservé, contenu différent remplacé |
| Y3 | Tests d'intégration synchronisation et OCR | D | Y1, Y2 | `tests/test_ocr.py` | suite verte, cas de déplacement et de republication |
| A1 | Mixin `ApiTextes` | D | C3, C5 | `moodlesync/api_textes.py` | méthodes exposées, validation, verrous |
| A2 | Recherche, copie, export, ouverture | D | A1 | `api_textes.py` | résultats avec page, copie utilisable dans une IA |
| A3 | Revue API et messages d'erreur | S | A1, A2 | corrections ciblées | aucune trace technique dans la fenêtre |
| U1 | HTML et CSS de l'onglet Mes textes | D | E0 | `index.html`, `style.css` | onglet, état vide, badges, qualité |
| U2 | `textes.js` : liste, recherche, copie, export | D | A2, U1 | `textes.js` | parcours complet sans rechargement |
| U3 | Panneau « À quoi ça sert ? » et aperçu | S | C2, U1 | `textes.js`, HTML | une page réelle, aucun fichier écrit |
| U4 | Carte de préparation, consentement, reprise | S | Y2, U1 | `sync.js`, HTML | trois clics, durée annoncée, pause |
| U5 | Accessibilité, thème sombre, vérification | D | U1 à U4 | CSS, `app.js` | `etatVerification` couvre l'onglet |
| P1 | Dépendances, PyInstaller, builds | D | C1 à C5 | `requirements.txt`, `MoodleSync.spec` | exe Windows et app macOS démarrent |
| P2 | Tests et CI avec Tesseract facultatif | D | Y3, A1, U5 | `tests/`, CI | tests hors ligne verts, tests OCR ignorés sans moteur |
| P3 | Documentation et exception `remplacer` | D | toutes | README, LISEZ-MOI, notes, CONTEXTE, CONTRIBUTING, TIERS | promesse et limite explicites |
| P4 | Audit final | S | P1 à P3 | rapport court | critères 1 à 16 du plan vérifiés |

---

## 4. Détail des phases

### Phase 0 : contrat

C'est la tâche la plus rentable. Elle évite que chaque modèle redécouvre les mêmes décisions.

Le contrat doit contenir :

- les structures JSON de `.moodlesync.json`, du cache OCR et de la file ;
- les signatures publiques de `ocr.py`, `api_textes.py` et des méthodes de `Api` ;
- les invariants : aucun original conservé, superposition seulement en mode `remplacer`, aucun réseau pendant l'OCR, remplacement atomique, page count constant ;
- les messages d'erreur visibles ;
- les noms de fichiers de sortie et les marqueurs de page ;
- la liste des tests qui doivent exister ;
- les limites assumées : manuscrit, formules, colonnes, PDF protégés.

Le contrat ne doit pas dépasser 3 pages. S'il grandit, c'est le signe que le découpage est trop fin.

### Phase 1 : spike

Le spike répond à une seule question : est-ce que `pypdfium2`, Tesseract TSV et la superposition fonctionnent sur Windows et macOS avec les versions du projet ?

Le rapport doit donner :

- la version de `pypdfium2` et de Tesseract ;
- le temps de rendu et d'OCR sur trois pages réelles ;
- la qualité du TSV et la confiance ;
- la présence ou l'absence de console noire ;
- la faisabilité de la superposition avec `pypdf` ;
- une décision go ou no-go.

Pas d'interface, pas de cache, pas de file. Si le spike échoue, on révise le plan avant d'écrire `ocr.py`.

### Phase 2 : moteur

L'ordre C1, C2, C3, C4, C5 est important.

- C1 peut être fait en parallèle de C2 si le contrat fixe la fonction d'appel.
- C3 dépend de C2, parce que la reprise a besoin du format de page.
- C4 dépend de C2, parce que la superposition a besoin du TSV.
- C5 dépend de C2, mais peut être fait par un autre modèle sans toucher au cœur.

Le point le plus risqué est C4. Il faut le traiter tôt, pas à la fin. Un PDF cherchable qui perd un signet est un échec visible.

### Phase 3 : synchronisation

C'est la phase qui peut casser l'existant. Elle doit rester chez un seul propriétaire, Sonnet, avec des tests écrits par DeepSeek.

Ordre :

1. Y1 : état, `deja_present`, `index_existant`, `pdf_range`.
2. Y3 : tests de non-régression, avant Y2.
3. Y2 : republication, restauration, file après synchronisation.

Le test minimum de Y1 : synchroniser, remplacer, synchroniser, vérifier zéro téléchargement. Puis déplacer le PDF, synchroniser, vérifier qu'il est retrouvé.

### Phase 4 : API

Le mixin `ApiTextes` suit `api_horaire.py`. DeepSeek peut le faire vite si le contrat est précis.

Les méthodes longues ne bloquent pas la page. La progression remonte par `window.textesProgres`. Les erreurs sont des phrases lisibles.

### Phase 5 : interface

Séparer la coquille de l'explication.

- U1 et U2 : structure, liste, recherche, copie. DeepSeek.
- U3 et U4 : compréhension et consentement. Sonnet.
- U5 : accessibilité et vérification. DeepSeek, revue Sonnet.

Le panneau « À quoi ça sert ? » ne doit pas être noyé dans la liste. Il a son propre moment.

### Phase 6 : finition

P1 et P2 sont mécaniques mais bloquants. P3 doit inclure une modification de `CONTRIBUTING.md` : le projet dit aujourd'hui « ne jamais écraser un fichier de l'utilisateur ». Le mode `remplacer` est une exception explicite, avec consentement, sans copie locale et avec restauration par téléchargement.

P4 est un audit, pas une réécriture. Il vérifie les 16 critères d'acceptation du plan.

---

## 5. Packs de contexte

Ne jamais envoyer le dépôt entier. Chaque tâche reçoit un pack de 4 à 8 fichiers ou extraits.

### Pack contrat

- `docs/ocr-contrat.md`
- `docs/plan-ocr.md`, sections 4.3, 5.2 à 5.10 et 8
- la commande de test

### Pack moteur

- `moodlesync/ocr.py`
- `moodlesync/seances.py`, fonction `pdf_range`
- `moodlesync/moteur.py`, fonctions `empreinte`, `index_existant`, `deja_present`, `telecharger`, `cle_url`
- `tests/test_seances.py` pour le style
- `docs/spike-ocr.md`

### Pack synchronisation

- `moodlesync/moteur.py`, extraits des lignes 780 à 1100
- `docs/ocr-contrat.md`
- `tests/test_moteur.py`
- le test qui échoue

### Pack API

- `moodlesync/api_horaire.py`
- `moodlesync/application.py`, classe `Api` et `lancer`
- `docs/ocr-contrat.md`

### Pack interface

- `moodlesync/interface/index.html`
- `moodlesync/interface/style.css`, variables et composants
- `moodlesync/interface/commun.js`
- `moodlesync/interface/app.js`
- une capture d'écran, une seule

### Pack packaging

- `requirements.txt`
- `requirements-compilation.txt`
- `MoodleSync.spec`
- `.github/workflows/compilation.yml`

---

## 6. Prompts courts

### Implémentation

```text
Rôle : implémenter la tâche <ID>.
Contexte : lis docs/ocr-contrat.md, puis uniquement <fichiers>.
Contraintes : <invariants de la tâche>.
Livrable : <fichiers et comportement>.
Tests : <commande et test précis>.
Ne touche pas : <fichiers hors périmètre>.
Réponds avec : fichiers modifiés, tests lancés, doutes, prochaine étape.
```

### Revue

```text
Rôle : revue ciblée, pas de refonte.
Contexte : docs/ocr-contrat.md, le diff git, les tests.
Cherche : violation du contrat, cas limite, régression, message technique visible.
Ne commente pas le style général.
Réponds avec : bloquant, important, mineur, ou rien.
```

### Spike

```text
Objectif : réponse go ou no-go, pas de code de production.
Mesure : <temps, qualité, console, compatibilité>.
Livrable : docs/spike-ocr.md, une page.
Si échec : explique la cause et propose un plan B.
```

### Handoff

```text
Tâche :
Fait :
Fichiers :
Tests :
Décisions :
Doutes :
Suivant :
```

---

## 7. Budget de tokens

Ordre de grandeur, à ajuster après les deux premières tâches.

| Phase | Tâches | Budget indicatif |
|---|---|---|
| Contrat | 1 | 8 à 12 k |
| Spike | 1 | 10 à 15 k |
| Moteur | 5 | 80 à 120 k |
| Synchronisation | 3 | 60 à 90 k |
| API | 3 | 30 à 45 k |
| Interface | 5 | 60 à 90 k |
| Packaging et docs | 4 | 40 à 60 k |
| Revues ciblées | 6 à 8 | 40 à 60 k |
| Total | 20 | 330 à 490 k |

Sans contrat, sans packs de contexte et avec des sessions longues, le même travail peut facilement dépasser 1 million de tokens. La différence vient surtout des relectures et des reprises, pas du code produit.

---

## 8. Portes de sortie

Une tâche n'est finie que si :

1. le test décrit dans la tâche passe ;
2. la suite complète passe ;
3. le diff ne touche que les fichiers prévus ;
4. le handoff est écrit ;
5. une revue ciblée a eu lieu si la tâche touche `moteur.py`, `ocr.py`, `api_textes.py` ou le remplacement PDF.

Pour les tâches critiques, la revue est faite par l'autre modèle. Pour les tâches mécaniques, une relecture rapide suffit.

---

## 9. Ordre recommandé

```text
E0
S1
C1 et C2 en parallèle si le contrat est stable
C3
C4
C5
Y1
Y3
Y2
A1
A2
A3
U1
U2
U3
U4
U5
P1
P2
P3
P4
```

Les tâches Y1, Y2, C3 et C4 ne se parallélisent pas. Les tâches C1, C5, U1 et P3 peuvent être décalées ou menées par l'autre modèle pendant une revue.

---

## 10. Ce qu'il ne faut pas faire

- Demander à un modèle de lire tout `moteur.py` pour une modification de 20 lignes.
- Alterner les modèles au milieu d'un même fichier.
- Écrire l'interface avant d'avoir figé les méthodes de l'API.
- Faire le PDF cherchable à la fin, après l'interface.
- Considérer les tests comme une tâche séparée après tout le reste.
- Laisser un modèle écrire les tests de son propre code critique sans revue.
- Empiler les captures d'écran et les longues sorties de test dans le contexte.
- Changer une clé JSON ou un nom de fonction sans mettre à jour le contrat.
