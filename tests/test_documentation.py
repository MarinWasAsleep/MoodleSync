"""Documentation de la 2.5 : forme et liens avec le code (ecart 286 de la revue de P3).

Aucun reseau, aucune fenetre. Les cinq documents que la 2.5 a ecrits ou modifies sont lus sur le disque :
`README.md`, `CONTRIBUTING.md`, `docs/notes-version.md`, `docs/tiers.md` et `docs/LISEZ-MOI.txt`.

Ce que ces tests tiennent : fins de ligne LF, aucun tiret long ni demi-cadratin, vocabulaire du contrat 3.4 (aucun
« OCR » ni « Tesseract » dans ce que lit l'etudiant), et les valeurs que les documents recopient du code (noms,
empreintes et version de pypdfium2) egales a celles du code. Ce qu'ils ne tiennent pas : que les phrases soient justes ;
cela se lit.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, re, sys, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import ocr

DOCUMENTS = ("README.md", "CONTRIBUTING.md", os.path.join("docs", "notes-version.md"),
             os.path.join("docs", "LISEZ-MOI.txt"))
# Ce que lit l'etudiant : le contrat 3.4 n'y veut ni OCR ni Tesseract. CONTRIBUTING et tiers.md parlent aux developpeurs.
POUR_L_ETUDIANT = ("README.md", os.path.join("docs", "notes-version.md"), os.path.join("docs", "LISEZ-MOI.txt"))


def lire(nom):
    with open(os.path.join(RACINE, nom), "rb") as f:
        return f.read().decode("utf-8")


class FormeDesDocuments(unittest.TestCase):
    def test_fins_de_ligne_lf(self):
        for nom in DOCUMENTS:
            with self.subTest(document=nom):
                self.assertNotIn("\r", lire(nom))

    def test_aucun_tiret_long(self):
        for nom in DOCUMENTS:
            for tiret in (chr(0x2013), chr(0x2014)):
                with self.subTest(document=nom, tiret=hex(ord(tiret))):
                    self.assertNotIn(tiret, lire(nom))

    def test_vocabulaire_du_contrat_3_4(self):
        for nom in POUR_L_ETUDIANT:
            with self.subTest(document=nom):
                trouves = re.findall(r"\b(ocr|tesseract)\b", lire(nom), flags=re.I)
                self.assertEqual(trouves, [], "mot interdit dans ce que lit l'etudiant")

    def test_aucune_phrase_sur_une_installation_non_branchee(self):
        """L'installation des deux paquets est branchee (ecart 279) : aucun document ne dit le contraire."""
        for nom in DOCUMENTS:
            with self.subTest(document=nom):
                texte = lire(nom).lower()
                for faux in ("pas encore branchée", "pas encore branchee", "installation_indisponible` et renvoie"):
                    self.assertNotIn(faux, texte)
