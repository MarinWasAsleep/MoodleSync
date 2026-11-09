"use strict";
/* Onglet Synchroniser : adresse du Moodle, connexion, dossier, cours, options, telechargement.
   Reprend, fonction par fonction, l'ancienne fenetre tkinter de MoodleSync. Utilise commun.js. */
let SE = null;                     // reglages de la synchronisation (api().sync_etat)
let SC = [];                       // lignes de la liste des cours
let sOccupe = false, sConnecte = false, syncPrete = false, dernierResultat = null;

/* =====================================================================  journal, statut, progression */
window.syncJournal = t => {
  const j = $("#s-journal"); if (!j) return;
  const bas = j.scrollHeight - j.scrollTop - j.clientHeight < 30;
  j.append(document.createTextNode(t + "\n"));
  if (bas) j.scrollTop = j.scrollHeight;
};
window.syncProgres = p => {
  const n = Math.max(p.n || 1, 1), pct = Math.round(100 * (p.i || 0) / n);
  $("#s-barre").value = pct; $("#s-pct").textContent = `${pct} %`;
  if (p.texte) syncJournal(`[${p.i}/${p.n}] ${p.texte}`);
};
function sStatut(texte, ok) {
  for (const el of document.querySelectorAll(".s-statut")) {
    el.textContent = texte;
    el.classList.toggle("ok", ok === true); el.classList.toggle("ko", ok === false);
  }
}
function sBandeau(texte) {
  $("#s-bandeau").innerHTML = texte ? `<div class="bandeau" role="alert">${ic("alerte")}<span class="texte">${esc(texte)}</span></div>` : "";
}
function sOccuper(o, texte) {
  sOccupe = o;
  barreOccupee(o, texte, "sync");
  for (const id of ["#s-lancer", "#s-connecter", "#a-connecter", "#s-appliquer", "#a-suite-co"]) { const b = $(id); if (b) b.disabled = o; }
  if (!o) $("#s-annuler").disabled = true;
}
function sErreur(r, statut = true) {
  sBandeau(r.erreur); toast(r.erreur, "critique");
  if (statut) sStatut(r.erreur.split("\n")[0].length <= 80 ? r.erreur.split("\n")[0] : "Impossible, voir le message", false);
}

