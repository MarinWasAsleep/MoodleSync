#!/usr/bin/env python3
"""MoodleSync, extraction du texte des scans : detection du moteur Tesseract et extraction d'une page.

Tache C1 : detection du moteur (Tesseract 4 ou 5) et reglages d'appel.
Tache C2 : une page (texte natif, rendu, reconnaissance, TSV, qualite) et le Markdown d'un document.
Tache C3 : cache, empreinte, reprise par page, file, document entier.
Tache C4 : PDF cherchable (identite, marque, controle, superposition d'une couche TSV, verification, remplacement).
Les sorties de cours (C5), la restauration et la reconciliation (Y2) n'existent pas encore.

Le moteur n'est pas forcement dans le PATH : la detection essaie, dans l'ordre du plan 5.2, le
chemin de la configuration (ocr_exe), shutil.which, le registre Windows, les chemins usuels, puis
macOS, enfin le paquet portable que installer_paquet decompresse dans le dossier des reglages (tache I1,
etape 6 du plan). Aucun appel reseau pendant l'extraction (invariant 6) : le seul appel reseau du module est
installer_paquet, action explicite de l'etudiant, qui passe par maj.py (import a l'usage). detecter ne leve
jamais et n'ecrit aucune trace technique. pypdf, Pillow et pypdfium2 sont importes a l'usage seulement (D11) :
sans eux, la detection reste utilisable.
"""
import copy, hashlib, hmac, json, logging, os, platform, re, shutil, stat, subprocess, sys, tempfile, threading, time, unicodedata, zipfile

from . import moteur as ms
from .marque import CLE_MARQUE, _entier_vrai, _marque_du_lecteur, lire_marque   # lire_marque : reexport du contrat 2.2

CACHE = ".moodlesync-ocr"
SEUIL_TEXTE = 80
SEUILS_QUALITE = (0.85, 0.70)   # conserves, non calibres (D11)
DELAI_PAGE = 120                # secondes par page pour le moteur (plan 5.4)
# Orientation du scan. Un scanner qui couche une page met le texte a 90 degres sans toucher au /Rotate du PDF :
# le rendu est droit, le texte ne l'est pas, et le moteur rend du bruit a faible confiance (mesure sur un article
# de revue scanne : 0,426 sans rotation, 0,919 apres). Quand la confiance de la page est sous le seuil, la page
# est reessayee aux trois autres orientations et la meilleure gagne, avec une marge pour ne pas tourner une page
# simplement mediocre.
SEUIL_ORIENTATION = 0.60
MARGE_ORIENTATION = 0.05
ORIENTATIONS = (90, 270, 180)   # sens horaire, apres l'essai sans rotation
MARQUE_DOC = "régénéré à chaque passage, supprime cette ligne pour garder le fichier tel quel"   # D4

# CREATE_NO_WINDOW (0x08000000, aucune console noire) et BELOW_NORMAL_PRIORITY_CLASS (0x00004000,
# priorite basse), sous Windows seulement : creationflags n'existe pas sur macOS.
CREATIONFLAGS = 0x08000000 | 0x00004000

MESSAGES = {
    "moteur_absent": "Le moteur d'extraction n'est pas encore installé. Indique où il se trouve dans les réglages.",
    "langue_manquante": "Il manque une langue de reconnaissance. MoodleSync utilise celle qui est disponible : la qualité peut baisser.",
    "protege": "Ce document est protégé par un mot de passe. MoodleSync ne le contourne pas : son texte n'a pas été extrait.",
    "illisible": "La page {n} n'a pas pu être lue. Elle est signalée dans le document, les autres pages sont intactes.",
    "corrompu": "Ce PDF est abîmé et n'a pas pu être ouvert. Les autres documents continuent.",
    "verrouille": "Ce fichier est ouvert dans un autre programme. Ferme-le et réessaie : rien n'a été modifié.",
    "trop_gros": "Ce document dépasse la taille maximale prévue ({mo} Mo). Augmente la limite dans les réglages pour en extraire le texte.",
    "refus_pdf": "Ce PDF est déjà lisible, signé ou en lecture seule : MoodleSync ne le modifie pas. Son texte reste disponible dans Mes textes.",
    "verification": "Le PDF cherchable n'a pas passé les contrôles. Ton fichier d'origine n'a pas été touché.",
    "modifie_main": "Ce fichier a été modifié depuis sa création par MoodleSync. Continuer le remplacera.",
    "pdf_genere": "« {nom} » est maintenant cherchable avec Ctrl+F. Ses pages d'origine sont conservées, l'original exact se retélécharge depuis Moodle.",
    "non_suivi": "Ce PDF ne vient pas d'un téléchargement de MoodleSync : il n'est pas remplacé. Son texte reste disponible dans Mes textes.",
    "hors_ligne": "Impossible de retélécharger l'original sans connexion. Ton PDF cherchable reste en place, avec ses pages d'origine. Réessaie une fois en ligne.",
    "restauration_differente": "Moodle propose une version différente de celle d'origine. Rien n'a été remplacé : lance une synchronisation.",
    # Phrases de ApiTextes (A1, ecarts 122 et 139) : recopiees de la section 5 du contrat, la seule source des phrases.
    "consentement_remplacer": "Le PDF sera remplacé sur place par une version cherchable qui garde ses pages d'origine. "
                              "Aucune copie de l'original n'est conservée, tu pourras le retélécharger depuis Moodle.",
    "mode_indisponible": "Ce mode n'existe pas. Choisis « Aucun » ou « Remplacer par une version cherchable ».",
    "installation_indisponible": "L'installation automatique n'est pas encore disponible. Indique l'emplacement du moteur "
                                 "dans les réglages.",
    "installation_indisponible_intel": "Le moteur ne s'installe pas automatiquement sur un Mac à processeur Intel. Si un "
                                       "moteur est déjà installé sur cet ordinateur, indique son emplacement dans les réglages.",
    # Phrases de l'installation du moteur (I1) : recopiees de la section 5 du contrat.
    "installation_faite": "Le moteur d'extraction est installé.",
    "installation_echec": "L'installation du moteur a échoué : rien n'a été modifié. Indique l'emplacement d'un moteur "
                          "déjà installé dans les réglages.",
    "paquet_hors_ligne": "Le moteur n'a pas pu être téléchargé : vérifie ta connexion Internet, puis réessaie. Tu peux "
                         "aussi indiquer l'emplacement d'un moteur déjà installé dans les réglages.",
    "paquet_invalide": "Le fichier téléchargé n'est pas celui attendu : il a été supprimé et rien n'a été installé. "
                       "Réessaie plus tard ou indique l'emplacement d'un moteur déjà installé dans les réglages.",
    "dossier_absent": "Le dossier de rangement n'existe pas encore : lance une synchronisation d'abord.",
    "fenetre_fermee": "La fenêtre n'est pas encore ouverte : réessaie dans un instant.",
    "valeur_invalide": "Valeur invalide.",
    "reglage_inconnu": "Réglage inconnu : {cle}",
    "chemin_introuvable": "Indique un chemin qui existe sur cet ordinateur.",
    "dossier_pris": "Ce nom est déjà celui d'un cours : choisis un autre dossier.",
    "occupe": "Une opération est déjà en cours : attends qu'elle se termine (ou annule-la).",
    # Phrases nouvelles de A3 (ecarts 137, 150, 159 et 161), a relire par D.
    "consentement_absent": "L'extraction du texte n'est pas activée. Active-la dans les réglages, puis réessaie.",
    "format_inconnu": "Ce format d'export n'existe pas. Choisis l'archive ZIP, l'archive avec JSONL ou le fichier Markdown.",
    "ouverture_refusee": "Ce document est introuvable ou n'est pas dans ton dossier de rangement : rien n'a été ouvert.",
    "ouverture_impossible": "Ce fichier n'a pas pu être ouvert. Cherche-le dans ton dossier de rangement.",
    "cible_dans_coffre": "Choisis un emplacement hors de ton dossier de rangement : l'export ne doit pas remplacer "
                         "tes cours ni tes textes.",
    "confirmation_lot": "{documents}, environ {pages}. Environ {mini} à {maxi} minutes. Tu peux continuer à utiliser "
                        "MoodleSync, mettre en pause ou fermer : la prochaine fois, ça reprend où tu t'es arrêté.",
    # Phrases des motifs d'echec et de la restauration d'un texte edite (refonte, 5.5) : les memes textes que la
    # table TX_MOTS de `textes.js`.
    "motif_difficile": "Le texte de ce document est trop abîmé pour être lu. Ton PDF est resté tel quel.",
    "motif_vide": "Aucun texte n'a été trouvé dans ce document. Ton PDF est resté tel quel.",
    "motif_illisible": "Ce document n'a pas pu être lu. Ton PDF est resté tel quel.",
    "motif_verification": "Le PDF cherchable n'a pas passé la vérification. Ton PDF est resté tel quel.",
    "motif_ecriture": "Le résultat n'a pas pu être écrit. Ton PDF est resté tel quel.",
    "motif_erreur": "Cette opération n'a pas abouti. Ton PDF est resté tel quel.",
    # E-V2-3 : un essai sur un document deja traite qui n'aboutit pas garde l'etat d'avant. Phrase a ajouter
    # au contrat 5.5 (ecrit au journal de R2c).
    "refaire_echec": "Ce document avait déjà été traité : ce nouvel essai n'a pas abouti. Ton PDF cherchable, "
                     "son texte et la copie de l'original sont restés en place.",
    "restauration_texte_garde": "Le PDF d'origine est remis. Le texte, que tu avais modifié, est resté en place.",
    # Phrases de l'API de la refonte (contrat 5.5), les memes textes que la table TX_MOTS de `textes.js`.
    "confirmation_traitement": "{n}, environ {p}, {m} à {x} minutes. {r} PDF seront remplacés par une version "
                               "cherchable ; une copie de chaque original est gardée.",
    "confirmation_restauration": "Remettre le PDF d'origine et supprimer le texte ?",
    "copie_vide": "Ce document n'a pas de texte à copier.",
    "depot_pas_pdf": "Seuls les PDF peuvent être déposés.",
    "confirmation_originaux": "Supprimer les {n} d'originaux ({o}) ? Les documents concernés ne seront plus "
                              "restaurables que par Moodle.",
}
# Les codes numerique, signe et lecture_seule (invariant 3) portent la phrase de refus_pdf (section 5 du contrat).
MESSAGES.update({code: MESSAGES["refus_pdf"] for code in ("numerique", "signe", "lecture_seule")})


class ErreurOcr(ms.Erreur):
    """Erreur prevue de l'extraction : `code` fixe, message pris dans MESSAGES (aucune trace technique)."""

    def __init__(self, code, **champs):
        modele = MESSAGES.get(code, code)
        try:
            message = modele.format(**champs)
        except (KeyError, IndexError, ValueError):
            message = modele
        super().__init__(message)
        self.code = code

BLOC_ABSENT = {
    "present": False, "version": "", "source": "", "exe": "",
    "langues": [], "langues_effectives": "", "repli": False,
    "message": MESSAGES["moteur_absent"], "tessdata": "", "majeure": 0,
}

RE_VERSION = re.compile(r"tesseract\s+v?(\d+(?:\.\d+)*)")
RE_LANGUE = re.compile(r"^[a-z]{3}(?:_[a-z0-9]+)*$")


def executer(args, *, delai, arreter=None):
    """Lance un processus avec une liste d'arguments, jamais un shell. Renvoie (code, stdout, stderr) en octets.

    Sous Windows, CREATE_NO_WINDOW et la priorite basse evitent la console noire et la contention.
    Le delai borne l'attente ; arreter() (s'il est fourni) interrompt plus tot. Point d'entree
    remplacable par les tests.
    """
    drapeaux = CREATIONFLAGS if os.name == "nt" else 0
    try:
        p = subprocess.Popen(list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=drapeaux)
    except OSError:
        return -1, b"", b""
    debut = time.monotonic()
    try:
        while True:
            try:
                out, err = p.communicate(timeout=0.2)
                return p.returncode, out, err
            except subprocess.TimeoutExpired:
                if (arreter is not None and arreter()) or time.monotonic() - debut >= delai:
                    p.kill()
                    try:
                        out, err = p.communicate(timeout=1)
                    except subprocess.TimeoutExpired:
                        out, err = b"", b""
                    return -1, out, err
    except Exception:
        return -1, b"", b""
    finally:
        # Tue le processus s'il tourne encore quand une exception sort, et donne un delai court
        # au dernier communicate apres kill.
        if p.poll() is None:
            p.kill()
            try:
                p.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                pass


def _exe_config(cfg):
    exe = (cfg.get("ocr_exe") or "").strip()
    return exe if exe and os.path.isfile(exe) else None


def _exe_registre():
    """Chemin de tesseract.exe lu dans le registre Windows (Path ou InstallDir), ou None."""
    try:
        import winreg
    except ImportError:
        return None
    cles = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Tesseract-OCR"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Tesseract-OCR"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Tesseract-OCR"),
    )
    for racine, cle in cles:
        try:
            with winreg.OpenKey(racine, cle) as k:
                for valeur in ("Path", "InstallDir"):
                    try:
                        dossier = winreg.QueryValueEx(k, valeur)[0]
                    except (OSError, TypeError):
                        continue
                    if not isinstance(dossier, str):
                        continue
                    exe = os.path.join(dossier, "tesseract.exe")
                    if os.path.isfile(exe):
                        return exe
        except OSError:
            continue
    return None


def _exe_usuel():
    """Chemins usuels de tesseract (Windows et macOS), hors registre et hors PATH."""
    candidats = []
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        progdata = os.environ.get("ProgramData") or r"C:\ProgramData"
        domicile = os.path.expanduser("~")
        candidats += [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.join(local, "Programs", "Tesseract-OCR", "tesseract.exe"),
            os.path.join(local, "Tesseract-OCR", "tesseract.exe"),
            os.path.join(progdata, "chocolatey", "bin", "tesseract.exe"),
            os.path.join(domicile, "scoop", "shims", "tesseract.exe"),
        ]
    else:
        candidats += [
            "/opt/homebrew/bin/tesseract",
            "/usr/local/bin/tesseract",
            "/usr/bin/tesseract",
        ]
    return next((p for p in candidats if os.path.isfile(p)), None)


def _plateforme():
    """Systeme courant, au sens de sys.platform : `win32` ou `darwin` ont un paquet du moteur (I1, ecart 242)."""
    return sys.platform


def _architecture():
    """Architecture du processeur, au sens de platform.machine() : `arm64` sur un Mac a puce Apple, `x86_64` sur un Mac
    Intel (ecart 291). platform.machine() plutot que sys.maxsize : maxsize ne dit que 32 ou 64 bits, jamais Intel ou ARM."""
    return platform.machine()


def _nom_exe(plateforme=None):
    """Nom du moteur a la racine du paquet portable : `tesseract.exe` sous Windows, `tesseract` ailleurs."""
    return "tesseract.exe" if (plateforme or _plateforme()) == "win32" else "tesseract"


def _dossier_paquet():
    """Dossier du paquet portable (I1) : dans le dossier des reglages, jamais dans le dossier de cours."""
    return os.path.join(ms.APP_DIR, "tesseract")


def _exe_portable():
    """Moteur du paquet portable installe par installer_paquet, ou None."""
    exe = os.path.join(_dossier_paquet(), _nom_exe())
    return exe if os.path.isfile(exe) else None


def _candidats_moteur(cfg):
    """Chemins candidats dans l'ordre du plan 5.2, un par un : (chemin, source). Les sources suivantes ne sont
    consultees que si les precedentes ne donnent rien d'utilisable."""
    for lire, source in ((lambda: _exe_config(cfg), "config"), (lambda: shutil.which("tesseract"), "path"),
                         (lambda: _exe_registre(), "registre"), (lambda: _exe_usuel(), "usuel"),
                         (lambda: _exe_portable(), "portable")):
        exe = lire()
        if exe:
            yield exe, source


def _repond(exe):
    """(version, majeure) si `exe --version` repond avec une version 4 ou 5, sinon None (ecart 247)."""
    code, out, err = executer([exe, "--version"], delai=5)
    version, majeure = _version(out + err)
    if code != 0 or majeure not in (4, 5):
        return None
    return version, majeure


def _trouver(cfg):
    """Renvoie (chemin, source, version, majeure) du premier candidat qui repond a --version avec une version 4 ou 5,
    dans l'ordre du plan 5.2, ou (None, None, "", 0). Un candidat qui existe mais ne repond pas, ou rend une version 3,
    est passe : il ne masque pas les suivants (ecart 247)."""
    for exe, source in _candidats_moteur(cfg):
        vu = _repond(exe)
        if vu:
            return exe, source, vu[0], vu[1]
    return None, None, "", 0


def _version(stdout):
    """Version et numero majeur depuis la sortie de tesseract --version."""
    texte = (stdout or b"").decode("utf-8", "replace")
    m = RE_VERSION.search(texte)
    if not m:
        return "", 0
    parties = m.group(1).split(".")
    try:
        majeure = int(parties[0])
    except ValueError:
        return "", 0
    return ".".join(parties[:3]), majeure


def _langues(stdout):
    """Codes de langue depuis la sortie de tesseract --list-langs."""
    texte = (stdout or b"").decode("utf-8", "replace")
    return [ligne.strip() for ligne in texte.splitlines() if RE_LANGUE.match(ligne.strip())]


def _langues_effectives(demandees, disponibles):
    """Langues a employer apres repli.

    Les langues de reconnaissance excluent osd (orientation) et equ (equations), qui ne
    reconnaissent pas de texte. Si aucune langue demandee n'est disponible : fra si possible, sinon eng,
    sinon la premiere langue de reconnaissance disponible. repli est vrai des qu'un repli a eu
    lieu ; dans ce cas langues_effectives == "" signifie « non utilisable » pour C2 (ne pas
    lancer -l "").
    """
    reconnues = [l for l in disponibles if l not in ("osd", "equ")]
    voulues = [l for l in (demandees or "").split("+") if l]
    gardees = [l for l in voulues if l in reconnues]
    if gardees:
        return "+".join(gardees), gardees != voulues
    if "fra" in reconnues:
        return "fra", True
    if "eng" in reconnues:
        return "eng", True
    if reconnues:
        return reconnues[0], True
    return "", True


def _dossier_tessdata(cfg, exe):
    """Dossier des donnees de langue qui existe : ocr_tessdata, puis TESSDATA_PREFIX, puis le
    dossier tessdata a cote du programme. Chaine vide si aucun n'existe (C2 lira « ne pas passer
    --tessdata-dir »)."""
    d = (cfg.get("ocr_tessdata") or "").strip()
    if d and os.path.isdir(d):
        return d
    d = (os.environ.get("TESSDATA_PREFIX") or "").strip()
    if d and os.path.isdir(d):
        return d
    d = os.path.join(os.path.dirname(exe), "tessdata")
    if os.path.isdir(d):
        return d
    return ""


