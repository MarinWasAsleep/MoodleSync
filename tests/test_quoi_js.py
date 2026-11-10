"""Tests du panneau « A quoi ca sert ? » et de l'apercu d'une page (tache U3).

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque. Deux familles de tests.

Statiques : le panneau `#d-tx-quoi` d'index.html porte les phrases du plan 3.6 mot pour mot (chaque
phrase est comparee entiere, et verifiee d'abord dans le plan lui-meme), aucun mot interdit, aucun
identifiant nouveau, aucun HTML construit avec des donnees, aucun `ocr_lancer` en dehors de
`txRefaire`, un bloc de style U3 sans couleur en dur.

Parcours (Node, s'ignore sans `node`) : la page entiere d'index.html est lue et rangee dans un DOM
minimal (classes, attributs et identifiants viennent du fichier, rien n'est recopie a la main), puis
les vraies fonctions de commun.js, textes.js et app.js tournent contre une doublure de l'API. Les
evenements remontent jusqu'a `document` (c'est ce qui a cache l'ecart 187). Le script s'ecrit dans
un dossier temporaire, supprime dans un `finally`.

Ce que ces tests ne mesurent pas : aucune vraie fenetre pywebview, aucun navigateur (donc ni rendu,
ni <dialog> natif, ni focus reel), aucun vrai presse-papiers, aucun vrai moteur de reconnaissance,
aucun vrai rendu de page, Windows et macOS non executes.

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

# Phrases du plan 3.6 (microcopy du panneau et blocs 1 a 4), sans la mise en forme du Markdown.
PHRASE_CHAPEAU = ("Un PDF scanné, c'est une photo de texte. MoodleSync peut le transformer en vrai texte, "
                  "sur ton ordinateur, une seule fois.")
PHRASE_SUITE = ("Ensuite, tu cherches un mot, tu copies un passage, tu colles ton cours dans une IA. "
                "Les pages restent indiquées.")
PHRASE_COUT = "Une seule extraction, ensuite tu réutilises. Tu ne renvoies plus les images à chaque question."
PHRASE_LIMITE = ("La reconnaissance n'est pas parfaite : l'écriture manuscrite, les formules et les colonnes "
                 "lui résistent parfois. MoodleSync signale les pages à vérifier.")
PHRASE_SOUS_BOUTON = "Une page, quelques secondes. Rien n'est enregistré tant que tu n'as pas confirmé."
PHRASE_SOUS_LIMITES = ("Par défaut, tes fichiers originaux ne sont jamais modifiés. Si tu choisis de rendre un PDF "
                       "cherchable, le fichier est remplacé sur place et garde ses pages d'origine. Aucune copie "
                       "lourde n'est conservée.")
PHRASE_MD = ("Markdown (.md) est un simple fichier texte avec des titres. Obsidian, les éditeurs de texte et les "
             "outils d'IA le lisent. Tu n'as pas besoin de connaître le format : ce qui compte, c'est que le "
             "texte soit cherchable et copiable.")
USAGES = (
    ("Retrouver une citation.",
     "Cherche un mot dans tous tes cours, même dans les photocopies. La page est indiquée."),
    ("Interroger une IA.",
     "Colle le texte d'un cours dans ChatGPT, Claude ou NotebookLM, puis pose tes questions. "
     "L'IA peut citer les pages au lieu de deviner."),
    ("Réviser et prendre des notes.",
     "Le texte va dans Obsidian, dans une fiche ou dans un outil de révision, sans rescanner le document."),
)
COLONNE_AVANT = ("Aujourd'hui, un scan", "Une image de 24 pages, 18 Mo", "Ctrl+F ne trouve rien",
                 "À renvoyer à chaque question posée à une IA", "L'IA doit deviner le texte sur l'image")
COLONNE_APRES = ("Après MoodleSync", "Un fichier texte de 24 pages, environ 90 Ko",
                 "Ctrl+F trouve « institution » à la page 12", "Se colle en un clic, avec les pages marquées",
                 "L'IA lit un texte propre et peut citer [p. 12]")
BOUTONS = ("Essayer sur une page de mon cours", "Voir un exemple", "Copier cet extrait", "Préparer tout le cours")
TITRES = ("À quoi ça sert ?", "Pourquoi un fichier .md ?")


def plan_plat():
    """Plan plat, ou None : le plan de travail vit sur le depot prive."""
    chemin = os.path.join(DOCS, "plan-ocr.md")
    if not os.path.isfile(chemin):
        return None
    texte = lire(chemin)
    return plat(texte.replace("**", "").replace("`", ""))


def panneau_html():
    page = lire(os.path.join(INTERFACE, "index.html"))
    debut = page.find('<dialog class="dialogue large" id="d-tx-quoi">')
    fin = page.find("</dialog>", debut)
    return page[debut:fin + len("</dialog>")] if debut >= 0 and fin > debut else ""


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


class PanneauStatique(unittest.TestCase):
    """index.html, textes.js et style.css : ce que le panneau dit et ce qu'il n'a pas le droit de faire."""

    @classmethod
    def setUpClass(cls):
        cls.page = lire(os.path.join(INTERFACE, "index.html"))
        cls.js = lire(os.path.join(INTERFACE, "textes.js"))
        cls.css = lire(os.path.join(INTERFACE, "style.css"))
        cls.panneau = panneau_html()
        cls.texte = texte_de(cls.panneau)
        cls.plan = plan_plat()

    def test_les_phrases_attendues_sont_bien_celles_du_plan(self):
        """Garde du test lui-meme : chaque phrase attendue existe, entiere, dans le plan 3.6."""
        if self.plan is None:
            self.skipTest("plan de travail absent de ce clone (depot prive)")
        phrases = [PHRASE_CHAPEAU, PHRASE_SUITE, PHRASE_COUT, PHRASE_LIMITE, PHRASE_SOUS_BOUTON,
                   PHRASE_SOUS_LIMITES, PHRASE_MD] + list(BOUTONS) + list(TITRES) + list(COLONNE_AVANT)
        phrases += list(COLONNE_APRES)
        for titre, phrase in USAGES:
            phrases += [titre, phrase]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.plan)

    def test_le_panneau_est_dans_index_html(self):
        self.assertTrue(self.panneau, "le dialogue #d-tx-quoi est introuvable dans index.html")
        self.assertIn('class="dialogue large"', self.panneau)
        self.assertIn("data-ferme", self.panneau, "le bouton de fermeture existe")

    def test_phrases_du_plan_dans_le_panneau(self):
        self.assertTrue(self.panneau, "le dialogue #d-tx-quoi est introuvable dans index.html")
        attendues = [PHRASE_CHAPEAU, PHRASE_SUITE, PHRASE_COUT, PHRASE_LIMITE, PHRASE_SOUS_BOUTON,
                     PHRASE_SOUS_LIMITES, PHRASE_MD, "Copier cet extrait", "Préparer tout le cours",
                     "Pourquoi un fichier .md ?"]
        attendues += list(COLONNE_AVANT) + list(COLONNE_APRES)
        for titre, phrase in USAGES:
            attendues.append(titre + " " + phrase)
        for phrase in attendues:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.texte, "phrase du plan 3.6 absente ou changee dans le panneau")

    def test_titre_et_boutons_du_plan(self):
        self.assertTrue(re.search(r"<h3>À quoi ça sert \?</h3>", self.panneau))
        # Libelles des deux etats du bouton d'essai : ils vivent dans TX_MOTS (textes.js).
        mots = tj.table_mots(self.js)
        self.assertEqual(mots.get("quoi_essayer"), "Essayer sur une page de mon cours")
        self.assertEqual(mots.get("quoi_exemple_bouton"), "Voir un exemple")
        self.assertIn("Essayer sur une page de mon cours", self.texte, "l'etat de depart du bouton")

    def test_mot_markdown_seulement_dans_la_ligne_repliable(self):
        m = re.search(r"<details[\s\S]*?</details>", self.panneau)
        self.assertIsNotNone(m, "la ligne repliable « Pourquoi un fichier .md ? » est un <details>")
        self.assertIn("<summary>", m.group(0))
        hors = self.panneau.replace(m.group(0), "")
        self.assertNotIn("markdown", hors.lower())
        self.assertIn("Markdown", m.group(0))

    def test_aucun_mot_interdit_ni_tiret_long(self):
        bas = self.texte.lower()
        for mot in INTERDITS:
            with self.subTest(mot=mot):
                self.assertNotIn(mot, bas)
        for tiret in (chr(0x2013), chr(0x2014)):
            self.assertNotIn(tiret, self.panneau)

    def test_aucun_identifiant_nouveau(self):
        """Le contrat 3.4 ne nomme que #d-tx-quoi et #tx-quoi : le panneau n'ajoute aucun id."""
        interieur = self.panneau.split(">", 1)[1]
        interieur = interieur.replace('id="d-tx-quoi"', "")
        self.assertNotIn(' id="', interieur)
        self.assertEqual(self.page.count('id="tx-quoi"'), 1)
        self.assertEqual(self.page.count('id="d-tx-quoi"'), 1)

    def test_lien_de_l_etat_vide(self):
        m = re.search(r'<div class="tx-vide" id="tx-vide">[\s\S]*?</div>', self.page)
        self.assertIsNotNone(m)
        self.assertRegex(m.group(0), r'<button class="lien" data-action="quoi">À quoi ça sert \?</button>')
        self.assertIn('data-action="preparer"', m.group(0), "le bouton de U4 reste en place")

    def test_aucun_html_construit_avec_des_donnees(self):
        sans = tj.sans_commentaires(self.js)
        corps = corps_de(sans, "txQuoiMontrer") or ""
        self.assertTrue(corps, "txQuoiMontrer est la fonction qui affiche la reponse de l'API")
        for procede in HTML_CONSTRUIT:
            with self.subTest(procede=procede):
                self.assertNotIn(procede, sans)
        self.assertNotRegex(sans, r"\b(ic|esc)\(", "ic() et esc() de commun.js rendent du HTML")
        self.assertIn("textContent", corps)
        self.assertIn("setAttribute", corps, "alt et src passent par setAttribute")

    def test_l_essai_appelle_apercu_et_jamais_ocr_lancer(self):
        sans = tj.sans_commentaires(self.js)
        essai = corps_de(sans, "txQuoiEssayer")
        self.assertTrue(essai, "txQuoiEssayer est la fonction du bouton d'essai")
        self.assertRegex(essai, r"api\(\)\.ocr_apercu\(\)", "chemin vide : le moteur choisit un scan")
        total = len(re.findall(r"ocr_lancer\(", sans))
        dans_refaire = len(re.findall(r"ocr_lancer\(", corps_de(sans, "txRefaire") or ""))
        self.assertEqual(total, dans_refaire, "aucun ocr_lancer hors de txRefaire : l'essai ne lance rien")
        self.assertNotIn("ocr_choisir_exe", sans, "« Indiquer l'emplacement » n'est pas branche (journal)")

    def test_preparer_depend_de_txpreparer(self):
        sans = tj.sans_commentaires(self.js)
        self.assertIn('typeof txPreparer === "function"', sans)
        self.assertNotRegex(sans, r"function\s+txPreparer\b", "txPreparer est a U4, U3 ne la definit pas")

    def test_ouverture_depuis_la_carte_et_l_etat_vide(self):
        sans = tj.sans_commentaires(self.js)
        self.assertIn('$("#tx-quoi")', sans)
        self.assertIn("'[data-action=\"quoi\"]'", sans)

    def test_bloc_de_style_u3(self):
        debut = self.css.rfind("U3")
        self.assertGreater(debut, 0, "le bloc U3 est annonce par un commentaire contenant « U3 »")
        bloc = self.css[debut:]
        for selecteur in (".tx-quoi-cols", ".tx-quoi-usage", ".tx-quoi-apercu", ".tx-quoi-texte",
                          ".tx-quoi-image", ".tx-quoi-modele"):
            with self.subTest(selecteur=selecteur):
                self.assertIn(selecteur, bloc)
        self.assertFalse(re.search(r"#[0-9a-fA-F]{3,8}\b", bloc), "aucune couleur en dur dans le bloc U3")
        self.assertNotIn("prefers-color-scheme", bloc)
        self.assertNotIn("[data-theme", bloc)
        self.assertNotIn("url(", bloc)
        self.assertIn("var(--", bloc)
        # Les deux colonnes passent l'une sous l'autre dans une fenetre etroite (point de rupture existant).
        m = re.search(r"@media \(max-width: (\d+)px\)\s*\{[^@]*?\.tx-quoi-cols[^}]*\}", bloc)
        self.assertIsNotNone(m, "une regle .tx-quoi-cols dans un @media (max-width)")
        self.assertIn(int(m.group(1)), (460, 560, 680, 860, 980), "point de rupture existant")

    def test_fichiers_en_lf(self):
        for chemin in (os.path.join(INTERFACE, "textes.js"), os.path.join(INTERFACE, "index.html"),
                       os.path.join(INTERFACE, "style.css"), os.path.abspath(__file__)):
            with self.subTest(fichier=os.path.basename(chemin)):
                with open(chemin, "rb") as f:
                    self.assertNotIn(b"\r", f.read())

    # ------------------------------------------------------------------ parcours sur DOM factice
    @unittest.skipUnless(shutil.which("node"), "node absent : parcours sur DOM factice non execute")
    def test_parcours_du_panneau_sur_dom_factice(self):
        node = shutil.which("node") or "node"
        coupe = tj.ENTETE.find("/* ---- arbre de la page")
        self.assertGreater(coupe, 0, "marqueur de l'arbre de la page introuvable dans l'entete de test_textes_js")
        dossier = tempfile.mkdtemp(prefix="parcours-quoi-")
        script = os.path.join(dossier, "_parcours_quoi.js")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(tj.ENTETE[:coupe] + "\n" + OUTILS + "\n")
                for nom in ("commun.js", "textes.js", "app.js"):
                    f.write("\n/* ===== %s ===== */\n" % nom)
                    f.write(lire(os.path.join(INTERFACE, nom)).replace("\r\n", "\n"))
                f.write("\n" + PARCOURS)
            r = subprocess.run([node, script, INTERFACE], capture_output=True, text=True, timeout=180)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        self.assertEqual(r.returncode, 0, "le parcours a echoue :\n%s\n%s" % (r.stdout, r.stderr))
        self.assertIn("OK", r.stdout)


