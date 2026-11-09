"use strict";
/* Onglet Mes textes : liste, recherche, copie, export (tache U2).
   Charge avant app.js (contrat 3.4) : choisirOnglet appelle txOuvrir() en arrivant sur l'onglet.
   Toute phrase d'interface est dans TX_MOTS et nulle part ailleurs (tests/test_textes_js.py).
   Aucun HTML n'est construit ici : tout texte venu de l'API passe par textContent ou createTextNode. */

let TX = null;                 // dernier ocr_etat()
let txPret = false;            // premier chargement fini
let txOccupe = false;          // extraction ou restauration en cours
let txDocs = [];               // derniere liste de ocr_documents()
let txJeton = 0;               // jeton de la requete de recherche : une reponse perimee est ignoree
let txDelai = 0;               // minuterie du delai de saisie
let txEnVol = false;           // une seule requete de recherche en vol (ecart 158)
let txAttente = null;          // terme tape pendant qu'une requete est en vol
let txMenu = null;             // menu ouvert, s'il y en a un

const DELAI_RECHERCHE = 300;   // plan 3.5 : un delai de 300 ms avant de chercher

/* Phrases de l'onglet. Plan 3.5, contrat 3.4 et 5 ; les autres sont declarees dans le test
   (PHRASES_NOUVELLES) et soumises a Maxence. {} marque une valeur intercalee. */
const TX_MOTS = {
  lecture: "Lecture des textes...",
  vide: "Aucun texte extrait pour l'instant.",
  document: "document",
  documents: "documents",
  page: "page",
  pages: "pages",
  de_texte: "de texte.",
  lisible: "lisible",
  lisibles: "lisibles",
  a_verifier: "à vérifier",
  a_verifier_badge: "À vérifier",
  bon: "Bon",
  difficile: "Difficile",
  cherchable: "PDF cherchable",
  texte_natif: "texte natif",
  scanne: "scanné",
  mo: "Mo",
  ouvrir: "Ouvrir",
  copier: "Copier le texte",
  refaire: "Refaire",
  refaire_titre: "Refaire ce document ?",
  copier_extrait: "Copier l'extrait",
  copier_cours: "Copier le contexte du cours",
  choisir_cours: "Choisis un cours",
  aucun_cours: "Aucun cours.",
  exporter: "Exporter",
  archive: "Archive ZIP",
  archive_jsonl: "Archive avec le détail page par page",
  archive_jsonl_aide: "Un fichier de données par page, pour les outils qui citent les sources.",
  markdown: "Fichier Markdown",
  ouvrir_dossier: "Ouvrir le dossier des textes",
  qualite: "Voir la qualité",
  aucun_souci: "Aucun document à vérifier.",
  plus: "Plus d'actions",
  aucun_resultat: "Aucun résultat.",
  resultat: "résultat",
  resultats: "résultats",
  tronque: " Tronqué.",
  copie: "Copié : {} caractères.",
  rien_a_copier: "Aucun texte à copier.",
  copie_ratee: "Copie impossible : sélectionne le texte à la main.",
  trop_long: "Ce texte est trop long pour le presse-papiers.",
  exporte: "Exporté : {} {}.",
  source: "Ce document s'ouvre depuis ton dossier de rangement.",
};

/* ------------------------------------------------------------------ outils */
function txVider(el) { if (el) el.textContent = ""; }

function txNombre(n) {
  return String(Math.max(0, Math.round(Number(n) || 0))).replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
}

function txVolume(octets) {
  const mo = Math.max(0, Number(octets) || 0) / 1048576;
  return mo.toFixed(1).replace(".", ",") + " " + TX_MOTS.mo;
}

function txPluriel(n, un, plusieurs) { return n > 1 ? plusieurs : un; }

function txErreur(r) { if (r && r.erreur) toast(String(r.erreur), "critique"); }

function txDoc(chemin) {
  for (const doc of txDocs) if (doc && doc.chemin === chemin) return doc;
  return { chemin: chemin };
}

