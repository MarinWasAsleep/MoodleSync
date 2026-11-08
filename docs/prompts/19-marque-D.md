# Prompt 19 pour DeepSeek v4.1 flash : ecart 6, module feuille des marques

Auteur : Hermes, orchestrateur, sur decision de Maxence, 8 novembre 2026. Destinataire : DeepSeek v4.1 flash, session neuve. Une seule tache.

## Role

Tu es D. Tu leves l'obstacle structurel de l'ecart 6 : `moteur.py` devra appeler la lecture de la marque d'un PDF, or `ocr.py` importe deja `moteur`. Tu n'ajoutes aucun comportement. Tu deplaces du code dans un module feuille, et tu prouves que le cycle a disparu.

## A lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : protocole (section 1), ecart 6 (section 6).
2. `docs/ocr-contrat.md` : 2.2 (la marque), 3.1 (la fonction `lire_marque`), 3.3 (`deja_present`, etape 4, pour comprendre pourquoi ce module existe).
3. `moodlesync/ocr.py`, seulement les lignes 1420 a 1500 : `CLE_MARQUE`, `_entier_vrai`, `_marque_valide`, `_marque_du_lecteur`, `lire_marque`. Et les endroits qui les utilisent : lignes 1580, 1725, 1830 a 1833, 1922.

## Decision de Maxence, a appliquer telle quelle

Creation de `moodlesync/marque.py`, module feuille sans dependance interne, qui recoit `CLE_MARQUE`, `_entier_vrai`, `_marque_valide`, `_marque_du_lecteur` et `lire_marque`, avec leurs docstrings actuelles. `ocr.py` les importe depuis ce module et reexporte `lire_marque` : `ocr.lire_marque` doit continuer a fonctionner sans qu'aucun appelant ni test ne change. `moteur.py` n'appelle rien de nouveau dans cette tache : l'appel reel arrive avec Y1b. Tu peux y ajouter l'import du module si cet import ne produit aucun avertissement, sinon tu ne l'ajoutes pas.

Preuve attendue que le cycle a disparu : un test qui importe, dans un sous-processus, `moodlesync.moteur` puis `moodlesync.marque`, et l'ordre inverse, et qui verifie qu'aucun import n'echoue. C'est un test de structure, pas de comportement.

## Second point : decoupage de Y1

Maxence a decide de decouper Y1 en trois : Y1a (l'ecart 6, cette tache), Y1b (etat de synchronisation et `deja_present`), Y1c (`index_existant` et `pdf_range`). Applique-le dans les documents :

- une ligne au journal des decisions (section 4) ;
- dans le tableau (section 2), la ligne Y1 devient `decoupee en Y1a, Y1b et Y1c` et tu ajoutes trois lignes, avec les proprietaires S pour Y1b et Y1c, D pour Y1a, et les dependances : Y1a aucun, Y1b C3, C4 et Y1a, Y1c C3, C4 et Y1a.

## Contraintes

- Aucun changement de comportement : les 399 tests passent a l'identique, plus le test de structure.
- Tu ne modifies que `moodlesync/marque.py` (nouveau), `moodlesync/ocr.py`, `moodlesync/moteur.py`, `tests/test_ocr.py` ou un nouveau fichier de test, `docs/ocr-avancement.md` et ce prompt. `docs/ocr-contrat.md` seulement si une formulation cite l'emplacement des fonctions.
- Francais, aucun tiret cadratin ni demi-cadratin. LF. Pas de `git add -A`, pas de push.
- Commit unique, auteur `MarinWasAsleep`. Verifie `git show --stat`.

## Livrable

`Fait / Fichiers / Tests / Decisions / Doutes / Suivant`, le hash du commit, et la confirmation que `ocr.lire_marque` se comporte comme avant.
