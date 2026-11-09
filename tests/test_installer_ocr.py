"""I1 : installation du moteur a la demande (ocr.installer_paquet et ApiTextes.ocr_installer).

Aucun test ne touche le reseau. Le seul point d'entree reseau de installer_paquet est maj.ouvrir (import a l'usage) :
la doublure ci-dessous ne repond qu'aux deux adresses prevues, note tout autre appel, et urllib.request.urlopen et
socket.create_connection sont remplaces par des doublures qui notent aussi leurs appels. Chaque test verifie en fin
de course que la liste des appels imprevus est vide : une exception levee par une doublure serait sinon avalee par
la fonction, qui ne laisse sortir aucune trace technique (invariant 9).
"""
import hashlib, io, json, os, socket, sys, tempfile, unittest, urllib.error, urllib.request, zipfile
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import maj, moteur as ms, ocr
from tests import test_api_textes as ta

URL_API = "https://api.github.com/repos/MarinWasAsleep/MoodleSync-moteur/releases/latest"
NOM_PAQUET = "MoodleSync-moteur.zip"                           # nom du fichier de la release, fige ici et dans ocr.NOM_PAQUET
URL_FICHIER = "https://github.com/MarinWasAsleep/MoodleSync-moteur/releases/download/v1/" + NOM_PAQUET
EXE = "tesseract.exe" if os.name == "nt" else "tesseract"


def fabriquer_zip(membres, symboles=()):
    """Archive en memoire. `membres` : {nom: octets}. `symboles` : noms d'entrees qui sont des liens symboliques."""
    sortie = io.BytesIO()
    with zipfile.ZipFile(sortie, "w", zipfile.ZIP_STORED) as z:
        for nom, contenu in membres.items():
            z.writestr(nom, contenu)
        for nom in symboles:
            info = zipfile.ZipInfo(nom)
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            z.writestr(info, "../../etc/passwd")
    return sortie.getvalue()


def paquet_valide():
    """Un moteur factice (exe, une donnee de langue) plus de quoi faire plusieurs blocs de telechargement."""
    return fabriquer_zip({EXE: b"MOTEUR", "tessdata/fra.traineddata": b"fra", "tessdata/eng.traineddata": b"eng",
                          "lourd.bin": os.urandom(1_200_000)})


class Reponse(io.BytesIO):
    def __init__(self, octets, panne_apres=None):
        super().__init__(octets)
        self.panne_apres = panne_apres
        self.lus = 0

    def read(self, n=-1):
        if self.panne_apres is not None and self.lus >= self.panne_apres:
            raise ConnectionResetError("connexion coupee")
        bloc = super().read(n)
        self.lus += len(bloc)
        return bloc


