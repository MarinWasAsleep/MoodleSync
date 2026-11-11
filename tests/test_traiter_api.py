"""Tests hors ligne des reponses nouvelles de l'API des textes (tache R4, contrat 4.1, 4.2, 4.4 et 4.7).

Aucune fenetre, aucun reseau, aucun vrai moteur : le coffre, les PDF et les doublures viennent de
`tests/test_api_textes.py`, dont `Base` sert de banc. Chaque reponse est comparee a sa fixture de
`docs/refonte-textes/fixtures/` par `tests.formes_refonte.differences` : la forme du contrat, cle par cle.

Ce que ces tests ne mesurent pas : aucun vrai moteur de reconnaissance, ni Windows ni macOS, aucune vraie boite de
dialogue native. Les PDF « scannes » sont fabriques a la main et le moteur est une doublure.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t . -v
"""
import json, os, shutil, sys, tempfile, threading, unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import moteur as ms, ocr, textes_arbre
from tests import test_api_textes as T
from tests.formes_refonte import charger_fixture, differences

SCAN = ([], True)          # une page a reconnaitre : PDF remplace, copie d'original
NATIF = (["Page de cours deja textuelle, relue et corrigee, avec assez de caracteres pour que la page soit un "
          "texte et non une image a reconnaitre"], False)      # page deja textuelle : aucun remplacement (O2)


class Banc(T.Base):
    """Le banc de test_api_textes, avec deux documents de deux et une pages, et deux cours."""

    def setUp(self):
        super().setUp()
        self.ranger("Cours A/S1/long.pdf", [SCAN] * 2)
        self.ranger("Cours A/S1/court.pdf", [SCAN])
        self.ranger("Cours B/S2/texte.pdf", [NATIF])
        # La fabrication du PDF cherchable est une doublure : elle remplace le fichier par un contenu different
        # (ce que fait la vraie, page par page) sans passer par pypdf, et rend ce que `traiter_document` attend.
        p = mock.patch.object(ocr, "fabriquer_pdf_cherchable", self.fabriquer)
        p.start()
        self.addCleanup(p.stop)

    def fabriquer(self, dest, chemin_rel, cfg, *, arreter=None):
        """Doublure de la fabrication du PDF cherchable : celle du banc, qui change la taille et ecrit `genere`.

        Une doublure qui garde la taille du fichier masque E-V3-1 (revue V3) : `textes_arbre` ne peut alors pas
        distinguer un PDF remplace d'un PDF perime. La doublure vit donc dans `test_api_textes.Base`, seule source.
        """
        return T.Base.fabriquer(self, dest, chemin_rel, cfg, arreter=arreter)

    def ecrire_texte(self, rel, contenu):
        chemin = os.path.join(self.dest, *rel.split("/"))
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenu)
        return chemin


