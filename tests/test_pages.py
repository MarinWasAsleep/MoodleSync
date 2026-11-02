"""Tests hors ligne du comptage des pages de Ma semaine : aucun PDF garde, seul le nombre de pages l'est.
Aucun acces reseau : le telechargement est remplace par une doublure qui ecrit un vrai PDF.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import io, json, os, sys, tempfile, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import moteur as ms, seances as sc, semaine as m
import pypdf

URL = "https://moodle.exemple.ch/webservice/pluginfile.php/1/f.pdf?forcedownload=1"
CLE = URL.split("?")[0]


def pdf(pages):
    w, o = pypdf.PdfWriter(), io.BytesIO()
    for _ in range(pages):
        w.add_blank_page(100, 100)
    w.write(o)
    return o.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = self.tmp.name
        self.addCleanup(setattr, ms, "recuperer", ms.recuperer)
        self.telecharges = []
        self.serveur = pdf(3)

        def recuperer(url, token, chemin, arreter=None, attendu=None):
            self.telecharges.append(chemin)
            if isinstance(self.serveur, Exception):
                raise self.serveur
            with open(chemin, "wb") as f:
                f.write(self.serveur)
        ms.recuperer = recuperer

    def fichier(self, t=100, taille=None):
        return {"nom": "f.pdf", "url": URL, "t": t, "taille": len(self.serveur) if taille is None else taille, "pdf": True}


class PagesPdf(Base):
    def test_telechargement_temporaire_efface_et_nombre_note(self):
        memo = {}
        self.assertEqual(sc.pages_pdf("j", self.fichier(), memo), 3)
        self.assertEqual(len(self.telecharges), 1)
        self.assertFalse(os.path.exists(self.telecharges[0]))
        self.assertFalse(os.path.exists(os.path.dirname(self.telecharges[0])))
        self.assertEqual(memo[CLE]["pages"], 3)

    def test_nombre_connu_sans_telechargement(self):
        memo = {}
        sc.pages_pdf("j", self.fichier(), memo)
        self.assertEqual(sc.pages_pdf("j", self.fichier(), memo), 3)
        self.assertEqual(len(self.telecharges), 1)

    def test_republication_recomptee(self):
        memo = {}
        sc.pages_pdf("j", self.fichier(100), memo)
        self.serveur = pdf(5)
        self.assertEqual(sc.pages_pdf("j", self.fichier(200), memo), 5)
        self.assertEqual(memo[CLE]["t"], 200)

    def ranger(self, contenu, t=100):
        chemin = os.path.join(self.d, "Cours", "f.pdf")
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(contenu)
        return {CLE: {"t": t, "chemin": os.path.join("Cours", "f.pdf")}}, chemin

    def test_copie_rangee_lue_sur_place_sans_la_toucher(self):
        contenu = pdf(7)
        etat, chemin = self.ranger(contenu)
        self.assertEqual(sc.pages_pdf("j", self.fichier(taille=len(contenu)), {}, etat, self.d), 7)
        self.assertEqual(self.telecharges, [])
        with open(chemin, "rb") as f:
            self.assertEqual(f.read(), contenu)

    def test_copie_rangee_d_une_autre_version_ignoree(self):
        for etat_t, taille_ecart in ((50, 0), (100, 1)):            # autre date, puis autre taille (fichier annote)
            with self.subTest(t=etat_t, ecart=taille_ecart):
                self.telecharges.clear()
                contenu = pdf(7)
                etat, _ = self.ranger(contenu, etat_t)
                f = self.fichier(100, len(contenu) + taille_ecart)
                self.assertEqual(sc.pages_pdf("j", f, {}, etat, self.d), 3)   # le nombre du serveur, pas 7
                self.assertEqual(len(self.telecharges), 1)

    def test_copie_rangee_disparue_ou_illisible(self):
        etat, chemin = self.ranger(b"pas un pdf")
        f = self.fichier(taille=len(b"pas un pdf"))
        self.assertEqual(sc.pages_pdf("j", f, {}, etat, self.d), 3)
        os.remove(chemin)
        self.assertEqual(sc.pages_pdf("j", f, {}, etat, self.d), 3)
        self.assertEqual(len(self.telecharges), 2)

    def test_echec_reseau_non_note(self):
        memo, self.serveur = {}, OSError("coupure")
        f = {"url": URL, "t": 100, "taille": 10}
        self.assertIsNone(sc.pages_pdf("j", f, memo))
        self.assertEqual(memo, {})
        self.serveur = pdf(3)
        self.assertEqual(sc.pages_pdf("j", f, memo), 3)

    def test_pdf_illisible_note_jusqu_a_republication(self):
        memo, self.serveur = {}, b"pas un pdf"
        self.assertIsNone(sc.pages_pdf("j", self.fichier(), memo))
        self.assertIsNone(sc.pages_pdf("j", self.fichier(), memo))
        self.assertEqual(len(self.telecharges), 1)
        self.assertIsNone(sc.pages_pdf("j", self.fichier(200), memo))
        self.assertEqual(len(self.telecharges), 2)

    def test_sans_adresse(self):
        self.assertIsNone(sc.pages_pdf("j", {"url": None}, {}))


class Semaine(Base):
    def setUp(self):
        super().setUp()
        sauve = ms.APP_DIR, ms.CONFIG, m.PAGES, m.ANCIENS_CACHES

        def retablir():
            ms.APP_DIR, ms.CONFIG, m.PAGES, m.ANCIENS_CACHES = sauve
        self.addCleanup(retablir)
        ms.APP_DIR, ms.CONFIG = self.d, os.path.join(self.d, "config.json")
        m.PAGES = os.path.join(self.d, "pages.json")
        ms.sauver_config({**ms.charger_config(), "dest": os.path.join(self.d, "Cours")})

    def test_nombres_gardes_d_une_actualisation_a_l_autre(self):
        for _ in range(2):
            f = self.fichier()
            m.compter_pages([{"lectures": [f, {"pdf": False}]}], "j", dire=lambda t: None)
            self.assertEqual(f["pages"], 3)
        self.assertEqual(len(self.telecharges), 1)
        with open(m.PAGES, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)[CLE]["pages"], 3)
        self.assertFalse(os.path.exists(m.PAGES + ".tmp"))

    def test_anciens_caches_effaces(self):
        m.ANCIENS_CACHES = [os.path.join(self.d, "cache_pages"), os.path.join(self.d, "absent")]
        os.makedirs(m.ANCIENS_CACHES[0])
        with open(os.path.join(m.ANCIENS_CACHES[0], "a.pdf"), "wb") as f:
            f.write(b"x")
        m.supprimer_anciens_caches()
        self.assertFalse(os.path.exists(m.ANCIENS_CACHES[0]))


if __name__ == "__main__":
    unittest.main()
