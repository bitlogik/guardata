
set -eux

pip3 install -U testresources psutil
pip3 install -r pre-requirements.txt
python3 setup.py bdist_wheel
rm -Rf guardata
pip3 install $(ls dist/guardata-*.whl)[all]

mkdir -p dir4tests
cp -R tests dir4tests
cp setup.cfg dir4tests
cd dir4tests

/home/testuser/.local/bin/py.test --log-level=DEBUG --durations=10 -v tests --runmountpoint --runslow -n auto --max-worker-restart=0 -x
/home/testuser/.local/bin/py.test --log-level=DEBUG --durations=10 -v tests/backend tests/test_cli.py --postgresql --runslow -n auto --max-worker-restart=0
