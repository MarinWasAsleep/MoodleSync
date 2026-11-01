"use strict";
/* Coquille de la fenetre : onglets, theme, tiroir des reglages, dialogues, verification, demarrage.
   Charge en dernier (apres commun.js, semaine.js, sync.js). */
let INFOS = null;                  // api().infos() : version, systeme, theme, Ma semaine activee...
let ONGLET = "sync";

/* =====================================================================  barre d'activite partagee */
const occupations = new Set();     // "sync", "semaine" : les deux onglets peuvent travailler en meme temps
function barreOccupee(o, texte, qui) {
  if (o) occupations.add(qui); else occupations.delete(qui);
  const actif = occupations.size > 0;
  $("#progres").classList.toggle("actif", actif);
  $("#statut-ligne").classList.toggle("visible", actif);
  if (o && texte) $("#statut-texte").textContent = texte;
}

/* =====================================================================  onglets */
function majActions() {
  const semaine = ONGLET === "semaine";
  $("#actions-semaine").hidden = !(semaine && INFOS && INFOS.semaine_active);
  $("#actions-sync").hidden = semaine;
  if (semaine && INFOS && INFOS.semaine_active) requestAnimationFrame(placerCurseur);
}
function choisirOnglet(o, focus = false) {
  ONGLET = o;
  for (const [nom, onglet, vue] of [["sync", "#o-sync", "#v-sync"], ["semaine", "#o-semaine", "#v-semaine"]]) {
    const actif = nom === o;
    $(onglet).setAttribute("aria-selected", actif); $(onglet).tabIndex = actif ? 0 : -1;
    $(vue).hidden = !actif;
    if (actif && focus) $(onglet).focus();
  }
  majActions();
}
$("#onglets").addEventListener("click", e => { const b = e.target.closest("[role=tab]"); if (b) choisirOnglet(b.dataset.onglet); });
$("#onglets").addEventListener("keydown", e => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
  e.preventDefault();
  choisirOnglet(e.key === "ArrowLeft" || e.key === "Home" ? "sync" : "semaine", true);
});

/* =====================================================================  theme */
function appliquerTheme(t, depuis) {
  const faire = () => { if (t === "systeme") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
    const sombre = t === "dark" || (t === "systeme" && matchMedia("(prefers-color-scheme: dark)").matches);
    $("#b-theme").innerHTML = ic(sombre ? "soleil" : "lune"); };
  if (!depuis || !document.startViewTransition || moins.matches) return faire();
  const r = depuis.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  const rayon = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  document.startViewTransition(faire).ready.then(() => document.documentElement.animate(
    {clipPath: [`circle(0 at ${x}px ${y}px)`, `circle(${rayon}px at ${x}px ${y}px)`]},
    {duration: 550, easing: "cubic-bezier(.2,.8,.2,1)", pseudoElement: "::view-transition-new(root)"}));
}
function themeCourant() { return document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); }
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (!document.documentElement.dataset.theme) appliquerTheme("systeme"); });

/* =====================================================================  tiroir des reglages */
function remplirTiroir() {
  const theme = INFOS.theme || "systeme";
  $("#reglages").innerHTML = `
    <div class="groupe"><h4>Thème</h4><div class="choix" style="grid-template-columns:repeat(3,1fr)">
      ${[["systeme", "Système"], ["light", "Clair"], ["dark", "Sombre"]].map(([v, n]) => `<label><input type="radio" name="theme" value="${v}" ${theme === v ? "checked" : ""}>${n}</label>`).join("")}</div></div>
    ${INFOS.semaine_active && G ? `<h3 class="titre-section">Ma semaine <span class="exp">expérimental</span></h3>${reglagesSemaine()}`
      : `<div class="groupe"><h4>Ma semaine <span class="exp">expérimental</span></h4><p>Désactivée. Pour l'essayer, ouvre l'onglet Ma semaine.</p></div>`}
    <div class="groupe"><h4>À propos</h4><p>MoodleSync ${esc(INFOS.version)} · lecture seule sur Moodle. Réglages, jeton et suivi restent sur l'ordinateur. Accès réseau : ton Moodle${SE && SE.titres_youtube ? " ; YouTube pour le titre des vidéos (réglable dans Synchroniser)" : ""} ; l'adresse d'abonnement de ton horaire, si tu en as donné une ; à la connexion, le pilote du navigateur s'il doit être téléchargé. Détail dans le README, section « Données personnelles ».</p></div>`;
}
function ouvrirTiroir(o) {
  $("#tiroir").classList.toggle("ouvert", o); $("#voile").classList.toggle("ouvert", o);
  $("#tiroir").inert = !o;
  if (o) { remplirTiroir(); $("#tiroir [data-ferme-tiroir]").focus(); }
}
$("#voile").addEventListener("click", () => ouvrirTiroir(false));
document.addEventListener("change", async e => {
  const t = e.target;
  if (t.name === "theme") {
    const r = await api().sync_regler("theme", t.value);
    if (r.erreur) return toast(r.erreur, "critique");
    INFOS.theme = t.value; appliquerTheme(t.value, t.closest("label"));
  }
});

