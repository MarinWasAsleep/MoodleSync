"""Tests hors ligne du mixin ApiTextes (moodlesync/api_textes.py) et de son branchement dans application.py.

Aucune fenetre, aucun reseau, aucun vrai moteur : les fonctions du moteur d'extraction sont remplacees par des
doublures, les reglages et le journal d'erreurs vont dans un dossier temporaire, les PDF sont fabriques a la main.
Les reponses nouvelles de la refonte (ocr_etat, ocr_traiter, ocr_copier_texte, ocr_restaurer,
ocr_originaux_supprimer, ocr_regler) sont mesurees dans tests/test_traiter_api.py, contre les fixtures.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t . -v
"""
import hashlib, json, os, sys, tempfile, threading, time, unittest
from types import SimpleNamespace
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import api_textes, application as app, moteur as ms, ocr, textes_arbre

COURS = [{"id": 11, "fullname": "Histoire des idées politiques (2026-2027)", "shortname": "COURS_HIP"}]

# Bloc moteur de la forme 3.1 (detecter) : un moteur present, deux langues et osd.
BLOC_MOTEUR = {"present": True, "version": "5.5.3", "source": "path", "exe": os.path.join("faux", "tesseract.exe"),
               "langues": ["eng", "fra", "osd"], "langues_effectives": "fra+eng", "repli": False,
               "message": "", "tessdata": "", "majeure": 5}

ENTETE_TSV = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
# Une phrase assez longue pour que la page soit un texte (le seuil `SEUIL_TEXTE` se compte en caracteres).
MOTS = ("Bonjour", "le", "monde", "studieux", "de", "la", "section", "un", "des", "textes", "anciens", "et", "des",
        "notes", "de", "cours", "relues", "page", "apres", "page")
TSV = "\r\n".join([ENTETE_TSV] + ["5\t1\t1\t1\t1\t%d\t%d\t10\t50\t20\t91.0\t%s" % (i, 100 + 10 * i, mot)
                                  for i, mot in enumerate(MOTS, 1)]) + "\r\n"

# Contrat 4.8 : les sept methodes retirees de l'API (le prompt en dit huit ; le contrat en nomme sept). Aucune
# n'existe plus, meme vide (invariant 8).
METHODES_RETIREES = ("ocr_apercu", "ocr_chercher", "ocr_copier", "ocr_exporter", "ocr_documents",
                     "ocr_lancer", "ocr_pdf_restaurer")

# Contrat 4.1, 4.2, 4.4, 4.7 : les methodes conservees ou nouvelles de l'onglet.
METHODES_VIVES = ("ocr_etat", "ocr_detecter", "ocr_choisir_exe", "ocr_installer", "ocr_installer_annuler",
                  "ocr_pause", "ocr_reprendre", "ocr_annuler", "ocr_ouvrir", "ocr_regler", "ocr_traiter",
                  "ocr_copier_texte", "ocr_restaurer", "ocr_originaux_supprimer", "ocr_arbre", "ocr_afficher")

# Ce que la vraie fabrication ajoute au PDF : une couche de texte, donc des octets de plus que la source.
COUCHE = b"\n% couche de texte de la version cherchable\n"


def empreinte(octets):
    return "sha256:" + hashlib.sha256(octets).hexdigest()


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


def charge_js(code):
    """Objet JSON d'un appel `window.<nom>({...})` envoye a la page."""
    return json.loads(code.split("(", 1)[1].rsplit(")", 1)[0])


