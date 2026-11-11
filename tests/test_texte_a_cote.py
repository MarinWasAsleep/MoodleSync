#!/usr/bin/env python3
"""Tests de R1b : le texte du document a cote de sa source, formats `md` et `txt` (contrat 2.1, 2.2, 3.4, 3.6).

Aucun document reel : les pages sont des dictionnaires de `extraire_page`, comme dans `tests/test_ocr.py`, et les
extractions passent par les doublures de `DocumentsC3` (moteur, reconnaissance, rendu). Aucune fenetre, aucun
`config.json`.

Ce que ces tests ne mesurent pas : ni Windows ni macOS (noms de fichiers reserves, lecteurs reseau), ni une vraie
reconnaissance (la suite de `tests/test_ocr.py` garde le moteur reel).

Lancer depuis la racine du depot : python -m unittest tests.test_texte_a_cote -v
"""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from moodlesync import moteur as ms, ocr
from tests.test_ocr import NATIF, SCAN, DocumentsC3

# PDF republie par Moodle : une page native de plus (E-V1-1), tout en texte pour ne pas demander le moteur.
PDF_PLUS_LONG = [NATIF, NATIF]

PAGES = [
    {"numero": 1, "source": "texte", "texte": "Le plan de Marshall.", "confiance": None, "mots": 4, "boites": None},
    {"numero": 2, "source": "ocr", "texte": "La relance reste fragile.", "confiance": 0.93, "mots": 4, "boites": None},
    {"numero": 3, "source": "vide", "texte": "", "confiance": None, "mots": 0, "boites": None},
]
REGLAGES = {"langues": "fra+eng", "moteur": "5.5.3"}

# Contenu exact du .txt de PAGES avec la page 4 illisible (3.4, O5) : une ligne `[p. n]`, une ligne vide, le
# texte, une ligne vide ; une page sans texte porte la phrase entre parentheses ; aucune balise, aucun en-tete.
TXT_GOLDEN = ("[p. 1]\n\nLe plan de Marshall.\n\n"
              "[p. 2]\n\nLa relance reste fragile.\n\n"
              "[p. 3]\n\n(aucun texte détecté)\n\n"
              "[p. 4]\n\n(aucun texte détecté)\n")


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return f.read()


def ecrire(chemin, contenu):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8", newline="\n") as f:
        f.write(contenu)


