"""Tests des reglages de texte et de la carte de Ma semaine (tache R11, contrat 6).

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque. Deux familles de tests, comme tests/test_quoi_js.py.

Statiques : « Format du texte » et la ligne des copies d'originaux sont les seuls reglages de texte
du tiroir ; la version cherchable des PDF, son consentement, l'extraction automatique et tout choix
de dossier de sortie ont disparu de `index.html` et de `app.js` ; le renvoi de la carte porte le nom
du sous-onglet « Choisir quoi traiter ».

Parcours (Node, s'ignore sans `node`) : la page entiere d'index.html est rangee dans le DOM factice
de `tests/test_textes_js.py`, puis les vraies fonctions de commun.js, sync.js, textes.js et app.js
tournent contre une doublure de l'API qui a la forme du contrat 4.2 et 4.7. Le format se lit dans
`ocr_etat()` et s'ecrit par `ocr_regler("ocr_format", ...)` ; les copies se suppriment en deux temps ;
le renvoi ouvre l'onglet puis le sous-onglet sans rien lancer.

Ce que ces tests ne mesurent pas : aucune vraie fenetre pywebview, aucun navigateur (ni rendu, ni
<dialog> natif, ni focus reel), aucun vrai moteur, aucune suppression reelle de copies, Windows et
macOS non executes.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, re, shutil, subprocess, sys, tempfile, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests import test_textes_js as tj
from tests import test_quoi_js as qj

INTERFACE = tj.INTERFACE
lire = tj.lire
plat = tj.plat
corps_de = qj.corps_de
texte_de = qj.texte_de

RETIRES = ("ocr_pdf", "ocr_apres_sync", "mode_pdf", "ocr_lancer", "ocr_pdf_restaurer",
           "ocr_dossier", "ocr_sortie_hors_coffre")


class ReglagesStatique(unittest.TestCase):
    """index.html, app.js, sync.js : ce que le contrat 6 garde et ce qu'il retire."""

    @classmethod
    def setUpClass(cls):
        cls.app = lire(os.path.join(INTERFACE, "app.js"))
        cls.sync = lire(os.path.join(INTERFACE, "sync.js"))
        cls.page = lire(os.path.join(INTERFACE, "index.html"))

    def test_le_format_du_texte_est_le_seul_reglage_de_format(self):
        sans = tj.sans_commentaires(self.app)
        self.assertIn("Format du texte", sans)
        self.assertIn('"r-tx-ocr-format"', sans)
        self.assertIn('[["md", "Markdown (.md)"], ["txt", "Texte brut (.txt)"]]', sans,
                      "les deux options du contrat 6, dans cet ordre")
        self.assertIn('txReglerExtraction("ocr_format", t.value, t, false)', sans,
                      "le changement passe par ocr_regler(\"ocr_format\", ...)")

    def test_les_reglages_retires_ne_sont_plus_dans_la_page(self):
        for nom in RETIRES:
            with self.subTest(nom=nom):
                self.assertNotIn(nom, self.page, "index.html ne nomme plus %s" % nom)
        for ident in ("r-tx-ocr-pdf", "r-tx-ocr-pdf-aide", "r-tx-ocr-actif", "r-tx-ocr-apres"):
            with self.subTest(ident=ident):
                self.assertNotIn(ident, self.page, "controle retire : %s" % ident)

    def test_les_reglages_retires_ne_sont_plus_dans_le_code(self):
        for nom, source in (("app.js", self.app), ("sync.js", self.sync)):
            sans = tj.sans_commentaires(source)
            for retire in RETIRES:
                with self.subTest(fichier=nom, nom=retire):
                    self.assertNotIn(retire, sans, "%s ne nomme plus %s" % (nom, retire))
        self.assertNotRegex(tj.sans_commentaires(self.app), r"function\s+txReglerMode\b",
                            "le consentement du mode des PDF est parti")

    def test_la_ligne_des_copies_et_son_bouton(self):
        sans = tj.sans_commentaires(self.app)
        self.assertIn("Copies d'originaux", sans)
        self.assertIn("Supprimer les copies", sans)
        self.assertIn('"r-tx-ocr-originaux"', sans)
        # Deux temps : la fonction demande confirmation avant le second appel (contrat 4.7).
        corps = corps_de(sans, "txSupprimerOriginaux") or ""
        self.assertTrue(corps, "txSupprimerOriginaux est la fonction du bouton")
        self.assertIn("r.confirmer", corps)
        self.assertIn("confirmer(", corps)
        self.assertGreaterEqual(corps.count("ocr_originaux_supprimer("), 2, "un premier appel, puis un rappel")
        self.assertIn("ocr_originaux_supprimer(true)", corps, "le rappel passe confirme=true")

    def test_la_carte_renvoie_au_sous_onglet(self):
        carte = self.page[self.page.find('id="tx-carte"'):]
        carte = carte[:carte.find("</section>")]
        m = re.search(r'<button[^>]*id="tx-choisir-quoi"[^>]*>([^<]*)</button>', carte)
        self.assertIsNotNone(m, "le renvoi de la carte est present")
        self.assertEqual(plat(m.group(1)), "Choisir quoi traiter")
        sans = tj.sans_commentaires(self.sync)
        i = sans.find('t.id === "tx-choisir-quoi"')
        self.assertGreater(i, 0, "sync.js branche le renvoi")
        suite = sans[i:i + 400]
        self.assertIn('choisirOnglet("textes")', suite)
        self.assertIn('txMontrerVue("choisir")', suite)
        self.assertNotIn("ocr_traiter", sans, "la carte ne lance aucun traitement")

    def test_fichiers_en_lf(self):
        for chemin in (os.path.join(INTERFACE, "app.js"), os.path.join(INTERFACE, "sync.js"),
                       os.path.join(INTERFACE, "index.html"), os.path.abspath(__file__)):
            with self.subTest(fichier=os.path.basename(chemin)):
                with open(chemin, "rb") as f:
                    self.assertNotIn(b"\r", f.read())

    # ------------------------------------------------------------------ parcours sur DOM factice
    @unittest.skipUnless(shutil.which("node"), "node absent : parcours sur DOM factice non execute")
    def test_parcours_des_reglages_et_du_renvoi(self):
        node = shutil.which("node") or "node"
        coupe = tj.ENTETE.find("/* ---- arbre de la page")
        self.assertGreater(coupe, 0, "marqueur de l'arbre de la page introuvable")
        entete = re.sub(r"let SC = \[.*?\];\n", "", tj.ENTETE[:coupe], count=1, flags=re.S)
        dossier = tempfile.mkdtemp(prefix="parcours-r11-")
        script = os.path.join(dossier, "_parcours_r11.js")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(entete + "\n" + qj.OUTILS + "\n" + MANQUES + "\n")
                for nom in ("commun.js", "sync.js", "textes.js", "app.js"):
                    f.write("\n/* ===== %s ===== */\n" % nom)
                    f.write(lire(os.path.join(INTERFACE, nom)).replace("\r\n", "\n"))
                f.write("\n" + PARCOURS)
            r = subprocess.run([node, script, INTERFACE], capture_output=True, text=True, timeout=180)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        self.assertEqual(r.returncode, 0, "le parcours a echoue :\n%s\n%s" % (r.stdout, r.stderr))
        self.assertIn("OK", r.stdout)


