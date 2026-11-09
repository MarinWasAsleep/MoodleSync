# Prompt 50 pour Claude Sonnet : revue de U5, accessibilité, thème sombre et vérification

Auteur du prompt : Hermes, orchestrateur, 9 novembre 2026, à la fin de U5 (prompt 49). Destinataire : Claude Sonnet (S), dans une **session neuve**. U5 est `à relire` et son propriétaire est D : la revue revient à S, qui n'en est pas propriétaire, et passe avant toute nouvelle tâche (règle de choix, point 1).
Utilisation : coller ce fichier en entier dans la session de S, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/50-revue-U5-S.md et exécute-le ».

---

## Rôle

Tu es Claude Sonnet (S). Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, DeepSeek v4.1 flash (D), et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans et d'un mode qui rend un PDF cherchable. Le moteur, la synchronisation, le mixin `ApiTextes`, le contrat et les onglets (U1 à U4) sont écrits et relus.

D a livré U5 (prompt 49) : l'accessibilité de l'onglet Mes textes (lignes de résultat et menus au clavier, `aria-haspopup`, `aria-expanded`, retour du focus), le thème sombre et les contrastes remontés au-dessus de 4,5, la clé `textes` d'`etatVerification`, et le groupe de réglages « Texte des cours (OCR) » dans le tiroir, avec la case qui désactive l'extraction automatique après synchronisation (écart 216, décision de Maxence). Les fichiers : `moodlesync/interface/app.js`, `moodlesync/interface/textes.js`, `moodlesync/interface/style.css`, un test nouveau `tests/test_accessibilite_js.py`, et les mises à jour du contrat 3.4 et du plan 3.1, 3.2, 3.3 et ligne 1031.

