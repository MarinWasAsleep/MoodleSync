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
const ONGLETS = [["sync", "#o-sync", "#v-sync"], ["semaine", "#o-semaine", "#v-semaine"],
                 ["textes", "#o-textes", "#v-textes"]];
function majActions() {
  const semaine = ONGLET === "semaine", textes = ONGLET === "textes";
  $("#actions-semaine").hidden = !(semaine && INFOS && INFOS.semaine_active);
  $("#actions-sync").hidden = semaine || textes;
  if (semaine && INFOS && INFOS.semaine_active) requestAnimationFrame(placerCurseur);
}
function choisirOnglet(o, focus = false) {
  ONGLET = o;
  for (const [nom, onglet, vue] of ONGLETS) {
    const actif = nom === o;
    $(onglet).setAttribute("aria-selected", actif); $(onglet).tabIndex = actif ? 0 : -1;
    $(vue).hidden = !actif;
    if (actif && focus) $(onglet).focus();
  }
  majActions();
  if (o === "textes" && typeof txOuvrir === "function") txOuvrir();
}
$("#onglets").addEventListener("click", e => { const b = e.target.closest("[role=tab]"); if (b) choisirOnglet(b.dataset.onglet); });
$("#onglets").addEventListener("keydown", e => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
  e.preventDefault();
  const noms = ONGLETS.map(o => o[0]), i = Math.max(0, noms.indexOf(ONGLET));
  const j = e.key === "Home" ? 0 : e.key === "End" ? noms.length - 1
    : e.key === "ArrowLeft" ? (i + noms.length - 1) % noms.length : (i + 1) % noms.length;
  choisirOnglet(noms[j], true);
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
    ${INFOS.semaine_active && G ? `<h3 class="titre-section">Ma semaine</h3>${reglagesSemaine()}`
      : `<div class="groupe"><h4>Ma semaine</h4><p>Désactivée. Pour l'utiliser, ouvre l'onglet Ma semaine.</p></div>`}
    <div class="groupe"><h4>Mises à jour</h4>
      <div class="ligne-champ" style="margin-top:0"><span class="chemin">Version installée : <b>${esc(INFOS.version)}</b></span><button class="bouton" id="r-maj">${ic("actualiser")}Rechercher</button></div>
      <p id="r-maj-etat">${MAJ?.disponible ? `La version ${esc(MAJ.version)} est disponible.` : ""}</p>
      <label class="interrupteur" style="margin-top:12px"><span>Chercher une nouvelle version au démarrage<small style="display:block;color:var(--texte-3)">Une requête à GitHub (api.github.com) au plus toutes les 12 h, sans donnée personnelle. Rien ne s'installe sans ton accord.</small></span><input type="checkbox" id="r-maj-auto" ${(typeof SE !== "undefined" && SE ? SE.maj_auto : true) !== false ? "checked" : ""}><span class="rail-i"></span></label></div>
    <div class="groupe"><h4>À propos</h4><p>MoodleSync ${esc(INFOS.version)} · lecture seule sur Moodle. Réglages, jeton et suivi restent sur l'ordinateur. Accès réseau : ton Moodle${SE && SE.titres_youtube ? " ; YouTube pour le titre des vidéos (réglable dans Synchroniser)" : ""} ; GitHub, pour chercher une nouvelle version (réglable) ; l'adresse d'abonnement de ton horaire, si tu en as donné une ; à la connexion, le pilote du navigateur s'il doit être téléchargé. Détail dans le README, section « Données personnelles ».</p></div>`;
  $("#reglages").append(groupeExtraction());
  remplirExtraction();
}
/* `section` vaut "extraction" quand le lien de la carte ouvre le tiroir (ecart 215) : le focus va au
   groupe de l'extraction. Ouvrir deux fois de suite ne reconstruit pas le tiroir. */
function ouvrirTiroir(o, section) {
  const tiroir = $("#tiroir"), ouvert = tiroir.classList.contains("ouvert");
  tiroir.classList.toggle("ouvert", o); $("#voile").classList.toggle("ouvert", o);
  tiroir.inert = !o;
  if (!o) return;
  if (!ouvert) remplirTiroir();
  const cible = section ? $("#r-tx-ocr") : $("#tiroir [data-ferme-tiroir]");
  if (!cible) return;
  cible.focus();
  if (cible.scrollIntoView) cible.scrollIntoView({ block: "start" });
}

/* =====================================================================  reglages de l'extraction */
/* Contrat 3.4, ligne Reglages : ce groupe est le seul endroit ou « OCR » et « Tesseract » s'ecrivent.
   Les valeurs viennent de ocr_etat() ; rien ne part sans un clic ou un changement, et tout reglage
   passe par ocr_regler (les phrases d'erreur de l'API s'affichent telles quelles).
   Contrat 6 de la refonte : « Format du texte » et la ligne des copies d'originaux ; la version
   cherchable des PDF, l'extraction automatique et le dossier de sortie n'y sont plus. */
let TX_REG = null;                 // dernier ocr_etat() lu pour le groupe
let txRegJeton = 0;                // une reponse tardive n'ecrit pas dans un tiroir rouvert
let txOriginauxEnCours = false;    // « Supprimer les copies » est en vol : un seul appel


/* La coquille du groupe de l'extraction : ecrite ici, hors du modele du tiroir, puis remplie par
   remplirExtraction(). Elle est le seul endroit de la page ou « OCR » s'ecrit (contrat 3.4). */
function groupeExtraction() {
  const groupe = document.createElement("div");
  groupe.className = "groupe"; groupe.id = "r-tx-ocr"; groupe.tabIndex = -1;
  const titre = document.createElement("h4");
  titre.textContent = "Texte des cours (OCR)";
  const ligne = document.createElement("p");
  ligne.id = "r-tx-ocr-moteur";
  ligne.setAttribute("role", "status");
  ligne.setAttribute("aria-live", "polite");
  ligne.textContent = "Lecture des réglages de l'extraction...";
  const corps = document.createElement("div");
  corps.id = "r-tx-ocr-corps"; corps.hidden = true;
  groupe.append(titre, ligne, corps);
  return groupe;
}

async function remplirExtraction() {
  const corps = $("#r-tx-ocr-corps"), ligne = $("#r-tx-ocr-moteur");
  if (!corps || !api()) return;
  const jeton = ++txRegJeton;
  let etat = null;
  try { etat = await api().ocr_etat(); } catch (e) { etat = null; }
  if (jeton !== txRegJeton || $("#r-tx-ocr-corps") !== corps) return;   // tiroir rouvert entre-temps
  if (etat && etat.erreur) toast(String(etat.erreur), "critique");
  if (!etat || etat.erreur) {
    if (ligne) ligne.textContent = "Réglages de l'extraction indisponibles.";
    return;
  }
  TX_REG = etat;
  txReglagesConstruire(corps, etat);
  txReglagesMaj(etat);
}

/* Les controles du groupe, construits une fois par ouverture du tiroir. */
function txReglagesConstruire(corps, etat) {
  corps.textContent = "";
  corps.hidden = false;
  const langues = document.createElement("div");
  langues.className = "ligne-champ";
  const etiquette = document.createElement("label");
  etiquette.className = "doux";
  etiquette.setAttribute("for", "r-tx-ocr-langues");
  etiquette.textContent = "Langues reconnues";
  const choix = document.createElement("select");
  choix.className = "champ"; choix.id = "r-tx-ocr-langues";
  langues.append(etiquette, choix);
  /* Contrat 6 : le format du texte, lu dans `ocr_etat().reglages.ocr_format` et jamais dans une
     variable de page (regle de l'ecart 240). */
  const format = document.createElement("div");
  format.className = "ligne-champ";
  const etiquetteFormat = document.createElement("label");
  etiquetteFormat.className = "doux";
  etiquetteFormat.setAttribute("for", "r-tx-ocr-format");
  etiquetteFormat.textContent = "Format du texte";
  const choixFormat = document.createElement("select");
  choixFormat.className = "champ"; choixFormat.id = "r-tx-ocr-format";
  for (const [code, nom] of [["md", "Markdown (.md)"], ["txt", "Texte brut (.txt)"]]) {
    const option = document.createElement("option");
    option.value = code; option.textContent = nom;
    choixFormat.append(option);
  }
  format.append(etiquetteFormat, choixFormat);
  /* Contrat 6 et O15 : les copies d'originaux, leur volume, et le bouton qui les libere. */
  const copies = document.createElement("div");
  copies.className = "ligne-champ";
  const ligneCopies = document.createElement("span");
  ligneCopies.className = "chemin"; ligneCopies.id = "r-tx-ocr-copies";
  const supprimer = document.createElement("button");
  supprimer.className = "bouton"; supprimer.id = "r-tx-ocr-originaux";
  supprimer.textContent = "Supprimer les copies";
  copies.append(ligneCopies, supprimer);
  const aideCopies = document.createElement("p");
  aideCopies.id = "r-tx-ocr-originaux-aide"; aideCopies.className = "doux";
  aideCopies.textContent = "Ces copies servent à remettre le PDF d'origine. Sans elles, seule une " +
    "nouvelle synchronisation depuis Moodle peut le récupérer.";
  supprimer.setAttribute("aria-describedby", "r-tx-ocr-originaux-aide");
  const moteur = document.createElement("div");
  moteur.className = "ligne-champ";
  const exe = document.createElement("span");
  exe.className = "chemin"; exe.id = "r-tx-ocr-exe";
  const indiquer = document.createElement("button");
  indiquer.className = "bouton"; indiquer.id = "r-tx-ocr-choisir";
  indiquer.textContent = "Indiquer l'emplacement";
  const installer = document.createElement("button");
  installer.className = "bouton"; installer.id = "r-tx-ocr-installer";
  installer.textContent = "Installer";
  moteur.append(exe, indiquer, installer);
  /* Ecart 292 : la meme barre et le meme « Annuler » que la carte (sync.js les met a jour ensemble). */
  const installation = document.createElement("div");
  installation.className = "tx-carte-installation"; installation.id = "r-tx-ocr-installation";
  installation.setAttribute("role", "status"); installation.setAttribute("aria-live", "polite");
  installation.hidden = true;
  const installationTexte = document.createElement("p");
  installationTexte.className = "tx-carte-installation-texte";
  installationTexte.textContent = "Installation du moteur en cours.";
  const installationBarre = document.createElement("progress");
  installationBarre.className = "tx-carte-installation-barre"; installationBarre.setAttribute("max", "100");
  const installationAnnuler = document.createElement("button");
  installationAnnuler.className = "bouton"; installationAnnuler.id = "r-tx-ocr-installer-annuler";
  installationAnnuler.setAttribute("data-action", "installer-annuler");
  installationAnnuler.textContent = "Annuler";
  installation.append(installationTexte, installationBarre, installationAnnuler);
  corps.append(langues, format, copies, aideCopies, moteur, installation);
  txReglagesLangues(choix, etat);
  if (typeof txInstallationRendre === "function") txInstallationRendre();   // sync.js : une installation deja en cours
}


/* Langues proposees : celles que le moteur detecte (contrat 3.2, « inclus dans les langues detectees »). */
function txReglagesLangues(select, etat) {
  const moteur = (etat && etat.moteur) || {}, reglages = (etat && etat.reglages) || {};
  const dispo = Array.isArray(moteur.langues) ? moteur.langues.map(x => String(x).toLowerCase()) : [];
  const courante = String(reglages.ocr_langues || "fra+eng").toLowerCase();
  const liste = [["fra+eng", "Français et anglais"], ["fra", "Français"], ["eng", "Anglais"]]
    .filter(([code]) => code === courante || !dispo.length || code.split("+").every(x => dispo.includes(x)));
  if (!liste.some(([code]) => code === courante)) liste.push([courante, courante]);
  select.textContent = "";
  for (const [code, nom] of liste) {
    const option = document.createElement("option");
    option.value = code; option.textContent = nom;
    select.append(option);
  }
  select.value = courante;
  select.dataset.codes = liste.map(([code]) => code).join(",");
}

/* Volume des copies d'originaux : `originaux.octets` de ocr_etat() (contrat 4.2), arrondi au dixieme. */
function txVolume(octets) {
  const o = Math.max(0, Number(octets) || 0);
  if (o < 1048576) return `${Math.round(o / 1024)} Ko`;
  return `${(o / 1048576).toFixed(1).replace(".", ",")} Mo`;
}

/* Met a jour les valeurs du groupe sans le reconstruire : le focus de l'utilisateur reste en place. */
function txReglagesMaj(etat) {
  if (!etat) return;
  const reglages = etat.reglages || {}, moteur = etat.moteur || {}, originaux = etat.originaux || {};
  const langues = $("#r-tx-ocr-langues");
  if (langues && reglages.ocr_langues) {
    const courante = String(reglages.ocr_langues);
    if (!String(langues.dataset.codes || "").split(",").includes(courante)) txReglagesLangues(langues, etat);
    langues.value = courante;
  }
  /* Le format vient de l'API, jamais d'une variable de page (contrat 6, regle de l'ecart 240). */
  const format = $("#r-tx-ocr-format");
  if (format) format.value = reglages.ocr_format === "txt" ? "txt" : "md";
  const copies = $("#r-tx-ocr-copies"), bouton = $("#r-tx-ocr-originaux");
  const nombre = Math.max(0, Number(originaux.nombre) || 0);
  if (copies) copies.textContent = `Copies d'originaux : ${nombre}, ${txVolume(originaux.octets)}`;
  if (bouton) bouton.disabled = nombre === 0 || txOriginauxEnCours;
  const exe = $("#r-tx-ocr-exe");
  if (exe) exe.textContent = moteur.exe ? String(moteur.exe) : "Aucun moteur détecté.";
  const ligne = $("#r-tx-ocr-moteur");
  if (ligne) ligne.textContent = moteur.present
    ? (moteur.version ? `Moteur détecté : version ${moteur.version}.` : "Moteur détecté.")
    : "Aucun moteur détecté : indique son emplacement ou installe-le.";
}

