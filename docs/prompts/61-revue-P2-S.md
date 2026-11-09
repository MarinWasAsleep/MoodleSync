# Prompt 61 pour Claude Sonnet : revue de P2, tests et CI avec Tesseract facultatif

Auteur du prompt : Claude Sonnet (S), 9 novembre 2026, à la fin de la revue de P1 (branche `agent/revue-P1-S`). Destinataire : Claude Sonnet (S), dans une **session neuve**. P2 est `à relire` et son propriétaire est D : la revue revient à S, qui n'en est pas propriétaire, et passe avant toute nouvelle tâche (règle de choix, point 1). P1 est `fait` (verdict important, entrée `revue` du 9 novembre 2026 à 23:20).

Utilisation : coller ce fichier en entier dans la session de S, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/61-revue-P2-S.md et exécute-le ».

---

## Rôle

Tu es Claude Sonnet (S). Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, DeepSeek v4.1 flash (D), et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans et d'un mode qui rend un PDF cherchable. Le moteur, la synchronisation, le mixin `ApiTextes`, l'installation du moteur, le contrat, l'interface et l'empaquetage (P1, relue) sont écrits et relus.

D a livré P2 (prompt 58) : `tests/test_ci.py` (nouveau, 17 tests qui lisent les fichiers et n'exécutent aucun workflow), la correction de la garde de T29 dans `tests/test_ocr.py` (`_moteur_reel` ne protège plus l'import de Pillow, écart 261), et une CI inchangée (`.github/workflows/compilation.yml`), la mesure disant que ses assertions minimales étaient déjà tenues. Le commit de P2 est `3ed0ce3` (`git log -1 3ed0ce3`), au-dessus de `9e159c8` (P1).

Cette session contient **une seule tâche** : la revue ciblée de P2 (diff, tests, workflow, journal). Ce n'est pas une refonte et ce n'est pas une correction : tu ne modifies aucun fichier de code, ni test, ni `requirements*.txt`, ni `MoodleSync.spec`, ni `.github/workflows/compilation.yml`, ni contrat, ni plan. Les constats s'écrivent, ils ne se corrigent pas.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\\MoodleSync\\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole (section 1) ; la ligne P2 (section 2) ; la porte « Après P2 » et les deux lignes « Après P1 » (section 3) ; l'entrée `fin` de P2 (section 5, 2026-11-09 22:48) ; l'entrée `revue` de P1 (2026-11-09 23:20) pour ses constats qui touchent P2 ; les écarts 18, 261, 262, 263, et 264 à 269 (section 6). **Il fait foi.**
2. `docs/plan-execution-ocr.md` : section 3 (la ligne P2 : fichiers, dépendances, critère de sortie « tests hors ligne verts, tests OCR ignorés sans moteur »), section 5 (Pack packaging), section 9.
3. `docs/ocr-contrat.md` : la ligne de T29 dans la table des tests (cherche `T29`), et rien d'autre.
4. `.github/workflows/compilation.yml` en entier, `tests/test_ci.py` en entier (nouveau en P2), `requirements.txt` et `requirements-testes.txt`, et dans `tests/test_ocr.py` la fonction `_moteur_reel` et la classe `MoteurReel` (T29).
5. Le diff de la tâche : `git diff 9e159c8 3ed0ce3 -- tests/ .github/`. Ton propre travail se fait sur une branche `agent/revue-P2-S` créée sur le commit de la revue de P1 (`git log -1 agent/revue-P1-S`).

Ne relis pas les tâches antérieures : le journal les résume. Ne relis pas le code du moteur, de l'installation ni de l'interface : ce n'est pas ta tâche.

## Étape A : base de tests

Lance `/opt/data/cache/scratch/venv-ms/bin/python -m unittest discover -s tests -t .` sur la copie de travail de ta branche `agent/revue-P2-S` et note le résultat **tel quel**. La base annoncée est **832 tests, 0 échec, 1 ignoré** (mesurée au début et à la fin de la revue de P1, la revue ne touchant que le journal et un prompt).