# ------------------------------------------------------------------ ocr_etat (4.2)
class Etat(Banc):
    """Forme de 4.2, compteurs de l'arbre, copies d'originaux."""

    def test_forme_egale_a_la_fixture(self):
        self.traiter("Cours A/S1/long.pdf")
        r = self.json_ok(self.api.ocr_etat())
        self.assertEqual(differences(charger_fixture("etat.json"), r), [])

    def test_compteurs_de_l_arbre(self):
        self.traiter("Cours A/S1/long.pdf")
        etat = self.json_ok(self.api.ocr_etat())
        self.assertEqual(etat["compteurs"], self.json_ok(self.api.ocr_arbre())["compteurs"])
        self.assertEqual(etat["compteurs"]["fichiers"], 3)
        self.assertEqual(etat["compteurs"]["traites"], 1)
        self.assertEqual(etat["compteurs"]["non_traites"], 2)

    def test_file_etat_pendant_le_traitement(self):
        """E-V3-2 : pendant le travail, `ocr_etat().file` porte `en_cours` et le document en cours (4.2).

        `_ocr_bloc_file` lit `ocr.charger_file`, qui ramene `en_cours` a `pause` par construction : sans l'etat
        du fil, la coque afficherait « en pause » et perdrait le nom du document a chaque rafraichissement.
        """
        self.ranger("Cours A/S1/grand.pdf", [SCAN] * 3)
        ouvert, libere = threading.Event(), threading.Event()
        vrai = self.executer

        def executer(args, *, delai, arreter=None):
            if not ouvert.is_set():
                ouvert.set()
                self.assertTrue(libere.wait(15), "la page 1 n'a pas ete relachee")
            return vrai(args, delai=delai, arreter=arreter)

        with mock.patch.object(ocr, "executer", executer):
            self.assertEqual(set(self.json_ok(self.api.ocr_traiter(["Cours A/S1/grand.pdf"], False, True))),
                             {"file"})
            self.assertTrue(ouvert.wait(15), "aucune page n'a demarre")
            etat = self.json_ok(self.api.ocr_etat())
            self.assertEqual(differences(charger_fixture("etat.json")["file"], etat["file"]), [])
            self.assertEqual(etat["file"]["etat"], "en_cours")
            self.assertEqual(etat["file"]["document"], "Cours A/S1/grand.pdf")
            self.assertEqual((etat["file"]["pages"], etat["file"]["documents_total"]), (3, 1))
            self.assertEqual(etat["file"]["reprise"], 0)
            self.assertTrue(etat["occupe"])
            libere.set()
            self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertEqual(self.json_ok(self.api.ocr_etat())["file"]["etat"], "terminee")

    def test_aucune_cle_retiree(self):
        r = self.json_ok(self.api.ocr_etat())
        for retire in ("active", "mode_pdf", "prevision", "a_preparer", "pages_a_preparer", "octets_texte",
                       "orphelins"):
            with self.subTest(cle=retire):
                self.assertNotIn(retire, r)
        self.assertEqual(list(r["reglages"]), ["ocr_langues", "ocr_dpi", "ocr_format"])
        self.assertNotIn("compteurs.documents", ".".join(r["compteurs"]))
        self.assertNotIn("a_verifier", [k for k, v in r.items() if not isinstance(v, dict)])

    def test_originaux(self):
        self.traiter("Cours A/S1/long.pdf")
        r = self.json_ok(self.api.ocr_etat())
        self.assertEqual(r["originaux"]["nombre"], 1)
        self.assertGreater(r["originaux"]["octets"], 0)

    def test_depot_inerte(self):
        """4.2 : le bloc depot existe deja, inerte, en attendant R5."""
        self.assertEqual(self.json_ok(self.api.ocr_etat())["depot"],
                         {"etat": "inactif", "dossier_defaut": self.api.ocr_etat()["depot"]["dossier_defaut"],
                          "dossier": "", "resultats": []})


