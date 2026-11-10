"""Tests de la carte de preparation, du consentement et de la reprise (tache U4).

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque. Deux familles de tests, comme tests/test_quoi_js.py.

Statiques : la carte `#tx-carte` est dans `#v-semaine` et plus dans `#v-sync`, aucun identifiant hors du
contrat 3.4, aucun mot interdit, `txPreparer` definie dans sync.js, un seul point d'appel de progression
dans textes.js, aucun ecouteur sur `#tx-quoi` ni sur `[data-action="quoi"]` dans sync.js (ecart 202), le
consentement ecrit avant `ocr_lancer`, aucun HTML construit avec des donnees dans le code de la carte.

Parcours (Node, s'ignore sans `node`) : la page entiere d'index.html est lue et rangee dans un DOM
minimal, puis les vraies fonctions de commun.js, sync.js, textes.js et app.js tournent contre une
doublure de l'API qui refuse `ocr_lancer` sans consentement, comme le vrai mixin (invariant 16). Le
script s'ecrit dans un dossier temporaire, supprime dans un `finally`.

Ce que ces tests ne mesurent pas : aucune vraie fenetre pywebview, aucun navigateur (donc ni rendu, ni
<dialog> natif, ni focus reel, ni toast visible derriere un dialogue modal), aucun vrai moteur, aucun
vrai consentement ecrit dans config.json, aucune duree reelle, Windows et macOS non executes.

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
texte_de = qj.texte_de

# Identifiants que le contrat 3.4 autorise dans la carte et dans le dialogue : aucun autre.
IDS_CARTE = {"tx-carte", "tx-preparer", "tx-plus-tard", "tx-quoi", "tx-reglages"}
IDS_DIALOGUE = {"d-tx-preparer"}


def bloc(page, debut, fin="</section>"):
    i = page.find(debut)
    j = page.find(fin, i)
    return page[i:j + len(fin)] if i >= 0 and j > i else ""


class CarteStatique(unittest.TestCase):
    """index.html, sync.js et textes.js : ce que la carte dit et ce qu'elle n'a pas le droit de faire."""

    @classmethod
    def setUpClass(cls):
        cls.page = lire(os.path.join(INTERFACE, "index.html"))
        cls.sync = lire(os.path.join(INTERFACE, "sync.js"))
        cls.textes = lire(os.path.join(INTERFACE, "textes.js"))
        cls.carte = bloc(cls.page, '<section class="carte-s tx-carte" id="tx-carte"')
        cls.dialogue = bloc(cls.page, '<dialog class="dialogue" id="d-tx-preparer">', "</dialog>")

    def test_la_carte_est_dans_ma_semaine_et_pas_dans_mes_cours(self):
        self.assertTrue(self.carte, "la carte #tx-carte est introuvable dans index.html")
        sync = self.page.find('id="v-sync"')
        semaine = self.page.find('id="v-semaine"')
        textes = self.page.find('id="v-textes"')
        place = self.page.find('id="tx-carte"')
        self.assertTrue(0 < sync < semaine < textes)
        self.assertTrue(semaine < place < textes, "#tx-carte doit etre dans #v-semaine (decision du 9 novembre 2026)")
        self.assertEqual(self.page.count('id="tx-carte"'), 1)

    def test_la_carte_garde_ses_deux_phrases_et_ses_cinq_identifiants(self):
        t = texte_de(self.carte)
        for phrase in ("Un PDF scanné, c'est une photo de texte. On peut le lire, mais pas le chercher, ni le "
                       "copier proprement, ni le donner à une IA sans renvoyer l'image à chaque fois.",
                       "MoodleSync le transforme en texte, une fois, sur ton ordinateur. Ensuite tu peux "
                       "chercher, copier et citer."):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, t)
        self.assertEqual(set(re.findall(r'\bid="([^"]+)"', self.carte)), IDS_CARTE)

    def test_la_carte_a_pause_annuler_reprendre_installer_et_emplacement(self):
        for action, libelle in (("pause", "Pause"), ("annuler", "Annuler"), ("installer", "Installer"),
                                ("exe", "Indiquer l'emplacement")):
            with self.subTest(action=action):
                m = re.search(r'<button[^>]*data-action="%s"[^>]*>([^<]*)</button>' % action, self.carte)
                self.assertIsNotNone(m, "bouton data-action=\"%s\" absent de la carte" % action)
                self.assertEqual(m.group(1), libelle)
        self.assertRegex(self.carte, r'<button[^>]*data-action="reprendre"')

    def test_le_dialogue_de_consentement(self):
        self.assertTrue(self.dialogue, "le dialogue #d-tx-preparer est introuvable")
        self.assertEqual(set(re.findall(r'\bid="([^"]+)"', self.dialogue)), IDS_DIALOGUE, "aucun id nouveau")
        t = texte_de(self.dialogue)
        for x in ("Préparer mes cours", "Seulement les documents sans texte", "Préparer maintenant", "Plus tard",
                  "Tu peux continuer à utiliser MoodleSync, mettre en pause ou fermer : la prochaine fois, "
                  "ça reprend où tu t'es arrêté."):
            with self.subTest(texte=x):
                self.assertIn(x, t)
        m = re.search(r'<input[^>]*name="sans_texte"[^>]*>', self.dialogue)
        self.assertIsNotNone(m, "la case de la portee")
        self.assertIn("checked", m.group(0), "cochee par defaut (plan 3.2)")
        self.assertIn('type="checkbox"', m.group(0))
        self.assertIn('data-action="lancer"', self.dialogue)
        plus_tard = re.search(r'<button[^>]*data-ferme[^>]*>Plus tard</button>', self.dialogue)
        self.assertIsNotNone(plus_tard, "« Plus tard » ferme le dialogue, sans rien ecrire")

    def test_aucun_mot_interdit_ni_tiret_long(self):
        mots = tj.table_mots(self.textes)
        propres = [v for k, v in mots.items() if k.startswith(("carte_", "preparer_"))]
        self.assertTrue(propres, "les phrases de la carte sont dans TX_MOTS (cles carte_* et preparer_*)")
        for source in (texte_de(self.carte) + " " + texte_de(self.dialogue) + " " + " ".join(propres),):
            bas = source.lower()
            for mot in INTERDITS:
                with self.subTest(mot=mot):
                    self.assertNotIn(mot, bas)
        for tiret in (chr(0x2013), chr(0x2014)):
            for nom, source in (("index.html", self.page), ("sync.js", self.sync), ("textes.js", self.textes)):
                with self.subTest(fichier=nom):
                    self.assertNotIn(tiret, source)

    def test_txpreparer_est_definie_dans_sync_js(self):
        sans = tj.sans_commentaires(self.sync)
        self.assertRegex(sans, r"function\s+txPreparer\s*\(")
        self.assertNotRegex(tj.sans_commentaires(self.textes), r"function\s+txPreparer\b")
        self.assertIn('typeof txPreparer === "function"', tj.sans_commentaires(self.textes), "U3 reste branche")

    def test_aucun_ecouteur_sur_le_panneau_quoi(self):
        """Ecart 202 : #tx-quoi et [data-action=\"quoi\"] sont branches par textes.js, une seule fois."""
        sans = tj.sans_commentaires(self.sync)
        self.assertNotIn("#tx-quoi", sans.replace("#d-tx-quoi", ""), "sync.js ne branche pas le lien de la carte")
        self.assertNotIn('data-action="quoi"', sans)
        self.assertNotIn("txQuoi", sans, "sync.js n'appelle pas le code du panneau : il ferme seulement son dialogue")

    def test_un_seul_point_d_appel_de_progression(self):
        sans = tj.sans_commentaires(self.textes)
        self.assertEqual(len(re.findall(r"txCarteProgres\(", sans)), 1)
        suite = sans.split("window.textesProgres = p => {")[1].split("window.textesJournal")[0]
        self.assertIn('typeof txCarteProgres === "function"', suite, "le point d'appel est gardé")
        # Le comportement existant de textesProgres ne change pas.
        for morceau in ("TX = TX || {};", "TX.file = p;", "txOccupe = etat ===", "barreOccupee(txOccupe",
                        'if (etat === "terminee") txRafraichir();'):
            with self.subTest(morceau=morceau):
                self.assertIn(morceau, suite)

    def test_consentement_ecrit_avant_ocr_lancer(self):
        sans = tj.sans_commentaires(self.sync)
        lancer = corps_de(sans, "txLancer")
        self.assertTrue(lancer, "txLancer est la fonction de « Préparer maintenant »")
        regler = lancer.find('api().ocr_regler("ocr", true)')
        premier = lancer.find("api().ocr_lancer(")
        self.assertGreater(regler, 0)
        self.assertGreater(premier, regler, "le consentement est ecrit avant le premier ocr_lancer")
        self.assertEqual(sans.count("ocr_lancer("), lancer.count("ocr_lancer("), "ocr_lancer n'est appele que par txLancer")
        self.assertRegex(lancer, r'ocr_lancer\(portee, false, true\)', "rappel avec confirme=True")
        self.assertNotIn("ocr_regler", corps_de(sans, "txCarteRendre") or "")

    def test_aucune_extraction_au_chargement(self):
        sans = tj.sans_commentaires(self.sync)
        for nom in ("sDemarrer", "txCarteCharger", "txCarteRendre", "txCarteProgres"):
            corps = corps_de(sans, nom)
            with self.subTest(fonction=nom):
                self.assertTrue(corps, "fonction %s absente" % nom)
                for appel in ("ocr_lancer", "ocr_regler", "ocr_reprendre"):
                    self.assertNotIn(appel, corps)

    def test_aucun_html_construit_avec_des_donnees(self):
        sans = tj.sans_commentaires(self.sync)
        noms = re.findall(r"(?:async\s+)?function\s+(tx\w+)\s*\(", sans)
        self.assertGreaterEqual(len(noms), 6, "les fonctions de la carte : %s" % noms)
        for nom in noms:
            corps = corps_de(sans, nom) or ""
            for procede in HTML_CONSTRUIT:
                with self.subTest(fonction=nom, procede=procede):
                    self.assertNotIn(procede, corps)
            with self.subTest(fonction=nom, procede="ic/esc"):
                self.assertNotRegex(corps, r"\b(ic|esc)\(")

    def test_aucune_duree_inventee_dans_la_page(self):
        sans = tj.sans_commentaires(self.sync) + tj.sans_commentaires(self.textes)
        self.assertNotIn("minutes", sans, "aucune duree : la page ne duplique pas _ocr_minutes (ecart 212)")

    def test_aucun_style_nouveau(self):
        """style.css est a U5 : la carte reutilise des composants existants."""
        feuille = lire(os.path.join(INTERFACE, "style.css"))
        for classe in ("tx-carte", "carte-s", "ligne-champ", "dialogue", "interrupteur", "actions", "bouton"):
            with self.subTest(classe=classe):
                self.assertIn("." + classe, feuille)

    def test_fichiers_en_lf(self):
        for chemin in (os.path.join(INTERFACE, "sync.js"), os.path.join(INTERFACE, "textes.js"),
                       os.path.join(INTERFACE, "index.html"), os.path.abspath(__file__)):
            with self.subTest(fichier=os.path.basename(chemin)):
                with open(chemin, "rb") as f:
                    self.assertNotIn(b"\r", f.read())

    # ------------------------------------------------------------------ parcours sur DOM factice
    @unittest.skipUnless(shutil.which("node"), "node absent : parcours sur DOM factice non execute")
    def test_parcours_de_la_carte_sur_dom_factice(self):
        node = shutil.which("node") or "node"
        coupe = tj.ENTETE.find("/* ---- arbre de la page")
        self.assertGreater(coupe, 0, "marqueur de l'arbre de la page introuvable dans l'entete de test_textes_js")
        # sync.js declare SC lui-meme : la doublure de l'entete n'est pas gardee.
        entete = re.sub(r"let SC = \[.*?\];\n", "", tj.ENTETE[:coupe], count=1, flags=re.S)
        self.assertNotIn("let SC =", entete)
        dossier = tempfile.mkdtemp(prefix="parcours-preparer-")
        script = os.path.join(dossier, "_parcours_preparer.js")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(entete + "\n" + qj.OUTILS + "\n" + CASES_COCHEES + "\n")
                for nom in ("commun.js", "sync.js", "textes.js", "app.js"):
                    f.write("\n/* ===== %s ===== */\n" % nom)
                    f.write(lire(os.path.join(INTERFACE, nom)).replace("\r\n", "\n"))
                f.write("\n" + PARCOURS)
            r = subprocess.run([node, script, INTERFACE], capture_output=True, text=True, timeout=180)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        self.assertEqual(r.returncode, 0, "le parcours a echoue :\n%s\n%s" % (r.stdout, r.stderr))
        self.assertIn("OK", r.stdout)


