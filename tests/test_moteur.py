"""Tests hors ligne du moteur (moteur.py) et de la recette de compilation : reglage YouTube, statistiques de
Selenium Manager, messages d'erreur, version unique, absence de tirets longs. Aucun acces reseau : les
appels a urllib et a Selenium sont remplaces par des doublures.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, sys, re, json, types, tempfile, unittest, urllib.error, urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import moteur as ms
import moodlesync


class FauxUrlopen:
    """Remplace urllib.request.urlopen : compte les appels, renvoie une reponse oEmbed."""

    def __init__(self):
        self.appels = []

    def __call__(self, url, timeout=None):
        self.appels.append(url)
        corps = json.dumps({"title": "Une conférence", "author_name": "Chaîne"}).encode("utf-8")

        class Reponse:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def read(s):
                return corps
        return Reponse()


class Reglages(unittest.TestCase):
    """APP_DIR, CONFIG et ERREURS rediriges vers un dossier temporaire ; urlopen remplace."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.anciens = (ms.CONFIG, ms.ERREURS, ms.TITRES_YOUTUBE, urllib.request.urlopen)
        ms.CONFIG = os.path.join(self.tmp.name, "config.json")
        ms.ERREURS = os.path.join(self.tmp.name, "erreurs.txt")
        self.urlopen = FauxUrlopen()
        urllib.request.urlopen = self.urlopen

    def tearDown(self):
        ms.CONFIG, ms.ERREURS, ms.TITRES_YOUTUBE, urllib.request.urlopen = self.anciens
        self.tmp.cleanup()

    def ecrire_config(self, c):
        with open(ms.CONFIG, "w", encoding="utf-8") as f:
            json.dump(c, f)


class YouTube(Reglages):
    URL = "https://www.youtube.com/watch?v=abc123"

    def test_ancienne_config_sans_la_cle(self):
        self.ecrire_config({"token": "x", "site": "https://moodle.exemple.ch"})
        self.assertIs(ms.charger_config()["titres_youtube"], True)

    def test_reglage_lu_et_applique(self):
        self.ecrire_config({"titres_youtube": False})
        c = ms.charger_config()
        self.assertIs(c["titres_youtube"], False)
        ms.appliquer_config(c)
        self.assertFalse(ms.TITRES_YOUTUBE)
        ms.appliquer_config({})
        self.assertTrue(ms.TITRES_YOUTUBE)                       # valeur par defaut

    def test_active_contacte_youtube(self):
        self.assertEqual(ms.titre_video(self.URL, actif=True), "Une conférence (Chaîne)")
        self.assertEqual(len(self.urlopen.appels), 1)
        self.assertTrue(self.urlopen.appels[0].startswith("https://www.youtube.com/oembed?"))

    def test_desactive_aucun_appel(self):
        ms.appliquer_config({"titres_youtube": False})
        self.assertIsNone(ms.titre_video(self.URL))
        self.assertIsNone(ms.titre_video(self.URL, actif=False))
        self.assertEqual(self.urlopen.appels, [])

    def test_lien_non_youtube_aucun_appel(self):
        self.assertIsNone(ms.titre_video("https://www.unil.ch/page", actif=True))
        self.assertEqual(self.urlopen.appels, [])

    def note_liens(self):
        dest = os.path.join(self.tmp.name, "rangement")
        lien = {"sid": 1, "section": "Séance 1", "dossier": "Cours", "nom": "Vidéo du cours " + chr(0x2013) + " partie 1",
                "url": self.URL, "description": ""}
        ms.ecrire_liens([lien], dest, dire=lambda t: None)
        with open(os.path.join(dest, "Cours", "Séance 1", ms.T["liens"]), encoding="utf-8") as f:
            return f.read()

    def test_note_de_liens_sans_youtube(self):
        ms.appliquer_config({"titres_youtube": False})
        texte = self.note_liens()
        self.assertEqual(self.urlopen.appels, [])
        self.assertIn(self.URL, texte)                             # le lien reste, avec son adresse
        self.assertNotIn("Une conférence", texte)
        self.assertNotIn(chr(0x2013), texte)                       # tiret long remplace par une virgule
        self.assertIn("Vidéo du cours, partie 1", texte)

    def test_note_de_liens_avec_youtube(self):
        ms.appliquer_config({"titres_youtube": True})
        self.assertIn("Une conférence (Chaîne)", self.note_liens())
        self.assertEqual(len(self.urlopen.appels), 1)


class SeleniumManager(unittest.TestCase):
    def test_statistiques_desactivees_avant_le_navigateur(self):
        """Doublure de selenium : le navigateur ne se lance pas, mais la variable doit etre posee avant."""
        vu = {}

        def pilote(options=None):
            vu["stats"] = os.environ.get("SE_AVOID_STATS")
            raise RuntimeError("pas de navigateur dans les tests")

        webdriver = types.SimpleNamespace(Chrome=pilote, Edge=pilote, ChromeOptions=FausseOptions,
                                          EdgeOptions=FausseOptions)
        selenium = types.ModuleType("selenium")
        selenium.webdriver = webdriver
        anciens = {k: sys.modules.get(k) for k in ("selenium", "selenium.webdriver")}
        ancienne_var = os.environ.pop("SE_AVOID_STATS", None)
        sys.modules["selenium"], sys.modules["selenium.webdriver"] = selenium, webdriver
        try:
            with self.assertRaises(ms.Erreur):
                ms.ouvrir_navigateur(dire=lambda t: None)
            self.assertEqual(vu["stats"], "true")
        finally:
            for k, v in anciens.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
            if ancienne_var is None:
                os.environ.pop("SE_AVOID_STATS", None)
            else:
                os.environ["SE_AVOID_STATS"] = ancienne_var


