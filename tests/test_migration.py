"""Migration de l'ancien dossier « Textes/ » (tache R6, contrat 8 de docs/refonte-textes/contrat.md).

Aucune fenetre, aucun PDF reel : un coffre d'ancienne disposition est construit dans un dossier
temporaire (documents, `Textes/`, `index.md`, `Qualité des textes.md`, fichier de cours, `.jsonl`,
`.md` edite, `.md` « Difficile », `.md` orphelin), puis migre. Chaque test mesure l'arbre entier par
une empreinte, pour prouver l'idempotence et qu'aucun PDF n'est touche.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moodlesync import application as app, moteur as ms, ocr, textes_migration

FRONT_MATTER = "---\nsource: {source}\nmoodlesync: {{\"version\": 1}}\n---\n\nTexte du document.\n"
EDITE = "Mon texte, corrige a la main.\n"
# Fichiers de synthese de l'ancienne version : `ms.MARQUE` en premiere ligne, comme les ecrivait `ocr.py` avant R1a.
AGREGE = ms.MARQUE + "\n\n# Titre\n\nUne ligne.\n"
# Export `.jsonl` de l'ancienne version : une ligne JSON par page, sans marque (plan 6.4). Sa signature est la
# forme de ses lignes, que `_genere` reconnait (E-V4-7).
EXPORT = json.dumps({"cours": "Cours A", "section": "S1", "fichier": "article.pdf", "page": 1,
                     "source": "ocr", "confiance": None, "texte": "Texte du document."},
                    ensure_ascii=False) + "\n"


def empreinte(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def empreinte_arbre(racine):
    """Empreinte de tout l'arbre : chemins relatifs, tailles et contenus, dossiers compris."""
    lignes = []
    for dossier, sous_dossiers, fichiers in os.walk(racine):
        sous_dossiers.sort()
        rel = os.path.relpath(dossier, racine)
        lignes.append("D " + rel.replace(os.sep, "/"))
        for nom in sorted(fichiers):
            chemin = os.path.join(dossier, nom)
            lignes.append("F %s/%s %s" % (rel.replace(os.sep, "/"), nom, empreinte(chemin)))
    return hashlib.sha256("\n".join(sorted(lignes)).encode("utf-8")).hexdigest()


def empreintes_pdf(racine):
    return {os.path.relpath(os.path.join(d, n), racine).replace(os.sep, "/"): empreinte(os.path.join(d, n))
            for d, _, fichiers in os.walk(racine) for n in fichiers if n.lower().endswith(".pdf")}


