#!/usr/bin/env python3
"""MoodleSync - recupere les fichiers de cours Moodle et les range par cours et section.

Utilisation : double-cliquer sur MoodleSync.exe ou MoodleSync.app (ou lancer ce script avec python).
Les reglages sont enregistres dans %LOCALAPPDATA%\\MoodleSync\\config.json sous Windows,
~/Library/Application Support/MoodleSync/config.json sous macOS.

Principe :
  1. on indique l'adresse de son Moodle, puis on se connecte une fois dans Chrome (ou Edge sous Windows)
     (SWITCH edu-ID, identifiant local ou autre : c'est la methode de l'etablissement),
  2. on choisit le dossier de rangement et les cours,
  3. le programme telecharge les fichiers nouveaux et les range tout seul.

Rangement produit : <dossier>\\<Cours>\\<Section>\\[<Sous-dossier>\\][<Statut>\\]fichier.ext
La couche de statut (Obligatoire / Complementaire / Supports de cours, ou Required /
Supplementary / Course material en anglais) est optionnelle.
"""
import os, re, sys, json, time, base64, hashlib, queue, threading, subprocess, unicodedata, collections
import urllib.parse, urllib.request, urllib.error

# Dans un .exe sans console, stdout et stderr valent None : certaines bibliotheques
# (Selenium notamment) ecrivent dedans et planteraient.
if getattr(sys, "frozen", False):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

BASE = ""                           # adresse du Moodle, reglee depuis config.json (regler_site)
SITE_UNIL = "https://moodle.unil.ch"  # valeur reprise pour les anciennes configurations
MAC = sys.platform == "darwin"
if MAC:
    APP_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "MoodleSync")
    # Agent de lancement de l'utilisateur : equivalent du dossier Demarrage, sans droit admin.
    DEMARRAGE = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", "ch.moodlesync.plist")
else:
    APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "MoodleSync")
    DEMARRAGE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                             "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "MoodleSync.lnk")
CONFIG = os.path.join(APP_DIR, "config.json")
PROFIL_CHROME = os.path.join(APP_DIR, "profil_chrome")
PROFIL_EDGE = os.path.join(APP_DIR, "profil_edge")
JOURNAL = os.path.join(APP_DIR, "journal.txt")
EXPLORATEUR = "le Finder" if MAC else "l'explorateur Windows"
# Sous Windows, Edge (toujours installe) prend le relais si Chrome manque. Sur Mac, Chrome seulement.
NAVIGATEURS = "Chrome" if MAC else "Chrome (ou Edge)"
if MAC and not os.environ.get("SSL_CERT_FILE"):
    # Le Python de python.org (et donc le .app) ignore le trousseau de macOS : sans ce fichier
    # de certificats, toute connexion HTTPS echoue (CERTIFICATE_VERIFY_FAILED).
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        pass
ETAT = ".moodlesync.json"           # dans le dossier de rangement, cache pour Obsidian
MARQUE = "<!-- MoodleSync : fichier régénéré à chaque synchronisation. Supprime cette ligne pour le garder tel quel. -->"


# Langue des noms de dossiers, des fichiers de notes et de la reconnaissance des etiquettes Moodle.
# L'interface elle-meme reste en francais.
LANGUES = {
    "fr": {
        "nom": "Français",
        "O": "Obligatoire", "C": "Complémentaire", "P": "Pour aller plus loin", "S": "Supports de cours",
        # Intitules de liste de lectures (voir statut_titre) : un mot isole ne compte qu'en fin d'intitule.
        "re_c": r"(lectures?|textes?|manuels?|documents?|ressources?)\s+(compl[ée]mentaires?|facultati(f|ve)s?"
                r"|optionnel(le)?s?|recommand[ée]e?s?|sugg[ée]r[ée]e?s?)"
                r"|(compl[ée]mentaires?|facultati(f|ve)s?)(?=\W*$)",
        "re_p": r"(pour )?aller plus loin",
        "re_o": r"(lectures?|textes?)\s+obligatoires?|obligatoires?(?=\W*$)",
        "re_s": r"diapos|slides?|supports? de cours|consignes|syllabus|calendrier|modalit[ée]s",
        # Deduction sans etiquette : uniquement ce qui designe nettement un document de l'enseignant.
        "re_sup": r"diapo|slides?|powerpoint|syllabus|consignes?|fiche|calendrier"
                  r"|plan du (cours|s[ée]minaire)|pr[ée]sentation|modalit[ée]s|qcm",
        "re_sup_non": r"syllabus de lectures?",
        "note": "Nouveautés Moodle.md", "titre_note": "Nouveautés Moodle",
        "liens": "Liens Moodle.md", "titre_liens": "Liens : ",
        "date_note": "%d.%m.%Y à %H:%M",
        "general": "Général", "sans_titre": "Sans titre", "cours": "Cours", "seminaire": "Séminaire",
        "ancienne": "ancienne version", "date_inconnue": "date inconnue",
        "maj": "mis à jour", "conservee": "ancienne version conservée",
        "nouveau_lien": "nouveau lien", "video": "Vidéo", "sep": " : ",
    },
    "en": {
        "nom": "English",
        "O": "Required", "C": "Supplementary", "P": "Further reading", "S": "Course material",
        "re_c": r"(supplementary|additional|optional|recommended|suggested)\s+(readings?|texts?|materials?)"
                r"|(supplementary|optional|recommended)(?=\W*$)",
        "re_p": r"further readings?|go(ing)? further",
        "re_o": r"(required|mandatory|compulsory|essential|core)\s+(readings?|texts?|materials?)"
                r"|(required|mandatory|compulsory)(?=\W*$)",
        "re_s": r"slides?|lecture (notes|material|materials)|course (material|materials|information|outline)"
                r"|syllabus|schedule|calendar|instructions|handouts?|assessment|guidelines",
        "re_sup": r"slides?|powerpoint|syllabus|instructions|handouts?|schedule|calendar"
                  r"|course (outline|plan|information)|presentation|worksheet|quiz",
        "re_sup_non": r"(reading|readings) (list|syllabus)|syllabus of readings",
        "note": "Moodle updates.md", "titre_note": "Moodle updates",
        "liens": "Moodle links.md", "titre_liens": "Links: ",
        "date_note": "%Y-%m-%d %H:%M",
        "general": "General", "sans_titre": "Untitled", "cours": "Lecture", "seminaire": "Seminar",
        "ancienne": "old version", "date_inconnue": "unknown date",
        "maj": "updated", "conservee": "old version kept",
        "nouveau_lien": "new link", "video": "Video", "sep": ": ",
    },
}
T = LANGUES["fr"]       # langue courante, reglee par regler_langue
ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVES = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
nfc = lambda s: unicodedata.normalize("NFC", s)


class Erreur(Exception):
    """Erreur lisible directement par l'utilisateur."""


class SessionExpiree(Erreur):
    """Le jeton n'est plus accepte : seule erreur qui justifie de l'effacer."""


class Annule(Exception):
    """Synchronisation interrompue a la demande de l'utilisateur."""


class ServiceMobileDesactive(Erreur):
    """Le Moodle refuse l'acces par l'application mobile : MoodleSync ne peut pas y fonctionner."""


MSG_SERVICE_DESACTIVE = (
    "Ce Moodle n'autorise pas l'accès par l'application mobile, dont MoodleSync dépend pour "
    "obtenir un jeton de connexion.\n\n"
    "Malheureusement, MoodleSync ne peut pas fonctionner avec cet établissement. Ce n'est un "
    "problème ni de ton compte ni de ton mot de passe : l'établissement a désactivé ce service, "
    "et seul son administrateur Moodle peut le réactiver (réglage « Moodle mobile web service »).")


# ------------------------------------------------------------------ reglages
def charger_config():
    c = {}
    try:
        with open(CONFIG, encoding="utf-8-sig") as f:
            c = json.load(f)
    except Exception:
        pass
    c.setdefault("token", "")
    if not c.get("site") and (c["token"] or c.get("cours")):
        c["site"] = SITE_UNIL           # anciennes versions : le programme ne connaissait que l'UNIL
    c.setdefault("site", "")
    c.setdefault("langue", "fr")
    c.setdefault("dest", os.path.join(os.path.expanduser("~"), "Documents", "Moodle"))
    c.setdefault("cours", {})
    c.setdefault("statuts", False)
    c.setdefault("note", True)
    return c


def appliquer_config(c):
    """Regle l'adresse du Moodle et la langue d'apres la configuration."""
    global BASE, T
    BASE = c.get("site") or ""
    T = LANGUES.get(c.get("langue"), LANGUES["fr"])


