# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from guardata.client.client_events import ClientEvent
from uuid import UUID

from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtWidgets import QWidget, QLabel

import pendulum

from guardata.client.types import (
    WorkspaceEntry,
    FsPath,
    EntryID,
    EntryName,
    BackendOrganizationFileLinkAddr,
)
from guardata.client.fs import WorkspaceFS, WorkspaceFSTimestamped, FSBackendOfflineError
from guardata.client.mountpoint.exceptions import (
    MountpointAlreadyMounted,
    MountpointNotMounted,
    MountpointError,
)

from guardata.client.gui.trio_thread import (
    JobResultError,
    ThreadSafeQtSignal,
    QtToTrioJob,
    JobSchedulerNotAvailable,
)
from guardata.client.gui import desktop
from guardata.client.gui.custom_dialogs import show_error, get_text_input, ask_question
from guardata.client.gui.flow_layout import FlowLayout
from guardata.client.gui.lang import translate as _
from guardata.client.gui.workspace_button import WorkspaceButton
from guardata.client.gui.timestamped_workspace_widget import TimestampedWorkspaceWidget
from guardata.client.gui.ui.workspaces_widget import Ui_WorkspacesWidget
from guardata.client.gui.workspace_sharing_widget import WorkspaceSharingWidget


async def _get_reencryption_needs(workspace_fs):
    try:
        reenc_needs = await workspace_fs.get_reencryption_need()
    except FSBackendOfflineError as exc:
        raise JobResultError("offline") from exc
    return workspace_fs.workspace_id, reenc_needs


async def _do_workspace_create(client, workspace_name):
    try:
        workspace_name = EntryName(workspace_name)
    except ValueError:
        raise JobResultError("invalid-name")
    workspace_id = await client.user_fs.workspace_create(workspace_name)
    return workspace_id


async def _do_workspace_rename(client, workspace_id, new_name, button):
    try:
        new_name = EntryName(new_name)
    except ValueError:
        raise JobResultError("invalid-name")
    try:
        await client.user_fs.workspace_rename(workspace_id, new_name)
        return button, new_name
    except Exception as exc:
        raise JobResultError("rename-error") from exc


async def _do_workspace_list(client):
    workspaces = []

    async def _add_workspacefs(workspace_fs, timestamped):
        ws_entry = workspace_fs.get_workspace_entry()
        users_roles = {}
        try:
            roles = await workspace_fs.get_user_roles()
            for user, role in roles.items():
                user_info = await client.get_user_info(user)
                users_roles[user_info.user_id] = (role, user_info)
        except FSBackendOfflineError:
            user_info = await client.get_user_info(workspace_fs.device.user_id)
            users_roles[user_info.user_id] = (ws_entry.role, user_info)

        try:
            # List files and directories in the root directory, used for preview
            files = []
            async for child in workspace_fs.iterdir("/"):
                child_info = await workspace_fs.path_info(child)
                # Do not include confined files and directories in the preview
                if not child_info.get("confined") or client.config.gui_show_confined:
                    files.append(child.name)
        except FSBackendOfflineError:
            pass
        workspaces.append((workspace_fs, ws_entry, users_roles, files, timestamped))

    user_manifest = client.user_fs.get_user_manifest()
    available_workspaces = [w for w in user_manifest.workspaces if w.role]
    for count, workspace in enumerate(available_workspaces):
        workspace_id = workspace.id
        workspace_fs = client.user_fs.get_workspace(workspace_id)
        await _add_workspacefs(workspace_fs, timestamped=False)
    worspaces_timestamped_dict = await client.mountpoint_manager.get_timestamped_mounted()
    for (workspace_id, timestamp), workspace_fs in worspaces_timestamped_dict.items():
        await _add_workspacefs(workspace_fs, timestamped=True)

    return workspaces


async def _do_workspace_mount(client, workspace_id, timestamp: pendulum.Pendulum = None):
    try:
        await client.mountpoint_manager.mount_workspace(workspace_id, timestamp)
    except MountpointAlreadyMounted:
        pass


async def _do_workspace_unmount(client, workspace_id, timestamp: pendulum.Pendulum = None):
    try:
        await client.mountpoint_manager.unmount_workspace(workspace_id, timestamp)
    except MountpointNotMounted:
        pass


