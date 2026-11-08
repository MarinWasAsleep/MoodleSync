#!/usr/bin/env python3
"""MoodleSync, extraction du texte des scans : detection du moteur Tesseract et extraction d'une page.

Tache C1 : detection du moteur (Tesseract 4 ou 5) et reglages d'appel.
Tache C2 : une page (texte natif, rendu, reconnaissance, TSV, qualite) et le Markdown d'un document.
Tache C3 : cache, empreinte, reprise par page, file, document entier.
Tache C4 : PDF cherchable (identite, marque, controle, superposition d'une couche TSV, verification, remplacement).
Les sorties de cours (C5), la restauration et la reconciliation (Y2) n'existent pas encore.

Le moteur n'est pas forcement dans le PATH : la detection essaie, dans l'ordre du plan 5.2, le
chemin de la configuration (ocr_exe), shutil.which, le registre Windows, les chemins usuels, puis
macOS. Le paquet portable (etape 6 du plan) est sans objet en 2.5. Aucun appel reseau
(invariant 6). detecter ne leve jamais et n'ecrit aucune trace technique. pypdf, Pillow et
pypdfium2 sont importes a l'usage seulement (D11) : sans eux, la detection reste utilisable.
"""
import copy, hashlib, json, logging, os, re, shutil, subprocess, sys, tempfile, threading, time, unicodedata

from . import moteur as ms
from .marque import CLE_MARQUE, _entier_vrai, _marque_du_lecteur, lire_marque

CACHE = ".moodlesync-ocr"
SEUIL_TEXTE = 80
SEUILS_QUALITE = (0.85, 0.70)   # conserves, non calibres (D11)
DELAI_PAGE = 120                # secondes par page pour le moteur (plan 5.4)
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
    bloc = _bloc_absent()
    exe, source = _trouver(cfg)
    if not exe:
        return bloc
    code, out, err = executer([exe, "--version"], delai=5)
    version, majeure = _version(out + err)
    if code != 0 or majeure not in (4, 5):
        return bloc
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
# Tache C2 : une page (texte natif, rendu, reconnaissance, TSV, qualite) et le Markdown d'un document.
# ---------------------------------------------------------------------------------------------
ACTION = "Texte des cours"


def _signaler(e):
    """Detail technique dans erreurs.txt (invariant 9) ; la phrase lisible vient de MESSAGES."""
    try:
        ms.message_erreur(e, ACTION)
    except Exception:
        pass


def _sans_trace(valeur_vide):
    """Invariant 9 : aucune exception technique ne sort d'une fonction de sortie de C5. Le detail part dans
    erreurs.txt (_signaler) et l'appelant recoit la valeur vide de la fonction (texte vide, nombre zero, liste
    ou chemin vide) au lieu d'un traceback. ms.Annule passe telle quelle : c'est une annulation demandee."""
    def envelopper(fonction):
        def enveloppe(*args, **kw):
            try:
                return fonction(*args, **kw)
            except ms.Annule:
                raise
            except Exception as e:
                _signaler(e)
                return valeur_vide() if callable(valeur_vide) else valeur_vide
        enveloppe.__name__ = fonction.__name__
        enveloppe.__doc__ = fonction.__doc__
        return enveloppe
    return envelopper


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
    try:
        mots = _reconnaitre(image, numero, reglages, exe, arreter)
    finally:
        try:
            image.close()
        except Exception:
            pass
    texte, confiance = reconstruire(mots)
    boites = [[m["x"], m["y"], m["l"], m["h"], m["conf"], m["texte"]] for m in mots] if avec_boites else None
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


# ---------------------------------------------------------------------------------------------
# Tache C3 : cache, empreinte, reprise par page, file, document entier.
# ---------------------------------------------------------------------------------------------
VERSION_JSON = 1
EXT_IMAGES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")   # plan 4.1
CODES_REFUS = ("numerique", "signe", "protege", "lecture_seule")             # traiter_document : « refuse »


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
        os.replace(temporaire, chemin)
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


def _genere(dest, chemin_rel):
    """Bloc `genere` (2.1) de l'etat de synchronisation pour ce chemin, ou None. Un bloc incomplet ou de version
    superieure est ignore : le fichier est alors traite comme natif."""
    etat = ms.charger_etat(dest)
    if not isinstance(etat, dict):
        return None
    voulu = _comparable(_cle(chemin_rel))
    for valeur in etat.values():
        if not isinstance(valeur, dict) or not isinstance(valeur.get("chemin"), str):
            continue
        genere = valeur.get("genere")
        if not isinstance(genere, dict) or _comparable(_cle(valeur["chemin"])) != voulu:
            continue
        version = genere.get("version", 1)
        if (genere.get("type") == "pdf_cherchable" and isinstance(version, int) and version <= 1
                and isinstance(genere.get("empreinte_source"), str) and genere["empreinte_source"]
                and isinstance(genere.get("taille_source"), int) and not isinstance(genere.get("taille_source"), bool)):
            return genere
    return None


def _identite_source(dest, chemin_rel, chemin):
    """(empreinte, taille, genere) de la SOURCE (2.3) : sha256 du fichier entier, ou, pour un PDF cherchable,
    l'identite du PDF recu de Moodle consignee dans `genere` (le fichier lui-meme n'est alors pas lu)."""
    genere = _genere(dest, chemin_rel)
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


