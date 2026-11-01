# -*- mode: python ; coding: utf-8 -*-
# Compilation de Ma semaine (prototype) en un seul fichier : python -m PyInstaller MaSemaine.spec
# Resultat : dist/MaSemaine.exe. Utilise la connexion de MoodleSync (meme dossier de reglages).
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['prototypes/ma_semaine.py'],
    pathex=['prototypes', '.'],
    binaries=[],
    datas=collect_data_files('sv_ttk') + [('MoodleSync.ico', '.')],
    hiddenimports=['seances', 'moodle_sync', 'pypdf'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['selenium', 'test_seances'],
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
