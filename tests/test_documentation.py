"""Documentation de la 2.5 et de la 3.0 : forme et liens avec le code (ecart 286 de la revue de P3).

Aucun reseau, aucune fenetre. Les cinq documents que la 2.5 a ecrits ou modifies sont lus sur le disque :
`README.md`, `CONTRIBUTING.md`, `docs/notes-version.md`, `docs/tiers.md` et `docs/LISEZ-MOI.txt`.

Ce que ces tests tiennent : fins de ligne LF, aucun tiret long ni demi-cadratin, vocabulaire du contrat 3.4 (aucun
« OCR » ni « Tesseract » dans ce que lit l'etudiant), et les valeurs que les documents recopient du code (noms,
empreintes et version de pypdfium2) egales a celles du code. Depuis la 3.0, ils tiennent aussi ce que les trois
documents d'etudiant disent de l'onglet « Mes textes » refait (contrat 5.5, decisions U2, U6, U9) : les trois
sous-onglets, le texte a cote du PDF dans les deux formats, le depot, et les limites qui restent vraies. Ce qu'ils
ne tiennent pas : que les phrases soient justes ; cela se lit.

Lancer depuis la racine du depot : python -m unittest discover -s tests -t .
"""
import os, re, sys, unicodedata, unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from moodlesync import ocr

def present(*parties):
    """Vrai si le document existe : le depot public ne porte que les documents d'etudiant, pas ceux du chantier."""
    return os.path.exists(os.path.join(RACINE, *parties))


def sans_le_document(*parties):
    """Ignore une classe de tests quand le document qu'elle lit n'est pas dans ce depot (public : documents du chantier absents)."""
    return unittest.skipUnless(present(*parties), "%s absent de ce depot" % "/".join(parties))


DOCUMENTS = tuple(nom for nom in ("README.md", "CONTRIBUTING.md", os.path.join("docs", "notes-version.md"),
                                  os.path.join("docs", "tiers.md"), os.path.join("docs", "LISEZ-MOI.txt"))
                  if present(nom))
# Ce que lit l'etudiant : le contrat 3.4 n'y veut ni OCR ni Tesseract. CONTRIBUTING et tiers.md parlent aux developpeurs.
POUR_L_ETUDIANT = ("README.md", os.path.join("docs", "notes-version.md"), os.path.join("docs", "LISEZ-MOI.txt"))


def lire(nom):
    with open(os.path.join(RACINE, nom), "rb") as f:
        return f.read().decode("utf-8")


NOTES = os.path.join("docs", "notes-version.md")
# Premiere section datee des notes de version : au-dessus, la 3.0 ; a partir d'ici, l'historique, laisse tel quel
# (2.5.1 et anterieures decrivent l'onglet d'avant et gardent leurs mots).
HISTORIQUE = "## Nouveautés de la 2.5.1"
# Sous-partie des notes de la 3.0 qui dit ce qui a change pour ceux qui mettent a jour : elle nomme les fonctions
# et les reglages disparus pour dire qu'ils ont disparu, ce qui n'est pas les annoncer.
MIGRATION = "### Si tu mets à jour depuis la 2.x"


def lire_partie_3_0(nom):
    """Partie 3.0 d'un document d'etudiant : le document entier, sauf dans les notes de version, ou l'historique
    date commence a `HISTORIQUE`."""
    texte = lire(nom)
    return texte.split(HISTORIQUE, 1)[0] if nom == NOTES else texte


def lire_nouveautes(nom):
    """Partie de la 3.0 qui annonce ce que la version apporte, sans le paragraphe de migration des notes."""
    texte = lire_partie_3_0(nom)
    if nom == NOTES and MIGRATION in texte:
        avant, suite = texte.split(MIGRATION, 1)
        suite = "### " + suite.split("### ", 1)[1] if "### " in suite else ""
        return avant + suite
    return texte


def sans_accents(texte):
    """Texte replie sur ses lettres de base : `docs/LISEZ-MOI.txt` est ecrit sans accents (comme ses 235 lignes
    d'origine) et doit pouvoir citer les libelles de l'interface, qui portent les leurs (contrat 5.5)."""
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


