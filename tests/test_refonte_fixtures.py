"""Garde des fixtures de la refonte de « Mes textes » (docs/refonte-textes/).

Verifie que les fixtures sont coherentes entre elles et avec le contrat : compteurs de l'arbre egaux aux sommes de
leurs enfants, valeurs de `statut` et de `motif` connues, comparateur de formes correct. Les documents de travail
vivent sur le depot prive : sur un clone public, ces tests s'ignorent.
"""
import os
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from tests.formes_refonte import charger_fixture, differences, fixtures_presentes

STATUTS = {"non_traite", "en_attente", "en_cours", "traite", "a_verifier", "echec"}
MOTIFS = {"", "difficile", "vide", "illisible", "verification", "ecriture", "erreur"}
CLES_COMPTEURS = {"fichiers", "traites", "a_verifier", "echecs", "non_traites", "pages_non_traitees"}
COMPTEUR_DU_STATUT = {"traite": "traites", "a_verifier": "a_verifier", "echec": "echecs", "non_traite": "non_traites"}


def somme(noeud):
    """Compteurs recalcules depuis les fichiers situes sous `noeud`."""
    total = dict.fromkeys(CLES_COMPTEURS, 0)
    pile = [noeud]
    while pile:
        n = pile.pop()
        if n["type"] == "dossier":
            pile.extend(n["enfants"])
            continue
        total["fichiers"] += 1
        cle = COMPTEUR_DU_STATUT.get(n["statut"])
        if cle:
            total[cle] += 1
        if n["statut"] in ("non_traite", "echec") and n["pages"] is not None:
            total["pages_non_traitees"] += n["pages"]
    return total


@unittest.skipUnless(fixtures_presentes(), "fixtures de la refonte absentes de ce clone (depot prive)")
class FixturesDeLaRefonte(unittest.TestCase):
    def test_compteurs_de_l_arbre_egaux_aux_sommes(self):
        arbre = charger_fixture("arbre.json")
        racine = {"type": "dossier", "enfants": arbre["cours"]}
        self.assertEqual(arbre["compteurs"], somme(racine))
        pile = list(arbre["cours"])
        while pile:
            n = pile.pop()
            if n["type"] == "dossier":
                with self.subTest(chemin=n["chemin"]):
                    self.assertEqual(n["compteurs"], somme(n))
                pile.extend(n["enfants"])

    def test_statuts_et_motifs_connus(self):
        pile = list(charger_fixture("arbre.json")["cours"])
        while pile:
            n = pile.pop()
            if n["type"] == "dossier":
                pile.extend(n["enfants"])
                continue
            with self.subTest(chemin=n["chemin"]):
                self.assertIn(n["statut"], STATUTS)
                self.assertIn(n["motif"], MOTIFS)
                self.assertEqual(bool(n["motif"]), n["statut"] == "echec")
                if n["statut"] == "echec" or n["statut"] == "non_traite":
                    self.assertFalse(n["texte"])
                    self.assertEqual(n["sortie"], "")
                else:
                    self.assertTrue(n["texte"])
                    self.assertTrue(n["sortie"].endswith("." + n["format"]))
                self.assertNotIn(":", n["chemin"], "un chemin de l'arbre est relatif, jamais absolu")

    def test_etat_porte_les_memes_compteurs_que_l_arbre(self):
        self.assertEqual(charger_fixture("etat.json")["compteurs"], charger_fixture("arbre.json")["compteurs"])

    def test_formes_retirees_absentes_de_l_etat(self):
        etat = charger_fixture("etat.json")
        for cle in ("active", "mode_pdf", "prevision"):
            self.assertNotIn(cle, etat)
        self.assertNotIn("ocr_apres_sync", etat["reglages"])
        self.assertIn(etat["reglages"]["ocr_format"], ("md", "txt"))

    def test_confirmation_et_depot(self):
        conf = charger_fixture("traiter_confirmation.json")
        self.assertEqual(set(conf), {"confirmer", "documents", "pages", "minutes", "remplacements"})
        self.assertEqual(len(conf["minutes"]), 2)
        depot = charger_fixture("depot.json")
        self.assertEqual(set(depot), {"confirmation", "depot"})
        for r in depot["depot"]["resultats"]:
            self.assertIn(r["statut"], ("ok", "a_verifier", "echec", "refuse"))
            if r["statut"] in ("echec", "refuse"):
                self.assertEqual((r["sortie_pdf"], r["sortie_texte"]), ("", ""))


class ComparateurDeFormes(unittest.TestCase):
    """Le comparateur sert aux tests de R3, R4 et R5 : il doit refuser un ecart, pas seulement tout accepter."""

    def test_formes_identiques(self):
        self.assertEqual(differences({"a": 1, "b": [{"type": "x", "c": "t"}]}, {"a": 2.5, "b": [{"type": "x", "c": "u"}]}), [])

    def test_cle_absente_ou_en_trop(self):
        d = differences({"a": 1, "b": 2}, {"a": 1, "c": 3})
        self.assertEqual(len(d), 2)
        self.assertTrue(any("b : cle absente" in x for x in d))
        self.assertTrue(any("c : cle en trop" in x for x in d))

    def test_booleen_n_est_pas_un_nombre(self):
        self.assertTrue(differences({"a": 1}, {"a": True}))

    def test_null_accepte_dans_les_deux_sens(self):
        self.assertEqual(differences({"a": 0.9}, {"a": None}), [])
        self.assertEqual(differences({"a": None}, {"a": 14}), [])

    def test_liste_choisit_le_modele_par_type(self):
        modele = {"l": [{"type": "dossier", "n": 1}, {"type": "fichier", "m": "x"}]}
        self.assertEqual(differences(modele, {"l": [{"type": "fichier", "m": "y"}, {"type": "dossier", "n": 2}]}), [])
        self.assertTrue(differences(modele, {"l": [{"type": "fichier", "n": 2}]}))

    def test_liste_vide_acceptee(self):
        self.assertEqual(differences({"l": [{"a": 1}]}, {"l": []}), [])


if __name__ == "__main__":
    unittest.main()
