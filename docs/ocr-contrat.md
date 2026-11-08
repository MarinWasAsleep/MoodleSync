# Contrat OCR : interfaces et invariants

Tâche E0, 7 novembre 2026, révisé le même jour après les décisions D1 à D7 (section 7). Contrat version 1. Source : `docs/plan-ocr.md` (noté « plan »), `docs/plan-execution-ocr.md`.
Les valeurs marquées **S1** ont été fixées après la revue du spike (D8 à D11, section 7, 7 novembre 2026). Tout ce qui est marqué **à confirmer** est une proposition de ce contrat, pas une décision du plan.
Les contradictions relevées dans le plan sont tranchées en section 7. Le plan doit être aligné sur ce contrat (liste à la fin de la section 7).

## 1. Objet et périmètre

**Fixé ici** : formes JSON (disque et API), noms et signatures des modules, identifiants DOM, invariants de sûreté, messages visibles, tests exigés, méthode de la couche de texte (D8), tolérance du rendu (D9), borne de volume (D10).
**Non fixé** : algorithmes internes de reconnaissance, apparence CSS, microcopy marketing du panneau « À quoi ça sert ? » (plan 3.6).
**Non-objectifs** : écriture manuscrite, formules, `.docx` et `.pptx` (lot 2 du plan), mode `ocr_pdf = "copie"`, JSONL par défaut, Ghostscript, OCRmyPDF, PyMuPDF (AGPL), paquet portable Tesseract (signature réservée en 3.1, implémentation hors E0).

**Faits du dépôt dont le contrat dépend** (vérifiés dans le code le 7 novembre 2026) :
- `moteur.empreinte(chemin)` : SHA-1 des 256 premiers Ko. `index_existant(dest)` renvoie `(par_nom, par_taille)` et ignore dossiers cachés et `*.part`. `telecharger` renomme l'ancien fichier en « ancienne version » (`T["ancienne"]`). `pdf_range` exige `taille locale == taille Moodle`.
- `.moodlesync.json` : `{cle_url(url): {"t": int, "chemin": str}}` plus `"_sections"`. `chemin` relatif à `dest`, séparateur du système. `sauver_etat` écrit `.tmp` puis `os.replace`.
- `Api(ApiHoraire)` : les méthodes publiques sont exposées à la page. `ApiHoraire.__init__` n'appelle pas `super().__init__()`. `_js(fonction, valeur)` appelle `window.<fonction>(valeur)`. `Api._long` est le verrou de la synchronisation.
- Conventions : JSON en UTF-8 sans BOM, écriture atomique, dates locales `AAAA-MM-JJTHH:MM:SS`, tailles en octets, identifiants Python en français sans accent, messages en français sans tiret long.
- Dans les JSON **nouveaux**, les chemins relatifs utilisent `/` et la forme NFC. Dans `.moodlesync.json`, le séparateur du système est conservé. Comparaison : `os.path.normcase(os.path.normpath(...))`.
- Chaque fichier JSON nouveau porte `"version": 1`. Une version supérieure à celle connue rend le fichier illisible : il est traité comme absent et **jamais réécrit**.

## 2. Contrats de données

### 2.1 Entrée `.moodlesync.json` d'un PDF généré

```json
{"https://moodle.exemple.ch/pluginfile.php/12/mod_resource/content/1/article.pdf": {
  "t": 1760000000, "chemin": "Cours A\\Section 1\\article.pdf",
  "genere": {"type": "pdf_cherchable", "taille_source": 18000000, "empreinte_source": "sha256:<hex>",
             "taille_fichier": 18300000, "empreinte_fichier": "sha256:<hex>",
             "pages": 24, "date": "2026-11-07T18:30:00", "version": 1}}}
```

| Clé | Type, unité | Défaut | Invariant |
|---|---|---|---|
| `t` | int, secondes epoch | 0 | `timemodified` Moodle. Jamais modifié par une génération. |
| `chemin` | str, relatif à `dest` | obligatoire | Chemin actuel du fichier sur disque. |
| `genere` | objet | absent | Absent = fichier natif. Présent seulement pour un PDF cherchable fabriqué par MoodleSync. |
| `genere.taille_source`, `empreinte_source` | int octets ; str `"algo:hex"` | obligatoires | Identité du PDF **reçu de Moodle**, mesurée avant toute transformation. Format fixé : `"sha256:<hex>"` du **fichier entier** (D2). |
| `genere.taille_fichier`, `empreinte_fichier` | idem | obligatoires | Identité du PDF **cherchable**, mesurée sur le fichier temporaire vérifié. |
| `genere.type`, `pages`, `date`, `version` | `"pdf_cherchable"` ; int ≥ 1 ; str ISO ; int | obligatoires, `version` = 1 | `pages` = pages de la source = pages du fichier. `version` supérieure au connu : `genere` ignoré, fichier traité comme natif. |

Une seule personne écrit `genere` : `ocr.fabriquer_pdf_cherchable` via `moteur.sauver_etat`. Un lecteur qui trouve un `genere` incomplet l'ignore.

### 2.2 Marque dans les métadonnées du PDF

Clé du dictionnaire `/Info` : `/MoodleSyncGenere`, valeur : chaîne JSON compacte (moins de 1 Ko).

```json
{"v": 1, "url": "https://moodle.exemple.ch/pluginfile.php/12/mod_resource/content/1/article.pdf",
 "t": 1760000000, "taille_source": 18000000, "empreinte_source": "sha256:<hex>", "pages": 24}
```

Invariants : `url` = `cle_url(url)`, **jamais** de jeton ni de paramètre ; aucun chemin local ; aucune identité du fichier lui-même (elle ne peut pas s'y contenir). Lecture par `ocr.lire_marque(chemin) -> dict | None`, qui ne lève jamais.

### 2.3 Cache `.moodlesync-ocr/cache.json` (nom confirmé par C3)

```json
{"version": 1, "documents": {"Cours A/Section 1/article.pdf": {
  "empreinte": "sha256:<hex>", "taille": 1234567, "pages": 24, "pages_texte": 2, "pages_ocr": 22, "numeros_ocr": [3, 4],
  "pages_vides": 0, "extraction": "ocr", "confiance": 0.89, "langues": "fra+eng", "dpi": 300, "psm": 3,
  "moteur": "5.5.3", "sortie": "Textes/Cours A/Section 1/article.pdf.md", "etat": "ok", "verifie": false,
  "date": "2026-11-07T18:30:00"}}}
```

| Clé | Type, unité | Défaut | Invariant |
|---|---|---|---|
| clé du dictionnaire | str, chemin `/` NFC | obligatoire | Chemin du document **tel que rangé** (PDF cherchable compris). Unique. |
| `empreinte`, `taille` | str ; int octets | obligatoires | Identité de la **source** : pour un PDF cherchable, `genere.empreinte_source`, pas celle du fichier. Sert à retrouver une entrée après déplacement. |
| `pages`, `pages_texte`, `pages_ocr`, `pages_vides` | int ≥ 0 | 0 | `pages_texte + pages_ocr + pages_vides == pages`. Une page illisible (`illisible`, 3.1) compte dans `pages_vides` (C3). |
| `numeros_ocr` | list[int], base 1 | `[]` | Pages passées par la reconnaissance. Obligatoire pour re-océriser un PDF cherchable (invariant 3). Ajout de ce contrat, à confirmer. |
| `extraction` | `"texte"`, `"ocr"`, `"mixte"`, `"vide"` | obligatoire | Tous natifs, tous reconnus, ou les deux. `"vide"` (écart 50, décision de Maxence) : aucune page native ni reconnue, donc `pages_texte = pages_ocr = 0`, `pages_vides = pages` et `confiance` nulle. Le `.md` écrit la même valeur. |
| `confiance` | float 0 à 1, 3 décimales, ou `null` | `null` | Moyenne des mots reconnus, valeurs négatives ignorées. `null` si aucune page reconnue. Unité fixée par D5. |
| `langues`, `dpi`, `psm`, `moteur` | str, int, int, str | réglages du moment | Un écart avec les réglages actuels rend l'entrée périmée sans toucher aux autres. **Ce sont les seules clés d'invalidation** (écart 7, C3) : `oem` est constant (1) et `tessdata` est un dossier local, qui n'entre ni dans le cache ni dans l'invalidation. Un autre modèle de langue de même version de moteur n'est donc pas détecté. |
| `sortie` | str, chemin `/` | obligatoire | `.md` du document, relatif à `dest` (`<ocr_dossier>/<chemin du document>.md`, « Textes » par défaut), ou absolu si `ocr_sortie_hors_coffre` (dossier `ocr_dossier` dans le dossier de données de MoodleSync, choix déduit par C3). Un `ocr_dossier` qui n'est pas un nom simple (séparateur, `..`, caractère interdit) est remplacé par « Textes ». |
| `etat`, `verifie`, `date` | `"ok"`, `"a_verifier"`, `"difficile"`, `"erreur"`, `"ignore"` ; bool ; str ISO | `"ok"`, `false`, obligatoire | `etat` dérive des pages (écart 8, C3) : `classer` « bon » donne `"ok"`, « a_verifier » donne `"a_verifier"`, « difficile » donne `"difficile"`, et le document prend la pire page. Une page sans texte détecté (source `vide`, reconnue sans mot) ou illisible rend le document `"a_verifier"`, de sorte que `"ok"` veut dire « section Pages à vérifier vide ». Un document `extraction: "vide"` est `"a_verifier"` : `etat` n'a pas de valeur `"vide"` (le `qualite` `"vide"` de `ocr_documents` se déduit de `extraction`, tâche C5). `"erreur"` et `"ignore"` ne sont pas écrits par C3 (aucune entrée n'est créée pour un document en échec) ; une entrée `"erreur"` n'est jamais valide. `verifie` masque l'avertissement sans changer le texte ; il est conservé quand le même contenu est refait ou déplacé. `date` : fin du dernier passage réussi. |

