"""Textes des cours : mixin de l'API de l'extraction locale du texte des documents (moodlesync/ocr.py).

Melange a application.Api : ces methodes sont appelees par la page (window.pywebview.api.<nom>). Chacune renvoie une
forme de la section 2.7 de docs/ocr-contrat.md, ou {"erreur": phrase lisible} : aucune exception ne sort et aucune
trace technique ne part vers la fenetre (invariant 9). Le reseau n'est appele nulle part ici, sauf par ocr.restaurer,
qui passe par moteur.py (invariant 6) : ce module n'importe aucune bibliotheque de reseau.

Verrous (contrat 3.2, invariant 7) :
- _ocr_verrou   (RLock, cache et file) : une lecture ou une ecriture de cache.json / file.json a la fois ;
- _ocr_fichiers (Lock) : une page, un apercu ou un remplacement a la fois ;
- _sync_veut    (Event) : une synchronisation attend, l'extraction cede entre deux pages (priorite, D1).
"""
import base64, io, os, threading, time
from contextlib import contextmanager

from . import moteur as ms, ocr
from .api_horaire import _proteger

ACTION = "Texte des cours"
# Meme phrase que application.OCCUPE, sans importer application (import circulaire) : seul le mixin la connait ici.
OCCUPE = "Une opération est déjà en cours : attends qu'elle se termine (ou annule-la)."
# Bornes de la mise en file automatique apres une synchronisation (D7, contrat 3.2).
LOT_DOCUMENTS = 50
LOT_PAGES = 500
# Page d'apercu : rendu a 150 DPI, ramene ensuite a 900 px de large au plus (D11).
DPI_APERCU = 150
LARGEUR_APERCU = 900

# Valeurs par defaut de config.json (plan 5.6) : charger_config ne les ecrit pas, le mixin les lit ainsi.
REGLAGES_OCR = {"ocr": False, "ocr_exe": "", "ocr_tessdata": "", "ocr_langues": "fra+eng", "ocr_dpi": 300,
                "ocr_psm": 3, "ocr_dossier": "Textes", "ocr_apres_sync": True, "ocr_max_mo": 300,
                "ocr_threads": 2, "ocr_batterie": "pause", "ocr_sortie_hors_coffre": False, "ocr_pdf": "aucun"}
MODES_PDF = ("aucun", "remplacer")
BATTERIES = ("pause", "continuer")
PSM = (1, 3, 4, 6)

# Phrases de la section 5 du contrat que ocr.MESSAGES ne porte pas encore (ecart 122, ocr.py hors perimetre de A1) :
# recopiees mot pour mot ici en attendant leur ajout dans ocr.MESSAGES, qui reprend la main des qu'elles y sont.
MESSAGES_TEXTE = {
    "consentement_remplacer": "Le PDF sera remplacé sur place par une version cherchable qui garde ses pages d'origine. "
                              "Aucune copie de l'original n'est conservée, tu pourras le retélécharger depuis Moodle.",
    "mode_indisponible": "Ce mode n'existe pas. Choisis « Aucun » ou « Remplacer par une version cherchable ».",
    "installation_indisponible": "L'installation automatique n'est pas encore disponible. Indique l'emplacement du "
                                 "moteur dans les réglages.",
}


def _message(code):
    """Phrase visible de la section 5 : ocr.MESSAGES d'abord, copie locale pour les trois codes manquants."""
    return ocr.MESSAGES.get(code) or MESSAGES_TEXTE[code]


def _reglage(cfg, cle):
    """Valeur d'un reglage, valeur par defaut du plan 5.6 si la cle manque ou est illisible."""
    valeur = cfg.get(cle, REGLAGES_OCR[cle])
    return REGLAGES_OCR[cle] if valeur is None else valeur


def _entier(valeur, defaut):
    """Entier positif ou nul ; toute autre valeur (dont un booleen) donne `defaut`."""
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        try:
            return int(valeur)
        except (TypeError, ValueError):
            return defaut
    return valeur


