"use strict";
/* Coque de « Mes textes » (tache R7, contrat 5.2) : sous-onglets, etat partage, chargement de
   l'arbre, progression du traitement, carte du moteur. Charge apres l'arborescence et les trois
   vues, avant app.js : choisirOnglet appelle txOuvrir() en arrivant sur l'onglet.
   Toute phrase d'interface est dans TX_MOTS et nulle part ailleurs (contrat 5.5).
   Aucun HTML n'est construit ici : tout texte venu de l'API passe par textContent. */

/* Etat partage par la coque et les vues : TX.arbre, TX.etat, TX.vue (contrat 5.2). */
let TX = { arbre: null, etat: null, vue: "cours" };

const TX_VUES = ["cours", "choisir", "deposer"];

let txVueActive = "cours";     // la vue affichee : TX.vue peut etre ecrase par sync.js
let txVuesObjets = {};          // nom -> objet de vue (init, rafraichir, activer, desactiver)
let txMoteurEnCours = false;   // une installation du moteur est en vol

/* Phrases de l'interface (contrat 5.5), mot pour mot. {} et {n} marquent une valeur intercalee.
   Les cles carte_* restent celles de la carte de Ma semaine (O9) ; preparer_* n'est plus appele
   depuis R11 et reste au tableau tant que le test des cles de R7 le nomme. */
const TX_MOTS = {
  intro: "Choisis les documents dont tu veux le texte. Le PDF est remplacé par une version cherchable, une copie de l'original est gardée, et le texte est écrit à côté.",
  onglet_cours: "Mes cours",
  onglet_choisir: "Choisir quoi traiter",
  onglet_deposer: "Déposer des fichiers",
  statut_non_traite: "Non traité",
  statut_en_attente: "En attente",
  statut_en_cours: "En cours",
  statut_traite: "Traité",
  statut_a_verifier: "À vérifier",
  statut_echec: "Non réussi",
  motif_difficile: "Le texte de ce document est trop abîmé pour être lu. Ton PDF est resté tel quel.",
  motif_vide: "Aucun texte n'a été trouvé dans ce document. Ton PDF est resté tel quel.",
  motif_illisible: "Ce document n'a pas pu être lu. Ton PDF est resté tel quel.",
  motif_verification: "Le PDF cherchable n'a pas passé la vérification. Ton PDF est resté tel quel.",
  motif_ecriture: "Le résultat n'a pas pu être écrit. Ton PDF est resté tel quel.",
  motif_erreur: "Cette opération n'a pas abouti. Ton PDF est resté tel quel.",
  avertissement_a_verifier: "Certaines pages sont peu sûres : vérifie le texte.",
  action_ouvrir: "Ouvrir le PDF",
  action_afficher: "Afficher dans l'explorateur",
  action_afficher_mac: "Afficher dans le Finder",
  action_copier: "Copier le texte",
  action_restaurer: "Restaurer l'original",
  action_reessayer: "Réessayer",
  tout_ouvrir: "Tout ouvrir",
  tout_fermer: "Tout fermer",
  traiter_selection: "Traiter la sélection",
  choix_resume: "{n} documents choisis, environ {p} pages",
  choix_resume_sans_pages: "{n} documents choisis",
  deposer_zone: "Glisse des PDF ici",
  deposer_choisir: "Choisir des fichiers",
  deposer_destination: "Les résultats seront rangés dans : {dossier}",
  deposer_changer: "Changer",
  deposer_lancer: "Extraire le texte",
  deposer_intact: "Ton fichier n'a pas été modifié.",
  etat_vide: "Rien à montrer pour l'instant. Choisis des documents dans « Choisir quoi traiter ».",
  resume_cours: "{t} traités, {v} à vérifier, {e} non réussis",
  /* Phrases du composant d'arborescence (contrat 5.3) : noms accessibles et resume d'un dossier. */
  arbre_nom: "Documents des cours",
  bascule: "Ouvrir ou fermer",
  case_fichier: "Choisir {}",
  case_dossier: "Choisir tout {}",
  menu_actions: "Actions sur {}",
  fichier: "fichier",
  fichiers: "fichiers",
  traite_un: "traité",
  traites: "traités",
  /* Carte du moteur et progression : phrases deja ecrites par l'ancien onglet, gardees. */
  carte_moteur_absent: "Le moteur d'extraction n'est pas encore installé.",
  progres_pct: "{} %",
  progres_pause: "Traitement en pause.",
  action_reprendre: "Reprendre",
  /* Annonce de la migration des anciens textes (contrat 8.7). */
  migration: "Anciens textes rangés à côté de leurs PDF : {} déplacés, {} supprimés, {} laissés en place.",
  /* Carte de Ma semaine (sync.js) : cles encore lues, retirees par R11. */
  document: "document",
  documents: "documents",
  page: "page",
  pages: "pages",
  carte_environ: "environ",
  carte_duree: "Environ {} à {} minutes.",
  carte_reprendre: "Reprendre l'extraction ({} documents restants)",
  carte_reprendre_un: "Reprendre l'extraction ({} document restant)",
  carte_page: "Page {} sur {}",
  carte_rang: "Document {} sur {}",
  carte_pause_sync: "En pause pendant la synchronisation. Elle reprend à la fin.",
  carte_rien: "Aucun document à préparer.",
  preparer_titre: "Préparer mes cours",
  preparer_maintenant: "Préparer maintenant",
};

