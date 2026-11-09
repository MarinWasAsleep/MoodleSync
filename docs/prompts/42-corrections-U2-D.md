# Prompt 42 pour DeepSeek v4.1 flash : corrections de U2, `textes.js` et son test

Auteur du prompt : Claude Sonnet (S), 9 novembre 2026, à la fin de la revue de U2 (prompt 41, verdict **bloquant**). Destinataire : DeepSeek v4.1 flash (D), dans une **session neuve**. U2 est `rejetée` : elle revient à son propriétaire, donc à D, et la correction passe avant toute nouvelle tâche (règle de choix, point 2).
Utilisation : coller ce fichier en entier dans la session de DeepSeek, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/42-corrections-U2-D.md et exécute-le ».

---

## Rôle

Tu es DeepSeek v4.1 flash. Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, Claude Sonnet, et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans et d'un mode qui rend un PDF cherchable. Tu as écrit U2 (`moodlesync/interface/textes.js` et `tests/test_textes_js.py`) ; Sonnet l'a relue et l'a rejetée : l'entrée de journal `revue` de U2 (la plus récente, auteur S) donne les mesures.

Cette session contient **une seule tâche** : corriger les constats ci-dessous dans `moodlesync/interface/textes.js` et `tests/test_textes_js.py`, et nulle part ailleurs. Écris d'abord les tests qui échouent sur `ea07635`, puis le code.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\\MoodleSync\\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.
- Une revue ne réécrit pas le code qu'elle relit. Si un constat demande une correction, il devient un écart de la section 6 avec son propriétaire et sa suite, pas une modification dans cette session.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole (section 1), la ligne U2 et la porte « Après U2 » (sections 2 et 3), l'entrée `revue` de U2 (la plus récente) en entier, l'entrée `fin` de U2 (la suivante), les écarts 182 à 195 (section 6) et la ligne du 9 novembre de la section 4 qui porte sur cette revue. **Il fait foi.**
2. `docs/ocr-contrat.md` : 2.7 (formes `ocr_copier`, `ocr_chercher`, `ocr_exporter`, `ocr_ouvrir`, `ocr_lancer`), 3.4 (interface), section 5 (messages et mots à éviter).
3. `docs/plan-ocr.md` : 3.5 (l'onglet Mes textes) et 3.7 (microcopy et ton).
4. `moodlesync/interface/textes.js` et `tests/test_textes_js.py`, en entier, sur le commit `ea07635` (`git show ea07635:<chemin>`, jamais la copie de travail pour les fichiers historiques).
5. `moodlesync/interface/index.html`, **le seul bloc `#v-textes`** (les boutons `#tx-copier-cours`, `#tx-exporter`, `#tx-ouvrir-dossier`, `#tx-qualite`, leurs classes), `moodlesync/interface/commun.js` (`$`, `api`, `toast`) et `moodlesync/interface/app.js` (`choisirOnglet`, `barreOccupee`, `confirmer`), pour comprendre ce que la page appelle. Tu ne modifies aucun des trois.

Ne relis pas les tâches antérieures à U1. Ne lis pas U3 à U5, elles ne sont pas commencées.

## Étape A : base de tests

Crée la branche `agent/corrections-U2-D` sur `ea07635`, puis lance `python -m unittest discover -s tests -t . -v` sur un export propre de ce commit (`git archive`, dossier temporaire hors du dépôt) avec l'interpréteur du venv (`venv-ms`, pywebview 6.2.1) et note le résultat **tel quel**. La base mesurée par la revue est **705 tests, 0 échec, 1 ignoré** (le seul ignoré est T29, Tesseract absent) ; sans `node`, il s'ajoute un ignoré (le parcours sur DOM factice) ; avec un interpréteur sans pywebview, les deux tests de `test_horaire` s'ajoutent. Si la base a bougé, arrête-toi et écris l'écart dans le journal. N'installe rien. Si `node` est présent, sers-t'en pour rejouer le parcours et pour tes sondes.

## Étape B : la correction

**Fichiers touchés : `moodlesync/interface/textes.js` et `tests/test_textes_js.py`, rien d'autre** (hors `docs/ocr-avancement.md` et le prompt suivant, à l'étape D). Pas de modification de `index.html`, `app.js`, `style.css`, d'un fichier Python, du contrat, du plan ni du plan d'exécution : un problème qui demande l'un d'eux se signale dans le journal. Mêmes règles de forme que U2 : aucune phrase hors de `TX_MOTS`, aucun `innerHTML`, aucun mot interdit, aucun tiret long, fichiers en LF.

