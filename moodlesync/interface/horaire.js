/* Ecran Horaire de Ma semaine : import d'un .ics (fichier ou abonnement), groupes suivis, cours Moodle.
   Contrat : window.Horaire.monter(conteneur, api), conteneur = element vide, api = window.pywebview.api.
   Tout le texte venu de Python ou du .ics est echappe. Aucune requete reseau depuis la page. */
(function () {
  "use strict";
  const JOURS_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
                      "octobre", "novembre", "décembre"];

  function esc(t) {
    return String(t ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  }
  function dateCourte(iso) {
    if (!iso) return "";
    const [a, m, j] = iso.slice(0, 10).split("-").map(Number);
    return `${j} ${JOURS_MOIS[m - 1]} ${a}`;
  }
  function heure(iso) { return iso && iso.length > 10 ? iso.slice(11, 16) : ""; }

  function monter(conteneur, api) {
    let etat = null, occupe = false, message = null;

    async function appeler(promesse, attente) {
      if (occupe) return;
      occupe = true; message = attente ? {texte: attente, genre: ""} : null; rendre();
      try {
        const r = await promesse();
        if (r && r.erreur) { message = {texte: r.erreur, genre: "critique"}; }
        else if (r) { etat = r; message = null; }
      } catch (e) {
        message = {texte: "L'application n'a pas répondu. Ferme et rouvre la fenêtre.", genre: "critique"};
      }
      occupe = false; rendre();
    }

    function entete() {
      const s = etat && etat.source;
      let src = "Aucun horaire importé.";
      if (s) {
        const quoi = s.type === "abonnement" ? `abonnement (${esc(s.nom)})` : `fichier ${esc(s.nom)}`;
        src = `Importé le ${esc(dateCourte(s.importe))} à ${esc(heure(s.importe))}, depuis ${quoi}.`;
      }
      const per = etat && etat.periode ? ` Séances du ${esc(dateCourte(etat.periode[0]))} au ${esc(dateCourte(etat.periode[1]))} ;
        en dehors, les dates restent celles lues dans Moodle.` : "";
      return `<div class="hor-tete">
        <p class="hor-aide">Ton horaire de cours, exporté depuis le site de ton établissement ou ton agenda (fichier .ics).
          Il sert à dater les séances que Moodle numérote sans date, et à repérer les semaines sans cours.</p>
        <p class="hor-source">${src}${per}</p>
        <div class="hor-actions">
          <button class="bouton principal" data-h="fichier" ${occupe ? "disabled" : ""}>Importer un fichier .ics</button>
          <button class="bouton" data-h="moodle" ${occupe ? "disabled" : ""}>Relire mes cours Moodle</button>
        </div>
        <details class="hor-abo" ${etat && etat.abonnement ? "open" : ""}>
          <summary>Abonnement par adresse (facultatif)</summary>
          <p class="hor-aide">Colle le lien d'abonnement de ton horaire (https:// ou webcal://). MoodleSync le relira
            à chaque actualisation de Ma semaine : c'est alors le seul accès réseau en dehors de Moodle. Le lien
            reste sur cet ordinateur ; il peut contenir un code personnel, ne le partage pas.</p>
          <div class="hor-ligne">
            <input type="url" class="hor-adresse" placeholder="https://..." value="${esc(etat && etat.abonnement || "")}" ${occupe ? "disabled" : ""}>
            <button class="bouton" data-h="abonner" ${occupe ? "disabled" : ""}>${etat && etat.abonnement ? "Relire" : "S'abonner"}</button>
            ${etat && etat.abonnement ? `<button class="bouton" data-h="retirer" ${occupe ? "disabled" : ""}>Retirer</button>` : ""}
          </div>
        </details></div>`;
    }

    function messages() {
      const out = [];
      if (message) out.push(`<div class="hor-message ${esc(message.genre)}">${esc(message.texte)}</div>`);
      const ea = etat && etat.erreur_abonnement;
      if (ea) out.push(`<div class="hor-message critique">Dernière relecture de l'abonnement impossible
        (${esc(dateCourte(ea.quand))}) : ${esc(ea.message)} L'horaire déjà importé est gardé.</div>`);
      const av = (etat && etat.avertissements) || [];
      if (av.length) out.push(`<div class="hor-message alerte"><b>Non lu dans le fichier :</b><ul>${
        av.map(a => `<li>${esc(a)}</li>`).join("")}</ul></div>`);
      return out.join("");
    }

    function selecteur(c) {
      const choisi = c.confirme ?? c.propose ?? "";
      const opts = [`<option value="" ${choisi === "" ? "selected" : ""}>Choisir le cours Moodle...</option>`]
        .concat((etat.cours_moodle || []).map(m => `<option value="${esc(m.id)}" ${String(choisi) === String(m.id) ? "selected" : ""}>${esc(m.nom)}</option>`))
        .concat([`<option value="aucun" ${choisi === "aucun" ? "selected" : ""}>Aucun : ce cours n'est pas dans Moodle</option>`]);
      let etatTexte = "";
      if (c.confirme === "aucun") etatTexte = `<span class="hor-puce">ignoré</span>`;
      else if (c.confirme) etatTexte = `<span class="hor-puce bon">confirmé</span>`;
      else if (c.propose) etatTexte = `<span class="hor-puce alerte">proposé, à confirmer</span>
        <button class="bouton petit" data-h="confirmer" data-cours="${esc(c.id)}" data-cid="${esc(c.propose)}">Confirmer</button>`;
      else etatTexte = `<span class="hor-puce alerte">à rapprocher</span>`;
      return `<div class="hor-ligne"><select class="hor-moodle" data-cours="${esc(c.id)}" aria-label="Cours Moodle de ${esc(c.intitule)}" ${occupe ? "disabled" : ""}>${opts.join("")}</select>${etatTexte}</div>`;
    }

    function cours() {
      if (!etat || !etat.cours.length) return "";
      return `<div class="hor-cours">${etat.cours.map(c => `
        <section class="hor-carte ${c.a_choisir ? "a-choisir" : ""}">
          <h4>${esc(c.intitule)}${c.a_choisir ? ` <span class="hor-puce alerte">groupe à choisir</span>` : ""}</h4>
          ${selecteur(c)}
          ${c.groupes.length > 1 ? `<p class="hor-aide">${c.groupes.length} groupes dans ton horaire : coche celui ou ceux que tu suis.</p>` : ""}
          <ul class="hor-groupes">${c.groupes.map(g => `
            <li><label><input type="checkbox" data-h="groupe" data-cours="${esc(c.id)}" data-groupe="${esc(g.id)}" ${g.suivi ? "checked" : ""} ${occupe ? "disabled" : ""}>
              <span>${esc(g.libelle)}</span></label></li>`).join("")}</ul>
        </section>`).join("")}</div>
        <p class="hor-aide">Un cours n'est utilisé pour dater les séances qu'une fois son cours Moodle confirmé et au moins un groupe coché.</p>`;
    }

    function rendre() {
      conteneur.innerHTML = `<div class="horaire">${entete()}${messages()}${
        occupe ? `<p class="hor-aide">Un instant...</p>` : ""}${cours()}</div>`;
    }

    conteneur.addEventListener("click", e => {
      const b = e.target.closest("button[data-h]"); if (!b || occupe) return;
      const h = b.dataset.h;
      if (h === "fichier") appeler(() => api.horaire_importer_fichier(), "Lecture du fichier...");
      else if (h === "moodle") appeler(() => api.horaire_cours_moodle(), "Lecture de tes cours dans Moodle...");
      else if (h === "abonner") appeler(() => api.horaire_abonnement(conteneur.querySelector(".hor-adresse").value), "Lecture de l'horaire en ligne...");
      else if (h === "retirer") appeler(() => api.horaire_abonnement(""), null);
      else if (h === "confirmer") appeler(() => api.horaire_confirmer(b.dataset.cours, b.dataset.cid), null);
    });
    conteneur.addEventListener("change", e => {
      const t = e.target; if (occupe) return;
      if (t.matches("input[data-h=groupe]")) appeler(() => api.horaire_groupe(t.dataset.cours, t.dataset.groupe, t.checked), null);
      else if (t.matches("select.hor-moodle")) appeler(() => api.horaire_confirmer(t.dataset.cours, t.value || null), null);
    });

    rendre();
    appeler(() => api.horaire_etat(), null);
  }

  window.Horaire = {monter};
})();
