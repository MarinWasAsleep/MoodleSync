"""Arborescence des textes (contrat 4.3) : forme, statuts, compteurs, confinement de `ocr_afficher`.

Les entrees de cache sont construites a la main selon le contrat 2.2 : ces tests ne dependent pas de R2.
Le coffre de la fixture est engendre dans un dossier temporaire (les tailles reelles n'ont pas a etre celles
de `fixtures/arbre.json`, seule la forme est comparee, plus les valeurs qui doivent tomber juste).
"""
import builtins
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from moodlesync import moteur as ms, ocr, textes_arbre
from moodlesync.api_arbre import ApiArbre, commande_afficher
from tests.formes_refonte import charger_fixture, differences

CFG = {"ocr_max_mo": 300, "ocr_format": "md"}
ZEROS = {"fichiers": 0, "traites": 0, "a_verifier": 0, "echecs": 0, "non_traites": 0, "pages_non_traitees": 0}
# Cles d'un noeud fichier dont la valeur est comparee a la fixture ; `octets` en est exclu (taille reelle du fichier).
CLES_COMPAREES = ("type", "nom", "chemin", "extension", "pages", "statut", "motif", "texte", "format", "sortie",
                  "remplace", "original_conserve", "confiance", "date")


def _entree(pages=None, etat="ok", **champs):
    """Entree de cache 2.2, minimale : ce que R2 ecrira, cle par cle.

    `taille` est remplie par `Base.cache` avec la taille du fichier ecrit, sauf quand un test la fixe volontairement
    (entree perimee).
    """
    entree = {"empreinte": "sha256:" + "0" * 64, "etat": etat, "date": "2026-11-10T14:31:53",
              "langues": "fra+eng", "dpi": 300, "psm": 3, "moteur": "5.5.0"}
    if pages is not None:
        entree["pages"] = pages
    entree.update(champs)
    return entree


def _noeud(arbre, chemin):
    pile = list(arbre.get("cours") or [])
    while pile:
        noeud = pile.pop()
        if noeud.get("chemin") == chemin:
            return noeud
        pile.extend(noeud.get("enfants") or [])
    return None


def _genere(taille_fichier, taille_source=100):
    """Bloc `genere` de `.moodlesync.json` (2.1) : l'identite du PDF recu et celle du PDF cherchable ecrit."""
    return {"type": "pdf_cherchable", "version": 1, "taille_source": taille_source,
            "empreinte_source": "sha256:" + "1" * 64,
            "taille_fichier": taille_fichier, "empreinte_fichier": "sha256:" + "2" * 64}


def _chemins(arbre):
    """Tous les chemins de l'arbre, dans l'ordre de lecture (dossiers et fichiers)."""
    sortie = []

    def descendre(noeuds):
        for noeud in noeuds:
            sortie.append(noeud["chemin"])
            descendre(noeud.get("enfants") or [])

    descendre(arbre.get("cours") or [])
    return sortie


def _noeuds(arbre):
    """Tous les noeuds de l'arbre (cours compris), dans l'ordre de lecture."""
    sortie = []

    def descendre(noeuds):
        for noeud in noeuds:
            sortie.append(noeud)
            descendre(noeud.get("enfants") or [])

    descendre(arbre.get("cours") or [])
    return sortie


def _differences_par_chemin(attendu, reel):
    """Phrases de `differences` pour chaque noeud reel, confronte au noeud de meme chemin de la fixture.

    `differences` prend pour modele le premier voisin de meme `type` (docstring de tests/formes_refonte.py), or
    `fixtures/arbre.json` porte des voisins de meme type et de formes differentes : un cours et une section sont
    tous deux `dossier`, un document traite et un document en echec sont tous deux `fichier`. Comparee telle
    quelle, la fixture rend des phrases meme pour un arbre juste (ecart E-R3-2 du journal). Le modele est donc
    choisi par chemin, seule facon de confronter la bonne forme a chaque noeud ; l'ordre, que la fixture ne suit
    pas, est prouve par son propre test (ecart E-R3-1).
    """
    modeles = {noeud["chemin"]: noeud for noeud in _noeuds(attendu)}
    sortie = differences({"racine": attendu.get("racine"), "compteurs": attendu.get("compteurs")},
                         {"racine": reel.get("racine"), "compteurs": reel.get("compteurs")}, "racine")
    for noeud in _noeuds(reel):
        modele = modeles.get(noeud["chemin"])
        if modele is None:
            sortie.append(f"{noeud['chemin']} : noeud absent de la fixture")
            continue
        sortie += differences(modele, noeud, noeud["chemin"])
    return sortie


def _etat_disque(dossier):
    """Instantane (taille, mtime) de tout ce que porte le dossier, cache compris."""
    vus = {}
    for racine, dossiers, fichiers in os.walk(dossier):
        for nom in dossiers + fichiers:
            chemin = os.path.join(racine, nom)
            st = os.stat(chemin)
            vus[os.path.relpath(chemin, dossier)] = (st.st_size, st.st_mtime_ns)
    return vus


