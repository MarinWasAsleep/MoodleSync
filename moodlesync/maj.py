"""Mise a jour de MoodleSync : version plus recente sur GitHub, telechargement verifie, remplacement de l'application.

Principe :
  1. chercher() lit la derniere Release publiee du depot (l'API ne renvoie ni brouillon ni pre-version) ;
  2. telecharger() recupere le fichier de la plateforme, seulement depuis des hotes GitHub en HTTPS, et le compare a
     l'empreinte SHA-256 que GitHub publie pour chaque fichier de la Release : sans empreinte, rien n'est installe ;
  3. remplacer() met le nouveau fichier a la place de l'ancien. Un .exe en cours d'execution ne peut pas etre ecrase
     sous Windows, mais il peut etre renomme : l'ancien passe en "MoodleSync.exe.ancien" (supprime au demarrage
     suivant), le nouveau prend sa place. Sous macOS, meme principe avec le dossier MoodleSync.app. Au moindre
     echec, l'ancien est remis en place.

Aucune interface ici : utilise par application.py (fenetre) et par `--maj` (sans fenetre).
"""
import os, re, sys, json, time, hashlib, shutil, tempfile, subprocess, urllib.request, urllib.error, urllib.parse

from . import VERSION, moteur as ms

DEPOT = "MarinWasAsleep/MoodleSync"
URL_API = f"https://api.github.com/repos/{DEPOT}/releases/latest"
URL_PAGE = f"https://github.com/{DEPOT}/releases/latest"
FICHIERS = {"win": "MoodleSync.exe", "mac": "MoodleSync-macOS.zip"}     # noms des fichiers de la Release
SUFFIXE_ANCIEN = ".ancien"
SUFFIXE_NOUVEAU = ".nouveau"
TAILLE_MAX = 250 * 1024 * 1024
DELAI_VERIFICATION = 12 * 3600                                          # secondes entre deux recherches automatiques
RE_EMPREINTE = re.compile(r"sha256:([0-9a-f]{64})")


