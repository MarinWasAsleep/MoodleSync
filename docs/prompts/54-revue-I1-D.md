# Prompt 54 pour DeepSeek v4.1 flash : revue de I1, installation du moteur à la demande

Auteur du prompt : Claude Sonnet (S), 9 novembre 2026, à la fin de I1 (prompt 53). Destinataire : DeepSeek v4.1 flash (D), dans une **session neuve**. I1 est `à relire` et son propriétaire est S : la revue revient à D, qui n'en est pas propriétaire, et passe avant toute nouvelle tâche (règle de choix, point 1).
Utilisation : coller ce fichier en entier dans la session de D, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/54-revue-I1-D.md et exécute-le ».

---

## Rôle

Tu es DeepSeek v4.1 flash (D). Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, Claude Sonnet (S), et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans et d'un mode qui rend un PDF cherchable. Le moteur d'extraction, la synchronisation, le mixin `ApiTextes`, le contrat et les onglets (U1 à U5) sont écrits et relus.

S a livré I1 (prompt 53) : `installer_paquet` dans `moodlesync/ocr.py` (téléchargement du paquet portable du moteur depuis `MarinWasAsleep/MoodleSync-moteur`, empreinte SHA-256 vérifiée avant toute décompression, décompression atomique dans le dossier des réglages, détection `portable`), `ocr_installer` dans `moodlesync/api_textes.py` (rend `ocr_etat()` après installation), quatre phrases nouvelles, `tests/test_installer_ocr.py` (49 tests) et la mise à jour du contrat. Branche `agent/I1-S`, créée sur `6575023` : `git log --oneline -3 agent/I1-S` doit montrer le commit d'I1 au-dessus de `6575023`.

Cette session contient **une seule tâche** : la revue ciblée de I1 (diff, contrat, tests, journal). Ce n'est pas une refonte et ce n'est pas une correction : tu ne modifies aucun fichier de code, ni test, ni contrat, ni plan, ni plan d'exécution. Les constats s'écrivent, ils ne se corrigent pas.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\\MoodleSync\\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole (section 1) ; la ligne I1 (section 2) ; la porte « Après I1 » (section 3) ; la décision de Maxence du 9 novembre 2026 sur le paquet portable et la ligne « Décision : I1 » (section 4) ; l'entrée `fin` de I1 (la plus récente, auteur S, 20:41) ; les écarts 206, 238 et 242 à 246 (section 6). **Il fait foi.**
2. `docs/ocr-contrat.md` : 3.1 (`installer_paquet`, relis le bloc que I1 a écrit), 3.2 (`ocr_installer`), 4 (invariants 6, 9 et 16), 5 (les quatre lignes nouvelles et le paragraphe qui les suit, mots à éviter), 6 (T31), 7 (D6 révisée).
3. `docs/plan-ocr.md` : 2.6 et 3.3 (paquet portable), 5.9 (sécurité et vie privée). Le plan n'est pas aligné sur D6 révisée (écart 244) : ne le compte pas comme défaut d'I1.
4. `docs/plan-execution-ocr.md` : section 5 (Pack API), section 9.
5. Le diff de la tâche : `git diff 6575023 agent/I1-S -- moodlesync/ocr.py moodlesync/api_textes.py tests/test_api_textes.py docs/ocr-contrat.md`, puis `tests/test_installer_ocr.py` en entier. Ton propre travail se fait sur une branche `agent/revue-I1-D` créée à partir du commit d'I1.
6. Pour comparer, en lecture : `moodlesync/maj.py` (le modèle de confiance, `ouvrir`, `lire_json`, `hote_autorise`, `telecharger`), `tests/test_maj.py` (doublure du réseau), `tests/test_ocr.py` lignes 689 à 695 et 2868 à 2887 (la garde qui interdit « urllib » et « socket » dans `ocr.py`).

Ne relis pas les tâches antérieures : le journal les résume.

## Étape A : base de tests

Lance `python -m unittest discover -s tests -t .` avec `/opt/data/cache/scratch/venv-ms/bin/python` (pywebview 6.2.1, Pillow, pypdf, pypdfium2, Node 26) sur la copie de travail de `agent/I1-S` et note le résultat **tel quel**. La base annoncée est **798 tests, 0 échec, 1 ignoré**, mesurée par S à la fin d'I1 (749 plus les 49 de `tests/test_installer_ocr.py`). Si elle a bougé, signale-le.

**Faits de la machine** : Linux, Python 3.14.9, aucun navigateur, aucune vraie fenêtre pywebview, Tesseract absent. N'installe rien et ne télécharge rien de réel pendant la session.

## Étape B : la revue

