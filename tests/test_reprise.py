#!/usr/bin/env python3
"""Tests hors ligne de la reprise d'une lecture en plusieurs fois : marque-page, seances, vitesse par seance.
Aucun acces a Moodle, aucune fenetre : les fichiers de reglages sont rediriges vers un dossier temporaire.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, sys, json, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moodlesync import suivi as a, semaine as m, seances as sc, application as app
from tests.test_suivi import Dossier, AvecAnalyse, lire, lire_texte

PLAGES = [(225, 255)]                                            # consigne : "pp. 225-255", 31 pages


class Calculs(unittest.TestCase):
    def test_pages_entre_sans_plages(self):
        self.assertEqual(a.pages_entre([], 0, 14), 14)
        self.assertEqual(a.pages_entre([], 14, 30), 16)
        self.assertEqual(a.pages_entre([], 30, 30), 0)

    def test_pages_entre_avec_plages(self):
        self.assertEqual(a.pages_entre(PLAGES, 224, 255), 31)
        self.assertEqual(a.pages_entre(PLAGES, 224, 240), 16)
        self.assertEqual(a.pages_entre(PLAGES, 240, 255), 15)
        deux = [(12, 20), (40, 50)]                              # les pages entre les plages ne comptent pas
        self.assertEqual(a.pages_entre(deux, 11, 45), 9 + 6)
        self.assertEqual(a.pages_entre(deux, 20, 39), 0)

    def test_bornes(self):
        self.assertEqual(a.bornes([(40, 50), (12, 20)], 300), (12, 50))
        self.assertEqual(a.bornes([], 29), (1, 29))
        self.assertEqual(a.bornes([], None), (1, None))

    def test_vitesse_par_seance_ne_compte_qu_une_lecture(self):
        v = m.calcul_vitesse({"x#0": (10, 30), "x#1": (10, 30), "y": (30, 60)})
        self.assertEqual(v, (25.0, 2))                           # 50 pages en 2 h, deux lectures


class Seances(Dossier):
    def test_deux_seances_dont_une_sans_temps_ne_faussent_pas_la_vitesse(self):
        api = a.Semaine()
        r1 = api.marquer_page("x", 10, "30")                     # 10 p. en 30 min : 20 p./h
        self.assertEqual((r1["marque"], r1["lues"], r1["minutes"], r1["vitesse_seance"]), (10, 10, 30, 20.0))
        self.assertEqual(r1["vitesse_mesuree"], (20.0, 1))
        r2 = api.marquer_page("x", 30, "")                       # 20 p., aucun temps : avance sans toucher la vitesse
        self.assertEqual((r2["marque"], r2["lues"], r2["minutes"]), (30, 30, 30))
        self.assertEqual(r2["vitesse_mesuree"], (20.0, 1))
        self.assertIsNone(r2["vitesse_seance"])
        r3 = api.marquer_page("x", 40, "1 h")                    # 10 p. en 60 min : 10 p./h
        self.assertEqual(r3["vitesse_mesuree"], (13.3, 1))       # 20 p. chronométrées en 90 min (pas 40 p. en 90 min : 26,7)
        self.assertEqual(r3["minutes"], 90)

    def test_naif_aurait_donne_une_autre_vitesse(self):
        # Garde-fou de conception : 40 p. en 90 min donneraient 26,7 p./h ; seules 20 p. sont chronometrees.
        api = a.Semaine()
        api.marquer_page("x", 10, "30"); api.marquer_page("x", 30, ""); r = api.marquer_page("x", 40, "60")
        self.assertEqual(r["vitesse_mesuree"][0], 13.3)
        self.assertNotEqual(r["vitesse_mesuree"][0], round(40 / 1.5, 1))

    def test_persistance_et_rechargement(self):
        api = a.Semaine()
        api.marquer_page("x", 12, "20")
        s = lire(a.SUIVI)["lectures"]["x"]
        self.assertEqual(s["seances"][0]["a"], 12)
        self.assertEqual(s["minutes"], 20)
        self.assertEqual(a.marque(a.Semaine().suivi["lectures"]["x"]), 12)

    def test_page_non_croissante_refusee(self):
        api = a.Semaine()
        api.marquer_page("x", 10, "")
        self.assertIn("déjà à la page 10", api.marquer_page("x", 10, "")["erreur"])
        self.assertIn("erreur", api.marquer_page("x", 4, ""))
        self.assertEqual(len(api.suivi["lectures"]["x"]["seances"]), 1)

    def test_saisies_invalides(self):
        api = a.Semaine()
        for page in ("", "abc", 0, -3, 99999, None):
            with self.subTest(page=page):
                self.assertIn("erreur", api.marquer_page("x", page, ""))
        self.assertIn("illisible", api.marquer_page("x", 5, "bientôt")["erreur"])
        self.assertIn("16 h", api.marquer_page("x", 5, "20 h")["erreur"])
        self.assertFalse(api.suivi["lectures"].get("x", {}).get("seances"))

    def test_plages_de_la_consigne(self):
        api = a.Semaine()
        self.assertIn("225 à 255", api.marquer_page("x", 14, "", PLAGES)["erreur"])     # hors des pages de la consigne
        self.assertIn("erreur", api.marquer_page("x", 300, "", PLAGES))
        r = api.marquer_page("x", 240, "45", PLAGES, 412)
        self.assertEqual((r["lues"], r["seances"][0]["de"]), (16, 224))
        self.assertEqual(lire(a.SUIVI)["lectures"]["x"]["pages"], 31)                  # pages de la consigne, pas du PDF
        self.assertFalse(r["fait"])
        r = api.marquer_page("x", 255, "40", PLAGES, 412)
        self.assertEqual((r["lues"], r["fait"]), (31, True))                           # derniere page : lue
        self.assertTrue(r["seances"][-1]["fin"])

    def test_fin_de_lecture_sans_plages_selon_le_nombre_de_pages_du_pdf(self):
        api = a.Semaine()
        self.assertIn("erreur", api.marquer_page("x", 30, "", None, 29))               # le PDF n'a que 29 pages
        self.assertFalse(api.marquer_page("x", 28, "", None, 29)["fait"])
        self.assertTrue(api.marquer_page("x", 29, "", None, 29)["fait"])

    def test_suppression_revient_a_l_arret_precedent(self):
        api = a.Semaine()
        api.marquer_page("x", 10, "30")
        api.marquer_page("x", 29, "30", None, 29)               # termine la lecture
        r = api.supprimer_seance("x", 1)
        self.assertEqual((r["marque"], r["fait"], r["minutes"]), (10, False, 30))
        self.assertEqual(api.supprimer_seance("x", 0)["marque"], None)
        self.assertNotIn("seances", api.suivi["lectures"]["x"])
        self.assertIn("erreur", api.supprimer_seance("x", 5))
        self.assertIn("erreur", api.supprimer_seance("inconnu", 0))

    def test_une_case_cochee_a_la_main_reste_cochee_a_la_suppression(self):
        api = a.Semaine()
        api.marquer_page("x", 10, "")
        api.cocher("x", True)
        self.assertTrue(api.supprimer_seance("x", 0)["fait"])    # seule une seance "fin" decoche

    def test_temps_total_non_ecrasable_quand_la_lecture_a_des_seances(self):
        api = a.Semaine()
        api.marquer_page("x", 10, "30")
        self.assertIn("erreur", api.noter_temps("x", "5"))
        self.assertEqual(api.suivi["lectures"]["x"]["minutes"], 30)

    def test_lecture_sans_seance_garde_l_ancien_calcul(self):
        api = a.Semaine()
        r = api.noter_temps("y", "1 h 10", 21)
        self.assertEqual(r["vitesse_mesuree"], (18.0, 1))
        api.marquer_page("x", 10, "30")
        self.assertEqual(a.vitesse_mesuree(api.suivi), (18.6, 2))   # (21 + 10) p. en 100 min

    def test_chrono(self):
        api = a.Semaine()
        debut = api.demarrer_chrono("x")["chrono"]
        self.assertEqual(api.demarrer_chrono("x")["chrono"], debut)          # un seul chrono par lecture
        self.assertEqual(lire(a.SUIVI)["lectures"]["x"]["chrono"], debut)    # survit a la fermeture
        self.assertIsNone(api.annuler_chrono("x")["chrono"])
        api.demarrer_chrono("x")
        r = api.marquer_page("x", 5, "10")
        self.assertIsNone(r["chrono"])                                       # noter sa page arrete le chrono
        self.assertNotIn("chrono", api.suivi["lectures"]["x"])

    def test_seance_irrealiste_ecartee_de_la_vitesse(self):
        api = a.Semaine()
        r = api.marquer_page("x", 2, "600")                      # 2 p. en 10 h : chrono oublie
        self.assertEqual(r["vitesse_mesuree"], None)
        self.assertEqual(r["minutes"], 600)                      # le temps passe reste note

    def test_aucune_regression_sur_les_anciens_suivis(self):
        api = a.Semaine()
        api.suivi["lectures"]["old"] = {"fait": True, "minutes": 60, "pages": 20}
        d = a.etat_lecture(api.suivi["lectures"]["old"])
        self.assertEqual((d["marque"], d["lues"], d["seances"], d["chrono"]), (None, 0, [], None))
        self.assertEqual(a.vitesse_mesuree(api.suivi), (20.0, 1))


class Interface(AvecAnalyse, Dossier):
    def test_donnees_portent_le_marque_page(self):
        api = a.Semaine()
        R = self.analyse()
        ids = m.ids_lectures(R["fenetre"][0])
        api.marquer_page(ids[2], 240, "20", [(225, 255)], 412)       # Aristote, consigne pp. 225-255
        d = a.completer(a.donnees_interface(R, api.suivi, {"vitesse": 12}), api.suivi)
        json.dumps(d)
        l = d["seances"][0]["lectures"][2]
        self.assertEqual((l["marque"], l["lues"], l["minutes"], l["fait"]), (240, 16, 20, False))
        self.assertEqual(len(l["seances"]), 1)
        self.assertEqual(d["seances"][0]["lectures"][0]["marque"], None)

    def test_export_markdown_montre_la_page_et_le_temps(self):
        api = a.Semaine()
        R = self.analyse()
        ids = m.ids_lectures(R["fenetre"][0])
        api.marquer_page(ids[0], 14, "25", None, 29)
        api.exporter(R, a.prefs())
        ligne = [x for x in lire_texte(self.md).splitlines() if f"id:{ids[0]}" in x][0]
        self.assertIn("arrêtée p. 14", ligne)
        self.assertIn("réel : 25 min", ligne)
        etat, _, _, mesures, _ = m.lire_ancien(self.md)
        self.assertEqual(etat[ids[0]], (False, 25))

    def test_temps_modifie_dans_le_fichier_devient_une_seance_sans_page(self):
        api = a.Semaine()
        R = self.analyse()
        ident = m.ids_lectures(R["fenetre"][0])[0]
        api.marquer_page(ident, 14, "25", None, 29)
        api.exporter(R, a.prefs())
        texte = lire_texte(self.md).replace("réel : 25 min", "réel : 40 min")
        with open(self.md, "w", encoding="utf-8") as f:
            f.write(texte)
        self.assertEqual(a.fusionner_md(api.suivi, self.md), 1)
        v = api.suivi["lectures"][ident]
        self.assertEqual((v["minutes"], a.marque(v), a.pages_lues(v)), (40, 14, 14))
        self.assertEqual(a.vitesse_mesuree(api.suivi), (33.6, 1))    # 14 p. en 25 min : les 15 min ajoutees n'y changent rien

    def test_appels_du_pont(self):
        for nom in ("marquer_page", "supprimer_seance", "demarrer_chrono", "annuler_chrono"):
            with self.subTest(nom=nom):
                self.assertTrue(callable(getattr(app.Api, nom)))
        r = app.Api().marquer_page("zz", 7, "14")
        self.assertEqual((r["marque"], r["vitesse_seance"]), (7, 30.0))


if __name__ == "__main__":
    unittest.main()
