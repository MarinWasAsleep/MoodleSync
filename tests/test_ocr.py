#!/usr/bin/env python3
"""Tests hors ligne de ocr.py : detection du moteur Tesseract (tache C1), extraction d'une page,
TSV, qualite et Markdown par document (tache C2).

Le sous-processus et le rendu sont remplaces par des doublures (executer, rendre_page), le registre
Windows est simule, les PDF sont fabriques a la main dans un dossier temporaire. Seul T29 lance le
vrai moteur, et il est ignore s'il est absent. Aucun acces reseau.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t . -v
"""
import hashlib, io, json, os, socket, sys, tempfile, time, unittest
import urllib.request
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import moteur as ms
from moodlesync import ocr


# Sortie reelle de tesseract --version (un « v » avant la version, fins de ligne CRLF), et
# --list-langs avec son en-tete, telles que mesurees par S sur la machine de developpement.
VERSION = b"tesseract v5.5.3.20260724\r\n leptonica-1.87.0\r\n"
LANGS = b'List of available languages in "C:\\tessdata/" (3):\r\neng\r\nfra\r\nosd\r\n'


class CleRegistre:
    """Doublure de la cle ouverte par winreg : simple gestionnaire de contexte."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FauxWinreg:
    """winreg simule : les cles Tesseract-OCR renvoient toutes le meme dossier, via Path et InstallDir."""

    HKEY_LOCAL_MACHINE = object()
    HKEY_CURRENT_USER = object()

    def __init__(self, dossier):
        self.dossier = dossier

    def OpenKey(self, racine, cle):
        return CleRegistre()

    def QueryValueEx(self, cle, valeur):
        return (self.dossier, 0)


class FauxWinregEntier:
    """winreg simule dont les valeurs Path et InstallDir sont des entiers, pas des chemins."""

    HKEY_LOCAL_MACHINE = object()
    HKEY_CURRENT_USER = object()

    def OpenKey(self, racine, cle):
        return CleRegistre()

    def QueryValueEx(self, cle, valeur):
        return (12345, 0)


class Detection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        # tesseract.exe range dans un dossier quelconque, hors du PATH : seul le registre le trouve.
        self.exe = os.path.join(d, "Tesseract-OCR", "tesseract.exe")
        os.makedirs(os.path.dirname(self.exe), exist_ok=True)
        with open(self.exe, "wb"):
            pass
        self.tessdata = os.path.join(d, "tessdata")
        os.makedirs(self.tessdata, exist_ok=True)

    def executer(self, args, *, delai, arreter=None):
        if "--version" in args:
            return 0, VERSION, b""
        if "--list-langs" in args:
            return 0, LANGS, b""
        return 1, b"", b""

    def test_detection_hors_path(self):
        """T25 : registre simule, chemin hors du PATH, TESSDATA_PREFIX, langue manquante et repli."""
        cfg = {"ocr_exe": "", "ocr_langues": "fra+deu"}
        faux = FauxWinreg(os.path.dirname(self.exe))
        with mock.patch.dict(sys.modules, {"winreg": faux}), \
                mock.patch.object(ocr.shutil, "which", return_value=None), \
                mock.patch.object(ocr, "executer", self.executer), \
                mock.patch.dict(os.environ, {"TESSDATA_PREFIX": self.tessdata}):
            bloc = ocr.detecter(cfg)
            reglages = ocr.reglages_depuis(cfg)

        self.assertTrue(bloc["present"])
        self.assertEqual(bloc["source"], "registre")
        self.assertEqual(bloc["exe"], self.exe)
        self.assertEqual(bloc["majeure"], 5)
        self.assertEqual(bloc["version"], "5.5.3")
        self.assertEqual(bloc["langues"], ["eng", "fra", "osd"])
        self.assertEqual(bloc["tessdata"], self.tessdata)
        # deu manque dans les langues detectees : repli sur fra, signale par le message.
        self.assertEqual(bloc["langues_effectives"], "fra")
        self.assertTrue(bloc["repli"])
        self.assertEqual(bloc["message"], ocr.MESSAGES["langue_manquante"])

        # reglages_depuis : langues effectives apres repli, et les autres cles du contrat 3.1.
        self.assertEqual(reglages, {"langues": "fra", "dpi": 300, "psm": 3, "oem": 1,
                                    "moteur": "5.5.3", "tessdata": self.tessdata})

    def test_list_langs_avec_tessdata_dir(self):
        """--list-langs recoit --tessdata-dir <dossier> quand ocr_tessdata est pose (constat 2)."""
        appels = []

        def executer(args, *, delai, arreter=None):
            appels.append(list(args))
            if "--version" in args:
                return 0, VERSION, b""
            if "--list-langs" in args:
                return 0, LANGS, b""
            return 1, b"", b""

        cfg = {"ocr_exe": self.exe, "ocr_langues": "fra", "ocr_tessdata": self.tessdata}
        with mock.patch.object(ocr, "executer", executer):
            bloc = ocr.detecter(cfg)

        self.assertTrue(bloc["present"])
        appels_langues = [a for a in appels if "--list-langs" in a]
        self.assertEqual(len(appels_langues), 1)
        i = appels_langues[0].index("--tessdata-dir")
        self.assertEqual(appels_langues[0][i + 1], self.tessdata)

    def test_dossier_tessdata_inexistant(self):
        """Un dossier de donnees qui n'existe pas n'est jamais renvoye : tessdata vaut "" (constat 3)."""
        cfg = {"ocr_tessdata": os.path.join(self.tmp.name, "nulle-part")}
        with mock.patch.dict(os.environ, {"TESSDATA_PREFIX": ""}):
            self.assertEqual(ocr._dossier_tessdata(cfg, self.exe), "")

    def test_repli_langues(self):
        """Repli : deu avec eng, fra, osd donne fra ; deu avec osd seul donne rien (constats 4, 6)."""
        effectives, repli = ocr._langues_effectives("deu", ["eng", "fra", "osd"])
        self.assertEqual(effectives, "fra")
        self.assertTrue(repli)

        effectives, repli = ocr._langues_effectives("deu", ["osd"])
        self.assertEqual(effectives, "")
        self.assertTrue(repli)

        # equ est exclu aussi, comme osd.
        effectives, repli = ocr._langues_effectives("fra", ["fra", "equ", "osd"])
        self.assertEqual(effectives, "fra")
        self.assertFalse(repli)

    def test_detecter_sans_langue_utilisable(self):
        """Moteur present sans langue exploitable : repli, message langue_manquante (constat 5)."""
        def executer(args, *, delai, arreter=None):
            if "--version" in args:
                return 0, VERSION, b""
            if "--list-langs" in args:
                return 0, b"List of available languages (1):\r\nosd\r\n", b""
            return 1, b"", b""

        cfg = {"ocr_exe": self.exe, "ocr_langues": "deu"}
        with mock.patch.object(ocr, "executer", executer):
            bloc = ocr.detecter(cfg)

        self.assertTrue(bloc["present"])
        self.assertEqual(bloc["langues_effectives"], "")
        self.assertTrue(bloc["repli"])
        self.assertEqual(bloc["message"], ocr.MESSAGES["langue_manquante"])

    def test_sources_et_version_trois(self):
        """Sources config, path, usuel ; une version 3 donne un moteur absent (constat 14)."""
        def executer_v3(args, *, delai, arreter=None):
            if "--version" in args:
                return 0, b"tesseract v3.05.02\r\n", b""
            return 1, b"", b""

        def executer_ok(args, *, delai, arreter=None):
            if "--version" in args:
                return 0, VERSION, b""
            if "--list-langs" in args:
                return 0, LANGS, b""
            return 1, b"", b""

        # Version 3 : absent, message moteur_absent.
        with mock.patch.object(ocr, "executer", executer_v3):
            bloc = ocr.detecter({"ocr_exe": self.exe})
        self.assertFalse(bloc["present"])
        self.assertEqual(bloc["message"], ocr.MESSAGES["moteur_absent"])

        # Source config : ocr_exe valide.
        with mock.patch.object(ocr, "executer", executer_ok):
            bloc = ocr.detecter({"ocr_exe": self.exe, "ocr_langues": "fra"})
        self.assertTrue(bloc["present"])
        self.assertEqual(bloc["source"], "config")

        # Source path : shutil.which trouve.
        with mock.patch.object(ocr, "executer", executer_ok), \
                mock.patch.object(ocr.shutil, "which", return_value=self.exe):
            bloc = ocr.detecter({"ocr_exe": "", "ocr_langues": "fra"})
        self.assertTrue(bloc["present"])
        self.assertEqual(bloc["source"], "path")

        # Source usuel : rien d'autre ne trouve, le chemin usuel si.
        with mock.patch.object(ocr, "executer", executer_ok), \
                mock.patch.object(ocr.shutil, "which", return_value=None), \
                mock.patch.object(ocr, "_exe_registre", return_value=None), \
                mock.patch.object(ocr, "_exe_usuel", return_value=self.exe):
            bloc = ocr.detecter({"ocr_exe": "", "ocr_langues": "fra"})
        self.assertTrue(bloc["present"])
        self.assertEqual(bloc["source"], "usuel")

    def test_version_et_langues_sur_stderr(self):
        """--version et --list-langs ecrits sur la sortie d'erreur sont lus (constat 8)."""
        def executer(args, *, delai, arreter=None):
            if "--version" in args:
                return 0, b"", VERSION
            if "--list-langs" in args:
                return 0, b"", LANGS
            return 1, b"", b""

        cfg = {"ocr_exe": self.exe, "ocr_langues": "fra"}
        with mock.patch.object(ocr, "executer", executer):
            bloc = ocr.detecter(cfg)

        self.assertTrue(bloc["present"])
        self.assertEqual(bloc["version"], "5.5.3")
        self.assertEqual(bloc["langues"], ["eng", "fra", "osd"])

    def test_registre_valeur_non_texte(self):
        """Une valeur de registre non texte n'empeche pas d'essayer les chemins usuels (constat 11)."""
        with mock.patch.dict(sys.modules, {"winreg": FauxWinregEntier()}), \
                mock.patch.object(ocr.shutil, "which", return_value=None), \
                mock.patch.object(ocr, "_exe_usuel", return_value=self.exe), \
                mock.patch.object(ocr, "executer", self.executer):
            bloc = ocr.detecter({"ocr_exe": "", "ocr_langues": "fra"})

        self.assertTrue(bloc["present"])
        self.assertEqual(bloc["source"], "usuel")

    def test_langues_avec_suffixes(self):
        """RE_LANGUE garde chi_sim, deu_frak, fra, ignore script/Latin (constat 15)."""
        sortie = b"chi_sim\r\ndeu_frak\r\nfra\r\nscript/Latin\r\n"
        self.assertEqual(ocr._langues(sortie), ["chi_sim", "deu_frak", "fra"])

    def test_reglages_depuis_valeurs_illisibles(self):
        """ocr_dpi et ocr_psm illisibles reprennent 300 et 3 (constat 13)."""
        cfg = {"ocr_exe": self.exe, "ocr_langues": "fra", "ocr_dpi": "abc", "ocr_psm": None}
        with mock.patch.object(ocr, "executer", self.executer):
            reglages = ocr.reglages_depuis(cfg)

        self.assertEqual(reglages["dpi"], 300)
        self.assertEqual(reglages["psm"], 3)

    def test_executer_sous_processus_reel(self):
        """executer avec un vrai sous-processus Python, sans Tesseract ni reseau (constat 14)."""
        code, out, err = ocr.executer([sys.executable, "-c", "print('bonjour')"], delai=5)
        self.assertEqual(code, 0)
        self.assertIn(b"bonjour", out)
        self.assertEqual(err, b"")

        # Delai court sur un processus qui dort : code -1, en moins de quelques secondes.
        debut = time.monotonic()
        code, out, err = ocr.executer(
            [sys.executable, "-c", "import time; time.sleep(30)"], delai=0.5)
        self.assertEqual(code, -1)
        self.assertLess(time.monotonic() - debut, 5)

        # arreter=lambda: True interrompt de meme.
        code, out, err = ocr.executer(
            [sys.executable, "-c", "import time; time.sleep(30)"], delai=30, arreter=lambda: True)
        self.assertEqual(code, -1)

    def test_executer_creationflags_windows(self):
        """Sous nt, creationflags porte CREATE_NO_WINDOW (aucune console noire, constat 14)."""
        captures = {}

        class FauxPopen:
            returncode = 0

            def __init__(self, args, **kw):
                captures["args"] = list(args)
                captures["creationflags"] = kw.get("creationflags")

            def communicate(self, timeout=None):
                return b"", b""

            def poll(self):
                return 0

            def kill(self):
                pass

        with mock.patch.object(ocr.os, "name", "nt"), \
                mock.patch.object(ocr.subprocess, "Popen", FauxPopen):
            code, out, err = ocr.executer(["x", "--version"], delai=5)

        self.assertEqual(code, 0)
        self.assertEqual(captures["creationflags"] & 0x08000000, 0x08000000)


