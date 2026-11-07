# Prompt 02 pour Claude Sonnet : revue de S1 (le spike)

Auteur du prompt : DeepSeek v4 pro, 7 novembre 2026. Destinataire : Claude Sonnet.
Utilisation : coller ce fichier en entier dans la session de Claude Sonnet, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/02-revue-S1-S.md et exécute-le ».

---

## Rôle

Tu es Claude Sonnet. Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, DeepSeek v4 pro, et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans (OCR avec Tesseract) et d'un mode qui rend un PDF cherchable.

Cette session contient **une seule tâche** : la revue de S1, le spike technique (rapport `docs/spike-ocr.md`) écrit par DeepSeek. Tu ne fais rien d'autre.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\MoodleSync\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole, l'état des tâches, le journal, les écarts. **Il fait foi.**
2. `docs/spike-ocr.md` : le rapport à relire.
3. `docs/ocr-contrat.md`, sections 1 (« Non fixé » : seuils de tolérance du rendu et méthode de la couche de texte, tous deux marqués S1), 3.1 (`executer`, `rendre_page`, `fabriquer_pdf_cherchable`), 4 (invariants 1 et 4, qui dépendent des valeurs S1), 7 (D1 à D7), et la liste « à confirmer ».
4. `docs/plan-ocr.md`, section 7 (lot 0) : le critère de sortie du spike.

## Étape A : base de tests

Lance `python -m unittest discover -s tests -t . -v`. Note dans le journal le nombre de tests et les éventuels échecs, **tels quels**. Le spike n'a pas touché au code : la base ne doit pas avoir bougé (277 tests, 0 échec). Si elle a bougé, signale-le.

## Étape B : revue ciblée de S1 (le rapport de spike)

Tu es le relecteur du rapport écrit par DeepSeek. Cherche, dans cet ordre :

1. **Mesures fausses ou invraisemblables.** Les versions, les temps par page, les comptes d'objets (pages, annotations, liens, signets) et les tailles. Si tu as un shell, relance les mesures les plus risquées (le temps rendu plus reconnaissance, la superposition) dans un environnement virtuel jetable hors du dépôt ; sinon, écris que tu n'as pas pu vérifier, et dis quoi vérifier. Ne reproche pas un point que tu n'as pas vérifié.
2. **Incohérences internes.** Un go ou no-go qui ne découle pas des mesures ; une valeur S1 proposée qui en contredit une autre ; un volet sans réponse ; une décision globale qui ne suit pas la porte de sortie.
3. **Ambiguïtés qui feraient diverger l'implémentation de C4.** La méthode de couche de texte, la tolérance du rendu, la borne de volume.
4. **Choses fragiles.** Une valeur présentée « mesuré » sans l'être, un « non observé » présenté « observé », un « non testé » présenté « testé ».
5. **Contradictions avec le contrat** : les marqueurs S1 de la section 1, les invariants 1 et 4, D1 à D7, ou la porte « Après S1 » (section 3 du journal).

Ne réécris pas le rapport. Ne le modifie pas. Pour chaque constat : gravité (**bloquant**, **important**, **mineur**), volet ou section concernée, le problème en une phrase, la correction proposée en une phrase. Pas de remarque de style. Si tu ne trouves rien dans une catégorie, écris « rien ».

Consigne de sortie :
- Écris une entrée de journal de type `revue` pour S1 (format de la section 5 du journal), avec la liste des constats.
- S'il y a au moins un **bloquant** : passe S1 à `rejetée`, ajoute les constats à la section 6 du journal (Écarts ouverts), **arrête-toi après l'étape D** : le prompt que tu prépares est celui de la correction, destiné à DeepSeek.
- Sinon : passe S1 à `fait` (Relue : oui, S). Les constats « important » et « mineur » vont dans la section 6 du journal. Passe à l'étape D.

## Étape D : clôture et chaînage (obligatoire, dernière étape)

1. **Relance la suite complète** et note le résultat réel (elle ne doit pas avoir bougé).
2. **Mets à jour `docs/ocr-avancement.md`** : états des tâches (E0, S1), colonne Relue, portes de sortie (section 3), entrées de journal (`revue` de S1), écarts (section 6). Tu n'effaces aucune ligne existante.
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

Fin du prompt 02.
