# MoodleSync

> **Tes cours Moodle, rangés tout seuls. Et ta semaine, planifiée.**

![Version](https://img.shields.io/badge/version-2.2-blue)
![Licence](https://img.shields.io/badge/licence-MIT-green)
![Plateforme](https://img.shields.io/badge/Windows%20%7C%20macOS-lightgrey)

MoodleSync, c'est une petite application pour étudiants qui fait deux choses, dans une seule fenêtre :

- **📁 Mes cours** — télécharge tes fichiers Moodle et les range par cours, par séance et par statut de lecture. Sans tri à la main, jamais deux fois le même fichier.
- **📅 Ma semaine** — ton planning de lecture : les séances à venir, quoi lire, combien de temps, quand c'est dû, et ta charge face à ton temps libre.

Conçu et testé sur le Moodle de l'UNIL, il fonctionne avec tout Moodle qui autorise l'application mobile.

![Fenêtre principale de MoodleSync](docs/screenshots/bienvenue.png)

---

## Pourquoi c'est pratique

- **Zéro tri manuel.** Les fichiers arrivent déjà rangés, dans les bons dossiers.
- **Rien n'est téléchargé deux fois.** Un fichier déjà là, même renommé par l'enseignant, n'est pas retéléchargé.
- **Les mises à jour sont conservées.** L'ancienne version d'un document est gardée à côté de la nouvelle.
- **Tu vois ce qui est nouveau** avant même de lancer le téléchargement.
- **Ta semaine en un coup d'œil.** Séances, lectures, durées estimées, échéances, et ta charge face à ton temps libre.

## Commencer

### Windows

Télécharge `MoodleSync.exe` dans la page [**Releases**](../../releases), place-le où tu veux, double-clique.

> Au premier lancement, Windows affiche un avertissement d'éditeur inconnu (l'application n'est pas signée) : **Informations complémentaires** puis **Exécuter quand même**.

Prérequis : Windows 10 ou 11. Chrome (sinon Edge) pour la connexion, et le composant Edge WebView2 (présent par défaut).

### macOS

Télécharge `MoodleSync-macOS.zip` (page [**Releases**](../../releases)), décompresse, place `MoodleSync.app` dans **Applications**.

> macOS la bloque au premier lancement (application non signée) : **Réglages Système › Confidentialité et sécurité › Ouvrir quand même**.

Prérequis : Google Chrome. Compilée pour les Mac à puce Apple. La version Mac est une pré-version : compilée et essayée automatiquement, pas encore à la main sur un vrai Mac.

### Depuis le code source

```bash
python -m pip install -r requirements.txt
python -m moodlesync
```

Python 3.12 ou plus récent.

## Utilisation

1. Indique l'adresse de ton Moodle (par exemple `https://moodle.unil.ch`), clique **Se connecter**. Chrome (ou Edge) s'ouvre : connecte-toi comme d'habitude, puis reviens dans la fenêtre. La connexion est détectée toute seule.
2. Choisis le dossier de rangement, la langue des dossiers, puis coche tes cours.
3. Clique **Télécharger et ranger**.

Au lancement suivant, il ne reste que l'étape 3. C'est tout.

## Les deux onglets

### 📁 Mes cours

La partie fichiers : la liste de tes cours (avec le nombre de fichiers et ce qui est nouveau), le téléchargement, le rangement, et les options.

Les statuts de lecture (`Obligatoire`, `Complémentaire`, `Pour aller plus loin`, `Supports de cours`) viennent de ce que l'enseignant a écrit dans Moodle : étiquettes, listes de lectures, noms de dossiers. Sans indication, seuls les supports de cours (diapos, syllabus, consignes) sont reconnus ; le reste reste dans sa séance. En cas de doute, rien n'est deviné.

![Arborescence produite dans l'Explorateur](docs/screenshots/arborescence.png)

### 📅 Ma semaine

Ton planning, lu en direct dans Moodle (en lecture seule) :

- les séances à venir et **quoi lire** avant chacune, avec le nombre de pages et une **durée estimée** ;
- **ta charge** de la semaine, face à ton temps libre (pose tes cours et tes créneaux « Temps libre » dans l'horaire visuel) ;
- les **échéances** de Moodle et celles que tu ajoutes ;
- ce qui a **changé** dans Moodle depuis la dernière fois.

Tu coches ce que tu as lu et notes ton temps réel : ta vraie vitesse de lecture s'en déduit. Une copie `Ma semaine.md`, lisible dans Obsidian, est écrite si tu le veux.

![Onglet Ma semaine](docs/screenshots/ma_semaine.png)

## Données personnelles

Tout reste sur ton ordinateur : réglages, jeton de session, journal et suivi, dans `%LOCALAPPDATA%\MoodleSync` (Windows) ou `~/Library/Application Support/MoodleSync` (macOS).

Le programme n'accède qu'à :

- **ton Moodle**, avec ton jeton, en lecture seule ;
- **youtube.com**, pour le titre des vidéos citées dans les liens (désactivable) ;
- **l'adresse d'abonnement de ton horaire**, seulement si tu en as collé une ;
- **le pilote du navigateur** (Selenium), téléchargé à la connexion s'il manque.

Aucun jeton, aucun mot de passe et aucun fichier de cours n'est publié dans ce dépôt.

## Construire l'exécutable

```bash
python -m pip install -r requirements-compilation.txt
python -m unittest discover -s tests -t .
pyinstaller --noconfirm --clean MoodleSync.spec
```

Un workflow GitHub compile et essaie le `.exe` (Windows) et le `.app` (macOS) à chaque envoi, et crée une pré-version dès qu'une étiquette `vX.Y` est envoyée.

## Limites

- Les dates de Ma semaine sont lues en **français seulement** : un cours qui les écrit en anglais, ou pas du tout, sera mal daté ou laissé « à dater ».
- Les statuts ne couvrent que ce que l'enseignant a écrit : le reste n'est pas deviné.
- Le Moodle doit **autoriser l'application mobile** (réglage côté administration) : sinon, rien ne peut se connecter.
- Seul le Moodle de l'UNIL a été testé à la main.
- Les durées de lecture sont des **estimations**, sauf à noter tes temps réels.

## Licence

MIT, voir [LICENSE](LICENSE). Les documents téléchargés restent la propriété de leurs auteurs et de ton établissement : cet outil ne les rediffuse pas, il les range sur ton disque.
