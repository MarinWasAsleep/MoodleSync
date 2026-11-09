# Plan : extraire le texte des scans avec Tesseract

État : proposition, 7 novembre 2026. Aucun code écrit.
But : ajouter à MoodleSync une extraction locale du texte des documents scannés, assez simple pour être utilisée sans connaître l'OCR, et assez solide pour traiter les quelques centaines de documents d'un étudiant.
Découpage d'exécution et travail avec deux modèles : `docs/plan-execution-ocr.md`.

---

## 1. Le problème réel

Un étudiant en science politique reçoit chaque semaine des PDF très différents :

- des diapositives et des syllabi, déjà numériques, dont le texte est directement lisible ;
- des articles et des chapitres scannés, souvent des photocopies ou des photos de livres, qui ne contiennent qu'une image ;
- des documents en français, parfois en anglais, avec des notes de bas de page, des colonnes, des tableaux.

Ces scans posent trois problèmes concrets :

1. **Ils ne se cherchent pas.** Un PDF scanné ne répond pas à Ctrl+F.
2. **Ils sont chers et lents à donner à une IA.** Les envoyer à chaque question, en images ou en PDF, consomme des tokens, du temps et parfois de l'argent.
3. **Ils ne se réutilisent pas.** Le même scan est renvoyé à ChatGPT, à Claude, à un outil de révision, puis à un autre, sans jamais devenir un texte propre et cité.

Or, un étudiant n'a pas besoin de connaître Tesseract, les DPI, les modèles de langue ou la segmentation de page. Il a besoin d'une chose : **pouvoir copier le texte de ses cours dans l'outil qu'il utilise déjà**, avec la bonne page sous la main.

L'extraction locale règle cela une fois pour toutes : le scan est converti en texte sur l'ordinateur, le texte est gardé à côté du cours, et il peut être cherché, copié, collé, indexé, sans renvoyer l'image à chaque fois.

---

## 2. La promesse

**« Le texte de tes cours, prêt pour ton IA. Sur ton ordinateur, une seule fois. »**

Trois bénéfices, dans cet ordre :

1. **Chercher dans les scans.** Le texte devient du texte, donc Ctrl+F et recherche globale fonctionnent.
2. **Alimenter une IA sans renvoyer les scans.** Un fichier Markdown léger, avec les pages marquées, se colle dans ChatGPT, Claude, NotebookLM, Obsidian ou un outil de révision.
3. **Ne payer qu'une fois.** Le travail se fait localement. Ensuite, chaque question réutilise le texte déjà extrait, sans refacturer les images.

Ce que la fonctionnalité ne promet pas :

- une reconnaissance parfaite, surtout sur les photos, les colonnes, les formules et l'écriture manuscrite ;
- de remplacer la lecture du document ;
- d'envoyer quoi que ce soit dans le cloud.

---

## 3. Ce que voit l'étudiant

### 3.1 Trois surfaces, une seule fonction

La fonctionnalité apparaît à trois endroits, avec des rôles distincts.

**A. Mes cours, une carte « Préparer mes cours pour l'IA »**

C'est le point de départ. La carte est visible dans les options ou juste sous la liste des cours. Elle dit, en une phrase :

> 18 documents scannés n'ont pas de texte. MoodleSync peut le leur ajouter, sur ton ordinateur, une fois pour toutes. Tu pourras ensuite les chercher et les coller dans une IA sans renvoyer les scans.

Deux boutons : **Préparer** et **Plus tard**.
Deux liens discrets : **À quoi ça sert ?** et **Réglages de l'extraction**.

Le premier lien est essentiel. Il ne renvoie pas vers une documentation : il ouvre un panneau visuel qui montre la différence sur un document de l'étudiant, et permet d'essayer sur une seule page (voir 3.6).

La carte n'apparaît pas si aucun scan n'est détecté. Elle n'apparaît pas non plus comme un écran bloquant : c'est une proposition, pas une étape obligatoire.

**B. Mes textes, un troisième onglet**

L'onglet est toujours visible. C'est la bibliothèque des textes extraits.

- En-tête : nombre de documents, nombre de pages, volume de texte, documents à vérifier.
- Recherche plein texte.
- Liste par cours, puis par section, avec un badge de qualité.
- Actions : ouvrir le Markdown, copier le texte, copier le contexte du cours, exporter.
- État vide : une explication courte et un bouton vers la préparation.

L'onglet ne remplace pas « Mes cours ». Il répond à un autre besoin : travailler avec le contenu, pas avec les fichiers.

**C. Réglages, une section « Texte des cours (OCR) »**

C'est ici que vivent les choses techniques, et seulement ici :

- moteur détecté, version, langues disponibles ;
- emplacement de `tesseract.exe` si la détection échoue ;
- langues, qualité (DPI), mode de page ;
- emplacement des textes, option pour ne pas écrire dans le coffre Obsidian ;
- comportement sur batterie, nombre de pages traitées en parallèle ;
- bouton **Détecter** et bouton **Choisir tesseract.exe** ; le bouton **Installer** est réservé au paquet portable (2.6) et répond d'ici là que l'installation automatique n'est pas encore disponible.

L'interface principale ne prononce pas le mot « OCR » ni « Tesseract ». Elle dit « extraire le texte des scans ». Le nom du moteur reste dans les réglages et dans les documents techniques.

### 3.2 Parcours 1 : Tesseract est déjà installé

C'est le cas de la machine de développement, et le cas de l'utilisateur qui a déjà fait la démarche.

1. MoodleSync détecte Tesseract au démarrage, sans que l'utilisateur ait à le chercher.
2. Après la première synchronisation, il compte les documents sans texte.
3. La carte « Préparer mes cours pour l'IA » apparaît avec un chiffre précis.
4. Un clic ouvre une confirmation courte :

   > 18 documents, environ 312 pages. Environ 8 à 15 minutes. Tu peux continuer à utiliser MoodleSync, mettre en pause ou fermer : la prochaine fois, ça reprend où tu t'es arrêté.

   Options : **Préparer maintenant**, **Plus tard**, et une case **Seulement les documents sans texte** (cochée par défaut).

5. La préparation tourne en arrière-plan, avec une barre et le document en cours.
6. À la fin : « 18 documents prêts, 312 pages. Ouvre Mes textes. » Un badge apparaît sur l'onglet.
7. L'étudiant peut alors chercher, copier le contexte d'un cours, ou exporter.

Le parcours tient en trois clics après l'installation : **Préparer**, **Confirmer**, **Copier**.

### 3.3 Parcours 2 : Tesseract n'est pas installé

Il ne faut pas renvoyer l'étudiant vers un tutoriel de ligne de commande.

**Version 2.5 : sans installation automatique.** Le paquet portable est hors de la 2.5 (décision D6 du contrat) et arrive avec la 2.6. La 2.5 se limite à la détection et au choix manuel du fichier.

La carte affiche :

> Le moteur d'extraction n'est pas encore installé. Indique où il se trouve dans les réglages.

Deux choix :

1. **J'ai déjà Tesseract** (ou **Indiquer l'emplacement**) : détection immédiate, puis choix du fichier `tesseract.exe` si la détection échoue.
2. **Plus tard** : la carte reste, l'application fonctionne normalement.

`ocr_installer` existe côté API mais répond le message `installation_indisponible` : « L'installation automatique n'est pas encore disponible. Indique l'emplacement du moteur dans les réglages. » Un lien vers la page officielle du moteur et le bouton **Indiquer l'emplacement** suffisent pour la 2.5.

**Version 2.6 : paquet portable.** La carte proposera en plus **Installer** : téléchargement d'un paquet portable (environ 65 Mo, sans droits administrateur), vérification SHA-256, décompression dans `%LOCALAPPDATA%\MoodleSync\tesseract`, détection, puis reprise du parcours 1. Même logique de confiance que les mises à jour : HTTPS, empreinte vérifiée, rien ne s'installe sans accord. Le paquet portable contient `tesseract.exe`, ses DLL et les données `fra`, `eng` et `osd`. Il est stocké dans le dossier de l'application, pas dans le dossier de cours. Il survit aux mises à jour de MoodleSync. Si le téléchargement est impossible (hors ligne, réseau de l'université), le choix manuel reste disponible.

### 3.4 Parcours 3 : le premier passage est long

C'est le point le plus important pour l'expérience. Une extraction de 3 000 pages peut prendre une heure. Il faut le dire avant, pas le découvrir après.

Avant un premier passage de plus de 50 documents ou 500 pages, une fenêtre donne (ce sont aussi les seuils de la mise en file automatique après une synchronisation, voir 5.5) :

- le nombre de documents et de pages ;
- une fourchette de durée ;
- le fait que le travail est local ;
- le fait qu'on peut fermer et reprendre ;
- une case pour traiter seulement les scans, pas les PDF déjà lisibles.

Pendant le travail :

- la barre globale de MoodleSync reste active ;
- le document en cours et la page en cours sont affichés ;
- **Pause** et **Annuler** sont disponibles ;
- la synchronisation Moodle a la priorité : si elle est lancée pendant l'extraction, c'est l'extraction qui cède (entre deux pages, ou après un remplacement de PDF), puis elle reprend à la fin de la synchronisation ;
- l'application reste utilisable pour consulter Ma semaine ou les textes déjà prêts.

Après une fermeture :