MANQUES = r"""
if (!HElement.prototype.matches) HElement.prototype.matches = function (sel) { return Hsimple(this, sel); };
let occupe = false, semainePrete = true;
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
  const PHRASE = "Les copies d'originaux seront supprimées. Une restauration ne sera plus possible " +
    "sans retélécharger le PDF depuis Moodle.";

  let HREG = etat({}), HREGLER = null, HORIGINAUX = null;
  const HAPPELS = [];
  const API = {
    ocr_etat: async () => { HAPPELS.push(["ocr_etat"]); return copie(HREG); },
    ocr_arbre: async () => { HAPPELS.push(["ocr_arbre"]);
      return { racine: "D:/Cours", cours: [], compteurs: COMPTEURS0 }; },
    ocr_regler: async (cle, valeur) => {
      HAPPELS.push(["ocr_regler", cle, valeur]);
      if (HREGLER) return HREGLER;
      if (cle === "ocr_format") HREG.reglages = Object.assign({}, HREG.reglages, { ocr_format: String(valeur) });
      return copie(HREG); },
    ocr_originaux_supprimer: async (...args) => {
      HAPPELS.push(args.length ? ["ocr_originaux_supprimer", args[0]] : ["ocr_originaux_supprimer"]);
      if (HORIGINAUX) return HORIGINAUX;
      if (!args[0]) return { confirmer: PHRASE, nombre: 3, octets: 4096 };
      HREG.originaux = { nombre: 0, octets: 0 };
      return { ok: true, nombre: 3, octets: 4096 }; },
    ocr_installer: async () => ({ ok: true }),
    ocr_installer_annuler: async () => ({ ok: true }),
    ocr_choisir_exe: async () => ({ annule: true }),
    ocr_lancer: async (...a) => { HAPPELS.push(["ocr_lancer"].concat(a)); return { file: FILE0 }; },
    sync_etat: async () => ({ accueil: false, site: "https://m.exemple.ch", dest: "D:/Cours", langue: "fr",
      langues: [{ code: "fr", nom: "Français" }], statuts: false, note: false, auto: false,
      titres_youtube: false, jeton: false, textes: { statuts: "Sous-dossiers par statut", note: "Lister les nouveautés" } }),
  };
  window.pywebview = { api: API };
  INFOS = { theme: "systeme", semaine_active: false, verif_action: "aucune", navigateurs: "x",
            explorateur: "y", version: "1.0" };
  occupe = false; semainePrete = true; syncPrete = true;

  const ouvrir = async () => { ouvrirTiroir(false); await clique($h("#b-reglages")); };

  /* ---- 1. le format se rend depuis ocr_etat(), sans memoire de page ---- */
  HREG = etat({});
  await ouvrir();
  let format = $h("#r-tx-ocr-format");
  exiger(format, "la liste du format est construite dans le groupe");
  assert.deepStrictEqual(format.children.map(o => o.value), ["md", "txt"]);
  assert.strictEqual(format.value, "md", "md quand ocr_etat().reglages.ocr_format vaut md");
  HREG = etat({ reglages: { ocr_langues: "fra+eng", ocr_dpi: 300, ocr_format: "txt" } });
  await ouvrir();
  format = $h("#r-tx-ocr-format");
  assert.strictEqual(format.value, "txt", "txt quand l'API le dit : aucune variable de page ne s'y oppose");
  HREG = etat({});

  /* ---- 2. un changement appelle ocr_regler("ocr_format", ...) ---- */
  await ouvrir();
  HAPPELS.length = 0;
  format = $h("#r-tx-ocr-format");
  format.value = "txt"; format.dispatchEvent({ type: "change" }); await Hattendre(60);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler"), [["ocr_regler", "ocr_format", "txt"]]);
  assert.strictEqual($h("#r-tx-ocr-format").value, "txt", "la reponse de l'API laisse la liste sur txt");
  HREGLER = { erreur: "Valeur invalide." };
  format = $h("#r-tx-ocr-format");
  format.value = "md"; format.dispatchEvent({ type: "change" }); await Hattendre(60);
  assert.strictEqual($h("#r-tx-ocr-format").value, "txt", "un refus remet la liste sur la valeur enregistree");
  HREGLER = null;
  HREG = etat({});

  /* ---- 3. les reglages retires n'existent plus dans le DOM ---- */
  await ouvrir();
  for (const ident of ["#r-tx-ocr-actif", "#r-tx-ocr-apres", "#r-tx-ocr-pdf", "#r-tx-ocr-pdf-aide"])
    exiger(!$h(ident), "controle retire de la page : " + ident);
  exiger($h("#r-tx-ocr-langues") && $h("#r-tx-ocr-exe"), "le tiroir garde langues, chemin et moteur");

  /* ---- 4. la ligne des copies et sa suppression en deux temps ---- */
  HREG = etat({ originaux: { nombre: 3, octets: 4096 } });
  await ouvrir();
  let copies = $h("#r-tx-ocr-copies"), bouton = $h("#r-tx-ocr-originaux");
  exiger(copies && bouton, "la ligne des copies et son bouton");
  assert.strictEqual(plat_texte(copies.textContent), "Copies d'originaux : 3, 4 Ko");
  assert.strictEqual(bouton.disabled, false);

  HAPPELS.length = 0;
  const avant = $h("#toasts").children.length;
  await clique(bouton);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_originaux_supprimer"), [["ocr_originaux_supprimer"]],
    "le premier clic demande la phrase, sans supprimer");
  const question = $h("#d-question");
  exiger(question.open === true, "la question s'affiche");
  assert.strictEqual($h("#q-texte").textContent, PHRASE, "la phrase de l'API, telle quelle");
  question.returnValue = ""; question.close(); await Hattendre(60);
  assert.strictEqual(HREG.originaux.nombre, 3, "refuser ne supprime rien");
  assert.deepStrictEqual($h("#toasts").children.slice(avant).map(t => t.textContent), [],
    "refuser n'annonce rien");

  HAPPELS.length = 0;
  bouton = $h("#r-tx-ocr-originaux");
  bouton.dispatchEvent({ type: "click" }); await Hattendre(60);
  question.returnValue = "ok"; question.close(); await Hattendre(80);
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_originaux_supprimer"),
    [["ocr_originaux_supprimer"], ["ocr_originaux_supprimer", true]], "un seul clic d'accord, un seul rappel");
  assert.strictEqual($h("#r-tx-ocr-originaux").disabled, true, "plus de copie : le bouton se desactive");
  copies = $h("#r-tx-ocr-copies");
  assert.strictEqual(plat_texte(copies.textContent), "Copies d'originaux : 0, 0 Ko", "la ligne relit l'etat");

  HREG = etat({ originaux: { nombre: 0, octets: 0 } });
  await ouvrir();
  assert.strictEqual($h("#r-tx-ocr-originaux").disabled, true, "sans copie, le bouton reste desactive");

  /* ---- 5. la carte renvoie au troisieme onglet puis au sous-onglet ---- */
  HREG = etat({ compteurs: { fichiers: 2, traites: 0, a_verifier: 0, echecs: 0, non_traites: 2,
                             pages_non_traitees: 20 } });
  await txCarteCharger();
  const carte = $h("#tx-carte"), renvoi = $h("#tx-choisir-quoi");
  exiger(visible(carte) && visible(renvoi), "la carte montre son renvoi quand il reste a traiter");
  ONGLET = "semaine";
  txMontrerVue("cours");
  HAPPELS.length = 0;
  await clique(renvoi);
  assert.strictEqual(ONGLET, "textes", "le troisième onglet est actif");
  assert.strictEqual(TX.vue, "choisir", "le sous-onglet « Choisir quoi traiter » est actif");
  exiger(visible($h("#tx-v-choisir")) && !visible($h("#tx-v-cours")), "le panneau choisir est visible");
  assert.deepStrictEqual(HAPPELS.filter(a => a[0] === "ocr_regler" || a[0] === "ocr_lancer" || a[0] === "ocr_traiter"),
    [], "le renvoi ne regle ni ne lance rien");

  console.log("OK");
  process.exit(0);
})().catch(e => { console.error(e && e.stack ? e.stack : e); process.exit(1); });
"""


if __name__ == "__main__":
    unittest.main()