**Faits de la machine** : Linux, Python 3.14.9, Node 26.12.1, Tesseract absent, PyYAML absent, aucun Windows et aucun macOS, PyInstaller absent du venv. Le venv `venv-ms` ne contient ni Pillow, ni pypdf, ni certifi : l'interpréteur les trouve par la variable `PYTHONPATH` ambiante, qu'il ne faut pas écraser (écart 269 ; sans elle, 591 tests et 34 échecs ou erreurs). Aucun workflow ne peut être lancé d'ici : ce qui se mesure est le contenu des fichiers et la suite locale.

## Étape B : la revue

**Ce qui est conforme à vérifier et à mesurer.** (1) `tests/test_ci.py` : les 17 tests lisent le bon fichier, chaque assertion distingue le bon état du mauvais ; la lecture du job `tests` par indentation (jobs à deux espaces, étapes à six) échoue avec un message clair sur une autre mise en page. (2) La CI est inchangée : `git diff 9e159c8 3ed0ce3 -- .github` doit être vide ; refais toi-même les cinq assertions minimales sur le workflow (job `tests` sur `ubuntu-latest` et `windows-latest`, installation de `requirements-testes.txt` avant la suite, commande `python -m unittest discover -s tests -t .`, ni Tesseract ni tessdata nommés, `fail-fast: false`) et dis si l'affirmation « déjà tenues » est exacte. (3) La garde de T29 : `_moteur_reel` n'enveloppe plus `import PIL` d'un `try/except ImportError` ; la raison de la garde nomme Tesseract ; refais la sonde `sys.modules["PIL"] = None` hors dépôt. (4) Inventaire des tests ignorés : suite entière avec `-v`, un seul ignoré, sa raison. (5) Mutations : rejoue **au moins douze mutations** hors dépôt sur `tests/test_ci.py` et sur la garde de T29 (matrice sans `windows-latest`, installation retirée, suite avant l'installation, Tesseract installé dans le job `tests`, CRLF ou tiret long dans le workflow, raison de garde sans le mot node ou Tesseract, garde retirée, `import PIL` reprotégé, un `skipUnless` sans raison, un job `tests` déplacé hors de `pull_request`, etc.) et compte les détectées et les survivantes, avec un témoin sans mutation. (6) Forme et périmètre : `git show --stat 3ed0ce3` ne touche que `tests/test_ci.py`, `tests/test_ocr.py`, `docs/ocr-avancement.md` et `docs/prompts/59-revue-P1-S.md` ; fichiers neufs en LF, sans tiret long ni demi-cadratin ; ni `Co-Authored-By` ni mention d'IA.

**Ce qui doit être cherché.** Le même défaut que l'écart 265 : une garde de fins de ligne qui lit l'arbre de travail et échouerait sous Windows (`core.autocrlf`), ici pour `.github/workflows/compilation.yml` et `tests/test_ci.py`. Un test qui passe pour une mauvaise raison (assertion lue sur un commentaire, test YAML qui ne vérifie rien faute de PyYAML, écart 262). Un `skipUnless` dont la raison ne dit pas la vérité. La clé de cache de `setup-python` (`cache-dependency-path: requirements-testes.txt`) ne couvre pas `requirements.txt`, que `requirements-testes.txt` inclut par `-r` : dis si c'est un défaut de correction ou seulement de rapidité. Toute affirmation de l'entrée `fin` de P2 que tu ne peux pas reproduire.

