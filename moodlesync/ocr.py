#!/usr/bin/env python3
"""MoodleSync, extraction du texte des scans : detection du moteur Tesseract et extraction d'une page.

Tache C1 : detection du moteur (Tesseract 4 ou 5) et reglages d'appel.
Tache C2 : une page (texte natif, rendu, reconnaissance, TSV, qualite) et le Markdown d'un document.
Le cache, la file, la superposition et les sorties de cours viennent avec les taches suivantes et
n'existent pas encore.

Le moteur n'est pas forcement dans le PATH : la detection essaie, dans l'ordre du plan 5.2, le
chemin de la configuration (ocr_exe), shutil.which, le registre Windows, les chemins usuels, puis
macOS. Le paquet portable (etape 6 du plan) est sans objet en 2.5. Aucun appel reseau
(invariant 6). detecter ne leve jamais et n'ecrit aucune trace technique. pypdf, Pillow et
pypdfium2 sont importes a l'usage seulement (D11) : sans eux, la detection reste utilisable.
"""
import copy, json, logging, os, re, shutil, subprocess, sys, tempfile, threading, time, unicodedata

from . import moteur as ms

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
}


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
    moteur = detecter(cfg)
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


def _est_pdf(chemin):
    return os.path.splitext(chemin)[1].lower() == ".pdf"


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
def _preparer(image):
    """Niveaux de gris et autocontraste (plan 5.3). Une transparence est composee sur fond blanc."""
    from PIL import Image, ImageOps
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        fond = Image.new("RGBA", rgba.size, "white")
        image = Image.alpha_composite(fond, rgba)
    return ImageOps.autocontrast(image.convert("L"))


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


def rendre_page(chemin, numero, dpi):
    """Image Pillow en niveaux de gris de la page `numero` (base 1) d'un PDF au `dpi` donne, ou du
    cadre `numero` d'une image. Point d'entree remplacable par les tests. Leve ErreurOcr « illisible »."""
    try:
        if numero < 1:
            raise ValueError("numero de page invalide")
        image = _rendre_pdf(chemin, numero, dpi) if _est_pdf(chemin) else _ouvrir_image(chemin, numero)
        return _preparer(image)
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
            "extraction": "texte" if not reconnues else ("ocr" if not natives else "mixte"),
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
    for ligne in lignes[1:]:
        if ligne.strip() == "---":
            return False
        if ligne.startswith("moodlesync:"):
            return True
    return False


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