class Reseau(unittest.TestCase):
    """Dossier des reglages temporaire, reseau double, detecter double, constante d'empreinte posee."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = self.tmp.name
        self.app = os.path.join(self.d, "app")                  # ms.APP_DIR : un cran sous self.d, pour voir ce qui s'echappe
        os.makedirs(self.app)
        self.cible = os.path.join(self.app, "tesseract")
        self.archive = paquet_valide()
        self.appels = []                                          # adresses demandees a maj.ouvrir
        self.imprevus = []                                        # tout appel reseau non prevu
        self.release = self.fabriquer_release(self.archive)
        self.reponse_api = None                                   # une exception ou un objet pour remplacer l'API
        self.reponse_fichier = None
        self.detections = []
        self.empreinte_livree = ocr.EMPREINTE_PAQUET
        self.sauve = {n: getattr(ms, n) for n in ("APP_DIR", "CONFIG", "ERREURS")}
        self.addCleanup(lambda: [setattr(ms, n, v) for n, v in self.sauve.items()])
        ms.APP_DIR, ms.CONFIG, ms.ERREURS = self.app, os.path.join(self.app, "config.json"), os.path.join(self.d, "erreurs.txt")
        for cible, nom, valeur in ((maj, "ouvrir", self.ouvrir), (urllib.request, "urlopen", self.urlopen_imprevu),
                                   (socket, "create_connection", self.connexion_imprevue),
                                   (ocr, "detecter", self.detecter), (ocr, "EMPREINTE_PAQUET", self.empreinte(self.archive))):
            p = mock.patch.object(cible, nom, valeur)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.assertEqual(self.imprevus, [], "appel reseau non prevu")

    # -- doublures
    @staticmethod
    def empreinte(octets):
        return hashlib.sha256(octets).hexdigest()

    @staticmethod
    def fabriquer_release(octets, digest=None):
        return {"tag_name": "v1", "draft": False, "prerelease": False, "assets": [
            {"name": NOM_PAQUET, "size": len(octets), "browser_download_url": URL_FICHIER,
             **({"digest": digest} if digest else {})}]}

    def ouvrir(self, url, timeout=30):
        self.appels.append(url)
        if url == URL_API:
            if self.reponse_api is not None:
                if isinstance(self.reponse_api, BaseException):
                    raise self.reponse_api
                return self.reponse_api
            return Reponse(json.dumps(self.release).encode("utf-8"))
        if url == URL_FICHIER:
            if isinstance(self.reponse_fichier, BaseException):
                raise self.reponse_fichier
            return self.reponse_fichier or Reponse(self.archive)
        self.imprevus.append(url)
        raise AssertionError(f"adresse non prevue : {url}")

    def urlopen_imprevu(self, *a, **k):
        self.imprevus.append(("urlopen", a))
        raise AssertionError("urlopen appele")

    def connexion_imprevue(self, *a, **k):
        self.imprevus.append(("create_connection", a))
        raise AssertionError("connexion ouverte")

    def detecter(self, cfg):
        """Moteur present si l'exe du paquet existe au moment de la detection."""
        self.detections.append(os.path.isfile(os.path.join(self.cible, EXE)))
        if self.detections[-1]:
            return dict(ta.BLOC_MOTEUR, source="portable", exe=os.path.join(self.cible, EXE))
        return dict(ocr.BLOC_ABSENT)

    def traces(self):
        """Tout ce qui traine dans le dossier des reglages (hors fichier d'erreurs) et au-dessus."""
        return sorted(os.listdir(self.app)), sorted(n for n in os.listdir(self.d) if n not in ("app", "erreurs.txt"))


class Installation(Reseau):
    def test_installation_reussie(self):
        vus = []
        r = ocr.installer_paquet(progres=lambda recu, total: vus.append((recu, total)))
        self.assertEqual(r, {"ok": True, "version": "5.5.3"})
        for parties, attendu in (((EXE,), b"MOTEUR"), (("tessdata", "fra.traineddata"), b"fra")):
            with open(os.path.join(self.cible, *parties), "rb") as f:
                self.assertEqual(f.read(), attendu)
        self.assertEqual(self.detections, [True], "detecter rappele une fois, apres l'installation")
        self.assertEqual(self.appels, [URL_API, URL_FICHIER])
        self.assertEqual(self.traces(), (["tesseract"], []), "aucun fichier ni dossier temporaire ne reste")
        self.assertTrue(vus and vus[0][1] == len(self.archive))

    def test_aucune_empreinte_lue_chez_le_serveur(self):
        """L'empreinte est dans le code (decision 4) : un `digest` du serveur ne change rien, dans les deux sens."""
        self.release = self.fabriquer_release(self.archive, digest="sha256:" + "0" * 64)
        self.assertEqual(ocr.installer_paquet(), {"ok": True, "version": "5.5.3"})
        falsifie = self.archive + b"x"
        self.release = self.fabriquer_release(falsifie, digest="sha256:" + self.empreinte(falsifie))
        self.reponse_fichier = Reponse(falsifie)
        self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})

    def test_remplace_une_installation_precedente(self):
        os.makedirs(self.cible)
        with open(os.path.join(self.cible, "ancien.txt"), "w") as f:
            f.write("ancien")
        self.assertEqual(ocr.installer_paquet(), {"ok": True, "version": "5.5.3"})
        self.assertEqual(sorted(os.listdir(self.cible)), sorted([EXE, "lourd.bin", "tessdata"]))
        self.assertEqual(self.traces(), (["tesseract"], []))

    def test_progres_au_plus_quatre_fois_par_seconde(self):
        horloge = [0.0]

        def avance():
            horloge[0] += 0.1
            return horloge[0]
        instants = []
        with mock.patch.object(ocr, "_horloge", avance):
            ocr.installer_paquet(progres=lambda recu, total: instants.append(horloge[0]))
        self.assertGreaterEqual(len(instants), 2)
        for avant, apres in zip(instants, instants[1:]):
            self.assertGreaterEqual(apres - avant, 0.25 - 1e-9)

    def test_detection_qui_echoue_ne_laisse_rien(self):
        """Le paquet se decompresse mais le moteur n'est pas detecte : l'installation est retiree, phrase claire."""
        with mock.patch.object(ocr, "detecter", lambda cfg: dict(ocr.BLOC_ABSENT)):
            r = ocr.installer_paquet()
        self.assertEqual(r, {"erreur": ocr.MESSAGES["installation_echec"]})
        self.assertEqual(self.traces(), ([], []))


