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
import base64, io, os, re, threading, time, unicodedata
from contextlib import contextmanager

from . import moteur as ms, ocr
from .api_horaire import _proteger

ACTION = "Texte des cours"
# Bornes de la mise en file automatique apres une synchronisation (D7, contrat 3.2).
LOT_DOCUMENTS = 50
LOT_PAGES = 500
# Page d'apercu : rendu a 150 DPI, ramene ensuite a 900 px de large au plus (D11).
DPI_APERCU = 150
LARGEUR_APERCU = 900
# Plafond de `ocr_copier` (contrat 2.7, plafond a confirmer) et contexte d'un extrait de recherche.
TEXTE_MAX = 2000000
CONTEXTE_CARACTERES = 40
# Lettre de lecteur Windows : `C:x` (ecart 144). Refuse avant `ocr._cle`, qui en ferait un chemin relatif.
RE_LECTEUR = re.compile(r"^[A-Za-z]:")

# Valeurs par defaut de config.json (plan 5.6) : charger_config ne les ecrit pas, le mixin les lit ainsi.
REGLAGES_OCR = {"ocr": False, "ocr_exe": "", "ocr_tessdata": "", "ocr_langues": "fra+eng", "ocr_dpi": 300,
                "ocr_psm": 3, "ocr_dossier": "Textes", "ocr_apres_sync": True, "ocr_max_mo": 300,
                "ocr_threads": 2, "ocr_batterie": "pause", "ocr_sortie_hors_coffre": False, "ocr_pdf": "aucun"}
MODES_PDF = ("aucun", "remplacer")
BATTERIES = ("pause", "continuer")
PSM = (1, 3, 4, 6)

def _message(code, **champs):
    """Phrase visible de la section 5 du contrat : ocr.MESSAGES est la seule source (invariant 9, ecart 122). Aucune
    phrase n'est ecrite dans ce module ; les champs `{...}` d'un modele se remplissent par `champs`."""
    modele = ocr.MESSAGES[code]
    return modele.format(**champs) if champs else modele


def _reglage(cfg, cle):
    """Valeur d'un reglage, valeur par defaut du plan 5.6 si la cle manque ou est illisible."""
    valeur = cfg.get(cle, REGLAGES_OCR[cle])
    return REGLAGES_OCR[cle] if valeur is None else valeur


def mettre_en_file_auto(compte_rendu):
    """Point d'appel du mode `--auto` (plan 5.5, ecart 135, decision de Maxence) : met en file les documents que la
    synchronisation vient d'ecrire et archive l'ancien `.md` d'un PDF cherchable republie, comme apres une
    synchronisation avec fenetre. N'ouvre aucune fenetre et ne demarre jamais l'extraction.

    Appelee par `moteur.mode_auto` par un import a l'usage : `moteur.py` n'importe pas `ocr`. Le consentement
    (D7) est relu ici : sans `ocr` ou sans `ocr_apres_sync`, rien n'entre dans la file."""
    cfg = ms.charger_config()
    dest = cfg.get("dest") or ""
    if not (dest and os.path.isdir(dest) and cfg.get("ocr") and cfg.get("ocr_apres_sync", True)):
        return 0
    try:
        return ocr.mettre_en_file_apres_sync(dest, cfg, compte_rendu)
    except Exception as e:
        ms.message_erreur(e, ACTION)
        return 0


def _entier(valeur, defaut=0):
    """Entier positif ou nul d'une valeur venue d'un JSON (cache ou file edites a la main). Seul un `int` hors
    booleen et non negatif passe ; toute autre valeur (chaine, flottant, booleen, negatif, liste) donne `defaut` :
    aucune valeur n'est inventee a partir d'une chaine (contrat 2.7, ecarts 136 et 165)."""
    if isinstance(valeur, int) and not isinstance(valeur, bool) and valeur >= 0:
        return valeur
    return defaut


