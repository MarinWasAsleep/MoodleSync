"""Ma semaine, suivi de l'etudiant : cases cochees, temps reels, echeances ajoutees a la main,
changements dans Moodle pas encore vus. Fusion avec Ma semaine.md (Obsidian, editeur de texte).

Aucune interface ici : utilise par application.py (fenetre) et par le mode automatique.
"""
import os, json, threading, hashlib, datetime as dt, collections

from . import semaine as m, seances as sc

ms = sc.ms
SUIVI = os.path.join(ms.APP_DIR, "ma_semaine_suivi.json")
DERNIER = os.path.join(ms.APP_DIR, "ma_semaine_dernier.json")


def lire_json(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defaut


def ecrire_json(chemin, valeur):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin + ".tmp", "w", encoding="utf-8") as f:
        json.dump(valeur, f, ensure_ascii=False, indent=1)
    os.replace(chemin + ".tmp", chemin)


# ------------------------------------------------------------------ suivi (cases, temps, echeances a la main)
def id_echeance(date, cours, nom):
    return hashlib.sha1(f"{date}|{cours}|{nom}".encode("utf-8")).hexdigest()[:10]


def migrer_depuis_md(chemin):
    """Suivi repris d'un Ma semaine.md existant : cases cochees, temps notes, section "Mes echeances"."""
    etat, _, texte, mesures, mes = m.lire_ancien(chemin)
    suivi = {"lectures": {}, "echeances": []}
    if texte is None or ms.MARQUE not in texte:
        return suivi                                   # pas de fichier, ou fichier de l'utilisateur : on n'y lit rien
    for ident, (fait, minutes) in etat.items():
        if fait or minutes:
            suivi["lectures"][ident] = {"fait": bool(fait), "minutes": minutes,
                                        "pages": mesures.get(ident, (None,))[0]}
    for e in m.echeances_manuelles(mes):
        date = e["date"].isoformat(timespec="minutes")
        suivi["echeances"].append({"id": id_echeance(date, e["cours"], e["nom"]), "date": date,
                                   "cours": e["cours"], "nom": e["nom"]})
    return suivi


def charger_suivi(chemin_md=None):
    suivi = lire_json(SUIVI, None)
    if suivi is None:
        suivi = migrer_depuis_md(chemin_md) if chemin_md else {"lectures": {}, "echeances": []}
    suivi.setdefault("lectures", {})
    suivi.setdefault("echeances", [])
    suivi.setdefault("changements", {"messages": [], "nouvelles": [], "depuis": None})
    return suivi


def lire_md_marque(chemin):
    """lire_ancien() si le fichier existe et porte la marque de MoodleSync, sinon None (on ne lit pas un
    fichier de l'utilisateur)."""
    lu = m.lire_ancien(chemin)
    return lu if lu[2] is not None and ms.MARQUE in lu[2] else None


def fusionner_md(suivi, chemin):
    """Reprend dans le suivi ce qui a ete coche ou note dans Ma semaine.md (Obsidian, editeur de texte).

    Fusion a trois versions : le suivi (application), le fichier, et ce que le dernier export a ecrit
    (suivi["export"]). Ce qui n'a change que dans le fichier passe dans le suivi ; ce qui n'a change que
    dans l'application reste. Si les deux ont change (ou sans export connu), rien ne se perd : une case
    cochee d'un cote reste cochee, un temps note d'un cote reste note (celui de l'application d'abord).
    Renvoie le nombre d'elements repris du fichier.
    """
    lu = lire_md_marque(chemin)
    if lu is None:
        return 0
    etat_md, _, _, mesures_md, mes_md = lu
    base = suivi.get("export")
    repris = 0
    for ident, md in etat_md.items():
        v = suivi["lectures"].get(ident, {})
        actuel = (bool(v.get("fait")), v.get("minutes"))
        b = tuple(base[ident]) if base and ident in base else None
        if md == actuel or md == b:
            continue                                   # fichier identique, ou pas touche depuis l'export
        nouveau = md if b is not None and actuel == b else (actuel[0] or md[0], actuel[1] or md[1])
        if nouveau == actuel:
            continue
        v = suivi["lectures"].setdefault(ident, {})
        v["fait"], v["minutes"] = nouveau
        if ident in mesures_md and not v.get("pages"):
            v["pages"] = mesures_md[ident][0]
        repris += 1
    # Echeances ecrites a la main : ajout et suppression dans le fichier sont repris.
    base_e = suivi.get("export_echeances")
    dans_md = {}
    for e in m.echeances_manuelles(mes_md):
        date = e["date"].isoformat(timespec="minutes")
        ident = id_echeance(date, e["cours"], e["nom"])
        dans_md[ident] = {"id": ident, "date": date, "cours": e["cours"], "nom": e["nom"]}
    dans_suivi = {e["id"] for e in suivi["echeances"]}
    for ident, e in dans_md.items():
        if ident not in dans_suivi and not (base_e is not None and ident in base_e):
            suivi["echeances"].append(e)               # ajoutee dans le fichier
            repris += 1
    if base_e is not None:
        avant = len(suivi["echeances"])
        suivi["echeances"] = [e for e in suivi["echeances"] if not (e["id"] in base_e and e["id"] not in dans_md)]
        repris += avant - len(suivi["echeances"])      # effacee dans le fichier
    return repris


