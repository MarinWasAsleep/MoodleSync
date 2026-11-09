# Prompt 59 pour Claude Sonnet : revue de P1, dépendances, PyInstaller et builds

Auteur du prompt : DeepSeek v4.1 flash (D), 9 novembre 2026, à la fin de P2 (branche `agent/P2-D`). Destinataire : Claude Sonnet (S), dans une **session neuve**. P1 est `à relire` et son propriétaire est D : la revue revient à S, qui n'en est pas propriétaire, et passe avant toute nouvelle tâche (règle de choix, point 1). P2 est aussi `à relire` et sa revue viendra après celle de P1, adressée à S.

Utilisation : coller ce fichier en entier dans la session de S, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/59-revue-P1-S.md et exécute-le ».

---

## Rôle

Tu es Claude Sonnet (S). Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, DeepSeek v4.1 flash (D), et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans et d'un mode qui rend un PDF cherchable. Le moteur, la synchronisation, le mixin `ApiTextes`, l'installation du moteur (`installer_paquet`, `ocr_installer`), le contrat et l'interface sont écrits et relus.

D a livré P1 (prompt 57) : `requirements.txt` épingle `pypdfium2==5.15.1` et `pillow==13.0.0` avec les limites de plateforme écrites en commentaire, `MoodleSync.spec` déclare `pypdfium2`, `pypdfium2_raw`, `PIL`, `PIL.Image`, `PIL.ImageOps` et `PIL.ImageChops` dans `hiddenimports` en gardant `pypdf` et le `certifi` de macOS, `requirements-testes.txt` ne dit plus que Pillow n'est pas nécessaire au produit, `tests/test_empaquetage.py` est nouveau (10 tests qui lisent ces fichiers). Branche `agent/P1-D` créée sur `cbe3552` : `git log --oneline -3 agent/P1-D` doit montrer le commit de P1 au-dessus de `cbe3552`.

Cette session contient **une seule tâche** : la revue ciblée de P1 (diff, fichiers de compilation, tests, journal). Ce n'est pas une refonte et ce n'est pas une correction : tu ne modifies aucun fichier de code, ni test, ni `requirements*.txt`, ni `MoodleSync.spec`, ni `.github/workflows/compilation.yml`, ni contrat, ni plan. Les constats s'écrivent, ils ne se corrigent pas.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\\MoodleSync\\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole (section 1) ; la ligne P1 (section 2) ; la porte « Après P1 » (section 3) ; l'entrée `fin` de P1 (section 5, 2026-11-09 22:31) ; les écarts 17, 43, 260, 261 et 262 (section 6). **Il fait foi.** L'entrée `fin` de P2 et la porte « Après P2 » sont hors de ta revue : elles décrivent la tâche suivante, pas P1.
2. `docs/plan-execution-ocr.md` : section 3 (la ligne P1 : fichiers, dépendances, critère de sortie « exe Windows et app macOS démarrent »), section 5 (Pack packaging), section 9.
3. `docs/ocr-contrat.md` : 3.1 (ce que le contrat dit des imports à l'usage d'`ocr.py`) et 7 (D11 : `pypdfium2` en import paresseux). Ne relis pas les autres sections.
4. `requirements.txt`, `requirements-testes.txt`, `requirements-compilation.txt` et `MoodleSync.spec`, en entier.
5. `.github/workflows/compilation.yml`, en entier : c'est lui qui installe `requirements-testes.txt`, lance la suite et appelle `pyinstaller --noconfirm --clean MoodleSync.spec`.
6. `tests/test_empaquetage.py` en entier (nouveau en P1).
7. Le diff de la tâche : `git diff cbe3552 agent/P1-D -- requirements.txt requirements-testes.txt MoodleSync.spec tests/test_empaquetage.py`. Ton propre travail se fait sur une branche `agent/revue-P1-S` créée sur `9e159c8` (le commit de P1, `git log -1 agent/P1-D`).

Ne relis pas les tâches antérieures : le journal les résume. Ne relis pas le code du moteur, de l'installation ni de l'interface : ce n'est pas ta tâche.

## Étape A : base de tests

