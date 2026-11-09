# Prompt 39 pour Claude Sonnet : revue de U1, HTML et CSS de l'onglet Mes textes

Auteur du prompt : DeepSeek v4.1 flash (D), 9 novembre 2026, à la fin de U1 (prompt 38). Destinataire : Claude Sonnet (S), dans une **session neuve**. U1 est `à relire` et son propriétaire est D : la revue revient donc à S, qui n'en est pas propriétaire (règle de choix, point 1). Aucune autre tâche n'est `à relire` ni `rejetée`, et U2, U3 et U4 dépendent de U1.
Utilisation : coller ce fichier en entier dans la session de Claude Sonnet, ou, s'il a accès au dépôt, lui dire « Lis docs/prompts/39-revue-U1-S.md et exécute-le ».

---

## Rôle

Tu es Claude Sonnet. Tu travailles sur MoodleSync (Python, interface HTML dans pywebview, Windows et macOS, licence MIT) avec une autre IA, DeepSeek v4.1 flash, et avec Maxence, le propriétaire du projet. Tu n'as aucune mémoire des sessions précédentes : **tout ce que tu dois savoir est dans le dépôt**. Le chantier est l'ajout d'une extraction locale du texte des scans (OCR avec Tesseract) et d'un mode qui rend un PDF cherchable. Le moteur (`moodlesync/ocr.py`), la synchronisation (`moodlesync/moteur.py`), le mixin `ApiTextes` (`moodlesync/api_textes.py`) et le contrat sont écrits, testés et relus ; A1, A2 et A3 sont `fait`. U1, la coquille de l'onglet Mes textes, est écrite et attend sa revue.

Cette session contient **une seule tâche** : la revue de U1. Tu lis, tu mesures et tu juges ; tu ne corriges rien. Les corrections éventuelles reviennent à D, dans une session neuve, après ton verdict.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin** (les deux tirets longs), nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure, une version, une référence ou un chiffre. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ». Si un outil te manque (shell, lecture de fichiers), dis-le et arrête-toi.
- Windows : chemins Windows, UTF-8 pour les accents. Les commandes passent par une liste d'arguments, jamais par un shell qui interprète les chemins.
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` ne doit entrer dans le dépôt ni dans tes réponses. Si tu dois lire `%LOCALAPPDATA%\\MoodleSync\\config.json` pour trouver le dossier de rangement, ne lis que la clé `dest` et n'affiche rien d'autre.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, passés en `git -c user.name=... -c user.email=...`. **Jamais** de ligne `Co-Authored-By` ni de mention d'une IA. **Pas de push.** Messages de commit en français sans accents, comme l'historique du dépôt.
- Tu ne modifies que les fichiers listés dans ce prompt. Tout autre fichier qui pose problème se signale dans le journal, il ne se corrige pas.

## À lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : le protocole, l'état des tâches, les portes, le journal des décisions, l'entrée `fin` de U1 (la plus récente, auteur D), l'entrée `revue` de A3, la porte « Après U1 » de la section 3 et les écarts 166 à 174. **Il fait foi.**
2. `docs/ocr-contrat.md` : section 1 (conventions), **3.4 (interface : onglet, identifiants, dialogues, badges, vérification)**, section 5 (mots à éviter dans l'interface principale), section 6 (T28, T30).
3. `docs/plan-ocr.md` : **3.1 (la carte « Préparer mes cours pour l'IA »)**, **3.5 (l'onglet Mes textes : en-tête, recherche, liste, actions, état vide)**, 3.6 (niveau 1 et niveau 2 du panneau, pour la provenance des phrases), 3.7 (microcopy et ton).
4. `docs/plan-execution-ocr.md` : section 3 (ligne U1 et sa porte : « onglet, état vide, badges, qualité »), phase 5, section 5 (Pack interface), section 8 (portes de sortie), section 9 (ordre des tâches, pour l'étape D).
5. `docs/prompts/38-U1-D.md` : le prompt de la tâche relue, pour savoir ce qui était demandé et ce qui était interdit.
6. Le diff de U1 : `git diff 224d32c..<commit de U1> -- moodlesync/interface/index.html moodlesync/interface/style.css tests/test_interface_textes.py`, puis `git show --stat <commit de U1>`, puis les trois fichiers en entier sur le commit (`git show <commit>:moodlesync/interface/index.html`, etc.). Le commit de U1 est `git log -1 agent/U1-D`. Vérifie que le diff des deux fichiers d'interface ne porte que des lignes ajoutées, que rien d'autre que les cinq fichiers annoncés n'est dans le commit, et que les trois fichiers sont en LF.
7. `tests/test_application.py`, classe `Page` uniquement (`test_scripts_et_conteneurs_attendus`, `test_rien_d_exterieur_ni_tiret_long`), pour ce que la suite vérifie déjà et que le nouveau fichier ne doit pas doubler mal.
8. Pour juger sans JavaScript nouveau : dans `moodlesync/interface/app.js`, les fonctions `choisirOnglet`, `majActions`, la navigation au clavier de `#onglets` et le gestionnaire de clic `[data-ferme]` ; dans `commun.js`, `$` et `ic`.