async function txReglerExtraction(cle, valeur, el, case_) {
  if (!api()) return;
  const r = await api().ocr_regler(cle, valeur);
  if (!r) return;
  if (r.erreur) {
    if (case_ && el) el.checked = !el.checked;
    else if (el && el.tagName === "SELECT" && TX_REG) txReglagesMaj(TX_REG);   // la liste revient sur la valeur enregistree
    return toast(String(r.erreur), "critique");
  }
  TX_REG = r;
  txReglagesMaj(r);
}

/* « Supprimer les copies » (O15, contrat 4.7) : deux temps. Le premier appel ne supprime rien et rend la
   phrase de l'API ; le second, avec confirme=true, libere les copies. */
async function txSupprimerOriginaux() {
  if (!api() || txOriginauxEnCours) return;
  txOriginauxEnCours = true;
  const bouton = $("#r-tx-ocr-originaux");
  if (bouton) bouton.disabled = true;
  try {
    let r = await api().ocr_originaux_supprimer();
    if (!r) return;
    if (r.erreur) return toast(String(r.erreur), "critique");
    if (r.confirmer) {
      const accord = await confirmer("Supprimer les copies d'originaux ?", String(r.confirmer), "Supprimer");
      if (!accord) return;
      r = await api().ocr_originaux_supprimer(true);
      if (!r) return;
      if (r.erreur) return toast(String(r.erreur), "critique");
    }
    toast("Copies d'originaux supprimées.", "bon");
    if (bouton) bouton.disabled = true;              // jusqu'a la relecture : le compte est perime
    const etat = await api().ocr_etat();
    if (etat && !etat.erreur) { TX_REG = etat; txReglagesMaj(etat); }
  } finally {
    txOriginauxEnCours = false;
    const nom = TX_REG && TX_REG.originaux ? TX_REG.originaux.nombre : 0;
    if (bouton) bouton.disabled = !(Number(nom) > 0);
  }
}