/* =====================================================================  rendu */
function rendreSync() {
  if (!SE) return;
  $("#s-accueil").hidden = !SE.accueil; $("#s-principal").hidden = SE.accueil;
  for (const id of ["#s-site", "#a-site"]) if (document.activeElement !== $(id)) $(id).value = SE.site || "";
  if (document.activeElement !== $("#s-dest")) $("#s-dest").value = SE.dest;
  $("#a-dest").textContent = SE.dest;
  const options = SE.langues.map(l => `<option value="${esc(l.code)}" ${l.code === SE.langue ? "selected" : ""}>${esc(l.nom)}</option>`).join("");
  $("#s-langue").innerHTML = options; $("#a-langue").innerHTML = options;
  $("#s-statuts").checked = SE.statuts; $("#t-statuts").textContent = SE.textes.statuts;
  $("#s-note").checked = SE.note; $("#t-note").textContent = SE.textes.note;
  $("#s-auto").checked = SE.auto;
  $("#s-youtube").checked = SE.titres_youtube;
  rendreCours();
}
function rendreCours() {
  const l = $("#s-cours");
  if (!SC.length) {
    l.innerHTML = `<li class="rien">${sConnecte ? "Aucun cours trouvé sur ce Moodle." : "Connecte-toi pour voir tes cours."}</li>`;
    return;
  }
  l.innerHTML = SC.map(c => `<li class="ligne-cours" data-cid="${c.id}">
      <label class="case" title="Suivre ce cours"><input type="checkbox" ${c.choisi ? "checked" : ""} aria-label="Suivre : ${esc(c.dossier)}">
        <span class="boite"><svg viewBox="0 0 24 24"><path d="M5 12.5 10 17 19 7"/></svg></span></label>
      <div class="c-nom"><span class="c-dossier">${esc(c.dossier)}</span><small title="${esc(c.nom)}">${esc(c.nom)}</small></div>
      <span class="puce nouveau" ${c.nouveaux ? "" : 'style="visibility:hidden" aria-hidden="true"'}>${c.nouveaux} nouveau${c.nouveaux > 1 ? "x" : ""}</span>
      <span class="c-nb">${c.nb} fichier${c.nb !== 1 ? "s" : ""}</span>
      <span class="c-taille">${esc(c.taille_txt)}</span>
      <button class="bouton icone c-renommer" title="Renommer le dossier de ce cours" aria-label="Renommer le dossier : ${esc(c.dossier)}">${ic("crayon")}</button>
    </li>`).join("");
}
function appliquerListe(r) {
  sStatut(r.statut.texte, r.statut.ok);
  sConnecte = !!r.connecte;
  $("#s-connecter").textContent = sConnecte || SE?.jeton ? "Se reconnecter" : "Se connecter à Moodle";
  if (r.cours) {
    SC = r.cours; $("#s-total").textContent = r.total;
    syncJournal(`${SC.length} cours trouvés, ${r.taille_totale} au total.`);
    if (r.nouveaux) syncJournal(`${r.nouveaux} fichiers nouveaux ou republiés sur Moodle dans les cours cochés (indiqués à côté de chaque cours).`);
  }
  // accueil : etape 1 franchie
  $("#a-etape1").classList.toggle("faite", sConnecte);
  $("#a-titre1").textContent = sConnecte ? `Connecté : ${r.nom || "statut inconnu"}` : "Se connecter à Moodle";
  $("#a-connecter").textContent = sConnecte ? "Connecté" : "Se connecter";
  $("#a-connecter").disabled = sConnecte;
  $("#a-suite").disabled = !sConnecte;
  $("#a-semaine").disabled = !sConnecte;
  rendreCours();
}