/* Chemin du dossier des textes, deduit du champ `sortie` d'une ligne : sans document, il n'y a rien
   a ouvrir, et la page ne connait pas le nom du dossier de sortie (contrat 2.7). */
function txDossierTextes() {
  for (const doc of txDocs) {
    if (!doc || !doc.sortie) continue;
    const sortie = String(doc.sortie).replace(/\\/g, "/");
    const chemin = String(doc.chemin || "").replace(/\\/g, "/");
    const parties = sortie.split("/");
    if (!/^([A-Za-z]:)?\//.test(sortie)) return parties[0] || "";
    const combien = chemin.split("/").filter(Boolean).length;
    return parties.slice(0, Math.max(1, parties.length - combien)).join("/");
  }
  return "";
}

/* ------------------------------------------------------------------ presse-papiers */
async function txCopier(texte) {
  const valeur = String(texte === undefined || texte === null ? "" : texte);
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(valeur);
      return true;
    }
  } catch (e) { /* repli ci-dessous */ }
  try {
    const zone = document.createElement("textarea");
    zone.value = valeur;
    zone.setAttribute("readonly", "readonly");
    zone.style.position = "fixed";
    zone.style.top = "-1000px";
    document.body.append(zone);
    zone.select();
    const ok = document.execCommand ? document.execCommand("copy") : false;
    zone.remove();
    return !!ok;
  } catch (e) { return false; }
}

async function txColler(texte, caracteres) {
  const ok = await txCopier(texte);
  toast(ok ? TX_MOTS.copie.replace("{}", txNombre(caracteres)) : TX_MOTS.copie_ratee, ok ? "bon" : "critique");
}

/* Une portee vide (aucun document, aucun caractere) ne doit ni ecraser le presse-papiers ni
   annoncer une copie reussie (ecart 188, moitie page). */
function txCopieVide(r) {
  return !(Number(r && r.documents) > 0) || !(Number(r && r.caracteres) > 0);
}

/* ------------------------------------------------------------------ en-tete et liste */
function txEntete(etat) {
  const compteurs = (etat && etat.compteurs) || {};
  const documents = compteurs.documents || 0, pages = compteurs.pages || 0;
  const aVerifier = compteurs.a_verifier || 0, lisibles = Math.max(0, documents - aVerifier);
  const ligne = document.querySelector(".tx-compte");
  if (!ligne) return;
  ligne.textContent = txNombre(documents) + " " + txPluriel(documents, TX_MOTS.document, TX_MOTS.documents)
    + ", " + txNombre(pages) + " " + txPluriel(pages, TX_MOTS.page, TX_MOTS.pages)
    + ", " + txVolume(compteurs.octets_texte) + " " + TX_MOTS.de_texte
    + " " + txNombre(lisibles) + " " + txPluriel(lisibles, TX_MOTS.lisible, TX_MOTS.lisibles)
    + ", " + txNombre(aVerifier) + " " + TX_MOTS.a_verifier + ".";
}

function txBadge(doc) {
  const qualite = doc.qualite === "bon" ? "bon" : doc.qualite === "difficile" ? "difficile" : "a-verifier";
  const badge = document.createElement("span");
  badge.className = "badge-qualite " + qualite;
  badge.textContent = qualite === "bon" ? TX_MOTS.bon
    : qualite === "difficile" ? TX_MOTS.difficile : TX_MOTS.a_verifier_badge;
  if (!doc.cherchable) return badge;
  const boite = document.createElement("span");
  boite.className = "tx-badges";
  const cherchable = document.createElement("span");
  cherchable.className = "badge-qualite cherchable";
  cherchable.textContent = TX_MOTS.cherchable;
  boite.append(badge, cherchable);
  return boite;
}

