"""Tests hors ligne du lecteur de calendriers .ics (moodlesync/ics.py).

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, sys, unittest, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moodlesync import ics

DT = dt.datetime
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "donnees", "horaire_anonyme.ics")


def cal(*evenements, fin_ligne="\r\n"):
    lignes = ["BEGIN:VCALENDAR", "VERSION:2.0"]
    for e in evenements:
        lignes += ["BEGIN:VEVENT"] + e.strip().split("\n") + ["END:VEVENT"]
    lignes.append("END:VCALENDAR")
    return fin_ligne.join(lignes) + fin_ligne


def debuts(texte):
    return [o["debut"] for o in ics.lire(texte)["occurrences"]]


class Lignes(unittest.TestCase):
    def test_pliage_et_echappements(self):
        t = cal("UID:a\nDTSTART;TZID=Europe/Zurich:20261102T101500\nDTEND;TZID=Europe/Zurich:20261102T120000\n"
                "SUMMARY:Introduction à la recherche: vote\\, abstention et rapport au poli\n tique 2 (Séminaire)\n"
                "LOCATION:Salle\\; 2\\\\3\nDESCRIPTION:ligne 1\\nligne 2")
        o = ics.lire(t)["occurrences"][0]
        self.assertEqual(o["intitule"], "Introduction à la recherche: vote, abstention et rapport au politique 2 (Séminaire)")
        self.assertEqual(o["lieu"], "Salle; 2\\3")
        self.assertEqual((o["debut"], o["fin"]), (DT(2026, 11, 2, 10, 15), DT(2026, 11, 2, 12)))

    def test_bom_fins_de_ligne_lf_et_tabulation(self):
        t = "﻿" + cal("UID:a\nDTSTART:20261102T101500\nSUMMARY:Cours\n\t long", fin_ligne="\n")
        self.assertEqual(ics.lire(t)["occurrences"][0]["intitule"], "Cours long")

    def test_deux_points_dans_un_parametre_entre_guillemets(self):
        nom, params, valeur = ics.propriete('LOCATION;ALTREP="https://x.ch/a:b":Salle 1')
        self.assertEqual((nom, params["ALTREP"], valeur), ("LOCATION", "https://x.ch/a:b", "Salle 1"))

    def test_pas_un_calendrier(self):
        with self.assertRaises(ics.ErreurICS):
            ics.lire("<html>connexion requise</html>")
        with self.assertRaises(ics.ErreurICS):
            ics.lire("")


class Dates(unittest.TestCase):
    def test_tzid_heure_murale(self):
        self.assertEqual(debuts(cal("UID:a\nDTSTART;TZID=America/New_York:20261102T101500")), [DT(2026, 11, 2, 10, 15)])

    def test_utc_converti_en_heure_locale(self):
        attendu = DT(2026, 11, 2, 9, 15, tzinfo=dt.timezone.utc).astimezone().replace(tzinfo=None)
        self.assertEqual(debuts(cal("UID:a\nDTSTART:20261102T091500Z")), [attendu])

    def test_duree_sans_fin(self):
        o = ics.lire(cal("UID:a\nDTSTART:20261102T101500\nDURATION:PT1H45M"))["occurrences"][0]
        self.assertEqual(o["fin"], DT(2026, 11, 2, 12))

    def test_journee_entiere_et_annule_ignores(self):
        r = ics.lire(cal("UID:a\nDTSTART;VALUE=DATE:20261224\nSUMMARY:Vacances",
                         "UID:b\nDTSTART:20261102T101500\nSTATUS:CANCELLED",
                         "UID:c\nDTSTART:20261103T101500"))
        self.assertEqual(len(r["occurrences"]), 1)
        self.assertEqual(r["ignores"]["journee"], 1)
        self.assertEqual(r["ignores"]["annules"], 1)

    def test_date_illisible_comptee(self):
        r = ics.lire(cal("UID:a\nDTSTART:demain", "UID:b\nDTSTART:20261103T101500"))
        self.assertEqual((len(r["occurrences"]), r["ignores"]["illisibles"]), (1, 1))

    def test_alarme_imbriquee_ignoree(self):
        t = cal("UID:a\nDTSTART:20261102T101500\nSUMMARY:Cours\nBEGIN:VALARM\nTRIGGER:-PT15M\nDESCRIPTION:Rappel\nEND:VALARM")
        o = ics.lire(t)["occurrences"]
        self.assertEqual((len(o), o[0]["intitule"]), (1, "Cours"))


class Repetitions(unittest.TestCase):
    def test_until(self):
        d = debuts(cal("UID:a\nDTSTART:20261007T081500\nRRULE:FREQ=WEEKLY;UNTIL=20261028T235959Z"))
        self.assertEqual(d, [DT(2026, 10, 7, 8, 15), DT(2026, 10, 14, 8, 15), DT(2026, 10, 21, 8, 15),
                             DT(2026, 10, 28, 8, 15)])

    def test_until_date_seule(self):
        d = debuts(cal("UID:a\nDTSTART:20261007T081500\nRRULE:FREQ=WEEKLY;UNTIL=20261021"))
        self.assertEqual(len(d), 3)

    def test_count_et_intervalle(self):
        d = debuts(cal("UID:a\nDTSTART:20261005T101500\nRRULE:FREQ=WEEKLY;INTERVAL=2;COUNT=3"))
        self.assertEqual(d, [DT(2026, 10, 5, 10, 15), DT(2026, 10, 19, 10, 15), DT(2026, 11, 2, 10, 15)])

    def test_byday_multiple(self):
        d = debuts(cal("UID:a\nDTSTART:20261005T101500\nRRULE:FREQ=WEEKLY;BYDAY=MO,TH;COUNT=4"))
        self.assertEqual([x.date() for x in d], [dt.date(2026, 10, 5), dt.date(2026, 10, 8),
                                                 dt.date(2026, 10, 12), dt.date(2026, 10, 15)])

    def test_exdate_et_recurrence_id(self):
        t = cal("UID:s\nDTSTART;TZID=Europe/Zurich:20261005T101500\nDURATION:PT2H\n"
                "RRULE:FREQ=WEEKLY;COUNT=4\nEXDATE;TZID=Europe/Zurich:20261012T101500\nSUMMARY:Cours",
                "UID:s\nRECURRENCE-ID;TZID=Europe/Zurich:20261019T101500\n"
                "DTSTART;TZID=Europe/Zurich:20261020T140000\nDTEND;TZID=Europe/Zurich:20261020T160000\nSUMMARY:Cours",
                "UID:s\nRECURRENCE-ID;TZID=Europe/Zurich:20261026T101500\nDTSTART;TZID=Europe/Zurich:20261026T101500\n"
                "STATUS:CANCELLED")
        self.assertEqual(debuts(t), [DT(2026, 10, 5, 10, 15), DT(2026, 10, 20, 14)])

    def test_rdate_simple(self):
        d = debuts(cal("UID:a\nDTSTART:20261005T101500\nRRULE:FREQ=WEEKLY;COUNT=1\nRDATE:20261223T101500"))
        self.assertEqual(d, [DT(2026, 10, 5, 10, 15), DT(2026, 12, 23, 10, 15)])

    def test_regle_non_lue_signalee_pas_devinee(self):
        for regle in ("FREQ=DAILY;COUNT=5", "FREQ=MONTHLY;BYDAY=1MO", "FREQ=WEEKLY;BYSETPOS=1;BYDAY=MO,TU",
                      "FREQ=WEEKLY;BYDAY=1MO"):
            with self.subTest(regle=regle):
                r = ics.lire(cal(f"UID:a\nDTSTART:20261005T101500\nSUMMARY:Cours X\nRRULE:{regle}"))
                self.assertEqual([o["debut"] for o in r["occurrences"]], [DT(2026, 10, 5, 10, 15)])
                self.assertEqual(len(r["avertissements"]), 1)
                self.assertIn("Cours X", r["avertissements"][0])

    def test_sans_fin_borne(self):
        d = debuts(cal("UID:a\nDTSTART:20261005T101500\nRRULE:FREQ=WEEKLY"))
        self.assertTrue(100 <= len(d) <= 106)


class Fixture(unittest.TestCase):
    def test_structure_pocketcampus(self):
        r = ics.lire_fichier(FIXTURE)
        self.assertEqual(len(r["occurrences"]), 77)
        self.assertEqual(r["avertissements"], [])
        o = r["occurrences"][0]
        self.assertEqual((o["debut"], o["intitule"]), (DT(2026, 11, 2, 10, 15),
                                                       "Recherche empirique : vote, abstention et participation 2 (Séminaire)"))

    def test_fichier_absent(self):
        with self.assertRaises(ics.ErreurICS):
            ics.lire_fichier(FIXTURE + ".absent")


if __name__ == "__main__":
    unittest.main()
