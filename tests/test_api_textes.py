"""Tests hors ligne du mixin ApiTextes (moodlesync/api_textes.py) et de son branchement dans application.py.

Aucune fenetre, aucun reseau, aucun vrai moteur : les fonctions du moteur d'extraction sont remplacees par des
doublures, les reglages et le journal d'erreurs vont dans un dossier temporaire, les PDF sont fabriques a la main.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t . -v
"""
import json, os, sys, tempfile, threading, time, unittest
from types import SimpleNamespace
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import api_textes, application as app, moteur as ms, ocr

COURS = [{"id": 11, "fullname": "Histoire des idées politiques (2026-2027)", "shortname": "COURS_HIP"}]

# Bloc moteur de la forme 3.1 (detecter) : un moteur present, deux langues et osd.
BLOC_MOTEUR = {"present": True, "version": "5.5.3", "source": "path", "exe": os.path.join("faux", "tesseract.exe"),
               "langues": ["eng", "fra", "osd"], "langues_effectives": "fra+eng", "repli": False,
               "message": "", "tessdata": "", "majeure": 5}

ENTETE_TSV = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
TSV = "\r\n".join([ENTETE_TSV,
                   "5\t1\t1\t1\t1\t1\t100\t10\t50\t20\t91.0\tBonjour",
                   "5\t1\t1\t1\t1\t2\t160\t10\t60\t20\t89.0\tle",
                   "5\t1\t1\t1\t1\t3\t230\t10\t40\t20\t93.0\tmonde"]) + "\r\n"


def pdf_minimal(pages):
    """PDF fabrique a la main. pages = liste de (lignes de texte, avec_image). Helvetica WinAnsi."""
    import io

    def echapper(t):
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objets = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
              3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
              4: (b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray "
                  b"/BitsPerComponent 8 /Length 1 >>\nstream\n\xff\nendstream")}
    ids = [5 + 2 * i for i in range(len(pages))]
    objets[2] = f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in ids)}] /Count {len(pages)} >>".encode()
    for i, (lignes, image) in enumerate(pages):
        flux = "q 100 0 0 100 50 500 cm /Im1 Do Q\n" if image else ""
        if lignes:
            flux += "BT /F1 12 Tf 50 750 Td 14 TL\n" + "".join(f"({echapper(l)}) Tj T*\n" for l in lignes) + "ET\n"
        donnees = flux.encode("cp1252")
        ressources = "/Font << /F1 3 0 R >>" + (" /XObject << /Im1 4 0 R >>" if image else "")
        objets[5 + 2 * i] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {6 + 2 * i} 0 R "
                             f"/Resources << {ressources} >> >>").encode()
        objets[6 + 2 * i] = f"<< /Length {len(donnees)} >>\nstream\n".encode() + donnees + b"\nendstream"
    sortie = io.BytesIO()
    sortie.write(b"%PDF-1.4\n")
    positions = {}
    for n in sorted(objets):
        positions[n] = sortie.tell()
        sortie.write(f"{n} 0 obj\n".encode() + objets[n] + b"\nendobj\n")
    debut_xref = sortie.tell()
    sortie.write(f"xref\n0 {len(objets) + 1}\n0000000000 65535 f \n".encode())
    for n in sorted(objets):
        sortie.write(f"{positions[n]:010d} 00000 n \n".encode())
    sortie.write(f"trailer\n<< /Size {len(objets) + 1} /Root 1 0 R >>\nstartxref\n{debut_xref}\n%%EOF\n".encode())
    return sortie.getvalue()


class FauxFenetre:
    """Fenetre pywebview simulee : enregistre ce que la page recevrait, repond aux boites de dialogue."""

    def __init__(self, choix=None):
        self.appels = []
        self.choix = choix

    def evaluate_js(self, code):
        self.appels.append(code)

    def create_file_dialog(self, *a, **k):
        return self.choix


class Base(unittest.TestCase):
    """Reglages et journal dans un dossier temporaire, moteur simule, coffre avec deux dossiers de cours."""

    RESEAU = ("infos_session", "cours_inscrits", "resume_cours", "collecte", "telecharger",
              "ecrire_liens", "ecrire_note", "verifier_site", "regler_demarrage", "api")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = self.tmp.name
        self.dest = os.path.join(self.d, "coffre")
        os.makedirs(self.dest)
        self.fenetre = FauxFenetre()
        self.delai_page = 0.0                  # duree simulee d'une page
        self.travaux = 0                       # pages en cours, toutes doublures confondues
        self.max_travaux = 0
        self.pages_vues = []                   # (exe, image temporaire) de chaque reconnaissance
        self.rendus = []
        self.verrou = threading.Lock()
        self.bloc = dict(BLOC_MOTEUR)
        self.dernier_compte = None
        self.pendant_sync = {}
        self.sauve = {n: getattr(ms, n) for n in self.RESEAU + ("APP_DIR", "CONFIG", "DEMARRAGE", "ERREURS")}
        self.addCleanup(self.restaurer)
        ms.APP_DIR, ms.CONFIG = self.d, os.path.join(self.d, "config.json")
        ms.DEMARRAGE, ms.ERREURS = os.path.join(self.d, "demarrage.lnk"), os.path.join(self.d, "erreurs.txt")

        def interdit(*a, **k):
            raise AssertionError("appel reseau non prevu")
        ms.api = interdit
        ms.infos_session = lambda tok: {"fullname": "Ada Lovelace", "userid": 7}
        ms.cours_inscrits = lambda tok, uid: COURS
        ms.resume_cours = lambda tok, cours, etat=None: [
            {"id": c["id"], "nom": c["fullname"], "shortname": c["shortname"], "nb": 1, "taille": 10, "nouveaux": 0}
            for c in cours]
        ms.collecte = lambda tok, cours, cfg, dire=print, liens=None, arreter=None: [{"cid": c["id"]} for c in cours]
        ms.telecharger = self.telecharger
        ms.ecrire_liens = lambda liens, dest, dire=print: []
        ms.ecrire_note = lambda r: None
        ms.verifier_site = lambda base: None
        ms.regler_demarrage = lambda actif: None
        self.configurer({"site": "https://moodle.exemple.ch", "token": "jeton", "dest": self.dest,
                         "cours": {"11": {"dossier": "Cours A", "choisi": True}}})
        for cible, nom, valeur in ((ocr, "detecter", lambda cfg: dict(self.bloc)),
                                   (ocr, "executer", self.executer),
                                   (ocr, "rendre_page", self.rendre)):
            p = mock.patch.object(cible, nom, valeur)
            p.start()
            self.addCleanup(p.stop)
        self.api = app.Api()
        self.api._fenetre = self.fenetre

    def restaurer(self):
        for nom, valeur in self.sauve.items():
            setattr(ms, nom, valeur)

    # -- doublures
    def executer(self, args, *, delai, arreter=None):
        """Reconnaissance simulee : instantanee, ou `delai_page` secondes, avec compteur de pages en cours."""
        with self.verrou:
            self.travaux += 1
            self.max_travaux = max(self.max_travaux, self.travaux)
        try:
            self.pages_vues.append((args[0], args[1]))
            if self.delai_page:
                time.sleep(self.delai_page)
            return 0, TSV.encode("utf-8"), b""
        finally:
            with self.verrou:
                self.travaux -= 1

    def rendre(self, chemin, numero, dpi, **kw):
        from PIL import Image
        self.rendus.append((chemin, numero, dpi, kw.get("preparer", True)))
        return Image.new("L", (120, 60), 255)

    def telecharger(self, items, cfg, dire=print, progres=None, arreter=None):
        """Synchronisation simulee : releve ce qui tourne pendant qu'elle tient les fichiers."""
        vus = {"travaux": self.travaux, "sync": self.api._sync_veut.is_set(),
               "fichiers": self.api._ocr_fichiers.locked(), "etat": ""}
        limite = time.monotonic() + 5
        while time.monotonic() < limite and getattr(self.api, "_ocr_etat_fil", "") != "pause_sync":
            time.sleep(0.01)
        vus["etat"] = getattr(self.api, "_ocr_etat_fil", "")
        self.pendant_sync = vus
        if progres:
            progres(1, len(items), "Cours A/S1/d0.pdf")
        compte = {"total": 1, "neufs": 1, "maj": 0, "doublons": 0, "erreurs": 0, "dest": cfg["dest"],
                  "liste_neufs": [("Cours A", os.path.join(cfg["dest"], "Cours A", "S1", "d0.pdf"))],
                  "liste_maj": [], "annule": False, "restants": {}, "generes": 0, "republies_generes": [],
                  "a_preparer": ["Cours A/S1/d0.pdf"]}
        self.dernier_compte = compte
        return compte

    # -- outils
    def configurer(self, c):
        with open(ms.CONFIG, "w", encoding="utf-8") as f:
            json.dump(c, f)

    def config(self):
        with open(ms.CONFIG, encoding="utf-8") as f:
            return json.load(f)

    def fichier(self):
        return ocr.charger_file(self.dest)

    def ranger(self, rel, pages):
        chemin = os.path.join(self.dest, *rel.split("/"))
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(pdf_minimal(pages))
        return chemin

    def instantane(self):
        """Tout ce que contient le coffre : chemins, tailles, dates de modification et octets."""
        etat = {}
        for racine, dossiers, fichiers in os.walk(self.dest):
            for nom in dossiers:
                etat[os.path.relpath(os.path.join(racine, nom), self.dest) + "/"] = b""
            for nom in fichiers:
                chemin = os.path.join(racine, nom)
                with open(chemin, "rb") as f:
                    etat[os.path.relpath(chemin, self.dest)] = f.read()
        return etat

    def attendre(self, condition, delai=15):
        limite = time.monotonic() + delai
        while time.monotonic() < limite:
            if condition():
                return True
            time.sleep(0.02)
        return False

    def json_ok(self, r):
        json.dumps(r)
        return r