function txLigne(doc) {
  const li = document.createElement("li");
  li.className = "tx-ligne";
  li.setAttribute("data-chemin", String(doc.chemin || ""));
  const tete = document.createElement("div");
  tete.className = "tx-ligne-tete";
  const nom = document.createElement("span");
  nom.className = "tx-nom";
  nom.textContent = String(doc.nom || "");
  tete.append(nom, txBadge(doc));
  const meta = document.createElement("p");
  meta.className = "tx-meta";
  const type = document.createElement("span");
  type.className = "tx-type";
  type.textContent = doc.type === "texte" ? TX_MOTS.texte_natif : TX_MOTS.scanne;
  const pages = document.createElement("span");
  pages.className = "tx-pages";
  const nombre = Number(doc.pages) || 0;
  pages.textContent = txNombre(nombre) + " " + txPluriel(nombre, TX_MOTS.page, TX_MOTS.pages);
  meta.append(type, pages);
  const actions = document.createElement("div");
  actions.className = "tx-ligne-actions";
  const ouvrir = document.createElement("button");
  ouvrir.className = "bouton petit";
  ouvrir.setAttribute("data-tx", "ouvrir");
  ouvrir.textContent = TX_MOTS.ouvrir;
  ouvrir.addEventListener("click", () => txOuvrirChemin(doc));
  const plus = document.createElement("button");
  plus.className = "bouton petit tx-ouvre";
  plus.setAttribute("data-tx", "menu");
  plus.setAttribute("aria-label", TX_MOTS.plus);
  plus.textContent = "…";
  plus.addEventListener("click", () => txMenuLigne(plus, doc));
  actions.append(ouvrir, plus);
  li.append(tete, meta, actions);
  return li;
}

function txListe(docs) {
  const ul = $("#tx-liste");
  if (!ul) return;
  txFermerMenu();
  txVider(ul);
  let cours = null, section = null, groupe = null, lignes = null;
  for (const doc of docs) {
    if (!groupe || doc.cours !== cours || doc.section !== section) {
      cours = doc.cours;
      section = doc.section;
      groupe = document.createElement("li");
      groupe.className = "tx-groupe";
      const titre = document.createElement("p");
      titre.className = "tx-groupe-titre";
      const lieu = document.createElement("span");
      lieu.textContent = String(doc.cours || "");
      const ou = document.createElement("span");
      ou.textContent = String(doc.section || "");
      titre.append(lieu, ou);
      lignes = document.createElement("ul");
      lignes.className = "tx-lignes";
      groupe.append(titre, lignes);
      ul.append(groupe);
    }
    lignes.append(txLigne(doc));
  }
  ul.hidden = !docs.length;
  const vide = $("#tx-vide");
  if (vide) vide.hidden = !!docs.length;
}

/* ------------------------------------------------------------------ menus */
function txMenuCreer(ancre) {
  txFermerMenu();
  const menu = document.createElement("div");
  menu.className = "tx-menu";
  menu.setAttribute("role", "menu");
  ancre.parentNode.append(menu);
  txMenu = menu;
  return menu;
}

function txMenuItem(libelle, action) {
  const bouton = document.createElement("button");
  bouton.setAttribute("role", "menuitem");
  bouton.textContent = libelle;
  bouton.addEventListener("click", () => { txFermerMenu(); action(); });
  return bouton;
}

function txMenuTitre(texte) {
  const titre = document.createElement("p");
  titre.className = "tx-menu-titre";
  titre.textContent = texte;
  return titre;
}

function txFermerMenu() {
  if (txMenu && txMenu.parentNode) txMenu.remove();
  txMenu = null;
}

/* Un clic ailleurs referme le menu ; celui qui l'ouvre est reconnu par sa classe `tx-ouvre`. */
document.addEventListener("click", e => {
  const cible = e.target;
  if (cible && cible.closest && (cible.closest(".tx-menu") || cible.closest(".tx-ouvre"))) return;
  txFermerMenu();
});

function txMenuLigne(ancre, doc) {
  if (ancre.parentNode.querySelector(".tx-menu")) { txFermerMenu(); return; }
  const menu = txMenuCreer(ancre);
  menu.append(txMenuItem(TX_MOTS.copier, () => txCopierDocument(doc)),
              txMenuItem(TX_MOTS.refaire, () => txRefaire(doc)));
}

