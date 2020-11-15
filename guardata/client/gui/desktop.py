# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import psutil

from PyQt5.QtCore import QUrl, QFileInfo, QSysInfo, QLocale
from PyQt5.QtGui import QDesktopServices, QGuiApplication, QClipboard

from guardata.api.protocol import DeviceName


def open_file(path):
    return QDesktopServices.openUrl(QUrl.fromLocalFile(QFileInfo(path).absoluteFilePath()))


def open_url(url):
    return QDesktopServices.openUrl(QUrl(url))


# def open_doc_link():
# return open_url("SOON")


def open_feedback_link():
    return open_url("https://guardata.app/contact")


# def open_user_guide():
# return open_url("https://USERGUIDE")


def get_default_device():
    device = QSysInfo.machineHostName()
    if device.lower() == "localhost":
        device = QSysInfo.productType()
    return "".join([c for c in device if DeviceName.regex.match(c)])


def get_locale_language():
    return QLocale.system().name()[:2].lower()


def copy_to_clipboard(text):
    QGuiApplication.clipboard().setText(text, QClipboard.Clipboard)
    QGuiApplication.clipboard().setText(text, QClipboard.Selection)


def is_process_running(pid):
    return psutil.pid_exists(pid)


def guardata_instances_count():
    inst_count = 0
    for proc in psutil.process_iter():
        try:
            if (
                proc.name().lower() in ["guardata", "guardata.exe"]
                and "backend" not in proc.cmdline()
            ):
                inst_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return inst_count
