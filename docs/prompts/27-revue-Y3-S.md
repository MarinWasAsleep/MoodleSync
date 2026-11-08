# Prompt 27 pour Claude Sonnet : revue de Y3 (tests de non-régression de la synchronisation)

Auteur du prompt : DeepSeek v4.1 flash, 8 novembre 2026, à la fin de la tâche Y3 (prompt 25). Destinataire : Claude Sonnet, dans une **session neuve** (tu n'as aucune mémoire de la session qui a préparé ce prompt). Y3 a été écrite par DeepSeek v4.1 flash ; la revue est confiée à S, qui n'en est pas propriétaire.
Utilisation : coller ce fichier en entier dans la session de Claude Sonnet, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/27-revue-Y3-S.md et exécute-le ».

---

## Rôle

Tu es Claude Sonnet. Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, DeepSeek v4.1 flash, et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans (OCR avec Tesseract) et d'un mode qui rend un PDF cherchable.

Cette session contient **une seule tâche** : la revue de Y3, c'est-à-dire de la classe `SynchronisationNative` ajoutée à la fin de `tests/test_synchro_ocr.py` (dix tests qui figent le comportement actuel de `telecharger` sur un coffre sans OCR) et de la correction de l'écart 95 dans la classe `ArgumentsActuels` du même fichier, faits par DeepSeek v4.1 flash. Tu ne fais rien d'autre. Tu ne modifies ni le code, ni les tests, ni le contrat, ni le plan : tu relis et tu juges.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\\MoodleSync\\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole, l'état des tâches, le journal, les écarts. **Il fait foi.** Lis en particulier l'entrée `fin` de Y3 (auteur D, 2026-11-08 19:21, la plus récente) : les dix tests annoncés, la base mesurée, les huit mutations, les doutes, que tu dois vérifier un par un. Lis aussi l'entrée `fin` des écarts 91 et 92 (auteur D, 2026-11-08 19:11), qui explique le comportement que Y3 fige, et les écarts 88 à 106 (93 fermé par `2e70f09`, 95 fermé par Y3, 94, 98 et 102 à 106 laissés ouverts par Y3 avec leur raison).
2. `docs/ocr-contrat.md` : sections 1 (conventions), 2.1 (`genere`), 3.3 (les quatre lignes de `moteur.py` et `seances.py`, avec les décisions de Y1b, de Y1c et des écarts 91 et 92), 4 (invariants 1, 8, 9, 10, 11, 12, 14 et 15), 6 (T8 à T14).
3. `docs/plan-ocr.md` : section 5.10 (le tableau des risques, les points 3 à 5 et 8), section 8 (critères 10, 13, 14 et 15).
4. Le diff de la tâche. La branche `agent/Y3-D` porte un seul commit au-dessus de `2e70f09` (vérifie avec `git log --oneline -3`). Lance `git diff 2e70f09 HEAD -- tests/test_synchro_ocr.py docs/ocr-avancement.md` et lis-le en entier, puis lis la classe `SynchronisationNative` et `ArgumentsActuels` dans le fichier : c'est l'objet de la revue. Ton propre travail se fait sur une branche `agent/Y3-S` créée à partir de ce commit (règle de `AGENTS.md`).
5. Le code, en lecture seule : dans `moodlesync/moteur.py`, `telecharger` (le début, la boucle de relocalisation, les compteurs, la fin et le compte rendu), `deja_present`, `entree_retrouvee`, `_authentifie`, `marque_du_fichier`, `index_existant`, `repartiteur`, `nom_ancienne_version`, `a_recuperer`, `charger_etat` ; dans `tests/test_synchro_ocr.py`, le banc (`FauxServeur`, `Banc`) et les classes de Y1b et des écarts 91 et 92 ; `tests/test_correctifs.py` (les deux tests de `telecharger` qui existent déjà : `test_telecharger_ne_range_pas_reessaiera`, `test_republication_erronee_garde_l_ancien_fichier`) ; `tests/test_moteur.py` pour le style.
6. `docs/plan-execution-ocr.md` : la phase 3 de la section 4, la ligne Y3 de la section 3, la section 9.

## Étape A : base de tests

Lance `python -m unittest discover -s tests -t . -v`. Note dans le journal le nombre de tests et les éventuels échecs, **tels quels**. La base annoncée par Y3 est verte à **484 tests, 0 échec, 3 ignorés** sur une machine Linux sans Tesseract (474 plus 10 de Y3 ; les 474 venaient de 468 plus les six tests des écarts 91 et 92). Les trois ignorés sont les deux tests de `test_horaire` sans pywebview et T29. Sur une machine Windows avec Tesseract 5.5.3, on attend 0 ignoré. Si elle a bougé, signale-le.

**Faits de la machine de Y3** (mesurés par D le 8 novembre 2026) : Linux, Python 3.14.9, pypdf 6.21.4, Tesseract absent, `pypdfium2` absent. Aucun vrai PDF cherchable n'a été fabriqué ni relu. N'installe rien (confirmation de Maxence obligatoire). Dis dans tes doutes ce que tu n'as pas pu exécuter.

**Fins de ligne.** L'arbre de travail porte 31 fichiers modifiés qui ne sont pas à Y3 (fins de ligne CRLF pour l'essentiel). Ne les normalise pas, ne les inclus pas dans un commit. Fais tes mesures sur un export propre du commit de Y3 (`git archive`), dans un dossier temporaire hors du dépôt.

