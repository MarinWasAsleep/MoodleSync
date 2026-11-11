"""Depot de fichiers hors Moodle : mixin de l'API de « Deposer des fichiers » (contrat 4.6, tache R5).

Melange a application.Api comme ApiTextes : ces methodes sont appelees par la page
(window.pywebview.api.<nom>). Chacune renvoie une forme du contrat 4.6, ou {"erreur": phrase lisible} : aucune
exception ne sort et aucune trace technique ne part vers la fenetre.

Le dossier de depot choisi sert de mini-coffre (O12) : la copie du fichier y vit, le cache de reconnaissance vit
dans `<dossier>/.moodlesync-ocr/` (marque cache sous Windows), et tout le travail passe par
`ocr.traiter_document(dest=dossier, garder_original=False)`. Rien n'est ajoute a `ocr.py`.

Invariant 4 de la refonte : un fichier depose n'est jamais touche a sa source. Le fichier est lu une fois pour
etre copie, jamais ouvert en ecriture, jamais deplace.
"""
import os, shutil, threading, time

from . import moteur as ms, ocr
from .api_horaire import _proteger
from .api_textes import _entier, _message, _nombre, dossier_depot_defaut

ACTION = "Depot de fichiers"
CACHE = ".moodlesync-ocr"
PREFIXE_ETAT = "depot:"
ATTRIBUT_CACHE = 0x2                        # FILE_ATTRIBUTE_HIDDEN (Windows)
# Phrase de confirmation du depot (fixtures/depot.json). 5.5 ne la nomme pas dans ocr.MESSAGES : elle est ecrite
# ici, voir l'ecart E-R5-1 du journal.
PHRASE_CONFIRMATION = ("{n}, environ {p}, {m} à {x} minutes. Les résultats seront rangés dans le dossier "
                       "choisi ; tes fichiers d'origine ne sont pas modifiés.")
MOTIFS = ("difficile", "vide", "illisible", "verification", "ecriture", "erreur")