class Formes(Base):
    """Formes de la section 2.7 et branchement du mixin."""

    def test_etat_forme(self):
        r = self.json_ok(self.api.ocr_etat())
        self.assertEqual(set(r), {"moteur", "active", "mode_pdf", "occupe", "file", "compteurs", "reglages"})
        self.assertEqual(set(r["moteur"]), {"present", "version", "source", "exe", "langues", "langues_effectives",
                                            "repli", "message"})
        self.assertEqual(set(r["file"]), {"etat", "document", "page", "pages", "documents_faits", "documents_total",
                                          "reprise"})
        self.assertEqual(set(r["compteurs"]), {"documents", "pages", "a_verifier", "a_preparer", "pages_a_preparer",
                                               "octets_texte", "orphelins"})
        self.assertEqual(set(r["reglages"]), {"ocr_langues", "ocr_dpi"})
        self.assertTrue(r["moteur"]["present"])
        self.assertFalse(r["active"])
        self.assertEqual(r["mode_pdf"], "aucun")
        self.assertFalse(r["occupe"])

    def test_sync_etat_bloc_ocr(self):
        r = self.json_ok(self.api.sync_etat())
        self.assertEqual(set(r["ocr"]), {"moteur", "active", "a_preparer", "en_attente", "pret", "a_verifier",
                                         "reprise"})
        self.assertTrue(r["ocr"]["moteur"])
        self.assertFalse(r["ocr"]["active"])
        self.assertEqual(r["ocr"]["pret"], 0)

    def test_mixin_branche(self):
        self.assertIsInstance(self.api, api_textes.ApiTextes)
        for nom in ("_ocr_verrou", "_ocr_fichiers", "_ocr_fil", "_ocr_arret", "_ocr_pause", "_sync_veut"):
            self.assertTrue(hasattr(self.api, nom), nom)
        self.assertIsInstance(self.api._ocr_verrou, type(threading.RLock()))
        self.assertIsInstance(self.api._ocr_fichiers, type(threading.Lock()))
        self.assertIsInstance(self.api._sync_veut, threading.Event)
        self.assertFalse(self.api._ocr_arret.is_set())
        for nom in ("ocr_etat", "ocr_detecter", "ocr_choisir_exe", "ocr_installer", "ocr_apercu", "ocr_lancer",
                    "ocr_pause", "ocr_reprendre", "ocr_annuler", "ocr_pdf_restaurer", "ocr_regler"):
            self.assertTrue(callable(getattr(self.api, nom, None)), nom)
        self.assertIsNone(self.api._ocr_fil)

    def test_compteurs_du_cache(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        with mock.patch.object(ocr, "detecter", lambda cfg: dict(self.bloc)):
            ocr.extraire_document(self.dest, "Cours A/S1/scan.pdf", {})
        r = self.json_ok(self.api.ocr_etat())
        self.assertEqual(r["compteurs"]["documents"], 1)
        self.assertEqual(r["compteurs"]["pages"], 1)
        self.assertGreater(r["compteurs"]["octets_texte"], 0)
        self.assertEqual(self.api.sync_etat()["ocr"]["pret"], 1)


class ApercuT24(Base):
    """T24 : l'apercu n'ecrit rien, ne met rien en file."""

    def test_apercu_sans_ecriture(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)] * 2)
        ocr.sauver_file(self.dest, {"version": 1, "etat": "pause", "portee": "sans_texte",
                                    "cree": "2026-11-08T10:00:00", "taches": []})
        avant = self.instantane()
        r = self.json_ok(self.api.ocr_apercu("Cours A/S1/scan.pdf", 2))
        self.assertEqual(self.instantane(), avant)
        self.assertTrue(r["image"].startswith("data:image/png;base64,"))
        self.assertLessEqual(r["largeur"], 900)
        self.assertGreater(r["hauteur"], 0)
        self.assertEqual(set(r), {"image", "largeur", "hauteur", "texte", "confiance", "qualite", "source",
                                  "chemin", "nom", "page", "exemple"})
        self.assertIn("Bonjour", r["texte"])
        self.assertEqual(r["qualite"], ocr.classer(r["confiance"]))
        self.assertEqual((r["chemin"], r["nom"], r["page"]), ("Cours A/S1/scan.pdf", "scan.pdf", 2))
        self.assertEqual(r["source"], "ocr")
        self.assertFalse(r["exemple"])
        self.assertEqual(self.rendus[-1][1], 2)                 # la page demandee est rendue

    def test_apercu_choisit_un_scan(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        r = self.json_ok(self.api.ocr_apercu())
        self.assertEqual((r["chemin"], r["page"]), ("Cours A/S1/scan.pdf", 1))

    def test_apercu_sans_moteur_ou_sans_scan_repond_un_exemple(self):
        self.bloc = dict(BLOC_MOTEUR, present=False, exe="", langues=[], langues_effectives="")
        self.api.ocr_detecter()                                   # la memoire du moteur est videe
        r = self.json_ok(self.api.ocr_apercu())
        self.assertTrue(r["exemple"])
        self.assertEqual(r["image"], "")
        self.assertEqual(r["texte"], "")
        self.assertFalse(r["confiance"])
        r = self.json_ok(self.api.ocr_apercu("Cours A/S1/absent.pdf"))
        self.assertTrue(r["exemple"])


class ErreursT26(Base):
    """T26 : chaque methode en erreur renvoie une phrase, sans trace technique."""

    def test_chaque_methode_en_erreur(self):
        def casse(*a, **k):
            raise RuntimeError("boum interne")
        appels = {"ocr_etat": lambda: self.api.ocr_etat(),
                  "ocr_detecter": lambda: self.api.ocr_detecter(),
                  "ocr_apercu": lambda: self.api.ocr_apercu(),
                  "ocr_lancer": lambda: self.api.ocr_lancer(),
                  "ocr_pause": lambda: self.api.ocr_pause(),
                  "ocr_reprendre": lambda: self.api.ocr_reprendre(),
                  "ocr_annuler": lambda: self.api.ocr_annuler(),
                  "ocr_pdf_restaurer": lambda: self.api.ocr_pdf_restaurer("Cours A/S1/scan.pdf"),
                  "ocr_regler": lambda: self.api.ocr_regler("ocr_dpi", 300)}
        with mock.patch.object(ms, "charger_config", casse):
            for nom, appel in appels.items():
                with self.subTest(methode=nom):
                    r = self.json_ok(appel())
                    self.assertIn("erreur", r, r)
                    self.assertIsInstance(r["erreur"], str)
                    self.assertNotIn("Traceback", r["erreur"])
                    self.assertNotIn("boum", r["erreur"])
                    self.assertNotIn("site-packages", r["erreur"])
                    self.assertNotIn(".py", r["erreur"])

    def test_erreurs_prevues_sont_des_phrases(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        self.assertEqual(self.api.ocr_pdf_restaurer("Cours A/S1/absent.pdf")["erreur"], ocr.MESSAGES["corrompu"])
        self.assertEqual(self.api.ocr_apercu("../secret.pdf")["erreur"], ocr.MESSAGES["corrompu"])
        self.assertEqual(self.api.ocr_regler("inconnu", 1)["erreur"], "Réglage inconnu : inconnu")
        self.assertEqual(self.api.ocr_installer(), {"erreur": api_textes._message("installation_indisponible")})


class ReglagesT31(Base):
    """T31 : liste blanche, bornes, mode copie refuse, consentement de remplacer."""

    def test_liste_blanche_et_bornes(self):
        a = self.api
        for cle, valeur in (("token", "x"), ("ocr_dpi", 100), ("ocr_dpi", 601), ("ocr_dpi", "beaucoup"),
                            ("ocr_psm", 2), ("ocr_psm", 0), ("ocr_max_mo", 9), ("ocr_max_mo", 2001),
                            ("ocr_threads", 0), ("ocr_threads", 5), ("ocr_batterie", "dormir"),
                            ("ocr_dossier", ".."), ("ocr_dossier", "A/B"), ("ocr_dossier", "Cours A"),
                            ("ocr_langues", "deu"), ("ocr_apres_sync", "peut-etre"),
                            ("ocr_exe", os.path.join(self.d, "absent.exe")), ("ocr", "peut-etre")):
            with self.subTest(cle=cle, valeur=valeur):
                r = self.json_ok(a.ocr_regler(cle, valeur))
                self.assertIn("erreur", r, r)
        self.assertFalse(self.config().get("ocr", False))

    def test_valeurs_acceptees(self):
        a = self.api
        self.assertEqual(self.json_ok(a.ocr_regler("ocr_dpi", 400))["reglages"]["ocr_dpi"], 400)
        self.assertEqual(self.config()["ocr_dpi"], 400)
        self.assertEqual(self.json_ok(a.ocr_regler("ocr_dossier", "Mes textes"))["reglages"]["ocr_dpi"], 400)
        self.assertEqual(self.config()["ocr_dossier"], "Mes textes")
        self.assertTrue(self.json_ok(a.ocr_regler("ocr", True))["active"])
        self.assertTrue(self.config()["ocr"])
        self.assertEqual(self.json_ok(a.ocr_regler("ocr_threads", 4))["file"]["etat"], "inactive")
        self.assertEqual(self.json_ok(a.ocr_regler("ocr_langues", "fra+osd"))["reglages"]["ocr_langues"], "fra+osd")
        self.assertTrue(self.json_ok(a.ocr_regler("ocr_apres_sync", False))["active"])
        self.assertFalse(self.config()["ocr_apres_sync"])
        exe = os.path.join(self.d, "tesseract.exe")
        open(exe, "wb").close()
        self.assertTrue(self.json_ok(a.ocr_regler("ocr_exe", exe))["moteur"]["present"])
        self.assertEqual(self.config()["ocr_exe"], exe)
        tess = os.path.join(self.d, "tessdata")
        os.makedirs(tess)
        self.assertTrue(self.json_ok(a.ocr_regler("ocr_tessdata", tess))["moteur"]["present"])

    def test_copie_refuse_et_remplacer_sous_consentement(self):
        a = self.api
        self.assertEqual(a.ocr_regler("ocr_pdf", "copie")["erreur"], api_textes._message("mode_indisponible"))
        self.assertEqual(a.ocr_regler("ocr_pdf", "autre")["erreur"], api_textes._message("mode_indisponible"))
        self.assertEqual(a.ocr_regler("ocr_pdf", "remplacer"),
                         {"confirmer": api_textes._message("consentement_remplacer")})
        self.assertNotIn("ocr_pdf", self.config())
        self.assertEqual(self.json_ok(a.ocr_regler("ocr_pdf", "remplacer", confirme=True))["mode_pdf"], "remplacer")
        self.assertEqual(self.config()["ocr_pdf"], "remplacer")
        self.assertEqual(self.json_ok(a.ocr_regler("ocr_pdf", "aucun"))["mode_pdf"], "aucun")

    def test_choisir_exe(self):
        a = self.api
        exe = os.path.join(self.d, "tesseract.exe")
        open(exe, "wb").close()
        faux = SimpleNamespace(OPEN_DIALOG=10, FOLDER_DIALOG=20)   # pywebview n'est pas importe par les tests
        a._fenetre = None
        with mock.patch.dict(sys.modules, {"webview": faux}):      # l'import passe : c'est l'absence de fenetre qui repond
            self.assertIn("erreur", a.ocr_choisir_exe())           # fenetre pas encore ouverte
        a._fenetre = FauxFenetre(choix=[exe])
        with mock.patch.dict(sys.modules, {"webview": faux}):
            self.assertTrue(self.json_ok(a.ocr_choisir_exe())["moteur"]["present"])
        self.assertEqual(self.config()["ocr_exe"], exe)
        a._fenetre = FauxFenetre(choix=None)
        with mock.patch.dict(sys.modules, {"webview": faux}):
            self.assertEqual(a.ocr_choisir_exe(), {"annule": True})


class MiseEnFileT32(Base):
    """T32 : 50 documents et 500 pages au plus, confirmation au-dela, jamais sans fenetre."""

    def setUp(self):
        super().setUp()
        c = self.config()
        c.update({"ocr": True, "ocr_apres_sync": True})
        self.configurer(c)

    def preparer(self, nombre, pages=1):
        chemins = []
        for i in range(nombre):
            rel = f"Cours A/S{i % 5}/d{i}.pdf"
            self.ranger(rel, [([], True)] * pages)
            chemins.append(rel)
        return chemins

    def test_lot_de_50_demarre_seul(self):
        chemins = self.preparer(50)
        r = self.json_ok(self.api._ocr_apres_sync({"a_preparer": chemins}))
        self.assertEqual(r, {"a_preparer": 50})
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertEqual(len(ocr.charger_cache(self.dest)["documents"]), 50)

    def test_51_documents_attendent_la_confirmation(self):
        chemins = self.preparer(51)
        r = self.json_ok(self.api._ocr_apres_sync({"a_preparer": chemins}))
        self.assertEqual(r, {"a_preparer": 51})
        self.assertIsNone(self.api._ocr_fil)
        file = self.fichier()
        self.assertEqual(file["etat"], "inactive")
        self.assertEqual(len([t for t in file["taches"] if t["etat"] == "attente"]), 51)

    def test_500_pages_attendent_la_confirmation(self):
        chemins = self.preparer(3, pages=250)
        r = self.json_ok(self.api._ocr_apres_sync({"a_preparer": chemins}))
        self.assertEqual(r, {"a_preparer": 3})
        self.assertIsNone(self.api._ocr_fil)
        self.assertEqual(sum(t["pages"] for t in self.fichier()["taches"]), 750)

    def test_jamais_sans_fenetre(self):
        self.api._fenetre = None
        chemins = self.preparer(3)
        self.assertEqual(self.json_ok(self.api._ocr_apres_sync({"a_preparer": chemins})), {"a_preparer": 3})
        self.assertIsNone(self.api._ocr_fil)
        self.assertEqual(len(self.fichier()["taches"]), 3)

    def test_extraction_desactivee_ne_demarre_pas(self):
        c = self.config()
        c.update({"ocr": False})
        self.configurer(c)
        chemins = self.preparer(3)
        self.assertEqual(self.json_ok(self.api._ocr_apres_sync({"a_preparer": chemins})), {"a_preparer": 3})
        self.assertIsNone(self.api._ocr_fil)

    def test_apres_sync_desactive_ne_demarre_pas(self):
        """Mise en file faite, mais pas de demarrage : `ocr` vrai, `ocr_apres_sync` faux (D7, contrat 3.2)."""
        c = self.config()
        c.update({"ocr": True, "ocr_apres_sync": False})
        self.configurer(c)
        chemins = self.preparer(3)
        self.assertEqual(self.json_ok(self.api._ocr_apres_sync({"a_preparer": chemins})), {"a_preparer": 3})
        self.assertIsNone(self.api._ocr_fil)
        self.assertEqual(len(self.fichier()["taches"]), 3)

    def test_confirmation_au_dela_des_seuils(self):
        self.preparer(51)
        r = self.json_ok(self.api.ocr_lancer("tout"))
        self.assertIn("confirmer", r)
        self.assertEqual((r["documents"], r["pages"]), (51, 51))
        self.assertEqual(len(r["minutes"]), 2)
        self.assertLessEqual(r["minutes"][0], r["minutes"][1])
        self.assertIn("51 documents", r["confirmer"])
        self.assertIsNone(self.api._ocr_fil)
        r = self.json_ok(self.api.ocr_lancer("tout", confirme=True))
        self.assertIn("file", r)
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))

    def test_rien_a_faire(self):
        self.assertEqual(self.api.ocr_lancer("tout"), {"rien": True})


class SerialisationT23(Base):
    """T23 : la synchronisation passe avant l'extraction, jamais deux travaux a la fois."""

    def setUp(self):
        super().setUp()
        # Ecart 132 : le consentement est relu avant chaque document, la file s'arrete si `ocr` est faux.
        c = self.config()
        c.update({"ocr": True})
        self.configurer(c)

    def test_sync_pendant_extraction(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)] * 6)
        self.delai_page = 0.05
        self.api.sync_verifier()
        self.assertTrue("file" in self.api.ocr_lancer("tout"))
        self.assertTrue(self.attendre(lambda: self.pages_vues), "aucune page n'a demarre")
        r = self.json_ok(self.api.sync_lancer(True))
        self.assertIn("ocr", r["resultat"])
        self.assertEqual(self.pendant_sync["travaux"], 0)          # aucune page pendant la synchronisation
        self.assertTrue(self.pendant_sync["sync"])
        self.assertTrue(self.pendant_sync["fichiers"])
        self.assertEqual(self.pendant_sync["etat"], "pause_sync")
        self.assertEqual(self.max_travaux, 1)                       # jamais deux pages a la fois
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        cache = ocr.charger_cache(self.dest)["documents"]
        self.assertEqual(list(cache.values())[0]["pages"], 6)
        self.assertEqual(len(self.pages_vues), 6)

    def test_pause_et_reprise(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)] * 4)
        self.delai_page = 0.03
        self.api.ocr_lancer("tout")
        self.assertTrue(self.attendre(lambda: self.pages_vues))
        self.assertIn("file", self.api.ocr_pause())
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "pause"))
        faites = len(self.pages_vues)
        time.sleep(0.15)
        self.assertEqual(len(self.pages_vues), faites)               # plus aucune page pendant la pause
        self.assertIn("file", self.api.ocr_reprendre())
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertEqual(len(self.pages_vues), 4)

    def test_annuler(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)] * 4)
        self.delai_page = 0.03
        self.api.ocr_lancer("tout")
        self.assertTrue(self.attendre(lambda: self.pages_vues))
        self.assertIn("file", self.api.ocr_annuler())
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "annulee"))
        self.assertEqual([t["etat"] for t in self.fichier()["taches"]], ["attente"])


