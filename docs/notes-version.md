## Nouveautés de la 3.0

- **Un onglet « Mes textes » refait.** Trois sous-onglets : « Mes cours » montre ce qui est fait, « Choisir quoi traiter » sert à cocher les documents, « Déposer des fichiers » accueille les PDF qui ne viennent pas de Moodle.
- **Le texte est écrit à côté de ton PDF.** Un fichier de texte par document, `article.pdf.md`, ou `article.pdf.txt` si tu choisis le texte brut dans les réglages (« Format du texte »). Si tu changes de format, l'ancien fichier reste à côté. Le dossier `Textes/` et ses fichiers de synthèse disparaissent.
- **Ton PDF devient cherchable.** Le PDF d'origine est remplacé par une version cherchable : Ctrl+F retrouve le texte, et le texte se copie depuis un lecteur de PDF. Une copie de l'original est gardée, et « Restaurer l'original » la remet en place.
- **Tu choisis une seule fois.** Tu coches, tu lances, c'est fait. Aucun document n'est traité en douce après une synchronisation, et un nouveau fichier attend que tu le coches.
- **Un document abîmé ne casse rien.** Si le texte est trop incertain, vide ou illisible, l'application ne remplace pas ton PDF et te le dit dans l'arborescence (« Non réussi », avec la raison). Ton fichier reste tel quel, et le menu du document propose « Réessayer ».
- **Copier le texte d'un document.** C'est la seule fonction de l'ancien onglet qui reste.
- **Déposer un PDF hors Moodle.** Tu le glisses dans la zone ou tu le choisis, puis tu indiques où ranger le résultat (« Documents déposés » sur le Bureau par défaut). Ton fichier d'origine n'est jamais modifié.
- **Au premier démarrage, l'application range tes anciens textes.** Elle déplace chaque fichier de texte à côté de son PDF, puis supprime le dossier `Textes/` après l'avoir annoncé.

### Si tu mets à jour depuis la 2.x

- Tes anciens textes changent de place une seule fois, au premier démarrage : chaque fichier de texte rejoint son PDF, et le dossier qui les regroupait est supprimé après l'avoir annoncé. Un texte dont le PDF n'existe plus reste où il est, et l'application le dit.
- La recherche d'un mot dans tous tes textes, l'export et l'aperçu d'une page ont disparu avec l'ancien onglet. « Copier le texte » reste, dans le menu de chaque document.
- Les deux réglages du texte ont disparu. Tu ne choisis plus entre garder ton PDF et le rendre cherchable : un PDF scanné que tu coches est remplacé, avec une copie de l'original. Un PDF qui a déjà son texte, ou que tu as posé toi-même dans un dossier de cours, reçoit son texte à côté et n'est pas remplacé. Et plus rien ne se traite tout seul après une synchronisation : c'est toi qui coches ce qui est traité.
- Si tu préfères du texte brut au Markdown, le choix est dans les réglages (« Format du texte »).

### Ce que cette version ne promet pas

- **Le glisser-déposer.** Le glisser-déposer n'a jamais été essayé sur un vrai poste Windows ou macOS. Le bouton « Choisir des fichiers » fait le même travail et marche partout.
- **La place prise par les copies.** Garder une copie de chaque original occupe de la place : autant que les PDF traités. Un bouton des réglages supprime toutes ces copies, et les documents concernés ne se restaurent plus que par Moodle.
- **Les PDF remplacés avant cette version.** Un PDF remplacé avant cette version n'a pas de copie de l'original : sa restauration repasse par Moodle et ne marche que si Moodle propose encore la même version.
- **Le texte en `.txt` si le cache disparaît.** Le texte en `.txt` est laissé tel quel si le cache de reconnaissance disparaît : sans lui, l'application ne peut pas savoir que ce fichier est le sien, et elle n'y touche pas.
- **La fenêtre.** Elle n'a jamais été vue sur Windows ni sur macOS : ni le rendu réel, ni le lecteur d'écran, ni la copie dans un vrai presse-papiers n'ont été mesurés.
- **Ctrl+F dans un lecteur de PDF.** La couche de texte d'un PDF remplacé n'a jamais été essayée dans un lecteur de PDF réel.

## Nouveautés de la 2.5.1

- **Un scan posé de travers est lu à l'endroit.** Un copieur qui couche une page sur la vitre laisse le texte à 90 degrés sans le dire au fichier : le texte était alors reconnu de travers et ressortait en charabia. La préparation remarque maintenant une page dont la lecture est douteuse, réessaie la page tournée dans les trois autres sens, et ne garde une rotation que si elle est à la fois sûre et nettement meilleure. Une page droite reste lue une seule fois, et une page simplement abîmée n'est pas tournée au hasard. Mesuré sur un article de revue scanné couché, page par page : confiance 0,43 avant, 0,92 après, avec le texte français redevenu lisible.
- **Coût de cette relecture.** Une page couchée demande deux reconnaissances au lieu d'une. Sur un document de contrôle mêlant une page blanche, une page de figure, une page de texte natif et trois pages scannées couchées, la préparation appelle le moteur huit fois au lieu de quatorze, et la page blanche comme la page de figure ne coûtent aucun appel.
- **Ce que ça ne promet pas.** Un scan couché dans l'autre sens, une page qui porte deux orientations à la fois et l'aperçu du texte cherché dans un lecteur réel n'ont pas été essayés.

