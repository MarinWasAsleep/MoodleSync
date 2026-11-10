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
let txMenuAncre = null;        // bouton qui l'a ouvert : le focus y revient (ecart 195)

const DELAI_RECHERCHE = 300;   // plan 3.5 : un delai de 300 ms avant de chercher

/* Phrases de l'onglet. Plan 3.5, contrat 3.4 et 5 ; les autres sont declarees dans le test
   (PHRASES_NOUVELLES) et soumises a Maxence. {} marque une valeur intercalee. Les cles quoi_* sont
   celles du panneau « A quoi ca sert ? » (U3) : quoi_essayer et quoi_exemple_bouton sont les deux
   libelles du bouton d'essai, ecrits tels quels au plan 3.6. */
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
  restaurer: "Restaurer l'original",
  restaurer_titre: "Restaurer l'original ?",
  restaurer_texte: "MoodleSync va retélécharger l'original depuis Moodle et remplacer le fichier modifié (le PDF cherchable) par cet original. Il faut être connecté à Moodle.",
  restaure: "Original restauré.",
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
  quoi_essayer: "Essayer sur une page de mon cours",
  quoi_exemple_bouton: "Voir un exemple",
  quoi_exemple: "Exemple, pas un de tes documents.",
  quoi_images: "Des images :",
  quoi_texte: "Du texte :",
  quoi_lecture: "Lecture de la page...",
  quoi_confiance: "Confiance :",
  quoi_aucun_texte: "Aucun texte reconnu sur cette page.",
  quoi_alt: "Aperçu de la page {} de {}.",
  quoi_alt_exemple: "Exemple de page scannée.",
  quoi_exemple_texte: "Une institution est un ensemble de règles qui dure dans le temps.",
  carte_environ: "environ",
  carte_moteur_absent: "Le moteur d'extraction n'est pas encore installé.",
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
  plus.setAttribute("aria-haspopup", "menu");
  plus.setAttribute("aria-expanded", "false");
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
/* Ecart 195 : un menu prend le focus, annonce son etat par aria-expanded, se ferme a Escape, et le
   focus revient alors au bouton qui l'a ouvert. */
function txMenuCreer(ancre) {
  txFermerMenu();
  const menu = document.createElement("div");
  menu.className = "tx-menu";
  menu.setAttribute("role", "menu");
  ancre.parentNode.append(menu);
  txMenu = menu;
  txMenuAncre = ancre || null;
  if (ancre && ancre.setAttribute) {
    ancre.setAttribute("aria-haspopup", "menu");
    ancre.setAttribute("aria-expanded", "true");
  }
  return menu;
}

/* Le focus entre dans le menu une fois ses entrees posees. */
function txMenuFocus(menu) {
  const premier = menu && menu.querySelector("button");
  if (premier && premier.focus) premier.focus();
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
  const ancre = txMenuAncre;
  txMenuAncre = null;
  if (txMenu && txMenu.parentNode) txMenu.remove();
  txMenu = null;
  if (ancre && ancre.setAttribute) ancre.setAttribute("aria-expanded", "false");
  return ancre;
}

/* Ecart 195 : Escape ferme le menu ouvert et rend le focus a son bouton. */
document.addEventListener("keydown", e => {
  if (e.key !== "Escape" || !txMenu) return;
  const ancre = txFermerMenu();
  if (ancre && ancre.focus) ancre.focus();
});

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
  if (doc.cherchable) menu.append(txMenuItem(TX_MOTS.restaurer, () => txRestaurer(doc)));   // ecart 294
  txMenuFocus(menu);
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

/* Ecart 294, critere 12 : « Restaurer l'original » d'un PDF cherchable. La confirmation dit ce que fait le
   bouton avant tout appel ; si le fichier a ete modifie a la main, l'API le dit et une seconde confirmation
   (sa phrase, telle quelle) precede le rappel avec confirme=true. Original injoignable : la phrase de l'API
   en toast, le PDF cherchable reste en place. */
