#!/usr/bin/env python3
"""MoodleSync, marque dans les metadonnees d'un PDF cherchable (contrat 2.2).

Module feuille : il n'importe rien d'autre du paquet. La marque doit etre lisible par
`moteur.py` (etape 4 de `deja_present`, contrat 3.3) sans que `moteur` importe `ocr`, qui
importe deja `moteur` : c'est l'ecart 6, resolu par ce module. `ocr.py` importe les noms
d'ici et reexporte `lire_marque` : `ocr.lire_marque(chemin)` reste l'entree publique du
contrat 2.2, aucun appelant ni test ne change.
"""
import json, logging

CLE_MARQUE = "/MoodleSyncGenere"  # cle de /Info (2.2)


def _entier_vrai(valeur):
    return isinstance(valeur, int) and not isinstance(valeur, bool)


def _marque_valide(texte):
    """Le dict de la marque si `texte` est un JSON de moins de 1 Ko, de version 1 et complet (2.2), sinon None."""
    if not isinstance(texte, str) or len(texte.encode("utf-8")) >= 1024:
        return None
    try:
        marque = json.loads(texte)
    except ValueError:
        return None
    if not isinstance(marque, dict) or not _entier_vrai(marque.get("v")) or marque["v"] != 1:
        return None
    if not (isinstance(marque.get("url"), str) and marque["url"] and _entier_vrai(marque.get("t"))
            and _entier_vrai(marque.get("taille_source")) and marque["taille_source"] >= 0
            and isinstance(marque.get("empreinte_source"), str) and marque["empreinte_source"]
            and _entier_vrai(marque.get("pages")) and marque["pages"] >= 1):
        return None
    return marque


def _marque_du_lecteur(lecteur):
    try:
        info = lecteur.metadata
        return _marque_valide(info.get(CLE_MARQUE) if info else None)
    except Exception:
        return None


def lire_marque(chemin):
    """La marque `/Info /MoodleSyncGenere` d'un PDF (2.2), ou None : cle absente, JSON illisible, bloc incomplet,
    version inconnue, fichier qui n'est pas un PDF. Ne leve jamais."""
    try:
        import pypdf
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        lecteur = pypdf.PdfReader(chemin)
        if lecteur.is_encrypted and not lecteur.decrypt(""):
            return None
        return _marque_du_lecteur(lecteur)
    except Exception:
        return None
