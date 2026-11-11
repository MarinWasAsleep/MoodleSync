"use strict";
/* Composant d'arborescence de « Mes textes » (tache R7, contrat 5.3).
   Il rend les donnees de `ocr_arbre` et emet des actions : il n'appelle jamais l'API.
   Aucun HTML n'est construit par concatenation : createElement et textContent seulement
   (regle de l'ancien textes.js, reprise au contrat 5.3). Les phrases viennent de TX_MOTS. */

/* Etat replie ou ouvert, garde par chemin pendant toute la duree de la page : deux charger()
   successifs retrouvent les memes branches ouvertes (contrat 5.3). */
const TX_ARBRE_OUVERTS = {};

/* Statuts dont la case est cochable en mode « choisir » (contrat 5.3 et 2.3). */
const TX_ARBRE_COCHABLES = ["non_traite", "echec"];

/* Le menu ouvert et son bouton : un seul menu a la fois dans la page. */
let txArbreMenu = null;
let txArbreMenuAncre = null;

/* Une phrase de TX_MOTS, ses valeurs intercalees remplacees : {} marque une valeur. */
function txArbrePhrase(cle, ...valeurs) {
  const modele = (typeof TX_MOTS === "object" && TX_MOTS && TX_MOTS[cle]) || "";
  let i = 0;
  return String(modele).replace(/\{\}/g, () => String(valeurs[i++] === undefined ? "" : valeurs[i - 1]));
}

/* Un element : sa balise, sa classe, son texte. Rien d'autre. */
function txArbreEl(tag, classe, texte) {
  const el = document.createElement(tag);
  if (classe) el.className = classe;
  if (texte !== undefined && texte !== null) el.appendChild(document.createTextNode(String(texte)));
  return el;
}

/* Tous les fichiers sous un noeud, dans l'ordre de l'arbre. */
function txArbreFichiers(noeud, sortie) {
  const liste = sortie || [];
  if (!noeud) return liste;
  if (noeud.type === "fichier") liste.push(noeud);
  else for (const enfant of noeud.enfants || []) txArbreFichiers(enfant, liste);
  return liste;
}

/* Les fichiers d'un noeud que le mode « choisir » laisse cocher. */
function txArbreCochables(noeud) {
  return txArbreFichiers(noeud, []).filter(f => TX_ARBRE_COCHABLES.indexOf(String(f.statut)) >= 0);
}

/* ------------------------------------------------------------------ phrases d'un noeud */
function txArbreStatut(noeud) {
  const statut = String((noeud && noeud.statut) || "non_traite");
  return txArbrePhrase("statut_" + statut) || statut;
}

function txArbreResume(noeud) {
  const compteurs = (noeud && noeud.compteurs) || {};
  const nombre = n => (typeof txNombre === "function" ? txNombre(n) : String(n));
  const pluriel = (n, un, plusieurs) => (Number(n) > 1 ? plusieurs : un);
  const fichiers = Number(compteurs.fichiers) || 0;
  const traites = Number(compteurs.traites) || 0;
  return nombre(fichiers) + " " + pluriel(fichiers, txArbrePhrase("fichier"), txArbrePhrase("fichiers"))
    + ", " + nombre(traites) + " " + pluriel(traites, txArbrePhrase("traite_un"), txArbrePhrase("traites"));
}

/* ------------------------------------------------------------------ composant */
/* txArbreCreer(conteneur, options) : options.mode vaut « voir » ou « choisir »,
   options.onAction(action, noeud) recoit les actions d'un fichier,
   options.onSelection(chemins, resume) recoit la selection du mode « choisir ». */
