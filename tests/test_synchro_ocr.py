#!/usr/bin/env python3
"""Tests de la tache Y1b : etat de synchronisation et `deja_present` (contrat 3.3, T10, T12, T13).

Aucun acces reseau : `urllib.request.urlopen` est remplace par un faux serveur qui compte les appels.
Cette machine n'a pas toujours de moteur de reconnaissance ni de rendu : les « PDF cherchables » sont fabriques
avec pypdf (la marque `/MoodleSyncGenere` ajoutee a /Info) et l'entree `genere` de 2.1 est ecrite a la main dans
`.moodlesync.json`. Aucun vrai remplacement de PDF n'est exerce ici.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t . -v
"""
import ast, hashlib, io, json, os, sys, tempfile, unittest
import urllib.request
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import marque, moteur as ms, ocr
from tests.test_ocr import MARQUE_VALIDE, NATIF, SCAN, json_compact, pdf_avec_info, pdf_minimal

URL = "https://moodle.exemple.ch/pluginfile.php/12/mod_resource/content/1/scan.pdf"
URL_AUTRE = "https://moodle.exemple.ch/pluginfile.php/13/mod_resource/content/1/scan.pdf"
T_MOODLE = 1760000000


def sha256(octets):
    return "sha256:" + hashlib.sha256(octets).hexdigest()


class FauxServeur:
    """Remplace urllib.request.urlopen : sert des octets par adresse sans parametres et compte les appels."""

    def __init__(self):
        self.contenus, self.appels = {}, []

    def __call__(self, requete, timeout=None):
        url = requete.full_url.split("?", 1)[0]
        self.appels.append(url)
        octets = self.contenus[url]

        class Entetes:
            def get_content_type(s):
                return "application/pdf"

            def get(s, nom, defaut=None):
                return str(len(octets)) if nom == "Content-Length" else defaut

        class Reponse:
            headers = Entetes()
            flux = io.BytesIO(octets)

            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def read(s, n=-1):
                return s.flux.read(n)
        return Reponse()


class Banc(unittest.TestCase):
    """Un coffre temporaire avec un cours, un faux serveur, des aides pour fabriquer et deplacer des PDF."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = os.path.join(self.tmp.name, "coffre")
        os.makedirs(self.dest)
        anciens = ms.CONFIG, ms.ERREURS
        ms.CONFIG = os.path.join(self.tmp.name, "config.json")
        ms.ERREURS = os.path.join(self.tmp.name, "erreurs.txt")
        self.addCleanup(lambda: setattr(ms, "CONFIG", anciens[0]) or setattr(ms, "ERREURS", anciens[1]))
        ms._MARQUES.clear()
        self.serveur = FauxServeur()
        patch = mock.patch.object(urllib.request, "urlopen", self.serveur)
        patch.start()
        self.addCleanup(patch.stop)
        self.source = pdf_minimal([SCAN])
        self.serveur.contenus[URL] = self.source
        self.cfg = {"dest": self.dest, "token": "x", "statuts": False}
        self.textes = []

    def item(self, url=URL, nom="scan.pdf", dossier="Cours A", section="Section 1", taille=None, t=T_MOODLE):
        return {"url": url + "?forcedownload=1", "nom": nom, "dossier": dossier, "section": section, "sous": "",
                "statut": "", "t": t, "taille": len(self.source) if taille is None else taille, "cid": 1,
                "sid": 10, "mime": "application/pdf"}

    def synchroniser(self, *items):
        self.textes = []
        return ms.telecharger(list(items), self.cfg, dire=lambda *a: None,
                              progres=lambda i, n, texte: self.textes.append(texte))

    def chemin(self, rel):
        return os.path.join(self.dest, *rel.split("/"))

    def ecrire(self, rel, octets):
        chemin = self.chemin(rel)
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(octets)
        return chemin

    def deplacer(self, de, vers):
        os.makedirs(os.path.dirname(self.chemin(vers)), exist_ok=True)
        os.replace(self.chemin(de), self.chemin(vers))

    def marque_pour(self, url=URL, source=None, **champs):
        source = self.source if source is None else source
        return dict(MARQUE_VALIDE, url=url, t=T_MOODLE, taille_source=len(source), empreinte_source=sha256(source),
                    pages=1, **champs)

    def cherchable(self, url=URL, source=None, avec_marque=True):
        """Octets d'un PDF « cherchable » : la marque de 2.2 dans /Info, une autre structure que la source."""
        info = {"/MoodleSyncGenere": json_compact(self.marque_pour(url, source))} if avec_marque else {"/Title": "x"}
        return pdf_avec_info([SCAN], info)

    def genere(self, octets, source=None):
        source = self.source if source is None else source
        return {"type": "pdf_cherchable", "taille_source": len(source), "empreinte_source": sha256(source),
                "taille_fichier": len(octets), "empreinte_fichier": sha256(octets), "pages": 1,
                "date": "2026-11-07T18:30:00", "version": 1}

    def remplacer(self, rel, url=URL):
        """Ce que ferait C4 apres une synchronisation : le PDF cherchable prend la place, `genere` entre dans l'etat."""
        octets = self.cherchable(url)
        self.ecrire(rel, octets)
        etat = ms.charger_etat(self.dest)
        etat[url]["genere"] = self.genere(octets)
        ms.sauver_etat(self.dest, etat)
        return octets

    def etat(self):
        return ms.charger_etat(self.dest)

    def index(self):
        return ms.index_existant(self.dest)

    def deja_present(self, it, cible, **kw):
        par_nom, par_taille = self.index()
        racine = os.path.normcase(os.path.join(self.dest, it["dossier"]))
        cours_de = ms.repartiteur(self.dest, [it])
        return ms.deja_present(it, cible, par_nom, lambda p: cours_de(p) == racine,
                               **dict({"etat": self.etat(), "dest": self.dest, "par_taille": par_taille}, **kw))

    def fichiers(self):
        return sorted(os.path.relpath(os.path.join(r, f), self.dest).replace(os.sep, "/")
                      for r, _, fs in os.walk(self.dest) for f in fs if not f.startswith("."))


