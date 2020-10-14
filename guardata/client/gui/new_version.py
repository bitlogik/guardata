# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import platform
import trio
from urllib.request import urlopen, Request
from packaging.version import Version

from PyQt5.QtCore import Qt, pyqtSignal, QSysInfo
from PyQt5.QtWidgets import QDialog, QWidget

from guardata import __version__
from guardata.client.gui import desktop
from guardata.client.gui.trio_thread import ThreadSafeQtSignal
from guardata.client.gui.lang import translate as _
from guardata.client.gui.ui.new_version_dialog import Ui_NewVersionDialog
from guardata.client.gui.ui.new_version_info import Ui_NewVersionInfo
from guardata.client.gui.ui.new_version_available import Ui_NewVersionAvailable


async def _do_check_new_version(url):
    current_version = Version(__version__)

    def _fetch_latest_release():
        with urlopen(Request(url, method="GET")) as req:
            latest_v = req.read()
            return Version(latest_v.decode("ascii"))

    latest_version = await trio.to_thread.run_sync(_fetch_latest_release)
    if latest_version:
        if latest_version > current_version:
            if platform.system() == "Windows":
                current_arch = QSysInfo().currentCpuArchitecture()
                if current_arch == "x86_64":
                    win_version = "win64"
                    return (
                        latest_version,
                        f"https://dl.guardata.app/guardata-{latest_version.public}-{win_version}-setup.exe",
                    )
            elif platform.system() == "Darwin":
                return (
                    latest_version,
                    f"https://dl.guardata.app/guardata_{latest_version.public}.dmg",
                )

    return None


class NewVersionInfo(QWidget, Ui_NewVersionInfo):
    close_clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setupUi(self)
        self.button_close.clicked.connect(self.close_clicked.emit)
        self.show_waiting()

    def show_error(self):
        self.label_waiting.hide()
        self.label_error.show()
        self.label_up_to_date.hide()

    def show_up_to_date(self):
        self.label_waiting.hide()
        self.label_error.hide()
        self.label_up_to_date.show()

    def show_waiting(self):
        self.label_waiting.show()
        self.label_error.hide()
        self.label_up_to_date.hide()


class NewVersionAvailable(QWidget, Ui_NewVersionAvailable):
    download_clicked = pyqtSignal()
    close_clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setupUi(self)
        self.button_download.clicked.connect(self.download_clicked.emit)
        self.button_ignore.clicked.connect(self.close_clicked.emit)

    def set_version(self, version):
        if version:
            self.label.setText(
                _("TEXT_GUARDATA_NEW_VERSION_AVAILABLE_version").format(version=str(version))
            )


class CheckNewVersion(QDialog, Ui_NewVersionDialog):
    check_new_version_success = pyqtSignal()
    check_new_version_error = pyqtSignal()

    def __init__(self, jobs_ctx, event_bus, config, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

        if platform.system() != "Windows" and platform.system() != "Darwin":
            return

        self.widget_info = NewVersionInfo(parent=self)
        self.widget_available = NewVersionAvailable(parent=self)
        self.widget_available.hide()
        self.layout.addWidget(self.widget_info)
        self.layout.addWidget(self.widget_available)

        self.widget_info.close_clicked.connect(self.ignore)
        self.widget_available.close_clicked.connect(self.ignore)
        self.widget_available.download_clicked.connect(self.download)

        self.jobs_ctx = jobs_ctx
        self.event_bus = event_bus
        self.config = config

        self.check_new_version_success.connect(self.on_check_new_version_success)
        self.check_new_version_error.connect(self.on_check_new_version_error)

        self.version_job = self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "check_new_version_success"),
            ThreadSafeQtSignal(self, "check_new_version_error"),
            _do_check_new_version,
            url=self.config.gui_check_version_url,
        )
        self.setWindowFlags(Qt.SplashScreen)

    def on_check_new_version_success(self):
        assert self.version_job.is_finished()
        assert self.version_job.status == "ok"
        version_job_ret = self.version_job.ret
        self.version_job = None
        if version_job_ret:
            new_version, url = version_job_ret
            self.widget_available.show()
            self.widget_info.hide()
            self.widget_available.set_version(new_version)
            self.download_url = url
            if not self.isVisible():
                self.exec_()
        else:
            if not self.isVisible():
                self.ignore()
            self.widget_available.hide()
            self.widget_info.show()
            self.widget_info.show_up_to_date()

    def on_check_new_version_error(self):
        self.version_job = None
        if not self.isVisible():
            self.ignore()

    def download(self):
        desktop.open_url(self.download_url)
        self.accept()

    def ignore(self):
        self.reject()

    def closeEvent(self, event):
        if self.version_job:
            self.version_job.cancel_and_join()
        event.accept()