class Base(unittest.TestCase):
    """Reglages et journal dans un dossier temporaire, moteur simule, coffre avec un dossier de cours."""

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
                                   (ocr, "rendre_page", self.rendre),
                                   (ocr, "fabriquer_pdf_cherchable", self.fabriquer)):
            p = mock.patch.object(cible, nom, valeur)
            p.start()
            self.addCleanup(p.stop)
        self.api = app.Api()
        self.api._fenetre = self.fenetre

    def fabriquer(self, dest, chemin_rel, cfg, *, arreter=None):
        """Doublure de la fabrication du PDF cherchable : elle change la taille du fichier, comme la vraie.

        La vraie fabrication ajoute une couche de texte (donc change la taille) et consigne dans `genere` de
        `.moodlesync.json` l'identite du PDF recu et celle du fichier ecrit (2.1). La doublure fait les deux :
        sans `genere`, `textes_arbre` (4.3) ne peut pas reconnaitre un PDF remplace, et un test mesure alors un
        monde que le vrai code ne produit jamais (ecart E-V3-1 de la revue V3).
        """
        chemin = os.path.join(dest, *chemin_rel.split("/"))
        with open(chemin, "rb") as f:
            octets = f.read()
        nouveau = octets.replace(b"%PDF-1.4", b"%PDF-1.5", 1) + COUCHE
        with open(chemin, "wb") as f:
            f.write(nouveau)
        etat = ms.charger_etat(dest)
        etat = etat if isinstance(etat, dict) else {}
        cle = next((c for c, v in etat.items()
                    if isinstance(v, dict) and v.get("chemin") == chemin_rel), "url:" + chemin_rel)
        etat[cle] = dict(etat.get(cle) or {}, chemin=chemin_rel,
                         genere={"type": "pdf_cherchable", "version": 1,
                                 "taille_source": len(octets), "empreinte_source": empreinte(octets),
                                 "taille_fichier": len(nouveau), "empreinte_fichier": empreinte(nouveau)})
        ms.sauver_etat(dest, etat)
        return {"remplace": chemin_rel}

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
        """Synchronisation simulee : releve ce qui tourne pendant qu'elle tient les fichiers. Le compte rendu a la
        forme du contrat 7 : `republies_generes`, plus de `a_preparer`."""
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
                  "liste_maj": [], "annule": False, "restants": {}, "generes": 0, "republies_generes": []}
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
        """Pose un PDF dans le coffre **et l'inscrit dans `.moodlesync.json`**, comme la synchronisation le fait
        d'un fichier telecharge (2.1 de `docs/ocr-contrat.md`).

        O17 (tache R2d) : un PDF absent de cet etat n'est plus remplace, il se traite comme un PDF textuel (O2).
        Un banc qui posait un PDF sans l'inscrire mesurait donc le defaut E-V7-2, pas un coffre reel.
        """
        chemin = os.path.join(self.dest, *rel.split("/"))
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(pdf_minimal(pages))
        self.suivre(rel)
        return chemin

    def suivre(self, rel, **champs):
        """Inscrit `rel` dans `.moodlesync.json` (cle d'URL, chemin relatif au coffre), ou met a jour son entree."""
        etat = ms.charger_etat(self.dest)
        etat = dict(etat) if isinstance(etat, dict) else {}
        cle = next((c for c, v in etat.items()
                    if isinstance(v, dict) and str(v.get("chemin", "")).replace(os.sep, "/") == rel), None)
        cle = cle or "https://moodle.exemple.ch/" + rel
        etat[cle] = dict(etat.get(cle) or {}, t=1760000000, chemin=rel.replace("/", os.sep), **champs)
        ms.sauver_etat(self.dest, etat)
        return cle

    def traiter(self, rel, cfg=None):
        """Traitement reel d'un document, moteur simule : cache, texte a cote et copie d'original comme en vrai."""
        return ocr.traiter_document(self.dest, rel, cfg or self.config())

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


class Branchement(Base):
    """Contrat 4.1 et 4.8 : le mixin est branche, les methodes vivantes existent, les retirees n'existent plus."""

    def test_mixin_branche(self):
        self.assertIsInstance(self.api, api_textes.ApiTextes)
        from moodlesync.api_arbre import ApiArbre
        self.assertIsInstance(self.api, ApiArbre)
        for nom in ("_ocr_verrou", "_ocr_fichiers", "_ocr_fil", "_ocr_arret", "_ocr_pause", "_sync_veut"):
            self.assertTrue(hasattr(self.api, nom), nom)
        self.assertIsInstance(self.api._ocr_verrou, type(threading.RLock()))
        self.assertIsInstance(self.api._ocr_fichiers, type(threading.Lock()))
        self.assertIsInstance(self.api._sync_veut, threading.Event)
        self.assertFalse(self.api._ocr_arret.is_set())
        self.assertIsNone(self.api._ocr_fil)

    def test_methodes_vivantes(self):
        for nom in METHODES_VIVES:
            with self.subTest(methode=nom):
                self.assertTrue(callable(getattr(self.api, nom, None)), nom)

    def test_methodes_retirees_absentes(self):
        """Contrat 4.8 et invariant 8 : une methode retiree n'existe plus, meme vide."""
        for nom in METHODES_RETIREES:
            with self.subTest(methode=nom):
                self.assertFalse(hasattr(app.Api, nom), "%s existe encore sur Api" % nom)
                self.assertFalse(hasattr(api_textes.ApiTextes, nom), nom)
                self.assertFalse(hasattr(self.api, nom), nom)

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


