"use strict";
/* Vue « Mes cours » de « Mes textes » (tache R8, contrat 5.4).
   Elle monte l'arbre en mode « voir » (txArbreCreer, contrat 5.3), la phrase d'etat
   (resume_cours), « Tout ouvrir », « Tout fermer » et « Actualiser », et branche les cinq actions
   du menu d'un document sur l'API : ouvrir, afficher, copier (avec le repli de presse-papiers),
   restaurer et reessayer (deux temps : confirmation, puis confirme=True).
   Elle n'appelle l'API que par ses propres fonctions, jamais depuis le composant, et n'ecrit aucun
   HTML : createElement et textContent seulement. Les phrases viennent de TX_MOTS (contrat 5.5). */

/* Les phrases visibles que le tableau 5.5 ne porte pas : le bouton « Actualiser » et les deux
   boutons du dialogue de confirmation. Ecrit au journal de R8 (ecart E-R8-1) : ces trois libelles
   demandent une cle dans TX_MOTS, que cette tache n'a pas le droit d'ajouter (textes.js est a R7). */
const TX_COURS_MOTS = {
  actualiser: "Actualiser",
  annuler: "Annuler",
  confirmer: "Confirmer",
};

let txCoursConteneur = null;   // le conteneur de la vue (#tx-v-cours)
let txCoursArbre = null;       // le composant d'arborescence (contrat 5.3)
let txCoursLu = null;          // le dernier arbre recu de ocr_arbre
let txCoursSuite = null;       // ce qui s'execute si l'etudiant confirme le dialogue ouvert

/* Un element de la vue : sa balise, sa classe, son texte. Rien d'autre. */
function txCoursEl(tag, classe, texte) {
  const el = document.createElement(tag);
  if (classe) el.className = classe;
  if (texte !== undefined && texte !== null) el.appendChild(document.createTextNode(String(texte)));
  return el;
}

/* Une phrase de TX_MOTS, avec ses valeurs nommees. */
function txCoursMot(cle, valeurs) {
  if (typeof txMot !== "function") return "";
  return valeurs === undefined ? txMot(cle) : txMot(cle, valeurs);
}

/* Un bouton de la vue : son action, son libelle, sa variante. */
function txCoursBouton(parent, action, libelle, principale) {
  const bouton = txCoursEl("button", principale ? "bouton principal" : "bouton", libelle);
  bouton.type = "button";
  bouton.setAttribute("data-action", action);
  parent.appendChild(bouton);
  return bouton;
}

/* ------------------------------------------------------------------ presse-papiers */
/* Le repli de l'ancien txCopier : navigator.clipboard d'abord, sinon une zone de texte selectionnee
   et document.execCommand("copy"), qui marche sous pywebview. */
