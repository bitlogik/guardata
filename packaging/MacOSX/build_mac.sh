#!/bin/sh
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

cd ../..
python3 setup.py bdist_wheel
cd packaging/MacOSX
python3 -m pip install 'pyinstaller==4.0'
python3 -m pip install -U certifi
echo 'from guardata.client.cli import run' > ../../guardata/client/cli/run_mac.py
echo 'run.run_gui()' >> ../../guardata/client/cli/run_mac.py
pyinstaller guardata.spec
