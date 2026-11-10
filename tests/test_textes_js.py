"""Tests de textes.js (tache U2, corrigee) : phrases, appels, onglets, et parcours sur un DOM factice.

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque. Les phrases d'interface sont relevees dans la seule table TX_MOTS de textes.js, puis
comparees au plan et au contrat mot pour mot (blancs replies en une espace) ; toute phrase qui n'y
est pas doit figurer dans PHRASES_NOUVELLES, pour validation par Maxence.

Le parcours (choisirOnglet, en-tete, liste, recherche avec delai, copie, export, qualite) est
execute par Node sur un DOM minimal ecrit ici : les vraies fonctions de commun.js, textes.js et
app.js sont chargees, et une doublure de l'API remplace Python. Le DOM reprend les classes des
boutons de l'onglet telles qu'index.html les ecrit (elles ne sont pas recopiees a la main), et ses
evenements remontent jusqu'a `document` comme ceux d'un navigateur : c'est ce qui a permis de voir
l'ecart 187, ou les menus de la copie du cours et de l'export se refermaient a l'instant ou ils
s'ouvraient. Le script du parcours est ecrit dans un dossier temporaire, jamais dans l'arbre du
depot, et supprime dans un `finally`. Ce parcours s'ignore quand `node` manque.

Ce que ces tests ne mesurent pas : aucune vraie fenetre pywebview, aucun navigateur, aucun vrai
presse-papiers (la doublure de navigator.clipboard ne fait qu'enregistrer le texte), Windows et
macOS non executes.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, re, shutil, subprocess, sys, tempfile, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
INTERFACE = os.path.join(RACINE, "moodlesync", "interface")
DOCS = os.path.join(RACINE, "docs")

# Contrat 5 : mots a eviter dans l'interface principale (hors noms d'appels et identifiants).
INTERDITS = ("ocr", "tesseract", "tessdata", "dpi", "segmentation", "psm", "tsv")

# Procedes qui construisent du HTML a partir de donnees : aucun n'a sa place dans textes.js.
HTML_CONSTRUIT = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write",
                  "DOMParser", "createContextualFragment")

# Phrases ecrites par U2 que ni le plan ni le contrat ne portent : a valider par Maxence.
# Les `{}` marquent une valeur intercalee (nom, nombre, page).
PHRASES_NOUVELLES = (
    "Restaurer l'original",
    "Restaurer l'original ?",
    "MoodleSync va retélécharger l'original depuis Moodle et remplacer le fichier modifié (le PDF cherchable) par cet original. Il faut être connecté à Moodle.",
    "Original restauré.",
    "Lecture des textes...",
    "Plus d'actions",
    "Refaire ce document ?",
    "Choisis un cours",
    "Aucun cours.",
    "Aucun document à vérifier.",
    "Aucun résultat.",
    "résultat",
    "résultats",
    "Tronqué.",
    "Copié : {} caractères.",
    "Aucun texte à copier.",
    "Copie impossible : sélectionne le texte à la main.",
    "Ce texte est trop long pour le presse-papiers.",
    "Exporté : {} {}.",
    "Ce document s'ouvre depuis ton dossier de rangement.",
    # Mots du contrat 5 (phrase de format_inconnu), capitalises pour un libelle de menu.
    "Archive ZIP",
    "Archive avec le détail page par page",
    "Un fichier de données par page, pour les outils qui citent les sources.",
    "Fichier Markdown",
    # Panneau « A quoi ca sert ? » (U3) : phrases que le plan 3.6 ne porte pas.
    "Exemple, pas un de tes documents.",
    "Des images :",
    "Du texte :",
    "Lecture de la page...",
    "Confiance :",
    "Aucun texte reconnu sur cette page.",
    "Aperçu de la page {} de {}.",
    "Exemple de page scannée.",
    "Une institution est un ensemble de règles qui dure dans le temps.",
    # Carte de preparation et dialogue de consentement (U4).
    "Reprendre l'extraction ({} documents restants)",
    "Reprendre l'extraction ({} document restant)",
    "Page {} sur {}",
    "Document {} sur {}",
    "En pause pendant la synchronisation. Elle reprend à la fin.",
    "Aucun document à préparer.",
    # Duree du premier passage (ecart 212), fourchette de ocr_etat().prevision.
    "Environ {} à {} minutes.",
)

# Garde-fou : hors de la table TX_MOTS, aucune chaine ne doit ressembler a une phrase francaise.
MOTS_FRANCAIS = (
    "le", "la", "les", "un", "une", "des", "du", "de", "ce", "cet", "cette", "mon", "ma", "mes",
    "ton", "ta", "tes", "son", "sa", "ses", "est", "sont", "pas", "pour", "dans", "sur", "avec",
    "aucun", "aucune", "tout", "toute", "tous", "toutes", "rien", "plus", "copier", "ouvrir",
    "refaire", "exporter", "choisis", "choisir", "résultat", "résultats", "trop", "long",
    "caractères", "archive", "fichier",
)

ACCENTS = "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ¿"

BLOC = "const TX_MOTS = {"
LIGNE_MOT = re.compile(r'^\s*([A-Za-z_]\w*):\s*(?:"((?:[^"\\]|\\.)*)"|`([^`]*)`)\s*,\s*$')
CHAINE = re.compile(r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|`([^`]*)`')


def fichier(*morceaux):
    return os.path.join(INTERFACE, *morceaux)


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return f.read()


def plat(texte):
    return " ".join(texte.split())


def sans_commentaires(source):
    """Retire commentaires de bloc et de ligne (les apostrophes des commentaires ne sont pas des chaines)."""
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return re.sub(r"//[^\n]*", " ", source)


def bloc_mots(source):
    """(texte de la table, interieur de la table) ou (None, None)."""
    debut = source.find(BLOC)
    if debut < 0:
        return None, None
    fin = source.find("\n};", debut)
    if fin < 0:
        return None, None
    return source[debut:fin + 3], source[debut + len(BLOC):fin]


def table_mots(source):
    """{cle: phrase normalisee} de TX_MOTS ; echoue si une ligne de la table n'est pas lisible."""
    entete, interieur = bloc_mots(source)
    if interieur is None:
        return {}
    mots = {}
    for ligne in interieur.splitlines():
        if not ligne.strip():
            continue
        m = LIGNE_MOT.match(ligne)
        if not m:
            raise AssertionError("ligne de TX_MOTS non reconnue par le test : %r" % ligne)
        valeur = m.group(2) if m.group(2) is not None else m.group(3)
        mots[m.group(1)] = plat(re.sub(r"\$\{[^}]*\}", "{}", valeur))
    return mots


def phrases_hors_table(source):
    """Chaines litterales ecrites hors de TX_MOTS (commentaires retires)."""
    entete, interieur = bloc_mots(source)
    if entete:
        source = source.replace(entete, " ")
    source = sans_commentaires(source)
    return [a or b or c for a, b, c in CHAINE.findall(source)]


def corpus():
    """Plan et contrat, blancs replies : la reference des phrases d'interface."""
    return " ".join(plat(lire(os.path.join(DOCS, nom))) for nom in ("plan-ocr.md", "ocr-contrat.md"))


