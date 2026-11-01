#!/usr/bin/env python3
"""Tests hors ligne du moteur de Ma semaine (aucun acces a Moodle).

Les titres reprennent les formes reellement rencontrees sur le Moodle de l'UNIL (automne 2026).
Lancer : python -m unittest prototypes/test_seances.py   (depuis la racine du depot)
"""
import os, sys, unittest, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seances as sc

D = dt.date
Y0 = 2026
LUN, MAR, MER, VEN = 0, 1, 2, 4


def seance(cid, titre, jour=None, cours=None):
    """Seance telle que ma_semaine.collecter la construit (sans les fichiers)."""
    an = sc.analyser_titre(titre, Y0)
    d, prec = sc.dater(an, {"jour": jour} if jour is not None else {})
    return {"cid": cid, "cours": cours or f"cours {cid}", "titre": titre, "analyse": an, "date": d,
            "precision": prec, "explicite": bool(d), "numero": sc.numero_seance(titre, court=bool(an)),
            "sans_travail": bool(sc.RE_SANS_TRAVAIL.search(titre))}


def lundis_de_reference():
    """Cours du lundi : ferie le 21.09, semaine intercalaire du 02.11, fin le 18.12 (lue ailleurs)."""
    return [
        seance("rech", "14 septembre", LUN), seance("rech", "21 septembre - Jour férié - Pas de cours", LUN),
        seance("rech", "2 novembre – Semaine intercalaire - Pas de cours", LUN),
        seance("rech", "14 décembre ", LUN),
        seance("inst", "Enseignement du 18.12.2026", VEN),
        seance("isp", "Séance 1 : lundi 14 septembre 2026", LUN),
    ]


class TitresDates(unittest.TestCase):
    def test_formes_de_dates(self):
        cas = {
            "Séance 7 - 9 novembre 2026": D(2026, 11, 9),
            "Séance 1 - 14 séptembre 2026": D(2026, 9, 14),          # faute reelle dans Moodle
            "S8 - 11/11 - Hobbes et l'état de nature": D(2026, 11, 11),
            "Enseignement du 13.11.2026": D(2026, 11, 13),
            "1er décembre « Contester l'ordre politique »": D(2026, 12, 1),
        }
        for titre, attendu in cas.items():
            with self.subTest(titre=titre):
                self.assertEqual(sc.analyser_titre(titre, Y0)["dates"][0], attendu)

    def test_semaine_et_alternatives(self):
        self.assertEqual(sc.analyser_titre("9 novembre - 15 novembre", Y0)["type"], "semaine")
        an = sc.analyser_titre('10-11 novembre - "Socialisation politique"', Y0)
        self.assertEqual(an["type"], "alternatives")
        self.assertEqual(sc.dater(an, {"jour": MER})[0], D(2026, 11, 11))

    def test_titres_sans_date(self):
        for titre in ["Séance 7. Sommes-nous socialisés une fois pour toutes ?", "1. Introduction",
                      "PREMIÈRE PARTIE", "Groupes, échéances et consignes"]:
            with self.subTest(titre=titre):
                self.assertIsNone(sc.analyser_titre(titre, Y0))


class Numeros(unittest.TestCase):
    def test_numeros(self):
        self.assertEqual(sc.numero_seance("Séance 7. Sommes-nous socialisés ?"), 7)
        self.assertEqual(sc.numero_seance("Présentation du cours : séance 1"), 1)
        self.assertEqual(sc.numero_seance("Session n° 3"), 3)
        self.assertEqual(sc.numero_seance("S8 - 11/11 - Hobbes", court=True), 8)

    def test_faux_numeros(self):
        self.assertIsNone(sc.numero_seance("Documents S2"))           # semestre 2, pas seance 2
        self.assertIsNone(sc.numero_seance("1. Introduction"))       # chapitre
        self.assertIsNone(sc.numero_seance("Semaine 3"))


