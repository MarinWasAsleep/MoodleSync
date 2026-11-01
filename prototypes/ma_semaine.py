#!/usr/bin/env python3
"""Ma semaine : petite fenetre qui cree un fichier Markdown (Ma semaine.md) a partir de Moodle.

Prototype, LECTURE SEULE sur Moodle. Elle reutilise la connexion de MoodleSync (meme jeton) : il faut
avoir lance MoodleSync et s'y etre connecte une fois. Choix de la periode (en jours) et de la vitesse
de lecture (en pages par heure) ; le fichier est ecrit dans le dossier de rangement de MoodleSync.

Le fichier est regenere a chaque fois, mais les cases cochees, les temps reels (`reel : 70`), la
section "Mes echeances" et la section "Notes" sont conservees. Si le fichier existe sans la marque de
MoodleSync, il n'est pas touche. L'etat des seances est garde dans ma_semaine_etat.json (dossier des
reglages) pour signaler ce qui a change depuis la generation precedente.

Les regles (dates, statuts, controles) sont dans seances.py, testees par test_seances.py.
Sans fenetre : python prototypes/ma_semaine.py --creer [--jours 14] [--vitesse 12]
               python prototypes/ma_semaine.py --audit     (relit le semestre ecoule)
"""
import sys, os, re, json, html, datetime as dt, collections, threading, queue, time

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seances as sc

ms = sc.ms
FICHIER = "Ma semaine.md"
FICHIER_AUDIT = "Ma semaine - audit.md"
PRESETS_JOURS = [(7, "1 semaine"), (14, "2 semaines"), (21, "3 semaines"), (30, "1 mois")]
PREFS = os.path.join(ms.APP_DIR, "ma_semaine.json")
ETAT = os.path.join(ms.APP_DIR, "ma_semaine_etat.json")
MESURES = os.path.join(ms.APP_DIR, "ma_semaine_mesures.json")
CACHE = os.path.join(ms.APP_DIR, "prototype_cache")
TITRE_MES_ECHEANCES = "## Mes échéances"
AIDE_MES_ECHEANCES = ("<!-- Ajoute ici ce que Moodle ne connaît pas, une ligne par échéance, par exemple :\n"
                      "- 15.12.2026 23:59 · Théories économiques · Rendu du dossier\n"
                      "La date (et l'heure, facultative) en début de ligne. Cette section est conservée. -->")


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


