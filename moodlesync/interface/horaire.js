/* Ecran Horaire de Ma semaine : planning visuel de la semaine (cours + creneaux libres) et, en option,
   import d'un .ics (fichier ou abonnement), groupes suivis, rapprochement avec Moodle.
   Contrat : window.Horaire.monter(conteneur, api), conteneur = element vide, api = window.pywebview.api.
   Tout le texte venu de Python ou du .ics est echappe. Aucune requete reseau depuis la page. */
(function () {
  "use strict";
  const JOURS_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
                      "octobre", "novembre", "décembre"];
  const JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];
  const COULEURS = ["#2a78d6", "#1baf7a", "#eda100", "#e87ba4", "#6250d6", "#00a2ae", "#d6892a", "#8a7be8"];
  const COULEUR_LIBRE = "#0ca30c";
  const DEBUT = 8 * 60, FIN = 20 * 60, PAS = 30, HAUTEUR = 32;   // grille : 8 h a 20 h, pas de 30 min
  const DUREE_DEFAUT = 105, DUREE_LIBRE = 60;                     // durees proposees (cours, creneau libre)
  const DUREE_MIN = 30, DUREE_MAX = 600;                          // bornes, alignees sur le moteur (horaire.py)
  const FREQUENCES = [["semaine", "Chaque semaine"], ["2semaines", "1 semaine sur 2"],
                      ["3semaines", "1 semaine sur 3"], ["mois", "Tous les mois"]];
  const FREQ_COURT = {semaine: "", "2semaines": "1 sem. sur 2", "3semaines": "1 sem. sur 3", mois: "mensuel"};

  function esc(t) {
    return String(t ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  }
  function dateCourte(iso) {
    if (!iso) return "";
    const [a, m, j] = iso.slice(0, 10).split("-").map(Number);
    return `${j} ${JOURS_MOIS[m - 1]} ${a}`;
  }
  function heure(iso) { return iso && iso.length > 10 ? iso.slice(11, 16) : ""; }
  function minute(hhmm) { const [h, m] = String(hhmm).split(":").map(Number); return h * 60 + m; }
  function hhmm(t) { return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`; }
  function fmtDuree(min) {
    if (min < 60) return `${min} min`;
    const h = Math.floor(min / 60), m = min % 60;
    return m ? `${h} h ${String(m).padStart(2, "0")}` : `${h} h`;
  }
  function fmtHeures(h) { return fmtDuree(Math.round(h * 60)); }
  function couleur(cid) {
    let n = 0;
    for (const c of String(cid)) n = (n * 31 + c.charCodeAt(0)) >>> 0;
    return COULEURS[n % COULEURS.length];
  }

  function monter(conteneur, api) {
    let etat = null, occupe = false, message = null, selection = null, blocActif = null;
    let redimension = null, vientRedimension = false;   // poignee de redimensionnement des blocs
    let deplacement = null, vientDeplacement = false;   // deplacement des blocs (glisser au sein de l'agenda)

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

    /* ============================================================  blocs (cours + libres) */
    function nomCours(cid) {
      const c = (etat.cours_moodle || []).find(x => String(x.id) === String(cid));
      if (c) return c.nom;
      const b = (etat.blocs || []).find(x => String(x.cid) === String(cid));
      return (b && b.titre) || String(cid);
    }

    function blocsTous() {
      const cours = (etat.blocs || []).map(b => ({type: "cours", cle: "cours:" + b.cid, cid: b.cid,
        jour: b.jour, heure: b.heure, duree: b.duree, nom: nomCours(b.cid)}));
      const libres = (etat.libres || []).map(b => {
        const freq = b.frequence || "semaine";
        return {type: "libre", cle: "libre:" + b.id, id: b.id, jour: b.jour, heure: b.heure,
          duree: b.duree, frequence: freq, nom: "Temps libre" + (FREQ_COURT[freq] ? ` (${FREQ_COURT[freq]})` : "")};
      });
      return [...cours, ...libres];
    }
    function trouverBloc(cle) { return blocsTous().find(b => b.cle === cle); }
    function couleurBloc(b) { return b.type === "libre" ? COULEUR_LIBRE : couleur(b.cid); }
    function sauverBlocActif(b) {
      return b.type === "cours" ? api.horaire_bloc(b.cid, b.jour, b.heure, b.duree)
                                : api.horaire_libre(b.jour, b.heure, b.duree, b.id, b.frequence);
    }
    function retirerBlocActif(b) {
      return b.type === "cours" ? api.horaire_supprimer_bloc(b.cid) : api.horaire_supprimer_libre(b.id);
    }

    function palette() {
      const cours = etat.cours_moodle || [];
      const places = new Set((etat.blocs || []).map(b => String(b.cid)));
      const chipLibre = `<li><button type="button" class="ed-cours ed-libre ${selection?.type === "libre" ? "choisi" : ""}"
        data-libre="1" draggable="true" title="Ajouter un créneau libre (pour lire)"><span class="ed-point" style="background:${COULEUR_LIBRE}"></span>
        <span class="ed-cours-nom">Temps libre</span><span class="ed-cours-marque"><svg><use href='#i-plus'/></svg></span></button></li>`;
      const lignes = cours.map(c => {
        const cid = String(c.id), estPlace = places.has(cid);
        return `<li><button type="button" class="ed-cours ${estPlace ? "place" : ""} ${selection?.type === "cours" && selection.cid === cid ? "choisi" : ""}"
          data-cid="${esc(cid)}" draggable="true" title="${estPlace ? "Déjà placé : clique pour le déplacer" : "Clique pour le placer"}">
          <span class="ed-point" style="background:${couleur(cid)}"></span>
          <span class="ed-cours-nom">${esc(c.nom)}</span>
          <span class="ed-cours-marque">${estPlace ? "<svg><use href='#i-check'/></svg>" : "<svg><use href='#i-plus'/></svg>"}</span>
        </button></li>`;
      }).join("");
      const aide = selection ? (selection.type === "libre"
        ? "Place un créneau libre : clique sur une case de la grille."
        : `Place maintenant « ${esc(nomCours(selection.cid))} » : clique sur une case de la grille.`)
        : "Clique un cours (ou « Temps libre ») puis une case de la grille, ou glisse-le.";
      const aCours = etat.heures_cours, aLibres = etat.heures_libres;
      const total = (aCours || aLibres)
        ? `${aCours ? fmtHeures(aCours) + " de cours" : ""}${aCours && aLibres ? " · " : ""}${aLibres ? fmtHeures(aLibres) + " libres" : ""} / semaine`
        : "Aucun bloc placé.";
      return `<div class="ed-palette">
        <h4>Tes cours et ton temps libre</h4>
        <p class="hor-aide">${aide}</p>
        <ul class="ed-cours-liste">${chipLibre}${lignes || `<li class="rien">Aucun cours Moodle lu : connecte-toi (onglet Synchroniser), puis « Relire mes cours Moodle ».</li>`}</ul>
        <div class="ed-total">${total}</div>
      </div>`;
    }

    function heuresOptions(sel) {
      let out = "";
      for (let t = DEBUT; t < FIN; t += PAS) out += `<option value="${hhmm(t)}" ${hhmm(t) === sel ? "selected" : ""}>${hhmm(t)}</option>`;
      return out;
    }

    function barreBloc() {
      if (!blocActif) return "";
      const b = trouverBloc(blocActif);
      if (!b) return "";
      return `<div class="ed-barre">
        <span class="ed-barre-nom">${esc(b.nom)}</span>
        <select class="ed-sel-jour" aria-label="Jour">${JOURS.map((n, j) => `<option value="${j}" ${b.jour === j ? "selected" : ""}>${n}</option>`).join("")}</select>
        <select class="ed-sel-heure" aria-label="Heure de début">${heuresOptions(b.heure)}</select>
        <div class="ed-durees"><button type="button" class="ed-duree" data-pas="-30" title="30 minutes de moins">−30</button><span class="ed-duree-texte">${fmtDuree(b.duree)}</span><button type="button" class="ed-duree" data-pas="30" title="30 minutes de plus">+30</button></div>
        ${b.type === "libre" ? `<select class="ed-sel-freq" aria-label="Fréquence">${FREQUENCES.map(([v, n]) => `<option value="${v}" ${b.frequence === v ? "selected" : ""}>${n}</option>`).join("")}</select>` : ""}
        <span class="espace"></span>
        <button type="button" class="bouton petit ed-retirer">Retirer</button>
      </div>`;
    }

    function grille() {
      const blocs = blocsTous();
      let heures = "";
      for (let t = DEBUT; t < FIN; t += PAS) {
        if ((t - DEBUT) % 60 === 0) heures += `<div class="ed-heure" style="top:${(t - DEBUT) / PAS * HAUTEUR}px">${hhmm(t)}</div>`;
      }
      const titres = JOURS.map(n => `<div class="ed-jour-titre">${n}</div>`).join("");
      let corps = "";
      for (let j = 0; j < 7; j++) {
        let cellules = "";
        for (let t = DEBUT; t < FIN; t += PAS) cellules += `<div class="ed-case" data-jour="${j}" data-heure="${hhmm(t)}"></div>`;
        const blocsJour = blocs.filter(b => b.jour === j).map(b => {
          const top = (minute(b.heure) - DEBUT) / PAS * HAUTEUR;
          const haut = Math.max(PAS, b.duree) / PAS * HAUTEUR;
          const style = b.type === "libre"
            ? `top:${top}px;height:${haut}px;border-color:var(--bon)`
            : `top:${top}px;height:${haut}px;background:color-mix(in srgb, ${couleurBloc(b)} 16%, var(--carte));border-color:${couleurBloc(b)}`;
          return `<button type="button" class="ed-bloc ${b.type === "libre" ? "libre" : ""} ${blocActif === b.cle ? "actif" : ""}"
            data-cle="${esc(b.cle)}" style="${style}" title="${esc(b.nom)} · ${esc(b.heure)} à ${esc(hhmm(minute(b.heure) + b.duree))}">
            <span class="ed-bloc-heure">${esc(b.heure)}</span><span class="ed-bloc-nom">${esc(b.nom)}</span>
            <span class="ed-poignee" title="Tirer pour ajuster la durée"></span></button>`;
        }).join("");
        corps += `<div class="ed-jour-corps" data-jour="${j}">${cellules}${blocsJour}</div>`;
      }
      return `<div class="ed-grille"><div class="ed-coin"></div>${titres}<div class="ed-heures">${heures}</div>${corps}</div>`;
    }

    function planning() {
      return `<div class="editeur">
        ${palette()}
        <div class="ed-droit">${grille()}${barreBloc()}</div>
      </div>`;
    }

    /* ============================================================  import .ics (conserve) */
    function entete() {
      const s = etat && etat.source;
      let src = "Aucun .ics importé.";
      if (s) {
        const quoi = s.type === "abonnement" ? `abonnement (${esc(s.nom)})` : `fichier ${esc(s.nom)}`;
        src = `Importé le ${esc(dateCourte(s.importe))} à ${esc(heure(s.importe))}, depuis ${quoi}.`;
      }
      const per = etat && etat.periode ? ` Séances du ${esc(dateCourte(etat.periode[0]))} au ${esc(dateCourte(etat.periode[1]))}.` : "";
      return `<details class="ed-ics" ${etat && etat.source ? "open" : ""}>
        <summary>Ou importer un fichier .ics / un abonnement (facultatif)</summary>
        <p class="hor-aide">Exporte ton emploi du temps depuis le site de ton établissement (fichier .ics), ou colle un lien d'abonnement. Il sert à dater les séances que Moodle numérote sans date, et à repérer les semaines sans cours. Il complète (sans l'effacer) ce que tu as posé à la main ci-dessus.</p>
        <p class="hor-source">${src}${per}</p>
        <div class="hor-actions">
          <button class="bouton" data-h="fichier" ${occupe ? "disabled" : ""}>Importer un fichier .ics</button>
          <button class="bouton" data-h="moodle" ${occupe ? "disabled" : ""}>Relire mes cours Moodle</button>
        </div>
        <div class="hor-ligne">
          <input type="url" class="hor-adresse" placeholder="https://... (abonnement)" value="${esc(etat && etat.abonnement || "")}" ${occupe ? "disabled" : ""}>
          <button class="bouton" data-h="abonner" ${occupe ? "disabled" : ""}>${etat && etat.abonnement ? "Relire" : "S'abonner"}</button>
          ${etat && etat.abonnement ? `<button class="bouton" data-h="retirer" ${occupe ? "disabled" : ""}>Retirer</button>` : ""}
        </div>
        ${etat && etat.cours ? coursICS() : ""}
      </details>`;
    }

    function coursICS() {
      return `<div class="hor-cours" style="margin-top:12px">${etat.cours.map(c => `
        <section class="hor-carte ${c.a_choisir ? "a-choisir" : ""}">
          <h4>${esc(c.intitule)}${c.a_choisir ? ` <span class="hor-puce alerte">groupe à choisir</span>` : ""}</h4>
          ${selecteur(c)}
          ${c.groupes.length > 1 ? `<p class="hor-aide">${c.groupes.length} groupes : coche celui ou ceux que tu suis.</p>` : ""}
          <ul class="hor-groupes">${c.groupes.map(g => `
            <li><label><input type="checkbox" data-h="groupe" data-cours="${esc(c.id)}" data-groupe="${esc(g.id)}" ${g.suivi ? "checked" : ""} ${occupe ? "disabled" : ""}>
              <span>${esc(g.libelle)}</span></label></li>`).join("")}</ul>
        </section>`).join("")}</div>`;
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

    function messages() {
      const out = [];
      if (message) out.push(`<div class="hor-message ${esc(message.genre)}">${esc(message.texte)}</div>`);
      const ea = etat && etat.erreur_abonnement;
      if (ea) out.push(`<div class="hor-message critique">Dernière relecture de l'abonnement impossible
        (${esc(dateCourte(ea.quand))}) : ${esc(ea.message)} L'horaire déjà importé est gardé.</div>`);
      const av = (etat && etat.avertissements) || [];
      if (av.length) out.push(`<div class="hor-message alerte"><b>Non lu dans le fichier :</b><ul>${av.map(a => `<li>${esc(a)}</li>`).join("")}</ul></div>`);
      return out.join("");
    }

    function rendre() {
      conteneur.innerHTML = `<div class="horaire">
        <p class="hor-aide">Pose tes cours et tes créneaux libres sur la grille : chaque cours un jour, une heure, une durée ; les créneaux « Temps libre » servent à estimer ton temps de lecture disponible.</p>
        ${messages()}${occupe ? `<p class="hor-aide">Un instant...</p>` : ""}
        ${etat ? planning() + entete() : ""}
      </div>`;
    }

    /* ============================================================  evenements */
    conteneur.addEventListener("click", e => {
      if (vientRedimension || vientDeplacement) { vientRedimension = vientDeplacement = false; return; }
      if (e.target.closest(".ed-poignee")) return;                  // la poignee sert au glisser, pas au clic
      const b = e.target.closest("button, .ed-case"); if (!b || occupe) return;

      if (b.classList.contains("ed-cours")) {
        if (b.dataset.libre !== undefined) selection = selection?.type === "libre" ? null : {type: "libre"};
        else {
          const cid = b.dataset.cid;
          selection = (selection?.type === "cours" && selection.cid === cid) ? null : {type: "cours", cid};
        }
        blocActif = null; rendre(); return;
      }
      if (b.classList.contains("ed-case")) {
        if (!selection) return;
        const j = +b.dataset.jour, h = b.dataset.heure;
        if (selection.type === "libre") appeler(() => api.horaire_libre(j, h, DUREE_LIBRE), "Enregistrement...");
        else appeler(() => api.horaire_bloc(selection.cid, j, h, DUREE_DEFAUT), "Enregistrement...");
        selection = null; blocActif = null; return;
      }
      if (b.classList.contains("ed-bloc")) {
        blocActif = blocActif === b.dataset.cle ? null : b.dataset.cle;
        selection = null; rendre(); return;
      }
      if (b.classList.contains("ed-duree")) {
        const bl = trouverBloc(blocActif); if (!bl) return;
        const duree = Math.min(DUREE_MAX, Math.max(DUREE_MIN, bl.duree + (+b.dataset.pas)));
        if (duree !== bl.duree) appeler(() => sauverBlocActif({...bl, duree}), null);
        return;
      }
      if (b.classList.contains("ed-retirer")) {
        const bl = trouverBloc(blocActif); blocActif = null; if (!bl) return;
        return appeler(() => retirerBlocActif(bl), null);
      }

      const h = b.dataset.h;
      if (h === "fichier") appeler(() => api.horaire_importer_fichier(), "Lecture du fichier...");
      else if (h === "moodle") appeler(() => api.horaire_cours_moodle(), "Lecture de tes cours dans Moodle...");
      else if (h === "abonner") appeler(() => api.horaire_abonnement(conteneur.querySelector(".hor-adresse").value), "Lecture de l'horaire en ligne...");
      else if (h === "retirer") appeler(() => api.horaire_abonnement(""), null);
      else if (h === "confirmer") appeler(() => api.horaire_confirmer(b.dataset.cours, b.dataset.cid), null);
    });

    conteneur.addEventListener("change", e => {
      const t = e.target; if (occupe) return;
      if (t.matches("input[data-h=groupe]")) return appeler(() => api.horaire_groupe(t.dataset.cours, t.dataset.groupe, t.checked), null);
      if (t.matches("select.hor-moodle")) return appeler(() => api.horaire_confirmer(t.dataset.cours, t.value || null), null);
      if (t.matches(".ed-sel-jour") || t.matches(".ed-sel-heure")) {
        const bl = trouverBloc(blocActif); if (!bl) return;
        const jour = t.matches(".ed-sel-jour") ? +t.value : bl.jour;
        const heure = t.matches(".ed-sel-heure") ? t.value : bl.heure;
        return appeler(() => sauverBlocActif({...bl, jour, heure}), null);
      }
      if (t.matches(".ed-sel-freq")) {
        const bl = trouverBloc(blocActif); if (!bl) return;
        return appeler(() => sauverBlocActif({...bl, frequence: t.value}), null);
      }
    });

    // glisser-deposer : un cours (ou « Temps libre ») de la palette vers une case de la grille.
    conteneur.addEventListener("dragstart", e => {
      const c = e.target.closest(".ed-cours"); if (!c) return;
      e.dataTransfer.setData("text/plain", c.dataset.libre !== undefined ? "libre" : "cours:" + c.dataset.cid);
      e.dataTransfer.effectAllowed = "move";
    });
    conteneur.addEventListener("dragover", e => {
      const cas = e.target.closest(".ed-case"); if (!cas || occupe) return;
      e.preventDefault(); e.dataTransfer.dropEffect = "move";
      cas.classList.add("survol");
    });
    conteneur.addEventListener("dragleave", e => {
      const cas = e.target.closest(".ed-case"); if (cas) cas.classList.remove("survol");
    });
    conteneur.addEventListener("drop", e => {
      const cas = e.target.closest(".ed-case"); if (!cas) return;
      e.preventDefault(); cas.classList.remove("survol");
      const data = e.dataTransfer.getData("text/plain"); if (!data || occupe) return;
      const j = +cas.dataset.jour, h = cas.dataset.heure;
      if (data === "libre") appeler(() => api.horaire_libre(j, h, DUREE_LIBRE), "Enregistrement...");
      else appeler(() => api.horaire_bloc(data.slice(6), j, h, DUREE_DEFAUT), "Enregistrement...");
    });

    // redimensionner (poignee) ou deplacer (corps) un bloc, a la Google Agenda.
    function caseSousCurseur(x, y) {
      const el = document.elementFromPoint(x, y);
      return el ? el.closest(".ed-case") : null;
    }
    conteneur.addEventListener("pointerdown", e => {
      if (occupe) return;
      const poignee = e.target.closest(".ed-poignee");
      if (poignee) {
        const blocEl = poignee.closest(".ed-bloc"), bl = trouverBloc(blocEl.dataset.cle); if (!bl) return;
        e.preventDefault();
        poignee.setPointerCapture(e.pointerId);
        redimension = {cle: bl.cle, y0: e.clientY, duree0: bl.duree, duree: bl.duree, el: blocEl};
        blocEl.classList.add("redimension");
        return;
      }
      const blocEl = e.target.closest(".ed-bloc");
      if (blocEl) {
        const bl = trouverBloc(blocEl.dataset.cle); if (!bl) return;
        deplacement = {cle: bl.cle, x0: e.clientX, y0: e.clientY, el: blocEl, actif: false, cible: null};
      }
    });
    document.addEventListener("pointermove", e => {
      if (redimension) {
        const pas = Math.round((e.clientY - redimension.y0) / HAUTEUR);
        const duree = Math.min(DUREE_MAX, Math.max(DUREE_MIN, redimension.duree0 + pas * PAS));
        if (duree !== redimension.duree) {
          redimension.duree = duree;
          redimension.el.style.height = (duree / PAS * HAUTEUR) + "px";
        }
      }
      if (deplacement) {
        if (!deplacement.actif) {
          if (Math.hypot(e.clientX - deplacement.x0, e.clientY - deplacement.y0) < 6) return;
          deplacement.actif = true;
          deplacement.el.classList.add("deplace");
          deplacement.el.style.pointerEvents = "none";
        }
        const cas = caseSousCurseur(e.clientX, e.clientY);
        if (cas !== deplacement.cible) {
          if (deplacement.cible) deplacement.cible.classList.remove("survol");
          deplacement.cible = cas;
          if (cas) cas.classList.add("survol");
        }
      }
    });
    function finRedimension() {
      if (!redimension) return;
      const r = redimension; redimension = null;
      r.el.classList.remove("redimension");
      if (r.duree !== r.duree0) {
        vientRedimension = true;
        setTimeout(() => { vientRedimension = false; }, 400);   // absorbe le clic qui suit (s'il y en a un)
        const bl = trouverBloc(r.cle);
        if (bl) appeler(() => sauverBlocActif({...bl, duree: r.duree}), null);
      }
    }
    function finDeplacement() {
      if (!deplacement) return;
      const d = deplacement; deplacement = null;
      d.el.classList.remove("deplace");
      d.el.style.pointerEvents = "";
      if (d.cible) d.cible.classList.remove("survol");
      if (!d.actif) return;                       // simple clic : le gestionnaire de clic s'en charge
      vientDeplacement = true;
      setTimeout(() => { vientDeplacement = false; }, 400);
      const bl = trouverBloc(d.cle);
      if (bl && d.cible) {
        const jour = +d.cible.dataset.jour, heure = d.cible.dataset.heure;
        if (jour !== bl.jour || heure !== bl.heure) appeler(() => sauverBlocActif({...bl, jour, heure}), null);
      }
    }
    document.addEventListener("pointerup", () => { finRedimension(); finDeplacement(); });
    document.addEventListener("pointercancel", () => { finRedimension(); finDeplacement(); });

    rendre();
    appeler(() => api.horaire_etat(), null).then(() => {
      if (etat && (!etat.cours_moodle || !etat.cours_moodle.length)) {
        appeler(() => api.horaire_cours_moodle(), "Lecture de tes cours dans Moodle...");
      }
    });
  }

  window.Horaire = {monter};
})();