class FormeDesDocuments(unittest.TestCase):
    def test_fins_de_ligne_lf(self):
        for nom in DOCUMENTS:
            with self.subTest(document=nom):
                self.assertNotIn("\r", lire(nom))

    def test_aucun_tiret_long(self):
        for nom in DOCUMENTS:
            for tiret in (chr(0x2013), chr(0x2014)):
                with self.subTest(document=nom, tiret=hex(ord(tiret))):
                    self.assertNotIn(tiret, lire(nom))

    def test_vocabulaire_du_contrat_3_4(self):
        for nom in POUR_L_ETUDIANT:
            with self.subTest(document=nom):
                trouves = re.findall(r"\b(ocr|tesseract)\b", lire(nom), flags=re.I)
                self.assertEqual(trouves, [], "mot interdit dans ce que lit l'etudiant")

    def test_aucune_phrase_sur_une_installation_non_branchee(self):
        """L'installation des deux paquets est branchee (ecart 279) : aucun document ne dit le contraire."""
        for nom in DOCUMENTS:
            with self.subTest(document=nom):
                texte = lire(nom).lower()
                for faux in ("pas encore branchée", "pas encore branchee", "installation_indisponible` et renvoie"):
                    self.assertNotIn(faux, texte)


@sans_le_document("docs", "tiers.md")
class LiensAvecLeCode(unittest.TestCase):
    def test_tiers_cite_les_noms_et_les_empreintes_du_code(self):
        tiers = lire(os.path.join("docs", "tiers.md"))
        for plateforme in ("win32", "darwin"):
            with self.subTest(plateforme=plateforme):
                self.assertIn(ocr.NOM_PAQUET[plateforme], tiers)
                self.assertIn(ocr.EMPREINTE_PAQUET[plateforme], tiers)

    def test_tiers_cite_la_version_epinglee_de_pypdfium2(self):
        pin = re.search(r"^pypdfium2==([0-9.]+)", lire("requirements.txt"), flags=re.M | re.I)
        self.assertTrue(pin, "pypdfium2 est epinglee dans requirements.txt")
        tiers = lire(os.path.join("docs", "tiers.md"))
        self.assertIn("pypdfium2 " + pin.group(1), tiers)
        for retiree in re.findall(r"pypdfium2 (5\.\d+\.\d+)", tiers):
            self.assertEqual(retiree, pin.group(1), "une autre version de pypdfium2 est citee comme la version employee")

    def test_la_limite_de_restauration_est_ecrite(self):
        """U1 et U9 : la copie de l'original n'existe que depuis la 3.0, donc un PDF remplace avant elle ne se
        restaure que par Moodle. CONTRIBUTING (hors perimetre de R13) garde la comparaison qui s'applique alors."""
        formes = {"README.md": r"remplacé avant cette version n'a pas de copie",
                  "CONTRIBUTING.md": r"à la main avant le premier remplacement",
                  NOTES: r"remplacé avant cette version n'a pas de copie"}
        for nom, forme in formes.items():
            with self.subTest(document=nom):
                texte = lire_partie_3_0(nom) if nom in POUR_L_ETUDIANT else lire(nom)
                texte = re.sub(r"\s+", " ", texte.replace("*", ""))      # retours a la ligne et gras mis a plat
                self.assertRegex(texte, forme)

    PHRASE_MACOS_13 = r"Sous macOS 11 et 12, le rendu des PDF est indisponible[^.]*macOS 13 ou plus"

    def test_la_limite_macos_13_est_annoncee_a_l_utilisateur(self):
        """Ecart 17 : pypdfium2 n'a de roue macOS qu'a partir de macOS 13 (requirements.txt). La limite est dite dans
        les Limites connues du README et dans les notes de version, pas seulement dans le fichier des dependances."""
        readme = re.sub(r"\s+", " ", lire("README.md").replace("*", ""))
        limites = readme.split("Limites connues", 1)[1].split("</details>", 1)[0]   # bloc repliable du README refait
        notes = re.sub(r"\s+", " ", lire(os.path.join("docs", "notes-version.md")).replace("*", ""))
        self.assertRegex(limites, r"Sous macOS 11 et 12, la préparation d'un PDF scanné est indisponible", "README.md, Limites connues")
        self.assertRegex(notes, self.PHRASE_MACOS_13, "docs/notes-version.md")
        self.assertIn("macOS 13", lire("requirements.txt"), "la limite vient de requirements.txt")

    def test_contributing_dit_vrai_sur_les_refus(self):
        """Ecart 280 : `non_suivi` = aucune entree dans `.moodlesync.json` ; `modifie_main` refuse sans confirmation."""
        texte = lire("CONTRIBUTING.md")
        self.assertNotIn("sans la marque du programme est refusé", texte)
        self.assertNotIn("un fichier modifié à la main demande une confirmation", texte)
        self.assertIn("aucune entrée dans `.moodlesync.json`", texte)