# ------------------------------------------------------------------ chemin de sortie (2.6)
def _nom_dossier_sortie(cfg):
    """`ocr_dossier` s'il est un nom simple (ni separateur, ni `..`, ni caractere interdit), sinon « Textes ».
    T[\"textes\"] n'existe pas encore (Y1) : le nom anglais n'est pas deduit de la langue."""
    nom = cfg.get("ocr_dossier")
    if isinstance(nom, str):
        nom = ms.nfc(nom.strip())
        if nom and nom not in (".", "..") and not ms.ILLEGAL.search(nom):
            return nom
    return "Textes"


def _chemin_sortie(dest, cfg, chemin_rel):
    """(chemin du .md, valeur de `sortie`). Relatif a dest avec `/`, ou absolu si `ocr_sortie_hors_coffre`
    (dossier de donnees de MoodleSync : le contrat ne dit pas ou, choix deduit)."""
    nom = _nom_dossier_sortie(cfg)
    parties = _cle(chemin_rel).split("/")
    parties[-1] += ".md"
    if cfg.get("ocr_sortie_hors_coffre"):
        md = ms.nfc(os.path.join(ms.APP_DIR, nom, *parties))
        return md, md
    return os.path.join(dest, nom, *parties), "/".join([nom] + parties)


def _resoudre_sortie(dest, sortie):
    return sortie if os.path.isabs(sortie) else os.path.join(dest, *sortie.split("/"))


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
    """Vrai si l'entree est valide et si son Markdown existe a l'endroit voulu par les reglages actuels."""
    sortie = entree.get("sortie")
    if not entree_valide(entree, empreinte, cles) or not isinstance(sortie, str) or not sortie:
        return False
    return sortie == _chemin_sortie(dest, cfg, chemin_rel)[1] and os.path.isfile(_resoudre_sortie(dest, sortie))


def _a_jour(dest, cfg, chemin_rel, chemin, cache, cles):
    """Fraicheur d'un document sans rien ecrire : l'empreinte n'est calculee que si une entree de meme taille existe."""
    entree = (trouver_entree(cache, chemin_rel, "", 0) or (None, None))[1]
    if entree is None:
        return False
    try:
        if not _genere(dest, chemin_rel) and entree.get("taille") != os.path.getsize(chemin):
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


