# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from PyQt5.QtWidgets import QWidget

from guardata.core.gui.lang import translate as _
from guardata.core.gui.ui.license_widget import Ui_LicenseWidget


class LicenseWidget(QWidget, Ui_LicenseWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.text_license.setHtml(_("TEXT_GUARDATA_LICENSE"))
