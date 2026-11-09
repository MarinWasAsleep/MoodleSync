# Prompt 34 pour DeepSeek v4.1 flash : corrections des quatre importants de la revue de A1

Auteur : Hermes, orchestrateur, 9 novembre 2026. Destinataire : DeepSeek v4.1 flash, dans une session neuve. Une seule tache : corriger les constats 1 a 4 de la revue de A1, plus les decisions de Maxence ci-dessous.

Ce prompt s'ouvre sur les decisions de Maxence. Elles s'appliquent telles quelles, sans reinterpretation.

## Decisions de Maxence, a appliquer telles quelles

1. **Ecarts 126 et 133, durees annoncees.** L'extraction reste sequentielle : aucun parallelisme n'est ajoute. Le diviseur par `ocr_threads` disparait des annonces (`_ocr_minutes` et `restant_min`). Le reglage `ocr_threads` reste accepte et enregistre par `ocr_regler` (le contrat 3.2 ne change pas sur ce point), mais il ne divise plus aucune duree et il est masque dans l'interface avancee (masquage a faire en U1 ou U5, hors de cette tache : l'ecrire dans le journal, ne pas toucher a l'interface).
2. **Ecart 138, reprise apres synchronisation.** Le lot juge par `_ocr_apres_sync` ne compte que les ajouts de la synchronisation en cours. Une file laissee en `pause` par une session precedente ne repart pas seule, conformement au contrat 2.5.
3. **Ecart 135, mode `--auto`.** En mode automatique sans fenetre, les nouveaux fichiers sont mis en file d'extraction, sans demarrer l'extraction, comme le prevoit le plan 5.5. L'ancien `.md` d'un PDF cherchable republie est archive de la meme facon qu'apres une synchronisation avec fenetre. `moteur.py` n'importe pas `ocr` : le branchement se fait par un point d'appel qui connait `ocr`, sans demarrer la file ni ouvrir de fenetre.

## Les quatre constats a corriger, mesures par la revue

Le detail exact, les mesures et les corrections proposees sont dans `docs/ocr-avancement.md`, entree `2026-11-09 10:36 | A1 | S | revue`, constats 1 a 4, et dans les ecarts 130 a 133 de la section 6. Lis-les, ils font foi.

1. **Ecart 130, la file est ecrasee.** Le fil d'extraction garde sa copie de `file.json` en memoire et la reecrit apres chaque page et chaque document ; `mettre_en_file_apres_sync`, appelee pendant une extraction, ajoute ses taches a une copie relue du disque que le fil ecrase ensuite. Correction attendue : relire la file sous `_ocr_verrou` avant chaque ecriture, ne modifier que sa propre tache, reprendre la boucle tant qu'une tache reste en `attente`. Test : une synchronisation pendant l'extraction avec un nouveau document, la tache est presente a la fin et traitee.
2. **Ecart 131, le remplacement hors verrou.** `progres` relache `_ocr_fichiers` apres la derniere page, puis `traiter_document` appelle `fabriquer_pdf_cherchable` hors verrou. Correction attendue : reprendre `_ocr_fichiers` (par `attendre`) avant l'appel et le relacher apres. Test : une doublure de `fabriquer_pdf_cherchable` lit `_ocr_fichiers.locked()` et doit le trouver vrai.
3. **Ecart 132, le consentement non relu.** `cfg` est lu une seule fois au depart : retirer `ocr_pdf = remplacer` ou desactiver `ocr` en cours d'extraction n'a aucun effet. Correction attendue : relire `_cfg()` avant chaque document, et arreter la file en `annulee` si `ocr` est faux. Test sur les deux reglages.
4. **Ecart 133, les durees fausses.** Voir la decision 1 ci-dessus.

## Regles non negociables

- Francais partout. **Aucun tiret cadratin ni demi-cadratin**, dans le code, les docs et les messages. Un test du contrat le verifie.
- Ne jamais inventer une mesure. Ce qui n'a pas ete mesure s'ecrit « non mesure », ce qui est deduit s'ecrit « deduit ».
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, sans `Co-Authored-By` ni mention d'une IA. Messages en francais sans accents. **Pas de push.**
- Jamais `git add -A`, `git add .`, `git commit -a`, `git clean`. Seulement les fichiers de la tache, puis `git show --stat` pour le prouver.
- Tu ne modifies que `moodlesync/api_textes.py`, `moodlesync/moteur.py`, `moodlesync/application.py`, `tests/test_api_textes.py`, `tests/test_synchro_ocr.py`, `docs/ocr-avancement.md` et ce prompt. Pas `ocr.py`, pas le contrat, pas le plan, pas l'interface : un besoin hors de cette liste se signale au journal, il ne se corrige pas.
- Aucun fichier de l'utilisateur, aucun document de cours, aucun jeton dans le depot ni dans tes reponses.

## Etat de depart, verifie le 9 novembre 2026

- Branche : `agent/A1-S`, tete `dcd2d4e` (revue de A1), poussee sur `private/agent/A1-S`. Cree ta branche `agent/corrections-A1-2-D` a partir de `dcd2d4e`.
- Suite de reference : `python -m unittest discover -s tests -t .` avec `/opt/data/cache/scratch/venv-ms/bin/python`, 556 tests, 0 echec, 1 ignore. Mesure-la toi-meme avant de toucher au code.
- `docs/prompts/33-A2-D.md` existe deja : ne le lance pas, ne le reecris pas. A2 attend la fin de cette tache.

## Etapes

A. Mesure la suite complete et colle le resultat reel.
B. Pour chaque constat, ecris d'abord le test qui echoue, puis la correction minimale. Un constat, un test, une correction. Ne melange pas les quatre dans un seul diff illisible.
C. Relance la suite complete et colle le resultat reel. Attendu : 556 tests plus les tiens, 0 echec, 1 ignore.
D. Mets a jour `docs/ocr-avancement.md` : entrees de journal (`fin` de cette correction), section 2 (base de tests), section 4 (une ligne par decision de Maxence ci-dessus, auteur « Maxence, via Hermes »), section 6 (ecarts 130 a 133, 135 et 138 : fermes ou reduits, avec la mesure). Tu n'effaces aucune ligne existante.
E. Commit unique, auteur impose, `git show --stat` verifie, message en francais sans accents.
F. Reponds avec `Fait / Fichiers / Tests / Decisions / Doutes / Suivant`, le hash du commit et la sortie reelle de la suite. Tu n'enchaines pas A2 toi-meme.

---

Fin du prompt 34.
