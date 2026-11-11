"""Tests de la vue « Choisir quoi traiter » de « Mes textes » (tache R9, contrat 5.4).

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque. Le parcours (Node, s'ignore sans `node`) range la vraie page d'index.html dans le DOM factice
de tests/test_textes_js.py, charge la vraie coque et le vrai composant d'arborescence, puis monte la
vue dans son vrai conteneur (`#tx-v-choisir`). Les evenements remontent jusqu'a `document` comme dans
un navigateur.

Le rendu et les reponses viennent des fixtures de docs/refonte-textes/fixtures/ (contrat 5.6) :
`arbre.json`, `etat.json` et `traiter_confirmation.json`. Le parcours verifie : le montage de la vue
et son dialogue cree dans le conteneur, le resume vivant (`choix_resume` et
`choix_resume_sans_pages`), « Tout cocher » et « Tout decocher », la selection d'un dossier entier
rendue comme le dossier seul, la selection mixte, l'appel sans `confirme` puis avec `confirme`,
le dialogue et ses nombres, le moteur absent, le gel pendant un traitement, le vidage a la fin et
les deux reponses qui se disent en toast (`rien`, `erreur`).

Ce que ces tests ne mesurent pas : aucun vrai navigateur (donc ni rendu, ni `<dialog>` modal natif,
ni focus reel, ni lecture d'ecran), aucun vrai moteur, Windows et macOS non executes.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import json, os, re, shutil, subprocess, sys, tempfile, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests import test_textes_js as tj

INTERFACE = tj.INTERFACE
FIXTURES = os.path.join(tj.DOCS, "fixtures")


def lire(nom):
    return tj.lire(os.path.join(INTERFACE, nom))


def charger(nom):
    with open(os.path.join(FIXTURES, nom), encoding="utf-8") as f:
        return json.load(f)


class VueStatique(unittest.TestCase):
    """textes-choisir.js : la vue, son arbre, son dialogue, et l'API appelee par elle seule."""

    @classmethod
    def setUpClass(cls):
        cls.source = lire("textes-choisir.js")
        cls.feuille = lire("textes-choisir.css")
        cls.page = lire("index.html")

    def test_fichier_en_lf_et_fini_par_un_saut_de_ligne(self):
        self.assertGreater(len(self.source), 1500, "textes-choisir.js est vide ou presque")
        self.assertTrue(self.source.endswith("\n"))
        for nom in ("textes-choisir.js", "textes-choisir.css"):
            with self.subTest(fichier=nom):
                with open(os.path.join(INTERFACE, nom), "rb") as f:
                    self.assertNotIn(b"\r", f.read(), "un fichier de la tache s'ecrit en LF")

    def test_aucun_html_construit(self):
        sans = tj.sans_commentaires(self.source)
        for procede in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "DOMParser"):
            with self.subTest(procede=procede):
                self.assertNotIn(procede, sans, "aucun HTML construit par concatenation : %s" % procede)
        self.assertIn("createElement", sans)
        self.assertTrue("textContent" in sans or "createTextNode" in sans)

    def test_la_vue_expose_les_quatre_methodes_du_contrat(self):
        self.assertIn("txVueChoisir", self.source, "la coque lit la globale txVueChoisir")
        for nom in ("init", "rafraichir", "activer", "desactiver"):
            with self.subTest(methode=nom):
                self.assertRegex(self.source, r"(?m)^\s*%s\(" % nom)

    def test_l_arbre_est_en_mode_choisir(self):
        sans = tj.sans_commentaires(self.source)
        self.assertIn("txArbreCreer", sans, "la vue tient l'arbre du composant (contrat 5.3)")
        self.assertRegex(sans, r'mode:\s*"choisir"', "l'arbre est en mode « choisir »")
        self.assertIn("onSelection", sans)

    def test_l_api_n_est_appelee_que_par_la_vue(self):
        sans = tj.sans_commentaires(self.source)
        self.assertIn("api().ocr_traiter", sans, "« Traiter la sélection » appelle ocr_traiter")
        self.assertIn("txErreur(", sans, "une erreur de l'API se dit en toast (contrat 5.2)")

    def test_le_dialogue_est_cree_par_la_vue(self):
        sans = tj.sans_commentaires(self.source)
        self.assertIn("d-tx-confirmer", sans)
        self.assertIn("createElement(\"dialog\")", sans)
        self.assertNotIn("d-tx-confirmer", self.page,
                         "le dialogue est cree dans le conteneur de la vue, pas dans index.html")

    def test_le_resume_vient_des_phrases_du_contrat(self):
        for cle in ("choix_resume", "choix_resume_sans_pages", "traiter_selection"):
            with self.subTest(cle=cle):
                self.assertIn(cle, self.source, "phrase du contrat 5.5 : %s" % cle)

    def test_aucun_tiret_long(self):
        for tiret in (chr(0x2013), chr(0x2014)):
            with self.subTest(tiret=hex(ord(tiret))):
                self.assertNotIn(tiret, self.source)
                self.assertNotIn(tiret, self.feuille)

    def test_feuille_de_style(self):
        self.assertGreater(len(self.feuille), 200, "textes-choisir.css est vide ou presque")
        for selecteur in (".tx-choix-barre", ".tx-choix-resume", ".tx-choix-lancer",
                          ".tx-choix-arbre", "#d-tx-confirmer", ".tx-confirme-nombres"):
            with self.subTest(selecteur=selecteur):
                self.assertIn(selecteur, self.feuille, "selecteur absent de textes-choisir.css : %s" % selecteur)
        self.assertIn("var(--", self.feuille, "les couleurs viennent des jetons de style.css")
        self.assertFalse(re.search(r"#[0-9a-fA-F]{3,8}\b", self.feuille), "aucune couleur en dur")