REL = "Cours A/Section 1/scan.pdf"
REL_AILLEURS = "Cours A/Section 2/Mon cours renomme.pdf"


class SynchroApresRemplacement(Banc):
    def test_deja_present_sans_original(self):
        """T10 : apres un remplacement, une synchronisation ne telecharge rien et ecrit « PDF cherchable »."""
        self.assertEqual(self.synchroniser(self.item())["neufs"], 1)
        octets = self.remplacer(REL)
        self.assertEqual(self.serveur.appels, [URL])
        r = self.synchroniser(self.item())
        self.assertEqual(self.serveur.appels, [URL])                      # aucun appel a urlopen en plus
        self.assertEqual((r["neufs"], r["maj"], r["doublons"], r["erreurs"], r["generes"]), (0, 0, 0, 0, 1))
        self.assertEqual(len(self.textes), 1)
        self.assertIn("PDF cherchable", self.textes[0])
        self.assertNotIn("Déjà présent", self.textes[0])
        with open(self.chemin(REL), "rb") as f:
            self.assertEqual(f.read(), octets)                            # le PDF cherchable est intact
        self.assertEqual(self.fichiers(), [REL])                          # aucun « ancienne version »

    def test_deplace_renomme_retrouve(self):
        """T12 : retrouve par taille_fichier et empreinte_fichier, sans doublon, sans telechargement, genere conserve."""
        self.synchroniser(self.item())
        self.remplacer(REL)
        avant = self.etat()[URL]
        self.deplacer(REL, REL_AILLEURS)
        r = self.synchroniser(self.item())
        self.assertEqual(self.serveur.appels, [URL])
        self.assertEqual((r["neufs"], r["maj"], r["erreurs"], r["generes"], r["doublons"]), (0, 0, 0, 1, 0))
        self.assertEqual(self.fichiers(), [REL_AILLEURS])                 # pas de doublon a l'ancien chemin
        apres = self.etat()[URL]
        self.assertEqual(apres["chemin"], os.path.relpath(self.chemin(REL_AILLEURS), self.dest))
        self.assertEqual(apres["genere"], avant["genere"])                # genere conserve
        self.assertEqual(apres["t"], avant["t"])
        self.assertIn("PDF cherchable", self.textes[0])

    def test_pdf_cherchable_deplace_renomme(self):
        """T12, nom du contrat : le test minimum du plan d'execution, synchroniser, remplacer, synchroniser, deplacer, synchroniser."""
        self.synchroniser(self.item())
        self.remplacer(REL)
        self.synchroniser(self.item())
        self.deplacer(REL, REL_AILLEURS)
        self.synchroniser(self.item())
        self.synchroniser(self.item())
        self.assertEqual(self.serveur.appels, [URL])                      # un seul telechargement en tout
        self.assertEqual(self.fichiers(), [REL_AILLEURS])

    def test_deplace_sans_marque_dans_le_fichier(self):
        """L'etape 3 ne lit aucune marque : l'identite suffit, et ne lit pas non plus le PDF pour decider."""
        self.synchroniser(self.item())
        self.remplacer(REL)
        self.deplacer(REL, REL_AILLEURS)
        with mock.patch.object(ms, "lire_marque", wraps=marque.lire_marque) as lire:
            self.synchroniser(self.item())
        self.assertEqual((lire.call_count, self.serveur.appels), (0, [URL]))

    def test_fichier_modifie_apres_remplacement_retelecharge(self):
        """Un PDF cherchable deplace puis modifie n'a plus la meme identite et n'a plus de marque : doute, donc telechargement."""
        self.synchroniser(self.item())
        self.remplacer(REL)
        self.deplacer(REL, REL_AILLEURS)
        self.ecrire(REL_AILLEURS, pdf_minimal([NATIF]))                   # autre contenu, sans marque
        r = self.synchroniser(self.item())
        self.assertEqual(self.serveur.appels, [URL, URL])
        self.assertEqual(r["neufs"], 1)

    def test_lecture_d_empreinte_impossible_ne_fait_pas_echouer(self):
        self.synchroniser(self.item())
        self.remplacer(REL)
        self.deplacer(REL, REL_AILLEURS)
        with mock.patch.object(ms, "empreinte_entiere", return_value=""):
            with mock.patch.object(ms, "lire_marque", return_value=None):
                r = self.synchroniser(self.item())
        self.assertEqual(r["erreurs"], 0)
        self.assertEqual(self.serveur.appels, [URL, URL])                 # le doute se resout par telechargement