**Ce qui doit être jugé.** La porte « Après P2 » (tests hors ligne verts, tests OCR ignorés sans moteur) : dis ce que la revue peut en conclure sur cette machine et ce qui reste à mesurer sur les exécuteurs de GitHub, sans accorder la porte à la place de la mesure. L'écart 261 (fermé par P2 : exact ? bien fermé ?), les écarts 262 et 263 (exacts, à reclasser ou à fermer ?), l'écart 18 (confirmation visuelle de l'absence de console, laissé à P4). Les doutes de l'entrée `fin` de P2 : lesquels tiennent. Confirme ou corrige les chiffres de cette entrée (17 tests, `Ran 16 tests` puis `FAILED (failures=1)` au premier passage de D, 815 puis 832 tests, 15 mutations détectées sur 15) en les mesurant.

**Livrable.** Une entrée `revue` de P2 dans le journal : ce qui est conforme, les constats numérotés (bloquant, important, mineur) à partir de l'écart 270, les mesures, les mutations rejouées et leur résultat, l'effet de chaque écart sur ce que voit l'étudiant ou sur ce qui sera publié. Verdict : `bloquant`, `important`, `mineur` ou `rien`.

**Test qui doit passer.** La suite complète, et `tests/test_ci.py` seul. Si un test ne passe pas, c'est un constat, pas une correction de ta part.

## Étape D : clôture et chaînage (obligatoire, dernière étape)

Lecture pour cette tâche : dans le point 2 ci-dessous, « état de P2 » se lit « état de P2 » (passage à `fait`, ou à `rejetée` si ton verdict est bloquant), « colonne Relue » se lit « colonne Relue de P2 » et « entrée de journal (`fin` de P2) » se lit « entrée de journal (`revue` de P2) ». La porte « Après P2 » existe : confirme-la, corrige-la, ou laisse-la sous réserves en complétant sa liste. La porte « Après P1 » est tranchée par la revue de P1 : elle n'est pas à toi. Aucune tâche n'est alors `à relire` : la règle de choix donne le point 3. Si P2 passe à `fait`, la tâche suivante est P3 (documentation et exception `remplacer`, propriétaire D), dont les dépendances (P1 et P2 relues) sont alors tenues. **Un prompt P3 existe déjà** : `docs/prompts/60-P3-D.md`, écrit par l'orchestrateur le 9 novembre 2026 (commit `1ceb26e`, branche `agent/P3-D`), avant la revue de P2 et sans la recopie de l'étape D, ce qui interrompt la chaîne. Ne l'écrase pas : lis-le, puis écris le prompt P3 conforme `docs/prompts/NN-P3-D.md` (NN : le plus grand numéro déjà présent plus un) qui reprend son contenu, ajoute la structure de ce prompt (règles, étape A, étape D recopiée) et tient compte des écarts 264 (version de pypdfium2 retirée de PyPI), 265 (tests de fins de ligne) et 266 (limite macOS 11 et 12, à écrire avec les mots exacts de l'écart), sans promettre ce que la documentation ne peut pas mesurer. Si P2 est `rejetée`, la tâche suivante est la correction de P2, adressée à D. Vient ensuite P4 (audit final, propriétaire S). Les écarts 242, 244, 246 et 253 attendent une décision ou une action de Maxence, et les écarts 264 (version de pypdfium2 à retenir) et 265 (assertions de fins de ligne, `.gitattributes`) aussi : dis-le dans ta réponse, ce ne sont pas des tâches du tableau. Les écarts 254 à 263 et 266 à 269 sont mineurs.

1. **Relance la suite complète** et note le résultat réel.
2. **Mets à jour `docs/ocr-avancement.md`** : état de P2, colonne Relue, portes de sortie (section 3), entrée de journal (`fin` de P2), écarts (section 6). Tu n'effaces aucune ligne existante.
3. **Prépare le prompt de l'étape suivante** (règle de choix ci-dessous) et écris-le dans `docs/prompts/NN-<ID>-<S ou D>.md`, où `NN` est le plus grand numéro déjà présent dans `docs/prompts/` plus un.
4. **Commit** (un seul) : les fichiers de la tâche, `docs/ocr-avancement.md` et le nouveau prompt. Rien d'autre. Pas de push. Vérifie `git show --stat` après le commit : il ne doit lister que ces fichiers.
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

Fin du prompt 61.
