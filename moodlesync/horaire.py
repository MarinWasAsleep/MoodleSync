"""Horaire de l'etudiant pour Ma semaine : import d'un .ics, groupes suivis, rapprochement avec Moodle.

Stockage : horaire_ics.json dans le dossier des reglages (ms.APP_DIR), local, jamais publie.
  {"version": 1,
   "source": {"type": "fichier" | "abonnement", "nom": "calendar.ics", "importe": "2026-11-01T21:00:00"},
   "abonnement": "https://..." ou null,      adresse collee par l'etudiant (relue a chaque actualisation)
   "erreur_abonnement": {"quand": ..., "message": ...} ou null,
   "avertissements": [...],                 ce que le lecteur .ics n'a pas su lire
   "cours": [{"id", "intitule", "moodle": {"propose": cid ou null, "confirme": cid, "aucun" ou null},
              "groupes": [{"id", "jour", "debut", "fin", "lieu", "dates": [iso], "suivi": bool}]}],
   "cours_moodle": {cid: nom complet}}       derniers cours Moodle connus, pour proposer les rapprochements

Methode generique, sans regle propre a un etablissement :
  - un groupe = (intitule, jour, heure de debut, heure de fin, lieu) ; l'etudiant coche ceux qu'il suit
    (un cours a un seul groupe est coche d'office ; a plusieurs, aucun : il est "a choisir") ;
  - le cours Moodle correspondant est PROPOSE (similarite des mots), puis CONFIRME par l'etudiant ;
    rien n'est utilise pour dater tant que ce n'est pas confirme ;
  - horaire_effectif() fusionne ce resultat avec horaire.json (format en tete de seances.py), qui reste lu
    tel quel (suivi, controle, titre, calendrier) ; pour un cours rapproche, le jour, l'heure et les dates
    reelles viennent du .ics. horaire.json n'est jamais modifie ni supprime.
"""
import os, re, json, hashlib, collections, datetime as dt, unicodedata, urllib.request, urllib.error

from . import moteur as ms, seances as sc, ics

CHEMIN = os.path.join(ms.APP_DIR, "horaire_ics.json")
SOURCE = "ton horaire (.ics)"
SEUIL_PROPOSITION = 0.6
MOTS_VIDES = {"a", "au", "aux", "d", "de", "des", "du", "en", "et", "l", "la", "le", "les", "of", "the", "and",
              "to", "in", "for", "un", "une", "sur", "pour"}
GENRES = {"cours": "cours", "lecture": "cours", "course": "cours", "seminaire": "seminaire", "seminar": "seminaire",
          "sem": "seminaire", "tp": "tp", "td": "tp", "exercices": "tp", "travaux": "tp"}
ROMAINS = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}


# ------------------------------------------------------------------ stockage
def vide():
    return {"version": 1, "source": None, "abonnement": None, "erreur_abonnement": None, "avertissements": [],
            "cours": [], "cours_moodle": {}}


def charger():
    try:
        with open(CHEMIN, encoding="utf-8") as f:
            h = json.load(f)
    except Exception:
        return vide()
    return {**vide(), **h} if isinstance(h, dict) else vide()


