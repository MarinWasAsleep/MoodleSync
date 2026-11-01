"""Lecture d'un calendrier .ics (RFC 5545), sans dependance. Sert a l'horaire de Ma semaine (horaire.py).

Ce qui est lu : les evenements (VEVENT) avec leur intitule, leur debut, leur fin et leur lieu ; le pliage
des lignes, les echappements, les heures avec TZID (lues telles qu'ecrites : heure murale, sans base de
fuseaux), les heures UTC (suffixe Z, converties en heure locale de l'ordinateur), les repetitions
hebdomadaires (RRULE FREQ=WEEKLY avec UNTIL, COUNT, INTERVAL, BYDAY, WKST), les exceptions (EXDATE),
les dates ajoutees (RDATE simples), les occurrences modifiees ou annulees (RECURRENCE-ID).

Ce qui n'est pas lu est SIGNALE, jamais devine : toute autre regle de repetition (quotidienne, mensuelle,
BYSETPOS...) ne donne que sa premiere date, avec un avertissement. Les evenements d'une journee entiere
(vacances, feries, examens sans heure) sont ignores : ils ne decrivent pas un creneau de cours.
"""
import re, datetime as dt

from . import moteur as ms

TAILLE_MAX = 5_000_000            # un horaire de semestre pese quelques dizaines de Ko
OCCURRENCES_MAX = 1000            # par evenement repete
DUREE_SANS_FIN = 2 * 366          # jours : une repetition sans fin est lue sur deux ans au plus
JOURS_ICS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


class ErreurICS(ms.Erreur):
    pass


# ------------------------------------------------------------------ lignes et proprietes
def deplier(texte):
    """Lignes logiques : retire le BOM, unifie les fins de ligne, recolle les lignes pliees."""
    texte = texte.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    lignes = []
    for l in texte.split("\n"):
        if l[:1] in (" ", "\t") and lignes:
            lignes[-1] += l[1:]
        elif l.strip():
            lignes.append(l)
    return lignes


def propriete(ligne):
    """(NOM, {PARAM: valeur}, valeur) d'une ligne "NOM;PARAM=x:valeur". Les deux-points entre
    guillemets (dans un parametre) ne coupent pas."""
    dans_guillemets, coupe = False, None
    for i, c in enumerate(ligne):
        if c == '"':
            dans_guillemets = not dans_guillemets
        elif c == ":" and not dans_guillemets:
            coupe = i
            break
    if coupe is None:
        return ligne.upper(), {}, ""
    tete, valeur = ligne[:coupe], ligne[coupe + 1:]
    morceaux = tete.split(";")
    params = {}
    for p in morceaux[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v.strip('"')
    return morceaux[0].upper(), params, valeur


def texte_ics(valeur):
    """Valeur de type TEXT sans ses echappements (\\n, \\, \\; \\\\)."""
    out, i = [], 0
    while i < len(valeur):
        c = valeur[i]
        if c == "\\" and i + 1 < len(valeur):
            n = valeur[i + 1]
            out.append("\n" if n in "nN" else n)
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out).strip()


# ------------------------------------------------------------------ dates
def date_ics(valeur, params=None):
    """datetime naif (heure locale ou murale) ou date (journee entiere). Leve ValueError si illisible."""
    params = params or {}
    v = valeur.strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", v):
        return dt.datetime.strptime(v[:8], "%Y%m%d").date()
    m = re.fullmatch(r"(\d{8})T(\d{4})(\d{2})?(Z?)", v)
    if not m:
        raise ValueError(f"date illisible : {v}")
    d = dt.datetime.strptime(m.group(1) + m.group(2) + (m.group(3) or "00"), "%Y%m%d%H%M%S")
    if m.group(4):
        d = d.replace(tzinfo=dt.timezone.utc).astimezone().replace(tzinfo=None)
    return d


def liste_dates(valeur, params):
    return [date_ics(x, params) for x in valeur.split(",") if x.strip()]


RE_DUREE = re.compile(r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def duree_ics(valeur):
    m = RE_DUREE.match(valeur.strip())
    if not m:
        raise ValueError(f"durée illisible : {valeur}")
    s, w, d, h, mi, se = m.groups()
    t = dt.timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0),
                     seconds=int(se or 0))
    return -t if s == "-" else t


# ------------------------------------------------------------------ repetitions
def regle(valeur):
    return {k.upper(): v for k, _, v in (p.partition("=") for p in valeur.split(";") if p)}


