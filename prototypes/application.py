#!/usr/bin/env python3
"""Application Ma semaine : l'interface HTML (interface/index.html) dans une fenetre native (pywebview).

LECTURE SEULE sur Moodle. Le moteur (dates, consignes, controles) est dans seances.py et ma_semaine.py ;
ce fichier ne fait que le relier a l'interface :
  - suivi des lectures (cases, temps reels) et echeances ajoutees a la main : ma_semaine_suivi.json,
    dans le dossier des reglages de MoodleSync. Au premier lancement, repris de Ma semaine.md ;
  - derniere analyse gardee (ma_semaine_dernier.json) : la fenetre s'ouvre tout de suite, puis s'actualise ;
  - Ma semaine.md reste ecrit a chaque actualisation (reglage "export_md"), comme export lisible ailleurs.
Sans pywebview, ma_semaine.py ouvre l'ancienne fenetre (tkinter).
"""
import os, sys, json, threading, hashlib, datetime as dt, collections

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ma_semaine as m
import seances as sc

ms = sc.ms
SUIVI = os.path.join(ms.APP_DIR, "ma_semaine_suivi.json")
DERNIER = os.path.join(ms.APP_DIR, "ma_semaine_dernier.json")
REGLAGES_PERMIS = {"jours": int, "vitesse": int, "pages": bool, "dossier": str, "export_md": bool, "theme": str}


def dossier_interface():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "interface")


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


ERREURS = os.path.join(ms.APP_DIR, "ma_semaine_erreurs.txt")


def message_erreur(e, action):
    """Detail technique dans ma_semaine_erreurs.txt (local), phrase lisible pour la fenetre."""
    import traceback
    try:
        os.makedirs(ms.APP_DIR, exist_ok=True)
        with open(ERREURS, "a", encoding="utf-8") as f:
            f.write(f"\n[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {action}\n")
            f.write("".join(traceback.format_exception(type(e), e, e.__traceback__)))
    except OSError:
        pass
    if isinstance(e, OSError):
        return f"{action} : impossible de lire ou d'écrire un fichier ({e.strerror or 'erreur système'})."
    if isinstance(e, (ConnectionError, TimeoutError)) or type(e).__module__.startswith(("urllib", "http", "socket")):
        return f"{action} : Moodle ne répond pas. Vérifie la connexion internet, puis réessaie."
    return f"{action} : erreur imprévue. Le détail est noté dans {ERREURS}."


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