class Branchements(Base):
    """Ecarts 112 et 114 : les quatre fonctions de Y2 recoivent leur appelant."""

    def test_lancement_supprime_les_parts_puis_reconcilie(self):
        appels = []

        def parts(dest):
            appels.append("parts")
            return 0

        def reconcilier(dest):
            appels.append("reconcilier")
            return 0
        with mock.patch.object(ocr, "supprimer_parts_orphelins", parts), \
                mock.patch.object(ocr, "reconcilier_etat", reconcilier):
            app.Api()
        self.assertEqual(appels, ["parts", "reconcilier"])

    def test_sync_appelle_mise_en_file_apres_sync(self):
        self.api.sync_verifier()
        recu = {}

        def mise_en_file(dest, cfg, compte_rendu):
            recu.update({"dest": dest, "compte": compte_rendu, "ocr": cfg.get("ocr")})
            return 2
        with mock.patch.object(ocr, "mettre_en_file_apres_sync", mise_en_file):
            r = self.json_ok(self.api.sync_lancer(True))
        self.assertEqual(recu["dest"], self.dest)
        self.assertIs(recu["compte"], self.dernier_compte)          # le compte rendu de telecharger
        self.assertIsNone(recu["ocr"])                               # appele meme extraction desactivee
        self.assertEqual(r["resultat"]["ocr"], {"a_preparer": 2})

    def test_pdf_restaurer_relaie(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        recu = {}

        def restaurer(dest, cfg, chemin_rel, *, confirme=False, arreter=None):
            recu.update({"dest": dest, "chemin": chemin_rel, "confirme": confirme,
                         "sync": self.api._sync_veut.is_set(), "fichiers": self.api._ocr_fichiers.locked()})
            return {"confirmer": ocr.MESSAGES["modifie_main"]}
        with mock.patch.object(ocr, "restaurer", restaurer):
            r = self.api.ocr_pdf_restaurer("Cours A/S1/scan.pdf")
        self.assertEqual(r, {"confirmer": ocr.MESSAGES["modifie_main"]})
        self.assertEqual(recu, {"dest": self.dest, "chemin": "Cours A/S1/scan.pdf", "confirme": False,
                                "sync": True, "fichiers": True})

        with mock.patch.object(ocr, "restaurer", lambda *a, **k: {"ok": True, "pages": 3}):
            self.assertEqual(self.api.ocr_pdf_restaurer("Cours A/S1/scan.pdf", True), {"ok": True, "pages": 3})
        with mock.patch.object(ocr, "restaurer", lambda *a, **k: recu.update(confirme=k.get("confirme")) or {"ok": True, "pages": 1}):
            self.api.ocr_pdf_restaurer("Cours A/S1/scan.pdf", True)
        self.assertTrue(recu["confirme"])

        def hors_ligne(*a, **k):
            raise ocr.ErreurOcr("hors_ligne")
        with mock.patch.object(ocr, "restaurer", hors_ligne):
            self.assertEqual(self.api.ocr_pdf_restaurer("Cours A/S1/scan.pdf")["erreur"], ocr.MESSAGES["hors_ligne"])

        def expiree(*a, **k):
            raise ms.SessionExpiree("expiree")
        with mock.patch.object(ocr, "restaurer", expiree):
            r = self.api.ocr_pdf_restaurer("Cours A/S1/scan.pdf")
        self.assertIn("session Moodle a expiré", r["erreur"])
        self.assertNotIn("Traceback", r["erreur"])


class ErreursDeDocument(Base):
    """Un document en erreur n'arrete pas la file (invariant 9)."""

    def setUp(self):
        super().setUp()
        # Ecart 132 : le consentement est relu avant chaque document, la file s'arrete si `ocr` est faux.
        c = self.config()
        c.update({"ocr": True})
        self.configurer(c)

    def test_document_en_erreur_n_arrete_pas_la_file(self):
        self.ranger("Cours A/S1/abime.pdf", [([], True)])
        self.ranger("Cours A/S1/bon.pdf", [([], True)])
        appels = []

        def traiter(dest, chemin_rel, cfg, **kw):
            appels.append(chemin_rel)
            if chemin_rel.endswith("abime.pdf"):
                raise ocr.ErreurOcr("corrompu")
            return {"entree": {"pages": 1}, "pdf": "aucun", "message": ""}
        with mock.patch.object(ocr, "traiter_document", traiter):
            self.api.ocr_lancer("tout")
            self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        taches = {t["chemin"]: t for t in self.fichier()["taches"]}
        self.assertEqual(appels, ["Cours A/S1/abime.pdf", "Cours A/S1/bon.pdf"])
        self.assertEqual({c: t["etat"] for c, t in taches.items()},
                         {"Cours A/S1/abime.pdf": "erreur", "Cours A/S1/bon.pdf": "fait"})
        self.assertEqual(taches["Cours A/S1/abime.pdf"]["message"], ocr.MESSAGES["corrompu"])
        self.assertIn("textesJournal", " ".join(self.fenetre.appels))     # la phrase part au journal
        self.assertNotIn("Traceback", " ".join(self.fenetre.appels))


class FileRelue(Base):
    """Ecarts 130, 131 et 132 : la file du disque fait foi, le remplacement tient le verrou des fichiers, le
    consentement est relu avant chaque document."""

    def setUp(self):
        super().setUp()
        c = self.config()
        c.update({"ocr": True, "ocr_apres_sync": True})
        self.configurer(c)

    def telecharger(self, items, cfg, dire=print, progres=None, arreter=None):
        """Synchronisation simulee qui ecrit un nouveau document et l'annonce au compte rendu."""
        self.ranger("Cours A/S1/nouveau.pdf", [([], True)])
        compte = Base.telecharger(self, items, cfg, dire, progres, arreter)
        compte["a_preparer"] = ["Cours A/S1/nouveau.pdf"]
        return compte

    def test_sync_pendant_extraction_garde_la_tache_ajoutee(self):
        """Ecart 130 : la tache ajoutee par la synchronisation survit aux ecritures du fil et est traitee."""
        self.ranger("Cours A/S1/scan.pdf", [([], True)] * 6)
        self.delai_page = 0.05
        self.api.sync_verifier()
        self.assertIn("file", self.api.ocr_lancer("tout"))
        self.assertTrue(self.attendre(lambda: self.pages_vues), "aucune page n'a demarre")
        r = self.json_ok(self.api.sync_lancer(True))
        self.assertEqual(r["resultat"]["ocr"], {"a_preparer": 1})
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        etats = {t["chemin"]: t["etat"] for t in self.fichier()["taches"]}
        self.assertEqual(etats, {"Cours A/S1/scan.pdf": "fait", "Cours A/S1/nouveau.pdf": "fait"})
        self.assertEqual(len(ocr.charger_cache(self.dest)["documents"]), 2)

    def test_remplacement_sous_verrou_des_fichiers(self):
        """Ecart 131 : `fabriquer_pdf_cherchable` est appelee sous `_ocr_fichiers`, pas apres la derniere page."""
        c = self.config()
        c.update({"ocr_pdf": "remplacer"})
        self.configurer(c)
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        vus = {}

        def fabriquer(dest, chemin_rel, cfg, *, arreter=None):
            vus["fichiers"] = self.api._ocr_fichiers.locked()
            return {"remplace": chemin_rel}

        with mock.patch.object(ocr, "fabriquer_pdf_cherchable", fabriquer):
            self.assertIn("file", self.api.ocr_lancer("tout"))
            self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertEqual(vus.get("fichiers"), True)

    def test_ocr_desactive_pendant_extraction_arrete_la_file(self):
        """Ecart 132 : `ocr` relu avant chaque document ; faux, la file s'arrete en `annulee`."""
        self.ranger("Cours A/S1/a.pdf", [([], True)] * 6)
        self.ranger("Cours A/S1/b.pdf", [([], True)] * 6)
        self.delai_page = 0.05
        self.assertIn("file", self.api.ocr_lancer("tout"))
        self.assertTrue(self.attendre(lambda: self.pages_vues))
        self.assertIn("active", self.api.ocr_regler("ocr", False))
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "annulee"))
        etats = {t["chemin"]: t["etat"] for t in self.fichier()["taches"]}
        self.assertEqual(etats, {"Cours A/S1/a.pdf": "fait", "Cours A/S1/b.pdf": "attente"})
        self.assertEqual(len(ocr.charger_cache(self.dest)["documents"]), 1)

    def test_mode_remplacer_retire_pendant_extraction(self):
        """Ecart 132 : `ocr_pdf` relu avant chaque document ; retire, le document suivant n'est pas remplace."""
        c = self.config()
        c.update({"ocr_pdf": "remplacer"})
        self.configurer(c)
        self.ranger("Cours A/S1/a.pdf", [([], True)] * 6)
        self.ranger("Cours A/S1/b.pdf", [([], True)])
        appels = []

        def fabriquer(dest, chemin_rel, cfg, *, arreter=None):
            appels.append(chemin_rel)
            return {"remplace": chemin_rel}

        self.delai_page = 0.05
        with mock.patch.object(ocr, "fabriquer_pdf_cherchable", fabriquer):
            self.assertIn("file", self.api.ocr_lancer("tout"))
            self.assertTrue(self.attendre(lambda: self.pages_vues))
            self.assertIn("mode_pdf", self.api.ocr_regler("ocr_pdf", "aucun"))
            self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertEqual(appels, ["Cours A/S1/a.pdf"])


class DureesAnnoncees(Base):
    """Ecart 133 et decision de Maxence : `ocr_threads` ne divise plus les durees annoncees."""

    def test_fourchette_sans_diviseur(self):
        for threads in (1, 2, 4):
            c = self.config()
            c.update({"ocr_threads": threads})
            self.configurer(c)
            self.assertEqual(self.api._ocr_minutes(3000, self.config()), [50, 150], threads)

    def test_restant_min_sans_diviseur(self):
        c = self.config()
        c.update({"ocr_threads": 4})
        self.configurer(c)
        self.api._ocr_etat_fil, self.api._ocr_page, self.api._ocr_pages = "en_cours", 0, 3000
        self.api._ocr_pousser(force=True)
        charge = json.loads(self.fenetre.appels[-1].split("(", 1)[1].rsplit(")", 1)[0])
        self.assertEqual(charge["restant_min"], 100)
        self.assertEqual((charge["page"], charge["pages"]), (0, 3000))


class RepriseArret138(Base):
    """Ecart 138, decision de Maxence : seul l'ajout de la synchronisation en cours fait repartir la file."""

    def preparer(self):
        """Une file en `pause` laissee par une session precedente, avec une tache en attente."""
        c = self.config()
        c.update({"ocr": True, "ocr_apres_sync": True})
        self.configurer(c)
        self.ranger("Cours A/S1/ancien.pdf", [([], True)])
        file = ocr.constituer_file(self.dest, c, "tout", False)
        file["etat"] = "pause"
        ocr.sauver_file(self.dest, file)
        self.assertEqual([t["etat"] for t in file["taches"]], ["attente"])

    def test_file_en_pause_ne_repart_pas_seule(self):
        self.preparer()
        self.assertEqual(self.json_ok(self.api._ocr_apres_sync({"a_preparer": []})), {"a_preparer": 0})
        self.assertIsNone(self.api._ocr_fil)
        self.assertEqual(self.fichier()["etat"], "pause")

    def test_ajout_de_la_synchronisation_fait_repartir(self):
        self.preparer()
        self.ranger("Cours A/S1/nouveau.pdf", [([], True)])
        r = self.json_ok(self.api._ocr_apres_sync({"a_preparer": ["Cours A/S1/nouveau.pdf"]}))
        self.assertEqual(r, {"a_preparer": 1})
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertEqual(len(ocr.charger_cache(self.dest)["documents"]), 2)


# ====================================================================== A2
class A2Base(Base):
    """Coffre prepare a la main : cache, .md deja ecrits, etat de synchronisation. Aucune extraction."""

    def setUp(self):
        super().setUp()
        self._cache = {}

    def poser(self, rel, pages=2, extraction="ocr", etat="ok", confiance=0.91, verifie=False, genere=False,
              fichier=True, sortie=None, date="2026-11-09T10:00:00"):
        """Une entree de cache (2.3), son document sur le disque et, si demande, un `genere` dans l'etat."""
        rel = ocr._cle(rel)
        sortie = sortie or f"Textes/{rel}.md"
        self._cache[rel] = {"empreinte": "sha256:0", "taille": 10, "pages": pages,
                            "pages_texte": pages if extraction == "texte" else 0,
                            "pages_ocr": pages if extraction == "ocr" else 0, "numeros_ocr": [],
                            "pages_vides": pages if extraction == "vide" else 0,
                            "extraction": extraction, "confiance": confiance, "langues": "fra+eng",
                            "dpi": 300, "psm": 3, "moteur": "5.5.3", "sortie": sortie, "etat": etat,
                            "verifie": verifie, "date": date}
        ocr.sauver_cache(self.dest, {"version": 1, "documents": self._cache})
        if fichier:
            self.ranger(rel, [([], True)])
        if genere:
            etat_sync = ms.charger_etat(self.dest)
            etat_sync[f"https://moodle.exemple.ch/{rel}"] = {
                "t": 1, "chemin": rel,
                "genere": {"type": "pdf_cherchable", "taille_source": 10, "empreinte_source": "sha256:1",
                           "taille_fichier": 11, "empreinte_fichier": "sha256:2", "pages": pages,
                           "date": date, "version": 1}}
            ms.sauver_etat(self.dest, etat_sync)
        return self._cache[rel]

    def md(self, rel, *textes, sortie=None):
        """Ecrit le .md d'un document, un marqueur et un texte par page (plan 6.1)."""
        sortie = sortie or f"Textes/{ocr._cle(rel)}.md"
        contenu = "".join(f"<!-- page {i} -->\n\n{texte}\n\n" for i, texte in enumerate(textes, 1))
        chemin = os.path.join(self.dest, *sortie.split("/"))
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenu)
        return sortie


class A2Coffre(A2Base):
    """Trois documents lisibles dans deux cours, pour la copie et l'export."""

    def setUp(self):
        super().setUp()
        self.poser("Cours A/S1/a.pdf", pages=2, extraction="ocr", confiance=0.92)
        self.md("Cours A/S1/a.pdf", "Page une.", "Page deux.")
        self.poser("Cours A/S1/b.pdf", pages=1, extraction="texte", confiance=None)
        self.md("Cours A/S1/b.pdf", "Page unique.")
        self.poser("Cours B/S1/c.pdf", pages=1, extraction="ocr", confiance=0.55)
        self.md("Cours B/S1/c.pdf", "Autre cours.")


