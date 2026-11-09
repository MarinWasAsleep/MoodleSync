# Prompt 52 pour DeepSeek v4.1 flash : corrections des quatre importants de la revue de U5

Auteur : Hermes, orchestrateur, 9 novembre 2026. Destinataire : DeepSeek v4.1 flash (D), dans une session neuve. Une seule tâche, quatre constats.

## Décision de Maxence, à appliquer telle quelle

La correction de U5 passe **avant** I1. Maxence a tranché le 9 novembre 2026 : les défauts visibles de l'interface déjà livrée se corrigent d'abord, l'installation du moteur ensuite.

## Rôle

Tu es DeepSeek v4.1 flash (D). Tu as écrit U5 ; Claude Sonnet (S) l'a relue et a trouvé quatre défauts importants, tous mesurés ou déduits, tous dans l'interface. Cette session les corrige. Tu ne fais rien d'autre.

## Règles non négociables

- Français. **Aucun tiret cadratin ni demi-cadratin**, nulle part : ni dans tes réponses, ni dans les fichiers. Écriture directe, sans formules creuses ni flatterie.
- Ne jamais inventer une mesure. Ce qui n'a pas été mesuré s'écrit « non mesuré ». Ce qui est déduit s'écrit « déduit ».
- Aucun document de cours, aucun jeton, aucun contenu de `config.json` dans le dépôt ni dans tes réponses.
- Commits : auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, sans `Co-Authored-By` ni mention d'une IA. Messages en français sans accents. **Pas de push.**
- Jamais `git add -A`, `git add .`, `git commit -a`, `git clean`. Seulement les fichiers de la tâche, puis `git show --stat` pour le prouver.
- Aucune phrase nouvelle hors de `TX_MOTS`, aucun `innerHTML` alimenté par une donnée, aucun mot interdit, aucun tiret long, fichiers en LF.

## À lire, dans cet ordre

1. `docs/ocr-avancement.md` : l'entrée `revue` de U5 (la plus récente, auteur S) et les écarts 216, 228, 232, 233 et 234 (section 6). **Ils font foi**, avec leurs mesures.
2. `docs/ocr-contrat.md` : 3.2 (`ocr_etat`, `ocr_regler`), 3.4 (interface, Réglages et Vérification), 5 (messages).
3. `moodlesync/interface/app.js` (le groupe de réglages dans `remplirTiroir`, `etatVerification`), `moodlesync/interface/textes.js` (la ligne de résultat et son `keydown`), `moodlesync/interface/style.css` (`.interrupteur`), `tests/test_accessibilite_js.py` en entier.

## État de départ

- Branche `agent/corrections-U5-D`, à créer à partir de `d983891`.
- Suite de référence : 748 tests, 0 échec, 1 ignoré, avec `/opt/data/cache/scratch/venv-ms/bin/python` (pywebview 6.2.1, Pillow, pypdf, pypdfium2, Node 26). Mesure-la toi-même d'abord.

## Les quatre constats

**1. Écart 228 reclassé important, écart 216 rouvert côté page : la case se recoche seule.** Le groupe de réglages lit la valeur d'`ocr_apres_sync` dans une clé que l'API ne rend jamais, et la doublure du test la rend à sa place. Avec la forme réelle d'`ocr_etat`, décocher la case coupe bien le réglage côté Python, mais l'affichage la recoche, donc l'étudiant ne peut pas la réactiver. Correction : lire la valeur là où `ocr_etat` la donne réellement (section 3.2 du contrat, `reglages`), et corriger la doublure du test pour qu'elle rende exactement la forme du contrat, sans clé inventée. Test : décocher puis relire l'état, la case reste décochée, et `ocr_regler` a bien été appelé avec `False`.

**2. Écart 232 : Entrée sur « Copier l'extrait » ouvre le fichier.** Le gestionnaire `keydown` de la ligne de résultat ne regarde pas la cible de l'événement. Correction : n'agir que si la cible est la ligne elle-même, pas un bouton à l'intérieur. Test : `Entrée` sur le bouton de copie appelle la copie et n'ouvre pas le document ; `Entrée` sur la ligne ouvre le document.

**3. Écart 233 (déduit) : les cases à cocher sont inatteignables au clavier.** `.interrupteur input { display: none }` retire les cases de l'ordre de tabulation, consentement compris. Correction : masquer visuellement sans retirer du flux, avec la technique déjà employée ailleurs dans `style.css` si elle existe (cherche `clip`, `sr-only`, `visually-hidden`), sinon une position absolue d'un pixel. Test : la case a un `tabindex` naturel et reste dans l'ordre de tabulation (vérifiable par l'absence de `display: none` et la présence du style de remplacement).

**4. Écart 234 : deux mutations du consentement survivent.** Le test ne distingue pas « la case est écrite à l'ouverture » de « la case est toujours cochée ». Correction : assertions qui comparent l'état de la case à la valeur rendue par l'API, avant et après un changement.

## Étapes

A. Mesure la suite complète et colle le résultat réel.
B. Pour chaque constat, écris d'abord le test qui échoue, puis la correction minimale. Un constat, un test, une correction.
C. Relance la suite complète. Attendu : 748 tests plus les tiens, 0 échec, 1 ignoré.
D. Mets à jour `docs/ocr-avancement.md` : entrée `fin` de cette correction, section 2 (base de tests, état de U5 repassé à `à relire`), section 6 (écarts 216, 228, 232, 233 et 234 : fermés ou réduits, avec la mesure). Tu n'effaces aucune ligne existante.
E. Commit unique, auteur imposé, `git show --stat` vérifié.
F. Réponds avec `Fait / Fichiers / Tests / Décisions / Doutes / Suivant`, le hash du commit et la sortie réelle de la suite. Tu n'enchaînes pas la revue.

---

Fin du prompt 52.
