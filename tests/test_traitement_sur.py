"""Tests du pipeline sur (tache R2) : echec sans aucune trace, copie de l'original, remplacement du PDF
cherchable, restauration locale (contrat 3.1, 3.2, 3.3).

Aucun vrai moteur : `executer` et `rendre_page` sont doubles par le banc de `tests/test_ocr.py`, comme les
tests de C2 a C4. Chaque echec est mesure par un **listage** du coffre avant et apres, hors
`.moodlesync-ocr/` : c'est l'invariant 2, et il ne se lit pas dans le code.

Ce que ces tests ne mesurent pas : un vrai Tesseract, Windows et macOS, les chemins longs, un coffre de
plusieurs milliers de fichiers, ni le glisser-deposer.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import json
import os
import shutil
import unittest
import urllib.request
from unittest import mock

from moodlesync import moteur as ms, ocr
from tests import test_ocr as T
from tests.test_ocr import BLANC, NATIF, SCAN, FauxUrlopen, octets, tsv_assez_long, tsv_un_mot


def listage(dest):
    """Tout ce qui est visible a cote des PDF : {chemin relatif en `/`: octets}. `.moodlesync-ocr/` exclu.

    C'est la mesure de l'invariant 2 : un echec ne doit rien changer a ce listage, ni fichier, ni contenu.
    """
    trouves = {}
    for racine, dossiers, fichiers in os.walk(dest):
        relatif = os.path.relpath(racine, dest)
        if relatif == ".":
            dossiers[:] = [d for d in dossiers if d != ocr.CACHE]
        for nom in fichiers:
            chemin = os.path.join(racine, nom)
            with open(chemin, "rb") as f:
                trouves[os.path.relpath(chemin, dest).replace(os.sep, "/")] = f.read()
    return trouves


def originaux(dest):
    """Contenu du dossier des copies d'originaux, trie (vide s'il n'existe pas)."""
    dossier = os.path.join(dest, ocr.CACHE, ocr.DOSSIER_ORIGINAUX)
    return sorted(os.listdir(dossier)) if os.path.isdir(dossier) else []


def edition_non_regenerable(chemin):
    """Marque un `.md` comme ecrit par l'etudiant : sa ligne `moodlesync:` disparait, comme la marque le dit."""
    with open(chemin, encoding="utf-8") as f:
        lignes = f.read().splitlines()
    with open(chemin, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(l for l in lignes if not l.startswith("moodlesync:")) + "\n")


class Banc(T.PdfBase):
    """Un PDF de cours range dans `coffre`, avec son entree dans .moodlesync.json (banc de `tests/test_ocr.py`)."""

    def traiter(self, cfg=None, **kw):
        return self.avec(ocr.traiter_document, self.dest, self.rel, cfg if cfg is not None else {}, **kw)

    def coffre_neuf(self):
        """Coffre vide pour un tour de mesure : le document precedent et son cache disparaissent."""
        shutil.rmtree(self.dest, ignore_errors=True)
        os.makedirs(self.dest)

    def entree_cache(self, rel=None):
        return ocr.charger_cache(self.dest)["documents"].get(self.rel if rel is None else rel)


