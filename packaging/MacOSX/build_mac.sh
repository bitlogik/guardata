#!/bin/sh
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

cd ../..
python3 setup.py bdist_wheel
python3 -m pip install .
python3 -m pip install 'pyinstaller==4.1'
python3 -m pip install -U certifi
cd packaging/MacOSX
MACRUNfile='../../guardata/client/cli/run_mac.py'
echo 'import sys, pathlib, os, locale ; from guardata.cli import cli' > $MACRUNfile
echo 'config_folder = pathlib.Path(pathlib.Path.home()/".config/guardata")' >> $MACRUNfile
echo 'config_folder.mkdir(parents=True, exist_ok=True)' >> $MACRUNfile
echo 'os.environ["QT_MAC_WANTS_LAYER"] = "1"' >> $MACRUNfile
echo 'locale.setlocale(locale.LC_ALL, "")' >> $MACRUNfile
echo 'argsv = ["client","gui","--log-level=INFO",f"--log-file={config_folder}/guardata-client.log",*sys.argv[1:]]' >> $MACRUNfile
echo 'cli(argsv)' >> $MACRUNfile
pyinstaller guardata.spec