def sauver(h):
    os.makedirs(os.path.dirname(CHEMIN), exist_ok=True)
    with open(CHEMIN + ".tmp", "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=1)
    os.replace(CHEMIN + ".tmp", CHEMIN)


def maintenant():
    return dt.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ normalisation et rapprochement
def sans_accents(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn")


def mots_et_genre(nom):
    """(mots significatifs, genre ou None) d'un nom de cours, du .ics ou de Moodle. Le genre (cours,
    seminaire, TP) est lu dans le prefixe Moodle (COURS_, SEM_) ou dans un mot du nom ("(Cours)",
    "- Seminaire") ; ce mot ne compte alors plus parmi les mots compares."""
    t = sans_accents(ms.RE_ANNEE.sub(" ", nom or "")).lower()
    genre = None
    m = re.match(r"^\s*(cours|sem|lecture|seminar|tp|td)_\s*", t)
    if m:
        genre, t = GENRES[m.group(1)], t[m.end():]
    mots = set()
    for x in re.findall(r"[a-z0-9]+", t):
        x = ROMAINS.get(x, x)
        if x in GENRES:
            genre = genre or GENRES[x]
        elif x not in MOTS_VIDES:
            mots.add(x)
    return mots, genre


def similarite(nom_ics, nom_moodle):
    """Score de 0 a 1 : mots communs (Jaccard) ; divise par deux si les genres (cours, seminaire) different,
    majore de 0,15 s'ils sont les memes (departage "Theories economiques - ITE" et "SEM_... - SITE")."""
    a, ga = mots_et_genre(nom_ics)
    b, gb = mots_et_genre(nom_moodle)
    if not a or not b:
        return 0.0
    s = len(a & b) / len(a | b)
    if ga and gb:
        s = s / 2 if ga != gb else min(1.0, s + 0.15)
    return round(s, 3)


def proposer(intitule, cours_moodle):
    """cid propose pour un intitule du .ics, ou None : meilleur score >= seuil et net devant le second."""
    scores = sorted(((similarite(intitule, nom), cid) for cid, nom in cours_moodle.items()), reverse=True)
    if not scores or scores[0][0] < SEUIL_PROPOSITION:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.1:
        return None
    return scores[0][1]


# ------------------------------------------------------------------ groupes
def normaliser(t):
    return re.sub(r"\s+", " ", sans_accents(t).lower()).strip()


def ident(*morceaux):
    return hashlib.sha1("|".join(str(m) for m in morceaux).encode("utf-8")).hexdigest()[:10]


def construire(occurrences):
    """Cours et groupes a partir des occurrences lues par ics.lire()."""
    par_cours = collections.OrderedDict()
    for o in occurrences:
        cle = normaliser(o["intitule"])
        c = par_cours.setdefault(cle, {"id": ident(cle), "intitule": o["intitule"], "groupes": collections.OrderedDict()})
        g_cle = (o["debut"].weekday(), f"{o['debut']:%H:%M}", f"{o['fin']:%H:%M}", o["lieu"].strip())
        g = c["groupes"].setdefault(g_cle, {"id": ident(cle, *g_cle), "jour": g_cle[0], "debut": g_cle[1],
                                            "fin": g_cle[2], "lieu": g_cle[3], "dates": []})
        d = o["debut"].date().isoformat()
        if d not in g["dates"]:
            g["dates"].append(d)
    out = []
    for c in par_cours.values():
        groupes = sorted(c["groupes"].values(), key=lambda g: (g["jour"], g["debut"], g["fin"], g["lieu"]))
        for g in groupes:
            g["dates"].sort()
            g["suivi"] = len(groupes) == 1
        out.append({"id": c["id"], "intitule": c["intitule"], "groupes": groupes,
                    "moodle": {"propose": None, "confirme": None}})
    return sorted(out, key=lambda c: normaliser(c["intitule"]))


def libelle_groupe(g):
    n = len(g["dates"])
    lieu = f", {g['lieu']}" if g["lieu"] else ""
    return f"{sc.JOURS_NOMS[g['jour']]} {g['debut']} à {g['fin']}{lieu} ({n} séance{'s' if n > 1 else ''})"


def reprendre_choix(nouveaux, anciens):
    """Garde, apres un nouvel import, les groupes coches et les rapprochements confirmes de l'import precedent."""
    par_id = {c["id"]: c for c in anciens}
    for c in nouveaux:
        a = par_id.get(c["id"])
        if not a:
            continue
        c["moodle"] = dict(a.get("moodle") or c["moodle"])
        choix = {g["id"]: g.get("suivi") for g in a.get("groupes", [])}
        for g in c["groupes"]:
            if g["id"] in choix:
                g["suivi"] = bool(choix[g["id"]])
    return nouveaux


def indice_horaire_json(c, cid):
    """Migration : si horaire.json donne jour et heure pour ce cours Moodle et qu'UN SEUL groupe correspond,
    il est coche (rien n'est coche si plusieurs groupes correspondent)."""
    h = sc.charger_horaire().get(str(cid), {})
    if h.get("jour") is None or len(c["groupes"]) < 2 or any(g["suivi"] for g in c["groupes"]):
        return
    ok = [g for g in c["groupes"] if g["jour"] == h["jour"] and (not h.get("heure") or g["debut"] == h["heure"])]
    if len(ok) == 1:
        ok[0]["suivi"] = True


def a_choisir(c):
    return len(c["groupes"]) > 1 and not any(g["suivi"] for g in c["groupes"])


# ------------------------------------------------------------------ import
def importer_texte(texte, source):
    """Lit un .ics et remplace l'horaire, en gardant les choix precedents. Leve ics.ErreurICS si illisible."""
    lu = ics.lire(texte)
    if not lu["occurrences"]:
        raise ics.ErreurICS("Ce calendrier ne contient aucune séance avec une heure : rien à importer.")
    h = charger()
    cours = reprendre_choix(construire(lu["occurrences"]), h["cours"])
    for c in cours:
        if not c["moodle"].get("confirme"):
            c["moodle"]["propose"] = proposer(c["intitule"], h["cours_moodle"])
    avert = list(lu["avertissements"])
    if lu["ignores"]["illisibles"]:
        avert.append(f"{lu['ignores']['illisibles']} événement(s) à la date illisible, ignoré(s).")
    h.update(cours=cours, avertissements=avert, source={**source, "importe": maintenant()})
    sauver(h)
    return h


def importer_fichier(chemin):
    with open(chemin, "rb") as f:
        brut = f.read(ics.TAILLE_MAX + 1)
    if len(brut) > ics.TAILLE_MAX:
        raise ics.ErreurICS("Ce fichier est trop gros pour un horaire (plus de 5 Mo) : ce n'est sans doute pas le bon.")
    return importer_texte(ics.decoder(brut), {"type": "fichier", "nom": os.path.basename(chemin)})


def adresse_valide(adresse):
    """Adresse d'abonnement en https (webcal:// converti), ou leve ms.Erreur."""
    a = (adresse or "").strip()
    if re.match(r"(?i)^webcals?://", a):
        a = "https://" + a.split("://", 1)[1]
    if not re.match(r"(?i)^https://[^\s/]+\.[^\s/]+/?\S*$", a):
        raise ms.Erreur("Adresse d'abonnement invalide : colle un lien qui commence par https:// ou webcal://.")
    return a


def telecharger(adresse):
    """Texte du calendrier a l'adresse donnee (HTTPS, 20 s, 5 Mo au plus). Leve ms.Erreur avec une phrase lisible."""
    req = urllib.request.Request(adresse, headers={"User-Agent": "MoodleSync", "Accept": "text/calendar"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            if not r.geturl().lower().startswith("https://"):
                raise ms.Erreur("L'adresse d'abonnement redirige vers une adresse non chiffrée (http) : refusée.")
            brut = r.read(ics.TAILLE_MAX + 1)
    except urllib.error.HTTPError as e:
        raise ms.Erreur(f"Le serveur de l'horaire a refusé la demande (code {e.code}). Le lien a peut-être expiré.")
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        raise ms.Erreur("Le serveur de l'horaire ne répond pas. Vérifie la connexion internet, ou le lien.")
    if len(brut) > ics.TAILLE_MAX:
        raise ics.ErreurICS("Le calendrier en ligne dépasse 5 Mo : ce n'est sans doute pas un horaire.")
    return ics.decoder(brut)


def nom_de_source(adresse):
    """Nom affiche d'un abonnement : le domaine seul (le reste du lien est souvent un jeton personnel)."""
    return re.sub(r"(?i)^https://", "", adresse).split("/")[0]


def regler_abonnement(adresse):
    """Enregistre l'adresse (ou la retire si vide) et importe tout de suite. Leve ms.Erreur."""
    h = charger()
    if not (adresse or "").strip():
        h["abonnement"], h["erreur_abonnement"] = None, None
        sauver(h)
        return h
    a = adresse_valide(adresse)
    h = importer_texte(telecharger(a), {"type": "abonnement", "nom": nom_de_source(a)})
    h["abonnement"], h["erreur_abonnement"] = a, None
    sauver(h)
    return h


def actualiser_abonnement():
    """Relit l'abonnement s'il y en a un. Ne leve jamais : renvoie un message d'avertissement ou None."""
    h = charger()
    if not h.get("abonnement"):
        return None
    try:
        h = importer_texte(telecharger(h["abonnement"]), {"type": "abonnement", "nom": nom_de_source(h["abonnement"])})
        h["erreur_abonnement"] = None
        sauver(h)
        return None
    except ms.Erreur as e:
        msg = str(e)
    except Exception as e:
        msg = ms.message_erreur(e, "Relecture de l'horaire en ligne")
    h = charger()
    h["erreur_abonnement"] = {"quand": maintenant(), "message": msg}
    sauver(h)
    return f"relecture de l'horaire en ligne impossible ({msg}) ; l'horaire déjà importé est gardé."


# ------------------------------------------------------------------ choix de l'etudiant
def trouver(h, cours_id):
    for c in h["cours"]:
        if c["id"] == cours_id:
            return c
    raise ms.Erreur("Cours introuvable dans l'horaire : réimporte le fichier.")


def choisir_groupe(cours_id, groupe_id, suivi):
    h = charger()
    c = trouver(h, cours_id)
    for g in c["groupes"]:
        if g["id"] == groupe_id:
            g["suivi"] = bool(suivi)
            sauver(h)
            return h
    raise ms.Erreur("Groupe introuvable dans l'horaire : réimporte le fichier.")


def confirmer(cours_id, cid):
    """cid : identifiant du cours Moodle, ou "aucun" (ce cours du .ics n'est pas dans Moodle), ou None (annule)."""
    h = charger()
    c = trouver(h, cours_id)
    if cid not in (None, "aucun"):
        cid = str(cid)
        if h["cours_moodle"] and cid not in h["cours_moodle"]:
            raise ms.Erreur("Ce cours Moodle n'est pas dans la liste de tes cours.")
    c["moodle"]["confirme"] = cid
    if cid not in (None, "aucun"):
        indice_horaire_json(c, cid)
    sauver(h)
    return h


def noter_cours_moodle(cours):
    """Garde la liste des cours Moodle (id, nom complet) et met a jour les propositions non confirmees."""
    h = charger()
    connus = {str(c["id"]): c.get("fullname") or c.get("shortname") or str(c["id"]) for c in cours}
    if connus == h["cours_moodle"]:
        return h
    h["cours_moodle"] = connus
    for c in h["cours"]:
        if not c["moodle"].get("confirme"):
            c["moodle"]["propose"] = proposer(c["intitule"], connus)
    sauver(h)
    return h


# ------------------------------------------------------------------ pour le moteur de Ma semaine
def horaire_effectif():
    """horaire.json complete par le .ics : {cid: {jour, heure, suivi, controle, titre, dates, heures, source}}
    plus "calendrier" (de horaire.json). Pour un cours rapproche (confirme) avec au moins un groupe suivi :
    jour (si tous ses groupes suivis tombent le meme jour), heure habituelle, dates reelles et heure de chacune."""
    base = sc.charger_horaire()
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in base.items()}
    reunis = collections.defaultdict(list)
    for c in charger()["cours"]:
        cid = c["moodle"].get("confirme")
        if cid in (None, "aucun"):
            continue
        reunis[str(cid)] += [g for g in c["groupes"] if g.get("suivi")]
    for cid, groupes in reunis.items():
        if not groupes:
            continue
        heures = {}
        for g in groupes:
            for d in g["dates"]:
                heures[d] = min(heures.get(d, g["debut"]), g["debut"])
        jours = {g["jour"] for g in groupes}
        e = out.setdefault(cid, {})
        e["jour"] = jours.pop() if len(jours) == 1 else None
        e["heure"] = collections.Counter(g["debut"] for g in groupes).most_common(1)[0][0]
        e["dates"], e["heures"], e["source"] = sorted(heures), heures, SOURCE
    return out


def avertissements():
    """Points a verifier lies a l'horaire, pour la liste "A verifier" de Ma semaine."""
    h = charger()
    out = []
    if h.get("erreur_abonnement"):
        out.append(f"Horaire : dernière relecture de l'horaire en ligne impossible ({h['erreur_abonnement']['message']}).")
    for c in h["cours"]:
        cid = c["moodle"].get("confirme")
        if cid not in (None, "aucun") and a_choisir(c):
            out.append(f"Horaire : « {c['intitule']} » a {len(c['groupes'])} groupes et aucun n'est coché. "
                       "Choisis le tien dans l'écran Horaire, sinon ses dates ne sont pas utilisées.")
    out += [f"Horaire : {a}" for a in h.get("avertissements", [])]
    return out


# ------------------------------------------------------------------ pour la page
def etat_page(h=None):
    """Etat de l'horaire pour l'ecran Horaire (JSON)."""
    h = h or charger()
    cours = []
    for c in h["cours"]:
        m = c["moodle"]
        cours.append({"id": c["id"], "intitule": c["intitule"], "a_choisir": a_choisir(c),
                      "propose": m.get("propose"), "confirme": m.get("confirme"),
                      "groupes": [{"id": g["id"], "libelle": libelle_groupe(g), "suivi": bool(g.get("suivi")),
                                   "premiere": g["dates"][0] if g["dates"] else None,
                                   "derniere": g["dates"][-1] if g["dates"] else None} for g in c["groupes"]]})
    toutes = sorted(d for c in h["cours"] for g in c["groupes"] for d in g["dates"])
    return {"source": h.get("source"), "abonnement": h.get("abonnement"),
            "erreur_abonnement": h.get("erreur_abonnement"), "avertissements": h.get("avertissements", []),
            "periode": [toutes[0], toutes[-1]] if toutes else None, "cours": cours,
            "cours_moodle": [{"id": cid, "nom": sc.nom_affiche(nom)}
                             for cid, nom in sorted(h["cours_moodle"].items(), key=lambda x: sc.nom_affiche(x[1]))]}
