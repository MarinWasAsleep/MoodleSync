"""Migration de l'ancien dossier « Textes/ » (contrat 8 de docs/refonte-textes/contrat.md).

La version 2.5 ecrivait le texte de chaque document sous `Textes/<Cours>/<section>/<nom>.md`, avec
`index.md`, `Qualité des textes.md` et un fichier « texte des documents » par cours. La refonte ecrit le
texte a cote du PDF : cette migration deplace chaque texte, supprime les agregats, puis `Textes/` quand
elle est vide.

Trois regles du contrat qui ne se negocient pas :

- **aucun PDF n'est modifie** : la migration ne fait que deplacer et supprimer des textes ;
- **un texte edite a la main n'est jamais supprime** (O14) : un document « Difficile » perd son `.md`
  seulement si son front matter porte la ligne `moodlesync:` ; sinon le texte est deplace ;
- **idempotente** : relancee, elle ne refait rien de fait et ne perd rien ; un texte dont le document
  source a disparu reste dans `Textes/`, qui n'est alors pas supprimee.

Le cache `.moodlesync-ocr/cache.json` suit : `sortie`, `format = "md"` et `sortie_empreinte` mesures,
`remplace` lu dans `.moodlesync.json` (`genere`), `original` a `null` (U9). Un ancien etat `difficile`
devient `echec` de motif `difficile` (O14). L'ecriture de `textes_v2` dans `config.json` et l'annonce
appartiennent a `application.migrer_textes`, pas a ce module.
"""
import json
import os

from . import moteur as ms, ocr

# L'ancien dossier de sortie (U2). `ocr_dossier` pouvait le renommer ; O10 retire ce reglage, et le
# contrat 8 ne nomme que `Textes/` : une autre disposition n'est pas migree (doute note au journal).
DOSSIER = "Textes"
INDEX = "index.md"
QUALITE = "Qualité des textes.md"
TITRE_COURS = " - texte des documents.md"
# Etats de l'ancien cache qui decrivent un document lu : `difficile` n'existe plus (2.2).
ETAT_DIFFICILE = "difficile"
# Cles d'une ligne de l'export `.jsonl` de l'ancienne version (plan 6.4), sa seule signature : ce fichier ne
# porte aucune marque (E-V4-7).
CLES_EXPORT = ("cours", "section", "fichier", "page", "texte")


def _posix(chemin):
    return chemin.replace(os.sep, "/")


def _fichiers(racine):
    """(chemin relatif a `racine`, avec `/`, chemin absolu) de tous les fichiers, ordre stable."""
    sortie = []
    for dossier, sous_dossiers, fichiers in os.walk(racine):
        sous_dossiers.sort()
        for nom in sorted(fichiers):
            absolu = os.path.join(dossier, nom)
            sortie.append((_posix(os.path.relpath(absolu, racine)), absolu))
    return sortie


def _agrege(rel, nom):
    """Vrai pour un nom de fichier de synthese de l'ancienne version (contrat 8.5), jamais pour un texte de document.

    Ce n'est qu'un **nom candidat** : `_genere` dit ensuite si le fichier porte la marque d'un fichier genere.
    Un PDF n'est jamais un agrege : la migration ne supprime aucun PDF (invariant 1, E-V4-7).
    """
    minuscule = ms.nfc(nom).lower()
    if minuscule.endswith(".pdf"):
        return False
    if minuscule.endswith(".jsonl"):
        return True
    if "/" not in rel and ms.nfc(nom) in (ms.nfc(INDEX), ms.nfc(QUALITE)):
        return True
    return ms.nfc(nom).endswith(ms.nfc(TITRE_COURS))


def _premiere_ligne(chemin):
    """Premiere ligne du fichier, sans BOM, ou chaine vide s'il est illisible ou vide."""
    try:
        with open(chemin, "rb") as f:
            tete = f.read(4096).decode("utf-8", "replace")
    except OSError:
        return ""
    tete = tete.lstrip("\ufeff")
    return tete.splitlines()[0].strip() if tete.strip() else ""


