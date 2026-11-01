"""Fenetre de MoodleSync : l'interface HTML (interface/index.html) dans une fenetre native (pywebview).

Ce fichier ne fait que relier la page aux moteurs : moteur.py (synchronisation), semaine.py et
seances.py (Ma semaine, lecture seule sur Moodle), suivi.py (cases, temps, echeances, changements).
Chaque methode publique de Api est appelable depuis la page (window.pywebview.api.<nom>) et renvoie
du JSON ; les erreurs sont des phrases lisibles ({"erreur": ...}), le detail technique va dans erreurs.txt.

pywebview execute chaque appel de la page dans son propre fil : une operation longue (connexion,
synchronisation) bloque seulement l'appel qui l'a lancee. La progression et le journal remontent a la
page par evaluate_js (Api._js). Une seule operation longue de synchronisation a la fois (Api._long).
"""
import os, sys, json, threading, functools

from . import moteur as ms, semaine as m, seances as sc, suivi as S, VERSION
from .api_horaire import ApiHoraire

REGLAGES_SEMAINE = {"active": bool, "jours": int, "vitesse": int, "pages": bool, "dossier": str,
                    "export_md": bool}
# Reglages de la synchronisation (config.json). "auto" n'est pas dans config.json : c'est le raccourci
# de demarrage (regler_demarrage). "theme" vaut pour toute la fenetre.
REGLAGES_SYNC = {"dest": str, "statuts": bool, "note": bool, "langue": str, "titres_youtube": bool,
                 "auto": bool, "theme": str, "accueil_fait": bool}
THEMES = ("systeme", "light", "dark")
SESSION_EXPIREE = "La session Moodle a expiré. Reconnecte-toi (onglet Synchroniser), puis réessaie."
OCCUPE = "Une opération est déjà en cours : attends qu'elle se termine (ou annule-la)."


