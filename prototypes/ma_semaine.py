#!/usr/bin/env python3
"""Ma semaine : petite fenetre qui cree un fichier Markdown (Ma semaine.md) a partir de Moodle.

Prototype, LECTURE SEULE sur Moodle. Elle reutilise la connexion de MoodleSync (meme jeton) : il faut
avoir lance MoodleSync et s'y etre connecte une fois. Choix de la periode (en jours) et de la vitesse
de lecture (en pages par heure) ; le fichier est ecrit dans le dossier de rangement de MoodleSync.

Le fichier est regenere a chaque fois, mais les cases cochees, les temps reels (`reel : 70`) et la
section "Notes" sont conservees. Si le fichier existe sans la marque de MoodleSync, il n'est pas touche.

Les regles de lecture des titres de section et des statuts sont dans seances.py (meme dossier).
Sans fenetre : python prototypes/ma_semaine.py --creer [--jours 14] [--vitesse 12]
"""
import sys, os, re, json, html, datetime as dt, collections, threading, queue, time

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seances as sc

ms = sc.ms
FICHIER = "Ma semaine.md"
PRESETS_JOURS = [(7, "1 semaine"), (14, "2 semaines"), (21, "3 semaines"), (30, "1 mois")]
PREFS = os.path.join(ms.APP_DIR, "ma_semaine.json")
CACHE = os.path.join(ms.APP_DIR, "prototype_cache")