@sans_le_document("docs", "plan-ocr.md")
class PlanEnDeuxPointCinq(unittest.TestCase):
    """Constat 298 : les dix passages de `docs/plan-ocr.md` remis en accord avec la 2.5 (ecart 293) sont gardes."""

    PASSAGES = (
        "télécharge le moteur dès la 2.5",
        "**Version 2.5 : installation automatique par paquet.**",
        "**Paquet portable (2.5).**",
        "installé par MoodleSync (2.5)",
        "Le bouton **Installer** télécharge le moteur à ta place",
        "dès la 2.5, le téléchargement du paquet portable",
        "par paquet portable (2.5, deux paquets",
        "installation par paquet portable (2.5)",
        "Il est livré dans la 2.5",
        "paquet portable dès la 2.5",
    )

    def setUp(self):
        self.plan = lire(os.path.join("docs", "plan-ocr.md"))

    def test_les_dix_passages_disent_2_5(self):
        for passage in self.PASSAGES:
            with self.subTest(passage=passage):
                self.assertIn(passage, self.plan)

    def test_le_plan_ne_renvoie_plus_l_installation_a_la_2_6(self):
        self.assertEqual(re.findall(r"(?<![\d.])2\.6(?!\d)", self.plan), [])
        for faux in ("pas d'installation automatique", "pas d’installation automatique"):
            self.assertNotIn(faux, self.plan.lower())


