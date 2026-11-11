"""Textes des cours : mixin de l'API de l'extraction locale du texte des documents (moodlesync/ocr.py).

Melange a application.Api : ces methodes sont appelees par la page (window.pywebview.api.<nom>). Chacune renvoie une
forme du contrat 4 de docs/refonte-textes/contrat.md, ou {"erreur": phrase lisible} : aucune exception ne sort et
aucune trace technique ne part vers la fenetre (invariant 9). Le reseau n'est appele nulle part ici, sauf par
ocr.restaurer, qui passe par moteur.py (invariant 6) : ce module n'importe aucune bibliotheque de reseau.

Verrous (contrat 3.2, invariant 7) :
- _ocr_verrou   (RLock, cache et file) : une lecture ou une ecriture de cache.json / file.json a la fois ;
- _ocr_fichiers (Lock) : une page ou un remplacement a la fois ;
- _sync_veut    (Event) : une synchronisation attend, l'extraction cede entre deux pages (priorite, D1).

La file ne se constitue plus que par `ocr_traiter` (contrat 4.4) : la synchronisation n'en cree aucune (contrat 7).
"""
import math, os, re, subprocess, sys, threading, time
from contextlib import contextmanager

from . import moteur as ms, ocr, textes_arbre
from .api_horaire import _proteger

ACTION = "Texte des cours"
# Lettre de lecteur Windows : `C:x` (ecart 144). Refuse avant `ocr._cle`, qui en ferait un chemin relatif.
RE_LECTEUR = re.compile(r"^[A-Za-z]:")
# Dossier de depot par defaut (contrat 4.2) : « Documents déposés » sur le Bureau.
DOSSIER_DEPOT = "Documents déposés"

# Etats de `file.etat` de 4.2. Pendant le travail, c'est l'etat du fil qui fait foi dans `_ocr_bloc_file`
# (E-V3-2) : un etat hors de cette liste (l'erreur imprevue de `_ocr_executer`) laisse parler file.json.
ETATS_FILE = ("inactive", "en_cours", "pause", "pause_sync", "terminee", "annulee")

# Valeurs par defaut des reglages que ce module lit (plan 5.6) : charger_config ne les ecrit pas.
REGLAGES_OCR = {"ocr_exe": "", "ocr_tessdata": "", "ocr_langues": "fra+eng", "ocr_dpi": 300,
                "ocr_psm": 3, "ocr_max_mo": 300, "ocr_threads": 2, "ocr_batterie": "pause", "ocr_format": "md"}
BATTERIES = ("pause", "continuer")
PSM = (1, 3, 4, 6)


def commande_ouvrir(chemin, plateforme=None):
    """Liste d'arguments qui ouvre `chemin` avec le lecteur du systeme (contrat 4.1), ou None sous Windows.

    Windows n'a pas de commande a liste d'arguments pour cela : `os.startfile` s'en charge. macOS ouvre par
    `open`, les autres systemes par `xdg-open`. Jamais de shell : l'appelant passe la liste telle quelle.
    """
    plateforme = sys.platform if plateforme is None else plateforme
    if plateforme.startswith("win"):
        return None
    if plateforme == "darwin":
        return ["open", chemin]
    return ["xdg-open", chemin]


def _message(code, **champs):
    """Phrase visible de la section 5 du contrat : ocr.MESSAGES est la seule source (invariant 9, ecart 122). Aucune
    phrase n'est ecrite dans ce module ; les champs `{...}` d'un modele se remplissent par `champs`."""
    modele = ocr.MESSAGES[code]
    return modele.format(**champs) if champs else modele


def _reglage(cfg, cle):
    """Valeur d'un reglage, valeur par defaut du plan 5.6 si la cle manque ou est illisible."""
    valeur = cfg.get(cle, REGLAGES_OCR[cle])
    return REGLAGES_OCR[cle] if valeur is None else valeur


def _entier(valeur, defaut=0):
    """Entier positif ou nul d'une valeur venue d'un JSON (cache ou file edites a la main). Seul un `int` hors
    booleen et non negatif passe ; toute autre valeur (chaine, flottant, booleen, negatif, liste) donne `defaut` :
    aucune valeur n'est inventee a partir d'une chaine (contrat 2.7, ecarts 136 et 165)."""
    if isinstance(valeur, int) and not isinstance(valeur, bool) and valeur >= 0:
        return valeur
    return defaut


def _nombre(valeur, mot):
    """« 1 document », « 3 documents » (zero et un au singulier)."""
    return f"{valeur} {mot}" + ("s" if valeur > 1 else "")


def _lecteur_sans_chemin(brut, est_absolu=os.path.isabs):
    """Vrai pour `C:x` ou `C:` (lettre de lecteur sans chemin absolu : ecart 144). Un chemin absolu sous Windows
    (`C:\\coffre\\x.md`) porte lui aussi une lettre de lecteur : il n'est pas refuse ici, `_ocr_confiner` le
    confine ensuite par `realpath` (ecart 299). `est_absolu` est remplacable par les tests (`ntpath.isabs`)."""
    return bool(RE_LECTEUR.match(brut)) and not est_absolu(brut)


def dossier_depot_defaut():
    """Dossier de depot par defaut (contrat 4.2) : « Documents déposés » sur le Bureau de l'utilisateur."""
    return os.path.join(os.path.expanduser("~"), "Desktop", DOSSIER_DEPOT)