def empreinte(chemin):
    with open(chemin, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


class CheminTexte(unittest.TestCase):
    """Contrat 3.6 : `<dossier de la source>/<nom complet>.<format>`, `sortie` relatif avec `/`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = self.tmp.name

    def chemin(self, rel, **cfg):
        return ocr.chemin_texte(self.dest, rel, cfg)

    def test_document_a_la_racine_d_un_cours(self):
        absolu, sortie = self.chemin("Cours A/article.pdf")
        self.assertEqual(sortie, "Cours A/article.pdf.md")
        self.assertEqual(absolu, os.path.join(self.dest, "Cours A", "article.pdf.md"))

    def test_document_dans_une_section(self):
        absolu, sortie = self.chemin("Cours A/Semaine 3/article.pdf")
        self.assertEqual(sortie, "Cours A/Semaine 3/article.pdf.md")
        self.assertEqual(absolu, os.path.join(self.dest, "Cours A", "Semaine 3", "article.pdf.md"))

    def test_nom_a_espaces_et_a_accents(self):
        rel = "Histoire contemporaine/Semaine 3/Étude de cas n° 1.pdf"
        absolu, sortie = self.chemin(rel)
        self.assertEqual(sortie, "Histoire contemporaine/Semaine 3/Étude de cas n° 1.pdf.md")
        self.assertEqual(absolu, os.path.join(self.dest, *rel.split("/")) + ".md")
        self.assertNotIn("\\", sortie)

    def test_image(self):
        self.assertEqual(self.chemin("Cours A/scan.png")[1], "Cours A/scan.png.md")

    def test_format_txt(self):
        absolu, sortie = self.chemin("Cours A/article.pdf", ocr_format="txt")
        self.assertEqual(sortie, "Cours A/article.pdf.txt")
        self.assertEqual(absolu, os.path.join(self.dest, "Cours A", "article.pdf.txt"))

    def test_format_invalide_vaut_md(self):
        """`ocr_format` absent, vide, inconnu ou d'un autre type vaut `md` (contrat 3.6)."""
        for cfg in ({}, {"ocr_format": None}, {"ocr_format": ""}, {"ocr_format": "pdf"}, {"ocr_format": "MD"},
                    {"ocr_format": 5}, {"ocr_format": True}, {"ocr_format": ["txt"]}):
            with self.subTest(cfg=cfg):
                self.assertEqual(self.chemin("Cours A/article.pdf", **cfg)[1], "Cours A/article.pdf.md")

    def test_separateurs_du_systeme_dans_le_chemin_recu(self):
        """Un chemin recu avec des `\\` (forme du systeme) rend la meme `sortie`, en `/`."""
        self.assertEqual(self.chemin("Cours A\\Semaine 3\\article.pdf")[1], "Cours A/Semaine 3/article.pdf.md")


class FormatTxt(unittest.TestCase):
    """Contrat 3.4, O5 : texte seul, aucune balise, une page par bloc `[p. n]`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.chemin = os.path.join(self.tmp.name, "Cours A", "article.pdf.txt")

    def test_contenu_exact(self):
        self.assertTrue(ocr.ecrire_document_texte(self.chemin, "Cours A/article.pdf", PAGES, REGLAGES,
                                                  format="txt", illisibles=[4], date="2026-11-10T10:00:00"))
        texte = lire(self.chemin)
        self.assertEqual(texte, TXT_GOLDEN)
        for interdit in ("---", "<!--", "moodlesync:", "# ", "> ", "Pages à vérifier"):
            with self.subTest(interdit=interdit):
                self.assertNotIn(interdit, texte)
        self.assertNotIn("\r", texte)

    def test_utf8_sans_bom_et_fins_de_ligne_lf(self):
        ocr.ecrire_document_texte(self.chemin, "Cours A/article.pdf", PAGES, REGLAGES,
                                  format="txt", illisibles=[], date="")
        with open(self.chemin, "rb") as f:
            brut = f.read()
        self.assertFalse(brut.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", brut)
        self.assertIn("détecté".encode("utf-8"), brut)

    def test_aucun_fichier_temporaire(self):
        ocr.ecrire_document_texte(self.chemin, "Cours A/article.pdf", PAGES, REGLAGES,
                                  format="txt", illisibles=[], date="")
        self.assertEqual(os.listdir(os.path.dirname(self.chemin)), ["article.pdf.txt"])

    def test_page_sans_texte_garde_sa_ligne(self):
        """Une page sans texte porte `[p. n]` puis la phrase : plus de trace que dans un `.md` (3.4)."""
        ocr.ecrire_document_texte(self.chemin, "article.pdf", PAGES, REGLAGES, format="txt", illisibles=[], date="")
        texte = lire(self.chemin)
        self.assertIn("[p. 3]\n\n(aucun texte détecté)\n", texte)
        self.assertEqual(texte.count("(aucun texte détecté)"), 1)

    def test_le_md_est_inchange(self):
        """`format=\"md\"` passe par `ecrire_document_md` : sortie identique, octet pour octet."""
        md = self.chemin[:-4] + ".md"
        reference = os.path.join(self.tmp.name, "reference.md")
        self.assertTrue(ocr.ecrire_document_texte(md, "Cours A/article.pdf", PAGES, REGLAGES,
                                                  format="md", illisibles=[4], date="2026-11-10T10:00:00"))
        ocr.ecrire_document_md(reference, "Cours A/article.pdf", PAGES, REGLAGES, illisibles=[4],
                               date="2026-11-10T10:00:00")
        self.assertEqual(lire(md), lire(reference))
        self.assertIn("moodlesync:", lire(md))

    def test_protection_d_un_txt_edite(self):
        """O6 : un `.txt` dont l'empreinte differe de celle du cache n'est jamais reecrit (2.2)."""
        ocr.ecrire_document_texte(self.chemin, "article.pdf", PAGES, REGLAGES, format="txt", illisibles=[], date="")
        ecrit = lire(self.chemin)
        edite = ecrit + "Ma note a moi.\n"
        ecrire(self.chemin, edite)
        self.assertFalse(ocr.ecrire_document_texte(self.chemin, "article.pdf", PAGES, REGLAGES, format="txt",
                                                   illisibles=[], date="",
                                                   precedente={"format": "txt", "sortie_empreinte": "sha256:" + "0" * 64}))
        self.assertEqual(lire(self.chemin), edite)

    def test_txt_reecrit_quand_l_empreinte_correspond(self):
        ocr.ecrire_document_texte(self.chemin, "article.pdf", PAGES, REGLAGES, format="txt", illisibles=[], date="")
        self.assertTrue(ocr.ecrire_document_texte(self.chemin, "article.pdf", PAGES, REGLAGES, format="txt",
                                                  illisibles=[], date="",
                                                  precedente={"format": "txt", "sortie_empreinte": empreinte(self.chemin)}))

    def test_txt_existant_sans_empreinte_connue_est_conserve(self):
        """Sans entree de cache (cache perdu), un `.txt` present n'est pas ecrase : invariant 3."""
        ecrire(self.chemin, "Texte que je n'ai pas ecrit.\n")
        self.assertFalse(ocr.ecrire_document_texte(self.chemin, "article.pdf", PAGES, REGLAGES, format="txt",
                                                   illisibles=[], date=""))
        self.assertEqual(lire(self.chemin), "Texte que je n'ai pas ecrit.\n")

    def test_empreinte_par_format_fait_foi(self):
        """2.2 (R1c, revue V1) : `sortie_empreintes` fait foi, format par format ; a defaut, `sortie_empreinte`
        ne protege que le format qu'elle decrit. Un texte d'un autre format est tenu pour modifie (echec sur)."""
        ecrire(self.chemin, "Texte ecrit par MoodleSync.\n")
        deux = {"sortie_empreintes": {"md": "sha256:" + "1" * 64, "txt": empreinte(self.chemin)}}
        self.assertTrue(ocr.ecrire_document_texte(self.chemin, "article.pdf", PAGES, REGLAGES, format="txt",
                                                  illisibles=[], date="", precedente=deux),
                        "l'empreinte du format txt autorise la reecriture")
        # L'objet ne porte pas d'empreinte pour `txt` : le fichier present est tenu pour edite, meme quand
        # `sortie_empreinte` (celle du format `md`) correspond a son contenu.
        edite = lire(self.chemin) + "Ma note.\n"
        ecrire(self.chemin, edite)
        un_seul = {"format": "md", "sortie_empreintes": {"md": "sha256:" + "1" * 64},
                   "sortie_empreinte": empreinte(self.chemin)}
        self.assertFalse(ocr.ecrire_document_texte(self.chemin, "article.pdf", PAGES, REGLAGES, format="txt",
                                                   illisibles=[], date="", precedente=un_seul),
                         "`sortie_empreinte` d'un autre format ne vaut pas pour un `.txt`")
        self.assertEqual(lire(self.chemin), edite)
        # Repli d'une entree d'avant R1c : `sortie_empreinte` vaut quand elle decrit le format demande.
        ancienne = {"format": "txt", "sortie_empreinte": empreinte(self.chemin)}
        self.assertTrue(ocr.ecrire_document_texte(self.chemin, "article.pdf", PAGES, REGLAGES, format="txt",
                                                  illisibles=[], date="", precedente=ancienne),
                        "une entree sans `sortie_empreintes` garde sa protection")


class EcritureACote(DocumentsC3):
    """`extraire_document` ecrit le texte a cote de la source et l'inscrit au cache (2.2)."""

    def test_md_a_cote_et_entree_de_cache(self):
        rel = "Cours A/Section 1/scan.pdf"
        self.ranger(rel, [SCAN] * 2)
        avant = octets_pdf(os.path.join(self.dest, *rel.split("/")))
        entree = self.extraire_doc(rel)
        texte = os.path.join(self.dest, *rel.split("/")) + ".md"
        self.assertTrue(os.path.isfile(texte))
        self.assertEqual(entree["sortie"], "Cours A/Section 1/scan.pdf.md")
        self.assertEqual(entree["format"], "md")
        self.assertEqual(entree["sortie_empreinte"], empreinte(texte))
        self.assertFalse(os.path.exists(os.path.join(self.dest, "Textes")))
        self.assertEqual(octets_pdf(os.path.join(self.dest, *rel.split("/"))), avant)

    def test_txt_a_cote(self):
        rel = "Cours A/Section 1/scan.pdf"
        self.ranger(rel, [SCAN] * 2)
        entree = self.extraire_doc(rel, {"ocr_format": "txt"})
        texte = os.path.join(self.dest, *rel.split("/")) + ".txt"
        self.assertTrue(os.path.isfile(texte))
        self.assertEqual((entree["format"], entree["sortie"]), ("txt", "Cours A/Section 1/scan.pdf.txt"))
        self.assertEqual(entree["sortie_empreinte"], empreinte(texte))
        self.assertFalse(os.path.exists(os.path.join(self.dest, *rel.split("/")) + ".md"))
        self.assertIn("[p. 1]", lire(texte))

    def test_document_a_la_racine_et_nom_a_accents(self):
        rel = "Cours é/Semaine 3/Étude n° 1.pdf"
        self.ranger(rel, [SCAN])
        entree = self.extraire_doc(rel)
        self.assertEqual(entree["sortie"], "Cours é/Semaine 3/Étude n° 1.pdf.md")
        self.assertTrue(os.path.isfile(os.path.join(self.dest, *rel.split("/")) + ".md"))

    def test_entree_a_jour_suit_le_format_demande(self):
        """Changer de format refait le document et n'efface pas l'autre fichier (O5)."""
        rel = "scan.pdf"
        self.ranger(rel, [SCAN])
        entree = self.extraire_doc(rel)
        self.assertEqual(entree["format"], "md")
        del self.appels[:]
        self.assertEqual(self.extraire_doc(rel)["format"], "md")        # inchange : rien n'est refait
        self.assertEqual(self.appels, [])
        self.extraire_doc(rel, {"ocr_format": "txt"})
        self.assertTrue(self.appels)                                    # le format a change : refait
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "scan.pdf.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "scan.pdf.txt")))
        # Texte supprime a cote : refait.
        del self.appels[:]
        os.remove(os.path.join(self.dest, "scan.pdf.txt"))
        self.extraire_doc(rel, {"ocr_format": "txt"})
        self.assertTrue(self.appels)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "scan.pdf.txt")))

    def test_format_invalide_dans_la_configuration(self):
        rel = "scan.pdf"
        self.ranger(rel, [SCAN])
        entree = self.extraire_doc(rel, {"ocr_format": "odt"})
        self.assertEqual((entree["format"], entree["sortie"]), ("md", "scan.pdf.md"))

    def test_txt_edite_conserve_et_empreinte_gardee(self):
        """O6 : un `.txt` modifie a la main n'est pas reecrit ; le cache garde l'empreinte du fichier ecrit."""
        rel = "scan.pdf"
        self.ranger(rel, [SCAN])
        entree = self.extraire_doc(rel, {"ocr_format": "txt"})
        chemin = os.path.join(self.dest, "scan.pdf.txt")
        gardee = entree["sortie_empreinte"]
        ecrire(chemin, lire(chemin) + "Ma note.\n")
        apres = self.extraire_doc(rel, {"ocr_format": "txt"})
        self.assertIn("Ma note.", lire(chemin))
        self.assertEqual(apres["sortie_empreinte"], gardee)

    def test_ancienne_version_renommee_a_cote_en_txt(self):
        rel = "Cours A/article.pdf"
        self.ranger(rel, [NATIF])
        self.extraire_doc(rel, {"ocr_format": "txt"})
        ancien = os.path.join(self.dest, "Cours A", "article.pdf.txt")
        self.assertTrue(os.path.isfile(ancien))
        nouveau = ocr.archiver_texte(self.dest, rel, 1760000000)
        self.assertTrue(os.path.isabs(nouveau))
        self.assertFalse(os.path.exists(ancien))
        nom = os.path.basename(nouveau)
        self.assertTrue(nom.startswith("article.pdf (" + ms.T["ancienne"] + " ") and nom.endswith(").txt"), nom)
        self.assertEqual(os.path.dirname(nouveau), os.path.dirname(ancien))
        self.assertIsNone(ocr.archiver_texte(self.dest, rel, 1760000000))

    def test_ancienne_version_renommee_a_cote_en_md(self):
        rel = "Cours A/article.pdf"
        self.ranger(rel, [NATIF])
        self.extraire_doc(rel)
        ancien = os.path.join(self.dest, "Cours A", "article.pdf.md")
        nouveau = ocr.archiver_texte(self.dest, rel, 1760000000)
        self.assertTrue(os.path.basename(nouveau).endswith(").md"))
        self.assertFalse(os.path.exists(ancien))
        self.assertEqual(os.path.dirname(nouveau), os.path.dirname(ancien))

    def test_txt_edite_n_est_pas_archive(self):
        """Un `.txt` edite a la main n'est pas renomme : il n'est pas un texte que MoodleSync peut remplacer."""
        rel = "article.pdf"
        self.ranger(rel, [NATIF])
        self.extraire_doc(rel, {"ocr_format": "txt"})
        chemin = os.path.join(self.dest, "article.pdf.txt")
        ecrire(chemin, "Mon texte a moi.\n")
        self.assertIsNone(ocr.archiver_texte(self.dest, rel, 1760000000))
        self.assertEqual(lire(chemin), "Mon texte a moi.\n")


