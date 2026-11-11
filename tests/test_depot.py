"""Tests hors ligne du depot de fichiers hors Moodle (tache R5, contrat 4.6, decisions O12 et O16).

Aucune fenetre native, aucun reseau, aucun vrai moteur : le moteur de reconnaissance est une doublure et les PDF
sont fabriques a la main (`tests/test_api_textes.pdf_minimal`). La fabrication du PDF cherchable, elle, est la
vraie : c'est ce qui prouve que la copie deposee est inscrite dans l'etat du mini-coffre avant le traitement
(ecart E-R2-1 de R2). Les reponses sont comparees a `docs/refonte-textes/fixtures/depot.json` par
`tests.formes_refonte.differences`.

Ce que ces tests ne mesurent pas : ni Windows ni macOS (l'attribut cache est mesure avec `ctypes` double), et
aucun glisser-deposer reel, qui n'existe ni ici ni sur la machine de mesure (O16).

Lancer depuis la racine du depot : python -m unittest discover -s tests -t . -v
"""
import hashlib, io, json, os, sys, tempfile, threading, time, unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import api_depot, application as app, moteur as ms, ocr
from tests import test_api_textes as T
from tests.formes_refonte import charger_fixture, differences

SCAN = ([], True)          # page sans texte natif, avec une image : a reconnaitre, donc PDF remplace
BLOC_MOTEUR = dict(T.BLOC_MOTEUR)
DOSSIER_DEPOT = os.path.join(os.path.expanduser("~"), "Desktop", "Documents déposés")