def noter_export(suivi, chemin):
    """Retient ce que l'export vient d'ecrire : base de la prochaine fusion."""
    lu = lire_md_marque(chemin)
    if lu is None:
        return
    suivi["export"] = {k: list(v) for k, v in lu[0].items()}
    suivi["export_echeances"] = [id_echeance(e["date"].isoformat(timespec="minutes"), e["cours"], e["nom"])
                                 for e in m.echeances_manuelles(lu[4])]


def cumuler_changements(suivi, R, quand):
    """Ajoute les changements de cette actualisation a ceux pas encore marques comme vus."""
    c = suivi["changements"]
    if R["changements"]:
        c["messages"] += [x for x in R["changements"] if x not in c["messages"]]
        c["depuis"] = c["depuis"] or quand
    deja = {tuple(x) for x in c["nouvelles"]}
    c["nouvelles"] += [list(x) for x in sorted(R["nouvelles"]) if tuple(x) not in deja]


def vitesse_mesuree(suivi):
    """(pages par heure, nombre de lectures) d'apres les temps notes (application et anciens fichiers), ou None."""
    mesures = dict(m.charger_mesures())
    for ident, v in suivi["lectures"].items():
        if v.get("minutes") and v.get("pages"):
            mesures[ident] = (v["pages"], v["minutes"])
    return m.calcul_vitesse(mesures)


def echeances_suivi(suivi):
    """Echeances ajoutees a la main, au format des echeances Moodle (pour l'export Markdown)."""
    out = []
    for e in suivi["echeances"]:
        try:
            d = dt.datetime.fromisoformat(e["date"])
        except ValueError:
            continue
        out.append({"date": d, "cours": e.get("cours", ""), "nom": e.get("nom", ""), "en_retard": False,
                    "manuelle": True, "id": e["id"]})
    return out


def texte_mes_echeances(suivi):
    lignes = []
    for e in sorted(echeances_suivi(suivi), key=lambda e: e["date"]):
        cours = f" · {e['cours']}" if e["cours"] else ""
        lignes.append(f"- {e['date']:%d.%m.%Y %H:%M}{cours} · {e['nom']}")
    return "\n".join(lignes)


# ------------------------------------------------------------------ donnees pour l'interface
def jsonable(d):
    return d.isoformat() if isinstance(d, (dt.date, dt.datetime)) else d


