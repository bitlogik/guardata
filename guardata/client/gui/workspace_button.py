# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from typing import Optional
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QGraphicsDropShadowEffect, QMenu
from PyQt5.QtGui import QColor, QCursor

from guardata.client.fs import WorkspaceFS
from guardata.client.types import EntryID, WorkspaceRole
from guardata.client.fs.workspacefs import ReencryptionNeed

from guardata.client.gui.lang import translate as _, format_datetime
from guardata.client.gui.custom_dialogs import show_info

from guardata.client.gui.ui.workspace_button import Ui_WorkspaceButton
from guardata.client.gui.ui.empty_workspace_widget import Ui_EmptyWorkspaceWidget

from guardata.client.gui.switch_button import SwitchButton


# Only used because we can't hide widgets in QtDesigner and adding the empty workspace
# button changes the minimum size we can set for the workspace button.
class EmptyWorkspaceWidget(QWidget, Ui_EmptyWorkspaceWidget):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.label_icon.apply_style()


class WorkspaceButton(QWidget, Ui_WorkspaceButton):
    clicked = pyqtSignal(WorkspaceFS)
    share_clicked = pyqtSignal(WorkspaceFS)
    reencrypt_clicked = pyqtSignal(EntryID, bool, bool, bool)
    delete_clicked = pyqtSignal(WorkspaceFS)
    rename_clicked = pyqtSignal(QWidget)
    remount_ts_clicked = pyqtSignal(WorkspaceFS)
    open_clicked = pyqtSignal(WorkspaceFS)
    switch_clicked = pyqtSignal(bool, WorkspaceFS, object)

    def __init__(
        self,
        workspace_name,
        workspace_fs,
        users_roles,
        is_mounted,
        files=None,
        reencryption_needs=None,
        timestamped=False,
    ):
        super().__init__()
        self.setupUi(self)
        self.users_roles = users_roles
        self.workspace_name = workspace_name
        self.workspace_fs = workspace_fs
        self._reencryption_needs: ReencryptionNeed = None
        self.timestamped = timestamped
        self.switch_button = SwitchButton()
        self.widget_actions.layout().insertWidget(0, self.switch_button)
        self.switch_button.clicked.connect(self._on_switch_clicked)
        self.reencrypting = None
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.widget_empty.layout().addWidget(EmptyWorkspaceWidget())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        files = files or []

        self.switch_button.setToolTip(_("TEXT_WORKSPACE_SWITCH_TOOLTIP"))

        if not len(files):
            self.widget_empty.show()
            self.widget_files.hide()
        else:
            for i, f in enumerate(files, 1):
                if i > 4:
                    break
                label = getattr(self, "file{}_name".format(i))
                label.setText(f)
            self.widget_files.show()
            self.widget_empty.hide()

        if self.timestamped:
            self.widget_title.setStyleSheet("background-color: #DDDDDD;")
            self.widget_actions.setStyleSheet("background-color: #DDDDDD;")
            self.widget.setStyleSheet("background-color: #DDDDDD;")
            self.switch_button.setChecked(True)
            self.button_reencrypt.hide()
            self.button_remount_ts.hide()
            self.button_share.hide()
            self.button_rename.hide()
            self.label_shared.hide()
            self.label_owner.hide()
            self.switch_button.hide()
        else:
            self.button_delete.hide()
        effect = QGraphicsDropShadowEffect(self)
        effect.setColor(QColor(0x99, 0x99, 0x99))
        effect.setBlurRadius(10)
        effect.setXOffset(2)
        effect.setYOffset(2)
        self.setGraphicsEffect(effect)
        if not self.is_owner:
            self.button_reencrypt.hide()
        self.widget_reencryption.hide()
        self.button_share.clicked.connect(self.button_share_clicked)
        self.button_share.apply_style()
        self.button_reencrypt.clicked.connect(self.button_reencrypt_clicked)
        self.button_reencrypt.apply_style()
        self.button_delete.clicked.connect(self.button_delete_clicked)
        self.button_delete.apply_style()
        self.button_rename.clicked.connect(self.button_rename_clicked)
        self.button_rename.apply_style()
        self.button_remount_ts.clicked.connect(self.button_remount_ts_clicked)
        self.button_remount_ts.apply_style()
        self.button_open.clicked.connect(self.button_open_workspace_clicked)
        self.button_open.apply_style()
        self.label_owner.apply_style()
        self.label_shared.apply_style()
        if not self.is_owner:
            self.label_owner.hide()
        if not self.is_shared:
            self.label_shared.hide()
        self.reload_workspace_name(self.workspace_name)
        self.set_mountpoint_state(is_mounted)

    @property
    def is_shared(self):
        return sum(1 for _, u in self.users_roles.values() if u.revoked_on is None) > 1

    @property
    def owner(self):
        for user_id, (role, user_info) in self.users_roles.items():
            if role == WorkspaceRole.OWNER:
                return user_info
        raise ValueError

    @property
    def others(self):
        return [
            user_info
            for user_id, (role, user_info) in self.users_roles.items()
            if user_id != self.workspace_fs.device.user_id
        ]

    @property
    def is_owner(self):
        user_id = self.workspace_fs.device.user_id
        return user_id in self.users_roles and self.users_roles[user_id][0] == WorkspaceRole.OWNER

    def show_context_menu(self, pos):
        global_pos = self.mapToGlobal(pos)
        menu = QMenu(self)

        action = menu.addAction(_("ACTION_WORKSPACE_OPEN_IN_FILE_EXPLORER"))
        action.triggered.connect(self.button_open_workspace_clicked)
        if not self.timestamped:
            action = menu.addAction(_("ACTION_WORKSPACE_RENAME"))
            action.triggered.connect(self.button_rename_clicked)
            action = menu.addAction(_("ACTION_WORKSPACE_SHARE"))
            action.triggered.connect(self.button_share_clicked)
            action = menu.addAction(_("ACTION_WORKSPACE_SEE_IN_THE_PAST"))
            action.triggered.connect(self.button_remount_ts_clicked)
            if self.reencryption_needs and self.reencryption_needs.need_reencryption:
                action = menu.addAction(_("ACTION_WORKSPACE_REENCRYPT"))
                action.triggered.connect(self.button_reencrypt_clicked)
        else:
            action = menu.addAction(_("ACTION_WORKSPACE_DELETE"))
            action.triggered.connect(self.button_delete_clicked)

        menu.exec_(global_pos)

    def button_open_workspace_clicked(self):
        self.open_clicked.emit(self.workspace_fs)

    def button_share_clicked(self):
        self.share_clicked.emit(self.workspace_fs)

    def button_reencrypt_clicked(self):
        if self.reencryption_needs:
            if not self.is_owner:
                show_info(self, message=_("TEXT_WORKSPACE_ONLY_OWNER_CAN_REENCRYPT"))
                return
            self.reencrypt_clicked.emit(
                self.workspace_id,
                bool(self.reencryption_needs.user_revoked),
                bool(self.reencryption_needs.role_revoked),
                bool(self.reencryption_needs.reencryption_already_in_progress),
            )

    def button_delete_clicked(self):
        self.delete_clicked.emit(self.workspace_fs)

    def button_rename_clicked(self):
        self.rename_clicked.emit(self)

    def button_remount_ts_clicked(self):
        self.remount_ts_clicked.emit(self.workspace_fs)

    @property
    def name(self):
        return self.workspace_name

    @property
    def workspace_id(self):
        return self.workspace_fs.workspace_id

    @property
    def timestamp(self):
        return getattr(self.workspace_fs, "timestamp", None)

    @property
    def reencryption_needs(self) -> Optional[ReencryptionNeed]:
        return self._reencryption_needs

    @reencryption_needs.setter
    def reencryption_needs(self, val: Optional[ReencryptionNeed]):
        self._reencryption_needs = val
        if not self.is_owner:
            return
        if val and val.need_reencryption:
            self.button_reencrypt.show()
        else:
            self.button_reencrypt.hide()

    @property
    def reencrypting(self):
        return self._reencrypting

    @reencrypting.setter
    def reencrypting(self, val):
        def _start_reencrypting():
            self.widget_reencryption.show()
            self.widget_actions.hide()
            self.button_reencrypt.hide()

        def _stop_reencrypting():
            self.button_reencrypt.hide()
            self.widget_actions.show()
            self.widget_reencryption.hide()

        self._reencrypting = val
        if not self.is_owner:
            return
        if self._reencrypting:
            _start_reencrypting()
            total, done = self._reencrypting
            self.progress_reencryption.setValue(int(done / total * 100))
        else:
            _stop_reencrypting()

    def reload_workspace_name(self, workspace_name):
        self.workspace_name = workspace_name
        display = workspace_name

        if not self.timestamped:
            if not self.is_shared:
                shared_message = _("TEXT_WORKSPACE_IS_PRIVATE")
            elif not self.is_owner:
                shared_message = _("TEXT_WORKSPACE_IS_OWNED_BY_user").format(
                    user=self.owner.short_user_display
                )
            elif len(self.others) == 1:
                (user,) = self.others
                shared_message = _("TEXT_WORKSPACE_IS_SHARED_WITH_user").format(
                    user=user.short_user_display
                )
            else:
                n = len(self.others)
                assert n > 1
                shared_message = _("TEXT_WORKSPACE_IS_SHARED_WITH_n_USERS").format(n=n)
            display += " ({})".format(shared_message)
        else:
            display += "-" + _("TEXT_WORKSPACE_IS_TIMESTAMPED_date").format(
                date=format_datetime(self.workspace_fs.timestamp)
            )
        self.label_title.setToolTip(display)
        if len(display) > 20:
            display = display[:20] + "..."
        self.label_title.setText(display)

    def mousePressEvent(self, event):
        if event.button() & Qt.LeftButton and self.switch_button.isChecked():
            self.clicked.emit(self.workspace_fs)

    def _on_switch_clicked(self, state):
        self.set_mountpoint_state(state)
        self.switch_clicked.emit(state, self.workspace_fs, self.timestamp)

    def set_mountpoint_state(self, state):
        if self.timestamped:
            return
        self.switch_button.setChecked(state)
        if state:
            self.widget.setStyleSheet("background-color: #FFFFFF;")
            self.widget_title.setStyleSheet("background-color: #FFFFFF;")
            self.widget_actions.setStyleSheet("background-color: #FFFFFF;")
            self.button_open.setDisabled(False)
        else:
            self.widget.setStyleSheet("background-color: #DDDDDD;")
            self.widget_title.setStyleSheet("background-color: #DDDDDD;")
            self.widget_actions.setStyleSheet("background-color: #DDDDDD;")
            self.button_open.setDisabled(True)
