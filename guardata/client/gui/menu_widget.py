# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QWidget, QStyle, QStyleOption

from guardata.client.gui.ui.menu_widget import Ui_MenuWidget
from guardata.client.gui.lang import translate as _
from guardata.client.logged_client import OrganizationStats
from guardata.client.gui.file_size import get_filesize


class MenuWidget(QWidget, Ui_MenuWidget):
    files_clicked = pyqtSignal()
    users_clicked = pyqtSignal()
    devices_clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setupUi(self)
        self.button_files.clicked.connect(self.files_clicked.emit)
        self.button_users.clicked.connect(self.users_clicked.emit)
        self.button_devices.clicked.connect(self.devices_clicked.emit)
        self.button_files.apply_style()
        self.button_users.apply_style()
        self.button_devices.apply_style()
        self.icon_connection.apply_style()

    def paintEvent(self, _):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)

    def activate_files(self):
        self._deactivate_all()
        self.button_files.setChecked(True)

    def activate_devices(self):
        self._deactivate_all()
        self.button_devices.setChecked(True)

    def activate_users(self):
        self._deactivate_all()
        self.button_users.setChecked(True)

    def _deactivate_all(self):
        self.button_files.setChecked(False)
        self.button_users.setChecked(False)
        self.button_devices.setChecked(False)

    def show_organization_stats(self, organization_id: str, organization_stats: OrganizationStats):
        self.label_organization_name.show()
        self.label_organization_size.show()
        self.label_organization_name.setText(organization_id)
        self.label_organization_size.setText(
            _("TEXT_ORGANIZATION_SIZE_organizationsize").format(
                organizationsize=get_filesize(organization_stats.data_size)
            )
        )

    def set_connection_state(self, text, tooltip, icon):
        self.label_connection_state.setText(text)
        self.label_connection_state.setToolTip(tooltip)
        self.icon_connection.setPixmap(icon)
        self.icon_connection.apply_style()
