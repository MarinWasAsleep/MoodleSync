# Prompt 21 pour DeepSeek v4.1 flash : corrections de C5 et de Y1a

Auteur : Hermes, orchestrateur, sur decision de Maxence, 8 novembre 2026. Destinataire : DeepSeek v4.1 flash, session neuve. Une seule tache, plusieurs corrections bornees.

## Role

Tu es D. Tu appliques les corrections issues des revues de C5 (ecarts 74, 76 a 84) et de Y1a (ecarts 85 et 87). Tu ne rouvres aucune tache : C5 et Y1a sont `fait`, tu corriges ce qui a ete releve, avec un test par correction quand le comportement change.

## A lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : les deux entrees `revue` de C5 et de Y1a (section 5), puis les ecarts 74 et 76 a 87 (section 6).
2. `docs/ocr-contrat.md` : 2.6 (nom du fichier de cours), 2.7, 3.1 (fonctions de C5), 4 (invariants 9 et 11).
3. `moodlesync/ocr.py` : les fonctions de C5 en fin de fichier (`_pages_md`, `ecrire_cours_md`, `ecrire_index`, `ecrire_qualite`, `ecrire_jsonl`, `assembler_contexte`, `_portee`, `_dans_la_portee`, `_sans_trace`) et `_marque_valide` dans `moodlesync/marque.py`.

## Decisions de Maxence, a appliquer telles quelles

1. **Ecart 76 : le nom retenu est `texte des documents`.** Le code garde le sien. Tu corriges le contrat 2.6 et 3.1 pour qu'ils disent `texte des documents`, et tu ajoutes une ligne au journal des decisions. Les trois tests existants qui figent ce nom restent inchanges.
2. **Ecart 77 :** une page vide en fin de document ne doit plus etre retiree. Le marqueur terminal n'existe pas dans ce que C2 ecrit ; `_pages_md` doit garder toutes les pages, y compris une derniere page vide.
3. **Ecart 78 :** la confiance par page affichee doit venir de la section « Pages a verifier » de C2 quand elle existe, page par page, au lieu d'une confiance unique repetee. Un document mixte doit enumerer ses pages.
4. **Ecart 79 :** avec `ocr_sortie_hors_coffre`, `index.md`, le fichier de qualite et le fichier de cours sont ecrits hors du coffre, comme les `.md` de document, et les orphelins sont listes dans ce mode.
5. **Ecart 80 :** dans le JSONL, `source` et `confiance` decrivent la page, pas le document.
6. **Ecart 74 :** la portee `cours:<cid>` se resout par la table `cfg["cours"][cid]["dossier"]`, comme `constituer_file`. C'est la lecture du contrat 2.7, donc aucune decision de Maxence n'est necessaire : applique-la et ecris-le au journal.
7. **Ecarts 81 et 82 :** le code mort (`_normaliser_md` et les expressions `RE_*` non appelees) est supprime ; la fixture `jeux()` produit les `.md` que C2 produit reellement.
8. **Ecart 83 :** les valeurs de retour des cinq fonctions publiques disent ce qui a ete ecrit, y compris quand une ecriture echoue et que l'invariant 9 renvoie une valeur vide.
9. **Ecart 84 :** l'ordre des entrees du journal est corrige par une entree nouvelle qui renvoie a l'ancienne. Aucune entree existante n'est supprimee ni modifiee.
10. **Ecart 85 :** le reexport de `lire_marque` par `ocr.py` est explique par un commentaire d'une ligne, sans `__all__`.
11. **Ecart 87 :** trois tests ajoutes pour les regles non couvertes de `_marque_valide` (borne de 1 Ko, `pages` au moins 1, booleen refuse comme entier), mesures par mutation.
12. **Ecart 86 : laisse-le ouvert.** Il se fermera avec Y1b, quand `moteur.py` importera `marque`.

## Contraintes

- Un test par correction de comportement, ecrit pour echouer d'abord quand c'est possible.
- La suite doit rester verte : 402 tests, 3 ignores, plus ceux que tu ajoutes.
- Tu ne modifies que `moodlesync/ocr.py`, `moodlesync/marque.py`, `tests/test_ocr.py`, `tests/test_marque.py`, `docs/ocr-contrat.md`, `docs/ocr-avancement.md` et ce prompt. Rien d'autre, et surtout pas `moteur.py` : Y1b s'en occupe.
- Francais, aucun tiret cadratin ni demi-cadratin. LF. Pas de `git add -A`, pas de push.
- Commit unique par groupe logique si tu en fais plusieurs, auteur `MarinWasAsleep`, et verifie `git show --stat`.
- Si une correction revele un probleme plus profond, tu t'arretes, tu l'ecris au journal comme ecart, et tu le dis dans ton rapport au lieu de l'improviser.

## Livrable

`Fait / Fichiers / Tests / Decisions / Doutes / Suivant`, le ou les hash de commit, et la liste des ecarts fermes avec leur numero.