class Calendrier(unittest.TestCase):
    def setUp(self):
        self.cal = sc.construire_calendrier(lundis_de_reference())

    def test_bornes_et_jours_sans_cours(self):
        self.assertEqual(self.cal["semestres"][(2026, "automne")], (D(2026, 9, 14), D(2026, 12, 20)))
        self.assertIn(D(2026, 9, 21), self.cal["sans_cours"])
        for j in range(2, 9):                                        # toute la semaine intercalaire
            self.assertIn(D(2026, 11, j), self.cal["sans_cours"])
        self.assertNotIn(D(2026, 9, 28), self.cal["sans_cours"])

    def test_pas_de_cours_local_ne_vaut_pas_pour_tous(self):
        cal = sc.construire_calendrier(lundis_de_reference() + [seance("x", "16 novembre - pas de cours", LUN)])
        self.assertNotIn(D(2026, 11, 16), cal["sans_cours"])

    def test_semaines_du_format_moodle_n_etendent_pas_le_semestre(self):
        cal = sc.construire_calendrier(lundis_de_reference() + [seance("m", "28 décembre - 3 janvier", LUN)])
        self.assertEqual(cal["semestres"][(2026, "automne")][1], D(2026, 12, 20))

    def test_config_prioritaire(self):
        cal = sc.construire_calendrier([], {"semestres": [["2026-09-14", "2026-12-18"]],
                                            "sans_cours": ["2026-09-21", ["2026-11-02", "2026-11-08"]]})
        self.assertEqual(sc.jours_de_cours(cal, LUN, (2026, "automne"))[:3],
                         [D(2026, 9, 14), D(2026, 9, 28), D(2026, 10, 5)])


class DatationParNumero(unittest.TestCase):
    """Cas reel : Intro. science politique (cours), 'Séance 7' sans date. Le seminaire du lundi, lui,
    ecrit 'Séance 7 - 9 novembre 2026' : la deduction doit retomber sur la meme date."""

    def setUp(self):
        self.cal = sc.construire_calendrier(lundis_de_reference())
        self.ancres = [(1, D(2026, 9, 14))]

    def dater(self, n, ancres=None, jour=LUN):
        return sc.dater_par_numero(n, self.ancres if ancres is None else ancres, self.cal, jour, D(2026, 11, 1))

    def test_saute_ferie_et_intercalaire(self):
        self.assertEqual(self.dater(2)[0], D(2026, 9, 28))
        self.assertEqual(self.dater(7)[0], D(2026, 11, 9))
        self.assertEqual(self.dater(8)[0], D(2026, 11, 16))
        self.assertEqual(self.dater(12)[0], D(2026, 12, 14))
        self.assertIn("21.09", self.dater(7)[1])
        self.assertIn("02.11", self.dater(7)[1])

    def test_toujours_signale_comme_deduit(self):
        self.assertTrue(self.dater(7)[1].startswith("date déduite"))

    def test_hors_semestre_non_date(self):
        d, raison = self.dater(13)
        self.assertIsNone(d)
        self.assertIn("hors du semestre", raison)

    def test_ancre_la_plus_proche(self):
        # Une ancre plus proche corrige une derive : si la seance 10 est datee du 07.12 (un decalage
        # que le calendrier ignore), la seance 11 suit la seance 10, pas la seance 1.
        d, _ = self.dater(11, [(1, D(2026, 9, 14)), (10, D(2026, 12, 7))])
        self.assertEqual(d, D(2026, 12, 14))

    def test_sans_jour_dans_l_horaire(self):
        d, raison = self.dater(7, jour=None)
        self.assertIsNone(d)
        self.assertIn("horaire.json", raison)

    def test_sans_ancre_signale_fortement(self):
        d, prec = self.dater(3, ancres=[])
        self.assertEqual(d, D(2026, 10, 5))                         # 14.09, (21.09 ferie), 28.09, 05.10
        self.assertIn("AUCUNE séance datée", prec)

    def test_ancre_hors_horaire_refusee(self):
        d, raison = self.dater(3, ancres=[(1, D(2026, 9, 15))])     # mardi, horaire : lundi
        self.assertIsNone(d)
        self.assertIn("à vérifier", raison)


