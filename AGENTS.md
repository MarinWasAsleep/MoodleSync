# Regles d'execution pour les agents (MoodleSync)

Ce fichier ne vaut que pour ce depot. Il ne change aucune regle du journal : `docs/ocr-avancement.md` fait foi, et une phrase de ce fichier qui le contredit est un bug a signaler.

## Contexte a charger

- Une tache, une session. Lire le prompt de `docs/prompts/` qui correspond a la tache, puis seulement le pack qu'il cite.
- Ne jamais lire le depot entier. Ne pas explorer pour decouvrir les fichiers : le pack de la tache les nomme.
- Si un fichier du pack manque, l'ecrire dans le journal et s'arreter, plutot que d'aller le chercher ailleurs.
- Ne pas relire un fichier deja lu dans la meme session.

## Outils

- Session bornee : `terminal` et `file` suffisent. Les autres outils coutent des tokens a chaque requete et n'ont pas d'usage ici.
- Une seule configuration par session. Ne pas changer de modele ni de jeu d'outils en cours de route : cela casse le cache et fait repayer tout l'historique.

## Modeles

- S = Claude Sonnet. Ecriture de code critique, contrat, interfaces, messages d'erreur.
- D = DeepSeek v4.1 flash. Revues, taches mecaniques, documentation, tests.
- Une tache a un seul proprietaire. Jamais deux agents sur le meme fichier dans la meme tache.

## Git

- Une branche par tache : `agent/<ID>-<S ou D>`.
- Auteur `MarinWasAsleep`, adresse `180754786+MarinWasAsleep@users.noreply.github.com`, pas de `Co-Authored-By`, pas de mention d'IA.
- Ne commiter que les fichiers de la tache. Jamais `git add -A`, jamais `git add .`, jamais `git commit -a`.
- Pas de push.

## Fins de ligne

- L'arbre de travail porte des CRLF dans les fichiers historiques, faute de `.gitattributes`. Ne pas les normaliser et ne jamais les inclure dans un commit. Un fichier touche par la tache s'ecrit en LF.
- Verifier `git show --stat` apres le commit : il ne doit lister que les fichiers de la tache.

## Budget

- Chaque requete renvoie tout l'historique. Regrouper les lectures et les commandes plutot que de faire un appel par fichier.
- Ne pas lancer une commande de test complete apres chaque modification : la suite en debut et en fin de tache, comme le protocole le demande.
