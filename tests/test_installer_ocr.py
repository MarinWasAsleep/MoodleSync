"""I1 : installation du moteur a la demande (ocr.installer_paquet et ApiTextes.ocr_installer).

Aucun test ne touche le reseau. Le seul point d'entree reseau de installer_paquet est maj.ouvrir (import a l'usage) :
la doublure ci-dessous ne repond qu'aux deux adresses prevues, note tout autre appel, et urllib.request.urlopen et
socket.create_connection sont remplaces par des doublures qui notent aussi leurs appels. Chaque test verifie en fin
de course que la liste des appels imprevus est vide : une exception levee par une doublure serait sinon avalee par
la fonction, qui ne laisse sortir aucune trace technique (invariant 9).
"""
import hashlib, io, json, os, shutil, socket, sys, tempfile, unittest, urllib.error, urllib.request, zipfile
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import maj, moteur as ms, ocr
from tests import test_api_textes as ta

DETECTER_CHEMIN_REEL = ocr._detecter_chemin             # les doublures des classes ci-dessous le remplacent

URL_BASE = "https://github.com/MarinWasAsleep/MoodleSync-moteur/releases/download/v1.0.0/"
# Ce que la release v1.0.0 publie (decision du 10 novembre 2026), fige ici et dans ocr : un nom, une empreinte SHA-256
# et le nom du moteur a la racine de l'archive, par systeme. Les empreintes sont celles mesurees sur les archives.
PAQUETS_ATTENDUS = {
    "win32": ("MoodleSync-moteur-windows.zip", "ba86c780c2c5aacbe66dd4c40ca0093ef1f80426df2cb9b226a1faf3c1a1f51d",
              "tesseract.exe"),
    "darwin": ("MoodleSync-moteur-macos.zip", "a7d6198ef730cfd6a93e2b3eb63d71f13bec1bfe60034be32ca93d23d9e72a96",
               "tesseract"),
}
PLATEFORME = "win32" if os.name == "nt" else "darwin"           # le systeme de cette machine, pour les tests courants
NOM_PAQUET = PAQUETS_ATTENDUS[PLATEFORME][0]
URL_FICHIER = URL_BASE + NOM_PAQUET
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
        self.headers = {"Content-Length": str(len(octets))}
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
        self.reponse_fichier = None                               # une exception ou un objet pour remplacer le fichier
        self.detections = []
        self.empreintes_livrees = dict(ocr.EMPREINTE_PAQUET)
        self.sauve = {n: getattr(ms, n) for n in ("APP_DIR", "CONFIG", "ERREURS")}
        self.addCleanup(lambda: [setattr(ms, n, v) for n, v in self.sauve.items()])
        ms.APP_DIR, ms.CONFIG, ms.ERREURS = self.app, os.path.join(self.app, "config.json"), os.path.join(self.d, "erreurs.txt")
        for cible, nom, valeur in ((maj, "ouvrir", self.ouvrir), (urllib.request, "urlopen", self.urlopen_imprevu),
                                   (socket, "create_connection", self.connexion_imprevue),
                                   (ocr, "_detecter_chemin", self.detecter), (ocr, "_plateforme", lambda: PLATEFORME)):
            p = mock.patch.object(cible, nom, valeur)
            p.start()
            self.addCleanup(p.stop)
        self.poser_empreinte(self.archive)

    def tearDown(self):
        self.assertEqual(self.imprevus, [], "appel reseau non prevu")

    # -- doublures
    @staticmethod
    def empreinte(octets):
        return hashlib.sha256(octets).hexdigest()

    def poser_empreinte(self, octets, plateforme=None):
        """L'empreinte du paquet de `plateforme` (celle de la machine par defaut) devient celle de `octets`."""
        p = mock.patch.dict(ocr.EMPREINTE_PAQUET, {plateforme or PLATEFORME: self.empreinte(octets)})
        p.start()
        self.addCleanup(p.stop)

    def ouvrir(self, url, timeout=30):
        self.appels.append(url)
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

    def detecter(self, cfg, exe, source="portable"):
        """Double de _detecter_chemin : moteur present si l'exe passe en argument existe au moment de la detection."""
        self.detections.append(os.path.isfile(exe))
        if self.detections[-1]:
            return dict(ta.BLOC_MOTEUR, source=source, exe=exe)
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
        self.assertEqual(self.detections, [True], "detection du moteur neuf, une fois, avant la mise en place")
        self.assertEqual(self.appels, [URL_FICHIER])
        self.assertEqual(self.traces(), (["tesseract"], []), "aucun fichier ni dossier temporaire ne reste")
        self.assertTrue(vus and vus[0][1] == len(self.archive))

    def test_aucune_empreinte_lue_chez_le_serveur(self):
        """L'empreinte est dans le code (decision 4) : la seule requete est celle du fichier, aucune API n'est lue, et
        un fichier different de l'empreinte du code est refuse, que le serveur le dise bon ou non."""
        self.assertEqual(ocr.installer_paquet(), {"ok": True, "version": "5.5.3"})
        self.assertEqual(self.appels, [URL_FICHIER], "aucune requete a l'API de GitHub")
        falsifie = self.archive + b"x"
        self.reponse_fichier = Reponse(falsifie)
        self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})

    def test_remplace_une_installation_precedente(self):
        os.makedirs(self.cible)
        with open(os.path.join(self.cible, "ancien.txt"), "w") as f:
            f.write("ancien")
        self.assertEqual(ocr.installer_paquet(), {"ok": True, "version": "5.5.3"})
        self.assertEqual(sorted(os.listdir(self.cible)), sorted([EXE, "lourd.bin", "tessdata"]))
        self.assertEqual(self.traces(), (["tesseract"], []))

    def test_installation_precedente_intacte_si_le_nouveau_paquet_est_invalide(self):
        """Ecart 248 : un dossier precedent valide n'est ni remplace ni supprime quand le nouveau moteur echoue."""
        os.makedirs(os.path.join(self.cible, "tessdata"))
        for nom, contenu in ((EXE, b"ANCIEN"), ("tessdata/fra.traineddata", b"ancien")):
            with open(os.path.join(self.cible, *nom.split("/")), "wb") as f:
                f.write(contenu)
        with mock.patch.object(ocr, "_detecter_chemin", lambda cfg, exe, source: dict(ocr.BLOC_ABSENT)):
            r = ocr.installer_paquet()
        self.assertEqual(r, {"erreur": ocr.MESSAGES["installation_echec"]})
        with open(os.path.join(self.cible, EXE), "rb") as f:
            self.assertEqual(f.read(), b"ANCIEN")
        with open(os.path.join(self.cible, "tessdata", "fra.traineddata"), "rb") as f:
            self.assertEqual(f.read(), b"ancien")
        self.assertEqual(sorted(os.listdir(self.cible)), sorted([EXE, "tessdata"]))
        self.assertEqual(self.traces(), (["tesseract"], []), "le dossier neuf est retire, rien d'autre ne reste")

    def test_moteur_qui_ne_repond_pas_a_la_config_n_empeche_pas_l_installation(self):
        """Ecart 247 : `ocr_exe` existe mais rend une version 3. Detection reelle (executer double) : le paquet est
        detecte par son chemin connu, l'installation reussit et le paquet reste en place."""
        faux = os.path.join(self.d, "vieux-tesseract")
        with open(faux, "wb") as f:
            f.write(b"x")
        with open(ms.CONFIG, "w", encoding="utf-8") as f:
            json.dump({"ocr_exe": faux}, f)
        lances = []

        def executer(args, *, delai, arreter=None):
            lances.append(args[0])
            if args[0] == faux:
                return 0, b"tesseract 3.05.02\n", b""
            if "--version" in args:
                return 0, b"tesseract 5.5.3\n", b""
            return 0, b"List of available languages (2):\neng\nfra\n", b""
        with mock.patch.object(ocr, "_detecter_chemin", DETECTER_CHEMIN_REEL), \
                mock.patch.object(ocr, "executer", executer), mock.patch.object(ocr, "_exe_registre", lambda: None), \
                mock.patch.object(ocr, "_exe_usuel", lambda: None), mock.patch.object(ocr.shutil, "which", lambda n: None):
            r = ocr.installer_paquet()
            self.assertEqual(r, {"ok": True, "version": "5.5.3"})
            self.assertTrue(os.path.isfile(os.path.join(self.cible, EXE)), "le paquet reste")
            self.assertEqual(self.traces(), (["config.json", "tesseract"], ["vieux-tesseract"]))
            bloc = ocr.detecter({"ocr_exe": faux})
        self.assertTrue(bloc["present"], "la detection passe au candidat suivant")
        self.assertEqual((bloc["source"], bloc["exe"]), ("portable", os.path.join(self.cible, EXE)))

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
        with mock.patch.object(ocr, "_detecter_chemin", lambda cfg, exe, source: dict(ocr.BLOC_ABSENT)):
            r = ocr.installer_paquet()
        self.assertEqual(r, {"erreur": ocr.MESSAGES["installation_echec"]})
        self.assertEqual(self.traces(), ([], []))