class CycleDeFormat(DocumentsC3):
    """E-V1-1 et E-V1-4 (revue V1) : une empreinte de texte par format dans le cache (2.2), et l'archivage des deux
    textes quand Moodle republie un PDF (7.1). Le traitement passe par `traiter_document`, le chemin de production."""

    REL = "Cours A/article.pdf"

    def traiter(self, cfg=None, **kw):
        """Entree de cache ecrite par `traiter_document` (3.1 : la forme `{"entree", ...}` est depaquee)."""
        return self.avec(ocr.traiter_document, self.dest, self.REL, cfg if cfg is not None else {}, **kw)["entree"]

    def texte(self, format):
        return os.path.join(self.dest, *self.REL.split("/")) + "." + format

    def anciennes_versions(self):
        dossier = os.path.dirname(self.texte("md"))
        return sorted(n for n in os.listdir(dossier) if "(" + ms.T["ancienne"] + " " in n)

    def test_cycle_md_txt_md_txt_rend_le_txt_a_jour(self):
        """Un `.txt` ecrit par MoodleSync n'est pas pris pour un texte edite au retour du format `txt` : le PDF a
        change entre-temps, le `.txt` doit suivre (E-V1-1)."""
        self.ranger(self.REL, [NATIF])
        self.traiter()                                            # 1. md
        self.traiter({"ocr_format": "txt"})                        # 2. txt
        self.assertIn("[p. 1]", lire(self.texte("txt")))
        self.assertNotIn("[p. 2]", lire(self.texte("txt")))
        self.ranger(self.REL, PDF_PLUS_LONG)                       # Moodle republie un PDF plus long
        self.traiter()                                             # 3. md
        entree = self.traiter({"ocr_format": "txt"})               # 4. txt, a remettre a jour
        texte = lire(self.texte("txt"))
        self.assertIn("[p. 2]", texte, "le `.txt` est reste perime (E-V1-1)")
        self.assertIn("Le plan de Marshall", texte)
        self.assertEqual((entree["format"], entree["sortie"]), ("txt", self.REL + ".txt"))
        self.assertEqual(entree["sortie_empreinte"], empreinte(self.texte("txt")))

    def test_une_empreinte_par_format_au_cache(self):
        """2.2 : `sortie_empreintes` porte l'empreinte du texte ecrit dans chaque format, `sortie_empreinte` celle
        du format courant. Changer de format n'efface pas celle de l'autre (O5)."""
        self.ranger(self.REL, [NATIF])
        premiere = self.traiter()
        self.assertEqual(premiere["sortie_empreintes"], {"md": empreinte(self.texte("md"))})
        self.assertEqual(premiere["sortie_empreinte"], empreinte(self.texte("md")))
        entree = self.traiter({"ocr_format": "txt"})
        self.assertEqual(entree["sortie_empreintes"], {"md": empreinte(self.texte("md")),
                                                       "txt": empreinte(self.texte("txt"))})
        self.assertEqual(entree["sortie_empreinte"], empreinte(self.texte("txt")))
        self.assertEqual(entree["format"], "txt")

    def test_entree_de_cache_perdue_ne_reecrit_pas_le_txt(self):
        """Decision R1c : sans entree de cache, rien ne prouve qu'un `.txt` a ete ecrit par MoodleSync (O5 interdit
        une marque dans le texte). Le fichier est tenu pour edite et laisse intact : echec sur, invariant 3."""
        self.ranger(self.REL, [NATIF])
        self.traiter({"ocr_format": "txt"})
        chemin = self.texte("txt")
        ecrit = lire(chemin)
        shutil.rmtree(os.path.join(self.dest, ocr.CACHE))
        self.ranger(self.REL, PDF_PLUS_LONG)
        entree = self.traiter({"ocr_format": "txt"})
        self.assertEqual(lire(chemin), ecrit, "un `.txt` sans empreinte connue n'est jamais ecrase")
        self.assertEqual((entree["sortie_empreinte"], entree["sortie_empreintes"]), ("", {}))

    def test_archiver_texte_renomme_les_deux_formats(self):
        """E-V1-4 : quand Moodle republie un PDF, les textes des deux formats passent en « ancienne version »."""
        self.ranger(self.REL, [NATIF])
        self.traiter({"ocr_format": "txt"})
        self.traiter()                                             # le cache decrit le `.md`, le `.txt` reste a cote
        self.assertTrue(os.path.isfile(self.texte("md")))
        self.assertTrue(os.path.isfile(self.texte("txt")))
        nouveau = ocr.archiver_texte(self.dest, self.REL, 1760000000)
        self.assertTrue(str(nouveau).endswith(").md"), nouveau)
        self.assertFalse(os.path.exists(self.texte("md")))
        self.assertFalse(os.path.exists(self.texte("txt")), "le texte de l'autre format est reste sous son nom")
        self.assertEqual(sorted(os.path.splitext(n)[1] for n in self.anciennes_versions()), [".md", ".txt"])
        self.assertIsNone(ocr.archiver_texte(self.dest, self.REL, 1760000000))

    def test_archiver_texte_laisse_un_txt_edite_a_la_main(self):
        """Invariant 3 : un `.txt` edite n'est ni reecrit ni renomme, meme quand le `.md` part en ancienne version."""
        self.ranger(self.REL, [NATIF])
        self.traiter({"ocr_format": "txt"})
        self.traiter()
        ecrire(self.texte("txt"), "Ma note a moi.\n")
        nouveau = ocr.archiver_texte(self.dest, self.REL, 1760000000)
        self.assertTrue(str(nouveau).endswith(").md"), nouveau)
        self.assertEqual(lire(self.texte("txt")), "Ma note a moi.\n")
        self.assertEqual([os.path.splitext(n)[1] for n in self.anciennes_versions()], [".md"])