# ------------------------------------------------------------------ pont avec la page (pywebview js_api)
class Api:
    """Fonctions appelees par la page : window.pywebview.api.<nom>(...). Chaque appel renvoie du JSON."""

    def __init__(self):
        self._fenetre = None
        self._verrou = threading.Lock()          # une seule actualisation a la fois
        self._vs = threading.RLock()             # suivi : la page peut cocher pendant une actualisation
        prefs = m.charger_prefs()
        chemin_md = os.path.join(self._dossier(prefs), m.FICHIER)
        self._suivi = charger_suivi(chemin_md)
        try:
            fusionner_md(self._suivi, chemin_md)
        except OSError:
            pass                                 # fichier illisible : la prochaine actualisation le signalera
        self._sauver()

    # -- outils internes (le prefixe _ les cache a la page)
    def _dossier(self, prefs=None):
        prefs = prefs if prefs is not None else m.charger_prefs()
        return prefs.get("dossier") or ms.charger_config()["dest"]

    def _sauver(self):
        with self._vs:
            ecrire_json(SUIVI, self._suivi)

    def _js(self, fonction, valeur):
        if self._fenetre is not None:
            try:
                self._fenetre.evaluate_js(f"window.{fonction} && window.{fonction}({json.dumps(valeur)})")
            except Exception:
                pass

    def _prefs(self):
        p = m.charger_prefs()
        return {"jours": int(p.get("jours", 14)), "vitesse": int(p.get("vitesse", sc.VITESSE_DEFAUT)),
                "pages": bool(p.get("pages", True)), "dossier": self._dossier(p),
                "export_md": bool(p.get("export_md", True)), "theme": p.get("theme", "systeme")}

    def _general(self):
        return {"prefs": self._prefs(), "vitesse_mesuree": vitesse_mesuree(self._suivi),
                "profils": [{"nom": n, "vitesse": v, "origine": o} for n, v, o in sc.PROFILS]}

    # -- appels de la page
    def demarrer(self):
        """Reglages et derniere analyse gardee (affichee tout de suite, avant l'actualisation)."""
        return {**self._general(), "donnees": completer(lire_json(DERNIER, None), self._suivi)}

    def actualiser(self):
        """Relit Moodle (20 a 60 secondes). Renvoie les donnees, ou {"erreur": message lisible}."""
        if not self._verrou.acquire(blocking=False):
            return {"erreur": "Une actualisation est déjà en cours."}
        try:
            prefs = self._prefs()
            chemin_md = os.path.join(prefs["dossier"], m.FICHIER)
            avert = []
            with self._vs:
                try:
                    if fusionner_md(self._suivi, chemin_md):
                        self._sauver()
                except OSError as e:
                    avert.append(message_erreur(e, "Lecture de Ma semaine.md"))
            R = m.analyser(prefs["jours"], prefs["pages"], m.CACHE, lambda t: self._js("progression", t))
            donnees = donnees_interface(R, self._suivi, prefs)
            with self._vs:
                cumuler_changements(self._suivi, R, donnees["genere"])
                self._sauver()
            ecrire_json(DERNIER, donnees)
            m.memoriser(R)
            if prefs["export_md"]:
                try:
                    self._exporter(R, prefs)
                except ms.Erreur as e:
                    avert.append(str(e))
                except OSError as e:
                    avert.append(message_erreur(e, "Export de Ma semaine.md"))
            return {**self._general(), "donnees": completer(donnees, self._suivi),
                    "avertissement": " ".join(avert) or None}
        except ms.SessionExpiree:
            return {"erreur": "La session Moodle a expiré. Ouvre MoodleSync, reconnecte-toi, puis actualise."}
        except ms.Erreur as e:
            return {"erreur": str(e)}
        except Exception as e:
            return {"erreur": message_erreur(e, "Actualisation")}
        finally:
            self._verrou.release()

    def _exporter(self, R, prefs):
        chemin = os.path.join(prefs["dossier"], m.FICHIER)
        with self._vs:
            _, notes, ancien, _, _ = m.lire_ancien(chemin)
            if ancien is not None and ms.MARQUE not in ancien:
                raise ms.Erreur(f"« {m.FICHIER} » existe sans la marque de MoodleSync : export Markdown non écrit.")
            etat = {k: (bool(v.get("fait")), v.get("minutes")) for k, v in self._suivi["lectures"].items()}
            c = self._suivi["changements"]
            # Le fichier montre, comme la fenetre, les changements pas encore marques comme vus.
            R = {**R, "changements": c["messages"] or (None if R["changements"] is None else []),
                 "nouvelles": {tuple(x) for x in c["nouvelles"]}}
            m.ecrire(chemin, m.rendre_depuis(R, prefs["vitesse"], etat, notes, texte_mes_echeances(self._suivi)))
            noter_export(self._suivi, chemin)
            self._sauver()

    def cocher(self, ident, fait, pages=None):
        with self._vs:
            v = self._suivi["lectures"].setdefault(str(ident), {})
            v["fait"] = bool(fait)
            if pages:
                v["pages"] = int(pages)
            self._sauver()
        return {"ok": True}

    def noter_temps(self, ident, texte, pages=None):
        """Temps reel saisi ("70", "1 h 10"...). Renvoie les minutes comprises et la vitesse mesuree.
        Un champ vide efface le temps ; un texte illisible ne change rien."""
        texte = str(texte or "").strip()
        minutes = m.minutes_reelles(texte if texte.lower().startswith(("réel", "reel")) else f"réel {texte}")
        with self._vs:
            v = self._suivi["lectures"].setdefault(str(ident), {})
            if texte and not minutes:
                return {"minutes": None, "illisible": True, "garde": v.get("minutes"),
                        "vitesse_mesuree": vitesse_mesuree(self._suivi)}
            v["minutes"] = minutes
            if pages:
                v["pages"] = int(pages)
            if minutes:
                v["fait"] = True
            self._sauver()
        return {"minutes": minutes, "vitesse_mesuree": vitesse_mesuree(self._suivi)}

    def ajouter_echeance(self, date, heure, cours, nom):
        try:
            d = dt.datetime.fromisoformat(f"{date}T{heure or '23:59'}")
        except ValueError:
            return {"erreur": "Date ou heure illisible."}
        nom = str(nom or "").strip() or "(sans intitulé)"
        cours = str(cours or "").strip()
        iso = d.isoformat(timespec="minutes")
        ident = id_echeance(iso, cours, nom)
        with self._vs:
            if any(e["id"] == ident for e in self._suivi["echeances"]):
                return {"erreur": "Cette échéance existe déjà."}
            self._suivi["echeances"].append({"id": ident, "date": iso, "cours": cours, "nom": nom})
            self._sauver()
            return {"echeances": self._suivi["echeances"]}

    def supprimer_echeance(self, ident):
        with self._vs:
            self._suivi["echeances"] = [e for e in self._suivi["echeances"] if e["id"] != ident]
            self._sauver()
            return {"echeances": self._suivi["echeances"]}

    def changements_vus(self):
        """Marque comme vus les changements affiches : ils quittent la fenetre et Ma semaine.md."""
        with self._vs:
            self._suivi["changements"] = {"messages": [], "nouvelles": [], "depuis": None}
            self._sauver()
        return {"ok": True}

    def regler(self, cle, valeur):
        if cle not in REGLAGES_PERMIS:
            return {"erreur": f"Réglage inconnu : {cle}"}
        try:
            valeur = REGLAGES_PERMIS[cle](valeur)
        except (TypeError, ValueError):
            return {"erreur": "Valeur invalide."}
        if cle == "jours" and not 1 <= valeur <= 120 or cle == "vitesse" and not 1 <= valeur <= 80:
            return {"erreur": "Valeur hors limites."}
        m.sauver_prefs({**m.charger_prefs(), cle: valeur})
        return self._general()

    def choisir_dossier(self):
        import webview
        r = self._fenetre.create_file_dialog(webview.FOLDER_DIALOG, directory=self._dossier())
        if r:
            return self.regler("dossier", os.path.normpath(r[0] if isinstance(r, (list, tuple)) else r))
        return self._general()

    def audit(self):
        try:
            b = m.analyser_audit(lambda t: self._js("progression", t))
            avert = None
            try:
                m.ecrire(os.path.join(self._dossier(), m.FICHIER_AUDIT), m.rendre_audit(b))
            except ms.Erreur as e:
                avert = str(e)
            except OSError as e:
                avert = message_erreur(e, "Écriture de l'audit")
            return {"bilan": b, "avertissement": avert}
        except ms.SessionExpiree:
            return {"erreur": "La session Moodle a expiré. Ouvre MoodleSync, reconnecte-toi, puis réessaie."}
        except ms.Erreur as e:
            return {"erreur": str(e)}
        except Exception as e:
            return {"erreur": message_erreur(e, "Audit")}

    def ouvrir(self, quoi):
        """Ouvre le dossier, Ma semaine.md ou l'audit."""
        dossier = self._dossier()
        if quoi == "dossier":
            ms.ouvrir_dossier(dossier)
            return {"ok": True}
        nom = {"md": m.FICHIER, "audit": m.FICHIER_AUDIT}.get(quoi)
        chemin = os.path.join(dossier, nom) if nom else None
        if not chemin or not os.path.exists(chemin):
            return {"erreur": "Fichier pas encore créé : actualise d'abord."}
        return {"ok": m.ouvrir_document(chemin) is not None}


