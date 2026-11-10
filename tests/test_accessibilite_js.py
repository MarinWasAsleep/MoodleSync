"""Tests de la verification, du groupe de reglages de l'extraction, de l'accessibilite et du theme (tache U5).

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque. Trois familles de tests, comme tests/test_preparer_js.py.

Statiques : `window.etatVerification()` rend la cle `textes` du contrat 3.4 et son `pret` tient compte
de `txPret` et de `txOccupe`, `onglets` lit `data-onglet` (ecart 179) ; le groupe « Texte des cours
(OCR) » du tiroir porte ses controles (dont le choix du mode des PDF, ecart 276) et passe par `ocr_regler`,
`ocr_choisir_exe` et `ocr_installer` ; aucun des sept mots interdits du contrat 5 hors de ce groupe ; les huit classes de
U4 sont styees ; les deux boutons principaux de la carte ne peuvent pas se montrer ensemble ; aucune
couleur litterale dans les blocs nouveaux ; les contrastes calcules depuis les variables des deux
themes passent 4,5 (ecart 178) ; la ligne de resultat et le menu sont atteignables au clavier (ecart
195).

Parcours (Node, s'ignore sans `node`) : la page entiere d'index.html est lue et rangee dans le DOM
factice de `tests/test_textes_js.py`, puis les vraies fonctions de `commun.js`, `sync.js`,
`textes.js` et `app.js` tournent contre une doublure de l'API. Le script s'ecrit dans un dossier
temporaire, supprime dans un `finally`.

Ce que ces tests ne mesurent pas : aucune vraie fenetre pywebview, aucun navigateur (donc ni rendu,
ni `<dialog>` natif, ni focus reel, ni lecture d'ecran), aucun vrai moteur, Windows et macOS non
executes.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, re, shutil, subprocess, sys, tempfile, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests import test_textes_js as tj
from tests import test_quoi_js as qj

INTERFACE = tj.INTERFACE
INTERDITS = tj.INTERDITS
HTML_CONSTRUIT = tj.HTML_CONSTRUIT
lire = tj.lire
plat = tj.plat
corps_de = qj.corps_de

# Controles du groupe « Texte des cours (OCR) » (contrat 3.4, ligne Reglages).
IDS_TIROIR = ("r-tx-ocr", "r-tx-ocr-moteur", "r-tx-ocr-exe", "r-tx-ocr-choisir", "r-tx-ocr-installer",
              "r-tx-ocr-actif", "r-tx-ocr-apres", "r-tx-ocr-langues", "r-tx-ocr-pdf", "r-tx-ocr-pdf-aide")

# Classes ecrites par U4, qui n'avaient aucune regle.
CLASSES_U4 = ("tx-carte-nombres", "tx-carte-moteur", "tx-carte-travail", "tx-carte-document",
              "tx-carte-rang", "tx-carte-page", "tx-carte-pause", "tx-preparer-nombres")

# Paires (selecteur, texte, fond, fond ecrit dans la regle) des blocs des textes et des blocs nouveaux :
# calculees depuis les variables de la feuille, seuil 4,5 pour du texte (cycle de contraste WCAG 2.x).
# Le quatrieme champ vaut False quand la regle n'ecrit pas de fond : le texte repose alors sur la
# surface de son conteneur (la carte, ou le bloc de travail).
PAIRES = (
    (".badge-qualite", "--texte-2", "--surface", True),
    (".badge-qualite.bon", "--bon-texte", "--bon-doux", True),
    (".badge-qualite.a-verifier", "--alerte", "--alerte-doux", True),
    (".badge-qualite.difficile", "--texte", "--critique-doux", True),
    (".badge-qualite.cherchable", "--texte", "--accent-doux", True),
    ("#tx-badge", "--texte", "--accent-doux", True),
    (".tx-prive", "--texte-2", "--fond", False),
    (".tx-resultats", "--texte-2", "--fond", False),
    (".tx-carte-nombres", "--texte", "--carte", False),
    (".tx-carte-moteur", "--alerte", "--alerte-doux", True),
    (".tx-carte-document", "--texte", "--surface", False),
    (".tx-carte-rang", "--texte-2", "--surface", False),
    (".tx-carte-pause", "--alerte", "--alerte-doux", True),
    (".tx-preparer-nombres", "--texte", "--carte", False),
)

VARIABLES = ("--fond", "--surface", "--carte", "--bord", "--bord-fort", "--texte", "--texte-2",
             "--texte-3", "--accent", "--accent-doux", "--accent-piste", "--bon", "--bon-texte",
             "--bon-doux", "--critique", "--critique-doux", "--alerte", "--alerte-doux")


def bloc_apres(source, marque):
    """Bloc `{ ... }` qui suit la premiere occurrence de `marque` (accolades equilibrees), ou ''."""
    i = source.find(marque)
    if i < 0:
        return ""
    j = source.find("{", i)
    if j < 0:
        return ""
    profondeur = 0
    for k in range(j, len(source)):
        if source[k] == "{":
            profondeur += 1
        elif source[k] == "}":
            profondeur -= 1
            if profondeur == 0:
                return source[j:k + 1]
    return ""


def regle(css, selecteur):
    """Regle CSS dont le selecteur ouvre une ligne ou suit une virgule d'une liste, ou ''."""
    for m in re.finditer(re.escape(selecteur), css):
        debut = css.rfind("\n", 0, m.start()) + 1
        avant = css[debut:m.start()].strip()
        if avant and not avant.endswith(","):
            continue
        j = css.find("{", m.end())
        fin = css.find("}", j) if j >= 0 else -1
        if j < 0 or fin < 0:
            continue
        return css[debut:fin + 1]
    return ""


def _canal(valeur):
    valeur = valeur / 255
    return valeur / 12.92 if valeur <= 0.03928 else ((valeur + 0.055) / 1.055) ** 2.4