class DocumentsA2(A2Base):
    """ocr_documents : forme 2.7, tri, filtres, lecture seule."""

    def setUp(self):
        super().setUp()
        self.poser("Cours B/S2/scan.pdf", pages=3, extraction="ocr", confiance=0.42, genere=True)
        self.poser("Cours A/S1/notes.pdf", pages=2, extraction="texte", confiance=None, verifie=True)
        self.poser("Cours A/S10/mixte.pdf", pages=4, extraction="mixte", confiance=0.77, etat="a_verifier")
        self.poser("Cours A/S2/vide.pdf", pages=1, extraction="vide", confiance=None, etat="a_verifier")

    def test_forme_et_tri(self):
        avant = self.instantane()
        r = self.json_ok(self.api.ocr_documents())
        self.assertEqual(self.instantane(), avant)                 # lecture seule
        self.assertEqual(set(r), {"documents", "total", "pages"})
        self.assertEqual((r["total"], r["pages"]), (4, 10))
        self.assertEqual([d["chemin"] for d in r["documents"]],
                         ["Cours A/S1/notes.pdf", "Cours A/S10/mixte.pdf", "Cours A/S2/vide.pdf",
                          "Cours B/S2/scan.pdf"])
        for ligne in r["documents"]:
            self.assertEqual(set(ligne), {"chemin", "cours", "section", "nom", "type", "pages", "qualite",
                                          "confiance", "cherchable", "verifie", "orphelin", "sortie", "date"})
        lignes = {d["chemin"]: d for d in r["documents"]}
        notes = lignes["Cours A/S1/notes.pdf"]
        self.assertEqual((notes["cours"], notes["section"], notes["nom"]), ("Cours A", "S1", "notes.pdf"))
        self.assertEqual((notes["type"], notes["qualite"], notes["confiance"], notes["verifie"]),
                         ("texte", "bon", None, True))
        self.assertEqual(notes["sortie"], "Textes/Cours A/S1/notes.pdf.md")
        self.assertFalse(notes["cherchable"])
        self.assertEqual((lignes["Cours A/S10/mixte.pdf"]["type"], lignes["Cours A/S10/mixte.pdf"]["qualite"]),
                         ("mixte", "a_verifier"))
        self.assertEqual((lignes["Cours A/S2/vide.pdf"]["type"], lignes["Cours A/S2/vide.pdf"]["qualite"]),
                         ("scanne", "vide"))
        scan = lignes["Cours B/S2/scan.pdf"]
        self.assertEqual((scan["type"], scan["qualite"], scan["confiance"]), ("scanne", "bon", 0.42))
        self.assertTrue(scan["cherchable"])
        self.assertFalse(scan["orphelin"])
        self.assertFalse(any(d["orphelin"] for d in r["documents"]))

    def test_genere_sans_fichier_et_orphelin(self):
        os.remove(os.path.join(self.dest, *"Cours B/S2/scan.pdf".split("/")))
        lignes = {d["chemin"]: d for d in self.api.ocr_documents()["documents"]}
        self.assertFalse(lignes["Cours B/S2/scan.pdf"]["cherchable"])
        self.assertTrue(lignes["Cours B/S2/scan.pdf"]["orphelin"])
        r = self.api.ocr_documents({"qualite": "orphelin"})
        self.assertEqual([d["chemin"] for d in r["documents"]], ["Cours B/S2/scan.pdf"])
        self.assertEqual(r["total"], 1)

    def test_filtres(self):
        tous = self.api.ocr_documents()
        self.assertEqual(tous["total"], 4)
        self.assertEqual(self.api.ocr_documents({"cours": 11})["total"], 3)       # 11 -> Cours A
        self.assertEqual(self.api.ocr_documents({"cours": "99"})["total"], 0)     # cours inconnu hors ligne
        self.assertEqual(self.api.ocr_documents({"cours": None})["total"], 4)
        self.assertEqual(self.api.ocr_documents({"qualite": "a_verifier"})["total"], 1)
        self.assertEqual(self.api.ocr_documents({"qualite": "vide"})["total"], 1)
        self.assertEqual(self.api.ocr_documents({"qualite": "bon"})["total"], 2)
        self.assertEqual(self.api.ocr_documents({"type": "texte"})["total"], 1)
        self.assertEqual(self.api.ocr_documents({"type": "scanne"})["total"], 2)
        self.assertEqual(self.api.ocr_documents({"type": "mixte"})["total"], 1)
        melange = self.api.ocr_documents({"cours": 11, "type": "scanne"})
        self.assertEqual([d["chemin"] for d in melange["documents"]], ["Cours A/S2/vide.pdf"])
        self.assertEqual(self.api.ocr_documents("pas un filtre")["total"], 4)


class ChercherA2(A2Base):
    """ocr_chercher : sans casse ni accents, une page par resultat, segments sans decalage."""

    def setUp(self):
        super().setUp()
        self.poser("Cours A/S1/economie.pdf", pages=3, extraction="ocr")
        self.md("Cours A/S1/economie.pdf", "L'économie politique étudie les choix.",
                "Une autre page sans le mot.", "L'ÉCONOMIE revient ici, et économie encore.")
        self.poser("Cours A/S1/verifier.pdf", pages=1, extraction="ocr")
        self.md("Cours A/S1/verifier.pdf", "Rien ici.")
        chemin = os.path.join(self.dest, "Textes", "Cours A", "S1", "verifier.pdf.md")
        with open(chemin, "a", encoding="utf-8", newline="\n") as f:
            f.write("## Pages à vérifier\n\n- page 1 : confiance 0,62\n")

    def test_texte_trop_court(self):
        vide = {"resultats": [], "total": 0, "tronque": False}
        for texte in ("", "a", " é", None, 3):
            with self.subTest(texte=texte):
                self.assertEqual(self.api.ocr_chercher(texte), vide)

    def test_sans_casse_ni_accents(self):
        avant = self.instantane()
        r = self.json_ok(self.api.ocr_chercher("economie"))
        self.assertEqual(self.instantane(), avant)
        self.assertEqual((r["total"], r["tronque"]), (2, False))
        self.assertEqual([(x["chemin"], x["page"]) for x in r["resultats"]],
                         [("Cours A/S1/economie.pdf", 1), ("Cours A/S1/economie.pdf", 3)])
        premier = r["resultats"][0]
        self.assertEqual(set(premier), {"chemin", "cours", "section", "nom", "page", "segments"})
        self.assertEqual((premier["cours"], premier["section"], premier["nom"]), ("Cours A", "S1", "economie.pdf"))
        segments = premier["segments"]
        self.assertTrue(segments)
        for segment in segments:
            self.assertEqual(set(segment), {"t", "m"})
            self.assertIsInstance(segment["t"], str)
            self.assertIsInstance(segment["m"], bool)
        self.assertEqual(sum(1 for s in segments if s["m"]), 1)
        self.assertEqual([s["t"] for s in segments if s["m"]][0].lower(), "économie")
        self.assertIn("politique", "".join(s["t"] for s in segments))

    def test_une_page_une_unite(self):
        r = self.api.ocr_chercher("economie")
        self.assertEqual(len([x for x in r["resultats"] if x["page"] == 3]), 1)

    def test_limite_et_tronque(self):
        r = self.api.ocr_chercher("economie", 1)
        self.assertEqual(len(r["resultats"]), 1)
        self.assertEqual((r["total"], r["tronque"]), (2, True))
        r = self.api.ocr_chercher("economie", 50)
        self.assertFalse(r["tronque"])

    def test_pages_a_verifier_exclues(self):
        self.assertEqual(self.api.ocr_chercher("confiance"), {"resultats": [], "total": 0, "tronque": False})

    def test_aucun_resultat(self):
        self.assertEqual(self.api.ocr_chercher("introuvable"), {"resultats": [], "total": 0, "tronque": False})


class CopierA2(A2Coffre):
    """ocr_copier : texte de C5, caracteres comptes ici, plafond, lecture seule."""

    def test_copie(self):
        avant = self.instantane()
        r = self.json_ok(self.api.ocr_copier("tout"))
        self.assertEqual(self.instantane(), avant)
        self.assertEqual(set(r), {"texte", "caracteres", "documents", "pages"})
        self.assertEqual(r["caracteres"], len(r["texte"]))
        self.assertEqual((r["documents"], r["pages"]), (3, 4))
        self.assertIn("[p. 1]", r["texte"])
        self.assertIn("[p. 2]", r["texte"])
        self.assertIn("Page une.", r["texte"])
        self.assertIn("# Cours A : texte des documents", r["texte"])
        self.assertIn("# Cours B : texte des documents", r["texte"])
        self.assertNotIn(ms.MARQUE, r["texte"])                     # pas de marque dans une copie

    def test_portees(self):
        r = self.api.ocr_copier("cours:11")
        self.assertEqual((r["documents"], r["pages"]), (2, 3))
        self.assertNotIn("Autre cours.", r["texte"])
        r = self.api.ocr_copier("document:Cours B/S1/c.pdf")
        self.assertEqual((r["documents"], r["pages"]), (1, 1))
        self.assertIn("Autre cours.", r["texte"])
        self.assertNotIn("Page une.", r["texte"])

    def test_portee_vide(self):
        self.assertEqual(self.api.ocr_copier("cours:99"),
                         {"texte": "", "caracteres": 0, "documents": 0, "pages": 0})

    def test_trop_long(self):
        long = "x" * (api_textes.TEXTE_MAX + 1)
        with mock.patch.object(ocr, "assembler_contexte", lambda *a, **k: long):
            r = self.json_ok(self.api.ocr_copier("tout"))
        self.assertEqual(r, {"trop_long": True, "caracteres": len(long)})


class ExporterA2(A2Coffre):
    """ocr_exporter : boite de dialogue native, zip, zip avec JSONL, Markdown, rien dans dest."""

    FAUX_WEBVIEW = SimpleNamespace(SAVE_DIALOG=30, FOLDER_DIALOG=20, OPEN_DIALOG=10)

    def exporter(self, portee, format="zip"):
        with mock.patch.dict(sys.modules, {"webview": self.FAUX_WEBVIEW}):
            return self.api.ocr_exporter(portee, format)

    def test_zip(self):
        cible = os.path.join(self.d, "export.zip")
        self.api._fenetre = FauxFenetre(choix=[cible])
        avant = self.instantane()
        r = self.json_ok(self.exporter("tout"))
        self.assertEqual(self.instantane(), avant)                  # rien n'est ecrit dans dest
        self.assertEqual(set(r), {"chemin", "octets", "documents"})
        self.assertEqual(r["chemin"], cible)
        self.assertEqual(r["octets"], os.path.getsize(cible))
        self.assertEqual(r["documents"], 3)
        import zipfile
        with zipfile.ZipFile(cible) as z:
            self.assertEqual(sorted(z.namelist()),
                             ["Cours A/S1/a.pdf.md", "Cours A/S1/b.pdf.md", "Cours B/S1/c.pdf.md"])
            self.assertIn(b"Page une.", z.read("Cours A/S1/a.pdf.md"))

    def test_zip_jsonl(self):
        cible = os.path.join(self.d, "export.zip")
        self.api._fenetre = FauxFenetre(choix=[cible])
        r = self.json_ok(self.exporter("tout", "zip_jsonl"))
        self.assertEqual(r["documents"], 3)
        import zipfile
        with zipfile.ZipFile(cible) as z:
            lignes = z.read("textes.jsonl").decode("utf-8").splitlines()
        self.assertEqual(len(lignes), 4)
        objets = [json.loads(ligne) for ligne in lignes]
        self.assertEqual(set(objets[0]), {"cours", "section", "fichier", "page", "source", "confiance", "texte"})
        self.assertEqual(sorted(o["page"] for o in objets if o["fichier"] == "a.pdf"), [1, 2])
        self.assertTrue(all(o["cours"] in ("Cours A", "Cours B") for o in objets))

    def test_md(self):
        cible = os.path.join(self.d, "contexte.md")
        self.api._fenetre = FauxFenetre(choix=[cible])
        r = self.json_ok(self.exporter("tout", "md"))
        self.assertEqual(r["documents"], 3)
        self.assertEqual(r["chemin"], cible)
        self.assertEqual(r["octets"], os.path.getsize(cible))
        with open(cible, encoding="utf-8") as f:
            contenu = f.read()
        self.assertIn("[p. 1]", contenu)
        self.assertIn("Page une.", contenu)

    def test_extension_ajoutee(self):
        cible = os.path.join(self.d, "sans_extension")
        self.api._fenetre = FauxFenetre(choix=cible)
        r = self.json_ok(self.exporter("tout"))
        self.assertEqual(r["chemin"], cible + ".zip")
        self.assertTrue(os.path.isfile(cible + ".zip"))

    def test_annule(self):
        self.api._fenetre = FauxFenetre(choix=None)
        self.assertEqual(self.exporter("tout"), {"annule": True})

    def test_fenetre_absente(self):
        self.api._fenetre = None
        self.assertIn("erreur", self.json_ok(self.exporter("tout")))

    def test_format_inconnu(self):
        self.api._fenetre = FauxFenetre(choix=[os.path.join(self.d, "x.tar")])
        r = self.json_ok(self.exporter("tout", "tar"))
        self.assertIn("erreur", r)
        self.assertNotIn("Traceback", r["erreur"])
        self.assertNotIn("site-packages", r["erreur"])