@sans_le_document("docs", "ocr-contrat.md")
class ContratNommeDesTestsReels(unittest.TestCase):
    """Constat 296 : chaque nom de test de la section 6 du contrat (T1 a T32) existe dans `tests/`.

    Le bandeau en tete de `docs/ocr-contrat.md` (R12) dit que `docs/refonte-textes/contrat.md` fait foi pour
    les sections qu'il remplace. Cinq lignes du tableau nomment des tests que la refonte a retires avec
    l'onglet d'avant (R1a, R4) : pour celles-la, le test ne demande plus l'ancien nom, il prouve que ce que
    ce nom mesurait a disparu et que le nouveau contrat le declare retire. Toute autre ligne manquante
    reste un echec, et retirer le bandeau fait echouer les preuves.
    """

    NOUVEAU_CONTRAT = os.path.join("docs", "refonte-textes", "contrat.md")
    BANDEAU = "Remplacé en partie par `docs/refonte-textes/contrat.md`"

    # ligne du tableau : (nom retire, fonction du nouveau contrat qui le remplace, section du nouveau contrat)
    RETIRES = {
        "T24": ("test_apercu_sans_ecriture", "ocr_apercu", "4.8"),
        "T27": ("test_contexte_copiable", "ocr_copier", "4.8"),
        "T31": ("ReglagesT31", "ocr_lancer", "4.8"),
        "T32": ("MiseEnFileT32", "mettre_en_file_apres_sync", "3.5"),
    }
    # ligne dont le test a seulement change de nom : le sujet est garde par un autre test.
    REMPLACES = {"T28": ("test_message_ne_porte_pas_de_tiret_long", "test_aucun_tiret_long")}

    def noms_du_tableau(self):
        contrat = lire(os.path.join("docs", "ocr-contrat.md"))
        section = contrat.split("## 6.", 1)[1].split("## 7.", 1)[0]
        lignes = [l for l in section.splitlines() if re.match(r"\|\s*T\d+\s*\|", l)]
        return {l.split("|")[1].strip(): re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", l.split("|")[2]) for l in lignes}

    def sources_des_tests(self):
        dossier = os.path.join(RACINE, "tests")
        sources = []
        for nom in sorted(os.listdir(dossier)):
            if nom.endswith(".py"):
                with open(os.path.join(dossier, nom), "rb") as f:
                    sources.append(f.read().decode("utf-8"))
        return "\n".join(sources)

    def sources_du_code(self):
        dossier = os.path.join(RACINE, "moodlesync")
        sources = []
        for nom in sorted(os.listdir(dossier)):
            if nom.endswith(".py"):
                with open(os.path.join(dossier, nom), "rb") as f:
                    sources.append(f.read().decode("utf-8"))
        return "\n".join(sources)

    def bandeau_present(self):
        tetiere = lire(os.path.join("docs", "ocr-contrat.md")).split("## 1.", 1)[0]
        return self.BANDEAU in tetiere

    def section_du_nouveau_contrat(self, numero):
        """Texte de la section `numero` (par exemple « 4.8 ») du nouveau contrat, ou ''."""
        morceaux = lire(self.NOUVEAU_CONTRAT).split("### %s" % numero, 1)
        if len(morceaux) < 2:
            return ""
        return morceaux[1].split("\n## ", 1)[0]

    def test_le_tableau_porte_t1_a_t32(self):
        self.assertEqual(sorted(self.noms_du_tableau(), key=lambda t: int(t[1:])), ["T%d" % n for n in range(1, 33)])

    def test_lignes_retirees_prouvees(self):
        """Chaque ligne declaree retiree est encore au tableau, et sa preuve existe dans le nouveau contrat."""
        tableau = self.noms_du_tableau()
        code, sources = self.sources_du_code(), self.sources_des_tests()
        self.assertTrue(self.bandeau_present(), "le bandeau de R12 a disparu de la tete de docs/ocr-contrat.md")
        for ligne, (nom, fonction, section) in self.RETIRES.items():
            with self.subTest(ligne=ligne):
                self.assertIn(ligne, tableau, "la ligne %s du tableau a disparu" % ligne)
                self.assertIn(nom, tableau[ligne], "la ligne %s ne nomme plus %s" % (ligne, nom))
                self.assertNotRegex(sources, r"(?m)^\s*(def|class) %s\b" % re.escape(nom),
                                    "%s existe encore dans tests/ : il n'est donc pas retire" % nom)
                texte = self.section_du_nouveau_contrat(section)
                self.assertTrue(texte, "le nouveau contrat n'a plus de section %s" % section)
                self.assertIn(fonction, texte, "la section %s du nouveau contrat ne declare plus %s retire" % (section, fonction))
                self.assertNotRegex(code, r"(?m)^\s*def %s\b" % re.escape(fonction),
                                    "%s existe encore dans moodlesync/ : il n'est donc pas retire" % fonction)
        for ligne, (ancien, nouveau) in self.REMPLACES.items():
            with self.subTest(ligne=ligne):
                self.assertIn(ligne, tableau, "la ligne %s du tableau a disparu" % ligne)
                self.assertIn(ancien, tableau[ligne], "la ligne %s ne nomme plus %s" % (ligne, ancien))
                self.assertRegex(sources, r"(?m)^\s*(def|class) %s\b" % re.escape(nouveau),
                                 "le remplacant de %s (%s) n'existe pas" % (ancien, nouveau))

    def test_chaque_nom_du_tableau_existe(self):
        sources = self.sources_des_tests()
        for test, noms in self.noms_du_tableau().items():
            with self.subTest(test=test):
                self.assertTrue(noms, "aucun nom de test dans la ligne")
                for nom in noms:
                    if re.search(r"(?m)^\s*(def|class) %s\b" % re.escape(nom), sources):
                        continue                                   # la ligne tient toujours
                    if test in self.RETIRES and self.RETIRES[test][0] == nom:
                        continue                                   # prouve par test_lignes_retirees_prouvees
                    if test in self.REMPLACES and self.REMPLACES[test][0] == nom:
                        nouveau = self.REMPLACES[test][1]
                        self.assertRegex(sources, r"(?m)^\s*(def|class) %s\b" % re.escape(nouveau),
                                         "%s : %s n'existe pas et son remplacant %s non plus" % (test, nom, nouveau))
                        continue
                    self.fail("%s : %s n'existe pas dans tests/ et la refonte ne le declare pas retire" % (test, nom))


BROUILLON = os.path.join("docs", "refonte-textes", "notes-version-brouillon.md")


@sans_le_document("docs", "refonte-textes", "notes-version-brouillon.md")
class BrouillonDeNotes(unittest.TestCase):
    """R12 : brouillon des notes de la prochaine version, non publie.

    Il n'est pas encore montre a l'etudiant, mais il deviendra ce texte-la : sa forme et son vocabulaire
    sont tenus ici comme ceux des notes publiees (contrat 5.5 : ni « OCR » ni « Tesseract » dans ce que lit
    l'etudiant), et ses trois limites sont exigees en toutes lettres.
    """

    def test_fichier_en_lf_et_sans_tiret_long(self):
        texte = lire(BROUILLON)
        self.assertNotIn("\r", texte, "fichier en LF")
        self.assertEqual(texte.count(chr(0x2014)), 0, "aucun tiret cadratin")
        self.assertEqual(texte.count(chr(0x2013)), 0, "aucun tiret demi-cadratin")
        self.assertTrue(texte.endswith("\n"), "saut de ligne final")

    def test_vocabulaire_du_contrat_3_4(self):
        self.assertEqual(re.findall(r"\b(ocr|tesseract)\b", lire(BROUILLON), flags=re.I), [],
                         "mot interdit dans ce que lit l'etudiant")

    def test_aucune_version_annoncee(self):
        """Le numero de version et la date ne sont pas decides : le brouillon ne les invente pas."""
        texte = lire(BROUILLON)
        self.assertIn("brouillon", texte.splitlines()[0].lower(), "le titre dit que ce n'est pas publie")
        self.assertIsNone(re.search(r"\b2\.\d", texte), "aucun numero de version annonce")

    def test_les_nouveautes_et_leurs_limites(self):
        texte = lire(BROUILLON)
        nouveautes = [l for l in texte.split("### Ce que ça ne promet pas", 1)[0].splitlines() if l.startswith("- ")]
        self.assertGreaterEqual(len(nouveautes), 6, "les nouveautes de la refonte sont listees")
        self.assertIn("### Ce que ça ne promet pas", texte)
        limites = texte.split("### Ce que ça ne promet pas", 1)[1]
        for sujet, mot in (("glisser-deposer jamais essaye sur un vrai poste (O16)", "glisser"),
                           ("copies d'originaux qui occupent de la place (U1, O15)", "place"),
                           ("PDF migres sans copie d'original (U9, O13)", "copie")):
            with self.subTest(sujet=sujet):
                self.assertIn(mot, limites, "limite non dite : %s" % sujet)


@sans_le_document("docs", "refonte-textes", "avancement.md")
class RenvoiDeLaRefonte(unittest.TestCase):
    """R12 : les deux documents de la 2.5 renvoient a la refonte, sans que leur texte soit reecrit."""

    def test_le_bandeau_du_contrat_est_en_tete(self):
        tetiere = lire(os.path.join("docs", "ocr-contrat.md")).split("## 1.", 1)[0]
        self.assertIn("Remplacé en partie par `docs/refonte-textes/contrat.md`", tetiere)
        for section in ("2.6", "2.7", "3.4"):
            with self.subTest(section=section):
                self.assertIn(section, tetiere, "le bandeau nomme la section remplacee %s" % section)
        self.assertIn("le nouveau contrat fait foi", tetiere)

    def test_l_avancement_renvoie_a_la_refonte(self):
        texte = lire(os.path.join("docs", "ocr-avancement.md"))
        section = texte.split("## 2. État des tâches", 1)[1].split("## 3.", 1)[0]
        tetiere = "\n".join(section.splitlines()[:4])
        self.assertIn("docs/refonte-textes/avancement.md", tetiere,
                      "la tete de la section 2 renvoie a l'avancement de la refonte")


class Version3DansLesDocumentsEtudiants(unittest.TestCase):
    """R13 : les trois documents d'etudiant decrivent la 3.0, et plus l'onglet d'avant.

    Ce que ces tests tiennent : les trois sous-onglets du contrat 5.5, le texte a cote du PDF dans les deux
    formats (U2, U12), le depot (U3, U8), la restauration (U10, O18), et l'absence de ce que la refonte a
    retire (U6, contrat 6). Ce qu'ils ne tiennent pas : la justesse des phrases ; cela se lit.
    """

    # Ce que l'onglet d'avant avait et que la 3.0 n'a plus : ces mots ne reviennent pas dans la 3.0, sauf dans
    # l'historique date des notes de version (section 2.5.1 et anterieures).
    DISPARUS = ("version cherchable des pdf", "extraction automatique", "index.md")
    # Fonctions retirees par U6 : plus une ligne ne les annonce comme fonctions de la 3.0. Le paragraphe de
    # migration des notes les nomme pour dire qu'elles ont disparu (prompt 21, point 3) : il est hors du champ.
    RETIRES = ("chercher un mot", "cherche un mot", "recherche par mot", "export", "aperçu")

    def test_les_reglages_et_les_dossiers_disparus_ne_reviennent_pas(self):
        for nom in POUR_L_ETUDIANT:
            texte = sans_accents(lire_partie_3_0(nom)).lower()
            for mot in self.DISPARUS:
                with self.subTest(document=nom, mot=mot):
                    self.assertNotIn(sans_accents(mot), texte, "mot de l'onglet d'avant dans la 3.0")

    def test_la_recherche_l_export_et_l_apercu_ne_sont_plus_annonces(self):
        for nom in POUR_L_ETUDIANT:
            texte = sans_accents(lire_nouveautes(nom).lower())
            for mot in self.RETIRES:
                with self.subTest(document=nom, mot=mot):
                    self.assertNotIn(sans_accents(mot), texte, "fonction retiree (U6) encore annoncee")

    def test_les_trois_sous_onglets_sont_nommes(self):
        for nom in POUR_L_ETUDIANT:
            texte = sans_accents(lire_partie_3_0(nom))
            for onglet in ("Mes cours", "Choisir quoi traiter", "Déposer des fichiers"):
                with self.subTest(document=nom, onglet=onglet):
                    self.assertIn(sans_accents(onglet), texte)

    def test_le_texte_est_a_cote_du_pdf_dans_les_deux_formats(self):
        """U2 et U12 : `<nom>.pdf.md` a cote du PDF, ou `.txt` au choix dans les reglages."""
        for nom in POUR_L_ETUDIANT:
            texte = sans_accents(lire_partie_3_0(nom))
            for attendu in ("article.pdf.md", "article.pdf.txt", "à côté"):
                with self.subTest(document=nom, attendu=attendu):
                    self.assertIn(sans_accents(attendu), texte)

    def test_le_depot_hors_moodle_et_la_restauration_sont_dits(self):
        """U3, U8 et U10 : le depot, son dossier par defaut, le bouton de choix, et « Restaurer l'original »."""
        for nom in POUR_L_ETUDIANT:
            texte = sans_accents(lire_partie_3_0(nom)).lower()
            for attendu in ("documents déposés", "restaurer l'original", "choisir des fichiers"):
                with self.subTest(document=nom, attendu=attendu):
                    self.assertIn(sans_accents(attendu), texte)


class LimitesDeLaTroisZero(unittest.TestCase):
    """R13 : les limites de la 3.0 sont dites dans les notes de version, sous « Ce que cette version ne promet
    pas » (prompt 21, point 2). Une phrase retiree fait echouer son sous-test : le journal R13 donne la mutation
    de chacune. Aucune de ces limites n'est mesurable dans ce conteneur (revue V7, section 9) : les taire serait
    promettre ce qui n'a pas ete essaye."""

    TITRE = "### Ce que cette version ne promet pas"
    LIMITES = (
        ("glisser-déposer jamais essayé sur un vrai poste Windows ou macOS (O16)",
         r"glisser-déposer n'a jamais été essayé sur un vrai poste Windows ou macOS"),
        ("copies d'originaux qui occupent de la place (U1, O15)",
         r"copie de chaque original occupe de la place"),
        ("PDF remplacés avant la 3.0, sans copie d'original (U9, O13)",
         r"remplacé avant cette version n'a pas de copie"),
        ("texte en .txt laissé tel quel si le cache disparaît (O6)",
         r"laissé tel quel si le cache de reconnaissance"),
        ("fenêtre jamais vue sur Windows et sur macOS (revue V7, section 9)",
         r"jamais été vue sur Windows"),
        ("Ctrl+F jamais essayé dans un vrai lecteur de PDF (revue V7, section 9)",
         r"jamais été essayée dans un lecteur de PDF"),
    )

    def setUp(self):
        self.assertTrue(lire(NOTES).count(self.TITRE) == 1, "la sous-partie des limites est unique dans les notes")
        self.notes = re.sub(r"\s+", " ", lire_partie_3_0(NOTES).replace("*", ""))

    def test_les_six_limites_sont_dites(self):
        for sujet, forme in self.LIMITES:
            with self.subTest(limite=sujet):
                self.assertRegex(self.notes, forme)


if __name__ == "__main__":
    unittest.main()
