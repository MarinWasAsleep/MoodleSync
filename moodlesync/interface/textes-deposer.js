"use strict";
/* Vue « Déposer des fichiers » de « Mes textes » (tache R10, contrat 5.4).
   Fichier cree vide par R7 : la vue y definit la globale txVueDeposer
   { init(conteneur), rafraichir(TX), activer(), desactiver() }.

   Le depot a deux entrees et une seule liste : le selecteur natif (ocr_choisir_fichiers) et le
   glisser-deposer de pywebview, que la coque rediffuse en `tx:depot` (contrat 4.6, O16). Un depot
   sans chemin (le navigateur ne livre que des objets File) est ignore avec un toast, jamais un
   plantage.

   Deux temps (contrat 5.4) : ocr_deposer(fichiers, dossier) sans `confirme` rend la phrase de
   confirmation et les refus ; le dialogue d-tx-deposer-confirmer les montre ; puis
   ocr_deposer(fichiers, dossier, true) lance le travail. Les resultats sont ceux de
   `depot.resultats` (contrat 4.6), relus par txRafraichir quand la file se termine.

   Aucun chemin absolu n'est montre (contrat 9.6), sauf le dossier de depot, seule exception de
   cette vue. Aucun HTML construit par concatenation : createElement et textContent seulement. */

/* Deux phrases que le contrat 5.5 ne range pas dans TX_MOTS (ecart E-R10-1 du journal) : la seconde
   reprend mot pour mot `ocr.MESSAGES["depot_pas_pdf"]`. TX_MOTS vit dans textes.js, hors du
   perimetre de R10. */
const TX_DEPOT_MOTS = {
  sans_chemin: "Ce dépôt n'a pas livré de chemin de fichier. Utilise « Choisir des fichiers ».",
  pas_pdf: "Seuls les PDF peuvent être déposés.",
  retirer: "Retirer",
  retirer_nom: "Retirer {} de la liste",
  annuler: "Annuler",
};

/* Etat de la vue : chemins retenus (absolus, contrat 4.6), phrase des refus par nom, dossier choisi
   a la main, travail en vol. Rien n'en sort : la coque ne partage que TX. */
let txDepot = {
  racine: null, zone: null, liste: null, refuses: null, destination: null, lancer: null,
  resultats: null, resultatsListe: null, dialogue: null, confirmerTexte: null,
  confirmerRefuses: null,
  chemins: [], raisons: {}, dossier: "", occupe: false, montee: false, attente: null,
  ecoute: false,
};

/* ------------------------------------------------------------------ outils */
function txDepotEl(tag, classe, texte) {
  const el = document.createElement(tag);
  if (classe) el.className = classe;
  if (texte !== undefined) el.textContent = texte;
  return el;
}

/* Le nom seul d'un chemin : c'est ce qui s'affiche. */
function txDepotNom(chemin) {
  return String(chemin === undefined || chemin === null ? "" : chemin).split(/[\\/]/).pop();
}

/* « Afficher dans l'explorateur », ou « Afficher dans le Finder » sous macOS (contrat 5.5). */
function txDepotMotAfficher() {
  const plateforme = String((typeof navigator !== "undefined" && navigator && navigator.platform) || "");
  return plateforme.indexOf("Mac") === 0 ? TX_MOTS.action_afficher_mac : TX_MOTS.action_afficher;
}

/* La phrase d'un motif, celle de TX_MOTS (contrat 5.5) ; vide si le motif est inconnu. */
function txDepotMotif(motif) {
  const cle = "motif_" + String(motif || "");
  return TX_MOTS[cle] === undefined ? "" : TX_MOTS[cle];
}

/* Le dossier de destination : celui choisi a la main, sinon celui de Python, sinon le defaut. */
function txDepotDossier(tx) {
  if (txDepot.dossier) return txDepot.dossier;
  const depot = (tx && tx.etat && tx.etat.depot) || {};
  if (depot.dossier) return String(depot.dossier);
  return String(depot.dossier_defaut || "");
}