/* =====================================================================  actions */
async function sDemarrer() {
  SE = await api().sync_etat();
  if (SE.erreur) { sErreur(SE); SE = null; syncPrete = true; return; }
  rendreSync();
  txCarteCharger();                  // la carte de preparation lit l'etat, sans rien lancer (U4)
  if (SE.jeton) await sVerifier();
  else { sStatut("Non connecté", false); syncPrete = true; }
  if (INFOS.verif_action === "synchroniser" && sConnecte) await sLancer(true);
  syncPrete = true;
}
async function sVerifier() {
  sStatut("Vérification de la session...", null);
  const r = await api().sync_verifier();
  if (r.erreur) return sErreur(r);
  if (r.expiree) SE.jeton = false;
  appliquerListe(r);
  if (r.connecte) activerMaSemaineAuto();
}
async function sAppliquerSite(texte) {
  if (sOccupe) return false;
  sOccuper(true, "Vérification de l'adresse...");
  let r = await api().sync_site(texte, false);
  sOccuper(false);
  if (r.confirmer) {
    if (!await confirmer("Changer de Moodle", r.confirmer, "Changer")) { rendreSync(); return false; }
    sOccuper(true, "Vérification de l'adresse...");
    r = await api().sync_site(texte, true);
    sOccuper(false);
  }
  if (r.erreur) { sErreur(r); rendreSync(); return false; }
  if (r.inchange) { $("#s-site").value = $("#a-site").value = r.site; return true; }
  SE = r.etat; SC = []; sConnecte = false; rendreSync();
  sStatut("Non connecté", false); sBandeau("");
  $("#s-total").textContent = "";
  appliquerListe({statut: {texte: "Non connecté", ok: false}, connecte: false});
  syncJournal(`Moodle : ${r.site}`);
  return true;
}
async function sConnecter(depuis) {
  if (sOccupe) return;
  const texte = (depuis === "accueil" ? $("#a-site") : $("#s-site")).value;
  if (!await sAppliquerSite(texte)) return;
  sOccuper(true, "Connexion en cours. Termine-la dans la fenêtre du navigateur.");
  sStatut(`Connexion en cours : termine-la dans ${INFOS.navigateurs}.`, null);
  sBandeau("");
  const r = await api().sync_connecter();
  sOccuper(false);
  if (r.erreur) return sErreur(r);
  SE.jeton = true;
  appliquerListe(r);
  activerMaSemaineAuto();
}
async function sLancer(auto = false) {
  if (sOccupe) return;
  const debut = () => {
    sOccuper(true, "Téléchargement en cours...");
    $("#s-annuler").disabled = false;
    $("#s-barre").value = 0; $("#s-pct").textContent = "0 %";
    sStatut("Téléchargement en cours...", null); sBandeau("");
  };
  debut();
  // Sans confirmation a demander, cet appel fait toute la synchronisation (jusqu'a son compte rendu).
  let r = await api().sync_lancer(auto);
  if (r.confirmer) {
    sOccuper(false); sStatut(sConnecte ? "Connecté" : "Non connecté", sConnecte ? true : false);
    if (!await confirmer("Dossier de rangement", r.confirmer, "Créer le dossier")) return;
    debut();
    r = await api().sync_lancer(true);
  }
  sOccuper(false);
  if (r.erreur) return sErreur(r);
  if (r.annule_avant) { sStatut("Annulé avant le téléchargement.", null); dernierResultat = {annule_avant: true}; return; }
  termine(r.resultat, r.cours);
}
function termine(r, cours) {
  dernierResultat = r;
  if (cours) { SC = cours; rendreCours(); }
  $("#s-barre").value = r.annule ? $("#s-barre").value : 100; if (!r.annule) $("#s-pct").textContent = "100 %";
  if (r.annule) sStatut(`Annulé : ${r.neufs} nouveaux fichiers rangés avant l'arrêt.`, null);
  else sStatut(`Terminé : ${r.neufs} nouveaux fichiers, ${r.maj} mis à jour.`, true);
  syncJournal("");
  if (r.annule) syncJournal("Synchronisation annulée. Les fichiers déjà téléchargés restent rangés ; le reste viendra à la prochaine synchronisation.");
  for (const l of r.lignes) syncJournal(`  ${l}`);
  syncJournal(`Nouveaux : ${r.neufs}`);
  syncJournal(`Mis à jour (ancienne version conservée) : ${r.maj}`);
  syncJournal(`Nouveaux liens : ${r.liens} (dans « ${r.fichier_liens} » de chaque section)`);
  syncJournal(`Déjà présents, ignorés : ${r.doublons}`);
  if (r.erreurs) syncJournal(`Échecs : ${r.erreurs}`);
  syncJournal(`Rangement : ${r.dest}`);
  if (r.note) syncJournal(`Liste des nouveautés : ${r.note}`);
  if (!r.annule && (r.neufs || r.maj || r.liens) && INFOS.verif_action !== "synchroniser")
    informer("Synchronisation terminée", `${r.neufs} nouveaux fichiers, ${r.maj} mis à jour et ${r.liens} nouveaux liens, rangés dans\n${r.dest}`
      + (r.lignes.length ? "\n\n" + r.lignes.slice(0, 8).join("\n") : ""));
  txCarteCharger();                  // de nouveaux documents peuvent attendre une preparation (U4)
}
async function sAnnuler() {
  const r = await api().sync_annuler();
  if (r.ok) { $("#s-annuler").disabled = true; sStatut("Annulation : fin du fichier en cours...", null); }
}
async function sRegler(cle, valeur) {
  const r = await api().sync_regler(cle, valeur);
  if (r.erreur) { toast(r.erreur, "critique"); rendreSync(); return false; }
  SE = r; rendreSync(); return true;
}
async function sRenommer(cid) {
  if (sOccupe) return informer("Renommer", "Attends la fin du téléchargement pour renommer un dossier.");
  const c = SC.find(x => x.id === cid); if (!c) return;
  const nouveau = await demander("Nom du dossier",
    `Nom du dossier pour :\n${c.nom}\n\nLe dossier existant sera renommé sur le disque, avec tout son contenu. `
    + `Renomme toujours ici, jamais dans ${INFOS.explorateur} : sinon MoodleSync ne retrouve plus les fichiers et les télécharge une seconde fois.`,
    c.dossier);
  if (nouveau === null) return;
  let r = await api().sync_renommer(cid, nouveau, false);
  if (r.confirmer) {
    if (!await confirmer("Renommer le dossier", r.confirmer, "Renommer")) return;
    r = await api().sync_renommer(cid, nouveau, true);
  }
  if (r.erreur) return toast(r.erreur, "critique");
  if (r.cours) { SC = r.cours; rendreCours(); toast("Dossier renommé.", "bon"); }
}