class PerteDEtat(Banc):
    def preparer(self, avec_marque=True):
        self.synchroniser(self.item())
        octets = self.cherchable(avec_marque=avec_marque)
        self.ecrire(REL, octets)
        os.remove(os.path.join(self.dest, ms.ETAT))
        self.deplacer(REL, REL_AILLEURS)
        return octets

    def test_perte_etat_marque(self):
        """T13, ecart 92 : .moodlesync.json supprime, la marque ne revendique plus le fichier, il est retelecharge."""
        octets = self.preparer()
        r = self.synchroniser(self.item())
        self.assertEqual(self.serveur.appels, [URL, URL])                 # retelecharge
        self.assertEqual((r["neufs"], r["doublons"], r["generes"], r["erreurs"]), (1, 0, 0, 0))
        entree = self.etat()[URL]
        self.assertEqual(sorted(entree), ["chemin", "t"])                 # aucun `genere` reconstruit
        self.assertEqual(entree["chemin"], os.path.relpath(self.chemin(REL), self.dest))
        self.assertNotIn("PDF cherchable", self.textes[0])                # message visible ordinaire
        with open(self.chemin(REL_AILLEURS), "rb") as f:                  # le PDF marque reste intact
            self.assertEqual(f.read(), octets)

    def test_t_est_celui_de_moodle(self):
        """La marque ne fixe plus `t` : l'entree retrouvee garde le `t` de l'etat, sinon celui que Moodle annonce."""
        p = self.ecrire(REL_AILLEURS, self.cherchable())
        entree = ms.entree_retrouvee(None, self.item(t=T_MOODLE + 500), p, self.dest)
        self.assertEqual((entree["t"], entree.get("genere")), (T_MOODLE + 500, None))
        connu = ms.entree_retrouvee({"t": T_MOODLE - 5, "chemin": "ancien"}, self.item(t=T_MOODLE + 500), p, self.dest)
        self.assertEqual((connu["t"], connu["chemin"], connu.get("genere")),
                         (T_MOODLE - 5, os.path.relpath(p, self.dest), None))

    def test_perte_etat_sans_marque(self):
        self.preparer(avec_marque=False)
        r = self.synchroniser(self.item())
        self.assertEqual(self.serveur.appels, [URL, URL])                 # retelecharge
        self.assertEqual((r["neufs"], r["generes"]), (1, 0))
        self.assertNotIn("genere", self.etat()[URL])

    def test_apres_retelechargement_plus_aucune_lecture(self):
        """L'etat ecrit par le telechargement suffit ensuite : la synchronisation suivante ne lit aucun PDF."""
        self.preparer()
        self.synchroniser(self.item())
        with mock.patch.object(ms, "lire_marque", wraps=marque.lire_marque) as lire:
            r = self.synchroniser(self.item())
        self.assertEqual((lire.call_count, r["generes"], r["doublons"], self.serveur.appels), (0, 0, 1, [URL, URL]))

    def test_marque_d_un_autre_document_ignoree(self):
        """Un PDF cherchable d'un autre document du cours n'est pas pris pour celui-ci."""
        self.synchroniser(self.item())
        self.ecrire(REL, self.cherchable(url=URL_AUTRE))
        os.remove(os.path.join(self.dest, ms.ETAT))
        self.deplacer(REL, REL_AILLEURS)
        r = self.synchroniser(self.item())
        self.assertEqual((r["neufs"], r["generes"], self.serveur.appels), (1, 0, [URL, URL]))

    def test_empreinte_illisible_apres_marque(self):
        """Marque lisible mais empreinte du fichier impossible : rien n'authentifie le fichier, il est retelecharge."""
        self.preparer()
        with mock.patch.object(ms, "empreinte_entiere", return_value=""):
            r = self.synchroniser(self.item())
        self.assertEqual((self.serveur.appels, r["neufs"], r["generes"], r["erreurs"]), ([URL, URL], 1, 0, 0))
        entree = self.etat()[URL]
        self.assertEqual((sorted(entree), entree["t"]), (["chemin", "t"], T_MOODLE))


class Ecart92(Banc):
    """Ecarts 91 et 92 : un PDF qu'on ne peut pas authentifier n'est plus revendique (contrat 3.3, section 4)."""

    def test_etat_perdu_pdf_marque_retelecharge(self):
        """Etat perdu : la marque ne revendique plus le fichier, il n'y a ni `genere` ni `generes`, et il est retelecharge."""
        octets = self.cherchable()
        self.ecrire(REL_AILLEURS, octets)
        r = self.synchroniser(self.item())
        self.assertEqual(self.serveur.appels, [URL])                      # retelecharge
        self.assertEqual((r["neufs"], r["doublons"], r["generes"], r["erreurs"]), (1, 0, 0, 0))
        entree = self.etat()[URL]
        self.assertEqual(sorted(entree), ["chemin", "t"])                 # aucun `genere`
        self.assertEqual(entree["chemin"], os.path.relpath(self.chemin(REL), self.dest))
        with open(self.chemin(REL_AILLEURS), "rb") as f:                  # le PDF marque n'est ni revendique ni ecrase
            self.assertEqual(f.read(), octets)
        self.assertEqual(self.fichiers(), sorted([REL, REL_AILLEURS]))

    def test_etat_perdu_pdf_marque_a_sa_place(self):
        """Etat perdu, PDF marque la ou MoodleSync l'attend : present, mais sans `genere` et hors du compte `generes`."""
        octets = self.cherchable()
        self.ecrire(REL, octets)
        r = self.synchroniser(self.item())
        self.assertEqual((self.serveur.appels, r["neufs"], r["doublons"], r["generes"]), ([], 0, 1, 0))
        self.assertEqual(sorted(self.etat()[URL]), ["chemin", "t"])
        with open(self.chemin(REL), "rb") as f:                           # jamais ecrase par la synchronisation
            self.assertEqual(f.read(), octets)

    def test_fichier_natif_n_herite_pas_du_genere(self):
        """Ecart 91 : un PDF natif de meme nom et de meme taille que Moodle n'herite pas du `genere` de l'ancienne entree."""
        self.synchroniser(self.item())
        self.remplacer(REL)                                               # PDF cherchable en place, `genere` dans l'etat
        os.remove(self.chemin(REL))
        natif = self.ecrire("Cours A/Section 2/scan.pdf", self.source)     # copie native de la source, meme nom, meme taille
        r = self.synchroniser(self.item())
        self.assertEqual(self.serveur.appels, [URL])                      # rien a retelecharger : le natif est present
        self.assertEqual((r["neufs"], r["doublons"], r["generes"], r["erreurs"]), (0, 1, 0, 0))
        entree = self.etat()[URL]
        self.assertEqual(sorted(entree), ["chemin", "t"])                 # il n'herite de rien
        self.assertEqual(entree["chemin"], os.path.relpath(natif, self.dest))

    def test_marque_d_un_autre_document_n_authentifie_pas(self):
        """Fichier present a l'emplacement attendu, marque d'un autre document, etat pointant ailleurs : aucun heritage."""
        self.ecrire(REL, self.cherchable(url=URL_AUTRE))
        ms.sauver_etat(self.dest, {URL: {"t": T_MOODLE, "chemin": "Cours A/Section 2/disparu.pdf",
                                        "genere": self.genere(self.cherchable())}})
        r = self.synchroniser(self.item())
        self.assertEqual((r["generes"], r["doublons"], self.serveur.appels), (0, 1, []))
        self.assertEqual(sorted(self.etat()[URL]), ["chemin", "t"])

    def test_etat_present_pdf_cherchable_deplace_reconnu(self):
        """Etat present : rien ne change, un PDF cherchable deplace reste reconnu et son `genere` intact (T12)."""
        self.synchroniser(self.item())
        octets = self.remplacer(REL)
        avant = self.etat()[URL]
        self.deplacer(REL, REL_AILLEURS)
        r = self.synchroniser(self.item())
        self.assertEqual((self.serveur.appels, r["generes"], r["doublons"], r["neufs"]), ([URL], 1, 0, 0))
        entree = self.etat()[URL]
        self.assertEqual(entree["genere"], avant["genere"])
        self.assertEqual(entree["chemin"], os.path.relpath(self.chemin(REL_AILLEURS), self.dest))
        with open(self.chemin(REL_AILLEURS), "rb") as f:
            self.assertEqual(f.read(), octets)

    def test_etat_present_pdf_modifie_deplace_retrouve_par_sa_marque(self):
        """Etat present : un PDF cherchable modifie et deplace est retrouve par sa marque, `genere` inchange, pour que
        `fabriquer_pdf_cherchable` reponde `modifie_main` (invariant 8)."""
        self.synchroniser(self.item())
        self.remplacer(REL)
        avant = self.etat()[URL]
        info = {"/MoodleSyncGenere": json_compact(self.marque_pour())}
        os.remove(self.chemin(REL))
        self.ecrire(REL_AILLEURS, pdf_avec_info([SCAN, NATIF], info))     # meme marque, autre identite
        r = self.synchroniser(self.item())
        self.assertEqual((self.serveur.appels, r["generes"], r["neufs"]), ([URL], 1, 0))
        self.assertEqual(self.etat()[URL]["genere"], avant["genere"])


