# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QFile
from PyQt5.QtGui import QFont, QFontDatabase


class guardataApp(QApplication):
    connected_devices = set()

    def __init__(self):
        super().__init__(["-stylesheet"])
        self.setOrganizationName("BitLogiK")
        self.setOrganizationDomain("cloud.guardata.app")
        self.setApplicationName("guardata")

    def load_stylesheet(self, res=":/styles/styles/main.css"):
        rc = QFile(res)
        rc.open(QFile.ReadOnly)
        content = rc.readAll().data()
        self.setStyleSheet(str(content, "utf-8"))

    def load_font(self, font="Open Sans"):
        QFontDatabase.addApplicationFont(":/fonts/fonts/OpenSans.ttf")
        QFontDatabase.addApplicationFont(":/fonts/fonts/Roboto-Regular.ttf")
        f = QFont(font)
        self.setFont(f)

    @classmethod
    def add_connected_device(cls, org_id, device_id):
        cls.connected_devices.add((org_id, device_id))

    @classmethod
    def remove_connected_device(cls, org_id, device_id):
        cls.connected_devices.discard((org_id, device_id))

    @classmethod
    def is_device_connected(cls, org_id, device_id):
        return (org_id, device_id) in cls.connected_devices

    @classmethod
    def has_active_modal(cls):
        if cls.activeModalWidget():
            return True
        mw = cls.get_main_window()
        if not mw:
            return False
        for win in mw.children():
            if win.objectName() == "GreyedDialog":
                return True
        return False

    @classmethod
    def get_main_window(cls):
        # Avoid recursive imports
        from .main_window import MainWindow

        for win in cls.topLevelWidgets():
            if isinstance(win, MainWindow):
                return win
        return None
