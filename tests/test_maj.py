#!/usr/bin/env python3
"""Tests hors ligne de la mise a jour (maj.py) et de son pont avec la page (application.py).
Aucun acces reseau : GitHub est remplace par des doublures ; les fichiers sont des dossiers temporaires.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import io, os, sys, json, time, hashlib, tempfile, unittest, urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moodlesync import maj, moteur as ms, application as app

EXE = b"MZ" + b"\x00" * 5000                                      # un "executable" Windows (commence par MZ)
SHA = hashlib.sha256(EXE).hexdigest()


def release(version="99.0", assets=None, **extra):
    a = [{"name": "MoodleSync.exe", "size": len(EXE), "digest": f"sha256:{SHA}",
          "browser_download_url": f"https://github.com/{maj.DEPOT}/releases/download/v{version}/MoodleSync.exe"},
         {"name": "MoodleSync-macOS.zip", "size": 10, "digest": "sha256:" + "a" * 64,
          "browser_download_url": f"https://github.com/{maj.DEPOT}/releases/download/v{version}/MoodleSync-macOS.zip"}]
    return {"tag_name": f"v{version}", "html_url": f"https://github.com/{maj.DEPOT}/releases/tag/v{version}",
            "draft": False, "prerelease": False, "assets": a if assets is None else assets, **extra}


class Reponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Versions(unittest.TestCase):
    def test_comparaison(self):
        for distante, locale, attendu in (("2.4", "2.3", True), ("v2.4", "2.3", True), ("2.3", "2.3", False),
                                          ("2.3.0", "2.3", False), ("2.3.1", "2.3", True), ("2.10", "2.9", True),
                                          ("2.2", "2.3", False), ("3.0", "2.99", True),
                                          ("n'importe quoi", "2.3", False), ("", "2.3", False), (None, "2.3", False)):
            with self.subTest(distante=distante, locale=locale):
                self.assertEqual(maj.plus_recente(distante, locale), attendu)

    def test_tuple(self):
        self.assertEqual(maj.version_tuple("v2.4.1"), (2, 4, 1))
        self.assertIsNone(maj.version_tuple("2.4-beta"))


class Hotes(unittest.TestCase):
    def test_seul_github_en_https(self):
        for url, attendu in (("https://github.com/x/y", True), ("https://api.github.com/repos/x", True),
                             ("https://objects.githubusercontent.com/a", True),
                             ("https://release-assets.githubusercontent.com/a", True),
                             ("http://github.com/x", False), ("https://github.com.evil.example/x", False),
                             ("https://evilgithubusercontent.com/x", False), ("https://evil.example/github.com", False),
                             ("ftp://github.com/x", False), ("", False), (None, False)):
            with self.subTest(url=url):
                self.assertEqual(maj.hote_autorise(url), attendu)

    def test_ouvrir_refuse_un_autre_hote(self):
        with self.assertRaises(ms.Erreur):
            maj.ouvrir("https://evil.example/MoodleSync.exe")


@mock.patch.object(maj, "plateforme", lambda: "win")
class Recherche(unittest.TestCase):
    def test_version_disponible(self):
        info = maj.chercher(lambda url: release("99.0"))              # toujours plus recente que la version installee
        self.assertTrue(info["disponible"])
        self.assertEqual((info["version"], info["fichier"]["nom"], info["fichier"]["sha256"]), ("99.0", "MoodleSync.exe", SHA))
        self.assertEqual(info["fichier"]["taille"], len(EXE))

    def test_deja_a_jour(self):
        self.assertFalse(maj.chercher(lambda url: release(maj.VERSION))["disponible"])
        self.assertFalse(maj.chercher(lambda url: release("1.0"))["disponible"])

    def test_sans_empreinte_pas_d_installation_automatique(self):
        a = release()["assets"]
        del a[0]["digest"]
        self.assertIsNone(maj.chercher(lambda url: release(assets=a))["fichier"])

    def test_empreinte_mal_formee_ou_taille_absurde(self):
        for mod in ({"digest": "sha256:xyz"}, {"digest": "md5:" + "a" * 32}, {"size": 0}, {"size": maj.TAILLE_MAX + 1},
                    {"size": "grand"}, {"browser_download_url": "https://evil.example/MoodleSync.exe"},
                    {"browser_download_url": "http://github.com/MoodleSync.exe"}):
            with self.subTest(mod=mod):
                a = release()["assets"]
                a[0].update(mod)
                self.assertIsNone(maj.chercher(lambda url: release(assets=a))["fichier"])

    def test_fichier_absent_de_la_release(self):
        self.assertIsNone(maj.chercher(lambda url: release(assets=[]))["fichier"])

    def test_pre_version_brouillon_et_etiquette_illisible_refuses(self):
        for extra in ({"prerelease": True}, {"draft": True}, {"tag_name": "bientot"}):
            with self.subTest(extra=extra), self.assertRaises(ms.Erreur):
                maj.chercher(lambda url: release(**extra))

    def test_page_etrangere_remplacee(self):
        info = maj.chercher(lambda url: release(html_url="https://evil.example/x"))
        self.assertEqual(info["page"], maj.URL_PAGE)

    def test_erreurs_reseau_en_phrases(self):
        def limite(url):
            raise urllib.error.HTTPError(url, 403, "rate limit", {}, io.BytesIO())

        def coupe(url):
            raise urllib.error.URLError("hors ligne")
        with self.assertRaisesRegex(ms.Erreur, "limite"):
            maj.chercher(limite)
        with self.assertRaisesRegex(ms.Erreur, "joindre GitHub"):
            maj.chercher(coupe)
        with self.assertRaises(ms.Erreur):
            maj.chercher(lambda url: (_ for _ in ()).throw(ValueError("json")))


class Dossier(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = self.tmp.name
        self.exe = os.path.join(self.d, "MoodleSync.exe")
        with open(self.exe, "wb") as f:
            f.write(b"MZancien")

    def lire(self, chemin):
        with open(chemin, "rb") as f:
            return f.read()

    def fichier(self, taille=len(EXE), sha=SHA):
        return {"nom": "MoodleSync.exe", "url": f"https://github.com/{maj.DEPOT}/x.exe", "taille": taille, "sha256": sha}


class Telechargement(Dossier):
    def test_fichier_verifie_pose_et_progression(self):
        dest, vus = os.path.join(self.d, "n.exe"), []
        with mock.patch.object(maj, "ouvrir", lambda url, timeout=0: Reponse(EXE)):
            maj.telecharger(self.fichier(), dest, lambda a, t: vus.append((a, t)))
        self.assertEqual(self.lire(dest), EXE)
        self.assertEqual(vus[-1], (len(EXE), len(EXE)))
        self.assertEqual(os.listdir(self.d).count("n.exe.part"), 0)

    def test_empreinte_differente_rien_n_est_pose(self):
        dest = os.path.join(self.d, "n.exe")
        with mock.patch.object(maj, "ouvrir", lambda url, timeout=0: Reponse(EXE[:-1] + b"X")):
            with self.assertRaisesRegex(ms.Erreur, "empreinte"):
                maj.telecharger(self.fichier(), dest)
        self.assertEqual(sorted(os.listdir(self.d)), ["MoodleSync.exe"])

    def test_taille_incomplete_ou_excessive(self):
        dest = os.path.join(self.d, "n.exe")
        for contenu in (EXE[:100], EXE + b"surplus"):
            with self.subTest(taille=len(contenu)), mock.patch.object(maj, "ouvrir", lambda url, timeout=0, c=contenu: Reponse(c)):
                with self.assertRaises(ms.Erreur):
                    maj.telecharger(self.fichier(), dest)
            self.assertEqual(sorted(os.listdir(self.d)), ["MoodleSync.exe"])

    def test_coupure_reseau_en_cours_de_route(self):
        class Coupee(Reponse):
            def read(self, n=-1):
                raise urllib.error.URLError("coupure")
        with mock.patch.object(maj, "ouvrir", lambda url, timeout=0: Coupee()):
            with self.assertRaisesRegex(ms.Erreur, "rien n'a été modifié"):
                maj.telecharger(self.fichier(), os.path.join(self.d, "n.exe"))
        self.assertEqual(sorted(os.listdir(self.d)), ["MoodleSync.exe"])


class Remplacement(Dossier):
    def nouveau(self, contenu=b"MZnouveau"):
        chemin = self.exe + maj.SUFFIXE_NOUVEAU
        with open(chemin, "wb") as f:
            f.write(contenu)
        return chemin

    def test_remplace_et_ne_laisse_rien(self):
        maj.remplacer(self.exe, self.nouveau())
        self.assertEqual(self.lire(self.exe), b"MZnouveau")
        self.assertEqual(os.listdir(self.d), ["MoodleSync.exe"])

    def test_echec_de_la_mise_en_place_remet_l_ancien(self):
        nouveau, vrai = self.nouveau(), os.rename

        def rename(a, b):
            if a == nouveau:
                raise PermissionError("verrou")
            return vrai(a, b)
        with mock.patch("os.rename", rename), self.assertRaisesRegex(ms.Erreur, "remise en place"):
            maj.remplacer(self.exe, nouveau)
        self.assertEqual(self.lire(self.exe), b"MZancien")

    def test_executable_verrouille_rien_ne_change(self):
        nouveau, vrai = self.nouveau(), os.rename

        def rename(a, b):
            if a == self.exe:
                raise PermissionError("utilisé")
            return vrai(a, b)
        with mock.patch("os.rename", rename), self.assertRaisesRegex(ms.Erreur, "rien n'a été modifié"):
            maj.remplacer(self.exe, nouveau)
        self.assertEqual(self.lire(self.exe), b"MZancien")

    def test_dossier_comme_une_application_mac(self):
        app_ = os.path.join(self.d, "MoodleSync.app")
        neuf = os.path.join(self.d, "neuf.app")
        for dossier, contenu in ((app_, "ancienne"), (neuf, "nouvelle")):
            os.makedirs(os.path.join(dossier, "Contents"))
            with open(os.path.join(dossier, "Contents", "v"), "w") as f:
                f.write(contenu)
        maj.remplacer(app_, neuf)
        self.assertEqual(self.lire(os.path.join(app_, "Contents", "v")), b"nouvelle")
        self.assertFalse(os.path.exists(neuf) or os.path.exists(app_ + maj.SUFFIXE_ANCIEN))

    def test_nettoyer_efface_les_restes(self):
        for s in (maj.SUFFIXE_ANCIEN, maj.SUFFIXE_NOUVEAU):
            open(self.exe + s, "wb").close()
        maj.nettoyer(self.exe)
        self.assertEqual(os.listdir(self.d), ["MoodleSync.exe"])

    @mock.patch.object(maj, "plateforme", lambda: "win")
    def test_installation_complete(self):
        info = {"fichier": self.fichier()}
        with mock.patch.object(maj, "ouvrir", lambda url, timeout=0: Reponse(EXE)):
            maj.installer(info, self.exe)
        self.assertEqual(self.lire(self.exe), EXE)
        self.assertEqual(os.listdir(self.d), ["MoodleSync.exe"])

    @mock.patch.object(maj, "plateforme", lambda: "win")
    def test_un_fichier_qui_n_est_pas_un_executable_est_refuse(self):
        contenu = b"PK" + b"\x00" * 100                                  # empreinte juste, mais pas un .exe
        info = {"fichier": self.fichier(len(contenu), hashlib.sha256(contenu).hexdigest())}
        with mock.patch.object(maj, "ouvrir", lambda url, timeout=0: Reponse(contenu)):
            with self.assertRaisesRegex(ms.Erreur, "pas un exécutable"):
                maj.installer(info, self.exe)
        self.assertEqual(self.lire(self.exe), b"MZancien")
        self.assertEqual(os.listdir(self.d), ["MoodleSync.exe"])

    def test_sans_fichier_verifiable(self):
        with self.assertRaisesRegex(ms.Erreur, "empreinte absente"):
            maj.installer({"fichier": None}, self.exe)


class Cible(unittest.TestCase):
    def test_code_source(self):
        chemin, raison = maj.cible()
        self.assertIsNone(chemin)
        self.assertIn("code source", raison)

    @mock.patch.object(maj, "plateforme", lambda: "win")
    def test_executable_compile(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", os.path.join(d, "MoodleSync.exe")):
            self.assertEqual(maj.cible(), (os.path.join(d, "MoodleSync.exe"), None))
            with mock.patch("os.access", lambda *a: False):
                self.assertIn("droits", maj.cible()[1])

    @mock.patch.object(maj, "plateforme", lambda: "mac")
    def test_application_mac(self):
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "MoodleSync.app", "Contents", "MacOS", "MoodleSync")
            with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", exe):
                self.assertEqual(maj.cible(), (os.path.join(d, "MoodleSync.app"), None))
            exe2 = os.path.join(d, "AppTranslocation", "x", "d", "MoodleSync.app", "Contents", "MacOS", "MoodleSync")
            with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", exe2):
                self.assertIn("temporaire", maj.cible()[1])


class Cache(unittest.TestCase):
    def test_verification_recente(self):
        t = 1_000_000.0
        self.assertTrue(maj.verification_recente({"verifie": t - 60}, t))
        self.assertFalse(maj.verification_recente({"verifie": t - maj.DELAI_VERIFICATION - 1}, t))
        self.assertFalse(maj.verification_recente({"verifie": t + 3600}, t))          # horloge reculee : on revérifie
        self.assertFalse(maj.verification_recente({}, t))
        self.assertFalse(maj.verification_recente({"verifie": "hier"}, t))


class Cli(unittest.TestCase):
    def lancer(self, chemin=("x.exe", None), info=None, erreur=None):
        dit = []
        with mock.patch.object(maj, "cible", lambda: chemin), \
                mock.patch.object(maj, "chercher", (lambda: (_ for _ in ()).throw(erreur)) if erreur else (lambda: info)), \
                mock.patch.object(maj, "installer", lambda i, c, p=None: dit.append("installe")), \
                mock.patch.object(maj, "relancer", lambda c: dit.append("relance")):
            return maj.cli(relancer_apres=True, dire=dit.append), dit

    def test_codes_de_sortie(self):
        code, _ = self.lancer(chemin=(None, "source"))
        self.assertEqual(code, 11)
        code, _ = self.lancer(info={"disponible": False, "version": "2.3", "fichier": None, "page": "p"})
        self.assertEqual(code, 10)
        code, _ = self.lancer(info={"disponible": True, "version": "2.4", "fichier": None, "page": "p"})
        self.assertEqual(code, 12)
        code, dit = self.lancer(info={"disponible": True, "version": "2.4", "fichier": {"x": 1}, "page": "p"})
        self.assertEqual((code, "installe" in dit, "relance" in dit), (0, True, True))
        code, _ = self.lancer(erreur=ms.Erreur("hors ligne"))
        self.assertEqual(code, 1)


class Pont(unittest.TestCase):
    """Api.maj_chercher : reglage, cache de 12 h, installation refusee hors executable."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sauve = (ms.APP_DIR, ms.CONFIG)
        ms.APP_DIR, ms.CONFIG = self.tmp.name, os.path.join(self.tmp.name, "config.json")
        self.addCleanup(lambda: (setattr(ms, "APP_DIR", self.sauve[0]), setattr(ms, "CONFIG", self.sauve[1])))
        self.appels = []

        def chercher():
            self.appels.append(1)
            return {"courante": maj.VERSION, "version": "99.0", "disponible": True, "page": maj.URL_PAGE, "fichier": None}
        p = mock.patch.object(maj, "chercher", chercher)
        p.start()
        self.addCleanup(p.stop)
        self.api = app.Api()

    def test_recherche_manuelle_puis_cache(self):
        r = self.api.maj_chercher(True)
        self.assertEqual((r["disponible"], r["version"], r["installable"]), (True, "99.0", False))
        self.assertIn("code source", r["raison"])                       # pas un executable compile : lien de telechargement
        self.assertEqual(self.api.maj_chercher(False)["version"], "99.0")
        self.assertEqual(len(self.appels), 1)                           # le demarrage reutilise le cache
        self.api.maj_chercher(True)
        self.assertEqual(len(self.appels), 2)                           # la recherche manuelle ignore le cache

    def test_reglage_coupe_aucune_requete(self):
        self.assertEqual(self.api.sync_regler("maj_auto", False)["maj_auto"], False)
        self.assertEqual(self.api.maj_chercher(False), {"saute": True})
        self.assertEqual(self.appels, [])
        self.assertEqual(self.api.sync_regler("maj_auto", True)["maj_auto"], True)

    def test_defaut_active_et_cache_perime(self):
        self.assertTrue(self.api._etat_sync()["maj_auto"])
        self.api._sauver_cfg(lambda c: c.update(maj_cache={"verifie": time.time() - 13 * 3600, "version": "98.0"}))
        self.assertEqual(self.api.maj_chercher(False)["version"], "99.0")
        self.assertEqual(len(self.appels), 1)

    def test_pas_de_requete_pendant_les_verifications_automatiques(self):
        with mock.patch.dict(os.environ, {"MOODLESYNC_VERIF": "x"}):
            self.assertEqual(self.api.maj_chercher(False), {"saute": True})
        self.assertEqual(self.appels, [])

    def test_installation_refusee_depuis_le_code_source(self):
        r = self.api.maj_installer()
        self.assertIn("code source", r["erreur"])
        self.assertEqual(self.appels, [])

    def test_installation_refusee_pendant_une_synchronisation(self):
        self.api._long.acquire()
        self.assertEqual(self.api.maj_installer(), {"erreur": app.OCCUPE})

    def test_version_a_jour_dans_le_cache(self):
        self.api._sauver_cfg(lambda c: c.update(maj_cache={"verifie": time.time(), "version": maj.VERSION}))
        self.assertFalse(self.api.maj_chercher(False)["disponible"])

    def test_appels_de_la_page_existent(self):
        for nom in ("maj_chercher", "maj_installer"):
            self.assertTrue(callable(getattr(app.Api, nom)))


if __name__ == "__main__":
    unittest.main()