# ---------------------------------------------------------------------------------------------
# Tache C2 : texte natif, reconnaissance, TSV, qualite, Markdown par document.
# ---------------------------------------------------------------------------------------------

ENTETE_TSV = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
REGLAGES = {"langues": "fra+eng", "dpi": 300, "psm": 3, "oem": 1, "moteur": "5.5.3", "tessdata": ""}
EXE = "C:\\faux\\tesseract.exe"


def mot_tsv(bloc, par, ligne, mot, x, conf, texte, y=10, l=50, h=20):
    return f"5\t1\t{bloc}\t{par}\t{ligne}\t{mot}\t{x}\t{y}\t{l}\t{h}\t{conf}\t{texte}"


def tsv_exemple():
    """TSV avec des niveaux 1 a 4, des mots dans le desordre, des accents, une confiance negative."""
    lignes = [
        ENTETE_TSV,
        "1\t1\t0\t0\t0\t0\t0\t0\t2481\t3508\t-1\t",
        "2\t1\t1\t0\t0\t0\t100\t100\t800\t200\t-1\t",
        "3\t1\t1\t1\t0\t0\t100\t100\t800\t200\t-1\t",
        "4\t1\t1\t1\t1\t0\t100\t100\t800\t50\t-1\t",
        mot_tsv(2, 1, 1, 1, 100, "95.0", "Fin"),
        mot_tsv(1, 1, 2, 2, 250, "100", "élève"),
        mot_tsv(1, 1, 1, 3, 300, "-1", "œuvre"),
        mot_tsv(1, 1, 2, 1, 100, "70.0", "garçon"),
        mot_tsv(1, 1, 1, 2, 200, "80.0", "été"),
        mot_tsv(1, 1, 1, 1, 100, "90.0", "Où"),
        mot_tsv(1, 1, 3, 1, 100, "88.0", "   "),
        "5\t1\t1\t1\t3\t2\t300\t10\t50\t20\t88.0\t",
    ]
    return "\r\n".join(lignes) + "\r\n"


def pdf_minimal(pages):
    """PDF fabrique a la main. pages = liste de (lignes de texte, avec_image). Helvetica WinAnsi."""
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


# Trois lignes de francais : plus de 80 caracteres alphanumeriques.
TEXTE_NATIF = ["Le plan de Marshall transforme l'économie européenne après la guerre.",
               "Les États-Unis financent la reconstruction, mais ils imposent leurs conditions.",
               "Cette aide produit une dépendance durable envers le dollar."]