# ------------------------------------------------------------------ versions
def version_tuple(texte):
    """"v2.4" ou "2.4.1" -> (2, 4) ou (2, 4, 1) ; None si ce n'est pas un numero de version."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+){0,3})", str(texte or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def plus_recente(distante, locale=VERSION):
    """Vrai si `distante` est strictement plus recente que `locale` ("2.4" > "2.3" ; "2.3.0" = "2.3")."""
    a, b = version_tuple(distante), version_tuple(locale)
    if not a or not b:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def plateforme():
    """"win", "mac", ou None (Linux : pas d'executable publie)."""
    if ms.MAC:
        return "mac"
    return "win" if sys.platform.startswith("win") else None


# ------------------------------------------------------------------ reseau (GitHub seulement)
def hote_autorise(url):
    """HTTPS vers github.com ou un domaine de contenu GitHub (les fichiers d'une Release y sont rediriges)."""
    p = urllib.parse.urlparse(str(url or ""))
    h = (p.hostname or "").lower()
    return p.scheme == "https" and (h in ("github.com", "api.github.com") or h.endswith(".githubusercontent.com"))


class _Redirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not hote_autorise(newurl):
            raise urllib.error.URLError("redirection vers un hôte qui n'est pas GitHub, refusée")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def ouvrir(url, timeout=30):
    """Ouvre une URL GitHub (jamais un autre hote, redirections comprises)."""
    if not hote_autorise(url):
        raise ms.Erreur("Adresse de mise à jour refusée : elle ne pointe pas vers GitHub.")
    req = urllib.request.Request(url, headers={"User-Agent": f"MoodleSync/{VERSION}",
                                               "Accept": "application/vnd.github+json, application/octet-stream"})
    return urllib.request.build_opener(_Redirection).open(req, timeout=timeout)


def lire_json(url):
    with ouvrir(url, timeout=20) as r:
        return json.loads(r.read(2_000_000).decode("utf-8"))


def _fichier_verifiable(a):
    """Description d'un fichier de la Release s'il est installable en confiance (hote GitHub, taille et empreinte
    connues), sinon None."""
    try:
        taille = int(a["size"])
        m = RE_EMPREINTE.fullmatch(str(a.get("digest") or ""))
        if m and 0 < taille <= TAILLE_MAX and hote_autorise(a["browser_download_url"]):
            return {"nom": a["name"], "url": a["browser_download_url"], "taille": taille, "sha256": m.group(1)}
    except (KeyError, TypeError, ValueError):
        pass
    return None


def chercher(lire=lire_json):
    """Derniere version publiee : {courante, version, disponible, page, fichier}. `fichier` vaut None si la Release n'a
    pas de fichier verifiable pour cette plateforme (l'installation automatique est alors refusee).
    Leve ms.Erreur si GitHub est injoignable."""
    try:
        r = lire(URL_API)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise ms.Erreur("GitHub limite le nombre de requêtes depuis ton réseau : réessaie dans une heure.")
        raise ms.Erreur(f"GitHub a répondu une erreur ({e.code}) : réessaie plus tard.")
    except (urllib.error.URLError, OSError, ValueError):
        raise ms.Erreur("Impossible de joindre GitHub : vérifie ta connexion Internet.")
    version = str(r.get("tag_name") or "").lstrip("v")
    if version_tuple(version) is None or r.get("draft") or r.get("prerelease"):
        raise ms.Erreur("La dernière version publiée sur GitHub est illisible : réessaie plus tard.")
    page = r.get("html_url") if hote_autorise(r.get("html_url")) else URL_PAGE
    nom = FICHIERS.get(plateforme())
    fichier = next((_fichier_verifiable(a) for a in r.get("assets") or [] if a.get("name") == nom), None)
    return {"courante": VERSION, "version": version, "disponible": plus_recente(version), "page": page,
            "fichier": fichier}


# ------------------------------------------------------------------ ce qui peut etre remplace
def cible():
    """(chemin de l'application a remplacer, None) ou (None, raison). Seul un executable compile, dans un dossier
    ou l'on peut ecrire, se remplace tout seul."""
    if not getattr(sys, "frozen", False):
        return None, "MoodleSync est lancé depuis le code source : mets-le à jour avec git pull."
    p = plateforme()
    if p == "win":
        chemin = os.path.abspath(sys.executable)
    elif p == "mac":
        chemin = os.path.abspath(sys.executable)
        while chemin and not chemin.endswith(".app") and os.path.dirname(chemin) != chemin:
            chemin = os.path.dirname(chemin)
        if not chemin.endswith(".app"):
            return None, "L'application n'est pas dans un dossier .app : télécharge la nouvelle version à la main."
        if "AppTranslocation" in chemin:
            return None, "L'application tourne depuis un emplacement temporaire de macOS : place-la dans Applications, relance-la, puis réessaie."
    else:
        return None, "Pas d'exécutable publié pour ce système."
    if not os.access(os.path.dirname(chemin), os.W_OK):
        return None, "Le dossier de l'application n'est pas modifiable (droits) : télécharge la nouvelle version à la main."
    return chemin, None


# ------------------------------------------------------------------ telechargement verifie
def telecharger(fichier, dest, progres=None):
    """Telecharge `fichier` (voir chercher) vers `dest`, en verifiant taille et SHA-256 avant de le poser.
    `progres(octets, total)` est appele regulierement. Leve ms.Erreur ; ne laisse rien derriere lui en cas d'echec."""
    partiel = dest + ".part"
    h, lus = hashlib.sha256(), 0
    try:
        with ouvrir(fichier["url"], timeout=60) as r, open(partiel, "wb") as f:
            while True:
                bloc = r.read(256 * 1024)
                if not bloc:
                    break
                lus += len(bloc)
                if lus > fichier["taille"]:
                    break
                h.update(bloc)
                f.write(bloc)
                if progres:
                    progres(lus, fichier["taille"])
        if lus != fichier["taille"]:
            raise ms.Erreur("Le téléchargement est incomplet ou de taille inattendue : mise à jour annulée, rien n'a été modifié.")
        if h.hexdigest() != fichier["sha256"]:
            raise ms.Erreur("Le fichier téléchargé ne correspond pas à l'empreinte publiée par GitHub : mise à jour annulée, rien n'a été modifié.")
        os.replace(partiel, dest)
    except (urllib.error.URLError, OSError) as e:
        raise ms.Erreur(f"Le téléchargement a échoué ({type(e).__name__}) : vérifie ta connexion, rien n'a été modifié.")
    finally:
        _supprimer(partiel)


def _supprimer(chemin):
    try:
        if os.path.isdir(chemin) and not os.path.islink(chemin):
            shutil.rmtree(chemin)
        elif os.path.lexists(chemin):
            os.remove(chemin)
    except OSError:
        pass


# ------------------------------------------------------------------ remplacement
def remplacer(chemin, neuf):
    """Met `neuf` (fichier ou dossier, sur le meme disque) a la place de `chemin`, meme si `chemin` est en cours
    d'execution : l'ancien est renomme en `chemin + SUFFIXE_ANCIEN`, jamais ecrase. Echec : l'ancien est remis."""
    ancien = chemin + SUFFIXE_ANCIEN
    _supprimer(ancien)                                  # reste d'une mise a jour precedente
    if os.path.lexists(ancien):
        raise ms.Erreur(f"« {os.path.basename(ancien)} » est encore utilisé (ferme les autres fenêtres de MoodleSync) : mise à jour annulée.")
    try:
        os.rename(chemin, ancien)
    except OSError as e:
        raise ms.Erreur(f"L'application ne peut pas être remplacée ({type(e).__name__}) : mise à jour annulée, rien n'a été modifié.")
    try:
        os.rename(neuf, chemin)
    except OSError as e:
        try:
            os.rename(ancien, chemin)
        except OSError:
            raise ms.Erreur(f"Remplacement impossible, et l'ancienne version est restée sous le nom « {os.path.basename(ancien)} » : renomme-la à la main.")
        raise ms.Erreur(f"Le remplacement a échoué ({type(e).__name__}) : l'ancienne version est remise en place.")
    _supprimer(ancien)                                  # sous Windows, l'executable lance reste verrouille : sans effet


def nettoyer(chemin=None):
    """Efface l'ancienne version laissee par la mise a jour precedente (a appeler au demarrage)."""
    chemin = chemin or cible()[0]
    if chemin:
        _supprimer(chemin + SUFFIXE_ANCIEN)
        _supprimer(chemin + SUFFIXE_NOUVEAU)


def _installer_mac(archive, app):
    parent = os.path.dirname(app)
    tmp = tempfile.mkdtemp(prefix=".MoodleSync-maj-", dir=parent)       # meme disque que l'application : renommage atomique
    try:
        try:
            subprocess.run(["ditto", "-x", "-k", archive, tmp], check=True, timeout=300, capture_output=True)
        except (subprocess.SubprocessError, OSError):
            raise ms.Erreur("L'archive téléchargée n'a pas pu être décompressée : mise à jour annulée, rien n'a été modifié.")
        neuf = os.path.join(tmp, "MoodleSync.app")
        if not os.path.isfile(os.path.join(neuf, "Contents", "MacOS", "MoodleSync")):
            raise ms.Erreur("L'archive téléchargée ne contient pas l'application attendue : mise à jour annulée.")
        remplacer(app, neuf)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def installer(info, chemin, progres=None):
    """Telecharge (verifie) et remplace `chemin`. `info` vient de chercher(). Leve ms.Erreur."""
    if not info.get("fichier"):
        raise ms.Erreur("Cette version n'a pas de fichier vérifiable (empreinte absente) : télécharge-la à la main.")
    if plateforme() == "mac":
        with tempfile.TemporaryDirectory() as d:
            archive = os.path.join(d, FICHIERS["mac"])
            telecharger(info["fichier"], archive, progres)
            _installer_mac(archive, chemin)
        return
    nouveau = chemin + SUFFIXE_NOUVEAU
    try:
        telecharger(info["fichier"], nouveau, progres)
        with open(nouveau, "rb") as f:
            if f.read(2) != b"MZ":
                raise ms.Erreur("Le fichier téléchargé n'est pas un exécutable Windows : mise à jour annulée.")
        remplacer(chemin, nouveau)
    finally:
        _supprimer(nouveau)


def relancer(chemin):
    """Lance la nouvelle version, sans attendre. A appeler une fois la fenetre actuelle fermee."""
    if plateforme() == "mac":
        subprocess.Popen(["open", "-n", chemin], close_fds=True)
        return
    # PyInstaller : sans cette variable, le fils reutiliserait le dossier temporaire du pere (qui disparait a sa fermeture).
    env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    subprocess.Popen([chemin], close_fds=True, env=env, cwd=os.path.dirname(chemin),
                     creationflags=0x00000008 | 0x00000200)        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


# ------------------------------------------------------------------ cache de la recherche automatique
def verification_recente(cache, maintenant=None):
    """Vrai si la derniere recherche date de moins de DELAI_VERIFICATION secondes (cache : {"verifie": epoch, ...})."""
    try:
        return 0 <= (maintenant or time.time()) - float(cache["verifie"]) < DELAI_VERIFICATION
    except (KeyError, TypeError, ValueError):
        return False


# ------------------------------------------------------------------ ligne de commande : --maj [--relancer]
SORTIES = {"installee": 0, "a_jour": 10, "impossible": 11, "sans_fichier": 12, "erreur": 1}


def cli(relancer_apres=False, dire=print):
    """Met a jour sans fenetre. Code de sortie : 0 installee, 10 deja a jour, 11 pas remplacable ici,
    12 pas de fichier verifiable, 1 erreur."""
    chemin, raison = cible()
    if not chemin:
        dire(raison)
        return SORTIES["impossible"]
    try:
        info = chercher()
        if not info["disponible"]:
            dire(f"Déjà à jour (version {VERSION}).")
            return SORTIES["a_jour"]
        if not info["fichier"]:
            dire(f"La version {info['version']} n'a pas de fichier vérifiable : {info['page']}")
            return SORTIES["sans_fichier"]
        dire(f"Installation de la version {info['version']}...")
        installer(info, chemin)
    except ms.Erreur as e:
        dire(str(e))
        return SORTIES["erreur"]
    dire(f"Version {info['version']} installée.")
    if relancer_apres:
        relancer(chemin)
    return SORTIES["installee"]