def _bloc_absent():
    """Bloc moteur absent, neuf a chaque appel : aucune liste partagee entre les blocs."""
    return copy.deepcopy(BLOC_ABSENT)


def detecter(cfg):
    """Detecte Tesseract et renvoie le bloc moteur (forme 2.7) plus tessdata et majeure. Ne leve jamais.

    Version 4 ou 5 exigee ; une version 3 est traitee comme un moteur absent.
    """
    try:
        return _detecter(cfg)
    except Exception:
        return _bloc_absent()


def _detecter(cfg):
    exe, source, version, majeure = _trouver(cfg)
    if not exe:
        return _bloc_absent()
    return _bloc_moteur(cfg, exe, source, version, majeure)


def _detecter_chemin(cfg, exe, source):
    """Bloc moteur d'un executable precis, sans parcourir les candidats (ecart 247). Moteur absent si `exe` ne repond
    pas avec une version 4 ou 5. Ne leve jamais."""
    try:
        vu = _repond(exe)
        return _bloc_moteur(cfg, exe, source, vu[0], vu[1]) if vu else _bloc_absent()
    except Exception:
        return _bloc_absent()


def _bloc_moteur(cfg, exe, source, version, majeure):
    bloc = _bloc_absent()
    tessdata = _dossier_tessdata(cfg, exe)
    args = [exe, "--list-langs"]
    if tessdata:
        args += ["--tessdata-dir", tessdata]
    code, out_langues, err_langues = executer(args, delai=5)
    langues = _langues(out_langues + err_langues)
    effectives, repli = _langues_effectives(cfg.get("ocr_langues") or "fra+eng", langues)
    bloc.update({
        "present": True,
        "version": version,
        "source": source,
        "exe": exe,
        "langues": langues,
        "langues_effectives": effectives,
        "repli": repli,
        "message": MESSAGES["langue_manquante"] if repli else "",
        "tessdata": tessdata,
        "majeure": majeure,
    })
    return bloc


def reglages_depuis(cfg):
    """Reglages d'appel Tesseract (contrat 3.1), avec les langues effectives apres repli.

    dpi et psm reprennent 300 et 3 si la valeur de config.json est illisible (ValueError ou
    TypeError). tessdata == "" signifie « ne pas passer --tessdata-dir » (lecture attendue de C2).
    """
    return _reglages_moteur(cfg, detecter(cfg))


def _reglages_moteur(cfg, moteur):
    """Corps de reglages_depuis pour un bloc moteur deja detecte : une seule detection par document (ecart 35)."""
    try:
        dpi = int(cfg.get("ocr_dpi", 300))
    except (ValueError, TypeError):
        dpi = 300
    try:
        psm = int(cfg.get("ocr_psm", 3))
    except (ValueError, TypeError):
        psm = 3
    return {
        "langues": moteur["langues_effectives"],
        "dpi": dpi,
        "psm": psm,
        "oem": 1,
        "moteur": moteur["version"],
        "tessdata": moteur["tessdata"],
    }


# ---------------------------------------------------------------------------------------------
# Tache I1 : installation du moteur a la demande (paquet portable, contrat 3.1 et D6).
# ---------------------------------------------------------------------------------------------
DEPOT_MOTEUR = "MarinWasAsleep/MoodleSync-moteur"     # une release par version du moteur
# Un paquet par systeme (decisions du 9 et du 10 novembre 2026), choisi selon sys.platform. Chaque archive porte le
# moteur (`tesseract.exe` et ses DLL, ou `tesseract` et `lib/`) et `tessdata/` a sa racine.
URL_BASE_PAQUETS = "https://github.com/" + DEPOT_MOTEUR + "/releases/download/v1.0.0/"
NOM_PAQUET = {"win32": "MoodleSync-moteur-windows.zip", "darwin": "MoodleSync-moteur-macos.zip"}
# SHA-256 de chaque fichier de NOM_PAQUET, inscrit dans le code et jamais lu dans la reponse du serveur (decision de
# Maxence du 9 novembre 2026, meme confiance que maj.py). Un systeme sans nom ou sans empreinte n'a pas de paquet :
# installer_paquet repond installation_indisponible, sans reseau ni decompression, et ne prend jamais celui de l'autre.
EMPREINTE_PAQUET = {
    "win32": "ba86c780c2c5aacbe66dd4c40ca0093ef1f80426df2cb9b226a1faf3c1a1f51d",
    "darwin": "a7d6198ef730cfd6a93e2b3eb63d71f13bec1bfe60034be32ca93d23d9e72a96",
}
TAILLE_MAX_PAQUET = 300 * 1024 * 1024                 # le paquet annonce fait environ 65 Mo (plan 3.3)
TAILLE_MAX_DECOMPRESSE = 1024 * 1024 * 1024
BLOC_TELECHARGEMENT = 256 * 1024
_VERROU_PAQUET = threading.Lock()


def _paquet(plateforme=None, architecture=None):
    """(nom, empreinte SHA-256) du paquet du systeme `plateforme` et de l'architecture `architecture` (les courants par
    defaut), ou None s'il n'en a pas. Le paquet macOS ne porte qu'un moteur arm64 : un Mac Intel n'en a pas (ecart 291)."""
    plateforme = plateforme or _plateforme()
    if plateforme == "darwin" and (architecture if architecture is not None else _architecture()) != "arm64":
        return None
    nom = NOM_PAQUET.get(plateforme) if isinstance(plateforme, str) else None
    empreinte = (EMPREINTE_PAQUET.get(plateforme) or "").strip().lower() if nom else ""
    return (nom, empreinte) if nom and empreinte else None


def _horloge():
    return time.monotonic()


def _parties_sures(nom):
    """Composants d'un nom d'entree d'archive, ou None si le nom sort du dossier cible : chemin absolu ou de lecteur,
    `..`, octet nul, composant a deux-points (flux Windows). Les antislashs valent des separateurs : un zip fait sous
    Windows peut les garder tels quels."""
    texte = str(nom or "").replace("\\", "/")
    if not texte or "\x00" in texte or texte.startswith("/"):
        return None
    parties = [p for p in texte.split("/") if p not in ("", ".")]
    if not parties or any(p == ".." or ":" in p for p in parties):
        return None
    return parties


def _supprimer(chemin):
    try:
        if os.path.isdir(chemin) and not os.path.islink(chemin):
            shutil.rmtree(chemin)
        elif os.path.lexists(chemin):
            os.remove(chemin)
    except OSError:
        pass


def _taille_annoncee(reponse):
    """Taille que le serveur annonce (en-tete Content-Length), 0 si elle manque ou n'a pas de sens."""
    try:
        taille = int(reponse.headers.get("Content-Length") or 0)
    except (AttributeError, TypeError, ValueError):
        return 0
    return taille if taille > 0 else 0


def _telecharger_paquet(url, destination, progres, arreter):
    """Telecharge `url` dans `destination` en flux. Rend (empreinte SHA-256 hexadecimale, octets) ou None si l'arret
    est demande. `progres(recu, total)` est appele au plus quatre fois par seconde ; `total` est la taille annoncee
    par le serveur, 0 si elle est inconnue. Une taille annoncee au-dessus de TAILLE_MAX_PAQUET est refusee avant le
    premier octet."""
    from . import maj
    h, recu, dernier = hashlib.sha256(), 0, None
    with maj.ouvrir(url, timeout=60) as r, open(destination, "wb") as f:
        taille = _taille_annoncee(r)
        if taille > TAILLE_MAX_PAQUET:
            raise ErreurOcr("paquet_invalide")
        while True:
            if arreter and arreter():
                return None
            bloc = r.read(BLOC_TELECHARGEMENT)
            if not bloc:
                break
            recu += len(bloc)
            if recu > TAILLE_MAX_PAQUET:
                raise ErreurOcr("paquet_invalide")
            h.update(bloc)
            f.write(bloc)
            maintenant = _horloge()
            if progres and (dernier is None or maintenant - dernier >= 0.25):
                dernier = maintenant
                progres(recu, taille)
    return h.hexdigest(), recu


def _decompresser_paquet(archive, dossier, arreter):
    """Decompresse `archive` dans `dossier` (neuf). Tout est verifie avant la premiere ecriture : un nom qui sort du
    dossier, un lien symbolique, une taille demesuree, l'absence du moteur a la racine. Rend False si l'arret est
    demande. Leve ErreurOcr(paquet_invalide) pour une archive inacceptable."""
    try:
        z = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError):
        raise ErreurOcr("paquet_invalide")
    with z:
        membres, total = [], 0
        for info in z.infolist():
            parties = _parties_sures(info.filename)
            if parties is None:
                raise ErreurOcr("paquet_invalide")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ErreurOcr("paquet_invalide")
            cible = os.path.join(dossier, *parties)
            if os.path.commonpath([os.path.realpath(dossier), os.path.realpath(cible)]) != os.path.realpath(dossier):
                raise ErreurOcr("paquet_invalide")
            total += info.file_size
            if total > TAILLE_MAX_DECOMPRESSE:
                raise ErreurOcr("paquet_invalide")
            membres.append((info, cible, info.is_dir() or info.filename.replace("\\", "/").endswith("/")))
        if not any(not est_dossier and os.path.dirname(os.path.relpath(c, dossier)) == "" and
                   os.path.basename(c) == _nom_exe() for _, c, est_dossier in membres):
            raise ErreurOcr("paquet_invalide")
        if not any(not est_dossier and os.path.relpath(c, dossier).replace(os.sep, "/").split("/")[0] == "tessdata"
                   and c.lower().endswith(".traineddata") for _, c, est_dossier in membres):
            raise ErreurOcr("paquet_invalide")                  # ecart 252 : pas de donnees de langue, pas de moteur utilisable
        for info, cible, est_dossier in membres:
            if arreter and arreter():
                return False
            if est_dossier:
                os.makedirs(cible, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(cible), exist_ok=True)
            with z.open(info) as source, open(cible, "wb") as sortie:
                shutil.copyfileobj(source, sortie)
    exe = os.path.join(dossier, _nom_exe())
    if os.name != "nt":
        os.chmod(exe, os.stat(exe).st_mode | 0o755)
    return True


def _mettre_en_place(neuf, cible):
    """Pose le dossier `neuf` a la place de `cible` par renommage (meme disque). L'ancienne installation reste en
    place si le renommage echoue."""
    ancien = None
    if os.path.lexists(cible):
        ancien = tempfile.mkdtemp(prefix=".tesseract-ancien-", dir=os.path.dirname(cible))
        os.rmdir(ancien)
        os.rename(cible, ancien)
    try:
        os.rename(neuf, cible)
    except OSError:
        if ancien:
            os.rename(ancien, cible)
        raise
    if ancien:
        _supprimer(ancien)


def installer_paquet(progres=None, arreter=None):
    """Telecharge, verifie et installe le moteur portable (contrat 3.1, D6). Action explicite de l'etudiant, seul appel
    reseau du module (invariant 6) : il passe par maj.py, hotes GitHub en HTTPS seulement.

    Rend {"ok": True, "version": ...}, {"annule": True} ou {"erreur": phrase de MESSAGES} ; ne leve jamais, aucune
    trace technique (invariant 9, le detail part dans erreurs.txt). Le SHA-256 du fichier est compare a
    l'empreinte du paquet de ce systeme (Windows ou macOS, jamais celui de l'autre) avant d'ouvrir l'archive ; un fichier
    different est supprime. La decompression se fait dans un dossier temporaire a cote de la cible, puis par renommage :
    une installation interrompue ne laisse aucun dossier a moitie ecrit. Le moteur neuf est detecte a son emplacement temporaire avant de remplacer quoi que ce soit : une
    installation precedente n'est touchee que si le nouveau paquet fonctionne. Destination : le dossier des reglages
    (`tesseract`), jamais le dossier de cours."""
    choix = _paquet()
    if not choix:
        # Un Mac Intel : refus avant toute requete, avec une phrase qui dit pourquoi (ecart 291).
        intel = _plateforme() == "darwin" and _architecture() != "arm64"
        return {"erreur": MESSAGES["installation_indisponible_intel" if intel else "installation_indisponible"]}
    nom_paquet, empreinte = choix
    if not _VERROU_PAQUET.acquire(blocking=False):
        return {"erreur": MESSAGES["occupe"]}
    parent = os.path.dirname(_dossier_paquet())
    fichier = dossier = None
    try:
        from . import maj
        if arreter and arreter():
            return {"annule": True}
        os.makedirs(parent, exist_ok=True)
        for nom in os.listdir(parent):                      # restes d'une installation tuee en route (fermeture)
            if nom.startswith((".paquet-", ".tesseract-")):
                _supprimer(os.path.join(parent, nom))
        url = URL_BASE_PAQUETS + nom_paquet             # adresse fixe de la release, aucune requete a l'API de GitHub
        if not maj.hote_autorise(url):
            return {"erreur": MESSAGES["paquet_invalide"]}
        descripteur, fichier = tempfile.mkstemp(prefix=".paquet-", suffix=".part", dir=parent)
        os.close(descripteur)
        vu = _telecharger_paquet(url, fichier, progres, arreter)
        if vu is None:
            return {"annule": True}
        if not hmac.compare_digest(vu[0], empreinte):
            _supprimer(fichier)
            return {"erreur": MESSAGES["paquet_invalide"]}
        dossier = tempfile.mkdtemp(prefix=".tesseract-", dir=parent)
        if not _decompresser_paquet(fichier, dossier, arreter):
            return {"annule": True}
        try:
            cfg = ms.charger_config()
        except Exception:
            cfg = {}
        # Le moteur neuf est verifie a son emplacement temporaire, par son chemin connu : ni l'ordre des candidats
        # (ecart 247) ni une installation precedente (ecart 248) n'entrent en jeu, et rien n'est remplace avant.
        bloc = _detecter_chemin(cfg, os.path.join(dossier, _nom_exe()), "portable")
        if not bloc.get("present"):
            return {"erreur": MESSAGES["installation_echec"]}
        _mettre_en_place(dossier, _dossier_paquet())
        dossier = None
        return {"ok": True, "version": bloc.get("version") or ""}
    except ErreurOcr as e:
        return {"erreur": str(e)}
    except (OSError, ms.Erreur) as e:
        _signaler(e)
        # Le reseau d'abord : les erreurs de connexion sont des OSError, comme celles du disque. Les erreurs de la
        # bibliotheque HTTP portent `reason` ou `code`, une erreur de disque non (le module n'en nomme aucune : 3.1).
        reseau = isinstance(e, (ConnectionError, TimeoutError)) or hasattr(e, "reason") or hasattr(e, "code")
        return {"erreur": MESSAGES["paquet_hors_ligne" if reseau else "installation_echec"]}
    except Exception as e:
        _signaler(e)
        return {"erreur": MESSAGES["installation_echec"]}
    finally:
        if fichier:
            _supprimer(fichier)
        if dossier:
            _supprimer(dossier)
        _VERROU_PAQUET.release()


# ---------------------------------------------------------------------------------------------
# Tache C2 : une page (texte natif, rendu, reconnaissance, TSV, qualite) et le Markdown d'un document.
# ---------------------------------------------------------------------------------------------
ACTION = "Texte des cours"


def _signaler(e):
    """Detail technique dans erreurs.txt (invariant 9) ; la phrase lisible vient de MESSAGES."""
    try:
        ms.message_erreur(e, ACTION)
    except Exception:
        pass


def _est_pdf(chemin):
    """Un PDF, y compris le fichier temporaire de l'invariant 5 (`<nom>.pdf.ocr.part`), qui est un PDF sans en avoir
    le nom : sans cela, la verification du rendu ne pourrait jamais rendre le fichier temporaire (ecart 71)."""
    nom = (chemin or "").lower()
    return nom.endswith(".pdf") or nom.endswith(".pdf.ocr.part")


# ------------------------------------------------------------------ texte natif
_LECTEUR = {"cle": None, "lecteur": None}
_VERROU_LECTEUR = threading.Lock()


def _ouvrir_pdf(chemin):
    """Lecteur pypdf du PDF, garde pour le prochain appel tant que le fichier ne change pas.

    Leve ErreurOcr « protege » (mot de passe non vide) ou « corrompu ». Un PDF chiffre dont le mot
    de passe utilisateur est vide s'ouvre comme dans n'importe quel lecteur : rien n'est contourne.
    """
    import pypdf
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        st = os.stat(chemin)
    except PermissionError as e:       # contrat 3.1 : une permission refusee a la lecture de la source est `verrouille`
        _signaler(e)
        raise ErreurOcr("verrouille") from None
    except OSError as e:
        _signaler(e)
        raise ErreurOcr("corrompu") from None
    cle = (os.path.abspath(chemin), st.st_mtime_ns, st.st_size)
    with _VERROU_LECTEUR:
        if _LECTEUR["cle"] == cle:
            return _LECTEUR["lecteur"]
    try:
        lecteur = pypdf.PdfReader(chemin)
        chiffre = lecteur.is_encrypted
    except PermissionError as e:
        _signaler(e)
        raise ErreurOcr("verrouille") from None
    except Exception as e:
        _signaler(e)
        raise ErreurOcr("corrompu") from None
    if chiffre:
        try:
            ouvert = bool(lecteur.decrypt(""))
        except Exception as e:
            _signaler(e)
            ouvert = False
        if not ouvert:
            raise ErreurOcr("protege")
    try:
        len(lecteur.pages)
    except Exception as e:
        _signaler(e)
        raise ErreurOcr("corrompu") from None
    with _VERROU_LECTEUR:
        _LECTEUR["cle"], _LECTEUR["lecteur"] = cle, lecteur
    return lecteur


