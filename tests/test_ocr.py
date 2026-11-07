#!/usr/bin/env python3
"""Tests hors ligne de la detection du moteur Tesseract (ocr.py, tache C1).

Le sous-processus est remplace par une doublure (aucun tesseract reel), le registre Windows est
simule, et le chemin est hors du PATH. TESSDATA_PREFIX est pose, une langue demandee manque : la
detection doit trouver le moteur, respecter le dossier de donnees et se replier sur une langue
disponible. Aucun acces reseau.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t . -v
"""
import os, sys, tempfile, unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import ocr


VERSION = b"tesseract 5.5.3.20260724\n leptonica-1.87.0\n"
LANGS = b"List of available languages (3):\neng\nfra\nosd\n"


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
        if args[-1] == "--version":
            return 0, VERSION, b""
        if args[-1] == "--list-langs":
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
        # deu manque dans les langues detectees : repli sur fra, signale.
        self.assertEqual(bloc["langues_effectives"], "fra")
        self.assertTrue(bloc["repli"])
        self.assertEqual(bloc["message"], "")

        # reglages_depuis : langues effectives apres repli, et les autres cles du contrat 3.1.
        self.assertEqual(reglages, {"langues": "fra", "dpi": 300, "psm": 3, "oem": 1,
                                    "moteur": "5.5.3", "tessdata": self.tessdata})


if __name__ == "__main__":
    unittest.main()
