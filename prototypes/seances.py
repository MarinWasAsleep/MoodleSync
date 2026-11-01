#!/usr/bin/env python3
"""Prototype : modele de "seance" a partir des cours Moodle (LECTURE SEULE).

But : verifier, sur de vrais cours, qu'on sait (1) dater une seance a partir du titre de sa section,
(2) lister ses lectures avec un statut explicite ou "deduit", (3) rapprocher les echeances de
l'API. Ce fichier ne modifie ni moodle_sync.py, ni Moodle, ni le dossier de rangement. Il reutilise
les fonctions de moodle_sync.py (jeton, API, statuts de lecture).

Horaire : fichier JSON facultatif `horaire.json` dans le dossier des reglages de MoodleSync
(jamais publie). Exemple :
  {"37540": {"jour": 2, "heure": "10:15", "titre": "Intro. science politique (seminaire)"},
   "38184": {"suivi": false}}
`jour` : 0 = lundi ... 6 = dimanche. Sert a choisir la bonne date quand un titre en donne
plusieurs (un groupe par jour) et a convertir une semaine en date de seance.

Utilisation : python prototypes/seances.py [--jours 14] [--pages] [--cache DOSSIER] [--json SORTIE]
"""
import sys, os, re, json, html, argparse, datetime as dt, collections, hashlib, logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moodle_sync as ms

MOIS = {"janvier": 1, "janv": 1, "fevrier": 2, "fevr": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "aout": 8, "septembre": 9, "sept": 9, "octobre": 10, "oct": 10,
        "novembre": 11, "nov": 11, "decembre": 12, "dec": 12}
JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
RE_PREFIXE = re.compile(r"(?i)\b(?:s[ée]ance|session|cours|semaine|week|th[èe]me|partie|chapitre)\s*(?:n[°o]\s*)?\d+\b|\bS\d{1,2}\b")
TIRETS = chr(0x2013) + chr(0x2014)          # demi-cadratin et cadratin, tels qu'ils apparaissent dans les titres Moodle
RE_TXT = re.compile(
    r"(?<!\d)(\d{1,2})(?:er)?\s*(?:(?:-|[" + TIRETS + r"]|et|&)\s*(\d{1,2})(?:er)?\s+)?"
    r"(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre"
    r"|janv|f[ée]vr|sept|oct|nov|d[ée]c)\b\.?(?:\s+(\d{4}))?", re.I)
RE_NUM = re.compile(r"(?<![\d/.])(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?![\d/.])")
RE_NUMEROTEE = re.compile(r"(?i)\bs[ée]ance\s*(?:n[°o]\s*)?\d+")
RE_SANS_TRAVAIL = re.compile(r"(?i)pas de (?:cours|s[ée]ance)|jour f[ée]ri[ée]|semaine intercalaire|cong[ée]|vacances")
RE_SANS_LECTURE = re.compile(r"(?i)pas de lecture")
RE_OPTIONNEL = re.compile(r"(?i)optionnel|facultatif")
A_LIRE = "À lire (statut non précisé)"
# Vitesses de lecture proposees (pages par heure) : (nom, pages/h, origine). Base : 400 mots par page,
# hypothese non mesuree. Voir INSPIRATIONS.md, partie III.
PROFILS = [
    ("Courante", 35, "238 mots/min (Brysbaert 2019, non-fiction en anglais), soit 35 pages/h : lecture sans effort de mémorisation."),
    ("Attentive", 21, "138 mots/min (Carver 1992, « mémoriser », rapporté par Brysbaert), soit 21 pages/h."),
    ("Étude", 12, "Valeur intermédiaire proposée ici, SANS SOURCE : lecture avec notes. À étalonner avec ton temps réel."),
    ("Approfondie", 6, "Norme de la VU Amsterdam (5 à 6 pages/h) pour la lecture d'étude littéraire ou technique."),
]
VITESSE_DEFAUT = 12


def sans_accents(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).lower()


def annee_pour(mois, y0):
    """Annee academique y0-y0+1 : aout a decembre -> y0, janvier a juillet -> y0+1."""
    return y0 if mois >= 8 else y0 + 1