# ------------------------------------------------------------------ ocr_traiter (4.4)
class Traiter(Banc):
    """4.4 : sans confirmation rien ne part ; avec, la file se constitue et l'executeur demarre."""

    def test_sans_confirme_ne_lance_rien(self):
        avant = self.instantane()
        r = self.json_ok(self.api.ocr_traiter(["Cours A/S1/long.pdf"]))
        self.assertEqual(differences(charger_fixture("traiter_confirmation.json"), r), [])
        self.assertEqual((r["documents"], r["pages"]), (1, 2))
        self.assertEqual(r["remplacements"], 1)
        self.assertEqual(len(r["minutes"]), 2)
        self.assertEqual(r["minutes"], self.api._ocr_minutes(2, self.config()))
        self.assertEqual(r["confirmer"], ocr.MESSAGES["confirmation_traitement"].format(
            n="1 document", p="2 pages", m=r["minutes"][0], x=r["minutes"][1], r=1))
        self.assertIsNone(self.api._ocr_fil)
        self.assertEqual(self.pages_vues, [])
        self.assertEqual(self.instantane(), avant)          # ni file, ni cache, ni texte ecrits

    def test_duree_annoncee_au_moins_quinze_secondes_par_page(self):
        """E-V7-4 et O18 : la mesure V7 donne 14 s par page au mieux (79 s sous charge), donc la fourchette
        annoncee part de 15 s par page et va jusqu'a 30 s, avec un plancher d'une minute."""
        self.ranger("Cours A/S1/seize.pdf", [SCAN] * 16)
        r = self.json_ok(self.api.ocr_traiter(["Cours A/S1/seize.pdf"]))
        self.assertEqual(r["pages"], 16)
        self.assertEqual(r["minutes"], [4, 8], "16 pages : 240 s au mieux, 480 s au plus")
        self.assertIn("4 à 8 minutes", r["confirmer"])

    def test_duree_arrondie_par_exces(self):
        """5 pages : 75 s et 150 s, arrondis au-dessus donnent 2 a 3 minutes (un arrondi au plus proche
        annoncerait 1 a 2 minutes, donc moins que la mesure)."""
        self.ranger("Cours A/S1/cinq.pdf", [SCAN] * 5)
        r = self.json_ok(self.api.ocr_traiter(["Cours A/S1/cinq.pdf"]))
        self.assertEqual((r["pages"], r["minutes"]), (5, [2, 3]))

    def test_duree_plancher_d_une_minute(self):
        """Une page : 15 s et 30 s, annoncees 1 a 1 minute, jamais « 0 minute »."""
        r = self.json_ok(self.api.ocr_traiter(["Cours A/S1/court.pdf"]))
        self.assertEqual((r["pages"], r["minutes"]), (1, [1, 1]))

    def test_avec_confirme_met_en_file_et_demarre(self):
        r = self.json_ok(self.api.ocr_traiter(["Cours A/S1/long.pdf"], False, True))
        self.assertEqual(set(r), {"file"})
        self.assertEqual(r["file"]["origine"], "coffre")
        self.assertEqual(differences(charger_fixture("etat.json")["file"], r["file"]), [])
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertEqual(len(self.pages_vues), 2)
        self.assertEqual([t["etat"] for t in self.fichier()["taches"]], ["fait"])

    def test_pdf_remplace_reste_traite_dans_l_arbre(self):
        """E-V3-1 : la fabrication change la taille du PDF (comme la vraie) ; il reste « Traite » (4.3).

        « Restaurer l'original » est propose quand `remplace` ou `texte` est vrai (textes-arbre.js, 5.3) : les
        deux sont donc verifies ici, avec les compteurs et la sortie.
        """
        chemin = os.path.join(self.dest, "Cours A", "S1", "long.pdf")
        avant = os.path.getsize(chemin)
        resultat = self.traiter("Cours A/S1/long.pdf")
        self.assertEqual((resultat["statut"], resultat["remplace"], resultat["texte"]), ("ok", True, True))
        noeuds = {n["chemin"]: n for n in textes_arbre.fichiers_sous(self.dest, self.config(), ["Cours A"])}
        noeud = noeuds["Cours A/S1/long.pdf"]
        self.assertNotEqual(noeud["octets"], avant)               # la fabrication a bien change la taille
        self.assertEqual(noeud["statut"], "traite")
        self.assertTrue(noeud["texte"])
        self.assertTrue(noeud["remplace"])
        self.assertTrue(noeud["original_conserve"])
        self.assertEqual(noeud["sortie"], "Cours A/S1/long.pdf.md")
        self.assertEqual(self.api.ocr_arbre()["compteurs"],
                         {"fichiers": 3, "traites": 1, "a_verifier": 0, "echecs": 0, "non_traites": 2,
                          "pages_non_traitees": 0})
        self.assertEqual(self.json_ok(self.api.ocr_etat())["compteurs"], self.api.ocr_arbre()["compteurs"])

    def test_lien_symbolique_sortant_n_est_pas_traite(self):
        """E-V3-3 : un chemin qui mene hors du coffre est refuse (contrat 4, confinement de `_ocr_confiner`)."""
        dehors = tempfile.mkdtemp(prefix="dehors-")
        self.addCleanup(shutil.rmtree, dehors, True)
        with open(os.path.join(dehors, "secret.pdf"), "wb") as f:
            f.write(T.pdf_minimal([SCAN]))
        try:
            os.symlink(dehors, os.path.join(self.dest, "lien"))
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles")
        avant = self.instantane()
        for chemin in ("lien", "lien/secret.pdf"):
            with self.subTest(chemin=chemin):
                self.assertEqual(self.json_ok(self.api.ocr_traiter([chemin])), {"rien": True})
        self.assertEqual(self.fichier()["taches"], [])
        self.assertEqual(self.instantane(), avant)

    def test_dossier_developpe_une_seule_fois(self):
        """Un dossier vaut tous ses fichiers eligibles, recursivement ; doublons fusionnes."""
        r = self.json_ok(self.api.ocr_traiter(["Cours A", "Cours A/S1/long.pdf", "Cours A/S1/long.pdf"]))
        self.assertEqual((r["documents"], r["pages"], r["remplacements"]), (2, 3, 2))
        self.assertEqual([t["chemin"] for t in self.fichier()["taches"]], [])      # rien d'ecrit sans confirme
        r = self.json_ok(self.api.ocr_traiter(["Cours A", "Cours A/S1/long.pdf"], False, True))
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertEqual(sorted(t["chemin"] for t in self.fichier()["taches"]),
                         ["Cours A/S1/court.pdf", "Cours A/S1/long.pdf"])

    def test_pdf_natif_ne_compte_pas_dans_les_remplacements(self):
        r = self.json_ok(self.api.ocr_traiter(["Cours B/S2/texte.pdf"]))
        self.assertEqual((r["documents"], r["pages"], r["remplacements"]), (1, 1, 0))

    def test_image_ne_compte_pas_dans_les_remplacements(self):
        """O2 : seul un PDF peut etre remplace ; une image n'entre que pour son texte."""
        from PIL import Image
        chemin = os.path.join(self.dest, "Cours C", "photo.png")
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        Image.new("L", (40, 40), 255).save(chemin)
        r = self.json_ok(self.api.ocr_traiter(["Cours C/photo.png"]))
        self.assertEqual((r["documents"], r["pages"], r["remplacements"]), (1, 1, 0))

    def test_melange_coffre_entier(self):
        r = self.json_ok(self.api.ocr_traiter(["Cours A", "Cours B"]))
        self.assertEqual((r["documents"], r["pages"], r["remplacements"]), (3, 4, 2))

    def test_rien(self):
        self.assertEqual(self.api.ocr_traiter([]), {"rien": True})
        self.assertEqual(self.api.ocr_traiter(["Cours A/S1/absent.pdf"]), {"rien": True})
        self.assertEqual(self.api.ocr_traiter("pas une liste"), {"rien": True})

    def test_traite_ignore_sans_refaire(self):
        self.traiter("Cours A/S1/long.pdf")
        self.assertEqual(self.api.ocr_traiter(["Cours A/S1/long.pdf"]), {"rien": True})
        r = self.json_ok(self.api.ocr_traiter(["Cours A/S1/long.pdf"], True))
        self.assertEqual(r["documents"], 1)

    def test_echec_ignore_sans_refaire(self):
        """O4 : un echec est memorise, il ne se retente que par `refaire` (« Reessayer »)."""
        self.ranger("Cours A/S1/vide.pdf", [([], False)])
        entree = self.traiter("Cours A/S1/vide.pdf")
        self.assertEqual(entree["statut"], "echec")
        self.assertEqual(self.api.ocr_traiter(["Cours A/S1/vide.pdf"]), {"rien": True})
        r = self.json_ok(self.api.ocr_traiter(["Cours A/S1/vide.pdf"], refaire=True))
        self.assertEqual(r["documents"], 1)
        self.assertEqual(self.api.ocr_traiter(["Cours A/S1/vide.pdf"], refaire=True, confirme=True)["file"]["etat"],
                         "inactive")
        self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))
        self.assertFalse(self.fichier()["taches"][0].get("refaire") is False)   # la tache porte `refaire`

    def test_moteur_absent(self):
        self.bloc = dict(T.BLOC_MOTEUR, present=False)
        self.assertEqual(self.api.ocr_traiter(["Cours A/S1/long.pdf"]),
                         {"erreur": ocr.MESSAGES["moteur_absent"]})
        self.assertEqual(self.fichier()["taches"], [])

    def test_file_occupee(self):
        from types import SimpleNamespace
        self.api._ocr_fil = SimpleNamespace(is_alive=lambda: True)
        self.assertEqual(self.api.ocr_traiter(["Cours A/S1/long.pdf"]), {"erreur": ocr.MESSAGES["occupe"]})

    def test_chemin_hors_coffre_ignore(self):
        """4 : un chemin recu est relatif au coffre ; `..` et un nom cache ne designent aucun document."""
        avant = self.instantane()
        for chemin in ("../secret.pdf", ".moodlesync-ocr/cache.json", "/etc/passwd", "Cours A/S1/long.pdf\x00"):
            with self.subTest(chemin=chemin):
                self.assertEqual(self.json_ok(self.api.ocr_traiter([chemin])), {"rien": True})
        self.assertEqual(self.instantane(), avant)

    def test_deja_en_file_ignore(self):
        """4.4 : un document deja dans la file n'y entre pas deux fois."""
        ocr.sauver_file(self.dest, {"version": 1, "etat": "inactive", "portee": "chemins", "origine": "coffre",
                                    "cree": "", "taches": [ocr._tache("Cours A/S1/long.pdf", "attente", 2)]})
        self.assertEqual(self.api.ocr_traiter(["Cours A/S1/long.pdf"]), {"rien": True})
        self.assertEqual(self.api.ocr_traiter(["Cours A/S1/long.pdf"], refaire=True), {"rien": True})
        self.assertEqual(len(ocr.charger_file(self.dest)["taches"]), 1)

    def test_dossier_absent(self):
        c = self.config()
        c["dest"] = ""
        self.configurer(c)
        self.assertEqual(self.api.ocr_traiter(["Cours A"]), {"erreur": ocr.MESSAGES["dossier_absent"]})

    def test_exception_inattendue_marque_l_echec_et_continue(self):
        """M20, 3.2 etape 5c : une exception imprevue de la fabrication ne sort pas de `traiter_document` ;
        le document est un echec de motif `erreur`, sans aucune trace a cote du PDF, et la file passe au
        document suivant (elle ne s'arrete pas)."""
        pdf = os.path.join(self.dest, "Cours A", "S1", "long.pdf")
        with open(pdf, "rb") as f:
            avant = f.read()

        def panne(dest, chemin_rel, cfg, *, arreter=None):
            raise RuntimeError("panne imprevue de la fabrication")

        with mock.patch.object(ocr, "fabriquer_pdf_cherchable", panne):
            self.api.ocr_traiter(["Cours A/S1/long.pdf", "Cours A/S1/court.pdf"], False, True)
            self.assertTrue(self.attendre(lambda: self.fichier()["etat"] == "terminee"))

        entree = ocr.charger_cache(self.dest)["documents"]["Cours A/S1/long.pdf"]
        self.assertEqual((entree["etat"], entree["motif"]), ("echec", "erreur"))
        with open(pdf, "rb") as f:
            self.assertEqual(f.read(), avant)                      # PDF intact, octet pour octet
        self.assertFalse(os.path.exists(pdf + ".md"))
        self.assertEqual(os.listdir(os.path.join(self.dest, ocr.CACHE, ocr.DOSSIER_ORIGINAUX)), [])
        # La file n'est pas arretee : le second document est traite.
        self.assertEqual([t["etat"] for t in self.fichier()["taches"]], ["fait", "fait"])
        self.assertIn("Cours A/S1/court.pdf", ocr.charger_cache(self.dest)["documents"])