/* ------------------------------------------------------------------ actions d'une ligne */
async function txOuvrirChemin(doc, page) {
  if (!api()) return;
  const chemin = doc && doc.sortie ? String(doc.sortie) : String((doc && doc.chemin) || "");
  const r = page === undefined ? await api().ocr_ouvrir(chemin) : await api().ocr_ouvrir(chemin, page);
  if (r.erreur) return txErreur(r);
  if (r.source) toast(TX_MOTS.source, "critique");
}

async function txCopierDocument(doc) {
  if (!api()) return;
  const r = await api().ocr_copier("document:" + String(doc.chemin || ""));
  if (r.erreur) return txErreur(r);
  if (r.trop_long) return toast(TX_MOTS.trop_long, "critique");
  if (txCopieVide(r)) return toast(TX_MOTS.rien_a_copier, "critique");
  await txColler(r.texte, r.caracteres);
}

async function txRefaire(doc) {
  if (!api()) return;
  const portee = "document:" + String(doc.chemin || "");
  let r = await api().ocr_lancer(portee, true);
  if (r.erreur) return txErreur(r);
  if (r.confirmer) {
    if (!await confirmer(TX_MOTS.refaire_titre, String(r.confirmer), TX_MOTS.refaire)) return;
    r = await api().ocr_lancer(portee, true, true);
    if (r.erreur) return txErreur(r);
  }
  await txOuvrir();
}

/* ------------------------------------------------------------------ recherche */
function txZoneTrouves() {
  const zone = $("#tx-resultats");
  if (!zone || !zone.parentNode) return null;
  let ul = document.querySelector(".tx-trouves");
  if (!ul) {
    ul = document.createElement("ul");
    ul.className = "tx-trouves";
    zone.parentNode.insertBefore(ul, zone.nextSibling);
  }
  return ul;
}

function txSaisie() {
  const champ = $("#tx-recherche");
  const texte = champ ? String(champ.value || "").trim() : "";
  clearTimeout(txDelai);
  const jeton = ++txJeton;
  if (texte.length < 2) { txAttente = null; txRemettreLaListe(); return; }
  txDelai = setTimeout(() => txChercher(texte, jeton), DELAI_RECHERCHE);
}

function txRemettreLaListe() {
  txVider(txZoneTrouves());
  const zone = $("#tx-resultats");
  if (zone) zone.textContent = "";
  txListe(txDocs);
}

async function txChercher(texte, jeton) {
  if (!api() || jeton !== txJeton) return;
  if (txEnVol) { txAttente = [texte, jeton]; return; }
  txEnVol = true;
  try {
    const r = await api().ocr_chercher(texte);
    if (jeton !== txJeton) return;                    // reponse perimee : ignoree
    if (r.erreur) return txErreur(r);
    txResultats(r);
  } finally {
    txEnVol = false;
    const suite = txAttente;
    txAttente = null;
    if (suite && suite[1] === txJeton) txChercher(suite[0], suite[1]);
  }
}

function txResultats(r) {
  const zone = $("#tx-resultats"), ul = txZoneTrouves();
  const items = Array.isArray(r.resultats) ? r.resultats : [];
  const total = Number(r.total) || 0;
  txVider(ul);
  const liste = $("#tx-liste");
  if (liste) liste.hidden = true;
  const vide = $("#tx-vide");
  if (vide) vide.hidden = true;
  if (zone) {
    zone.textContent = total
      ? txNombre(total) + " " + txPluriel(total, TX_MOTS.resultat, TX_MOTS.resultats)
        + (r.tronque ? TX_MOTS.tronque : "")
      : TX_MOTS.aucun_resultat;
  }
  if (ul) for (const item of items) ul.append(txTrouve(item));
}