**Constats à corriger, tous mesurés par la revue (reproduis chacun avant de corriger).**

1. **Écart 187, bloquant : les menus de « Copier le contexte du cours » et d'« Exporter » se referment à l'instant où ils s'ouvrent.** L'écouteur de `document` (`textes.js`, `document.addEventListener("click", ...)`) ferme tout menu quand le clic ne vient ni d'un `.tx-menu` ni d'un élément `.tx-ouvre`. Seul le bouton `…` des lignes porte `tx-ouvre` ; `#tx-copier-cours` et `#tx-exporter` d'`index.html` n'ont que `bouton principal` et `bouton`. Le test masque le défaut : son arbre factice écrit `tx-ouvre` sur ces deux boutons et `dispatchEvent` ne remonte pas. Exigence : le clic qui ouvre un menu ne le ferme pas, **sans toucher `index.html`** (par exemple, `textes.js` marque par `setAttribute` les boutons qui ouvrent un menu au moment du branchement, ou l'écouteur reconnaît les ancres par leur identifiant) ; un clic ailleurs le ferme toujours, un second clic sur le bouton le ferme (comportement actuel). Test : l'arbre factice reprend les classes de `#tx-copier-cours`, `#tx-exporter` et `#tx-ouvrir-dossier` **lues dans `index.html`** (pas recopiées à la main), et un clic fait remonter l'événement de l'élément jusqu'à `document` comme un navigateur (une doublure de `dispatchEvent` qui parcourt les ancêtres jusqu'à `document` suffit). Il doit échouer sur `ea07635` avec ce DOM, puis passer.
2. **Écart 188, moitié page : une copie vide est annoncée comme réussie.** `ocr_copier` rend `{"texte": "", "caracteres": 0, "documents": 0, "pages": 0}` pour une portée vide (par exemple `cours:<cid>` d'un cours jamais coché ni renommé, la moitié API est hors de cette tâche) ; `txCopierCours` et `txCopierDocument` mettent alors `""` dans le presse-papiers (ils écrasent son contenu) et affichent « Copié : 0 caractères. ». Exigence : quand `documents` vaut 0 (ou `caracteres` vaut 0), la page n'écrit rien dans le presse-papiers et affiche une phrase d'avertissement (toast `critique`). La phrase est nouvelle : **propose-la** dans `TX_MOTS` (par exemple « Aucun texte à copier. »), ajoute-la à `PHRASES_NOUVELLES` et pose-la à Maxence en questionnaire à choix dans ton entrée de journal, avec ta recommandation ; ne la tiens pas pour validée. Test : une réponse `documents: 0` ne touche pas le presse-papiers (la doublure garde sa valeur d'avant) et affiche la phrase, pour la copie d'un cours et pour celle d'un document.
3. **Écart 190 : « 1 lisibles ».** L'en-tête accorde « document » et « page » mais pas « lisibles » : `1 document, 1 page, 0,0 Mo de texte. 1 lisibles, 0 à vérifier.` Exigence : « lisible » au singulier pour 0 et 1 (comme « 0 document » au singulier), « lisibles » à partir de 2 ; « à vérifier » ne change pas. Le mot du plan reste « lisibles » (plan 3.5), « lisible » est son singulier : `TX_MOTS` gagne la clé du singulier et le test l'attend. Le parcours existant attend `0 lisibles` : corrige cette attente et ajoute le cas d'un seul document.
4. **Écart 191, deux pertes de recherche.** (i) Taper, quitter l'onglet, y revenir avant 300 ms : `txOuvrir` vide le champ mais ni la minuterie `txDelai` ni le jeton `txJeton` ; la requête part quand même et affiche « 4 résultats », liste masquée, champ vide. (ii) `textesProgres({etat: "terminee"})` rappelle `txOuvrir()`, qui vide le champ et les résultats : la recherche en cours disparaît. Exigence : (i) `txOuvrir` annule la minuterie et invalide le jeton quand il vide le champ (aucune requête ne part, aucun résultat ne s'affiche pour un champ vide) ; (ii) un rechargement déclenché par `terminee` rafraîchit l'en-tête et la liste sous-jacente (`TX`, `txDocs`) sans toucher au champ ni aux résultats affichés ; le retour sur l'onglet continue de repartir de la liste (décision (5) de ton entrée `fin`). Test : un scénario Node pour chacun, qui échoue sur `ea07635`.
5. **Écart 192 : les 23 mutations survivantes.** La revue en a rejoué 49, 26 détectées, 23 survivantes, toutes survivantes à la suite complète. À tuer, chacune par une assertion nommée : `Refaire` sans `refaire=true` (M12) ou sans le second appel `confirme=true` (M13) (asserte `HLANCES`, avec un `{"confirmer": ...}` puis un refus et une acceptation), le format `zip_jsonl` envoyé comme `zip` (M16) (asserte `HEXPORTS` pour les trois formats), le bouton de ligne sans `tx-ouvre` (M42) et l'absence de fermeture au clic ailleurs (M43) (par le DOM de l'exigence 1), seuil de recherche à 1 caractère (M20), pluriel dès 1 (M21), qualité `vide` absente de la fenêtre de qualité (M22), garde `trop_long` du document (M23) et `annule` de l'export (M24), flèche droite non circulaire (M26), `terminee` qui ne recharge plus (M27), clic sur un résultat qui ne passe pas la page (M29) (asserte `HOUVERTURES` avec la page), `pause` et `pause_sync` qui ne marquent plus l'onglet occupé (M31), champ non vidé au retour sur l'onglet (M36), « Tronqué. » jamais affiché (M48), séparateur des milliers retiré (M49). M28, M32, M35, M40, M44 et M46 sont facultatives : tue celles que le même scénario couvre sans le compliquer.
6. **Écart 193, deux défauts de construction du test, à corriger au passage.** (a) La seconde alternative de `test_etat_vide_et_liste_masques` (`or re.search(r'\$\("#tx-liste"\)', t)`) est toujours vraie : retire-la. (b) Le test écrit `tests/_parcours_textes.js` dans l'arbre du dépôt : écris-le dans un dossier temporaire (`tempfile`) et supprime-le dans un `finally`. (c) Élargis `test_aucun_html_construit` à `outerHTML`, `insertAdjacentHTML`, `document.write`, `DOMParser` et `createContextualFragment` (sans toucher à `ic()` ni `esc()`).