class Formes(Base):
    """Formes de 4.2 et branchement des compteurs sur l'arbre."""

    def test_etat_forme(self):
        r = self.json_ok(self.api.ocr_etat())
        self.assertEqual(set(r), {"moteur", "occupe", "file", "compteurs", "reglages", "originaux", "depot"})
        self.assertEqual(set(r["moteur"]), {"present", "version", "source", "exe", "langues", "langues_effectives",
                                            "repli", "message"})
        self.assertEqual(set(r["file"]), {"etat", "origine", "document", "page", "pages", "documents_faits",
                                          "documents_total", "reprise"})
        self.assertEqual(set(r["compteurs"]), {"fichiers", "traites", "a_verifier", "echecs", "non_traites",
                                               "pages_non_traitees"})
        self.assertEqual(set(r["reglages"]), {"ocr_langues", "ocr_dpi", "ocr_format"})
        self.assertEqual(set(r["originaux"]), {"nombre", "octets"})
        self.assertEqual(set(r["depot"]), {"etat", "dossier_defaut", "dossier", "resultats"})
        for retire in ("active", "mode_pdf", "prevision", "a_preparer", "pages_a_preparer", "octets_texte",
                       "orphelins"):
            self.assertNotIn(retire, r)
        self.assertNotIn("ocr_apres_sync", r["reglages"])
        self.assertTrue(r["moteur"]["present"])
        self.assertFalse(r["occupe"])
        self.assertEqual(r["file"]["etat"], "inactive")
        self.assertEqual(r["file"]["origine"], "coffre")
        self.assertEqual(r["reglages"]["ocr_format"], "md")
        self.assertEqual(r["depot"]["etat"], "inactif")
        self.assertTrue(r["depot"]["dossier_defaut"].endswith(api_textes.DOSSIER_DEPOT))

    def test_etat_ne_lit_le_coffre_qu_une_fois(self):
        """Contrat 4.2 : les compteurs viennent de l'arbre construit par l'appel, sans second parcours."""
        appels = {"arbre": 0, "compteurs": 0}
        vrai_construire, vrai_compteurs = textes_arbre.construire_arbre, textes_arbre.compteurs

        def construire(*a, **k):
            appels["arbre"] += 1
            return vrai_construire(*a, **k)

        def compteurs(arbre):
            appels["compteurs"] += 1
            return vrai_compteurs(arbre)
        with mock.patch.object(textes_arbre, "construire_arbre", construire), \
                mock.patch.object(textes_arbre, "compteurs", compteurs):
            self.api.ocr_etat()
        self.assertEqual(appels, {"arbre": 1, "compteurs": 1})

    def test_compteurs_du_cache(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        self.traiter("Cours A/S1/scan.pdf")
        r = self.json_ok(self.api.ocr_etat())
        self.assertEqual(r["compteurs"]["fichiers"], 1)
        self.assertEqual(r["compteurs"]["traites"], 1)
        self.assertEqual(r["compteurs"]["non_traites"], 0)
        self.assertEqual(self.api.ocr_arbre()["compteurs"], r["compteurs"])

    def test_originaux(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        self.assertEqual(self.api.ocr_etat()["originaux"], {"nombre": 0, "octets": 0})
        self.traiter("Cours A/S1/scan.pdf")
        originaux = self.api.ocr_etat()["originaux"]
        entree = ocr.charger_cache(self.dest)["documents"]["Cours A/S1/scan.pdf"]
        self.assertEqual(originaux["nombre"], 1)
        self.assertEqual(originaux["octets"], entree["original"]["taille"])

    def test_sync_etat_bloc_ocr(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        self.traiter("Cours A/S1/scan.pdf")
        r = self.json_ok(self.api.sync_etat())
        self.assertEqual(set(r["ocr"]), {"moteur", "fichiers", "traites", "a_verifier", "echecs", "non_traites",
                                         "reprise"})
        self.assertTrue(r["ocr"]["moteur"])
        self.assertEqual((r["ocr"]["fichiers"], r["ocr"]["traites"]), (1, 1))

    def test_pousser_porte_origine(self):
        """Contrat 4.2 et 5.2 : `window.textesProgres` recoit `origine` dans le bloc `file`."""
        self.api._ocr_origine = "depot"
        self.api._ocr_pousser(force=True)
        charge = charge_js(self.fenetre.appels[-1])
        self.assertEqual(charge["origine"], "depot")
        for cle in ("etat", "document", "page", "pages", "documents_faits", "documents_total", "restant_min",
                    "message"):
            self.assertIn(cle, charge)


class ErreursT26(Base):
    """T26 : chaque methode en erreur renvoie une phrase, sans trace technique."""

    def test_chaque_methode_en_erreur(self):
        def casse(*a, **k):
            raise RuntimeError("boum interne")
        appels = {"ocr_etat": lambda: self.api.ocr_etat(),
                  "ocr_detecter": lambda: self.api.ocr_detecter(),
                  "ocr_traiter": lambda: self.api.ocr_traiter(["Cours A/S1/x.pdf"]),
                  "ocr_pause": lambda: self.api.ocr_pause(),
                  "ocr_reprendre": lambda: self.api.ocr_reprendre(),
                  "ocr_annuler": lambda: self.api.ocr_annuler(),
                  "ocr_restaurer": lambda: self.api.ocr_restaurer("Cours A/S1/scan.pdf"),
                  "ocr_copier_texte": lambda: self.api.ocr_copier_texte("Cours A/S1/scan.pdf"),
                  "ocr_originaux_supprimer": lambda: self.api.ocr_originaux_supprimer(),
                  "ocr_regler": lambda: self.api.ocr_regler("ocr_dpi", 300)}
        with mock.patch.object(ms, "charger_config", casse):
            for nom, appel in appels.items():
                with self.subTest(methode=nom):
                    r = self.json_ok(appel())
                    self.assertIn("erreur", r, r)
                    self.assertIsInstance(r["erreur"], str)
                    for interdit in ("Traceback", "boum", "site-packages", ".py"):
                        self.assertNotIn(interdit, r["erreur"])


class DureesAnnoncees(Base):
    """Ecart 133 et decision de Maxence : `ocr_threads` ne divise plus les durees annoncees.

    La fourchette elle-meme est celle de O18 (revue V7, E-V7-4) : 15 secondes par page au moins, 30 au plus.
    3000 pages donnent donc 750 a 1500 minutes, quel que soit `ocr_threads`.
    """

    def test_fourchette_sans_diviseur(self):
        for threads in (1, 2, 4):
            c = self.config()
            c.update({"ocr_threads": threads})
            self.configurer(c)
            self.assertEqual(self.api._ocr_minutes(3000, self.config()), [750, 1500], threads)

    def test_restant_min_sans_diviseur(self):
        c = self.config()
        c.update({"ocr_threads": 4})
        self.configurer(c)
        self.api._ocr_etat_fil, self.api._ocr_page, self.api._ocr_pages = "en_cours", 0, 3000
        self.api._ocr_pousser(force=True)
        charge = charge_js(self.fenetre.appels[-1])
        self.assertEqual(charge["restant_min"], 100)
        self.assertEqual((charge["page"], charge["pages"]), (0, 3000))


class Executeur(Base):
    """Contrat 4.4 : l'executeur traite la file, cede a la synchronisation, et n'arrete pas sur un document en
    erreur."""

    def lancer(self, *chemins, refaire=False):
        return self.json_ok(self.api.ocr_traiter(list(chemins), refaire, True))

    def test_pause_et_reprise(self):
        """4.4 et 2.5 : la pause retient les pages suivantes, la reprise termine le document.

        Aucun delai fixe : la premiere page est tenue ouverte par le test (`premiere`), la pause est demandee
        pendant qu'elle tourne, puis la page est relachee. L'ancienne version dormait 0,15 s et dependait donc de
        la charge de la machine (ecart E-V3-6 de la revue V3).
        """
        self.ranger("Cours A/S1/scan.pdf", [([], True)] * 4)
        premiere = threading.Event()          # la page 1 est en cours
        relache = threading.Event()           # le test laisse la page 1 se terminer
        vrai = self.executer

        def etat_brut():
            """Etat ecrit par l'executeur, sans la reconciliation de `charger_file` (2.5)."""
            with open(os.path.join(self.dest, ocr.CACHE, "file.json"), encoding="utf-8") as f:
                return json.load(f)["etat"]

        def executer(args, *, delai, arreter=None):
            if not premiere.is_set():
                premiere.set()
                self.assertTrue(relache.wait(15), "la page 1 n'a pas ete relachee")
            return vrai(args, delai=delai, arreter=arreter)

        with mock.patch.object(ocr, "executer", executer):
            self.lancer("Cours A/S1/scan.pdf")
            self.assertTrue(premiere.wait(15), "aucune page n'a demarre")
            self.assertIn("file", self.api.ocr_pause())            # pause demandee pendant la page 1
            relache.set()
            # La file ne peut que se mettre en pause ou finir : on l'attend sans delai fixe.
            self.assertTrue(self.attendre(lambda: etat_brut() in ("pause", "terminee")))
            self.assertEqual(etat_brut(), "pause")
            faites = len(self.pages_vues)
            self.assertEqual(faites, 1)                            # aucune page pendant la pause
            self.assertIn("file", self.api.ocr_reprendre())
            self.assertTrue(self.attendre(lambda: etat_brut() == "terminee"))
        self.assertEqual(len(self.pages_vues), 4)
        self.assertEqual(faites, 1)

    def test_annuler(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)] * 4)
        self.delai_page = 0.03
        self.lancer("Cours A/S1/scan.pdf")
        self.assertTrue(self.attendre(lambda: self.pages_vues))
        self.assertIn("file", self.api.ocr_annuler())
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "annulee"))
        self.assertEqual([t["etat"] for t in self.fichier()["taches"]], ["attente"])

    def test_sync_pendant_extraction(self):
        """Invariant 7 : l'extraction cede la main a la synchronisation entre deux pages."""
        self.ranger("Cours A/S1/scan.pdf", [([], True)] * 6)
        self.delai_page = 0.05
        self.api.sync_verifier()
        self.lancer("Cours A/S1/scan.pdf")
        self.assertTrue(self.attendre(lambda: self.pages_vues), "aucune page n'a demarre")
        self.json_ok(self.api.sync_lancer(True))
        self.assertEqual(self.pendant_sync["travaux"], 0)          # aucune page pendant la synchronisation
        self.assertTrue(self.pendant_sync["sync"])
        self.assertTrue(self.pendant_sync["fichiers"])
        self.assertEqual(self.pendant_sync["etat"], "pause_sync")
        self.assertEqual(self.max_travaux, 1)                       # jamais deux pages a la fois
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertEqual(len(self.pages_vues), 6)

    def test_document_en_erreur_n_arrete_pas_la_file(self):
        self.ranger("Cours A/S1/abime.pdf", [([], True)])
        self.ranger("Cours A/S1/bon.pdf", [([], True)])
        appels = []

        def traiter(dest, chemin_rel, cfg, **kw):
            appels.append(chemin_rel)
            if chemin_rel.endswith("abime.pdf"):
                raise ocr.ErreurOcr("corrompu")
            return {"entree": {"pages": 1}, "message": ""}
        with mock.patch.object(ocr, "traiter_document", traiter):
            self.lancer("Cours A/S1/abime.pdf", "Cours A/S1/bon.pdf")
            self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        taches = {t["chemin"]: t for t in self.fichier()["taches"]}
        self.assertEqual(appels, ["Cours A/S1/abime.pdf", "Cours A/S1/bon.pdf"])
        self.assertEqual({c: t["etat"] for c, t in taches.items()},
                         {"Cours A/S1/abime.pdf": "erreur", "Cours A/S1/bon.pdf": "fait"})
        self.assertEqual(taches["Cours A/S1/abime.pdf"]["message"], ocr.MESSAGES["corrompu"])
        self.assertIn("textesJournal", " ".join(self.fenetre.appels))     # la phrase part au journal
        self.assertNotIn("Traceback", " ".join(self.fenetre.appels))


