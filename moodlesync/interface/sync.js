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
  rendreCours();
}

/* =====================================================================  actions */
async function sDemarrer() {
  SE = await api().sync_etat();
  if (SE.erreur) { sErreur(SE); SE = null; syncPrete = true; return; }
  rendreSync();
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
      + (r.lignes.length ? "\n\n" + r.lignes.slice(0, 8).join("\n") : ""), true);
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

/* =====================================================================  evenements */
document.addEventListener("click", async e => {
  const t = e.target.closest("button"); if (!t) return;
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