def _normaliser_natif(texte):
    """Normalisation du texte natif (plan 5.3) sans nettoyage excessif : NFC, caracteres de controle,
    espaces multiples, coupure de mot en fin de ligne (seulement avant une minuscule), sauts de paragraphe."""
    t = ms.nfc(texte or "").replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("­\n", "")
    t = "".join(c for c in t if c in "\n\t" or (unicodedata.category(c) not in ("Cc", "Cf")))
    t = re.sub(r"[ \t]+", " ", t)
    t = "\n".join(ligne.strip(" ") for ligne in t.split("\n"))
    t = re.sub(r"(?<=[^\W\d_])-\n([^\W\d_])", lambda m: m.group(1) if m.group(1).islower() else m.group(0), t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _texte_natif(page):
    try:
        return page.extract_text() or ""
    except Exception:
        return ""


def _a_image(page):
    """Vrai si la page porte une image. En cas de doute (lecture impossible), vrai : mieux vaut tenter la reconnaissance."""
    try:
        return len(page.images) > 0
    except Exception:
        return True


def decider_source(texte_natif):
    """« texte » si le texte natif compte au moins SEUIL_TEXTE caracteres alphanumeriques, sinon « ocr »."""
    utiles = sum(1 for c in (texte_natif or "") if c.isalnum())
    return "texte" if utiles >= SEUIL_TEXTE else "ocr"


def classer(confiance):
    """Niveau de qualite d'une confiance de 0 a 1 : bon, a_verifier, difficile ; None donne vide (T4)."""
    if confiance is None:
        return "vide"
    if confiance >= SEUILS_QUALITE[0]:
        return "bon"
    if confiance >= SEUILS_QUALITE[1]:
        return "a_verifier"
    return "difficile"


# ------------------------------------------------------------------ rendu
def _preparer(image, autocontraste=True):
    """Niveaux de gris, et autocontraste pour la reconnaissance (plan 5.3). Une transparence est composee sur fond
    blanc. `autocontraste=False` rend l'image brute : c'est elle que compare la verification du rendu (D9, ecart 69)."""
    from PIL import Image, ImageOps
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        fond = Image.new("RGBA", rgba.size, "white")
        image = Image.alpha_composite(fond, rgba)
    gris = image.convert("L")
    return ImageOps.autocontrast(gris) if autocontraste else gris


def _rendre_pdf(chemin, numero, dpi):
    import pypdfium2 as pdfium   # import paresseux (D11) : absent, l'appel echoue proprement
    pdf = pdfium.PdfDocument(chemin)
    try:
        return pdf[numero - 1].render(scale=dpi / 72).to_pil().convert("L")
    finally:
        pdf.close()


def _ouvrir_image(chemin, numero):
    from PIL import Image, ImageOps
    with Image.open(chemin) as im:
        im.seek(numero - 1)   # numero compte les cadres d'un TIFF ; EOFError au-dela
        return ImageOps.exif_transpose(im).copy()


def rendre_page(chemin, numero, dpi, *, preparer=True):
    """Image Pillow en niveaux de gris de la page `numero` (base 1) d'un PDF au `dpi` donne, ou du
    cadre `numero` d'une image. Point d'entree remplacable par les tests. `preparer=False` rend l'image brute, sans
    autocontraste : c'est la seule forme que compare la verification du rendu (D9, ecart 69). Leve ErreurOcr « illisible »."""
    try:
        if numero < 1:
            raise ValueError("numero de page invalide")
        image = _rendre_pdf(chemin, numero, dpi) if _est_pdf(chemin) else _ouvrir_image(chemin, numero)
        return _preparer(image, preparer)
    except Exception as e:
        _signaler(e)
        raise ErreurOcr("illisible", n=numero) from None


# ------------------------------------------------------------------ TSV
def parser_tsv(tsv):
    """Mots (niveau 5) d'une sortie TSV de Tesseract : {"bloc","par","ligne","x","y","l","h","conf","texte"}.

    `conf` est ramenee de 0 a 1 (le TSV donne 0 a 100, D5) ; une valeur negative reste negative et sera
    ignoree par reconstruire. Les lignes mal formees et les mots vides sont ecartes.
    """
    mots = []
    for ligne in (tsv or "").splitlines():
        champs = ligne.split("\t", 11)
        if len(champs) < 12:
            continue
        try:
            if int(champs[0]) != 5:
                continue
            bloc, par, lig = int(champs[2]), int(champs[3]), int(champs[4])
            x, y, l, h = (int(champs[i]) for i in (6, 7, 8, 9))
            conf = float(champs[10]) / 100
        except ValueError:
            continue
        texte = champs[11].strip()
        if not texte:
            continue
        mots.append({"bloc": bloc, "par": par, "ligne": lig, "x": x, "y": y, "l": l, "h": h,
                     "conf": conf, "texte": texte})
    return mots


def reconstruire(mots):
    """(texte, confiance) : mots ordonnes par bloc, paragraphe, ligne, abscisse. Un saut de ligne entre les
    lignes, une ligne vide entre les paragraphes. Confiance moyenne de 0 a 1 sur les mots a confiance
    positive ou nulle, arrondie a 3 decimales ; None s'il n'y en a aucun."""
    ordre = sorted(mots, key=lambda m: (m["bloc"], m["par"], m["ligne"], m["x"]))
    paragraphes, courant, cle_ligne, cle_par = [], [], None, None
    for m in ordre:
        if (m["bloc"], m["par"]) != cle_par:
            if courant:
                paragraphes.append(courant)
            courant, cle_ligne, cle_par = [], None, (m["bloc"], m["par"])
        if m["ligne"] != cle_ligne:
            courant.append([])
            cle_ligne = m["ligne"]
        courant[-1].append(m["texte"])
    if courant:
        paragraphes.append(courant)
    texte = "\n\n".join("\n".join(" ".join(ligne) for ligne in par) for par in paragraphes)
    valeurs = [min(m["conf"], 1.0) for m in mots if m["conf"] >= 0]
    return texte, (round(sum(valeurs) / len(valeurs), 3) if valeurs else None)


# ------------------------------------------------------------------ une page
def _reconnaitre(image, numero, reglages, exe, arreter):
    """Lance le moteur sur l'image (fichier temporaire du systeme, supprime ensuite) et renvoie les mots."""
    dpi = int(reglages.get("dpi") or 300)
    fd, temp = tempfile.mkstemp(prefix="moodlesync-ocr-", suffix=".png")
    os.close(fd)
    try:
        image.save(temp, format="PNG", dpi=(dpi, dpi), compress_level=1)
        args = [exe, temp, "stdout", "-l", reglages["langues"], "--psm", str(reglages.get("psm", 3)),
                "--oem", str(reglages.get("oem", 1))]
        if reglages.get("tessdata"):
            args += ["--tessdata-dir", reglages["tessdata"]]
        args += ["-c", "tessedit_create_tsv=1"]
        code, sortie, erreur = executer(args, delai=DELAI_PAGE, arreter=arreter)
    finally:
        try:
            os.remove(temp)
        except OSError:
            pass
    if code != 0:
        if arreter is not None and arreter():
            raise ms.Annule()
        _signaler(RuntimeError(f"Reconnaissance de la page {numero} : code {code}. "
                               + (erreur or b"")[:500].decode("utf-8", "replace")))
        raise ErreurOcr("illisible", n=numero)
    return parser_tsv((sortie or b"").decode("utf-8", "replace"))


def _valeur_confiance(confiance):
    """Confiance utilisable pour comparer deux essais : une page sans mot vaut moins que tout."""
    return -1.0 if confiance is None else float(confiance)


def _reconnaitre_orientee(image, numero, reglages, exe, arreter):
    """(mots, angle) : reconnaissance de la page, en essayant les rotations quand la premiere lecture est douteuse.

    Un scan couche donne du texte illisible a faible confiance : la page est alors tournee de 90, 270 puis 180
    degres dans le sens horaire. Une rotation n'est adoptee que si elle est a la fois sure (confiance au moins
    SEUIL_ORIENTATION) et nettement meilleure que la lecture droite (au moins MARGE_ORIENTATION de plus) : sur du
    bruit, ou la confiance reste basse partout, aucune rotation ne l'emporte et la page garde sa lecture droite.
    Le premier essai qui remplit ces conditions arrete la boucle, donc une page droite coute une reconnaissance et
    une page couchee deux (mesure : 14 appels pour trois pages couchees avant cette regle, 8 apres).
    `angle` est l'angle horaire applique a l'image, 0 si aucun.
    """
    droite = (None, [])
    for angle in (0,) + ORIENTATIONS:
        essai = image if angle == 0 else image.rotate(-angle, expand=True)
        try:
            try:
                mots = _reconnaitre(essai, numero, reglages, exe, arreter)
            except ms.Annule:
                raise
            except Exception:
                if angle == 0:
                    raise           # la premiere lecture decide du sort de la page
                break               # une rotation qui echoue ne perd pas la lecture deja faite
        finally:
            if essai is not image:
                try:
                    essai.close()
                except Exception:
                    pass
        _texte, confiance = reconstruire(mots)
        if angle == 0:
            droite = (confiance, mots)
            if _valeur_confiance(confiance) >= SEUIL_ORIENTATION:
                break               # lecture droite et sure : inutile de tourner
        elif (_valeur_confiance(confiance) >= SEUIL_ORIENTATION
              and _valeur_confiance(confiance) - _valeur_confiance(droite[0]) >= MARGE_ORIENTATION):
            return mots, angle
    return droite[1], 0


def _boites_retournees(boites, taille, angle):
    """Boites ramenees du rendu tourne au rendu affiche, qui est le repere de la couche de texte.

    `boites` : [[x, y, l, h, confiance, mot]] dans l'image tournee de `angle` degres dans le sens horaire ;
    `taille` : (largeur, hauteur) de l'image avant rotation. La couche de texte se place avec `_position` sur le
    rendu affiche, donc une page lue tournee doit rendre ses boites dans ce repere, sinon le texte cherche se
    retrouve a cote de l'encre. Une boite tournee de 90 degres echange largeur et hauteur (mesure sur une image
    marquee, les trois formules rendent le point d'origine).
    """
    if not angle:
        return boites
    largeur, hauteur = taille
    sortie = []
    for x, y, l, h, confiance, mot in boites:
        if angle == 90:
            sortie.append([y, hauteur - 1 - x - l, h, l, confiance, mot])
        elif angle == 270:
            sortie.append([largeur - 1 - y - h, x, h, l, confiance, mot])
        else:                        # 180
            sortie.append([largeur - 1 - x - l, hauteur - 1 - y - h, l, h, confiance, mot])
    return sortie


def extraire_page(chemin, numero, reglages, *, forcer_ocr=False, arreter=None, exe="", avec_boites=False):
    """Texte d'une page (contrat 3.1) : {"numero", "source": "texte|ocr|vide", "texte", "confiance", "mots", "boites"}.

    Un PDF dont la page porte assez de texte natif n'appelle jamais le moteur (T2). Sans texte, une page
    avec image est reconnue, une page sans image est « vide » (T3). `forcer_ocr` ignore le texte natif :
    c'est l'appelant qui decide quand l'employer. `numero` compte aussi les cadres d'un TIFF.
    `exe` : chemin du moteur (bloc de detecter), absent de `reglages` ; requis pour la reconnaissance.
    `boites` : None, ou [[x, y, l, h, confiance, mot]] en pixels au dpi de `reglages` si `avec_boites`.
    Leve ErreurOcr (illisible, protege, corrompu, moteur_absent, langue_manquante) ou ms.Annule.
    """
    try:
        return _extraire_page(chemin, numero, reglages, forcer_ocr, arreter, exe, avec_boites)
    except (ErreurOcr, ms.Annule):
        raise
    except Exception as e:
        _signaler(e)
        raise ErreurOcr("illisible", n=numero) from None


def _resultat(numero, source, texte, confiance, mots, boites=None):
    return {"numero": numero, "source": source, "texte": texte, "confiance": confiance,
            "mots": mots, "boites": boites}


def _extraire_page(chemin, numero, reglages, forcer_ocr, arreter, exe, avec_boites):
    if _est_pdf(chemin):
        lecteur = _ouvrir_pdf(chemin)
        if not 1 <= numero <= len(lecteur.pages):
            raise ErreurOcr("illisible", n=numero)
        page = lecteur.pages[numero - 1]
        if not forcer_ocr:
            natif = _normaliser_natif(_texte_natif(page))
            if decider_source(natif) == "texte":
                return _resultat(numero, "texte", natif, None, len(natif.split()))
            if not any(c.isalnum() for c in natif) and not _a_image(page):
                return _resultat(numero, "vide", "", None, 0)
    if not exe:
        raise ErreurOcr("moteur_absent")
    if not reglages.get("langues"):
        raise ErreurOcr("langue_manquante")   # jamais -l ""
    if arreter is not None and arreter():
        raise ms.Annule()
    image = rendre_page(chemin, numero, int(reglages.get("dpi") or 300))
    taille = image.size
    try:
        mots, angle = _reconnaitre_orientee(image, numero, reglages, exe, arreter)
    finally:
        try:
            image.close()
        except Exception:
            pass
    texte, confiance = reconstruire(mots)
    boites = None
    if avec_boites:
        boites = [[m["x"], m["y"], m["l"], m["h"], m["conf"], m["texte"]] for m in mots]
        boites = _boites_retournees(boites, taille, angle)
    return _resultat(numero, "ocr", texte, confiance, len(mots), boites)


# ------------------------------------------------------------------ Markdown d'un document
def _virgule(valeur):
    return f"{valeur:.2f}".replace(".", ",")


def _resume_pages(pages, total):
    """Comptes et confiance moyenne (ponderee par les mots) d'un document, pour l'en-tete du Markdown."""
    reconnues = [p for p in pages if p["source"] == "ocr"]
    pesees = [(p["confiance"], p.get("mots") or 0) for p in reconnues if p.get("confiance") is not None]
    poids = sum(m for _, m in pesees)
    confiance = round(sum(c * m for c, m in pesees) / poids, 3) if poids else None
    natives = sum(1 for p in pages if p["source"] == "texte")
    return {"pages": total, "pages_texte": natives, "pages_ocr": len(reconnues),
            "pages_vides": sum(1 for p in pages if p["source"] == "vide"),
            "extraction": ("vide" if not natives else "texte") if not reconnues else ("ocr" if not natives else "mixte"),
            "confiance": confiance}


def _qualite_page(page):
    """Texte natif : bon. Page sans texte : vide. Page reconnue : classer(confiance)."""
    if page["source"] == "texte":
        return "bon"
    if page["source"] == "vide":
        return "vide"
    return classer(page.get("confiance"))


def _regenerable(chemin):
    """Vrai si le fichier n'existe pas ou si son front matter porte la cle moodlesync (D4, invariant 8).
    Fichier edite, sans front matter ou illisible en UTF-8 : faux, il n'est jamais reecrit."""
    if not os.path.exists(chemin):
        return True
    try:
        with open(chemin, "rb") as f:
            lignes = f.read().decode("utf-8").lstrip("﻿").splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    if not lignes or lignes[0].strip() != "---":
        return False
    trouvee = False
    for ligne in lignes[1:]:
        if ligne.strip() == "---":
            return trouvee   # la cle ne compte que dans un front matter ferme (ecart 45)
        if ligne.startswith("moodlesync:"):
            trouvee = True
    return False   # front matter jamais ferme : fichier de l'utilisateur, conserve


def _yaml(valeur):
    return json.dumps(valeur, ensure_ascii=False)


def ecrire_document_md(chemin_md, chemin_rel, pages, reglages, *, illisibles=(), date=""):
    """Ecrit le Markdown d'un document (plan 6.1). Renvoie True s'il est ecrit, False s'il est conserve.

    `chemin_md` : fichier a ecrire (absolu, choisi par l'appelant). `chemin_rel` : chemin du document
    relatif a dest, seul chemin qui entre dans le fichier. `pages` : resultats de extraire_page.
    `illisibles` : numeros des pages levees en « illisible », signalees dans le texte. `reglages` : forme
    de reglages_depuis. Un .md existant sans la cle moodlesync dans son front matter n'est jamais reecrit.
    L'ecriture est atomique (fichier temporaire puis os.replace).
    """
    if not _regenerable(chemin_md):
        return False
    parties = [p for p in ms.nfc(chemin_rel).replace("\\", "/").split("/") if p]
    cours = parties[0] if len(parties) > 1 else ""
    section = parties[1] if len(parties) > 2 else ""
    par_numero = {p["numero"]: p for p in pages}
    numeros = sorted(set(par_numero) | set(illisibles))
    resume = _resume_pages(list(par_numero.values()), len(numeros))

    tete = ["---", f"source: {_yaml('/'.join(parties))}"]
    if cours:
        tete.append(f"cours: {_yaml(cours)}")
    if section:
        tete.append(f"section: {_yaml(section)}")
    tete += [f"pages: {resume['pages']}", f"extraction: {_yaml(resume['extraction'])}"]
    if resume["pages_ocr"]:
        if reglages.get("langues"):
            tete.append(f"langues: {_yaml(reglages['langues'])}")
        if resume["confiance"] is not None:
            tete.append("confiance: " + f"{resume['confiance']:.3f}".rstrip("0").rstrip("."))
        if reglages.get("moteur"):
            tete.append(f"moteur: {_yaml('Tesseract ' + reglages['moteur'])}")
    tete += [f"genere: {_yaml(date or time.strftime('%Y-%m-%dT%H:%M:%S'))}", f"moodlesync: {_yaml(MARQUE_DOC)}", "---"]

    total = resume["pages"]
    resume_ligne = f"{total} page{'s' if total > 1 else ''}"
    if resume["pages_ocr"]:
        resume_ligne += f", dont {resume['pages_ocr']} scannée{'s' if resume['pages_ocr'] > 1 else ''}"
    resume_ligne += "."
    if resume["confiance"] is not None:
        resume_ligne += f" Confiance moyenne : {_virgule(resume['confiance'])}."
    corps = [f"# {parties[-1] if parties else ''}", "",
             f"> Source : {' / '.join(parties)}", f"> {resume_ligne}"]

    a_verifier = []
    for n in numeros:
        corps += ["", f"<!-- page {n} -->", ""]
        page = par_numero.get(n)
        if page is None:
            corps.append("> " + MESSAGES["illisible"].format(n=n))
            a_verifier.append(f"- page {n} : page illisible")
            continue
        corps.append(page["texte"])
        qualite = _qualite_page(page)
        if qualite == "vide":
            a_verifier.append(f"- page {n} : aucun texte détecté")
        elif qualite != "bon":
            a_verifier.append(f"- page {n} : confiance {_virgule(page['confiance'])}")
    if a_verifier:
        corps += ["", "## Pages à vérifier", ""] + a_verifier

    contenu = "\n".join(tete + [""] + corps) + "\n"
    os.makedirs(os.path.dirname(chemin_md) or ".", exist_ok=True)
    temporaire = chemin_md + ".tmp"
    try:
        with open(temporaire, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenu)
        os.replace(temporaire, chemin_md)
    except BaseException:
        try:
            os.remove(temporaire)
        except OSError:
            pass
        raise
    return True


def _texte_brut(pages, illisibles=()):
    """Contenu d'un `.txt` (3.4, O5) : un bloc par page, aucun en-tete, aucune balise, aucune synthese.

    Chaque page : une ligne `[p. n]`, une ligne vide, le texte de la page, une ligne vide. Une page sans texte
    (page vide ou page illisible, qui n'a rien rendu) porte `TEXTE_PAGE_VIDE` a la place du texte.
    """
    par_numero = {p["numero"]: p for p in pages}
    lignes = []
    for n in sorted(set(par_numero) | set(illisibles)):
        texte = ((par_numero.get(n) or {}).get("texte") or "").strip("\n")
        lignes += [f"[p. {n}]", "", texte if texte.strip() else TEXTE_PAGE_VIDE, ""]
    return "\n".join(lignes)


def ecrire_document_texte(chemin_texte, chemin_rel, pages, reglages, *, format, illisibles, date,
                          precedente=None):
    """Ecrit le texte d'un document a cote de sa source (3.4). Vrai s'il est ecrit, faux s'il est conserve.

    `md` passe par `ecrire_document_md` sans changer sa sortie (front matter, `<!-- page n -->`, section « Pages à
    vérifier », ligne `moodlesync:`), et garde donc sa protection. `txt` est du texte seul, UTF-8, fins de ligne
    `\\n`, sans en-tete ni balise (O5) : voir `_texte_brut`. `precedente` est l'entree de cache du passage precedent :
    son empreinte pour ce format (`_empreinte_connue`, 2.2) autorise la reecriture, et son absence fait tenir le
    fichier present pour un texte edite a la main, qui n'est jamais reecrit (O6, invariant 3). On ne reecrit que ce
    qu'on a ecrit.
    """
    if format != "txt":
        return ecrire_document_md(chemin_texte, chemin_rel, pages, reglages, illisibles=illisibles, date=date)
    if os.path.isfile(chemin_texte):
        connue = _empreinte_connue(precedente, format)
        if not connue or _sha256(chemin_texte) != connue:
            return False
    _ecrire_texte(chemin_texte, _texte_brut(pages, illisibles))
    return True


def _texte_regenerable(chemin, entree):
    """Vrai si le texte a cote peut etre remplace : `.md` par la ligne `moodlesync:` (D4), `.txt` par l'empreinte de
    son format dans le cache (O6, la meme regle que `ecrire_document_texte`). Faux si l'empreinte manque ou si le
    fichier ne se lit pas : il est conserve."""
    if os.path.splitext(chemin)[1].lower() == ".txt":
        connue = _empreinte_connue(entree, "txt")
        if not connue:
            return False
        try:
            return _sha256(chemin) == connue
        except OSError:
            return False
    return _regenerable(chemin)


def _empreintes_texte(entree):
    """Empreinte du texte ecrit dans chaque format (2.2, `sortie_empreintes`) : objet `{"md": ..., "txt": ...}`.

    Une entree d'avant R1c n'en porte pas, et une valeur qui n'est pas un `sha256:` non vide est ignoree : l'objet
    rendu est alors vide ou incomplet, et `_empreinte_connue` retombe sur `sortie_empreinte`.
    """
    empreintes = entree.get("sortie_empreintes") if isinstance(entree, dict) else None
    if not isinstance(empreintes, dict):
        return {}
    return {f: e for f, e in empreintes.items() if f in FORMATS_TEXTE and isinstance(e, str) and e}


def _empreinte_connue(entree, format):
    """Empreinte du texte ecrit au passage precedent dans `format` (2.2), ou "" si elle n'est pas connue.

    `sortie_empreintes` fait foi. A defaut, `sortie_empreinte` ne vaut que si l'entree decrit ce meme format :
    sinon le fichier present est tenu pour modifie a la main et n'est pas reecrit (echec sur, invariant 3).
    """
    empreintes = _empreintes_texte(entree)
    if format in empreintes:
        return empreintes[format]
    if isinstance(entree, dict) and entree.get("format") == format:
        valeur = entree.get("sortie_empreinte")
        return valeur if isinstance(valeur, str) else ""
    return ""


def _empreinte_texte(chemin):
    """`sha256:<hex>` du texte ecrit, ou \"\" s'il ne se lit pas (le cache ne garde alors aucune empreinte)."""
    try:
        return _sha256(chemin)
    except OSError as e:
        _signaler(e)
        return ""


# ---------------------------------------------------------------------------------------------
# Tache C3 : cache, empreinte, reprise par page, file, document entier.
# ---------------------------------------------------------------------------------------------
VERSION_JSON = 1
# Origine d'une file (contrat 4.2) : les documents du coffre, ou ceux deposes dans un dossier (4.6, R5).
ORIGINES_FILE = ("coffre", "depot")
EXT_IMAGES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")   # plan 4.1


def _cle(chemin_rel):
    """Chemin relatif a dest sous la forme des JSON neufs : separateur `/`, NFC, sans `.` ni element vide."""
    return "/".join(p for p in re.split(r"[\\/]+", ms.nfc(chemin_rel or "")) if p and p != ".")


def _absolu(dest, chemin_rel):
    return os.path.join(dest, *_cle(chemin_rel).split("/"))


def _comparable(chemin):
    return os.path.normcase(os.path.normpath(chemin))


def _maintenant():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _entier(cfg, cle, defaut):
    """Entier strictement positif de la configuration, sinon `defaut` (valeur editee a la main, illisible)."""
    try:
        valeur = int(cfg.get(cle, defaut))
    except (ValueError, TypeError, OverflowError):
        return defaut
    return valeur if valeur > 0 else defaut


# ------------------------------------------------------------------ fichiers JSON neufs (contrat 1)
def _lire_json(chemin):
    """Objet JSON d'un fichier neuf, ou None s'il est absent, illisible ou de version superieure (traite comme absent)."""
    try:
        with open(chemin, "rb") as f:
            donnees = json.loads(f.read().decode("utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(donnees, dict):
        return None
    version = donnees.get("version", VERSION_JSON)
    if isinstance(version, bool) or not isinstance(version, int) or version > VERSION_JSON:
        return None
    return donnees


def _version_superieure(chemin):
    """Vrai si le fichier present sur le disque porte une version que ce code ne connait pas."""
    try:
        with open(chemin, "rb") as f:
            version = json.loads(f.read().decode("utf-8-sig")).get("version")
    except (OSError, ValueError, AttributeError):
        return False
    return isinstance(version, int) and not isinstance(version, bool) and version > VERSION_JSON


ESSAIS_ECRITURE = 5                 # essais d'un os.replace de fichier de travail (ecart 302)
PAUSE_ECRITURE = 0.05               # secondes entre deux essais


def _remplacer_travail(temporaire, chemin):
    """os.replace d'un fichier de travail. Sous Windows, un lecteur qui tient le fichier ouvert (la page, un
    antivirus, l'indexeur) fait lever PermissionError : quelques essais courts, puis l'erreur sort telle quelle."""
    for essai in range(1, ESSAIS_ECRITURE + 1):
        try:
            return os.replace(temporaire, chemin)
        except PermissionError:
            if essai == ESSAIS_ECRITURE:
                raise
            _pause(PAUSE_ECRITURE)


def _ecrire_json(chemin, donnees, indent=None):
    """Ecriture atomique (.tmp puis os.replace), UTF-8 sans BOM. Un fichier de version superieure n'est jamais
    reecrit : le fichier du disque est relu avant l'ecriture, ce qui evite un drapeau dans les signatures
    publiques. Renvoie False dans ce cas."""
    if _version_superieure(chemin):
        return False
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    temporaire = chemin + ".tmp"
    try:
        with open(temporaire, "w", encoding="utf-8", newline="\n") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=indent)
        _remplacer_travail(temporaire, chemin)
    except BaseException:
        try:
            os.remove(temporaire)
        except OSError:
            pass
        raise
    return True


def _chemin_ocr(dest, *parties):
    return os.path.join(dest, CACHE, *parties)


# ------------------------------------------------------------------ cache (2.3)
def charger_cache(dest):
    """Cache `.moodlesync-ocr/cache.json` : {"version": 1, "documents": {...}}. Absent, illisible ou de version
    superieure : cache vide. Aucun verrou ici (il est dans ApiTextes)."""
    donnees = _lire_json(_chemin_ocr(dest, "cache.json")) or {}
    documents = donnees.get("documents")
    if not isinstance(documents, dict):
        documents = {}
    return {"version": VERSION_JSON, "documents": {k: v for k, v in documents.items() if isinstance(v, dict)}}


def sauver_cache(dest, cache):
    """Ecrit le cache (atomique). Sans effet si `dest` n'existe pas ou si le fichier est de version superieure."""
    if not os.path.isdir(dest):
        return
    _ecrire_json(_chemin_ocr(dest, "cache.json"),
                 {"version": VERSION_JSON, "documents": (cache or {}).get("documents", {})}, indent=1)


def trouver_entree(cache, chemin_rel, empreinte, taille):
    """(cle, entree) d'un document : par chemin d'abord, puis par identite (empreinte et taille egales). None sinon.

    La taille Moodle n'intervient jamais (invariant 11). Une entree trouvee par identite sous un autre chemin
    peut etre un deplacement ou une copie : c'est a l'appelant de regarder si l'ancien fichier existe encore."""
    documents = (cache or {}).get("documents") or {}
    voulu = _comparable(_cle(chemin_rel))
    for cle, entree in documents.items():
        if _comparable(_cle(cle)) == voulu:
            return cle, entree
    if empreinte:
        for cle in sorted(documents):
            entree = documents[cle]
            if entree.get("empreinte") == empreinte and entree.get("taille") == taille:
                return cle, entree
    return None


def _cles_reglages(reglages):
    """Les quatre reglages qui figurent au cache. `oem` est constant (1) et `tessdata` est un dossier local, absent
    d'un cache qui peut changer de machine : ni l'un ni l'autre n'invalide une entree (ecart 7)."""
    return {cle: reglages.get(cle) for cle in ("langues", "dpi", "psm", "moteur")}


def entree_valide(entree, empreinte, reglages):
    """Vrai si l'entree decrit ce contenu (empreinte) avec ces reglages (langues, dpi, psm, moteur)."""
    if not isinstance(entree, dict) or entree.get("etat") == "erreur":
        return False
    if not empreinte or entree.get("empreinte") != empreinte:
        return False
    return all(entree.get(cle) == valeur for cle, valeur in _cles_reglages(reglages).items())


def _sha256(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return "sha256:" + h.hexdigest()


def _genere_lisible(genere):
    version = genere.get("version", 1)
    return bool(genere.get("type") == "pdf_cherchable" and isinstance(version, int) and version <= 1
                and isinstance(genere.get("empreinte_source"), str) and genere["empreinte_source"]
                and isinstance(genere.get("taille_source"), int) and not isinstance(genere.get("taille_source"), bool))


def _genere(dest, chemin_rel, chemin=None):
    """Bloc `genere` (2.1) de l'etat de synchronisation pour ce chemin, ou None. Un bloc incomplet ou de version
    superieure est ignore : le fichier est alors traite comme natif.

    Ecart 51 : quand `chemin` (le fichier sur le disque) est donne et qu'aucune entree ne porte `chemin_rel`
    (le PDF cherchable a ete deplace ou renomme dans le coffre), le fichier est retrouve comme en 3.3 : par
    `genere.taille_fichier` puis `genere.empreinte_fichier`. Sans cela son identite deviendrait le sha256 du
    fichier cherchable et la couche invisible serait lue comme du texte natif (invariants 3 et 11)."""
    etat = ms.charger_etat(dest)
    if not isinstance(etat, dict):
        return None
    voulu = _comparable(_cle(chemin_rel))
    candidats = []
    for valeur in etat.values():
        if not isinstance(valeur, dict) or not isinstance(valeur.get("chemin"), str):
            continue
        genere = valeur.get("genere")
        if not isinstance(genere, dict) or not _genere_lisible(genere):
            continue
        if _comparable(_cle(valeur["chemin"])) == voulu:
            return genere
        candidats.append(genere)
    if not chemin or not candidats:
        return None
    try:
        taille = os.path.getsize(chemin)
        retenus = [g for g in candidats if g.get("taille_fichier") == taille]
        if not retenus:
            return None
        empreinte = _sha256(chemin)
    except OSError as e:               # illisible : le repli ne decide rien, l'appelant tranchera (verrouille ou corrompu)
        _signaler(e)
        return None
    return next((g for g in retenus if g.get("empreinte_fichier") == empreinte), None)


def _identite_source(dest, chemin_rel, chemin):
    """(empreinte, taille, genere) de la SOURCE (2.3) : sha256 du fichier entier, ou, pour un PDF cherchable,
    l'identite du PDF recu de Moodle consignee dans `genere` (le fichier lui-meme n'est alors pas lu)."""
    genere = _genere(dest, chemin_rel, chemin)
    if genere:
        return genere["empreinte_source"], genere["taille_source"], genere
    try:
        taille = os.path.getsize(chemin)
        return _sha256(chemin), taille, None
    except PermissionError as e:
        _signaler(e)
        raise ErreurOcr("verrouille") from None
    except OSError as e:
        _signaler(e)
        raise ErreurOcr("corrompu") from None


# ------------------------------------------------------------------ chemin du texte (3.6)
FORMATS_TEXTE = ("md", "txt")
TEXTE_PAGE_VIDE = "(aucun texte détecté)"   # 3.4 : ce qu'un `.txt` porte pour une page sans texte


def format_texte(cfg):
    """`ocr_format` s'il vaut `md` ou `txt`, sinon `md` (3.6). Un reglage modifie a la main ne casse rien."""
    valeur = cfg.get("ocr_format") if isinstance(cfg, dict) else None
    return valeur if valeur in FORMATS_TEXTE else "md"


def chemin_texte(dest, chemin_rel, cfg):
    """(chemin absolu du texte, valeur de `sortie`) : le texte du document, a cote de sa source (2.1, 3.6).

    `<dossier de la source>/<nom complet du document>.<format>`. `sortie` est relatif a dest, avec `/`, et ne porte
    aucun chemin absolu : ce que la page en fait est un chemin recu, donc confine par `_ocr_confiner`.
    """
    parties = [p for p in _cle(chemin_rel).split("/") if p]
    if not parties:
        raise ErreurOcr("corrompu")
    parties[-1] += "." + format_texte(cfg)
    return os.path.join(dest, *parties), "/".join(parties)


def _resoudre_sortie(dest, sortie):
    return sortie if os.path.isabs(sortie) else os.path.join(dest, *sortie.split("/"))


# ------------------------------------------------------------------ copies d'originaux (2.1, 3.2, 3.3)
DOSSIER_ORIGINAUX = "originaux"


def chemin_original(dest, empreinte):
    """(chemin absolu, valeur de `original.fichier` de 2.2) de la copie d'un original.

    `.moodlesync-ocr/originaux/<hex>.pdf`, nommee par le SHA-256 du fichier d'origine (2.1). `fichier` est
    relatif au dossier du cache, comme 2.2 l'ecrit (`originaux/<hex>.pdf`).
    """
    hexa = (empreinte or "").split(":", 1)[-1]
    if not hexa or "/" in hexa or "\\" in hexa or ".." in hexa:
        raise ErreurOcr("corrompu")
    return _chemin_ocr(dest, DOSSIER_ORIGINAUX, hexa + ".pdf"), DOSSIER_ORIGINAUX + "/" + hexa + ".pdf"


def _resoudre_original(dest, fichier):
    """Chemin absolu d'une copie d'original depuis `original.fichier` (2.2), ou \"\" si la valeur ne designe
    pas une copie du dossier des originaux (valeur editee a la main, chemin absolu, `..`)."""
    parties = [p for p in str(fichier or "").replace("\\", "/").split("/") if p and p != "."]
    if not parties or ".." in parties or parties[0] != DOSSIER_ORIGINAUX or len(parties) < 2:
        return ""
    return _chemin_ocr(dest, *parties)


def _empreinte_fichier(chemin):
    """`sha256:<hex>` d'un fichier, ou \"\" s'il ne se lit pas (le cache ne garde alors aucune empreinte)."""
    try:
        return _sha256(chemin)
    except OSError as e:
        _signaler(e)
        return ""


def _copier_original(dest, chemin, empreinte):
    """Copie verifiee de l'original, relue et comparee a son empreinte (3.2 etape 5a).

    Rend `(bloc `original` de 2.2, valeur de `fichier` de la copie creee ou None si elle etait deja la)`.
    Leve ErreurOcr « ecriture » si la copie ne porte pas l'empreinte de la source : sans copie verifiee, le
    PDF n'est pas remplace (invariant 1).
    """
    cible, relatif = chemin_original(dest, empreinte)
    deja = os.path.isfile(cible) and _empreinte_fichier(cible) == empreinte
    if not deja:
        temporaire = cible + ".part"
        try:
            os.makedirs(os.path.dirname(cible), exist_ok=True)
            shutil.copyfile(chemin, temporaire)
            _remplacer_travail(temporaire, cible)
        except (OSError, shutil.Error) as e:
            _signaler(e)
            raise ErreurOcr("ecriture") from None
        finally:
            try:
                os.remove(temporaire)
            except OSError:
                pass
        if _empreinte_fichier(cible) != empreinte:
            _supprimer(cible)   # une copie non verifiee ne reste pas sous un nom qui annonce l'original
            raise ErreurOcr("ecriture")
    try:
        taille = os.path.getsize(cible)
    except OSError as e:
        _signaler(e)
        raise ErreurOcr("ecriture") from None
    return {"fichier": relatif, "empreinte": empreinte, "taille": taille}, (None if deja else relatif)


def _remettre_pdf(source, chemin):
    """Remet une copie d'original a la place du PDF (3.3), par ecriture atomique : `<nom>.ocr.part` dans le
    meme dossier, puis `_remplacer` (un nouvel essai apres PAUSE_VERROU, puis `verrouille`). Le temporaire
    ne reste jamais."""
    part = chemin + ".ocr.part"
    try:
        try:
            shutil.copyfile(source, part)
        except OSError as e:
            _signaler(e)
            raise ErreurOcr("ecriture") from None
        _remplacer(part, chemin)
    finally:
        try:
            os.remove(part)
        except OSError:
            pass


# ------------------------------------------------------------------ nombre de pages
def _nb_pages(chemin):
    """Nombre de pages d'un PDF (pypdf) ou de cadres d'une image (Pillow). ErreurOcr protege ou corrompu."""
    try:
        if _est_pdf(chemin):
            n = len(_ouvrir_pdf(chemin).pages)
        else:
            from PIL import Image
            with Image.open(chemin) as image:
                n = getattr(image, "n_frames", 1)
    except ErreurOcr:
        raise
    except PermissionError as e:       # contrat 3.1 : `verrouille`, pas `corrompu` (ecart 52)
        _signaler(e)
        raise ErreurOcr("verrouille") from None
    except Exception as e:
        _signaler(e)
        raise ErreurOcr("corrompu") from None
    if n < 1:
        raise ErreurOcr("corrompu")
    return n


def _a_reconnaitre(chemin):
    """Vrai si au moins une page demande le moteur. Meme decision que _extraire_page (copiee pour ne pas toucher
    au code de C2), sans rendu ni reconnaissance : une image isolee est toujours a reconnaitre."""
    if not _est_pdf(chemin):
        return True
    for page in _ouvrir_pdf(chemin).pages:
        natif = _normaliser_natif(_texte_natif(page))
        if decider_source(natif) == "texte":
            continue
        if not any(c.isalnum() for c in natif) and not _a_image(page):
            continue
        return True
    return False


# ------------------------------------------------------------------ reprise par page (2.4)
def _fichier_reprise(dest, empreinte):
    return _chemin_ocr(dest, "pages", empreinte.split(":", 1)[-1] + ".json")


def _format_page(page, avec_boites):
    """Format d'une page dans `faites` : source, texte, confiance, mots ; `boites` seulement si demandees."""
    enreg = {"source": page["source"], "texte": page["texte"], "confiance": page["confiance"], "mots": page["mots"]}
    if avec_boites and page.get("boites") is not None:
        enreg["boites"] = page["boites"]
    return enreg


def _charger_reprise(dest, empreinte, cles, nb_pages, avec_boites=False):
    """Pages deja faites {numero: enregistrement}. Fichier absent, de version superieure, d'une autre empreinte,
    d'autres reglages ou d'un autre nombre de pages : {} (le document repart de zero). Avec `avec_boites`, une page
    reconnue sans boites est refaite."""
    donnees = _lire_json(_fichier_reprise(dest, empreinte))
    if (not donnees or donnees.get("empreinte") != empreinte or donnees.get("reglages") != cles
            or donnees.get("pages") != nb_pages or not isinstance(donnees.get("faites"), dict)):
        return {}
    faites = {}
    for cle, enreg in donnees["faites"].items():
        if not (isinstance(cle, str) and cle.isdigit() and 1 <= int(cle) <= nb_pages and isinstance(enreg, dict)):
            continue
        if enreg.get("source") not in ("texte", "ocr", "vide") or not isinstance(enreg.get("texte"), str):
            continue
        if avec_boites and enreg["source"] == "ocr" and "boites" not in enreg:
            continue
        faites[int(cle)] = enreg
    return faites


def _sauver_reprise(dest, empreinte, cles, nb_pages, faites):
    """Reecrit le fichier de reprise en entier (atomique), apres chaque page."""
    _ecrire_json(_fichier_reprise(dest, empreinte),
                 {"version": VERSION_JSON, "empreinte": empreinte, "reglages": cles, "pages": nb_pages,
                  "faites": {str(n): faites[n] for n in sorted(faites)}})


def _supprimer_reprise(dest, empreinte):
    chemin = _fichier_reprise(dest, empreinte)
    if _version_superieure(chemin):
        return   # jamais touche, comme un fichier jamais reecrit (contrat 1)
    try:
        os.remove(chemin)
    except OSError:
        pass


# ------------------------------------------------------------------ un document
def _etat_document(pages, illisibles=0):
    """`etat` du cache, derive des pages (ecart 8) : « ok » seulement si la section « Pages a verifier » du
    Markdown est vide (bon donne ok) ; « difficile » si une page l'est ; sinon « a_verifier » (page peu sure, sans
    texte detecte ou illisible, ou document sans aucune page lue)."""
    pire = "a_verifier" if illisibles or not pages else "ok"
    for page in pages:
        qualite = _qualite_page(page)
        if qualite == "difficile":
            return "difficile"
        if qualite != "bon":
            pire = "a_verifier"
    return pire


def _entree_a_jour(dest, cfg, chemin_rel, entree, empreinte, cles):
    """Vrai si l'entree est valide et si son texte existe a cote de la source, dans le format demande (3.6).

    L'emplacement attendu vient de `chemin_texte` : un document dont le texte est ailleurs (ancien `Textes/`, autre
    format) n'est pas a jour, et son texte est reecrit a cote, sans effacer l'autre fichier (O5).
    """
    sortie = entree.get("sortie")
    if not entree_valide(entree, empreinte, cles) or not isinstance(sortie, str) or not sortie:
        return False
    try:
        texte, attendu = chemin_texte(dest, chemin_rel, cfg)
    except ErreurOcr:
        return False
    return sortie == attendu and os.path.isfile(texte)


def _a_jour(dest, cfg, chemin_rel, chemin, cache, cles):
    """Fraicheur d'un document sans rien ecrire : l'empreinte n'est calculee que si une entree de meme taille existe."""
    entree = (trouver_entree(cache, chemin_rel, "", 0) or (None, None))[1]
    if entree is None:
        return False
    try:
        if not _genere(dest, chemin_rel, chemin) and entree.get("taille") != os.path.getsize(chemin):
            return False
        empreinte = _identite_source(dest, chemin_rel, chemin)[0]
    except ErreurOcr:
        return False
    return _entree_a_jour(dest, cfg, chemin_rel, entree, empreinte, cles)


def _pages_forcees(genere, precedente, empreinte, nb_pages):
    """Pages a reconnaitre meme si elles portent du texte. Un PDF cherchable de MoodleSync porte une couche
    invisible qui n'est jamais lue comme du texte natif (invariant 3) : on reconnait les pages de `numeros_ocr` du
    cache. Cache perdu (lire_marque est a C4) : on ne sait pas lesquelles sont a nous, on les reconnait toutes."""
    if not genere:
        return set()
    if precedente and precedente.get("empreinte") == empreinte and isinstance(precedente.get("numeros_ocr"), list):
        return {n for n in precedente["numeros_ocr"] if isinstance(n, int) and not isinstance(n, bool)}
    return set(range(1, nb_pages + 1))


def _entete_document(dest, chemin_rel, cfg, *, refaire=False):
    """Ce que l'extraction et le traitement lisent avant de travailler (3.2 etape 1) : chemins, identite de
    la source, reglages du moteur, cache et entree precedente. `a_jour` porte l'entree d'un document deja
    traite et inchange, a renvoyer telle quelle.

    Leve ErreurOcr (corrompu, trop_gros, verrouille) : le document est inutilisable, l'appelant decide.
    """
    rel = _cle(chemin_rel)
    chemin = _absolu(dest, rel)
    if not rel or ".." in rel.split("/") or not os.path.isfile(chemin):
        raise ErreurOcr("corrompu")
    mo = _entier(cfg, "ocr_max_mo", 300)
    try:
        if os.path.getsize(chemin) > mo * 1024 * 1024:
            raise ErreurOcr("trop_gros", mo=mo)
    except OSError as e:
        _signaler(e)
        raise ErreurOcr("corrompu") from None
    empreinte, taille, genere = _identite_source(dest, rel, chemin)

    moteur = detecter(cfg)
    reglages = _reglages_moteur(cfg, moteur)
    cles = _cles_reglages(reglages)
    texte_abs, sortie = chemin_texte(dest, rel, cfg)

    cache = charger_cache(dest)
    trouve = trouver_entree(cache, rel, empreinte, taille)
    precedente, cle_cache, a_jour = None, rel, None
    if trouve:
        meme_chemin = _comparable(_cle(trouve[0])) == _comparable(rel)
        if meme_chemin:
            precedente, cle_cache = trouve[1], trouve[0]
            if not refaire and _entree_a_jour(dest, cfg, rel, precedente, empreinte, cles):
                a_jour = dict(precedente)
        elif not os.path.exists(_absolu(dest, trouve[0])):
            precedente = trouve[1]   # deplacement : l'ancienne entree et son texte restent (invariant 11)
    return {"dest": dest, "rel": rel, "chemin": chemin, "empreinte": empreinte, "taille": taille,
            "genere": genere, "moteur": moteur, "reglages": reglages, "cles": cles, "fmt": format_texte(cfg),
            "texte_abs": texte_abs, "sortie": sortie, "cache": cache, "cle_cache": cle_cache,
            "precedente": precedente, "a_jour": a_jour}


def _pages_document(ctx, *, avec_boites, progres=None, arreter=None, attendre=None):
    """Pages du document (3.2 etape 1) : texte natif, sinon reconnaissance, une page a la fois. Les pages deja
    faites sont reprises de `pages/<empreinte>.json`, le fichier est reecrit apres chaque page nouvelle.

    Rend `(pages, illisibles, nb)`. Une page illisible est signalee et le document continue ; `arreter()` vrai
    leve ms.Annule et les pages faites restent ; les autres erreurs du moteur sortent telles quelles.
    """
    nb = _nb_pages(ctx["chemin"])
    faites = _charger_reprise(ctx["dest"], ctx["empreinte"], ctx["cles"], nb, avec_boites)
    forcees = _pages_forcees(ctx["genere"], ctx["precedente"], ctx["empreinte"], nb)
    exe = ctx["moteur"].get("exe") or ""
    pages, illisibles, traitees = [], [], 0
    for n in range(1, nb + 1):
        if n in faites:
            pages.append(dict(faites[n], numero=n, boites=faites[n].get("boites")))
        else:
            if traitees and attendre is not None:
                attendre()
            if arreter is not None and arreter():
                raise ms.Annule()
            try:
                page = extraire_page(ctx["chemin"], n, ctx["reglages"], forcer_ocr=n in forcees,
                                     arreter=arreter, exe=exe, avec_boites=avec_boites)
            except ErreurOcr as e:
                if e.code != "illisible":
                    raise
                illisibles.append(n)
            else:
                pages.append(page)
                faites[n] = _format_page(page, avec_boites)
                _sauver_reprise(ctx["dest"], ctx["empreinte"], ctx["cles"], nb, faites)
            traitees += 1
        if progres is not None:
            progres({"document": ctx["rel"], "page": n, "pages": nb})
    return pages, illisibles, nb


def _entree_document(ctx, pages, illisibles, nb, date, *, ecrit, etat, remplace=False, original=None, motif="",
                     complete=True):
    """Entree de cache d'un document (2.2). `complete` ecrit les cles de la refonte (`remplace`, `original`,
    `sortie_empreintes`, `motif`) et retire `sortie`, `format` et `sortie_empreinte` d'un echec ; `extraire_document`
    garde la forme d'avant la refonte, que ses tests fixent.
    """
    resume = _resume_pages(pages, nb)
    precedente = ctx["precedente"] or {}
    entree = {
        "empreinte": ctx["empreinte"], "taille": ctx["taille"], "pages": nb,
        "pages_texte": resume["pages_texte"], "pages_ocr": resume["pages_ocr"],
        "numeros_ocr": sorted(p["numero"] for p in pages if p["source"] == "ocr"),
        "pages_vides": resume["pages_vides"] + len(illisibles),   # une page illisible n'a pas de texte : somme egale a `pages`
        "extraction": resume["extraction"], "confiance": resume["confiance"],
        "langues": ctx["cles"]["langues"], "dpi": ctx["cles"]["dpi"], "psm": ctx["cles"]["psm"],
        "moteur": ctx["cles"]["moteur"], "etat": etat,
        "verifie": bool(precedente.get("empreinte") == ctx["empreinte"] and precedente.get("verifie")),
        "date": date,
    }
    if complete and etat == "echec":
        entree["motif"] = motif
        entree["remplace"] = False
        entree["original"] = None
        return entree
    entree["sortie"] = ctx["sortie"]
    entree["format"] = ctx["fmt"]
    # 2.2 : l'empreinte du texte ecrit, format par format (`sortie_empreintes`, R1c) et pour le format courant
    # (`sortie_empreinte`). Un texte conserve parce qu'edite garde les empreintes du passage precedent (O6).
    empreintes = _empreintes_texte(precedente)
    entree["sortie_empreinte"] = precedente.get("sortie_empreinte") or ""
    if ecrit:
        entree["sortie_empreinte"] = _empreinte_texte(ctx["texte_abs"])
        if entree["sortie_empreinte"]:
            empreintes[ctx["fmt"]] = entree["sortie_empreinte"]
    if complete:
        entree["sortie_empreintes"] = empreintes
        entree["remplace"] = bool(remplace)
        entree["original"] = original
    return entree


def _etat_retenu(pages, illisibles):
    """`etat` d'un document traite (3.2 etape 2) : « ok » si toutes les pages sont bonnes, sinon « a_verifier ».

    Une page « difficile » isolee ne fait pas echouer le document (seule la confiance du document, moyenne
    ponderee par les mots, decide) : elle le met « a_verifier », et son avertissement la signale.
    """
    if illisibles or not pages:
        return "a_verifier"
    return "ok" if all(_qualite_page(p) == "bon" for p in pages) else "a_verifier"


def _motif_echec(pages, illisibles, nb, confiance):
    """Motif d'echec d'un document (3.2 etape 2), ou \"\" : `illisible` si aucune page n'a pu etre lue (le cas le
    plus precis), `vide` si aucune page ne porte de texte (O3), `difficile` si la confiance du document est
    connue et strictement inferieure a SEUILS_QUALITE[1] (0,70). Un document sans page reconnue n'a pas de
    confiance et n'echoue pas pour cela.
    """
    if nb and not pages:
        return "illisible"
    if not any((p.get("texte") or "").strip() for p in pages):
        return "vide"
    if confiance is not None and confiance < SEUILS_QUALITE[1]:
        return "difficile"
    return ""


def _echec_memorise(ctx):
    """Entree d'echec deja au cache pour ce contenu et ces reglages (O4), a renvoyer sans rien refaire : le
    document n'est pas retente tout seul, seule une demande `refaire` le reprend."""
    precedente = ctx["precedente"] or {}
    if precedente.get("etat") != "echec" or not entree_valide(precedente, ctx["empreinte"], ctx["cles"]):
        return None
    return dict(precedente)


def _echec_document(ctx, pages, illisibles, nb, date, motif, *, reprise=True):
    """Echec d'un document (3.2 etape 3) : rien n'est ecrit a cote du PDF, et l'echec est memorise (O4).

    La reprise par page est supprimee, sauf pour un echec tardif (etape 6) : ses boites evitent une seconde
    reconnaissance de la meme image au prochain essai (ecart 60).
    """
    if reprise:
        _supprimer_reprise(ctx["dest"], ctx["empreinte"])
    entree = _entree_document(ctx, pages, illisibles, nb, date, ecrit=False, etat="echec", motif=motif)
    ctx["cache"]["documents"][ctx["cle_cache"]] = entree
    sauver_cache(ctx["dest"], ctx["cache"])
    return _resultat_traitement(entree, False)


def _retirer_trace(ctx, ecrit, copie):
    """3.2 etape 6 (O1) : un echec tardif ou une annulation ne laisse ni le texte ecrit par ce passage, ni la
    copie d'original qu'il vient de creer, ni le fichier temporaire d'une fabrication interrompue. Le PDF
    d'origine est intact (ordre atomique de C4). Un texte conserve parce qu'edite n'a pas ete ecrit : il n'est
    jamais touche (invariant 3).
    """
    if ecrit:
        _supprimer(ctx["texte_abs"])
    if copie:
        chemin = _resoudre_original(ctx["dest"], copie)
        if chemin:
            _supprimer(chemin)


def _resultat_traitement(entree, texte):
    """Forme de retour de `traiter_document` (3.1), avec la phrase d'avertissement de l'appelant (`message`,
    vide quand il n'y a rien a dire)."""
    statut = entree.get("etat") or ""
    return {"entree": dict(entree), "statut": statut,
            "motif": (entree.get("motif") or "") if statut == "echec" else "",
            "remplace": bool(entree.get("remplace")), "texte": bool(texte), "message": ""}


def _resultat_conserve(entree, motif):
    """Retour de `traiter_document` quand un essai n'aboutit pas sur un document deja traite (E-V2-3) : l'etat
    d'avant est rendu tel quel, avec le motif mesure et l'avertissement `refaire_echec`."""
    resultat = _resultat_traitement(entree, True)
    resultat["motif"] = motif
    resultat["message"] = MESSAGES["refaire_echec"]
    return resultat


def pdf_modifie_main(dest, chemin_rel):
    """Vrai si le PDF en place n'est plus celui que MoodleSync a fabrique (invariant 8) : son entree d'etat porte
    un `genere` complet et l'identite du fichier ne correspond plus a `taille_fichier` et `empreinte_fichier`.

    Sans `genere`, la question ne se pose pas (le PDF n'a pas ete remplace par nous) : faux. Lecture seule.
    """
    rel = _cle(chemin_rel)
    if not rel:
        return False
    trouve = _entree_etat(dest, rel)
    if trouve is None:
        return False
    genere = _genere_complet(trouve[1].get("genere"))
    if genere is None:
        return False
    try:
        actuel = identite(_absolu(dest, rel))
    except ErreurOcr:
        return False
    return (actuel["taille"], actuel["empreinte"]) != (genere["taille_fichier"], genere["empreinte_fichier"])


def _cherchable_intact(ctx):
    """Vrai si le PDF en place est exactement celui que MoodleSync a fabrique : `genere` complet (2.1) et
    identite du fichier egale a `taille_fichier` et `empreinte_fichier`."""
    genere = _genere_complet(ctx.get("genere"))
    if genere is None:
        return False
    try:
        actuel = identite(ctx["chemin"])
    except ErreurOcr:
        return False
    return (actuel["taille"], actuel["empreinte"]) == (genere["taille_fichier"], genere["empreinte_fichier"])


def _remplacement_repris(ctx):
    """`(remplace, original)` d'un PDF deja remplace que ce passage ne refabrique pas (E-V2-2) : son ancienne
    entree garde sa copie si elle est toujours sur le disque et porte son empreinte (O13). Un PDF retouche a la
    main n'arrive pas ici (`_cherchable_intact` est faux)."""
    original = (ctx["precedente"] or {}).get("original")
    if not isinstance(original, dict):
        return True, None
    chemin = _resoudre_original(ctx["dest"], original.get("fichier"))
    if chemin and os.path.isfile(chemin) and _empreinte_fichier(chemin) == original.get("empreinte"):
        return True, dict(original)
    _signaler(RuntimeError("copie d'original absente ou alteree, non reprise : " + ctx["rel"]))
    return True, None


def _entree_a_conserver(ctx):
    """Entree de cache d'un document deja traite, a garder telle quelle quand un nouvel essai n'aboutit pas
    (E-V2-3) : son PDF cherchable, son texte et sa copie restent, et seul un document jamais traite memorise un
    echec (O4). None quand il n'y a rien a garder (document jamais traite, texte disparu, autre empreinte)."""
    precedente = ctx["precedente"] or {}
    if precedente.get("etat") not in ("ok", "a_verifier"):
        return None
    if not entree_valide(precedente, ctx["empreinte"], ctx["cles"]):
        return None
    sortie = precedente.get("sortie")
    if not isinstance(sortie, str) or not sortie or not os.path.isfile(_resoudre_sortie(ctx["dest"], sortie)):
        return None
    return dict(precedente)


def extraire_document(dest, chemin_rel, cfg, *, progres=None, arreter=None, attendre=None, refaire=False):
    """Extrait le texte d'un document et renvoie son entree de cache (2.3). Ne modifie jamais le PDF source.

    Un document inchange (meme empreinte, memes reglages, texte present a cote de la source) n'est pas refait. Sinon :
    le moteur est detecte une fois (ecart 35), les pages deja faites sont reprises de `pages/<empreinte>.json`, les
    autres sont extraites une a une (fichier de reprise reecrit apres chacune), puis le texte est ecrit a cote du
    document (`ecrire_document_texte`, `md` ou `txt` selon `ocr_format`), le cache mis a jour et le fichier de
    reprise supprime. `progres({"document", "page", "pages"})` suit chaque page ; `attendre()` est appele entre deux
    pages ; `arreter()` vrai leve ms.Annule, les pages faites restent. `refaire` ignore l'entree de cache du document
    (ajout a la signature de 3.1, pour la tache `refaire` de la file).
    Leve ErreurOcr (protege, corrompu, trop_gros, verrouille, moteur_absent, langue_manquante) ou ms.Annule.
    Le traitement complet (qualite, copie de l'original, PDF cherchable) est `traiter_document` (3.2).
    """
    ctx = _entete_document(dest, chemin_rel, cfg, refaire=refaire)
    if ctx["a_jour"] is not None:
        return dict(ctx["a_jour"])
    # L'extraction seule ne demande plus de boites : le mode PDF qui les utilisait est retire (O10, contrat 3.5).
    # C'est `traiter_document` qui les demande, pour un PDF avec au moins une page a reconnaitre (contrat 3.2).
    avec_boites = False
    pages, illisibles, nb = _pages_document(ctx, avec_boites=avec_boites, progres=progres, arreter=arreter,
                                            attendre=attendre)
    date = _maintenant()
    try:
        ecrit = ecrire_document_texte(ctx["texte_abs"], ctx["rel"], pages, ctx["reglages"], format=ctx["fmt"],
                                      illisibles=illisibles, date=date, precedente=ctx["precedente"])
    except PermissionError as e:
        _signaler(e)
        raise ErreurOcr("verrouille") from None
    entree = _entree_document(ctx, pages, illisibles, nb, date, ecrit=ecrit,
                              etat=_etat_document(pages, len(illisibles)), complete=False)
    ctx["cache"]["documents"][ctx["cle_cache"]] = entree
    sauver_cache(dest, ctx["cache"])
    if not avec_boites:
        _supprimer_reprise(dest, ctx["empreinte"])   # en mode remplacer, la reprise sert la fabrication (ecart 60)
    return dict(entree)


def traiter_document(dest, chemin_rel, cfg, *, progres=None, arreter=None, attendre=None, refaire=False,
                     garder_original=True):
    """Traite un document et rend la forme de 3.1 : `{"entree", "statut", "motif", "remplace", "texte"}`.

    Ordre de 3.2, sans raccourci : extraction page par page, decision de qualite sur le document (seuil strict
    de 0,70, motifs `difficile`, `vide`, `illisible`), echec qui n'ecrit rien, ecriture du texte a cote, copie de
    l'original verifiee par empreinte, fabrication du PDF cherchable, annulation d'un echec tardif, ecriture du
    cache. Un PDF avec au moins une page a reconnaitre est remplace et garde sa copie dans
    `.moodlesync-ocr/originaux/<hex>.pdf` (sauf `garder_original` faux) ; un PDF entierement textuel et une image
    ne recoivent que leur texte (O2), et un PDF que `.moodlesync.json` ne suit pas aussi (O17 : pas de
    remplacement, pas de copie, pas de fabrication). Un echec ne laisse rien a cote du PDF (O1, invariant 2) et sa
    memoire empeche une nouvelle tentative sans `refaire` (O4).

    Ne leve jamais pour un echec de qualite : il rend `statut == "echec"` et son motif. Leve ms.Annule si
    `arreter()` le demande (rien n'est alors laisse sur le disque) et ErreurOcr quand le document lui-meme est
    inutilisable (corrompu, trop_gros, verrouille, moteur_absent, langue_manquante).
    """
    ctx = _entete_document(dest, chemin_rel, cfg, refaire=refaire)
    if ctx["a_jour"] is not None:
        return _resultat_traitement(ctx["a_jour"], os.path.isfile(ctx["texte_abs"]))
    memo = None if refaire else _echec_memorise(ctx)
    if memo is not None:
        return _resultat_traitement(memo, False)

    pdf = _est_pdf(ctx["rel"])
    a_reconnaitre = _a_reconnaitre(ctx["chemin"])
    # O17 : remplacer exige que .moodlesync.json suive le fichier. Un PDF que l'etat ne suit pas (pose a la
    # main, ou etat perdu) se traite comme un PDF textuel (O2) : son texte est ecrit, le PDF reste tel quel et
    # aucune copie d'original n'est faite. Le cas est reconnu ici, avant la fabrication, et non en rattrapant
    # son refus `non_suivi`, qui partait jusque-la dans le motif `verification` (E-V7-2) et perdait le texte.
    a_remplacer = pdf and a_reconnaitre and _entree_etat(dest, ctx["rel"]) is not None
    # E-V2-2 : un PDF qui porte deja notre couche n'est plus « a reconnaitre » (mesure de la revue V2 sur le PDF
    # fabrique). Son remplacement et sa copie sont alors repris de l'entree precedente, pas perdus.
    deja_cherchable = pdf and not a_reconnaitre and _cherchable_intact(ctx)
    avec_boites = a_remplacer
    pages, illisibles, nb = _pages_document(ctx, avec_boites=avec_boites, progres=progres, arreter=arreter,
                                            attendre=attendre)
    date = _maintenant()
    confiance = _resume_pages(pages, nb)["confiance"]
    motif = _motif_echec(pages, illisibles, nb, confiance)
    if motif:
        # E-V2-3 : l'echec d'un nouvel essai sur un document deja traite ne touche a rien de ce qui existait ;
        # seul un document jamais traite memorise un echec (O4).
        conserve = _entree_a_conserver(ctx)
        if conserve is not None:
            return _resultat_conserve(conserve, motif)
        return _echec_document(ctx, pages, illisibles, nb, date, motif)

    try:
        ecrit = ecrire_document_texte(ctx["texte_abs"], ctx["rel"], pages, ctx["reglages"], format=ctx["fmt"],
                                      illisibles=illisibles, date=date, precedente=ctx["precedente"])
    except OSError as e:
        _signaler(e)
        # Rien n'a ete ecrit : la reprise garde ses pages pour l'essai suivant.
        return _echec_document(ctx, pages, illisibles, nb, date, "ecriture", reprise=False)

    remplace, original, copie = False, None, None
    if deja_cherchable:
        remplace, original = _remplacement_repris(ctx)
    elif a_remplacer:
        try:
            if garder_original:
                original, copie = _copier_original(dest, ctx["chemin"], ctx["empreinte"])
            fabriquer_pdf_cherchable(dest, ctx["rel"], cfg, arreter=arreter)
            remplace = True
        except ms.Annule:
            _retirer_trace(ctx, ecrit, copie)
            raise
        except Exception as e:
            _retirer_trace(ctx, ecrit, copie)
            if isinstance(e, ErreurOcr):
                # 3.2 etape 5a : une copie non verifiee est un echec `ecriture` ; toute autre panne de la
                # fabrication (refus compris) est un echec `verification` (etape 5c).
                code_motif = "ecriture" if e.code == "ecriture" else "verification"
                return _echec_document(ctx, pages, illisibles, nb, date, code_motif, reprise=False)
            _signaler(e)
            return _echec_document(ctx, pages, illisibles, nb, date, "erreur", reprise=False)

    entree = _entree_document(ctx, pages, illisibles, nb, date, ecrit=ecrit,
                              etat=_etat_retenu(pages, illisibles), remplace=remplace, original=original)
    ctx["cache"]["documents"][ctx["cle_cache"]] = entree
    sauver_cache(dest, ctx["cache"])
    if not avec_boites:
        _supprimer_reprise(dest, ctx["empreinte"])
    return _resultat_traitement(entree, True)


def _autre_texte(chemin):
    """Chemin du texte du meme document dans l'autre format (`article.pdf.md` depuis `article.pdf.txt`)."""
    base, extension = os.path.splitext(chemin)
    return base + (".md" if extension.lower() == ".txt" else ".txt")


def archiver_texte(dest, chemin_rel, t_ancien):
    """Renomme en « ancienne version » (moteur.nom_ancienne_version) les textes a cote d'un document, dans les deux
    formats ecrits (E-V1-4, revue V1), et renvoie le nouveau chemin absolu du texte du format courant. None s'il n'y
    a aucun texte connu au cache, ou si aucun n'est regenerable : un texte edite a la main n'est jamais renomme
    (invariant 3, meme garde que `ecrire_document_texte` : ligne `moodlesync:` pour un `.md`, empreinte de son format
    pour un `.txt`). Chaque fichier garde son format. Une erreur du systeme de fichiers leve OSError.
    """
    voulu = _comparable(_cle(chemin_rel))
    entree = next((e for k, e in charger_cache(dest)["documents"].items() if _comparable(_cle(k)) == voulu), None)
    sortie = entree.get("sortie") if entree else None
    if not isinstance(sortie, str) or not sortie:
        return None
    texte = _resoudre_sortie(dest, sortie)
    nouveau = None
    for chemin in (texte, _autre_texte(texte)):
        if not os.path.isfile(chemin) or not _texte_regenerable(chemin, entree):
            continue
        cible = ms.nom_ancienne_version(chemin, t_ancien)
        os.replace(chemin, cible)
        nouveau = nouveau or cible
    return nouveau


def republier(dest, chemin_rel, t_ancien):
    """Un PDF cherchable republie par Moodle reprend l'etat « Non traite » (contrat 7.1).

    Appelee par `moteur.telecharger` (import a l'usage : `moteur.py` n'importe pas `ocr`) apres le remplacement du
    fichier. Le texte a cote est renomme « ancienne version AAAA-MM-JJ » par `archiver_texte` (un texte edite a la
    main reste), l'entree de cache est retiree (le document redevient « Non traite ») et la copie d'original du PDF
    remplace est supprimee avec elle. Rend le chemin du texte archive, ou None. Une erreur du systeme de fichiers
    leve OSError.
    """
    archive = archiver_texte(dest, chemin_rel, t_ancien)
    trouve = trouver_entree(charger_cache(dest), chemin_rel, "", 0)
    if trouve is not None:
        _retirer_entree_cache(dest, trouve[0])
    return archive


# ------------------------------------------------------------------ file de travail (2.5)
def _file_vide():
    """File absente : aucune tache, aucun etat. `origine` (4.2) n'est ecrit que par une file qui en porte une :
    `charger_file` la reprend du JSON quand elle y est, et `ApiTextes` la donne pour `coffre` par defaut."""
    return {"version": VERSION_JSON, "etat": "inactive", "portee": "sans_texte", "cree": "", "taches": []}


def charger_file(dest):
    """File `.moodlesync-ocr/file.json`. Au chargement `en_cours` devient `pause` (aucune reprise automatique) et
    une tache `en_cours` redevient `attente`, ses pages faites restent. Absente, illisible ou de version superieure :
    file vide. Le disque n'est pas modifie."""
    file = _file_vide()
    donnees = _lire_json(_chemin_ocr(dest, "file.json"))
    if not donnees:
        return file
    for cle in ("etat", "portee", "cree"):
        if isinstance(donnees.get(cle), str):
            file[cle] = donnees[cle]
    if donnees.get("origine") in ORIGINES_FILE:
        file["origine"] = donnees["origine"]
    if file["etat"] == "en_cours":
        file["etat"] = "pause"
    vus = set()
    liste = donnees.get("taches")
    for tache in liste if isinstance(liste, list) else []:
        if not isinstance(tache, dict) or not isinstance(tache.get("chemin"), str):
            continue
        cle = _comparable(_cle(tache["chemin"]))
        if cle in vus:
            continue
        vus.add(cle)
        tache = dict(tache)
        if tache.get("etat", "attente") == "en_cours":
            tache["etat"] = "attente"
        file["taches"].append(tache)
    return file


def sauver_file(dest, file):
    """Ecrit la file (atomique). Sans effet si `dest` n'existe pas ou si le fichier est de version superieure."""
    if not os.path.isdir(dest):
        return
    _ecrire_json(_chemin_ocr(dest, "file.json"), dict(file, version=VERSION_JSON), indent=1)


def _est_ancienne_version(nom):
    return any("(" + langue["ancienne"] + " " in nom for langue in ms.LANGUES.values() if "ancienne" in langue)


def _eligible(dest, cfg, chemin_rel):
    """Chemin absolu du document s'il peut entrer en file (2.5), sinon None : ni un `Textes/` pose directement dans
    dest (un coffre qui n'a pas encore migre, 7), ni dossier ou fichier cache (`.moodlesync-ocr/`), ni « ancienne
    version », ni `.md` ou `.txt` (un texte a cote n'est pas un document), ni plus de `ocr_max_mo`. Seuls les PDF et
    les images sont pris (plan 4.1)."""
    parties = _cle(chemin_rel).split("/")
    if not parties[0] or ".." in parties or any(p.startswith(".") for p in parties):
        return None
    if len(parties) > 1 and ms.cle_nom(parties[0]) in ms.dossiers_sortie_ocr(cfg):
        return None
    extension = os.path.splitext(parties[-1])[1].lower()
    if extension != ".pdf" and extension not in EXT_IMAGES:
        return None
    if _est_ancienne_version(parties[-1]):
        return None
    chemin = _absolu(dest, chemin_rel)
    try:
        if not os.path.isfile(chemin) or os.path.getsize(chemin) > _entier(cfg, "ocr_max_mo", 300) * 1024 * 1024:
            return None
    except OSError:
        return None
    return chemin


def _tache(chemin_rel, etat, pages, message="", refaire=False):
    tache = {"chemin": chemin_rel, "etat": etat, "priorite": 0, "pages": pages, "pages_faites": 0,
             "ajoute": _maintenant(), "message": message}
    if refaire and etat == "attente":
        tache["refaire"] = True
    return tache


def constituer_file_chemins(dest, cfg, chemins, refaire=False, ecrire=True):
    """File des seuls documents demandes (contrat 4.4), deja developpes par `textes_arbre.fichiers_sous`.

    `chemins` : chemins relatifs a `dest`, avec `/`. Chaque document eligible devient une tache `attente` portant son
    nombre exact de pages (le document est lu ici, et seulement pour les documents demandes) ; un PDF illisible ou
    protege devient une tache `ignore` avec la phrase de la section 5, et n'entre ni dans `documents` ni dans
    `pages`. `refaire` marque les taches pour que l'executeur ignore le cache (O4, « Reessayer »).
    `ecrire` faux ne touche pas le disque : c'est le premier temps de `ocr_traiter`, sans `confirme`.
    Rend `(file, documents, pages, remplacements)`, `remplacements` comptant les PDF qui seraient remplaces (O2).
    """
    taches, documents, pages, remplacements = [], 0, 0, 0
    vus = set()
    for brut in chemins or []:
        if not isinstance(brut, str):
            continue
        rel = _cle(brut)
        if not rel or _comparable(rel) in vus or _eligible(dest, cfg, rel) is None:
            continue
        vus.add(_comparable(rel))
        chemin = _absolu(dest, rel)
        try:
            nb = _nb_pages(chemin)
        except ErreurOcr as e:
            taches.append(_tache(rel, "ignore", 0, str(e)))
            continue
        taches.append(_tache(rel, "attente", nb, refaire=refaire))
        documents += 1
        pages += nb
        if _est_pdf(rel):
            try:
                if _a_reconnaitre(chemin):
                    remplacements += 1
            except ErreurOcr as e:
                _signaler(e)          # la question du remplacement ne bloque pas la mise en file
    file = {"version": VERSION_JSON, "etat": "inactive", "portee": "chemins", "origine": "coffre",
            "cree": _maintenant(), "taches": taches}
    if ecrire and isinstance(dest, str) and dest:
        sauver_file(dest, file)
    return file, documents, pages, remplacements


# ---------------------------------------------------------------------------------------------
# Tache C4 : PDF cherchable (identite, marque, controle, superposition, verification, remplacement).
# ---------------------------------------------------------------------------------------------
NOM_POLICE = "MoodleSyncF"        # nom de la police de la couche dans /Resources /Font de chaque page reconnue
OCTETS_PAR_PAGE = 64 * 1024       # D10, voir la note ci-dessous
# D10 : volume maximal de la couche par page reconnue, flux compresse. La revue V2 a mesure que la borne de
# 10 Ko refusait l'article d'echantillon de la refonte (181 015 octets de couche pour 14 pages, soit 12,9 Ko
# par page) et le faisait echouer en « Non reussi ». L'orchestrateur, sur mandat de Maxence, l'a relevee a 64 Ko
# par page : la borne reste un garde-fou contre une couche folle, pas un plafond de qualite.
DPI_CONTROLE = 150                # D9 : resolution du rendu de controle
PAUSE_VERROU = 2                  # secondes avant le nouvel essai d'un fichier verrouille (invariant 5)
LARGEUR_MOYENNE = 0.5             # largeur moyenne d'un caractere Helvetica, en em : approximation, non mesuree


def _pause(secondes):
    """Attente avant le nouvel essai ; point d'entree remplacable par les tests."""
    time.sleep(secondes)


def identite(chemin):
    """{"taille": int, "empreinte": "sha256:<hex>"} du fichier entier (D2). PermissionError donne `verrouille`,
    toute autre erreur de lecture `corrompu` (meme regle qu'extraire_document)."""
    try:
        taille = os.path.getsize(chemin)
        return {"taille": taille, "empreinte": _sha256(chemin)}
    except PermissionError as e:
        _signaler(e)
        raise ErreurOcr("verrouille") from None
    except OSError as e:
        _signaler(e)
        raise ErreurOcr("corrompu") from None


# ------------------------------------------------------------------ controle d'un PDF
def _attribut(page, cle):
    """Valeur (resolue) d'un attribut de page, heritee des noeuds /Pages parents si besoin, ou None."""
    noeud, vus = page, 0
    while noeud is not None and vus < 64:
        if cle in noeud:
            return noeud[cle]
        parent = _resolu(noeud.get("/Parent"))
        noeud = parent if hasattr(parent, "get") else None
        vus += 1
    return None


def _rotation(page):
    try:
        return int(_attribut(page, "/Rotate") or 0) % 360
    except (ValueError, TypeError):
        return 0


def _resolu(valeur):
    return valeur.get_object() if hasattr(valeur, "get_object") else valeur


def _compter_signets(elements):
    return sum(_compter_signets(e) if isinstance(e, list) else 1 for e in elements)


def _champ_signature(champ, vus):
    """Vrai si ce champ de formulaire, ou l'un de ses enfants, est une signature numerique remplie (/FT /Sig, /V)."""
    champ = _resolu(champ)
    if not hasattr(champ, "get") or id(champ) in vus:
        return False
    vus.add(id(champ))
    if champ.get("/FT") == "/Sig" and champ.get("/V") is not None:
        return True
    return any(_champ_signature(k, vus) for k in (_resolu(champ.get("/Kids")) or []))


def _est_signe(lecteur):
    racine = _resolu(lecteur.trailer["/Root"])
    permissions = _resolu(racine.get("/Perms"))
    if permissions is not None and "/DocMDP" in permissions:
        return True
    formulaire = _resolu(racine.get("/AcroForm"))
    vus = set()
    return formulaire is not None and any(_champ_signature(c, vus) for c in (_resolu(formulaire.get("/Fields")) or []))


def controler_pdf(chemin):
    """Etat d'un PDF avant ou apres une superposition (contrat 3.1) : pages, protege, signe, lecture_seule, numerique,
    annotations, liens, signets, dimensions [[largeur, hauteur, rotation]] et marque.

    `lecture_seule` : PDF chiffre (meme a mot de passe utilisateur vide : le reecrire enleverait la protection) ou fichier
    non modifiable pour le systeme. `numerique` : aucune page a reconnaitre et pas de marque MoodleSync (invariant 3).
    `signe` : champ de signature rempli ou certification DocMDP. Un PDF a mot de passe renvoie `protege` vrai sans lever.
    Leve ErreurOcr « corrompu ».
    """
    try:
        lecteur = _ouvrir_pdf(chemin)
    except ErreurOcr as e:
        if e.code != "protege":
            raise
        return {"pages": 0, "protege": True, "signe": False, "lecture_seule": False, "numerique": False,
                "annotations": 0, "liens": 0, "signets": 0, "dimensions": [], "marque": None}
    annotations = liens = 0
    dimensions, signe = [], False
    try:
        pages = list(lecteur.pages)
        for page in pages:
            boite = page.mediabox
            dimensions.append([round(float(boite.width), 2), round(float(boite.height), 2), _rotation(page)])
            for annotation in (_resolu(page.get("/Annots")) or []):
                annotation = _resolu(annotation)
                annotations += 1
                liens += annotation.get("/Subtype") == "/Link"
                signe = signe or (annotation.get("/FT") == "/Sig" and annotation.get("/V") is not None)
        signe = signe or _est_signe(lecteur)
        try:
            signets = _compter_signets(lecteur.outline)
        except Exception as e:
            _signaler(e)
            raise ErreurOcr("corrompu") from None
    except ErreurOcr:
        raise
    except Exception as e:
        _signaler(e)
        raise ErreurOcr("corrompu") from None
    marque = _marque_du_lecteur(lecteur)
    try:
        numerique = marque is None and not _a_reconnaitre(chemin)
    except ErreurOcr:
        raise
    except Exception as e:
        _signaler(e)
        numerique = False
    return {"pages": len(pages), "protege": False, "signe": bool(signe),
            "lecture_seule": bool(lecteur.is_encrypted) or not os.access(chemin, os.W_OK), "numerique": numerique,
            "annotations": annotations, "liens": liens, "signets": signets, "dimensions": dimensions, "marque": marque}


# ------------------------------------------------------------------ couche de texte (D8)
def _position(px, py, dpi, boite, rotation):
    """Du pixel (px, py) du rendu au `dpi` (origine en haut a gauche, page tournee comme affichee) au point du PDF :
    (x, y, (a, b, c, d)), x et y en points dans l'espace utilisateur de la page, (a, b, c, d) la direction du texte.
    `boite` = (gauche, bas, droite, haut) de la page, `rotation` = /Rotate de la page (0, 90, 180 ou 270)."""
    k = 72.0 / dpi
    u, v = px * k, py * k
    x0, y0, x1, y1 = boite
    w, h = x1 - x0, y1 - y0
    if rotation == 90:
        return x0 + v, y0 + u, (0, 1, -1, 0)
    if rotation == 180:
        return x0 + w - u, y0 + v, (-1, 0, 0, -1)
    if rotation == 270:
        return x0 + w - v, y0 + h - u, (0, -1, 1, 0)
    return x0 + u, y1 - v, (1, 0, 0, 1)


def _encodable(mot):
    """Les caracteres du mot qui existent en WinAnsi (cp1252) ; les autres sont omis de la couche (D8)."""
    gardes = []
    for c in ms.nfc(mot or ""):
        if ord(c) < 32:
            continue
        try:
            c.encode("cp1252")
        except UnicodeEncodeError:
            continue
        gardes.append(c)
    return "".join(gardes)


def _boites_utiles(boites):
    """[(x, y, l, h, texte encodable)] : les mots de la couche. Une boite sans surface ou sans caractere encodable est ecartee."""
    utiles = []
    for x, y, l, h, _confiance, mot in boites:
        texte = _encodable(mot)
        if texte and l > 0 and h > 0:
            utiles.append((x, y, l, h, texte))
    return utiles


def _nombre(valeur):
    texte = f"{valeur:.2f}".rstrip("0").rstrip(".")
    return "0" if texte in ("", "-0") else texte


def _chaine_pdf(texte):
    """Chaine litterale PDF en WinAnsi, ASCII seulement : parentheses, barre oblique et octets hors 32 a 126 en octal."""
    sortie = []
    for octet in texte.encode("cp1252"):
        c = chr(octet)
        sortie.append("\\" + c if c in "()\\" else c if 32 <= octet < 127 else f"\\{octet:03o}")
    return "".join(sortie)


def _flux_couche(boites, dpi, boite, rotation):
    """Flux de contenu de la couche : texte invisible (mode de rendu 3), un mot par `Tj`, Helvetica en WinAnsi, position et
    taille tirees du TSV (taille = hauteur de la boite, echelle horizontale pour la largeur, ligne de base a 80 % de la
    hauteur : approximations, alignement non verifie visuellement). Octets ASCII ; None s'il n'y a aucun mot."""
    k = 72.0 / dpi
    lignes = ["BT", "3 Tr"]
    for x, y, l, h, texte in _boites_utiles(boites):
        taille = max(h * k, 1.0)
        echelle = min(max(100.0 * (l * k) / (len(texte) * LARGEUR_MOYENNE * taille), 5.0), 500.0)
        cx, cy, (a, b, c, d) = _position(x, y + 0.8 * h, dpi, boite, rotation)
        lignes.append(f"/{NOM_POLICE} {_nombre(taille)} Tf {_nombre(echelle)} Tz {a} {b} {c} {d} {_nombre(cx)} {_nombre(cy)} Tm "
                      f"({_chaine_pdf(texte)}) Tj")
    if len(lignes) == 2:
        return None
    lignes.append("ET")
    return ("\n".join(lignes) + "\n").encode("ascii")


def _geometrie(page):
    """((gauche, bas, droite, haut), rotation) de la page, telle que le rendu l'affiche."""
    boite = page.cropbox
    return (float(boite.left), float(boite.bottom), float(boite.right), float(boite.top)), _rotation(page)


def _nouveau_contents(page, debut, couche):
    """/Contents d'une page reconnue : [q, objets d'origine, couche]. Les objets d'origine sont repris par leur objet
    indirect (page.raw_get), jamais par l'objet resolu (ecart 15 : le resolu donne un ecart de rendu de 255)."""
    from pypdf.generic import ArrayObject
    if "/Contents" not in page:
        return ArrayObject([debut, couche])
    brut = page.raw_get("/Contents")
    resolu = brut.get_object()
    elements = list(resolu) if isinstance(resolu, ArrayObject) else [brut]
    return ArrayObject([debut] + elements + [couche])


def _ressources_avec_police(page, police):
    """Copie des ressources de la page (heritees si besoin) avec la police de la couche : les ressources partagees avec
    d'autres pages, natives comprises, ne sont jamais modifiees."""
    from pypdf.generic import DictionaryObject, NameObject
    ressources = _attribut(page, "/Resources")
    nouvelles = DictionaryObject()
    polices = DictionaryObject()
    if ressources is not None:
        for cle, valeur in dict.items(ressources):
            nouvelles[cle] = valeur
        existantes = _resolu(ressources.get("/Font"))
        if existantes is not None:
            for cle, valeur in dict.items(existantes):
                polices[cle] = valeur
    polices[NameObject("/" + NOM_POLICE)] = police
    nouvelles[NameObject("/Font")] = polices
    return nouvelles


def _ecrire_part(chemin, part, couches, texte_marque):
    """Ecrit `part` : le PDF `chemin` cloné, avec la couche de chaque page de `couches` ({numero: flux}) et la marque dans
    /Info. Renvoie le volume des couches, en octets de flux compresse."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    w = PdfWriter(clone_from=chemin)
    police = w._add_object(DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                                             NameObject("/BaseFont"): NameObject("/Helvetica"),
                                             NameObject("/Encoding"): NameObject("/WinAnsiEncoding")}))
    ouverture = DecodedStreamObject()
    ouverture.set_data(b"q\n")
    debut = w._add_object(ouverture)
    volume = 0
    for numero, flux in couches.items():
        page = w.pages[numero - 1]
        brut = DecodedStreamObject()
        brut.set_data(b"Q\nq\n" + flux + b"Q\n")
        compresse = brut.flate_encode(9)
        volume += len(compresse._data)
        page[NameObject("/Contents")] = _nouveau_contents(page, debut, w._add_object(compresse))
        page[NameObject("/Resources")] = _ressources_avec_police(page, police)
    w.add_metadata({CLE_MARQUE: texte_marque})
    with open(part, "wb") as f:
        w.write(f)
    return volume


# ------------------------------------------------------------------ verification (invariant 4)
def _echec_verification(raison):
    """Detail dans erreurs.txt, phrase lisible dans l'exception (invariant 9)."""
    _signaler(RuntimeError("Verification du PDF cherchable : " + raison))
    return ErreurOcr("verification")


def _meme_image(a, b):
    from PIL import ImageChops
    return a.size == b.size and ImageChops.difference(a.convert("L"), b.convert("L")).getbbox() is None


def _comparer_rendus(a, b):
    """(identiques, ecart maximal par pixel) entre deux rendus bruts. D9 : l'egalite se juge sur les images brutes,
    jamais sur les images preparees (ecart 69)."""
    from PIL import ImageChops
    if a.size != b.size:
        return False, None
    difference = ImageChops.difference(a.convert("L"), b.convert("L"))
    if difference.getbbox() is None:
        return True, 0
    extremum = difference.getextrema()
    if isinstance(extremum, tuple):
        extremum = extremum[1]
    return False, int(extremum) if isinstance(extremum, (int, float)) else 0


def _raison_rendu(numero, avant, apres, ecart):
    """Raison technique d'un rendu different, pour erreurs.txt. L'autocontraste sert ici d'explication, jamais de
    decision : il dit qu'une difference est invisible a l'oeil. La phrase visible reste MESSAGES[\"verification\"]."""
    if ecart is None:
        return f"rendu different a la page {numero} (dimensions {avant.size} et {apres.size})"
    raison = f"rendu different a la page {numero}, ecart maximal {ecart} sur 255"
    try:
        if _meme_image(_preparer(avant), _preparer(apres)):
            raison += " (identique apres autocontraste)"
    except Exception:
        pass
    return raison


def _verifier(chemin, part, avant, attendus, volume, texte_marque):
    """Controles de l'invariant 4 sur le fichier temporaire. `attendus` = {page: nombre de caracteres alphanumeriques de la
    couche}. Un seul ecart leve ErreurOcr « verification »."""
    try:
        apres = controler_pdf(part)
    except ErreurOcr as e:
        raise _echec_verification("le fichier temporaire ne se rouvre pas (" + e.code + ")") from None
    if apres["protege"] or apres["signe"]:
        raise _echec_verification("le fichier temporaire est protege ou signe")
    for cle in ("pages", "dimensions", "annotations", "liens", "signets"):
        if apres[cle] != avant[cle]:
            raise _echec_verification(f"{cle} differents (avant {avant[cle]!r}, apres {apres[cle]!r})")
    if apres["marque"] != json.loads(texte_marque):
        raise _echec_verification("marque absente ou alteree")
    if volume > OCTETS_PAR_PAGE * len(attendus):
        raise _echec_verification(f"couche de {volume} octets pour {len(attendus)} page(s), au-dessus de {OCTETS_PAR_PAGE} par page")
    lecteur = _ouvrir_pdf(part)
    for numero, attendu in attendus.items():
        extrait = sum(1 for c in _texte_natif(lecteur.pages[numero - 1]) if c.isalnum())
        if extrait == 0 or extrait < 0.9 * attendu:
            raise _echec_verification(f"texte non extractible page {numero} ({extrait} caracteres sur {attendu})")
    reconnues = sorted(attendus)
    for numero in sorted({reconnues[0], reconnues[len(reconnues) // 2], reconnues[-1]}):
        rendus = []
        try:
            for fichier in (chemin, part):
                rendus.append(rendre_page(fichier, numero, DPI_CONTROLE, preparer=False))
            identiques, ecart = _comparer_rendus(rendus[0], rendus[1])
            raison = None if identiques else _raison_rendu(numero, rendus[0], rendus[1], ecart)
        except Exception as e:
            raise _echec_verification(f"rendu de la page {numero} impossible ({type(e).__name__})") from None
        finally:
            for image in rendus:
                try:
                    image.close()
                except Exception:
                    pass
        if not identiques:
            raise _echec_verification(raison)


# ------------------------------------------------------------------ etat et remplacement
def _entree_etat(dest, rel):
    """(cle, entree) de .moodlesync.json dont `chemin` est ce document (separateur, NFC et casse du systeme ignores), ou None."""
    etat = ms.charger_etat(dest)
    if not isinstance(etat, dict):
        return None
    voulu = _comparable(_cle(rel))
    for cle, valeur in etat.items():
        if isinstance(valeur, dict) and isinstance(valeur.get("chemin"), str) and _comparable(_cle(valeur["chemin"])) == voulu:
            return cle, valeur
    return None


def _genere_complet(genere):
    """Le bloc `genere` s'il est complet et de version connue (2.1), sinon None : un bloc incomplet est ignore."""
    if not isinstance(genere, dict) or genere.get("type") != "pdf_cherchable":
        return None
    if not _entier_vrai(genere.get("version", 1)) or genere.get("version", 1) > 1:
        return None
    for cle in ("taille_source", "taille_fichier"):
        if not _entier_vrai(genere.get(cle)):
            return None
    for cle in ("empreinte_source", "empreinte_fichier"):
        if not isinstance(genere.get(cle), str) or not genere[cle]:
            return None
    return genere


def _poser_genere(dest, cle, genere):
    """Etape 3 de l'invariant 5 : `genere` dans l'entree d'etat, le reste de .moodlesync.json intact."""
    etat = ms.charger_etat(dest)
    if not isinstance(etat, dict) or not isinstance(etat.get(cle), dict):
        raise ErreurOcr("non_suivi")
    etat[cle]["genere"] = genere
    ms.sauver_etat(dest, etat)


def _retirer_genere(dest, cle):
    """Etape 5 de l'invariant 5 : le remplacement a echoue, l'etat ne doit plus annoncer un PDF cherchable."""
    try:
        etat = ms.charger_etat(dest)
        if isinstance(etat, dict) and isinstance(etat.get(cle), dict) and "genere" in etat[cle]:
            del etat[cle]["genere"]
            ms.sauver_etat(dest, etat)
    except Exception as e:
        _signaler(e)


def _remplacer(part, chemin):
    """Etape 4 : os.replace atomique. Fichier verrouille (PermissionError) : un nouvel essai apres PAUSE_VERROU secondes,
    puis `verrouille`. Toute autre erreur sort telle quelle."""
    for essai in (1, 2):
        try:
            os.replace(part, chemin)
            return
        except PermissionError as e:
            if essai == 1:
                _pause(PAUSE_VERROU)
                continue
            _signaler(e)
            raise ErreurOcr("verrouille") from None


def fabriquer_pdf_cherchable(dest, chemin_rel, cfg, *, arreter=None):
    """Remplace le PDF `chemin_rel` par sa version cherchable et renvoie le bloc `genere` (2.1).

    Superposition seulement (invariant 2) : une couche de texte invisible construite depuis le TSV est ajoutee aux pages qui
    demandent la reconnaissance, le reste du PDF est repris tel quel. Refus sans rien ecrire : `protege`, `signe`,
    `lecture_seule`, `numerique` (invariant 3), `non_suivi` (aucune entree dans .moodlesync.json, donc pas de fichier de
    Moodle a remplacer) et `modifie_main` (le fichier porte notre marque ou un `genere` sans etre ni la source ni le PDF
    cherchable decrit : jamais superpose deux fois, invariants 8 et 10). Un PDF deja cherchable par nous renvoie son bloc
    `genere` sans rien refaire. Ordre de l'invariant 5 : identite source, fichier `<nom>.ocr.part` dans le meme dossier,
    verification, etat avec `genere`, os.replace ; si os.replace echoue, `genere` est retire. Echec de verification :
    ErreurOcr « verification ». Fichier verrouille : un nouvel essai apres 2 s, puis `verrouille`. Un .part n'est jamais
    laisse derriere. Les pages deja reconnues sont reprises du fichier de reprise, boites comprises (ecart 60) ; celles
    qui manquent sont reconnues ici, et la reprise n'est supprimee qu'apres un remplacement reussi.
    """
    rel = _cle(chemin_rel)
    chemin = _absolu(dest, rel)
    if not rel or ".." in rel.split("/") or not _est_pdf(rel) or not os.path.isfile(chemin):
        raise ErreurOcr("corrompu")
    mo = _entier(cfg, "ocr_max_mo", 300)
    try:
        if os.path.getsize(chemin) > mo * 1024 * 1024:
            raise ErreurOcr("trop_gros", mo=mo)
    except OSError as e:
        _signaler(e)
        raise ErreurOcr("corrompu") from None

    avant = controler_pdf(chemin)
    for code in ("protege", "signe", "lecture_seule", "numerique"):
        if avant[code]:
            raise ErreurOcr(code)
    trouve = _entree_etat(dest, rel)
    if trouve is None:
        raise ErreurOcr("non_suivi")
    cle_etat, entree = trouve

    source = identite(chemin)
    genere = _genere_complet(entree.get("genere"))
    if genere or avant["marque"]:
        if genere and (source["taille"], source["empreinte"]) == (genere["taille_fichier"], genere["empreinte_fichier"]):
            return dict(genere)   # deja cherchable : rien a refaire
        coupure = (genere and not avant["marque"]
                   and (source["taille"], source["empreinte"]) == (genere["taille_source"], genere["empreinte_source"]))
        if not coupure:   # coupure entre les etapes 3 et 4 : le fichier est encore la source, on refait
            raise ErreurOcr("modifie_main")

    t = entree.get("t")
    marque = {"v": 1, "url": ms.cle_url(cle_etat), "t": t if _entier_vrai(t) else 0, "taille_source": source["taille"],
              "empreinte_source": source["empreinte"], "pages": avant["pages"]}
    texte_marque = json.dumps(marque, separators=(",", ":"), ensure_ascii=False)
    if len(texte_marque.encode("utf-8")) >= 1024:
        raise _echec_verification("la marque depasse 1 Ko")

    moteur = detecter(cfg)
    reglages = _reglages_moteur(cfg, moteur)
    exe = moteur.get("exe") or ""
    dpi = int(reglages["dpi"])
    # Reprise laissee par extraire_document en mode remplacer (ecart 60) : les boites deja mesurees evitent une
    # seconde reconnaissance de la meme image.
    faites = _charger_reprise(dest, source["empreinte"], _cles_reglages(reglages), avant["pages"], avec_boites=True)
    lecteur = _ouvrir_pdf(chemin)
    couches, attendus = {}, {}
    for numero in range(1, avant["pages"] + 1):
        if arreter is not None and arreter():
            raise ms.Annule()
        if numero in faites:
            page = dict(faites[numero], numero=numero, boites=faites[numero].get("boites"))
        else:
            try:
                page = extraire_page(chemin, numero, reglages, exe=exe, avec_boites=True, arreter=arreter)
            except ErreurOcr as e:
                if e.code != "illisible":
                    raise
                continue   # une page illisible n'a pas de couche ; les autres restent traitees
        if page["source"] != "ocr" or not page.get("boites"):
            continue
        boite, rotation = _geometrie(lecteur.pages[numero - 1])
        flux = _flux_couche(page["boites"], dpi, boite, rotation)
        if flux is not None:
            couches[numero] = flux
            attendus[numero] = sum(1 for *_, texte in _boites_utiles(page["boites"]) for c in texte if c.isalnum())
    if not couches:
        raise _echec_verification("aucune page reconnue ne donne de couche de texte")
    if arreter is not None and arreter():
        raise ms.Annule()

    part = chemin + ".ocr.part"
    try:
        try:
            volume = _ecrire_part(chemin, part, couches, texte_marque)
        except PermissionError as e:
            _signaler(e)
            raise ErreurOcr("verrouille") from None
        _verifier(chemin, part, avant, attendus, volume, texte_marque)
        resultat = identite(part)
        genere = {"type": "pdf_cherchable", "taille_source": source["taille"], "empreinte_source": source["empreinte"],
                  "taille_fichier": resultat["taille"], "empreinte_fichier": resultat["empreinte"],
                  "pages": avant["pages"], "date": _maintenant(), "version": 1}
        _poser_genere(dest, cle_etat, genere)
        try:
            _remplacer(part, chemin)
        except BaseException:
            _retirer_genere(dest, cle_etat)
            raise
        _supprimer_reprise(dest, source["empreinte"])   # ecart 60 : seulement apres un remplacement reussi
        return genere
    finally:
        try:
            os.remove(part)
        except OSError:
            pass


# ---------------------------------------------------------------------------------------------
# Tache Y2 : restauration de l'original, reconciliation de l'etat, fichiers temporaires orphelins.
# ---------------------------------------------------------------------------------------------
def restaurer(dest, chemin_rel, cfg, *, confirme=False, arreter=None):
    """Remet le PDF d'origine d'un document traite (3.3) : `{"ok": True}`, `{"confirmer": str}` pour un fichier
    modifie a la main, ou la phrase `restauration_texte_garde` en plus quand un texte edite est reste en place.

    Copie locale d'abord (O13) : `originaux/<hex>.pdf` de l'entree de cache, empreinte verifiee avant, ecriture
    atomique (`<nom>.ocr.part` puis `_remplacer`). Puis, dans cet ordre, le texte a cote (un texte edite a la
    main reste, invariant 3), `genere` retire de `.moodlesync.json`, l'entree de cache retiree et la copie
    d'original supprimee : le document redevient « Non traite ». Sans copie (PDF migre, U9), le re-telechargement
    de Moodle d'avant, compare a `genere.taille_source` et `empreinte_source` (`restauration_differente`, rien
    n'est remplace), puis les memes suppressions.

    Leve ErreurOcr(hors_ligne | restauration_differente | verrouille | non_suivi | corrompu), ms.SessionExpiree
    (jeton absent ou refuse), ms.Erreur (Moodle renvoie une page a la place du fichier) ou ms.Annule. Dans tous
    ces cas le PDF cherchable est intact et aucune suppression n'a eu lieu.
    """
    if isinstance(chemin_rel, dict) and not isinstance(cfg, dict):
        # Transition : `api_textes` appelle encore `restaurer(dest, cfg, chemin)` ; R4 le reecrit sur 3.3.
        chemin_rel, cfg = cfg, chemin_rel
    rel = _cle(chemin_rel)
    chemin = _absolu(dest, rel)
    if not rel or ".." in rel.split("/") or not _est_pdf(rel) or not os.path.isfile(chemin):
        raise ErreurOcr("corrompu")
    trouve_cache = trouver_entree(charger_cache(dest), rel, "", 0)
    cle_cache, entree = trouve_cache if trouve_cache else (None, {})
    entree = entree if isinstance(entree, dict) else {}
    original = entree.get("original")
    fichier = original.get("fichier") if isinstance(original, dict) else ""

    source = _resoudre_original(dest, fichier) if fichier else ""
    if source and os.path.isfile(source):
        # E-V2-5, invariant 8 : un PDF retouche a la main depuis le traitement n'est pas remis a l'original sans
        # la confirmation `modifie_main` d'avant (la copie locale ne dispensait plus de la demander).
        if not confirme and pdf_modifie_main(dest, rel):
            return {"confirmer": MESSAGES["modifie_main"]}
        if _empreinte_fichier(source) != original.get("empreinte"):
            # Copie alteree : on ne remet jamais autre chose que l'original annonce (invariant 1).
            _signaler(RuntimeError("copie d'original altérée, non remise : " + source))
            source = ""
        else:
            _remettre_pdf(source, chemin)
    if not source or not os.path.isfile(source):
        resultat = _restaurer_depuis_moodle(dest, rel, chemin, cfg, confirme=confirme, arreter=arreter)
        if resultat is not None:
            return resultat

    garde = _retirer_texte(dest, entree)
    _retirer_genere_document(dest, rel)
    _retirer_entree_cache(dest, cle_cache)
    return {"ok": True, "message": MESSAGES["restauration_texte_garde"]} if garde else {"ok": True}


def _restaurer_depuis_moodle(dest, rel, chemin, cfg, *, confirme, arreter):
    """Repli de 3.3 (O13) : le PDF cherchable est retelecharge depuis Moodle et compare a `genere`.

    None quand le PDF d'origine est en place et que les suppressions de 3.3 doivent suivre ; un dict quand la
    reponse est complete (`{"ok": True}` : deja l'original, rien a faire ; `{"confirmer": ...}` : fichier modifie
    a la main, sans aucune requete).
    """
    trouve = _entree_etat(dest, rel)
    if trouve is None:
        raise ErreurOcr("non_suivi")
    cle_etat, entree = trouve
    genere = _genere_complet(entree.get("genere"))
    if genere is None:
        return {"ok": True}          # deja l'original : rien n'est telecharge ni supprime
    actuel = identite(chemin)
    if (actuel["taille"], actuel["empreinte"]) == (genere["taille_source"], genere["empreinte_source"]):
        return None                  # coupure d'un remplacement : le fichier est deja l'original
    if (actuel["taille"], actuel["empreinte"]) != (genere["taille_fichier"], genere["empreinte_fichier"]) and not confirme:
        return {"confirmer": MESSAGES["modifie_main"]}

    jeton = cfg.get("token") if isinstance(cfg, dict) else None
    if not isinstance(jeton, str) or not jeton:
        raise ms.SessionExpiree("Tu n'es pas connecté à Moodle. Connecte-toi, puis réessaie : ton PDF cherchable reste en place.")
    part = chemin + ".ocr.part"
    try:
        try:
            ms.retelecharger(ms.cle_url(cle_etat), jeton, part, arreter, attendu=ms.type_attendu(os.path.basename(rel)))
        except ms.HorsLigne as e:
            _signaler(e)
            raise ErreurOcr("hors_ligne") from None
        except PermissionError as e:
            _signaler(e)
            raise ErreurOcr("verrouille") from None
        recu = identite(part)
        if (recu["taille"], recu["empreinte"]) != (genere["taille_source"], genere["empreinte_source"]):
            raise ErreurOcr("restauration_differente")
        _remplacer(part, chemin)
    finally:
        try:
            os.remove(part)
        except OSError:
            pass
    return None


def _retirer_texte(dest, entree):
    """Supprime le texte a cote d'une source restauree (3.3). Vrai quand un texte edite a la main a ete laisse,
    et que la phrase `restauration_texte_garde` doit le dire (O6, invariant 3)."""
    sortie = entree.get("sortie")
    if not isinstance(sortie, str) or not sortie:
        return False
    texte = _resoudre_sortie(dest, sortie)
    if not os.path.isfile(texte):
        return False
    if not _texte_regenerable(texte, entree):
        return True
    _supprimer(texte)
    return False


def _retirer_genere_document(dest, rel):
    """Retire `genere` de l'entree d'etat du document (3.3), s'il y en a une ; `t` et `chemin` restent."""
    trouve = _entree_etat(dest, rel)
    if trouve is not None:
        _retirer_genere(dest, trouve[0])


def _retirer_entree_cache(dest, cle_cache):
    """Retire l'entree de cache du document (3.3) : il redevient « Non traite ». La copie d'original qu'aucune
    autre entree ne nomme est supprimee avec elle."""
    if not cle_cache:
        return
    cache = charger_cache(dest)
    entree = cache["documents"].pop(cle_cache, None)
    sauver_cache(dest, cache)
    original = (entree or {}).get("original")
    fichier = original.get("fichier") if isinstance(original, dict) else ""
    if not fichier:
        return
    for autre in cache["documents"].values():
        copie = autre.get("original") if isinstance(autre, dict) else None
        if isinstance(copie, dict) and copie.get("fichier") == fichier:
            return
    chemin = _resoudre_original(dest, fichier)
    if chemin:
        _supprimer(chemin)


def reconcilier_etat(dest):
    """Retire `genere` des entrees dont le fichier a encore l'identite de la SOURCE (remplacement interrompu entre
    l'ecriture de l'etat et `os.replace`, invariant 5, ou restauration interrompue), et renvoie le nombre corrigees.

    Un fichier qui a l'identite du PDF cherchable, qui a une autre identite (modifie a la main, invariant 8), qui manque
    ou qu'on ne peut pas lire n'est pas touche. La taille filtre : l'empreinte entiere n'est calculee que sur une taille
    egale a `taille_source`. L'etat n'est reecrit que s'il change ; l'echec d'ecriture est signale et rend 0.
    """
    etat = ms.charger_etat(dest)
    if not isinstance(etat, dict):
        return 0
    corriges = 0
    for entree in etat.values():
        genere = _genere_complet(entree.get("genere")) if isinstance(entree, dict) else None
        rel = entree.get("chemin") if genere else None
        if not isinstance(rel, str) or not rel:
            continue
        chemin = os.path.join(dest, rel)
        try:
            if os.path.getsize(chemin) != genere["taille_source"]:
                continue
            empreinte = _sha256(chemin)
        except OSError:
            continue
        if empreinte == genere["empreinte_source"] and empreinte != genere["empreinte_fichier"]:
            del entree["genere"]
            corriges += 1
    if not corriges:
        return 0
    try:
        ms.sauver_etat(dest, etat)
    except OSError as e:
        _signaler(e)
        return 0
    return corriges


def supprimer_parts_orphelins(dest):
    """Supprime les `*.ocr.part` abandonnes par une coupure (invariant 5, ecart 62) et renvoie leur nombre. A appeler au
    lancement, hors extraction. Dossiers caches ignores (`.moodlesync-ocr/`), un autre `.part` n'est jamais touche."""
    if not os.path.isdir(dest):
        return 0
    supprimes = 0
    for racine, dossiers, fichiers in os.walk(dest):
        dossiers[:] = [d for d in dossiers if not d.startswith(".")]
        for nom in fichiers:
            if nom.lower().endswith(".ocr.part"):
                try:
                    os.remove(os.path.join(racine, nom))
                    supprimes += 1
                except OSError as e:
                    _signaler(e)
    return supprimes


# ---------------------------------------------------------------------------------------------
# Ce qui reste de la tache C5 : l'ecriture atomique du texte (R1b s'en sert, R2 la reprend) et les
# orphelins (invariant 11, releves par `ocr_etat`, repris par R4). Aucun appel au moteur.
# ---------------------------------------------------------------------------------------------
def _ecrire_texte(chemin, contenu):
    """Ecriture atomique (.tmp puis os.replace), UTF-8 sans BOM, fins de ligne LF. Une erreur d'ecriture leve
    OSError, le fichier precedent reste intact et aucun .tmp ne subsiste."""
    os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
    temporaire = chemin + ".tmp"
    try:
        with open(temporaire, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenu)
        _remplacer_travail(temporaire, chemin)
    except BaseException:
        try:
            os.remove(temporaire)
        except OSError:
            pass
        raise


# ------------------------------------------------------------------ copies d'originaux (4.2, 4.7)
def originaux(dest):
    """(nombre, octets) des copies d'originaux presentes dans `.moodlesync-ocr/originaux/` (contrat 4.2).

    Le dossier est cache : `moteur.index_existant` ne le voit pas. Un dossier absent rend (0, 0), jamais une erreur.
    """
    nombre, octets = 0, 0
    for chemin in _fichiers_originaux(dest):
        try:
            octets += os.path.getsize(chemin)
        except OSError as e:
            _signaler(e)
            continue
        nombre += 1
    return nombre, octets


def _fichiers_originaux(dest):
    """Chemins absolus des copies presentes dans le dossier des originaux (liste vide s'il n'existe pas)."""
    dossier = _chemin_ocr(dest, DOSSIER_ORIGINAUX)
    sortie = []
    try:
        with os.scandir(dossier) as entrees:
            for entree in entrees:
                try:
                    if entree.is_file():
                        sortie.append(entree.path)
                except OSError:
                    continue
    except OSError:
        return []
    return sorted(sortie)


def supprimer_originaux(dest):
    """Supprime toutes les copies d'originaux et rend le volume libere (nombre, octets) (contrat 4.7, O15).

    Les entrees de cache concernees passent a `original: null` (2.2) : les documents ne sont plus restaurables que
    par Moodle (O13), et le cache ne nomme plus un fichier absent. Le dossier vide est retire ; un fichier qui
    resiste est signale et laisse en place, sans faire echouer le reste.
    """
    nombre, octets = originaux(dest)
    cache = charger_cache(dest)
    modifie = False
    for entree in (cache.get("documents") or {}).values():
        if isinstance(entree, dict) and entree.get("original") is not None:
            entree["original"] = None
            modifie = True
    for chemin in _fichiers_originaux(dest):
        _supprimer(chemin)
    try:
        os.rmdir(_chemin_ocr(dest, DOSSIER_ORIGINAUX))
    except OSError:
        pass                      # dossier absent, ou copie qui resiste : rien a signaler de plus
    if modifie:
        sauver_cache(dest, cache)
    return nombre, octets


# ------------------------------------------------------------------ texte copiable (4.7)
def _sans_entete(texte, format_):
    """Texte d'un document sans son en-tete (contrat 4.7) : le front matter d'un `.md` et sa section « Pages a
    verifier » sont retires, le reste du fichier est rendu tel quel. Un `.txt` n'a pas d'en-tete (O5)."""
    if format_ != "md":
        return texte.strip("\n")
    lignes = texte.split("\n")
    if lignes and lignes[0].strip() == "---":
        for i in range(1, len(lignes)):
            if lignes[i].strip() == "---":
                lignes = lignes[i + 1:]
                break
    garde = []
    for ligne in lignes:
        if ligne.strip() == "## Pages à vérifier":
            break
        garde.append(ligne)
    return "\n".join(garde).strip("\n")


def _pages_texte(texte):
    """Nombre de pages marquees dans le texte copie : `[p. n]` du `.txt`, `<!-- page n -->` du `.md`."""
    return len(re.findall(r"(?m)^\[p\. \d+\]$|^<!-- page \d+ -->$", texte))


def texte_copiable(dest, chemin_rel):
    """(texte, pages) du document, tel qu'on le copie (contrat 4.7) ; ("", 0) s'il n'a pas de texte.

    Le chemin du texte vient de l'entree de cache (`sortie`). Le texte est rendu sans front matter ni section
    « Pages a verifier ». Le nombre de pages est celui du cache ; sans lui, celui des marques du texte.
    """
    trouve = trouver_entree(charger_cache(dest), chemin_rel, "", 0)
    entree = trouve[1] if trouve and isinstance(trouve[1], dict) else {}
    sortie = entree.get("sortie")
    if not isinstance(sortie, str) or not sortie:
        return "", 0
    chemin = _resoudre_sortie(dest, sortie)
    try:
        with open(chemin, encoding="utf-8") as f:
            brut = f.read()
    except (OSError, UnicodeDecodeError) as e:
        _signaler(e)
        return "", 0
    format_ = entree.get("format")
    if format_ not in FORMATS_TEXTE:
        format_ = os.path.splitext(chemin)[1].lower().lstrip(".")
    texte = _sans_entete(brut, format_)
    pages = entree.get("pages")
    if isinstance(pages, bool) or not isinstance(pages, int) or pages < 0:
        pages = _pages_texte(texte)
    return texte, pages
