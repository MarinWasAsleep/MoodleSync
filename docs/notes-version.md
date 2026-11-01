**Pré-version.** La version Windows a été essayée à la main ; la version Mac n'a été essayée
qu'automatiquement (lancement, connexion HTTPS, ouverture de la fenêtre sur une machine de GitHub).
Sur Mac, la version 1.3 reste disponible plus bas dans les Releases. Un retour (ticket) est le
bienvenu.

## Nouveautés

- **Nouvelle fenêtre.** Une seule fenêtre, deux onglets : « Synchroniser », qui fait tout ce que
  faisait l'ancienne fenêtre, et « Ma semaine ». Thème clair ou sombre, qui suit le système.
- **Ma semaine (expérimental, désactivé par défaut).** Les séances et les lectures des jours à
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