def sauver_config(c):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------- API
def api(token, fonction, **params):
    q = {"wstoken": token, "wsfunction": fonction, "moodlewsrestformat": "json"}
    q.update({k: v for k, v in params.items() if v is not None})
    url = BASE + "/webservice/rest/server.php?" + urllib.parse.urlencode(q, doseq=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8"))
    except OSError as e:
        # URLError, mais aussi un delai depasse pendant la lecture de la reponse (TimeoutError).
        raise Erreur(f"Moodle est injoignable ({getattr(e, 'reason', None) or e}). "
                     "Verifie ta connexion internet.")
    if isinstance(d, dict) and d.get("exception"):
        code = d.get("errorcode") or ""
        if code in ("invalidtoken", "accessexception"):
            raise SessionExpiree("La session a expire. Reconnecte-toi.")
        raise Erreur(d.get("message") or code or "Erreur Moodle inconnue.")
    return d


def infos_session(token):
    return api(token, "core_webservice_get_site_info")


def cours_inscrits(token, userid):
    return api(token, "core_enrol_get_users_courses", userid=userid)


# ---------------------------------------------------------------- adresse du site
def normaliser_site(texte):
    """Adresse racine d'un Moodle, deduite de ce que l'utilisateur a colle (https, sans /my ni /login)."""
    t = (texte or "").strip()
    if not t:
        raise Erreur("Indique l'adresse de ton Moodle, par exemple https://moodle.exemple.ch")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", t, re.I):
        t = "https://" + t
    u = urllib.parse.urlparse(t)
    if u.scheme.lower() not in ("http", "https") or not u.netloc or " " in u.netloc or "." not in u.netloc:
        raise Erreur("Cette adresse n'est pas valide. Colle l'adresse de la page d'accueil de ton Moodle, "
                     "par exemple https://moodle.exemple.ch")
    chemin = u.path
    m = re.search(r"/(my|login|course|user|mod|admin|index\.php|lib|pluginfile\.php|webservice|auth"
                  r"|enrol|calendar|grade|message|blocks|theme)(/|$)", chemin)
    if m:
        chemin = chemin[:m.start()]
    return "https://" + u.netloc.lower() + chemin.rstrip("/")     # http est refuse : le jeton circulerait en clair


def lire_page(url):
    """Corps d'une page (meme en cas d'erreur HTTP), ou Erreur si le serveur est injoignable."""
    req = urllib.request.Request(url, headers={"User-Agent": "MoodleSync/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read(200000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.read(200000).decode("utf-8", "replace")
        except Exception:
            return ""
    except urllib.error.URLError as e:
        raise Erreur(f"Impossible de joindre {url.split('/')[2]} ({e.reason}). "
                     "Vérifie l'adresse et ta connexion internet.")
    except Exception as e:
        raise Erreur(f"Impossible de joindre ce site : {str(e)[:120]}")


def verifier_site(base):
    """Controle que l'adresse est celle d'un Moodle dont les services web sont ouverts.

    Sans jeton, le point d'entree des services web d'un Moodle repond en JSON avec un code
    d'erreur : invalidtoken si les services sont actifs, accessexception s'ils sont desactives.
    """
    corps = lire_page(base + "/webservice/rest/server.php?moodlewsrestformat=json")
    try:
        d = json.loads(corps)
    except ValueError:
        d = None
    if isinstance(d, dict) and d.get("errorcode"):
        if d["errorcode"] == "accessexception":
            raise ServiceMobileDesactive(MSG_SERVICE_DESACTIVE)
        return
    # Pas de reponse JSON : un Moodle derriere un filtre, ou autre chose. On regarde la page de connexion.
    if re.search(r"moodle|M\.cfg", lire_page(base + "/login/index.php"), re.I):
        return
    raise Erreur("Cette adresse ne semble pas être celle d'un Moodle. Vérifie-la : c'est l'adresse "
                 "de la page d'accueil de ton Moodle, par exemple https://moodle.exemple.ch")


# ---------------------------------------------------------------- connexion
def cookies_vers_entete(cookies):
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


class SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def jeton_depuis_session(cookies):
    """Echange une session Moodle valide contre un jeton de service web durable."""
    url = (f"{BASE}/admin/tool/mobile/launch.php?service=moodle_mobile_app"
           f"&passport=1.0&urlscheme=moodlemobile")
    req = urllib.request.Request(url, headers={"Cookie": cookies_vers_entete(cookies),
                                               "User-Agent": "Mozilla/5.0"})
    op = urllib.request.build_opener(SansRedirection)
    loc = ""
    try:
        loc = op.open(req, timeout=60).headers.get("Location") or ""
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location") or ""
    except Exception:
        return None
    if "token=" not in loc:
        return None
    brut = loc.split("token=", 1)[1]
    brut += "=" * (-len(brut) % 4)
    try:
        clair = base64.b64decode(brut).decode("utf-8", "replace")
    except Exception:
        return None
    parts = clair.split(":::")
    return parts[1] if len(parts) >= 2 else None


# Etat de la page vue par le navigateur : 2 = connecte (menu utilisateur de Moodle present),
# 1 = probablement connecte (page du site, ni connexion ni invite), 0 = pas connecte.
JS_ETAT = r"""
if (!document.body || document.readyState !== 'complete') return 0;
if (!location.href.startsWith(arguments[0])) return 0;
if (document.body.classList.contains('notloggedin')) return 0;
if (document.querySelector('#user-menu-toggle, .usermenu, a[href*="/user/profile.php"]')) return 2;
return /\/(login|auth)\//.test(location.pathname) ? 0 : 1;
"""


def ouvrir_navigateur(dire=print):
    """Lance Chrome, ou Edge sous Windows si Chrome manque, avec un profil propre a MoodleSync.

    Le navigateur est pilote (Selenium) parce que c'est le seul moyen de voir la connexion aboutir
    et de lire le cookie de session, protege contre tout autre programme.
    Renvoie (nom du navigateur, pilote).
    """
    try:
        from selenium import webdriver
    except ImportError:
        raise Erreur("Le module Selenium manque sur cet ordinateur.")
    essais = [("Chrome", webdriver.Chrome, webdriver.ChromeOptions, PROFIL_CHROME)]
    if not MAC:
        essais.append(("Edge", webdriver.Edge, webdriver.EdgeOptions, PROFIL_EDGE))
    echecs = []
    for nom, pilote, options, profil in essais:
        o = options()
        o.add_argument(f"--user-data-dir={profil}")
        o.add_argument("--no-first-run")
        o.add_argument("--no-default-browser-check")
        o.add_argument("--start-maximized")
        dire(f"Ouverture de {nom} sur Moodle...")
        try:
            return nom, pilote(options=o)
        except Exception as e:
            echecs.append(f"{nom} : {str(e).strip().splitlines()[0][:150] if str(e).strip() else type(e).__name__}")
            if len(essais) > 1 and nom == "Chrome":
                dire("Chrome n'a pas pu être lancé, essai avec Edge...")
    if MAC:
        raise Erreur("Chrome n'a pas pu etre lance. Verifie qu'il est installe.\n" + "\n".join(echecs))
    raise Erreur("Ni Chrome ni Edge n'ont pu etre lances. Installe Google Chrome, ou mets Edge a jour.\n"
                 + "\n".join(echecs))


def connexion_navigateur(dire=print):
    """Ouvre le navigateur, attend la connexion, renvoie (jeton, certain).

    `certain` vaut False quand la page n'a jamais montre le menu utilisateur de Moodle (theme
    inconnu) : la connexion est alors deduite de l'adresse de la page, et seul le jeton fait foi.
    """
    nom, nav = ouvrir_navigateur(dire)
    jeton, certain = None, True
    try:
        nav.get(BASE + "/my/")
        debut, faible, echecs = time.time(), 0, 0
        while time.time() - debut < 600:
            try:
                etat = nav.execute_script(JS_ETAT, BASE + "/")
            except Exception:
                etat = 0
            faible = faible + 1 if etat == 1 else 0      # il faut une page stable, pas un passage
            if etat == 2 or faible >= 3:
                dire("Connexion detectee, recuperation du jeton..." if etat == 2 else
                     "Connexion probable (theme Moodle non reconnu), essai du jeton...")
                cookies = {c["name"]: c["value"] for c in nav.get_cookies()}
                jeton = jeton_depuis_session(cookies)
                if jeton:
                    certain = etat == 2
                    break
                if etat == 2 or echecs >= 2:
                    raise ServiceMobileDesactive(MSG_SERVICE_DESACTIVE)
                echecs, faible = echecs + 1, 0           # peut-etre pas encore connecte : on attend
            time.sleep(2)
    finally:
        try:
            nav.quit()
        except Exception:
            pass
    if not jeton:
        raise Erreur(f"Connexion non terminee. Relance et connecte-toi dans la fenetre {nom}.")
    return jeton, certain


# ------------------------------------------------------------ noms et dossiers
def nettoie(nom, limite=240):
    """Nom de fichier ou de dossier sur : caracteres interdits, longueur, points finaux."""
    nom = nfc(nom or "").replace("\u00a0", " ").replace("\u202f", " ")
    nom = ILLEGAL.sub("", nom).strip()
    nom = re.sub(r"\s+", " ", nom).strip(" .")
    if nom.split(".")[0].lower() in RESERVES:
        nom = "_" + nom
    if len(nom) > limite:
        tige, ext = os.path.splitext(nom)
        nom = tige[:limite - len(ext)].rstrip(" .") + ext
    return nom or T["sans_titre"]


def cle_nom(nom):
    """Forme comparable d'un nom : minuscules, espaces normalises, sans espace insecable."""
    s = nfc(nom or "").lower().replace("\u00a0", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", s).strip()


def empreinte(chemin, taille_bloc=262144):
    """Empreinte rapide du debut du fichier, pour reconnaitre un contenu deja present."""
    h = hashlib.sha1()
    try:
        with open(chemin, "rb") as f:
            h.update(f.read(taille_bloc))
    except OSError:
        return ""
    return h.hexdigest()


RE_ANNEE = re.compile(r"\(\s*20\d\d\s*[-–/]\s*20\d\d\s*\)|\b20\d\d\s*[-–/]\s*20\d\d\b|\b\d\d-\d\d\b")


def nettoie_dossier(nom, limite=90):
    """Nom de dossier, avec possibilite d'imbriquer : \"Cours\\Sous-dossier\" ou \"Cours/Sous-dossier\"."""
    parties = [p for p in re.split(r"[\\/]+", nfc(nom or "")) if p.strip()]
    return os.sep.join(nettoie(p, limite) for p in parties) or T["sans_titre"]


def dossier_defaut(cours):
    """Dossier propose pour un cours, deduit du nom Moodle.

    COURS_X (2026-2027) -> X - Cours (ou Lecture)
    SEM_X (2026-2027)   -> X - Seminaire (ou Seminar)
    X (2026-2027)       -> X
    """
    nom = RE_ANNEE.sub("", nfc(cours.get("fullname") or cours.get("shortname") or "Cours"))
    nom = re.sub(r"\s{2,}", " ", nom).strip(" -")
    court = (cours.get("shortname") or "").strip()
    if re.match(r"^cours[_\s:-]", court, re.I):
        nom = f"{nom} - {T['cours']}"
    elif re.match(r"^sem[_\s:-]", court, re.I) and not re.search(r"minaire|seminar", nom, re.I):
        nom = f"{nom} - {T['seminaire']}"
    return nettoie(nom, 90)


# -------------------------------------------------------------------- statuts

def lignes_html(fragment):
    """Lignes de texte d'un fragment HTML de Moodle : une par paragraphe, element de liste ou <br>.

    Les retours a la ligne du code source ne comptent pas : un intitule coupe en deux dans
    l'editeur (\"Lectures\\nobligatoires :\") reste sur une ligne.
    """
    import html
    s = re.sub(r"\s+", " ", fragment or "")
    s = re.sub(r"(?i)<br\s*/?>|</?(p|li|div|h\d|tr|ul|ol)\b[^>]*>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace(" ", " ")
    return [l.strip() for l in s.split("\n") if l.strip()]


def statut_titre(ligne):
    """Statut annonce par un intitule (\"Lectures obligatoires :\", \"Pour aller plus loin\"), sinon None.

    Seul le debut de la ligne compte, jusqu'aux deux-points : une phrase qui contient le mot
    (\"L'inscription au groupe est obligatoire.\", \"Formation obligatoire a Zotero\") n'est pas un
    intitule. Jusqu'a trois mots peuvent preceder l'expression (\"Autres manuels complementaires\").
    """
    tete = re.sub(r"\s+", " ", ligne or "").strip()
    deux_points = tete.find(":")
    if 0 <= deux_points <= 80:
        tete = tete[:deux_points]
    if len(tete) > 80:
        return None
    for cle in ("C", "P", "O"):
        if re.match(rf"^\W*(?:[\w'’-]+\s+){{0,3}}?(?:{T['re_' + cle.lower()]})", tete, re.I):
            return T[cle]
    return None


MOTS_VIDES = {"texte", "textes", "chap", "chapitre", "copie", "coupe", "extrait", "extraits", "version",
              "partie", "lecture", "lectures", "reading", "readings", "pages", "dans", "pour", "avec",
              "sous", "direction", "with", "from", "eds", "dir"}


def mots(texte, noms_composes=False):
    """Mots comparables (sans accents, minuscules, 4 lettres et plus) et annees d'un texte.

    Avec noms_composes, \"DicoBourdieu\" donne \"dico\" et \"bourdieu\" (noms de fichiers).
    """
    s = nfc(texte or "")
    if noms_composes:
        s = re.sub(r"([a-zà-ÿ])([A-Z])", r"\1 \2", s)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()
    annees = set()
    for n in re.findall(r"\d+", s):
        if len(n) in (4, 8):                    # 8 chiffres : \"19842002\" pour 1984/2002
            annees |= {a for a in (n[:4], n[4:]) if re.fullmatch(r"1[5-9]\d\d|20\d\d", a)}
    return {m for m in re.findall(r"[a-z]{4,}", s) if m not in MOTS_VIDES}, annees


def proches(a, b):
    """Meme mot, ou l'un prolonge l'autre (pluriel, coquille finale : \"Barraul\" et \"Barrault\").

    L'elision perdue dans un nom de fichier est toleree : \"LEtat\" vaut \"Etat\", \"lhomme\" \"homme\".
    """
    def variantes(m):
        return {m, m[1:]} if len(m) >= 5 and m[0] in "lcdjmnst" else {m}
    return any(x == y or (min(len(x), len(y)) >= 5 and (x.startswith(y) or y.startswith(x)))
               for x in variantes(a) for y in variantes(b))


def communs(mots_a, mots_b):
    return sum(1 for a in mots_a if any(proches(a, b) for b in mots_b))


def reference(ligne):
    """Auteurs, annees et mots d'une ligne de bibliographie, ou None si elle n'en a pas l'air.

    Les auteurs sont ce qui precede l'annee ou le titre, avec une virgule (\"Weber, Max (1995)\",
    \"Steven Lukes, « ... »\") : une phrase qui cite \"Studer (1996)\" n'est pas une reference.
    """
    m = re.search(r"\(\s*(1[5-9]|20)\d\d|[«“\"]|\b(1[5-9]|20)\d\d\b", ligne)
    if not m:
        return None
    auteurs = ligne[:m.start()]
    if "," not in auteurs or len(auteurs) > 150 or not re.search(r"[A-ZÀ-Ý][a-zà-ÿ]", auteurs):
        return None
    return {"noms": mots(auteurs)[0], "annees": set(re.findall(r"\b(?:1[5-9]|20)\d\d\b", ligne)),
            "tout": mots(ligne)[0]}


def rapprocher(fichier, refs):
    """Statut de la reference bibliographique qui designe ce fichier, ou None.

    Un nom d'auteur cite dans plusieurs references de la section ne suffit pas : il faut en
    plus l'annee ou un mot propre a cette reference, ou deux auteurs, ou deux mots propres.
    Un mot propre n'apparait dans aucune autre reference de la section : \"Birnbaum\", editeur
    de l'ouvrage qui contient trois des textes, ne designe aucun d'eux. Les mots du fichier
    doivent en majorite se retrouver dans la reference : \"Bourdieu, Science, politique et
    sciences sociales, 2021\" n'est pas \"Bourdieu (2021), La croyance et la representation\".
    En cas de doute entre deux statuts, rien n'est decide.
    """
    noms_f, annees_f = mots(fichier, noms_composes=True)
    if not noms_f:
        return None
    frequence = collections.Counter(m for _, r in refs for m in r["tout"])
    auteurs = collections.Counter(m for _, r in refs for m in r["noms"])
    retenus = []
    for statut, r in refs:
        propres = {m for m in r["tout"] - r["noms"] if frequence[m] == 1}
        n, t = communs(r["noms"], noms_f), communs(propres, noms_f)
        seul = any(auteurs[m] == 1 for m in r["noms"] if any(proches(m, f) for f in noms_f))
        a = bool(r["annees"] & annees_f)
        if not ((n and (a or t or seul)) or n >= 2 or t >= 2):
            continue
        couverture = (communs(noms_f, r["tout"]) + len(annees_f & r["annees"])) / (len(noms_f) + len(annees_f))
        if couverture < 0.6:
            continue
        retenus.append((3 * n + 2 * a + t + couverture, statut))
    if not retenus:
        return None
    retenus.sort(reverse=True)
    meilleur, statut = retenus[0]
    if any(s != statut and score >= meilleur - 1 for score, s in retenus[1:]):
        return None
    return statut


def bibliographie(resume):
    """Lignes de la bibliographie d'un resume de section, avec le statut de leur intitule."""
    refs, courant = [], None
    for ligne in lignes_html(resume):
        s = statut_titre(ligne)
        if s:
            courant = s
            ligne = ligne.split(":", 1)[1] if ":" in ligne[:81] else ""
        r = reference(ligne)
        if r and courant:
            refs.append((courant, r))
        elif not r and not s and len(ligne) > 40 and ligne.endswith((":", "?")):
            # Phrase qui annonce une autre liste (\"Exercice en classe : lisez les textes suivants :\")
            # sans dire leur statut : la liste precedente s'arrete la.
            courant = None
    return refs


def statuts_de_section(section, statut_section=None):
    """Statut explicite de chaque fichier d'une section, d'apres ce que l'enseignant a ecrit.

    Par ordre de priorite : etiquette placee avant le fichier, nom du dossier Moodle qui le
    contient (\"Lectures complementaires\"), liste de lectures du resume de section rapprochee du
    nom du fichier, intitule de la sous-section (statut_section). Rien n'est devine : un fichier
    que rien ne designe n'a pas de statut.
    Renvoie {nom de fichier: statut} et l'ensemble des fichiers classes d'apres la liste de lectures.
    """
    out, biblio, courant = {}, set(), None
    refs = bibliographie(section.get("summary"))
    for m in section.get("modules", []):
        if m.get("modname") == "label":
            lignes = lignes_html((m.get("description") or "")) or [m.get("name") or ""]
            s = statut_titre(lignes[0])
            if not s and re.search(T["re_s"], " ".join(lignes), re.I):
                s = T["S"]
            courant = s or courant
            continue
        if m.get("modname") not in ("resource", "folder"):
            continue
        dossier = statut_titre(m.get("name")) if m.get("modname") == "folder" else None
        for c in m.get("contents") or []:
            if c.get("type") != "file" or not c.get("filename"):
                continue
            nom = nfc(c["filename"])
            s = courant or dossier
            if not s and refs and os.path.splitext(nom)[1].lower() not in EXT_DIAPOS:
                s = rapprocher(f"{m.get('name') or ''} {os.path.splitext(nom)[0]}", refs)
                if s:
                    biblio.add(nom)
            s = s or statut_section
            if s:
                out[nom] = s
    return out, biblio


EXT_DIAPOS = (".pptx", ".ppt", ".pps", ".ppsx", ".key", ".odp")


def statut_deduit(nom_module, nom_fichier):
    """Le statut "Supports de cours" si le nom ou le type du fichier le dit nettement, sinon None.

    Reste volontairement etroit : seul un document produit par l'enseignant (diapos, syllabus,
    consignes...) se reconnait a son nom. Obligatoire et Complementaire ne se deduisent pas : seule
    une etiquette de l'enseignant, ou le syllabus du cours, le dit.
    """
    if os.path.splitext(nom_fichier or "")[1].lower() in EXT_DIAPOS:
        return T["S"]
    texte = f"{nom_module or ''} {nom_fichier or ''}"
    if re.search(T["re_sup_non"], texte, re.I):
        return None
    return T["S"] if re.search(T["re_sup"], texte, re.I) else None


# ------------------------------------------------------------------- collecte
def sous_sections(sections):
    """{identifiant de sous-section: section qui la contient}.

    Depuis Moodle 4.5, une section peut contenir des sous-sections (\"Lecture obligatoire\" dans la
    seance du 12 octobre). L'API les renvoie a la fin, comme des sections ordinaires : sans ce
    lien, leurs fichiers seraient ranges loin de leur seance.
    """
    parents = {}
    for s in sections:
        for m in s.get("modules", []):
            if m.get("modname") == "subsection":
                try:
                    parents[int(json.loads(m.get("customdata") or "{}")["sectionid"])] = s
                except (ValueError, KeyError, TypeError):
                    pass
    return parents


def collecte(token, cours, cfg, dire=print, liens=None, arreter=None):
    """Liste des fichiers a recuperer pour les cours choisis.

    Si une liste `liens` est fournie, les activites \"URL\" de Moodle y sont ajoutees.
    Leve Annule si `arreter()` devient vrai entre deux cours.
    """
    items = []
    for c in cours:
        if arreter and arreter():
            raise Annule()
        choix = cfg["cours"].get(str(c["id"]), {})
        if not choix.get("choisi", True):
            continue
        dossier = nettoie_dossier(choix.get("dossier") or dossier_defaut(c))
        dire(f"Lecture de {c['fullname']}...")
        sections = api(token, "core_course_get_contents", courseid=c["id"])
        parents = sous_sections(sections)
        for s in sections:
            parent = parents.get(s.get("id"))
            statut_sous = statut_titre(s.get("name")) if parent else None
            if statut_sous:
                # Sous-section \"Lecture obligatoire\" d'une seance : ses fichiers rejoignent le dossier
                # de la seance, avec le statut que son nom annonce. Les autres sous-sections (une par
                # date, par exemple) restent des dossiers a part, comme les sections.
                sec, sid_liens = nettoie(parent.get("name") or T["general"], 100), parent.get("id")
            else:
                sec, sid_liens = nettoie(s.get("name") or T["general"], 100), s.get("id")
            stats, biblio = statuts_de_section(s, statut_sous)
            for m in s.get("modules", []):
                mod = m.get("modname")
                if mod == "url" and liens is not None:
                    u = ((m.get("contents") or [{}])[0].get("fileurl") or "").strip()
                    if u:
                        liens.append({"dossier": dossier, "section": sec, "sid": sid_liens,
                                      "nom": m.get("name") or u,
                                      "url": u, "description": texte_brut(m.get("description"))})
                    continue
                if mod not in ("resource", "folder"):
                    continue
                sous = nettoie(m.get("name") or "", 80) if mod == "folder" else ""
                for f in m.get("contents") or []:
                    if f.get("type") != "file" or not f.get("fileurl"):
                        continue
                    statut = stats.get(nfc(f.get("filename") or ""))
                    deduit = False
                    if not statut and cfg.get("statuts"):
                        statut = statut_deduit(m.get("name"), f.get("filename"))
                        deduit = bool(statut)
                    items.append({
                        "cours": c["fullname"], "cid": c["id"], "dossier": dossier, "section": sec,
                        "sid": s.get("id"), "sous": sous, "nom": nettoie(f.get("filename") or "fichier"),
                        "url": f["fileurl"], "taille": f.get("filesize") or 0,
                        "t": f.get("timemodified") or 0,
                        "statut": statut, "deduit": deduit,
                        "biblio": nfc(f.get("filename") or "") in biblio,
                        "module": mod,
                    })
    if cfg.get("statuts"):
        biblio = sum(1 for it in items if it["biblio"])
        if biblio:
            dire(f"{biblio} fichiers classés d'après la liste de lectures de leur section (rapprochement "
                 "du nom du fichier avec l'auteur, l'année et le titre cités par l'enseignant).")
        deduits = sum(1 for it in items if it["deduit"])
        if deduits:
            dire(f"{deduits} fichiers classés en « {T['S']} » par déduction (nom ou type du fichier), "
                 "et non d'après une étiquette de l'enseignant.")
    return items


def chemin_cible(it, dest, avec_statuts):
    parts = [dest, it["dossier"], it["section"]]
    if it["sous"]:
        parts.append(it["sous"])
    if avec_statuts and it.get("statut"):
        parts.append(it["statut"])
    parts.append(it["nom"])
    chemin = os.path.join(*parts)
    if len(chemin) > 240:
        surplus = len(chemin) - 240
        tige, ext = os.path.splitext(it["nom"])
        court = tige[:max(20, len(tige) - surplus - 5)].rstrip(" .") + ext
        parts[-1] = court
        chemin = os.path.join(*parts)
    return chemin


def index_existant(dest):
    """Fichiers deja ranges : par nom normalise (avec taille), et par taille + empreinte.

    Les dossiers caches (.obsidian, .trash d'un coffre Obsidian, etc.) sont ignores.
    """
    par_nom, par_taille = {}, {}
    if not os.path.isdir(dest):
        return par_nom, par_taille
    for r, ds, fs in os.walk(dest):
        ds[:] = [d for d in ds if not d.startswith(".")]
        for f in fs:
            if f.startswith(".") or f.endswith(".part"):
                continue
            p = os.path.join(r, f)
            try:
                taille = os.path.getsize(p)
            except OSError:
                continue
            par_nom.setdefault(cle_nom(f), set()).add((taille, p))
            par_taille.setdefault(taille, set()).add((empreinte(p), p))
    return par_nom, par_taille


def deja_present(it, cible, par_nom, meme_cours=lambda p: True):
    """Chemin du fichier s'il est deja range dans son cours, sinon None.

    Meme nom dans le dossier de destination : present. Meme nom ailleurs dans le dossier du
    cours (rangement a la main) : present seulement si la taille annoncee par Moodle concorde.
    Un fichier range dans un autre cours ne compte jamais : un PDF publie dans deux cours
    doit se retrouver dans les deux dossiers.
    """
    if os.path.exists(cible):
        return cible
    ici = os.path.normcase(os.path.dirname(cible))
    for taille, p in sorted(par_nom.get(cle_nom(it["nom"]), ())):
        if os.path.normcase(os.path.dirname(p)) == ici:
            return p
        if it["taille"] and taille == it["taille"] and meme_cours(p):
            return p
    return None


def repartiteur(dest, items):
    """Fonction qui dit a quel dossier de cours appartient un chemin.

    Le dossier de cours le plus profond l'emporte : un fichier de
    \"Theories economiques\\SITE (seminaire)\" appartient au SITE, pas au cours ITE qui le contient.
    """
    racines = sorted({os.path.normcase(os.path.join(dest, it["dossier"])) for it in items},
                     key=len, reverse=True)

    def cours_de(p):
        q = os.path.normcase(p)
        return next((r for r in racines if q.startswith(r + os.sep)), None)
    return cours_de


# ------------------------------------------------------------------- etat
def charger_etat(dest):
    """Pour chaque fichier Moodle deja recupere : sa version (timemodified) et ou il est range."""
    try:
        with open(os.path.join(dest, ETAT), encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def sauver_etat(dest, etat):
    if not os.path.isdir(dest):
        return
    p = os.path.join(dest, ETAT)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=0)
    os.replace(p + ".tmp", p)


def cle_url(url):
    """Identifiant stable d'un fichier Moodle : son adresse sans parametres."""
    return url.split("?", 1)[0]


def a_recuperer(it, etat):
    """Vrai si ce fichier Moodle n'a jamais ete recupere, ou si l'enseignant l'a republie depuis."""
    connu = etat.get(cle_url(it["url"]))
    return not connu or bool(it.get("t") and it["t"] > connu.get("t", 0))


def nom_ancienne_version(chemin, t):
    tige, ext = os.path.splitext(chemin)
    date = time.strftime("%Y-%m-%d", time.localtime(t)) if t else T["date_inconnue"]
    candidat, n = f"{tige} ({T['ancienne']} {date}){ext}", 2
    while os.path.exists(candidat):
        candidat, n = f"{tige} ({T['ancienne']} {date}, {n}){ext}", n + 1
    return candidat


def sections_reelles(items, dest, etat, cours_de):
    """Dossier ou se trouvent reellement les fichiers de chaque section Moodle (par identifiant).

    L'utilisateur a pu renommer ou raccourcir un dossier de section, ou l'enseignant renommer la
    section sur Moodle : les nouveautes doivent rejoindre le dossier existant au lieu d'en creer
    un second a cote. Vote a la majorite des fichiers deja ranges ; a egalite, le nom donne a la
    main (different du nom Moodle) l'emporte. Le choix est retenu dans l'etat, pour les sections
    dont aucun fichier n'est encore connu (sections qui ne contiennent que des liens).
    Renvoie {identifiant de section: nom du dossier de section dans le dossier du cours}.
    """
    retenu = etat.setdefault("_sections", {})
    votes = {}
    for it in items:
        e = etat.get(cle_url(it["url"]))
        if not e or not it.get("sid"):
            continue
        p = os.path.join(dest, e["chemin"])
        racine = os.path.join(dest, it["dossier"])
        if not os.path.exists(p) or cours_de(p) != os.path.normcase(racine):
            continue
        parties = os.path.relpath(p, racine).split(os.sep)
        if len(parties) > 1:
            votes.setdefault(str(it["sid"]), collections.Counter())[parties[0]] += 1
    choix = {}
    for it in items:
        sid = str(it.get("sid") or "")
        if not sid or sid in choix:
            continue
        if sid in votes:
            v = votes[sid]
            choix[sid] = max(v, key=lambda nom: (v[nom], nom != it["section"]))
        elif sid in retenu and os.path.isdir(os.path.join(dest, it["dossier"], retenu[sid])):
            choix[sid] = retenu[sid]
    retenu.update(choix)
    return choix


def renommer_dossier_cours(dest, ancien, nouveau):
    """Renomme sur le disque le dossier d'un cours et reporte le changement dans la memoire.

    Sans cela, le programme ne reconnaitrait plus les fichiers deja ranges (ils sont cherches
    dans le dossier du cours) et les retelechargerait dans un nouveau dossier.
    Leve Erreur si le renommage est impossible ; rien n'est alors modifie.
    """
    src, dst = os.path.join(dest, ancien), os.path.join(dest, nouveau)
    meme = os.path.normcase(src) == os.path.normcase(dst)      # simple changement de casse
    if os.path.normcase(dst).startswith(os.path.normcase(src) + os.sep):
        raise Erreur("Le nouveau dossier ne peut pas être à l'intérieur de l'ancien.")
    if os.path.exists(dst) and not meme:
        raise Erreur(f"Un dossier « {nouveau} » existe déjà. Choisis un autre nom, "
                     "ou regroupe les deux dossiers à la main avant de renommer.")
    if os.path.isdir(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            os.rename(src, dst)
        except OSError as e:
            raise Erreur(f"Renommage impossible ({e.strerror}). Un fichier de ce dossier est "
                         "peut-être ouvert dans un autre programme : ferme-le et réessaie.")
    etat = charger_etat(dest)
    prefixe = os.path.normcase(ancien) + os.sep
    for v in etat.values():
        if isinstance(v, dict) and os.path.normcase(v.get("chemin", "")).startswith(prefixe):
            v["chemin"] = nouveau + os.sep + v["chemin"][len(prefixe):]
    sauver_etat(dest, etat)


def recuperer(url, token, partiel, arreter=None):
    """Telecharge dans `partiel`. Leve Annule entre deux blocs si `arreter()` devient vrai."""
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(f"{url}{sep}token={token}", headers={"User-Agent": "MoodleSync/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(partiel, "wb") as fh:
        while True:
            if arreter and arreter():
                raise Annule()
            bloc = r.read(1 << 16)
            if not bloc:
                break
            fh.write(bloc)


def telecharger(items, cfg, dire=print, progres=None, arreter=None):
    """Telecharge les fichiers manquants ou republies, et les range. Renvoie un compte rendu.

    Un fichier republie par l'enseignant (timemodified plus recent) remplace l'ancien, qui est
    renomme a cote, jamais ecrase. Au premier passage, l'etat present sert de reference.
    Si `arreter()` devient vrai, le fichier en cours est abandonne (son .part est efface) et
    ceux deja termines restent ranges ; le compte rendu porte alors "annule".
    """
    dest = cfg["dest"]
    par_nom, par_taille = index_existant(dest)
    etat = charger_etat(dest)
    absolu = lambda rel: os.path.join(dest, rel)
    relatif = lambda p: os.path.relpath(p, dest)
    neufs, maj, doublons, erreurs, annule = [], [], 0, 0, False
    total = len(items)
    cours_de = repartiteur(dest, items)
    # Fichiers deplaces a la main depuis le dernier passage : on les relocalise d'abord, pour que
    # le choix des dossiers de section se fonde sur leur emplacement actuel.
    for it in items:
        connu = etat.get(cle_url(it["url"]))
        if connu and os.path.exists(absolu(connu["chemin"])):
            continue
        racine = os.path.normcase(os.path.join(dest, it["dossier"]))
        local = deja_present(it, chemin_cible(it, dest, cfg["statuts"]), par_nom,
                             lambda p: cours_de(p) == racine)
        if local:
            etat[cle_url(it["url"])] = {"t": connu["t"] if connu else it["t"], "chemin": relatif(local)}
    sections = sections_reelles(items, dest, etat, cours_de)

    def vu(i, texte):
        if progres:
            progres(i, total, texte)

    try:
        for i, it in enumerate(items, 1):
            if arreter and arreter():
                annule = True
                break
            if sections.get(str(it.get("sid"))):
                it = dict(it, section=sections[str(it["sid"])])
            cle = cle_url(it["url"])
            racine = os.path.normcase(os.path.join(dest, it["dossier"]))
            meme_cours = lambda p: cours_de(p) == racine
            connu = etat.get(cle)
            if connu and os.path.exists(absolu(connu["chemin"])) and meme_cours(absolu(connu["chemin"])):
                local = absolu(connu["chemin"])
            else:
                local = deja_present(it, chemin_cible(it, dest, cfg["statuts"]), par_nom, meme_cours)
                if local:
                    # Premier passage, ou fichier deplace a la main : on retient ou il est.
                    connu = {"t": connu["t"] if connu else it["t"], "chemin": relatif(local)}
                    etat[cle] = connu
            if local and not (it["t"] and it["t"] > connu["t"]):
                doublons += 1
                vu(i, f"Déjà présent : {it['nom']}")
                continue
            cible = local or chemin_cible(it, dest, cfg["statuts"])
            partiel = cible + ".part"
            try:
                os.makedirs(os.path.dirname(cible), exist_ok=True)
                recuperer(it["url"], cfg["token"], partiel, arreter)
                fp, taille = empreinte(partiel), os.path.getsize(partiel)
                if local:
                    if taille == os.path.getsize(local) and fp == empreinte(local):
                        # Date changee sur Moodle, contenu identique.
                        os.remove(partiel)
                        connu["t"] = it["t"]
                        doublons += 1
                        vu(i, f"Déjà présent : {it['nom']}")
                        continue
                    ancien = nom_ancienne_version(local, connu["t"])
                    os.replace(local, ancien)
                    os.replace(partiel, local)
                    connu["t"] = it["t"]
                    maj.append((it["dossier"], local, ancien))
                    dire(f"Mis a jour : {it['nom']} (ancienne version conservee)")
                    vu(i, f"Mis à jour : {it['nom']}")
                    continue
                # Meme contenu deja present sous un autre nom dans ce cours : pas de doublon.
                # Dans un autre cours, on range quand meme une copie ici.
                jumeaux = sorted(q for (e, q) in par_taille.get(taille, set())
                                 if e == fp and meme_cours(q))
                if jumeaux:
                    os.remove(partiel)
                    etat[cle] = {"t": it["t"], "chemin": relatif(jumeaux[0])}
                    doublons += 1
                    dire(f"Contenu deja present sous un autre nom : {it['nom']}")
                    vu(i, f"Déjà présent sous un autre nom : {it['nom']}")
                    continue
                os.replace(partiel, cible)
                par_nom.setdefault(cle_nom(it["nom"]), set()).add((taille, cible))
                par_taille.setdefault(taille, set()).add((fp, cible))
                etat[cle] = {"t": it["t"], "chemin": relatif(cible)}
                neufs.append((it["dossier"], cible))
                vu(i, it["nom"])
            except Annule:
                annule = True
                if os.path.exists(partiel):
                    os.remove(partiel)
                break
            except Exception as e:
                erreurs += 1
                if os.path.exists(partiel):
                    try:
                        os.remove(partiel)
                    except OSError:
                        pass
                dire(f"Echec sur {it['nom']} : {str(e)[:120]}")
    finally:
        sauver_etat(dest, etat)
    restants = collections.Counter(it["cid"] for it in items if it.get("cid") is not None
                                   and a_recuperer(it, etat))
    return {"total": total, "neufs": len(neufs), "maj": len(maj), "doublons": doublons,
            "erreurs": erreurs, "dest": dest, "liste_neufs": neufs, "liste_maj": maj,
            "annule": annule, "restants": restants}


def texte_brut(fragment):
    """Texte lisible d'un fragment HTML de Moodle."""
    import html
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def titre_video(url):
    """Titre reel d'une video YouTube, via le service oEmbed public (sans cle). None sinon."""
    if not re.search(r"(youtube\.com|youtu\.be)/", url):
        return None
    q = urllib.parse.urlencode({"url": url, "format": "json"})
    try:
        with urllib.request.urlopen("https://www.youtube.com/oembed?" + q, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if not d.get("title"):
        return None
    return f"{d['title']} ({d['author_name']})" if d.get("author_name") else d["title"]


def ecrire_liens(liens, dest, dire=print):
    """Ecrit la note de liens de chaque section. Renvoie les liens apparus depuis le passage precedent.

    Le fichier n'est reecrit que s'il change, et seulement s'il porte encore la MARQUE :
    sans elle, l'utilisateur l'a repris a la main et on n'y touche plus.
    Au tout premier passage, les liens existants servent de reference et ne sont pas annonces.
    """
    etat = charger_etat(dest)
    titres = etat.setdefault("_titres_videos", {})
    premiere = "_liens_vus" not in etat
    sans_tiret = lambda s: re.sub(r"\s*[–—]\s*", ", ", s)  # tirets longs : virgule
    vus = set(etat.get("_liens_vus", []))
    lien_md = lambda texte, u: (f"[{texte.replace('[', '(').replace(']', ')')}]"
                                f"({u.replace(' ', '%20').replace('(', '%28').replace(')', '%29')})")
    par_section, nouveaux = {}, []
    reelles = etat.get("_sections", {})      # dossiers de section reels, appris par telecharger
    for l in liens:
        section = reelles.get(str(l.get("sid")), l["section"])
        par_section.setdefault((l["dossier"], section), []).append(l)
    for (dossier, section), ls in par_section.items():
        chemin = os.path.join(dest, dossier, section, T["liens"])
        lignes = [MARQUE, "", f"# {T['titre_liens']}{section}", ""]
        for l in ls:
            if l["url"] not in titres:
                t = titre_video(l["url"])
                if t:
                    titres[l["url"]] = t
            domaine = urllib.parse.urlparse(l["url"]).netloc.replace("www.", "")
            lignes.append(f"- {lien_md(sans_tiret(l['nom']), l['url'])} ({domaine})")
            if titres.get(l["url"]):
                lignes.append(f"  {T['video']}{T['sep']}{sans_tiret(titres[l['url']])}")
            if l["description"]:
                d = sans_tiret(l["description"])
                lignes.append(f"  {d[:400] + '…' if len(d) > 400 else d}")
            if not premiere and l["url"] not in vus:
                nouveaux.append((dossier, l["nom"], l["url"]))
        texte = "\n".join(lignes) + "\n"
        try:
            with open(chemin, encoding="utf-8-sig") as f:
                avant = f.read()
        except OSError:
            avant = None
        if avant == texte:
            continue
        if avant is not None and not avant.startswith(MARQUE):
            dire(f"Note de liens modifiee a la main, laissee telle quelle : {chemin}")
            continue
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte)
    etat["_liens_vus"] = sorted({l["url"] for l in liens} | vus)
    sauver_etat(dest, etat)
    return nouveaux


def ecrire_note(r):
    """Ajoute en tete de la note Markdown les fichiers arrives ou mis a jour. Renvoie son chemin."""
    if not (r["liste_neufs"] or r["liste_maj"] or r.get("liste_liens")):
        return None
    dest = r["dest"]

    def lien(p):
        rel = os.path.relpath(p, dest).replace("\\", "/")
        return f"[{os.path.basename(p)}]({urllib.parse.quote(rel)})"

    par_cours = {}
    for dossier, p in r["liste_neufs"]:
        par_cours.setdefault(dossier, []).append(f"- {lien(p)}")
    for dossier, p, ancien in r["liste_maj"]:
        par_cours.setdefault(dossier, []).append(
            f"- {T['maj']}{T['sep']}{lien(p)} ({T['conservee']}{T['sep']}{lien(ancien)})")
    for dossier, nom, url in r.get("liste_liens", []):
        par_cours.setdefault(dossier, []).append(f"- {T['nouveau_lien']}{T['sep']}[{nom}]({url})")
    bloc = [f"## {time.strftime(T['date_note'])}", ""]
    for dossier in sorted(par_cours):
        bloc += [f"### {dossier.replace(chr(92), ' / ')}", *par_cours[dossier], ""]

    chemin = os.path.join(dest, T["note"])
    entete = f"# {T['titre_note']}\n\n"
    try:
        with open(chemin, encoding="utf-8-sig") as f:
            avant = f.read()
    except OSError:
        avant = ""
    if avant.startswith(entete):
        avant = avant[len(entete):]
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(entete + "\n".join(bloc) + "\n" + avant)
    return chemin


# ------------------------------------------------------- lancement automatique
def commande_auto():
    """Programme et arguments a lancer a l'ouverture de session."""
    if getattr(sys, "frozen", False):
        return sys.executable, ["--auto", "--demarrage"]
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return (pyw if os.path.exists(pyw) else sys.executable,
            [os.path.abspath(__file__), "--auto", "--demarrage"])


def regler_demarrage(actif):
    """Cree ou retire le raccourci du dossier Demarrage de Windows, ou l'agent de lancement
    de macOS (aucun droit admin requis dans les deux cas)."""
    if not actif:
        if os.path.exists(DEMARRAGE):
            os.remove(DEMARRAGE)
        return
    cible, args = commande_auto()
    if MAC:
        import plistlib
        os.makedirs(os.path.dirname(DEMARRAGE), exist_ok=True)
        with open(DEMARRAGE, "wb") as f:
            plistlib.dump({"Label": "ch.moodlesync", "ProgramArguments": [cible] + args,
                           "RunAtLoad": True, "ProcessType": "Interactive"}, f)
        return
    args = " ".join(f'"{a}"' if " " in a else a for a in args)
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:MS_LNK);"
          "$s.TargetPath=$env:MS_CIBLE;$s.Arguments=$env:MS_ARGS;$s.Save()")
    env = dict(os.environ, MS_LNK=DEMARRAGE, MS_CIBLE=cible, MS_ARGS=args)
    os.makedirs(os.path.dirname(DEMARRAGE), exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env,
                   check=True, capture_output=True, creationflags=0x08000000)  # sans console


def ouvrir_dossier(d):
    """Ouvre un dossier dans l'explorateur Windows ou le Finder."""
    if MAC:
        subprocess.Popen(["open", d])
    else:
        os.startfile(d)


def prevenir(texte, ouvrir=None):
    """Petite fenetre d'information, utilisee par le lancement automatique."""
    import tkinter as tk
    from tkinter import messagebox
    racine = tk.Tk()
    racine.withdraw()
    racine.attributes("-topmost", True)
    if ouvrir:
        if messagebox.askyesno("MoodleSync", texte + "\n\nOuvrir le dossier ?", parent=racine):
            ouvrir_dossier(ouvrir)
    else:
        messagebox.showinfo("MoodleSync", texte, parent=racine)
    racine.destroy()


def resume_cours(token, cours, etat=None):
    """Nombre de fichiers, volume et nouveautes (fichiers jamais recuperes ou republies) par cours."""
    out = []
    etat = etat or {}
    for c in cours:
        n, taille, nouveaux = 0, 0, 0
        try:
            sections = api(token, "core_course_get_contents", courseid=c["id"])
        except Erreur:
            sections = []
        for s in sections:
            for m in s.get("modules", []):
                if m.get("modname") in ("resource", "folder"):
                    for f in m.get("contents") or []:
                        if f.get("type") == "file":
                            n += 1
                            taille += f.get("filesize") or 0
                            if f.get("fileurl") and a_recuperer(
                                    {"url": f["fileurl"], "t": f.get("timemodified") or 0}, etat):
                                nouveaux += 1
        out.append({"id": c["id"], "nom": c["fullname"], "shortname": c.get("shortname", ""),
                    "nb": n, "taille": taille, "nouveaux": nouveaux})
    return out


def nouveautes_par_cours(r):
    """Lignes "Cours : 3 nouveaux fichiers, 1 mis a jour, 2 liens", du cours le plus touche au moins."""
    compte = {}
    for genre, liste in (("neufs", r["liste_neufs"]), ("maj", r["liste_maj"]),
                         ("liens", r.get("liste_liens") or [])):
        for x in liste:
            compte.setdefault(x[0], collections.Counter())[genre] += 1
    lignes = []
    for dossier, c in sorted(compte.items(), key=lambda kv: -sum(kv[1].values())):
        morceaux = []
        if c["neufs"]:
            morceaux.append(f"{c['neufs']} nouveau{'x' if c['neufs'] > 1 else ''} fichier{'s' if c['neufs'] > 1 else ''}")
        if c["maj"]:
            morceaux.append(f"{c['maj']} mis à jour")
        if c["liens"]:
            morceaux.append(f"{c['liens']} lien{'s' if c['liens'] > 1 else ''}")
        lignes.append(f"{dossier.replace(chr(92), ' / ')} : {', '.join(morceaux)}")
    return lignes


def notifier(titre, lignes):
    """Notification du systeme (centre de notifications de Windows ou de macOS). Vrai si envoyee.

    Rien ne quitte l'ordinateur : c'est une notification locale. Sous Windows, MoodleSync
    s'inscrit une fois dans le registre de l'utilisateur (HKCU) pour que la notification porte
    son nom ; aucun droit administrateur n'est requis.
    """
    texte = "\n".join(lignes[:4]) + (f"\net {len(lignes) - 4} autres cours" if len(lignes) > 4 else "")
    try:
        if MAC:
            script = ["-e", "on run argv", "-e",
                      "display notification (item 2 of argv) with title (item 1 of argv)", "-e", "end run"]
            subprocess.run(["osascript", *script, titre, texte], check=True, capture_output=True, timeout=20)
            return True
        import winreg
        from xml.sax.saxutils import escape
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\AppUserModelId\MoodleSync") as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "MoodleSync")
            icone = chemin_icone_image()
            if icone:
                winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, icone)
        xml = ("<toast><visual><binding template=\"ToastGeneric\">"
               f"<text>{escape(titre)}</text><text>{escape(texte)}</text>"
               "</binding></visual></toast>")
        ps = ("$null=[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime];"
              "$null=[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom,ContentType=WindowsRuntime];"
              "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;$x.LoadXml($env:MS_XML);"
              "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('MoodleSync')"
              ".Show([Windows.UI.Notifications.ToastNotification]::new($x))")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       env=dict(os.environ, MS_XML=xml), check=True, capture_output=True,
                       timeout=30, creationflags=0x08000000)
        return True
    except Exception:
        return False


def humain(n):
    for u in ("o", "Ko", "Mo", "Go"):
        if n < 1024:
            return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.1f} To"


# ------------------------------------------------------------------ interface
COULEURS = {
    "light": {"ok": "#0f7b0f", "ko": "#c42b1c", "neutre": "#616161", "doux": "#6b6b6b",
              "journal": "#f3f3f3", "texte": "#1b1b1b", "accent": "#005fb8", "fond": "#fafafa"},
    "dark": {"ok": "#6ccb5f", "ko": "#ff99a4", "neutre": "#9e9e9e", "doux": "#a8a8a8",
             "journal": "#2b2b2b", "texte": "#e4e4e4", "accent": "#60cdff", "fond": "#1c1c1c"},
}


def theme_systeme():
    """'dark' ou 'light', selon le reglage Windows des applications ou l'apparence de macOS
    (ou MOODLESYNC_THEME)."""
    force = os.environ.get("MOODLESYNC_THEME", "").lower()
    if force in ("dark", "light"):
        return force
    if MAC:
        # La cle n'existe qu'en mode sombre : `defaults` echoue en mode clair.
        try:
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                               capture_output=True, text=True, timeout=2)
            return "dark" if "dark" in r.stdout.lower() else "light"
        except Exception:
            return "light"
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
    except OSError:
        return "light"


def chemin_icone():
    """L'exe porte son icone ; en script, MoodleSync.ico est a cote du fichier."""
    if getattr(sys, "frozen", False):
        return sys.executable
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MoodleSync.ico")
    return p if os.path.exists(p) else None


def chemin_icone_image():
    """Icone pour les notifications, copiee dans APP_DIR : le dossier temporaire ou l'exe
    decompresse ses fichiers disparait a la fermeture, avant que la notification ne s'efface."""
    src = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "MoodleSync.ico")
    dst = os.path.join(APP_DIR, "MoodleSync.ico")
    try:
        if not os.path.exists(dst) and os.path.exists(src):
            os.makedirs(APP_DIR, exist_ok=True)
            with open(src, "rb") as a, open(dst, "wb") as b:
                b.write(a.read())
    except OSError:
        return None
    return dst if os.path.exists(dst) else None


# Polices : (titres, crayon de renommage, journal). Le crayon est un glyphe de Segoe MDL2 Assets
# sous Windows, un caractere Unicode ordinaire sous macOS.
if MAC:
    POLICE_TITRE, POLICE_CRAYON, CRAYON, POLICE_JOURNAL = ("Helvetica Neue", "bold"), ("Helvetica Neue", 13), "✎", ("Menlo", 11)
else:
    POLICE_TITRE, POLICE_CRAYON, CRAYON, POLICE_JOURNAL = ("Segoe UI Semibold",), ("Segoe MDL2 Assets", 11), "", ("Consolas", 9)


def lancer_interface():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog
    try:
        import sv_ttk
    except ImportError:          # sans le theme, l'interface reste fonctionnelle, en style classique
        sv_ttk = None
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
        # Sans cet identifiant, la barre des taches range la fenetre sous l'icone de Python.
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("MoodleSync")
    except Exception:
        pass
    CARTE = "Card.TFrame" if sv_ttk else "TFrame"
    ACCENT = "Accent.TButton" if sv_ttk else "TButton"
    INTER = "Switch.TCheckbutton" if sv_ttk else "TCheckbutton"

    def barre_titre(fenetre, sombre):
        """Barre de titre sombre ou claire (Windows 10 recent et 11)."""
        try:
            from ctypes import windll, byref, c_int, sizeof
            hwnd = windll.user32.GetParent(fenetre.winfo_id())
            v = c_int(1 if sombre else 0)
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(v), sizeof(v))
        except Exception:
            pass

    class Fenetre(tk.Tk):
        def __init__(self):
            super().__init__()
            self.withdraw()               # on n'affiche qu'une fois le theme applique
            self.cfg = charger_config()
            appliquer_config(self.cfg)
            self.file = queue.Queue()
            self._suite_site = None
            self.liste = {}
            self.occupe = False
            self.arret = threading.Event()
            self.connecte = False
            self.theme = None
            self.title("MoodleSync")
            self.geometry("880x940")
            self.minsize(760, 780)
            icone = chemin_icone()
            if icone:
                try:
                    self.iconbitmap(default=icone)
                except tk.TclError:
                    pass
            self.var_dest = tk.StringVar(value=self.cfg["dest"])
            self.var_site = tk.StringVar(value=self.cfg["site"])
            self.var_langue = tk.StringVar(value=T["nom"])
            self.var_dest.trace_add("write", lambda *a: self._dest_changee())
            self._appliquer_theme()
            self._construire()
            self._construire_accueil()
            self._appliquer_theme(force=True)
            premiere_fois = not (self.cfg["token"] or self.cfg["cours"] or self.cfg.get("accueil_fait"))
            (self.accueil if premiere_fois else self.principal).pack(fill="both", expand=True)
            self.update()                 # laisse passer <<ThemeChanged>> avant de nettoyer
            self._nettoyer_palette()
            barre_titre(self, self.theme == "dark")
            self.deiconify()
            self.after(120, self._pompe)
            self.after(2000, self._suivre_theme)
            if os.path.exists(DEMARRAGE):
                # Le programme a pu etre deplace depuis l'activation : on remet le raccourci a jour.
                try:
                    regler_demarrage(True)
                except Exception:
                    pass
            if self.cfg["token"]:
                self._verifier()
            else:
                self._statut("Non connecté", False)

        # -------------------------------------------------------------- theme
        def _appliquer_theme(self, force=False):
            theme = theme_systeme()
            if theme == self.theme and not force:
                return
            change = self.theme is not None and theme != self.theme
            self.theme = theme
            if sv_ttk:
                sv_ttk.set_theme(theme)
            c = COULEURS[theme]
            st = ttk.Style()
            # Les styles derives sont propres a chaque theme : on les redefinit a chaque bascule.
            st.configure("Titre.TLabel", font=(POLICE_TITRE[0], 20) + POLICE_TITRE[1:])
            st.configure("Soustitre.TLabel", foreground=c["doux"])
            st.configure("Section.TLabel", font=(POLICE_TITRE[0], 12) + POLICE_TITRE[1:])
            st.configure("Doux.TLabel", foreground=c["doux"])
            st.configure("Etape.TLabel", font=(POLICE_TITRE[0], 16) + POLICE_TITRE[1:], foreground=c["accent"])
            st.configure("Ok.TLabel", foreground=c["ok"])
            st.configure("Ko.TLabel", foreground=c["ko"])
            st.configure("Neutre.TLabel", foreground=c["neutre"])
            st.configure("Nouveau.TLabel", foreground=c["accent"])
            st.configure("Crayon.TLabel", font=POLICE_CRAYON, foreground=c["doux"])
            self.after(50, self._nettoyer_palette)
            if change:
                barre_titre(self, theme == "dark")
                if self.state() == "normal":
                    # Windows ne repeint la barre de titre qu'au redimensionnement.
                    l, h = self.winfo_width(), self.winfo_height()
                    self.geometry(f"{l + 1}x{h}")
                    self.after(30, lambda: self.geometry(f"{l}x{h}"))

        def _nettoyer_palette(self, w=None):
            """Annule les couleurs que tk_setPalette (appele par sv-ttk) impose a chaque widget.

            Sous Tk 9, les widgets ttk acceptent l'option -foreground : la palette l'y fixe et
            ecrase alors les couleurs des styles (statut vert ou rouge, textes secondaires).
            """
            racine = w is None
            for e in (w or self).winfo_children():
                if isinstance(e, ttk.Widget):
                    try:
                        e.configure(foreground="")
                    except tk.TclError:
                        pass
                self._nettoyer_palette(e)
            if racine and hasattr(self, "journal"):
                c = COULEURS[self.theme]
                self.journal.configure(background=c["journal"], foreground=c["texte"])
                self.zone.configure(background=ttk.Style().lookup(".", "background") or c["fond"])

        def _suivre_theme(self):
            self._appliquer_theme()
            self.after(2000, self._suivre_theme)

        # ------------------------------------------------------------ widgets
        def _construire(self):
            self.principal = p = ttk.Frame(self, padding=(28, 20, 28, 20))

            tete = ttk.Frame(p)
            tete.pack(fill="x")
            titres = ttk.Frame(tete)
            titres.pack(side="left")
            ttk.Label(titres, text="MoodleSync", style="Titre.TLabel").pack(anchor="w")
            ttk.Label(titres, text="Tes fichiers Moodle, téléchargés et rangés par cours.",
                      style="Soustitre.TLabel").pack(anchor="w")
            self.btn_co = ttk.Button(tete, text="Se connecter à Moodle", command=self._connecter)
            self.btn_co.pack(side="right")
            self.lbl = ttk.Label(tete, text="", style="Neutre.TLabel")
            self.lbl.pack(side="right", padx=(0, 14))
            ttk.Separator(p).pack(fill="x", pady=16)

            ttk.Label(p, text="Adresse de ton Moodle", style="Section.TLabel").pack(anchor="w")
            ligne_site = ttk.Frame(p)
            ligne_site.pack(fill="x", pady=(6, 16))
            entree = ttk.Entry(ligne_site, textvariable=self.var_site)
            entree.pack(side="left", fill="x", expand=True)
            entree.bind("<Return>", lambda e: self._appliquer_site())
            self.btn_site = ttk.Button(ligne_site, text="Appliquer", command=self._appliquer_site)
            self.btn_site.pack(side="left", padx=(8, 0))

            ttk.Label(p, text="Dossier de rangement", style="Section.TLabel").pack(anchor="w")
            ligne = ttk.Frame(p)
            ligne.pack(fill="x", pady=(6, 16))
            ttk.Entry(ligne, textvariable=self.var_dest).pack(side="left", fill="x", expand=True)
            ttk.Button(ligne, text="Changer…", command=self._choisir_dossier).pack(side="left", padx=(8, 0))

            tete_cours = ttk.Frame(p)
            tete_cours.pack(fill="x")
            ttk.Label(tete_cours, text="Cours", style="Section.TLabel").pack(side="left")
            self.lbl_total = ttk.Label(tete_cours, text="", style="Doux.TLabel")
            self.lbl_total.pack(side="left", padx=12)
            ttk.Button(tete_cours, text="Tout décocher", command=lambda: self._cocher(False)).pack(side="right")
            ttk.Button(tete_cours, text="Tout cocher", command=lambda: self._cocher(True)).pack(
                side="right", padx=8)

            cadre = ttk.Frame(p, style=CARTE, padding=6)
            cadre.pack(fill="both", expand=True, pady=(8, 4))
            ttk.Label(p, style="Doux.TLabel",
                      text="Pour renommer le dossier d'un cours, clique sur son crayon. Ne le renomme jamais "
                           f"dans {EXPLORATEUR} : MoodleSync ne retrouverait plus les fichiers "
                           "et les téléchargerait une seconde fois.",
                      wraplength=780, justify="left").pack(anchor="w", pady=(0, 16))
            self.zone = tk.Canvas(cadre, highlightthickness=0, borderwidth=0, height=200)
            defil = ttk.Scrollbar(cadre, orient="vertical", command=self.zone.yview)
            self.zone.configure(yscrollcommand=defil.set)
            defil.pack(side="right", fill="y")
            self.zone.pack(side="left", fill="both", expand=True)
            self.lignes = ttk.Frame(self.zone)
            self.lignes.columnconfigure(0, weight=1)
            fen = self.zone.create_window(0, 0, window=self.lignes, anchor="nw")
            self.lignes.bind("<Configure>",
                             lambda e: self.zone.configure(scrollregion=self.zone.bbox("all")))
            self.zone.bind("<Configure>", lambda e: self.zone.itemconfigure(fen, width=e.width))
            self.bind_all("<MouseWheel>", self._molette)
            ttk.Label(self.lignes, text="Connecte-toi pour voir tes cours.", style="Doux.TLabel").grid(
                padx=12, pady=12, sticky="w")

            tete_opts = ttk.Frame(p)
            tete_opts.pack(fill="x")
            ttk.Label(tete_opts, text="Options", style="Section.TLabel").pack(side="left")
            self._combo_langue(tete_opts).pack(side="right")
            ttk.Label(tete_opts, text="Langue des dossiers et du classement",
                      style="Doux.TLabel").pack(side="right", padx=10)
            opts = ttk.Frame(p)
            opts.pack(fill="x", pady=(6, 16))
            self.var_statuts = tk.BooleanVar(value=self.cfg["statuts"])
            self.chk_statuts = ttk.Checkbutton(opts, style=INTER, variable=self.var_statuts,
                                               text=self._texte_statuts(), command=self._statuts_change)
            self.chk_statuts.pack(anchor="w", pady=3)
            self.var_note = tk.BooleanVar(value=self.cfg["note"])
            self.chk_note = ttk.Checkbutton(opts, style=INTER, variable=self.var_note,
                                            text=self._texte_note(), command=self._note_change)
            self.chk_note.pack(anchor="w", pady=3)
            self.var_auto = tk.BooleanVar(value=os.path.exists(DEMARRAGE))
            ttk.Checkbutton(opts, style=INTER, variable=self.var_auto,
                            text="Synchroniser automatiquement à chaque ouverture de session"
                                 + ("" if MAC else " Windows"),
                            command=self._auto_change).pack(anchor="w", pady=3)

            bas = ttk.Frame(p)
            bas.pack(fill="x")
            self.btn_go = ttk.Button(bas, text="Télécharger et ranger", style=ACCENT, command=self._lancer)
            self.btn_go.pack(side="left")
            self.btn_annuler = ttk.Button(bas, text="Annuler", command=self._annuler, state="disabled")
            self.btn_annuler.pack(side="left", padx=(8, 0))
            ttk.Button(bas, text="Ouvrir le dossier", command=self._ouvrir).pack(side="left", padx=8)
            self.lbl_pct = ttk.Label(bas, text="", style="Doux.TLabel", width=6, anchor="e")
            self.lbl_pct.pack(side="right")
            self.barre = ttk.Progressbar(bas, mode="determinate", length=240)
            self.barre.pack(side="right", padx=(0, 6))

            self.journal = tk.Text(p, height=5, wrap="word", state="disabled", font=POLICE_JOURNAL,
                                   relief="flat", borderwidth=0, padx=10, pady=8)
            self.journal.pack(fill="both", expand=False, pady=(16, 0))

        def _construire_accueil(self):
            self.accueil = a = ttk.Frame(self, padding=(48, 36, 48, 36))
            ttk.Label(a, text="Bienvenue dans MoodleSync", style="Titre.TLabel").pack(anchor="w")
            ttk.Label(a, text="Tes fichiers Moodle, téléchargés et rangés par cours, sans tri à la main. "
                              "Trois étapes, une seule fois.",
                      style="Soustitre.TLabel", wraplength=720, justify="left").pack(anchor="w", pady=(4, 22))

            def etape(num, titre, texte):
                cadre = ttk.Frame(a, style=CARTE, padding=(18, 14))
                cadre.pack(fill="x", pady=6)
                cadre.columnconfigure(1, weight=1)
                pastille = ttk.Label(cadre, text=num, style="Etape.TLabel", width=2, anchor="center")
                pastille.grid(row=0, column=0, rowspan=3, sticky="n", padx=(0, 14))
                t = ttk.Label(cadre, text=titre, style="Section.TLabel")
                t.grid(row=0, column=1, sticky="w")
                ttk.Label(cadre, text=texte, style="Doux.TLabel", wraplength=520, justify="left").grid(
                    row=1, column=1, sticky="w", pady=(2, 0))
                return cadre, pastille, t

            c1, self.pastille1, self.titre1 = etape(
                "1", "Se connecter à Moodle",
                f"Indique l'adresse de ton Moodle (par exemple https://moodle.exemple.ch). {NAVIGATEURS} s'ouvre : connecte-toi comme d'habitude "
                "(SWITCH edu-ID, identifiant de ton établissement...), puis reviens ici. "
                "Ton mot de passe n'est jamais enregistré.")
            self.btn_co_accueil = ttk.Button(c1, text="Se connecter", style=ACCENT, command=self._connecter)
            self.btn_co_accueil.grid(row=0, column=2, rowspan=2, padx=(12, 0))
            ligne_site = ttk.Frame(c1, style=CARTE)
            ligne_site.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(10, 0))
            entree = ttk.Entry(ligne_site, textvariable=self.var_site)
            entree.pack(side="left", fill="x", expand=True)
            entree.bind("<Return>", lambda e: self._connecter())

            c2, _, _ = etape("2", "Choisir où ranger les fichiers",
                             "Un dossier par cours y sera créé, puis un sous-dossier par section.")
            ligne = ttk.Frame(c2, style=CARTE)
            ligne.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(10, 0))
            ttk.Entry(ligne, textvariable=self.var_dest).pack(side="left", fill="x", expand=True)
            ttk.Button(ligne, text="Changer…", command=self._choisir_dossier).pack(side="left", padx=(8, 0))

            ttk.Label(c2, text="Langue des dossiers et du classement", style="Doux.TLabel").grid(
                row=3, column=1, sticky="w", pady=(10, 0))
            self._combo_langue(c2).grid(row=3, column=2, sticky="e", padx=(8, 0), pady=(10, 0))

            etape("3", "Choisir tes cours",
                  "À l'écran suivant, coche les cours à suivre. Tu pourras renommer chaque dossier, "
                  f"toujours depuis MoodleSync, jamais dans {EXPLORATEUR}.")

            bas = ttk.Frame(a)
            bas.pack(fill="x", pady=(22, 0))
            self.btn_suite = ttk.Button(bas, text="Continuer vers mes cours", style=ACCENT,
                                        command=self._fin_accueil, state="disabled")
            self.btn_suite.pack(side="right")

        def _fin_accueil(self):
            self.cfg["accueil_fait"] = True
            sauver_config(self.cfg)
            self.accueil.pack_forget()
            self.principal.pack(fill="both", expand=True)

        def _connecte(self, nom):
            self.connecte = True
            self.pastille1.configure(text="✓", style="Ok.TLabel")
            self.titre1.configure(text=f"Connecté : {nom}")
            self.btn_co_accueil.configure(text="Connecté", state="disabled")
            self.btn_suite.configure(state="normal")
            self.btn_co.configure(text="Se reconnecter")

        def _molette(self, ev):
            w = self.winfo_containing(ev.x_root, ev.y_root)
            if w is not None and str(w).startswith(str(self.zone)):
                # Windows donne des multiples de 120, macOS des petits entiers.
                self.zone.yview_scroll(-ev.delta if MAC else int(-ev.delta / 120), "units")

        # ------------------------------------------------------------- outils
        def _ecrire(self, texte):
            self.journal.configure(state="normal")
            self.journal.insert("end", texte + "\n")
            self.journal.see("end")
            self.journal.configure(state="disabled")

        def _statut(self, texte, ok=None):
            self.lbl.configure(text="●  " + texte,
                               style="Ok.TLabel" if ok else ("Ko.TLabel" if ok is False else "Neutre.TLabel"))

        def _dest_changee(self):
            self.cfg["dest"] = self.var_dest.get()
            sauver_config(self.cfg)

        def _statuts_change(self):
            self.cfg["statuts"] = bool(self.var_statuts.get())
            sauver_config(self.cfg)

        def _note_change(self):
            self.cfg["note"] = bool(self.var_note.get())
            sauver_config(self.cfg)

        def _auto_change(self):
            actif = bool(self.var_auto.get())
            try:
                regler_demarrage(actif)
            except Exception as e:
                self.var_auto.set(not actif)
                messagebox.showerror("MoodleSync", f"Réglage impossible : {str(e)[:200]}")
                return
            self._ecrire("Synchronisation automatique activée : elle se fera à chaque ouverture "
                         "de session, avec un message seulement s'il y a du nouveau."
                         if actif else "Synchronisation automatique désactivée.")

        def _choisir_dossier(self):
            d = filedialog.askdirectory(title="Ou ranger les fichiers de cours ?",
                                        initialdir=self.var_dest.get() or os.path.expanduser("~"))
            if d:
                self.var_dest.set(os.path.normpath(d))

        def _ouvrir(self):
            d = self.cfg["dest"]
            if os.path.isdir(d):
                ouvrir_dossier(d)
            else:
                messagebox.showinfo("MoodleSync", "Le dossier n'existe pas encore.")

        def _pompe(self):
            try:
                while True:
                    genre, data = self.file.get_nowait()
                    if genre == "log":
                        self._ecrire(data)
                    elif genre == "statut":
                        self._statut(*data)
                    elif genre == "connecte":
                        self._connecte(data)
                    elif genre == "cours":
                        self._remplir(data)
                    elif genre == "progres":
                        i, n, texte = data
                        self.barre["maximum"] = max(n, 1)
                        self.barre["value"] = i
                        self.lbl_pct.configure(text=f"{round(100 * i / max(n, 1))} %")
                        if texte:
                            self._ecrire(f"[{i}/{n}] {texte}")
                    elif genre == "site":
                        self._site_applique(data)
                    elif genre == "fin":
                        self._termine(data)
                    elif genre == "occupe":
                        self._occupe(data)
                    elif genre == "annule":
                        self._occupe(False)
                        self._statut("Annulé avant le téléchargement.", None)
                        self._ecrire("Synchronisation annulée pendant la lecture des cours : "
                                     "rien n'a été téléchargé.")
                    elif genre == "erreur":
                        self._occupe(False)
                        self._suite_site = None
                        court = data.split("\n")[0]
                        self._statut(court if len(court) <= 80 else "Impossible, voir le message", False)
                        messagebox.showerror("MoodleSync", data)
            except queue.Empty:
                pass
            self.after(120, self._pompe)

        def _occupe(self, etat):
            self.occupe = etat
            if not etat:
                self.btn_annuler.configure(state="disabled")
            self.btn_go.configure(state="disabled" if etat else "normal")
            self.btn_co.configure(state="disabled" if etat else "normal")
            self.btn_site.configure(state="disabled" if etat else "normal")
            if not self.connecte:
                self.btn_co_accueil.configure(state="disabled" if etat else "normal")

        # ------------------------------------------------- adresse et langue
        def _texte_statuts(self):
            return f"Sous-dossiers {T['O']}, {T['C']}, {T['P']}, {T['S']}"

        def _texte_note(self):
            return f"Lister les nouveautés dans « {T['note']} »"

        def _combo_langue(self, parent):
            combo = ttk.Combobox(parent, state="readonly", width=12, textvariable=self.var_langue,
                                 values=[v["nom"] for v in LANGUES.values()])
            combo.bind("<<ComboboxSelected>>", lambda e: self._langue_change())
            return combo

        def _langue_change(self):
            code = next((k for k, v in LANGUES.items() if v["nom"] == self.var_langue.get()), "fr")
            if code == self.cfg["langue"]:
                return
            # Un nom de dossier par defaut peut dependre de la langue : on fige ceux d'aujourd'hui,
            # sinon un second dossier apparaitrait a cote du premier.
            for cid in self.liste:
                self._maj_config_cours(cid)
            self.cfg["langue"] = code
            sauver_config(self.cfg)
            appliquer_config(self.cfg)
            self.chk_statuts.configure(text=self._texte_statuts())
            self.chk_note.configure(text=self._texte_note())
            self._ecrire(f"Langue des dossiers : {LANGUES[code]['nom']}. Elle s'applique aux nouveaux "
                         "fichiers et aux nouvelles notes ; ce qui est déjà rangé ne bouge pas.")

        def _appliquer_site(self, suite=None):
            if self.occupe:
                return
            try:
                base = normaliser_site(self.var_site.get())
            except Erreur as e:
                messagebox.showerror("MoodleSync", str(e))
                return
            self.var_site.set(base)
            if base == self.cfg["site"]:
                if suite:
                    suite()
                return
            if (self.cfg["token"] or self.cfg["cours"]) and not messagebox.askyesno(
                    "MoodleSync",
                    f"Passer à {base} ?\n\nTu seras déconnecté de {self.cfg['site']} et la liste de tes "
                    "cours sera oubliée. Les fichiers déjà téléchargés ne sont pas touchés."):
                self.var_site.set(self.cfg["site"])
                return
            self._occupe(True)
            self._statut("Vérification de l'adresse...", None)
            self._suite_site = suite

            def travail():
                try:
                    verifier_site(base)
                    self.file.put(("site", base))
                except Erreur as e:
                    self.file.put(("erreur", str(e)))
                except Exception as e:
                    self.file.put(("erreur", f"Vérification impossible : {str(e)[:200]}"))
            threading.Thread(target=travail, daemon=True).start()

        def _site_applique(self, base):
            self.cfg["site"], self.cfg["token"], self.cfg["cours"] = base, "", {}
            sauver_config(self.cfg)
            appliquer_config(self.cfg)
            self.connecte = False
            for w in self.lignes.winfo_children():
                w.destroy()
            self.liste = {}
            ttk.Label(self.lignes, text="Connecte-toi pour voir tes cours.", style="Doux.TLabel").grid(
                padx=12, pady=12, sticky="w")
            self._nettoyer_palette(self.lignes)
            self.lbl_total.configure(text="")
            self.pastille1.configure(text="1", style="Etape.TLabel")
            self.titre1.configure(text="Se connecter à Moodle")
            self.btn_co.configure(text="Se connecter à Moodle")
            self.btn_suite.configure(state="disabled")
            self._occupe(False)
            self._statut("Non connecté", False)
            self._ecrire(f"Moodle : {base}")
            suite, self._suite_site = self._suite_site, None
            if suite:
                self.after(50, suite)

        # ---------------------------------------------------------- connexion
        def _connecter(self):
            try:
                base = normaliser_site(self.var_site.get())
            except Erreur as e:
                messagebox.showerror("MoodleSync", str(e))
                return
            if base != self.cfg["site"]:
                self._appliquer_site(suite=self._connecter)     # verifie l'adresse, puis revient ici
                return
            self._occupe(True)
            self._statut("Connexion en cours. Termine-la dans la fenetre du navigateur.", None)

            def travail():
                try:
                    jeton, certain = connexion_navigateur(lambda m: self.file.put(("log", m)))
                    self.cfg["token"] = jeton
                    sauver_config(self.cfg)
                    i = infos_session(jeton)
                    nom = i.get("fullname")
                    if certain and nom:
                        self.file.put(("statut", (f"Connecté : {nom}", True)))
                    else:
                        self.file.put(("log", "Ce Moodle n'a pas montré le menu utilisateur habituel : "
                                              "la connexion est déduite du jeton obtenu."))
                        self.file.put(("statut", ("Statut inconnu : connexion probable", None)))
                    self.file.put(("connecte", nom or "statut inconnu"))
                    self.file.put(("cours", resume_cours(jeton, cours_inscrits(jeton, i["userid"]),
                                                         charger_etat(self.cfg["dest"]))))
                except Erreur as e:
                    self.file.put(("erreur", str(e)))
                except Exception as e:
                    self.file.put(("erreur", f"Connexion impossible : {str(e)[:200]}"))
                finally:
                    self.file.put(("occupe", False))
            threading.Thread(target=travail, daemon=True).start()

        def _verifier(self):
            self._statut("Verification de la session...", None)

            def travail():
                try:
                    i = infos_session(self.cfg["token"])
                    nom = i.get("fullname")
                    self.file.put(("statut", (f"Connecté : {nom}" if nom else "Statut inconnu : connexion probable",
                                              True if nom else None)))
                    self.file.put(("connecte", nom or "statut inconnu"))
                    self.file.put(("cours", resume_cours(self.cfg["token"],
                                                         cours_inscrits(self.cfg["token"], i["userid"]),
                                                         charger_etat(self.cfg["dest"]))))
                except SessionExpiree:
                    self.cfg["token"] = ""
                    sauver_config(self.cfg)
                    self.file.put(("statut", ("Session expiree. Clique sur « Se connecter ».", False)))
                except Erreur as e:
                    # Reseau coupe ou Moodle en panne : le jeton reste valable, on le garde.
                    self.file.put(("statut", (f"{str(e)[:100]} Relance plus tard.", False)))
                except Exception as e:
                    self.file.put(("statut", (f"Souci reseau : {str(e)[:80]}", False)))
            threading.Thread(target=travail, daemon=True).start()

        # -------------------------------------------------------------- cours
        def _remplir(self, cours):
            for w in self.lignes.winfo_children():
                w.destroy()
            self.liste = {}
            for n, c in enumerate(cours):
                choix = self.cfg["cours"].get(str(c["id"]), {})
                dossier = nettoie_dossier(choix.get("dossier") or dossier_defaut(c))
                choisi = choix.get("choisi", True)
                d = {"id": c["id"], "nom": c["nom"], "dossier": dossier, "choisi": choisi,
                     "nb": c["nb"], "taille": c["taille"], "var": tk.BooleanVar(value=choisi)}
                d["case"] = ttk.Checkbutton(self.lignes, text=dossier, variable=d["var"],
                                            command=lambda cid=c["id"]: self._basculer(cid))
                d["case"].grid(row=n, column=0, sticky="w", padx=(10, 8), pady=3)
                d["badge"] = ttk.Label(self.lignes, text="", style="Nouveau.TLabel")
                d["badge"].grid(row=n, column=1, sticky="e", padx=8)
                self._badge(d, c.get("nouveaux", 0))
                ttk.Label(self.lignes, text=f"{c['nb']} fichier{'s' if c['nb'] != 1 else ''}",
                          style="Doux.TLabel").grid(row=n, column=2, sticky="e", padx=8)
                ttk.Label(self.lignes, text=humain(c["taille"]), style="Doux.TLabel", width=7,
                          anchor="e").grid(row=n, column=3, sticky="e", padx=8)
                crayon = ttk.Label(self.lignes, text=CRAYON, style="Crayon.TLabel", cursor="hand2")
                crayon.grid(row=n, column=4, padx=(6, 10))
                crayon.bind("<Button-1>", lambda e, cid=c["id"]: self._renommer(cid))
                self.liste[c["id"]] = d
            self._nettoyer_palette(self.lignes)     # la palette vaut aussi pour les widgets neufs
            self.zone.yview_moveto(0)
            total = sum(c["taille"] for c in cours)
            nb = sum(c["nb"] for c in cours)
            self.lbl_total.configure(text=f"{len(cours)} cours, {nb} fichiers, {humain(total)}")
            self._ecrire(f"{len(cours)} cours trouvés, {humain(total)} au total.")
            nouveaux = sum(c.get("nouveaux", 0) for c in cours if self.liste[c["id"]]["choisi"])
            if nouveaux:
                self._ecrire(f"{nouveaux} fichiers nouveaux ou republiés sur Moodle dans les cours cochés "
                             "(indiqués à côté de chaque cours).")

        def _badge(self, d, n):
            """Pastille \"3 nouveaux\" : fichiers presents sur Moodle et pas encore recuperes."""
            d["badge"].configure(text=f"{n} nouveau{'x' if n > 1 else ''}" if n else "")

        def _maj_config_cours(self, cid):
            d = self.liste[cid]
            self.cfg["cours"][str(d["id"])] = {"dossier": d["dossier"], "choisi": d["choisi"]}
            sauver_config(self.cfg)

        def _basculer(self, cid):
            d = self.liste[cid]
            d["choisi"] = bool(d["var"].get())
            self._maj_config_cours(cid)

        def _renommer(self, cid):
            d = self.liste[cid]
            if self.occupe:
                messagebox.showinfo("MoodleSync", "Attends la fin du téléchargement pour renommer un dossier.")
                return
            nouveau = simpledialog.askstring(
                "Nom du dossier",
                f"Nom du dossier pour :\n{d['nom']}\n\n"
                "Le dossier existant sera renommé sur le disque, avec tout son contenu.\n"
                f"Renomme toujours ici, jamais dans {EXPLORATEUR} : sinon MoodleSync\n"
                "ne retrouve plus les fichiers et les télécharge une seconde fois.",
                initialvalue=d["dossier"], parent=self)
            if not nouveau or nettoie_dossier(nouveau) == d["dossier"]:
                return
            nouveau, ancien = nettoie_dossier(nouveau), d["dossier"]
            # Cours ranges a l'interieur (SITE dans le dossier ITE) : leurs chemins suivent.
            prefixe = os.path.normcase(ancien) + os.sep
            inclus = [x for x in self.liste.values()
                      if x is not d and os.path.normcase(x["dossier"]).startswith(prefixe)]
            src = os.path.join(self.cfg["dest"], ancien)
            if os.path.isdir(src):
                n = sum(len(f) for _, _, f in os.walk(src))
                suivent = "".join(f"\n   {x['dossier']}" for x in inclus)
                if not messagebox.askyesno(
                        "Renommer le dossier",
                        f"Renommer le dossier sur le disque, avec ses {n} fichiers ?\n\n"
                        f"   {ancien}\n→ {nouveau}"
                        + (f"\n\nCes cours rangés à l'intérieur suivront :{suivent}" if inclus else "")
                        + "\n\nSi tu refuses, le nom reste inchangé.", parent=self):
                    return
            try:
                renommer_dossier_cours(self.cfg["dest"], ancien, nouveau)
            except Erreur as e:
                messagebox.showerror("MoodleSync", str(e), parent=self)
                return
            for x in [d] + inclus:
                x["dossier"] = nouveau + x["dossier"][len(ancien):]
                x["case"].configure(text=x["dossier"])
                self._maj_config_cours(x["id"])
            self._ecrire(f"Dossier renommé : {ancien} → {nouveau}")

        def _cocher(self, etat):
            for cid, d in self.liste.items():
                d["choisi"] = etat
                d["var"].set(etat)
                self._maj_config_cours(cid)

        # --------------------------------------------------------- traitement
        def _lancer(self):
            if not self.cfg["token"]:
                messagebox.showinfo("MoodleSync", "Commence par te connecter à Moodle.")
                return
            if not os.path.isdir(self.cfg["dest"]):
                if not messagebox.askyesno("MoodleSync",
                                           f"Le dossier\n{self.cfg['dest']}\n n'existe pas encore. "
                                           "Le creer ?"):
                    return
                try:
                    os.makedirs(self.cfg["dest"], exist_ok=True)
                except OSError as e:
                    messagebox.showerror("MoodleSync", f"Impossible de creer le dossier : {e}")
                    return
            choisis = [iid for iid, d in self.liste.items() if d["choisi"]]
            if not choisis:
                messagebox.showinfo("MoodleSync", "Aucun cours n'est coché.")
                return
            self._occupe(True)
            self.arret.clear()
            self.btn_annuler.configure(state="normal")
            self.barre["value"] = 0
            self._statut("Telechargement en cours...", None)

            def travail():
                try:
                    i = infos_session(self.cfg["token"])
                    tous = cours_inscrits(self.cfg["token"], i["userid"])
                    ids = {self.liste[x]["id"] for x in choisis}
                    retenus = [c for c in tous if c["id"] in ids]
                    liens = []
                    items = collecte(self.cfg["token"], retenus, self.cfg,
                                     lambda m: self.file.put(("log", m)), liens=liens,
                                     arreter=self.arret.is_set)
                    self.file.put(("log", f"{len(items)} fichiers et {len(liens)} liens a examiner."))
                    r = telecharger(items, self.cfg,
                                    dire=lambda m: self.file.put(("log", m)),
                                    progres=lambda a, b, t: self.file.put(("progres", (a, b, t))),
                                    arreter=self.arret.is_set)
                    # Annule : les liens attendront la prochaine synchronisation, la note liste ce
                    # qui est deja arrive.
                    r["liste_liens"] = [] if r["annule"] else ecrire_liens(
                        liens, self.cfg["dest"], dire=lambda m: self.file.put(("log", m)))
                    r["note"] = ecrire_note(r) if self.cfg["note"] else None
                    self.file.put(("fin", r))
                except Annule:
                    self.file.put(("annule", None))
                except Erreur as e:
                    self.file.put(("erreur", str(e)))
                except Exception as e:
                    self.file.put(("erreur", f"Erreur pendant le telechargement : {str(e)[:200]}"))
            threading.Thread(target=travail, daemon=True).start()

        def _annuler(self):
            self.arret.set()
            self.btn_annuler.configure(state="disabled")
            self._statut("Annulation : fin du fichier en cours...", None)

        def _termine(self, r):
            self._occupe(False)
            for d in self.liste.values():
                if d["choisi"]:
                    self._badge(d, r["restants"].get(d["id"], 0))
            if r["annule"]:
                self._statut(f"Annulé : {r['neufs']} nouveaux fichiers rangés avant l'arrêt.", None)
            else:
                self._statut(f"Terminé : {r['neufs']} nouveaux fichiers, {r['maj']} mis à jour.", True)
            self._ecrire("")
            if r["annule"]:
                self._ecrire("Synchronisation annulée. Les fichiers déjà téléchargés restent rangés ; "
                             "le reste viendra à la prochaine synchronisation.")
            for ligne in nouveautes_par_cours(r):
                self._ecrire(f"  {ligne}")
            self._ecrire(f"Nouveaux : {r['neufs']}")
            self._ecrire(f"Mis à jour (ancienne version conservée) : {r['maj']}")
            self._ecrire(f"Nouveaux liens : {len(r['liste_liens'])} (dans « {T['liens']} » de chaque section)")
            self._ecrire(f"Déjà présents, ignorés : {r['doublons']}")
            if r["erreurs"]:
                self._ecrire(f"Échecs : {r['erreurs']}")
            self._ecrire(f"Rangement : {r['dest']}")
            if r.get("note"):
                self._ecrire(f"Liste des nouveautés : {r['note']}")
            if not r["annule"] and (r["neufs"] or r["maj"] or r["liste_liens"]):
                messagebox.showinfo("MoodleSync",
                                    f"{r['neufs']} nouveaux fichiers, {r['maj']} mis à jour et "
                                    f"{len(r['liste_liens'])} nouveaux liens, rangés dans\n{r['dest']}\n\n"
                                    + "\n".join(nouveautes_par_cours(r)[:8]))

    Fenetre().mainloop()


