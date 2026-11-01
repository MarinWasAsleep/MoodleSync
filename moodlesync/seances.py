"""Moteur de Ma semaine : seances, lectures et controles a partir des cours Moodle (LECTURE SEULE).

Fonctions pures (testees hors ligne dans test_seances.py) : dater une seance d'apres le titre de sa
section ou son numero, classer ses lectures (statut ecrit par l'enseignant, consigne, ou "deduit"),
construire le calendrier des jours sans cours, controler la coherence du resultat. Ce fichier ne
modifie ni Moodle, ni le dossier de rangement. Collecte et rendu : semaine.py.

Tout marche sans reglage : le jour de chaque cours est deduit de ses dates dans Moodle quand il est
net. Fichier facultatif `horaire.json` dans le dossier des reglages de MoodleSync (jamais publie) :
  {"37540": {"jour": 2, "heure": "10:15", "titre": "Intro. science politique (seminaire)"},
   "38184": {"suivi": false},
   "38245": {"jour": 1, "controle": false},
   "calendrier": {"semestres": [["2026-09-14", "2026-12-18"]], "sans_cours": ["2026-09-21"]}}
`jour` : 0 = lundi ... 6 = dimanche. `suivi: false` : cours ignore. `controle: false` : cours affiche
mais pas controle (par exemple un cours sans seances ni lectures). `calendrier` : corrige les bornes du
semestre et les jours sans cours lus dans Moodle.
"""
import sys, os, re, json, html, datetime as dt, collections, hashlib, logging

from . import moteur as ms

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


def dater(analyse, horaire, source="l'horaire"):
    """(date, precision) de la seance, ou (None, raison). `source` : d'ou vient le jour du cours."""
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
        return d, "; ".join(notes + [f"jour déduit de {source}"])
    if analyse["type"] == "alternatives":
        if jour is not None:
            for d in ds:
                if d.weekday() == jour:
                    return d, "; ".join(notes + [f"choisie parmi {len(ds)} dates d'après {source}"])
        return ds[0], "; ".join(notes + [f"{len(ds)} dates possibles, la première prise"])
    d = ds[0]
    if jour is not None and d.weekday() != jour:
        notes.append(f"jour ({JOURS[d.weekday()]}) différent de {source} ({JOURS[jour]})")
    return d, "; ".join(notes) or "lue"


def nom_affiche(nom_complet):
    """Nom lisible d'un cours : sans l'annee academique ni le prefixe technique COURS_ ou SEM_.

    "COURS_Introduction a la recherche (2026-2027)" -> "Introduction a la recherche (cours)".
    """
    nom = ms.RE_ANNEE.sub("", html.unescape(nom_complet or "")).strip()
    m = re.match(r"(?i)^(cours|sem|lecture|seminar)_\s*", nom)
    if m:
        nom = nom[m.end():]
        genre = "cours" if m.group(1).lower() in ("cours", "lecture") else "séminaire"
        if not re.search(r"(?i)\b(cours|s[ée]minaire|seminar|lecture)\b", nom):
            nom = f"{nom} ({genre})"
    return re.sub(r"\s{2,}", " ", nom).strip(" -") or nom_complet


def jour_habituel(dates):
    """Jour de la semaine du cours, deduit de ses dates ecrites dans Moodle, s'il est net.

    Il faut au moins 3 dates, dont 70 % le meme jour : sert quand horaire.json ne donne pas le jour
    (cas de la plupart des utilisateurs). Sinon None : mieux vaut ne rien controler que mal controler.
    """
    c = collections.Counter(d.weekday() for d in dates)
    if sum(c.values()) < 3:
        return None
    jour, n = c.most_common(1)[0]
    return jour if n / sum(c.values()) >= 0.7 else None


# ------------------------------------------------------------------ consignes ecrites par l'enseignant
# Nom et description d'un fichier ou d'un lien, resume d'une section. Toutes les langues a la fois :
# un enseignant peut ecrire en anglais dans un Moodle regle en francais. La premiere expression
# trouvee l'emporte ("Lecture facultative, mais... lire l'introduction" : facultative).
RE_FACULTATIF = re.compile(
    r"non[- ]obligatoires?|pas obligatoires?|non exig[ée]e?s?|facultati(?:f|ve)s?|optionnel(?:le)?s?"
    r"|(?:lectures?|textes?|documents?|ressources?)\s+compl[ée]mentaires?|recommand[ée]e?s?"
    r"|pour aller plus loin|\bnot (?:required|mandatory)|\boptional\b|\bsupplementary\b|further reading"
    r"|\brecommended\b", re.I)