# ------------------------------------------------------------------ ocr_copier_texte (4.7)
class Copier(Banc):
    """4.7 : le texte du document, sans front matter ni section « Pages a verifier »."""

    def test_md(self):
        self.traiter("Cours A/S1/long.pdf")
        r = self.json_ok(self.api.ocr_copier_texte("Cours A/S1/long.pdf"))
        self.assertEqual(set(r), {"texte", "caracteres", "pages"})
        self.assertNotIn("moodlesync:", r["texte"])
        self.assertFalse(r["texte"].startswith("---"))
        self.assertIn("Bonjour", r["texte"])
        self.assertEqual(r["pages"], 2)
        self.assertEqual(r["caracteres"], len(r["texte"]))
        self.assertEqual(r["texte"].count("<!-- page"), 2)

    def test_md_sans_section_a_verifier(self):
        self.traiter("Cours A/S1/court.pdf")
        entree = ocr.charger_cache(self.dest)["documents"]["Cours A/S1/court.pdf"]
        chemin = ocr._resoudre_sortie(self.dest, entree["sortie"])
        with open(chemin, "a", encoding="utf-8") as f:
            f.write("\n## Pages à vérifier\n\n- page 1 : confiance 0,5\n")
        r = self.json_ok(self.api.ocr_copier_texte("Cours A/S1/court.pdf"))
        self.assertNotIn("Pages à vérifier", r["texte"])
        self.assertNotIn("confiance", r["texte"])

    def test_txt(self):
        c = self.config()
        c["ocr_format"] = "txt"
        self.configurer(c)
        self.traiter("Cours A/S1/court.pdf")
        r = self.json_ok(self.api.ocr_copier_texte("Cours A/S1/court.pdf"))
        self.assertEqual(set(r), {"texte", "caracteres", "pages"})
        self.assertIn("[p. 1]", r["texte"])
        self.assertFalse(r["texte"].startswith("---"))
        self.assertEqual(r["pages"], 1)

    def test_vide(self):
        self.ranger("Cours A/S1/blanc.pdf", [([], False)])
        self.traiter("Cours A/S1/blanc.pdf")
        self.assertEqual(self.api.ocr_copier_texte("Cours A/S1/blanc.pdf"),
                         {"erreur": ocr.MESSAGES["copie_vide"]})
        self.ranger("Cours A/S1/jamais.pdf", [SCAN])
        self.assertEqual(self.api.ocr_copier_texte("Cours A/S1/jamais.pdf"),
                         {"erreur": ocr.MESSAGES["copie_vide"]})

    def test_chemin_refuse(self):
        for chemin in ("../x.pdf", None, "Cours A/S1/absent.pdf"):
            with self.subTest(chemin=chemin):
                self.assertEqual(self.api.ocr_copier_texte(chemin),
                                 {"erreur": ocr.MESSAGES["ouverture_refusee"]})


