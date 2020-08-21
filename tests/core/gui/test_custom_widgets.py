# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest

from guardata.core.gui import custom_widgets
from PyQt5.QtGui import QGuiApplication


@pytest.mark.gui
def test_file_line_edit(qtbot):

    w = custom_widgets.FileLabel(parent=None)
    qtbot.addWidget(w)

    w.setText("A_short_file_name.txt")
    assert w.text() == "A_short_file_name.txt"

    w.setText("A_longer_file_name_to_check_if_it_is_shortened.txt")
    if QGuiApplication.platformName() != "offscreen":
        assert w.text() == "A_longer_file_name_to_check_if_.."
    else:
        assert w.text() == "A_longer_file_name_to_check_if_it_is_shortened.txt"
