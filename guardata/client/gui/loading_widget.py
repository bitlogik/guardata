# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget

from guardata.client.gui.ui.loading_widget import Ui_LoadingWidget


class LoadingWidget(QWidget, Ui_LoadingWidget):
    cancelled = pyqtSignal()

    def __init__(self, total_size):
        super().__init__()
        self.setupUi(self)
        self.divider = 1
        while int(total_size / self.divider) > 0x7FFFFFFF:
            self.divider *= 1000
        self.progress_bar.setMaximum(int(total_size / self.divider))
        self.progress_bar.setMinimum(0)
        self.progress_bar.setValue(0)

    def on_close(self):
        self.cancelled.emit()

    def set_current_file(self, f):
        if len(f) > 35:
            self.label.setText('"{}...{}"'.format(f[:26], f[-6:]))
        else:
            self.label.setText(f'"{f}"')

    def set_progress(self, size):
        self.progress_bar.setValue(int(size / self.divider))
