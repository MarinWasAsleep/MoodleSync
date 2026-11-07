#!/usr/bin/env python3
"""MoodleSync, extraction du texte des scans : detection du moteur Tesseract et configuration.

Tache C1 : detection du moteur (Tesseract 4 ou 5) et reglages d'appel. Aucune extraction ici :
le rendu, le TSV, le Markdown, le cache, la file et la superposition viennent avec les taches
C2 et suivantes, et n'existent pas encore.

Le moteur n'est pas forcement dans le PATH : la detection essaie, dans l'ordre du plan 5.2, le
chemin de la configuration (ocr_exe), shutil.which, le registre Windows, les chemins usuels, puis
macOS. Le paquet portable (etape 6 du plan) est sans objet en 2.5. Aucun appel reseau
(invariant 6). detecter ne leve jamais et n'ecrit aucune trace technique.
"""
import os, re, shutil, subprocess, sys, time

CACHE = ".moodlesync-ocr"
SEUIL_TEXTE = 80
SEUILS_QUALITE = (0.85, 0.70)   # conserves, non calibres (D11)

# CREATE_NO_WINDOW (0x08000000, aucune console noire) et BELOW_NORMAL_PRIORITY_CLASS (0x00004000,
# priorite basse), sous Windows seulement : creationflags n'existe pas sur macOS.
CREATIONFLAGS = 0x08000000 | 0x00004000

MESSAGES = {
    "moteur_absent": "Le moteur d'extraction n'est pas encore installé. Indique où il se trouve dans les réglages.",
    "langue_manquante": "Il manque une langue de reconnaissance. MoodleSync utilise celle qui est disponible : la qualité peut baisser.",
}

BLOC_ABSENT = {
    "present": False, "version": "", "source": "", "exe": "",
    "langues": [], "langues_effectives": "", "repli": False,
    "message": MESSAGES["moteur_absent"], "tessdata": "", "majeure": 0,
}

RE_VERSION = re.compile(r"tesseract\s+(\d+(?:\.\d+)*)")
RE_LANGUE = re.compile(r"^[a-z]{3}$")


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
                    out, err = p.communicate()
                    return -1, out, err
    except Exception:
        return -1, b"", b""


def _exe_config(cfg):
    exe = (cfg.get("ocr_exe") or "").strip()
    return exe if exe and os.path.isfile(exe) else None


def _exe_registre():
    """Chemin de tesseract.exe lu dans le registre Windows (Path ou InstallDir), ou None."""
    if os.name != "nt":
        return None
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
                    exe = os.path.join(dossier or "", "tesseract.exe")
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


def _trouver(cfg):
    """Renvoie (chemin, source) d'apres l'ordre du plan 5.2, ou (None, None)."""
    exe = _exe_config(cfg)
    if exe:
        return exe, "config"
    exe = shutil.which("tesseract")
    if exe:
        return exe, "path"
    exe = _exe_registre()
    if exe:
        return exe, "registre"
    exe = _exe_usuel()
    if exe:
        return exe, "usuel"
    return None, None


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
    """Codes de langue (3 lettres minuscules) depuis la sortie de tesseract --list-langs."""
    texte = (stdout or b"").decode("utf-8", "replace")
    return [ligne.strip() for ligne in texte.splitlines() if RE_LANGUE.match(ligne.strip())]


def _langues_effectives(demandees, disponibles):
    """Langues a employer apres repli : les demandees presentes, sinon la premiere disponible."""
    voulues = [l for l in (demandees or "").split("+") if l]
    gardees = [l for l in voulues if l in disponibles]
    if gardees:
        return "+".join(gardees), gardees != voulues
    if disponibles:
        return disponibles[0], True
    return "", True


def _dossier_tessdata(cfg, exe):
    """Dossier des donnees de langue : ocr_tessdata, puis TESSDATA_PREFIX, puis le dossier du programme."""
    d = (cfg.get("ocr_tessdata") or "").strip()
    if d:
        return d
    d = (os.environ.get("TESSDATA_PREFIX") or "").strip()
    if d:
        return d
    return os.path.join(os.path.dirname(exe), "tessdata")


def detecter(cfg):
    """Detecte Tesseract et renvoie le bloc moteur (forme 2.7) plus tessdata et majeure. Ne leve jamais.

    Version 4 ou 5 exigee ; une version 3 est traitee comme un moteur absent.
    """
    try:
        return _detecter(cfg)
    except Exception:
        return dict(BLOC_ABSENT)


def _detecter(cfg):
    bloc = dict(BLOC_ABSENT)
    exe, source = _trouver(cfg)
    if not exe:
        return bloc
    code, out, _ = executer([exe, "--version"], delai=5)
    version, majeure = _version(out)
    if code != 0 or majeure not in (4, 5):
        return bloc
    code, out_langues, _ = executer([exe, "--list-langs"], delai=5)
    langues = _langues(out_langues)
    effectives, repli = _langues_effectives(cfg.get("ocr_langues") or "fra+eng", langues)
    bloc.update({
        "present": True,
        "version": version,
        "source": source,
        "exe": exe,
        "langues": langues,
        "langues_effectives": effectives,
        "repli": repli,
        "message": "",
        "tessdata": _dossier_tessdata(cfg, exe),
        "majeure": majeure,
    })
    return bloc


def reglages_depuis(cfg):
    """Reglages d'appel Tesseract (contrat 3.1), avec les langues effectives apres repli."""
    moteur = detecter(cfg)
    return {
        "langues": moteur["langues_effectives"],
        "dpi": int(cfg.get("ocr_dpi", 300)),
        "psm": int(cfg.get("ocr_psm", 3)),
        "oem": 1,
        "moteur": moteur["version"],
        "tessdata": moteur["tessdata"],
    }
