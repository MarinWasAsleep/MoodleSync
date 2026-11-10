"""Tests de la coquille de l'onglet Mes textes (tache U1) : index.html et style.css.

Aucun acces reseau, aucun navigateur, aucune fenetre : les deux fichiers sont lus sur le disque et
analyses par html.parser. Les textes attendus sont ceux du plan 3.5 et 3.6 et du contrat 3.4, mot
pour mot ; les blancs sont replies en une espace avant comparaison, rien d'autre n'est normalise.

Le nombre de documents, de pages et de volume de l'en-tete est rempli par la page (U2) : la coquille
ne porte que les mots fixes des deux phrases du plan 3.5.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, re, sys, unittest
from html.parser import HTMLParser

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
INTERFACE = os.path.join(RACINE, "moodlesync", "interface")

# Contrat 3.4 : les quatorze identifiants du panneau, plus la pastille de l'onglet.
IDENTIFIANTS = ("tx-entete", "tx-recherche", "tx-resultats", "tx-liste", "tx-vide", "tx-copier-cours",
                "tx-exporter", "tx-ouvrir-dossier", "tx-qualite", "tx-carte", "tx-preparer", "tx-plus-tard",
                "tx-quoi", "tx-reglages", "tx-badge")
DIALOGUES = ("d-tx-preparer", "d-tx-quoi", "d-tx-qualite")

# Contrat 5 : mots a eviter dans l'interface principale.
INTERDITS = ("ocr", "tesseract", "tessdata", "dpi", "segmentation", "psm", "tsv")

# Plan 3.5, en-tete : les mots fixes des deux phrases (les nombres sont remplis par la page).
ENTETE = ("de texte.", "lisibles", "à vérifier.",
          "Tout est sur cet ordinateur. Aucun document n'a été envoyé à une IA.")

# Plan 3.5, etat vide.
VIDE = ("Aucun texte extrait pour l'instant.",
        "MoodleSync peut extraire le texte de tes scans et de tes PDF, sur ton ordinateur. Une seule fois, "
        "puis tu pourras les chercher et les coller dans l'IA de ton choix.",
        "Préparer mes cours")

# Plan 3.6, niveau 1 : les deux phrases de la carte.
CARTE = ("Un PDF scanné, c'est une photo de texte. On peut le lire, mais pas le chercher, ni le copier "
         "proprement, ni le donner à une IA sans renvoyer l'image à chaque fois.",
         "MoodleSync le transforme en texte, une fois, sur ton ordinateur. Ensuite tu peux chercher, copier et citer.")

# Plan 3.1 : les libelles de la carte.
CARTE_LIBELLES = {"tx-preparer": "Préparer", "tx-plus-tard": "Plus tard",
                  "tx-quoi": "À quoi ça sert ?", "tx-reglages": "Réglages de l'extraction"}


def lire(nom):
    with open(os.path.join(INTERFACE, nom), encoding="utf-8") as f:
        return f.read()


def plat(texte):
    """Blancs replies en une espace, pour comparer une phrase ecrite sur plusieurs lignes."""
    return " ".join(texte.split())


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


def attributs(e):
    return " ".join(v or "" for v in e["attrs"].values())


def contenu(e):
    """Texte et valeurs d'attributs d'un sous-arbre, pour y chercher un mot interdit."""
    return texte(e) + " " + " ".join(attributs(f) for f in elements(e))


class Coquille(unittest.TestCase):
    """index.html : onglet, panneau, identifiants, etat vide, carte, dialogues."""

    @classmethod
    def setUpClass(cls):
        cls.page = lire("index.html")
        cls.feuille = lire("style.css")
        cls.arbre = Arbre()
        cls.arbre.feed(cls.page)
        cls.arbre.close()

    def par_id(self, ident):
        trouves = [e for e in elements(self.arbre.racine) if e["attrs"].get("id") == ident]
        self.assertEqual(len(trouves), 1, "identifiant #%s absent ou repete (%d)" % (ident, len(trouves)))
        return trouves[0]

    # ------------------------------------------------------------------ onglet
    def test_onglet(self):
        o = self.par_id("o-textes")
        self.assertEqual(o["nom"], "button")
        self.assertEqual(o["attrs"].get("role"), "tab")
        self.assertEqual(o["attrs"].get("data-onglet"), "textes")
        self.assertEqual(o["attrs"].get("aria-controls"), "v-textes")
        self.assertEqual(o["attrs"].get("aria-selected"), "false")
        self.assertEqual(o["attrs"].get("tabindex"), "-1")
        self.assertIn("Mes textes", plat(texte(o)))
        icones = {f["attrs"].get("href") for f in elements(o) if f["nom"] == "use"}
        self.assertTrue(icones & {"#i-fichier", "#i-lecture"}, "icone du jeu existant attendue : %s" % icones)
        onglets = self.par_id("onglets")
        self.assertIn(o, list(elements(onglets)), "l'onglet doit etre dans #onglets")

    def test_pastille_dans_l_onglet(self):
        o = self.par_id("o-textes")
        self.assertIn(self.par_id("tx-badge"), list(elements(o)))

    def test_onglets_existants_intacts(self):
        for x in ("sync", "semaine"):
            self.assertEqual(self.par_id("o-" + x)["attrs"].get("aria-controls"), "v-" + x)
        self.assertIsNotNone(self.par_id("actions-sync"))
        self.assertIsNotNone(self.par_id("actions-semaine"))

    # ------------------------------------------------------------------ panneau
    def test_panneau(self):
        p = self.par_id("v-textes")
        self.assertEqual(p["nom"], "section")
        self.assertEqual(p["attrs"].get("role"), "tabpanel")
        self.assertEqual(p["attrs"].get("aria-labelledby"), "o-textes")
        self.assertIn("hidden", p["attrs"], "le panneau doit etre masque au depart")

    def test_aucun_mot_technique_dans_le_panneau(self):
        bloc = contenu(self.par_id("v-textes")).lower()
        for mot in INTERDITS:
            with self.subTest(mot=mot):
                self.assertNotIn(mot, bloc)

    def test_identifiants_du_contrat(self):
        ids = [e["attrs"]["id"] for e in elements(self.arbre.racine) if "id" in e["attrs"]]
        for ident in IDENTIFIANTS:
            with self.subTest(ident=ident):
                self.assertEqual(ids.count(ident), 1)
        self.assertEqual(sorted(i for i in ids if i.startswith("tx-")), sorted(IDENTIFIANTS))
        self.assertEqual(sorted(i for i in ids if i.startswith("d-tx-")), sorted(DIALOGUES))

    # ------------------------------------------------------------------ en-tete, recherche, liste
    def test_entete(self):
        t = plat(texte(self.par_id("tx-entete")))
        for x in ENTETE:
            with self.subTest(texte=x):
                self.assertIn(x, t)
        ids = [e["attrs"]["id"] for e in elements(self.par_id("tx-entete")) if "id" in e["attrs"]]
        self.assertEqual(ids, ["tx-entete"], "aucun identifiant nouveau dans l'en-tete : %s" % ids)

    def test_recherche(self):
        c = self.par_id("tx-recherche")
        self.assertEqual(c["nom"], "input")
        self.assertEqual(c["attrs"].get("type"), "search")
        labels = [e for e in elements(self.arbre.racine)
                  if e["nom"] == "label" and e["attrs"].get("for") == "tx-recherche"]
        self.assertEqual(len(labels), 1, "un label associe au champ de recherche")
        self.assertTrue(plat(texte(labels[0])), "le label du champ de recherche porte un texte")
        self.assertIsNotNone(self.par_id("tx-resultats"))

    def test_liste_vide(self):
        liste = self.par_id("tx-liste")
        self.assertEqual(liste["enfants"], [], "la liste est remplie par U2 : aucun modele de ligne")
        self.assertEqual(plat(texte(liste)), "")

    def test_actions_principales(self):
        for ident, libelle in (("tx-copier-cours", "Copier le contexte du cours"), ("tx-exporter", "Exporter"),
                              ("tx-ouvrir-dossier", "Ouvrir le dossier des textes"), ("tx-qualite", "Voir la qualité")):
            with self.subTest(bouton=ident):
                b = self.par_id(ident)
                self.assertEqual(b["nom"], "button")
                self.assertIn(libelle, plat(texte(b)))

    # ------------------------------------------------------------------ etat vide
    def test_etat_vide(self):
        v = self.par_id("tx-vide")
        t = plat(texte(v))
        for x in VIDE:
            with self.subTest(texte=x):
                self.assertIn(x, t)

    def test_bouton_de_l_etat_vide(self):
        v = self.par_id("tx-vide")
        boutons = [e for e in elements(v) if e["nom"] == "button" and e["attrs"].get("data-action") == "preparer"]
        self.assertEqual(len(boutons), 1, "un bouton data-action=\"preparer\" dans l'etat vide")
        b = boutons[0]
        self.assertNotIn("id", b["attrs"], "le contrat ne fixe pas d'identifiant pour ce bouton")
        self.assertEqual(plat(texte(b)), "Préparer mes cours")

    # ------------------------------------------------------------------ carte
    def test_carte(self):
        c = self.par_id("tx-carte")
        t = plat(texte(c))
        for x in CARTE:
            with self.subTest(texte=x):
                self.assertIn(x, t)
        for ident, libelle in CARTE_LIBELLES.items():
            with self.subTest(element=ident):
                e = self.par_id(ident)
                self.assertIn(e, list(elements(c)), "#%s doit etre dans la carte" % ident)
                self.assertIn(libelle, plat(texte(e)))

    # ------------------------------------------------------------------ dialogues
    def test_dialogues(self):
        for ident in DIALOGUES:
            with self.subTest(dialogue=ident):
                d = self.par_id(ident)
                self.assertEqual(d["nom"], "dialog")
                self.assertIn("dialogue", (d["attrs"].get("class") or "").split())
                titres = [e for e in elements(d) if e["nom"] == "h3" and plat(texte(e))]
                self.assertEqual(len(titres), 1, "un titre dans le dialogue")
                fermetures = [e for e in elements(d) if e["nom"] == "button" and "data-ferme" in e["attrs"]]
                self.assertTrue(fermetures, "un bouton de fermeture (data-ferme) dans le dialogue")

    def test_dialogue_quoi_est_large(self):
        d = self.par_id("d-tx-quoi")
        self.assertIn("large", (d["attrs"].get("class") or "").split())

    # ------------------------------------------------------------------ feuille et forme
    def test_badges_de_qualite(self):
        for selecteur in (".badge-qualite", ".badge-qualite.bon", ".badge-qualite.a-verifier",
                          ".badge-qualite.difficile", ".badge-qualite.cherchable"):
            with self.subTest(selecteur=selecteur):
                self.assertTrue(selecteur in self.feuille, "selecteur absent de style.css : %s" % selecteur)
        for variable in ("var(--bon", "var(--alerte", "var(--critique"):
            with self.subTest(variable=variable):
                self.assertTrue(variable in self.feuille, "variable absente de style.css : %s" % variable)

    def test_styles_de_l_onglet(self):
        for selecteur in ("#tx-badge", ".tx-vide", ".tx-liste", ".tx-carte", ".tx-actions"):
            with self.subTest(selecteur=selecteur):
                self.assertTrue(selecteur in self.feuille, "selecteur absent de style.css : %s" % selecteur)

    # ------------------------------------------------------------------ barre de preparation
    def test_barre_de_preparation(self):
        """La barre de l'onglet : un bloc muet au depart, rempli par textes.js."""
        p = self.par_id("v-textes")
        blocs = [e for e in elements(p) if "tx-travail" in (e["attrs"].get("class") or "").split()]
        self.assertEqual(len(blocs), 1, "un bloc .tx-travail dans le panneau")
        b = blocs[0]
        self.assertEqual(b["nom"], "div")
        self.assertEqual(b["attrs"].get("role"), "status")
        self.assertEqual(b["attrs"].get("aria-live"), "polite")
        self.assertIn("hidden", b["attrs"], "masque tant que rien ne travaille")
        barres = [e for e in elements(b) if e["nom"] == "progress"]
        self.assertEqual(len(barres), 1, "une barre <progress>")
        self.assertEqual(barres[0]["attrs"].get("max"), "100")
        self.assertTrue(barres[0]["attrs"].get("aria-label"), "la barre a un nom accessible")
        ids = [e["attrs"]["id"] for e in elements(b) if "id" in e["attrs"]]
        self.assertEqual(ids, [], "aucun identifiant nouveau : le contrat 3.4 les fixe")
        for classe in ("tx-travail-document", "tx-travail-pct", "tx-travail-detail", "tx-travail-pause"):
            with self.subTest(classe=classe):
                self.assertTrue(any(classe in (e["attrs"].get("class") or "").split() for e in elements(b)),
                                "classe absente du bloc : %s" % classe)
        self.assertIn(".tx-travail", self.feuille, "le bloc a une regle dans style.css")

    def test_aucune_ressource_externe(self):
        self.assertNotRegex(self.feuille, r"url\(\s*['\"]?https?:")
        self.assertNotIn("http://", self.feuille)
        self.assertNotIn("https://", self.feuille)
        # index.html porte trois adresses d'exemple ecrites avant U1 (lignes 81, 82 et 116) : aucune
        # ressource chargee, ni src, ni href, ni url().
        self.assertNotRegex(self.page, r"(src|href)=\"https?:")
        self.assertNotRegex(self.page, r"url\(\s*['\"]?https?:")
        self.assertNotRegex(self.page, r"@import")

    def test_ni_tiret_long_ni_cadratin(self):
        for nom, t in (("index.html", self.page), ("style.css", self.feuille)):
            with self.subTest(fichier=nom):
                self.assertNotIn(chr(0x2013), t)
                self.assertNotIn(chr(0x2014), t)


if __name__ == "__main__":
    unittest.main()
