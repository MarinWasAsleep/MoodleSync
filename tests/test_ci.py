"""Tests hors ligne de la CI (tache P2) : la suite tourne sans moteur OCR, et la CI le prouve.

Aucun workflow n'est execute et aucun executeur de GitHub n'est joignable depuis la machine de
developpement : ces tests lisent les fichiers (`.github/workflows/compilation.yml` et `tests/`) et
verifient ce qui peut l'etre par lecture. L'execution reelle sur les executeurs, ses durees et la
presence d'un Tesseract preinstalle dans les images de GitHub ne sont pas mesurables ici.

Le moteur est facultatif (contrat) : un `tesseract` present sur la machine ne doit faire echouer
aucun test, et un sous-processus a `PATH` prepare le mesure avec un faux moteur (ecart 270).

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = ".github/workflows/compilation.yml"
DOSSIER_TESTS = os.path.join(RACINE, "tests")
COMMANDE_SUITE = "python -m unittest discover -s tests -t ."
INSTALLATION = "python -m pip install -r requirements-testes.txt"
FICHIERS_DE_FORME = (WORKFLOW, "tests/test_ci.py")
VARIABLE_SOUS_PROCESSUS = "MOODLESYNC_CI_DANS_UN_SOUS_PROCESSUS"

# Assertions qui font dependre la suite de l'etat de la machine : elles exigent qu'un outil soit
# absent du `PATH`. Le moteur est facultatif (contrat), donc la suite doit rester verte qu'il soit
# la ou non (ecart 270, mesure par la revue de P2). Limite : une absence exigee autrement qu'avec
# `assertIsNone`, `assertFalse` ou `assertEqual(..., None)` n'est pas vue (journal, corrections-P2).
ABSENCES_INTERDITES = (
    re.compile(r"assertIsNone\(\s*shutil\.which\("),
    re.compile(r"assertFalse\(\s*shutil\.which\("),
    re.compile(r"assertEqual\(\s*shutil\.which\([^()]*\)\s*,\s*None\s*\)"),
)


def lire_octets(chemin):
    with open(os.path.join(RACINE, chemin), "rb") as f:
        return f.read()


def lire_texte(chemin):
    """Contenu du fichier, fins de ligne normalisees : la lecture ne depend pas du systeme."""
    return lire_octets(chemin).decode("utf-8").replace("\r\n", "\n")


def lignes_du_job(texte, nom):
    """Lignes du job `nom` du workflow, sans les lignes du job suivant.

    Lecture par indentation, plan du fichier : les jobs sont des cles de deux espaces sous `jobs:`,
    leurs etapes des elements de liste de six espaces. Un job absent rend une liste vide, ce que
    chaque test dit ; une autre mise en page fait echouer le test qui cherche une etape, jamais
    passer par defaut.
    """
    lignes = texte.split("\n")
    debut = None
    for i, ligne in enumerate(lignes):
        if ligne == "  %s:" % nom:
            debut = i + 1
            break
    if debut is None:
        return []
    for j in range(debut, len(lignes)):
        if re.match(r"^  [A-Za-z0-9_.-]+:\s*$", lignes[j]):
            return lignes[debut:j]
    return lignes[debut:]


def etapes(lignes):
    """Etapes d'un job : chaque element de liste de six espaces ouvre une etape."""
    blocs = []
    for ligne in lignes:
        if re.match(r"^      - ", ligne):
            blocs.append([ligne])
        elif blocs:
            blocs[-1].append(ligne)
    return blocs


def texte_etape(etape):
    return "\n".join(etape)


def fichiers_de_test(suffixe):
    """Fichiers `tests/*<suffixe>` du depot, tries : la liste vient du disque, pas d'une enumeration."""
    return sorted(nom for nom in os.listdir(DOSSIER_TESTS)
                  if nom.endswith(suffixe) and os.path.isfile(os.path.join(DOSSIER_TESTS, nom)))


def gardes(chemin="tests/test_ocr.py"):
    """Couples (numero de ligne, ligne) des gardes `@unittest.skipUnless(...)` d'un fichier de test."""
    trouvees = []
    for numero, ligne in enumerate(lire_texte(chemin).split("\n"), 1):
        if ligne.strip().startswith("@unittest.skipUnless("):
            trouvees.append((numero, ligne.strip()))
    return trouvees