class EmpreinteEtPublication(Reseau):
    def test_empreinte_fausse(self):
        """Le fichier est supprime, rien n'est decompresse, la phrase vient de MESSAGES."""
        with mock.patch.dict(ocr.EMPREINTE_PAQUET, {PLATEFORME: self.empreinte(b"autre chose")}), \
                mock.patch.object(zipfile, "ZipFile", side_effect=AssertionError("archive ouverte")):
            r = ocr.installer_paquet()
        self.assertEqual(r, {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []), "ni fichier telecharge, ni dossier")
        self.assertEqual(self.detections, [])

    def test_paquet_sans_empreinte(self):
        """Empreinte vide ou absente pour ce systeme : phrase claire, ni reseau ni decompression."""
        for vide in ("", None, "  "):
            with self.subTest(constante=vide), mock.patch.dict(ocr.EMPREINTE_PAQUET, {PLATEFORME: vide}):
                self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["installation_indisponible"]})
        self.assertEqual(self.appels, [])
        self.assertEqual(self.traces(), ([], []))

    def test_fichier_hors_github_refuse(self):
        with mock.patch.object(ocr, "URL_BASE_PAQUETS", "https://exemple.org/moteur/"):
            self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.appels, [], "le fichier hors GitHub n'est jamais demande")

    def test_fichier_trop_gros_refuse(self):
        """Taille annoncee trop grande : refus avant le premier octet ; taille non annoncee : refus en cours de route."""
        with mock.patch.object(ocr, "TAILLE_MAX_PAQUET", 1000):
            annoncee = Reponse(self.archive)
            self.reponse_fichier = annoncee
            self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
            self.assertEqual(annoncee.lus, 0, "aucun octet n'est lu quand la taille annoncee est deja trop grande")
            self.assertEqual(self.traces(), ([], []))
            muet = Reponse(self.archive)
            del muet.headers["Content-Length"]
            self.reponse_fichier = muet
            self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []))

    def test_taille_inconnue_progression_indeterminee(self):
        """Sans Content-Length, le total vaut 0 : la page garde une barre indeterminee (sync.js)."""
        muet = Reponse(self.archive)
        del muet.headers["Content-Length"]
        self.reponse_fichier = muet
        vus = []
        self.assertEqual(ocr.installer_paquet(progres=lambda recu, total: vus.append(total)),
                         {"ok": True, "version": "5.5.3"})
        self.assertTrue(vus and set(vus) == {0})


