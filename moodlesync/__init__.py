"""MoodleSync : copie rangee des fichiers de cours Moodle, et Ma semaine (planning de lecture, experimental).

Modules :
  moteur.py       connexion, lecture de l'API Moodle, telechargement et rangement (la synchronisation) ;
  seances.py      Ma semaine : dates des seances, lectures, controles (fonctions pures, testees) ;
  semaine.py      Ma semaine : collecte, analyse, rendu de Ma semaine.md et de l'audit ;
  suivi.py        Ma semaine : cases, temps, echeances, changements, fusion avec Ma semaine.md ;
  application.py  la fenetre (pywebview) et le pont avec interface/index.html ;
  __main__.py     lancement : fenetre, ou mode automatique (--auto).
"""
VERSION = "2.0"