def fonction(texte, nom):
    """Noeud AST de la fonction `nom` d'un fichier de test, ou None."""
    for noeud in ast.walk(ast.parse(texte)):
        if isinstance(noeud, ast.FunctionDef) and noeud.name == nom:
            return noeud
    return None


def planter_faux_moteur(dossier):
    """Ecrit un faux `tesseract` executable dans `dossier` et rend son chemin.

    Sous Windows le fichier s'appelle `tesseract.bat` (le `PATHEXT` par defaut le fait trouver par
    `shutil.which`), ailleurs `tesseract` avec son bit executable. Le faux repond a `--version` :
    c'est ce qu'il faut pour qu'une detection le voie, et rien de plus, puisqu'aucun test ne
    l'execute. Le dossier est temporaire et n'est pas dans le depot.
    """
    if os.name == "nt":
        chemin = os.path.join(dossier, "tesseract.bat")
        contenu = "@echo off\r\necho tesseract 5.5.3\r\n"
    else:
        chemin = os.path.join(dossier, "tesseract")
        contenu = "#!/bin/sh\nprintf 'tesseract 5.5.3\\n'\n"
    with open(chemin, "w", newline="") as f:
        f.write(contenu)
    if os.name != "nt":
        os.chmod(chemin, 0o755)
    return chemin


class JobTests(unittest.TestCase):
    """Le job `tests` installe les dependances de test puis lance la suite hors ligne, sur Linux et
    sur Windows : c'est lui qui tourne sur une pull request."""

    def setUp(self):
        self.texte = lire_texte(WORKFLOW)
        self.lignes = lignes_du_job(self.texte, "tests")
        self.bloc = "\n".join(self.lignes)

    def test_job_tests_present(self):
        self.assertTrue(self.lignes, "aucun job `tests:` dans %s" % WORKFLOW)

    def test_declenchee_sur_une_pull_request(self):
        self.assertIn("\n  pull_request:", self.texte, "le workflow ne se declenche plus sur une pull request")

    def test_job_atteignable_sur_une_pull_request(self):
        conditions = [ligne.strip() for ligne in self.lignes if ligne.strip().startswith("if:")]
        for condition in conditions:
            self.assertIn("pull_request", condition,
                          "le job `tests` est conditionne sans nommer pull_request : %s" % condition)

    def test_deux_systemes(self):
        self.assertIn("ubuntu-latest", self.bloc, "le job `tests` ne tourne plus sous ubuntu-latest")
        self.assertIn("windows-latest", self.bloc, "le job `tests` ne tourne plus sous windows-latest")

    def test_dependances_de_test_installees(self):
        installations = [texte_etape(e) for e in etapes(self.lignes) if INSTALLATION in texte_etape(e)]
        self.assertTrue(installations,
                        "le job `tests` n'installe pas requirements-testes.txt avec `%s`" % INSTALLATION)

    def test_suite_hors_ligne_lancee(self):
        lancees = [texte_etape(e) for e in etapes(self.lignes) if COMMANDE_SUITE in texte_etape(e)]
        self.assertTrue(lancees,
                        "le job `tests` ne lance pas `%s`" % COMMANDE_SUITE)

    def test_dependances_avant_la_suite(self):
        lignes = self.lignes
        installation = [i for i, ligne in enumerate(lignes) if INSTALLATION in ligne]
        suite = [i for i, ligne in enumerate(lignes) if COMMANDE_SUITE in ligne]
        self.assertTrue(installation and suite, "etape d'installation ou suite absente du job `tests`")
        self.assertLess(min(installation), min(suite),
                        "la suite est lancee avant l'installation de requirements-testes.txt")

    def test_une_seule_suite_par_job(self):
        """Deux commandes de suite dans le meme job feraient tourner la base deux fois sans le dire."""
        lignes = [ligne for ligne in self.lignes if COMMANDE_SUITE in ligne]
        self.assertEqual(len(lignes), 1, "le job `tests` lance la suite %d fois" % len(lignes))