# ------------------------------------------------------------------ ocr_ouvrir (4.1)
class Ouvrir(Banc):
    """4.1 : le PDF du coffre s'ouvre avec le lecteur du systeme, jamais un shell, et le confinement tient.

    Aucun lecteur n'est lance : `subprocess.Popen` et `os.startfile` sont doubles. Le systeme d'execution
    des tests n'est ni Windows ni macOS (les trois formes de commande se verifient sur la fonction pure).
    """

    def test_commande_par_systeme(self):
        from moodlesync.api_textes import commande_ouvrir
        pdf = os.path.join(self.dest, "Cours A", "S1", "court.pdf")
        self.assertEqual(commande_ouvrir(pdf, "win32"), None, "Windows passe par os.startfile")
        self.assertEqual(commande_ouvrir(pdf, "darwin"), ["open", pdf])
        self.assertEqual(commande_ouvrir(pdf, "linux"), ["xdg-open", pdf])
        self.assertEqual(commande_ouvrir(pdf, "freebsd13"), ["xdg-open", pdf], "ailleurs : xdg-open")

    def test_ouvre_le_pdf_avec_le_lecteur_du_systeme(self):
        self.ranger("Cours A/S1/court.pdf", [SCAN])
        pdf = os.path.join(self.dest, "Cours A", "S1", "court.pdf")
        with mock.patch("moodlesync.api_textes.subprocess.Popen") as lance:
            r = self.api.ocr_ouvrir("Cours A/S1/court.pdf")
        self.assertEqual(r, {"ok": True}, "une ouverture reussie ne dit rien de plus")
        self.assertEqual(lance.call_count, 1, "un seul lancement")
        args, options = lance.call_args
        self.assertIsInstance(args[0], list, "une liste d'arguments, jamais une chaine")
        self.assertEqual(args[0][-1], pdf, "le fichier ouvert est le PDF du coffre")
        self.assertIs(options.get("shell"), False, "jamais un shell")

    def test_la_cle_page_est_ignoree(self):
        self.ranger("Cours A/S1/court.pdf", [SCAN])
        with mock.patch("moodlesync.api_textes.subprocess.Popen") as lance:
            r = self.api.ocr_ouvrir("Cours A/S1/court.pdf", page=3)
        self.assertEqual(r, {"ok": True})
        self.assertEqual(lance.call_args[0][0][-1], os.path.join(self.dest, "Cours A", "S1", "court.pdf"))

    def test_windows_passe_par_os_startfile(self):
        pdf = self.ranger("Cours A/S1/court.pdf", [SCAN])
        pdf = os.path.join(self.dest, "Cours A", "S1", "court.pdf")
        with mock.patch("moodlesync.api_textes.sys.platform", "win32"), \
             mock.patch("moodlesync.api_textes.os.startfile", create=True) as demarre, \
             mock.patch("moodlesync.api_textes.subprocess.Popen") as lance:
            r = self.api.ocr_ouvrir("Cours A/S1/court.pdf")
        self.assertEqual(r, {"ok": True})
        demarre.assert_called_once_with(pdf)
        self.assertEqual(lance.call_count, 0, "sous Windows, aucun sous-processus")

    def test_un_dossier_est_refuse(self):
        self.ranger("Cours A/S1/court.pdf", [SCAN])
        with mock.patch("moodlesync.api_textes.subprocess.Popen") as lance:
            r = self.api.ocr_ouvrir("Cours A/S1")
        self.assertEqual(r, {"erreur": ocr.MESSAGES["ouverture_refusee"]}, "un dossier passe par ocr_afficher")
        self.assertEqual(lance.call_count, 0, "rien n'est lance pour un dossier")

    def test_un_chemin_hors_du_coffre_est_refuse(self):
        dehors = os.path.join(self.d, "hors.pdf")
        with open(dehors, "wb") as f:
            f.write(b"%PDF-1.4\n")
        for chemin in ("../hors.pdf", dehors, None, "", "Cours A/S1/absent.pdf"):
            with self.subTest(chemin=chemin):
                with mock.patch("moodlesync.api_textes.subprocess.Popen") as lance:
                    r = self.api.ocr_ouvrir(chemin)
                self.assertEqual(r, {"erreur": ocr.MESSAGES["ouverture_refusee"]})
                self.assertEqual(lance.call_count, 0, "un chemin refuse ne lance rien")

    def test_un_lancement_impossible_dit_l_erreur(self):
        self.ranger("Cours A/S1/court.pdf", [SCAN])
        with mock.patch("moodlesync.api_textes.subprocess.Popen", side_effect=OSError("absent")):
            r = self.api.ocr_ouvrir("Cours A/S1/court.pdf")
        self.assertEqual(r, {"erreur": ocr.MESSAGES["ouverture_refusee"]}, "jamais une trace d'exception")


