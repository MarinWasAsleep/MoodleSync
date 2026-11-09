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
from email.message import Message
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

    def rendre(self, chemin, numero, dpi, **kw):
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

    def test_rendre_page_fichier_temporaire(self):
        """Ecart 71 : le fichier temporaire <nom>.pdf.ocr.part est un PDF ; sans cela, D9 ne pourrait jamais rendre le
        fichier verifie et tout remplacement echouerait en verification avec un vrai pdfium."""
        from PIL import Image
        self.assertTrue(ocr._est_pdf("scan.pdf.ocr.part"))
        self.assertTrue(ocr._est_pdf(os.path.join("Cours", "scan.PDF")))
        self.assertFalse(ocr._est_pdf("scan.png"))
        self.assertFalse(ocr._est_pdf("scan.pdf.ocr"))
        appels = []

        def rendre_pdf(chemin, numero, dpi):
            appels.append((chemin, numero, dpi))
            return Image.new("L", (10, 10), 255)

        part = os.path.join(self.d, "scan.pdf.ocr.part")
        with mock.patch.object(ocr, "_rendre_pdf", rendre_pdf):
            rendu = ocr.rendre_page(part, 1, 150, preparer=False)
        self.assertEqual(appels, [(part, 1, 150)])
        self.assertEqual((rendu.mode, rendu.size), ("L", (10, 10)))

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
                mock.patch.object(ocr, "rendre_page", lambda *a, **kw: self.rendre(*a, **kw))]
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


# ---------------------------------------------------------------------------------------------
# Tache C4 : PDF cherchable (identite, marque, controle, superposition, verification, remplacement).
# ---------------------------------------------------------------------------------------------
URL_MOODLE = "https://moodle.exemple.ch/pluginfile.php/12/mod_resource/content/1/scan.pdf"
REL_C4 = "Cours A/Section 1/scan.pdf"
MARQUE_VALIDE = {"v": 1, "url": URL_MOODLE, "t": 1760000000, "taille_source": 1000,
                 "empreinte_source": "sha256:" + "0" * 64, "pages": 3}


def json_compact(donnees):
    return json.dumps(donnees, separators=(",", ":"), ensure_ascii=False)


def donnees_contenu(page):
    """Octets du flux /Contents d'une page dont /Contents est un flux unique (lecture brute, sans reserialisation)."""
    return page.raw_get("/Contents").get_object().get_data()


def pdf_riche():
    """Trois pages : un scan tourne de 90 degres avec un lien et un signet, un scan de 400 sur 300 avec une
    annotation, une page native."""
    from pypdf import PdfWriter
    from pypdf.annotations import Link, Text
    from pypdf.generic import RectangleObject
    w = PdfWriter(clone_from=io.BytesIO(pdf_minimal([SCAN, SCAN, NATIF])))
    w.pages[0].rotate(90)
    w.pages[1].mediabox = RectangleObject([0, 0, 400, 300])
    w.add_outline_item("Chapitre un", 0)
    w.add_annotation(0, Link(rect=(10, 10, 100, 40), url="https://exemple.ch"))
    w.add_annotation(1, Text(rect=(50, 50, 80, 80), text="note"))
    sortie = io.BytesIO()
    w.write(sortie)
    return sortie.getvalue()


def pdf_signe():
    """Un champ de signature numerique rempli (AcroForm, /FT /Sig, /V)."""
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, ByteStringObject, DictionaryObject, NameObject, NumberObject, TextStringObject
    w = PdfWriter(clone_from=io.BytesIO(pdf_minimal([SCAN])))
    valeur = DictionaryObject({NameObject("/Type"): NameObject("/Sig"), NameObject("/Filter"): NameObject("/Adobe.PPKLite"),
                               NameObject("/SubFilter"): NameObject("/adbe.pkcs7.detached"),
                               NameObject("/Contents"): ByteStringObject(b"\x00" * 16),
                               NameObject("/ByteRange"): ArrayObject([NumberObject(0)] * 4)})
    champ = DictionaryObject({NameObject("/FT"): NameObject("/Sig"), NameObject("/T"): TextStringObject("Signature1"),
                              NameObject("/V"): w._add_object(valeur)})
    w._root_object[NameObject("/AcroForm")] = DictionaryObject({NameObject("/Fields"): ArrayObject([w._add_object(champ)]),
                                                                NameObject("/SigFlags"): NumberObject(3)})
    sortie = io.BytesIO()
    w.write(sortie)
    return sortie.getvalue()


def pdf_chiffre(utilisateur, proprietaire=None):
    from pypdf import PdfWriter
    w = PdfWriter(clone_from=io.BytesIO(pdf_minimal([SCAN])))
    w.encrypt(utilisateur, owner_password=proprietaire, algorithm="RC4-128")
    sortie = io.BytesIO()
    w.write(sortie)
    return sortie.getvalue()


def pdf_avec_info(pages, info):
    from pypdf import PdfWriter
    w = PdfWriter(clone_from=io.BytesIO(pdf_minimal(pages)))
    w.add_metadata(info)
    sortie = io.BytesIO()
    w.write(sortie)
    return sortie.getvalue()