class ReseauIndisponible(Reseau):
    def verifier(self, r):
        self.assertEqual(r, {"erreur": ocr.MESSAGES["paquet_hors_ligne"]})
        for interdit in ("Traceback", "URLError", "Errno", "getaddrinfo", "ConnectionReset", ".py"):
            self.assertNotIn(interdit, r["erreur"])
        self.assertEqual(self.traces(), ([], []))

    def test_serveur_injoignable(self):
        self.reponse_fichier = urllib.error.URLError("[Errno -2] Name or service not known")
        self.verifier(ocr.installer_paquet())

    def test_limite_de_requetes_ou_erreur_http(self):
        self.reponse_fichier = urllib.error.HTTPError(URL_FICHIER, 403, "rate limit", {}, None)
        self.verifier(ocr.installer_paquet())

    def test_delai_depasse(self):
        self.reponse_fichier = TimeoutError("timed out")
        self.verifier(ocr.installer_paquet())

    def test_connexion_coupee_pendant_le_telechargement(self):
        self.reponse_fichier = Reponse(self.archive, panne_apres=300_000)
        self.verifier(ocr.installer_paquet())

    def test_telechargement_refuse(self):
        self.reponse_fichier = urllib.error.URLError("refuse")
        self.verifier(ocr.installer_paquet())

    def test_fichier_qui_n_est_pas_une_archive_malgre_une_bonne_reponse(self):
        """Une page d'erreur HTML a la place du fichier : l'empreinte ne correspond pas, rien n'est decompresse."""
        self.reponse_fichier = Reponse(b"<html>pas un zip</html>")
        r = ocr.installer_paquet()
        self.assertEqual(r, {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []))