**Hors de cette tâche, à ne pas corriger** : la moitié API de l'écart 188 (un cours jamais enregistré ne se résout pas), les écarts 189, 194 et 195, la phrase de `Refaire` quand l'API répond `rien`, le type « Mixte » et l'explication en survol (U5), les écarts 147, 157, 182 à 186, et tout ce qui est dans U3 à U5.

**Test qui doit passer** : `tests/test_textes_js.py` en entier, puis la suite complète (705 tests plus ceux que tu ajoutes, 0 échec, 1 ignoré). Avant de coder, lance les nouveaux tests sur `ea07635` : ils doivent échouer franchement (`AssertionError`, jamais une erreur d'attribut), et tu notes le nombre d'échecs. **Mutations** : rejoue sur une copie hors du dépôt, témoin vert avant et après chaque série, les mutations M12, M13, M16, M20, M21, M22, M23, M24, M26, M27, M29, M31, M36, M42, M43, M48 et M49 ci-dessus, plus celles de l'écart 187 (retirer la marque de l'ancre) et de l'écart 191 (ne pas invalider le jeton) ; écris pour chacune quel test la voit, et classe celles qui survivent.


## Étape D : clôture et chaînage (obligatoire, dernière étape)

Lecture pour cette tâche : dans le point 2 ci-dessous, « état de A3 » se lit « état de U2 » (passage de `rejetée` à `à relire`, jamais directement à `fait`), « colonne Relue » se lit « colonne Relue de U2 » (retour à `non`) et « entrée de journal (`revue` de A3) » se lit « entrée de journal (`fin` de U2, corrections) ». La porte « Après U2 » existe (non franchie, revue de S) : tu ne la modifies pas pour la déclarer franchie, tu ajoutes seulement ce que ta correction a mesuré ; c'est la nouvelle revue de U2 qui tranche. Les écarts 187, 188 (moitié page), 190, 191 et 192 se ferment ou restent ouverts par une phrase de ton entrée de journal qui les cite, avec la mesure ; tu n'écris pas « fermé » sans l'avoir mesuré. La règle de choix s'applique une fois U2 repassée à `à relire` : la tâche suivante est la revue de U2, adressée à S (S n'est pas propriétaire de U2).

1. **Relance la suite complète** et note le résultat réel (elle ne doit pas avoir bougé).
2. **Mets à jour `docs/ocr-avancement.md`** : état de U2, colonne Relue, portes de sortie (section 3), entrée de journal (`revue` de U2), écarts (section 6). Tu n'effaces aucune ligne existante.
3. **Prépare le prompt de l'étape suivante** (règle de choix ci-dessous) et écris-le dans `docs/prompts/NN-<ID>-<S ou D>.md`, où `NN` est le plus grand numéro déjà présent dans `docs/prompts/` plus un.
4. **Commit** (un seul) : `docs/ocr-avancement.md` et le nouveau prompt. Rien d'autre. Pas de push.
   Pour cette tâche, qui produit du code, le commit unique porte en plus les deux fichiers de la tâche (`moodlesync/interface/textes.js`, `tests/test_textes_js.py`) ; le prompt 41 était une revue, sans code, et sa liste ne citait que le journal et le prompt suivant.
5. **Réponds à Maxence** avec le format court : `Fait / Fichiers / Décisions / Doutes / Suivant`, puis le chemin du prompt suivant et la phrase à coller dans la session du destinataire. Tu n'enchaînes pas toi-même la tâche suivante.

### Règle de choix de la tâche suivante

Applique dans cet ordre, la première règle qui donne un résultat :

1. Une tâche à l'état `à relire` (la plus ancienne d'abord) : le prompt suivant est la **revue** de cette tâche, adressée à l'IA qui n'en est **pas** propriétaire. Une tâche terminée ne débloque ses dépendantes qu'une fois relue et `fait`, donc la revue passe avant toute nouvelle tâche.
2. Une tâche `rejetée` : le prompt suivant est la **correction**, adressée à son propriétaire.
3. La première tâche `à faire` ou `bloquée` dont **toutes les dépendances sont `fait`**, adressée à son propriétaire (colonne Proprio). L'ordre est celui de `docs/plan-execution-ocr.md`, section 9, avec E0b placée juste après E0. Si le propriétaire est toi-même, le prompt est écrit à part, pour une session neuve.
4. Aucune tâche prête : il n'y a pas de prompt suivant. Écris à Maxence ce qui bloque (revue manquante, décision à prendre, validation à faire sur macOS) et ce qu'il doit faire.

### Contenu de chaque prompt généré

Un prompt généré reprend la **structure de celui-ci** : Rôle (nom de l'IA destinataire, une tâche, une session) ; Règles non négociables (copie intégrale de la section « Règles non négociables » ci-dessus) ; À lire (le pack de la tâche, selon `docs/plan-execution-ocr.md` section 5, plus le journal et les sections du contrat qui la concernent) ; Étape A (base de tests) ; Étapes de la tâche (contraintes issues des invariants du contrat, livrable exact, test qui doit passer, fichiers qu'elle ne touche pas) ; Étape D de clôture et chaînage, **recopiée mot pour mot, y compris cette règle de choix et cette consigne de contenu**. Cette recopie est ce qui fait tenir la chaîne : un prompt qui ne la contient pas interrompt tout. Pour une tâche d'implémentation, le prompt demande d'abord le test qui échoue, puis le code. Pour une revue, il reprend l'étape B du prompt de revue, adaptée aux fichiers et aux invariants du diff. Il n'invente aucune règle absente du contrat ou du journal.

---

Fin du prompt 42.