def analyser_titre(titre, y0):
    """Dates lues dans un titre de section : {type, dates: [(date, annee_deduite)]} ou None."""
    # Accents et casse retires d'abord : un titre de Moodle peut contenir "séptembre" (faute reelle).
    t = RE_PREFIXE.sub(" ", sans_accents(titre or ""))
    trouvees, spans = [], []
    for m in RE_TXT.finditer(t):
        j1, j2, mois, an = m.groups()
        mois = MOIS.get(mois.lower().rstrip(".").replace("septembe", "septembre"))
        if not mois:
            continue
        deduite = an is None
        a = int(an) if an else annee_pour(mois, y0)
        try:
            ds = [dt.date(a, mois, int(j)) for j in (j1, j2) if j]
        except ValueError:
            continue
        trouvees.append({"dates": ds, "alt": bool(j2), "deduite": deduite, "span": m.span()})
    if not trouvees:
        for m in RE_NUM.finditer(t):
            j, mois, an = m.groups()
            if not (1 <= int(mois) <= 12 and 1 <= int(j) <= 31):
                continue
            deduite = an is None
            a = int(an) + (2000 if an and len(an) == 2 else 0) if an else annee_pour(int(mois), y0)
            try:
                trouvees.append({"dates": [dt.date(a, int(mois), int(j))], "alt": False, "deduite": deduite,
                                 "span": m.span()})
            except ValueError:
                pass
    if not trouvees:
        return None
    if len(trouvees) == 2 and not trouvees[0]["alt"] and not trouvees[1]["alt"]:
        entre = t[trouvees[0]["span"][1]:trouvees[1]["span"][0]]
        d1, d2 = trouvees[0]["dates"][0], trouvees[1]["dates"][0]
        if re.fullmatch(r"\s*[-" + TIRETS + r"]\s*", entre) and 5 <= (d2 - d1).days <= 7:
            return {"type": "semaine", "dates": [d1], "deduite": trouvees[0]["deduite"]}
    t0 = trouvees[0]
    return {"type": "alternatives" if t0["alt"] else "date", "dates": t0["dates"], "deduite": t0["deduite"]}


def dater(analyse, horaire):
    """(date, precision) de la seance, ou (None, raison)."""
    if not analyse:
        return None, "aucune date lisible"
    jour = horaire.get("jour")
    ds, notes = analyse["dates"], []
    if analyse["deduite"]:
        notes.append("année déduite")
    if analyse["type"] == "semaine":
        if jour is None:
            return ds[0], "semaine lue, jour inconnu (lundi pris)"
        d = ds[0] + dt.timedelta(days=(jour - ds[0].weekday()) % 7)
        return d, "; ".join(notes + ["jour déduit de l'horaire"])
    if analyse["type"] == "alternatives":
        if jour is not None:
            for d in ds:
                if d.weekday() == jour:
                    return d, "; ".join(notes + [f"choisie parmi {len(ds)} dates d'après l'horaire"])
        return ds[0], "; ".join(notes + [f"{len(ds)} dates possibles, la première prise"])
    d = ds[0]
    if jour is not None and d.weekday() != jour:
        notes.append(f"jour ({JOURS[d.weekday()]}) différent de l'horaire ({JOURS[jour]})")
    return d, "; ".join(notes) or "lue"


# ------------------------------------------------------------------ seances numerotees sans date
# "Seance 7", "Session 3" : numero fiable meme sans date. "S8" seulement s'il y a aussi une date dans
# le titre ("S2" seul designe souvent le semestre 2).
RE_NUMERO = re.compile(r"\bs(?:eance|ession)\s*(?:n°\s*|no\.?\s*)?(\d{1,2})\b")
RE_NUMERO_COURT = re.compile(r"\bs(\d{1,2})\b")
# Sans cours pour TOUS les cours ce jour-la (ou cette semaine-la). Un simple "pas de cours" sans
# l'une de ces raisons ne concerne que le cours qui l'ecrit.
RE_SANS_COURS_GENERAL = re.compile(r"(?i)jour f[ée]ri[ée]|semaine intercalaire|semaine de lecture|vacances|cong[ée]")


def numero_seance(titre, court=False):
    t = sans_accents(titre or "")
    m = RE_NUMERO.search(t) or (RE_NUMERO_COURT.search(t) if court else None)
    return int(m.group(1)) if m else None