def dossier_interface():
    """Dossier de la page : dans le paquet, ou dans le dossier temporaire de l'executable (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None)
    return os.path.join(base, "interface") if base else os.path.join(os.path.dirname(os.path.abspath(__file__)), "interface")


def proteger(action):
    """Decorateur : toute exception devient {"erreur": phrase lisible}."""
    def deco(f):
        @functools.wraps(f)
        def g(*a, **k):
            try:
                return f(*a, **k)
            except ms.SessionExpiree:
                return {"erreur": SESSION_EXPIREE}
            except ms.Erreur as e:
                return {"erreur": str(e)}
            except Exception as e:
                return {"erreur": ms.message_erreur(e, action)}
        return g
    return deco


def pluriel(n, mot, mots=None):
    return f"{n} {mot if n == 1 else (mots or mot + 's')}"


class Api(ApiHoraire):
    """Fonctions appelees par la page. Les attributs prefixes de _ ne sont pas exposes a la page."""

    def __init__(self):
        self._fenetre = None
        self._semaine = None                         # cree a la demande : Ma semaine peut etre desactivee
        self._long = threading.Lock()                # connexion, verification d'adresse, synchronisation
        self._arret = threading.Event()              # bouton Annuler
        self._cours = {}                             # cid -> ligne affichee (derniere liste lue dans Moodle)
        self._vc = threading.RLock()                 # config.json : lu et ecrit par plusieurs fils

    # -- outils internes
    def _js(self, fonction, valeur):
        if self._fenetre is not None:
            try:
                self._fenetre.evaluate_js(f"window.{fonction} && window.{fonction}({json.dumps(valeur)})")
            except Exception:
                pass

    def _journal(self, texte):
        self._js("syncJournal", str(texte))

    def _sem(self):
        if self._semaine is None:
            self._semaine = S.Semaine()
        return self._semaine

    def _general_semaine(self):
        p = S.prefs()
        out = {"prefs": p, "profils": [{"nom": n, "vitesse": v, "origine": o} for n, v, o in sc.PROFILS],
               "vitesse_mesuree": None}
        if p["active"]:
            out["vitesse_mesuree"] = S.vitesse_mesuree(self._sem().suivi)
        return out

    def _cfg(self):
        with self._vc:
            c = ms.charger_config()
            ms.appliquer_config(c)
            return c

    def _sauver_cfg(self, modif):
        """Relit config.json, applique `modif(cfg)`, l'ecrit : une modification ne peut pas en effacer une autre."""
        with self._vc:
            c = ms.charger_config()
            modif(c)
            ms.sauver_config(c)
            ms.appliquer_config(c)
            return c

    # ================================================================ fenetre et reglages generaux
    @proteger("Démarrage")
    def infos(self):
        """Ce que la page doit savoir au demarrage, avant tout appel reseau."""
        c = self._cfg()
        theme = c.get("theme") or m.charger_prefs().get("theme") or "systeme"   # theme du prototype repris
        return {"version": VERSION, "mac": ms.MAC, "explorateur": ms.EXPLORATEUR, "navigateurs": ms.NAVIGATEURS,
                "theme": theme if theme in THEMES else "systeme", "semaine_active": S.prefs()["active"],
                "verif_action": os.environ.get("MOODLESYNC_VERIF_ACTION", "aucune") if os.environ.get("MOODLESYNC_VERIF")
                else "aucune"}

    # ================================================================ Synchroniser
    def _textes(self):
        T = ms.T
        return {"statuts": f"Sous-dossiers {T['O']}, {T['C']}, {T['P']}, {T['S']}",
                "note": f"Lister les nouveautés dans « {T['note']} »", "liens": T["liens"]}

    def _etat_sync(self, c=None):
        c = c or self._cfg()
        return {"site": c["site"], "dest": c["dest"], "langue": c["langue"],
                "langues": [{"code": k, "nom": v["nom"]} for k, v in ms.LANGUES.items()],
                "statuts": bool(c["statuts"]), "note": bool(c["note"]),
                "titres_youtube": bool(c.get("titres_youtube", True)), "auto": os.path.exists(ms.DEMARRAGE),
                "jeton": bool(c["token"]), "accueil": not (c["token"] or c["cours"] or c.get("accueil_fait")),
                "dest_existe": os.path.isdir(c["dest"]), "textes": self._textes(), "occupe": self._long.locked()}

    @proteger("Réglages")
    def sync_etat(self):
        """Reglages de la synchronisation, pour l'onglet Synchroniser."""
        return self._etat_sync()

    def _lignes(self, cours, c):
        """Lignes de la liste des cours : dossier (choisi ou par defaut), case, fichiers, volume, nouveautes."""
        lignes = []
        for x in cours:
            choix = c["cours"].get(str(x["id"]), {})
            # Meme nom par defaut que collecte() : calcule depuis le nom complet du cours.
            defaut = ms.dossier_defaut({"fullname": x["nom"], "shortname": x.get("shortname", "")})
            lignes.append({"id": x["id"], "nom": x["nom"], "dossier": ms.nettoie_dossier(choix.get("dossier") or defaut),
                           "choisi": bool(choix.get("choisi", True)), "nb": x["nb"], "taille": x["taille"],
                           "taille_txt": ms.humain(x["taille"]), "nouveaux": x.get("nouveaux", 0)})
        self._cours = {l["id"]: l for l in lignes}
        return lignes

    def _liste(self, c, jeton, userid):
        cours = ms.resume_cours(jeton, ms.cours_inscrits(jeton, userid), ms.charger_etat(c["dest"]))
        lignes = self._lignes(cours, c)
        nb, total = sum(l["nb"] for l in lignes), sum(l["taille"] for l in lignes)
        nouveaux = sum(l["nouveaux"] for l in lignes if l["choisi"])
        return {"cours": lignes, "total": f"{pluriel(len(lignes), 'cours', 'cours')}, {pluriel(nb, 'fichier')}, "
                                          f"{ms.humain(total)}", "taille_totale": ms.humain(total),
                "nouveaux": nouveaux}

    @proteger("Vérification de la session")
    def sync_verifier(self):
        """Session encore valable ? Puis la liste des cours. Ne touche ni au navigateur ni aux fichiers."""
        c = self._cfg()
        if not c["token"]:
            return {"statut": {"texte": "Non connecté", "ok": False}, "connecte": False}
        try:
            i = ms.infos_session(c["token"])
        except ms.SessionExpiree:
            self._sauver_cfg(lambda x: x.update(token=""))
            return {"statut": {"texte": "Session expirée. Clique sur « Se connecter ».", "ok": False},
                    "connecte": False, "expiree": True}
        except ms.Erreur as e:
            # Reseau coupe ou Moodle en panne : le jeton reste valable, on le garde.
            return {"statut": {"texte": f"{str(e)[:160]} Relance plus tard.", "ok": False}, "connecte": False,
                    "jeton_garde": True}
        nom = i.get("fullname")
        out = {"statut": {"texte": f"Connecté : {nom}" if nom else "Statut inconnu : connexion probable",
                          "ok": True if nom else None}, "connecte": True, "nom": nom}
        return {**out, **self._liste(c, c["token"], i["userid"])}

    @proteger("Adresse du Moodle")
    def sync_site(self, texte, confirme=False):
        """Change l'adresse du Moodle. Renvoie {"confirmer": question} si l'on quitte un compte connecte."""
        base = ms.normaliser_site(texte)
        c = self._cfg()
        if base == c["site"]:
            return {"ok": True, "site": base, "inchange": True}
        if (c["token"] or c["cours"]) and not confirme:
            return {"confirmer": f"Passer à {base} ?\n\nTu seras déconnecté de {c['site']} et la liste de tes cours "
                                 "sera oubliée. Les fichiers déjà téléchargés ne sont pas touchés.", "site": base}
        if not self._long.acquire(blocking=False):
            return {"erreur": OCCUPE}
        try:
            ms.verifier_site(base)
        finally:
            self._long.release()
        self._sauver_cfg(lambda x: x.update(site=base, token="", cours={}))
        self._cours = {}
        return {"ok": True, "site": base, "etat": self._etat_sync()}

    @proteger("Connexion")
    def sync_connecter(self):
        """Ouvre Chrome (ou Edge sous Windows), attend la connexion, puis liste les cours (jusqu'a 10 min)."""
        if not self._cfg()["site"]:
            return {"erreur": "Indique d'abord l'adresse de ton Moodle."}
        if not self._long.acquire(blocking=False):
            return {"erreur": OCCUPE}
        try:
            jeton, certain = ms.connexion_navigateur(self._journal)
            c = self._sauver_cfg(lambda x: x.update(token=jeton))
            i = ms.infos_session(jeton)
            nom = i.get("fullname")
            if certain and nom:
                statut = {"texte": f"Connecté : {nom}", "ok": True}
            else:
                self._journal("Ce Moodle n'a pas montré le menu utilisateur habituel : "
                              "la connexion est déduite du jeton obtenu.")
                statut = {"texte": "Statut inconnu : connexion probable", "ok": None}
            return {"statut": statut, "connecte": True, "nom": nom or "statut inconnu",
                    **self._liste(c, jeton, i["userid"])}
        finally:
            self._long.release()

    def _maj_cours(self, c, l):
        c["cours"][str(l["id"])] = {"dossier": l["dossier"], "choisi": l["choisi"]}

    @proteger("Choix des cours")
    def sync_choisir(self, cid, choisi):
        """Coche ou decoche un cours (cid), ou tous les cours (cid = null)."""
        cibles = list(self._cours.values()) if cid is None else [self._cours.get(int(cid))]
        if None in cibles:
            return {"erreur": "Cours inconnu : actualise la liste."}
        for l in cibles:
            l["choisi"] = bool(choisi)
        self._sauver_cfg(lambda c: [self._maj_cours(c, l) for l in cibles])
        return {"ok": True, "nouveaux": sum(l["nouveaux"] for l in self._cours.values() if l["choisi"])}

    @proteger("Renommage")
    def sync_renommer(self, cid, nouveau, confirme=False):
        """Renomme le dossier d'un cours sur le disque (et ceux des cours ranges a l'interieur)."""
        if self._long.locked():
            return {"erreur": "Attends la fin du téléchargement pour renommer un dossier."}
        d = self._cours.get(int(cid))
        if d is None:
            return {"erreur": "Cours inconnu : actualise la liste."}
        if not str(nouveau or "").strip() or ms.nettoie_dossier(nouveau) == d["dossier"]:
            return {"inchange": True}
        c = self._cfg()
        nouveau, ancien = ms.nettoie_dossier(nouveau), d["dossier"]
        # Cours ranges a l'interieur (SITE dans le dossier ITE) : leurs chemins suivent.
        prefixe = os.path.normcase(ancien) + os.sep
        inclus = [x for x in self._cours.values() if x is not d and os.path.normcase(x["dossier"]).startswith(prefixe)]
        src = os.path.join(c["dest"], ancien)
        if os.path.isdir(src) and not confirme:
            n = sum(len(f) for _, _, f in os.walk(src))
            suivent = "".join(f"\n   {x['dossier']}" for x in inclus)
            return {"confirmer": f"Renommer le dossier sur le disque, avec ses {n} fichiers ?\n\n   {ancien}\n→ {nouveau}"
                                 + (f"\n\nCes cours rangés à l'intérieur suivront :{suivent}" if inclus else "")
                                 + "\n\nSi tu refuses, le nom reste inchangé."}
        ms.renommer_dossier_cours(c["dest"], ancien, nouveau)
        for x in [d] + inclus:
            x["dossier"] = nouveau + x["dossier"][len(ancien):]
        self._sauver_cfg(lambda cc: [self._maj_cours(cc, x) for x in [d] + inclus])
        self._journal(f"Dossier renommé : {ancien} → {nouveau}")
        return {"ok": True, "cours": list(self._cours.values())}

    @proteger("Réglages")
    def sync_regler(self, cle, valeur):
        if cle not in REGLAGES_SYNC:
            return {"erreur": f"Réglage inconnu : {cle}"}
        try:
            valeur = REGLAGES_SYNC[cle](valeur)
        except (TypeError, ValueError):
            return {"erreur": "Valeur invalide."}
        if cle == "langue" and valeur not in ms.LANGUES or cle == "theme" and valeur not in THEMES:
            return {"erreur": "Valeur invalide."}
        if cle == "dest":
            valeur = valeur.strip()
            if not valeur or not os.path.isabs(os.path.expanduser(valeur)):
                return {"erreur": "Indique un chemin complet de dossier."}
            valeur = os.path.normpath(os.path.expanduser(valeur))
        if cle == "auto":
            ms.regler_demarrage(valeur)
            self._journal("Synchronisation automatique activée : elle se fera à chaque ouverture de session, avec un "
                          "message seulement s'il y a du nouveau." if valeur else "Synchronisation automatique désactivée.")
            return self._etat_sync()
        if cle == "langue":
            if valeur == self._cfg()["langue"]:
                return self._etat_sync()

            def changer(c):
                # Un nom de dossier par defaut depend de la langue : on fige ceux d'aujourd'hui,
                # sinon un second dossier apparaitrait a cote du premier.
                for l in self._cours.values():
                    self._maj_cours(c, l)
                c["langue"] = valeur
            self._sauver_cfg(changer)
            self._journal(f"Langue des dossiers : {ms.LANGUES[valeur]['nom']}. Elle s'applique aux nouveaux fichiers "
                          "et aux nouvelles notes ; ce qui est déjà rangé ne bouge pas.")
            return self._etat_sync()
        self._sauver_cfg(lambda c: c.update({cle: valeur}))
        return self._etat_sync()

    @proteger("Réglages")
    def sync_choisir_dossier(self):
        import webview
        c = self._cfg()
        depart = c["dest"] if os.path.isdir(c["dest"]) else os.path.expanduser("~")
        r = self._fenetre.create_file_dialog(webview.FOLDER_DIALOG, directory=depart)
        if r:
            return self.sync_regler("dest", os.path.normpath(r[0] if isinstance(r, (list, tuple)) else r))
        return self._etat_sync()

    @proteger("Ouverture du dossier")
    def sync_ouvrir_dossier(self):
        d = self._cfg()["dest"]
        if not os.path.isdir(d):
            return {"erreur": "Le dossier n'existe pas encore."}
        ms.ouvrir_dossier(d)
        return {"ok": True}

    @proteger("Annulation")
    def sync_annuler(self):
        """Arrete la synchronisation : le fichier en cours est abandonne, les fichiers finis restent."""
        if not self._long.locked():
            return {"ok": False}
        self._arret.set()
        return {"ok": True}

    @proteger("Synchronisation")
    def sync_lancer(self, creer=False):
        """Telecharge et range. Renvoie {"resultat": ...}, {"annule_avant": True} ou {"confirmer": ...}."""
        c = self._cfg()
        if not c["token"]:
            return {"erreur": "Commence par te connecter à Moodle."}
        if not os.path.isdir(c["dest"]):
            if not creer:
                return {"confirmer": f"Le dossier\n{c['dest']}\nn'existe pas encore. Le créer ?"}
            try:
                os.makedirs(c["dest"], exist_ok=True)
            except OSError as e:
                return {"erreur": f"Impossible de créer le dossier : {e.strerror or e}"}
        choisis = {cid for cid, l in self._cours.items() if l["choisi"]}
        if not choisis:
            return {"erreur": "Aucun cours n'est coché." if self._cours else "Connecte-toi pour voir tes cours."}
        if not self._long.acquire(blocking=False):
            return {"erreur": OCCUPE}
        self._arret.clear()
        try:
            dire = self._journal
            i = ms.infos_session(c["token"])
            retenus = [x for x in ms.cours_inscrits(c["token"], i["userid"]) if x["id"] in choisis]
            liens = []
            try:
                items = ms.collecte(c["token"], retenus, c, dire, liens=liens, arreter=self._arret.is_set)
            except ms.Annule:
                dire("Synchronisation annulée pendant la lecture des cours : rien n'a été téléchargé.")
                return {"annule_avant": True}
            dire(f"{len(items)} fichiers et {len(liens)} liens à examiner.")
            r = ms.telecharger(items, c, dire=dire, arreter=self._arret.is_set,
                               progres=lambda a, b, t: self._js("syncProgres", {"i": a, "n": b, "texte": t}))
            # Annule : les liens attendront la prochaine synchronisation, la note liste ce qui est deja arrive.
            r["liste_liens"] = [] if r["annule"] else ms.ecrire_liens(liens, c["dest"], dire=dire)
            r["note"] = ms.ecrire_note(r) if c["note"] else None
            restants = {int(k): v for k, v in r["restants"].items()}
            for cid, l in self._cours.items():
                if l["choisi"]:
                    l["nouveaux"] = restants.get(cid, 0)
            return {"resultat": {"neufs": r["neufs"], "maj": r["maj"], "doublons": r["doublons"],
                                 "erreurs": r["erreurs"], "liens": len(r["liste_liens"]), "dest": r["dest"],
                                 "note": r["note"], "annule": bool(r["annule"]), "lignes": ms.nouveautes_par_cours(r),
                                 "fichier_liens": ms.T["liens"]},
                    "cours": list(self._cours.values())}
        finally:
            self._arret.clear()
            self._long.release()

    # ================================================================ Ma semaine
    @proteger("Ma semaine")
    def demarrer(self):
        """Reglages et derniere analyse gardee (affichee tout de suite, avant l'actualisation)."""
        g = self._general_semaine()
        return {**g, "donnees": self._sem().derniere() if g["prefs"]["active"] else None}

    @proteger("Actualisation")
    def actualiser(self):
        """Relit Moodle (20 a 60 secondes). Refuse si Ma semaine est desactivee."""
        if not S.prefs()["active"]:
            return {"erreur": "Ma semaine est désactivée : active-la d'abord."}
        r = self._sem().actualiser(lambda t: self._js("progression", t))
        return {**self._general_semaine(), **r}

    @proteger("Suivi")
    def cocher(self, ident, fait, pages=None):
        self._sem().cocher(ident, fait, pages)
        return {"ok": True}

    @proteger("Suivi")
    def noter_temps(self, ident, texte, pages=None):
        return self._sem().noter_temps(ident, texte, pages)

    @proteger("Échéances")
    def ajouter_echeance(self, date, heure, cours, nom):
        return self._sem().ajouter_echeance(date, heure, cours, nom)

    @proteger("Échéances")
    def supprimer_echeance(self, ident):
        return self._sem().supprimer_echeance(ident)

    @proteger("Changements")
    def changements_vus(self):
        self._sem().changements_vus()
        return {"ok": True}

    @proteger("Réglages")
    def regler(self, cle, valeur):
        """Reglage de Ma semaine (liste blanche REGLAGES_SEMAINE)."""
        if cle not in REGLAGES_SEMAINE:
            return {"erreur": f"Réglage inconnu : {cle}"}
        try:
            valeur = REGLAGES_SEMAINE[cle](valeur)
        except (TypeError, ValueError):
            return {"erreur": "Valeur invalide."}
        if cle == "jours" and not 1 <= valeur <= 120 or cle == "vitesse" and not 1 <= valeur <= 80:
            return {"erreur": "Valeur hors limites."}
        p = m.charger_prefs()
        # "active" toujours ecrit : sans lui, un fichier de reglages non vide passe pour celui du prototype
        # (suivi.prefs active alors Ma semaine).
        p.setdefault("active", S.prefs()["active"])
        p[cle] = valeur
        m.sauver_prefs(p)
        return self._general_semaine()

    @proteger("Réglages")
    def choisir_dossier(self):
        import webview
        r = self._fenetre.create_file_dialog(webview.FOLDER_DIALOG, directory=S.prefs()["dossier"])
        if r:
            return self.regler("dossier", os.path.normpath(r[0] if isinstance(r, (list, tuple)) else r))
        return self._general_semaine()

    @proteger("Audit")
    def audit(self):
        if not S.prefs()["active"]:
            return {"erreur": "Ma semaine est désactivée : active-la d'abord."}
        b = m.analyser_audit(lambda t: self._js("progression", t))
        avert = None
        try:
            m.ecrire(os.path.join(S.prefs()["dossier"], m.FICHIER_AUDIT), m.rendre_audit(b))
        except ms.Erreur as e:
            avert = str(e)
        except OSError as e:
            avert = ms.message_erreur(e, "Écriture de l'audit")
        return {"bilan": b, "avertissement": avert}

    @proteger("Ouverture")
    def ouvrir(self, quoi):
        """Ouvre le dossier, Ma semaine.md ou l'audit."""
        dossier = S.prefs()["dossier"]
        if quoi == "dossier":
            if not os.path.isdir(dossier):
                return {"erreur": "Le dossier n'existe pas encore."}
            ms.ouvrir_dossier(dossier)
            return {"ok": True}
        nom = {"md": m.FICHIER, "audit": m.FICHIER_AUDIT}.get(quoi)
        chemin = os.path.join(dossier, nom) if nom else None
        if not chemin or not os.path.exists(chemin):
            return {"erreur": "Fichier pas encore créé : actualise d'abord."}
        return {"ok": m.ouvrir_document(chemin) is not None}


