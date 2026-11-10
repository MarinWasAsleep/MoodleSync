# Prompt 64 pour DeepSeek v4.1 flash : revue de P4, audit final des 16 critères

Auteur du prompt : Claude Sonnet (S), 10 novembre 2026, à la fin de P4 (branche `agent/P4-S`). Destinataire : DeepSeek v4.1 flash (D), dans une **session neuve**. P4 est `à relire` et son propriétaire est S : la revue revient à D, qui n'en est pas propriétaire, et passe avant toute nouvelle tâche (règle de choix, point 1).

Utilisation : coller ce fichier en entier dans la session de D, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/64-revue-P4-D.md et exécute-le ».

---

## Rôle

Tu es DeepSeek v4.1 flash (D). Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, Claude Sonnet (S), et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans et d'un mode qui rend un PDF cherchable. Toutes les tâches de code et de documentation sont livrées et relues ; il ne reste que l'audit final.

S a livré P4 : l'audit des 16 critères d'acceptation du plan (`docs/plan-ocr.md`, section 8). Son rapport est l'entrée `fin` de P4 du 10 novembre 2026 à 00:47 dans `docs/ocr-avancement.md` (section 5), avec les écarts 292 à 294 (section 6), la ligne « Avant P4 (audit) » (section 3) et la ligne P4 (section 2). La branche est `agent/P4-S` (`git log -1 agent/P4-S`), créée sur `eac2d04`.

Cette session contient **une seule tâche** : la revue ciblée de P4. Ce n'est pas une refonte, pas une correction et pas un second audit complet : tu relances les tests que le rapport cite, tu vérifies que le rapport dit vrai, tu écris tes constats. Tu ne modifies aucun fichier de code, de test, de contrat, de plan ni de documentation ; seuls `docs/ocr-avancement.md` (entrée `revue`, état de P4, colonne Relue, portes, écarts) et, si la règle de choix l'exige, un prompt suivant peuvent changer.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\\MoodleSync\\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.
- La documentation ne promet rien qui ne soit mesuré. Une limite annoncée vaut mieux qu'une promesse fausse.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole (section 1) ; les lignes de P3 et de P4 (section 2) ; les lignes « Après P1 », « Après P2 » et « Avant P4 » (section 3, y compris « Avant P4 (audit) ») ; l'entrée `fin` de P4 (section 5, en haut) ; les écarts 253, 276, 281, 287, 292, 293 et 294 (section 6). **Il fait foi.**
2. `docs/plan-ocr.md` : section 8, sous-section « Critères d'acceptation » (16 critères).
3. `docs/ocr-contrat.md` : section 6, le tableau T1 à T32 et la ligne « Critères d'acceptation du plan (8.) vers tests ».
4. Les tests que le rapport nomme, dans `tests/`, et le code seulement là où le rapport dit « lu dans le code » (par exemple l'absence d'appel de `ocr_pdf_restaurer` dans `moodlesync/interface/`, ligne 332 de `moodlesync/interface/app.js`).

Ne relis pas les tâches antérieures : le journal les résume.

## Étape A : base de tests

Sur ta branche `agent/revue-P4-D`, créée sur le commit de P4 (`git log -1 agent/P4-S`), lance `/opt/data/cache/scratch/venv-ms/bin/python -m unittest discover -s tests -t .` et note le résultat **tel quel**. La base annoncée est **866 tests, 0 échec, 1 ignoré** (T29, `tests.test_ocr.MoteurReel.test_moteur_reel`, raison « Tesseract absent : reconnaissance reelle non executee »). Ne pas écraser la variable `PYTHONPATH` ambiante (écart 269). Aucun workflow ne peut être lancé d'ici.

## Étape B : la revue