# Lecteur HTML minimal : la page d'index.html est rangee dans le DOM factice, classes et attributs compris.
OUTILS = r"""
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

PARCOURS = r"""
(async () => {
  const exiger = (cond, message) => { if (!cond) throw new assert.AssertionError({ message: message }); };
  const texte = el => el.textContent;
  const plat_texte = t => String(t).replace(/\s+/g, " ").trim();

  let HAPERCUS = [], HPREP = 0, HGARDE = null, HREPONSE = null, HE = null;
  const API = {
    ocr_etat: async () => HE,
    ocr_documents: async () => ({ documents: [], total: 0, pages: 0 }),
    ocr_apercu: async (...a) => { HAPERCUS.push(a); if (HGARDE) await new Promise(r => HGARDE.push(r)); return HREPONSE; },
    ocr_lancer: async (...a) => { HLANCES.push(a); return { file: {} }; },
  };
  window.pywebview = { api: API };

  const $h = s => document.querySelector(s);
  const dq = $h("#d-tx-quoi");
  exiger(dq, "le dialogue #d-tx-quoi est absent de la page");
  const Q = s => dq.querySelector(s);
  const lesToasts = () => $h("#toasts").children.map(t => {
    const m = String(t.innerHTML).match(/<span>([\s\S]*)<\/span>/); return m ? Hdecode(m[1]) : ""; });
  const genres = () => $h("#toasts").children.map(t => t.className);
  const ouvre = async (origine, etat) => {
    TX = etat; HE = etat;
    (origine || $h("#tx-quoi")).dispatchEvent({ type: "click" });
    await Hattendre(25);
  };
  const ferme = async () => { dq.querySelector("[data-ferme]").dispatchEvent({ type: "click" }); await Hattendre(10); };
  const clique = async sel => { Q(sel).dispatchEvent({ type: "click" }); await Hattendre(25); };

  const COMPTEURS = { documents: 3, pages: 9, a_verifier: 1, a_preparer: 2, pages_a_preparer: 5,
                      octets_texte: 6710886, orphelins: 0 };
  const MOTEUR = { present: true, version: "5.5.3", source: "registre", exe: "x", langues: ["fra"],
                   langues_effectives: "fra", repli: false, message: "" };
  const ETAT = { moteur: MOTEUR, active: true, mode_pdf: "aucun", occupe: false, compteurs: COMPTEURS };
  const ETAT_ABSENT = { moteur: Object.assign({}, MOTEUR, { present: false }), active: false, mode_pdf: "aucun",
                        occupe: false, compteurs: COMPTEURS };
  const ETAT_ZERO = { moteur: MOTEUR, active: false, mode_pdf: "aucun", occupe: false,
                      compteurs: { documents: 0, pages: 0, a_verifier: 0, a_preparer: 0, pages_a_preparer: 0,
                                   octets_texte: 0, orphelins: 0 } };
  const REPONSE = { image: "data:image/png;base64,AAAA", largeur: 900, hauteur: 600,
                    texte: "Ligne <b>un</b>\nLigne deux", confiance: 0.916, qualite: "bon", source: "ocr",
                    chemin: "Cours A/S1/a.pdf", nom: "a<i>.pdf", page: 2, exemple: false };

  /* ---- 1. ouverture depuis la carte, avec les chiffres de la bibliotheque ---- */
  exiger(Q(".tx-quoi-essai"), "le bouton d'essai (.tx-quoi-essai) est absent du panneau");
  exiger(Q(".tx-quoi-avant-chiffres") && Q(".tx-quoi-apres-chiffres"), "les deux lignes de chiffres sont absentes");
  exiger(dq.open === false, "le panneau est ferme au depart");
  await ouvre($h("#tx-quoi"), ETAT);
  exiger(dq.open === true, "le lien #tx-quoi de la carte ouvre le panneau");
  exiger(Hactif === Q(".tx-quoi-essai"), "le focus va au bouton d'essai a l'ouverture");
  assert.strictEqual(texte(Q(".tx-quoi-avant-chiffres")), "Des images : 9 pages");
  assert.strictEqual(texte(Q(".tx-quoi-apres-chiffres")), "Du texte : 9 pages, 6,4 Mo");
  exiger(Q(".tx-quoi-note-chiffres").hidden === true, "chiffres reels : aucune note d'exemple");
  assert.strictEqual(texte(Q(".tx-quoi-essai")), "Essayer sur une page de mon cours");
  exiger(Q(".tx-quoi-apercu").hidden === true, "aucun apercu avant le clic");
  assert.deepStrictEqual(HAPERCUS, [], "ouvrir ne lance aucune extraction");

  /* ---- 2. fermeture par le bouton du dialogue (app.js) : le focus revient au lien ---- */
  await ferme();
  exiger(dq.open === false, "le bouton data-ferme ferme le panneau");
  exiger(Hactif === $h("#tx-quoi"), "le focus revient a l'element qui a ouvert le panneau");

  /* ---- 3. ouverture depuis l'etat vide de Mes textes ---- */
  const lienVide = document.querySelector("#tx-vide [data-action=\"quoi\"]");
  exiger(lienVide, "l'etat vide de Mes textes porte un lien data-action=\"quoi\"");
  await ouvre(lienVide, ETAT);
  exiger(dq.open === true, "le lien de l'etat vide ouvre le panneau");
  await ferme();
  exiger(Hactif === lienVide, "le focus revient au lien de l'etat vide");

  /* ---- 4. exemple generique annonce, jamais les chiffres inventes pris pour les siens ---- */
  await ouvre(null, ETAT_ZERO);
  assert.strictEqual(texte(Q(".tx-quoi-avant-chiffres")), "Une image de 24 pages, 18 Mo", "le texte du plan revient");
  assert.strictEqual(texte(Q(".tx-quoi-apres-chiffres")), "Un fichier texte de 24 pages, environ 90 Ko");
  exiger(Q(".tx-quoi-note-chiffres").hidden === false, "l'exemple generique est annonce");
  assert.strictEqual(texte(Q(".tx-quoi-note-chiffres")), "Exemple, pas un de tes documents.");
  assert.strictEqual(texte(Q(".tx-quoi-essai")), "Voir un exemple", "aucun scan detecte");
  await ferme();
  await ouvre(null, ETAT_ABSENT);
  assert.strictEqual(texte(Q(".tx-quoi-essai")), "Voir un exemple", "moteur absent : un exemple, pas un essai");
  await ferme();
  /* TX inconnu : le panneau lit l'etat lui-meme, sans l'ecrire dans TX */
  TX = null; HE = ETAT;
  $h("#tx-quoi").dispatchEvent({ type: "click" }); await Hattendre(25);
  assert.strictEqual(texte(Q(".tx-quoi-avant-chiffres")), "Des images : 9 pages", "etat lu a l'ouverture");
  exiger(TX === null, "le panneau n'ecrit pas TX");
  await ferme();

  /* ---- 5. l'essai : un seul appel, sans argument, jamais ocr_lancer ---- */
  await ouvre(null, ETAT);
  globalThis.txPreparer = () => { HPREP++; };
  HGARDE = []; HREPONSE = REPONSE;
  Q(".tx-quoi-essai").dispatchEvent({ type: "click" });
  Q(".tx-quoi-essai").dispatchEvent({ type: "click" });               // double clic : un seul appel
  await Hattendre(25);
  assert.deepStrictEqual(HAPERCUS, [[]], "ocr_apercu() sans argument, une seule fois : " + JSON.stringify(HAPERCUS));
  exiger(Q(".tx-quoi-essai").disabled === true, "le bouton est desactive pendant la lecture");
  assert.strictEqual(texte(Q(".tx-quoi-essai")), "Lecture de la page...");
  exiger(Q(".tx-quoi-apercu").hidden === true, "rien ne s'affiche avant la reponse");
  HGARDE.splice(0).forEach(f => f()); HGARDE = null;
  await Hattendre(25);
  exiger(Q(".tx-quoi-essai").disabled === false, "le bouton est reactive");
  assert.strictEqual(texte(Q(".tx-quoi-essai")), "Essayer sur une page de mon cours");
  exiger(Q(".tx-quoi-apercu").hidden === false, "l'apercu s'affiche");
  assert.strictEqual(Q(".tx-quoi-image").getAttribute("src"), "data:image/png;base64,AAAA", "image de la page");
  exiger(Q(".tx-quoi-image").hidden === false && Q(".tx-quoi-modele").hidden === true, "image reelle, pas le modele");
  assert.strictEqual(Q(".tx-quoi-image").getAttribute("alt"), "Aperçu de la page 2 de a<i>.pdf.", "texte alternatif");
  assert.strictEqual(texte(Q(".tx-quoi-texte")), "Ligne <b>un</b>\nLigne deux", "texte extrait, brut");
  assert.strictEqual(Q(".tx-quoi-texte").children.length, 0, "aucun HTML construit avec le texte de l'API");
  exiger(Q(".tx-quoi-note-apercu").hidden === true, "ce n'est pas un exemple : aucune note");
  const conf = Q(".tx-quoi-confiance");
  exiger(conf.hidden === false, "la ligne de confiance est visible");
  exiger(plat_texte(texte(conf)).startsWith("Confiance : 92 %"), "confiance chiffree : " + plat_texte(texte(conf)));
  const badge = conf.querySelector(".badge-qualite");
  exiger(badge && texte(badge) === "Bon" && badge.classList.contains("bon"), "le mot est ecrit a cote : Bon");
  assert.deepStrictEqual(HLANCES, [], "l'essai ne met rien en file (aucun ocr_lancer)");

  /* ---- 6. copie de l'extrait, puis garde de l'extrait vide ---- */
  HCOPIE = "AVANT";
  const avant = $h("#toasts").children.length;
  await clique(".tx-quoi-copier");
  assert.strictEqual(HCOPIE, "Ligne <b>un</b>\nLigne deux", "Copier cet extrait colle le texte extrait");
  assert.deepStrictEqual(lesToasts().slice(avant), ["Copié : 26 caractères."]);
  assert.deepStrictEqual(genres().slice(avant), ["toast bon"]);

  /* ---- 7. Preparer tout le cours : txPreparer de U4, jamais ocr_lancer ---- */
  exiger(Q(".tx-quoi-preparer").hidden === false, "avec txPreparer, le bouton est visible");
  await clique(".tx-quoi-preparer");
  assert.strictEqual(HPREP, 1, "le bouton appelle txPreparer");
  assert.deepStrictEqual(HLANCES, [], "U3 ne lance rien lui-meme");

  /* ---- 8. fermeture : l'apercu est efface, rouvrir ne relance rien ---- */
  await ferme();
  exiger(Q(".tx-quoi-apercu").hidden === true, "l'apercu disparait a la fermeture");
  assert.strictEqual(Q(".tx-quoi-image").getAttribute("src"), null, "l'image est retiree");
  assert.strictEqual(texte(Q(".tx-quoi-texte")), "", "le texte est efface");
  await ouvre(null, ETAT);
  exiger(Q(".tx-quoi-apercu").hidden === true, "rouvrir ne montre pas l'ancien apercu");
  assert.strictEqual(HAPERCUS.length, 1, "rouvrir ne relance pas l'extraction");
  await ferme();

  /* ---- 9. sans txPreparer, le bouton est masque ---- */
  delete globalThis.txPreparer;
  await ouvre(null, ETAT);
  await clique(".tx-quoi-essai");
  exiger(Q(".tx-quoi-apercu").hidden === false, "second essai affiche l'apercu");
  exiger(Q(".tx-quoi-preparer").hidden === true, "sans txPreparer, Preparer tout le cours est masque");
  assert.strictEqual(HAPERCUS.length, 2);

  /* ---- 10. confiance moyenne et confiance inconnue ---- */
  HREPONSE = Object.assign({}, REPONSE, { confiance: 0.624, qualite: "a_verifier" });
  await clique(".tx-quoi-essai");
  const conf2 = Q(".tx-quoi-confiance");
  exiger(plat_texte(texte(conf2)).startsWith("Confiance : 62 %"), "62 % : " + plat_texte(texte(conf2)));
  const badge2 = conf2.querySelector(".badge-qualite");
  exiger(texte(badge2) === "À vérifier" && badge2.classList.contains("a-verifier"), "mot A verifier");
  HREPONSE = Object.assign({}, REPONSE, { confiance: null, qualite: "vide", source: "texte" });
  await clique(".tx-quoi-essai");
  exiger(Q(".tx-quoi-confiance").hidden === true, "confiance inconnue : la ligne n'affiche rien d'invente");

  /* ---- 11. extrait vide : phrase d'etat, aucune copie, presse-papiers intact ---- */
  HREPONSE = Object.assign({}, REPONSE, { texte: "   ", confiance: 0.3, qualite: "difficile" });
  await clique(".tx-quoi-essai");
  assert.strictEqual(texte(Q(".tx-quoi-texte")), "Aucun texte reconnu sur cette page.");
  HCOPIE = "AVANT";
  const n0 = $h("#toasts").children.length;
  await clique(".tx-quoi-copier");
  assert.strictEqual(HCOPIE, "AVANT", "un extrait vide n'ecrase pas le presse-papiers");
  assert.deepStrictEqual(lesToasts().slice(n0), ["Aucun texte à copier."]);
  assert.deepStrictEqual(genres().slice(n0), ["toast critique"]);

  /* ---- 12. exemple embarque : annonce, modele a la place de l'image, pas de copie ---- */
  HREPONSE = { image: "", largeur: 0, hauteur: 0, texte: "", confiance: null, qualite: "vide", source: "vide",
               chemin: "", nom: "", page: 1, exemple: true };
  await clique(".tx-quoi-essai");
  exiger(Q(".tx-quoi-apercu").hidden === false, "l'exemple s'affiche");
  exiger(Q(".tx-quoi-note-apercu").hidden === false, "l'apercu dit que c'est un exemple");
  assert.strictEqual(texte(Q(".tx-quoi-note-apercu")), "Exemple, pas un de tes documents.");
  exiger(Q(".tx-quoi-image").hidden === true && Q(".tx-quoi-modele").hidden === false, "le modele remplace l'image");
  assert.strictEqual(Q(".tx-quoi-modele").getAttribute("aria-label"), "Exemple de page scannée.");
  assert.strictEqual(texte(Q(".tx-quoi-texte")),
    "Une institution est un ensemble de règles qui dure dans le temps.");
  exiger(Q(".tx-quoi-confiance").hidden === true, "aucune confiance inventee pour un exemple");
  exiger(Q(".tx-quoi-copier").hidden === true, "un exemple ne se copie pas");
  HREPONSE = Object.assign({}, HREPONSE, { texte: "Texte d'exemple venu de l'API" });
  await clique(".tx-quoi-essai");
  HCOPIE = "AVANT";
  const n3 = $h("#toasts").children.length;
  await clique(".tx-quoi-copier");                     // le bouton est masque, mais un clic ne copie rien d'un exemple
  assert.strictEqual(HCOPIE, "AVANT", "l'exemple n'ecrit jamais le presse-papiers");
  assert.deepStrictEqual(lesToasts().slice(n3), ["Aucun texte à copier."]);
  HREPONSE = Object.assign({}, HREPONSE, { texte: "" });
  await clique(".tx-quoi-essai");
  HREPONSE = REPONSE;
  await clique(".tx-quoi-essai");
  exiger(Q(".tx-quoi-copier").hidden === false && Q(".tx-quoi-note-apercu").hidden === true,
         "une vraie page rend le bouton de copie et retire la note");

  /* ---- 13. reponse d'erreur de l'API : la phrase, telle quelle ---- */
  HREPONSE = { erreur: "Ce PDF est abîmé et n'a pas pu être ouvert. Les autres documents continuent." };
  await clique(".tx-quoi-essai");
  const n1 = $h("#toasts").children.length;
  assert.deepStrictEqual(lesToasts().slice(n1 - 1), [HREPONSE.erreur], "la phrase de l'API, sans reformulation");
  assert.strictEqual(genres()[n1 - 1], "toast critique");
  exiger(Q(".tx-quoi-apercu").hidden === true, "une erreur n'affiche aucun apercu (l'ancien est efface)");
  exiger(Q(".tx-quoi-essai").disabled === false, "le bouton est reactive apres une erreur");
  assert.strictEqual(texte(Q(".tx-quoi-essai")), "Essayer sur une page de mon cours");
  HREPONSE = null;
  await clique(".tx-quoi-essai");
  exiger(Q(".tx-quoi-apercu").hidden === true && Q(".tx-quoi-essai").disabled === false, "reponse vide : rien ne casse");

  /* ---- 14. reponse tardive : le panneau ferme entre-temps n'affiche rien ---- */
  HREPONSE = REPONSE; HGARDE = [];
  const n2 = HAPERCUS.length;
  Q(".tx-quoi-essai").dispatchEvent({ type: "click" });
  await Hattendre(15);
  assert.strictEqual(HAPERCUS.length, n2 + 1);
  await ferme();
  HGARDE.splice(0).forEach(f => f()); HGARDE = null;
  await Hattendre(30);
  exiger(Q(".tx-quoi-apercu").hidden === true, "une reponse qui arrive apres la fermeture ne s'affiche pas");
  exiger(Q(".tx-quoi-essai").disabled === false, "le bouton est libre apres une reponse tardive");
  await ouvre(null, ETAT);
  await clique(".tx-quoi-essai");
  assert.strictEqual(HAPERCUS.length, n2 + 2, "un nouvel essai part bien");
  exiger(Q(".tx-quoi-apercu").hidden === false, "et s'affiche");
  await ferme();

  /* ---- 15. au total, aucune ecriture ni mise en file ---- */
  assert.deepStrictEqual(HLANCES, [], "aucun ocr_lancer pendant tout le parcours");
  console.log("OK");
  process.exit(0);
})().catch(e => { console.error(e && e.stack ? e.stack : e); process.exit(1); });
"""


if __name__ == "__main__":
    unittest.main()
