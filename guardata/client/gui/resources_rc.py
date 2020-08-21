# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

try:
    from guardata.client.gui._resources_rc import *  # noqa
except ImportError as exc:
    raise ModuleNotFoundError(
        """PyQt resources bundle hasn't been generated.
You must install the guardata package or run `python setup.py generate_pyqt_resources_bundle`
"""
    ) from exc


if __name__ == "__main__":
    from PyQt5.QtCore import QDirIterator

    it = QDirIterator(":", QDirIterator.Subdirectories)
    while it.hasNext():
        print(it.next())