def occurrences_hebdo(debut, r):
    """Debuts des occurrences d'une regle FREQ=WEEKLY (deja verifiee lisible), DTSTART compris."""
    intervalle = int(r.get("INTERVAL", "1") or 1)
    wkst = JOURS_ICS.index(r.get("WKST", "MO").upper())
    jours = sorted({JOURS_ICS.index(j.upper()) for j in r["BYDAY"].split(",")} if r.get("BYDAY")
                   else {debut.weekday()}, key=lambda j: (j - wkst) % 7)
    compte = int(r["COUNT"]) if r.get("COUNT") else None
    jusqu = None
    if r.get("UNTIL"):
        u = date_ics(r["UNTIL"])
        jusqu = u if isinstance(u, dt.datetime) else dt.datetime.combine(u, dt.time(23, 59, 59))
    limite = debut + dt.timedelta(days=DUREE_SANS_FIN)
    jour0 = debut.date() if isinstance(debut, dt.datetime) else debut
    semaine0 = jour0 - dt.timedelta(days=(jour0.weekday() - wkst) % 7)
    out, n = [], 0
    while len(out) < OCCURRENCES_MAX:
        lundi_ = semaine0 + dt.timedelta(weeks=n * intervalle)
        for j in jours:
            jour = lundi_ + dt.timedelta(days=(j - wkst) % 7)
            occ = dt.datetime.combine(jour, debut.time()) if isinstance(debut, dt.datetime) else jour
            if occ < debut:
                continue
            if (jusqu and occ > jusqu) or occ > limite or (compte is not None and len(out) >= compte):
                return out
            out.append(occ)
        n += 1
    return out


def regle_non_lue(r):
    """Raison pour laquelle une regle n'est pas lue, ou None si FREQ=WEEKLY simple."""
    if r.get("FREQ", "").upper() != "WEEKLY":
        return f"répétition « {r.get('FREQ', '?').lower()} »"
    autres = sorted(set(r) - {"FREQ", "INTERVAL", "BYDAY", "UNTIL", "COUNT", "WKST"})
    if autres:
        return "répétition hebdomadaire avec " + ", ".join(autres)
    if any(j.strip().upper() not in JOURS_ICS for j in r.get("BYDAY", "").split(",") if j.strip()):
        return f"jours de répétition « {r['BYDAY']} »"
    try:
        int(r.get("INTERVAL", "1") or 1), int(r.get("COUNT", "0") or 0)
        if r.get("UNTIL"):
            date_ics(r["UNTIL"])
    except ValueError:
        return "répétition illisible"
    return None


# ------------------------------------------------------------------ evenements
def evenements_bruts(lignes):
    """Liste de dictionnaires {NOM: [(params, valeur), ...]} pour chaque VEVENT (VALARM ignore)."""
    out, pile, courant = [], [], None
    for l in lignes:
        nom, params, valeur = propriete(l)
        if nom == "BEGIN":
            pile.append(valeur.upper())
            if valeur.upper() == "VEVENT" and pile.count("VEVENT") == 1:
                courant = {}
            continue
        if nom == "END":
            if pile and pile[-1] == valeur.upper():
                pile.pop()
            if valeur.upper() == "VEVENT" and courant is not None:
                out.append(courant)
                courant = None
            continue
        if courant is not None and pile and pile[-1] == "VEVENT":
            courant.setdefault(nom, []).append((params, valeur))
    return out


def un(ev, nom):
    return ev[nom][0] if ev.get(nom) else ({}, "")