/* =====================================================================  carte de preparation (U4) */
/* La carte de Ma semaine : proposer l'extraction du texte, la lancer avec le consentement, la suivre, la
   reprendre. Les phrases sont dans TX_MOTS (textes.js, charge apres ce fichier : resolu au moment du clic).
   Aucun HTML n'est construit ici : textContent seulement. Rien ne part sans un clic, et ocr_lancer n'est
   appele que par txLancer, apres l'ecriture du consentement (invariant 16). */
let txCarteReporte = false;        // « Plus tard » : l'offre reste masquee jusqu'au prochain lancement
let txLancerEnCours = false;       // « Preparer maintenant » est en vol : un seul lancement
let txPreparerOuvre = false;       // lecture de l'etat avant l'ouverture du dialogue
let txPreparerOrigine = null;      // element qui a ouvert le dialogue : le focus y revient
let txCarteInstalle = false;        // l'installation du moteur est en cours (ecart 245)
let txCarteMoteurEnCours = false;  // « Installer » ou le choix du moteur est en vol

function txCarteMots(modele, ...valeurs) {
  let m = modele;
  for (const v of valeurs) m = m.replace("{}", () => String(v));
  return m;
}
function txCarteNombres(compteurs) {
  const docs = Number(compteurs.a_preparer) || 0, pages = Number(compteurs.pages_a_preparer) || 0;
  return txNombre(docs) + " " + txPluriel(docs, TX_MOTS.document, TX_MOTS.documents) + ", " + TX_MOTS.carte_environ
    + " " + txNombre(pages) + " " + txPluriel(pages, TX_MOTS.page, TX_MOTS.pages) + ".";
}
/* Documents restants d'une file en pause ou annulee. Le bloc de textesProgres n'a pas `reprise` : deduit. */
function txCarteReprise(file) {
  if (typeof file.reprise === "number") return Math.max(0, file.reprise);
  const etat = String(file.etat || "");
  if (etat !== "pause" && etat !== "annulee") return 0;
  return Math.max(0, (Number(file.documents_total) || 0) - (Number(file.documents_faits) || 0));
}
function txCarteTravail(carte, file, travail) {
  const bloc = carte.querySelector(".tx-carte-travail");
  if (!bloc) return;
  bloc.hidden = !travail;
  if (!travail) return;
  const document_ = carte.querySelector(".tx-carte-document"), rang = carte.querySelector(".tx-carte-rang");
  const page = carte.querySelector(".tx-carte-page"), pause = carte.querySelector(".tx-carte-pause");
  const nom = String(file.document || "").split(/[\\/]/).pop();
  document_.textContent = nom; document_.hidden = !nom;
  const total = Number(file.documents_total) || 0, faits = Number(file.documents_faits) || 0;
  rang.hidden = !(total > 0);
  rang.textContent = total > 0 ? txCarteMots(TX_MOTS.carte_rang, txNombre(Math.min(total, faits + 1)), txNombre(total)) : "";
  const pages = Number(file.pages) || 0;
  page.hidden = !(pages > 0);
  page.textContent = pages > 0 ? txCarteMots(TX_MOTS.carte_page, txNombre(Number(file.page) || 0), txNombre(pages)) : "";
  pause.hidden = file.etat !== "pause_sync";
  pause.textContent = pause.hidden ? "" : TX_MOTS.carte_pause_sync;
}
/* Dessine la carte d'apres TX (dernier ocr_etat, ou `file` de la progression vive). Ne lit ni n'ecrit rien. */
function txCarteRendre() {
  const carte = $("#tx-carte");
  if (!carte) return;
  const etat = TX || {}, compteurs = etat.compteurs || {}, file = etat.file || {};
  const travail = file.etat === "en_cours" || file.etat === "pause_sync";
  const reprise = txCarteReprise(file);
  const aPreparer = Number(compteurs.a_preparer) || 0;
  const sansMoteur = !!(etat.moteur && etat.moteur.present === false);
  const propose = !travail && reprise === 0 && aPreparer > 0;
  const montrer = (selecteur, oui) => {
    const el = carte.querySelector(selecteur);
    if (el) el.hidden = !oui;
    return el;
  };
  carte.hidden = !(travail || reprise > 0 || (aPreparer > 0 && !txCarteReporte));
  const nombres = montrer(".tx-carte-nombres", propose && !sansMoteur);
  if (nombres) nombres.textContent = propose ? txCarteNombres(compteurs) : "";
  const moteur = montrer(".tx-carte-moteur", sansMoteur && !travail);
  if (moteur) moteur.textContent = sansMoteur ? TX_MOTS.carte_moteur_absent : "";
  montrer("#tx-preparer", propose && !sansMoteur);
  const reprendre = montrer('[data-action="reprendre"]', !travail && reprise > 0);
  if (reprendre && reprise > 0) {
    reprendre.textContent = txCarteMots(reprise > 1 ? TX_MOTS.carte_reprendre : TX_MOTS.carte_reprendre_un, txNombre(reprise));
  }
  montrer('[data-action="pause"]', file.etat === "en_cours");
  montrer('[data-action="annuler"]', travail || reprise > 0);
  montrer('[data-action="installer"]', sansMoteur && !travail && !txCarteInstalle);
  montrer('[data-action="exe"]', sansMoteur && !travail && !txCarteInstalle);
  montrer("#tx-plus-tard", !travail);
  txCarteTravail(carte, file, travail);
}
/* La carte lit ocr_etat() pour elle-meme et ecrit TX. Rend l'etat lu, ou null sur une erreur (phrase de l'API). */
async function txCarteCharger() {
  if (!api()) return null;
  const etat = await api().ocr_etat();
  if (!etat || etat.erreur) { txErreur(etat); return null; }
  TX = etat;
  txCarteRendre();
  return etat;
}
/* Point d'appel de textesProgres (textes.js) : TX.file vient d'etre remplace par la progression. Hors
   `en_cours`, la carte relit l'etat pour avoir les compteurs et la reprise. */