def charger_etat():
    try:
        with open(ETAT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def sauver_etat(etat):
    os.makedirs(ms.APP_DIR, exist_ok=True)
    with open(ETAT + ".tmp", "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=1)
    os.replace(ETAT + ".tmp", ETAT)


# ------------------------------------------------------------------ fichier precedent
def section(texte, titre, suivant):
    """Texte entre la ligne `titre` et la ligne `suivant` (ou la fin), sans espaces autour."""
    i = texte.find("\n" + titre)
    if i < 0:
        return ""
    i += len(titre) + 1
    j = texte.find("\n" + suivant, i) if suivant else -1
    return texte[i:j if j >= 0 else len(texte)].strip()


RE_REEL = re.compile(r"(?i)r[ée]el\s*:?\s*(?:(\d{1,2})\s*h\s*(\d{1,2})?|(\d{1,4}))")


def minutes_reelles(texte):
    """Temps note sur une ligne : "reel : 70", "reel 70 min", "reel : 1 h 10", "reel: 2h". Minutes, ou None."""
    m = RE_REEL.search(texte or "")
    if not m:
        return None
    h, mn, seul = m.groups()
    total = int(seul) if seul else int(h) * 60 + int(mn or 0)
    return total or None


def lire_ancien(chemin):
    """(cases cochees et temps reels, notes, texte, {identifiant: (pages, minutes)} des lectures
    chronometrees, texte de la section "Mes echeances")."""
    etat, notes, texte, mesures, mes = {}, "", None, {}, ""
    try:
        with open(chemin, encoding="utf-8") as f:
            texte = f.read()
    except OSError:
        return etat, notes, texte, mesures, mes
    for m in re.finditer(r"^- \[( |x|X)\] (.*?)<!-- id:(\w+) -->", texte, re.M):
        minutes = minutes_reelles(m.group(2))
        etat[m.group(3)] = (m.group(1).lower() == "x", minutes)
        pages = re.search(r"\((\d+) p\.", m.group(2))
        if minutes and pages:
            mesures[m.group(3)] = (int(pages.group(1)), minutes)
    notes = section(texte, "## Notes", None)
    mes = section(texte, TITRE_MES_ECHEANCES, "## Notes")
    return etat, notes, texte, mesures, mes


RE_ECHEANCE = re.compile(r"^\s*[-*]\s*(?:(\d{1,2})[./](\d{1,2})[./](\d{2,4})|(\d{4})-(\d{2})-(\d{2}))"
                         r"(?:\s+(?:à\s+)?(\d{1,2})\s*[:h]\s*(\d{2}))?\s*[·:,;\-]*\s*(.*)$", re.M)


def echeances_manuelles(texte):
    """Echeances ecrites a la main dans la section "Mes echeances" (lignes "- 15.12.2026 23:59 · ...")."""
    texte = re.sub(r"<!--.*?-->", "", texte or "", flags=re.S)
    out = []
    for m in RE_ECHEANCE.finditer(texte):
        j, mo, a, ai, moi, ji, h, mi, reste = m.groups()
        try:
            if ai:
                d = dt.datetime(int(ai), int(moi), int(ji))
            else:
                a = int(a) + (2000 if len(a) == 2 else 0)
                d = dt.datetime(a, int(mo), int(j))
            d = d.replace(hour=int(h), minute=int(mi)) if h else d.replace(hour=23, minute=59)
        except ValueError:
            continue
        morceaux = [x.strip() for x in re.split(r"\s+·\s+", reste.strip()) if x.strip()]
        cours, nom = (morceaux[0], " · ".join(morceaux[1:])) if len(morceaux) > 1 else ("", reste.strip())
        out.append({"date": d, "cours": cours, "nom": nom or "(sans intitulé)", "en_retard": False, "manuelle": True})
    return out


def charger_mesures():
    try:
        with open(MESURES, encoding="utf-8") as f:
            return {k: tuple(v) for k, v in json.load(f).items()}
    except Exception:
        return {}


def sauver_mesures(mesures):
    os.makedirs(ms.APP_DIR, exist_ok=True)
    with open(MESURES + ".tmp", "w", encoding="utf-8") as f:
        json.dump(mesures, f, indent=1)
    os.replace(MESURES + ".tmp", MESURES)


def calcul_vitesse(mesures):
    """(pages par heure, nombre de lectures) d'apres {identifiant: (pages, minutes)}, ou None.

    Une mesure invraisemblable (moins de 1 ou plus de 150 pages par heure : faute de frappe, lecture
    interrompue) est ecartee pour ne pas fausser la moyenne.
    """
    bonnes = [(p, m) for p, m in mesures.values() if m > 0 and 1 <= p / (m / 60) <= 150]
    pages, minutes = sum(p for p, _ in bonnes), sum(m for _, m in bonnes)
    if not bonnes:
        return None
    return round(pages / (minutes / 60), 1), len(bonnes)


def vitesse_observee(chemin):
    """Vitesse d'apres TOUS les temps reels notes : ceux gardes des generations precedentes (les lectures
    passees sortent du fichier) et ceux du fichier actuel, pas encore gardes."""
    return calcul_vitesse({**charger_mesures(), **lire_ancien(chemin)[3]})


# ------------------------------------------------------------------ rendu Markdown
def nom_profil(vitesse):
    for nom, v, _ in sc.PROFILS:
        if v == vitesse:
            return f"profil « {nom} »"
    return "réglage personnel"


def sans_tirets_longs(texte):
    """Aucun tiret long dans un fichier produit, meme ceux des titres ecrits par les enseignants."""
    return texte.replace(chr(0x2013), "-").replace(chr(0x2014), "-")


def ligne_lecture(f, s, vitesse, etat, vus, nouvelles):
    """Ligne a cocher d'une lecture, avec duree, statut et origine du statut."""
    fd = sc.fmt_duree
    p_pdf, p = f.get("pages"), sc.pages_a_lire(f)
    nom = re.sub(r"\.pdf$", "", f["nom"], flags=re.I)
    if f.get("lien") and f.get("url"):
        nom = f"[{nom}]({f['url']})"
    if f.get("pages_consigne"):
        plages = ", ".join(f"{a}-{b}" for a, b in f["plages"])
        duree = f" ({p} p. d'après la consigne : pp. {plages}, {fd(p / vitesse)})"
    else:
        duree = f" ({p} p., {fd(p / vitesse)})" if p else ""
    facultatif = "" if f["statut"] == ms.T["O"] else " (facultatif)"
    if f["origine"] == "déduit":
        etiq = "*À lire (déduit)*"
    elif f["origine"] == "consigne":
        etiq = f"**{f['statut']}**{facultatif}, d'après la consigne : « {f['extrait']} »"
    else:
        etiq = f"**{f['statut']}**{facultatif}"
    if not f.get("pages_consigne") and p_pdf and p_pdf > sc.PAGES_LONG:
        etiq += f" · *{p_pdf} p. sans pages précisées : durée sans doute surestimée*"
    if (f"{s['cid']}:{s['section']}", f["nom"]) in nouvelles:
        etiq += " · **nouveau**"
    vus[f["nom"]] += 1
    ident = sc.id_lecture(s["cid"], f["nom"] + (f"#{vus[f['nom']]}" if vus[f["nom"]] > 1 else ""))
    coche, reel = etat.get(ident, (False, None))
    suite = f" · réel : {reel} min" if reel else ""
    return f"- [{'x' if coche else ' '}] {nom}{duree} · {etiq}{suite} <!-- id:{ident} -->"


def rendre_md(fenetre, echeances, a_dater, sans_seance, aujourdhui, jours, etat, notes, avec_pages, vitesse,
              alertes=(), changements=None, nouvelles=frozenset(), mes_echeances="", non_controles=(),
              a_surveiller=()):
    MN, fd = sc.MOIS_NOMS, sc.fmt_duree
    L = [ms.MARQUE, "", "# Ma semaine", "",
         f"Généré le {aujourdhui.day} {MN[aujourdhui.month - 1]} {aujourdhui.year}, pour les {jours} prochains jours. "
         "Explications en bas du fichier (« Comment lire ce fichier »).", ""]
    L += [f"## À vérifier ({len(alertes)})", ""]
    if alertes:
        L += ["Contrôles automatiques. Chaque point peut cacher une séance ou une lecture absente du planning.", ""]
        L += [f"- {a}" for a in alertes]
    else:
        L.append("Aucune incohérence trouvée par les contrôles automatiques.")
    if non_controles:
        L += ["", "Non contrôlés (réglage `\"controle\": false` dans horaire.json) : " + ", ".join(non_controles) + "."]
    L.append("")
    if a_surveiller:
        L += [f"## À surveiller ({len(a_surveiller)})", "",
              "Rien d'anormal : ces séances n'ont pas encore de lecture visible, alors que le cours en donne "
              "d'habitude, ou leur contenu est verrouillé. Regénère le fichier avant la séance.", ""]
        L += [f"- {a}" for a in a_surveiller] + [""]
    L += ["## Depuis la dernière génération", ""]
    if changements is None:
        L.append("Première génération : rien à comparer pour l'instant.")
    elif not changements:
        L.append("Rien de changé dans Moodle pour cette période.")
    else:
        L += [f"- {c}" for c in changements]
    L += ["", "## Échéances", ""]
    proches = [e for e in echeances if aujourdhui - dt.timedelta(days=7) <= e["date"].date()
               <= aujourdhui + dt.timedelta(days=90)]
    if not proches:
        L.append("Aucune échéance pour les 90 prochains jours.")
    for e in sorted(proches, key=lambda e: e["date"]):
        marque = ""
        if e.get("manuelle"):
            marque = " · *ajoutée à la main*" + (" · passée" if e["date"].date() < aujourdhui else "")
        elif e["en_retard"]:
            marque = " · **en retard**"
        if e["date"].date() == aujourdhui:
            marque += " · **aujourd'hui**"
        cours = f" · {e['cours']}" if e["cours"] else ""
        L.append(f"- {e['date']:%d.%m.%Y %H:%M}{cours} · {e['nom']}{marque}")
    L += ["", "*Calendrier de Moodle, plus tes échéances de la section « Mes échéances » (en bas). "
          "Un rendu sans date dans Moodle n'y figure que si tu l'ajoutes.*", ""]
    semaines = collections.OrderedDict()
    for s in fenetre:
        semaines.setdefault(s["date"] - dt.timedelta(days=s["date"].weekday()), []).append(s)
    if not semaines:
        L += ["Aucune séance datée dans cette période.", ""]
    for debut, seances in semaines.items():
        fin_sem = debut + dt.timedelta(days=6)
        tot = sum((sc.pages_a_lire(f) or 0) for s in seances for f in s["lectures"]
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
            heure = (s["heure"].lstrip("0").replace(":", " h ") + " · ") if s.get("heure") else ""
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
            for c in s.get("consigne") or []:
                L += [f"Consigne de la section : « {c} »", ""]
            vus = collections.Counter()
            for f in s["lectures"]:
                L.append(ligne_lecture(f, s, vitesse, etat, vus, nouvelles))
            if not s["lectures"] and not s["sans_lecture"]:
                L.append("*Aucune lecture identifiée.*")
            if s["supports"]:
                L += ["", f"Supports de cours : {len(s['supports'])} fichier(s), non comptés dans la lecture."]
            L.append("")
    L += ["## À dater à la main", ""]
    raisons = collections.defaultdict(collections.Counter)
    for s in a_dater:
        raisons[s["cours"]][s["precision"]] += 1
    for k, rs in raisons.items():
        L.append(f"- {k} : " + " ; ".join(f"{v} séance(s), {r}" for r, v in rs.items()) + ".")
    for k in sans_seance:
        L.append(f"- {k} : aucune séance datée ou numérotée dans les titres de sections.")
    if not raisons and not sans_seance:
        L.append("Rien : toutes les séances trouvées sont datées.")
    L += ["", "## Comment lire ce fichier", "",
          "- **Obligatoire**, **Complémentaire** : écrit par l'enseignant dans Moodle (étiquette, liste de "
          "lectures, intitulé).",
          "- **… d'après la consigne** : le statut vient d'une phrase de l'enseignant, recopiée entre "
          "guillemets pour que tu puisses juger. Les pages indiquées (« pp. 225-255 ») remplacent alors "
          "la longueur du PDF.",
          "- *À lire (déduit)* : rien ne le dit ; le programme suppose que c'est une lecture parce que c'est "
          "un fichier qui n'est pas une diapo, placé dans la séance. Ça peut être faux.",
          "- *date déduite* : l'année ou le jour n'est pas écrit dans le titre de la section.",
          "- *date déduite du numéro* : la section dit « Séance 7 » sans date. La date est comptée depuis une "
          "séance datée du même cours, une séance par semaine au jour du cours, en sautant les jours "
          "annoncés sans cours dans Moodle (fériés, semaine intercalaire).",
          "- Le jour de chaque cours vient de horaire.json s'il existe, sinon des dates du cours dans Moodle.",
          f"- Durées : pages divisées par **{vitesse} pages par heure** ({nom_profil(vitesse)}). "
          "C'est une estimation, pas une mesure : note ton temps réel pour la corriger.",
          "- Pour noter ton temps, ajoute `réel : 70` (minutes) ou `réel : 1 h 10` sur la ligne de la lecture. "
          "Ces temps calculent ta vraie vitesse de lecture, proposée dans la fenêtre de Ma semaine. "
          "Les cases cochées, ce temps, et les sections « Mes échéances » et « Notes » sont conservés "
          "quand le fichier est regénéré ; tout le reste est réécrit.", ""]
    L += [TITRE_MES_ECHEANCES, "", mes_echeances or AIDE_MES_ECHEANCES, "", "## Notes", "", notes or ""]
    return sans_tirets_longs("\n".join(L).rstrip() + "\n")


# ------------------------------------------------------------------ collecte (lecture seule)
def collecter(tok, y0, dire, aujourdhui):
    """Seances de tous les cours suivis, datees, avec leurs lectures. Lecture seule sur Moodle."""
    horaires = sc.charger_horaire()
    cours = ms.cours_inscrits(tok, ms.infos_session(tok)["userid"])
    toutes, suivis = [], {}
    for c in cours:
        cid = str(c["id"])
        h = horaires.get(cid, {})
        if h.get("suivi") is False:
            continue
        nom_cours = h.get("titre") or sc.nom_affiche(c["fullname"])
        suivis[c["id"]] = {"nom": nom_cours, "jour": h.get("jour"), "source": "l'horaire",
                           "controle": h.get("controle", True) is not False}
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
            seance = {"cours": nom_cours, "cid": c["id"], "section": s.get("id"), "titre": titre,
                      "numero": numero, "analyse": an,
                      "lectures": [f for f in fichiers if not f["support"]],
                      "supports": [f for f in fichiers if f["support"]],
                      "nb_modules": len(s.get("modules") or []),
                      "consigne": sc.consigne_section(s.get("summary")),
                      "sans_travail": bool(sc.RE_SANS_TRAVAIL.search(titre)),
                      "sans_lecture": bool(sc.RE_SANS_LECTURE.search(titre)),
                      "ouverture": re.sub(r"<[^>]+>", "", html.unescape(s.get("availabilityinfo") or "")).strip() or None}
            d, prec = sc.dater(an, h)
            seance["date"], seance["precision"], seance["heure"] = d, prec, h.get("heure")
            seance["explicite"] = bool(d)
            toutes.append(seance)
    # Jour du cours sans horaire.json : celui de ses dates dans Moodle, s'il est net. Les titres qui
    # donnent une semaine ou deux dates sont alors redates sur ce jour.
    for cid, v in suivis.items():
        if v["jour"] is not None:
            continue
        propres = [s for s in toutes if s["cid"] == cid]
        j = sc.jour_habituel([s["date"] for s in propres if s["explicite"] and not s["sans_travail"]
                              and s["analyse"]["type"] == "date"])
        if j is None:
            continue
        v["jour"], v["source"] = j, "ses dates dans Moodle"
        for s in propres:
            if s["analyse"] and s["analyse"]["type"] in ("semaine", "alternatives"):
                s["date"], s["precision"] = sc.dater(s["analyse"], {"jour": j}, "ses dates dans Moodle")
    # Calendrier lu dans TOUS les cours (feries, semaine intercalaire), puis seances numerotees sans
    # date placees d'apres le numero, le jour du cours et une seance datee du meme cours.
    cal = sc.construire_calendrier(toutes, horaires.get("calendrier"))
    ancres = collections.defaultdict(list)
    for s in toutes:
        if s["explicite"] and s["numero"]:
            ancres[s["cid"]].append((s["numero"], s["date"]))
    # Dernier recours, pour un cours numerote avec moins de 3 dates : le jour de ses seances datees,
    # s'il est le meme pour toutes (cas reel : seule la "Seance 1 : lundi 14 septembre" est datee).
    for cid, v in suivis.items():
        jours = {d.weekday() for _, d in ancres[cid]}
        if v["jour"] is None and len(jours) == 1 and any(s["cid"] == cid and not s["date"] for s in toutes):
            v["jour"] = jours.pop()
            n = len(ancres[cid])
            v["source"] = "sa séance datée dans Moodle" if n == 1 else f"ses {n} séances datées dans Moodle"
    for s in toutes:
        if not s["date"] and s["numero"]:
            s["date"], s["precision"] = sc.dater_par_numero(s["numero"], ancres[s["cid"]], cal,
                                                           suivis[s["cid"]]["jour"], aujourdhui)
        # Semaine generee par le format "semaines" de Moodle qui tombe sur une semaine annoncee sans
        # cours ailleurs : ce n'est pas une seance (une seance explicitement datee, elle, reste en alerte).
        if (s["date"] in cal["sans_cours"] and not s["sans_travail"] and s["analyse"]
                and s["analyse"]["type"] == "semaine"):
            s["sans_cours_deduit"] = cal["sans_cours"][s["date"]]
            s["sans_travail"] = True
    seances = [s for s in toutes if s["date"]]
    a_dater = [s for s in toutes if not s["date"]]
    sans_seance = [v["nom"] for cid, v in suivis.items() if not any(s["cid"] == cid for s in toutes)]
    ev = ms.api(tok, "core_calendar_get_action_events_by_timesort",
                timesortfrom=int(time.time()) - 7 * 86400, limitnum=50).get("events", [])
    ids_suivis = {str(cid) for cid in suivis}
    echeances = [{"date": dt.datetime.fromtimestamp(e["timestart"]),
                  "cours": html.unescape(e["course"]["fullname"]), "nom": html.unescape(e["name"]),
                  "en_retard": bool(e.get("overdue"))}
                 for e in ev if str(e["course"]["id"]) in ids_suivis]
    echeances.sort(key=lambda x: x["date"])
    return seances, a_dater, sans_seance, echeances, suivis, cal


def connexion():
    cfg = ms.charger_config()
    ms.appliquer_config(cfg)
    if not cfg["token"]:
        raise ms.Erreur("Aucune connexion trouvée. Lance MoodleSync et connecte-toi une première fois.")
    aujourdhui = dt.date.today()
    return cfg["token"], aujourdhui, (aujourdhui.year if aujourdhui.month >= 8 else aujourdhui.year - 1)


def ecrire(chemin, texte):
    """Ecrit un fichier produit, sauf s'il existe sans la marque de MoodleSync (fichier de l'utilisateur)."""
    try:
        with open(chemin, encoding="utf-8") as f:
            if ms.MARQUE not in f.read():
                raise ms.Erreur(f"Le fichier « {os.path.basename(chemin)} » existe déjà sans la marque de "
                                "MoodleSync : je n'y touche pas.")
    except OSError:
        pass
    os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
    with open(chemin + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texte)
    os.replace(chemin + ".tmp", chemin)


def generer(jours, vitesse, dossier, avec_pages=True, cache=CACHE, dire=print):
    """Cree (ou regenere) Ma semaine.md. Renvoie un petit compte rendu."""
    tok, aujourdhui, y0 = connexion()
    chemin = os.path.join(dossier, FICHIER)
    etat, notes, ancien, mesures, mes = lire_ancien(chemin)
    if ancien is not None and ms.MARQUE not in ancien:
        raise ms.Erreur(f"Le fichier « {FICHIER} » existe déjà sans la marque de MoodleSync : je n'y touche pas.")
    if mesures:
        # Les lectures passees vont sortir du fichier : leurs temps reels sont gardes pour la vitesse.
        sauver_mesures({**charger_mesures(), **mesures})
    seances, a_dater, sans_seance, echeances, suivis, cal = collecter(tok, y0, dire, aujourdhui)
    fin = aujourdhui + dt.timedelta(days=jours)
    alertes = sc.controles(seances, suivis, cal, aujourdhui, fin)
    a_surveiller = sc.surveillances(seances, suivis, aujourdhui, fin)
    non_controles = [v["nom"] for v in suivis.values() if not v["controle"]]
    apres = sc.instantane(seances)
    precedent = charger_etat()
    changements, nouvelles = (None, set()) if precedent is None else \
        sc.differences(precedent.get("seances", {}), apres, aujourdhui, fin)
    echeances = echeances + echeances_manuelles(mes)
    fenetre = sorted((s for s in seances if aujourdhui <= s["date"] <= fin),
                     key=lambda s: (s["date"], s.get("heure") or ""))
    if avec_pages:
        for s in fenetre:
            for f in s["lectures"]:
                if f["pdf"]:
                    dire(f"Comptage des pages : {f['nom'][:60]}")
                    f["pages"] = sc.pages_pdf(tok, f, cache)
    texte = rendre_md(fenetre, echeances, a_dater, sans_seance, aujourdhui, jours, etat, notes, avec_pages, vitesse,
                      alertes, changements, nouvelles, mes, non_controles, a_surveiller)
    ecrire(chemin, texte)
    sauver_etat({"genere": dt.datetime.now().isoformat(timespec="seconds"), "seances": apres})
    lectures = [f for s in fenetre for f in s["lectures"]]
    return {"chemin": chemin, "seances": len(fenetre), "lectures": len(lectures),
            "deduites": sum(1 for f in lectures if f["origine"] == "déduit"), "alertes": len(alertes),
            "a_surveiller": len(a_surveiller), "changements": len(changements or [])}


# ------------------------------------------------------------------ audit du semestre ecoule
def categorie(f):
    if f["origine"] == "déduit":
        return "déduit"
    return "consigne" if f["origine"] == "consigne" else "enseignant"


def rendre_audit(seances, a_dater, suivis, cal, debut, fin, alertes, aujourdhui):
    """Bilan, cours par cours, de ce que le programme a su lire du semestre ecoule."""
    L = [ms.MARQUE, "", "# Ma semaine : audit du semestre", "",
         f"Généré le {sc.jour_long(aujourdhui)} {aujourdhui.year}. Période relue : du {sc.jour_long(debut)} "
         f"au {sc.jour_long(fin)} (séances déjà passées, dont tu connais la réalité).", "",
         "But : repérer un cours mal lu AVANT qu'une lecture ou une séance manque. Compare chaque ligne avec "
         "ce que tu sais du cours.", "",
         "| Cours | Jour (source) | Séances | dont datées par numéro | Lectures : enseignant / consigne / déduites"
         " | Séances sans lecture |", "|---|---|---|---|---|---|"]
    a_regarder = []
    for cid, v in suivis.items():
        v = sc.suivi(v)
        ss = [s for s in seances if s["cid"] == cid and debut <= s["date"] <= fin and not s["sans_travail"]]
        lec = collections.Counter(categorie(f) for s in ss for f in s["lectures"])
        vides = [s for s in ss if not s["lectures"] and not s["sans_lecture"]]
        par_num = sum(1 for s in ss if not s["explicite"])
        jour = f"{sc.JOURS_NOMS[v['jour']]} ({v['source']})" if v["jour"] is not None else "inconnu"
        L.append(f"| {v['nom']} | {jour} | {len(ss)} | {par_num} | {lec['enseignant']} / {lec['consigne']} / "
                 f"{lec['déduit']} | {len(vides)} |")
        total = sum(lec.values())
        if not ss:
            a_regarder.append(f"{v['nom']} : aucune séance reconnue. Cours organisé autrement (thèmes, "
                              "chapitres) : le planning ne peut rien en dire.")
        elif total and lec["déduit"] / total > 0.5:
            a_regarder.append(f"{v['nom']} : {lec['déduit']} lectures sur {total} ont un statut deviné. "
                              "Vérifie dans Moodle si l'enseignant l'écrit ailleurs (syllabus, polycopié).")
        if ss and len(vides) / len(ss) > 0.5:
            a_regarder.append(f"{v['nom']} : {len(vides)} séances sur {len(ss)} sans aucune lecture trouvée. "
                              "Soit le cours n'en donne pas, soit elles sont ailleurs (polycopié, liens, autre section).")
    L += ["", "## À regarder", ""] + ([f"- {x}" for x in a_regarder] or ["Rien de suspect."])
    L += ["", f"## Contrôles sur la période ({len(alertes)})", ""] + ([f"- {a}" for a in alertes] or ["Aucun."])
    L += ["", "## Calendrier lu dans Moodle", ""]
    for k, (a, b) in sorted(cal["semestres"].items()):
        L.append(f"- Semestre {k[1]} {k[0]}-{k[0] + 1} : du {sc.court(a)}.{a.year} au {sc.court(b)}.{b.year} "
                 "(premières et dernières dates écrites dans les titres).")
    raisons = collections.OrderedDict()
    for d in sorted(cal["sans_cours"]):
        raisons.setdefault(cal["sans_cours"][d], []).append(d)
    for r, ds in raisons.items():
        L.append(f"- Sans cours du {sc.court(ds[0])} au {sc.court(ds[-1])} : {r}" if len(ds) > 1 else
                 f"- Sans cours le {sc.court(ds[0])} : {r}")
    if a_dater:
        L += ["", "## Séances non datées", ""]
        groupes = collections.OrderedDict()
        for s in a_dater:
            groupes.setdefault((s["cours"], s["precision"]), []).append(s)
        for (cours, raison), g in groupes.items():
            nums = sorted(s["numero"] for s in g if s.get("numero"))
            quoi = (f"« {g[0]['titre'].strip()} »" if len(g) == 1 else
                    f"{len(g)} séances" + (f" (n° {nums[0]} à {nums[-1]})" if len(nums) == len(g) else ""))
            L.append(f"- {cours} : {quoi}, {raison}.")
    return sans_tirets_longs("\n".join(L).rstrip() + "\n")


def auditer(dossier, dire=print):
    """Relit le semestre en cours jusqu'a hier et ecrit Ma semaine - audit.md. Renvoie un compte rendu."""
    tok, aujourdhui, y0 = connexion()
    seances, a_dater, _, _, suivis, cal = collecter(tok, y0, dire, aujourdhui)
    bornes = cal["semestres"].get(sc.semestre(aujourdhui))
    if not bornes:
        raise ms.Erreur("Début du semestre introuvable : aucune date dans les titres de sections.")
    debut, fin = bornes[0], aujourdhui - dt.timedelta(days=1)
    alertes = sc.controles(seances, suivis, cal, debut, fin)
    chemin = os.path.join(dossier, FICHIER_AUDIT)
    ecrire(chemin, rendre_audit(seances, a_dater, suivis, cal, debut, fin, alertes, aujourdhui))
    return {"chemin": chemin, "alertes": len(alertes)}


# ------------------------------------------------------------------ ouverture du fichier produit
def ouvrir_document(chemin):
    """Ouvre un fichier avec le programme associe ; sans association, avec l'editeur de texte du systeme.

    Renvoie "associe", "texte" ou None (echec). Beaucoup d'ordinateurs n'ont aucun programme associe
    aux fichiers .md : le Bloc-notes (Windows) ou TextEdit (macOS) existent partout.
    """
    import subprocess
    try:
        if ms.MAC:
            if subprocess.run(["open", chemin]).returncode == 0:
                return "associe"
            return "texte" if subprocess.run(["open", "-t", chemin]).returncode == 0 else None
        if sys.platform.startswith("win"):
            try:
                os.startfile(chemin)
                return "associe"
            except OSError:
                subprocess.Popen(["notepad.exe", chemin])
                return "texte"
        subprocess.Popen(["xdg-open", chemin])
        return "associe"
    except Exception:
        return None


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
    ouvrir_v = tk.BooleanVar(value=bool(prefs.get("ouvrir", True)))
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
        obs_txt.configure(wraplength=430 if r else 580)
        if r:
            obs_txt.configure(text=f"Ta vitesse mesurée : {r[0]:g} pages/h, d'après {r[1]} lecture(s) "
                                   "chronométrée(s).")
            obs_btn.configure(command=lambda: vit_v.set(max(1, round(r[0]))))
            obs_btn.pack(side="right")
        else:
            obs_txt.configure(text="Pas encore de vitesse mesurée. Quand tu as lu un texte, ajoute « réel : 70 » "
                                   "(minutes passées) sur sa ligne dans Ma semaine.md, puis regénère : ta vraie "
                                   "vitesse s'affichera ici, avec un bouton pour l'utiliser.")
            obs_btn.pack_forget()

    vit_v.trace_add("write", maj_desc)
    maj_desc()
    maj_obs()

    # --- options et dossier
    bloc = ttk.LabelFrame(cadre, text="Options", padding=10)
    bloc.pack(fill="x", pady=4)
    ttk.Checkbutton(bloc, variable=pages_v, text="Compter les pages (télécharge les PDF de la période "
                    "dans un dossier temporaire)").pack(anchor="w")
    ttk.Checkbutton(bloc, variable=ouvrir_v, text="Ouvrir le fichier une fois créé (Ma semaine.md ou l'audit)"
                    ).pack(anchor="w", pady=(4, 0))
    ouvrir_v.trace_add("write", lambda *_: sauver_prefs({**charger_prefs(), "ouvrir": bool(ouvrir_v.get())}))
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
    b_audit = ttk.Button(actions, text="Audit du semestre")
    b_audit.pack(side="right")
    journal = tk.Text(cadre, height=5, wrap="word", state="disabled", relief="flat", borderwidth=1)
    journal.pack(fill="both", expand=True, pady=(6, 0))

    def log(t):
        journal.configure(state="normal")
        journal.insert("end", t + "\n")
        journal.see("end")
        journal.configure(state="disabled")

    def ouvrir_fichier():
        if not dernier["chemin"]:
            return
        r = ouvrir_document(dernier["chemin"])
        if r == "texte":
            log("Aucun programme n'est associé aux fichiers .md : ouvert dans l'éditeur de texte du système. "
                "Pour une lecture plus confortable, associe les .md à Obsidian, Typora ou VS Code.")
        elif r is None:
            log("Impossible d'ouvrir le fichier automatiquement. Ouvre-le depuis le dossier.")

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
                    if "seances" in val:
                        log(f"Terminé : {val['seances']} séance(s), {val['lectures']} lecture(s) "
                            f"dont {val['deduites']} déduite(s).\n{val['chemin']}")
                        if val["alertes"]:
                            log(f"{val['alertes']} point(s) à vérifier : voir « À vérifier » en haut du fichier.")
                        if val["a_surveiller"]:
                            log(f"{val['a_surveiller']} séance(s) à surveiller (lectures pas encore déposées).")
                        if val["changements"]:
                            log(f"{val['changements']} changement(s) dans Moodle depuis la dernière génération.")
                    else:
                        log(f"Audit terminé ({val['alertes']} point(s) relevés sur le semestre).\n{val['chemin']}")
                    bouton.configure(state="normal")
                    b_audit.configure(state="normal")
                    b_fichier.configure(state="normal",
                                        text="Ouvrir Ma semaine.md" if "seances" in val else "Ouvrir l'audit")
                    b_dossier.configure(state="normal")
                    maj_obs()
                    if ouvrir_v.get() and not os.environ.get("MASEMAINE_TEST"):
                        ouvrir_fichier()
                    return
                else:
                    log(val)
                    bouton.configure(state="normal")
                    b_audit.configure(state="normal")
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
        sauver_prefs({"jours": j, "vitesse": v, "pages": bool(pages_v.get()), "dossier": dossier_v.get(),
                      "ouvrir": bool(ouvrir_v.get())})
        log(f"Période : {j} jour(s). Vitesse : {v} pages/h.")

        executer(lambda: generer(j, v, dossier_v.get(), pages_v.get(), CACHE, lambda t: q.put(("log", t))))

    def executer(travail):
        bouton.configure(state="disabled")
        b_audit.configure(state="disabled")

        def tache():
            try:
                q.put(("ok", travail()))
            except ms.SessionExpiree:
                q.put(("err", "La session a expiré. Ouvre MoodleSync, reconnecte-toi, puis réessaie."))
            except ms.Erreur as e:
                q.put(("err", str(e)))
            except Exception as e:
                q.put(("err", f"Erreur inattendue : {e!r}"))
        threading.Thread(target=tache, daemon=True).start()
        sonder()

    def lancer_audit():
        log("Audit : relecture du semestre écoulé (séances passées).")
        executer(lambda: auditer(dossier_v.get(), lambda t: q.put(("log", t))))

    bouton.configure(command=lancer)
    b_audit.configure(command=lancer_audit)
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
    if "--audit" in sys.argv:
        p = charger_prefs()
        r = auditer(p.get("dossier") or ms.charger_config()["dest"], print)
        print(f"Audit terminé : {r['alertes']} point(s) relevés. Fichier : {r['chemin']}")
        return
    if "--creer" in sys.argv:
        def opt(nom, defaut):
            return type(defaut)(sys.argv[sys.argv.index(nom) + 1]) if nom in sys.argv else defaut
        p = charger_prefs()
        r = generer(opt("--jours", int(p.get("jours", 14))), opt("--vitesse", int(p.get("vitesse", sc.VITESSE_DEFAUT))),
                    p.get("dossier") or ms.charger_config()["dest"], True, CACHE, print)
        print(f"Terminé : {r['seances']} séance(s), {r['lectures']} lecture(s) dont {r['deduites']} déduite(s).")
        if r["alertes"]:
            print(f"{r['alertes']} point(s) à vérifier : voir « À vérifier » en haut du fichier.")
        if r["a_surveiller"]:
            print(f"{r['a_surveiller']} séance(s) à surveiller (lectures pas encore déposées).")
        if r["changements"]:
            print(f"{r['changements']} changement(s) dans Moodle depuis la dernière génération.")
        print(f"Fichier : {r['chemin']}")
        return
    lancer_fenetre()


if __name__ == "__main__":
    main()