- l'état est enregistré après chaque page ;
- au lancement suivant, la carte propose **Reprendre l'extraction (12 documents restants)** ;
- aucun document déjà traité n'est refait.

### 3.5 L'onglet Mes textes

**En-tête**

> 128 documents, 4 210 pages, 6,4 Mo de texte. 122 lisibles, 6 à vérifier.
> Tout est sur cet ordinateur. Aucun document n'a été envoyé à une IA.

**Recherche**

Un champ unique, avec un délai de 300 ms. Les résultats affichent :

- le cours et la section ;
- le nom du document ;
- la page ;
- un extrait avec le terme en surbrillance.

Un clic ouvre le Markdown au bon endroit, ou affiche l'extrait dans un panneau avec **Copier l'extrait**.

**Liste des documents**

Chaque ligne :

- nom du document ;
- type : « texte natif » ou « scanné » ;
- pages ;
- badge de qualité : **Bon**, **À vérifier**, **Difficile** ;
- bouton **Ouvrir** ;
- menu **Copier le texte**, **Refaire**, **Marquer comme vérifié**.

**Actions principales**

- **Copier le contexte du cours** : choisit un cours, assemble un Markdown propre avec les pages marquées, copie dans le presse-papiers, affiche le nombre de caractères.
- **Exporter** : crée un zip avec les Markdown et, en option, un JSONL page par page pour les outils de RAG.
- **Ouvrir le dossier des textes** : ouvre `Textes/` dans l'explorateur ou le Finder.
- **Voir la qualité** : liste des pages vides, floues, protégées ou à faible confiance.

**État vide**

> Aucun texte extrait pour l'instant.
> MoodleSync peut extraire le texte de tes scans et de tes PDF, sur ton ordinateur. Une seule fois, puis tu pourras les chercher et les coller dans l'IA de ton choix.
> **Préparer mes cours**

### 3.6 Expliquer à quoi ça sert, dans l'interface

C'est le point qui manquait dans la première version de ce plan. Les bénéfices étaient dispersés dans plusieurs écrans, et expliqués avec des phrases. Une phrase ne suffit pas : l'étudiant doit **voir** la différence avant de s'engager sur 300 pages.

Trois niveaux d'explication, du plus léger au plus convaincant.

#### Niveau 1 : une phrase au bon endroit

Sur la carte de Ma semaine, la phrase ne parle pas de format ni de technique. Elle parle d'un problème vécu :

> Un PDF scanné, c'est une photo de texte. On peut le lire, mais pas le chercher, ni le copier proprement, ni le donner à une IA sans renvoyer l'image à chaque fois.

Puis la solution, en une ligne :

> MoodleSync le transforme en texte, une fois, sur ton ordinateur. Ensuite tu peux chercher, copier et citer.

Le mot « Markdown » n'apparaît pas ici. Le mot « OCR » non plus.

#### Niveau 2 : le panneau « À quoi ça sert ? »

Un lien sous la carte ouvre un panneau, pas une page de documentation. Il tient en un écran et contient quatre blocs.

**Bloc 1 : avant et après, côte à côte**

Deux colonnes, avec le même document.

| Aujourd'hui, un scan | Après MoodleSync |
|---|---|
| Une image de 24 pages, 18 Mo | Un fichier texte de 24 pages, environ 90 Ko |
| Ctrl+F ne trouve rien | Ctrl+F trouve « institution » à la page 12 |
| À renvoyer à chaque question posée à une IA | Se colle en un clic, avec les pages marquées |
| L'IA doit deviner le texte sur l'image | L'IA lit un texte propre et peut citer `[p. 12]` |

Les chiffres affichés sont ceux de la bibliothèque de l'étudiant quand ils sont connus. Sinon, l'exemple reste générique et annoncé comme un exemple.

**Bloc 2 : trois usages concrets**

Trois cartes, avec une icône et une phrase.

1. **Retrouver une citation.** « Cherche un mot dans tous tes cours, même dans les photocopies. La page est indiquée. »
2. **Interroger une IA.** « Colle le texte d'un cours dans ChatGPT, Claude ou NotebookLM, puis pose tes questions. L'IA peut citer les pages au lieu de deviner. »
3. **Réviser et prendre des notes.** « Le texte va dans Obsidian, dans une fiche ou dans un outil de révision, sans rescanner le document. »

Une phrase de coût, sans chiffre inventé :

> Une seule extraction, ensuite tu réutilises. Tu ne renvoies plus les images à chaque question.

**Bloc 3 : une limite, tout de suite**

Une seule phrase, pour éviter la déception :

> La reconnaissance n'est pas parfaite : l'écriture manuscrite, les formules et les colonnes lui résistent parfois. MoodleSync signale les pages à vérifier.

**Bloc 4 : la preuve sur une page**

C'est le bloc qui fait basculer la décision. Un bouton :

> **Essayer sur une page de mon cours**

Si Tesseract est installé, MoodleSync choisit un scan de l'étudiant, extrait **une seule page**, et affiche côte à côte :

- l'image de la page, pour reconnaître le document ;
- le texte extrait, avec les mots reconnus ;
- la confiance de la page ;
- deux boutons : **Copier cet extrait** et **Préparer tout le cours**.

L'aperçu prend quelques secondes. Il n'écrit rien dans `Textes/`, ne met rien en file et ne modifie aucun fichier. C'est un essai, pas un engagement.

Si Tesseract n'est pas installé, le panneau montre un exemple statique et ne propose rien d'autre : l'installation et le choix manuel du moteur sont dans la carte de préparation (Ma semaine) et dans les réglages, décision du 9 novembre 2026. L'étudiant comprend la valeur avant de toucher à quoi que ce soit.

Si aucun scan n'est détecté, le bouton devient **Voir un exemple** et utilise un document de démonstration embarqué. Le panneau reste utile.

**Pourquoi un fichier `.md` ?**

Une petite ligne repliable, pour ceux qui se posent la question :

> Markdown (`.md`) est un simple fichier texte avec des titres. Obsidian, les éditeurs de texte et les outils d'IA le lisent. Tu n'as pas besoin de connaître le format : ce qui compte, c'est que le texte soit cherchable et copiable.

On ne commence jamais par le format. On commence par le problème, puis par la démonstration. Le `.md` n'est qu'un contenant.

#### Niveau 3 : le même panneau aux autres endroits

Le panneau « À quoi ça sert ? » est accessible :

- depuis la carte de Ma semaine ;
- depuis l'état vide de Mes textes ;
- depuis la fenêtre de consentement du premier passage, sous une forme compacte : une ligne « Avant : une image. Après : du texte cherchable et citable. » et un lien vers le panneau complet.

Il n'apparaît pas comme une fenêtre publicitaire au démarrage. Il est là quand l'étudiant se demande « pourquoi je ferais ça ? », pas avant.

#### Détails d'interface

- Le panneau est une boîte de dialogue native de la page, comme les autres dialogues du projet, avec fermeture au clavier et focus maîtrisé.
- Les deux colonnes passent l'une sous l'autre dans une fenêtre étroite.
- L'image de l'aperçu a un texte alternatif qui décrit le document.
- La confiance n'est pas indiquée par la couleur seule : un mot est écrit à côté.
- L'aperçu réutilise le rendu et l'appel Tesseract du moteur, avec une limite d'une page et un délai court.
- Aucun fichier de sortie n'est créé pendant l'aperçu. Le cache de l'aperçu est en mémoire et disparaît à la fermeture du panneau.
- Le panneau peut être rouvert sans relancer l'extraction.

#### Microcopy du panneau

Titre : **À quoi ça sert ?**

Chapeau :

> Un PDF scanné, c'est une photo de texte. MoodleSync peut le transformer en vrai texte, sur ton ordinateur, une seule fois.

Après le avant/après :

> Ensuite, tu cherches un mot, tu copies un passage, tu colles ton cours dans une IA. Les pages restent indiquées.

Sous le bouton d'essai :

> Une page, quelques secondes. Rien n'est enregistré tant que tu n'as pas confirmé.

Sous les limites :

> Par défaut, tes fichiers originaux ne sont jamais modifiés. Si tu choisis de rendre un PDF cherchable, le fichier est remplacé sur place et garde ses pages d'origine. Aucune copie lourde n'est conservée.

### 3.7 Microcopy et ton

Le ton reste celui du projet : direct, utile, sans jargon.

- **À faire** : « Extraire le texte des scans », « Préparer mes cours pour l'IA », « Copier le contexte du cours ».
- **À éviter** : « OCR », « Tesseract », « segmentation », « DPI », « tessdata » dans l'interface principale.
- **Transparence** : « sur ton ordinateur », « aucun document n'est envoyé », « la reconnaissance n'est pas parfaite ».
- **Durée** : toujours une fourchette, jamais une promesse exacte.
- **Qualité** : « à vérifier », jamais « échec » pour un document lisible mais imparfait.

---

## 4. Spécification fonctionnelle

### 4.1 Formats pris en charge

**Lot 1, le cœur du besoin :**