def cacher_cache(dossier):
    """Marque le cache de reconnaissance du dossier de depot comme cache sous Windows (O12).

    `SetFileAttributesW` par `ctypes`, garde par `os.name == "nt"` : sous macOS et Linux le nom commence deja par
    un point, et l'appel n'aurait pas de sens. Rend vrai si l'attribut a ete pose. Ne leve jamais : un echec laisse
    simplement le dossier visible.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.SetFileAttributesW(ctypes.c_wchar_p(dossier), ATTRIBUT_CACHE))
    except Exception:
        return False


def nom_libre(dossier, nom):
    """Nom de fichier libre dans `dossier` : le nom demande, sinon « (2) », « (3) » avant l'extension (4.6).

    Libre veut dire libre pour le PDF **et pour son texte** : un `<nom>.pdf.md` ou `<nom>.pdf.txt` deja present,
    meme sans son PDF, occupe le nom (E-V4-1). Ce fichier est le texte de l'etudiant, seul, et la refonte ne le
    supprime ni ne l'ecrase jamais (invariant 3) : le depot prend « (2) ».
    """
    base, extension = os.path.splitext(nom)
    candidat, n = nom, 1
    while any(os.path.exists(os.path.join(dossier, candidat + suffixe)) for suffixe in ("", ".md", ".txt")):
        n += 1
        candidat = f"{base} ({n}){extension}"
    return candidat


def chemins_deposes(event):
    """Chemins complets d'un evenement `drop` de pywebview (O16), dans l'ordre, sans doublon.

    pywebview pose `pywebviewFullPath` sur chaque fichier de `dataTransfer.files` quand un gestionnaire DOM ecoute
    le depot (`webview/util.py`, branche `pywebviewEventHandler`, et `webview/dom/element.py`, qui tient
    `_dnd_state["num_listeners"]`). Un fichier sans ce champ n'a pas de chemin connu : il n'est pas invente.
    """
    transfert = (event or {}).get("dataTransfer") if isinstance(event, dict) else None
    fichiers = transfert.get("files") if isinstance(transfert, dict) else None
    sortie = []
    for fichier in fichiers if isinstance(fichiers, list) else []:
        chemin = fichier.get("pywebviewFullPath") if isinstance(fichier, dict) else None
        if isinstance(chemin, str) and chemin and os.path.isabs(chemin) and chemin not in sortie:
            sortie.append(chemin)
    return sortie


def _sans_effet(event):
    """Garde du glisser-deposer : annule le comportement par defaut du navigateur, sans rien lire ni deposer.

    Posee sur `body` par `_depot_installer` (E-V4-3) : lacher un PDF a cote de la zone de depot n'ouvre pas le
    fichier dans la fenetre. Rend None.
    """
    return None


class ApiDepot:
    """Pas de __init__ : Api.__init__ appelle self._init_depot() apres self._init_textes()."""

    # ------------------------------------------------------------------ mise en place
    def _init_depot(self):
        self._depot_verrou = threading.Lock()        # un depot a la fois
        self._depot_fil = None                       # fil daemon du depot en cours
        self._depot_etat_bloc = "inactif"            # 4.2 : inactif, en_cours, termine
        self._depot_dossier = ""                     # dossier du dernier depot
        self._depot_resultats = []                   # 4.6 : resultats du dernier depot
        self._depot_total = 0                        # documents a traiter du depot en cours
        self._depot_instant = 0.0                    # derniere emission de progression
        self._depot_dom = False                      # gestionnaire DOM de depot pose (O16)

    def _depot_actif(self):
        return bool(self._depot_fil is not None and self._depot_fil.is_alive())

    def _depot_etat(self, cfg):
        """Bloc `depot` de 4.2 : le dernier depot et son dossier. Personne d'autre ne fabrique ce bloc."""
        return {"etat": self._depot_etat_bloc, "dossier_defaut": dossier_depot_defaut(),
                "dossier": self._depot_dossier, "resultats": [dict(r) for r in self._depot_resultats]}

    def _depot_pousser(self, document="", page=0, pages=0, force=False):
        """Progression du depot vers la page (window.textesProgres), au plus quatre fois par seconde.

        Meme forme que `_ocr_pousser` (5.2) avec `origine = "depot"` (4.2) : la coque n'a qu'un seul point d'entree.
        Les compteurs sont ceux du depot et non ceux de la file du coffre : un depot ne touche pas `file.json`.
        """
        maintenant = time.monotonic()
        if not force and maintenant - self._depot_instant < 0.25:
            return
        self._depot_instant = maintenant
        restant = None
        if pages and page < pages:
            restant = max(1, round((pages - page) * 2 / 60))
        self._js("textesProgres", {"etat": self._depot_etat_bloc, "origine": "depot", "document": document,
                                   "page": _entier(page, 0), "pages": _entier(pages, 0),
                                   "documents_faits": len(self._depot_resultats), "documents_total": self._depot_total,
                                   "restant_min": restant, "message": ""})

    # ------------------------------------------------------------------ 4.6 : trois methodes
    @_proteger(ACTION)
    def ocr_choisir_fichiers(self):
        """Boite de dialogue native, plusieurs fichiers : `{"fichiers": [<chemin absolu>, ...]}` ou `{"annule": True}`.

        Les chemins absolus ne sortent de cette methode que pour le depot (4.6) : l'interface les remet tels quels
        a `ocr_deposer`.
        """
        import webview
        if self._fenetre is None:
            return {"erreur": _message("fenetre_fermee")}
        r = self._fenetre.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True,
                                             file_types=("Documents PDF (*.pdf)", "Tous les fichiers (*.*)"))
        if not r:
            return {"annule": True}
        choisis = r if isinstance(r, (list, tuple)) else [r]
        fichiers = [os.path.abspath(x) for x in choisis if isinstance(x, str) and x.strip()]
        if not fichiers:
            return {"annule": True}
        return {"fichiers": fichiers}

    @_proteger(ACTION)
    def ocr_choisir_dossier_depot(self):
        """Boite de dialogue native de dossier, ouverte sur `depot.dossier_defaut` : `{"dossier": ...}` ou annule."""
        import webview
        if self._fenetre is None:
            return {"erreur": _message("fenetre_fermee")}
        depart = self._depot_dossier or dossier_depot_defaut()
        if not os.path.isdir(depart):
            depart = os.path.expanduser("~")     # dossier par defaut pas encore cree : on ouvre sur le foyer
        r = self._fenetre.create_file_dialog(webview.FOLDER_DIALOG, directory=depart)
        if not r:
            return {"annule": True}
        choix = r[0] if isinstance(r, (list, tuple)) else r
        if not isinstance(choix, str) or not choix.strip():
            return {"annule": True}
        return {"dossier": os.path.normpath(os.path.abspath(choix))}

    @_proteger(ACTION)
    def ocr_deposer(self, fichiers, dossier, confirme=False):
        """Depot de fichiers hors Moodle (4.6).

        `fichiers` : chemins absolus. Sans `confirme`, rien n'est copie ni ecrit : la reponse porte la phrase de
        confirmation, les nombres (documents, pages, minutes) et les refus avec leur phrase. Avec `confirme=True`,
        le dossier est cree s'il manque, les fichiers sont copies un a un puis traites par `traiter_document`
        (`garder_original=False`), et la reponse porte le bloc `depot` (etat `en_cours`).
        """
        cfg = self._cfg()
        if not self._ocr_moteur(cfg).get("present"):
            return {"erreur": ocr.MESSAGES["moteur_absent"]}
        if self._depot_actif() or self._depot_verrou.locked() or self._ocr_actif():
            return {"erreur": _message("occupe")}
        items = self._depot_trier(fichiers, cfg)
        if not items:
            return {"annule": True}
        cible = self._depot_cible(dossier)
        retenus = [i for i in items if i["genre"] == "fichier"]
        refuses = [i for i in items if i["genre"] == "refus"]
        pages = sum(i["pages"] for i in retenus)
        if not confirme:
            mini, maxi = self._ocr_minutes(pages, cfg)
            return {"confirmer": PHRASE_CONFIRMATION.format(n=_nombre(len(retenus), "document"),
                                                            p=_nombre(pages, "page"), m=mini, x=maxi),
                    "documents": len(retenus), "pages": pages, "minutes": [mini, maxi],
                    "refuses": [{"nom": i["nom"], "raison": i["raison"]} for i in refuses]}
        try:
            os.makedirs(cible, exist_ok=True)
        except OSError as e:
            return {"erreur": ms.message_erreur(e, ACTION)}
        if not self._depot_verrou.acquire(blocking=False):
            return {"erreur": _message("occupe")}
        self._depot_dossier = cible
        self._depot_resultats = []
        self._depot_total = len(retenus)
        self._depot_etat_bloc = "en_cours"
        cacher_cache(os.path.join(cible, CACHE))
        self._ocr_arret.clear()
        try:
            self._depot_fil = threading.Thread(target=self._depot_executer, args=(items, cible, cfg),
                                               name="moodlesync-depot", daemon=True)
            self._depot_fil.start()
        except Exception as e:
            self._depot_verrou.release()
            self._depot_etat_bloc = "inactif"
            return {"erreur": ms.message_erreur(e, ACTION)}
        self._depot_pousser(force=True)
        return {"depot": self._depot_etat(cfg)}

    # ------------------------------------------------------------------ tri et refus (4.6)
    def _depot_cible(self, dossier):
        """Dossier de depot absolu : celui recu, sinon « Documents déposés » sur le Bureau (4.2)."""
        brut = dossier.strip() if isinstance(dossier, str) else ""
        if not brut:
            return dossier_depot_defaut()
        return os.path.normpath(os.path.abspath(os.path.expanduser(brut)))

    def _depot_trier(self, fichiers, cfg):
        """Liste des entrees du depot, dans l'ordre recu : un refus (4.6) ou un fichier a traiter."""
        liste = fichiers if isinstance(fichiers, (list, tuple)) else []
        items = []
        for brut in liste:
            if not isinstance(brut, str) or not brut.strip():
                continue
            chemin = os.path.abspath(os.path.expanduser(brut.strip()))
            refus = self._depot_refus(chemin, cfg)
            if refus is not None:
                nom, motif, raison = refus
                items.append({"genre": "refus", "nom": nom, "motif": motif, "raison": raison})
            else:
                items.append({"genre": "fichier", "source": chemin, "nom": os.path.basename(chemin),
                              "pages": self._depot_pages(chemin)})
        return items

    def _depot_refus(self, chemin, cfg):
        """(nom, motif, phrase) si le fichier est refuse, sinon None.

        U8 : seuls les PDF. Puis introuvable, trop gros (`ocr_max_mo`), protege par un mot de passe. Aucun refus ne
        copie quoi que ce soit : le fichier d'origine n'est meme pas ouvert en ecriture.
        """
        nom = os.path.basename(chemin)
        if not ocr._est_pdf(nom):
            return nom, "depot_pas_pdf", ocr.MESSAGES["depot_pas_pdf"]
        if not os.path.isfile(chemin):
            return nom, "introuvable", ocr.MESSAGES["chemin_introuvable"]
        mo = _entier(cfg.get("ocr_max_mo"), 300)
        try:
            if os.path.getsize(chemin) > mo * 1024 * 1024:
                return nom, "trop_gros", ocr.MESSAGES["trop_gros"].format(mo=mo)
        except OSError:
            return nom, "introuvable", ocr.MESSAGES["chemin_introuvable"]
        try:
            if ocr.controler_pdf(chemin)["protege"]:
                return nom, "protege", ocr.MESSAGES["protege"]
        except ocr.ErreurOcr as e:
            return nom, "corrompu", str(e)
        except OSError:
            return nom, "introuvable", ocr.MESSAGES["chemin_introuvable"]
        return None

    def _depot_pages(self, chemin):
        """Nombre de pages lu pour la phrase de confirmation, 0 s'il est inconnu (le dialogue n'invente rien)."""
        try:
            return ocr._nb_pages(chemin)
        except (ocr.ErreurOcr, OSError):
            return 0

    # ------------------------------------------------------------------ travail du depot
    def _depot_executer(self, items, dossier, cfg):
        """Corps du fil : chaque fichier de la liste, dans l'ordre, puis l'etat `termine`.

        Une annulation (`_ocr_arret`) arrete le lot a l'unite suivante et laisse les fichiers suivants non traites :
        aucun resultat n'est invente pour eux.
        """
        try:
            for item in items:
                if self._ocr_arret.is_set():
                    break
                if item["genre"] == "refus":
                    resultat = {"nom": item["nom"], "statut": "refuse", "motif": item["motif"],
                                "sortie_pdf": "", "sortie_texte": "", "pages": 0}
                else:
                    resultat = self._depot_un(item, dossier, cfg)
                if resultat is None:                 # annulation : rien n'a ete laisse pour ce fichier
                    break
                self._depot_resultats.append(resultat)
                self._depot_pousser(document=resultat["nom"], force=True)
        except Exception as e:
            try:
                ms.message_erreur(e, ACTION)
            except Exception:
                pass
        finally:
            self._depot_etat_bloc = "termine"
            if self._depot_verrou.locked():
                self._depot_verrou.release()
            self._depot_pousser(force=True)

    def _depot_un(self, item, dossier, cfg):
        """Un fichier : copie, inscription dans le mini-coffre, traitement, resultat de 4.6 (None si annule)."""
        source, nom = item["source"], item["nom"]
        rel = ocr._cle(nom_libre(dossier, nom))
        copie = os.path.join(dossier, *rel.split("/"))
        # `nom_libre` garantit que ni le PDF ni son texte n'existent : ce que l'effacement trouvera est donc de ce
        # depot. La verification est refaite ici, au cas ou un autre programme aurait ecrit entre les deux.
        texte_preexistant = os.path.exists(ocr.chemin_texte(dossier, rel, cfg)[0])
        try:
            shutil.copyfile(source, copie)       # copie du contenu, jamais un deplacement ni un changement a la source
        except OSError as e:
            try:
                ms.message_erreur(e, ACTION)
            except Exception:
                pass
            return self._depot_resultat(nom, "echec", "ecriture", 0)
        empreinte = None
        try:
            empreinte = ocr.identite(copie)["empreinte"]
            self._depot_inscrire(dossier, rel)
            resultat = ocr.traiter_document(dossier, rel, cfg, progres=lambda evt: self._depot_page(evt, nom),
                                            arreter=self._ocr_arret.is_set, garder_original=False)
        except ms.Annule:
            self._depot_effacer(dossier, rel, empreinte, cfg, texte_preexistant)
            return None
        except ocr.ErreurOcr as e:
            self._depot_effacer(dossier, rel, empreinte, cfg, texte_preexistant)
            motif = e.code if e.code in MOTIFS else "erreur"
            return self._depot_resultat(nom, "echec", motif, item["pages"])
        except OSError as e:
            try:
                ms.message_erreur(e, ACTION)
            except Exception:
                pass
            self._depot_effacer(dossier, rel, empreinte, cfg, texte_preexistant)
            return self._depot_resultat(nom, "echec", "ecriture", item["pages"])
        except Exception as e:
            try:
                ms.message_erreur(e, ACTION)
            except Exception:
                pass
            self._depot_effacer(dossier, rel, empreinte, cfg, texte_preexistant)
            return self._depot_resultat(nom, "echec", "erreur", item["pages"])
        statut = (resultat or {}).get("statut") or "echec"
        if statut == "echec":
            # Invariant 2 : un echec ne laisse rien dans le dossier pour ce fichier.
            self._depot_effacer(dossier, rel, empreinte, cfg, texte_preexistant)
            return self._depot_resultat(nom, "echec", (resultat or {}).get("motif") or "erreur", item["pages"])
        entree = (resultat or {}).get("entree") or {}
        pages = entree.get("pages")
        return {"nom": nom, "statut": statut, "motif": "", "sortie_pdf": copie,
                "sortie_texte": ocr.chemin_texte(dossier, rel, cfg)[0],
                "pages": pages if isinstance(pages, int) and not isinstance(pages, bool) else item["pages"]}

    def _depot_resultat(self, nom, statut, motif, pages):
        return {"nom": nom, "statut": statut, "motif": motif, "sortie_pdf": "", "sortie_texte": "",
                "pages": _entier(pages, 0)}

    def _depot_page(self, evt, nom):
        """Progression d'un document (contrat 2.5) : page lue et pages du document, sans toucher a `file.json`."""
        self._depot_pousser(document=nom, page=_entier(evt.get("page"), 0), pages=_entier(evt.get("pages"), 0))

    def _depot_inscrire(self, dossier, rel):
        """Inscrit la copie dans l'etat du dossier de depot (`.moodlesync.json`, O12).

        `fabriquer_pdf_cherchable` refuse un PDF absent de cet etat (`non_suivi`) : sans cette inscription, tout PDF
        depose a reconnaitre echouerait en `verification` (ecart E-R2-1 de R2). La cle ne vient pas de Moodle : elle
        porte le prefixe `depot:` et une date nulle, donc jamais de reprise de mise a jour.
        """
        etat = ms.charger_etat(dossier)
        etat[PREFIXE_ETAT + rel] = {"chemin": rel, "t": 0}
        ms.sauver_etat(dossier, etat)

    def _depot_effacer(self, dossier, rel, empreinte, cfg, texte_preexistant=False):
        """Efface toute trace d'une copie dans le dossier de depot : copie, texte, temporaire, cache, etat.

        **Seulement ce que ce depot a cree** (E-V4-1) : la copie et son temporaire sont de lui, puisque `nom_libre`
        a verifie que le nom etait libre. Le texte, lui, n'est efface que s'il n'existait pas avant ce fichier
        (`texte_preexistant` faux) : un texte de l'etudiant, laisse seul dans le dossier, ne part jamais
        (invariant 3). Ne leve jamais : un effacement impossible est signale a `erreurs.txt`.
        """
        copie = os.path.join(dossier, *rel.split("/"))
        a_effacer = [copie, copie + ".ocr.part"]
        if not texte_preexistant:
            a_effacer.insert(1, ocr.chemin_texte(dossier, rel, cfg)[0])
        for chemin in a_effacer:
            try:
                os.remove(chemin)
            except OSError:
                pass
        try:
            cache = ocr.charger_cache(dossier)
            documents = cache.get("documents")
            if isinstance(documents, dict):
                for cle in [k for k in documents if ocr._comparable(ocr._cle(k)) == ocr._comparable(rel)]:
                    del documents[cle]
                ocr.sauver_cache(dossier, cache)
        except Exception as e:
            try:
                ms.message_erreur(e, ACTION)
            except Exception:
                pass
        try:
            etat = ms.charger_etat(dossier)
            if (PREFIXE_ETAT + rel) in etat:
                del etat[PREFIXE_ETAT + rel]
                ms.sauver_etat(dossier, etat)
        except Exception as e:
            try:
                ms.message_erreur(e, ACTION)
            except Exception:
                pass
        if empreinte:
            ocr._supprimer_reprise(dossier, empreinte)

    # ------------------------------------------------------------------ glisser-deposer (O16)
    def _depot_installer(self, essais=40, attente=0.25):
        """Pose les gestionnaires DOM de depot de la vue « Deposer » (O16). Vrai si pose.

        pywebview ne remplit `_dnd_state["paths"]` que si un gestionnaire DOM ecoute `drop`
        (`webview/util.py` : `if _dnd_state['num_listeners'] == 0: return`) : c'est donc au Python de poser
        l'ecouteur, sur l'element fixe `#tx-v-deposer` de `interface/index.html` (5.2), avec `body` en repli.

        Un `drop` n'arrive que si `dragover` a ete annule (specification HTML) : les deux ecouteurs sont donc des
        `DOMEventHandler(prevent_default=True)`, le modele documente de pywebview 6.2.1 (`webview/dom/__init__.py`,
        `DOMEventHandler` ; `webview/dom/element.py`, `Element.on` pose `e.preventDefault()`). Un gestionnaire
        simple, sans `prevent_default`, ne recoit jamais le depot : c'etait E-V4-3.

        Quand la zone existe, `body` recoit en plus une garde qui annule `dragover` et `drop` : lacher un PDF a
        cote de la zone ne fait plus ouvrir le fichier dans la fenetre. La garde ne depose rien.

        Le comportement reel n'est pas mesurable ici (ni Windows ni macOS) : ce que ce code prouve est la forme
        des gestionnaires poses, pas l'effet d'un vrai glisser. Ne leve jamais.
        """
        if self._fenetre is None:
            return False
        from webview.dom import DOMEventHandler
        dernier = None
        for essai in range(max(1, essais)):
            try:
                dom = getattr(self._fenetre, "dom", None)
                zone = corps = None
                if dom is not None:
                    zone = dom.get_element("#tx-v-deposer")
                    corps = dom.get_element("body")
                cible = zone if zone is not None else corps
                if cible is not None:
                    cible.on("dragover", DOMEventHandler(_sans_effet, prevent_default=True, stop_propagation=True))
                    cible.on("drop", DOMEventHandler(self._depot_depose, prevent_default=True, stop_propagation=True))
                    if zone is not None and corps is not None:
                        corps.on("dragover", DOMEventHandler(_sans_effet, prevent_default=True))
                        corps.on("drop", DOMEventHandler(_sans_effet, prevent_default=True))
                    self._depot_dom = True
                    return True
            except Exception as e:
                dernier = e
            if essai + 1 < max(1, essais) and attente:
                time.sleep(attente)
        if dernier is not None:
            try:
                ms.message_erreur(dernier, ACTION)     # une seule ligne, apres les essais
            except Exception:
                pass
        return False

    def _depot_depose(self, event):
        """Un depot de fichiers dans la fenetre : les chemins complets partent a `window.textesDepotChemins` (4.6).

        L'interface appelle ensuite `ocr_deposer`. Aucun chemin n'est devine : un fichier sans `pywebviewFullPath`
        n'est pas remonte.
        """
        chemins = chemins_deposes(event)
        if chemins:
            self._js("textesDepotChemins", chemins)
        return chemins