Ne relis pas les tâches antérieures à U1 : le journal les résume.

## Étape A : base de tests

Lance `python -m unittest discover -s tests -t . -v` sur un export propre du commit de U1 (`git archive`, dossier temporaire hors du dépôt) et note le résultat **tel quel**. La base annoncée par U1 est **690 tests, 0 échec, 1 ignoré** (671 avant U1 plus les 19 de `tests/test_interface_textes.py`) avec un interpréteur qui a pywebview ; le seul ignoré est alors T29 (Tesseract absent). Sans pywebview, les deux tests de `test_horaire` s'ajoutent à T29 et la base vaut 690 tests, 0 échec, 3 ignorés. Si la base a bougé, arrête-toi et écris l'écart dans le journal.

**Faits de la machine de D** (mesurés le 9 novembre 2026) : Linux, Python 3.14.9, venv `venv-ms` avec pywebview, Tesseract absent, `pypdfium2` absent, aucun navigateur. Dis dans tes doutes ce que tu n'as pas pu exécuter (Windows, macOS, vraie fenêtre, vrai navigateur). N'installe rien (confirmation de Maxence obligatoire).

**Fins de ligne.** Les blobs des fichiers de U1 sont en LF ; l'arbre de travail porte des fichiers modifiés qui ne sont pas de cette revue (fins de ligne CRLF pour l'essentiel). Ne les normalise pas et ne les inclus pas dans ton commit. Si tu écris un fichier de cette tâche, écris-le en LF.

## Étape B : la revue

Objet : le diff de U1, les trois fichiers en entier sur le commit, l'entrée `fin` de U1. Tu mesures et tu lis, tu ne corriges pas. Chaque défaut est un écart numéroté à partir de 175 dans la section 6, et le verdict global vaut `bloquant`, `important`, `mineur` ou `rien`.

**Comportements à vérifier, contre le contrat 3.4, le plan 3.1, 3.5, 3.6 et 3.7, et le prompt 38 :**