class ApiTextes:
    """Pas de __init__ : Api.__init__ appelle self._init_textes() (contrat 3.2)."""

    # ------------------------------------------------------------------ mise en place
    def _init_textes(self):
        self._ocr_verrou = threading.RLock()         # cache et file
        self._ocr_fichiers = threading.Lock()        # une page ou un remplacement
        self._ocr_fil = None                         # fil daemon de l'extraction
        self._ocr_arret = threading.Event()          # annulation demandee
        self._ocr_pause = threading.Event()          # pause demandee par la page
        self._install_arret = threading.Event()      # annulation de l'installation du moteur (ecart 245)
        self._sync_veut = threading.Event()          # une synchronisation attend (D1)
        self._ocr_etat_fil = "inactive"              # etat pousse a la page
        self._ocr_courant = ""                       # chemin du document en cours
        self._ocr_origine = "coffre"                 # origine de la file en cours (contrat 4.2)
        self._ocr_page = 0                           # page en cours
        self._ocr_pages = 0                          # pages du document en cours
        self._ocr_faits = 0                          # documents termines de la file
        self._ocr_total = 0                          # documents de la file
        self._ocr_js = 0.0                           # derniere emission de progression
        self._ocr_memo = None                        # (instant, bloc moteur) : evite de relancer le moteur
        self._ocr_lancement()

    def _ocr_lancement(self):
        """Au lancement, hors extraction (contrat 3.1, invariant 5) : `.ocr.part` abandonnes, puis etat reconcilie.
        Ecart 112 : ce sont les deux appelants que Y2 n'avait pas. Ne leve jamais et ne cree rien."""
        try:
            dest = ms.charger_config().get("dest") or ""
            if os.path.isdir(dest):
                ocr.supprimer_parts_orphelins(dest)
                ocr.reconcilier_etat(dest)
        except Exception as e:
            try:
                ms.message_erreur(e, ACTION)
            except Exception:
                pass

    @contextmanager
    def _ocr_exclusif(self):
        """Invariant 7 : une synchronisation ou une restauration tient `_ocr_fichiers`, l'extraction cede entre deux
        pages. Pose `_sync_veut` avant d'attendre, pour que l'extraction ne prenne pas une page de plus."""
        self._sync_veut.set()
        try:
            with self._ocr_fichiers:
                yield
        finally:
            self._sync_veut.clear()

    def _ocr_fermer(self):
        """Fermeture de la fenetre : l'arret est demande, le fil n'est pas attendu (il est daemon)."""
        self._ocr_arret.set()
        self._install_arret.set()

    # ------------------------------------------------------------------ outils internes
    def _ocr_moteur(self, cfg, frais=False):
        """Bloc moteur (forme 3.1), garde 60 s : `detecter` lance deux sous-processus a chaque appel."""
        maintenant = time.monotonic()
        if not frais and self._ocr_memo is not None and maintenant - self._ocr_memo[0] < 60:
            return self._ocr_memo[1]
        bloc = ocr.detecter(cfg)
        self._ocr_memo = (maintenant, bloc)
        return bloc

    def _ocr_actif(self):
        return bool(self._ocr_fil is not None and self._ocr_fil.is_alive())

    def _ocr_bloc_file(self, cfg=None):
        """Bloc `file` de 4.2, derive de file.json (contrat 3.1 : la derivation appartient a ApiTextes).

        `ocr.charger_file` ramene `en_cours` a `pause` par construction (aucune reprise automatique apres une
        fermeture). Pendant le travail, c'est donc l'etat du fil qui fait foi, sinon `ocr_etat` annoncerait
        « en pause », sans document, alors que `occupe` est vrai (E-V3-2, 4.2).
        """
        cfg = cfg or self._cfg()
        dest = cfg.get("dest") or ""
        file = ocr.charger_file(dest) if dest else {"etat": "inactive", "origine": "coffre", "taches": []}
        taches = [t for t in file.get("taches") or [] if isinstance(t, dict)]
        en_cours = next((t for t in taches if t.get("etat") == "en_cours"), None)
        restants = sum(1 for t in taches if t.get("etat") in ("attente", "en_cours"))
        etat = file.get("etat") or "inactive"
        if self._ocr_actif() and self._ocr_etat_fil in ETATS_FILE:
            etat = self._ocr_etat_fil
        vivant = etat == "en_cours"
        origine = file.get("origine")
        return {"etat": etat,
                "origine": origine if origine in ocr.ORIGINES_FILE else "coffre",
                "document": (en_cours or {}).get("chemin") or (self._ocr_courant if vivant else ""),
                "page": _entier((en_cours or {}).get("pages_faites"), 0) if en_cours else (self._ocr_page if vivant else 0),
                "pages": _entier((en_cours or {}).get("pages"), 0) if en_cours else (self._ocr_pages if vivant else 0),
                "documents_faits": sum(1 for t in taches if t.get("etat") == "fait"),
                "documents_total": len(taches),
                "reprise": restants if etat in ("pause", "pause_sync", "annulee") else 0}

    def _ocr_arbre(self, cfg):
        """Arbre des documents du coffre (4.3), construit une seule fois par appel d'etat."""
        return textes_arbre.construire_arbre(cfg.get("dest") or "", cfg)

    def _ocr_resume(self, cfg=None):
        """Bloc `"ocr"` de sync_etat : moteur present et compteurs de l'arbre (4.2), sans relire le disque une
        deuxieme fois. Ne leve jamais : il part avec la liste des cours."""
        try:
            cfg = cfg or self._cfg()
            compteurs = textes_arbre.compteurs(self._ocr_arbre(cfg))
            return {"moteur": bool(self._ocr_moteur(cfg).get("present")), "fichiers": compteurs["fichiers"],
                    "traites": compteurs["traites"], "a_verifier": compteurs["a_verifier"],
                    "echecs": compteurs["echecs"], "non_traites": compteurs["non_traites"],
                    "reprise": self._ocr_bloc_file(cfg)["reprise"]}
        except Exception:
            return {"moteur": False, "fichiers": 0, "traites": 0, "a_verifier": 0, "echecs": 0, "non_traites": 0,
                    "reprise": 0}

    def _ocr_pousser(self, force=False, message=""):
        """Progression vers la page (window.textesProgres), au plus quatre fois par seconde (contrat 3.2). Le bloc
        porte `origine` (4.2) : la coque sait si le travail vient du coffre ou d'un depot."""
        maintenant = time.monotonic()
        if not force and maintenant - self._ocr_js < 0.25:
            return
        self._ocr_js = maintenant
        restant = None
        if self._ocr_etat_fil == "en_cours" and self._ocr_pages:
            restants = max(0, self._ocr_pages - self._ocr_page)
            if restants:
                # Extraction sequentielle (ecart 126, decision de Maxence) : `ocr_threads` ne divise pas la duree.
                restant = max(1, round(restants * 2 / 60))
        self._js("textesProgres", {"etat": self._ocr_etat_fil, "origine": self._ocr_origine,
                                   "document": self._ocr_courant, "page": self._ocr_page, "pages": self._ocr_pages,
                                   "documents_faits": self._ocr_faits, "documents_total": self._ocr_total,
                                   "restant_min": restant, "message": message})

    def _ocr_journal(self, texte):
        if texte:
            self._js("textesJournal", str(texte))

    # ------------------------------------------------------------------ outils d'ouverture
    def _ocr_confiner(self, dest, chemin, cfg):
        """Chemin absolu confine (invariant 8, plan 5.9), ou None.

        Relatif a `dest`, separateurs normalises par `ocr._cle` ; ni `..`, ni lettre de lecteur (`C:x`, ecart 144),
        ni dossier cache. Resolution par `os.path.realpath`, puis comparaison de prefixe avec `dest` : un lien
        symbolique qui sort du coffre est refuse. Aucun fichier cache n'est atteignable."""
        if not isinstance(chemin, str):
            return None
        brut = chemin.strip()
        if not brut or "\x00" in brut or _lecteur_sans_chemin(brut):
            return None                               # octet nul : refus, pas une erreur imprevue (ecart 159)
        if os.path.isabs(brut):
            candidat = brut
        else:
            parties = ocr._cle(brut).split("/")
            if not parties[0] or ".." in parties:
                return None
            candidat = ocr._absolu(dest, "/".join(parties))
        try:
            reel = os.path.realpath(candidat)
        except OSError:
            return None
        racines = [os.path.realpath(dest)]
        for racine in racines:
            try:
                relatif = os.path.relpath(os.path.normcase(os.path.normpath(reel)),
                                          os.path.normcase(os.path.normpath(racine)))
            except ValueError:
                continue                          # lecteur different (Windows)
            if relatif == os.curdir:
                return reel                      # la racine elle-meme
            parties = relatif.split(os.sep)
            if parties[0] == os.pardir:
                continue
            if any(partie.startswith(".") for partie in parties):
                return None                      # .moodlesync-ocr/, .moodlesync.json, nom cache
            return reel
        return None

    def _ocr_relatif(self, dest, chemin):
        """Chemin relatif a `dest`, avec `/` : la forme de tout chemin recu par l'API (4).

        Les deux cotes passent par `os.path.realpath` : `_ocr_confiner` rend deja un chemin resolu, et comparer a
        `dest` non resolu rendait un chemin en `..`. Sous macOS le dossier temporaire est sous `/var`, lien vers
        `/private/var` ; sous Windows `realpath` rend le nom long la ou le dossier porte le nom court 8.3
        (`RUNNER~1`). L'API refusait alors un document du coffre : `ocr_copier_texte` ne trouvait aucun texte et
        `ocr_restaurer` repondait « Ce PDF est abime » (familles C et D de R14).
        """
        try:
            return os.path.relpath(os.path.realpath(chemin), os.path.realpath(dest)).replace(os.sep, "/")
        except (OSError, ValueError):
            return ""                             # lecteur different (Windows)

    # ------------------------------------------------------------------ fil d'extraction
    def _ocr_lire_file(self, dest):
        """File relue du disque sous `_ocr_verrou` : c'est elle qui fait foi, jamais une copie gardee en memoire
        (ecart 130). `charger_file` ramene `en_cours` a `pause` ; l'etat du fil est donc remis ensuite."""
        with self._ocr_verrou:
            file = ocr.charger_file(dest)
        if self._ocr_etat_fil == "en_cours":
            file["etat"] = "en_cours"
        return file

    def _ocr_modifier_tache(self, dest, chemin, **champs):
        """Relit la file du disque, ne modifie que la tache de `chemin`, puis la reecrit (ecart 130). Renvoie la
        tache ecrite, ou None si elle a disparu de la file."""
        with self._ocr_verrou:
            file = ocr.charger_file(dest)
            if self._ocr_etat_fil == "en_cours":
                file["etat"] = "en_cours"
            tache = next((t for t in file.get("taches") or []
                          if isinstance(t, dict) and t.get("chemin") == chemin), None)
            if tache is not None:
                tache.update(champs)
                ocr.sauver_file(dest, file)
            return tache

    def _ocr_poser_etat(self, dest, etat):
        """Ecrit l'etat de la file s'il change, et le pousse a la page. La file est relue du disque, pour que les
        taches ajoutees entre-temps ne soient pas perdues (ecart 130)."""
        if etat == self._ocr_etat_fil:
            return
        with self._ocr_verrou:
            file = ocr.charger_file(dest)
            file["etat"] = etat
            ocr.sauver_file(dest, file)
        self._ocr_etat_fil = etat
        self._ocr_pousser(force=True)

    def _ocr_attendre(self, dest):
        """Entre deux pages : cede a la synchronisation (pause_sync, reprise seule) et respecte la pause.
        Faux si l'annulation a ete demandee."""
        while True:
            if self._ocr_arret.is_set():
                return False
            if self._sync_veut.is_set():
                self._ocr_poser_etat(dest, "pause_sync")
                time.sleep(0.05)
                continue
            if self._ocr_pause.is_set():
                self._ocr_poser_etat(dest, "pause")
                time.sleep(0.05)
                continue
            return True

    def _ocr_document(self, tache, dest, cfg):
        """Un document, une page a la fois sous `_ocr_fichiers` : la synchronisation passe entre deux pages.
        C'est `ocr.traiter_document` (contrat 3.1) qui fait le travail, pour chaque tache de la file (4.4)."""
        chemin = tache["chemin"]
        tenu = {"oui": False}

        def prendre():
            if not tenu["oui"]:
                self._ocr_fichiers.acquire()
                tenu["oui"] = True

        def rendre():
            if tenu["oui"]:
                self._ocr_fichiers.release()
                tenu["oui"] = False

        def progres(evt):
            pages_faites = _entier(evt.get("page"), tache.get("pages_faites", 0))
            tache["pages_faites"] = pages_faites
            self._ocr_page = pages_faites
            self._ocr_pages = _entier(evt.get("pages"), tache.get("pages", 0))
            # Contrat 2.5 : la file est ecrite apres chaque page, relue du disque et seule cette tache change.
            self._ocr_modifier_tache(dest, chemin, etat="en_cours", pages_faites=pages_faites)
            self._ocr_pousser()
            rendre()
            if pages_faites >= self._ocr_pages:
                # Ecart 131 : la fin du document (texte, cache, remplacement du PDF) est une unite sous
                # `_ocr_fichiers`, comme une page (contrat 4, invariant 7 et D1).
                prendre()

        def attendre():
            if not self._ocr_attendre(dest):
                return                               # arreter() leve ms.Annule a la page suivante
            self._ocr_poser_etat(dest, "en_cours")
            prendre()

        prendre()
        try:
            return ocr.traiter_document(dest, chemin, cfg, progres=progres, attendre=attendre,
                                        arreter=self._ocr_arret.is_set, refaire=bool(tache.get("refaire")))
        finally:
            rendre()

    def _ocr_prochaine(self, dest):
        """Premiere tache a traiter, relue du disque (ecart 130) : la boucle reprend tant qu'une tache reste en
        attente."""
        file = self._ocr_lire_file(dest)
        taches = [t for t in file.get("taches") or [] if isinstance(t, dict)]
        self._ocr_total = len(taches)
        self._ocr_faits = sum(1 for t in taches if t.get("etat") == "fait")
        return next((dict(t) for t in taches if t.get("etat") in ("attente", "en_cours")), None)

    def _ocr_boucle(self):
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        with self._ocr_verrou:
            file = ocr.charger_file(dest)
            file["etat"] = "en_cours"
            ocr.sauver_file(dest, file)
        origine = file.get("origine")
        self._ocr_origine = origine if origine in ocr.ORIGINES_FILE else "coffre"
        self._ocr_etat_fil = "en_cours"
        self._ocr_pousser(force=True)
        while True:
            tache = self._ocr_prochaine(dest)
            if tache is None:
                break
            chemin = tache.get("chemin") or ""
            if not chemin or not self._ocr_attendre(dest):
                return self._ocr_poser_etat(dest, "annulee")
            cfg = self._cfg()                        # ecart 132 : les reglages sont relus avant chaque document
            self._ocr_poser_etat(dest, "en_cours")
            tache = self._ocr_modifier_tache(dest, chemin, etat="en_cours",
                                             pages_faites=_entier(tache.get("pages_faites"), 0))
            if tache is None:                        # la tache a disparu de la file : on passe a la suivante
                continue
            self._ocr_courant = chemin
            self._ocr_page = _entier(tache.get("pages_faites"), 0)
            self._ocr_pages = _entier(tache.get("pages"), 0)
            self._ocr_pousser(force=True)
            message = ""
            try:
                resultat = self._ocr_document(tache, dest, cfg)
            except ms.Annule:
                self._ocr_modifier_tache(dest, chemin, etat="attente")
                return self._ocr_poser_etat(dest, "annulee")
            except ocr.ErreurOcr as e:
                message = str(e)
                self._ocr_modifier_tache(dest, chemin, etat="erreur", message=message)
            except ms.Erreur as e:
                message = str(e)
                self._ocr_modifier_tache(dest, chemin, etat="erreur", message=message)
            except Exception as e:
                message = ms.message_erreur(e, ACTION)
                self._ocr_modifier_tache(dest, chemin, etat="erreur", message=message)
            else:
                entree = (resultat or {}).get("entree") or {}
                message = (resultat or {}).get("message") or ""
                self._ocr_modifier_tache(dest, chemin, etat="fait",
                                         pages_faites=_entier(entree.get("pages"), tache.get("pages_faites", 0)),
                                         message=message)
                self._ocr_faits += 1
            self._ocr_journal(message)
            self._ocr_pousser(force=True)
        return self._ocr_poser_etat(dest, "terminee")

    def _ocr_executer(self):
        """Corps du fil : toute erreur imprevue finit dans erreurs.txt et laisse la file en etat `erreur`."""
        try:
            self._ocr_boucle()
        except Exception as e:
            self._ocr_etat_fil = "erreur"
            try:
                self._ocr_journal(ms.message_erreur(e, ACTION))
            except Exception:
                pass
            self._ocr_pousser(force=True)

    def _ocr_demarrer(self):
        """Demarre le fil si aucun ne tourne et si la file a des taches en attente. Vrai si demarre."""
        with self._ocr_verrou:
            if self._ocr_actif():
                return False
            cfg = self._cfg()
            dest = cfg.get("dest") or ""
            if not dest or not os.path.isdir(dest):
                return False
            file = ocr.charger_file(dest)
            if not any(t.get("etat") in ("attente", "en_cours") for t in file["taches"]):
                return False
            self._ocr_arret.clear()
            self._ocr_pause.clear()
            self._ocr_fil = threading.Thread(target=self._ocr_executer, name="moodlesync-textes", daemon=True)
            self._ocr_fil.start()
            return True

    # ------------------------------------------------------------------ formes de 4.2
    def _depot_etat(self, cfg):
        """Bloc `depot` de 4.2. Inerte ici : le depot est la tache R5 (`moodlesync/api_depot.py`), qui remplace
        cette methode dans son mixin. Personne d'autre ne fabrique ce bloc."""
        return {"etat": "inactif", "dossier_defaut": dossier_depot_defaut(), "dossier": "", "resultats": []}

    @_proteger(ACTION)
    def ocr_etat(self):
        """Etat complet de l'extraction (forme 4.2). L'arbre est construit une seule fois : ses compteurs sont ceux
        de `ocr_arbre` (4.3), sans relire le disque une deuxieme fois."""
        cfg = self._cfg()
        bloc = self._ocr_moteur(cfg)
        moteur = {cle: bloc.get(cle) for cle in ("present", "version", "source", "exe", "langues",
                                                 "langues_effectives", "repli", "message")}
        moteur["present"] = bool(moteur["present"])
        arbre = self._ocr_arbre(cfg)
        nombre, octets = ocr.originaux(cfg.get("dest") or "")
        return {"moteur": moteur,
                "occupe": self._ocr_actif(), "file": self._ocr_bloc_file(cfg),
                "compteurs": textes_arbre.compteurs(arbre),
                "reglages": {"ocr_langues": _reglage(cfg, "ocr_langues"),
                             "ocr_dpi": _entier(_reglage(cfg, "ocr_dpi"), 300),
                             "ocr_format": ocr.format_texte(cfg)},
                "originaux": {"nombre": nombre, "octets": octets},
                "depot": self._depot_etat(cfg)}

    @_proteger(ACTION)
    def ocr_detecter(self):
        """Relance la detection du moteur (bouton Detecter des reglages) et renvoie l'etat."""
        self._ocr_memo = None
        return self.ocr_etat()

    @_proteger(ACTION)
    def ocr_choisir_exe(self):
        """Boite de dialogue native : choix de tesseract.exe, enregistre dans `ocr_exe`."""
        import webview
        if self._fenetre is None:
            return {"erreur": _message("fenetre_fermee")}
        r = self._fenetre.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                            file_types=("Programme (tesseract.exe)", "Tous les fichiers (*.*)"))
        if not r:
            return {"annule": True}
        chemin = r[0] if isinstance(r, (list, tuple)) else r
        self._sauver_cfg(lambda c: c.update(ocr_exe=os.path.abspath(chemin)))
        self._ocr_memo = None
        return self.ocr_etat()

    @_proteger(ACTION)
    def ocr_installer(self):
        """Installe le moteur portable a la demande (I1, D6). Le clic sur « Installer » est l'accord explicite.
        Moteur deja detecte : l'etat complet, rien n'est telecharge. Succes : `ocr_etat()` (les deux pages ne se
        rafraichissent que sur une reponse qui porte `moteur`, ecart 238). Erreur : la phrase, telle quelle, ecrite
        aussi au journal. `{"annule": True}` est relaye. La progression part vers
        `window.textesInstallation({"recu", "total"})` et `ocr_installer_annuler` pose l'arret (ecart 245)."""
        if self._ocr_moteur(self._cfg(), frais=True).get("present"):
            return self.ocr_etat()
        self._install_arret.clear()
        r = ocr.installer_paquet(progres=lambda recu, total: self._js("textesInstallation", {"recu": recu, "total": total}),
                                 arreter=self._install_arret.is_set)
        if r.get("annule"):
            return {"annule": True}
        if not r.get("ok"):
            phrase = r.get("erreur") or _message("installation_echec")
            self._ocr_journal(phrase)
            return {"erreur": phrase}
        self._ocr_memo = None
        etat = self.ocr_etat()
        self._ocr_journal(_message("installation_faite"))
        return etat

    @_proteger(ACTION)
    def ocr_installer_annuler(self):
        """Bouton « Annuler » de l'installation : l'arret est pris au prochain bloc telecharge ou fichier decompresse,
        `ocr_installer` rend alors `{"annule": True}` et ne laisse aucun dossier."""
        self._install_arret.set()
        return {"ok": True}

    def _ocr_minutes(self, pages, cfg):
        """Fourchette de duree annoncee avant un lancement (O7, O18) : 15 secondes par page au moins,
        30 secondes au plus, avec un plancher d'une minute, arrondi par exces.

        La revue V7 (E-V7-4) mesure 14 s par page sur une machine calme et 79 s sous charge : l'ancienne
        fourchette (1 a 3 s par page) annoncait la moitie de la duree reelle pour 16 pages (1 a 2 minutes
        contre 222 s mesurees). Extraction sequentielle (ecart 126, decision de Maxence) : `ocr_threads`
        ne divise pas la duree (ecart 133).
        """
        secondes = max(0, _entier(pages, 0))
        return [max(1, math.ceil(secondes * 15 / 60)), max(1, math.ceil(secondes * 30 / 60))]

    # ------------------------------------------------------------------ 4.4 ocr_traiter
    def _ocr_a_traiter(self, noeud, refaire, en_file):
        """Vrai si le fichier de cet arbre doit entrer dans une nouvelle file (4.4).

        Sont ignores : les fichiers `traite` ou `a_verifier` sauf `refaire`, les fichiers `echec` sauf `refaire`
        (c'est le « Reessayer » de O4), et ceux qui sont deja dans la file.
        """
        cle = ocr._comparable(ocr._cle(noeud.get("chemin") or ""))
        if not cle or cle in en_file:
            return False
        statut = noeud.get("statut")
        if statut in ("en_attente", "en_cours"):
            return False
        if statut in ("traite", "a_verifier", "echec"):
            return bool(refaire)
        return True

    @_proteger(ACTION)
    def ocr_traiter(self, chemins, refaire=False, confirme=False):
        """Traite les documents choisis dans l'arborescence (contrat 4.4).

        `chemins` : chemins relatifs au coffre, chacun un fichier ou un dossier (un dossier vaut tous ses fichiers
        eligibles, recursivement ; doublons et fichiers deja couverts fusionnes, par `textes_arbre.fichiers_sous`).
        Sans `confirme`, rien n'est lance et rien n'est ecrit : la reponse porte la phrase de confirmation et les
        nombres exacts (documents, pages lues pour les seuls fichiers choisis, minutes, PDF a remplacer). Avec
        `confirme=True`, la file est ecrite (`origine = "coffre"`), l'executeur demarre, et la reponse porte le bloc
        `file` de 4.2. `refaire` retente aussi un document deja traite ou en echec (O4).
        """
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        if not dest or not os.path.isdir(dest):
            return {"erreur": _message("dossier_absent")}
        if not self._ocr_moteur(cfg).get("present"):
            return {"erreur": ocr.MESSAGES["moteur_absent"]}
        if self._ocr_actif():
            return {"erreur": _message("occupe")}
        refaire = bool(refaire)
        # Contrat 4 : tout chemin recu passe par `_ocr_confiner` (hors du coffre, composant cache, lien
        # symbolique sortant, octet nul). Un chemin refuse ne designe aucun document (E-V3-3).
        demandes = [chemin for chemin in (chemins if isinstance(chemins, list) else [])
                    if self._ocr_confiner(dest, chemin, cfg) is not None]
        if not demandes:
            return {"rien": True}
        with self._ocr_verrou:
            file = ocr.charger_file(dest)
        en_file = {ocr._comparable(ocr._cle(t.get("chemin") or "")) for t in file.get("taches") or []
                   if isinstance(t, dict) and t.get("etat") in ("attente", "en_cours")}
        noeuds = textes_arbre.fichiers_sous(dest, cfg, demandes)
        choisis = [n for n in noeuds if self._ocr_a_traiter(n, refaire, en_file)]
        if not choisis:
            return {"rien": True}
        avec_ecriture = bool(confirme)
        with self._ocr_verrou:
            file, documents, pages, remplacements = ocr.constituer_file_chemins(
                dest, cfg, [n["chemin"] for n in choisis], refaire=refaire, ecrire=avec_ecriture)
        if documents == 0 and not any(t.get("etat") == "attente" for t in file["taches"]):
            return {"rien": True}
        if not confirme:
            return {"confirmer": self._ocr_phrase_traitement(documents, pages, remplacements, cfg),
                    "documents": documents, "pages": pages, "minutes": self._ocr_minutes(pages, cfg),
                    "remplacements": remplacements}
        if not self._ocr_demarrer():
            return {"rien": True}
        return {"file": self._ocr_bloc_file(cfg)}

    def _ocr_phrase_traitement(self, documents, pages, remplacements, cfg):
        """Phrase de confirmation du lancement (5.5, O7) : documents, pages, duree, PDF remplaces."""
        mini, maxi = self._ocr_minutes(pages, cfg)
        return _message("confirmation_traitement", n=_nombre(documents, "document"),
                        p=_nombre(pages, "page"), m=mini, x=maxi, r=remplacements)

    @_proteger(ACTION)
    def ocr_pause(self):
        """Pause : l'extraction s'arrete apres la page en cours, son etat est conserve."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        if not dest:
            return {"file": self._ocr_bloc_file(cfg)}
        with self._ocr_verrou:
            file = ocr.charger_file(dest)
        if any(t.get("etat") in ("attente", "en_cours") for t in file["taches"]):
            self._ocr_pause.set()
            if not self._ocr_actif() and file.get("etat") != "pause":
                file["etat"] = "pause"
                with self._ocr_verrou:
                    ocr.sauver_file(dest, file)
        return {"file": self._ocr_bloc_file(cfg)}

    @_proteger(ACTION)
    def ocr_reprendre(self):
        """Reprise : leve la pause et l'arret, puis relance le fil si besoin."""
        self._ocr_pause.clear()
        self._ocr_arret.clear()
        self._ocr_demarrer()
        return {"file": self._ocr_bloc_file()}

    @_proteger(ACTION)
    def ocr_annuler(self):
        """Annulation : l'extraction s'arrete a la page suivante, les pages faites restent, la file reste en attente."""
        self._ocr_arret.set()
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        if dest and not self._ocr_actif():
            with self._ocr_verrou:
                file = ocr.charger_file(dest)
                if file.get("etat") in ("pause", "pause_sync", "en_cours") or any(
                        t.get("etat") in ("attente", "en_cours") for t in file["taches"]):
                    file["etat"] = "annulee"
                    ocr.sauver_file(dest, file)
        return {"file": self._ocr_bloc_file(cfg)}

    # ------------------------------------------------------------------ 4.1, 4.7
    @_proteger(ACTION)
    def ocr_ouvrir(self, chemin, page=None):
        """Ouvre un PDF du coffre avec le lecteur du systeme (4.1) : `{"ok": True}` ou une erreur.

        Le confinement de `_ocr_confiner` s'applique, la cle `page` est ignoree, et un chemin de dossier est refuse
        (`ocr_afficher` montre un dossier). Commande par liste d'arguments, jamais un shell : Windows `os.startfile`,
        macOS `open`, ailleurs `xdg-open` (decision de l'orchestrateur sur la revue V6, ecart E-V6-1)."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        if not dest:
            return {"erreur": _message("dossier_absent")}
        reel = self._ocr_confiner(dest, chemin, cfg)
        if reel is None or not os.path.isfile(reel):
            return {"erreur": _message("ouverture_refusee")}
        commande = commande_ouvrir(reel)
        try:
            if commande is None:
                os.startfile(reel)                    # Windows : le lecteur associe au fichier
            else:
                subprocess.Popen(commande, shell=False)
        except (OSError, ValueError, AttributeError):
            return {"erreur": _message("ouverture_refusee")}
        return {"ok": True}

    @_proteger(ACTION)
    def ocr_copier_texte(self, chemin):
        """Texte d'un document, tel qu'on le copie (4.7) : `{"texte", "caracteres", "pages"}`, sans front matter ni
        section « Pages à vérifier ». Un document sans texte : `{"erreur": MESSAGES["copie_vide"]}`."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        if not dest:
            return {"erreur": _message("dossier_absent")}
        reel = self._ocr_confiner(dest, chemin, cfg)
        if reel is None or not os.path.isfile(reel):
            return {"erreur": _message("ouverture_refusee")}
        rel = self._ocr_relatif(dest, reel)
        if not rel:
            return {"erreur": _message("ouverture_refusee")}
        texte, pages = ocr.texte_copiable(dest, rel)
        if not texte.strip():
            return {"erreur": _message("copie_vide")}
        return {"texte": texte, "caracteres": len(texte), "pages": _entier(pages, 0)}

    @_proteger(ACTION)
    def ocr_restaurer(self, chemin, confirme=False):
        """Restaure l'original d'un PDF traite (4.7, 3.3). Sans `confirme`, rien n'est fait : la reponse porte la
        phrase `confirmation_restauration`, ou `modifie_main` quand le PDF a ete retouche a la main depuis le
        traitement (invariant 8, E-V2-5 : c'est ce que repondait `ocr_pdf_restaurer`). Avec, `ocr.restaurer` remet
        la copie locale ou retelecharge depuis Moodle, et rend `{"ok": True}` ou la phrase d'erreur."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        if not dest:
            return {"erreur": _message("dossier_absent")}
        reel = self._ocr_confiner(dest, chemin, cfg)
        if reel is None or not os.path.isfile(reel):
            return {"erreur": _message("ouverture_refusee")}
        rel = self._ocr_relatif(dest, reel)
        if not rel:
            return {"erreur": _message("ouverture_refusee")}
        if not confirme:
            if ocr.pdf_modifie_main(dest, rel):
                return {"confirmer": _message("modifie_main")}
            return {"confirmer": _message("confirmation_restauration")}
        with self._ocr_exclusif():
            return ocr.restaurer(dest, rel, cfg, confirme=True)

    @_proteger(ACTION)
    def ocr_originaux_supprimer(self, confirme=False):
        """Libere toutes les copies d'originaux (4.7, O15). Sans `confirme` : `{"confirmer", "nombre", "octets"}`.
        Avec : `{"ok": True, "nombre", "octets"}`. Les documents concernes ne sont plus restaurables que par Moodle.
        """
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        nombre, octets = ocr.originaux(dest) if dest else (0, 0)
        if not confirme:
            return {"confirmer": _message("confirmation_originaux", n=_nombre(nombre, "copie"), o=_mo(octets)),
                    "nombre": nombre, "octets": octets}
        with self._ocr_exclusif():
            nombre, octets = ocr.supprimer_originaux(dest) if dest else (0, 0)
        return {"ok": True, "nombre": nombre, "octets": octets}

    # ------------------------------------------------------------------ reglages (4.1)
    @_proteger(ACTION)
    def ocr_regler(self, cle, valeur):
        """Liste blanche des reglages de l'extraction (contrat 4.1) : `ocr_exe`, `ocr_tessdata`, `ocr_langues`,
        `ocr_dpi`, `ocr_psm`, `ocr_max_mo`, `ocr_threads`, `ocr_batterie`, `ocr_format`. Toute autre cle est refusee.
        Renvoie `ocr_etat()`, ou une phrase d'erreur."""
        if not isinstance(cle, str) or cle not in REGLAGES_OCR:
            return {"erreur": _message("reglage_inconnu", cle=str(cle)[:40])}
        cfg = self._cfg()
        try:
            valeur = self._ocr_valeur(cle, valeur, cfg)
        except _Refus as e:
            return e.reponse
        except (TypeError, ValueError):
            return {"erreur": _message("valeur_invalide")}
        self._sauver_cfg(lambda c: c.update({cle: valeur}))
        self._ocr_memo = None
        return self.ocr_etat()

    def _ocr_valeur(self, cle, valeur, cfg):
        """Valeur validee d'un reglage ; leve _Refus (phrase d'erreur) ou ValueError."""
        if cle in ("ocr_exe", "ocr_tessdata"):
            texte = valeur if isinstance(valeur, str) else ""
            texte = texte.strip()
            if not texte:
                return ""
            existe = os.path.isfile(texte) if cle == "ocr_exe" else os.path.isdir(texte)
            if not existe:
                raise _Refus(_message("chemin_introuvable"))
            return os.path.abspath(texte)
        if cle == "ocr_langues":
            return _langues(valeur, self._ocr_moteur(cfg, frais=True))
        if cle == "ocr_dpi":
            return _borne(valeur, 150, 600)
        if cle == "ocr_psm":
            nombre = _borne(valeur, 1, 6)
            if nombre not in PSM:
                raise ValueError("mode de page")
            return nombre
        if cle == "ocr_max_mo":
            return _borne(valeur, 10, 2000)
        if cle == "ocr_threads":
            return _borne(valeur, 1, 4)
        if cle == "ocr_batterie":
            if valeur not in BATTERIES:
                raise ValueError("batterie")
            return valeur
        if cle == "ocr_format":
            if valeur not in ocr.FORMATS_TEXTE:
                raise ValueError("format")
            return valeur
        raise ValueError(cle)


