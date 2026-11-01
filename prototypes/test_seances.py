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
        seance("rech", "2 novembre " + sc.TIRETS[0] + " Semaine intercalaire - Pas de cours", LUN),  # tiret de Moodle
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

    def test_cours_sans_jour_regroupes(self):
        msgs = self.ctrl([], {"n": ("Nouveau cours", None), "m": ("Autre cours", None)})
        self.assertEqual(len(msgs), 1)                               # une seule ligne, pas une par cours
        self.assertIn("Nouveau cours, Autre cours", msgs[0])

    def test_controle_desactive(self):
        msgs = self.ctrl([], {"ite": {"nom": "ITE", "jour": MAR, "controle": False}})
        self.assertEqual(msgs, [])

    def test_source_du_jour_citee(self):
        msgs = self.ctrl([], {"x": {"nom": "X", "jour": MAR, "source": "ses dates dans Moodle"}})
        self.assertIn("d'après ses dates dans Moodle", msgs[0])


def avec_lectures(s, n=1, **extra):
    s.update({"lectures": [{"nom": f"texte{i}.pdf"} for i in range(n)], "nb_modules": n, "ouverture": None,
              "sans_lecture": False, **extra})
    return s


class Habitudes(unittest.TestCase):
    """Cas reel : Histoire des idees politiques, S9 du 18.11 encore vide alors que S2 a S8 avaient un texte."""

    def setUp(self):
        self.cal = sc.construire_calendrier(lundis_de_reference())
        self.suivis = {"hip": ("Idées politiques", MER)}
        self.passees = [avec_lectures(seance("hip", f"S{i} - {d} - Titre", MER), 1)
                        for i, d in ((2, "23/09"), (3, "30/09"), (4, "07/10"), (5, "14/10"))]

    def ctrl(self, ss, debut=D(2026, 11, 16), fin=D(2026, 11, 22)):
        return sc.surveillances(ss, self.suivis, debut, fin)

    def test_pas_melange_avec_les_controles(self):
        vide = avec_lectures(seance("hip", "S9 - 18/11 - Hobbes", MER), 0)
        self.assertEqual(sc.controles(self.passees + [vide], self.suivis, self.cal, D(2026, 11, 16),
                                      D(2026, 11, 22)), [])

    def test_seance_hors_jour_deja_signalee_ailleurs(self):
        zoom = avec_lectures(seance("hip", "Zoom politique du 19 novembre 2026", MER), 0)
        self.assertEqual(self.ctrl(self.passees + [zoom]), [])

    def test_seance_vide_dans_un_cours_a_lectures(self):
        vide = avec_lectures(seance("hip", "S9 - 18/11 - Hobbes et le Leviathan", MER), 0)
        msgs = self.ctrl(self.passees + [vide])
        self.assertEqual(len(msgs), 1)
        self.assertIn("4 des 4 séances passées", msgs[0])

    def test_cours_sans_habitude_de_lectures(self):
        passees = [avec_lectures(s, 0) for s in self.passees]
        vide = avec_lectures(seance("hip", "S9 - 18/11 - Hobbes", MER), 0)
        self.assertEqual(self.ctrl(passees + [vide]), [])

    def test_trop_peu_d_historique(self):
        vide = avec_lectures(seance("hip", "S9 - 18/11 - Hobbes", MER), 0)
        self.assertEqual(self.ctrl(self.passees[:2] + [vide]), [])

    def test_pas_de_lecture_annonce(self):
        vide = avec_lectures(seance("hip", "S9 - 18/11 - pas de lecture", MER), 0, sans_lecture=True)
        self.assertEqual(self.ctrl(self.passees + [vide]), [])

    def test_contenu_verrouille(self):
        ferme = avec_lectures(seance("hip", "S9 - 18/11 - Hobbes", MER), 0,
                              ouverture="Non disponible à moins que : Vous soyez membre de Groupe A")
        msgs = self.ctrl([ferme])
        self.assertEqual(len(msgs), 1)
        self.assertIn("non visible", msgs[0])