/* ------------------------------------------------------------------ montage du DOM */
function txDepotMonter(conteneur) {
  const racine = txDepotEl("div", "tx-depot");

  const zone = txDepotEl("div", "tx-depot-zone");
  zone.appendChild(txDepotEl("p", "tx-depot-zone-texte", TX_MOTS.deposer_zone));
  zone.setAttribute("role", "button");
  zone.setAttribute("tabindex", "0");
  zone.setAttribute("aria-label", TX_MOTS.deposer_zone);

  const choisir = txDepotEl("button", "bouton", TX_MOTS.deposer_choisir);
  choisir.setAttribute("type", "button");
  choisir.setAttribute("data-action", "choisir");

  const destination = txDepotEl("p", "tx-depot-destination");
  const changer = txDepotEl("button", "bouton petit", TX_MOTS.deposer_changer);
  changer.setAttribute("type", "button");
  changer.setAttribute("data-action", "changer");
  const ligneDossier = txDepotEl("div", "tx-depot-dossier");
  ligneDossier.appendChild(destination);
  ligneDossier.appendChild(changer);

  const liste = txDepotEl("ul", "tx-depot-liste");
  const refuses = txDepotEl("ul", "tx-depot-refuses");
  refuses.hidden = true;

  const lancer = txDepotEl("button", "bouton principal", TX_MOTS.deposer_lancer);
  lancer.setAttribute("type", "button");
  lancer.setAttribute("data-action", "lancer");
  lancer.disabled = true;

  const resultats = txDepotEl("section", "tx-depot-resultats");
  resultats.hidden = true;
  const resultatsListe = txDepotEl("ul", "tx-depot-resultats-liste");
  resultats.appendChild(resultatsListe);

  const dialogue = txDepotEl("dialog", "dialogue tx-depot-dialogue");
  dialogue.setAttribute("id", "d-tx-deposer-confirmer");
  dialogue.setAttribute("aria-label", TX_MOTS.deposer_lancer);
  const contenu = txDepotEl("div", "contenu");
  const confirmerTexte = txDepotEl("p", "tx-depot-confirmer-texte");
  const confirmerRefuses = txDepotEl("ul", "tx-depot-confirmer-refuses");
  contenu.appendChild(confirmerTexte);
  contenu.appendChild(confirmerRefuses);
  const actions = txDepotEl("div", "actions");
  const annuler = txDepotEl("button", "bouton", TX_DEPOT_MOTS.annuler);
  annuler.setAttribute("type", "button");
  annuler.setAttribute("data-action", "annuler");
  const confirmer = txDepotEl("button", "bouton principal", TX_MOTS.deposer_lancer);
  confirmer.setAttribute("type", "button");
  confirmer.setAttribute("data-action", "confirmer");
  actions.appendChild(annuler);
  actions.appendChild(confirmer);
  dialogue.appendChild(contenu);
  dialogue.appendChild(actions);

  racine.appendChild(zone);
  racine.appendChild(choisir);
  racine.appendChild(ligneDossier);
  racine.appendChild(liste);
  racine.appendChild(refuses);
  racine.appendChild(lancer);
  racine.appendChild(resultats);
  racine.appendChild(dialogue);
  conteneur.appendChild(racine);

  txDepot.racine = racine;
  txDepot.zone = zone;
  txDepot.liste = liste;
  txDepot.refuses = refuses;
  txDepot.destination = destination;
  txDepot.lancer = lancer;
  txDepot.resultats = resultats;
  txDepot.resultatsListe = resultatsListe;
  txDepot.dialogue = dialogue;
  txDepot.confirmerTexte = confirmerTexte;
  txDepot.confirmerRefuses = confirmerRefuses;
}

/* ------------------------------------------------------------------ listes */
function txDepotVider(el) {
  while (el && el.childNodes && el.childNodes.length) el.removeChild(el.childNodes[0]);
}