function txArbreCreer(conteneur, options) {
  const opts = options || {};
  const mode = opts.mode === "choisir" ? "choisir" : "voir";
  const onAction = typeof opts.onAction === "function" ? opts.onAction : null;
  const onSelection = typeof opts.onSelection === "function" ? opts.onSelection : null;

  let arbre = null;
  let coches = {};               // chemin d'un fichier -> true

  const racine = document.createElement("ul");
  racine.className = "tx-arbre";
  racine.setAttribute("role", "tree");
  racine.setAttribute("aria-label", txArbrePhrase("arbre_nom"));

  /* ---------------------------------------------------------------- etat des cases */
  function etatCase(noeud) {
    const liste = txArbreCochables(noeud);
    if (!liste.length) return "non";
    const prises = liste.filter(f => coches[f.chemin]).length;
    if (prises === 0) return "non";
    return prises === liste.length ? "oui" : "mixte";
  }

  function poserCase(noeud, valeur) {
    for (const f of txArbreCochables(noeud)) {
      if (valeur) coches[f.chemin] = true;
      else delete coches[f.chemin];
    }
  }

  function basculerCase(noeud) {
    if (!noeud) return;
    if (noeud.type === "fichier") {
      if (TX_ARBRE_COCHABLES.indexOf(String(noeud.statut)) < 0) return;
      if (coches[noeud.chemin]) delete coches[noeud.chemin];
      else coches[noeud.chemin] = true;
      return;
    }
    poserCase(noeud, etatCase(noeud) !== "oui");
  }

  /* Selection rendue : un dossier entierement coche compte pour lui seul, pas pour ses fichiers. */
  function cheminsChoisis() {
    const sortie = [];
    const visiter = noeud => {
      if (!noeud) return;
      if (noeud.type === "fichier") {
        if (mode === "choisir" && coches[noeud.chemin]) sortie.push(noeud.chemin);
        return;
      }
      if (mode === "choisir" && etatCase(noeud) === "oui") { sortie.push(noeud.chemin); return; }
      for (const enfant of noeud.enfants || []) visiter(enfant);
    };
    for (const cours of (arbre && arbre.cours) || []) visiter(cours);
    return sortie;
  }

  /* Resume de la selection : les seuls documents qui restent cochables (contrat 5.3), et leurs pages
     quand elles sont toutes connues. Un dossier compte ce qu'il laisse cocher, pas ses documents deja
     traites (ecart E-V5-3). */
  function resumeSelection(chemins) {
    const parChemin = {};
    const ranger = noeud => {
      if (!noeud) return;
      parChemin[noeud.chemin] = noeud;
      for (const enfant of enfantsDe(noeud)) ranger(enfant);
    };
    for (const cours of (arbre && arbre.cours) || []) ranger(cours);
    let documents = 0, pages = 0, connues = true;
    for (const chemin of chemins) {
      const noeud = parChemin[chemin];
      const liste = !noeud ? [] : noeud.type === "dossier" ? txArbreCochables(noeud) : [noeud];
      for (const f of liste) {
        documents++;
        if (f.pages === null || f.pages === undefined) connues = false;
        else pages += Number(f.pages) || 0;
      }
    }
    return { documents: documents, pages: connues ? pages : null, pages_connues: connues && documents > 0 };
  }

  function annoncerSelection() {
    if (mode !== "choisir" || !onSelection) return;
    const chemins = cheminsChoisis();
    onSelection(chemins, resumeSelection(chemins));
  }

  /* ---------------------------------------------------------------- rendu */
  function enfantsDe(noeud) {
    return Array.isArray(noeud && noeud.enfants) ? noeud.enfants : [];
  }

  function estOuvert(noeud) {
    return !!TX_ARBRE_OUVERTS[noeud.chemin];
  }

  function caseDe(noeud) {
    const boite = document.createElement("input");
    boite.type = "checkbox";
    boite.className = "tx-case";
    const etat = etatCase(noeud);
    boite.checked = etat === "oui";
    boite.indeterminate = etat === "mixte";
    boite.setAttribute("aria-checked", etat === "oui" ? "true" : etat === "mixte" ? "mixed" : "false");
    if (noeud.type === "fichier") {
      boite.setAttribute("aria-label", txArbrePhrase("case_fichier", noeud.nom));
      if (TX_ARBRE_COCHABLES.indexOf(String(noeud.statut)) < 0) {
        boite.disabled = true;
        boite.setAttribute("aria-disabled", "true");
      }
    } else {
      boite.setAttribute("aria-label", txArbrePhrase("case_dossier", noeud.nom));
      if (!txArbreCochables(noeud).length) {
        boite.disabled = true;
        boite.setAttribute("aria-disabled", "true");
      }
    }
    return boite;
  }

  function ligneDossier(noeud) {
    const ligne = txArbreEl("div", "tx-ligne");
    const bascule = txArbreEl("button", "tx-bascule", estOuvert(noeud) ? "\u25be" : "\u25b8");
    bascule.type = "button";
    bascule.setAttribute("aria-label", txArbrePhrase("bascule"));
    ligne.appendChild(bascule);
    if (mode === "choisir") ligne.appendChild(caseDe(noeud));
    ligne.appendChild(txArbreEl("span", "tx-nom", noeud.nom));
    ligne.appendChild(txArbreEl("span", "tx-resume", txArbreResume(noeud)));
    return ligne;
  }

  function ligneFichier(noeud) {
    const ligne = txArbreEl("div", "tx-ligne");
    if (mode === "choisir") ligne.appendChild(caseDe(noeud));
    ligne.appendChild(txArbreEl("span", "tx-nom", noeud.nom));
    const badge = txArbreEl("span", "tx-badge", txArbreStatut(noeud));
    badge.setAttribute("data-statut", String(noeud.statut || "non_traite"));
    ligne.appendChild(badge);
    if (mode === "voir") {
      const menu = txArbreEl("button", "tx-menu", "\u22ee");
      menu.type = "button";
      menu.setAttribute("aria-haspopup", "menu");
      menu.setAttribute("aria-label", txArbrePhrase("menu_actions", noeud.nom));
      ligne.appendChild(menu);
    }
    return ligne;
  }

  function rendreNoeud(noeud, niveau) {
    const dossier = noeud.type === "dossier";
    const li = document.createElement("li");
    li.className = "tx-noeud " + (dossier ? "tx-dossier" : "tx-fichier");
    li.setAttribute("role", "treeitem");
    li.setAttribute("aria-level", String(niveau));
    li.setAttribute("data-chemin", String(noeud.chemin || ""));
    if (dossier) {
      li.setAttribute("aria-expanded", estOuvert(noeud) ? "true" : "false");
      li.appendChild(ligneDossier(noeud));
      const groupe = document.createElement("ul");
      groupe.setAttribute("role", "group");
      groupe.hidden = !estOuvert(noeud);
      for (const enfant of enfantsDe(noeud)) groupe.appendChild(rendreNoeud(enfant, niveau + 1));
      li.appendChild(groupe);
    } else {
      li.setAttribute("data-statut", String(noeud.statut || "non_traite"));
      if (TX_ARBRE_COCHABLES.indexOf(String(noeud.statut)) < 0) li.className = li.className + " tx-indisponible";
      li.appendChild(ligneFichier(noeud));
    }
    li.tabIndex = -1;
    return li;
  }

  function rendre() {
    fermerMenu();
    while (racine.firstChild) racine.removeChild(racine.firstChild);
    for (const cours of (arbre && arbre.cours) || []) racine.appendChild(rendreNoeud(cours, 1));
    if (!racine.parentNode) conteneur.appendChild(racine);
    const premier = listeTreeitems()[0];
    if (premier) premier.tabIndex = 0;
  }

  /* Met a jour les cases sans reconstruire l'arbre : la branche ouverte et le focus restent. */
  function majCases() {
    for (const li of listeTreeitems()) {
      const boite = li.querySelector(".tx-case");
      const noeud = noeudDe(li);
      if (!boite || !noeud) continue;
      const etat = etatCase(noeud);
      boite.checked = etat === "oui";
      boite.indeterminate = etat === "mixte";
      boite.setAttribute("aria-checked", etat === "oui" ? "true" : etat === "mixte" ? "mixed" : "false");
    }
  }

  /* ---------------------------------------------------------------- lecture du DOM */
  function chercher(chemin) {
    let trouve = null;
    const visiter = noeud => {
      if (!noeud || trouve) return;
      if (noeud.chemin === chemin) { trouve = noeud; return; }
      for (const enfant of enfantsDe(noeud)) visiter(enfant);
    };
    for (const cours of (arbre && arbre.cours) || []) visiter(cours);
    return trouve;
  }

  function noeudDe(li) {
    return chercher(li && li.getAttribute ? li.getAttribute("data-chemin") : "");
  }

  function listeTreeitems() {
    return Array.from(racine.querySelectorAll("[role=treeitem]"));
  }

  /* Les treeitems visibles, dans l'ordre du DOM : une branche fermee ne compte pas. */
  function visibles() {
    const sortie = [];
    const parcourir = ul => {
      for (const li of ul.children) {
        if (!li.classList || !li.classList.contains("tx-noeud")) continue;
        sortie.push(li);
        const ouvert = li.getAttribute("aria-expanded") === "true";
        if (!ouvert) continue;
        for (const groupe of li.children) {
          if (groupe.tagName && String(groupe.tagName).toLowerCase() === "ul") parcourir(groupe);
        }
      }
    };
    parcourir(racine);
    return sortie;
  }

  function focaliser(li) {
    if (!li) return;
    for (const autre of listeTreeitems()) autre.tabIndex = -1;
    li.tabIndex = 0;
    if (typeof li.focus === "function") li.focus();
  }

  function premierDe(chemin) {
    return listeTreeitems().filter(li => li.getAttribute("data-chemin") === chemin)[0] || null;
  }

  /* ---------------------------------------------------------------- ouvrir, fermer */
  function basculer(noeud) {
    if (!noeud || noeud.type !== "dossier") return;
    TX_ARBRE_OUVERTS[noeud.chemin] = !estOuvert(noeud);
    rendre();
    focaliser(premierDe(noeud.chemin));
  }

  /* ---------------------------------------------------------------- menu d'un fichier */
  function actionsDe(noeud) {
    const actions = ["ouvrir", "afficher"];
    if (noeud.texte) actions.push("copier");
    /* O18 (revue V7, E-V7-3) : « Restaurer l'original » n'a de sens que pour un PDF reellement remplace.
    Un PDF textuel traite a son texte mais n'a pas de copie : la restauration n'y ferait rien. */
    if (noeud.remplace) actions.push("restaurer");
    if (String(noeud.statut || "") === "echec") actions.push("reessayer");
    return actions;
  }

  function fermerMenu() {
    if (txArbreMenu && txArbreMenu.parentNode) txArbreMenu.parentNode.removeChild(txArbreMenu);
    txArbreMenu = null;
    txArbreMenuAncre = null;
  }

  function ouvrirMenu(noeud, ancre) {
    if (!onAction || !noeud || mode !== "voir" || !ancre) return;
    const dejaOuvert = txArbreMenuAncre === ancre;
    fermerMenu();
    if (dejaOuvert) return;
    const menu = document.createElement("ul");
    menu.className = "tx-menu-liste";
    menu.setAttribute("role", "menu");
    for (const action of actionsDe(noeud)) {
      const item = txArbreEl("li", "tx-menu-item");
      const bouton = txArbreEl("button", "tx-menu-bouton", txArbrePhrase("action_" + action));
      bouton.type = "button";
      bouton.setAttribute("role", "menuitem");
      bouton.setAttribute("data-action", action);
      item.appendChild(bouton);
      menu.appendChild(item);
    }
    ancre.parentNode.appendChild(menu);
    txArbreMenu = menu;
    txArbreMenuAncre = ancre;
    const premier = menu.querySelector("[role=menuitem]");
    if (premier && typeof premier.focus === "function") premier.focus();
  }

  function actionSur(chemin, action) {
    const noeud = chercher(chemin);
    fermerMenu();
    if (noeud && onAction) onAction(action, noeud);
  }

  /* ---------------------------------------------------------------- clavier (modele ARIA tree) */
  function clavier(e) {
    const li = e.target && e.target.closest ? e.target.closest("[role=treeitem]") : null;
    if (!li) return;
    const liste = visibles(), index = liste.indexOf(li), noeud = noeudDe(li);
    const cle = e.key;
    if (cle === "ArrowDown" || cle === "ArrowUp" || cle === "Home" || cle === "End") {
      if (e.preventDefault) e.preventDefault();
      const cible = cle === "Home" ? liste[0]
        : cle === "End" ? liste[liste.length - 1]
          : liste[Math.min(liste.length - 1, Math.max(0, index + (cle === "ArrowDown" ? 1 : -1)))];
      focaliser(cible);
      return;
    }
    if (cle === "ArrowRight") {
      if (e.preventDefault) e.preventDefault();
      if (!noeud || noeud.type !== "dossier") return;
      if (!estOuvert(noeud)) { basculer(noeud); return; }
      const suite = liste[index + 1];
      if (suite && Number(suite.getAttribute("aria-level")) > Number(li.getAttribute("aria-level"))) focaliser(suite);
      return;
    }
    if (cle === "ArrowLeft") {
      if (e.preventDefault) e.preventDefault();
      if (noeud && noeud.type === "dossier" && estOuvert(noeud)) { basculer(noeud); return; }
      for (let i = index - 1; i >= 0; i--) {
        if (Number(liste[i].getAttribute("aria-level")) < Number(li.getAttribute("aria-level"))) {
          focaliser(liste[i]);
          return;
        }
      }
      return;
    }
    if (cle === " " || cle === "Spacebar") {
      if (mode !== "choisir" || !noeud) return;
      if (e.preventDefault) e.preventDefault();
      basculerCase(noeud);
      majCases();
      annoncerSelection();
      return;
    }
    if (cle === "Enter") {
      /* Entree sur un element du menu d'un fichier : son action, jamais la bascule du menu (ecart E-V5-1).
         `preventDefault` empeche le clic natif du bouton, donc l'action ne part qu'une fois. */
      const item = e.target && e.target.closest ? e.target.closest("[role=menuitem]") : null;
      if (item) {
        if (e.preventDefault) e.preventDefault();
        actionSur(noeudDe(li).chemin, item.getAttribute("data-action"));
        return;
      }
      if (e.preventDefault) e.preventDefault();
      if (!noeud) return;
      if (noeud.type === "dossier") { basculer(noeud); return; }
      ouvrirMenu(noeud, li.querySelector(".tx-menu"));
    }
  }

  /* ---------------------------------------------------------------- clics */
  function clic(e) {
    const cible = e.target;
    if (!cible || !cible.closest) return;
    const item = cible.closest("[data-action]");
    const menuOuvert = cible.closest(".tx-menu-liste");
    const li = cible.closest("[role=treeitem]");
    if (menuOuvert && item) { actionSur(noeudDe(li).chemin, item.getAttribute("data-action")); return; }
    if (!li) { fermerMenu(); return; }
    const noeud = noeudDe(li);
    if (!noeud) return;
    if (cible.closest(".tx-menu")) { ouvrirMenu(noeud, cible.closest(".tx-menu")); return; }
    if (cible.closest(".tx-bascule")) { basculer(noeud); return; }
    if (cible.closest(".tx-case")) {
      basculerCase(noeud);
      majCases();
      annoncerSelection();
      return;
    }
    if (noeud.type === "dossier") { basculer(noeud); return; }
    fermerMenu();
    focaliser(li);
  }

  racine.addEventListener("keydown", clavier);
  racine.addEventListener("click", clic);

  /* ---------------------------------------------------------------- interface publique */
  const composant = {
    racine: racine,
    charger(nouvel) {
      arbre = nouvel || null;
      const gardes = {};
      for (const cours of (arbre && arbre.cours) || []) {
        for (const f of txArbreFichiers(cours, [])) if (coches[f.chemin]) gardes[f.chemin] = true;
      }
      coches = gardes;
      rendre();
      annoncerSelection();
      return composant;
    },
    selection() {
      return cheminsChoisis();
    },
    resume() {
      return resumeSelection(cheminsChoisis());
    },
    vider() {
      arbre = null;
      coches = {};
      fermerMenu();
      while (racine.firstChild) racine.removeChild(racine.firstChild);
      if (racine.parentNode) racine.parentNode.removeChild(racine);
    },
    ouvrirTout() {
      const visiter = noeud => {
        if (!noeud || noeud.type !== "dossier") return;
        TX_ARBRE_OUVERTS[noeud.chemin] = true;
        for (const enfant of enfantsDe(noeud)) visiter(enfant);
      };
      for (const cours of (arbre && arbre.cours) || []) visiter(cours);
      rendre();
    },
    fermerTout() {
      for (const chemin of Object.keys(TX_ARBRE_OUVERTS)) delete TX_ARBRE_OUVERTS[chemin];
      rendre();
    },
  };
  return composant;
}

/* Un clic ailleurs ferme le menu ouvert d'un fichier. */
document.addEventListener("click", e => {
  if (!txArbreMenu || !e.target || !e.target.closest) return;
  if (e.target.closest(".tx-menu-liste") || e.target.closest(".tx-menu")) return;
  if (txArbreMenu.parentNode) txArbreMenu.parentNode.removeChild(txArbreMenu);
  txArbreMenu = null;
  txArbreMenuAncre = null;
});