def luminance(couleur):
    hexa = couleur.lstrip("#")
    if len(hexa) == 3:
        hexa = "".join(c * 2 for c in hexa)
    r, v, b = (int(hexa[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _canal(r) + 0.7152 * _canal(v) + 0.0722 * _canal(b)


def contraste(a, b):
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def variables(css, ouverture, fermeture="}"):
    """Variables de couleur d'un bloc de la feuille : {--nom: #hex}."""
    debut = css.find(ouverture)
    if debut < 0:
        return {}
    fin = css.find(fermeture, debut)
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{3,8})", css[debut:fin]))


def themes(css):
    """(clair, sombre) : les deux jeux de variables de la feuille."""
    clair = variables(css, ":root {")
    sombre = variables(css, ':root[data-theme="dark"] {')
    return clair, sombre


class U5Statique(unittest.TestCase):
    """app.js, style.css, textes.js et index.html : ce que la page doit et doit a la verification."""

    @classmethod
    def setUpClass(cls):
        cls.app = lire(os.path.join(INTERFACE, "app.js"))
        cls.page = lire(os.path.join(INTERFACE, "index.html"))
        cls.css = lire(os.path.join(INTERFACE, "style.css"))
        cls.textes = lire(os.path.join(INTERFACE, "textes.js"))
        cls.sync = lire(os.path.join(INTERFACE, "sync.js"))

    # ------------------------------------------------------------------ verification
    def test_etat_verification_couvre_l_onglet(self):
        sans = tj.sans_commentaires(self.app)
        bloc = bloc_apres(sans, "window.etatVerification")
        self.assertTrue(bloc, "window.etatVerification est introuvable dans app.js")
        self.assertIn("textes:", bloc, "la cle `textes` du contrat 3.4 manque")
        dedans = bloc_apres(bloc, "textes:")
        self.assertTrue(dedans, "le bloc `textes` de la verification est vide")
        for cle in ("documents", "pages", "a_verifier", "file", "erreur"):
            with self.subTest(cle=cle):
                self.assertRegex(dedans, r"\b%s\s*:" % cle, "champ manquant : %s" % cle)
        self.assertIn("TX", bloc, "les compteurs viennent de TX (dernier ocr_etat)")
        self.assertIn("compteurs", bloc)
        self.assertIn(".etat", bloc.split("file", 1)[-1], "`file` est file.etat")
        # `pret` exige txPret et !txOccupe (contrat 3.4, ligne Verification).
        ligne_pret = [l for l in bloc.splitlines() if l.strip().startswith("pret:")]
        self.assertTrue(ligne_pret, "la ligne `pret` est introuvable")
        self.assertIn("txPret", ligne_pret[0], "pret exige txPret")
        self.assertIn("!txOccupe", ligne_pret[0], "pret exige !txOccupe")
        for cle in ("onglet", "erreur", "connecte", "cours", "semaine_active", "cartes", "lectures",
                    "synchro", "version", "onglets", "horaire"):
            with self.subTest(cle=cle):
                self.assertRegex(bloc, r"\b%s\s*:" % cle, "aucune cle existante ne disparait : %s" % cle)

    def test_onglets_lus_dans_data_onglet(self):
        """Ecart 179 : `#tx-badge` est dans le bouton, donc `textContent` rendrait « Mes textes3 »."""
        sans = tj.sans_commentaires(self.app)
        bloc = bloc_apres(sans, "window.etatVerification")
        ligne = [l for l in bloc.splitlines() if l.strip().startswith("onglets:")]
        self.assertTrue(ligne, "la ligne `onglets` est introuvable")
        self.assertRegex(ligne[0], r"data-onglet|dataset\.onglet", "les noms se lisent dans data-onglet")
        self.assertNotIn("textContent", ligne[0], "le texte du bouton porte la pastille")

    # ------------------------------------------------------------------ groupe de reglages
    def test_le_groupe_de_reglages_de_l_extraction(self):
        self.assertIn("Texte des cours (OCR)", self.app, "le contrat 3.4 nomme le groupe ainsi")
        self.assertIn("function remplirTiroir(", self.app)
        tiroir = corps_de(tj.sans_commentaires(self.app), "remplirTiroir") or ""
        self.assertTrue(tiroir, "remplirTiroir est la fonction du tiroir")
        for ident in IDS_TIROIR:
            with self.subTest(ident=ident):
                self.assertIn(ident, self.app, "controle absent du groupe : %s" % ident)
        sans = tj.sans_commentaires(self.app)
        for appel in ('api().ocr_etat()', 'api().ocr_regler(', 'api().ocr_choisir_exe()',
                      'api().ocr_installer()'):
            with self.subTest(appel=appel):
                self.assertIn(appel, sans, "le groupe passe par %s" % appel)
        self.assertIn('"ocr_apres_sync"', sans, "la case de l'extraction automatique (ecart 216)")
        self.assertIn('"ocr_langues"', sans, "les langues du groupe")
        self.assertIn('"ocr_pdf"', sans, "le choix du mode des PDF, avec son consentement separe (ecart 276)")
        self.assertIn("confirmer(", corps_de(sans, "txReglerMode") or "", "le mode `remplacer` passe par confirmer()")

    def test_le_mode_des_pdf_a_une_aide_et_une_etiquette(self):
        """Ecart 276 : la liste a une etiquette liee, et la phrase sur l'absence de copie locale est decrite par aria."""
        sans = tj.sans_commentaires(self.app)
        self.assertIn('"r-tx-ocr-pdf"', sans)
        self.assertRegex(sans, r'setAttribute\("for", "r-tx-ocr-pdf"\)', "etiquette liee a la liste")
        self.assertRegex(sans, r'setAttribute\("aria-describedby", "r-tx-ocr-pdf-aide"\)', "aide liee a la liste")
        self.assertIn("Aucune copie de l'original", self.app, "l'avertissement dit qu'aucune copie locale n'est gardee")

    def test_aucun_mot_interdit_hors_du_groupe(self):
        """Contrat 5 : OCR et Tesseract ne s'ecrivent que dans le groupe des reglages."""
        for nom, source in (("app.js", self.app), ("textes.js", self.textes), ("sync.js", self.sync),
                            ("index.html", self.page)):
            sans = tj.sans_commentaires(source)
            sans = re.sub(r"ocr_\w+", " ", sans)                  # identifiants de l'API
            sans = sans.replace('"ocr"', " ")                     # la cle de ocr_regler, contrat 3.2
            sans = re.sub(r"#?r-tx[\w-]*", " ", sans)             # identifiants du tiroir
            sans = sans.replace("Texte des cours (OCR)", " ")     # titre du groupe
            bas = sans.lower()
            for mot in INTERDITS:
                with self.subTest(fichier=nom, mot=mot):
                    self.assertNotIn(mot, bas)
            for tiret in (chr(0x2013), chr(0x2014)):
                with self.subTest(fichier=nom, tiret=hex(ord(tiret))):
                    self.assertNotIn(tiret, source)

    # ------------------------------------------------------------------ accessibilite
    def test_ligne_de_resultat_et_menu_au_clavier(self):
        sans = tj.sans_commentaires(self.textes)
        trouve = corps_de(sans, "txTrouve") or ""
        self.assertTrue(trouve, "txTrouve construit une ligne de resultat")
        self.assertIn("tabIndex", trouve, "la ligne de resultat est atteignable (ecart 195)")
        self.assertIn('setAttribute("role", "button")', trouve, "la ligne porte un role")
        self.assertRegex(trouve, r'"Enter"', "Entree ouvre le resultat")
        self.assertRegex(trouve, r'" "', "l'espace ouvre le resultat")
        menu = corps_de(sans, "txMenuCreer") or ""
        self.assertTrue(menu, "txMenuCreer ouvre un menu")
        self.assertIn("aria-expanded", menu, "le bouton d'ouverture annonce son menu")
        self.assertIn("aria-haspopup", menu)
        focus = corps_de(sans, "txMenuFocus") or ""
        self.assertRegex(focus, r"\.focus\(\)", "le focus entre dans le menu")
        quitter = corps_de(sans, "txFermerMenu") or ""
        self.assertIn("aria-expanded", quitter, "la fermeture remet le bouton dans son etat")
        self.assertIn('"Escape"', sans, "Escape ferme un menu")
        escape = re.search(r'"Escape"[\s\S]{0,400}?txFermerMenu\(\)', sans)
        self.assertIsNotNone(escape, "Escape ferme le menu et rend le focus")

    def test_les_interrupteurs_restent_dans_la_tabulation(self):
        """Ecart 233 : un champ `display: none` sort de la tabulation (deduit, aucun navigateur).

        Le champ reste dans l'arbre, invisible et positionne, et l'anneau de focus va au rail,
        comme `.case input` plus haut dans la feuille.
        """
        texte = regle(self.css, ".interrupteur input")
        self.assertTrue(texte, "regle introuvable : .interrupteur input")
        self.assertNotIn("display: none", texte, "un champ ainsi masque n'est ni tabulable ni activable")
        self.assertNotIn("visibility: hidden", texte, "visibility cache retire aussi le champ de la tabulation")
        self.assertRegex(texte, r"position:\s*absolute", "le champ est masque par position, pas retire du flux")
        self.assertRegex(texte, r"opacity:\s*0", "le champ reste dans l'arbre, invisible")
        anneau = regle(self.css, ".interrupteur input:focus-visible")
        self.assertTrue(anneau, "le rail recoit un anneau de focus")
        self.assertIn("outline", anneau)
        self.assertIn("var(--accent)", anneau)

    def test_focus_rendu_apres_le_consentement_depuis_le_panneau(self):
        """Ecart 222 : la troisieme entree passe une origine a txPreparer."""
        sans = tj.sans_commentaires(self.textes)
        corps = corps_de(sans, "txQuoiPreparer") or ""
        self.assertTrue(corps, "txQuoiPreparer est la troisieme entree du consentement")
        self.assertRegex(corps, r"txPreparer\(\s*txQuoiOrigine", "l'origine du panneau est transmise")

    # ------------------------------------------------------------------ theme et style
    def test_les_classes_de_u4_sont_stylees(self):
        for classe in CLASSES_U4:
            with self.subTest(classe=classe):
                self.assertRegex(self.css, r"\.%s\b[^{]*\{" % re.escape(classe),
                                 "aucune regle pour .%s" % classe)

    def test_les_deux_boutons_principaux_ne_se_montrent_pas_ensemble(self):
        """Moteur absent et file en pause : Reprendre et Installer sont offerts ensemble."""
        motif = r'\.tx-carte[^{]*:has\(\[data-action="installer"\][^{]*' \
                r'[^{]*\[data-action="reprendre"\][^{]*\{[^}]*\}'
        m = re.search(motif, self.css)
        self.assertIsNotNone(m, "une regle CSS doit demettre Reprendre quand Installer est visible")
        self.assertIn("var(--carte)", m.group(0), "elle reprend le style d'un bouton ordinaire")
        self.assertIn("var(--bord-fort)", m.group(0))

    def test_aucune_couleur_litterale_dans_les_blocs_nouveaux(self):
        debut = self.css.rfind("U5")
        self.assertGreater(debut, 0, "le bloc U5 est annonce par un commentaire contenant « U5 »")
        bloc = self.css[debut:]
        self.assertFalse(re.search(r"#[0-9a-fA-F]{3,8}\b", bloc), "aucune couleur en dur dans le bloc U5")
        self.assertNotIn("rgb(", bloc)
        self.assertNotIn("url(", bloc)
        self.assertNotIn("prefers-color-scheme", bloc)
        self.assertNotIn("[data-theme", bloc)
        self.assertIn("var(--", bloc)
        # Les regles corrigees pour le contraste (ecart 178) ne prennent que des variables.
        for selecteur in (".badge-qualite.difficile", ".badge-qualite.cherchable", "#tx-badge",
                          ".tx-prive", ".tx-resultats"):
            with self.subTest(selecteur=selecteur):
                texte = regle(self.css, selecteur)
                self.assertTrue(texte, "regle introuvable : %s" % selecteur)
                self.assertFalse(re.search(r"#[0-9a-fA-F]{3,8}\b", texte), "couleur en dur : %s" % selecteur)
                self.assertNotIn("rgb(", texte)
                self.assertIn("var(--", texte)

    def test_contraste_des_badges_et_des_nouveaux_blocs(self):
        clair, sombre = themes(self.css)
        self.assertGreaterEqual(len(clair), 16, "variables du theme clair incompletes : %s" % sorted(clair))
        self.assertGreaterEqual(len(sombre), 12, "variables du theme sombre incompletes : %s" % sorted(sombre))
        for nom, jeu in (("clair", clair), ("sombre", sombre)):
            for selecteur, texte_var, fond_var, fond_dans_la_regle in PAIRES:
                with self.subTest(theme=nom, selecteur=selecteur):
                    self.assertIn(texte_var, jeu, "variable absente : %s" % texte_var)
                    self.assertIn(fond_var, jeu, "variable absente : %s" % fond_var)
                    regle_css = regle(self.css, selecteur)
                    self.assertIn("var(%s)" % texte_var, regle_css, "%s ne prend pas %s" % (selecteur, texte_var))
                    if fond_dans_la_regle:
                        self.assertIn("var(%s)" % fond_var, regle_css,
                                      "%s ne prend pas %s" % (selecteur, fond_var))
                    rapport = contraste(jeu[texte_var], jeu[fond_var])
                    self.assertGreaterEqual(round(rapport, 2), 4.5,
                                            "%s en %s : %.2f" % (selecteur, nom, rapport))

    # ------------------------------------------------------------------ forme
    def test_fichiers_en_lf(self):
        for nom in ("app.js", "textes.js", "style.css", "index.html"):
            with self.subTest(fichier=nom):
                with open(os.path.join(INTERFACE, nom), "rb") as f:
                    self.assertNotIn(b"\r", f.read())
        with open(os.path.abspath(__file__), "rb") as f:
            self.assertNotIn(b"\r", f.read())

    def test_appels_api_de_app_js(self):
        from moodlesync.api_textes import ApiTextes
        appels = sorted(set(re.findall(r"api\(\)\.(ocr_\w+)\(", tj.sans_commentaires(self.app))))
        self.assertGreaterEqual(len(appels), 4, "les appels du groupe : %s" % appels)
        for nom in appels:
            with self.subTest(appel=nom):
                self.assertTrue(callable(getattr(ApiTextes, nom, None)), "ApiTextes.%s n'existe pas" % nom)

    # ------------------------------------------------------------------ parcours sur DOM factice
    @unittest.skipUnless(shutil.which("node"), "node absent : parcours sur DOM factice non execute")
    def test_parcours_de_la_verification_sur_dom_factice(self):
        node = shutil.which("node") or "node"
        coupe = tj.ENTETE.find("/* ---- arbre de la page")
        self.assertGreater(coupe, 0, "marqueur de l'arbre de la page introuvable dans l'entete de test_textes_js")
        # sync.js declare SC lui-meme : la doublure de l'entete n'est pas gardee.
        entete = re.sub(r"let SC = \[.*?\];\n", "", tj.ENTETE[:coupe], count=1, flags=re.S)
        self.assertNotIn("let SC =", entete)
        dossier = tempfile.mkdtemp(prefix="parcours-u5-")
        script = os.path.join(dossier, "_parcours_u5.js")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(entete + "\n" + MANQUES + "\n" + qj.OUTILS + "\n" + CASES_COCHEES + "\n")
                for nom in ("commun.js", "sync.js", "textes.js", "app.js"):
                    f.write("\n/* ===== %s ===== */\n" % nom)
                    f.write(lire(os.path.join(INTERFACE, nom)).replace("\r\n", "\n"))
                f.write("\n" + PARCOURS)
            r = subprocess.run([node, script, INTERFACE], capture_output=True, text=True, timeout=180)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        self.assertEqual(r.returncode, 0, "le parcours a echoue :\n%s\n%s" % (r.stdout, r.stderr))
        self.assertIn("OK", r.stdout)


# Ce que le DOM factice de test_textes_js ne fournit pas encore et dont la page se sert : `matches`
# pour les ecouteurs `change` de sync.js, et les variables de semaine.js, qui n'est pas chargee ici.
MANQUES = r"""
if (!HElement.prototype.matches) HElement.prototype.matches = function (sel) { return Hsimple(this, sel); };
let occupe = false, semainePrete = true;
"""

# Un navigateur coche les cases qui portent `checked` dans le HTML ; le DOM factice ne le fait pas.
CASES_COCHEES = r"""
for (const el of Hdescend(document.body)) if (el.hasAttribute("checked")) el.checked = true;
"""

PARCOURS = r"""
(async () => {
  const exiger = (cond, message) => { if (!cond) throw new assert.AssertionError({ message: message }); };
  const plat_texte = t => String(t).replace(/\s+/g, " ").trim();
  const $h = s => document.querySelector(s);
  const copie = o => JSON.parse(JSON.stringify(o));
  const fusion = (base, sur) => {
    const r = copie(base);
    for (const k of Object.keys(sur || {})) r[k] = (sur[k] && typeof sur[k] === "object" && !Array.isArray(sur[k]) && r[k])
      ? fusion(r[k], sur[k]) : sur[k];
    return r;
  };
  const visible = el => !!el && el.hidden === false;
  const lesToasts = () => $h("#toasts").children.map(t => {
    const m = String(t.innerHTML).match(/<span>([\s\S]*)<\/span>/); return m ? Hdecode(m[1]) : ""; });
  const clique = async el => { el.dispatchEvent({ type: "click" }); await Hattendre(60); };

  const PHRASE_REMPLACER = "Le PDF sera remplacé sur place par une version cherchable qui garde ses pages d'origine. " +
    "Aucune copie de l'original n'est conservée, tu pourras le retélécharger depuis Moodle.";
  const MOTEUR = { present: true, version: "5.5.3", source: "registre", exe: "C:\\Program Files\\T\\tesseract.exe",
                   langues: ["eng", "fra", "osd"], langues_effectives: "fra+eng", repli: false, message: "" };
  const FILE0 = { etat: "inactive", document: "", page: 0, pages: 0, documents_faits: 0, documents_total: 0, reprise: 0 };
  const COMPTEURS0 = { documents: 0, pages: 0, a_verifier: 0, a_preparer: 0, pages_a_preparer: 0,
                       octets_texte: 0, orphelins: 0 };
  const ETAT0 = { moteur: MOTEUR, active: true, mode_pdf: "aucun", occupe: false, file: FILE0,
                  compteurs: COMPTEURS0, reglages: { ocr_langues: "fra+eng", ocr_dpi: 300, ocr_apres_sync: true } };
  const etat = sur => fusion(ETAT0, sur);

  let HREG = etat({}), HAPRES = true, HREGLER = null, HEXE = null, HINSTALLER = null, HDOCS = { documents: [], total: 0, pages: 0 };
  const HAPPELS = [];
  const HOUVERTURES = [];
  const API = {
    ocr_etat: async () => { HAPPELS.push(["ocr_etat"]); return copie(HREG); },
    ocr_documents: async () => copie(HDOCS),
    ocr_regler: async (cle, valeur, confirme) => {
      HAPPELS.push(confirme === undefined ? ["ocr_regler", cle, valeur] : ["ocr_regler", cle, valeur, confirme]);
      if (HREGLER) return HREGLER;
      /* Le mode `remplacer` demande un consentement separe (contrat 3.2, D3) : la phrase d'abord, l'ecriture avec confirme. */
      if (cle === "ocr_pdf") {
        if (valeur === "remplacer" && HREG.mode_pdf !== "remplacer" && !confirme) return { confirmer: PHRASE_REMPLACER };
        HREG.mode_pdf = valeur;
      }
      if (cle === "ocr") HREG.active = !!valeur;
      /* `ocr_etat().reglages` porte `ocr_apres_sync` (contrat 2.7, ecart 240) : la doublure le range dedans. */
      if (cle === "ocr_apres_sync") { HAPRES = !!valeur; HREG.reglages = Object.assign({}, HREG.reglages, { ocr_apres_sync: !!valeur }); }
      if (cle === "ocr_langues") HREG.reglages = Object.assign({}, HREG.reglages, { ocr_langues: String(valeur) });
      return copie(HREG); },
    ocr_choisir_exe: async () => { HAPPELS.push(["ocr_choisir_exe"]); return HEXE; },
    ocr_installer: async () => { HAPPELS.push(["ocr_installer"]); return HINSTALLER; },
    ocr_ouvrir: async (chemin, page) => { HOUVERTURES.push([chemin, page === undefined ? null : page]); return { ok: true }; },
    ocr_copier: async () => ({ texte: "x", caracteres: 1, documents: 1, pages: 1 }),
    ocr_chercher: async t => ({ resultats: [{ chemin: "Cours A/S1/a.pdf", cours: "Cours A", section: "S1",
      nom: t + ".pdf", page: 3, segments: [{ t: "avant ", m: false }, { t: t, m: true }, { t: " apres", m: false }] }],
      total: 1, tronque: false }),
    ocr_lancer: async (...a) => { HAPPELS.push(["ocr_lancer"].concat(a)); return { file: FILE0 }; },
    sync_etat: async () => ({ accueil: false, site: "https://m.exemple.ch", dest: "D:/Cours", langue: "fr",
      langues: [{ code: "fr", nom: "Français" }], statuts: false, note: false, auto: false, titres_youtube: false,
      jeton: false, textes: { statuts: "Sous-dossiers par statut", note: "Lister les nouveautés" } }),
  };
  window.pywebview = { api: API };
  INFOS = { theme: "systeme", semaine_active: false, verif_action: "aucune", navigateurs: "x",
            explorateur: "y", version: "1.0" };
  occupe = false; semainePrete = true; syncPrete = true;

  /* ---- 1. etatVerification : la cle `textes` du contrat 3.4 ---- */
  let v = etatVerification();
  exiger(v && typeof v === "object", "etatVerification rend un objet");
  exiger(v.textes && typeof v.textes === "object", "la cle `textes` manque");
  assert.deepStrictEqual(Object.keys(v.textes).sort(), ["a_verifier", "documents", "erreur", "file", "pages"]);
  assert.deepStrictEqual([v.textes.documents, v.textes.pages, v.textes.a_verifier, v.textes.file, v.textes.erreur],
    [0, 0, 0, "", ""], "aucun etat lu : des zeros et des chaines vides, jamais undefined");
  exiger(v.pret === false, "sans txPret, pret est faux");
  for (const cle of ["onglet", "erreur", "connecte", "cours", "semaine_active", "cartes", "lectures",
                     "synchro", "version", "onglets", "horaire", "textes"])
    exiger(cle in v, "aucune cle existante ne disparait : " + cle);

  /* ---- 2. les compteurs, la file, et `pret` ---- */
  TX = etat({ compteurs: { documents: 3, pages: 9, a_verifier: 1, a_preparer: 2, pages_a_preparer: 5,
                           octets_texte: 6710886, orphelins: 0 },
              file: { etat: "pause", document: "", page: 0, pages: 0, documents_faits: 1,
                      documents_total: 5, reprise: 4 } });
  txPret = true; txOccupe = false;
  v = etatVerification();
  assert.deepStrictEqual([v.textes.documents, v.textes.pages, v.textes.a_verifier, v.textes.file],
    [3, 9, 1, "pause"], "documents, pages, a_verifier et file viennent de TX");
  exiger(v.pret === true, "tout est pret : pret vrai");
  txOccupe = true; exiger(etatVerification().pret === false, "txOccupe vrai : pret faux"); txOccupe = false;
  txPret = false; exiger(etatVerification().pret === false, "txPret faux : pret faux"); txPret = true;
  occupe = true; exiger(etatVerification().pret === false, "occupe de Ma semaine : pret faux"); occupe = false;
  exiger(etatVerification().pret === true, "pret revient a vrai");

  /* ---- 3. onglets : trois noms, la pastille ne s'y colle pas (ecart 179) ---- */
  const pastille = $h("#tx-badge");
  pastille.textContent = "3"; pastille.hidden = false;
  const noms = etatVerification().onglets;
  assert.deepStrictEqual(noms, ["sync", "semaine", "textes"],
    "les noms se lisent dans data-onglet, pas dans textContent");
  for (const nom of noms) exiger(!/[0-9]/.test(nom), "aucun nom ne porte de chiffre : " + nom);
  pastille.hidden = true;

  /* ---- 4. erreur = dernier message d'erreur encore affiche ---- */
  /* Le message est pose comme le ferait toast() de commun.js ; le DOM factice ne lit pas innerHTML,
     donc son texte est ecrit par textContent (un navigateur donne le meme resultat). */
  const poseToast = (classe, texte) => {
    const t = document.createElement("div");
    t.className = "toast " + classe; t.textContent = texte;
    $h("#toasts").append(t); return t;
  };
  poseToast("critique", "Ce PDF est abîmé et n'a pas pu être ouvert.");
  assert.strictEqual(etatVerification().textes.erreur, "Ce PDF est abîmé et n'a pas pu être ouvert.",
    "la derniere erreur affichee est rapportee");
  poseToast("bon", "Copié : 12 caractères.");
  assert.strictEqual(etatVerification().textes.erreur, "Ce PDF est abîmé et n'a pas pu être ouvert.",
    "un message ordinaire ne remplace pas l'erreur");

  /* ---- 5. le groupe des reglages de l'extraction, consentement faux (ecart 234) ---- */
  HREG = etat({ moteur: MOTEUR, active: false });
  HAPPELS.length = 0;
  await clique($h("#b-reglages"));
  exiger($h("#tiroir").classList.contains("ouvert"), "le tiroir s'ouvre");
  const groupe = $h("#r-tx-ocr");
  exiger(groupe, "le groupe « Texte des cours (OCR) » est dans le tiroir");
  exiger(plat_texte(groupe.textContent).includes("Texte des cours (OCR)"), "le titre du groupe");
  let actif = $h("#r-tx-ocr-actif"), apres = $h("#r-tx-ocr-apres"), langues = $h("#r-tx-ocr-langues");
  exiger(actif && apres && langues, "les controles du groupe sont construits");
  exiger(actif.checked === false, "le consentement suit ocr_etat().active, faux ici (ecart 234)");
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"), [],
    "ouvrir le groupe n'ecrit aucun reglage (ecart 234, mutation M39)");
  exiger(apres.checked === true, "l'extraction automatique est vraie par defaut");
  assert.strictEqual(langues.value, "fra+eng", "la langue vient de ocr_etat().reglages");
  assert.strictEqual($h("#r-tx-ocr-exe").textContent, MOTEUR.exe, "le chemin du moteur est affiche");
  exiger($h("#r-tx-ocr-choisir") && $h("#r-tx-ocr-installer"), "Indiquer l'emplacement et Installer");

  /* Consentement vrai : le groupe suit l'etat, toujours sans ecriture. */
  HREG = etat({ moteur: MOTEUR, active: true });
  ouvrirTiroir(false); await clique($h("#b-reglages"));
  actif = $h("#r-tx-ocr-actif"); apres = $h("#r-tx-ocr-apres"); langues = $h("#r-tx-ocr-langues");
  exiger(actif && actif.checked === true, "le consentement vient de ocr_etat().active");
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"), [],
    "ouvrir le groupe n'ecrit aucun reglage (ecart 234, mutation M39)");

  /* ---- 6. les reglages passent par ocr_regler ---- */
  HAPPELS.length = 0;
  apres.checked = false; apres.dispatchEvent({ type: "change" }); await Hattendre(60);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"), [["ocr_regler", "ocr_apres_sync", false]],
    "la case d'extraction automatique ecrit ocr_apres_sync");
  assert.strictEqual(HAPRES, false, "le reglage enregistre cote Python est faux");
  assert.strictEqual(HREG.reglages.ocr_apres_sync, false,
    "la doublure rend la forme du contrat 2.7 : `reglages` porte `ocr_apres_sync` (ecart 240)");
  exiger(apres.checked === false, "la case decochee reste decochee apres la reponse (ecart 228)");

  /* Relire l'etat comme le fait une reouverture du tiroir : la case reste decochee (ecart 228). */
  ouvrirTiroir(false); await clique($h("#b-reglages"));
  actif = $h("#r-tx-ocr-actif"); apres = $h("#r-tx-ocr-apres"); langues = $h("#r-tx-ocr-langues");
  exiger(apres && apres.checked === false, "rouvrir le groupe ne recoche pas la case (ecart 228)");

  HAPPELS.length = 0;
  langues.value = "fra"; langues.dispatchEvent({ type: "change" }); await Hattendre(60);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"), [["ocr_regler", "ocr_langues", "fra"]],
    "les langues passent par ocr_regler");
  apres.checked = true; apres.dispatchEvent({ type: "change" }); await Hattendre(60);
  exiger(apres.checked === true, "le groupe n'est pas reconstruit par un reglage : le focus reste");
  exiger(HAPRES === true, "la case rend la main : elle peut renvoyer vrai (ecart 228)");
  HREGLER = { erreur: "Valeur invalide." };
  const t0 = lesToasts().length;
  actif.checked = false; actif.dispatchEvent({ type: "change" }); await Hattendre(60);
  assert.deepStrictEqual(lesToasts().slice(t0), ["Valeur invalide."], "la phrase de l'API, telle quelle");
  exiger(actif.checked === true, "un refus remet la case dans son etat");
  HREGLER = null;

  /* Ecart 240 : la memoire de la page vaut vrai (la case vient d'etre recochee) ; apres un redemarrage la
     configuration dit faux et ocr_etat() le rend : la case s'affiche decochee, la valeur de l'API passe avant. */
  HREG = etat({ reglages: { ocr_langues: "fra+eng", ocr_dpi: 300, ocr_apres_sync: false } });
  ouvrirTiroir(false); await clique($h("#b-reglages"));
  apres = $h("#r-tx-ocr-apres");
  exiger(apres && apres.checked === false, "ocr_etat().reglages.ocr_apres_sync faux : la case est decochee (ecart 240)");
  HREG = etat({ reglages: { ocr_langues: "fra+eng", ocr_dpi: 300, ocr_apres_sync: true } });
  ouvrirTiroir(false); await clique($h("#b-reglages"));
  apres = $h("#r-tx-ocr-apres");
  exiger(apres && apres.checked === true, "et cochee quand l'API rend vrai");

  /* ---- 6b. le mode des PDF : « Aucun » par defaut, consentement separe pour « Remplacer » (ecart 276) ---- */
  HREG = etat({ mode_pdf: "aucun" });
  ouvrirTiroir(false); HAPPELS.length = 0; await clique($h("#b-reglages"));
  let mode = $h("#r-tx-ocr-pdf");
  exiger(mode, "la liste du mode des PDF est dans le groupe");
  assert.deepStrictEqual(mode.children.map(o => o.value), ["aucun", "remplacer"], "deux modes, Aucun en premier");
  assert.strictEqual(mode.value, "aucun", "Aucun par defaut : le mode vient de ocr_etat().mode_pdf");
  exiger(plat_texte(mode.children[0].textContent) === "Aucun", "la premiere option dit Aucun");
  exiger(/Remplacer par une version cherchable/.test(plat_texte(mode.children[1].textContent)), "la seconde dit Remplacer");
  exiger(plat_texte($h("#r-tx-ocr-pdf-aide").textContent).includes("Aucune copie de l'original"),
    "l'avertissement sur l'absence de copie locale est visible sans rien cliquer");
  assert.strictEqual(mode.getAttribute("aria-describedby"), "r-tx-ocr-pdf-aide", "l'avertissement decrit la liste");
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"), [], "ouvrir le groupe n'ecrit aucun mode");

  /* Refus du consentement : rien n'est ecrit, la liste revient sur Aucun. */
  mode.value = "remplacer"; mode.dispatchEvent({ type: "change" }); await Hattendre(60);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"), [["ocr_regler", "ocr_pdf", "remplacer"]],
    "la premiere demande n'ecrit pas : l'API repond par la phrase de consentement");
  const question = $h("#d-question");
  exiger(question.open === true, "le consentement separe s'affiche dans la boite de dialogue");
  assert.strictEqual($h("#q-texte").textContent, PHRASE_REMPLACER, "la phrase de l'API, telle quelle, avec l'absence de copie");
  question.returnValue = ""; question.close(); await Hattendre(40);
  assert.strictEqual($h("#r-tx-ocr-pdf").value, "aucun", "refuser remet la liste sur Aucun");
  assert.strictEqual(HREG.mode_pdf, "aucun", "rien n'est ecrit sans accord");
  exiger(!HAPPELS.some(a => a[0] === "ocr_regler" && a[3] === true), "aucun appel avec confirme sans accord");

  /* Accord : un second appel avec confirme=true, et le mode tient apres une reouverture du tiroir. */
  HAPPELS.length = 0;
  mode = $h("#r-tx-ocr-pdf");
  mode.value = "remplacer"; mode.dispatchEvent({ type: "change" }); await Hattendre(60);
  question.returnValue = "ok"; question.close(); await Hattendre(60);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"),
    [["ocr_regler", "ocr_pdf", "remplacer"], ["ocr_regler", "ocr_pdf", "remplacer", true]], "demande, accord, ecriture confirmee");
  assert.strictEqual(HREG.mode_pdf, "remplacer", "le mode est enregistre");
  assert.strictEqual($h("#r-tx-ocr-pdf").value, "remplacer", "la liste affiche le mode choisi");
  exiger(!HAPPELS.some(a => a[1] === "ocr"), "le consentement du premier passage n'est ni donne ni retire par ce choix");
  ouvrirTiroir(false); await clique($h("#b-reglages"));
  assert.strictEqual($h("#r-tx-ocr-pdf").value, "remplacer", "rouvrir le groupe relit le mode, il ne revient pas sur Aucun");

  /* Revenir a Aucun : aucun consentement, une seule ecriture. */
  HAPPELS.length = 0; question.open = false;
  mode = $h("#r-tx-ocr-pdf");
  mode.value = "aucun"; mode.dispatchEvent({ type: "change" }); await Hattendre(60);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"), [["ocr_regler", "ocr_pdf", "aucun"]],
    "revenir a Aucun s'ecrit tout de suite");
  exiger(question.open !== true, "aucune boite de dialogue pour revenir a Aucun");
  assert.strictEqual(HREG.mode_pdf, "aucun");

  /* Une erreur de l'API : la phrase telle quelle, la liste revient sur le mode enregistre. */
  HREGLER = { erreur: "Ce mode n'existe pas. Choisis « Aucun » ou « Remplacer par une version cherchable »." };
  const t3 = lesToasts().length;
  mode.value = "remplacer"; mode.dispatchEvent({ type: "change" }); await Hattendre(60);
  assert.deepStrictEqual(lesToasts().slice(t3), [HREGLER.erreur], "la phrase de l'API, telle quelle");
  assert.strictEqual($h("#r-tx-ocr-pdf").value, "aucun", "un refus remet la liste dans son etat");
  HREGLER = null;

  /* ---- 7. le moteur : choisir l'emplacement, installer ---- */
  HEXE = { erreur: "Indique un chemin qui existe sur cet ordinateur." };
  const t1 = lesToasts().length;
  await clique($h("#r-tx-ocr-choisir"));
  assert.deepStrictEqual(lesToasts().slice(t1), ["Indique un chemin qui existe sur cet ordinateur."],
    "la phrase de ocr_choisir_exe, telle quelle");
  HEXE = etat({ moteur: Object.assign({}, MOTEUR, { exe: "D:\\outil\\tesseract.exe" }) });
  await clique($h("#r-tx-ocr-choisir"));
  assert.strictEqual($h("#r-tx-ocr-exe").textContent, "D:\\outil\\tesseract.exe", "le chemin suit le choix");
  HINSTALLER = { erreur: "L'installation automatique n'est pas encore disponible. Indique l'emplacement du moteur dans les réglages." };
  const t2 = lesToasts().length;
  await clique($h("#r-tx-ocr-installer"));
  assert.deepStrictEqual(lesToasts().slice(t2), [HINSTALLER.erreur], "la phrase de ocr_installer, telle quelle");
  assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_installer").length, 1);

  /* ---- 8. « Reglages de l'extraction » mene au groupe (ecart 215) ---- */
  ouvrirTiroir(false);
  exiger(!$h("#tiroir").classList.contains("ouvert"), "le tiroir se ferme");
  Hactif = null;
  await clique($h("#tx-reglages"));
  exiger($h("#tiroir").classList.contains("ouvert"), "Reglages de l'extraction ouvre le tiroir");
  exiger(Hactif === $h("#r-tx-ocr"), "le focus va au groupe de l'extraction");

  /* ---- 9. la ligne de resultat et le menu, au clavier (ecart 195) ---- */
  HDOCS = { documents: [{ chemin: "Cours A/S1/a.pdf", cours: "Cours A", section: "S1", nom: "a.pdf",
    type: "scanne", pages: 4, qualite: "bon", confiance: 0.9, cherchable: false, verifie: false,
    orphelin: false, sortie: "Textes/Cours A/S1/a.pdf.md", date: "2026-11-09" }], total: 1, pages: 4 };
  choisirOnglet("textes");
  await Hattendre(80);
  const ligne = document.querySelector(".tx-ligne");
  exiger(ligne, "la liste affiche une ligne");
  const boutonMenu = ligne.querySelector("[data-tx=menu]");
  assert.strictEqual(boutonMenu.getAttribute("aria-haspopup"), "menu", "le bouton annonce un menu");
  boutonMenu.dispatchEvent({ type: "click" }); await Hattendre(30);
  const menu = ligne.querySelector(".tx-menu");
  exiger(menu, "le menu s'ouvre");
  exiger(Hactif === menu.querySelector("button"), "le focus entre dans le menu");
  assert.strictEqual(boutonMenu.getAttribute("aria-expanded"), "true", "aria-expanded a l'ouverture");
  document.dispatchEvent({ type: "keydown", key: "Escape" }); await Hattendre(20);
  exiger(!ligne.querySelector(".tx-menu"), "Escape ferme le menu");
  exiger(Hactif === boutonMenu, "le focus revient au bouton du menu");
  assert.strictEqual(boutonMenu.getAttribute("aria-expanded"), "false", "aria-expanded a la fermeture");

  const champ = $h("#tx-recherche");
  champ.value = "scan"; champ.dispatchEvent({ type: "input" }); await Hattendre(420);
  const trouve = document.querySelector(".tx-trouve");
  exiger(trouve, "un resultat s'affiche");
  assert.strictEqual(trouve.tabIndex, 0, "la ligne de resultat est atteignable au clavier");
  assert.strictEqual(trouve.getAttribute("role"), "button", "la ligne de resultat porte un role");
  HOUVERTURES.length = 0;
  trouve.dispatchEvent({ type: "keydown", key: "Enter", preventDefault() {} }); await Hattendre(40);
  assert.deepStrictEqual(HOUVERTURES, [["Textes/Cours A/S1/a.pdf.md", 3]], "Entree ouvre la page du resultat");
  trouve.dispatchEvent({ type: "keydown", key: " ", preventDefault() {} }); await Hattendre(40);
  assert.strictEqual(HOUVERTURES.length, 2, "l'espace ouvre aussi le resultat");

  /* ---- 9 bis. « Copier l'extrait » garde sa touche (ecart 232) ---- */
  const boutonCopie = trouve.querySelector("button");
  exiger(boutonCopie, "le bouton « Copier l'extrait » de la ligne");
  HOUVERTURES.length = 0;
  let annulee = false;
  boutonCopie.dispatchEvent({ type: "keydown", key: "Enter", preventDefault() { annulee = true; } });
  await Hattendre(40);
  assert.deepStrictEqual(HOUVERTURES, [], "Entree sur « Copier l'extrait » n'ouvre pas le document (ecart 232)");
  exiger(!annulee, "la ligne n'annule pas la touche du bouton de copie (ecart 232)");
  boutonCopie.dispatchEvent({ type: "keydown", key: " ", preventDefault() { annulee = true; } });
  await Hattendre(40);
  assert.deepStrictEqual(HOUVERTURES, [], "l'espace sur « Copier l'extrait » n'ouvre pas le document");
  exiger(!annulee, "la ligne n'annule pas l'espace du bouton de copie");
  HCOPIE = "";
  boutonCopie.dispatchEvent({ type: "click" }); await Hattendre(60);
  assert.strictEqual(HCOPIE, "avant scan apres", "le bouton de copie remplit le presse-papiers");

  /* ---- 10. le focus revient apres le consentement, pour les trois entrees (ecart 222) ---- */
  HREG = etat({ compteurs: { documents: 3, pages: 9, a_verifier: 1, a_preparer: 2, pages_a_preparer: 5,
                             octets_texte: 6710886, orphelins: 0 } });
  const consentement = $h("#d-tx-preparer");
  const plusTard = async () => {
    for (const b of Hdescend(consentement)) if (b.hasAttribute("data-ferme") && plat_texte(b.textContent) === "Plus tard") {
      b.dispatchEvent({ type: "click" }); break; }
    await Hattendre(40);
  };
  Hactif = null;
  await clique($h("#tx-preparer"));
  exiger(consentement.open === true, "entree #tx-preparer : le dialogue s'ouvre");
  await plusTard();
  exiger(consentement.open === false, "Plus tard le ferme");
  exiger(Hactif === $h("#tx-preparer"), "entree #tx-preparer : le focus revient au bouton");

  const boutonVide = document.querySelector('#tx-vide [data-action="preparer"]');
  exiger(boutonVide, "le bouton de l'etat vide");
  await clique(boutonVide);
  exiger(consentement.open === true, "entree de l'etat vide : le dialogue s'ouvre");
  await plusTard();
  exiger(Hactif === boutonVide, "entree de l'etat vide : le focus revient au bouton");

  Hactif = null;
  await clique($h("#tx-quoi"));
  exiger($h("#d-tx-quoi").open === true, "le panneau s'ouvre");
  await clique(document.querySelector(".tx-quoi-preparer"));
  exiger($h("#d-tx-quoi").open === false, "le panneau se ferme avant le consentement");
  exiger(consentement.open === true, "troisieme entree : le consentement s'ouvre");
  await plusTard();
  exiger(Hactif === $h("#tx-quoi"), "troisieme entree : le focus revient au lien du panneau");

  /* ---- 11. moteur absent et file en pause : les deux boutons principaux sont offerts ensemble ---- */
  HREG = etat({ moteur: Object.assign({}, MOTEUR, { present: false }),
                file: { etat: "pause", document: "", page: 0, pages: 0, documents_faits: 1,
                        documents_total: 5, reprise: 4 } });
  await txCarteCharger();
  const carte = $h("#tx-carte");
  exiger(visible(carte), "la carte est visible");
  exiger(visible(carte.querySelector('[data-action="reprendre"]')) && visible(carte.querySelector('[data-action="installer"]')),
    "Reprendre et Installer sont offerts ensemble : une regle CSS doit en demettre un");

  /* ---- 12. aucun lancement, aucun consentement implicite pendant tout le parcours ---- */
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_lancer"), [], "aucun ocr_lancer dans ce parcours");
  console.log("OK");
  process.exit(0);
})().catch(e => { console.error(e && e.stack ? e.stack : e); process.exit(1); });
"""


if __name__ == "__main__":
    unittest.main()