class Controles(unittest.TestCase):
    """Chaque test reproduit une facon dont une seance peut disparaitre sans bruit."""

    def setUp(self):
        self.base = lundis_de_reference()
        self.cal = sc.construire_calendrier(self.base)
        self.debut, self.fin = D(2026, 11, 1), D(2026, 11, 15)

    def ctrl(self, seances, suivis):
        return sc.controles(seances, suivis, self.cal, self.debut, self.fin)

    def test_seance_attendue_absente(self):
        # Histoire internationale : sections datees jusqu'au 28.10 seulement, cours le mercredi.
        ss = [seance("hic", f"{j} octobre 2026", MER) for j in (21, 28)]
        msgs = self.ctrl(ss, {"hic": ("Histoire internationale", MER)})
        self.assertEqual(len(msgs), 1)
        self.assertIn("mercredi 11 novembre", msgs[0])               # le 04.11 est intercalaire

    def test_cours_sans_aucune_seance(self):
        msgs = self.ctrl([], {"ite": ("ITE", MAR)})
        self.assertEqual(len(msgs), 1)
        self.assertIn("mardi 10 novembre", msgs[0])

    def test_rien_a_signaler(self):
        ss = [seance("hip", "S8 - 11/11 - Hobbes", MER)]
        self.assertEqual(self.ctrl(ss, {"hip": ("Idées politiques", MER)}), [])

    def test_mauvais_jour(self):
        ss = [seance("irp", "Zoom politique du 12 novembre 2026", VEN),
              seance("irp", "Enseignement du 13.11.2026", VEN)]
        msgs = self.ctrl(ss, {"irp": ("Institutions", VEN)})
        self.assertEqual(len(msgs), 1)
        self.assertIn("jeudi", msgs[0])

    def test_ordre_numeros_dates(self):
        ss = [seance("hip", "S7 - 28/10 - Filmer", MER), seance("hip", "S8 - 21/10 - Hobbes", MER),
              seance("hip", "S9 - 11/11 - Leviathan", MER)]
        msgs = self.ctrl(ss, {"hip": ("Idées politiques", MER)})
        self.assertTrue(any("séance 8" in m and "séance 7" in m for m in msgs))

    def test_doublon(self):
        ss = [seance("v", "Séance 7 - 9 novembre 2026", LUN), seance("v", "Séance 8 - 9 novembre 2026", LUN)]
        msgs = self.ctrl(ss, {"v": ("Séminaire vote", LUN)})
        self.assertTrue(any("2 sections" in m for m in msgs))

    def test_meme_seance_decrite_deux_fois_pas_un_doublon(self):
        ss = [seance("v", "Séance 7 - 9 novembre 2026", LUN), seance("v", "Séance 7 : lundi 9 novembre", LUN)]
        self.assertEqual(self.ctrl(ss, {"v": ("Séminaire vote", LUN)}), [])

    def test_seance_un_jour_sans_cours(self):
        ss = [seance("x", "3 novembre - Exposés", MAR), seance("x", "10 novembre - Suite", MAR)]
        msgs = self.ctrl(ss, {"x": ("Cours du mardi", MAR)})
        self.assertTrue(any("sans cours" in m for m in msgs))

    def test_pas_de_cours_annonce_n_est_pas_une_alerte(self):
        ss = [seance("sem", "3-4 novembre - Semaine intercalaire - pas de séance", MER),
              seance("sem", "10-11 novembre - Socialisation", MER)]
        self.assertEqual(self.ctrl(ss, {"sem": ("Séminaire ISP", MER)}), [])

    def test_cours_sans_jour(self):
        msgs = self.ctrl([], {"n": ("Nouveau cours", None)})
        self.assertIn("pas de jour dans horaire.json", msgs[0])


class BoutEnBout(unittest.TestCase):
    """Le cas qui a motive ces controles : 25 seances numerotees sans date (ISP cours)."""

    def test_isp_cours(self):
        ss = lundis_de_reference() + [seance("isp", f"Séance {n}. Titre", LUN) for n in range(1, 26)]
        cal = sc.construire_calendrier(ss)
        ancres = [(s["numero"], s["date"]) for s in ss if s["cid"] == "isp" and s["explicite"] and s["numero"]]
        for s in ss:
            if not s["date"] and s["numero"]:
                s["date"], s["precision"] = sc.dater_par_numero(s["numero"], ancres, cal, LUN, D(2026, 11, 1))
        datees = {s["numero"]: s["date"] for s in ss if s["cid"] == "isp" and s["date"] and not s["explicite"]}
        self.assertEqual(len(datees), 12)                           # 12 seances en automne, 13 au printemps
        self.assertEqual(datees[7], D(2026, 11, 9))
        msgs = sc.controles([s for s in ss if s["date"]], {"isp": ("ISP cours", LUN)}, cal,
                            D(2026, 11, 1), D(2026, 11, 15))
        self.assertEqual(msgs, [])


if __name__ == "__main__":
    unittest.main()
