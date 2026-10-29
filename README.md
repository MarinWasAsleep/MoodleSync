# MoodleSync

Tes fichiers Moodle, téléchargés et rangés par cours, par section et par statut de lecture.
Une petite fenêtre Windows, aucune ligne de commande.

Développé pour le Moodle de l'UNIL, à l'usage des étudiants qui veulent retrouver leurs
documents de cours proprement classés sans le faire à la main.

---

## Ce que fait le programme

- **Connexion par SWITCH edu-ID.** Le mot de passe n'est jamais stocké. La fenêtre ouvre
  Chrome, tu te connectes normalement, elle récupère une autorisation temporaire valable
  plusieurs semaines.
- **Liste de tes cours** avec le nombre de fichiers et le volume de chacun, à cocher ou décocher.
- **Téléchargement idempotent.** Un fichier déjà présent n'est pas retéléchargé, même s'il a
  été renommé par l'enseignant : la comparaison porte aussi sur le contenu.
- **Fichiers mis à jour.** Si l'enseignant remplace un document, la nouvelle version est
  téléchargée et l'ancienne est conservée sous un nom explicite (`... (ancienne version 2026-10-29).pdf`).
- **Rangement automatique** dans l'arborescence que tu choisis, avec renommage des dossiers de
  cours et sous-dossiers imbriqués si tu veux.
- **Statuts de lecture en option** : Obligatoire, Complémentaire, Supports de cours, à partir
  des étiquettes de Moodle.
- **Note de nouveautés** : un fichier `Nouveautés Moodle.md` liste ce qui a été ajouté ou
  modifié lors de la synchronisation.
- **Page de liens** : les liens externes déposés par les enseignants (articles, vidéos) sont
  rassemblés dans `Liens Moodle.md`, section par section, puisque ce ne sont pas des fichiers.
- **Journal** et lancement automatique possible à l'ouverture de session.

## Ce que le programme ne fait pas

- Il ne récupère pas les devoirs, forums, quiz et tests : ce ne sont pas des fichiers.
- Il ne suit pas les liens vers des sites externes, il les liste seulement.
- Il ne s'inscrit à aucun cours et ne modifie rien sur Moodle.
- Il ne contourne aucune authentification : il accède à ce à quoi l'étudiant a déjà droit.

## Installation

### Version prête à l'emploi

Télécharge `MoodleSync.exe` dans la page **Releases** de ce dépôt, place-le où tu veux,
et double-clique dessus. Windows affichera un avertissement d'éditeur inconnu, l'exécutable
n'étant pas signé : « Informations complémentaires » puis « Exécuter quand même ».

Prérequis : Windows et Google Chrome installés.

### Depuis le code source

```
python -m pip install selenium sv-ttk
python moodle_sync.py
```

## Utilisation

1. Clique sur **Se connecter à Moodle**, connecte-toi dans Chrome avec SWITCH edu-ID, reviens
   dans la fenêtre. La connexion est détectée toute seule.
2. Choisis le dossier de rangement avec **Changer…**, coche les cours voulus.
3. Clique sur **Télécharger et ranger**.

Au lancement suivant, il ne reste que l'étape 3. Si la session a expiré, le programme le dit
et propose de se reconnecter.

## Rangement produit

```
<dossier choisi>\
    Institutions et régimes politiques\
        Enseignement du 30.10.2026\
            Supports de cours\
                7_Conférence du Prof Raul Magni-Berton.pdf
            Obligatoire\
                S6-Haegel2024-LaSciencepolitique-Chap4-1.pdf
```

La couche `Obligatoire` / `Complémentaire` / `Supports de cours` est optionnelle, décochée par
défaut. Un dossier de cours peut être renommé par double-clic, et une barre oblique inverse
permet d'imbriquer, par exemple `Introduction aux théories économiques\SITE (séminaire)`.

## À propos des statuts

Moodle indique parfois explicitement qu'une lecture est obligatoire ou complémentaire, via des
étiquettes dans les sections. Quand c'est le cas, le programme les respecte.

**Quand ce n'est pas le cas, il devine**, à partir du type de document : diapos, fiches et
consignes en Supports de cours, textes et articles en Obligatoire. Une déduction n'est pas une
consigne de l'enseignant. Seul le syllabus du cours fait foi.

## Données personnelles

Les réglages, le jeton de session et le journal restent sur l'ordinateur, dans
`%LOCALAPPDATA%\MoodleSync`. Rien n'est envoyé ailleurs que vers `moodle.unil.ch`.

Pour tout effacer : supprime ce dossier, ainsi que les fichiers téléchargés.

Aucun jeton, aucun mot de passe et aucun fichier de cours ne doit être publié dans ce dépôt.

## Construire l'exécutable

```
python -m pip install selenium sv-ttk pyinstaller
pyinstaller --noconfirm --clean MoodleSync.spec
```

La recette `MoodleSync.spec` est versionnée, elle embarque Selenium, son gestionnaire de
pilote et le thème `sv-ttk`. Le résultat apparaît dans `dist\`.

## Adapter à une autre université

L'adresse du serveur est la constante `BASE` en tête de `moodle_sync.py`. Il faut aussi que
l'établissement autorise le service mobile Moodle, dont dépend l'obtention du jeton.

## Limites connues

- Windows uniquement. Une version macOS demanderait un second empaquetage.
- Chrome doit être installé, c'est lui qui porte la connexion edu-ID.
- Les noms de sections viennent de Moodle : ils changent d'un cours et d'un enseignant à l'autre.
- Le premier lancement est le plus fragile : antivirus, dossier OneDrive en lecture seule,
  session expirée. Les messages d'erreur sont écrits pour être compris sans être développeur.

## Licence

MIT, voir `LICENSE`. Les documents téléchargés restent la propriété de leurs auteurs et de
l'UNIL : cet outil ne les rediffuse pas, il les range sur ton disque.