/* Une ligne : le nom seul, puis la phrase s'il y en a une. */
function txDepotLigne(nom, classe, phrase) {
  const li = txDepotEl("li", classe);
  li.appendChild(document.createTextNode(nom));
  if (phrase) li.appendChild(txDepotEl("span", "tx-depot-raison", phrase));
  return li;
}

/* Les fichiers retenus : les chemins choisis, moins ceux que ocr_deposer a refuses. */
function txDepotDessinerListe() {
  if (!txDepot.liste) return;
  txDepotVider(txDepot.liste);
  let retenus = 0;
  txDepot.chemins.forEach((chemin, index) => {
    if (txDepot.raisons[txDepotNom(chemin)]) return;
    retenus++;
    const li = txDepotLigne(txDepotNom(chemin), "tx-depot-fichier");
    const retirer = txDepotEl("button", "bouton petit tx-depot-retirer", TX_DEPOT_MOTS.retirer);
    retirer.setAttribute("type", "button");
    retirer.setAttribute("data-action", "retirer");
    retirer.setAttribute("data-index", String(index));
    retirer.setAttribute("aria-label", txDepotRetirerNom(txDepotNom(chemin)));
    li.appendChild(retirer);
    txDepot.liste.appendChild(li);
  });
  /* « Extraire le texte » ne s'active que s'il reste un fichier a extraire (E-V6-5). */
  if (txDepot.lancer) txDepot.lancer.disabled = txDepot.occupe || retenus === 0;
}

/* Le nom accessible du bouton qui retire un fichier de la liste. */
function txDepotRetirerNom(nom) {
  return TX_DEPOT_MOTS.retirer_nom.replace(/\{\}/g, () => String(nom));
}

/* Retirer un fichier de la liste, avant le depot : le chemin seul disparait, rien n'est touche. */
function txDepotRetirer(index) {
  const i = Number(index);
  if (!Number.isInteger(i) || i < 0 || i >= txDepot.chemins.length) return;
  txDepot.chemins.splice(i, 1);
  txDepotDessinerListe();
}

function txDepotDessinerRefuses() {
  if (!txDepot.refuses) return;
  txDepotVider(txDepot.refuses);
  const noms = Object.keys(txDepot.raisons);
  txDepot.refuses.hidden = noms.length === 0;
  for (const nom of noms) {
    txDepot.refuses.appendChild(txDepotLigne(nom, "tx-depot-refuse", txDepot.raisons[nom]));
  }
}

/* ------------------------------------------------------------------ entrees du depot */
/* Les deux entrees passent ici : selecteur (chemins absolus) et evenement tx:depot. Un element qui
   n'est pas un chemin est ignore avec un toast, jamais une exception (O16). */
function txDepotAjouter(liste) {
  const recus = Array.isArray(liste) ? liste : (liste ? [liste] : []);
  let sansChemin = 0;
  for (const chemin of recus) {
    if (typeof chemin !== "string" || !chemin.trim()) { sansChemin++; continue; }
    const propre = chemin.trim();
    if (txDepot.chemins.indexOf(propre) >= 0) continue;
    txDepot.chemins.push(propre);
  }
  if (sansChemin > 0) toast(TX_DEPOT_MOTS.sans_chemin, "critique");
  txDepotDessinerListe();
}

async function txDepotChoisirFichiers() {
  if (!api()) return null;
  const r = await api().ocr_choisir_fichiers();
  if (txErreur(r)) return r;
  if (!r || r.annule) return null;
  txDepotAjouter(r.fichiers || []);
  return r;
}

async function txDepotChangerDossier() {
  if (!api()) return null;
  const r = await api().ocr_choisir_dossier_depot();
  if (txErreur(r)) return r;
  if (!r || r.annule || !r.dossier) return null;
  txDepot.dossier = String(r.dossier);
  if (txDepot.destination) {
    txDepot.destination.textContent = txMot("deposer_destination", { dossier: txDepot.dossier });
  }
  return r;
}