class TextesJs(unittest.TestCase):
    """textes.js : forme, appels, phrases, et branchement des trois onglets."""

    @classmethod
    def setUpClass(cls):
        chemin = fichier("textes.js")
        cls.existe = os.path.isfile(chemin)
        cls.source = lire(chemin) if cls.existe else ""
        cls.app = lire(fichier("app.js"))
        cls.page = lire(fichier("index.html"))
        cls.feuille = lire(fichier("style.css"))

    def source_test(self):
        self.assertTrue(self.existe, "moodlesync/interface/textes.js est absent")
        return self.source

    # ------------------------------------------------------------------ fichier et chargement
    def test_fichier_existe_et_finit_par_un_saut_de_ligne(self):
        t = self.source_test()
        self.assertGreater(len(t), 2000, "textes.js est vide ou presque")
        self.assertTrue(t.endswith("\n"))
        self.assertNotIn("\r", t, "textes.js doit etre ecrit en LF")

    def test_charge_avant_app(self):
        balises = re.findall(r'<script src="([^"]+)"></script>', self.page)
        self.assertIn("textes.js", balises, "index.html ne charge pas textes.js")
        self.assertEqual(balises.count("textes.js"), 1, "une seule balise textes.js")
        self.assertLess(balises.index("textes.js"), balises.index("app.js"), "textes.js avant app.js")
        self.assertEqual(balises.index("horaire.js") + 1, balises.index("textes.js"),
                         "textes.js entre horaire.js et app.js")

    def test_fonctions_et_variables_du_contrat(self):
        t = self.source_test()
        for x in ("function txOuvrir(", "window.textesProgres", "window.textesJournal"):
            with self.subTest(element=x):
                self.assertIn(x, t)
        for nom in ("TX", "txPret", "txOccupe"):
            with self.subTest(variable=nom):
                self.assertTrue(re.search(r"(?m)^let %s\b" % nom, t),
                                "variable globale du contrat 3.4 absente : %s" % nom)
        self.assertIn('"textes"', t, "occupations recoit \"textes\" par barreOccupee")
        self.assertIn("barreOccupee(", t)

    def test_onglet_textes_appelle_tx_ouvrir(self):
        self.assertTrue(re.search(r'if \(o === "textes" && typeof txOuvrir === "function"\) txOuvrir\(\);', self.app),
                        "choisirOnglet doit appeler txOuvrir() sur l'onglet textes")

    # ------------------------------------------------------------------ appels a l'API
    def test_appels_api_sont_des_methodes_du_mixin(self):
        from moodlesync.api_textes import ApiTextes
        appels = sorted(set(re.findall(r"api\(\)\.(ocr_\w+)\(", self.source_test())))
        self.assertGreaterEqual(len(appels), 6, "trop peu d'appels d'API : %s" % appels)
        for nom in appels:
            with self.subTest(appel=nom):
                self.assertTrue(callable(getattr(ApiTextes, nom, None)), "ApiTextes.%s n'existe pas" % nom)

    def test_aucun_html_construit(self):
        t = sans_commentaires(self.source_test())
        for procede in HTML_CONSTRUIT:
            with self.subTest(procede=procede):
                self.assertNotIn(procede, t, "aucun HTML construit dans textes.js : %s" % procede)
        self.assertIn("textContent", t)
        self.assertIn("createTextNode", t)

    # ------------------------------------------------------------------ phrases
    def test_phrases_du_plan_ou_declarees(self):
        mots = table_mots(self.source_test())
        self.assertGreaterEqual(len(mots), 15, "table TX_MOTS absente ou trop courte : %s" % sorted(mots))
        reference = corpus()
        for cle, phrase in sorted(mots.items()):
            with self.subTest(cle=cle, phrase=phrase):
                self.assertTrue(phrase in reference or phrase in PHRASES_NOUVELLES,
                                "phrase hors plan, hors contrat et hors PHRASES_NOUVELLES : %r" % phrase)

    def test_libelles_du_plan_presents(self):
        mots = set(table_mots(self.source_test()).values())
        for phrase in ("texte natif", "scanné", "Bon", "À vérifier", "Difficile", "PDF cherchable",
                       "Ouvrir", "Copier le texte", "Refaire", "Copier l'extrait",
                       "Copier le contexte du cours", "Exporter", "Ouvrir le dossier des textes",
                       "Voir la qualité", "page", "documents", "pages", "Mo", "de texte.",
                       "lisible", "lisibles"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, mots)

    def test_aucune_phrase_hors_de_la_table(self):
        for chaine in phrases_hors_table(self.source_test()):
            with self.subTest(chaine=chaine):
                self.assertFalse(set(chaine) & set(ACCENTS), "accent hors de TX_MOTS : %r" % chaine)
                self.assertNotIn("'", chaine, "apostrophe hors de TX_MOTS : %r" % chaine)
                if not re.search(r"\s", chaine):
                    continue                      # un mot seul est un identifiant ou un libelle de la table
                mots = re.findall(r"[A-Za-zÀ-ÿ]+", chaine.lower())
                self.assertFalse([m for m in mots if m in MOTS_FRANCAIS],
                                 "phrase francaise hors de TX_MOTS : %r" % chaine)

    def test_mots_interdits_et_tirets(self):
        t = re.sub(r"ocr_\w+", " ", self.source_test())
        t = re.sub(r"#?[dt]?x-[a-z-]+", " ", t)
        t = re.sub(r"aria-[a-z]+", " ", t)
        bas = t.lower()
        for mot in INTERDITS:
            with self.subTest(mot=mot):
                self.assertNotIn(mot, bas)
        self.assertNotIn(chr(0x2013), self.source_test())
        self.assertNotIn(chr(0x2014), self.source_test())

    # ------------------------------------------------------------------ comportements attendus
    def test_recherche_temporisee_et_jeton(self):
        t = self.source_test()
        self.assertIn("300", t, "le delai de 300 ms de la recherche est ecrit dans textes.js")
        self.assertIn("setTimeout", t)
        self.assertIn("clearTimeout", t)
        self.assertTrue(re.search(r"txJeton", t), "jeton de requete (reponses perimees ignorees)")
        self.assertIn('"input"', t, "le champ de recherche ecoute la saisie")

    def test_etat_vide_et_liste_masques(self):
        t = self.source_test()
        self.assertTrue(re.search(r'\$\("#tx-vide"\)[\s\S]{0,80}\.hidden', t),
                        "l'etat vide doit etre masque quand la liste a des lignes")
        self.assertTrue(re.search(r'\$\("#tx-liste"\)[\s\S]{0,120}\.hidden\s*=\s*true', t),
                        "la liste doit etre masquee pendant la recherche")

    def test_onglets_a_trois(self):
        app = self.app
        self.assertTrue(re.search(r'\["textes",\s*"#o-textes",\s*"#v-textes"\]', app),
                        "les trois onglets sont dans la table de choisirOnglet")
        self.assertTrue(re.search(r'\$\("#actions-sync"\)\.hidden\s*=\s*semaine\s*\|\|\s*textes', app),
                        "#actions-sync doit etre masque sur Ma semaine et sur Mes textes")
        self.assertIn('"Home"', app)
        self.assertIn('"End"', app)
        self.assertIn("placerCurseur", app, "le comportement de Ma semaine ne change pas")
        self.assertIn('choisirOnglet(INFOS.semaine_active ? "semaine" : "sync")', app)

    def test_style_du_bloc_mes_textes(self):
        bloc = self.feuille[self.feuille.rfind("Mes textes"):]
        for selecteur in (".tx-ligne", ".tx-groupe", ".tx-menu", ".tx-trouve", ".tx-extrait mark"):
            with self.subTest(selecteur=selecteur):
                self.assertIn(selecteur, bloc)
        self.assertFalse(re.search(r"#[0-9a-fA-F]{3,8}\b", bloc), "aucune couleur en dur dans le bloc")
        self.assertNotIn("prefers-color-scheme", bloc)
        self.assertNotIn("[data-theme", bloc)
        self.assertNotIn("url(", bloc)

    # ------------------------------------------------------------------ parcours sur DOM factice
    @unittest.skipUnless(shutil.which("node"), "node absent : parcours sur DOM factice non execute")
    def test_parcours_sur_dom_factice(self):
        self.source_test()
        node = shutil.which("node") or "node"
        dossier = tempfile.mkdtemp(prefix="parcours-textes-")
        script = os.path.join(dossier, "_parcours_textes.js")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(ENTETE + "\n")
                for nom in ("commun.js", "textes.js", "app.js"):
                    f.write("\n/* ===== %s ===== */\n" % nom)
                    f.write(lire(fichier(nom)).replace("\r\n", "\n"))
                f.write("\n" + PARCOURS)
            r = subprocess.run([node, script, INTERFACE], capture_output=True, text=True, timeout=180)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        self.assertEqual(r.returncode, 0, "le parcours a echoue :\n%s\n%s" % (r.stdout, r.stderr))
        self.assertIn("OK", r.stdout)


