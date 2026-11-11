"""Tests de la vue « Mes cours » de « Mes textes » (tache R8, contrat 5.4).

Aucune fenetre, aucun navigateur, aucune dependance : les fichiers de l'interface sont lus sur le
disque. Le parcours (Node, s'ignore sans `node`) charge la vraie page d'index.html dans le DOM
factice de tests/test_textes_js.py, puis execute les vraies fonctions de commun.js,
textes-arbre.js, textes-cours.js et de la coque textes.js contre une doublure de l'API. Le
composant d'arborescence n'est jamais double : c'est celui de R7, dans son vrai conteneur
(`#tx-v-cours`). Les evenements remontent jusqu'a `document` comme dans un navigateur.

Le rendu vient des fixtures du contrat 5.6 (`arbre.json`, `etat.json`), les reponses d'exemple de
`ocr_arbre` et `ocr_etat`. Le parcours verifie : la phrase d'etat, « Tout ouvrir » et « Tout
fermer », « Actualiser », les cinq actions branchees sur la bonne methode avec le bon chemin,
la copie avec son repli quand le presse-papiers moderne manque, les deux temps de `restaurer` et
de `reessayer` (`confirme=True` seulement au deuxieme clic), l'annulation qui n'appelle rien,
la phrase de motif sous un document « a verifier » ou « non reussi », l'erreur de l'API en toast,
et l'etat vide avec son renvoi vers « Choisir quoi traiter ».

Deux tests statiques ferment les portes du contrat : aucune methode retiree (4.8) n'est appelee,
et aucun HTML n'est construit par concatenation.

Ce que ces tests ne mesurent pas : aucun vrai navigateur (donc ni rendu, ni presse-papiers reel,
ni <dialog> natif, ni focus reel, ni lecture d'ecran), Windows et macOS non executes.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import json, os, shutil, subprocess, sys, tempfile, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests import test_textes_js as tj

INTERFACE = tj.INTERFACE
FIXTURE_ARBRE = os.path.join(tj.DOCS, "fixtures", "arbre.json")
FIXTURE_ETAT = os.path.join(tj.DOCS, "fixtures", "etat.json")
VUE = os.path.join(INTERFACE, "textes-cours.js")
FEUILLE = os.path.join(INTERFACE, "textes-cours.css")

# Contrat 4.8 : methodes retirees de l'API. Aucune ne doit rester dans une vue (porte du contrat).
METHODES_RETIREES = ("ocr_apercu", "ocr_chercher", "ocr_copier", "ocr_exporter", "ocr_documents",
                     "ocr_lancer", "ocr_pdf_restaurer")

# Les cinq actions du contrat 5.4 et la methode que chacune appelle.
ACTIONS = {"ouvrir": "ocr_ouvrir", "afficher": "ocr_afficher", "copier": "ocr_copier_texte",
           "restaurer": "ocr_restaurer", "reessayer": "ocr_traiter"}


class VueCoursStatique(unittest.TestCase):
    """textes-cours.js et textes-cours.css : forme, globales, methodes, phrases, styles."""

    @classmethod
    def setUpClass(cls):
        cls.source = tj.lire(VUE)
        cls.feuille = tj.lire(FEUILLE)

    def test_fichier_en_lf_et_non_vide(self):
        self.assertGreater(len(self.source), 1500, "textes-cours.js est vide ou presque")
        self.assertTrue(self.source.endswith("\n"), "le fichier finit par un saut de ligne")
        with open(VUE, "rb") as f:
            self.assertNotIn(b"\r", f.read(), "textes-cours.js doit etre ecrit en LF")
        with open(FEUILLE, "rb") as f:
            self.assertNotIn(b"\r", f.read(), "textes-cours.css doit etre ecrit en LF")
        with open(os.path.abspath(__file__), "rb") as f:
            self.assertNotIn(b"\r", f.read(), "ce fichier de test doit etre ecrit en LF")

    def test_la_vue_du_contrat(self):
        """Contrat 5.2 : chaque vue rend { init, rafraichir, activer, desactiver }."""
        self.assertIn("txVueCours", self.source)
        for methode in ("init", "rafraichir", "activer", "desactiver"):
            with self.subTest(methode=methode):
                self.assertRegex(self.source, r"(?m)^\s{2}%s\(" % methode)

    def test_chaque_action_appelle_sa_methode(self):
        sans = tj.sans_commentaires(self.source)
        for action, methode in ACTIONS.items():
            with self.subTest(action=action):
                self.assertIn('"%s"' % action, sans, "action du contrat 5.4 : %s" % action)
                self.assertIn(methode, sans, "methode de l'action %s : %s" % (action, methode))

    def test_aucune_methode_retiree(self):
        """Porte du contrat 4.8 : une methode retiree n'existe plus, donc aucune vue ne l'appelle."""
        sans = tj.sans_commentaires(self.source)
        for methode in METHODES_RETIREES:
            with self.subTest(methode=methode):
                self.assertNotRegex(sans, r"\b%s\b" % methode,
                                    "methode retiree (4.8) encore appelee : %s" % methode)

    def test_aucun_html_construit(self):
        sans = tj.sans_commentaires(self.source)
        for procede in tj.HTML_CONSTRUIT:
            with self.subTest(procede=procede):
                self.assertNotIn(procede, sans, "aucun HTML construit par concatenation : %s" % procede)
        self.assertNotRegex(sans, r"\b(ic|esc)\(", "ic() et esc() de commun.js rendent du HTML")
        self.assertIn("createElement", sans)
        self.assertIn("textContent", sans)

    def test_aucun_tiret_cadratin(self):
        for nom, source in (("textes-cours.js", self.source), ("textes-cours.css", self.feuille),
                            ("ce test", tj.lire(os.path.abspath(__file__)))):
            for tiret in (chr(0x2013), chr(0x2014)):
                with self.subTest(fichier=nom, tiret=hex(ord(tiret))):
                    self.assertNotIn(tiret, source)

    def test_styles_de_la_vue(self):
        for selecteur in (".tx-cours-entete", ".tx-cours-resume", ".tx-cours-actions", ".tx-cours-arbre",
                          ".tx-cours-vide", ".tx-cours-lien", ".tx-cours-motif", "#d-tx-cours-confirmer"):
            with self.subTest(selecteur=selecteur):
                self.assertIn(selecteur, self.feuille, "selecteur absent de textes-cours.css : %s" % selecteur)
        self.assertIn("var(--", self.feuille, "les styles passent par les jetons")
        self.assertFalse([c for c in __import__("re").findall(r"#[0-9a-fA-F]{3,8}\b", self.feuille)],
                         "aucune couleur en dur dans textes-cours.css")


@unittest.skipUnless(shutil.which("node"), "node absent : parcours sur DOM factice non execute")
class VueCoursParcours(unittest.TestCase):
    """textes-cours.js sur la vraie page : etat, actions, deux temps, motifs, etat vide."""

    @classmethod
    def setUpClass(cls):
        node = shutil.which("node") or "node"
        coupe = tj.ENTETE.find("/* ---- arbre de la page")
        assert coupe > 0, "marqueur de l'arbre de la page introuvable"
        arbre = json.loads(tj.lire(FIXTURE_ARBRE))
        etat = json.loads(tj.lire(FIXTURE_ETAT))
        dossier = tempfile.mkdtemp(prefix="parcours-cours-")
        script = os.path.join(dossier, "_parcours_cours.js")
        try:
            with open(script, "w", encoding="utf-8") as f:
                f.write(tj.ENTETE[:coupe] + "\n" + tj.PAGE + "\n" + tj.PRELUDE + "\n")
                f.write("const ARBRE_FIXTURE = %s;\n" % json.dumps(arbre, ensure_ascii=False))
                f.write("const ETAT_FIXTURE = %s;\n" % json.dumps(etat, ensure_ascii=False))
                for nom in ("commun.js", "textes-arbre.js", "textes-cours.js", "textes.js"):
                    f.write("\n/* ===== %s ===== */\n" % nom)
                    f.write(tj.lire(os.path.join(INTERFACE, nom)).replace("\r\n", "\n"))
                f.write("\n" + PARCOURS)
            r = subprocess.run([node, script, INTERFACE], capture_output=True, text=True, timeout=180)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
        cls.resultat = r

    def test_parcours_de_la_vue_cours(self):
        self.assertEqual(self.resultat.returncode, 0,
                         "le parcours a echoue :\n%s\n%s" % (self.resultat.stdout, self.resultat.stderr))
        self.assertIn("OK", self.resultat.stdout)


PARCOURS = r"""
(async () => {
  const exiger = (cond, message) => { if (!cond) throw new assert.AssertionError({ message: message }); };
  const plat = t => String(t).replace(/\s+/g, ' ').trim();
  const txt = el => plat(el ? el.textContent : '');
  const $h = s => document.querySelector(s);
  const copie = o => JSON.parse(JSON.stringify(o));
  const attendre = () => Hattendre(40);
  const clique = async el => { exiger(el, 'element introuvable'); el.dispatchEvent({ type: 'click' }); await attendre(); };
  const toasts = () => $h('#toasts').children.map(t => {
    const m = String(t.innerHTML).match(/<span>([\s\S]*)<\/span>/); return m ? Hdecode(m[1]) : ''; });

  /* ---- doublure de l'API : la forme du contrat, cle par cle ---- */
  let ETAT = copie(ETAT_FIXTURE), ARBRE = copie(ARBRE_FIXTURE);
  const APPELS = [];
  const HREPONSES = { ocr_etat: () => ETAT, ocr_arbre: () => ARBRE };
  const doublure = nom => async (...args) => {
    APPELS.push({ nom: nom, args: args });
    const f = HREPONSES[nom];
    const r = typeof f === 'function' ? f(...args) : f;
    return r === undefined ? { ok: true } : copie(r);
  };
  const API = {};
  for (const nom of ['ocr_etat', 'ocr_arbre', 'ocr_ouvrir', 'ocr_afficher', 'ocr_copier_texte',
                     'ocr_restaurer', 'ocr_traiter']) API[nom] = doublure(nom);
  window.pywebview = { api: API };

  const noms = () => APPELS.map(a => a.nom);
  const appelsDe = nom => APPELS.filter(a => a.nom === nom);
  const vider = () => { APPELS.length = 0; };
  const items = () => Array.from(document.querySelectorAll('#tx-cours-arbre [role=treeitem]'));
  /* Les noeuds reellement visibles : les branches repliees sont dans un groupe hidden, comme dans
     le navigateur (le composant rend tout l'arbre et masque les groupes). */
  const visibles = () => items().filter(li => {
    let p = li.parentNode;
    while (p && p !== document.body) {
      if (p.tagName && String(p.tagName).toLowerCase() === 'ul' && p.hidden) return false;
      p = p.parentNode;
    }
    return true;
  });
  const liDe = chemin => items().filter(li => li.getAttribute('data-chemin') === chemin)[0] || null;
  const agir = async (chemin, action) => {
    const li = liDe(chemin);
    exiger(li, 'document absent de l arbre : ' + chemin);
    await clique(li.querySelector('.tx-menu'));
    const item = document.querySelector('.tx-menu-liste [data-action="' + action + '"]');
    exiger(item, 'action proposee par le menu : ' + action);
    await clique(item);
  };
  const STUDER = 'Histoire contemporaine/Semaine 3/Studer 1996.pdf';
  const A_VERIFIER = 'Histoire contemporaine/Semaine 3/Cours du 12 octobre.pdf';
  const NON_TRAITE = 'Histoire contemporaine/Semaine 3/Annexe 1.pdf';
  const ECHEC = 'Histoire contemporaine/Semaine 4/Carte des alliances.pdf';

  /* ---- 1. au chargement : la vue est montee dans son conteneur, rien n'est lu ---- */
  const conteneur = $h('#tx-v-cours');
  exiger(conteneur, 'le conteneur de la vue est dans la page');
  exiger($h('#tx-cours-entete'), 'la vue monte son en-tete');
  for (const action of ['tout-ouvrir', 'tout-fermer', 'actualiser']) {
    exiger($h('#tx-cours-actions [data-action="' + action + '"]'), 'bouton de la vue : ' + action);
  }
  assert.strictEqual(txt($h('#tx-cours-resume')), '', 'aucune phrase d etat avant le premier chargement');
  exiger($h('#tx-cours-arbre').hidden, 'l arbre est cache tant que rien n est lu');
  exiger($h('#tx-cours-vide').hidden, 'l etat vide est cache tant que rien n est lu');
  assert.deepStrictEqual(APPELS, [], 'la vue ne lit rien avant txRafraichir');
  assert.strictEqual(TX.vue, 'cours', 'la vue cours est la vue active');

  /* ---- 2. premier chargement : arbre, phrase d etat, compteurs de la racine ---- */
  await txRafraichir();
  assert.deepStrictEqual(noms(), ['ocr_etat', 'ocr_arbre'], 'etat puis arbre : ' + JSON.stringify(noms()));
  exiger(!$h('#tx-cours-arbre').hidden, 'l arbre s affiche');
  exiger($h('#tx-cours-vide').hidden, 'pas d etat vide avec des cours');
  assert.strictEqual(txt($h('#tx-cours-resume')), '2 traités, 1 à vérifier, 1 non réussis',
    'phrase d etat (resume_cours) : ' + txt($h('#tx-cours-resume')));
  const coursA = liDe('Histoire contemporaine');
  exiger(coursA, 'le cours est rendu');
  assert.strictEqual(coursA.getAttribute('aria-expanded'), 'false', 'un cours est replie au depart');
  assert.strictEqual(visibles().length, 2, 'seuls les deux cours sont visibles, replies');
  /* le premier chargement pose deja les phrases de motif, sans aucun clic */
  const motifDirect = liDe(ECHEC).querySelector('.tx-ligne .tx-cours-motif');
  exiger(motifDirect, 'la phrase de motif est posee au chargement de l arbre');
  assert.strictEqual(txt(motifDirect), TX_MOTS.motif_difficile, 'motif du premier chargement');

  /* ---- 3. Tout ouvrir et Tout fermer ---- */
  await clique($h('#tx-cours-actions [data-action="tout-ouvrir"]'));
  assert.strictEqual(liDe('Histoire contemporaine').getAttribute('aria-expanded'), 'true', 'Tout ouvrir ouvre un cours');
  exiger(visibles().some(li => li.getAttribute('data-chemin') === STUDER), 'les documents du cours sont rendus');
  assert.strictEqual(visibles().length, 10, 'tous les noeuds de l arbre sont visibles');
  await clique($h('#tx-cours-actions [data-action="tout-fermer"]'));
  assert.strictEqual(liDe('Histoire contemporaine').getAttribute('aria-expanded'), 'false', 'Tout fermer referme');
  assert.strictEqual(visibles().length, 2, 'seuls les cours restent visibles');

  /* ---- 4. la phrase de motif sous le nom d un document ---- */
  await clique($h('#tx-cours-actions [data-action="tout-ouvrir"]'));
  const motifEchec = liDe(ECHEC).querySelector('.tx-ligne .tx-cours-motif');
  exiger(motifEchec, 'la phrase de motif est sous le nom d un echec');
  assert.strictEqual(txt(motifEchec), TX_MOTS.motif_difficile, 'motif du document en echec');
  const motifVerifier = liDe(A_VERIFIER).querySelector('.tx-ligne .tx-cours-motif');
  exiger(motifVerifier, 'la phrase d avertissement est sous le nom d un document a verifier');
  assert.strictEqual(txt(motifVerifier), TX_MOTS.avertissement_a_verifier, 'avertissement du document a verifier');
  assert.strictEqual(liDe(STUDER).querySelector('.tx-cours-motif'), null, 'un document traite n a pas de motif');
  assert.strictEqual(liDe(NON_TRAITE).querySelector('.tx-cours-motif'), null, 'un document non traite n a pas de motif');
  /* une branche ouverte a la main garde le motif : le composant redessine, la vue le remet */
  await clique($h('#tx-cours-actions [data-action="tout-fermer"]'));
  await clique(liDe('Histoire contemporaine').querySelector('.tx-bascule'));
  await clique(liDe('Histoire contemporaine/Semaine 4').querySelector('.tx-bascule'));
  exiger(visibles().some(li => li.getAttribute('data-chemin') === ECHEC), 'la branche rouverte montre l echec');
  const motifApres = liDe(ECHEC).querySelector('.tx-cours-motif');
  exiger(motifApres, 'la phrase de motif survit a un redessin du composant');
  assert.strictEqual(txt(motifApres), TX_MOTS.motif_difficile, 'la phrase remise est la meme');
  await clique($h('#tx-cours-actions [data-action="tout-ouvrir"]'));

  /* ---- 5. ouvrir, afficher, copier ---- */
  HREPONSES.ocr_ouvrir = { ok: true };
  vider();
  const avantOuvrir = toasts().length;
  await agir(STUDER, 'ouvrir');
  assert.deepStrictEqual(appelsDe('ocr_ouvrir'), [{ nom: 'ocr_ouvrir', args: [STUDER] }],
    'ouvrir appelle ocr_ouvrir avec le chemin du document');
  assert.deepStrictEqual(toasts().slice(avantOuvrir), [],
    'une ouverture reussie ne dit rien : c est le lecteur du systeme qui montre le PDF');

  HREPONSES.ocr_afficher = { ok: true };
  vider();
  await agir(STUDER, 'afficher');
  assert.deepStrictEqual(appelsDe('ocr_afficher'), [{ nom: 'ocr_afficher', args: [STUDER] }],
    'afficher appelle ocr_afficher avec le chemin du document');

  HREPONSES.ocr_copier_texte = { texte: 'Texte du document.', caracteres: 19, pages: 14 };
  HCOPIE = '';
  vider();
  await agir(STUDER, 'copier');
  assert.deepStrictEqual(appelsDe('ocr_copier_texte'), [{ nom: 'ocr_copier_texte', args: [STUDER] }],
    'copier appelle ocr_copier_texte avec le chemin du document');
  assert.strictEqual(HCOPIE, 'Texte du document.', 'le texte du document part dans le presse-papiers');

  /* repli de copie : sans navigator.clipboard, la zone de texte et execCommand prennent le relais */
  const CLIPBOARD = navigator.clipboard;
  navigator.clipboard = null;
  const EXECUTES = [];
  document.execCommand = cmd => { EXECUTES.push(cmd); return true; };
  HCOPIE = '';
  vider();
  await agir(STUDER, 'copier');
  assert.deepStrictEqual(EXECUTES, ['copy'], 'sans presse-papiers moderne, execCommand copie');
  assert.strictEqual(HCOPIE, '', 'le repli ne passe pas par navigator.clipboard');
  navigator.clipboard = CLIPBOARD;
  delete document.execCommand;

  /* un document sans texte n a pas l action copier */
  await clique(liDe(NON_TRAITE).querySelector('.tx-menu'));
  assert.strictEqual(document.querySelector('.tx-menu-liste [data-action="copier"]'), null,
    'copier n est propose que pour un document qui a un texte');
  await clique(liDe(NON_TRAITE).querySelector('.tx-menu'));

  /* ---- 6. restaurer : deux temps, confirme=True au deuxieme clic seulement ---- */
  const PHRASE_RESTAURER = "Remettre le PDF d'origine et supprimer le texte ?";
  HREPONSES.ocr_restaurer = (...args) => (args.length > 1 ? { ok: true } : { confirmer: PHRASE_RESTAURER });
  vider();
  await agir(STUDER, 'restaurer');
  assert.deepStrictEqual(appelsDe('ocr_restaurer'), [{ nom: 'ocr_restaurer', args: [STUDER] }],
    'restaurer interroge l API sans confirme');
  assert.strictEqual(appelsDe('ocr_restaurer').filter(a => a.args[1] === true).length, 0,
    'aucun confirme=True avant le deuxieme clic');
  const boite = $h('#d-tx-cours-confirmer');
  exiger(boite, 'le dialogue de confirmation est cree par la vue');
  exiger(boite.open, 'le dialogue est ouvert');
  assert.strictEqual(txt(boite.querySelector('.tx-cours-dialogue-texte')), PHRASE_RESTAURER,
    'le dialogue dit la phrase de l API');

  /* annuler n appelle rien et ferme le dialogue */
  vider();
  await clique(boite.querySelector('[data-action="annuler"]'));
  exiger(!boite.open, 'Annuler ferme le dialogue');
  assert.deepStrictEqual(appelsDe('ocr_restaurer'), [], 'Annuler n appelle pas l API');

  /* confirmer rappelle avec confirme=True, puis la vue relit tout */
  vider();
  await agir(STUDER, 'restaurer');
  vider();
  await clique($h('#d-tx-cours-confirmer [data-action="confirmer"]'));
  await attendre();
  assert.deepStrictEqual(appelsDe('ocr_restaurer'), [{ nom: 'ocr_restaurer', args: [STUDER, true] }],
    'le deuxieme clic passe confirme=True');
  assert.deepStrictEqual(noms().slice(-2), ['ocr_etat', 'ocr_arbre'], 'apres restauration, la vue relit tout');
  exiger(!$h('#d-tx-cours-confirmer').open, 'le dialogue est referme');

  /* une restauration ordinaire ne dit rien de plus */
  HREPONSES.ocr_restaurer = (...args) => (args.length > 1 ? { ok: true } : { confirmer: PHRASE_RESTAURER });
  vider();
  const avantSilence = toasts().length;
  await agir(STUDER, 'restaurer');
  await clique($h('#d-tx-cours-confirmer [data-action="confirmer"]'));
  await attendre();
  assert.deepStrictEqual(toasts().slice(avantSilence), [], 'sans `message`, aucune phrase de plus');

  /* le `message` de l'API est montre : le texte edite est reste en place (contrat 3.3, E-V6-2) */
  const PHRASE_GARDE = "Le PDF d'origine est remis. Le texte, que tu avais modifié, est resté en place.";
  HREPONSES.ocr_restaurer = (...args) => (args.length > 1 ? { ok: true, message: PHRASE_GARDE }
                                                          : { confirmer: PHRASE_RESTAURER });
  vider();
  const avantGarde = toasts().length;
  await agir(STUDER, 'restaurer');
  await clique($h('#d-tx-cours-confirmer [data-action="confirmer"]'));
  await attendre();
  assert.deepStrictEqual(toasts().slice(avantGarde), [PHRASE_GARDE],
    'la phrase de `message` est montree apres une restauration qui garde un texte edite');
  const deuxTemps = appelsDe('ocr_restaurer');
  assert.strictEqual(deuxTemps.length, 2, 'la restauration garde ses deux temps');
  assert.deepStrictEqual(deuxTemps[1].args, [STUDER, true], 'le deuxieme appel porte confirme=True');
  HREPONSES.ocr_restaurer = (...args) => (args.length > 1 ? { ok: true } : { confirmer: PHRASE_RESTAURER });

  /* ---- 7. reessayer : ocr_traiter sans confirme, puis confirme=True ---- */
  const PHRASE_TRAITER = '1 documents, environ 13 pages, 1 à 2 minutes. 1 PDF sera remplacé par une version cherchable.';
  HREPONSES.ocr_traiter = (...args) => (args.length > 2 ? { file: { etat: 'en_cours' } }
    : { confirmer: PHRASE_TRAITER, documents: 1, pages: 13, minutes: [1, 2], remplacements: 1 });
  vider();
  await agir(ECHEC, 'reessayer');
  assert.deepStrictEqual(appelsDe('ocr_traiter'), [{ nom: 'ocr_traiter', args: [[ECHEC], true] }],
    'reessayer demande un traitement refait, sans confirme');
  vider();
  await clique($h('#d-tx-cours-confirmer [data-action="confirmer"]'));
  await attendre();
  assert.deepStrictEqual(appelsDe('ocr_traiter'), [{ nom: 'ocr_traiter', args: [[ECHEC], true, true] }],
    'le deuxieme clic passe confirme=True');

  /* ---- 8. une erreur de l API s affiche en toast ---- */
  HREPONSES.ocr_ouvrir = { erreur: 'Le fichier est introuvable.' };
  const avant0 = toasts().length;
  await agir(STUDER, 'ouvrir');
  assert.deepStrictEqual(toasts().slice(avant0), ['Le fichier est introuvable.'],
    'une ouverture refusee dit la phrase de l API');
  HREPONSES.ocr_ouvrir = { ok: true };

  HREPONSES.ocr_afficher = { erreur: "L'ouverture a été refusée." };
  const avant = toasts().length;
  await agir(STUDER, 'afficher');
  assert.deepStrictEqual(toasts().slice(avant), ["L'ouverture a été refusée."], 'la phrase de l erreur est montree');

  HREPONSES.ocr_copier_texte = { erreur: "Ce document n'a pas de texte à copier." };
  const avant2 = toasts().length;
  await agir(STUDER, 'copier');
  assert.deepStrictEqual(toasts().slice(avant2), ["Ce document n'a pas de texte à copier."],
    'une copie vide dit la phrase de l API');

  /* ---- 9. Actualiser relit tout ---- */
  HREPONSES.ocr_afficher = { ok: true };
  HREPONSES.ocr_copier_texte = { texte: 'x', caracteres: 1, pages: 1 };
  vider();
  await clique($h('#tx-cours-actions [data-action="actualiser"]'));
  await attendre();
  assert.deepStrictEqual(noms(), ['ocr_etat', 'ocr_arbre'], 'Actualiser appelle txRafraichir');

  /* ---- 10. etat vide : la phrase d accueil et le renvoi vers « Choisir quoi traiter » ---- */
  ARBRE = { racine: 'C:/Moodle', cours: [],
            compteurs: { fichiers: 0, traites: 0, a_verifier: 0, echecs: 0, non_traites: 0, pages_non_traitees: 0 } };
  await txRafraichir();
  exiger(!$h('#tx-cours-vide').hidden, 'l etat vide s affiche sans cours');
  assert.strictEqual(txt($h('#tx-cours-vide p')), TX_MOTS.etat_vide, 'phrase d etat vide');
  exiger($h('#tx-cours-arbre').hidden, 'l arbre est cache quand il est vide');
  assert.strictEqual(txt($h('#tx-cours-resume')), '', 'aucune phrase d etat sans document');
  exiger($h('#tx-cours-actions [data-action="tout-ouvrir"]').hidden, 'Tout ouvrir disparait sans arbre');
  exiger($h('#tx-cours-actions [data-action="tout-fermer"]').hidden, 'Tout fermer disparait sans arbre');
  exiger(!$h('#tx-cours-actions [data-action="actualiser"]').hidden, 'Actualiser reste disponible');
  const lien = $h('#tx-cours-vide a');
  exiger(lien, 'le renvoi vers « Choisir quoi traiter » est un lien');
  assert.strictEqual(lien.getAttribute('href'), '#tx-o-choisir', 'le lien vise le sous-onglet');
  assert.strictEqual(txt(lien), TX_MOTS.onglet_choisir, 'le lien porte le nom du sous-onglet');
  await clique(lien);
  assert.strictEqual(TX.vue, 'choisir', 'le lien ouvre « Choisir quoi traiter »');
  exiger(!$h('#tx-v-choisir').hidden, 'le panneau de « Choisir quoi traiter » est visible');
  txMontrerVue('cours');

  /* l arbre revient quand des cours reapparaissent */
  ARBRE = copie(ARBRE_FIXTURE);
  await txRafraichir();
  exiger($h('#tx-cours-vide').hidden, 'l etat vide disparait avec des cours');
  exiger(!$h('#tx-cours-arbre').hidden, 'l arbre revient');
  assert.strictEqual(txt($h('#tx-cours-resume')), '2 traités, 1 à vérifier, 1 non réussis', 'la phrase d etat revient');

  console.log('OK');
  process.exit(0);
})().catch(e => { console.error(e && e.stack ? e.stack : e); process.exit(1); });
"""


if __name__ == "__main__":
    unittest.main()