class JourHabituel(unittest.TestCase):
    """Sans horaire.json (cas de la plupart des utilisateurs), le jour vient des dates du cours."""

    def test_jour_net(self):
        self.assertEqual(sc.jour_habituel([D(2026, 9, 16), D(2026, 9, 23), D(2026, 9, 30), D(2026, 10, 7)]), MER)

    def test_une_exception_toleree(self):
        ds = [D(2026, 9, 16), D(2026, 9, 23), D(2026, 9, 30), D(2026, 10, 7), D(2026, 11, 12)]
        self.assertEqual(sc.jour_habituel(ds), MER)

    def test_trop_peu_ou_trop_disperse(self):
        self.assertIsNone(sc.jour_habituel([D(2026, 9, 16), D(2026, 9, 23)]))
        self.assertIsNone(sc.jour_habituel([D(2026, 9, 14), D(2026, 9, 15), D(2026, 9, 16), D(2026, 9, 17)]))

    def test_dater_cite_la_source(self):
        an = sc.analyser_titre("9 novembre - 15 novembre", Y0)
        d, prec = sc.dater(an, {"jour": MER}, "ses dates dans Moodle")
        self.assertEqual(d, D(2026, 11, 11))
        self.assertIn("ses dates dans Moodle", prec)


class Consignes(unittest.TestCase):
    """Descriptions reelles des fichiers d'Histoire des idees politiques, plus des cas en anglais."""

    def statut(self, texte):
        return sc.consigne(texte)[0]

    def test_a_lire(self):
        for t in ["Castoriadis. Texte à lire pour la séance du 23 septembre.",
                  "Sélection de (courts) extraits de Bodin et La Boétie à lire avant le cours",
                  "Texte à lire de Filmer",
                  "Aristote : lire uniquement les chapitres 6-13 du livre III (pp. 225-255). Le reste passe en "
                  "lecture facultative.",
                  "Lire d’abord (et prioritairement) : Le Mythe de la caverne",
                  "Required reading for week 3", "Please read before the seminar"]:
            with self.subTest(t=t):
                self.assertEqual(self.statut(t), sc.ms.T["O"])

    def test_facultatif(self):
        for t in ["par Gilens et Page. Lecture facultative, mais édifiante. Lire l'abstract et l'introduction.",
                  "Texte non obligatoire", "Optional reading", "Pour aller plus loin : Weber"]:
            with self.subTest(t=t):
                self.assertIn(self.statut(t), (sc.ms.T["C"], sc.ms.T["P"]))

    def test_rien_d_ecrit(self):
        for t in ["Sélection de chapitres du Leviathan", "Castoriadis - Imaginaire politique grec et moderne",
                  "L'inscription au groupe est importante"]:
            with self.subTest(t=t):
                self.assertIsNone(self.statut(t))

    def test_extrait_montre_la_phrase(self):
        _, extrait = sc.consigne("Castoriadis. Texte à lire pour la séance du 23 septembre. Autre phrase.")
        self.assertEqual(extrait, "Texte à lire pour la séance du 23 septembre.")

    def test_pages(self):
        self.assertEqual(sc.pages_consigne("Lire d'abord : pp. 247 " + sc.TIRETS[0] + " 256, puis pp. 168-184"),
                         (27, [(247, 256), (168, 184)]))
        self.assertEqual(sc.pages_consigne("chapitres 6-13 du livre III des politiques (pp. 225-255)")[0], 31)
        self.assertEqual(sc.pages_consigne("Read pages 12 to 30")[0], 19)
        self.assertEqual(sc.pages_consigne("chapitres 6-13, édition 1993"), (None, []))

    def test_consigne_de_section(self):
        resume = ("<p>Pour la séance d'introduction, nous discuterons des modalités pratiques. Pour vous préparer, "
                  "vous pouvez déjà lire le syllabus disponible dans la section Généralités.</p>")
        self.assertEqual(sc.consigne_section(resume),
                         ["Pour vous préparer, vous pouvez déjà lire le syllabus disponible dans la section Généralités."])
        self.assertEqual(sc.consigne_section("<p>Lectures obligatoires : Weber, Max (1919), Le savant</p>"), [])


