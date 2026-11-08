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
        self.assertIn("erreur", self.api.ocr_choisir_exe())


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
        a._fenetre = None
        self.assertIn("erreur", a.ocr_choisir_exe())            # fenetre pas encore ouverte
        exe = os.path.join(self.d, "tesseract.exe")
        open(exe, "wb").close()
        faux = SimpleNamespace(OPEN_DIALOG=10, FOLDER_DIALOG=20)   # pywebview n'est pas importe par les tests
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


if __name__ == "__main__":
    unittest.main()