/* ------------------------------------------------------------------ dialogue et travail */
function txDepotDessinerConfirmation(r) {
  if (txDepot.confirmerTexte) txDepot.confirmerTexte.textContent = String((r && r.confirmer) || "");
  if (!txDepot.confirmerRefuses) return;
  txDepotVider(txDepot.confirmerRefuses);
  for (const refuse of (r && r.refuses) || []) {
    const nom = String((refuse && refuse.nom) || "");
    txDepot.confirmerRefuses.appendChild(txDepotLigne(nom, "tx-depot-refuse",
      String((refuse && refuse.raison) || "")));
  }
}

/* Premier temps : rien ne part sans confirmation (contrat 5.4). */
async function txDepotLancer() {
  if (!api() || txDepot.occupe || !txDepot.chemins.length) return null;
  const dossier = txDepotDossier(txAssurer());
  const fichiers = txDepot.chemins.slice();
  const r = await api().ocr_deposer(fichiers, dossier);
  if (txErreur(r)) return r;
  if (!r || r.annule) return null;
  txDepot.raisons = {};
  for (const refuse of r.refuses || []) {
    if (refuse && refuse.nom) txDepot.raisons[String(refuse.nom)] = String(refuse.raison || "");
  }
  txDepotDessinerRefuses();
  txDepotDessinerListe();
  if (r.rien) return r;
  txDepot.attente = { fichiers: fichiers, dossier: dossier };
  txDepotDessinerConfirmation(r);
  if (txDepot.dialogue && typeof txDepot.dialogue.showModal === "function") txDepot.dialogue.showModal();
  return r;
}

/* Deuxieme temps : le meme appel, avec confirme=True. */
async function txDepotConfirmer() {
  if (!api() || !txDepot.attente) return null;
  const attente = txDepot.attente;
  txDepot.attente = null;
  if (txDepot.dialogue && typeof txDepot.dialogue.close === "function") txDepot.dialogue.close();
  txDepot.occupe = true;
  txDepotDessinerListe();
  let r = null;
  try {
    r = await api().ocr_deposer(attente.fichiers, attente.dossier, true);
  } finally {
    txDepot.occupe = false;
  }
  if (txErreur(r)) { txDepotDessinerListe(); return r; }
  if (r && r.depot) {
    const tx = txAssurer();
    tx.etat = tx.etat || {};
    tx.etat.depot = r.depot;
    txVueDeposer.rafraichir(tx);
  }
  txDepotDessinerListe();
  return r;
}

/* ------------------------------------------------------------------ resultats (contrat 4.6) */
function txDepotLigneResultat(resultat, dossier) {
  const nom = String((resultat && resultat.nom) || "");
  const statut = String((resultat && resultat.statut) || "");
  const motif = String((resultat && resultat.motif) || "");
  const li = txDepotEl("li", "tx-depot-resultat tx-depot-" + (statut || "inconnu"));
  li.setAttribute("data-statut", statut);
  li.appendChild(txDepotEl("span", "tx-depot-nom", nom));
  if (statut === "ok" || statut === "a_verifier") {
    const reussi = statut === "ok";
    li.appendChild(txDepotEl("span", "tx-depot-badge",
      reussi ? TX_MOTS.statut_traite : TX_MOTS.statut_a_verifier));
    if (!reussi) li.appendChild(txDepotEl("span", "tx-depot-avertissement", TX_MOTS.avertissement_a_verifier));
    const afficher = txDepotEl("button", "bouton petit", txDepotMotAfficher());
    afficher.setAttribute("type", "button");
    afficher.setAttribute("data-action", "afficher");
    afficher.setAttribute("data-dossier", dossier);
    li.appendChild(afficher);
    return li;
  }
  if (statut === "echec") {
    li.appendChild(txDepotEl("span", "tx-depot-badge", TX_MOTS.statut_echec));
    const phrase = txDepotMotif(motif);
    li.appendChild(txDepotEl("span", "tx-depot-raison",
      (phrase ? phrase + " " : "") + TX_MOTS.deposer_intact));
    return li;
  }
  /* Refuse : la phrase vient de la reponse de ocr_deposer sans `confirme` (contrat 4.6). */
  const raison = txDepot.raisons[nom] || (motif === "depot_pas_pdf" ? TX_DEPOT_MOTS.pas_pdf : "");
  if (raison) li.appendChild(txDepotEl("span", "tx-depot-raison", raison));
  return li;
}