class WorkspacesWidget(QWidget, Ui_WorkspacesWidget):
    RESET_TIMER_THRESHOLD = 1000  # ms

    fs_updated_qt = pyqtSignal(ClientEvent, UUID)
    fs_synced_qt = pyqtSignal(ClientEvent, UUID)
    entry_downsynced_qt = pyqtSignal(UUID, UUID)

    sharing_updated_qt = pyqtSignal(WorkspaceEntry, object)
    _workspace_created_qt = pyqtSignal(WorkspaceEntry)
    load_workspace_clicked = pyqtSignal(WorkspaceFS, FsPath, bool)
    workspace_reencryption_success = pyqtSignal(QtToTrioJob)
    workspace_reencryption_error = pyqtSignal(QtToTrioJob)
    workspace_reencryption_progress = pyqtSignal(EntryID, int, int)
    mountpoint_started = pyqtSignal(object, object)
    mountpoint_stopped = pyqtSignal(object, object)

    rename_success = pyqtSignal(QtToTrioJob)
    rename_error = pyqtSignal(QtToTrioJob)
    create_success = pyqtSignal(QtToTrioJob)
    create_error = pyqtSignal(QtToTrioJob)
    list_success = pyqtSignal(QtToTrioJob)
    list_error = pyqtSignal(QtToTrioJob)
    mount_success = pyqtSignal(QtToTrioJob)
    mount_error = pyqtSignal(QtToTrioJob)
    unmount_success = pyqtSignal(QtToTrioJob)
    unmount_error = pyqtSignal(QtToTrioJob)
    reencryption_needs_success = pyqtSignal(QtToTrioJob)
    reencryption_needs_error = pyqtSignal(QtToTrioJob)
    ignore_success = pyqtSignal(QtToTrioJob)
    ignore_error = pyqtSignal(QtToTrioJob)

    def __init__(self, client, jobs_ctx, event_bus, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

        self.client = client
        self.jobs_ctx = jobs_ctx
        self.event_bus = event_bus
        self.reencrypting = set()
        self.disabled_workspaces = self.client.config.disabled_workspaces

        self.layout_workspaces = FlowLayout(spacing=40)
        self.layout_content.addLayout(self.layout_workspaces)

        self.button_add_workspace.clicked.connect(self.create_workspace_clicked)
        self.button_goto_file.clicked.connect(self.goto_file_clicked)

        self.button_add_workspace.apply_style()
        self.button_goto_file.apply_style()

        self.fs_updated_qt.connect(self._on_fs_updated_qt)
        self.fs_synced_qt.connect(self._on_fs_synced_qt)
        self.entry_downsynced_qt.connect(self._on_entry_downsynced_qt)

        self.line_edit_search.textChanged.connect(self.on_workspace_filter)

        self.rename_success.connect(self.on_rename_success)
        self.rename_error.connect(self.on_rename_error)
        self.create_success.connect(self.on_create_success)
        self.create_error.connect(self.on_create_error)
        self.list_success.connect(self.on_list_success)
        self.list_error.connect(self.on_list_error)
        self.reencryption_needs_success.connect(self.on_reencryption_needs_success)
        self.reencryption_needs_error.connect(self.on_reencryption_needs_error)
        self.workspace_reencryption_progress.connect(self._on_workspace_reencryption_progress)
        self.mount_success.connect(self.on_mount_success)
        self.mount_error.connect(self.on_mount_error)
        self.unmount_success.connect(self.on_unmount_success)
        self.unmount_error.connect(self.on_unmount_error)

        self.workspace_reencryption_success.connect(self._on_workspace_reencryption_success)
        self.workspace_reencryption_error.connect(self._on_workspace_reencryption_error)

        self.reset_required = False
        self.reset_timer = QTimer()
        self.reset_timer.setInterval(self.RESET_TIMER_THRESHOLD)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self.on_timeout)

        self.mountpoint_started.connect(self._on_mountpoint_started_qt)
        self.mountpoint_stopped.connect(self._on_mountpoint_stopped_qt)

        self.sharing_updated_qt.connect(self._on_sharing_updated_qt)
        self._workspace_created_qt.connect(self._on_workspace_created_qt)

    def disconnect_all(self):
        pass

    def showEvent(self, event):
        self.event_bus.connect(ClientEvent.FS_WORKSPACE_CREATED, self._on_workspace_created_trio)
        self.event_bus.connect(ClientEvent.FS_ENTRY_UPDATED, self._on_fs_entry_updated_trio)
        self.event_bus.connect(ClientEvent.FS_ENTRY_SYNCED, self._on_fs_entry_synced_trio)
        self.event_bus.connect(ClientEvent.SHARING_UPDATED, self._on_sharing_updated_trio)
        self.event_bus.connect(ClientEvent.FS_ENTRY_DOWNSYNCED, self._on_entry_downsynced_trio)
        self.event_bus.connect(ClientEvent.MOUNTPOINT_STARTED, self._on_mountpoint_started_trio)
        self.event_bus.connect(ClientEvent.MOUNTPOINT_STOPPED, self._on_mountpoint_stopped_trio)
        self.reset()

    def hideEvent(self, event):
        try:
            self.event_bus.disconnect(
                ClientEvent.FS_WORKSPACE_CREATED, self._on_workspace_created_trio
            )
            self.event_bus.disconnect(ClientEvent.FS_ENTRY_UPDATED, self._on_fs_entry_updated_trio)
            self.event_bus.disconnect(ClientEvent.FS_ENTRY_SYNCED, self._on_fs_entry_synced_trio)
            self.event_bus.disconnect(ClientEvent.SHARING_UPDATED, self._on_sharing_updated_trio)
            self.event_bus.disconnect(
                ClientEvent.FS_ENTRY_DOWNSYNCED, self._on_entry_downsynced_trio
            )
            self.event_bus.disconnect(
                ClientEvent.MOUNTPOINT_STARTED, self._on_mountpoint_started_trio
            )
            self.event_bus.disconnect(
                ClientEvent.MOUNTPOINT_STOPPED, self._on_mountpoint_stopped_trio
            )
        except ValueError:
            pass

    def goto_file_clicked(self):
        file_link = get_text_input(
            self,
            _("TEXT_WORKSPACE_GOTO_FILE_LINK_TITLE"),
            _("TEXT_WORKSPACE_GOTO_FILE_LINK_INSTRUCTIONS"),
            placeholder=_("TEXT_WORKSPACE_GOTO_FILE_LINK_PLACEHOLDER"),
            default_text="",
            button_text=_("ACTION_GOTO_FILE_LINK"),
        )
        if not file_link:
            return

        url = None
        try:
            url = BackendOrganizationFileLinkAddr.from_url(file_link)
        except ValueError as exc:
            show_error(self, _("TEXT_WORKSPACE_GOTO_FILE_LINK_INVALID_LINK"), exception=exc)
            return

        for item in self.layout_workspaces.items:
            w = item.widget()
            if w and w.workspace_fs.workspace_id == url.workspace_id:
                self.load_workspace(w.workspace_fs, path=url.path, selected=True)
                return
        show_error(self, _("TEXT_WORKSPACE_GOTO_FILE_LINK_WORKSPACE_NOT_FOUND"))

    def on_workspace_filter(self, pattern):
        pattern = pattern.lower()
        for i in range(self.layout_workspaces.count()):
            item = self.layout_workspaces.itemAt(i)
            if item:
                w = item.widget()
                if pattern and pattern not in w.name.lower():
                    w.hide()
                else:
                    w.show()

    def load_workspace(self, workspace_fs, path=FsPath("/"), selected=False):
        self.load_workspace_clicked.emit(workspace_fs, path, selected)

    def on_create_success(self, job):
        pass

    def on_create_error(self, job):
        if job.status == "invalid-name":
            show_error(self, _("TEXT_WORKSPACE_CREATE_NEW_INVALID_NAME"), exception=job.exc)
        else:
            show_error(self, _("TEXT_WORKSPACE_CREATE_NEW_UNKNOWN_ERROR"), exception=job.exc)

    def on_rename_success(self, job):
        workspace_button, workspace_name = job.ret
        if workspace_button:
            workspace_button.reload_workspace_name(workspace_name)

    def on_rename_error(self, job):
        if job.status == "invalid-name":
            show_error(self, _("TEXT_WORKSPACE_RENAME_INVALID_NAME"), exception=job.exc)
        else:
            show_error(self, _("TEXT_WORKSPACE_RENAME_UNKNOWN_ERROR"), exception=job.exc)

    def on_list_success(self, job):
        self.layout_workspaces.clear()
        workspaces = job.ret

        if not workspaces:
            self.line_edit_search.hide()
            label = QLabel(_("TEXT_WORKSPACE_NO_WORKSPACES"))
            label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            self.layout_workspaces.addWidget(label)
            return

        self.line_edit_search.show()
        for count, workspace in enumerate(workspaces):
            workspace_fs, ws_entry, users_roles, files, timestamped = workspace

            try:
                self.add_workspace(
                    workspace_fs, ws_entry, users_roles, files, timestamped=timestamped
                )
            except JobSchedulerNotAvailable:
                pass

    def on_list_error(self, job):
        self.layout_workspaces.clear()
        label = QLabel(_("TEXT_WORKSPACE_NO_WORKSPACES"))
        label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.layout_workspaces.addWidget(label)

    def on_mount_success(self, job):
        self.reset()

    def on_mount_error(self, job):
        if isinstance(job.exc, MountpointError):
            workspace_id = job.arguments.get("workspace_id")
            timestamp = job.arguments.get("timestamp")
            wb = self.get_workspace_button(workspace_id, timestamp)
            if wb:
                wb.set_mountpoint_state(False)
            show_error(self, _("TEXT_WORKSPACE_CANNOT_MOUNT"), exception=job.exc)

    def on_unmount_success(self, job):
        self.reset()

    def on_unmount_error(self, job):
        if isinstance(job.exc, MountpointError):
            show_error(self, _("TEXT_WORKSPACE_CANNOT_UNMOUNT"), exception=job.exc)

    def on_reencryption_needs_success(self, job):
        workspace_id, reencryption_needs = job.ret
        for idx in range(self.layout_workspaces.count()):
            widget = self.layout_workspaces.itemAt(idx).widget()
            if widget.workspace_fs.workspace_id == workspace_id:
                widget.reencryption_needs = reencryption_needs
                break

    def on_reencryption_needs_error(self, job):
        pass

    def add_workspace(self, workspace_fs, ws_entry, users_roles, files, timestamped):

        # The Qt thread should never hit the client directly.
        # Synchronous calls can run directly in the job system
        # as they won't block the Qt loop for long
        workspace_name = self.jobs_ctx.run_sync(workspace_fs.get_workspace_name)

        # Temporary code to fix the workspace names edited by
        # the previous naming policy (the userfs used to add
        # `(shared by <device>)` at the end of the workspace name)
        token = " (shared by "
        if token in workspace_name:
            workspace_name, *_ = workspace_name.split(token)
            self.jobs_ctx.submit_job(
                ThreadSafeQtSignal(self, "ignore_success", QtToTrioJob),
                ThreadSafeQtSignal(self, "ignore_error", QtToTrioJob),
                _do_workspace_rename,
                client=self.client,
                workspace_id=workspace_fs.workspace_id,
                new_name=workspace_name,
                button=None,
            )
        button = WorkspaceButton(
            workspace_name=workspace_name,
            workspace_fs=workspace_fs,
            users_roles=users_roles,
            is_mounted=self.is_workspace_mounted(workspace_fs.workspace_id, None),
            files=files[:4],
            timestamped=timestamped,
        )
        self.layout_workspaces.addWidget(button)
        button.clicked.connect(self.load_workspace)
        button.share_clicked.connect(self.share_workspace)
        button.reencrypt_clicked.connect(self.reencrypt_workspace)
        button.delete_clicked.connect(self.delete_workspace)
        button.rename_clicked.connect(self.rename_workspace)
        button.remount_ts_clicked.connect(self.remount_workspace_ts)
        button.open_clicked.connect(self.open_workspace)
        button.switch_clicked.connect(self._on_switch_clicked)

        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "reencryption_needs_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "reencryption_needs_error", QtToTrioJob),
            _get_reencryption_needs,
            workspace_fs=workspace_fs,
        )

    def _on_switch_clicked(self, state, workspace_fs, timestamp):
        if state:
            self.mount_workspace(workspace_fs.workspace_id, timestamp)
        else:
            self.unmount_workspace(workspace_fs.workspace_id, timestamp)
        if not timestamp:
            self.update_workspace_config(workspace_fs.workspace_id, state)

    def open_workspace(self, workspace_fs):
        self.open_workspace_file(workspace_fs, None)

    def open_workspace_file(self, workspace_fs, file_name):
        file_name = FsPath("/", file_name) if file_name else FsPath("/")

        # The Qt thread should never hit the client directly.
        # Synchronous calls can run directly in the job system
        # as they won't block the Qt loop for long
        path = self.jobs_ctx.run_sync(
            self.client.mountpoint_manager.get_path_in_mountpoint,
            workspace_fs.workspace_id,
            file_name,
            workspace_fs.timestamp if isinstance(workspace_fs, WorkspaceFSTimestamped) else None,
        )

        desktop.open_file(str(path))

    def remount_workspace_ts(self, workspace_fs):
        def _on_finished(date, time):
            if not date or not time:
                return

            datetime = pendulum.datetime(
                date.year(),
                date.month(),
                date.day(),
                time.hour(),
                time.minute(),
                time.second(),
                tzinfo="local",
            )
            self.mount_workspace(workspace_fs.workspace_id, datetime)

        TimestampedWorkspaceWidget.show_modal(
            workspace_fs=workspace_fs, jobs_ctx=self.jobs_ctx, parent=self, on_finished=_on_finished
        )

    def mount_workspace(self, workspace_id, timestamp=None):
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "mount_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "mount_error", QtToTrioJob),
            _do_workspace_mount,
            client=self.client,
            workspace_id=workspace_id,
            timestamp=timestamp,
        )

    def unmount_workspace(self, workspace_id, timestamp=None):
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "unmount_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "unmount_error", QtToTrioJob),
            _do_workspace_unmount,
            client=self.client,
            workspace_id=workspace_id,
            timestamp=timestamp,
        )

    def update_workspace_config(self, workspace_id, state):
        if state:
            self.disabled_workspaces -= {workspace_id}
        else:
            self.disabled_workspaces |= {workspace_id}
        self.event_bus.send(
            ClientEvent.GUI_CONFIG_CHANGED, disabled_workspaces=self.disabled_workspaces
        )

    def is_workspace_mounted(self, workspace_id, timestamp=None):
        return self.jobs_ctx.run_sync(
            self.client.mountpoint_manager.is_workspace_mounted, workspace_id, timestamp
        )

    def delete_workspace(self, workspace_fs):
        if isinstance(workspace_fs, WorkspaceFSTimestamped):
            self.unmount_workspace(workspace_fs.workspace_id, workspace_fs.timestamp)
            return
        else:
            workspace_name = self.jobs_ctx.run_sync(workspace_fs.get_workspace_name)
            result = ask_question(
                self,
                _("TEXT_WORKSPACE_DELETE_TITLE"),
                _("TEXT_WORKSPACE_DELETE_INSTRUCTIONS_workspace").format(workspace=workspace_name),
                [_("ACTION_DELETE_WORKSPACE_CONFIRM"), _("ACTION_CANCEL")],
            )
            if result != _("ACTION_DELETE_WORKSPACE_CONFIRM"):
                return
            # Workspace deletion is not available yet (button should be hidden anyway)

    def rename_workspace(self, workspace_button):
        new_name = get_text_input(
            self,
            _("TEXT_WORKSPACE_RENAME_TITLE"),
            _("TEXT_WORKSPACE_RENAME_INSTRUCTIONS"),
            placeholder=_("TEXT_WORKSPACE_RENAME_PLACEHOLDER"),
            default_text=workspace_button.name,
            button_text=_("ACTION_WORKSPACE_RENAME_CONFIRM"),
        )
        if not new_name:
            return
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "rename_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "rename_error", QtToTrioJob),
            _do_workspace_rename,
            client=self.client,
            workspace_id=workspace_button.workspace_fs.workspace_id,
            new_name=new_name,
            button=workspace_button,
        )

    def share_workspace(self, workspace_fs):
        WorkspaceSharingWidget.show_modal(
            user_fs=self.client.user_fs,
            workspace_fs=workspace_fs,
            client=self.client,
            jobs_ctx=self.jobs_ctx,
            parent=self,
            on_finished=self.reset,
        )

    def reencrypt_workspace(self, workspace_id, user_revoked, role_revoked):
        if workspace_id in self.reencrypting or (not user_revoked and not role_revoked):
            return

        question = ""
        if user_revoked:
            question += "{}\n".format(_("TEXT_WORKSPACE_NEED_REENCRYPTION_BECAUSE_USER_REVOKED"))
        if role_revoked:
            question += "{}\n".format(_("TEXT_WORKSPACE_NEED_REENCRYPTION_BECAUSE_USER_REMOVED"))
        question += _("TEXT_WORKSPACE_NEED_REENCRYPTION_INSTRUCTIONS")

        r = ask_question(
            self,
            _("TEXT_WORKSPACE_NEED_REENCRYPTION_TITLE"),
            question,
            [_("ACTION_WORKSPACE_REENCRYPTION_CONFIRM"), _("ACTION_CANCEL")],
        )
        if r != _("ACTION_WORKSPACE_REENCRYPTION_CONFIRM"):
            return

        async def _reencrypt(on_progress, workspace_id):
            job = await self.client.user_fs.workspace_start_reencryption(workspace_id)
            while True:
                total, done = await job.do_one_batch(size=1)
                on_progress.emit(workspace_id, total, done)
                if total == done:
                    break
            return workspace_id

        self.reencrypting.add(workspace_id)

        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "workspace_reencryption_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "workspace_reencryption_error", QtToTrioJob),
            _reencrypt,
            on_progress=ThreadSafeQtSignal(
                self, "workspace_reencryption_progress", EntryID, int, int
            ),
            workspace_id=workspace_id,
        )

    def _on_workspace_reencryption_success(self, job):
        workspace_id = job.ret
        self.reencrypting.remove(workspace_id)

    def _on_workspace_reencryption_error(self, job):
        workspace_id = job.ret
        self.reencrypting.remove(workspace_id)

    def get_workspace_button(self, workspace_id, timestamp):
        for idx in range(self.layout_workspaces.count()):
            widget = self.layout_workspaces.itemAt(idx).widget()
            if (
                widget
                and not isinstance(widget, QLabel)
                and widget.workspace_id == workspace_id
                and timestamp == widget.timestamp
            ):
                return widget
        return None

    def _on_workspace_reencryption_progress(self, workspace_id, total, done):
        wb = self.get_workspace_button(workspace_id, None)
        if done == total:
            wb.reencrypting = None
        else:
            wb.reencrypting = (total, done)

    def create_workspace_clicked(self):
        workspace_name = get_text_input(
            parent=self,
            title=_("TEXT_WORKSPACE_NEW_TITLE"),
            message=_("TEXT_WORKSPACE_NEW_INSTRUCTIONS"),
            placeholder=_("TEXT_WORKSPACE_NEW_PLACEHOLDER"),
            button_text=_("ACTION_WORKSPACE_NEW_CREATE"),
        )
        if not workspace_name:
            return
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "create_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "create_error", QtToTrioJob),
            _do_workspace_create,
            client=self.client,
            workspace_name=workspace_name,
        )

    def reset(self):
        if self.reset_timer.isActive():
            self.reset_required = True
        else:
            self.reset_required = False
            self.reset_timer.start()
            self.list_workspaces()

    def on_timeout(self):
        if self.reset_required:
            self.reset()

    def list_workspaces(self):
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "list_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "list_error", QtToTrioJob),
            _do_workspace_list,
            client=self.client,
        )

    def _on_sharing_updated_trio(self, event, new_entry, previous_entry):
        self.sharing_updated_qt.emit(new_entry, previous_entry)

    def _on_sharing_updated_qt(self, new_entry, previous_entry):
        self.reset()

    def _on_workspace_created_trio(self, event, new_entry):
        self._workspace_created_qt.emit(new_entry)

    def _on_workspace_created_qt(self, workspace_entry):
        self.reset()

    def _on_fs_entry_synced_trio(self, event, id, workspace_id=None):
        self.fs_synced_qt.emit(event, id)

    def _on_fs_entry_updated_trio(self, event, workspace_id=None, id=None):
        if workspace_id and not id:
            self.fs_updated_qt.emit(event, workspace_id)

    def _on_entry_downsynced_trio(self, event, workspace_id=None, id=None):
        self.entry_downsynced_qt.emit(workspace_id, id)

    def _on_entry_downsynced_qt(self, workspace_id, id):
        self.reset()

    def _on_fs_synced_qt(self, event, id):
        self.reset()

    def _on_fs_updated_qt(self, event, workspace_id):
        self.reset()

    def _on_mountpoint_started_qt(self, workspace_id, timestamp):
        wb = self.get_workspace_button(workspace_id, timestamp)
        if wb:
            wb.set_mountpoint_state(True)

    def _on_mountpoint_stopped_qt(self, workspace_id, timestamp):
        wb = self.get_workspace_button(workspace_id, timestamp)
        if wb:
            wb.set_mountpoint_state(False)

    def _on_mountpoint_started_trio(self, event, mountpoint, workspace_id, timestamp):
        self.mountpoint_started.emit(workspace_id, timestamp)

    def _on_mountpoint_stopped_trio(self, event, mountpoint, workspace_id, timestamp):
        self.mountpoint_stopped.emit(workspace_id, timestamp)