## Étape B : revue ciblée de Y3

Tu es le relecteur de `tests/test_synchro_ocr.py` (classe `SynchronisationNative`, dix tests, et le test corrigé de l'écart 95) et de l'entrée de journal de Y3. Le contrat fait foi. Cherche, dans cet ordre :

1. **Couverture.** Les neuf cas demandés par le prompt 25 sont-ils présents : nouveau fichier ; deuxième passage ; même nom et même taille dans une autre section du cours (étape 5) ; même contenu sous un autre nom (bloc des jumeaux) ; même document publié dans deux cours ; republication à contenu différent ; date changée à contenu identique ; erreur sur un fichier (invariant 9) ; cours nommé « Textes » (étape 1, écart 100) ? Les valeurs attendues sont-elles celles du code d'aujourd'hui, et pas seulement celles du prompt ? Cherche un cas du prompt qui manque ou qui a été déformé. Le dixième test (`test_marque_d_un_autre_document_a_l_etape_cinq`) remplace le test de l'écart 93 demandé par le prompt, dont les valeurs attendues ne sont plus celles du code : juge ce remplacement au regard de l'écart 106 et de l'invariant 14.
2. **Forme des tests.** Chaque test vérifie-t-il les clés utiles du compte rendu et jamais le compte rendu entier (Y2 y ajoutera `a_preparer` et `republies_generes`) ? La somme `neufs + maj + doublons + generes + erreurs == total` est-elle vérifiée à la fin de chaque passage complet (contrat 3.3) ? Une assertion dépend-elle de la casse ou de la normalisation Unicode de la plateforme ? Y a-t-il un `sleep`, un vrai appel réseau, ou un test qui doublerait ce que couvrent déjà `test_correctifs.py`, les classes de Y1b et des écarts 91 et 92, `tests/test_moteur.py` ou `tests/test_seances.py` ? L'aide `compte` et l'aide `partiels` sont-elles justes ?
3. **Écart 95.** L'assertion est-elle identique sur les deux plateformes, et mord-elle ? Rejoue la mutation : dans `deja_present`, retire la branche `if os.path.normcase(os.path.dirname(p)) == ici: return p` de l'étape 5 ; `test_meme_nom_dans_le_dossier_sans_condition_de_taille` doit échouer. Dis ce que le test prouve sous Linux et ce qu'il ne prouve que par déduction sous Windows.
4. **Écart 93 et écart 106.** Confirme ou conteste la mesure de Y3 : un fichier de l'étape 5 qui porte la marque d'un autre document donne `neufs` 1 et un appel, parce que l'étape 5 écarte tout PDF à marque. Le contrôle d'adresse vit-il bien dans `_authentifie`, et `test_marque_d_un_autre_document_n_authentifie_pas` le couvre-t-il encore après `2e70f09` ? Refais la mutation : retire `m["url"] == cle_url(it["url"])` de `_authentifie` et dis quels tests échouent.
5. **Mutations.** Y3 en annonce huit, huit détectées (M1 à M8, journal `fin`). Refais-en au moins quatre de ton choix, hors dépôt, sur une copie de l'export de Y3, en restaurant le fichier après chacune. Idées : retirer l'étape 1 de `deja_present` ; retirer l'étape 2 ; conserver `genere` à l'étape 5 ; ne pas incrémenter `doublons` après une erreur ; remplacer `nom_ancienne_version` par un nom fixe ; compter `generes` dans `doublons`. Cherche un test qui passerait même si le code était faux (assertion trop faible, doublure qui masque le défaut, valeurs recopiées du code).
6. **Ce que ces tests ne prouvent pas.** Le journal écrit : aucun vrai PDF cherchable de `fabriquer_pdf_cherchable`, aucune vraie synchronisation réseau, Windows et macOS non exécutés, aucune annulation, aucune republication d'un PDF cherchable (écart 88, Y2), aucune durée mesurée. Confirme ou complète cette liste.
7. **Hors périmètre.** Aucun fichier de `moodlesync/`, ni `docs/ocr-contrat.md`, ni `docs/plan-ocr.md`, ni `tests/test_ocr.py` ne doit être touché par le commit de Y3. Les écarts 91, 92, 94, 98, 99, 100, 101, 102, 103, 104 et 105 ne devaient pas être corrigés (91 et 92 le sont déjà par `2e70f09`) ; T8 et T9 sont absents, Y2 s'en charge. Vérifie le diff.
8. **Forme.** Aucun tiret cadratin ni demi-cadratin dans `tests/test_synchro_ocr.py`, `docs/ocr-avancement.md` et le prompt (compte par code de caractère), identifiants Python en français sans accent. Les fichiers du commit sont en LF (zéro retour chariot dans les blobs) ; `git show --stat` du commit ne doit lister que `tests/test_synchro_ocr.py`, `docs/ocr-avancement.md` et `docs/prompts/27-revue-Y3-S.md`.

Ne réécris pas le code et ne le modifie pas. Pour chaque constat : gravité (**bloquant**, **important**, **mineur**), section du contrat ou du plan concernée, le problème en une phrase, la correction proposée en une phrase. Pas de remarque de style. Si tu ne trouves rien dans une catégorie, écris « rien ». Quand tu affirmes un comportement, exécute-le (en lecture seule, dans le dossier temporaire de la session) ou marque-le « déduit ».

Consigne de sortie :
- Écris une entrée de journal de type `revue` pour Y3 (format de la section 5 du journal), avec la liste des constats, et dis si les écarts 95 et 106 se ferment (ils sont déjà marqués fermés par Y3 : confirme ou rouvre) et si l'écart 94 reste bien ouvert.
- S'il y a au moins un **bloquant** : passe Y3 à `rejetée`, ajoute les constats à la section 6 du journal (Écarts ouverts), **arrête-toi après l'étape D** : le prompt que tu prépares est celui de la correction, destiné à DeepSeek v4.1 flash.
- Sinon : passe Y3 à `fait` (Relue : oui, S), ajoute les constats « important » et « mineur » à la section 6, et franchis la porte « Avant Y2 » si sa condition est remplie (Y1 et Y3 à `fait`, test « synchroniser, remplacer, synchroniser : zéro téléchargement » vert ; il l'est, `test_pdf_cherchable_deplace_renomme`). Passe à l'étape D.

## Étape D : clôture et chaînage (obligatoire, dernière étape)

Lecture pour cette tâche : dans le point 2 ci-dessous, « état de C1 » se lit « état de Y3 » (passage à `fait` avec la colonne Relue à `oui`, ou à `rejetée` s'il y a un bloquant), « colonne Relue » se lit « colonne Relue de Y3 » et « entrée de journal (`revue` de C1) » se lit « entrée de journal (`revue` de Y3) » ; la porte « Avant Y2 » de la section 3 est à compléter si Y3 passe à `fait` (la ligne existe, état « non franchie ») ; le point 1 attend la base mesurée à l'étape A, et il faut coller le nombre réel ; le point 4 commite `docs/ocr-avancement.md` et le nouveau prompt. Le reste est recopié sans changement.

1. **Relance la suite complète** et note le résultat réel (elle ne doit pas avoir bougé).
2. **Mets à jour `docs/ocr-avancement.md`** : état de C1, colonne Relue, portes de sortie (section 3), entrée de journal (`revue` de C1), écarts (section 6). Tu n'effaces aucune ligne existante.
3. **Prépare le prompt de l'étape suivante** (règle de choix ci-dessous) et écris-le dans `docs/prompts/NN-<ID>-<S ou D>.md`, où `NN` est le plus grand numéro déjà présent dans `docs/prompts/` plus un.
4. **Commit** (un seul) : `docs/ocr-avancement.md`, le nouveau prompt. Rien d'autre. Pas de push.
5. **Réponds à Maxence** avec le format court : `Fait / Fichiers / Décisions / Doutes / Suivant`, puis le chemin du prompt suivant et la phrase à coller dans la session du destinataire. Tu n'enchaînes pas toi-même la tâche suivante.

### Règle de choix de la tâche suivante

Applique dans cet ordre, la première règle qui donne un résultat :

1. Une tâche à l'état `à relire` (la plus ancienne d'abord) : le prompt suivant est la **revue** de cette tâche, adressée à l'IA qui n'en est **pas** propriétaire. Une tâche terminée ne débloque ses dépendantes qu'une fois relue et `fait`, donc la revue passe avant toute nouvelle tâche.
2. Une tâche `rejetée` : le prompt suivant est la **correction**, adressée à son propriétaire.
3. La première tâche `à faire` ou `bloquée` dont **toutes les dépendances sont `fait`**, adressée à son propriétaire (colonne Proprio). L'ordre est celui de `docs/plan-execution-ocr.md`, section 9, avec E0b placée juste après E0. Si le propriétaire est toi-même, le prompt est écrit à part, pour une session neuve.
4. Aucune tâche prête : il n'y a pas de prompt suivant. Écris à Maxence ce qui bloque (revue manquante, décision à prendre, validation à faire sur macOS) et ce qu'il doit faire.

### Contenu de chaque prompt généré

Un prompt généré reprend la **structure de celui-ci** : Rôle (nom de l'IA destinataire, une tâche, une session) ; Règles non négociables (copie intégrale de la section « Règles non négociables » ci-dessus) ; À lire (le pack de la tâche, selon `docs/plan-execution-ocr.md` section 5, plus le journal et les sections du contrat qui la concernent) ; Étape A (base de tests) ; Étapes de la tâche (contraintes issues des invariants du contrat, livrable exact, test qui doit passer, fichiers qu'elle ne touche pas) ; Étape D de clôture et chaînage, **recopiée mot pour mot, y compris cette règle de choix et cette consigne de contenu**. Cette recopie est ce qui fait tenir la chaîne : un prompt qui ne la contient pas interrompt tout. Pour une tâche d'implémentation, le prompt demande d'abord le test qui échoue, puis le code. Pour une revue, il reprend l'étape B de ce prompt, adaptée aux fichiers et aux invariants du diff. Il n'invente aucune règle absente du contrat ou du journal.

---

Fin du prompt 27.
