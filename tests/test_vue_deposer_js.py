"""Tests de la vue « Déposer des fichiers » de « Mes textes » (tache R10, contrat 5.4).

Aucune fenetre, aucun navigateur, aucune dependance reseau : les fichiers de l'interface sont lus
sur le disque, et le parcours (Node, s'ignore sans `node`) range la vraie page d'index.html dans le
DOM factice de tests/test_textes_js.py avant de charger commun.js, textes-deposer.js puis textes.js,
dans l'ordre de la page. Les evenements remontent jusqu'a `document` comme dans un navigateur.

Le parcours verifie, sur la reponse d'exemple de `fixtures/depot.json` (contrat 5.6) :
l'evenement `tx:depot` et le selecteur alimentent la meme liste ; les refus sont listes avec leur
phrase ; les deux temps de `ocr_deposer` (aucun `confirme` avant le dialogue, `true` apres) ; le
dossier par defaut puis change ; les trois sortes de resultats (succes avec « Afficher dans
l'explorateur », echec avec son motif et `deposer_intact`, refuse avec sa phrase) ; le clavier sur
la zone (Entree et Espace) ; un depot sans chemin (objet File du navigateur) ignore avec un toast ;
et l'absence de chemin absolu dans la liste et les resultats, le dossier de depot excepte.

Ce que ces tests ne mesurent pas : aucun vrai navigateur (ni rendu, ni focus reel, ni lecture
d'ecran), aucun vrai clavier, aucun vrai glisser-deposer de pywebview (O16, ni Windows ni macOS),
aucune vraie boite de dialogue native.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import json, os, re, shutil, subprocess, sys, tempfile, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests import test_textes_js as tj

INTERFACE = tj.INTERFACE
FIXTURE = os.path.join(tj.DOCS, "fixtures", "depot.json")
FIXTURE_ETAT = os.path.join(tj.DOCS, "fixtures", "etat.json")
JS = os.path.join(INTERFACE, "textes-deposer.js")
CSS = os.path.join(INTERFACE, "textes-deposer.css")


class DeposerStatique(unittest.TestCase):
    """textes-deposer.js et sa feuille : les regles de forme et les portes du contrat 5.4."""

    @classmethod
    def setUpClass(cls):
        cls.source = tj.lire(JS)
        cls.css = tj.lire(CSS)
        cls.page = tj.lire(os.path.join(INTERFACE, "index.html"))

    def test_fichier_ecrit_et_en_lf(self):
        self.assertGreater(len(self.source), 2000, "textes-deposer.js est vide ou presque")
        self.assertGreater(len(self.css), 200, "textes-deposer.css est vide ou presque")
        for chemin in (JS, CSS, os.path.abspath(__file__)):
            with self.subTest(fichier=os.path.basename(chemin)):
                with open(chemin, "rb") as f:
                    self.assertNotIn(b"\r", f.read(), "fichier en LF")

    def test_aucun_cadratin(self):
        for texte in (self.source, self.css, tj.lire(os.path.abspath(__file__))):
            with self.subTest(fichier="R10"):
                self.assertEqual(texte.count(chr(0x2014)), 0, "aucun tiret cadratin")
                self.assertEqual(texte.count(chr(0x2013)), 0, "aucun tiret demi-cadratin")

    def test_aucun_html_construit(self):
        sans = tj.sans_commentaires(self.source)
        for procede in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "DOMParser"):
            with self.subTest(procede=procede):
                self.assertNotIn(procede, sans, "aucun HTML construit par concatenation : %s" % procede)
        self.assertIn("createElement", sans)
        self.assertIn("createTextNode", sans)
        self.assertNotIn("cssText", sans, "les styles restent dans textes-deposer.css")

    def test_globales_et_methodes_du_contrat(self):
        self.assertRegex(self.source, r"(?m)^const txVueDeposer = \{")
        for methode in ("init", "rafraichir", "activer", "desactiver"):
            with self.subTest(methode=methode):
                self.assertRegex(self.source, r"(?m)^\s{2}%s\(" % methode)

    def test_appelle_seulement_les_methodes_du_contrat(self):
        sans = tj.sans_commentaires(self.source)
        permises = {"ocr_choisir_fichiers", "ocr_choisir_dossier_depot", "ocr_deposer", "ocr_afficher"}
        vues = set(re.findall(r"\bocr_[a-z_]+", sans))
        self.assertTrue(vues, "la vue appelle l'API")
        self.assertEqual(vues - permises, set(), "methodes hors du contrat 4.6 et 5.4")

    def test_styles_dans_sa_seule_feuille(self):
        # Les commentaires sont retires d'abord : sans cela, un selecteur precede d'un commentaire
        # sort du controle (mutation « .depot-zone », mesuree au journal).
        for selecteur in re.findall(r"([^{}]+)\{", tj.sans_commentaires(self.css)):
            propre = selecteur.strip()
            if not propre or propre.startswith("@"):
                continue
            for part in propre.split(","):
                with self.subTest(selecteur=part.strip()):
                    self.assertIn("tx-depot", part, "chaque regle ne vise que la vue du depot")
        self.assertIn("var(--", self.css, "les couleurs viennent des variables de style.css")

    def test_chargee_par_la_vraie_page(self):
        balises = re.findall(r'<script src="([^"]+)"></script>', self.page)
        self.assertIn("textes-deposer.js", balises)
        self.assertLess(balises.index("textes-deposer.js"), balises.index("textes.js"),
                        "la vue est chargee avant la coque")


# Le parcours : un script Node, les vraies sources, la vraie page, la fixture de depot.
PARCOURS = r"""
(async () => {
  const exiger = (cond, message) => { if (!cond) throw new assert.AssertionError({ message: message }); };
  const plat = t => String(t).replace(/\s+/g, " ").trim();
  const $h = s => document.querySelector(s);
  const clique = async el => { el.dispatchEvent({ type: "click" }); await Hattendre(40); };
  const copie = o => JSON.parse(JSON.stringify(o));
  const lesToasts = () => $h("#toasts").children.map(t => {
    const m = String(t.innerHTML).match(/<span>([\s\S]*)<\/span>/); return m ? Hdecode(m[1]) : ""; });
  const noms = el => el.children.map(li => {
    const premier = li.childNodes[0];
    return premier && premier.nodeType === 3 ? premier.textContent : ""; });
  const contenu = el => plat(el.textContent);
  const sansEntete = (el, ou) => { const t = contenu(el); exiger(t.indexOf("C:") < 0, "aucun chemin absolu dans " + ou + " : " + t); };

  const ETAT = Object.assign(copie(ETATPAGE), {});
  const ARBRE = { racine: "C:/Moodle", cours: [], compteurs: { fichiers: 0, traites: 0, a_verifier: 0,
                  echecs: 0, non_traites: 0, pages_non_traitees: 0 } };
  let HETAT = copie(ETAT);
  let FICHIERS = ["C:/Users/max/Desktop/b.pdf", "C:/Users/max/Desktop/c.pdf"];
  let DEPOT_REPONSE = null;   // resultats d'un depot, quand le test en veut d'autres que la fixture
  const DOSSIER = "C:/Users/max/Desktop/Depot choisi";
  const appels = [];
  const DERNIER = () => appels[appels.length - 1] || [];

  const API = {
    ocr_etat: async () => { appels.push(["ocr_etat"]); return copie(HETAT); },
    ocr_arbre: async () => { appels.push(["ocr_arbre"]); return copie(ARBRE); },
    ocr_choisir_fichiers: async () => { appels.push(["ocr_choisir_fichiers"]); return { fichiers: FICHIERS.slice() }; },
    ocr_choisir_dossier_depot: async () => { appels.push(["ocr_choisir_dossier_depot"]); return { dossier: DOSSIER }; },
    ocr_deposer: async (...a) => {
      appels.push(["ocr_deposer"].concat(a));
      if (a.length >= 3 && a[2]) {
        const depot = copie(DEPOT_FIXTURE);
        if (DEPOT_REPONSE) depot.resultats = copie(DEPOT_REPONSE);
        return { depot: depot };
      }
      return copie(CONFIRMATION_FIXTURE);
    },
    ocr_afficher: async c => { appels.push(["ocr_afficher", c]); return { ok: true }; },
  };
  window.pywebview = { api: API };

  /* ---- 1. la vue est montee par la coque dans son vrai conteneur ---- */
  exiger(TX && TX.vue === "cours", "la coque demarre sur « Mes cours »");
  await txOuvrir();   /* le vrai chargement (app.js appelle txOuvrir) : etat puis arbre */
  exiger(TX.etat && TX.etat.depot, "l'etat partage porte le depot apres le chargement");
  txMontrerVue("deposer");
  const vue = $h("#tx-v-deposer");
  const zone = $h("#tx-v-deposer .tx-depot-zone");
  exiger(zone, "la zone de depot existe");
  exiger(zone === vue.querySelector(".tx-depot-zone"), "la zone vit dans le conteneur de la vue");
  assert.strictEqual(zone.getAttribute("role"), "button", "zone : role=button");
  assert.strictEqual(zone.getAttribute("tabindex"), "0", "zone : tabindex=0");
  assert.strictEqual(plat(zone.textContent), TX_MOTS.deposer_zone, "la zone porte la phrase du contrat 5.5");

  /* ---- 2. dossier par defaut, liste vide, bouton desactive ---- */
  let destination = $h("#tx-v-deposer .tx-depot-destination");
  exiger(destination, "la phrase du dossier de destination existe");
  assert.strictEqual(plat(destination.textContent), txMot("deposer_destination", { dossier: ETAT.depot.dossier_defaut }),
    "le dossier par defaut vient de ocr_etat().depot.dossier_defaut (contrat 4.2)");
  exiger($h("#tx-v-deposer .tx-depot-liste").children.length === 0, "liste vide au depart");
  exiger($h('#tx-v-deposer [data-action="lancer"]').disabled === true, "« Extraire le texte » desactive sans fichier");

  /* ---- 3. l'evenement tx:depot et le selecteur alimentent la meme liste ---- */
  window.textesDepotChemins(["C:/Users/max/Desktop/a.pdf", "C:/Users/max/Desktop/b.pdf",
                             "C:/Users/max/Desktop/notes.docx"]);
  await Hattendre(20);
  let liste = $h("#tx-v-deposer .tx-depot-liste");
  assert.deepStrictEqual(noms(liste), ["a.pdf", "b.pdf", "notes.docx"], "tx:depot remplit la liste");
  sansEntete(liste, "la liste des fichiers retenus");
  exiger($h('#tx-v-deposer [data-action="lancer"]').disabled === false, "le bouton s'active avec des fichiers");

  const avant = appels.length;
  await clique($h('#tx-v-deposer [data-action="choisir"]'));
  exiger(DERNIER()[0] === "ocr_choisir_fichiers", "« Choisir des fichiers » appelle ocr_choisir_fichiers");
  assert.deepStrictEqual(noms(liste), ["a.pdf", "b.pdf", "notes.docx", "c.pdf"],
    "le selecteur ajoute a la meme liste, sans doublon");
  exiger(appels.length === avant + 1, "un seul appel au selecteur pour un clic");

  /* ---- 4. le dossier par defaut puis change ---- */
  await clique($h('#tx-v-deposer [data-action="changer"]'));
  exiger(DERNIER()[0] === "ocr_choisir_dossier_depot", "« Changer » appelle ocr_choisir_dossier_depot");
  assert.strictEqual(plat(destination.textContent), txMot("deposer_destination", { dossier: DOSSIER }),
    "la phrase suit le dossier choisi");

  /* ---- 5. les deux temps de ocr_deposer ---- */
  await clique($h('#tx-v-deposer [data-action="lancer"]'));
  let appel = DERNIER();
  assert.strictEqual(appel[0], "ocr_deposer", "« Extraire le texte » appelle ocr_deposer");
  exiger(appel.length === 3, "sans `confirme` : deux arguments, jamais trois (recu " + JSON.stringify(appel) + ")");
  assert.strictEqual(appel[2], DOSSIER, "le dossier choisi est transmis");
  assert.deepStrictEqual(appel[1], ["C:/Users/max/Desktop/a.pdf", "C:/Users/max/Desktop/b.pdf",
                                    "C:/Users/max/Desktop/notes.docx", "C:/Users/max/Desktop/c.pdf"],
    "les chemins absolus retenus sont transmis, comme la reponse de ocr_choisir_fichiers (contrat 4.6)");
  const dialogue = $h("#d-tx-deposer-confirmer");
  exiger(dialogue, "le dialogue est cree par la vue");
  exiger(dialogue.open === true, "le dialogue de confirmation s'ouvre apres le premier appel");
  assert.strictEqual(plat($h("#tx-v-deposer .tx-depot-confirmer-texte").textContent), CONFIRMATION_FIXTURE.confirmer,
    "le dialogue montre la phrase de confirmation de l'API");

  /* les refus sont listes avec leur phrase, et sortent de la liste des retenus */
  const refuses = $h("#tx-v-deposer .tx-depot-refuses");
  exiger(refuses.hidden === false, "la liste des refus est visible");
  assert.deepStrictEqual(noms(refuses), ["notes.docx"], "le refus porte le nom du fichier");
  assert.strictEqual(plat(refuses.children[0].querySelector(".tx-depot-raison").textContent),
    CONFIRMATION_FIXTURE.refuses[0].raison, "le refus porte la phrase de l'API (contrat 4.6)");
  assert.deepStrictEqual(noms(liste), ["a.pdf", "b.pdf", "c.pdf"], "un refuse n'est pas un fichier retenu");
  /* les refus du premier temps sont aussi dans le dialogue de confirmation (E-V6-7) */
  const refusesDialogue = $h("#tx-v-deposer .tx-depot-confirmer-refuses");
  exiger(refusesDialogue, "le dialogue porte une liste de refus");
  assert.deepStrictEqual(noms(refusesDialogue), ["notes.docx"],
    "le dialogue de confirmation liste les refus du premier temps");
  assert.strictEqual(plat(refusesDialogue.children[0].querySelector(".tx-depot-raison").textContent),
    CONFIRMATION_FIXTURE.refuses[0].raison, "le dialogue porte la phrase du refus");

  const appelsAvant = appels.length;
  await clique($h('#tx-v-deposer [data-action="confirmer"]'));
  appel = DERNIER();
  exiger(appels.length === appelsAvant + 1, "le deuxieme temps est un seul appel");
  assert.strictEqual(appel[0], "ocr_deposer", "le deuxieme temps appelle encore ocr_deposer");
  exiger(appel.length === 4, "avec `confirme` : trois arguments (recu " + JSON.stringify(appel) + ")");
  assert.strictEqual(appel[3], true, "le deuxieme appel passe confirme=True");
  assert.strictEqual(appel[2], DOSSIER, "le deuxieme appel garde le dossier");
  exiger(dialogue.open === false, "le dialogue se ferme a la confirmation");

  /* ---- 6. les resultats : succes, echec, refuse ---- */
  const bloc = $h("#tx-v-deposer .tx-depot-resultats");
  exiger(bloc.hidden === false, "la liste des resultats s'affiche");
  const resultats = $h("#tx-v-deposer .tx-depot-resultats-liste").children;
  assert.strictEqual(resultats.length, 3, "les trois resultats de la fixture sont montres");
  const ok = resultats[0], echec = resultats[1], refuse = resultats[2];
  assert.strictEqual(ok.getAttribute("data-statut"), "ok");
  assert.strictEqual(plat(ok.querySelector(".tx-depot-nom").textContent), "scan.pdf");
  assert.ok(contenu(ok).indexOf(TX_MOTS.statut_traite) >= 0, "un succes est annonce comme traite");
  const afficher = ok.querySelector('[data-action="afficher"]');
  exiger(afficher, "un succes offre « Afficher dans l'explorateur »");
  const avantAfficher = appels.length;
  await clique(afficher);
  exiger(DERNIER()[0] === "ocr_afficher", "le bouton appelle ocr_afficher");
  assert.strictEqual(DERNIER()[1], DEPOT_FIXTURE.dossier, "il ouvre le dossier de depot (contrat 5.4)");
  exiger(appels.length === avantAfficher + 1, "un seul appel d'affichage");

  assert.strictEqual(echec.getAttribute("data-statut"), "echec");
  assert.strictEqual(plat(echec.querySelector(".tx-depot-nom").textContent), "flou.pdf");
  assert.ok(contenu(echec).indexOf(TX_MOTS.motif_difficile) >= 0, "un echec dit la phrase de son motif");
  assert.ok(contenu(echec).indexOf(TX_MOTS.deposer_intact) >= 0, "un echec dit que le fichier est intact");
  assert.ok(contenu(echec).indexOf(TX_MOTS.statut_traite) < 0, "un echec n'est jamais presente comme un succes");
  assert.strictEqual(echec.querySelector('[data-action="afficher"]'), null, "un echec n'offre pas d'affichage");

  assert.strictEqual(refuse.getAttribute("data-statut"), "refuse");
  assert.ok(contenu(refuse).indexOf("notes.docx") >= 0, "un refuse porte son nom");
  assert.ok(contenu(refuse).indexOf(TXT_PAS_PDF) >= 0, "un refuse porte la phrase de refus");
  for (const li of resultats) sansEntete(li, "un resultat");

  /* ---- 6bis. la liste des retenus est videe apres un depot termine (E-V6-5) ---- */
  liste = $h("#tx-v-deposer .tx-depot-liste");
  assert.deepStrictEqual(noms(liste), [], "un depot termine vide la liste des fichiers retenus");
  exiger($h('#tx-v-deposer [data-action="lancer"]').disabled === true,
    "sans fichier retenu, « Extraire le texte » est desactive");
  exiger($h("#tx-v-deposer .tx-depot-resultats").hidden === false, "les resultats restent affiches");

  /* ---- 6ter. un fichier retenu peut etre retire avant le depot ---- */
  window.textesDepotChemins(["C:/Users/max/Desktop/x.pdf", "C:/Users/max/Desktop/y.pdf",
                             "C:/Users/max/Desktop/z.pdf"]);
  await Hattendre(20);
  assert.deepStrictEqual(noms(liste), ["x.pdf", "y.pdf", "z.pdf"], "les trois fichiers sont retenus");
  await clique(liste.children[1].querySelector('[data-action="retirer"]'));
  assert.deepStrictEqual(noms(liste), ["x.pdf", "z.pdf"], "« Retirer » enleve le fichier de la liste");
  exiger($h('#tx-v-deposer [data-action="lancer"]').disabled === false, "la liste n'est pas vide");
  await clique($h('#tx-v-deposer [data-action="lancer"]'));
  const retenus = DERNIER();
  assert.strictEqual(retenus[0], "ocr_deposer", "« Extraire le texte » interroge l'API");
  assert.deepStrictEqual(retenus[1], ["C:/Users/max/Desktop/x.pdf", "C:/Users/max/Desktop/z.pdf"],
    "seuls les fichiers qui restent partent a l'API");
  await clique($h('#tx-v-deposer [data-action="annuler"]'));
  exiger($h("#d-tx-deposer-confirmer").open === false, "Annuler ferme le dialogue");

  /* ---- 6quater. un document « a verifier » n'est jamais annonce « Traite » (E-V6-6) ---- */
  DEPOT_REPONSE = copie(DEPOT_FIXTURE.resultats).concat([{
    nom: "moyen.pdf", statut: "a_verifier", motif: "",
    sortie_pdf: "C:/Users/max/Desktop/Depot choisi/moyen.pdf",
    sortie_texte: "C:/Users/max/Desktop/Depot choisi/moyen.pdf.md", pages: 5 }]);
  await clique($h('#tx-v-deposer [data-action="lancer"]'));
  await clique($h('#tx-v-deposer [data-action="confirmer"]'));
  const apres = $h("#tx-v-deposer .tx-depot-resultats-liste");
  const verifie = apres.children.filter(li => li.getAttribute("data-statut") === "a_verifier")[0];
  exiger(verifie, "le resultat « a verifier » est montre : " + contenu(apres));
  assert.strictEqual(plat(verifie.querySelector(".tx-depot-nom").textContent), "moyen.pdf");
  assert.ok(contenu(verifie).indexOf(TX_MOTS.statut_a_verifier) >= 0, "le resultat dit « À vérifier »");
  assert.ok(contenu(verifie).indexOf(TX_MOTS.statut_traite) < 0, "il n'est jamais annonce « Traité »");
  assert.ok(contenu(verifie).indexOf(TX_MOTS.avertissement_a_verifier) >= 0,
    "il porte l'avertissement des pages peu sures");
  exiger(verifie.querySelector('[data-action="afficher"]'), "il offre l'affichage dans l'explorateur");

  /* ---- 7. clavier sur la zone : Entree et Espace ouvrent le selecteur ---- */
  for (const touche of ["Enter", " "]) {
    const avantTouche = appels.length;
    let empeche = false;
    const ev = { type: "keydown", key: touche, target: zone, preventDefault() { empeche = true; } };
    zone.dispatchEvent(ev);
    await Hattendre(40);
    exiger(empeche, "la touche " + JSON.stringify(touche) + " est consommee");
    exiger(appels.length === avantTouche + 1 && DERNIER()[0] === "ocr_choisir_fichiers",
      "la touche " + JSON.stringify(touche) + " ouvre le selecteur");
  }
  /* une autre touche ne fait rien */
  const avantAutre = appels.length;
  zone.dispatchEvent({ type: "keydown", key: "a", target: zone, preventDefault() {} });
  await Hattendre(20);
  exiger(appels.length === avantAutre, "une autre touche n'ouvre rien");

  /* ---- 8. un depot sans chemin est ignore avec un toast, jamais un plantage ---- */
  const toastsAvant = lesToasts().length;
  const nomsAvant = noms(liste).slice();
  window.textesDepotChemins([{ name: "fichier.pdf" }]);
  await Hattendre(20);
  assert.deepStrictEqual(noms(liste), nomsAvant, "un objet File n'entre pas dans la liste");
  const toasts = lesToasts();
  exiger(toasts.length === toastsAvant + 1, "un toast explique le depot ignore");
  assert.strictEqual(toasts[toasts.length - 1], TX_DEPOT_MOTS.sans_chemin, "le toast dit quoi faire");
  window.textesDepotChemins(null);
  await Hattendre(20);
  assert.deepStrictEqual(noms(liste), nomsAvant, "un depot vide ne change rien");

  /* ---- 9. un clic sur la zone (pas sur le bouton) ouvre le selecteur (E-V6-7) ---- */
  const avantZone = appels.length;
  await clique($h("#tx-v-deposer .tx-depot-zone-texte"));
  exiger(appels.length === avantZone + 1 && DERNIER()[0] === "ocr_choisir_fichiers",
    "un clic sur la zone en pointilles ouvre le selecteur");

  console.log("OK");
})().catch(e => { console.error(e && e.stack ? e.stack : e); process.exit(1); });
"""


@unittest.skipUnless(shutil.which("node"), "node absent : parcours sur DOM factice non execute")
class DeposerParcours(unittest.TestCase):
    """La vue sur la vraie page : entrees, refus, deux temps, dossier, resultats, clavier."""

    def test_parcours_de_la_vue_sur_le_dom_factice(self):
        node = shutil.which("node") or "node"
        coupe = tj.ENTETE.find("/* ---- arbre de la page")
        self.assertGreater(coupe, 0, "marqueur du DOM factice introuvable")
        depot = json.loads(tj.lire(FIXTURE))
        etat = json.loads(tj.lire(FIXTURE_ETAT))
        dossier = tempfile.mkdtemp(prefix="parcours-deposer-")
        script = os.path.join(dossier, "_parcours_deposer.js")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(tj.ENTETE[:coupe] + "\n" + tj.PAGE + "\n" + tj.PRELUDE + "\n")
                f.write("const ETATPAGE = %s;\n" % json.dumps(etat, ensure_ascii=False))
                f.write("const CONFIRMATION_FIXTURE = %s;\n" % json.dumps(depot["confirmation"], ensure_ascii=False))
                f.write("const DEPOT_FIXTURE = %s;\n" % json.dumps(depot["depot"], ensure_ascii=False))
                f.write('const TXT_PAS_PDF = %s;\n' % json.dumps(depot["confirmation"]["refuses"][0]["raison"], ensure_ascii=False))
                for nom in ("commun.js", "textes-deposer.js", "textes.js"):
                    f.write("\n/* ===== %s ===== */\n" % nom)
                    f.write(tj.lire(os.path.join(INTERFACE, nom)).replace("\r\n", "\n"))
                f.write("\n" + PARCOURS)
            r = subprocess.run([node, script, INTERFACE], capture_output=True, text=True, timeout=180)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        self.assertEqual(r.returncode, 0, "le parcours a echoue :\n%s\n%s" % (r.stdout, r.stderr))
        self.assertIn("OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
