
set -eux

pip3 install -U testresources psutil
pip3 install -r pre-requirements.txt
python3 setup.py bdist_wheel
pip3 install $(ls dist/guardata-*.whl)[all]

mkdir -p empty
cp -R tests empty
cp setup.cfg empty
cd empty

/home/testuser/.local/bin/py.test --log-level=DEBUG --durations=10 -v tests --runmountpoint --runslow -n auto --max-worker-restart=0 -x
/home/testuser/.local/bin/py.test --log-level=DEBUG --durations=10 -v tests/backend tests/test_cli.py --postgresql --runslow -n auto --max-worker-restart=0