class TraitementSur(Banc):
    """3.2, dans l'ordre : extraction, qualite, echec, texte, copie, PDF cherchable, annulation, cache."""

    def test_pdf_scanne_remplace_et_garde_une_copie(self):
        """Un PDF avec au moins une page a reconnaitre est remplace et garde l'original, octet pour octet (U1)."""
        self.poser(pages=[SCAN, SCAN])
        origine = octets(self.chemin)
        resultat = self.traiter()

        self.assertEqual(set(resultat), {"entree", "statut", "motif", "remplace", "texte", "message"})
        self.assertEqual((resultat["statut"], resultat["motif"], resultat["remplace"], resultat["texte"]),
                         ("ok", "", True, True))
        self.assertEqual(resultat["message"], "")
        entree = resultat["entree"]
        self.assertTrue(os.path.isfile(self.chemin + ".md"))
        self.assertNotEqual(octets(self.chemin), origine)
        self.assertIsNotNone(ocr.lire_marque(self.chemin))
        self.assertIn("genere", ms.charger_etat(self.dest)[self.cle_etat])

        # 2.2 : l'entree porte le texte, le format, le remplacement et la copie de l'original.
        self.assertEqual((entree["sortie"], entree["format"], entree["remplace"]),
                         (self.rel + ".md", "md", True))
        self.assertEqual(entree["sortie_empreinte"], T.sha256_octets(octets(self.chemin + ".md")))
        hexa = entree["empreinte"].split(":", 1)[1]
        self.assertEqual(entree["original"], {"fichier": "originaux/" + hexa + ".pdf",
                                              "empreinte": entree["empreinte"], "taille": len(origine)})
        copie, _ = ocr.chemin_original(self.dest, entree["empreinte"])
        self.assertEqual(octets(copie), origine)
        self.assertEqual(originaux(self.dest), [hexa + ".pdf"])

        # Un second passage ne refait rien : la source est identifiee par `genere`, le texte est a jour.
        appels = len(self.appels)
        second = self.traiter()
        self.assertEqual(len(self.appels), appels)
        self.assertEqual((second["statut"], second["remplace"], second["texte"]), ("ok", True, True))

    def test_pdf_textuel_ne_recoit_que_son_texte(self):
        """O2 : un PDF entierement textuel n'est pas remplace et n'a pas de copie (rien a rendre cherchable)."""
        self.poser(pages=[NATIF, NATIF])
        origine = octets(self.chemin)
        resultat = self.traiter()

        self.assertEqual((resultat["statut"], resultat["remplace"], resultat["texte"]), ("ok", False, True))
        self.assertEqual(octets(self.chemin), origine)
        self.assertIsNone(resultat["entree"]["original"])
        self.assertFalse(resultat["entree"]["remplace"])
        self.assertTrue(os.path.isfile(self.chemin + ".md"))
        self.assertEqual(originaux(self.dest), [])
        self.assertEqual(self.appels, [])                      # aucune page a reconnaitre

    def test_pdf_hors_suivi_recoit_son_texte_sans_remplacement(self):
        """O17 (E-V7-2) : un PDF que .moodlesync.json ne suit pas se traite comme un PDF textuel (O2).

        Le texte est ecrit a cote, le PDF reste intact octet pour octet, aucune copie d'original n'est faite et la
        fabrication du PDF cherchable n'est meme pas lancee (elle refuserait par `non_suivi`, range jusque-la dans
        le motif `verification`, qui perdait le texte pourtant lu).
        """
        self.poser(pages=[SCAN], etat=False)
        origine = octets(self.chemin)
        with mock.patch.object(ocr, "fabriquer_pdf_cherchable",
                               side_effect=ocr.ErreurOcr("non_suivi")) as fabrication:
            resultat = self.traiter()

        self.assertEqual(fabrication.call_count, 0)
        self.assertEqual(set(resultat), {"entree", "statut", "motif", "remplace", "texte", "message"})
        self.assertEqual((resultat["statut"], resultat["motif"], resultat["remplace"], resultat["texte"]),
                         ("ok", "", False, True))
        self.assertEqual(octets(self.chemin), origine)
        self.assertFalse(os.path.exists(self.chemin + ".ocr.part"))
        self.assertEqual(originaux(self.dest), [])
        self.assertTrue(os.path.isfile(self.chemin + ".md"))
        entree = resultat["entree"]
        self.assertEqual((entree["etat"], entree["remplace"], entree["original"]), ("ok", False, None))
        self.assertEqual((entree["sortie"], entree["format"]), (self.rel + ".md", "md"))
        self.assertNotIn("genere", ms.charger_etat(self.dest).get(self.cle_etat) or {})

    def test_pdf_suivi_est_toujours_remplace(self):
        """Jumeau du precedent, non-regression : le meme PDF, suivi par .moodlesync.json, est bien remplace."""
        self.poser(pages=[SCAN])
        origine = octets(self.chemin)
        resultat = self.traiter()

        self.assertEqual((resultat["statut"], resultat["remplace"], resultat["texte"]), ("ok", True, True))
        self.assertNotEqual(octets(self.chemin), origine)
        self.assertEqual(len(originaux(self.dest)), 1)
        self.assertTrue(resultat["entree"]["remplace"])
        self.assertIsNotNone(resultat["entree"]["original"])
        self.assertIn("genere", ms.charger_etat(self.dest)[self.cle_etat])

    def test_image_ne_recoit_que_son_texte(self):
        """O2 : une image du coffre recoit son texte, rien n'est remplace (une image n'est pas un PDF)."""
        from PIL import Image
        chemin = os.path.join(self.dest, "Cours A", "Section 1", "scan.png")
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        Image.new("L", (40, 40), 255).save(chemin)
        avant = octets(chemin)

        resultat = self.avec(ocr.traiter_document, self.dest, "Cours A/Section 1/scan.png", {})
        self.assertEqual((resultat["statut"], resultat["remplace"], resultat["texte"]), ("ok", False, True))
        self.assertEqual(octets(chemin), avant)
        self.assertTrue(os.path.isfile(chemin + ".md"))
        self.assertIsNone(resultat["entree"]["original"])
        self.assertEqual(resultat["entree"]["sortie"], "Cours A/Section 1/scan.png.md")

    def test_garder_original_faux_ne_garde_aucune_copie(self):
        """`garder_original=False` (depot, 4.6) : le PDF est remplace sans copie, et le PDF source n'est pas touche
        a sa place d'origine (ici la copie du depot) ; `original` vaut null (2.2)."""
        self.poser(pages=[SCAN])
        resultat = self.traiter(garder_original=False)

        self.assertTrue(resultat["remplace"])
        self.assertIsNone(resultat["entree"]["original"])
        self.assertEqual(originaux(self.dest), [])
        self.assertIsNotNone(ocr.lire_marque(self.chemin))

    def test_seuil_de_zero_soixante_dix(self):
        """3.2 etape 2 : 0,70 exactement n'est pas un echec, 0,69 en est un (seuil strict)."""
        self.tsv = tsv_un_mot(70, "mot").encode("utf-8")
        self.poser(pages=[SCAN])
        juste = self.traiter()
        self.assertEqual(juste["entree"]["confiance"], 0.7)
        self.assertEqual((juste["statut"], juste["motif"]), ("a_verifier", ""))
        self.assertTrue(juste["remplace"])

        # Un autre coffre pour le second seuil : le premier document est deja traite.
        self.dest = os.path.join(self.d, "coffre2")
        os.makedirs(self.dest)
        self.chemin = os.path.join(self.dest, *self.rel.split("/"))
        self.tsv = tsv_un_mot(69, "mot").encode("utf-8")
        self.poser(pages=[SCAN])
        avant = listage(self.dest)
        sous = self.traiter()
        self.assertEqual((sous["statut"], sous["motif"]), ("echec", "difficile"))
        self.assertEqual(sous["entree"]["confiance"], 0.69)
        self.assertEqual(listage(self.dest), avant)

    def test_document_vide_est_un_echec(self):
        """O3 : un document sans aucun texte est un echec de motif `vide`, et il ne laisse rien."""
        self.poser(pages=[BLANC])
        avant = listage(self.dest)
        resultat = self.traiter()

        self.assertEqual((resultat["statut"], resultat["motif"], resultat["texte"]), ("echec", "vide", False))
        self.assertEqual(listage(self.dest), avant)
        self.assertEqual(originaux(self.dest), [])
        self.assertNotIn("sortie", resultat["entree"])
        self.assertNotIn("format", resultat["entree"])
        self.assertEqual(resultat["entree"]["etat"], "echec")
        self.assertIn(self.rel, ocr.charger_cache(self.dest)["documents"])   # l'echec est memorise (O4)

    def test_document_illisible_est_un_echec(self):
        """Aucune page lue : motif `illisible`, distinct de `vide`, et rien n'est ecrit."""
        self.poser(pages=[SCAN, SCAN])
        avant = listage(self.dest)

        def illisible(*a, **kw):
            raise ocr.ErreurOcr("illisible")

        with mock.patch.object(ocr, "extraire_page", illisible):
            resultat = self.traiter()
        self.assertEqual((resultat["statut"], resultat["motif"]), ("echec", "illisible"))
        self.assertEqual(listage(self.dest), avant)
        self.assertEqual(originaux(self.dest), [])

    def test_echec_d_ecriture_ne_laisse_rien(self):
        """Une ecriture de texte impossible est un echec `ecriture` (2.2, O1) : rien n'est ecrit ni remplace."""
        self.poser(pages=[SCAN])
        avant = listage(self.dest)

        def refuse(*a, **kw):
            raise OSError("disque plein")

        with mock.patch.object(ocr, "ecrire_document_texte", refuse):
            resultat = self.traiter()
        self.assertEqual((resultat["statut"], resultat["motif"]), ("echec", "ecriture"))
        self.assertEqual(listage(self.dest), avant)
        self.assertEqual(originaux(self.dest), [])
        self.assertIsNone(ocr.lire_marque(self.chemin))

    def test_empreinte_de_copie_fausse_est_un_echec(self):
        """3.2 etape 5a : une copie qui ne porte pas l'empreinte de la source fait echouer le document (motif
        `ecriture`), et le texte deja ecrit est retire."""
        self.poser(pages=[SCAN])
        origine = octets(self.chemin)
        avant = listage(self.dest)

        def copie_fausse(source, cible):
            with open(cible, "wb") as f:
                f.write(b"pas l'original")

        with mock.patch.object(ocr.shutil, "copyfile", copie_fausse):
            resultat = self.traiter()
        self.assertEqual((resultat["statut"], resultat["motif"]), ("echec", "ecriture"))
        self.assertEqual(listage(self.dest), avant)
        self.assertEqual(octets(self.chemin), origine)
        self.assertEqual(originaux(self.dest), [])

    def test_panne_de_verification_efface_texte_copie_et_temporaire(self):
        """3.2 etape 6 (O1) : la fabrication d'un PDF cherchable qui ne passe pas la verification laisse le PDF
        intact octet pour octet, sans texte, sans copie et sans fichier temporaire."""
        from PIL import Image
        self.poser(pages=[SCAN, SCAN])
        origine = octets(self.chemin)

        def rendre(chemin, numero, dpi, *, preparer=True):
            image = Image.new("L", (120, 60), 255)
            if chemin.endswith(".ocr.part") and dpi == 150:
                image.putpixel((0, 0), 254)
            return image

        self.rendre = rendre
        avant = listage(self.dest)
        resultat = self.traiter()

        self.assertEqual((resultat["statut"], resultat["motif"], resultat["texte"]), ("echec", "verification", False))
        self.assertEqual(listage(self.dest), avant)
        self.assertEqual(octets(self.chemin), origine)
        self.assertEqual(originaux(self.dest), [])
        self.assertFalse([n for n in os.listdir(os.path.dirname(self.chemin))
                          if n.endswith((".tmp", ".part"))])
        # Ecart 60 : la reprise et ses boites restent pour l'essai suivant, sans `cfg["ocr_pdf"]` (3.2, point 3).
        reprise = ocr._fichier_reprise(self.dest, resultat["entree"]["empreinte"])
        with open(reprise, encoding="utf-8") as f:
            faites = json.load(f)["faites"]
        self.assertEqual(sorted(faites), ["1", "2"])
        self.assertTrue(all(enreg.get("boites") for enreg in faites.values()))

    def test_annulation_pendant_les_pages(self):
        """3.1 : `arreter()` vrai leve ms.Annule et rien n'est laisse a cote du PDF."""
        self.poser(pages=[SCAN, SCAN])
        avant = listage(self.dest)
        with self.assertRaises(ms.Annule):
            self.traiter(arreter=lambda: True)
        self.assertEqual(listage(self.dest), avant)
        self.assertEqual(originaux(self.dest), [])

    def test_annulation_pendant_la_fabrication(self):
        """Une annulation pendant la fabrication, apres l'ecriture du texte et de la copie, les retire aussi
        (3.2 etape 6). Le point d'arret est celui ou le texte et la copie existent deja (E-V2-4 c)."""
        self.poser(pages=[SCAN])
        avant = listage(self.dest)
        appels = {"n": 0, "texte": False, "copie": False}

        def arreter():
            appels["n"] += 1
            appels["texte"], appels["copie"] = os.path.isfile(self.chemin + ".md"), bool(originaux(self.dest))
            return appels["texte"] and appels["copie"]

        with self.assertRaises(ms.Annule):
            self.traiter(arreter=arreter)
        self.assertTrue(appels["texte"] and appels["copie"],
                        "l'annulation tombe apres l'ecriture du texte et de la copie")
        self.assertEqual(listage(self.dest), avant)
        self.assertEqual(originaux(self.dest), [])

    def test_annulation_a_chaque_etape(self):
        """E-V2-4 (a) : pour chaque point d'arret du document, l'annulation au N-ieme appel de `arreter` leve
        ms.Annule et ne laisse rien (invariant 2), aucune copie d'original. Methode de la sonde `sonde_annul.py`
        de V2 : le nombre de points d'arret est mesure d'abord, puis annule a chacun ; les points de la
        fabrication, ou le texte et la copie existent deja, mesurent leur retrait (M11, M30)."""
        self.poser(pages=[SCAN, SCAN])
        mesure = {"n": 0}

        def compter():
            mesure["n"] += 1
            return False

        self.traiter(arreter=compter)
        arrets = mesure["n"]
        self.assertGreaterEqual(arrets, 7, "le banc doit offrir au moins les sept points d'arret de V2")

        for n in range(1, arrets + 1):
            with self.subTest(n=n):
                self.coffre_neuf()
                self.poser(pages=[SCAN, SCAN])
                avant = listage(self.dest)
                vus = {"n": 0, "texte": False, "copie": False}

                def arreter():
                    vus["n"] += 1
                    if vus["n"] < n:
                        return False
                    vus["texte"], vus["copie"] = os.path.isfile(self.chemin + ".md"), bool(originaux(self.dest))
                    return True

                with self.assertRaises(ms.Annule):
                    self.traiter(arreter=arreter)
                self.assertEqual(vus["n"], n)
                self.assertEqual(listage(self.dest), avant)
                self.assertEqual(originaux(self.dest), [])
                self.assertFalse([nom for nom in os.listdir(os.path.dirname(self.chemin))
                                  if nom.endswith((".part", ".tmp"))])
                if vus["texte"]:
                    # Point d'arret de la fabrication : le texte venait d'etre ecrit, la copie d'etre posee.
                    self.assertTrue(vus["copie"], "N=%d : le texte est ecrit sans la copie" % n)
                if n == arrets:
                    self.assertTrue(vus["texte"] and vus["copie"], "le dernier point d'arret est celui de la fabrication")

    def test_un_texte_edite_survit_a_un_echec_tardif(self):
        """E-V2-4 (b), invariant 3 : un texte modifie a la main n'est ni reecrit ni supprime quand la fabrication
        echoue apres l'ecriture du texte (M19)."""
        self.poser(pages=[SCAN])
        texte = self.chemin + ".md"
        with open(texte, "w", encoding="utf-8", newline="\n") as f:
            f.write("Mes notes a moi, sans la ligne moodlesync.\n")
        edite = octets(texte)
        avant = listage(self.dest)

        def refuse(dest, chemin_rel, cfg, *, arreter=None):
            raise ocr.ErreurOcr("verification")

        with mock.patch.object(ocr, "fabriquer_pdf_cherchable", refuse):
            resultat = self.traiter()
        self.assertEqual((resultat["statut"], resultat["motif"]), ("echec", "verification"))
        self.assertEqual(octets(texte), edite)
        self.assertEqual(listage(self.dest), avant)
        self.assertEqual(originaux(self.dest), [])

    def test_refaire_sur_un_document_remplace_garde_remplace_et_copie(self):
        """E-V2-2, O13 : `refaire` sur un PDF deja remplace garde `remplace`, `original` et la copie locale ;
        le PDF cherchable reste celui qu'on a fabrique (aucune seconde fabrication) et « Restaurer l'original »
        marche encore sans reseau."""
        self.poser(pages=[SCAN])
        origine = octets(self.chemin)
        # Une couche assez longue pour que la page fabriquee soit classee « texte » : c'est l'etat mesure
        # par la revue V2 sur le PDF reel (`_a_reconnaitre: False`), celui ou `refaire` perdait la copie.
        self.tsv = tsv_assez_long().encode("utf-8")
        premier = self.traiter()
        self.assertTrue(premier["remplace"])
        self.assertFalse(self.avec(ocr._a_reconnaitre, self.chemin))
        copie, _ = ocr.chemin_original(self.dest, premier["entree"]["empreinte"])
        cherchable = octets(self.chemin)

        refait = self.traiter(refaire=True)

        self.assertEqual((refait["statut"], refait["remplace"], refait["texte"]), ("ok", True, True))
        self.assertEqual(refait["entree"]["original"], premier["entree"]["original"])
        self.assertEqual(octets(self.chemin), cherchable)                  # ni refabrique ni touche
        self.assertEqual(originaux(self.dest), [premier["entree"]["empreinte"].split(":", 1)[1] + ".pdf"])
        self.assertTrue(os.path.isfile(copie))
        self.assertEqual(octets(copie), origine)

        # Restauration locale, sans jeton : la copie garde par `refaire` sert encore.
        cache = ocr.charger_cache(self.dest)
        self.assertEqual(cache["documents"][self.rel]["original"], premier["entree"]["original"])
        self.assertEqual(ocr.restaurer(self.dest, self.rel, {}), {"ok": True})
        self.assertEqual(octets(self.chemin), origine)
        self.assertEqual(originaux(self.dest), [])
        self.assertIsNone(self.entree_cache())

    def test_refaire_sur_un_pdf_textuel_ne_le_remplace_pas(self):
        """O2, E-V2-2 : `refaire` sur un PDF entierement textuel ne le remplace pas, ne lui donne aucune copie
        et ne pose aucune marque."""
        self.poser(pages=[NATIF])
        premier = self.traiter()
        self.assertFalse(premier["remplace"])

        refait = self.traiter(refaire=True)

        self.assertEqual((refait["statut"], refait["remplace"], refait["texte"]), ("ok", False, True))
        self.assertIsNone(refait["entree"]["original"])
        self.assertEqual(originaux(self.dest), [])
        self.assertIsNone(ocr.lire_marque(self.chemin))

    def test_copie_alteree_n_est_pas_reprise_par_refaire(self):
        """E-V2-2, O13 : `refaire` ne reprend pas une copie d'original qui ne porte plus son empreinte ; le
        remplacement reste vrai, `original` est nul, et la restauration retombe sur Moodle."""
        self.poser(pages=[SCAN])
        self.tsv = tsv_assez_long().encode("utf-8")
        premier = self.traiter()
        self.assertTrue(premier["remplace"])
        copie, _ = ocr.chemin_original(self.dest, premier["entree"]["empreinte"])
        with open(copie, "ab") as f:
            f.write(b"alteree")

        refait = self.traiter(refaire=True)

        self.assertTrue(refait["remplace"])
        self.assertIsNone(refait["entree"]["original"])
        with self.assertRaises(ms.SessionExpiree):       # sans jeton : plus de copie utilisable
            ocr.restaurer(self.dest, self.rel, {})

    def test_refaire_en_echec_de_qualite_ne_touche_a_rien(self):
        """E-V2-3 : un document deja traite, retraite avec une confiance sous 0,70, garde son PDF cherchable,
        son texte, sa copie et son entree `traite` ; l'echec n'est pas memorise et l'avertissement
        `refaire_echec` est dit a l'appelant. Seul un document jamais traite memorise un echec."""
        self.poser(pages=[SCAN])
        premier = self.traiter()
        self.assertTrue(premier["remplace"])
        avant = listage(self.dest)
        texte = octets(self.chemin + ".md")
        copie = originaux(self.dest)
        vrai = ocr._pages_document

        def pages_faibles(ctx, **kw):
            # Une relecture qui ne rend qu'un mot tres mal lu : confiance 0,4, sous le seuil de 0,70.
            vrai(ctx, **kw)
            return ([{"numero": 1, "source": "ocr", "texte": "mot", "confiance": 0.4, "mots": 1}], [], 1)

        with mock.patch.object(ocr, "_pages_document", pages_faibles):
            refait = self.traiter(refaire=True)

        self.assertEqual(refait["statut"], premier["statut"])              # l'etat d'avant, pas `echec`
        self.assertEqual(refait["message"], ocr.MESSAGES["refaire_echec"])
        self.assertTrue(refait["remplace"] and refait["texte"])
        self.assertEqual(refait["entree"], premier["entree"])
        self.assertEqual(listage(self.dest), avant)                        # ni PDF, ni texte, ni copie touches
        self.assertEqual(octets(self.chemin + ".md"), texte)
        self.assertEqual(originaux(self.dest), copie)
        self.assertEqual(self.entree_cache()["etat"], premier["entree"]["etat"])

    def test_echec_memorise_n_est_pas_retente(self):
        """O4 : un echec garde son entree et n'est pas retente tout seul ; `refaire` le reprend."""
        self.tsv = tsv_un_mot(69, "mot").encode("utf-8")
        self.poser(pages=[SCAN])
        premier = self.traiter()
        self.assertEqual(premier["statut"], "echec")
        appels = len(self.appels)

        second = self.traiter()
        self.assertEqual((second["statut"], second["motif"]), ("echec", "difficile"))
        self.assertEqual(len(self.appels), appels)               # aucun appel au moteur

        self.tsv = tsv_un_mot(95, "mot").encode("utf-8")
        refait = self.traiter(refaire=True)
        self.assertEqual((refait["statut"], refait["motif"]), ("ok", ""))
        self.assertTrue(refait["remplace"])

    def test_avec_boites_independant_du_reglage(self):
        """3.2 point 3 : `avec_boites` vaut vrai pour tout PDF a reconnaitre, sans `cfg["ocr_pdf"]` ; sans boites,
        la fabrication n'aurait aucune couche de texte a poser."""
        self.poser(pages=[SCAN, SCAN])
        resultat = self.traiter({"ocr_pdf": "aucun"})
        self.assertTrue(resultat["remplace"])
        self.assertIsNotNone(ocr.lire_marque(self.chemin))
        self.assertEqual(len(self.appels), 2)                    # une reconnaissance par page, une seule

    def test_messages_des_motifs(self):
        """5.5, mot pour mot, et aucun tiret long dans les phrases ajoutees."""
        self.assertEqual(ocr.MESSAGES["motif_difficile"],
                         "Le texte de ce document est trop abîmé pour être lu. Ton PDF est resté tel quel.")
        self.assertEqual(ocr.MESSAGES["motif_vide"],
                         "Aucun texte n'a été trouvé dans ce document. Ton PDF est resté tel quel.")
        self.assertEqual(ocr.MESSAGES["motif_illisible"],
                         "Ce document n'a pas pu être lu. Ton PDF est resté tel quel.")
        self.assertEqual(ocr.MESSAGES["motif_verification"],
                         "Le PDF cherchable n'a pas passé la vérification. Ton PDF est resté tel quel.")
        self.assertEqual(ocr.MESSAGES["motif_ecriture"],
                         "Le résultat n'a pas pu être écrit. Ton PDF est resté tel quel.")
        self.assertEqual(ocr.MESSAGES["motif_erreur"],
                         "Cette opération n'a pas abouti. Ton PDF est resté tel quel.")
        self.assertEqual(ocr.MESSAGES["restauration_texte_garde"],
                         "Le PDF d'origine est remis. Le texte, que tu avais modifié, est resté en place.")
        self.assertEqual(ocr.MESSAGES["refaire_echec"],
                         "Ce document avait déjà été traité : ce nouvel essai n'a pas abouti. Ton PDF cherchable, "
                         "son texte et la copie de l'original sont restés en place.")
        for code in ("motif_difficile", "motif_vide", "motif_illisible", "motif_verification",
                     "motif_ecriture", "motif_erreur", "restauration_texte_garde", "refaire_echec"):
            for tiret in (chr(0x2013), chr(0x2014)):
                self.assertNotIn(tiret, ocr.MESSAGES[code], code)