class OuvrirA2(A2Base):
    """ocr_ouvrir : .md, dossier, source ; tout chemin hors dest ou hors sortie est refuse."""

    def setUp(self):
        super().setUp()
        self.poser("Cours A/S1/scan.pdf", pages=1, extraction="ocr")
        self.md("Cours A/S1/scan.pdf", "Page un.")
        self.md_chemin = os.path.realpath(os.path.join(self.dest, "Textes", "Cours A", "S1", "scan.pdf.md"))

    def test_md(self):
        appels = []
        with mock.patch.object(app.m, "ouvrir_document", lambda chemin: appels.append(chemin) or "associe"):
            r = self.api.ocr_ouvrir("Textes/Cours A/S1/scan.pdf.md", 1)
        self.assertEqual(r, {"ok": True})
        self.assertEqual(appels, [self.md_chemin])

    def test_chemin_absolu_dans_dest(self):
        appels = []
        with mock.patch.object(app.m, "ouvrir_document", lambda chemin: appels.append(chemin) or "texte"):
            self.assertEqual(self.api.ocr_ouvrir(self.md_chemin), {"ok": True})
        self.assertEqual(appels, [self.md_chemin])

    def test_dossier(self):
        appels = []
        with mock.patch.object(ms, "ouvrir_dossier", lambda dossier: appels.append(dossier)):
            r = self.api.ocr_ouvrir("Textes")
        self.assertEqual(r, {"ok": True})
        self.assertEqual(appels, [os.path.realpath(os.path.join(self.dest, "Textes"))])

    def test_source(self):
        def interdit(*a, **k):
            raise AssertionError("un PDF d'origine ne s'ouvre pas comme un texte")
        with mock.patch.object(app.m, "ouvrir_document", interdit), mock.patch.object(ms, "ouvrir_dossier", interdit):
            self.assertEqual(self.api.ocr_ouvrir("Cours A/S1/scan.pdf"), {"source": True})

    def test_refus(self):
        def interdit(*a, **k):
            raise AssertionError("chemin refuse : rien ne doit s'ouvrir")
        chemins = ("../secret.pdf", "/etc/passwd", "C:x", "C:/x/y.pdf", ".moodlesync-ocr/cache.json",
                   "Textes/../../x", ".moodlesync.json", "Cours A/S1/absent.pdf")
        with mock.patch.object(app.m, "ouvrir_document", interdit), mock.patch.object(ms, "ouvrir_dossier", interdit):
            for chemin in chemins:
                with self.subTest(chemin=chemin):
                    r = self.json_ok(self.api.ocr_ouvrir(chemin))
                    self.assertEqual(r, {"erreur": ocr.MESSAGES["ouverture_refusee"]})   # A3, ecart 159 (etait `corrompu`)
                    self.assertNotIn("Traceback", r["erreur"])
        self.assertEqual(self.api.ocr_ouvrir(None)["erreur"], ocr.MESSAGES["ouverture_refusee"])


class ErreursT26A2(A2Base):
    """T26 etendu aux cinq methodes de A2 : une phrase, jamais de trace technique."""

    def test_les_cinq_methodes_en_erreur(self):
        def casse(*a, **k):
            raise RuntimeError("boum interne")
        appels = {"ocr_documents": lambda: self.api.ocr_documents(),
                  "ocr_chercher": lambda: self.api.ocr_chercher("texte"),
                  "ocr_copier": lambda: self.api.ocr_copier("tout"),
                  "ocr_exporter": lambda: self.api.ocr_exporter("tout"),
                  "ocr_ouvrir": lambda: self.api.ocr_ouvrir("Textes")}
        with mock.patch.object(ms, "charger_config", casse):
            for nom, appel in appels.items():
                with self.subTest(methode=nom):
                    r = self.json_ok(appel())
                    self.assertIn("erreur", r, r)
                    self.assertIsInstance(r["erreur"], str)
                    for interdit in ("Traceback", "boum", "site-packages", ".py"):
                        self.assertNotIn(interdit, r["erreur"])