def donnees_interface(R, suivi, prefs):
    """Ce que la page affiche, en JSON. Les phrases des controles restent celles du moteur."""
    vitesse = int(prefs.get("vitesse", sc.VITESSE_DEFAUT))
    seances = []
    for s in R["fenetre"]:
        lectures = []
        for f, ident in zip(s["lectures"], m.ids_lectures(s)):
            v = suivi["lectures"].get(ident, {})
            lectures.append({"id": ident, "nom": f["nom"], "statut": f["statut"], "origine": f["origine"],
                             "extrait": f.get("extrait"), "pages": sc.pages_a_lire(f),
                             "pages_pdf": f.get("pages"), "consigne_pages": bool(f.get("pages_consigne")),
                             "plages": f.get("plages") or [], "lien": f.get("url") if f.get("lien") else None,
                             "facultatif": f["statut"] in (ms.T["C"], ms.T["P"]),
                             "nouveau": (f"{s['cid']}:{s['section']}", f["nom"]) in R["nouvelles"],
                             "fait": bool(v.get("fait")), "minutes": v.get("minutes")})
        seances.append({"date": s["date"].isoformat(), "heure": s.get("heure"), "cours": s["cours"],
                        "cid": s["cid"], "cle": f"{s['cid']}:{s['section']}", "titre": s["titre"].strip(), "precision": s["precision"],
                        "sans_travail": s["sans_travail"], "sans_lecture": s["sans_lecture"],
                        "sans_cours_deduit": bool(s.get("sans_cours_deduit")), "ouverture": s["ouverture"],
                        "consigne": s.get("consigne") or [], "supports": len(s["supports"]), "lectures": lectures})
    echeances = [{"date": e["date"].isoformat(timespec="minutes"), "cours": sc.nom_affiche(e["cours"]),
                  "nom": e["nom"], "retard": bool(e["en_retard"]), "manuelle": False}
                 for e in R["echeances"]]
    a_dater = collections.Counter(s["cours"] for s in R["a_dater"])
    return {"genere": dt.datetime.now().isoformat(timespec="seconds"), "aujourdhui": R["aujourdhui"].isoformat(),
            "jours": R["jours"], "seances": seances, "echeances_moodle": echeances,
            "alertes": R["alertes"], "surveiller": R["a_surveiller"], "non_controles": R["non_controles"],
            "changements": R["changements"], "a_dater": dict(a_dater), "sans_seance": R["sans_seance"],
            "avec_pages": R["avec_pages"]}


def completer(donnees, suivi):
    """Etat du suivi applique aux donnees : cases, temps, echeances a la main, changements non vus."""
    if not donnees:
        return donnees
    c = suivi.get("changements") or {"messages": [], "nouvelles": [], "depuis": None}
    nouvelles = {tuple(x) for x in c["nouvelles"]}
    for s in donnees["seances"]:
        for l in s["lectures"]:
            v = suivi["lectures"].get(l["id"], {})
            l["fait"], l["minutes"] = bool(v.get("fait")), v.get("minutes")
            if s.get("cle"):
                l["nouveau"] = (s["cle"], l["nom"]) in nouvelles     # nouveau tant que pas marque "vu"
    donnees["non_vus"] = list(c["messages"])
    donnees["non_vus_depuis"] = c["depuis"]
    donnees["echeances"] = donnees["echeances_moodle"] + [
        {"date": e["date"], "cours": e.get("cours", ""), "nom": e.get("nom", ""), "retard": False,
         "manuelle": True, "id": e["id"]} for e in suivi["echeances"]]
    return donnees


# ------------------------------------------------------------------ service (fenetre et mode automatique)
PREFS_DEFAUT = {"active": False, "jours": 14, "vitesse": sc.VITESSE_DEFAUT, "pages": True, "dossier": "",
                "export_md": True, "theme": "systeme"}


def prefs():
    """Reglages de Ma semaine, completes par les valeurs par defaut. Dossier vide = celui de la synchronisation."""
    lu = m.charger_prefs()
    p = {**PREFS_DEFAUT, **lu}
    if lu and "active" not in lu:
        p["active"] = True                           # reglages du prototype : Ma semaine etait deja utilisee
    p["dossier"] = p["dossier"] or ms.charger_config()["dest"]
    return p


