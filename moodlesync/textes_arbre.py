"""Arborescence des documents d'un coffre (contrat 4.3 de docs/refonte-textes/contrat.md).

Lecture seule : ce module ne lit aucun PDF, n'ecrit rien et ne lance rien. `cache.json`, `file.json` et
`.moodlesync.json` sont lus une fois chacun ; le nombre de pages vient du cache, jamais du document, pour que
l'arbre reste rapide sur des milliers de fichiers. `.moodlesync.json` ne sert qu'a la taille du PDF cherchable
d'un document remplace (`genere.taille_fichier`, 2.2). Les chemins rendus sont relatifs a `dest`, avec `/`.
"""
import os

from . import moteur as ms, ocr

# Les compteurs de la racine et de chaque dossier (4.3).
COMPTEURS = ("fichiers", "traites", "a_verifier", "echecs", "non_traites", "pages_non_traitees")
# Statut d'un fichier vu par l'interface (2.3).
STATUTS = ("non_traite", "en_attente", "en_cours", "traite", "a_verifier", "echec")
# Etat du document au cache (2.2) vers statut (2.3). `difficile` n'est plus un etat de document.
ETATS = {"ok": "traite", "a_verifier": "a_verifier", "echec": "echec"}


def _compteurs_vides():
    return {cle: 0 for cle in COMPTEURS}


def _clef(chemin):
    """Forme comparable d'un chemin relatif : `ocr._cle` puis comparaison du systeme (casse sous Windows)."""
    return ocr._comparable(ocr._cle(chemin))


def _entier(valeur):
    """Entier positif ou nul, sinon None (une valeur abimee du cache ne devient jamais un nombre)."""
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        return None
    return valeur if valeur >= 0 else None


def _texte(valeur):
    return valeur if isinstance(valeur, str) else ""


def _confiance(valeur):
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    return valeur


# ------------------------------------------------------------------ statut (2.3)
def statut_fichier(entree_cache, tache_file):
    """Statut d'un fichier, derive du cache et de sa tache de `file.json` (contrat 2.3).

    La tache passe avant le cache : un document en attente ou en cours n'a pas encore son nouveau texte.
    `entree_cache` vaut None quand aucune entree n'est a jour pour ce fichier ; c'est l'appelant qui le decide.
    """
    if isinstance(tache_file, dict):
        etat = tache_file.get("etat") or "attente"
        if etat == "en_cours":
            return "en_cours"
        if etat == "attente":
            return "en_attente"
    if not isinstance(entree_cache, dict):
        return "non_traite"
    return ETATS.get(entree_cache.get("etat"), "non_traite")


# ------------------------------------------------------------------ cache et file, lus une fois
def _lire_taches(dest):
    """Taches de `file.json` par clef de chemin, etat conserve tel quel.

    `ocr.charger_file` ramene une tache `en_cours` a `attente` (aucune reprise automatique) : l'arbre, lui, doit
    voir la tache en cours (2.3). La file n'est donc lue qu'a travers le JSON, sans la reconcilier ni l'ecrire.
    """
    donnees = ocr._lire_json(ocr._chemin_ocr(dest, "file.json")) or {}
    taches = {}
    liste = donnees.get("taches")
    for tache in liste if isinstance(liste, list) else []:
        if not isinstance(tache, dict) or not isinstance(tache.get("chemin"), str):
            continue
        taches.setdefault(_clef(tache["chemin"]), tache)
    return taches


def _dans_le_coffre(racine, chemin, est_dossier=False):
    """Vrai si `chemin`, une fois resolu, reste dans le coffre (contrat 4, invariant 8). `racine` est deja resolu.

    Un lien symbolique ou une jonction qui sort du coffre n'est ni montre ni traite (E-V3-3) ; un lien qui reste
    dedans est rendu comme une entree ordinaire, ce que `_ocr_confiner` accepte aussi de son cote. Seuls les
    dossiers et les liens sont resolus : un fichier ordinaire dont le dossier est dans le coffre y est aussi, et
    resoudre chaque fichier doublerait la construction de l'arbre (mesure du journal). Les jonctions de Windows
    sont des dossiers : `is_dir` les suit, donc elles passent par la resolution.
    """
    try:
        if not est_dossier and not os.path.islink(chemin):
            return True
        reel = os.path.realpath(chemin)
    except (OSError, ValueError):
        return False
    try:
        relatif = os.path.relpath(os.path.normcase(os.path.normpath(reel)),
                                  os.path.normcase(os.path.normpath(racine)))
    except ValueError:
        return False                    # lecteur different (Windows)
    return relatif == os.curdir or relatif.split(os.sep)[0] != os.pardir


