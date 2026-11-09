# Prompt 35 pour Claude Sonnet : revue de A2, recherche, copie, export, ouverture

Auteur du prompt : DeepSeek v4.1 flash, 9 novembre 2026, à la fin de A2 (prompt 33). Destinataire : Claude Sonnet, dans une **session neuve**. A2 est `à relire` : la revue est la seule tâche ouverte, et une tâche terminée ne débloque ses dépendantes qu'une fois relue et passée à `fait` (règle de choix, étape D).
Utilisation : coller ce fichier en entier dans la session de Claude Sonnet, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/35-revue-A2-S.md et exécute-le ».

---

## Rôle

Tu es Claude Sonnet. Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, DeepSeek v4.1 flash, et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans (OCR avec Tesseract) et d'un mode qui rend un PDF cherchable. Le moteur (`moodlesync/ocr.py`), la synchronisation (`moodlesync/moteur.py`), le mixin `ApiTextes` (`moodlesync/api_textes.py`, tâches A1 et A2) et leurs tests sont écrits. A1 a été relue et passée à `fait` ; A2 attend sa revue.

Cette session contient **une seule tâche** : la revue de A2, c'est-à-dire les cinq méthodes que A2 a ajoutées à `moodlesync/api_textes.py` (`ocr_documents`, `ocr_chercher`, `ocr_copier`, `ocr_exporter`, `ocr_ouvrir`), leurs outils privés, et les 27 tests ajoutés à `tests/test_api_textes.py`. Tu ne corriges rien : chaque défaut devient un écart dans la section 6 du journal, et le verdict le classe. Tu ne touches ni au code ni aux tests, ni à `ocr.py`, `moteur.py`, `application.py`, l'interface, le contrat ou le plan.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\\MoodleSync\\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole, l'état des tâches, le journal, les écarts. **Il fait foi.** Lis en particulier l'entrée `fin` de A2 (la plus récente), l'entrée `fin` des corrections du prompt 34, l'entrée `revue` de A1, et les écarts 122 à 152.
2. `docs/ocr-contrat.md` : sections 1 (conventions), 2.3 (cache), 2.5 (file), 2.6 (arborescence), **2.7 (formes renvoyées)**, 3.1 (sorties de C5 et fonctions d'`ocr.py`), **3.2 (signatures des cinq méthodes)**, 4 (invariants 6, 8, 9, 11, 15), 5 (messages), 6 (T24, T26, T27, T28), 7 (D4, D5).
3. `docs/plan-ocr.md` : sections 3.5 (l'onglet Mes textes), 4.4 (qualité), 4.5 (fraîcheur, orphelins), 5.9 (sécurité et vie privée), 6.1 à 6.4 (formats produits, JSONL), 8 (critères 7 et 8).
4. `docs/plan-execution-ocr.md` : section 3 (lignes A2 et A3), phase 4 (section 4), section 5 (Pack API), section 9 (ordre des tâches).
5. `docs/prompts/33-A2-D.md` : le prompt de la tâche relue, pour savoir ce qui était demandé.
6. Le diff de A2 : `git diff 364922e..<commit de A2> -- moodlesync/api_textes.py tests/test_api_textes.py`, puis les deux fichiers en entier. Vérifie que le diff ne touche rien d'autre et que les 36 tests antérieurs et `Base` sont intacts.
7. Dans `moodlesync/ocr.py` : `charger_cache`, `charger_file`, `_orphelins`, `_documents`, `_pages_md`, `_pages_a_verifier`, `_lire_md`, `_dans_la_portee`, `_dossier_textes`, `_resoudre_sortie`, `_cle`, `_absolu`, `_comparable`, `_dossier_du_cours`, `classer`, `assembler_contexte`, `ecrire_jsonl`, `MESSAGES`, `ErreurOcr`. Dans `moodlesync/moteur.py` : `charger_config`, `charger_etat`, `message_erreur`, `cle_nom`, `nfc`, `ouvrir_dossier`, `T`, `ILLEGAL`. Dans `moodlesync/semaine.py` : `ouvrir_document`.
8. Pour comparer et imiter : `moodlesync/api_horaire.py` (`_proteger`), `moodlesync/application.py` (`_js`, `_cfg`, `_sauver_cfg`, `ouvrir`, `lancer`), et `tests/test_api_textes.py` (`Base`, `FauxFenetre`, `pdf_minimal`, doublures de `detecter`, `executer` et `rendre_page`).

Ne relis pas les tâches antérieures à A1 : le journal les résume.

## Étape A : base de tests

Lance `python -m unittest discover -s tests -t . -v` sur un export propre du commit de A2 (`git archive`, dossier temporaire hors du dépôt). Note dans le journal le nombre de tests et les éventuels échecs, **tels quels**. La base annoncée est **594 tests, 0 échec, 1 ignoré** (567 plus 27 de A2, mesurée par D sur un export propre de `364922e` plus les deux fichiers de A2). Le seul ignoré attendu est T29, Tesseract absent.

**Faits de la machine** (mesurés par D le 9 novembre 2026) : Linux, Python 3.14.9, pywebview 6.2.1 présent, Tesseract absent, `pypdfium2` absent, pypdf 6.21.4, Pillow 13.0.0. Aucun vrai moteur, aucun vrai Moodle. N'installe rien (confirmation de Maxence obligatoire).

**Fins de ligne.** L'arbre de travail porte des fichiers modifiés qui ne sont pas de cette tâche (fins de ligne CRLF pour l'essentiel). Ne les normalise pas et ne les inclus pas dans ton commit. Les blobs de `moodlesync/api_textes.py` et de `tests/test_api_textes.py` sont en LF. Fais tes mesures sur un export propre du commit de A2.

## Étape B : la revue

Objet : le diff de A2 et les deux fichiers entiers. Tu mesures et tu lis, tu ne corriges pas. Chaque défaut est un écart numéroté à partir de 153 dans la section 6, et le verdict global vaut `bloquant`, `important`, `mineur` ou `rien`.

**Comportements à vérifier, contre le contrat et les décisions du journal :**

- `ocr_documents` : forme de 2.7 (clés de la ligne et du bloc), tri par cours, section, nom (`ms.cle_nom`), `cherchable` = état portant `genere` et fichier présent, `orphelin` pour une entrée de cache dont le document a disparu, filtres `cours` (cid résolu par `_dossier_du_cours`), `qualite`, `type`, `total` et `pages`. Aucune écriture. Vérifie le cas d'un cache édité (entiers, `confiance` hors bornes, booléens), et que `_entier` de A1 n'est pas réutilisé sans borne (écart 136).
- `ocr_chercher` : texte de moins de deux caractères, recherche sans casse ni accents, une page par résultat, `segments` avec `t` et `m` reconstruits dans le texte d'origine (aucun décalage, pas de piège UTF-16), `total` et `tronque` au-delà de `limite`, section « Pages à vérifier » exclue (écart 78). Vérifie que `_pliage` ne perd ni n'invente de caractère (accents, ligatures, majuscules), et que l'extrait ne dépasse pas la page.
- `ocr_copier` : `ocr.assembler_contexte(dest, portee, cfg=cfg)`, compte de caractères calculé ici sur la chaîne rendue (T27), plafond de 2 000 000 avec `trop_long`, `documents` et `pages` (écart 151), aucune écriture, presse-papiers laissé à la page.
- `ocr_exporter` : `format` parmi `zip`, `zip_jsonl` et `md`, `import webview` dans la méthode seulement, boîte native, `{"annule": True}` sans choix, zip sans chemin absolu, JSONL par `ocr.ecrire_jsonl` avec un flux fourni par le mixin, rien d'écrit dans `dest`, `octets` réel, extension ajoutée. Vérifie le chemin d'une erreur d'écriture (invariant 9) et l'écart 148.
- `ocr_ouvrir` : confinement comme `ocr._eligible` et plus strict (relatif à `dest`, `ocr._cle`, aucun `..`, aucune lettre de lecteur `C:x`, `realpath` puis préfixe avec `dest` et le dossier de sortie, aucun accès à `.moodlesync-ocr/`), `.md` ouvert par une liste d'arguments, dossier ouvert de même, `{"source": True}` pour un fichier d'origine, phrase de la section 5 pour un chemin refusé (écart 149). Vérifie les liens symboliques (déduit pour Windows), le chemin absolu dans le coffre et hors du coffre, et que `page` ne sert qu'à la page.
- Transverse : `api_textes.py` n'importe ni `urllib` ni `socket`, ni `webview` en tête de module (invariant 6) ; aucune réponse ne porte de trace technique (invariant 9) ; `_ocr_fichiers` n'est jamais tenu par ces méthodes et aucun nouveau verrou n'est posé ; le cache est lu sous `_ocr_verrou` ; lecture seule sur `dest` pour `ocr_documents`, `ocr_chercher`, `ocr_copier` ; entiers `int` positifs ou nuls, `confiance` `float` de 0 à 1 ou `None` ; aucun écart 130 à 152 corrigé par surprise.
- Tests : lis les 27 tests ajoutés, vérifie qu'ils ne modifient ni `Base` ni les 36 tests existants, et que chacun échoue bien sans le code (le journal annonce 26 sur 27 en échec sans A2, le seul vert étant `StructureA2`, qui ne dépend d'aucune méthode). Rejoue au moins quatre des six mutations du journal, puis des mutations de ton cru, hors du dépôt, une copie jetable par mutation, suite complète, témoin vert avant et après. Cherche les tests tautologiques et les assertions qui ne distinguent pas deux comportements.
- Écarts 147 à 152 : dis pour chacun s'il est exact, ce qu'il coûte et qui doit le corriger (A2 de nouveau, A3, U2, ou une décision de Maxence). Classe aussi les écarts 130 à 146 que A2 aurait aggravés ou laissés passer.