# ====================================================================== confinement et ouverture
class Confinement(Base):
    """Contrat 4 et invariant 8 : tout chemin recu est confine au coffre."""

    def setUp(self):
        super().setUp()
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        self.md = os.path.join(self.dest, "Cours A", "S1", "scan.pdf.md")
        with open(self.md, "w", encoding="utf-8") as f:
            f.write("Page un.")
        # `ocr_ouvrir` ouvre desormais le PDF par le lecteur du systeme (contrat 4.1, R7c) : le
        # lancement est double, aucun lecteur ne s'ouvre pendant les tests.
        p = mock.patch("moodlesync.api_textes.subprocess.Popen")
        self.lance = p.start()
        self.addCleanup(p.stop)

    def test_chemin_refuse_ou_absent_phrase_dediee(self):
        refus = {"erreur": ocr.MESSAGES["ouverture_refusee"]}
        chemins = ("../secret.pdf", "/etc/passwd", "C:x", "C:/x/y.pdf", ".moodlesync-ocr/cache.json",
                   "Cours A/../../x", ".moodlesync.json", "Cours A/S1/absent.pdf", "", "   ", None, 5,
                   ["Cours A"], {"a": 1})
        for chemin in chemins:
            with self.subTest(chemin=chemin):
                self.assertEqual(self.json_ok(self.api.ocr_ouvrir(chemin)), refus)

    def test_octet_nul_donne_la_phrase_de_refus_sans_trace(self):
        avant = os.path.getsize(ms.ERREURS) if os.path.exists(ms.ERREURS) else 0
        for chemin in ("a\x00b", "Cours A/S1/scan.pdf\x00.png", "Cours A\x00", "\x00"):
            with self.subTest(chemin=chemin):
                self.assertEqual(self.api.ocr_ouvrir(chemin), {"erreur": ocr.MESSAGES["ouverture_refusee"]})
        self.assertEqual(os.path.getsize(ms.ERREURS) if os.path.exists(ms.ERREURS) else 0, avant)

    def test_source_et_dossier(self):
        """4.1 : un fichier est ouvert par le lecteur du systeme, un dossier est refuse (`ocr_afficher` le montre)."""
        self.assertEqual(self.api.ocr_ouvrir("Cours A/S1/scan.pdf"), {"ok": True})
        self.assertEqual(self.api.ocr_ouvrir("Cours A/S1/scan.pdf.md"), {"ok": True})
        self.assertEqual(self.api.ocr_ouvrir("Cours A"), {"erreur": ocr.MESSAGES["ouverture_refusee"]})

    def test_chemin_absolu_dans_dest(self):
        self.assertEqual(self.api.ocr_ouvrir(self.md), {"ok": True})

    def test_dossier_de_rangement_absent(self):
        c = self.config()
        c["dest"] = ""
        self.configurer(c)
        self.assertEqual(self.api.ocr_ouvrir("Cours A"), {"erreur": ocr.MESSAGES["dossier_absent"]})

    def test_lien_symbolique_vers_l_exterieur_refuse(self):
        dehors = os.path.join(self.d, "dehors")
        os.makedirs(dehors)
        secret = os.path.join(dehors, "secret.pdf")
        with open(secret, "wb") as f:
            f.write(pdf_minimal([([], True)]))
        lien_dossier = os.path.join(self.dest, "lien")
        lien_fichier = os.path.join(self.dest, "Cours A", "S1", "copie.pdf")
        try:
            os.symlink(dehors, lien_dossier)
            os.symlink(secret, lien_fichier)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles")
        refus = {"erreur": ocr.MESSAGES["ouverture_refusee"]}
        for chemin in ("lien", "lien/secret.pdf", "Cours A/S1/copie.pdf", lien_fichier):
            with self.subTest(chemin=chemin):
                self.assertEqual(self.api.ocr_ouvrir(chemin), refus)
                self.assertEqual(self.api.ocr_copier_texte(chemin), refus)

    def test_lien_symbolique_interne_accepte(self):
        lien = os.path.join(self.dest, "interne")
        try:
            os.symlink(os.path.join(self.dest, "Cours A"), lien)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles")
        self.assertEqual(self.api.ocr_ouvrir("interne/S1/scan.pdf"), {"ok": True})


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