class EmpreinteEtPublication(Reseau):
    def test_empreinte_fausse(self):
        """Le fichier est supprime, rien n'est decompresse, la phrase vient de MESSAGES."""
        with mock.patch.object(ocr, "EMPREINTE_PAQUET", self.empreinte(b"autre chose")), \
                mock.patch.object(zipfile, "ZipFile", side_effect=AssertionError("archive ouverte")):
            r = ocr.installer_paquet()
        self.assertEqual(r, {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []), "ni fichier telecharge, ni dossier")
        self.assertEqual(self.detections, [])

    def test_paquet_pas_encore_publie(self):
        """Constante vide (livraison actuelle) : phrase claire, ni reseau ni decompression."""
        for vide in ("", None):
            with self.subTest(constante=vide), mock.patch.object(ocr, "EMPREINTE_PAQUET", vide):
                self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["installation_indisponible"]})
        self.assertEqual(self.appels, [])
        self.assertEqual(self.traces(), ([], []))

    def test_constante_livree(self):
        """Valeur livree par le module (avant la doublure) : vide tant que Maxence n'a pas publie le paquet, sinon
        une empreinte SHA-256 de 64 chiffres hexadecimaux."""
        self.assertRegex(self.empreinte_livree, r"^([0-9a-f]{64})?$")
        self.assertEqual(ocr.DEPOT_MOTEUR, "MarinWasAsleep/MoodleSync-moteur")
        self.assertEqual(ocr.NOM_PAQUET, NOM_PAQUET)
        self.assertEqual(ocr.NOM_EXE_PAQUET, EXE)

    def test_release_sans_le_fichier(self):
        self.release = {"tag_name": "v1", "assets": []}
        self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["installation_indisponible"]})
        self.assertEqual(self.appels, [URL_API])

    def test_fichier_hors_github_refuse(self):
        self.release["assets"][0]["browser_download_url"] = "https://exemple.org/moteur.zip"
        self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.appels, [URL_API], "le fichier hors GitHub n'est jamais demande")

    def test_fichier_trop_gros_refuse(self):
        with mock.patch.object(ocr, "TAILLE_MAX_PAQUET", 1000):
            self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []))


