# Prompt 16 pour DeepSeek v4.1 flash : corrections de C4 et mesure D9 reelle

Auteur : Hermes, orchestrateur, sur decision de Maxence, 8 novembre 2026. Destinataire : DeepSeek v4.1 flash, dans une session neuve. Une seule tache.

## Role

Tu es D. Tu corriges quatre ecarts ouverts sur C4 dans `moodlesync/ocr.py` et `tests/test_ocr.py`, et tu executes une fois la verification du rendu (D9) avec un vrai pdfium. C4 est `fait` et relue : tu ne la reecris pas, tu appliques des corrections bornees.

## A lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : protocole (section 1), ligne C4 du tableau (section 2), et les ecarts 60, 61, 67, 68, 69 (section 6).
2. `docs/ocr-contrat.md` : 3.1 pour `extraire_document`, `fabriquer_pdf_cherchable`, `_verifier` ; invariant 4 pour D9 ; invariant 5 pour l'ordre d'ecriture.
3. `docs/prompts/14-C4-D.md` : la revue qui a mesure les mutations non detectees (ecarts 67 et 68).
4. `moodlesync/ocr.py`, uniquement les fonctions citees : `_supprimer_reprise` (ligne 1015 environ), `extraire_document`, `_verifier`, `fabriquer_pdf_cherchable`, `rendre_page`.

## Decisions de Maxence, a appliquer telles quelles

1. **Ecart 60.** La reprise, donc les boites, ne doit plus etre supprimee avant `fabriquer_pdf_cherchable`. Corrige l'ordre : la fabrication se fait avec les boites disponibles, et la suppression de la reprise n'a lieu qu'apres un remplacement reussi, dans le meme ordre que l'invariant 5. Si l'appelant demande `refaire`, la suppression suit la meme regle.
2. **Ecart 69.** La comparaison du rendu de D9 doit porter sur les images brutes, sans autocontraste. L'autocontraste ne sert plus qu'a expliquer un echec dans le message, jamais a decider de l'egalite.
3. **Ecarts 67 et 68.** Ajoute les deux tests manquants : retirer le controle des liens doit faire echouer un test, et vider le flux `q` d'ouverture ou retirer l'enveloppe `Q q ... Q` de la couche doit faire echouer un test. Ces tests doivent echouer sur le code actuel, puis passer apres ta correction si une correction est necessaire.
4. **Ecart 61.** Execute la verification du rendu avec un vrai pdfium, une fois, et colle les mesures reelles au journal. `pypdfium2` peut etre installe dans un environnement Python local pour cette mesure : c'est autorise par Maxence. Ne l'ajoute pas a `requirements-testes.txt`, ne modifie pas les dependances du produit. Trois PDF suffisent, fabriques avec l'aide `pdf_minimal` de `tests/test_ocr.py`. Mesure au moins : le rendu a 150 DPI de la premiere, de la page du milieu et de la derniere page, avant et apres l'ajout de la couche, et l'ecart maximal par pixel. Si une partie n'est pas mesurable, ecris « non mesure » et dis pourquoi.

## Contraintes

- Tests d'abord, puis le code. La suite doit rester verte : 382 tests, 1 ignore, plus ceux que tu ajoutes.
- Tu ne modifies que `moodlesync/ocr.py`, `tests/test_ocr.py`, `docs/ocr-contrat.md` si une formulation doit suivre, `docs/ocr-avancement.md` et ce prompt. Rien d'autre.
- Francais, aucun tiret cadratin ni demi-cadratin. Fichiers en LF. Pas de `git add -A`, pas de push.
- Commit unique, auteur `MarinWasAsleep`, sans mention d'IA. Verifie `git show --stat` : seuls les fichiers ci-dessus.
- Mets a jour le tableau (C4 reste `fait`), la section 6 (les ecarts fermes citent cette entree), et le journal (entree `fin` au format impose), puis prepare le prompt de C5 dans `docs/prompts/17-C5-D.md`, en reprenant la structure et l'etape D du prompt 15.

## Livrable

Reponds avec `Fait / Fichiers / Tests / Decisions / Doutes / Suivant`, le hash du commit et le chemin du prompt 17.
