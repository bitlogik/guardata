# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from guardata.client.client_events import ClientEvent
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QPixmap, QColor, QIcon
from PyQt5.QtWidgets import QGraphicsDropShadowEffect, QWidget, QMenu

from guardata.client.gui.mount_widget import MountWidget
from guardata.client.gui.users_widget import UsersWidget
from guardata.client.gui.devices_widget import DevicesWidget
from guardata.client.gui.menu_widget import MenuWidget
from guardata.client.gui.lang import translate as _
from guardata.client.gui.custom_widgets import Pixmap
from guardata.client.gui.custom_dialogs import show_error
from guardata.client.gui.ui.central_widget import Ui_CentralWidget


from guardata.api.protocol import (
    HandshakeAPIVersionError,
    HandshakeRevokedDevice,
    HandshakeOrganizationExpired,
)
from guardata.client.backend_connection import BackendConnStatus
from guardata.client.fs import (
    FSWorkspaceNoReadAccess,
    FSWorkspaceNoWriteAccess,
    FSWorkspaceInMaintenance,
)


class CentralWidget(QWidget, Ui_CentralWidget):
    NOTIFICATION_EVENTS = [
        ClientEvent.BACKEND_CONNECTION_CHANGED,
        ClientEvent.MOUNTPOINT_STOPPED,
        ClientEvent.MOUNTPOINT_REMOTE_ERROR,
        ClientEvent.MOUNTPOINT_UNHANDLED_ERROR,
        ClientEvent.SHARING_UPDATED,
        ClientEvent.FS_ENTRY_FILE_UPDATE_CONFLICTED,
    ]

    connection_state_changed = pyqtSignal(object, object)
    logout_requested = pyqtSignal()
    new_notification = pyqtSignal(str, str)

    def __init__(self, client, jobs_ctx, event_bus, systray_notification, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

        self.jobs_ctx = jobs_ctx
        self.client = client
        self.event_bus = event_bus
        self.systray_notification = systray_notification

        self.menu = MenuWidget(parent=self)
        self.widget_menu.layout().addWidget(self.menu)

        for e in self.NOTIFICATION_EVENTS:
            self.event_bus.connect(e, self.handle_event)

        self.set_user_info()
        menu = QMenu()
        log_out_act = menu.addAction(_("ACTION_LOG_OUT"))
        log_out_act.triggered.connect(self.logout_requested.emit)
        self.button_user.setMenu(menu)
        pix = Pixmap(":/icons/images/material/person.svg")
        pix.replace_color(QColor(0, 0, 0), QColor(0x00, 0x92, 0xFF))
        self.button_user.setIcon(QIcon(pix))
        self.button_user.clicked.connect(self._show_user_menu)

        self.new_notification.connect(self.on_new_notification)
        self.menu.files_clicked.connect(self.show_mount_widget)
        self.menu.users_clicked.connect(self.show_users_widget)
        self.menu.devices_clicked.connect(self.show_devices_widget)
        self.connection_state_changed.connect(self._on_connection_state_changed)

        self.widget_title2.hide()
        self.icon_title3.hide()
        self.label_title3.setText("")
        self.icon_title3.apply_style()
        self.icon_title3.apply_style()

        effect = QGraphicsDropShadowEffect(self)
        effect.setColor(QColor(100, 100, 100))
        effect.setBlurRadius(4)
        effect.setXOffset(-2)
        effect.setYOffset(2)
        self.widget_notif.setGraphicsEffect(effect)

        self.mount_widget = MountWidget(self.client, self.jobs_ctx, self.event_bus, parent=self)
        self.widget_central.layout().insertWidget(0, self.mount_widget)
        self.mount_widget.folder_changed.connect(self._on_folder_changed)

        self.users_widget = UsersWidget(self.client, self.jobs_ctx, self.event_bus, parent=self)
        self.widget_central.layout().insertWidget(0, self.users_widget)

        self.devices_widget = DevicesWidget(self.client, self.jobs_ctx, self.event_bus, parent=self)
        self.widget_central.layout().insertWidget(0, self.devices_widget)

        self._on_connection_state_changed(
            self.client.backend_status, self.client.backend_status_exc, allow_systray=False
        )
        self.show_mount_widget()

    def _show_user_menu(self):
        self.button_user.showMenu()

    def set_user_info(self):
        org = self.client.device.organization_id
        username = self.client.device.short_user_display
        user_text = f"{org}\n{username}"
        self.button_user.setText(user_text)

    def _on_folder_changed(self, workspace_name, path):
        if workspace_name and path:
            self.widget_title2.show()
            self.label_title2.setText(workspace_name)
            self.icon_title3.show()
            self.label_title3.setText(path)
        else:
            self.widget_title2.hide()
            self.icon_title3.hide()
            self.label_title3.setText("")

    def handle_event(self, event, **kwargs):
        if event == ClientEvent.BACKEND_CONNECTION_CHANGED:
            self.connection_state_changed.emit(kwargs["status"], kwargs["status_exc"])
        elif event == ClientEvent.MOUNTPOINT_STOPPED:
            self.new_notification.emit("WARNING", _("NOTIF_WARN_MOUNTPOINT_UNMOUNTED"))
        elif event == ClientEvent.MOUNTPOINT_REMOTE_ERROR:
            exc = kwargs["exc"]
            path = kwargs["path"]
            if isinstance(exc, FSWorkspaceNoReadAccess):
                msg = _("NOTIF_WARN_WORKSPACE_READ_ACCESS_LOST_{}").format(path)
            elif isinstance(exc, FSWorkspaceNoWriteAccess):
                msg = _("NOTIF_WARN_WORKSPACE_WRITE_ACCESS_LOST_{}").format(path)
            elif isinstance(exc, FSWorkspaceInMaintenance):
                msg = _("NOTIF_WARN_WORKSPACE_IN_MAINTENANCE_{}").format(path)
            else:
                msg = _("NOTIF_WARN_MOUNTPOINT_REMOTE_ERROR_{}_{}").format(path, str(exc))
            self.new_notification.emit("WARNING", msg)
        elif event == ClientEvent.MOUNTPOINT_UNHANDLED_ERROR:
            exc = kwargs["exc"]
            path = kwargs["path"]
            operation = kwargs["operation"]
            self.new_notification.emit(
                "ERROR",
                _("NOTIF_ERR_MOUNTPOINT_UNEXPECTED_ERROR_{}_{}_{}").format(
                    operation, path, str(exc)
                ),
            )
        elif event == ClientEvent.SHARING_UPDATED:
            new_entry = kwargs["new_entry"]
            previous_entry = kwargs["previous_entry"]
            new_role = getattr(new_entry, "role", None)
            previous_role = getattr(previous_entry, "role", None)
            if new_role is not None and previous_role is None:
                self.new_notification.emit(
                    "INFO", _("NOTIF_INFO_WORKSPACE_SHARED_{}").format(new_entry.name)
                )
            elif new_role is not None and previous_role is not None:
                self.new_notification.emit(
                    "INFO", _("NOTIF_INFO_WORKSPACE_ROLE_UPDATED_{}").format(new_entry.name)
                )
            elif new_role is None and previous_role is not None:
                self.new_notification.emit(
                    "INFO", _("NOTIF_INFO_WORKSPACE_UNSHARED_{}").format(previous_entry.name)
                )
        elif event == ClientEvent.FS_ENTRY_FILE_UPDATE_CONFLICTED:
            self.new_notification.emit(
                "WARNING", _("NOTIF_WARN_SYNC_CONFLICT_{}").format(kwargs["path"])
            )

    def _on_connection_state_changed(self, status, status_exc, allow_systray=True):
        text = None
        icon = None
        tooltip = None
        notif = None
        disconnected = None

        if status in (BackendConnStatus.READY, BackendConnStatus.INITIALIZING):
            tooltip = text = _("TEXT_BACKEND_STATE_CONNECTED")
            icon = QPixmap(":/icons/images/material/cloud_queue.svg")

        elif status == BackendConnStatus.LOST:
            tooltip = text = _("TEXT_BACKEND_STATE_DISCONNECTED")
            icon = QPixmap(":/icons/images/material/cloud_off.svg")
            disconnected = True

        elif status == BackendConnStatus.REFUSED:
            disconnected = True
            cause = status_exc.__cause__
            if isinstance(cause, HandshakeAPIVersionError):
                tooltip = _("TEXT_BACKEND_STATE_API_MISMATCH_versions").format(
                    versions=", ".join([str(v.version) for v in cause.backend_versions])
                )
            elif isinstance(cause, HandshakeRevokedDevice):
                tooltip = _("TEXT_BACKEND_STATE_REVOKED_DEVICE")
                notif = ("REVOKED", tooltip)
                self.new_notification.emit(*notif)
            elif isinstance(cause, HandshakeOrganizationExpired):
                tooltip = _("TEXT_BACKEND_STATE_ORGANIZATION_EXPIRED")
            else:
                tooltip = _("TEXT_BACKEND_STATE_UNKNOWN")
            text = _("TEXT_BACKEND_STATE_DISCONNECTED")
            icon = QPixmap(":/icons/images/material/cloud_off.svg")
            notif = ("WARNING", tooltip)

        elif status == BackendConnStatus.CRASHED:
            text = _("TEXT_BACKEND_STATE_DISCONNECTED")
            tooltip = _("TEXT_BACKEND_STATE_CRASHED_cause").format(cause=str(status_exc.__cause__))
            icon = QPixmap(":/icons/images/material/cloud_off.svg")
            notif = ("ERROR", tooltip)
            disconnected = True

        self.menu.set_connection_state(text, tooltip, icon)
        if notif:
            self.new_notification.emit(*notif)
        if allow_systray and disconnected:
            self.systray_notification.emit(
                "guardata",
                _("TEXT_SYSTRAY_BACKEND_DISCONNECT_organization").format(
                    organization=self.client.device.organization_id
                ),
                5000,
            )

    def on_new_notification(self, notif_type, msg):
        if notif_type == "REVOKED":
            show_error(self, msg)

    def show_mount_widget(self):
        self.clear_widgets()
        self.menu.activate_files()
        self.label_title.setText(_("ACTION_MENU_DOCUMENTS"))
        self.mount_widget.show()
        self.mount_widget.show_workspaces_widget()

    def show_users_widget(self, page=1):
        self.clear_widgets()
        self.menu.activate_users()
        self.label_title.setText(_("ACTION_MENU_USERS"))
        self.users_widget.show()

    def show_devices_widget(self):
        self.clear_widgets()
        self.menu.activate_devices()
        self.label_title.setText(_("ACTION_MENU_DEVICES"))
        self.devices_widget.show()

    def clear_widgets(self):
        self.widget_title2.hide()
        self.icon_title3.hide()
        self.label_title3.setText("")
        self.users_widget.hide()
        self.mount_widget.hide()
        self.devices_widget.hide()
