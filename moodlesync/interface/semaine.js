"use strict";
/* Onglet Ma semaine : planning de lecture (experimental). Utilise commun.js. */
const PERIODES = [[7, "1 semaine"], [14, "2 semaines"], [21, "3 semaines"], [30, "1 mois"]];
const proprete = n => n.replace(/\.pdf$/i, "").replace(/_+/g, " ").replace(/\s{2,}/g, " ").trim();
let G = null, D = null, occupe = false;
const vitesse = () => G?.prefs.vitesse || 12;
const duree = p => { const m = Math.round(p * 60 / vitesse() / 5) * 5; return m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}` : `${m} min`; };
const fmtMin = m => m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}` : `${m} min`;
const lecturesDe = s => s.lectures || [];
const toutes = () => (D?.seances || []).filter(s => !s.sans_travail).flatMap(lecturesDe);
const compte = l => !l.facultatif;

/* =====================================================================  messages du moteur */
const decoupe = m => { const i = m.indexOf(" : "); return i < 0 ? ["", m] : [m.slice(0, i), m.slice(i + 3)]; };
const phrase = t => { const i = t.search(/[.?] /); return i < 0 ? t : t.slice(0, i + 1); };
const surv = () => (D?.surveiller || []).map(m => {
  const r = m.match(/^(.*?), (\S+ \d+ \S+) \(« (.*?) »\) : (.*)$/);
  return r ? {cours: r[1], quand: r[2], titre: r[3], texte: r[4]} : {cours: "", quand: "", titre: "", texte: m};
});
const surveillee = s => surv().find(x => x.cours === s.cours && x.titre === s.titre);
const alerteDe = s => (D?.alertes || []).find(a => a.startsWith(s.cours + " : ") && a.includes(s.titre));

/* =====================================================================  tuiles */
function tuiles(premiere) {
  const ls = toutes().filter(compte);
  const total = ls.reduce((a, l) => a + (l.pages || 0), 0);
  const faites = ls.filter(l => l.fait).reduce((a, l) => a + (l.pages || 0), 0);
  const pct = total ? Math.round(100 * faites / total) : 0;
  const ech = (D?.echeances || []).slice().sort((a, b) => a.date.localeCompare(b.date));
  const prochaine = ech.find(e => !e.retard && ecart(e.date) >= 0);
  const retard = ech.filter(e => e.retard).length;
  const n = prochaine ? ecart(prochaine.date) : null;
  if (premiere || !$("#t-pages")) {
    $("#tuiles").innerHTML = `
      <div class="tuile anime" style="--i:0">
        <div class="etiquette">${ic("livre")}<span id="t-titre"></span></div>
        <div class="valeur"><span id="t-pages" data-v="0">0</span> p.<small id="t-duree"></small></div>
        <div class="detail" id="t-detail"></div>
        <div class="jauge" id="t-jauge" role="meter" aria-valuemin="0" aria-valuemax="100" aria-label="Part des pages lues"><div></div></div>
      </div>
      <div class="tuile anime cliquable" style="--i:1" id="t-echeance"></div>
      <div class="tuile critique anime cliquable" style="--i:2" data-panneau="p-verifier">
        <div class="etiquette">${ic("alerte")}À vérifier</div><div class="valeur"><span id="t-alertes" data-v="0">0</span></div>
        <div class="detail">Séance introuvable ou mal placée</div></div>
      <div class="tuile alerte anime cliquable" style="--i:3" data-panneau="p-surveiller">
        <div class="etiquette">${ic("oeil")}À surveiller</div><div class="valeur"><span id="t-surv" data-v="0">0</span></div>
        <div class="detail">Lectures pas encore déposées</div></div>`;
  }
  $("#t-titre").textContent = `Lecture des ${D?.jours || G?.prefs.jours || 14} prochains jours`;
  animerNombre($("#t-pages"), total);
  $("#t-duree").textContent = total ? `≈ ${duree(total)}` : "";
  $("#t-detail").innerHTML = `<span id="t-faites">${faites}</span> p. lues (${pct} %) · hors lectures facultatives · ${vitesse()} p./h`;
  const j = $("#t-jauge"), barre = j.firstElementChild, avant = parseFloat(barre.style.width) || 0;
  requestAnimationFrame(() => { barre.style.width = pct + "%"; });
  j.setAttribute("aria-valuenow", pct);
  j.classList.toggle("pleine", pct === 100 && total > 0);
  if (pct > avant) { j.classList.remove("brille"); void j.offsetWidth; j.classList.add("brille"); }
  $("#t-echeance").innerHTML = `
    <div class="etiquette">${ic("calendrier")}Prochaine échéance</div>
    <div class="valeur">${n === null ? "Aucune" : n === 0 ? "Aujourd'hui" : n === 1 ? "Demain" : `Dans ${n} jours`}</div>
    <div class="detail">${esc(prochaine?.nom || "Rien de prévu dans le calendrier")}</div>
    ${retard ? `<div class="detail" style="color:var(--critique);font-weight:600">${retard} en retard</div>` : ""}`;
  animerNombre($("#t-alertes"), (D?.alertes || []).length);
  animerNombre($("#t-surv"), (D?.surveiller || []).length);
}