def semestre(d):
    """Cle du semestre : (annee de debut de l'annee academique, 'automne' ou 'printemps')."""
    return (d.year, "automne") if d.month >= 8 else (d.year - 1, "printemps")


def court(d):
    return f"{d.day:02d}.{d.month:02d}"


def lundi(d):
    return d - dt.timedelta(days=d.weekday())


def construire_calendrier(seances, config=None):
    """Calendrier des cours, lu dans les titres de Moodle (et dans la cle "calendrier" de horaire.json).

    Rien n'est invente. Bornes d'un semestre : premiere et derniere date ecrite dans un titre de
    seance, tous cours confondus (les semaines generees par le format "semaines" de Moodle ne comptent
    pas, elles vont souvent au-dela du semestre). Jours sans cours : titres qui l'annoncent pour tout le
    monde (ferie, semaine intercalaire, vacances). horaire.json peut corriger :
      "calendrier": {"semestres": [["2026-09-14", "2026-12-18"]],
                     "sans_cours": ["2026-09-21", ["2026-11-02", "2026-11-08"]]}
    """
    config = config or {}
    bornes, sans = {}, {}
    for s in seances:
        an, d = s.get("analyse"), s.get("date")
        if not an or not d or not s.get("explicite"):
            continue
        if RE_SANS_COURS_GENERAL.search(s["titre"]):
            if an["type"] == "semaine" or "semaine" in sans_accents(s["titre"]):
                jours = [lundi(d) + dt.timedelta(days=i) for i in range(7)]
            else:
                jours = an["dates"]
            for j in jours:
                sans.setdefault(j, f"« {s['titre'].strip()} » ({s['cours']})")
            continue
        if s.get("sans_travail") or an["type"] == "semaine":
            continue
        k = semestre(d)
        b = bornes.get(k)
        bornes[k] = (min(b[0], d), max(b[1], d)) if b else (d, d)
    for a, b in config.get("semestres", []):
        a, b = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        bornes[semestre(a)] = (a, b)
    for x in config.get("sans_cours", []):
        a, b = (x, x) if isinstance(x, str) else x
        a, b = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        while a <= b:
            sans[a] = "horaire.json"
            a += dt.timedelta(days=1)
    bornes = {k: (lundi(a), lundi(b) + dt.timedelta(days=6)) for k, (a, b) in bornes.items()}
    return {"semestres": bornes, "sans_cours": sans}


def jours_de_cours(cal, jour, sem):
    """Dates du semestre `sem` tombant le jour `jour` (0 = lundi), jours sans cours retires."""
    if sem not in cal["semestres"]:
        return []
    a, b = cal["semestres"][sem]
    d = a + dt.timedelta(days=(jour - a.weekday()) % 7)
    out = []
    while d <= b:
        if d not in cal["sans_cours"]:
            out.append(d)
        d += dt.timedelta(days=7)
    return out


def dater_par_numero(n, ancres, cal, jour, aujourdhui):
    """(date, precision) d'une seance numerotee sans date, ou (None, raison).

    `ancres` : [(numero, date)] lues dans les titres du MEME cours. La seance n est placee n - k jours
    de cours apres l'ancre k la plus proche, sur le jour de l'horaire, en sautant les jours sans cours.
    Le calcul reste dans le semestre de l'ancre (les vacances d'un autre semestre ne sont pas connues).
    """
    if jour is None:
        return None, "numéro sans date, et pas de jour pour ce cours dans horaire.json"
    if ancres:
        k, d0 = min(ancres, key=lambda a: (abs(a[0] - n), a[0] > n))
        sem, repere = semestre(d0), f"séance {k} datée du {court(d0)} dans Moodle"
        liste = jours_de_cours(cal, jour, sem)
        if d0 not in liste:
            return None, (f"numéro sans date ; le repère (séance {k} du {court(d0)}) ne tombe pas un "
                          f"{JOURS_NOMS[jour]} de cours : horaire ou titre à vérifier")
    else:
        sem = semestre(aujourdhui)
        liste = jours_de_cours(cal, jour, sem)
        if not liste:
            return None, "numéro sans date, et début du semestre inconnu"
        k, d0 = 1, liste[0]
        repere = (f"AUCUNE séance datée dans ce cours : séance 1 supposée le {court(d0)}, "
                  f"premier {JOURS_NOMS[jour]} du semestre")
    i = liste.index(d0) + (n - k)
    if not 0 <= i < len(liste):
        return None, f"numéro sans date, hors du semestre d'après le repère (séance {k} du {court(d0)})"
    d = liste[i]
    sautes = sorted(x for x in cal["sans_cours"] if min(d0, d) < x < max(d0, d) and x.weekday() == jour)
    prec = f"date déduite du numéro : {repere}, un {JOURS_NOMS[jour]} de cours par séance"
    if sautes:
        prec += ", sans cours le " + ", ".join(court(x) for x in sautes)
    return d, prec


