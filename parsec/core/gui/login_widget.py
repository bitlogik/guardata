# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from pathlib import Path

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget

from parsec.core.local_device import list_available_devices
from parsec.api.protocol import OrganizationID, DeviceID

from parsec.core.gui.lang import translate as _
from parsec.core.gui.parsec_application import ParsecApp
from parsec.core.gui.ui.login_widget import Ui_LoginWidget
from parsec.core.gui.ui.account_button import Ui_AccountButton
from parsec.core.gui.ui.login_accounts_widget import Ui_LoginAccountsWidget
from parsec.core.gui.ui.login_password_input_widget import Ui_LoginPasswordInputWidget
from parsec.core.gui.ui.login_no_devices_widget import Ui_LoginNoDevicesWidget


class AccountButton(QWidget, Ui_AccountButton):
    clicked = pyqtSignal(OrganizationID, DeviceID, Path)

    def __init__(self, organization_id, device_id, key_file):
        super().__init__()
        self.setupUi(self)
        self.organization_id = organization_id
        self.device_id = device_id
        self.key_file = key_file
        self.label_device.setText(self.device_id.device_name)
        self.label_name.setText(self.device_id.user_id)
        self.label_organization.setText(self.organization_id)
        if str(device_id.user_id) == "bob":
            self.label_device.setText("Desktop")
            self.label_name.setText("Maxime GRANDCOLAS <maxime.grandcolas@gmail.com>")
            self.label_organization.setText("Scille")

    def mousePressEvent(self, event):
        if event.button() & Qt.LeftButton:
            self.clicked.emit(self.organization_id, self.device_id, self.key_file)


class LoginAccountsWidget(QWidget, Ui_LoginAccountsWidget):
    account_clicked = pyqtSignal(OrganizationID, DeviceID, Path)

    def __init__(self, devices):
        super().__init__()
        self.setupUi(self)
        for o, d, t, kf in devices:
            if not ParsecApp.is_device_connected(o, d):
                ab = AccountButton(o, d, kf)
                ab.clicked.connect(self.account_clicked.emit)
                self.accounts_widget.layout().addWidget(ab)


class LoginPasswordInputWidget(QWidget, Ui_LoginPasswordInputWidget):
    back_clicked = pyqtSignal()
    log_in_clicked = pyqtSignal(Path, str)

    def __init__(self, organization_id, device_id, key_file):
        super().__init__()
        self.setupUi(self)
        self.key_file = key_file
        self.button_back.clicked.connect(self.back_clicked.emit)
        self.button_login.clicked.connect(self._on_log_in_clicked)
        self.label_instructions.setText(
            _("TEXT_LOGIN_ENTER_PASSWORD_INSTRUCTIONS_organization-device-user-email").format(
                organization=organization_id,
                user=device_id.user_id,
                device=device_id.device_name,
                email="",
            )
        )

    def _on_log_in_clicked(self):
        self.button_login.setDisabled(True)
        self.button_login.setText(_("ACTION_LOGGING_IN"))
        self.log_in_clicked.emit(self.key_file, self.line_edit_password.text())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return and self.button_login.isEnabled():
            self._on_log_in_clicked()
        event.accept()

    def reset(self):
        self.button_login.setDisabled(False)
        self.line_edit_password.setText("")
        self.button_login.setText(_("ACTION_LOG_IN"))


class LoginNoDevicesWidget(QWidget, Ui_LoginNoDevicesWidget):
    join_organization_clicked = pyqtSignal()
    create_organization_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        if ParsecApp.connected_devices:
            self.label_no_device.setText(_("TEXT_LOGIN_NO_AVAILABLE_DEVICE"))
        else:
            self.label_no_device.setText(_("TEXT_LOGIN_NO_DEVICE_ON_MACHINE"))
        self.button_create_org.clicked.connect(self.create_organization_clicked.emit)
        self.button_join_org.clicked.connect(self.join_organization_clicked.emit)


class LoginWidget(QWidget, Ui_LoginWidget):
    login_with_password_clicked = pyqtSignal(object, str)
    create_organization_clicked = pyqtSignal()
    join_organization_clicked = pyqtSignal()

    def __init__(self, jobs_ctx, event_bus, config, login_failed_sig, parent):
        super().__init__(parent=parent)
        self.setupUi(self)
        self.jobs_ctx = jobs_ctx
        self.event_bus = event_bus
        self.config = config
        self.login_failed_sig = login_failed_sig

        login_failed_sig.connect(self.on_login_failed)
        self.reload_devices()

    def on_login_failed(self):
        item = self.widget.layout().itemAt(0)
        if item:
            lw = item.widget()
            lw.reset()

    def reload_devices(self):
        self._clear_widget()
        devices = list_available_devices(self.config.config_dir)
        if len(devices):
            accounts_widget = LoginAccountsWidget(devices)
            accounts_widget.account_clicked.connect(self._on_account_clicked)
            self.widget.layout().addWidget(accounts_widget)
            accounts_widget.setFocus()
        else:
            no_device_widget = LoginNoDevicesWidget()
            no_device_widget.create_organization_clicked.connect(
                self.create_organization_clicked.emit
            )
            no_device_widget.join_organization_clicked.connect(self.join_organization_clicked.emit)
            self.widget.layout().addWidget(no_device_widget)
            no_device_widget.setFocus()

    def _clear_widget(self):
        while self.widget.layout().count() != 0:
            item = self.widget.layout().takeAt(0)
            if item:
                w = item.widget()
                self.widget.layout().removeWidget(w)
                w.hide()
                w.setParent(None)

    def _on_account_clicked(self, organization_id, device_id, key_file):
        self._clear_widget()
        lw = LoginPasswordInputWidget(organization_id, device_id, key_file)
        lw.back_clicked.connect(self.reload_devices)
        lw.log_in_clicked.connect(self.try_login)
        self.widget.layout().addWidget(lw)
        lw.line_edit_password.setFocus()

    def _on_back_clicked(self):
        self.reload_devices()

    def try_login(self, key_file, password):
        self.login_with_password_clicked.emit(key_file, password)

    def disconnect_all(self):
        pass