/* =====================================================================  planning */
function statut(l) {
  if (l.origine === "déduit")
    return `<span class="statut deduit" title="Rien ne le dit dans Moodle : fichier placé dans la séance, qui n'est pas une diapo.">À lire, déduit</span>`;
  const nom = l.facultatif ? `${l.statut}, facultatif` : l.statut;
  const cit = l.origine === "consigne" ? ` title="D'après la consigne : « ${esc(l.extrait)} »"` : "";
  return `<span class="statut ${l.facultatif ? "facultatif" : "obligatoire"}"${cit}>${l.origine === "consigne" ? ic("guillemet") : ""}${esc(nom)}</span>`;
}

function ligneLecture(l) {
  const meta = [];
  if (l.pages) meta.push(`${l.pages} p.${l.consigne_pages ? ` d'après la consigne (pp. ${l.plages.map(p => p.join("-")).join(", ")})` : ""}`);
  if (l.pages) meta.push(`≈ ${duree(l.pages)}`);
  if (!l.consigne_pages && l.pages_pdf > 60) meta.push(`<span title="La consigne ne précise pas les pages : durée sans doute surestimée.">long, à cibler</span>`);
  if (l.origine === "consigne") meta.push(`<span class="citation">« ${esc(l.extrait)} »</span>`);
  const nom = l.lien ? `<a href="${esc(l.lien)}" target="_blank" rel="noopener">${esc(proprete(l.nom))}</a>` : esc(proprete(l.nom));
  return `<div class="lecture ${l.fait ? "faite" : ""}" data-id="${esc(l.id)}">
    <label class="case" title="Marquer comme lu"><input type="checkbox" ${l.fait ? "checked" : ""} aria-label="Lu : ${esc(proprete(l.nom))}">
      <span class="boite"><svg viewBox="0 0 24 24"><path d="M5 12.5 10 17 19 7"/></svg></span></label>
    <div style="min-width:0"><span class="nom" title="${esc(l.nom)}">${nom}</span>
      <div class="sous">${l.nouveau ? `<span class="puce nouveau">Nouveau</span>` : ""}${meta.join(" · ")}</div></div>
    <div class="droite">${statut(l)}<input class="temps ${l.minutes ? "ok" : ""}" placeholder="temps réel" value="${l.minutes ? fmtMin(l.minutes) : ""}"
      aria-label="Temps réel de lecture" title="Minutes passées : 70, 1 h 10..."></div></div>`;
}

function carte(s, i) {
  const puces = [];
  if (s.precision.startsWith("date déduite du numéro"))
    puces.push(`<span class="puce" title="${esc(s.precision)}">${ic("approx")}Date déduite du numéro</span>`);
  if (s.precision.includes("différent de"))
    puces.push(`<span class="puce critique" title="${esc(alerteDe(s) || s.precision)}">${ic("alerte")}Pas le jour habituel</span>`);
  const sv = surveillee(s), ls = lecturesDe(s);
  let bas = (s.consigne || []).map(c => `<div class="consigne-section">« ${esc(c)} »</div>`).join("");
  if (ls.length) bas += `<div class="lectures">${ls.map(ligneLecture).join("")}</div>`;
  else if (s.ouverture) bas += `<div class="vide">${ic("cadenas")}Contenu non visible pour toi : ${esc(s.ouverture)}</div>`;
  else if (sv) bas += `<div class="vide alerte">${ic("oeil")}Pas encore de lecture en ligne, alors que ce cours en donne d'habitude.</div>`;
  else if (s.sans_lecture) bas += `<div class="vide">Pas de lecture (écrit dans Moodle).</div>`;
  else bas += `<div class="vide">Aucune lecture identifiée.</div>`;
  if (s.supports) bas += `<div class="supports">${s.supports} support(s) de cours, non comptés</div>`;
  return `<article class="carte anime" style="--i:${i}">
    <div class="tete"><div class="heure">${esc((s.heure || "").replace(/^0/, ""))}</div>
      <div class="titres"><div class="cours">${esc(s.cours)}</div><div class="section">${esc(s.titre)}</div>
        ${puces.length ? `<div class="puces">${puces.join("")}</div>` : ""}</div>
      <span class="info" title="Date : ${esc(s.precision)}">${ic("info")}</span></div>${bas}</article>`;
}

function pagesJour(ss) { return ss.flatMap(lecturesDe).filter(compte).reduce((a, l) => a + (l.pages || 0), 0); }
function jourComplet(ss) { const ls = ss.flatMap(lecturesDe).filter(compte); return ls.length > 0 && ls.every(l => l.fait); }

function planning() {
  if (!D) { $("#planning").innerHTML = [0, 1, 2].map(i => `<div class="squelette" style="height:${[120, 180, 140][i]}px;margin-bottom:12px"></div>`).join(""); return; }
  if (!D.seances.length) { $("#planning").innerHTML = `<div class="pause anime">${ic("calendrier")}<div><b>Aucune séance datée</b> dans cette période.</div></div>`; return; }
  const semaines = new Map();
  for (const s of D.seances) { const k = cle(lundi(jour(s.date))); if (!semaines.has(k)) semaines.set(k, []); semaines.get(k).push(s); }
  let html = "", i = 0;
  for (const [k, ss] of semaines) {
    const deb = jour(k), fin = new Date(deb); fin.setDate(fin.getDate() + 6);
    const titre = `Semaine du ${deb.getDate()}${deb.getMonth() !== fin.getMonth() ? " " + MOIS[deb.getMonth()] : ""} au ${fin.getDate()} ${MOIS[fin.getMonth()]}`;
    const actives = ss.filter(s => !s.sans_travail), p = pagesJour(actives);
    html += `<div class="semaine" data-semaine="${k}"><h2 class="anime" style="--i:${i++}">${titre}<span class="trait"></span>${p ? `<span class="charge">${p} p. · ≈ ${duree(p)}</span>` : ""}</h2>`;
    if (!actives.length) {
      const nom = ss.some(s => /intercalaire/i.test(s.titre)) ? "Semaine intercalaire" : "Pas de cours";
      html += `<div class="pause anime" style="--i:${i++}">${ic("pause")}<div><b>${nom}</b> · aucun cours cette semaine, annoncé dans Moodle par ${ss.length} cours.</div></div></div>`;
      continue;
    }
    const parJour = new Map();
    for (const s of actives) { if (!parJour.has(s.date)) parJour.set(s.date, []); parJour.get(s.date).push(s); }
    for (const [d, sj] of parJour) {
      const dj = jour(d), e = ecart(d), pj = pagesJour(sj);
      html += `<div class="jour ${jourComplet(sj) ? "complet" : ""}" data-jour="${d}">
        <div class="date"><div class="nom">${JOURS[dj.getDay()]}</div><div class="num">${dj.getDate()}<span class="coche-jour">${ic("check")}</span></div>
          <div class="mois">${MOIS[dj.getMonth()]}</div>
          ${e === 0 ? `<span class="relatif">Aujourd'hui</span>` : e === 1 ? `<span class="relatif">Demain</span>` : ""}
          ${pj ? `<div class="pages">${pj} p. à lire</div>` : ""}</div>
        <div class="seances">${sj.map(s => carte(s, i++)).join("")}</div></div>`;
    }
    html += `</div>`;
  }
  $("#planning").innerHTML = html;
}

/* =====================================================================  colonne de droite */
function rail() {
  const ech = (D?.echeances || []).slice().sort((a, b) => a.date.localeCompare(b.date)).map(e => {
    const d = new Date(e.date), n = ecart(e.date);
    const passee = e.manuelle && n < 0;
    const reste = e.retard ? `${ic("alerte")}En retard` : passee ? "Passée" : n === 0 ? "Aujourd'hui" : n === 1 ? "Demain" : `Dans ${n} jours`;
    const cls = e.retard ? "retard" : !passee && n <= 7 ? "proche" : "";
    const h = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    return `<li class="echeance ${cls}" ${e.manuelle ? `data-ech="${esc(e.id)}"` : ""}><div class="quand"><div class="j">${d.getDate()}</div><div class="m">${MOIS_COURT[d.getMonth()]}</div></div>
      <div><b>${esc(e.nom)}</b>${esc(e.cours)}<div class="reste">${reste}${!e.retard ? ` · ${h}` : ""}${e.manuelle ? " · ajoutée par toi" : ""}</div></div>
      ${e.manuelle ? `<button class="suppr" title="Supprimer">${ic("x")}</button>` : "<span></span>"}</li>`;
  }).join("") || `<li class="rien">Rien dans les 90 prochains jours.</li>`;
  const alertes = (D?.alertes || []).map(a => { const [c, t] = decoupe(a); return `<li title="${esc(t)}"><b>${esc(c)}</b>${esc(phrase(t))}</li>`; }).join("")
    || `<li class="rien">Aucune incohérence trouvée.</li>`;
  const survs = surv().map(x => `<li><b>${esc(x.cours)}</b>${esc(x.quand)} · ${esc(x.texte)}</li>`).join("") || `<li class="rien">Rien à surveiller.</li>`;
  const ch = D?.non_vus || [];
  const depuis = D?.non_vus_depuis ? new Date(D.non_vus_depuis) : null;
  const changements = ch.length
    ? ch.map(c => { const [a, b] = decoupe(c); return `<li><b>${esc(a)}</b>${esc(b)}</li>`; }).join("")
      + `<li class="rien">Relevés depuis le ${depuis ? `${depuis.getDate()} ${MOIS[depuis.getMonth()]}` : "?"}. Gardés jusqu'à ce que tu les marques comme vus.</li>`
    : D?.changements == null ? `<li class="rien">Première actualisation : rien à comparer.</li>` : `<li class="rien">Rien de nouveau dans Moodle.</li>`;
  const ouverts = new Set([...document.querySelectorAll(".panneau[open]")].map(p => p.id));
  const ouvert = (id, defaut) => (ouverts.size ? ouverts.has(id) : defaut) ? "open" : "";
  $("#rail").innerHTML = `
    <details class="panneau critique anime" style="--i:1" id="p-verifier" ${ouvert("p-verifier", (D?.alertes || []).length > 0)}><summary>${ic("alerte")}À vérifier<span class="compte">${(D?.alertes || []).length}</span>${ic("chevron", "chevron")}</summary><ul>${alertes}</ul>
      ${D?.non_controles?.length ? `<ul><li class="rien">Non contrôlés (réglage) : ${esc(D.non_controles.join(", "))}</li></ul>` : ""}</details>
    <details class="panneau alerte anime" style="--i:2" id="p-surveiller" ${ouvert("p-surveiller", false)}><summary>${ic("oeil")}À surveiller<span class="compte">${(D?.surveiller || []).length}</span>${ic("chevron", "chevron")}</summary><ul>${survs}</ul></details>
    <details class="panneau anime" style="--i:3" id="p-echeances" ${ouvert("p-echeances", true)}><summary>${ic("calendrier")}Échéances<span class="compte">${(D?.echeances || []).length}</span>${ic("chevron", "chevron")}</summary>
      <ul id="liste-echeances">${ech}</ul><button class="bouton ajouter" id="b-ajouter">${ic("plus")}Ajouter une échéance</button></details>
    <details class="panneau anime" style="--i:4" id="p-changements" ${ouvert("p-changements", ch.length > 0)}><summary>${ic("histoire")}Changements dans Moodle${ch.length ? `<span class="compte">${ch.length}</span>` : ""}${ic("chevron", "chevron")}</summary><ul>${changements}</ul>
      ${ch.length ? `<button class="bouton ajouter" id="b-vus">${ic("check")}Vu, effacer la liste</button>` : ""}</details>
    <details class="panneau anime" style="--i:5" id="p-legende" ${ouvert("p-legende", false)}><summary>${ic("info")}Comment lire${ic("chevron", "chevron")}</summary>
      <div class="legende">
        <div><span class="statut obligatoire">Obligatoire</span>Écrit par l'enseignant.</div>
        <div><span class="statut obligatoire">${ic("guillemet")}Obligatoire</span>D'après une consigne, citée.</div>
        <div><span class="statut facultatif">Complémentaire, facultatif</span>Non compté dans la charge.</div>
        <div><span class="statut deduit">À lire, déduit</span>Rien ne le dit : supposé.</div>
        <div><span class="puce">${ic("approx")}Date déduite</span>Comptée depuis une séance datée.</div>
      </div></details>
    <div class="pied">Lecture seule sur Moodle · ton suivi reste sur l'ordinateur</div>`;
  $("#liste-cours").innerHTML = [...new Set((D?.seances || []).map(s => s.cours))].map(c => `<option value="${esc(c)}">`).join("");
}

function entete() {
  const a = auj();
  $("#aujourdhui").textContent = `${JOURS[a.getDay()]} ${a.getDate()} ${MOIS[a.getMonth()]} ${a.getFullYear()}`;
  const j = G?.prefs.jours || 14;
  $("#segments").innerHTML = `<span class="curseur"></span>` + PERIODES.map(([v, n]) => `<button data-jours="${v}" aria-pressed="${v === j}">${n}</button>`).join("");
  $("#periode-select").innerHTML = PERIODES.map(([v, n]) => `<option value="${v}" ${v === j ? "selected" : ""}>${n}</option>`).join("")
    + (PERIODES.some(([v]) => v === j) ? "" : `<option value="${j}" selected>${j} jours</option>`);
  requestAnimationFrame(placerCurseur);
  if (D?.genere) {
    const min = Math.round((Date.now() - new Date(D.genere)) / 6e4);
    $("#maj").textContent = `Actualisé ${min < 1 ? "à l'instant" : min < 60 ? `il y a ${min} min` : min < 1440 ? `il y a ${Math.round(min / 60)} h` : `le ${new Date(D.genere).toLocaleDateString("fr-CH")}`}`;
  }
}
function placerCurseur() {
  const b = $("#segments button[aria-pressed=true]"), c = $("#segments .curseur");
  if (!b || !c) { if (c) c.style.width = 0; return; }
  c.style.left = b.offsetLeft + "px"; c.style.width = b.offsetWidth + "px";
}

function tout(premiere = true) { entete(); tuiles(premiere); planning(); rail(); }

/* =====================================================================  reglages (section du tiroir) */
function reglagesSemaine() {
  const p = G.prefs, vm = G.vitesse_mesuree;
  return `
    <div class="groupe"><h4>Vitesse de lecture</h4>
      <div class="choix">${G.profils.map(f => `<label title="${esc(f.origine)}"><input type="radio" name="vitesse" value="${f.vitesse}" ${f.vitesse === p.vitesse ? "checked" : ""}>${esc(f.nom)}<small>${f.vitesse} pages/h</small></label>`).join("")}</div>
      <div class="ligne-champ"><label for="r-vitesse">Ou précisément</label><input class="champ" type="number" min="1" max="80" id="r-vitesse" value="${p.vitesse}" style="width:76px"><span>pages/h</span></div>
      ${vm ? `<div class="ligne-champ"><span class="chemin">Ta vitesse mesurée : <b>${vm[0]} pages/h</b>, d'après ${vm[1]} lecture(s) chronométrée(s).</span><button class="bouton" id="r-mesuree">Utiliser</button></div>`
           : `<p>Pas encore de vitesse mesurée. Note le temps passé sur une lecture (champ « temps réel ») : ta vraie vitesse apparaîtra ici.</p>`}
    </div>
    <div class="groupe"><h4>Horaire des cours</h4>
      <div class="ligne-champ"><button class="bouton" id="r-horaire">${ic("calendrier")}Horaire des cours</button></div>
      <p>Importer ton horaire (.ics) aide à dater les séances et à choisir ton groupe.</p></div>
    <div class="groupe"><h4>Dossier</h4>
      <div class="ligne-champ"><span class="chemin">${esc(p.dossier)}</span><button class="bouton" id="r-dossier">${ic("dossier")}Changer</button></div>
      <p>Dossier de Ma semaine.md et de l'audit.</p></div>
    <div class="groupe" style="display:flex;flex-direction:column;gap:14px"><h4 style="margin:0">Options</h4>
      <label class="interrupteur"><span>Compter les pages des PDF<small style="display:block;color:var(--texte-3)">Télécharge les PDF de la période ; ils restent en cache dans le dossier des réglages.</small></span><input type="checkbox" id="r-pages" ${p.pages ? "checked" : ""}><span class="rail-i"></span></label>
      <label class="interrupteur"><span>Écrire aussi Ma semaine.md<small style="display:block;color:var(--texte-3)">Une copie lisible dans Obsidian ou un éditeur de texte.</small></span><input type="checkbox" id="r-md" ${p.export_md ? "checked" : ""}><span class="rail-i"></span></label>
      <label class="interrupteur"><span>Ma semaine activée<small style="display:block;color:var(--texte-3)">Fonction expérimentale. Désactivée, elle ne lit plus rien dans Moodle.</small></span><input type="checkbox" id="r-active" checked><span class="rail-i"></span></label>
    </div>
    <div class="groupe"><h4>Fichiers</h4><div class="ligne-champ">
      <button class="bouton" data-ouvrir="md">${ic("fichier")}Ma semaine.md</button><button class="bouton" data-ouvrir="dossier">${ic("dossier")}Ouvrir le dossier</button></div></div>`;
}
async function regler(cle, valeur) {
  const r = await api().regler(cle, valeur);
  if (r.erreur) { toast(r.erreur, "critique"); return false; }
  G = {...G, ...r}; return true;
}

/* =====================================================================  actions */
function chargement(o, texte) {
  occupe = o;
  barreOccupee(o, texte, "semaine");
  for (const b of ["#b-actualiser", "#b-audit"]) $(b).disabled = o;
  $("#b-actualiser").classList.toggle("tourne", o);
}
window.progression = t => { $("#statut-texte").textContent = t; };

async function actualiser() {
  if (occupe || !api() || !INFOS?.semaine_active) return;
  chargement(true, "Ma semaine : connexion à Moodle...");
  const r = await api().actualiser();
  chargement(false);
  $("#bandeaux").innerHTML = "";
  semainePrete = true;
  if (r.erreur) { bandeau(r.erreur); toast(r.erreur, "critique"); return; }
  const avant = D; G = {...G, ...r}; D = r.donnees;
  tout(true);
  if (r.avertissement) bandeau(r.avertissement, "alerte");
  const n = D.changements?.length || 0;
  toast(avant ? (n ? `Ma semaine actualisée : ${n} changement(s) dans Moodle.` : "Ma semaine actualisée : rien de changé dans Moodle.") : "Planning à jour.", "bon");
}
function bandeau(texte, genre = "") { $("#bandeaux").innerHTML = `<div class="bandeau ${genre}" role="alert">${ic("alerte")}<span class="texte">${esc(texte)}</span><button class="bouton" id="b-reessayer">Réessayer</button></div>`; }


async function audit() {
  if (occupe) return;
  chargement(true, "Relecture du semestre écoulé...");
  const r = await api().audit();
  chargement(false);
  if (r.erreur) { toast(r.erreur, "critique"); return; }
  const b = r.bilan, deb = jour(b.debut), fin = jour(b.fin);
  const total = c => c.enseignant + c.consigne + c.deduit;
  $("#audit").innerHTML = `
    <p style="margin:0;color:var(--texte-2)">Séances du ${deb.getDate()} ${MOIS[deb.getMonth()]} au ${fin.getDate()} ${MOIS[fin.getMonth()]}, déjà passées : compare avec ce que tu sais de chaque cours.</p>
    <table class="tableau"><thead><tr><th>Cours</th><th>Jour</th><th class="n">Séances</th><th class="n">Par numéro</th><th>Lectures : enseignant · consigne · déduites</th><th class="n">Sans lecture</th></tr></thead><tbody>
    ${b.cours.map(c => `<tr><td>${esc(c.nom)}</td><td data-l="Jour">${c.jour ? `${esc(c.jour)} <span style="color:var(--texte-3)">(${esc(c.source)})</span>` : "inconnu"}</td>
      <td class="n" data-l="Séances">${c.seances}</td><td class="n" data-l="Par numéro">${c.par_numero}</td>
      <td data-l="Lectures">${c.enseignant} · ${c.consigne} · ${c.deduit}${total(c) ? `<div class="barre-mini" title="bleu : écrit par l'enseignant · violet : consigne · gris : déduit">
        <span style="flex:${c.enseignant};background:var(--accent)"></span><span style="flex:${c.consigne};background:#6250d6"></span><span style="flex:${c.deduit};background:var(--bord-fort)"></span></div>` : ""}</td>
      <td class="n" data-l="Sans lecture">${c.sans_lecture}</td></tr>`).join("")}</tbody></table>
    <div class="groupe"><h4>À regarder</h4><ul style="margin:0;padding-left:18px">${b.a_regarder.map(x => `<li>${esc(x)}</li>`).join("") || "<li>Rien de suspect.</li>"}</ul></div>
    <div class="groupe"><h4>Contrôles sur la période (${b.alertes.length})</h4><ul style="margin:0;padding-left:18px">${b.alertes.map(x => `<li>${esc(x)}</li>`).join("") || "<li>Aucun.</li>"}</ul></div>
    <div class="groupe"><h4>Calendrier lu dans Moodle</h4><ul style="margin:0;padding-left:18px">${b.calendrier.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
    ${b.non_datees.length ? `<div class="groupe"><h4>Séances non datées</h4><ul style="margin:0;padding-left:18px">${b.non_datees.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}`;
  $("#d-audit").showModal();
  if (r.avertissement) toast(r.avertissement, "critique");
}

function trouverLecture(id) { for (const s of D.seances) for (const l of lecturesDe(s)) if (l.id === id) return [s, l]; return []; }

async function cocher(ligne, fait) {
  const [s, l] = trouverLecture(ligne.dataset.id); if (!l) return;
  l.fait = fait; ligne.classList.toggle("faite", fait);
  const c = ligne.querySelector(".case"); c.classList.remove("onde"); if (fait) { void c.offsetWidth; c.classList.add("onde"); }
  const bloc = ligne.closest(".jour");
  if (bloc) {
    const sj = D.seances.filter(x => x.date === bloc.dataset.jour && !x.sans_travail);
    const complet = jourComplet(sj), etait = bloc.classList.contains("complet");
    bloc.classList.toggle("complet", complet);
    if (complet && !etait) { eclats(bloc.querySelector(".coche-jour")); toast(`${bloc.querySelector(".nom").textContent} : toutes les lectures sont faites.`, "bon"); }
  }
  tuiles(false);
  if (toutes().filter(compte).every(x => x.fait) && fait) eclats($("#t-jauge"));
  await api().cocher(l.id, fait, l.pages);
}

async function noterTemps(champ) {
  const ligne = champ.closest(".lecture"), [, l] = trouverLecture(ligne.dataset.id); if (!l) return;
  const texte = champ.value.trim();
  if (!texte && !l.minutes) return;
  const r = await api().noter_temps(l.id, texte, l.pages);
  if (texte && !r.minutes) { champ.classList.remove("ko"); void champ.offsetWidth; champ.classList.add("ko"); toast("Temps illisible : écris par exemple 70 ou 1 h 10.", "critique"); return; }
  l.minutes = r.minutes; G.vitesse_mesuree = r.vitesse_mesuree;
  champ.value = r.minutes ? fmtMin(r.minutes) : ""; champ.classList.toggle("ok", !!r.minutes);
  if (r.minutes && !l.fait) { const i = ligne.querySelector(".case input"); i.checked = true; cocher(ligne, true); }
  if (r.minutes && r.vitesse_mesuree) toast(`Noté. Ta vitesse mesurée : ${r.vitesse_mesuree[0]} pages/h (${r.vitesse_mesuree[1]} lecture(s)).`, "bon");
}

/* =====================================================================  evenements */
document.addEventListener("change", async e => {
  const t = e.target;
  if (t.matches(".lecture .case input")) return cocher(t.closest(".lecture"), t.checked);
  if (t.matches(".temps")) return noterTemps(t);
  if (t.id === "periode-select") return changerPeriode(+t.value);
  if (t.name === "vitesse" || t.id === "r-vitesse") { if (await regler("vitesse", +t.value)) { remplirTiroir(); tout(false); } return; }
  if (t.id === "r-pages") return regler("pages", t.checked);
  if (t.id === "r-md") return regler("export_md", t.checked);
  if (t.id === "r-active" && !t.checked) {
    if (await regler("active", false)) { INFOS.semaine_active = false; ouvrirTiroir(false); vueSemaine(); toast("Ma semaine désactivée.", "bon"); }
    else t.checked = true;
  }
});
document.addEventListener("keydown", e => {
  if (e.target.matches && e.target.matches(".temps") && e.key === "Enter") e.target.blur();
});
async function changerPeriode(j) {
  if (occupe || j === G.prefs.jours) return;
  if (await regler("jours", j)) { entete(); actualiser(); }
}
document.addEventListener("click", async e => {
  const t = e.target.closest("button, .tuile.cliquable"); if (!t) return;
  if (t.dataset.jours) return changerPeriode(+t.dataset.jours);
  if (t.id === "b-actualiser" || t.id === "b-reessayer") return actualiser();
  if (t.id === "b-audit") return audit();
  if (t.id === "b-horaire" || t.id === "r-horaire") return ouvrirHoraire();
  if (t.id === "b-activer") return activerSemaine();
  if (t.id === "b-vus") {
    await api().changements_vus();
    D.non_vus = []; D.non_vus_depuis = null;
    D.seances.forEach(s => s.lectures.forEach(l => { l.nouveau = false; }));
    return tout(false);
  }
  if (t.id === "b-ajouter") { const f = $("#f-echeance"); f.reset(); f.date.value = cle(auj()); return $("#d-echeance").showModal(); }
  if (t.id === "r-dossier") { G = {...G, ...(await api().choisir_dossier())}; return remplirTiroir(); }
  if (t.id === "r-mesuree") { if (await regler("vitesse", Math.max(1, Math.round(G.vitesse_mesuree[0])))) { remplirTiroir(); tout(false); toast("Vitesse mesurée appliquée.", "bon"); } return; }
  if (t.dataset.ouvrir) { const r = await api().ouvrir(t.dataset.ouvrir); if (r.erreur) toast(r.erreur, "critique"); return; }
  if (t.id === "b-ouvrir-audit") { const r = await api().ouvrir("audit"); if (r.erreur) toast(r.erreur, "critique"); return; }
  if (t.classList.contains("suppr")) {
    const li = t.closest(".echeance"); li.classList.add("sort");
    const r = await api().supprimer_echeance(li.dataset.ech);
    if (r.erreur) { li.classList.remove("sort"); return toast(r.erreur, "critique"); }
    D.echeances = D.echeances.filter(x => !x.manuelle).concat(r.echeances.map(x => ({...x, manuelle: true, retard: false})));
    setTimeout(() => { rail(); tuiles(false); }, 280); return;
  }
  if (t.dataset.panneau) { const p = document.getElementById(t.dataset.panneau); p.open = true; p.scrollIntoView({behavior: "smooth", block: "center"}); }
});
$("#f-echeance").addEventListener("submit", async e => {
  const f = e.target;
  if (!e.submitter || e.submitter.value !== "ok") return;
  const r = await api().ajouter_echeance(f.date.value, f.heure.value, f.cours.value, f.nom.value);
  if (r.erreur) { e.preventDefault(); return toast(r.erreur, "critique"); }
  D.echeances = D.echeances.filter(x => !x.manuelle).concat(r.echeances.map(x => ({...x, manuelle: true, retard: false})));
  rail(); tuiles(false); toast("Échéance ajoutée.", "bon");
});
addEventListener("resize", placerCurseur);

/* =====================================================================  horaire (module horaire.js, fourni a part) */
function ouvrirHoraire() {
  const d = $("#d-horaire"), zone = $("#horaire");
  zone.innerHTML = "";
  if (window.Horaire && typeof window.Horaire.monter === "function") {
    try { window.Horaire.monter(zone, api()); }
    catch (e) { zone.innerHTML = `<p class="rien">L'écran de l'horaire n'a pas pu s'afficher.</p>`; }
  } else zone.innerHTML = `<p class="rien">L'import de l'horaire n'est pas disponible dans cette version.</p>`;
  if (!d.open) d.showModal();
}

/* =====================================================================  activation et demarrage */
let semainePrete = false;          // pour etatVerification : premiere actualisation terminee (ou impossible)
function vueSemaine() {
  const on = !!(INFOS && INFOS.semaine_active);
  $("#semaine-off").hidden = on; $("#semaine-on").hidden = !on;
  majActions();
}
async function activerSemaine() {
  const b = $("#b-activer"); if (b) b.disabled = true;
  const r = await api().regler("active", true);
  if (b) b.disabled = false;
  if (r.erreur) return toast(r.erreur, "critique");
  INFOS.semaine_active = true;
  await demarrerSemaine();
}
async function demarrerSemaine() {
  vueSemaine();
  if (!INFOS.semaine_active) { semainePrete = true; return; }
  const r = await api().demarrer();
  if (r.erreur) { semainePrete = true; bandeau(r.erreur); return; }
  G = r; D = r.donnees;
  tout(true);
  await actualiser();
}
