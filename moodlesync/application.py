"""Fenetre de MoodleSync : l'interface HTML (interface/index.html) dans une fenetre native (pywebview).

Ce fichier ne fait que relier la page aux moteurs : moteur.py (synchronisation), semaine.py et
seances.py (Ma semaine, lecture seule sur Moodle), suivi.py (cases, temps, echeances, changements).
Chaque methode publique de Api est appelable depuis la page (window.pywebview.api.<nom>) et renvoie
du JSON ; les erreurs sont des phrases lisibles ({"erreur": ...}), le detail technique va dans erreurs.txt.
"""
import os, sys, json, threading

from . import moteur as ms, semaine as m, seances as sc, suivi as S
from .api_horaire import ApiHoraire

REGLAGES_SEMAINE = {"active": bool, "jours": int, "vitesse": int, "pages": bool, "dossier": str,
                    "export_md": bool, "theme": str}
SESSION_EXPIREE = "La session Moodle a expiré. Reconnecte-toi (onglet Synchroniser), puis réessaie."


def dossier_interface():
    """Dossier de la page : dans le paquet, ou dans le dossier temporaire de l'executable (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None)
    return os.path.join(base, "interface") if base else os.path.join(os.path.dirname(os.path.abspath(__file__)), "interface")


def proteger(action):
    """Decorateur : toute exception devient {"erreur": phrase lisible}."""
    def deco(f):
        def g(*a, **k):
            try:
                return f(*a, **k)
            except ms.SessionExpiree:
                return {"erreur": SESSION_EXPIREE}
            except ms.Erreur as e:
                return {"erreur": str(e)}
            except Exception as e:
                return {"erreur": ms.message_erreur(e, action)}
        g.__name__, g.__doc__ = f.__name__, f.__doc__
        return g
    return deco


class Api(ApiHoraire):
    """Fonctions appelees par la page. Les attributs prefixes de _ ne sont pas exposes a la page."""

    def __init__(self):
        self._fenetre = None
        self._semaine = None                         # cree a la demande : Ma semaine peut etre desactivee

    # -- outils internes
    def _js(self, fonction, valeur):
        if self._fenetre is not None:
            try:
                self._fenetre.evaluate_js(f"window.{fonction} && window.{fonction}({json.dumps(valeur)})")
            except Exception:
                pass

    def _sem(self):
        if self._semaine is None:
            self._semaine = S.Semaine()
        return self._semaine

    def _general_semaine(self):
        p = S.prefs()
        out = {"prefs": p, "profils": [{"nom": n, "vitesse": v, "origine": o} for n, v, o in sc.PROFILS],
               "vitesse_mesuree": None}
        if p["active"]:
            out["vitesse_mesuree"] = S.vitesse_mesuree(self._sem().suivi)
        return out

    # ================================================================ Ma semaine
    @proteger("Ma semaine")
    def demarrer(self):
        """Reglages et derniere analyse gardee (affichee tout de suite, avant l'actualisation)."""
        g = self._general_semaine()
        return {**g, "donnees": self._sem().derniere() if g["prefs"]["active"] else None}

    @proteger("Actualisation")
    def actualiser(self):
        """Relit Moodle (20 a 60 secondes)."""
        r = self._sem().actualiser(lambda t: self._js("progression", t))
        return {**self._general_semaine(), **r}

    @proteger("Suivi")
    def cocher(self, ident, fait, pages=None):
        self._sem().cocher(ident, fait, pages)
        return {"ok": True}

    @proteger("Suivi")
    def noter_temps(self, ident, texte, pages=None):
        return self._sem().noter_temps(ident, texte, pages)

    @proteger("Échéances")
    def ajouter_echeance(self, date, heure, cours, nom):
        return self._sem().ajouter_echeance(date, heure, cours, nom)

    @proteger("Échéances")
    def supprimer_echeance(self, ident):
        return self._sem().supprimer_echeance(ident)

    @proteger("Changements")
    def changements_vus(self):
        self._sem().changements_vus()
        return {"ok": True}

    @proteger("Réglages")
    def regler(self, cle, valeur):
        if cle not in REGLAGES_SEMAINE:
            return {"erreur": f"Réglage inconnu : {cle}"}
        try:
            valeur = REGLAGES_SEMAINE[cle](valeur)
        except (TypeError, ValueError):
            return {"erreur": "Valeur invalide."}
        if cle == "jours" and not 1 <= valeur <= 120 or cle == "vitesse" and not 1 <= valeur <= 80:
            return {"erreur": "Valeur hors limites."}
        m.sauver_prefs({**m.charger_prefs(), cle: valeur})
        return self._general_semaine()

    @proteger("Réglages")
    def choisir_dossier(self):
        import webview
        r = self._fenetre.create_file_dialog(webview.FOLDER_DIALOG, directory=S.prefs()["dossier"])
        if r:
            return self.regler("dossier", os.path.normpath(r[0] if isinstance(r, (list, tuple)) else r))
        return self._general_semaine()

    @proteger("Audit")
    def audit(self):
        b = m.analyser_audit(lambda t: self._js("progression", t))
        avert = None
        try:
            m.ecrire(os.path.join(S.prefs()["dossier"], m.FICHIER_AUDIT), m.rendre_audit(b))
        except ms.Erreur as e:
            avert = str(e)
        except OSError as e:
            avert = ms.message_erreur(e, "Écriture de l'audit")
        return {"bilan": b, "avertissement": avert}

    @proteger("Ouverture")
    def ouvrir(self, quoi):
        """Ouvre le dossier, Ma semaine.md ou l'audit."""
        dossier = S.prefs()["dossier"]
        if quoi == "dossier":
            ms.ouvrir_dossier(dossier)
            return {"ok": True}
        nom = {"md": m.FICHIER, "audit": m.FICHIER_AUDIT}.get(quoi)
        chemin = os.path.join(dossier, nom) if nom else None
        if not chemin or not os.path.exists(chemin):
            return {"erreur": "Fichier pas encore créé : actualise d'abord."}
        return {"ok": m.ouvrir_document(chemin) is not None}


def lancer(titre="MoodleSync"):
    """Ouvre la fenetre. Leve ImportError si pywebview manque, une autre exception si le moteur web manque."""
    import webview
    api = Api()
    fenetre = webview.create_window(titre, url=os.path.join(dossier_interface(), "index.html"), js_api=api,
                                    width=1280, height=880, min_size=(380, 560), background_color="#f4f4f2")
    api._fenetre = fenetre
    stockage = os.path.join(ms.APP_DIR, "webview")
    verif = os.environ.get("MOODLESYNC_VERIF")
    if not verif:
        webview.start(private_mode=False, storage_path=stockage)
        return

    # Verification sans intervention (CI, essais) : attend que la page ait fini de charger (ou affiche une
    # erreur), ecrit ce qu'elle montre (window.etatVerification()) dans le fichier `verif`, puis ferme.
    def verifier():
        import time
        etat = "délai dépassé"
        for _ in range(int(os.environ.get("MOODLESYNC_VERIF_DELAI", "180"))):
            time.sleep(1)
            try:
                etat = fenetre.evaluate_js("window.etatVerification ? JSON.stringify(window.etatVerification()) : ''")
            except Exception as e:
                etat = f"evaluate_js : {e!r}"
                continue
            if etat and '"pret":true' in etat:
                break
        with open(verif, "w", encoding="utf-8") as f:
            f.write(str(etat))
        fenetre.destroy()
    webview.start(verifier, private_mode=False, storage_path=stockage)
