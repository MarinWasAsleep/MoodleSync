"""Tests hors ligne des correctifs de l'audit 2.0 : obtention du jeton, controle des telechargements,
adresse du site pendant une lecture de Moodle, reglages atomiques. Aucun acces reseau.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import base64, email.message, os, sys, tempfile, unittest, urllib.error, urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import application as app, moteur as ms, semaine as m


class FauxNavigateur:
    def __init__(self, etat):
        self.etat, self.ferme = etat, False

    def get(self, url):
        pass

    def execute_script(self, *a):
        return self.etat

    def get_cookies(self):
        return []

    def quit(self):
        self.ferme = True


class Connexion(unittest.TestCase):
    def setUp(self):
        self.sauve = ms.ouvrir_navigateur, ms.jeton_depuis_session, ms.time
        self.temps = [0.0]

        class Temps:
            time = staticmethod(lambda: self.temps[0])
            sleep = staticmethod(lambda s: self.temps.__setitem__(0, self.temps[0] + s))
        ms.time = Temps
        self.addCleanup(lambda: (setattr(ms, "ouvrir_navigateur", self.sauve[0]),
                                 setattr(ms, "jeton_depuis_session", self.sauve[1]), setattr(ms, "time", self.sauve[2])))

    def lancer(self, etat, reponses):
        """`reponses` : resultats successifs de jeton_depuis_session, le dernier se repete."""
        self.nav = FauxNavigateur(etat)
        self.essais = 0
        ms.ouvrir_navigateur = lambda dire=print: ("Chrome", self.nav)

        def jeton(cookies):
            self.essais += 1
            return reponses[min(self.essais, len(reponses)) - 1]
        ms.jeton_depuis_session = jeton
        return ms.connexion_navigateur(lambda t: None)

    def test_un_echec_passager_ne_conclut_pas(self):
        self.assertEqual(self.lancer(2, [(None, "absent"), (None, "reseau"), ("J", None)]), ("J", True))
        self.assertEqual(self.essais, 3)

    def test_refus_persistant_service_desactive(self):
        with self.assertRaises(ms.ServiceMobileDesactive):
            self.lancer(2, [(None, "absent")])
        self.assertEqual(self.essais, ms.ESSAIS_JETON)
        self.assertTrue(self.nav.ferme)

    def test_panne_reseau_n_accuse_pas_l_etablissement(self):
        with self.assertRaises(ms.Erreur) as c:
            self.lancer(2, [(None, "reseau")])
        self.assertNotIsInstance(c.exception, ms.ServiceMobileDesactive)
        self.assertEqual(str(c.exception), ms.MSG_JETON_RESEAU)

    def test_theme_inconnu_pas_connecte_attend(self):
        with self.assertRaises(ms.Erreur) as c:                   # jusqu'au delai, sans accuser le service
            self.lancer(1, [(None, "connexion")])
        self.assertNotIsInstance(c.exception, ms.ServiceMobileDesactive)
        self.assertIn("Connexion non terminee", str(c.exception))


class JetonDepuisSession(unittest.TestCase):
    def essai(self, resultat):
        class Ouvreur:
            def open(s, req, timeout=None):
                if isinstance(resultat, Exception):
                    raise resultat

                class R:
                    headers = {}
                return R
        sauve = urllib.request.build_opener, ms.BASE
        urllib.request.build_opener = lambda *a: Ouvreur()
        ms.BASE = "https://moodle.exemple.ch"
        try:
            return ms.jeton_depuis_session({"s": "v"})
        finally:
            urllib.request.build_opener, ms.BASE = sauve
            if isinstance(resultat, urllib.error.HTTPError):
                resultat.close()

    def http(self, code, location=None):
        h = email.message.Message()
        if location:
            h["Location"] = location
        return urllib.error.HTTPError("u", code, "m", h, None)

    def test_raisons(self):
        code = base64.b64encode(b"sig:::LEJETON:::prive").decode()
        self.assertEqual(self.essai(self.http(303, f"moodlemobile://token={code}")), ("LEJETON", None))
        self.assertEqual(self.essai(self.http(303, "https://moodle.exemple.ch/login/index.php")), (None, "connexion"))
        self.assertEqual(self.essai(self.http(503)), (None, "reseau"))
        self.assertEqual(self.essai(OSError("coupure")), (None, "reseau"))
        self.assertEqual(self.essai(None), (None, "absent"))        # 200 sans redirection


def reponse(corps, type_="application/pdf", longueur="auto"):
    h = email.message.Message()
    h["Content-Type"] = type_
    if longueur is not None:
        h["Content-Length"] = str(len(corps) if longueur == "auto" else longueur)
    restes = [corps[i:i + 4] for i in range(0, len(corps), 4)]

    class R:
        headers = h

        def __enter__(s):
            return s

        def __exit__(s, *a):
            return False

        def read(s, n):
            return restes.pop(0) if restes else b""
    return R()


class Telechargement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(setattr, urllib.request, "urlopen", urllib.request.urlopen)
        self.partiel = os.path.join(self.tmp.name, "f.part")

    def servir(self, r):
        urllib.request.urlopen = lambda req, timeout=None: r

    def test_fichier_normal(self):
        self.servir(reponse(b"%PDF-contenu"))
        ms.recuperer("https://m/f.pdf", "t", self.partiel, attendu="application/pdf")
        with open(self.partiel, "rb") as f:
            self.assertEqual(f.read(), b"%PDF-contenu")

    def test_page_ou_json_a_la_place_du_fichier(self):
        for type_ in ("text/html; charset=utf-8", "application/json"):
            with self.subTest(type_=type_):
                self.servir(reponse(b'{"errorcode":"x"}', type_))
                with self.assertRaises(ms.Erreur):
                    ms.recuperer("https://m/f.pdf", "t", self.partiel, attendu="application/pdf")

    def test_vrai_fichier_html_de_cours_accepte(self):
        self.assertEqual(ms.type_attendu("page.html"), "text/html")
        self.servir(reponse(b"<html></html>", "text/html"))
        ms.recuperer("https://m/page.html", "t", self.partiel, attendu=ms.type_attendu("page.html"))
        self.assertTrue(os.path.exists(self.partiel))

    def test_mimetype_de_moodle_prioritaire(self):
        self.assertEqual(ms.type_attendu("sans_extension", "Application/PDF"), "application/pdf")
        self.assertEqual(ms.type_attendu("sans_extension"), "")

    def test_fichier_tronque(self):
        self.servir(reponse(b"%PDF", longueur=1000))
        with self.assertRaises(ms.Erreur) as c:
            ms.recuperer("https://m/f.pdf", "t", self.partiel, attendu="application/pdf")
        self.assertIn("incomplet", str(c.exception))

    def test_sans_longueur_annoncee_accepte(self):
        self.servir(reponse(b"%PDF-contenu", longueur=None))
        ms.recuperer("https://m/f.pdf", "t", self.partiel, attendu="application/pdf")

    def item(self, t=100):
        return {"cours": "C", "cid": 1, "dossier": "C", "section": "S", "sid": 1, "sous": "", "nom": "f.pdf",
                "url": "https://m/f.pdf", "taille": 5, "mime": "application/pdf", "t": t, "statut": None,
                "deduit": False, "biblio": False, "module": "resource"}

    def test_telecharger_ne_range_pas_et_reessaiera(self):
        dest = os.path.join(self.tmp.name, "dest")
        os.makedirs(dest)
        cfg = {"dest": dest, "token": "t", "statuts": False}
        self.servir(reponse(b"<html>erreur</html>", "text/html"))
        r = ms.telecharger([self.item()], cfg, dire=lambda t: None)
        self.assertEqual((r["erreurs"], r["neufs"]), (1, 0))
        fichiers = [f for _, _, fs in os.walk(dest) for f in fs if not f.startswith(".moodlesync")]
        self.assertEqual(fichiers, [])
        self.servir(reponse(b"%PDF-vrai"))
        r = ms.telecharger([self.item()], cfg, dire=lambda t: None)
        self.assertEqual((r["erreurs"], r["neufs"]), (0, 1))

    def test_republication_erronee_garde_l_ancien_fichier(self):
        dest = os.path.join(self.tmp.name, "dest")
        os.makedirs(dest)
        cfg = {"dest": dest, "token": "t", "statuts": False}
        self.servir(reponse(b"%PDF-v1"))
        chemin = ms.telecharger([self.item(100)], cfg, dire=lambda t: None)["liste_neufs"][0][1]
        self.servir(reponse(b"<html>erreur</html>", "text/html"))
        r = ms.telecharger([self.item(200)], cfg, dire=lambda t: None)
        self.assertEqual((r["erreurs"], r["maj"]), (1, 0))
        with open(chemin, "rb") as f:
            self.assertEqual(f.read(), b"%PDF-v1")


class AdressePendantLecture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        sauve = ms.APP_DIR, ms.CONFIG, ms.verifier_site, ms.ERREURS, m.PREFS, m.analyser, m.analyser_audit

        def retablir():
            ms.APP_DIR, ms.CONFIG, ms.verifier_site, ms.ERREURS, m.PREFS, m.analyser, m.analyser_audit = sauve
            ms.appliquer_config(ms.charger_config())
        self.addCleanup(retablir)
        ms.APP_DIR, ms.CONFIG, ms.ERREURS = d, os.path.join(d, "config.json"), os.path.join(d, "erreurs.txt")
        m.PREFS = os.path.join(d, "prefs.json")
        ms.verifier_site = lambda base: None
        ms.sauver_config({**ms.charger_config(), "site": "https://ancien.exemple.ch", "token": "J", "dest": d})
        m.sauver_prefs({"active": True})
        self.api = app.Api()

    def test_refuse_pendant_actualisation_et_audit(self):
        vus = []

        def lecture(*a, **k):
            vus.append(self.api.sync_site("https://nouveau.exemple.ch", True))
            raise ms.Erreur("fin de l'essai")
        m.analyser = m.analyser_audit = lecture
        self.api.actualiser()
        self.api.audit()
        self.assertEqual(len(vus), 2)
        for r in vus:
            self.assertIn("erreur", r)
        c = ms.charger_config()
        self.assertEqual((c["site"], c["token"]), ("https://ancien.exemple.ch", "J"))

    def test_accepte_apres_la_lecture_meme_si_elle_a_echoue(self):
        def lecture(*a, **k):
            raise ms.Erreur("panne")
        m.analyser = lecture
        self.api.actualiser()
        self.assertEqual(self.api._lectures, 0)
        self.assertTrue(self.api.sync_site("https://nouveau.exemple.ch", True).get("ok"))
        self.assertEqual(ms.charger_config()["site"], "https://nouveau.exemple.ch")


class Reglages(unittest.TestCase):
    def test_sauver_prefs_atomique(self):
        with tempfile.TemporaryDirectory() as d:
            sauve = ms.APP_DIR, m.PREFS
            ms.APP_DIR, m.PREFS = d, os.path.join(d, "prefs.json")
            try:
                m.sauver_prefs({"a": 1})
                with self.assertRaises(TypeError):
                    m.sauver_prefs({"a": object()})               # echec en cours d'ecriture
                self.assertEqual(m.charger_prefs(), {"a": 1})
            finally:
                ms.APP_DIR, m.PREFS = sauve


if __name__ == "__main__":
    unittest.main()
