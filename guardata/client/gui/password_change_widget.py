# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget

from structlog import get_logger

from guardata.client.local_device import (
    get_key_file,
    change_device_password,
    LocalDeviceCryptoError,
)

from guardata.client.gui.password_validation import PasswordStrengthWidget, get_password_strength
from guardata.client.gui.custom_dialogs import show_error, show_info, GreyedDialog
from guardata.client.gui.lang import translate as _

from guardata.client.gui.ui.password_change_widget import Ui_PasswordChangeWidget


logger = get_logger()


class PasswordChangeWidget(QWidget, Ui_PasswordChangeWidget):
    accepted = pyqtSignal()

    def __init__(self, client, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setupUi(self)
        self.client = client
        pwd_str_widget = PasswordStrengthWidget(main_pwd=self.line_edit_password)
        self.line_edit_old_password.textChanged.connect(self.check_infos)
        self.line_edit_password.textChanged.connect(pwd_str_widget.on_password_change)
        self.line_edit_password.textChanged.connect(self.check_infos)
        self.line_edit_password_check.textChanged.connect(pwd_str_widget.on_otherpwd_change)
        self.line_edit_password_check.textChanged.connect(self.check_infos)
        self.layout_password_strength.addWidget(pwd_str_widget)
        self.button_change.clicked.connect(self.change_password)
        self.button_change.setDisabled(True)

    def check_infos(self):
        if (
            len(self.line_edit_old_password.text())
            and len(self.line_edit_password.text())
            and get_password_strength(self.line_edit_password.text()) > 2
            and self.line_edit_password_check.text() == self.line_edit_password.text()
        ):
            self.button_change.setDisabled(False)
        else:
            self.button_change.setDisabled(True)

    def change_password(self):
        if self.line_edit_password.text() != self.line_edit_password_check.text():
            show_error(self, _("TEXT_CHANGE_PASSWORD_PASSWORD_MISMATCH"))
        else:
            key_file = get_key_file(self.client.config.config_dir, self.client.device)
            try:
                change_device_password(
                    key_file, self.line_edit_old_password.text(), self.line_edit_password.text()
                )
                show_info(self, _("TEXT_CHANGE_PASSWORD_SUCCESS"))
                self.accepted.emit()
            except LocalDeviceCryptoError as exc:
                show_error(self, _("TEXT_CHANGE_PASSWORD_INVALID_PASSWORD"), exception=exc)

    @classmethod
    def show_modal(cls, client, parent):
        w = cls(client=client)
        d = GreyedDialog(w, title=_("TEXT_CHANGE_PASSWORD_TITLE"), parent=parent)
        w.accepted.connect(d.accept)
        # Unlike exec_, show is asynchronous and works within the main Qt loop
        d.show()
