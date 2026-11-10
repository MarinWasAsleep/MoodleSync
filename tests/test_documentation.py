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

    PHRASE_MACOS_13 = r"Sous macOS 11 et 12, le rendu des PDF est indisponible[^.]*macOS 13 ou plus"

    def test_la_limite_macos_13_est_annoncee_a_l_utilisateur(self):
        """Ecart 17 : pypdfium2 n'a de roue macOS qu'a partir de macOS 13 (requirements.txt). La limite est dite dans
        la section Limites du README et dans les notes de version, pas seulement dans le fichier des dependances."""
        readme = re.sub(r"\s+", " ", lire("README.md").replace("*", ""))
        limites = readme.split("## Limites", 1)[1].split("## Licence", 1)[0]
        notes = re.sub(r"\s+", " ", lire(os.path.join("docs", "notes-version.md")).replace("*", ""))
        self.assertRegex(limites, self.PHRASE_MACOS_13, "README.md, section Limites")
        self.assertRegex(notes, self.PHRASE_MACOS_13, "docs/notes-version.md")
        self.assertIn("macOS 13", lire("requirements.txt"), "la limite vient de requirements.txt")

    def test_contributing_dit_vrai_sur_les_refus(self):
        """Ecart 280 : `non_suivi` = aucune entree dans `.moodlesync.json` ; `modifie_main` refuse sans confirmation."""
        texte = lire("CONTRIBUTING.md")
        self.assertNotIn("sans la marque du programme est refusé", texte)
        self.assertNotIn("un fichier modifié à la main demande une confirmation", texte)
        self.assertIn("aucune entrée dans `.moodlesync.json`", texte)


class PlanEnDeuxPointCinq(unittest.TestCase):
    """Constat 298 : les dix passages de `docs/plan-ocr.md` remis en accord avec la 2.5 (ecart 293) sont gardes."""

    PASSAGES = (
        "télécharge le moteur dès la 2.5",
        "**Version 2.5 : installation automatique par paquet.**",
        "**Paquet portable (2.5).**",
        "installé par MoodleSync (2.5)",
        "Le bouton **Installer** télécharge le moteur à ta place",
        "dès la 2.5, le téléchargement du paquet portable",
        "par paquet portable (2.5, deux paquets",
        "installation par paquet portable (2.5)",
        "Il est livré dans la 2.5",
        "paquet portable dès la 2.5",
    )

    def setUp(self):
        self.plan = lire(os.path.join("docs", "plan-ocr.md"))

    def test_les_dix_passages_disent_2_5(self):
        for passage in self.PASSAGES:
            with self.subTest(passage=passage):
                self.assertIn(passage, self.plan)

    def test_le_plan_ne_renvoie_plus_l_installation_a_la_2_6(self):
        self.assertEqual(re.findall(r"(?<![\d.])2\.6(?!\d)", self.plan), [])
        for faux in ("pas d'installation automatique", "pas d’installation automatique"):
            self.assertNotIn(faux, self.plan.lower())


class ContratNommeDesTestsReels(unittest.TestCase):
    """Constat 296 : chaque nom de test de la section 6 du contrat (T1 a T32) existe dans `tests/`."""

    def noms_du_tableau(self):
        contrat = lire(os.path.join("docs", "ocr-contrat.md"))
        section = contrat.split("## 6.", 1)[1].split("## 7.", 1)[0]
        lignes = [l for l in section.splitlines() if re.match(r"\| T\d+ \|", l)]
        return {l.split("|")[1].strip(): re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", l.split("|")[2]) for l in lignes}

    def sources_des_tests(self):
        dossier = os.path.join(RACINE, "tests")
        sources = []
        for nom in sorted(os.listdir(dossier)):
            if nom.endswith(".py"):
                with open(os.path.join(dossier, nom), "rb") as f:
                    sources.append(f.read().decode("utf-8"))
        return "\n".join(sources)

    def test_le_tableau_porte_t1_a_t32(self):
        self.assertEqual(sorted(self.noms_du_tableau(), key=lambda t: int(t[1:])), ["T%d" % n for n in range(1, 33)])

    def test_chaque_nom_du_tableau_existe(self):
        sources = self.sources_des_tests()
        for test, noms in self.noms_du_tableau().items():
            with self.subTest(test=test):
                self.assertTrue(noms, "aucun nom de test dans la ligne")
                for nom in noms:
                    self.assertRegex(sources, r"(?m)^\s*(def|class) %s\b" % re.escape(nom), "%s : %s n'existe pas dans tests/" % (test, nom))


if __name__ == "__main__":
    unittest.main()