def _export_genere(chemin):
    """Vrai si ce `.jsonl` a la forme de l'export de l'ancienne version (plan 6.4) : une ligne JSON par page.

    Aucune marque n'est ecrite dans un `.jsonl` : sa signature est la forme de ses lignes, les cles que
    `ecrire_jsonl` ecrivait. Un fichier vide, illisible ou d'une autre forme est un fichier de l'etudiant : il
    reste en place (E-V4-7).
    """
    try:
        with open(chemin, "rb") as f:
            lignes = [ligne for ligne in f.read().decode("utf-8", "replace").splitlines() if ligne.strip()]
    except OSError:
        return False
    if not lignes:
        return False
    for ligne in lignes:
        try:
            objet = json.loads(ligne)
        except ValueError:
            return False
        if not isinstance(objet, dict) or any(cle not in objet for cle in CLES_EXPORT):
            return False
    return True


def _genere(chemin, nom):
    """Vrai si ce fichier de synthese porte la marque d'un fichier ecrit par l'ancienne version (E-V4-7).

    Un `.md` genere commencait par `ms.MARQUE` (`ecrire_index`, `ecrire_qualite`, `ecrire_cours_md`) : c'est la
    marque qui distingue un agregat d'un fichier de l'etudiant, par exemple dans un cours de Moodle dont le
    dossier s'appelle `Textes`. Un PDF n'est jamais concerne.
    """
    if ms.nfc(nom).lower().endswith(".pdf"):
        return False
    if ms.nfc(nom).lower().endswith(".jsonl"):
        return _export_genere(chemin)
    return _premiere_ligne(chemin) == ms.MARQUE


def _comparable(chemin):
    return ocr._comparable(ocr._cle(chemin))


def _entree(cache, source_rel, ancien_rel):
    """(cle, entree) du document dans le cache : par sa cle d'abord, puis par l'ancien `sortie`."""
    voulue = _comparable(source_rel)
    ancienne = _comparable(DOSSIER + "/" + ancien_rel)
    for cle, entree in (cache.get("documents") or {}).items():
        if not isinstance(entree, dict):
            continue
        if _comparable(cle) == voulue:
            return cle, entree
    for cle, entree in (cache.get("documents") or {}).items():
        if not isinstance(entree, dict):
            continue
        sortie = entree.get("sortie")
        if isinstance(sortie, str) and sortie and _comparable(sortie) == ancienne:
            return cle, entree
    return None, None


def _sha256(chemin):
    return ocr._sha256(chemin)


def _meme_contenu(a, b):
    try:
        return _sha256(a) == _sha256(b)
    except OSError:
        return False


def _deplacer(ancien, cible):
    """Deplace le texte a cote de son document. La cible ne peut pas exister : l'appelant l'a verifie."""
    os.makedirs(os.path.dirname(cible), exist_ok=True)
    os.replace(ancien, cible)


def _elaguer(dossier):
    """Supprime les sous-dossiers vides, puis `dossier` s'il est vide. Vrai si `dossier` a disparu.

    Une erreur du systeme de fichiers (dossier non vide, verrou) laisse le dossier en place : c'est le
    sens du contrat 8.6, « sinon la laisser et le dire ».
    """
    try:
        noms = os.listdir(dossier)
    except OSError:
        return False
    for nom in noms:
        chemin = os.path.join(dossier, nom)
        if os.path.isdir(chemin) and not os.path.islink(chemin):
            _elaguer(chemin)
    try:
        os.rmdir(dossier)
        return True
    except OSError:
        return False


def _entree_migree(entree, source_rel, dest, sortie, empreinte):
    """Entree de cache d'un document dont le texte est deplace (contrat 8.2, 2.2)."""
    nouvelle = dict(entree)
    nouvelle["sortie"] = sortie
    nouvelle["format"] = "md"
    nouvelle["sortie_empreinte"] = empreinte
    nouvelle["remplace"] = bool(ocr._genere(dest, source_rel))
    nouvelle["original"] = None
    return nouvelle