# ------------------------------------------------------------------ ocr_restaurer (4.7, 3.3)
class Restaurer(Banc):
    """4.7 et 3.3 : deux temps, copie locale d'abord, puis le document redevient « Non traite »."""

    def test_deux_temps(self):
        self.traiter("Cours A/S1/court.pdf")
        avant = self.instantane()
        self.assertEqual(self.api.ocr_restaurer("Cours A/S1/court.pdf"),
                         {"confirmer": ocr.MESSAGES["confirmation_restauration"]})
        self.assertEqual(self.instantane(), avant)          # sans `confirme`, rien n'est touche
        pdf = os.path.join(self.dest, "Cours A", "S1", "court.pdf")
        with open(pdf, "rb") as f:
            remplace = f.read()
        r = self.json_ok(self.api.ocr_restaurer("Cours A/S1/court.pdf", True))
        self.assertEqual(r, {"ok": True})
        with open(pdf, "rb") as f:
            self.assertNotEqual(f.read(), remplace)          # le PDF d'origine est revenu
        self.assertNotIn("Cours A/S1/court.pdf", ocr.charger_cache(self.dest)["documents"])
        self.assertFalse(os.path.exists(pdf + ".md"))
        self.assertEqual(self.api.ocr_arbre()["compteurs"]["non_traites"], 3)

    def poser_genere(self, rel):
        """Ecrit dans `.moodlesync.json` le bloc `genere` que la vraie fabrication pose : la doublure de ce banc
        ne l'ecrit pas, et c'est lui qui dit quel fichier MoodleSync a fabrique (invariant 8)."""
        chemin = os.path.join(self.dest, *rel.split("/"))
        ident = ocr.identite(chemin)
        ms.sauver_etat(self.dest, {rel: {"t": 1760000000, "chemin": rel.replace("/", os.sep),
                                         "genere": {"type": "pdf_cherchable", "version": 1,
                                                    "taille_source": ident["taille"],
                                                    "empreinte_source": ident["empreinte"],
                                                    "taille_fichier": ident["taille"],
                                                    "empreinte_fichier": ident["empreinte"],
                                                    "pages": 1, "date": "2026-11-11T10:00:00"}}})

    def test_pdf_modifie_a_la_main_demande_confirmation(self):
        """E-V2-5, invariant 8 : un PDF retouche a la main apres le traitement recoit la phrase `modifie_main`
        avant toute remise (comme l'ancien `ocr_pdf_restaurer`), et l'original n'est remis qu'avec `confirme`."""
        rel = "Cours A/S1/court.pdf"
        pdf = os.path.join(self.dest, "Cours A", "S1", "court.pdf")
        with open(pdf, "rb") as f:
            origine = f.read()
        self.traiter(rel)
        self.poser_genere(rel)
        with open(pdf, "ab") as f:
            f.write(b"\n% retouche a la main\n")
        avant = self.instantane()

        self.assertEqual(self.api.ocr_restaurer(rel), {"confirmer": ocr.MESSAGES["modifie_main"]})
        self.assertEqual(self.instantane(), avant)          # rien n'est remis sans l'accord

        self.assertEqual(self.json_ok(self.api.ocr_restaurer(rel, True)), {"ok": True})
        with open(pdf, "rb") as f:
            remis = f.read()
        self.assertEqual(remis, origine)                    # la copie locale, octet pour octet
        self.assertNotIn(b"retouche a la main", remis)
        self.assertNotIn(rel, ocr.charger_cache(self.dest)["documents"])

    def test_chemin_refuse(self):
        self.assertEqual(self.api.ocr_restaurer("../x.pdf", True),
                         {"erreur": ocr.MESSAGES["ouverture_refusee"]})
        self.assertEqual(self.api.ocr_restaurer(None), {"erreur": ocr.MESSAGES["ouverture_refusee"]})


