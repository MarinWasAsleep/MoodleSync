"""Assemble le paquet macOS final : binaires, dylib aplaties dans lib/, chemins reecrits.

Prend les binaires de tesseract 5.5.4 (flacon Homebrew) et les dylib de ses dependances,
copie tout dans un arbre plat, reecrit les references /opt/... en @loader_path, puis zippe.
"""
import os, re, shutil, sys, zipfile, hashlib

RACINE = "/opt/data/cache/scratch/moteur-mac"
BUILD = os.path.join(RACINE, "build")
TESS = os.path.join(RACINE, "tesseract", "5.5.4")
SORTIE = os.path.join(RACINE, "paquet")
PREFIXES = ["/opt/leptonica", "/opt/libarchive", "/opt/giflib", "/opt/jpeg-turbo", "/opt/libpng",
            "/opt/libtiff", "/opt/openjpeg", "/opt/webp", "/opt/libb2", "/opt/lz4", "/opt/xz",
            "/opt/zstd", "/opt/tesseract"]


def dylibs():
    """Toutes les dylib des dependances, par nom de fichier."""
    trouvees = {}
    for racine, _, fichiers in os.walk(BUILD):
        if os.path.basename(racine) != "lib":
            continue
        for f in fichiers:
            if f.endswith(".dylib"):
                trouvees.setdefault(f, os.path.join(racine, f))
    return trouvees


def reecrit(chemin, table):
    """Reecrit dans le binaire les chemins /opt/... vers @loader_path/<nom de dylib>."""
    d = open(chemin, "rb").read()
    change = False
    for prefixe in PREFIXES:
        motif = re.compile(re.escape(prefixe.encode()) + rb"/lib/([A-Za-z0-9_.+-]+\.dylib)")
        def remplace(m):
            nonlocal change
            nom = m.group(1).decode()
            if nom not in table:
                return m.group(0)
            change = True
            return b"@loader_path/" + nom.encode()
        d = motif.sub(remplace, d)
    if change:
        open(chemin, "wb").write(d)
    return change


def main():
    if os.path.isdir(SORTIE):
        shutil.rmtree(SORTIE)
    os.makedirs(os.path.join(SORTIE, "lib"))

    table = dylibs()
    print(len(table), "dylib trouvees")

    for nom, source in table.items():
        shutil.copy2(source, os.path.join(SORTIE, "lib", nom))

    for f in ("tesseract",):
        shutil.copy2(os.path.join(TESS, "bin", f), os.path.join(SORTIE, f))
        os.chmod(os.path.join(SORTIE, f), 0o755)

    for racine, _, fichiers in os.walk(SORTIE):
        for f in fichiers:
            if f.endswith(".dylib") or f == "tesseract":
                reecrit(os.path.join(racine, f), table)

    shutil.copytree(os.path.join(TESS, "share", "tessdata"), os.path.join(SORTIE, "tessdata"))
    shutil.copy2(os.path.join(TESS, "LICENSE"), os.path.join(SORTIE, "LICENSE-tesseract.txt"))

    restants = []
    for racine, _, fichiers in os.walk(SORTIE):
        for f in fichiers:
            p = os.path.join(racine, f)
            d = open(p, "rb").read()
            for prefixe in PREFIXES:
                if prefixe.encode() + b"/lib/" in d:
                    restants.append((os.path.relpath(p, SORTIE), prefixe))
    print("references restantes:", restants[:5], len(restants))

    out = os.path.join(RACINE, "MoodleSync-moteur-macos.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for racine, _, fichiers in os.walk(SORTIE):
            for f in sorted(fichiers):
                p = os.path.join(racine, f)
                z.write(p, os.path.relpath(p, SORTIE))
    print("taille", os.path.getsize(out) // 1024 // 1024, "Mo")
    print("sha256", hashlib.sha256(open(out, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
