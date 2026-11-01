#!/usr/bin/env python3
"""Tests hors ligne du suivi de Ma semaine (suivi.py) et du pont avec la page (application.py).
Aucun acces a Moodle, aucune fenetre : les fichiers de reglages sont rediriges vers un dossier temporaire.

Lancer depuis la racine du depot : python -m unittest discover tests
"""
import os, sys, json, tempfile, unittest, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moodlesync import suivi as a, semaine as m, seances as sc, application as app, moteur as ms

D = dt.date


def lire_texte(chemin):
    with open(chemin, encoding="utf-8") as f:
        return f.read()


def lire(chemin):
    return json.loads(lire_texte(chemin))


class Dossier(unittest.TestCase):
    """Chaque test travaille dans son propre dossier de reglages."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.anciens = (a.SUIVI, a.DERNIER, m.PREFS, m.MESURES, m.ETAT)
        a.SUIVI, a.DERNIER = os.path.join(d, "suivi.json"), os.path.join(d, "dernier.json")
        m.PREFS, m.MESURES, m.ETAT = os.path.join(d, "prefs.json"), os.path.join(d, "mesures.json"), os.path.join(d, "etat.json")
        m.sauver_prefs({"dossier": d, "jours": 14, "vitesse": 12})
        self.md = os.path.join(d, m.FICHIER)

    def tearDown(self):
        a.SUIVI, a.DERNIER, m.PREFS, m.MESURES, m.ETAT = self.anciens
        self.tmp.cleanup()


class Migration(Dossier):
    def test_reprend_cases_temps_et_echeances(self):
        with open(self.md, "w", encoding="utf-8") as f:
            f.write(sc.ms.MARQUE + "\n\n- [x] Hobbes (29 p., 2 h 25) · réel : 1 h 30 <!-- id:aaa -->\n"
                    "- [ ] Castoriadis (27 p., 2 h 15) <!-- id:bbb -->\n\n## Mes échéances\n\n"
                    "- 01.11.2026 23:59 · Théories économiques · Rendu intro\n\n## Notes\n\nx\n")
        api = a.Semaine()
        s = lire(a.SUIVI)
        self.assertEqual(s["lectures"]["aaa"], {"fait": True, "minutes": 90, "pages": 29})
        self.assertNotIn("bbb", s["lectures"])                       # rien a reprendre
        self.assertEqual(s["echeances"][0]["nom"], "Rendu intro")
        self.assertEqual(a.vitesse_mesuree(api.suivi), (19.3, 1))

    def test_sans_fichier(self):
        a.Semaine()
        self.assertEqual(lire(a.SUIVI), {"lectures": {}, "echeances": [],
                                         "changements": {"messages": [], "nouvelles": [], "depuis": None}})


class Suivi(Dossier):
    def test_cocher_et_noter(self):
        api = a.Semaine()
        api.cocher("x1", True, 20)
        r = api.noter_temps("x2", "1 h 10", 21)
        self.assertEqual(r["minutes"], 70)
        self.assertEqual(r["vitesse_mesuree"], (18.0, 1))
        self.assertTrue(lire(a.SUIVI)["lectures"]["x2"]["fait"])  # un temps note = lu
        self.assertIsNone(api.noter_temps("x3", "bientôt")["minutes"])
        for texte, attendu in (("70", 70), ("réel : 45", 45), ("2h", 120)):
            self.assertEqual(api.noter_temps("x4", texte)["minutes"], attendu)

    def test_echeances(self):
        api = a.Semaine()
        r = api.ajouter_echeance("2026-12-15", "18:00", "ITE", "Dossier final")
        e = r["echeances"][0]
        self.assertEqual(e["date"], "2026-12-15T18:00")
        self.assertEqual(api.ajouter_echeance("2026-13-40", "", "", "x"), {"erreur": "Date ou heure illisible."})
        self.assertEqual(api.supprimer_echeance(e["id"])["echeances"], [])
        api.ajouter_echeance("2026-12-01", "", "", "")
        self.assertEqual(api.suivi["echeances"][0]["date"], "2026-12-01T23:59")   # heure par defaut
        self.assertEqual(api.suivi["echeances"][0]["nom"], "(sans intitulé)")
        self.assertIn("01.12.2026 23:59 · (sans intitulé)", a.texte_mes_echeances(api.suivi))

    def test_reglages_limites(self):
        api = app.Api()
        self.assertEqual(api.regler("vitesse", "19")["prefs"]["vitesse"], 19)
        self.assertIn("erreur", api.regler("vitesse", 500))
        self.assertIn("erreur", api.regler("jours", 0))
        self.assertIn("erreur", api.regler("token", "x"))             # rien d'autre n'est modifiable
        self.assertIn("erreur", api.regler("vitesse", "vite"))
        self.assertFalse(api.regler("export_md", False)["prefs"]["export_md"])

    def test_ouvrir_fichier_absent(self):
        self.assertIn("erreur", app.Api().ouvrir("md"))
        self.assertIn("erreur", app.Api().ouvrir("n'importe quoi"))


class AvecAnalyse:
    def analyse(self):
        lect = [{"nom": "Hobbes.pdf", "statut": "À lire (statut non précisé)", "origine": "déduit", "pages": 29,
                 "pdf": True, "support": False},
                {"nom": "Gilens.pdf", "statut": sc.ms.T["C"], "origine": "consigne", "extrait": "Lecture facultative.",
                 "pages": 40, "pdf": True, "support": False},
                {"nom": "Aristote.pdf", "statut": sc.ms.T["O"], "origine": "consigne", "extrait": "Lire pp. 225-255.",
                 "pages": 412, "pages_consigne": 31, "plages": [(225, 255)], "pdf": True, "support": False}]
        s = {"date": D(2026, 11, 11), "heure": "08:30", "cours": "HIP", "cid": 1, "section": 8, "titre": " S8 - Hobbes ",
             "precision": "lue", "sans_travail": False, "sans_lecture": False, "ouverture": None, "consigne": [],
             "supports": [{}], "lectures": lect}
        return {"aujourdhui": D(2026, 11, 1), "jours": 14, "fenetre": [s], "a_dater": [], "sans_seance": ["ITE"],
                "echeances": [{"date": dt.datetime(2026, 11, 9, 23, 59), "cours": "COURS_Méthodes (2026-2027)",
                               "nom": "TP4", "en_retard": False}],
                "alertes": ["X : y."], "a_surveiller": [], "non_controles": [], "changements": None,
                "nouvelles": {("1:8", "Hobbes.pdf")}, "avec_pages": True}

class Donnees(AvecAnalyse, Dossier):
    def test_format(self):
        suivi = {"lectures": {}, "echeances": [{"id": "e1", "date": "2026-12-15T18:00", "cours": "", "nom": "Dossier"}]}
        ids = m.ids_lectures(self.analyse()["fenetre"][0])
        suivi["lectures"][ids[0]] = {"fait": True, "minutes": 90}
        suivi["changements"] = {"messages": [], "nouvelles": [["1:8", "Hobbes.pdf"]], "depuis": None}
        d = a.completer(a.donnees_interface(self.analyse(), suivi, {"vitesse": 12}), suivi)
        json.dumps(d)                                                 # tout est serialisable
        s = d["seances"][0]
        self.assertEqual(s["titre"], "S8 - Hobbes")
        self.assertEqual(s["supports"], 1)
        h, g, ar = s["lectures"]
        self.assertTrue(h["fait"] and h["nouveau"] and h["minutes"] == 90)
        self.assertTrue(g["facultatif"])
        self.assertEqual((ar["pages"], ar["pages_pdf"], ar["consigne_pages"]), (31, 412, True))
        self.assertEqual(d["echeances_moodle"][0]["cours"], "Méthodes (cours)")
        self.assertEqual([e["manuelle"] for e in d["echeances"]], [False, True])

    def test_ids_identiques_au_markdown(self):
        s = self.analyse()["fenetre"][0]
        s["lectures"].append(dict(s["lectures"][0]))                 # meme fichier deux fois
        ids = m.ids_lectures(s)
        self.assertEqual(len(set(ids)), 4)
        self.assertEqual(ids[0], sc.id_lecture(1, "Hobbes.pdf"))
        self.assertEqual(ids[3], sc.id_lecture(1, "Hobbes.pdf#2"))

    def test_export_markdown_garde_cases_et_notes(self):
        api = a.Semaine()
        R = self.analyse()
        ids = m.ids_lectures(R["fenetre"][0])
        api.cocher(ids[0], True)
        api.ajouter_echeance("2026-12-15", "18:00", "ITE", "Dossier final")
        with open(self.md, "w", encoding="utf-8") as f:
            f.write(sc.ms.MARQUE + "\n\n## Notes\n\nMes notes à garder\n")
        api.exporter(R, a.prefs())
        texte = lire_texte(self.md)
        self.assertIn(f"- [x] Hobbes (29 p.", texte)
        self.assertIn("Mes notes à garder", texte)
        self.assertIn("15.12.2026 18:00 · ITE · Dossier final", texte)

    def test_export_refuse_un_fichier_utilisateur(self):
        with open(self.md, "w", encoding="utf-8") as f:
            f.write("Mon propre fichier\n")
        api = a.Semaine()
        with self.assertRaises(sc.ms.Erreur):
            api.exporter(self.analyse(), a.prefs())
        self.assertEqual(lire_texte(self.md), "Mon propre fichier\n")


class Fusion(AvecAnalyse, Dossier):
    """Ma semaine.md modifie a la main (Obsidian) entre deux actualisations."""

    def exporter(self, api):
        api.exporter(self.analyse(), a.prefs())
        return lire_texte(self.md)

    def remplacer(self, avant, apres):
        texte = lire_texte(self.md)
        self.assertIn(avant, texte)
        with open(self.md, "w", encoding="utf-8") as f:
            f.write(texte.replace(avant, apres, 1))

    def test_case_cochee_et_temps_dans_le_fichier(self):
        api = a.Semaine()
        ids = m.ids_lectures(self.analyse()["fenetre"][0])
        self.exporter(api)
        self.remplacer("- [ ] Hobbes (29 p.", "- [x] Hobbes (29 p.")
        self.remplacer(f"<!-- id:{ids[2]} -->", f"réel : 1 h 30 <!-- id:{ids[2]} -->")
        api = a.Semaine()                                               # relance : fusion a l'ouverture
        self.assertTrue(api.suivi["lectures"][ids[0]]["fait"])
        self.assertEqual(api.suivi["lectures"][ids[2]]["minutes"], 90)
        self.assertIn(f"- [x] Hobbes (29 p.", self.exporter(api))    # et l'export suivant le garde

    def test_case_decochee_dans_le_fichier(self):
        api = a.Semaine()
        ids = m.ids_lectures(self.analyse()["fenetre"][0])
        api.cocher(ids[0], True)
        self.exporter(api)
        self.remplacer("- [x] Hobbes (29 p.", "- [ ] Hobbes (29 p.")
        self.assertFalse(a.Semaine().suivi["lectures"][ids[0]]["fait"])

    def test_fichier_ancien_n_ecrase_pas_l_application(self):
        api = a.Semaine()
        ids = m.ids_lectures(self.analyse()["fenetre"][0])
        self.exporter(api)
        api.cocher(ids[0], True)                                    # coche dans la fenetre, fichier pas reecrit
        self.assertEqual(a.fusionner_md(api.suivi, self.md), 0)
        self.assertTrue(api.suivi["lectures"][ids[0]]["fait"])

    def test_deux_cotes_modifies_rien_ne_se_perd(self):
        api = a.Semaine()
        ids = m.ids_lectures(self.analyse()["fenetre"][0])
        self.exporter(api)
        api.noter_temps(ids[1], "40")                               # application : temps sur Gilens
        self.remplacer("- [ ] Hobbes (29 p.", "- [x] Hobbes (29 p.")
        self.remplacer(f"<!-- id:{ids[1]} -->", f"réel : 55 <!-- id:{ids[1]} -->")
        a.fusionner_md(api.suivi, self.md)
        self.assertTrue(api.suivi["lectures"][ids[0]]["fait"])
        self.assertEqual(api.suivi["lectures"][ids[1]]["minutes"], 40)   # l'application d'abord

    def test_echeances_ajoutee_et_effacee_dans_le_fichier(self):
        api = a.Semaine()
        api.ajouter_echeance("2026-12-15", "18:00", "ITE", "Dossier final")
        api.ajouter_echeance("2026-12-20", "12:00", "", "Autre")
        self.exporter(api)
        self.remplacer("- 15.12.2026 18:00 · ITE · Dossier final\n", "- 03.12.2026 · Méthodes · TP5\n")
        api = a.Semaine()
        noms = sorted(e["nom"] for e in api.suivi["echeances"])
        self.assertEqual(noms, ["Autre", "TP5"])

    def test_echeance_effacee_dans_l_application_ne_revient_pas(self):
        api = a.Semaine()
        e = api.ajouter_echeance("2026-12-15", "18:00", "ITE", "Dossier final")["echeances"][0]
        self.exporter(api)
        api.supprimer_echeance(e["id"])
        a.fusionner_md(api.suivi, self.md)
        self.assertEqual(api.suivi["echeances"], [])

    def test_fichier_sans_marque_ignore(self):
        with open(self.md, "w", encoding="utf-8") as f:
            f.write("- [x] Hobbes <!-- id:abc -->\n")
        api = a.Semaine()
        self.assertNotIn("abc", api.suivi["lectures"])

    def test_echeance_en_double_refusee(self):
        api = a.Semaine()
        api.ajouter_echeance("2026-12-15", "18:00", "ITE", "Dossier")
        self.assertIn("erreur", api.ajouter_echeance("2026-12-15", "18:00", " ITE ", "Dossier"))


class Changements(AvecAnalyse, Dossier):
    def test_gardes_jusqu_a_vu(self):
        api = a.Semaine()
        R = self.analyse()
        R["changements"] = ["HIP : lecture ajoutée pour le mercredi 11 novembre : Hobbes.pdf."]
        a.cumuler_changements(api.suivi, R, "2026-11-01T10:00:00")
        R2 = {**self.analyse(), "changements": [], "nouvelles": set()}      # actualisation suivante : rien
        a.cumuler_changements(api.suivi, R2, "2026-11-02T10:00:00")
        d = a.completer(a.donnees_interface(R2, api.suivi, {}), api.suivi)
        self.assertEqual(len(d["non_vus"]), 1)
        self.assertEqual(d["non_vus_depuis"], "2026-11-01T10:00:00")
        self.assertTrue(d["seances"][0]["lectures"][0]["nouveau"])          # badge garde aussi
        self.assertIn("lecture ajoutée", self.exporter_texte(api, R2))
        api.changements_vus()
        d = a.completer(a.donnees_interface(R2, api.suivi, {}), api.suivi)
        self.assertEqual(d["non_vus"], [])
        self.assertFalse(d["seances"][0]["lectures"][0]["nouveau"])

    def test_pas_de_doublon(self):
        api = a.Semaine()
        R = {**self.analyse(), "changements": ["X : y."]}
        a.cumuler_changements(api.suivi, R, "t1")
        a.cumuler_changements(api.suivi, R, "t2")
        self.assertEqual(api.suivi["changements"]["messages"], ["X : y."])
        self.assertEqual(len(api.suivi["changements"]["nouvelles"]), 1)

    def exporter_texte(self, api, R):
        api.exporter(R, a.prefs())
        return lire_texte(self.md)


class Erreurs(AvecAnalyse, Dossier):
    def setUp(self):
        super().setUp()
        self.ancien_err = ms.ERREURS
        ms.ERREURS = os.path.join(self.tmp.name, "erreurs.txt")

    def tearDown(self):
        ms.ERREURS = self.ancien_err
        super().tearDown()

    def test_temps_illisible_garde_l_ancien(self):
        api = a.Semaine()
        api.noter_temps("x", "70")
        r = api.noter_temps("x", "bientôt")
        self.assertTrue(r["illisible"])
        self.assertEqual(lire(a.SUIVI)["lectures"]["x"]["minutes"], 70)
        self.assertIsNone(api.noter_temps("x", "")["minutes"])           # champ vide : efface

    def test_export_impossible_n_annule_pas_l_actualisation(self):
        api = a.Semaine()
        bloque = os.path.join(self.tmp.name, "bloque")
        open(bloque, "w").close()                                  # un fichier la ou il faudrait un dossier
        m.sauver_prefs({**m.charger_prefs(), "dossier": os.path.join(bloque, "dessous")})
        ancien, m.analyser = m.analyser, lambda *x, **k: self.analyse()
        ancien_mem, m.memoriser = m.memoriser, lambda R: None
        try:
            r = api.actualiser()
        finally:
            m.analyser, m.memoriser = ancien, ancien_mem
        self.assertNotIn("erreur", r)
        self.assertIn("Export de Ma semaine.md", r["avertissement"])
        self.assertEqual(len(r["donnees"]["seances"]), 1)

    def test_message_lisible_et_detail_note(self):
        try:
            raise KeyError("cle_interne")
        except KeyError as e:
            texte = ms.message_erreur(e, "Actualisation")
        self.assertNotIn("KeyError", texte)
        self.assertIn("KeyError", lire_texte(ms.ERREURS))


class Interface(unittest.TestCase):
    def test_fichier_present_et_sans_tirets_longs(self):
        # La page est decoupee : index.html (structure) et les scripts *.js (Ma semaine dans semaine.js).
        dossier = app.dossier_interface()
        self.assertTrue(os.path.exists(os.path.join(dossier, "index.html")))
        texte = "".join(lire_texte(os.path.join(dossier, f)) for f in sorted(os.listdir(dossier))
                        if f.endswith((".html", ".js")))
        self.assertNotIn(chr(0x2013), texte)
        self.assertNotIn(chr(0x2014), texte)
        for appel in ("demarrer", "actualiser", "cocher", "noter_temps", "ajouter_echeance", "supprimer_echeance",
                      "regler", "choisir_dossier", "audit", "ouvrir", "changements_vus"):
            with self.subTest(appel=appel):
                self.assertIn(f"api().{appel}(", texte)
                self.assertTrue(callable(getattr(app.Api, appel)))


if __name__ == "__main__":
    unittest.main()
