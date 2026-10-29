#!/usr/bin/env python3
"""Dessine MoodleSync.ico sans dependance : carre arrondi bleu, dossier blanc, fleche de telechargement.

Utilisation : python -I faire_icone.py   (ecrit MoodleSync.ico a cote de ce script)
Le dessin est fait dans un repere 1024 x 1024, rendu en sur-echantillonnage 4x pour lisser les bords.
"""
import os, struct, zlib

HAUT, BAS = (59, 130, 246), (29, 78, 216)       # degrade du fond
DOS, FACE, FLECHE = (191, 219, 254), (255, 255, 255), (37, 99, 235)


def dans_rect_arrondi(x, y, x0, y0, x1, y1, r):
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def dans_triangle(x, y, a, b, c):
    def cote(p, q):
        return (x - q[0]) * (p[1] - q[1]) - (p[0] - q[0]) * (y - q[1])
    d1, d2, d3 = cote(a, b), cote(b, c), cote(c, a)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def couleur(x, y):
    """Couleur RGBA du point (x, y) du repere 1024, ou None si transparent."""
    if not dans_rect_arrondi(x, y, 48, 48, 976, 976, 210):
        return None
    t = (y - 48) / 928
    c = tuple(round(h + (b - h) * t) for h, b in zip(HAUT, BAS))
    if dans_rect_arrondi(x, y, 220, 280, 500, 420, 44) or dans_rect_arrondi(x, y, 220, 330, 804, 720, 56):
        c = DOS
    if dans_rect_arrondi(x, y, 220, 400, 804, 776, 56):
        c = FACE
    if dans_rect_arrondi(x, y, 476, 450, 548, 620, 20) or \
            dans_triangle(x, y, (392, 590), (632, 590), (512, 716)):
        c = FLECHE
    return c


def rendu(taille, ss=4):
    n = taille * ss
    pas = 1024 / n
    px = bytearray()
    for j in range(taille):
        for i in range(taille):
            r = g = b = a = 0
            for v in range(ss):
                for u in range(ss):
                    c = couleur((i * ss + u + 0.5) * pas, (j * ss + v + 0.5) * pas)
                    if c:
                        r, g, b, a = r + c[0], g + c[1], b + c[2], a + 1
            px += bytes((r // a, g // a, b // a, round(255 * a / (ss * ss)))) if a else b"\0\0\0\0"
    return bytes(px)


def png(taille, rgba):
    lignes = b"".join(b"\0" + rgba[y * taille * 4:(y + 1) * taille * 4] for y in range(taille))
    def bloc(genre, data):
        return struct.pack(">I", len(data)) + genre + data + struct.pack(">I", zlib.crc32(genre + data))
    return (b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", taille, taille, 8, 6, 0, 0, 0))
            + bloc(b"IDAT", zlib.compress(lignes, 9)) + bloc(b"IEND", b""))


def ico(tailles):
    images = [png(t, rendu(t)) for t in tailles]
    tete = struct.pack("<HHH", 0, 1, len(images))
    decalage = 6 + 16 * len(images)
    entrees = b""
    for t, im in zip(tailles, images):
        entrees += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(im), decalage)
        decalage += len(im)
    return tete + entrees + b"".join(images)


if __name__ == "__main__":
    sortie = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MoodleSync.ico")
    with open(sortie, "wb") as f:
        f.write(ico([16, 24, 32, 48, 64, 256]))
    print(sortie, os.path.getsize(sortie), "octets")
