"""Tests de la verification, du groupe de reglages de l'extraction, de l'accessibilite et du theme (tache U5).

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque. Trois familles de tests, comme tests/test_preparer_js.py.

Statiques : `window.etatVerification()` rend la cle `textes` du contrat 3.4 et son `pret` tient compte
d'un etat des textes lu et d'une file libre, `onglets` lit `data-onglet` (ecart 179) ; le groupe
« Texte des cours (OCR) » du tiroir porte ses controles (format du texte, copies d'originaux, contrat 6)
et passe par `ocr_regler`, `ocr_choisir_exe`, `ocr_installer` et `ocr_originaux_supprimer` ; aucun des
sept mots interdits du contrat 5 hors de ce groupe ; les classes de U4 sont styees ; les deux boutons
principaux de la carte ne peuvent pas se montrer ensemble ; aucune couleur litterale dans les blocs
nouveaux ; les contrastes calcules depuis les variables des deux themes passent 4,5 (ecart 178).

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

# Controles du groupe « Texte des cours (OCR) » (contrat 3.4, ligne Reglages, et contrat 6 de la refonte).
IDS_TIROIR = ("r-tx-ocr", "r-tx-ocr-moteur", "r-tx-ocr-exe", "r-tx-ocr-choisir", "r-tx-ocr-installer",
              "r-tx-ocr-installation", "r-tx-ocr-installer-annuler",
              "r-tx-ocr-langues", "r-tx-ocr-format", "r-tx-ocr-copies", "r-tx-ocr-originaux",
              "r-tx-ocr-originaux-aide")

# Classes ecrites par U4, qui n'avaient aucune regle. Le dialogue de preparation est parti (R11).
CLASSES_U4 = ("tx-carte-nombres", "tx-carte-moteur", "tx-carte-travail", "tx-carte-document",
              "tx-carte-rang", "tx-carte-page", "tx-carte-pause")

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
        # `pret` exige un etat des textes deja lu et une file libre (R11, contrat 3.4, ligne Verification).
        ligne_pret = [l for l in bloc.splitlines() if l.strip().startswith("pret:")]
        self.assertTrue(ligne_pret, "la ligne `pret` est introuvable")
        self.assertIn("textesLus", ligne_pret[0], "pret exige un etat des textes lu")
        self.assertIn("textesLibres", ligne_pret[0], "pret exige une file qui ne travaille pas")
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
        # « Installer » passe par le chemin unique de la carte (txCarteInstaller, sync.js), ecart 292.
        for appel in ('api().ocr_etat()', 'api().ocr_regler(', 'api().ocr_choisir_exe()',
                      'txCarteInstaller()', 'api().ocr_originaux_supprimer('):
            with self.subTest(appel=appel):
                self.assertIn(appel, sans, "le groupe passe par %s" % appel)
        for cle in ('"ocr_langues"', '"ocr_format"', '"r-tx-ocr-format"'):
            with self.subTest(cle=cle):
                self.assertIn(cle, sans, "le groupe porte %s" % cle)
        self.assertIn("confirmer(", corps_de(sans, "txSupprimerOriginaux") or "",
                      "« Supprimer les copies » est en deux temps (contrat 4.7)")
        for retire in ("ocr_apres_sync", "ocr_pdf", "mode_pdf", "txReglerMode"):
            with self.subTest(retire=retire):
                self.assertNotIn(retire, sans, "%s est retire par la refonte (contrat 6)" % retire)

    def test_le_format_et_les_copies_ont_une_etiquette(self):
        """Contrat 6 : le format a son etiquette, et le bouton des copies decrit son avertissement."""
        sans = tj.sans_commentaires(self.app)
        self.assertIn("Format du texte", sans)
        self.assertRegex(sans, r'setAttribute\("for", "r-tx-ocr-format"\)', "etiquette liee au format")
        self.assertIn("Supprimer les copies", sans)
        self.assertIn("Copies d'originaux", sans)
        self.assertRegex(sans, r'setAttribute\("aria-describedby", "r-tx-ocr-originaux-aide"\)',
                         "l'aide est liee au bouton des copies")

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

    # ------------------------------------------------------------------ theme et style
    # Les tests de la ligne de resultat et de son menu sont retires par R7 avec la liste de l'ancien
    # onglet (U6, contrat 5.2) ; ceux du panneau « A quoi ça sert ? » avec le panneau (O8).
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
        # « Installer » des reglages appelle txCarteInstaller (sync.js, ecart 292) : son appel d'API s'y lit.
        sync = lire(os.path.join(INTERFACE, "sync.js"))
        appels = sorted(set(re.findall(r"api\(\)\.(ocr_\w+)\(", tj.sans_commentaires(self.app)))
                        | set(re.findall(r"api\(\)\.(ocr_installer)\(", tj.sans_commentaires(sync))))
        self.assertGreaterEqual(len(appels), 4, "les appels du groupe : %s" % appels)
        # R11 branche deux methodes du contrat 4.2 et 4.7 que R4 et R5 posent apres elle : elles sont
        # nommees au contrat et pas encore dans ApiTextes de ce worktree (ecart ecrit au journal de R11).
        contrat = {"ocr_originaux_supprimer"}
        for nom in appels:
            with self.subTest(appel=nom):
                self.assertTrue(callable(getattr(ApiTextes, nom, None)) or nom in contrat,
                                "ApiTextes.%s n'existe pas et n'est pas au contrat 4" % nom)

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

  const PHRASE_COPIES = "Les copies d'originaux seront supprimées. Une restauration ne sera plus possible " +
    "sans retélécharger le PDF depuis Moodle.";
  const MOTEUR = { present: true, version: "5.5.3", source: "registre", exe: "C:\\Program Files\\T\\tesseract.exe",
                   langues: ["eng", "fra", "osd"], langues_effectives: "fra+eng", repli: false, message: "" };
  const FILE0 = { etat: "inactive", origine: "coffre", document: "", page: 0, pages: 0,
                  documents_faits: 0, documents_total: 0, reprise: 0 };
  const COMPTEURS0 = { fichiers: 0, traites: 0, a_verifier: 0, echecs: 0, non_traites: 0, pages_non_traitees: 0 };
  const ETAT0 = { moteur: MOTEUR, occupe: false, file: FILE0, compteurs: COMPTEURS0,
                  reglages: { ocr_langues: "fra+eng", ocr_dpi: 300, ocr_format: "md" },
                  originaux: { nombre: 0, octets: 0 },
                  depot: { etat: "inactif", dossier_defaut: "", dossier: "", resultats: [] } };
  const etat = sur => fusion(ETAT0, sur);

  let HREG = etat({}), HREGLER = null, HEXE = null, HINSTALLER = null, HORIGINAUX = null;
  const HAPPELS = [];
  const API = {
    ocr_etat: async () => { HAPPELS.push(["ocr_etat"]); return copie(HREG); },
    ocr_arbre: async () => { HAPPELS.push(["ocr_arbre"]);
      return { racine: "D:/Cours", cours: [], compteurs: COMPTEURS0 }; },
    ocr_regler: async (cle, valeur, confirme) => {
      HAPPELS.push(confirme === undefined ? ["ocr_regler", cle, valeur] : ["ocr_regler", cle, valeur, confirme]);
      if (HREGLER) return HREGLER;
      if (cle === "ocr_langues") HREG.reglages = Object.assign({}, HREG.reglages, { ocr_langues: String(valeur) });
      if (cle === "ocr_format") HREG.reglages = Object.assign({}, HREG.reglages, { ocr_format: String(valeur) });
      return copie(HREG); },
    ocr_originaux_supprimer: async (...args) => {
      const confirme = args[0];
      HAPPELS.push(args.length === 0 ? ["ocr_originaux_supprimer"]
                                     : ["ocr_originaux_supprimer", confirme]);
      if (HORIGINAUX) return HORIGINAUX;
      if (!confirme) return { confirmer: PHRASE_COPIES, nombre: 4, octets: 2097152 };
      HREG.originaux = { nombre: 0, octets: 0 };
      return { ok: true, nombre: 4, octets: 2097152 }; },
    ocr_choisir_exe: async () => { HAPPELS.push(["ocr_choisir_exe"]); return HEXE; },
    ocr_installer: async () => { HAPPELS.push(["ocr_installer"]); return HINSTALLER; },
    ocr_installer_annuler: async () => { HAPPELS.push(["ocr_installer_annuler"]); return { ok: true }; },
    ocr_ouvrir: async (chemin, page) => { HAPPELS.push(["ocr_ouvrir", chemin]); return { ok: true }; },
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
  exiger(v.pret === false, "sans etat des textes lu, pret est faux");
  for (const cle of ["onglet", "erreur", "connecte", "cours", "semaine_active", "cartes", "lectures",
                     "synchro", "version", "onglets", "horaire", "textes"])
    exiger(cle in v, "aucune cle existante ne disparait : " + cle);

  /* ---- 2. les compteurs, la file, et `pret` ---- */
  TX = etat({ compteurs: { fichiers: 3, traites: 0, a_verifier: 1, echecs: 0, non_traites: 2, pages_non_traitees: 5 },
              file: { etat: "inactive", origine: "coffre", document: "", page: 0, pages: 0,
                      documents_faits: 0, documents_total: 0, reprise: 0 } });
  v = etatVerification();
  assert.deepStrictEqual([v.textes.documents, v.textes.pages, v.textes.a_verifier, v.textes.file],
    [0, 0, 1, "inactive"], "documents, pages, a_verifier et file viennent de TX");
  exiger(v.pret === true, "un etat lu et une file libre : pret vrai");
  TX.file = { etat: "pause", document: "", page: 0, pages: 0, documents_faits: 1, documents_total: 5, reprise: 4 };
  exiger(etatVerification().pret === false, "une file en pause : pret faux");
  TX.file = { etat: "en_cours", document: "", page: 0, pages: 0, documents_faits: 1, documents_total: 5, reprise: 0 };
  exiger(etatVerification().pret === false, "une file en cours : pret faux");
  TX = null;
  exiger(etatVerification().pret === false, "sans TX, pret est faux");
  TX = etat({});
  occupe = true; exiger(etatVerification().pret === false, "occupe de Ma semaine : pret faux"); occupe = false;
  exiger(etatVerification().pret === true, "pret revient a vrai");

  /* ---- 3. onglets : trois noms, la pastille ne s'y colle pas (ecart 179) ---- */
  const pastille = $h("#tx-badge");
  pastille.textContent = "3"; pastille.hidden = false;
  const noms = etatVerification().onglets;
  /* R7 ajoute trois sous-onglets [role=tab] dans #v-textes : app.js les liste encore avec un nom
     vide, parce qu'il lit tous les [role=tab] de la page (ecart a corriger par R11, journal R7). */
  assert.deepStrictEqual(noms.slice(0, 3), ["sync", "semaine", "textes"],
    "les noms se lisent dans data-onglet, pas dans textContent");
  exiger(noms.slice(3).every(nom => nom === ""),
    "les sous-onglets de Mes textes n'ont pas de data-onglet : " + JSON.stringify(noms));
  for (const nom of noms.slice(0, 3)) exiger(!/[0-9]/.test(nom), "aucun nom ne porte de chiffre : " + nom);
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

  /* ---- 5. le groupe des reglages de l'extraction (contrat 6) ---- */
  HREG = etat({});
  HAPPELS.length = 0;
  await clique($h("#b-reglages"));
  exiger($h("#tiroir").classList.contains("ouvert"), "le tiroir s'ouvre");
  const groupe = $h("#r-tx-ocr");
  exiger(groupe, "le groupe « Texte des cours (OCR) » est dans le tiroir");
  exiger(plat_texte(groupe.textContent).includes("Texte des cours (OCR)"), "le titre du groupe");
  let langues = $h("#r-tx-ocr-langues"), format = $h("#r-tx-ocr-format");
  exiger(langues && format, "les controles du groupe sont construits");
  for (const retire of ["#r-tx-ocr-actif", "#r-tx-ocr-apres", "#r-tx-ocr-pdf", "#r-tx-ocr-pdf-aide"])
    exiger(!$h(retire), "controle retire par la refonte : " + retire);
  assert.strictEqual(langues.value, "fra+eng", "la langue vient de ocr_etat().reglages");
  assert.deepStrictEqual(format.children.map(o => o.value), ["md", "txt"], "deux formats, md en premier");
  exiger(plat_texte(format.children[0].textContent) === "Markdown (.md)", "la premiere option dit Markdown");
  exiger(plat_texte(format.children[1].textContent) === "Texte brut (.txt)", "la seconde dit Texte brut");
  assert.strictEqual(format.value, "md", "le format vient de ocr_etat().reglages.ocr_format");
  assert.strictEqual($h("#r-tx-ocr-exe").textContent, MOTEUR.exe, "le chemin du moteur est affiche");
  exiger($h("#r-tx-ocr-choisir") && $h("#r-tx-ocr-installer"), "Indiquer l'emplacement et Installer");
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"), [],
    "ouvrir le groupe n'ecrit aucun reglage (ecart 234, mutation M39)");

  /* Le format suit l'API : une valeur txt dans ocr_etat() se lit au rendu, sans memoire de page. */
  HREG = etat({ reglages: { ocr_langues: "fra+eng", ocr_dpi: 300, ocr_format: "txt" } });
  ouvrirTiroir(false); await clique($h("#b-reglages"));
  format = $h("#r-tx-ocr-format");
  assert.strictEqual(format.value, "txt", "ocr_etat().reglages.ocr_format passe avant toute memoire de page");
  HREG = etat({ reglages: { ocr_langues: "fra+eng", ocr_dpi: 300, ocr_format: "md" } });
  ouvrirTiroir(false); await clique($h("#b-reglages"));
  assert.strictEqual($h("#r-tx-ocr-format").value, "md", "et redevient md quand l'API le dit");

  /* ---- 6. le format passe par ocr_regler ---- */
  HAPPELS.length = 0;
  format = $h("#r-tx-ocr-format");
  format.value = "txt"; format.dispatchEvent({ type: "change" }); await Hattendre(60);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"), [["ocr_regler", "ocr_format", "txt"]],
    "le format s'ecrit par ocr_regler(\"ocr_format\", ...)");
  assert.strictEqual(HREG.reglages.ocr_format, "txt", "le reglage enregistre cote Python suit");
  assert.strictEqual($h("#r-tx-ocr-format").value, "txt", "la liste garde le format choisi");
  langues = $h("#r-tx-ocr-langues");
  HAPPELS.length = 0;
  langues.value = "fra"; langues.dispatchEvent({ type: "change" }); await Hattendre(60);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"), [["ocr_regler", "ocr_langues", "fra"]],
    "les langues passent aussi par ocr_regler");
  exiger($h("#r-tx-ocr-format").value === "txt", "le groupe n'est pas reconstruit par un reglage : le focus reste");
  HREGLER = { erreur: "Valeur invalide." };
  const t0 = lesToasts().length;
  format = $h("#r-tx-ocr-format");
  format.value = "md"; format.dispatchEvent({ type: "change" }); await Hattendre(60);
  assert.deepStrictEqual(lesToasts().slice(t0), ["Valeur invalide."], "la phrase de l'API, telle quelle");
  assert.strictEqual($h("#r-tx-ocr-format").value, "txt",
    "un refus remet la liste sur la valeur enregistree");
  HREGLER = null;

  /* ---- 6b. les copies d'originaux : leur volume, et leur suppression en deux temps (O15) ---- */
  HREG = etat({ originaux: { nombre: 4, octets: 2097152 } });
  ouvrirTiroir(false); HAPPELS.length = 0; await clique($h("#b-reglages"));
  let copies = $h("#r-tx-ocr-copies"), bouton = $h("#r-tx-ocr-originaux");
  exiger(copies && bouton, "la ligne des copies et son bouton sont dans le groupe");
  assert.strictEqual(plat_texte(copies.textContent), "Copies d'originaux : 4, 2,0 Mo",
    "le nombre et le volume viennent de ocr_etat().originaux");
  assert.strictEqual(bouton.disabled, false, "des copies existent : le bouton est actif");
  assert.strictEqual(bouton.textContent, "Supprimer les copies");
  assert.strictEqual(bouton.getAttribute("aria-describedby"), "r-tx-ocr-originaux-aide",
    "l'aide est liee au bouton");
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_originaux_supprimer"), [],
    "ouvrir le groupe ne supprime rien");

  HREG = etat({ originaux: { nombre: 0, octets: 0 } });
  ouvrirTiroir(false); await clique($h("#b-reglages"));
  copies = $h("#r-tx-ocr-copies"); bouton = $h("#r-tx-ocr-originaux");
  assert.strictEqual(plat_texte(copies.textContent), "Copies d'originaux : 0, 0 Ko", "aucune copie");
  assert.strictEqual(bouton.disabled, true, "sans copie, le bouton est desactive");

  HREG = etat({ originaux: { nombre: 4, octets: 2097152 } });
  ouvrirTiroir(false); HAPPELS.length = 0; await clique($h("#b-reglages"));
  bouton = $h("#r-tx-ocr-originaux");
  const tCopies = lesToasts().length;
  await clique(bouton);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_originaux_supprimer"), [["ocr_originaux_supprimer"]],
    "le premier appel ne supprime rien : il demande la phrase de confirmation");
  const question = $h("#d-question");
  exiger(question.open === true, "la confirmation s'affiche dans la boite de dialogue");
  assert.strictEqual($h("#q-texte").textContent, PHRASE_COPIES, "la phrase de l'API, telle quelle");
  question.returnValue = ""; question.close(); await Hattendre(60);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_originaux_supprimer"), [["ocr_originaux_supprimer"]],
    "refuser ne rappelle pas l'API");
  assert.strictEqual(HREG.originaux.nombre, 4, "refuser ne supprime rien");
  assert.deepStrictEqual(lesToasts().slice(tCopies), [], "refuser n'annonce aucune suppression");

  HAPPELS.length = 0;
  bouton = $h("#r-tx-ocr-originaux");
  bouton.dispatchEvent({ type: "click" }); await Hattendre(60);
  question.returnValue = "ok"; question.close(); await Hattendre(80);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_originaux_supprimer"),
    [["ocr_originaux_supprimer"], ["ocr_originaux_supprimer", true]],
    "demande, accord, suppression confirmee");
  assert.deepStrictEqual(lesToasts().slice(tCopies), ["Copies d'originaux supprimées."], "une seule annonce");
  assert.deepStrictEqual(HREG.originaux, { nombre: 0, octets: 0 }, "les copies sont liberees");
  assert.ok(HAPPELS.some(a => a[0] === "ocr_etat"), "le groupe relit les compteurs apres la suppression");
  assert.strictEqual(plat_texte($h("#r-tx-ocr-copies").textContent), "Copies d'originaux : 0, 0 Ko");
  assert.strictEqual($h("#r-tx-ocr-originaux").disabled, true, "plus de copie : le bouton est desactive");

  /* Une erreur de l'API : la phrase telle quelle, rien n'est supprime. */
  HREG = etat({ originaux: { nombre: 2, octets: 2048 } });
  ouvrirTiroir(false); await clique($h("#b-reglages"));
  HORIGINAUX = { erreur: "Les copies n'ont pas pu être supprimées." };
  const tErreur = lesToasts().length;
  await clique($h("#r-tx-ocr-originaux"));
  assert.deepStrictEqual(lesToasts().slice(tErreur), ["Les copies n'ont pas pu être supprimées."],
    "la phrase de l'API, telle quelle");
  assert.strictEqual(HREG.originaux.nombre, 2, "rien n'a ete supprime");
  HORIGINAUX = null;

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

  /* Les sections 9 et 9 bis (ligne de resultat, recherche, menus de la liste) sont retirees par R7 :
     elles mesuraient l'ancien onglet, supprime avec lui (U6, O8, contrat 5.2). La navigation au
     clavier de la nouvelle arborescence est mesuree par tests/test_arbre_js.py. */

  /* ---- 10. le renvoi de la carte reste un bouton nomme, sans dialogue (O9) ---- */
  HREG = etat({ compteurs: { fichiers: 3, traites: 0, a_verifier: 1, echecs: 0, non_traites: 2,
                             pages_non_traitees: 5 } });
  await txCarteCharger();
  const renvoi = $h("#tx-choisir-quoi");
  exiger(renvoi && visible(renvoi), "le renvoi « Choisir quoi traiter » est visible");
  assert.strictEqual(plat_texte(renvoi.textContent), "Choisir quoi traiter", "le bouton porte son nom");
  exiger(!$h("#d-tx-preparer"), "plus de dialogue de consentement dans la page");

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
