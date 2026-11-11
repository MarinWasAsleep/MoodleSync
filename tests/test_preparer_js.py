"""Tests de la carte de Ma semaine apres O9 (tache R11).

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque. Deux familles de tests, comme tests/test_quoi_js.py.

Statiques : la carte `#tx-carte` est dans `#v-semaine`, son renvoi porte le nom du sous-onglet
« Choisir quoi traiter », le dialogue de consentement `#d-tx-preparer` et `txPreparer` ont disparu,
aucune fonction de la carte n'appelle l'API de lancement, et les noms de l'ancienne API ne restent
nulle part dans `moodlesync/interface/`.

Parcours (Node, s'ignore sans `node`) : la page entiere d'index.html est lue et rangee dans un DOM
minimal, puis les vraies fonctions de commun.js, sync.js, textes.js et app.js tournent contre une
doublure de l'API qui a la forme du contrat 4.2. Le renvoi ouvre le troisieme onglet puis le
sous-onglet, les nombres viennent des compteurs, et Pause, Reprendre et Annuler restent branches.

Ce que ces tests ne mesurent pas : aucune vraie fenetre pywebview, aucun navigateur (donc ni rendu,
ni <dialog> natif, ni focus reel), aucun vrai moteur, aucune duree reelle, Windows et macOS non
executes.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, re, shutil, subprocess, sys, tempfile, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests import test_textes_js as tj
from tests import test_quoi_js as qj

INTERFACE = tj.INTERFACE
HTML_CONSTRUIT = tj.HTML_CONSTRUIT
lire = tj.lire
plat = tj.plat
corps_de = qj.corps_de
texte_de = qj.texte_de

# Noms de l'ancienne API que la refonte retire (contrat 4.8 et decision O10).
ANCIENS = ("ocr_pdf", "ocr_apres_sync", "mode_pdf", "ocr_lancer", "ocr_pdf_restaurer")

# Identifiants de la carte apres O9 et O18 : le renvoi remplace « Preparer », et le bouton mort
# « A quoi ca sert ? » (#tx-quoi) a disparu (E-V7-1).
IDS_CARTE = {"tx-carte", "tx-choisir-quoi", "tx-plus-tard", "tx-reglages"}


def bloc(page, debut, fin="</section>"):
    i = page.find(debut)
    j = page.find(fin, i)
    return page[i:j + len(fin)] if i >= 0 and j > i else ""


class CarteStatique(unittest.TestCase):
    """index.html et sync.js : ce que la carte dit et ce qu'elle ne fait plus."""

    @classmethod
    def setUpClass(cls):
        cls.page = lire(os.path.join(INTERFACE, "index.html"))
        cls.sync = lire(os.path.join(INTERFACE, "sync.js"))
        cls.textes = lire(os.path.join(INTERFACE, "textes.js"))
        cls.app = lire(os.path.join(INTERFACE, "app.js"))
        cls.carte = bloc(cls.page, '<section class="carte-s tx-carte" id="tx-carte"')

    def test_la_carte_est_dans_ma_semaine_et_pas_dans_mes_cours(self):
        self.assertTrue(self.carte, "la carte #tx-carte est introuvable dans index.html")
        sync = self.page.find('id="v-sync"')
        semaine = self.page.find('id="v-semaine"')
        textes = self.page.find('id="v-textes"')
        place = self.page.find('id="tx-carte"')
        self.assertTrue(0 < sync < semaine < textes)
        self.assertTrue(semaine < place < textes, "#tx-carte doit etre dans #v-semaine")
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

    def test_le_renvoi_porte_le_nom_du_sous_onglet(self):
        m = re.search(r'<button[^>]*id="tx-choisir-quoi"[^>]*>([^<]*)</button>', self.carte)
        self.assertIsNotNone(m, "le renvoi « Choisir quoi traiter » est absent de la carte")
        self.assertEqual(m.group(1), "Choisir quoi traiter")

    def test_le_dialogue_de_consentement_est_parti(self):
        self.assertNotIn('id="d-tx-preparer"', self.page, "le dialogue de consentement est retire par R11")
        sans = tj.sans_commentaires(self.sync)
        self.assertNotRegex(sans, r"function\s+txPreparer\b")
        self.assertNotRegex(sans, r"function\s+txLancer\b")
        self.assertNotIn('data-action="lancer"', self.page)
        self.assertNotIn('name="sans_texte"', self.page)

    def test_la_carte_garde_pause_annuler_reprendre_installer_et_emplacement(self):
        for action, libelle in (("pause", "Pause"), ("annuler", "Annuler"), ("installer", "Installer"),
                                ("exe", "Indiquer l'emplacement")):
            with self.subTest(action=action):
                m = re.search(r'<button[^>]*data-action="%s"[^>]*>([^<]*)</button>' % action, self.carte)
                self.assertIsNotNone(m, "bouton data-action=\"%s\" absent de la carte" % action)
                self.assertEqual(m.group(1), libelle)
        self.assertRegex(self.carte, r'<button[^>]*data-action="reprendre"')

    def test_le_renvoi_ouvre_l_onglet_puis_le_sous_onglet(self):
        sans = tj.sans_commentaires(self.sync)
        i = sans.find('t.id === "tx-choisir-quoi"')
        self.assertGreater(i, 0, "sync.js ne branche pas #tx-choisir-quoi")
        suite = sans[i:i + 400]
        self.assertIn('choisirOnglet("textes")', suite, "le renvoi active le troisieme onglet")
        self.assertIn('txMontrerVue("choisir")', suite, "puis le sous-onglet « Choisir quoi traiter »")

    def test_aucun_appel_de_lancement_dans_la_carte(self):
        sans = tj.sans_commentaires(self.sync)
        noms = re.findall(r"(?:async\s+)?function\s+(tx\w+)\s*\(", sans)
        self.assertGreaterEqual(len(noms), 5, "les fonctions de la carte : %s" % noms)
        for nom in noms:
            corps = corps_de(sans, nom) or ""
            for appel in ("ocr_lancer", "ocr_regler", "ocr_traiter"):
                with self.subTest(fonction=nom, appel=appel):
                    self.assertNotIn(appel, corps, "la carte ne lance ni ne regle rien")
        self.assertNotIn("ocr_lancer", sans, "aucune fonction de sync.js n'appelle l'ancien lanceur")

    def test_les_nombres_viennent_des_compteurs_du_contrat(self):
        sans = tj.sans_commentaires(self.sync)
        corps = corps_de(sans, "txCarteNombres") or ""
        self.assertTrue(corps, "txCarteNombres est la phrase des documents restants")
        self.assertIn("non_traites", corps)
        self.assertIn("pages_non_traitees", corps, "la page ne calcule rien : elle lit les compteurs")
        for nom in ("a_preparer", "pages_a_preparer", "prevision"):
            with self.subTest(nom=nom):
                self.assertNotIn(nom, sans, "la cle %s n'existe plus (contrat 4.2)" % nom)
        self.assertEqual(sans.count("minutes"), 0, "aucune duree inventee par la page")

    def test_aucun_html_construit_avec_des_donnees(self):
        sans = tj.sans_commentaires(self.sync)
        for nom in re.findall(r"(?:async\s+)?function\s+(tx\w+)\s*\(", sans):
            corps = corps_de(sans, nom) or ""
            for procede in HTML_CONSTRUIT:
                with self.subTest(fonction=nom, procede=procede):
                    self.assertNotIn(procede, corps)
            with self.subTest(fonction=nom, procede="ic/esc"):
                self.assertNotRegex(corps, r"\b(ic|esc)\(")

    def test_aucun_nom_de_l_ancienne_api_dans_l_interface(self):
        for nom in sorted(os.listdir(INTERFACE)):
            if not nom.endswith((".js", ".html", ".css")):
                continue
            source = lire(os.path.join(INTERFACE, nom))
            for ancien in ANCIENS:
                with self.subTest(fichier=nom, nom=ancien):
                    self.assertNotIn(ancien, source, "%s ne doit plus nommer %s" % (nom, ancien))

    def test_le_bouton_a_quoi_ca_sert_est_parti(self):
        """E-V7-1 et O18 : le bouton ne repondait a aucun clic, et aucun JS ne le servait."""
        self.assertNotIn('id="tx-quoi"', self.page, "le bouton mort « À quoi ça sert ? » est retire de la carte")
        self.assertNotIn('id="tx-quoi"', self.carte, "la carte #tx-carte ne porte plus #tx-quoi")
        for nom in sorted(os.listdir(INTERFACE)):
            if not nom.endswith((".js", ".html")):
                continue
            source = tj.sans_commentaires(lire(os.path.join(INTERFACE, nom)))
            with self.subTest(fichier=nom):
                self.assertNotIn("tx-quoi", source, "%s ne doit plus nommer #tx-quoi" % nom)

    def test_aucun_style_nouveau(self):
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
                f.write(entete + "\n" + qj.OUTILS + "\n" + MANQUES + "\n" + CASES_COCHEES + "\n")
                for nom in ("commun.js", "sync.js", "textes.js", "app.js"):
                    f.write("\n/* ===== %s ===== */\n" % nom)
                    f.write(lire(os.path.join(INTERFACE, nom)).replace("\r\n", "\n"))
                f.write("\n" + PARCOURS)
            r = subprocess.run([node, script, INTERFACE], capture_output=True, text=True, timeout=180)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        self.assertEqual(r.returncode, 0, "le parcours a echoue :\n%s\n%s" % (r.stdout, r.stderr))
        self.assertIn("OK", r.stdout)