class CheminsDeLArchive(Reseau):
    def poser(self, membres, symboles=()):
        self.archive = fabriquer_zip(membres, symboles)
        self.poser_empreinte(self.archive)

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

    def test_archive_sans_donnees_de_langue(self):
        """Ecart 252 : pas de tessdata, ou un tessdata sans .traineddata : refus avant toute decompression."""
        for nom, membres in (("sans_dossier", {EXE: b"MOTEUR", "lourd.bin": b"x"}),
                             ("dossier_vide", {EXE: b"MOTEUR", "tessdata/": b""}),
                             ("sans_traineddata", {EXE: b"MOTEUR", "tessdata/configs/lisezmoi.txt": b"x"}),
                             ("tessdata_ailleurs", {EXE: b"MOTEUR", "sous/tessdata/fra.traineddata": b"x"})):
            with self.subTest(cas=nom):
                self.poser(membres)
                with mock.patch.object(ocr, "_decompresser_paquet", wraps=ocr._decompresser_paquet) as d, \
                        mock.patch.object(shutil, "copyfileobj", side_effect=AssertionError("ecriture")):
                    self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
                self.assertEqual(d.call_count, 1)
                self.assertEqual(self.traces(), ([], []))
                self.assertEqual(self.detections, [])

    def test_pas_une_archive(self):
        self.archive = b"ceci n'est pas un zip"
        self.poser_empreinte(self.archive)
        self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []))

    def test_archive_trop_grosse_une_fois_decompressee(self):
        with mock.patch.object(ocr, "TAILLE_MAX_DECOMPRESSE", 1000):
            self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
        self.assertEqual(self.traces(), ([], []))

    def test_sous_dossiers_et_noms_a_accents(self):
        self.poser({EXE: b"MOTEUR", "tessdata/fra.traineddata": b"x", "tessdata/configs/été.txt": b"x", "tessdata/": b""})
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
        self.reponse_fichier = urllib.error.URLError("hors ligne")
        ocr.installer_paquet()
        self.assertEqual(self.traces(), ([], []))

    def test_le_verrou_est_relache_apres_une_erreur(self):
        self.reponse_fichier = urllib.error.URLError("x")
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
        with mock.patch.object(ocr, "URL_BASE_PAQUETS", "https://github.com/autre/depot/releases/download/x/"):
            r = ocr.installer_paquet()
        self.assertIn("erreur", r)
        self.assertEqual(len(self.imprevus), 1)
        self.imprevus.clear()

    def test_l_adresse_est_celle_de_la_release_du_depot_du_moteur(self):
        ocr.installer_paquet()
        self.assertEqual(self.appels, [URL_FICHIER])
        self.assertEqual(ocr.URL_BASE_PAQUETS, URL_BASE)
        self.assertEqual(ocr.DEPOT_MOTEUR, "MarinWasAsleep/MoodleSync-moteur")