/* ------------------------------------------------------------------ outils */
/* Une phrase de TX_MOTS : {} remplace par les valeurs, dans l'ordre ; {nom} par la valeur du nom. */
function txMot(cle, ...valeurs) {
  const modele = String(TX_MOTS[cle] === undefined ? "" : TX_MOTS[cle]);
  const nommees = valeurs.length && valeurs[0] && typeof valeurs[0] === "object" && !Array.isArray(valeurs[0])
    ? valeurs[0] : null;
  if (nommees) {
    return modele.replace(/\{([a-zA-Z_]+)\}/g, (tout, nom) => (nommees[nom] === undefined ? tout : String(nommees[nom])));
  }
  let i = 0;
  return modele.replace(/\{\}/g, () => String(valeurs[i++] === undefined ? "" : valeurs[i - 1]));
}

function txNombre(n) {
  return String(Math.max(0, Math.round(Number(n) || 0))).replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
}

function txPluriel(n, un, plusieurs) { return Number(n) > 1 ? plusieurs : un; }

/* L'etat partage, toujours un objet : sync.js remplace TX par un ocr_etat entier. */
function txAssurer() {
  if (!TX || typeof TX !== "object") TX = { arbre: null, etat: null, vue: txVueActive };
  if (TX_VUES.indexOf(String(TX.vue)) < 0) TX.vue = txVueActive;
  return TX;
}

/* Une erreur de l'API s'affiche telle quelle ; rend vrai quand une phrase a ete montree. */
function txErreur(r) {
  if (r && r.erreur) { toast(String(r.erreur), "critique"); return true; }
  return false;
}

function txMontrer(el, visible) { if (el) el.hidden = !visible; }

/* Un evenement sans dependre de CustomEvent (tests sur DOM factice). */
function txEvenement(type, detail) {
  if (typeof CustomEvent === "function") return new CustomEvent(type, { detail: detail });
  const e = { type: type, detail: detail };
  e.preventDefault = () => {};
  return e;
}

/* ------------------------------------------------------------------ textes fixes de la coque */
function txLibelles() {
  const intro = $("#tx-intro");
  if (intro) intro.textContent = TX_MOTS.intro;
  for (const vue of TX_VUES) {
    const onglet = $("#tx-o-" + vue);
    if (onglet) onglet.textContent = TX_MOTS["onglet_" + vue];
  }
}

/* ------------------------------------------------------------------ sous-onglets (contrat 5.2) */
function txVueDe(nom) {
  return txVuesObjets[nom] || null;
}

