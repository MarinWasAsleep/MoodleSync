# Prompt 41 pour Claude Sonnet : revue de U2, `textes.js` (liste, recherche, copie, export)

Auteur du prompt : DeepSeek v4.1 flash (D), 9 novembre 2026, à la fin de U2 (prompt 40). Destinataire : Claude Sonnet (S), dans une **session neuve**. U2 est `à relire` : elle revient à l'IA qui n'en est pas propriétaire, donc à S, et la revue passe avant toute nouvelle tâche (règle de choix, point 1).
Utilisation : coller ce fichier en entier dans la session de Claude Sonnet, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/41-revue-U2-S.md et exécute-le ».

---

## Rôle

Tu es Claude Sonnet. Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, DeepSeek v4.1 flash, et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans (OCR avec Tesseract) et d'un mode qui rend un PDF cherchable. Le moteur, la synchronisation, le mixin `ApiTextes` (`moodlesync/api_textes.py`) et le contrat sont écrits, testés et relus. La coquille HTML et CSS de l'onglet « Mes textes » (U1) est écrite et relue. U2 vient d'être livrée par D : `textes.js`, la balise qui le charge, les trois onglets d'`app.js`, les styles des lignes et des résultats, et `tests/test_textes_js.py`.

Cette session contient **une seule tâche** : la revue ciblée de U2 (diff, contrat, tests, journal). Ce n'est pas une refonte et ce n'est pas une correction : tu ne modifies aucun fichier de code, ni test, ni contrat, ni plan, ni plan d'exécution. Les constats s'écrivent, ils ne se corrigent pas.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\\MoodleSync\\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.
- Une revue ne réécrit pas le code qu'elle relit. Si un constat demande une correction, il devient un écart de la section 6 avec son propriétaire et sa suite, pas une modification dans cette session.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole (section 1), l'état des tâches (section 2, ligne U2), les portes (section 3, dont « Après U2 » et ses réserves), l'entrée `fin` de U2 (la plus récente, auteur D) avec ses trois questionnaires pour Maxence, l'entrée `revue` de U1, les écarts 172, 175, 178, 179, 182, 183, 184, 185 et 186. **Il fait foi.**
2. `docs/ocr-contrat.md` : section 1 (conventions), **2.7 (formes renvoyées par l'API)**, **3.2 (méthodes et progression)**, **3.4 (interface)**, section 5 (messages et mots à éviter), section 6 (T28, T30).
3. `docs/plan-ocr.md` : **3.5 en entier (l'onglet Mes textes)** et 3.7 (microcopy et ton). Le plan 3.6 ne concerne pas U2.
4. `docs/plan-execution-ocr.md` : section 3 (ligne U2 et sa porte : « parcours complet sans rechargement »), phase 5, section 5 (Pack interface), section 8.
5. Le diff de U2 : `git log --oneline -3 agent/U2-D`, `git show --stat` du commit de U2, puis `git diff 9cf1c56 <commit de U2>` pour `moodlesync/interface/textes.js` (nouveau, en entier), `index.html`, `app.js`, `style.css`, et `tests/test_textes_js.py` (nouveau, en entier). Lis aussi les fichiers entiers des trois blobs modifiés, jamais la copie de travail, qui porte des CRLF pour les fichiers historiques.
6. Pour comprendre ce que la page appelle : `moodlesync/api_textes.py`, **en lecture seule**, les docstrings de `ocr_etat`, `ocr_documents`, `ocr_chercher`, `ocr_copier`, `ocr_exporter`, `ocr_ouvrir`, `ocr_lancer`, `_ocr_portee`, et dans `moodlesync/application.py` la méthode publique `ouvrir`. Vérifie au passage que `ocr_verifie` et `ocr_orphelin` n'existent pas (écart 182) et que `ouvrir` n'ouvre pas un fichier d'origine (écart 183).
7. `moodlesync/interface/commun.js`, `app.js` et `index.html` sur le commit de U2, pour les aides (`$`, `ic`, `api`, `toast`, `barreOccupee`, `confirmation`), les dialogues, `etatVerification`, et la navigation au clavier des onglets.

Ne relis pas les tâches antérieures à U1 : le journal les résume. Ne relis pas U3 à U5, elles ne sont pas commencées.

## Étape A : base de tests

Crée la branche `agent/revue-U2-S` sur le commit de U2, puis lance `python -m unittest discover -s tests -t . -v` sur un export propre de ce commit (`git archive`, dossier temporaire hors du dépôt) et note le résultat **tel quel**, au début et à la fin de la revue. La base annoncée par U2 est **705 tests, 0 échec, 1 ignoré** avec un interpréteur qui a pywebview (le venv `venv-ms`, pywebview 6.2.1) : le seul ignoré est T29, Tesseract absent. Sans `node`, il s'ajoute un ignoré (le parcours sur DOM factice), soit 705 tests, 0 échec, 2 ignorés, mesuré ; avec un interpréteur sans pywebview, les deux tests de `test_horaire` s'ajoutent à T29, soit 3 ignorés. Si la base a bougé, arrête-toi et écris l'écart dans le journal.

**Faits de la machine de D** (mesurés le 9 novembre 2026) : Linux, Python 3.14.9, pywebview 6.2.1 dans le venv, Tesseract absent, `pypdfium2` absent, aucun navigateur, **Node 26 présent** (`node --version`). N'installe rien. Si `node` est présent chez toi, sers-t'en pour rejouer le parcours du test et pour tes propres sondes ; sinon écris « non mesuré » et dis dans tes doutes ce que tu n'as pas pu exécuter (Windows, macOS, vraie fenêtre, vrai navigateur, vrai presse-papiers).

## Étape B : la revue

**But.** Dire si U2 tient le contrat, si la porte « parcours complet sans rechargement » est franchie, et si le test voit ce qu'il prétend voir. Verdict final : `bloquant`, `important`, `mineur` ou `rien`.

Ordre imposé, une section par point, chaque constat numéroté et mesuré :

1. **Périmètre et forme.** `git show --stat` du commit de U2 : doit lister les cinq fichiers de la tâche, `docs/ocr-avancement.md` et le prompt 41, rien d'autre. Aucun fichier Python, ni contrat, ni plan, ni plan d'exécution, ni test existant. `git diff --numstat` : `index.html` +1 et 0 retirée, `app.js` +10 et 4 remplacées (la table des onglets, `majActions`, `choisirOnglet`, la navigation au clavier), `style.css` +46 et 0 retirée, `textes.js` et `test_textes_js.py` nouveaux. Zéro octet CR dans les cinq fichiers. Auteur `MarinWasAsleep`, aucun `Co-Authored-By`. Le journal ne perd aucune entrée.
2. **Invariants du contrat 3.4.** Trois onglets (`#o-textes` avec `aria-selected`, `tabindex`, seul `#v-textes` visible, `#actions-sync` et `#actions-semaine` masqués), `choisirOnglet` appelle `txOuvrir()` si elle existe, `TX`, `txPret`, `txOccupe`, `occupations` par `barreOccupee(..., "textes")`, `textesProgres` et `textesJournal` définis, `textes.js` chargé avant `app.js`. Le comportement des deux onglets existants (`placerCurseur`, démarrage sur `semaine` ou `sync`, `etatVerification`, `remplirTiroir`) ne doit pas changer : diff d'`app.js` à l'appui, et exécution des vraies fonctions sur un DOM factice si `node` est là.
3. **Ce que la page fait, phrase par phrase.** L'en-tête (les cinq nombres, le volume en Mo avec virgule, les lisibles, les à vérifier, l'accord au singulier), la liste (groupe cours et section, nom, type, pages, badge, **Ouvrir**, menu **Copier le texte** / **Refaire**), la recherche (délai de 300 ms, deux caractères au moins, une seule requête en vol, réponse périmée ignorée, compte et « Tronqué. », `<mark>`, jointure des segments, champ vidé qui remet la liste), les actions principales (cours par `SC` puis `ocr_copier("cours:<cid>")`, export en trois formats sur `tout`, dossier des textes, qualité). Vérifie chaque appel d'API contre `ApiTextes` et chaque forme 2.7 contre le contrat. Cherche les cas limites : un document sans page, un nom qui contient `<`, un `sortie` absolu ou vide, une réponse `{"erreur": phrase}`, `{"trop_long": true}`, `{"annule": true}`, `{"confirmer": ...}`, `{"rien": true}`, une liste vide, un `SC` vide, un cours non choisi.
4. **Aucun HTML construit avec des données.** Aucun `innerHTML` dans `textes.js` ; tout texte de l'API par `textContent` ou `createTextNode` ; les attributs (`data-chemin`) posés par `setAttribute`. Le test vérifie l'absence d'`innerHTML` : dis si cette garde est assez large.
5. **Phrases, mots interdits, tirets.** Toute phrase d'interface passe par `TX_MOTS`, les mots du plan 3.5 sont repris mot pour mot, les 18 phrases nouvelles sont bien dans `PHRASES_NOUVELLES` du test, aucun des sept mots interdits (OCR, Tesseract, tessdata, DPI, segmentation, PSM, TSV) hors des noms d'appels et des identifiants, aucun tiret long. Dis pour chaque phrase nouvelle si tu l'acceptes, la remplacerais, ou la renvoies à Maxence ; c'est lui qui tranche, mais ton avis est attendu.
6. **Le test.** Lis `tests/test_textes_js.py` en entier. Lance-le sur le commit de U2 : vert. Lance-le sur `9cf1c56` plus le seul fichier de test : il doit échouer franchement (U2 annonce `FAILED (failures=19)`, 15 tests, tous en `AssertionError`), et dis si l'échec dépend bien du code et non d'un fichier absent. Vérifie qu'il passe sans `node` (le parcours s'ignore) et que le parcours Node exerce les **vraies** fonctions d'`app.js` et de `textes.js`, pas une copie. Cherche ce que le test ne voit pas : une phrase écrite hors de la table sans accent ni mot outil, un libellé changé sans accent, un état intermédiaire non observé, une assertion qui passerait aussi sans le code (compte les sous-cas qui passent déjà sur le commit de départ).
7. **Mutations.** Rejoue au moins dix mutations de ton cru sur une copie hors du dépôt, témoin vert avant et après, dont les onze annoncées par U2 (masquage de `#tx-vide`, `innerHTML`, délai de 300 ms, `#actions-sync`, réponse périmée, une seule requête en vol, libellé « Ouvrir », appel à `txOuvrir()`, mot interdit, phrase hors table). Écris pour chacune quel test la voit, et **quelles mutations survivent**, y compris à la suite complète. Une mutation survivante est un constat, pas un échec de la tâche : classe-la.
8. **La porte « parcours complet sans rechargement ».** Confirme ou corrige l'état écrit dans la section 3, avec les mesures du parcours et tes propres sondes. Dis ce que la porte ne prouve pas : aucune vraie fenêtre pywebview, aucun navigateur, aucun vrai presse-papiers, Windows et macOS non exécutés. Ces limites sont déjà déclarées par U2 : ne les compte pas comme des constats, sauf si U2 les a masquées.
9. **Le journal.** Vérifie que chaque chiffre de l'entrée `fin` de U2 est exact (690 et 705 tests, 19 échecs, onze mutations, 542 lignes, 1, 10 et 46 lignes de diff), que les écarts 182 à 186 sont bien ouverts et bien classés, que les trois questionnaires pour Maxence sont complets et qu'aucune décision de Maxence n'est prise à sa place. Corrige par une entrée nouvelle, jamais en réécrivant l'ancienne.

**Ce que la revue ne fait pas.** Aucune correction de code, aucun test ajouté, aucun identifiant DOM nouveau, aucune phrase changée. Aucune affirmation sans mesure. Aucun constat sur le style général, sur des fichiers hors du diff, ou sur des limites déjà déclarées (vraie fenêtre, presse-papiers, Windows, macOS).

## Étape D : clôture et chaînage (obligatoire, dernière étape)

Lecture pour cette tâche : dans le point 2 ci-dessous, « état de A3 » se lit « état de U2 » (passage à `fait`, ou à `rejetée` si ton verdict est bloquant), « colonne Relue » se lit « colonne Relue de U2 » et « entrée de journal (`revue` de A3) » se lit « entrée de journal (`revue` de U2) ». La porte « Après U2 » existe (ajoutée par U2) : confirme-la, corrige-la, ou laisse-la sous réserves en complétant sa liste. La règle de choix s'applique une fois U2 relue : si U2 passe à `fait`, la tâche suivante est U3 (dépendances C2 et U1 `fait`), adressée à S ; si U2 est `rejetée`, la tâche suivante est la correction de U2, adressée à D.

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

Fin du prompt 41.
