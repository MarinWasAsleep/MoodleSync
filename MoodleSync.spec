# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all
import sys

datas = []
binaries = []
hiddenimports = []
datas += collect_data_files('sv_ttk')
datas += [('MoodleSync.ico', '.')]      # icone des notifications (voir chemin_icone_image)
tmp_ret = collect_all('selenium')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['moodle_sync.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    # macOS : application MoodleSync.app (un dossier, pas un fichier unique, comme Apple l'attend).
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MoodleSync', console=False,
              argv_emulation=False, upx=False, icon=['MoodleSync.ico'])
    coll = COLLECT(exe, a.binaries, a.datas, name='MoodleSync', upx=False)
    app = BUNDLE(coll, name='MoodleSync.app', icon='MoodleSync.ico', bundle_identifier='ch.moodlesync',
                 info_plist={'NSHighResolutionCapable': True, 'CFBundleShortVersionString': '1.3',
                             'NSRequiresAquaSystemAppearance': False})
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='MoodleSync',
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