async function txRestaurer(doc) {
  if (!api()) return;
  const chemin = String((doc && doc.chemin) || "");
  if (!await confirmer(TX_MOTS.restaurer_titre, TX_MOTS.restaurer_texte, TX_MOTS.restaurer)) return;
  let r = await api().ocr_pdf_restaurer(chemin);
  if (r && r.confirmer) {
    if (!await confirmer(TX_MOTS.restaurer_titre, String(r.confirmer), TX_MOTS.restaurer)) return;
    r = await api().ocr_pdf_restaurer(chemin, true);
  }
  if (!r || r.erreur) return txErreur(r);
  toast(TX_MOTS.restaure);
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
  /* Ecart 195 : la ligne s'ouvre au clavier, comme les lectures de Ma semaine (role et tabindex). */
  li.setAttribute("role", "button");
  li.tabIndex = 0;
  li.addEventListener("keydown", e => {
    /* Ecart 232 : le bouton « Copier l'extrait » est dans la ligne ; sa touche lui appartient. */
    if (e.target !== li) return;
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    txOuvrirChemin(txDoc(item.chemin), item.page);
  });
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
  txMenuFocus(menu);
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
  txMenuFocus(menu);
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

/* ------------------------------------------------------------------ panneau « A quoi ca sert ? » (U3) */
/* Les phrases fixes du plan 3.6 sont ecrites dans index.html (#d-tx-quoi). Ici : les chiffres de la
   bibliotheque, l'essai sur une page (ocr_apercu) et son affichage. L'apercu ne s'ecrit nulle part et
   ne met rien en file : il reste en memoire (txQuoiApercu) et disparait a la fermeture du panneau. */
let txQuoiApercu = null;       // derniere reponse affichee de ocr_apercu
let txQuoiJeton = 0;           // une reponse qui arrive apres la fermeture ne s'affiche pas
let txQuoiEnCours = false;     // une seule lecture de page a la fois
let txQuoiOrigine = null;      // element qui a ouvert le panneau : le focus y revient
let txQuoiLibelle = "";        // libelle du bouton d'essai hors lecture
let txQuoiDefauts = null;      // phrases d'exemple du plan, ecrites dans index.html

function txQuoi(selecteur) {
  const dialogue = $("#d-tx-quoi");
  return dialogue ? dialogue.querySelector(selecteur) : null;
}

/* Bloc 1 : les chiffres de la bibliotheque quand ils sont connus, sinon l'exemple du plan, annonce. */
function txQuoiChiffres(etat) {
  const avant = txQuoi(".tx-quoi-avant-chiffres"), apres = txQuoi(".tx-quoi-apres-chiffres");
  const note = txQuoi(".tx-quoi-note-chiffres");
  if (!avant || !apres) return;
  if (!txQuoiDefauts) txQuoiDefauts = { avant: avant.textContent, apres: apres.textContent };
  const compteurs = (etat && etat.compteurs) || {};
  const pages = Number(compteurs.pages) || 0;
  const unite = txNombre(pages) + " " + txPluriel(pages, TX_MOTS.page, TX_MOTS.pages);
  if (pages > 0) {
    avant.textContent = TX_MOTS.quoi_images + " " + unite;
    apres.textContent = TX_MOTS.quoi_texte + " " + unite + ", " + txVolume(compteurs.octets_texte);
  } else {
    avant.textContent = txQuoiDefauts.avant;
    apres.textContent = txQuoiDefauts.apres;
  }
  if (note) {
    note.textContent = TX_MOTS.quoi_exemple;
    note.hidden = pages > 0;
  }
}

/* L'essai porte sur un vrai scan seulement si le moteur est la et que la bibliotheque en a. */
function txQuoiEssaiPossible(etat) {
  const compteurs = (etat && etat.compteurs) || {};
  const moteur = etat && etat.moteur;
  return !!(moteur && moteur.present && ((Number(compteurs.documents) || 0) > 0
    || (Number(compteurs.a_preparer) || 0) > 0));
}

/* Efface l'apercu et invalide toute reponse encore attendue. */
function txQuoiRaz() {
  txQuoiJeton++;
  txQuoiApercu = null;
  txQuoiEnCours = false;
  const zone = txQuoi(".tx-quoi-apercu");
  if (zone) zone.hidden = true;
  const image = txQuoi(".tx-quoi-image");
  if (image) { image.removeAttribute("src"); image.setAttribute("alt", ""); image.hidden = true; }
  const modele = txQuoi(".tx-quoi-modele");
  if (modele) modele.hidden = true;
  const texte = txQuoi(".tx-quoi-texte");
  if (texte) texte.textContent = "";
  const confiance = txQuoi(".tx-quoi-confiance");
  if (confiance) { confiance.textContent = ""; confiance.hidden = true; }
  const bouton = txQuoi(".tx-quoi-essai");
  if (bouton) { bouton.disabled = false; if (txQuoiLibelle) bouton.textContent = txQuoiLibelle; }
}

async function txQuoiOuvrir(origine) {
  const dialogue = $("#d-tx-quoi");
  if (!dialogue || dialogue.open) return;
  let etat = TX && TX.compteurs ? TX : null;     // TX n'a que `file` tant qu'aucun ocr_etat n'est arrive
  if (!etat && api()) {                          // lu ici, sans toucher TX : l'onglet Mes textes le tient
    const lu = await api().ocr_etat();
    if (lu && lu.erreur) txErreur(lu); else etat = lu;
    if (dialogue.open) return;
  }
  txQuoiRaz();
  txQuoiOrigine = origine || null;
  txQuoiChiffres(etat);
  txQuoiLibelle = txQuoiEssaiPossible(etat) ? TX_MOTS.quoi_essayer : TX_MOTS.quoi_exemple_bouton;
  const essai = txQuoi(".tx-quoi-essai");
  if (essai) essai.textContent = txQuoiLibelle;
  dialogue.showModal();
  if (essai) essai.focus();
}

/* Affiche la reponse de ocr_apercu. Tout texte de l'API passe par textContent ou setAttribute. */
function txQuoiMontrer(r) {
  const zone = txQuoi(".tx-quoi-apercu");
  if (!zone) return;
  const exemple = !!r.exemple;
  zone.hidden = false;
  const note = txQuoi(".tx-quoi-note-apercu");
  if (note) { note.textContent = TX_MOTS.quoi_exemple; note.hidden = !exemple; }
  const image = txQuoi(".tx-quoi-image"), modele = txQuoi(".tx-quoi-modele");
  const texte = txQuoi(".tx-quoi-texte"), confiance = txQuoi(".tx-quoi-confiance");
  if (exemple) {
    image.removeAttribute("src");
    image.hidden = true;
    modele.setAttribute("aria-label", TX_MOTS.quoi_alt_exemple);
    modele.hidden = false;
    texte.textContent = TX_MOTS.quoi_exemple_texte;
  } else {
    modele.hidden = true;
    image.hidden = !r.image;
    if (r.image) {
      image.setAttribute("src", String(r.image));
      image.setAttribute("alt", TX_MOTS.quoi_alt.replace("{}", () => txNombre(r.page))
        .replace("{}", () => String(r.nom || "")));
    }
    texte.textContent = String(r.texte || "").trim() ? String(r.texte) : TX_MOTS.quoi_aucun_texte;
  }
  confiance.textContent = "";
  const niveau = typeof r.confiance === "number" ? Math.min(1, Math.max(0, r.confiance)) : null;
  confiance.hidden = exemple || niveau === null;
  if (!confiance.hidden) {                       // le mot est ecrit a cote du nombre : jamais la couleur seule
    const mesure = document.createElement("span");
    mesure.textContent = TX_MOTS.quoi_confiance + " " + Math.round(niveau * 100) + " % ";
    confiance.append(mesure, txBadge({ qualite: r.qualite, cherchable: false }));
  }
  const copier = txQuoi(".tx-quoi-copier"), preparer = txQuoi(".tx-quoi-preparer");
  if (copier) copier.hidden = exemple;
  if (preparer) preparer.hidden = typeof txPreparer !== "function";
}

async function txQuoiEssayer() {
  if (txQuoiEnCours || !api()) return;
  const bouton = txQuoi(".tx-quoi-essai");
  txQuoiRaz();
  const jeton = txQuoiJeton;
  txQuoiEnCours = true;
  if (bouton) { bouton.disabled = true; bouton.textContent = TX_MOTS.quoi_lecture; }
  try {
    const r = await api().ocr_apercu();
    if (jeton !== txQuoiJeton) return;            // le panneau a ete ferme ou relance entre-temps
    if (!r || r.erreur) return txErreur(r);
    txQuoiApercu = r;
    txQuoiMontrer(r);
  } finally {
    if (jeton === txQuoiJeton) {
      txQuoiEnCours = false;
      if (bouton) { bouton.disabled = false; bouton.textContent = txQuoiLibelle; }
    }
  }
}

async function txQuoiCopier() {
  const r = txQuoiApercu;
  const texte = r && !r.exemple ? String(r.texte || "") : "";
  if (!texte.trim()) return toast(TX_MOTS.rien_a_copier, "critique");
  await txColler(texte, texte.length);
}

/* « Preparer tout le cours » : consentement, duree et lancement sont a U4 (txPreparer). Le panneau
   transmet l'element qui l'a ouvert : le focus revient la a la fermeture du consentement (ecart 222). */
function txQuoiPreparer() {
  if (typeof txPreparer === "function") txPreparer(txQuoiOrigine || document.activeElement);
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
  if (typeof txCarteProgres === "function") txCarteProgres(p);   // carte de preparation (sync.js, U4)
};

/* Progression du telechargement du moteur (ecart 245) : {recu, total} en octets, au plus quatre fois par seconde. */
window.textesInstallation = p => {
  if (p && typeof p === "object" && typeof txCarteInstallation === "function") txCarteInstallation(p);   // sync.js
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

/* Panneau « A quoi ca sert ? » (U3). Le lien #tx-quoi de la carte (Ma semaine) n'est branche ici que
   pour l'ouverture : U4 branche le reste de la carte et ne doit pas doubler cet ecouteur. */
const txQuoiLiens = [$("#tx-quoi")].concat(Array.from(document.querySelectorAll('[data-action="quoi"]')));
for (const lien of txQuoiLiens) {
  if (lien) lien.addEventListener("click", () => txQuoiOuvrir(lien));
}
const txQuoiDialogue = $("#d-tx-quoi");
if (txQuoiDialogue) {
  txQuoiDialogue.addEventListener("close", () => {
    txQuoiRaz();
    const origine = txQuoiOrigine;
    txQuoiOrigine = null;
    if (origine && origine.focus) origine.focus();
  });
  txQuoiDialogue.addEventListener("click", e => {
    const bouton = e.target && e.target.closest ? e.target.closest("[data-quoi]") : null;
    if (!bouton) return;
    const action = bouton.getAttribute("data-quoi");
    if (action === "essai") txQuoiEssayer();
    else if (action === "copier") txQuoiCopier();
    else if (action === "preparer") txQuoiPreparer();
  });
}
