# Prompt 43 pour Claude Sonnet : revue des corrections de U2, `textes.js` et son test

Auteur du prompt : DeepSeek v4.1 flash (D), 9 novembre 2026, à la fin des corrections de U2 (prompt 42). Destinataire : Claude Sonnet (S), dans une **session neuve**. U2 est repassée `à relire` : elle revient à l'IA qui n'en est pas propriétaire, donc à S, et la revue passe avant toute nouvelle tâche (règle de choix, point 1).
Utilisation : coller ce fichier en entier dans la session de Claude Sonnet, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/43-revue-U2-S.md et exécute-le ».

---

## Rôle

Tu es Claude Sonnet. Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, DeepSeek v4.1 flash, et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans et d'un mode qui rend un PDF cherchable. Le moteur, la synchronisation, le mixin `ApiTextes`, le contrat, la coquille de l'onglet « Mes textes » (U1) et `textes.js` (U2) sont écrits.

Ta revue de U2 (prompt 41) a rendu un verdict **bloquant** et rejeté U2 : les menus de « Copier le contexte du cours » et d'« Exporter » se refermaient à l'instant où ils s'ouvraient (écart 187), la copie d'un cours jamais coché ni renommé annonçait une réussite vide (écart 188, moitié page), l'en-tête écrivait « 1 lisibles » (écart 190), deux pertes de recherche (écart 191) et 23 mutations survivantes (écart 192). D a corrigé ces cinq écarts dans `moodlesync/interface/textes.js` et `tests/test_textes_js.py` (prompt 42), avec les deux défauts de construction du test de l'écart 193.

