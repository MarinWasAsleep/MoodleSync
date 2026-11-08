# Prompt 32 pour DeepSeek v4.1 flash : rendre la suite verte apres A1

Auteur : Hermes, orchestrateur, 8 novembre 2026. Destinataire : DeepSeek v4.1 flash. Une seule tache, courte.

## Le probleme, mesure

La suite complete est rouge apres le commit `781da59` : 556 tests, **1 echec**, 1 ignore. L'echec est `tests.test_api_textes.ErreursT26.test_erreurs_prevues_sont_des_phrases`, ligne 339 :

```
AssertionError: 'erreur' not found in {'annule': True}
```

Il echoue aussi quand on lance ce seul test, donc ce n'est pas une pollution entre tests.

## Diagnostic, a verifier puis a appliquer

`ocr_choisir_exe` a trois comportements legitimes : `{"erreur": ...}` si la fenetre n'est pas ouverte, `{"annule": True}` si l'utilisateur annule la boite de dialogue, et l'etat complet apres un choix. L'assertion de la ligne 339 suppose que le deuxieme cas renvoie une erreur, ce qui est faux.

Les trois comportements sont deja couverts ailleurs dans le fichier : `a._fenetre = None` vers la ligne 391 et `test_jamais_sans_fenetre` ligne 445 pour l'absence de fenetre, `FauxFenetre(choix=None)` ligne 400 pour l'annulation. L'assertion de la ligne 339 est donc a la fois fausse et redondante.

Applique la correction minimale : retire cette assertion, et si tu juges qu'un cas manque vraiment, remplace-la par une assertion qui teste un comportement non deja couvert, en le disant dans l'entree de journal. Ne modifie aucun comportement de `api_textes.py`.

## Second point : le 28e test

Le fichier `tests/test_api_textes.py` contient `test_apres_sync_desactive_ne_demarre_pas`, que l'entree `fin` de A1 dit ne pas avoir ecrit. `git log -S` montre qu'il est pourtant introduit par `781da59` lui-meme : il vient donc de la session A1, simplement perdu de vue. Ecris-le noir sur blanc dans une entree `ecart` ou `fin`, avec cette mesure, pour que la revue n'ait pas a le rechercher.

## Contraintes

- Suite verte exigee : 556 tests, 0 echec, 1 ignore, ou plus si tu ajoutes des assertions.
- Tu ne modifies que `tests/test_api_textes.py` et `docs/ocr-avancement.md` et ce prompt. Pas `api_textes.py`, pas `application.py`.
- Francais, aucun tiret cadratin ni demi-cadratin. LF. Pas de `git add -A`, pas de push.
- Commit unique, auteur `MarinWasAsleep`, `git show --stat` verifie.

## Livrable

`Fait / Fichiers / Tests / Doutes`, le hash du commit, et la sortie reelle de la suite complete.