**Ce qui est conforme à vérifier et à mesurer.** (1) L'empreinte : `EMPREINTE_PAQUET` est une constante du code, comparée avant que `zipfile.ZipFile` s'ouvre, jamais lue dans la réponse du serveur ; un fichier différent est supprimé. (2) Le réseau : `ocr.py` ne contient ni « urllib » ni « socket » (compte-les), le seul réseau passe par `maj.py`, aucun appel pendant l'extraction (invariant 6) ; rejoue la suite avec la résolution de noms et les connexions interdites. (3) La décompression : tout nom d'entrée est vérifié avant la première écriture (chemin absolu, de lecteur, `..`, antislash, octet nul, deux-points, lien symbolique), le dossier cible est un dossier temporaire voisin puis un renommage, l'ancienne installation revient si le renommage échoue, aucun dossier à moitié écrit après un arrêt, une erreur ou un disque plein. (4) Les phrases : les quatre codes nouveaux sont identiques dans `ocr.MESSAGES` et dans la table du contrat 5, aucun des sept mots interdits ; aucune phrase n'est écrite hors de `ocr.MESSAGES` ; aucune trace technique ne sort (invariant 9). (5) `ocr_installer` : moteur déjà détecté, `ocr_etat()` sans requête ; succès, `ocr_etat()` avec sa clé `moteur` (écart 238) ; erreur et annulation relayées telles quelles ; la phrase va au journal ; seul `ocr_installer` change dans `api_textes.py` et seules deux lignes changent dans `tests/test_api_textes.py` (338 et 1749). (6) Le périmètre : aucun fichier de l'interface n'est touché, aucun fichier hors de la liste de la ligne I1, les fichiers touchés sont en LF, aucun tiret long. (7) Le consentement : `ocr_installer` n'exige pas `ocr` (décision de S, section 4) : dis si la décision tient au regard de l'invariant 16 et de la carte, qui offre « Installer » avant tout consentement.

**Ce qui doit être cherché.** Les cas où le test passe pour une mauvaise raison : une doublure de `maj.ouvrir` plus permissive que la vraie (la vraie refuse les hôtes hors GitHub et suit les redirections), une assertion qui ne distingue pas le bon comportement du mauvais, un `tearDown` qui ne voit pas un appel réseau avalé par `except`, une doublure de `detecter` qui rend « présent » pour une mauvaise raison. Cherche aussi, dans le code : un chemin qui laisse un `.part` ou un dossier temporaire, un cas où le verrou n'est pas relâché, une erreur de disque classée comme erreur réseau (le classement repose sur `ConnectionError`, `TimeoutError` et les attributs `reason` et `code`), une valeur de `taille` de la release qui trompe la barre de progression, un comportement propre à Windows (renommage d'un dossier tenu ouvert, noms réservés, longueur de chemin, `os.chmod`), un `commonpath` qui lève sur deux lecteurs. Rejoue **au moins vingt mutations** sur une copie hors dépôt, dont celles qui touchent la comparaison d'empreinte, la validation des noms, le renommage, la restauration de l'ancienne installation, le verrou, le journal et la forme rendue par `ocr_installer`.

**Ce qui doit être jugé.** Les écarts 242 à 246 ouverts par S : dis pour chacun s'il est exact, s'il doit être fermé, reclassé ou renvoyé à une décision de Maxence. L'écart 243 pose une question : la garde de `tests/test_ocr.py` qui interdit « urllib » et « socket » dans tout le texte d'`ocr.py` est-elle une règle voulue, et le passage par `maj.py` convient-il ? Les doutes (1) à (8) de l'entrée `fin` d'I1 : dis lesquels tiennent. Tu confirmes ou tu corriges les chiffres de l'entrée `fin` (49 tests, `FAILED (failures=1, errors=49)` sur `6575023`, 26 mutations, zéro connexion) en les mesurant.

**Ordre imposé : le test qui échoue d'abord, s'applique à S, pas à toi.** Tu ne corriges rien.

**Livrable.** Une entrée `revue` de I1 dans le journal : ce qui est conforme, les constats numérotés (bloquant, important, mineur), les mesures, les mutations rejouées et leur résultat, l'effet de chaque écart sur ce que l'étudiant voit. Verdict : `bloquant`, `important`, `mineur` ou `rien`.

**Test qui doit passer.** La suite complète, et `tests/test_installer_ocr.py` seul. Si un test ne passe pas, c'est un constat, pas une correction de ta part.

## Étape D : clôture et chaînage (obligatoire, dernière étape)

Lecture pour cette tâche : dans le point 2 ci-dessous, « état de U5 » se lit « état de I1 » (passage à `fait`, ou à `rejetée` si ton verdict est bloquant), « colonne Relue » se lit « colonne Relue de I1 » et « entrée de journal (`revue` de U5) » se lit « entrée de journal (`revue` de I1) ». La porte « Après I1 » existe : confirme-la, corrige-la, ou laisse-la non franchie ou sous réserves en complétant sa liste ; c'est ta revue qui tranche. La règle de choix s'applique une fois I1 relue. Si I1 passe à `fait`, aucune tâche n'est `à relire` ni `rejetée` et la première tâche prête est **P1** (dépendances, PyInstaller, builds ; C1 à C5 sont `fait`), propriétaire D : comme le propriétaire est toi-même, le prompt est écrit à part pour une session neuve. Viennent ensuite P2 à P4 dans l'ordre du plan d'exécution, section 9. Les écarts 240 (API), 242, 245 et 246 attendent une décision ou une action de Maxence : dis-le dans ta réponse, ce ne sont pas des tâches du tableau. Si I1 est `rejetée`, la tâche suivante est la correction d'I1, adressée à S.

1. **Relance la suite complète** et note le résultat réel (elle ne doit pas avoir bougé).
2. **Mets à jour `docs/ocr-avancement.md`** : état de U5, colonne Relue, portes de sortie (section 3), entrée de journal (`revue` de U5), écarts (section 6). Tu n'effaces aucune ligne existante.
3. **Prépare le prompt de l'étape suivante** (règle de choix ci-dessous) et écris-le dans `docs/prompts/NN-<ID>-<S ou D>.md`, où `NN` est le plus grand numéro déjà présent dans `docs/prompts/` plus un.
4. **Commit** (un seul) : `docs/ocr-avancement.md` et le nouveau prompt. Rien d'autre. Pas de push.
   Cette tâche est une revue, sans code : sa liste ne cite que le journal et le prompt suivant.
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

Fin du prompt 54.
