"""Tests du composant d'arborescence de « Mes textes » (tache R7, contrat 5.3).

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque, et le parcours (Node, s'ignore sans `node`) range la vraie page d'index.html dans le DOM
factice de tests/test_textes_js.py avant de monter le composant dans son vrai conteneur
(`#tx-v-cours`, `#tx-v-choisir`). Les evenements remontent jusqu'a `document` comme dans un
navigateur.

Le rendu vient de `docs/refonte-textes/fixtures/arbre.json`, la reponse d'exemple de `ocr_arbre`
(contrat 5.6). Le parcours verifie : le rendu, l'ouverture et la fermeture, la case a trois etats
d'un dossier, la selection rendue (un dossier entierement coche compte pour lui seul), les fichiers
non cochables du mode « choisir », le menu d'un fichier selon son statut, la navigation au clavier
du modele ARIA `tree`, et l'etat ouvert conserve par chemin entre deux `charger()`.

Deux tests statiques ferment les portes du contrat : le composant n'ecrit jamais de HTML par
concatenation (aucun `innerHTML`) et n'appelle jamais l'API (`api()`, `ocr_`, `pywebview`).

Ce que ces tests ne mesurent pas : aucun vrai navigateur (donc ni rendu, ni focus reel, ni lecture
d'ecran), aucun vrai clavier, Windows et macOS non executes.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import json, os, shutil, subprocess, sys, tempfile, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests import test_textes_js as tj

INTERFACE = tj.INTERFACE
FIXTURE = os.path.join(tj.DOCS, "fixtures", "arbre.json")


class ArbreStatique(unittest.TestCase):
    """textes-arbre.js : les deux regles du contrat 5.3, par grep."""

    @classmethod
    def setUpClass(cls):
        cls.source = tj.lire(os.path.join(INTERFACE, "textes-arbre.js"))

    def test_aucun_html_construit(self):
        sans = tj.sans_commentaires(self.source)
        for procede in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "DOMParser"):
            with self.subTest(procede=procede):
                self.assertNotIn(procede, sans, "aucun HTML construit par concatenation : %s" % procede)
        self.assertIn("createElement", sans)
        self.assertIn("createTextNode", sans)

    def test_jamais_d_appel_a_l_api(self):
        sans = tj.sans_commentaires(self.source)
        for motif in ("api()", "ocr_", "pywebview", "await "):
            with self.subTest(motif=motif):
                self.assertNotIn(motif, sans, "le composant emet des actions, il n'appelle pas l'API : %s" % motif)

    def test_les_cinq_methodes_du_contrat(self):
        for nom in ("charger", "selection", "vider", "ouvrirTout", "fermerTout"):
            with self.subTest(methode=nom):
                self.assertRegex(self.source, r"(?m)^\s{4}%s\(" % nom)

    def test_fichier_en_lf(self):
        with open(os.path.join(INTERFACE, "textes-arbre.js"), "rb") as f:
            self.assertNotIn(b"\r", f.read())
        with open(os.path.abspath(__file__), "rb") as f:
            self.assertNotIn(b"\r", f.read())


@unittest.skipUnless(shutil.which("node"), "node absent : parcours sur DOM factice non execute")
class ArbreParcours(unittest.TestCase):
    """textes-arbre.js sur la vraie page : rendu, cases, selection, menu, clavier."""

    @classmethod
    def setUpClass(cls):
        node = shutil.which("node") or "node"
        coupe = tj.ENTETE.find("/* ---- arbre de la page")
        assert coupe > 0, "marqueur de l'arbre de la page introuvable"
        publique = json.loads(tj.lire(FIXTURE))
        dossier = tempfile.mkdtemp(prefix="parcours-arbre-")
        script = os.path.join(dossier, "_parcours_arbre.js")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(tj.ENTETE[:coupe] + "\n" + tj.PAGE + "\n" + PRELUDE + "\n")
                f.write("const ARBRE_FIXTURE = %s;\n" % json.dumps(publique, ensure_ascii=False))
                for nom in ("commun.js", "textes-arbre.js", "textes.js"):
                    f.write("\n/* ===== %s ===== */\n" % nom)
                    f.write(tj.lire(os.path.join(INTERFACE, nom)).replace("\r\n", "\n"))
                f.write("\n" + PARCOURS)
            r = subprocess.run([node, script, INTERFACE], capture_output=True, text=True, timeout=180)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        cls.resultat = r

    def test_parcours(self):
        self.assertEqual(self.resultat.returncode, 0,
                         "le parcours a echoue :\n%s\n%s" % (self.resultat.stdout, self.resultat.stderr))
        self.assertIn("OK", self.resultat.stdout)


PRELUDE = r"""
const occupations = new Set();
function barreOccupee(o, texte, qui) { if (o) occupations.add(qui); else occupations.delete(qui); }
function Htouche(cible, key) {
  const ev = { type: "keydown", key: key, preventDefault() {}, stopPropagation() {} };
  ev.target = cible;
  cible.dispatchEvent(ev);
}
const Hclic = cible => { cible.dispatchEvent({ type: "click" }); };
"""

PARCOURS = r"""
(async () => {
  const exiger = (cond, message) => { if (!cond) throw new assert.AssertionError({ message: message }); };
  const $h = s => document.querySelector(s);
  const plat = t => String(t).replace(/\s+/g, " ").trim();
  const texte = el => plat(el.textContent);
  const items = conteneur => Array.from(conteneur.querySelectorAll("[role=treeitem]"));
  const parChemin = (conteneur, chemin) =>
    items(conteneur).filter(li => li.getAttribute("data-chemin") === chemin)[0] || null;
  const ligne = li => li.querySelector(".tx-ligne");
  const attendre = () => new Promise(r => setTimeout(r, 10));

  /* ---- 1. mode « voir » : rendu de la fixture dans le vrai conteneur de la page ---- */
  const zoneVoir = $h("#tx-v-cours");
  exiger(zoneVoir, "le conteneur #tx-v-cours de la page est introuvable");
  const actions = [], selections = [];
  const voir = txArbreCreer(zoneVoir, { mode: "voir", onAction: (a, n) => actions.push([a, n.chemin]) });
  voir.charger(ARBRE_FIXTURE);
  const arbre = $h("#tx-v-cours .tx-arbre");
  exiger(arbre, "l'arbre est monte dans son conteneur");
  assert.strictEqual(arbre.getAttribute("role"), "tree");
  assert.strictEqual(plat(arbre.getAttribute("aria-label")), TX_MOTS.arbre_nom, "nom accessible du contrat 5.3");
  assert.strictEqual(items(arbre).length, 10, "dix noeuds : quatre dossiers, six fichiers");
  const histoire = parChemin(arbre, "Histoire contemporaine");
  const semaine3 = parChemin(arbre, "Histoire contemporaine/Semaine 3");
  const studer = parChemin(arbre, "Histoire contemporaine/Semaine 3/Studer 1996.pdf");
  exiger(histoire && semaine3 && studer, "les noeuds de la fixture sont rendus");
  assert.strictEqual(histoire.getAttribute("aria-level"), "1");
  assert.strictEqual(semaine3.getAttribute("aria-level"), "2");
  assert.strictEqual(studer.getAttribute("aria-level"), "3");
  exiger(histoire.classList.contains("tx-dossier") && studer.classList.contains("tx-fichier"), "classes du contrat");
  assert.strictEqual(histoire.getAttribute("aria-expanded"), "false", "replie au depart");
  exiger(histoire.querySelector("ul").hidden, "le groupe d'un dossier replie est masque");
  assert.strictEqual(texte(ligne(histoire).querySelector(".tx-resume")), "5 fichiers, 2 traités");
  assert.strictEqual(texte(ligne(semaine3).querySelector(".tx-resume")), "3 fichiers, 1 traité");
  assert.strictEqual(items(arbre).filter(li => li.tabIndex === 0).length, 1, "un seul treeitem dans l'ordre du clavier");
  assert.strictEqual(items(arbre)[0].tabIndex, 0, "c'est le premier");
  assert.strictEqual(arbre.querySelectorAll(".tx-case").length, 0, "aucune case en mode « voir »");

  /* badges et libelles de statut (contrat 2.3 et 5.5) */
  const badge = chemin => ligne(parChemin(arbre, chemin)).querySelector(".tx-badge");
  assert.strictEqual(texte(badge("Histoire contemporaine/Semaine 3/Studer 1996.pdf")), "Traité");
  assert.strictEqual(badge("Histoire contemporaine/Semaine 3/Studer 1996.pdf").getAttribute("data-statut"), "traite");
  assert.strictEqual(texte(badge("Histoire contemporaine/Semaine 3/Cours du 12 octobre.pdf")), "À vérifier");
  assert.strictEqual(texte(badge("Histoire contemporaine/Semaine 3/Annexe 1.pdf")), "Non traité");
  assert.strictEqual(texte(badge("Histoire contemporaine/Semaine 4/Carte des alliances.pdf")), "Non réussi");
  assert.strictEqual(texte(badge("Droit constitutionnel/Plan du cours.pdf")), "Non traité");

  /* ---- 2. ouvrir et fermer : bascule, clic sur la ligne, clavier ---- */
  Hclic(ligne(histoire).querySelector(".tx-bascule"));
  await attendre();
  assert.strictEqual(parChemin(arbre, "Histoire contemporaine").getAttribute("aria-expanded"), "true",
    "la bascule ouvre le dossier");
  exiger(!parChemin(arbre, "Histoire contemporaine").querySelector("ul").hidden, "le groupe s'affiche");
  Hclic(ligne(parChemin(arbre, "Histoire contemporaine")).querySelector(".tx-bascule"));
  await attendre();
  assert.strictEqual(parChemin(arbre, "Histoire contemporaine").getAttribute("aria-expanded"), "false",
    "un second clic referme");
  Hclic(ligne(parChemin(arbre, "Histoire contemporaine")).querySelector(".tx-nom"));
  await attendre();
  assert.strictEqual(parChemin(arbre, "Histoire contemporaine").getAttribute("aria-expanded"), "true",
    "un clic sur le nom du dossier l'ouvre aussi");

  /* fleche droite : ouvre, puis descend ; fleche gauche : ferme, puis remonte */
  let courant = parChemin(arbre, "Histoire contemporaine");
  Htouche(courant, "ArrowRight");
  await attendre();
  /* le dossier etait ouvert : la fleche droite descend au premier enfant */
  exiger(Hactif === parChemin(arbre, "Histoire contemporaine/Semaine 3"), "fleche droite descend au premier enfant");
  Htouche(Hactif, "ArrowRight");
  await attendre();
  assert.strictEqual(parChemin(arbre, "Histoire contemporaine/Semaine 3").getAttribute("aria-expanded"), "true",
    "fleche droite ouvre le dossier ferme");
  Htouche(parChemin(arbre, "Histoire contemporaine/Semaine 3"), "ArrowRight");
  await attendre();
  exiger(Hactif === parChemin(arbre, "Histoire contemporaine/Semaine 3/Studer 1996.pdf"),
    "fleche droite sur un dossier ouvert va au premier fichier");
  Htouche(Hactif, "ArrowLeft");
  await attendre();
  exiger(Hactif === parChemin(arbre, "Histoire contemporaine/Semaine 3"), "fleche gauche remonte au parent");
  Htouche(Hactif, "ArrowLeft");
  await attendre();
  assert.strictEqual(parChemin(arbre, "Histoire contemporaine/Semaine 3").getAttribute("aria-expanded"), "false",
    "fleche gauche sur un dossier ouvert le ferme");

  /* haut, bas, debut, fin */
  const visibles = () => {
    const sortie = [];
    const parcourir = ul => {
      for (const li of ul.children) {
        if (!li.classList || !li.classList.contains("tx-noeud")) continue;
        sortie.push(li);
        if (li.getAttribute("aria-expanded") !== "true") continue;
        for (const groupe of li.children) {
          if (groupe.tagName && String(groupe.tagName).toLowerCase() === "ul") parcourir(groupe);
        }
      }
    };
    parcourir(arbre);
    return sortie;
  };
  Htouche(parChemin(arbre, "Histoire contemporaine"), "End");
  await attendre();
  exiger(Hactif === visibles()[visibles().length - 1], "Fin va au dernier noeud visible");
  Htouche(Hactif, "Home");
  await attendre();
  exiger(Hactif === parChemin(arbre, "Histoire contemporaine"), "Debut va au premier noeud");
  Htouche(Hactif, "ArrowDown");
  await attendre();
  exiger(Hactif === parChemin(arbre, "Histoire contemporaine/Semaine 3"), "fleche bas va au suivant visible");
  Htouche(Hactif, "ArrowUp");
  await attendre();
  exiger(Hactif === parChemin(arbre, "Histoire contemporaine"), "fleche haut revient");
  assert.strictEqual(items(arbre).filter(li => li.tabIndex === 0).length, 1, "un seul noeud dans l'ordre du clavier");

  /* ---- 3. menu d'un fichier selon son statut ---- */
  const menuDe = chemin => {
    const li = parChemin(arbre, chemin);
    Hclic(ligne(li).querySelector(".tx-menu"));
    return li.querySelector(".tx-menu-liste");
  };
  let menu = menuDe("Histoire contemporaine/Semaine 3/Studer 1996.pdf");
  exiger(menu, "le menu s'ouvre");
  assert.strictEqual(menu.getAttribute("role"), "menu");
  assert.deepStrictEqual(Array.from(menu.querySelectorAll("[role=menuitem]")).map(texte),
    ["Ouvrir le PDF", "Afficher dans l'explorateur", "Copier le texte", "Restaurer l'original"],
    "un document traite et remplace : ouvrir, afficher, copier, restaurer");
  const premier = menu.querySelector("[role=menuitem]");
  exiger(Hactif === premier, "le focus va au premier item du menu");
  Hclic(premier);
  await attendre();
  assert.deepStrictEqual(actions, [["ouvrir", "Histoire contemporaine/Semaine 3/Studer 1996.pdf"]],
    "le menu emet l'action avec le noeud");
  exiger(!parChemin(arbre, "Histoire contemporaine/Semaine 3/Studer 1996.pdf").querySelector(".tx-menu-liste"),
    "le menu se referme apres l'action");
  menu = menuDe("Histoire contemporaine/Semaine 4/Carte des alliances.pdf");
  assert.deepStrictEqual(Array.from(menu.querySelectorAll("[role=menuitem]")).map(texte),
    ["Ouvrir le PDF", "Afficher dans l'explorateur", "Réessayer"],
    "un echec : ni copie, ni restauration, mais Reessayer");
  Hclic(ligne(parChemin(arbre, "Histoire contemporaine/Semaine 4/Carte des alliances.pdf")).querySelector(".tx-menu"));
  await attendre();
  exiger(!parChemin(arbre, "Histoire contemporaine/Semaine 4/Carte des alliances.pdf").querySelector(".tx-menu-liste"),
    "un second clic sur le bouton referme le menu");
  menu = menuDe("Droit constitutionnel/Plan du cours.pdf");
  assert.deepStrictEqual(Array.from(menu.querySelectorAll("[role=menuitem]")).map(texte),
    ["Ouvrir le PDF", "Afficher dans l'explorateur"], "un document non traite : ni copie, ni restauration");
  assert.strictEqual(ligne(parChemin(arbre, "Droit constitutionnel/Plan du cours.pdf")).querySelector(".tx-menu")
    .getAttribute("aria-haspopup"), "menu");
  assert.strictEqual(ligne(parChemin(arbre, "Droit constitutionnel/Plan du cours.pdf")).querySelector(".tx-menu")
    .getAttribute("aria-label"), "Actions sur Plan du cours.pdf");
  /* Entree ouvre le menu d'un fichier (aucun menu ouvert a cet instant) */
  Hclic($h("#v-textes"));
  await attendre();
  Htouche(parChemin(arbre, "Droit constitutionnel/Plan du cours.pdf"), "Enter");
  await attendre();
  exiger(parChemin(arbre, "Droit constitutionnel/Plan du cours.pdf").querySelector(".tx-menu-liste"),
    "Entree ouvre le menu d'un fichier");

  /* Entree sur un element du menu : son action part, une seule fois (ecart E-V5-1) */
  const liPlan = parChemin(arbre, "Droit constitutionnel/Plan du cours.pdf");
  const itemMenu = liPlan.querySelector(".tx-menu-liste [role=menuitem]");
  exiger(itemMenu, "le menu porte des elements menuitem");
  exiger(Hactif === itemMenu, "le focus est alle au premier element du menu");
  assert.strictEqual(texte(itemMenu), "Ouvrir le PDF");
  const avantMenu = actions.length;
  let empeche = false;
  const toucheMenu = { type: "keydown", key: "Enter", target: itemMenu, stopPropagation() {},
                       preventDefault() { empeche = true; } };
  itemMenu.dispatchEvent(toucheMenu);
  await attendre();
  assert.deepStrictEqual(actions.slice(avantMenu),
    [["ouvrir", "Droit constitutionnel/Plan du cours.pdf"]],
    "Entree sur « Ouvrir le PDF » emet l'action du menu");
  exiger(empeche, "la touche est consommee : le clic natif du bouton ne doublera pas l'action");
  exiger(!parChemin(arbre, "Droit constitutionnel/Plan du cours.pdf").querySelector(".tx-menu-liste"),
    "le menu se referme apres l'action");
  assert.strictEqual(actions.length, avantMenu + 1, "une seule action pour une seule touche");

  Hclic($h("#v-textes"));
  await attendre();
  exiger(!parChemin(arbre, "Droit constitutionnel/Plan du cours.pdf").querySelector(".tx-menu-liste"),
    "un clic ailleurs ferme le menu");

  /* ---- 4. etat ouvert conserve par chemin entre deux charger() ---- */
  voir.fermerTout();
  Hclic(ligne(parChemin(arbre, "Histoire contemporaine")).querySelector(".tx-bascule"));
  await attendre();
  assert.strictEqual(parChemin(arbre, "Histoire contemporaine").getAttribute("aria-expanded"), "true");
  voir.charger(ARBRE_FIXTURE);
  assert.strictEqual(parChemin(arbre, "Histoire contemporaine").getAttribute("aria-expanded"), "true",
    "un nouveau charger() retrouve la branche ouverte");
  assert.strictEqual(texte(ligne(parChemin(arbre, "Histoire contemporaine")).querySelector(".tx-resume")),
    "5 fichiers, 2 traités", "le resume survit au rechargement");
  voir.fermerTout();
  assert.strictEqual(parChemin(arbre, "Histoire contemporaine").getAttribute("aria-expanded"), "false",
    "fermerTout referme tout");
  voir.ouvrirTout();
  assert.deepStrictEqual(items(arbre).filter(li => li.getAttribute("aria-expanded") === "false").length, 0,
    "ouvrirTout ouvre tous les dossiers");
  voir.vider();
  exiger(!$h("#tx-v-cours .tx-arbre"), "vider retire l'arbre du conteneur");

  /* ---- 5. mode « choisir » : cases, tri-etat, selection rendue ---- */
  const zoneChoisir = $h("#tx-v-choisir");
  exiger(zoneChoisir, "le conteneur #tx-v-choisir de la page est introuvable");
  let dernier = null;
  const choisir = txArbreCreer(zoneChoisir, {
    mode: "choisir",
    onSelection: (chemins, resume) => { selections.push(chemins.slice()); dernier = resume; },
  });
  choisir.charger(ARBRE_FIXTURE);
  const arbreChoisir = $h("#tx-v-choisir .tx-arbre");
  const noeud = chemin => parChemin(arbreChoisir, chemin);
  const caseDe = chemin => ligne(noeud(chemin)).querySelector(".tx-case");
  assert.strictEqual(arbreChoisir.querySelectorAll(".tx-case").length, 10, "une case par noeud en mode « choisir »");
  assert.strictEqual(arbreChoisir.querySelectorAll(".tx-menu").length, 0, "aucun menu en mode « choisir »");
  exiger(caseDe("Histoire contemporaine/Semaine 3/Studer 1996.pdf").disabled, "un document traite n'est pas cochable");
  assert.strictEqual(caseDe("Histoire contemporaine/Semaine 3/Studer 1996.pdf").getAttribute("aria-disabled"), "true");
  exiger(noeud("Histoire contemporaine/Semaine 3/Studer 1996.pdf").classList.contains("tx-indisponible"),
    "le fichier non cochable est grise");
  assert.strictEqual(texte(ligne(noeud("Histoire contemporaine/Semaine 3/Studer 1996.pdf")).querySelector(".tx-badge")),
    "Traité", "le badge reste lisible");
  exiger(caseDe("Histoire contemporaine/Semaine 3/Cours du 12 octobre.pdf").disabled, "« À vérifier » n'est pas cochable");
  exiger(!caseDe("Histoire contemporaine/Semaine 3/Annexe 1.pdf").disabled, "« Non traité » est cochable");
  exiger(!caseDe("Histoire contemporaine/Semaine 4/Carte des alliances.pdf").disabled, "« Non réussi » est cochable");
  exiger(!caseDe("Histoire contemporaine").disabled, "la case d'un dossier n'est jamais desactivee");
  exiger(!caseDe("Droit constitutionnel").disabled, "Droit constitutionnel a un fichier cochable");
  assert.strictEqual(selections.length, 1, "charger annonce la selection (vide) une fois");
  assert.deepStrictEqual(selections[0], []);

  /* cocher le seul fichier cochable de « Semaine 3 » : ce dossier est alors entierement coche,
     et « Histoire contemporaine », qui garde un autre fichier cochable, devient mixte */
  Hclic(caseDe("Histoire contemporaine/Semaine 3/Annexe 1.pdf"));
  await attendre();
  assert.deepStrictEqual(choisir.selection(), ["Histoire contemporaine/Semaine 3"],
    "un dossier entierement coche compte pour lui seul");
  assert.deepStrictEqual(selections[selections.length - 1], ["Histoire contemporaine/Semaine 3"]);
  assert.strictEqual(caseDe("Histoire contemporaine/Semaine 3").getAttribute("aria-checked"), "true");
  assert.strictEqual(caseDe("Histoire contemporaine").indeterminate, true, "case de dossier mixte");
  assert.strictEqual(caseDe("Histoire contemporaine").getAttribute("aria-checked"), "mixed");
  exiger(caseDe("Histoire contemporaine").checked === false, "une case mixte n'est pas cochee");
  assert.deepStrictEqual(dernier, { documents: 1, pages: 18, pages_connues: true },
    "le resume ne compte que ce qui reste cochable dans le dossier : " + JSON.stringify(dernier));

  /* cocher le second dossier cochable rend le cours entierement coche */
  Hclic(caseDe("Histoire contemporaine/Semaine 4"));
  await attendre();
  assert.deepStrictEqual(choisir.selection(), ["Histoire contemporaine"],
    "le cours entierement coche remplace ses dossiers et ses fichiers");
  assert.strictEqual(caseDe("Histoire contemporaine").checked, true);
  assert.strictEqual(caseDe("Histoire contemporaine").indeterminate, false);
  assert.strictEqual(caseDe("Histoire contemporaine").getAttribute("aria-checked"), "true");
  assert.deepStrictEqual(dernier, { documents: 2, pages: 31, pages_connues: true },
    "le cours compte ses deux fichiers cochables, pas les trois deja traites ou a verifier");

  /* la case d'un dossier coche decoche ; les fichiers non cochables restent hors selection */
  Hclic(caseDe("Histoire contemporaine"));
  await attendre();
  assert.deepStrictEqual(choisir.selection(), [], "un second clic decoche tout le dossier");
  assert.strictEqual(caseDe("Histoire contemporaine").getAttribute("aria-checked"), "false");
  assert.strictEqual(caseDe("Histoire contemporaine/Semaine 3/Annexe 1.pdf").checked, false);

  /* cocher un dossier puis le decocher par sa case */
  Hclic(caseDe("Histoire contemporaine/Semaine 3"));
  await attendre();
  assert.deepStrictEqual(choisir.selection(), ["Histoire contemporaine/Semaine 3"], "la case du dossier coche");
  assert.strictEqual(caseDe("Histoire contemporaine").getAttribute("aria-checked"), "mixed");
  Hclic(caseDe("Histoire contemporaine/Semaine 3"));
  await attendre();
  assert.deepStrictEqual(choisir.selection(), [], "la meme case decoche le dossier");
  assert.strictEqual(caseDe("Histoire contemporaine").getAttribute("aria-checked"), "false");

  /* pages inconnues : le resume le dit (pages null) */
  Hclic(caseDe("Droit constitutionnel/Plan du cours.pdf"));
  await attendre();
  assert.deepStrictEqual(choisir.selection(), ["Droit constitutionnel"]);
  assert.strictEqual(dernier.documents, 1);
  assert.strictEqual(dernier.pages, null, "pages inconnues : aucun nombre invente");
  assert.strictEqual(dernier.pages_connues, false);

  /* ---- 6. clavier du mode « choisir » : Espace coche ---- */
  const plan = noeud("Droit constitutionnel/Plan du cours.pdf");
  Htouche(plan, " ");
  await attendre();
  assert.deepStrictEqual(choisir.selection(), [], "Espace decoche le fichier focalise");
  Htouche(plan, " ");
  await attendre();
  assert.deepStrictEqual(choisir.selection(), ["Droit constitutionnel"], "Espace recoche");
  const traite = noeud("Histoire contemporaine/Semaine 3/Studer 1996.pdf");
  Htouche(traite, " ");
  await attendre();
  assert.deepStrictEqual(choisir.selection(), ["Droit constitutionnel"],
    "Espace sur un fichier non cochable ne change rien");
  /* un dossier se coche aussi au clavier */
  Htouche(noeud("Histoire contemporaine/Semaine 4"), " ");
  await attendre();
  assert.deepStrictEqual(choisir.selection(),
    ["Histoire contemporaine/Semaine 4", "Droit constitutionnel"]);
  /* flèches en mode « choisir » : le meme modele ARIA */
  Htouche(noeud("Droit constitutionnel/Plan du cours.pdf"), "Home");
  await attendre();
  exiger(Hactif === noeud("Histoire contemporaine"), "Debut en mode « choisir »");
  choisir.vider();

  /* ---- 7. les actions emises portent le noeud complet ---- */
  const recues = [];
  const zone = $h("#tx-v-deposer") || $h("#tx-v-cours");
  const relire = txArbreCreer(zone, { mode: "voir", onAction: (a, n) => recues.push([a, n]) });
  relire.charger(ARBRE_FIXTURE);
  const mineral = parChemin(zone, "Droit constitutionnel/Plan du cours.pdf");
  Hclic(ligne(mineral).querySelector(".tx-menu"));
  Hclic(mineral.querySelector(".tx-menu-liste").querySelectorAll("[role=menuitem]")[1]);
  await attendre();
  assert.strictEqual(recues.length, 1);
  assert.strictEqual(recues[0][0], "afficher");
  assert.strictEqual(recues[0][1].chemin, "Droit constitutionnel/Plan du cours.pdf");
  assert.strictEqual(recues[0][1].statut, "non_traite");
  assert.strictEqual(recues[0][1].pages, null, "le noeud garde sa forme de fixture");

  /* ---- 8. dossier sans rien de cochable, restauration d'un document remplace sans texte,
          selection qui survit a un rechargement (ecarts E-V5-3 b, c, d, e) ---- */
  const fic = (chemin, nom, statut, extra) => Object.assign({
    type: "fichier", nom: nom, chemin: chemin, extension: "pdf", octets: 1024, pages: 4,
    statut: statut, motif: "", texte: false, format: "", sortie: "",
    remplace: false, original_conserve: false, confiance: null, date: "" }, extra || {});
  const dos = (chemin, nom, enfants, compteurs) => ({
    type: "dossier", nom: nom, chemin: chemin, enfants: enfants,
    compteurs: compteurs || { fichiers: enfants.length, traites: 0, a_verifier: 0, echecs: 0,
                              non_traites: 0, pages_non_traitees: 0 } });
  const ARBRE_BIS = {
    racine: "C:/Moodle",
    cours: [
      dos("Cours fini", "Cours fini", [
        fic("Cours fini/Remplace.pdf", "Remplace.pdf", "traite",
            { remplace: true, original_conserve: true, confiance: 0.93, date: "2026-11-10T10:00:00" }),
        fic("Cours fini/Verifie.pdf", "Verifie.pdf", "a_verifier", { texte: true, format: "md", pages: 9 }),
      ]),
      dos("Cours mixte", "Cours mixte", [
        fic("Cours mixte/Neuf.pdf", "Neuf.pdf", "non_traite", { pages: 6 }),
        fic("Cours mixte/Ancien.pdf", "Ancien.pdf", "traite", { texte: true, format: "md", remplace: true }),
      ]),
      dos("Cours large", "Cours large", [
        fic("Cours large/Alpha.pdf", "Alpha.pdf", "non_traite", { pages: 5 }),
        fic("Cours large/Beta.pdf", "Beta.pdf", "non_traite", { pages: 7 }),
      ]),
    ],
    compteurs: { fichiers: 6, traites: 2, a_verifier: 1, echecs: 0, non_traites: 3, pages_non_traitees: 27 },
  };

  /* (d) : un document remplace sans texte offre « Restaurer l'original » */
  const recuesBis = [];
  const bis = txArbreCreer($h("#tx-v-cours"), { mode: "voir", onAction: (a, n) => recuesBis.push([a, n.chemin]) });
  bis.charger(ARBRE_BIS);
  const zoneBis = $h("#tx-v-cours");
  const menuBis = chemin => {
    Hclic(ligne(parChemin(zoneBis, chemin)).querySelector(".tx-menu"));
    return parChemin(zoneBis, chemin).querySelector(".tx-menu-liste");
  };
  assert.deepStrictEqual(Array.from(menuBis("Cours fini/Remplace.pdf").querySelectorAll("[role=menuitem]")).map(texte),
    ["Ouvrir le PDF", "Afficher dans l'explorateur", "Restaurer l'original"],
    "un document remplace sans texte : restaurer est propose, copier ne l'est pas");
  const libellesVerifie = Array.from(menuBis("Cours fini/Verifie.pdf").querySelectorAll("[role=menuitem]")).map(texte);
  exiger(libellesVerifie.indexOf("Copier le texte") >= 0, "un document qui a un texte offre la copie");
  exiger(libellesVerifie.indexOf("Restaurer l'original") < 0,
    "un PDF textuel traite n'a pas ete remplace : rien a restaurer (E-V7-3, O18)");
  bis.vider();

  /* (b), (c) et (e) en mode « choisir » */
  let dernierBis = null;
  const choisirBis = txArbreCreer($h("#tx-v-choisir"), {
    mode: "choisir", onSelection: (chemins, resume) => { dernierBis = resume; } });
  choisirBis.charger(ARBRE_BIS);
  const racineBis = $h("#tx-v-choisir .tx-arbre");
  const caseBis = chemin => ligne(parChemin(racineBis, chemin)).querySelector(".tx-case");
  exiger(caseBis("Cours fini").disabled, "un dossier sans rien de cochable a sa case desactivee");
  assert.strictEqual(caseBis("Cours fini").getAttribute("aria-disabled"), "true");
  exiger(!caseBis("Cours mixte").disabled, "un dossier qui garde un fichier cochable a sa case active");
  exiger(!caseBis("Cours large").disabled, "un dossier entierement cochable a sa case active");
  Hclic(caseBis("Cours mixte"));
  await attendre();
  assert.deepStrictEqual(choisirBis.selection(), ["Cours mixte"]);
  assert.deepStrictEqual(dernierBis, { documents: 1, pages: 6, pages_connues: true },
    "le dossier ne compte que son fichier non traite");

  /* (c) : la selection survit a un rechargement (fin de traitement, Actualiser) */
  choisirBis.charger(ARBRE_BIS);
  assert.deepStrictEqual(choisirBis.selection(), ["Cours mixte"],
    "un rechargement garde la selection des chemins qui existent encore");
  assert.strictEqual(caseBis("Cours mixte").getAttribute("aria-checked"), "true",
    "le rendu retrouve la case du dossier entierement coche");
  assert.strictEqual(caseBis("Cours mixte").checked, true);

  /* (e) : un dossier a moitie coche est mixte des le rendu initial, pas seulement apres un clic */
  Hclic(caseBis("Cours mixte"));
  await attendre();
  Hclic(caseBis("Cours large/Alpha.pdf"));
  await attendre();
  assert.deepStrictEqual(choisirBis.selection(), ["Cours large/Alpha.pdf"]);
  assert.strictEqual(caseBis("Cours large").getAttribute("aria-checked"), "mixed", "mixte apres le clic");
  choisirBis.charger(ARBRE_BIS);
  assert.strictEqual(caseBis("Cours large").indeterminate, true, "indeterminate au rendu initial");
  assert.strictEqual(caseBis("Cours large").getAttribute("aria-checked"), "mixed",
    "aria-checked mixed au rendu initial, pas true");
  assert.deepStrictEqual(choisirBis.selection(), ["Cours large/Alpha.pdf"], "le fichier coche reste la selection");
  choisirBis.vider();

  console.log("OK");
  process.exit(0);
})().catch(e => { console.error(e && e.stack ? e.stack : e); process.exit(1); });
"""


if __name__ == "__main__":
    unittest.main()
