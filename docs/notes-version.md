## Nouveautés de la 2.5

- **Un troisième onglet, « Mes textes ».** Le texte des cours scannés, prêt à chercher, copier ou exporter. La préparation se lance depuis une carte dans Ma semaine : elle annonce le nombre de documents, de pages et une durée approximative, puis demande ton accord. Tu peux fermer la fenêtre, mettre en pause ou arrêter, la préparation reprend où elle s'était arrêtée et cède la place à une synchronisation. Après ce premier accord, une synchronisation lancée depuis la fenêtre relance la préparation des nouveaux documents, à condition que le moteur soit présent et que le lot ne dépasse pas 50 documents ni 500 pages ; jamais en mode `--auto`. Une case des réglages coupe ce lancement automatique.
- **Le moteur d'extraction s'installe depuis l'application.** Il n'est pas dans l'exécutable : la carte et les réglages proposent de le télécharger, ou d'indiquer un moteur déjà installé. Le paquet de ton système (Windows : 63 028 791 octets, environ 184 Mo une fois décompressé ; macOS : 13 685 896 octets, environ 33 Mo décompressé) s'installe sans droits d'administrateur, et son empreinte SHA-256, inscrite dans le programme, est vérifiée avant toute décompression. Le téléchargement, la vérification et la décompression des deux paquets ont été mesurés ; le lancement du moteur sous Windows et sous macOS ne l'a pas été. Le moteur du paquet macOS est un exécutable arm64 (Mac à puce Apple), non signé : sur un Mac Intel, l'installation échouera (déduit).
- **Le texte va dans `Textes/`.** Un fichier Markdown par document, avec des marqueurs de page, un fichier `index.md`, un fichier `Qualité des textes.md` et, par cours, `<Cours> - texte des documents.md`. Supprime la ligne `moodlesync` d'un fichier et il n'est plus réécrit.
- **Un mode qui rend tes PDF cherchables.** « Remplacer par une version cherchable » garde tes pages d'origine et ajoute une couche de texte invisible : Ctrl+F trouve le texte, et il se copie dans n'importe quel lecteur de PDF. Il se choisit dans les réglages, par la liste « Version cherchable des PDF ». Ce mode demande un consentement séparé, qui rappelle qu'aucune copie de l'original n'est conservée. Le mode par défaut (« Aucun ») ne touche pas tes PDF.
- **Chercher, copier, exporter.** La recherche donne la page et l'extrait, la copie prend le texte d'un document ou le contexte d'un cours, l'export propose une archive ZIP, une archive avec JSONL ou un Markdown.
- **Ce que ça ne promet pas.** Une page douteuse est signalée (« À vérifier », « Difficile ») et listée plutôt que devinée, les deux seuils de qualité n'ont pas été calibrés sur un corpus réel, et un remplacement est abandonné au moindre écart : ton fichier d'origine reste alors en place, intact. L'original n'est pas conservé, par choix de volume ; la restauration par téléchargement existe dans le programme mais n'a pas encore de bouton dans la fenêtre, et elle ne marche que pour un PDF resté tel que MoodleSync l'avait téléchargé : un PDF modifié à la main avant le premier remplacement est remplacé sans alerte, et sa restauration répondra que Moodle propose une version différente (déduit de la lecture du code). Sous macOS 11 et 12, la bibliothèque qui rend les pages de PDF demande macOS 13 : la préparation d'un PDF scanné n'y est probablement pas disponible (déduit, jamais essayé).

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
