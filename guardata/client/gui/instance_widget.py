# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from guardata.client.client_events import ClientEvent
import trio

from structlog import get_logger

from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication

from guardata.client import logged_client_factory
from guardata.api.protocol import HandshakeRevokedDevice
from guardata.client.local_device import LocalDeviceError, load_device_with_password
from guardata.client.mountpoint import (
    MountpointConfigurationError,
    MountpointDriverCrash,
    MountpointFuseNotAvailable,
    MountpointWinfspNotAvailable,
)

from guardata.client.gui.trio_thread import QtToTrioJobScheduler, ThreadSafeQtSignal
from guardata.client.gui.guardata_application import guardataApp
from guardata.client.gui.custom_dialogs import show_error
from guardata.client.gui.lang import translate as _
from guardata.client.gui.login_widget import LoginWidget
from guardata.client.gui.central_widget import CentralWidget


logger = get_logger()


async def _do_run_client(config, device, qt_on_ready):
    # Quick fix to avoid MultiError<Cancelled, ...> exception bubbling up
    # TODO: replace this by a proper generic MultiError handling
    with trio.MultiError.catch(lambda exc: None if isinstance(exc, trio.Cancelled) else exc):
        async with logged_client_factory(config=config, device=device, event_bus=None) as client:
            # Create our own job scheduler allows us to cancel all pending
            # jobs depending on us when we logout
            client_jobs_ctx = QtToTrioJobScheduler()
            async with trio.open_service_nursery() as nursery:
                await nursery.start(client_jobs_ctx._start)
                qt_on_ready.emit(client, client_jobs_ctx)


