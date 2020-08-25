# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget

from guardata.client.gui.files_widget import FilesWidget
from guardata.client.gui.workspaces_widget import WorkspacesWidget

from guardata.client.gui.ui.mount_widget import Ui_MountWidget


class MountWidget(QWidget, Ui_MountWidget):
    widget_switched = pyqtSignal(list)
    folder_changed = pyqtSignal(str, str)

    def __init__(self, client, jobs_ctx, event_bus, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

        self.client = client
        self.jobs_ctx = jobs_ctx
        self.event_bus = event_bus
        self.workspaces_widget = WorkspacesWidget(
            self.client, self.jobs_ctx, self.event_bus, parent=self
        )
        self.layout_content.insertWidget(0, self.workspaces_widget)
        self.workspaces_widget.load_workspace_clicked.connect(self.load_workspace)
        self.files_widget = FilesWidget(self.client, self.jobs_ctx, self.event_bus, parent=self)
        self.files_widget.folder_changed.connect(self.folder_changed.emit)
        self.layout_content.insertWidget(0, self.files_widget)
        self.files_widget.back_clicked.connect(self.show_workspaces_widget)
        self.show_workspaces_widget()

    def load_workspace(self, workspace_fs, default_path, select=False):
        self.show_files_widget(workspace_fs, default_path, select)

    def show_files_widget(self, workspace_fs, default_path, selected=False):
        self.workspaces_widget.hide()
        self.files_widget.set_workspace_fs(
            workspace_fs,
            current_directory=default_path.parent,
            default_selection=default_path.name
            if len(default_path.parts) != 0 and selected
            else None,
        )
        self.files_widget.show()

    def show_workspaces_widget(self):
        self.folder_changed.emit(None, None)
        self.files_widget.hide()
        self.workspaces_widget.show()
        self.workspaces_widget.reset()