def tsv_dense(n_mots, graine=1):
    """TSV de n mots de huit lettres au hasard (incompressibles), 40 mots par ligne."""
    import random
    alea = random.Random(graine)
    lignes = [ENTETE_TSV]
    for i in range(n_mots):
        mot = "".join(alea.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(8))
        lignes.append(mot_tsv(1, 1, 1 + i // 40, 1 + i % 40, 100 + (i % 40) * 55, "90", mot, y=100 + (i // 40) * 30, l=50, h=24))
    return "\r\n".join(lignes) + "\r\n"


def tsv_assez_long():
    """Vingt mots de neuf lettres : la couche depasse SEUIL_TEXTE caracteres alphanumeriques."""
    lignes = [ENTETE_TSV] + [mot_tsv(1, 1, 1, i + 1, 100 + 60 * i, "90", "politique") for i in range(20)]
    return "\r\n".join(lignes) + "\r\n"


class IdentiteEtMarque(Doublures):
    def pdf_info(self, info, nom="marque.pdf"):
        chemin = os.path.join(self.d, nom)
        with open(chemin, "wb") as f:
            f.write(pdf_avec_info([NATIF], info))
        return chemin

    def test_identite(self):
        chemin = os.path.join(self.d, "é àç.bin")
        with open(chemin, "wb") as f:
            f.write(b"contenu du fichier" * 100000)
        voulu = "sha256:" + hashlib.sha256(b"contenu du fichier" * 100000).hexdigest()
        self.assertEqual(ocr.identite(chemin), {"taille": 18 * 100000, "empreinte": voulu})

    def test_identite_erreurs(self):
        with self.assertRaises(ocr.ErreurOcr) as c:
            ocr.identite(os.path.join(self.d, "nulle-part.pdf"))
        self.assertEqual(c.exception.code, "corrompu")
        chemin = self.pdf([NATIF])
        with mock.patch.object(ocr, "_sha256", side_effect=PermissionError("verrouille")):
            with self.assertRaises(ocr.ErreurOcr) as c:
                ocr.identite(chemin)
        self.assertEqual((c.exception.code, str(c.exception)), ("verrouille", ocr.MESSAGES["verrouille"]))

    def test_lire_marque_valide(self):
        chemin = self.pdf_info({"/MoodleSyncGenere": json_compact(MARQUE_VALIDE)})
        self.assertEqual(ocr.lire_marque(chemin), MARQUE_VALIDE)

    def test_lire_marque_absente_illisible_incomplete(self):
        incomplete = {k: v for k, v in MARQUE_VALIDE.items() if k != "pages"}
        cas = {
            "absente": self.pdf_info({"/Title": "Cours"}),
            "illisible": self.pdf_info({"/MoodleSyncGenere": "{pas du json"}),
            "pas_un_objet": self.pdf_info({"/MoodleSyncGenere": "[1, 2]"}),
            "incomplete": self.pdf_info({"/MoodleSyncGenere": json_compact(incomplete)}),
            "version_superieure": self.pdf_info({"/MoodleSyncGenere": json_compact(dict(MARQUE_VALIDE, v=2))}),
            "types_faux": self.pdf_info({"/MoodleSyncGenere": json_compact(dict(MARQUE_VALIDE, pages="trois"))}),
        }
        for nom, chemin in cas.items():
            with self.subTest(nom):
                self.assertIsNone(ocr.lire_marque(chemin))

    def test_marque_de_un_ko_ou_plus_refusee(self):
        """Ecart 87 : la borne de 1 Ko porte sur le texte de la marque (2.2), pas sur le PDF."""
        marque = dict(MARQUE_VALIDE, empreinte_source="x" * 1100)
        self.assertGreaterEqual(len(json_compact(marque).encode("utf-8")), 1024)
        self.assertIsNone(ocr.lire_marque(self.pdf_info({"/MoodleSyncGenere": json_compact(marque)})))

    def test_marque_sans_page_refusee(self):
        """Ecart 87 : `pages` vaut au moins 1 (2.2) ; zero ne designe aucun document."""
        for pages in (0, -1):
            with self.subTest(pages=pages):
                marque = json_compact(dict(MARQUE_VALIDE, pages=pages))
                self.assertIsNone(ocr.lire_marque(self.pdf_info({"/MoodleSyncGenere": marque})))

    def test_marque_booleen_refuse_comme_entier(self):
        """Ecart 87 : un booleen JSON (`true`) n'est pas un entier (2.2), meme si Python le range parmi les int."""
        for champ in ("v", "t", "taille_source", "pages"):
            with self.subTest(champ=champ):
                marque = json_compact(dict(MARQUE_VALIDE, **{champ: True}))
                self.assertIsNone(ocr.lire_marque(self.pdf_info({"/MoodleSyncGenere": marque})))

    def test_lire_marque_ne_leve_jamais(self):
        abime = os.path.join(self.d, "abime.pdf")
        with open(abime, "wb") as f:
            f.write(b"%PDF-1.4\nce n'est pas un pdf \x00\x01")
        protege = os.path.join(self.d, "protege.pdf")
        with open(protege, "wb") as f:
            f.write(pdf_chiffre("secret"))
        for chemin in (abime, protege, os.path.join(self.d, "nulle-part.pdf"), self.d, "", None):
            with self.subTest(str(chemin)):
                self.assertIsNone(ocr.lire_marque(chemin))


class ControlePdf(Doublures):
    def ecrire(self, donnees, nom="controle.pdf"):
        chemin = os.path.join(self.d, nom)
        with open(chemin, "wb") as f:
            f.write(donnees)
        return chemin

    def test_forme_du_controle(self):
        chemin = self.ecrire(pdf_riche())
        ctl = ocr.controler_pdf(chemin)
        self.assertEqual(set(ctl), {"pages", "protege", "signe", "lecture_seule", "numerique", "annotations", "liens",
                                    "signets", "dimensions", "marque"})
        self.assertEqual(ctl["pages"], 3)
        self.assertEqual(ctl["dimensions"], [[595, 842, 90], [400, 300, 0], [595, 842, 0]])
        self.assertEqual((ctl["annotations"], ctl["liens"], ctl["signets"]), (2, 1, 1))
        self.assertEqual((ctl["protege"], ctl["signe"], ctl["lecture_seule"], ctl["numerique"]), (False, False, False, False))
        self.assertIsNone(ctl["marque"])
        json.dumps(ctl)   # serialisable

    def test_numerique_et_marque(self):
        natif = self.ecrire(pdf_minimal([NATIF, NATIF]), "natif.pdf")
        self.assertTrue(ocr.controler_pdf(natif)["numerique"])
        marque = self.ecrire(pdf_avec_info([NATIF, NATIF], {"/MoodleSyncGenere": json_compact(MARQUE_VALIDE)}), "marque.pdf")
        ctl = ocr.controler_pdf(marque)
        self.assertFalse(ctl["numerique"])   # invariant 3 : un PDF a notre marque n'est jamais « numerique »
        self.assertEqual(ctl["marque"], MARQUE_VALIDE)
        # une marque illisible ne compte pas : le PDF natif reste numerique
        casse = self.ecrire(pdf_avec_info([NATIF], {"/MoodleSyncGenere": "{pas du json"}), "casse.pdf")
        self.assertTrue(ocr.controler_pdf(casse)["numerique"])
        # un scan n'est pas numerique
        self.assertFalse(ocr.controler_pdf(self.ecrire(pdf_minimal([SCAN]), "scan.pdf"))["numerique"])

    def test_signe_chiffre_protege(self):
        signe = ocr.controler_pdf(self.ecrire(pdf_signe(), "signe.pdf"))
        self.assertTrue(signe["signe"])
        self.assertFalse(signe["protege"])
        # mot de passe utilisateur vide : le PDF s'ouvre, mais il est chiffre donc en lecture seule pour nous
        ouvert = ocr.controler_pdf(self.ecrire(pdf_chiffre("", "proprio"), "ouvert.pdf"))
        self.assertTrue(ouvert["lecture_seule"])
        self.assertFalse(ouvert["protege"])
        self.assertEqual(ouvert["pages"], 1)
        # mot de passe non vide : protege, sans lever
        protege = ocr.controler_pdf(self.ecrire(pdf_chiffre("secret"), "protege.pdf"))
        self.assertTrue(protege["protege"])
        self.assertEqual(protege["pages"], 0)
        # fichier non modifiable pour le systeme (attribut lecture seule de Windows, droits sur macOS)
        simple = self.ecrire(pdf_minimal([SCAN]), "simple.pdf")
        with mock.patch.object(ocr.os, "access", return_value=False):
            self.assertTrue(ocr.controler_pdf(simple)["lecture_seule"])
        self.assertFalse(ocr.controler_pdf(simple)["lecture_seule"])

    def test_pdf_abime(self):
        abime = self.ecrire(b"%PDF-1.4\nce n'est pas un pdf \x00\x01\x02", "abime.pdf")
        with self.assertRaises(ocr.ErreurOcr) as c:
            ocr.controler_pdf(abime)
        self.assertEqual((c.exception.code, str(c.exception)), ("corrompu", ocr.MESSAGES["corrompu"]))
        with self.assertRaises(ocr.ErreurOcr) as c:
            ocr.controler_pdf(os.path.join(self.d, "nulle-part.pdf"))
        self.assertEqual(c.exception.code, "corrompu")


class PdfBase(DocumentsC3):
    """Un PDF de cours range dans `coffre`, avec son entree dans .moodlesync.json."""

    def setUp(self):
        super().setUp()
        self.rel = REL_C4
        self.cle_etat = URL_MOODLE
        self.chemin = os.path.join(self.dest, *self.rel.split("/"))
        self.pauses = []
        patch = mock.patch.object(ocr, "_pause", self.pauses.append)
        patch.start()
        self.addCleanup(patch.stop)

    def poser(self, donnees=None, pages=(SCAN, SCAN, SCAN), etat=True):
        os.makedirs(os.path.dirname(self.chemin), exist_ok=True)
        with open(self.chemin, "wb") as f:
            f.write(donnees if donnees is not None else pdf_minimal(list(pages)))
        if etat:
            self.ecrire_etat()
        return self.chemin

    def ecrire_etat(self, **entree):
        e = {"t": 1760000000, "chemin": self.rel.replace("/", os.sep)}
        e.update(entree)
        ms.sauver_etat(self.dest, {self.cle_etat: e, "_sections": {"12": "Section 1"}})

    def fabriquer(self, cfg=None, **kw):
        return self.avec(ocr.fabriquer_pdf_cherchable, self.dest, self.rel, cfg if cfg is not None else {}, **kw)

    def part(self):
        return self.chemin + ".ocr.part"

    def fichiers(self):
        trouves = []
        for racine, _, noms in os.walk(self.dest):
            trouves += [os.path.relpath(os.path.join(racine, n), self.dest).replace(os.sep, "/") for n in noms]
        return sorted(trouves)

    def fichier_etat(self):
        chemin = os.path.join(self.dest, ms.ETAT)
        return octets(chemin) if os.path.isfile(chemin) else b""

    def copie_avant(self):
        copie = os.path.join(self.d, "avant.pdf")
        with open(copie, "wb") as f:
            f.write(octets(self.chemin))
        return copie

    def genere_pour(self, chemin, **champs):
        ident = ocr.identite(chemin)
        bloc = {"type": "pdf_cherchable", "taille_source": ident["taille"], "empreinte_source": ident["empreinte"],
                "taille_fichier": ident["taille"], "empreinte_fichier": ident["empreinte"], "pages": 1,
                "date": "2026-11-08T10:00:00", "version": 1}
        bloc.update(champs)
        return bloc

    def etat_genere(self):
        return ms.charger_etat(self.dest)[self.cle_etat].get("genere")


class RefusPdf(PdfBase):
    def refuse(self, code, message=None):
        avant, etat, fichiers = octets(self.chemin), self.fichier_etat(), self.fichiers()
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.fabriquer()
        self.assertEqual(c.exception.code, code)
        self.assertEqual(str(c.exception), message or ocr.MESSAGES[code])
        self.assertEqual(octets(self.chemin), avant)
        self.assertEqual(self.fichier_etat(), etat)
        self.assertEqual(self.fichiers(), fichiers)
        self.assertEqual(self.appels, [])   # rien n'est reconnu, rien n'est ecrit
        self.assertFalse(os.path.exists(self.part()))

    def test_refus_numerique_signe_lecture_seule(self):
        """T19 : chaque refus sans rien ecrire, et un PDF a notre marque n'est pas refuse comme numerique."""
        self.poser(pages=[NATIF, NATIF])
        self.refuse("numerique", ocr.MESSAGES["refus_pdf"])
        self.poser(pdf_signe())
        self.refuse("signe", ocr.MESSAGES["refus_pdf"])
        self.poser(pdf_chiffre("", "proprio"))
        self.refuse("lecture_seule", ocr.MESSAGES["refus_pdf"])
        self.poser(pdf_chiffre("secret"))
        self.refuse("protege")
        self.poser(pages=[SCAN])
        with mock.patch.object(ocr.os, "access", return_value=False):
            self.refuse("lecture_seule", ocr.MESSAGES["refus_pdf"])

    def test_pdf_a_notre_marque_pas_refuse_comme_numerique(self):
        self.poser(pdf_avec_info([NATIF, NATIF], {"/MoodleSyncGenere": json_compact(MARQUE_VALIDE)}))
        genere = self.genere_pour(self.chemin, pages=2)
        self.ecrire_etat(genere=genere)
        avant = octets(self.chemin)
        # identite conforme a genere : deja fait, le bloc est renvoye tel quel, rien n'est reconnu ni ecrit
        self.assertEqual(self.fabriquer(), genere)
        self.assertEqual(octets(self.chemin), avant)
        self.assertEqual(self.appels, [])
        self.assertFalse(os.path.exists(self.part()))

    def test_marque_sans_etat_ou_fichier_modifie(self):
        """Marque presente mais fichier ni source ni conforme a genere : ni numerique, ni superpose deux fois."""
        self.poser(pdf_avec_info([NATIF, NATIF], {"/MoodleSyncGenere": json_compact(MARQUE_VALIDE)}))
        self.refuse("modifie_main")
        self.ecrire_etat(genere=self.genere_pour(self.chemin, taille_fichier=1, empreinte_fichier="sha256:" + "3" * 64,
                                                 taille_source=2, empreinte_source="sha256:" + "4" * 64))
        self.refuse("modifie_main")

    def test_non_suivi(self):
        self.poser(pages=[SCAN], etat=False)
        self.refuse("non_suivi")
        ms.sauver_etat(self.dest, {"https://moodle.exemple.ch/autre.pdf": {"t": 1, "chemin": "Ailleurs/autre.pdf"}})
        self.refuse("non_suivi")

    def test_pdf_abime_et_absent(self):
        self.poser(b"%PDF-1.4\nce n'est pas un pdf \x00\x01\x02")
        self.refuse("corrompu")
        os.remove(self.chemin)
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.fabriquer()
        self.assertEqual(c.exception.code, "corrompu")

    def test_arret_demande(self):
        self.poser()
        avant, etat = octets(self.chemin), self.fichier_etat()
        with self.assertRaises(ms.Annule):
            self.fabriquer(arreter=lambda: True)
        self.assertEqual((octets(self.chemin), self.fichier_etat()), (avant, etat))
        self.assertFalse(os.path.exists(self.part()))


class CoucheDeTexte(unittest.TestCase):
    def test_position_selon_la_rotation(self):
        """Du pixel du rendu au point du PDF : origine en bas a gauche, boite de page, rotation de la page."""
        boite = (0, 0, 200, 100)
        attendu = {
            0: ((0, 100, (1, 0, 0, 1)), (30, 90)),
            90: ((0, 0, (0, 1, -1, 0)), (10, 30)),
            180: ((200, 0, (-1, 0, 0, -1)), (170, 10)),
            270: ((200, 100, (0, -1, 1, 0)), (190, 70)),
        }
        for rotation, (coin, interieur) in attendu.items():
            with self.subTest(rotation=rotation):
                x, y, matrice = ocr._position(0, 0, 72, boite, rotation)
                self.assertEqual((x, y, matrice), coin)
                x, y, _ = ocr._position(30, 10, 72, boite, rotation)
                self.assertEqual((x, y), interieur)
        # boite decalee et resolution de 144 dpi (un pixel vaut un demi-point)
        x, y, _ = ocr._position(0, 0, 144, (10, 20, 210, 120), 0)
        self.assertEqual((x, y), (10, 120))
        x, y, _ = ocr._position(60, 20, 144, (10, 20, 210, 120), 0)
        self.assertEqual((x, y), (40, 110))

    def test_flux_de_la_couche(self):
        boites = [[100, 200, 300, 40, 0.9, "Où"],
                  [10, 10, 50, 20, 0.9, "日本"],          # hors cp1252 : omis de la couche
                  [10, 10, 50, 20, 0.9, "(a)\\"],          # parentheses et barre oblique : echappees
                  [10, 10, 0, 20, 0.9, "sans-largeur"],    # boite vide : ignoree
                  [10, 10, 50, 20, 0.9, "œuvre"]]
        flux = ocr._flux_couche(boites, 300, (0, 0, 595, 842), 0)
        self.assertIsInstance(flux, bytes)
        self.assertTrue(all(b < 128 for b in flux))   # ASCII seulement : les octets non ASCII sont en octal
        self.assertEqual(flux.count(b"Tj"), 3)
        self.assertIn(b"3 Tr", flux)                 # texte invisible
        self.assertIn(b"(O\\371)", flux)             # ù en WinAnsi
        self.assertIn(b"(\\(a\\)\\\\)", flux)
        self.assertIn(b"(\\234uvre)", flux)          # œ en WinAnsi
        self.assertNotIn("日".encode("utf-8"), flux)
        self.assertIsNone(ocr._flux_couche([[0, 0, 10, 10, 0.9, "日本語"]], 300, (0, 0, 595, 842), 0))
        self.assertIsNone(ocr._flux_couche([], 300, (0, 0, 595, 842), 0))


class Superposition(PdfBase):
    def test_superposition_conserve_objets(self):
        """T20 : pages, dimensions et rotations, annotations, liens et signets identiques ; pages natives intactes."""
        from pypdf import PdfReader
        from pypdf.generic import ArrayObject, IndirectObject
        self.poser(pdf_riche())
        avant = ocr.controler_pdf(self.copie_avant())
        genere = self.fabriquer()
        apres = ocr.controler_pdf(self.chemin)
        for cle in ("pages", "dimensions", "annotations", "liens", "signets"):
            self.assertEqual(apres[cle], avant[cle], cle)
        self.assertEqual(apres["dimensions"], [[595, 842, 90], [400, 300, 0], [595, 842, 0]])
        self.assertEqual(genere["pages"], 3)
        self.assertFalse(apres["numerique"])
        self.assertIsNotNone(apres["marque"])

        lecteur_avant, lecteur_apres = PdfReader(os.path.join(self.d, "avant.pdf")), PdfReader(self.chemin)
        # la page native (3) est identique, son /Contents n'est pas touche
        self.assertEqual(donnees_contenu(lecteur_apres.pages[2]), donnees_contenu(lecteur_avant.pages[2]))
        self.assertNotIsInstance(lecteur_apres.pages[2].raw_get("/Contents").get_object(), ArrayObject)
        # les pages reconnues (1 et 2) : /Contents devient [q, objet d'origine, couche], par objets indirects
        for i in (0, 1):
            contenu = lecteur_apres.pages[i].raw_get("/Contents").get_object()
            self.assertIsInstance(contenu, ArrayObject)
            self.assertEqual(len(contenu), 3)
            self.assertTrue(all(isinstance(x, IndirectObject) for x in contenu))
            self.assertEqual(contenu[1].get_object().get_data(), donnees_contenu(lecteur_avant.pages[i]))
            self.assertIn(b"3 Tr", contenu[2].get_object().get_data())
            ressources = lecteur_apres.pages[i]["/Resources"]
            self.assertIn("/F1", ressources["/Font"])
            self.assertIn("/Im1", ressources["/XObject"])
            self.assertIn("/" + ocr.NOM_POLICE, ressources["/Font"])
        # le texte de la couche est extractible, accents compris
        texte = lecteur_apres.pages[0].extract_text()
        for mot in ("Où", "été", "garçon", "élève", "œuvre", "Fin"):
            self.assertIn(mot, texte)
        self.assertEqual(self.etat_genere(), genere)

    def test_contents_deja_en_tableau(self):
        """/Contents est un tableau de deux flux : la couche s'ajoute sans rien perdre."""
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import ArrayObject, DecodedStreamObject, NameObject
        w = PdfWriter(clone_from=io.BytesIO(pdf_minimal([SCAN])))
        page = w.pages[0]
        d = donnees_contenu(page)
        a, b = DecodedStreamObject(), DecodedStreamObject()
        a.set_data(d[: len(d) // 2])
        b.set_data(d[len(d) // 2:])
        page[NameObject("/Contents")] = ArrayObject([w._add_object(a), w._add_object(b)])
        sortie = io.BytesIO()
        w.write(sortie)
        self.poser(sortie.getvalue())
        self.fabriquer()
        contenu = PdfReader(self.chemin).pages[0].raw_get("/Contents").get_object()
        self.assertEqual(len(contenu), 4)   # q, les deux flux d'origine, la couche
        self.assertEqual(contenu[1].get_object().get_data() + contenu[2].get_object().get_data(), d)
        self.assertIn(b"3 Tr", contenu[3].get_object().get_data())

    def test_flux_de_la_couche_encadre(self):
        """Ecart 68 : le flux d'ouverture vaut `q` et la couche est encadree par `Q q ... Q` ; vider l'un ou retirer
        l'autre fait echouer ce test."""
        from pypdf import PdfReader
        from pypdf.generic import ArrayObject
        self.poser(pages=[SCAN])
        self.fabriquer()
        contenu = PdfReader(self.chemin).pages[0].raw_get("/Contents").get_object()
        self.assertIsInstance(contenu, ArrayObject)
        self.assertEqual(contenu[0].get_object().get_data(), b"q\n")
        couche = contenu[-1].get_object().get_data()
        self.assertTrue(couche.startswith(b"Q\nq\n"), couche[:20])
        self.assertTrue(couche.endswith(b"Q\n"), couche[-20:])
        self.assertIn(b"3 Tr", couche)
        self.assertIn(b"ET\nQ\n", couche)   # la couche ferme son propre BT/ET avant l'enveloppe

    def test_signet_perdu_abandonne(self):
        """T20 : un signet perdu fait abandonner, l'original reste en place, genere n'est jamais ecrit."""
        from pypdf import PdfWriter
        self.poser(pdf_riche())
        avant, etat = octets(self.chemin), self.fichier_etat()
        ecrire_vrai = ocr._ecrire_part

        def ecrire_sans_signets(*a, **kw):
            volume = ecrire_vrai(*a, **kw)
            part = a[1]
            w = PdfWriter(clone_from=part)
            del w._root_object["/Outlines"]
            with open(part, "wb") as f:
                w.write(f)
            return volume

        with mock.patch.object(ocr, "_ecrire_part", ecrire_sans_signets):
            with self.assertRaises(ocr.ErreurOcr) as c:
                self.fabriquer()
        self.assertEqual((c.exception.code, str(c.exception)), ("verification", ocr.MESSAGES["verification"]))
        self.assertEqual((octets(self.chemin), self.fichier_etat()), (avant, etat))
        self.assertFalse(os.path.exists(self.part()))

    def test_page_perdue_ou_annotation_perdue(self):
        from pypdf import PdfWriter
        self.poser(pdf_riche())
        avant = octets(self.chemin)
        ecrire_vrai = ocr._ecrire_part
        for nom, abime in (("annotation", lambda w: w.pages[1].pop("/Annots")),
                           ("page", lambda w: w.remove_page(2))):
            def ecrire_abime(*a, _abime=abime, **kw):
                volume = ecrire_vrai(*a, **kw)
                w = PdfWriter(clone_from=a[1])
                _abime(w)
                with open(a[1], "wb") as f:
                    w.write(f)
                return volume

            with self.subTest(nom), mock.patch.object(ocr, "_ecrire_part", ecrire_abime):
                with self.assertRaises(ocr.ErreurOcr) as c:
                    self.fabriquer()
                self.assertEqual(c.exception.code, "verification")
                self.assertEqual(octets(self.chemin), avant)
                self.assertFalse(os.path.exists(self.part()))

    def test_lien_perdu_abandonne(self):
        """Ecart 67 : un lien perdu dans le fichier temporaire fait abandonner, meme si le nombre d'annotations ne
        bouge pas (le lien devient une annotation de texte). Retirer le controle des liens fait echouer ce test."""
        from pypdf import PdfWriter
        from pypdf.generic import NameObject
        self.poser(pdf_riche())
        avant, etat = octets(self.chemin), self.fichier_etat()
        ecrire_vrai = ocr._ecrire_part
        mesures = []

        def ecrire_sans_lien(*a, **kw):
            volume = ecrire_vrai(*a, **kw)
            part = a[1]
            w = PdfWriter(clone_from=part)
            page = w.pages[0]
            for annot in page["/Annots"]:
                objet = annot.get_object()
                if objet.get("/Subtype") == "/Link":
                    objet[NameObject("/Subtype")] = NameObject("/Text")
            with open(part, "wb") as f:
                w.write(f)
            apres = ocr.controler_pdf(part)
            mesures.append((apres["annotations"], apres["liens"]))
            return volume

        with mock.patch.object(ocr, "_ecrire_part", ecrire_sans_lien):
            with self.assertRaises(ocr.ErreurOcr) as c:
                self.fabriquer()
        self.assertEqual((c.exception.code, str(c.exception)), ("verification", ocr.MESSAGES["verification"]))
        # la mutation a bien laisse le nombre d'annotations intact : seul le controle des liens peut la voir
        self.assertEqual(mesures, [(2, 0)])
        self.assertEqual(octets(self.chemin), avant)
        self.assertEqual(self.fichier_etat(), etat)
        self.assertFalse(os.path.exists(self.part()))

    def test_rendu_de_trois_pages(self):
        """Premiere, milieu et derniere page reconnues, a 150 DPI, original et fichier temporaire."""
        self.poser(pages=[SCAN, NATIF, SCAN, SCAN, SCAN, SCAN, NATIF])   # reconnues : 1, 3, 4, 5, 6
        self.fabriquer()
        controles = [(os.path.basename(c), n) for c, n, dpi in self.rendus if dpi == 150]
        self.assertEqual(sorted(controles), sorted([("scan.pdf", 1), ("scan.pdf", 4), ("scan.pdf", 6),
                                                    ("scan.pdf.ocr.part", 1), ("scan.pdf.ocr.part", 4), ("scan.pdf.ocr.part", 6)]))

    def test_rendu_different_abandonne(self):
        """D9 : un seul pixel d'ecart entre l'original et le fichier temporaire, abandon."""
        from PIL import Image
        self.poser()
        avant, etat = octets(self.chemin), self.fichier_etat()

        def rendre(chemin, numero, dpi, **kw):
            image = Image.new("L", (120, 60), 255)
            if chemin.endswith(".ocr.part") and dpi == 150 and numero == 3:
                image.putpixel((5, 5), 254)
            return image

        self.rendre = rendre
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.fabriquer()
        self.assertEqual(c.exception.code, "verification")
        self.assertEqual((octets(self.chemin), self.fichier_etat()), (avant, etat))
        self.assertFalse(os.path.exists(self.part()))

    def test_rendu_compare_sur_images_brutes(self):
        """Ecart 69 : deux rendus bruts differents que l'autocontraste rend identiques font abandonner (D9 compare
        les images brutes ; l'autocontraste ne sert plus qu'a expliquer)."""
        from PIL import Image
        self.poser()
        avant, etat = octets(self.chemin), self.fichier_etat()

        def rendre(chemin, numero, dpi, *, preparer=True):
            # deux images de meme structure, l'une dans [100, 200], l'autre dans [50, 100] : l'autocontraste les
            # ramene toutes deux a [0, 255], donc a la meme image preparee.
            base = 50 if chemin.endswith(".ocr.part") else 100
            image = Image.new("L", (120, 60), base)
            image.paste(base * 2, (0, 0, 60, 60))
            return ocr._preparer(image) if preparer else image

        # la doublure reproduit fidelement ce que fait pdfium : image brute, autocontraste seulement si demande
        brute = Image.new("L", (120, 60), 100)
        brute.paste(200, (0, 0, 60, 60))
        autre = Image.new("L", (120, 60), 50)
        autre.paste(100, (0, 0, 60, 60))
        self.assertNotEqual(brute.tobytes(), autre.tobytes())
        self.assertEqual(ocr._preparer(brute).tobytes(), ocr._preparer(autre).tobytes())

        self.rendre = rendre
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.fabriquer()
        self.assertEqual(c.exception.code, "verification")
        self.assertEqual((octets(self.chemin), self.fichier_etat()), (avant, etat))
        self.assertFalse(os.path.exists(self.part()))

    def test_rendu_impossible_abandonne(self):
        """pypdfium2 absent ou rendu en erreur : la verification ne peut pas conclure, donc abandon."""
        from PIL import Image
        self.poser()
        avant = octets(self.chemin)

        def rendre(chemin, numero, dpi, **kw):
            if dpi == 150:
                raise ocr.ErreurOcr("illisible", n=numero)
            return Image.new("L", (120, 60), 255)

        self.rendre = rendre
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.fabriquer()
        self.assertEqual(c.exception.code, "verification")
        self.assertEqual(octets(self.chemin), avant)
        self.assertFalse(os.path.exists(self.part()))

    def test_texte_non_extractible_abandonne(self):
        self.poser()
        avant = octets(self.chemin)
        with mock.patch.object(ocr, "_texte_natif", lambda page: ""):
            with self.assertRaises(ocr.ErreurOcr) as c:
                self.fabriquer()
        self.assertEqual(c.exception.code, "verification")
        self.assertEqual(octets(self.chemin), avant)
        self.assertFalse(os.path.exists(self.part()))

    def test_volume_de_la_couche_borne(self):
        """D10 : plus de 10 Ko par page reconnue (flux compresse) : abandon. Des mots au hasard ne se compressent pas."""
        self.tsv = tsv_dense(4000).encode("utf-8")
        self.poser(pages=[SCAN])
        avant, etat = octets(self.chemin), self.fichier_etat()
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.fabriquer()
        self.assertEqual(c.exception.code, "verification")
        self.assertEqual((octets(self.chemin), self.fichier_etat()), (avant, etat))
        self.assertFalse(os.path.exists(self.part()))

    def test_page_sans_mot_exploitable(self):
        """Une page reconnue sans aucun mot encodable ne donne aucune couche : rien a remplacer, abandon."""
        self.tsv = (ENTETE_TSV + "\r\n" + mot_tsv(1, 1, 1, 1, 100, "90", "日本語") + "\r\n").encode("utf-8")
        self.poser(pages=[SCAN])
        avant = octets(self.chemin)
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.fabriquer()
        self.assertEqual(c.exception.code, "verification")
        self.assertEqual(octets(self.chemin), avant)

    def test_page_illisible_sautee(self):
        """Une page que le rendu ne lit pas n'a pas de couche ; les autres en ont une, le fichier reste valide."""
        from pypdf import PdfReader
        from PIL import Image
        self.poser(pages=[SCAN, SCAN, SCAN])

        def rendre(chemin, numero, dpi, **kw):
            self.rendus.append((chemin, numero, dpi))
            if numero == 2 and dpi == 300:
                raise ocr.ErreurOcr("illisible", n=2)
            return Image.new("L", (120, 60), 255)

        self.rendre = rendre
        self.fabriquer()
        lecteur = PdfReader(self.chemin)
        self.assertEqual(lecteur.pages[0].extract_text().count("Fin"), 1)
        self.assertEqual(lecteur.pages[1].extract_text().strip(), "")
        self.assertEqual(lecteur.pages[2].extract_text().count("Fin"), 1)


class RemplacementAtomique(PdfBase):
    def suivre(self, echecs_replace=0):
        """Enregistre l'ordre des ecritures d'etat et des os.replace du fichier temporaire."""
        evt = []
        replace_vrai, sauver_vrai = os.replace, ms.sauver_etat
        restants = [echecs_replace]

        def replace(src, dst, *a, **kw):
            if not str(src).endswith(".ocr.part"):
                return replace_vrai(src, dst, *a, **kw)
            self.assertTrue(os.path.isfile(src))
            if restants[0]:
                restants[0] -= 1
                evt.append("replace-echec")
                raise PermissionError("fichier ouvert dans un autre programme")
            evt.append("replace")
            return replace_vrai(src, dst, *a, **kw)

        def sauver(dest, etat):
            entree = etat.get(self.cle_etat, {})
            evt.append("etat+genere" if "genere" in entree else "etat-genere")
            if "genere" in entree:
                self.assertEqual(entree["genere"]["taille_fichier"], os.path.getsize(self.part()))
            return sauver_vrai(dest, etat)

        for p in (mock.patch.object(ocr.os, "replace", replace), mock.patch.object(ms, "sauver_etat", sauver)):
            p.start()
            self.addCleanup(p.stop)
        return evt

    def test_remplacement_atomique_volume(self):
        """T21 : reussite, aucun second PDF, aucun .part, volume borne ; l'etat porte genere."""
        self.poser(pdf_riche())
        avant = octets(self.chemin)
        genere = self.fabriquer()
        apres = octets(self.chemin)
        self.assertNotEqual(apres, avant)
        self.assertFalse(os.path.exists(self.part()))
        self.assertEqual([f for f in self.fichiers() if f.lower().endswith(".pdf")], [self.rel])
        self.assertEqual([f for f in self.fichiers() if "Originaux" in f or ".orig" in f or ".bak" in f
                          or "ancienne" in f.lower() or f.endswith(".part")], [])
        self.assertLessEqual(len(apres) - len(avant), 10 * 1024 * 2)   # deux pages reconnues
        self.assertEqual(set(genere), {"type", "taille_source", "empreinte_source", "taille_fichier", "empreinte_fichier",
                                       "pages", "date", "version"})
        self.assertEqual((genere["type"], genere["pages"], genere["version"]), ("pdf_cherchable", 3, 1))
        self.assertEqual((genere["taille_source"], genere["empreinte_source"]),
                         (len(avant), "sha256:" + hashlib.sha256(avant).hexdigest()))
        self.assertEqual((genere["taille_fichier"], genere["empreinte_fichier"]),
                         (len(apres), "sha256:" + hashlib.sha256(apres).hexdigest()))
        etat = ms.charger_etat(self.dest)
        self.assertEqual(etat[self.cle_etat]["genere"], genere)
        self.assertEqual((etat[self.cle_etat]["t"], etat[self.cle_etat]["chemin"]), (1760000000, self.rel.replace("/", os.sep)))
        self.assertEqual(etat["_sections"], {"12": "Section 1"})   # le reste de l'etat est conserve

    def test_echec_avant_replace(self):
        """T21 : un echec avant os.replace (ici l'ecriture de l'etat) laisse l'original intact et aucun .part."""
        self.poser()
        avant, etat = octets(self.chemin), self.fichier_etat()
        with mock.patch.object(ms, "sauver_etat", side_effect=OSError("disque plein")):
            with self.assertRaises(OSError):
                self.fabriquer()
        self.assertEqual((octets(self.chemin), self.fichier_etat()), (avant, etat))
        self.assertFalse(os.path.exists(self.part()))
        self.assertEqual([f for f in self.fichiers() if f.endswith(".pdf")], [self.rel])

    def test_ordre_de_l_invariant_5(self):
        """L'etat n'est ecrit qu'apres la verification du .part, os.replace vient en dernier."""
        self.poser()
        evt = self.suivre()
        self.fabriquer()
        self.assertEqual(evt, ["etat+genere", "replace"])

    def test_verification_avant_toute_ecriture_d_etat(self):
        from PIL import Image
        self.poser()
        evt = self.suivre()
        self.rendre = lambda chemin, n, dpi, **kw: Image.new("L", (120, 60), 0 if chemin.endswith(".ocr.part") else 255)
        with self.assertRaises(ocr.ErreurOcr):
            self.fabriquer()
        self.assertEqual(evt, [])

    def test_pdf_verrouille(self):
        """T18 : os.replace leve PermissionError ; un nouvel essai apres 2 s, puis verrouille ; original intact,
        genere retire de l'etat."""
        self.poser()
        avant = octets(self.chemin)
        etat_avant = ms.charger_etat(self.dest)
        evt = self.suivre(echecs_replace=2)
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.fabriquer()
        self.assertEqual((c.exception.code, str(c.exception)), ("verrouille", ocr.MESSAGES["verrouille"]))
        self.assertEqual(evt, ["etat+genere", "replace-echec", "replace-echec", "etat-genere"])
        self.assertEqual(self.pauses, [2])
        self.assertEqual(octets(self.chemin), avant)
        self.assertEqual(ms.charger_etat(self.dest), etat_avant)
        self.assertNotIn("genere", ms.charger_etat(self.dest)[self.cle_etat])
        self.assertFalse(os.path.exists(self.part()))

    def test_verrou_leve_au_second_essai(self):
        self.poser()
        evt = self.suivre(echecs_replace=1)
        genere = self.fabriquer()
        self.assertEqual(evt, ["etat+genere", "replace-echec", "replace"])
        self.assertEqual(self.pauses, [2])
        self.assertEqual(ms.charger_etat(self.dest)[self.cle_etat]["genere"], genere)
        self.assertFalse(os.path.exists(self.part()))

    def test_autre_erreur_de_remplacement(self):
        """Une erreur qui n'est pas un verrou : etat et .part nettoyes, l'erreur sort telle quelle (OSError)."""
        self.poser()
        avant = octets(self.chemin)
        replace_vrai = os.replace

        def replace(src, dst, *a, **kw):
            if str(src).endswith(".ocr.part"):
                raise OSError("disque plein")
            return replace_vrai(src, dst, *a, **kw)

        with mock.patch.object(ocr.os, "replace", replace):
            with self.assertRaises(OSError):
                self.fabriquer()
        self.assertEqual(octets(self.chemin), avant)
        self.assertNotIn("genere", ms.charger_etat(self.dest)[self.cle_etat])
        self.assertFalse(os.path.exists(self.part()))
        self.assertEqual(self.pauses, [])

    def test_coupure_entre_etat_et_remplacement(self):
        """genere ecrit mais le fichier a encore l'identite source : on refait, sans refus."""
        self.poser()
        source = ocr.identite(self.chemin)
        self.ecrire_etat(genere={"type": "pdf_cherchable", "taille_source": source["taille"],
                                 "empreinte_source": source["empreinte"], "taille_fichier": source["taille"] + 999,
                                 "empreinte_fichier": "sha256:" + "2" * 64, "pages": 3, "date": "2026-11-08T10:00:00", "version": 1})
        genere = self.fabriquer()
        self.assertNotEqual(genere["taille_fichier"], source["taille"] + 999)
        self.assertEqual(genere["empreinte_source"], source["empreinte"])
        self.assertEqual(ms.charger_etat(self.dest)[self.cle_etat]["genere"], genere)

    def test_deuxieme_passage_ne_refait_rien(self):
        self.poser()
        premier = self.fabriquer()
        octets_1 = octets(self.chemin)
        appels = len(self.appels)
        self.assertEqual(self.fabriquer(), premier)
        self.assertEqual((octets(self.chemin), len(self.appels)), (octets_1, appels))

    def test_marque_ecrite(self):
        """Marque : moins de 1 Ko, URL sans jeton, aucun chemin local, identite de la source."""
        from pypdf import PdfReader
        self.cle_etat = URL_MOODLE + "?token=SECRET123&forcedownload=1"
        self.poser()
        source = ocr.identite(self.chemin)
        self.fabriquer()
        marque = ocr.lire_marque(self.chemin)
        self.assertEqual(marque, {"v": 1, "url": URL_MOODLE, "t": 1760000000, "taille_source": source["taille"],
                                  "empreinte_source": source["empreinte"], "pages": 3})
        brut = PdfReader(self.chemin).metadata["/MoodleSyncGenere"]
        self.assertLess(len(brut.encode("utf-8")), 1024)
        for interdit in ("token", "SECRET", "?", self.dest, self.d, "\\\\", "Cours A", "Section 1"):
            self.assertNotIn(interdit, brut)
        self.assertEqual(json.loads(brut), marque)

    def test_marque_trop_longue_refusee(self):
        self.cle_etat = "https://moodle.exemple.ch/" + "a" * 1100 + "/scan.pdf"
        self.poser()
        avant = octets(self.chemin)
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.fabriquer()
        self.assertEqual(c.exception.code, "verification")
        self.assertEqual(octets(self.chemin), avant)
        self.assertFalse(os.path.exists(self.part()))

    def test_pdf_a_notre_marque_n_est_plus_numerique(self):
        """Apres le remplacement, la couche porte plus de SEUIL_TEXTE caracteres : sans la marque, le PDF serait « numerique »."""
        self.tsv = tsv_assez_long().encode("utf-8")
        self.poser(pages=[SCAN])
        self.fabriquer()
        self.assertFalse(ocr._a_reconnaitre(self.chemin))
        ctl = ocr.controler_pdf(self.chemin)
        self.assertFalse(ctl["numerique"])
        self.assertIsNotNone(ctl["marque"])

    def test_aucun_reseau(self):
        """Invariant 6 : fabriquer_pdf_cherchable n'appelle ni urlopen ni socket."""
        self.poser()
        with mock.patch.object(urllib.request, "urlopen", side_effect=OSError("reseau interdit")) as ouvrir, \
                mock.patch.object(socket, "create_connection", side_effect=OSError("reseau interdit")) as relier:
            self.fabriquer()
        ouvrir.assert_not_called()
        relier.assert_not_called()

    def test_entree_d_etat_retrouvee_par_chemin(self):
        """L'entree d'etat se retrouve par `chemin`, separateur du systeme ou `/` indifferent."""
        self.poser(etat=False)
        ms.sauver_etat(self.dest, {"https://moodle.exemple.ch/a.pdf": {"t": 1, "chemin": "Autre\\a.pdf"},
                                   self.cle_etat: {"t": 5, "chemin": "Cours A\\Section 1\\scan.pdf"}})
        genere = self.fabriquer()
        etat = ms.charger_etat(self.dest)
        self.assertEqual(etat[self.cle_etat]["genere"], genere)
        self.assertNotIn("genere", etat["https://moodle.exemple.ch/a.pdf"])
        self.assertEqual(ocr.lire_marque(self.chemin)["t"], 5)


class TraiterEtRemplacer(PdfBase):
    def test_traiter_document_remplace(self):
        self.poser()
        resultat = self.avec(ocr.traiter_document, self.dest, self.rel, {"ocr_pdf": "remplacer"})
        self.assertEqual(resultat["pdf"], "remplace")
        self.assertEqual(resultat["message"], ocr.MESSAGES["pdf_genere"].format(nom="scan.pdf"))
        self.assertIn("scan.pdf", resultat["message"])
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "Textes", "Cours A", "Section 1", "scan.pdf.md")))
        self.assertIsNotNone(ocr.lire_marque(self.chemin))
        self.assertIn("genere", ms.charger_etat(self.dest)[self.cle_etat])
        # la source etant identifiee par genere, un second passage ne refait rien
        appels = len(self.appels)
        self.avec(ocr.traiter_document, self.dest, self.rel, {"ocr_pdf": "remplacer"})
        self.assertEqual(len(self.appels), appels)

    def reprise(self, empreinte):
        return ocr._fichier_reprise(self.dest, empreinte)

    def test_reprise_sert_la_fabrication(self):
        """Ecart 60 : en mode `remplacer`, chaque page a reconnaitre n'est reconnue qu'une fois ; la reprise, donc les
        boites, reste disponible pendant la fabrication et n'est supprimee qu'apres un remplacement reussi."""
        self.poser(pages=[SCAN, SCAN, SCAN])
        empreinte = ocr.identite(self.chemin)["empreinte"]
        resultat = self.avec(ocr.traiter_document, self.dest, self.rel, {"ocr_pdf": "remplacer"})
        self.assertEqual(resultat["pdf"], "remplace")
        self.assertEqual(len(self.appels), 3)   # une reconnaissance par page, pas deux
        self.assertEqual(sorted(n for _, n, dpi in self.rendus if dpi == 300), [1, 2, 3])
        self.assertFalse(os.path.exists(self.reprise(empreinte)))

    def test_reprise_gardee_si_le_remplacement_echoue(self):
        """Ecart 60 : un remplacement qui echoue laisse la reprise et ses boites en place, pour l'essai suivant."""
        from PIL import Image
        self.poser(pages=[SCAN, SCAN])
        empreinte = ocr.identite(self.chemin)["empreinte"]

        def rendre(chemin, numero, dpi, *, preparer=True):
            image = Image.new("L", (120, 60), 255)
            if chemin.endswith(".ocr.part") and dpi == 150:
                image.putpixel((0, 0), 254)
            return image

        self.rendre = rendre
        resultat = self.avec(ocr.traiter_document, self.dest, self.rel, {"ocr_pdf": "remplacer"})
        self.assertEqual((resultat["pdf"], resultat["message"]), ("echec", ocr.MESSAGES["verification"]))
        chemin = self.reprise(empreinte)
        self.assertTrue(os.path.isfile(chemin))
        faites = self.lire_json(chemin)["faites"]
        self.assertEqual(sorted(faites), ["1", "2"])
        for enreg in faites.values():
            self.assertEqual(enreg["source"], "ocr")
            self.assertTrue(enreg["boites"])

    def test_traiter_document_refuse(self):
        self.poser(pages=[NATIF, NATIF])
        avant = octets(self.chemin)
        resultat = self.avec(ocr.traiter_document, self.dest, self.rel, {"ocr_pdf": "remplacer"})
        self.assertEqual((resultat["pdf"], resultat["message"]), ("refuse", ocr.MESSAGES["refus_pdf"]))
        self.assertEqual(octets(self.chemin), avant)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "Textes", "Cours A", "Section 1", "scan.pdf.md")))   # le texte est ecrit

    def test_messages_de_c4(self):
        self.assertEqual(ocr.MESSAGES["refus_pdf"],
                         "Ce PDF est déjà lisible, signé ou en lecture seule : MoodleSync ne le modifie pas. "
                         "Son texte reste disponible dans Mes textes.")
        for code in ("numerique", "signe", "lecture_seule"):
            self.assertEqual(str(ocr.ErreurOcr(code)), ocr.MESSAGES["refus_pdf"])
        self.assertEqual(ocr.MESSAGES["verification"],
                         "Le PDF cherchable n'a pas passé les contrôles. Ton fichier d'origine n'a pas été touché.")
        self.assertEqual(ocr.MESSAGES["modifie_main"],
                         "Ce fichier a été modifié depuis sa création par MoodleSync. Continuer le remplacera.")
        self.assertEqual(ocr.MESSAGES["pdf_genere"],
                         "« {nom} » est maintenant cherchable avec Ctrl+F. Ses pages d'origine sont conservées, "
                         "l'original exact se retélécharge depuis Moodle.")
        self.assertIn("non_suivi", ocr.MESSAGES)
        for message in ocr.MESSAGES.values():
            self.assertNotIn(chr(0x2014), message)
            self.assertNotIn(chr(0x2013), message)


