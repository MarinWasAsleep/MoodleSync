# Spike OCR : pypdfium2, Tesseract TSV et superposition

Tâche S1, 7 novembre 2026, propriétaire D. Machine Windows 10/11, Python 3.15.2.
Question unique : pypdfium2, Tesseract en sortie TSV et la superposition d'une couche de texte avec pypdf fonctionnent-ils, avec des temps acceptables, sur cette machine ? Réponse : go ou no-go, par volet.

## Versions (mesuré)

| Composant | Version |
|---|---|
| Python | 3.15.2 |
| pypdfium2 | 5.15.0 (wheel win_amd64) |
| Pillow | 13.0.0 |
| pypdf | 7.0.0 |
| Tesseract | 5.5.3.20260724 (Leptonica 1.87.0) |

Environnement virtuel jetable créé hors du dépôt (dossier temporaire du système), supprimé après usage. Aucune installation dans l'environnement du projet.

## Détection (mesuré)

- `tesseract.exe` est dans `C:\Program Files\Tesseract-OCR\`, hors PATH (confirmation : `where tesseract` ne trouve rien).
- `TESSDATA_PREFIX` vaut `C:\Users\marin\AppData\Local\tessdata`.
- `--list-langs` renvoie `eng`, `fra`, `osd`, lus dans ce dossier.
- Registre `HKLM\SOFTWARE\Tesseract-OCR` : `Path` et `InstallDir` pointent vers `C:\Program Files\Tesseract-OCR` (confirmé, pas supposé).
- **Constat important** : le dossier tessdata utilisateur contient seulement les trois `traineddata` (fra 14,2 Mo, eng 4,1 Mo, osd 10,5 Mo). Il ne contient **ni le sous-dossier `configs` ni `pdf.ttf`**. Ces deux éléments sont dans `C:\Program Files\Tesseract-OCR\tessdata`, qui contient aussi un `fra.traineddata` « fast » de 1,1 Mo, différent du modèle « best » de 14,2 Mo du dossier utilisateur.
- Conséquence : la config `tsv` (et `pdf`) n'est pas trouvée quand `--tessdata-dir` pointe vers le dossier utilisateur. Le TSV s'obtient avec `-c tessedit_create_tsv=1`, sans fichier de config. La sortie PDF (`textonly_pdf`) exige `configs/pdf` et `pdf.ttf`, donc le dossier programme.

## Tableau des mesures

| Volet | Mesure | Valeur | Statut |
|---|---|---|---|
| Rendu | temps par page, 300 DPI, niveaux de gris, autocontraste | 0,07 à 0,35 s (3 essais) | mesuré |
| Rendu | taille image A4 (3508 × 2481 px, ~8,7 Mpx) | PNG de 128 Ko (scan) à 1,2 Mo (page chargée) | mesuré |
| Reconnaissance | temps OCR par page (`fra+eng`, psm 3, oem 1) | 0,44 à 1,96 s | mesuré |
| Reconnaissance | rendu + OCR d'une page de scan | 0,51 s (objectif < 3 s : tenu) | mesuré |
| Reconnaissance | confiance (TSV / 100), mots négatifs ignorés | 0,917 (titre de scan) ; 0,489 (photo difficile) ; 0 négatif sur 3 pages | mesuré |
| Reconnaissance | accents | `é è ç œ` corrects dans le TSV et le texte extrait | mesuré |
| Reconnaissance | page mixte, texte natif via pypdf | page 0 : 143 caractères natifs ; page 1 : image seule (28) | mesuré |
| Console | `CREATE_NO_WINDOW` depuis `pythonw.exe` | tesseract s'exécute (rc 0), sortie capturée | mesuré |
| Console | absence visuelle de fenêtre noire | non observé (test manuel décrit plus bas) | non observé |
| Superposition | couche TSV, objets avant/après | pages 3→3, annotations 2→2, liens 1→1, signets 1→1 | mesuré |
| Superposition | `textonly_pdf`, objets avant/après | identique (3, 2, 1, 1) | mesuré |
| Superposition | texte extractible après | 131 à 132 caractères alphanumériques, accents présents | mesuré |
| Superposition | écart de rendu avant/après sur 3 pages | 0,0 (texte invisible, aucune différence de pixel) | mesuré |
| Superposition | taille du fichier avant / après | 323 933 → 325 370 (couche TSV, +0,4 %) ; → 328 070 (`textonly_pdf`, +1,3 %) | mesuré |
| Superposition | taille de la couche de texte seule | ~3,3 Ko par page | mesuré |
| Aperçu | PNG 900 px de large | 33 Ko, 0,009 s, 900 × 637 px | mesuré |
| macOS | tout | non testé | non testé |

## Décision par volet

- **Rendu : go.** pypdfium2 rend une page A4 à 300 DPI en 0,07 à 0,35 s, en niveaux de gris avec autocontraste, sans dépendance lourde.
- **Reconnaissance : go.** TSV lisible, accents corrects, confiance 0 à 1, une page en 0,44 à 1,96 s. Sous réserve d'utiliser `-c tessedit_create_tsv=1` (la config `tsv` manque dans le dossier tessdata utilisateur).
- **Console : go, à confirmer visuellement.** Le drapeau `CREATE_NO_WINDOW` (0x08000000) est appliqué et tesseract s'exécute sans erreur depuis un processus sans console (`pythonw.exe`). L'absence de fenêtre noire n'a pas pu être observée ici. Test manuel pour Maxence : lancer MoodleSync, déclencher une extraction d'une page, regarder si une fenêtre console clignote. Le même drapeau est déjà employé dans `moteur.py` (appel PowerShell).
- **Superposition : go.** Les deux méthodes (couche TSV et `textonly_pdf`) conservent pages, dimensions, rotation, annotations, liens et signets, ajoutent un texte extractible avec accents, et le fichier se rouvre. L'écart de rendu est nul (couche invisible).
- **macOS : non testé.** À vérifier plus tard : chemin de `tesseract` via Homebrew (`/opt/homebrew/bin/tesseract`), wheels `pypdfium2` pour Apple Silicon, comportement de `textonly_pdf` sur macOS.

**Décision globale : go**, avec la couche TSV (couche construite depuis le TSV) recommandée.

## Valeurs proposées pour ce que le contrat marque S1

- **Méthode de la couche de texte : couche TSV** (construire la couche invisible depuis les coordonnées du TSV, puis fusion avec pypdf). Raisons : elle fonctionne avec le dossier tessdata utilisateur (modèle fra « best » de 14,2 Mo), son alignement est exact par construction (les coordonnées du TSV sont celles de l'image rendue, rapport fixe 300/72), et elle n'exige ni `pdf.ttf` ni la config `pdf` absents du dossier utilisateur. La méthode `textonly_pdf` fonctionne mais exige l'image sauvée avec `dpi=(300, 300)` (sinon tesseract estime une résolution fausse, 1177 ici, et désaligne le texte) et le dossier tessdata du programme.
- **Tolérance du rendu (invariant 4) : 0, ou au plus 1/255 en écart moyen.** Mesuré à 0,0 sur 3 pages. Une tolérance serrée est possible ; garder une marge minimale pour les arrondis de fusion.
- **Borne de volume (invariant 1) : +2 % du fichier source, plafond +200 Ko par document.** Mesuré +0,4 % (couche TSV) à +1,3 % (`textonly_pdf`), couche de texte ~3,3 Ko par page. Une borne de +2 % laisse une marge confortable sans autoriser de doublon.
- **Taille de l'aperçu : 900 px de large, ~33 Ko, < 100 Ko.** Mesuré 33 Ko en 0,009 s.
- **Seuils de qualité : conserver 0,85 et 0,70.** Un bon scan donne 0,92, une photo difficile 0,49. Les seuils actuels classent correctement ces deux cas.

## Plan B (en cas de no-go, non déclenché)

- Si le rendu échouait sur une plateforme : secours API Windows ou Poppler embarqué (déjà prévu au plan, section 9).
- Si la superposition perdait un objet : passer la fabrication du PDF cherchable en mode `copie` seulement, ou renoncer au mode `remplacer` et garder le `.md` comme seule sortie.
- Si Tesseract ne pouvait pas produire de TSV : repli sur la sortie texte simple, sans confiance par mot.

## Limites

- macOS non testé, aucune affirmation sur son fonctionnement.
- L'absence de fenêtre console n'a pas été observée visuellement, seulement le drapeau appliqué et l'exécution réussie.
- Les mesures portent sur 3 documents réels (un numérique, un scanné, un mixte) et quelques pages ; les temps sont indicatifs, pas un banc complet.
- pypdf 7.0 a changé l'API : `merge_page` sur une page non rattachée à un writer lève une erreur. Il faut `PdfWriter(clone_from=...)` puis modifier la page clonée. Ce point est à intégrer dans C4.

Fichiers d'essai : trois pages réelles copiées depuis le dossier de rangement dans le dossier temporaire (jamais dans le dépôt), puis un PDF de test fabriqué avec un signet, un lien et une annotation.
