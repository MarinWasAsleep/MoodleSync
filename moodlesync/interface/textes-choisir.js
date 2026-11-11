"use strict";
/* Vue « Choisir quoi traiter » de « Mes textes » (tache R9, contrat 5.4).
   Elle tient l'arbre en mode « choisir » (txArbreCreer, contrat 5.3), montre un resume vivant de la
   selection, et fait les deux temps de ocr_traiter : sans confirme, puis avec confirme, le dialogue
   de confirmation etant cree ici dans le conteneur de la vue et non dans index.html.
   Toute phrase d'interface vient de TX_MOTS (contrat 5.5) ; les rares libelles que ce contrat ne
   nomme pas sont dans TX_CHOISIR_MOTS ci-dessous et sont ecrits au journal (ecart E-R9-1).
   Aucun HTML n'est construit par concatenation : createElement et textContent seulement. */

/* Libelles absents de TX_MOTS et du tableau 5.5, que cette tache ne peut pas y ajouter (textes.js
   est hors de son perimetre, ecart E-R9-1) : les deux cases de tout cocher, le renvoi au moteur,
   les deux boutons du dialogue et ses deux phrases propres. */
const TX_CHOISIR_MOTS = {
  tout_cocher: "Tout cocher",
  tout_decocher: "Tout décocher",
  installer_moteur: "Installer le moteur",
  annuler: "Annuler",
  confirme: "Traiter",
  remplacements: "{n} PDF remplacés",
  rien: "Il n'y a rien à traiter dans cette sélection.",
};

/* Etat de la vue : un seul arbre charge, une seule selection, un seul dialogue en attente. */
const TX_CHOISIR = {
  conteneur: null,
  composant: null,
  arbre: null,
  selection: [],
  resume: { documents: 0, pages: null, pages_connues: false },
  moteur: true,
  gele: false,
  envoi: false,
  attente: null,
  elements: {},
};

/* ------------------------------------------------------------------ outils */
function txChoisirEl(tag, classe, texte) {
  const el = document.createElement(tag);
  if (classe) el.className = classe;
  if (texte !== undefined && texte !== null) el.appendChild(document.createTextNode(String(texte)));
  return el;
}

/* Une phrase de TX_CHOISIR_MOTS, {n} remplace par la valeur nommee ; sinon une phrase de TX_MOTS. */
function txChoisirMot(cle, valeurs) {
  if (TX_CHOISIR_MOTS[cle] === undefined) return txMot(cle, valeurs || {});
  const modele = String(TX_CHOISIR_MOTS[cle]);
  if (!valeurs) return modele;
  return modele.replace(/\{([a-zA-Z_]+)\}/g, (tout, nom) =>
    (valeurs[nom] === undefined ? tout : String(valeurs[nom])));
}

function txChoisirPluriel(nombre, un, plusieurs) {
  const n = Number(nombre) || 0;
  return txNombre(n) + " " + (n === 1 ? un : plusieurs);
}

/* Accord du singulier sur les mots qui suivent un nombre : le contrat 5.5 donne le pluriel et sa
   note d'accord (« 1 document choisi, environ 1 page »). Les mots ne sont pas reecrits ici. */
function txChoisirAccorder(phrase, nom, valeur) {
  const morceaux = String(phrase).split("{" + nom + "}");
  if (morceaux.length < 2) return String(phrase);
  const singulier = mot => (/[A-Za-zÀ-ÿ]s$/.test(mot) ? mot.slice(0, -1) : mot);
  let sortie = morceaux[0] + String(valeur);
  for (let i = 1; i < morceaux.length; i++) {
    let suite = morceaux[i];
    if (Number(valeur) <= 1) {
      suite = suite.replace(/^(\s+)([A-Za-zÀ-ÿ]+)(\s+[A-Za-zÀ-ÿ]+)?/,
        (tout, blanc, premier, second) =>
          blanc + singulier(premier) + String(second || "").replace(/[A-Za-zÀ-ÿ]+/g, singulier));
    }
    sortie += suite;
  }
  return sortie;
}

/* Le resume vivant : choix_resume quand les pages de tous les fichiers choisis sont connues,
   choix_resume_sans_pages sinon (contrat 5.4 et 5.5). */
function txChoisirResumeTexte(resume) {
  const documents = Number(resume && resume.documents) || 0;
  if (!documents) return "";
  const sansPages = !(resume && resume.pages_connues);
  let phrase = sansPages ? TX_MOTS.choix_resume_sans_pages : TX_MOTS.choix_resume;
  phrase = txChoisirAccorder(phrase, "n", txNombre(documents));
  if (!sansPages) phrase = txChoisirAccorder(phrase, "p", txNombre(Number(resume.pages) || 0));
  return phrase;
}

