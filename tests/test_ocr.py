#!/usr/bin/env python3
"""Tests hors ligne de la detection du moteur Tesseract (ocr.py, tache C1).

Le sous-processus est remplace par une doublure (aucun tesseract reel), le registre Windows est
simule, et le chemin est hors du PATH. TESSDATA_PREFIX est pose, une langue demandee manque : la
detection doit trouver le moteur, respecter le dossier de donnees et se replier sur une langue
disponible. Aucun acces reseau.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t . -v
"""
import os, sys, tempfile, time, unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
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


if __name__ == "__main__":
    unittest.main()