def controles(seances, suivis, cal, debut, fin):
    """Tests de coherence sur la periode [debut, fin]. Renvoie une liste de messages (points a verifier).

    `suivis` : {cid: (nom du cours, jour de l'horaire ou None)}. Chaque test vise une facon dont une
    seance peut manquer ou etre mal placee SANS que rien ne le signale :
      1. couverture : chaque jour de cours de l'horaire a une section (ou un "pas de cours") ;
      2. jour : une date lue tombe un autre jour que celui de l'horaire ;
      3. ordre : les numeros de seance et les dates ecrites progressent ensemble ;
      4. doublon : deux sections differentes pour la meme date du meme cours ;
      5. jour sans cours : une seance placee un jour annonce sans cours par un autre cours.
    """
    out = []
    par_cours = collections.defaultdict(list)
    for s in seances:
        if s.get("date"):
            par_cours[s["cid"]].append(s)
    semestres_vus = [b for b in cal["semestres"].values() if b[0] <= fin and b[1] >= debut]
    for cid, (nom, jour) in suivis.items():
        ss = par_cours.get(cid, [])
        dans = [s for s in ss if debut <= s["date"] <= fin]
        if jour is None:
            out.append(f"{nom} : pas de jour dans horaire.json, les séances manquantes ne peuvent pas être repérées.")
        else:
            manquants = []
            for a, b in semestres_vus:
                d = max(a, debut)
                d += dt.timedelta(days=(jour - d.weekday()) % 7)
                while d <= min(b, fin):
                    if d not in cal["sans_cours"] and not any(s["date"] == d for s in ss):
                        manquants.append(d)
                    d += dt.timedelta(days=7)
            if manquants:
                quand = (f"le {jour_long(manquants[0])}" if len(manquants) == 1 else
                         f"{len(manquants)} {JOURS_NOMS[jour]}s ({', '.join(court(d) for d in manquants)})")
                out.append(f"{nom} : aucune séance trouvée pour {quand}, jour(s) de cours d'après l'horaire. "
                           + ("Le cours n'a aucune section datée ou numérotée : ce qu'il faut préparer n'est pas "
                              "lisible dans Moodle." if not ss else
                              "Section pas encore publiée, ou titrée sans date ni numéro de séance."))
            for s in dans:
                if (s["date"].weekday() != jour and not s.get("sans_travail")
                        and (s.get("analyse") or {}).get("type") != "semaine"):
                    out.append(f"{nom} : « {s['titre'].strip()} » tombe un {JOURS_NOMS[s['date'].weekday()]}, "
                               f"l'horaire dit {JOURS_NOMS[jour]}. Séance déplacée, ou section qui n'est pas une séance ?")
        num = sorted((s["numero"], s["date"]) for s in ss if s.get("numero") and s.get("explicite"))
        for (k1, d1), (k2, d2) in zip(num, num[1:]):
            if k2 > k1 and d2 <= d1:
                out.append(f"{nom} : la séance {k2} ({court(d2)}) n'est pas après la séance {k1} ({court(d1)}). "
                           "Numéro ou date erroné dans Moodle, et les dates déduites de ce cours sont douteuses.")
        groupes = collections.defaultdict(list)
        for s in dans:
            if not s.get("sans_travail"):
                groupes[s["date"]].append(s)
        for d, g in groupes.items():
            if len(g) > 1 and len({s.get("numero") for s in g}) > 1:
                out.append(f"{nom} : {len(g)} sections pour le {jour_long(d)} ("
                           + " ; ".join(f"« {s['titre'].strip()[:50]} »" for s in g) + ").")
        for s in dans:
            if s["date"] in cal["sans_cours"] and not s.get("sans_travail"):
                out.append(f"{nom} : « {s['titre'].strip()} » est placée le {jour_long(s['date'])}, "
                           f"annoncé sans cours par {cal['sans_cours'][s['date']]}.")
    return out