class ArgumentsActuels(Banc):
    """`deja_present` avec les quatre arguments d'aujourd'hui rend exactement les resultats d'aujourd'hui."""

    def appel(self, it, cible, meme_cours=None):
        par_nom, _ = self.index()
        if meme_cours is None:
            return ms.deja_present(it, cible, par_nom)
        return ms.deja_present(it, cible, par_nom, meme_cours)

    def test_chemin_exact(self):
        p = self.ecrire(REL, b"x")
        self.assertEqual(self.appel(self.item(), p), p)

    def test_meme_nom_dans_le_dossier_sans_condition_de_taille(self):
        """Etape 5, branche « meme dossier » : la casse du nom ne compte pas, la taille annoncee non plus.

        Sur un systeme sensible a la casse (Linux), l'etape 5 rend le fichier ecrit sous son autre casse ; sur un
        systeme insensible a la casse (Windows), `cible` existe, donc l'etape 1 repond avant l'etape 5. Les deux
        reponses sont dans le meme dossier : c'est cela que l'assertion fixe, identiquement sur les deux systemes.
        """
        p = self.ecrire("Cours A/Section 1/Scan.PDF", b"abc")
        cible = os.path.join(self.dest, "Cours A", "Section 1", "scan.pdf")
        trouve = self.appel(self.item(taille=999), cible)
        self.assertIsNotNone(trouve)
        self.assertIn(trouve, (p, cible))                                 # la reponse est l'un des deux chemins du dossier
        self.assertEqual(os.path.normcase(os.path.dirname(trouve)), os.path.normcase(os.path.dirname(cible)))

    def test_meme_nom_ailleurs_avec_la_taille_annoncee(self):
        p = self.ecrire(REL_AILLEURS.replace("Mon cours renomme", "scan"), b"abcd")
        cible = self.chemin(REL)
        self.assertEqual(self.appel(self.item(taille=4), cible), p)
        self.assertIsNone(self.appel(self.item(taille=5), cible))
        self.assertIsNone(self.appel(self.item(taille=0), cible))

    def test_autre_cours_refuse(self):
        self.ecrire("Cours B/Section 1/scan.pdf", b"abcd")
        cible = self.chemin(REL)
        self.assertIsNone(self.appel(self.item(taille=4), cible, lambda p: False))

    def test_ni_lecture_ni_empreinte_sans_les_nouveaux_arguments(self):
        self.ecrire("Cours A/Section 2/scan.pdf", self.cherchable())
        with mock.patch.object(ms, "lire_marque", wraps=marque.lire_marque) as lire, \
                mock.patch.object(ms, "empreinte_entiere", wraps=ms.empreinte_entiere) as emp:
            self.assertIsNone(self.appel(self.item(nom="autre.pdf"), self.chemin("Cours A/Section 1/autre.pdf")))
        self.assertEqual((lire.call_count, emp.call_count), (0, 0))