class Doublures(unittest.TestCase):
    """Dossier temporaire, journal d'erreurs isole, et doublures de executer et de rendre_page."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = self.tmp.name
        self.appels = []
        self.images = []   # chemins d'image passes a executer
        self.rendus = []
        self.tsv = tsv_exemple().encode("utf-8")
        self.code = 0
        sauve = ms.APP_DIR, ms.ERREURS
        ms.APP_DIR, ms.ERREURS = self.d, os.path.join(self.d, "erreurs.txt")
        self.addCleanup(lambda: (setattr(ms, "APP_DIR", sauve[0]), setattr(ms, "ERREURS", sauve[1])))

    def executer(self, args, *, delai, arreter=None):
        self.appels.append((list(args), delai, arreter))
        self.images.append(args[1])
        self.image_existait = os.path.isfile(args[1])
        return self.code, self.tsv, b""

    def rendre(self, chemin, numero, dpi):
        from PIL import Image
        self.rendus.append((chemin, numero, dpi))
        return Image.new("L", (120, 60), 255)

    def pdf(self, pages, nom="cours.pdf"):
        chemin = os.path.join(self.d, nom)
        with open(chemin, "wb") as f:
            f.write(pdf_minimal(pages))
        return chemin

    def extraire(self, chemin, numero=1, reglages=None, **kw):
        kw.setdefault("exe", EXE)
        with mock.patch.object(ocr, "executer", self.executer), mock.patch.object(ocr, "rendre_page", self.rendre):
            return ocr.extraire_page(chemin, numero, reglages if reglages is not None else REGLAGES, **kw)


class TsvEtReconstruction(Doublures):
    def test_tsv_accents(self):
        """T1 : niveau 5 seulement, ordre bloc, paragraphe, ligne, abscisse, confiance negative ignoree,
        UTF-8, accents, chemin a espaces et accents."""
        mots = ocr.parser_tsv(tsv_exemple())
        self.assertEqual(len(mots), 6)   # niveaux 1 a 4, mot vide et mot d'espaces ecartes
        self.assertEqual(set(mots[0]), {"bloc", "par", "ligne", "x", "y", "l", "h", "conf", "texte"})
        premier = mots[0]
        self.assertEqual((premier["bloc"], premier["texte"], premier["conf"]), (2, "Fin", 0.95))
        self.assertTrue(any(m["conf"] < 0 and m["texte"] == "œuvre" for m in mots))

        texte, confiance = ocr.reconstruire(mots)
        self.assertEqual(texte, "Où été œuvre\ngarçon élève\n\nFin")
        # (0,90 + 0,80 + 0,70 + 1,00 + 0,95) / 5 : le mot a confiance negative n'entre pas dans la moyenne.
        self.assertAlmostEqual(confiance, 0.87, places=3)
        self.assertEqual(ocr.reconstruire([]), ("", None))
        self.assertEqual(ocr.reconstruire([{"bloc": 1, "par": 1, "ligne": 1, "x": 0, "y": 0, "l": 1, "h": 1,
                                            "conf": -0.01, "texte": "a"}]), ("a", None))

        # Pipeline complet sur une image dont le chemin porte des espaces et des accents.
        from PIL import Image
        dossier = os.path.join(self.d, "Cours é è", "Section 1")
        os.makedirs(dossier)
        image = os.path.join(dossier, "Scan été n° 1.png")
        Image.new("L", (200, 100), 255).save(image)
        donnees = os.path.join(self.d, "données")
        page = self.extraire(image, 1, dict(REGLAGES, tessdata=donnees))
        self.assertEqual(page["texte"], "Où été œuvre\ngarçon élève\n\nFin")
        self.assertEqual(page["source"], "ocr")
        self.assertEqual(page["mots"], 6)
        args, delai, arreter = self.appels[0]
        temp = args[1]
        self.assertEqual(args, [EXE, temp, "stdout", "-l", "fra+eng", "--psm", "3", "--oem", "1",
                                "--tessdata-dir", donnees, "-c", "tessedit_create_tsv=1"])
        self.assertEqual(delai, 120)
        # L'image temporaire existait pendant l'appel, hors du dossier de rangement, et a disparu.
        self.assertTrue(self.image_existait)
        self.assertFalse(os.path.abspath(temp).startswith(os.path.abspath(dossier)))
        self.assertFalse(os.path.exists(temp))

    def test_parser_tsv_robuste(self):
        self.assertEqual(ocr.parser_tsv(""), [])
        self.assertEqual(ocr.parser_tsv(ENTETE_TSV + "\n"), [])
        sale = ENTETE_TSV + "\nn'importe quoi\n5\t1\t1\n" + mot_tsv(1, 1, 1, 1, 5, "x", "mal") + "\n" + \
            mot_tsv(1, 1, 1, 2, 9, "50", "bien") + "\n"
        mots = ocr.parser_tsv(sale)
        self.assertEqual([m["texte"] for m in mots], ["bien"])
        self.assertEqual(mots[0]["x"], 9)

    def test_sans_tessdata_pas_d_option(self):
        """tessdata == "" : aucun --tessdata-dir (convention de C1, ecart 42)."""
        from PIL import Image
        image = os.path.join(self.d, "a.png")
        Image.new("L", (50, 50), 255).save(image)
        self.extraire(image, 1, dict(REGLAGES, tessdata=""))
        args = self.appels[0][0]
        self.assertNotIn("--tessdata-dir", args)
        self.assertEqual(args[-2:], ["-c", "tessedit_create_tsv=1"])

    def test_boites_a_la_demande(self):
        from PIL import Image
        image = os.path.join(self.d, "a.png")
        Image.new("L", (50, 50), 255).save(image)
        self.assertIsNone(self.extraire(image)["boites"])
        boites = self.extraire(image, avec_boites=True)["boites"]
        self.assertEqual(len(boites), 6)
        self.assertEqual(boites[0], [100, 10, 50, 20, 0.95, "Fin"])


class Qualite(unittest.TestCase):
    def test_confiance_niveaux(self):
        """T4 : 0,85 bon ; 0,849 a verifier ; 0,70 a verifier ; 0,699 difficile ; None vide."""
        self.assertEqual(ocr.classer(0.85), "bon")
        self.assertEqual(ocr.classer(1.0), "bon")
        self.assertEqual(ocr.classer(0.849), "a_verifier")
        self.assertEqual(ocr.classer(0.70), "a_verifier")
        self.assertEqual(ocr.classer(0.699), "difficile")
        self.assertEqual(ocr.classer(0.0), "difficile")
        self.assertEqual(ocr.classer(None), "vide")


class PageNative(Doublures):
    def test_natif_contre_ocr(self):
        """T2 : une page a 80 caracteres alphanumeriques reste du texte, zero appel a executer."""
        chemin = self.pdf([(TEXTE_NATIF, False)])
        page = self.extraire(chemin, 1, dict(REGLAGES, langues=""), exe="")   # aucun moteur n'est necessaire
        self.assertEqual(page["source"], "texte")
        self.assertEqual(page["numero"], 1)
        self.assertIn("économie européenne", page["texte"])
        self.assertIsNone(page["confiance"])
        self.assertIsNone(page["boites"])
        self.assertGreater(page["mots"], 10)
        self.assertEqual(self.appels, [])
        self.assertEqual(self.rendus, [])

        # Le seuil : exactement 80 caracteres alphanumeriques, ponctuation et espaces non comptes.
        self.assertEqual(ocr.decider_source("a" * 80), "texte")
        self.assertEqual(ocr.decider_source("a" * 79 + " .,;:!?- " * 20), "ocr")
        self.assertEqual(ocr.decider_source("é1" * 40), "texte")
        self.assertEqual(ocr.decider_source(""), "ocr")
        self.assertEqual(ocr.decider_source(None), "ocr")

        # forcer_ocr ignore le texte natif (decision de l'appelant, jamais de C2).
        page = self.extraire(chemin, 1, forcer_ocr=True)
        self.assertEqual(page["source"], "ocr")
        self.assertEqual(len(self.appels), 1)

    def test_page_mixte(self):
        """T3 : sans texte avec image : ocr ; sans texte ni image : vide, sans erreur."""
        chemin = self.pdf([(TEXTE_NATIF, True), ([], True), ([], False)])
        natif = self.extraire(chemin, 1)
        self.assertEqual(natif["source"], "texte")
        self.assertEqual(self.appels, [])

        scan = self.extraire(chemin, 2)
        self.assertEqual(scan["source"], "ocr")
        self.assertAlmostEqual(scan["confiance"], 0.87, places=3)
        self.assertEqual(len(self.appels), 1)
        self.assertEqual(self.rendus, [(chemin, 2, 300)])

        vide = self.extraire(chemin, 3)
        self.assertEqual((vide["source"], vide["texte"], vide["confiance"], vide["mots"]), ("vide", "", None, 0))
        self.assertEqual(len(self.appels), 1)   # aucun appel de plus
        self.assertEqual(vide["numero"], 3)

        # Un TIFF a plusieurs cadres : numero compte les cadres.
        from PIL import Image
        tiff = os.path.join(self.d, "deux.tiff")
        Image.new("L", (30, 20), 255).save(tiff, save_all=True, append_images=[Image.new("L", (40, 25), 0)])
        taille = {}

        def executer(args, *, delai, arreter=None):
            with Image.open(args[1]) as im:
                taille["t"] = im.size
            return 0, tsv_exemple().encode("utf-8"), b""

        with mock.patch.object(ocr, "executer", executer):
            page = ocr.extraire_page(tiff, 2, REGLAGES, exe=EXE)
        self.assertEqual(page["numero"], 2)
        self.assertEqual(taille["t"], (40, 25))
        with mock.patch.object(ocr, "executer", executer), self.assertRaises(ocr.ErreurOcr) as c:
            ocr.extraire_page(tiff, 3, REGLAGES, exe=EXE)
        self.assertEqual(c.exception.code, "illisible")

    def test_normalisation_natif(self):
        n = ocr._normaliser_natif
        self.assertEqual(n("a   b\t\tc  \n"), "a b c")
        self.assertEqual(n("une expé-\nrience réussie"), "une expérience réussie")
        self.assertEqual(n("Jean-\nPaul et 1990-\n2000"), "Jean-\nPaul et 1990-\n2000")   # pas de recollage hasardeux
        self.assertEqual(n("a\n\n\n\n\nb\r\nc"), "a\n\nb\nc")
        self.assertEqual(n("e\u0301te\u0301"), "été")                                       # NFC
        self.assertEqual(n("avant\u00a0: après"), "avant\u00a0: après")                     # l'espace insecable reste
        self.assertEqual(n("a\x00b"), "ab")
        self.assertEqual(n(""), "")


class ErreursDePage(Doublures):
    def test_erreurs_lisibles(self):
        from PIL import Image
        image = os.path.join(self.d, "a.png")
        Image.new("L", (50, 50), 255).save(image)

        # Echec du moteur : illisible, avec le numero de page, sans trace technique ni code de retour.
        self.code = 1
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.extraire(image)
        e = c.exception
        self.assertEqual(e.code, "illisible")
        self.assertIsInstance(e, ms.Erreur)
        self.assertEqual(str(e), ocr.MESSAGES["illisible"].format(n=1))
        self.assertIn("La page 1", str(e))
        for interdit in ("Traceback", "tesseract", "code", "{n}"):
            self.assertNotIn(interdit, str(e))
        self.assertFalse(os.path.exists(self.images[-1]))   # l'image temporaire est supprimee quand meme
        self.assertTrue(os.path.isfile(ms.ERREURS))          # le detail va dans erreurs.txt

        # Moteur absent, puis langue manquante : aucun appel, jamais -l "".
        self.appels.clear()
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.extraire(image, exe="")
        self.assertEqual((c.exception.code, str(c.exception)), ("moteur_absent", ocr.MESSAGES["moteur_absent"]))
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.extraire(image, 1, dict(REGLAGES, langues=""))
        self.assertEqual((c.exception.code, str(c.exception)), ("langue_manquante", ocr.MESSAGES["langue_manquante"]))
        self.assertEqual(self.appels, [])

        # Annulation : ms.Annule, pas une erreur de page.
        self.code = -1
        with self.assertRaises(ms.Annule):
            self.extraire(image, arreter=lambda: True)

        # Delai ecoule sans demande d'arret : page illisible.
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.extraire(image, arreter=lambda: False)
        self.assertEqual(c.exception.code, "illisible")

        # arreter est transmis a executer.
        marque = lambda: False
        self.code = 0
        self.extraire(image, arreter=marque)
        self.assertIs(self.appels[-1][2], marque)

    def test_pdf_protege_et_corrompu(self):
        from pypdf import PdfWriter
        w = PdfWriter()
        w.add_blank_page(200, 200)
        w.encrypt("secret", algorithm="RC4-128")
        protege = os.path.join(self.d, "protege.pdf")
        with open(protege, "wb") as f:
            w.write(f)
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.extraire(protege)
        self.assertEqual((c.exception.code, str(c.exception)), ("protege", ocr.MESSAGES["protege"]))

        abime = os.path.join(self.d, "abime.pdf")
        with open(abime, "wb") as f:
            f.write(b"%PDF-1.4\nce n'est pas un pdf \x00\x01\x02")
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.extraire(abime)
        self.assertEqual((c.exception.code, str(c.exception)), ("corrompu", ocr.MESSAGES["corrompu"]))
        self.assertEqual(self.appels, [])

        absent = os.path.join(self.d, "nulle-part.pdf")
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.extraire(absent)
        self.assertEqual(c.exception.code, "corrompu")

    def test_page_hors_borne(self):
        chemin = self.pdf([(TEXTE_NATIF, False)])
        for n in (0, 2, -1):
            with self.assertRaises(ocr.ErreurOcr) as c:
                self.extraire(chemin, n)
            self.assertEqual(c.exception.code, "illisible")

    def test_rendre_page_sans_pypdfium2(self):
        """Import paresseux (D11) : sans pypdfium2, rendre_page d'un PDF leve illisible, rien d'autre."""
        chemin = self.pdf([([], True)])
        with mock.patch.dict(sys.modules, {"pypdfium2": None}), self.assertRaises(ocr.ErreurOcr) as c:
            ocr.rendre_page(chemin, 1, 150)
        self.assertEqual(c.exception.code, "illisible")
        self.assertIn("La page 1", str(c.exception))

    def test_rendre_page_image(self):
        """rendre_page d'une image isolee : niveaux de gris, sans pypdfium2."""
        from PIL import Image
        image = os.path.join(self.d, "couleur.png")
        Image.new("RGB", (40, 30), (200, 10, 10)).save(image)
        rendu = ocr.rendre_page(image, 1, 300)
        self.assertEqual((rendu.mode, rendu.size), ("L", (40, 30)))

    def test_import_sans_pypdfium2_ni_reseau(self):
        """ocr.py n'importe pypdfium2 qu'a l'usage et n'appelle ni urllib ni socket (invariant 6)."""
        with open(ocr.__file__, encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("urllib", source)
        self.assertNotIn("socket", source)
        self.assertNotIn("\nimport pypdfium2", source)
        self.assertNotIn("\nfrom pypdfium2", source)


class MarkdownDocument(Doublures):
    PAGES = [
        {"numero": 1, "source": "texte", "texte": "Texte natif un.", "confiance": None, "mots": 3, "boites": None},
        {"numero": 2, "source": "ocr", "texte": "Texte reconnu bien.", "confiance": 0.90, "mots": 10, "boites": None},
        {"numero": 3, "source": "ocr", "texte": "Bruit", "confiance": 0.60, "mots": 10, "boites": None},
        {"numero": 4, "source": "vide", "texte": "", "confiance": None, "mots": 0, "boites": None},
    ]

    def ecrire(self, pages=None, **kw):
        sortie = os.path.join(self.d, "Textes", "Cours A", "Section 1", "article.pdf.md")
        kw.setdefault("date", "2026-11-07T18:30:00")
        kw.setdefault("illisibles", [5])
        ok = ocr.ecrire_document_md(sortie, "Cours A/Section 1/article.pdf", pages or self.PAGES, REGLAGES, **kw)
        return sortie, ok

    def lire(self, chemin):
        with open(chemin, encoding="utf-8") as f:
            return f.read()

    def test_forme_du_markdown(self):
        sortie, ok = self.ecrire()
        self.assertTrue(ok)
        t = self.lire(sortie)
        self.assertTrue(t.startswith('---\nsource: "Cours A/Section 1/article.pdf"\ncours: "Cours A"\nsection: "Section 1"\n'))
        for ligne in ('pages: 5', 'extraction: "mixte"', 'langues: "fra+eng"', 'confiance: 0.75',
                      'moteur: "Tesseract 5.5.3"', 'genere: "2026-11-07T18:30:00"',
                      'moodlesync: "régénéré à chaque passage, supprime cette ligne pour garder le fichier tel quel"'):
            self.assertIn("\n" + ligne + "\n", t)
        corps = t.split("\n---\n", 1)[1]
        self.assertTrue(corps.lstrip().startswith("# article.pdf"))
        self.assertIn("> Source : Cours A / Section 1 / article.pdf", corps)
        self.assertIn("> 5 pages, dont 2 scannées. Confiance moyenne : 0,75.", corps)
        for n in range(1, 6):
            self.assertIn(f"<!-- page {n} -->", corps)
        self.assertLess(corps.index("<!-- page 1 -->"), corps.index("<!-- page 2 -->"))
        self.assertIn("Texte natif un.", corps)
        self.assertIn(ocr.MESSAGES["illisible"].format(n=5), corps)
        verifier = corps.split("## Pages à vérifier\n", 1)[1]
        self.assertEqual(verifier.strip().splitlines(),
                         ["- page 3 : confiance 0,60", "- page 4 : aucun texte détecté", "- page 5 : page illisible"])
        # Aucun chemin absolu, aucun tiret long, pas de fichier temporaire.
        self.assertNotIn(self.d, t)
        self.assertNotIn("\u2014", t)
        self.assertNotIn("\u2013", t)
        self.assertEqual(os.listdir(os.path.dirname(sortie)), ["article.pdf.md"])

    def test_document_natif_sans_page_a_verifier(self):
        pages = self.PAGES[:1] + [{"numero": 2, "source": "texte", "texte": "Deux.", "confiance": None, "mots": 1, "boites": None}]
        sortie, _ = self.ecrire(pages, illisibles=[])
        t = self.lire(sortie)
        self.assertIn('extraction: "texte"', t)
        self.assertNotIn("Pages à vérifier", t)
        self.assertNotIn("langues:", t)
        self.assertNotIn("confiance:", t)
        self.assertIn("> 2 pages.", t)

    def test_sortie_editee_conservee(self):
        """T7 : un .md sans la cle moodlesync n'est pas reecrit ; avec la cle, il est regenere."""
        sortie, _ = self.ecrire()
        avec_cle = self.lire(sortie)
        # Avec la cle : regenere (contenu different).
        nouvelles = [dict(self.PAGES[0], texte="Texte natif modifie.")]
        sortie, ok = self.ecrire(nouvelles, illisibles=[])
        self.assertTrue(ok)
        self.assertIn("Texte natif modifie.", self.lire(sortie))
        self.assertNotEqual(self.lire(sortie), avec_cle)

        # Sans la cle (l'utilisateur l'a retiree) : conserve octet pour octet.
        edite = "\n".join(l for l in self.lire(sortie).split("\n") if not l.startswith("moodlesync:")) + "\nMa note.\n"
        with open(sortie, "w", encoding="utf-8", newline="") as f:
            f.write(edite)
        sortie, ok = self.ecrire()
        self.assertFalse(ok)
        self.assertEqual(self.lire(sortie), edite)

        # Un fichier sans front matter, ou illisible en UTF-8, n'est jamais reecrit non plus.
        for contenu in (b"Mes notes a moi\n", b"\xff\xfe\x00 binaire"):
            with open(sortie, "wb") as f:
                f.write(contenu)
            self.assertFalse(self.ecrire()[1])
            with open(sortie, "rb") as f:
                self.assertEqual(f.read(), contenu)

        # La cle hors du front matter ne compte pas.
        piege = "Ma note\nmoodlesync: \"x\"\n---\n"
        with open(sortie, "w", encoding="utf-8", newline="") as f:
            f.write(piege)
        self.assertFalse(self.ecrire()[1])

    def test_ecriture_atomique(self):
        sortie, _ = self.ecrire()
        avant = self.lire(sortie)
        with mock.patch.object(ocr.os, "replace", side_effect=PermissionError("verrouille")):
            with self.assertRaises(OSError):
                self.ecrire([dict(self.PAGES[0], texte="Autre.")], illisibles=[])
        self.assertEqual(self.lire(sortie), avant)
        self.assertEqual(os.listdir(os.path.dirname(sortie)), ["article.pdf.md"])

    def test_front_matter_non_ferme(self):
        """Ecart 45 : la cle moodlesync ne compte que dans un front matter ferme par un `---`."""
        sortie, _ = self.ecrire()
        for contenu in ('---\nsource: "x"\nmoodlesync: "y"\nMes notes sans fermeture\n',
                        '---\r\nsource: "x"\r\nmoodlesync: "y"\r\n'):
            with open(sortie, "w", encoding="utf-8", newline="") as f:
                f.write(contenu)
            self.assertFalse(ocr._regenerable(sortie))
            self.assertFalse(self.ecrire()[1])
            with open(sortie, encoding="utf-8", newline="") as f:
                self.assertEqual(f.read(), contenu)
        # Ferme, avec la cle : regenere ; ferme, sans la cle : conserve.
        with open(sortie, "w", encoding="utf-8", newline="") as f:
            f.write('---\nmoodlesync: "y"\n---\nTexte\n')
        self.assertTrue(ocr._regenerable(sortie))
        with open(sortie, "w", encoding="utf-8", newline="") as f:
            f.write('---\nsource: "x"\n---\nmoodlesync: "y"\n')
        self.assertFalse(ocr._regenerable(sortie))


# ---------------------------------------------------------------------------------------------
# Tache C3 : cache, empreinte, reprise par page, file, document entier.
# ---------------------------------------------------------------------------------------------
BLOC_MOTEUR = {"present": True, "version": "5.5.3", "source": "registre", "exe": EXE,
               "langues": ["eng", "fra", "osd"], "langues_effectives": "fra+eng", "repli": False,
               "message": "", "tessdata": "", "majeure": 5}
REGLAGES_CLES = {"langues": "fra+eng", "dpi": 300, "psm": 3, "moteur": "5.5.3"}
SCAN = ([], True)       # page sans texte avec une image : reconnue
BLANC = ([], False)     # page sans texte ni image : vide
NATIF = (TEXTE_NATIF, False)


def octets(chemin):
    with open(chemin, "rb") as f:
        return f.read()


class DocumentsC3(Doublures):
    """Un dossier de rangement `coffre` et un extracteur de document qui compte aussi les detections."""

    def setUp(self):
        super().setUp()
        self.dest = os.path.join(self.d, "coffre")
        os.makedirs(self.dest)
        self.detections = 0
        self.bloc = dict(BLOC_MOTEUR)

    def detecter(self, cfg):
        self.detections += 1
        return self.bloc

    def doublures(self):
        pile = [mock.patch.object(ocr, "detecter", self.detecter),
                mock.patch.object(ocr, "executer", self.executer),
                mock.patch.object(ocr, "rendre_page", lambda *a: self.rendre(*a))]
        return pile

    def avec(self, fonction, *args, **kw):
        pile = self.doublures()
        for p in pile:
            p.start()
        try:
            return fonction(*args, **kw)
        finally:
            for p in reversed(pile):
                p.stop()

    def ranger(self, rel, pages):
        chemin = os.path.join(self.dest, *rel.split("/"))
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(pdf_minimal(pages))
        return chemin

    def extraire_doc(self, rel, cfg=None, **kw):
        return self.avec(ocr.extraire_document, self.dest, rel, cfg if cfg is not None else {}, **kw)

    def fichier_ocr(self, *parties):
        return os.path.join(self.dest, ocr.CACHE, *parties)

    def lire_json(self, chemin):
        with open(chemin, "rb") as f:
            return json.loads(f.read().decode("utf-8"))

    def md(self, rel):
        with open(os.path.join(self.dest, "Textes", *rel.split("/")) + ".md", encoding="utf-8") as f:
            return f.read()


class ReprisePage(DocumentsC3):
    def test_reprise_apres_arret(self):
        """T5 : annulation apres la page 3 de 6 ; relance : les pages 1 a 3 ne sont pas refaites."""
        rel = "Cours A/Section 1/scan.pdf"
        self.ranger(rel, [SCAN] * 6)
        evenements = []
        with self.assertRaises(ms.Annule):
            self.extraire_doc(rel, progres=evenements.append, arreter=lambda: len(self.appels) >= 3)
        self.assertEqual(len(self.appels), 3)
        self.assertEqual([r[1] for r in self.rendus], [1, 2, 3])
        self.assertEqual(evenements, [{"document": rel, "page": n, "pages": 6} for n in (1, 2, 3)])

        # Le fichier de reprise est coherent (2.4) ; ni cache ni Markdown avant la fin du document.
        dossier = self.fichier_ocr("pages")
        noms = os.listdir(dossier)
        self.assertEqual(len(noms), 1)
        reprise = self.lire_json(os.path.join(dossier, noms[0]))
        empreinte = "sha256:" + hashlib.sha256(octets(os.path.join(self.dest, "Cours A", "Section 1", "scan.pdf"))).hexdigest()
        self.assertEqual(noms[0], empreinte.split(":")[1] + ".json")
        self.assertEqual((reprise["version"], reprise["empreinte"], reprise["pages"]), (1, empreinte, 6))
        self.assertEqual(reprise["reglages"], REGLAGES_CLES)
        self.assertEqual(sorted(reprise["faites"]), ["1", "2", "3"])
        self.assertEqual(reprise["faites"]["2"]["source"], "ocr")
        self.assertNotIn("boites", reprise["faites"]["2"])
        self.assertFalse(os.path.exists(self.fichier_ocr("cache.json")))
        self.assertFalse(os.path.exists(os.path.join(self.dest, "Textes")))

        # Relance : seules les pages 4 a 6 sont faites, le fichier de reprise disparait a la fin.
        entree = self.extraire_doc(rel)
        self.assertEqual(len(self.appels), 6)
        self.assertEqual(sorted(r[1] for r in self.rendus), [1, 2, 3, 4, 5, 6])
        self.assertEqual(os.listdir(dossier), [])
        self.assertEqual((entree["pages"], entree["pages_ocr"], entree["numeros_ocr"]), (6, 6, [1, 2, 3, 4, 5, 6]))
        self.assertEqual(self.lire_json(self.fichier_ocr("cache.json"))["documents"][rel]["empreinte"], empreinte)
        self.assertIn("<!-- page 6 -->", self.md(rel))

    def test_reprise_ignoree_si_reglages_ou_empreinte_changent(self):
        rel = "scan.pdf"
        self.ranger(rel, [SCAN] * 3)
        with self.assertRaises(ms.Annule):
            self.extraire_doc(rel, arreter=lambda: len(self.appels) >= 2)
        self.assertEqual(len(self.appels), 2)
        # Autre dpi : le fichier de reprise est ignore, le document repart de zero.
        self.extraire_doc(rel, {"ocr_dpi": 200})
        self.assertEqual(len(self.appels), 5)

        # Autre empreinte dans le fichier de reprise : meme chose.
        avant = len(self.appels)
        with self.assertRaises(ms.Annule):
            self.extraire_doc(rel, {"ocr_dpi": 250}, arreter=lambda: len(self.appels) >= avant + 1)
        dossier = self.fichier_ocr("pages")
        reprise = os.path.join(dossier, os.listdir(dossier)[0])
        donnees = self.lire_json(reprise)
        donnees["empreinte"] = "sha256:autre"
        with open(reprise, "w", encoding="utf-8") as f:
            json.dump(donnees, f)
        self.extraire_doc(rel, {"ocr_dpi": 250})
        self.assertEqual(len(self.appels), avant + 1 + 3)

        # Autre nombre de pages : meme chose.
        page = {"source": "ocr", "texte": "t", "confiance": 0.9, "mots": 1}
        ocr._sauver_reprise(self.dest, "sha256:x", REGLAGES_CLES, 9, {1: page})
        self.assertEqual(ocr._charger_reprise(self.dest, "sha256:x", REGLAGES_CLES, 9), {1: page})
        self.assertEqual(ocr._charger_reprise(self.dest, "sha256:x", REGLAGES_CLES, 3), {})
        self.assertEqual(ocr._charger_reprise(self.dest, "sha256:x", dict(REGLAGES_CLES, psm=6), 9), {})
        # Boites demandees (mode remplacer) : une page reconnue sans boites est refaite.
        self.assertEqual(ocr._charger_reprise(self.dest, "sha256:x", REGLAGES_CLES, 9, avec_boites=True), {})

    def test_attendre_et_progres(self):
        rel = "scan.pdf"
        self.ranger(rel, [SCAN] * 3)
        attentes, evenements = [], []
        self.extraire_doc(rel, attendre=lambda: attentes.append(len(self.appels)), progres=evenements.append)
        self.assertEqual(attentes, [1, 2])   # entre deux pages, pas avant la premiere
        self.assertEqual([e["page"] for e in evenements], [1, 2, 3])

    def test_detection_une_fois(self):
        """Ecart 35 : le moteur est detecte une seule fois par document."""
        self.ranger("scan.pdf", [SCAN] * 3)
        self.extraire_doc("scan.pdf")
        self.assertEqual(self.detections, 1)


class CacheEtDeplacement(DocumentsC3):
    def test_cache_et_deplacement(self):
        """T6 : inchange, zero appel ; reglage change, seul ce document est refait ; deplace, retrouve par identite."""
        a, b = "Cours A/a.pdf", "Cours A/b.pdf"
        self.ranger(a, [SCAN] * 2)
        self.ranger(b, [SCAN] * 3)
        self.extraire_doc(a)
        self.extraire_doc(b, {"ocr_dpi": 200})
        self.assertEqual(len(self.appels), 5)

        # Inchange : zero appel, meme entree.
        entree_a = self.extraire_doc(a)
        self.assertEqual(len(self.appels), 5)
        # b a ete fait avec un autre dpi : il est refait, a ne l'est pas.
        self.extraire_doc(b)
        self.assertEqual(len(self.appels), 8)
        self.extraire_doc(a)
        self.extraire_doc(b)
        self.assertEqual(len(self.appels), 8)
        cache = ocr.charger_cache(self.dest)
        self.assertEqual({cache["documents"][k]["dpi"] for k in (a, b)}, {300})

        # entree_valide : les quatre reglages du cache, ni oem ni tessdata (ecart 7).
        self.assertTrue(ocr.entree_valide(entree_a, entree_a["empreinte"], REGLAGES_CLES))
        self.assertTrue(ocr.entree_valide(entree_a, entree_a["empreinte"], dict(REGLAGES_CLES, oem=2, tessdata="D:\\autre")))
        for cle, valeur in (("langues", "fra"), ("dpi", 200), ("psm", 6), ("moteur", "5.4.0")):
            self.assertFalse(ocr.entree_valide(entree_a, entree_a["empreinte"], dict(REGLAGES_CLES, **{cle: valeur})), cle)
        self.assertFalse(ocr.entree_valide(entree_a, "sha256:autre", REGLAGES_CLES))
        self.assertFalse(ocr.entree_valide(dict(entree_a, etat="erreur"), entree_a["empreinte"], REGLAGES_CLES))
        self.assertFalse(ocr.entree_valide({}, entree_a["empreinte"], REGLAGES_CLES))

        # Un reglage change (langue, psm, moteur) refait le document.
        avant = len(self.appels)
        self.extraire_doc(a, {"ocr_psm": 6})
        self.assertEqual(len(self.appels), avant + 2)
        self.bloc = dict(BLOC_MOTEUR, version="5.6.0")
        self.extraire_doc(a, {"ocr_psm": 6})
        self.assertEqual(len(self.appels), avant + 4)
        self.bloc = dict(BLOC_MOTEUR, version="5.6.0", langues_effectives="fra")
        self.extraire_doc(a, {"ocr_psm": 6})
        self.assertEqual(len(self.appels), avant + 6)

        # Deplace : retrouve par identite, jamais par la seule taille ; le chemin prime.
        self.bloc = dict(BLOC_MOTEUR)
        cache = ocr.charger_cache(self.dest)
        entree_b = cache["documents"][b]
        os.makedirs(os.path.join(self.dest, "Cours B"))
        os.replace(os.path.join(self.dest, "Cours A", "b.pdf"), os.path.join(self.dest, "Cours B", "renomme.pdf"))
        trouve = ocr.trouver_entree(cache, "Cours B/renomme.pdf", entree_b["empreinte"], entree_b["taille"])
        self.assertEqual(trouve[0], b)
        self.assertEqual(trouve[1], entree_b)
        self.assertIsNone(ocr.trouver_entree(cache, "Cours B/renomme.pdf", "sha256:autre", entree_b["taille"]))
        self.assertIsNone(ocr.trouver_entree(cache, "Cours B/renomme.pdf", entree_b["empreinte"], entree_b["taille"] + 1))
        self.assertEqual(ocr.trouver_entree(cache, "Cours A\\a.pdf", "sha256:autre", 1)[0], a)   # par chemin, separateur du systeme
        self.assertEqual(ocr.trouver_entree(cache, "Cours A/b.pdf", "sha256:autre", 1)[0], b)

    def test_deplacement_garde_l_ancienne_entree(self):
        a = "Cours A/a.pdf"
        self.ranger(a, [SCAN] * 2)
        self.extraire_doc(a)
        cache = ocr.charger_cache(self.dest)
        cache["documents"][a]["verifie"] = True
        ocr.sauver_cache(self.dest, cache)
        os.makedirs(os.path.join(self.dest, "Cours B"))
        os.replace(os.path.join(self.dest, "Cours A", "a.pdf"), os.path.join(self.dest, "Cours B", "a.pdf"))
        nouvelle = self.extraire_doc("Cours B/a.pdf")
        cache = ocr.charger_cache(self.dest)
        self.assertEqual(sorted(cache["documents"]), [a, "Cours B/a.pdf"])   # l'ancienne entree reste : orphelin, rien n'est supprime
        self.assertTrue(nouvelle["verifie"])
        self.assertEqual(nouvelle["sortie"], "Textes/Cours B/a.pdf.md")
        self.assertEqual(cache["documents"][a]["sortie"], "Textes/Cours A/a.pdf.md")
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "Textes", "Cours A", "a.pdf.md")))

    def test_copie_n_est_pas_un_deplacement(self):
        a = "Cours A/a.pdf"
        chemin = self.ranger(a, [SCAN] * 2)
        self.extraire_doc(a)
        os.makedirs(os.path.join(self.dest, "Cours B"))
        with open(chemin, "rb") as f, open(os.path.join(self.dest, "Cours B", "copie.pdf"), "wb") as g:
            g.write(f.read())
        cache = ocr.charger_cache(self.dest)
        cache["documents"][a]["verifie"] = True
        ocr.sauver_cache(self.dest, cache)
        self.assertFalse(self.extraire_doc("Cours B/copie.pdf")["verifie"])

    def test_md_supprime_est_refait(self):
        rel = "scan.pdf"
        self.ranger(rel, [SCAN] * 2)
        self.extraire_doc(rel)
        os.remove(os.path.join(self.dest, "Textes", "scan.pdf.md"))
        self.extraire_doc(rel)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "Textes", "scan.pdf.md")))

    def test_refaire_ignore_le_cache(self):
        rel = "scan.pdf"
        self.ranger(rel, [SCAN] * 2)
        self.extraire_doc(rel)
        self.extraire_doc(rel, refaire=True)
        self.assertEqual(len(self.appels), 4)