async function txCoursCopier(texte) {
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

/* ------------------------------------------------------------------ phrase de motif */
/* Le composant ne place pas de texte libre sous un document : la vue ajoute la phrase de motif
   (avertissement d'un document a verifier, motif d'un echec) dans la ligne du document. Le
   composant redessine son arbre a chaque ouverture de branche, donc la vue la remet apres chaque
   rendu : c'est un ecart du contrat 5.3, ecrit au journal de R8. */
function txCoursPhraseMotif(noeud) {
  const statut = String((noeud && noeud.statut) || "");
  if (statut === "a_verifier") return txCoursMot("avertissement_a_verifier");
  if (statut !== "echec") return "";
  const cle = "motif_" + String((noeud && noeud.motif) || "erreur");
  const connue = typeof TX_MOTS === "object" && TX_MOTS && TX_MOTS[cle];
  return txCoursMot(connue ? cle : "motif_erreur");
}

function txCoursMotifs() {
  if (!txCoursConteneur || !txCoursLu) return;
  const parChemin = {};
  const ranger = noeud => {
    if (!noeud) return;
    parChemin[String(noeud.chemin || "")] = noeud;
    for (const enfant of (noeud.enfants || [])) ranger(enfant);
  };
  for (const cours of (txCoursLu.cours || [])) ranger(cours);
  const lignes = txCoursConteneur.querySelectorAll(".tx-cours-arbre .tx-fichier");
  for (const li of lignes) {
    const ligne = li.querySelector(".tx-ligne");
    if (!ligne) continue;
    const ancien = ligne.querySelector(".tx-cours-motif");
    if (ancien && ancien.parentNode) ancien.parentNode.removeChild(ancien);
    const noeud = parChemin[String(li.getAttribute("data-chemin") || "")];
    const phrase = txCoursPhraseMotif(noeud);
    if (!phrase) continue;
    ligne.appendChild(txCoursEl("span", "tx-cours-motif", phrase));
  }
}

/* ------------------------------------------------------------------ dialogue de confirmation */
/* Les deux temps des contrats 3.3 et 4.4 : l'API rend {confirmer}, la vue demande, puis rappelle
   avec confirme=True. Le dialogue vit dans le conteneur de la vue, pas dans index.html. */
function txCoursDemander(phrase, suite) {
  const boite = $("#d-tx-cours-confirmer");
  if (!boite) return null;
  txCoursSuite = typeof suite === "function" ? suite : null;
  const texte = boite.querySelector(".tx-cours-dialogue-texte");
  if (texte) texte.textContent = String(phrase === undefined || phrase === null ? "" : phrase);
  if (typeof boite.showModal === "function") boite.showModal();
  else boite.open = true;
  const premier = boite.querySelector('[data-action="confirmer"]');
  if (premier && typeof premier.focus === "function") premier.focus();
  return boite;
}

/* Reponse de l'etudiant : la suite ne s'execute qu'au clic sur Confirmer. */
function txCoursFermer(confirme) {
  const boite = $("#d-tx-cours-confirmer");
  const suite = txCoursSuite;
  txCoursSuite = null;
  if (boite) {
    if (typeof boite.close === "function") boite.close();
    boite.open = false;
  }
  if (confirme && typeof suite === "function") return suite();
  return null;
}

/* ------------------------------------------------------------------ les cinq actions */
/* Restauration confirmee (contrat 3.3) : le PDF d'origine revient, la vue relit tout. */
async function txCoursRestaurer(chemin) {
  if (!api()) return null;
  const r = await api().ocr_restaurer(chemin, true);
  if (txErreur(r) || !r || !r.ok) return r;
  /* La phrase de `message` dit qu'un texte edite a la main est reste en place (contrat 3.3,
     invariant 3, ecart E-V6-2) : sans elle, l'etudiant croirait son texte supprime. */
  if (r.message) toast(String(r.message), "bon");
  await txRafraichir();
  return r;
}

/* Nouvel essai confirme (contrat 4.4, parametre refaire) : le document repart en file. */
async function txCoursRetenter(chemin) {
  if (!api()) return null;
  const r = await api().ocr_traiter([chemin], true, true);
  if (!txErreur(r) && r) await txRafraichir();
  return r;
}

/* Une action du menu d'un document (contrat 5.4) : la bonne methode, le chemin du document. */
async function txCoursAction(action, noeud) {
  if (!noeud || !api()) return null;
  const chemin = String(noeud.chemin || "");
  if (!chemin) return null;
  let r = null;
  if (action === "ouvrir") {
    r = await api().ocr_ouvrir(chemin);
    txErreur(r);
    return r;
  }
  if (action === "afficher") {
    r = await api().ocr_afficher(chemin);
    txErreur(r);
    return r;
  }
  if (action === "copier") {
    r = await api().ocr_copier_texte(chemin);
    if (!txErreur(r)) await txCoursCopier(r && r.texte);
    return r;
  }
  if (action === "restaurer") {
    r = await api().ocr_restaurer(chemin);
    if (txErreur(r)) return r;
    if (r && r.confirmer) txCoursDemander(r.confirmer, () => txCoursRestaurer(chemin));
    return r;
  }
  if (action === "reessayer") {
    r = await api().ocr_traiter([chemin], true);
    if (txErreur(r)) return r;
    if (r && !r.rien && r.confirmer) txCoursDemander(r.confirmer, () => txCoursRetenter(chemin));
    return r;
  }
  return null;
}

/* ------------------------------------------------------------------ rendu */
/* L'etat partage de la coque (contrat 5.2) : TX.arbre porte la reponse de ocr_arbre. */
function txCoursRafraichir(tx) {
  const partage = tx && typeof tx === "object" ? tx : TX;
  const arbre = partage && partage.arbre ? partage.arbre : null;
  const lu = !!arbre;
  const cours = Array.isArray(arbre && arbre.cours) ? arbre.cours : [];
  const videArbre = lu && cours.length === 0;
  txCoursLu = lu ? arbre : null;

  const listes = $("#tx-cours-arbre");
  const vide = $("#tx-cours-vide");
  const resume = $("#tx-cours-resume");
  const actions = $("#tx-cours-actions");
  const ouvrir = actions ? actions.querySelector('[data-action="tout-ouvrir"]') : null;
  const fermer = actions ? actions.querySelector('[data-action="tout-fermer"]') : null;

  if (listes) listes.hidden = !lu || videArbre;
  if (vide) vide.hidden = !videArbre;
  for (const bouton of [ouvrir, fermer]) {
    if (!bouton) continue;
    bouton.hidden = videArbre;
    bouton.disabled = !lu || videArbre;
  }
  if (resume) {
    resume.hidden = !lu || videArbre;
    const compteurs = (arbre && arbre.compteurs) || {};
    resume.textContent = lu && !videArbre
      ? txCoursMot("resume_cours", { t: txNombre(compteurs.traites), v: txNombre(compteurs.a_verifier),
                                     e: txNombre(compteurs.echecs) })
      : "";
  }
  if (!txCoursArbre) return null;
  if (!lu || videArbre) {
    txCoursArbre.vider();
    return null;
  }
  txCoursArbre.charger(arbre);
  txCoursMotifs();
  return null;
}

/* ------------------------------------------------------------------ clics */
/* Les clics de la vue passent tous par ici : les boutons de la vue, la confirmation, et, apres le
   composant, la remise des phrases de motif (il redessine alors son arbre). */
function txCoursClic(e) {
  const cible = e && e.target;
  if (!cible || !cible.closest) return null;
  const bouton = cible.closest("[data-action]");
  if (bouton) {
    const action = bouton.getAttribute("data-action");
    if (action === "tout-ouvrir") {
      if (txCoursArbre) txCoursArbre.ouvrirTout();
      txCoursMotifs();
      return null;
    }
    if (action === "tout-fermer") {
      if (txCoursArbre) txCoursArbre.fermerTout();
      txCoursMotifs();
      return null;
    }
    if (action === "actualiser") return txRafraichir();
    if (action === "aller-choisir") {
      if (e.preventDefault) e.preventDefault();
      if (typeof txMontrerVue === "function") txMontrerVue("choisir");
      return null;
    }
    if (action === "annuler") return txCoursFermer(false);
    if (action === "confirmer") return txCoursFermer(true);
  }
  txCoursMotifs();
  return null;
}

/* ------------------------------------------------------------------ montage */
/* La coque appelle init une seule fois, avec le conteneur du panneau (contrat 5.2). */
function txCoursMonter(conteneur) {
  if (!conteneur) return null;
  txCoursConteneur = conteneur;
  while (conteneur.firstChild) conteneur.removeChild(conteneur.firstChild);

  const entete = txCoursEl("div", "tx-cours-entete");
  entete.id = "tx-cours-entete";
  const resume = txCoursEl("p", "tx-cours-resume");
  resume.id = "tx-cours-resume";
  resume.hidden = true;
  entete.appendChild(resume);

  const actions = txCoursEl("div", "tx-cours-actions");
  actions.id = "tx-cours-actions";
  const ouvrir = txCoursBouton(actions, "tout-ouvrir", txCoursMot("tout_ouvrir"));
  const fermer = txCoursBouton(actions, "tout-fermer", txCoursMot("tout_fermer"));
  txCoursBouton(actions, "actualiser", TX_COURS_MOTS.actualiser);
  ouvrir.disabled = true;
  fermer.disabled = true;
  entete.appendChild(actions);
  conteneur.appendChild(entete);

  const listes = txCoursEl("div", "tx-cours-arbre");
  listes.id = "tx-cours-arbre";
  listes.hidden = true;
  conteneur.appendChild(listes);

  const vide = txCoursEl("div", "tx-cours-vide");
  vide.id = "tx-cours-vide";
  vide.hidden = true;
  vide.appendChild(txCoursEl("p", "tx-cours-texte", txCoursMot("etat_vide")));
  const lien = txCoursEl("a", "tx-cours-lien", txCoursMot("onglet_choisir"));
  lien.setAttribute("href", "#tx-o-choisir");
  lien.setAttribute("data-action", "aller-choisir");
  vide.appendChild(lien);
  conteneur.appendChild(vide);

  const boite = document.createElement("dialog");
  boite.className = "dialogue";
  boite.id = "d-tx-cours-confirmer";
  boite.setAttribute("aria-labelledby", "tx-cours-dialogue-texte");
  const texte = txCoursEl("p", "tx-cours-dialogue-texte");
  texte.id = "tx-cours-dialogue-texte";
  boite.appendChild(texte);
  const choix = txCoursEl("div", "actions");
  txCoursBouton(choix, "annuler", TX_COURS_MOTS.annuler);
  txCoursBouton(choix, "confirmer", TX_COURS_MOTS.confirmer, true);
  boite.appendChild(choix);
  conteneur.appendChild(boite);

  txCoursArbre = typeof txArbreCreer === "function"
    ? txArbreCreer(listes, { mode: "voir", onAction: txCoursAction })
    : null;
  conteneur.addEventListener("click", txCoursClic);
  conteneur.addEventListener("keydown", () => { txCoursMotifs(); });
  return null;
}

/* Globale du contrat 5.2 : la coque lit txVueCours et appelle ces quatre methodes. */
const txVueCours = {
  init(conteneur) {
    return txCoursMonter(conteneur);
  },
  rafraichir(tx) {
    return txCoursRafraichir(tx);
  },
  activer() {
    txCoursMotifs();
    return null;
  },
  desactiver() {
    if (txCoursSuite) txCoursFermer(false);
    return null;
  },
};
