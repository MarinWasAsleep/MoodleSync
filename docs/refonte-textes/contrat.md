# Refonte de « Mes textes » : contrat

Ce contrat gèle les interfaces entre les tâches R1 à R12 (`plan.md`). Chaque agent le lit en entier avant de commencer. **Il fait foi** pour tout ce qu'il nomme : en cas de conflit avec `docs/ocr-contrat.md`, `docs/plan-ocr.md` ou un test existant, c'est ce fichier qui l'emporte, et le test ancien est retiré par la tâche qui le casse. Ce que ce fichier ne nomme pas reste régi par `docs/ocr-contrat.md`.

Les décisions de Maxence (U1 à U13) et de l'orchestrateur (O1 à O16) sont dans `decisions.md`. Une phrase d'ici qui les contredit est un bug à signaler au journal `avancement.md`, pas à corriger en silence.

Règles de forme : français, **aucun tiret cadratin ni demi-cadratin**, fichiers écrits en LF, commits sans accents.

## 1. Ce qui change, en une page

| Avant | Après |
|---|---|
| Un dossier `Textes/` à part, avec `index.md`, `Qualité des textes.md` et un fichier par cours | **Supprimé.** Le texte d'un document est à côté de son PDF |
| Une longue liste de documents | Une **arborescence** cours, sections, fichiers, repliable |
| « Préparer » traite tout ce qui n'a pas de texte | On **choisit** dans une arborescence à cocher, une seule fois |
| Mode PDF « aucun » par défaut, « remplacer » sur consentement | Les PDF choisis sont **toujours remplacés**, avec une copie de l'original |
| Un document « Difficile » est gardé avec son `.md` | Un document « Difficile » est un **échec** : rien n'est écrit, le PDF reste intact |
| Rien pour des fichiers hors Moodle | Un onglet **Déposer des fichiers** |
| Recherche, export, aperçu, copie de contexte, dialogue de qualité | **Supprimés**. Reste : copier le texte d'un document |
| Texte en `.md` seulement | `.md` **ou** `.txt` au choix dans les réglages |

## 2. Données sur disque

### 2.1 Disposition

```text
<dest>/                                  le coffre
  <Cours>/<Section>/article.pdf          le PDF (remplacé par la version cherchable après un traitement réussi)
  <Cours>/<Section>/article.pdf.md       le texte (ou article.pdf.txt, selon le réglage ocr_format)
  <Cours>/<Section>/article.pdf (ancienne version AAAA-MM-JJ).md   inchangé : nom_ancienne_version
  .moodlesync-ocr/
    cache.json   file.json   pages/      inchangés (2.3, 2.4, 2.5 de ocr-contrat.md), avec les ajouts de 2.2 ci-dessous
    originaux/<hex>.pdf                  copie de l'original, nommée par le SHA-256 du fichier d'origine
```

- Le nom du texte est `<nom complet du document avec son extension>.<format>` où `format` vaut `md` ou `txt` (réglage `ocr_format`, défaut `md`). Pour une image : `scan.png.md`.
- `Textes/`, `index.md`, `Qualité des textes.md`, `<Cours> - texte des documents.md` et tout export `.jsonl` **n'existent plus**. Aucun code ne les écrit, aucun code ne les lit, hormis la migration (R6).
- Un dossier ou fichier dont un composant commence par `.` n'est jamais traité ni montré.
- `moteur.index_existant` ignore déjà les dossiers cachés : `originaux/` n'y entre pas. Un `.md` ou `.txt` à côté d'un PDF y entre comme tout fichier du coffre ; c'est sans effet sur la synchronisation (elle compare des noms et des tailles de fichiers Moodle). R1 le vérifie par un test.

### 2.2 Cache `.moodlesync-ocr/cache.json` : entrée d'un document

Les clés de 2.3 de `ocr-contrat.md` restent, avec ces changements :