class Arret(Reseau):
    def test_arret_en_cours_de_telechargement(self):
        appels = []

        def arreter():
            appels.append(1)
            return len(appels) >= 2
        self.reponse_fichier = Reponse(self.archive)
        with mock.patch.object(zipfile, "ZipFile", side_effect=AssertionError("archive ouverte")):
            r = ocr.installer_paquet(arreter=arreter)
        self.assertEqual(r, {"annule": True})
        self.assertLess(self.reponse_fichier.lus, len(self.archive), "le telechargement s'arrete en route")
        self.assertEqual(self.traces(), ([], []), "aucun dossier ni fichier laisse")
        self.assertEqual(self.detections, [])

    def test_arret_pendant_la_decompression(self):
        def arreter():
            """Vrai des qu'un premier fichier est ecrit dans le dossier temporaire de decompression."""
            return any(os.listdir(os.path.join(self.app, n)) for n in os.listdir(self.app)
                       if n.startswith(".tesseract-") and os.path.isdir(os.path.join(self.app, n)))
        r = ocr.installer_paquet(arreter=arreter)
        self.assertEqual(r, {"annule": True})
        self.assertEqual(self.traces(), ([], []))
        self.assertEqual(self.detections, [])

    def test_arret_avant_le_debut(self):
        self.assertEqual(ocr.installer_paquet(arreter=lambda: True), {"annule": True})
        self.assertEqual(self.traces(), ([], []))


class ReseauIndisponible(Reseau):
    def verifier(self, r):
        self.assertEqual(r, {"erreur": ocr.MESSAGES["paquet_hors_ligne"]})
        for interdit in ("Traceback", "URLError", "Errno", "getaddrinfo", "ConnectionReset", ".py"):
            self.assertNotIn(interdit, r["erreur"])
        self.assertEqual(self.traces(), ([], []))

    def test_serveur_injoignable(self):
        self.reponse_api = urllib.error.URLError("[Errno -2] Name or service not known")
        self.verifier(ocr.installer_paquet())

    def test_limite_de_requetes_ou_erreur_http(self):
        self.reponse_api = urllib.error.HTTPError(URL_API, 403, "rate limit", {}, None)
        self.verifier(ocr.installer_paquet())

    def test_delai_depasse(self):
        self.reponse_api = TimeoutError("timed out")
        self.verifier(ocr.installer_paquet())

    def test_connexion_coupee_pendant_le_telechargement(self):
        self.reponse_fichier = Reponse(self.archive, panne_apres=300_000)
        self.verifier(ocr.installer_paquet())

    def test_telechargement_refuse(self):
        self.reponse_fichier = urllib.error.URLError("refuse")
        self.verifier(ocr.installer_paquet())

    def test_reponse_de_l_api_illisible(self):
        self.reponse_api = Reponse(b"<html>pas du json</html>")
        r = ocr.installer_paquet()
        self.assertEqual(r, {"erreur": ocr.MESSAGES["installation_echec"]})
        self.assertEqual(self.traces(), ([], []))