Lance `/opt/data/cache/scratch/venv-ms/bin/python -m unittest discover -s tests -t .` sur la copie de travail de ta branche `agent/revue-P1-S` et note le résultat **tel quel**. La base annoncée sur le commit de P1 est **815 tests, 0 échec, 1 ignoré** (mesurée par D à la fin de P1, puis au début de P2). Si tu crées ta branche sur `agent/P2-D` au lieu de `9e159c8`, la base devient **832 tests** et les 17 tests de `tests/test_ci.py` sont ceux de P2, hors de ta revue ; dis alors laquelle des deux bases tu as mesurée.

**Faits de la machine** : Linux, Python 3.14.9, Node 26.12.1, Tesseract absent, `pypdfium2` 5.15.1, `pillow` 13.0.0 et `pypdf` 6.21.4 dans le venv `venv-ms`, PyInstaller absent du venv, aucun Windows et aucun macOS, PyYAML absent. La CI de GitHub ne peut pas être lancée d'ici et aucun exécutable ne peut être fabriqué : ce qui se mesure ici est le contenu des fichiers, les métadonnées PyPI et la roue de `pyinstaller-hooks-contrib`, pas un bundle. Tu peux télécharger des roues hors du dépôt (dans `/opt/data/cache/scratch/`), jamais les installer dans le venv du dépôt.

## Étape B : la revue

**Ce qui est conforme à vérifier et à mesurer.** (1) `requirements.txt` : les deux lignes ajoutées épinglent une version exacte, sans marqueur de plateforme ; les versions existent sur PyPI et les fichiers publiés contiennent bien les roues annoncées par l'entrée `fin` de P1 (win32, win_amd64, win_arm64, manylinux, macosx_13_0 arm64 et x86_64 pour `pypdfium2`, aucune source ; roues Windows, Linux et macOS pour Pillow), `requires_python` de Pillow compatible avec le Python 3.12 des trois jobs de compilation ; le commentaire sur la limite macOS 13 et 12 est exact et ne promet rien que pip ne tienne. (2) `MoodleSync.spec` : les `hiddenimports` couvrent ce que les imports à l'usage d'`ocr.py` cachent à PyInstaller (D11), `pypdf` et le `certifi` de macOS sont gardés, le fichier compile, et rien d'autre n'y a changé que ce que P1 annonce. (3) Les hooks : `pyinstaller-hooks-contrib==2026.9` porte bien `hook-pypdfium2.py` et `hook-pypdfium2_raw.py`, et `collect_dynamic_libs("pypdfium2_raw")` couvre réellement l'emplacement de la bibliothèque pdfium dans la roue de `pypdfium2 5.15.1` (lis la roue : où est la bibliothèque, sous quel nom, et le hook la prend-il). Dis si `hiddenimports` suffit pour les données non importables (par exemple `version.json`) ou si le hook les collecte. (4) `tests/test_empaquetage.py` : les 10 tests lisent les bons fichiers, chaque assertion distingue le bon état du mauvais, et le fichier est en LF sans tiret long. Rejoue **au moins dix mutations** hors dépôt : retirer `pypdfium2` ou `pillow` de `requirements.txt`, y ajouter un marqueur de plateforme, retirer `pypdfium2_raw` ou `PIL` des `hiddenimports`, retirer le bloc `certifi` de macOS, remettre la phrase « n'est pas necessaire au produit » dans `requirements-testes.txt`, passer un de ces fichiers en CRLF, ajouter un tiret long. Compte les détectées et les survivantes. (5) La forme et le périmètre : les quatre fichiers touchés sont en LF, sans tiret long ni demi-cadratin ; le commit de P1 ne touche que `requirements.txt`, `requirements-testes.txt`, `MoodleSync.spec`, `tests/test_empaquetage.py`, `docs/ocr-avancement.md` et `docs/prompts/58-P2-D.md` ; aucune mention d'IA ni `Co-Authored-By`. (6) `requirements-testes.txt` : Pillow y reste listée pour les tests avec la même version, `-r requirements-compilation.txt` est inchangé, et le fichier ne contredit plus le produit. (7) L'écart 260 (`requirements-compilation.txt`, ligne `pillow==13.0.0 ; sys_platform == "darwin"`) : dis si P1 a eu raison de ne pas y toucher et si la justification de l'écart tient.

