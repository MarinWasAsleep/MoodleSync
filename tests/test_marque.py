#!/usr/bin/env python3
"""Tests de structure de `moodlesync/marque.py` (tache Y1a, ecart 6).

Test de structure, pas de comportement : la marque est lue dans un module feuille pour que
`moteur.py` puisse l'appeler sans que `ocr.py`, qui importe `moteur`, ne referme le cycle.
Les imports sont faits dans un sous-processus neuf : l'ordre ne depend d'aucun module deja
charge par la suite de tests. Aucun acces reseau.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t . -v
"""
import os, subprocess, sys, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import marque, ocr


def _importer(*modules):
    """(code de retour, sortie d'erreur) de l'import de `modules`, dans cet ordre, dans un Python neuf."""
    commande = [sys.executable, "-c", "import " + ", ".join(modules)]
    environnement = dict(os.environ, PYTHONPATH=RACINE)
    processus = subprocess.run(commande, cwd=RACINE, env=environnement, capture_output=True, text=True)
    return processus.returncode, processus.stderr


class TestModuleFeuille(unittest.TestCase):
    """Le cycle moteur -> marque et marque -> moteur ne se referme plus par ocr."""

    def test_ordre_des_imports_sans_cycle(self):
        for ordre in (("moodlesync.moteur", "moodlesync.marque"),
                      ("moodlesync.marque", "moodlesync.moteur"),
                      ("moodlesync.marque", "moodlesync.moteur", "moodlesync.ocr")):
            with self.subTest(ordre=ordre):
                code, erreur = _importer(*ordre)
                self.assertEqual(code, 0, erreur)

    def test_marque_n_importe_rien_du_paquet(self):
        with open(os.path.join(RACINE, "moodlesync", "marque.py"), encoding="utf-8") as f:
            source = f.read()
        for motif in ("from .", "from moodlesync", "import moodlesync"):
            self.assertNotIn(motif, source)

    def test_ocr_reexporte_lire_marque(self):
        self.assertIs(ocr.lire_marque, marque.lire_marque)
        self.assertIs(ocr.CLE_MARQUE, marque.CLE_MARQUE)


if __name__ == "__main__":
    unittest.main()
