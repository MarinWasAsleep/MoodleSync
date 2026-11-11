"""Tests de la coque de « Mes textes » (tache R7, contrat 5.1, 5.2 et 5.5).

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque. Les phrases d'interface sont relevees dans la seule table TX_MOTS de textes.js, puis
comparees mot pour mot au tableau du contrat 5.5 (blancs replies en une espace) : le test s'ignore
quand le contrat manque.

Le parcours (Node) charge la vraie page d'index.html dans un DOM minimal ecrit ici, puis execute les
vraies fonctions de commun.js, textes-arbre.js, des trois vues et de textes.js contre une doublure
de l'API. Les evenements remontent jusqu'a `document` comme dans un navigateur. Le script du
parcours s'ecrit dans un dossier temporaire, supprime dans un `finally`, et s'ignore sans `node`.

Ce module porte aussi le DOM factice des autres tests d'interface (ENTETE et PAGE) : tests/test_quoi_js.py
le reexporte, tests/test_preparer_js.py et tests/test_accessibilite_js.py le decoupent sur le marqueur
« /* ---- arbre de la page ».

Ce que ces tests ne mesurent pas : aucune vraie fenetre pywebview, aucun navigateur (donc ni rendu,
ni <dialog> natif, ni focus reel, ni lecture d'ecran), aucun vrai moteur, Windows et macOS non
executes.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, re, shutil, subprocess, sys, tempfile, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
INTERFACE = os.path.join(RACINE, "moodlesync", "interface")
DOCS = os.path.join(RACINE, "docs", "refonte-textes")
CONTRAT = os.path.join(DOCS, "contrat.md")

# Contrat 5.5 : mots a eviter dans l'onglet (hors noms d'appels et identifiants).
INTERDITS = ("ocr", "tesseract", "tessdata", "dpi", "segmentation", "psm", "tsv")

# Procedes qui construisent du HTML a partir de donnees : aucun n'a sa place dans ces fichiers.
HTML_CONSTRUIT = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write",
                  "DOMParser", "createContextualFragment")

ACCENTS = "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ¿"

# Garde-fou : hors de la table TX_MOTS, aucune chaine ne doit ressembler a une phrase francaise.
MOTS_FRANCAIS = (
    "le", "la", "les", "un", "une", "des", "du", "de", "ce", "cet", "cette", "mon", "ma", "mes",
    "ton", "ta", "tes", "son", "sa", "ses", "est", "sont", "pas", "pour", "dans", "sur", "avec",
    "aucun", "aucune", "tout", "toute", "tous", "toutes", "rien", "plus", "copier", "ouvrir",
    "choisis", "choisir", "document", "documents", "fichier", "fichiers", "traite", "traites",
)

# Cles ecrites par R7 qui ne sont pas au tableau du contrat 5.5 : noms accessibles du composant
# d'arborescence (contrat 5.3), variante macOS, et cles de la carte de Ma semaine encore lues par
# sync.js jusqu'a R11.
CLES_HORS_CONTRAT = {
    "arbre_nom", "bascule", "case_fichier", "case_dossier", "menu_actions",
    "fichier", "fichiers", "traite_un", "traites",
    "action_afficher_mac", "carte_moteur_absent", "progres_pct", "progres_pause", "action_reprendre", "migration",
    "document", "documents", "page", "pages", "carte_environ", "carte_duree", "carte_reprendre",
    "carte_reprendre_un", "carte_page", "carte_rang", "carte_pause_sync", "carte_rien",
    "preparer_titre", "preparer_maintenant",
}

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
        if not ligne.strip() or ligne.strip().startswith("/*"):
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


def table_contrat():
    """{cle: phrase} du tableau du contrat 5.5, ou None si le contrat manque."""
    if not os.path.isfile(CONTRAT):
        return None
    texte = lire(CONTRAT)
    debut = texte.find("### 5.5 Phrases visibles")
    if debut < 0:
        return None
    fin = texte.find("\nCôté Python", debut)
    bloc = texte[debut:fin if fin > debut else len(texte)]
    table = {}
    for ligne in bloc.splitlines():
        if not ligne.startswith("| `"):
            continue
        cellules = [c.strip() for c in ligne.strip().strip("|").split("|")]
        if len(cellules) < 2:
            continue
        cles = re.findall(r"`([a-z_]+)`", cellules[0])
        if not cles:
            continue
        cellule = cellules[1]
        mac = re.search(r"\(sous macOS : « ([^»]*) »\)", cellule)
        if mac:
            table[cles[0] + "_mac"] = plat(mac.group(1))
            cellule = cellule.replace(mac.group(0), "")
        glose = cellule.find(" (")
        if glose > 0:
            cellule = cellule[:glose]
        cellule = cellule.strip()
        if cellule.startswith("«") and cellule.endswith("»"):
            cellule = cellule[1:-1]
        phrases = [plat(p) for p in cellule.split(" » / « ") if plat(p)]
        for i, cle in enumerate(cles):
            if i < len(phrases):
                table[cle] = phrases[i]
    return table


class TextesJs(unittest.TestCase):
    """textes.js : forme, globales, phrases, et aucune construction de HTML."""

    @classmethod
    def setUpClass(cls):
        cls.source = lire(fichier("textes.js"))
        cls.arbre = lire(fichier("textes-arbre.js"))
        cls.page = lire(fichier("index.html"))
        cls.feuille = lire(fichier("style.css"))

    # ------------------------------------------------------------------ fichier et chargement
    def test_fichier_existe_et_finit_par_un_saut_de_ligne(self):
        self.assertGreater(len(self.source), 2000, "textes.js est vide ou presque")
        self.assertTrue(self.source.endswith("\n"))
        self.assertNotIn("\r", self.source, "textes.js doit etre ecrit en LF")
        self.assertNotIn("\r", self.arbre, "textes-arbre.js doit etre ecrit en LF")

    def test_charge_avant_app(self):
        balises = re.findall(r'<script src="([^"]+)"></script>', self.page)
        for nom in ("textes-arbre.js", "textes-cours.js", "textes-choisir.js", "textes-deposer.js",
                    "textes.js", "app.js"):
            with self.subTest(script=nom):
                self.assertIn(nom, balises, "index.html ne charge pas %s" % nom)
                self.assertEqual(balises.count(nom), 1, "une seule balise %s" % nom)
        self.assertLess(balises.index("textes-arbre.js"), balises.index("textes.js"), "l'arbre avant la coque")
        self.assertLess(balises.index("textes-cours.js"), balises.index("textes.js"), "les vues avant la coque")
        self.assertLess(balises.index("textes.js"), balises.index("app.js"), "textes.js avant app.js")
        for nom in ("textes-cours.css", "textes-choisir.css", "textes-deposer.css"):
            with self.subTest(feuille=nom):
                self.assertIn('<link rel="stylesheet" href="%s">' % nom, self.page)

    def test_globales_du_contrat(self):
        for x in ("function txRafraichir(", "function txMontrerVue(", "function txErreur(",
                  "window.textesProgres", "window.textesDepotChemins"):
            with self.subTest(element=x):
                self.assertIn(x, self.source)
        self.assertTrue(re.search(r"(?m)^let TX\b", self.source), "TX est declaree par la coque")
        for cle in ("arbre", "etat", "vue"):
            with self.subTest(cle=cle):
                self.assertIn("TX." + cle, self.source, "TX.%s du contrat 5.2" % cle)
        self.assertIn("tx:progres", self.source)
        self.assertIn("tx:depot", self.source)

    def test_stubs_retires_par_r11(self):
        """R11 retire les stubs marques : plus rien n'y fait appel (txOccupe est parti, txOuvrir reste)."""
        self.assertNotIn("/* retire par R11 */", self.source, "les stubs marques sont retires")
        for nom in ("txPret", "txOccupe"):
            with self.subTest(nom=nom):
                self.assertNotRegex(sans_commentaires(self.source), r"\b%s\b" % nom,
                                    "plus personne ne lit %s" % nom)
        self.assertIn("function txOuvrir(", self.source, "app.js appelle toujours txOuvrir")
        self.assertTrue(re.search(r'if \(o === "textes" && typeof txOuvrir === "function"\) txOuvrir\(\);',
                                  lire(fichier("app.js"))), "app.js appelle toujours txOuvrir")

    def test_l_arbre_n_appelle_jamais_l_api(self):
        sans = sans_commentaires(self.arbre)
        for appel in ("api()", "ocr_", "pywebview"):
            with self.subTest(appel=appel):
                self.assertNotIn(appel, sans, "le composant n'appelle jamais l'API : %s" % appel)
        self.assertIn("function txArbreCreer(", sans)
        for nom in ("charger", "selection", "vider", "ouvrirTout", "fermerTout"):
            with self.subTest(methode=nom):
                self.assertTrue(re.search(r"(?m)^\s{4}%s\(" % nom, sans), "methode du contrat 5.3 : %s" % nom)

    # ------------------------------------------------------------------ phrases
    def test_table_tx_mots_egale_au_contrat(self):
        contrat = table_contrat()
        if contrat is None:
            self.skipTest("docs/refonte-textes/contrat.md absent : tableau 5.5 non verifie")
        mots = table_mots(self.source)
        self.assertGreaterEqual(len(mots), 30, "table TX_MOTS trop courte : %s" % sorted(mots))
        for cle, phrase in sorted(contrat.items()):
            with self.subTest(cle=cle):
                self.assertIn(cle, mots, "cle du contrat 5.5 absente de TX_MOTS : %s" % cle)
                self.assertEqual(mots[cle], phrase, "phrase du contrat 5.5 differente")
        inconnues = sorted(set(mots) - set(contrat) - CLES_HORS_CONTRAT)
        self.assertEqual(inconnues, [], "cles hors contrat 5.5 et hors CLES_HORS_CONTRAT : %s" % inconnues)

    def test_aucune_phrase_hors_de_la_table(self):
        for chaine in phrases_hors_table(self.source):
            with self.subTest(chaine=chaine):
                self.assertFalse(set(chaine) & set(ACCENTS), "accent hors de TX_MOTS : %r" % chaine)
                self.assertNotIn("'", chaine, "apostrophe hors de TX_MOTS : %r" % chaine)
                if not re.search(r"\s", chaine):
                    continue
                mots = re.findall(r"[A-Za-zÀ-ÿ]+", chaine.lower())
                self.assertFalse([m for m in mots if m in MOTS_FRANCAIS],
                                 "phrase francaise hors de TX_MOTS : %r" % chaine)

    def test_mots_interdits_et_tirets(self):
        for nom, source in (("textes.js", self.source), ("textes-arbre.js", self.arbre)):
            t = re.sub(r"ocr_\w+", " ", source)
            t = re.sub(r"#?[dt]?x-[a-z-]+", " ", t)
            t = re.sub(r"aria-[a-z]+", " ", t)
            bas = t.lower()
            for mot in INTERDITS:
                with self.subTest(fichier=nom, mot=mot):
                    self.assertNotIn(mot, bas)
            for tiret in (chr(0x2013), chr(0x2014)):
                with self.subTest(fichier=nom, tiret=hex(ord(tiret))):
                    self.assertNotIn(tiret, source)

    def test_aucun_html_construit(self):
        for nom, source in (("textes.js", self.source), ("textes-arbre.js", self.arbre)):
            sans = sans_commentaires(source)
            for procede in HTML_CONSTRUIT:
                with self.subTest(fichier=nom, procede=procede):
                    self.assertNotIn(procede, sans, "aucun HTML construit : %s" % procede)
            with self.subTest(fichier=nom, procede="ic/esc"):
                self.assertNotRegex(sans, r"\b(ic|esc)\(", "ic() et esc() de commun.js rendent du HTML")
            self.assertTrue("textContent" in sans or "createTextNode" in sans, "le texte passe par un noeud")

    def test_styles_de_la_coque_et_de_l_arbre(self):
        for selecteur in (".tx-intro", ".tx-onglets", ".tx-vue", ".tx-arbre", ".tx-bascule", ".tx-case",
                          ".tx-resume", ".tx-badge", ".tx-menu-liste", "#tx-moteur"):
            with self.subTest(selecteur=selecteur):
                self.assertIn(selecteur, self.feuille, "selecteur absent de style.css : %s" % selecteur)
        bloc = self.feuille[self.feuille.find("Mes textes : coque"):]
        self.assertFalse(re.search(r"#[0-9a-fA-F]{3,8}\b", bloc), "aucune couleur en dur dans les blocs neufs")
        self.assertIn("var(--", bloc)

    def test_fichiers_en_lf(self):
        for chemin in (fichier("textes.js"), fichier("textes-arbre.js"), fichier("index.html"),
                       fichier("style.css"), os.path.abspath(__file__)):
            with self.subTest(fichier=os.path.basename(chemin)):
                with open(chemin, "rb") as f:
                    self.assertNotIn(b"\r", f.read())

    # ------------------------------------------------------------------ parcours sur DOM factice
    @unittest.skipUnless(shutil.which("node"), "node absent : parcours sur DOM factice non execute")
    def test_parcours_de_la_coque_sur_dom_factice(self):
        node = shutil.which("node") or "node"
        coupe = ENTETE.find("/* ---- arbre de la page")
        self.assertGreater(coupe, 0, "marqueur de l'arbre de la page introuvable")
        dossier = tempfile.mkdtemp(prefix="parcours-r7-")
        script = os.path.join(dossier, "_parcours_coque.js")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(ENTETE[:coupe] + "\n" + PAGE + "\n" + PRELUDE + "\n")
                for nom in ("commun.js", "textes-arbre.js"):
                    f.write("\n/* ===== %s ===== */\n" % nom)
                    f.write(lire(fichier(nom)).replace("\r\n", "\n"))
                f.write("\n" + VUES + "\n")
                f.write("\n/* ===== textes.js ===== */\n")
                f.write(lire(fichier("textes.js")).replace("\r\n", "\n"))
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
    this.checked = false; this.tabIndex = 0; this.style = {}; this.dataset = {}; this._attrs = {};
    this._classes = new Set(); this._texte = ""; this._ecoute = {}; this._inner = "";
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
    if (nom === "checked") this.checked = true;
    if (nom === "disabled") this.disabled = true;
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
  contains(n) { let p = n; while (p) { if (p === this) return true; p = p.parentNode; } return false; }
  closest(sel) { let n = this; while (n && n.nodeType === 1) { if (Hsimple(n, sel)) return n; n = n.parentNode; } return null; }
  addEventListener(type, fn) { (this._ecoute[type] = this._ecoute[type] || []).push(fn); }
  removeEventListener(type, fn) { const l = this._ecoute[type]; if (l) { const i = l.indexOf(fn); if (i >= 0) l.splice(i, 1); } }
  /* Un clic remonte de l'element jusqu'a document, comme dans un navigateur (ecart 187). */
  dispatchEvent(ev) {
    const evenement = ev || {};
    if (!evenement.type) evenement.type = "";
    if (!evenement.target) { try { evenement.target = this; } catch (e) { /* un Event natif n'a pas de poseur */ } }
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
let Hactif = null, HCOPIE = "";
function matchMedia() { return { matches: false, addEventListener() {}, removeEventListener() {} }; }
function requestAnimationFrame(f) { return setTimeout(f, 0); }
function addEventListener() {}   /* app.js attend « pywebviewready » au chargement */
Object.defineProperty(globalThis, "navigator", { configurable: true, writable: true,
  value: { clipboard: { writeText: async t => { HCOPIE = String(t); } } } });
const Hattendre = ms => new Promise(r => setTimeout(r, ms));
function Hel(tag, id, cls) { const e = document.createElement(tag); if (id) e.id = id; if (cls) e.className = cls; return e; }

/* Classes des elements de la page : lues dans index.html, jamais recopiees a la main. */
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

/* ---- arbre de la page */
"""

# Lecteur HTML minimal : la vraie page d'index.html est rangee dans le DOM factice.
PAGE = r"""
function Hdecode(t) {
  return t.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'")
          .replace(/&nbsp;/g, "\u00a0").replace(/&amp;/g, "&");
}
function Hparse(html) {
  const racine = new HElement("#fragment"), pile = [racine];
  const VIDES = new Set(["meta", "link", "input", "img", "br", "hr"]);
  const jeton = /<!--[\s\S]*?-->|<(\/?)([a-zA-Z][\w-]*)((?:"[^"]*"|[^>"])*?)(\/?)>|[^<]+/g;
  let m;
  while ((m = jeton.exec(html))) {
    const s = m[0], haut = pile[pile.length - 1];
    if (s.startsWith("<!--")) continue;
    if (m[2] === undefined) { haut.appendChild(new HTexte(Hdecode(s))); continue; }
    const tag = m[2].toLowerCase();
    if (m[1]) {                                   // balise fermante
      for (let i = pile.length - 1; i > 0; i--) { if (pile[i].tagName.toLowerCase() === tag) { pile.length = i; break; } }
      continue;
    }
    if (tag === "script" || tag === "style") {    // contenu brut, ignore
      const fin = html.indexOf("</" + tag + ">", jeton.lastIndex);
      jeton.lastIndex = fin < 0 ? html.length : fin + tag.length + 3;
      continue;
    }
    const el = new HElement(tag);
    const attrs = /([\w:-]+)(?:\s*=\s*"([^"]*)")?/g;
    let a;
    while ((a = attrs.exec(m[3]))) el.setAttribute(a[1], a[2] === undefined ? "" : Hdecode(a[2]));
    haut.appendChild(el);
    if (!m[4] && !VIDES.has(tag)) pile.push(el);
  }
  return racine;
}
/* La vraie page d'index.html dans le DOM factice, avant que les scripts ne se branchent dessus. */
{
  const corps = HPAGE.slice(HPAGE.indexOf(">", HPAGE.indexOf("<body")) + 1, HPAGE.lastIndexOf("</body>"));
  for (const n of Hparse(corps).childNodes.slice()) document.body.appendChild(n);
}
"""

# Ce que la page attend de app.js et que le parcours de la coque ne charge pas.
PRELUDE = r"""
const occupations = new Set();
function barreOccupee(o, texte, qui) { if (o) occupations.add(qui); else occupations.delete(qui); }
for (const el of Hdescend(document.body)) if (el.hasAttribute("checked")) el.checked = true;
/* Un navigateur emet un objet KeyboardEvent : le DOM factice accepte un objet simple. */
function Htouche(cible, key) {
  const ev = { type: "keydown", key: key, preventDefault() {}, stopPropagation() {} };
  ev.target = cible;
  cible.dispatchEvent(ev);
}
"""

# Trois vues d'epreuve : la coque doit appeler init, activer, desactiver et rafraichir.
VUES = r"""
const HVIE = { cours: { init: 0, rafraichir: 0, activer: 0, desactiver: 0 },
               choisir: { init: 0, rafraichir: 0, activer: 0, desactiver: 0 },
               deposer: { init: 0, rafraichir: 0, activer: 0, desactiver: 0 } };