# ====================================================================== phrases
CODES_A3 = ("dossier_absent", "fenetre_fermee", "valeur_invalide", "reglage_inconnu", "chemin_introuvable",
            "occupe", "ouverture_refusee", "ouverture_impossible",
            "installation_faite", "installation_echec", "paquet_hors_ligne", "paquet_invalide")   # quatre derniers : I1
CODES_I1 = ("installation_faite", "installation_echec", "paquet_hors_ligne", "paquet_invalide")
# Phrases de la refonte (contrat 5.5) que ocr.MESSAGES porte.
CODES_REFONTE = ("confirmation_traitement", "confirmation_restauration", "restauration_texte_garde", "copie_vide",
                 "depot_pas_pdf", "occupe", "confirmation_originaux")


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
    for interdit in ("Traceback", "site-packages", 'File "', '.py"', ".py,", "line "):
        if interdit in texte:
            return False
    if texte.startswith(api_textes.ACTION + " : ") or texte.startswith("Textes des cours : ") \
            or texte == app.SESSION_EXPIREE:
        return True
    return any(m.match(texte) for m in motifs)


class Messages(Base):
    """Invariant 9 et contrat 5.5 : les phrases visibles viennent de ocr.MESSAGES, et les nouvelles y sont."""

    def test_codes_presents_et_mots_interdits(self):
        import re
        for code in CODES_A3:
            with self.subTest(code=code):
                self.assertIn(code, ocr.MESSAGES)
                self.assertTrue(ocr.MESSAGES[code].strip())
                self.assertIsNone(re.search(r"\b(OCR|Tesseract|tessdata|DPI|PSM|TSV)\b", phrase(self, code)), code)

    def test_codes_de_la_refonte(self):
        phrases = {
            "confirmation_traitement": "2 documents, environ 31 pages, 1 à 3 minutes. 2 PDF seront remplacés par "
                                       "une version cherchable ; une copie de chaque original est gardée.",
            "confirmation_restauration": "Remettre le PDF d'origine et supprimer le texte ?",
            "restauration_texte_garde": "Le PDF d'origine est remis. Le texte, que tu avais modifié, est resté en "
                                        "place.",
            "copie_vide": "Ce document n'a pas de texte à copier.",
            "depot_pas_pdf": "Seuls les PDF peuvent être déposés.",
            "motif_difficile": "Le texte de ce document est trop abîmé pour être lu. Ton PDF est resté tel quel.",
            "motif_vide": "Aucun texte n'a été trouvé dans ce document. Ton PDF est resté tel quel.",
            "motif_illisible": "Ce document n'a pas pu être lu. Ton PDF est resté tel quel.",
            "motif_verification": "Le PDF cherchable n'a pas passé la vérification. Ton PDF est resté tel quel.",
            "motif_ecriture": "Le résultat n'a pas pu être écrit. Ton PDF est resté tel quel.",
            "motif_erreur": "Cette opération n'a pas abouti. Ton PDF est resté tel quel.",
        }
        for code, texte in phrases.items():
            with self.subTest(code=code):
                if code == "confirmation_traitement":
                    self.assertEqual(phrase(self, code, n="2 documents", p="31 pages", m=1, x=3, r=2), texte)
                else:
                    self.assertEqual(phrase(self, code), texte)

    def test_occupe_identique_a_celle_de_application(self):
        self.assertEqual(phrase(self, "occupe"), app.OCCUPE)

    def test_aucun_tiret_long(self):
        for code in CODES_REFONTE:
            self.assertNotIn(chr(0x2014), phrase(self, code))
            self.assertNotIn(chr(0x2013), phrase(self, code))

    def test_codes_de_i1_dans_codes_a3(self):
        for code in CODES_I1:
            with self.subTest(code=code):
                self.assertIn(code, CODES_A3)
                self.assertIn(code, ocr.MESSAGES)

    def test_aucune_copie_locale(self):
        for nom in ("MESSAGES_TEXTE", "DOSSIER_ABSENT", "FENETRE_FERMEE", "OCCUPE"):
            with self.subTest(nom=nom):
                self.assertFalse(hasattr(api_textes, nom), nom)

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