class FausseOptions:
    def add_argument(self, a):
        pass


class Erreurs(Reglages):
    def message(self, e, action="Synchronisation"):
        try:
            raise e
        except Exception as x:
            return ms.message_erreur(x, action)

    def test_reseau(self):
        for e in (urllib.error.URLError("hote introuvable"), ConnectionResetError(10054, "coupe"),
                  TimeoutError("delai")):
            with self.subTest(e=type(e).__name__):
                texte = self.message(e)
                self.assertIn("Moodle ne répond pas", texte)
                self.assertNotIn("fichier", texte)

    def test_fichier(self):
        texte = self.message(PermissionError(13, "Accès refusé", "x.md"))
        self.assertIn("impossible de lire ou d'écrire un fichier", texte)
        self.assertIn("Accès refusé", texte)

    def test_imprevue_detail_note_localement(self):
        texte = self.message(KeyError("cle_interne"), "Audit")
        self.assertTrue(texte.startswith("Audit : erreur imprévue"))
        self.assertNotIn("KeyError", texte)
        with open(ms.ERREURS, encoding="utf-8") as f:
            journal = f.read()
        self.assertIn("KeyError", journal)
        self.assertIn("Audit", journal)


class Divers(unittest.TestCase):
    def test_annee_avec_tiret_demi_cadratin(self):
        for nom in ("COURS_Histoire (2026" + chr(0x2013) + "2027)", "COURS_Histoire (2026-2027)",
                    "COURS_Histoire 2026/2027"):
            with self.subTest(nom=nom):
                self.assertEqual(ms.RE_ANNEE.sub("", nom).strip(), "COURS_Histoire")

    def test_pas_de_tiret_long_dans_les_fichiers_de_compilation(self):
        for chemin in ("moodlesync/moteur.py", "MoodleSync.spec", "requirements.txt", "requirements-compilation.txt",
                       ".github/workflows/compilation.yml", "tests/test_moteur.py"):
            with self.subTest(chemin=chemin):
                with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
                    texte = f.read()
                self.assertNotIn(chr(0x2013), texte)
                self.assertNotIn(chr(0x2014), texte)


class Version(unittest.TestCase):
    def test_source_unique(self):
        """La recette lit la version dans moodlesync/__init__.py et n'en ecrit aucune en dur."""
        with open(os.path.join(RACINE, "MoodleSync.spec"), encoding="utf-8") as f:
            spec = f.read()
        with open(os.path.join(RACINE, "moodlesync", "__init__.py"), encoding="utf-8") as f:
            init = f.read()
        motif = re.search(r"re\.search\(r'(.+?)', f\.read\(\), re\.M\)", spec).group(1)
        self.assertEqual(re.search(motif, init, re.M).group(1), moodlesync.VERSION)
        self.assertNotRegex(spec, r"""CFBundle\w*Version["']\s*:\s*["']\d""")
        self.assertNotIn(f'"{moodlesync.VERSION}"', spec)


if __name__ == "__main__":
    unittest.main()


class Integration(Reglages):
    """Corrections de l'agent principal : configuration atomique, demarrage depuis les sources, Ma semaine
    dans le mode automatique."""

    def test_config_ecrite_sans_fichier_temporaire_restant(self):
        ms.sauver_config({"token": "x"})
        self.assertEqual(json.load(open(ms.CONFIG, encoding="utf-8")), {"token": "x"})
        self.assertFalse(os.path.exists(ms.CONFIG + ".tmp"))

    def test_commande_auto_depuis_les_sources_vise_lancer_py(self):
        prog, args = ms.commande_auto()
        self.assertEqual(os.path.basename(args[0]), "lancer.py")
        self.assertTrue(os.path.exists(args[0]))
        self.assertEqual(args[1:], ["--auto", "--demarrage"])

    def test_semaine_auto_desactivee_ne_fait_rien(self):
        from moodlesync import suivi
        ancien = suivi.prefs
        suivi.prefs = lambda: {"active": False}
        try:
            self.assertIsNone(ms.semaine_auto())
        finally:
            suivi.prefs = ancien

    def test_semaine_auto_erreur_n_interrompt_pas(self):
        from moodlesync import suivi
        anciens = suivi.prefs, suivi.Semaine
        suivi.prefs = lambda: {"active": True}

        class Panne:
            def __init__(self):
                raise KeyError("interne")
        suivi.Semaine = Panne
        try:
            self.assertIsNone(ms.semaine_auto())                  # pas d'exception
            self.assertIn("KeyError", open(ms.ERREURS, encoding="utf-8").read())
        finally:
            suivi.prefs, suivi.Semaine = anciens