const HCONTENEURS = {}, HDERNIER = {};
function hVue(nom) {
  return {
    init(conteneur) { HVIE[nom].init++; HCONTENEURS[nom] = conteneur; },
    rafraichir(tx) { HVIE[nom].rafraichir++; HDERNIER[nom] = tx; },
    activer() { HVIE[nom].activer++; },
    desactiver() { HVIE[nom].desactiver++; },
  };
}
const txVueCours = hVue("cours");
const txVueChoisir = hVue("choisir");
const txVueDeposer = hVue("deposer");
"""

PARCOURS = r"""
(async () => {
  const exiger = (cond, message) => { if (!cond) throw new assert.AssertionError({ message: message }); };
  const plat_texte = t => String(t).replace(/\s+/g, " ").trim();
  const $h = s => document.querySelector(s);
  const clique = async el => { el.dispatchEvent({ type: "click" }); await Hattendre(40); };
  const visible = el => !!el && el.hidden === false;
  const copie = o => JSON.parse(JSON.stringify(o));
  const lesToasts = () => $h("#toasts").children.map(t => {
    const m = String(t.innerHTML).match(/<span>([\s\S]*)<\/span>/); return m ? Hdecode(m[1]) : ""; });
  const panneaux = () => ["cours", "choisir", "deposer"].map(v => $h("#tx-v-" + v).hidden);

  const MOTEUR = { present: true, version: "5.5.0", source: "portable", exe: "x", langues: ["fra"],
                   langues_effectives: "fra", repli: false, message: "" };
  const FILE0 = { etat: "inactive", document: "", page: 0, pages: 0, documents_faits: 0,
                  documents_total: 0, reprise: 0 };
  const ETAT0 = { moteur: MOTEUR, occupe: false, file: FILE0,
                  compteurs: { fichiers: 6, traites: 2, a_verifier: 1, echecs: 1, non_traites: 2,
                               pages_non_traitees: 31 },
                  reglages: { ocr_langues: "fra+eng", ocr_dpi: 300, ocr_format: "md" },
                  originaux: { nombre: 2, octets: 13871416 },
                  depot: { etat: "inactif", dossier_defaut: "C:/Bureau/Documents déposés", dossier: "", resultats: [] } };
  const ARBRE = { racine: "C:/Moodle", cours: [], compteurs: { fichiers: 0, traites: 0, a_verifier: 0,
                  echecs: 0, non_traites: 0, pages_non_traitees: 0 } };

  const APPELS = [];
  let HETAT = copie(ETAT0), HARBRE = copie(ARBRE), HINSTALLER = null;
  const API = {
    ocr_etat: async () => { APPELS.push("ocr_etat"); return copie(HETAT); },
    ocr_arbre: async () => { APPELS.push("ocr_arbre"); return copie(HARBRE); },
    ocr_pause: async () => { APPELS.push("ocr_pause"); return { file: Object.assign({}, FILE0, { etat: "pause" }) }; },
    ocr_reprendre: async () => { APPELS.push("ocr_reprendre"); return { file: Object.assign({}, FILE0, { etat: "en_cours" }) }; },
    ocr_annuler: async () => { APPELS.push("ocr_annuler"); return { file: Object.assign({}, FILE0, { etat: "annulee" }) }; },
    ocr_installer: async () => { APPELS.push("ocr_installer"); return HINSTALLER; },
    ocr_choisir_exe: async () => { APPELS.push("ocr_choisir_exe"); return { annule: true }; },
    ocr_installer_annuler: async () => { APPELS.push("ocr_installer_annuler"); return { annule: true }; },
  };
  window.pywebview = { api: API };

  /* ---- 1. au chargement : phrases fixes, vues montees une fois, un seul panneau visible ---- */
  const intro = $h("#tx-intro");
  exiger(intro, "la phrase d'introduction (#tx-intro) est dans la page");
  assert.strictEqual(plat_texte(intro.textContent), TX_MOTS.intro, "la phrase d'introduction vient de TX_MOTS");
  assert.strictEqual(plat_texte($h("#tx-o-cours").textContent), "Mes cours");
  assert.strictEqual(plat_texte($h("#tx-o-choisir").textContent), "Choisir quoi traiter");
  assert.strictEqual(plat_texte($h("#tx-o-deposer").textContent), "Déposer des fichiers");
  assert.deepStrictEqual(panneaux(), [false, true, true], "un seul panneau visible au depart");
  assert.strictEqual($h("#tx-o-cours").getAttribute("aria-selected"), "true");
  assert.strictEqual($h("#tx-o-choisir").getAttribute("aria-selected"), "false");
  assert.strictEqual($h("#tx-o-cours").tabIndex, 0);
  assert.strictEqual($h("#tx-o-choisir").tabIndex, -1);
  assert.deepStrictEqual([HVIE.cours.init, HVIE.choisir.init, HVIE.deposer.init], [1, 1, 1], "init une seule fois");
  assert.strictEqual(HVIE.cours.activer, 1, "la vue active est activee au chargement");
  assert.strictEqual(HVIE.choisir.activer, 0, "les autres ne sont pas activees");
  exiger(HCONTENEURS.cours === $h("#tx-v-cours"), "init recoit le conteneur de la vue");
  exiger(TX && TX.vue === "cours" && "arbre" in TX && "etat" in TX, "TX porte arbre, etat et vue (contrat 5.2)");
  assert.deepStrictEqual(APPELS, [], "la coque ne lit rien tant que l'onglet n'est pas ouvert");

  /* ---- 2. les trois sous-onglets : clic, fleches, Debut, Fin ---- */
  await clique($h("#tx-o-choisir"));
  assert.deepStrictEqual(panneaux(), [true, false, true], "clic sur Choisir : son panneau seul");
  assert.strictEqual(HVIE.cours.desactiver, 1, "la vue quittee est desactivee");
  assert.strictEqual(HVIE.choisir.activer, 1, "la vue choisie est activee");
  assert.strictEqual($h("#tx-o-choisir").tabIndex, 0);
  assert.strictEqual($h("#tx-o-cours").tabIndex, -1);
  assert.strictEqual(TX.vue, "choisir", "TX.vue suit le sous-onglet");
  Htouche($h("#tx-onglets"), "ArrowRight");
  await Hattendre(10);
  assert.deepStrictEqual(panneaux(), [true, true, false], "fleche droite : Deposer");
  assert.strictEqual(TX.vue, "deposer");
  Htouche($h("#tx-onglets"), "ArrowRight");
  await Hattendre(10);
  assert.strictEqual(TX.vue, "cours", "fleche droite depuis la derniere : retour a la premiere");
  Htouche($h("#tx-onglets"), "ArrowLeft");
  await Hattendre(10);
  assert.strictEqual(TX.vue, "deposer", "fleche gauche depuis la premiere : la derniere");
  Htouche($h("#tx-onglets"), "Home");
  await Hattendre(10);
  assert.strictEqual(TX.vue, "cours", "Debut va a la premiere");
  Htouche($h("#tx-onglets"), "End");
  await Hattendre(10);
  assert.strictEqual(TX.vue, "deposer", "Fin va a la derniere");
  Htouche($h("#tx-onglets"), "ArrowDown");
  await Hattendre(10);
  assert.strictEqual(TX.vue, "deposer", "une autre touche ne change rien");
  txMontrerVue("inconnue");
  assert.strictEqual(TX.vue, "deposer", "un nom inconnu est ignore");
  txMontrerVue("cours");
  assert.deepStrictEqual(panneaux(), [false, true, true], "txMontrerVue active le panneau demande");
  exiger(HVIE.cours.activer >= 2 && HVIE.deposer.desactiver >= 1, "activer et desactiver suivent les passages");

  /* ---- 3. txRafraichir : etat puis arbre, un seul chargement par appel ---- */
  APPELS.length = 0;
  await txRafraichir();
  assert.deepStrictEqual(APPELS, ["ocr_etat", "ocr_arbre"], "etat puis arbre : " + JSON.stringify(APPELS));
  assert.strictEqual(TX.etat.reglages.ocr_format, "md");
  assert.deepStrictEqual(TX.arbre, ARBRE, "TX.arbre est la reponse de ocr_arbre");
  assert.strictEqual(HVIE.cours.rafraichir, 1, "la vue active est rafraichie");
  assert.strictEqual(HDERNIER.cours, TX, "la vue recoit l'etat partage");
  assert.strictEqual(HVIE.choisir.rafraichir, 0, "les vues inactives ne sont pas rafraichies");
  /* une erreur de l'API : la phrase telle quelle, et rien d'autre n'est lu */
  APPELS.length = 0;
  const t0 = lesToasts().length;
  HETAT = { erreur: "Texte des cours : une erreur est survenue." };
  await txRafraichir();
  assert.deepStrictEqual(lesToasts().slice(t0), ["Texte des cours : une erreur est survenue."], "phrase de l'API");
  assert.deepStrictEqual(APPELS, ["ocr_etat"], "une erreur d'etat arrete le chargement");
  HETAT = copie(ETAT0);
  APPELS.length = 0;
  HARBRE = { erreur: "Le dossier de rangement est introuvable." };
  const t1 = lesToasts().length;
  await txRafraichir();
  assert.deepStrictEqual(lesToasts().slice(t1), ["Le dossier de rangement est introuvable."]);
  HARBRE = copie(ARBRE);

  /* ---- 4. txErreur ---- */
  const t2 = lesToasts().length;
  assert.strictEqual(txErreur({ erreur: "Copie impossible." }), true, "txErreur rend vrai quand elle montre");
  assert.deepStrictEqual(lesToasts().slice(t2), ["Copie impossible."]);
  assert.strictEqual(txErreur({ ok: true }), false, "sans erreur, rien ne s'affiche");
  assert.strictEqual(lesToasts().length, t2 + 1);

  /* ---- 5. progression : barre, TX.etat.file, evenement tx:progres, relecture a la fin ---- */
  const vus = [];
  document.addEventListener("tx:progres", e => vus.push(e.detail));
  window.textesProgres({ etat: "en_cours", document: "Histoire contemporaine/Semaine 3/Studer 1996.pdf",
                         page: 3, pages: 14, documents_faits: 2, documents_total: 6 });
  exiger(visible($h("#tx-travail")), "la barre de travail s'affiche");
  assert.strictEqual(plat_texte($h("#tx-travail .tx-travail-document").textContent), "Studer 1996.pdf",
    "le document en cours, sans son dossier");
  assert.strictEqual(plat_texte($h("#tx-travail .tx-travail-pct").textContent), "37 %", "2 documents et 3 pages sur 14");
  assert.strictEqual($h("#tx-travail progress").value, 37, "la barre suit");
  assert.strictEqual(vus.length, 1, "tx:progres est emis");
  assert.strictEqual(vus[0].document, "Histoire contemporaine/Semaine 3/Studer 1996.pdf");
  assert.strictEqual(TX.file.page, 3, "textesProgres garde TX.file pour la carte de Ma semaine");
  assert.strictEqual(TX.etat.file.page, 3, "TX.etat.file du contrat 5.2");
  assert.strictEqual(TX.file.etat, "en_cours", "un traitement occupe l'onglet");
  exiger(occupations.has("textes"), "la barre globale d'app.js suit");
  exiger(visible($h('#tx-travail [data-action="pause"]')), "Pause est propose");
  exiger(!visible($h('#tx-travail [data-action="reprendre"]')), "hors pause, Reprendre est masque");
  window.textesProgres({ etat: "pause", document: "a.pdf", page: 1, pages: 2, documents_faits: 2, documents_total: 6 });
  exiger(!visible($h('#tx-travail [data-action="pause"]')), "en pause, Pause disparait");
  exiger(visible($h('#tx-travail [data-action="reprendre"]')), "en pause, Reprendre apparait (E-V5-2)");
  assert.strictEqual(plat_texte($h('#tx-travail [data-action="reprendre"]').textContent), TX_MOTS.action_reprendre,
    "le bouton porte sa phrase de TX_MOTS");
  /* Reprendre appelle ocr_reprendre puis relit l'etat (contrat 5.2) */
  APPELS.length = 0;
  await clique($h('#tx-travail [data-action="reprendre"]'));
  await Hattendre(40);
  assert.strictEqual(APPELS[0], "ocr_reprendre", "Reprendre appelle ocr_reprendre : " + JSON.stringify(APPELS));
  assert.ok(APPELS.indexOf("ocr_etat") > 0 && APPELS.indexOf("ocr_arbre") > 0,
    "apres la reprise, l'onglet relit l'etat et l'arbre : " + JSON.stringify(APPELS));
  window.textesProgres({ etat: "pause_sync", document: "a.pdf", page: 1, pages: 2, documents_faits: 2, documents_total: 6 });
  exiger(visible($h("#tx-travail")), "pause pendant la synchronisation : la barre reste");
  exiger(visible($h('#tx-travail [data-action="reprendre"]')), "en pause de synchronisation, Reprendre est la aussi");
  APPELS.length = 0;
  window.textesProgres({ etat: "terminee", document: "", page: 0, pages: 0, documents_faits: 6, documents_total: 6 });
  await Hattendre(60);
  assert.deepStrictEqual(APPELS, ["ocr_etat", "ocr_arbre"], "la fin d'un traitement relit tout");
  exiger(!visible($h("#tx-travail")), "plus rien ne travaille : la barre se masque");
  assert.strictEqual(TX.file.etat, "terminee", "la file est terminee");
  exiger(!occupations.has("textes"), "plus rien n'occupe l'onglet");
  assert.strictEqual(vus.length, 5, "un evenement par appel, Reprendre compris");
  window.textesProgres(null);
  assert.strictEqual(vus.length, 5, "un appel vide est ignore");

  /* ---- 6. Pause et Arreter ---- */
  APPELS.length = 0;
  window.textesProgres({ etat: "en_cours", document: "a.pdf", page: 1, pages: 2, documents_faits: 1, documents_total: 6 });
  await clique($h('#tx-travail [data-action="pause"]'));
  assert.deepStrictEqual(APPELS, ["ocr_pause"], "Pause appelle ocr_pause");
  await clique($h('#tx-travail [data-action="arreter"]'));
  assert.deepStrictEqual(APPELS.slice(1), ["ocr_annuler"], "Arreter appelle ocr_annuler");
  window.textesProgres({ etat: "inactive", document: "", page: 0, pages: 0, documents_faits: 0, documents_total: 0 });
  exiger(!visible($h("#tx-travail")), "une file inactive masque la barre");

  /* ---- 7. carte du moteur : visible quand il manque, invisible sinon ---- */
  HETAT = copie(ETAT0); HETAT.moteur = Object.assign({}, MOTEUR, { present: false });
  await txRafraichir();
  exiger(visible($h("#tx-moteur")), "sans moteur, la carte d'installation est visible");
  assert.strictEqual(plat_texte($h("#tx-moteur .tx-moteur-texte").textContent), TX_MOTS.carte_moteur_absent);
  exiger(visible($h('#tx-moteur [data-action="installer"]')), "le bouton Installer");
  exiger(visible($h('#tx-moteur [data-action="exe"]')), "le choix de l'emplacement");
  APPELS.length = 0;
  await clique($h('#tx-moteur [data-action="exe"]'));
  assert.deepStrictEqual(APPELS, ["ocr_choisir_exe"], "Indiquer l'emplacement appelle ocr_choisir_exe");
  HINSTALLER = copie(ETAT0); HETAT = copie(ETAT0);
  APPELS.length = 0;
  await clique($h('#tx-moteur [data-action="installer"]'));
  await Hattendre(40);
  assert.strictEqual(APPELS[0], "ocr_installer", "Installer appelle ocr_installer");
  assert.ok(APPELS.includes("ocr_arbre"), "installe, la coque relit tout : " + JSON.stringify(APPELS));
  exiger(!visible($h("#tx-moteur")), "moteur present : la carte disparait");
  window.textesInstallation({ recu: 40, total: 100 });
  exiger(!visible($h("#tx-moteur")), "une progression sans carte ne casse rien");
  HETAT = copie(ETAT0);
  await txRafraichir();
  exiger(!visible($h("#tx-moteur")), "moteur present : rien a installer");

  /* ---- 8. glisser-deposer et annonce de la migration ---- */
  const depots = [];
  document.addEventListener("tx:depot", e => depots.push(e.detail));
  window.textesDepotChemins(["C:/Users/max/Desktop/a.pdf", "C:/Users/max/Desktop/b.pdf"]);
  assert.deepStrictEqual(depots, [["C:/Users/max/Desktop/a.pdf", "C:/Users/max/Desktop/b.pdf"]],
    "tx:depot porte les chemins recus");
  window.textesDepotChemins(null);
  assert.deepStrictEqual(depots[1], [], "une valeur vide donne une liste vide");
  const t3 = lesToasts().length;
  window.textesMigration({ deplaces: 4, supprimes: 3, restants: 0 });
  assert.strictEqual(lesToasts().length, t3 + 1, "la migration s'annonce une fois");
  assert.ok(lesToasts()[t3].indexOf("4") >= 0, "l'annonce porte les nombres : " + lesToasts()[t3]);

  /* ---- 9. le stub de app.js ---- */
  assert.strictEqual(typeof txOuvrir, "function", "txOuvrir reste definie pour app.js");
  APPELS.length = 0;
  await txOuvrir();
  assert.deepStrictEqual(APPELS, ["ocr_etat", "ocr_arbre"], "txOuvrir relit tout");

  console.log("OK");
  process.exit(0);
})().catch(e => { console.error(e && e.stack ? e.stack : e); process.exit(1); });
"""


if __name__ == "__main__":
    unittest.main()