class AucuneTrace(Base):
    """Porte de sortie : aucune reponse d'une methode publique ne porte de trace technique ni de phrase absente de
    ocr.MESSAGES (hors celles que ms.message_erreur fabrique)."""

    FAUX_WEBVIEW = SimpleNamespace(SAVE_DIALOG=30, FOLDER_DIALOG=20, OPEN_DIALOG=10)

    def appels(self):
        a = self.api
        return [
            ("ocr_etat", lambda: a.ocr_etat()), ("ocr_detecter", lambda: a.ocr_detecter()),
            ("ocr_choisir_exe", lambda: a.ocr_choisir_exe()), ("ocr_installer", lambda: a.ocr_installer()),
            ("ocr_traiter", lambda: a.ocr_traiter()), ("ocr_traiter", lambda: a.ocr_traiter(3, 4, "x")),
            ("ocr_traiter", lambda: a.ocr_traiter(["../x"])),
            ("ocr_pause", lambda: a.ocr_pause()), ("ocr_reprendre", lambda: a.ocr_reprendre()),
            ("ocr_annuler", lambda: a.ocr_annuler()),
            ("ocr_ouvrir", lambda: a.ocr_ouvrir("../x")), ("ocr_ouvrir", lambda: a.ocr_ouvrir("a\x00b")),
            ("ocr_ouvrir", lambda: a.ocr_ouvrir("Cours A/S1/absent.pdf")), ("ocr_ouvrir", lambda: a.ocr_ouvrir(None)),
            ("ocr_copier_texte", lambda: a.ocr_copier_texte("Cours A/S1/absent.pdf")),
            ("ocr_copier_texte", lambda: a.ocr_copier_texte(None)),
            ("ocr_restaurer", lambda: a.ocr_restaurer("Cours A/S1/absent.pdf")),
            ("ocr_restaurer", lambda: a.ocr_restaurer(None)),
            ("ocr_originaux_supprimer", lambda: a.ocr_originaux_supprimer()),
            ("ocr_regler", lambda: a.ocr_regler("inconnu", 1)), ("ocr_regler", lambda: a.ocr_regler("ocr_dpi", "x")),
            ("ocr_regler", lambda: a.ocr_regler("ocr_dossier", "Cours A")),
            ("ocr_regler", lambda: a.ocr_regler("ocr_exe", "/inexistant/tesseract")),
            ("ocr_regler", lambda: a.ocr_regler("ocr_pdf", "copie")),
            ("ocr_regler", lambda: a.ocr_regler("ocr_langues", "zzz")), ("ocr_regler", lambda: a.ocr_regler(None, None)),
            ("ocr_arbre", lambda: a.ocr_arbre()), ("ocr_afficher", lambda: a.ocr_afficher("../x")),
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

    def test_le_filtre_de_phrases_distingue(self):
        motifs = motifs_des_phrases()
        self.assertTrue(phrase_permise(ocr.MESSAGES["corrompu"], motifs))
        self.assertTrue(phrase_permise(phrase(self, "reglage_inconnu", cle="x"), motifs))
        self.assertTrue(phrase_permise(api_textes.ACTION + " : erreur imprévue. Le détail est noté dans e.txt.", motifs))
        for mauvaise in ("Valeur invalide pour moi.", "Une phrase inventée.", "Traceback (most recent call last):",
                         'File "x.py", line 3'):
            self.assertFalse(phrase_permise(mauvaise, motifs), mauvaise)


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