function txCarteProgres(p) {
  if (!p || typeof p !== "object") return;
  txCarteRendre();
  if (String(p.etat || "") !== "en_cours") txCarteCharger();
}
function txCarteFile(r) {
  if (!r) return;
  if (r.erreur) return txErreur(r);
  if (r.file) { TX = TX || {}; TX.file = r.file; txCarteRendre(); }
}
async function txCartePause() { txCarteFile(await api().ocr_pause()); }
async function txCarteReprendre() { txCarteFile(await api().ocr_reprendre()); }
async function txCarteAnnuler() { txCarteFile(await api().ocr_annuler()); }

/* Installer et indiquer l'emplacement : la phrase de l'API est affichee telle quelle (l'installation
   automatique n'existe pas encore, ecart 206). */
function txCarteMoteur(r) {
  if (!r || r.annule) return;
  if (r.erreur) return txErreur(r);
  if (r.moteur) { TX = r; txCarteRendre(); }
}
/* Ecart 245 : barre et bouton « Annuler » pendant l'installation. `recu` et `total` sont des octets ; sans
   total connu (0) la barre reste indeterminee. */
function txCarteInstallation(p) {
  const bloc = $(".tx-carte-installation");
  if (!bloc || !txCarteInstalle) return;
  const barre = bloc.querySelector("progress"), texte = bloc.querySelector(".tx-carte-installation-texte");
  const recu = Number(p && p.recu) || 0, total = Number(p && p.total) || 0;
  if (total > 0) {
    const pct = Math.max(0, Math.min(100, Math.round(recu * 100 / total)));
    if (barre) barre.value = pct;
    if (texte) texte.textContent = `Téléchargement du moteur : ${pct} %.`;
  } else if (barre) {
    barre.removeAttribute("value");
  }
}
function txCarteInstallationMontrer(oui) {
  txCarteInstalle = oui;
  const bloc = $(".tx-carte-installation");
  if (bloc) {
    bloc.hidden = !oui;
    const barre = bloc.querySelector("progress"), texte = bloc.querySelector(".tx-carte-installation-texte");
    if (barre) barre.removeAttribute("value");
    if (texte) texte.textContent = "Installation du moteur en cours.";
  }
  for (const s of ['[data-action="installer"]', '[data-action="exe"]']) {
    const b = $(".tx-carte " + s);
    if (b) b.hidden = oui || b.hidden;
  }
}
async function txCarteInstaller() {
  if (txCarteMoteurEnCours) return;
  txCarteMoteurEnCours = true;
  txCarteInstallationMontrer(true);
  try { txCarteMoteur(await api().ocr_installer()); }
  finally { txCarteMoteurEnCours = false; txCarteInstallationMontrer(false); txCarteRendre(); }
}
async function txCarteInstallerAnnuler() {
  if (txCarteInstalle && api()) await api().ocr_installer_annuler();
}
async function txCarteEmplacement() {
  if (txCarteMoteurEnCours) return;
  txCarteMoteurEnCours = true;
  try { txCarteMoteur(await api().ocr_choisir_exe()); } finally { txCarteMoteurEnCours = false; }
}