function txTrouve(item) {
  const li = document.createElement("li");
  li.className = "tx-trouve";
  const tete = document.createElement("div");
  tete.className = "tx-trouve-tete";
  const lieu = document.createElement("span");
  lieu.className = "tx-lieu";
  lieu.textContent = String(item.cours || "") + " · " + String(item.section || "");
  const nom = document.createElement("span");
  nom.className = "tx-nom";
  nom.textContent = String(item.nom || "");
  const page = document.createElement("span");
  page.className = "tx-page";
  page.textContent = TX_MOTS.page + " " + txNombre(item.page);
  tete.append(lieu, nom, page);
  const extrait = document.createElement("p");
  extrait.className = "tx-extrait";
  const segments = Array.isArray(item.segments) ? item.segments : [];
  let jointure = "";
  for (const segment of segments) {
    const texte = String(segment && segment.t !== undefined && segment.t !== null ? segment.t : "");
    jointure += texte;
    if (segment && segment.m) {
      const marque = document.createElement("mark");
      marque.textContent = texte;
      extrait.append(marque);
    } else {
      extrait.append(document.createTextNode(texte));
    }
  }
  const copier = document.createElement("button");
  copier.className = "bouton petit";
  copier.textContent = TX_MOTS.copier_extrait;
  copier.addEventListener("click", () => txColler(jointure, jointure.length));
  li.addEventListener("click", e => {
    if (e.target && e.target.closest && e.target.closest("button")) return;
    txOuvrirChemin(txDoc(item.chemin), item.page);
  });
  li.append(tete, extrait, copier);
  return li;
}

/* ------------------------------------------------------------------ actions principales */
async function txCopierCours(cours) {
  if (!api()) return;
  const r = await api().ocr_copier("cours:" + String(cours.id));
  if (r.erreur) return txErreur(r);
  if (r.trop_long) return toast(TX_MOTS.trop_long, "critique");
  if (txCopieVide(r)) return toast(TX_MOTS.rien_a_copier, "critique");
  await txColler(r.texte, r.caracteres);
}

function txMenuCours() {
  const ancre = $("#tx-copier-cours");
  if (!ancre) return;
  if (ancre.parentNode.querySelector(".tx-menu")) { txFermerMenu(); return; }
  const menu = txMenuCreer(ancre);
  menu.append(txMenuTitre(TX_MOTS.choisir_cours));
  const cours = typeof SC !== "undefined" && Array.isArray(SC) ? SC.filter(c => c && c.choisi !== false) : [];
  if (!cours.length) {
    const vide = document.createElement("p");
    vide.className = "tx-menu-vide";
    vide.textContent = TX_MOTS.aucun_cours;
    menu.append(vide);
    return;
  }
  for (const c of cours) menu.append(txMenuItem(String(c.dossier || c.nom || ""), () => txCopierCours(c)));
}

async function txExporter(format) {
  if (!api()) return;
  const r = await api().ocr_exporter("tout", format);
  if (r.erreur) return txErreur(r);
  if (r.annule) return;
  const documents = Number(r.documents) || 0;
  toast(TX_MOTS.exporte.replace("{}", txNombre(documents))
    .replace("{}", txPluriel(documents, TX_MOTS.document, TX_MOTS.documents)), "bon");
}

function txMenuExport() {
  const ancre = $("#tx-exporter");
  if (!ancre) return;
  if (ancre.parentNode.querySelector(".tx-menu")) { txFermerMenu(); return; }
  const menu = txMenuCreer(ancre);
  for (const [format, libelle] of [["zip", TX_MOTS.archive], ["zip_jsonl", TX_MOTS.archive_jsonl],
                                   ["md", TX_MOTS.markdown]]) {
    const entree = txMenuItem(libelle, () => txExporter(format));
    if (format === "zip_jsonl") entree.title = TX_MOTS.archive_jsonl_aide;
    menu.append(entree);
  }
}

async function txOuvrirDossier() {
  if (!api()) return;
  const dossier = txDossierTextes();
  if (!dossier) return toast(TX_MOTS.vide, "critique");
  const r = await api().ocr_ouvrir(dossier);
  if (r.erreur) txErreur(r);
}

