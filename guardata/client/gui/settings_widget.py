# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from guardata.client.client_events import ClientEvent
import platform

from PyQt5.QtWidgets import QWidget

from guardata.client.gui import lang
from guardata.client.gui.lang import translate as _
from guardata.client.gui.custom_dialogs import show_info
from guardata.client.gui.new_version import CheckNewVersion
from guardata.client.gui.ui.settings_widget import Ui_SettingsWidget


class SettingsWidget(QWidget, Ui_SettingsWidget):
    def __init__(self, client_config, jobs_ctx, event_bus, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client_config = client_config
        self.event_bus = event_bus
        self.jobs_ctx = jobs_ctx
        self.setupUi(self)

        if platform.system() != "Windows" and platform.system() != "Darwin":
            self.widget_version.hide()

        self.button_save.clicked.connect(self.save)
        self.check_box_tray.setChecked(self.client_config.gui_tray_enabled)
        current = None
        for lg, key in lang.LANGUAGES.items():
            self.combo_languages.addItem(lg, key)
            if key == self.client_config.gui_language:
                current = lg
        if current:
            self.combo_languages.setCurrentText(current)
        self.check_box_check_at_startup.setChecked(self.client_config.gui_check_version_at_startup)
        self.button_check_version.clicked.connect(self.check_version)
        self.check_box_show_confined.setChecked(self.client_config.gui_show_confined)

    def check_version(self):
        d = CheckNewVersion(self.jobs_ctx, self.event_bus, self.client_config, parent=self)
        d.open()

    def save(self):
        self.event_bus.send(
            ClientEvent.GUI_CONFIG_CHANGED,
            gui_tray_enabled=self.check_box_tray.isChecked(),
            gui_language=self.combo_languages.currentData(),
            gui_check_version_at_startup=self.check_box_check_at_startup.isChecked(),
        )
        show_info(self, _("TEXT_SETTINGS_NEED_RESTART"))