class RestaurationSur(Banc):
    """3.3 : copie locale d'abord, puis le texte, `genere`, l'entree de cache et la copie."""

    def preparer(self, cfg=None, pages=(SCAN,)):
        self.poser(pages=list(pages))
        self.origine = octets(self.chemin)
        resultat = self.traiter(cfg)
        self.assertTrue(resultat["remplace"])
        self.entree = resultat["entree"]
        self.cherchable = octets(self.chemin)          # le PDF que MoodleSync vient de fabriquer
        self.copie, _ = ocr.chemin_original(self.dest, self.entree["empreinte"])
        self.assertTrue(os.path.isfile(self.copie))

    def test_restauration_depuis_la_copie(self):
        """O13 : le PDF d'origine est remis depuis la copie, octet pour octet ; le texte, `genere`, l'entree de
        cache et la copie disparaissent, et le fichier redevient « Non traite »."""
        self.preparer()
        self.assertNotEqual(octets(self.chemin), self.origine)
        resultat = ocr.restaurer(self.dest, self.rel, {})

        self.assertEqual(resultat, {"ok": True})
        self.assertEqual(octets(self.chemin), self.origine)
        self.assertIsNone(ocr.lire_marque(self.chemin))
        self.assertFalse(os.path.exists(self.chemin + ".md"))
        self.assertIsNone(self.entree_cache())
        self.assertFalse(os.path.isfile(self.copie))
        self.assertEqual(originaux(self.dest), [])
        self.assertNotIn("genere", ms.charger_etat(self.dest)[self.cle_etat])
        # Rien d'autre n'a bouge : ni l'etat de synchronisation de Moodle, ni un fichier temporaire.
        self.assertEqual(sorted(listage(self.dest)), sorted([self.rel, ms.ETAT]))
        self.assertEqual(ms.charger_etat(self.dest)[self.cle_etat]["t"], 1760000000)

    def test_restauration_d_un_texte_edite_le_garde(self):
        """O6, invariant 3 : un texte modifie a la main n'est jamais supprime, et la phrase de retour le dit."""
        self.preparer()
        texte = self.chemin + ".md"
        edition_non_regenerable(texte)
        edite = octets(texte)
        resultat = ocr.restaurer(self.dest, self.rel, {})

        self.assertEqual(resultat, {"ok": True, "message": ocr.MESSAGES["restauration_texte_garde"]})
        self.assertEqual(octets(self.chemin), self.origine)
        self.assertEqual(octets(texte), edite)
        self.assertIsNone(self.entree_cache())

    def test_restauration_d_un_texte_txt(self):
        """Le meme retrait pour un `.txt`, dont la protection est l'empreinte du cache (O6)."""
        self.preparer({"ocr_format": "txt"})
        texte = self.chemin + ".txt"
        self.assertTrue(os.path.isfile(texte))
        self.assertEqual(ocr.restaurer(self.dest, self.rel, {}), {"ok": True})
        self.assertEqual(octets(self.chemin), self.origine)
        self.assertFalse(os.path.exists(texte))
        self.assertIsNone(self.entree_cache())

    def test_restauration_sans_copie_retelecharge(self):
        """O13, U9 : un PDF migre n'a pas de copie ; l'original est retelecharge depuis Moodle et compare a
        `genere`, puis les memes suppressions ont lieu."""
        self.preparer()
        os.remove(self.copie)
        cache = ocr.charger_cache(self.dest)
        cache["documents"][self.rel]["original"] = None
        ocr.sauver_cache(self.dest, cache)

        serveur = FauxUrlopen(self.origine)
        with mock.patch.object(urllib.request, "urlopen", serveur):
            resultat = ocr.restaurer(self.dest, self.rel, {"token": "jeton-secret"})
        self.assertEqual(resultat, {"ok": True})
        self.assertEqual(len(serveur.requetes), 1)
        self.assertEqual(octets(self.chemin), self.origine)
        self.assertFalse(os.path.exists(self.chemin + ".md"))
        self.assertIsNone(self.entree_cache())
        self.assertNotIn("genere", ms.charger_etat(self.dest)[self.cle_etat])
        self.assertFalse([n for n in os.listdir(os.path.dirname(self.chemin)) if n.endswith((".part", ".tmp"))])

    def test_restauration_d_un_pdf_modifie_a_la_main_demande_confirmation(self):
        """E-V2-5 : un PDF retouche a la main apres le traitement n'est pas remis a l'original sans la
        confirmation `modifie_main` d'avant (sonde S9 de V2). Rien n'est touche avant l'accord.

        La retouche garde la taille du fichier : seule l'empreinte le distingue de celui que MoodleSync a
        fabrique (invariant 8), la mutation S3 qui ne compare que la taille doit donc etre vue ici."""
        self.preparer()
        with open(self.chemin, "r+b") as f:
            contenu = f.read()
            i = len(contenu) // 2                 # un octet change au milieu, meme nombre d'octets
            f.seek(i)
            f.write(bytes([contenu[i] ^ 0xFF]))
        retouche = octets(self.chemin)
        self.assertEqual(len(retouche), len(self.cherchable), "la retouche garde la taille")

        self.assertEqual(ocr.restaurer(self.dest, self.rel, {}), {"confirmer": ocr.MESSAGES["modifie_main"]})
        self.assertEqual(octets(self.chemin), retouche)
        self.assertEqual(originaux(self.dest), [self.entree["empreinte"].split(":", 1)[1] + ".pdf"])
        self.assertEqual(ocr.restaurer(self.dest, self.rel, {}, confirme=True), {"ok": True})
        self.assertEqual(octets(self.chemin), self.origine)
        self.assertIsNone(self.entree_cache())

    def test_restauration_d_un_document_sans_entree_de_cache(self):
        """Sans entree de cache et sans `genere`, le document est deja l'original : rien n'est supprime."""
        self.poser(pages=[NATIF])
        self.assertEqual(ocr.restaurer(self.dest, self.rel, {}), {"ok": True})
        self.assertEqual(sorted(listage(self.dest)), sorted([self.rel, ms.ETAT]))


if __name__ == "__main__":
    unittest.main()