def charger_horaire():
    try:
        with open(os.path.join(ms.APP_DIR, "horaire.json"), encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def lectures_de_section(s, statut_sous):
    """Fichiers d'une section : lecture (explicite ou deduite) ou support."""
    stats, biblio = ms.statuts_de_section(s, statut_sous)
    out = []
    for m in s.get("modules", []):
        if m.get("modname") not in ("resource", "folder"):
            continue
        for f in m.get("contents") or []:
            if f.get("type") != "file" or not f.get("filename"):
                continue
            nom = ms.nfc(f["filename"])
            st = stats.get(nom)
            if st:
                origine = "liste de lectures" if nom in biblio else "étiquette ou intitulé"
            else:
                st = ms.statut_deduit(m.get("name"), nom)
                origine = "déduit (support)" if st else "déduit"
                st = st or A_LIRE
            out.append({"nom": nom, "module": m.get("name"), "statut": st, "origine": origine,
                        "support": st == ms.T["S"], "url": f.get("fileurl"), "taille": f.get("filesize") or 0,
                        "pdf": nom.lower().endswith(".pdf")})
    return out


def pages_pdf(token, fichier, cache):
    """Nombre de pages d'un PDF (telecharge dans le dossier temporaire `cache`), ou None."""
    import pypdf
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    os.makedirs(cache, exist_ok=True)
    chemin = os.path.join(cache, hashlib.sha1(fichier["url"].encode()).hexdigest()[:16] + ".pdf")
    try:
        if not os.path.exists(chemin):
            ms.recuperer(fichier["url"], token, chemin + ".part")
            os.replace(chemin + ".part", chemin)
        return len(pypdf.PdfReader(chemin).pages)
    except Exception:
        return None


MOIS_NOMS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
             "novembre", "décembre"]
JOURS_NOMS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def fmt_duree(h):
    m = int(round(h * 60 / 5) * 5)
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


def jour_long(d):
    return f"{JOURS_NOMS[d.weekday()]} {d.day} {MOIS_NOMS[d.month - 1]}"


def id_lecture(cid, nom):
    return hashlib.sha1(f"{cid}|{nom}".encode("utf-8")).hexdigest()[:8]


def lire_ancien(chemin):
    """Cases cochees et temps reels deja saisis, et section Notes, d'un fichier precedent."""
    etat, notes, texte = {}, "", None
    try:
        with open(chemin, encoding="utf-8") as f:
            texte = f.read()
    except OSError:
        return etat, notes, texte
    for m in re.finditer(r"^- \[( |x|X)\] (.*?)<!-- id:(\w+) -->", texte, re.M):
        reel = re.search(r"r[ée]el\s*:\s*(\d+)", m.group(2))
        etat[m.group(3)] = (m.group(1).lower() == "x", int(reel.group(1)) if reel else None)
    i = texte.find("\n## Notes")
    if i >= 0:
        notes = texte[i + len("\n## Notes"):].strip()
    return etat, notes, texte