class CheminsDeLArchive(Reseau):
    def poser(self, membres, symboles=()):
        self.archive = fabriquer_zip(membres, symboles)
        self.release = self.fabriquer_release(self.archive)
        p = mock.patch.object(ocr, "EMPREINTE_PAQUET", self.empreinte(self.archive))
        p.start()
        self.addCleanup(p.stop)

    def test_chemins_sortants_refuses_sans_rien_ecrire(self):
        cas = {"remonte": "../evil.txt", "profond": "tessdata/../../evil.txt", "absolu": "/evil.txt",
               "lecteur": "C:/evil.txt", "antislash": "..\\evil.txt", "antislash_absolu": "\\evil.txt",
               "flux": "a:evil.txt"}
        for nom, chemin in cas.items():
            with self.subTest(cas=nom):
                self.poser({EXE: b"MOTEUR", chemin: b"mal"})
                r = ocr.installer_paquet()
                self.assertEqual(r, {"erreur": ocr.MESSAGES["paquet_invalide"]})
                self.assertEqual(self.traces(), ([], []), "rien d'ecrit, ni dans la cible ni au-dessus")
                self.assertFalse(os.path.exists(os.path.join(self.d, "evil.txt")))

    def test_le_premier_membre_sain_n_est_pas_ecrit_si_un_autre_sort(self):
        """Tout est verifie avant la premiere ecriture."""
        self.poser({EXE: b"MOTEUR", "a.txt": b"a", "../evil.txt": b"mal"})
        self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []))

    def test_lien_symbolique_refuse(self):
        self.poser({EXE: b"MOTEUR"}, symboles=("lien",))
        self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []))

    def test_validation_d_un_nom(self):
        """Le validateur lui-meme, y compris les noms qu'une archive de test ne peut pas porter (octet nul)."""
        for mauvais in ("../a", "a/../../b", "/a", "\\a", "C:/a", "c:a", "a:b", "a\x00b", "", "..", "a/..", "./..",
                        "..\\a", "a\\..\\..\\b", "//serveur/partage"):
            with self.subTest(nom=mauvais):
                self.assertIsNone(ocr._parties_sures(mauvais))
        self.assertEqual(ocr._parties_sures("tessdata/fra.traineddata"), ["tessdata", "fra.traineddata"])
        self.assertEqual(ocr._parties_sures("tessdata\\fra.traineddata"), ["tessdata", "fra.traineddata"])
        self.assertEqual(ocr._parties_sures("./a//b/"), ["a", "b"])

    def test_archive_sans_le_moteur(self):
        self.poser({"lisezmoi.txt": b"rien"})
        self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []))

    def test_pas_une_archive(self):
        self.archive = b"ceci n'est pas un zip"
        self.release = self.fabriquer_release(self.archive)
        with mock.patch.object(ocr, "EMPREINTE_PAQUET", self.empreinte(self.archive)):
            self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []))

    def test_archive_trop_grosse_une_fois_decompressee(self):
        with mock.patch.object(ocr, "TAILLE_MAX_DECOMPRESSE", 1000):
            self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []))

    def test_sous_dossiers_et_noms_a_accents(self):
        self.poser({EXE: b"MOTEUR", "tessdata/configs/été.txt": b"x", "tessdata/": b""})
        self.assertEqual(ocr.installer_paquet(), {"ok": True, "version": "5.5.3"})
        self.assertTrue(os.path.isfile(os.path.join(self.cible, "tessdata", "configs", "été.txt")))


class InstallationInterrompue(Reseau):
    def test_echec_au_deplacement_final(self):
        """Un renommage qui echoue : pas de dossier a moitie ecrit, l'ancienne installation reste."""
        os.makedirs(self.cible)
        with open(os.path.join(self.cible, "ancien.txt"), "w") as f:
            f.write("ancien")
        vrai = os.rename

        def rename(src, dst, *a, **k):
            nom = os.path.basename(src)
            if nom.startswith(".tesseract-") and not nom.startswith(".tesseract-ancien-"):   # le dossier qu'on pose
                raise OSError(28, "No space left on device")
            return vrai(src, dst, *a, **k)
        with mock.patch("os.rename", rename):
            r = ocr.installer_paquet()
        self.assertEqual(r, {"erreur": ocr.MESSAGES["installation_echec"]})
        self.assertEqual(self.traces(), (["tesseract"], []))
        self.assertEqual(os.listdir(self.cible), ["ancien.txt"], "l'ancienne installation est remise en place")
        self.assertNotIn("Errno", r["erreur"])

    def test_echec_pendant_l_ecriture(self):
        """Disque plein au milieu de la decompression : aucun dossier ni fichier laisse."""
        vrai = ocr.shutil.copyfileobj
        n = []

        def copie(src, dst, *a, **k):
            n.append(1)
            if len(n) == 2:
                raise OSError(28, "No space left on device")
            return vrai(src, dst, *a, **k)
        with mock.patch.object(ocr.shutil, "copyfileobj", copie):
            r = ocr.installer_paquet()
        self.assertEqual(r, {"erreur": ocr.MESSAGES["installation_echec"]})
        self.assertEqual(self.traces(), ([], []))

    def test_une_seule_installation_a_la_fois(self):
        with ocr._VERROU_PAQUET:
            self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["occupe"]})
        self.assertEqual(self.appels, [])
        self.assertEqual(ocr.installer_paquet(), {"ok": True, "version": "5.5.3"}, "verrou relache apres usage")
        self.assertFalse(ocr._VERROU_PAQUET.locked())

    def test_restes_d_une_installation_tuee_nettoyes(self):
        """La fermeture de l'application en plein telechargement laisse un .part et un dossier : le prochain essai les retire."""
        for nom in (".paquet-abc.part", ".tesseract-xyz", ".tesseract-ancien-q"):
            chemin = os.path.join(self.app, nom)
            os.makedirs(chemin) if "tesseract" in nom else open(chemin, "wb").close()
        self.reponse_api = urllib.error.URLError("hors ligne")
        ocr.installer_paquet()
        self.assertEqual(self.traces(), ([], []))

    def test_le_verrou_est_relache_apres_une_erreur(self):
        self.reponse_api = urllib.error.URLError("x")
        ocr.installer_paquet()
        self.assertFalse(ocr._VERROU_PAQUET.locked())


