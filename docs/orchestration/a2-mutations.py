"""Mutations de A2, hors du depot : une copie jetable par mutation, suite complete, temoin vert avant et apres.

Usage : /opt/data/cache/scratch/venv-ms/bin/python /opt/data/cache/scratch/a2-mutations.py
"""
import os, shutil, subprocess, sys

RACINE = "/opt/data/cache/scratch"
DEPOT = os.path.join(RACINE, "ws", "moodlesync")
BASE = os.path.join(RACINE, "a2base")
PYTHON = os.path.join(RACINE, "venv-ms", "bin", "python")
FICHIER = os.path.join("moodlesync", "api_textes.py")

MUTATIONS = [
    ("M1 type d'un document texte classe scanne",
     'if extraction == "texte":\n        return "texte"',
     'if extraction == "texte":\n        return "scanne"'),
    ("M2 pliage sans retrait des diacritiques",
     "if unicodedata.combining(element):\n                continue",
     "if False:\n                continue"),
    ("M3 tronque toujours faux",
     'return {"resultats": resultats, "total": total, "tronque": total > borne}',
     'return {"resultats": resultats, "total": total, "tronque": False}'),
    ("M4 plafond de copie retire",
     "if caracteres > TEXTE_MAX:",
     "if False:"),
    ("M5 zip_jsonl sans JSONL",
     "if jsonl:\n                flux",
     "if False:\n                flux"),
    ("M6 composant cache accepte",
     'if any(partie.startswith(".") for partie in parties):\n                return None',
     "if False:\n                return None"),
]


def arbre(racine):
    if os.path.isdir(racine):
        shutil.rmtree(racine)
    os.makedirs(racine)
    archive = subprocess.run(["git", "archive", "364922e"], cwd=DEPOT, capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", racine], input=archive.stdout, check=True)
    shutil.copy2(os.path.join(DEPOT, FICHIER), os.path.join(racine, FICHIER))
    shutil.copy2(os.path.join(DEPOT, "tests", "test_api_textes.py"),
                 os.path.join(racine, "tests", "test_api_textes.py"))


def suite(racine):
    r = subprocess.run([PYTHON, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                       cwd=racine, capture_output=True, text=True, timeout=300)
    lignes = [ligne for ligne in r.stderr.splitlines() if ligne.startswith(("Ran ", "OK", "FAILED"))]
    return " / ".join(lignes) if lignes else "resultat illisible (code %s)" % r.returncode


arbre(BASE)
print("temoin avant :", suite(BASE))
for numero, (nom, avant, apres) in enumerate(MUTATIONS, 1):
    racine = os.path.join(RACINE, "a2mut%d" % numero)
    arbre(racine)
    chemin = os.path.join(racine, FICHIER)
    with open(chemin, encoding="utf-8") as f:
        source = f.read()
    if source.count(avant) != 1:
        print("%s : motif absent ou multiple (%d)" % (nom, source.count(avant)))
        continue
    with open(chemin, "w", encoding="utf-8", newline="\n") as f:
        f.write(source.replace(avant, apres))
    print("%s : %s" % (nom, suite(racine)))
print("temoin apres :", suite(BASE))