function txDepotDessinerResultats(depot) {
  if (!txDepot.resultats || !txDepot.resultatsListe) return;
  const resultats = (depot && depot.resultats) || [];
  txDepotVider(txDepot.resultatsListe);
  txDepot.resultats.hidden = resultats.length === 0;
  if (!resultats.length) return;
  const dossier = String((depot && depot.dossier) || txDepot.dossier || "");
  for (const resultat of resultats) txDepot.resultatsListe.appendChild(txDepotLigneResultat(resultat, dossier));
}

async function txDepotAfficher(bouton) {
  if (!api()) return null;
  const dossier = String(bouton.getAttribute("data-dossier") || "");
  if (!dossier) return null;
  const r = await api().ocr_afficher(dossier);
  if (txErreur(r)) return r;
  return r;
}

/* ------------------------------------------------------------------ la vue (contrat 5.2) */
const txVueDeposer = {
  init(conteneur) {
    if (!conteneur || txDepot.montee) return;
    txDepot.montee = true;
    txDepotMonter(conteneur);
    txDepotDessinerListe();
    if (!txDepot.ecoute) {
      txDepot.ecoute = true;
      /* Glisser-deposer de pywebview : la coque rediffuse ici les chemins absolus (contrat 5.2). */
      document.addEventListener("tx:depot", e => { txDepotAjouter(e && e.detail); });
    }
    conteneur.addEventListener("click", e => {
      const cible = e.target;
      const bouton = cible && cible.closest ? cible.closest("[data-action]") : null;
      if (!bouton) {
        if (cible && cible.closest && cible.closest(".tx-depot-zone")) txDepotChoisirFichiers();
        return;
      }
      const action = bouton.getAttribute("data-action");
      if (action === "choisir") txDepotChoisirFichiers();
      else if (action === "changer") txDepotChangerDossier();
      else if (action === "lancer") txDepotLancer();
      else if (action === "confirmer") txDepotConfirmer();
      else if (action === "annuler" && txDepot.dialogue) txDepot.dialogue.close();
      else if (action === "afficher") txDepotAfficher(bouton);
      else if (action === "retirer") txDepotRetirer(bouton.getAttribute("data-index"));
    });
    /* Enter et Espace ouvrent le selecteur (contrat 5.4). */
    conteneur.addEventListener("keydown", e => {
      const zone = e.target && e.target.closest ? e.target.closest(".tx-depot-zone") : null;
      if (!zone) return;
      if (e.key !== "Enter" && e.key !== " " && e.key !== "Spacebar") return;
      if (typeof e.preventDefault === "function") e.preventDefault();
      txDepotChoisirFichiers();
    });
  },

  rafraichir(tx) {
    const depot = (tx && tx.etat && tx.etat.depot) || {};
    if (txDepot.destination) {
      const dossier = txDepotDossier(tx);
      txDepot.destination.textContent = dossier ? txMot("deposer_destination", { dossier: dossier }) : "";
    }
    txDepot.occupe = String(depot.etat || "") === "en_cours";
    /* Un depot termine vide la liste des fichiers retenus : les relancer les deposerait deux fois
       (contrat 4.6, ecart E-V6-5). Les resultats, eux, restent affiches. */
    if (String(depot.etat || "") === "termine") {
      txDepot.chemins = [];
      txDepot.raisons = {};
      txDepotDessinerRefuses();
    }
    txDepotDessinerListe();
    if (String(depot.etat || "") === "termine" || (depot.resultats || []).length) txDepotDessinerResultats(depot);
  },

  activer() { return null; },

  desactiver() { return null; },
};
