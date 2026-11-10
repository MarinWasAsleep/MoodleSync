# Outils de l'orchestrateur

Ce dossier garde ce qui servait aux sessions d'agents et qui vivait sinon dans le cache de la machine, effacé au bout de 24 heures. Il ne fait pas partie du produit : rien ici n'est importé par `moodlesync/`, rien n'est testé par la suite.

## Scripts

| Fichier | Rôle |
|---|---|
| `recree-venv-ms.sh` | Recrée le venv de mesure (`pywebview`, Pillow, pypdf, pypdfium2). À lancer en début de session si `/opt/data/cache/scratch/venv-ms` a été purgé. |
| `verif_langue.py` | Contrôle déterministe d'un diff : cadratins, CRLF, ratio de mots anglais. `--crouton` envoie à Crouton Alpha les seules lignes déjà signalées. |
| `en_lf.py` | Réécrit un fichier en LF sans changer son contenu, pour que le diff d'un fichier historique retombe à ses seules lignes modifiées. |
| `faux_moteur.py` | Faux `tesseract` pour les essais de détection et d'installation, sans installer le vrai moteur. |
| `a2-mutations.py` | Campagne de mutations de la tâche A2, gardée comme exemple de méthode. |
| `assemble_mac.py`, `assemble_mac2.py` | Fabriquent le paquet macOS du moteur : flacons Homebrew, dylib aplaties dans `lib/`, chemins réécrits vers `@loader_path`, zip final. `assemble_mac2.py` est la version utilisée pour la release v1.0.0. |

## Sessions

`docs/orchestration/sessions/` garde les journaux `stream-json` des sessions d'agents et leurs comptes rendus. Un fichier `*.jsonl` par session, un `*-resultat.txt` quand le compte rendu a été extrait.

Ils servent à deux choses : retrouver le décompte de tokens d'une session après coup, et relire ce qu'un agent a réellement dit quand le journal du dépôt ne garde que la conclusion.

Le nom du fichier est celui de la tâche, pas celui de la branche : `corrections-I1-S.jsonl` est la session de correction de I1, tenue par Sonnet.