class StructureA2(unittest.TestCase):
    """Invariant 6 : ni reseau ni webview en tete de module."""

    def test_aucun_reseau_et_webview_local(self):
        import ast
        with open(os.path.join(RACINE, "moodlesync", "api_textes.py"), encoding="utf-8") as f:
            arbre = ast.parse(f.read())
        fonctions = [n for n in ast.walk(arbre) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                noms = [a.name.split(".")[0] for a in noeud.names]
            elif isinstance(noeud, ast.ImportFrom):
                noms = [(noeud.module or "").split(".")[0]]
            else:
                continue
            for nom in noms:
                self.assertNotIn(nom, ("urllib", "socket", "http", "ssl", "requests"), nom)
                if nom == "webview":
                    self.assertTrue(any(noeud in list(ast.walk(f)) for f in fonctions),
                                    "import webview en tete de module")


# ====================================================================== A3
# Les tests de A3 nomment les phrases par leur code dans ocr.MESSAGES : un code absent echoue avec un message franc.
CODES_A3 = ("dossier_absent", "fenetre_fermee", "valeur_invalide", "reglage_inconnu", "chemin_introuvable",
            "dossier_pris", "occupe", "consentement_absent", "format_inconnu", "ouverture_refusee",
            "ouverture_impossible", "cible_dans_coffre", "confirmation_lot")
CODES_A1 = ("consentement_remplacer", "mode_indisponible", "installation_indisponible")


def phrase(test, code, **champs):
    """Phrase de ocr.MESSAGES pour `code`, ou echec franc si le code n'y est pas."""
    test.assertIn(code, ocr.MESSAGES, f"code {code} absent de ocr.MESSAGES")
    return ocr.MESSAGES[code].format(**champs) if champs else ocr.MESSAGES[code]


def motifs_des_phrases():
    """Un motif par phrase de ocr.MESSAGES, les champs {n}, {cle}... valant n'importe quel texte."""
    import re
    motifs = []
    for modele in ocr.MESSAGES.values():
        morceaux = re.split(r"\{[a-z_]+\}", modele)
        motifs.append(re.compile("^" + ".+".join(re.escape(m) for m in morceaux) + "$", re.S))
    return motifs


def phrase_permise(texte, motifs):
    """Une phrase visible vient de ocr.MESSAGES, ou de ms.message_erreur (« Texte des cours : ... »), ou de la
    session expiree de _proteger ; jamais de trace technique."""
    for interdit in ("Traceback", "site-packages", 'File "', ".py\"", ".py,", "line "):
        if interdit in texte:
            return False
    if texte.startswith(api_textes.ACTION + " : ") or texte == app.SESSION_EXPIREE:
        return True
    return any(m.match(texte) for m in motifs)


def messages_du_contrat():
    """{code: phrase} de la table de la section 5 de docs/ocr-contrat.md."""
    import re
    with open(os.path.join(RACINE, "docs", "ocr-contrat.md"), encoding="utf-8") as f:
        texte = f.read()
    debut = texte.index("## 5. Messages et vocabulaire")
    fin = texte.index("## 6.", debut)
    table = {}
    for ligne in texte[debut:fin].splitlines():
        m = re.match(r"^\| `([a-z_]+)` \| (.+) \|$", ligne)
        if m:
            table[m.group(1)] = m.group(2)
    return table


class ExportA3(A2Base):
    """Coffre de A2 plus l'outillage de la boite de dialogue d'export."""

    FAUX_WEBVIEW = SimpleNamespace(SAVE_DIALOG=30, FOLDER_DIALOG=20, OPEN_DIALOG=10)

    def setUp(self):
        super().setUp()
        self.poser("Cours A/S1/a.pdf", pages=2, extraction="ocr", confiance=0.92)
        self.md("Cours A/S1/a.pdf", "Page une.", "Page deux.")
        self.poser("Cours A/S1/b.pdf", pages=1, extraction="texte", confiance=None)
        self.md("Cours A/S1/b.pdf", "Page unique.")
        self.poser("Cours B/S1/c.pdf", pages=1, extraction="ocr", confiance=0.55)
        self.md("Cours B/S1/c.pdf", "Autre cours.")

    def exporter(self, portee, format="zip", choix=None):
        self.api._fenetre = FauxFenetre(choix=choix)
        with mock.patch.dict(sys.modules, {"webview": self.FAUX_WEBVIEW}):
            return self.json_ok(self.api.ocr_exporter(portee, format))

    def cible(self, nom):
        return os.path.join(self.d, nom)


class SegmentsA3(A2Base):
    """Ecarts 153, 154 et 156 : l'extrait garde ses espaces de bord, replie les blancs internes et trouve un terme
    de plusieurs mots coupe par un saut de ligne."""

    def chercher(self, page, terme):
        self.poser("Cours A/S1/p.pdf", pages=1, extraction="ocr")
        self.md("Cours A/S1/p.pdf", page)
        return self.json_ok(self.api.ocr_chercher(terme))

    def segments(self, page, terme):
        r = self.chercher(page, terme)
        self.assertEqual(r["total"], 1, r)
        return r["resultats"][0]["segments"]

    def test_espaces_de_bord_conserves(self):
        segments = self.segments("Le chat mange la souris dans la cuisine du voisin.", "mange")
        self.assertEqual(segments, [{"t": "Le chat ", "m": False}, {"t": "mange", "m": True},
                                    {"t": " la souris dans la cuisine du voisin.", "m": False}])
        self.assertEqual("".join(s["t"] for s in segments), "Le chat mange la souris dans la cuisine du voisin.")

    def test_blancs_internes_replies_blancs_de_bord_gardes(self):
        segments = self.segments("Le  chat\n\nmange   la\tsouris", "mange")
        self.assertEqual([s["t"] for s in segments], ["Le chat ", "mange", " la souris"])
        self.assertEqual([s["m"] for s in segments], [False, True, False])

    def test_terme_de_plusieurs_mots_coupe_par_un_saut_de_ligne(self):
        segments = self.segments("Intro sur la machine\nlearning et ses usages.", "machine learning")
        self.assertEqual(segments, [{"t": "Intro sur la ", "m": False}, {"t": "machine learning", "m": True},
                                    {"t": " et ses usages.", "m": False}])

    def test_terme_coupe_par_une_suite_de_blancs(self):
        for coupure in ("machine   learning", "machine\n\n  learning", "machine\t\r\nlearning", "machine\u00a0learning"):
            with self.subTest(coupure=coupure):
                segments = self.segments(f"Sur la {coupure} aujourd'hui.", "machine learning")
                self.assertEqual([s["t"] for s in segments if s["m"]], ["machine learning"])
                self.assertEqual("".join(s["t"] for s in segments), "Sur la machine learning aujourd'hui.")

    def test_aiguille_avec_blancs_irreguliers(self):
        for terme in ("machine learning", "machine\nlearning", "  MACHINE   Learning  ", "machine\t\tlearning"):
            with self.subTest(terme=terme):
                segments = self.segments("La machine learning et la machine\nlearning.", terme)
                self.assertEqual(sum(1 for s in segments if s["m"]), 1)

    def test_sans_decalage_avec_accents_et_saut_de_ligne(self):
        segments = self.segments("L'économie\npolitique étudie les choix.", "economie politique")
        self.assertEqual(segments, [{"t": "L'", "m": False}, {"t": "économie politique", "m": True},
                                    {"t": " étudie les choix.", "m": False}])

    def test_deux_pages_comptees_que_le_blanc_soit_un_espace_ou_un_saut(self):
        self.poser("Cours A/S1/p.pdf", pages=2, extraction="ocr")
        self.md("Cours A/S1/p.pdf", "Le machine learning ici.", "Le machine\nlearning ici.")
        r = self.api.ocr_chercher("machine learning")
        self.assertEqual((r["total"], [x["page"] for x in r["resultats"]]), (2, [1, 2]))

    def test_marque_combinante_apres_le_terme(self):
        import unicodedata
        page = unicodedata.normalize("NFD", "Un café chaud.")
        for terme in ("café", unicodedata.normalize("NFD", "café"), "cafe"):
            with self.subTest(terme=terme):
                segments = self.segments(page, terme)
                self.assertEqual([s["t"] for s in segments],
                                 ["Un ", unicodedata.normalize("NFD", "café"), " chaud."])
                self.assertEqual("".join(s["t"] for s in segments), page)

    def test_marque_combinante_apres_le_contexte(self):
        import unicodedata
        page = unicodedata.normalize("NFD", "x" * 10 + "cible" + "é" * 41)
        segments = self.segments(page, "cible")
        self.assertEqual(segments[-1], {"t": "e\u0301" * 40, "m": False})     # la derniere lettre garde sa marque
        self.assertEqual("".join(s["t"] for s in segments), "x" * 10 + "cible" + "e\u0301" * 40)

    def test_pliage_rapide_identique_au_pliage_par_caractere(self):
        import random, unicodedata
        for point in range(0x110000):
            if 0xD800 <= point <= 0xDFFF:
                continue
            c = chr(point)
            self.assertEqual(api_textes._plier_vite(c), api_textes._pliage(c)[0], hex(point))
        hasard = random.Random(3)
        alphabet = "aAéÉe\u0301ßﬁİœ \n\t\u00a0xZ1.\u0301\u0327"
        for _ in range(3000):
            texte = "".join(hasard.choice(alphabet) for _ in range(hasard.randint(0, 30)))
            self.assertEqual(api_textes._plier_vite(texte), api_textes._pliage(texte)[0], repr(texte))

    def test_les_pages_sans_le_terme_ne_sont_pas_pliees_par_caractere(self):
        self.poser("Cours A/S1/p.pdf", pages=4, extraction="ocr")
        self.md("Cours A/S1/p.pdf", "Rien ici.", "Le mot cherché ici.", "Encore rien.", "Toujours rien.")
        appels = []
        original = api_textes._pliage
        with mock.patch.object(api_textes, "_pliage", lambda texte: appels.append(texte) or original(texte)):
            r = self.api.ocr_chercher("cherche")
        self.assertEqual((r["total"], [x["page"] for x in r["resultats"]]), (1, [2]))
        self.assertEqual(len(appels), 1)                     # seule la page qui contient le terme descend au caractere
        self.assertIn("cherché", appels[0])

    def test_pages_au_dela_de_la_limite_comptees_sans_pliage_par_caractere(self):
        self.poser("Cours A/S1/p.pdf", pages=5, extraction="ocr")
        self.md("Cours A/S1/p.pdf", *["Le mot cherché ici."] * 5)
        appels = []
        original = api_textes._pliage
        with mock.patch.object(api_textes, "_pliage", lambda texte: appels.append(texte) or original(texte)):
            r = self.api.ocr_chercher("cherche", 2)
        self.assertEqual((r["total"], r["tronque"], len(r["resultats"])), (5, True, 2))
        self.assertEqual(len(appels), 2)


class ZipA3(ExportA3):
    """Ecart 155 : le nom d'entree du zip vient de la cle du cache, donc il est unique."""

    def test_deux_documents_de_meme_nom_dans_deux_sous_dossiers(self):
        import warnings, zipfile
        for rel, texte in (("Cours A/S3/a.pdf", "Texte racine."), ("Cours A/S3/Dossier/a.pdf", "Texte du sous-dossier.")):
            self.poser(rel, pages=1)
            self.md(rel, texte)
        cible = self.cible("export.zip")
        with warnings.catch_warnings(record=True) as vus:
            warnings.simplefilter("always")
            r = self.exporter("tout", "zip", choix=[cible])
        self.assertEqual(vus, [])                              # pas de « Duplicate name »
        with zipfile.ZipFile(cible) as z:
            noms = z.namelist()
            self.assertEqual(sorted(noms), ["Cours A/S1/a.pdf.md", "Cours A/S1/b.pdf.md", "Cours A/S3/Dossier/a.pdf.md",
                                            "Cours A/S3/a.pdf.md", "Cours B/S1/c.pdf.md"])
            self.assertEqual(r["documents"], len(noms))
            self.assertIn(b"Texte du sous-dossier.", z.read("Cours A/S3/Dossier/a.pdf.md"))
            self.assertIn(b"Texte racine.", z.read("Cours A/S3/a.pdf.md"))
            self.assertNotIn(b"Texte racine.", z.read("Cours A/S3/Dossier/a.pdf.md"))

    def test_documents_egal_au_nombre_d_entrees_avec_jsonl(self):
        import zipfile
        self.poser("Cours A/S1/Dossier/a.pdf", pages=1)
        self.md("Cours A/S1/Dossier/a.pdf", "Sous-dossier.")
        cible = self.cible("export.zip")
        r = self.exporter("tout", "zip_jsonl", choix=[cible])
        with zipfile.ZipFile(cible) as z:
            self.assertEqual(r["documents"], len([n for n in z.namelist() if n.endswith(".md")]))
            self.assertEqual(len(z.namelist()), len(set(z.namelist())))

    def test_cle_du_cache_avec_remontee_exclue_du_zip(self):
        import zipfile
        self.poser("../evil.pdf", pages=1, fichier=False)
        self.md("../evil.pdf", "Hors coffre.", sortie="evil.pdf.md")
        self._cache["../evil.pdf"]["sortie"] = "evil.pdf.md"
        ocr.sauver_cache(self.dest, {"version": 1, "documents": self._cache})
        cible = self.cible("export.zip")
        r = self.exporter("tout", "zip", choix=[cible])
        with zipfile.ZipFile(cible) as z:
            for nom in z.namelist():
                self.assertNotIn("..", nom.split("/"), nom)
            self.assertEqual(r["documents"], len(z.namelist()))


class ExportSurA3(ExportA3):
    """Ecarts 150, 161, 162 et 163 : format, cible, verrou, ecriture."""

    def test_format_inconnu_avant_toute_lecture_de_la_configuration(self):
        def casse(*a, **k):
            raise RuntimeError("boum interne")
        self.api._fenetre = FauxFenetre(choix=[self.cible("x.tar")])
        with mock.patch.object(ms, "charger_config", casse):
            r = self.json_ok(self.api.ocr_exporter("tout", "tar"))
        self.assertEqual(r, {"erreur": phrase(self, "format_inconnu")})
        self.assertFalse(os.path.exists(ms.ERREURS))           # rien dans erreurs.txt

    def test_format_non_texte(self):
        for format in (None, 3, ["zip"], "ZIP", ""):
            with self.subTest(format=format):
                r = self.json_ok(self.api.ocr_exporter("tout", format))
                self.assertEqual(r, {"erreur": phrase(self, "format_inconnu")})

    def test_cible_sous_dest_refusee(self):
        cibles = (("md", os.path.join(self.dest, "Textes", "Cours A", "S1", "a.pdf.md")),
                  ("zip", os.path.join(self.dest, ".moodlesync-ocr", "cache")),
                  ("zip", os.path.join(self.dest, "Cours A", "export.zip")),
                  ("md", os.path.join(self.dest, "export")))
        avant = self.instantane()
        with mock.patch.object(api_textes.ApiTextes, "_ocr_ecrire",
                               lambda *a, **k: self.fail("rien ne doit s'ecrire")):
            for format, cible in cibles:
                with self.subTest(cible=cible):
                    r = self.exporter("tout", format, choix=[cible])
                    self.assertEqual(r, {"erreur": phrase(self, "cible_dans_coffre")})
        self.assertEqual(self.instantane(), avant)

    def test_cible_sous_dest_par_un_lien_symbolique_refusee(self):
        lien = self.cible("lien")
        try:
            os.symlink(self.dest, lien)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles")
        avant = self.instantane()
        r = self.exporter("tout", "zip", choix=[os.path.join(lien, "export.zip")])
        self.assertEqual(r, {"erreur": phrase(self, "cible_dans_coffre")})
        self.assertEqual(self.instantane(), avant)

    def test_cible_hors_du_coffre_acceptee(self):
        cible = self.cible("export.zip")
        self.assertEqual(self.exporter("tout", "zip", choix=[cible])["chemin"], cible)
        autre = os.path.join(self.d, "coffre-voisin", "export.zip")       # meme prefixe de nom que `dest`
        os.makedirs(os.path.dirname(autre))
        self.assertEqual(self.exporter("tout", "zip", choix=[autre])["chemin"], autre)

    def test_cible_sous_le_dossier_de_sortie_hors_du_coffre(self):
        hors = os.path.join(self.d, "hors")
        for rel in ("Cours A/S1/a.pdf", "Cours A/S1/b.pdf", "Cours B/S1/c.pdf"):
            self._cache[rel]["sortie"] = os.path.join(hors, *rel.split("/")) + ".md"
            os.makedirs(os.path.dirname(self._cache[rel]["sortie"]), exist_ok=True)
            with open(self._cache[rel]["sortie"], "w", encoding="utf-8", newline="\n") as f:
                f.write("<!-- page 1 -->\n\nTexte hors coffre.\n\n")
        ocr.sauver_cache(self.dest, {"version": 1, "documents": self._cache})
        r = self.exporter("tout", "md", choix=[os.path.join(hors, "Cours A", "S1", "a.pdf.md")])
        self.assertEqual(r, {"erreur": phrase(self, "cible_dans_coffre")})
        with open(os.path.join(hors, "Cours A", "S1", "a.pdf.md"), encoding="utf-8") as f:
            self.assertIn("Texte hors coffre.", f.read())
        ok = self.exporter("tout", "md", choix=[self.cible("contexte.md")])
        self.assertEqual(ok["chemin"], self.cible("contexte.md"))

    def test_extension_md_ajoutee_au_format_md(self):
        cible = self.cible("contexte")
        r = self.exporter("tout", "md", choix=[cible])
        self.assertEqual(r["chemin"], cible + ".md")
        self.assertTrue(os.path.isfile(cible + ".md"))
        self.assertFalse(os.path.exists(cible))
        majuscules = self.cible("autre.MD")
        self.assertEqual(self.exporter("tout", "md", choix=[majuscules])["chemin"], majuscules)
        self.assertEqual(self.exporter("tout", "zip", choix=[self.cible("x.md")])["chemin"], self.cible("x.md") + ".zip")

    def test_coffre_identique_apres_chaque_format(self):
        for format, nom in (("zip", "a.zip"), ("zip_jsonl", "b.zip"), ("md", "c.md")):
            with self.subTest(format=format):
                avant = self.instantane()
                self.exporter("tout", format, choix=[self.cible(nom)])
                self.assertEqual(self.instantane(), avant)
                self.assertTrue(os.path.isfile(self.cible(nom)))

    def test_erreur_d_ecriture_sans_fichier_temporaire(self):
        cible = self.cible("export.zip")
        self.api._fenetre = FauxFenetre(choix=[cible])

        def refuse(*a, **k):
            raise PermissionError(13, "Permission denied")
        with mock.patch.dict(sys.modules, {"webview": self.FAUX_WEBVIEW}), mock.patch.object(os, "replace", refuse):
            r = self.json_ok(self.api.ocr_exporter("tout", "zip"))
        self.assertEqual(set(r), {"erreur"})
        self.assertTrue(r["erreur"].startswith(api_textes.ACTION + " : impossible de lire ou d'écrire un fichier"), r)
        self.assertFalse(os.path.exists(cible))
        self.assertFalse(os.path.exists(cible + ".tmp"))
        self.assertEqual([n for n in os.listdir(self.d) if n.endswith(".tmp")], [])

    def test_dossier_inexistant_pour_la_cible(self):
        r = self.exporter("tout", "md", choix=[os.path.join(self.d, "inconnu", "x.md")])
        self.assertEqual(set(r), {"erreur"})
        self.assertTrue(r["erreur"].startswith(api_textes.ACTION + " : "), r)

    def test_jsonl_ecrit_sous_le_verrou_du_cache(self):
        vus = []

        def faux_jsonl(dest, portee, flux, *, cfg=None):
            vus.append(self.api._ocr_verrou._is_owned())
            flux.write('{"cours": "x"}\n' * 4)
            return 4
        with mock.patch.object(ocr, "ecrire_jsonl", faux_jsonl):
            r = self.exporter("tout", "zip_jsonl", choix=[self.cible("export.zip")])
        self.assertEqual(vus, [True])
        self.assertEqual(r["documents"], 3)

    def test_jsonl_incomplet_est_une_erreur_sans_zip(self):
        cible = self.cible("export.zip")

        def court(dest, portee, flux, *, cfg=None):
            flux.write('{"cours": "x"}\n')
            return 1                                           # 4 pages attendues
        with mock.patch.object(ocr, "ecrire_jsonl", court):
            r = self.exporter("tout", "zip_jsonl", choix=[cible])
        self.assertEqual(set(r), {"erreur"})
        self.assertTrue(r["erreur"].startswith(api_textes.ACTION + " : impossible de lire ou d'écrire un fichier"), r)
        self.assertFalse(os.path.exists(cible))
        self.assertFalse(os.path.exists(cible + ".tmp"))

    def test_jsonl_complet_accepte(self):
        import zipfile
        cible = self.cible("export.zip")
        self.exporter("tout", "zip_jsonl", choix=[cible])
        with zipfile.ZipFile(cible) as z:
            self.assertEqual(len(z.read("textes.jsonl").decode("utf-8").splitlines()), 4)

    def test_lecture_du_cache_sous_le_verrou(self):
        verrou = self.api._ocr_verrou
        vus = {"documents": [], "contexte": []}
        original = {"documents": ocr._documents, "contexte": ocr.assembler_contexte}

        def espion(nom):
            def f(*a, **k):
                vus[nom].append(verrou._is_owned())
                return original[nom](*a, **k)
            return f
        with mock.patch.object(ocr, "_documents", espion("documents")), \
                mock.patch.object(ocr, "assembler_contexte", espion("contexte")):
            self.exporter("tout", "zip", choix=[self.cible("a.zip")])
            self.exporter("tout", "md", choix=[self.cible("b.md")])
        self.assertTrue(vus["documents"] and vus["contexte"])
        self.assertTrue(all(vus["documents"]), vus)
        self.assertTrue(all(vus["contexte"]), vus)


class LecturesSousVerrouA3(A2Coffre):
    """Ecarts 163 (K7, K14) : le cache est lu sous `_ocr_verrou` par ocr_documents, ocr_copier et ocr_chercher."""

    def espionner(self, objet, nom):
        verrou = self.api._ocr_verrou
        vus = []
        original = getattr(objet, nom)

        def f(*a, **k):
            vus.append(verrou._is_owned())
            return original(*a, **k)
        p = mock.patch.object(objet, nom, f)
        p.start()
        self.addCleanup(p.stop)
        return vus

    def test_documents(self):
        caches, documents = self.espionner(ocr, "charger_cache"), self.espionner(ocr, "_documents")
        self.api.ocr_documents()
        self.assertTrue(caches and documents)
        self.assertTrue(all(caches) and all(documents), (caches, documents))

    def test_copier(self):
        contexte, documents = self.espionner(ocr, "assembler_contexte"), self.espionner(ocr, "_documents")
        self.api.ocr_copier("tout")
        self.assertTrue(contexte and documents)
        self.assertTrue(all(contexte) and all(documents), (contexte, documents))

    def test_chercher(self):
        documents = self.espionner(ocr, "_documents")
        self.api.ocr_chercher("page")
        self.assertTrue(documents and all(documents), documents)


class CopierA3(A2Coffre):
    """Ecart 163 (K6) : frontiere du plafond de 2 000 000 caracteres."""

    def test_plafond_atteint_n_est_pas_depasse(self):
        exact = "x" * api_textes.TEXTE_MAX
        with mock.patch.object(ocr, "assembler_contexte", lambda *a, **k: exact):
            r = self.api.ocr_copier("tout")
        self.assertEqual(set(r), {"texte", "caracteres", "documents", "pages"})
        self.assertEqual(r["caracteres"], 2000000)
        self.assertEqual(len(r["texte"]), 2000000)
        trop = "x" * (api_textes.TEXTE_MAX + 1)
        with mock.patch.object(ocr, "assembler_contexte", lambda *a, **k: trop):
            self.assertEqual(self.api.ocr_copier("tout"), {"trop_long": True, "caracteres": 2000001})


class CacheEditeA3(A2Base):
    """Ecarts 163 (K1, K2) et 165 : un cache edite est refuse, jamais coerce."""

    def ligne(self, **champs):
        self.poser("Cours A/S1/x.pdf", pages=2)
        self._cache["Cours A/S1/x.pdf"].update(champs)
        ocr.sauver_cache(self.dest, {"version": 1, "documents": self._cache})
        return self.json_ok(self.api.ocr_documents())["documents"][0]

    def test_pages(self):
        for valeur, attendu in ((7, 7), (0, 0), ("5", 0), (3.9, 0), (True, 0), (False, 0), (-3, 0), (None, 0),
                                ([4], 0), ({"a": 1}, 0), (float("inf"), 0), (float("nan"), 0)):
            with self.subTest(valeur=valeur):
                ligne = self.ligne(pages=valeur)
                self.assertEqual(ligne["pages"], attendu)
                self.assertIs(type(ligne["pages"]), int)

    def test_confiance(self):
        for valeur, attendu in ((0.5, 0.5), (0, 0.0), (1, 1.0), (1.0, 1.0), (0.12345, 0.123), (1.5, None),
                                (-0.1, None), (2, None), (True, None), ("0.5", None), (None, None),
                                (float("nan"), None), (float("inf"), None), ([0.5], None)):
            with self.subTest(valeur=valeur):
                resultat = self.ligne(confiance=valeur)["confiance"]
                self.assertEqual(resultat, attendu)
                if attendu is not None:
                    self.assertIsInstance(resultat, float)

    def test_verifie_seulement_pour_true(self):
        for valeur, attendu in ((True, True), (False, False), ("non", False), ("oui", False), (1, False),
                                ("", False), ([1], False), (None, False)):
            with self.subTest(valeur=valeur):
                self.assertIs(self.ligne(verifie=valeur)["verifie"], attendu)

    def test_champs_texte(self):
        ligne = self.ligne(sortie=5, date=["2026"])
        self.assertEqual((ligne["sortie"], ligne["date"]), ("", ""))

    def test_compteurs_sans_coercion(self):
        self.poser("Cours A/S1/x.pdf", pages=2, etat="a_verifier")
        self._cache["Cours A/S1/x.pdf"].update(pages="9", verifie="non")
        ocr.sauver_cache(self.dest, {"version": 1, "documents": self._cache})
        compteurs = self.api.ocr_etat()["compteurs"]
        self.assertEqual((compteurs["pages"], compteurs["a_verifier"]), (0, 1))
        self._cache["Cours A/S1/x.pdf"].update(pages=4, verifie=True)
        ocr.sauver_cache(self.dest, {"version": 1, "documents": self._cache})
        compteurs = self.api.ocr_etat()["compteurs"]
        self.assertEqual((compteurs["pages"], compteurs["a_verifier"]), (4, 0))


class EntierA3(unittest.TestCase):
    """Ecart 165 : un seul assistant d'entier borne."""

    def test_entier(self):
        for valeur, defaut, attendu in ((7, 3, 7), (0, 3, 0), (True, 3, 3), (False, 3, 3), ("5", 3, 3), (3.9, 3, 3),
                                        (-1, 3, 3), (None, 3, 3), (float("inf"), 3, 3), (float("nan"), 3, 3),
                                        ([1], 3, 3), ({}, 3, 3)):
            with self.subTest(valeur=valeur):
                self.assertEqual(api_textes._entier(valeur, defaut), attendu)

    def test_un_seul_assistant(self):
        self.assertFalse(hasattr(api_textes, "_positif"))


class OuvrirA3(A2Base):
    """Ecarts 159, 163 (K3) : phrases de la section 5, echec d'ouverture, octet nul, lien symbolique."""

    def setUp(self):
        super().setUp()
        self.poser("Cours A/S1/scan.pdf", pages=1, extraction="ocr")
        self.md("Cours A/S1/scan.pdf", "Page un.")
        self.md_chemin = os.path.realpath(os.path.join(self.dest, "Textes", "Cours A", "S1", "scan.pdf.md"))

    def interdit(self, *a, **k):
        raise AssertionError("chemin refuse : rien ne doit s'ouvrir")

    def test_chemin_refuse_ou_absent_phrase_dediee(self):
        refus = {"erreur": phrase(self, "ouverture_refusee")}
        self.assertNotEqual(refus["erreur"], ocr.MESSAGES["corrompu"])
        chemins = ("../secret.pdf", "/etc/passwd", "C:x", "C:/x/y.pdf", ".moodlesync-ocr/cache.json",
                   "Textes/../../x", ".moodlesync.json", "Cours A/S1/absent.pdf", "Textes/Cours A/S1/absent.md",
                   "", "   ", None, 5, ["Textes"], {"a": 1})
        with mock.patch.object(app.m, "ouvrir_document", self.interdit), \
                mock.patch.object(ms, "ouvrir_dossier", self.interdit):
            for chemin in chemins:
                with self.subTest(chemin=chemin):
                    self.assertEqual(self.json_ok(self.api.ocr_ouvrir(chemin)), refus)

    def test_dossier_de_rangement_absent(self):
        c = self.config()
        c["dest"] = ""
        self.configurer(c)
        self.assertEqual(self.api.ocr_ouvrir("Textes"), {"erreur": phrase(self, "dossier_absent")})

    def test_octet_nul_donne_la_phrase_de_refus_sans_trace(self):
        avant = os.path.getsize(ms.ERREURS) if os.path.exists(ms.ERREURS) else 0
        with mock.patch.object(app.m, "ouvrir_document", self.interdit), \
                mock.patch.object(ms, "ouvrir_dossier", self.interdit):
            for chemin in ("a\x00b", "Textes/Cours A/S1/scan.pdf.md\x00.png", "Textes\x00", "\x00"):
                with self.subTest(chemin=chemin):
                    self.assertEqual(self.api.ocr_ouvrir(chemin), {"erreur": phrase(self, "ouverture_refusee")})
        self.assertEqual(os.path.getsize(ms.ERREURS) if os.path.exists(ms.ERREURS) else 0, avant)

    def test_echec_d_ouverture_du_document(self):
        with mock.patch.object(app.m, "ouvrir_document", lambda chemin: None):
            r = self.json_ok(self.api.ocr_ouvrir("Textes/Cours A/S1/scan.pdf.md"))
        self.assertEqual(r, {"erreur": phrase(self, "ouverture_impossible")})

    def test_echec_d_ouverture_du_dossier(self):
        def echoue(dossier):
            raise OSError(2, "introuvable")
        with mock.patch.object(ms, "ouvrir_dossier", echoue):
            r = self.json_ok(self.api.ocr_ouvrir("Textes"))
        self.assertEqual(r, {"erreur": phrase(self, "ouverture_impossible")})

    def test_succes_et_role_de_page(self):
        appels = []
        with mock.patch.object(app.m, "ouvrir_document", lambda chemin: appels.append(chemin) or "associe"):
            sans = self.api.ocr_ouvrir("Textes/Cours A/S1/scan.pdf.md")
            avec = self.api.ocr_ouvrir("Textes/Cours A/S1/scan.pdf.md", 7)
            absurde = self.api.ocr_ouvrir("Textes/Cours A/S1/scan.pdf.md", "pas une page")
        self.assertEqual((sans, avec, absurde), ({"ok": True},) * 3)
        self.assertEqual(appels, [self.md_chemin] * 3)         # `page` ne change rien cote Python

    def test_lien_symbolique_vers_l_exterieur_refuse(self):
        dehors = os.path.join(self.d, "dehors")
        os.makedirs(dehors)
        secret = os.path.join(dehors, "secret.md")
        with open(secret, "w", encoding="utf-8") as f:
            f.write("secret")
        lien_dossier = os.path.join(self.dest, "Textes", "lien")
        lien_fichier = os.path.join(self.dest, "Textes", "Cours A", "S1", "copie.md")
        try:
            os.symlink(dehors, lien_dossier)
            os.symlink(secret, lien_fichier)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles")
        refus = {"erreur": phrase(self, "ouverture_refusee")}
        with mock.patch.object(app.m, "ouvrir_document", self.interdit), \
                mock.patch.object(ms, "ouvrir_dossier", self.interdit):
            for chemin in ("Textes/lien", "Textes/lien/secret.md", "Textes/Cours A/S1/copie.md", lien_fichier):
                with self.subTest(chemin=chemin):
                    self.assertEqual(self.api.ocr_ouvrir(chemin), refus)

    def test_lien_symbolique_interne_accepte(self):
        lien = os.path.join(self.dest, "Textes", "interne")
        try:
            os.symlink(os.path.join(self.dest, "Textes", "Cours A"), lien)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles")
        appels = []
        with mock.patch.object(app.m, "ouvrir_document", lambda chemin: appels.append(chemin) or "associe"):
            self.assertEqual(self.api.ocr_ouvrir("Textes/interne/S1/scan.pdf.md"), {"ok": True})
        self.assertEqual(appels, [self.md_chemin])


class ReglagesA3(A2Base):
    """Ecarts 139, 141 et 160 : phrases de la section 5 pour les reglages, nom de dossier de sortie."""

    def test_phrases(self):
        a = self.api
        self.assertEqual(a.ocr_regler("inconnu", 1), {"erreur": phrase(self, "reglage_inconnu", cle="inconnu")})
        self.assertEqual(a.ocr_regler("ocr_dpi", "beaucoup"), {"erreur": phrase(self, "valeur_invalide")})
        self.assertEqual(a.ocr_regler("ocr_dpi", 100), {"erreur": phrase(self, "valeur_invalide")})
        self.assertEqual(a.ocr_regler("ocr_exe", os.path.join(self.d, "absent.exe")),
                         {"erreur": phrase(self, "chemin_introuvable")})
        self.assertEqual(a.ocr_regler("ocr_tessdata", os.path.join(self.d, "absent")),
                         {"erreur": phrase(self, "chemin_introuvable")})
        self.assertEqual(a.ocr_regler("ocr_dossier", "Cours A"), {"erreur": phrase(self, "dossier_pris")})
        self.assertEqual(a.ocr_regler("ocr_pdf", "copie"), {"erreur": phrase(self, "mode_indisponible")})
        self.assertEqual(a.ocr_regler("ocr_pdf", "remplacer"), {"confirmer": phrase(self, "consentement_remplacer")})
        self.assertEqual(a.ocr_installer(), {"erreur": phrase(self, "installation_indisponible")})

    def test_cle_qui_n_est_pas_un_texte(self):
        for cle in (None, 3, ["ocr"], {"a": 1}):
            with self.subTest(cle=cle):
                r = self.json_ok(self.api.ocr_regler(cle, True))
                self.assertEqual(list(r), ["erreur"])
                self.assertTrue(r["erreur"].startswith("Réglage inconnu"), r)

    def test_dossier_de_sortie_refuse(self):
        for nom in (".textes", ".moodlesync-ocr", ".", "..", "x.", "x..", "CON", "con", "Prn", "AUX", "nul", "COM1",
                    "com9", "LPT1", "lpt9", "CON.txt", "nul.md", "a/b", "a\\b", "a:b", "", "   "):
            with self.subTest(nom=nom):
                r = self.json_ok(self.api.ocr_regler("ocr_dossier", nom))
                self.assertEqual(r, {"erreur": phrase(self, "valeur_invalide")})
        self.assertNotIn("ocr_dossier", self.config())

    def test_dossier_de_sortie_accepte(self):
        for nom in ("Mes textes", "Textes", "Textes.v2", "Console", "COM10", "COM", "LPT0", "Auxiliaire", "a.b"):
            with self.subTest(nom=nom):
                r = self.json_ok(self.api.ocr_regler("ocr_dossier", nom))
                self.assertIn("reglages", r, r)
                self.assertEqual(self.config()["ocr_dossier"], nom)

    def test_dossier_de_sortie_visible_reste_ouvrable(self):
        self.assertIn("reglages", self.api.ocr_regler("ocr_dossier", "Mes textes"))
        self.poser("Cours A/S1/scan.pdf", pages=1, sortie="Mes textes/Cours A/S1/scan.pdf.md")
        self.md("Cours A/S1/scan.pdf", "Page un.", sortie="Mes textes/Cours A/S1/scan.pdf.md")
        appels = []
        with mock.patch.object(app.m, "ouvrir_document", lambda chemin: appels.append(chemin) or "associe"):
            self.assertEqual(self.api.ocr_ouvrir("Mes textes/Cours A/S1/scan.pdf.md"), {"ok": True})
        self.assertEqual(len(appels), 1)


class LancerA3(A2Base):
    """Ecarts 137 et 139 : consentement, occupation, accord du pluriel."""

    def test_refus_sans_consentement(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        self.assertFalse(self.config().get("ocr", False))
        for portee in ("sans_texte", "tout", "cours:11"):
            with self.subTest(portee=portee):
                self.assertEqual(self.json_ok(self.api.ocr_lancer(portee)),
                                 {"erreur": phrase(self, "consentement_absent")})
        self.assertIsNone(self.api._ocr_fil)
        self.assertEqual(self.fichier()["taches"], [])           # aucune file constituee
        self.assertEqual(self.pages_vues, [])

    def test_consentement_donne_la_file_se_constitue(self):
        c = self.config()
        c["ocr"] = True
        self.configurer(c)
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        self.assertIn("file", self.api.ocr_lancer("tout"))
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))

    def test_extraction_deja_en_cours(self):
        c = self.config()
        c["ocr"] = True
        self.configurer(c)
        self.api._ocr_fil = SimpleNamespace(is_alive=lambda: True)
        self.assertEqual(self.api.ocr_lancer("tout"), {"erreur": phrase(self, "occupe")})

    def test_dossier_de_rangement_absent_et_fenetre_fermee(self):
        c = self.config()
        c.update({"ocr": True, "dest": os.path.join(self.d, "absent")})
        self.configurer(c)
        self.assertEqual(self.api.ocr_lancer("tout"), {"erreur": phrase(self, "dossier_absent")})
        self.api._fenetre = None
        with mock.patch.dict(sys.modules, {"webview": SimpleNamespace(OPEN_DIALOG=10)}):
            self.assertEqual(self.api.ocr_choisir_exe(), {"erreur": phrase(self, "fenetre_fermee")})

    def test_phrase_du_lot_s_accorde(self):
        cfg = self.config()
        self.assertTrue(self.api._ocr_phrase_lot(1, 1, cfg).startswith("1 document, environ 1 page. "))
        self.assertTrue(self.api._ocr_phrase_lot(2, 2, cfg).startswith("2 documents, environ 2 pages. "))
        self.assertTrue(self.api._ocr_phrase_lot(1, 501, cfg).startswith("1 document, environ 501 pages. "))
        self.assertTrue(self.api._ocr_phrase_lot(51, 1, cfg).startswith("51 documents, environ 1 page. "))
        mini, maxi = self.api._ocr_minutes(501, cfg)
        self.assertEqual(self.api._ocr_phrase_lot(1, 501, cfg),
                         phrase(self, "confirmation_lot", documents="1 document", pages="501 pages",
                                mini=mini, maxi=maxi))

    def test_confirmation_d_un_seul_document_long(self):
        c = self.config()
        c["ocr"] = True
        self.configurer(c)
        self.ranger("Cours A/S1/long.pdf", [([], True)] * 501)
        r = self.json_ok(self.api.ocr_lancer("tout"))
        self.assertEqual((r["documents"], r["pages"]), (1, 501))
        self.assertTrue(r["confirmer"].startswith("1 document, environ 501 pages. "), r["confirmer"])