def lancer():
    """Ouvre la fenetre. Leve ImportError si pywebview n'est pas installe."""
    import webview
    api = Api()
    fenetre = webview.create_window("Ma semaine", url=os.path.join(dossier_interface(), "index.html"), js_api=api,
                                    width=1280, height=880, min_size=(380, 560), background_color="#f4f4f2")
    api._fenetre = fenetre
    verif = os.environ.get("MASEMAINE_VERIF")
    if verif:
        # Verification sans intervention : attend que la page ait affiche le planning (ou une erreur),
        # ecrit ce qu'elle montre dans le fichier `verif`, puis ferme la fenetre.
        def verifier():
            import time
            etat = "délai dépassé"
            for _ in range(180):
                time.sleep(1)
                try:
                    etat = fenetre.evaluate_js(
                        "JSON.stringify({cartes: document.querySelectorAll('.carte').length,"
                        " lectures: document.querySelectorAll('.lecture').length,"
                        " pages: (document.querySelector('#t-pages') || {}).dataset?.v,"
                        " alertes: (document.querySelector('#t-alertes') || {}).dataset?.v,"
                        " occupe: document.querySelector('#progres').classList.contains('actif'),"
                        " erreur: document.querySelector('#bandeaux').innerText})")
                except Exception as e:
                    etat = f"evaluate_js : {e!r}"
                    continue
                if etat and '"occupe":false' in etat and ('"cartes":0' not in etat or '"erreur":"' in etat
                                                           and '"erreur":""' not in etat):
                    break
            with open(verif, "w", encoding="utf-8") as f:
                f.write(str(etat))
            fenetre.destroy()
        webview.start(verifier, private_mode=False, storage_path=os.path.join(ms.APP_DIR, "webview"))
        return
    webview.start(private_mode=False, storage_path=os.path.join(ms.APP_DIR, "webview"))


if __name__ == "__main__":
    lancer()
