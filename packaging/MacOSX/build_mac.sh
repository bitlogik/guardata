#!/bin/sh
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

cd ../..
python3 setup.py bdist_wheel
python3 -m pip install .
python3 -m pip install 'pyinstaller==4.0'
python3 -m pip install -U certifi
cd packaging/MacOSX
MACRUNfile='../../guardata/client/cli/run_mac.py'
echo 'import sys, pathlib ; from guardata.cli import cli' > $MACRUNfile
echo 'config_folder = pathlib.Path(pathlib.Path.home()/".config/guardata")' >> $MACRUNfile
echo 'config_folder.mkdir(parents=True, exist_ok=True)' >> $MACRUNfile
echo 'sys.argv = [sys.argv[0],"client","gui","--log-level=INFO",f"--log-file={config_folder}/guardata-client.log"]+sys.argv[1:]' >> $MACRUNfile
echo 'cli.main()' >> $MACRUNfile
pyinstaller guardata.spec