class DoubluresDuReseau(Reseau):
    """La preuve que les doublures refusent ce qui n'est pas prevu."""

    def test_adresse_imprevue(self):
        with self.assertRaises(AssertionError):
            maj.ouvrir("https://exemple.org/autre")
        self.assertEqual(len(self.imprevus), 1)
        self.imprevus.clear()

    def test_urlopen_et_connexion_refuses(self):
        with self.assertRaises(AssertionError):
            urllib.request.urlopen("https://github.com/")
        with self.assertRaises(AssertionError):
            socket.create_connection(("github.com", 443))
        self.assertEqual(len(self.imprevus), 2)
        self.imprevus.clear()

    def test_une_adresse_imprevue_fait_echouer_le_test(self):
        """installer_paquet avale l'exception (aucune trace technique) : seul le releve des appels la fait voir."""
        self.release["assets"][0]["browser_download_url"] = "https://github.com/autre/depot/releases/download/x/y.zip"
        r = ocr.installer_paquet()
        self.assertIn("erreur", r)
        self.assertEqual(len(self.imprevus), 1)
        self.imprevus.clear()

    def test_les_deux_adresses_sont_celles_du_depot_du_moteur(self):
        ocr.installer_paquet()
        self.assertEqual(self.appels, [URL_API, URL_FICHIER])


