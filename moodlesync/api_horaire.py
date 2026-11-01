"""Fonctions de la page pour l'horaire des cours (import .ics, choix des groupes, rapprochement avec Moodle).

Melangees a application.Api : appelables depuis la page (window.pywebview.api.<nom>). Chaque methode
renvoie l'etat de l'ecran Horaire (horaire.etat_page()) ou {"erreur": phrase lisible}. self._fenetre est la
fenetre pywebview, posee par application.lancer().
"""
from . import moteur as ms, horaire


def _proteger(action):
    def deco(f):
        def g(*a, **k):
            try:
                return f(*a, **k)
            except ms.SessionExpiree:
                return {"erreur": "La session Moodle a expiré. Reconnecte-toi (onglet Synchroniser), puis réessaie."}
            except ms.Erreur as e:
                return {"erreur": str(e)}
            except Exception as e:
                return {"erreur": ms.message_erreur(e, action)}
        g.__name__, g.__doc__ = f.__name__, f.__doc__
        return g
    return deco


class ApiHoraire:
    @_proteger("Horaire")
    def horaire_etat(self):
        """Etat de l'ecran Horaire."""
        return horaire.etat_page()

    @_proteger("Import de l'horaire")
    def horaire_importer_fichier(self):
        """Ouvre la boite de dialogue native, importe le .ics choisi. {"annule": True} si rien n'est choisi."""
        import webview
        r = self._fenetre.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                             file_types=("Calendrier (*.ics)", "Tous les fichiers (*.*)"))
        if not r:
            return {**horaire.etat_page(), "annule": True}
        chemin = r[0] if isinstance(r, (list, tuple)) else r
        return horaire.etat_page(horaire.importer_fichier(chemin))

    @_proteger("Abonnement à l'horaire")
    def horaire_abonnement(self, adresse):
        """Enregistre l'adresse d'abonnement (https:// ou webcal://) et importe ; adresse vide = abonnement retire."""
        return horaire.etat_page(horaire.regler_abonnement(adresse))

    @_proteger("Horaire")
    def horaire_groupe(self, cours_id, groupe_id, suivi):
        """Coche ou decoche un groupe suivi."""
        return horaire.etat_page(horaire.choisir_groupe(cours_id, groupe_id, suivi))

    @_proteger("Horaire")
    def horaire_confirmer(self, cours_id, cid):
        """Confirme le cours Moodle d'un cours du .ics : identifiant Moodle, "aucun", ou null pour annuler."""
        return horaire.etat_page(horaire.confirmer(cours_id, cid if cid not in ("", None) else None))

    @_proteger("Lecture des cours Moodle")
    def horaire_cours_moodle(self):
        """Relit la liste de tes cours dans Moodle (lecture seule), pour les propositions de rapprochement."""
        cfg = ms.charger_config()
        ms.appliquer_config(cfg)
        if not cfg.get("token"):
            raise ms.Erreur("Pas encore connecté à Moodle : connecte-toi d'abord (onglet Synchroniser).")
        cours = ms.cours_inscrits(cfg["token"], ms.infos_session(cfg["token"])["userid"])
        return horaire.etat_page(horaire.noter_cours_moodle(cours))