class LecturesDeSection(unittest.TestCase):
    """Section reconstituee au format de l'API Moodle (core_course_get_contents)."""

    def module(self, modname, nom, desc="", fichiers=(), url=None):
        contents = [{"type": "file", "filename": f, "fileurl": f"https://m/{f}", "filesize": 1} for f in fichiers]
        if url:
            contents = [{"type": "url", "fileurl": url}]
        return {"modname": modname, "name": nom, "description": desc, "contents": contents}

    def test_section_hip_s2(self):
        s = {"summary": "", "modules": [
            self.module("resource", "Castoriadis - Imaginaire politique", "<p>Texte à lire pour la séance du 23 septembre.</p>",
                        ["Castoriadis.pdf"]),
            self.module("resource", "Testing Theories of American Politics",
                        "<p>par Gilens et Page</p><p>Lecture facultative, mais édifiante.</p>", ["GilensPage2014.pdf"]),
            self.module("resource", "Powerpoint séance 2", "", ["HIP2309 - S2.pptx"]),
            self.module("url", "Vidéo : Le danger des inégalités", "à regarder avant le cours", url="https://youtube.com/x"),
            self.module("url", "Article de Nippel", "Texte à lire pour la séance", url="https://exemple.org/nippel"),
        ]}
        par_nom = {f["nom"]: f for f in sc.lectures_de_section(s, None)}
        self.assertEqual(par_nom["Castoriadis.pdf"]["statut"], sc.ms.T["O"])
        self.assertEqual(par_nom["Castoriadis.pdf"]["origine"], "consigne")
        self.assertEqual(par_nom["GilensPage2014.pdf"]["statut"], sc.ms.T["C"])
        self.assertTrue(par_nom["HIP2309 - S2.pptx"]["support"])
        self.assertNotIn("Vidéo : Le danger des inégalités", par_nom)       # une video n'est pas une lecture
        self.assertTrue(par_nom["Article de Nippel"]["lien"])

    def test_pages_de_la_consigne_pour_un_fichier_seul(self):
        s = {"summary": "", "modules": [
            self.module("resource", "Aristote et la démocratie", "<p>Lire uniquement pp. 225-255.</p>", ["Aristote.pdf"]),
            self.module("folder", "Textes", "<p>Lire pp. 1-10.</p>", ["a.pdf", "b.pdf"])]}
        par_nom = {f["nom"]: f for f in sc.lectures_de_section(s, None)}
        self.assertEqual(sc.pages_a_lire({**par_nom["Aristote.pdf"], "pages": 412}), 31)
        self.assertIsNone(par_nom["a.pdf"]["pages_consigne"])             # dossier : a quel fichier ?

    def test_sans_consigne_reste_deduit(self):
        s = {"summary": "", "modules": [self.module("resource", "Sélection de chapitres du Leviathan", "",
                                                    ["Hobbes-complet.pdf"])]}
        f = sc.lectures_de_section(s, None)[0]
        self.assertEqual(f["origine"], "déduit")


class Changements(unittest.TestCase):
    def etat(self, date, lectures, titre="S9 - Hobbes"):
        return {"date": date, "titre": titre, "cours": "HIP", "lectures": lectures}

    def diff(self, avant, apres):
        return sc.differences(avant, apres, D(2026, 11, 16), D(2026, 11, 29))

    def test_lecture_ajoutee(self):
        msgs, nouvelles = self.diff({"1:9": self.etat("2026-11-18", [])}, {"1:9": self.etat("2026-11-18", ["Hobbes.pdf"])})
        self.assertEqual(nouvelles, {("1:9", "Hobbes.pdf")})
        self.assertIn("lecture ajoutée", msgs[0])

    def test_date_changee_et_disparue(self):
        msgs, _ = self.diff({"1:9": self.etat("2026-11-18", []), "1:10": self.etat("2026-11-25", [])},
                            {"1:9": self.etat("2026-11-25", [])})
        self.assertTrue(any("changé de date" in m for m in msgs))
        self.assertTrue(any("n'est plus trouvée" in m for m in msgs))

    def test_nouvelle_seance(self):
        msgs, _ = self.diff({}, {"2:4": self.etat("2026-11-18", [], "18 novembre 2026")})
        self.assertIn("nouvelle séance", msgs[0])

    def test_hors_periode_ignore(self):
        msgs, _ = self.diff({"1:2": self.etat("2026-09-23", [])}, {"1:2": self.etat("2026-09-23", ["x.pdf"])})
        self.assertEqual(msgs, [])

    def test_instantane(self):
        s = avec_lectures(seance("hip", "S8 - 11/11 - Hobbes", MER), 1)
        s["section"] = 8
        self.assertEqual(sc.instantane([s])["hip:8"]["lectures"], ["texte0.pdf"])


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