# ------------------------------------------------------------------ mode auto
def mode_auto(demarrage=False):
    """Execution sans fenetre : python moodle_sync.py --auto

    Avec --demarrage (lancement a l'ouverture de session) : on laisse au reseau le temps
    d'arriver, on journalise dans journal.txt (dossier APP_DIR), et on ne previent
    l'utilisateur que s'il y a du nouveau ou si la session a expire.
    """
    if demarrage:
        os.makedirs(APP_DIR, exist_ok=True)
        if os.path.exists(JOURNAL) and os.path.getsize(JOURNAL) > 200_000:
            os.replace(JOURNAL, JOURNAL + ".ancien")
        sys.stdout = sys.stderr = open(JOURNAL, "a", encoding="utf-8")
        print(f"\n--- {time.strftime('%d.%m.%Y %H:%M')}")
    cfg = charger_config()
    appliquer_config(cfg)
    if not cfg["token"]:
        print("Aucun jeton. Lance l'interface et connecte-toi une fois.")
        if demarrage:
            prevenir("MoodleSync n'est pas connecté. Ouvre MoodleSync pour te connecter.")
        return 1
    essais = 6 if demarrage else 1
    for n in range(essais):
        try:
            i = infos_session(cfg["token"])
            print(f"Connecte : {i['fullname']}")
            liens = []
            items = collecte(cfg["token"], cours_inscrits(cfg["token"], i["userid"]), cfg, liens=liens)
            break
        except SessionExpiree as e:
            print(e)
            if demarrage:
                prevenir("La session Moodle a expiré. Ouvre MoodleSync pour te reconnecter.")
            return 1
        except Erreur as e:
            print(e)
            if n == essais - 1:
                return 1
            time.sleep(30)
    print(f"{len(items)} fichiers et {len(liens)} liens examines, dossier cible : {cfg['dest']}")
    r = telecharger(items, cfg, dire=print)
    r["liste_liens"] = ecrire_liens(liens, cfg["dest"], dire=print)
    print(f"nouveaux={r['neufs']} mis_a_jour={r['maj']} deja_presents={r['doublons']} "
          f"echecs={r['erreurs']} nouveaux_liens={len(r['liste_liens'])}")
    note = ecrire_note(r) if cfg["note"] else None
    if note:
        print(f"Note : {note}")
    if demarrage and (r["neufs"] or r["maj"] or r["liste_liens"]):
        titre = (f"Moodle : {r['neufs']} nouveaux fichiers, {r['maj']} mis à jour, "
                 f"{len(r['liste_liens'])} nouveaux liens")
        lignes = nouveautes_par_cours(r)
        # Notification du systeme, discrete ; la fenetre d'autrefois seulement si elle echoue.
        if not notifier(titre, lignes):
            prevenir(titre + ".\n\n" + "\n".join(lignes[:8])
                     + (f"\n\nLa liste est dans « {T['note']} »." if note else ""), ouvrir=r["dest"])
    return 0


if __name__ == "__main__":
    if "--auto" in sys.argv:
        sys.exit(mode_auto(demarrage="--demarrage" in sys.argv))
    lancer_interface()
