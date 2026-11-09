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

FICHIERS = ("requirements.txt", "requirements-testes.txt", "MoodleSync.spec", "tests/test_empaquetage.py",
            ".gitattributes")

# Versions que le depot epingle (ecarts 264 et 268). 5.15.1 est retiree de PyPI (yanked) : jamais a epingler.
PYPDFIUM2 = "5.15.2"
PYPDFIUM2_RETIREES = ("5.15.1",)
PILLOW = "13.0.0"


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

    def test_pypdfium2_version_decidee(self):
        """Ecart 264 : 5.15.1 est retiree de PyPI, la decision de Maxence est 5.15.2."""
        version, _ = exigence(self.texte, "pypdfium2")
        self.assertNotIn(version, PYPDFIUM2_RETIREES, "version retiree de PyPI (yanked)")
        self.assertEqual(version, PYPDFIUM2)

    def test_pillow_epingle(self):
        for nom in ("pillow", "Pillow"):
            version, marqueur = exigence(self.texte, nom)
            if version is not None:
                break
        self.assertIsNotNone(version, "requirements.txt n'epingle pas Pillow")
        self.assertRegex(version or "", r"^\d+\.\d+")
        self.assertEqual(marqueur, "", "aucun marqueur de plateforme ne doit retirer Pillow d'un systeme")

    def test_pillow_version_exacte(self):
        """Ecart 268 (M07) : le motif x.y laissait passer n'importe quelle version."""
        self.assertEqual(exigence(self.texte, "pillow")[0], PILLOW)

    def test_pypdfium2_absent_de_requirements_compilation(self):
        """requirements-compilation.txt inclut requirements.txt et ne reepingle pas pypdfium2 (une seconde
        version divergerait)."""
        compilation = lire("requirements-compilation.txt")
        self.assertRegex(compilation, r"(?m)^-r requirements\.txt\s*$")
        self.assertIsNone(exigence(compilation, "pypdfium2")[0])

    def test_limite_macos_ecrite(self):
        """pypdfium2 n'a de roue macOS que pour 13 et plus (ecart 17) : la limite et la source des versions
        sont ecrites dans le fichier, faute de pouvoir les exprimer en marqueur."""
        self.assertIn("macOS 13", self.texte)
        self.assertIn("PyPI", self.texte)

    def test_limite_macos_exacte(self):
        """Ecart 266 : il existe un sdist, la limite ne vient pas de pip mais de la bibliotheque embarquee
        (Mach-O minos 13.0.0). Un commentaire qui dit « aucune source » ou « pip ne trouve rien » est faux.
        Ecart 268 (M23, M24) : la phrase de la limite doit etre une ligne de commentaire precise, pas
        seulement presente quelque part."""
        bas = self.texte.lower()
        self.assertNotIn("aucune source", bas)
        self.assertNotIn("pas de source", bas)
        self.assertNotIn("pip ne trouve rien", bas)
        commentaires = [l for l in self.texte.splitlines() if l.startswith("#")]
        self.assertTrue(any("roue macOS que pour macOS 13 et plus" in l for l in commentaires),
                        "la ligne de la limite (roue macOS seulement pour macOS 13 et plus) n'est pas ecrite")
        self.assertTrue(any("minos" in l for l in commentaires),
                        "la limite pour l'application embarquee (minos 13.0.0) n'est pas ecrite")
        self.assertTrue(any("sdist" in l for l in commentaires), "le sdist n'est pas mentionne")
        self.assertIn("macOS 11 et 12", self.texte)

    def test_commentaire_nomme_la_version_retiree(self):
        """Le commentaire de pypdfium2 ne presente plus la 5.15.1 comme retenue : il dit qu'elle est retiree."""
        commentaires = "\n".join(l for l in self.texte.splitlines() if l.startswith("#"))
        self.assertNotIn("5.15.2 existe, non retenue", commentaires)
        self.assertIn("5.15.1", commentaires)
        self.assertIn("retiree", commentaires)