class DetectionDuPaquet(unittest.TestCase):
    """detecter retrouve le paquet portable (source `portable`), apres les autres chemins."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sauve = ms.APP_DIR
        ms.APP_DIR = os.path.join(self.tmp.name, "MoodleSync")
        self.addCleanup(setattr, ms, "APP_DIR", self.sauve)
        for nom, valeur in (("_exe_registre", lambda: None), ("_exe_usuel", lambda: None)):
            p = mock.patch.object(ocr, nom, valeur)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(ocr.shutil, "which", lambda n: None)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"TESSDATA_PREFIX": ""})
        p.start()
        self.addCleanup(p.stop)

    def executer(self, args, *, delai, arreter=None):
        if "--version" in args:
            return 0, b"tesseract 5.5.3\n", b""
        return 0, b"List of available languages (2):\neng\nfra\n", b""

    def test_absent_sans_paquet(self):
        with mock.patch.object(ocr, "executer", self.executer):
            self.assertFalse(ocr.detecter({})["present"])

    def test_present_avec_paquet(self):
        dossier = os.path.join(ms.APP_DIR, "tesseract")
        os.makedirs(os.path.join(dossier, "tessdata"))
        with open(os.path.join(dossier, EXE), "wb") as f:
            f.write(b"x")
        with mock.patch.object(ocr, "executer", self.executer):
            bloc = ocr.detecter({})
        self.assertTrue(bloc["present"])
        self.assertEqual((bloc["source"], bloc["version"]), ("portable", "5.5.3"))
        self.assertEqual(bloc["exe"], os.path.join(dossier, EXE))
        self.assertEqual(bloc["tessdata"], os.path.join(dossier, "tessdata"))

    def test_le_choix_manuel_passe_avant_le_paquet(self):
        dossier = os.path.join(ms.APP_DIR, "tesseract")
        os.makedirs(dossier)
        with open(os.path.join(dossier, EXE), "wb") as f:
            f.write(b"x")
        manuel = os.path.join(self.tmp.name, "mien")
        with open(manuel, "wb") as f:
            f.write(b"x")
        with mock.patch.object(ocr, "executer", self.executer):
            bloc = ocr.detecter({"ocr_exe": manuel})
        self.assertEqual((bloc["source"], bloc["exe"]), ("config", manuel))


class Api(ta.Base):
    """ocr_installer : `ocr_etat()` apres une installation, l'etat sans requete si le moteur est la, phrases au journal."""

    def setUp(self):
        super().setUp()
        self.appels_reseau = []
        self.imprevus = []
        for cible, nom, valeur in ((maj, "ouvrir", self.ouvrir_imprevu), (urllib.request, "urlopen", self.ouvrir_imprevu),
                                   (socket, "create_connection", self.ouvrir_imprevu)):
            p = mock.patch.object(cible, nom, valeur)
            p.start()
            self.addCleanup(p.stop)
        self.bloc = dict(ocr.BLOC_ABSENT)                         # Base.detecter lit self.bloc

    def tearDown(self):
        self.assertEqual(self.imprevus, [], "appel reseau non prevu")

    def ouvrir_imprevu(self, *a, **k):
        self.imprevus.append(a)
        raise AssertionError("reseau")

    def journal(self):
        return [c for c in self.fenetre.appels if "textesJournal" in c]

    def phrases_du_journal(self):
        return [json.loads(c[c.index("(") + 1:c.rindex(")")]) for c in self.journal()]

    def installateur(self, retour):
        """Doublure de installer_paquet : change le moteur detecte quand l'installation reussit."""
        appels = []

        def faux(progres=None, arreter=None):
            appels.append((progres, arreter))
            if retour.get("ok"):
                self.bloc = dict(ta.BLOC_MOTEUR, source="portable", version=retour["version"])
            return dict(retour)
        p = mock.patch.object(ocr, "installer_paquet", faux)
        p.start()
        self.addCleanup(p.stop)
        return appels

    def test_installation_reussie_rend_l_etat_complet(self):
        appels = self.installateur({"ok": True, "version": "5.5.3"})
        r = self.api.ocr_installer()
        self.assertEqual(len(appels), 1)
        self.assertIn("moteur", r, "les deux pages ne se rafraichissent que sur une reponse qui porte `moteur`")
        self.assertTrue(r["moteur"]["present"])
        self.assertEqual(r["moteur"]["version"], "5.5.3")
        self.assertEqual(set(r), set(self.api.ocr_etat()))
        self.assertEqual(r, self.api.ocr_etat(), "meme forme 2.7 que ocr_etat, memo de detection rafraichi")
        self.assertNotIn("erreur", r)
        self.assertEqual(self.phrases_du_journal(), [ocr.MESSAGES["installation_faite"]])

    def test_moteur_deja_present_ne_telecharge_rien(self):
        self.bloc = dict(ta.BLOC_MOTEUR)
        with mock.patch.object(ocr, "installer_paquet", side_effect=AssertionError("installation lancee")):
            r = self.api.ocr_installer()
        self.assertEqual(r, self.api.ocr_etat())
        self.assertTrue(r["moteur"]["present"])
        self.assertEqual(self.journal(), [])

    def test_moteur_present_apres_un_memo_perime(self):
        """Le moteur vient d'etre installe a la main : la detection est refaite, pas lue dans la memoire de 60 s."""
        self.api.ocr_etat()                                       # memo : absent
        self.bloc = dict(ta.BLOC_MOTEUR)
        with mock.patch.object(ocr, "installer_paquet", side_effect=AssertionError("installation lancee")):
            self.assertTrue(self.api.ocr_installer()["moteur"]["present"])

    def test_erreur_relayee_telle_quelle_et_ecrite_au_journal(self):
        for code in ("paquet_hors_ligne", "paquet_invalide", "installation_echec", "installation_indisponible"):
            with self.subTest(code=code):
                self.fenetre.appels.clear()
                self.installateur({"erreur": ocr.MESSAGES[code]})
                self.assertEqual(self.api.ocr_installer(), {"erreur": ocr.MESSAGES[code]})
                self.assertEqual(self.phrases_du_journal(), [ocr.MESSAGES[code]])

    def test_annulation_relayee_sans_journal(self):
        self.installateur({"annule": True})
        self.assertEqual(self.api.ocr_installer(), {"annule": True})
        self.assertEqual(self.journal(), [])

    def test_exception_inattendue_sans_trace(self):
        with mock.patch.object(ocr, "installer_paquet", side_effect=RuntimeError("boum interne")):
            r = self.api.ocr_installer()
        self.assertEqual(list(r), ["erreur"])
        for interdit in ("boum", "Traceback", ".py"):
            self.assertNotIn(interdit, r["erreur"])

    def test_sans_consentement_l_installation_se_fait_et_ne_donne_pas_le_consentement(self):
        """Contrat 3.2 : installer n'est pas extraire. Le clic sur « Installer » est l'accord explicite de D6 ;
        `ocr` reste faux, aucune extraction ne part, la file n'est pas touchee."""
        self.assertFalse(self.config().get("ocr"))
        self.installateur({"ok": True, "version": "5.5.3"})
        avant = self.instantane()
        r = self.api.ocr_installer()
        self.assertTrue(r["moteur"]["present"])
        self.assertFalse(r["active"])
        self.assertFalse(self.config().get("ocr"), "le consentement n'est pas ecrit par l'installation")
        self.assertFalse(r["occupe"])
        self.assertEqual(self.pages_vues, [])
        self.assertEqual(self.instantane(), avant, "le dossier de rangement n'est pas touche")
        self.assertEqual(self.api.ocr_lancer()["erreur"], ocr.MESSAGES["consentement_absent"])

    def test_etat_livre_sans_paquet_publie(self):
        """Sans doublure de installer_paquet : la constante livree est vide, la phrase le dit et rien n'est demande."""
        with mock.patch.object(ocr, "EMPREINTE_PAQUET", ""):
            r = self.api.ocr_installer()
        self.assertEqual(r, {"erreur": ocr.MESSAGES["installation_indisponible"]})
        self.assertEqual(self.phrases_du_journal(), [ocr.MESSAGES["installation_indisponible"]])

    def test_de_bout_en_bout_avec_le_reseau_double(self):
        """Vraie installer_paquet, reseau double : ocr_installer rend l'etat, le dossier existe, un seul telechargement."""
        archive = paquet_valide()
        vus = []

        def ouvrir(url, timeout=30):
            vus.append(url)
            if url == URL_API:
                return Reponse(json.dumps(Reseau.fabriquer_release(archive)).encode("utf-8"))
            if url == URL_FICHIER:
                return Reponse(archive)
            self.imprevus.append(url)
            raise AssertionError(url)

        def detecter(cfg):
            ok = os.path.isfile(os.path.join(self.d, "tesseract", EXE))
            return dict(ta.BLOC_MOTEUR, source="portable") if ok else dict(ocr.BLOC_ABSENT)
        with mock.patch.object(maj, "ouvrir", ouvrir), mock.patch.object(ocr, "detecter", detecter), \
                mock.patch.object(ocr, "EMPREINTE_PAQUET", hashlib.sha256(archive).hexdigest()):
            r = self.api.ocr_installer()
        self.assertEqual(vus, [URL_API, URL_FICHIER])
        self.assertTrue(r["moteur"]["present"])
        self.assertEqual(r["moteur"]["source"], "portable")
        self.assertTrue(os.path.isfile(os.path.join(self.d, "tesseract", EXE)), "dans le dossier des reglages")
        self.assertFalse(os.path.exists(os.path.join(self.dest, "tesseract")), "jamais dans le dossier de cours")


if __name__ == "__main__":
    unittest.main()