def octets_pdf(chemin):
    with open(chemin, "rb") as f:
        return f.read()


# ------------------------------------------------------------------ eligibilite
class Eligibilite(DocumentsC3):
    """O11 et 3.5 : un `Textes/` pose directement dans dest reste exclu, celui d'un cours est un dossier ordinaire."""

    def test_textes_a_la_racine_exclu(self):
        self.ranger("Textes/Cours A/ancien.pdf", [SCAN])
        self.assertIsNone(ocr._eligible(self.dest, {}, "Textes/Cours A/ancien.pdf"))

    def test_textes_dans_un_cours_garde(self):
        rel = "Cours A/Section 1/Textes/sous.pdf"
        self.ranger(rel, [SCAN])
        self.assertEqual(ocr._eligible(self.dest, {}, rel), os.path.join(self.dest, *rel.split("/")))

    def test_textes_ecrit_dans_une_autre_casse_exclu(self):
        self.ranger("textes/Cours A/ancien.pdf", [SCAN])
        self.assertIsNone(ocr._eligible(self.dest, {}, "textes/Cours A/ancien.pdf"))

    def test_un_texte_a_cote_n_est_jamais_eligible(self):
        """O11 : un `.md` ou un `.txt` a cote d'un PDF n'entre ni dans l'arbre ni dans la file."""
        for nom in ("Cours A/article.pdf.md", "Cours A/article.pdf.txt", "Cours A/article.pdf (ancienne version 2026-01-01).md"):
            self.ranger(nom, [SCAN])
            with self.subTest(nom=nom):
                self.assertIsNone(ocr._eligible(self.dest, {}, nom))

    def test_nom_du_dossier_de_sortie_retire(self):
        """`ocr_dossier` ne designe plus rien : 3.5 retire `_nom_dossier_sortie`."""
        for nom in ("_nom_dossier_sortie", "_chemin_sortie", "_dossier_textes", "_dossiers_sortie"):
            with self.subTest(nom=nom):
                self.assertFalse(hasattr(ocr, nom), "%s devait disparaitre (contrat 3.5)" % nom)

    def test_le_decorateur_sans_trace_est_retire(self):
        """E-V1-8 : `_sans_trace` n'avait plus aucun appelant depuis R1a ; 3.5 retire les aides sans appelant."""
        self.assertFalse(hasattr(ocr, "_sans_trace"))


if __name__ == "__main__":
    unittest.main()