class SansMoteur(unittest.TestCase):
    """La CI ne doit pas installer Tesseract : c'est ce qui prouve que la suite passe sans moteur, et
    que les tests qui ont besoin du vrai moteur s'ignorent proprement. Le moteur reste facultatif
    (contrat) : aucun test ne doit exiger son absence de la machine (ecart 270, revue de P2)."""

    def setUp(self):
        self.texte = lire_texte(WORKFLOW)

    def test_aucune_installation_de_tesseract(self):
        lignes = [(i, ligne.strip()) for i, ligne in enumerate(self.texte.split("\n"), 1)
                  if re.search(r"tesseract|tessdata", ligne, re.I)]
        self.assertEqual(lignes, [],
                         "le workflow nomme Tesseract ou tessdata : lignes %s. Un job qui installe le "
                         "moteur doit le dire explicitement ici, avec la raison ecrite au journal "
                         "(prompt 58), parce que ce test est la preuve que la suite passe sans moteur"
                         % lignes)

    def test_aucun_test_n_exige_l_absence_d_un_outil(self):
        """Propriete du dossier de tests, pas de la machine : aucun test ne doit exiger qu'un outil
        soit absent du `PATH`. Une garde de test facultatif dit sa raison et nomme son outil ; elle
        n'impose rien (ecart 270)."""
        coupables = []
        for nom in fichiers_de_test(".py"):
            chemin = "tests/" + nom
            for numero, ligne in enumerate(lire_texte(chemin).split("\n"), 1):
                if any(motif.search(ligne) for motif in ABSENCES_INTERDITES):
                    coupables.append("%s ligne %d : %s" % (chemin, numero, ligne.strip()))
        self.assertEqual(
            coupables, [],
            "ces assertions font echouer la suite quand un outil est installe, alors que le moteur "
            "est facultatif et que la CI peut tourner sur une image qui le porte : %s" % coupables)

    def test_suite_de_la_ci_verte_avec_un_faux_moteur(self):
        """La suite des gardes ne depend pas de la machine : elle reste verte avec un faux
        `tesseract` en tete du `PATH`, mesure dans un sous-processus a `PATH` prepare (ecart 270).

        Le sous-processus est necessaire : modifier le `PATH` du processus courant le laisserait
        modifie pour les autres tests. Les tests de ce fichier lisent le depot, ils n'executent pas
        le moteur, donc un faux suffit. Le test complet de reconnaissance (T29) n'est pas lance ici :
        il demande un vrai moteur et une image, et un faux moteur sur le `PATH` le fait echouer a bon
        droit (mesure au journal).
        """
        if os.environ.get(VARIABLE_SOUS_PROCESSUS) == "1":
            self.skipTest("sous-processus lance par ce meme test : recursion evitee")
        with tempfile.TemporaryDirectory() as dossier:
            faux = planter_faux_moteur(dossier)
            trouve = shutil.which("tesseract", path=dossier)
            # Sous Windows, `which` rend l'extension de PATHEXT (`.BAT`) et non celle du fichier ecrit (`.bat`) :
            # meme fichier, casse differente (ecart 303). On compare comme le systeme.
            self.assertEqual(os.path.normcase(trouve) if trouve else trouve, os.path.normcase(faux),
                             "le faux moteur n'est pas executable ou pas lisible sous ce systeme")
            environnement = dict(os.environ)
            environnement[VARIABLE_SOUS_PROCESSUS] = "1"
            environnement["PATH"] = dossier + os.pathsep + environnement.get("PATH", "")
            programme = "\n".join([
                "import shutil, sys, unittest",
                "moteur = shutil.which('tesseract')",
                "if not moteur:",
                "    sys.exit('faux moteur introuvable sur le PATH prepare : ' + sys.argv[1])",
                "print('moteur trouve : ' + moteur)",
                "resultat = unittest.TextTestRunner(verbosity=0).run(",
                "    unittest.defaultTestLoader.loadTestsFromName('tests.test_ci'))",
                "sys.exit(0 if resultat.wasSuccessful() else 1)",
            ])
            lance = subprocess.run([sys.executable, "-c", programme, faux],
                                   cwd=RACINE, env=environnement,
                                   capture_output=True, text=True, timeout=300)
        self.assertEqual(lance.returncode, 0,
                         "la suite des gardes echoue avec un faux moteur sur le PATH\n"
                         "stdout :\n%s\nstderr :\n%s" % (lance.stdout, lance.stderr))

    def test_garde_du_moteur_reel_nomme_tesseract(self):
        """Toute garde qui appelle `_moteur_reel` doit nommer Tesseract : c'est la seule dependance
        facultative de ces tests, et la raison de l'ignore doit la dire."""
        gardes_moteur = [(n, l) for n, l in gardes() if "_moteur_reel(" in l]
        self.assertTrue(gardes_moteur, "plus aucune garde n'appelle `_moteur_reel` dans tests/test_ocr.py")
        for numero, ligne in gardes_moteur:
            self.assertIn("Tesseract", ligne,
                          "la garde de la ligne %d ne nomme pas Tesseract : %s" % (numero, ligne))

    def test_definition_du_moteur_reel(self):
        """`_moteur_reel` doit interroger la detection du moteur, pas une liste ecrite a la main."""
        texte = lire_texte("tests/test_ocr.py")
        noeud = fonction(texte, "_moteur_reel") or self.fail("`_moteur_reel` a disparu de tests/test_ocr.py")
        source = ast.get_source_segment(texte, noeud) or ""
        self.assertIn("ocr.detecter(", source, "la garde n'interroge plus `ocr.detecter` : %s" % source)

    def test_pillow_manquant_n_est_pas_ignore(self):
        """Pillow est une dependance de requirements-testes.txt (P1) : la garde ne doit pas la mettre
        dans un `try/except ImportError`, sinon un environnement casse n'ignore T29 en silence au lieu
        de le signaler (ecart 261, mesure de P2)."""
        texte = lire_texte("tests/test_ocr.py")
        noeud = fonction(texte, "_moteur_reel") or self.fail("`_moteur_reel` a disparu de tests/test_ocr.py")
        source = ast.get_source_segment(texte, noeud) or ""
        self.assertNotIn("except ImportError", source,
                         "un `try/except ImportError` protege la garde : Pillow absent redeviendrait un "
                         "test ignore au lieu d'une erreur d'installation")
        self.assertIn("import PIL", source,
                      "la garde de T29 n'importe plus Pillow : son absence n'est plus signalee")

    def test_gardes_des_parcours_js_nomment_node(self):
        """Un fichier `tests/*_js.py` execute du JavaScript : chaque parcours sur DOM factice porte une
        garde `shutil.which("node")` dont la raison nomme node."""
        fichiers = fichiers_de_test("_js.py")
        self.assertTrue(fichiers, "aucun fichier de test JavaScript dans tests/")
        for nom in fichiers:
            chemin = "tests/" + nom
            gardes_node = [(n, l) for n, l in gardes(chemin) if 'shutil.which("node")' in l]
            self.assertTrue(gardes_node, "%s n'a aucune garde sur node" % chemin)
            for numero, ligne in gardes_node:
                self.assertIn("node", ligne.split(",", 1)[-1],
                              "la garde de %s ligne %d ne nomme pas node : %s" % (chemin, numero, ligne))

    def test_toutes_les_gardes_disent_leur_raison(self):
        """Une garde sans raison s'ignore en silence : chaque `skipUnless` porte une phrase."""
        for nom in fichiers_de_test(".py"):
            chemin = "tests/" + nom
            for numero, ligne in gardes(chemin):
                self.assertRegex(ligne, r'"[^"]*[A-Za-z][^"]*"\s*\)',
                                 "garde sans raison en %s ligne %d : %s" % (chemin, numero, ligne))