def _confiance(valeur):
    """Float de 0 a 1, arrondi a trois decimales, ou None : une valeur hors bornes ou illisible n'est pas inventee."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    nombre = float(valeur)
    if nombre != nombre or not 0.0 <= nombre <= 1.0:   # nan, infini ou hors bornes
        return None
    return round(nombre, 3)


def _type_document(extraction):
    """Type affiche (2.7) : `texte`, `scanne` ou `mixte`. Un document sans aucun texte (`extraction` vide) n'a pas
    de texte natif : il est classe « scanne », et sa qualite « vide » le dit deja (contrat 2.3)."""
    if extraction == "texte":
        return "texte"
    if extraction == "mixte":
        return "mixte"
    return "scanne"


def _qualite_document(entree):
    """Qualite de 2.7 : `vide` se deduit de l'extraction (contrat 2.3), sinon `ok` donne `bon`."""
    if entree.get("extraction") == "vide":
        return "vide"
    return {"ok": "bon", "difficile": "difficile"}.get(entree.get("etat"), "a_verifier")


_ESPACES = re.compile(r"\s+")
_COMBINANTS = {}


def _combinants():
    """Table de `str.translate` qui retire les marques combinantes (`unicodedata.combining` non nul), construite a
    la premiere recherche. Aucune marque n'est au-dela de U+1FFFF."""
    if not _COMBINANTS:
        _COMBINANTS.update({i: None for i in range(0x20000) if unicodedata.combining(chr(i))})
    return _COMBINANTS


def _plier_vite(texte):
    """Meme texte plie que `_pliage(texte)[0]`, sans table d'index et sans boucle Python par caractere : sans casse
    ni accents, chaque suite de blancs repliee en une espace (une suite de bord laisse une espace). Sert a savoir si
    une page contient le terme (ecart 158) ; seules les pages qui le contiennent descendent ensuite au caractere."""
    plie = unicodedata.normalize("NFD", texte).casefold().translate(_combinants())
    corps = " ".join(plie.split())
    if not corps:
        return " " if plie else ""
    return (" " if plie[0].isspace() else "") + corps + (" " if plie[-1].isspace() else "")


def _pliage(texte):
    """(texte sans casse ni accents, index du caractere d'origine pour chaque caractere plie).

    Le pliage decompose en NFD et retire les diacritiques ; `casefold` peut allonger un caractere (par exemple
    « ß » donne « ss »), d'ou la table d'index : un extrait se reconstruit toujours dans le texte d'origine
    (contrat 2.7 : des segments, jamais de decalages). Une suite de blancs (espace, saut de ligne, tabulation,
    espace insecable) devient une seule espace, rattachee au premier blanc de la suite : un terme de plusieurs
    mots se trouve alors meme si le texte le coupe par un saut de ligne (ecart 154)."""
    plie, origine = [], []
    for i, caractere in enumerate(texte):
        for element in unicodedata.normalize("NFD", caractere).casefold():
            if unicodedata.combining(element):
                continue
            if element.isspace():
                if plie and plie[-1] == " ":
                    continue
                element = " "
            plie.append(element)
            origine.append(i)
    return "".join(plie), origine


def _apres_marques(texte, fin):
    """`fin` repoussee au-dela des marques combinantes qui suivent : une lettre garde ses accents (NFD)."""
    while fin < len(texte) and unicodedata.combining(texte[fin]):
        fin += 1
    return fin


def _nombre(valeur, mot):
    """« 1 document », « 3 documents » (zero et un au singulier)."""
    return f"{valeur} {mot}" + ("s" if valeur > 1 else "")


def _nom_zip(dest, chemin):
    """Nom d'entree d'un document dans le zip d'export : sa cle de cache, c'est-a-dire son chemin relatif complet
    dans le coffre (prefixe du coffre retire s'il y est), avec `.md` (contrat 2.6, ecart 155). Unique parce que la
    cle l'est. None si la cle sort du coffre (`..`, lettre de lecteur, vide) : elle n'entre pas dans le zip."""
    relatif = ocr._cle(chemin)
    racine = ocr._cle(dest)
    if racine and relatif.startswith(racine + "/"):
        relatif = relatif[len(racine) + 1:]
    parties = relatif.split("/")
    if not relatif or ".." in parties or RE_LECTEUR.match(parties[0]):
        return None
    return relatif + ".md"