### 2.4 Reprise par page `.moodlesync-ocr/pages/<hex de l'empreinte>.json`

```json
{"version": 1, "empreinte": "sha256:<hex>", "reglages": {"langues": "fra+eng", "dpi": 300, "psm": 3, "moteur": "5.5.3"},
 "pages": 24, "faites": {"1": {"source": "texte", "texte": "...", "confiance": null, "mots": 0},
                         "3": {"source": "ocr", "texte": "...", "confiance": 0.912, "mots": 310,
                               "boites": [[x, y, l, h, 0.93, "mot"]]}}}
```

Invariants : réécrit en entier (atomique) après **chaque** page ; clés de `faites` = numéros de page en chaîne ; `source` ∈ `texte`, `ocr`, `vide` ; `boites` (pixels au `dpi` du bloc `reglages`) n'existe que si `ocr_pdf == "remplacer"` (à confirmer ; C2 les produit quand l'appelant passe `avec_boites=True`, voir 3.1) ; un bloc `reglages` (les quatre clés ci-dessus, comme le cache), une `empreinte` ou un nombre de `pages` différents de l'actuel : fichier ignoré, document repris à zéro (C3) ; avec `ocr_pdf == "remplacer"`, une page reconnue sans `boites` est refaite (C3) ; supprimé à la fin d'un document réussi, une fois le `.md` écrit et le cache à jour ; en mode `remplacer`, il est conservé après l'extraction, sert les `boites` de `fabriquer_pdf_cherchable` et n'est supprimé qu'après un remplacement réussi (écart 60). Une page illisible n'est pas inscrite dans `faites` : elle est retentée à la reprise.

### 2.5 File `.moodlesync-ocr/file.json` (nom confirmé par C3)

```json
{"version": 1, "etat": "pause", "portee": "sans_texte", "cree": "2026-11-07T18:00:00",
 "taches": [{"chemin": "Cours A/Section 1/article.pdf", "etat": "attente", "priorite": 0,
             "pages": 24, "pages_faites": 12, "ajoute": "2026-11-07T18:00:00", "message": ""}]}
```

| Clé | Type | Défaut | Invariant |
|---|---|---|---|
| `etat` | `"inactive"`, `"en_cours"`, `"pause"`, `"annulee"` | `"inactive"` | Au chargement, `"en_cours"` devient `"pause"` : **aucune reprise automatique**, la page propose « Reprendre ». |
| `portee` | `"tout"`, `"sans_texte"`, `"cours:<cid>"`, `"document:<chemin>"` | `"sans_texte"` | Même syntaxe pour `ocr_lancer`, `ocr_copier`, `ocr_exporter`. |
| `taches[].etat` | `"attente"`, `"en_cours"`, `"fait"`, `"erreur"`, `"ignore"` | `"attente"` | Un chemin n'apparaît qu'une fois. Écrit après chaque page et chaque document. |
| `taches[].message` | str | `""` | Phrase de la section 5 ou vide. Jamais de détail technique (il va dans `erreurs.txt`). |
| `taches[].refaire` | bool, clé facultative | absente (faux) | Ajout de C3 : posée par `constituer_file(..., refaire=True)` sur les tâches en attente, lue par l'exécuteur (`extraire_document(..., refaire=True)`), pour qu'une reprise après arrêt n'oublie pas le choix. |

Ne sont jamais mis en file : `Textes/` (le dossier de sortie placé directement dans `dest`), `.moodlesync-ocr/` et tout fichier ou dossier caché, les fichiers « ancienne version » (`T["ancienne"]`, en français et en anglais), les `*.md`, les fichiers de plus de `ocr_max_mo` (300 Mo par défaut). Seuls les PDF et les images du plan 4.1 sont pris. Un PDF protégé ou abîmé est mis en file avec l'état `"ignore"` et sa phrase de la section 5 dans `message` (rien n'est lancé pour lui).

