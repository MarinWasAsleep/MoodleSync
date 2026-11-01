# -*- mode: python ; coding: utf-8 -*-
# Compilation de MoodleSync : python -m PyInstaller --noconfirm --clean MoodleSync.spec
# Windows : dist/MoodleSync.exe (un seul fichier, sans console). macOS : dist/MoodleSync.app.
# Dependances : requirements-compilation.txt. Version : moodlesync/__init__.py (seule source).
import os, re, sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

RACINE = os.path.abspath(SPECPATH)
with open(os.path.join(RACINE, "moodlesync", "__init__.py"), encoding="utf-8") as f:
    VERSION = re.search(r'^VERSION\s*=\s*"(\d+(?:\.\d+){0,3})"', f.read(), re.M).group(1)
NUMEROS = tuple(int(x) for x in (VERSION.split(".") + ["0"] * 4)[:4])     # "X.Y" -> (X, Y, 0, 0)

datas = [("MoodleSync.ico", "."),                                  # icone des notifications (moteur.chemin_icone_image)
         ("moodlesync/interface", "interface")]                    # la page (application.dossier_interface)
binaries = []
# Les imports de ces modules sont faits a l'interieur des fonctions : on les declare.
hiddenimports = collect_submodules("moodlesync") + ["pypdf"]
for paquet in ("selenium", "webview"):                             # selenium : Selenium Manager ; webview : scripts JS
    d, b, h = collect_all(paquet)
    datas += d; binaries += b; hiddenimports += h
if sys.platform == "darwin":
    hiddenimports += ["certifi"]                                  # certificats HTTPS (moteur, debut du fichier)
    datas += collect_all("certifi")[0]

a = Analysis(
    ["lancer.py"],
    pathex=[RACINE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests"],
    noarchive=False,
    optimize=0,
)


def autre_systeme(entree):
    """Selenium Manager existe en un executable par systeme (le hook de selenium les embarque tous) :
    on ne garde que celui de la plateforme compilee."""
    parties = os.path.normpath(entree[0]).split(os.sep)
    garder = "macos" if sys.platform == "darwin" else "windows"
    return parties[-1].startswith("selenium-manager") and not parties[-1].endswith((".txt", ".json")) \
        and len(parties) > 1 and parties[-2] != garder


a.datas = [e for e in a.datas if not autre_systeme(e)]
a.binaries = [e for e in a.binaries if not autre_systeme(e)]
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    # macOS : application MoodleSync.app (un dossier, pas un fichier unique, comme Apple l'attend).
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MoodleSync", console=False,
              argv_emulation=False, upx=False, icon=["MoodleSync.ico"])
    coll = COLLECT(exe, a.binaries, a.datas, name="MoodleSync", upx=False)
    app = BUNDLE(coll, name="MoodleSync.app", icon="MoodleSync.ico", bundle_identifier="ch.moodlesync",
                 version=VERSION,
                 info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": VERSION,
                             "CFBundleVersion": VERSION, "NSRequiresAquaSystemAppearance": False})
else:
    from PyInstaller.utils.win32.versioninfo import (VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
                                                     StringStruct, VarFileInfo, VarStruct)
    texte = ".".join(str(n) for n in NUMEROS)
    version_windows = VSVersionInfo(
        ffi=FixedFileInfo(filevers=NUMEROS, prodvers=NUMEROS, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1,
                          subtype=0x0, date=(0, 0)),
        kids=[StringFileInfo([StringTable("040C04B0", [                # francais (040C), Unicode (04B0)
            StringStruct("ProductName", "MoodleSync"),
            StringStruct("FileDescription", "MoodleSync"),
            StringStruct("FileVersion", texte),
            StringStruct("ProductVersion", texte),
            StringStruct("InternalName", "MoodleSync"),
            StringStruct("OriginalFilename", "MoodleSync.exe"),
            StringStruct("LegalCopyright", "Licence MIT"),
        ])]), VarFileInfo([VarStruct("Translation", [0x040C, 1200])])])
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="MoodleSync",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,                     # UPX augmente les fausses alertes des antivirus
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=["MoodleSync.ico"],
        version=version_windows,
    )