| Clé | Nouvelle valeur ou ajout |
|---|---|
| `etat` | `ok`, `a_verifier` ou `echec`. **`difficile` n'est plus un état de document** : une page peut l'être, un document l'est seulement par son échec |
| `motif` | **nouveau**, présent si `etat == "echec"` : `difficile` (confiance moyenne sous 0,70), `vide` (aucun texte trouvé), `illisible` (aucune page lue), `verification` (le PDF fabriqué n'a pas passé la vérification), `ecriture` (écriture impossible), `erreur` (autre) |
| `sortie` | chemin relatif à `dest`, avec `/`, **du texte à côté du PDF** (`Cours A/S1/article.pdf.md`). Absent si `etat == "echec"` |
| `format` | **nouveau**, `md` ou `txt`, le format du texte écrit. Absent si échec |
| `remplace` | **nouveau**, bool : le PDF a été remplacé par la version cherchable |
| `original` | **nouveau**, objet ou `null` : `{"fichier": "originaux/<hex>.pdf", "empreinte": "sha256:<hex>", "taille": int}`. `null` si aucune copie (PDF textuel, image, PDF migré, ou échec) |
| `sortie_empreinte` | **nouveau**, `"sha256:<hex>"` du texte écrit, dans le format de `format`. Sert à la protection d'un `.txt` édité (O6). Aussi écrit pour un `.md` |
| `sortie_empreintes` | **nouveau (R1c, revue V1)**, objet `{"md": "sha256:<hex>", "txt": "sha256:<hex>"}` : l'empreinte du dernier texte écrit **dans chaque format**, pour qu'un retour de format (`txt`, `md`, `txt`) ne prenne pas un ancien `.txt` pour un texte édité. Absent ou incomplet : on retombe sur `sortie_empreinte` si `format` est le format demandé, sinon le fichier existant est tenu pour modifié (échec sûr) |
| `date` | inchangé |

Un document en échec garde son entrée (avec `empreinte`, `taille`, `date`) pour que l'arborescence affiche « Non réussi » sans le retenter (O4). Elle est écartée dès que le fichier source change (empreinte différente) ou que `refaire` est vrai.

`.moodlesync.json` (2.1) et la marque `/MoodleSyncGenere` (2.2) restent **tels quels** : la synchronisation s'en sert pour reconnaître un PDF cherchable republié.

### 2.3 Statut d'un fichier, vu par l'interface

Dérivé par `textes_arbre.statut_fichier` (R3) à partir du cache et de `file.json` :

| `statut` | Condition | Libellé |
|---|---|---|
| `non_traite` | aucune entrée de cache à jour | « Non traité » |
| `en_attente` | le fichier est dans `file.json`, tâche en attente | « En attente » |
| `en_cours` | le fichier est la tâche en cours de `file.json` | « En cours » |
| `traite` | `etat == "ok"` | « Traité » |
| `a_verifier` | `etat == "a_verifier"` | « À vérifier » |
| `echec` | `etat == "echec"` | « Non réussi » |

## 3. Pipeline de traitement (`moodlesync/ocr.py`, tâches R1 et R2)

### 3.1 Signature

```python
def traiter_document(dest: str, chemin_rel: str, cfg: dict, *, progres=None, arreter=None, attendre=None,
                     refaire: bool = False, garder_original: bool = True) -> dict
# {"entree": <entrée de cache>, "statut": "ok"|"a_verifier"|"echec", "motif": str, "remplace": bool, "texte": bool}
```

`traiter_document` remplace l'ancienne version (extraction puis, selon `ocr_pdf`, fabrication du PDF). Il ne lève jamais pour un échec de qualité : il rend `statut == "echec"`. Il lève `ms.Annule` si `arreter()` le demande, et rien n'est alors laissé sur le disque.

### 3.2 Étapes, dans cet ordre

1. **Extraction** page par page : inchangée (texte natif, sinon reconnaissance avec relecture tournée, `extraire_page`).
2. **Décision de qualité** sur le document : `echec` si `confiance` du document (moyenne pondérée par les mots, `_resume_pages`) est connue et **strictement inférieure à `SEUILS_QUALITE[1]` (0,70)** (motif `difficile`) ; `echec` si aucune page ne porte de texte (motif `vide`) ; `echec` si aucune page n'a pu être lue (motif `illisible`). Un document sans page reconnue (tout natif) n'a pas de `confiance` et n'échoue pas. Sinon `a_verifier` si une page n'est pas « bonne » ou est illisible, sinon `ok`.
3. **Échec** : rien n'est écrit (ni texte, ni copie d'original, ni PDF remplacé). La reprise par page (`pages/<hex>.json`) est supprimée. L'entrée de cache est écrite avec `etat = "echec"` et son `motif`. Retour immédiat.
4. **Écriture du texte** à côté de la source (`ecrire_document_texte`, 4.2), de façon atomique (fichier temporaire puis `os.replace`, avec les nouveaux essais de `_remplacer_travail`).
5. **Remplacement du PDF**, seulement si la source est un PDF avec au moins une page à reconnaître (O2) :
   a. si `garder_original` : copier la source dans `originaux/<hex>.pdf`, relire la copie, comparer l'empreinte ; si elle diffère, **échec** de motif `ecriture` ;
   b. `fabriquer_pdf_cherchable` (inchangé : couche de texte, vérification par rendu, ordre atomique, `genere` dans `.moodlesync.json`) ;
   c. si la fabrication refuse ou échoue : **échec** de motif `verification`, et l'étape 6 s'applique.
6. **Annulation d'un échec tardif** (O1) : si l'étape 4 a écrit un texte et que l'étape 5 échoue, le texte écrit est supprimé, la copie d'original créée est supprimée, et le PDF d'origine est intact (c'est l'invariant de l'ordre atomique de C4). L'entrée de cache dit `echec`.
7. **Cache** : écrire l'entrée (2.2) puis `sauver_cache`.

### 3.3 Restauration

```python
def restaurer(dest: str, chemin_rel: str, cfg: dict, *, confirme: bool = False) -> dict
# {"ok": True} | {"confirmer": str} | {"erreur": str}
```