Cette session contient **une seule tâche** : la revue ciblée de ces corrections (diff, contrat, tests, journal). Ce n'est pas une refonte et ce n'est pas une correction : tu ne modifies aucun fichier de code, ni test, ni contrat, ni plan, ni plan d'exécution. Les constats s'écrivent, ils ne se corrigent pas.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\\MoodleSync\\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.
- Une revue ne réécrit pas le code qu'elle relit. Si un constat demande une correction, il devient un écart de la section 6 avec son propriétaire et sa suite, pas une modification dans cette session.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole (section 1) ; la ligne U2 (section 2) ; la porte « Après U2 » (section 3) ; l'entrée `fin` des corrections (la plus récente, auteur D) et l'entrée `revue` de U2 (la précédente, auteur S) ; les écarts 187 à 195 (section 6) ; la ligne du 9 novembre de la section 4 qui porte sur ces corrections. **Il fait foi.**
2. `docs/ocr-contrat.md` : 2.7 (formes `ocr_copier`, `ocr_chercher`, `ocr_exporter`, `ocr_ouvrir`, `ocr_lancer`), 3.4 (interface), section 5 (messages et mots à éviter).
3. `docs/plan-ocr.md` : 3.5 (l'onglet Mes textes) et 3.7 (microcopy et ton).
4. Le commit des corrections : `git log --oneline -3 agent/corrections-U2-D`, `git show --stat` de son sommet, puis `git diff ea07635 <sommet>` pour `moodlesync/interface/textes.js` et `tests/test_textes_js.py`. Lis ces deux fichiers en entier sur ce commit (`git show <sommet>:<chemin>`), jamais la copie de travail pour les fichiers historiques.
5. `moodlesync/interface/index.html` (le seul bloc `#v-textes`, les identifiants et les classes des boutons `#tx-copier-cours`, `#tx-exporter`, `#tx-ouvrir-dossier`, et la balise `textes.js`), `moodlesync/interface/commun.js` (`$`, `api`, `toast`) et `moodlesync/interface/app.js` (`choisirOnglet`, `majActions`, `barreOccupee`, la navigation au clavier des onglets, `confirmer`), en lecture seule : tu ne modifies aucun des trois.
6. `docs/plan-execution-ocr.md` : section 3 (ligne U2 et sa porte « parcours complet sans rechargement »), section 5 (pack interface).

Ne relis pas les tâches antérieures à U1. Ne lis pas U3 à U5, elles ne sont pas commencées.

## Étape A : base de tests

Crée la branche `agent/revue-U2-2-S` sur le sommet de `agent/corrections-U2-D`, puis lance `python -m unittest discover -s tests -t . -v` sur un export propre de ce commit (`git archive`, dossier temporaire hors du dépôt) et note le résultat **tel quel**, au début et à la fin de la revue. La base annoncée par les corrections est **705 tests, 0 échec, 1 ignoré** avec un interpréteur qui a pywebview (le venv `venv-ms`, pywebview 6.2.1) : le seul ignoré est T29, Tesseract absent. Sans `node`, il s'ajoute un ignoré (le parcours sur DOM factice) ; avec un interpréteur sans pywebview, les deux tests de `test_horaire` s'ajoutent à T29. Si la base a bougé, arrête-toi et écris l'écart dans le journal.

**Faits de la machine de D** (mesurés le 9 novembre 2026) : Linux, Python 3.14.9, pywebview 6.2.1 dans le venv `venv-ms`, Node 26.12.1, Tesseract absent, `pypdfium2` absent, aucun navigateur, rien installé. Si `node` est présent chez toi, sers-t'en pour rejouer le parcours du test et pour tes propres sondes ; sinon écris « non mesuré » et dis dans tes doutes ce que tu n'as pas pu exécuter.

## Étape B : la revue

**But.** Dire si les corrections ferment les écarts 187, 188 (moitié page), 190, 191 et 192 sans en ouvrir d'autres, si le test voit maintenant ce qu'il prétend voir, et si la porte « parcours complet sans rechargement » peut être franchie. Verdict final : `bloquant`, `important`, `mineur` ou `rien`.

Ordre imposé, une section par point, chaque constat numéroté et mesuré :

1. **Périmètre et forme.** `git show --stat` du commit des corrections : doit lister `moodlesync/interface/textes.js`, `tests/test_textes_js.py`, `docs/ocr-avancement.md` et le prompt 43, rien d'autre, en particulier ni `index.html`, ni `app.js`, ni `style.css`, ni fichier Python, ni contrat, ni plan, ni plan d'exécution. Zéro octet CR dans les deux fichiers de la tâche, écrits en LF. Auteur `MarinWasAsleep`, aucun `Co-Authored-By` ni mention d'IA dans le message. Le journal ne perd aucune entrée (comparer ligne à ligne avec `ea07635`). Aucun tiret long dans les fichiers touchés ni dans les lignes ajoutées au journal.
2. **Écart 187, les menus d'action.** Exige : le clic qui ouvre un menu ne le ferme pas, sans qu'`index.html` change (mesure que son blob est identique à celui de `ea07635`) ; un clic ailleurs le ferme toujours ; un second clic sur le bouton le ferme. Mesure sur un DOM factice qui reprend les classes des boutons **lues dans `index.html`** et dont les événements remontent de l'élément jusqu'à `document` : le menu de « Copier le contexte du cours », celui d'« Exporter » et celui d'une ligne doivent rester ouverts après la remontée du clic qui les ouvre. Dis quelle ligne de `textes.js` fait tenir le comportement, et si un identifiant ou une classe nouvelle apparaît dans le DOM (le contrat 3.4 ne prévoit que les quinze identifiants de l'onglet) ; une classe posée à l'exécution est acceptable, un identifiant nouveau ne l'est pas.
3. **Écart 188, la copie vide (moitié page).** Exige : quand `documents` vaut 0 ou `caracteres` vaut 0, la page n'écrit rien dans le presse-papiers et affiche un avertissement `critique`, pour la copie d'un document comme pour celle d'un cours ; la phrase nouvelle est dans `TX_MOTS` et dans `PHRASES_NOUVELLES`, elle est posée à Maxence en questionnaire à choix avec une recommandation dans l'entrée de journal, et elle n'est pas tenue pour validée. Mesure que la doublure du presse-papiers garde sa valeur d'avant. Vérifie que la garde passe après `trop_long` (une réponse `trop_long` n'a que `caracteres` et garde sa phrase) et que le cas `documents` valant 0 mais `caracteres` non nul est aussi couvert.
4. **Écart 190, l'accord de l'en-tête.** « 0 lisible » et « 1 lisible » au singulier, « lisibles » à partir de 2, « à vérifier » inchangé, `TX_MOTS` avec la clé du singulier, le test qui attend les deux formes (aucun document, un seul document). Mesure les trois cas sur le parcours, en-tête entier comparé mot pour mot.
5. **Écart 191, les deux pertes de recherche.** (i) Taper, quitter l'onglet, y revenir avant 300 ms : aucune requête ne doit partir, aucun résultat ne doit s'afficher pour un champ vide, et une réponse déjà en vol doit être ignorée après le retour sur l'onglet (la minuterie et le jeton sont annulés quand le champ est vidé). (ii) `textesProgres({etat: "terminee"})` rafraîchit l'en-tête et la liste sous-jacente (`TX`, `txDocs`) sans toucher au champ ni aux résultats affichés. Le retour sur l'onglet continue de repartir de la liste (décision (5) de l'entrée `fin` de U2). Mesure les deux scénarios, et dis si un troisième cas de perte subsiste.
6. **Écart 192, les mutations.** Rejoue sur une copie hors du dépôt, témoin vert avant et après chaque série, les dix-sept mutations de l'écart 192 (M12, M13, M16, M20, M21, M22, M23, M24, M26, M27, M29, M31, M36, M42, M43, M48, M49), plus celle de l'écart 187 (retirer la marque de l'ancre) et celle de l'écart 191 (ne pas invalider le jeton). Écris pour chacune quel test la voit, et classe celles qui survivent, y compris à la suite complète. Cherche aussi ce que le test ne voit pas encore : le toast d'échec de copie (M40), une phrase d'un mot hors de la table (M46), la phrase de `Refaire` quand l'API répond `rien` (écart 194, hors de la correction).
7. **Écart 193, la construction du test.** Vérifie que la seconde alternative toujours vraie de `test_etat_vide_et_liste_masques` a disparu, que le script du parcours est écrit dans un dossier temporaire et supprimé dans un `finally` (plus de `tests/_parcours_textes.js` dans l'arbre, et un `git status` propre après le test), et que la garde « aucun HTML construit » couvre `outerHTML`, `insertAdjacentHTML`, `document.write`, `DOMParser` et `createContextualFragment` sans toucher à `ic()` ni `esc()`. Dis ce qui reste ouvert dans l'écart 193 (phrase comparée par sous-chaîne, phrase d'un mot).
8. **Le test.** Lis `tests/test_textes_js.py` en entier. Lance-le sur le commit des corrections : vert. Lance-le sur un export propre de `ea07635` avec le seul fichier de test des corrections : il doit échouer franchement, en `AssertionError` (nombre d'échecs noté tel quel), et l'échec doit venir du comportement, pas d'un fichier absent. Vérifie que le parcours exerce les **vraies** fonctions de `commun.js`, `textes.js` et `app.js`, que l'arbre factice lit bien les classes d'`index.html` à l'exécution, et qu'aucune assertion ne passe déjà sur `ea07635`. Dis sans complaisance ce que le test ne voit toujours pas.
9. **La porte et le journal.** Confirme ou corrige l'état de la porte « parcours complet sans rechargement » (section 3) avec tes mesures, et rappelle ce qu'elle ne prouve pas : aucune vraie fenêtre pywebview, aucun navigateur, aucun vrai presse-papiers, Windows et macOS non exécutés, aucune lecture d'écran. Vérifie chaque chiffre de l'entrée `fin` des corrections (tests, échecs, mutations, lignes de diff), que les écarts 187, 188 côté page, 190, 191 et 192 sont fermés avec leur mesure ou restent ouverts avec la raison, que 188 côté API, 189, 193 (ce qui reste), 194 et 195 restent ouverts et bien classés, et que le questionnaire sur la phrase de copie vide est complet, sans décision prise à la place de Maxence.

**Ce que la revue ne fait pas.** Aucune correction de code, aucun test ajouté, aucun identifiant DOM nouveau, aucune phrase changée. Aucune affirmation sans mesure. Aucun constat sur le style général, sur des fichiers hors du diff, ou sur des limites déjà déclarées (vraie fenêtre, presse-papiers, Windows, macOS).

## Étape D : clôture et chaînage (obligatoire, dernière étape)

Lecture pour cette tâche : dans le point 2 ci-dessous, « état de A3 » se lit « état de U2 » (passage à `fait`, ou à `rejetée` si ton verdict est bloquant), « colonne Relue » se lit « colonne Relue de U2 » et « entrée de journal (`revue` de A3) » se lit « entrée de journal (`revue` de U2, seconde) ». La porte « Après U2 » existe (complétée par les corrections) : confirme-la, corrige-la, ou laisse-la sous réserves en complétant sa liste ; c'est ta revue qui tranche. La règle de choix s'applique une fois U2 relue : si U2 passe à `fait`, la première tâche prête est U3 (dépendances C2 et U1, toutes deux `fait`), adressée à S ; si U2 est `rejetée`, la tâche suivante est la correction de U2, adressée à D.

1. **Relance la suite complète** et note le résultat réel (elle ne doit pas avoir bougé).
2. **Mets à jour `docs/ocr-avancement.md`** : état de U2, colonne Relue, portes de sortie (section 3), entrée de journal (`revue` de U2), écarts (section 6). Tu n'effaces aucune ligne existante.
3. **Prépare le prompt de l'étape suivante** (règle de choix ci-dessous) et écris-le dans `docs/prompts/NN-<ID>-<S ou D>.md`, où `NN` est le plus grand numéro déjà présent dans `docs/prompts/` plus un.
4. **Commit** (un seul) : `docs/ocr-avancement.md` et le nouveau prompt. Rien d'autre. Pas de push.
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

Fin du prompt 43.