/* ------------------------------------------------------------------ la barre et le dialogue */
function txChoisirMonter(conteneur) {
  const barre = txChoisirEl("div", "tx-choix-barre");
  const resume = txChoisirEl("p", "tx-choix-resume");
  resume.setAttribute("aria-live", "polite");
  const actions = txChoisirEl("div", "tx-choix-actions");
  const toutCocher = txChoisirEl("button", "bouton", TX_CHOISIR_MOTS.tout_cocher);
  toutCocher.type = "button";
  toutCocher.setAttribute("data-action", "tout-cocher");
  const toutDecocher = txChoisirEl("button", "bouton", TX_CHOISIR_MOTS.tout_decocher);
  toutDecocher.type = "button";
  toutDecocher.setAttribute("data-action", "tout-decocher");
  const lancer = txChoisirEl("button", "bouton principal tx-choix-lancer", txMot("traiter_selection"));
  lancer.type = "button";
  lancer.setAttribute("data-action", "traiter");
  lancer.disabled = true;
  lancer.setAttribute("aria-disabled", "true");
  actions.appendChild(toutCocher);
  actions.appendChild(toutDecocher);
  actions.appendChild(lancer);
  barre.appendChild(resume);
  barre.appendChild(actions);

  const zone = txChoisirEl("div", "tx-choix-arbre");

  const dialogue = document.createElement("dialog");
  dialogue.className = "dialogue tx-choix-dialogue";
  dialogue.id = "d-tx-confirmer";
  const entete = txChoisirEl("header");
  const titre = txChoisirEl("h3", "tx-confirme-titre", txMot("traiter_selection"));
  entete.appendChild(titre);
  const corps = txChoisirEl("div", "contenu");
  const phrase = txChoisirEl("p", "tx-confirme-phrase");
  const nombres = txChoisirEl("ul", "tx-confirme-nombres");
  const lignes = {};
  for (const cle of ["documents", "pages", "minutes", "remplacements"]) {
    const ligne = txChoisirEl("li", "tx-confirme-" + cle);
    lignes[cle] = ligne;
    nombres.appendChild(ligne);
  }
  corps.appendChild(phrase);
  corps.appendChild(nombres);
  const actionsDialogue = txChoisirEl("div", "actions");
  const annuler = txChoisirEl("button", "bouton", TX_CHOISIR_MOTS.annuler);
  annuler.type = "button";
  annuler.setAttribute("data-ferme", "");
  const confirmer = txChoisirEl("button", "bouton principal", TX_CHOISIR_MOTS.confirme);
  confirmer.type = "button";
  confirmer.setAttribute("data-action", "confirmer");
  actionsDialogue.appendChild(annuler);
  actionsDialogue.appendChild(confirmer);
  dialogue.appendChild(entete);
  dialogue.appendChild(corps);
  dialogue.appendChild(actionsDialogue);

  conteneur.appendChild(barre);
  conteneur.appendChild(zone);
  conteneur.appendChild(dialogue);

  TX_CHOISIR.elements = {
    barre: barre, resume: resume, actions: actions, lancer: lancer, zone: zone,
    toutCocher: toutCocher, toutDecocher: toutDecocher,
    dialogue: dialogue, titre: titre, phrase: phrase, nombres: nombres,
    documents: lignes.documents, pages: lignes.pages, minutes: lignes.minutes,
    remplacements: lignes.remplacements, confirmer: confirmer, annuler: annuler,
  };
  TX_CHOISIR.composant = txArbreCreer(zone, {
    mode: "choisir",
    onSelection: (chemins, resumeSelection) => txChoisirSelection(chemins, resumeSelection),
  });
}

/* ------------------------------------------------------------------ selection */
function txChoisirSelection(chemins, resume) {
  if (TX_CHOISIR.gele) return;                 // selection gelee pendant un traitement
  TX_CHOISIR.selection = Array.isArray(chemins) ? chemins.slice() : [];
  TX_CHOISIR.resume = resume || { documents: 0, pages: null, pages_connues: false };
  if (TX_CHOISIR.elements.resume) {
    TX_CHOISIR.elements.resume.textContent = txChoisirResumeTexte(TX_CHOISIR.resume);
  }
  txChoisirBouton();
}