/* Active un sous-onglet : un seul panneau visible, une seule vue active. */
function txMontrerVue(nom) {
  if (TX_VUES.indexOf(String(nom)) < 0) return;
  const ancienne = txVueDe(txVueActive);
  if (txVueActive !== nom && ancienne && typeof ancienne.desactiver === "function") ancienne.desactiver();
  txVueActive = nom;
  txAssurer().vue = nom;
  for (const vue of TX_VUES) {
    const onglet = $("#tx-o-" + vue), panneau = $("#tx-v-" + vue);
    const actif = vue === nom;
    if (onglet) { onglet.setAttribute("aria-selected", actif ? "true" : "false"); onglet.tabIndex = actif ? 0 : -1; }
    if (panneau) panneau.hidden = !actif;
  }
  const active = txVueDe(nom);
  if (active && typeof active.activer === "function") active.activer();
  if (active && typeof active.rafraichir === "function" && txAssurer().etat) active.rafraichir(txAssurer());
}

function txMonterOnglets() {
  const barre = $("#tx-onglets");
  if (!barre) return;
  barre.addEventListener("click", e => {
    const onglet = e.target && e.target.closest ? e.target.closest("[role=tab]") : null;
    if (onglet) txMontrerVue(onglet.getAttribute("data-vue"));
  });
  barre.addEventListener("keydown", e => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].indexOf(e.key) < 0) return;
    e.preventDefault();
    const i = TX_VUES.indexOf(txVueActive);
    const j = e.key === "Home" ? 0 : e.key === "End" ? TX_VUES.length - 1
      : e.key === "ArrowLeft" ? (i + TX_VUES.length - 1) % TX_VUES.length : (i + 1) % TX_VUES.length;
    txMontrerVue(TX_VUES[j]);
    const onglet = $("#tx-o-" + TX_VUES[j]);
    if (onglet && typeof onglet.focus === "function") onglet.focus();
  });
}

/* Une vue est un objet {init, rafraichir, activer, desactiver} ; une fabrique est acceptee aussi.
   Les globales sont lues par leur nom : une `const` de script n'est pas une propriete de window. */
function txGlobalVue(nom) {
  if (nom === "cours") return typeof txVueCours !== "undefined" ? txVueCours : null;
  if (nom === "choisir") return typeof txVueChoisir !== "undefined" ? txVueChoisir : null;
  if (nom === "deposer") return typeof txVueDeposer !== "undefined" ? txVueDeposer : null;
  return null;
}

function txMonterVues() {
  for (const vue of TX_VUES) {
    const global = txGlobalVue(vue);
    if (!global) continue;
    const objet = typeof global === "function" && typeof global.init !== "function" ? global() : global;
    if (!objet || typeof objet !== "object") continue;
    txVuesObjets[vue] = objet;
    const conteneur = $("#tx-v-" + vue);
    if (conteneur && typeof objet.init === "function") objet.init(conteneur);
  }
}

/* ------------------------------------------------------------------ carte du moteur */
function txMoteur(etat) {
  const carte = $("#tx-moteur");
  if (!carte) return;
  const moteur = (etat && etat.moteur) || {};
  const present = !!moteur.present;
  carte.hidden = present;
  if (present) return;
  const texte = carte.querySelector(".tx-moteur-texte");
  if (texte) texte.textContent = TX_MOTS.carte_moteur_absent;
  txMontrer(carte.querySelector('[data-action="installer"]'), !txMoteurEnCours);
  txMontrer(carte.querySelector('[data-action="exe"]'), !txMoteurEnCours);
  txMontrer(carte.querySelector(".tx-moteur-installation"), txMoteurEnCours);
}