@unittest.skipUnless(shutil.which("node"), "node absent : parcours sur DOM factice non execute")
class VueParcours(unittest.TestCase):
    """La vue sur la vraie page, avec la vraie coque et le vrai composant, contre une fausse API."""

    @classmethod
    def setUpClass(cls):
        node = shutil.which("node") or "node"
        coupe = tj.ENTETE.find("/* ---- arbre de la page")
        assert coupe > 0, "marqueur de l'arbre de la page introuvable"
        dossier = tempfile.mkdtemp(prefix="parcours-choisir-")
        script = os.path.join(dossier, "_parcours_choisir.js")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(tj.ENTETE[:coupe] + "\n" + tj.PAGE + "\n" + tj.PRELUDE + "\n")
                f.write("const ARBRE_FIXTURE = %s;\n" % json.dumps(charger("arbre.json"), ensure_ascii=False))
                f.write("const ETAT_FIXTURE = %s;\n" % json.dumps(charger("etat.json"), ensure_ascii=False))
                f.write("const CONFIRMATION = %s;\n"
                        % json.dumps(charger("traiter_confirmation.json"), ensure_ascii=False))
                for nom in ("commun.js", "textes-arbre.js", "textes-choisir.js", "textes.js"):
                    f.write("\n/* ===== %s ===== */\n" % nom)
                    f.write(lire(nom).replace("\r\n", "\n"))
                f.write("\n" + PARCOURS)
            r = subprocess.run([node, script, INTERFACE], capture_output=True, text=True, timeout=180)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        cls.resultat = r

    def test_parcours(self):
        self.assertEqual(self.resultat.returncode, 0,
                         "le parcours a echoue :\n%s\n%s" % (self.resultat.stdout, self.resultat.stderr))
        self.assertIn("OK", self.resultat.stdout)


