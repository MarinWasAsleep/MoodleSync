# -*- mode: python ; coding: utf-8 -*-
# Compilation de Ma semaine (prototype) en un seul fichier : python -m PyInstaller MaSemaine.spec
# Resultat : dist/MaSemaine.exe. Utilise la connexion de MoodleSync (meme dossier de reglages).
# Avec pywebview installe : interface HTML (prototypes/interface). Sans : ancienne fenetre tkinter.
from PyInstaller.utils.hooks import collect_data_files, collect_all

datas = collect_data_files('sv_ttk') + [('MoodleSync.ico', '.'), ('prototypes/interface', 'interface')]
binaries, hiddenimports = [], ['seances', 'moodle_sync', 'application', 'pypdf']
try:
    import webview  # noqa: F401
    d, b, h = collect_all('webview')
    datas += d; binaries += b; hiddenimports += h
except ImportError:
    print("pywebview absent : MaSemaine.exe utilisera l'ancienne fenetre.")

a = Analysis(
    ['prototypes/ma_semaine.py'],
    pathex=['prototypes', '.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['selenium', 'test_seances', 'test_application'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MaSemaine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['MoodleSync.ico'],
)