**Mesures attendues** : suite complète au début et à la fin sur un export propre du commit de A2 ; compte des tests ajoutés ; au moins quatre mutations rejouées (détectées ou survivantes, avec le nom du test qui les voit) ; vérification par programme des formes JSON (clés, types, entiers positifs, `confiance`) et des refus de `ocr_ouvrir` ; contrôle des fins de ligne et des tirets longs dans les blobs du commit ; `git show --stat` du commit de A2.

**Verdict.** Aucun bloquant n'est attendu ; un important ou un mineur se justifie par une mesure, pas par une préférence. A2 passe à `fait` (Relue : oui) si le verdict n'est pas `bloquant`, sinon à `rejetée` avec la liste des corrections à faire par son propriétaire.

## Étape D : clôture et chaînage (obligatoire, dernière étape)

Lecture pour cette tâche : le point 2 met à jour l'état de A2 et écrit l'entrée `revue` de A2 ; la règle de choix s'applique une fois A2 passée à `fait` ou `rejetée`.

1. **Relance la suite complète** et note le résultat réel (elle ne doit pas avoir bougé).
2. **Mets à jour `docs/ocr-avancement.md`** : état de A2, colonne Relue, portes de sortie (section 3), entrée de journal (`revue` de A2), écarts (section 6). Tu n'effaces aucune ligne existante.
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

Fin du prompt 35.