class CoffreAncien(unittest.TestCase):
    """Un coffre d'ancienne disposition, construit en test, dans un dossier temporaire."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.dest = os.path.join(self.d, "coffre")
        os.makedirs(self.dest)
        self.sauve = (ms.APP_DIR, ms.CONFIG)
        ms.APP_DIR, ms.CONFIG = self.d, os.path.join(self.d, "config.json")

    def tearDown(self):
        ms.APP_DIR, ms.CONFIG = self.sauve
        self.tmp.cleanup()

    # -- outils
    def ecrire(self, rel, contenu):
        chemin = os.path.join(self.dest, *rel.split("/"))
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenu)
        return chemin

    def ecrire_bytes(self, rel, donnees=b"%PDF-1.4 faux document\n"):
        chemin = os.path.join(self.dest, *rel.split("/"))
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(donnees)
        return chemin

    def lire(self, rel):
        with open(os.path.join(self.dest, *rel.split("/")), encoding="utf-8") as f:
            return f.read()

    def existe(self, rel):
        return os.path.exists(os.path.join(self.dest, *rel.split("/")))

    def cache(self, documents):
        """Ecrit `.moodlesync-ocr/cache.json` ; rend les entrees telles qu'elles sont sur le disque."""
        self.ecrire(".moodlesync-ocr/cache.json", json.dumps({"version": 1, "documents": documents},
                                                             ensure_ascii=False, indent=1))
        return documents

    def lire_cache(self):
        with open(os.path.join(self.dest, ".moodlesync-ocr", "cache.json"), encoding="utf-8") as f:
            return json.load(f)["documents"]

    def genere(self, chemin):
        """`.moodlesync.json` : un PDF deja remplace par l'ancienne version (bloc `genere`)."""
        self.ecrire(".moodlesync.json", json.dumps({
            "https://moodle.exemple.ch/mod/resource/view.php?id=1": {
                "chemin": chemin,
                "genere": {"type": "pdf_cherchable", "version": 1, "empreinte_source": "sha256:abc",
                           "taille_source": 21}}}, ensure_ascii=False, indent=1))

    def migrer(self, cfg=None):
        return textes_migration.migrer(self.dest, cfg if cfg is not None else {"dest": self.dest})

    # -- le coffre complet de l'enonce
    def coffre_complet(self):
        self.ecrire_bytes("Cours A/S1/article.pdf")
        self.ecrire_bytes("Cours A/S1/edite.pdf")
        self.ecrire_bytes("Cours A/S1/scan.pdf")
        self.ecrire_bytes("Cours A/autre.pdf")
        self.genere("Cours A/S1/article.pdf")
        texte = FRONT_MATTER.format(source="Cours A/S1/article.pdf")
        self.ecrire("Textes/Cours A/S1/article.pdf.md", texte)
        self.ecrire("Textes/Cours A/S1/edite.pdf.md", EDITE)
        self.ecrire("Textes/Cours A/S1/scan.pdf.md", FRONT_MATTER.format(source="Cours A/S1/scan.pdf"))
        self.ecrire("Textes/Cours A/S1/fantome.pdf.md", FRONT_MATTER.format(source="Cours A/S1/fantome.pdf"))
        self.ecrire("Textes/index.md", AGREGE)
        self.ecrire("Textes/Qualité des textes.md", AGREGE)
        self.ecrire("Textes/Cours A/Cours A - texte des documents.md", AGREGE)
        self.ecrire("Textes/Cours A/export.jsonl", EXPORT)
        self.cache({
            "Cours A/S1/article.pdf": {"etat": "ok", "empreinte": "sha256:a", "taille": 21,
                                       "sortie": "Textes/Cours A/S1/article.pdf.md"},
            "Cours A/S1/edite.pdf": {"etat": "a_verifier", "empreinte": "sha256:b", "taille": 21,
                                     "sortie": "Textes/Cours A/S1/edite.pdf.md"},
            "Cours A/S1/scan.pdf": {"etat": "difficile", "empreinte": "sha256:c", "taille": 21,
                                    "sortie": "Textes/Cours A/S1/scan.pdf.md"},
            "Cours A/S1/fantome.pdf": {"etat": "ok", "empreinte": "sha256:d", "taille": 21,
                                       "sortie": "Textes/Cours A/S1/fantome.pdf.md"},
        })