function txMoteurInstallation(p) {
  const carte = $("#tx-moteur");
  if (!carte) return;
  if (typeof txCarteInstallation === "function") txCarteInstallation(p);   // carte de Ma semaine (sync.js)
  const zone = carte.querySelector(".tx-moteur-installation");
  if (zone && !zone.hidden) {
    const recu = Number(p && p.recu) || 0, total = Number(p && p.total) || 0;
    const barre = zone.querySelector("progress"), texte = zone.querySelector(".tx-moteur-installation-texte");
    if (barre) {
      if (total > 0) barre.value = Math.max(0, Math.min(100, Math.round(recu * 100 / total)));
      else barre.removeAttribute("value");
    }
    if (texte) texte.textContent = total > 0 ? txMot("progres_pct", Math.round(recu * 100 / total)) : TX_MOTS.carte_moteur_absent;
  }
}

async function txInstaller() {
  if (!api() || txMoteurEnCours) return null;
  txMoteurEnCours = true;
  txMoteur(txAssurer().etat);
  let r = null;
  try {
    r = await api().ocr_installer();
  } finally {
    txMoteurEnCours = false;
  }
  if (r && r.erreur) { txErreur(r); txMoteur(txAssurer().etat); return r; }
  if (r) txAssurer().etat = r;
  await txRafraichir();
  return r;
}

async function txChoisirExe() {
  if (!api()) return null;
  const r = await api().ocr_choisir_exe();
  if (r && r.erreur) { txErreur(r); return r; }
  if (r) { txAssurer().etat = r; txMoteur(r); }
  return r;
}

async function txInstallerAnnuler() {
  if (!api()) return null;
  const r = await api().ocr_installer_annuler();
  txMoteurEnCours = false;
  txMoteur(txAssurer().etat);
  return r;
}

/* ------------------------------------------------------------------ barre de travail (contrat 5.2) */
/* Le bloc suit la file : document en cours, avancement, Pause et Arreter. Seul le pourcentage est
   calcule ici, a partir des nombres de Python ; les phrases viennent de TX_MOTS. */
function txTravail(file) {
  const bloc = $("#tx-travail");
  if (!bloc) return;
  const etat = String((file && file.etat) || "");
  const actif = etat === "en_cours" || etat === "pause" || etat === "pause_sync";
  bloc.hidden = !actif;
  if (!actif) return;
  const total = Math.max(0, Number(file.documents_total) || 0);
  const faits = Math.max(0, Number(file.documents_faits) || 0);
  const pages = Math.max(0, Number(file.pages) || 0);
  const page = Math.max(0, Number(file.page) || 0);
  const nom = String(file.document || "").split(/[\\/]/).pop();
  const enCours = bloc.querySelector(".tx-travail-document");
  if (enCours) enCours.textContent = nom;
  let avance = 0;
  if (total > 0) {
    avance = faits;
    if (pages > 0 && page > 0 && page < pages) avance += page / pages;
  }
  const pct = total > 0 ? Math.max(0, Math.min(100, Math.round(avance * 100 / total))) : 0;
  const pourcent = bloc.querySelector(".tx-travail-pct");
  if (pourcent) pourcent.textContent = total > 0 ? txMot("progres_pct", txNombre(pct)) : "";
  const barre = bloc.querySelector("progress");
  if (barre) {
    if (total > 0) barre.value = pct;
    else barre.removeAttribute("value");
  }
  txMontrer(bloc.querySelector('[data-action="pause"]'), etat !== "pause" && etat !== "pause_sync");
  /* Reprendre n'apparait qu'en pause (contrat 5.2) : c'est le seul chemin de reprise de l'onglet
     (ecart E-V5-2), la carte de Ma semaine ne le propose que si elle s'affiche. */
  txMontrer(bloc.querySelector('[data-action="reprendre"]'), etat === "pause" || etat === "pause_sync");
}

async function txPause() {
  if (!api()) return null;
  const r = await api().ocr_pause();
  if (r && r.erreur) return txErreur(r);
  if (r && r.file) window.textesProgres(r.file);
  return r;
}

/* Reprise : la file repart, puis l'onglet relit l'etat et l'arbre (contrat 5.2). */
async function txReprendre() {
  if (!api()) return null;
  const r = await api().ocr_reprendre();
  if (r && r.erreur) return txErreur(r);
  if (r && r.file) window.textesProgres(r.file);
  await txRafraichir();
  return r;
}