class Base(unittest.TestCase):
    def setUp(self):
        self.dest = tempfile.mkdtemp(prefix="arbre-")

    def tearDown(self):
        shutil.rmtree(self.dest, ignore_errors=True)

    def fichier(self, chemin_rel, octets=64, contenu=None):
        chemin = os.path.join(self.dest, *chemin_rel.split("/"))
        dossier = os.path.dirname(chemin)
        if dossier:
            os.makedirs(dossier, exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(contenu if contenu is not None else b"x" * octets)
        return chemin

    def taille(self, chemin_rel):
        return os.path.getsize(os.path.join(self.dest, *chemin_rel.split("/")))

    def ecrire_json(self, nom, donnees):
        dossier = os.path.join(self.dest, ".moodlesync-ocr")
        os.makedirs(dossier, exist_ok=True)
        with open(os.path.join(dossier, nom), "w", encoding="utf-8") as f:
            json.dump(donnees, f)

    def cache(self, entrees):
        """Ecrit cache.json ; une entree sans `taille` recoit la taille reelle du fichier ecrit."""
        remplies = {}
        for cle, entree in entrees.items():
            entree = dict(entree)
            if "taille" not in entree:
                entree["taille"] = self.taille(cle)
            remplies[cle] = entree
        self.ecrire_json("cache.json", {"version": 1, "documents": remplies})

    def file(self, taches, etat="inactive"):
        self.ecrire_json("file.json", {"version": 1, "etat": etat, "portee": "coffre", "cree": "", "taches": taches})

    def etat_sync(self, documents):
        """`.moodlesync.json` du coffre (2.1) : `{"<cle>": {"chemin": ..., "genere": {...}}}`, un document par cle."""
        with open(os.path.join(self.dest, ms.ETAT), "w", encoding="utf-8") as f:
            json.dump(documents, f)


class FormeFixture(Base):
    """La forme de `ocr_arbre` est celle de `fixtures/arbre.json`, valeurs comprises."""

    def setUp(self):
        super().setUp()
        s3 = "Histoire contemporaine/Semaine 3"
        s4 = "Histoire contemporaine/Semaine 4"
        self.fichier(s3 + "/Studer 1996.pdf", 4096)
        self.fichier(s3 + "/Cours du 12 octobre.pdf", 2048)
        self.fichier(s3 + "/Annexe 1.pdf", 1024)
        self.fichier(s4 + "/Carte des alliances.pdf", 512)
        self.fichier(s4 + "/Lecture.pdf", 256)
        self.fichier("Droit constitutionnel/Plan du cours.pdf", 128)
        self.cache({
            s3 + "/Studer 1996.pdf": _entree(
                14, etat="ok", confiance=0.935, date="2026-11-10T14:31:53",
                sortie=s3 + "/Studer 1996.pdf.md", format="md", remplace=True,
                original={"fichier": "originaux/" + "a" * 64 + ".pdf", "empreinte": "sha256:" + "b" * 64, "taille": 4096},
                sortie_empreinte="sha256:" + "c" * 64),
            s3 + "/Cours du 12 octobre.pdf": _entree(
                9, etat="a_verifier", confiance=0.78, date="2026-11-10T14:40:02",
                sortie=s3 + "/Cours du 12 octobre.pdf.md", format="md", remplace=True,
                original={"fichier": "originaux/" + "d" * 64 + ".pdf", "empreinte": "sha256:" + "e" * 64, "taille": 2048},
                sortie_empreinte="sha256:" + "f" * 64),
            # Entree perimee : la taille ne correspond plus, le document redevient « Non traite » (2.3) mais
            # ses pages restent connues du cache (4.3).
            s3 + "/Annexe 1.pdf": _entree(
                18, etat="ok", taille=self.taille(s3 + "/Annexe 1.pdf") + 7, confiance=0.4,
                sortie=s3 + "/Annexe 1.pdf.md", format="md", remplace=True),
            s4 + "/Carte des alliances.pdf": _entree(
                13, etat="echec", motif="difficile", confiance=0.52, date="2026-11-10T14:55:10"),
            s4 + "/Lecture.pdf": _entree(
                6, etat="ok", date="2026-11-10T14:58:44", sortie=s4 + "/Lecture.pdf.txt",
                format="txt", remplace=False, original=None, sortie_empreinte="sha256:" + "9" * 64),
        })
        self.arbre = textes_arbre.construire_arbre(self.dest, CFG)

    def test_forme_egale_a_la_fixture(self):
        self.assertEqual(_differences_par_chemin(charger_fixture("arbre.json"), self.arbre), [])

    def test_racine_et_compteurs_racine(self):
        self.assertEqual(self.arbre["racine"], self.dest)
        self.assertEqual(self.arbre["compteurs"], charger_fixture("arbre.json")["compteurs"])

    def test_valeurs_de_chaque_noeud(self):
        modeles = {noeud["chemin"]: noeud for noeud in _noeuds(charger_fixture("arbre.json"))}
        noeuds = _noeuds(self.arbre)
        self.assertEqual(sorted(modeles), sorted(noeud["chemin"] for noeud in noeuds))
        for noeud in noeuds:
            attendu = modeles[noeud["chemin"]]
            self.assertEqual(noeud["nom"], attendu["nom"])
            if noeud["type"] == "dossier":
                self.assertEqual(noeud["compteurs"], attendu["compteurs"], noeud["chemin"])
                continue
            for cle in CLES_COMPAREES:
                self.assertEqual(noeud[cle], attendu[cle], f"{noeud['chemin']} : {cle}")
            self.assertEqual(noeud["octets"], self.taille(noeud["chemin"]))

    def test_aucun_chemin_absolu_dans_l_arbre(self):
        # Le compte d'abord : un arbre vide passerait la boucle sans rien prouver (mutation M5).
        self.assertEqual(len([noeud for noeud in _noeuds(self.arbre) if noeud["type"] == "fichier"]), 6)
        for chemin in _chemins(self.arbre):
            self.assertFalse(os.path.isabs(chemin), chemin)
            self.assertNotIn(self.dest, chemin)


class Statuts(Base):
    def setUp(self):
        super().setUp()
        for nom in ("a.pdf", "b.pdf", "c.pdf", "d.pdf", "e.pdf", "f.pdf", "g.pdf"):
            self.fichier("Cours A/" + nom, 100)
        self.cache({
            "Cours A/c.pdf": _entree(3, etat="ok", sortie="Cours A/c.pdf.md", format="md", remplace=True),
            "Cours A/d.pdf": _entree(4, etat="a_verifier", sortie="Cours A/d.pdf.md", format="md", confiance=0.8),
            "Cours A/e.pdf": _entree(5, etat="echec", motif="vide"),
            # Un echec garde son entree : une sortie ou un remplacement restes au cache ne s'affichent jamais.
            "Cours A/g.pdf": _entree(7, etat="echec", motif="verification", sortie="Cours A/g.pdf.md", format="md",
                                     remplace=True),
        })
        self.file([
            {"chemin": "Cours A/b.pdf", "etat": "attente", "pages": 2},
            {"chemin": "Cours A/f.pdf", "etat": "en_cours", "pages_faites": 1, "pages": 6},
        ])
        self.arbre = textes_arbre.construire_arbre(self.dest, CFG)

    def statut(self, chemin):
        return _noeud(self.arbre, "Cours A/" + chemin)["statut"]

    def test_les_six_statuts(self):
        self.assertEqual(self.statut("a.pdf"), "non_traite")
        self.assertEqual(self.statut("b.pdf"), "en_attente")
        self.assertEqual(self.statut("c.pdf"), "traite")
        self.assertEqual(self.statut("d.pdf"), "a_verifier")
        self.assertEqual(self.statut("e.pdf"), "echec")
        self.assertEqual(self.statut("f.pdf"), "en_cours")

    def test_tache_en_cours_lue_sur_le_disque(self):
        # `ocr.charger_file` ramene une tache `en_cours` a `attente` : l'arbre doit lire la file telle quelle (2.3).
        tache = {"chemin": "Cours A/f.pdf", "etat": "en_cours"}
        self.assertEqual(textes_arbre.statut_fichier(_entree(1, etat="ok"), tache), "en_cours")
        self.assertEqual(textes_arbre.statut_fichier(_entree(1, etat="ok"), {"chemin": "x", "etat": "attente"}),
                         "en_attente")

    def test_statut_fichier_sans_cache_ni_file(self):
        self.assertEqual(textes_arbre.statut_fichier(None, None), "non_traite")
        self.assertEqual(textes_arbre.statut_fichier({}, None), "non_traite")
        self.assertEqual(textes_arbre.statut_fichier({"etat": "difficile"}, None), "non_traite")

    def test_tache_faite_laisse_parler_le_cache(self):
        self.assertEqual(textes_arbre.statut_fichier(_entree(1, etat="ok"), {"chemin": "x", "etat": "fait"}), "traite")

    def test_echec_sans_texte_ni_sortie(self):
        noeud = _noeud(self.arbre, "Cours A/e.pdf")
        self.assertEqual(noeud["motif"], "vide")
        self.assertFalse(noeud["texte"])
        self.assertEqual(noeud["sortie"], "")
        self.assertEqual(noeud["format"], "")
        self.assertFalse(noeud["remplace"])
        self.assertFalse(noeud["original_conserve"])
        # Entree d'un echec qui porte encore une sortie et un remplacement : rien ne s'affiche.
        tardif = _noeud(self.arbre, "Cours A/g.pdf")
        self.assertEqual(tardif["motif"], "verification")
        self.assertFalse(tardif["texte"])
        self.assertEqual(tardif["sortie"], "")
        self.assertFalse(tardif["remplace"])

    def test_traite_donne_texte_sortie_et_original(self):
        noeud = _noeud(self.arbre, "Cours A/c.pdf")
        self.assertTrue(noeud["texte"])
        self.assertEqual(noeud["sortie"], "Cours A/c.pdf.md")
        self.assertEqual(noeud["format"], "md")
        self.assertTrue(noeud["remplace"])
        self.assertEqual(noeud["pages"], 3)
        self.assertEqual(noeud["date"], "2026-11-10T14:31:53")

    def test_confiance_absente_vaut_null(self):
        self.assertIsNone(_noeud(self.arbre, "Cours A/c.pdf")["confiance"])
        self.assertEqual(_noeud(self.arbre, "Cours A/d.pdf")["confiance"], 0.8)
        self.assertIsNone(_noeud(self.arbre, "Cours A/a.pdf")["confiance"])


class Remplace(Base):
    """E-V3-1 : un PDF remplace par sa version cherchable reste « Traite » (2.2, 2.3 et 4.3).

    Le disque porte le PDF cherchable, dont la taille est consignee dans `genere.taille_fichier` de
    `.moodlesync.json` ; le cache, lui, garde la taille de la source. L'arbre ne lit aucun PDF : il compare des
    tailles, celle du disque et celle du cache.
    """

    def setUp(self):
        super().setUp()
        self.fichier("Cours A/S1/remplace.pdf", 300)          # la version cherchable, plus grosse que la source
        self.fichier("Cours A/S1/autre.pdf", 300)             # meme taille sur le disque, jamais remplace
        self.cache({
            "Cours A/S1/remplace.pdf": _entree(
                4, etat="ok", sortie="Cours A/S1/remplace.pdf.md", format="md", remplace=True, taille=100,
                original={"fichier": "originaux/" + "a" * 64 + ".pdf", "empreinte": "sha256:" + "b" * 64,
                          "taille": 100}),
            "Cours A/S1/autre.pdf": _entree(4, etat="ok", sortie="Cours A/S1/autre.pdf.md", format="md",
                                           remplace=False, taille=200),
        })
        self.etat_sync({"url:1": {"chemin": "Cours A/S1/remplace.pdf", "genere": _genere(300, 100)}})
        self.arbre = textes_arbre.construire_arbre(self.dest, CFG)

    def statut(self, chemin, arbre=None):
        return _noeud(arbre or self.arbre, chemin)["statut"]

    def test_un_pdf_remplace_reste_traite(self):
        noeud = _noeud(self.arbre, "Cours A/S1/remplace.pdf")
        self.assertEqual(noeud["statut"], "traite")
        self.assertTrue(noeud["texte"])
        self.assertTrue(noeud["remplace"])
        self.assertTrue(noeud["original_conserve"])
        self.assertEqual(noeud["octets"], 300)
        # « Restaurer l'original » est propose quand `remplace` ou `texte` est vrai (textes-arbre.js, 5.3).
        self.assertTrue(noeud["remplace"] or noeud["texte"])

    def test_compteurs_du_pdf_remplace(self):
        # Seul « remplace.pdf » est a jour : « autre.pdf » a une entree perimee (200 au cache, 300 sur le disque).
        self.assertEqual(self.arbre["compteurs"],
                         {"fichiers": 2, "traites": 1, "a_verifier": 0, "echecs": 0, "non_traites": 1,
                          "pages_non_traitees": 4})
        self.assertEqual(_noeud(self.arbre, "Cours A/S1")["compteurs"], self.arbre["compteurs"])

    def test_pdf_remplace_puis_modifie_redevient_non_traite(self):
        """Une taille qui n'est ni celle de la source ni celle du fichier fabrique : le document a change."""
        self.fichier("Cours A/S1/remplace.pdf", 400)
        arbre = textes_arbre.construire_arbre(self.dest, CFG)
        noeud = _noeud(arbre, "Cours A/S1/remplace.pdf")
        self.assertEqual(noeud["statut"], "non_traite")
        self.assertFalse(noeud["texte"])
        self.assertFalse(noeud["remplace"])
        self.assertEqual((arbre["compteurs"]["traites"], arbre["compteurs"]["non_traites"]), (0, 2))

    def test_la_taille_du_pdf_cherchable_ne_vaut_que_pour_ce_document(self):
        """Deux documents de meme taille sur le disque : le `genere` de l'un ne blanchit pas l'autre."""
        self.assertEqual(self.statut("Cours A/S1/autre.pdf"), "non_traite")

    def test_sans_remplace_la_taille_du_cherchable_est_ignoree(self):
        """2.2 : seule une entree qui dit `remplace` accepte la taille du fichier fabrique."""
        self.etat_sync({"url:1": {"chemin": "Cours A/S1/autre.pdf", "genere": _genere(300, 200)}})
        arbre = textes_arbre.construire_arbre(self.dest, CFG)
        self.assertEqual(self.statut("Cours A/S1/autre.pdf", arbre), "non_traite")
        self.assertEqual(self.statut("Cours A/S1/remplace.pdf", arbre), "non_traite")   # son genere a disparu

    def test_un_genere_qui_n_est_pas_un_pdf_cherchable_est_ignore(self):
        genere = _genere(300, 100)
        del genere["type"]
        self.etat_sync({"url:1": {"chemin": "Cours A/S1/remplace.pdf", "genere": genere}})
        self.assertEqual(self.statut("Cours A/S1/remplace.pdf", textes_arbre.construire_arbre(self.dest, CFG)),
                         "non_traite")

    def test_entree_sans_taille_tenue_pour_a_jour(self):
        """2.2 : une entree sans `taille` (cache ecrit a la main) reste a jour, comme avant la correction."""
        self.ecrire_json("cache.json", {"version": 1, "documents": {
            "Cours A/S1/autre.pdf": {"empreinte": "sha256:" + "0" * 64, "etat": "ok",
                                     "sortie": "Cours A/S1/autre.pdf.md", "format": "md", "remplace": False}}})
        noeud = _noeud(textes_arbre.construire_arbre(self.dest, CFG), "Cours A/S1/autre.pdf")
        self.assertEqual(noeud["statut"], "traite")
        self.assertTrue(noeud["texte"])


class Compteurs(Base):
    def test_compteurs_de_chaque_dossier(self):
        self.fichier("A/s1/x.pdf", 10)
        self.fichier("A/s1/y.pdf", 10)
        self.fichier("A/s2/z.pdf", 10)
        self.fichier("A/w.pdf", 10)
        self.cache({
            "A/s1/x.pdf": _entree(7, etat="ok", sortie="A/s1/x.pdf.md"),
            "A/s1/y.pdf": _entree(3, etat="echec", motif="illisible"),
            "A/w.pdf": _entree(2, etat="a_verifier", sortie="A/w.pdf.md"),
        })
        arbre = textes_arbre.construire_arbre(self.dest, CFG)
        self.assertEqual(_noeud(arbre, "A/s1")["compteurs"],
                         {"fichiers": 2, "traites": 1, "a_verifier": 0, "echecs": 1, "non_traites": 0,
                          "pages_non_traitees": 3})
        self.assertEqual(_noeud(arbre, "A/s2")["compteurs"],
                         {"fichiers": 1, "traites": 0, "a_verifier": 0, "echecs": 0, "non_traites": 1,
                          "pages_non_traitees": 0})
        self.assertEqual(_noeud(arbre, "A")["compteurs"],
                         {"fichiers": 4, "traites": 1, "a_verifier": 1, "echecs": 1, "non_traites": 1,
                          "pages_non_traitees": 3})
        self.assertEqual(arbre["compteurs"], _noeud(arbre, "A")["compteurs"])

    def test_compteurs_sans_relire_le_disque(self):
        self.fichier("A/x.pdf", 10)
        arbre = textes_arbre.construire_arbre(self.dest, CFG)
        with mock.patch("moodlesync.textes_arbre.os.scandir", side_effect=AssertionError("disque relu")):
            self.assertEqual(textes_arbre.compteurs(arbre), arbre["compteurs"])

    def test_compteurs_d_un_arbre_vide(self):
        self.assertEqual(textes_arbre.compteurs({"racine": "", "cours": [], "compteurs": dict(ZEROS)}), ZEROS)
        self.assertEqual(textes_arbre.compteurs(None), ZEROS)


class Parcours(Base):
    def test_coffre_absent(self):
        arbre = textes_arbre.construire_arbre(os.path.join(self.dest, "absent"), CFG)
        self.assertEqual(arbre, {"racine": os.path.join(self.dest, "absent"), "cours": [],
                                 "compteurs": dict(ZEROS)})
        self.assertEqual(textes_arbre.construire_arbre("", CFG)["cours"], [])

    def test_eligible_ecarte_ce_qui_ne_se_traite_pas(self):
        self.fichier("Cours A/bon.pdf", 10)
        self.fichier("Cours A/notes.md", 10)
        self.fichier("Cours A/notes.pdf.txt", 10)
        self.fichier("Cours A/article.pdf (ancienne version 2026-11-01).pdf", 10)
        self.fichier(".moodlesync-ocr/cache.json", 10)
        self.fichier(".cache/bon.pdf", 10)
        self.fichier("Textes/Cours A/copie.pdf", 10)
        gros = self.fichier("Cours A/gros.pdf", 0)
        with open(gros, "wb") as f:
            f.truncate(300 * 1024 * 1024 + 1)
        self.fichier("Cours A/scan.png", 10)
        arbre = textes_arbre.construire_arbre(self.dest, CFG)
        noms = sorted(noeud["nom"] for noeud in self._fichiers(arbre))
        self.assertEqual(noms, ["bon.pdf", "scan.png"])

    def test_fichier_trop_gros_selon_le_reglage(self):
        self.fichier("Cours A/gros.pdf", 0)
        chemin = os.path.join(self.dest, "Cours A", "gros.pdf")
        with open(chemin, "wb") as f:
            f.truncate(1024 * 1024 + 1)
        self.fichier("Cours A/petit.pdf", 10)
        arbre = textes_arbre.construire_arbre(self.dest, {"ocr_max_mo": 1})
        self.assertEqual([n["nom"] for n in self._fichiers(arbre)], ["petit.pdf"])

    def test_dossier_sans_fichier_eligible_est_omis(self):
        self.fichier("Vide/notes.md", 10)
        self.fichier("Vide/sous/autre.txt", 10)
        self.fichier("Plein/x.pdf", 10)
        arbre = textes_arbre.construire_arbre(self.dest, CFG)
        self.assertEqual([c["nom"] for c in arbre["cours"]], ["Plein"])

    def test_ordre_dossiers_avant_fichiers_et_tri_par_cle_nom(self):
        for nom in ("Zeta.pdf", "alpha.pdf", "Béta.pdf"):
            self.fichier("Cours A/" + nom, 10)
        self.fichier("Cours A/Semaine 2/x.pdf", 10)
        self.fichier("Cours A/semaine 10/x.pdf", 10)
        arbre = textes_arbre.construire_arbre(self.dest, CFG)
        # ms.cle_nom compare les minuscules : « semaine 10 » passe avant « Semaine 2 ».
        self.assertEqual([e["nom"] for e in arbre["cours"][0]["enfants"]],
                         ["semaine 10", "Semaine 2", "alpha.pdf", "Béta.pdf", "Zeta.pdf"])

    def test_fichier_disparu_pendant_le_parcours_est_ignore(self):
        self.fichier("Cours A/x.pdf", 10)
        self.fichier("Cours A/y.pdf", 10)
        vrai = os.path.getsize

        def taille(chemin):
            if chemin.endswith("x.pdf"):
                raise OSError(2, "disparu")
            return vrai(chemin)

        with mock.patch("moodlesync.textes_arbre.os.path.getsize", side_effect=taille):
            arbre = textes_arbre.construire_arbre(self.dest, CFG)
        self.assertEqual([n["nom"] for n in self._fichiers(arbre)], ["y.pdf"])

    def _fichiers(self, arbre):
        sortie = []

        def descendre(noeuds):
            for noeud in noeuds:
                if noeud["type"] == "fichier":
                    sortie.append(noeud)
                descendre(noeud.get("enfants") or [])

        descendre(arbre.get("cours") or [])
        return sortie


class FichiersSous(Base):
    def setUp(self):
        super().setUp()
        self.fichier("Cours A/S1/a.pdf", 10)
        self.fichier("Cours A/S1/b.pdf", 10)
        self.fichier("Cours A/S2/c.pdf", 10)
        self.fichier("Droit/d.pdf", 10)

    def test_dossier_developpe_et_doublons_fusionnes(self):
        arbre = textes_arbre.construire_arbre(self.dest, CFG)
        noeuds = textes_arbre.fichiers_sous(self.dest, CFG, ["Cours A/S1", "Cours A/S1/a.pdf", "Cours A/S1"])
        self.assertEqual([n["chemin"] for n in noeuds], ["Cours A/S1/a.pdf", "Cours A/S1/b.pdf"])
        self.assertEqual(len(textes_arbre.fichiers_sous(self.dest, CFG, ["Cours A"])), 3)
        self.assertEqual([n["chemin"] for n in noeuds],
                         [c for c in _chemins(arbre) if c.startswith("Cours A/S1/")])

    def test_ordre_de_l_arbre_et_chemins_inconnus(self):
        noeuds = textes_arbre.fichiers_sous(self.dest, CFG, ["Droit", "Cours A", "Inconnu", "../dehors", ""])
        self.assertEqual([n["chemin"] for n in noeuds],
                         ["Cours A/S1/a.pdf", "Cours A/S1/b.pdf", "Cours A/S2/c.pdf", "Droit/d.pdf"])
        self.assertEqual(textes_arbre.fichiers_sous(self.dest, CFG, []), [])

    def test_fichier_non_eligible_demande_reste_dehors(self):
        self.fichier("Cours A/S1/notes.md", 10)
        self.assertEqual([n["chemin"] for n in textes_arbre.fichiers_sous(self.dest, CFG, ["Cours A/S1/notes.md"])],
                         [])


class LiensSortants(Base):
    """E-V3-3 : un lien symbolique ou une jonction qui sort du coffre n'est ni montre ni traite (4, invariant 8)."""

    def setUp(self):
        super().setUp()
        self.dehors = tempfile.mkdtemp(prefix="dehors-")
        self.addCleanup(shutil.rmtree, self.dehors, True)
        with open(os.path.join(self.dehors, "secret.pdf"), "wb") as f:
            f.write(b"x" * 10)
        self.fichier("Cours A/S1/vrai.pdf", 10)
        try:
            os.symlink(self.dehors, os.path.join(self.dest, "lien"))
            os.symlink(os.path.join(self.dehors, "secret.pdf"),
                       os.path.join(self.dest, "Cours A", "S1", "copie.pdf"))
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles")

    def test_l_arbre_ne_montre_pas_un_lien_sortant(self):
        arbre = textes_arbre.construire_arbre(self.dest, CFG)
        self.assertEqual(_chemins(arbre), ["Cours A", "Cours A/S1", "Cours A/S1/vrai.pdf"])
        self.assertEqual(arbre["compteurs"]["fichiers"], 1)

    def test_fichiers_sous_ne_rend_pas_un_lien_sortant(self):
        noeuds = textes_arbre.fichiers_sous(self.dest, CFG, ["lien", "Cours A"])
        self.assertEqual([n["chemin"] for n in noeuds], ["Cours A/S1/vrai.pdf"])

    def test_l_arbre_ne_parcourt_pas_un_dossier_sortant(self):
        """Le dossier hors du coffre n'est meme pas ouvert : ses noms ne sont pas lus (E-V3-3)."""
        vrai = os.scandir
        dehors = os.path.realpath(self.dehors)

        def scandir(chemin):
            if os.path.realpath(chemin) == dehors:
                raise AssertionError("l'arbre a parcouru un dossier hors du coffre")
            return vrai(chemin)

        with mock.patch("moodlesync.textes_arbre.os.scandir", side_effect=scandir):
            arbre = textes_arbre.construire_arbre(self.dest, CFG)
        self.assertEqual(_chemins(arbre), ["Cours A", "Cours A/S1", "Cours A/S1/vrai.pdf"])

    def test_un_lien_interne_reste_visible(self):
        """Le confinement suit `_ocr_confiner` : un lien qui reste dans le coffre n'est pas cache."""
        os.symlink(os.path.join(self.dest, "Cours A"), os.path.join(self.dest, "interne"))
        self.assertIn("interne/S1/vrai.pdf", _chemins(textes_arbre.construire_arbre(self.dest, CFG)))


class LectureSeule(Base):
    def test_aucun_fichier_cree_ni_modifie(self):
        self.fichier("Cours A/x.pdf", 10)
        self.cache({"Cours A/x.pdf": _entree(2, etat="ok", sortie="Cours A/x.pdf.md")})
        self.file([{"chemin": "Cours A/x.pdf", "etat": "attente"}])
        avant = _etat_disque(self.dest)
        textes_arbre.construire_arbre(self.dest, CFG)
        textes_arbre.fichiers_sous(self.dest, CFG, ["Cours A"])
        self.assertEqual(_etat_disque(self.dest), avant)

    def test_aucun_dossier_cache_cree(self):
        self.fichier("Cours A/x.pdf", 10)
        textes_arbre.construire_arbre(self.dest, CFG)
        self.assertFalse(os.path.exists(os.path.join(self.dest, ".moodlesync-ocr")))
        self.assertEqual(sorted(os.listdir(self.dest)), ["Cours A"])


class AucuneLectureDePdf(Base):
    """E-V3-4 : l'arbre ne lit aucun PDF (4.3). Toute ouverture d'un PDF fait echouer ces tests."""

    def setUp(self):
        super().setUp()
        self.fichier("Cours A/S1/article.pdf", 2048)
        self.fichier("Cours A/S1/scan.png", 32)
        self.cache({"Cours A/S1/article.pdf": _entree(12, etat="ok", sortie="Cours A/S1/article.pdf.md",
                                                     format="md", remplace=True)})

    def _sans_ouverture_de_pdf(self):
        """Doublure d'`open` (et de `io.open`, `os.open`) : ouvrir un PDF leve, au lieu de le lire.

        C'est la mutation A10 de la revue V3 : un parcours qui ouvre et lit chaque fichier doit se voir ici.
        """
        vrais = {"open": builtins.open, "io": io.open, "os": os.open}

        def refuser(nom):
            def ouvrir(chemin, *a, **k):
                if os.fspath(chemin).lower().endswith(".pdf"):
                    raise AssertionError(f"l'arbre a ouvert un PDF : {chemin}")
                return vrais[nom](chemin, *a, **k)
            return ouvrir

        return mock.patch("builtins.open", refuser("open")), mock.patch("io.open", refuser("io")), \
            mock.patch("os.open", refuser("os"))

    def test_l_arbre_n_ouvre_aucun_pdf(self):
        a, b, c = self._sans_ouverture_de_pdf()
        with a, b, c:
            with self.assertRaises(AssertionError):              # la doublure attrape bien une lecture de PDF
                open(os.path.join(self.dest, "Cours A", "S1", "article.pdf"), "rb")
            arbre = textes_arbre.construire_arbre(self.dest, CFG)
            noeuds = textes_arbre.fichiers_sous(self.dest, CFG, ["Cours A"])
        self.assertEqual(_noeud(arbre, "Cours A/S1/article.pdf")["pages"], 12)
        self.assertEqual([n["chemin"] for n in noeuds], ["Cours A/S1/article.pdf", "Cours A/S1/scan.png"])


class Performance(Base):
    def test_trois_mille_fichiers(self):
        documents = {}
        for cours in range(30):
            for section in range(5):
                dossier = f"Cours {cours:02d}/Section {section}"
                os.makedirs(os.path.join(self.dest, *dossier.split("/")), exist_ok=True)
                for n in range(20):
                    rel = f"{dossier}/doc {n}.pdf"
                    with open(os.path.join(self.dest, *rel.split("/")), "wb") as f:
                        f.write(b"x" * 32)
                    documents[rel] = _entree(n + 1, etat="ok", sortie=rel + ".md", format="md",
                                             taille=32, confiance=0.9)
        self.cache(documents)
        self.file([{"chemin": "Cours 00/Section 0/doc 0.pdf", "etat": "attente"}])
        debut = time.perf_counter()
        arbre = textes_arbre.construire_arbre(self.dest, CFG)
        duree = time.perf_counter() - debut
        print(f"\nR3 mesure : arbre de 3000 fichiers construit en {duree:.3f} s")
        self.assertEqual(arbre["compteurs"]["fichiers"], 3000)
        self.assertEqual(arbre["compteurs"]["traites"], 2999)
        self.assertEqual(len(arbre["cours"]), 30)
        self.assertLess(duree, 10.0)


class Api(Base):
    """`ocr_arbre` et `ocr_afficher` : confinement et commandes, `subprocess` double."""

    def setUp(self):
        super().setUp()
        self.fichier("Cours A/x.pdf", 10)
        self.fichier("Cours A/y.pdf", 10)
        self.cache({"Cours A/x.pdf": _entree(2, etat="ok", sortie="Cours A/x.pdf.md")})
        self.api = _FauxApi(self.dest)

    def test_ocr_arbre_rend_l_arbre_du_coffre(self):
        arbre = self.api.ocr_arbre()
        self.assertEqual(arbre["racine"], self.dest)
        self.assertEqual(arbre["compteurs"]["fichiers"], 2)
        # Chaque noeud fichier a la forme du noeud fichier non traite de la fixture.
        modele = next(noeud for noeud in _noeuds(charger_fixture("arbre.json"))
                      if noeud["chemin"].endswith("Plan du cours.pdf"))
        for noeud in _noeuds(arbre):
            if noeud["type"] == "fichier":
                self.assertEqual(differences(modele, noeud), [], noeud["chemin"])

    def test_ocr_arbre_d_une_config_sans_dest(self):
        self.assertEqual(_FauxApi("").ocr_arbre(), {"racine": "", "cours": [], "compteurs": dict(ZEROS)})

    def test_ocr_afficher_un_fichier(self):
        with mock.patch("moodlesync.api_arbre.subprocess.Popen") as popen:
            self.assertEqual(self.api.ocr_afficher("Cours A/x.pdf"), {"ok": True})
        commande, = popen.call_args.args
        self.assertEqual(commande, ["xdg-open", os.path.join(self.dest, "Cours A")])
        self.assertIs(popen.call_args.kwargs["shell"], False)

    def test_commandes_par_systeme(self):
        fichier = os.path.join(self.dest, "Cours A", "x.pdf")
        self.assertEqual(commande_afficher(fichier, "win32"), ["explorer", "/select," + fichier])
        self.assertEqual(commande_afficher(fichier, "darwin"), ["open", "-R", fichier])
        self.assertEqual(commande_afficher(fichier, "linux"), ["xdg-open", os.path.join(self.dest, "Cours A")])
        dossier = os.path.join(self.dest, "Cours A")
        self.assertEqual(commande_afficher(dossier, "win32"), ["explorer", dossier])
        self.assertEqual(commande_afficher(dossier, "darwin"), ["open", dossier])
        self.assertEqual(commande_afficher(dossier, "linux"), ["xdg-open", dossier])

    def test_ocr_afficher_un_dossier(self):
        with mock.patch("moodlesync.api_arbre.subprocess.Popen") as popen:
            self.assertEqual(self.api.ocr_afficher("Cours A"), {"ok": True})
        commande, = popen.call_args.args
        self.assertEqual(commande, ["xdg-open", os.path.join(self.dest, "Cours A")])

    def test_confinement(self):
        refuses = ("../dehors.pdf", "/etc/passwd", ".moodlesync-ocr/cache.json", "\x00x.pdf", "Cours A/../../x",
                   "", "Cours A/absent.pdf", "C:dehors.pdf")
        for chemin in refuses:
            with mock.patch("moodlesync.api_arbre.subprocess.Popen") as popen:
                self.assertEqual(self.api.ocr_afficher(chemin), {"erreur": ocr.MESSAGES["ouverture_refusee"]}, chemin)
                popen.assert_not_called()

    def test_lien_symbolique_sortant_refuse(self):
        dehors = tempfile.mkdtemp(prefix="dehors-")
        self.addCleanup(shutil.rmtree, dehors, True)
        cible = os.path.join(dehors, "secret.pdf")
        with open(cible, "wb") as f:
            f.write(b"x")
        os.symlink(cible, os.path.join(self.dest, "Cours A", "lien.pdf"))
        with mock.patch("moodlesync.api_arbre.subprocess.Popen") as popen:
            self.assertEqual(self.api.ocr_afficher("Cours A/lien.pdf"),
                             {"erreur": ocr.MESSAGES["ouverture_refusee"]})
            popen.assert_not_called()

    def test_echec_d_ouverture(self):
        with mock.patch("moodlesync.api_arbre.subprocess.Popen", side_effect=OSError(13, "refus")):
            self.assertEqual(self.api.ocr_afficher("Cours A/x.pdf"),
                             {"erreur": ocr.MESSAGES["ouverture_refusee"]})


class _FauxApi(ApiArbre):
    """Api sans fenetre : `_cfg` de `Api` (application.py) rend la configuration de la session."""

    def __init__(self, dest):
        self._dest = dest

    def _cfg(self):
        return {"dest": self._dest, "ocr_max_mo": 300, "ocr_format": "md"}


if __name__ == "__main__":
    unittest.main()