def rafraichir_demarrage():
    """Le programme a pu etre deplace depuis l'activation du lancement automatique : on remet le raccourci
    a jour. Seulement pour l'executable : lance depuis les sources, la commande ne serait pas celle voulue."""
    if getattr(sys, "frozen", False) and os.path.exists(ms.DEMARRAGE):
        try:
            ms.regler_demarrage(True)
        except Exception as e:
            ms.message_erreur(e, "Mise à jour du lancement automatique")


def identifiant_windows():
    """Sans cet identifiant, la barre des taches de Windows range la fenetre sous l'icone de Python."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MoodleSync")
        except Exception:
            pass


def lancer(titre="MoodleSync"):
    """Ouvre la fenetre. Leve ImportError si pywebview manque, une autre exception si le moteur web manque."""
    import webview
    identifiant_windows()
    threading.Thread(target=rafraichir_demarrage, daemon=True).start()
    api = Api()
    fenetre = webview.create_window(titre, url=os.path.join(dossier_interface(), "index.html"), js_api=api,
                                    width=1280, height=880, min_size=(380, 560), background_color="#f4f4f2")
    api._fenetre = fenetre
    stockage = os.path.join(ms.APP_DIR, "webview")
    verif = os.environ.get("MOODLESYNC_VERIF")
    if not verif:
        webview.start(private_mode=False, storage_path=stockage)
        return

    # Verification sans intervention (CI, essais) : attend que la page ait fini de charger (ou affiche une
    # erreur), ecrit ce qu'elle montre (window.etatVerification()) dans le fichier `verif`, puis ferme.
    def verifier():
        import time
        etat = "délai dépassé"
        for _ in range(int(os.environ.get("MOODLESYNC_VERIF_DELAI", "180"))):
            time.sleep(1)
            try:
                etat = fenetre.evaluate_js("window.etatVerification ? JSON.stringify(window.etatVerification()) : ''")
            except Exception as e:
                etat = f"evaluate_js : {e!r}"
                continue
            if etat and '"pret":true' in etat:
                break
        with open(verif, "w", encoding="utf-8") as f:
            f.write(str(etat))
        fenetre.destroy()
    webview.start(verifier, private_mode=False, storage_path=stockage)