ENTETE = r"""
"use strict";
/* DOM minimal : assez de noeuds, d'attributs et d'evenements pour executer les vraies fonctions
   de l'interface sans navigateur ni dependance. Ecrit par tests/test_textes_js.py. */
const assert = require("assert");
const fs = require("fs");
const path = require("path");

class HNoeud {
  constructor(t) { this.nodeType = t; this.childNodes = []; this.parentNode = null; }
  get nextSibling() { const p = this.parentNode; if (!p) return null;
    const i = p.childNodes.indexOf(this); return i < 0 ? null : (p.childNodes[i + 1] || null); }
}
class HTexte extends HNoeud {
  constructor(t) { super(3); this._t = String(t); }
  get textContent() { return this._t; }
  set textContent(v) { this._t = String(v); }
}
class HElement extends HNoeud {
  constructor(tag) {
    super(1);
    this.tagName = String(tag).toUpperCase();
    this.id = ""; this.hidden = false; this.value = ""; this.disabled = false; this.open = false;
    this.tabIndex = 0; this.style = {}; this.dataset = {}; this._attrs = {}; this._classes = new Set();
    this._texte = ""; this._ecoute = {}; this._inner = "";
  }
  get classList() { const s = this._classes; return {
    add: (...c) => c.forEach(x => s.add(x)), remove: (...c) => c.forEach(x => s.delete(x)),
    contains: c => s.has(c),
    toggle: (c, f) => { const on = f === undefined ? !s.has(c) : !!f; if (on) s.add(c); else s.delete(c); return on; } }; }
  get className() { return [...this._classes].join(" "); }
  set className(v) { this._classes = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get children() { return this.childNodes.filter(n => n.nodeType === 1); }
  get firstChild() { return this.childNodes[0] || null; }
  setAttribute(nom, val) {
    if (nom === "id") this.id = String(val);
    if (nom === "class") this.className = val;
    if (nom === "hidden") this.hidden = true;
    if (nom === "value") this.value = String(val);
    if (nom.startsWith("data-")) this.dataset[nom.slice(5).replace(/-([a-z])/g, (m, c) => c.toUpperCase())] = String(val);
    this._attrs[nom] = String(val);
  }
  getAttribute(nom) {
    if (nom === "id") return this.id || null;
    if (nom === "class") return this._classes.size ? this.className : null;
    if (nom === "hidden") return this.hidden ? "" : null;
    if (nom === "value") return this.value;
    return nom in this._attrs ? this._attrs[nom] : null;
  }
  hasAttribute(nom) { return this.getAttribute(nom) !== null; }
  removeAttribute(nom) { delete this._attrs[nom]; if (nom === "hidden") this.hidden = false; }
  append(...noeuds) { for (const n of noeuds) this.appendChild(n); }
  appendChild(n) { if (typeof n === "string") n = new HTexte(n);
    if (n.parentNode) n.parentNode.removeChild(n); n.parentNode = this; this.childNodes.push(n); return n; }
  insertBefore(n, ref) { const i = ref ? this.childNodes.indexOf(ref) : -1; n.parentNode = this;
    if (i < 0) this.childNodes.push(n); else this.childNodes.splice(i, 0, n); return n; }
  removeChild(n) { const i = this.childNodes.indexOf(n); if (i >= 0) this.childNodes.splice(i, 1);
    n.parentNode = null; return n; }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  get textContent() { return this._texte + this.childNodes.map(n => n.textContent).join(""); }
  set textContent(v) { this.childNodes = []; this._texte = String(v); }
  get innerHTML() { return this._inner; }
  set innerHTML(v) { this._inner = String(v); this.childNodes = []; this._texte = ""; }
  querySelector(sel) { const t = Hselect(this, sel); return t.length ? t[0] : null; }
  querySelectorAll(sel) { return Hselect(this, sel); }
  closest(sel) { let n = this; while (n && n.nodeType === 1) { if (Hsimple(n, sel)) return n; n = n.parentNode; } return null; }
  addEventListener(type, fn) { (this._ecoute[type] = this._ecoute[type] || []).push(fn); }
  removeEventListener(type, fn) { const l = this._ecoute[type]; if (l) { const i = l.indexOf(fn); if (i >= 0) l.splice(i, 1); } }
  /* Un clic remonte de l'element jusqu'a document, comme dans un navigateur : c'est ce que le
     test de U2 ne faisait pas, et c'est ce qui masquait l'ecart 187. */
  dispatchEvent(ev) {
    const evenement = ev || {};
    if (!evenement.type) evenement.type = "";
    if (!evenement.target) evenement.target = this;
    let n = this;
    while (n) {
      const liste = (n._ecoute && n._ecoute[evenement.type]) || [];
      for (const fn of liste.slice()) fn.call(n, evenement);
      n = n.parentNode;
    }
    return true;
  }
  focus() { Hactif = this; }
  select() {}
  showModal() { this.open = true; }
  close() { this.open = false; this.dispatchEvent({ type: "close" }); }
  getBoundingClientRect() { return { left: 0, top: 0, width: 0, height: 0 }; }
}
class HDoc extends HElement {
  constructor() { super("#document"); this.documentElement = new HElement("html");
    this.body = new HElement("body"); this.documentElement.appendChild(this.body); this.appendChild(this.documentElement); }
  createElement(t) { return new HElement(t); }
  createTextNode(t) { return new HTexte(t); }
}
function Hsimple(el, sel) {
  if (!el || el.nodeType !== 1) return false;
  let reste = String(sel).trim();
  const tag = (reste.match(/^[a-zA-Z][a-zA-Z0-9-]*/) || [""])[0];
  if (tag) { if (el.tagName.toLowerCase() !== tag.toLowerCase()) return false; reste = reste.slice(tag.length); }
  while (reste.length) {
    const sorte = reste[0];
    if (sorte === "#" || sorte === ".") {
      const fin = (() => { const s = reste.slice(1).search(/[#.\[]/); return s < 0 ? reste.length : s + 1; })();
      const valeur = reste.slice(1, fin);
      if (sorte === "#" ? el.id !== valeur : !el.classList.contains(valeur)) return false;
      reste = reste.slice(fin);
    } else if (sorte === "[") {
      const fin = reste.indexOf("]");
      if (fin < 0) return false;
      const dedans = reste.slice(1, fin), egal = dedans.indexOf("=");
      if (egal < 0) { if (!el.hasAttribute(dedans)) return false; }
      else {
        const nom = dedans.slice(0, egal), val = dedans.slice(egal + 1).replace(/^"|"$/g, "");
        if (!el.hasAttribute(nom) || el.getAttribute(nom) !== val) return false;
      }
      reste = reste.slice(fin + 1);
    } else return false;
  }
  return true;
}
function Hdescend(racine) {
  const sortie = [], pile = [...racine.childNodes];
  while (pile.length) { const n = pile.shift(); if (n.nodeType === 1) { sortie.push(n); pile.push(...n.childNodes); } }
  return sortie;
}
function Hselect(racine, sel) {
  let courants = [racine];
  for (const partie of String(sel).trim().split(/\s+/)) {
    const suivants = [];
    for (const c of courants) for (const d of Hdescend(c)) if (Hsimple(d, partie) && !suivants.includes(d)) suivants.push(d);
    courants = suivants;
  }
  return courants;
}
const document = new HDoc();
const window = globalThis;
let Hactif = null, HCOPIE = "", HETAT = null, HDOCS = null, HDELAI = 0;
let HREQUETES = [], HCOPIES = [], HEXPORTS = [], HOUVERTURES = [], HLANCES = [];
let HRESTAURATIONS = [], HRESTAURER = () => ({ ok: true, pages: 2 });   // ecart 294 : ocr_pdf_restaurer
let HCOPIE_MODE = "", HEXPORT_ANNULE = false, HCONFIRMATION = false, HTOTAL = null, HTRONQUE = false;
function matchMedia() { return { matches: false, addEventListener() {}, removeEventListener() {} }; }
function requestAnimationFrame(f) { return setTimeout(f, 0); }
function addEventListener() {}
Object.defineProperty(globalThis, "navigator", { configurable: true, writable: true,
  value: { clipboard: { writeText: async t => { HCOPIE = String(t); } } } });
const Hattendre = ms => new Promise(r => setTimeout(r, ms));
let HPORTE = null;                 // portes des reponses de recherche, relachees par le parcours
function Hel(tag, id, cls) { const e = document.createElement(tag); if (id) e.id = id; if (cls) e.className = cls; return e; }

/* Classes des boutons de l'onglet : lues dans index.html, jamais recopiees a la main (ecart 187). */
const HPAGE = fs.readFileSync(path.join(process.argv[2] || ".", "index.html"), "utf8");
function Hclasses(ident) {
  const balise = HPAGE.match(new RegExp("<[a-zA-Z][^>]*\\bid=\"" + ident + "\"[^>]*>"));
  if (!balise) throw new Error("index.html ne porte pas #" + ident);
  const classe = balise[0].match(/class="([^"]*)"/);
  return classe ? classe[1] : "";
}

/* SC : declare par sync.js dans la vraie page ; la doublure reprend sa forme (id, choisi, dossier, nom). */
let SC = [{ id: 7, choisi: true, dossier: "Cours A", nom: "Cours A (S1)" },
          { id: 9, choisi: false, dossier: "Cours B", nom: "Cours B" }];

/* ---- arbre de la page : onglets, actions, panneaux, Mes textes ---- */
const hOnglets = Hel("nav", "onglets");
for (const [nom, ident, texte] of [["sync", "o-sync", "Mes cours"], ["semaine", "o-semaine", "Ma semaine"], ["textes", "o-textes", "Mes textes"]]) {
  const b = Hel("button", ident);
  b.setAttribute("role", "tab"); b.setAttribute("data-onglet", nom); b.setAttribute("aria-controls", "v-" + nom);
  b.setAttribute("aria-selected", nom === "sync" ? "true" : "false");
  b.tabIndex = nom === "sync" ? 0 : -1;
  b.appendChild(document.createTextNode(texte));
  if (nom === "textes") { const p = Hel("span", "tx-badge"); p.hidden = true; b.appendChild(p); }
  hOnglets.appendChild(b);
}
document.body.appendChild(hOnglets);
const hActionsSync = Hel("div", "actions-sync");
const hActionsSemaine = Hel("div", "actions-semaine"); hActionsSemaine.hidden = true;
document.body.append(hActionsSync, hActionsSemaine);
document.body.append(Hel("div", "progres"), Hel("div", "statut-ligne"));
document.body.appendChild(Hel("span", "statut-texte"));
document.body.appendChild(Hel("div", "toasts"));
document.body.appendChild(Hel("div", "voile"));
document.body.appendChild(Hel("aside", "tiroir", "tiroir"));
const hMain = Hel("main", "page"); document.body.appendChild(hMain);
const hVSync = Hel("section", "v-sync");
const hVSemaine = Hel("section", "v-semaine"); hVSemaine.hidden = true;
const hVTextes = Hel("section", "v-textes"); hVTextes.hidden = true;
hMain.append(hVSync, hVSemaine, hVTextes);
const hEntete = Hel("div", "tx-entete", "tx-entete");
hEntete.append(Hel("p", "", "tx-compte"), Hel("p", "", "tx-prive"));
const hBarre = Hel("div", "tx-barre", "tx-barre");
hBarre.appendChild(Hel("input", "tx-recherche", "champ large"));
const hResultats = Hel("p", "tx-resultats", "doux tx-resultats");
const hActions = Hel("div", "", "tx-actions");
const hCopierCours = Hel("button", "tx-copier-cours"); hCopierCours.className = Hclasses("tx-copier-cours");
const hExporter = Hel("button", "tx-exporter"); hExporter.className = Hclasses("tx-exporter");
const hOuvrirDossier = Hel("button", "tx-ouvrir-dossier"); hOuvrirDossier.className = Hclasses("tx-ouvrir-dossier");
const hQualite = Hel("button", "tx-qualite");
hActions.append(hCopierCours, hExporter, hOuvrirDossier, hQualite);
const hListe = Hel("ul", "tx-liste", "tx-liste");
const hVide = Hel("div", "tx-vide", "tx-vide");
hVTextes.append(hEntete, hBarre, hResultats, hActions, hListe, hVide);
const hQualiteDialogue = Hel("dialog", "d-tx-qualite", "dialogue"); document.body.appendChild(hQualiteDialogue);
const hQuestion = Hel("dialog", "d-question", "dialogue");
hQuestion.append(Hel("p", "q-titre"), Hel("p", "q-texte"), Hel("input", "q-champ"),
                 Hel("button", "q-ok"), Hel("button", "q-annuler"));
document.body.appendChild(hQuestion);

/* ---- doublure de l'API : enregistre les appels, repond les formes 2.7 ---- */
const API = {
  ocr_etat: async () => HETAT,
  ocr_documents: async () => HDOCS,
  ocr_chercher: async t => { HREQUETES.push(t); if (HPORTE) await new Promise(r => HPORTE.push(r));
    await Hattendre(HDELAI);
    return { resultats: [{ chemin: "Cours A/S1/a.pdf", cours: "Cours A", section: "S1", nom: t + ".pdf",
      page: 3, segments: [{ t: "avant ", m: false }, { t: t, m: true }, { t: " après", m: false }] }],
      total: HTOTAL === null ? t.length : HTOTAL, tronque: HTRONQUE }; },
  ocr_copier: async p => { HCOPIES.push(p);
    if (HCOPIE_MODE === "vide") return { texte: "", caracteres: 0, documents: 0, pages: 0 };
    if (HCOPIE_MODE === "trop") return { trop_long: true, caracteres: 2100000 };
    return { texte: "texte du document a.pdf", caracteres: 23, documents: 1, pages: 4 }; },
  ocr_exporter: async (p, f) => { HEXPORTS.push([p, f]);
    if (HEXPORT_ANNULE) return { annule: true };
    return { chemin: "hors/x.zip", octets: 1234, documents: 3 }; },
  ocr_ouvrir: async (c, page) => { HOUVERTURES.push([c, page === undefined ? null : page]); return { ok: true }; },
  ocr_pdf_restaurer: async (c, confirme) => { HRESTAURATIONS.push([c, !!confirme]); return HRESTAURER(c, !!confirme); },
  ocr_lancer: async (p, refaire, confirme) => { HLANCES.push([p, refaire, !!confirme]);
    if (HCONFIRMATION && !confirme) return { confirmer: "2 pages, environ 1 minute.", documents: 1, pages: 2 };
    return { file: {} }; },
};
"""

