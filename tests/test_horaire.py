"""Tests hors ligne de l'horaire de Ma semaine (moodlesync/horaire.py, api_horaire.py) et de son
branchement dans seances.py. Aucun acces reseau : l'abonnement est simule. Les reglages sont rediriges
vers un dossier temporaire.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, sys, json, tempfile, unittest, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moodlesync import horaire, ics, seances as sc, moteur as ms, api_horaire

D = dt.date
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "donnees", "horaire_anonyme.ics")
SEMINAIRE = "Introduction à la discipline (Séminaire)"
MOODLE = {"101": "SEM_Introduction à la discipline (2026-2027)", "102": "COURS_Introduction à la discipline (2026-2027)",
          "103": "SEM_Recherche empirique : vote, abstention et participation II (2026-2027)",
          "104": "COURS_Histoire des idées (2026-2027)"}


def lire_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return f.read()


class Reglages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.anciens = (horaire.CHEMIN, ms.APP_DIR, ms.ERREURS)
        horaire.CHEMIN = os.path.join(self.tmp.name, "horaire_ics.json")
        ms.APP_DIR = self.tmp.name                       # horaire.json lu par seances.charger_horaire
        ms.ERREURS = os.path.join(self.tmp.name, "erreurs.txt")

    def tearDown(self):
        horaire.CHEMIN, ms.APP_DIR, ms.ERREURS = self.anciens
        self.tmp.cleanup()

    def horaire_json(self, contenu):
        with open(os.path.join(self.tmp.name, "horaire.json"), "w", encoding="utf-8") as f:
            json.dump(contenu, f)

    def importer(self):
        horaire.noter_cours_moodle([{"id": int(k), "fullname": v} for k, v in MOODLE.items()])
        return horaire.importer_texte(lire_fixture(), {"type": "fichier", "nom": "horaire_anonyme.ics"})

    def cours(self, h, intitule):
        return next(c for c in h["cours"] if c["intitule"] == intitule)


class Groupes(Reglages):
    def test_cinq_groupes_a_choisir(self):
        c = self.cours(self.importer(), SEMINAIRE)
        self.assertEqual(len(c["groupes"]), 5)
        self.assertFalse(any(g["suivi"] for g in c["groupes"]))
        self.assertTrue(horaire.a_choisir(c))
        self.assertEqual(horaire.libelle_groupe(c["groupes"][4]), "mercredi 10:15 à 12:00, Bâtiment B 205 BAT-205 (7 séances)")
        self.assertEqual(c["groupes"][4]["dates"][:2], ["2026-11-04", "2026-11-11"])

    def test_groupe_unique_coche_d_office(self):
        c = self.cours(self.importer(), "Histoire des idées (Cours)")
        self.assertEqual([g["suivi"] for g in c["groupes"]], [True])
        self.assertFalse(horaire.a_choisir(c))

    def test_choix_gardes_au_reimport(self):
        h = self.importer()
        c = self.cours(h, SEMINAIRE)
        horaire.choisir_groupe(c["id"], c["groupes"][4]["id"], True)
        horaire.confirmer(c["id"], "101")
        c2 = self.cours(self.importer(), SEMINAIRE)
        self.assertEqual([g["suivi"] for g in c2["groupes"]], [False, False, False, False, True])
        self.assertEqual(c2["moodle"]["confirme"], "101")

    def test_groupe_ou_cours_inconnu(self):
        self.importer()
        with self.assertRaises(ms.Erreur):
            horaire.choisir_groupe("nexistepas", "x", True)

    def test_calendrier_vide(self):
        with self.assertRaises(ics.ErreurICS):
            horaire.importer_texte("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", {"type": "fichier", "nom": "x.ics"})


class Rapprochement(Reglages):
    def test_genre_departage(self):
        self.assertEqual(horaire.similarite(SEMINAIRE, MOODLE["101"]), 1.0)
        self.assertEqual(horaire.similarite(SEMINAIRE, MOODLE["102"]), 0.5)
        self.assertEqual(horaire.proposer(SEMINAIRE, MOODLE), "101")
        self.assertEqual(horaire.proposer("Introduction à la discipline (Cours)", MOODLE), "102")

    def test_chiffres_romains_et_ponctuation(self):
        self.assertEqual(horaire.proposer("Recherche empirique : vote, abstention et participation 2 (Séminaire)", MOODLE), "103")

    def test_rien_de_proche_ou_ambigu(self):
        self.assertIsNone(horaire.proposer("Biologie cellulaire (Cours)", MOODLE))
        self.assertIsNone(horaire.proposer("Introduction à la discipline", {"1": "Introduction à la discipline, groupe 1",
                                                                            "2": "Introduction à la discipline, groupe 2"}))

    def test_proposition_jamais_utilisee_sans_confirmation(self):
        h = self.importer()
        self.assertEqual(self.cours(h, "Histoire des idées (Cours)")["moodle"]["propose"], "104")
        self.assertNotIn("104", horaire.horaire_effectif())

    def test_confirmation_et_aucun(self):
        c = self.cours(self.importer(), "Histoire des idées (Cours)")
        horaire.confirmer(c["id"], "104")
        e = horaire.horaire_effectif()["104"]
        self.assertEqual((e["jour"], e["heure"], e["source"]), (2, "08:30", horaire.SOURCE))
        self.assertEqual(e["dates"][0], "2026-11-04")
        self.assertEqual(e["heures"]["2026-11-04"], "08:30")
        horaire.confirmer(c["id"], "aucun")
        self.assertNotIn("104", horaire.horaire_effectif())
        with self.assertRaises(ms.Erreur):
            horaire.confirmer(c["id"], "999")                      # pas un de tes cours

    def test_cours_a_choisir_signale_une_fois_confirme(self):
        c = self.cours(self.importer(), SEMINAIRE)
        self.assertEqual(horaire.avertissements(), [])
        horaire.confirmer(c["id"], "101")
        self.assertEqual(len(horaire.avertissements()), 1)
        self.assertNotIn("101", horaire.horaire_effectif())        # aucun groupe : rien n'est date


class Migration(Reglages):
    def test_horaire_json_garde_et_complete(self):
        self.horaire_json({"104": {"jour": 0, "heure": "09:00", "controle": False, "titre": "HIP"},
                           "999": {"suivi": False}, "calendrier": {"sans_cours": ["2026-11-11"]}})
        c = self.cours(self.importer(), "Histoire des idées (Cours)")
        horaire.confirmer(c["id"], "104")
        e = horaire.horaire_effectif()
        self.assertEqual((e["104"]["jour"], e["104"]["heure"]), (2, "08:30"))   # le .ics confirme l'emporte
        self.assertEqual((e["104"]["controle"], e["104"]["titre"]), (False, "HIP"))
        self.assertEqual(e["999"], {"suivi": False})
        self.assertEqual(e["calendrier"], {"sans_cours": ["2026-11-11"]})
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "horaire.json")))

    def test_indice_horaire_json_unique(self):
        self.horaire_json({"101": {"jour": 1, "heure": "12:15"}})
        c = self.cours(self.importer(), SEMINAIRE)
        horaire.confirmer(c["id"], "101")
        c = self.cours(horaire.charger(), SEMINAIRE)
        self.assertEqual([g["suivi"] for g in c["groupes"]], [False, False, True, False, False])

    def test_indice_horaire_json_ambigu_rien_coche(self):
        self.horaire_json({"101": {"jour": 2, "heure": "10:15"}})       # deux groupes le mercredi a 10:15
        c = self.cours(self.importer(), SEMINAIRE)
        horaire.confirmer(c["id"], "101")
        self.assertFalse(any(g["suivi"] for g in self.cours(horaire.charger(), SEMINAIRE)["groupes"]))


class Abonnement(Reglages):
    def setUp(self):
        super().setUp()
        self.ancien = horaire.telecharger
        self.reponse = lire_fixture()

        def faux(adresse):
            if isinstance(self.reponse, Exception):
                raise self.reponse
            self.demande = adresse
            return self.reponse
        horaire.telecharger = faux

    def tearDown(self):
        horaire.telecharger = self.ancien
        super().tearDown()

    def test_adresses(self):
        self.assertEqual(horaire.adresse_valide(" webcal://exemple.ch/cal/abc.ics "), "https://exemple.ch/cal/abc.ics")
        for mauvaise in ("http://exemple.ch/x.ics", "ftp://exemple.ch/x", "exemple.ch/x.ics", "https:// x"):
            with self.subTest(adresse=mauvaise), self.assertRaises(ms.Erreur):
                horaire.adresse_valide(mauvaise)

    def test_abonner_puis_relire_puis_retirer(self):
        h = horaire.regler_abonnement("webcal://exemple.ch/cal/jeton123.ics")
        self.assertEqual(h["abonnement"], "https://exemple.ch/cal/jeton123.ics")
        self.assertEqual(h["source"]["nom"], "exemple.ch")                # jamais le jeton du lien
        self.assertEqual(len(h["cours"]), 7)
        self.assertIsNone(horaire.actualiser_abonnement())
        h = horaire.regler_abonnement("")
        self.assertIsNone(h["abonnement"])
        self.assertEqual(len(h["cours"]), 7)                              # l'horaire importe reste

    def test_echec_de_relecture_garde_l_horaire_et_ne_leve_pas(self):
        horaire.regler_abonnement("https://exemple.ch/cal.ics")
        self.reponse = ms.Erreur("Le serveur de l'horaire ne répond pas.")
        msg = horaire.actualiser_abonnement()
        self.assertIn("ne répond pas", msg)
        h = horaire.charger()
        self.assertEqual(len(h["cours"]), 7)
        self.assertTrue(any("relecture" in a for a in horaire.avertissements()))
        self.reponse = KeyError("imprevu")
        self.assertIn("erreur imprévue", horaire.actualiser_abonnement())

    def test_sans_abonnement_rien_ne_part(self):
        self.reponse = AssertionError("aucun acces reseau attendu")
        self.assertIsNone(horaire.actualiser_abonnement())


class Branchement(unittest.TestCase):
    """Datation des seances numerotees par les dates reelles du .ics (seances.py)."""

    def setUp(self):
        sem = sc.semestre(D(2026, 10, 1))
        self.cal = {"semestres": {sem: (D(2026, 9, 14), D(2026, 12, 20))}, "sans_cours": {}}
        # Le .ics couvre du 4 novembre au 16 decembre ; pas de cours le 11 novembre.
        self.reelles = [D(2026, 11, 4), D(2026, 11, 18), D(2026, 11, 25), D(2026, 12, 2), D(2026, 12, 9), D(2026, 12, 16)]
        self.ancres = [(6, D(2026, 10, 28))]                 # seance 6 datee dans Moodle

    def dater(self, n, reelles=True):
        return sc.dater_par_numero(n, self.ancres, self.cal, 2, D(2026, 11, 1), self.reelles if reelles else None)

    def test_semaine_absente_du_ics_sautee(self):
        self.assertEqual(self.dater(7)[0], D(2026, 11, 4))
        d, prec = self.dater(8)
        self.assertEqual(d, D(2026, 11, 18))
        self.assertIn("ton horaire (.ics)", prec)
        self.assertEqual(self.dater(8, reelles=False)[0], D(2026, 11, 11))   # sans .ics : chaque semaine

    def test_hors_periode_couverte_retour_au_jour(self):
        self.assertEqual(self.dater(5)[0], D(2026, 10, 21))
        self.assertIn("un mercredi de cours", self.dater(5)[1])

    def test_sans_jour_mais_avec_ics(self):
        d, _ = sc.dater_par_numero(2, [], self.cal, None, D(2026, 11, 1), self.reelles)
        self.assertEqual(d, D(2026, 11, 18))
        self.assertIsNone(sc.dater_par_numero(2, [], self.cal, None, D(2026, 11, 1))[0])

    def test_controles_avec_dates_reelles(self):
        suivis = {1: {"nom": "Cours X", "jour": 2, "source": horaire.SOURCE, "controle": True, "dates": self.reelles}}
        seances = [{"cid": 1, "date": d, "titre": f"S{i}", "numero": i, "explicite": True, "analyse": None}
                   for i, d in enumerate([D(2026, 11, 4), D(2026, 11, 25)], start=7)]
        alertes = sc.controles(seances, suivis, self.cal, D(2026, 11, 2), D(2026, 11, 29))
        manques = [a for a in alertes if "aucune séance trouvée" in a]
        self.assertEqual(len(manques), 1)
        self.assertIn("18 novembre", manques[0])                 # le 11, absent du .ics, n'est pas reclame
        self.assertNotIn("11 novembre", manques[0])

    def test_seance_deplacee_selon_le_ics_pas_signalee(self):
        reelles = self.reelles + [D(2026, 11, 12)]               # seance exceptionnelle un jeudi
        suivis = {1: {"nom": "Cours X", "jour": 2, "source": horaire.SOURCE, "controle": True, "dates": reelles}}
        seances = [{"cid": 1, "date": D(2026, 11, 12), "titre": "S8", "numero": 8, "explicite": True,
                    "analyse": {"type": "date"}}]
        alertes = sc.controles(seances, suivis, self.cal, D(2026, 11, 9), D(2026, 11, 15))
        self.assertFalse(any("tombe un" in a for a in alertes))


class Pont(Reglages):
    class Fenetre:
        def __init__(self, reponse):
            self.reponse = reponse

        def create_file_dialog(self, *a, **k):
            return self.reponse

    def api(self, reponse):
        x = api_horaire.ApiHoraire()
        x._fenetre = self.Fenetre(reponse)
        return x

    def test_import_par_dialogue_annule_et_erreur(self):
        try:
            import webview  # noqa: F401
        except ImportError:
            self.skipTest("pywebview absent")
        r = self.api((FIXTURE,)).horaire_importer_fichier()
        self.assertEqual(len(r["cours"]), 7)
        self.assertEqual(r["source"]["nom"], "horaire_anonyme.ics")
        self.assertTrue(self.api(None).horaire_importer_fichier()["annule"])
        r = self.api((FIXTURE + ".absent",)).horaire_importer_fichier()
        self.assertIn("erreur", r)
        self.assertNotIn("Traceback", r["erreur"])

    def test_etat_et_choix(self):
        self.importer()
        x = self.api(None)
        e = x.horaire_etat()
        c = next(c for c in e["cours"] if c["intitule"] == SEMINAIRE)
        self.assertTrue(c["a_choisir"])
        self.assertEqual(c["propose"], "101")
        e = x.horaire_groupe(c["id"], c["groupes"][4]["id"], True)
        e = x.horaire_confirmer(c["id"], "101")
        c = next(c for c in e["cours"] if c["intitule"] == SEMINAIRE)
        self.assertEqual((c["confirme"], c["a_choisir"]), ("101", False))
        self.assertEqual(e["periode"], ["2026-11-02", "2026-12-18"])
        self.assertIn("erreur", x.horaire_abonnement("http://pas-chiffre.ch/x.ics"))
        json.dumps(e)

    def test_cours_moodle_sans_connexion(self):
        ancien = ms.charger_config
        ms.charger_config = lambda: {"token": "", "site": ms.SITE_UNIL, "dest": self.tmp.name}
        try:
            r = self.api(None).horaire_cours_moodle()
        finally:
            ms.charger_config = ancien
        self.assertIn("connecte-toi", r["erreur"])


class BlocsManuels(Reglages):
    def test_ajouter_deplacer_supprimer(self):
        horaire.sauver_bloc("101", 1, "10:15", 105)
        self.assertEqual(horaire.blocs_manuels(), [{"cid": "101", "jour": 1, "heure": "10:15", "duree": 105, "titre": None}])
        horaire.sauver_bloc("101", 3, "08:30", 120)                 # deplacer remplace
        self.assertEqual(horaire.blocs_manuels()[0]["jour"], 3)
        # les autres reglages de horaire.json sont gardes
        self.horaire_json({"101": {"jour": 1, "heure": "10:15", "controle": False, "titre": "X"}})
        horaire.sauver_bloc("101", 2, "09:00", 90)
        e = sc.charger_horaire()["101"]
        self.assertEqual((e["controle"], e["titre"], e["duree"]), (False, "X", 90))
        horaire.supprimer_bloc("101")
        e = sc.charger_horaire()["101"]
        self.assertNotIn("jour", e)
        self.assertEqual(e["controle"], False)

    def test_valeurs_invalides(self):
        for args in (("101", 7, "10:00", 60), ("101", 1, "10:00", 10), ("101", 1, "10h", 60)):
            with self.subTest(args=args), self.assertRaises(ms.Erreur):
                horaire.sauver_bloc(*args)

    def test_suivi_false_leve_par_le_placement(self):
        self.horaire_json({"101": {"suivi": False}})
        horaire.sauver_bloc("101", 1, "09:00", 90)
        self.assertNotIn("suivi", sc.charger_horaire()["101"])

    def test_heures_hebdo_manuel(self):
        horaire.sauver_bloc("101", 1, "08:00", 90)
        horaire.sauver_bloc("102", 2, "10:00", 120)
        self.assertEqual(horaire.heures_cours_hebdo(), 3.5)

    def test_heures_hebdo_ics(self):
        c = self.cours(self.importer(), "Histoire des idées (Cours)")
        horaire.confirmer(c["id"], "104")
        self.assertEqual(horaire.heures_cours_hebdo(), 1.5)          # 08:30 a 10:00

    def test_etat_page_porte_blocs_et_heures(self):
        horaire.sauver_bloc("101", 1, "10:15", 105)
        e = horaire.etat_page()
        self.assertEqual(e["blocs"], [{"cid": "101", "jour": 1, "heure": "10:15", "duree": 105, "titre": None}])
        self.assertEqual(e["heures_cours"], 1.75)                   # 105 min
        json.dumps(e)

    def test_api_bloc_et_suppression(self):
        try:
            import webview  # noqa: F401
        except ImportError:
            self.skipTest("pywebview absent")
        x = api_horaire.ApiHoraire()
        x._fenetre = Pont.Fenetre(None)
        r = x.horaire_bloc("101", 1, "10:15", 105)
        self.assertEqual(r["blocs"][0]["jour"], 1)
        r = x.horaire_supprimer_bloc("101")
        self.assertEqual(r["blocs"], [])
        self.assertIn("erreur", x.horaire_bloc("101", 9, "10:00", 60))


class CreneauxLibres(Reglages):
    def test_ajouter_modifier_supprimer(self):
        horaire.sauver_libre(1, "18:00", 120)
        libres = horaire.blocs_libres()
        self.assertEqual((libres[0]["jour"], libres[0]["heure"], libres[0]["duree"]), (1, "18:00", 120))
        ident = libres[0]["id"]
        horaire.sauver_libre(2, "20:00", 90, ident)          # deplace via l'id, pas de doublon
        libres = horaire.blocs_libres()
        self.assertEqual(len(libres), 1)
        self.assertEqual((libres[0]["jour"], libres[0]["heure"], libres[0]["duree"]), (2, "20:00", 90))
        horaire.supprimer_libre(ident)
        self.assertEqual(horaire.blocs_libres(), [])

    def test_heures_libres_hebdo(self):
        horaire.sauver_libre(1, "18:00", 120)
        horaire.sauver_libre(3, "14:00", 90)
        self.assertEqual(horaire.heures_libres_hebdo(), 3.5)

    def test_frequences(self):
        horaire.sauver_libre(1, "18:00", 120, frequence="2semaines")   # 120 / 2 = 60 min
        horaire.sauver_libre(3, "14:00", 180, frequence="3semaines")   # 180 / 3 = 60 min
        horaire.sauver_libre(5, "10:00", 240, frequence="mois")        # 240 / 4 = 60 min
        self.assertEqual(horaire.heures_libres_hebdo(), 3.0)
        self.assertEqual(horaire.blocs_libres()[0]["frequence"], "2semaines")
        with self.assertRaises(ms.Erreur):
            horaire.sauver_libre(1, "18:00", 60, frequence="nimporte")

    def test_frequence_conservee_a_la_modification(self):
        horaire.sauver_libre(1, "18:00", 120, frequence="mois")
        ident = horaire.blocs_libres()[0]["id"]
        horaire.sauver_libre(2, "20:00", 90, ident)                     # sans frequence : conservee
        self.assertEqual(horaire.blocs_libres()[0]["frequence"], "mois")

    def test_id_inconnu_et_valeurs_invalides(self):
        with self.assertRaises(ms.Erreur):
            horaire.sauver_libre(1, "18:00", 60, "nexistepas")
        with self.assertRaises(ms.Erreur):
            horaire.sauver_libre(7, "18:00", 60)

    def test_etat_page_porte_libres(self):
        horaire.sauver_libre(1, "18:00", 120)
        e = horaire.etat_page()
        self.assertEqual(e["heures_libres"], 2.0)
        self.assertEqual(len(e["libres"]), 1)
        json.dumps(e)


if __name__ == "__main__":
    unittest.main()