Portées (C3, lecture déduite du plan 3.2) : `tout` = documents éligibles sans entrée de cache valide ; `sans_texte` = parmi eux, ceux qui ont au moins une page à reconnaître (scan, PDF mixte, image) ; `cours:<cid>` = comme `tout`, limité au dossier du cours donné par `cfg["cours"][cid]["dossier"]` (le nom par défaut vient de Moodle et n'est pas connu hors ligne : sans ce réglage, la portée est vide) ; `document:<chemin>` = ce document seul. Un document dont l'entrée est valide n'est mis en file que si `refaire` est vrai. Au chargement, une tâche `"en_cours"` redevient `"attente"` (ses pages faites restent dans `pages/`).

### 2.6 Arborescence de sortie

```text
<dest>/Textes/                     (T["textes"] : "Textes" ou "Texts" ; réglage ocr_dossier)
  index.md   Qualité des textes.md   (T["qualite_textes"], à confirmer pour l'anglais)
  <Cours>/<Cours> - texte des documents.md   (T["texte_complet"])
  <Cours>/<Section>/<nom du document avec extension>.md           ex. article.pdf.md
  <Cours>/<Section>/article.pdf (ancienne version AAAA-MM-JJ).md  (nom_ancienne_version)
<dest>/.moodlesync-ocr/{cache.json, file.json, pages/}
```

Marqueurs de page : `<!-- page n -->` dans le `.md` d'un document, `[p. n]` dans le fichier de cours et dans la copie. Front matter et entête : plan 6.1 à 6.3, avec une clé de plus (D4). **Marque de régénération** : le `.md` d'un document porte dans son front matter la ligne `moodlesync: "régénéré à chaque passage, supprime cette ligne pour garder le fichier tel quel"` ; le front matter reste en tête du fichier (Obsidian). Fichiers de cours, `index.md` et `Qualité des textes.md` : `ms.MARQUE` en première ligne, comme les autres notes générées. Les `.md` ne contiennent jamais de chemin absolu.

**Nom du fichier de cours** (décision de Maxence, 8 novembre 2026, écart 76) : `<Cours> - texte des documents.md`, celui que C5 écrit. La clé de traduction `texte_complet` garde son nom (3.3) ; seul le nom affiché du fichier est `texte des documents`, et le titre reste `# <Cours> : texte des documents` (plan 6.2).

### 2.7 Formes renvoyées par l'API

Règles communes : chaque méthode renvoie un `dict`. Erreur : `{"erreur": "<phrase française>"}` seul. Confirmation requise : `{"confirmer": "<texte>"}` seul, la page rappelle avec `confirme=True`. Annulation de dialogue : `{"annule": True}`. Les compteurs sont des int ≥ 0, `confiance` un float 0 à 1 ou `null`. Aucune clé ne contient de trace d'exception.

**`ocr_etat()`** et le bloc `"ocr"` de `sync_etat()` :

```json
{"moteur": {"present": true, "version": "5.5.3", "source": "registre", "exe": "C:\\...\\tesseract.exe",
            "langues": ["eng", "fra", "osd"], "langues_effectives": "fra+eng", "repli": false, "message": ""}, "active": false, "mode_pdf": "aucun", "occupe": false,
 "file": {"etat": "inactive", "document": "", "page": 0, "pages": 0, "documents_faits": 0, "documents_total": 0, "reprise": 0},
 "compteurs": {"documents": 0, "pages": 0, "a_verifier": 0, "a_preparer": 0, "pages_a_preparer": 0, "octets_texte": 0, "orphelins": 0},
 "reglages": {"ocr_langues": "fra+eng", "ocr_dpi": 300}}
```

`moteur.source` ∈ `config`, `path`, `registre`, `usuel`, `portable`. Quand `repli` est vrai, `message` vaut `langue_manquante` ; `langues_effectives == ""` avec `repli` vrai signifie « moteur présent sans langue utilisable » (aucune reconnaissance possible), et `tessdata == ""` « ne pas passer `--tessdata-dir` » (conventions de C1, 3.1). `file.etat` ∈ valeurs de 2.5 plus `"pause_sync"` et `"terminee"`. `file.reprise` = documents restants d'une file en pause. `occupe` = extraction ou restauration en cours. Le bloc `"ocr"` de `sync_etat` ne garde que `{"moteur": bool, "active": bool, "a_preparer": int, "en_attente": int, "pret": int, "a_verifier": int, "reprise": int}`.

**`ocr_documents(filtre=None)`** : `filtre` = `{"cours": cid|null, "qualite": "bon"|"a_verifier"|"difficile"|"orphelin"|null, "type": "texte"|"scanne"|null}`.
`{"documents": [{"chemin", "cours", "section", "nom", "type": "texte|scanne|mixte", "pages", "qualite": "bon|a_verifier|difficile|vide", "confiance", "cherchable": bool, "verifie": bool, "orphelin": bool, "sortie", "date"}], "total": int, "pages": int}`. Trié par cours, section, nom (`ms.cle_nom`). `cherchable` = l'état porte `genere` et le fichier existe. Une ligne n'affiche jamais « déjà présent ».

**`ocr_chercher(texte, limite=50)`** : texte de moins de 2 caractères : `{"resultats": [], "total": 0, "tronque": false}`. Recherche sans casse ni accents. Sinon `{"resultats": [{"chemin", "cours", "section", "nom", "page": int, "segments": [{"t": "str", "m": bool}]}], "total": int, "tronque": bool}`. `segments` découpe l'extrait (`m` vrai = terme trouvé) : pas de décalages, donc pas de piège UTF-16.

**`ocr_apercu(chemin="", page=1)`** : `{"image": "data:image/png;base64,...", "largeur": int, "hauteur": int, "texte": str, "confiance": float|null, "qualite": str, "source": "texte|ocr|vide", "chemin": str, "nom": str, "page": int, "exemple": bool}`. `chemin` vide : le moteur choisit un scan. `exemple` vrai : document embarqué, moteur absent ou aucun scan. Image : 900 px de large au plus (D11). **N'écrit rien, ne met rien en file.**

**`ocr_lancer(portee="sans_texte", refaire=False, confirme=False)`** : `{"file": <bloc file>}`, ou `{"rien": True}`, ou `{"confirmer": ..., "documents": int, "pages": int, "minutes": [min, max]}` quand le lot dépasse 50 documents ou 500 pages et que `confirme` est faux. `refaire` ignore le cache du document.

**`ocr_copier(portee)`** : `{"texte": str, "caracteres": int, "documents": int, "pages": int}`. Au-delà de 2 000 000 caractères : `{"trop_long": True, "caracteres": int}` (plafond à confirmer). Le presse-papiers est écrit par la page.

**`ocr_exporter(portee, format="zip")`** : `format` ∈ `zip`, `zip_jsonl`, `md`. `{"chemin": str, "octets": int, "documents": int}`, ou `{"annule": True}`. Le chemin vient d'une boîte de dialogue native (à confirmer). Le JSONL suit le plan 6.4.

## 3. Frontières des modules et signatures

Règle : toute exception prévue est `ocr.ErreurOcr(ms.Erreur)`, de `code` fixe et de message pris dans `MESSAGES` (section 5). `ms.Annule` signale une annulation. Aucune autre exception ne sort d'une fonction publique sans passer par `ms.message_erreur`.

### 3.1 `moodlesync/ocr.py`

```python
CACHE = ".moodlesync-ocr"; SEUIL_TEXTE = 80; SEUILS_QUALITE = (0.85, 0.70)   # conservés, non calibrés (D11)
# Deux points d'entrée remplaçables par les tests, les seuls à toucher un sous-processus ou le rendu :
def executer(args: list[str], *, delai: float, arreter=None) -> tuple[int, bytes, bytes]   # CREATE_NO_WINDOW, priorité basse
def rendre_page(chemin: str, numero: int, dpi: int, *, preparer=True):                # image Pillow en niveaux de gris ;
    # preparer=False rend l'image brute, sans autocontraste : seule forme comparee par la verification du rendu (D9, ecart 69).

# Moteur
def detecter(cfg: dict) -> dict          # ne lève jamais. Clés de ocr_etat()["moteur"] plus "exe", "tessdata", "majeure": int
def reglages_depuis(cfg: dict) -> dict   # {"langues", "dpi", "psm", "oem": 1, "moteur", "tessdata"} ; langues effectives après repli
    # Conventions de C1, lues par C2 : langues_effectives == "" avec repli vrai (et message langue_manquante) signifie « moteur présent,
    # sans langue utilisable » : on ne lance jamais -l "", on lève langue_manquante. tessdata == "" signifie « ne pas passer --tessdata-dir ».
def installer_paquet(progres=None, arreter=None) -> dict    # RÉSERVÉ à la 2.6 (D6). SHA-256 obligatoire. Seul appel réseau d'extraction autorisé.

# Une page
def parser_tsv(tsv: str) -> list[dict]       # niveau 5 seulement ; {"bloc","par","ligne","x","y","l","h","conf": float,"texte": str}
def reconstruire(mots: list[dict]) -> tuple[str, float | None]   # texte ordonné par bloc, paragraphe, ligne, x ; confiance 0 à 1
def decider_source(texte_natif: str) -> str                      # "texte" si au moins SEUIL_TEXTE caractères alphanumériques, sinon "ocr"
def classer(confiance: float | None) -> str                      # "bon", "a_verifier", "difficile", "vide"
def extraire_page(chemin: str, numero: int, reglages: dict, *, forcer_ocr=False, arreter=None, exe="", avec_boites=False) -> dict
    # {"numero", "source": "texte|ocr|vide", "texte", "confiance", "mots", "boites": list | None}
    # Page sans texte et sans image : source "vide", pas une erreur. Image isolée ou TIFF : numero compte les cadres.
    # Lève ErreurOcr(code="illisible") pour une page ; l'appelant la signale et continue. Autres codes : protege, corrompu
    # (ouverture du PDF), moteur_absent (exe vide), langue_manquante (reglages["langues"] == ""). ms.Annule si arreter() le demande.
    # exe (C2) : chemin du moteur, pris dans detecter(cfg)["exe"] ; reglages_depuis ne le porte pas et sa forme ne change pas.
    #   Requis pour la reconnaissance seulement : une page native suffisante ne lance et n'exige rien (T2).
    # avec_boites (C2) : l'appelant le met à vrai si cfg["ocr_pdf"] == "remplacer" (C4). Alors boites = [[x, y, l, h, confiance 0 à 1, mot]]
    #   en pixels au dpi de reglages, dans l'ordre du TSV ; sinon None. C2 ne lit jamais cfg.
    # Une page native suffisante est lue par pypdf, normalisée (NFC, espaces multiples, mot coupé en fin de ligne avant une minuscule,
    #   sauts de paragraphe), source "texte", confiance None. Une page sans texte alphanumérique et sans image est "vide" ;
    #   une page à texte insuffisant (moins de SEUIL_TEXTE) est reconnue, image ou non.
class ErreurOcr(ms.Erreur):                                    # ErreurOcr(code, **champs) ; .code ; str() = MESSAGES[code].format(**champs)
def parser_tsv(...)   # conf est ramenée de 0 à 1 (TSV / 100, D5) ; une conf négative reste négative et est ignorée par reconstruire
    # reconstruire : un saut de ligne entre les lignes, une ligne vide entre les paragraphes ; confiance arrondie à 3 décimales
def ecrire_document_md(chemin_md: str, chemin_rel: str, pages: list[dict], reglages: dict, *, illisibles=(), date="") -> bool
    # C2. Markdown d'un document, plan 6.1 : front matter avec la clé moodlesync (D4), <!-- page n -->, section « Pages à vérifier »
    # (pages dont la qualité n'est pas « bon », pages sans texte détecté, pages illisibles ; texte natif = « bon »). chemin_md absolu, choisi
    # par l'appelant ; chemin_rel est le seul chemin écrit dans le fichier. Atomique (.tmp puis os.replace). Renvoie True si écrit, False si
    # un .md existant n'a pas la clé moodlesync dans son front matter (jamais réécrit, invariant 8). Une erreur d'écriture lève OSError.
def apercu(dest: str, cfg: dict, chemin: str = "", page: int = 1) -> dict          # forme 2.7 ; aucune écriture disque

# Un document
def controler_pdf(chemin: str) -> dict
    # {"pages", "protege", "signe", "lecture_seule", "numerique", "annotations", "liens", "signets", "dimensions": [[l, h, rotation]], "marque": dict | None}
    # Lève ErreurOcr "corrompu". "numerique" = aucune page à reconnaître et pas de marque MoodleSync.
    # C4 : "lecture_seule" = PDF chiffré, même à mot de passe utilisateur vide (le réécrire enlèverait la protection), ou fichier non modifiable pour le
    #   système (os.access). "signe" = champ de signature rempli (AcroForm, /FT /Sig, /V) ou certification /DocMDP. "protege" (mot de passe non vide)
    #   ne lève pas : le dict revient avec pages 0 et protege vrai. "annotations" = tous les /Annots, "liens" = ceux de sous-type /Link (compris dans
    #   "annotations"), "signets" = éléments de /Outlines. "dimensions" = MediaBox arrondie à 2 décimales et /Rotate hérité.
def extraire_document(dest: str, chemin_rel: str, cfg: dict, *, progres=None, arreter=None, attendre=None, refaire=False) -> dict
    # Entrée de cache (2.3). Écrit pages/, le .md, le cache. Ne modifie JAMAIS le PDF source.
    # progres(evt: dict) : evt = {"document", "page", "pages"} (après chaque page, reprise comprise) ; attendre() est appelé entre deux pages
    #   (pause, priorité de la synchronisation), pas avant la première page traitée.
    # Lève Annule (pages faites conservées), ErreurOcr(protege | corrompu | trop_gros | verrouille | moteur_absent) ; langue_manquante (C2) sort aussi.
    # C3 : refaire (ajout, par défaut faux) ignore l'entrée de cache du document, pas le fichier de reprise. Le moteur est détecté une fois par appel
    #   (écart 35 ; reglages_depuis garde sa forme, extraire_document passe par un corps privé qui reçoit le bloc déjà détecté).
    #   En mode remplacer (avec_boites), le fichier de reprise et ses boites sont conservés après l'extraction : fabriquer_pdf_cherchable
    #   les lit et ne le supprime qu'après un remplacement réussi (écart 60) ; refaire ne change pas cette règle, il ne vide pas la reprise.
    #   Document inchangé (entrée valide, .md présent à l'endroit voulu par les réglages) : l'entrée est renvoyée sans aucun appel au moteur.
    #   Page illisible : signalée dans le .md, comptée dans pages_vides, le document continue. Trop gros : plus de ocr_max_mo (300 Mo). Fichier absent : corrompu.
    #   PermissionError à la lecture de la source ou à l'écriture du .md : verrouille. Aucune entrée de cache n'est créée pour un document en échec.
    #   Déplacement : entrée trouvée par identité dont l'ancien fichier n'existe plus ; elle sert à garder verifie, le document est re-extrait à
    #   son nouveau chemin, l'ancienne entrée et son .md restent (orphelin, invariant 11). Une copie (ancien fichier présent) n'hérite de rien.
    #   PDF cherchable (bloc genere dans .moodlesync.json) : identité = genere.empreinte_source et taille_source ; forcer_ocr pour les pages de numeros_ocr
    #   du cache ; cache perdu : toutes les pages sont reconnues (invariant 3 ; lire_marque existe depuis C4 mais n'est pas
    #   reliée à extraire_document, la régénération depuis la couche de texte de l'invariant 10 n'est pas faite : écart 63).
def traiter_document(dest: str, chemin_rel: str, cfg: dict, **mêmes_options) -> dict
    # extraire_document puis, si cfg["ocr_pdf"] == "remplacer", fabriquer_pdf_cherchable.
    # {"entree": dict, "pdf": "aucun|remplace|refuse|echec", "message": str}. Un échec du PDF n'annule pas le texte.
    # C3 : seul cfg["ocr_pdf"] == "remplacer" (et un PDF) appelle fabriquer_pdf_cherchable (écrite par C4, branche testée depuis C4).
    #   ErreurOcr numerique | signe | protege | lecture_seule : "refuse" ; autre ErreurOcr ou exception : "echec" ; message = phrase de MESSAGES
    #   (ou ms.message_erreur) ; "remplace" : MESSAGES["pdf_genere"] si C4 l'a écrit. "aucun" : message vide.

# PDF cherchable
def identite(chemin: str) -> dict                       # {"taille": int, "empreinte": "sha256:<hex>"} du fichier entier (D2). PermissionError : verrouille, autre erreur : corrompu.
def lire_marque(chemin: str) -> dict | None             # C4. Définie dans `moodlesync/marque.py` (module feuille, Y1a) et réexportée ici : `ocr.lire_marque` reste l'entrée du contrat 2.2.
                                                        # Ne lève jamais. None : clé absente, JSON illisible ou de 1 Ko et plus, v différent de 1, bloc incomplet
                                                        # (v, url, t, taille_source, empreinte_source, pages tous présents et du bon type), fichier qui n'est pas un PDF.
def fabriquer_pdf_cherchable(dest: str, chemin_rel: str, cfg: dict, *, arreter=None) -> dict
    # Retourne le bloc "genere". Superposition seulement, couche TSV (D8). Ordre imposé : invariant 5.
    # Lève ErreurOcr(numerique | signe | protege | lecture_seule | non_suivi | modifie_main | verrouille | verification | corrompu | trop_gros | moteur_absent |
    # langue_manquante) ou ms.Annule. Décisions de C4 (journal, section 4, 2026-11-08), qui précisent ce que ce contrat laissait ouvert :
    # - Refus, sans rien écrire ni reconnaître, dans cet ordre : protege, signe, lecture_seule, numerique (critères : controler_pdf), puis non_suivi, puis modifie_main.
    #   Les codes numerique, signe et lecture_seule portent la phrase de refus_pdf (section 5).
    # - Entrée d'état : la première entrée de .moodlesync.json dont "chemin" désigne ce document (séparateur, NFC et casse du système ignorés, comme _genere).
    #   Sa clé, passée par cle_url, est l'url de la marque. Aucune entrée : non_suivi (message ajouté en section 5) : un fichier que MoodleSync n'a pas reçu de
    #   Moodle n'est jamais remplacé (invariant 16) et n'a ni url ni t à écrire dans la marque.
    # - Déjà fabriqué : l'entrée porte un bloc genere complet dont taille_fichier et empreinte_fichier égalent l'identité du fichier : le bloc est renvoyé tel quel,
    #   rien n'est reconnu ni écrit. Fichier qui porte notre marque ou un genere sans être ce PDF cherchable : modifie_main, rien n'est écrit (invariants 8 et 10 :
    #   jamais superposé deux fois). Exception, la coupure entre les étapes 3 et 4 : genere écrit mais fichier encore égal à la source (taille_source, empreinte_source)
    #   et sans marque : on refait. Aucun argument confirme ici : la confirmation de modifie_main appartient à Y2.
    # - Pages à couche : celles que extraire_page reconnaît (source "ocr", mêmes règles que C2), avec avec_boites. Les pages déjà faites sont
    #   reprises du fichier de reprise, boites comprises : une page à reconnaître n'est reconnue qu'une fois en mode remplacer (écart 60) ; seules
    #   les pages absentes de la reprise sont reconnues ici. Une page illisible n'a pas de couche. Aucune page à couche (aucun mot encodable) : abandon,
    #   ErreurOcr "verification". La reprise est supprimée après un remplacement réussi seulement.
    # - Couche (D8) : un seul flux par page, "BT 3 Tr", un Tj par mot du TSV niveau 5, police Helvetica WinAnsi (/MoodleSyncF), caractères hors cp1252 omis (un mot vide est écarté),
    #   octets ASCII (octal hors 32 à 126), flux compressé (Flate, niveau 9). Taille de police = hauteur de la boîte du mot, échelle horizontale Tz = largeur / (0,5 em par
    #   caractère), ligne de base à 80 % de la hauteur : approximations, alignement non vérifié visuellement. Position selon la CropBox et /Rotate de la page, texte tourné
    #   avec la page. /Contents devient [q, objets d'origine par leur objet indirect (raw_get), "Q q <couche> Q"] ; /Resources de la page est copié avec la police ajoutée,
    #   une ressource partagée avec une autre page n'est jamais modifiée. Marque ajoutée à /Info par add_metadata.
    # - Fichier temporaire : <nom du fichier avec extension>.ocr.part (ex. scan.pdf.ocr.part), même dossier, écrasé s'il existe, supprimé à la sortie quoi qu'il arrive.
    #   Ce nom reste celui d'un PDF pour le rendu : _est_pdf l'accepte, sinon la vérification ne pourrait jamais rendre le fichier temporaire (écart 71).
    #   La suppression des .ocr.part orphelins au lancement (invariant 5) n'est pas écrite par C4 (écart 62).
    # - Vérification (invariant 4), dans cet ordre, un écart suffit : le fichier se rouvre ; mêmes pages, dimensions et rotations, comptes d'annotations, de liens et de signets ;
    #   marque lisible et égale à celle écrite ; volume des flux de couche compressés au plus 10 Ko par page à couche (D10) ; texte extractible, au moins 90 % des caractères
    #   alphanumériques de la couche, sur chaque page à couche ; rendu de la première, de la page du milieu et de la dernière page à couche (rendre_page(..., preparer=False),
    #   150 DPI, avant et après) identique pixel pour pixel (D9, écart maximal 0). La comparaison porte sur les images brutes, sans autocontraste : l'autocontraste ne sert
    #   qu'à expliquer un écart dans erreurs.txt, jamais à décider de l'égalité (écart 69). Un rendu impossible (pypdfium2 absent) vaut un écart. Marque de 1 Ko ou plus : abandon "verification".
    # - Remplacement : os.replace ; PermissionError : un nouvel essai après PAUSE_VERROU (2 s), puis verrouille ; dans les deux cas genere est retiré de l'état (étape 5). Une autre
    #   OSError retire genere, supprime le .part et sort telle quelle.
    # - Un fichier de plus de ocr_max_mo : trop_gros. Aucun appel réseau (invariant 6).
def restaurer(dest: str, cfg: dict, chemin_rel: str, *, confirme=False, arreter=None) -> dict
    # {"ok": True, "pages": int} ou {"confirmer": str}. Lève ErreurOcr(hors_ligne | modifie_main | verification) ou ms.SessionExpiree.
def reconcilier_etat(dest: str) -> int      # retire "genere" quand le fichier a encore l'identité source (remplacement interrompu). Renvoie le nombre corrigé.

# Cache et file (aucun verrou ici : le verrou est dans ApiTextes)
def charger_cache(dest) -> dict;  def sauver_cache(dest, cache) -> None
    # {"version": 1, "documents": {...}}. Absent, illisible ou de version supérieure : cache vide. Version supérieure (contrat 1) : la signature
    # ne porte pas de drapeau, c'est l'écriture qui relit le fichier présent et ne l'écrase jamais (même règle pour file.json et pages/).
def trouver_entree(cache: dict, chemin_rel: str, empreinte: str, taille: int) -> tuple[str, dict] | None   # par chemin, puis par identité
def entree_valide(entree: dict, empreinte: str, reglages: dict) -> bool   # empreinte + langues, dpi, psm, moteur (2.3) ; un etat "erreur" n'est jamais valide
def charger_file(dest) -> dict;   def sauver_file(dest, file) -> None
def constituer_file(dest, cfg, portee: str, refaire=False) -> dict       # applique 2.5 ; écrit file.json (etat "inactive") ; renvoie la file écrite (forme 2.5, C3)
    # Le bloc "file" de 2.7 (document, page, documents_faits...) en est dérivé par ApiTextes (A1).
def mettre_en_file_apres_sync(dest, cfg, compte_rendu: dict) -> int      # lit compte_rendu["a_preparer"] ; renvoie le nombre de tâches mises en attente
    # (nouvelles, ou terminées dont le fichier est republié) ; ne change pas l'etat de la file ; un chemin déjà en attente n'est pas ajouté.
def archiver_texte(dest, chemin_rel: str, t_ancien: int) -> str | None   # .md généré renommé en « ancienne version » ; None s'il est édité à la main
    # (C3) .md pris dans la clé sortie du cache (pas de cfg en argument) ; renvoie le nouveau chemin absolu ; None sans entrée, sans fichier ou si
    # _regenerable est faux (front matter fermé portant la clé moodlesync, écart 45). Une erreur du système de fichiers lève OSError.
```

Rendu des sorties (Markdown de cours, index, qualité, JSONL, contexte copiable), fixé par C5 (tâche C5, journal `fin` de C5) :

```python
def ecrire_cours_md(dest: str, portee: str, *, cfg: dict | None = None) -> list[str]
    # Un fichier par cours de la portée (2.5) : `<dest>/<dossier>/<Cours>/<Cours> - texte des documents.md` (2.6).
    # Forme du plan 6.2 : ms.MARQUE en première ligne (D4), puis `# <Cours> : texte des documents`, la phrase d'introduction
    # du plan 6.2, `## <Section>`, `### <nom du document avec extension>`, `[source : <section>/<nom>, N pages]` (chemin
    # relatif, jamais absolu), puis `[p. n]` avant le texte de chaque page. Écriture atomique, UTF-8 sans BOM, LF. Les
    # documents sont lus dans le cache, triés par cours, section et nom (ms.cle_nom). Un cours sans .md lisible n'a pas de
    # fichier, et une section dont tous les .md manquent n'est pas écrite. Aucun .md de document n'est réécrit (invariant
    # 8) ; C5 n'écrit que sous le dossier de sortie (invariant 1). `cfg` résout `cours:<cid>` (voir la portée plus bas).
    # Renvoie les chemins écrits ; une écriture qui échoue est signalée et arrête le travail, les fichiers déjà écrits
    # restent dans la liste (invariant 9, écart 83).
def ecrire_index(dest: str) -> str
    # `<dest>/<dossier>/index.md` (2.6) : ms.MARQUE, `# Textes des cours`, une ligne par cours
    # (`- <Cours> : N documents, M pages, X Mo`), puis `## Documents à vérifier` (documents dont etat n'est pas `ok` et qui
    # ne sont pas `verifie`, confiance à la française, pages douteuses), puis `## Documents orphelins` s'il y en a (invariant 11).
    # Le volume est celui des .md du cours mesuré sur le disque (fichier de cours compris), choix de C5 : le plan 6.3 ne dit
    # pas ce qu'il mesure. Le nombre de pages douteuses est celui des lignes de la section « Pages à vérifier » du .md, une
    # page par ligne (écart 78) ; sans section, C5 retombe sur pages moins pages_texte. Renvoie le chemin écrit, ou "" si
    # l'écriture a échoué (invariant 9).
def ecrire_qualite(dest: str) -> str
    # `<dest>/<dossier>/Qualité des textes.md` (2.6, T["qualite_textes"]) : ms.MARQUE, documents à vérifier (même règle que
    # l'index), page par page quand c'est utile, confiance par `_virgule`, lien relatif vers le .md du document. La confiance
    # affichée pour une page est celle que C2 écrit pour elle dans « Pages à vérifier », page par page, jamais la moyenne du
    # document répétée (écart 78) ; un document mixte énumère donc ses pages douteuses, y compris ses pages natives si elles
    # en ont. Une page difficile n'est jamais omise (plan 4.4) ; les orphelins y sont listés aussi. Renvoie le chemin écrit,
    # ou "" en échec.
def assembler_contexte(dest: str, portee: str, *, cfg: dict | None = None) -> str
    # Texte prêt à coller (plan 6.2, T27) : même forme que le fichier de cours, sans ms.MARQUE, cours séparés par une ligne
    # vide. Marqueurs `[p. n]` et phrase d'introduction. Aucune écriture disque (T24, T27). Le compte de caractères de 2.7
    # est calculé par l'appelant (A2) sur la chaîne renvoyée. Chaîne vide si rien ne correspond ou en cas d'échec.
def ecrire_jsonl(dest: str, portee: str, flux, *, cfg: dict | None = None) -> int
    # Une ligne JSON par page (plan 6.4) dans `flux` (texte ou binaire, fourni par l'appelant ; aucun fichier écrit ici) :
    # clés `cours`, `section`, `fichier`, `page`, `source`, `confiance`, `texte`, une seule ligne par page, UTF-8 sans BOM.
    # `source` et `confiance` décrivent la page, pas le document (écart 80) : `source` vaut `ocr` ou `texte` selon
    # `numeros_ocr` du cache (une page native d'un document mixte sort en `texte`), `vide` pour un document sans texte ;
    # `confiance` ne porte que la valeur écrite par C2 pour cette page dans « Pages à vérifier », sinon `null` (le cache ne
    # garde que la moyenne du document). Créé seulement à la demande. Renvoie le nombre exact de lignes écrites : une
    # écriture qui échoue est signalée et arrête le travail, le compte dit ce qui est déjà dans le flux (écart 83).
# Portée : `tout`, `sans_texte`, `cours:<cid>`, `document:<chemin>` (2.5) ; `cours:<cid>` se résout par
#   cfg["cours"][cid]["dossier"], comme `constituer_file` et la portée de 2.5 (écart 74) : sans cette table, la portée est
#   vide, le nom par défaut venant de Moodle. Le dossier obtenu est comparé sans casse ni accents (ms.cle_nom). C5 ne lit
#   que des documents déjà extraits : `sans_texte` ne filtre rien.
# Orphelins (invariant 11, contrat 6 T6) : fonction privée `_orphelins(dest, cache)`, utilisée par `ecrire_index` et
#   `ecrire_qualite`. Deux cas : entrée du cache dont le document a disparu du disque, .md de document présent sans entrée
#   de cache. Une `sortie` absolue (`ocr_sortie_hors_coffre`) est suivie comme une relative, et les agrégats sont écrits
#   dans le dossier des .md de document, hors du coffre (écart 79). Jamais supprimés ; les actions Conserver et Retirer
#   restent à A1.
# Invariant 9 : aucune de ces fonctions ne laisse sortir d'exception technique. Le détail part dans erreurs.txt
#   (ms.message_erreur) et l'appelant reçoit ce qui a été écrit : les chemins déjà écrits, le nombre exact de lignes déjà
#   dans le flux, et sinon la valeur vide (chaîne, liste, zéro). ms.Annule passe telle quelle.
# La section « Pages à vérifier » d'un .md de document n'entre jamais dans un agrégat, où qu'elle se trouve dans le fichier ;
#   elle est lue à part pour la qualité, l'index et le JSONL (écart 78).
# Toutes les pages d'un .md de document sont gardées, y compris une dernière page vide : C2 écrit un marqueur par page et
#   aucun marqueur terminal (écart 77).
```

La signature d'`ecrire_document_md` est fixée plus haut (C2).

### 3.2 `moodlesync/api_textes.py`

```python
from .api_horaire import _proteger        # même décorateur que l'horaire (application.proteger ferait un import circulaire)
class ApiTextes:
    # Pas de __init__ : Api.__init__ appelle self._init_textes(). Tout attribut ou méthode sans _ est exposé à la page.
    def _init_textes(self) -> None        # _ocr_verrou (RLock : cache et file), _ocr_fichiers (Lock : une page ou un remplacement),
                                          # _ocr_fil (Thread daemon | None), _ocr_arret, _ocr_pause, _sync_veut (Event)
    def _ocr_exclusif(self)               # gestionnaire de contexte pour sync_lancer et ocr_pdf_restaurer ; invariant 7
    def _ocr_apres_sync(self, compte_rendu: dict) -> dict      # {"a_preparer": int} ; ajouté à sync_lancer()["resultat"]["ocr"]. Démarre l'extraction seule si ocr et ocr_apres_sync sont vrais, fenêtre ouverte, lot de 50 documents et 500 pages au plus (D7) ; sinon file en attente, la carte propose « Préparer ».
    def _ocr_fermer(self) -> None         # appelé à la fermeture : lève l'arrêt, n'attend pas le fil
    # Toutes décorées @_proteger("Texte des cours") ; toutes renvoient les formes 2.7
    def ocr_etat(self); def ocr_detecter(self); def ocr_choisir_exe(self)
    def ocr_installer(self)               # RÉSERVÉ : {"erreur": MESSAGES["installation_indisponible"]} jusqu'à la 2.6 (D6)
    def ocr_apercu(self, chemin="", page=1)
    def ocr_lancer(self, portee="sans_texte", refaire=False, confirme=False)
    def ocr_pause(self); def ocr_reprendre(self); def ocr_annuler(self)         # {"file": <bloc file>}
    def ocr_documents(self, filtre=None); def ocr_chercher(self, texte, limite=50)
    def ocr_copier(self, portee); def ocr_exporter(self, portee, format="zip")
    def ocr_ouvrir(self, chemin, page=None)          # .md ou dossier, ou {"source": True} pour le PDF ; refuse tout chemin hors dest et hors Textes
    def ocr_pdf_restaurer(self, chemin, confirme=False)
    def ocr_verifie(self, chemin, verifie=True)      # « Marquer comme vérifié » (à confirmer : absent du tableau 5.1 du plan)
    def ocr_orphelin(self, chemin, action)           # action ∈ "conserver", "retirer" (à confirmer : plan 4.5)
    def ocr_regler(self, cle, valeur)                # liste blanche : table ci-dessous ; renvoie ocr_etat()
```

`ocr_regler` : `ocr` bool `false` ; `ocr_exe`, `ocr_tessdata` str `""` (fichier ou dossier existant) ; `ocr_langues` str `"fra+eng"` (inclus dans les langues détectées) ; `ocr_dpi` int `300` (150 à 600) ; `ocr_psm` int `3` (1, 3, 4, 6) ; `ocr_dossier` str `"Textes"` (nom simple, sans `..`, différent de tout dossier de cours) ; `ocr_apres_sync` bool `true` ; `ocr_max_mo` int `300` (10 à 2000) ; `ocr_threads` int `2` (1 à 4) ; `ocr_batterie` str `"pause"` (`pause`, `continuer`) ; `ocr_sortie_hors_coffre` bool `false` ; `ocr_pdf` str `"aucun"` (`aucun`, `remplacer` ; `copie` refusé avec le message `mode_indisponible`, D3). Passer `ocr_pdf` à `remplacer` demande `confirme=True` après le message `consentement_remplacer`.

Progression (comme `syncProgres`) : `_js("textesProgres", {"etat": "en_cours|pause|pause_sync|terminee|annulee|erreur", "document": str, "page": int, "pages": int, "documents_faits": int, "documents_total": int, "restant_min": int|None, "message": str})`, émise au plus 4 fois par seconde. Journal : `_js("textesJournal", str)`, phrases de la section 5 seulement.

### 3.3 Modifications minimales de `moteur.py` et `seances.py`

- `DOSSIERS_OCR = (".moodlesync-ocr",)` et `dossiers_sortie_ocr(cfg=None) -> set` (`T["textes"]`, `"Textes"`, `"Texts"`, `ocr_dossier`, normalisés NFC et casse). **Une seule constante** porte la liste.
- `index_existant(dest, exclus=None)` : forme du retour inchangée. Les dossiers exclus sont ceux **placés directement dans `dest`** : un sous-dossier « Textes » d'une section n'est pas exclu.
- `deja_present(it, cible, par_nom, meme_cours=..., *, etat=None, dest="", par_taille=None)` : sans les trois nouveaux arguments, comportement actuel. Ordre : 1 chemin exact ; 2 `etat[cle_url(it["url"])]["chemin"]` ; 3 fichier du même cours dont `identite` égale `taille_fichier` et `empreinte_fichier` (la taille filtre via `par_taille`, l'empreinte ne se calcule que sur égalité de taille) ; 4 PDF du même cours dont `lire_marque` (importée de `moodlesync.marque`, module feuille, jamais de `ocr` : écart 6, Y1a) porte la même `url` (lecture seulement si 1 à 3 échouent, limitée aux PDF non référencés par l'état) ; 5 même nom et taille annoncée par Moodle, **sauf** pour un fichier connu comme généré (état ou marque) ; 6 `None`, donc téléchargement.
  Décisions de Y1b (journal, section 4, 2026-11-08) :
  - **Empreinte entière** : `moteur.empreinte_entiere(chemin)` rend `"sha256:<hex>"` du fichier entier (même chaîne que `ocr._sha256`, vérifié par un test) ou `""` si la lecture échoue ; une lecture qui échoue ne fait jamais échouer la synchronisation, le doute se résout par téléchargement. `moteur.py` n'importe toujours que la bibliothèque standard et `marque`. `moteur.genere_valide(bloc)` applique la règle de 2.1 (bloc complet, `type` `pdf_cherchable`, `version` 1) comme `ocr._genere_complet`.
  - **Nouveaux arguments** : sans `etat`, `deja_present` se comporte comme avant (aucune lecture de marque, aucun calcul d'empreinte). L'étape 4 ne s'applique qu'à un fichier Moodle de nom `*.pdf` ; elle lit au plus une fois chaque PDF du même cours (mémo par chemin, taille et date de modification).
  - **PDF retrouvé par sa seule marque** : l'entrée d'état recréée reconstruit `genere` : `taille_source`, `empreinte_source`, `pages` viennent de la marque, `taille_fichier` et `empreinte_fichier` sont mesurées sur le fichier au moment de la reconstruction, `date` est celle de la reconstruction, `version` vaut 1, `t` vaut celui de la marque (le `t` de la version traitée, pas celui que Moodle annonce). Conséquence assumée : l'identité mesurée ce jour devient la référence, la protection `modifie_main` ne peut pas distinguer un PDF modifié à la main avant la perte de l'état. Si l'empreinte du fichier ne se lit pas, l'entrée ne reçoit que `t` et `chemin`, et le fichier reste « connu comme généré » par sa marque (lue à l'étape 5).
  - **Compteurs** : un PDF cherchable conservé compte dans `generes` et **pas** dans `doublons` (`doublons` reste « déjà présents, ignorés » et ne contient que des fichiers natifs). Total d'un passage : `neufs + maj + doublons + generes + erreurs` pour les fichiers examinés.
- `telecharger(items, cfg, dire, progres, arreter)` : signature inchangée. Si l'entrée porte `genere` et que Moodle annonce un `t` plus récent : voir invariant 12. Le compte rendu gagne `"a_preparer": [chemin_rel]`, `"generes": int` (PDF cherchables conservés) et `"republies_generes": [{"chemin", "t_ancien"}]`. Un PDF cherchable conservé est journalisé « PDF cherchable (généré par MoodleSync) », jamais « Déjà présent ». `liste_maj` accepte `ancien = None` pour ce cas (consommateurs à vérifier : `ecrire_note`, `nouveautes_par_cours`).
- `seances.pdf_range(fichier, etat, dest)` : si l'entrée porte `genere`, `t` égal, `getsize == genere.taille_fichier` et `genere.taille_source == fichier["taille"]` (quand elle est connue) : renvoie le chemin. Sinon, comportement actuel.
- `moteur.LANGUES` gagne `textes`, `qualite_textes`, `texte_complet` (fr et en).

### 3.4 Interface

| Élément | Contrat |
|---|---|
| Onglet | `#o-textes` (`data-onglet="textes"`, texte « Mes textes »), panneau `#v-textes` (`role=tabpanel`, `aria-labelledby="o-textes"`), pastille `#tx-badge`. `choisirOnglet` et la navigation au clavier de `app.js` (codées en dur pour deux onglets) passent à trois. |
| Identifiants | Préfixe `tx-` (`t-` est déjà pris). Mes textes : `#tx-entete`, `#tx-recherche`, `#tx-resultats`, `#tx-liste`, `#tx-vide`, `#tx-copier-cours`, `#tx-exporter`, `#tx-ouvrir-dossier`, `#tx-qualite`. Mes cours : carte `#tx-carte` (visible si `a_preparer > 0`), `#tx-preparer`, `#tx-plus-tard`, liens `#tx-quoi`, `#tx-reglages`. |
| Dialogues (`<dialog class="dialogue">`) | `#d-tx-preparer` (consentement et durée), `#d-tx-quoi` (classe `large`), `#d-tx-qualite`. Confirmations simples : `confirmer()` et `informer()` de `app.js`. |
| Réglages | Groupe « Texte des cours (OCR) » dans `remplirTiroir`. Seul endroit où « OCR » et « Tesseract » sont écrits. |
| Page vers Python | `api().ocr_*`. Python vers la page : `window.textesProgres(p)` et `window.textesJournal(t)`, définis dans `textes.js`, chargé avant `app.js`. |
| Variables globales | `TX` (dernier `ocr_etat`), `txPret` (bool, premier chargement fini), `txOccupe` (bool). `occupations` reçoit `"textes"` pendant le travail. |
| Badges | `.badge-qualite` plus `.bon`, `.a-verifier`, `.difficile`, `.cherchable`, couleurs des variables `--bon`, `--alerte`, `--critique`, **toujours accompagnées du mot** (« Bon », « À vérifier », « Difficile », « PDF cherchable »). |
| Vérification | `window.etatVerification()` gagne `textes: {documents, pages, a_verifier, file, erreur}` (`file` = `file.etat`, `erreur` = texte des bandeaux de l'onglet). `pret` exige `txPret && !txOccupe`. `onglets` liste trois noms. |

## 4. Invariants et règles de sûreté

1. **Aucun original conservé.** Ni `Originaux/`, ni `.orig`, ni `.bak`, ni PDF généré renommé « ancienne version ». Le volume des PDF n'augmente que de la couche de texte (borne : 10 Ko par page reconnue, flux compressé, sans plafond absolu, D10).
2. **Superposition seulement, seulement en mode `remplacer`.** Le contenu de la page est conservé tel quel, une couche de texte invisible est ajoutée aux pages de `numeros_ocr`. Les pages natives restent identiques. Reconstruire une page est interdit.
3. **Refus.** PDF numérique (aucune page à reconnaître), signé, chiffré, en lecture seule : rien n'est modifié, message explicite. Un PDF portant **notre** marque n'est pas « numérique » : ses pages de `numeros_ocr` restent à reconnaître, la couche invisible n'est jamais lue comme du texte natif.
4. **Vérification avant remplacement.** Même nombre de pages, mêmes dimensions et rotations page par page, texte extractible sur les pages reconnues, mêmes comptes d'annotations, de liens et de signets, fichier réouvrable, rendu de 3 pages identique à l'original (écart maximal 0 par pixel, sur les images brutes sans autocontraste, rendu par le même pdfium à 150 DPI, première, milieu et dernière page reconnues, D9, écart 69) ; volume de la couche dans la borne de l'invariant 1. Un seul écart : abandon, original en place, `genere` jamais écrit.
5. **Écriture atomique, ordre imposé** : (1) identité source ; (2) fichier `<nom>.ocr.part` dans le même dossier, vérifié, identité du fichier ; (3) `sauver_etat` avec `genere` ; (4) `os.replace` ; (5) si (4) échoue, retirer `genere` et sauver. Le fichier verrouillé (Acrobat, OneDrive) reçoit un nouvel essai après 2 s, puis le message `verrouille`. Les `.ocr.part` orphelins sont supprimés au lancement. `reconcilier_etat` répare une coupure entre (3) et (4).
6. **Aucun réseau pendant l'extraction.** `executer`, `rendre_page`, `extraire_*`, `fabriquer_pdf_cherchable` n'importent ni n'appellent `urllib` ni `socket`. Seuls réseaux autorisés : `restaurer` (action explicite de l'utilisateur) et `installer_paquet` (HTTPS, SHA-256 vérifié).
7. **Sérialisation.** Une unité de travail (une page, ou un remplacement) tient `_ocr_fichiers`. `sync_lancer` pose `_sync_veut`, attend au plus une unité, tient `_ocr_fichiers` pendant `collecte` et `telecharger`, puis relâche : **la synchronisation a la priorité** (D1). L'extraction vérifie `_sync_veut` entre deux pages et passe en `pause_sync`. Jamais d'extraction en mode `--auto` sans fenêtre.
8. **Éditions manuelles.** Un `.md` sans clé `moodlesync` dans son front matter (D4) n'est jamais réécrit. Un PDF cherchable dont l'identité diffère de `genere.taille_fichier` et `empreinte_fichier` n'est ni remplacé ni restauré sans `confirme=True` et le message `modifie_main`.
9. **Aucune trace technique dans la fenêtre.** Ni traceback, ni code de retour, ni chemin de DLL. Le détail va dans `erreurs.txt` (`ms.message_erreur`). Un document en erreur n'arrête ni la file ni la synchronisation.
10. **Perte d'état.** `.moodlesync.json` perdu : un PDF cherchable déplacé est retrouvé par sa marque (étape 4). Sans marque ni état, le doute se résout par téléchargement : un doublon temporaire vaut mieux qu'un fichier manquant. `.moodlesync-ocr/` perdu : textes refaits au prochain passage ; un PDF portant la marque n'est pas superposé deux fois ; son `.md` est régénéré depuis sa couche de texte avec `etat: "a_verifier"` (à confirmer).
11. **Fichier déplacé ou renommé.** Retrouvé par identité (2.1, 2.3), jamais par la taille Moodle. Le cache et la reprise suivent. L'ancien `.md` devient « orphelin », listé, jamais supprimé sans accord.
12. **Republication.** Contenu identique à `genere.taille_source` et `empreinte_source` : seul `t` change, le `.part` est supprimé, aucun traitement. Contenu différent : le nouveau PDF remplace le PDF cherchable **au même chemin**, `genere` est retiré, le document est remis en file, `archiver_texte` conserve l'ancien `.md`, aucun PDF « ancienne version » n'est créé.
13. **Restauration.** Retélécharge dans un `.part`, vérifie `taille_source` et `empreinte_source`, remplace atomiquement, retire `genere`. Hors ligne, jeton expiré ou cours fermé : message dédié, PDF cherchable intact. Moodle renvoie une version différente : aucun remplacement, message `restauration_differente`.
14. **`deja_present`.** Jamais de comparaison entre la taille d'un PDF cherchable et celle de Moodle. En cas de doute, retélécharger.
15. **Exclusions.** `Textes/` et `.moodlesync-ocr/` ne participent ni à `index_existant`, ni à `repartiteur`, ni à la file.
16. **Défauts sûrs.** `ocr = false`, `ocr_pdf = "aucun"`. Aucun traitement sans consentement. `remplacer` exige un consentement séparé. `CONTRIBUTING.md` (« ne jamais écraser un fichier de l'utilisateur ») doit nommer cette exception en P3.

## 5. Messages et vocabulaire

Tous dans `ocr.MESSAGES[code]`, en français, tutoiement, sans tiret long. Ils sont la seule source des phrases visibles.

| Code | Message |
|---|---|
| `moteur_absent` | Le moteur d'extraction n'est pas encore installé. Indique où il se trouve dans les réglages. |
| `langue_manquante` | Il manque une langue de reconnaissance. MoodleSync utilise celle qui est disponible : la qualité peut baisser. |
| `protege` | Ce document est protégé par un mot de passe. MoodleSync ne le contourne pas : son texte n'a pas été extrait. |
| `verrouille` | Ce fichier est ouvert dans un autre programme. Ferme-le et réessaie : rien n'a été modifié. |
| `illisible` | La page {n} n'a pas pu être lue. Elle est signalée dans le document, les autres pages sont intactes. |
| `hors_ligne` | Impossible de retélécharger l'original sans connexion. Ton PDF cherchable reste en place, avec ses pages d'origine. Réessaie une fois en ligne. |
| `pdf_genere` | « {nom} » est maintenant cherchable avec Ctrl+F. Ses pages d'origine sont conservées, l'original exact se retélécharge depuis Moodle. |
| `a_verifier` | {n} documents sont à vérifier : la reconnaissance y est moins sûre. Compare avec le document source. |
| `corrompu` | Ce PDF est abîmé et n'a pas pu être ouvert. Les autres documents continuent. |
| `refus_pdf` | Ce PDF est déjà lisible, signé ou en lecture seule : MoodleSync ne le modifie pas. Son texte reste disponible dans Mes textes. |
| `verification` | Le PDF cherchable n'a pas passé les contrôles. Ton fichier d'origine n'a pas été touché. |
| `modifie_main` | Ce fichier a été modifié depuis sa création par MoodleSync. Continuer le remplacera. |
| `restauration_differente` | Moodle propose une version différente de celle d'origine. Rien n'a été remplacé : lance une synchronisation. |
| `consentement_remplacer` | Le PDF sera remplacé sur place par une version cherchable qui garde ses pages d'origine. Aucune copie de l'original n'est conservée, tu pourras le retélécharger depuis Moodle. |
| `mode_indisponible` | Ce mode n'existe pas. Choisis « Aucun » ou « Remplacer par une version cherchable ». |
| `installation_indisponible` | L'installation automatique n'est pas encore disponible. Indique l'emplacement du moteur dans les réglages. |
| `trop_gros` | Ce document dépasse la taille maximale prévue ({mo} Mo). Augmente la limite dans les réglages pour en extraire le texte. |
| `non_suivi` | Ce PDF ne vient pas d'un téléchargement de MoodleSync : il n'est pas remplacé. Son texte reste disponible dans Mes textes. |

Les codes d'`ErreurOcr` `numerique`, `signe` et `lecture_seule` (invariant 3) portent tous la phrase de `refus_pdf`. `refus_pdf`, `verification`, `modifie_main` et `pdf_genere` sont dans `ocr.MESSAGES` depuis C4, identiques à ce tableau ; `non_suivi` est ajouté par C4.

**À éviter dans l'interface principale** (carte, onglet, dialogues, toasts, journal) : OCR, Tesseract, tessdata, DPI, segmentation, PSM, TSV. Dire « extraire le texte des scans », « le moteur d'extraction », « qualité de rendu ». Ces mots restent dans le groupe de réglages, `erreurs.txt` et la documentation. « Échec » ne s'emploie jamais pour un document lisible mais imparfait : « à vérifier ».

## 6. Contrat de tests

Niveaux : **U** unitaire (doublures de `executer` et `rendre_page`), **I** intégration avec fichiers temporaires et téléchargement simulé (`urlopen` remplacé, comme `tests/test_moteur.py`). Les tests avec le vrai moteur sont ignorés s'il est absent. Commande : `python -m unittest discover -s tests -t . -v`. Fichiers : `tests/test_ocr.py` (moteur, synchro, restauration), `tests/test_api_textes.py` (API ; à confirmer).

| # | Test | Niv. | Comportement attendu | Fichiers |
|---|---|---|---|---|
| T1 | `test_tsv_accents` | U | TSV avec « é è ç œ » en UTF-8, chemins à espaces et accents ; mots de niveau 5 seulement ; ordre bloc, paragraphe, ligne, abscisse ; confiance négative ignorée | `ocr.py` |
| T2 | `test_natif_contre_ocr` | U | Page à 80 caractères alphanumériques : `texte`, **zéro** appel à `executer` | `ocr.py` |
| T3 | `test_page_mixte` | U | Sans texte avec image : `ocr` ; sans texte ni image : `vide`, non signalée en échec | `ocr.py` |
| T4 | `test_confiance_niveaux` | U | 0,85 bon ; 0,849 à vérifier ; 0,70 à vérifier ; 0,699 difficile ; `null` vide | `ocr.py` |
| T5 | `test_reprise_apres_arret` | I | Annulation après la page 3 de 6 ; relance : pages 1 à 3 non refaites (appels comptés) ; `pages/` cohérent | `ocr.py` |
| T6 | `test_cache_et_deplacement` | U | Document inchangé : zéro appel ; réglage changé : seul ce document est refait ; fichier déplacé retrouvé par identité (la liste des orphelins relève de C5 et n'est pas testée par T6) | `ocr.py` |
| T7 | `test_sortie_editee_conservee` | U | `.md` sans la clé `moodlesync` non réécrit ; avec la clé, régénéré | `ocr.py` |
| T8 | `test_republication_identique` | I | `.part` de même identité source : seul `t` change, `genere` conservé, rien en file | `moteur.py`, `ocr.py` |
| T9 | `test_republication_differente` | I | Nouveau PDF au même chemin, `genere` retiré, 1 tâche en file, aucun PDF « ancienne version », ancien `.md` conservé | `moteur.py`, `ocr.py` |
| T10 | `test_deja_present_sans_original` | I | Après remplacement : synchro sans appel à `urlopen`, 0 nouveau, libellé « PDF cherchable » | `moteur.py` |
| T11 | `test_index_existant_textes` | U | `Textes/` et `.moodlesync-ocr/` visibles mais exclus ; une section « Textes » d'un cours ne l'est pas | `moteur.py` |
| T12 | `test_pdf_cherchable_deplace_renomme` | I | Retrouvé par `taille_fichier` et `empreinte_fichier`, pas de doublon, pas de téléchargement | `moteur.py` |
| T13 | `test_perte_etat_marque` | I | `.moodlesync.json` supprimé : PDF déplacé retrouvé par `/MoodleSyncGenere` ; sans marque : retéléchargé | `moteur.py`, `ocr.py` |
| T14 | `test_pdf_range_cherchable` | U | Page count lu sur le PDF local, réseau interdit ; repli si taille différente | `seances.py` |
| T15 | `test_restauration` | I | Hors ligne (`URLError`) : `hors_ligne`, PDF inchangé octet pour octet. En ligne : taille et empreinte sources vérifiées, remplacement, `genere` retiré, aucun `Originaux/` | `ocr.py` |
| T16 | `test_restauration_fichier_modifie` | U | Identité différente : `confirmer` sans écrasement ; avec `confirme=True` seulement | `ocr.py` |
| T17 | `test_pdf_protege_corrompu` | U | `protege` et `corrompu` lèvent `ErreurOcr` ; la file continue sur le document suivant | `ocr.py` |
| T18 | `test_pdf_verrouille` | I | `os.replace` lève `PermissionError` : un nouvel essai après 2 s (doublure du délai), puis `verrouille` ; original intact, aucun `.part`, `genere` écrit avant puis retiré de l'état | `ocr.py` |
| T19 | `test_refus_numerique_signe_lecture_seule` | U | `fabriquer_pdf_cherchable` refuse chaque cas (numerique, signe, lecture_seule chiffré ou non modifiable, protege) sans écrire ni reconnaître ; un PDF à notre marque n'est pas refusé comme numérique : bloc `genere` renvoyé s'il est conforme, `modifie_main` sinon | `ocr.py` |
| T20 | `test_superposition_conserve_objets` | I | Pages, dimensions et rotations, annotations, liens, signets identiques, pages natives intactes, `/Contents` par objets indirects ; un signet, une annotation, un lien ou une page perdus : abandon, original intact | `ocr.py` |
| T21 | `test_remplacement_atomique_volume` | I | Échec avant `os.replace` : original intact, aucun `.part`. Réussite : aucun second PDF, volume borné (10 Ko par page à couche), `genere` dans l'état | `ocr.py` |
| T22 | `test_aucun_reseau_extraction` | I | `urlopen` et `socket.create_connection` levant une erreur : extraction complète réussie | `ocr.py` |
| T23 | `test_serialisation_extraction_sync` | I | `sync_lancer` pendant une extraction : attente d'une unité, jamais deux travaux simultanés, reprise ensuite | `application.py`, `api_textes.py` |
| T24 | `test_apercu_sans_ecriture` | I | Arborescence de `dest` identique avant et après, `file.json` inchangé | `ocr.py` |
| T25 | `test_detection_hors_path` | U | Registre simulé, chemin hors PATH, `TESSDATA_PREFIX` ; langue manquante et repli | `ocr.py` |
| T26 | `test_api_erreurs_lisibles` | U | Chaque `ocr_*` en erreur renvoie `{"erreur": str}` sans « Traceback », sans chemin de bibliothèque | `api_textes.py` |
| T27 | `test_contexte_copiable` | U | `[p. n]`, phrase d'introduction, aucune écriture disque ; le compte de caractères est calculé par l'appelant (A2) sur la chaîne renvoyée, hors de C5 (3.1, revue de C5) | `ocr.py` |
| T28 | `test_pas_de_tiret_long` | U | Aucun tiret long dans `ocr.py`, `api_textes.py`, `textes.js`, `MESSAGES`, ce contrat | `tests/` |
| T29 | `test_moteur_reel` | I | Image Pillow, vrai moteur, quelques mots ; ignoré sans moteur | `ocr.py` |
| T30 | `test_verification_interface` | I | `MOODLESYNC_VERIF` : `etatVerification().textes` présent, trois onglets, `pret` vrai | `app.js`, CI |
| T31 | `test_reglages_validation` | U | Bornes de 3.2 ; `copie` refusé (`mode_indisponible`) ; `remplacer` sans `confirme` : `confirmer` ; `..` refusé ; `ocr_installer` : `installation_indisponible` | `api_textes.py` |
| T32 | `test_mise_en_file_auto` | I | 50 documents et 500 pages au plus : démarrage seul ; au-delà : `confirmer` ; jamais en mode `--auto` | `api_textes.py`, `ocr.py` |

**Critères d'acceptation du plan (8.) vers tests** : 1 → T25, T30 ; 2 → T25, T30 ; 3 → T2 ; 4 → T1, T29 ; 5 → T6 ; 6 → T5 ; 7 → T27 ; 8 → T22 ; 9 → T17, T18, T23 ; 3.4 et 5.5 → T32 ; 10 → la suite entière ; 11 → T24, T30 ; 12 → T15, T19, T20, T21 ; 13 → T10, T12, T13, T14 ; 14 → T11 ; 15 → T8, T9 ; 16 → T21.

## 7. Décisions prises

Toutes ont suivi la recommandation proposée. Chacune levait une contradiction du plan.

| # | Sujet | Décision | Écart avec le plan à corriger |
|---|---|---|---|
| D1 | Pause entre extraction et synchronisation | La synchronisation prime. L'extraction cède entre deux pages ou après un remplacement, puis reprend. Invariant 7. | 3.4 dit l'inverse : à réécrire. |
| D2 | Empreintes d'identité | `sha256:` du fichier entier pour `genere`, la marque PDF et le cache. Calcul seulement sur les candidats de même taille (`deja_present`, étape 3). `moteur.empreinte` (SHA-1 du préfixe) reste utilisé par l'index et la déduplication existants, sans changement. | 4.3 et 5.10 montrent `sha1:` : à remplacer par `sha256:`. |
| D3 | Valeurs de `ocr_pdf` | `aucun` et `remplacer` seulement. `copie` refusé (`mode_indisponible`). À rouvrir après la 2.5 si le besoin se confirme. | 4.3, 4.5, 5.6 et 9 parlent de `copie` et de « trois modes » : à retirer. |
| D4 | Marque des `.md` de document | Clé `moodlesync` dans le front matter, front matter en tête. Notes de cours, index et qualité : `ms.MARQUE` en première ligne. | 5.9 (« en première ligne ») : à préciser. |
| D5 | Unité de la confiance | Stockée de 0 à 1, seuils 0,85 et 0,70, affichée « 0,89 ». Le TSV (0 à 100) est divisé par 100. | 4.4 : seuils à écrire 0,85 et 0,70. |
| D6 | Paquet portable | Hors de la 2.5. `ocr_installer` existe et répond `installation_indisponible`. Détection et choix manuel de `tesseract.exe` dans la 2.5. | 3.3 : parcours 2 à décrire sans installation pour la 2.5. |
| D7 | Mise en file après synchronisation | Automatique si `ocr` et `ocr_apres_sync` sont vrais, fenêtre ouverte, et lot de 50 documents et 500 pages au plus. Au-delà : confirmation avec durée. Jamais en mode `--auto`. | 5.5 : à relier aux seuils de 3.4. |
| D8 | Méthode de la couche de texte (S1) | **Couche TSV** : texte invisible (mode de rendu 3) écrit en flux de contenu brut depuis les coordonnées du TSV (niveau 5), police Helvetica en WinAnsi, ajouté à `/Contents` par l'objet indirect (`page.raw_get("/Contents")`, jamais l'objet résolu), flux compressé. Un caractère non encodable en cp1252 est omis de la couche, il reste dans le `.md`. Aucune bibliothèque nouvelle. `textonly_pdf` n'est pas utilisé. Le nom « technique 2 » du rapport de spike est abandonné : on dit « couche TSV ». | 4.3 numérote « technique 1 » la superposition et « technique 2 » la reconstruction : numérotation du plan inchangée, le contrat nomme les méthodes. |
| D9 | Tolérance du rendu (S1) | Écart maximal 0 par pixel entre le rendu avant et après (même pdfium, niveaux de gris, 150 DPI) sur 3 pages reconnues : première, milieu, dernière. Mesuré : 0 ; une réécriture fautive de `/Contents` donne 255. Mesure réelle de l'écart 61 (prompt 16, 8 novembre 2026) : pypdfium2 5.15.1, pdfium 159.0.8149.0, pypdf 6.21.4, quatre PDF (`pdf_minimal`), huit rendus à 150 DPI, écart maximal 0 sur les images brutes ; la comparaison se fait sans autocontraste (écart 69), sur des images de 1240 sur 1755 pixels pour une page de 595 sur 842 points. | Aucun. |
| D10 | Borne de volume (S1) | 10 Ko par page reconnue au plus pour la couche, flux compressé, sans plafond absolu ni pourcentage. Chiffres connus : 3,3 Ko par page (rapport), 8,8 Ko non compressé et 1,1 Ko en Flate sur des pages synthétiques de 1 000 caractères (S). C4 mesure une page réelle dense avant de figer et signale tout écart au journal. | Aucun. |
| D11 | Versions, aperçu, seuils (S1) | `pypdf` reste à 6.21.4 (épinglé), le code utilise `PdfWriter(clone_from=...)` puis modifie la page clonée, ce qui vaut aussi en 7.0.0. Aperçu : 900 px de large. Seuils de qualité 0,85 et 0,70 conservés, **non calibrés** (deux points mesurés). `pypdfium2` : import paresseux, `detecter` ne lève jamais, absence de wheel sur macOS 11 et 12 (wheel macOS 13 et plus seulement) traitée comme moteur absent. | Aucun. |

**Confirmés par C3** : noms `cache.json` et `file.json`, valeur `"vide"` de `extraction` (écart 50, décision de Maxence), `etat` dérivé des pages (écart 8), clés d'invalidation limitées à `langues`, `dpi`, `psm`, `moteur` (écart 7), message `trop_gros`, argument `refaire` d'`extraire_document` et clé facultative `refaire` des tâches.

**Confirmés par C4** : suffixe `<nom du fichier avec extension>.ocr.part`, code `non_suivi`, critères de `signe` et de `lecture_seule`, retour du bloc `genere` sans rien refaire pour un PDF déjà fabriqué (détail en 3.1).

**Restent à confirmer** (propositions de ce contrat, hors décisions ci-dessus) : clé `numeros_ocr`, clé `boites` de la reprise, `ocr_verifie` et `ocr_orphelin`, plafond de 2 000 000 caractères pour `ocr_copier`, dialogue natif de `ocr_exporter`, `tests/test_api_textes.py`, nom anglais de `T["qualite_textes"]`, régénération d'un `.md` depuis la couche de texte après perte du cache (invariant 10), comportement de `liste_maj` avec `ancien = None`.
