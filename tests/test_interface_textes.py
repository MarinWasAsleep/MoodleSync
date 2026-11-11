"""Tests de la coquille de « Mes textes » dans index.html (tache R7, contrat 5.1 et 5.2).

Aucun acces reseau, aucun navigateur, aucune fenetre : le fichier est lu sur le disque et analyse
par html.parser. Ces tests verifient ce que la page doit porter pour que la coque et les trois vues
s'y branchent : les identifiants du contrat 5.2, les trois sous-onglets et leurs panneaux, la barre
de travail, la carte du moteur, les `<script>` et `<link>` du contrat 5.1, et la disparition de
l'ancien onglet (recherche, export, qualite, panneau « A quoi ça sert ? »).

Ce que ces tests ne mesurent pas : le rendu, le comportement des sous-onglets (tests/test_textes_js.py)
et l'arborescence (tests/test_arbre_js.py), ni aucun navigateur.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, re, sys, unittest
from html.parser import HTMLParser

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
INTERFACE = os.path.join(RACINE, "moodlesync", "interface")

# Contrat 5.2 : les elements fixes de #v-textes.
IDENTIFIANTS = ("tx-intro", "tx-moteur", "tx-travail", "tx-onglets",
                "tx-o-cours", "tx-o-choisir", "tx-o-deposer",
                "tx-v-cours", "tx-v-choisir", "tx-v-deposer")

# Identifiants de l'ancien onglet, retires avec lui (U6, O8).
RETIRES = ("tx-entete", "tx-recherche", "tx-resultats", "tx-liste", "tx-vide", "tx-copier-cours",
           "tx-exporter", "tx-ouvrir-dossier", "tx-qualite", "d-tx-quoi", "d-tx-qualite")

# Ce que R11 touche : la carte de Ma semaine, son renvoi et l'onglet.
INTACTS = ("tx-carte", "tx-choisir-quoi", "o-textes", "v-textes", "tx-badge")

# Contrat 5 : mots a eviter dans l'onglet.
INTERDITS = ("ocr", "tesseract", "tessdata", "dpi", "segmentation", "psm", "tsv")

SCRIPTS = ("commun.js", "semaine.js", "sync.js", "horaire.js", "textes-arbre.js", "textes-cours.js",
           "textes-choisir.js", "textes-deposer.js", "textes.js", "app.js")
FEUILLES = ("style.css", "horaire.css", "textes-cours.css", "textes-choisir.css", "textes-deposer.css")


class Arbre(HTMLParser):
    """Arbre minimal : chaque element garde son nom, ses attributs, son texte direct et ses enfants."""

    VIDES = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
             "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.racine = {"nom": "#document", "attrs": {}, "texte": "", "enfants": []}
        self.pile = [self.racine]

    def handle_starttag(self, tag, attrs):
        e = {"nom": tag, "attrs": dict(attrs), "texte": "", "enfants": []}
        self.pile[-1]["enfants"].append(e)
        if tag not in self.VIDES:
            self.pile.append(e)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VIDES:
            self.pile.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.pile) - 1, 0, -1):
            if self.pile[i]["nom"] == tag:
                del self.pile[i:]
                return

    def handle_data(self, data):
        self.pile[-1]["texte"] += data


def elements(e):
    yield e
    for f in e["enfants"]:
        yield from elements(f)


def texte(e):
    return e["texte"] + "".join(texte(f) for f in e["enfants"])


def plat(t):
    return " ".join(t.split())


def attributs(e):
    return " ".join(v or "" for v in e["attrs"].values())


def contenu(e):
    """Texte et valeurs d'attributs d'un sous-arbre, pour y chercher un mot interdit."""
    return texte(e) + " " + " ".join(attributs(f) for f in elements(e))


class Coquille(unittest.TestCase):
    """index.html : ce que la coque de Mes textes trouve, et ce qui a disparu."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(INTERFACE, "index.html"), encoding="utf-8") as f:
            cls.page = f.read()
        cls.arbre = Arbre()
        cls.arbre.feed(cls.page)
        cls.arbre.close()

    def par_id(self, ident):
        trouves = [e for e in elements(self.arbre.racine) if e["attrs"].get("id") == ident]
        self.assertEqual(len(trouves), 1, "identifiant #%s absent ou repete (%d)" % (ident, len(trouves)))
        return trouves[0]

    # ------------------------------------------------------------------ onglet et panneau
    def test_onglet_mes_textes(self):
        o = self.par_id("o-textes")
        self.assertEqual(o["nom"], "button")
        self.assertEqual(o["attrs"].get("role"), "tab")
        self.assertEqual(o["attrs"].get("aria-controls"), "v-textes")
        self.assertIn("Mes textes", plat(texte(o)))
        self.assertIn(self.par_id("tx-badge"), list(elements(o)), "la pastille reste dans l'onglet")
        self.assertIn(o, list(elements(self.par_id("onglets"))), "l'onglet reste dans #onglets")

    def test_panneau_mes_textes(self):
        p = self.par_id("v-textes")
        self.assertEqual(p["nom"], "section")
        self.assertEqual(p["attrs"].get("role"), "tabpanel")
        self.assertEqual(p["attrs"].get("aria-labelledby"), "o-textes")
        self.assertIn("hidden", p["attrs"], "le panneau est masque au depart")

    def test_identifiants_du_contrat(self):
        ids = [e["attrs"]["id"] for e in elements(self.arbre.racine) if "id" in e["attrs"]]
        for ident in IDENTIFIANTS + INTACTS:
            with self.subTest(ident=ident):
                self.assertEqual(ids.count(ident), 1, "#%s doit exister une seule fois" % ident)

    def test_aucun_identifiant_de_l_ancien_onglet(self):
        ids = [e["attrs"]["id"] for e in elements(self.arbre.racine) if "id" in e["attrs"]]
        for ident in RETIRES:
            with self.subTest(ident=ident):
                self.assertEqual(ids.count(ident), 0, "#%s devait disparaitre avec l'ancien onglet" % ident)

    # ------------------------------------------------------------------ sous-onglets
    def test_trois_sous_onglets(self):
        barre = self.par_id("tx-onglets")
        self.assertEqual(barre["attrs"].get("role"), "tablist")
        self.assertTrue(plat(barre["attrs"].get("aria-label") or ""), "la barre a un nom accessible")
        onglets = [e for e in elements(barre) if e["nom"] == "button"]
        self.assertEqual(len(onglets), 3, "trois sous-onglets")
        attendus = [("tx-o-cours", "tx-v-cours", "true", "0"),
                    ("tx-o-choisir", "tx-v-choisir", "false", "-1"),
                    ("tx-o-deposer", "tx-v-deposer", "false", "-1")]
        for (ident, panneau, selectionne, ordre), onglet in zip(attendus, onglets):
            with self.subTest(onglet=ident):
                self.assertEqual(onglet["attrs"].get("id"), ident)
                self.assertEqual(onglet["attrs"].get("role"), "tab")
                self.assertEqual(onglet["attrs"].get("aria-controls"), panneau)
                self.assertEqual(onglet["attrs"].get("aria-selected"), selectionne)
                self.assertEqual(onglet["attrs"].get("tabindex"), ordre)
                self.assertTrue(onglet["attrs"].get("data-vue"), "la coque lit data-vue")

    def test_trois_panneaux(self):
        for ident, onglet, masque in (("tx-v-cours", "tx-o-cours", False),
                                      ("tx-v-choisir", "tx-o-choisir", True),
                                      ("tx-v-deposer", "tx-o-deposer", True)):
            with self.subTest(panneau=ident):
                p = self.par_id(ident)
                self.assertEqual(p["attrs"].get("role"), "tabpanel")
                self.assertEqual(p["attrs"].get("aria-labelledby"), onglet)
                self.assertEqual("hidden" in p["attrs"], masque, "un seul panneau visible au depart")
                self.assertEqual(p["enfants"], [], "les vues remplissent leur conteneur, pas la page")

    # ------------------------------------------------------------------ phrase, carte, barre
    def test_phrase_d_introduction(self):
        intro = self.par_id("tx-intro")
        self.assertEqual(intro["nom"], "p")
        self.assertEqual(intro["enfants"], [], "la phrase vient de TX_MOTS, pas de la page")

    def test_carte_du_moteur(self):
        carte = self.par_id("tx-moteur")
        self.assertEqual(carte["nom"], "section")
        self.assertIn("hidden", carte["attrs"], "masquee tant que le moteur est la")
        actions = {}
        for e in elements(carte):
            if e["nom"] == "button" and e["attrs"].get("data-action"):
                actions[e["attrs"]["data-action"]] = plat(texte(e))
        self.assertIn("installer", actions)
        self.assertIn("installer-annuler", actions)
        self.assertIn("exe", actions)
        self.assertEqual(actions["installer"], "Installer")
        self.assertEqual(actions["installer-annuler"], "Annuler")
        self.assertEqual(actions["exe"], "Indiquer l'emplacement")
        barres = [e for e in elements(carte) if e["nom"] == "progress"]
        self.assertEqual(len(barres), 1, "une barre d'installation")
        self.assertEqual(barres[0]["attrs"].get("max"), "100")
        self.assertIn(carte, list(elements(self.par_id("v-textes"))), "la carte est dans l'onglet")

    def test_barre_de_travail(self):
        bloc = self.par_id("tx-travail")
        self.assertEqual(bloc["nom"], "div")
        self.assertEqual(bloc["attrs"].get("role"), "status")
        self.assertEqual(bloc["attrs"].get("aria-live"), "polite")
        self.assertIn("hidden", bloc["attrs"], "masquee tant que rien ne travaille")
        barres = [e for e in elements(bloc) if e["nom"] == "progress"]
        self.assertEqual(len(barres), 1, "une seule barre")
        self.assertEqual(barres[0]["attrs"].get("max"), "100")
        self.assertTrue(barres[0]["attrs"].get("aria-label"), "la barre a un nom accessible")
        for classe in ("tx-travail-document", "tx-travail-pct"):
            with self.subTest(classe=classe):
                self.assertTrue(any(classe in (e["attrs"].get("class") or "").split() for e in elements(bloc)),
                                "classe absente du bloc : %s" % classe)
        self.assertIn("tx-travail-barre", bloc and (barres[0]["attrs"].get("class") or ""))

    def test_pause_reprendre_et_arreter(self):
        bloc = self.par_id("tx-travail")
        libelles = {}
        for e in elements(bloc):
            if e["nom"] == "button" and e["attrs"].get("data-action"):
                libelles[e["attrs"]["data-action"]] = plat(texte(e))
        self.assertEqual(libelles.get("pause"), "Pause")
        self.assertEqual(libelles.get("arreter"), "Arrêter")
        self.assertEqual(libelles.get("reprendre"), "Reprendre",
                         "le contrat 5.2 donne une reprise dans la barre (ecart E-V5-2)")
        self.assertIn("hidden", [e for e in elements(bloc) if e["attrs"].get("data-action") == "reprendre"][0]["attrs"],
                      "Reprendre n'apparait qu'en pause : masque au depart")

    # ------------------------------------------------------------------ mots et forme
    def test_aucun_mot_technique_dans_l_onglet(self):
        bloc = contenu(self.par_id("v-textes")).lower()
        for mot in INTERDITS:
            with self.subTest(mot=mot):
                self.assertNotIn(mot, bloc)

    def test_la_carte_de_ma_semaine_reste_intacte(self):
        carte = self.par_id("tx-carte")
        self.assertIn(carte, list(elements(self.par_id("v-semaine"))), "#tx-carte est a R11")
        # R11 (O9) remplace « Preparer » par un renvoi vers « Choisir quoi traiter » et retire le
        # dialogue de consentement : la carte reste, son contenu change.
        self.assertIn(self.par_id("tx-choisir-quoi"),
                      [e for e in elements(self.arbre.racine) if e["attrs"].get("id") == "tx-choisir-quoi"],
                      "#tx-choisir-quoi est le renvoi de la carte")
        self.assertEqual([e for e in elements(self.arbre.racine) if e["attrs"].get("id") == "d-tx-preparer"],
                         [], "le dialogue de consentement est retire par R11")

    def test_scripts_et_feuilles(self):
        scripts = re.findall(r'<script src="([^"]+)"></script>', self.page)
        feuilles = re.findall(r'<link rel="stylesheet" href="([^"]+)">', self.page)
        self.assertEqual(scripts, list(SCRIPTS), "l'ordre du contrat 5.1 : l'arbre et les vues avant la coque")
        self.assertEqual(feuilles, list(FEUILLES))
        for nom in SCRIPTS[4:] + FEUILLES[2:]:
            with self.subTest(fichier=nom):
                self.assertTrue(os.path.isfile(os.path.join(INTERFACE, nom)), "fichier absent : %s" % nom)

    def test_aucune_ressource_externe(self):
        self.assertNotRegex(self.page, r'(src|href)="https?://')
        self.assertNotRegex(self.page, r"url\(\s*['\"]?https?://")
        self.assertNotRegex(self.page, r"@import")

    def test_ni_tiret_long_ni_cadratin(self):
        for tiret in (chr(0x2013), chr(0x2014)):
            self.assertNotIn(tiret, self.page)

    def test_fichier_en_lf(self):
        for chemin in (os.path.join(INTERFACE, "index.html"), os.path.abspath(__file__)):
            with self.subTest(fichier=os.path.basename(chemin)):
                with open(chemin, "rb") as f:
                    self.assertNotIn(b"\r", f.read())


if __name__ == "__main__":
    unittest.main()