def _moteur_reel():
    """Vrai quand un vrai Tesseract repond : c'est le seul outil facultatif de la garde de T29.

    Pillow est une dependance de requirements-testes.txt depuis P1 : son absence est une installation
    cassee, donc une erreur, jamais un test ignore (ecart 261, P2).
    """
    import PIL  # noqa: F401  (import volontairement non protege : voir la docstring)
    return bool(ocr.detecter({})["present"])


class SortiesDeCours(DocumentsC3):
    """Tache C5 : Markdown de cours, index, qualite, contexte copiable, JSONL, orphelins.

    Les documents sont fabriques par extraire_document (doublures de executer et de rendre_page) : les .md
    lus par C5 sont ceux de C2, et le cache est celui de C3. Aucun document reel, aucun config.json.
    """

    def setUp(self):
        super().setUp()
        self.cfg = {}

    def sortie(self, *parties):
        return os.path.join(self.dest, "Textes", *parties)

    def lire(self, *parties):
        with open(self.sortie(*parties), "rb") as f:
            return f.read().decode("utf-8")

    def marquer(self, rel, **champs):
        cache = ocr.charger_cache(self.dest)
        cache["documents"][rel].update(champs)
        ocr.sauver_cache(self.dest, cache)

    def etat(self, rel, confiance, etat):
        """Confiance et etat du cache, comme C3 les deriverait (2.3) : la page de chaque document porte la
        confiance du document, donc la moyenne ponderee la rend telle quelle."""
        self.marquer(rel, confiance=confiance, etat=etat)

    def ecrire_nomme(self, chemin, contenu):
        """Fichier ecrit par le banc : le systeme de fichiers garde le nom tel quel (pas de normalisation)."""
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(contenu.encode("utf-8"))

    def document(self, rel, pages, cfg=None):
        """Un document du coffre, de son PDF a son entree de cache, comme C2 et C3 le laissent.

        Le .md est ecrit par `ecrire_document_md` de C2, avec la section « Pages à vérifier » qu'il produit
        reellement (ecart 82) ; le cache reprend les comptes de `_resume_pages` et l'etat de `_etat_document`.
        `pages` : [(numero, source, confiance, texte)], source etant `ocr`, `texte` ou `vide`.
        """
        parties = rel.split("/")
        chemin = os.path.join(self.dest, *parties)
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(b"%PDF-1.4\n")   # le document existe : ce n'est pas un orphelin
        resultats = [{"numero": numero, "source": source, "texte": texte, "confiance": confiance,
                      "mots": len(texte.split())} for numero, source, confiance, texte in pages]
        md, sortie = ocr._chemin_sortie(self.dest, cfg or {}, rel)
        ocr.ecrire_document_md(md, rel, resultats, {"langues": "fra+eng", "moteur": "5.5.3"},
                               date="2026-11-08T10:00:00")
        resume = ocr._resume_pages(resultats, len(resultats))
        cache = ocr.charger_cache(self.dest)
        cache["documents"][rel] = {
            "empreinte": "sha256:" + rel, "taille": 9, "pages": resume["pages"],
            "pages_texte": resume["pages_texte"], "pages_ocr": resume["pages_ocr"],
            "numeros_ocr": [p["numero"] for p in resultats if p["source"] == "ocr"],
            "pages_vides": resume["pages_vides"], "extraction": resume["extraction"],
            "confiance": resume["confiance"], "langues": "fra+eng", "dpi": 300, "psm": 3, "moteur": "5.5.3",
            "sortie": sortie, "etat": ocr._etat_document(resultats), "verifie": False,
            "date": "2026-11-08T10:00:00"}
        ocr.sauver_cache(self.dest, cache)
        return rel

    def jeux(self, cfg=None):
        """Deux cours, trois documents, inseres dans le desordre : un bon, un a verifier, un difficile.

        La section « Pages à vérifier » ne porte que les pages que C2 y mettrait (ecart 82) : rien pour a.pdf, la
        page 2 peu sure et la page 3 sans texte de b.pdf, la page 1 de c.pdf. La derniere page de b.pdf est blanche,
        cas courant d'un scan (ecart 77).
        """
        self.document("Cours B/Section 2/c.pdf", [(1, "ocr", 0.55, "Photocopie peu lisible.")], cfg)
        self.document("Cours A/Section 1/b.pdf", [(1, "ocr", 0.93, "Le chômage baisse lentement."),
                                                  (2, "ocr", 0.78, "La relance reste fragile."),
                                                  (3, "vide", None, "")], cfg)
        self.document("Cours A/Section 1/a.pdf", [(1, "ocr", 0.93, "Le plan de Marshall transforme l'économie "
                                                          "européenne."),
                                                  (2, "ocr", 0.93, "Les États-Unis financent la reconstruction.")], cfg)

    def jeux_mixte(self):
        """Un document mixte : page 1 native, page 2 reconnue a 0,42, page 3 reconnue a 0,91 (ecarts 78 et 80)."""
        return self.document("Cours M/Section 1/m.pdf", [(1, "texte", None, "Le texte natif de la première page."),
                                                        (2, "ocr", 0.42, "Reconnaissance peu sûre."),
                                                        (3, "ocr", 0.91, "Fin du document.")])

    def test_contexte_copiable(self):
        """T27 : [p. n], phrase d'introduction, ordre des documents, aucune ecriture disque."""
        self.jeux()
        cfg = {"cours": {"42": {"dossier": "Cours B"}}}
        avant = sorted(os.walk(self.dest))
        texte = ocr.assembler_contexte(self.dest, "tout")
        self.assertEqual(sorted(os.walk(self.dest)), avant)   # aucune ecriture disque
        self.assertTrue(texte.startswith("# Cours A : texte des documents"), texte[:80])
        self.assertIn("Texte extrait localement par MoodleSync.", texte)
        self.assertIn("[p. 1]", texte)
        self.assertIn("[p. 3]", texte)
        self.assertIn("## Section 1", texte)
        self.assertIn("### b.pdf", texte)
        self.assertIn("[source : Section 1/b.pdf, 3 pages]", texte)
        # Ordre : cours, puis section, puis nom (ms.cle_nom), et Cours B apres Cours A. Le cache est insere dans
        # le desordre (jeux), donc ceci mesure le tri de _documents (ecart 82).
        self.assertLess(texte.index("### a.pdf"), texte.index("### b.pdf"))
        self.assertLess(texte.index("# Cours A"), texte.index("# Cours B"))
        self.assertEqual(texte.count("# Cours A : texte des documents"), 1)
        # `cours:<cid>` se resout par cfg["cours"][cid]["dossier"] (contrat 2.5, ecart 74).
        self.assertEqual(ocr.assembler_contexte(self.dest, "cours:42", cfg=cfg).count("# Cours B"), 1)
        self.assertNotIn("Cours A", ocr.assembler_contexte(self.dest, "cours:42", cfg=cfg))
        self.assertEqual(ocr.assembler_contexte(self.dest, "cours:42"), "")   # sans cfg, la portee est vide
        self.assertEqual(ocr.assembler_contexte(self.dest, "cours:Inconnu", cfg=cfg), "")
        self.assertEqual(ocr.assembler_contexte(self.dest, "document:Cours A/Section 1/a.pdf").count("### "), 1)
        self.assertEqual(ocr.assembler_contexte(self.dest, "document:absent.pdf"), "")

    def test_markdown_de_cours(self):
        """Plan 6.2 : ms.MARQUE en premiere ligne, titre, phrase d'introduction, sections, [p. n]."""
        self.jeux()
        avant = sorted(tuple(entree) for entree in os.walk(self.dest))
        ocr.ecrire_cours_md(self.dest, "tout")
        # os.walk rend un tuple (racine, dossiers, fichiers) : on compare des listes de tuples, pas des listes
        # auxquelles on ajoute des tuples. Le fichier de cours n'ajoute aucune entree : ses deux dossiers existent
        # deja (ceux des .md de document), seule leur liste de fichiers change.
        apres = sorted(tuple(entree) for entree in os.walk(self.dest))
        attendu = avant
        for cours in ("Cours A", "Cours B"):
            racine = os.path.join(self.dest, "Textes", cours)
            attendu = [(r, d, list(f) + [f"{cours} - texte des documents.md"]) if r == racine else (r, d, f)
                       for r, d, f in attendu]
        self.assertEqual(apres, sorted(attendu))
        contenu = self.lire("Cours A", "Cours A - texte des documents.md")
        lignes = contenu.split("\n")
        self.assertEqual(lignes[0], ms.MARQUE)
        self.assertEqual(lignes[1], "")
        self.assertEqual(lignes[2], "# Cours A : texte des documents")
        self.assertIn("Texte extrait localement par MoodleSync. Les citations indiquent la page du PDF, "
                      "pas la page imprimée.", contenu)
        self.assertIn("## Section 1", contenu)
        self.assertIn("### a.pdf", contenu)
        self.assertIn("[source : Section 1/a.pdf, 2 pages]", contenu)
        self.assertIn("[p. 1]", contenu)
        self.assertIn("[p. 2]", contenu)
        self.assertIn("[p. 3]", contenu)
        self.assertLess(contenu.index("[p. 1]"), contenu.index("[p. 2]"))
        self.assertLess(contenu.index("### a.pdf"), contenu.index("### b.pdf"))
        self.assertNotIn("\r", contenu)
        self.assertFalse(contenu.startswith("\ufeff"))
        # Le texte des pages vient du .md du document, sans son front matter ni ses commentaires.
        self.assertNotIn("moodlesync:", contenu)
        self.assertNotIn("<!-- page", contenu)
        self.assertNotIn("---", contenu)
        self.assertNotIn(self.dest, contenu)   # aucun chemin absolu
        # La section de controle de C2 n'est pas du texte de cours : elle ne passe pas dans l'agregat, y compris
        # quand elle precede la derniere page (c.pdf, b.pdf). Sans cela, la page 3 de b.pdf porterait le titre.
        self.assertNotIn("Pages à vérifier", contenu)
        self.assertNotIn("confiance 0,55", contenu)
        # La derniere page de b.pdf est blanche : elle est ecrite quand meme (ecart 77), donc le fichier se termine
        # sur son marqueur, sans texte.
        self.assertTrue(contenu.rstrip("\n").endswith("[p. 3]"), contenu[-80:])
        cours_b = self.lire("Cours B", "Cours B - texte des documents.md")
        self.assertNotIn("Pages à vérifier", cours_b)
        self.assertTrue(cours_b.rstrip("\n").endswith("Photocopie peu lisible."), cours_b[-80:])
        # Portee `cours:<cid>` resolue par cfg["cours"][cid]["dossier"] (contrat 2.5, ecart 74), sans casse.
        cfg = {"cours": {"42": {"dossier": "cours a"}}}
        ecrits = ocr.ecrire_cours_md(self.dest, "cours:42", cfg=cfg)
        self.assertEqual([os.path.basename(c) for c in ecrits], ["Cours A - texte des documents.md"])

    def test_index(self):
        """Plan 6.3 : compteurs par cours, volume mesure, documents a verifier, verifie exclu."""
        self.jeux()
        self.marquer("Cours B/Section 2/c.pdf", verifie=True)
        ocr.ecrire_index(self.dest)
        contenu = self.lire("index.md")
        lignes = contenu.split("\n")
        self.assertEqual(lignes[0], ms.MARQUE)
        self.assertIn("# Textes des cours", contenu)
        self.assertIn("- Cours A : 2 documents, 5 pages, ", contenu)
        self.assertIn("- Cours B : 1 document, 1 page, ", contenu)
        self.assertRegex(contenu, r"- Cours A : 2 documents, 5 pages, \d+,\d Mo")
        self.assertRegex(contenu, r"- Cours B : 1 document, 1 page, \d+,\d Mo")
        self.assertIn("## Documents à vérifier", contenu)
        # b.pdf : page 2 a 0,78 et page 3 sans texte, les deux seules lignes de sa section « Pages à vérifier ».
        # Le compte vient de cette section, pas de pages moins pages_texte (ecart 78).
        entree = ocr.charger_cache(self.dest)["documents"]["Cours A/Section 1/b.pdf"]
        self.assertIn(f"Cours A / Section 1 / b.pdf : confiance {ocr._virgule(entree['confiance'])}, "
                      "2 pages douteuses", contenu)
        self.assertNotIn("c.pdf", contenu)
        self.assertNotIn("a.pdf", contenu)
        self.assertNotIn(self.dest, contenu)
        # Le volume affiche est celui des .md du cours, mesure sur le disque (le fichier de cours en fait partie
        # quand il existe deja).
        poids = sum(os.path.getsize(self.sortie("Cours A", *p))
                    for p in (("Section 1", "a.pdf.md"), ("Section 1", "b.pdf.md")))
        self.assertIn(f"- Cours A : 2 documents, 5 pages, {ocr._volume(poids)}", contenu)
        ocr.ecrire_cours_md(self.dest, "tout")
        ocr.ecrire_index(self.dest)
        poids += os.path.getsize(self.sortie("Cours A", "Cours A - texte des documents.md"))
        self.assertIn(f"- Cours A : 2 documents, 5 pages, {ocr._volume(poids)}", self.lire("index.md"))

    def test_qualite(self):
        """Plan 4.4 : confiance a la francaise, lien relatif, page difficile presente, jamais omise."""
        self.jeux()
        self.marquer("Cours B/Section 2/c.pdf", verifie=True)
        ocr.ecrire_qualite(self.dest)
        contenu = self.lire("Qualité des textes.md")
        self.assertEqual(contenu.split("\n")[0], ms.MARQUE)
        self.assertIn("b.pdf", contenu)
        self.assertIn("(Cours A/Section 1/b.pdf.md)", contenu)   # lien relatif au .md du document
        self.assertIn("Cours A/Section 1/b.pdf.md", contenu)
        self.assertNotIn(self.dest, contenu)
        self.assertNotIn("a.pdf", contenu)                      # 0,93 : bon
        self.assertNotIn("c.pdf", contenu)                      # verifie : masque
        # La confiance affichee page par page est celle de la section de C2 (ecart 78) : page 2 a 0,78, page 3
        # blanche, et rien pour la page 1, qui est en « bon ».
        self.assertIn("- page 2 : confiance 0,78", contenu)
        self.assertIn("- page 3 : aucun texte détecté", contenu)
        self.assertNotIn("- page 1 : confiance", contenu)
        # Une page difficile n'est jamais omise (plan 4.4) : c.pdf, 0,55, etat difficile.
        self.marquer("Cours B/Section 2/c.pdf", verifie=False)
        ocr.ecrire_qualite(self.dest)
        contenu = self.lire("Qualité des textes.md")
        self.assertIn("c.pdf", contenu)
        self.assertIn("0,55", contenu)
        self.assertIn("(Cours B/Section 2/c.pdf.md)", contenu)
        # Une page sans texte est signalee : la page 3 de b.pdf est vide dans son .md.
        self.assertIn("aucun texte détecté", contenu)
        self.assertEqual(contenu.count("- page 1 : confiance 0,55"), 1)

    def test_jsonl(self):
        """Plan 6.4 : une ligne par page, cles du plan, UTF-8 sans BOM, a la demande seulement."""
        self.jeux()
        avant = sorted(os.walk(self.dest))
        flux = io.StringIO()
        nombre = ocr.ecrire_jsonl(self.dest, "tout", flux)
        self.assertEqual(nombre, 6)
        self.assertEqual(sorted(os.walk(self.dest)), avant)      # rien n'est ecrit sur le disque
        lignes = flux.getvalue().splitlines()
        self.assertEqual(len(lignes), 6)
        premiere = json.loads(lignes[0])
        self.assertEqual(set(premiere), {"cours", "section", "fichier", "page", "source", "confiance", "texte"})
        self.assertEqual((premiere["cours"], premiere["section"], premiere["fichier"], premiere["page"]),
                         ("Cours A", "Section 1", "a.pdf", 1))
        self.assertEqual(premiere["source"], "ocr")
        # `confiance` decrit la page (ecart 80) : C2 ne donne une valeur que dans « Pages à vérifier », donc la
        # page 1 de a.pdf, en « bon », n'en a pas.
        self.assertIsNone(premiere["confiance"])
        self.assertEqual([json.loads(l)["page"] for l in lignes[:2]], [1, 2])
        # Le texte d'une page ne porte que son propre texte : ni la section de controle de C2, ni la page suivante.
        self.assertNotIn("Pages à vérifier", flux.getvalue())
        self.assertEqual(json.loads(lignes[3])["confiance"], 0.78)   # page 2 de b.pdf, seule page cotee
        self.assertIsNone(json.loads(lignes[4])["confiance"])        # page 3 de b.pdf, sans texte
        self.assertEqual(json.loads(lignes[4])["texte"], "")
        self.assertEqual(json.loads(lignes[5])["texte"], "Photocopie peu lisible.")
        # Les trois dernieres lignes : deux pages de b.pdf puis c.pdf ; la page vide reste une ligne (ecart 77).
        self.assertEqual([(json.loads(l)["fichier"], json.loads(l)["page"]) for l in lignes[2:]],
                         [("b.pdf", 1), ("b.pdf", 2), ("b.pdf", 3), ("c.pdf", 1)])
        cfg = {"cours": {"42": {"dossier": "Cours B"}}}
        self.assertEqual(ocr.ecrire_jsonl(self.dest, "cours:42", io.StringIO(), cfg=cfg), 1)
        # Ecriture dans un fichier ouvert en binaire : UTF-8 sans BOM, une seule ligne par page.
        chemin = os.path.join(self.d, "export.jsonl")
        with open(chemin, "wb") as f:
            self.assertEqual(ocr.ecrire_jsonl(self.dest, "document:Cours A/Section 1/a.pdf", f), 2)
        brut = octets(chemin)
        self.assertFalse(brut.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(len(brut.decode("utf-8").splitlines()), 2)

    def test_derniere_page_vide_conservee(self):
        """Ecart 77 : C2 ecrit un marqueur par page, sans marqueur terminal. Une derniere page blanche reste une
        page du document : elle compte dans l'agregat, dans le JSONL et dans la qualite."""
        self.jeux()
        document = "Cours A/Section 1/b.pdf"
        texte = ocr.assembler_contexte(self.dest, f"document:{document}")
        self.assertIn("[source : Section 1/b.pdf, 3 pages]", texte)
        self.assertIn("[p. 3]", texte)
        self.assertEqual(ocr.ecrire_jsonl(self.dest, f"document:{document}", io.StringIO()), 3)
        ocr.ecrire_qualite(self.dest)
        self.assertIn("- page 3 : aucun texte détecté", self.lire("Qualité des textes.md"))

    def test_qualite_page_par_page_d_un_document_mixte(self):
        """Ecart 78 : la confiance de chaque page vient de « Pages à vérifier », pas de la moyenne du document.

        Un document mixte est enumere page par page : la page 1 native n'a rien a verifier, la page 2 porte 0,42,
        la page 3 est en « bon ». L'index compte les pages douteuses de la section, pas pages moins pages_texte.
        """
        self.jeux_mixte()
        ocr.ecrire_qualite(self.dest)
        contenu = self.lire("Qualité des textes.md")
        self.assertIn("Cours M / Section 1 / m.pdf", contenu)
        self.assertIn("- page 2 : confiance 0,42", contenu)
        self.assertEqual(contenu.count("- page "), 1)   # une page douteuse, pas une ligne par page du document
        ocr.ecrire_index(self.dest)
        entree = ocr.charger_cache(self.dest)["documents"]["Cours M/Section 1/m.pdf"]
        self.assertIn(f"m.pdf : confiance {ocr._virgule(entree['confiance'])}, 1 page douteuse",
                      self.lire("index.md"))

    def test_jsonl_decrit_la_page(self):
        """Ecart 80 : `source` et `confiance` d'une ligne decrivent la page, pas le document."""
        self.jeux_mixte()
        flux = io.StringIO()
        self.assertEqual(ocr.ecrire_jsonl(self.dest, "tout", flux), 3)
        lignes = [json.loads(l) for l in flux.getvalue().splitlines()]
        self.assertEqual([(l["page"], l["source"], l["confiance"]) for l in lignes],
                         [(1, "texte", None), (2, "ocr", 0.42), (3, "ocr", None)])

    def test_sortie_hors_coffre(self):
        """Ecart 79 : avec ocr_sortie_hors_coffre, les agregats suivent les .md hors du coffre et les orphelins y
        sont listes ; rien n'est ecrit sous dest/Textes."""
        cfg = {"ocr_sortie_hors_coffre": True}
        self.jeux(cfg)
        hors = os.path.join(self.d, "Textes")   # ms.APP_DIR est remplace par le dossier temporaire des tests
        self.assertFalse(os.path.isdir(os.path.join(self.dest, "Textes")))
        ecrits = ocr.ecrire_cours_md(self.dest, "tout")
        self.assertEqual(len(ecrits), 2)
        for chemin in ecrits:
            self.assertTrue(chemin.startswith(hors + os.sep), chemin)
        self.assertTrue(ocr.ecrire_index(self.dest).startswith(hors + os.sep))
        self.assertTrue(ocr.ecrire_qualite(self.dest).startswith(hors + os.sep))
        self.assertTrue(os.path.isfile(os.path.join(hors, "index.md")))
        self.assertFalse(os.path.isdir(os.path.join(self.dest, "Textes")))
        # Un PDF supprime : son .md est un orphelin, et il est liste dans l'index ecrit hors du coffre.
        os.remove(os.path.join(self.dest, "Cours A", "Section 1", "b.pdf"))
        orphelins = ocr._orphelins(self.dest, ocr.charger_cache(self.dest))
        self.assertEqual([o["chemin"] for o in orphelins], ["Cours A/Section 1/b.pdf"])
        self.assertTrue(os.path.isabs(orphelins[0]["sortie"]), orphelins[0]["sortie"])
        ocr.ecrire_index(self.dest)
        with open(os.path.join(hors, "index.md"), encoding="utf-8") as f:
            contenu = f.read()
        self.assertIn("b.pdf", contenu)
        self.assertIn("orphelin", contenu.lower())

    def test_volume_en_mo(self):
        """Ecart 82 : le volume de l'index est en Mo, pas en Ko (mutation _volume divisee par 1024)."""
        self.jeux()
        self.ecrire_nomme(self.sortie("Cours B", "Section 2", "gros.pdf.md"), "x" * (2 * 1024 * 1024))
        ocr.ecrire_index(self.dest)
        self.assertRegex(self.lire("index.md"), r"- Cours B : 1 document, 1 page, 2,0 Mo")

    def test_cours_sans_aucun_md(self):
        """Ecart 82 : un cours dont tous les .md manquent ne produit ni fichier de cours ni bloc dans le contexte."""
        self.jeux()
        for nom in ("a.pdf.md", "b.pdf.md"):
            os.remove(self.sortie("Cours A", "Section 1", nom))
        ecrits = ocr.ecrire_cours_md(self.dest, "tout")
        self.assertEqual([os.path.basename(c) for c in ecrits], ["Cours B - texte des documents.md"])
        texte = ocr.assembler_contexte(self.dest, "tout")
        self.assertNotIn("# Cours A", texte)
        self.assertIn("# Cours B", texte)

    def test_retour_partiel_sur_echec_d_ecriture(self):
        """Ecart 83 : la valeur de retour dit ce qui a ete ecrit, meme quand une ecriture echoue ensuite."""
        self.jeux()
        vrai = ocr.os.replace
        appels = []

        def echouer_au_second(*a, **kw):
            appels.append(a)
            if len(appels) == 2:
                raise OSError("disque plein")
            return vrai(*a, **kw)

        with mock.patch.object(ocr.os, "replace", echouer_au_second):
            ecrits = ocr.ecrire_cours_md(self.dest, "tout")
        self.assertEqual([os.path.basename(c) for c in ecrits], ["Cours A - texte des documents.md"])
        self.assertTrue(os.path.isfile(self.sortie("Cours A", "Cours A - texte des documents.md")))

        class Flux:
            def __init__(self):
                self.lignes = []

            def write(self, texte):
                if len(self.lignes) == 2:
                    raise OSError("disque plein")
                self.lignes.append(texte)

        flux = Flux()
        self.assertEqual(ocr.ecrire_jsonl(self.dest, "tout", flux), 2)
        self.assertEqual(len(flux.lignes), 2)

    def test_orphelins(self):
        """Invariant 11 : un .md de sortie sans document correspondant est liste, jamais supprime."""
        self.jeux()
        os.remove(os.path.join(self.dest, "Cours A", "Section 1", "b.pdf"))
        orphelins = ocr._orphelins(self.dest, ocr.charger_cache(self.dest))
        self.assertEqual([o["sortie"] for o in orphelins], ["Textes/Cours A/Section 1/b.pdf.md"])
        self.assertEqual(orphelins[0]["chemin"], "Cours A/Section 1/b.pdf")
        self.assertTrue(os.path.isfile(self.sortie("Cours A", "Section 1", "b.pdf.md")))
        ocr.ecrire_index(self.dest)
        self.assertIn("b.pdf", self.lire("index.md"))
        self.assertIn("orphelin", self.lire("index.md").lower())
        # Un .md de document present mais absent du cache est aussi un orphelin.
        os.makedirs(self.sortie("Cours C", "Section 3"))
        with open(self.sortie("Cours C", "Section 3", "inconnu.pdf.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("# inconnu.pdf\n")
        sorties = [o["sortie"] for o in ocr._orphelins(self.dest, ocr.charger_cache(self.dest))]
        self.assertIn("Textes/Cours C/Section 3/inconnu.pdf.md", sorties)

    def test_md_manquant_ignore(self):
        """Invariant 8 : un .md de document absent sort de l'agregat, il n'est pas invente."""
        self.jeux()
        os.remove(self.sortie("Cours A", "Section 1", "b.pdf.md"))
        texte = ocr.assembler_contexte(self.dest, "tout")
        self.assertNotIn("### b.pdf", texte)
        self.assertIn("### a.pdf", texte)
        ocr.ecrire_cours_md(self.dest, "tout")
        self.assertNotIn("### b.pdf", self.lire("Cours A", "Cours A - texte des documents.md"))
        self.assertFalse(os.path.exists(self.sortie("Cours A", "Section 1", "b.pdf.md")))
        # Un .md illisible (octets qui ne sont pas de l'UTF-8) est traite de la meme facon.
        with open(self.sortie("Cours A", "Section 1", "a.pdf.md"), "wb") as f:
            f.write(b"---\nsource: \"x\"\n---\n\xff\xfe pas de l'utf-8\n")
        self.assertNotIn("### a.pdf", ocr.assembler_contexte(self.dest, "tout"))

    def test_ecriture_atomique_sans_temporaire(self):
        """Aucun .tmp ne reste, et un echec d'ecriture n'abime pas le fichier precedent."""
        self.jeux()
        ocr.ecrire_cours_md(self.dest, "tout")
        ocr.ecrire_index(self.dest)
        ocr.ecrire_qualite(self.dest)
        restes = [os.path.join(racine, nom) for racine, _, noms in os.walk(self.dest)
                  for nom in noms if nom.endswith(".tmp")]
        self.assertEqual(restes, [])
        precedent = self.lire("index.md")
        vrai = os.replace

        def echouer(*a, **kw):
            raise OSError("disque plein")

        with mock.patch.object(ocr.os, "replace", echouer):
            with self.assertRaises(OSError):
                ocr._ecrire_texte(self.sortie("essai.md"), "x")
        self.assertEqual(self.lire("index.md"), precedent)
        self.assertEqual([os.path.join(r, n) for r, _, noms in os.walk(self.dest)
                          for n in noms if n.endswith(".tmp")], [])
        self.assertIs(os.replace, vrai)
        # Invariant 9 : par la porte publique, la meme panne ne sort pas en traceback. Le detail est signale et
        # l'appelant recoit la valeur vide de la fonction.
        with mock.patch.object(ocr.os, "replace", echouer), \
                mock.patch.object(ocr, "_signaler") as signaler:
            self.assertEqual(ocr.ecrire_index(self.dest), "")
            self.assertEqual(ocr.ecrire_qualite(self.dest), "")
            self.assertEqual(ocr.ecrire_cours_md(self.dest, "tout"), [])
        self.assertEqual(signaler.call_count, 3)
        self.assertEqual(self.lire("index.md"), precedent)

    def test_aucun_chemin_absolu_ni_marque_dans_les_sorties(self):
        """Invariant 1 et 9 : jamais de chemin absolu, jamais de trace technique, jamais de fichier hors Textes."""
        self.jeux()
        avant = {os.path.join(r, n) for r, _, noms in os.walk(self.dest) for n in noms}
        ocr.ecrire_cours_md(self.dest, "tout")
        ocr.ecrire_index(self.dest)
        ocr.ecrire_qualite(self.dest)
        apres = {os.path.join(r, n) for r, _, noms in os.walk(self.dest) for n in noms}
        nouveaux = apres - avant
        self.assertTrue(nouveaux)
        for chemin in nouveaux:
            self.assertTrue(chemin.startswith(os.path.join(self.dest, "Textes") + os.sep), chemin)
            contenu = octets(chemin).decode("utf-8")
            self.assertNotIn(self.dest, contenu)
            self.assertNotIn(self.d, contenu)
            self.assertNotIn("Traceback", contenu)
            self.assertNotIn(chr(0x2014), contenu)
            self.assertNotIn(chr(0x2013), contenu)
            self.assertFalse(contenu.startswith("\ufeff"))
        # Aucun original, aucune copie, aucun .bak (invariant 1).
        self.assertFalse([c for c in apres if c.endswith((".bak", ".orig"))])

    def test_aucun_appel_au_moteur_ni_au_reseau(self):
        """Invariant 6 : C5 ne rend rien, ne reconnait rien, n'ouvre aucun reseau."""
        self.jeux()
        appels = len(self.appels)
        with mock.patch.object(ocr, "executer", side_effect=AssertionError("moteur appelé")), \
                mock.patch.object(ocr, "rendre_page", side_effect=AssertionError("rendu appelé")), \
                mock.patch.object(ocr, "detecter", side_effect=AssertionError("détection appelée")), \
                mock.patch.object(ocr, "extraire_page", side_effect=AssertionError("page extraite")), \
                mock.patch.object(ocr, "extraire_document", side_effect=AssertionError("document extrait")), \
                mock.patch.object(ocr, "fabriquer_pdf_cherchable", side_effect=AssertionError("PDF fabriqué")), \
                mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("réseau")), \
                mock.patch.object(socket, "create_connection", side_effect=AssertionError("réseau")):
            ocr.ecrire_cours_md(self.dest, "tout")
            ocr.ecrire_index(self.dest)
            ocr.ecrire_qualite(self.dest)
            ocr.assembler_contexte(self.dest, "tout")
            ocr.ecrire_jsonl(self.dest, "tout", io.StringIO())
        self.assertEqual(len(self.appels), appels)
        source = octets(os.path.join(RACINE, "moodlesync", "ocr.py")).decode("utf-8")
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import socket", source)

    def test_portees_et_cache_absent(self):
        """Les portees de C5 suivent celles de la file (2.5) ; un coffre sans cache ne produit rien."""
        self.assertEqual(ocr.assembler_contexte(self.dest, "tout"), "")
        self.assertEqual(ocr.ecrire_jsonl(self.dest, "tout", io.StringIO()), 0)
        ocr.ecrire_index(self.dest)
        self.assertEqual(self.lire("index.md").split("\n")[0], ms.MARQUE)
        self.assertIn("# Textes des cours", self.lire("index.md"))
        self.jeux()
        cfg = {"cours": {"1": {"dossier": "Cours A"}, "2": {"dossier": "cours b"}}}
        self.assertEqual(ocr.assembler_contexte(self.dest, "cours:1", cfg=cfg).count("# Cours A"), 1)
        self.assertEqual(ocr.assembler_contexte(self.dest, "cours:2", cfg=cfg).count("# Cours B"), 1)
        self.assertEqual(ocr.ecrire_jsonl(self.dest, "cours:absent", io.StringIO(), cfg=cfg), 0)
        self.assertEqual(ocr.assembler_contexte(self.dest, "tout").count("### "), 3)
        # `sans_texte` ne filtre rien ici : C5 ne lit que des documents deja extraits (journal, choix 5).
        self.assertEqual(ocr.assembler_contexte(self.dest, "sans_texte").count("### "), 3)
        self.assertEqual(ocr.assembler_contexte(self.dest, "portee inconnue").count("### "), 3)
        self.assertEqual(ocr.assembler_contexte(self.dest, "document:Cours A\\Section 1\\a.pdf").count("### "), 1)


# ---------------------------------------------------------------------------------------------
# Tache Y2 : restauration de l'original, reconciliation de l'etat, `.ocr.part` orphelins, file apres synchronisation.
# ---------------------------------------------------------------------------------------------
def sha256_octets(donnees):
    return "sha256:" + hashlib.sha256(donnees).hexdigest()


class FauxUrlopen:
    """Doublure de urlopen (comme tests/test_moteur.py) : sert des octets, compte les appels, peut echouer."""

    def __init__(self, octets=b"", type_contenu="application/pdf", erreur=None):
        self.octets, self.type_contenu, self.erreur, self.requetes = octets, type_contenu, erreur, []

    def __call__(self, requete, timeout=None):
        self.requetes.append(requete.full_url)
        if self.erreur is not None:
            raise self.erreur
        octets, type_contenu = self.octets, self.type_contenu

        class Entetes:
            def get_content_type(s):
                return type_contenu

            def get(s, nom, defaut=None):
                return str(len(octets)) if nom == "Content-Length" else defaut

        class Reponse:
            headers = Entetes()
            flux = io.BytesIO(octets)

            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def read(s, n=-1):
                return s.flux.read(n)
        return Reponse()


class Restauration(PdfBase):
    """T15, T16 : `restaurer` retelecharge l'original, verifie son identite, remplace atomiquement, retire `genere`."""

    def setUp(self):
        super().setUp()
        self.source = pdf_minimal([SCAN, SCAN])
        self.cherchable = pdf_avec_info([SCAN, SCAN], {"/MoodleSyncGenere": json_compact(
            dict(MARQUE_VALIDE, taille_source=len(self.source), empreinte_source=sha256_octets(self.source), pages=2))})
        self.assertNotEqual(self.source, self.cherchable)
        self.genere = {"type": "pdf_cherchable", "taille_source": len(self.source),
                       "empreinte_source": sha256_octets(self.source), "taille_fichier": len(self.cherchable),
                       "empreinte_fichier": sha256_octets(self.cherchable), "pages": 2,
                       "date": "2026-11-08T10:00:00", "version": 1}
        self.poser(donnees=self.cherchable, etat=False)
        self.ecrire_etat(genere=self.genere)
        self.cfg = {"token": "jeton-secret"}

    def restaurer(self, serveur, **kw):
        with mock.patch.object(urllib.request, "urlopen", serveur):
            return ocr.restaurer(self.dest, self.cfg, self.rel, **kw)

    def intact(self):
        """Le PDF cherchable est la octet pour octet, `genere` toujours dans l'etat, aucun fichier en plus."""
        self.assertEqual(octets(self.chemin), self.cherchable)
        self.assertEqual(self.etat_genere(), self.genere)
        self.assertEqual(self.fichiers(), sorted([REL_C4, ms.ETAT]))

    def test_restauration_en_ligne(self):
        """T15 : taille et empreinte sources verifiees, remplacement, `genere` retire, `t` et `chemin` gardes, aucun
        `Originaux/` ni `.part`."""
        serveur = FauxUrlopen(self.source)
        resultat = self.restaurer(serveur)
        self.assertEqual(resultat, {"ok": True, "pages": 2})
        self.assertEqual(octets(self.chemin), self.source)
        entree = ms.charger_etat(self.dest)[self.cle_etat]
        self.assertNotIn("genere", entree)
        self.assertEqual((entree["t"], entree["chemin"]), (1760000000, self.rel.replace("/", os.sep)))
        self.assertEqual(self.fichiers(), sorted([REL_C4, ms.ETAT]))
        self.assertFalse(any("Originaux" in f or f.endswith((".part", ".orig", ".bak")) for f in self.fichiers()))
        self.assertEqual(len(serveur.requetes), 1)
        self.assertTrue(serveur.requetes[0].startswith(URL_MOODLE + "?"))
        self.assertIn("token=jeton-secret", serveur.requetes[0])

    def test_hors_ligne(self):
        """T15 : `URLError`, delai depasse, coupure ou erreur du serveur : `hors_ligne`, PDF cherchable inchange."""
        import urllib.error
        for erreur in (urllib.error.URLError("pas de reseau"), TimeoutError("delai"), ConnectionResetError("coupure"),
                       urllib.error.HTTPError(URL_MOODLE, 503, "indisponible", Message(), io.BytesIO(b""))):
            with self.subTest(type(erreur).__name__):
                with self.assertRaises(ocr.ErreurOcr) as c:
                    self.restaurer(FauxUrlopen(erreur=erreur))
                self.assertEqual(c.exception.code, "hors_ligne")
                self.assertEqual(str(c.exception), ocr.MESSAGES["hors_ligne"])
                self.assertNotIn("pas de reseau", str(c.exception))     # aucune trace technique (invariant 9)
                self.intact()

    def test_jeton_expire(self):
        """HTTP 401 : `SessionExpiree`, PDF cherchable intact."""
        import urllib.error
        with self.assertRaises(ms.SessionExpiree):
            self.restaurer(FauxUrlopen(erreur=urllib.error.HTTPError(URL_MOODLE, 401, "refuse", Message(), io.BytesIO(b""))))
        self.intact()

    def test_page_a_la_place_du_fichier(self):
        """Moodle repond 200 avec une page (cours ferme, jeton refuse) : erreur lisible, rien n'est remplace."""
        with self.assertRaises(ms.Erreur) as c:
            self.restaurer(FauxUrlopen(b"<html>acces refuse</html>", type_contenu="text/html"))
        self.assertNotIsInstance(c.exception, ocr.ErreurOcr)
        self.intact()

    def test_version_differente(self):
        """Invariant 13 : Moodle propose un autre contenu, aucun remplacement, `restauration_differente`."""
        autre = pdf_minimal([NATIF, NATIF])
        for contenu in (autre, self.source[:-1] + b"X"):      # taille differente, puis meme taille mais un octet change
            with self.subTest(len(contenu)):
                with self.assertRaises(ocr.ErreurOcr) as c:
                    self.restaurer(FauxUrlopen(contenu))
                self.assertEqual(c.exception.code, "restauration_differente")
                self.assertEqual(str(c.exception), ocr.MESSAGES["restauration_differente"])
                self.intact()

    def test_fichier_modifie_demande_confirmation(self):
        """T16 : identite differente de `genere.taille_fichier` et `empreinte_fichier` : `confirmer`, rien n'est ecrasé ni
        telecharge ; avec `confirme=True` seulement, la restauration a lieu."""
        edite = self.cherchable + b"\n%edite a la main\n"
        with open(self.chemin, "wb") as f:
            f.write(edite)
        serveur = FauxUrlopen(self.source)
        self.assertEqual(self.restaurer(serveur), {"confirmer": ocr.MESSAGES["modifie_main"]})
        self.assertEqual(serveur.requetes, [])                            # aucune requete avant l'accord
        self.assertEqual(octets(self.chemin), edite)
        self.assertEqual(self.etat_genere(), self.genere)
        self.assertEqual(self.restaurer(serveur, confirme=True), {"ok": True, "pages": 2})
        self.assertEqual(octets(self.chemin), self.source)
        self.assertEqual(len(serveur.requetes), 1)

    def test_fichier_modifie_meme_taille(self):
        """Un octet change sans changer la taille est aussi une modification a la main."""
        edite = bytearray(self.cherchable)
        edite[len(edite) // 2] ^= 0x55
        edite = bytes(edite)
        with open(self.chemin, "wb") as f:
            f.write(edite)
        self.assertEqual(self.restaurer(FauxUrlopen(self.source)), {"confirmer": ocr.MESSAGES["modifie_main"]})
        self.assertEqual(octets(self.chemin), edite)

    def test_fichier_verrouille(self):
        """Le remplacement echoue deux fois (PermissionError) : un nouvel essai apres la pause, puis `verrouille` ;
        PDF cherchable et `genere` intacts, aucun `.part`."""
        reel = os.replace

        def refuse(src, dst, *a, **kw):
            if str(src).endswith(".part"):
                raise PermissionError("ouvert dans Acrobat")
            return reel(src, dst, *a, **kw)

        with mock.patch.object(os, "replace", refuse):
            with self.assertRaises(ocr.ErreurOcr) as c:
                self.restaurer(FauxUrlopen(self.source))
        self.assertEqual((c.exception.code, str(c.exception)), ("verrouille", ocr.MESSAGES["verrouille"]))
        self.assertEqual(self.pauses, [ocr.PAUSE_VERROU])
        self.intact()

    def test_annulation(self):
        """`arreter()` : `Annule`, le `.part` existe vraiment au moment de l'arret puis disparait, PDF intact."""
        vus = []
        original = ms.recuperer

        def espion(url, token, partiel, *a, **kw):
            try:
                return original(url, token, partiel, *a, **kw)
            finally:
                vus.append(os.path.exists(partiel))

        with mock.patch.object(ms, "recuperer", espion):
            with self.assertRaises(ms.Annule):
                self.restaurer(FauxUrlopen(self.source), arreter=lambda: True)
        self.assertEqual(vus, [True])
        self.intact()

    def test_document_natif_rien_a_restaurer(self):
        """Entree d'etat sans `genere` : le fichier est deja l'original, aucune requete, aucun changement."""
        self.ecrire_etat()
        serveur = FauxUrlopen(self.source)
        self.assertEqual(self.restaurer(serveur), {"ok": True, "pages": 2})
        self.assertEqual(serveur.requetes, [])
        self.assertEqual(octets(self.chemin), self.cherchable)

    def test_jeton_absent(self):
        """Pas de jeton : `SessionExpiree` sans requete, PDF cherchable intact."""
        self.cfg = {}
        serveur = FauxUrlopen(self.source)
        with self.assertRaises(ms.SessionExpiree):
            self.restaurer(serveur)
        self.assertEqual(serveur.requetes, [])
        self.intact()

    def test_fichier_deja_source_apres_coupure(self):
        """Le fichier a deja l'identite de la source (coupure d'un remplacement) : `genere` retire, aucune requete."""
        with open(self.chemin, "wb") as f:
            f.write(self.source)
        serveur = FauxUrlopen(self.source)
        self.assertEqual(self.restaurer(serveur), {"ok": True, "pages": 2})
        self.assertEqual(serveur.requetes, [])
        self.assertIsNone(self.etat_genere())
        self.assertEqual(octets(self.chemin), self.source)

    def test_document_inconnu(self):
        """Aucune entree d'etat pour ce chemin : `non_suivi`, aucune requete."""
        ms.sauver_etat(self.dest, {})
        serveur = FauxUrlopen(self.source)
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.restaurer(serveur)
        self.assertEqual(c.exception.code, "non_suivi")
        self.assertEqual(serveur.requetes, [])

    def test_fichier_absent(self):
        os.remove(self.chemin)
        with self.assertRaises(ocr.ErreurOcr) as c:
            self.restaurer(FauxUrlopen(self.source))
        self.assertEqual(c.exception.code, "corrompu")

    def test_messages_du_contrat(self):
        """Section 5 du contrat, mot pour mot."""
        self.assertEqual(ocr.MESSAGES["hors_ligne"], "Impossible de retélécharger l'original sans connexion. "
                         "Ton PDF cherchable reste en place, avec ses pages d'origine. Réessaie une fois en ligne.")
        self.assertEqual(ocr.MESSAGES["restauration_differente"], "Moodle propose une version différente de celle "
                         "d'origine. Rien n'a été remplacé : lance une synchronisation.")

    def test_apres_restauration_le_fichier_est_natif(self):
        """Apres la restauration, l'etat n'annonce plus de `genere` et le fichier ne porte plus notre marque."""
        self.restaurer(FauxUrlopen(self.source))
        self.assertIsNone(self.etat_genere())
        self.assertIsNone(ocr.lire_marque(self.chemin))


class ReconcilierEtat(PdfBase):
    """Invariant 5 : une coupure entre l'ecriture de `genere` (etape 3) et `os.replace` (etape 4)."""

    def setUp(self):
        super().setUp()
        self.source = pdf_minimal([SCAN])
        self.cherchable = pdf_avec_info([SCAN], {"/Title": "x"})
        self.genere = {"type": "pdf_cherchable", "taille_source": len(self.source),
                       "empreinte_source": sha256_octets(self.source), "taille_fichier": len(self.cherchable),
                       "empreinte_fichier": sha256_octets(self.cherchable), "pages": 1,
                       "date": "2026-11-08T10:00:00", "version": 1}

    def mettre(self, contenu):
        self.poser(donnees=contenu, etat=False)
        self.ecrire_etat(genere=self.genere)

    def test_fichier_encore_la_source(self):
        self.mettre(self.source)
        self.assertEqual(ocr.reconcilier_etat(self.dest), 1)
        entree = ms.charger_etat(self.dest)[self.cle_etat]
        self.assertNotIn("genere", entree)
        self.assertEqual((entree["t"], entree["chemin"]), (1760000000, self.rel.replace("/", os.sep)))
        self.assertEqual(ms.charger_etat(self.dest)["_sections"], {"12": "Section 1"})   # le reste de l'etat est intact
        self.assertEqual(octets(self.chemin), self.source)

    def test_pdf_cherchable_en_place_laisse(self):
        self.mettre(self.cherchable)
        avant = self.fichier_etat()
        self.assertEqual(ocr.reconcilier_etat(self.dest), 0)
        self.assertEqual(self.fichier_etat(), avant)                      # l'etat n'est meme pas reecrit

    def test_fichier_modifie_laisse(self):
        """Ni la source ni le PDF cherchable : modifie a la main, `genere` garde (invariant 8)."""
        self.mettre(self.cherchable + b"\n%main\n")
        self.assertEqual(ocr.reconcilier_etat(self.dest), 0)
        self.assertEqual(self.etat_genere(), self.genere)

    def test_meme_taille_contenu_different_laisse(self):
        """Meme taille que la source mais un octet different : ce n'est pas la source, on ne touche a rien."""
        faux = bytearray(self.source)
        faux[len(faux) // 2] ^= 0x55
        self.mettre(bytes(faux))
        self.assertEqual(ocr.reconcilier_etat(self.dest), 0)
        self.assertEqual(self.etat_genere(), self.genere)

    def test_fichier_absent_ou_etat_vide(self):
        self.mettre(self.source)
        os.remove(self.chemin)
        self.assertEqual(ocr.reconcilier_etat(self.dest), 0)
        self.assertEqual(self.etat_genere(), self.genere)
        self.assertEqual(ocr.reconcilier_etat(os.path.join(self.d, "nulle-part")), 0)

    def test_genere_incomplet_ignore(self):
        self.poser(donnees=self.source, etat=False)
        self.ecrire_etat(genere={"type": "pdf_cherchable", "taille_source": len(self.source)})
        self.assertEqual(ocr.reconcilier_etat(self.dest), 0)

    def test_ensuite_fabriquer_refait(self):
        """Apres la reconciliation, la fabrication ne repond plus `modifie_main` pour un fichier encore natif."""
        self.mettre(self.source)
        ocr.reconcilier_etat(self.dest)
        genere = self.avec(ocr.fabriquer_pdf_cherchable, self.dest, self.rel, {})
        self.assertEqual(genere["empreinte_source"], self.genere["empreinte_source"])

    def test_parts_orphelins(self):
        """Invariant 5 : les `.ocr.part` abandonnes par une coupure sont supprimes, rien d'autre."""
        autre = os.path.join(self.dest, "Cours B", "x.pdf")
        for p in (self.chemin + ".ocr.part", autre + ".ocr.part"):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(b"abandonne")
        gardes = [self.chemin, autre + ".part", os.path.join(self.dest, "note.ocr.part.md")]
        for p in gardes:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(b"a garder")
        self.assertEqual(ocr.supprimer_parts_orphelins(self.dest), 2)
        self.assertEqual(self.fichiers(), sorted(os.path.relpath(g, self.dest).replace(os.sep, "/") for g in gardes))
        self.assertEqual(ocr.supprimer_parts_orphelins(self.dest), 0)
        self.assertEqual(ocr.supprimer_parts_orphelins(os.path.join(self.d, "nulle-part")), 0)


class MiseEnFileApresRepublication(DocumentsC3):
    """Y2 : `mettre_en_file_apres_sync` lit `republies_generes` (archive l'ancien texte) et `a_preparer`."""

    REL = "Cours A/article.pdf"

    def preparer(self):
        self.ranger(self.REL, [NATIF])
        self.extraire_doc(self.REL)
        self.md_actuel = os.path.join(self.dest, "Textes", "Cours A", "article.pdf.md")
        self.assertTrue(os.path.isfile(self.md_actuel))

    def archives(self):
        dossier = os.path.dirname(self.md_actuel)
        return sorted(n for n in os.listdir(dossier) if "(" + ms.T["ancienne"] in n)

    def rendu(self, **plus):
        return dict({"a_preparer": [self.REL], "republies_generes": [{"chemin": self.REL, "t_ancien": 1760000000}]}, **plus)

    def test_texte_archive_et_document_en_file(self):
        self.preparer()
        self.assertEqual(self.avec(ocr.mettre_en_file_apres_sync, self.dest, {}, self.rendu()), 1)
        self.assertFalse(os.path.exists(self.md_actuel))
        self.assertEqual(len(self.archives()), 1)
        self.assertTrue(self.archives()[0].startswith("article.pdf ("))
        file = ocr.charger_file(self.dest)
        self.assertEqual([(t["chemin"], t["etat"]) for t in file["taches"]], [(self.REL, "attente")])

    def test_deuxieme_appel_sans_erreur(self):
        """Deja archive : rien a archiver, la tache est deja en attente."""
        self.preparer()
        self.avec(ocr.mettre_en_file_apres_sync, self.dest, {}, self.rendu())
        self.assertEqual(self.avec(ocr.mettre_en_file_apres_sync, self.dest, {}, self.rendu()), 0)
        self.assertEqual(len(self.archives()), 1)

    def test_texte_edite_a_la_main_jamais_archive(self):
        """Invariant 8 : sans la cle `moodlesync`, le `.md` reste ou il est ; le document est quand meme mis en file."""
        self.preparer()
        with open(self.md_actuel, encoding="utf-8") as f:
            texte = f.read()
        edite = "\n".join(l for l in texte.split("\n") if not l.startswith("moodlesync:"))
        with open(self.md_actuel, "w", encoding="utf-8", newline="") as f:
            f.write(edite)
        self.assertEqual(self.avec(ocr.mettre_en_file_apres_sync, self.dest, {}, self.rendu()), 1)
        self.assertEqual(self.archives(), [])
        with open(self.md_actuel, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), edite)

    def test_archivage_impossible_n_arrete_pas_la_file(self):
        """Invariant 9 : une erreur du systeme de fichiers pendant l'archivage ne fait pas perdre la mise en file."""
        self.preparer()
        with mock.patch.object(ocr, "archiver_texte", side_effect=PermissionError("md ouvert")):
            self.assertEqual(self.avec(ocr.mettre_en_file_apres_sync, self.dest, {}, self.rendu()), 1)
        self.assertTrue(os.path.isfile(self.md_actuel))
        self.assertEqual([t["chemin"] for t in ocr.charger_file(self.dest)["taches"]], [self.REL])

    def test_entrees_invalides_ignorees(self):
        self.preparer()
        rendu = {"a_preparer": [], "republies_generes": [None, "x", {"chemin": 3, "t_ancien": 1}, {"chemin": self.REL},
                                                         {"chemin": self.REL, "t_ancien": True}]}
        self.assertEqual(self.avec(ocr.mettre_en_file_apres_sync, self.dest, {}, rendu), 0)
        self.assertTrue(os.path.isfile(self.md_actuel))
        self.assertEqual(self.avec(ocr.mettre_en_file_apres_sync, self.dest, {}, {"republies_generes": "non"}), 0)

    def test_document_republie_absent_de_a_preparer(self):
        """Un document republie qui n'est pas dans `a_preparer` est archive, pas mis en file : la file suit `a_preparer`."""
        self.preparer()
        rendu = {"a_preparer": [], "republies_generes": [{"chemin": self.REL, "t_ancien": 1760000000}]}
        self.assertEqual(self.avec(ocr.mettre_en_file_apres_sync, self.dest, {}, rendu), 0)
        self.assertEqual(len(self.archives()), 1)


class MoteurReel(unittest.TestCase):
    @unittest.skipUnless(_moteur_reel(), "Tesseract absent : reconnaissance reelle non executee")
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