def extraire_document(dest, chemin_rel, cfg, *, progres=None, arreter=None, attendre=None, refaire=False):
    """Extrait le texte d'un document et renvoie son entree de cache (2.3). Ne modifie jamais le PDF source.

    Un document inchange (meme empreinte, memes reglages, Markdown present) n'est pas refait. Sinon : le moteur est
    detecte une fois (ecart 35), les pages deja faites sont reprises de `pages/<empreinte>.json`, les autres sont
    extraites une a une (fichier de reprise reecrit apres chacune), puis le .md est ecrit, le cache mis a jour et
    le fichier de reprise supprime. `progres({"document", "page", "pages"})` suit chaque page ; `attendre()` est
    appele entre deux pages ; `arreter()` vrai leve ms.Annule, les pages faites restent. `refaire` ignore l'entree
    de cache du document (ajout a la signature de 3.1, pour la tache `refaire` de la file).
    Leve ErreurOcr (protege, corrompu, trop_gros, verrouille, moteur_absent, langue_manquante) ou ms.Annule.
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
    exe = moteur.get("exe") or ""
    md, sortie = _chemin_sortie(dest, cfg, rel)

    cache = charger_cache(dest)
    trouve = trouver_entree(cache, rel, empreinte, taille)
    precedente, cle_cache = None, rel
    if trouve:
        meme_chemin = _comparable(_cle(trouve[0])) == _comparable(rel)
        if meme_chemin:
            precedente, cle_cache = trouve[1], trouve[0]
            if not refaire and _entree_a_jour(dest, cfg, rel, precedente, empreinte, cles):
                return dict(precedente)
        elif not os.path.exists(_absolu(dest, trouve[0])):
            precedente = trouve[1]   # deplacement : l'ancienne entree et son .md restent (orphelins, invariant 11)
    meme_contenu = bool(precedente) and precedente.get("empreinte") == empreinte

    nb = _nb_pages(chemin)
    avec_boites = cfg.get("ocr_pdf") == "remplacer"
    faites = _charger_reprise(dest, empreinte, cles, nb, avec_boites)
    forcees = _pages_forcees(genere, precedente, empreinte, nb)

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
                page = extraire_page(chemin, n, reglages, forcer_ocr=n in forcees, arreter=arreter, exe=exe,
                                     avec_boites=avec_boites)
            except ErreurOcr as e:
                if e.code != "illisible":
                    raise
                illisibles.append(n)
            else:
                pages.append(page)
                faites[n] = _format_page(page, avec_boites)
                _sauver_reprise(dest, empreinte, cles, nb, faites)
            traitees += 1
        if progres is not None:
            progres({"document": rel, "page": n, "pages": nb})

    date = _maintenant()
    try:
        ecrire_document_md(md, rel, pages, reglages, illisibles=illisibles, date=date)
    except PermissionError as e:
        _signaler(e)
        raise ErreurOcr("verrouille") from None
    resume = _resume_pages(pages, nb)
    entree = {
        "empreinte": empreinte, "taille": taille, "pages": nb,
        "pages_texte": resume["pages_texte"], "pages_ocr": resume["pages_ocr"],
        "numeros_ocr": sorted(p["numero"] for p in pages if p["source"] == "ocr"),
        "pages_vides": resume["pages_vides"] + len(illisibles),   # une page illisible n'a pas de texte : somme egale a `pages`
        "extraction": resume["extraction"], "confiance": resume["confiance"],
        "langues": cles["langues"], "dpi": cles["dpi"], "psm": cles["psm"], "moteur": cles["moteur"],
        "sortie": sortie, "etat": _etat_document(pages, len(illisibles)),
        "verifie": bool(meme_contenu and precedente and precedente.get("verifie")), "date": date,
    }
    cache["documents"][cle_cache] = entree
    sauver_cache(dest, cache)
    if not avec_boites:
        _supprimer_reprise(dest, empreinte)   # en mode remplacer, la reprise sert la fabrication (ecart 60)
    return dict(entree)


def traiter_document(dest, chemin_rel, cfg, **options):
    """extraire_document puis, si cfg[\"ocr_pdf\"] == \"remplacer\", fabriquer_pdf_cherchable (C4, reference en avant :
    la fonction n'existe pas encore). {\"entree\", \"pdf\": \"aucun|remplace|refuse|echec\", \"message\"}. Un echec du PDF
    n'annule pas le texte, deja ecrit."""
    entree = extraire_document(dest, chemin_rel, cfg, **options)
    resultat = {"entree": entree, "pdf": "aucun", "message": ""}
    if cfg.get("ocr_pdf") != "remplacer" or not _est_pdf(chemin_rel):
        return resultat
    try:
        fabriquer_pdf_cherchable(dest, chemin_rel, cfg, arreter=options.get("arreter"))
    except ms.Annule:
        raise
    except ErreurOcr as e:
        resultat["pdf"] = "refuse" if e.code in CODES_REFUS else "echec"
        resultat["message"] = str(e)
    except Exception as e:
        resultat["pdf"] = "echec"
        resultat["message"] = ms.message_erreur(e, ACTION)
    else:
        resultat["pdf"] = "remplace"
        try:
            resultat["message"] = MESSAGES.get("pdf_genere", "").format(nom=os.path.basename(chemin_rel))
        except (KeyError, IndexError, ValueError):
            resultat["message"] = ""
    return resultat


def archiver_texte(dest, chemin_rel, t_ancien):
    """Renomme le .md genere d'un document en « ancienne version » (moteur.nom_ancienne_version) et renvoie son
    nouveau chemin absolu. None s'il n'y a pas de .md connu au cache, ou s'il a ete edite a la main (invariant 8,
    meme garde que ecrire_document_md). Une erreur du systeme de fichiers leve OSError."""
    voulu = _comparable(_cle(chemin_rel))
    entree = next((e for k, e in charger_cache(dest)["documents"].items() if _comparable(_cle(k)) == voulu), None)
    sortie = entree.get("sortie") if entree else None
    if not isinstance(sortie, str) or not sortie:
        return None
    md = _resoudre_sortie(dest, sortie)
    if not os.path.isfile(md) or not _regenerable(md):
        return None
    nouveau = ms.nom_ancienne_version(md, t_ancien)
    os.replace(md, nouveau)
    return nouveau


# ------------------------------------------------------------------ file de travail (2.5)
def _file_vide():
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


def _nom_en_minuscules(texte):
    return ms.nfc(texte).casefold()


def _dossiers_sortie(cfg):
    return {_nom_en_minuscules(_nom_dossier_sortie(cfg)), "textes", "texts"}


def _est_ancienne_version(nom):
    return any("(" + langue["ancienne"] + " " in nom for langue in ms.LANGUES.values() if "ancienne" in langue)


def _eligible(dest, cfg, chemin_rel):
    """Chemin absolu du document s'il peut entrer en file (2.5), sinon None : ni `Textes/` (dossier place directement
    dans dest), ni dossier ou fichier cache (`.moodlesync-ocr/`), ni « ancienne version », ni `.md`, ni plus de
    `ocr_max_mo`. Seuls les PDF et les images sont pris (plan 4.1)."""
    parties = _cle(chemin_rel).split("/")
    if not parties[0] or ".." in parties or any(p.startswith(".") for p in parties):
        return None
    if len(parties) > 1 and _nom_en_minuscules(parties[0]) in _dossiers_sortie(cfg):
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


def _candidats(dest, cfg):
    """Chemins relatifs des documents eligibles, tries par cours, section et nom (ms.cle_nom)."""
    sorties = _dossiers_sortie(cfg)
    trouves = set()
    for racine, dossiers, fichiers in os.walk(dest):
        dossiers[:] = [d for d in dossiers if not d.startswith(".")
                       and not (racine == dest and _nom_en_minuscules(d) in sorties)]
        for nom in fichiers:
            rel = _cle(os.path.relpath(os.path.join(racine, nom), dest))
            if _eligible(dest, cfg, rel):
                trouves.add(rel)
    return sorted(trouves, key=lambda r: [ms.cle_nom(p) for p in r.split("/")])


def _dossier_du_cours(cfg, cid):
    """Dossier du cours `cid` d'apres cfg[\"cours\"][cid][\"dossier\"] (choix de l'utilisateur), sinon None : le nom
    par defaut vient de Moodle et n'est pas connu hors ligne."""
    cours = cfg.get("cours")
    choix = cours.get(str(cid)) if isinstance(cours, dict) else None
    dossier = choix.get("dossier") if isinstance(choix, dict) else None
    return _cle(ms.nettoie_dossier(dossier)) if isinstance(dossier, str) and dossier.strip() else None


def _tache(chemin_rel, etat, pages, message="", refaire=False):
    tache = {"chemin": chemin_rel, "etat": etat, "priorite": 0, "pages": pages, "pages_faites": 0,
             "ajoute": _maintenant(), "message": message}
    if refaire and etat == "attente":
        tache["refaire"] = True
    return tache


def constituer_file(dest, cfg, portee, refaire=False):
    """Constitue la file de la portee (2.5) et l'ecrit dans file.json (etat `inactive`) ; ne lance rien.

    `tout` : tous les documents eligibles sans entree de cache valide ; `sans_texte` : parmi eux, ceux qui ont au
    moins une page a reconnaitre (scans, PDF mixtes, images) ; `cours:<cid>` : `tout` limite au dossier du cours ;
    `document:<chemin>` : ce document. `refaire` ignore le cache (les taches portent alors `\"refaire\": true`).
    Un PDF illisible ou protege devient une tache `ignore` avec la phrase de la section 5. Renvoie la file ecrite."""
    portee = portee if isinstance(portee, str) and portee else "sans_texte"
    cles = _cles_reglages(_reglages_moteur(cfg, detecter(cfg)))
    cache = charger_cache(dest)
    if portee.startswith("document:"):
        rel = _cle(portee[len("document:"):])
        choisis = [rel] if rel and _eligible(dest, cfg, rel) else []
    else:
        choisis = _candidats(dest, cfg)
        if portee.startswith("cours:"):
            dossier = _dossier_du_cours(cfg, portee[len("cours:"):])
            choisis = [r for r in choisis if dossier and r.startswith(dossier + "/")]
        elif portee not in ("tout", "sans_texte"):
            choisis = []
    taches = []
    for rel in choisis:
        chemin = _absolu(dest, rel)
        if not refaire and _a_jour(dest, cfg, rel, chemin, cache, cles):
            continue
        try:
            pages = _nb_pages(chemin)
            if portee == "sans_texte" and not _a_reconnaitre(chemin):
                continue
        except ErreurOcr as e:
            taches.append(_tache(rel, "ignore", 0, str(e)))
            continue
        taches.append(_tache(rel, "attente", pages, refaire=refaire))
    file = {"version": VERSION_JSON, "etat": "inactive", "portee": portee, "cree": _maintenant(), "taches": taches}
    sauver_file(dest, file)
    return file


def mettre_en_file_apres_sync(dest, cfg, compte_rendu):
    """Ajoute a la file les chemins de compte_rendu[\"a_preparer\"] (D7) et renvoie le nombre de taches mises en
    attente. Un chemin deja en attente n'est pas ajoute ; une tache terminee dont le fichier est republie revient
    en attente. Les documents non eligibles (2.5) sont ignores. L'etat de la file n'est pas modifie."""
    chemins = compte_rendu.get("a_preparer") if isinstance(compte_rendu, dict) else None
    if not isinstance(chemins, list) or not chemins:
        return 0
    file = charger_file(dest)
    existantes = {_comparable(_cle(t["chemin"])): t for t in file["taches"]}
    ajoutes = 0
    for brut in chemins:
        if not isinstance(brut, str) or _eligible(dest, cfg, brut) is None:
            continue
        rel = _cle(brut)
        existante = existantes.get(_comparable(rel))
        if existante is not None and existante.get("etat") in ("attente", "en_cours"):
            continue
        try:
            nouvelle = _tache(rel, "attente", _nb_pages(_absolu(dest, rel)))
        except ErreurOcr as e:
            nouvelle = _tache(rel, "ignore", 0, str(e))
        if existante is None:
            file["taches"].append(nouvelle)
            existantes[_comparable(rel)] = nouvelle
        else:
            existante.clear()
            existante.update(nouvelle)
        ajoutes += nouvelle["etat"] == "attente"
    if ajoutes or file["taches"]:
        file["cree"] = file["cree"] or _maintenant()
        sauver_file(dest, file)
    return ajoutes


# ---------------------------------------------------------------------------------------------
# Tache C4 : PDF cherchable (identite, marque, controle, superposition, verification, remplacement).
# ---------------------------------------------------------------------------------------------
NOM_POLICE = "MoodleSyncF"        # nom de la police de la couche dans /Resources /Font de chaque page reconnue
OCTETS_PAR_PAGE = 10 * 1024       # D10 : volume maximal de la couche par page reconnue, flux compresse
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
# Tache C5 : Markdown de cours, index, qualite, contexte copiable, JSONL, orphelins.
# Aucun appel au moteur, aucun rendu, aucun reseau (invariant 6) : C5 lit le cache et les .md.
# ---------------------------------------------------------------------------------------------
PHRASE_COURS = "Texte extrait localement par MoodleSync. Les citations indiquent la page du PDF, pas la page imprimée."
TITRE_COURS = "texte des documents"      # plan 6.2 : « # <Cours> : texte des documents »
TITRE_INDEX = "Textes des cours"         # plan 6.3
TITRE_QUALITE = "Qualité des textes"     # contrat 2.6
RE_PAGE = re.compile(r"^<!-- page (\d+) -->$")
RE_LIEN = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
RE_ENTETE = re.compile(r"^#{1,6} ")
RE_PUCE = re.compile(r"^[-*+] ")
RE_SOULIGNE = re.compile(r"^([_*]{1,3})(\S.*?)\1$")
RE_FERMETURE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
RE_FIN_PHRASE = re.compile(r"(?<=[.!?»])\s+(?=\S)")


def _sans_marque(texte):
    """Texte sans la marque de regeneration (premiere ligne de ms.MARQUE) : elle n'entre pas dans un agregat."""
    lignes = texte.split("\n")
    if lignes and lignes[0].strip() == ms.MARQUE:
        return "\n".join(lignes[1:])
    return texte


def _front_matter(lignes):
    """(champs du front matter, index de la premiere ligne du corps). Le front matter n'est reconnu que ferme
    par un `---` (meme regle que _regenerable, ecart 45) ; sans lui, le corps commence a la premiere ligne."""
    if not lignes or lignes[0].strip() != "---":
        return {}, 0
    champs = {}
    for i, ligne in enumerate(lignes[1:], 1):
        if ligne.strip() == "---":
            return champs, i + 1
        cle, _, valeur = ligne.partition(":")
        if valeur.strip():
            valeur = valeur.strip()
            try:
                champs[cle.strip()] = json.loads(valeur)
            except ValueError:
                champs[cle.strip()] = valeur
    return {}, 0   # front matter jamais ferme : fichier de l'utilisateur, traite comme du texte


def _pages_md(texte):
    """Pages d'un .md de document (plan 6.1) : [(numero, texte de la page)], dans l'ordre du fichier.

    Seuls les marqueurs `<!-- page n -->` decoupent les pages ; sans marqueur, le corps entier est la page 1.
    Les lignes de front matter, l'entete de C2 (titre, `> Source`, resume) et la section « Pages à vérifier »
    sont retirees : ce n'est pas du texte de cours. C2 n'ecrit cette section qu'apres la derniere page, mais un
    fichier edite a la main peut la placer ailleurs : une fois rencontree, elle ferme le texte et tout ce qui la
    suit est ignore, comme le fait deja l'agregat pour le premier document. Aucun contenu n'est invente : une
    page vide reste vide.
    """
    lignes = _sans_marque(texte).split("\n")
    _, debut = _front_matter(lignes)
    pages, numero = [], None
    for ligne in lignes[debut:]:
        nu = ligne.strip()
        if RE_ENTETE.match(nu) and nu.lstrip("#").strip().startswith("Pages à vérifier"):
            break      # la section de controle de C2 n'est pas du texte de cours, ou qu'elle soit : elle ferme le texte
        trouve = RE_PAGE.match(nu)
        if trouve:
            numero = int(trouve.group(1))
            pages.append((numero, []))
            continue
        if nu.startswith("<!--") and nu.endswith("-->"):
            continue   # commentaire HTML : jamais du texte de cours
        if numero is None:
            if not nu or RE_ENTETE.match(nu) or nu.startswith(">"):
                continue   # entete de C2 (titre, `> Source`, resume), avant la premiere page
            numero = 1
            pages.append((numero, []))
        pages[-1][1].append(ligne)
    if pages and not any(l.strip() for l in pages[-1][1]) and len(pages) > 1:
        pages.pop()   # marqueur de page en fin de fichier : il ne cree pas une page vide
    return [(n, "\n".join(corps).strip()) for n, corps in pages]


def _normaliser_md(texte):
    """Texte de page pret a etre colle dans une IA : liens reduits a leur libelle, entetes et puces sans marque
    Markdown, emphase retiree, lignes repliees en un paragraphe. Le contenu des mots n'est pas modifie."""
    texte = RE_LIEN.sub(lambda m: m.group(1), texte.replace("\\|", "|"))
    paragraphes, courant = [], []
    for ligne in texte.split("\n"):
        nu = ligne.strip()
        if not nu:
            if courant:
                paragraphes.append(" ".join(courant))
                courant = []
            continue
        if RE_FERMETURE.match(ligne):
            if courant:
                paragraphes.append(" ".join(courant))
                courant = []
            paragraphes.append(nu)
            continue
        nu = RE_ENTETE.sub("", nu)
        nu = RE_PUCE.sub("", nu)
        souligne = RE_SOULIGNE.match(nu)
        if souligne:
            nu = souligne.group(2)
        courant.append(nu)
    if courant:
        paragraphes.append(" ".join(courant))
    return "\n\n".join(paragraphes)


def _documents(dest):
    """Documents connus du cache, tries par cours, section et nom (ms.cle_nom), avec leur entree et leur .md.

    Chaque element : {"chemin", "cours", "section", "nom", "entree", "md"} ; `md` vaut None si le .md manque.
    Le cache est la reference (invariant 10) ; C5 ne lit jamais index_existant (invariant 15).
    """
    documents = charger_cache(dest)["documents"]
    resultat = []
    for cle, entree in documents.items():
        chemin = _cle(cle)
        parties = chemin.split("/") if chemin else []
        sortie = entree.get("sortie")
        md = _resoudre_sortie(dest, sortie) if isinstance(sortie, str) and sortie else None
        if md is not None and not os.path.isfile(md):
            md = None
        resultat.append({"chemin": chemin, "cours": parties[0] if len(parties) > 1 else "",
                         "section": parties[1] if len(parties) > 2 else "",
                         "nom": parties[-1] if parties else "", "entree": entree, "md": md})
    resultat.sort(key=lambda d: (ms.cle_nom(d["cours"]), ms.cle_nom(d["section"]), ms.cle_nom(d["nom"]), d["chemin"]))
    return resultat


def _portee(portee):
    """(sorte, valeur) d'une portee de 2.5 : tout, sans_texte, cours:<cid>, document:<chemin>."""
    texte = portee if isinstance(portee, str) else ""
    sorte, _, valeur = texte.partition(":")
    if sorte == "cours" and valeur.strip():
        return "cours", valeur.strip()
    if sorte == "document" and valeur.strip():
        return "document", _cle(valeur)
    return "tout", ""


def _dans_la_portee(document, portee):
    """Vrai si le document entre dans la portee. `cours:<cid>` designe le dossier du cours (meme lecture que
    constituer_file : le dossier, pas l'identifiant), sans distinction de casse ni d'accents (ms.cle_nom)."""
    sorte, valeur = _portee(portee)
    if sorte == "cours":
        return ms.cle_nom(document["cours"]) == ms.cle_nom(valeur)
    if sorte == "document":
        return _comparable(document["chemin"]) == _comparable(valeur)
    return True   # tout et sans_texte : C5 ne lit que des documents deja extraits, la portee ne filtre rien


def _lire_md(document):
    """Pages [(numero, texte)] d'un .md de document, ou None si le fichier manque ou n'est pas de l'UTF-8.
    Un .md absent ou illisible sort de l'agregat : rien n'est invente (invariant 8)."""
    if not document["md"]:
        return None
    try:
        with open(document["md"], "rb") as f:
            texte = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        _signaler(e)
        return None
    return _pages_md(texte)


def _volume(octets_):
    """Volume lisible, a la francaise, en Mo a une decimale (plan 6.3 : « 1,2 Mo »)."""
    return f"{octets_ / (1024 * 1024):.1f}".replace(".", ",") + " Mo"


def _pluriel(nombre, mot, pluriel=None):
    """« 1 page », « 3 pages » ; un mot compose prend son pluriel sur le nom (pluriel donne a part)."""
    return f"{nombre} {mot if nombre <= 1 else (pluriel or mot + 's')}"


def _pages_douteuses(entree):
    """Nombre de pages que le document n'a pas en « bon » (2.3 : etat derive de la pire page)."""
    try:
        return max(0, int(entree.get("pages", 0)) - int(entree.get("pages_texte", 0)))
    except (TypeError, ValueError):
        return 0


def _ecrire_texte(chemin, contenu):
    """Ecriture atomique (.tmp puis os.replace), UTF-8 sans BOM, fins de ligne LF. Une erreur d'ecriture leve
    OSError, le fichier precedent reste intact et aucun .tmp ne subsiste."""
    os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
    temporaire = chemin + ".tmp"
    try:
        with open(temporaire, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenu)
        os.replace(temporaire, chemin)
    except BaseException:
        try:
            os.remove(temporaire)
        except OSError:
            pass
        raise


def _dossier_textes(dest, cfg=None):
    """Dossier des agregats (index, qualite) : celui des .md de documents, deduit du cache. Sans cache ni
    document, `ocr_dossier` (ou « Textes ») a la racine de dest."""
    for entree in charger_cache(dest)["documents"].values():
        sortie = entree.get("sortie")
        if isinstance(sortie, str) and sortie and not os.path.isabs(sortie):
            return os.path.join(dest, sortie.split("/")[0])
    return os.path.join(dest, _nom_dossier_sortie(cfg or {}))


# ------------------------------------------------------------------ agregat d'un cours (plan 6.2)
def _bloc_cours(cours, documents):
    """Bloc Markdown d'un cours (plan 6.2), sans la marque ni le titre : sections, documents, pages."""
    lignes = [PHRASE_COURS, ""]
    section = None
    for document in documents:
        if document["section"] != section:
            section = document["section"]
            if section:
                lignes += [f"## {section}", ""]
        pages = _lire_md(document)
        if pages is None:
            continue   # .md absent ou illisible : le document sort de l'agregat, il n'est pas invente
        lignes += [f"### {document['nom']}", ""]
        parties = [p for p in (document["section"], document["nom"]) if p]
        lignes += [f"[source : {'/'.join(parties)}, {_pluriel(len(pages), 'page')}]", ""]
        for numero, texte in pages:
            lignes += [f"[p. {numero}]", ""]
            if texte:
                lignes += [texte, ""]
    return lignes


def _grouper(documents):
    """{cours: [documents]}, l'ordre des documents etant celui de _documents."""
    groupes = {}
    for document in documents:
        groupes.setdefault(document["cours"], []).append(document)
    return groupes


@_sans_trace("")
def assembler_contexte(dest, portee):
    """Texte pret a coller dans une IA (plan 6.2), pour les documents deja extraits de la portee (2.5).

    Marqueurs `[p. n]` visibles, phrase d'introduction du plan 6.2, ordre cours, section, nom. Aucune ecriture
    disque (T24 et T27) : la marque ms.MARQUE n'y figure pas, elle ne sert qu'aux fichiers ecrits. Le compte de
    caracteres de la forme 2.7 est calcule par l'appelant (A2) sur le texte renvoye.
    """
    blocs = []
    for cours, documents in _grouper([d for d in _documents(dest) if _dans_la_portee(d, portee)]).items():
        if not cours:
            continue   # un document a la racine de dest n'a pas de cours : il n'entre pas dans un agregat par cours
        lignes = _bloc_cours(cours, documents)
        if len(lignes) <= 2:
            continue   # aucun .md lisible pour ce cours
        blocs.append("\n".join([f"# {cours} : {TITRE_COURS}", ""] + lignes).rstrip("\n"))
    return "\n\n".join(blocs) + ("\n" if blocs else "")


@_sans_trace(list)
def ecrire_cours_md(dest, portee):
    """Ecrit `Textes/<Cours>/<Cours> - texte complet.md` (plan 6.2, contrat 2.6) pour chaque cours de la portee.

    ms.MARQUE en premiere ligne (D4), puis le titre et le bloc du cours. Ecriture atomique, UTF-8 sans BOM, LF,
    aucun chemin absolu. Un cours sans .md lisible n'a pas de fichier. Renvoie la liste des chemins ecrits.
    """
    ecrits = []
    for cours, documents in _grouper([d for d in _documents(dest) if _dans_la_portee(d, portee)]).items():
        if not cours:
            continue
        lignes = _bloc_cours(cours, documents)
        if len(lignes) <= 2:
            continue
        contenu = "\n".join([ms.MARQUE, "", f"# {cours} : {TITRE_COURS}", ""] + lignes).rstrip("\n") + "\n"
        chemin = os.path.join(_dossier_textes(dest), cours, f"{cours} - {TITRE_COURS}.md")
        _ecrire_texte(chemin, contenu)
        ecrits.append(chemin)
    return ecrits


# ------------------------------------------------------------------ orphelins (invariant 11)
def _orphelins(dest, cache):
    """Sorties sans document correspondant (invariant 11) : liste, jamais supprimees.

    Deux cas : une entree du cache dont le document a disparu du disque (son .md reste, et reste dans le cache
    pour garder `verifie`), et un .md de document present sous le dossier de sortie sans entree de cache.
    Chaque element : {"chemin", "sortie", "cours", "section", "nom"} ; `chemin` est le document attendu.
    """
    documents = (cache or {}).get("documents") or {}
    dossier = _dossier_textes(dest)
    connues, resultat = set(), []
    for cle, entree in documents.items():
        chemin = _cle(cle)
        sortie = entree.get("sortie")
        if not chemin or not isinstance(sortie, str) or not sortie or os.path.isabs(sortie):
            continue
        connues.add(_comparable(_resoudre_sortie(dest, sortie)))
        if not os.path.isfile(_absolu(dest, chemin)):
            parties = chemin.split("/")
            resultat.append({"chemin": chemin, "sortie": sortie,
                             "cours": parties[0] if len(parties) > 1 else "",
                             "section": parties[1] if len(parties) > 2 else "",
                             "nom": parties[-1]})
    if os.path.isdir(dossier):
        for racine, dossiers, fichiers in os.walk(dossier):
            dossiers.sort()
            for nom in sorted(fichiers):
                if not nom.endswith(".md"):
                    continue
                chemin = os.path.join(racine, nom)
                if _comparable(chemin) in connues:
                    continue
                relatif = os.path.relpath(chemin, dossier).replace(os.sep, "/")
                if relatif.count("/") < 2:
                    continue   # index, qualite et fichier de cours : pas des .md de document
                parties = relatif.split("/")
                resultat.append({"chemin": "/".join(parties[:-1] + [parties[-1][:-3]]),
                                 "sortie": "/".join([os.path.basename(dossier)] + parties),
                                 "cours": parties[0], "section": parties[1] if len(parties) > 2 else "",
                                 "nom": parties[-1][:-3]})
    resultat.sort(key=lambda o: (ms.cle_nom(o["cours"]), ms.cle_nom(o["section"]), ms.cle_nom(o["nom"]), o["sortie"]))
    return resultat


def _a_verifier(documents, cache):
    """Documents dont `etat` n'est pas `ok` et qui ne sont pas marques `verifie` (plan 6.3, 2.3)."""
    return [d for d in documents
            if d["entree"].get("etat") != "ok" and not d["entree"].get("verifie")]


def _ligne_a_verifier(document):
    """« Cours A / Section 2 / photocopie.pdf : confiance 0,64, 3 pages douteuses » (plan 6.3)."""
    entree = document["entree"]
    morceaux = []
    confiance = entree.get("confiance")
    if isinstance(confiance, (int, float)) and not isinstance(confiance, bool):
        morceaux.append(f"confiance {_virgule(confiance)}")
    douteuses = _pages_douteuses(entree)
    if douteuses:
        morceaux.append(_pluriel(douteuses, "page douteuse", "pages douteuses"))
    if entree.get("extraction") == "vide":
        morceaux.append("aucun texte détecté")
    titre = " / ".join(p for p in (document["cours"], document["section"], document["nom"]) if p)
    return f"{titre} : {', '.join(morceaux)}" if morceaux else titre


# ------------------------------------------------------------------ index (plan 6.3)
@_sans_trace("")
def ecrire_index(dest):
    """Ecrit `Textes/index.md` (plan 6.3) : ms.MARQUE, titre, une ligne par cours, puis les documents a verifier.

    Compteurs par cours : documents, pages et volume des .md du cours (fichiers de document et fichier de cours
    compris), mesure sur le disque. Les documents a verifier sont ceux dont l'etat du cache n'est pas `ok` et qui
    ne sont pas marques `verifie`. Les orphelins sont listes a part, jamais supprimes. Renvoie le chemin ecrit,
    ou une chaine vide si l'ecriture a echoue (invariant 9 : le detail va dans erreurs.txt).
    """
    cache = charger_cache(dest)
    documents = _documents(dest)
    lignes = [ms.MARQUE, "", f"# {TITRE_INDEX}", ""]
    for cours, groupe in _grouper(documents).items():
        if not cours:
            continue
        pages = sum(int(d["entree"].get("pages") or 0) for d in groupe)
        poids = 0
        for racine, dossiers, fichiers in os.walk(os.path.join(_dossier_textes(dest), cours)):
            for nom in fichiers:
                if nom.endswith(".md"):
                    try:
                        poids += os.path.getsize(os.path.join(racine, nom))
                    except OSError as e:
                        _signaler(e)
        lignes.append(f"- {cours} : {_pluriel(len(groupe), 'document')}, {_pluriel(pages, 'page')}, {_volume(poids)}")
    lignes += ["", "## Documents à vérifier", ""]
    fautifs = [_ligne_a_verifier(d) for d in _a_verifier(documents, cache)]
    lignes += [f"- {ligne}" for ligne in fautifs]
    if not fautifs:
        lignes.append("Aucun document à vérifier.")
    orphelins = _orphelins(dest, cache)
    if orphelins:
        lignes += ["", "## Documents orphelins", "",
                   "Ces documents ont été déplacés ou supprimés : leur texte est conservé, rien n'est effacé sans ton accord.",
                   ""]
        lignes += [f"- {o['chemin']} : texte conservé ({o['sortie']})" for o in orphelins]
    chemin = os.path.join(_dossier_textes(dest), "index.md")
    _ecrire_texte(chemin, "\n".join(lignes).rstrip("\n") + "\n")
    return chemin


# ------------------------------------------------------------------ qualite (plan 4.4)
def _section_document(document, pages):
    """Bloc d'un document dans `Qualité des textes.md` : entete, lien relatif au .md, puis les pages a revoir.

    Le lien part du dossier du fichier de qualite (la racine de Textes) : `Cours A/Section 1/b.pdf.md`. La
    confiance d'une page est celle du document : C2 ne stocke pas de confiance par page dans le .md, et C5 ne
    reconnait rien (la valeur est donc la meme pour toutes les pages d'un document, ecrit au journal).
    """
    entree = document["entree"]
    confiance = entree.get("confiance")
    confiance = confiance if isinstance(confiance, (int, float)) and not isinstance(confiance, bool) else None
    titre = " / ".join(p for p in (document["cours"], document["section"], document["nom"]) if p)
    lien = "/".join([p for p in (document["cours"], document["section"]) if p] + [document["nom"] + ".md"])
    lignes = [f"## {titre}", ""]
    details = []
    if confiance is not None:
        details.append(f"confiance {_virgule(confiance)}")
    details.append(_pluriel(int(entree.get("pages") or 0), "page"))
    if entree.get("extraction"):
        details.append(f"extraction {entree['extraction']}")
    lignes += [f"[Ouvrir le texte]({lien})", "", ", ".join(details) + ".", ""]
    if entree.get("verifie"):
        lignes += ["Marqué comme vérifié.", ""]
    douteuses = []
    for numero, texte in pages:
        if not texte:
            douteuses.append(f"- page {numero} : aucun texte détecté")
            continue
        if entree.get("extraction") != "ocr" or confiance is None:
            continue   # page native, ou document sans confiance : rien a verifier
        douteuses.append(f"- page {numero} : confiance {_virgule(confiance)}")
    if douteuses:
        lignes += douteuses + [""]
    return lignes


@_sans_trace("")
def ecrire_qualite(dest):
    """Ecrit `Textes/Qualité des textes.md` (plan 4.4) : ms.MARQUE, liste des documents a verifier, page par page.

    Confiance a la francaise (_virgule), lien relatif vers le .md du document. Une page difficile n'est jamais
    omise. Les documents marques `verifie` sont exclus. Renvoie le chemin ecrit, ou une chaine vide si l'ecriture
    a echoue (invariant 9 : le detail va dans erreurs.txt).
    """
    cache = charger_cache(dest)
    documents = _documents(dest)
    fautifs = _a_verifier(documents, cache)
    lignes = [ms.MARQUE, "", f"# {TITRE_QUALITE}", ""]
    if not fautifs:
        lignes += ["Aucun document à vérifier : la reconnaissance est sûre partout.", ""]
    else:
        lignes += [f"{_pluriel(len(fautifs), 'document')} à vérifier : la reconnaissance y est moins sûre. "
                   "Compare avec le document source.", ""]
        for document in fautifs:
            pages = _lire_md(document)
            lignes += _section_document(document, pages or [])
    orphelins = _orphelins(dest, cache)
    if orphelins:
        lignes += ["## Textes orphelins", "",
                   "Ces documents ont été déplacés ou supprimés : leur texte est conservé.", ""]
        lignes += [f"- {o['chemin']} : texte conservé ({o['sortie']})" for o in orphelins]
    chemin = os.path.join(_dossier_textes(dest), f"{TITRE_QUALITE}.md")
    _ecrire_texte(chemin, "\n".join(lignes).rstrip("\n") + "\n")
    return chemin


# ------------------------------------------------------------------ JSONL a la demande (plan 6.4)
@_sans_trace(0)
def ecrire_jsonl(dest, portee, flux):
    """Ecrit une ligne JSON par page dans `flux` (plan 6.4) et renvoie le nombre de lignes ecrites.

    Cles : `cours`, `section`, `fichier`, `page`, `source`, `confiance`, `texte`. UTF-8 sans BOM, une seule ligne
    par page (les fins de ligne du texte sont remplacees par des espaces). Cree seulement a la demande : aucun
    fichier n'est ecrit sur le disque, le flux est fourni par l'appelant (texte ou binaire). Renvoie le nombre de
    lignes ecrites, ou 0 si l'ecriture a echoue (invariant 9 : le detail va dans erreurs.txt).
    """
    nombre = 0
    for document in _documents(dest):
        if not _dans_la_portee(document, portee):
            continue
        pages = _lire_md(document)
        if pages is None:
            continue
        entree = document["entree"]
        confiance = entree.get("confiance")
        confiance = float(confiance) if isinstance(confiance, (int, float)) and not isinstance(confiance, bool) else None
        for numero, texte in pages:
            ligne = json.dumps({"cours": document["cours"], "section": document["section"],
                                "fichier": document["nom"], "page": numero,
                                "source": entree.get("extraction") or "", "confiance": confiance,
                                "texte": " ".join(texte.split())}, ensure_ascii=False) + "\n"
            try:
                flux.write(ligne)
            except TypeError:
                flux.write(ligne.encode("utf-8"))   # flux binaire ouvert par l'appelant
            nombre += 1
    return nombre