# Disposition des deux archives de la release v1.0.0, relevee sur les fichiers publies (10 novembre 2026) : les noms
# sont ceux des archives reelles, les contenus sont factices.
MEMBRES_WINDOWS = {"tesseract.exe": b"MZ", "libtesseract-5.dll": b"d", "libleptonica-6.dll": b"d", "zlib1.dll": b"d",
                   "tessdata/fra.traineddata": b"fra", "tessdata/eng.traineddata": b"eng",
                   "tessdata/osd.traineddata": b"osd", "tessdata/configs/hocr": b"c", "tessdata/pdf.ttf": b"t"}
MEMBRES_MACOS = {"tesseract": b"mach-o", "LICENSE-tesseract.txt": b"licence", "lib/libleptonica.6.dylib": b"d",
                 "lib/libleptonica.dylib": b"d", "lib/libjpeg.8.3.2.dylib": b"d",
                 "tessdata/fra.traineddata": b"fra", "tessdata/eng.traineddata": b"eng",
                 "tessdata/osd.traineddata": b"osd"}
MEMBRES = {"win32": MEMBRES_WINDOWS, "darwin": MEMBRES_MACOS}


class DeuxPaquets(Reseau):
    """Ecart 279 : un paquet par systeme, choisi selon sys.platform ; jamais celui de l'autre systeme."""

    def systeme(self, plateforme):
        """Fait croire a ocr qu'il tourne sous `plateforme` et pose une archive a la disposition de ce systeme."""
        p = mock.patch.object(ocr, "_plateforme", lambda: plateforme)
        p.start()
        self.addCleanup(p.stop)
        self.archive = fabriquer_zip(MEMBRES[plateforme])
        self.poser_empreinte(self.archive, plateforme)
        autre = "darwin" if plateforme == "win32" else "win32"
        self.url = URL_BASE + PAQUETS_ATTENDUS[plateforme][0]
        self.url_autre = URL_BASE + PAQUETS_ATTENDUS[autre][0]

        def ouvrir(url, timeout=30):
            self.appels.append(url)
            if url == self.url:
                return Reponse(self.archive)
            self.imprevus.append(url)
            raise AssertionError(f"adresse non prevue : {url}")
        p = mock.patch.object(maj, "ouvrir", ouvrir)
        p.start()
        self.addCleanup(p.stop)

    def test_constantes_livrees(self):
        for plateforme, (nom, empreinte, exe) in PAQUETS_ATTENDUS.items():
            with self.subTest(plateforme=plateforme):
                self.assertEqual(ocr.NOM_PAQUET[plateforme], nom)
                self.assertEqual(self.empreintes_livrees[plateforme], empreinte)
                self.assertRegex(empreinte, r"^[0-9a-f]{64}$")
                self.assertEqual(ocr._nom_exe(plateforme), exe)
        self.assertEqual(set(ocr.NOM_PAQUET), {"win32", "darwin"})
        self.assertEqual(set(self.empreintes_livrees), {"win32", "darwin"})
        self.assertEqual(len(set(ocr.NOM_PAQUET.values())), 2, "deux fichiers distincts")
        self.assertEqual(len(set(self.empreintes_livrees.values())), 2, "deux empreintes distinctes")
        self.assertEqual(ocr.URL_BASE_PAQUETS, URL_BASE)

    def test_choix_selon_la_plateforme(self):
        for plateforme in ("win32", "darwin"):
            with self.subTest(plateforme=plateforme):
                nom, empreinte, exe = PAQUETS_ATTENDUS[plateforme]
                with mock.patch.dict(ocr.EMPREINTE_PAQUET, self.empreintes_livrees, clear=True):   # les valeurs livrees
                    with mock.patch.object(ocr, "_plateforme", lambda: plateforme):
                        self.assertEqual(ocr._paquet(), (nom, empreinte))
                    self.assertEqual(ocr._paquet(plateforme), (nom, empreinte))
        self.assertIsNone(ocr._paquet("linux"))

    def test_chaque_systeme_telecharge_son_paquet_et_jamais_l_autre(self):
        for plateforme in ("win32", "darwin"):
            with self.subTest(plateforme=plateforme):
                self.appels.clear()
                self.systeme(plateforme)
                r = ocr.installer_paquet()
                self.assertEqual(r, {"ok": True, "version": "5.5.3"})
                self.assertEqual(self.appels, [self.url])
                self.assertNotIn(self.url_autre, self.appels)
                exe = PAQUETS_ATTENDUS[plateforme][2]
                self.assertTrue(os.path.isfile(os.path.join(self.cible, exe)), "le moteur est a la racine du dossier")
                self.assertTrue(os.path.isfile(os.path.join(self.cible, "tessdata", "fra.traineddata")))
                shutil.rmtree(self.cible)

    def test_systeme_sans_paquet(self):
        """Linux, BSD, valeur inconnue : installation_indisponible, ni reseau ni dossier, aucun paquet essaye."""
        for plateforme in ("linux", "freebsd", "cygwin", "", None):
            with self.subTest(plateforme=plateforme), mock.patch.object(ocr, "_plateforme", lambda: plateforme):
                self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["installation_indisponible"]})
        self.assertEqual(self.appels, [])
        self.assertEqual(self.traces(), ([], []))

    def test_paquet_absent_pour_ce_systeme_ne_prend_pas_celui_de_l_autre(self):
        """Seule l'empreinte de Windows est connue, le systeme est macOS : rien n'est demande, ni l'un ni l'autre."""
        self.systeme("darwin")
        with mock.patch.dict(ocr.EMPREINTE_PAQUET, {"win32": self.empreinte(self.archive)}, clear=True):
            self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["installation_indisponible"]})
        with mock.patch.dict(ocr.NOM_PAQUET, {"win32": PAQUETS_ATTENDUS["win32"][0]}, clear=True):
            self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["installation_indisponible"]})
        self.assertEqual(self.appels, [])
        self.assertEqual(self.traces(), ([], []))

    def test_l_archive_de_l_autre_systeme_est_refusee(self):
        """Un paquet Windows servi sous macOS (ou l'inverse) n'a pas le moteur attendu a la racine : refus."""
        for plateforme, autre in (("darwin", "win32"), ("win32", "darwin")):
            with self.subTest(plateforme=plateforme):
                self.systeme(plateforme)
                self.archive = fabriquer_zip(MEMBRES[autre])
                self.poser_empreinte(self.archive, plateforme)
                self.assertEqual(ocr.installer_paquet(), {"erreur": ocr.MESSAGES["paquet_invalide"]})
                self.assertEqual(self.traces(), ([], []))

    def test_detection_apres_installation_sur_les_deux_dispositions(self):
        """La detection REELLE (ocr.detecter, `executer` double) retrouve le moteur du paquet sous les deux systemes :
        meme ordre des candidats, source `portable`, exe a la racine du dossier, tessdata a cote."""
        def executer(args, *, delai, arreter=None):
            if "--version" in args:
                return 0, b"tesseract 5.5.3\n", b""
            return 0, b"List of available languages (3):\neng\nfra\nosd\n", b""
        for plateforme in ("win32", "darwin"):
            with self.subTest(plateforme=plateforme):
                self.systeme(plateforme)
                exe = PAQUETS_ATTENDUS[plateforme][2]
                with mock.patch.object(ocr, "_detecter_chemin", DETECTER_CHEMIN_REEL), \
                        mock.patch.object(ocr, "executer", executer), mock.patch.object(ocr, "_exe_registre", lambda: None), \
                        mock.patch.object(ocr, "_exe_usuel", lambda: None), \
                        mock.patch.object(ocr.shutil, "which", lambda n: None), \
                        mock.patch.dict(os.environ, {"TESSDATA_PREFIX": ""}):
                    self.assertEqual(ocr.installer_paquet(), {"ok": True, "version": "5.5.3"})
                    bloc = ocr.detecter({})
                self.assertTrue(bloc["present"])
                self.assertEqual((bloc["source"], bloc["version"]), ("portable", "5.5.3"))
                self.assertEqual(bloc["exe"], os.path.join(self.cible, exe))
                self.assertEqual(bloc["tessdata"], os.path.join(self.cible, "tessdata"))
                self.assertEqual(bloc["langues"], ["eng", "fra", "osd"])
                shutil.rmtree(self.cible)

    def test_noms_d_archive_ecrits_avec_des_antislash(self):
        """Une archive fabriquee sous Windows peut garder `tessdata\\fra.traineddata` : le moteur est encore trouve."""
        self.systeme("win32")
        self.archive = fabriquer_zip({"tesseract.exe": b"MZ", "tessdata\\fra.traineddata": b"fra"})
        self.poser_empreinte(self.archive, "win32")
        self.assertEqual(ocr.installer_paquet(), {"ok": True, "version": "5.5.3"})
        self.assertTrue(os.path.isfile(os.path.join(self.cible, "tessdata", "fra.traineddata")))

    def test_le_moteur_se_cherche_selon_le_systeme(self):
        """`_exe_portable` cherche `tesseract.exe` sous Windows et `tesseract` ailleurs, dans le dossier du paquet."""
        os.makedirs(self.cible)
        for nom in ("tesseract.exe", "tesseract"):
            with open(os.path.join(self.cible, nom), "wb") as f:
                f.write(b"x")
        for plateforme, exe in (("win32", "tesseract.exe"), ("darwin", "tesseract")):
            with self.subTest(plateforme=plateforme), mock.patch.object(ocr, "_plateforme", lambda: plateforme):
                self.assertEqual(ocr._exe_portable(), os.path.join(self.cible, exe))


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
        """Sans doublure de installer_paquet, sur un systeme sans paquet : la phrase le dit et rien n'est demande."""
        with mock.patch.object(ocr, "_plateforme", lambda: "linux"):
            r = self.api.ocr_installer()
        self.assertEqual(r, {"erreur": ocr.MESSAGES["installation_indisponible"]})
        self.assertEqual(self.phrases_du_journal(), [ocr.MESSAGES["installation_indisponible"]])

    def installer_pour_de_vrai(self, archive, reponse):
        """Vraie installer_paquet, reseau double ; l'horloge avance de 0,3 s par lecture, donc chaque bloc est signale."""
        horloge = [0.0]

        def avance():
            horloge[0] += 0.3
            return horloge[0]

        def ouvrir(url, timeout=30):
            if url == URL_FICHIER:
                return reponse
            self.imprevus.append(url)
            raise AssertionError(url)
        sans_moteur = lambda cfg: dict(ocr.BLOC_ABSENT) if not os.path.isfile(os.path.join(self.d, "tesseract", EXE)) \
            else dict(ta.BLOC_MOTEUR, source="portable")
        with mock.patch.object(maj, "ouvrir", ouvrir), mock.patch.object(ocr, "detecter", sans_moteur), \
                mock.patch.object(ocr, "_horloge", avance), \
                mock.patch.object(ocr, "_detecter_chemin", lambda cfg, exe, source: dict(ta.BLOC_MOTEUR, source=source)
                                  if os.path.isfile(exe) else dict(ocr.BLOC_ABSENT)), \
                mock.patch.object(ocr, "_plateforme", lambda: PLATEFORME), \
                mock.patch.dict(ocr.EMPREINTE_PAQUET, {PLATEFORME: hashlib.sha256(archive).hexdigest()}):
            return self.api.ocr_installer()

    def progressions(self):
        return [json.loads(c[c.index("(") + 1:c.rindex(")")]) for c in self.fenetre.appels if "textesInstallation" in c]

    def test_progression_poussee_vers_la_page(self):
        """Ecart 245 : `ocr_installer` relaie `progres` : window.textesInstallation({recu, total}), au moins deux fois."""
        archive = paquet_valide()
        r = self.installer_pour_de_vrai(archive, Reponse(archive))
        self.assertTrue(r["moteur"]["present"])
        vus = self.progressions()
        self.assertGreaterEqual(len(vus), 2)
        self.assertTrue(all(set(v) == {"recu", "total"} and v["total"] == len(archive) for v in vus))
        self.assertEqual([v["recu"] for v in vus], sorted(v["recu"] for v in vus), "la progression ne recule pas")

    def test_annulation_depuis_la_page_ne_laisse_aucun_dossier(self):
        """Ecart 245 : `ocr_installer_annuler` pose l'arret ; `ocr_installer` rend {"annule": True}, rien ne reste."""
        archive = paquet_valide()
        api = self.api

        class Interrompue(Reponse):
            def read(self, n=-1):
                if self.lus > 0:
                    self.annule = api.ocr_installer_annuler()
                return super().read(n)
        reponse = Interrompue(archive)
        r = self.installer_pour_de_vrai(archive, reponse)
        self.assertEqual(r, {"annule": True})
        self.assertEqual(reponse.annule, {"ok": True})
        self.assertLess(reponse.lus, len(archive), "le telechargement s'est arrete")
        self.assertEqual(sorted(os.listdir(self.d)), sorted(n for n in os.listdir(self.d) if n in ("coffre", "config.json")),
                         "ni .paquet, ni .tesseract, ni dossier tesseract")
        self.assertEqual(self.journal(), [], "annuler n'ecrit rien au journal")
        r = self.installer_pour_de_vrai(archive, Reponse(archive))
        self.assertTrue(r["moteur"]["present"], "l'arret est repose a zero a l'appel suivant")

    def test_de_bout_en_bout_avec_le_reseau_double(self):
        """Vraie installer_paquet, reseau double : ocr_installer rend l'etat, le dossier existe, un seul telechargement."""
        archive = paquet_valide()
        vus = []

        def ouvrir(url, timeout=30):
            vus.append(url)
            if url == URL_FICHIER:
                return Reponse(archive)
            self.imprevus.append(url)
            raise AssertionError(url)

        def detecter(cfg):
            ok = os.path.isfile(os.path.join(self.d, "tesseract", EXE))
            return dict(ta.BLOC_MOTEUR, source="portable") if ok else dict(ocr.BLOC_ABSENT)
        with mock.patch.object(maj, "ouvrir", ouvrir), mock.patch.object(ocr, "detecter", detecter), \
                mock.patch.object(ocr, "_detecter_chemin", lambda cfg, exe, source: dict(ta.BLOC_MOTEUR, source=source)
                                  if os.path.isfile(exe) else dict(ocr.BLOC_ABSENT)), \
                mock.patch.object(ocr, "_plateforme", lambda: PLATEFORME), \
                mock.patch.dict(ocr.EMPREINTE_PAQUET, {PLATEFORME: hashlib.sha256(archive).hexdigest()}):
            r = self.api.ocr_installer()
        self.assertEqual(vus, [URL_FICHIER])
        self.assertTrue(r["moteur"]["present"])
        self.assertEqual(r["moteur"]["source"], "portable")
        self.assertTrue(os.path.isfile(os.path.join(self.d, "tesseract", EXE)), "dans le dossier des reglages")
        self.assertFalse(os.path.exists(os.path.join(self.dest, "tesseract")), "jamais dans le dossier de cours")


if __name__ == "__main__":
    unittest.main()
