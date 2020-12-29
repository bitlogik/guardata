# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QGraphicsDropShadowEffect, QLabel
from PyQt5.QtGui import QColor

from guardata.client.backend_connection import BackendNotAvailable, BackendConnectionError
from guardata.client.gui.trio_thread import JobResultError, ThreadSafeQtSignal, QtToTrioJob
from guardata.client.gui.greet_device_widget import GreetDeviceWidget
from guardata.client.gui.lang import translate as _
from guardata.client.gui.custom_widgets import ensure_string_size
from guardata.client.gui.custom_dialogs import show_error
from guardata.client.gui.flow_layout import FlowLayout
from guardata.client.gui.ui.devices_widget import Ui_DevicesWidget
from guardata.client.gui.ui.device_button import Ui_DeviceButton

DEVICES_PER_PAGE = 20


class DeviceButton(QWidget, Ui_DeviceButton):
    def __init__(self, device_info, is_current_device):
        super().__init__()
        self.setupUi(self)
        self.is_current_device = is_current_device
        self.device_info = device_info
        self.label_icon.apply_style()

        self.label_device_name.setText(
            ensure_string_size(self.device_info.device_display, 260, self.label_device_name.font())
        )
        self.label_device_name.setToolTip(self.device_info.device_display)
        if self.is_current_device:
            self.label_is_current.setText("({})".format(_("TEXT_DEVICE_IS_CURRENT")))
        effect = QGraphicsDropShadowEffect(self)
        effect.setColor(QColor(0x99, 0x99, 0x99))
        effect.setBlurRadius(10)
        effect.setXOffset(2)
        effect.setYOffset(2)
        self.setGraphicsEffect(effect)


async def _do_invite_device(client):
    try:
        return await client.new_device_invitation(send_email=False)
    except BackendNotAvailable as exc:
        raise JobResultError("offline") from exc
    except BackendConnectionError as exc:
        raise JobResultError("error") from exc


def filter_devices(device, pattern):
    return device.device_display.lower().find(pattern.lower()) != -1


async def _do_list_devices(client, page, pattern=None):
    try:
        devices, total = await client.get_user_devices_info(per_page=DEVICES_PER_PAGE, page=page)
        if pattern:
            devices_filtered = filter(lambda x: filter_devices(x, pattern), devices)
            # return all results without pagination
            return devices_filtered, DEVICES_PER_PAGE - 1

        # When without filter : put the current device first
        for i, device in enumerate(devices):
            if client.device.device_id == device.device_id:
                curr_dev = devices.pop(i)
                break
        devices.insert(0, curr_dev)
        return devices, total

    except BackendNotAvailable as exc:
        raise JobResultError("offline") from exc
    except BackendConnectionError as exc:
        raise JobResultError("error") from exc


class DevicesWidget(QWidget, Ui_DevicesWidget):
    list_success = pyqtSignal(QtToTrioJob)
    list_error = pyqtSignal(QtToTrioJob)

    invite_success = pyqtSignal(QtToTrioJob)
    invite_error = pyqtSignal(QtToTrioJob)

    def __init__(self, client, jobs_ctx, event_bus, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setupUi(self)
        self.jobs_ctx = jobs_ctx
        self.client = client
        self.event_bus = event_bus
        self.layout_devices = FlowLayout(spacing=24)
        self.layout_content.addLayout(self.layout_devices)
        self.button_add_device.clicked.connect(self.invite_device)
        self.button_add_device.apply_style()
        self.button_previous_page.clicked.connect(self.show_previous_page)
        self.button_next_page.clicked.connect(self.show_next_page)
        self.list_success.connect(self._on_list_success)
        self.list_error.connect(self._on_list_error)
        self.invite_success.connect(self._on_invite_success)
        self.invite_error.connect(self._on_invite_error)
        self.line_edit_search.textChanged.connect(self.on_filter)

    def show(self):
        self._page = 1

        self.reset()
        super().show()

    def show_next_page(self):
        self._page += 1
        self.reset()

    def show_previous_page(self):
        if self._page > 1:
            self._page -= 1
        self.reset()

    def on_filter(self):
        self._page = 1
        pattern = self.line_edit_search.text()
        if len(pattern) < 2:
            return self.reset()
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "list_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "list_error", QtToTrioJob),
            _do_list_devices,
            client=self.client,
            page=self._page,
            pattern=pattern,
        )

    def invite_device(self):
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "invite_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "invite_error", QtToTrioJob),
            _do_invite_device,
            client=self.client,
        )

    def _on_invite_success(self, job):
        assert job.is_finished()
        assert job.status == "ok"

        def _on_greet_finished(return_code):
            if return_code:
                self.reset()

        GreetDeviceWidget.show_modal(
            client=self.client,
            jobs_ctx=self.jobs_ctx,
            invite_addr=job.ret,
            parent=self,
            on_finished=_on_greet_finished,
        )

    def _on_invite_error(self, job):
        assert job.is_finished()
        assert job.status != "ok"

        status = job.status
        if status == "offline":
            errmsg = _("TEXT_INVITE_DEVICE_INVITE_OFFLINE")
        else:
            errmsg = _("TEXT_INVITE_DEVICE_INVITE_ERROR")

        show_error(self, errmsg, exception=job.exc)

    def add_device(self, device_info, is_current_device):
        button = DeviceButton(device_info, is_current_device)
        self.layout_devices.addWidget(button)
        button.show()

    def pagination(self, total: int):
        """Show/activate or hide/deactivate previous and next page button"""
        if total > DEVICES_PER_PAGE:
            self.button_previous_page.show()
            self.button_next_page.show()
            if self._page * DEVICES_PER_PAGE >= total:
                self.button_next_page.setEnabled(False)
            else:
                self.button_next_page.setEnabled(True)
            if self._page <= 1:
                self.button_previous_page.setEnabled(False)
            else:
                self.button_previous_page.setEnabled(True)
        else:
            self.button_previous_page.hide()
            self.button_next_page.hide()

    def _on_list_success(self, job):
        assert job.is_finished()
        assert job.status == "ok"

        devices, total = job.ret
        # Securing if page go to far
        if total == 0 and self._page > 1:
            self._page -= 1
            self.reset()
        current_device = self.client.device
        self.layout_devices.clear()
        for device in devices:
            self.add_device(device, is_current_device=current_device.device_id == device.device_id)
        self.spinner.spinner_movie.stop()
        self.spinner.hide()
        # Show/activate or hide/deactivate previous and next page button
        self.pagination(total=total)

    def _on_list_error(self, job):
        assert job.is_finished()
        assert job.status != "ok"
        self.spinner.spinner_movie.stop()
        self.spinner.hide()

        status = job.status
        if status in ["error", "offline"]:
            self.layout_devices.clear()
            label = QLabel(_("TEXT_DEVICE_LIST_RETRIEVABLE_FAILURE"))
            label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            self.layout_devices.addWidget(label)

    def reset(self):
        self.layout_devices.clear()
        self.button_previous_page.hide()
        self.button_next_page.hide()
        self.spinner.spinner_movie.start()
        self.spinner.show()
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "list_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "list_error", QtToTrioJob),
            _do_list_devices,
            client=self.client,
            page=self._page,
        )