def rendre_md(fenetre, echeances, a_dater, sans_seance, aujourdhui, jours, etat, notes, avec_pages):
    """Texte Markdown de la semaine. Standard (cases a cocher), lisible dans tout editeur."""
    L = [ms.MARQUE, "", "# Ma semaine", "",
         f"Généré le {aujourdhui.day} {MOIS_NOMS[aujourdhui.month - 1]} {aujourdhui.year}, pour les {jours} prochains jours.",
         "", "## Comment lire ce fichier", "",
         "- **Obligatoire**, **Complémentaire** : écrit par l'enseignant dans Moodle.",
         "- *À lire (déduit)* : le programme suppose que c'est une lecture parce que c'est un fichier "
         "qui n'est pas une diapo, placé dans la séance. Ça peut être faux.",
         "- *date déduite* : l'année ou le jour n'est pas écrit dans le titre de la section.",
         f"- Durées : pages divisées par une cadence de {CADENCE_RAPIDE} à {CADENCE_LENTE} pages par heure. "
         "C'est une hypothèse non validée : note ton temps réel pour la corriger.",
         "- Pour noter ton temps, ajoute `réel : 70` (en minutes) sur la ligne de la lecture. "
         "Les cases cochées et ce temps sont conservés quand le fichier est regénéré. "
         "La section « Notes » en bas aussi ; tout le reste est réécrit.", ""]
    semaines = collections.OrderedDict()
    for s in fenetre:
        semaines.setdefault(s["date"] - dt.timedelta(days=s["date"].weekday()), []).append(s)
    if not semaines:
        L += ["Aucune séance datée dans cette période.", ""]
    for debut, seances in semaines.items():
        fin_sem = debut + dt.timedelta(days=6)
        tot = sum((f.get("pages") or 0) for s in seances for f in s["lectures"]
                  if f["statut"] not in (ms.T["C"], ms.T["P"]))
        titre = f"## Semaine du {debut.day} {MOIS_NOMS[debut.month - 1]} au {fin_sem.day} {MOIS_NOMS[fin_sem.month - 1]}"
        L += [titre, ""]
        if avec_pages and tot:
            L += [f"**Charge de lecture estimée : {tot} pages, soit {fmt_duree(tot / CADENCE_RAPIDE)} à "
                  f"{fmt_duree(tot / CADENCE_LENTE)}** (hors lectures facultatives).", ""]
        courant = None
        for s in seances:
            if s["date"] != courant:
                courant = s["date"]
                L += [f"### {jour_long(courant).capitalize()}", ""]
            heure = (s["heure"].lstrip("0").replace(":", " h ") + " · ") if s["heure"] else ""
            L.append(f"**{heure}{s['cours']}** · {s['titre'].strip()} · *{s['precision']}*")
            L.append("")
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
                duree = f" ({p} p., {fmt_duree(p / CADENCE_RAPIDE)} à {fmt_duree(p / CADENCE_LENTE)})" if p else ""
                if f["origine"] == "déduit":
                    etiq = "*À lire (déduit)*"
                else:
                    etiq = f"**{f['statut']}**" + ("" if f["statut"] == ms.T["O"] else " (facultatif)")
                vus[f["nom"]] += 1
                ident = id_lecture(s["cid"], f["nom"] + (f"#{vus[f['nom']]}" if vus[f["nom"]] > 1 else ""))
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
    par_cours = collections.Counter(s["cours"] for s in a_dater)
    for k, v in par_cours.items():
        L.append(f"- {k} : {v} séance(s) numérotée(s) sans date lisible.")
    for k in sans_seance:
        L.append(f"- {k} : aucune séance datée dans les titres de sections.")
    L += ["", "## Notes", "", notes or ""]
    return "\n".join(L).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jours", type=int, default=14)
    ap.add_argument("--sans-pages", action="store_true",
                    help="ne telecharge pas les PDF (sinon : dossier temporaire, pour compter les pages)")
    ap.add_argument("--cache", default=os.path.join(ms.APP_DIR, "prototype_cache"))
    ap.add_argument("--md", default=None, help="fichier de sortie (defaut : <dossier de rangement>/Ma semaine.md)")
    ap.add_argument("--console", action="store_true", help="affiche aussi le detail dans la console")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    a.pages = not a.sans_pages
    sys.stdout.reconfigure(encoding="utf-8")

    cfg = ms.charger_config()
    ms.appliquer_config(cfg)
    tok = cfg["token"]
    if not tok:
        sys.exit("Pas de jeton : lance d'abord MoodleSync et connecte-toi.")
    aujourdhui = dt.date.today()
    y0 = aujourdhui.year if aujourdhui.month >= 8 else aujourdhui.year - 1
    fin = aujourdhui + dt.timedelta(days=a.jours)
    horaires = charger_horaire()
    info = ms.infos_session(tok)
    cours = ms.cours_inscrits(tok, info["userid"])

    seances, a_dater, sans_seance = [], [], []
    for c in cours:
        cid = str(c["id"])
        h = horaires.get(cid, {})
        if h.get("suivi") is False:
            continue
        nom_cours = h.get("titre") or c["fullname"]
        sections = ms.api(tok, "core_course_get_contents", courseid=c["id"])
        parents = ms.sous_sections(sections)
        par_id = {s.get("id"): s for s in sections}
        corps = {}                     # id de section -> lectures a rattacher
        titres_speciaux = {}
        for s in sections:
            parent = parents.get(s.get("id"))
            statut_sous = ms.statut_titre(s.get("name")) if parent else None
            cible = parent if (parent and statut_sous) else s
            corps.setdefault(cible.get("id"), []).extend(lectures_de_section(s, statut_sous))
        n_dates = 0
        for s in sections:
            titre = s.get("name") or ""
            if parents.get(s.get("id")) and ms.statut_titre(titre):
                continue                                    # sous-section de statut : rattachee a sa seance
            an = analyser_titre(titre, y0)
            numerotee = bool(RE_NUMEROTEE.search(titre))
            if not an and not numerotee:
                continue
            fichiers = corps.get(s.get("id"), [])
            lect = [f for f in fichiers if not f["support"]]
            seance = {"cours": nom_cours, "cid": c["id"], "titre": titre, "section": s.get("id"),
                      "lectures": lect, "supports": [f for f in fichiers if f["support"]],
                      "sans_travail": bool(RE_SANS_TRAVAIL.search(titre)),
                      "sans_lecture": bool(RE_SANS_LECTURE.search(titre)),
                      "optionnel": bool(RE_OPTIONNEL.search(titre)),
                      "ouverture": re.sub(r"<[^>]+>", "", html.unescape(s.get("availabilityinfo") or "")).strip() or None}
            d, prec = dater(an, h)
            if d:
                n_dates += 1
                heure = h.get("heure")
                seance["date"], seance["precision"] = d, prec
                seance["heure"] = heure
                seances.append(seance)
            else:
                seance["date"], seance["precision"] = None, prec
                a_dater.append(seance)
        if n_dates == 0:
            sans_seance.append(nom_cours)

    # ---------------------------------------------------------------- echeances (API, lecture seule)
    import time
    ev = ms.api(tok, "core_calendar_get_action_events_by_timesort",
                timesortfrom=int(time.time()) - 7 * 86400, limitnum=50).get("events", [])
    suivis = {str(c["id"]) for c in cours if horaires.get(str(c["id"]), {}).get("suivi") is not False}
    echeances = []
    for e in ev:
        if str(e["course"]["id"]) in suivis:
            echeances.append({"date": dt.datetime.fromtimestamp(e["timestart"]), "cours": html.unescape(e["course"]["fullname"]),
                              "nom": html.unescape(e["name"]), "type": f'{e.get("modulename")}/{e.get("eventtype")}',
                              "en_retard": bool(e.get("overdue"))})
    echeances.sort(key=lambda x: x["date"])

    # ---------------------------------------------------------------- pages et affichage
    fenetre = sorted((s for s in seances if aujourdhui <= s["date"] <= fin), key=lambda s: (s["date"], s["heure"] or ""))
    if a.pages:
        for s in fenetre:
            for f in s["lectures"]:
                f["pages"] = pages_pdf(tok, f, a.cache) if f["pdf"] else None

    import io
    sortie_reelle = sys.stdout
    if not a.console:
        sys.stdout = io.StringIO()                     # le detail ne s'affiche que si demande
    print(f"Prototype séances | {aujourdhui:%d.%m.%Y} | fenêtre : {a.jours} jours | année académique {y0}-{y0 + 1}")
    print(f"Cadence de lecture (hypothèse non validée) : {CADENCE_LENTE} à {CADENCE_RAPIDE} pages/heure\n")
    if not fenetre:
        print("Aucune séance datée dans la fenêtre.")
    for s in fenetre:
        quand = f"{JOURS[s['date'].weekday()].capitalize()} {s['date']:%d.%m}" + (f" {s['heure']}" if s["heure"] else "")
        flags = [x for x, v in (("PAS DE COURS", s["sans_travail"]), ("PAS DE LECTURE", s["sans_lecture"]),
                                ("OPTIONNEL", s["optionnel"])) if v]
        print(f"== {quand} | {s['cours']}")
        print(f"   section : {s['titre'].strip()}  [date : {s['precision']}]" + (f"  [{', '.join(flags)}]" if flags else ""))
        if s["ouverture"]:
            print(f"   ouverture : {s['ouverture']}")
        tot = 0
        for f in s["lectures"]:
            p = f.get("pages")
            if f["statut"] not in (ms.T["C"], ms.T["P"]):     # complémentaire et plus loin : facultatifs, non comptés
                tot += p or 0
            etiq = "déduit" if f["origine"] == "déduit" else f"explicite : {f['statut']} ({f['origine']})"
            print(f"   - [{etiq}] {f['nom']}" + (f"  ({p} p.)" if p else ""))
        if s["supports"]:
            print(f"   supports : {len(s['supports'])} (non comptés dans la lecture)")
        if not s["lectures"]:
            print("   (aucune lecture identifiée)")
        if a.pages and tot:
            print(f"   total à lire (hors complémentaire) : {tot} p. -> environ {tot / CADENCE_RAPIDE:.1f} à {tot / CADENCE_LENTE:.1f} h")
        print()

    print("== Échéances (API de calendrier)")
    for e in echeances:
        if e["date"].date() <= aujourdhui + dt.timedelta(days=90):
            print(f"   {e['date']:%d.%m.%Y %H:%M} | {e['cours'][:34]} | {e['nom'][:70]} [{e['type']}]"
                  + (" EN RETARD" if e["en_retard"] else ""))
    print("\n== À dater à la main (séances numérotées ou sans date lisible)")
    par_cours = collections.Counter(s["cours"] for s in a_dater)
    for k, v in par_cours.items():
        print(f"   {k} : {v} séance(s)")
    for k in sans_seance:
        print(f"   {k} : aucune séance datée")

    # ---------------------------------------------------------------- mesure sur tout le semestre
    print("\n== Mesure sur toutes les séances datées du semestre")
    tous = [f for s in seances for f in s["lectures"]]
    c = collections.Counter("explicite" if f["origine"] != "déduit" else "déduit" for f in tous)
    print(f"   séances datées : {len(seances)} | lectures : {len(tous)} (explicites {c['explicite']}, déduites {c['déduit']})")
    par = collections.defaultdict(lambda: [0, 0])
    for s in seances:
        for f in s["lectures"]:
            par[s["cours"]][0 if f["origine"] != "déduit" else 1] += 1
    for k, (e, d) in par.items():
        print(f"   {k[:60]:<60} explicites {e:>3} | déduites {d:>3}")
    sys.stdout = sortie_reelle

    # ---------------------------------------------------------------- fichier Markdown
    chemin = a.md or os.path.join(cfg["dest"], "Ma semaine.md")
    etat, notes, ancien = lire_ancien(chemin)
    if ancien is not None and ms.MARQUE not in ancien:
        sys.exit(f"Le fichier existe et ne porte pas la marque de MoodleSync, je n'y touche pas : {chemin}")
    os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
    texte = rendre_md(fenetre, echeances, a_dater, sans_seance, aujourdhui, a.jours, etat, notes, a.pages)
    with open(chemin + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texte)
    os.replace(chemin + ".tmp", chemin)
    print(f"Écrit : {chemin}")
    if a.json:
        def enc(o):
            return o.isoformat() if isinstance(o, (dt.date, dt.datetime)) else str(o)
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"seances": seances, "a_dater": a_dater, "echeances": echeances}, fh, default=enc,
                      ensure_ascii=False, indent=1)


if __name__ == "__main__":
    # Ce fichier est surtout le moteur de lecture (titres, statuts, pages) utilise par ma_semaine.py.
    # Lance directement, il fait la meme chose que : python prototypes/ma_semaine.py --creer
    # (l'ancienne sortie en ligne de commande, avec ses constantes de cadence, n'est plus utilisee).
    import ma_semaine
    if "--creer" not in sys.argv:
        sys.argv.insert(1, "--creer")
    ma_semaine.main()