class MessagesA3(Base):
    """Invariant 9, section 5 : toutes les phrases visibles viennent de ocr.MESSAGES, et du contrat."""

    def test_codes_presents_et_mots_interdits(self):
        import re
        for code in CODES_A1 + CODES_A3:
            with self.subTest(code=code):
                self.assertIn(code, ocr.MESSAGES)
                self.assertTrue(ocr.MESSAGES[code].strip())
        for code in CODES_A3:
            with self.subTest(interdit=code):
                self.assertIsNone(re.search(r"\b(OCR|Tesseract|tessdata|DPI|PSM|TSV)\b", phrase(self, code)), code)

    def test_mots_du_contrat(self):
        table = messages_du_contrat()
        for code in CODES_A1 + CODES_A3:
            with self.subTest(code=code):
                self.assertIn(code, table, "code absent de la section 5 du contrat")
                self.assertEqual(table[code], phrase(self, code))
        for code, texte in table.items():
            if code in ocr.MESSAGES:
                with self.subTest(contrat=code):
                    self.assertEqual(texte, ocr.MESSAGES[code])

    def test_aucune_copie_locale(self):
        for nom in ("MESSAGES_TEXTE", "DOSSIER_ABSENT", "FENETRE_FERMEE", "OCCUPE"):
            with self.subTest(nom=nom):
                self.assertFalse(hasattr(api_textes, nom), nom)

    def test_occupe_identique_a_celle_de_application(self):
        self.assertEqual(phrase(self, "occupe"), app.OCCUPE)

    def test_message_ne_porte_pas_de_tiret_long(self):
        for code in CODES_A1 + CODES_A3:
            self.assertNotIn(chr(0x2014), phrase(self, code))
            self.assertNotIn(chr(0x2013), phrase(self, code))

    def test_aucune_phrase_ecrite_dans_une_reponse(self):
        """Aucun `{"erreur": ...}`, `{"confirmer": ...}` ni `raise _Refus(...)` ne porte un texte litteral."""
        import ast
        with open(os.path.join(RACINE, "moodlesync", "api_textes.py"), encoding="utf-8") as f:
            arbre = ast.parse(f.read())
        litteraux = (ast.Constant, ast.JoinedStr)
        fautifs = []
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Dict):
                for cle, valeur in zip(noeud.keys, noeud.values):
                    if isinstance(cle, ast.Constant) and cle.value in ("erreur", "confirmer", "message") \
                            and isinstance(valeur, litteraux) and not (isinstance(valeur, ast.Constant)
                                                                        and valeur.value in ("", None)):
                        fautifs.append((noeud.lineno, cle.value))
            if isinstance(noeud, ast.Call) and getattr(noeud.func, "id", "") == "_Refus" and noeud.args \
                    and isinstance(noeud.args[0], litteraux):
                fautifs.append((noeud.lineno, "_Refus"))
        self.assertEqual(fautifs, [])


