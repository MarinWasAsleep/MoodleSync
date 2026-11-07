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
