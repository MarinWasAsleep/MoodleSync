"""Ecarts 299 a 302 : defauts qui n'apparaissaient que sous Windows (premier passage reel de la suite, CI run 42774342853).

Aucun de ces tests ne depend du systeme : les separateurs et les lettres de lecteur sont rejoues avec `ntpath`, et le
verrou d'un lecteur Windows sur `file.json` est simule par un `PermissionError` de `os.replace`.
"""
import ntpath
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moodlesync import api_textes, moteur as ms, ocr
from tests import test_api_textes as T
from tests import test_synchro_ocr as S


class LecteurSansChemin(unittest.TestCase):
    """Ecart 299 : un chemin absolu Windows porte une lettre de lecteur, il n'est pas refuse comme `C:x`."""

    def test_chemin_absolu_windows_n_est_pas_refuse(self):
        for brut in ("C:\\coffre\\Textes\\Cours A\\S1\\scan.pdf.md", "D:/coffre/x.md", "c:\\"):
            with self.subTest(brut):
                self.assertFalse(api_textes._lecteur_sans_chemin(brut, ntpath.isabs))

    def test_lettre_de_lecteur_sans_chemin_reste_refusee(self):
        for brut in ("C:x", "C:", "c:..\\x", "Z:Textes\\a.md", "C:Cours A/S1"):
            with self.subTest(brut):
                self.assertTrue(api_textes._lecteur_sans_chemin(brut, ntpath.isabs))

    @unittest.skipIf(os.name == "nt", "sous Windows, `C:\\x` est un chemin absolu")
    def test_sous_posix_la_lettre_de_lecteur_reste_refusee(self):
        """Sans lecteur sur ce systeme, `C:\\x` n'est pas absolu : refus comme avant l'ecart 299."""
        self.assertTrue(api_textes._lecteur_sans_chemin("C:\\x", os.path.isabs))

    def test_chemin_relatif_sans_lecteur(self):
        self.assertFalse(api_textes._lecteur_sans_chemin("Cours A/S1/scan.pdf.md", ntpath.isabs))


class ConfinementSeparateurs(T.Base):
    """Ecart 299 : le confinement accepte un chemin absolu a separateurs melanges, et refuse toujours la sortie."""

    def setUp(self):
        super().setUp()
        self.ranger("Cours A/S1/scan.pdf", [([], True)])
        os.makedirs(os.path.join(self.dest, "Textes", "Cours A", "S1"))
        self.md = os.path.join(self.dest, "Textes", "Cours A", "S1", "scan.pdf.md")
        with open(self.md, "w", encoding="utf-8") as f:
            f.write("Page un.")
        self.reel = os.path.realpath(self.md)

    def test_forme_normale_et_forme_melangee(self):
        cfg = self.config()
        autre = os.path.join(self.dest, "Textes", "Cours A") + "/S1/./scan.pdf.md"
        for forme in (self.md, autre, self.md.upper() if os.name == "nt" else self.md):
            with self.subTest(forme):
                self.assertEqual(self.api._ocr_confiner(self.dest, forme, cfg), self.reel)

    def test_hors_du_coffre_refuse(self):
        cfg = self.config()
        dehors = os.path.join(self.d, "dehors.md")
        with open(dehors, "w", encoding="utf-8") as f:
            f.write("x")
        for forme in (dehors, os.path.join(self.dest, "..", "dehors.md"), os.path.join(self.dest, "Textes", "..", "..",
                                                                                      "dehors.md")):
            with self.subTest(forme):
                self.assertIsNone(self.api._ocr_confiner(self.dest, forme, cfg))


class DejaPresentSeparateurs(S.Banc):
    """Ecart 300 : `deja_present` rend un chemin a separateurs du systeme, meme si l'etat en porte d'autres."""

    def test_chemin_de_l_etat_normalise(self):
        self.ecrire("Cours A/Section 2/autre.pdf", self.cherchable(url=S.URL_AUTRE))
        for ecrit in ("Cours A/Section 2/autre.pdf", "Cours A/Section 2/../Section 2/./autre.pdf",
                      "Cours A//Section 2//autre.pdf"):
            with self.subTest(ecrit):
                ms.sauver_etat(self.dest, {S.URL: {"t": S.T_MOODLE, "chemin": ecrit}})
                trouve = self.deja_present(self.item(), self.chemin("Cours A/Section 1/nulle.pdf"))
                self.assertEqual(trouve, self.chemin("Cours A/Section 2/autre.pdf"))
                self.assertEqual(trouve, os.path.normpath(trouve))