class InstanceWidget(QWidget):
    run_client_success = pyqtSignal()
    run_client_error = pyqtSignal()
    run_client_ready = pyqtSignal(object, object)
    logged_in = pyqtSignal()
    logged_out = pyqtSignal()
    state_changed = pyqtSignal(QWidget, str)
    login_failed = pyqtSignal()
    join_organization_clicked = pyqtSignal()
    create_organization_clicked = pyqtSignal()

    def __init__(self, jobs_ctx, event_bus, config, systray_notification, **kwargs):
        super().__init__(**kwargs)
        self.jobs_ctx = jobs_ctx
        self.event_bus = event_bus
        self.config = config
        self.systray_notification = systray_notification

        self.client = None
        self.client_jobs_ctx = None
        self.running_client_job = None
        self.workspace_path = None

        self.run_client_success.connect(self.on_client_run_done)
        self.run_client_error.connect(self.on_client_run_error)
        self.run_client_ready.connect(self.on_run_client_ready)
        self.logged_in.connect(self.on_logged_in)
        self.logged_out.connect(self.on_logged_out)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    @pyqtSlot(object, object)
    def _client_ready(self, client, client_jobs_ctx):
        self.run_client_ready.emit(client, client_jobs_ctx)

    @property
    def current_device(self):
        if self.client:
            return self.client.device
        return None

    @property
    def is_logged_in(self):
        return self.running_client_job is not None

    def set_workspace_path(self, action_addr):
        self.workspace_path = action_addr

    def reset_workspace_path(self):
        self.workspace_path = None

    def on_client_config_updated(self, event, **kwargs):
        self.event_bus.send(ClientEvent.GUI_CONFIG_CHANGED, **kwargs)

    def start_client(self, device):
        assert not self.running_client_job
        assert not self.client
        assert not self.client_jobs_ctx

        self.config = guardataApp.get_main_window().config

        self.running_client_job = self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "run_client_success"),
            ThreadSafeQtSignal(self, "run_client_error"),
            _do_run_client,
            self.config,
            device,
            ThreadSafeQtSignal(self, "run_client_ready", object, object),
        )

    def on_run_client_ready(self, client, client_jobs_ctx):
        self.client = client
        self.client_jobs_ctx = client_jobs_ctx
        self.client.event_bus.connect(ClientEvent.GUI_CONFIG_CHANGED, self.on_client_config_updated)
        self.event_bus.send(
            ClientEvent.GUI_CONFIG_CHANGED,
            gui_last_device="{}:{}".format(
                self.client.device.organization_addr.organization_id, self.client.device.device_id
            ),
        )
        guardataApp.add_connected_device(
            self.client.device.organization_addr.organization_id, self.client.device.device_id
        )
        self.logged_in.emit()

    def on_client_run_error(self):
        assert self.running_client_job.is_finished()
        if self.client:
            self.client.event_bus.disconnect(
                ClientEvent.GUI_CONFIG_CHANGED, self.on_client_config_updated
            )
        if self.running_client_job.status is not None:
            if isinstance(self.running_client_job.exc, HandshakeRevokedDevice):
                show_error(
                    self,
                    _("TEXT_LOGIN_ERROR_DEVICE_REVOKED"),
                    exception=self.running_client_job.exc,
                )
            elif isinstance(self.running_client_job.exc, MountpointWinfspNotAvailable):
                show_error(
                    self,
                    _("TEXT_LOGIN_ERROR_WINFSP_NOT_AVAILABLE"),
                    exception=self.running_client_job.exc,
                )
            elif isinstance(self.running_client_job.exc, MountpointFuseNotAvailable):
                show_error(
                    self,
                    _("TEXT_LOGIN_ERROR_FUSE_NOT_AVAILABLE"),
                    exception=self.running_client_job.exc,
                )
            else:
                logger.exception("Unhandled error", exc_info=self.running_client_job.exc)
                show_error(
                    self, _("TEXT_LOGIN_UNKNOWN_ERROR"), exception=self.running_client_job.exc
                )
        self.running_client_job = None
        self.logged_out.emit()

    def on_client_run_done(self):
        assert self.running_client_job.is_finished()
        if self.client:
            guardataApp.remove_connected_device(
                self.client.device.organization_addr.organization_id, self.client.device.device_id
            )
            self.client.event_bus.disconnect(
                ClientEvent.GUI_CONFIG_CHANGED, self.on_client_config_updated
            )
        self.running_client_job = None
        self.logged_out.emit()

    def stop_client(self):
        if self.running_client_job:
            self.running_client_job.cancel_and_join()

    def on_logged_out(self):
        self.state_changed.emit(self, "logout")
        self.show_login_widget()

    def on_logged_in(self):
        self.state_changed.emit(self, "connected")
        self.show_central_widget()

    def logout(self):
        self.stop_client()

    def login_with_password(self, key_file, password):
        message = None
        exception = None
        try:
            device = load_device_with_password(key_file, password)
            if guardataApp.is_device_connected(
                device.organization_addr.organization_id, device.device_id
            ):
                message = _("TEXT_LOGIN_ERROR_ALREADY_CONNECTED")
            else:
                self.start_client(device)
        except LocalDeviceError as exc:
            message = _("TEXT_LOGIN_ERROR_AUTHENTICATION_FAILED")
            exception = exc

        except (RuntimeError, MountpointConfigurationError, MountpointDriverCrash) as exc:
            message = _("TEXT_LOGIN_MOUNTPOINT_ERROR")
            exception = exc

        except Exception as exc:
            message = _("TEXT_LOGIN_UNKNOWN_ERROR")
            exception = exc
            logger.exception("Unhandled error during login")
        finally:
            if message:
                show_error(self, message, exception=exception)
                self.login_failed.emit()

    def show_central_widget(self):
        self.clear_widgets()
        central_widget = CentralWidget(
            self.client,
            self.client_jobs_ctx,
            self.client.event_bus,
            action_addr=self.workspace_path,
            systray_notification=self.systray_notification,
            parent=self,
        )
        self.layout().addWidget(central_widget)
        central_widget.logout_requested.connect(self.logout)
        central_widget.show()

    def show_login_widget(self):
        self.clear_widgets()
        login_widget = LoginWidget(
            self.jobs_ctx, self.event_bus, self.config, self.login_failed, parent=self
        )
        self.layout().addWidget(login_widget)

        login_widget.login_with_password_clicked.connect(self.login_with_password)
        login_widget.join_organization_clicked.connect(self.join_organization_clicked.emit)
        login_widget.create_organization_clicked.connect(self.create_organization_clicked.emit)
        login_widget.login_canceled.connect(self.reset_workspace_path)
        login_widget.show()

    def get_central_widget(self):
        item = self.layout().itemAt(0)
        if item:
            if isinstance(item.widget(), CentralWidget):
                return item.widget()
        return None

    def get_login_widget(self):
        item = self.layout().itemAt(0)
        if item:
            if isinstance(item.widget(), LoginWidget):
                return item.widget()
        return None

    def clear_widgets(self):
        item = self.layout().takeAt(0)
        if item:
            item.widget().hide()
            item.widget().setParent(None)
        QApplication.processEvents()
