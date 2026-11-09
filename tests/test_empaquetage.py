"""Tests hors ligne de l'empaquetage (tache P1) : dependances de requirements.txt, imports caches du spec
PyInstaller, absence de tiret long et de CRLF dans les fichiers de compilation.

Aucun PyInstaller n'est lance et aucun bundle n'est fabrique : ces tests lisent les fichiers, parce que la
machine de developpement est sous Linux, sans PyInstaller, sans Windows et sans macOS. Le demarrage reel de
l'exe et de l'app reste a mesurer par Maxence.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import ast, os, re, sys, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

FICHIERS = ("requirements.txt", "requirements-testes.txt", "MoodleSync.spec", "tests/test_empaquetage.py")


def lire(chemin):
    with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
        return f.read()


def exigence(texte, nom):
    """(version, marqueur) de la ligne de premier niveau qui epingle `nom`, ou (None, None) sans ligne.

    Une ligne commence en colonne 0 et peut porter un extra (`urllib3[socks]`), une version `==...` et un
    marqueur apres un point-virgule. Les commentaires en fin de ligne sont coupes.
    """
    motif = re.compile(r"^%s\s*(?:\[[^\]]*\])?\s*(==[^\s;#]*)?\s*(?:;(.*))?$" % re.escape(nom), re.M)
    m = motif.search(texte)
    if not m:
        return None, None
    version = m.group(1)[2:].split("#")[0].strip() if m.group(1) else None
    marqueur = (m.group(2) or "").split("#")[0].strip()
    return version, marqueur


class Requirements(unittest.TestCase):
    """Le produit importe pypdfium2 et PIL a l'execution (D11) : les deux doivent etre installes par
    requirements.txt, avec une version exacte et sans marqueur qui les retirerait d'un des deux systemes.

    Les metadonnees PyPI lues le 9 novembre 2026 donnent des roues Windows (win32, win_amd64, win_arm64),
    Linux et macOS pour les deux paquets. La seule limite de plateforme reelle, pypdfium2 sans roue macOS
    avant 13 (ecart 17), ne s'exprime pas en marqueur PEP 508 : elle est donc ecrite en commentaire, et ce
    test verifie que le commentaire la nomme.
    """

    def setUp(self):
        self.texte = lire("requirements.txt")

    def test_pypdfium2_epingle(self):
        version, marqueur = exigence(self.texte, "pypdfium2")
        self.assertIsNotNone(version, "requirements.txt n'epingle pas pypdfium2")
        self.assertRegex(version or "", r"^\d+\.\d+")
        self.assertEqual(marqueur, "", "aucun marqueur de plateforme ne doit retirer pypdfium2 d'un systeme")

    def test_pillow_epingle(self):
        for nom in ("pillow", "Pillow"):
            version, marqueur = exigence(self.texte, nom)
            if version is not None:
                break
        self.assertIsNotNone(version, "requirements.txt n'epingle pas Pillow")
        self.assertRegex(version or "", r"^\d+\.\d+")
        self.assertEqual(marqueur, "", "aucun marqueur de plateforme ne doit retirer Pillow d'un systeme")

    def test_limite_macos_ecrite(self):
        """pypdfium2 n'a de roue macOS que pour 13 et plus (ecart 17) : la limite et la source des versions
        sont ecrites dans le fichier, faute de pouvoir les exprimer en marqueur."""
        self.assertIn("macOS 13", self.texte)
        self.assertIn("PyPI", self.texte)


class Spec(unittest.TestCase):
    """MoodleSync.spec doit montrer a PyInstaller ce que les imports a l'usage de ocr.py cachent (D11) :
    pypdfium2 et sa bibliotheque pdfium, PIL et ses trois modules, pypdf, et le certifi de macOS."""

    def setUp(self):
        self.texte = lire("MoodleSync.spec")
        self.arbre = ast.parse(self.texte)

    def _hiddenimports(self):
        noms = set()
        for noeud in ast.walk(self.arbre):
            if isinstance(noeud, ast.Assign):
                cibles = [c.id for c in noeud.targets if isinstance(c, ast.Name)]
                if "hiddenimports" not in cibles:
                    continue
                for sous in ast.walk(noeud.value):
                    if isinstance(sous, ast.Constant) and isinstance(sous.value, str):
                        noms.add(sous.value)
                    elif isinstance(sous, ast.Call) and sous.args and isinstance(sous.args[0], ast.Constant):
                        noms.add(sous.args[0].value)
        return noms

    def test_pypdfium2_declare(self):
        noms = self._hiddenimports()
        self.assertIn("pypdfium2", noms)
        self.assertIn("pypdfium2_raw", noms, "la bibliotheque pdfium est dans le paquet pypdfium2_raw")

    def test_pil_declare(self):
        noms = self._hiddenimports()
        self.assertTrue(any(n == "PIL" or n.startswith("PIL.") for n in noms), "PIL absent des hiddenimports")

    def test_pypdf_garde(self):
        self.assertIn("pypdf", self._hiddenimports())

    def test_certifi_macos_garde(self):
        blocs = [n for n in ast.walk(self.arbre)
                 if isinstance(n, ast.If) and "darwin" in (ast.get_source_segment(self.texte, n.test) or "")]
        self.assertTrue(blocs, "le bloc macOS du spec a disparu")
        self.assertTrue(any("certifi" in (ast.get_source_segment(self.texte, n) or "") for n in blocs))

    def test_spec_compile(self):
        compile(self.texte, "MoodleSync.spec", "exec")


class Forme(unittest.TestCase):
    """Aucun fichier touche par P1 ne porte de tiret long ni de CRLF (travail en LF)."""

    def test_ni_tiret_long_ni_crlf(self):
        for chemin in FICHIERS:
            with self.subTest(chemin=chemin):
                with open(os.path.join(RACINE, chemin), "rb") as f:
                    octets = f.read()
                self.assertNotIn(b"\r\n", octets)
                texte = octets.decode("utf-8")
                self.assertNotIn(chr(0x2013), texte)
                self.assertNotIn(chr(0x2014), texte)


class RequirementsTestes(unittest.TestCase):
    """Pillow n'est plus une dependance de test seulement : le produit l'importe a l'execution."""

    def test_pillow_presente_comme_dependance_du_produit(self):
        texte = lire("requirements-testes.txt")
        self.assertNotIn("n'est pas necessaire au produit", texte)
        self.assertIn("Pillow", texte)
        self.assertIn("requirements.txt", texte)


if __name__ == "__main__":
    unittest.main()