# ------------------------------------------------------------------ ocr_originaux_supprimer (4.7)
class Originaux(Banc):
    """4.7 et O15 : liberer les copies, en deux temps, et le dire."""

    def test_deux_temps(self):
        self.traiter("Cours A/S1/long.pdf")
        nombre, octets = self.api.ocr_etat()["originaux"]["nombre"], self.api.ocr_etat()["originaux"]["octets"]
        self.assertEqual(nombre, 1)
        r = self.json_ok(self.api.ocr_originaux_supprimer())
        self.assertEqual(set(r), {"confirmer", "nombre", "octets"})
        self.assertEqual((r["nombre"], r["octets"]), (nombre, octets))
        self.assertEqual(self.api.ocr_etat()["originaux"]["nombre"], 1)      # toujours la sans `confirme`
        r = self.json_ok(self.api.ocr_originaux_supprimer(True))
        self.assertEqual(r, {"ok": True, "nombre": nombre, "octets": octets})
        self.assertEqual(self.api.ocr_etat()["originaux"], {"nombre": 0, "octets": 0})
        entree = ocr.charger_cache(self.dest)["documents"]["Cours A/S1/long.pdf"]
        self.assertIsNone(entree["original"])          # plus de copie : restauration par Moodle seulement

    def test_sans_copie(self):
        self.assertEqual(self.json_ok(self.api.ocr_originaux_supprimer()),
                         {"confirmer": self.api.ocr_originaux_supprimer()["confirmer"], "nombre": 0, "octets": 0})
        self.assertEqual(self.api.ocr_originaux_supprimer(True), {"ok": True, "nombre": 0, "octets": 0})