## Nouveautés de la 2.5

- **Un troisième onglet, « Mes textes ».** Le texte des cours scannés, prêt à chercher, copier ou exporter. La préparation se lance depuis une carte dans Ma semaine : elle annonce le nombre de documents, de pages et une durée approximative, puis demande ton accord. Tu peux fermer la fenêtre, mettre en pause ou arrêter, la préparation reprend où elle s'était arrêtée et cède la place à une synchronisation. Après ce premier accord, une synchronisation lancée depuis la fenêtre relance la préparation des nouveaux documents, à condition que le moteur soit présent et que le lot ne dépasse pas 50 documents ni 500 pages ; jamais en mode `--auto`. Une case des réglages coupe ce lancement automatique.
- **Le moteur d'extraction s'installe depuis l'application.** Il n'est pas dans l'exécutable : la carte et les réglages proposent de le télécharger, ou d'indiquer un moteur déjà installé. Le paquet de ton système (Windows : 63 028 791 octets, environ 184 Mo une fois décompressé ; macOS : 13 685 896 octets, environ 33 Mo décompressé) s'installe sans droits d'administrateur, et son empreinte SHA-256, inscrite dans le programme, est vérifiée avant toute décompression. Le téléchargement, la vérification et la décompression des deux paquets ont été mesurés ; le lancement du moteur sous Windows et sous macOS ne l'a pas été. Le moteur du paquet macOS est un exécutable arm64 (Mac à puce Apple), non signé : sur un Mac Intel, l'installation échouera (déduit).
- **Le texte va dans `Textes/`.** Un fichier Markdown par document, avec des marqueurs de page, un fichier `index.md`, un fichier `Qualité des textes.md` et, par cours, `<Cours> - texte des documents.md`. Supprime la ligne `moodlesync` d'un fichier et il n'est plus réécrit.
- **Un mode qui rend tes PDF cherchables.** « Remplacer par une version cherchable » garde tes pages d'origine et ajoute une couche de texte invisible : Ctrl+F trouve le texte, et il se copie dans n'importe quel lecteur de PDF. Il se choisit dans les réglages, par la liste « Version cherchable des PDF ». Ce mode demande un consentement séparé, qui rappelle qu'aucune copie de l'original n'est conservée. Le mode par défaut (« Aucun ») ne touche pas tes PDF.
- **Chercher, copier, exporter.** La recherche donne la page et l'extrait, la copie prend le texte d'un document ou le contexte d'un cours, l'export propose une archive ZIP, une archive avec JSONL ou un Markdown.
- **Ce que ça ne promet pas.** Une page douteuse est signalée (« À vérifier », « Difficile ») et listée plutôt que devinée, les deux seuils de qualité n'ont pas été calibrés sur un corpus réel, et un remplacement est abandonné au moindre écart : ton fichier d'origine reste alors en place, intact. L'original n'est pas conservé, par choix de volume ; la restauration par téléchargement a un bouton « Restaurer l'original » dans le menu « … » d'un PDF cherchable de « Mes textes », et elle ne marche que pour un PDF resté tel que MoodleSync l'avait téléchargé : un PDF modifié à la main avant le premier remplacement est remplacé sans alerte, et sa restauration répondra que Moodle propose une version différente (déduit de la lecture du code).
- **Une limite sous macOS ancien.** Sous macOS 11 et 12, le rendu des PDF est indisponible : la bibliothèque qui dessine les pages demande macOS 13 ou plus, donc la préparation d'un PDF scanné n'y fonctionne pas (lu dans la bibliothèque, jamais essayé sur ces versions).

## Nouveautés de la 2.4

- **Mises à jour intégrées.** MoodleSync cherche une nouvelle version sur GitHub au démarrage (une requête
  au plus toutes les 12 h, désactivable dans Réglages › Mises à jour) et te le dit par un bandeau. Un clic sur
  « Mettre à jour » télécharge le fichier de ta plateforme, le vérifie par son empreinte SHA-256 publiée par
  GitHub, remplace l'application et la relance ; réglages, connexion et suivi sont conservés. Au moindre
  échec, l'ancienne version reste en place. Rien ne s'installe sans ton accord, et sans empreinte vérifiable
  l'installation automatique est refusée (le bandeau propose le téléchargement manuel).
- **`MoodleSync.exe --maj`** fait la même chose sans fenêtre (avec `--relancer` pour redémarrer ensuite).
- **Option « Compter les lectures facultatives »** (Réglages, section Ma semaine). Cochée, les lectures
  facultatives entrent dans le total des pages et des lectures, la jauge, ta charge et `Ma semaine.md`. Le
  total affiche aussi le nombre de lectures faites sur le nombre de lectures.
