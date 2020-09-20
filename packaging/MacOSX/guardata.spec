# -*- mode: python ; coding: utf-8 -*-
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import os
exec(open("../../guardata/_version.py", encoding="utf8").read())

pkgs_remove = [
  'tcl85',
  'tk85',
  '_tkinter',
  'libopenblas',
]

def remove(pkgs):
    for pkg in pkgs:
        a.binaries = [x for x in a.binaries if not x[0].startswith(pkg)]

a = Analysis(["../../guardata/client/cli/run_mac.py"],
             pathex=[os.path.dirname(os.path.abspath("guardata.spec"))],
             binaries=[],
             datas=[
                ("../../guardata/client/resources/guardata.icns", "guardata/client/resources/"),
                ("../../guardata/client/resources/default_pattern.ignore", "guardata/client/resources/"),
             ],
             hiddenimports=["pytzdata", "certifi"],
             hookspath=["hooks"],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=None,
             noarchive=False)
remove(pkgs_remove)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=None)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name="guardata-gui",
          icon="../../guardata/client/resources/guardata.icns",
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
            "NSHighResolutionCapable": True,
            'NSAppleScriptEnabled': False,
            "CFBundleIdentifier": "fr.bitlogik.guardata",
            "CFBundleName": "guardata",
            "CFBundleDisplayName": "guardata",
            "CFBundleShortVersionString": __version__,
            "LSApplicationCategoryType": "public.app-category.productivity",
            "LSMultipleInstancesProhibited": True,
         },
)