RE_A_LIRE = re.compile(
    r"\b(?:textes?|lectures?|extraits?|chapitres?|articles?)\s+[àa]\s+lire\b|[àa]\s+lire\s+(?:pour|avant|d['’]ici)"
    r"|\blire\s+(?:uniquement|seulement|d['’]abord|en priorit|prioritairement|pour|avant)"
    r"|\bobligatoires?\b|[àa]\s+pr[ée]parer\b"
    r"|\b(?:required|mandatory|compulsory|essential)\b|\bread\s+(?:for|before|only|first)\b|\bto read\b"
    r"|\bto prepare\b", re.I)
RE_PLUS_LOIN = re.compile(r"aller plus loin|further", re.I)
RE_VIDEO = re.compile(r"vid[ée]o|youtube|vimeo|podcast|[ée]couter|regarder|watch|listen", re.I)
RE_PAGES = re.compile(r"\b(?:pp?\.|pages?)\s*(\d{1,4})\s*(?:-|[" + TIRETS + r"]|à|to)\s*(\d{1,4})\b", re.I)
RE_PREPARER = re.compile(r"\blire\b|\blisez\b|pr[ée]par|\bread\b|\bprepare\b", re.I)
PAGES_LONG = 60     # au-dela, un PDF sans pages precisees est sans doute a lire en partie


def phrase(texte, pos, n=140):
    """Phrase de `texte` qui contient la position `pos`, raccourcie a `n` caracteres."""
    debut = max(texte.rfind(". ", 0, pos), texte.rfind("? ", 0, pos), texte.rfind("! ", 0, pos))
    debut = debut + 2 if debut >= 0 else 0
    fin = min([i for i in (texte.find(". ", pos), texte.find("? ", pos), texte.find("! ", pos)) if i >= 0]
              or [len(texte)])
    p = texte[debut:fin + 1].strip()
    return p if len(p) <= n else p[:n - 3].rstrip() + "..."


def consigne(texte):
    """(statut, extrait) d'apres une consigne ecrite (nom ou description d'un fichier), sinon (None, None).

    Le statut n'est pas devine : il recopie ce que dit la phrase, et l'extrait est montre a l'utilisateur.
    """
    t = " ".join((texte or "").split())
    trouves = [m for m in (RE_FACULTATIF.search(t), RE_A_LIRE.search(t)) if m]
    if not trouves:
        return None, None
    m = min(trouves, key=lambda x: x.start())
    if m.re is RE_A_LIRE:
        statut = ms.T["O"]
    else:
        statut = ms.T["P"] if RE_PLUS_LOIN.search(m.group(0)) else ms.T["C"]
    return statut, phrase(t, m.start())


def pages_consigne(texte):
    """(nombre de pages, [(debut, fin)]) des plages "pp. 225-255" d'une consigne, ou (None, [])."""
    plages = []
    for a, b in RE_PAGES.findall(" ".join((texte or "").split())):
        a, b = int(a), int(b)
        if a <= b <= a + 500 and (a, b) not in plages:
            plages.append((a, b))
    return (sum(b - a + 1 for a, b in plages), plages) if plages else (None, [])


def consigne_section(resume):
    """Phrases du resume d'une section qui demandent de lire ou de preparer quelque chose (2 au plus)."""
    out = []
    for ligne in ms.lignes_html(resume or ""):
        for p in re.split(r"(?<=[.!?])\s+", ligne):
            if RE_PREPARER.search(p) and 15 <= len(p) and len(out) < 2:
                out.append(p if len(p) <= 200 else p[:197].rstrip() + "...")
    return out


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


def jours_de_cours(cal, jour, sem, reelles=None):
    """Dates du semestre `sem` tombant le jour `jour` (0 = lundi), jours sans cours retires.

    `reelles` : dates des seances lues dans l'horaire .ics de l'etudiant. Entre la premiere et la derniere,
    elles remplacent les dates calculees (une semaine absente du .ics est une semaine sans cours) ;
    en dehors, le calcul d'apres le jour reste. Sans jour connu, seules les dates reelles comptent.
    Un jour annonce sans cours dans Moodle l'emporte sur le .ics (un horaire officiel liste souvent
    les seances de la semaine de lecture ou d'un ferie).
    """
    reelles = sorted(r for r in (reelles or []) if semestre(r) == sem and r not in cal["sans_cours"])
    out = []
    if jour is not None and sem in cal["semestres"]:
        a, b = cal["semestres"][sem]
        d = a + dt.timedelta(days=(jour - a.weekday()) % 7)
        while d <= b:
            if d not in cal["sans_cours"] and not (reelles and reelles[0] <= d <= reelles[-1]):
                out.append(d)
            d += dt.timedelta(days=7)
    return sorted(set(out) | set(reelles))