def _sous(chemin, racine):
    """Vrai si `chemin` est `racine` ou se trouve dessous, comparaison du systeme (casse sous Windows)."""
    chemin = os.path.normcase(os.path.abspath(chemin))
    racine = os.path.normcase(os.path.abspath(racine))
    return chemin == racine or chemin.startswith(racine + os.sep)


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
            if entree.get("etat") != "ok" and entree.get("verifie") is not True:
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
                # Extraction sequentielle (ecart 126, decision de Maxence) : `ocr_threads` ne divise pas la duree.
                restant = max(1, round(restants * 2 / 60))
        self._js("textesProgres", {"etat": self._ocr_etat_fil, "document": self._ocr_courant,
                                   "page": self._ocr_page, "pages": self._ocr_pages,
                                   "documents_faits": self._ocr_faits, "documents_total": self._ocr_total,
                                   "restant_min": restant, "message": message})

    def _ocr_journal(self, texte):
        if texte:
            self._js("textesJournal", str(texte))

    # ------------------------------------------------------------------ outils de A2 (recherche, copie, export, ouverture)
    def _ocr_cherchables(self, dest):
        """Chemins comparables dont l'etat de synchronisation porte un bloc `genere` (contrat 2.7 : `cherchable`
        exige l'etat et un fichier present ; la presence du fichier est verifiee par l'appelant)."""
        trouves = set()
        try:
            etat = ms.charger_etat(dest)
        except Exception:
            return trouves
        if not isinstance(etat, dict):
            return trouves
        for entree in etat.values():
            if not isinstance(entree, dict) or not isinstance(entree.get("chemin"), str):
                continue
            if isinstance(entree.get("genere"), dict):
                trouves.add(ocr._comparable(ocr._cle(entree["chemin"])))
        return trouves

    def _ocr_portee(self, dest, portee, cfg):
        """(documents, pages) d'une portee, comptes comme l'agregat de C5 : cours non vide et .md lisible."""
        documents = pages = 0
        with self._ocr_verrou:
            trouves = ocr._documents(dest)
        for document in trouves:
            if not document["cours"] or not ocr._dans_la_portee(document, portee, cfg):
                continue
            contenu = ocr._lire_md(document)
            if contenu is None:
                continue
            documents += 1
            pages += len(contenu)
        return documents, pages

    def _ocr_extrait(self, document, numero, contenu, origine, position, longueur):
        """Un resultat de recherche (2.7) : la page, son extrait en segments, le terme marque une fois.

        `origine` vient de `_pliage` : chaque caractere plie renvoie a son caractere d'origine, donc l'extrait
        est decoupe dans `contenu` sans aucun decalage. Les segments gardent leurs blancs de bord et ne replient
        que les blancs internes (ecart 153) : leur jointure redonne l'extrait, aux blancs internes pres. Une marque
        combinante qui suit la fin du terme ou du contexte reste dans son segment (ecart 156)."""
        fin = min(len(origine), position + longueur + CONTEXTE_CARACTERES)
        debut = max(0, position - CONTEXTE_CARACTERES)
        fin_terme = _apres_marques(contenu, origine[position + longueur - 1] + 1)
        fin_extrait = _apres_marques(contenu, origine[fin - 1] + 1)
        avant = contenu[origine[debut]:origine[position]]
        trouve = contenu[origine[position]:fin_terme]
        apres = contenu[fin_terme:fin_extrait]
        segments = []
        for texte, marque in ((avant, False), (trouve, True), (apres, False)):
            texte = _ESPACES.sub(" ", texte)
            if texte:
                segments.append({"t": texte, "m": marque})
        return {"chemin": document["chemin"], "cours": document["cours"], "section": document["section"],
                "nom": document["nom"], "page": numero, "segments": segments}

    def _ocr_pages_attendues(self, dest, portee, cfg):
        """Pages que `ocr.ecrire_jsonl` doit ecrire pour la portee : une ligne par page des .md lisibles. Appelee
        sous `_ocr_verrou`, avec l'ecriture qu'elle controle."""
        attendues = 0
        for document in ocr._documents(dest):
            if not ocr._dans_la_portee(document, portee, cfg):
                continue
            pages = ocr._lire_md(document)
            if pages is not None:
                attendues += len(pages)
        return attendues

    def _ocr_zip(self, dest, portee, cfg, jsonl):
        """(octets du zip, nombre de .md ajoutes). Le zip porte les .md de document de la portee, a leur chemin
        relatif complet (`_nom_zip`, unique), sans chemin absolu (2.6) ; `jsonl` ajoute `textes.jsonl` par
        `ocr.ecrire_jsonl` (plan 6.4), sous `_ocr_verrou`, et un compte de lignes inferieur aux pages attendues est une
        erreur d'ecriture : aucun zip partiel (ecart 162). Rien n'est ecrit dans dest."""
        import errno, zipfile
        with self._ocr_verrou:
            trouves = ocr._documents(dest)
        ajoutes = set()
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
            for document in trouves:
                if not document["cours"] or not document["md"] or not ocr._dans_la_portee(document, portee, cfg):
                    continue
                nom = _nom_zip(dest, document["chemin"])
                if nom is None or ocr._comparable(nom) in ajoutes:
                    continue
                try:
                    with open(document["md"], "rb") as f:
                        contenu = f.read()
                except OSError as e:
                    ms.message_erreur(e, ACTION)   # un .md illisible sort du zip, invariant 9
                    continue
                z.writestr(nom, contenu)
                ajoutes.add(ocr._comparable(nom))
            if jsonl:
                flux = io.StringIO()
                with self._ocr_verrou:
                    attendues = self._ocr_pages_attendues(dest, portee, cfg)
                    ecrites = ocr.ecrire_jsonl(dest, portee, flux, cfg=cfg)
                if not isinstance(ecrites, int) or ecrites < attendues:
                    # Phrase de ms.message_erreur (OSError) : le detail n'est pas pour la fenetre.
                    raise OSError(errno.EIO, os.strerror(errno.EIO))
                z.writestr("textes.jsonl", flux.getvalue().encode("utf-8"))
        return tampon.getvalue(), len(ajoutes)

    def _ocr_ecrire(self, chemin, donnees):
        """Ecriture atomique d'un export (temporaire puis `os.replace`), hors de `dest`. Une OSError remonte."""
        temporaire = chemin + ".tmp"
        try:
            with open(temporaire, "wb") as f:
                f.write(donnees)
            os.replace(temporaire, chemin)
        except BaseException:
            try:
                os.remove(temporaire)
            except OSError:
                pass
            raise

    def _ocr_cible_dans_le_coffre(self, dest, chemin, cfg):
        """Vrai si la cible d'un export est `dest` ou le dossier de sortie, ou se trouve dessous (plan 5.9,
        invariant 8, ecart 161). Les liens symboliques sont resolus : un lien vers le coffre ne contourne rien."""
        racines = [dest]
        try:
            with self._ocr_verrou:
                racines.append(ocr._dossier_textes(dest, cfg))
        except Exception:
            pass
        cible = os.path.realpath(chemin)
        return any(_sous(cible, os.path.realpath(racine)) for racine in racines)

    def _ocr_confiner(self, dest, chemin, cfg):
        """Chemin absolu confine (invariant 8, plan 5.9), ou None.

        Relatif a `dest`, separateurs normalises par `ocr._cle` ; ni `..`, ni lettre de lecteur (`C:x`, ecart 144),
        ni dossier cache. Resolution par `os.path.realpath`, puis comparaison de prefixe avec `dest` et le dossier
        de sortie : un lien symbolique qui sort du coffre est refuse. Aucun fichier cache n'est atteignable."""
        if not isinstance(chemin, str):
            return None
        brut = chemin.strip()
        if not brut or "\x00" in brut or RE_LECTEUR.match(brut):
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
        try:
            with self._ocr_verrou:
                dossier = ocr._dossier_textes(dest, cfg)
            racines.append(os.path.realpath(dossier))
        except Exception:
            pass
        for racine in racines:
            try:
                relatif = os.path.relpath(os.path.normcase(reel), os.path.normcase(racine))
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
        taches ajoutees entre-temps par une synchronisation ne soient pas perdues (ecart 130)."""
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
        """Un document, une page a la fois sous `_ocr_fichiers` : la synchronisation passe entre deux pages."""
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
        attente, y compris une tache ajoutee par une synchronisation pendant l'extraction."""
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
        self._ocr_etat_fil = "en_cours"
        self._ocr_pousser(force=True)
        while True:
            tache = self._ocr_prochaine(dest)
            if tache is None:
                break
            chemin = tache.get("chemin") or ""
            if not chemin or not self._ocr_attendre(dest):
                return self._ocr_poser_etat(dest, "annulee")
            cfg = self._cfg()                        # ecart 132 : le consentement est relu avant chaque document
            if not cfg.get("ocr"):
                return self._ocr_poser_etat(dest, "annulee")
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

    # ------------------------------------------------------------------ mise en file automatique
    def _ocr_apres_sync(self, compte_rendu):
        """Contrat 3.2 : met en file ce que la synchronisation a ecrit, puis demarre l'extraction seule si `ocr` et
        `ocr_apres_sync` sont vrais, la fenetre ouverte, et le lot sous 50 documents et 500 pages (D7). Jamais sans
        fenetre : le mode --auto ne construit pas Api et passe par `mettre_en_file_auto`.
        Le lot juge ne compte que les taches ajoutees par cette synchronisation (ecart 138, decision de Maxence) :
        une file laissee en `pause` par une session precedente ne repart pas seule (contrat 2.5)."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        avant = set()
        try:
            with self._ocr_verrou:
                if dest:
                    avant = {ocr._cle(t.get("chemin") or "") for t in ocr.charger_file(dest)["taches"]
                             if isinstance(t, dict) and t.get("etat") == "attente"}
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
        file = self._ocr_lire_file(dest)
        attente = [t for t in file["taches"] if isinstance(t, dict) and t.get("etat") == "attente"
                   and ocr._cle(t.get("chemin") or "") not in avant]
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
        """Installe le moteur portable a la demande (I1, D6). Le clic sur « Installer » est l'accord explicite : aucun
        consentement `ocr` n'est exige, installer n'est pas extraire, et le consentement n'est pas donne par ce clic.
        Moteur deja detecte : l'etat complet, rien n'est telecharge. Succes : `ocr_etat()` (les deux pages ne se
        rafraichissent que sur une reponse qui porte `moteur`, ecart 238). Erreur : la phrase, telle quelle, ecrite
        aussi au journal. `{"annule": True}` est relaye. Pas d'arret branche : aucun bouton n'annule le telechargement."""
        if self._ocr_moteur(self._cfg(), frais=True).get("present"):
            return self.ocr_etat()
        r = ocr.installer_paquet()
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
        """Fourchette de duree, ordre de grandeur du plan 5.8 : 1 a 3 secondes par page. Extraction sequentielle
        (ecart 126, decision de Maxence) : `ocr_threads` ne divise plus la duree (ecart 133)."""
        secondes = max(0, _entier(pages, 0))
        mini = max(1, round(secondes / 60))
        return [mini, max(mini + 1, round(secondes * 3 / 60))]

    def _ocr_phrase_lot(self, documents, pages, cfg):
        """Fenetre de confirmation du premier passage long (plan 3.4)."""
        mini, maxi = self._ocr_minutes(pages, cfg)
        return _message("confirmation_lot", documents=_nombre(documents, "document"), pages=_nombre(pages, "page"),
                        mini=mini, maxi=maxi)

    @_proteger(ACTION)
    def ocr_lancer(self, portee="sans_texte", refaire=False, confirme=False):
        """Constitue la file de la portee (2.5) et demarre l'extraction. Au-dela de 50 documents ou 500 pages, une
        confirmation avec la duree est demandee (plan 3.4, D7) ; `confirme=True` la donne. Sans le consentement
        (`ocr` vrai), rien n'est constitue ni lance : la page ne tient pas seule ce garde-fou (invariant 16, ecart 137)."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        if not cfg.get("ocr"):
            return {"erreur": _message("consentement_absent")}
        if not dest or not os.path.isdir(dest):
            return {"erreur": _message("dossier_absent")}
        if self._ocr_actif():
            return {"erreur": _message("occupe")}
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
    def ocr_documents(self, filtre=None):
        """Liste des documents extraits (forme 2.7), triee par cours, section et nom (ms.cle_nom).

        `filtre` = {"cours": cid|null, "qualite": "bon"|"a_verifier"|"difficile"|"orphelin"|null,
        "type": "texte"|"scanne"|null}. Lecture seule : le cache est lu sous `_ocr_verrou`, les orphelins sont
        releves (invariant 11), rien n'est ecrit ni mis en file."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        filtre = filtre if isinstance(filtre, dict) else {}
        if not dest or not os.path.isdir(dest):
            return {"documents": [], "total": 0, "pages": 0}
        with self._ocr_verrou:
            cache = ocr.charger_cache(dest)
            trouves = ocr._documents(dest)
            try:
                orphelins = {ocr._comparable(e["chemin"]) for e in ocr._orphelins(dest, cache)}
            except Exception:
                orphelins = set()
        cherchables = self._ocr_cherchables(dest)
        cours_voulu = filtre.get("cours")
        dossier = ocr._dossier_du_cours(cfg, cours_voulu) if cours_voulu is not None else None
        qualite_voulue = filtre.get("qualite")
        qualite_voulue = (qualite_voulue if qualite_voulue in ("bon", "a_verifier", "difficile", "vide", "orphelin")
                          else None)
        type_voulu = filtre.get("type")
        type_voulu = type_voulu if type_voulu in ("texte", "scanne", "mixte") else None
        documents = []
        for document in trouves:
            chemin = document["chemin"]
            if not chemin:
                continue
            entree = document["entree"] if isinstance(document["entree"], dict) else {}
            if cours_voulu is not None and (not dossier or ms.cle_nom(document["cours"]) != ms.cle_nom(dossier)):
                continue
            ligne = {"chemin": chemin, "cours": document["cours"], "section": document["section"],
                     "nom": document["nom"], "type": _type_document(entree.get("extraction")),
                     "pages": _entier(entree.get("pages")), "qualite": _qualite_document(entree),
                     "confiance": _confiance(entree.get("confiance")),
                     "cherchable": (ocr._comparable(chemin) in cherchables
                                    and os.path.isfile(ocr._absolu(dest, chemin))),
                     "verifie": entree.get("verifie") is True, "orphelin": ocr._comparable(chemin) in orphelins,
                     "sortie": entree.get("sortie") if isinstance(entree.get("sortie"), str) else "",
                     "date": entree.get("date") if isinstance(entree.get("date"), str) else ""}
            if qualite_voulue == "orphelin":
                if not ligne["orphelin"]:
                    continue
            elif qualite_voulue and ligne["qualite"] != qualite_voulue:
                continue
            if type_voulu and ligne["type"] != type_voulu:
                continue
            documents.append(ligne)
        return {"documents": documents, "total": len(documents), "pages": sum(d["pages"] for d in documents)}

    @_proteger(ACTION)
    def ocr_chercher(self, texte, limite=50):
        """Recherche sans casse ni accents dans les .md de document (forme 2.7).

        Une page est une unite de resultat ; les segments se reconstruisent dans le texte d'origine, sans
        decalage. Les blancs se replient, dans le terme comme dans le texte : « machine learning » se trouve
        dans « machine\\nlearning » (ecart 154). La section « Pages à vérifier » n'entre jamais dans la recherche
        (ecart 78). Au-dela de `limite` resultats, `tronque` est vrai ; `total` compte toutes les pages trouvees.

        Une page est d'abord pliee d'un bloc (`_plier_vite`) pour savoir si elle contient le terme ; seules les pages
        qui deviennent un resultat descendent au caractere (`_pliage`, table d'index), pas celles au-dela de `limite`
        (ecart 158)."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        termine = {"resultats": [], "total": 0, "tronque": False}
        terme = texte.strip() if isinstance(texte, str) else ""
        aiguille = _plier_vite(terme).strip()
        if len(aiguille) < 2:
            return termine
        if not dest or not os.path.isdir(dest):
            return termine
        borne = limite if isinstance(limite, int) and not isinstance(limite, bool) and limite >= 0 else 50
        with self._ocr_verrou:
            trouves = ocr._documents(dest)
        resultats, total = [], 0
        for document in trouves:
            pages = ocr._lire_md(document)
            if not pages:
                continue
            for numero, contenu in pages:
                if not contenu:
                    continue
                if aiguille not in _plier_vite(contenu):
                    continue
                total += 1
                if len(resultats) < borne:
                    foin, origine = _pliage(contenu)
                    position = foin.find(aiguille)
                    if position < 0:                      # les deux pliages sont identiques (test) : garde-fou
                        total -= 1
                        continue
                    resultats.append(self._ocr_extrait(document, numero, contenu, origine, position, len(aiguille)))
        return {"resultats": resultats, "total": total, "tronque": total > borne}

    @_proteger(ACTION)
    def ocr_copier(self, portee):
        """Texte pret a coller (plan 6.2, T27) pour la portee : `{"texte", "caracteres", "documents", "pages"}`.

        Le texte vient de `ocr.assembler_contexte`, sans ecriture ; le compte de caracteres est calcule ici sur
        la chaine renvoyee (T27). Au-dela de `TEXTE_MAX` : `{"trop_long": True, "caracteres": n}`. Le
        presse-papiers est ecrit par la page, jamais par Python."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        portee = portee if isinstance(portee, str) else ""
        if not dest or not os.path.isdir(dest):
            return {"texte": "", "caracteres": 0, "documents": 0, "pages": 0}
        with self._ocr_verrou:
            texte = ocr.assembler_contexte(dest, portee, cfg=cfg)
            documents, pages = self._ocr_portee(dest, portee, cfg)
        texte = texte if isinstance(texte, str) else ""
        caracteres = len(texte)
        if caracteres > TEXTE_MAX:
            return {"trop_long": True, "caracteres": caracteres}
        return {"texte": texte, "caracteres": caracteres, "documents": documents, "pages": pages}

    @_proteger(ACTION)
    def ocr_exporter(self, portee, format="zip"):
        """Exporte les textes de la portee (forme 2.7) dans un fichier choisi par une boite de dialogue native.

        `format` : `zip` (les .md de document), `zip_jsonl` (les memes .md et `textes.jsonl` par
        `ocr.ecrire_jsonl`), `md` (le texte assemble, comme la copie). Rien n'est ecrit dans `dest` ni dans le
        dossier de sortie : une cible qui s'y trouve est refusee avant tout ecriture (plan 5.9, ecart 161). Le format
        est controle avant toute lecture de la configuration (ecart 150)."""
        if not isinstance(format, str) or format not in ("zip", "zip_jsonl", "md"):
            return {"erreur": _message("format_inconnu")}
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        if not dest or not os.path.isdir(dest):
            return {"erreur": _message("dossier_absent")}
        if self._fenetre is None:
            return {"erreur": _message("fenetre_fermee")}
        import webview
        if format == "md":
            choix = self._fenetre.create_file_dialog(webview.SAVE_DIALOG, save_filename="Texte des cours.md",
                                                     file_types=("Markdown (*.md)", "Tous les fichiers (*.*)"))
        else:
            choix = self._fenetre.create_file_dialog(webview.SAVE_DIALOG, save_filename="Textes des cours.zip",
                                                     file_types=("Archive ZIP (*.zip)", "Tous les fichiers (*.*)"))
        if not choix:
            return {"annule": True}
        chemin = choix[0] if isinstance(choix, (list, tuple)) else choix
        chemin = os.path.abspath(str(chemin))
        extension = ".md" if format == "md" else ".zip"
        if not chemin.lower().endswith(extension):
            chemin += extension
        if self._ocr_cible_dans_le_coffre(dest, chemin, cfg):
            return {"erreur": _message("cible_dans_coffre")}
        if format == "md":
            with self._ocr_verrou:
                texte = ocr.assembler_contexte(dest, portee, cfg=cfg)
                documents, _ = self._ocr_portee(dest, portee, cfg)
            donnees = (texte if isinstance(texte, str) else "").encode("utf-8")
        else:
            donnees, documents = self._ocr_zip(dest, portee, cfg, format == "zip_jsonl")
        self._ocr_ecrire(chemin, donnees)
        return {"chemin": chemin, "octets": os.path.getsize(chemin), "documents": documents}

    @_proteger(ACTION)
    def ocr_ouvrir(self, chemin, page=None):
        """Ouvre le .md d'un document ou un dossier du coffre ; repond `{"source": True}` pour un fichier
        d'origine (PDF, image). `page` est transmise par la page pour le defilement, Python ne s'en sert pas.

        Tout chemin hors de `dest` et du dossier de sortie est refuse, comme le dossier cache (invariant 8,
        plan 5.9) : la reponse est `ouverture_refusee` (chemin refuse, absent ou octet nul), `ouverture_impossible`
        quand le systeme n'ouvre pas le fichier. L'ouverture passe par une liste d'arguments, jamais par un shell
        (`ms.ouvrir_dossier`, `semaine.ouvrir_document`). Succes : `{"ok": True}` (.md ou dossier ouvert) ou
        `{"source": True}` (fichier d'origine, que la page ouvre autrement)."""
        from . import semaine as sem
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        if not dest:
            return {"erreur": _message("dossier_absent")}
        reel = self._ocr_confiner(dest, chemin, cfg)
        if reel is None:
            return {"erreur": _message("ouverture_refusee")}
        if os.path.isdir(reel):
            try:
                ms.ouvrir_dossier(reel)
            except OSError as e:
                ms.message_erreur(e, ACTION)           # detail dans erreurs.txt, la fenetre recoit la phrase
                return {"erreur": _message("ouverture_impossible")}
            return {"ok": True}
        if not os.path.isfile(reel):
            return {"erreur": _message("ouverture_refusee")}
        if os.path.splitext(reel)[1].lower() != ".md":
            return {"source": True}
        if not sem.ouvrir_document(reel):
            return {"erreur": _message("ouverture_impossible")}
        return {"ok": True}

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
        if not isinstance(cle, str) or cle not in REGLAGES_OCR:
            return {"erreur": _message("reglage_inconnu", cle=str(cle)[:40])}
        cfg = self._cfg()
        try:
            valeur = self._ocr_valeur(cle, valeur, cfg)
        except _Refus as e:
            return e.reponse
        except (TypeError, ValueError):
            return {"erreur": _message("valeur_invalide")}
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


RE_RESERVE = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)


def _dossier(valeur, cfg):
    """Nom simple et visible de dossier de sortie : ni separateur, ni `..`, ni caractere interdit, ni point en tete
    (`ocr_ouvrir` refuse les composants caches, ecarts 141 et 160), ni point final, ni nom reserve de Windows
    (`CON`, `NUL`, `COM1`..., avec ou sans extension), et jamais un dossier de cours."""
    nom = ms.nfc(valeur.strip()) if isinstance(valeur, str) else ""
    if not nom or nom.startswith(".") or nom.endswith(".") or ms.ILLEGAL.search(nom) or "/" in nom or "\\" in nom \
            or ".." in nom or RE_RESERVE.match(nom.split(".")[0]):
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
        raise _Refus(_message("dossier_pris"))
    return nom