function txChoisirBouton() {
  const lancer = TX_CHOISIR.elements.lancer;
  if (!lancer) return;
  lancer.textContent = TX_CHOISIR.moteur ? txMot("traiter_selection") : TX_CHOISIR_MOTS.installer_moteur;
  /* Sans moteur, le bouton reste actif meme sans selection : il ne traite rien, il renvoie a la
     carte du moteur (contrat 5.4, ecart E-V6-4). */
  lancer.disabled = TX_CHOISIR.gele || (TX_CHOISIR.moteur && TX_CHOISIR.selection.length === 0);
  lancer.setAttribute("aria-disabled", lancer.disabled ? "true" : "false");
}

/* Tout cocher ou tout decocher : la vue clique les cases que le composant laisse cochables, qui
   reste seul maitre de sa selection (contrat 5.3). Un dossier entier reste rendu comme le dossier. */
function txChoisirTout(valeur) {
  const conteneur = TX_CHOISIR.conteneur;
  if (!conteneur || TX_CHOISIR.gele) return;
  for (const boite of conteneur.querySelectorAll(".tx-case")) {
    if (boite.disabled) continue;
    if (!!boite.checked === !!valeur) continue;
    if (typeof boite.click === "function") boite.click();
    else boite.dispatchEvent({ type: "click" });
  }
  txChoisirBouton();
}

/* ------------------------------------------------------------------ gel de la selection */
function txChoisirAppliquerGel() {
  const conteneur = TX_CHOISIR.conteneur;
  if (!conteneur || !conteneur.classList) return;
  conteneur.classList.toggle("tx-gele", TX_CHOISIR.gele);
  for (const bouton of [TX_CHOISIR.elements.toutCocher, TX_CHOISIR.elements.toutDecocher]) {
    if (bouton) bouton.disabled = TX_CHOISIR.gele;
  }
  if (!TX_CHOISIR.gele) return;
  for (const boite of conteneur.querySelectorAll(".tx-case")) boite.disabled = true;
}

function txChoisirGeler(gel) {
  TX_CHOISIR.gele = !!gel;
  txChoisirAppliquerGel();
  txChoisirBouton();
}

/* La fin d'un traitement vide la selection et remonte l'arbre tel que Python l'a rendu. */
function txChoisirTerminer() {
  const composant = TX_CHOISIR.composant;
  TX_CHOISIR.selection = [];
  TX_CHOISIR.resume = { documents: 0, pages: null, pages_connues: false };
  TX_CHOISIR.gele = false;
  if (TX_CHOISIR.elements.resume) TX_CHOISIR.elements.resume.textContent = "";
  if (composant) {
    composant.vider();
    if (TX_CHOISIR.arbre) composant.charger(TX_CHOISIR.arbre);
  }
  txChoisirAppliquerGel();
  txChoisirBouton();
}

function txChoisirDegeler() {
  TX_CHOISIR.gele = false;
  if (TX_CHOISIR.composant && TX_CHOISIR.arbre) TX_CHOISIR.composant.charger(TX_CHOISIR.arbre);
  txChoisirAppliquerGel();
  txChoisirBouton();
}

/* ------------------------------------------------------------------ dialogue de confirmation */
function txChoisirOuvrirDialogue(reponse) {
  const el = TX_CHOISIR.elements;
  if (!el.dialogue) return;
  TX_CHOISIR.attente = reponse;
  if (el.phrase) el.phrase.textContent = String(reponse.confirmer || "");
  if (el.documents) {
    el.documents.textContent = txChoisirPluriel(reponse.documents, txMot("document"), txMot("documents"));
  }
  if (el.pages) el.pages.textContent = txChoisirPluriel(reponse.pages, txMot("page"), txMot("pages"));
  if (el.minutes) {
    const bornes = Array.isArray(reponse.minutes) ? reponse.minutes : [];
    el.minutes.textContent = bornes.length >= 2 ? txMot("carte_duree", bornes[0], bornes[1]) : "";
  }
  if (el.remplacements) {
    el.remplacements.textContent = txChoisirMot("remplacements", { n: txNombre(reponse.remplacements) });
  }
  if (typeof el.dialogue.showModal === "function") el.dialogue.showModal();
  else el.dialogue.open = true;
  if (el.confirmer && typeof el.confirmer.focus === "function") el.confirmer.focus();
}

function txChoisirFermerDialogue() {
  const dialogue = TX_CHOISIR.elements.dialogue;
  TX_CHOISIR.attente = null;
  if (!dialogue) return;
  if (typeof dialogue.close === "function") dialogue.close();
  dialogue.open = false;
}

/* ------------------------------------------------------------------ appels de l'API */
/* Une reponse de ocr_traiter : erreur en toast, rien en toast, confirmation en dialogue,
   file active en gel de la selection. */