/* =====================================================================  dialogues (sans alert/confirm du navigateur) */
function dialogue(titre, texte, {ok = "OK", annuler = "Annuler", champ = null, info = false} = {}) {
  return new Promise(resolve => {
    const d = $("#d-question");
    $("#q-titre").textContent = titre;
    $("#q-texte").textContent = texte;
    const c = $("#q-champ"); c.hidden = champ === null; c.value = champ ?? "";
    $("#q-ok").textContent = ok;
    $("#q-annuler").hidden = info; $("#q-annuler").textContent = annuler;
    const fin = v => { d.removeEventListener("close", surFermeture); resolve(v); };
    const surFermeture = () => fin(d.returnValue === "ok" ? (champ === null ? true : c.value) : (champ === null ? false : null));
    d.returnValue = "";
    d.addEventListener("close", surFermeture);
    d.showModal();
    (champ === null ? $("#q-ok") : c).focus();
    if (champ !== null) c.select();
  });
}
const confirmer = (titre, texte, ok = "Continuer") => dialogue(titre, texte, {ok});
const demander = (titre, texte, valeur) => dialogue(titre, texte, {ok: "Renommer", champ: valeur});
const informer = (titre, texte) => dialogue(titre, texte, {info: true});

/* =====================================================================  evenements generaux */
document.addEventListener("click", e => {
  const t = e.target.closest("button"); if (!t) return;
  if (t.id === "b-reglages") return ouvrirTiroir(true);
  if (t.hasAttribute("data-ferme-tiroir")) return ouvrirTiroir(false);
  if (t.hasAttribute("data-ferme")) return t.closest("dialog").close();
  if (t.id === "b-theme") {
    const v = themeCourant() === "dark" ? "light" : "dark"; appliquerTheme(v, t);
    if (INFOS) { INFOS.theme = v; api().sync_regler("theme", v); }
  }
});
document.addEventListener("keydown", e => { if (e.key === "Escape" && $("#tiroir").classList.contains("ouvert")) ouvrirTiroir(false); });
// Liens vers Moodle : dans le navigateur du systeme, jamais dans la fenetre de l'application.
document.addEventListener("click", e => {
  const a = e.target.closest("a[href^='http']"); if (!a) return;
  if (!a.target) a.target = "_blank";
});

/* =====================================================================  verification sans intervention */
window.etatVerification = () => {
  const bandeaux = [...document.querySelectorAll("#bandeaux .bandeau, #s-bandeau .bandeau")];
  const erreur = bandeaux.map(b => b.querySelector(".texte").textContent.trim()).join(" | ");
  const semaineFinie = !INFOS || !INFOS.semaine_active || semainePrete;
  return {
    pret: !!INFOS && syncPrete && semaineFinie && !sOccupe && !occupe,
    onglet: ONGLET, erreur, connecte: sConnecte, cours: SC.length, semaine_active: !!(INFOS && INFOS.semaine_active),
    cartes: document.querySelectorAll("#v-semaine .carte").length, lectures: document.querySelectorAll("#v-semaine .lecture").length,
    synchro: dernierResultat, version: INFOS && INFOS.version,
    onglets: [...document.querySelectorAll("[role=tab]")].map(b => b.textContent.trim()),
    horaire: typeof window.Horaire === "object" && window.Horaire !== null,
  };
};

/* =====================================================================  demarrage */
async function demarrer() {
  INFOS = await api().infos();
  if (INFOS.erreur) { INFOS = {theme: "systeme", semaine_active: false, verif_action: "aucune", navigateurs: "le navigateur", explorateur: "l'explorateur", version: ""}; toast("Démarrage incomplet.", "critique"); }
  appliquerTheme(INFOS.theme || "systeme");
  $("#version").textContent = INFOS.version ? `version ${INFOS.version}` : "";
  for (const el of document.querySelectorAll(".t-explorateur")) el.textContent = INFOS.explorateur;
  $("#a-navigateurs").textContent = INFOS.navigateurs;
  choisirOnglet(INFOS.semaine_active ? ONGLET : "sync");
  vueSemaine();
  // Les deux onglets se chargent en parallele : la synchronisation ne depend pas de Ma semaine.
  await Promise.all([sDemarrer(), demarrerSemaine()]);
}
if (api()) demarrer(); else addEventListener("pywebviewready", demarrer);