def jours_attendus(cal, jour, a, b, debut, fin, reelles=None):
    """Jours de cours entre max(a, debut) et min(b, fin) : dates reelles du .ics sur la periode qu'il
    couvre, un `jour` par semaine ailleurs (les jours sans cours sont filtres par l'appelant)."""
    reelles = sorted(reelles or [])
    out = []
    if jour is not None:
        d = max(a, debut)
        d += dt.timedelta(days=(jour - d.weekday()) % 7)
        while d <= min(b, fin):
            if not (reelles and reelles[0] <= d <= reelles[-1]):
                out.append(d)
            d += dt.timedelta(days=7)
    out += [r for r in reelles if max(a, debut) <= r <= min(b, fin)]
    return sorted(set(out))


def dater_par_numero(n, ancres, cal, jour, aujourdhui, reelles=None):
    """(date, precision) d'une seance numerotee sans date, ou (None, raison).

    `ancres` : [(numero, date)] lues dans les titres du MEME cours. La seance n est placee n - k jours
    de cours apres l'ancre k la plus proche, sur le jour de l'horaire, en sautant les jours sans cours.
    Le calcul reste dans le semestre de l'ancre (les vacances d'un autre semestre ne sont pas connues).
    `reelles` : dates des seances de ce cours lues dans l'horaire .ics (voir jours_de_cours).
    """
    reelles = sorted(reelles or [])
    if jour is None and not reelles:
        return None, "numéro sans date, et pas de jour pour ce cours (ni horaire .ics, ni horaire.json)"
    nom_jour = JOURS_NOMS[jour] if jour is not None else "jour"
    if ancres:
        k, d0 = min(ancres, key=lambda a: (abs(a[0] - n), a[0] > n))
        sem, repere = semestre(d0), f"séance {k} datée du {court(d0)} dans Moodle"
        liste = jours_de_cours(cal, jour, sem, reelles)
        if d0 not in liste:
            return None, (f"numéro sans date ; le repère (séance {k} du {court(d0)}) ne tombe pas un "
                          f"{nom_jour} de cours : horaire ou titre à vérifier")
    else:
        sem = semestre(aujourdhui)
        liste = jours_de_cours(cal, jour, sem, reelles)
        if not liste:
            return None, "numéro sans date, et début du semestre inconnu"
        k, d0 = 1, liste[0]
        repere = (f"AUCUNE séance datée dans ce cours : séance 1 supposée le {court(d0)}, "
                  f"premier {nom_jour} de cours connu")
    i = liste.index(d0) + (n - k)
    if not 0 <= i < len(liste):
        return None, f"numéro sans date, hors du semestre d'après le repère (séance {k} du {court(d0)})"
    d = liste[i]
    sautes = sorted(x for x in cal["sans_cours"] if min(d0, d) < x < max(d0, d) and x.weekday() == jour)
    if d in reelles:
        prec = f"date déduite du numéro : {repere}, puis les séances de ton horaire (.ics)"
        sautes = [x for x in sautes if not reelles[0] <= x <= reelles[-1]]
    else:
        prec = f"date déduite du numéro : {repere}, un {nom_jour} de cours par séance"
    if sautes:
        prec += ", sans cours le " + ", ".join(court(x) for x in sautes)
    return d, prec


def suivi(v):
    """Description d'un cours suivi : {nom, jour, source, controle}. Accepte aussi (nom, jour)."""
    if isinstance(v, dict):
        return {"source": "l'horaire", "controle": True, **v}
    return {"nom": v[0], "jour": v[1], "source": "l'horaire", "controle": True}