def _tailles_remplacees(dest):
    """Taille du PDF cherchable de chaque document remplace, lue dans `genere` de `.moodlesync.json` (2.1, 2.2).

    L'arbre ne lit toujours aucun PDF : `genere.taille_fichier` est la taille du fichier que la fabrication a
    ecrit, et c'est a elle que se compare la taille du disque quand le cache dit `remplace`. Un bloc incomplet,
    d'une autre nature ou d'une version inconnue est ignore, comme `ocr._genere` le fait.
    """
    tailles = {}
    etat = ms.charger_etat(dest)
    if not isinstance(etat, dict):
        return tailles
    for valeur in etat.values():
        if not isinstance(valeur, dict) or not isinstance(valeur.get("chemin"), str):
            continue
        genere = valeur.get("genere")
        if not isinstance(genere, dict) or genere.get("type") != "pdf_cherchable":
            continue
        version = genere.get("version", 1)
        if isinstance(version, bool) or not isinstance(version, int) or version > 1:
            continue
        taille = _entier(genere.get("taille_fichier"))
        if taille is None:
            continue
        tailles.setdefault(_clef(valeur["chemin"]), taille)
    return tailles


def _a_jour(entree, octets, taille_remplacee=None):
    """Vrai si l'entree de cache decrit le fichier present (2.2 : elle est ecartee des que la source change).

    Deux tailles peuvent decrire le fichier du disque, sans jamais relire ni empreindre le document (4.3) :
    celle de la source, gardee au cache (`taille`), et, pour un PDF remplace par sa version cherchable
    (`remplace`), celle du fichier fabrique, gardee dans `genere.taille_fichier` de `.moodlesync.json` (2.2).
    Un document remplace que quelqu'un a ensuite modifie n'a ni l'une ni l'autre taille : il redevient
    « Non traite ». Une entree sans taille (cache ecrit a la main) est tenue pour a jour.
    """
    if not isinstance(entree, dict):
        return False
    if entree.get("remplace") is True and taille_remplacee is not None and taille_remplacee == octets:
        return True
    taille = entree.get("taille")
    if isinstance(taille, bool) or not isinstance(taille, int):
        return True
    return taille == octets


# ------------------------------------------------------------------ noeuds
def _sortie(entree, statut):
    """(sortie, format, texte, remplace, original_conserve) : rien pour un echec (invariant 2 de la section 9)."""
    if not isinstance(entree, dict) or statut == "echec":
        return "", "", False, False, False
    sortie = _texte(entree.get("sortie"))
    if not sortie:
        return "", "", False, False, False
    return sortie, _texte(entree.get("format")), True, entree.get("remplace") is True, bool(entree.get("original"))


def _noeud_fichier(chemin, octets, documents, taches, tailles_remplacees):
    """Noeud « fichier » de 4.3. `chemin` est relatif a dest, avec `/`."""
    cle = _clef(chemin)
    brut = documents.get(cle)
    entree = brut if _a_jour(brut, octets, tailles_remplacees.get(cle)) else None
    statut = statut_fichier(entree, taches.get(cle))
    sortie, format_, texte, remplace, original = _sortie(entree, statut)
    return {"type": "fichier",
            "nom": chemin.rsplit("/", 1)[-1],
            "chemin": chemin,
            "extension": os.path.splitext(chemin)[1].lstrip(".").lower(),
            "octets": octets,
            "pages": _entier(brut.get("pages")) if isinstance(brut, dict) else None,
            "statut": statut,
            "motif": _texte(entree.get("motif")) if statut == "echec" else "",
            "texte": texte,
            "format": format_,
            "sortie": sortie,
            "remplace": remplace,
            "original_conserve": original,
            "confiance": _confiance(entree.get("confiance")) if isinstance(entree, dict) else None,
            "date": _texte(entree.get("date")) if isinstance(entree, dict) else ""}


def _somme(noeuds):
    """Compteurs de la reunion de ces noeuds (4.3) : chaque dossier porte deja la somme de ses descendants."""
    total = _compteurs_vides()
    for noeud in noeuds:
        if noeud["type"] != "fichier":
            for cle in COMPTEURS:
                total[cle] += noeud["compteurs"][cle]
            continue
        total["fichiers"] += 1
        statut = noeud["statut"]
        if statut == "traite":
            total["traites"] += 1
        elif statut == "a_verifier":
            total["a_verifier"] += 1
        elif statut == "echec":
            total["echecs"] += 1
        else:                       # non_traite, en_attente, en_cours : pas encore de texte
            total["non_traites"] += 1
        if statut in ("non_traite", "echec") and noeud["pages"] is not None:
            total["pages_non_traitees"] += noeud["pages"]
    return total


def _ordre(noeud):
    """Tri de 4.3 : dossiers avant fichiers, puis `ms.cle_nom` (le nom brut departage deux noms equivalents)."""
    return (0 if noeud["type"] == "dossier" else 1, ms.cle_nom(noeud["nom"]), noeud["nom"])