def lire(texte):
    """Occurrences d'un calendrier .ics. Renvoie {"occurrences": [{uid, intitule, debut, fin, lieu}],
    "avertissements": [phrases], "ignores": {"journee": n, "annules": n, "illisibles": n}}.
    Leve ErreurICS si ce n'est pas un calendrier."""
    if len(texte) > TAILLE_MAX:
        raise ErreurICS("Ce fichier est trop gros pour un horaire (plus de 5 Mo) : ce n'est sans doute pas le bon.")
    lignes = deplier(texte)
    if not lignes or lignes[0].strip().upper() != "BEGIN:VCALENDAR":
        raise ErreurICS("Ce fichier n'est pas un calendrier .ics lisible (il ne commence pas par BEGIN:VCALENDAR).")
    avert, ignores = [], {"journee": 0, "annules": 0, "illisibles": 0}
    maitres, modifs = [], []
    for ev in evenements_bruts(lignes):
        (p_deb, v_deb) = un(ev, "DTSTART")
        intitule = texte_ics(un(ev, "SUMMARY")[1]) or "(sans intitulé)"
        try:
            debut = date_ics(v_deb, p_deb)
        except ValueError:
            ignores["illisibles"] += 1
            continue
        if not isinstance(debut, dt.datetime):
            ignores["journee"] += 1
            continue
        try:
            if ev.get("DTEND"):
                fin = date_ics(*reversed(un(ev, "DTEND")))
                fin = fin if isinstance(fin, dt.datetime) else debut
            elif ev.get("DURATION"):
                fin = debut + duree_ics(un(ev, "DURATION")[1])
            else:
                fin = debut
        except ValueError:
            fin = debut
        e = {"uid": un(ev, "UID")[1].strip(), "intitule": intitule, "debut": debut, "duree": fin - debut,
             "lieu": texte_ics(un(ev, "LOCATION")[1]),
             "annule": un(ev, "STATUS")[1].strip().upper() == "CANCELLED", "ev": ev}
        if ev.get("RECURRENCE-ID"):
            try:
                e["remplace"] = date_ics(*reversed(un(ev, "RECURRENCE-ID")))
            except ValueError:
                ignores["illisibles"] += 1
                continue
            modifs.append(e)
        else:
            maitres.append(e)
    remplacements = {(m["uid"], m["remplace"]): m for m in modifs}
    occ = []
    for e in maitres:
        if e["annule"]:
            ignores["annules"] += 1
            continue
        debuts = [e["debut"]]
        if e["ev"].get("RRULE"):
            r = regle(un(e["ev"], "RRULE")[1])
            raison = regle_non_lue(r)
            if raison:
                avert.append(f"« {e['intitule']} » : {raison} non lue ; seule la première séance "
                             f"({e['debut']:%d.%m.%Y}) est prise.")
            else:
                # DTSTART compte toujours comme une seance, meme hors des jours de la regle (RFC 5545).
                debuts = [e["debut"]] + occurrences_hebdo(e["debut"], r)
        for params, valeur in e["ev"].get("RDATE", []):
            if params.get("VALUE", "").upper() == "PERIOD":
                avert.append(f"« {e['intitule']} » : dates ajoutées sous forme de période, non lues.")
                continue
            try:
                debuts += [d for d in liste_dates(valeur, params) if isinstance(d, dt.datetime)]
            except ValueError:
                avert.append(f"« {e['intitule']} » : dates ajoutées (RDATE) illisibles, non lues.")
        exclues = set()
        for params, valeur in e["ev"].get("EXDATE", []):
            try:
                exclues.update(liste_dates(valeur, params))
            except ValueError:
                avert.append(f"« {e['intitule']} » : dates exclues (EXDATE) illisibles : séances peut-être en trop.")
        for d in sorted(set(debuts)):
            if d in exclues or d.date() in exclues:
                continue
            m = remplacements.pop((e["uid"], d), None)
            if m is not None:
                if m["annule"]:
                    ignores["annules"] += 1
                    continue
                occ.append(occurrence(m, m["debut"]))
            else:
                occ.append(occurrence(e, d))
    for m in remplacements.values():            # occurrence modifiee dont l'originale n'est pas trouvee
        if not m["annule"]:
            occ.append(occurrence(m, m["debut"]))
    occ.sort(key=lambda o: (o["debut"], o["intitule"]))
    return {"occurrences": occ, "avertissements": avert, "ignores": ignores}


def occurrence(e, debut):
    return {"uid": e["uid"], "intitule": e["intitule"], "debut": debut, "fin": debut + e["duree"], "lieu": e["lieu"]}


def lire_fichier(chemin):
    try:
        with open(chemin, "rb") as f:
            brut = f.read(TAILLE_MAX + 1)
    except OSError as e:
        raise ErreurICS(f"Impossible de lire le fichier : {e.strerror or 'erreur système'}.")
    if len(brut) > TAILLE_MAX:
        raise ErreurICS("Ce fichier est trop gros pour un horaire (plus de 5 Mo) : ce n'est sans doute pas le bon.")
    return lire(decoder(brut))


def decoder(brut):
    try:
        return brut.decode("utf-8-sig")
    except UnicodeDecodeError:
        return brut.decode("latin-1")
