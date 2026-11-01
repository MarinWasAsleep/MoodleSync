"""Lancement : python -m moodlesync (fenetre), python -m moodlesync --auto [--demarrage] (sans fenetre)."""
import sys


def main():
    from . import moteur as ms
    if "--auto" in sys.argv:
        sys.exit(ms.mode_auto(demarrage="--demarrage" in sys.argv))
    try:
        from . import application
        application.lancer()
    except Exception as e:                           # pywebview absent, ou moteur web absent ou en panne
        ms.message_erreur(e, "Ouverture de la fenêtre")
        ms.prevenir(ms.TEXTE_FENETRE_IMPOSSIBLE)
        sys.exit(1)


if __name__ == "__main__":
    main()