class FichiersJson(DocumentsC3):
    def test_cache_ecriture_et_lecture(self):
        self.assertEqual(ocr.charger_cache(self.dest), {"version": 1, "documents": {}})
        cache = {"version": 1, "documents": {"Cours é/é.pdf": {"empreinte": "sha256:x", "taille": 3}}}
        ocr.sauver_cache(self.dest, cache)
        brut = octets(self.fichier_ocr("cache.json"))
        self.assertFalse(brut.startswith(b"\xef\xbb\xbf"))
        self.assertIn("Cours é".encode("utf-8"), brut)
        self.assertEqual(os.listdir(self.fichier_ocr()), ["cache.json"])
        self.assertEqual(ocr.charger_cache(self.dest), cache)
        # Illisible : traite comme absent.
        with open(self.fichier_ocr("cache.json"), "wb") as f:
            f.write(b"{pas du json")
        self.assertEqual(ocr.charger_cache(self.dest), {"version": 1, "documents": {}})

    def test_version_superieure_jamais_reecrite(self):
        """Contrat 1 : une version superieure est traitee comme absente et le fichier n'est jamais reecrit."""
        os.makedirs(self.fichier_ocr())
        contenus = {"cache.json": {"version": 2, "documents": {"x": {"empreinte": "sha256:x"}}},
                    "file.json": {"version": 2, "etat": "en_cours", "taches": [{"chemin": "x"}]}}
        for nom, contenu in contenus.items():
            with open(self.fichier_ocr(nom), "w", encoding="utf-8") as f:
                json.dump(contenu, f)
        avant = {nom: octets(self.fichier_ocr(nom)) for nom in contenus}
        self.assertEqual(ocr.charger_cache(self.dest), {"version": 1, "documents": {}})
        self.assertEqual(ocr.charger_file(self.dest)["taches"], [])
        ocr.sauver_cache(self.dest, {"version": 1, "documents": {"y": {}}})
        ocr.sauver_file(self.dest, {"version": 1, "etat": "pause", "portee": "tout", "cree": "", "taches": []})
        # Le travail d'un document n'ecrit rien non plus dans ces fichiers.
        self.ranger("scan.pdf", [SCAN] * 2)
        entree = self.extraire_doc("scan.pdf")
        self.assertEqual(entree["pages_ocr"], 2)
        for nom in contenus:
            self.assertEqual(octets(self.fichier_ocr(nom)), avant[nom], nom)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "Textes", "scan.pdf.md")))

    def test_reprise_de_version_superieure_ignoree(self):
        self.ranger("scan.pdf", [SCAN] * 2)
        with self.assertRaises(ms.Annule):
            self.extraire_doc("scan.pdf", arreter=lambda: len(self.appels) >= 1)
        dossier = self.fichier_ocr("pages")
        chemin = os.path.join(dossier, os.listdir(dossier)[0])
        donnees = self.lire_json(chemin)
        donnees["version"] = 2
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(donnees, f)
        brut = octets(chemin)
        self.extraire_doc("scan.pdf")
        self.assertEqual(len(self.appels), 3)   # repart de zero : 1 + 2
        self.assertEqual(octets(chemin), brut)


