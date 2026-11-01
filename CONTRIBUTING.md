# Contribuer à MoodleSync

MoodleSync est un logiciel libre (licence MIT), écrit par un étudiant pour ses propres cours puis
partagé. Il est maintenu sur le temps libre de son auteur : les réponses aux tickets et aux
propositions n'ont pas de délai garanti. Toute aide est la bienvenue, surtout celle de personnes qui
utilisent un autre Moodle que celui de l'UNIL.

## Ce qui aide le plus

1. **Un retour d'usage sur un autre Moodle.** Le programme n'a été testé que sur le Moodle de l'UNIL.
   Si tu l'essaies ailleurs, ouvre un ticket (*issue*) pour dire ce qui marche et ce qui casse :
   version de Moodle, méthode de connexion de ton établissement, message d'erreur lu dans la
   fenêtre ou dans le journal.
2. **Un cas de classement qui échoue.** Les statuts de lecture (obligatoire, complémentaire...)
   dépendent de la façon dont chaque enseignant écrit ses sections. Un exemple suffit : le titre
   de la section, la façon dont la liste de lectures est écrite, et le statut attendu. Recopie les
   textes à la main, sans noms de fichiers privés ni données personnelles.
3. **Des mots-clés ou des formulations d'une autre langue.** Les intitulés reconnus sont définis dans
   le dictionnaire `LANGUES` de `moodlesync/moteur.py` (français et anglais pour l'instant). Ma semaine
   ne lit les dates qu'en français (`moodlesync/seances.py`) : des exemples réels de titres de
   séances dans une autre langue aideraient à l'étendre.
4. **Des corrections de texte et de documentation** : README, messages d'erreur, `docs/LISEZ-MOI.txt`.

## Avant d'écrire du code

Ouvre d'abord un ticket pour décrire ce que tu veux changer. Cela évite un travail qui ne rentrerait
pas dans le projet. Pour une petite correction évidente (faute, message d'erreur), une proposition
de modification (*pull request*) directe convient.

## Principes à respecter

Ce sont des choix assumés. Une modification qui les contredit sera refusée, ou discutée d'abord.

- **Lecture seule sur Moodle.** Le programme ne modifie rien sur Moodle et accède seulement à ce
  à quoi l'étudiant a déjà droit.
- **Ne jamais écraser ni supprimer un fichier de l'utilisateur.** Un fichier remplacé par l'enseignant
  est téléchargé à côté, et l'ancienne version est conservée sous un nom daté.
- **Annoncer ce qui est déduit.** Quand le programme ne lit pas une information chez l'enseignant et
  qu'il la devine (par exemple un support de cours reconnu à son nom), il le dit, dans le journal et
  dans les notes produites. Un statut d'obligation (obligatoire, complémentaire) ne se devine jamais
  sans être signalé comme tel.
- **Rien ne sort de l'ordinateur.** Le jeton, les réglages et le journal restent en local. Tout
  nouvel accès réseau, y compris vers un service public, doit être justifié dans le ticket,
  documenté dans la section « Données personnelles » du README, et désactivable.
- **Des messages lisibles par quelqu'un qui n'est pas développeur.** En français, sans trace d'erreur
  brute dans la fenêtre.

## Données personnelles : à ne jamais publier

N'ajoute jamais à un ticket, à une proposition ou à un fichier du dépôt :

- le jeton de session, `config.json`, `.moodlesync.json`, le journal ou `erreurs.txt` tels quels (ils
  peuvent contenir des noms de cours et de fichiers) ;
- ton fichier d'horaire `.ics` ou son adresse d'abonnement (ils contiennent ton emploi du temps, et
  l'adresse peut contenir un code personnel) ;
- des documents de cours : ils appartiennent à leurs auteurs et à l'établissement ;
- des captures d'écran qui montrent ton nom, ton adresse ou des cours privés.

Si tu as le moindre doute, anonymise avant de publier.

## Environnement de développement

```
python -m pip install -r requirements.txt
python -m moodlesync
```

Python 3.12 ou plus récent. Le code est dans le paquet `moodlesync/` : `moteur.py` (connexion, API
Moodle, téléchargement et rangement), `seances.py`, `semaine.py`, `suivi.py`, `horaire.py` et
`ics.py` (Ma semaine), `application.py` et `interface/` (la fenêtre, en HTML, affichée par
pywebview). Pour construire l'exécutable : voir « Construire l'exécutable » dans le README. Le
workflow `.github/workflows/compilation.yml` lance les tests, compile et essaie l'exécutable Windows
et l'application macOS à chaque envoi.

## Vérifications

```
python -m unittest discover -s tests -t .
```

Les tests sont hors ligne : ils ne contactent ni Moodle ni aucun autre service, et redirigent les
réglages vers un dossier temporaire. Une modification doit garder la suite au vert et ajouter des
tests pour ce qu'elle change. Pour une modification des règles de classement ou de lecture des
dates, indique en plus un exemple concret (avant et après, avec le titre de la section et les noms
de fichiers anonymisés) et le Moodle sur lequel tu l'as essayée. Pour une modification de
l'interface, joins une capture d'écran, sous Windows ou sur Mac.

## Style

- Python simple, sans dépendance de plus sans raison. Une dépendance nouvelle se discute dans un
  ticket : elle alourdit l'exécutable et la chaîne de compilation. Les versions sont figées dans
  `requirements.txt`.
- L'interface ne charge aucune ressource externe (ni police, ni script en ligne) et doit marcher
  dans WebView2 (Windows) comme dans WebKit (Safari 16 et plus, macOS).
- Commentaires et messages en français. Pas de tirets longs dans les textes.
- Les fonctions courtes et nommées par ce qu'elles font valent mieux qu'un long commentaire.

## Signaler une faille de sécurité

Ouvre un ticket en disant seulement qu'une faille existe, **sans en donner les détails** : ils seront
échangés en privé. Ne publie jamais de jeton valide.

## Licence

En proposant une modification, tu acceptes qu'elle soit publiée sous licence MIT, comme le reste du
projet (voir `LICENSE`).