class Migration(CoffreAncien):
    """Les sept etapes du contrat 8 : deplacer, convertir un « Difficile », supprimer les agregats."""

    def test_le_coffre_ancien_est_migre(self):
        self.coffre_complet()
        pdf_avant = empreintes_pdf(self.dest)
        bilan = self.migrer()
        self.assertEqual(bilan, {"deplaces": 2, "supprimes": 5, "restants": 1},
                         "deux textes deplaces, cinq fichiers agreges supprimes, un orphelin laisse")
        for rel in ("Cours A/S1/article.pdf.md", "Cours A/S1/edite.pdf.md", "Cours A/S1/scan.pdf.md"):
            with self.subTest(rel=rel):
                self.assertFalse(self.existe("Textes/" + rel), "le texte a quitte Textes/")
        self.assertTrue(self.existe("Cours A/S1/article.pdf.md"), "le texte est a cote de son PDF")
        self.assertEqual(self.lire("Cours A/S1/article.pdf.md"),
                         FRONT_MATTER.format(source="Cours A/S1/article.pdf"), "le contenu n'est pas retouche")
        self.assertEqual(self.lire("Cours A/S1/edite.pdf.md"), EDITE, "un texte edite est deplace tel quel")
        for rel in ("Textes/index.md", "Textes/Qualité des textes.md",
                    "Textes/Cours A/Cours A - texte des documents.md", "Textes/Cours A/export.jsonl"):
            with self.subTest(rel=rel):
                self.assertFalse(self.existe(rel), "fichier agrege supprime")
        self.assertTrue(self.existe("Textes/Cours A/S1/fantome.pdf.md"), "un orphelin reste dans Textes/")
        self.assertTrue(os.path.isdir(os.path.join(self.dest, "Textes")), "Textes/ n'est pas vide : elle reste")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")

    def test_le_cache_suit_les_textes_deplaces(self):
        self.coffre_complet()
        self.migrer()
        cache = self.lire_cache()
        article = cache["Cours A/S1/article.pdf"]
        self.assertEqual(article["etat"], "ok", "un etat sain ne change pas")
        self.assertEqual(article["sortie"], "Cours A/S1/article.pdf.md", "sortie suit le fichier deplace")
        self.assertEqual(article["format"], "md", "le format migre est md (contrat 8.2)")
        self.assertTrue(article["remplace"], "remplace se lit dans .moodlesync.json (genere)")
        self.assertIsNone(article["original"], "un PDF migre n'a pas de copie d'original (U9)")
        self.assertEqual(article["sortie_empreinte"],
                         "sha256:" + empreinte(os.path.join(self.dest, "Cours A", "S1", "article.pdf.md")),
                         "sortie_empreinte est mesuree sur le fichier deplace")
        edite = cache["Cours A/S1/edite.pdf"]
        self.assertEqual(edite["sortie"], "Cours A/S1/edite.pdf.md")
        self.assertEqual(edite["etat"], "a_verifier", "l'etat du document ne change pas")
        self.assertFalse(edite["remplace"], "aucun genere : le PDF n'a pas ete remplace")
        scan = cache["Cours A/S1/scan.pdf"]
        self.assertEqual(scan["etat"], "echec", "un ancien « Difficile » devient un echec (O14)")
        self.assertEqual(scan["motif"], "difficile", "le motif dit pourquoi")
        for cle in ("sortie", "format", "sortie_empreinte"):
            with self.subTest(cle=cle):
                self.assertNotIn(cle, scan, "un echec ne porte pas " + cle)
        self.assertIsNone(scan["original"], "un echec n'a pas de copie d'original")
        fantome = cache["Cours A/S1/fantome.pdf"]
        self.assertEqual(fantome["sortie"], "Textes/Cours A/S1/fantome.pdf.md", "un orphelin n'est pas touche")
        self.assertNotIn("format", fantome)

    def test_un_texte_edite_d_un_difficile_est_deplace_jamais_supprime(self):
        self.ecrire_bytes("Cours A/S1/scan.pdf")
        self.ecrire("Textes/Cours A/S1/scan.pdf.md", EDITE)
        self.cache({"Cours A/S1/scan.pdf": {"etat": "difficile", "sortie": "Textes/Cours A/S1/scan.pdf.md"}})
        pdf_avant = empreintes_pdf(self.dest)
        bilan = self.migrer()
        self.assertEqual(bilan, {"deplaces": 1, "supprimes": 0, "restants": 0})
        self.assertEqual(self.lire("Cours A/S1/scan.pdf.md"), EDITE, "un fichier edite est la chose la plus precieuse")
        self.assertEqual(self.lire_cache()["Cours A/S1/scan.pdf"]["etat"], "echec")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")

    def test_relancee_la_migration_ne_change_plus_aucun_octet(self):
        self.coffre_complet()
        pdf_avant = empreintes_pdf(self.dest)
        self.migrer()
        avant = empreinte_arbre(self.dest)
        bilan = self.migrer()
        self.assertEqual(bilan, {"deplaces": 0, "supprimes": 0, "restants": 1}, "la relance ne refait rien")
        self.assertEqual(empreinte_arbre(self.dest), avant, "aucun octet change par la relance")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")

    def test_sans_dossier_textes_rien_ne_se_passe(self):
        self.ecrire_bytes("Cours A/S1/article.pdf")
        self.cache({"Cours A/S1/article.pdf": {"etat": "ok", "empreinte": "sha256:a", "taille": 21}})
        avant = empreinte_arbre(self.dest)
        pdf_avant = empreintes_pdf(self.dest)
        self.assertEqual(self.migrer(), {"deplaces": 0, "supprimes": 0, "restants": 0},
                         "pas de Textes/ : rien a faire")
        self.assertEqual(empreinte_arbre(self.dest), avant, "aucune ecriture")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")

    def test_dossier_textes_vide_est_supprime(self):
        self.ecrire_bytes("Cours A/S1/article.pdf")
        os.makedirs(os.path.join(self.dest, "Textes"))
        pdf_avant = empreintes_pdf(self.dest)
        self.assertEqual(self.migrer(), {"deplaces": 0, "supprimes": 0, "restants": 0})
        self.assertFalse(os.path.exists(os.path.join(self.dest, "Textes")), "Textes/ vide est supprime")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")

    def test_dossier_textes_non_vide_est_laisse(self):
        self.ecrire_bytes("Cours A/S1/article.pdf")
        self.ecrire("Textes/Cours A/S1/fantome.pdf.md", FRONT_MATTER.format(source="Cours A/S1/fantome.pdf"))
        pdf_avant = empreintes_pdf(self.dest)
        bilan = self.migrer()
        self.assertEqual(bilan, {"deplaces": 0, "supprimes": 0, "restants": 1})
        self.assertTrue(os.path.isdir(os.path.join(self.dest, "Textes")), "Textes/ reste, l'annonce le dit")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")

    def test_une_cible_deja_presente_n_est_pas_ecrasee(self):
        self.ecrire_bytes("Cours A/S1/article.pdf")
        self.ecrire("Cours A/S1/article.pdf.md", EDITE)
        self.ecrire("Textes/Cours A/S1/article.pdf.md", FRONT_MATTER.format(source="Cours A/S1/article.pdf"))
        pdf_avant = empreintes_pdf(self.dest)
        bilan = self.migrer()
        self.assertEqual(bilan, {"deplaces": 0, "supprimes": 0, "restants": 1},
                         "un texte deja a cote, different, n'est jamais ecrase")
        self.assertEqual(self.lire("Cours A/S1/article.pdf.md"), EDITE)
        self.assertTrue(self.existe("Textes/Cours A/S1/article.pdf.md"), "l'ancien reste, il n'est pas perdu")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")

    def test_une_cible_identique_supprime_le_doublon(self):
        self.ecrire_bytes("Cours A/S1/article.pdf")
        self.ecrire("Cours A/S1/article.pdf.md", FRONT_MATTER.format(source="Cours A/S1/article.pdf"))
        self.ecrire("Textes/Cours A/S1/article.pdf.md", FRONT_MATTER.format(source="Cours A/S1/article.pdf"))
        pdf_avant = empreintes_pdf(self.dest)
        bilan = self.migrer()
        self.assertEqual(bilan, {"deplaces": 0, "supprimes": 1, "restants": 0}, "le doublon identique part")
        self.assertFalse(os.path.exists(os.path.join(self.dest, "Textes")), "Textes/ se vide et part")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")

    def test_un_fichier_etranger_dans_textes_compte_et_reste(self):
        """E-V4-8 : un fichier qui n'est pas un `.md` compte dans `restants`, `Textes/` reste (contrat 8.6)."""
        self.ecrire_bytes("Cours A/S1/article.pdf")
        self.ecrire("Textes/Cours A/S1/article.pdf.md", FRONT_MATTER.format(source="Cours A/S1/article.pdf"))
        self.ecrire("Textes/note perso.txt", "une note que j'ai ecrite\n")
        pdf_avant = empreintes_pdf(self.dest)
        bilan = self.migrer()
        self.assertEqual(bilan, {"deplaces": 1, "supprimes": 0, "restants": 1},
                         "le fichier etranger compte, sinon l'annonce se tait")
        self.assertTrue(self.existe("Textes/note perso.txt"), "il n'est jamais supprime")
        self.assertTrue(os.path.isdir(os.path.join(self.dest, "Textes")), "Textes/ reste")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")

    def test_un_dossier_textes_de_moodle_garde_ses_fichiers(self):
        """E-V4-7 : sans la marque d'un fichier genere, rien n'est supprime ; et jamais un PDF."""
        self.ecrire_bytes("Textes/S1/cours.pdf")
        self.ecrire("Textes/index.md", "# Index d'un cours Moodle\n")
        self.ecrire("Textes/Cours - texte des documents.md", "notes prises en cours\n")
        self.ecrire("Textes/export.jsonl", '{"page": 1}\n')
        self.ecrire_bytes("Cours A/article.pdf")
        self.ecrire("Textes/Cours A/article.pdf.md", FRONT_MATTER.format(source="Cours A/article.pdf"))
        pdf_avant = empreintes_pdf(self.dest)
        bilan = self.migrer()
        self.assertEqual(bilan, {"deplaces": 1, "supprimes": 0, "restants": 4},
                         "quatre fichiers sans la marque restent, dont un PDF")
        for rel in ("Textes/S1/cours.pdf", "Textes/index.md", "Textes/Cours - texte des documents.md",
                    "Textes/export.jsonl"):
            with self.subTest(rel=rel):
                self.assertTrue(self.existe(rel), "un fichier sans la marque d'un fichier genere est garde")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")

    def test_une_migration_interrompue_garde_le_cache_a_jour(self):
        """E-V4-6 : le cache est ecrit apres chaque texte deplace, une erreur au milieu ne le laisse pas faux."""
        self.ecrire_bytes("Cours A/S1/a.pdf")
        self.ecrire_bytes("Cours A/S1/b.pdf")
        self.ecrire("Textes/Cours A/S1/a.pdf.md", FRONT_MATTER.format(source="Cours A/S1/a.pdf"))
        self.ecrire("Textes/Cours A/S1/b.pdf.md", FRONT_MATTER.format(source="Cours A/S1/b.pdf"))
        self.ecrire("Textes/Cours A/export.jsonl", EXPORT)
        self.cache({"Cours A/S1/a.pdf": {"etat": "ok", "sortie": "Textes/Cours A/S1/a.pdf.md"},
                    "Cours A/S1/b.pdf": {"etat": "ok", "sortie": "Textes/Cours A/S1/b.pdf.md"}})
        pdf_avant = empreintes_pdf(self.dest)
        vrai = os.remove

        def remove(chemin, *arguments, **options):
            if str(chemin).endswith("export.jsonl"):
                raise OSError("fichier verrouille")
            return vrai(chemin, *arguments, **options)
        with mock.patch.object(textes_migration.os, "remove", remove):
            with self.assertRaises(OSError):
                self.migrer()
        cache = self.lire_cache()
        for cle in ("Cours A/S1/a.pdf", "Cours A/S1/b.pdf"):
            with self.subTest(cle=cle):
                self.assertEqual(cache[cle]["sortie"], cle + ".md",
                                 "le cache suit un texte deja deplace, malgre l'interruption")
                self.assertEqual(cache[cle]["format"], "md")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")
        bilan = self.migrer()                              # la relance reprend la fin du travail
        self.assertEqual(bilan, {"deplaces": 0, "supprimes": 1, "restants": 0})
        self.assertFalse(os.path.exists(os.path.join(self.dest, "Textes")), "Textes/ part a la reprise")
        self.assertEqual(empreintes_pdf(self.dest), pdf_avant, "aucun PDF n'est modifie")