# Ce que le DOM factice de test_textes_js ne fournit pas encore et dont la page se sert :
# `matches` pour les ecouteurs `change`, et les variables de semaine.js, qui n'est pas chargee ici.
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
  const T = el => plat_texte(el.textContent);
  const clique = async el => { el.dispatchEvent({ type: "click" }); await Hattendre(60); };

  const MOTEUR = { present: true, version: "5.5.3", source: "registre", exe: "C:\\moteur\\tesseract.exe",
                   langues: ["eng", "fra", "osd"], langues_effectives: "fra+eng", repli: false, message: "" };
  const FILE0 = { etat: "inactive", origine: "coffre", document: "", page: 0, pages: 0,
                  documents_faits: 0, documents_total: 0, reprise: 0 };
  const COMPTEURS0 = { fichiers: 0, traites: 0, a_verifier: 0, echecs: 0, non_traites: 0, pages_non_traitees: 0 };
  const ETAT0 = { moteur: MOTEUR, occupe: false, file: FILE0, compteurs: COMPTEURS0,
                  reglages: { ocr_langues: "fra+eng", ocr_dpi: 300, ocr_format: "md" },
                  originaux: { nombre: 0, octets: 0 },
                  depot: { etat: "inactif", dossier_defaut: "", dossier: "", resultats: [] } };
  const etat = sur => fusion(ETAT0, sur);

  let HE = etat({}), HFILE = FILE0;
  const HAPPELS = [];
  const API = {
    ocr_etat: async () => { HAPPELS.push(["ocr_etat"]); return copie(HE); },
    ocr_arbre: async () => { HAPPELS.push(["ocr_arbre"]);
      return { racine: "D:/Cours", cours: [], compteurs: COMPTEURS0 }; },
    ocr_pause: async () => { HAPPELS.push(["ocr_pause"]); return { file: HFILE }; },
    ocr_reprendre: async () => { HAPPELS.push(["ocr_reprendre"]); return { file: HFILE }; },
    ocr_annuler: async () => { HAPPELS.push(["ocr_annuler"]); return { file: HFILE }; },
    ocr_installer: async () => { HAPPELS.push(["ocr_installer"]); return { erreur: "Installation indisponible." }; },
    ocr_installer_annuler: async () => { HAPPELS.push(["ocr_installer_annuler"]); return { ok: true }; },
    ocr_choisir_exe: async () => { HAPPELS.push(["ocr_choisir_exe"]); return { annule: true }; },
    ocr_regler: async (...a) => { HAPPELS.push(["ocr_regler"].concat(a)); return copie(HE); },
    ocr_lancer: async (...a) => { HAPPELS.push(["ocr_lancer"].concat(a)); return { file: FILE0 }; },
    sync_etat: async () => ({ accueil: false, site: "https://m.exemple.ch", dest: "D:/Cours", langue: "fr",
      langues: [{ code: "fr", nom: "Français" }], statuts: false, note: false, auto: false,
      titres_youtube: false, jeton: false, textes: { statuts: "Sous-dossiers par statut", note: "Lister les nouveautés" } }),
  };
  window.pywebview = { api: API };
  INFOS = { theme: "systeme", semaine_active: false, verif_action: "aucune", navigateurs: "x",
            explorateur: "y", version: "1.0" };
  occupe = false; semainePrete = true; syncPrete = true;

  const carte = $h("#tx-carte");
  exiger(carte, "la carte #tx-carte est dans la page");
  exiger(carte.closest("#v-semaine") && !carte.closest("#v-sync"), "la carte est dans #v-semaine");
  exiger(!$h("#d-tx-preparer"), "le dialogue de consentement est parti");
  exiger(!$h("#tx-quoi"), "le bouton mort « À quoi ça sert ? » est parti (E-V7-1)");
  const C = s => carte.querySelector(s);

  /* ---- 1. au chargement : la carte lit l'etat, ne lance rien, et reste masquee sans reste a traiter ---- */
  exiger(carte.hidden === true, "sans etat lu, la carte est masquee");
  await txCarteCharger(); await Hattendre(40);
  exiger(carte.hidden === true, "non_traites 0 : la carte reste masquee");
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] !== "ocr_etat"), [], "la carte ne fait que lire l'etat");
  assert.deepStrictEqual(HAPPELS, [["ocr_etat"]], "au chargement, un seul ocr_etat : " + JSON.stringify(HAPPELS));

  /* ---- 2. des documents non traites : la carte, ses nombres et son renvoi ---- */
  HE = etat({ compteurs: { fichiers: 18, traites: 0, a_verifier: 0, echecs: 0, non_traites: 18, pages_non_traitees: 312 } });
  await txCarteCharger();
  exiger(visible(carte), "non_traites > 0 : la carte est visible");
  assert.strictEqual(T(C(".tx-carte-nombres")), "18 documents, environ 312 pages.");
  exiger(visible(C("#tx-choisir-quoi")), "le renvoi « Choisir quoi traiter » est visible");
  exiger(visible(C("#tx-plus-tard")), "« Plus tard » reste offert");
  for (const a of ["reprendre", "pause", "annuler", "installer", "exe"])
    exiger(C('[data-action="' + a + '"]').hidden === true, a + " est masque quand rien ne travaille");
  exiger(C(".tx-carte-travail").hidden === true && C(".tx-carte-moteur").hidden === true, "ni travail ni moteur absent");
  HE = etat({ compteurs: { fichiers: 1, traites: 0, a_verifier: 0, echecs: 0, non_traites: 1, pages_non_traitees: 1 } });
  await txCarteCharger();
  assert.strictEqual(T(C(".tx-carte-nombres")), "1 document, environ 1 page.", "singulier");
  HE = etat({ compteurs: { fichiers: 2, traites: 0, a_verifier: 0, echecs: 0, non_traites: 2, pages_non_traitees: 1224 } });
  await txCarteCharger();
  assert.strictEqual(C(".tx-carte-nombres").textContent, "2 documents, environ 1\u00a0224 pages.");
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] !== "ocr_etat"), [], "lire les nombres ne lance rien");

  /* ---- 3. le renvoi ouvre le troisieme onglet, puis le sous-onglet ---- */
  HE = etat({ compteurs: { fichiers: 18, traites: 0, a_verifier: 0, echecs: 0, non_traites: 18, pages_non_traitees: 312 } });
  await txCarteCharger();
  ONGLET = "semaine";
  txMontrerVue("cours");
  await clique($h("#tx-choisir-quoi"));
  assert.strictEqual(ONGLET, "textes", "le renvoi active l'onglet « Mes textes »");
  exiger($h("#v-textes").hidden === false && $h("#v-semaine").hidden === true, "l'onglet Mes textes est affiche");
  assert.strictEqual(TX.vue, "choisir", "le sous-onglet « Choisir quoi traiter » est actif");
  exiger($h("#tx-v-choisir").hidden === false && $h("#tx-v-cours").hidden === true, "le panneau choisir est visible");
  assert.strictEqual($h("#tx-o-choisir").getAttribute("aria-selected"), "true");
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_lancer" || a[0] === "ocr_regler"), [],
    "le renvoi n'ecrit ni ne lance rien");

  /* ---- 4. « Plus tard » masque la carte, un travail en cours la ramene ---- */
  await clique($h("#tx-plus-tard"));
  exiger(carte.hidden === true, "« Plus tard » masque la carte");
  await txCarteCharger();
  exiger(carte.hidden === true, "elle reste masquee apres une relecture");
  txCarteReporte = false;                       // un nouveau lancement de l'application
  window.textesProgres({ etat: "en_cours", document: "Cours A/Section 1/article.pdf", page: 3, pages: 24,
                         documents_faits: 2, documents_total: 18 });
  exiger(visible(carte), "une extraction en cours montre la carte");
  exiger(visible(C(".tx-carte-travail")), "bloc de travail visible");
  assert.strictEqual(T(C(".tx-carte-document")), "article.pdf", "le document en cours, sans son dossier");
  assert.strictEqual(T(C(".tx-carte-page")), "Page 3 sur 24");
  assert.strictEqual(T(C(".tx-carte-rang")), "Document 3 sur 18");
  exiger(visible(C('[data-action="pause"]')) && visible(C('[data-action="annuler"]')), "Pause et Annuler");
  exiger(C("#tx-choisir-quoi").hidden === true, "aucun renvoi pendant un travail");
  txCarteReporte = true;                        // le renvoi reporte ne cache jamais le travail

  /* ---- 5. Pause, Reprendre, Annuler ---- */
  HFILE = { etat: "pause", document: "", page: 0, pages: 0, documents_faits: 1, documents_total: 5, reprise: 4 };
  await clique(C('[data-action="pause"]'));
  assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_pause").length, 1, "Pause appelle ocr_pause");
  assert.strictEqual(T(C('[data-action="reprendre"]')), "Reprendre l'extraction (4 documents restants)");
  exiger(visible(carte) && visible(C('[data-action="reprendre"]')), "une file en pause se reprend, meme apres « Plus tard »");
  HFILE = { etat: "en_cours", document: "a/b.pdf", page: 1, pages: 2, documents_faits: 1, documents_total: 5, reprise: 0 };
  await clique(C('[data-action="reprendre"]'));
  assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_reprendre").length, 1, "Reprendre appelle ocr_reprendre");
  HFILE = { etat: "annulee", document: "", page: 0, pages: 0, documents_faits: 1, documents_total: 5, reprise: 4 };
  await clique(C('[data-action="annuler"]'));
  assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_annuler").length, 1, "Annuler appelle ocr_annuler");
  exiger(visible(C('[data-action="reprendre"]')), "apres l'annulation, la file qui reste se reprend");

  /* ---- 6. une pause venue de Python : une phrase, pas de bouton Pause ---- */
  HE = etat({ file: { etat: "pause_sync", document: "a/b.pdf", page: 1, pages: 2,
                      documents_faits: 3, documents_total: 8, reprise: 5 } });
  window.textesProgres({ etat: "pause_sync", document: "a/b.pdf", page: 1, pages: 2,
                         documents_faits: 3, documents_total: 8 });
  await Hattendre(40);
  exiger(visible(C(".tx-carte-pause")), "pause pour la synchronisation : une phrase");
  assert.strictEqual(T(C(".tx-carte-pause")), "En pause pendant la synchronisation. Elle reprend à la fin.");
  exiger(C('[data-action="pause"]').hidden === true, "pas de Pause pendant une pause");

  /* ---- 7. fin du travail : la carte relit l'etat, puis disparait quand il ne reste rien ---- */
  txCarteReporte = false;
  HE = etat({ compteurs: { fichiers: 4, traites: 0, a_verifier: 0, echecs: 0, non_traites: 4, pages_non_traitees: 10 },
              file: { etat: "terminee", origine: "coffre", document: "", page: 0, pages: 0,
                      documents_faits: 8, documents_total: 8, reprise: 0 } });
  window.textesProgres({ etat: "terminee", document: "", page: 0, pages: 0, documents_faits: 8, documents_total: 8 });
  await Hattendre(80);
  exiger(visible(carte) && T(C(".tx-carte-nombres")) === "4 documents, environ 10 pages.",
    "terminee : l'etat relu montre ce qui reste");
  HE = etat({ file: { etat: "terminee", origine: "coffre", document: "", page: 0, pages: 0,
                      documents_faits: 8, documents_total: 8, reprise: 0 } });
  window.textesProgres({ etat: "terminee", document: "", page: 0, pages: 0, documents_faits: 8, documents_total: 8 });
  await Hattendre(80);
  exiger(carte.hidden === true, "terminee et plus rien a traiter : la carte disparait");

  /* ---- 8. moteur absent : la phrase, Installer et l'emplacement ; le renvoi n'est pas un lancement ---- */
  HE = etat({ moteur: Object.assign({}, MOTEUR, { present: false }),
              compteurs: { fichiers: 3, traites: 0, a_verifier: 0, echecs: 0, non_traites: 3, pages_non_traitees: 9 } });
  await txCarteCharger();
  exiger(visible(carte), "la carte reste visible sans moteur");
  assert.strictEqual(T(C(".tx-carte-moteur")), "Le moteur d'extraction n'est pas encore installé.");
  exiger(visible(C('[data-action="installer"]')) && visible(C('[data-action="exe"]')), "Installer et l'emplacement");
  const t0 = $h("#toasts").children.length;
  await clique(C('[data-action="installer"]'));
  assert.strictEqual(HAPPELS.filter(a => a[0] === "ocr_installer").length, 1, "Installer appelle ocr_installer");
  exiger($h("#toasts").children.length > t0, "l'erreur de l'API s'affiche");

  /* ---- 9. les reglages restent joignables depuis la carte ---- */
  await clique($h("#tx-reglages"));
  exiger($h("#tiroir").classList.contains("ouvert"), "Reglages de l'extraction ouvre le tiroir");

  /* ---- 10. aucun lancement ni consentement implicite sur tout le parcours ---- */
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_lancer" || a[0] === "ocr_regler"), [],
    "jamais d'ocr_lancer ni d'ocr_regler : " + JSON.stringify(HAPPELS));
  console.log("OK");
  process.exit(0);
})().catch(e => { console.error(e && e.stack ? e.stack : e); process.exit(1); });
"""


if __name__ == "__main__":
    unittest.main()