def _entree_echec(entree, source_rel, dest):
    """Entree de cache d'un ancien « Difficile » converti en echec (O14, 2.2) : ni sortie ni format."""
    nouvelle = dict(entree)
    nouvelle["etat"] = "echec"
    nouvelle["motif"] = ETAT_DIFFICILE
    for cle in ("sortie", "format", "sortie_empreinte"):
        nouvelle.pop(cle, None)
    nouvelle["remplace"] = bool(ocr._genere(dest, source_rel))
    nouvelle["original"] = None
    return nouvelle


def migrer(dest, cfg):
    """Migre l'ancien dossier `Textes/` du coffre `dest` et rend `{"deplaces", "supprimes", "restants"}`.

    Sept etapes du contrat 8 : sans `Textes/`, rien a faire ; sinon chaque texte de document dont le
    document source existe est deplace a cote de lui, un ancien « Difficile » non edite est supprime et
    devient un echec, un texte sans document source reste en place, les agregats **qui portent la marque
    d'un fichier genere** sont supprimes (E-V4-7 : jamais un fichier de l'etudiant, jamais un PDF), et
    `Textes/` part si elle est vide. `restants` compte tout ce qui reste alors dans `Textes/`, `.md` ou non
    (E-V4-8), pour que l'annonce le dise. Le cache est ecrit apres **chaque** document deplace : une migration
    interrompue au milieu ne laisse pas de fiche fausse (E-V4-6). Aucun PDF n'est ouvert en ecriture. Une erreur
    du systeme de fichiers n'est pas avalee : l'appelant la signale et la migration sera reprise au demarrage
    suivant.
    """
    bilan = {"deplaces": 0, "supprimes": 0, "restants": 0}
    if not isinstance(dest, str) or not dest or not os.path.isdir(dest):
        return bilan
    racine = os.path.join(dest, DOSSIER)
    if not os.path.isdir(racine):
        return bilan

    cache = ocr.charger_cache(dest)
    agreges = []

    for rel, absolu in _fichiers(racine):
        nom = rel.rsplit("/", 1)[-1]
        if _agrege(rel, nom):
            if _genere(absolu, nom):
                agreges.append(absolu)
            continue                                  # sans la marque : fichier de l'etudiant, laisse (E-V4-7)
        if not nom.lower().endswith(".md"):
            continue
        source_rel = rel[: -len(".md")]
        source = os.path.join(dest, *source_rel.split("/"))
        cle, entree = _entree(cache, source_rel, rel)
        if not os.path.isfile(source):
            continue                                  # le document a disparu : le texte reste (8.4)

        edite = not ocr._regenerable(absolu)
        difficile = bool(entree) and entree.get("etat") == ETAT_DIFFICILE
        if difficile:
            cache["documents"][cle] = _entree_echec(entree, source_rel, dest)
            ocr.sauver_cache(dest, cache)             # E-V4-6 : le cache suit chaque document, pas la fin du lot
            if not edite:
                os.remove(absolu)                     # un texte non edite d'un « Difficile » part (O14)
                bilan["supprimes"] += 1
                continue

        cible = os.path.join(dest, *rel.split("/"))
        empreinte = None
        if os.path.exists(cible):
            if _meme_contenu(absolu, cible):
                os.remove(absolu)                     # doublon identique : l'ancien exemplaire part
                bilan["supprimes"] += 1
            else:
                continue                              # jamais d'ecrasement : le texte reste dans Textes/
        else:
            _deplacer(absolu, cible)
            bilan["deplaces"] += 1
            empreinte = _sha256(cible)

        if entree is not None and not difficile:
            if empreinte is None:
                empreinte = _sha256(cible)
            cache["documents"][cle] = _entree_migree(entree, source_rel, dest, rel, empreinte)
            ocr.sauver_cache(dest, cache)             # E-V4-6 : ecrit apres chaque document deplace

    for absolu in agreges:
        os.remove(absolu)
        bilan["supprimes"] += 1

    # E-V4-8 : tout fichier qui reste dans `Textes/` compte, `.md` ou non, pour que l'annonce le dise (8.6).
    if not _elaguer(racine) and os.path.isdir(racine):    # Textes/ part si elle est vide (8.6)
        bilan["restants"] = max(1, len(_fichiers(racine)))
    return bilan
