# -*- mode: python ; coding: utf-8 -*-

import os
exec(open("../../guardata/_version.py", encoding="utf8").read())


block_cipher = None


a = Analysis(["../../guardata/cli.py"],
             pathex=[os.path.dirname(os.path.abspath("app.spec"))],
             binaries=[],
             datas=[],
             hiddenimports=["pytzdata"],
             hookspath=["hooks"],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name="guardata",
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name="guardata")
app = BUNDLE(coll,
    name="guardata.app",
    icon="../../guardata/client/resources/guardata.icns",
    bundle_identifier="fr.bitlogik.guardata",
    info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSAppleScriptEnabled': False,
            "CFBundleIdentifier": "fr.bitlogik.guardata",
            "CFBundleName": "guardata",
            "CFBundleDisplayName": "guardata",
            "CFBundleShortVersionString": __version__,
            "LSApplicationCategoryType": "public.app-category.productivity",
            "LSMultipleInstancesProhibited": True,
         },
)

