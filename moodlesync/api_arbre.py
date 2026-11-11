"""Arborescence des textes : mixin de l'API de la page (contrat 4.3 et 4.5 de docs/refonte-textes/contrat.md).

Melange a `application.Api` comme `ApiTextes`, il ne definit aucun `__init__` : l'enregistrement du mixin est fait
par R4. Chaque methode rend un `dict` ; une erreur rend `{"erreur": phrase lisible}` seule et aucune exception ne
sort vers la fenetre.

Ce module lit le coffre (jamais un PDF) et ouvre l'explorateur par une liste d'arguments : aucun shell.
"""
import os
import subprocess
import sys

from . import textes_arbre
from .api_horaire import _proteger
from .api_textes import ApiTextes, _message

ACTION = "Textes des cours"


def commande_afficher(chemin, plateforme=None):
    """Liste d'arguments qui montre `chemin` dans l'explorateur du systeme (contrat 4.5).

    Windows selectionne le fichier (`explorer /select,<chemin>`), macOS aussi (`open -R <chemin>`), les autres
    systemes ouvrent le dossier parent (`xdg-open`), sans promesse. Un dossier est ouvert lui-meme.
    """
    plateforme = sys.platform if plateforme is None else plateforme
    dossier = os.path.isdir(chemin)
    if plateforme.startswith("win"):
        return ["explorer", chemin] if dossier else ["explorer", "/select," + chemin]
    if plateforme == "darwin":
        return ["open", chemin] if dossier else ["open", "-R", chemin]
    if dossier:
        return ["xdg-open", chemin]
    return ["xdg-open", os.path.dirname(chemin) or os.curdir]


class ApiArbre:
    """Mixin de l'API : `ocr_arbre` et `ocr_afficher` (4.3 et 4.5)."""

    def _arbre_confiner(self, dest, chemin, cfg):
        """Confinement de `ApiTextes._ocr_confiner`, reemploye tel quel : une seule regle pour tous les chemins."""
        return ApiTextes._ocr_confiner(self, dest, chemin, cfg)

    @_proteger(ACTION)
    def ocr_arbre(self):
        """Arbre des documents du coffre (4.3). Lecture seule : n'ecrit rien, ne lance rien."""
        cfg = self._cfg()
        return textes_arbre.construire_arbre(cfg.get("dest") or "", cfg)

    @_proteger(ACTION)
    def ocr_afficher(self, chemin):
        """Montre le document (ou son dossier) dans l'explorateur (4.5)."""
        cfg = self._cfg()
        dest = cfg.get("dest") or ""
        reel = self._arbre_confiner(dest, chemin, cfg) if dest else None
        if not reel or not os.path.exists(reel):
            return {"erreur": _message("ouverture_refusee")}
        try:
            subprocess.Popen(commande_afficher(reel), shell=False)
        except (OSError, ValueError):
            return {"erreur": _message("ouverture_refusee")}
        return {"ok": True}
