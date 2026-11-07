# Prompt 01 pour DeepSeek v4 pro : revue du contrat (E0), puis spike (S1)

Auteur du prompt : Claude Sonnet, 7 novembre 2026. Destinataire : DeepSeek v4 pro.
Utilisation : coller ce fichier en entier dans la session de DeepSeek, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/01-revue-E0-puis-S1-D.md et exécute-le ».

---

## Rôle

Tu es DeepSeek v4 pro. Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, Claude Sonnet, et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans (OCR avec Tesseract) et d'un mode qui rend un PDF cherchable.

Cette session contient deux tâches, dans cet ordre : **revue de E0** (le contrat d'interface), puis **S1** (le spike technique). Tu ne fais rien d'autre.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\MoodleSync\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole, l'état des tâches, le journal. **Il fait foi.**
2. `docs/ocr-contrat.md` : le contrat à relire.
3. `docs/plan-ocr.md`, sections 4.3, 5.2, 5.3, 5.4, 7 (lot 0), 8 et 9.
4. Extraits de code, sans lire les fichiers entiers : `moodlesync/moteur.py` (`empreinte`, `index_existant`, `deja_present`, `charger_etat`, `sauver_etat`, `cle_url`, `recuperer`, `telecharger`), `moodlesync/seances.py` (`pdf_range`, `pages_pdf`), `moodlesync/api_horaire.py` (début), `moodlesync/application.py` (`Api.__init__`, `sync_lancer`).

## Étape A : base de tests

Lance `python -m unittest discover -s tests -t . -v`. Note dans le journal le nombre de tests et les éventuels échecs, **tels quels**. Si la base est rouge avant que tu aies touché quoi que ce soit, signale-le dans le journal et continue : ce n'est pas ton écart.

## Étape B : revue ciblée de E0 (le contrat)

Tu es le relecteur d'un document écrit par l'autre IA. Cherche, dans cet ordre :

1. **Faits du dépôt faux.** Vérifie dans le code chaque affirmation de la section 1 (« Faits du dépôt ») et de la section 3.3 (signatures actuelles de `index_existant`, `deja_present`, `pdf_range`, `telecharger`, comportement de `ApiHoraire.__init__`, `proteger` contre `_proteger`, usage de `T["ancienne"]`).
2. **Incohérences internes.** Une clé, un nom ou une valeur qui diffère entre la section 2, la section 3, les invariants et les tests. Un invariant qu'aucun test de la section 6 ne couvre. Un critère d'acceptation du plan (section 8) sans test.
3. **Ambiguïtés qui feraient diverger deux implémentations.** Là où deux modèles écriraient deux comportements différents à partir du même texte.
4. **Choses impossibles ou fragiles.** Par exemple une étape qui exige un verrou impossible à tenir, une comparaison coûteuse sur chaque synchronisation, un cas où la sûreté annoncée n'est pas garantie.
5. **Contradictions avec les décisions D1 à D7** (section 7 du contrat et section 4 du journal).

Ne réécris pas le contrat. Ne le modifie pas. Pour chaque constat : gravité (**bloquant**, **important**, **mineur**), section concernée, le problème en une phrase, la correction proposée en une phrase. Pas de remarque de style. Si tu ne trouves rien dans une catégorie, écris « rien ».

Consigne de sortie :
- Écris une entrée de journal de type `revue` pour E0 (format de la section 5 du journal), avec la liste des constats.
- S'il y a au moins un **bloquant** : passe E0 à `rejetée`, ajoute les constats à la section 6 du journal (Écarts ouverts), **arrête-toi après l'étape D (chaînage)** : tu ne fais pas S1, et le prompt que tu prépares est celui de la correction, destiné à Claude Sonnet.
- Sinon : passe E0 à `fait` (Relue : oui, D). Les constats « important » et « mineur » vont dans la section 6 du journal. Passe à l'étape C.

## Étape C : tâche S1, spike pypdfium2 et Tesseract (seulement si E0 n'est pas rejetée)

Réserve la tâche : S1 passe à `en cours` dans le journal, Propriétaire D, avec la date.

**Question unique** : est-ce que pypdfium2, Tesseract en sortie TSV et la superposition d'une couche de texte avec pypdf fonctionnent, avec des temps acceptables, sur cette machine Windows, et que peut-on dire de macOS ? Réponse attendue : **go ou no-go**, par volet.

**Interdits** : modifier `moodlesync/`, `tests/`, `requirements.txt`, `MoodleSync.spec`, le contrat. Aucune interface, aucun cache, aucune file. Ne rien installer dans l'environnement Python du projet : crée un environnement virtuel jetable **hors du dépôt** (dossier temporaire du système) et installe-y `pypdfium2`, `Pillow` et `pypdf` aux versions courantes ; note les versions exactes obtenues. Tes scripts d'essai restent hors du dépôt. Le seul livrable est `docs/spike-ocr.md`, une page.

**Mesures à faire** (chaque ligne du rapport indique : mesuré, déduit ou non mesuré) :

1. **Versions** : Python, pypdfium2, Pillow, pypdf, Tesseract.
2. **Détection** : sur la machine de développement, `tesseract.exe` est dans `C:\Program Files\Tesseract-OCR\`, hors PATH, `TESSDATA_PREFIX` pointe vers un dossier `tessdata` dans `%LOCALAPPDATA%` (vérifie, ne le suppose pas). Les langues `fra`, `eng`, `osd` y sont-elles ? Que donne `--list-langs` ? Quel dossier de langues est réellement utilisé ?
3. **Documents d'essai** : trois pages réelles si possible (une numérique, une scannée, une mixte), prises dans le dossier de rangement de l'utilisateur, **copiées dans le dossier temporaire et jamais dans le dépôt**. S'il n'y a pas de vrai scan, fabrique-en un avec Pillow (texte français avec « é è ç œ », deux colonnes, une note de bas de page) converti en PDF image. Dis lequel tu as utilisé.
4. **Rendu** : page rendue par pypdfium2 à 300 DPI, niveaux de gris, autocontraste. Temps par page. Taille de l'image.
5. **Reconnaissance** : `tesseract <image> stdout -l fra+eng --psm 3 --oem 1 --tessdata-dir <dossier> tsv`. Temps par page (objectif : rendu plus reconnaissance sous 3 secondes). Qualité du TSV : accents corrects, niveaux, confiance (rappel : le contrat stocke la confiance de 0 à 1, donc TSV divisé par 100), mots à confiance négative. Une page mixte : que renvoie pypdf pour le texte natif ?
6. **Console noire** : lance l'appel avec `subprocess` et `CREATE_NO_WINDOW`, depuis un processus sans console (`pythonw.exe`). Une fenêtre console apparaît-elle ? Si tu ne peux pas l'observer, écris « non observé » et donne le moyen de le vérifier (Maxence regardera).
7. **Superposition** (le volet le plus risqué) :
   - Technique 1 : `tesseract <image> <sortie> -c textonly_pdf=1 pdf` (ou équivalent), puis fusion sur la page d'origine avec pypdf.
   - Technique 2 : couche construite à partir du TSV (texte invisible positionné), puis fusion.
   - Pour chacune, sur un PDF de test qui contient **une annotation, un lien et un signet** : nombre de pages, dimensions et rotation par page, comptes d'annotations, de liens et de signets avant et après, texte extractible après (accents « é è ç œ » compris), alignement du texte sur l'image (donne ta méthode), taille du fichier avant et après (le ratio sert à la borne de volume du contrat), le fichier se rouvre.
   - Rendu avant et après sur trois pages : écart moyen entre les deux images, pour proposer la tolérance de la vérification (invariant 4 du contrat).
8. **Aperçu** : un PNG de 900 px de large, quelle taille en octets, quel temps ?
9. **macOS** : tu ne peux pas le tester ici. Écris « non testé », liste ce qui devra l'être (chemin de `tesseract` avec Homebrew, wheels de pypdfium2 pour Apple Silicon) sans affirmer qu'il marchera.

**Structure de `docs/spike-ocr.md`** : versions ; tableau des mesures (mesuré, déduit, non mesuré) ; décision go ou no-go **par volet** (rendu, reconnaissance, console, superposition, macOS) ; valeurs proposées pour tout ce que le contrat marque **S1** (méthode de la couche de texte, tolérance du rendu, borne de volume, taille de l'aperçu, seuils de qualité s'ils paraissent mal calibrés) ; plan B en cas de no-go ; limites. Tu **proposes** ces valeurs, tu ne modifies pas le contrat : l'autre IA le fera en revue.

**Porte de sortie** : go si et seulement si une page tient sous 3 secondes, aucune console n'apparaît (ou ne peut être exclue que par un test manuel que tu décris), le TSV est lisible avec les accents, et au moins une technique de superposition conserve pages, dimensions, annotations, liens et signets. Sinon no-go, avec la cause et un plan B. Dans les deux cas S1 passe à `à relire` (jamais `fait` : c'est l'autre IA qui valide).

## Étape D : clôture et chaînage (obligatoire, dernière étape)

1. **Relance la suite complète** et note le résultat réel (elle ne doit pas avoir bougé).
2. **Mets à jour `docs/ocr-avancement.md`** : états des tâches (E0, S1), colonne Relue, portes de sortie (section 3), entrées de journal (`revue` de E0, `prise` et `fin` de S1), écarts (section 6). Tu n'effaces aucune ligne existante.
3. **Prépare le prompt de l'étape suivante** (règle de choix ci-dessous) et écris-le dans `docs/prompts/NN-<ID>-<S ou D>.md`, où `NN` est le plus grand numéro déjà présent dans `docs/prompts/` plus un.
4. **Commit** (un seul) : `docs/spike-ocr.md` (si S1 a été faite), `docs/ocr-avancement.md`, le nouveau prompt. Rien d'autre. Pas de push.
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

Fin du prompt 01.