class ApiTextes:
    """Pas de __init__ : Api.__init__ appelle self._init_textes() (contrat 3.2)."""

    # ------------------------------------------------------------------ mise en place
    def _init_textes(self):
        self._ocr_verrou = threading.RLock()         # cache et file
        self._ocr_fichiers = threading.Lock()        # une page, un apercu ou un remplacement
        self._ocr_fil = None                         # fil daemon de l'extraction
        self._ocr_arret = threading.Event()          # annulation demandee
        self._ocr_pause = threading.Event()          # pause demandee par la page
        self._sync_veut = threading.Event()          # une synchronisation attend (D1)
        self._ocr_etat_fil = "inactive"              # etat pousse a la page
        self._ocr_courant = ""                       # chemin du document en cours
        self._ocr_page = 0                           # page en cours
        self._ocr_pages = 0                          # pages du document en cours
        self._ocr_threads = 2                        # pages en parallele, pour la duree restante (plan 5.8)
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
        """Bloc `file` de 2.7, derive de file.json (contrat 3.1 : la derivation appartient a ApiTextes)."""
        cfg = cfg or self._cfg()
        dest = cfg.get("dest") or ""
        file = ocr.charger_file(dest) if dest else {"etat": "inactive", "taches": []}
        taches = [t for t in file.get("taches") or [] if isinstance(t, dict)]
        en_cours = next((t for t in taches if t.get("etat") == "en_cours"), None)
        restants = sum(1 for t in taches if t.get("etat") in ("attente", "en_cours"))
        etat = file.get("etat") or "inactive"
        vivant = etat == "en_cours"
        return {"etat": etat,
                "document": (en_cours or {}).get("chemin") or (self._ocr_courant if vivant else ""),
                "page": _entier((en_cours or {}).get("pages_faites"), 0) if en_cours else (self._ocr_page if vivant else 0),
                "pages": _entier((en_cours or {}).get("pages"), 0) if en_cours else (self._ocr_pages if vivant else 0),
                "documents_faits": sum(1 for t in taches if t.get("etat") == "fait"),
                "documents_total": len(taches),
                "reprise": restants if etat in ("pause", "pause_sync", "annulee") else 0}

    def _ocr_compteurs(self, cfg):
        """Compteurs de 2.7 : le cache pour les documents prepares, file.json pour ce qui reste a preparer."""
        totaux = {"documents": 0, "pages": 0, "a_verifier": 0, "a_preparer": 0, "pages_a_preparer": 0,
                  "octets_texte": 0, "orphelins": 0}
        dest = cfg.get("dest") or ""
        if not dest or not os.path.isdir(dest):
            return totaux
        cache = ocr.charger_cache(dest)
        documents = cache.get("documents") or {}
        octets = 0
        for entree in documents.values():
            if not isinstance(entree, dict):
                continue
            totaux["pages"] += _entier(entree.get("pages"), 0)
            if entree.get("etat") != "ok" and not entree.get("verifie"):
                totaux["a_verifier"] += 1
            sortie = entree.get("sortie")
            if isinstance(sortie, str) and sortie:
                try:
                    octets += os.path.getsize(ocr._resoudre_sortie(dest, sortie))
                except OSError:
                    pass
        totaux["documents"] = len(documents)
        totaux["octets_texte"] = octets
        attente = [t for t in ocr.charger_file(dest).get("taches") or []
                   if isinstance(t, dict) and t.get("etat") == "attente"]
        totaux["a_preparer"] = len(attente)
        totaux["pages_a_preparer"] = sum(_entier(t.get("pages"), 0) for t in attente)
        try:
            totaux["orphelins"] = len(ocr._orphelins(dest, cache))
        except Exception:
            totaux["orphelins"] = 0
        return totaux

    def _ocr_resume(self, cfg=None):
        """Bloc `"ocr"` de sync_etat (sept cles, contrat 2.7). Ne leve jamais : il part avec la liste des cours."""
        try:
            cfg = cfg or self._cfg()
            compteurs = self._ocr_compteurs(cfg)
            return {"moteur": bool(self._ocr_moteur(cfg).get("present")), "active": bool(cfg.get("ocr")),
                    "a_preparer": compteurs["a_preparer"], "en_attente": compteurs["a_preparer"],
                    "pret": compteurs["documents"], "a_verifier": compteurs["a_verifier"],
                    "reprise": self._ocr_bloc_file(cfg)["reprise"]}
        except Exception:
            return {"moteur": False, "active": False, "a_preparer": 0, "en_attente": 0, "pret": 0,
                    "a_verifier": 0, "reprise": 0}

    def _ocr_pousser(self, force=False, message=""):
        """Progression vers la page (window.textesProgres), au plus quatre fois par seconde (contrat 3.2)."""
        maintenant = time.monotonic()
        if not force and maintenant - self._ocr_js < 0.25:
            return
        self._ocr_js = maintenant
        restant = None
        if self._ocr_etat_fil == "en_cours" and self._ocr_pages:
            restants = max(0, self._ocr_pages - self._ocr_page)
            if restants:
                threads = max(1, min(4, self._ocr_threads or 1))
                restant = max(1, round(restants * 2 / 60 / threads))
        self._js("textesProgres", {"etat": self._ocr_etat_fil, "document": self._ocr_courant,
                                   "page": self._ocr_page, "pages": self._ocr_pages,
                                   "documents_faits": self._ocr_faits, "documents_total": self._ocr_total,
                                   "restant_min": restant, "message": message})

    def _ocr_journal(self, texte):
        if texte:
            self._js("textesJournal", str(texte))

    # ------------------------------------------------------------------ fil d'extraction
    def _ocr_poser_etat(self, file, dest, etat):
        """Ecrit l'etat de la file s'il change, et le pousse a la page."""
        if file.get("etat") != etat:
            with self._ocr_verrou:
                file["etat"] = etat
                ocr.sauver_file(dest, file)
            self._ocr_etat_fil = etat
            self._ocr_pousser(force=True)

    def _ocr_attendre(self, file, dest):
        """Entre deux pages : cede a la synchronisation (pause_sync, reprise seule) et respecte la pause.
        Faux si l'annulation a ete demandee."""
        while True:
            if self._ocr_arret.is_set():
                return False
            if self._sync_veut.is_set():
                self._ocr_poser_etat(file, dest, "pause_sync")
                time.sleep(0.05)
                continue
            if self._ocr_pause.is_set():
                self._ocr_poser_etat(file, dest, "pause")
                time.sleep(0.05)
                continue
            return True

    def _ocr_document(self, tache, file, dest, cfg):
        """Un document, une page a la fois sous `_ocr_fichiers` : la synchronisation passe entre deux pages."""
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
            tache["pages_faites"] = _entier(evt.get("page"), tache.get("pages_faites", 0))
            self._ocr_page = tache["pages_faites"]
            self._ocr_pages = _entier(evt.get("pages"), tache.get("pages", 0))
            with self._ocr_verrou:
                ocr.sauver_file(dest, file)          # contrat 2.5 : la file est ecrite apres chaque page
            self._ocr_pousser()
            rendre()

        def attendre():
            if not self._ocr_attendre(file, dest):
                return                               # arreter() leve ms.Annule a la page suivante
            self._ocr_poser_etat(file, dest, "en_cours")
            self._ocr_etat_fil = "en_cours"
            prendre()

        prendre()
        try:
            return ocr.traiter_document(dest, tache["chemin"], cfg, progres=progres, attendre=attendre,
                                        arreter=self._ocr_arret.is_set, refaire=bool(tache.get("refaire")))
        finally:
            rendre()

    def _ocr_boucle(self):
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        self._ocr_threads = max(1, min(4, _entier(_reglage(cfg, "ocr_threads"), 2)))
        with self._ocr_verrou:
            file = ocr.charger_file(dest)
            file["etat"] = "en_cours"
            ocr.sauver_file(dest, file)
        self._ocr_etat_fil = "en_cours"
        self._ocr_faits = sum(1 for t in file["taches"] if t.get("etat") == "fait")
        self._ocr_total = len(file["taches"])
        self._ocr_pousser(force=True)
        for tache in list(file["taches"]):
            if tache.get("etat") not in ("attente", "en_cours"):
                continue
            if not self._ocr_attendre(file, dest):
                return self._ocr_poser_etat(file, dest, "annulee")
            self._ocr_poser_etat(file, dest, "en_cours")
            tache["etat"] = "en_cours"
            tache["pages_faites"] = _entier(tache.get("pages_faites"), 0)
            self._ocr_courant = tache["chemin"]
            self._ocr_page = tache["pages_faites"]
            self._ocr_pages = _entier(tache.get("pages"), 0)
            self._ocr_pousser(force=True)
            message = ""
            try:
                resultat = self._ocr_document(tache, file, dest, cfg)
            except ms.Annule:
                tache["etat"] = "attente"
                with self._ocr_verrou:
                    ocr.sauver_file(dest, file)
                return self._ocr_poser_etat(file, dest, "annulee")
            except ocr.ErreurOcr as e:
                tache["etat"] = "erreur"
                tache["message"] = str(e)
                message = str(e)
            except ms.Erreur as e:
                tache["etat"] = "erreur"
                tache["message"] = str(e)
                message = str(e)
            except Exception as e:
                tache["etat"] = "erreur"
                tache["message"] = ms.message_erreur(e, ACTION)
                message = tache["message"]
            else:
                tache["etat"] = "fait"
                entree = (resultat or {}).get("entree") or {}
                tache["pages_faites"] = _entier(entree.get("pages"), tache.get("pages_faites", 0))
                tache["message"] = (resultat or {}).get("message") or ""
                message = tache["message"]
                self._ocr_faits += 1
            with self._ocr_verrou:
                ocr.sauver_file(dest, file)
            self._ocr_journal(message)
            self._ocr_pousser(force=True)
        return self._ocr_poser_etat(file, dest, "terminee")

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

    # ------------------------------------------------------------------ mise en file automatique
    def _ocr_apres_sync(self, compte_rendu):
        """Contrat 3.2 : met en file ce que la synchronisation a ecrit, puis demarre l'extraction seule si `ocr` et
        `ocr_apres_sync` sont vrais, la fenetre ouverte, et le lot sous 50 documents et 500 pages (D7). Jamais sans
        fenetre : le mode --auto ne construit pas Api et ne passe donc jamais ici."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        try:
            with self._ocr_verrou:
                ajoutes = ocr.mettre_en_file_apres_sync(dest, cfg, compte_rendu) if dest else 0
        except Exception as e:
            ms.message_erreur(e, ACTION)
            ajoutes = 0
        if not (dest and cfg.get("ocr") and cfg.get("ocr_apres_sync", True)):
            return {"a_preparer": ajoutes}
        if self._fenetre is None or self._ocr_actif():
            return {"a_preparer": ajoutes}
        if not self._ocr_moteur(cfg).get("present"):
            return {"a_preparer": ajoutes}
        file = ocr.charger_file(dest)
        attente = [t for t in file["taches"] if t.get("etat") == "attente"]
        pages = sum(_entier(t.get("pages"), 0) for t in attente)
        if attente and len(attente) <= LOT_DOCUMENTS and pages <= LOT_PAGES:
            self._ocr_demarrer()
        return {"a_preparer": ajoutes}

    # ------------------------------------------------------------------ formes de 2.7
    @_proteger(ACTION)
    def ocr_etat(self):
        """Etat complet de l'extraction (forme 2.7)."""
        cfg = self._cfg()
        bloc = self._ocr_moteur(cfg)
        moteur = {cle: bloc.get(cle) for cle in ("present", "version", "source", "exe", "langues",
                                                 "langues_effectives", "repli", "message")}
        moteur["present"] = bool(moteur["present"])
        return {"moteur": moteur, "active": bool(cfg.get("ocr")),
                "mode_pdf": _reglage(cfg, "ocr_pdf") if _reglage(cfg, "ocr_pdf") in MODES_PDF else "aucun",
                "occupe": self._ocr_actif(), "file": self._ocr_bloc_file(cfg),
                "compteurs": self._ocr_compteurs(cfg),
                "reglages": {"ocr_langues": _reglage(cfg, "ocr_langues"), "ocr_dpi": _entier(_reglage(cfg, "ocr_dpi"), 300)}}

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
            return {"erreur": "La fenêtre n'est pas encore ouverte : réessaie dans un instant."}
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
        """Reserve au paquet portable (2.6) : repond que l'installation n'est pas disponible (D6)."""
        return {"erreur": _message("installation_indisponible")}

    def _ocr_exemple(self):
        """Forme 2.7 d'un exemple : aucun scan, ou moteur absent. Le document de demonstration appartient a U3,
        l'image reste vide et la page affiche son exemple statique."""
        return {"image": "", "largeur": 0, "hauteur": 0, "texte": "", "confiance": None, "qualite": "vide",
                "source": "vide", "chemin": "", "nom": "", "page": 1, "exemple": True}

    def _ocr_scan(self, dest, cfg):
        """Premier document eligible qui demande une reconnaissance (scan, PDF mixte, image), sinon \"\"."""
        for rel in ocr._candidats(dest, cfg):
            try:
                if ocr._a_reconnaitre(ocr._absolu(dest, rel)):
                    return rel
            except Exception:
                continue
        return ""

    @_proteger(ACTION)
    def ocr_apercu(self, chemin="", page=1):
        """Une page d'un document, pour l'essai « A quoi ca sert ? » (forme 2.7). N'ecrit rien, ne met rien en file."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        if not self._ocr_moteur(cfg).get("present"):
            return self._ocr_exemple()
        rel = ocr._cle(chemin or "")
        if rel and (".." in rel.split("/") or not os.path.isfile(ocr._absolu(dest, rel))):
            return {"erreur": ocr.MESSAGES["corrompu"]}
        if not rel:
            rel = self._ocr_scan(dest, cfg)
            if not rel:
                return self._ocr_exemple()
        absolu = ocr._absolu(dest, rel)
        with self._ocr_fichiers:
            nb = ocr._nb_pages(absolu)
            numero = max(1, min(nb, _entier(page, 1) or 1))
            image = ocr.rendre_page(absolu, numero, DPI_APERCU)
            reglages = ocr.reglages_depuis(cfg)
            resultat = ocr.extraire_page(absolu, numero, reglages, exe=self._ocr_moteur(cfg).get("exe") or "")
        image = image.convert("L")
        largeur, hauteur = image.size
        if largeur > LARGEUR_APERCU:
            hauteur = max(1, round(hauteur * LARGEUR_APERCU / largeur))
            largeur = LARGEUR_APERCU
            image = image.resize((largeur, hauteur))
        tampon = io.BytesIO()
        image.save(tampon, format="PNG")
        return {"image": "data:image/png;base64," + base64.b64encode(tampon.getvalue()).decode("ascii"),
                "largeur": largeur, "hauteur": hauteur, "texte": resultat.get("texte") or "",
                "confiance": resultat.get("confiance"), "qualite": ocr.classer(resultat.get("confiance")),
                "source": resultat.get("source") or "vide", "chemin": rel, "nom": os.path.basename(rel),
                "page": numero, "exemple": False}

    def _ocr_minutes(self, pages, cfg):
        """Fourchette de duree, ordre de grandeur du plan 5.8 : 1 a 3 secondes par page, `ocr_threads` pages."""
        threads = max(1, min(4, _entier(_reglage(cfg, "ocr_threads"), 2)))
        secondes = max(0, _entier(pages, 0)) / threads
        mini = max(1, round(secondes / 60))
        return [mini, max(mini + 1, round(secondes * 3 / 60))]

    def _ocr_phrase_lot(self, documents, pages, cfg):
        """Fenetre de confirmation du premier passage long (plan 3.4)."""
        mini, maxi = self._ocr_minutes(pages, cfg)
        return (f"{documents} documents, environ {pages} pages. Environ {mini} à {maxi} minutes. "
                "Tu peux continuer à utiliser MoodleSync, mettre en pause ou fermer : "
                "la prochaine fois, ça reprend où tu t'es arrêté.")

    @_proteger(ACTION)
    def ocr_lancer(self, portee="sans_texte", refaire=False, confirme=False):
        """Constitue la file de la portee (2.5) et demarre l'extraction. Au-dela de 50 documents ou 500 pages, une
        confirmation avec la duree est demandee (plan 3.4, D7) ; `confirme=True` la donne."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        if not dest or not os.path.isdir(dest):
            return {"erreur": "Le dossier de rangement n'existe pas encore : lance une synchronisation d'abord."}
        if self._ocr_actif():
            return {"erreur": OCCUPE}
        portee = portee if isinstance(portee, str) and portee else "sans_texte"
        if portee == "sans_texte" and not self._ocr_moteur(cfg).get("present"):
            return {"erreur": ocr.MESSAGES["moteur_absent"]}
        with self._ocr_verrou:
            file = ocr.constituer_file(dest, cfg, portee, bool(refaire))
        attente = [t for t in file["taches"] if t.get("etat") == "attente"]
        if not attente:
            return {"rien": True}
        documents = len(attente)
        pages = sum(_entier(t.get("pages"), 0) for t in attente)
        if (documents > LOT_DOCUMENTS or pages > LOT_PAGES) and not confirme:
            return {"confirmer": self._ocr_phrase_lot(documents, pages, cfg), "documents": documents,
                    "pages": pages, "minutes": self._ocr_minutes(pages, cfg)}
        if not self._ocr_demarrer():
            return {"rien": True}
        return {"file": self._ocr_bloc_file(cfg)}

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

    @_proteger(ACTION)
    def ocr_pdf_restaurer(self, chemin, confirme=False):
        """Restaure l'original d'un PDF cherchable (invariant 13). Relaie la reponse de ocr.restaurer telle quelle :
        {"ok": True, "pages": n} ou {"confirmer": MESSAGES["modifie_main"]} ; les erreurs deviennent une phrase."""
        cfg = self._cfg()
        with self._ocr_exclusif():
            return ocr.restaurer(cfg.get("dest") or "", cfg, chemin, confirme=bool(confirme))

    # ------------------------------------------------------------------ reglages
    @_proteger(ACTION)
    def ocr_regler(self, cle, valeur, confirme=False):
        """Liste blanche des reglages de l'extraction (contrat 3.2, plan 5.6). Renvoie ocr_etat(), une phrase
        d'erreur, ou {"confirmer": ...} pour le mode `remplacer` (consentement separe, D3)."""
        if cle not in REGLAGES_OCR:
            return {"erreur": f"Réglage inconnu : {cle}"}
        cfg = self._cfg()
        try:
            valeur = self._ocr_valeur(cle, valeur, cfg)
        except _Refus as e:
            return e.reponse
        except (TypeError, ValueError):
            return {"erreur": "Valeur invalide."}
        if cle == "ocr_pdf":
            if valeur not in MODES_PDF:
                return {"erreur": _message("mode_indisponible")}
            if valeur == "remplacer" and _reglage(cfg, "ocr_pdf") != "remplacer" and not confirme:
                return {"confirmer": _message("consentement_remplacer")}
        self._sauver_cfg(lambda c: c.update({cle: valeur}))
        self._ocr_memo = None
        return self.ocr_etat()

    def _ocr_valeur(self, cle, valeur, cfg):
        """Valeur validee d'un reglage ; leve _Refus (phrase d'erreur) ou ValueError."""
        if cle in ("ocr", "ocr_apres_sync", "ocr_sortie_hors_coffre"):
            return _booleen(valeur)
        if cle in ("ocr_exe", "ocr_tessdata"):
            texte = valeur if isinstance(valeur, str) else ""
            texte = texte.strip()
            if not texte:
                return ""
            existe = os.path.isfile(texte) if cle == "ocr_exe" else os.path.isdir(texte)
            if not existe:
                raise _Refus("Indique un chemin qui existe sur cet ordinateur.")
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
        if cle == "ocr_dossier":
            return _dossier(valeur, cfg)
        if cle == "ocr_pdf":
            return valeur if isinstance(valeur, str) else ""
        raise ValueError(cle)