class RemplacementVerrouille(unittest.TestCase):
    """Ecart 302 : un lecteur qui tient `file.json` fait lever PermissionError a `os.replace` sous Windows."""

    def refuser(self, fois):
        reel = os.replace
        etat = {"refus": 0}

        def replace(src, dst, *a, **k):
            if etat["refus"] < fois:
                etat["refus"] += 1
                raise PermissionError(13, "simule : fichier tenu par un lecteur", str(dst))
            return reel(src, dst, *a, **k)
        return replace, etat

    def test_un_refus_passager_est_absorbe(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "file.json")
            replace, etat = self.refuser(ocr.ESSAIS_ECRITURE - 1)
            with mock.patch.object(os, "replace", replace), mock.patch.object(ocr, "_pause") as pause:
                self.assertTrue(ocr._ecrire_json(chemin, {"version": 1, "etat": "terminee"}))
            self.assertEqual(etat["refus"], ocr.ESSAIS_ECRITURE - 1)
            self.assertEqual(pause.call_count, ocr.ESSAIS_ECRITURE - 1)
            self.assertEqual((ocr._lire_json(chemin) or {}).get("etat"), "terminee")
            self.assertEqual(os.listdir(d), ["file.json"])

    def test_refus_durable_sort_telle_quelle_sans_tmp(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "file.json")
            replace, etat = self.refuser(10 ** 6)
            with mock.patch.object(os, "replace", replace), mock.patch.object(ocr, "_pause"):
                with self.assertRaises(PermissionError):
                    ocr._ecrire_json(chemin, {"version": 1})
            self.assertEqual(etat["refus"], ocr.ESSAIS_ECRITURE)
            self.assertEqual(os.listdir(d), [])

    def test_autre_erreur_pas_de_nouvel_essai(self):
        with tempfile.TemporaryDirectory() as d:
            appels = []

            def replace(src, dst, *a, **k):
                appels.append(dst)
                raise OSError(5, "autre erreur")
            with mock.patch.object(os, "replace", replace), mock.patch.object(ocr, "_pause") as pause:
                with self.assertRaises(OSError):
                    ocr._ecrire_json(os.path.join(d, "file.json"), {"version": 1})
            self.assertEqual((len(appels), pause.call_count), (1, 0))

    def test_ecriture_de_texte_meme_regle(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "a.md")
            replace, etat = self.refuser(2)
            with mock.patch.object(os, "replace", replace), mock.patch.object(ocr, "_pause"):
                ocr._ecrire_texte(chemin, "texte")
            with open(chemin, encoding="utf-8") as f:
                self.assertEqual(f.read(), "texte")


class FilEtVerrouDeFile(T.Base):
    """Ecart 302 : sans nouvel essai, un seul refus de `os.replace` sur `file.json` fait perdre des pages (mesure
    sous Linux par simulation : `1 != 4`, la signature relevee par la CI Windows)."""

    def setUp(self):
        super().setUp()
        c = self.config()
        c.update({"ocr": True})
        self.configurer(c)
        reel = os.replace
        self.refus, self.refus_voulus = 0, 1
        cible = self

        def replace(src, dst, *a, **k):
            # Le refus tombe sur les reecritures de `file.json` qui suivent la premiere page.
            if str(dst).endswith("file.json") and cible.pages_vues and cible.refus < cible.refus_voulus:
                cible.refus += 1
                raise PermissionError(13, "simule", str(dst))
            return reel(src, dst, *a, **k)
        p = mock.patch.object(os, "replace", replace)
        p.start()
        self.addCleanup(p.stop)

    def test_pause_et_reprise_malgre_un_refus(self):
        self.ranger("Cours A/S1/scan.pdf", [([], True)] * 4)
        self.delai_page = 0.03
        self.api.ocr_lancer("tout")
        self.assertTrue(self.attendre(lambda: self.pages_vues))
        self.assertIn("file", self.api.ocr_pause())
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "pause"))
        self.assertIn("file", self.api.ocr_reprendre())
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertEqual(len(self.pages_vues), 4)
        self.assertEqual(self.refus, 1)
        self.assertEqual([t["etat"] for t in self.fichier()["taches"]], ["fait"])

    def test_refus_pendant_la_fin_de_document(self):
        """Le refus tombe aussi sur la reecriture qui marque la tache `erreur` : la file ne reste pas bloquee."""
        self.refus_voulus = 2
        self.ranger("Cours A/S1/a.pdf", [([], True)] * 3)
        self.ranger("Cours A/S1/b.pdf", [([], True)])
        self.delai_page = 0.02
        self.assertIn("file", self.api.ocr_lancer("tout"))
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertEqual({t["etat"] for t in self.fichier()["taches"]}, {"fait"})


class ComparaisonACleOcr(unittest.TestCase):
    """Ecart 301 complete : `a_preparer` est en `/` (`relatif_cle`), les tests le comparent en `/` aussi."""

    def test_chemin_du_systeme_windows_ramene_a_la_forme_de_la_file(self):
        brut = ntpath.relpath("C:\\coffre\\Cours A\\Section 1\\scan.pdf", "C:\\coffre")
        self.assertEqual(brut, "Cours A\\Section 1\\scan.pdf")
        self.assertNotEqual([brut], [S.REL])                          # la comparaison non normalisee echoue sous Windows
        self.assertEqual([S.en_cle(brut, sep=ntpath.sep)], [S.REL])

    def test_forme_deja_en_barres_obliques_inchangee(self):
        self.assertEqual(S.en_cle(S.REL, sep=ntpath.sep), S.REL)
        self.assertEqual(S.en_cle(S.REL), S.REL)


if __name__ == "__main__":
    unittest.main()