class GenereIgnore(Banc):
    def test_genere_incomplet_ou_de_version_superieure(self):
        """2.1 : un `genere` incomplet ou de version superieure est ignore, le fichier est traite comme natif."""
        octets = self.cherchable(avec_marque=False)
        base = self.genere(octets)
        cas = {"version 2": dict(base, version=2), "sans empreinte": {k: v for k, v in base.items() if k != "empreinte_fichier"},
               "taille texte": dict(base, taille_fichier="12"), "mauvais type": dict(base, type="autre"),
               "pas un objet": "pdf", "empreinte vide": dict(base, empreinte_fichier="")}
        for nom, genere in cas.items():
            with self.subTest(nom):
                self.assertFalse(ms.genere_valide(genere))
                shutil_rel = "Cours A/Section 2/autre nom.pdf"
                self.ecrire(shutil_rel, octets)
                ms.sauver_etat(self.dest, {URL: {"t": T_MOODLE, "chemin": REL, "genere": genere}})
                self.assertIsNone(self.deja_present(self.item(), self.chemin(REL)))
                os.remove(self.chemin(shutil_rel))
        ms.sauver_etat(self.dest, {URL: {"t": T_MOODLE, "chemin": REL, "genere": base}})
        self.ecrire("Cours A/Section 2/autre nom.pdf", octets)
        self.assertEqual(self.deja_present(self.item(), self.chemin(REL)), self.chemin("Cours A/Section 2/autre nom.pdf"))

    def test_meme_regle_que_ocr(self):
        octets = self.cherchable(avec_marque=False)
        base = self.genere(octets)
        for genere in (base, dict(base, version=2), dict(base, version=True), dict(base, taille_source=True),
                       {k: v for k, v in base.items() if k != "taille_source"}, dict(base, empreinte_source=""),
                       {k: v for k, v in base.items() if k != "version"}, None, [], dict(base, type="x")):
            with self.subTest(genere=genere):
                self.assertEqual(ms.genere_valide(genere), ocr._genere_complet(genere) is not None)

    def test_genere_ignore_telecharge(self):
        self.synchroniser(self.item())
        octets = self.cherchable(avec_marque=False)
        self.ecrire(REL_AILLEURS, octets)
        os.remove(self.chemin(REL))
        etat = self.etat()
        etat[URL]["genere"] = dict(self.genere(octets), version=2)
        ms.sauver_etat(self.dest, etat)
        r = self.synchroniser(self.item())
        self.assertEqual((r["neufs"], r["generes"], self.serveur.appels), (1, 0, [URL, URL]))


class EtapeQuatre(Banc):
    def espion(self):
        return mock.patch.object(ms, "lire_marque", wraps=marque.lire_marque)

    def test_rien_lu_quand_les_etapes_un_a_trois_reussissent(self):
        octets = self.ecrire(REL, self.cherchable())
        self.ecrire("Cours A/Section 2/autre.pdf", self.cherchable(url=URL_AUTRE))
        ms.sauver_etat(self.dest, {URL: {"t": T_MOODLE, "chemin": REL}})
        with self.espion() as lire:
            self.assertEqual(self.deja_present(self.item(), self.chemin(REL)), self.chemin(REL))     # 1
            ms.sauver_etat(self.dest, {URL: {"t": T_MOODLE, "chemin": "Cours A/Section 2/autre.pdf"}})
            self.assertEqual(self.deja_present(self.item(), self.chemin("Cours A/Section 1/nulle.pdf")),
                             self.chemin("Cours A/Section 2/autre.pdf"))                                  # 2
            self.assertEqual(lire.call_count, 0)
        with open(octets, "rb") as f:
            contenu = f.read()
        self.deplacer(REL, REL_AILLEURS)
        ms.sauver_etat(self.dest, {URL: {"t": T_MOODLE, "chemin": REL, "genere": self.genere(contenu)}})
        with self.espion() as lire:
            self.assertEqual(self.deja_present(self.item(), self.chemin(REL)), self.chemin(REL_AILLEURS))  # 3
            self.assertEqual(lire.call_count, 0)

    def test_ne_lit_que_les_pdf_du_meme_cours_non_references(self):
        self.ecrire("Cours A/Section 1/reference.pdf", self.cherchable(url=URL_AUTRE))
        self.ecrire("Cours A/Section 1/libre.pdf", self.cherchable(url=URL_AUTRE + "x"))
        self.ecrire("Cours A/Section 1/notes.txt", b"pas un pdf")
        self.ecrire("Cours B/Section 1/etranger.pdf", self.cherchable(url=URL_AUTRE + "y"))
        ms.sauver_etat(self.dest, {URL: {"t": T_MOODLE, "chemin": "Cours A/Section 1/scan.pdf",
                                         "genere": self.genere(b"absent")},
                                   URL_AUTRE: {"t": 1, "chemin": "Cours A/Section 1/reference.pdf"}})
        with self.espion() as lire:
            self.assertIsNone(self.deja_present(self.item(), self.chemin(REL)))
        lus = sorted(os.path.basename(c.args[0]) for c in lire.call_args_list)
        self.assertEqual(lus, ["libre.pdf"])

    def test_pas_de_lecture_pour_un_fichier_moodle_qui_n_est_pas_un_pdf(self):
        self.ecrire("Cours A/Section 1/libre.pdf", self.cherchable())
        with self.espion() as lire:
            self.assertIsNone(self.deja_present(self.item(nom="cours.docx"), self.chemin("Cours A/Section 1/cours.docx")))
        self.assertEqual(lire.call_count, 0)

    def test_compare_l_url_sans_parametres(self):
        p = self.ecrire(REL_AILLEURS, self.cherchable(url=URL))
        ms.sauver_etat(self.dest, {URL: {"t": T_MOODLE, "chemin": "Cours A/Section 1/scan.pdf",
                                         "genere": self.genere(b"absent")}})
        it = self.item()
        self.assertTrue(it["url"].endswith("?forcedownload=1"))
        self.assertEqual(self.deja_present(it, self.chemin(REL)), p)
        self.ecrire(REL_AILLEURS, self.cherchable(url=URL_AUTRE))         # marque d'un autre document
        ms._MARQUES.clear()
        self.assertIsNone(self.deja_present(it, self.chemin("Cours A/Section 1/zzz.pdf")))

    def test_lecture_de_marque_qui_leve_ne_fait_pas_echouer(self):
        self.ecrire(REL_AILLEURS, self.cherchable())
        ms.sauver_etat(self.dest, {URL: {"t": T_MOODLE, "chemin": "Cours A/Section 1/scan.pdf",
                                         "genere": self.genere(b"absent")}})
        with mock.patch.object(ms, "lire_marque", side_effect=RuntimeError("boom")):
            self.assertIsNone(self.deja_present(self.item(), self.chemin(REL)))

    def test_chaque_pdf_lu_une_seule_fois_par_passage(self):
        """Plusieurs documents a retrouver dans le meme cours : la marque d'un PDF n'est lue qu'une fois."""
        for i in range(3):
            self.ecrire(f"Cours A/Section 2/f{i}.pdf", self.cherchable(url=URL_AUTRE + str(i)))
        ms.sauver_etat(self.dest, {URL + str(i + 10): {"t": T_MOODLE, "chemin": f"Cours A/Section 1/absent{i}.pdf",
                                                       "genere": self.genere(b"absent")} for i in range(3)})
        with self.espion() as lire:
            for i in range(3):
                self.assertIsNone(self.deja_present(self.item(url=URL + str(i + 10), nom=f"n{i}.pdf"),
                                                    self.chemin(f"Cours A/Section 1/n{i}.pdf")))
        self.assertEqual(lire.call_count, 3)