PARCOURS = r"""
/* ---- donnees ---- */
const DOCS = { documents: [
  { chemin: "Cours A/S1/a.pdf", cours: "Cours A", section: "S1", nom: "a.pdf", type: "scanne", pages: 4,
    qualite: "bon", confiance: 0.91, cherchable: false, verifie: false, orphelin: false,
    sortie: "Textes/Cours A/S1/a.pdf.md", date: "2026-11-09" },
  { chemin: "Cours A/S1/b.pdf", cours: "Cours A", section: "S1", nom: "b.pdf", type: "texte", pages: 2,
    qualite: "a_verifier", confiance: 0.62, cherchable: true, verifie: false, orphelin: false,
    sortie: "Textes/Cours A/S1/b.pdf.md", date: "2026-11-09" },
  { chemin: "Cours B/S2/c.pdf", cours: "Cours B", section: "S2", nom: "c<d>.pdf", type: "mixte", pages: 3,
    qualite: "difficile", confiance: 0.4, cherchable: false, verifie: false, orphelin: false,
    sortie: "Textes/Cours B/S2/c.pdf.md", date: "2026-11-09" } ], total: 3, pages: 9 };
const DOC_VIDE = { chemin: "Cours B/S2/d.pdf", cours: "Cours B", section: "S2", nom: "d.pdf", type: "scanne",
  pages: 0, qualite: "vide", confiance: 0, cherchable: false, verifie: false, orphelin: false,
  sortie: "Textes/Cours B/S2/d.pdf.md", date: "2026-11-09" };
const ETAT = { moteur: { present: true, version: "5.5.3", source: "registre", exe: "x", langues: ["fra"],
    langues_effectives: "fra", repli: false, message: "" }, active: true, mode_pdf: "aucun", occupe: false,
  file: { etat: "inactive", document: "", page: 0, pages: 0, documents_faits: 0, documents_total: 0, reprise: 0 },
  compteurs: { documents: 3, pages: 9, a_verifier: 1, a_preparer: 0, pages_a_preparer: 0, octets_texte: 6710886,
    orphelins: 0 },
  reglages: { ocr_langues: "fra", ocr_dpi: 300 } };
HETAT = ETAT; HDOCS = DOCS;
window.pywebview = { api: API };
const $h = s => document.querySelector(s);
const textes = el => el.textContent;
const lignes = () => Hselect(document, ".tx-ligne");
const nbToasts = () => $h("#toasts").children.length;
const toastsDepuis = n => $h("#toasts").children.slice(n).map(t => t.innerHTML).join(" | ");
const genresDepuis = n => $h("#toasts").children.slice(n).map(t => t.className).join(" | ");

(async () => {
  /* ---- 1. arriver sur l'onglet : trois onglets, un seul panneau, aucune action de barre ---- */
  choisirOnglet("textes");
  await Hattendre(30);
  assert.strictEqual(ONGLET, "textes");
  for (const [ident, nom] of [["#o-sync", "sync"], ["#o-semaine", "semaine"], ["#o-textes", "textes"]]) {
    const actif = nom === "textes";
    assert.strictEqual($h(ident).getAttribute("aria-selected"), actif ? "true" : "false", "aria-selected " + ident);
    assert.strictEqual($h(ident).tabIndex, actif ? 0 : -1, "tabindex " + ident);
  }
  assert.strictEqual($h("#v-textes").hidden, false);
  assert.strictEqual($h("#v-sync").hidden, true);
  assert.strictEqual($h("#v-semaine").hidden, true);
  assert.strictEqual($h("#actions-sync").hidden, true);
  assert.strictEqual($h("#actions-semaine").hidden, true);

  /* ---- 2. en-tete, liste, etat vide ---- */
  assert.strictEqual(plat_texte(textes($h(".tx-compte"))),
    "3 documents, 9 pages, 6,4 Mo de texte. 2 lisibles, 1 à vérifier.", "en-tete : " + textes($h(".tx-compte")));
  assert.strictEqual(Hselect($h("#tx-liste"), ".tx-groupe").length, 2, "deux cours");
  assert.strictEqual(lignes().length, 3, "trois documents");
  assert.strictEqual($h("#tx-vide").hidden, true, "l'etat vide est masque quand la liste a des lignes");
  assert.strictEqual($h("#tx-liste").hidden, false);
  assert.strictEqual($h("#tx-liste").innerHTML, "", "la liste ne passe jamais par innerHTML");
  assert.strictEqual(lignes()[0].getAttribute("data-chemin"), "Cours A/S1/a.pdf", "chemin porte par la ligne");
  const noms = lignes().map(l => textes(l.querySelector(".tx-nom")));
  assert.deepStrictEqual(noms, ["a.pdf", "b.pdf", "c<d>.pdf"]);
  const types = lignes().map(l => textes(l.querySelector(".tx-type")));
  assert.deepStrictEqual(types, ["scanné", "texte natif", "scanné"], "mixte affiche scanne (provisoire)");
  const badges = Hselect($h("#tx-liste"), ".badge-qualite").map(b => textes(b));
  assert.ok(badges.includes("Bon") && badges.includes("À vérifier") && badges.includes("Difficile"), "badges : " + badges);
  assert.ok(badges.includes("PDF cherchable"), "variante cherchable");

  /* ---- 3. menu d'une ligne : copier le texte ---- */
  const ligneA = lignes()[0];
  ligneA.querySelector("[data-tx=menu]").dispatchEvent({ type: "click" });
  await Hattendre(10);
  const menu = ligneA.querySelector(".tx-menu");
  assert.ok(menu, "le menu de la ligne s'ouvre et reste ouvert apres la remontee du clic (M42)");
  const libelles = menu.children.map(b => textes(b));
  assert.deepStrictEqual(libelles, ["Copier le texte", "Refaire"]);
  menu.children[0].dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.deepStrictEqual(HCOPIES, ["document:Cours A/S1/a.pdf"]);
  assert.strictEqual(HCOPIE, "texte du document a.pdf");
  assert.ok(toasts().includes("Copié : 23 caractères."), "toast de copie : " + toasts());
  assert.strictEqual(ligneA.querySelector(".tx-menu"), null, "le menu se referme apres l'action");

  /* ---- 4. ouvrir un document : le .md de sortie ---- */
  ligneA.querySelector("[data-tx=ouvrir]").dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.deepStrictEqual(HOUVERTURES, [["Textes/Cours A/S1/a.pdf.md", null]]);

  /* ---- 5. recherche : delai, extrait, copie de l'extrait, champ vide ---- */
  const champ = $h("#tx-recherche");
  champ.value = "scan";
  champ.dispatchEvent({ type: "input" });
  await Hattendre(120);
  assert.deepStrictEqual(HREQUETES, [], "aucune requete avant le delai de 300 ms");
  await Hattendre(300);
  assert.deepStrictEqual(HREQUETES, ["scan"], "une requete apres le delai");
  assert.strictEqual(plat_texte(textes($h("#tx-resultats"))), "4 résultats");
  const trouve = $h(".tx-trouve");
  assert.ok(trouve, "un resultat affiche");
  assert.strictEqual(textes(trouve.querySelector("mark")), "scan", "terme en surbrillance");
  assert.strictEqual(textes(trouve.querySelector(".tx-extrait")), "avant scan après", "jointure des segments");
  assert.ok(textes(trouve).includes("Cours A") && textes(trouve).includes("page 3"), "cours, section et page");
  assert.strictEqual($h("#tx-liste").hidden, true, "la liste laisse la place aux resultats");
  trouve.querySelector("button").dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.strictEqual(HCOPIE, "avant scan après", "Copier l'extrait colle la jointure");
  champ.value = "";
  champ.dispatchEvent({ type: "input" });
  await Hattendre(20);
  assert.strictEqual(plat_texte(textes($h("#tx-resultats"))), "");
  assert.strictEqual($h("#tx-liste").hidden, false, "un champ vide remet la liste");
  assert.strictEqual(HREQUETES.length, 1);

  /* ---- 6. reponse perimee : seule la derniere requete s'affiche, une seule en vol ---- */
  HPORTE = [];
  champ.value = "sc";
  champ.dispatchEvent({ type: "input" });
  await Hattendre(340);
  champ.value = "scan";
  champ.dispatchEvent({ type: "input" });
  await Hattendre(340);
  assert.deepStrictEqual(HREQUETES, ["scan", "sc"], "une seule requete en vol : " + HREQUETES);
  HPORTE.shift()();                       // la reponse de « sc » arrive : elle est perimee
  await Hattendre(30);
  assert.strictEqual(plat_texte(textes($h("#tx-resultats"))), "", "une reponse perimee ne s'affiche pas");
  HPORTE.shift()();                       // la requete « scan », gardee en attente, part maintenant
  await Hattendre(60);
  assert.strictEqual(plat_texte(textes($h("#tx-resultats"))), "4 résultats", "la derniere requete s'affiche");
  assert.ok(textes($h(".tx-trouve")).includes("scan.pdf"));
  HPORTE = null;

  /* ---- 7. menus d'action : ils restent ouverts, se ferment ailleurs et au second clic ---- */
  const boutonExport = $h("#tx-exporter"), boutonCours = $h("#tx-copier-cours");
  boutonExport.dispatchEvent({ type: "click" });
  await Hattendre(10);
  let menuExport = boutonExport.parentNode.querySelector(".tx-menu");
  assert.ok(menuExport, "le menu d'export reste ouvert apres la remontee du clic (ecart 187)");
  assert.deepStrictEqual(menuExport.children.map(b => textes(b)),
    ["Archive ZIP", "Archive avec le détail page par page", "Fichier Markdown"]);
  menuExport.children[1].dispatchEvent({ type: "click" });                 // archive avec le detail
  await Hattendre(20);
  boutonExport.dispatchEvent({ type: "click" });
  await Hattendre(10);
  boutonExport.parentNode.querySelector(".tx-menu").children[2].dispatchEvent({ type: "click" });   // markdown
  await Hattendre(20);
  boutonExport.dispatchEvent({ type: "click" });
  await Hattendre(10);
  boutonExport.parentNode.querySelector(".tx-menu").children[0].dispatchEvent({ type: "click" });   // zip
  await Hattendre(20);
  assert.deepStrictEqual(HEXPORTS, [["tout", "zip_jsonl"], ["tout", "md"], ["tout", "zip"]],
    "les trois formats partent tels quels (M16) : " + JSON.stringify(HEXPORTS));
  assert.ok(toasts().includes("Exporté : 3 documents."), "toast d'export : " + toasts());
  boutonExport.dispatchEvent({ type: "click" });
  await Hattendre(10);
  assert.ok(boutonExport.parentNode.querySelector(".tx-menu"), "menu d'export ouvert");
  $h("#tx-entete").dispatchEvent({ type: "click" });
  await Hattendre(10);
  assert.strictEqual(boutonExport.parentNode.querySelector(".tx-menu"), null,
    "un clic ailleurs ferme le menu (M43)");
  boutonExport.dispatchEvent({ type: "click" });
  await Hattendre(10);
  assert.ok(boutonExport.parentNode.querySelector(".tx-menu"), "seconde ouverture de l'export");
  boutonExport.dispatchEvent({ type: "click" });
  await Hattendre(10);
  assert.strictEqual(boutonExport.parentNode.querySelector(".tx-menu"), null,
    "un second clic sur le bouton ferme le menu");
  boutonCours.dispatchEvent({ type: "click" });
  await Hattendre(10);
  const menuCours = boutonCours.parentNode.querySelector(".tx-menu");
  assert.ok(menuCours, "le menu des cours reste ouvert apres la remontee du clic (ecart 187)");
  assert.strictEqual(textes(menuCours), "Choisis un coursCours A", "titre et cours choisis seulement");
  menuCours.children[1].dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.deepStrictEqual(HCOPIES.slice(-1), ["cours:7"], "portee cours:<cid>");
  assert.strictEqual(HCOPIE, "texte du document a.pdf", "la copie du cours remplit le presse-papiers");
  assert.ok(toasts().includes("Copié : 23 caractères."), "toast de la copie du cours");

  /* ---- 8. qualite : a verifier, difficile et vide ---- */
  HDOCS = { documents: DOCS.documents.concat([DOC_VIDE]), total: 4, pages: 9 };
  await txOuvrir();
  await Hattendre(20);
  $h("#tx-qualite").dispatchEvent({ type: "click" });
  await Hattendre(10);
  assert.strictEqual($h("#d-tx-qualite").open, true, "le dialogue de qualite s'ouvre");
  const qualite = textes($h("#d-tx-qualite"));
  assert.ok(qualite.includes("b.pdf") && qualite.includes("c<d>.pdf"), "documents signales : " + qualite);
  assert.ok(qualite.includes("d.pdf"), "un document vide est signale (M22) : " + qualite);
  assert.ok(!qualite.includes("a.pdf"), "un document bon n'est pas signale");

  /* ---- 9. aucun document, puis un seul : singulier de l'en-tete (ecart 190) ---- */
  HETAT = Object.assign({}, ETAT, { compteurs: { documents: 0, pages: 0, a_verifier: 0, a_preparer: 0,
    pages_a_preparer: 0, octets_texte: 0, orphelins: 0 } });
  HDOCS = { documents: [], total: 0, pages: 0 };
  await txOuvrir();
  assert.strictEqual($h("#tx-vide").hidden, false, "l'etat vide revient sans document");
  assert.strictEqual($h("#tx-liste").hidden, true);
  assert.strictEqual(lignes().length, 0);
  assert.strictEqual(plat_texte(textes($h(".tx-compte"))),
    "0 document, 0 page, 0,0 Mo de texte. 0 lisible, 0 à vérifier.",
    "aucun document : tout au singulier (ecart 190) : " + textes($h(".tx-compte")));
  HETAT = Object.assign({}, ETAT, { compteurs: { documents: 1, pages: 1, a_verifier: 0, a_preparer: 0,
    pages_a_preparer: 0, octets_texte: 1024, orphelins: 0 } });
  HDOCS = { documents: [DOCS.documents[1]], total: 1, pages: 1 };
  await txOuvrir();
  assert.strictEqual(plat_texte(textes($h(".tx-compte"))),
    "1 document, 1 page, 0,0 Mo de texte. 1 lisible, 0 à vérifier.",
    "un document : « 1 lisible » (ecart 190, M21) : " + textes($h(".tx-compte")));
  HETAT = ETAT; HDOCS = DOCS;

  /* ---- 10. navigation au clavier : Home, End et les deux fleches circulaires ---- */
  choisirOnglet("sync", true);
  $h("#onglets").dispatchEvent({ type: "keydown", key: "End", preventDefault() {} });
  await Hattendre(30);
  assert.strictEqual(ONGLET, "textes", "End va au dernier onglet");
  assert.strictEqual(Hactif, $h("#o-textes"), "le focus suit");
  $h("#onglets").dispatchEvent({ type: "keydown", key: "Home", preventDefault() {} });
  await Hattendre(10);
  assert.strictEqual(ONGLET, "sync", "Home va au premier onglet");
  $h("#onglets").dispatchEvent({ type: "keydown", key: "ArrowLeft", preventDefault() {} });
  await Hattendre(10);
  assert.strictEqual(ONGLET, "textes", "la fleche gauche est circulaire");
  $h("#onglets").dispatchEvent({ type: "keydown", key: "ArrowRight", preventDefault() {} });
  await Hattendre(10);
  assert.strictEqual(ONGLET, "sync", "la fleche droite est circulaire (M26)");

  /* ---- 11. Refaire : refaire=true, puis confirmation en deux appels (M12, M13) ---- */
  HETAT = ETAT; HDOCS = DOCS; HCONFIRMATION = true; HLANCES = [];
  await txOuvrir();
  await Hattendre(20);
  const ligneB = lignes()[1];
  ligneB.querySelector("[data-tx=menu]").dispatchEvent({ type: "click" });
  await Hattendre(10);
  const menuB = ligneB.querySelector(".tx-menu");
  assert.deepStrictEqual(menuB.children.map(b => textes(b)), ["Copier le texte", "Refaire", "Restaurer l'original"],
    "un PDF cherchable porte aussi « Restaurer l'original » (ecart 294)");
  menuB.children[1].dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.deepStrictEqual(HLANCES, [["document:Cours A/S1/b.pdf", true, false]],
    "Refaire demande refaire=true (M12) : " + JSON.stringify(HLANCES));
  const question = $h("#d-question");
  assert.strictEqual(question.open, true, "la confirmation du lot s'ouvre");
  question.returnValue = "";
  question.close();
  await Hattendre(20);
  assert.strictEqual(HLANCES.length, 1, "un refus n'appelle pas l'API une seconde fois");
  ligneB.querySelector("[data-tx=menu]").dispatchEvent({ type: "click" });
  await Hattendre(10);
  ligneB.querySelector(".tx-menu").children[1].dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.strictEqual($h("#d-question").open, true, "la confirmation revient apres acceptation");
  $h("#d-question").returnValue = "ok";
  $h("#d-question").close();
  await Hattendre(40);
  assert.deepStrictEqual(HLANCES.slice(-1), [["document:Cours A/S1/b.pdf", true, true]],
    "l'acceptation renvoie confirme=true (M13) : " + JSON.stringify(HLANCES));
  HCONFIRMATION = false;

  /* ---- 11b. Restaurer l'original (ecart 294, critere 12) : confirmation, puis ocr_pdf_restaurer ---- */
  const menuRestaurer = async ligne => {
    ligne.querySelector("[data-tx=menu]").dispatchEvent({ type: "click" });
    await Hattendre(10);
    return ligne.querySelector(".tx-menu").children.find(b => textes(b) === "Restaurer l'original");
  };
  const reponds = async ok => { const q = $h("#d-question"); q.returnValue = ok ? "ok" : ""; q.close(); await Hattendre(40); };
  HETAT = ETAT; HDOCS = DOCS; HRESTAURATIONS = []; HCONFIRMATION = false;
  await txOuvrir();
  await Hattendre(20);
  lignes()[0].querySelector("[data-tx=menu]").dispatchEvent({ type: "click" });
  await Hattendre(10);
  assert.ok(!lignes()[0].querySelector(".tx-menu").children.some(b => textes(b) === "Restaurer l'original"),
    "un PDF qui n'est pas cherchable n'a rien a restaurer");
  txFermerMenu();
  (await menuRestaurer(lignes()[1])).dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.strictEqual($h("#d-question").open, true, "la restauration demande une confirmation");
  assert.strictEqual(plat_texte(textes($h("#q-titre"))), "Restaurer l'original ?");
  assert.ok(textes($h("#q-texte")).includes("retélécharger l'original depuis Moodle") &&
            textes($h("#q-texte")).includes("remplacer le fichier modifié"),
    "la confirmation dit ce que fait le bouton : " + textes($h("#q-texte")));
  assert.deepStrictEqual(HRESTAURATIONS, [], "rien n'est appele avant l'accord");
  await reponds(false);
  assert.deepStrictEqual(HRESTAURATIONS, [], "un refus n'appelle jamais l'API");
  /* accord : un seul appel, avec le chemin du PDF (pas le .md de sortie) */
  let avantR = nbToasts();
  (await menuRestaurer(lignes()[1])).dispatchEvent({ type: "click" });
  await Hattendre(20);
  await reponds(true);
  assert.deepStrictEqual(HRESTAURATIONS, [["Cours A/S1/b.pdf", false]], "ocr_pdf_restaurer(chemin) : " + JSON.stringify(HRESTAURATIONS));
  assert.ok(toastsDepuis(avantR).includes("Original restauré."), "toast de reussite : " + toastsDepuis(avantR));
  /* fichier modifie a la main : la phrase de l'API, puis rappel avec confirme=true */
  HRESTAURATIONS = [];
  const PHRASE_MODIFIE = "Ce fichier a été modifié depuis sa création par MoodleSync. Continuer le remplacera.";
  HRESTAURER = (c, conf) => conf ? { ok: true, pages: 2 } : { confirmer: PHRASE_MODIFIE };
  (await menuRestaurer(lignes()[1])).dispatchEvent({ type: "click" });
  await Hattendre(20);
  await reponds(true);
  assert.strictEqual($h("#d-question").open, true, "la seconde confirmation s'ouvre");
  assert.strictEqual(plat_texte(textes($h("#q-texte"))), PHRASE_MODIFIE, "phrase de l'API, telle quelle");
  assert.deepStrictEqual(HRESTAURATIONS, [["Cours A/S1/b.pdf", false]], "pas encore de rappel");
  await reponds(false);
  assert.strictEqual(HRESTAURATIONS.length, 1, "refuser la seconde confirmation ne rappelle pas l'API");
  (await menuRestaurer(lignes()[1])).dispatchEvent({ type: "click" });
  await Hattendre(20);
  await reponds(true);
  await reponds(true);
  assert.deepStrictEqual(HRESTAURATIONS.slice(1), [["Cours A/S1/b.pdf", false], ["Cours A/S1/b.pdf", true]],
    "rappel avec confirme=true : " + JSON.stringify(HRESTAURATIONS));
  /* original injoignable : la phrase de l'API, rien n'est casse, aucun faux succes */
  const PHRASE_HORS_LIGNE = "Impossible de retélécharger l'original sans connexion. Ton PDF cherchable reste en place, avec ses pages d'origine. Réessaie une fois en ligne.";
  HRESTAURER = () => ({ erreur: PHRASE_HORS_LIGNE });
  avantR = nbToasts();
  (await menuRestaurer(lignes()[1])).dispatchEvent({ type: "click" });
  await Hattendre(20);
  await reponds(true);
  assert.ok(toastsDepuis(avantR).includes(PHRASE_HORS_LIGNE), "la phrase de l'API : " + toastsDepuis(avantR));
  assert.ok(!toastsDepuis(avantR).includes("Original restauré."), "aucun faux succes");
  assert.ok(genresDepuis(avantR).includes("critique"), "erreur en critique");
  assert.strictEqual(lignes().length, 3, "la liste reste intacte");
  HRESTAURER = () => ({ ok: true, pages: 2 }); HRESTAURATIONS = [];

  /* ---- 12. copie vide et texte trop long (ecart 188, M23) ---- */
  HCOPIE = "valeur precedente du presse-papiers";
  let avant = nbToasts();
  HCOPIE_MODE = "vide";
  const ligneA2 = lignes()[0];
  ligneA2.querySelector("[data-tx=menu]").dispatchEvent({ type: "click" });
  await Hattendre(10);
  ligneA2.querySelector(".tx-menu").children[0].dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.strictEqual(HCOPIE, "valeur precedente du presse-papiers",
    "une copie sans document n'ecrase pas le presse-papiers (ecart 188)");
  assert.ok(toastsDepuis(avant).includes("Aucun texte à copier."),
    "phrase d'avertissement pour un document vide : " + toastsDepuis(avant));
  assert.ok(genresDepuis(avant).includes("critique"), "avertissement en critique : " + genresDepuis(avant));
  avant = nbToasts();
  boutonCours.dispatchEvent({ type: "click" });
  await Hattendre(10);
  boutonCours.parentNode.querySelector(".tx-menu").children[1].dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.strictEqual(HCOPIE, "valeur precedente du presse-papiers",
    "la copie d'un cours sans document n'ecrit rien (ecart 188)");
  assert.ok(toastsDepuis(avant).includes("Aucun texte à copier."),
    "phrase d'avertissement pour un cours vide : " + toastsDepuis(avant));
  avant = nbToasts();
  HCOPIE_MODE = "trop";
  ligneA2.querySelector("[data-tx=menu]").dispatchEvent({ type: "click" });
  await Hattendre(10);
  ligneA2.querySelector(".tx-menu").children[0].dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.strictEqual(HCOPIE, "valeur precedente du presse-papiers", "un texte trop long ne copie rien (M23)");
  assert.ok(toastsDepuis(avant).includes("Ce texte est trop long pour le presse-papiers."),
    "phrase du texte trop long : " + toastsDepuis(avant));
  HCOPIE_MODE = "";

  /* ---- 13. export annule : aucun toast (M24) ---- */
  avant = nbToasts();
  HEXPORT_ANNULE = true;
  boutonExport.dispatchEvent({ type: "click" });
  await Hattendre(10);
  boutonExport.parentNode.querySelector(".tx-menu").children[0].dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.strictEqual(toastsDepuis(avant), "", "un export annule n'affiche rien (M24) : " + toastsDepuis(avant));
  HEXPORT_ANNULE = false;

  /* ---- 14. dossier des textes et journal (M35, M28) ---- */
  HOUVERTURES = [];
  $h("#tx-ouvrir-dossier").dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.deepStrictEqual(HOUVERTURES, [["Textes", null]], "le dossier des textes s'ouvre (M35)");
  const HJOURNAL = [];
  window.syncJournal = t => HJOURNAL.push(t);
  window.textesJournal("reprise");
  assert.deepStrictEqual(HJOURNAL, ["reprise"], "textesJournal ecrit dans le journal de Mes cours (M28)");

  /* ---- 15. recherche : seuil de deux caracteres, total, troncature, page (M20, M21, M29, M48) ---- */
  HREQUETES = [];
  HTOTAL = 1; HTRONQUE = true;
  champ.value = "s";
  champ.dispatchEvent({ type: "input" });
  await Hattendre(400);
  assert.deepStrictEqual(HREQUETES, [], "un seul caractere ne lance pas de recherche (M20) : " + HREQUETES);
  assert.strictEqual(plat_texte(textes($h("#tx-resultats"))), "", "aucun resultat pour un caractere");
  assert.strictEqual($h("#tx-liste").hidden, false, "la liste reste en place");
  champ.value = "scan";
  champ.dispatchEvent({ type: "input" });
  await Hattendre(400);
  assert.deepStrictEqual(HREQUETES, ["scan"]);
  assert.strictEqual(plat_texte(textes($h("#tx-resultats"))), "1 résultat Tronqué.",
    "un resultat au singulier et la troncature (M21, M48) : " + textes($h("#tx-resultats")));
  HOUVERTURES = [];
  $h(".tx-trouve").dispatchEvent({ type: "click" });
  await Hattendre(20);
  assert.deepStrictEqual(HOUVERTURES, [["Textes/Cours A/S1/a.pdf.md", 3]],
    "un clic sur un resultat ouvre la page (M29)");
  HTOTAL = null; HTRONQUE = false;

  /* ---- 16. separateur des milliers dans l'en-tete (M49) ---- */
  HETAT = Object.assign({}, ETAT, { compteurs: { documents: 4210, pages: 4210, a_verifier: 0, a_preparer: 0,
    pages_a_preparer: 0, octets_texte: 0, orphelins: 0 } });
  HDOCS = DOCS;
  await txOuvrir();
  await Hattendre(20);
  const compte = textes($h(".tx-compte"));
  assert.ok(compte.includes("4\u00a0210 documents"), "separateur des milliers (M49) : " + compte);
  assert.ok(compte.includes("4\u00a0210 pages"), "separateur des milliers sur les pages : " + compte);

  /* ---- 17. retour sur l'onglet : champ vide, rien ne part, jeton invalide (M36, ecart 191) ---- */
  HETAT = ETAT; HDOCS = DOCS;
  champ.value = "sca";
  champ.dispatchEvent({ type: "input" });
  await Hattendre(50);
  HREQUETES = [];
  choisirOnglet("sync");
  await Hattendre(10);
  choisirOnglet("textes");
  await Hattendre(400);
  assert.strictEqual($h("#tx-recherche").value, "", "le retour sur l'onglet vide le champ (M36)");
  assert.deepStrictEqual(HREQUETES, [], "aucune requete ne part pour un champ vide (ecart 191) : " + HREQUETES);
  assert.strictEqual(plat_texte(textes($h("#tx-resultats"))), "", "aucun resultat pour un champ vide");
  assert.strictEqual($h("#tx-liste").hidden, false, "le retour repart de la liste");
  HPORTE = [];
  HREQUETES = [];
  champ.value = "scan";
  champ.dispatchEvent({ type: "input" });
  await Hattendre(340);
  assert.deepStrictEqual(HREQUETES, ["scan"], "une requete en vol");
  choisirOnglet("sync");
  await Hattendre(10);
  choisirOnglet("textes");
  await Hattendre(80);
  HPORTE.shift()();
  await Hattendre(40);
  assert.strictEqual(plat_texte(textes($h("#tx-resultats"))), "",
    "une reponse perimee par le retour sur l'onglet ne s'affiche pas (jeton)");
  assert.strictEqual($h("#tx-liste").hidden, false, "la liste reste affichee");
  HPORTE = null;

  /* ---- 18. fin d'extraction : en-tete et liste suivent, recherche intacte (ecart 191, M27) ---- */
  HETAT = ETAT; HDOCS = DOCS;
  await txOuvrir();
  await Hattendre(20);
  HREQUETES = []; HTOTAL = 2;
  champ.value = "scan";
  champ.dispatchEvent({ type: "input" });
  await Hattendre(400);
  assert.strictEqual(plat_texte(textes($h("#tx-resultats"))), "2 résultats");
  HETAT = Object.assign({}, ETAT, { compteurs: { documents: 4, pages: 9, a_verifier: 1, a_preparer: 0,
    pages_a_preparer: 0, octets_texte: 6710886, orphelins: 0 } });
  HDOCS = { documents: DOCS.documents.concat([DOC_VIDE]), total: 4, pages: 9 };
  textesProgres({ etat: "terminee" });
  await Hattendre(80);
  assert.strictEqual($h("#tx-recherche").value, "scan", "la fin d'extraction ne vide pas le champ (ecart 191)");
  assert.strictEqual(plat_texte(textes($h("#tx-resultats"))), "2 résultats",
    "les resultats affiches restent apres la fin d'extraction (ecart 191)");
  assert.ok(textes($h(".tx-compte")).includes("4 documents"),
    "l'en-tete suit la fin d'extraction (M27) : " + textes($h(".tx-compte")));
  assert.strictEqual(txDocs.length, 4, "la liste sous-jacente est rechargee");
  champ.value = "";
  champ.dispatchEvent({ type: "input" });
  await Hattendre(30);
  assert.strictEqual(lignes().length, 4, "le champ vide remet la liste rechargee");
  HTOTAL = null;

  /* ---- 19. pause et pause_sync tiennent l'onglet occupe (M31, M32) ---- */
  HETAT = ETAT; HDOCS = DOCS;
  occupations.clear();
  textesProgres({ etat: "pause" });
  assert.ok(occupations.has("textes"), "une pause tient l'onglet occupe (M31, M32) : " + [...occupations]);
  assert.ok($h("#statut-ligne").classList.contains("visible"), "la barre d'activite est visible");
  textesProgres({ etat: "pause_sync" });
  assert.ok(occupations.has("textes"), "pause_sync tient l'onglet occupe : " + [...occupations]);
  textesProgres({ etat: "terminee" });
  await Hattendre(80);
  assert.ok(!occupations.has("textes"), "la fin libere la barre d'activite : " + [...occupations]);

  console.log("OK");
  process.exit(0);
})().catch(e => { console.error(e && e.stack ? e.stack : e); process.exit(1); });

function plat_texte(t) { return String(t).split(/\s+/).filter(Boolean).join(" "); }
function toasts() { return $h("#toasts").children.map(t => t.innerHTML).join(" | "); }
"""


if __name__ == "__main__":
    unittest.main()
