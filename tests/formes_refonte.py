"""Comparaison de formes entre une reponse reelle de l'API et une fixture de docs/refonte-textes/fixtures/.

Les taches de Python (R3, R4, R5) l'importent pour prouver que leurs vraies sorties ont la forme du contrat :

    from tests.formes_refonte import charger_fixture, differences
    assert differences(charger_fixture("arbre.json"), api.ocr_arbre()) == []

Regles :
- deux dictionnaires ont exactement les memes cles ;
- deux listes : chaque element du reel doit avoir la forme d'un element de la fixture (celui de meme `type`
  s'il y en a un, sinon le premier) ; une liste vide est acceptee dans le reel ;
- `None` d'un cote ou de l'autre est accepte (pages null, confiance null) ;
- un booleen n'est jamais un nombre ; un entier et un flottant sont interchangeables.
"""
import json
import os

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "docs", "refonte-textes", "fixtures")


def fixtures_presentes():
    return os.path.isdir(DOSSIER)


def charger_fixture(nom):
    with open(os.path.join(DOSSIER, nom), encoding="utf-8") as f:
        return json.load(f)


def _genre(valeur):
    if isinstance(valeur, bool):
        return "bool"
    if isinstance(valeur, (int, float)):
        return "nombre"
    if isinstance(valeur, str):
        return "texte"
    if isinstance(valeur, list):
        return "liste"
    if isinstance(valeur, dict):
        return "objet"
    return "nul"


def differences(attendu, reel, chemin="$"):
    """Liste de phrases, vide si la forme du reel est celle de la fixture."""
    if attendu is None or reel is None:
        return []
    ga, gr = _genre(attendu), _genre(reel)
    if ga != gr:
        return [f"{chemin} : {gr} au lieu de {ga}"]
    if ga == "objet":
        sortie = []
        for cle in sorted(set(attendu) - set(reel)):
            sortie.append(f"{chemin}.{cle} : cle absente")
        for cle in sorted(set(reel) - set(attendu)):
            sortie.append(f"{chemin}.{cle} : cle en trop")
        for cle in sorted(set(attendu) & set(reel)):
            sortie += differences(attendu[cle], reel[cle], f"{chemin}.{cle}")
        return sortie
    if ga == "liste":
        if not attendu:
            return []
        sortie = []
        for i, element in enumerate(reel):
            modele = attendu[0]
            if isinstance(element, dict) and "type" in element:
                # meme type ET meme profondeur de forme : on prefere le modele de meme `chemin`, puis de meme `type` et de memes cles
                memes = [a for a in attendu if isinstance(a, dict) and a.get("type") == element["type"]]
                modele = next((a for a in memes if a.get("chemin") == element.get("chemin")), None) \
                    or next((a for a in memes if set(a) == set(element)), None) or (memes[0] if memes else modele)
            sortie += differences(modele, element, f"{chemin}[{i}]")
        return sortie
    return []