class EtapeCinq(Banc):
    """Invariant 14 : jamais de comparaison entre la taille d'un PDF cherchable et celle de Moodle."""

    def test_fichier_genere_connu_par_l_etat_n_est_pas_pris_pour_une_version(self):
        octets = self.cherchable(url=URL_AUTRE, avec_marque=False)
        self.ecrire("Cours A/Section 2/scan.pdf", octets)
        ms.sauver_etat(self.dest, {URL_AUTRE: {"t": 1, "chemin": "Cours A/Section 2/scan.pdf",
                                                 "genere": self.genere(octets)}})
        it = self.item(taille=len(octets))                  # Moodle annonce, par coincidence, la taille du fichier genere
        self.assertIsNone(self.deja_present(it, self.chemin(REL)))

    def test_fichier_genere_connu_par_sa_marque_n_est_pas_pris_pour_une_version(self):
        octets = self.cherchable(url=URL_AUTRE)
        self.ecrire("Cours A/Section 2/scan.pdf", octets)
        it = self.item(taille=len(octets))
        self.assertIsNone(self.deja_present(it, self.chemin(REL)))

    def test_fichier_natif_de_meme_nom_et_taille_toujours_pris(self):
        octets = pdf_minimal([NATIF])
        p = self.ecrire("Cours A/Section 2/scan.pdf", octets)
        it = self.item(taille=len(octets))
        self.assertEqual(self.deja_present(it, self.chemin(REL)), p)

    def test_taille_de_moodle_differente_du_pdf_cherchable_apres_synchro(self):
        """Le PDF cherchable est plus gros que la source : il n'est ni retelecharge ni renomme en « ancienne version »."""
        self.synchroniser(self.item())
        octets = self.remplacer(REL)
        self.assertNotEqual(len(octets), len(self.source))
        for _ in range(2):
            r = self.synchroniser(self.item())
            self.assertEqual((r["neufs"], r["maj"], r["generes"]), (0, 0, 1))
        self.assertEqual(self.fichiers(), [REL])


class DeuxCours(Banc):
    def test_autre_cours_refuse_par_identite(self):
        """Un PDF cherchable range dans un autre cours ne compte jamais : le meme document publie dans deux cours."""
        self.synchroniser(self.item())
        self.remplacer(REL)
        self.deplacer(REL, "Cours B/Section 1/scan.pdf")
        autre_cours = self.item(dossier="Cours A")
        racine = os.path.normcase(os.path.join(self.dest, "Cours A"))
        cours_de = ms.repartiteur(self.dest, [autre_cours, self.item(dossier="Cours B")])
        par_nom, par_taille = self.index()
        trouve = ms.deja_present(autre_cours, self.chemin(REL), par_nom, lambda p: cours_de(p) == racine,
                                 etat=self.etat(), dest=self.dest, par_taille=par_taille)
        self.assertIsNone(trouve)


class Structure(unittest.TestCase):
    def test_moteur_importe_lire_marque_de_marque(self):
        self.assertIs(ms.lire_marque, marque.lire_marque)
        self.assertIs(ms.lire_marque, ocr.lire_marque)

    def test_moteur_n_importe_ni_ocr_ni_autre_module_du_paquet(self):
        with open(os.path.join(RACINE, "moodlesync", "moteur.py"), encoding="utf-8") as f:
            arbre = ast.parse(f.read())
        internes = [(n.module, tuple(a.name for a in n.names), n.level) for n in ast.walk(arbre)
                    if isinstance(n, ast.ImportFrom) and (n.level or (n.module or "").startswith("moodlesync"))]
        internes += [(a.name, (), 0) for n in ast.walk(arbre) if isinstance(n, ast.Import)
                     for a in n.names if a.name.startswith("moodlesync")]
        # `from . import suivi` (dans semaine_auto) date d'avant Y1b ; la seule entree nouvelle est `marque`.
        self.assertEqual(sorted(internes, key=str), [("marque", ("lire_marque",), 1), (None, ("suivi",), 1)])
        self.assertNotIn("ocr", [m for m, _, _ in internes])

    def test_empreinte_entiere_comme_ocr(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "é à.bin")
            with open(chemin, "wb") as f:
                f.write(b"contenu" * 400000)                  # plus de 256 Ko : le SHA-1 du debut ne suffit pas
            self.assertEqual(ms.empreinte_entiere(chemin), ocr._sha256(chemin))
            self.assertEqual(ms.empreinte_entiere(chemin), ocr.identite(chemin)["empreinte"])
            self.assertEqual(ms.empreinte_entiere(chemin), sha256(b"contenu" * 400000))
            self.assertEqual(ms.empreinte_entiere(os.path.join(d, "nulle part")), "")
            self.assertEqual(ms.empreinte_entiere(d), "")     # un dossier : toujours une chaine vide, jamais d'exception


