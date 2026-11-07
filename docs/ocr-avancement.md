# OCR : tableau d'avancement partagé

Ce fichier est la **seule source de vérité** sur l'état du chantier OCR. Il est lu et mis à jour par les deux IA (S = Claude Sonnet, D = DeepSeek v4 pro) et par Maxence.
Contrat : `docs/ocr-contrat.md`. Plan : `docs/plan-ocr.md`. Découpage : `docs/plan-execution-ocr.md`.
Une phrase de ce fichier qui contredit le code ou le contrat est un bug à signaler dans le journal (section 5), pas à corriger en silence.

## 1. Protocole (obligatoire pour les deux IA)

**Au début d'une tâche**
1. Lire ce fichier en entier, puis le contrat, puis seulement les fichiers du pack de la tâche.
2. Vérifier que les dépendances de la tâche sont en état `fait` **et** relues (colonne Relue). Sinon, ne pas commencer : écrire l'écart dans le journal.
3. Lancer `python -m unittest discover -s tests -t . -v` et noter le résultat dans le journal (« base verte : N tests » ou la liste des échecs préexistants). Ne jamais partir d'une base inconnue.
4. Passer la tâche à `en cours`, écrire son nom dans Propriétaire et la date. **Une tâche en cours n'est reprise par personne d'autre.** Une tâche `en cours` depuis plus de 48 h sans entrée de journal peut être reprise par Maxence ou par l'autre IA, avec une entrée qui le dit.

**Pendant**
- Ne toucher que les fichiers prévus par la tâche (colonne Fichiers). Un fichier hors périmètre se signale, il ne se modifie pas.
- Une décision qui change une signature, une clé JSON, un identifiant DOM ou un message : mettre à jour `docs/ocr-contrat.md` **dans le même commit**, et ajouter une ligne au journal des décisions (section 4).

**À la fin d'une tâche**
1. Lancer la suite complète. Coller le résultat réel (nombre de tests, échecs) dans l'entrée de journal. Pas de « les tests passent » sans chiffre.
2. Écrire l'entrée de journal au format de la section 5 (Fait, Fichiers, Tests, Décisions, Doutes, Suivant).
3. Passer la tâche à `à relire` (jamais directement à `fait`). Seul l'**autre** IA, ou Maxence, passe une tâche à `fait` après une revue ciblée (diff, contrat, tests) et écrit son verdict dans le journal.
4. Les tâches touchant `moteur.py`, `ocr.py`, `api_textes.py` ou le remplacement de PDF exigent cette revue. Pour les tâches mécaniques (P1, P3, U5), une relecture rapide suffit.

**États autorisés** : `à faire`, `bloquée`, `en cours`, `à relire`, `fait`, `rejetée` (revue négative, retour au propriétaire).

**Règles de forme**
- Français, pas de tiret long ni de tiret demi-cadratin (un test du contrat le vérifie), pas de promesse de perfection.
- Un commit par tâche terminée. Identité : MarinWasAsleep (adresse noreply GitHub). Aucun `Co-Authored-By` ni ligne de signature d'IA. Le hash du commit va dans la colonne Preuve.
- Ne rien affirmer qui n'a pas été vérifié. Une information déduite est marquée « déduit ».
- Ne jamais supprimer une entrée du journal. Une erreur se corrige par une entrée nouvelle qui renvoie à l'ancienne.

## 2. État des tâches

