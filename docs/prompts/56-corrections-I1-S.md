# Prompt 56 pour Claude Sonnet : corrections de l'installation du moteur

Auteur : Hermes, orchestrateur, 9 novembre 2026. Destinataire : Claude Sonnet (S), dans une session neuve. Une seule tache, cinq constats.

## Decisions de Maxence, a appliquer telles quelles

1. **Ecart 247 et 245 ensemble**, dans cette tache : le telechargement inutile et l'absence de progression sont corriges en meme temps.
2. **Ecart 248 avec eux** : une installation precedente n'est jamais effacee sans le dire.
3. **Ecart 251** : les quatre codes de I1 entrent dans `CODES_A3`, avec un test qui les couvre.
4. **Ecart 252** : un paquet sans les donnees de langue est refuse avant toute decompression.
5. **Ecart 240** : `ocr_apres_sync` est expose dans `ocr_etat().reglages`, pour que la case de la page reflete toujours la vraie valeur.

## Role

Tu es Claude Sonnet (S). Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec DeepSeek v4.1 flash (D) et avec Maxence, le proprietaire. Tu n'as aucune memoire des sessions precedentes : tout ce que tu dois savoir est dans le depot. `installer_paquet` et `ocr_installer` existent (tache I1) et sont relus ; leurs defauts sont mesures dans le journal.

Cette session corrige cinq defauts de l'installation du moteur et du reglage d'extraction automatique. Elle ne fait rien d'autre.

## Regles non negociables

- Francais. **Aucun tiret cadratin ni demi-cadratin**, nulle part : ni dans tes reponses, ni dans les fichiers. Ecriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure. Ce qui n'a pas ete mesure s'ecrit « non mesure ». Ce qui est deduit s'ecrit « deduit ».
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` dans le depot ni dans tes reponses.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, sans `Co-Authored-By` ni mention d'une IA. Messages en francais sans accents. **Pas de push.**
- Jamais `git add -A`, `git add .`, `git commit -a`, `git clean`. Seulement les fichiers de la tache, puis `git show --stat` pour le prouver.
- Aucun test ne touche le reseau : les requetes sont doublees.

## A lire, dans cet ordre

1. `docs/ocr-avancement.md` : les ecarts 240, 245, 247, 248, 251 et 252 (section 6) et l'entree `revue` de I1 (auteur D). **Ils font foi**, avec leurs mesures.
2. `docs/ocr-contrat.md` : 2.7 (`ocr_etat`), 3.1 (`installer_paquet`, `detecter`), 3.2 (`ocr_installer`), 3.4 (interface, la carte et les reglages), 5 (messages et `CODES_A3`).
3. `moodlesync/ocr.py` : `installer_paquet`, `_mettre_en_place`, `detecter`, `_detecter`, `_trouver`, `MESSAGES`.
4. `moodlesync/api_textes.py` : `ocr_installer`, `ocr_etat`, `_ocr_moteur`, `_ocr_journal`.
5. `moodlesync/interface/sync.js` et `app.js` : le bouton « Installer » de la carte et le groupe de reglages.
6. `tests/test_installer_ocr.py` et `tests/test_api_textes.py` (la ligne qui fige `set(reglages)`).

## Etat de depart

- Branche `agent/corrections-I1-S`, a creer a partir de `28bd150`.
- Suite de reference : 798 tests, 0 echec, 1 ignore, avec `/opt/data/cache/scratch/venv-ms/bin/python` (pywebview 6.2.1, Pillow, pypdf, pypdfium2, Node 26). Mesure-la toi-meme d'abord.

## Les constats

**1. Ecart 247 (important).** Un moteur indique dans les reglages ou trouve dans le PATH qui existe mais ne repond pas rend toute installation impossible : `_trouver` s'arrete sur ce candidat, `detecter` rend absent, le paquet fraichement installe est supprime, et chaque clic refait 65 Mo. Correction : apres la pose du paquet, detecter directement l'executable installe (chemin connu, pas l'ordre des candidats) ; et dans `_trouver`, n'accepter un candidat que s'il repond a `--version` avec une version 4 ou 5, sinon passer au suivant. Test : un `ocr_exe` qui existe mais rend une version 3 n'empeche pas l'installation ; l'installation reussit et le paquet reste.

**2. Ecart 245 (important).** `ocr_installer` bloque pendant le telechargement et la page n'a ni progression ni annulation. Correction : `ocr_installer` relaie `progres` et `arreter` a `installer_paquet` (une methode de progression dediee, par exemple `window.textesInstallation(recu, total)`), et la carte affiche une barre pendant l'installation avec un bouton « Annuler » qui pose l'arret. Test : la progression est poussee au moins deux fois, l'annulation rend `{"annule": True}` et ne laisse aucun dossier.

**3. Ecart 248 (mineur).** Une installation precedente dans `tesseract/` est supprimee quand la detection echoue apres le renommage. Correction : detecter avant de remplacer, et si une installation precedente existe et fonctionne, la conserver ; en cas d'echec du nouveau paquet, restaurer l'ancien. Test : dossier precedent present et valide, nouveau paquet invalide, l'ancien est intact.

**4. Ecart 251 (mineur).** Les quatre codes de I1 ne sont pas dans `CODES_A3`. Correction : les y ajouter, avec un test qui lit `CODES_A3` et verifie que chaque code a une phrase dans `MESSAGES` et dans la section 5 du contrat.

**5. Ecart 252 (mineur).** Un paquet sans `tessdata/` s'installe et annonce un succes. Correction : refuser avant toute decompression un paquet dont l'archive ne porte pas de dossier `tessdata` avec au moins un fichier `.traineddata`. Test : archive sans `tessdata`, refus, phrase de `paquet_invalide`, aucun dossier laisse.

**6. Ecart 240 (important).** `ocr_etat().reglages` n'expose pas `ocr_apres_sync`, donc la case de la page se reaffiche cochée apres un redemarrage. Correction : exposer la cle dans `reglages`, mettre a jour le contrat 2.7 et la ligne de `tests/test_api_textes.py` qui fige `set(reglages)`, et faire lire cette valeur par `app.js` en priorite sur la memoire de page. Test : reglage a faux dans la configuration, `ocr_etat` le rend, la case s'affiche decochee.

## Etapes

A. Mesure la suite complete et colle le resultat reel.
B. Pour chaque constat, ecris d'abord le test qui echoue, puis la correction minimale. Un constat, un test, une correction.
C. Relance la suite complete. Attendu : 798 tests plus les tiens, 0 echec, 1 ignore, et toujours zero tentative reseau.
D. Mets a jour `docs/ocr-avancement.md` : entree `fin`, section 2 (base de tests), section 6 (les six ecarts : fermes ou reduits, avec la mesure). Tu n'effaces aucune ligne existante.
E. Commit unique, auteur impose, `git show --stat` verifie. Tu ne touches pas `docs/plan-ocr.md` (ecart 244, pour P1).
F. Reponds avec `Fait / Fichiers / Tests / Decisions / Doutes / Suivant`, le hash du commit et la sortie reelle de la suite. Tu n'enchaines pas la revue.

---

Fin du prompt 56.