class MarqueEcart87(unittest.TestCase):
    """Ecart 87 : trois regles de `marque.lire_marque` qui doivent chacune faire echouer un test si elles sautent."""

    def lire(self, donnees, nom="m.pdf"):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, nom)
            with open(chemin, "wb") as f:
                f.write(pdf_avec_info([NATIF], {"/MoodleSyncGenere": json_compact(donnees)}))
            return marque.lire_marque(chemin)

    def test_valide(self):
        self.assertEqual(self.lire(MARQUE_VALIDE), MARQUE_VALIDE)

    def test_un_ko_et_plus(self):
        trop = dict(MARQUE_VALIDE, empreinte_source="x" * 1100)
        self.assertGreaterEqual(len(json_compact(trop).encode("utf-8")), 1024)
        self.assertIsNone(self.lire(trop))

    def test_pages_a_zero(self):
        self.assertIsNone(self.lire(dict(MARQUE_VALIDE, pages=0)))

    def test_booleen_refuse_comme_entier(self):
        self.assertIsNone(self.lire(dict(MARQUE_VALIDE, t=True)))
        self.assertIsNone(self.lire(dict(MARQUE_VALIDE, url=True)))
        self.assertIsNone(self.lire(dict(MARQUE_VALIDE, pages=True)))


class SynchronisationNative(Banc):
    """Y3 : ce que `telecharger` fait sur un coffre sans OCR, fige pour que Y2 ne le casse pas en silence.

    Contrat 3.3 : a la fin d'un passage complet, `neufs + maj + doublons + generes + erreurs == total` (hors
    annulation, que ces tests ne couvrent pas). Chaque test verifie les cles du compte rendu dont il a besoin,
    jamais le compte rendu entier : Y2 y ajoutera `a_preparer` et `republies_generes`. Aucun PDF cherchable
    fabrique par le moteur n'entre ici, le coffre reste natif.
    """

    def compte(self, r):
        return r["neufs"] + r["maj"] + r["doublons"] + r["generes"] + r["erreurs"]

    def partiels(self):
        return [f for _, _, fs in os.walk(self.dest) for f in fs if f.endswith(".part")]

    def test_nouveau_fichier(self):
        """Un item, rien sur le disque : telecharge une fois, range au chemin attendu, `t` et `chemin` sans `genere`."""
        r = self.synchroniser(self.item())
        self.assertEqual((r["neufs"], r["maj"], r["doublons"], r["generes"], r["erreurs"]), (1, 0, 0, 0, 0))
        self.assertEqual(self.compte(r), r["total"])
        self.assertEqual(self.serveur.appels, [URL])
        self.assertEqual(self.fichiers(), [REL])
        with open(self.chemin(REL), "rb") as f:
            self.assertEqual(f.read(), self.source)
        entree = self.etat()[URL]
        self.assertEqual(sorted(entree), ["chemin", "t"])                 # aucun `genere` : le fichier est natif
        self.assertEqual((entree["t"], entree["chemin"]), (T_MOODLE, os.path.relpath(self.chemin(REL), self.dest)))

    def test_deuxieme_passage_ne_telecharge_rien(self):
        """Fichier en place et etat a jour : `doublons` seul, et aucun appel au serveur de plus."""
        self.synchroniser(self.item())
        r = self.synchroniser(self.item())
        self.assertEqual((r["neufs"], r["maj"], r["doublons"], r["generes"], r["erreurs"]), (0, 0, 1, 0, 0))
        self.assertEqual(self.compte(r), r["total"])
        self.assertEqual(self.serveur.appels, [URL])
        self.assertEqual(self.fichiers(), [REL])

    def test_meme_nom_dans_une_autre_section_meme_taille(self):
        """Etape 5 : meme nom, meme taille que Moodle, dans une autre section du cours. Doublon, zero appel."""
        p = self.ecrire("Cours A/Section 2/scan.pdf", self.source)
        r = self.synchroniser(self.item())
        self.assertEqual((r["neufs"], r["maj"], r["doublons"], r["generes"], r["erreurs"]), (0, 0, 1, 0, 0))
        self.assertEqual(self.compte(r), r["total"])
        self.assertEqual(self.serveur.appels, [])
        self.assertEqual(self.fichiers(), ["Cours A/Section 2/scan.pdf"])
        entree = self.etat()[URL]
        self.assertEqual(sorted(entree), ["chemin", "t"])                 # l'etape 5 ne revendique pas un `genere`
        self.assertEqual(entree["chemin"], os.path.relpath(p, self.dest))
        self.assertFalse(os.path.exists(self.chemin(REL)))

    def test_meme_contenu_sous_un_autre_nom_dans_le_cours(self):
        """Bloc des jumeaux : le contenu est telecharge, reconnu identique, jete, et l'etat pointe vers l'autre nom."""
        p = self.ecrire("Cours A/Section 2/autre.pdf", self.source)
        r = self.synchroniser(self.item())
        self.assertEqual((r["neufs"], r["maj"], r["doublons"], r["generes"], r["erreurs"]), (0, 0, 1, 0, 0))
        self.assertEqual(self.compte(r), r["total"])
        self.assertEqual(self.serveur.appels, [URL])                      # un appel : le contenu a ete compare
        self.assertEqual(self.fichiers(), ["Cours A/Section 2/autre.pdf"])
        self.assertEqual(self.etat()[URL]["chemin"], os.path.relpath(p, self.dest))
        self.assertFalse(os.path.exists(self.chemin(REL)))

    def test_meme_document_publie_dans_deux_cours(self):
        """Le partage entre cours est voulu (docstring de `deja_present`) : une copie rangee dans chaque cours."""
        self.serveur.contenus[URL_AUTRE] = self.source
        r = self.synchroniser(self.item(), self.item(url=URL_AUTRE, dossier="Cours B"))
        self.assertEqual((r["neufs"], r["maj"], r["doublons"], r["generes"], r["erreurs"]), (2, 0, 0, 0, 0))
        self.assertEqual(self.compte(r), r["total"])
        self.assertEqual(sorted(self.serveur.appels), sorted([URL, URL_AUTRE]))
        self.assertEqual(self.fichiers(), ["Cours A/Section 1/scan.pdf", "Cours B/Section 1/scan.pdf"])
        etat = self.etat()
        self.assertEqual(etat[URL]["chemin"], os.path.relpath(self.chemin(REL), self.dest))
        self.assertEqual(etat[URL_AUTRE]["chemin"],
                         os.path.relpath(self.chemin("Cours B/Section 1/scan.pdf"), self.dest))

    def test_republication_contenu_different(self):
        """Republication : le nouveau contenu prend la place, l'ancien est renomme a cote par `nom_ancienne_version`."""
        self.synchroniser(self.item())
        local = self.chemin(REL)
        ancien = ms.nom_ancienne_version(local, T_MOODLE)                 # calcule avant, la fonction evite les noms pris
        nouveau = pdf_minimal([NATIF])
        self.serveur.contenus[URL] = nouveau
        r = self.synchroniser(self.item(t=T_MOODLE + 60))
        self.assertEqual((r["maj"], r["neufs"], r["doublons"], r["generes"], r["erreurs"]), (1, 0, 0, 0, 0))
        self.assertEqual(self.compte(r), r["total"])
        self.assertEqual(self.serveur.appels, [URL, URL])
        with open(local, "rb") as f:
            self.assertEqual(f.read(), nouveau)
        self.assertTrue(os.path.exists(ancien))                           # l'ancienne version est gardee a cote
        with open(ancien, "rb") as f:
            self.assertEqual(f.read(), self.source)
        self.assertEqual(self.fichiers(),
                         sorted([REL, os.path.relpath(ancien, self.dest).replace(os.sep, "/")]))
        entree = self.etat()[URL]
        self.assertEqual((entree["t"], entree["chemin"]), (T_MOODLE + 60, os.path.relpath(local, self.dest)))

    def test_date_changee_contenu_identique(self):
        """Moodle annonce une date plus recente, le contenu est le meme : doublon, `t` mis a jour, rien de renomme."""
        self.synchroniser(self.item())
        local = self.chemin(REL)
        ancienne = ms.nom_ancienne_version(local, T_MOODLE)
        r = self.synchroniser(self.item(t=T_MOODLE + 60))
        self.assertEqual((r["doublons"], r["maj"], r["neufs"], r["generes"], r["erreurs"]), (1, 0, 0, 0, 0))
        self.assertEqual(self.compte(r), r["total"])
        self.assertEqual(self.serveur.appels, [URL, URL])
        self.assertEqual(self.etat()[URL]["t"], T_MOODLE + 60)
        self.assertEqual(self.fichiers(), [REL])                          # aucune « ancienne version »
        self.assertFalse(os.path.exists(ancienne))
        self.assertEqual(self.partiels(), [])                             # le `.part` est efface
        with open(local, "rb") as f:
            self.assertEqual(f.read(), self.source)

    def test_erreur_sur_un_fichier(self):
        """Invariant 9 : une adresse inconnue compte une erreur, ne laisse aucun `.part`, et n'entre pas dans l'etat."""
        inconnue = "https://moodle.exemple.ch/pluginfile.php/99/mod_resource/content/1/perdu.pdf"
        r = self.synchroniser(self.item(url=inconnue, nom="perdu.pdf"), self.item())
        self.assertEqual((r["erreurs"], r["neufs"], r["maj"], r["doublons"], r["generes"]), (1, 1, 0, 0, 0))
        self.assertEqual(self.compte(r), r["total"])
        self.assertEqual(self.fichiers(), [REL])
        self.assertEqual(self.partiels(), [])
        etat = self.etat()
        self.assertNotIn(inconnue, etat)                                  # l'adresse en echec n'entre pas dans l'etat
        self.assertEqual([cle for cle in etat if not cle.startswith("_")], [URL])

    def test_marque_d_un_autre_document_a_l_etape_cinq(self):
        """Etape 5 et marque : un PDF qui porte une marque n'est jamais pris pour une version de ce document.

        Mesure du cas de l'ecart 93 : le fichier a le meme nom et la meme taille que Moodle, dans une autre section
        du cours, mais sa marque est celle d'un autre document. L'exclusion de l'invariant 14 s'applique, le fichier
        n'est pas retenu, il est telecharge au chemin attendu, et aucun `genere` n'entre dans l'etat.
        """
        octets = self.cherchable(url=URL_AUTRE)
        p = self.ecrire("Cours A/Section 2/scan.pdf", octets)
        r = self.synchroniser(self.item(taille=len(octets)))
        self.assertEqual((r["neufs"], r["doublons"], r["maj"], r["generes"], r["erreurs"]), (1, 0, 0, 0, 0))
        self.assertEqual(self.compte(r), r["total"])
        self.assertEqual(self.serveur.appels, [URL])
        entree = self.etat()[URL]
        self.assertEqual(sorted(entree), ["chemin", "t"])
        self.assertEqual(entree["chemin"], os.path.relpath(self.chemin(REL), self.dest))
        with open(p, "rb") as f:
            self.assertEqual(f.read(), octets)                            # le fichier d'un autre document reste intact

    def test_cours_nomme_textes(self):
        """Ecart 100, comportement a conserver : l'etape 1 retrouve un cours nomme « Textes » a son chemin exact.

        La perte de l'ecart 100 ne touche que les fichiers deplaces de ce cours : ce cas-la reste ouvert et n'est
        pas fige ici.
        """
        rel = "Textes/Section 1/scan.pdf"
        p = self.ecrire(rel, self.source)
        r = self.synchroniser(self.item(dossier="Textes"))
        self.assertEqual((r["neufs"], r["maj"], r["doublons"], r["generes"], r["erreurs"]), (0, 0, 1, 0, 0))
        self.assertEqual(self.compte(r), r["total"])
        self.assertEqual(self.serveur.appels, [])
        self.assertEqual(self.fichiers(), [rel])
        self.assertEqual(self.etat()[URL]["chemin"], os.path.relpath(p, self.dest))


if __name__ == "__main__":
    unittest.main()
