"use strict";
/* Outils communs aux deux onglets (charge en premier). */
/* =====================================================================  outils */
const JOURS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
const MOIS_COURT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const $ = s => document.querySelector(s);
const jour = s => new Date(String(s).slice(0, 10) + "T12:00:00");
const auj = () => { const d = new Date(); d.setHours(12, 0, 0, 0); return d; };
const ecart = s => Math.round((jour(s) - auj()) / 864e5);
const ic = (n, cls = "") => `<svg class="${cls}"><use href="#i-${n}"/></svg>`;
const esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const lundi = d => { const x = new Date(d); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };
const cle = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const moins = matchMedia("(prefers-reduced-motion: reduce)");
const api = () => window.pywebview && window.pywebview.api;
/* chiffres qui defilent */
function animerNombre(el, vers, fmt = n => n) {
  const de = Number(el.dataset.v ?? 0); el.dataset.v = vers;
  if (moins.matches || de === vers) { el.textContent = fmt(vers); return; }
  const t0 = performance.now(), d = 650;
  const pas = t => { const k = Math.min(1, Math.max(0, (t - t0) / d)), e = 1 - Math.pow(1 - k, 3);
    if (el.dataset.v == vers) el.textContent = fmt(Math.round(de + (vers - de) * e)); if (k < 1) requestAnimationFrame(pas); };
  requestAnimationFrame(pas);
  setTimeout(() => { if (el.dataset.v == vers) el.textContent = fmt(vers); }, d + 80);   // filet : fenetre cachee, pas d'images
}

/* toasts */
function toast(texte, genre = "", icone = genre === "critique" ? "alerte" : "check") {
  const t = document.createElement("div");
  t.className = `toast ${genre}`; t.innerHTML = `${ic(icone)}<span>${esc(texte)}</span>`;
  $("#toasts").append(t);
  setTimeout(() => { t.classList.add("part"); t.addEventListener("animationend", () => t.remove()); }, genre === "critique" ? 6000 : 3200);
}

/* eclats de couleur depuis un element */
function eclats(el) {
  if (moins.matches) return;
  const r = el.getBoundingClientRect(), couleurs = ["#2a78d6", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"];
  for (let i = 0; i < 14; i++) {
    const p = document.createElement("span"), a = Math.PI * 2 * i / 14, v = 40 + Math.random() * 40;
    p.className = "eclat";
    p.style.cssText = `left:${r.left + r.width / 2}px;top:${r.top + r.height / 2}px;background:${couleurs[i % 5]};` +
      `--x:${Math.cos(a) * v}px;--y:${Math.sin(a) * v}px;--r:${Math.random() * 360}deg`;
    document.body.append(p); p.addEventListener("animationend", () => p.remove());
  }
}