- Avec une entrée de cache portant `original` : remettre le PDF depuis `originaux/<hex>.pdf` (vérifier l'empreinte avant, écriture atomique), supprimer le texte à côté (`.md` ou `.txt`), retirer `genere` de `.moodlesync.json`, **supprimer l'entrée de cache et la copie d'original**. Le fichier redevient « Non traité ».
- Sans copie (document migré, U9) : comportement actuel de `ocr.restaurer` (re-téléchargement depuis Moodle, comparaison), puis les mêmes suppressions.
- Un texte modifié à la main (O6) n'est jamais supprimé : la restauration remet le PDF et laisse le texte, en le disant dans la phrase de retour (`restauration_texte_garde`).

### 3.4 Format du texte

`ecrire_document_texte(chemin_texte, chemin_rel, pages, reglages, *, format, illisibles, date) -> bool` (vrai si écrit, faux si conservé car édité).

- **`md`** : identique à `ecrire_document_md` d'aujourd'hui (front matter, `<!-- page n -->`, section « Pages à vérifier »), y compris la ligne `moodlesync:` qui protège un fichier édité.
- **`txt`** (O5) : texte seul, UTF-8, fins de ligne `\n`. Aucun en-tête. Pour chaque page : une ligne `[p. n]`, une ligne vide, le texte de la page, une ligne vide. Une page sans texte porte `[p. n]` puis `(aucun texte détecté)`. Aucune section « Pages à vérifier ».
- Protection : avant d'écrire, si le fichier existe et que son empreinte diffère de `sortie_empreinte` du cache, il est considéré modifié à la main et **n'est pas réécrit** (le retour est faux, le statut reste inchangé). Pour un `md`, la règle de la ligne `moodlesync:` s'applique en plus, comme aujourd'hui.

### 3.5 Code retiré (R1a, puis R1b et R4)

**R1a** retire de `ocr.py` : `ecrire_index`, `ecrire_qualite`, `ecrire_cours_md`, `assembler_contexte`, `ecrire_jsonl`, `_bloc_cours`, `_grouper`, `_orphelins`, et les aides qui n'ont plus d'appelant. Règle : **ce qui garde un appelant restant est conservé** et noté au journal pour la tâche qui retire cet appelant (par exemple `_orphelins`, tant que `ocr_etat` s'en sert : R4).

**R1b** retire `_dossier_textes`, `_nom_dossier_sortie`, `_chemin_sortie` (remplacé par `chemin_texte`, 3.6) et `_dossiers_sortie` (l'exclusion d'un `Textes/` posé directement dans `dest` reste, par `moteur.dossiers_sortie_ocr`).

**R4** retire `mettre_en_file_apres_sync` et les dernières lectures de `cfg["ocr_pdf"]`, `ocr_dossier`, `ocr_sortie_hors_coffre` et `ocr_apres_sync`.

### 3.6 Chemin du texte

```python
def chemin_texte(dest: str, chemin_rel: str, cfg: dict) -> tuple[str, str]
# (chemin absolu du texte, valeur de `sortie` : relatif à dest avec "/")
```

`<dossier de la source>/<nom complet>.<format>`. `format` = `cfg["ocr_format"]` si `md` ou `txt`, sinon `md`.

## 4. API (`window.pywebview.api`)

Règles communes de `ocr-contrat.md` 2.7 : chaque méthode rend un `dict`. Erreur : `{"erreur": "<phrase française>"}` seul. Confirmation requise : `{"confirmer": "<phrase>"}` seul, la page rappelle avec `confirme=True`. Annulation de dialogue : `{"annule": True}`. Aucune clé ne contient de trace d'exception. Un chemin reçu est toujours **relatif à `dest`, avec `/`**, et passe par `_ocr_confiner` (refus : hors du coffre, composant caché, lien symbolique sortant, octet nul).

Les exemples complets sont dans `fixtures/` ; les tests des deux côtés les lisent (5.4).

### 4.1 Méthodes conservées, avec leurs changements

| Méthode | Changement |
|---|---|
| `ocr_detecter`, `ocr_choisir_exe`, `ocr_installer`, `ocr_installer_annuler`, `ocr_pause`, `ocr_reprendre`, `ocr_annuler` | inchangées |
| `ocr_ouvrir(chemin, page=None)` | **ouvre le PDF avec le lecteur du système** (décision de l'orchestrateur, sur la revue V6 : l'ancienne formule « la page l'ouvre autrement » ne faisait rien) ; confinement par `_ocr_confiner`, commande par liste d'arguments, jamais un shell (Windows `os.startfile`, macOS `open`, ailleurs `xdg-open`) ; rend `{"ok": True}` ou `{"erreur": phrase}` (`ouverture_refusee`) ; la clé `page` est ignorée ; le chemin d'un dossier est refusé (utiliser `ocr_afficher`) |
| `ocr_etat()` | forme nouvelle, 4.2 |
| `ocr_regler(cle, valeur)` | clés acceptées : `ocr_exe`, `ocr_tessdata`, `ocr_langues`, `ocr_dpi`, `ocr_psm`, `ocr_max_mo`, `ocr_threads`, `ocr_batterie`, **`ocr_format`** (`md` ou `txt`). Toute autre clé : `{"erreur": ...}` |

### 4.2 `ocr_etat()`

```json
{"moteur": {"present": true, "version": "5.5.0", "source": "portable", "exe": "...", "langues": ["eng","fra","osd"],
            "langues_effectives": "fra+eng", "repli": false, "message": ""},
 "occupe": false,
 "file": {"etat": "inactive", "origine": "coffre", "document": "", "page": 0, "pages": 0,
          "documents_faits": 0, "documents_total": 0, "reprise": 0},
 "compteurs": {"fichiers": 0, "traites": 0, "a_verifier": 0, "echecs": 0, "non_traites": 0, "pages_non_traitees": 0},
 "reglages": {"ocr_langues": "fra+eng", "ocr_dpi": 300, "ocr_format": "md"},
 "originaux": {"nombre": 0, "octets": 0},
 "depot": {"etat": "inactif", "dossier_defaut": "<Bureau>/Documents déposés", "dossier": "", "resultats": []}}
```

- Retirés : `active`, `mode_pdf`, `prevision`, `reglages.ocr_apres_sync`, `compteurs.documents`, `a_verifier` (ancienne forme), `a_preparer`, `pages_a_preparer`, `octets_texte`, `orphelins`.
- `file.etat` ∈ `inactive`, `en_cours`, `pause`, `pause_sync`, `terminee`, `annulee`. `file.origine` ∈ `coffre`, `depot`.
- `compteurs` vient de l'arborescence (4.3), sans la relire : même calcul que `ocr_arbre().compteurs`.
- `depot.etat` ∈ `inactif`, `en_cours`, `termine`. `depot.resultats` : 4.6.

### 4.3 `ocr_arbre()` (R3, `moodlesync/textes_arbre.py` et `api_arbre.py`)

Lecture seule : n'écrit rien, ne lance rien. Parcourt `dest`, applique `ocr._eligible` à chaque fichier (O11), lit `cache.json`, `file.json` et `.moodlesync.json` (pour `genere.taille_fichier`, qui reconnaît un PDF remplacé, R3c) une fois chacun.

Fonctions publiques de `moodlesync/textes_arbre.py`, que R4 appelle :

```python
def construire_arbre(dest: str, cfg: dict) -> dict                       # la forme ci-dessous
def fichiers_sous(dest: str, cfg: dict, chemins: list[str]) -> list[dict]   # nœuds « fichier » à plat ; un dossier de `chemins` est développé, doublons fusionnés, ordre de l'arbre
def compteurs(arbre: dict) -> dict                                         # les compteurs de la racine, sans relire le disque
```

```json
{"racine": "C:\\Users\\max\\Moodle",
 "cours": [
   {"type": "dossier", "nom": "Histoire contemporaine", "chemin": "Histoire contemporaine",
    "compteurs": {"fichiers": 4, "traites": 2, "a_verifier": 1, "echecs": 0, "non_traites": 1, "pages_non_traitees": 18},
    "enfants": [
      {"type": "dossier", "nom": "Semaine 3", "chemin": "Histoire contemporaine/Semaine 3", "compteurs": {...}, "enfants": [
        {"type": "fichier", "nom": "Studer 1996.pdf", "chemin": "Histoire contemporaine/Semaine 3/Studer 1996.pdf",
         "extension": "pdf", "octets": 11391303, "pages": 14, "statut": "traite", "motif": "",
         "texte": true, "format": "md", "sortie": "Histoire contemporaine/Semaine 3/Studer 1996.pdf.md",
         "remplace": true, "original_conserve": true, "confiance": 0.935, "date": "2026-11-10T14:31:53"}]}]}],
 "compteurs": {"fichiers": 4, "traites": 2, "a_verifier": 1, "echecs": 0, "non_traites": 1, "pages_non_traitees": 18}}
```

- Les `cours` sont les dossiers directement sous `dest`, sauf les dossiers cachés. Un dossier sans aucun fichier éligible dessous est omis. Tri par `ms.cle_nom`, dossiers avant fichiers.
- `pages` : nombre de pages **si le cache le connaît**, sinon `null` (l'arbre ne lit aucun PDF : il doit rester rapide sur des milliers de fichiers). Le nombre exact est calculé par `ocr_traiter` pour les seuls fichiers choisis. `confiance` : `null` si absente. `motif` : vide hors échec. `date` : vide si jamais traité. `texte`, `remplace`, `original_conserve` : faux pour un fichier non traité.
- `compteurs` d'un dossier = somme de ses descendants. `pages_non_traitees` = pages des fichiers `non_traite` ou `echec` dont `pages` est connu.
- Un échec n'a ni `sortie` ni `texte` vrai ; il a un `motif` (2.2).
- Aucune clé de chemin absolu hors `racine`.

### 4.4 `ocr_traiter(chemins, refaire=False, confirme=False)` (R4)

`chemins` : liste de chemins relatifs, chacun un **fichier ou un dossier** (un dossier vaut tous ses fichiers éligibles, récursivement). Doublons et fichiers déjà inclus par un dossier sont fusionnés.

- Sont **ignorés** : les fichiers `traite` ou `a_verifier` sauf si `refaire` ; les fichiers `echec` sauf si `refaire` (c'est le « Réessayer », O4) ; les fichiers déjà en file.
- **Sans `confirme`** : ne lance rien. Rend `{"confirmer": "<phrase>", "documents": n, "pages": n, "minutes": [mini, maxi], "remplacements": n}`. `remplacements` = nombre de PDF qui seraient remplacés (O7). Si rien n'est à faire : `{"rien": True}`.
- **Avec `confirme=True`** : met en file (`file.origine = "coffre"`), démarre l'exécuteur, rend `{"file": <bloc file de 4.2>}`.
- Moteur absent : `{"erreur": MESSAGES["moteur_absent"]}`. Une file déjà active : `{"erreur": MESSAGES["occupe"]}`.
- La phrase de confirmation est celle de `MESSAGES["confirmation_traitement"]` (5).

### 4.5 `ocr_afficher(chemin)` (R3)

Montre le fichier **dans l'explorateur** : Windows `explorer /select,"<chemin absolu>"`, macOS `open -R "<chemin absolu>"`. Pour un dossier : l'ouvre. Rend `{"ok": True}` ou `{"erreur": MESSAGES["ouverture_refusee"]}`. Aucun shell : liste d'arguments. Sous un autre système : ouvre le dossier parent (`xdg-open`), sans promesse.

### 4.6 Dépôt (R5, `moodlesync/api_depot.py`)

| Méthode | Rend |
|---|---|
| `ocr_choisir_fichiers()` | boîte de dialogue native, plusieurs PDF : `{"fichiers": [<chemin absolu>, ...]}` ou `{"annule": True}`. Les chemins absolus **ne sortent de cette méthode que pour le dépôt** |
| `ocr_choisir_dossier_depot()` | boîte de dialogue native de dossier, ouverte sur `depot.dossier_defaut` : `{"dossier": <chemin absolu>}` ou `{"annule": True}` |
| `ocr_deposer(fichiers, dossier, confirme=False)` | `fichiers` : liste de chemins absolus. Sans `confirme` : `{"confirmer", "documents", "pages", "minutes", "refuses": [{"nom", "raison"}]}`. Avec : `{"depot": {"etat": "en_cours", ...}}` |

- Seuls les **PDF** sont acceptés (U8). Un autre fichier est listé dans `refuses` avec la phrase `depot_pas_pdf`. Un fichier introuvable, protégé ou trop gros (`ocr_max_mo`) est refusé avec sa phrase.
- Le dossier de dépôt est créé s'il manque. Il sert de mini-coffre (O12) : le fichier y est **copié** (jamais déplacé ni modifié à la source), puis traité par `traiter_document(dest=dossier, ..., garder_original=False)`. Le cache vit dans `<dossier>/.moodlesync-ocr/`, marqué caché sous Windows.
- Succès : `<dossier>/<nom>.pdf` (version cherchable si au moins une page est reconnue, sinon la copie telle quelle) et `<dossier>/<nom>.pdf.<format>`.
- Échec : **rien** ne reste dans le dossier pour ce fichier (la copie est supprimée) ; le résultat porte le motif.
- Un nom déjà pris dans le dossier reçoit ` (2)`, ` (3)`... avant l'extension. Le fichier d'origine n'est jamais touché, même par erreur.
- `depot.resultats` : `[{"nom", "statut": "ok"|"a_verifier"|"echec"|"refuse", "motif": str, "sortie_pdf": str, "sortie_texte": str, "pages": int}]`, `sortie_*` en chemins absolus du dossier de dépôt, vides en cas d'échec.
- Le glisser-déposer (O16) : `application.py` enregistre un gestionnaire DOM de pywebview sur le dépôt d'un fichier ; il appelle `window.textesDepotChemins(["<chemin absolu>", ...])`. L'interface appelle ensuite `ocr_deposer`. Le bouton « Choisir des fichiers » appelle `ocr_choisir_fichiers`.

### 4.7 Autres méthodes

| Méthode | Rend |
|---|---|
| `ocr_copier_texte(chemin)` | `{"texte": str, "caracteres": int, "pages": int}` : le texte du document (`.md` ou `.txt`), sans front matter ni section « Pages à vérifier ». Document sans texte : `{"erreur": MESSAGES["copie_vide"]}` |
| `ocr_restaurer(chemin, confirme=False)` | 3.3. Sans `confirme` : `{"confirmer": MESSAGES["confirmation_restauration"]}` |
| `ocr_originaux_supprimer(confirme=False)` | libère toutes les copies d'originaux (O15). Sans `confirme` : `{"confirmer", "nombre", "octets"}`. Avec : `{"ok": True, "nombre", "octets"}`. Les documents concernés ne sont plus restaurables que par Moodle |

### 4.8 Méthodes retirées

**R1a** retire `ocr_apercu`, `ocr_chercher`, `ocr_copier` et `ocr_exporter`, `ocr_documents`, avec leurs aides privées sans autre appelant. **R4** retire `ocr_lancer` et `ocr_pdf_restaurer` quand `ocr_traiter` et `ocr_restaurer` les remplacent. Une méthode retirée n'existe plus : aucune ne doit rester, même vide.

## 5. Interface

### 5.1 Fichiers

| Fichier | Rôle | Tâche |
|---|---|---|
| `moodlesync/interface/index.html` | squelette du troisième onglet, `<script>` et `<link>` de tous les fichiers ci-dessous (les fichiers que R8 à R10 écrivent, JS et CSS, sont créés **vides, avec un commentaire d'en-tête**, par R7) | R7 |
| `moodlesync/interface/textes.js` | **coque** : sous-onglets, état partagé, chargement de l'arbre, progression, carte du moteur. Réécrit entièrement | R7 |
| `moodlesync/interface/textes-arbre.js` | **composant d'arborescence**, 5.3 | R7 |
| `moodlesync/interface/textes-cours.js` | vue « Mes cours » | R8 |
| `moodlesync/interface/textes-choisir.js` | vue « Choisir quoi traiter » | R9 |
| `moodlesync/interface/textes-deposer.js` | vue « Déposer des fichiers » | R10 |
| `moodlesync/interface/style.css` | styles de la coque et de l'arbre, section `/* Mes textes : coque */` et `/* Mes textes : arbre */` | R7 |
| `moodlesync/interface/textes-cours.css`, `textes-choisir.css`, `textes-deposer.css` | styles de chaque vue, un fichier par vue, **créés vides par R7** avec leur `<link>` | R8, R9, R10 |
| `app.js`, `sync.js` | réglages, carte de Ma semaine, retrait des dialogues obsolètes | R11 |

Un agent n'écrit **que** dans les fichiers de sa tâche. Si un fichier d'une autre tâche pose problème, il l'écrit au journal.

### 5.2 Coque (`textes.js`, R7)

Éléments fixes de `index.html` (les vues remplissent leur conteneur, elles n'ajoutent rien à `index.html`) :

```text
#v-textes
  #tx-intro            phrase d'explication courte (O8)
  #tx-moteur           carte d'installation du moteur (conservée : bouton Installer, progression, Annuler)
  #tx-travail          barre de progression du traitement en cours, avec Pause, Reprendre (visible seulement en pause, appelle ocr_reprendre) et Arrêter
  #tx-onglets          role="tablist", aria-label="Mes textes"
    #tx-o-cours   #tx-o-choisir   #tx-o-deposer      role="tab", aria-controls="tx-v-..."
  #tx-v-cours   #tx-v-choisir   #tx-v-deposer        role="tabpanel", un seul visible
```

Globales exposées par la coque (aucune autre n'est partagée) :

| Nom | Rôle |
|---|---|
| `TX` | objet d'état : `TX.arbre` (dernière réponse de `ocr_arbre`), `TX.etat` (dernière réponse de `ocr_etat`), `TX.vue` (`"cours"`, `"choisir"`, `"deposer"`) |
| `txRafraichir()` | async : relit `ocr_etat()` et `ocr_arbre()`, met à jour `TX`, appelle `rafraichir(TX)` de la vue active |
| `txMontrerVue(nom)` | active un sous-onglet (clic, flèches gauche et droite, Début, Fin) |
| `txErreur(r)` | affiche `r.erreur` en toast s'il y en a une, rend vrai alors |
| `window.textesProgres(file)` | appelée par Python (existe déjà) : met à jour `TX.etat.file`, la barre, puis émet `document.dispatchEvent(new CustomEvent("tx:progres", {detail: file}))`. À la fin (`file.etat == "terminee"`), appelle `txRafraichir()` |
| `window.textesDepotChemins(liste)` | appelée par Python au glisser-déposer : émet `new CustomEvent("tx:depot", {detail: liste})` |

Chaque vue définit une fonction globale `txVueCours`, `txVueChoisir`, `txVueDeposer` : `{ init(conteneur), rafraichir(TX), activer(), desactiver() }`. La coque appelle `init` une fois au chargement, `activer` et `desactiver` aux changements de sous-onglet, `rafraichir` après chaque `txRafraichir()` quand la vue est active.

### 5.3 Composant d'arborescence (`textes-arbre.js`, R7)

```js
txArbreCreer(conteneur, options) -> { charger(arbre), selection(), vider(), ouvrirTout(), fermerTout() }
// options : {
//   mode: "voir" | "choisir",
//   onAction: (action, noeud) => void,     // mode "voir" : action ∈ "ouvrir","afficher","copier","restaurer","reessayer"
//   onSelection: (chemins, resume) => void // mode "choisir" : chemins = liste des chemins cochés (dossiers entiers réduits à leur dossier)
// }
```

Structure du DOM, que les tests d'interface construisent **depuis le vrai `index.html`** :

```html
<ul class="tx-arbre" role="tree" aria-label="...">
  <li role="treeitem" aria-expanded="false" aria-level="1" data-chemin="Cours A" class="tx-noeud tx-dossier">
    <div class="tx-ligne">
      <button class="tx-bascule" aria-label="Ouvrir ou fermer">...</button>
      <input type="checkbox" class="tx-case" aria-label="...">       <!-- mode "choisir" seulement -->
      <span class="tx-nom">Cours A</span>
      <span class="tx-resume">4 fichiers, 2 traités</span>           <!-- dossiers -->
    </div>
    <ul role="group"> ...enfants... </ul>
  </li>
  <li role="treeitem" aria-level="3" data-chemin="Cours A/S1/article.pdf" data-statut="traite" class="tx-noeud tx-fichier">
    <div class="tx-ligne">
      <input type="checkbox" class="tx-case" aria-label="...">
      <span class="tx-nom">article.pdf</span>
      <span class="tx-badge" data-statut="traite">Traité</span>
      <button class="tx-menu" aria-haspopup="menu" aria-label="Actions sur article.pdf">...</button>   <!-- mode "voir" -->
    </div>
  </li>
</ul>
```

- Clavier (modèle ARIA `tree`) : Haut et Bas déplacent, Droite ouvre ou descend, Gauche ferme ou remonte, Espace coche (mode `choisir`), Entrée ouvre le menu d'un fichier (mode `voir`), Début et Fin. Un seul `treeitem` a `tabindex="0"`.
- Case d'un dossier : trois états. Cochée (tous les fichiers éligibles dessous), décochée, **mixte** (`aria-checked="mixed"`, propriété `indeterminate`). Cocher un dossier coche tous ses descendants ; la sélection rendue contient le dossier seul quand il est entièrement coché (pas ses fichiers).
- En mode `choisir`, seuls les fichiers `non_traite` et `echec` sont cochables ; les autres sont affichés, grisés, avec leur badge, `aria-disabled="true"`. Les dossiers n'ont jamais de case désactivée : leur case porte sur ce qui reste cochable. Un dossier sans rien de cochable a sa case désactivée.
- Menu d'un fichier (mode `voir`) : `ouvrir` (toujours), `afficher` (toujours), `copier` (si `texte`), `restaurer` (si `remplace`, décision O18 : un PDF textuel traité n'est pas remplacé, il n'y a rien à restaurer), `reessayer` (si `echec`). Libellés en 5.5.
- Le composant n'appelle **jamais** l'API : il rend des données et émet des actions. Les vues appellent l'API.
- Aucun HTML construit par concaténation : `createElement` et `textContent` seulement (règle de `textes.js` actuel).
- État replié ou ouvert conservé par `chemin` pendant la durée de la page, entre deux `charger()`.

### 5.4 Vues

**« Mes cours » (R8)** : l'arbre en mode `voir`, la phrase d'état (« 12 documents traités, 2 à vérifier, 1 non réussi »), un bouton « Tout ouvrir » / « Tout fermer », un bouton « Actualiser ». Actions : `ouvrir` appelle `ocr_ouvrir`, `afficher` appelle `ocr_afficher`, `copier` appelle `ocr_copier_texte` puis copie dans le presse-papiers (avec le repli de l'actuel `txCopier`), `restaurer` appelle `ocr_restaurer` (deux temps : confirmation, puis `confirme=True`), `reessayer` appelle `ocr_traiter([chemin], refaire=True)` puis la même confirmation. État vide : phrase d'accueil et renvoi vers « Choisir quoi traiter ». Un document `a_verifier` ou `echec` montre sa phrase de motif sous son nom.

**« Choisir quoi traiter » (R9)** : l'arbre en mode `choisir`, un résumé vivant (« 3 documents choisis, environ 41 pages », ou « 3 documents choisis » si une page est inconnue : les nombres exacts viennent du dialogue de confirmation), un bouton « Traiter la sélection » (désactivé sans sélection ou sans moteur) qui appelle `ocr_traiter(selection)` sans `confirme`, ouvre le dialogue de confirmation (`<dialog id="d-tx-confirmer">` créé par R9 dans son conteneur, pas dans `index.html`) avec `documents`, `pages`, `minutes`, `remplacements`, puis rappelle avec `confirme=True`. Cases « Tout cocher » et « Tout décocher ». Moteur absent : le bouton montre « Installer le moteur » et renvoie à `#tx-moteur`.

**« Déposer des fichiers » (R10)** : une zone de glisser-déposer (`role="button"`, `tabindex="0"`, Entrée et Espace ouvrent le sélecteur), un bouton « Choisir des fichiers » (`ocr_choisir_fichiers`), puis le dossier de destination (« Les résultats seront rangés dans : `<dossier>` », bouton « Changer » = `ocr_choisir_dossier_depot`), puis la liste des fichiers retenus et des fichiers refusés avec leur phrase, puis « Extraire le texte » (`ocr_deposer`, deux temps comme R9). Pendant le travail : la barre de la coque. À la fin : la liste des résultats (`depot.resultats`) avec, pour chaque succès, « Afficher dans l'explorateur » (appelle `ocr_afficher` sur le dossier de dépôt). Un échec dit la phrase de son motif et « Ton fichier n'a pas été modifié ».

### 5.5 Phrases visibles

Les phrases de l'interface vivent dans la table `TX_MOTS` de `textes.js` (R7 la crée avec **toutes** les phrases ci-dessous ; les vues s'en servent, elles n'en ajoutent pas sans l'écrire au journal) et, côté Python, dans `ocr.MESSAGES`. « OCR » et « Tesseract » n'apparaissent **que** dans le tiroir des réglages (contrat 3.4 de `ocr-contrat.md`, conservé).

| Clé | Phrase |
|---|---|
| `intro` | « Choisis les documents dont tu veux le texte. Le PDF est remplacé par une version cherchable, une copie de l'original est gardée, et le texte est écrit à côté. » |
| `onglet_cours` | « Mes cours » |
| `onglet_choisir` | « Choisir quoi traiter » |
| `onglet_deposer` | « Déposer des fichiers » |
| `statut_non_traite` | « Non traité » |
| `statut_en_attente` | « En attente » |
| `statut_en_cours` | « En cours » |
| `statut_traite` | « Traité » |
| `statut_a_verifier` | « À vérifier » |
| `statut_echec` | « Non réussi » |
| `motif_difficile` | « Le texte de ce document est trop abîmé pour être lu. Ton PDF est resté tel quel. » |
| `motif_vide` | « Aucun texte n'a été trouvé dans ce document. Ton PDF est resté tel quel. » |
| `motif_illisible` | « Ce document n'a pas pu être lu. Ton PDF est resté tel quel. » |
| `motif_verification` | « Le PDF cherchable n'a pas passé la vérification. Ton PDF est resté tel quel. » |
| `motif_ecriture` | « Le résultat n'a pas pu être écrit. Ton PDF est resté tel quel. » |
| `motif_erreur` | « Cette opération n'a pas abouti. Ton PDF est resté tel quel. » |
| `avertissement_a_verifier` | « Certaines pages sont peu sûres : vérifie le texte. » |
| `action_ouvrir` | « Ouvrir le PDF » |
| `action_afficher` | « Afficher dans l'explorateur » (sous macOS : « Afficher dans le Finder ») |
| `action_copier` | « Copier le texte » |
| `action_restaurer` | « Restaurer l'original » |
| `action_reessayer` | « Réessayer » |
| `tout_ouvrir` / `tout_fermer` | « Tout ouvrir » / « Tout fermer » |
| `traiter_selection` | « Traiter la sélection » |
| `choix_resume` | « {n} documents choisis, environ {p} pages » (accord : « 1 document choisi, environ 1 page ») : seulement quand les pages de **tous** les fichiers choisis sont connues |
| `choix_resume_sans_pages` | « {n} documents choisis » (accord : « 1 document choisi ») |
| `deposer_zone` | « Glisse des PDF ici » |
| `deposer_choisir` | « Choisir des fichiers » |
| `deposer_destination` | « Les résultats seront rangés dans : {dossier} » |
| `deposer_changer` | « Changer » |
| `deposer_lancer` | « Extraire le texte » |
| `deposer_intact` | « Ton fichier n'a pas été modifié. » |
| `etat_vide` | « Rien à montrer pour l'instant. Choisis des documents dans « Choisir quoi traiter ». » |
| `resume_cours` | « {t} traités, {v} à vérifier, {e} non réussis » |

Côté Python, `ocr.MESSAGES` gagne : `confirmation_traitement` (« {n} documents, environ {p} pages, {m} à {x} minutes. {r} PDF seront remplacés par une version cherchable ; une copie de chaque original est gardée. »), `confirmation_restauration` (« Remettre le PDF d'origine et supprimer le texte ? »), `restauration_texte_garde` (« Le PDF d'origine est remis. Le texte, que tu avais modifié, est resté en place. »), `copie_vide` (« Ce document n'a pas de texte à copier. »), `depot_pas_pdf` (« Seuls les PDF peuvent être déposés. »), `occupe` (existe). Les phrases du tableau précédent pour les motifs existent aussi côté Python (`MESSAGES["motif_<code>"]`), avec le même texte.

### 5.6 Données de développement

`fixtures/` contient les réponses d'exemple de `ocr_arbre`, `ocr_etat`, `ocr_traiter` (confirmation) et `depot`. Les tâches d'interface (R7 à R10) s'en servent pour leurs tests, avec une fausse `api()` qui rend ces objets. **Les tâches de Python (R3, R4, R5) valident leurs vraies sorties contre les mêmes fichiers** : un test compare l'ensemble des clés (récursivement) et le type de chaque valeur. Si une forme change, la tâche qui la change met à jour le contrat **et** les fixtures dans le même commit, et le dit au journal.

## 6. Réglages (R11, `app.js`)

- Un champ « Format du texte » (liste : « Markdown (.md) », « Texte brut (.txt) ») appelle `ocr_regler("ocr_format", ...)`, valeur lue dans `ocr_etat().reglages.ocr_format` (jamais dans une variable de page, règle de l'écart 240).
- Une ligne « Copies d'originaux : {nombre}, {volume} » avec un bouton « Supprimer les copies » (deux temps, `ocr_originaux_supprimer`).
- **Retirés** : la liste « Version cherchable des PDF », son consentement, la case « Extraction automatique après synchronisation », le choix du dossier de sortie.
- Le tiroir garde les réglages du moteur (chemin, langues, résolution).

## 7. Synchronisation (R4, `moteur.py`)

- La synchronisation **ne lance plus jamais** de préparation : `mettre_en_file_apres_sync` et son appel disparaissent. La ligne « Textes à préparer à la prochaine ouverture » disparaît aussi.
- Le compte rendu de `telecharger` garde `republies_generes` (utile à l'ancienne version, 7.1) ; `a_preparer` est retiré.
- 7.1 : quand Moodle republie un PDF déjà traité (`genere` présent, source changée), le texte à côté est renommé « ancienne version AAAA-MM-JJ » (`archiver_texte`, adapté au nouvel emplacement, `.md` ou `.txt`), le nouveau PDF est téléchargé, et le fichier redevient « Non traité » (son entrée de cache est retirée). La copie d'original du PDF remplacé est supprimée.
- `moteur.dossiers_sortie_ocr` et l'exclusion de `Textes/` dans `index_existant` sont **conservés** par toute la refonte : un coffre qui n'a pas encore migré garde un `Textes/` que la synchronisation ne doit pas prendre pour des fichiers Moodle. Les retirer est un nettoyage ultérieur, hors de cette refonte.

## 8. Migration (R6, `moodlesync/textes_migration.py`)

Au premier démarrage où `config.json` ne porte pas `"textes_v2": true` :

1. S'il n'y a pas de `Textes/` dans `dest` : écrire `textes_v2` et finir, sans annonce.
2. Pour chaque `.md` de document sous `Textes/<Cours>/.../<nom>.md` dont le PDF source existe : le **déplacer** à côté du PDF (`<dossier du PDF>/<nom>.md`), mettre à jour `sortie` dans le cache, renseigner `format = "md"` et `sortie_empreinte`. Pas de `remplace` ni de `original` (U9) : `remplace` est lu dans `.moodlesync.json` (`genere`) et `original` vaut `null`.
3. Un document dont l'ancien état est `difficile` (O14) : son `.md` **non édité** (ligne `moodlesync:` présente) est supprimé et l'entrée devient `echec`, motif `difficile` ; un `.md` édité est déplacé comme au 2.
4. Un `.md` dont le PDF source n'existe plus : laissé en place dans `Textes/` (l'annonce le dit) ; `Textes/` n'est alors pas supprimé.
5. Supprimer `index.md`, `Qualité des textes.md`, les fichiers « texte des documents » et les `.jsonl`.
6. Supprimer `Textes/` si elle est vide ; sinon la laisser et le dire.
7. Écrire `textes_v2: true` dans `config.json`, puis annoncer **une fois** : `window.textesMigration({"deplaces": n, "supprimes": n, "restants": n})`, affiché en toast par la coque.

La migration est **idempotente** : relancée, elle ne refait rien de ce qui est fait et ne perd rien. Elle ne touche jamais un PDF.

## 9. Invariants de la refonte

1. **Un PDF n'est jamais modifié sans copie de l'original** (sauf un PDF migré, U9, et un fichier déposé, qui est une copie).
2. **Un échec ne laisse aucune trace visible** à côté du PDF : ni `.md`, ni `.txt`, ni copie d'original, ni PDF remplacé.
3. **Un texte modifié à la main n'est jamais réécrit ni supprimé** (hors restauration, qui le dit).
4. **Un fichier déposé n'est jamais touché à sa source.**
5. L'interface **n'appelle l'API que depuis les vues** ; le composant d'arborescence ne l'appelle jamais.
6. Aucun chemin absolu n'est montré à l'étudiant, sauf le dossier de dépôt et la racine du coffre.
7. L'arborescence et les compteurs sont **lus, jamais déduits d'un parcours du disque par l'interface**.
8. Aucune méthode retirée (4.8) ne subsiste, même vide.

## 10. Ce qui n'est pas dans cette refonte

Le moteur de reconnaissance, la relecture tournée, la vérification du rendu, l'installation du moteur, Ma semaine hors sa carte, l'horaire, la synchronisation hors 7. Aucune publication au dépôt public. Aucune CI lancée sur le compte de Maxence.