def controles(seances, suivis, cal, debut, fin):
    """Tests de coherence sur la periode [debut, fin]. Renvoie une liste de messages (points a verifier).

    `suivis` : {cid: {nom, jour, source, controle}} (voir suivi()). Chaque test vise une facon dont une
    seance ou une lecture peut manquer SANS que rien ne le signale :
      1. couverture : chaque jour de cours a une section (ou un "pas de cours") ;
      2. jour : une date lue tombe un autre jour que le jour du cours ;
      3. ordre : les numeros de seance et les dates ecrites progressent ensemble ;
      4. doublon : deux sections differentes pour la meme date du meme cours ;
      5. jour sans cours : une seance placee un jour annonce sans cours par un autre cours.
    Ce qui n'est pas encore depose (lectures, contenu verrouille) releve de surveillances(), pas d'ici.
    Un cours regle "controle": false dans horaire.json n'est pas controle (il est cite a part).
    """
    out, sans_jour = [], []
    par_cours = collections.defaultdict(list)
    for s in seances:
        if s.get("date"):
            par_cours[s["cid"]].append(s)
    semestres_vus = [b for b in cal["semestres"].values() if b[0] <= fin and b[1] >= debut]
    for cid, v in suivis.items():
        v = suivi(v)
        if not v["controle"]:
            continue
        nom, jour, source = v["nom"], v["jour"], v["source"]
        ss = par_cours.get(cid, [])
        dans = [s for s in ss if debut <= s["date"] <= fin]
        reelles = sorted(dt.date.fromisoformat(x) if isinstance(x, str) else x for x in v.get("dates") or [])
        if jour is None and not reelles:
            sans_jour.append(nom)
        else:
            manquants = []
            for a, b in semestres_vus:
                # Jours attendus : ceux de l'horaire .ics sur la periode qu'il couvre, sinon un par semaine.
                for d in jours_attendus(cal, jour, a, b, debut, fin, reelles):
                    if d not in cal["sans_cours"] and not any(s["date"] == d for s in ss):
                        manquants.append(d)
            if manquants:
                quand = (f"le {jour_long(manquants[0])}" if len(manquants) == 1 else
                         f"{len(manquants)} {JOURS_NOMS[jour] + 's' if jour is not None else 'jours'} "
                         f"({', '.join(court(d) for d in manquants)})")
                out.append(f"{nom} : aucune séance trouvée pour {quand}, jour(s) de cours d'après {source}. "
                           + ("Le cours n'a aucune section datée ou numérotée : ce qu'il faut préparer n'est pas "
                              "lisible dans Moodle." if not ss else
                              "Section pas encore publiée, ou titrée sans date ni numéro de séance."))
            for s in dans:
                if jour is None or s["date"] in reelles:
                    continue                            # seance placee un jour de l'horaire .ics : normal
                if (s["date"].weekday() != jour and not s.get("sans_travail")
                        and (s.get("analyse") or {}).get("type") != "semaine"):
                    out.append(f"{nom} : « {s['titre'].strip()} » tombe un {JOURS_NOMS[s['date'].weekday()]}, "
                               f"alors que le cours a lieu le {JOURS_NOMS[jour]} (d'après {source}). "
                               "Séance déplacée, ou section qui n'est pas une séance ?")
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
    if sans_jour:
        out.append("Jour de cours inconnu (ni horaire .ics ou horaire.json, ni dates régulières dans Moodle) pour : "
                   + ", ".join(sans_jour) + ". Les séances manquantes de ces cours ne sont pas repérées.")
    return out


def surveillances(seances, suivis, debut, fin):
    """Seances de [debut, fin] dont le contenu n'est probablement pas encore depose. Messages.

    Pas une erreur : un enseignant depose souvent les textes quelques jours avant. Deux cas :
      - contenu ferme : section verrouillee ou ouverte plus tard, sans contenu visible ;
      - habitude : seance sans lecture dans un cours dont au moins 60 % des 3 seances passees (ou plus)
        en avaient. Un cours qui ne donne pas de lectures ne declenche donc jamais ce message.
    Une seance qui ne tombe pas le jour du cours (deja signalee par controles()) est laissee de cote.
    """
    out = []
    for cid, v in suivis.items():
        v = suivi(v)
        if not v["controle"]:
            continue
        ss = [s for s in seances if s["cid"] == cid and s.get("date")]
        passees = [s for s in ss if s["date"] < debut and not s.get("sans_travail") and not s.get("sans_lecture")]
        avec = sum(1 for s in passees if s.get("lectures"))
        habitue = len(passees) >= 3 and avec / len(passees) >= 0.6
        for s in sorted(ss, key=lambda s: s["date"]):
            if not debut <= s["date"] <= fin:
                continue
            if s.get("sans_travail") or s.get("sans_lecture") or s.get("lectures"):
                continue
            if (v["jour"] is not None and s["date"].weekday() != v["jour"]
                    and (s.get("analyse") or {}).get("type") != "semaine"):
                continue
            if s.get("ouverture") and not s.get("nb_modules"):
                ouv = s["ouverture"] if len(s["ouverture"]) <= 120 else s["ouverture"][:117] + "..."
                out.append(f"{v['nom']}, {jour_long(s['date'])} (« {s['titre'].strip()} ») : contenu non visible "
                           f"pour toi (restriction Moodle : {ouv}). Il s'ouvrira à la date dite, ou il est réservé "
                           "à un groupe dont tu ne fais pas partie.")
            elif habitue:
                out.append(f"{v['nom']}, {jour_long(s['date'])} (« {s['titre'].strip()} ») : aucune lecture pour "
                           f"l'instant, alors que {avec} des {len(passees)} séances passées en avaient.")
    return out