/* « Indiquer l'emplacement » : la phrase de l'API est affichee telle quelle. « Installer » ne passe pas ici
   (ecart 292) : il appelle txCarteInstaller (sync.js), comme le bouton de la carte. */
async function txReglagesMoteur(appel) {
  if (!api() || txCarteMoteurEnCours) return;
  txCarteMoteurEnCours = true;
  try { txCarteMoteur(await appel()); } finally { txCarteMoteurEnCours = false; }
}
/* Appelee par txCarteMoteur (sync.js) : le groupe suit le moteur que l'API vient de rendre. */
function txReglagesDepuis(etat) {
  if (!etat || !etat.moteur) return;
  TX_REG = etat;
  txReglagesMaj(etat);
}
$("#voile").addEventListener("click", () => ouvrirTiroir(false));
document.addEventListener("change", async e => {
  const t = e.target;
  if (t.id === "r-maj-auto") {
    const r = await api().sync_regler("maj_auto", t.checked);
    if (r.erreur) { t.checked = !t.checked; return toast(r.erreur, "critique"); }
    if (typeof SE !== "undefined" && SE) SE.maj_auto = t.checked;
    return;
  }
  if (t.name === "theme") {
    const r = await api().sync_regler("theme", t.value);
    if (r.erreur) return toast(r.erreur, "critique");
    INFOS.theme = t.value; appliquerTheme(t.value, t.closest("label"));
    return;
  }
  if (t.id === "r-tx-ocr-langues") return txReglerExtraction("ocr_langues", t.value, t, false);
  if (t.id === "r-tx-ocr-format") return txReglerExtraction("ocr_format", t.value, t, false);
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
  if (t.id === "tx-reglages") return ouvrirTiroir(true, "extraction");
  if (t.id === "r-tx-ocr-choisir") return txReglagesMoteur(() => api().ocr_choisir_exe());
  if (t.id === "r-tx-ocr-installer") return txCarteInstaller();
  if (t.id === "r-tx-ocr-originaux") return txSupprimerOriginaux();
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

/* =====================================================================  mises a jour (maj.py) */
let MAJ = null;                    // derniere reponse de maj_chercher : {version, disponible, page, installable, raison}
let majMasque = false, majOccupe = false;
const mo = o => `${(o / 1048576).toFixed(1).replace(".", ",")} Mo`;

function majAffiche(etat) {
  const el = $("#bandeau-maj");
  if (!MAJ?.disponible || (majMasque && !majOccupe)) { el.innerHTML = ""; return; }
  const lien = `<a href="${esc(MAJ.page)}" target="_blank" rel="noopener">Notes de version</a>`;
  el.innerHTML = `<div class="bandeau info" role="status">${ic("synchro")}
    <span class="texte">${etat ?? `<b>MoodleSync ${esc(MAJ.version)} est disponible</b> (tu as la ${esc(INFOS.version)}). ${lien}`}</span>
    ${majOccupe ? `<progress id="maj-barre" max="100" value="0" aria-label="Téléchargement"></progress>`
      : (MAJ.installable ? `<button class="bouton principal petit" id="b-maj-installer">Mettre à jour</button>`
          : `<a class="bouton petit" href="${esc(MAJ.page)}" target="_blank" rel="noopener" title="${esc(MAJ.raison || "")}">Télécharger</a>`)
        + `<button class="bouton icone petit" id="b-maj-plus-tard" title="Plus tard" aria-label="Plus tard">${ic("x")}</button>`}</div>`;
}
async function majVerifier(manuel = false) {
  const etat = $("#r-maj-etat");
  if (manuel && etat) etat.textContent = "Recherche...";
  const r = await api().maj_chercher(manuel);
  if (r.saute) return;
  if (r.erreur) { if (manuel) { toast(r.erreur, "critique"); if (etat) etat.textContent = r.erreur; } return; }   // au demarrage : en silence
  MAJ = r; majMasque = false; majAffiche();
  if (!manuel) return;
  const msg = r.disponible ? `La version ${r.version} est disponible.` : `Tu as la dernière version (${r.courante}).`;
  if (etat) etat.textContent = msg;
  toast(msg, "bon");
  if (r.disponible) ouvrirTiroir(false);
}
async function majInstaller() {
  if (!MAJ?.disponible || majOccupe) return;
  const ok = await confirmer(`Installer la version ${MAJ.version} ?`,
    `MoodleSync télécharge la ${MAJ.version} depuis GitHub, vérifie son empreinte SHA-256, remplace l'application, puis redémarre. ` +
    `Tes réglages, ta connexion et ton suivi sont conservés. Si quoi que ce soit échoue, rien n'est modifié.`, "Mettre à jour");
  if (!ok) return;
  majOccupe = true; majAffiche(`Téléchargement de la ${esc(MAJ.version)}...`);
  const r = await api().maj_installer();
  majOccupe = false;
  if (r.erreur) { majAffiche(); return toast(r.erreur, "critique"); }
  majOccupe = true;
  majAffiche(`Version ${esc(r.version)} installée : redémarrage...`);
  $("#maj-barre")?.setAttribute("value", 100);
}
window.progressionMaj = ([lus, total]) => {
  const t = $("#bandeau-maj .texte"), b = $("#maj-barre"); if (!t) return;
  t.textContent = `Téléchargement de la ${MAJ.version} : ${Math.round(100 * lus / total)} % (${mo(lus)} sur ${mo(total)})`;
  if (b) b.value = Math.round(100 * lus / total);
};
document.addEventListener("click", e => {
  const t = e.target.closest("button"); if (!t) return;
  if (t.id === "b-maj-installer") return majInstaller();
  if (t.id === "b-maj-plus-tard") { majMasque = true; return majAffiche(); }
  if (t.id === "r-maj") return majVerifier(true);
});

/* =====================================================================  verification sans intervention */
/* Contrat 3.4, ligne Verification : la derniere phrase d'erreur encore affichee (un message critique
   de #toasts, le seul endroit ou l'onglet des textes signale une erreur) tient lieu de `textes.erreur`.
   Decision de l'ecart 226, prise en U5 : l'onglet n'a pas de bandeau, et le contrat 3.4 est aligne. */
function derniereErreur() {
  const toasts = document.querySelectorAll("#toasts .toast.critique");
  const dernier = toasts[toasts.length - 1];
  return dernier ? dernier.textContent.trim() : "";
}

window.etatVerification = () => {
  const bandeaux = [...document.querySelectorAll("#bandeaux .bandeau, #s-bandeau .bandeau")];
  const erreur = bandeaux.map(b => b.querySelector(".texte").textContent.trim()).join(" | ");
  const semaineFinie = !INFOS || !INFOS.semaine_active || semainePrete;
  const extraction = TX || {}, compteurs = extraction.compteurs || {}, file = extraction.file || {};
  /* R11 : les globales txPret et txOccupe de l'ancienne coque sont parties. `pret` exige la meme chose
     qu'avant, lu dans TX : un ocr_etat deja recu, et une file qui ne travaille pas (contrat 3.4). */
  const textesLus = !!(extraction.moteur || extraction.compteurs);
  const textesLibres = ["en_cours", "pause", "pause_sync"].indexOf(String(file.etat || "")) < 0;
  return {
    pret: !!INFOS && syncPrete && semaineFinie && !sOccupe && !occupe && textesLus && textesLibres,
    onglet: ONGLET, erreur, connecte: sConnecte, cours: SC.length, semaine_active: !!(INFOS && INFOS.semaine_active),
    cartes: document.querySelectorAll("#v-semaine .carte").length, lectures: document.querySelectorAll("#v-semaine .lecture").length,
    synchro: dernierResultat, version: INFOS && INFOS.version,
    onglets: [...document.querySelectorAll("[role=tab]")].map(b => b.dataset.onglet || ""),
    horaire: typeof window.Horaire === "object" && window.Horaire !== null,
    textes: { documents: Number(compteurs.documents) || 0, pages: Number(compteurs.pages) || 0,
              a_verifier: Number(compteurs.a_verifier) || 0, file: String(file.etat || ""),
              erreur: derniereErreur() },
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
  choisirOnglet(INFOS.semaine_active ? "semaine" : "sync");
  vueSemaine();
  // Les deux onglets se chargent en parallele : la synchronisation ne depend pas de Ma semaine.
  majVerifier(false);                // une nouvelle version ? (au plus une requete toutes les 12 h, reglable) : independant des onglets
  await Promise.all([sDemarrer(), demarrerSemaine()]);
}
if (api()) demarrer(); else addEventListener("pywebviewready", demarrer);