- Les identifiants et la structure : les quinze identifiants du contrat 3.4 (`#tx-entete`, `#tx-recherche`, `#tx-resultats`, `#tx-liste`, `#tx-vide`, `#tx-copier-cours`, `#tx-exporter`, `#tx-ouvrir-dossier`, `#tx-qualite`, `#tx-carte`, `#tx-preparer`, `#tx-plus-tard`, `#tx-quoi`, `#tx-reglages`, `#tx-badge`) présents une fois chacun et aucun autre identifiant `tx-` ou `d-tx-` ; l'onglet `#o-textes` dans `#onglets`, avec `role="tab"`, `data-onglet="textes"`, `aria-controls="v-textes"`, `aria-selected="false"`, `tabindex="-1"`, une icône du jeu existant et le texte « Mes textes » ; les deux onglets existants, `#actions-sync` et `#actions-semaine` intacts ; le panneau `#v-textes` en `role="tabpanel"`, `aria-labelledby="o-textes"`, `hidden`, et **hors** des deux autres panneaux ; la carte `#tx-carte` dans Mes cours, comme l'écrit le contrat 3.4, et non dans le panneau de Mes textes ; la liste `#tx-liste` vide, sans modèle de ligne.
- Les textes, mot pour mot : compare **par programme** (une sonde qui lit le HTML et le plan) l'en-tête, l'état vide et la carte aux phrases du plan (3.5 pour l'en-tête et l'état vide, 3.6 niveau 1 pour la carte, 3.1 pour les libellés de la carte) et au contrat 3.4 ; signale tout mot changé, ajouté ou retiré, et tout texte d'interface absent du plan et du contrat. Vérifie que les nombres de l'en-tête sont dans des `span` que la page remplit et qu'aucun identifiant n'a été inventé dans l'en-tête ni dans l'état vide. Le bouton « Préparer mes cours » de l'état vide porte `data-action="preparer"` et aucun identifiant (écart 172) : dis si ce choix tient pour U2.
- Les mots interdits et la forme : recherche insensible à la casse des sept mots de la section 5 (OCR, Tesseract, tessdata, DPI, segmentation, PSM, TSV) dans tout le panneau, attributs compris ; aucun tiret cadratin ni demi-cadratin dans les trois fichiers ; aucune ressource externe, aucun `@import`, aucun `url(...)` distant ; dis ce que valent les trois `https://` antérieurs à U1 (écart 174) et si le test les contourne à bon droit.
- Les dialogues : `#d-tx-preparer`, `#d-tx-quoi` (classe `large`), `#d-tx-qualite`, avec un titre et un bouton de fermeture seulement ; vérifie dans `app.js` que `[data-ferme]` ferme bien le dialogue qui le contient et que ces trois dialogues n'ont besoin d'aucun JavaScript nouveau pour se fermer.
- La feuille : `.badge-qualite` et les quatre variantes `.bon`, `.a-verifier`, `.difficile`, `.cherchable` sur les variables existantes, la couleur toujours accompagnée du mot (contrat 3.4), aucune couleur en dur là où une variable existe, aucun `@media (prefers-color-scheme)` ni `[data-theme]` nouveau (le thème sombre est U5), le style de `#tx-badge` et de l'état vide, la cohérence avec les composants existants (`.carte-s`, `.bouton`, `.lien`, `.champ`, `.doux`) et avec le responsive existant (points de rupture 860, 680 et 560 pixels). Dis si U5 pourra vérifier le contraste sans réécrire ce bloc.
- Le test : lis `tests/test_interface_textes.py` en entier. Chaque assertion distingue-t-elle vraiment deux comportements ? Rejoue **au moins cinq mutations de ton cru**, hors du dépôt, une copie jetable par mutation, sur une copie de l'arbre de U1 : par exemple retirer un identifiant, changer un mot d'une phrase du plan, retirer `hidden` du panneau, retirer une variante de badge, changer `data-action="preparer"` en identifiant, écrire un mot interdit dans le panneau. Dis, pour chacune, si le test échoue et quel test la voit. Cherche les assertions tautologiques et celles qui passent sur le code de départ : U1 en annonce trois (`test_aucune_ressource_externe`, `test_ni_tiret_long_ni_cadratin`, `test_onglets_existants_intacts`), contrôle-le et dis si d'autres assertions sont dans ce cas. Vérifie aussi que le test ne dépend ni de `application.py`, ni de pywebview, ni d'un navigateur.
- Les réserves annoncées : l'onglet inerte (`choisirOnglet` et la navigation au clavier codés en dur pour deux onglets, `majActions` qui laisse `#actions-sync` visible), l'état vide et la liste présents ensemble dans le HTML, l'absence de rendu réel. Dis pour chacune si elle est exacte, si elle relève de U2 ou de U5, et si le journal doit l'écrire autrement.
- Le périmètre : vérifie que le commit de U1 ne contient que `moodlesync/interface/index.html`, `moodlesync/interface/style.css`, `tests/test_interface_textes.py`, `docs/ocr-avancement.md` et `docs/prompts/39-revue-U1-S.md` ; qu'aucun fichier JavaScript, aucun fichier Python, ni le contrat, ni le plan, ni le plan d'exécution, ni un test existant n'a changé ; que `git diff --numstat` ne donne que des lignes ajoutées sur les deux fichiers d'interface (aucune ligne retirée, donc aucune fin de ligne historique dans le commit) ; que les trois fichiers sont en LF ; que `docs/ocr-avancement.md` ne perd aucune ligne existante.
- Les écarts 172 à 174 : dis pour chacun s'il est exact, bien classé et bien laissé ouvert, ou s'il doit être fermé par U1 avant de passer à `fait`.

**Mesures attendues** : suite complète au début et à la fin sur un export propre du commit de U1 ; compte des tests du fichier nouveau (19 annoncés) ; au moins cinq mutations rejouées, avec le test qui les voit ; comparaison par programme des phrases du plan et du contrat avec le HTML ; comptage des quinze identifiants et des identifiants `tx-` et `d-tx-` ; contrôle des mots interdits dans le panneau, des fins de ligne et des tirets longs dans les blobs du commit ; `git show --stat` du commit de U1.

**Verdict.** Un important ou un mineur se justifie par une mesure, pas par une préférence. U1 passe à `fait` (Relue : oui) si le verdict n'est pas `bloquant`, sinon à `rejetée` avec la liste des corrections à faire par son propriétaire (D). La porte « Après U1 » est franchie, franchie sous réserves ou non franchie, avec la raison.

## Étape D : clôture et chaînage (obligatoire, dernière étape)

Lecture pour cette tâche : le point 2 met à jour l'état de U1 et la colonne Relue de U1, la porte « Après U1 » (section 3) et écrit l'entrée `revue` de U1. La règle de choix s'applique une fois U1 passée à `fait` ou `rejetée`.

1. **Relance la suite complète** et note le résultat réel (elle ne doit pas avoir bougé).
2. **Mets à jour `docs/ocr-avancement.md`** : état de U1, colonne Relue, porte « Après U1 » (section 3), entrée de journal (`revue` de U1), écarts (section 6). Tu n'effaces aucune ligne existante.
3. **Prépare le prompt de l'étape suivante** (règle de choix ci-dessous) et écris-le dans `docs/prompts/NN-<ID>-<S ou D>.md`, où `NN` est le plus grand numéro déjà présent dans `docs/prompts/` plus un.
4. **Commit** (un seul) : `docs/ocr-avancement.md` et le nouveau prompt. Rien d'autre. Pas de push.
   Cette tâche est une revue, sans code : le commit unique ne porte que ces deux fichiers.
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

Fin du prompt 39.