Cette session contient **une seule tâche** : la revue ciblée de U5 (diff, contrat, plans, tests, journal). Ce n'est pas une refonte et ce n'est pas une correction : tu ne modifies aucun fichier de code, ni test, ni contrat, ni plan, ni plan d'exécution. Les constats s'écrivent, ils ne se corrigent pas.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\\MoodleSync\\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole (section 1) ; la ligne U5 (section 2) ; les portes « Après U4 » et « Après U5 » (section 3) ; les lignes de la section 4 du 9 novembre 2026 (la carte dans Ma semaine, le paquet portable en 2.5, les trois décisions de U4 dont la case `ocr_apres_sync`) ; l'entrée `fin` de U5 (la plus récente, auteur D) ; les écarts 178, 179, 195, 213 à 216, 222 et 226 (fermés par U5) et 228 à 231 (nouveaux) (section 6). **Il fait foi.**
2. `docs/ocr-contrat.md` : 3.4 (interface : relis les lignes que U5 a modifiées, Identifiants, Réglages et Vérification), 4 (invariants 7, 9 et 16), 5 (messages et mots à éviter : le groupe de réglages est le seul endroit où le vocabulaire technique est permis).
3. `docs/plan-ocr.md` : 3.1 A (réglages), 3.2 (parcours 1), 3.3 (parcours 2, exception « Plus tard »), 3.7 (microcopy et ton), 5.9 (vie privée), 8 (critères 7 à 11).
4. `docs/plan-execution-ocr.md` : section 3 (ligne U5 et sa porte : « `etatVerification` couvre l'onglet »), phase 5, section 5 (Pack interface), section 9.
5. Le diff de la tâche : `git log --oneline -3` sur `agent/U5-D` doit montrer le commit de U5 au-dessus de `ccb3742`. Lis `git diff ccb3742 HEAD -- moodlesync/interface/app.js`, `-- moodlesync/interface/textes.js`, `-- moodlesync/interface/style.css`, et `tests/test_accessibilite_js.py` en entier. Ton propre travail se fait sur une branche `agent/revue-U5-S` créée à partir de ce commit.
6. Pour comparer et imiter, en lecture : `moodlesync/interface/semaine.js` (le motif `role="button"` et `tabindex` des lignes), `tests/test_textes_js.py` (l'arbre factice et le parcours Node), `tests/test_preparer_js.py` (la méthode de U4).

Ne relis pas les tâches antérieures à U4 : le journal les résume.

## Étape A : base de tests

Lance `python -m unittest discover -s tests -t .` avec `/opt/data/cache/scratch/venv-ms/bin/python` (pywebview 6.2.1, Pillow, pypdf, pypdfium2, Node 26) et note le résultat **tel quel**. La base annoncée est **748 tests, 0 échec, 1 ignoré**, mesurée par D au début et à la fin de U5. Si elle a bougé, signale-le.

**Faits de la machine** : Linux, Python 3.14.9, aucun navigateur, aucune vraie fenêtre pywebview, Tesseract absent. N'installe rien.

## Étape B : la revue

**Ce qui est conforme à vérifier et à mesurer.** Le consentement écrit avant le premier lancement, aucun lancement au chargement, la case `ocr_apres_sync` qui appelle bien `ocr_regler` avec un booléen, les identifiants du contrat 3.4 présents une fois chacun, aucun identifiant nouveau hors contrat, aucune couleur littérale dans le bloc U5 de `style.css`, les contrastes calculés au-dessus de 4,5, les sept mots interdits absents hors du groupe de réglages, l'absence de `innerHTML` alimenté par une donnée.

**Ce qui doit être cherché.** Les cas où le test passe pour une mauvaise raison : une assertion qui ne distingue pas le bon comportement du mauvais, un arbre factice qui ajoute une classe ou un attribut que le vrai `index.html` ne porte pas (c'est le défaut qui a fait rejeter U2), une doublure qui rend une forme que l'API ne rend jamais. Rejoue au moins vingt mutations, dont celles qui touchent la garde de consentement, la case `ocr_apres_sync`, le retour du focus et le calcul de `pret`.

**Ce qui doit être jugé.** Les écarts 228 à 231 ouverts par D : dis pour chacun s'il est exact, s'il doit être fermé, rouvert ou renvoyé à une décision de Maxence. L'écart 226 (bandeau inexistant, tranché par D pour le dernier toast critique) : dis si la lecture tient.

**Ordre imposé : le test qui échoue d'abord, s'applique à D, pas à toi.** Tu ne corriges rien.

**Livrable.** Une entrée `revue` de U5 dans le journal : ce qui est conforme, les constats numérotés (bloquant, important, mineur), les mesures, les mutations rejouées et leur résultat, l'effet de chaque écart sur ce que l'utilisateur voit. Verdict : `bloquant`, `important`, `mineur` ou `rien`.

**Test qui doit passer.** La suite complète, et `tests/test_accessibilite_js.py` seul. Si un test ne passe pas, c'est un constat, pas une correction de ta part.

## Étape D : clôture et chaînage (obligatoire, dernière étape)

Lecture pour cette tâche : dans le point 2 ci-dessous, « état de U5 » se lit « état de U5 » (passage à `fait`, ou à `rejetée` si ton verdict est bloquant), « colonne Relue » se lit « colonne Relue de U5 » et « entrée de journal » se lit « entrée de journal (`revue` de U5) ». La porte « Après U5 » existe : confirme-la, corrige-la, ou laisse-la non franchie ou sous réserves en complétant sa liste ; c'est ta revue qui tranche. La règle de choix s'applique une fois U5 relue. Si U5 passe à `fait`, la première tâche prête est **I1** (installation du moteur à la demande, prompt `docs/prompts/46-I1-S.md`, propriétaire S, décision de Maxence du 9 novembre 2026) : elle n'a pas de ligne dans la section 2, tu en ajoutes une avant de générer le prompt suivant, et comme son propriétaire est toi-même le prompt est écrit à part pour une session neuve. Viennent ensuite P1 à P4 dans l'ordre du plan d'exécution, section 9. Si U5 est `rejetée`, la tâche suivante est la correction de U5, adressée à D.

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

Fin du prompt 50.