class FauxFenetre:
    def __init__(self, pret=True):
        self.pret = pret
        self.scripts = []

    def evaluate_js(self, code):
        self.scripts.append(code)
        return self.pret


class FauxApi:
    """La surface d'Api que la migration utilise : les reglages et l'appel a la page."""

    def __init__(self):
        self._fenetre = None
        self.appels = []

    def _cfg(self):
        return ms.charger_config()

    def _sauver_cfg(self, modif):
        c = ms.charger_config()
        modif(c)
        ms.sauver_config(c)

    def _js(self, fonction, valeur):
        self.appels.append((fonction, valeur))


class AuDemarrage(CoffreAncien):
    """Appel au demarrage (contrat 8.7) : une fois, puis `textes_v2` ; annonce s'il y a eu du travail."""

    def setUp(self):
        super().setUp()
        self.configurer()

    def configurer(self, **champs):
        c = {"dest": self.dest}
        c.update(champs)
        with open(ms.CONFIG, "w", encoding="utf-8") as f:
            json.dump(c, f)

    def config(self):
        with open(ms.CONFIG, encoding="utf-8") as f:
            return json.load(f)

    def test_du_travail_donne_une_annonce_et_textes_v2(self):
        self.ecrire_bytes("Cours A/S1/article.pdf")
        self.ecrire("Textes/Cours A/S1/article.pdf.md", FRONT_MATTER.format(source="Cours A/S1/article.pdf"))
        api = FauxApi()
        bilan = app.migrer_textes(api)
        self.assertEqual(bilan, {"deplaces": 1, "supprimes": 0, "restants": 0}, "l'annonce porte le bilan")
        self.assertTrue(self.config().get("textes_v2"), "textes_v2 est ecrit apres la migration")
        self.assertTrue(self.existe("Cours A/S1/article.pdf.md"), "le travail est fait")

    def test_annonce_une_seule_fois(self):
        self.ecrire_bytes("Cours A/S1/article.pdf")
        self.ecrire("Textes/Cours A/S1/article.pdf.md", FRONT_MATTER.format(source="Cours A/S1/article.pdf"))
        api = FauxApi()
        self.assertTrue(app.migrer_textes(api), "le premier demarrage annonce")
        self.ecrire("Textes/Cours A/S1/autre.pdf.md", FRONT_MATTER.format(source="Cours A/S1/autre.pdf"))
        self.assertEqual(app.migrer_textes(api), {}, "le deuxieme demarrage n'annonce plus rien")
        self.assertTrue(self.existe("Textes/Cours A/S1/autre.pdf.md"), "et ne refait rien")

    def test_sans_travail_aucune_annonce(self):
        self.ecrire_bytes("Cours A/S1/article.pdf")
        api = FauxApi()
        self.assertEqual(app.migrer_textes(api), {}, "rien a faire : pas d'annonce")
        self.assertTrue(self.config().get("textes_v2"), "textes_v2 est ecrit quand meme (contrat 8.1)")

    def test_l_annonce_dit_ce_qui_reste_dans_textes(self):
        """E-V4-8 : un fichier etranger laisse `Textes/` en place, et l'annonce le dit (contrat 8.6)."""
        self.ecrire_bytes("Cours A/S1/article.pdf")
        self.ecrire("Textes/note perso.txt", "une note que j'ai ecrite\n")
        self.assertEqual(app.migrer_textes(FauxApi()), {"deplaces": 0, "supprimes": 0, "restants": 1},
                         "sans ce compte, l'annonce se tairait et Textes/ resterait sans explication")
        self.assertTrue(self.config().get("textes_v2"))

    def test_une_migration_interrompue_ne_marque_pas_textes_v2(self):
        """E-V4-6 : une erreur de suppression laisse `textes_v2` non ecrit, la migration sera reprise."""
        self.ecrire_bytes("Cours A/S1/a.pdf")
        self.ecrire("Textes/Cours A/S1/a.pdf.md", FRONT_MATTER.format(source="Cours A/S1/a.pdf"))
        self.ecrire("Textes/Cours A/export.jsonl", EXPORT)
        vrai = os.remove

        def remove(chemin, *arguments, **options):
            if str(chemin).endswith("export.jsonl"):
                raise OSError("fichier verrouille")
            return vrai(chemin, *arguments, **options)
        with mock.patch.object(textes_migration.os, "remove", remove):
            self.assertEqual(app.migrer_textes(FauxApi()), {}, "une erreur ne s'annonce pas comme un bilan")
        self.assertFalse(self.config().get("textes_v2"), "le prochain demarrage reprend la migration")
        self.assertTrue(self.existe("Cours A/S1/a.pdf.md"), "le texte deja deplace reste a sa place")

    def test_l_annonce_passe_par_la_page(self):
        api = FauxApi()
        api._fenetre = FauxFenetre()
        self.assertTrue(app.annoncer_migration(api, {"deplaces": 2, "supprimes": 1, "restants": 0}, essais=1))
        self.assertEqual([f for f, _ in api.appels], ["textesMigration"], "une seule annonce, par window.textesMigration")
        self.assertEqual(api.appels[0][1], {"deplaces": 2, "supprimes": 1, "restants": 0})
        api.appels.clear()
        self.assertFalse(app.annoncer_migration(api, {}, essais=1), "un bilan vide ne s'annonce pas")
        self.assertEqual(api.appels, [])

    def test_la_page_pas_encore_prete_n_empeche_rien(self):
        api = FauxApi()
        api._fenetre = FauxFenetre(pret=False)
        self.assertFalse(app.annoncer_migration(api, {"deplaces": 1, "supprimes": 0, "restants": 0}, essais=1),
                         "sans la fonction dans la page, rien n'est appele")
        self.assertEqual(api.appels, [])


if __name__ == "__main__":
    unittest.main()