/* Dialogue de consentement. Trois entrees : #tx-preparer, [data-action="preparer"] et txPreparer() (appelee
   sans argument par « Preparer tout le cours » du panneau, qui se ferme d'abord). Ouvrir n'ecrit rien. */
async function txPreparer(origine) {
  const dialogue = $("#d-tx-preparer");
  if (!dialogue || dialogue.open || txPreparerOuvre) return;
  txPreparerOuvre = true;
  try {
    const etat = await txCarteCharger();              // nombres frais, ocr_etat() seulement
    if (!etat || dialogue.open) return;
    const quoi = $("#d-tx-quoi");
    if (quoi && quoi.open) quoi.close();
    const compteurs = etat.compteurs || {};
    const nombres = dialogue.querySelector(".tx-preparer-nombres");
    if (nombres) {
      nombres.hidden = !(Number(compteurs.a_preparer) > 0);
      nombres.textContent = nombres.hidden ? "" : txCarteNombres(compteurs);
    }
    const sans = dialogue.querySelector('input[name="sans_texte"]');
    if (sans) sans.checked = true;
    txPreparerOrigine = origine && origine.focus ? origine : null;
    dialogue.showModal();
    const lancer = dialogue.querySelector('[data-action="lancer"]');
    if (lancer) lancer.focus();
  } finally { txPreparerOuvre = false; }
}
/* « Preparer maintenant » : le consentement d'abord (ocr_regler), puis ocr_lancer. Un dialogue modal cache
   les toasts : il est ferme avant d'afficher une phrase d'erreur. */
async function txLancer() {
  const dialogue = $("#d-tx-preparer");
  if (txLancerEnCours || !dialogue || !api()) return;
  const bouton = dialogue.querySelector('[data-action="lancer"]');
  const sans = dialogue.querySelector('input[name="sans_texte"]');
  const portee = sans && !sans.checked ? "tout" : "sans_texte";
  txLancerEnCours = true;
  if (bouton) bouton.disabled = true;
  try {
    const regle = await api().ocr_regler("ocr", true);
    if (!regle || regle.erreur) { dialogue.close(); return txErreur(regle); }
    let r = await api().ocr_lancer(portee, false);
    if (r && r.confirmer) {
      if (!await confirmer(TX_MOTS.preparer_titre, String(r.confirmer), TX_MOTS.preparer_maintenant)) return;
      r = await api().ocr_lancer(portee, false, true);
    }
    dialogue.close();
    if (!r || r.erreur) return txErreur(r);
    if (r.rien) toast(TX_MOTS.carte_rien);
    else txCarteFile(r);
    await txCarteCharger();
  } finally {
    txLancerEnCours = false;
    if (bouton) bouton.disabled = false;
  }
}
const txPreparerDialogue = $("#d-tx-preparer");
if (txPreparerDialogue) {
  txPreparerDialogue.addEventListener("close", () => {
    const origine = txPreparerOrigine;
    txPreparerOrigine = null;
    if (origine && origine.focus) origine.focus();
  });
}