def instantane(seances):
    """Etat des seances datees, a comparer avec la generation suivante (voir differences)."""
    return {f"{s['cid']}:{s['section']}": {"date": s["date"].isoformat(), "titre": s["titre"].strip(),
                                           "cours": s["cours"], "lectures": [f["nom"] for f in s.get("lectures", [])]}
            for s in seances if s.get("date") and s.get("section") is not None}


def differences(avant, apres, debut, fin):
    """Ce qui a change depuis la generation precedente, pour les seances de [debut, fin].

    Renvoie (messages, {(cle de seance, nom de lecture)} des lectures nouvelles).
    """
    msgs, nouvelles = [], set()

    def dans(e):
        return e is not None and debut <= dt.date.fromisoformat(e["date"]) <= fin

    for k, n in apres.items():
        a = avant.get(k)
        if not (dans(n) or dans(a)):
            continue
        d = dt.date.fromisoformat(n["date"])
        if a is None:
            msgs.append(f"{n['cours']} : nouvelle séance publiée pour le {jour_long(d)} (« {n['titre']} »).")
            continue
        if a["date"] != n["date"]:
            msgs.append(f"{n['cours']} : « {n['titre']} » a changé de date : "
                        f"{jour_long(dt.date.fromisoformat(a['date']))} avant, {jour_long(d)} maintenant.")
        for lec in n["lectures"]:
            if lec not in a["lectures"]:
                nouvelles.add((k, lec))
                msgs.append(f"{n['cours']} : lecture ajoutée pour le {jour_long(d)} : {lec}.")
        for lec in a["lectures"]:
            if lec not in n["lectures"]:
                msgs.append(f"{n['cours']} : lecture retirée de Moodle pour le {jour_long(d)} : {lec}.")
    for k, a in avant.items():
        if k not in apres and dans(a):
            msgs.append(f"{a['cours']} : la séance « {a['titre']} » du "
                        f"{jour_long(dt.date.fromisoformat(a['date']))} n'est plus trouvée "
                        "(section supprimée, masquée, ou renommée sans date).")
    return msgs, nouvelles


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
        mod, nom_mod = m.get("modname"), ms.nfc(m.get("name") or "")
        desc = " ".join(ms.lignes_html(m.get("description") or ""))
        st_cons, extrait = consigne(f"{nom_mod}. {desc}")
        if mod == "url":
            # Un lien n'est une lecture que si sa consigne le dit, et jamais une video ou un son.
            url = next((c.get("fileurl") for c in m.get("contents") or [] if c.get("fileurl")), m.get("url"))
            if st_cons and not RE_VIDEO.search(f"{nom_mod} {desc} {url or ''}"):
                n, plages = pages_consigne(f"{nom_mod} {desc}")
                out.append({"nom": nom_mod, "module": nom_mod, "statut": st_cons, "origine": "consigne",
                            "extrait": extrait, "support": False, "url": url, "taille": 0, "pdf": False,
                            "lien": True, "pages_consigne": n, "plages": plages})
            continue
        if mod not in ("resource", "folder"):
            continue
        fichiers = [f for f in m.get("contents") or [] if f.get("type") == "file" and f.get("filename")]
        for f in fichiers:
            nom = ms.nfc(f["filename"])
            st, ext = stats.get(nom), None
            if st:
                origine = "liste de lectures" if nom in biblio else "étiquette ou intitulé"
            elif ms.statut_deduit(nom_mod, nom):
                st, origine = ms.T["S"], "déduit (support)"
            elif st_cons:
                st, origine, ext = st_cons, "consigne", extrait
            else:
                st, origine = A_LIRE, "déduit"
            # Les pages d'une consigne ne valent que pour un fichier seul dans son module.
            n, plages = pages_consigne(f"{nom_mod} {desc}") if len(fichiers) == 1 else (None, [])
            out.append({"nom": nom, "module": nom_mod, "statut": st, "origine": origine, "extrait": ext,
                        "support": st == ms.T["S"], "url": f.get("fileurl"), "taille": f.get("filesize") or 0,
                        "pdf": nom.lower().endswith(".pdf"), "lien": False, "pages_consigne": n, "plages": plages})
    return out


def pages_a_lire(f):
    """Pages a compter pour une lecture : celles de la consigne si elle en donne, sinon le PDF entier."""
    return f.get("pages_consigne") or f.get("pages")


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

