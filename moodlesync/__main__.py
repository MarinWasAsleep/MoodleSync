"""Lancement : python -m moodlesync (fenetre), --auto [--demarrage] (synchronisation sans fenetre),
--maj [--relancer] (mise a jour sans fenetre)."""
import sys


def main():
    from . import moteur as ms
    try:
        from . import maj
        maj.nettoyer()                               # efface l'ancienne version laissee par une mise a jour
    except Exception:
        pass
    if "--auto" in sys.argv:
        sys.exit(ms.mode_auto(demarrage="--demarrage" in sys.argv))        # jamais de recherche de mise a jour ici
    if "--maj" in sys.argv:
        from . import maj
        sys.exit(maj.cli(relancer_apres="--relancer" in sys.argv))
    try:
        from . import application
        application.lancer()
    except Exception as e:                           # pywebview absent, ou moteur web absent ou en panne
        ms.message_erreur(e, "Ouverture de la fenêtre")
        ms.prevenir(ms.TEXTE_FENETRE_IMPOSSIBLE)
        sys.exit(1)


if __name__ == "__main__":
    main()