class Forme(unittest.TestCase):
    """Le workflow et ce fichier s'ecrivent en LF, sans tiret long ni demi-cadratin."""

    def test_ni_tiret_long_ni_crlf(self):
        for chemin in FICHIERS_DE_FORME:
            with self.subTest(chemin=chemin):
                octets = lire_octets(chemin)
                self.assertNotIn(b"\r\n", octets)
                texte = octets.decode("utf-8")
                self.assertNotIn(chr(0x2013), texte)
                self.assertNotIn(chr(0x2014), texte)


class Yaml(unittest.TestCase):
    """Le workflow est du YAML lisible par `yaml.safe_load` quand PyYAML est disponible.

    PyYAML n'est ni dans `requirements.txt` ni dans `requirements-testes.txt` : ne pas ajouter de
    dependance pour ce test. Absent, le controle de forme YAML n'est pas mesure (journal de P2) et le
    test se contente de le dire sans echouer.
    """

    def test_yaml_lisible(self):
        try:
            import yaml
        except ImportError:
            self.assertNotIn("yaml", lire_texte("requirements-testes.txt").lower(),
                             "PyYAML est entre dans requirements-testes.txt sans decision au journal")
            return
        donnees = yaml.safe_load(lire_texte(WORKFLOW))
        self.assertIn("jobs", donnees or {})
        self.assertIn("tests", donnees["jobs"])
        etapes_du_job = donnees["jobs"]["tests"].get("steps") or []
        commandes = "\n".join(str(etape.get("run", "")) for etape in etapes_du_job)
        self.assertIn(COMMANDE_SUITE, commandes)


if __name__ == "__main__":
    unittest.main()