class _Refus(Exception):
    """Valeur refusee avec sa reponse deja formee."""

    def __init__(self, phrase):
        super().__init__(phrase)
        self.reponse = {"erreur": phrase}


def _mo(octets):
    """Volume lisible des copies, arrondi au dixieme (contrat 6, ligne des copies)."""
    valeur = float(max(0, _entier(octets, 0)))
    for unite in ("o", "Ko", "Mo", "Go"):
        if valeur < 1024:
            return f"{valeur:.1f} {unite}" if unite != "o" else f"{int(valeur)} o"
        valeur /= 1024
    return f"{valeur:.1f} To"


def _borne(valeur, mini, maxi):
    if isinstance(valeur, bool):
        raise ValueError("entier")
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        raise ValueError("entier") from None
    if not mini <= nombre <= maxi:
        raise ValueError("borne")
    return nombre


def _langues(valeur, moteur):
    """Langues demandees, chacune detectee (contrat 3.2 : « inclus dans les langues detectees »)."""
    texte = valeur.strip().lower() if isinstance(valeur, str) else ""
    demandees = [x for x in texte.split("+") if x]
    if not demandees or not all(ocr.RE_LANGUE.match(x) for x in demandees):
        raise _Refus(ocr.MESSAGES["langue_manquante"])
    disponibles = {str(x).lower() for x in moteur.get("langues") or []}
    if not disponibles or any(x not in disponibles for x in demandees):
        raise _Refus(ocr.MESSAGES["langue_manquante"])
    return "+".join(demandees)
