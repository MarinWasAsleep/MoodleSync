"""Outils partages des tests d'interface, et garde des deux panneaux retires (tache R7).

Le panneau « A quoi ça sert ? » (#d-tx-quoi) et le dialogue de qualite (#d-tx-qualite) ont disparu
avec l'ancien onglet (decision U6 et O8, contrat 5.2) : leurs tests sont retires, et ce fichier ne
garde plus que ce que les autres modules d'interface lui empruntent depuis le debut, a savoir le
lecteur HTML qui range la vraie page d'index.html dans le DOM factice (OUTILS), texte_de et corps_de.

OUTILS vient desormais de tests/test_textes_js.py (PAGE) : un seul lecteur de page pour tous les
parcours, celui de la coque. tests/test_preparer_js.py et tests/test_accessibilite_js.py continuent de
l'appeler ici.

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, re, shutil, subprocess, sys, tempfile, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests import test_textes_js as tj

INTERFACE = tj.INTERFACE
DOCS = tj.DOCS
INTERDITS = tj.INTERDITS
HTML_CONSTRUIT = tj.HTML_CONSTRUIT
plat = tj.plat
lire = tj.lire

# Le lecteur HTML minimal : la vraie page d'index.html est rangee dans le DOM factice.
OUTILS = tj.PAGE


def texte_de(html):
    """Texte visible d'un fragment : balises retirees sans espace ajoute, blancs replies."""
    sans = re.sub(r"<[^>]+>", "", html)
    sans = sans.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return plat(sans)


def corps_de(source, nom):
    """Corps d'une fonction JS `function nom(...) { ... }` (accolades equilibrees), ou None."""
    m = re.search(r"(?:async\s+)?function\s+%s\s*\(" % re.escape(nom), source)
    if not m:
        return None
    i = source.find("{", m.end())
    profondeur = 0
    for j in range(i, len(source)):
        if source[j] == "{":
            profondeur += 1
        elif source[j] == "}":
            profondeur -= 1
            if profondeur == 0:
                return source[i:j + 1]
    return None


class PanneauxRetires(unittest.TestCase):
    """index.html : les deux panneaux de l'ancien onglet ne sont plus la, et rien ne les ouvre."""

    @classmethod
    def setUpClass(cls):
        cls.page = lire(os.path.join(INTERFACE, "index.html"))
        cls.js = lire(os.path.join(INTERFACE, "textes.js"))

    def test_les_deux_dialogues_sont_retires(self):
        for ident in ("d-tx-quoi", "d-tx-qualite"):
            with self.subTest(dialogue=ident):
                self.assertNotIn('id="%s"' % ident, self.page, "#%s doit avoir disparu (U6, O8)" % ident)

    def test_aucun_code_ne_les_ouvre(self):
        for appel in ("d-tx-quoi", "d-tx-qualite", "txQuoi", "txQualite"):
            with self.subTest(appel=appel):
                self.assertNotIn(appel, tj.sans_commentaires(self.js),
                                 "textes.js ne branche plus le panneau retire : %s" % appel)

    def test_le_lecteur_range_la_vraie_page(self):
        """Garde de l'outil partage : PAGE est bien le lecteur de page de test_textes_js."""
        coupe = tj.ENTETE.find("/* ---- arbre de la page")
        self.assertGreater(coupe, 0)
        self.assertIn("function Hparse(", OUTILS)
        self.assertIn("document.body.appendChild", OUTILS)

    # ------------------------------------------------------------------ parcours sur DOM factice
    @unittest.skipUnless(shutil.which("node"), "node absent : parcours du lecteur de page non execute")
    def test_le_lecteur_range_la_vraie_page_dans_le_dom(self):
        """Le DOM bati depuis index.html : c'est ce dont dependent les trois parcours d'interface."""
        node = shutil.which("node") or "node"
        coupe = tj.ENTETE.find("/* ---- arbre de la page")
        dossier = tempfile.mkdtemp(prefix="parcours-lecteur-")
        script = os.path.join(dossier, "_lecteur.js")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(tj.ENTETE[:coupe] + "\n" + OUTILS + "\n" + VERIF)
            r = subprocess.run([node, script, INTERFACE], capture_output=True, text=True, timeout=180)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        self.assertEqual(r.returncode, 0, "le lecteur a echoue :\n%s\n%s" % (r.stdout, r.stderr))
        self.assertIn("OK", r.stdout)


VERIF = r"""
const exiger = (cond, message) => { if (!cond) throw new assert.AssertionError({ message: message }); };
const $h = s => document.querySelector(s);
exiger($h("#v-textes"), "la page rangee porte #v-textes");
exiger($h("#tx-onglets"), "la page rangee porte la barre des sous-onglets");
assert.strictEqual($h("#tx-onglets").querySelectorAll("[role=tab]").length, 3, "trois sous-onglets ranges");
assert.strictEqual($h("#tx-o-cours").getAttribute("data-vue"), "cours", "les attributs data- sont ranges");
exiger(!$h("#d-tx-quoi") && !$h("#d-tx-qualite"), "les deux panneaux retires ne sont pas dans la page");
console.log("OK");
"""



if __name__ == "__main__":
    unittest.main()