class _Refus(Exception):
    """Valeur refusee avec sa reponse deja formee."""

    def __init__(self, phrase):
        super().__init__(phrase)
        self.reponse = {"erreur": phrase}


def _booleen(valeur):
    if isinstance(valeur, bool):
        return valeur
    raise ValueError("booleen")


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


def _dossier(valeur, cfg):
    """Nom simple de dossier de sortie : ni separateur, ni `..`, ni caractere interdit, et jamais un dossier de cours."""
    nom = ms.nfc(valeur.strip()) if isinstance(valeur, str) else ""
    if not nom or nom in (".", "..") or ms.ILLEGAL.search(nom) or "/" in nom or "\\" in nom or ".." in nom:
        raise ValueError("dossier")
    cours = cfg.get("cours") if isinstance(cfg.get("cours"), dict) else {}
    pris = set()
    for choix in cours.values():
        dossier = choix.get("dossier") if isinstance(choix, dict) else None
        if isinstance(dossier, str) and dossier.strip():
            parties = ocr._cle(dossier).split("/")
            pris.add(ms.cle_nom(parties[0]))
            pris.add(ms.cle_nom(ocr._cle(dossier)))
    if ms.cle_nom(nom) in pris:
        raise _Refus("Ce nom est déjà celui d'un cours : choisis un autre dossier.")
    return nom
