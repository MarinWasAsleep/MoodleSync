# OCR : tableau d'avancement partagé

Ce fichier est la **seule source de vérité** sur l'état du chantier OCR. Il est lu et mis à jour par les deux IA (S = Claude Sonnet, D = DeepSeek v4.1 flash) et par Maxence.
**Nom de D** : à partir du 7 novembre 2026 (après le prompt 10), D est DeepSeek v4.1 flash et non plus DeepSeek v4 pro. Les prompts 01 à 09 et les entrées de journal antérieures écrivent « DeepSeek v4 pro » : ils sont historiques et ne sont pas réécrits. Tout prompt, journal ou document nouveau écrit « DeepSeek v4.1 flash » (ou « D ») pour la place D, et ne reprend pas l'ancien nom par recopie d'un prompt précédent.
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

Dernière mise à jour : 7 novembre 2026, par S (fin de C2). Prompts de session : `docs/prompts/` (un fichier par étape, chaînés, voir le prompt 01, étape D). Base de tests actuelle : **verte, 308 tests** (289 plus 19 tests ajoutés par C2, dont T1, T2, T3, T4, T7 et T29 ; mesurée par S à l'ouverture, 289, et à la clôture, 308).

| ID  | Tâche                                         | Proprio | État                   | Relue | Dépend de  | Fichiers                                                | Preuve                                                                                              |
| --- | --------------------------------------------- | ------- | ---------------------- | ----- | ---------- | ------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| E0  | Contrat d'interface                           | S       | fait                   | oui   | plan       | `docs/ocr-contrat.md`                                   | commit `f14d60f`, revue D (prompt 01, étape B)                                                      |
| E0b | Aligner `plan-ocr.md` sur D1 à D7             | S       | fait                   | oui   | E0         | `docs/plan-ocr.md`                                      | commit `426be86`, revue D (prompt 04, étape B) : verdict rien, plan aligné, écart 1 fermé        |
| S1  | Spike pypdfium2 et Tesseract TSV              | D       | fait                   | oui   | E0         | `docs/spike-ocr.md`                                     | commit `67148fa`, revue S (prompt 02, étape B) : go Windows, 6 importants et 5 mineurs en section 6 |
| C1  | Détection du moteur et configuration          | D       | fait                   | oui   | E0, S1     | `moodlesync/ocr.py`                                     | commits `3568782` puis `6551b9f` (correction), revue S (prompt 08, étape B) : verdict mineur, écarts 39 à 42 |
| C2  | Texte natif, TSV, Markdown par document       | S       | à relire               | non   | E0, S1     | `moodlesync/ocr.py`                                     | commit de C2 (hash à noter par le relecteur), revue D attendue (prompt 10)                        |
| C3  | Cache, empreinte, reprise, file               | S       | bloquée par C2         | non   | C2         | `moodlesync/ocr.py`                                     |                                                                                                     |
| C4  | PDF cherchable, superposition, vérification   | S       | bloquée par C2         | non   | C2         | `moodlesync/ocr.py`                                     |                                                                                                     |
| C5  | Markdown de cours, index, qualité, JSONL      | D       | bloquée par C2         | non   | C2         | `moodlesync/ocr.py`                                     |                                                                                                     |
| Y1  | État de synchronisation et `deja_present`     | S       | bloquée par C3, C4     | non   | C3, C4     | `moodlesync/moteur.py`, `moodlesync/seances.py`         |                                                                                                     |
| Y3  | Tests de non-régression synchronisation       | D       | bloquée par Y1         | non   | Y1         | `tests/test_ocr.py`                                     |                                                                                                     |
| Y2  | Republication, restauration, file après sync  | S       | bloquée par Y3         | non   | Y1, Y3     | `moodlesync/moteur.py`, `moodlesync/ocr.py`             |                                                                                                     |
| A1  | Mixin `ApiTextes`                             | D       | bloquée par C3, C5     | non   | C3, C5     | `moodlesync/api_textes.py`, `moodlesync/application.py` |                                                                                                     |
| A2  | Recherche, copie, export, ouverture           | D       | bloquée par A1         | non   | A1         | `moodlesync/api_textes.py`                              |                                                                                                     |
| A3  | Revue API et messages                         | S       | bloquée par A2         | non   | A1, A2     | corrections ciblées                                     |                                                                                                     |
| U1  | HTML et CSS de l'onglet Mes textes            | D       | bloquée par E0b        | non   | E0         | `index.html`, `style.css`                               |                                                                                                     |
| U2  | `textes.js` : liste, recherche, copie, export | D       | bloquée par A2, U1     | non   | A2, U1     | `moodlesync/interface/textes.js`                        |                                                                                                     |
| U3  | Panneau « À quoi ça sert ? » et aperçu        | S       | bloquée par C2, U1     | non   | C2, U1     | `textes.js`, `index.html`                               |                                                                                                     |
| U4  | Carte de préparation, consentement, reprise   | S       | bloquée par Y2, U1     | non   | Y2, U1     | `sync.js`, `index.html`                                 |                                                                                                     |
| U5  | Accessibilité, thème sombre, vérification     | D       | bloquée par U1 à U4    | non   | U1 à U4    | `style.css`, `app.js`                                   |                                                                                                     |
| P1  | Dépendances, PyInstaller, builds              | D       | bloquée par C1 à C5    | non   | C1 à C5    | `requirements.txt`, `MoodleSync.spec`                   |                                                                                                     |
| P2  | Tests et CI, moteur facultatif                | D       | bloquée par Y3, A1, U5 | non   | Y3, A1, U5 | `tests/`, `.github/workflows/compilation.yml`           |                                                                                                     |
| P3  | Documentation et exception `remplacer`        | D       | bloquée par toutes     | non   | toutes     | README, LISEZ-MOI, notes, CONTEXTE, CONTRIBUTING, TIERS |                                                                                                     |
| P4  | Audit final des 16 critères                   | S       | bloquée par P1 à P3    | non   | P1 à P3    | rapport court                                           |                                                                                                     |

Tâche ajoutée par rapport au plan d'exécution : E0b. Le plan d'exécution annonce 20 tâches, le tableau en compte 23 : l'écart est signalé, pas corrigé.

## 3. Portes de sortie en cours

| Porte | Condition | État |
|---|---|---|
| Avant S1 | Contrat relu par D (prompt 01, étape B), `docs/` commité (`f14d60f`, fait) | franchie |
| Avant U1 | Plan aligné sur D1 à D7 (E0b) | franchie (E0b relue et passée à `fait` par D le 7 novembre 2026, verdict rien, écart 1 fermé) |
| Après S1 | Go écrit avec versions, temps par page, console absente, superposition faisable | franchie (S1 relue et `fait` par S ; go limité à Windows ; console absente établie par déduction, voir l'entrée de revue de S1, confirmation visuelle encore souhaitée) |
| Après C1 | Registre, chemins, langues, `--tessdata-dir`, erreurs lisibles (plan d'exécution, section 3), C1 relue | franchie (C1 relue et `fait` par S le 7 novembre 2026, verdict mineur ; `ocr.detecter({})` renvoie `present: True` sur la machine de développement ; macOS non exécuté) |
| Après C2 | Page native sans reconnaissance (T2, zéro appel à `executer`) et page scannée avec confiance (T29, ou T1 et T3 par doublure) ; C2 relue | atteinte côté tests le 7 novembre 2026 (T2 vert, T29 exécuté avec le vrai moteur 5.5.3) ; **non franchie** tant que la revue de C2 n'est pas faite ; rendu réel d'une page de PDF non exercé (`pypdfium2` absent) |
| Avant C4 | Valeurs S1 du contrat tranchées par Maxence et reportées dans `docs/ocr-contrat.md` : méthode de la couche de texte (et nom de la technique), tolérance du rendu, borne de volume, version de pypdf (écarts 12 à 16) | franchie le 7 novembre 2026 (D8 à D11, contrat section 7) ; reste la mesure d'une page réelle dense par C4 (D10) |
| Avant Y2 | Y1 et Y3 à `fait`, test « synchroniser, remplacer, synchroniser : zéro téléchargement » vert | non franchie |
| Avant P4 | Les 16 critères ont chacun un test vert (table du contrat, section 6) | non franchie |

## 4. Journal des décisions

Chaque ligne : date, auteur, décision, raison, fichiers touchés. Les lignes ne se modifient pas.

| Date | Auteur | Décision | Raison | Fichiers |
|---|---|---|---|---|
| 2026-11-07 | Maxence | Mode par défaut `aucun`, `remplacer` explicite, aucune copie de l'original | Pas de doublement de volume | plan |
| 2026-11-07 | Maxence, via S | D8 à D11 : couche TSV en flux brut (Helvetica WinAnsi, caractère hors cp1252 omis de la couche), écart de rendu maximal 0 à 150 DPI sur 3 pages, borne de 10 Ko par page reconnue en flux compressé sans plafond absolu, pypdf 6.21.4 conservé, seuils 0,85 et 0,70 non calibrés, `pypdfium2` en import paresseux | Revue de S1 (écarts 12 à 17), toutes recommandations de S acceptées | `docs/ocr-contrat.md` |
| 2026-11-07 | Maxence, via S | D1 à D7 : synchronisation prioritaire, SHA-256 complet, `copie` refusé, clé `moodlesync` dans le front matter, confiance de 0 à 1, paquet portable en 2.6, mise en file automatique sous 50 documents et 500 pages | Contradictions du plan, détail dans le contrat section 7 | `docs/ocr-contrat.md` |
| 2026-11-07 | S | C2 : `extraire_page` gagne `exe` (chemin du moteur, absent de `reglages_depuis`) et `avec_boites` ; `ecrire_document_md(chemin_md, chemin_rel, pages, reglages, *, illisibles=(), date="") -> bool` fixée ; `ErreurOcr(code, **champs)` ; conventions de C1 (`langues_effectives == ""`, `tessdata == ""`) écrites au contrat | `reglages_depuis` ne doit pas changer de forme (le bloc `reglages` des reprises et du cache en dépend) ; C2 ne lit jamais `cfg` | `docs/ocr-contrat.md` 2.4, 2.7, 3.1 |
| 2026-11-07 | Maxence, via S | La place D passe de DeepSeek v4 pro à DeepSeek v4.1 flash (nom donné par Maxence, formulation officielle non vérifiée) ; prompts 01 à 09 et journal antérieur non réécrits ; prompt 10 et `plan-execution-ocr.md` mis à jour | Éviter qu'un prompt ou une entrée nouvelle confonde les deux modèles | `docs/ocr-avancement.md` (protocole, tête), `docs/plan-execution-ocr.md`, `docs/prompts/10-C2-D.md` |

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

### 2026-11-07 20:15 | C2 | S | fin
Fait : C2, partie extraction d'une page dans `moodlesync/ocr.py` : `ErreurOcr` (sous-classe de `ms.Erreur`, `code`, message de `MESSAGES`), messages `protege`, `illisible`, `corrompu`, `rendre_page`, `parser_tsv`, `reconstruire`, `decider_source`, `classer`, `extraire_page`, `ecrire_document_md`. Écart 41 fermé (docstring `equ`), écart 42 fermé (conventions au contrat 2.7 et 3.1). Tests écrits d'abord : 18 des 19 nouveaux échouaient (`AttributeError`), le 19e (absence de `urllib` et `socket` dans la source) passait déjà ; tous passent avec le code.

**Partition de périmètre (choix de lecture, pas une règle du contrat).** Le contrat ne dit pas quelle tâche porte chaque fonction. J'applique le plan d'exécution, section 3 : C2 = texte natif, reconnaissance, TSV, Markdown par document ; C3 = cache, empreinte, reprise, file. Écrites ici : les fonctions ci-dessus. Non écrites : `controler_pdf` (C4), `extraire_document` et `traiter_document` (C3), `apercu` (U3), cache, reprise, file (C3), PDF cherchable (C4), Markdown de cours, index, qualité, JSONL (C5), `identite`, `lire_marque`. La partition n'a pas bloqué.

**Choix déduits ou décidés (à relire)**
1. Moteur absent ou sans langue : `ErreurOcr("moteur_absent")` si `exe` est vide, sinon `ErreurOcr("langue_manquante")` si `reglages["langues"] == ""`. Le contrôle vient après le texte natif : une page native suffisante n'exige aucun moteur.
2. `exe` : `reglages_depuis` ne porte pas le chemin du moteur et sa forme ne change pas. `extraire_page` prend `exe=""` en argument nommé (valeur de `detecter(cfg)["exe"]`). `reglages_depuis` relançant `detecter` (écart 35), l'appelant (C3, C4, U3) devra détecter une fois et passer `exe`.
3. `boites` : `avec_boites=False` en argument nommé, l'appelant passe vrai si `cfg["ocr_pdf"] == "remplacer"` (C4). Alors `[[x, y, l, h, confiance 0 à 1, mot]]` dans l'ordre du TSV, y compris les mots à confiance négative (C4 filtre) ; sinon `None`.
4. `parser_tsv` divise par 100 (D5) et garde une confiance négative négative ; `reconstruire` l'ignore dans la moyenne mais garde le mot dans le texte. Confiance arrondie à 3 décimales dans `reconstruire` (cache 2.3) : la valeur stockée fait foi pour `classer`.
5. `reconstruire` : un saut de ligne entre les lignes, **une ligne vide entre les paragraphes** (le plan 5.4 ne parle que de saut de ligne ; déduit).
6. Page PDF sans assez de texte natif : reconnue si elle a une image **ou** un peu de texte natif (moins de 80 caractères) ; « vide » seulement sans aucun caractère alphanumérique natif et sans image (lecture de T3, déduit). Détection d'image par `page.images` de pypdf ; en cas d'exception, on suppose une image. Une page dont le texte est dessiné en vecteurs, sans texte ni image, sort « vide » (T3 le veut ainsi).
7. Normalisation du texte natif : NFC, caractères de contrôle et de format retirés, espaces multiples, mot coupé en fin de ligne recollé **seulement avant une minuscule** (« Jean-\nPaul » et « 1990-\n2000 » intacts), trois sauts de ligne ou plus ramenés à deux.
8. PDF chiffré : ouvert si le mot de passe utilisateur est vide (comme n'importe quel lecteur, rien n'est contourné), sinon `protege`. Si le déchiffrement lève une exception (par exemple chiffrement AES sans la dépendance de chiffrement de pypdf, **non vérifié**), il est classé `protege`. Fichier absent ou illisible : `corrompu` (le contrat n'a pas d'autre message).
9. `rendre_page` : PDF par `pypdfium2` (import paresseux, D11), rendu RVB puis conversion en gris et autocontraste par Pillow ; image isolée par Pillow (transparence composée sur blanc, rotation EXIF, `numero` = cadre). Sans `pypdfium2`, `ErreurOcr("illisible")` (le contrat n'a pas de message dédié, aucun n'est inventé) ; le détail va dans `erreurs.txt`.
10. Annulation : `arreter()` vrai avant le rendu ou après un code de retour non nul lève `ms.Annule`, pas `illisible`. Code non nul sans demande d'arrêt, ou délai de 120 s écoulé : `illisible`, détail dans `erreurs.txt` par `ms.message_erreur`.
11. Markdown : clé de front matter `moodlesync`, `cours` et `section` déduits des deux premiers composants de `chemin_rel` (omis s'ils n'existent pas), `langues`, `confiance` et `moteur` écrits seulement s'il y a des pages reconnues. « Pages à vérifier » = pages que `classer` ne met pas à « bon » (une page native vaut « bon »), pages sans texte détecté (source « vide », ou reconnue sans mot) et pages illisibles : lecture du plan 6.1 et 4.4, **déduite**. Les pages illisibles arrivent par l'argument nommé `illisibles` (liste de numéros) car `extraire_page` les lève au lieu de les renvoyer. `confiance` du document = moyenne des pages reconnues pondérée par leurs mots. Affichage « 0,75 » arrondi à 2 décimales (près d'un seuil, « 0,85 » peut s'afficher pour 0,849 ; cosmétique).
12. T7 est rattaché à C2 parce que C2 écrit le `.md` (`ecrire_document_md`). `_resume_pages` reste privée ; C3 peut la promouvoir.
13. `ocr.py` importe `moodlesync.moteur` pour `ErreurOcr(ms.Erreur)` et `message_erreur`. `moteur` importe `urllib` : l'invariant 6 est lu comme « `ocr.py` n'appelle et ne contient ni `urllib` ni `socket` » (un test le vérifie sur le texte du fichier), pas « aucun module chargé n'en importe un ». T22 (C3) est le test qui le vérifie en comportement.

Fichiers : `moodlesync/ocr.py`, `tests/test_ocr.py`, `docs/ocr-contrat.md` (2.4, 2.7, 3.1 : conventions de C1, signatures de la partie « Une page », `ErreurOcr`, `ecrire_document_md`, `boites`), `docs/ocr-avancement.md`, `docs/prompts/10-C2-D.md`.
Tests : `python -m unittest discover -s tests -t . -v` : 308 tests, 0 échec (289 existants plus 19). Numérotés : T1 `test_tsv_accents`, T2 `test_natif_contre_ocr`, T3 `test_page_mixte`, T4 `test_confiance_niveaux`, T7 `test_sortie_editee_conservee`, T29 `test_moteur_reel`. **T29 a tourné** (vrai moteur 5.5.3, ignoré seulement si moteur ou Pillow manquent) ; il lit « Bonjour le monde » et « Politique sociale » dessinés avec Pillow. Les 13 autres tests nouveaux n'ont pas de numéro T (TSV mal formé, normalisation, erreurs lisibles, PDF protégé et corrompu, page hors borne, `pypdfium2` absent, rendu d'image, absence de `urllib` et `socket`, forme du Markdown, document natif, écriture atomique, `boites`, `tessdata` vide). Le message « Ma semaine (mode automatique) : erreur imprévue » en fin de sortie est émis par un test existant, pas un échec. Zéro cadratin et zéro demi-cadratin dans `ocr.py`, `test_ocr.py` et `ocr-contrat.md` (comptage par code de caractère). Le journal `erreurs.txt` réel n'a pas été touché par les tests (daté du 6 novembre, les tests le redirigent).
Décisions : une ligne ajoutée à la section 4 (signatures et conventions).
Doutes : (1) **le rendu réel d'une page de PDF n'est pas exercé** : `pypdfium2` n'est pas installé dans l'environnement du projet (mesuré), `_rendre_pdf` (`PdfDocument`, `page.render(scale=...).to_pil()`) est écrit d'après l'API de la version 5.15.0 vue par le spike, **non exécuté** ; tous les tests de PDF passent par une doublure de `rendre_page`, T29 passe par une image isolée ; (2) macOS non exécuté ; (3) `pypdfium2` doit entrer dans `requirements.txt` (P1, fichier non touché ici ; wheel macOS 13 et plus seulement, écart 17) ; (4) `_ouvrir_pdf` garde le dernier lecteur pypdf en mémoire (pypdf lit le fichier entier dans un `BytesIO` et ne garde aucun descripteur ouvert, vérifié dans le code de pypdf 6.21.4) : un PDF de 300 Mo reste en mémoire jusqu'au PDF suivant, à ramener par C3 si gênant ; (5) plan 5.3, images isolées : le redimensionnement des images trop petites et la règle du GIF (première image seulement) ne sont pas faits, un GIF animé compte ses cadres comme des pages ; (6) écarts 39 et 40 non traités, comme demandé ; (7) l'heure de cette entrée est celle de l'horloge de la machine.
Suivant : revue de C2 par D (prompt 10, règle de choix point 1 : C2 est la seule tâche à relire).

### 2026-11-07 20:10 | C2 | S | prise
Fait : C2 reprise (prompt 09). Dépendances E0 et S1 à l'état `fait` et relues (E0 relue par D, S1 relue par S). C1 `fait` et relue. Lecture du journal (revue de C1, écarts 4, 8, 39 à 42), du contrat (1, 2.3, 2.4, 2.6, 3.1, 4, 5, 6, 7), du plan (4.2, 4.4, 5.3, 5.4, 6.1), du rapport de spike, de `ocr.py` et `test_ocr.py` (état après `f3bb580`) avant toute modification.
Faits de la machine de développement (rien installé) : Tesseract 5.5.3 détecté (`ocr.detecter({})["present"]` renvoie `True`), Pillow et pypdf présents, **`pypdfium2` absent** (mesuré par `importlib.util.find_spec`). Le rendu réel d'une page de PDF ne peut donc pas être exercé ici.
Fichiers : `docs/ocr-avancement.md` (état et cette entrée).
Tests : `python -m unittest discover -s tests -t . -v` : 289 tests, 0 échec (base inchangée). Le message « Ma semaine (mode automatique) : erreur imprévue » affiché en fin de sortie est émis par un test existant, pas un échec.
Décisions : aucune.
Doutes : aucun à ce stade.
Suivant : tests qui échouent (T1, T2, T3, T4, T7, T29), puis `moodlesync/ocr.py` (partie extraction d'une page).

### 2026-11-07 19:58 | C1 | S | revue
Fait : revue de la correction de C1 (prompt 08), diff `HEAD~1..HEAD` (commit `6551b9f`) de `moodlesync/ocr.py` et `tests/test_ocr.py` lu en entier, contrat (2.7, 3.1, 3.2, invariants 6, 9 et 16, section 5, T25), plan (5.2, 5.6) et rapport de spike relus. **Aucun bloquant, aucun important, 4 mineurs** (écarts 39 à 42). C1 passe à `fait` (Relue : oui, S). Porte « Après C1 » franchie.

Les 16 constats de ma revue précédente, vérifiés un par un dans le code et par exécution :
- 1 (bloquant, « v » de la version) : corrigé, `RE_VERSION` accepte `v?` ; la doublure de T25 reprend la sortie réelle (« v », CRLF, en-tête de `--list-langs`).
- 2 (`--tessdata-dir` sur `--list-langs`) : corrigé, le dossier est déterminé avant l'appel ; test `test_list_langs_avec_tessdata_dir`.
- 3 (dossier de données inexistant) : corrigé, `_dossier_tessdata` ne renvoie qu'un dossier existant, sinon `""`.
- 4 (repli sur `osd`, `eng` avant `fra`) : corrigé, `osd` et `equ` exclus, `fra` puis `eng`.
- 5 et 6 (repli silencieux, `-l ""`) : corrigé, `message` vaut `MESSAGES["langue_manquante"]` dès que `repli` est vrai, y compris avec `langues_effectives` vide.
- 7 (garde `os.name`) : corrigé dans le code, **non exerçable sur Windows** (déduit pour macOS, rien exécuté sur macOS) ; voir écart 39.
- 8 (`stdout + stderr`) : corrigé pour `--version` et `--list-langs` ; test `test_version_et_langues_sur_stderr`.
- 9 (processus tué dans un `finally`) : corrigé, vérifié à la main (un `arreter` qui lève renvoie `(-1, b"", b"")` en 0,24 s, le processus enfant est terminé) ; aucun test ne le couvre, écart 39.
- 10 (`BLOC_ABSENT` partagé) : corrigé par `copy.deepcopy` ; aucun test, écart 39.
- 11 (valeur de registre non texte) : corrigé, `isinstance(dossier, str)` ; test `test_registre_valeur_non_texte`.
- 12 : laissé ouvert comme demandé (écart 34), code inchangé sur l'ordre `ocr_tessdata`, `TESSDATA_PREFIX`, programme.
- 13 : corrigé pour `int()` avec `ValueError` et `TypeError` ; la relance de `detecter` reste pour C3 (écart 35). Reste `OverflowError`, écart 40.
- 14 (tests) : couverts, 11 tests sans numéro T ajoutés ; T25 reste le seul test numéroté.
- 15 (`RE_LANGUE`) : corrigé, `chi_sim`, `deu_frak`, `fra` gardés, `script/Latin` ignoré.
- 16 : laissé ouvert comme demandé (écart 38), code inchangé.
Écarts 23 à 33, 36 et 37 : fermés, confirmés par cette revue. 35 : fermé pour `int()`, relance de `detecter` pour C3. 34 et 38 : ouverts, décisions de Maxence.

Constats (gravité, section, problème, correction) :
1. **Mineur**, contrat 6 (T25) et prompt 07 (« les tests échouent sans l'implémentation ») : les corrections des constats 9 et 10, et celle du constat 7, ne sont couvertes par aucun test qui échoue sans elles. Mesuré : face à l'ancien `ocr.py` (commit `3568782`), 10 des 12 tests de `tests/test_ocr.py` échouent (9 échecs, 1 erreur) ; les deux qui passent sont `test_executer_sous_processus_reel` et `test_executer_creationflags_windows`. Ce dernier ne vérifie que `CREATE_NO_WINDOW` (`0x08000000`), pas la priorité basse (`0x4000`). Correction : trois tests courts, sans numéro T : un `arreter` qui lève avec un `Popen` enveloppé pour vérifier que le processus est terminé ; un bloc absent dont on modifie la liste `langues` sans toucher au suivant ; `ocr.os.name` posé à `"posix"` avec un `winreg` simulé pour exercer la sortie par registre sans la garde.
2. **Mineur**, contrat 3.1 (« ne lève jamais ») et 3.2 (bornes de `ocr_dpi` et `ocr_psm`) : une configuration éditée à la main reste mal traitée. Mesuré : `detecter({"ocr_exe": 5})`, `{"ocr_tessdata": 5}`, `{"ocr_langues": 5}` renvoient `present: False` sur la machine où `detecter({})` renvoie `True` (l'`AttributeError` de `.strip()` ou `.split()` est avalée, le moteur est déclaré absent à tort) ; `reglages_depuis({"ocr_dpi": float("inf")})` lève `OverflowError` (le module `json` accepte `Infinity`) ; `ocr_dpi: 0` donne `dpi == 0` sans borne. Correction : ne lire que les valeurs `str` pour les trois clés texte (sinon la valeur par défaut), attraper aussi `OverflowError`, et décider si les valeurs hors bornes de 3.2 sont ramenées à 300 et 3 à la lecture ou laissées à `ocr_regler` (A1) ; la décision est à écrire.
3. **Mineur**, `moodlesync/ocr.py`, docstring de `_langues_effectives` : « osd et equ (orientation et equipement) » est inexact. `equ.traineddata` est le module de détection d'équations de Tesseract [mémoire IA, à vérifier]. L'exclusion de `equ` reste juste. Correction : « osd (orientation) et equ (équations) ».
4. **Mineur**, contrat 2.7 et 3.1 : deux conventions créées par la correction ne vivent que dans les docstrings de `ocr.py` : `langues_effectives == ""` avec `repli` vrai et `message` de `langue_manquante` signifie « moteur sans langue utilisable » (C2 ne lance pas `-l ""`) ; `tessdata == ""` signifie « ne pas passer `--tessdata-dir` ». C2 les lit. Correction : les écrire en 2.7 et 3.1, dans le commit de C2 (le contrat est à S, protocole section 1).

Vérifié sans constat : signatures (`executer(args, *, delai, arreter)` renvoie `(code, stdout, stderr)` en octets ; `detecter` renvoie les clés de 2.7 plus `tessdata` et `majeure` ; `reglages_depuis` renvoie `{"langues", "dpi", "psm", "oem": 1, "moteur", "tessdata"}`) ; constantes `CACHE`, `SEUIL_TEXTE`, `SEUILS_QUALITE`, `MESSAGES` inchangées ; liste d'arguments, jamais de shell, `CREATIONFLAGS = 0x08000000 | 0x4000` sous `nt` seulement ; délai borné, `communicate(timeout=1)` après `kill` ; ordre `config`, `path`, `registre`, `usuel` ; version 4 ou 5 exigée, version 3 absente ; imports `copy, os, re, shutil, subprocess, sys, time` seulement (aucun `urllib` ni `socket`, invariant 6) ; `detecter` ne lève jamais et n'écrit aucune trace (invariant 9) ; zéro cadratin et zéro demi-cadratin dans `ocr.py` et `test_ocr.py` (comptage par code de caractère) ; identifiants en français sans accent.
Vérification en lecture seule : `python -c "from moodlesync import ocr; print(ocr.detecter({})['present'])"` renvoie `True` ; bloc complet lu sans afficher les chemins : version `5.5.3`, source `registre`, majeure 5, langues `eng, fra, osd`, `langues_effectives` `fra+eng`, `repli` faux, `message` vide, `tessdata` renseigné. Essais faits dans le dossier temporaire de la session, rien d'installé, `ocr.py` et `test_ocr.py` non modifiés.
Fichiers : `docs/ocr-avancement.md` (état, porte, journal, écarts 39 à 42), `docs/prompts/09-C2-S.md`.
Tests : `python -m unittest discover -s tests -t . -v` : 289 tests, 0 échec à l'ouverture, puis 289 tests, 0 échec à la clôture (base inchangée). Le message « Ma semaine (mode automatique) : erreur imprévue » en fin de sortie est émis par un test existant, pas un échec.
Décisions : aucune dans la section 4.
Doutes : (1) macOS entièrement non exécuté, la sortie par registre sans garde et le chemin Homebrew sont déduits ; (2) la forme de `--version` des versions 4.x n'est pas mesurée ; (3) plan 5.2, dernière puce (langues réparties entre deux dossiers : choisir celui qui contient `fra` et `eng`) : non implémentée, elle ne figure pas dans le contrat 3.1 et dépend de la décision de Maxence sur l'écart 34 ; (4) la ligne U1 du tableau dit « bloquée par E0b » alors que E0b est `fait` : état périmé, non corrigé ici ; (5) `pypdfium2` n'est pas installé dans l'environnement du projet (mesuré), ce qui touche C2 (T29) ; (6) l'heure de cette entrée est celle de l'horloge de la machine.
Suivant : C2 (texte natif, TSV, Markdown par document), propriétaire S, prompt 09 pour une session neuve (règle de choix, point 3 : aucune tâche à relire ni rejetée, C2 est la première tâche prête dans l'ordre de la section 9 du plan d'exécution).
Verdict (revue seulement) : mineur

### 2026-11-07 18:50 | C1 | D | fin
Fait : correction de C1 (prompt 07), les 16 constats de la revue repris un par un. 1 (bloquant) RE_VERSION accepte un « v » optionnel, corrigé. 2 --list-langs reçoit --tessdata-dir quand le dossier est connu, corrigé. 3 _dossier_tessdata ne renvoie qu'un dossier qui existe, sinon chaîne vide, corrigé. 4 _langues_effectives exclut osd et equ, préfère fra puis eng, corrigé. 5 et 6 message langue_manquante dès que repli est vrai, corrigé. 7 garde os.name retirée de _exe_registre, corrigé. 8 --version et --list-langs lus sur stdout + stderr, corrigé. 9 executer tue le processus dans un finally et borne le dernier communicate, corrigé. 10 BLOC_ABSENT copié par deepcopy, corrigé. 11 _exe_registre ne retient que les valeurs str, corrigé. 12 ordre du dossier de données : laissé ouvert (décision de Maxence). 13 reglages_depuis prend 300 et 3 si ocr_dpi ou ocr_psm est illisible, corrigé (la relance de detecter reste ouverte pour C3). 14 tests ajoutés pour config, path, usuel, version 3, moteur absent et executer, corrigé. 15 RE_LANGUE garde chi_sim et deu_frak, corrigé. 16 message d'une version 3 : laissé ouvert (décision de Maxence). Écarts 23 à 38 fermés, sauf 34 et 38 (décisions de Maxence) et la relance de 35 (C3).
Fichiers : moodlesync/ocr.py, tests/test_ocr.py, docs/ocr-avancement.md, docs/prompts/08-C1-S.md.
Tests : python -m unittest discover -s tests -t . -v : 289 tests, 0 échec (278 existants plus 11 tests ajoutés, T25 corrigé). ocr.detecter({}) sur la machine de développement renvoie present: True (version 5.5.3, source registre). Zéro tiret long dans ocr.py et test_ocr.py (comptage par code de caractère).
Décisions : aucune dans la section 4.
Doutes : (1) la forme des versions 4.x de tesseract n'est pas mesurée, le « v » est accepté par prudence ; (2) le constat 7 (macOS) et la levée d'ImportError hors Windows sont déduits, rien n'est exécuté sur macOS ici ; (3) l'heure de cette entrée est celle de l'horloge de la machine.
Suivant : revue de C1 par S (prompt 08), règle de choix point 1 (tâche à relire la plus ancienne).

### 2026-11-07 18:48 | C1 | D | prise
Fait : C1 reprise (correction, prompt 07). Dépendances E0 et S1 à l'état fait et relues. Lecture du journal (entrée revue de S, constats 1 à 16), du contrat (2.7, 3.1, 3.2, 4, 5, 6), du plan (5.2, 5.6), du spike, de ocr.py et test_ocr.py (commit 3568782) et de compilation.yml (jobs macos et windows) avant toute modification.
Fichiers : docs/ocr-avancement.md (état et cette entrée).
Tests : python -m unittest discover -s tests -t . -v : 278 tests, 0 échec (base inchangée). Le message « Ma semaine (mode automatique) : erreur imprévue » affiché en fin de sortie est émis par un test existant, pas un échec.
Décisions : aucune.
Doutes : aucun à ce stade.
Suivant : tests qui échouent, puis moodlesync/ocr.py corrigé constat par constat.

### 2026-11-07 18:28 | C1 | S | revue
Fait : revue ciblée de `moodlesync/ocr.py` et `tests/test_ocr.py` (prompt 06), diff `HEAD~1..HEAD` lu en entier, contrat (2.7, 3.1, 3.2, invariants 6, 9 et 16, section 5, T25), plan (5.2, 5.6) et rapport de spike relus. **1 bloquant, 6 importants, 9 mineurs.** C1 passe à `rejetée` (Relue : non). Retour à D, prompt 07.
Vérifications faites sur la machine de développement (Tesseract installé, `HKLM\SOFTWARE\Tesseract-OCR`, hors PATH), lecture seule, rien installé ni écrit : `tesseract.exe --version` renvoie `tesseract v5.5.3.20260724` avec un **« v »** (mesuré) ; `--list-langs` renvoie l'en-tête `List of available languages in "C:\Users\<utilisateur>\AppData\Local\tessdata/" (3):` puis `eng`, `fra`, `osd` ; avec `--tessdata-dir` vers le dossier du programme, la liste devient `eng`, `fra`, `frm`, `osd` (4 langues), et l'option fonctionne avant ou après `--list-langs` (mesuré). `ocr.detecter({})` lancé tel quel sur cette machine renvoie `present: False` (mesuré). Les essais avec une expression régulière corrigée ont été faits en mémoire, `ocr.py` n'est pas modifié.

Constats (gravité, section, problème, correction) :
1. **Bloquant**, contrat 3.1, plan 5.2 : `RE_VERSION` (`tesseract\s+(\d+...)`) refuse la sortie réelle `tesseract v5.5.3...` (le « v » n'est pas prévu). `detecter` déclare le moteur absent sur la machine même qui a servi au spike ; T25 passe parce que sa doublure `VERSION` écrit `tesseract 5.5.3...` sans « v », forme que ce moteur n'émet pas. Correction : `tesseract\s+v?(\d+...)`, et la doublure de T25 reprend la sortie réelle (« v », fins de ligne CRLF, en-tête de `--list-langs`).
2. **Important**, plan 5.2 (« lire le dossier de données réellement utilisé ») : `--list-langs` est lancé sans `--tessdata-dir`, alors que `tessdata` renvoyé vient de `ocr_tessdata` en premier. Avec `ocr_tessdata` vers le dossier du programme, `langues` reste `eng, fra, osd` alors que le moteur y lirait 4 langues (mesuré). Les langues listées et le dossier rapporté peuvent donc venir de deux dossiers. Correction : déterminer le dossier d'abord, puis lancer `--list-langs --tessdata-dir <dossier>` quand il est connu.
3. **Important**, contrat 3.1 (`tessdata`), plan 5.2 : le dossier par défaut est deviné par `dirname(exe)/tessdata` sans vérifier qu'il existe. Faux pour une cale Chocolatey ou Scoop (`...\bin\tessdata`) et pour Homebrew (`/opt/homebrew/bin\tessdata` obtenu sur cette machine avec un chemin Homebrew simulé, déduit pour macOS), où les données sont ailleurs. C2 passerait un `--tessdata-dir` inexistant. Correction : ne renvoyer qu'un dossier qui existe (`ocr_tessdata`, `TESSDATA_PREFIX`, dossier du programme), sinon chaîne vide, que C2 lira comme « ne pas passer `--tessdata-dir` ».
4. **Important**, plan 5.2 (« se rabattre sur la langue disponible ») : `_langues_effectives` prend `disponibles[0]`, ordre alphabétique de `--list-langs`. `osd` (détection d'orientation, pas une langue de reconnaissance) peut être choisie (`("deu", ["osd"])` donne `osd`, mesuré) et `deu` demandé avec `eng, fra, osd` donne `eng` plutôt que `fra` (mesuré). Correction : exclure `osd` et `equ` des langues de reconnaissance, préférer `fra` puis `eng`.
5. **Important**, contrat 2.7 et 4 : moteur présent sans langue exploitable (`--list-langs` en échec ou en délai, ou seulement `osd`) : `present` vrai, `langues_effectives` vide, `repli` vrai, `message` vide, et `reglages_depuis` renvoie `langues: ""` (mesuré sur `_langues_effectives("fra", [])`), ce qui fera lancer `-l ""` par C2 sans qu'aucun message n'explique quoi que ce soit. Correction : dans ce cas `message = MESSAGES["langue_manquante"]`, et `langues_effectives` vide documenté comme « non utilisable » pour C2.
6. **Important**, plan 5.2 (« prévenir »), contrat 5 : le repli est silencieux dans le bloc `moteur` (`message` vide). Le doute (2) de D le renvoie au journal de C2, mais `ocr_etat()` ne lit que `detecter`, donc personne n'a de quoi avertir la fenêtre. Correction : `message = MESSAGES["langue_manquante"]` quand `repli` est vrai (la forme 2.7 reste valable, `message` est déjà une clé), et adapter l'assertion de T25.
7. **Important** (déduit, non exécuté sur macOS), contrat 6 (T25), `.github/workflows/compilation.yml` (le job `macos` lance la suite, le job de publication en dépend) : `_exe_registre` sort sur `os.name != "nt"` avant de lire le module simulé ; sur macOS T25 reçoit `present: False` et échoue, ce qui bloque la compilation. Correction : retirer la garde `os.name` (l'`ImportError` de `winreg` suffit à renvoyer `None` hors Windows).
8. **Mineur** [mémoire IA, à vérifier], plan 5.2 : seule la sortie standard est lue. Tesseract 4.0 écrirait la version et la liste des langues sur la sortie d'erreur ; il serait alors vu comme absent. Correction : analyser `stdout + stderr` pour `--version` et `--list-langs`.
9. **Mineur**, contrat 3.1 (`executer`) : une exception hors `TimeoutExpired` (par exemple levée par `arreter()`) sort sans tuer le processus ; `communicate()` après `kill` n'a pas de délai. Correction : `kill` dans un `finally` si le processus tourne, et délai court sur le dernier `communicate`.
10. **Mineur**, contrat 3.1 : `dict(BLOC_ABSENT)` est une copie superficielle, la liste `langues` est partagée entre tous les blocs absents (déduit, non montré). Correction : `copy.deepcopy` ou liste neuve.
11. **Mineur**, plan 5.2 : une valeur de registre non texte (`REG_DWORD`) fait lever `TypeError` dans `os.path.join` ; `detecter` renvoie alors « absent » sans essayer les chemins usuels (déduit, non montré). Correction : ne retenir que les valeurs de type `str`.
12. **Mineur**, contrat 3.2, plan 5.2 et 5.6, énoncé de la revue : le code applique `ocr_tessdata`, puis `TESSDATA_PREFIX`, puis le dossier du programme ; l'énoncé du prompt 06 lit « `TESSDATA_PREFIX` respecté, puis `ocr_tessdata` ». Le contrat ne tranche pas. Le réglage explicite avant la variable d'environnement est défendable. À trancher par Maxence, pas de modification du code d'ici là.
13. **Mineur**, contrat 3.1 : `reglages_depuis` relance `detecter` (deux sous-processus) à chaque appel, et `int(cfg.get("ocr_dpi", 300))` lève sur une valeur éditée à la main dans `config.json`. Correction : valeurs par défaut 300 et 3 si la valeur est illisible ; la relance de `detecter` reste à traiter en C3 (cache de détection).
14. **Mineur**, contrat 6 (T25) : aucun test ne couvre les sources `config`, `path`, `usuel`, une version 3 (doit donner « absent »), un moteur absent, ni `executer` (drapeaux, délai). Correction : quelques méthodes de test ajoutées à la classe `Detection`, sans numéro T.
15. **Mineur**, plan 5.6 (« langue parmi les langues détectées ») : `RE_LANGUE` (`^[a-z]{3}$`) ignore `chi_sim`, `deu_frak`, `ita_old` (essai : `_langues` ne garde que `fra` sur `chi_sim, fra, deu_frak, script/Latin`, mesuré). Correction : `^[a-z]{3}(?:_[a-z0-9]+)*$`.
16. **Mineur**, plan 5.2 (« signaler les versions 3 ») : une version 3 reçoit le message `moteur_absent` (« pas encore installé »), ce qui est faux. Le contrat n'a pas de message pour ce cas. À trancher (nouveau message au contrat, ou accepter la formulation) ; pas de modification du code d'ici là.

Forme : zéro cadratin, zéro demi-cadratin dans `ocr.py` et `test_ocr.py` (comptage par code de caractère). `MESSAGES` : `moteur_absent` et `langue_manquante` identiques mot pour mot à la section 5. Constantes `CACHE`, `SEUIL_TEXTE`, `SEUILS_QUALITE` conformes. Invariant 6 : seuls `os`, `re`, `shutil`, `subprocess`, `sys`, `time` sont importés, ni `urllib` ni `socket`. `executer` : liste d'arguments, `creationflags=0x08000000 | 0x4000` sous Windows seulement, délai borné, drapeau d'arrêt. Ordre de détection du plan 5.2 respecté (`config`, `path`, `registre`, `usuel`). Signatures et clés du bloc conformes à 2.7 et 3.1 (réserve : constats 5 et 6).
Fichiers : `docs/ocr-avancement.md` (état, journal, écarts 23 à 38), `docs/prompts/07-C1-D.md`. `ocr.py` et `test_ocr.py` non modifiés.
Tests : `python -m unittest discover -s tests -t . -v` : 278 tests, 0 échec à l'ouverture, puis 278 tests, 0 échec à la clôture (base inchangée). Le message « Ma semaine (mode automatique) : erreur imprévue » en fin de sortie est émis par un test existant, pas un échec.
Décisions : aucune dans la section 4 (les constats 12 et 16 demandent une décision de Maxence).
Doutes : (1) la sortie `tesseract v...` est mesurée sur une seule installation (5.5.3) ; la forme des versions 4.x n'est pas mesurée ; (2) constats 7 et 3 (macOS) déduits, rien exécuté sur macOS ; (3) constat 8 non vérifié ; (4) l'heure de cette entrée est celle de l'horloge de la machine.
Suivant : correction de C1 par D (prompt 07, règle de choix point 2 : C1 est la seule tâche `rejetée`, aucune autre n'est `à relire`).
Verdict (revue seulement) : bloquant

### 2026-11-07 16:08 | C1 | D | fin
Fait : moodlesync/ocr.py créé (détection et configuration). Constantes CACHE = ".moodlesync-ocr", SEUIL_TEXTE = 80, SEUILS_QUALITE = (0.85, 0.70) conservés non calibrés (D11). executer : sous-processus par liste d'arguments, jamais un shell, CREATE_NO_WINDOW et priorité basse sous Windows, délai et drapeau d'arrêt, renvoie (code, stdout, stderr) en octets. detecter : ordre du plan 5.2 (ocr_exe, shutil.which, registre Windows Path et InstallDir, chemins usuels, macOS), version 4 ou 5 exigée, renvoie le bloc moteur 2.7 plus tessdata et majeure, ne lève jamais. reglages_depuis : langues effectives après repli, dpi, psm, oem 1, moteur, tessdata. MESSAGES : moteur_absent et langue_manquante. Test T25 écrit d'abord (échoue), puis le code.
Fichiers : moodlesync/ocr.py, tests/test_ocr.py, docs/ocr-avancement.md, docs/prompts/06-C1-S.md.
Tests : python -m unittest discover -s tests -t . -v : 278 tests, 0 échec (277 existants plus T25). Le message « Ma semaine (mode automatique) : erreur imprévue » affiché en fin de sortie est émis par un test existant, pas un échec. Zéro tiret long dans ocr.py et test_ocr.py (comptage par code de caractère).
Décisions : aucune dans la section 4.
Doutes : (1) version tronquée à trois composantes (« 5.5.3 » au lieu de « 5.5.3.20260724 »), cohérente avec l'exemple 2.7 et la clé moteur du cache (2.3) ; (2) le bloc moteur garde message vide quand le moteur est présent avec repli : le repli est porté par le booléen repli, le message langue_manquante servira au journal (C2 et suivantes) ; (3) écart 17 (pypdfium2 sur macOS 11 et 12) : rien à écrire en C1, ocr.py n'importe pas pypdfium2, l'import paresseux revient à C2 et P1 ; (4) l'horloge de la machine indique 16:08 alors que la dernière entrée porte 18:00 : horodatage réel, non corrigé.
Suivant : revue de C1 par S (prompt 06), règle de choix point 1 (tâche à relire la plus ancienne).

### 2026-11-07 16:01 | C1 | D | prise
Fait : C1 réservée (propriétaire D), prompt 05. Dépendances E0 et S1 à l'état fait et relues. Lecture du journal, du contrat (sections 2.7, 3.1, 3.2, 4, 5, 6), du rapport de spike et du plan (5.2, 5.6) avant toute modification.
Fichiers : docs/ocr-avancement.md (état et cette entrée).
Tests : python -m unittest discover -s tests -t . -v : 277 tests, 0 échec (base inchangée). Le message « Ma semaine (mode automatique) : erreur imprévue » affiché en fin de sortie est émis par un test existant, pas un échec.
Décisions : aucune.
Doutes : aucun à ce stade.
Suivant : test T25 qui échoue, puis moodlesync/ocr.py (détection et configuration).

### 2026-11-07 18:00 | E0b | D | revue
Fait : revue ciblée de l'alignement de `docs/plan-ocr.md` sur D1 à D7 (prompt 04). Aucun constat, rien de bloquant ni d'important ni de mineur. E0b passe à `fait` (Relue : oui, D). Écart 1 fermé. Porte « Avant U1 » franchie.
Colonne « Écart avec le plan à corriger » de la section 7 du contrat reprise ligne par ligne sans me fier à la liste cochée de S : 16 lignes sur 16 corrigées ou sans objet motivé, conforme au plan relu section par section (3.3, 3.4, 4.3, 4.4, 4.5, 5.5, 5.6, 5.9, 5.10, 6.1 à 6.3, 8, 9, 10, 11).
Grep relancés dans `docs/plan-ocr.md` : `copie` (casse ignorée sur la première lettre) 33 lignes, aucune ne désigne un mode `copie` (copier-coller, boutons Copier, `ocr_copier`, photocopies, négations « sans copie locale de l'original », « seconde copie » de 5.10 point 4 = doublon), zéro « mode copie » ni « trois modes » ; `sha1:` zéro occurrence, les trois « SHA-1 » restantes décrivent `moteur.empreinte` (4.3, 5.10 étape 3, 5.10 tableau des risques), conformes à D2 ; `sha256:` du fichier entier partout où le contrat l'exige (4.3, 4.5, 5.7, 5.10) ; `première ligne` quatre occurrences toutes conformes à D4 ; `pause` sept occurrences, aucune « mise en pause de la synchronisation » ; `85` et `70` trois occurrences toutes 0,85 et 0,70, bornes cohérentes avec T4.
Compléments et doutes déclarés par S examinés un par un : tous rattachés à D1 à D7 ou au journal (section 11 reformulée, compléments D6 hors 3.3 et décision 1, phrases ajoutées en 4.3, 5.9 et 5.10, clé `moodlesync` en 6.1, retrait de la ligne `copie` de la liste des tests de la section 8). Aucune règle absente du contrat.
Invariants 1, 2, 5, 7, 12, 16 et formes 2.1 à 2.6 : aucune contradiction restante. Garde-fou : numérotation « technique 1 / technique 2 » de 4.3 intacte, aucune valeur S1 (D8 à D11) recopiée dans le plan.
Forme : zéro cadratin, zéro demi-cadratin dans `docs/plan-ocr.md` et `docs/ocr-avancement.md` (comptage par code de caractère), accents corrects, tableaux Markdown intacts.
Fichiers : `docs/ocr-avancement.md` (états, porte, journal, écart 1), `docs/prompts/05-C1-D.md`. Le plan n'est pas modifié.
Tests : `python -m unittest discover -s tests -t . -v` : 277 tests, 0 échec à l'ouverture, puis 277 tests, 0 échec à la clôture (base inchangée). Le message « Ma semaine (mode automatique) : erreur imprévue » en fin de sortie est émis par un test existant, pas un échec.
Décisions : aucune dans la section 4.
Doutes : l'exemple de cache en 5.7 ne porte pas toutes les clés de 2.3 (`pages_vides`, `numeros_ocr`, `extraction`, `verifie`) ; ce n'est pas une contradiction (clés « à confirmer »), à réconcilier en C3. L'écart 12 (nom des techniques) reste ouvert avant C4.
Suivant : C1 (détection du moteur et configuration), propriétaire D, prompt 05 pour une session neuve.
Verdict (revue seulement) : rien

### 2026-11-07 17:00 | E0b | S | fin
Fait : `docs/plan-ocr.md` aligné sur D1 à D7 (prompt 03). Le contrat fait foi, aucune règle ajoutée qui ne soit pas dans le contrat ou le journal. Numérotation « technique 1 / technique 2 » de 4.3 inchangée (garde-fou, D8). Aucune valeur S1 (D8 à D11) recopiée dans le plan ; aucune phrase du plan ne les contredit (« quelques kilo-octets par page » en 4.3 reste exacte, vérifié par Grep de `pypdf`, `plafond`, `Ko par page`, `DPI`).

Colonne « Écart avec le plan à corriger » de la section 7 du contrat, ligne par ligne :
- [x] D1, 3.4 : « mise en pause pendant l'extraction » réécrit : la synchronisation a la priorité, l'extraction cède entre deux pages ou après un remplacement, puis reprend. Corrigée.
- [x] D1, 5.5 : « La synchronisation met l'extraction en pause » réécrit dans le même sens (état `pause_sync`, attente d'une unité au plus, invariant 7). Corrigée.
- [x] D1, section 11 (« L'OCR ne doit jamais la bloquer, la ralentir ») : **n'était pas strictement vraie** après D1, puisque la synchronisation attend jusqu'à une unité de travail. Réécrite : « ne doit jamais la bloquer ni la faire échouer, et il ne la retarde que d'une unité de travail au plus ». À relire par D (voir Doutes).
- [x] D2, 4.3 : les deux `sha1:` de l'exemple `genere` remplacés par `sha256:` ; phrase ajoutée (sha256 du fichier entier, marque PDF et cache, calcul sur candidats de même taille, `moteur.empreinte` inchangée). Corrigée.
- [x] D2, 5.10 : l'exemple `genere` passe à `sha256:` ; l'étape existante « même taille et même SHA-1 des 256 premiers kilo-octets » est conservée (précisée « `moteur.empreinte`, qui ne change pas ») ; la ligne « Doublon de contenu » du tableau de risques dit maintenant que c'est la taille et le SHA-1 du préfixe (`moteur.empreinte`) qui diffèrent. Corrigée.
- [x] D3, 4.3 : paragraphe d'ouverture sur la « copie PDF cherchable » réécrit (second PDF écarté, `mode_indisponible`) ; phrase « Le mode `copie` ne doit jamais écraser… » retirée ; phrase « Le mode `copie` reste possible plus tard » remplacée par « il n'y a que ces deux politiques en 2.5 » ; technique 2 (reconstruction des pages) réécrite : « n'est utilisée dans aucun mode » (invariant 2), numérotation conservée ; titre « Deux techniques, à choisir après le lot 0 » devenu « Deux techniques décrites, une seule utilisée ». Corrigée.
- [x] D3, 4.5 : aucune occurrence de `copie` ni de « trois modes » dans 4.5 (vérifié par Grep). Rien à retirer.
- [x] D3, 5.6 : ligne `ocr_pdf` du tableau (`aucun` ou `remplacer`) et phrase de validation (« parmi `aucun` et `remplacer`, toute autre valeur refusée avec `mode_indisponible` »). « Trois modes » retiré. Corrigée.
- [x] D3, section 9 : aucune occurrence de `copie` comme mode ni de « trois modes » (seules restent des négations « sans copie locale de l'original », conformes à D3). Rien à retirer.
- [x] D4, 5.9 : « marque en première ligne » précisé (clé `moodlesync` du front matter pour les `.md` de document, `ms.MARQUE` en première ligne pour cours, index, qualité). Corrigée.
- [x] D4, tableau de risques de la section 9 : ligne « Fichier de sortie édité à la main » précisée de la même façon. Corrigée.
- [x] D5, 4.4 : « 85 » et « 70 » remplacés par 0,85 et 0,70 (bornes : 0,70 inclus, 0,85 exclu pour « à vérifier », cohérent avec T4) ; phrase ajoutée (stockée de 0 à 1, TSV divisé par 100, affichée « 0,89 »). Exemples de la section 6 vérifiés : 6.1 « 0,89 », 6.1 « page 7 : confiance 0,62 », 6.3 « 0,64 » sont cohérents ; `confiance: 0.89` du front matter et du cache (5.7) et `0.91` du JSONL (6.4) sont l'écriture stockée (0 à 1). Corrigée.
- [x] D6, 3.3 : parcours 2 décrit sans installation automatique pour la 2.5 (détection, choix manuel de `tesseract.exe`, `ocr_installer` répond `installation_indisponible`) ; paquet portable (65 Mo, SHA-256) déplacé dans un bloc « Version 2.6 ». Corrigée.
- [x] D6, section 9, décision 1 : phrase ajoutée (paquet portable pas livré en 2.5, 2.6). Cohérente avec la décision 1 de la section 10 (déjà conforme). Corrigée.
- [x] D7, 5.5 : mise en file après synchronisation reliée aux seuils de 3.4 (démarrage seul si `ocr` et `ocr_apres_sync` vrais, fenêtre ouverte, 50 documents et 500 pages au plus ; au-delà, confirmation avec durée ; jamais en `--auto`). 3.4 renvoie à 5.5. Corrigée.
- [x] D7, section 9 décision 3 et section 10 décision 5 : alignées sur D7 (mêmes seuils, confirmation au-delà). Corrigée.
- [x] D8 : numérotation de 4.3 intacte. D9, D10, D11 : « Aucun » dans la colonne. Rien à corriger.

Compléments trouvés (hors liste du prompt, tous alignés sur le contrat, à relire) :
- Section 8, liste des tests : la ligne « PDF cherchable en mode `copie` : original intact, copie avec texte extractible » est **retirée**. Elle n'est pas dans la liste T1 à T32 du contrat.
- D4 : 6.1 gagne la clé `moodlesync` dans le front matter (le contrat 2.6 dit « avec une clé de plus ») ; 6.2 et 6.3 gagnent une phrase sur `ms.MARQUE`.
- D6, mentions d'installation en 2.5 qui contredisaient D6 : 3.1 (bouton **Installer**), 3.6 (panneau « À quoi ça sert ? » : **Installer le moteur**), 5.1 (tableau API : `ocr_installer`), 5.2 (étape 6 de la détection et message de détection échouée), 5.9 (seul appel réseau possible, aligné sur l'invariant 6 : restauration et, en 2.6, paquet portable), lot 3 (paquet portable), critère d'acceptation 2, tableau des risques (ligne « Tesseract absent du PATH »).
- D1, deux mentions de la pause : 5.1 (tableau des fichiers modifiés, `application.py`) et lot 3 (« pause pendant la synchronisation »).
- D2 : 4.5 (clé de cache) précisée `sha256:` ; 5.10, ouverture : « Aujourd'hui, MoodleSync ne vérifie pas… » et phrase sur le `sha256:` des PDF générés seulement ; 5.10, correction 2 : sha256 calculé seulement sur les candidats de même taille.
- Fichier d'avancement : à ma lecture, le tableau de la section 2 avait des colonnes plus larges que dans le dernier commit (même contenu, espaces différents). La diff Git montre donc des lignes de tableau modifiées en plus de celles que j'ai changées ; aucun contenu n'a été effacé.

Fichiers : `docs/plan-ocr.md`, `docs/ocr-avancement.md`, `docs/prompts/04-E0b-D.md`. Contrat, rapport de spike, `moodlesync/`, `tests/`, `requirements.txt` non touchés.

Tests de la tâche (résultats réels) :
1. `Grep` de `copie` (casse ignorée sur la première lettre) : 33 lignes. Aucune ne désigne un mode `copie`. Elles désignent : copier-coller, copier le texte ou le contexte, boutons « Copier », `ocr_copier`, « photocopie(s) », « copie lourde », et des **négations** de copie de l'original (« sans copie locale de l'original », « aucune copie de l'original », « sans copie de secours », « logique sans copie de l'original », « seconde copie » en 5.10 point 4, qui désigne un doublon d'un PDF cherchable, pas un mode). « Le PDF cherchable est la seule copie locale » (5.10) désigne le PDF cherchable lui-même. Zéro occurrence de la forme `mode copie` ni de « trois modes ».
2. `Grep` de `sha1:` : zéro occurrence. (Les trois occurrences de « SHA-1 » restantes sont intentionnelles : description de `moteur.empreinte` en 4.3, 5.10 étape 3, 5.10 tableau de risques.)
3. Tirets longs dans `docs/plan-ocr.md` : zéro cadratin, zéro demi-cadratin (comptage Python par code de caractère).
4. Colonne « Écart avec le plan à corriger » : cochée ligne par ligne ci-dessus, 16 lignes sur 16 corrigées ou sans objet motivé.
5. `python -m unittest discover -s tests -t . -v` : 277 tests, 0 échec. Le message « Ma semaine (mode automatique) : erreur imprévue » en fin de sortie est émis par un test existant, pas un échec.

Décisions : aucune dans la section 4 (application des décisions D1 à D7 existantes).
Doutes : (1) section 11 reformulée (« ralentir » ne tenait plus après D1) : c'est un jugement de S, à confirmer par D ; (2) les compléments D6 hors 3.3 et décision 1 vont au-delà de la liste du prompt ; (3) le plan garde « OCR » dans des sections techniques, conforme au contrat (mots interdits seulement dans l'interface principale) ; (4) 4.3 contient toujours « technique 1 / technique 2 » alors que le contrat nomme la méthode retenue « couche TSV » : numérotation du plan inchangée comme demandé, les noms sont dans le contrat ; (5) l'ancienne phrase de 5.10 « Remplacer les octets sans enrichir l'état casse donc plusieurs choses » et le reste de 5.10 n'ont pas été modifiés au-delà des points listés ; D est invité à vérifier qu'il ne reste aucune incohérence entre 5.10 et le contrat 2.1 à 2.2.
Suivant : revue de E0b par D (prompt 04). Écart 1 : corrigé par E0b, à relire, non fermé. Les écarts 2 et 3 ne sont pas à moi. C1 et C2 restent prêtes, mais la revue de E0b passe avant (règle de choix, point 1).

### 2026-11-07 16:00 | E0b | S | prise
Fait : E0b réservée (propriétaire S), prompt 03. Dépendance E0 `fait` et relue. Lecture du journal, du contrat (sections 2, 4, 7) et du plan avant toute modification.
Fichiers : `docs/ocr-avancement.md` (état et cette entrée). Plan pas encore modifié.
Tests : `python -m unittest discover -s tests -t . -v` : 277 tests, 0 échec (base inchangée). Le message « Ma semaine (mode automatique) : erreur imprévue » affiché en fin de sortie est émis par un test existant, pas un échec.
Décisions : aucune.
Doutes : aucun à ce stade.
Suivant : alignement de `docs/plan-ocr.md` sur D1 à D7.

### 2026-11-07 15:40 | S1 | S | écart
Fait : Maxence a tranché les valeurs S1 sur recommandation de S : D8 (couche TSV, flux brut), D9 (écart de rendu maximal 0), D10 (10 Ko par page reconnue, flux compressé), D11 (pypdf 6.21.4, aperçu 900 px, seuils non calibrés, `pypdfium2` en import paresseux). Reportées dans le contrat (marqueurs S1 des sections 1, 2.7, 3.1, invariants 1 et 4, section 7). Porte « Avant C4 » franchie. Écarts 12, 13, 14, 15, 16 fermés par D8 à D11 ; 17 fermé côté décision (D11), reste à écrire dans C1 et P1 ; 19 couvert par D11 (« non calibrés »).
Fichiers : `docs/ocr-contrat.md`, `docs/ocr-avancement.md`, `docs/prompts/03-E0b-S.md` (garde-fou).
Tests : `python -m unittest discover -s tests -t . -v` : 277 tests, 0 échec.
Décisions : section 4 (D8 à D11).
Doutes : la borne de 10 Ko par page n'a pas été mesurée sur une page réelle dense (C4 le fait avant de figer) ; le rapport de spike n'est pas corrigé (mineurs 18, 20, 21, 22 restent ouverts, ce sont des notes sur le rapport).
Suivant : E0b (prompt 03), inchangé.

### 2026-11-07 15:10 | S1 | S | revue
Fait : revue ciblée de `docs/spike-ocr.md` (prompt 02). Aucun bloquant : le go découle des mesures, chaque volet a sa réponse, la porte « Après S1 » est franchie. S1 passe à `fait` (Relue : oui, S). C1 et C2, dont les dépendances sont `fait`, passent à `à faire`. Les valeurs S1 du contrat restent proposées, non fixées (porte « Avant C4 »).

Vérifications refaites par S, dans un environnement virtuel jetable hors du dépôt, sur un PDF de 3 pages **fabriqué** (images de texte français à 150 DPI, un signet, un lien, une annotation), pas sur les documents réels de Maxence (non lus, donc non reproduits : tailles 323 933 et 325 370 octets, confiance 0,917 et 0,489, temps de 0,44 à 1,96 s sur pages réelles) :
- versions confirmées : pypdfium2 5.15.0, Pillow 13.0.0, pypdf 7.0.0 (dernière publiée, 6.21.4 existe), Tesseract 5.5.3.20260724 avec Leptonica 1.87.0 ; Python 3.15.2 ;
- détection confirmée : `tesseract.exe` hors PATH (`where` ne trouve rien), clé de registre `HKLM\SOFTWARE\Tesseract-OCR` avec `Path`, `InstallDir` et `CurrentVersion` ; `TESSDATA_PREFIX` vers `%LOCALAPPDATA%\tessdata` (trois `traineddata`, ni `configs` ni `pdf.ttf`) ; le dossier du programme contient `configs`, `pdf.ttf` et un `fra.traineddata` de 1 130 365 octets (« fast ») ;
- rendu 300 DPI niveaux de gris : 0,074 s par page (mesuré 3 fois) ; reconnaissance `fra+eng`, psm 3, oem 1, `-c tessedit_create_tsv=1`, `--tessdata-dir` utilisateur : 0,83 à 0,88 s par page dense, 120 à 156 mots, confiance 0,957 à 0,959, « é è ç œ » corrects, code retour 0 ;
- superposition par la méthode du rapport (couche invisible `3 Tr` construite depuis le TSV, police Helvetica en WinAnsi, fusion dans `/Contents`) : pages, annotations, liens, signets 3, 2, 1, 1 avant et après, texte extractible avec accents, écart de rendu maximal 0 sur 3 pages ; refait avec pypdf 6.21.4 (version épinglée dans `requirements.txt`) : même résultat ;
- `merge_page` d'une page non rattachée à un writer : `DeprecationError` sous pypdf 7.0.0, fonctionne sous 6.21.4 ; `PdfWriter(clone_from=...)` puis fusion fonctionne dans les deux ;
- console : un processus enfant lancé avec `CREATE_NO_WINDOW` depuis `pythonw.exe` voit `GetConsoleWindow() == 0` (aucune fenêtre console), et `tesseract --version` renvoie 0 dans les mêmes conditions. Déduit, non observé visuellement ;
- wheels (déduit, par `pip download` sans installation) : pour Python 3.12 (celui du build), `pypdfium2 5.15.0` et Pillow 13.0.0 existent pour `win_amd64` ; pour macOS, `pypdfium2 5.15.0` n'existe qu'avec l'étiquette `macosx_13_0` (arm64 et x86_64), rien pour macOS 11 et 12.

Constats (gravité, volet ou section, problème, correction) :
1. **Mesures fausses ou invraisemblables** : rien. Aucune mesure vérifiée ne s'est révélée fausse.
2. **Incohérences internes** :
   - important, « Valeurs proposées » et « Décision globale » : le rapport appelle « technique 2 » la couche construite depuis le TSV, alors que le plan 4.3 appelle « technique 2 » la reconstruction des pages, interdite en mode `remplacer` (invariant 2) ; les deux techniques du rapport sont des superpositions. Un lecteur du plan qui lit « technique 2 » comprend l'inverse. Correction : nommer les méthodes « couche TSV » et « textonly_pdf », ne plus utiliser les numéros.
   - important, « Borne de volume » : « +2 %, plafond +200 Ko » se heurte à ~3,3 Ko par page : le plafond absolu est atteint à environ 60 pages, donc un scan de 100 pages serait toujours refusé par la vérification ; de plus, +1 437 octets mesurés pour la couche TSV (3 pages) ne correspondent pas à 3,3 Ko par page, et le rapport ne dit ni combien de pages portent la couche, ni si le flux est compressé. Mes mesures sur 3 pages synthétiques de ~1 000 caractères : ~8,8 Ko par page non compressé, ~1,1 Ko par page en Flate (texte répétitif, donc indicatif seulement). Correction : fixer la borne en octets par page reconnue, après mesure sur une page réelle dense, avec flux compressé, et supprimer le plafond absolu ou le rendre proportionnel au nombre de pages.
3. **Ambiguïtés qui feraient diverger C4** :
   - important, « Méthode de la couche de texte » : la construction n'est pas spécifiée. Ni la bibliothèque (ReportLab n'est pas une dépendance du projet, et PyInstaller l'ajouterait), ni la police, ni l'encodage, ni le traitement des caractères hors cp1252 (flèches, signes mathématiques, lettres grecques) ne sont dits ; `pdf.ttf` n'existe pas dans le dossier tessdata utilisateur. Mon essai : flux de contenu écrit à la main, Helvetica WinAnsi, mode de rendu 3, conforme pour le français et l'anglais ; hors cp1252 non couvert. Correction : décrire la construction retenue (flux brut ou bibliothèque, police, encodage) et la règle pour un caractère non encodable (par exemple l'omettre de la couche, sans toucher au `.md`).
   - important, « Tolérance du rendu » : « 0, ou au plus 1/255 en écart moyen » donne deux valeurs et deux métriques, sans DPI ni choix des 3 pages. Correction : une valeur, une métrique (écart maximal par pixel ou écart moyen), un DPI, la règle de choix des pages. Piège à documenter pour C4 : réécrire `/Contents` avec l'objet résolu (`page["/Contents"]`) au lieu de la référence indirecte (`page.raw_get("/Contents")`) crée un écart de rendu massif (maximum 255) ; c'est un bon argument pour garder une tolérance stricte.
   - important, « Versions » et « Limites » : le spike mesure pypdf 7.0.0, le dépôt épingle 6.21.4 (`requirements.txt`), et le rapport ne dit pas laquelle C4 doit viser. L'API de `merge_page` diffère (confirmé). Correction : trancher la version, reporter la consigne dans le contrat et P1 ; si le projet reste en 6.21.4, la note « `merge_page` retiré » devient une contrainte de migration, pas de C4.
   - important, « macOS » et « Versions » : Python 3.15.2 seulement, alors que le build utilise 3.12 ; et `pypdfium2 5.15.0` n'a de wheel macOS qu'à partir de macOS 13. L'import de `pypdfium2` doit donc échouer proprement (import paresseux, détection qui ne lève jamais) sur macOS 11 et 12, et la limite doit être écrite. Correction : l'ajouter aux limites du rapport (ou à l'écart ouvert) et à C1 et P1.
4. **Choses fragiles** :
   - mineur, « Console » : la porte « Après S1 » exige « console absente » ; le rapport écrit « go, à confirmer visuellement » et la porte a été notée franchie. Mon contrôle par `GetConsoleWindow` appuie le go sans remplacer l'observation. Correction : garder la confirmation visuelle dans la liste de P2 ou P4.
   - mineur, « Seuils de qualité » : « conserver 0,85 et 0,70 » et « classent correctement » reposent sur deux points (0,917 et 0,489) ; la zone « à vérifier » n'a pas été exercée. Correction : écrire « non calibré, conservés par défaut ».
   - mineur, « Reconnaissance » : toutes les mesures utilisent le modèle `fra` « best » (14,2 Mo) du dossier utilisateur ; l'installation standard ne fournit que le modèle « fast » (1,1 Mo) dans le dossier du programme. Temps et confiance avec ce modèle : non mesurés. Correction : l'écrire dans les limites.
5. **Contradictions avec le contrat** :
   - mineur, « Plan B » : « passer la fabrication du PDF cherchable en mode `copie` » contredit D3 (`copie` refusé) et l'invariant 1 (aucun original conservé). Correction : ne garder que « renoncer au mode `remplacer` et garder le `.md` ».
   - mineur, « Décision globale » : « go » sans périmètre, alors que macOS est non testé et que le lot 0 du plan vise Windows et macOS. Correction : « go Windows ».
   Les marqueurs S1 de la section 1 du contrat, les invariants 1 et 4 et D1 à D7 ne sont contredits par aucune mesure ; la porte « Après S1 » est cohérente avec le rapport sous la réserve de la console.

Fichiers : `docs/ocr-avancement.md` (états, portes, journal, écarts). Rapport de spike non modifié. Contrat non modifié (les valeurs S1 restent à fixer, voir porte « Avant C4 »). Fichiers d'essai dans `%USERPROFILE%\.claude\jobs\0221660b\tmp`, hors dépôt, aucun document de cours lu.
Tests : `python -m unittest discover -s tests -t . -v` : 277 tests, 0 échec à l'ouverture, puis 277 tests, 0 échec à la clôture (base inchangée). Le message « Ma semaine (mode automatique) : erreur imprévue » affiché en fin de sortie est émis par un test existant, pas un échec.
Décisions : aucune dans la section 4 (S1 relue, non rejetée). Les valeurs S1 sont à trancher par Maxence avant C4.
Doutes : documents réels non retestés par S ; confirmation visuelle de la console ; macOS entièrement non testé ; décision pypdf 6.21.4 ou 7.0.0.
Suivant : E0b (alignement du plan sur D1 à D7), propriétaire S, prompt 03 pour une session neuve. C1 et C2 sont prêtes, mais l'ordre du plan d'exécution place E0b avant elles. Valeurs S1 à trancher avant C4.
Verdict (revue seulement) : important (6), mineur (5), rien de bloquant.

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
| 1 | S | Le plan 3.4, 3.3, 4.3, 4.4, 4.5, 5.5, 5.6, 5.9, 5.10 et 9 contredisent D1 à D7 | `docs/plan-ocr.md` | fermé par la revue de D (prompt 04, étape B), verdict rien |
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
| 12 | S | Important. Le rapport de spike appelle « technique 2 » la couche TSV ; le plan 4.3 appelle « technique 2 » la reconstruction des pages (interdite en `remplacer`). Nommer « couche TSV » et « textonly_pdf » | `docs/spike-ocr.md`, `docs/plan-ocr.md` 4.3 | ouvert (avant C4) |
| 13 | S | Important. Borne de volume « +2 %, plafond +200 Ko » incohérente avec ~3,3 Ko par page (plafond atteint vers 60 pages) ; +1 437 octets mesurés ne correspondent pas à 3,3 Ko par page ; compression et nombre de pages à couche non dits. À refixer en octets par page, flux compressé, sur une page réelle dense | `docs/spike-ocr.md`, `docs/ocr-contrat.md` invariant 1 | ouvert (avant C4) |
| 14 | S | Important. Construction de la couche TSV non spécifiée : bibliothèque (ReportLab n'est pas une dépendance), police, encodage, caractère hors cp1252, `pdf.ttf` absent du dossier utilisateur. Essai de S : flux brut, Helvetica WinAnsi, mode de rendu 3 | `docs/spike-ocr.md`, `docs/ocr-contrat.md` 3.1 | ouvert (avant C4) |
| 15 | S | Important. Tolérance du rendu à deux valeurs et deux métriques (« 0, ou 1/255 en écart moyen »), sans DPI ni choix des pages. Piège de C4 : réécrire `/Contents` avec l'objet résolu au lieu de `raw_get("/Contents")` donne un écart maximal de 255 | `docs/spike-ocr.md`, `docs/ocr-contrat.md` invariant 4 | ouvert (avant C4) |
| 16 | S | Important. Spike sous pypdf 7.0.0, dépôt sous 6.21.4 : la version visée par C4 n'est pas dite ; `merge_page` sur page non rattachée échoue en 7.0.0 et fonctionne en 6.21.4 (vérifié) | `docs/spike-ocr.md`, `requirements.txt` | ouvert (avant C4, P1) |
| 17 | S | Important. Spike en Python 3.15.2 seulement, build en 3.12 (wheels `win_amd64` vérifiés par `pip download`, déduit) ; `pypdfium2 5.15.0` n'a de wheel macOS qu'à partir de macOS 13 : l'import doit échouer proprement sur macOS 11 et 12, à écrire dans C1, P1 et les limites | `docs/spike-ocr.md`, C1, P1 | ouvert |
| 18 | S | Mineur. Console : porte franchie sur un go « à confirmer visuellement » ; contrôle de S par `GetConsoleWindow() == 0` (déduit). Garder la confirmation visuelle dans P2 ou P4 | `docs/spike-ocr.md`, P2, P4 | ouvert |
| 19 | S | Mineur. Seuils de qualité 0,85 et 0,70 « classent correctement » sur deux points seulement, zone « à vérifier » non exercée : écrire « non calibré » | `docs/spike-ocr.md` | ouvert |
| 20 | S | Mineur. Mesures faites avec le modèle `fra` « best » du dossier utilisateur ; l'installation standard fournit le modèle « fast » (1,1 Mo) : temps et confiance non mesurés avec lui | `docs/spike-ocr.md` | ouvert |
| 21 | S | Mineur. Plan B « mode `copie` » contredit D3 et l'invariant 1 | `docs/spike-ocr.md` | ouvert |
| 22 | S | Mineur. « Décision globale : go » sans périmètre, macOS non testé : écrire « go Windows » | `docs/spike-ocr.md` | ouvert |
| 23 | S | Bloquant. `RE_VERSION` refuse la sortie réelle `tesseract v5.5.3...` (« v ») : `detecter` renvoie « absent » sur la machine de développement ; la doublure de T25 omet le « v » et masque le défaut. Corriger la regex et la doublure | `moodlesync/ocr.py`, `tests/test_ocr.py`, contrat 3.1, plan 5.2 | fermé par la correction de C1 (prompt 07) |
| 24 | S | Important. `--list-langs` sans `--tessdata-dir` alors que `tessdata` vient de `ocr_tessdata` : langues et dossier peuvent venir de deux dossiers (3 langues contre 4, mesuré) | `moodlesync/ocr.py`, plan 5.2 | fermé par la correction de C1 (prompt 07) |
| 25 | S | Important. Dossier de données par défaut deviné `dirname(exe)/tessdata` sans vérification d'existence (cales Chocolatey et Scoop, Homebrew) ; ne renvoyer qu'un dossier existant, sinon chaîne vide | `moodlesync/ocr.py`, contrat 3.1 | fermé par la correction de C1 (prompt 07) |
| 26 | S | Important. Repli sur `disponibles[0]` : peut choisir `osd`, et `eng` plutôt que `fra`. Exclure `osd` et `equ`, préférer `fra` puis `eng` | `moodlesync/ocr.py`, plan 5.2 | fermé par la correction de C1 (prompt 07) |
| 27 | S | Important. Moteur présent sans langue exploitable : `langues_effectives` vide, `message` vide, `reglages_depuis` renvoie `langues: ""` (C2 lancerait `-l ""`) | `moodlesync/ocr.py`, contrat 2.7 | fermé par la correction de C1 (prompt 07) |
| 28 | S | Important. Repli silencieux : `message` vide dans le bloc `moteur` alors que le plan dit « prévenir » ; mettre `MESSAGES["langue_manquante"]` quand `repli` est vrai | `moodlesync/ocr.py`, `tests/test_ocr.py`, plan 5.2, contrat 5 | fermé par la correction de C1 (prompt 07) |
| 29 | S | Important (déduit). `_exe_registre` sort sur `os.name != "nt"` : T25 échoue sur macOS et bloque la CI (job `macos`, dont la publication dépend). Retirer la garde | `moodlesync/ocr.py`, `.github/workflows/compilation.yml` | fermé par la correction de C1 (prompt 07) |
| 30 | S | Mineur [mémoire IA, à vérifier]. Seule la sortie standard est lue ; Tesseract 4.0 écrirait version et langues sur la sortie d'erreur. Lire `stdout + stderr` | `moodlesync/ocr.py`, plan 5.2 | fermé par la correction de C1 (prompt 07) |
| 31 | S | Mineur. `executer` : exception hors délai sans `kill` du processus, `communicate()` sans délai après `kill` | `moodlesync/ocr.py`, contrat 3.1 | fermé par la correction de C1 (prompt 07) |
| 32 | S | Mineur. `dict(BLOC_ABSENT)` : copie superficielle, liste `langues` partagée (déduit) | `moodlesync/ocr.py` | fermé par la correction de C1 (prompt 07) |
| 33 | S | Mineur. Valeur de registre non texte : `TypeError` dans `os.path.join`, `detecter` renvoie « absent » sans essayer les chemins usuels (déduit) | `moodlesync/ocr.py`, plan 5.2 | fermé par la correction de C1 (prompt 07) |
| 34 | S | Mineur. Ordre du dossier de données : code = `ocr_tessdata`, `TESSDATA_PREFIX`, programme ; l'énoncé de la revue lit `TESSDATA_PREFIX` d'abord ; le contrat ne tranche pas | `docs/ocr-contrat.md` 3.2, plan 5.2 et 5.6 | ouvert (décision de Maxence) |
| 35 | S | Mineur. `reglages_depuis` relance `detecter` à chaque appel (deux sous-processus) et `int()` lève sur une valeur de `config.json` éditée à la main ; la relance est à traiter en C3 | `moodlesync/ocr.py`, contrat 3.1 | fermé pour `int()` (prompt 07) ; la relance de `detecter` reste pour C3 |
| 36 | S | Mineur. T25 ne couvre ni `config`, `path`, `usuel`, ni version 3, ni moteur absent, ni `executer` | `tests/test_ocr.py`, contrat 6 | fermé par la correction de C1 (prompt 07) |
| 37 | S | Mineur. `RE_LANGUE` ignore `chi_sim`, `deu_frak`, `ita_old` | `moodlesync/ocr.py`, plan 5.6 | fermé par la correction de C1 (prompt 07) |
| 38 | S | Mineur. Une version 3 reçoit le message `moteur_absent` (« pas encore installé ») ; le contrat n'a pas de message pour ce cas | `docs/ocr-contrat.md` section 5, plan 5.2 | ouvert (décision de Maxence) |
| 39 | S | Mineur. Les corrections de C1 pour `executer` (kill dans un `finally`), `BLOC_ABSENT` (copie profonde) et `_exe_registre` (garde `os.name`) n'existent dans aucun test qui échoue sans elles ; le test de `creationflags` ne vérifie pas la priorité basse `0x4000` (10 des 12 tests de `test_ocr.py` échouent face à l'ancien code) | `tests/test_ocr.py`, contrat 6 | ouvert (C2 ou C3, au passage) |
| 40 | S | Mineur. Configuration éditée à la main : `ocr_exe`, `ocr_tessdata` ou `ocr_langues` non texte font déclarer le moteur absent à tort ; `ocr_dpi` à `Infinity` lève `OverflowError` dans `reglages_depuis` ; `ocr_dpi: 0` passe sans borne | `moodlesync/ocr.py`, contrat 3.1 et 3.2 | ouvert (décision sur les bornes à lire ou à valider, A1) |
| 41 | S | Mineur. Docstring de `_langues_effectives` : « equ (equipement) » inexact, `equ` est le module de détection d'équations [mémoire IA, à vérifier] | `moodlesync/ocr.py` | fermé par C2 (journal `fin` de C2) |
| 42 | S | Mineur. Deux conventions de C1 absentes du contrat : `langues_effectives == ""` avec `repli` vrai signifie « non utilisable », `tessdata == ""` signifie « ne pas passer `--tessdata-dir` » | `docs/ocr-contrat.md` 2.7 et 3.1 | fermé par C2 (contrat 2.7 et 3.1, journal `fin` de C2) |
| 43 | S | Important. `pypdfium2` n'est pas dans `requirements.txt` ni dans l'environnement du projet ; wheel macOS 13 et plus seulement (écart 17). `rendre_page` d'un PDF échoue avec « illisible » tant qu'il manque | `requirements.txt`, `MoodleSync.spec` | ouvert (P1) |
| 44 | S | Important. Le rendu réel d'une page de PDF par `pypdfium2` n'a jamais été exécuté dans le dépôt (`_rendre_pdf` écrit d'après l'API vue par le spike, tous les tests de PDF passent par une doublure de `rendre_page`) : à exercer une fois, dans un environnement jetable ou après P1, avant C4 | `moodlesync/ocr.py`, `tests/test_ocr.py` | ouvert (relecteur de C2 ou C4) |