class DocumentComplet(DocumentsC3):
    def test_aucun_reseau_extraction(self):
        """T22 : urlopen et socket.create_connection levent une erreur, un PDF natif est extrait quand meme."""
        self.bloc = dict(ocr.BLOC_ABSENT)   # pas de moteur : un PDF natif n'en a pas besoin
        rel = "Cours A/natif.pdf"
        self.ranger(rel, [NATIF, NATIF])
        with mock.patch.object(urllib.request, "urlopen", side_effect=OSError("reseau interdit")) as ouvrir, \
                mock.patch.object(socket, "create_connection", side_effect=OSError("reseau interdit")) as relier:
            entree = self.extraire_doc(rel)
        ouvrir.assert_not_called()
        relier.assert_not_called()
        self.assertEqual((entree["extraction"], entree["pages"], entree["pages_texte"], entree["pages_ocr"]), ("texte", 2, 2, 0))
        self.assertEqual(self.appels, [])
        self.assertEqual(self.rendus, [])
        self.assertIn("Le plan de Marshall", self.md(rel))

    def test_forme_de_l_entree(self):
        rel = "Cours A/Section 1/mixte.pdf"
        chemin = self.ranger(rel, [NATIF, SCAN, BLANC])
        entree = self.extraire_doc(rel, {}, )
        self.assertEqual(set(entree), {"empreinte", "taille", "pages", "pages_texte", "pages_ocr", "numeros_ocr", "pages_vides",
                                       "extraction", "confiance", "langues", "dpi", "psm", "moteur", "sortie", "etat",
                                       "verifie", "date"})
        self.assertEqual(entree["empreinte"], "sha256:" + hashlib.sha256(octets(chemin)).hexdigest())
        self.assertEqual(entree["taille"], os.path.getsize(chemin))
        self.assertEqual((entree["pages"], entree["pages_texte"], entree["pages_ocr"], entree["pages_vides"]), (3, 1, 1, 1))
        self.assertEqual(entree["numeros_ocr"], [2])
        self.assertEqual(entree["extraction"], "mixte")
        self.assertEqual(entree["confiance"], 0.87)   # (0,90 + 0,80 + 0,70 + 1,00 + 0,95) / 5, valeur de tsv_exemple
        self.assertEqual((entree["langues"], entree["dpi"], entree["psm"], entree["moteur"]), ("fra+eng", 300, 3, "5.5.3"))
        self.assertEqual(entree["sortie"], "Textes/Cours A/Section 1/mixte.pdf.md")
        self.assertEqual((entree["etat"], entree["verifie"]), ("a_verifier", False))
        self.assertRegex(entree["date"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")
        self.assertEqual(entree["pages_texte"] + entree["pages_ocr"] + entree["pages_vides"], entree["pages"])
        self.assertEqual(ocr.charger_cache(self.dest)["documents"][rel], entree)
        self.assertEqual(os.listdir(self.fichier_ocr("pages")), [])

    def test_document_sans_texte(self):
        """Ecart 50 : toutes les pages vides donnent extraction \"vide\", sans confiance."""
        rel = "Cours A/blanc.pdf"
        self.ranger(rel, [BLANC] * 3)
        entree = self.extraire_doc(rel)
        self.assertEqual(entree["extraction"], "vide")
        self.assertEqual((entree["pages"], entree["pages_texte"], entree["pages_ocr"], entree["pages_vides"]), (3, 0, 0, 3))
        self.assertIsNone(entree["confiance"])
        self.assertEqual(entree["numeros_ocr"], [])
        self.assertEqual(entree["etat"], "a_verifier")
        self.assertEqual(self.appels, [])
        t = self.md(rel)
        self.assertIn('\nextraction: "vide"\n', t)
        self.assertNotIn("\nconfiance:", t)
        verifier = t.split("## Pages à vérifier\n", 1)[1].strip().splitlines()
        self.assertEqual(verifier, [f"- page {n} : aucun texte détecté" for n in (1, 2, 3)])
        resume = ocr._resume_pages([{"numero": 1, "source": "vide", "texte": "", "confiance": None, "mots": 0}], 1)
        self.assertEqual((resume["extraction"], resume["confiance"]), ("vide", None))

    def test_page_illisible_comptee(self):
        rel = "scan.pdf"
        self.ranger(rel, [SCAN] * 3)

        def rendre(chemin, numero, dpi):
            if numero == 2:
                raise ocr.ErreurOcr("illisible", n=2)
            return Doublures.rendre(self, chemin, numero, dpi)
        self.rendre = rendre
        entree = self.extraire_doc(rel)
        self.assertEqual((entree["pages"], entree["pages_ocr"], entree["pages_vides"]), (3, 2, 1))
        self.assertEqual(entree["numeros_ocr"], [1, 3])
        self.assertEqual(entree["etat"], "a_verifier")
        self.assertIn(ocr.MESSAGES["illisible"].format(n=2), self.md(rel))

    def test_etat_derive_des_pages(self):
        """Ecart 8 : bon donne ok, la pire page l'emporte, une page sans texte rend le document a verifier."""
        def p(source, confiance):
            return {"numero": 1, "source": source, "texte": "x", "confiance": confiance, "mots": 5}
        self.assertEqual(ocr._etat_document([p("texte", None), p("ocr", 0.9)]), "ok")
        self.assertEqual(ocr._etat_document([p("ocr", 0.9), p("ocr", 0.8)]), "a_verifier")
        self.assertEqual(ocr._etat_document([p("ocr", 0.8), p("ocr", 0.5)]), "difficile")
        self.assertEqual(ocr._etat_document([p("texte", None), p("vide", None)]), "a_verifier")
        self.assertEqual(ocr._etat_document([p("texte", None)], illisibles=1), "a_verifier")
        self.assertEqual(ocr._etat_document([]), "a_verifier")

    def test_erreurs_de_document(self):
        self.ranger("gros.pdf", [SCAN])
        with open(os.path.join(self.dest, "gros.pdf"), "ab") as f:
            f.write(b"\n%" + b"x" * (1024 * 1024))
        with self.assertRaises(ocr.ErreurOcr) as e:
            self.extraire_doc("gros.pdf", {"ocr_max_mo": 1})
        self.assertEqual(e.exception.code, "trop_gros")
        self.assertIn("1 Mo", str(e.exception))
        self.assertEqual(self.appels, [])
        with self.assertRaises(ocr.ErreurOcr) as e:
            self.extraire_doc("absent.pdf")
        self.assertEqual(e.exception.code, "corrompu")
        with open(os.path.join(self.dest, "casse.pdf"), "wb") as f:
            f.write(b"pas un pdf")
        with self.assertRaises(ocr.ErreurOcr) as e:
            self.extraire_doc("casse.pdf")
        self.assertEqual(e.exception.code, "corrompu")
        self.ranger("lu.pdf", [SCAN])
        with mock.patch.object(ocr, "_sha256", side_effect=PermissionError("ouvert ailleurs")):
            with self.assertRaises(ocr.ErreurOcr) as e:
                self.extraire_doc("lu.pdf")
        self.assertEqual(e.exception.code, "verrouille")
        self.assertEqual(str(e.exception), "Ce fichier est ouvert dans un autre programme. Ferme-le et réessaie : rien n'a été modifié.")
        # Moteur absent : une page a reconnaitre leve moteur_absent, les pages faites restent.
        self.bloc = dict(ocr.BLOC_ABSENT)
        self.ranger("mixte.pdf", [NATIF, SCAN])
        with self.assertRaises(ocr.ErreurOcr) as e:
            self.extraire_doc("mixte.pdf")
        self.assertEqual(e.exception.code, "moteur_absent")
        self.assertEqual(len(os.listdir(self.fichier_ocr("pages"))), 1)
        self.assertFalse(os.path.exists(self.fichier_ocr("cache.json")))

    def test_dossier_de_sortie(self):
        self.ranger("Cours A/a.pdf", [NATIF])
        self.assertEqual(self.extraire_doc("Cours A/a.pdf", {"ocr_dossier": "Mes textes"})["sortie"], "Mes textes/Cours A/a.pdf.md")
        for faux in ("..", "../hors", "a/b", "C:\\x", "/abs", "", 5):
            sortie = self.extraire_doc("Cours A/a.pdf", {"ocr_dossier": faux, "ocr_dpi": 301 + len(str(faux))}, refaire=True)["sortie"]
            self.assertEqual(sortie, "Textes/Cours A/a.pdf.md", faux)
        hors = self.extraire_doc("Cours A/a.pdf", {"ocr_sortie_hors_coffre": True}, refaire=True)["sortie"]
        self.assertTrue(os.path.isabs(hors))
        self.assertTrue(os.path.isfile(hors))
        self.assertFalse(hors.startswith(self.dest))

    def test_pdf_cherchable_jamais_lu_comme_natif(self):
        """Invariant 3 : la couche invisible d'un PDF a notre marque n'est jamais lue comme du texte natif."""
        rel = "Cours A/cherchable.pdf"
        chemin = self.ranger(rel, [NATIF, NATIF])
        genere = {"type": "pdf_cherchable", "taille_source": 4321, "empreinte_source": "sha256:source",
                  "taille_fichier": os.path.getsize(chemin), "empreinte_fichier": "sha256:fichier",
                  "pages": 2, "date": "2026-11-07T18:30:00", "version": 1}
        ms.sauver_etat(self.dest, {"https://moodle.exemple.ch/a/cherchable.pdf": {"t": 1, "chemin": "Cours A\\cherchable.pdf", "genere": genere}})
        # Cache perdu : on ne sait pas quelles pages sont a nous, toutes sont reconnues (aucune lecture de la couche).
        entree = self.extraire_doc(rel)
        self.assertEqual(len(self.appels), 2)
        self.assertEqual((entree["empreinte"], entree["taille"]), ("sha256:source", 4321))
        self.assertEqual((entree["pages_texte"], entree["pages_ocr"], entree["numeros_ocr"]), (0, 2, [1, 2]))
        # Cache present (reglages periodiques) : seules les pages de numeros_ocr sont reconnues, la page 1 reste native.
        cache = ocr.charger_cache(self.dest)
        cache["documents"][rel].update(numeros_ocr=[2], pages_texte=1, pages_ocr=1, moteur="5.0.0")
        ocr.sauver_cache(self.dest, cache)
        del self.appels[:]
        entree = self.extraire_doc(rel)
        self.assertEqual(len(self.appels), 1)
        self.assertEqual((entree["pages_texte"], entree["pages_ocr"], entree["numeros_ocr"]), (1, 1, [2]))
        self.assertEqual(entree["empreinte"], "sha256:source")
        # Valide et inchange : zero appel, la source reste celle de `genere`.
        del self.appels[:]
        self.extraire_doc(rel)
        self.assertEqual(self.appels, [])
        # Le PDF lui-meme n'est jamais modifie.
        self.assertEqual(octets(chemin), pdf_minimal([NATIF, NATIF]))

    def test_traiter_document_sans_remplacement(self):
        self.ranger("natif.pdf", [NATIF])
        for mode in ({}, {"ocr_pdf": "aucun"}, {"ocr_pdf": "copie"}):
            resultat = self.avec(ocr.traiter_document, self.dest, "natif.pdf", mode)
            self.assertEqual(set(resultat), {"entree", "pdf", "message"})
            self.assertEqual((resultat["pdf"], resultat["message"]), ("aucun", ""))
            self.assertEqual(resultat["entree"]["pages_texte"], 1)


SOUS_TEXTES = "Cours A/Section 1/Textes/sous.pdf"


class FileDeTravail(DocumentsC3):
    def preparer(self):
        self.ranger("Cours A/Section 1/scan.pdf", [SCAN] * 2)
        self.ranger("Cours A/Section 1/natif.pdf", [NATIF])
        self.ranger("Cours A/Section 1/scan (ancienne version 2026-01-01).pdf", [SCAN])
        self.ranger("Cours B/gros.pdf", [SCAN])
        with open(os.path.join(self.dest, "Cours B", "gros.pdf"), "ab") as f:
            f.write(b"\n%" + b"x" * (1024 * 1024))
        self.ranger("Textes/Cours A/ancien.pdf", [SCAN])
        self.ranger(".moodlesync-ocr/cache.pdf", [SCAN])
        self.ranger("Cours A/Section 1/Textes/sous.pdf", [SCAN])
        with open(os.path.join(self.dest, "Cours A", "note.md"), "w", encoding="utf-8") as f:
            f.write("note")
        with open(os.path.join(self.dest, "Cours B", "casse.pdf"), "wb") as f:
            f.write(b"pas un pdf")
        from PIL import Image
        Image.new("L", (40, 40), 255).save(os.path.join(self.dest, "Cours B", "photo.png"))

    CFG = {"ocr_max_mo": 1, "cours": {"12": {"dossier": "Cours A"}}}

    def chemins(self, file):
        return [t["chemin"] for t in file["taches"]]

    def test_file_etat_au_chargement(self):
        vide = ocr.charger_file(self.dest)
        self.assertEqual(vide, {"version": 1, "etat": "inactive", "portee": "sans_texte", "cree": "", "taches": []})
        tache = {"chemin": "a.pdf", "etat": "en_cours", "priorite": 0, "pages": 4, "pages_faites": 2, "ajoute": "2026-11-07T18:00:00", "message": ""}
        ocr.sauver_file(self.dest, {"version": 1, "etat": "en_cours", "portee": "tout", "cree": "2026-11-07T18:00:00", "taches": [tache]})
        brut = octets(self.fichier_ocr("file.json"))
        self.assertFalse(brut.startswith(b"\xef\xbb\xbf"))
        charge = ocr.charger_file(self.dest)
        self.assertEqual(charge["etat"], "pause")   # aucune reprise automatique
        self.assertEqual(charge["portee"], "tout")
        self.assertEqual(charge["taches"][0]["etat"], "attente")
        self.assertEqual(charge["taches"][0]["pages_faites"], 2)
        # Le disque n'est pas modifie par le chargement.
        self.assertEqual(octets(self.fichier_ocr("file.json")), brut)

    def test_constituer_sans_texte(self):
        self.preparer()
        file = self.avec(ocr.constituer_file, self.dest, self.CFG, "sans_texte")
        # Le dossier « Textes » d'une section n'est pas exclu (3.3) ; celui qui est place directement dans dest, si.
        self.assertEqual(self.chemins(file), ["Cours A/Section 1/scan.pdf", SOUS_TEXTES, "Cours B/casse.pdf", "Cours B/photo.png"])
        self.assertEqual((file["version"], file["etat"], file["portee"]), (1, "inactive", "sans_texte"))
        self.assertRegex(file["cree"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")
        scan, _, casse, photo = file["taches"]
        self.assertEqual({k: scan[k] for k in ("etat", "priorite", "pages", "pages_faites", "message")},
                         {"etat": "attente", "priorite": 0, "pages": 2, "pages_faites": 0, "message": ""})
        self.assertRegex(scan["ajoute"], r"^\d{4}-\d\d-\d\dT")
        self.assertEqual(photo["pages"], 1)
        # Un PDF illisible n'est pas lance : tache ignoree, avec la phrase de la section 5.
        self.assertEqual((casse["etat"], casse["message"], casse["pages"]), ("ignore", ocr.MESSAGES["corrompu"], 0))
        self.assertEqual(ocr.charger_file(self.dest), file)   # ecrite sur disque, rien d'autre
        self.assertEqual(self.appels, [])
        self.assertEqual(self.detections, 1)

    def test_constituer_portees(self):
        self.preparer()
        tout = self.avec(ocr.constituer_file, self.dest, self.CFG, "tout")
        self.assertEqual(self.chemins(tout), ["Cours A/Section 1/natif.pdf", "Cours A/Section 1/scan.pdf", SOUS_TEXTES,
                                              "Cours B/casse.pdf", "Cours B/photo.png"])
        cours = self.avec(ocr.constituer_file, self.dest, self.CFG, "cours:12")
        self.assertEqual(self.chemins(cours), ["Cours A/Section 1/natif.pdf", "Cours A/Section 1/scan.pdf", SOUS_TEXTES])
        self.assertEqual(cours["portee"], "cours:12")
        self.assertEqual(self.chemins(self.avec(ocr.constituer_file, self.dest, self.CFG, "cours:99")), [])
        un = self.avec(ocr.constituer_file, self.dest, self.CFG, "document:Cours A/Section 1/natif.pdf")
        self.assertEqual(self.chemins(un), ["Cours A/Section 1/natif.pdf"])
        for refuse in ("document:Textes/Cours A/ancien.pdf", "document:Cours B/gros.pdf", "document:Cours A/note.md",
                       "document:Cours A/Section 1/scan (ancienne version 2026-01-01).pdf", "document:absent.pdf",
                       "document:../hors.pdf"):
            self.assertEqual(self.avec(ocr.constituer_file, self.dest, self.CFG, refuse)["taches"], [], refuse)
        # Un chemin n'apparait qu'une fois.
        self.assertEqual(len(set(self.chemins(tout))), len(tout["taches"]))

    def test_constituer_et_cache(self):
        self.preparer()
        self.extraire_doc("Cours A/Section 1/scan.pdf")
        self.extraire_doc("Cours A/Section 1/natif.pdf")
        sans = self.avec(ocr.constituer_file, self.dest, self.CFG, "sans_texte")
        self.assertEqual(self.chemins(sans), [SOUS_TEXTES, "Cours B/casse.pdf", "Cours B/photo.png"])
        tout = self.avec(ocr.constituer_file, self.dest, self.CFG, "tout")
        self.assertEqual(self.chemins(tout), [SOUS_TEXTES, "Cours B/casse.pdf", "Cours B/photo.png"])
        refaire = self.avec(ocr.constituer_file, self.dest, self.CFG, "tout", True)
        self.assertEqual(self.chemins(refaire), ["Cours A/Section 1/natif.pdf", "Cours A/Section 1/scan.pdf", SOUS_TEXTES,
                                                 "Cours B/casse.pdf", "Cours B/photo.png"])
        self.assertTrue(all(t.get("refaire") for t in refaire["taches"] if t["etat"] == "attente"))
        self.assertFalse(any("refaire" in t for t in tout["taches"]))
        # Un reglage change : le document n'est plus valide, il revient.
        apres = self.avec(ocr.constituer_file, self.dest, dict(self.CFG, ocr_dpi=200), "sans_texte")
        self.assertIn("Cours A/Section 1/scan.pdf", self.chemins(apres))
        self.assertNotIn("Cours A/Section 1/natif.pdf", self.chemins(apres))   # natif : pas besoin du moteur

    def test_mise_en_file_apres_sync(self):
        self.preparer()
        compte_rendu = {"a_preparer": ["Cours A/Section 1/scan.pdf", "Cours A/Section 1/natif.pdf", "Cours A/note.md",
                                       "Textes/Cours A/ancien.pdf", "absent.pdf", "Cours B/gros.pdf",
                                       "Cours A/Section 1/scan (ancienne version 2026-01-01).pdf"]}
        self.assertEqual(self.avec(ocr.mettre_en_file_apres_sync, self.dest, self.CFG, compte_rendu), 2)
        file = ocr.charger_file(self.dest)
        self.assertEqual(self.chemins(file), ["Cours A/Section 1/scan.pdf", "Cours A/Section 1/natif.pdf"])
        self.assertEqual((file["etat"], file["portee"]), ("inactive", "sans_texte"))
        self.assertEqual([t["pages"] for t in file["taches"]], [2, 1])
        # Deja en file : rien n'est ajoute ; une tache faite dont le fichier est republie revient en attente.
        self.assertEqual(self.avec(ocr.mettre_en_file_apres_sync, self.dest, self.CFG, compte_rendu), 0)
        file["taches"][0]["etat"] = "fait"
        file["taches"][0]["pages_faites"] = 2
        file["etat"] = "pause"
        ocr.sauver_file(self.dest, file)
        self.assertEqual(self.avec(ocr.mettre_en_file_apres_sync, self.dest, self.CFG, compte_rendu), 1)
        apres = ocr.charger_file(self.dest)
        self.assertEqual((apres["taches"][0]["etat"], apres["taches"][0]["pages_faites"]), ("attente", 0))
        self.assertEqual(apres["etat"], "pause")
        self.assertEqual(len(apres["taches"]), 2)
        self.assertEqual(self.avec(ocr.mettre_en_file_apres_sync, self.dest, self.CFG, {}), 0)


class ArchiverTexte(DocumentsC3):
    def test_archiver_texte(self):
        rel = "Cours A/article.pdf"
        self.ranger(rel, [NATIF])
        self.extraire_doc(rel)
        ancien = os.path.join(self.dest, "Textes", "Cours A", "article.pdf.md")
        self.assertTrue(os.path.isfile(ancien))
        nouveau = ocr.archiver_texte(self.dest, rel, 1760000000)
        self.assertTrue(os.path.isabs(nouveau))
        self.assertTrue(os.path.isfile(nouveau))
        self.assertFalse(os.path.exists(ancien))
        nom = os.path.basename(nouveau)
        self.assertTrue(nom.startswith("article.pdf (" + ms.T["ancienne"] + " ") and nom.endswith(").md"), nom)
        self.assertEqual(os.path.dirname(nouveau), os.path.dirname(ancien))
        # Plus de .md a ranger : rien a faire.
        self.assertIsNone(ocr.archiver_texte(self.dest, rel, 1760000000))
        self.assertIsNone(ocr.archiver_texte(self.dest, "inconnu.pdf", 1760000000))

    def test_archiver_texte_edite_a_la_main(self):
        rel = "article.pdf"
        self.ranger(rel, [NATIF])
        self.extraire_doc(rel)
        chemin = os.path.join(self.dest, "Textes", "article.pdf.md")
        with open(chemin, encoding="utf-8") as f:
            texte = f.read()
        edite = "\n".join(l for l in texte.split("\n") if not l.startswith("moodlesync:"))
        with open(chemin, "w", encoding="utf-8", newline="") as f:
            f.write(edite)
        self.assertIsNone(ocr.archiver_texte(self.dest, rel, 1760000000))
        with open(chemin, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), edite)
        # Front matter non ferme : meme garde (ecart 45).
        with open(chemin, "w", encoding="utf-8", newline="") as f:
            f.write('---\nmoodlesync: "x"\nMa note\n')
        self.assertIsNone(ocr.archiver_texte(self.dest, rel, 1760000000))
        self.assertTrue(os.path.isfile(chemin))


def _moteur_reel():
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return bool(ocr.detecter({})["present"])


class MoteurReel(unittest.TestCase):
    @unittest.skipUnless(_moteur_reel(), "Tesseract ou Pillow absent")
    def test_moteur_reel(self):
        """T29 : image Pillow avec quelques mots, vrai moteur : texte reconnu, confiance entre 0 et 1."""
        from PIL import Image, ImageDraw, ImageFont
        with tempfile.TemporaryDirectory() as d:
            image = os.path.join(d, "mots écrits.png")
            im = Image.new("L", (1400, 360), 255)
            dessin = ImageDraw.Draw(im)
            police = ImageFont.load_default(size=90)
            dessin.text((40, 40), "Bonjour le monde", fill=0, font=police)
            dessin.text((40, 190), "Politique sociale", fill=0, font=police)
            im.save(image, dpi=(300, 300))
            cfg = {}
            reglages = ocr.reglages_depuis(cfg)
            page = ocr.extraire_page(image, 1, reglages, exe=ocr.detecter(cfg)["exe"])
        self.assertEqual(page["source"], "ocr")
        minuscules = page["texte"].lower()
        self.assertIn("bonjour", minuscules)
        self.assertIn("monde", minuscules)
        self.assertIsNotNone(page["confiance"])
        self.assertGreater(page["confiance"], 0)
        self.assertLessEqual(page["confiance"], 1)
        self.assertGreaterEqual(page["mots"], 4)


if __name__ == "__main__":
    unittest.main()
