# Prompt 26 pour DeepSeek v4.1 flash : ecart 92, ne pas revendiquer un PDF qu'on ne peut pas authentifier

Auteur : Hermes, orchestrateur, sur decision de Maxence, 8 novembre 2026. Destinataire : DeepSeek v4.1 flash. Une seule tache.

## Role

Tu es D. Tu appliques la decision de Maxence sur l'ecart 92 : quand l'etat a disparu, la marque d'un PDF ne sert plus a revendiquer ce fichier comme notre PDF cherchable. Tu ne casses aucune autre fonction de la marque.

## A lire, dans cet ordre, et rien d'autre

1. `docs/ocr-avancement.md` : les ecarts 91 et 92 et l'entree de revue de Y1b (section 6 et section 5).
2. `docs/ocr-contrat.md` : 2.2 (ce que la marque contient, et pourquoi elle ne peut pas porter l'identite du fichier), 3.3 (`deja_present`, `telecharger`, `genere`), invariants 8, 10 et 12.
3. `moodlesync/moteur.py` : `deja_present`, `telecharger`, et le chemin qui reconstruit `genere` depuis la marque.

## Decision de Maxence, a appliquer telle quelle

Quand `genere` est absent de l'etat, tu ne reconstruis plus l'entree depuis la marque. Le fichier marque est traite comme **non suivi** : il n'est pas compte comme un PDF cherchable, il n'est pas revendique comme notre fichier, et la synchronisation le retelchargera, avec le message visible deja prevu pour ce cas.

Ce que la marque continue de faire, sans changement : reconnaitre qu'un PDF est le notre pour **ne jamais le superposer une seconde fois** (invariants 8 et 10), et alimenter `modifie_main` quand l'etat existe. Tu ne retires donc aucun appel a `lire_marque` : tu retires seulement la reconstruction d'une entree `genere` a partir d'elle.

Ecris la regle au contrat 3.3, ajoute une ligne au journal des decisions au nom de Maxence, et ferme l'ecart 92 par une entree de journal qui le cite.

## Ecart 91

Verifie s'il tombe sous la meme regle. S'il tombe, ferme-le avec la meme entree et dis-le. Sinon, laisse-le ouvert et ecris en une phrase pourquoi il est distinct.

## Tests

Trois tests au moins, ecrits pour echouer avant le code :

1. etat perdu sur un PDF marque : pas de `generes`, pas de `genere` reconstruit, le fichier sera retelcharge ;
2. etat perdu sur un PDF natif de meme nom et meme taille qu'un ancien `genere` : il n'herite de rien ;
3. etat present : comportement inchange, y compris la reconnaissance d'un PDF cherchable deplace.

## Contraintes

- Suite verte : 468 tests, 3 ignores, plus ceux que tu ajoutes.
- Tu ne modifies que `moodlesync/moteur.py`, les fichiers de tests concernes, `docs/ocr-contrat.md`, `docs/ocr-avancement.md` et ce prompt. Rien d'autre.
- Francais, aucun tiret cadratin ni demi-cadratin. LF. Pas de `git add -A`, pas de push.
- Commit unique, auteur `MarinWasAsleep`. Verifie `git show --stat`.

## Livrable

`Fait / Fichiers / Tests / Decisions / Doutes / Suivant`, le hash du commit, et le sort de l'ecart 91.