class EcheancesManuelles(unittest.TestCase):
    def test_formats(self):
        import ma_semaine as m
        texte = ("<!-- - 01.01.2000 · exemple ignoré -->\n"
                 "- 01.11.2026 23:59 · Théories économiques · Rendu intro, plan, bibliographie\n"
                 "- 2026-12-15 · Dossier final\n"
                 "- 3.12.26 14h00 : TP Méthodes\n"
                 "- pas une date\n")
        e = m.echeances_manuelles(texte)
        self.assertEqual([x["date"] for x in e], [dt.datetime(2026, 11, 1, 23, 59), dt.datetime(2026, 12, 15, 23, 59),
                                                  dt.datetime(2026, 12, 3, 14, 0)])
        self.assertEqual(e[0]["cours"], "Théories économiques")
        self.assertEqual(e[0]["nom"], "Rendu intro, plan, bibliographie")
        self.assertEqual(e[1]["cours"], "")
        self.assertTrue(all(x["manuelle"] for x in e))

    def test_section_conservee(self):
        import ma_semaine as m
        texte = "x\n## Mes échéances\n\n- 01.11.2026 · A · B\n\n## Notes\n\nmes notes\n"
        self.assertEqual(m.section(texte, m.TITRE_MES_ECHEANCES, "## Notes"), "- 01.11.2026 · A · B")
        self.assertEqual(m.section(texte, "## Notes", None), "mes notes")


class NomsDeCours(unittest.TestCase):
    def test_noms(self):
        cas = {"COURS_Introduction à la recherche (2026-2027)": "Introduction à la recherche (cours)",
               " COURS_Introduction à la science politique (2026-2027)": "Introduction à la science politique (cours)",
               "SEM_Introduction aux théories économiques - SITE (2026-2027)":
                   "Introduction aux théories économiques - SITE (séminaire)",
               "Institutions et régimes politiques (2026" + sc.TIRETS[0] + "2027)": "Institutions et régimes politiques",
               "Histoire des idées politiques - Cours (2026-2027)": "Histoire des idées politiques - Cours",
               "Political Theory &amp; Ideas": "Political Theory & Ideas"}
        for brut, attendu in cas.items():
            with self.subTest(brut=brut):
                self.assertEqual(sc.nom_affiche(brut), attendu)


class Vitesse(unittest.TestCase):
    def test_formats_de_temps(self):
        import ma_semaine as m
        cas = {"· réel : 70 min": 70, "reel 45": 45, "réel: 1 h 10": 70, "réel : 2h": 120, "Réel : 1h05": 65,
               "réel : 120": 120, "pas de temps": None, "réel : 0": None}
        for texte, attendu in cas.items():
            with self.subTest(texte=texte):
                self.assertEqual(m.minutes_reelles(texte), attendu)

    def test_calcul_et_valeurs_aberrantes(self):
        import ma_semaine as m
        self.assertEqual(m.calcul_vitesse({"a": (20, 60), "b": (10, 60)}), (15.0, 2))
        self.assertEqual(m.calcul_vitesse({"a": (20, 60), "faute": (300, 5)}), (20.0, 1))
        self.assertIsNone(m.calcul_vitesse({}))

    def test_mesures_lues_dans_le_fichier(self):
        import ma_semaine as m, tempfile
        texte = ("- [x] Hobbes (29 p., 2 h 25) · *À lire (déduit)* · réel : 1 h 30 <!-- id:aaa -->\n"
                 "- [ ] Castoriadis (27 p. d'après la consigne : pp. 1-27, 2 h 15) · réel 90 <!-- id:bbb -->\n"
                 "- [ ] Sans temps (10 p., 50 min) <!-- id:ccc -->\n")
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "Ma semaine.md")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write(texte)
            self.assertEqual(m.lire_ancien(chemin)[3], {"aaa": (29, 90), "bbb": (27, 90)})