def sha256(chemin):
    with open(chemin, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def identite(chemin):
    """(empreinte, taille, date de modification en nanosecondes) d'un fichier."""
    st = os.stat(chemin)
    return sha256(chemin), st.st_size, st.st_mtime_ns


def contenu(dossier):
    """Tout ce que contient un dossier, recursivement : chemin relatif vers octets."""
    etat = {}
    for racine, dossiers, fichiers in os.walk(dossier):
        for nom in dossiers:
            etat[os.path.relpath(os.path.join(racine, nom), dossier) + "/"] = b""
        for nom in fichiers:
            chemin = os.path.join(racine, nom)
            with open(chemin, "rb") as f:
                etat[os.path.relpath(chemin, dossier)] = f.read()
    return etat


def visibles(dossier):
    """Noms visibles d'un dossier : le cache `.moodlesync-ocr` est cache, il ne compte pas (O12)."""
    if not os.path.isdir(dossier):
        return []
    return sorted(n for n in os.listdir(dossier) if not n.startswith("."))


def pdf_protege(chemin, mot_de_passe="secret"):
    """PDF chiffre par un mot de passe utilisateur, lu par pypdf comme n'importe quel lecteur."""
    import pypdf
    lecteur = pypdf.PdfReader(io.BytesIO(T.pdf_minimal([SCAN])))
    ecrivain = pypdf.PdfWriter()
    for page in lecteur.pages:
        ecrivain.add_page(page)
    ecrivain.encrypt(mot_de_passe)
    with open(chemin, "wb") as f:
        ecrivain.write(f)
    return chemin


class FauxElement:
    """Element DOM de pywebview : retient ses ecouteurs."""

    def __init__(self):
        self.ecouteurs = []

    def on(self, evenement, fonction):
        self.ecouteurs.append((evenement, fonction))

    def off(self, evenement, fonction):
        self.ecouteurs = [e for e in self.ecouteurs if e != (evenement, fonction)]


class FauxDom:
    """`window.dom` de pywebview : rend les elements demandes, ou None."""

    def __init__(self, elements):
        self.elements = elements
        self.demandes = []

    def get_element(self, selecteur):
        self.demandes.append(selecteur)
        return self.elements.get(selecteur)


class FauxCtypes:
    """`ctypes` double : `windll.kernel32.SetFileAttributesW` retient ses appels."""

    def __init__(self, reponse=1):
        self.appels = []
        self.reponse = reponse
        self.c_wchar_p = lambda valeur: ("c_wchar_p", valeur)
        self.windll = mock.Mock()
        self.windll.kernel32.SetFileAttributesW.side_effect = self._poser

    def _poser(self, *arguments):
        self.appels.append(arguments)
        return self.reponse


class Banc(unittest.TestCase):
    """Reglages et journal dans un dossier temporaire, moteur simule, un dossier de depot hors du coffre."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = self.tmp.name
        self.dest = os.path.join(self.d, "coffre")
        self.depot = os.path.join(self.d, "Documents déposés")
        os.makedirs(self.dest)
        self.fenetre = T.FauxFenetre()
        self.bloc = dict(BLOC_MOTEUR)
        self.confiance = 91.0                  # confiance des mots de la doublure (0,91 : document « bon »)
        self.arret_apres = 0                   # pages reconnues avant de demander l'arret du depot
        self.pages_vues = []
        self.sauve = {n: getattr(ms, n) for n in ("APP_DIR", "CONFIG", "DEMARRAGE", "ERREURS")}
        self.addCleanup(self.restaurer)
        ms.APP_DIR, ms.CONFIG = self.d, os.path.join(self.d, "config.json")
        ms.DEMARRAGE, ms.ERREURS = os.path.join(self.d, "demarrage.lnk"), os.path.join(self.d, "erreurs.txt")
        self.configurer({"dest": self.dest, "ocr_format": "md", "ocr_max_mo": 300, "token": "", "cours": {}})
        for nom, valeur in (("detecter", lambda cfg: dict(self.bloc)), ("executer", self.executer),
                            ("rendre_page", self.rendre)):
            p = mock.patch.object(ocr, nom, valeur)
            p.start()
            self.addCleanup(p.stop)
        self.api = app.Api()
        self.api._fenetre = self.fenetre

    def restaurer(self):
        for nom, valeur in self.sauve.items():
            setattr(ms, nom, valeur)

    def configurer(self, c):
        with open(ms.CONFIG, "w", encoding="utf-8") as f:
            json.dump(c, f)

    def config(self):
        with open(ms.CONFIG, encoding="utf-8") as f:
            return json.load(f)

    def regler(self, **champs):
        c = self.config()
        c.update(champs)
        self.configurer(c)

    # -- doublures du moteur
    def executer(self, args, *, delai, arreter=None):
        self.pages_vues.append((args[0], args[1]))
        if self.arret_apres and len(self.pages_vues) >= self.arret_apres:
            self.api._ocr_arret.set()
        tsv = T.TSV.replace("\t91.0\t", "\t%s\t" % self.confiance)
        return 0, tsv.encode("utf-8"), b""

    def rendre(self, chemin, numero, dpi, **kw):
        from PIL import Image
        return Image.new("L", (120, 60), 255)

    # -- outils
    def pdf(self, nom, pages=(SCAN,), dossier=None):
        """Un PDF fabrique a la main, range dans `dossier` (le dossier de travail par defaut)."""
        base = dossier or self.d
        chemin = os.path.join(base, nom)
        os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(T.pdf_minimal(list(pages)))
        return chemin

    def fichier(self, nom, octets=b"pas un pdf", dossier=None):
        base = dossier or self.d
        os.makedirs(base, exist_ok=True)
        chemin = os.path.join(base, nom)
        with open(chemin, "wb") as f:
            f.write(octets)
        return chemin

    def deposer(self, fichiers, dossier=None, delai=20):
        """Depot en deux temps, puis attente de la fin : les resultats de 4.6."""
        r = self.api.ocr_deposer(fichiers, dossier or self.depot)
        if "confirmer" not in r:
            return r
        lance = self.api.ocr_deposer(fichiers, dossier or self.depot, confirme=True)
        self.assertIn("depot", lance, lance)
        self.assertTrue(self.attendre(lambda: self.api.ocr_etat()["depot"]["etat"] == "termine", delai),
                        "le depot ne s'est pas termine")
        return self.api.ocr_etat()["depot"]

    def attendre(self, condition, delai=20):
        limite = time.monotonic() + delai
        while time.monotonic() < limite:
            if condition():
                return True
            time.sleep(0.01)
        return condition()

    def json_ok(self, r):
        json.dumps(r)
        return r


# ------------------------------------------------------------------ branchement
class Branchement(Banc):
    """Contrat 4.6 et 4.2 : le mixin est branche, il fabrique le bloc depot, ses trois methodes existent."""

    def test_mixin_branche(self):
        self.assertIsInstance(self.api, api_depot.ApiDepot)
        for nom in ("_depot_verrou", "_depot_fil", "_depot_etat_bloc", "_depot_dossier", "_depot_resultats"):
            self.assertTrue(hasattr(self.api, nom), nom)
        self.assertIsInstance(self.api._depot_verrou, type(threading.Lock()))

    def test_bloc_depot_vient_du_mixin_du_depot(self):
        self.assertIs(app.Api._depot_etat, api_depot.ApiDepot._depot_etat)
        self.assertEqual(self.json_ok(self.api.ocr_etat())["depot"],
                         {"etat": "inactif", "dossier_defaut": DOSSIER_DEPOT, "dossier": "", "resultats": []})

    def test_trois_methodes(self):
        for nom in ("ocr_choisir_fichiers", "ocr_choisir_dossier_depot", "ocr_deposer"):
            with self.subTest(methode=nom):
                self.assertTrue(callable(getattr(self.api, nom)))

    def test_dossier_par_defaut(self):
        """4.2 : « Documents déposés » sur le Bureau, et un dossier vide vaut ce defaut."""
        self.assertEqual(api_depot.dossier_depot_defaut(), DOSSIER_DEPOT)
        self.assertEqual(self.api._depot_cible(""), DOSSIER_DEPOT)
        self.assertEqual(self.api._depot_cible("   "), DOSSIER_DEPOT)


# ------------------------------------------------------------------ boites de dialogue
class Dialogues(Banc):
    """4.6 : les deux boites natives rendent des chemins absolus, ou `{"annule": True}`."""

    def test_choisir_fichiers(self):
        choix = [os.path.join(self.d, "a.pdf"), os.path.join(self.d, "b.pdf")]
        self.fenetre.choix = choix
        faux = mock.Mock()
        faux.OPEN_DIALOG = "open"
        faux.FOLDER_DIALOG = "folder"
        with mock.patch.dict(sys.modules, {"webview": faux}):
            r = self.api.ocr_choisir_fichiers()
        self.assertEqual(r, {"fichiers": [os.path.abspath(c) for c in choix]})

    def test_choisir_fichiers_annule(self):
        self.fenetre.choix = None
        faux = mock.Mock()
        with mock.patch.dict(sys.modules, {"webview": faux}):
            self.assertEqual(self.api.ocr_choisir_fichiers(), {"annule": True})

    def test_choisir_dossier_depot(self):
        self.fenetre.choix = self.depot
        faux = mock.Mock()
        with mock.patch.dict(sys.modules, {"webview": faux}):
            r = self.api.ocr_choisir_dossier_depot()
        self.assertEqual(r, {"dossier": os.path.abspath(self.depot)})
        self.assertEqual(faux.FOLDER_DIALOG, faux.FOLDER_DIALOG)

    def test_choisir_dossier_annule(self):
        self.fenetre.choix = None
        with mock.patch.dict(sys.modules, {"webview": mock.Mock()}):
            self.assertEqual(self.api.ocr_choisir_dossier_depot(), {"annule": True})

    def test_fenetre_absente(self):
        self.api._fenetre = None
        with mock.patch.dict(sys.modules, {"webview": mock.Mock()}):
            for r in (self.api.ocr_choisir_fichiers(), self.api.ocr_choisir_dossier_depot()):
                self.assertEqual(r, {"erreur": ocr.MESSAGES["fenetre_fermee"]})


# ------------------------------------------------------------------ refus (4.6)
class Refus(Banc):
    """4.6 et U8 : seuls les PDF, et chaque refus porte sa phrase. Rien n'est copie."""

    def refus(self, chemin, **reglages):
        self.regler(**reglages)
        r = self.api.ocr_deposer([chemin], self.depot)
        self.assertIn("confirmer", r, r)
        self.assertEqual(len(r["refuses"]), 1, r)
        return r["refuses"][0]

    def test_pas_un_pdf(self):
        r = self.refus(self.fichier("notes.docx"))
        self.assertEqual(r, {"nom": "notes.docx", "raison": ocr.MESSAGES["depot_pas_pdf"]})
        self.assertFalse(os.path.isdir(self.depot))

    def test_introuvable(self):
        r = self.refus(os.path.join(self.d, "absent.pdf"))
        self.assertEqual(r, {"nom": "absent.pdf", "raison": ocr.MESSAGES["chemin_introuvable"]})

    def test_protege(self):
        chemin = pdf_protege(os.path.join(self.d, "cache.pdf"))
        r = self.refus(chemin)
        self.assertEqual(r, {"nom": "cache.pdf", "raison": ocr.MESSAGES["protege"]})

    def test_trop_gros(self):
        chemin = self.pdf("gros.pdf")
        r = self.refus(chemin, ocr_max_mo=0)
        self.assertEqual(r, {"nom": "gros.pdf", "raison": ocr.MESSAGES["trop_gros"].format(mo=0)})

    def test_melange_accepte_et_refuse(self):
        bon = self.pdf("scan.pdf", [SCAN] * 2)
        r = self.api.ocr_deposer([bon, self.fichier("notes.docx"), os.path.join(self.d, "absent.pdf")], self.depot)
        self.assertEqual(r["documents"], 1)
        self.assertEqual(r["pages"], 2)
        self.assertEqual([x["nom"] for x in r["refuses"]], ["notes.docx", "absent.pdf"])
        self.assertFalse(os.path.isdir(self.depot))          # ni copie ni dossier a ce stade

    def test_tout_refuse_ne_copie_rien(self):
        r = self.api.ocr_deposer([self.fichier("notes.docx")], self.depot, confirme=True)
        self.assertIn("depot", r)
        self.assertTrue(self.attendre(lambda: self.api.ocr_etat()["depot"]["etat"] == "termine"))
        depot = self.api.ocr_etat()["depot"]
        self.assertEqual([x["statut"] for x in depot["resultats"]], ["refuse"])
        self.assertEqual(depot["resultats"][0]["motif"], "depot_pas_pdf")
        self.assertEqual(depot["resultats"][0]["sortie_pdf"], "")
        self.assertEqual(os.listdir(self.depot), [])


# ------------------------------------------------------------------ confirmation et formes
class Formes(Banc):
    """4.6 : confirmation en deux temps, formes de `fixtures/depot.json`."""

    def test_sans_confirme_ne_copie_rien(self):
        bon = self.pdf("scan.pdf", [SCAN] * 20)
        autre = self.fichier("notes.docx")
        avant = contenu(self.d)
        r = self.json_ok(self.api.ocr_deposer([bon, autre], self.depot))
        self.assertEqual(differences(charger_fixture("depot.json")["confirmation"], r), [])
        self.assertEqual(r["documents"], 1)
        self.assertEqual(r["pages"], 20)
        self.assertEqual(r["minutes"], [5, 10], "20 pages : 15 s minimum et 30 s maximum par page (E-V7-4)")
        self.assertEqual(r["refuses"], [{"nom": "notes.docx", "raison": ocr.MESSAGES["depot_pas_pdf"]}])
        self.assertEqual(contenu(self.d), avant)
        self.assertFalse(os.path.isdir(self.depot))

    def test_avec_confirme_travaille_en_fond(self):
        bon = self.pdf("scan.pdf", [SCAN] * 2)
        r = self.api.ocr_deposer([bon], self.depot, confirme=True)
        self.assertIn(r["depot"]["etat"], ("en_cours", "termine"), r)
        self.assertEqual(r["depot"]["dossier"], os.path.abspath(self.depot))
        self.assertTrue(self.attendre(lambda: self.api.ocr_etat()["depot"]["etat"] == "termine"))

    def test_forme_du_bloc_depot_apres_travail(self):
        self.deposer([self.pdf("scan.pdf", [SCAN] * 2), self.fichier("notes.docx")])
        depot = self.json_ok(self.api.ocr_etat()["depot"])
        self.assertEqual(differences(charger_fixture("depot.json")["depot"], depot), [])
        self.assertEqual([x["statut"] for x in depot["resultats"]], ["ok", "refuse"])

    def test_forme_d_un_resultat_en_echec(self):
        self.confiance = 30.0
        depot = self.json_ok(self.deposer([self.pdf("flou.pdf", [SCAN])]))
        self.assertEqual(sorted(depot["resultats"][0]),
                         ["motif", "nom", "pages", "sortie_pdf", "sortie_texte", "statut"])

    def test_resultat_d_un_succes(self):
        depot = self.deposer([self.pdf("scan.pdf", [SCAN] * 2)])
        resultat = depot["resultats"][0]
        self.assertEqual(resultat["statut"], "ok")
        self.assertEqual(resultat["motif"], "")
        self.assertEqual(resultat["pages"], 2)
        self.assertTrue(resultat["sortie_pdf"].startswith(os.path.abspath(self.depot)))
        self.assertTrue(os.path.isfile(resultat["sortie_pdf"]))
        self.assertTrue(os.path.isfile(resultat["sortie_texte"]))
        self.assertEqual(depot["etat"], "termine")
        self.assertEqual(depot["dossier"], os.path.abspath(self.depot))

    def test_occupe(self):
        self.api._depot_verrou.acquire()
        self.addCleanup(self.api._depot_verrou.release)
        r = self.api.ocr_deposer([self.pdf("scan.pdf")], self.depot, confirme=True)
        self.assertEqual(r, {"erreur": ocr.MESSAGES["occupe"]})

    def test_moteur_absent(self):
        self.bloc["present"] = False
        self.api._ocr_memo = None
        r = self.api.ocr_deposer([self.pdf("scan.pdf")], self.depot)
        self.assertEqual(r, {"erreur": ocr.MESSAGES["moteur_absent"]})

    def test_aucun_fichier(self):
        self.assertEqual(self.api.ocr_deposer([], self.depot), {"annule": True})


# ------------------------------------------------------------------ traitement (4.6)
class Traitement(Banc):
    """4.6 : copie dans le dossier (jamais de deplacement), nom libre, echec sans trace, mini-coffre."""

    def test_copie_jamais_deplacement(self):
        source = self.pdf("scan.pdf", [SCAN] * 2)
        avant = identite(source)
        depot = self.deposer([source])
        self.assertEqual(depot["resultats"][0]["statut"], "ok")
        self.assertTrue(os.path.isfile(source), "le fichier d'origine a disparu")
        self.assertEqual(identite(source), avant, "le fichier d'origine a change")
        self.assertEqual(os.listdir(self.depot).count("scan.pdf"), 1)
        self.assertTrue(os.path.isfile(os.path.join(self.depot, "scan.pdf")))
        self.assertTrue(os.path.isfile(os.path.join(self.depot, "scan.pdf.md")))

    def test_nom_deja_pris(self):
        self.fichier("scan.pdf", b"deja la", dossier=self.depot)
        depot = self.deposer([self.pdf("scan.pdf", [SCAN])])
        self.assertEqual(depot["resultats"][0]["statut"], "ok")
        self.assertTrue(os.path.isfile(os.path.join(self.depot, "scan (2).pdf")))
        self.assertTrue(os.path.isfile(os.path.join(self.depot, "scan (2).pdf.md")))
        with open(os.path.join(self.depot, "scan.pdf"), "rb") as f:
            self.assertEqual(f.read(), b"deja la")            # le fichier present n'est pas ecrase

    def test_nom_deja_pris_deux_fois(self):
        self.deposer([self.pdf("scan.pdf", [SCAN])])
        self.deposer([self.pdf("scan.pdf", [SCAN])])
        for nom in ("scan.pdf", "scan (2).pdf"):
            with self.subTest(nom=nom):
                self.assertTrue(os.path.isfile(os.path.join(self.depot, nom)))

    def test_nom_libre(self):
        self.assertEqual(api_depot.nom_libre(self.depot, "x.pdf"), "x.pdf")
        self.fichier("x.pdf", dossier=self.depot)
        self.assertEqual(api_depot.nom_libre(self.depot, "x.pdf"), "x (2).pdf")
        self.fichier("x (2).pdf", dossier=self.depot)
        self.assertEqual(api_depot.nom_libre(self.depot, "x.pdf"), "x (3).pdf")

    def test_nom_libre_compte_les_textes(self):
        """E-V4-1 : un texte sans son PDF occupe le nom, dans les deux formats (contrat 4.6, invariant 3)."""
        for suffixe in (".md", ".txt"):
            with self.subTest(suffixe=suffixe):
                os.makedirs(self.depot, exist_ok=True)
                for nom in os.listdir(self.depot):
                    os.remove(os.path.join(self.depot, nom))
                self.fichier("y.pdf" + suffixe, b"mon texte", dossier=self.depot)
                self.assertEqual(api_depot.nom_libre(self.depot, "y.pdf"), "y (2).pdf")

    def test_texte_preexistant_survit_a_un_echec(self):
        """E-V4-1 : le texte de l'etudiant, seul dans le dossier, n'est jamais supprime par un depot en echec."""
        for suffixe in (".md", ".txt"):
            with self.subTest(suffixe=suffixe):
                self.confiance = 30.0                                  # document « Difficile » : echec (U4)
                dossier = os.path.join(self.d, "depot" + suffixe.replace(".", "-"))
                os.makedirs(dossier)
                sien = self.fichier("scan.pdf" + suffixe, b"TEXTE A MOI " + suffixe.encode(), dossier=dossier)
                avant = identite(sien)
                depot = self.deposer([self.pdf("scan.pdf", [SCAN])], dossier)
                self.assertEqual(depot["resultats"][0]["statut"], "echec")
                self.assertTrue(os.path.isfile(sien), "le texte de l'etudiant a ete supprime")
                self.assertEqual(identite(sien), avant, "le texte de l'etudiant a change")
                self.assertEqual(visibles(dossier), ["scan.pdf" + suffixe], "rien d'autre ne reste")

    def test_un_depot_reussi_ne_pointe_jamais_vers_un_autre_texte(self):
        """E-V4-2 : consequence de E-V4-1, le resultat pointe vers le texte du document depose, pas vers un autre."""
        for format_texte in ("md", "txt"):
            with self.subTest(format=format_texte):
                self.regler(ocr_format=format_texte)
                dossier = os.path.join(self.d, "reussi-" + format_texte)
                os.makedirs(dossier)
                sien = self.fichier("scan.pdf." + format_texte, b"TEXTE A MOI\n", dossier=dossier)
                depot = self.deposer([self.pdf("scan.pdf", [SCAN])], dossier)
                resultat = depot["resultats"][0]
                self.assertEqual(resultat["statut"], "ok")
                self.assertEqual(os.path.basename(resultat["sortie_pdf"]), "scan (2).pdf")
                self.assertEqual(os.path.basename(resultat["sortie_texte"]), "scan (2).pdf." + format_texte)
                self.assertTrue(os.path.isfile(resultat["sortie_texte"]))
                with open(sien, "rb") as f:
                    self.assertEqual(f.read(), b"TEXTE A MOI\n", "le texte de l'etudiant n'est pas touche")
                with open(resultat["sortie_texte"], encoding="utf-8") as f:
                    self.assertNotIn("TEXTE A MOI", f.read(), "le resultat ne pointe pas vers l'autre texte")

    def test_un_texte_ecrit_puis_un_echec_est_retire(self):
        """E-V4-5 (mutation R5-8) : un texte ecrit par ce depot puis suivi d'un echec est retire par `_depot_effacer`."""
        def faux(dossier, rel, cfg, **autres):
            chemin = ocr.chemin_texte(dossier, rel, cfg)[0]
            with open(chemin, "w", encoding="utf-8", newline="\n") as f:
                f.write("texte ecrit juste avant l'echec\n")
            return {"entree": {}, "statut": "echec", "motif": "verification", "remplace": False, "texte": False}
        with mock.patch.object(ocr, "traiter_document", faux):
            depot = self.deposer([self.pdf("scan.pdf", [SCAN])])
        self.assertEqual(depot["resultats"][0]["statut"], "echec")
        self.assertEqual(visibles(self.depot), [], "un echec ne laisse ni copie ni texte")

    def test_pdf_a_reconnaitre_devient_cherchable(self):
        """E-R2-1 : la copie inscrite dans l'etat du mini-coffre (O12) est remplacee par sa version cherchable.

        `fabriquer_pdf_cherchable` refuse un PDF absent de `.moodlesync.json` (`non_suivi`) : sans l'inscription de
        `_depot_inscrire`, ce depot finirait en echec `verification`, avec la vraie fabrication.
        """
        depot = self.deposer([self.pdf("scan.pdf", [SCAN])])
        resultat = depot["resultats"][0]
        self.assertEqual(resultat["statut"], "ok", depot)
        self.assertEqual(resultat["motif"], "")
        entree = next(iter(ocr.charger_cache(self.depot)["documents"].values()))
        self.assertTrue(entree.get("remplace"), entree)
        self.assertIsNone(entree.get("original"), entree)        # garder_original=False (4.6)
        self.assertFalse(os.path.isdir(os.path.join(self.depot, ".moodlesync-ocr", "originaux")))
        with open(resultat["sortie_pdf"], "rb") as f:
            self.assertIn(b"%PDF", f.read(8))

    def test_echec_ne_laisse_rien(self):
        self.confiance = 30.0                                     # document « Difficile » : echec (U4)
        depot = self.deposer([self.pdf("flou.pdf", [SCAN] * 2)])
        resultat = depot["resultats"][0]
        self.assertEqual(resultat["statut"], "echec")
        self.assertEqual(resultat["motif"], "difficile")
        self.assertEqual((resultat["sortie_pdf"], resultat["sortie_texte"]), ("", ""))
        self.assertEqual(visibles(self.depot), [])                # rien pour ce fichier, cache excepte
        self.assertEqual(ocr.charger_cache(self.depot)["documents"], {})
        self.assertEqual(ms.charger_etat(self.depot), {})

    def test_echec_apres_un_succes_ne_touche_pas_le_premier(self):
        self.deposer([self.pdf("scan.pdf", [SCAN])])
        self.confiance = 30.0
        depot = self.deposer([self.pdf("flou.pdf", [SCAN])])
        self.assertEqual(depot["resultats"][0]["statut"], "echec")
        self.assertTrue(os.path.isfile(os.path.join(self.depot, "scan.pdf")))
        self.assertTrue(os.path.isfile(os.path.join(self.depot, "scan.pdf.md")))

    def test_cache_du_mini_coffre(self):
        self.deposer([self.pdf("scan.pdf", [SCAN])])
        self.assertTrue(os.path.isfile(os.path.join(self.depot, ".moodlesync-ocr", "cache.json")))

    def test_format_txt(self):
        self.regler(ocr_format="txt")
        depot = self.deposer([self.pdf("scan.pdf", [SCAN])])
        self.assertEqual(depot["resultats"][0]["statut"], "ok")
        self.assertTrue(os.path.isfile(os.path.join(self.depot, "scan.pdf.txt")))

    def test_progression_avec_origine_depot(self):
        self.deposer([self.pdf("scan.pdf", [SCAN] * 2)])
        blocs = [T.charge_js(code) for code in self.fenetre.appels if code.startswith("window.textesProgres")]
        self.assertTrue(blocs)
        self.assertEqual({b["origine"] for b in blocs}, {"depot"})
        self.assertEqual(blocs[-1]["etat"], "termine")
        for bloc in blocs:
            self.assertEqual(set(bloc), {"etat", "origine", "document", "page", "pages", "documents_faits",
                                         "documents_total", "restant_min", "message"})


# ------------------------------------------------------------------ invariant 4
class Invariant4(Banc):
    """Invariant 4 de la refonte : un fichier depose n'est jamais touche a sa source."""

    def test_original_intact_apres_succes_echec_et_interruption(self):
        for cas in ("succes", "echec", "interruption"):
            with self.subTest(cas=cas):
                self.confiance = 91.0
                self.arret_apres = 0
                self.api._ocr_arret.clear()
                source = self.pdf("scan-%s.pdf" % cas, [SCAN] * 3)
                avant = identite(source)
                if cas == "echec":
                    self.confiance = 30.0
                if cas == "interruption":
                    self.arret_apres = 1
                depot = self.deposer([source])
                self.assertEqual(identite(source), avant,
                                 "le fichier d'origine a change (%s : %r)" % (cas, depot["resultats"]))
                with open(source, "rb") as f:
                    self.assertEqual(f.read(), T.pdf_minimal([SCAN] * 3))
                if cas == "interruption":
                    self.assertEqual(depot["resultats"], [])
                    self.assertEqual([n for n in visibles(self.depot) if n.startswith("scan-interruption")], [])

    def test_interruption_ne_laisse_rien(self):
        self.arret_apres = 1
        depot = self.deposer([self.pdf("scan.pdf", [SCAN] * 3)])
        self.assertEqual(depot["resultats"], [])
        self.assertEqual(depot["etat"], "termine")
        self.assertEqual(visibles(self.depot), [])
        self.assertEqual(ocr.charger_cache(self.depot)["documents"], {})
        self.assertEqual(ms.charger_etat(self.depot), {})


# ------------------------------------------------------------------ attribut cache (O12)
class AttributCache(Banc):
    """O12 : le cache du dossier de depot est marque cache sous Windows, `ctypes` double."""

    def test_sous_windows(self):
        faux = FauxCtypes()
        chemin = os.path.join("C:\\Users\\max\\Desktop", "Documents déposés", ".moodlesync-ocr")
        with mock.patch.object(os, "name", "nt"), mock.patch.dict(sys.modules, {"ctypes": faux}):
            self.assertTrue(api_depot.cacher_cache(chemin))
        self.assertEqual(faux.appels, [(("c_wchar_p", chemin), api_depot.ATTRIBUT_CACHE)])
        self.assertEqual(api_depot.ATTRIBUT_CACHE, 0x2)

    def test_echec_de_l_appel_ne_leve_pas(self):
        faux = FauxCtypes()
        faux.windll.kernel32.SetFileAttributesW.side_effect = OSError("refuse")
        with mock.patch.object(os, "name", "nt"), mock.patch.dict(sys.modules, {"ctypes": faux}):
            self.assertFalse(api_depot.cacher_cache("C:\\x"))

    def test_hors_windows(self):
        faux = FauxCtypes()
        with mock.patch.object(os, "name", "posix"), mock.patch.dict(sys.modules, {"ctypes": faux}):
            self.assertFalse(api_depot.cacher_cache("/x/.moodlesync-ocr"))
        self.assertEqual(faux.appels, [])

    def test_appele_au_depot(self):
        """Le depot confirme pose l'attribut sur le cache du dossier choisi, une fois le dossier cree."""
        with mock.patch.object(api_depot, "cacher_cache", mock.Mock(return_value=True)) as pose:
            self.deposer([self.pdf("scan.pdf", [SCAN])])
        self.assertEqual(pose.call_count, 1)
        self.assertEqual(pose.call_args[0][0], os.path.join(os.path.abspath(self.depot), ".moodlesync-ocr"))


# ------------------------------------------------------------------ glisser-deposer (O16)
class GlisserDeposer(Banc):
    """O16 : le gestionnaire DOM de depot remonte les chemins complets de pywebview, et rien d'autre."""

    def installer(self, elements=None):
        dom = FauxDom(elements if elements is not None else {"#tx-v-deposer": FauxElement()})
        self.fenetre.dom = dom
        return dom, self.api._depot_installer(essais=1, attente=0)

    @staticmethod
    def par_nom(element):
        """{nom de l'evenement: gestionnaire pose}, les doublons de nom gardant le dernier."""
        return dict(element.ecouteurs)

    def test_gestionnaire_pose_sur_la_vue_deposer(self):
        dom, pose = self.installer()
        self.assertTrue(pose)
        self.assertTrue(self.api._depot_dom)
        self.assertEqual(dom.demandes[0], "#tx-v-deposer")
        self.assertEqual([e for e, _ in dom.elements["#tx-v-deposer"].ecouteurs], ["dragover", "drop"])

    def test_dragover_et_drop_annulent_le_defaut(self):
        """E-V4-3 : un `drop` n'arrive que si `dragover` est annule (modele documente de pywebview)."""
        from webview.dom import DOMEventHandler
        dom, _ = self.installer()
        poses = self.par_nom(dom.elements["#tx-v-deposer"])
        for evenement in ("dragover", "drop"):
            with self.subTest(evenement=evenement):
                self.assertIn(evenement, poses)
                self.assertIsInstance(poses[evenement], DOMEventHandler,
                                      "l'ecouteur doit etre un DOMEventHandler : un appelable simple n'annule rien")
                self.assertTrue(poses[evenement].prevent_default, "sans preventDefault, pas de drop")
        self.assertEqual(poses["drop"].callback, self.api._depot_depose,
                         "le gestionnaire de depot reste celui qui lit les chemins")

    def test_un_depot_hors_de_la_zone_n_ouvre_pas_le_pdf(self):
        """E-V4-3 : garde sur `body`, lacher a cote de la zone n'ouvre pas le PDF dans la fenetre."""
        from webview.dom import DOMEventHandler
        corps = FauxElement()
        dom, pose = self.installer({"#tx-v-deposer": FauxElement(), "body": corps})
        self.assertTrue(pose)
        poses = self.par_nom(corps)
        for evenement in ("dragover", "drop"):
            with self.subTest(evenement=evenement):
                self.assertIn(evenement, poses)
                self.assertIsInstance(poses[evenement], DOMEventHandler)
                self.assertTrue(poses[evenement].prevent_default)
        evenement = {"type": "drop", "dataTransfer": {"files": [
            {"name": "scan.pdf", "pywebviewFullPath": os.path.join(self.d, "scan.pdf")}]}}
        self.assertIsNone(poses["drop"].callback(evenement), "la garde ne depose rien")
        self.assertEqual([c for c in self.fenetre.appels if c.startswith("window.textesDepotChemins")], [])

    def test_repli_sur_le_corps(self):
        corps = FauxElement()
        dom, pose = self.installer({"body": corps})
        self.assertTrue(pose)
        self.assertEqual(dom.demandes, ["#tx-v-deposer", "body"])
        self.assertEqual([e for e, _ in corps.ecouteurs], ["dragover", "drop"])

    def test_sans_element_rend_faux(self):
        _, pose = self.installer({})
        self.assertFalse(pose)
        self.assertFalse(self.api._depot_dom)

    def test_sans_fenetre_rend_faux(self):
        self.api._fenetre = None
        self.assertFalse(self.api._depot_installer(essais=1, attente=0))

    def test_evenement_de_depot(self):
        dom, _ = self.installer()
        gerer = self.par_nom(dom.elements["#tx-v-deposer"])["drop"].callback
        evenement = {"type": "drop", "dataTransfer": {"files": [
            {"name": "scan.pdf", "pywebviewFullPath": os.path.join(self.d, "scan.pdf")},
            {"name": "notes.docx", "pywebviewFullPath": os.path.join(self.d, "notes.docx")}]}}
        self.assertEqual(gerer(evenement), [os.path.join(self.d, "scan.pdf"), os.path.join(self.d, "notes.docx")])
        appels = [T.charge_js(code) for code in self.fenetre.appels if code.startswith("window.textesDepotChemins")]
        self.assertEqual(appels, [[os.path.join(self.d, "scan.pdf"), os.path.join(self.d, "notes.docx")]])

    def test_chemin_absent_n_est_pas_invente(self):
        dom, _ = self.installer()
        gerer = self.par_nom(dom.elements["#tx-v-deposer"])["drop"].callback
        self.assertEqual(gerer({"type": "drop", "dataTransfer": {"files": [{"name": "scan.pdf"}]}}), [])
        self.assertEqual(gerer({"type": "drop"}), [])
        self.assertEqual(gerer(None), [])
        self.assertEqual([c for c in self.fenetre.appels if c.startswith("window.textesDepotChemins")], [])

    def test_chemins_deposes(self):
        self.assertEqual(api_depot.chemins_deposes(
            {"dataTransfer": {"files": [{"pywebviewFullPath": "/a/b.pdf"}, {"pywebviewFullPath": "/a/b.pdf"},
                                        {"pywebviewFullPath": "relatif.pdf"}, {"name": "sans.pdf"}]}}), ["/a/b.pdf"])
        self.assertEqual(api_depot.chemins_deposes({}), [])


if __name__ == "__main__":
    unittest.main()