# ------------------------------------------------------------------ reglages
def charger_prefs():
    try:
        with open(PREFS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def sauver_prefs(p):
    os.makedirs(ms.APP_DIR, exist_ok=True)
    with open(PREFS, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ fichier precedent
def lire_ancien(chemin):
    """(cases cochees et temps reels, notes, texte, [(pages, minutes) des lectures chronometrees])."""
    etat, notes, texte, mesures = {}, "", None, []
    try:
        with open(chemin, encoding="utf-8") as f:
            texte = f.read()
    except OSError:
        return etat, notes, texte, mesures
    for m in re.finditer(r"^- \[( |x|X)\] (.*?)<!-- id:(\w+) -->", texte, re.M):
        reel = re.search(r"r[ée]el\s*:\s*(\d+)", m.group(2))
        minutes = int(reel.group(1)) if reel else None
        etat[m.group(3)] = (m.group(1).lower() == "x", minutes)
        pages = re.search(r"\((\d+) p\.", m.group(2))
        if minutes and pages:
            mesures.append((int(pages.group(1)), minutes))
    i = texte.find("\n## Notes")
    if i >= 0:
        notes = texte[i + len("\n## Notes"):].strip()
    return etat, notes, texte, mesures


def vitesse_observee(chemin):
    """(pages par heure, nombre de lectures) d'apres les temps reels notes, ou None."""
    mesures = lire_ancien(chemin)[3]
    pages, minutes = sum(p for p, _ in mesures), sum(m for _, m in mesures)
    if not mesures or minutes <= 0:
        return None
    return round(pages / (minutes / 60), 1), len(mesures)


# ------------------------------------------------------------------ rendu Markdown
def nom_profil(vitesse):
    for nom, v, _ in sc.PROFILS:
        if v == vitesse:
            return f"profil « {nom} »"
    return "réglage personnel"


def rendre_md(fenetre, echeances, a_dater, sans_seance, aujourdhui, jours, etat, notes, avec_pages, vitesse,
              alertes=()):
    MN, fd = sc.MOIS_NOMS, sc.fmt_duree
    L = [ms.MARQUE, "", "# Ma semaine", "",
         f"Généré le {aujourdhui.day} {MN[aujourdhui.month - 1]} {aujourdhui.year}, pour les {jours} prochains jours.",
         "", "## Comment lire ce fichier", "",
         "- **Obligatoire**, **Complémentaire** : écrit par l'enseignant dans Moodle.",
         "- *À lire (déduit)* : le programme suppose que c'est une lecture parce que c'est un fichier "
         "qui n'est pas une diapo, placé dans la séance. Ça peut être faux.",
         "- *date déduite* : l'année ou le jour n'est pas écrit dans le titre de la section.",
         "- *date déduite du numéro* : la section dit « Séance 7 » sans date. La date est comptée depuis une "
         "séance datée du même cours, un cours par semaine au jour de ton horaire, en sautant les jours "
         "annoncés sans cours dans Moodle (fériés, semaine intercalaire).",
         f"- Durées : pages divisées par **{vitesse} pages par heure** ({nom_profil(vitesse)}). "
         "C'est une estimation, pas une mesure : note ton temps réel pour la corriger.",
         "- Pour noter ton temps, ajoute `réel : 70` (en minutes) sur la ligne de la lecture. "
         "Les cases cochées et ce temps sont conservés quand le fichier est regénéré. "
         "La section « Notes » en bas aussi ; tout le reste est réécrit.", ""]
    L += [f"## À vérifier ({len(alertes)})", ""]
    if alertes:
        L += ["Contrôles automatiques : séance attendue d'après ton horaire mais introuvable, date sur un autre "
              "jour que l'horaire, numéros et dates qui ne progressent pas ensemble, doublons, séance un jour "
              "sans cours. Chaque point peut cacher une séance absente du planning ci-dessous.", ""]
        L += [f"- {a}" for a in alertes]
    else:
        L.append("Aucune incohérence trouvée par les contrôles automatiques (séances attendues d'après "
                 "l'horaire, jours, ordre des numéros, doublons, jours sans cours).")
    L.append("")
    semaines = collections.OrderedDict()
    for s in fenetre:
        semaines.setdefault(s["date"] - dt.timedelta(days=s["date"].weekday()), []).append(s)
    if not semaines:
        L += ["Aucune séance datée dans cette période.", ""]
    for debut, seances in semaines.items():
        fin_sem = debut + dt.timedelta(days=6)
        tot = sum((f.get("pages") or 0) for s in seances for f in s["lectures"]
                  if f["statut"] not in (ms.T["C"], ms.T["P"]))
        L += [f"## Semaine du {debut.day} {MN[debut.month - 1]} au {fin_sem.day} {MN[fin_sem.month - 1]}", ""]
        if avec_pages and tot:
            L += [f"**Charge de lecture estimée : {tot} pages, soit {fd(tot / vitesse)}** "
                  "(hors lectures facultatives).", ""]
        courant = None
        for s in seances:
            if s["date"] != courant:
                courant = s["date"]
                L += [f"### {sc.jour_long(courant).capitalize()}", ""]
            heure = (s["heure"].lstrip("0").replace(":", " h ") + " · ") if s["heure"] else ""
            L += [f"**{heure}{s['cours']}** · {s['titre'].strip()} · *{s['precision']}*", ""]
            if s.get("sans_cours_deduit"):
                L += [f"Pas de cours (déduit : jour annoncé sans cours par {s['sans_cours_deduit']}).", ""]
                continue
            if s["sans_travail"]:
                L += ["Pas de cours (écrit dans le titre de la section).", ""]
                continue
            if s["sans_lecture"]:
                L += ["Pas de lecture (écrit dans le titre de la section).", ""]
            if s["ouverture"]:
                L += [f"Ouverture : {s['ouverture']}", ""]
            vus = collections.Counter()
            for f in s["lectures"]:
                p = f.get("pages")
                nom = re.sub(r"\.pdf$", "", f["nom"], flags=re.I)
                duree = f" ({p} p., {fd(p / vitesse)})" if p else ""
                if f["origine"] == "déduit":
                    etiq = "*À lire (déduit)*"
                else:
                    etiq = f"**{f['statut']}**" + ("" if f["statut"] == ms.T["O"] else " (facultatif)")
                vus[f["nom"]] += 1
                ident = sc.id_lecture(s["cid"], f["nom"] + (f"#{vus[f['nom']]}" if vus[f["nom"]] > 1 else ""))
                coche, reel = etat.get(ident, (False, None))
                suite = f" · réel : {reel} min" if reel else ""
                L.append(f"- [{'x' if coche else ' '}] {nom}{duree} · {etiq}{suite} <!-- id:{ident} -->")
            if not s["lectures"] and not s["sans_lecture"]:
                L.append("*Aucune lecture identifiée.*")
            if s["supports"]:
                L += ["", f"Supports de cours : {len(s['supports'])} fichier(s), non comptés dans la lecture."]
            L.append("")
    L += ["## Échéances", ""]
    proches = [e for e in echeances if e["date"].date() <= aujourdhui + dt.timedelta(days=90)]
    if not proches:
        L += ["Aucune échéance dans le calendrier de Moodle pour les 90 prochains jours.", ""]
    for e in proches:
        L.append(f"- {e['date']:%d.%m.%Y %H:%M} · {e['cours']} · {e['nom']}"
                 + (" · **en retard**" if e["en_retard"] else ""))
    L += ["", "*Ces échéances viennent du calendrier de Moodle. Un rendu sans date dans Moodle n'y figure pas.*", "",
          "## À dater à la main", ""]
    raisons = collections.defaultdict(collections.Counter)
    for s in a_dater:
        raisons[s["cours"]][s["precision"]] += 1
    for k, rs in raisons.items():
        L.append(f"- {k} : " + " ; ".join(f"{v} séance(s), {r}" for r, v in rs.items()) + ".")
    for k in sans_seance:
        L.append(f"- {k} : aucune séance datée dans les titres de sections.")
    L += ["", "## Notes", "", notes or ""]
    texte = "\n".join(L).rstrip() + "\n"
    # Aucun tiret long dans le fichier produit, meme ceux des titres ecrits par les enseignants.
    return texte.replace(chr(0x2013), "-").replace(chr(0x2014), "-")


# ------------------------------------------------------------------ collecte (lecture seule)
def collecter(tok, y0, dire, aujourdhui):
    horaires = sc.charger_horaire()
    cours = ms.cours_inscrits(tok, ms.infos_session(tok)["userid"])
    toutes, suivis = [], {}
    for c in cours:
        cid = str(c["id"])
        h = horaires.get(cid, {})
        if h.get("suivi") is False:
            continue
        nom_cours = h.get("titre") or c["fullname"]
        suivis[c["id"]] = (nom_cours, h.get("jour"))
        dire(f"Lecture de {nom_cours}...")
        sections = ms.api(tok, "core_course_get_contents", courseid=c["id"])
        parents = ms.sous_sections(sections)
        corps = {}
        for s in sections:
            parent = parents.get(s.get("id"))
            statut_sous = ms.statut_titre(s.get("name")) if parent else None
            cible = parent if (parent and statut_sous) else s
            corps.setdefault(cible.get("id"), []).extend(sc.lectures_de_section(s, statut_sous))
        for s in sections:
            titre = s.get("name") or ""
            if parents.get(s.get("id")) and ms.statut_titre(titre):
                continue
            an = sc.analyser_titre(titre, y0)
            numero = sc.numero_seance(titre, court=bool(an))
            if not an and numero is None:
                continue
            fichiers = corps.get(s.get("id"), [])
            seance = {"cours": nom_cours, "cid": c["id"], "titre": titre, "numero": numero, "analyse": an,
                      "lectures": [f for f in fichiers if not f["support"]],
                      "supports": [f for f in fichiers if f["support"]],
                      "sans_travail": bool(sc.RE_SANS_TRAVAIL.search(titre)),
                      "sans_lecture": bool(sc.RE_SANS_LECTURE.search(titre)),
                      "ouverture": re.sub(r"<[^>]+>", "", html.unescape(s.get("availabilityinfo") or "")).strip() or None}
            d, prec = sc.dater(an, h)
            seance["date"], seance["precision"], seance["heure"] = d, prec, h.get("heure")
            seance["explicite"] = bool(d)
            toutes.append(seance)
    # Seconde passe : calendrier lu dans TOUS les cours (feries, semaine intercalaire), puis seances
    # numerotees sans date placees d'apres le numero, l'horaire et une seance datee du meme cours.
    cal = sc.construire_calendrier(toutes, horaires.get("calendrier"))
    ancres = collections.defaultdict(list)
    for s in toutes:
        if s["explicite"] and s["numero"]:
            ancres[s["cid"]].append((s["numero"], s["date"]))
    for s in toutes:
        if not s["date"] and s["numero"]:
            s["date"], s["precision"] = sc.dater_par_numero(s["numero"], ancres[s["cid"]], cal,
                                                           suivis[s["cid"]][1], aujourdhui)
        # Semaine generee par le format "semaines" de Moodle qui tombe sur une semaine annoncee sans
        # cours ailleurs : ce n'est pas une seance (une seance explicitement datee, elle, reste en alerte).
        if (s["date"] in cal["sans_cours"] and not s["sans_travail"] and s["analyse"]
                and s["analyse"]["type"] == "semaine"):
            s["sans_cours_deduit"] = cal["sans_cours"][s["date"]]
            s["sans_travail"] = True
    seances = [s for s in toutes if s["date"]]
    a_dater = [s for s in toutes if not s["date"]]
    sans_seance = [nom for cid, (nom, _) in suivis.items() if not any(s["cid"] == cid for s in seances)]
    ev =ms.api(tok, "core_calendar_get_action_events_by_timesort",
                timesortfrom=int(time.time()) - 7 * 86400, limitnum=50).get("events", [])
    ids_suivis = {str(cid) for cid in suivis}
    echeances = [{"date": dt.datetime.fromtimestamp(e["timestart"]),
                  "cours": html.unescape(e["course"]["fullname"]), "nom": html.unescape(e["name"]),
                  "en_retard": bool(e.get("overdue"))}
                 for e in ev if str(e["course"]["id"]) in ids_suivis]
    echeances.sort(key=lambda x: x["date"])
    return seances, a_dater, sans_seance, echeances, suivis, cal


def generer(jours, vitesse, dossier, avec_pages=True, cache=CACHE, dire=print):
    """Cree (ou regenere) Ma semaine.md. Renvoie un petit compte rendu."""
    cfg = ms.charger_config()
    ms.appliquer_config(cfg)
    tok = cfg["token"]
    if not tok:
        raise ms.Erreur("Aucune connexion trouvée. Lance MoodleSync et connecte-toi une première fois.")
    aujourdhui = dt.date.today()
    y0 = aujourdhui.year if aujourdhui.month >= 8 else aujourdhui.year - 1
    chemin = os.path.join(dossier, FICHIER)
    etat, notes, ancien, _ = lire_ancien(chemin)
    if ancien is not None and ms.MARQUE not in ancien:
        raise ms.Erreur(f"Le fichier « {FICHIER} » existe déjà sans la marque de MoodleSync : je n'y touche pas.")
    seances, a_dater, sans_seance, echeances, suivis, cal = collecter(tok, y0, dire, aujourdhui)
    fin = aujourdhui + dt.timedelta(days=jours)
    alertes = sc.controles(seances, suivis, cal, aujourdhui, fin)
    fenetre = sorted((s for s in seances if aujourdhui <= s["date"] <= fin), key=lambda s: (s["date"], s["heure"] or ""))
    if avec_pages:
        for s in fenetre:
            for f in s["lectures"]:
                if f["pdf"]:
                    dire(f"Comptage des pages : {f['nom'][:60]}")
                    f["pages"] = sc.pages_pdf(tok, f, cache)
    texte = rendre_md(fenetre, echeances, a_dater, sans_seance, aujourdhui, jours, etat, notes, avec_pages, vitesse,
                      alertes)
    os.makedirs(dossier, exist_ok=True)
    with open(chemin + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texte)
    os.replace(chemin + ".tmp", chemin)
    lectures = [f for s in fenetre for f in s["lectures"]]
    return {"chemin": chemin, "seances": len(fenetre), "lectures": len(lectures),
            "deduites": sum(1 for f in lectures if f["origine"] == "déduit"), "alertes": len(alertes)}


# ------------------------------------------------------------------ fenetre
def lancer_fenetre():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    try:
        import sv_ttk
    except ImportError:
        sv_ttk = None

    prefs, cfg = charger_prefs(), ms.charger_config()
    root = tk.Tk()
    root.title("Ma semaine")
    root.geometry("640x720")
    root.minsize(560, 640)
    if sv_ttk:
        try:
            sv_ttk.set_theme(ms.theme_systeme())
        except Exception:
            pass

    jours_v = tk.IntVar(value=int(prefs.get("jours", 14)))
    vit_v = tk.IntVar(value=int(prefs.get("vitesse", sc.VITESSE_DEFAUT)))
    pages_v = tk.BooleanVar(value=bool(prefs.get("pages", True)))
    dossier_v = tk.StringVar(value=prefs.get("dossier") or cfg["dest"])
    q = queue.Queue()
    dernier = {"chemin": None}

    cadre = ttk.Frame(root, padding=16)
    cadre.pack(fill="both", expand=True)
    ttk.Label(cadre, text="Ma semaine", font=("Segoe UI", 16, "bold")).pack(anchor="w")
    ttk.Label(cadre, wraplength=580, justify="left", text=(
        "Crée Ma semaine.md : séances à venir, lectures, temps estimé, échéances. "
        "Lisible dans n'importe quel éditeur de texte.")).pack(anchor="w", pady=(2, 6))

    # --- periode
    bloc = ttk.LabelFrame(cadre, text="Période à couvrir", padding=10)
    bloc.pack(fill="x", pady=4)
    ligne = ttk.Frame(bloc)
    ligne.pack(fill="x")
    for v, nom in PRESETS_JOURS:
        ttk.Radiobutton(ligne, text=nom, value=v, variable=jours_v).pack(side="left", padx=(0, 12))
    ligne2 = ttk.Frame(bloc)
    ligne2.pack(fill="x", pady=(6, 0))
    ttk.Label(ligne2, text="Ou précisément :").pack(side="left")
    ttk.Spinbox(ligne2, from_=1, to=120, width=5, textvariable=jours_v).pack(side="left", padx=6)
    ttk.Label(ligne2, text="jours à partir d'aujourd'hui").pack(side="left")

    # --- vitesse
    bloc = ttk.LabelFrame(cadre, text="Vitesse de lecture (pages par heure)", padding=10)
    bloc.pack(fill="x", pady=4)
    grille = ttk.Frame(bloc)
    grille.pack(fill="x")
    for i, (nom, v, _) in enumerate(sc.PROFILS):
        ttk.Radiobutton(grille, text=f"{nom} : {v} pages/h", value=v, variable=vit_v).grid(
            row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=1)
    ligne = ttk.Frame(bloc)
    ligne.pack(fill="x", pady=(6, 0))
    ttk.Label(ligne, text="Ou précisément :").pack(side="left")
    ttk.Spinbox(ligne, from_=1, to=80, width=5, textvariable=vit_v).pack(side="left", padx=6)
    ttk.Label(ligne, text="pages par heure").pack(side="left")
    desc = ttk.Label(bloc, wraplength=560, justify="left", foreground="gray")
    desc.pack(anchor="w", pady=(8, 0))
    obs = ttk.Frame(bloc)
    obs.pack(fill="x", pady=(6, 0))
    obs_txt = ttk.Label(obs, wraplength=430, justify="left")
    obs_txt.pack(side="left")
    obs_btn = ttk.Button(obs, text="Utiliser cette vitesse")
    obs_btn.pack(side="right")

    def maj_desc(*_):
        try:
            v = int(vit_v.get())
        except (tk.TclError, ValueError):
            return
        txt = next((o for _, pv, o in sc.PROFILS if pv == v), "")
        desc.configure(text=(txt or "Réglage personnel.") + "  Base de calcul : 400 mots par page, "
                       "hypothèse non mesurée.")

    def maj_obs():
        r = vitesse_observee(os.path.join(dossier_v.get(), FICHIER))
        if r:
            obs_txt.configure(text=f"D'après tes temps réels notés dans le fichier : {r[0]:g} pages/h "
                                   f"({r[1]} lecture(s)).")
            obs_btn.configure(state="normal", command=lambda: vit_v.set(max(1, round(r[0]))))
        else:
            obs_txt.configure(text="Aucun temps réel noté pour l'instant (ajoute « réel : 70 » sur une ligne "
                                   "du fichier pour calibrer ta vitesse).")
            obs_btn.configure(state="disabled")

    vit_v.trace_add("write", maj_desc)
    maj_desc()
    maj_obs()

    # --- options et dossier
    bloc = ttk.LabelFrame(cadre, text="Options", padding=10)
    bloc.pack(fill="x", pady=4)
    ttk.Checkbutton(bloc, variable=pages_v, text="Compter les pages (télécharge les PDF de la période "
                    "dans un dossier temporaire)").pack(anchor="w")
    ligne = ttk.Frame(bloc)
    ligne.pack(fill="x", pady=(8, 0))
    ttk.Label(ligne, text="Dossier :").pack(side="left")
    ttk.Label(ligne, textvariable=dossier_v, wraplength=380).pack(side="left", padx=6)

    def changer():
        d = filedialog.askdirectory(initialdir=dossier_v.get() or None, title="Dossier où écrire Ma semaine.md")
        if d:
            dossier_v.set(os.path.normpath(d))
            maj_obs()
    ttk.Button(ligne, text="Changer...", command=changer).pack(side="right")

    # --- action
    actions = ttk.Frame(cadre)
    actions.pack(fill="x", pady=(10, 4))
    bouton = ttk.Button(actions, text="Créer Ma semaine.md")
    bouton.pack(side="left")
    b_fichier = ttk.Button(actions, text="Ouvrir le fichier", state="disabled")
    b_fichier.pack(side="left", padx=8)
    b_dossier = ttk.Button(actions, text="Ouvrir le dossier", state="disabled")
    b_dossier.pack(side="left")
    journal = tk.Text(cadre, height=5, wrap="word", state="disabled", relief="flat", borderwidth=1)
    journal.pack(fill="both", expand=True, pady=(6, 0))

    def log(t):
        journal.configure(state="normal")
        journal.insert("end", t + "\n")
        journal.see("end")
        journal.configure(state="disabled")

    def ouvrir_fichier():
        if dernier["chemin"]:
            if ms.MAC:
                import subprocess
                subprocess.run(["open", dernier["chemin"]])
            else:
                os.startfile(dernier["chemin"])

    b_fichier.configure(command=ouvrir_fichier)
    b_dossier.configure(command=lambda: ms.ouvrir_dossier(dossier_v.get()))

    def sonder():
        try:
            while True:
                genre, val = q.get_nowait()
                if genre == "log":
                    log(val)
                elif genre == "ok":
                    dernier["chemin"] = val["chemin"]
                    log(f"Terminé : {val['seances']} séance(s), {val['lectures']} lecture(s) "
                        f"dont {val['deduites']} déduite(s).\n{val['chemin']}")
                    if val["alertes"]:
                        log(f"{val['alertes']} point(s) à vérifier : voir « À vérifier » en haut du fichier.")
                    bouton.configure(state="normal")
                    b_fichier.configure(state="normal")
                    b_dossier.configure(state="normal")
                    maj_obs()
                    return
                else:
                    log(val)
                    bouton.configure(state="normal")
                    messagebox.showerror("Ma semaine", val)
                    return
        except queue.Empty:
            pass
        root.after(120, sonder)

    def lancer():
        try:
            j, v = int(jours_v.get()), int(vit_v.get())
        except (tk.TclError, ValueError):
            messagebox.showwarning("Ma semaine", "La période et la vitesse doivent être des nombres entiers.")
            return
        if not (1 <= j <= 120 and 1 <= v <= 80):
            messagebox.showwarning("Ma semaine", "Période : 1 à 120 jours. Vitesse : 1 à 80 pages par heure.")
            return
        sauver_prefs({"jours": j, "vitesse": v, "pages": bool(pages_v.get()), "dossier": dossier_v.get()})
        bouton.configure(state="disabled")
        log(f"Période : {j} jour(s). Vitesse : {v} pages/h.")

        def tache():
            try:
                q.put(("ok", generer(j, v, dossier_v.get(), pages_v.get(), CACHE, lambda t: q.put(("log", t)))))
            except ms.SessionExpiree:
                q.put(("err", "La session a expiré. Ouvre MoodleSync, reconnecte-toi, puis réessaie."))
            except ms.Erreur as e:
                q.put(("err", str(e)))
            except Exception as e:
                q.put(("err", f"Erreur inattendue : {e!r}"))
        threading.Thread(target=tache, daemon=True).start()
        sonder()

    bouton.configure(command=lancer)
    root.update_idletasks()
    if os.environ.get("MASEMAINE_TEST") == "lancer":   # simule un clic sur le bouton, puis affiche le journal
        def fin():
            if b_fichier.instate(["!disabled"]) or "Erreur" in journal.get("1.0", "end"):
                print(journal.get("1.0", "end").strip())
                root.destroy()
            else:
                root.after(300, fin)
        root.after(120000, root.destroy)
        bouton.invoke()
        root.after(300, fin)
        root.mainloop()
        return
    if os.environ.get("MASEMAINE_TEST"):        # verification sans capture d'ecran : taille demandee par les widgets
        print("taille demandee :", root.winfo_reqwidth(), "x", root.winfo_reqheight(),
              "| boutons a y =", bouton.winfo_y() + actions.winfo_y(), "| journal a y =", journal.winfo_y())
        root.destroy()
        return
    root.geometry(f"{max(640, root.winfo_reqwidth())}x{max(720, root.winfo_reqheight())}")
    root.mainloop()


def main():
    if "--creer" in sys.argv:
        def opt(nom, defaut):
            return type(defaut)(sys.argv[sys.argv.index(nom) + 1]) if nom in sys.argv else defaut
        p = charger_prefs()
        r = generer(opt("--jours", int(p.get("jours", 14))), opt("--vitesse", int(p.get("vitesse", sc.VITESSE_DEFAUT))),
                    p.get("dossier") or ms.charger_config()["dest"], True, CACHE, print)
        print(f"Terminé : {r['seances']} séance(s), {r['lectures']} lecture(s) dont {r['deduites']} déduite(s).")
        if r["alertes"]:
            print(f"{r['alertes']} point(s) à vérifier : voir « À vérifier » en haut du fichier.")
        print(f"Fichier : {r['chemin']}")
        return
    lancer_fenetre()


if __name__ == "__main__":
    main()