- PDF, y compris les PDF mixtes (certaines pages ont du texte, d'autres non) ;
- images : `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`, `.webp` ;
- TIFF multipage : chaque page est traitée.

**Lot 2, sans OCR, mais utile :**

- `.docx` et `.pptx` : extraction directe du texte XML, sans dépendance lourde ;
- `.odt` et `.odp` : même principe, plus tard.

**Hors périmètre initial :**

- écriture manuscrite ;
- formules mathématiques complexes ;
- tableaux à structure fine ;
- HEIC sans conversion ;
- PDF protégés par un mot de passe (signalés, pas forcés).

### 4.2 Ce qui est extrait, et ce qui ne l'est pas

La règle centrale : **ne pas océriser ce qui a déjà du texte**.

Pour chaque page PDF :

1. extraire le texte avec `pypdf` ;
2. compter les caractères utiles ;
3. si la page a assez de texte, garder le texte natif, sans OCR ;
4. sinon, rendre la page en image et lancer Tesseract ;
5. marquer la page comme `texte` ou `ocr`.

Avantages :

- les diapositives et les articles numériques sont instantanés ;
- la qualité est meilleure, car le texte natif est exact ;
- le temps de traitement se concentre sur les vrais scans.

Seuil de départ : 80 caractères alphanumériques par page. Il est réglable dans le code, pas dans l'interface. Une page blanche reste blanche, elle n'est pas signalée comme échec.

### 4.3 Sorties

Dans le dossier de rangement, un nouveau dossier visible :

```text
Textes/
  index.md
  Qualité des textes.md
  Cours A/
    Cours A - texte complet.md
    Section 1/
      article.pdf.md
      chapitre.pdf.md
  Cours B/
    Cours B - texte complet.md
    ...
```

Règles :

- le chemin reprend celui du document source, avec l'extension d'origine conservée dans le nom (`article.pdf.md`) pour éviter les collisions ;
- un fichier par document, avec les pages marquées ;
- un fichier par cours, prêt à coller dans une IA ;
- un index global, avec les liens et les compteurs ;
- un fichier de qualité, qui liste les documents à vérifier ;
- le JSONL n'est créé qu'à la demande, pas par défaut.

Le dossier `Textes/` est visible parce qu'il doit être utilisable dans Obsidian et facile à trouver. Le cache et la file de travail restent cachés dans `.moodlesync-ocr/`, que le parcours actuel ignore déjà (dossiers commençant par un point).

Si le dossier de destination est un coffre Obsidian synchronisé par OneDrive, les textes seront synchronisés comme le reste. C'est un choix de l'utilisateur. Une option permet de placer `Textes/` ailleurs.

#### Le PDF d'origine devient-il cherchable ?

**Non, par défaut.** Le PDF d'origine n'est ni modifié ni transformé. Il reste exactement le fichier reçu de Moodle, avec ses images. Ce qui devient cherchable, c'est le fichier texte créé à côté, dans `Textes/`. Le mode explicite `remplacer`, décrit plus bas, est la seule exception.

Il faut distinguer deux recherches :

1. **La recherche dans MoodleSync, Obsidian ou un éditeur de texte.** Elle porte sur les `.md`. Elle fonctionne dès que l'extraction est faite, y compris pour les scans. C'est le besoin principal : retrouver une citation, un auteur, une notion, avec la page.
2. **La recherche Ctrl+F dans le lecteur PDF.** Elle ne fonctionne que si le PDF contient une couche de texte. Un scan n'en a pas. Le fichier `.md` à côté ne change rien pour Acrobat, Edge ou Aperçu.

Conséquences pour l'interface :

- le bouton **Ouvrir** d'un résultat ouvre le `.md`, pas le PDF ;
- un bouton séparé **Voir le document source** ouvre le PDF, pour comparer ;
- une phrase explicite apparaît dans le panneau « À quoi ça sert ? » et dans les réglages : « Par défaut, ton PDF d'origine n'est pas modifié. La recherche se fait dans Mes textes. »

Un PDF cherchable n'est pas le comportement par défaut. Un **second** PDF conservé à côté de l'original est écarté pour la 2.5 (décision D3 du contrat) :

- il faudrait fabriquer un nouveau PDF, avec l'image de chaque page et une couche de texte invisible par-dessus ;
- ce fichier serait un doublon, plus lourd que le Markdown, et double le volume ;
- le rendu des pages scannées serait une image à 300 DPI, donc proche de l'original mais pas identique ;
- `ocr_regler` refuse donc toute valeur de `ocr_pdf` autre que `aucun` et `remplacer` (message `mode_indisponible`) ; la question est à rouvrir après la 2.5 si le besoin se confirme.

Le mode `remplacer` remplace le PDF par sa version cherchable, sans conserver de copie locale de l'original. La restauration se fait en retéléchargeant l'original depuis Moodle.

Pour l'IA, le PDF cherchable n'apporte rien de plus : le Markdown est plus léger, plus facile à citer et plus facile à découper. Le PDF cherchable sert seulement au confort de lecture dans un lecteur PDF.

#### Remplacer le PDF par une version cherchable ?

Oui, c'est possible, et c'est même le comportement le plus pratique pour quelqu'un qui reste dans Acrobat ou Edge et veut Ctrl+F directement dans son document. Mais il faut le faire explicitement, pas en silence.

Deux politiques, réglables dans les options avancées :

| Mode | Ce qui se passe | Pour qui |
|---|---|---|
| `aucun` (défaut) | Le PDF reste intact, seul le `.md` est créé | Tout le monde, assez pour chercher dans MoodleSync et Obsidian |
| `remplacer` | Le PDF du dossier de cours devient cherchable, au même chemin | Ceux qui veulent Ctrl+F à l'endroit habituel |

Il n'y a que ces deux politiques en 2.5. Un second PDF à côté de l'original est refusé (`mode_indisponible`, D3) : il doublerait le volume. À rouvrir après la 2.5 si le besoin se confirme.

**Pas de copie locale de l'original**

Le PDF cherchable contient déjà les pages d'origine, avec leurs images. Il n'y a donc pas de dossier `Originaux/` et pas de second PDF conservé. Le seul endroit où l'original exact reste disponible est Moodle.

Ce choix évite de doubler le volume, ce qui serait inacceptable sur une bibliothèque de plusieurs centaines de documents. Il a une contrepartie claire : le fichier exact reçu de l'enseignant n'est plus sur le disque. Pour le récupérer, MoodleSync le retélécharge depuis Moodle. Sans réseau, ou si le cours a été fermé, la restauration exacte n'est pas possible, mais le PDF cherchable conserve les images et le texte des pages.

L'identité du fichier est conservée sans copie lourde, dans l'état de synchronisation :

```json
{
  "t": 1760000000,
  "chemin": "Cours A/Section 1/article.pdf",
  "genere": {
    "type": "pdf_cherchable",
    "taille_source": 18000000,
    "empreinte_source": "sha256:...",
    "taille_fichier": 18300000,
    "empreinte_fichier": "sha256:...",
    "pages": 24,
    "date": "2026-11-07T18:30:00",
    "version": 1
  }
}
```

`taille_source` et `empreinte_source` décrivent le PDF reçu de Moodle. `taille_fichier` et `empreinte_fichier` décrivent le PDF cherchable présent sur le disque. Les deux sont nécessaires : le premier pour reconnaître une republication, le second pour retrouver un fichier déplacé ou renommé.

Toutes ces empreintes sont des `sha256:` du **fichier entier** (décision D2 du contrat), comme celles de la marque dans le PDF et du cache. Elles ne sont calculées que sur les candidats de même taille. L'empreinte existante de `moteur.empreinte` (SHA-1 des 256 premiers Ko) ne change pas : elle reste celle de l'index et de la déduplication actuels.

**Deux techniques décrites, une seule utilisée**

1. **Ajouter une couche sur la page d'origine.** Tesseract produit une page PDF texte seule (`textonly_pdf`), ou un PDF construit à partir des coordonnées TSV, puis `pypdf` fusionne cette couche sur la page existante. L'image, les annotations et les liens de la page sont conservés. C'est la méthode propre, et c'est la seule autorisée en mode `remplacer` : elle garantit un volume proche de l'original et ne perd pas les objets PDF. Elle oblige à vérifier l'alignement des coordonnées et la police Unicode.
2. **Reconstruire les pages scannées.** Tesseract produit un PDF avec l'image et le texte, puis `pypdf` assemble le document. C'est plus simple, mais les objets PDF d'origine (signets, liens, formulaires) peuvent être perdus, et le fichier peut grossir. Cette méthode n'est utilisée dans aucun mode : reconstruire une page est interdit (invariant 2 du contrat), y compris en mode `remplacer`, où il n'existe pas de copie de secours. Elle n'est décrite que pour expliquer pourquoi elle est écartée.

Dans les deux cas, on n'utilise ni Ghostscript ni OCRmyPDF, pour ne pas ajouter une dépendance AGPL et un binaire lourd.

**Règles de sécurité**

- Ne jamais remplacer un PDF numérique déjà cherchable.
- Ne jamais remplacer un PDF signé, protégé ou en lecture seule.
- Compter les annotations, les liens et les signets avant et après la superposition. Si un seul disparaît, abandonner et laisser l'original en place.
- Calculer `taille_source` et `empreinte_source` sur l'original avant de le transformer, et les écrire dans l'état avant le remplacement.
- Écrire le PDF cherchable dans un fichier temporaire, vérifier que le nombre de pages est identique, que les dimensions de page sont identiques, que le texte est extractible, que le PDF s'ouvre et que le rendu de quelques pages correspond à l'original. Remplacer seulement si tout est bon.
- Ne jamais conserver de second PDF. Si le remplacement échoue, l'original reste intact.
- Ajouter au PDF cherchable une marque discrète dans ses métadonnées : URL Moodle sans jeton, `timemodified`, taille et empreinte de la source, nombre de pages, version. Elle sert de secours si `.moodlesync.json` est perdu.
- Afficher un badge **PDF cherchable** dans Mes textes, et une phrase claire dans les réglages : « L'original exact n'est pas conservé en double. MoodleSync peut le retélécharger depuis Moodle. »
- Si l'enseignant republie le document, comparer le nouveau fichier à `taille_source` et `empreinte_source`. Si le contenu est identique, seul le `timemodified` change, et le PDF cherchable est conservé. Sinon, le nouveau PDF remplace l'ancien PDF cherchable, sans renommage « ancienne version » du PDF. Seul le `.md` de l'ancienne version peut être conservé, car il est petit.

**Pourquoi ce n'est pas le défaut**

Tous les étudiants n'ont pas besoin de Ctrl+F dans le PDF. Beaucoup travaillent dans Obsidian ou collent le texte dans une IA, et le `.md` suffit. Remplacer un fichier de cours est une opération sensible : elle change le fichier reçu de l'enseignant, elle peut casser un signet ou une signature, et l'original exact n'est plus disponible localement. Le mode `aucun` reste donc le plus sûr. Le mode `remplacer` est une option explicite pour ceux qui savent pourquoi ils la choisissent.

**Coût**

La couche de texte est produite à partir du même passage OCR que le `.md` : pas de seconde reconnaissance. Avec la méthode de superposition, le PDF cherchable ajoute surtout la couche de texte, quelques kilo-octets par page. Une reconstruction complète peut ajouter plusieurs méga-octets par document, et c'est une raison de plus pour ne jamais la choisir. Aucun espace n'est consommé par une copie de l'original.

### 4.4 Qualité

Chaque page reçoit une confiance moyenne, calculée sur les mots reconnus par Tesseract. Elle est stockée de 0 à 1 (le TSV de Tesseract, de 0 à 100, est divisé par 100) et affichée avec une virgule, par exemple « 0,89 » (décision D5 du contrat).

Trois niveaux par défaut :

- **Bon** : confiance supérieure ou égale à 0,85 ;
- **À vérifier** : de 0,70 (inclus) à 0,85 (exclu) ;
- **Difficile** : inférieure à 0,70.

Le document affiche aussi :

- le nombre de pages sans texte détecté ;
- le nombre de pages en échec ;
- le mode utilisé (`texte` ou `ocr`) ;
- la langue employée.

Une page difficile n'est jamais supprimée. Elle est incluse avec une mention, pour que l'étudiant puisse juger. Le fichier `Qualité des textes.md` donne la liste, avec un lien vers le document source.

Actions proposées :

- **Refaire avec un autre mode** : page simple, bloc unique, orientation automatique ;
- **Marquer comme vérifié** : masque l'avertissement sans modifier le texte ;
- **Ouvrir le document source** : pour comparer.

### 4.5 Fraîcheur, reprise, versions

- La clé de cache est le chemin relatif plus une empreinte du contenu (`sha256:` du fichier entier, D2) et des réglages (langue, DPI, mode, version du moteur).
- Un fichier inchangé n'est jamais refait.
- Un fichier déplacé ou renommé est retrouvé par son empreinte et par l'état `genere` quand il a été transformé en PDF cherchable. La synchronisation actuelle, elle, retrouve surtout par le nom et la taille : c'est précisément ce qu'il faut adapter pour le mode `remplacer` (voir 5.10).
- Un fichier republié par l'enseignant est réextrait. L'ancien `.md` est conservé à côté, avec la mention « ancienne version » et la date. Le PDF cherchable, lui, n'est pas conservé : il est remplacé au même chemin par la nouvelle version, pour ne pas doubler le volume.
- Une fermeture pendant un document conserve les pages déjà faites. La reprise commence à la première page manquante.
- Un fichier supprimé du disque ne supprime pas son texte sans accord. Il est listé comme orphelin, avec un choix **Conserver** ou **Retirer de la liste**.

---

## 5. Architecture technique

### 5.1 Modules et points d'intégration

Le projet a déjà une séparation claire : `moteur.py` pour les données, `application.py` pour le pont, `interface/` pour la page. On la respecte.

**Nouveaux fichiers**

| Fichier | Rôle |
|---|---|
| `moodlesync/ocr.py` | détection de Tesseract, extraction PDF et images, cache, file de travail, rendu Markdown, qualité |
| `moodlesync/api_textes.py` | mixin `ApiTextes`, appelé par la page, sur le modèle de `api_horaire.py` |
| `moodlesync/interface/textes.js` | onglet Mes textes, recherche, copie, export, progression |
| `tests/test_ocr.py` | tests unitaires et tests d'intégration facultatifs |

**Fichiers modifiés**

| Fichier | Modification |
|---|---|
| `moodlesync/application.py` | `Api` hérite aussi de `ApiTextes` ; initialisation ; enqueue après `sync_lancer` ; priorité de la synchronisation sur l'extraction |
| `moodlesync/moteur.py` | constantes de langue pour `Textes`, `Texts` ; éventuellement un utilitaire de chemin partagé |
| `moodlesync/interface/index.html` | troisième onglet, section `v-textes`, boîte de dialogue de consentement, icônes |
| `moodlesync/interface/style.css` | styles de la bibliothèque, des badges, des résultats, du panneau de qualité |
| `moodlesync/interface/app.js` | onglet supplémentaire, état de vérification, occupation globale |
| `moodlesync/interface/sync.js` | carte de préparation, lien après synchronisation, message de reprise |
| `MoodleSync.spec` | inclure `pypdfium2` et Pillow |
| `requirements.txt` | ajouter `pypdfium2` et Pillow, versions épinglées |
| `README.md`, `docs/LISEZ-MOI.txt`, `docs/notes-version.md`, `CONTEXTE.md` | documentation, vie privée, limites, version 2.5 |
| `docs/TIERS.md` | licences des composants ajoutés |

**API exposée à la page**

| Méthode | Rôle |
|---|---|
| `ocr_etat()` | moteur, version, langues, activation, file, compteurs, qualité |
| `ocr_detecter()` | relance la détection et enregistre le chemin |
| `ocr_choisir_exe()` | boîte de dialogue native pour `tesseract.exe` |
| `ocr_installer()` | réservé à la 2.6 (paquet portable, avec progression) ; en 2.5, répond `installation_indisponible` |
| `ocr_apercu(chemin, page)` | extrait une seule page pour l'essai « À quoi ça sert ? », sans rien écrire ni mettre en file |
| `ocr_lancer(portee, refaire)` | met en file et démarre, sans bloquer la page |
| `ocr_pause()`, `ocr_reprendre()`, `ocr_annuler()` | contrôle du travail |
| `ocr_documents(filtre)` | liste pour l'onglet |
| `ocr_chercher(texte)` | recherche plein texte et extraits |
| `ocr_copier(portee)` | assemble et copie le contexte |
| `ocr_exporter(portee, format)` | crée un zip ou un Markdown |
| `ocr_ouvrir(chemin)` | ouvre un Markdown ou le dossier |
| `ocr_pdf_restaurer(chemin)` | retélécharge l'original depuis Moodle, le vérifie et retire la version cherchable |
| `ocr_regler(cle, valeur)` | réglages, liste blanche |

Les méthodes longues ne bloquent pas la page. `ocr_lancer` démarre un fil de travail et rend la main. La progression remonte par `window.textesProgres({...})`, comme la synchronisation.

### 5.2 Détection de Tesseract

C'est le point qui a échoué le plus souvent dans les essais : **Tesseract n'est pas forcément dans le PATH**.

Sur la machine de développement :

- `tesseract.exe` est dans `C:\Program Files\Tesseract-OCR\tesseract.exe` ;
- il n'est pas dans le PATH ;
- les langues `eng`, `fra` et `osd` sont dans `C:\Users\<utilisateur>\AppData\Local\tessdata` ;
- `TESSDATA_PREFIX` pointe vers ce dossier ;
- le registre `HKLM\SOFTWARE\Tesseract-OCR` contient `Path` et `InstallDir` ;
- la version détectée est `5.5.3.20260724`.

La détection doit donc essayer, dans l'ordre :

1. le chemin enregistré dans la configuration ;
2. `shutil.which("tesseract")` ;
3. le registre Windows, `HKLM\SOFTWARE\Tesseract-OCR`, `HKLM\SOFTWARE\WOW6432Node\Tesseract-OCR`, `HKCU\SOFTWARE\Tesseract-OCR`, valeurs `Path` et `InstallDir` ;
4. les chemins usuels : `C:\Program Files\Tesseract-OCR`, `C:\Program Files (x86)\Tesseract-OCR`, `%LOCALAPPDATA%\Programs\Tesseract-OCR`, `%LOCALAPPDATA%\Tesseract-OCR`, Chocolatey, Scoop ;
5. sur macOS : `/opt/homebrew/bin/tesseract`, `/usr/local/bin/tesseract`, `/usr/bin/tesseract` ;
6. à partir de la 2.6, le paquet portable installé par MoodleSync dans `%LOCALAPPDATA%\MoodleSync\tesseract` (cette étape est sans objet en 2.5).

Vérification :

- lancer `tesseract --version` avec un délai de 5 secondes ;
- exiger une version 4 ou 5, signaler les versions 3 ;
- lancer `tesseract --list-langs` ;
- lire le dossier de données réellement utilisé ;
- si `TESSDATA_PREFIX` existe, le respecter ;
- si les langues sont réparties entre deux dossiers, choisir celui qui contient `fra` et `eng`, sinon prévenir et se rabattre sur la langue disponible.

Sous Windows, tous les appels utilisent `CREATE_NO_WINDOW` pour éviter qu'une console noire clignote dans une application sans console. Les chemins passent par une liste d'arguments, jamais par un shell, pour supporter les espaces et les accents.

Si la détection échoue, le message doit être utile :

> Tesseract n'a pas été trouvé. Il est peut-être installé ailleurs. Indique le fichier `tesseract.exe`. (L'installation automatique n'existe pas encore : elle viendra avec la 2.6.)

Jamais un traceback.

### 5.3 Pipeline PDF

**Rendu des pages**

- `pypdf` est déjà une dépendance, pour le texte et le nombre de pages.
- `pypdfium2` rend les pages en image. Il est préféré à PyMuPDF, présent sur la machine de développement mais sous licence AGPL, incompatible avec un exe MIT. `pypdfium2` est sous licence permissive et n'a pas besoin de Ghostscript ni de Poppler.
- Rendu par défaut à 300 DPI, soit un facteur 300/72. Une page A4 fait environ 2 480 par 3 508 pixels.
- Conversion en niveaux de gris et autocontraste avec Pillow. Pas de binarisation agressive : Tesseract gère mieux l'image d'origine.
- Rotation EXIF corrigée pour les photos. Pour les pages PDF tournées, le mode orientation automatique est proposé en réparation.

**Texte natif**

- `pypdf.PdfReader(...).pages[i].extract_text()`.
- Normalisation : espaces multiples, coupures de mots en fin de ligne (`-` suivi d'un retour), sauts de paragraphe.
- Pas de nettoyage excessif : on ne veut pas abîmer les citations, les noms propres ou les notes.

**Pages mixtes**

- Une page avec du texte natif et une image est traitée comme du texte natif si le texte est suffisant.
- Une page sans texte mais avec une image est océrisée.
- Une page sans texte et sans image est laissée vide, avec une mention dans le rapport de qualité.

**Images isolées**

- OCR direct à 300 DPI, ou redimensionnement si l'image est trop petite.
- TIFF multipage : une page par image.
- GIF : première image seulement, avec mention.

### 5.4 Appel à Tesseract

Appel direct par `subprocess`, sans `pytesseract` : on garde le contrôle sur le délai, l'annulation, l'encodage et la sortie TSV.

Commande type :

```text
tesseract <image> stdout -l fra+eng --psm 3 --oem 1 --tessdata-dir <dossier> tsv
```

Pourquoi TSV :

- il donne le texte mot par mot ;
- il donne une confiance par mot, donc par ligne et par page ;
- il permet de reconstruire les lignes dans l'ordre ;
- il permettra plus tard de surligner un résultat de recherche dans la page.

Reconstruction :

- garder les niveaux 5 (mots) ;
- regrouper par bloc, paragraphe et ligne ;
- trier par coordonnées ;
- joindre les mots avec un espace ;
- ajouter un saut de ligne entre les lignes ;
- calculer la confiance moyenne des mots, en ignorant les valeurs négatives.

Réglages :

- `fra+eng` par défaut si les deux langues existent, sinon la langue disponible ;
- `--psm 3` par défaut ;
- `--psm 1` pour l'orientation automatique ;
- `--psm 6` pour un bloc unique ;
- `--oem 1` pour le moteur LSTM ;
- délai de 120 secondes par page ;
- priorité basse du processus ;
- annulation : tuer le processus en cours, conserver les pages déjà faites.

Cas d'erreur :

- page vide : texte vide, pas une erreur ;
- page illisible : mention dans le rapport ;
- PDF protégé : message clair, pas de tentative de contournement ;
- fichier verrouillé par OneDrive ou l'antivirus : un nouvel essai, puis erreur ;
- fichier trop gros : au-delà de 300 Mo par défaut, demander confirmation ou ignorer.

### 5.5 File de travail

Un seul travail d'extraction à la fois, dans un fil dédié.

- La file est persistante, dans `.moodlesync-ocr/file.json`.
- Elle contient le chemin, la priorité, l'état et la date.
- L'état est écrit après chaque document et après chaque page.
- Le fil est démoniaque : une fermeture de la fenêtre n'attend pas la fin, et la reprise se fait au lancement suivant.
- Deux pages peuvent être océrisées en parallèle au maximum, pour ne pas saturer un portable. Le réglage est avancé.
- La synchronisation et l'extraction ne tournent pas ensemble, et **la synchronisation a la priorité** (décision D1 du contrat, invariant 7). Quand une synchronisation est demandée, elle attend au plus une unité de travail (une page, ou un remplacement de PDF) ; l'extraction vérifie cette demande entre deux pages et après un remplacement, cède, passe à l'état `pause_sync`, puis reprend d'elle-même quand la synchronisation est terminée.
- Un seul verrou d'extraction empêche deux lancements.
- Les erreurs vont dans le journal et dans `erreurs.txt`, avec le détail technique, jamais dans une fenêtre.

Après une synchronisation, si `ocr` et `ocr_apres_sync` sont vrais (décision D7 du contrat) :

- les nouveaux fichiers et les fichiers republiés sont mis en file ;
- les fichiers déjà traités et inchangés ne le sont pas ;
- le résultat de la synchronisation indique « 3 documents à préparer » sans bloquer ;
- l'extraction démarre **seule** si la fenêtre est ouverte et si le lot compte 50 documents et 500 pages au plus : ce sont les seuils de la fenêtre de confirmation décrite en 3.4 ;
- au-delà de ces seuils, la file reste en attente et la carte demande une confirmation, avec la durée estimée, avant de démarrer ;
- si l'application est lancée en mode `--auto` sans fenêtre, l'extraction n'est jamais lancée. Elle attend la prochaine ouverture de la fenêtre. Un mode `--ocr` pourra la lancer sans fenêtre, pour les utilisateurs avancés.

### 5.6 Configuration

Nouvelles clés dans `config.json`, avec des valeurs par défaut sûres :

| Clé | Défaut | Rôle |
|---|---|---|
| `ocr` | `false` | activation, après consentement |
| `ocr_exe` | `""` | chemin explicite de `tesseract.exe` |
| `ocr_tessdata` | `""` | dossier des langues, si détection nécessaire |
| `ocr_langues` | `"fra+eng"` | langue de reconnaissance |
| `ocr_dpi` | `300` | qualité de rendu |
| `ocr_psm` | `3` | mode de page |
| `ocr_dossier` | `"Textes"` | dossier de sortie visible |
| `ocr_apres_sync` | `true` | mise en file automatique après synchronisation |
| `ocr_max_mo` | `300` | taille maximale d'un document |
| `ocr_threads` | `2` | pages en parallèle |
| `ocr_batterie` | `"pause"` | pause si batterie faible |
| `ocr_sortie_hors_coffre` | `false` | écrire les textes ailleurs |
| `ocr_pdf` | `"aucun"` | `aucun` ou `remplacer` : fabriquer aussi un PDF cherchable, en le remplaçant sur place |

Les valeurs sont validées dans `ocr_regler` : langue parmi les langues détectées, DPI entre 150 et 600, mode parmi 1, 3, 4 et 6, taille entre 10 et 2 000 Mo, threads entre 1 et 4, `ocr_pdf` parmi `aucun` et `remplacer` (toute autre valeur est refusée avec le message `mode_indisponible`). Aucun chemin relatif avec `..`.

`sync_etat` renvoie un résumé de l'OCR pour la carte : installé, activé, en attente, prêt, à vérifier. Cela évite un appel supplémentaire au chargement.

### 5.7 État et cache

Deux niveaux.

**Cache de production**, dans `.moodlesync-ocr/` à la racine du dossier de rangement :

```json
{
  "version": 1,
  "documents": {
    "Cours A/Section 1/article.pdf": {
      "empreinte": "sha256:...",
      "taille": 1234567,
      "pages": 24,
      "pages_texte": 2,
      "pages_ocr": 22,
      "confiance": 0.89,
      "langues": "fra+eng",
      "dpi": 300,
      "psm": 3,
      "moteur": "5.5.3",
      "sortie": "Textes/Cours A/Section 1/article.pdf.md",
      "etat": "ok",
      "date": "2026-11-07T18:30:00"
    }
  }
}
```

**Pages en cours**, dans `.moodlesync-ocr/pages/<empreinte>.json`, pour reprendre un document interrompu sans refaire les pages déjà faites.

Le cache est petit, mais il contient du texte. Il est caché pour Obsidian et pour le parcours de synchronisation. Une option permet de le placer dans `%LOCALAPPDATA%` si l'utilisateur ne veut rien de caché dans son coffre.

La clé inclut les réglages : changer de langue, de DPI ou de mode invalide les pages concernées, sans toucher aux autres documents.

### 5.8 Performance

Ordres de grandeur à vérifier pendant le lot 0, puis à afficher dans l'interface.

- PDF numérique : moins d'une seconde par document.
- Page scannée à 300 DPI : environ 1 à 3 secondes avec Tesseract 5.
- 3 000 pages, deux pages en parallèle : environ 25 à 75 minutes.
- 250 documents de 12 pages : environ 1 à 2 heures au premier passage.
- Texte produit : environ 2 à 5 Ko par page, soit 6 à 15 Mo pour 3 000 pages, contre plusieurs centaines de Mo à plusieurs Go de scans.
- Mémoire : une page A4 en niveaux de gris à 300 DPI fait environ 8 Mo, deux pages en parallèle restent sous 50 Mo.

Conséquences :

- ne jamais océriser un PDF qui a déjà du texte ;
- ne jamais refaire un document inchangé ;
- annoncer la durée avant le premier passage ;
- permettre la pause, la reprise et la fermeture ;
- ne pas lancer l'extraction au démarrage de session, seulement quand la fenêtre est ouverte ou sur commande explicite.

### 5.9 Sécurité et vie privée

- Aucun appel réseau pendant l'extraction. Tesseract lit des fichiers locaux et écrit du texte local.
- Les seuls appels réseau possibles hors synchronisation sont déclenchés par l'utilisateur : la restauration d'un original (retéléchargement depuis Moodle) et, à partir de la 2.6, le téléchargement du paquet portable, en HTTPS, avec une empreinte SHA-256 vérifiée. Même logique que `maj.py`.
- Aucune télémétrie. Les compteurs restent locaux.
- Les textes peuvent contenir des documents protégés par le droit d'auteur. Ils restent sur l'ordinateur, comme les PDF. Le README le rappelle.
- Le dossier `Textes/` peut être synchronisé par Obsidian, OneDrive ou iCloud. C'est signalé dans les réglages, avec une option pour le placer ailleurs.
- Aucun mot de passe, aucun jeton, aucun contenu de cours n'est publié dans le dépôt.
- Les fichiers sont ouverts en lecture seule. Aucun fichier source n'est modifié ou supprimé, sauf en mode `remplacer`, explicitement choisi. Dans ce mode, aucune copie de l'original n'est conservée localement : le PDF cherchable contient les pages, et l'original exact se retélécharge depuis Moodle.
- Un fichier de sortie existant n'est réécrit que s'il porte la marque MoodleSync (décision D4 du contrat). Pour le `.md` d'un document, la marque est la clé `moodlesync` du front matter, qui reste en tête du fichier (Obsidian en dépend). Pour les fichiers de cours, l'index et `Qualité des textes.md`, c'est `ms.MARQUE` en première ligne, comme les autres notes générées. Sans marque, le fichier est considéré comme édité à la main et conservé.

### 5.10 Synchronisation après un remplacement

Aujourd'hui, MoodleSync ne vérifie pas les fichiers de cours par une empreinte cryptographique. Il n'y a pas de chaîne de vérification au sens fort, ni de contrôle d'intégrité contre Moodle. Le seul SHA-256 vérifié est celui des mises à jour de l'application (`maj.py`), et remplacer un PDF de cours n'y touche pas. Le mode `remplacer` ajoute un `sha256:` du fichier entier, mais seulement pour les PDF qu'il génère : il sert à les reconnaître et à vérifier une restauration, pas à contrôler les fichiers natifs.

La synchronisation repose sur trois heuristiques :

1. le chemin exact attendu existe : le fichier est considéré comme présent, sans comparer sa taille ;
2. sinon, même nom ailleurs dans le cours : présent seulement si la taille locale égale la taille annoncée par Moodle ;
3. sinon, même contenu sous un autre nom : même taille et même SHA-1 des 256 premiers kilo-octets (`moteur.empreinte`, qui ne change pas).

L'état `.moodlesync.json` stocke, par URL Moodle, le `timemodified` de la version locale et le chemin relatif. Aujourd'hui, il ne stocke ni taille ni empreinte du fichier local.

Un PDF cherchable a un contenu différent, souvent plus lourd, et parfois un chemin différent. Remplacer les octets sans enrichir l'état casse donc plusieurs choses.

| Risque | Cause | Conséquence |
|---|---|---|
| Fichier déplacé ou renommé non reconnu | la taille locale ne correspond plus à celle de Moodle | retéléchargement de l'original, doublon |
| PDF cherchable ignoré par Ma semaine | `pdf_range` exige `taille locale == taille Moodle` | comptage des pages par un téléchargement temporaire, alors que le fichier est local |
| Doublon de contenu | la taille et le SHA-1 des 256 premiers Ko (`moteur.empreinte`, l'empreinte de l'index existant) du PDF cherchable diffèrent de ceux de l'original | le même document publié sous deux noms n'est plus reconnu comme identique ; d'où l'identité source en `sha256:` du fichier entier (D2) |
| Ancien PDF cherchable laissé à côté du nouveau | republication : `telecharger` renomme le fichier local en « ancienne version » | deux PDF dans le dossier, dont un généré |
| Remplacement partiel | coupure, disque plein, fichier verrouillé par Acrobat ou OneDrive | état pointant vers un PDF incomplet, impossible à distinguer sans empreinte |
| Perte de `.moodlesync.json` | réinstallation, dossier déplacé, état corrompu | un PDF cherchable déplacé n'est plus reconnu |
| Faux sentiment de sécurité | l'interface dit « déjà présent » | l'utilisateur croit à une vérification d'intégrité qui n'existe pas |

**La logique sans copie de l'original**

Le PDF cherchable est la seule copie locale. Il contient les pages d'origine. On ne peut donc pas reconnaître un fichier déplacé en comparant sa taille à celle de Moodle. On le reconnaît par sa propre identité, enregistrée au moment de la génération.

L'état stocke deux identités distinctes :

- l'identité de la source Moodle : `taille_source`, `empreinte_source` ;
- l'identité du PDF cherchable : `taille_fichier`, `empreinte_fichier`.

La première sert à détecter une republication et à reconnaître le même document publié sous un autre nom. La seconde sert à retrouver le PDF cherchable après un déplacement ou un renommage, sans original local.

**Corrections obligatoires avant d'activer `remplacer`**

1. **Marquer le PDF généré dans `.moodlesync.json`.** L'entrée garde `t` et `chemin`, et ajoute un objet `genere` :

   ```json
   {
     "t": 1760000000,
     "chemin": "Cours A/Section 1/article.pdf",
     "genere": {
       "type": "pdf_cherchable",
       "taille_source": 18000000,
       "empreinte_source": "sha256:...",
       "taille_fichier": 18300000,
       "empreinte_fichier": "sha256:...",
       "pages": 24,
       "date": "2026-11-07T18:30:00",
       "version": 1
     }
   }
   ```

   Le `t` reste celui de Moodle : ajouter une couche de texte ne change pas la version du document.

2. **Adapter `deja_present`.** Le chemin exact reste accepté. Si l'état pointe vers un PDF cherchable qui n'est plus à son chemin, le fichier est retrouvé par `taille_fichier` et `empreinte_fichier` dans `par_taille`, qui indexe déjà tous les fichiers du dossier (le `sha256:` du fichier entier n'est calculé que sur les candidats de même taille). Cela couvre un déplacement et un renommage, sans comparer à la taille Moodle.

   L'ordre de recherche devient :

   1. le chemin exact attendu existe ;
   2. le chemin enregistré dans l'état existe ;
   3. un fichier du même cours a la taille et l'empreinte du PDF cherchable ;
   4. un PDF du même cours porte les métadonnées Moodle de ce fichier ;
   5. pour un fichier natif, même nom et même taille que Moodle ;
   6. sinon, télécharger.

   L'étape 5 ne s'applique jamais à un PDF cherchable : sa taille locale n'est pas celle de Moodle. C'est ce qui évite de le confondre avec un autre fichier du même nom.

3. **Ajouter un secours dans le PDF.** Le PDF cherchable porte dans ses métadonnées l'URL Moodle sans jeton, le `timemodified`, `taille_source`, `empreinte_source` et le nombre de pages. Si `.moodlesync.json` est perdu, `deja_present` peut lire cette marque pour reconnaître un PDF cherchable déplacé. Le fichier reste identifiable même sans l'état.

4. **Dédupliquer par l'identité source.** Quand un PDF Moodle est téléchargé et qu'un autre fichier du même cours a déjà été transformé avec la même `taille_source` et la même `empreinte_source`, la synchronisation pointe vers ce PDF cherchable au lieu de créer une seconde copie. Le cas « même document sous deux noms » reste couvert.

5. **Adapter `pdf_range`.** Si l'état porte `genere`, si le `t` correspond et si la taille locale égale `genere.taille_fichier`, le fichier local est utilisé sans comparer à la taille Moodle. Sinon, repli sur le téléchargement temporaire actuel.

6. **Traiter la republication.** Télécharger le nouveau fichier dans `.part`, comparer `taille_source` et `empreinte_source`. Si le contenu est identique, seul le `timemodified` change : le `.part` est supprimé et le PDF cherchable est conservé. Si le contenu est différent, le nouveau PDF remplace l'ancien PDF cherchable au même chemin, `genere` est retiré de l'état, et le document est remis en file. Le PDF généré n'est jamais renommé « ancienne version ». Seul le `.md` peut être conservé comme ancienne version, parce qu'il est petit. En mode `remplacer`, la reconstruction complète est interdite : seule la superposition est utilisée, et un échec de superposition laisse l'original en place.

7. **Restaurer sans copie locale.** `ocr_pdf_restaurer` retélécharge l'original depuis Moodle dans un fichier temporaire, vérifie `taille_source` et `empreinte_source`, puis remplace le PDF cherchable. Si le réseau manque, si le jeton a expiré ou si le cours est fermé, il l'explique clairement. Si le PDF cherchable a été modifié manuellement, il demande confirmation avant de l'écraser. Aucun dossier `Originaux/` n'est créé.

8. **Exclure `Textes/` et `.moodlesync-ocr/` de `index_existant`.** Ces dossiers ne doivent jamais participer à la déduplication. Les dossiers cachés et les `.part` restent exclus comme aujourd'hui. Une seule constante doit porter cette liste.

9. **Sérialiser extraction et synchronisation.** Les deux ne tournent jamais en même temps. Le remplacement attend la fin de la page en cours, et la synchronisation attend la fin du remplacement. Sous Windows, un fichier ouvert dans Acrobat peut être verrouillé : nouvel essai, puis message clair, sans perte.

10. **Distinguer les libellés.** Dans le journal et dans Mes textes, « déjà présent » ne doit pas être affiché pour un PDF cherchable. Le badge **PDF cherchable** et la mention « généré par MoodleSync » suffisent.

11. **Accepter la compatibilité descendante.** Une ancienne version de MoodleSync ignore `genere`. Le chemin exact fonctionne encore, donc elle ne retélécharge pas le PDF à sa place. Un fichier déplacé peut en revanche être retéléchargé. C'est documenté, pas silencieux.

**Règle de sûreté**

En cas de doute, MoodleSync retélécharge plutôt que de masquer un fichier. Un doublon temporaire est moins grave qu'un fichier manquant. Avec les deux identités et la marque dans le PDF, ce doute devient rare.

Sans ces règles, le mode `remplacer` introduit des doublons et des téléchargements inutiles, même si le PDF reste lisible. Avec elles, la synchronisation continue de considérer le PDF cherchable comme la version locale du fichier Moodle, sans conserver l'original.

---

## 6. Format des fichiers produits

### 6.1 Markdown par document

```markdown
---
source: "Cours A/Section 1/article.pdf"
cours: "Cours A"
section: "Section 1"
pages: 24
extraction: "ocr"
langues: "fra+eng"
confiance: 0.89
moteur: "Tesseract 5.5.3"
genere: "2026-11-07T18:30:00"
moodlesync: "régénéré à chaque passage, supprime cette ligne pour garder le fichier tel quel"
---

# article.pdf

> Source : Cours A / Section 1 / article.pdf
> 24 pages, dont 22 scannées. Confiance moyenne : 0,89.

<!-- page 1 -->

Texte de la page 1.

<!-- page 2 -->

Texte de la page 2.

...

## Pages à vérifier

- page 7 : confiance 0,62
- page 19 : aucun texte détecté
```

La clé `moodlesync` est la marque de régénération (D4) : le front matter reste en tête du fichier, et un `.md` qui n'a plus cette clé est considéré comme édité à la main et n'est plus réécrit.

Les commentaires `<!-- page n -->` restent invisibles dans Obsidian, mais sont présents dans le fichier brut et dans le copier-coller du texte. Pour l'IA, le fichier combiné utilise une forme visible.

### 6.2 Markdown combiné par cours

```markdown
# Cours A : texte des documents

Texte extrait localement par MoodleSync. Les citations indiquent la page du PDF, pas la page imprimée.

## Section 1

### article.pdf

[source : Section 1/article.pdf, 24 pages]

[p. 1]

Texte de la page 1.

[p. 2]

Texte de la page 2.
```

Ce fichier de cours porte, comme l'index et `Qualité des textes.md`, la marque `ms.MARQUE` en première ligne (D4).

Ce fichier est celui que l'étudiant colle dans une IA. Il commence par une phrase qui aide le modèle à citer correctement, et les pages sont visibles.

### 6.3 Index

```markdown
# Textes des cours

- Cours A : 12 documents, 340 pages, 1,2 Mo
- Cours B : 8 documents, 210 pages, 0,8 Mo

## Documents à vérifier

- Cours A / Section 2 / photocopie.pdf : confiance 0,64, 3 pages douteuses
```

L'index et `Qualité des textes.md` portent aussi la marque `ms.MARQUE` en première ligne (D4).

### 6.4 JSONL à la demande

Une ligne par page, pour les outils de recherche augmentée :

```json
{"cours":"Cours A","section":"Section 1","fichier":"article.pdf","page":1,"source":"ocr","confiance":0.91,"texte":"..."}
```

Pas de découpage en morceaux de tokens : les outils de RAG le font mieux, et un découpage figé serait à refaire à chaque modèle.

---

## 7. Découpage en lots

### Lot 0 : preuve technique, 0,5 à 1 jour

- installer `pypdfium2` et Pillow dans un environnement de test ;
- rendre une page d'un PDF scanné ;
- lancer Tesseract avec TSV ;
- mesurer le temps et la qualité sur 3 documents réels ;
- vérifier que `pypdfium2` fonctionne sous Windows et macOS avec les versions de Python du projet ;
- vérifier l'absence de console noire ;
- décider du mode de secours si `pypdfium2` manque sur une plateforme.

Critère de sortie : une page scannée produit un texte correct, avec une confiance, en moins de 3 secondes.

### Lot 1 : moteur, 3 à 5 jours

- `moodlesync/ocr.py` ;
- détection de Tesseract et des langues ;
- extraction PDF native et OCR ;
- cache, empreinte, reprise ;
- rendu Markdown par document et par cours ;
- rapport de qualité ;
- tests unitaires ;
- commande de test sans interface, par exemple `python -m moodlesync --ocr --essai`.

Critère de sortie : 10 documents réels, dont des scans et des PDF numériques, sont traités, relancés sans doublon, et le résultat est lisible.

### Lot 2 : interface, 3 à 4 jours

- troisième onglet ;
- carte de préparation dans Mes cours ;
- panneau « À quoi ça sert ? » avec avant/après, trois usages et essai sur une page ;
- boîte de consentement avec durée estimée ;
- progression, pause, annulation, reprise ;
- recherche et copie ;
- export ;
- réglages ;
- accessibilité et thème sombre.

Critère de sortie : un utilisateur qui ne connaît pas l'OCR arrive au texte copié en trois clics après l'installation.

### Lot 3 : robustesse, 2 à 3 jours

- file persistante ;
- parallélisme limité ;
- extraction qui cède à la synchronisation (priorité de la synchronisation, D1), puis reprend ;
- batterie faible ;
- fichiers verrouillés, protégés, corrompus ;
- versions et fichiers déplacés ;
- sorties éditées à la main ;
- paquet portable Windows (hors de la 2.5, prévu pour la 2.6, D6) ;
- tests sur une machine sans Python.

Critère de sortie : fermer l'application au milieu d'un document ne perd rien, et la reprise continue au bon endroit.

### Lot 4 : finition et diffusion, 1 à 2 jours

- `MoodleSync.spec`, `requirements.txt` ;
- README, LISEZ-MOI, notes de version, CONTEXTE ;
- `docs/TIERS.md` ;
- captures d'écran ;
- CI avec Tesseract facultatif ;
- version 2.5.

Total réaliste : **2 à 3 semaines** à temps partiel, ou **7 à 10 jours** de travail concentré.

---

## 8. Tests et critères d'acceptation

### Tests unitaires

- parsing TSV : lignes, colonnes, confiance, caractères accentués ;
- reconstruction du texte : ordre des lignes, espaces, paragraphes ;
- décision texte natif contre OCR, y compris pages mixtes ;
- calcul de la confiance moyenne ;
- invalidation du cache par empreinte et par réglages ;
- deuxième passage sans travail ;
- fichier déplacé retrouvé par empreinte ;
- fichier republié réextrait et ancienne sortie conservée ;
- sortie éditée à la main non écrasée ;
- reprise après annulation au milieu d'un document ;
- détection de Tesseract avec registre simulé et chemin absent du PATH ;
- langue manquante et repli ;
- PDF protégé, PDF corrompu, page vide ;
- chemin avec espaces, accents, caractères Unicode ;
- taille maximale et fichier ignoré ;
- absence de réseau pendant l'extraction ;
- PDF cherchable en mode `remplacer` : aucun fichier `Originaux/`, fichier cherchable au même chemin, nombre de pages identique, restauration par téléchargement ;
- refus de remplacer un PDF numérique, signé ou protégé ;
- échec de fabrication du PDF cherchable : aucun remplacement, message clair ;
- après remplacement, une synchronisation ne retélécharge pas le PDF et ne le compte pas comme modifié ;
- PDF cherchable déplacé : retrouvé par `genere.taille_fichier` et `genere.empreinte_fichier`, sans retéléchargement ;
- PDF cherchable renommé : retrouvé par l'empreinte du fichier, sans doublon ;
- état `.moodlesync.json` perdu : PDF cherchable déplacé retrouvé par les métadonnées du PDF ;
- `index_existant` ignore `Textes/` et `.moodlesync-ocr/`, même visibles ;
- `pdf_range` lit le PDF cherchable local sans réseau, avec le même nombre de pages ;
- republication avec contenu identique : seul le `timemodified` change, aucun OCR ni remplacement ;
- republication avec contenu différent : nouveau PDF au même chemin, `genere` retiré, aucun ancien PDF cherchable renommé ;
- remplacement interrompu ou fichier verrouillé : original intact, état cohérent, message clair ;
- restauration hors ligne : message clair, PDF cherchable conservé ;
- restauration après modification manuelle du PDF cherchable : avertissement, pas d'écrasement.

### Tests d'intégration

- générer une petite image avec Pillow, la faire passer par le vrai Tesseract, vérifier quelques mots ;
- traiter un PDF numérique et vérifier qu'aucun OCR n'est lancé ;
- traiter un PDF scanné de deux pages et vérifier les marqueurs de page ;
- tester l'annulation avec un faux Tesseract lent.

Les tests d'intégration sont ignorés si Tesseract n'est pas installé, pour ne pas casser la CI de tout le monde. Une tâche CI dédiée installe Tesseract sous Windows et macOS.

### Vérification de l'interface

Le harnais `MOODLESYNC_VERIF` existe déjà. Il faut ajouter à `window.etatVerification()` :

- onglet `textes` ;
- nombre de documents prêts ;
- état de la file ;
- absence d'erreur bloquante.

### Critères d'acceptation

1. Sur une machine où Tesseract est installé mais absent du PATH, MoodleSync le détecte au premier lancement.
2. Sur une machine sans Tesseract, la carte explique la situation et propose d'indiquer l'emplacement du moteur (pas d'installation automatique en 2.5), sans bloquer le reste.
3. Un PDF numérique n'est pas océrisé et produit son texte en moins d'une seconde.
4. Un scan de 20 pages produit un Markdown avec les pages marquées et une confiance.
5. Un deuxième passage ne refait aucun document inchangé.
6. Fermer l'application au milieu d'un document ne perd aucune page déjà faite.
7. La copie du contexte d'un cours produit un texte collable dans une IA, avec les pages.
8. Aucun appel réseau n'est fait pendant l'extraction.
9. Une erreur sur un document n'empêche ni la synchronisation ni les autres documents.
10. Les tests existants passent, et les nouveaux tests couvrent les cas ci-dessus.
11. Un étudiant peut ouvrir « À quoi ça sert ? », comprendre l'avant/après et essayer une page de son propre scan avant de lancer l'extraction. Cet aperçu n'écrit aucun fichier dans `Textes/` et ne met rien en file.
12. En mode `remplacer`, le PDF du cours répond à Ctrl+F dans Acrobat ou Edge, le nombre de pages est inchangé, aucun dossier `Originaux/` n'est créé, et **Restaurer l'original** retélécharge le fichier depuis Moodle.
13. Après un remplacement, une synchronisation ne retélécharge pas le PDF, ne le compte pas comme modifié et ne crée aucun doublon, même si le fichier a été déplacé dans le cours.
14. `Textes/` et `.moodlesync-ocr/` ne participent jamais à la détection des fichiers déjà présents.
15. Une republication ne laisse pas l'ancien PDF cherchable à côté du nouveau : le nouveau PDF remplace l'ancien au même chemin, et seul le `.md` peut être conservé comme ancienne version.
16. Le volume total des PDF n'est pas doublé par l'OCR : aucun original n'est conservé en plus du PDF cherchable.

---

## 9. Risques et décisions

| Risque | Impact | Réponse |
|---|---|---|
| `pypdfium2` indisponible sur une plateforme | pas de rendu PDF | vérifier au lot 0 ; sinon prévoir un secours (API Windows, Poppler embarqué) |
| Tesseract absent du PATH | fonctionnalité invisible | registre, chemins usuels, choix manuel de `tesseract.exe` (paquet portable à partir de la 2.6) |
| Langues réparties entre deux dossiers | OCR en anglais seulement | lire `--list-langs`, choisir le dossier complet, prévenir |
| Premier passage très long | abandon, mauvaise expérience | durée annoncée, pause, reprise, fermeture possible |
| Confiance faible sur les photos | texte inutilisable | badge, rapport, mode de secours, pas de promesse excessive |
| Coffre Obsidian synchronisé | textes envoyés dans le cloud | avertissement, option hors coffre |
| Sorties qui encombrent l'arborescence | confusion | option « seulement les fichiers par cours », nommage clair |
| Fichier de sortie édité à la main | écrasement | marque `moodlesync` dans le front matter (documents) ou `ms.MARQUE` en première ligne (cours, index, qualité), sinon conservation |
| Ancienne version d'un document | doublons | renommage avec date, comme les PDF |
| Licence AGPL de PyMuPDF | incompatible avec MIT | ne pas l'utiliser, même s'il est installé |
| Taille de l'exe | diffusion plus lourde | ne pas embarquer Tesseract, paquet séparé |
| Antivirus et sous-processus | faux positifs | Tesseract est un binaire connu, signé par son éditeur ; pas de code obfusqué |
| macOS non signé | ouverture bloquée | documenter, tester, plus tard notariser |
| Formules et colonnes | qualité médiocre | assumé, signalé, mode de secours |

### Décisions recommandées

1. **Ne pas embarquer Tesseract dans l'exe.** L'exe passe de 28 Mo à plus de 100 Mo, et chaque mise à jour embarquerait le moteur. Un paquet portable téléchargé à la demande, vérifié par empreinte, est plus propre. Il n'est pas livré dans la 2.5 (D6) : la 2.5 se limite à la détection et au choix manuel de `tesseract.exe`, le paquet portable vient avec la 2.6.
2. **Deux sorties : un fichier par document et un fichier par cours.** Le premier sert à Obsidian et à la traçabilité, le second à l'IA.
3. **Pas d'OCR silencieux.** L'extraction est proposée, jamais imposée. Une fois activée (`ocr` et `ocr_apres_sync`), elle démarre seule après une synchronisation, mais seulement quand la fenêtre est ouverte et si le lot compte 50 documents et 500 pages au plus ; au-delà, elle demande une confirmation avec la durée estimée (D7).
4. **Pas de PyMuPDF.** `pypdfium2` pour le rendu, `pypdf` pour le texte.
5. **Pas de suppression.** Les anciennes sorties sont renommées, les orphelines sont listées, jamais effacées sans accord.
6. **Pas de promesse de perfection.** La qualité est affichée, les pages douteuses sont signalées.
7. **Ne pas modifier les PDF d'origine par défaut.** La recherche se fait dans les `.md`. Un mode explicite `remplacer` peut rendre le PDF cherchable à son emplacement habituel, sans conserver de copie de l'original : le PDF cherchable contient les pages, et la restauration se fait par téléchargement depuis Moodle. L'état de synchronisation doit stocker l'identité source et l'identité du fichier généré (`genere`), et les dossiers de sortie doivent être exclus de la déduplication. Le mode par défaut reste `aucun`.

---

## 10. Questions à trancher avant le lot 1

1. **Paquet portable dès la 2.5, ou détection seulement ?**
   Recommandation : détection et guide dans la 2.5, paquet portable Windows dans la 2.6. Cela permet de sortir le moteur plus vite, sans bloquer sur l'hébergement et la signature des binaires.

2. **Nom et emplacement du dossier visible.**
   Recommandation : `Textes/` dans le dossier de rangement, avec une option pour le placer ailleurs. Le nom suit la langue des dossiers (`Textes` en français, `Texts` en anglais).

3. **Périmètre du premier lot.**
   Recommandation : PDF et images seulement. Les `.docx` et `.pptx` sont déjà numériques et viendront ensuite, sans OCR.

4. **Marqueur de page.**
   Recommandation : commentaire `<!-- page n -->` dans le fichier par document, marqueur visible `[p. n]` dans le fichier combiné pour l'IA.

5. **Extraction automatique après synchronisation.**
   Recommandation (retenue, D7) : oui si `ocr` et `ocr_apres_sync` sont actives, la fenêtre ouverte et le lot de 50 documents et 500 pages au plus (au-delà : confirmation avec la durée), mais jamais pendant le mode `--auto` sans fenêtre. Sinon un étudiant verrait son disque travailler à chaque ouverture de session sans comprendre pourquoi.

---

## 11. Ce qu'il ne faut pas casser

- La synchronisation reste la fonction principale et elle a la priorité (D1). L'OCR ne doit jamais la bloquer ni la faire échouer, et il ne la retarde que d'une unité de travail au plus (une page, ou un remplacement de PDF).
- Le dossier de rangement peut être un coffre Obsidian. Les dossiers cachés, `.obsidian`, `.trash` et `.part` restent exclus.
- Aucun fichier source n'est modifié, déplacé ou supprimé, sauf en mode `remplacer` explicitement choisi. Dans ce mode, le PDF cherchable remplace le fichier au même chemin, sans copie locale de l'original, et la restauration se fait par téléchargement depuis Moodle. Dans tous les autres modes, le PDF reste intact.
- Les noms de dossiers existants ne changent pas.
- Le jeton et le profil Chrome restent dans `%LOCALAPPDATA%`.
- L'application fonctionne sans Tesseract, exactement comme avant.
- Les erreurs techniques vont dans `erreurs.txt`, pas dans une fenêtre.
- L'interface reste en français, les dossiers suivent la langue choisie.