/* =====================================================================  evenements */
document.addEventListener("click", async e => {
  const t = e.target.closest("button"); if (!t) return;
  if (t.id === "tx-preparer" || t.dataset.action === "preparer") return txPreparer(t);
  if (t.id === "tx-plus-tard") { txCarteReporte = true; return txCarteRendre(); }
  if (t.id === "tx-reglages") return ouvrirTiroir(true);
  if (t.dataset.action === "lancer") return txLancer();
  if (t.dataset.action === "pause") return txCartePause();
  if (t.dataset.action === "reprendre") return txCarteReprendre();
  if (t.dataset.action === "annuler") return txCarteAnnuler();
  if (t.dataset.action === "installer") return txCarteInstaller();
  if (t.dataset.action === "installer-annuler") return txCarteInstallerAnnuler();
  if (t.dataset.action === "exe") return txCarteEmplacement();
  if (t.id === "s-connecter") return sConnecter("principal");
  if (t.id === "a-connecter") return sConnecter("accueil");
  if (t.id === "s-appliquer") return sAppliquerSite($("#s-site").value);
  if (t.id === "s-lancer") return sLancer();
  if (t.id === "s-annuler") return sAnnuler();
  if (t.id === "s-ouvrir" ) { const r = await api().sync_ouvrir_dossier(); if (r.erreur) informer("Dossier", r.erreur); return; }
  if (t.id === "s-changer" || t.id === "a-changer") { const r = await api().sync_choisir_dossier(); if (r.erreur) toast(r.erreur, "critique"); else { SE = r; rendreSync(); } return; }
  if (t.id === "s-tout" || t.id === "s-rien") {
    const etat = t.id === "s-tout", r = await api().sync_choisir(null, etat);
    if (r.erreur) return toast(r.erreur, "critique");
    SC.forEach(c => { c.choisi = etat; }); return rendreCours();
  }
  if (t.classList.contains("c-renommer")) return sRenommer(+t.closest(".ligne-cours").dataset.cid);
  if (t.id === "a-semaine") { if (!INFOS.semaine_active) await activerMaSemaineAuto(); if (SE.accueil) await sRegler("accueil_fait", true); choisirOnglet("semaine"); return; }
  if (t.id === "a-suite") { if (await sRegler("accueil_fait", true)) { SE.accueil = false; rendreSync(); } return; }
});
document.addEventListener("change", async e => {
  const t = e.target;
  if (t.matches(".ligne-cours .case input")) {
    const cid = +t.closest(".ligne-cours").dataset.cid, r = await api().sync_choisir(cid, t.checked);
    if (r.erreur) { t.checked = !t.checked; return toast(r.erreur, "critique"); }
    const c = SC.find(x => x.id === cid); if (c) c.choisi = t.checked; return;
  }
  if (t.id === "s-dest") return sRegler("dest", t.value);
  if (t.id === "s-langue" || t.id === "a-langue") return sRegler("langue", t.value);
  if (t.id === "s-statuts") return sRegler("statuts", t.checked);
  if (t.id === "s-note") return sRegler("note", t.checked);
  if (t.id === "s-youtube") return sRegler("titres_youtube", t.checked);
  if (t.id === "s-auto") return sRegler("auto", t.checked);
});
document.addEventListener("keydown", e => {
  if (e.key !== "Enter") return;
  if (e.target.id === "s-site") { e.preventDefault(); sAppliquerSite(e.target.value); }
  if (e.target.id === "a-site") { e.preventDefault(); sConnecter("accueil"); }
  if (e.target.id === "s-dest") e.target.blur();
});