function txChoisirReponse(reponse, apresConfirmation) {
  if (!reponse) return null;
  if (txErreur(reponse)) return reponse;
  if (reponse.rien) { toast(TX_CHOISIR_MOTS.rien); return reponse; }
  if (reponse.confirmer && !apresConfirmation) { txChoisirOuvrirDialogue(reponse); return reponse; }
  if (reponse.file) txChoisirGeler(true);
  return reponse;
}

async function txChoisirTraiter() {
  if (!api() || TX_CHOISIR.gele || TX_CHOISIR.envoi) return null;
  /* Le moteur absent passe avant la selection : le bouton renvoie a sa carte (E-V6-4). */
  if (!TX_CHOISIR.moteur) { txChoisirVersMoteur(); return null; }
  if (!TX_CHOISIR.selection.length) { txChoisirBouton(); return null; }
  TX_CHOISIR.envoi = true;
  let reponse = null;
  try {
    reponse = await api().ocr_traiter(TX_CHOISIR.selection.slice());
  } finally {
    TX_CHOISIR.envoi = false;
  }
  return txChoisirReponse(reponse, false);
}

async function txChoisirConfirmer() {
  if (!TX_CHOISIR.attente || !api() || TX_CHOISIR.envoi) return null;
  const chemins = TX_CHOISIR.selection.slice();
  txChoisirFermerDialogue();
  TX_CHOISIR.envoi = true;
  let reponse = null;
  try {
    reponse = await api().ocr_traiter(chemins, false, true);
  } finally {
    TX_CHOISIR.envoi = false;
  }
  return txChoisirReponse(reponse, true);
}

/* Sans moteur, le bouton renvoie a la carte d'installation (#tx-moteur, contrat 5.4). */
function txChoisirVersMoteur() {
  const carte = document.querySelector("#tx-moteur");
  if (!carte) return;
  const cible = carte.querySelector('[data-action="installer"]') || carte;
  if (typeof carte.scrollIntoView === "function") carte.scrollIntoView({ block: "start" });
  if (typeof cible.focus === "function") cible.focus();
}

/* ------------------------------------------------------------------ lecture de l'etat partage */
function txChoisirRafraichir(etatPartage) {
  const partage = etatPartage || (typeof TX !== "undefined" && TX ? TX : null);
  if (!partage) return;
  TX_CHOISIR.moteur = !!(partage.etat && partage.etat.moteur && partage.etat.moteur.present);
  if (partage.arbre && TX_CHOISIR.composant) {
    TX_CHOISIR.arbre = partage.arbre;
    TX_CHOISIR.composant.charger(partage.arbre);
    txChoisirAppliquerGel();
  }
  txChoisirBouton();
}

/* ------------------------------------------------------------------ clics et progression */
function txChoisirClic(e) {
  const cible = e && e.target;
  if (!cible || !cible.closest) return;
  if (cible.closest("[data-ferme]")) { txChoisirFermerDialogue(); return; }
  const bouton = cible.closest("[data-action]");
  if (!bouton) return;
  if (bouton.disabled) return;
  const action = bouton.getAttribute("data-action");
  if (action === "tout-cocher") txChoisirTout(true);
  else if (action === "tout-decocher") txChoisirTout(false);
  else if (action === "traiter") txChoisirTraiter();
  else if (action === "confirmer") txChoisirConfirmer();
}

function txChoisirProgres(e) {
  const file = (e && e.detail) || null;
  if (!file) return;
  const etat = String(file.etat || "");
  if (etat === "en_cours" || etat === "pause" || etat === "pause_sync") {
    if (!TX_CHOISIR.gele) txChoisirGeler(true);
    return;
  }
  if (etat === "terminee") { txChoisirTerminer(); return; }
  if (etat === "annulee") txChoisirDegeler();
}

/* ------------------------------------------------------------------ la vue (contrat 5.2) */
const txVueChoisir = {
  init(conteneur) {
    if (!conteneur) return;
    if (TX_CHOISIR.conteneur === conteneur && TX_CHOISIR.composant) return;
    TX_CHOISIR.conteneur = conteneur;
    txChoisirMonter(conteneur);
    conteneur.addEventListener("click", txChoisirClic);
    document.addEventListener("tx:progres", txChoisirProgres);
  },
  rafraichir(etatPartage) {
    return txChoisirRafraichir(etatPartage);
  },
  activer() {
    txChoisirBouton();
  },
  desactiver() {
    if (TX_CHOISIR.attente) txChoisirFermerDialogue();
  },
  /* Lecture seule de la selection, pour les tests et la revue ; la coque ne s'en sert pas. */
  selection() {
    return TX_CHOISIR.selection.slice();
  },
};
