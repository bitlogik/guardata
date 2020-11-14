#!/bin/sh
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

cd ../..
python3 setup.py bdist_wheel
python3 -m pip --use-feature=2020-resolver install .
python3 -m pip --use-feature=2020-resolver install 'pyinstaller==4.0'
python3 -m pip --use-feature=2020-resolver install -U certifi
cd packaging/MacOSX
MACRUNfile='../../guardata/client/cli/run_mac.py'
echo 'import sys, pathlib ; from guardata.cli import cli' > $MACRUNfile
echo 'config_folder = pathlib.Path(pathlib.Path.home()/".config/guardata")' >> $MACRUNfile
echo 'config_folder.mkdir(parents=True, exist_ok=True)' >> $MACRUNfile
echo 'argsv = ["client","gui","--log-level=INFO",f"--log-file={config_folder}/guardata-client.log",*sys.argv[1:]]' >> $MACRUNfile
echo 'cli(argsv)' >> $MACRUNfile
pyinstaller guardata.spec