async function txArreter() {
  if (!api()) return null;
  const r = await api().ocr_annuler();
  if (r && r.erreur) return txErreur(r);
  if (r && r.file) window.textesProgres(r.file);
  return r;
}

/* ------------------------------------------------------------------ chargement (contrat 5.2) */
/* Relit l'etat et l'arbre, met a jour TX, la carte du moteur et la barre, puis la vue active. */
async function txRafraichir() {
  if (!api()) return null;
  const etat = await api().ocr_etat();
  if (etat && etat.erreur) { txErreur(etat); return null; }
  if (etat) {
    txAssurer().etat = etat;
    txMoteur(etat);
    txTravail(etat.file);
  }
  const arbre = await api().ocr_arbre();
  if (arbre && arbre.erreur) { txErreur(arbre); return null; }
  if (arbre) txAssurer().arbre = arbre;
  const vue = txVueDe(txVueActive);
  if (vue && typeof vue.rafraichir === "function") vue.rafraichir(txAssurer());
  return txAssurer();
}

/* ------------------------------------------------------------------ appels de Python */
window.textesProgres = p => {
  if (!p || typeof p !== "object") return;
  TX = TX || {};
  TX.file = p;
  const etat = String(p.etat || "");
  barreOccupee(etat === "en_cours" || etat === "pause" || etat === "pause_sync", "", "textes");
  txAssurer().etat = txAssurer().etat || {};
  txAssurer().etat.file = p;
  txTravail(p);
  document.dispatchEvent(txEvenement("tx:progres", p));
  if (etat === "terminee") txRafraichir();
  if (typeof txCarteProgres === "function") txCarteProgres(p);   // carte de Ma semaine (sync.js)
};

/* Glisser-deposer (contrat 4.6, O16) : Python remet les chemins absolus, la vue « Deposer » suit. */
window.textesDepotChemins = liste => {
  const chemins = Array.isArray(liste) ? liste : (liste ? [liste] : []);
  document.dispatchEvent(txEvenement("tx:depot", chemins));
};

/* Progression du telechargement du moteur (ecart 245) : {recu, total} en octets. */
window.textesInstallation = p => {
  if (p && typeof p === "object") txMoteurInstallation(p);
};

window.textesJournal = t => {
  if (typeof window.syncJournal === "function") window.syncJournal(String(t));
};

/* Migration des anciens textes (contrat 8.7) : une annonce, une seule fois. */
window.textesMigration = p => {
  if (!p || typeof p !== "object") return;
  toast(txMot("migration", p.deplaces || 0, p.supprimes || 0, p.restants || 0), "bon");
};

/* ------------------------------------------------------------------ stubs retires par R11 */
/* app.js appelle txOuvrir() en arrivant sur l'onglet : la coque relit tout. */
function txOuvrir() { return txRafraichir(); }

/* ------------------------------------------------------------------ branchements */
txLibelles();
txMonterOnglets();
txMonterVues();
txMontrerVue(txVueActive);

const txMoteurCarte = $("#tx-moteur");
if (txMoteurCarte) {
  txMoteurCarte.addEventListener("click", e => {
    const bouton = e.target && e.target.closest ? e.target.closest("[data-action]") : null;
    if (!bouton) return;
    const action = bouton.getAttribute("data-action");
    if (action === "installer") txInstaller();
    else if (action === "exe") txChoisirExe();
    else if (action === "installer-annuler") txInstallerAnnuler();
  });
}

const txTravailBloc = $("#tx-travail");
if (txTravailBloc) {
  txTravailBloc.addEventListener("click", e => {
    const bouton = e.target && e.target.closest ? e.target.closest("[data-action]") : null;
    if (!bouton) return;
    if (bouton.getAttribute("data-action") === "pause") txPause();
    else if (bouton.getAttribute("data-action") === "reprendre") txReprendre();
    else if (bouton.getAttribute("data-action") === "arreter") txArreter();
  });
}