function txQualite() {
  const dialogue = $("#d-tx-qualite");
  if (!dialogue) return;
  let zone = dialogue.querySelector(".tx-qualite");
  if (!zone) {
    zone = document.createElement("div");
    zone.className = "contenu tx-qualite";
    dialogue.append(zone);
  }
  txVider(zone);
  const souci = txDocs.filter(d => d && (d.qualite === "a_verifier" || d.qualite === "difficile"
    || d.qualite === "vide"));
  if (!souci.length) {
    const rien = document.createElement("p");
    rien.textContent = TX_MOTS.aucun_souci;
    zone.append(rien);
  }
  for (const doc of souci) {
    const ligne = document.createElement("div");
    ligne.className = "tx-qualite-ligne";
    const nom = document.createElement("span");
    nom.className = "tx-nom";
    nom.textContent = String(doc.nom || "");
    const lieu = document.createElement("span");
    lieu.className = "tx-lieu";
    lieu.textContent = String(doc.cours || "") + " · " + String(doc.section || "");
    ligne.append(nom, lieu, txBadge(doc));
    zone.append(ligne);
  }
  dialogue.showModal();
}

/* ------------------------------------------------------------------ chargement de l'onglet */
/* Lit l'etat et la liste : met a jour TX, txDocs et l'en-tete. Ne rend pas la liste. */
async function txCharger() {
  const etat = await api().ocr_etat();
  if (etat && etat.erreur) txErreur(etat);
  else if (etat) { TX = etat; txEntete(etat); txOccupe = !!etat.occupe; }
  const liste = await api().ocr_documents();
  if (liste && liste.erreur) txErreur(liste);
  else if (liste) txDocs = Array.isArray(liste.documents) ? liste.documents : [];
}

/* Vrai quand une recherche occupe l'affichage : la liste est alors masquee derriere elle. */
function txRechercheAffichee() {
  const ul = document.querySelector(".tx-trouves"), zone = $("#tx-resultats");
  return !!((ul && ul.childNodes.length) || (zone && zone.textContent));
}

async function txOuvrir() {
  if (!api()) return;
  barreOccupee(true, TX_MOTS.lecture, "textes");
  txFermerMenu();
  const champ = $("#tx-recherche");
  if (champ && champ.value) {
    champ.value = "";                 // un retour sur l'onglet repart de la liste (decision (5))
    clearTimeout(txDelai); txDelai = 0;
    txJeton++;                        // la requete en vol ou en attente ne s'affichera plus
    txAttente = null;
  }
  txVider(txZoneTrouves());
  const compte = $("#tx-resultats");
  if (compte) compte.textContent = "";
  try {
    await txCharger();
    txListe(txDocs);
  } finally {
    txPret = true;
    if (!txOccupe) barreOccupee(false, "", "textes");
  }
}

/* Fin d'extraction : l'en-tete et la liste sous-jacente suivent, le champ et les resultats
   affiches ne bougent pas (ecart 191). */
async function txRafraichir() {
  if (!api()) return;
  await txCharger();
  if (!txRechercheAffichee()) txListe(txDocs);
}

/* ------------------------------------------------------------------ appels de Python */
window.textesProgres = p => {
  if (!p || typeof p !== "object") return;
  TX = TX || {};
  TX.file = p;
  const etat = String(p.etat || "");
  txOccupe = etat === "en_cours" || etat === "pause" || etat === "pause_sync";
  barreOccupee(txOccupe, "", "textes");
  if (etat === "terminee") txRafraichir();
};

window.textesJournal = t => {
  if (typeof window.syncJournal === "function") window.syncJournal(String(t));
};

/* ------------------------------------------------------------------ branchements */
/* index.html ne porte pas `tx-ouvre` sur les deux boutons a menu (contrat 3.4) : la page la pose
   au branchement, sinon le clic qui ouvre le menu le refermerait aussitot (ecart 187). */
for (const ident of ["#tx-copier-cours", "#tx-exporter"]) {
  const bouton = $(ident);
  if (bouton && bouton.classList) bouton.classList.add("tx-ouvre");
}
$("#tx-recherche").addEventListener("input", txSaisie);
$("#tx-copier-cours").addEventListener("click", txMenuCours);
$("#tx-exporter").addEventListener("click", txMenuExport);
$("#tx-ouvrir-dossier").addEventListener("click", txOuvrirDossier);
$("#tx-qualite").addEventListener("click", txQualite);
