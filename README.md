<div align="center">

<img src="docs/logo.png" alt="" width="96">

# MoodleSync

**Tes cours Moodle, rangés tout seuls. Ta semaine de lecture, planifiée.**

Une petite application gratuite pour étudiants : elle télécharge tes fichiers Moodle, les range, te dit quoi lire et quand, et rend tes PDF scannés cherchables.

[![Dernière version](https://img.shields.io/github/v/release/MarinWasAsleep/MoodleSync?label=version&color=2f7cf6)](../../releases/latest)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-22a06b)](LICENSE)
![Windows et macOS](https://img.shields.io/badge/Windows%20%7C%20macOS-555)
![Gratuit](https://img.shields.io/badge/gratuit-sans%20compte-8a63d2)

[<img src="https://img.shields.io/badge/T%C3%A9l%C3%A9charger%20pour%20Windows-2f7cf6?style=for-the-badge&logo=windows&logoColor=white" alt="Télécharger pour Windows">](https://github.com/MarinWasAsleep/MoodleSync/releases/latest/download/MoodleSync.exe)
&nbsp;
[<img src="https://img.shields.io/badge/T%C3%A9l%C3%A9charger%20pour%20macOS-222?style=for-the-badge&logo=apple&logoColor=white" alt="Télécharger pour macOS">](https://github.com/MarinWasAsleep/MoodleSync/releases/latest/download/MoodleSync-macOS.zip)

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/MarinWasAsleep/MoodleSync/main/docs/screenshots/semaine-dark.png">
  <img src="https://raw.githubusercontent.com/MarinWasAsleep/MoodleSync/main/docs/screenshots/semaine-light.png" alt="Ma semaine : ta charge de lecture, les séances à venir et les échéances" width="900">
</picture>

</div>

---

## ✨ Trois onglets, une seule fenêtre

<table>
<tr>
<td width="33%" valign="top">

### 📁 Mes cours

Tous les fichiers de tes cours, téléchargés et **rangés par cours, par séance et par statut** (obligatoire, complémentaire...). Rien n'est téléchargé deux fois.

</td>
<td width="33%" valign="top">

### 📅 Ma semaine

**Quoi lire, pour quand, et combien de temps.** Ta charge de la semaine face à ton temps libre, les échéances, et un marque-page pour lire en plusieurs fois.

</td>
<td width="33%" valign="top">

### 📄 Mes textes

Le texte de tes cours, **même des PDF scannés** : tu coches, le PDF devient cherchable et son texte s'écrit à côté. Trois sous-onglets, et un dépôt pour les PDF venus d'ailleurs.

</td>
</tr>
</table>

## 💡 Pourquoi c'est pratique

- **Zéro tri à la main.** Les fichiers arrivent déjà dans les bons dossiers.
- **Tu vois ce qui est nouveau** avant même de télécharger.
- **Rien ne se perd.** Quand un enseignant met un document à jour, l'ancienne version est gardée à côté.
- **Ta semaine d'un coup d'œil.** Séances, lectures, durées estimées, échéances.
- **Tout reste sur ton ordinateur.** Pas de compte à créer, pas de serveur, aucun document envoyé ailleurs.

## 🚀 Installer en une minute

| | Windows 10 ou 11 | macOS (M series) |
|---|---|---|
| **1. Télécharger** | [`MoodleSync.exe`](https://github.com/MarinWasAsleep/MoodleSync/releases/latest/download/MoodleSync.exe) | [`MoodleSync-macOS.zip`](https://github.com/MarinWasAsleep/MoodleSync/releases/latest/download/MoodleSync-macOS.zip), puis décompresse |
| **2. Ranger** | où tu veux | `MoodleSync.app` dans **Applications** |
| **3. Ouvrir** | double-clic | double-clic |
| **Premier lancement** | avertissement d'éditeur inconnu (l'application n'est pas signée) : **Informations complémentaires** puis **Exécuter quand même** | macOS la bloque (non signée) : **Réglages Système › Confidentialité et sécurité › Ouvrir quand même** |
| **Il te faut** | Chrome ou Edge | Google Chrome |

> [!NOTE]
> La version Mac est compilée et essayée automatiquement à chaque version, mais jamais à la main sur un vrai Mac. Un retour ([ticket](../../issues)) est le bienvenu.

Ensuite, MoodleSync se met à jour tout seul : un bandeau te prévient quand une nouvelle version sort, et rien ne s'installe sans ton accord.

## 🧭 Utilisation : trois étapes, une seule fois

1. **Connecte-toi.** Indique l'adresse de ton Moodle (par exemple `https://moodle.unil.ch`) et clique **Se connecter**. Ton navigateur s'ouvre : connecte-toi comme d'habitude, puis reviens. Ton mot de passe n'est jamais enregistré.
2. **Choisis** le dossier de rangement et coche tes cours.
3. Clique **Télécharger et ranger**.

Les fois suivantes, il ne reste que l'étape 3.

> Conçu et testé sur le Moodle de l'UNIL, MoodleSync fonctionne avec tout Moodle qui autorise l'application mobile Moodle.

## 📸 En images

<details open>
<summary><b>📁 Mes cours</b> : tes cours, le nombre de fichiers, ce qui est nouveau</summary>
<br>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/MarinWasAsleep/MoodleSync/main/docs/screenshots/cours-dark.png">
  <img src="https://raw.githubusercontent.com/MarinWasAsleep/MoodleSync/main/docs/screenshots/cours-light.png" alt="Onglet Mes cours">
</picture>

Et le résultat dans ton explorateur de fichiers :

<img src="docs/screenshots/arborescence.png" alt="Dossiers rangés par cours et par séance" width="600">
</details>

<details open>
<summary><b>📅 Ma semaine</b> : chaque séance, quoi lire avant, combien de temps</summary>
<br>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/MarinWasAsleep/MoodleSync/main/docs/screenshots/lectures-dark.png">
  <img src="https://raw.githubusercontent.com/MarinWasAsleep/MoodleSync/main/docs/screenshots/lectures-light.png" alt="Les lectures de la semaine, avec leur statut et le bouton Ma page">
</picture>
</details>

<details>
<summary><b>🗓️ Ton horaire</b> : pose tes cours et ton temps libre sur une grille</summary>
<br>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/MarinWasAsleep/MoodleSync/main/docs/screenshots/horaire-dark.png">
  <img src="https://raw.githubusercontent.com/MarinWasAsleep/MoodleSync/main/docs/screenshots/horaire-light.png" alt="Grille de l'horaire des cours et des créneaux de temps libre">
</picture>
</details>

## 🆕 Quoi de neuf

- **3.0** : l'onglet **Mes textes** refait. Trois sous-onglets, le texte écrit à côté de chaque PDF (Markdown ou texte brut), les PDF que tu coches rendus cherchables avec une copie de l'original, et un dépôt pour les PDF qui ne viennent pas de Moodle.
- **2.5.1** : un PDF scanné posé de travers sur la vitre du copieur est maintenant lu à l'endroit, au lieu de ressortir en charabia.
- **2.5** : le nouvel onglet **Mes textes**, avec le texte de tes PDF scannés.
- **2.4** : les mises à jour s'installent depuis l'application.
- **2.3** : lire en plusieurs fois, avec un marque-page et ta vraie vitesse de lecture.

Tout le détail : [notes de version](docs/notes-version.md).

## 🔒 Tes données restent chez toi

Réglages, connexion et suivi restent sur ton ordinateur, dans `%LOCALAPPDATA%\MoodleSync` (Windows) ou `~/Library/Application Support/MoodleSync` (macOS). MoodleSync ne contacte que :

- **ton Moodle**, en lecture seule ;
- **github.com**, pour les mises à jour et, si tu le demandes, le moteur d'extraction du texte ;
- **youtube.com**, pour le titre des vidéos citées dans tes cours (désactivable) ;
- **l'adresse de ton horaire**, seulement si tu en as collé une ;
- **le pilote du navigateur** (Selenium), téléchargé à la connexion s'il manque.

Aucun document n'est envoyé à une IA ni à un serveur tiers.

## ❓ Questions fréquentes

<details>
<summary><b>Est-ce que ça marche avec mon université ?</b></summary>

Avec tout Moodle qui autorise l'application mobile Moodle (un réglage de l'administration). Seul le Moodle de l'UNIL a été essayé à la main. Les dates de Ma semaine sont lues en français seulement : un cours qui les écrit en anglais, ou pas du tout, sera mal daté ou laissé « à dater ».
</details>

<details>
<summary><b>Comment MoodleSync sait-il ce qui est obligatoire ?</b></summary>

Il lit ce que l'enseignant a écrit dans Moodle : étiquettes, listes de lectures, noms de dossiers. Sans indication, seuls les supports de cours (diapos, syllabus, consignes) sont reconnus, et le reste reste dans sa séance. En cas de doute, rien n'est deviné.
</details>

<details>
<summary><b>Les durées de lecture sont-elles fiables ?</b></summary>

Ce sont des estimations. Coche ce que tu as lu et note ton temps (à la main ou avec le chrono ▶) : ta vraie vitesse s'en déduit, séance par séance. Les lectures facultatives ne comptent pas dans les totaux, sauf si tu coches « Compter les lectures facultatives » dans les réglages.
</details>

<details>
<summary><b>Je peux utiliser Ma semaine dans Obsidian ?</b></summary>

Oui : MoodleSync peut écrire une copie `Ma semaine.md`, lisible dans Obsidian.
</details>

<details>
<summary><b>Est-ce que ça modifie mes PDF ?</b></summary>

Seulement ceux que tu coches dans « Mes textes ». Un PDF choisi est remplacé par une version cherchable, et une copie de l'original est gardée pour que « Restaurer l'original » puisse la remettre en place. Tes autres PDF ne sont pas touchés, et un PDF que tu déposes depuis ton ordinateur n'est jamais modifié à sa source.
</details>

## 📚 Pour aller plus loin

<details>
<summary><b>Le texte de tes cours : ce que ça fait, et ce que ça ne fait pas</b></summary>

Un PDF scanné ne contient que des images : pas de Ctrl+F, pas de copier-coller. MoodleSync en extrait le texte sur ton ordinateur, avec un moteur d'extraction qui n'est pas embarqué dans l'application.

**Comment ça se passe**

1. Ouvre « Mes textes », puis « Choisir quoi traiter » : tu coches des documents, ou un cours entier, et tu cliques « Traiter la sélection ». Un document déjà traité n'est pas refait, sauf si tu le coches de nouveau.
2. Avant de lancer, la fenêtre annonce le nombre de documents, de pages et une durée approximative (au moins quinze secondes par page), et combien de PDF seront remplacés. Tu peux fermer la fenêtre, mettre en pause ou arrêter ; le travail reprend là où il s'était arrêté.
3. Le moteur s'installe depuis l'application, sans droits d'administrateur : 63 028 791 octets pour Windows (environ 184 Mo décompressé, 183 666 757 octets) et 13 685 896 octets pour macOS (environ 33 Mo décompressé, 33 065 769 octets). Son empreinte SHA-256, inscrite dans le programme, est vérifiée avant toute décompression. Sur un autre système, tu peux indiquer un moteur installé à la main.
4. Les résultats sont dans « Mes cours » : une arborescence par cours et par section, un badge par document (« Traité », « À vérifier », « Non réussi »), et le menu d'un document pour l'ouvrir, montrer son dossier, copier son texte ou restaurer l'original.

**Déposer un PDF venu d'ailleurs**

Le sous-onglet « Déposer des fichiers » accueille les PDF qui ne viennent pas de Moodle : tu les glisses dans la zone ou tu les choisis avec le bouton, et les résultats sont rangés dans « Documents déposés » sur le Bureau, ou dans le dossier que tu indiques. Ton fichier d'origine n'est jamais modifié.

**Ce que ça produit**

```text
<dossier de rangement>/<Cours>/<Section>/article.pdf        le PDF, remplacé par la version cherchable
<dossier de rangement>/<Cours>/<Section>/article.pdf.md     le texte (ou article.pdf.txt, si tu choisis le texte brut)
```

Un fichier de texte par document, à côté de son PDF, au format choisi dans les réglages : « Markdown (.md) » ou « Texte brut (.txt) ». Un `.md` porte une ligne `moodlesync` : supprime-la et il n'est plus réécrit. Un `.txt` est protégé de la même façon, par une empreinte gardée dans le cache de reconnaissance.

Un PDF qui contient déjà du texte (aucune page scannée) reçoit son texte à côté sans être remplacé : il n'y a rien à rendre cherchable. Même chose pour un PDF posé à la main dans un dossier de cours, que MoodleSync ne suit pas : il gagne son texte, et rien d'autre n'est touché.

**Les copies d'originaux**

Chaque PDF de tes cours remplacé laisse une copie de son original, dans un dossier caché à la racine du dossier de rangement. Ces copies occupent de la place, autant que les PDF traités. Les réglages affichent leur nombre et leur volume, avec le bouton « Supprimer les copies ».

**Retrouver l'original**

Le menu d'un PDF remplacé propose « Restaurer l'original » : la copie gardée sur ton ordinateur est remise en place, et le texte à côté est supprimé, sauf si tu l'avais modifié à la main. Un PDF remplacé avant cette version n'a pas de copie de l'original : sa restauration repasse par Moodle et ne marche que si Moodle propose encore la même version.

**À lire avant**

- **Une page douteuse est signalée, jamais inventée.** Un document reçoit « Traité », « À vérifier » ou « Non réussi ». Les deux seuils qui décident de ces mots n'ont pas été calibrés sur un corpus réel : le badge dit qu'il faut vérifier, il ne dit pas que le texte est juste.
- **Un remplacement est abandonné au moindre écart.** Avant de rendre un PDF cherchable, MoodleSync compare le résultat à l'original : même nombre de pages, mêmes dimensions et rotations, mêmes annotations, liens et signets, texte extractible, fichier réouvrable, rendu identique sur trois pages échantillonnées. Un seul contrôle qui échoue arrête l'opération et ton fichier d'origine reste en place. Une différence sur une page non échantillonnée échappe à ces contrôles.
- **Un document qui échoue ne laisse rien.** Si le texte est trop incertain, vide ou illisible, aucun fichier de texte n'est écrit, le PDF n'est pas remplacé, et l'arborescence dit « Non réussi » avec la raison. Le menu du document propose « Réessayer ».
- **Rien ne se traite sans toi.** Aucun document n'est préparé après une synchronisation : tu coches ce qui est traité, une fois.
- **Sous macOS 11 et 12, la préparation d'un PDF scanné n'est probablement pas disponible** : la bibliothèque qui rend les pages demande macOS 13 ou plus (lu dans la bibliothèque, déduit : jamais essayé sur ces versions).
- **Le moteur du paquet macOS n'a jamais été lancé sur un Mac.** C'est un exécutable pour Mac à puce Apple (arm64), non signé : sur un Mac Intel, l'installation échouera (déduit).
</details>

<details>
<summary><b>Les mises à jour en détail</b></summary>

MoodleSync cherche une nouvelle version sur la page [Releases](../../releases) au démarrage (une requête au plus toutes les 12 h, désactivable dans **Réglages › Mises à jour**) ou quand tu cliques sur **Rechercher**. Au clic sur **Mettre à jour**, le programme :

1. télécharge le fichier de ta plateforme, uniquement depuis des adresses GitHub en HTTPS ;
2. le compare à l'empreinte SHA-256 que GitHub publie pour ce fichier : sans empreinte, ou si elle diffère, rien n'est installé ;
3. remplace l'application et la relance. Tes réglages, ta connexion et ton suivi sont conservés.

Au moindre échec, l'ancienne version reste en place. Sous Windows, l'ancien `.exe` est renommé en `MoodleSync.exe.ancien` puis effacé au lancement suivant. L'application doit se trouver dans un dossier où tu peux écrire ; sinon, ou lancée depuis le code source, le bandeau propose le téléchargement manuel.

Sans fenêtre : `MoodleSync.exe --maj` met à jour (code de sortie 0 : installée, 10 : déjà à jour, 11 : remplacement impossible ici, 12 : pas de fichier vérifiable, 1 : erreur), avec `--relancer` pour redémarrer ensuite. La synchronisation automatique (`--auto`) ne cherche jamais de mise à jour.

Sur Mac, la mise à jour remplace `MoodleSync.app` (archive décompressée avec `ditto`). Ce chemin n'a pas été essayé à la main sur un vrai Mac, seulement par des tests automatiques sur des dossiers temporaires.
</details>

<details>
<summary><b>Lancer depuis le code source, compiler</b></summary>

Python 3.12 ou plus récent.

```bash
python -m pip install -r requirements.txt
python -m moodlesync
```

Construire l'exécutable :

```bash
python -m pip install -r requirements-compilation.txt
python -m unittest discover -s tests -t .
pyinstaller --noconfirm --clean MoodleSync.spec
```

Un workflow GitHub compile et essaie le `.exe` (Windows) et le `.app` (macOS) à chaque envoi, et publie une version dès qu'une étiquette `vX.Y` est envoyée. Pour contribuer : [CONTRIBUTING.md](CONTRIBUTING.md).
</details>

<details>
<summary><b>Limites connues</b></summary>

- Les dates de Ma semaine sont lues en **français seulement**.
- Les statuts ne couvrent que ce que l'enseignant a écrit : le reste n'est pas deviné.
- Le Moodle doit **autoriser l'application mobile** : sinon, rien ne peut se connecter.
- Seul le Moodle de l'UNIL a été testé à la main.
- Les durées de lecture sont des **estimations**, sauf à noter tes temps réels.
- La préparation du texte demande un **moteur d'extraction installé à part** (téléchargé depuis l'application). Le paquet macOS ne contient qu'un moteur arm64 non signé, jamais lancé sur un Mac.
- **Sous macOS 11 et 12**, la préparation d'un PDF scanné est indisponible (lu dans la bibliothèque, jamais essayé).
- La qualité du texte reconnu est signalée par un badge, **sans garantie** : un document noté « Traité » peut contenir des erreurs.
- Le **glisser-déposer** des fichiers n'a jamais été essayé sur un vrai poste Windows ou macOS : le bouton « Choisir des fichiers » fait le même travail et marche partout.
- Garder une **copie de chaque original** occupe de la place, autant que les PDF traités ; un bouton des réglages les supprime, et la restauration repasse alors par Moodle.
- La fenêtre **n'a jamais été vue sur Windows ni sur macOS** : ni rendu réel, ni lecteur d'écran, ni Ctrl+F dans un lecteur de PDF n'ont été essayés.
</details>

## 📄 Licence

MIT, voir [LICENSE](LICENSE). Les documents téléchargés restent la propriété de leurs auteurs et de ton établissement : MoodleSync ne les rediffuse pas, il les range sur ton disque.

<div align="center">
<br>
<sub>Fait par un étudiant de l'UNIL, pour les étudiants. Un bug, une idée ? <a href="../../issues">Ouvre un ticket</a>.</sub>
</div>