PARCOURS = r"""
(async () => {
  const exiger = (cond, message) => { if (!cond) throw new assert.AssertionError({ message: message }); };
  const $h = s => document.querySelector(s);
  const plat = t => String(t).replace(/\s+/g, " ").trim();
  const texte = el => (el ? plat(el.textContent) : "");
  const attendre = (ms) => new Promise(r => setTimeout(r, ms === undefined ? 20 : ms));
  const clic = async el => { exiger(el, "element a cliquer introuvable"); el.dispatchEvent({ type: "click" }); await attendre(); };
  const copie = o => JSON.parse(JSON.stringify(o));
  const toasts = () => $h("#toasts").children.map(t => {
    const m = String(t.innerHTML).match(/<span>([\s\S]*)<\/span>/); return m ? Hdecode(m[1]) : ""; });

  const APPELS = [];
  let ETAT = copie(ETAT_FIXTURE), ARBRE = copie(ARBRE_FIXTURE), REPONSES = [];
  const API = {
    ocr_etat: async () => { APPELS.push({ nom: "ocr_etat" }); return copie(ETAT); },
    ocr_arbre: async () => { APPELS.push({ nom: "ocr_arbre" }); return copie(ARBRE); },
    ocr_traiter: async (...args) => {
      APPELS.push({ nom: "ocr_traiter", args: args });
      const r = REPONSES.length ? REPONSES.shift() : null;
      return r ? copie(r) : null;
    },
    ocr_installer: async () => null,
  };
  window.pywebview = { api: API };
  const appels = nom => APPELS.filter(a => a.nom === nom);

  const zone = $h("#tx-v-choisir");
  exiger(zone, "le conteneur #tx-v-choisir de la page est introuvable");
  const noeud = chemin => Array.from(zone.querySelectorAll("[role=treeitem]"))
    .filter(li => li.getAttribute("data-chemin") === chemin)[0] || null;
  const caseDe = chemin => noeud(chemin).querySelector(".tx-case");
  const bouton = action => zone.querySelector('[data-action="' + action + '"]');
  const lancer = () => bouton("traiter");
  const resume = () => texte(zone.querySelector(".tx-choix-resume"));
  const dialogue = () => $h("#tx-v-choisir #d-tx-confirmer");
  const cases = () => Array.from(zone.querySelectorAll(".tx-case"));
  const cochees = () => cases().filter(b => b.checked).length;

  /* ---- 1. montage : la vue remplit son conteneur, le dialogue y est cree ---- */
  exiger(zone.querySelector(".tx-choix-barre"), "la barre de choix est montee dans le conteneur");
  exiger(zone.querySelector(".tx-choix-arbre"), "la zone d'arbre est montee");
  exiger(dialogue(), "le dialogue de confirmation est cree par la vue, dans son conteneur");
  assert.strictEqual(dialogue().tagName.toLowerCase(), "dialog");
  assert.strictEqual(dialogue().id, "d-tx-confirmer");
  assert.strictEqual(texte(bouton("tout-cocher")), "Tout cocher");
  assert.strictEqual(texte(bouton("tout-decocher")), "Tout décocher");
  assert.strictEqual(texte(lancer()), "Traiter la sélection", "phrase du contrat 5.5");
  exiger(lancer().disabled, "sans selection, le bouton est desactive");
  assert.strictEqual(resume(), "", "aucun resume sans selection");
  exiger(!zone.querySelector(".tx-arbre"), "l'arbre n'est charge qu'a la premiere lecture");

  /* ---- 2. premiere lecture : l'arbre du contrat 5.3, en mode « choisir » ---- */
  txMontrerVue("choisir");
  await txRafraichir();
  exiger(zone.querySelector(".tx-arbre"), "l'arbre est monte apres la lecture");
  assert.strictEqual(zone.querySelectorAll("[role=treeitem]").length, 10, "les dix noeuds de la fixture");
  assert.strictEqual(cases().length, 10, "une case par noeud");
  assert.strictEqual(zone.querySelectorAll(".tx-menu").length, 0, "aucun menu en mode « choisir »");
  exiger(caseDe("Histoire contemporaine/Semaine 3/Studer 1996.pdf").disabled,
    "un document traite n'est pas cochable");
  assert.strictEqual(resume(), "");
  exiger(lancer().disabled, "toujours aucune selection");

  /* ---- 3. « Tout cocher » et « Tout décocher » : les dossiers entiers comptent pour eux seuls ---- */
  await clic(bouton("tout-cocher"));
  assert.deepStrictEqual(txVueChoisir.selection(), ["Histoire contemporaine", "Droit constitutionnel"],
    "tous les fichiers cochables sont coches, leurs dossiers entiers les remplacent");
  assert.strictEqual(resume(), "3 documents choisis",
    "le resume compte les seuls fichiers cochables, et une page inconnue l'empeche de donner un total");
  exiger(!lancer().disabled, "une selection rend le bouton actif");
  await clic(bouton("tout-decocher"));
  assert.deepStrictEqual(txVueChoisir.selection(), []);
  assert.strictEqual(resume(), "");
  assert.strictEqual(cochees(), 0, "plus aucune case cochee");
  exiger(lancer().disabled, "sans selection, le bouton est de nouveau desactive");

  /* ---- 4. un dossier entier est envoye comme le dossier seul ---- */
  await clic(caseDe("Histoire contemporaine/Semaine 3"));
  assert.deepStrictEqual(txVueChoisir.selection(), ["Histoire contemporaine/Semaine 3"],
    "la selection rend le dossier, pas ses trois fichiers");
  assert.strictEqual(resume(), "1 document choisi, environ 18 pages",
    "choix_resume : seul le fichier non traite du dossier compte, avec ses pages");
  exiger(!lancer().disabled);

  /* ---- 5. « Traiter la sélection » : premier appel sans confirme, puis le dialogue ---- */
  const avant = appels("ocr_traiter").length;
  REPONSES = [CONFIRMATION];
  await clic(lancer());
  let traites = appels("ocr_traiter");
  assert.strictEqual(traites.length, avant + 1, "un seul appel avant confirmation");
  assert.deepStrictEqual(traites[0].args, [["Histoire contemporaine/Semaine 3"]],
    "l'API recoit la selection seule, sans confirme");
  exiger(dialogue().open, "le dialogue de confirmation est ouvert");
  assert.strictEqual(texte(dialogue().querySelector(".tx-confirme-phrase")), plat(CONFIRMATION.confirmer),
    "la phrase de confirmation est celle que Python a rendue");
  assert.strictEqual(texte(dialogue().querySelector(".tx-confirme-documents")), "2 documents");
  assert.strictEqual(texte(dialogue().querySelector(".tx-confirme-pages")), "31 pages");
  assert.strictEqual(texte(dialogue().querySelector(".tx-confirme-minutes")), "Environ 1 à 3 minutes.");
  assert.strictEqual(texte(dialogue().querySelector(".tx-confirme-remplacements")), "2 PDF remplacés");
  assert.strictEqual(texte(dialogue().querySelector(".tx-confirme-titre")), "Traiter la sélection");

  /* ---- 6. la validation rappelle avec confirme, et gele la selection ---- */
  const FILE = { etat: "en_cours", origine: "coffre", document: "Histoire contemporaine/Semaine 3/Annexe 1.pdf",
                 page: 2, pages: 18, documents_faits: 0, documents_total: 3, reprise: 0 };
  REPONSES = [{ file: FILE }];
  await clic(bouton("confirmer"));
  traites = appels("ocr_traiter");
  assert.strictEqual(traites.length, avant + 2, "la validation rappelle l'API une fois");
  assert.deepStrictEqual(traites[1].args, [["Histoire contemporaine/Semaine 3"], false, true],
    "le second appel porte confirme=True");
  exiger(!dialogue().open, "le dialogue se referme");
  exiger(lancer().disabled, "pendant un traitement, le bouton est desactive");
  exiger(bouton("tout-cocher").disabled && bouton("tout-decocher").disabled,
    "les cases de tout cocher et tout decocher sont gelees");
  exiger(cases().every(b => b.disabled), "toutes les cases sont gelees");
  exiger(zone.classList.contains("tx-gele"), "la vue porte son etat gele");
  const resumeGele = resume();
  await clic(caseDe("Droit constitutionnel/Plan du cours.pdf"));
  assert.strictEqual(resume(), resumeGele, "une case cliquee pendant le gel ne change pas la selection");
  const pendant = appels("ocr_traiter").length;
  await clic(lancer());
  assert.strictEqual(appels("ocr_traiter").length, pendant, "aucun nouvel appel pendant le gel");

  /* ---- 7. la fin du traitement vide la selection et rafraichit la vue ---- */
  APPELS.length = 0;
  window.textesProgres({ etat: "terminee", document: "", page: 0, pages: 0,
                         documents_faits: 3, documents_total: 3 });
  await attendre(80);
  assert.deepStrictEqual(txVueChoisir.selection(), [], "la selection est videe a la fin");
  assert.strictEqual(resume(), "", "le resume est vide");
  assert.strictEqual(cochees(), 0, "plus aucune case cochee");
  exiger(lancer().disabled, "sans selection, le bouton est desactive");
  exiger(!zone.classList.contains("tx-gele"), "le gel est leve");
  exiger(!bouton("tout-cocher").disabled && !bouton("tout-decocher").disabled,
    "les cases de tout cocher et tout decocher sont de nouveau actives");
  exiger(!caseDe("Histoire contemporaine/Semaine 3/Annexe 1.pdf").disabled,
    "les cases cochables sont de nouveau actives");
  assert.deepStrictEqual(appels("ocr_arbre").length > 0, true, "la coque relit l'arbre a la fin");

  /* ---- 8. selection repartie sur deux branches, chacune reduite a son chemin le plus haut ---- */
  await clic(caseDe("Histoire contemporaine/Semaine 4/Carte des alliances.pdf"));
  await clic(caseDe("Droit constitutionnel"));
  assert.deepStrictEqual(txVueChoisir.selection(),
    ["Histoire contemporaine/Semaine 4", "Droit constitutionnel"],
    "chaque branche entiere est rendue par son dossier, dans l'ordre de l'arbre");
  assert.strictEqual(resume(), "2 documents choisis",
    "deux fichiers cochables, et le total des pages reste inconnu ici");

  /* ---- 8bis. la selection a plusieurs chemins part entiere et dans l'ordre (E-V6-3) ---- */
  const avantMulti = appels("ocr_traiter").length;
  REPONSES = [CONFIRMATION];
  await clic(lancer());
  let multi = appels("ocr_traiter");
  assert.strictEqual(multi.length, avantMulti + 1, "un seul appel avant confirmation");
  assert.deepStrictEqual(multi[avantMulti].args,
    [["Histoire contemporaine/Semaine 4", "Droit constitutionnel"]],
    "la selection entiere part a l'API, dans l'ordre de l'arbre, dossier par dossier");
  REPONSES = [{ file: FILE }];
  await clic(bouton("confirmer"));
  multi = appels("ocr_traiter");
  assert.deepStrictEqual(multi[avantMulti + 1].args,
    [["Histoire contemporaine/Semaine 4", "Droit constitutionnel"], false, true],
    "le deuxieme appel garde la selection entiere et son ordre, avec confirme=True");
  /* la fin du traitement leve le gel, comme dans la vraie file */
  window.textesProgres({ etat: "terminee", document: "", page: 0, pages: 0,
                         documents_faits: 2, documents_total: 2 });
  await attendre(80);
  assert.deepStrictEqual(txVueChoisir.selection(), [], "la selection est videe a la fin");

  /* ---- 9. un dossier dont les pages sont inconnues : choix_resume_sans_pages ---- */
  await clic(bouton("tout-decocher"));
  await clic(caseDe("Droit constitutionnel"));
  assert.deepStrictEqual(txVueChoisir.selection(), ["Droit constitutionnel"]);
  assert.strictEqual(resume(), "1 document choisi",
    "accord au singulier et aucune page inventee");

  /* ---- 10. « rien » et « erreur » se disent en toast ---- */
  let t0 = toasts().length;
  REPONSES = [{ rien: true }];
  await clic(lancer());
  exiger(toasts().length === t0 + 1, "une reponse sans rien a faire se dit en toast");
  exiger(toasts()[t0].length > 0, "le toast porte une phrase");
  exiger(!dialogue().open, "aucun dialogue pour une selection sans rien a faire");
  t0 = toasts().length;
  REPONSES = [{ erreur: "Le moteur d'extraction n'est pas installé." }];
  await clic(lancer());
  assert.deepStrictEqual(toasts().slice(t0), ["Le moteur d'extraction n'est pas installé."],
    "l'erreur de l'API est montree telle quelle");
  exiger(!dialogue().open);

  /* ---- 11. moteur absent : le bouton devient « Installer le moteur » et renvoie a la carte ---- */
  ETAT = copie(ETAT_FIXTURE);
  ETAT.moteur = Object.assign({}, ETAT.moteur, { present: false });
  await txRafraichir();
  assert.strictEqual(texte(lancer()), "Installer le moteur");
  exiger(!lancer().disabled, "une selection garde le bouton actif");
  APPELS.length = 0;
  await clic(lancer());
  assert.strictEqual(appels("ocr_traiter").length, 0,
    "sans moteur, le bouton n'appelle pas l'API");
  const installer = $h('#tx-moteur [data-action="installer"]');
  exiger(installer && Hactif === installer, "le bouton renvoie a la carte du moteur");
  await clic(bouton("tout-decocher"));
  assert.deepStrictEqual(txVueChoisir.selection(), [], "plus rien de coche");
  exiger(!lancer().disabled, "sans selection et sans moteur, « Installer le moteur » reste actif (E-V6-4)");
  APPELS.length = 0;
  await clic(lancer());
  assert.strictEqual(appels("ocr_traiter").length, 0,
    "sans selection et sans moteur, le bouton n'appelle pas l'API");
  exiger(Hactif === installer, "sans selection, le bouton renvoie encore a la carte du moteur");

  /* ---- 12. le dialogue ne survit pas a la sortie de la vue ---- */
  txVueChoisir.desactiver();
  assert.strictEqual(txVueChoisir.activer(), undefined, "activer ne leve pas");
  txVueChoisir.rafraichir(TX);
  assert.strictEqual(texte(lancer()) === "Installer le moteur" || texte(lancer()) === "Traiter la sélection", true);

  console.log("OK");
  process.exit(0);
})().catch(e => { console.error(e && e.stack ? e.stack : e); process.exit(1); });
"""


if __name__ == "__main__":
    unittest.main()