# Un navigateur coche les cases qui portent `checked` dans le HTML ; le DOM factice ne le fait pas.
CASES_COCHEES = r"""
for (const el of Hdescend(document.body)) if (el.hasAttribute("checked")) el.checked = true;
"""

PARCOURS = r"""
(async () => {
  const exiger = (cond, message) => { if (!cond) throw new assert.AssertionError({ message: message }); };
  const plat_texte = t => String(t).replace(/\s+/g, " ").trim();
  const $h = s => document.querySelector(s);
  const carte = $h("#tx-carte"), dp = $h("#d-tx-preparer"), dquoi = $h("#d-tx-quoi"), dq = $h("#d-question");
  exiger(carte && dp && dquoi && dq, "carte, dialogues absents de la page");
  const C = s => carte.querySelector(s);
  const D = s => dp.querySelector(s);
  const T = el => plat_texte(el.textContent);
  const lesToasts = () => $h("#toasts").children.map(t => {
    const m = String(t.innerHTML).match(/<span>([\s\S]*)<\/span>/); return m ? Hdecode(m[1]) : ""; });
  const genres = () => $h("#toasts").children.map(t => t.className);
  const copie = o => JSON.parse(JSON.stringify(o));
  const fusion = (base, sur) => {
    const r = copie(base);
    for (const k of Object.keys(sur || {})) r[k] = (sur[k] && typeof sur[k] === "object" && !Array.isArray(sur[k]) && r[k])
      ? fusion(r[k], sur[k]) : sur[k];
    return r;
  };

  const MOTEUR = { present: true, version: "5.5.3", source: "registre", exe: "x", langues: ["fra"],
                   langues_effectives: "fra", repli: false, message: "" };
  const FILE0 = { etat: "inactive", document: "", page: 0, pages: 0, documents_faits: 0, documents_total: 0, reprise: 0 };
  const ETAT0 = { moteur: MOTEUR, active: false, mode_pdf: "aucun", occupe: false, file: FILE0,
                  compteurs: { documents: 0, pages: 0, a_verifier: 0, a_preparer: 0, pages_a_preparer: 0,
                               octets_texte: 0, orphelins: 0 }, reglages: { ocr_langues: "fra+eng", ocr_dpi: 300 } };
  const etat = sur => fusion(ETAT0, sur);
  const FILE_COURS = { etat: "en_cours", document: "Cours A/S1/article.pdf", page: 0, pages: 24,
                       documents_faits: 0, documents_total: 18, reprise: 0 };
  const PHRASE_CONSENTEMENT = "L'extraction du texte n'est pas activée. Active-la dans les réglages, puis réessaie.";
  const PHRASE_LOT = "60 documents, environ 900 pages. Environ 15 à 45 minutes. Tu peux continuer à utiliser MoodleSync, mettre en pause ou fermer : la prochaine fois, ça reprend où tu t'es arrêté.";
  const PHRASE_INSTALLER = "L'installation automatique n'est pas encore disponible. Indique l'emplacement du moteur dans les réglages.";

  let HAPPELS = [], HE = etat({}), HSANS = 0;
  let HLANCER = () => ({ file: FILE_COURS }), HREGLER = null, HINSTALLER = null, HEXE = null, HFILE = null;
  const appelsOcr = () => HAPPELS.filter(a => a[0] === "ocr_regler" || a[0] === "ocr_lancer").map(a => a.slice());
  const API = {
    sync_etat: async () => { HAPPELS.push(["sync_etat"]);
      return { accueil: false, site: "https://m.exemple.ch", dest: "D:/Cours", langue: "fr", langues: [{ code: "fr", nom: "Français" }],
               statuts: false, note: false, auto: false, titres_youtube: false, jeton: false,
               textes: { statuts: "Sous-dossiers par statut", note: "Lister les nouveautés" } }; },
    ocr_etat: async () => { HAPPELS.push(["ocr_etat"]); return copie(HE); },
    ocr_documents: async () => ({ documents: [], total: 0, pages: 0 }),
    ocr_regler: async (cle, valeur) => { HAPPELS.push(["ocr_regler", cle, valeur]);
      if (HREGLER) return HREGLER; if (cle === "ocr") HE.active = !!valeur; return copie(HE); },
    ocr_lancer: async (...a) => { HAPPELS.push(["ocr_lancer", ...a]);
      if (!HE.active) { HSANS++; return { erreur: PHRASE_CONSENTEMENT }; }
      return HLANCER(...a); },
    ocr_pause: async () => { HAPPELS.push(["ocr_pause"]); return { file: HFILE }; },
    ocr_reprendre: async () => { HAPPELS.push(["ocr_reprendre"]); return { file: HFILE }; },
    ocr_annuler: async () => { HAPPELS.push(["ocr_annuler"]); return { file: HFILE }; },
    ocr_installer: async () => { HAPPELS.push(["ocr_installer"]); return HINSTALLER; },
    ocr_installer_annuler: async () => { HAPPELS.push(["ocr_installer_annuler"]); return { ok: true }; },
    ocr_choisir_exe: async () => { HAPPELS.push(["ocr_choisir_exe"]); return HEXE; },
  };
  window.pywebview = { api: API };
  INFOS = { theme: "systeme", semaine_active: false, verif_action: "aucune", navigateurs: "x", explorateur: "y", version: "t" };

  const visible = el => el.hidden === false;
  const ferme = async () => { for (const b of Hdescend(dp)) if (b.hasAttribute("data-ferme") && T(b) === "Plus tard") { b.dispatchEvent({ type: "click" }); break; } await Hattendre(10); };
  const clique = async (el) => { el.dispatchEvent({ type: "click" }); await Hattendre(40); };
  const lancer = () => D('[data-action="lancer"]');
  const offre = (a, p) => etat({ compteurs: { a_preparer: a, pages_a_preparer: p } });

  /* ---- 1. la carte est dans Ma semaine, masquee, et rien ne part au chargement ---- */
  exiger(carte.closest("#v-semaine") && !carte.closest("#v-sync"), "la carte est dans #v-semaine, pas dans #v-sync");
  exiger(visible(carte) === false, "la carte est masquee au depart");
  exiger(dp.open === false, "le dialogue est ferme au depart");
  await sDemarrer(); await Hattendre(40);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0].startsWith("ocr_")).map(a => a[0]), ["ocr_etat"],
    "au chargement, la carte lit l'etat et ne lance rien : " + JSON.stringify(HAPPELS));
  exiger(carte.hidden === true, "a_preparer 0 et pas de reprise : la carte reste masquee");
  exiger(TX && TX.compteurs, "la carte ecrit TX (dernier ocr_etat)");

  /* ---- 2. visibilite et nombres ---- */
  HE = offre(18, 312); await txCarteCharger();
  exiger(carte.hidden === false, "a_preparer > 0 : la carte est visible");
  assert.strictEqual(T(C(".tx-carte-nombres")), "18 documents, environ 312 pages.");
  exiger(visible(C("#tx-preparer")) && visible(C("#tx-plus-tard")), "Preparer et Plus tard");
  for (const a of ["reprendre", "pause", "annuler", "installer", "exe"])
    exiger(C('[data-action="' + a + '"]').hidden === true, a + " est masque quand on propose seulement de preparer");
  exiger(C(".tx-carte-travail").hidden === true && C(".tx-carte-moteur").hidden === true, "ni travail ni moteur absent");
  HE = offre(1, 1); await txCarteCharger();
  assert.strictEqual(T(C(".tx-carte-nombres")), "1 document, environ 1 page.", "singulier");
  HE = offre(2, 1224); await txCarteCharger();
  assert.strictEqual(C(".tx-carte-nombres").textContent, "2 documents, environ 1\u00a0224 pages.", "espace insecable des milliers");
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_lancer" || a[0] === "ocr_regler"), [], "lire ne lance rien");

  /* ---- 3. reprise : visible meme sans rien a preparer ---- */
  HE = etat({ file: { etat: "pause", documents_faits: 6, documents_total: 18, reprise: 12 } }); await txCarteCharger();
  exiger(carte.hidden === false, "reprise > 0 : la carte est visible");
  assert.strictEqual(T(C('[data-action="reprendre"]')), "Reprendre l'extraction (12 documents restants)");
  exiger(visible(C('[data-action="reprendre"]')) && visible(C('[data-action="annuler"]')), "Reprendre et Annuler");
  exiger(C("#tx-preparer").hidden === true && C(".tx-carte-nombres").hidden === true, "pas de Preparer pendant une reprise");
  HE = etat({ file: { etat: "pause", documents_faits: 17, documents_total: 18, reprise: 1 } }); await txCarteCharger();
  assert.strictEqual(T(C('[data-action="reprendre"]')), "Reprendre l'extraction (1 document restant)");

  /* ---- 4. moteur absent : Installer et choix manuel, jamais Preparer ---- */
  HE = etat({ moteur: { present: false }, compteurs: { a_preparer: 3, pages_a_preparer: 9 } }); await txCarteCharger();
  exiger(carte.hidden === false, "la carte reste visible sans moteur");
  assert.strictEqual(T(C(".tx-carte-moteur")), "Le moteur d'extraction n'est pas encore installé.");
  exiger(visible(C(".tx-carte-moteur")) && visible(C('[data-action="installer"]')) && visible(C('[data-action="exe"]')),
    "phrase, Installer et Indiquer l'emplacement");
  exiger(C("#tx-preparer").hidden === true, "sans moteur, Preparer n'est pas propose");
  HINSTALLER = { erreur: PHRASE_INSTALLER };
  const t0 = lesToasts().length;
  await clique(C('[data-action="installer"]'));
  assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_installer").length, 1, "Installer appelle ocr_installer");
  assert.deepStrictEqual(lesToasts().slice(t0), [PHRASE_INSTALLER], "la phrase de l'API, telle quelle");
  assert.deepStrictEqual(genres().slice(t0), ["toast critique"]);
  /* Ecart 245 : pendant l'installation, la barre et « Annuler » remplacent les deux boutons ; la progression
     arrive par window.textesInstallation ; « Annuler » appelle ocr_installer_annuler ; la fin restaure la carte. */
  const zone = C(".tx-carte-installation"), barre = zone.querySelector("progress");
  exiger(zone.hidden === true, "la zone d'installation est masquee hors installation");
  let fini; HINSTALLER = new Promise(res => { fini = res; });
  const enCours = clique(C('[data-action="installer"]'));
  exiger(visible(zone) && C('[data-action="installer"]').hidden === true && C('[data-action="exe"]').hidden === true,
    "installation en cours : zone visible, Installer et Indiquer l'emplacement masques");
  window.textesInstallation({ recu: 25, total: 100 });
  assert.strictEqual(barre.value, 25, "la barre suit la progression");
  assert.ok(T(zone.querySelector(".tx-carte-installation-texte")).includes("25"), "le pourcentage est ecrit");
  window.textesProgres({ etat: "terminee", document: "", page: 0, pages: 0, documents_faits: 0, documents_total: 0 });
  exiger(C('[data-action="installer"]').hidden === true, "un rendu de la carte pendant l'installation ne remontre pas Installer");
  await clique(zone.querySelector('[data-action="installer-annuler"]'));
  assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_installer_annuler").length, 1, "Annuler appelle ocr_installer_annuler");
  fini({ annule: true });
  await enCours; await new Promise(r => setTimeout(r, 30));
  exiger(zone.hidden === true, "installation finie : la zone se masque");
  HINSTALLER = { erreur: PHRASE_INSTALLER };

  HEXE = { annule: true };
  await clique(C('[data-action="exe"]'));
  assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_choisir_exe").length, 1, "le choix manuel appelle ocr_choisir_exe");
  exiger(visible(C('[data-action="installer"]')), "choix annule : rien ne change");
  HEXE = etat({ compteurs: { a_preparer: 3, pages_a_preparer: 9 } });
  await clique(C('[data-action="exe"]'));
  exiger(visible(C("#tx-preparer")) && C('[data-action="installer"]').hidden === true && C(".tx-carte-moteur").hidden === true,
    "moteur trouve : la carte propose Preparer");
  HEXE = { erreur: "Indique un chemin qui existe sur cet ordinateur." };
  const t1 = lesToasts().length;
  await clique(C('[data-action="exe"]'));
  assert.deepStrictEqual(lesToasts().slice(t1), ["Indique un chemin qui existe sur cet ordinateur."]);
  assert.deepStrictEqual(appelsOcr(), [], "ni le consentement ni le lancement ne sont touches par le moteur");

  /* ---- 5. le dialogue s'ouvre par les trois entrees, sans rien ecrire ---- */
  HE = offre(18, 312); await txCarteCharger();
  const lienVide = $h('#tx-vide [data-action="preparer"]');
  exiger(lienVide, "le bouton de l'etat vide de Mes textes");
  const entrees = [
    ["#tx-preparer", async () => { await clique($h("#tx-preparer")); }],
    ['[data-action="preparer"]', async () => { await clique(lienVide); }],
    ["txPreparer()", async () => { dquoi.showModal(); txPreparer(); await Hattendre(40);
      exiger(dquoi.open === false, "le panneau « A quoi ca sert ? » se ferme avant le consentement"); }],
  ];
  for (const [nom, declenche] of entrees) {
    const lus = HAPPELS.filter(a => a[0] === "ocr_etat").length;
    await declenche();
    exiger(dp.open === true, "entree " + nom + " : le dialogue de consentement s'ouvre");
    assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_etat").length, lus + 1, nom + " : les nombres viennent d'une lecture fraiche");
    assert.strictEqual(T(D(".tx-preparer-nombres")), "18 documents, environ 312 pages.", nom);
    exiger(D('input[name="sans_texte"]').checked === true, nom + " : case cochee par defaut");
    exiger(Hactif === lancer(), nom + " : le focus va a Preparer maintenant");
    assert.deepStrictEqual(appelsOcr(), [], nom + " : ouvrir n'ecrit aucun consentement et ne lance rien");
    await ferme();
    exiger(dp.open === false, nom + " : Plus tard ferme le dialogue");
    assert.deepStrictEqual(appelsOcr(), [], nom + " : Plus tard n'ecrit jamais le consentement");
  }
  await txPreparer(); await txPreparer();                      // double appel : un seul dialogue
  exiger(dp.open === true, "txPreparer() sans argument ouvre le dialogue");
  await ferme();
  exiger(HAPPELS.every(a => a[0] !== "ocr_lancer"), "aucun ocr_lancer jusqu'ici");
  /* la carte : « Plus tard » masque la carte pour la session, sans rien ecrire */
  await clique($h("#tx-plus-tard"));
  exiger(carte.hidden === true, "Plus tard de la carte la masque");
  assert.deepStrictEqual(appelsOcr(), [], "Plus tard de la carte n'ecrit rien");
  await txCarteCharger();
  exiger(carte.hidden === true, "elle reste masquee apres une relecture");
  TX.file = FILE_COURS; txCarteRendre();
  exiger(carte.hidden === false, "mais l'extraction en cours la montre toujours");
  TX.file = FILE0;

  /* ---- 6. Preparer maintenant : consentement puis lancement, portee par defaut ---- */
  HE = offre(18, 312); HLANCER = () => { HE.file = FILE_COURS; return { file: FILE_COURS }; };
  carte.hidden = false;
  await txPreparer();
  await clique(lancer());
  assert.deepStrictEqual(appelsOcr(), [["ocr_regler", "ocr", true], ["ocr_lancer", "sans_texte", false]],
    "consentement ecrit puis ocr_lancer('sans_texte', false) : " + JSON.stringify(appelsOcr()));
  assert.strictEqual(HSANS, 0, "ocr_lancer n'est jamais parti sans consentement");
  exiger(dp.open === false, "le dialogue se ferme une fois lance");
  exiger(visible(C(".tx-carte-travail")) && visible(C('[data-action="pause"]')), "une file s'affiche dans la carte");

  /* ---- 7. case decochee : portee `tout` ---- */
  HAPPELS = []; HE = offre(18, 312); await txCarteCharger();
  await txPreparer();
  D('input[name="sans_texte"]').checked = false;
  await clique(lancer());
  assert.deepStrictEqual(appelsOcr(), [["ocr_regler", "ocr", true], ["ocr_lancer", "tout", false]], "portee `tout`");
  await txPreparer();
  exiger(D('input[name="sans_texte"]').checked === true, "la case est recochee a chaque ouverture");
  await ferme();

  /* ---- 7b. double clic : un seul consentement et un seul lancement ---- */
  HAPPELS = []; HE = offre(18, 312); await txCarteCharger();
  await txPreparer();
  lancer().dispatchEvent({ type: "click" }); lancer().dispatchEvent({ type: "click" });
  await Hattendre(60);
  assert.deepStrictEqual(appelsOcr(), [["ocr_regler", "ocr", true], ["ocr_lancer", "sans_texte", false]], "un seul lancement");
  exiger(lancer().disabled === false, "le bouton est libere apres le lancement");

  /* ---- 8. confirmer : la phrase de l'API, puis rappel avec confirme=True ---- */
  HAPPELS = []; HE = offre(60, 900); await txCarteCharger();
  HLANCER = (portee, refaire, confirme) => confirme ? (HE.file = FILE_COURS, { file: FILE_COURS })
    : { confirmer: PHRASE_LOT, documents: 60, pages: 900, minutes: [15, 45] };
  await txPreparer();
  lancer().dispatchEvent({ type: "click" }); await Hattendre(40);
  exiger(dq.open === true, "au-dela des seuils, la phrase de l'API s'affiche dans un dialogue");
  assert.strictEqual(T($h("#q-texte")), plat_texte(PHRASE_LOT), "phrase telle quelle");
  assert.deepStrictEqual(appelsOcr(), [["ocr_regler", "ocr", true], ["ocr_lancer", "sans_texte", false]], "pas encore de rappel");
  dq.returnValue = "annuler"; dq.close(); await Hattendre(40);
  assert.deepStrictEqual(appelsOcr().length, 2, "refuser ne rappelle pas ocr_lancer");
  exiger(dp.open === true, "refuser laisse le dialogue ouvert");
  lancer().dispatchEvent({ type: "click" }); await Hattendre(40);
  dq.returnValue = "ok"; dq.close(); await Hattendre(40);
  assert.deepStrictEqual(appelsOcr().slice(2), [["ocr_regler", "ocr", true], ["ocr_lancer", "sans_texte", false],
                                               ["ocr_lancer", "sans_texte", false, true]], "rappel avec confirme=True");
  exiger(dp.open === false && HSANS === 0, "lance, jamais sans consentement");

  /* ---- 9. erreurs : phrases telles quelles, dialogue ferme avant le toast ---- */
  HAPPELS = []; HE = offre(5, 20); HE.file = FILE0; await txCarteCharger();
  HREGLER = { erreur: "Valeur invalide." };
  await txPreparer();
  const t2 = lesToasts().length;
  await clique(lancer());
  assert.deepStrictEqual(lesToasts().slice(t2), ["Valeur invalide."]);
  assert.deepStrictEqual(appelsOcr(), [["ocr_regler", "ocr", true]], "pas d'ocr_lancer si le consentement n'est pas ecrit");
  exiger(dp.open === false, "le dialogue est ferme : un toast resterait cache derriere un dialogue modal");
  HREGLER = null;
  HLANCER = () => ({ erreur: "Une opération est déjà en cours : attends qu'elle se termine (ou annule-la)." });
  await txPreparer();
  const t3 = lesToasts().length;
  await clique(lancer());
  assert.deepStrictEqual(lesToasts().slice(t3), ["Une opération est déjà en cours : attends qu'elle se termine (ou annule-la)."]);
  assert.deepStrictEqual(genres().slice(t3), ["toast critique"]);
  HLANCER = () => ({ rien: true });
  await txPreparer();
  const t4 = lesToasts().length;
  await clique(lancer());
  assert.deepStrictEqual(lesToasts().slice(t4), ["Aucun document à préparer."]);
  exiger(dp.open === false, "rien a preparer : le dialogue se ferme");
  /* lecture de l'etat en erreur : pas de dialogue */
  const lire0 = HE;
  HE = { erreur: "Texte des cours : une erreur est survenue." };
  const t5 = lesToasts().length;
  await txPreparer();
  exiger(dp.open === false, "ocr_etat en erreur : le dialogue ne s'ouvre pas");
  assert.deepStrictEqual(lesToasts().slice(t5), ["Texte des cours : une erreur est survenue."]);
  HE = lire0;

  /* ---- 10. progression : le document et la page en cours, par le point d'appel ---- */
  txCarteReporte = false;                       // un nouveau lancement de l'application
  HAPPELS = []; HE = offre(18, 312); HE.file = FILE0; carte.hidden = true; TX = null;
  window.textesProgres({ etat: "en_cours", document: "Cours A/Section 1/article.pdf", page: 3, pages: 24,
                         documents_faits: 2, documents_total: 18, restant_min: null, message: "" });
  exiger(carte.hidden === false, "la progression montre la carte");
  exiger(visible(C(".tx-carte-travail")), "bloc de travail visible");
  assert.strictEqual(T(C(".tx-carte-document")), "article.pdf", "le document en cours, sans son dossier");
  assert.strictEqual(T(C(".tx-carte-page")), "Page 3 sur 24");
  assert.strictEqual(T(C(".tx-carte-rang")), "Document 3 sur 18");
  exiger(visible(C('[data-action="pause"]')) && visible(C('[data-action="annuler"]')), "Pause et Annuler");
  exiger(C("#tx-preparer").hidden === true && C('[data-action="reprendre"]').hidden === true, "ni Preparer ni Reprendre");
  assert.strictEqual(TX.file.page, 3, "textesProgres garde son comportement : TX.file");
  exiger(occupations.has("textes"), "la barre globale reste celle d'app.js");
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_etat"), [], "en cours : aucune relecture a chaque progression");
  window.textesProgres({ etat: "en_cours", document: "Cours A/Section 1/article.pdf", page: 4, pages: 24,
                         documents_faits: 2, documents_total: 18, restant_min: null, message: "" });
  assert.strictEqual(T(C(".tx-carte-page")), "Page 4 sur 24");
  window.textesProgres({ etat: "en_cours", document: "", page: 0, pages: 0, documents_faits: 0, documents_total: 0 });
  exiger(C(".tx-carte-page").hidden === true, "sans page connue, aucune ligne de page inventee");

  /* ---- 11. Pause, Reprendre, Annuler (meme si l'offre a ete reportee par « Plus tard ») ---- */
  txCarteReporte = true;
  window.textesProgres({ etat: "en_cours", document: "a/b.pdf", page: 1, pages: 2, documents_faits: 0, documents_total: 5 });
  HFILE = { etat: "pause", document: "", page: 0, pages: 0, documents_faits: 1, documents_total: 5, reprise: 4 };
  await clique(C('[data-action="pause"]'));
  assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_pause").length, 1, "Pause appelle ocr_pause");
  assert.strictEqual(T(C('[data-action="reprendre"]')), "Reprendre l'extraction (4 documents restants)");
  exiger(carte.hidden === false && visible(C('[data-action="reprendre"]')), "une file en pause se reprend, meme apres « Plus tard »");
  exiger(C(".tx-carte-travail").hidden === true && C('[data-action="pause"]').hidden === true, "apres la pause : Reprendre");
  HFILE = { etat: "en_cours", document: "a/b.pdf", page: 1, pages: 2, documents_faits: 1, documents_total: 5, reprise: 0 };
  await clique(C('[data-action="reprendre"]'));
  assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_reprendre").length, 1, "Reprendre appelle ocr_reprendre");
  exiger(visible(C(".tx-carte-travail")) && visible(C('[data-action="pause"]')), "la reprise remet le travail a l'ecran");
  HFILE = { etat: "annulee", document: "", page: 0, pages: 0, documents_faits: 1, documents_total: 5, reprise: 4 };
  await clique(C('[data-action="annuler"]'));
  assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_annuler").length, 1, "Annuler appelle ocr_annuler");
  exiger(visible(C('[data-action="reprendre"]')), "apres l'annulation, la file qui reste se reprend");
  /* une pause venue de Python (fermeture, synchronisation) */
  HE = etat({ file: { etat: "pause", documents_faits: 3, documents_total: 8, reprise: 5 } });
  window.textesProgres({ etat: "pause", document: "", page: 0, pages: 0, documents_faits: 3, documents_total: 8 });
  await Hattendre(40);
  assert.strictEqual(T(C('[data-action="reprendre"]')), "Reprendre l'extraction (5 documents restants)", "relu depuis l'API");
  HE = etat({ file: { etat: "pause_sync", document: "a/b.pdf", page: 1, pages: 2, documents_faits: 3, documents_total: 8, reprise: 5 } });
  window.textesProgres({ etat: "pause_sync", document: "a/b.pdf", page: 1, pages: 2, documents_faits: 3, documents_total: 8 });
  await Hattendre(40);
  exiger(visible(C(".tx-carte-pause")), "pause pour la synchronisation : une phrase");
  assert.strictEqual(T(C(".tx-carte-pause")), "En pause pendant la synchronisation. Elle reprend à la fin.");
  exiger(C('[data-action="pause"]').hidden === true, "pas de Pause pendant une pause");
  /* fin du travail : la carte relit l'etat (nouveaux documents en attente), puis disparait quand il ne reste rien */
  txCarteReporte = false;
  HE = etat({ compteurs: { a_preparer: 4, pages_a_preparer: 10 }, file: { etat: "terminee", documents_faits: 8, documents_total: 8, reprise: 0 } });
  window.textesProgres({ etat: "terminee", document: "", page: 0, pages: 0, documents_faits: 8, documents_total: 8 });
  await Hattendre(60);
  exiger(carte.hidden === false && T(C(".tx-carte-nombres")) === "4 documents, environ 10 pages.", "terminee : l'etat relu montre ce qui attend");
  HE = etat({ file: { etat: "terminee", documents_faits: 8, documents_total: 8, reprise: 0 } });
  window.textesProgres({ etat: "terminee", document: "", page: 0, pages: 0, documents_faits: 8, documents_total: 8 });
  await Hattendre(60);
  exiger(carte.hidden === true, "terminee et plus rien a preparer : la carte disparait");

  /* ---- 12. liens de la carte ---- */
  await clique($h("#tx-reglages"));
  exiger($h("#tiroir").classList.contains("ouvert"), "Reglages de l'extraction ouvre le tiroir des reglages");
  const liensQuoi = [$h("#tx-quoi")].concat(Hdescend(document.body).filter(e => e.getAttribute("data-action") === "quoi"));
  exiger(liensQuoi.length === 2, "le lien de la carte et celui de l'etat vide");
  for (const lien of liensQuoi) assert.strictEqual(lien._ecoute.click.length, 1, "un seul ecouteur sur le lien du panneau (ecart 202)");

  /* ---- 12b. ecart 292 : « Installer » des reglages = meme chemin, meme barre, meme « Annuler » que la carte ---- */
  HE = etat({ moteur: { present: false }, compteurs: { a_preparer: 3, pages_a_preparer: 9 } });
  await txCarteCharger();
  ouvrirTiroir(false); await clique($h("#b-reglages")); await Hattendre(40);
  const bInst = $h("#r-tx-ocr-installer"), bEmpl = $h("#r-tx-ocr-choisir");
  const zoneR = $h("#r-tx-ocr-installation");
  exiger(bInst && bEmpl && zoneR, "le groupe des reglages a Installer et sa zone d'installation");
  const barreR = zoneR.querySelector("progress"), annulerR = zoneR.querySelector("button");
  exiger(barreR && annulerR && T(annulerR) === "Annuler", "la zone porte une barre et un bouton Annuler");
  exiger(zoneR.hidden === true && bInst.disabled !== true, "hors installation : zone masquee, Installer actif");
  const appelsInst = () => HAPPELS.filter(a => a[0] === "ocr_installer").length;
  const annulsInst = () => HAPPELS.filter(a => a[0] === "ocr_installer_annuler").length;
  HAPPELS = [];
  /* une erreur : la phrase de l'API, telle quelle, et tout est remis en etat */
  HINSTALLER = { erreur: PHRASE_INSTALLER };
  const t6 = lesToasts().length;
  await clique(bInst);
  assert.strictEqual(appelsInst(), 1, "Installer des reglages appelle ocr_installer");
  assert.deepStrictEqual(lesToasts().slice(t6), [PHRASE_INSTALLER], "la phrase de l'API, telle quelle");
  exiger(zoneR.hidden === true && bInst.disabled === false && bEmpl.disabled === false, "apres l'erreur : tout est libere");
  /* en cours : etat occupe, les deux boutons Installer desactives, un seul appel */
  HAPPELS = [];
  let finiR; HINSTALLER = new Promise(res => { finiR = res; });
  const enCoursR = clique(bInst);
  exiger(visible(zoneR), "installation en cours : la zone des reglages est visible");
  exiger(bInst.disabled === true && bEmpl.disabled === true, "les boutons des reglages sont desactives");
  exiger(C('[data-action="installer"]').disabled === true && C('[data-action="installer"]').hidden === true,
    "le bouton Installer de la carte est desactive aussi");
  await clique(bInst); await clique(C('[data-action="installer"]'));
  assert.strictEqual(appelsInst(), 1, "un seul appel, quel que soit le bouton");
  window.textesInstallation({ recu: 40, total: 100 });
  assert.strictEqual(barreR.value, 40, "la barre des reglages suit la progression");
  assert.ok(T(zoneR.querySelector("p")).includes("40"), "le pourcentage est ecrit dans les reglages");
  assert.strictEqual(C(".tx-carte-installation progress").value, 40, "la barre de la carte suit la meme progression");
  let retraits = 0; const retire = barreR.removeAttribute.bind(barreR);
  barreR.removeAttribute = nom => { if (nom === "value") retraits++; retire(nom); };   // le DOM factice garde la valeur
  window.textesInstallation({ recu: 5, total: 0 });
  assert.strictEqual(retraits, 1, "sans total connu, la barre des reglages redevient indeterminee");
  await clique(annulerR);
  assert.strictEqual(annulsInst(), 1, "Annuler des reglages appelle ocr_installer_annuler");
  finiR({ annule: true });
  await enCoursR; await Hattendre(40);
  exiger(zoneR.hidden === true && bInst.disabled === false && bEmpl.disabled === false
         && C('[data-action="installer"]').disabled === false, "installation finie : tout est libere des deux cotes");
  /* l'installation lancee depuis la carte occupe aussi les reglages, et le meme Annuler la coupe */
  HAPPELS = [];
  let finiC; HINSTALLER = new Promise(res => { finiC = res; });
  const enCoursC = clique(C('[data-action="installer"]'));
  exiger(visible(zoneR) && bInst.disabled === true, "lancee depuis la carte : les reglages sont occupes");
  await clique(bInst);
  assert.strictEqual(appelsInst(), 1, "le bouton des reglages ne relance rien");
  await clique(annulerR);
  assert.strictEqual(annulsInst(), 1, "le meme Annuler coupe l'installation lancee depuis la carte");
  finiC({ annule: true });
  await enCoursC; await Hattendre(40);
  exiger(zoneR.hidden === true && bInst.disabled === false, "fin : les reglages sont libres");
  /* succes : le groupe affiche le moteur, la carte aussi */
  HINSTALLER = etat({ moteur: Object.assign({}, MOTEUR, { exe: "C:\\moteur\\tesseract.exe" }) });
  await clique(bInst);
  assert.strictEqual($h("#r-tx-ocr-exe").textContent, "C:\\moteur\\tesseract.exe", "le chemin du moteur installe est ecrit");
  assert.ok(T($h("#r-tx-ocr-moteur")).includes("Moteur détecté"), "la ligne du moteur suit l'installation");
  HINSTALLER = { erreur: PHRASE_INSTALLER };
  ouvrirTiroir(false);

  /* ---- 13. au total : jamais d'extraction sans consentement ---- */
  assert.strictEqual(HSANS, 0, "aucun ocr_lancer sans consentement sur tout le parcours");
  console.log("OK");
  process.exit(0);
})().catch(e => { console.error(e && e.stack ? e.stack : e); process.exit(1); });
"""


if __name__ == "__main__":
    unittest.main()