class AucuneTraceA3(A2Coffre):
    """Porte de sortie de A3 : aucune reponse d'une methode publique ne porte de trace technique ni de phrase
    absente de ocr.MESSAGES (hors celles que ms.message_erreur fabrique)."""

    FAUX_WEBVIEW = SimpleNamespace(SAVE_DIALOG=30, FOLDER_DIALOG=20, OPEN_DIALOG=10)

    def appels(self):
        """(nom, appel) de chaque methode publique, avec des arguments valides puis absurdes."""
        a = self.api
        cible_dans_coffre = os.path.join(self.dest, "export.zip")
        return [
            ("ocr_etat", lambda: a.ocr_etat()), ("ocr_detecter", lambda: a.ocr_detecter()),
            ("ocr_choisir_exe", lambda: a.ocr_choisir_exe()), ("ocr_installer", lambda: a.ocr_installer()),
            ("ocr_apercu", lambda: a.ocr_apercu()), ("ocr_apercu", lambda: a.ocr_apercu("../x.pdf", "x")),
            ("ocr_apercu", lambda: a.ocr_apercu("Cours A/S1/absent.pdf", -4)),
            ("ocr_lancer", lambda: a.ocr_lancer()), ("ocr_lancer", lambda: a.ocr_lancer(3, 4, "x")),
            ("ocr_pause", lambda: a.ocr_pause()), ("ocr_reprendre", lambda: a.ocr_reprendre()),
            ("ocr_annuler", lambda: a.ocr_annuler()),
            ("ocr_documents", lambda: a.ocr_documents()), ("ocr_documents", lambda: a.ocr_documents(5)),
            ("ocr_documents", lambda: a.ocr_documents({"cours": [], "qualite": 3, "type": {}})),
            ("ocr_chercher", lambda: a.ocr_chercher("page")), ("ocr_chercher", lambda: a.ocr_chercher(None, "x")),
            ("ocr_copier", lambda: a.ocr_copier("tout")), ("ocr_copier", lambda: a.ocr_copier(None)),
            ("ocr_exporter", lambda: a.ocr_exporter("tout", "tar")), ("ocr_exporter", lambda: a.ocr_exporter("tout")),
            ("ocr_exporter", lambda: a.ocr_exporter("tout", "md")),
            ("ocr_ouvrir", lambda: a.ocr_ouvrir("../x")), ("ocr_ouvrir", lambda: a.ocr_ouvrir("a\x00b")),
            ("ocr_ouvrir", lambda: a.ocr_ouvrir("Textes/Cours A/S1/absent.md")), ("ocr_ouvrir", lambda: a.ocr_ouvrir(None)),
            ("ocr_pdf_restaurer", lambda: a.ocr_pdf_restaurer("Cours A/S1/absent.pdf")),
            ("ocr_pdf_restaurer", lambda: a.ocr_pdf_restaurer(None)),
            ("ocr_regler", lambda: a.ocr_regler("inconnu", 1)), ("ocr_regler", lambda: a.ocr_regler("ocr_dpi", "x")),
            ("ocr_regler", lambda: a.ocr_regler("ocr_dossier", "Cours A")),
            ("ocr_regler", lambda: a.ocr_regler("ocr_dossier", "CON")),
            ("ocr_regler", lambda: a.ocr_regler("ocr_exe", "/inexistant/tesseract")),
            ("ocr_regler", lambda: a.ocr_regler("ocr_pdf", "copie")),
            ("ocr_regler", lambda: a.ocr_regler("ocr_pdf", "remplacer")),
            ("ocr_regler", lambda: a.ocr_regler("ocr_langues", "zzz")), ("ocr_regler", lambda: a.ocr_regler(None, None)),
        ]

    def verifier(self, scenario):
        motifs = motifs_des_phrases()
        vues = 0
        for nom, appel in self.appels():
            try:
                r = appel()
            except Exception as e:                              # aucune exception ne sort
                self.fail(f"{scenario} {nom} a leve {e!r}")
            json.dumps(r)
            self.assertIsInstance(r, dict, (scenario, nom))
            for cle in ("erreur", "confirmer", "message"):
                if cle in r and r[cle]:
                    vues += 1
                    self.assertIsInstance(r[cle], str, (scenario, nom, cle))
                    self.assertTrue(phrase_permise(r[cle], motifs), (scenario, nom, r[cle]))
            self.assertNotIn("Traceback", json.dumps(r, ensure_ascii=False), (scenario, nom))
        return vues

    def test_environnement_normal(self):
        with mock.patch.dict(sys.modules, {"webview": self.FAUX_WEBVIEW}):
            self.api._fenetre = FauxFenetre(choix=[os.path.join(self.dest, "export.zip")])
            self.assertGreater(self.verifier("normal"), 10)

    def test_sans_dossier_de_rangement(self):
        c = self.config()
        c["dest"] = os.path.join(self.d, "absent")
        self.configurer(c)
        with mock.patch.dict(sys.modules, {"webview": self.FAUX_WEBVIEW}):
            self.assertGreater(self.verifier("dest absent"), 5)

    def test_sans_fenetre(self):
        self.api._fenetre = None
        with mock.patch.dict(sys.modules, {"webview": self.FAUX_WEBVIEW}):
            self.assertGreater(self.verifier("sans fenetre"), 5)

    def test_configuration_cassee(self):
        def casse(*a, **k):
            raise RuntimeError("boum interne")
        with mock.patch.object(ms, "charger_config", casse), \
                mock.patch.dict(sys.modules, {"webview": self.FAUX_WEBVIEW}):
            self.assertGreater(self.verifier("config cassee"), 10)

    def test_consentement_donne(self):
        c = self.config()
        c["ocr"] = True
        self.configurer(c)
        self.api._fenetre = FauxFenetre(choix=[os.path.join(self.d, "export.zip")])
        with mock.patch.dict(sys.modules, {"webview": self.FAUX_WEBVIEW}), \
                mock.patch.object(api_textes.ApiTextes, "_ocr_demarrer", lambda self: False):   # pas de fil en fond
            self.assertGreater(self.verifier("consentement"), 5)

    def test_le_filtre_de_phrases_distingue(self):
        motifs = motifs_des_phrases()
        self.assertTrue(phrase_permise(ocr.MESSAGES["corrompu"], motifs))
        self.assertTrue(phrase_permise(phrase(self, "reglage_inconnu", cle="x"), motifs))
        self.assertTrue(phrase_permise(api_textes.ACTION + " : erreur imprévue. Le détail est noté dans e.txt.", motifs))
        for mauvaise in ("Valeur invalide pour moi.", "Une phrase inventée.", "Traceback (most recent call last):",
                         'File "x.py", line 3'):
            self.assertFalse(phrase_permise(mauvaise, motifs), mauvaise)


class ErreursProfondesA3(A2Coffre):
    """Ecart 163 : T26 atteint la logique de chacune des cinq methodes (la doublure leve plus loin que
    `charger_config`), et le resultat reste une phrase."""

    FAUX_WEBVIEW = SimpleNamespace(SAVE_DIALOG=30, FOLDER_DIALOG=20, OPEN_DIALOG=10)

    def verifier(self, r, atteint):
        self.json_ok(r)
        self.assertTrue(atteint, "la doublure n'a pas ete atteinte : le test n'exerce que l'enveloppe")
        self.assertEqual(list(r), ["erreur"], r)
        self.assertTrue(phrase_permise(r["erreur"], motifs_des_phrases()), r)
        self.assertNotIn("boum", r["erreur"])

    def casse(self, atteint):
        def f(*a, **k):
            atteint.append(1)
            raise RuntimeError("boum interne")
        return f

    def test_documents(self):
        atteint = []
        with mock.patch.object(ocr, "charger_cache", self.casse(atteint)):
            self.verifier(self.api.ocr_documents(), atteint)

    def test_chercher(self):
        atteint = []
        with mock.patch.object(ocr, "_lire_md", self.casse(atteint)):
            self.verifier(self.api.ocr_chercher("page"), atteint)

    def test_copier(self):
        atteint = []
        with mock.patch.object(ocr, "assembler_contexte", self.casse(atteint)):
            self.verifier(self.api.ocr_copier("tout"), atteint)

    def test_exporter(self):
        for format in ("zip", "zip_jsonl", "md"):
            with self.subTest(format=format):
                atteint = []
                self.api._fenetre = FauxFenetre(choix=[os.path.join(self.d, "export")])
                cible = "assembler_contexte" if format == "md" else "_documents"
                with mock.patch.object(ocr, cible, self.casse(atteint)), \
                        mock.patch.dict(sys.modules, {"webview": self.FAUX_WEBVIEW}):
                    self.verifier(self.api.ocr_exporter("tout", format), atteint)
        atteint = []
        with mock.patch.object(ocr, "ecrire_jsonl", self.casse(atteint)), \
                mock.patch.dict(sys.modules, {"webview": self.FAUX_WEBVIEW}):
            self.api._fenetre = FauxFenetre(choix=[os.path.join(self.d, "export")])
            self.verifier(self.api.ocr_exporter("tout", "zip_jsonl"), atteint)

    def test_ouvrir(self):
        atteint = []
        with mock.patch.object(ms, "ouvrir_dossier", self.casse(atteint)):
            r = self.api.ocr_ouvrir("Textes")
        self.assertTrue(atteint)
        self.json_ok(r)
        self.assertEqual(list(r), ["erreur"], r)
        self.assertTrue(phrase_permise(r["erreur"], motifs_des_phrases()), r)


class FinDeFichier(unittest.TestCase):
    """Ecart 164 : le bloc `unittest.main()` est la derniere chose du fichier."""

    def test_unittest_main_en_fin_de_fichier(self):
        with open(os.path.abspath(__file__), encoding="utf-8") as f:
            lignes = [ligne.rstrip("\n") for ligne in f]
        while lignes and not lignes[-1].strip():
            lignes.pop()
        self.assertEqual(lignes[-2:], ['if __name__ == "__main__":', "    unittest.main()"])
        self.assertEqual(sum(1 for ligne in lignes if ligne.startswith("if __name__")), 1)


if __name__ == "__main__":
    unittest.main()