class Spec(unittest.TestCase):
    """MoodleSync.spec : ce que PyInstaller doit voir. Les imports a l'usage de ocr.py (pypdfium2, PIL) sont
    suivis sans declaration (ecart 267, mesure) ; le certifi de macOS et pypdf restent declares."""

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

    def _excludes(self):
        for noeud in ast.walk(self.arbre):
            if isinstance(noeud, ast.Call) and getattr(noeud.func, "id", "") == "Analysis":
                for mot in noeud.keywords:
                    if mot.arg == "excludes":
                        return ast.literal_eval(mot.value)
        self.fail("Analysis(..., excludes=...) introuvable dans le spec")

    def test_imports_a_l_usage_non_declares(self):
        """Ecart 267 : PyInstaller suit les imports ecrits dans les fonctions (mesure : deux compilations,
        avec et sans les hiddenimports de P1, ont donne les memes 366 fichiers). pypdfium2, PIL et leurs
        modules n'ont donc rien a faire dans hiddenimports ; ils entrent par requirements.txt et leur hook."""
        noms = self._hiddenimports()
        for nom in ("pypdfium2", "pypdfium2_raw"):
            self.assertNotIn(nom, noms)
        self.assertEqual([n for n in noms if n == "PIL" or n.startswith("PIL.")], [])

    def test_imports_a_l_usage_suivis_par_pyinstaller(self):
        """Ce qui rend ces imports visibles : collect_submodules("moodlesync") fait analyser ocr.py, qui
        importe pypdfium2 et PIL dans des fonctions."""
        self.assertIn("moodlesync", self._hiddenimports())
        importes = set()
        for fonction in ast.walk(ast.parse(lire("moodlesync/ocr.py"))):
            if isinstance(fonction, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(fonction):
                    if isinstance(n, ast.Import):
                        importes.update(a.name.split(".")[0] for a in n.names)
                    elif isinstance(n, ast.ImportFrom) and n.module:
                        importes.add(n.module.split(".")[0])
        self.assertIn("pypdfium2", importes)
        self.assertIn("PIL", importes)

    def test_commentaire_du_spec_exact(self):
        """Ecart 267 : l'ancien commentaire disait que PyInstaller ne voit pas ces imports ; c'est faux."""
        self.assertNotIn("PyInstaller ne les voit pas", self.texte)
        self.assertIn("suit les imports", self.texte)
        self.assertIn("requirements.txt", self.texte)

    def test_excludes_ne_retire_ni_pil_ni_pypdfium2(self):
        """Ecart 268 (M27) : excludes=["tests", "PIL", "pypdfium2"] passait. Seul tests est exclu."""
        self.assertEqual(self._excludes(), ["tests"])

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
    """Aucun fichier touche par la tache ne porte de tiret long ni de CRLF (travail en LF)."""

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

    def test_lignes_de_requirements_testes(self):
        """Ecart 268 (M16, M17, M18) : les lignes elles-memes, pas seulement les mots du commentaire."""
        testes = lire("requirements-testes.txt")
        self.assertRegex(testes, r"(?m)^-r requirements-compilation\.txt\s*$")
        self.assertEqual(exigence(testes, "pillow")[0], PILLOW)
        self.assertEqual(exigence(testes, "pillow")[0], exigence(lire("requirements.txt"), "pillow")[0])

    def test_pillow_de_compilation_suit_requirements(self):
        """La ligne pillow de requirements-compilation.txt (conversion de l'icone sous macOS) a la meme
        version que celle du produit."""
        self.assertEqual(exigence(lire("requirements-compilation.txt"), "pillow")[0], PILLOW)


class Gitattributes(unittest.TestCase):
    """Ecart 265 : sans .gitattributes, l'arbre de travail d'un poste Windows en autocrlf porte du CRLF et
    les gardes de fins de ligne echouent. Le fichier force LF."""

    def setUp(self):
        self.regles = {}
        for ligne in lire(".gitattributes").splitlines():
            ligne = ligne.split("#")[0].strip()
            if ligne:
                motif, *attributs = ligne.split()
                self.regles[motif] = attributs

    def test_lf_force_pour_tout_texte(self):
        self.assertEqual(self.regles.get("*"), ["text=auto", "eol=lf"])

    def test_code_et_documentation_en_lf(self):
        for motif in ("*.py", "*.md", "*.txt", "*.js", "*.css", "*.html", "*.yml", "*.spec", "*.ics"):
            with self.subTest(motif=motif):
                self.assertIn("eol=lf", self.regles.get(motif, []))
                self.assertIn("text", self.regles.get(motif, []))

    def test_binaires(self):
        for motif in ("*.png", "*.ico", "*.icns", "*.zip"):
            with self.subTest(motif=motif):
                self.assertEqual(self.regles.get(motif), ["binary"])


if __name__ == "__main__":
    unittest.main()
