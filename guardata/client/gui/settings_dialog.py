# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from PyQt5.QtWidgets import QDialog

from guardata.client.gui.settings_widget import SettingsWidget
from guardata.client.gui.ui.settings_dialog import Ui_SettingsDialog


class SettingsDialog(QDialog, Ui_SettingsDialog):
    def __init__(self, config, jobs_ctx, event_bus, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setupUi(self)
        self.event_bus = event_bus
        s = SettingsWidget(config, jobs_ctx, self.event_bus)
        s.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().insertWidget(0, s)
        self.button_close.clicked.connect(self.accept)
