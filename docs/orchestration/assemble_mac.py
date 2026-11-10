"""Assemble le paquet macOS : binaires tesseract, dependances Homebrew et tessdata.

Telecharge les flacons Homebrew (arm64_sequoia), les decompresse, copie les dylib dans lib/,
reecrit les chemins /opt/... vers @loader_path, puis fabrique le zip.
"""
import json, os, re, shutil, subprocess, sys, tarfile, urllib.request, zipfile, hashlib

RACINE = "/opt/data/cache/scratch/moteur-mac"
BUILD = os.path.join(RACINE, "build")
FLAVOR = "arm64_sequoia"

# (nom de formule, prefixe Homebrew attendu dans les chemins)
FORMULES = [
    ("leptonica", "/opt/leptonica"),
    ("libarchive", "/opt/libarchive"),
    ("giflib", "/opt/giflib"),
    ("jpeg-turbo", "/opt/jpeg-turbo"),
    ("libpng", "/opt/libpng"),
    ("libtiff", "/opt/libtiff"),
    ("openjpeg", "/opt/openjpeg"),
    ("webp", "/opt/webp"),
    ("libb2", "/opt/libb2"),
    ("lz4", "/opt/lz4"),
    ("xz", "/opt/xz"),
    ("zstd", "/opt/zstd"),
]


def jeton():
    u = "https://ghcr.io/token?scope=repository:homebrew/core/%s:pull&service=ghcr.io"
    return json.load(urllib.request.urlopen(u % "leptonica", timeout=30))["token"]


def infos(nom):
    req = urllib.request.Request("https://formulae.brew.sh/api/formula/%s.json" % nom,
                                 headers={"User-Agent": "MoodleSync/1.0"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def telecharge(nom, tok):
    d = infos(nom)
    f = d["bottle"]["stable"]["files"].get(FLAVOR)
    if not f:
        print("pas de flacon", FLAVOR, "pour", nom)
        return None
    url = "https://ghcr.io/v2/homebrew/core/%s/blobs/sha256:%s" % (nom, f["sha256"])
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    chemin = os.path.join(BUILD, nom + ".tar.gz")
    with urllib.request.urlopen(req, timeout=300) as r, open(chemin, "wb") as s:
        shutil.copyfileobj(r, s)
    return chemin, d["versions"]["stable"]


def main():
    os.makedirs(BUILD, exist_ok=True)
    tok = jeton()
    for nom, prefixe in FORMULES:
        chemin, version = telecharge(nom, tok)
        if not chemin:
            continue
        dossier = os.path.join(BUILD, nom)
        if os.path.isdir(dossier):
            shutil.rmtree(dossier)
        os.makedirs(dossier)
        with tarfile.open(chemin) as t:
            t.extractall(dossier, filter="data")
        print(nom, version, "ok")


if __name__ == "__main__":
    main()
