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

DOCUMENTS = ("README.md", "CONTRIBUTING.md", os.path.join("docs", "notes-version.md"), os.path.join("docs", "tiers.md"),
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


class LiensAvecLeCode(unittest.TestCase):
    def test_tiers_cite_les_noms_et_les_empreintes_du_code(self):
        tiers = lire(os.path.join("docs", "tiers.md"))
        for plateforme in ("win32", "darwin"):
            with self.subTest(plateforme=plateforme):
                self.assertIn(ocr.NOM_PAQUET[plateforme], tiers)
                self.assertIn(ocr.EMPREINTE_PAQUET[plateforme], tiers)

    def test_tiers_cite_la_version_epinglee_de_pypdfium2(self):
        pin = re.search(r"^pypdfium2==([0-9.]+)", lire("requirements.txt"), flags=re.M | re.I)
        self.assertTrue(pin, "pypdfium2 est epinglee dans requirements.txt")
        tiers = lire(os.path.join("docs", "tiers.md"))
        self.assertIn("pypdfium2 " + pin.group(1), tiers)
        for retiree in re.findall(r"pypdfium2 (5\.\d+\.\d+)", tiers):
            self.assertEqual(retiree, pin.group(1), "une autre version de pypdfium2 est citee comme la version employee")

    def test_les_notes_et_le_readme_citent_la_liste_des_modes(self):
        """Le mode `remplacer` est un reglage de la fenetre (ecart 276) : les documents disent ou le trouver."""
        for nom in ("README.md", os.path.join("docs", "notes-version.md"), os.path.join("docs", "LISEZ-MOI.txt")):
            with self.subTest(document=nom):
                self.assertIn("Version cherchable des PDF", lire(nom))

    def test_la_limite_de_restauration_est_ecrite(self):
        """Ecart 281 : un PDF modifie a la main avant le premier remplacement ne se restaure pas."""
        for nom in ("README.md", "CONTRIBUTING.md", os.path.join("docs", "notes-version.md")):
            with self.subTest(document=nom):
                texte = re.sub(r"\s+", " ", lire(nom).replace("*", ""))      # retours a la ligne et gras mis a plat
                self.assertRegex(texte, r"à la main avant le premier remplacement")

    def test_contributing_dit_vrai_sur_les_refus(self):
        """Ecart 280 : `non_suivi` = aucune entree dans `.moodlesync.json` ; `modifie_main` refuse sans confirmation."""
        texte = lire("CONTRIBUTING.md")
        self.assertNotIn("sans la marque du programme est refusé", texte)
        self.assertNotIn("un fichier modifié à la main demande une confirmation", texte)
        self.assertIn("aucune entrée dans `.moodlesync.json`", texte)


if __name__ == "__main__":
    unittest.main()
