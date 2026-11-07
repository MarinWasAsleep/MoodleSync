# MoodleSync

> **Tes cours Moodle, rangés tout seuls. Et ta semaine, planifiée.**

![Version](https://img.shields.io/badge/version-2.4-blue)
![Licence](https://img.shields.io/badge/licence-MIT-green)
![Plateforme](https://img.shields.io/badge/Windows%20%7C%20macOS-lightgrey)

MoodleSync, c'est une petite application pour étudiants qui fait deux choses, dans une seule fenêtre :

- **📁 Mes cours** : télécharge tes fichiers Moodle et les range par cours, par séance et par statut de lecture. Sans tri à la main, jamais deux fois le même fichier.
- **📅 Ma semaine** : ton planning de lecture : les séances à venir, quoi lire, combien de temps, quand c'est dû, et ta charge face à ton temps libre.

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

Prérequis : Google Chrome. Compilée pour les Mac à puce Apple. La version Mac est compilée et essayée automatiquement à chaque version, mais pas à la main sur un vrai Mac : un retour (ticket) est le bienvenu.

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

Tu coches ce que tu as lu et notes ton temps réel : ta vraie vitesse de lecture s'en déduit.

**Lire en plusieurs fois.** Avec « Ma page », tu notes où tu t'es arrêté (et, si tu veux, le temps de cette séance, à la main ou avec le chrono ▶). Le marque-page te ramène à la bonne page, la barre d'avancement et le temps restant se mettent à jour, et la vitesse se mesure **séance par séance** : seules les séances dont tu as noté le temps y entrent, une page notée sans temps ne fausse donc rien.

Une copie `Ma semaine.md`, lisible dans Obsidian, est écrite si tu le veux.

**Lectures facultatives.** Elles ne comptent pas dans les totaux par défaut. L'option « Compter les lectures facultatives » (Réglages, section Ma semaine) les inclut dans le total des pages et des lectures, la jauge, ta charge et `Ma semaine.md`.

![Onglet Ma semaine](docs/screenshots/ma_semaine.png)

## Données personnelles

Tout reste sur ton ordinateur : réglages, jeton de session, journal et suivi, dans `%LOCALAPPDATA%\MoodleSync` (Windows) ou `~/Library/Application Support/MoodleSync` (macOS).

Le programme n'accède qu'à :

- **ton Moodle**, avec ton jeton, en lecture seule ;
- **youtube.com**, pour le titre des vidéos citées dans les liens (désactivable) ;
- **github.com**, pour savoir si une nouvelle version existe et la télécharger si tu l'acceptes (désactivable) ;
- **l'adresse d'abonnement de ton horaire**, seulement si tu en as collé une ;
- **le pilote du navigateur** (Selenium), téléchargé à la connexion s'il manque.

Aucun jeton, aucun mot de passe et aucun fichier de cours n'est publié dans ce dépôt.

## Mises à jour

MoodleSync cherche une nouvelle version sur la page [Releases](../../releases) de ce dépôt, au démarrage (une requête au plus toutes les 12 h, désactivable dans **Réglages › Mises à jour**) ou quand tu cliques sur **Rechercher**. Quand une version plus récente existe, un bandeau te le dit ; rien ne s'installe sans ton accord.

Au clic sur **Mettre à jour**, le programme :

1. télécharge le fichier de ta plateforme, uniquement depuis des adresses GitHub en HTTPS ;
2. le compare à l'empreinte SHA-256 que GitHub publie pour ce fichier : sans empreinte, ou si elle diffère, rien n'est installé ;
3. remplace l'application et la relance. Tes réglages, ta connexion et ton suivi sont conservés.

Au moindre échec, l'ancienne version reste en place. Sous Windows, l'ancien `.exe` est renommé en `MoodleSync.exe.ancien` puis effacé au lancement suivant. L'application doit se trouver dans un dossier où tu peux écrire ; sinon, ou lancée depuis le code source, le bandeau propose le téléchargement manuel.

Sans fenêtre : `MoodleSync.exe --maj` met à jour (code de sortie 0 : installée, 10 : déjà à jour, 11 : remplacement impossible ici, 12 : pas de fichier vérifiable, 1 : erreur), avec `--relancer` pour redémarrer ensuite. La synchronisation automatique (`--auto`) ne cherche jamais de mise à jour.

Sur Mac, la mise à jour remplace `MoodleSync.app` de la même façon (archive décompressée avec `ditto`). Ce chemin n'a pas été essayé à la main sur un vrai Mac, seulement testé par des tests automatiques sur des dossiers temporaires.

## Construire l'exécutable

```bash
python -m pip install -r requirements-compilation.txt
python -m unittest discover -s tests -t .
pyinstaller --noconfirm --clean MoodleSync.spec
```

Un workflow GitHub compile et essaie le `.exe` (Windows) et le `.app` (macOS) à chaque envoi, et publie une version dès qu'une étiquette `vX.Y` est envoyée.

## Limites

- Les dates de Ma semaine sont lues en **français seulement** : un cours qui les écrit en anglais, ou pas du tout, sera mal daté ou laissé « à dater ».
- Les statuts ne couvrent que ce que l'enseignant a écrit : le reste n'est pas deviné.
- Le Moodle doit **autoriser l'application mobile** (réglage côté administration) : sinon, rien ne peut se connecter.
- Seul le Moodle de l'UNIL a été testé à la main.
- Les durées de lecture sont des **estimations**, sauf à noter tes temps réels.

## Licence

MIT, voir [LICENSE](LICENSE). Les documents téléchargés restent la propriété de leurs auteurs et de ton établissement : cet outil ne les rediffuse pas, il les range sur ton disque.