Dernière mise à jour : 7 novembre 2026, par D. Prompts de session : `docs/prompts/` (un fichier par étape, chaînés, voir le prompt 01, étape D). Base de tests actuelle : **verte, 277 tests** (mesurée par D à l'ouverture et à la clôture de S1).

| ID  | Tâche                                         | Proprio | État                   | Relue | Dépend de  | Fichiers                                                | Preuve                                               |
| --- | --------------------------------------------- | ------- | ---------------------- | ----- | ---------- | ------------------------------------------------------- | ---------------------------------------------------- |
| E0  | Contrat d'interface                           | S       | fait                   | oui   | plan       | `docs/ocr-contrat.md`                                   | commit `f14d60f`, revue D (prompt 01, étape B)             |
| E0b | Aligner `plan-ocr.md` sur D1 à D7             | S       | à faire                | non   | E0         | `docs/plan-ocr.md`                                      | liste des écarts : contrat section 7                 |
| S1  | Spike pypdfium2 et Tesseract TSV              | D       | à relire               | non   | E0         | `docs/spike-ocr.md`                                     | go écrit, à valider par S                                  |
| C1  | Détection du moteur et configuration          | D       | bloquée par S1         | non   | E0, S1     | `moodlesync/ocr.py`                                     |                                                      |
| C2  | Texte natif, TSV, Markdown par document       | S       | bloquée par S1         | non   | E0, S1     | `moodlesync/ocr.py`                                     |                                                      |
| C3  | Cache, empreinte, reprise, file               | S       | bloquée par C2         | non   | C2         | `moodlesync/ocr.py`                                     |                                                      |
| C4  | PDF cherchable, superposition, vérification   | S       | bloquée par C2         | non   | C2         | `moodlesync/ocr.py`                                     |                                                      |
| C5  | Markdown de cours, index, qualité, JSONL      | D       | bloquée par C2         | non   | C2         | `moodlesync/ocr.py`                                     |                                                      |
| Y1  | État de synchronisation et `deja_present`     | S       | bloquée par C3, C4     | non   | C3, C4     | `moodlesync/moteur.py`, `moodlesync/seances.py`         |                                                      |
| Y3  | Tests de non-régression synchronisation       | D       | bloquée par Y1         | non   | Y1         | `tests/test_ocr.py`                                     |                                                      |
| Y2  | Republication, restauration, file après sync  | S       | bloquée par Y3         | non   | Y1, Y3     | `moodlesync/moteur.py`, `moodlesync/ocr.py`             |                                                      |
| A1  | Mixin `ApiTextes`                             | D       | bloquée par C3, C5     | non   | C3, C5     | `moodlesync/api_textes.py`, `moodlesync/application.py` |                                                      |
| A2  | Recherche, copie, export, ouverture           | D       | bloquée par A1         | non   | A1         | `moodlesync/api_textes.py`                              |                                                      |
| A3  | Revue API et messages                         | S       | bloquée par A2         | non   | A1, A2     | corrections ciblées                                     |                                                      |
| U1  | HTML et CSS de l'onglet Mes textes            | D       | bloquée par E0b        | non   | E0         | `index.html`, `style.css`                               |                                                      |
| U2  | `textes.js` : liste, recherche, copie, export | D       | bloquée par A2, U1     | non   | A2, U1     | `moodlesync/interface/textes.js`                        |                                                      |
| U3  | Panneau « À quoi ça sert ? » et aperçu        | S       | bloquée par C2, U1     | non   | C2, U1     | `textes.js`, `index.html`                               |                                                      |
| U4  | Carte de préparation, consentement, reprise   | S       | bloquée par Y2, U1     | non   | Y2, U1     | `sync.js`, `index.html`                                 |                                                      |
| U5  | Accessibilité, thème sombre, vérification     | D       | bloquée par U1 à U4    | non   | U1 à U4    | `style.css`, `app.js`                                   |                                                      |
| P1  | Dépendances, PyInstaller, builds              | D       | bloquée par C1 à C5    | non   | C1 à C5    | `requirements.txt`, `MoodleSync.spec`                   |                                                      |
| P2  | Tests et CI, moteur facultatif                | D       | bloquée par Y3, A1, U5 | non   | Y3, A1, U5 | `tests/`, `.github/workflows/compilation.yml`           |                                                      |
| P3  | Documentation et exception `remplacer`        | D       | bloquée par toutes     | non   | toutes     | README, LISEZ-MOI, notes, CONTEXTE, CONTRIBUTING, TIERS |                                                      |
| P4  | Audit final des 16 critères                   | S       | bloquée par P1 à P3    | non   | P1 à P3    | rapport court                                           |                                                      |

Tâche ajoutée par rapport au plan d'exécution : E0b. Le plan d'exécution annonce 20 tâches, le tableau en compte 23 : l'écart est signalé, pas corrigé.

## 3. Portes de sortie en cours

| Porte | Condition | État |
|---|---|---|
| Avant S1 | Contrat relu par D (prompt 01, étape B), `docs/` commité (`f14d60f`, fait) | franchie |
| Avant U1 | Plan aligné sur D1 à D7 (E0b) | non franchie |
| Après S1 | Go écrit avec versions, temps par page, console absente, superposition faisable | franchie (go écrit, à valider par la revue de S1 ; console à confirmer visuellement) |
| Avant Y2 | Y1 et Y3 à `fait`, test « synchroniser, remplacer, synchroniser : zéro téléchargement » vert | non franchie |
| Avant P4 | Les 16 critères ont chacun un test vert (table du contrat, section 6) | non franchie |

## 4. Journal des décisions

Chaque ligne : date, auteur, décision, raison, fichiers touchés. Les lignes ne se modifient pas.

| Date | Auteur | Décision | Raison | Fichiers |
|---|---|---|---|---|
| 2026-11-07 | Maxence | Mode par défaut `aucun`, `remplacer` explicite, aucune copie de l'original | Pas de doublement de volume | plan |
| 2026-11-07 | Maxence, via S | D1 à D7 : synchronisation prioritaire, SHA-256 complet, `copie` refusé, clé `moodlesync` dans le front matter, confiance de 0 à 1, paquet portable en 2.6, mise en file automatique sous 50 documents et 500 pages | Contradictions du plan, détail dans le contrat section 7 | `docs/ocr-contrat.md` |

## 5. Journal des tâches

Plus récent en haut. Format imposé, une entrée par fin de tâche, par prise de tâche et par revue. Les prompts de session sont dans `docs/prompts/`.

```text
### AAAA-MM-JJ HH:MM | <ID> | <S ou D ou Maxence> | <prise | fin | revue | écart>
Fait :
Fichiers :
Tests : commande lancée, nombre de tests, échecs (résultat réel collé)
Décisions : (renvoie à la section 4 si une ligne y est ajoutée)
Doutes :
Suivant :
Verdict (revue seulement) : bloquant | important | mineur | rien
```

### 2026-11-07 14:51 | S1 | D | fin
Fait : spike exécuté, `docs/spike-ocr.md` écrit. Réponse go par volet : rendu go, reconnaissance go, console go à confirmer visuellement, superposition go, macOS non testé. Méthode proposée : couche construite depuis le TSV (technique 2).
Fichiers : `docs/spike-ocr.md`.
Tests : `python -m unittest discover -s tests -t . -v` : 277 tests, 0 échec (base inchangée).
Décisions : aucune (valeurs S1 proposées, pas tranchées).
Doutes : absence de console non observée visuellement ; macOS non testé ; pypdf 7.0 a retiré `merge_page` sur page non rattachée (à reporter dans C4).
Suivant : revue de S1 par S.

### 2026-11-07 14:30 | S1 | D | prise
Fait : S1 réservée (propriétaire D), spike lancé sur la machine Windows, mesures dans le dossier temporaire du système.
Fichiers : aucun (mesures hors dépôt).
Tests : `python -m unittest discover -s tests -t . -v` : 277 tests, 0 échec.
Décisions : aucune.
Doutes : aucun.
Suivant : exécution du spike.

### 2026-11-07 14:20 | E0 | D | revue
Fait : revue ciblée de E0 (contrat) contre le code et le plan. Faits du dépôt tous vérifiés, aucune contradiction avec D1 à D7. 3 constats importants et 5 mineurs, aucun bloquant. E0 passe à `fait`.
Fichiers : aucun modifié.
Tests : `python -m unittest discover -s tests -t . -v` : 277 tests, 0 échec.
Décisions : E0 relue, non rejetée (Relue : oui, D).
Doutes : import circulaire `deja_present`/`lire_marque` à résoudre en Y1 ; vocabulaire `type`/`extraction` à préciser avant C5 et A2.
Suivant : S1, puis revue de S1 par S.
Verdict (revue seulement) : important (3), mineur (5), rien de bloquant.

### 2026-11-07 | E0 | S | écart
Fait : les quatre documents de préproduction sont commités (`f14d60f`, auteur MarinWasAsleep). Prompt 01 écrit pour D : revue de E0, puis S1 si E0 n'est pas rejetée, puis préparation du prompt suivant.
Fichiers : `docs/prompts/01-revue-E0-puis-S1-D.md`, ce fichier.
Tests : aucun lancé, aucun code produit.
Décisions : la porte « avant S1 » exige la relecture de E0 par D, pas l'alignement du plan (E0b), qui ne bloque que U1.
Doutes : D n'a pas encore confirmé qu'il dispose d'un shell et d'un accès au dépôt ; Tesseract n'a pas été vérifié sur la machine par S.
Suivant : D exécute le prompt 01.

### 2026-11-07 | E0 | S | fin
Fait : contrat `docs/ocr-contrat.md` écrit puis révisé après les réponses de Maxence aux sept points à trancher.
Fichiers : `docs/ocr-contrat.md` (nouveau, non commité).
Tests : aucun lancé, aucun code produit. Contrôle fait : zéro tiret long dans le contrat.
Décisions : D1 à D7 (section 4).
Doutes : 360 lignes pour une cible de 300 ; propositions « à confirmer » listées en bas de la section 7 du contrat ; contrat jamais relu par D.
Suivant : relecture du contrat par D, puis E0b, puis S1.

## 6. Écarts ouverts

Une ligne par désaccord ou incohérence découvert. Un écart se ferme par une entrée de journal qui le cite.

| # | Découvert par | Écart | Concerne | État |
|---|---|---|---|---|
| 1 | S | Le plan 3.4, 3.3, 4.3, 4.4, 4.5, 5.5, 5.6, 5.9, 5.10 et 9 contredisent D1 à D7 | `docs/plan-ocr.md` | ouvert (E0b) |
| 2 | S | Le plan d'exécution annonce 20 tâches pour 22 identifiants listés | `docs/plan-execution-ocr.md` | ouvert |
| 3 | S | `CONTRIBUTING.md` dit « ne jamais écraser un fichier de l'utilisateur » : l'exception `remplacer` doit y être écrite | `CONTRIBUTING.md` | ouvert (P3) |
| 4 | D | `ocr_documents` renvoie `type` « texte|scanne|mixte », le cache porte `extraction` « texte|ocr|mixte » et `decider_source` « texte|ocr » ; « scanne » et « ocr » désignent la même chose, et le filtre `type` n'accepte pas « mixte » | `docs/ocr-contrat.md` 2.3, 2.7, 3.1 | ouvert |
| 5 | D | `ocr_ouvrir` « refuse tout chemin hors dest » alors que `ocr_sortie_hors_coffre` autorise des textes hors du coffre | `docs/ocr-contrat.md` 3.1, 3.2 | ouvert |
| 6 | D | `deja_present` (moteur.py) doit appeler `ocr.lire_marque` (étape 4), or `ocr.py` importe `moteur` : import circulaire non traité | `docs/ocr-contrat.md` 3.3, 3.1 | ouvert |
| 7 | D | `reglages_depuis` renvoie `oem` et `tessdata`, absents des clés d'invalidation du cache (langues, dpi, psm, moteur) | `docs/ocr-contrat.md` 3.1, 2.3 | ouvert |
| 8 | D | vocabulaire `qualite` (`classer` : bon, a_verifier, difficile, vide) contre `etat` du cache (ok, a_verifier, difficile, erreur, ignore) : le passage de « bon » à « ok » n'est pas précisé | `docs/ocr-contrat.md` 2.3, 3.1, 2.7 | ouvert |
| 9 | D | `pdf_range` (3.3) laisse ambigu le cas `fichier["taille"]` inconnu (« quand elle est connue ») | `docs/ocr-contrat.md` 3.3 | ouvert |
| 10 | D | le filtre `qualite: "orphelin"` de `ocr_documents` filtre le booléen `orphelin`, pas la clé `qualite` | `docs/ocr-contrat.md` 2.7 | ouvert |
| 11 | D | `liste_maj` avec `ancien = None` casse `ecrire_note` (`lien(ancien)` sur None) ; le contrat le signale comme « à vérifier » | `docs/ocr-contrat.md` 3.3, `moodlesync/moteur.py` | ouvert |
