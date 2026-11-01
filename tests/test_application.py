"""Tests hors ligne du pont entre la page et les moteurs (application.py), onglet Synchroniser surtout.

Aucun acces reseau, aucun navigateur, aucune fenetre : les fonctions reseau du moteur sont remplacees par
des doublures et tous les fichiers de reglages vont dans un dossier temporaire.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, sys, re, json, glob, tempfile, threading, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moodlesync import application as app, moteur as ms, semaine as m, suivi as S

COURS = [{"id": 11, "fullname": "Histoire des idées politiques (2026-2027)", "shortname": "COURS_HIP"},
         {"id": 12, "fullname": "Théories économiques (2026-2027)", "shortname": "SEM_ITE"}]


class Doublures(unittest.TestCase):
    """Reglages dans un dossier temporaire ; reseau, navigateur et raccourci de demarrage remplaces."""

    RESEAU = ("infos_session", "cours_inscrits", "resume_cours", "collecte", "telecharger", "ecrire_liens",
              "ecrire_note", "connexion_navigateur", "verifier_site", "regler_demarrage", "api")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.d = self.tmp.name
        self.dest = os.path.join(d, "Cours")
        self.sauve = {n: getattr(ms, n) for n in self.RESEAU + ("APP_DIR", "CONFIG", "DEMARRAGE", "ERREURS")}
        self.sauve_m = (m.PREFS, m.MESURES, m.ETAT, S.SUIVI, S.DERNIER, m.analyser)
        ms.APP_DIR, ms.CONFIG = d, os.path.join(d, "config.json")
        ms.DEMARRAGE, ms.ERREURS = os.path.join(d, "demarrage.lnk"), os.path.join(d, "erreurs.txt")
        m.PREFS, m.MESURES, m.ETAT = (os.path.join(d, x) for x in ("prefs.json", "mesures.json", "etat.json"))
        S.SUIVI, S.DERNIER = os.path.join(d, "suivi.json"), os.path.join(d, "dernier.json")
        self.appels = []

        def interdit(*a, **k):
            raise AssertionError("appel reseau non prevu")
        ms.api = interdit
        ms.infos_session = lambda tok: self.trace("infos_session") or {"fullname": "Ada Lovelace", "userid": 7}
        ms.cours_inscrits = lambda tok, uid: COURS
        ms.resume_cours = lambda tok, cours, etat=None: [
            {"id": c["id"], "nom": c["fullname"], "shortname": c["shortname"], "nb": 3, "taille": 2048, "nouveaux": 1}
            for c in cours]
        ms.collecte = lambda tok, cours, cfg, dire=print, liens=None, arreter=None: self.trace("collecte", cours) or \
            [{"cid": c["id"]} for c in cours]
        ms.telecharger = self.telecharger
        ms.ecrire_liens = lambda liens, dest, dire=print: []
        ms.ecrire_note = lambda r: None
        ms.connexion_navigateur = lambda dire=print: ("jeton-neuf", True)
        ms.verifier_site = lambda base: self.trace("verifier_site", base)
        ms.regler_demarrage = lambda actif: self.trace("regler_demarrage", actif)
        m.analyser = interdit
        self.ecrire_config({"site": "https://moodle.exemple.ch", "token": "jeton", "dest": self.dest})
        self.api = app.Api()

    def tearDown(self):
        for n, v in self.sauve.items():
            setattr(ms, n, v)
        m.PREFS, m.MESURES, m.ETAT, S.SUIVI, S.DERNIER, m.analyser = self.sauve_m
        ms.appliquer_config(ms.charger_config())
        self.tmp.cleanup()

    def trace(self, nom, *args):
        self.appels.append((nom,) + args)

    def telecharger(self, items, cfg, dire=print, progres=None, arreter=None):
        self.trace("telecharger", items)
        if progres:
            progres(1, len(items), "fichier.pdf")
        return {"total": len(items), "neufs": len(items), "maj": 0, "doublons": 0, "erreurs": 0, "dest": cfg["dest"],
                "liste_neufs": [("Histoire des idées politiques - Cours", "a.pdf")], "liste_maj": [], "annule": False,
                "restants": {}}

    def ecrire_config(self, c):
        with open(ms.CONFIG, "w", encoding="utf-8") as f:
            json.dump(c, f)

    def config(self):
        with open(ms.CONFIG, encoding="utf-8") as f:
            return json.load(f)

    def json_ok(self, r):
        json.dumps(r)                                # tout ce qui part vers la page doit etre serialisable
        return r


class Reglages(Doublures):
    def test_liste_blanche(self):
        a = self.api
        self.assertIn("erreur", a.sync_regler("token", "vole"))
        self.assertIn("erreur", a.sync_regler("site", "https://ailleurs.ch"))      # passe par sync_site
        self.assertIn("erreur", a.sync_regler("langue", "klingon"))
        self.assertIn("erreur", a.sync_regler("theme", "violet"))
        self.assertIn("erreur", a.sync_regler("dest", "dossier/relatif"))
        self.assertEqual(self.config()["token"], "jeton")
        r = self.json_ok(a.sync_regler("statuts", True))
        self.assertTrue(r["statuts"])
        self.assertTrue(self.config()["statuts"])
        self.assertFalse(self.json_ok(a.sync_regler("titres_youtube", False))["titres_youtube"])
        self.assertFalse(self.config()["titres_youtube"])

    def test_youtube_actif_par_defaut(self):
        self.assertTrue(self.api.sync_etat()["titres_youtube"])

    def test_demarrage_automatique(self):
        self.api.sync_regler("auto", True)
        self.assertIn(("regler_demarrage", True), self.appels)
        self.assertNotIn("auto", self.config())                  # pas dans config.json : c'est le raccourci

    def test_theme_general(self):
        self.api.sync_regler("theme", "dark")
        self.assertEqual(self.api.infos()["theme"], "dark")

    def test_reglages_ma_semaine_ne_l_activent_pas(self):
        # Un fichier de reglages non vide sans "active" passe pour celui du prototype : regler l'ecrit toujours.
        self.assertFalse(S.prefs()["active"])
        self.api.regler("jours", 21)
        self.assertFalse(S.prefs()["active"])
        self.assertEqual(m.charger_prefs()["active"], False)

    def test_langue_fige_les_dossiers(self):
        self.api.sync_verifier()
        self.api.sync_regler("langue", "en")
        cours = self.config()["cours"]
        self.assertEqual(cours["11"]["dossier"], "Histoire des idées politiques - Cours")   # nom francais garde
        self.assertEqual(self.config()["langue"], "en")


class Session(Doublures):
    def test_sans_jeton(self):
        self.ecrire_config({"site": "https://moodle.exemple.ch", "token": ""})
        r = self.json_ok(self.api.sync_verifier())
        self.assertFalse(r["connecte"])
        self.assertNotIn(("infos_session",), self.appels)

    def test_liste_des_cours(self):
        r = self.json_ok(self.api.sync_verifier())
        self.assertTrue(r["connecte"])
        self.assertEqual(r["statut"]["texte"], "Connecté : Ada Lovelace")
        noms = [c["dossier"] for c in r["cours"]]
        # Meme nom par defaut que celui que collecte() utilisera (nom complet du cours, sans l'annee).
        self.assertEqual(noms, [ms.dossier_defaut(c) for c in COURS])
        self.assertEqual(r["total"], "2 cours, 6 fichiers, " + ms.humain(4096))

    def test_session_expiree_efface_le_jeton(self):
        def expiree(tok):
            raise ms.SessionExpiree("expiree")
        ms.infos_session = expiree
        r = self.api.sync_verifier()
        self.assertTrue(r["expiree"])
        self.assertEqual(self.config()["token"], "")

    def test_panne_reseau_garde_le_jeton(self):
        def panne(tok):
            raise ms.Erreur("Moodle ne répond pas.")
        ms.infos_session = panne
        r = self.api.sync_verifier()
        self.assertTrue(r["jeton_garde"])
        self.assertEqual(self.config()["token"], "jeton")

    def test_changer_de_moodle_demande_confirmation(self):
        r = self.api.sync_site("moodle.autre.ch")
        self.assertIn("confirmer", r)
        self.assertNotIn(("verifier_site", "https://moodle.autre.ch"), self.appels)
        r = self.json_ok(self.api.sync_site("moodle.autre.ch", True))
        self.assertTrue(r["ok"])
        c = self.config()
        self.assertEqual((c["site"], c["token"], c["cours"]), ("https://moodle.autre.ch", "", {}))

    def test_connexion(self):
        r = self.json_ok(self.api.sync_connecter())
        self.assertTrue(r["connecte"])
        self.assertEqual(self.config()["token"], "jeton-neuf")


class Synchronisation(Doublures):
    def test_preconditions(self):
        self.assertIn("confirmer", self.api.sync_lancer())                 # dossier absent : on demande
        self.assertFalse(os.path.exists(self.dest))
        self.assertIn("erreur", self.api.sync_lancer(True))                # aucun cours liste
        self.assertTrue(os.path.isdir(self.dest))
        self.ecrire_config({"site": "https://moodle.exemple.ch", "token": "", "dest": self.dest})
        self.assertEqual(self.api.sync_lancer(True)["erreur"], "Commence par te connecter à Moodle.")

    def test_seuls_les_cours_coches(self):
        self.api.sync_verifier()
        self.api.sync_choisir(12, False)
        self.assertFalse(self.config()["cours"]["12"]["choisi"])
        r = self.json_ok(self.api.sync_lancer(True))
        self.assertEqual(r["resultat"]["neufs"], 1)
        collectes = [x for x in self.appels if x[0] == "collecte"][0][1]
        self.assertEqual([c["id"] for c in collectes], [11])
        self.assertEqual(r["resultat"]["lignes"], ["Histoire des idées politiques - Cours : 1 nouveau fichier"])

    def test_tout_cocher(self):
        self.api.sync_verifier()
        self.api.sync_choisir(None, False)
        self.assertEqual({v["choisi"] for v in self.config()["cours"].values()}, {False})
        self.assertIn("erreur", self.api.sync_lancer(True))

    def test_une_operation_a_la_fois_et_annuler(self):
        self.api.sync_verifier()
        os.makedirs(self.dest)
        demarre, vu = threading.Event(), {}

        def lent(items, cfg, dire=print, progres=None, arreter=None):
            demarre.set()
            for _ in range(500):
                if arreter():
                    vu["arret"] = True
                    break
                threading.Event().wait(0.01)
            return {**self.telecharger(items, cfg), "annule": vu.get("arret", False)}
        ms.telecharger = lent
        res = {}
        t = threading.Thread(target=lambda: res.update(self.api.sync_lancer()))
        t.start()
        self.assertTrue(demarre.wait(5))
        self.assertEqual(self.api.sync_lancer()["erreur"], app.OCCUPE)
        self.assertEqual(self.api.sync_connecter()["erreur"], app.OCCUPE)
        self.assertIn("erreur", self.api.sync_renommer(11, "Autre"))
        self.assertTrue(self.api.sync_annuler()["ok"])
        t.join(5)
        self.assertTrue(vu.get("arret"))
        self.assertTrue(res["resultat"]["annule"])
        self.assertFalse(self.api.sync_annuler()["ok"])                  # plus rien a annuler

    def test_annule_pendant_la_lecture_des_cours(self):
        self.api.sync_verifier()
        os.makedirs(self.dest)

        def annule(*a, **k):
            raise ms.Annule()
        ms.collecte = annule
        self.assertEqual(self.api.sync_lancer(), {"annule_avant": True})

    def test_erreur_imprevue_devient_une_phrase(self):
        self.api.sync_verifier()
        os.makedirs(self.dest)

        def casse(*a, **k):
            raise KeyError("cle_interne")
        ms.telecharger = casse
        r = self.api.sync_lancer()
        self.assertNotIn("KeyError", r["erreur"])
        self.assertIn("Synchronisation", r["erreur"])
        with open(ms.ERREURS, encoding="utf-8") as f:
            self.assertIn("KeyError", f.read())
        self.assertFalse(self.api._long.locked())                       # le verrou est rendu


class Renommage(Doublures):
    def test_confirmation_et_cours_inclus(self):
        self.ecrire_config({"site": "https://moodle.exemple.ch", "token": "jeton", "dest": self.dest,
                            "cours": {"12": {"dossier": "Histoire des idées politiques - Cours" + os.sep + "SITE",
                                             "choisi": True}}})
        self.api.sync_verifier()
        src = os.path.join(self.dest, "Histoire des idées politiques - Cours", "SITE")
        os.makedirs(src)
        open(os.path.join(src, "a.pdf"), "w").close()
        r = self.api.sync_renommer(11, "HIP")
        self.assertIn("1 fichiers", r["confirmer"])
        self.assertIn("SITE", r["confirmer"])                            # le cours inclus est annonce
        r = self.json_ok(self.api.sync_renommer(11, "HIP", True))
        self.assertTrue(os.path.exists(os.path.join(self.dest, "HIP", "SITE", "a.pdf")))
        cours = self.config()["cours"]
        self.assertEqual(cours["11"]["dossier"], "HIP")
        self.assertEqual(cours["12"]["dossier"], "HIP" + os.sep + "SITE")

    def test_sans_dossier_sur_le_disque(self):
        self.api.sync_verifier()
        self.assertTrue(self.api.sync_renommer(11, "HIP")["ok"])
        self.assertEqual(self.config()["cours"]["11"]["dossier"], "HIP")
        self.assertTrue(self.api.sync_renommer(11, "  ")["inchange"])


class MaSemaineDesactivee(Doublures):
    def test_aucun_acces_moodle(self):
        a = self.api
        self.assertFalse(a.infos()["semaine_active"])
        self.assertIsNone(self.json_ok(a.demarrer())["donnees"])
        self.assertIn("désactivée", a.actualiser()["erreur"])              # m.analyser interdit : jamais appele
        self.assertIn("désactivée", a.audit()["erreur"])
        self.assertEqual(self.appels, [])


class Page(unittest.TestCase):
    """Chaque appel de la page correspond a une methode publique de Api, et la page ne charge rien d'exterieur."""

    def textes(self):
        out = {}
        for f in glob.glob(os.path.join(app.dossier_interface(), "*")):
            if f.endswith((".js", ".html", ".css")):
                with open(f, encoding="utf-8") as h:
                    out[os.path.basename(f)] = h.read()
        return out

    def test_appels_connus(self):
        appels = set()
        for nom, t in self.textes().items():
            appels |= set(re.findall(r"api\(\)\.(\w+)\(", t)) | set(re.findall(r"\bapi\.(\w+)\(", t))
        self.assertGreater(len(appels), 20)
        for nom in sorted(appels):
            with self.subTest(appel=nom):
                self.assertFalse(nom.startswith("_"))
                self.assertTrue(callable(getattr(app.Api, nom, None)), f"Api.{nom} n'existe pas")

    def test_rien_d_exterieur_ni_tiret_long(self):
        for nom, t in self.textes().items():
            with self.subTest(fichier=nom):
                self.assertNotRegex(t, r"(src|href)=\"(https?:)?//")       # ni CDN ni police en ligne
                self.assertNotRegex(t, r"@import|url\(\s*['\"]?https?:")
                self.assertNotIn(chr(0x2013), t)
                self.assertNotIn(chr(0x2014), t)
                self.assertNotRegex(t, r"\b(alert|confirm|prompt)\(")       # bloqueraient la fenetre

    def test_scripts_et_conteneurs_attendus(self):
        page = self.textes()["index.html"]
        for x in ('id="o-sync"', 'id="o-semaine"', 'id="horaire"', 'src="horaire.js"', 'href="horaire.css"',
                  'src="app.js"', 'role="tablist"'):
            self.assertIn(x, page)
        self.assertIn("window.etatVerification", self.textes()["app.js"])


if __name__ == "__main__":
    unittest.main()