**Ce qui doit être cherché.** Les cas où le test passe pour une mauvaise raison : une assertion qui lit un commentaire au lieu d'une exigence, un test qui accepterait un marqueur de plateforme, un `hiddenimports` lu sans vérifier que le module est importable dans le venv. Cherche aussi dans les fichiers : un paquet qui ne suivra pas dans l'exe alors que P1 le croit embarqué (données, bibliothèque hors du dossier du module, sous-paquet dynamique), un `hiddenimport` inutile qui gonfle le bundle, une version de Pillow ou de `pypdfium2` incompatible avec le PyInstaller épinglé (`pyinstaller==6.22.3`, `pyinstaller-hooks-contrib==2026.9`), une limite macOS 11 et 12 qui casse `pip install -r requirements.txt` au lieu de seulement désactiver le rendu, et toute affirmation de l'entrée `fin` de P1 que tu ne peux pas reproduire.

**Ce qui doit être jugé.** La porte « Après P1 » demande que l'exe Windows et l'app macOS démarrent : dis ce que la revue peut en conclure sur cette machine et ce qui reste à mesurer par Maxence, sans accorder la porte à la place de la mesure. Les écarts 17, 43 et 260 : dis pour chacun s'il est exact, s'il doit être fermé, reclassé ou renvoyé à une décision de Maxence. L'écart 261 (garde de T29, corrigé par P2) et l'écart 262 (PyYAML absent) appartiennent à P2 : ne les traite pas, cite-les seulement si P1 en est la cause. Les doutes de l'entrée `fin` de P1 : dis lesquels tiennent. Tu confirmes ou tu corriges les chiffres de cette entrée (10 tests, `FAILED (failures=8)` sur `cbe3552`, 815 tests, 0 échec, 1 ignoré) en les mesurant.

**Ordre imposé : le test qui échoue d'abord, s'applique à D, pas à toi.** Tu ne corriges rien.

**Livrable.** Une entrée `revue` de P1 dans le journal : ce qui est conforme, les constats numérotés (bloquant, important, mineur), les mesures, les mutations rejouées et leur résultat, l'effet de chaque écart sur ce que voit l'étudiant ou sur ce qui sera publié. Verdict : `bloquant`, `important`, `mineur` ou `rien`.

**Test qui doit passer.** La suite complète, et `tests/test_empaquetage.py` seul. Si un test ne passe pas, c'est un constat, pas une correction de ta part.

## Étape D : clôture et chaînage (obligatoire, dernière étape)

Lecture pour cette tâche : dans le point 2 ci-dessous, « état de P2 » se lit « état de P1 » (passage à `fait`, ou à `rejetée` si ton verdict est bloquant), « colonne Relue » se lit « colonne Relue de P1 » et « entrée de journal (`fin` de P2) » se lit « entrée de journal (`revue` de P1) ». La porte « Après P1 » existe et c'est ta revue qui la tranche : confirme-la, corrige-la, ou laisse-la non franchie ou sous réserves en complétant sa liste. La porte « Après P2 » a déjà été franchie sous réserves par P2 : elle n'est pas à toi. La règle de choix s'applique une fois P1 relue. Si P1 passe à `fait`, la plus ancienne tâche `à relire` devient P2 (propriétaire D) : le prompt suivant est la **revue de P2**, adressée à S, et il doit dire ce que P2 a livré (`tests/test_ci.py`, la garde de T29 corrigée, une CI inchangée). Si P1 est `rejetée`, la tâche suivante est la correction de P1, adressée à D. Viennent ensuite P3 (documentation et exception `remplacer`, propriétaire D) puis P4 (audit final, propriétaire S), dans l'ordre de la section 9 du plan d'exécution. Les écarts 242 (deux paquets du moteur, un par système), 244 (plan non aligné), 246 (empreinte et nom d'actif à inscrire dans le code) et 253 (installer depuis le groupe de réglages) attendent une décision ou une action de Maxence : dis-le dans ta réponse, ce ne sont pas des tâches du tableau. Les écarts 254 à 263 sont mineurs.

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

Fin du prompt 59.