class Semaine:
    """Suivi de l'etudiant et actualisation. Un seul objet par processus ; sur pour plusieurs fils."""

    def __init__(self):
        self.vs = threading.RLock()
        self.verrou = threading.Lock()               # une seule actualisation a la fois
        chemin_md = os.path.join(prefs()["dossier"], m.FICHIER)
        self.suivi = charger_suivi(chemin_md)
        try:
            fusionner_md(self.suivi, chemin_md)
        except OSError:
            pass                                     # illisible : la prochaine actualisation le signalera
        self.sauver()

    def sauver(self):
        with self.vs:
            ecrire_json(SUIVI, self.suivi)

    def actualiser(self, dire=print):
        """Relit Moodle, garde l'analyse et ecrit Ma semaine.md. Leve ms.Erreur (dont SessionExpiree) ;
        renvoie {"donnees": ..., "avertissement": texte ou None}."""
        if not self.verrou.acquire(blocking=False):
            raise ms.Erreur("Une actualisation de Ma semaine est déjà en cours.")
        try:
            p = prefs()
            chemin_md = os.path.join(p["dossier"], m.FICHIER)
            avert = []
            with self.vs:
                try:
                    if fusionner_md(self.suivi, chemin_md):
                        self.sauver()
                except OSError as e:
                    avert.append(ms.message_erreur(e, "Lecture de Ma semaine.md"))
            R = m.analyser(p["jours"], p["pages"], m.CACHE, dire)
            donnees = donnees_interface(R, self.suivi, p)
            with self.vs:
                cumuler_changements(self.suivi, R, donnees["genere"])
                self.sauver()
            ecrire_json(DERNIER, donnees)
            m.memoriser(R)
            if p["export_md"]:
                try:
                    self.exporter(R, p)
                except ms.Erreur as e:
                    avert.append(str(e))
                except OSError as e:
                    avert.append(ms.message_erreur(e, "Export de Ma semaine.md"))
            return {"donnees": completer(donnees, self.suivi), "avertissement": " ".join(avert) or None}
        finally:
            self.verrou.release()

    def exporter(self, R, p):
        chemin = os.path.join(p["dossier"], m.FICHIER)
        with self.vs:
            _, notes, ancien, _, _ = m.lire_ancien(chemin)
            if ancien is not None and ms.MARQUE not in ancien:
                raise ms.Erreur(f"« {m.FICHIER} » existe sans la marque de MoodleSync : export Markdown non écrit.")
            etat = {k: (bool(v.get("fait")), v.get("minutes")) for k, v in self.suivi["lectures"].items()}
            c = self.suivi["changements"]
            # Le fichier montre, comme la fenetre, les changements pas encore marques comme vus.
            R = {**R, "changements": c["messages"] or (None if R["changements"] is None else []),
                 "nouvelles": {tuple(x) for x in c["nouvelles"]}}
            m.ecrire(chemin, m.rendre_depuis(R, p["vitesse"], etat, notes, texte_mes_echeances(self.suivi)))
            noter_export(self.suivi, chemin)
            self.sauver()

    def derniere(self):
        """Derniere analyse gardee, completee par le suivi (affichage immediat a l'ouverture)."""
        return completer(lire_json(DERNIER, None), self.suivi)

    def cocher(self, ident, fait, pages=None):
        with self.vs:
            v = self.suivi["lectures"].setdefault(str(ident), {})
            v["fait"] = bool(fait)
            if pages:
                v["pages"] = int(pages)
            self.sauver()

    def noter_temps(self, ident, texte, pages=None):
        """Temps reel saisi ("70", "1 h 10"...). Un champ vide efface le temps ; un texte illisible ne change rien."""
        texte = str(texte or "").strip()
        minutes = m.minutes_reelles(texte if texte.lower().startswith(("réel", "reel")) else f"réel {texte}")
        with self.vs:
            v = self.suivi["lectures"].setdefault(str(ident), {})
            if texte and not minutes:
                return {"minutes": None, "illisible": True, "garde": v.get("minutes"),
                        "vitesse_mesuree": vitesse_mesuree(self.suivi)}
            v["minutes"] = minutes
            if pages:
                v["pages"] = int(pages)
            if minutes:
                v["fait"] = True
            self.sauver()
        return {"minutes": minutes, "vitesse_mesuree": vitesse_mesuree(self.suivi)}

    def ajouter_echeance(self, date, heure, cours, nom):
        try:
            d = dt.datetime.fromisoformat(f"{date}T{heure or '23:59'}")
        except ValueError:
            return {"erreur": "Date ou heure illisible."}
        nom = str(nom or "").strip() or "(sans intitulé)"
        cours = str(cours or "").strip()
        iso = d.isoformat(timespec="minutes")
        ident = id_echeance(iso, cours, nom)
        with self.vs:
            if any(e["id"] == ident for e in self.suivi["echeances"]):
                return {"erreur": "Cette échéance existe déjà."}
            self.suivi["echeances"].append({"id": ident, "date": iso, "cours": cours, "nom": nom})
            self.sauver()
            return {"echeances": self.suivi["echeances"]}

    def supprimer_echeance(self, ident):
        with self.vs:
            self.suivi["echeances"] = [e for e in self.suivi["echeances"] if e["id"] != ident]
            self.sauver()
            return {"echeances": self.suivi["echeances"]}

    def changements_vus(self):
        with self.vs:
            self.suivi["changements"] = {"messages": [], "nouvelles": [], "depuis": None}
            self.sauver()