def _entrees(dossier):
    """(nom, est un dossier) des entrees visibles d'un dossier, sans les noms caches (2.1).

    Un dossier illisible rend une liste vide : l'arbre montre ce qu'il peut lire, il ne leve pas.
    """
    sortie = []
    try:
        with os.scandir(dossier) as entrees:
            for entree in entrees:
                if entree.name.startswith("."):
                    continue
                try:
                    est_dossier = entree.is_dir()
                except OSError:
                    continue
                sortie.append((entree.name, est_dossier))
    except OSError:
        return []
    return sortie


def _enfants(dossier, chemin, cfg, dest, racine, documents, taches, tailles_remplacees):
    """Noeuds d'un dossier, dossiers vides omis et liens sortants ecartes (4.3)."""
    noeuds = []
    for nom, est_dossier in _entrees(dossier):
        absolu = os.path.join(dossier, nom)
        if not _dans_le_coffre(racine, absolu, est_dossier):
            continue            # un lien symbolique ou une jonction qui sort du coffre ne s'affiche pas (E-V3-3)
        rel = f"{chemin}/{nom}" if chemin else nom
        if est_dossier:
            enfants = _enfants(absolu, rel, cfg, dest, racine, documents, taches, tailles_remplacees)
            if enfants:
                noeuds.append({"type": "dossier", "nom": nom, "chemin": rel,
                               "compteurs": _somme(enfants), "enfants": enfants})
            continue
        eligible = ocr._eligible(dest, cfg, rel)
        if eligible is None:
            continue
        try:
            octets = os.path.getsize(eligible)
        except OSError:
            continue            # fichier disparu entre deux appels : ignore, jamais une erreur
        noeuds.append(_noeud_fichier(rel, octets, documents, taches, tailles_remplacees))
    noeuds.sort(key=_ordre)
    return noeuds


# ------------------------------------------------------------------ interface publique (4.3)
def construire_arbre(dest, cfg):
    """Arbre des documents de `dest` (forme de 4.3). Coffre absent : arbre vide, sans erreur."""
    cfg = cfg if isinstance(cfg, dict) else {}
    arbre = {"racine": dest if isinstance(dest, str) else "", "cours": [], "compteurs": _compteurs_vides()}
    if not isinstance(dest, str) or not os.path.isdir(dest):
        return arbre
    documents = {_clef(cle): entree for cle, entree in (ocr.charger_cache(dest).get("documents") or {}).items()
                 if isinstance(entree, dict)}
    taches = _lire_taches(dest)
    tailles_remplacees = _tailles_remplacees(dest)
    racine = os.path.realpath(dest)
    cours = []
    for nom, est_dossier in _entrees(dest):
        absolu = os.path.join(dest, nom)
        # Un fichier pose directement dans le coffre n'est pas un cours ; un lien sortant du coffre non plus.
        if not est_dossier or not _dans_le_coffre(racine, absolu, True):
            continue
        enfants = _enfants(absolu, nom, cfg, dest, racine, documents, taches, tailles_remplacees)
        if not enfants:
            continue
        cours.append({"type": "dossier", "nom": nom, "chemin": nom, "compteurs": _somme(enfants), "enfants": enfants})
    cours.sort(key=_ordre)
    arbre["cours"] = cours
    arbre["compteurs"] = _somme(cours)
    return arbre


def fichiers_sous(dest, cfg, chemins):
    """Noeuds « fichier » a plat des `chemins` demandes, dans l'ordre de l'arbre (4.4).

    Un dossier est developpe en tous ses fichiers eligibles, recursivement ; un chemin inconnu est ignore et les
    doublons sont fusionnes (un fichier deja couvert par un dossier ne revient pas deux fois).
    """
    demandes = [_clef(chemin) for chemin in (chemins or []) if isinstance(chemin, str)]
    demandes = [demande for demande in demandes if demande]
    if not demandes:
        return []
    sortie = []

    def descendre(noeuds):
        for noeud in noeuds:
            if noeud["type"] == "fichier":
                cle = _clef(noeud["chemin"])
                if any(cle == demande or cle.startswith(demande + "/") for demande in demandes):
                    sortie.append(noeud)
            else:
                descendre(noeud.get("enfants") or [])

    descendre(construire_arbre(dest, cfg)["cours"])
    return sortie


def compteurs(arbre):
    """Compteurs de la racine (4.3), sans relire le disque : ceux de l'arbre deja construit."""
    valeurs = arbre.get("compteurs") if isinstance(arbre, dict) else None
    total = _compteurs_vides()
    if isinstance(valeurs, dict):
        for cle in COMPTEURS:
            valeur = _entier(valeurs.get(cle))
            total[cle] = valeur if valeur is not None else 0
    return total