1. **Tests cités.** Pour chacun des 16 critères, relance seuls (`python -m unittest tests.test_xxx.Classe.methode`) les tests que la ligne du tableau cite, et compare le résultat au rapport. Pour le critère 10, la suite entière suffit. Dis si un nom de méthode ou de classe cité n'existe pas.
2. **Aucun critère `tenu` sur un test ignoré.** Vérifie que les critères marqués `tenu` (5, 7, 8, 14, 15) ne reposent ni sur T29 ni sur un test ignoré (liste des ignorés : suite entière avec `-v`, un seul attendu), et que chaque test cité par ces cinq lignes reproduit la phrase du critère. Dis lesquels des cinq mériteraient `tenu sous réserves`.
3. **Critère 3 (durée).** Le rapport cite une mesure hors dépôt (`p4/duree.py`, Linux, une page native 0,57 à 1,03 s au premier appel du processus, 20 pages 0,08 s). Refais une mesure équivalente, hors dépôt, et dis si l'ordre de grandeur est confirmé ; ne remplace pas le classement `tenu sous réserves` sans raison mesurée.
4. **Critère 12.** Vérifie par recherche dans `moodlesync/interface/` qu'aucun fichier n'appelle `ocr_pdf_restaurer` (écart 294), que la liste `#r-tx-ocr-pdf` permet de choisir le mode `remplacer` (écart 276), et dis si le classement `non tenu` est exact.
5. **Écart 292.** Vérifie à la ligne 332 de `moodlesync/interface/app.js` que le bouton « Installer » des réglages n'a ni barre ni annulation, que `ocr_installer_annuler` n'est appelé que dans `moodlesync/interface/sync.js`, et dis si la décision du 9 novembre 2026 (section 4) est bien celle que la ligne décrit.
6. **Écart 293.** Vérifie par recherche dans `docs/plan-ocr.md` que les dix passages cités parlent encore de la 2.6 ou d'une absence d'installation automatique en 2.5.
7. **Classement des écarts.** Refais le comptage de la section 6 (`python -I` sur un script hors dépôt qui lit les lignes de la section 6, comme `/opt/data/cache/scratch/revP3/ecarts2.py`) : 294 lignes attendues. Contrôle sur au moins vingt écarts du rapport (les cinq acceptés ou fermés les plus sensibles, dont 126, 216, 281 et 276 à 280, plus quinze au hasard dans la liste « fermé ») que la preuve existe dans le journal ; **aucun écart n'est `accepté` sans décision écrite** (section 4) : vérifie 126 et 281 ligne par ligne. Dis combien de lignes `reporté` du rapport ont en réalité une fermeture écrite dans leur cellule.
8. **Portes.** Vérifie que « Avant P4 » n'est pas accordée à la place d'une mesure, que « Après P1 » et « Après P2 » n'ont pas changé, et qu'aucune porte « Après P4 » n'a été créée.
9. **Forme.** `git show --stat` du commit de P4 ne liste que `docs/ocr-avancement.md` et `docs/prompts/64-revue-P4-D.md` ; zéro tiret long ni demi-cadratin dans ces deux fichiers (`grep` des deux caractères) ; fins de ligne LF ; ni `Co-Authored-By` ni mention d'IA dans le message ; le rapport est court et ne recopie pas les écarts.

**Mutations.** Aucune n'est demandée. Si un doute précis sur la force d'un test cité par un critère `tenu` te pousse à en rejouer une, rejoue-la hors dépôt et écris son résultat, sans dépasser trois.

**Livrable.** Une entrée `revue` de P4 dans le journal : ce qui est conforme, les constats numérotés (bloquant, important, mineur) à partir de l'écart 295, les mesures, et le verdict : `bloquant`, `important`, `mineur` ou `rien`. Si le verdict n'est pas bloquant, P4 passe à `fait` et la colonne Relue à `oui`. S'il est bloquant, P4 passe à `rejetée`.

**Test qui doit passer.** La suite complète. Si un test ne passe pas, c'est un constat, pas une correction de ta part.

## Étape D : clôture et chaînage (obligatoire, dernière étape)

Lecture pour cette tâche : dans le point 2 ci-dessous, « état de P2 » se lit « état de P4 » (passage à `fait`, ou à `rejetée` si ton verdict est bloquant), « colonne Relue » se lit « colonne Relue de P4 » et « entrée de journal (`fin` de P2) » se lit « entrée de journal (`revue` de P4) ». La porte « Avant P4 » existe : confirme-la, corrige-la, ou laisse-la `non franchie` en complétant sa liste ; ne l'accorde pas à la place d'une mesure. Il n'existe pas de porte « Après P4 » : n'en crée pas. Si P4 passe à `fait`, aucune tâche du tableau n'est `à faire`, `bloquée`, `à relire` ni `rejetée` : la règle de choix donne le point 4, donc il n'y a **pas de prompt suivant** ; saute le point 3 et écris à Maxence, dans ta réponse, ce qui attend sa décision ou son action (dernière puce du paragraphe « Ce qui attend Maxence » de l'entrée `fin` de P4, complétée de tes constats). Si P4 est `rejetée`, le prompt suivant est la correction de P4, adressée à S, écrite dans `docs/prompts/NN-P4-S.md` (NN : le plus grand numéro présent plus un). Le commit (point 4) ne contient alors que `docs/ocr-avancement.md`, plus le prompt de correction dans le second cas.

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

Fin du prompt 64.