- La mise à jour sous macOS remplace `MoodleSync.app` ; ce chemin n'a pas été essayé à la main sur un vrai Mac.

## Nouveautés de la 2.3

- **Reprendre une lecture en plusieurs fois.** Sur chaque lecture de Ma semaine, le bouton « Ma page »
  note la page où tu t'es arrêté. La ligne affiche « Arrêtée p. 14 », une barre d'avancement et le
  temps restant ; la jauge de lecture compte aussi les pages déjà lues des lectures en cours. Arrivé à la
  dernière page, la lecture est marquée comme lue. Pour une lecture à pages ciblées (« pp. 225-255 »),
  tu indiques la page de ton exemplaire et seules les pages de la consigne sont comptées.
- **Une vitesse de lecture mesurée par séance.** Un temps global n'a pas de sens pour une lecture
  étalée sur plusieurs jours. Chaque séance enregistre la page d'arrêt et, si tu veux, son temps ;
  la vitesse est calculée sur les seules séances chronométrées (pages parcourues divisées par minutes).
  Une page notée sans temps fait avancer le marque-page sans fausser ta vitesse. L'aperçu de la saisie
  annonce la vitesse de la séance avant l'enregistrement, et une séance invraisemblable est écartée.
- **Chrono facultatif.** Le bouton ▶ lance un chrono qui survit à la fermeture du programme : en notant ta
  page, le temps est déjà rempli (modifiable si tu as fait des pauses).
- **Historique des séances** consultable et corrigeable (suppression d'une séance saisie par erreur).
- **Ma semaine.md** indique la page d'arrêt de chaque lecture (en lecture seule : elle se modifie dans
  la fenêtre).

## Nouveautés de la 2.2

- **Ma semaine n'est plus expérimentale.** Elle s'active toute seule après la connexion et devient
  l'onglet par défaut. L'écran d'accueil est allégé, et une dernière étape invite à la découvrir.
- **Interface clarifiée.** Les onglets s'appellent « Mes cours » et « Ma semaine » ; la synthèse
  de ta charge passe en tête ; les contrôles de diagnostic sont repliés pour laisser la place à
  l'essentiel.

## Nouveautés de la 2.1

- **Planning visuel de l'horaire.** Dans « Horaire des cours », pose tes cours et tes créneaux
  « Temps libre » directement sur une grille de la semaine (poser, glisser, redimensionner,
  déplacer), à la façon d'un agenda. Le fichier .ics reste disponible en option.
- **Créneaux « Temps libre »** avec une fréquence (chaque semaine, 1 semaine sur 2, 1 sur 3,
  mensuel) : ils servent à estimer ton temps de lecture disponible.
- **Synthèse « Ta charge »** : lecture estimée, heures de cours et temps libre, avec une alerte
  douce quand la charge dépasse le temps disponible.
- **Ouvrir les lectures** : clique sur le nom d'une lecture pour ouvrir le fichier déjà
  téléchargé, comme un hub de travail.

## Nouveautés

- **Nouvelle fenêtre.** Une seule fenêtre, deux onglets : « Synchroniser », qui fait tout ce que
  faisait l'ancienne fenêtre, et « Ma semaine ». Thème clair ou sombre, qui suit le système.
- **Ma semaine (désactivé par défaut).** Les séances et les lectures des jours à
  venir, avec une durée estimée, les échéances de Moodle et les tiennes, ce qui a changé dans
  Moodle, et des contrôles de cohérence. Lecture seule sur Moodle. Ses limites sont expliquées
  avant l'activation et dans le README (dates lues en français seulement, lectures parfois
  déduites à tort).
- **Horaire des cours par fichier .ics**, importé ou par abonnement, avec le choix de ton groupe
  quand un cours en a plusieurs.
- **Ma semaine.md** : une copie lisible dans Obsidian, synchronisée dans les deux sens avec la
  fenêtre (cases cochées, temps notés, échéances).
- **Titres YouTube désactivables** : une case des options empêche tout contact avec youtube.com.
- **Statistiques de Selenium désactivées** à la connexion.

## À savoir

- Tes réglages, ta connexion et tes fichiers rangés sont repris tels quels.
- La fenêtre utilise Microsoft Edge WebView2 sous Windows (présent sur Windows 11 et sur Windows 10
  à jour) ; s'il manque, le programme le dit et donne l'adresse pour l'installer.
- Les fichiers déjà rangés ne sont jamais déplacés.
- Les exécutables ne sont pas signés : Windows et macOS afficheront un avertissement au premier
  lancement (voir le README).
- La version Mac est compilée et essayée automatiquement (lancement, connexion HTTPS, ouverture de la fenêtre)
  à chaque version, mais pas à la main sur un vrai Mac : un retour (ticket) est le bienvenu.