# ------------------------------------------------------------------ ocr_regler (4.1)
class Regler(Banc):
    """4.1 : neuf cles acceptees, toute autre refusee, `ocr_format` en md ou txt."""

    ACCEPTEES = ("ocr_exe", "ocr_tessdata", "ocr_langues", "ocr_dpi", "ocr_psm", "ocr_max_mo", "ocr_threads",
                 "ocr_batterie", "ocr_format")
    RETIREES = ("ocr_pdf", "ocr_apres_sync", "ocr_dossier", "ocr_sortie_hors_coffre", "ocr", "inconnu")

    def test_cles_retirees_refusees(self):
        for cle in self.RETIREES:
            with self.subTest(cle=cle):
                r = self.json_ok(self.api.ocr_regler(cle, "x"))
                self.assertEqual(list(r), ["erreur"])
                self.assertEqual(r["erreur"], ocr.MESSAGES["reglage_inconnu"].format(cle=cle))
                self.assertNotIn(cle, self.config())

    def test_valeur_restee_dans_la_configuration_est_ignoree(self):
        """O10 : une valeur de `config.json` pour un reglage retire n'empeche rien et n'apparait plus."""
        c = self.config()
        c.update({"ocr_pdf": "remplacer", "ocr_apres_sync": False, "ocr_dossier": "Textes", "ocr": True,
                  "ocr_sortie_hors_coffre": True})
        self.configurer(c)
        self.assertEqual(self.json_ok(self.api.ocr_etat())["file"]["etat"], "inactive")
        self.assertNotIn("ocr_pdf", self.json_ok(self.api.ocr_etat()))
        self.assertEqual(self.json_ok(self.api.ocr_traiter(["Cours A/S1/court.pdf"]))["documents"], 1)

    def test_liste_blanche_et_bornes(self):
        for cle, valeur in (("ocr_dpi", 100), ("ocr_dpi", 601), ("ocr_dpi", "beaucoup"), ("ocr_psm", 2),
                            ("ocr_psm", 0), ("ocr_max_mo", 9), ("ocr_max_mo", 2001), ("ocr_threads", 0),
                            ("ocr_threads", 5), ("ocr_batterie", "dormir"), ("ocr_format", "pdf"),
                            ("ocr_format", ""), ("ocr_langues", "deu"),
                            ("ocr_exe", os.path.join(self.d, "absent.exe"))):
            with self.subTest(cle=cle, valeur=valeur):
                self.assertIn("erreur", self.json_ok(self.api.ocr_regler(cle, valeur)))

    def test_format(self):
        self.assertEqual(self.json_ok(self.api.ocr_regler("ocr_format", "txt"))["reglages"]["ocr_format"], "txt")
        self.assertEqual(self.config()["ocr_format"], "txt")
        self.assertEqual(self.json_ok(self.api.ocr_regler("ocr_format", "md"))["reglages"]["ocr_format"], "md")
        redemarre = T.app.Api()
        redemarre._fenetre = self.fenetre
        self.assertEqual(self.json_ok(redemarre.ocr_etat())["reglages"]["ocr_format"], "md")

    def test_valeurs_acceptees(self):
        self.assertEqual(self.json_ok(self.api.ocr_regler("ocr_dpi", 400))["reglages"]["ocr_dpi"], 400)
        self.assertEqual(self.config()["ocr_dpi"], 400)
        self.assertEqual(self.json_ok(self.api.ocr_regler("ocr_threads", 4))["file"]["etat"], "inactive")
        self.assertEqual(self.json_ok(self.api.ocr_regler("ocr_batterie", "continuer"))["reglages"]["ocr_dpi"], 400)
        self.assertEqual(self.config()["ocr_batterie"], "continuer")
        exe = os.path.join(self.d, "tesseract.exe")
        open(exe, "wb").close()
        self.assertTrue(self.json_ok(self.api.ocr_regler("ocr_exe", exe))["moteur"]["present"])
        self.assertEqual(self.config()["ocr_exe"], exe)


if __name__ == "__main__":
    unittest.main()
