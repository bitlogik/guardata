# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from guardata.client.client_events import ClientEvent
from typing import Optional
from structlog import get_logger

from PyQt5.QtCore import QCoreApplication, pyqtSignal, Qt, QSize
from PyQt5.QtGui import QColor, QIcon, QKeySequence
from PyQt5.QtWidgets import QMainWindow, QApplication, QMenu, QShortcut

from guardata import __version__ as GUARDATA_VERSION

from guardata.client.local_device import list_available_devices, get_key_file
from guardata.client.config import save_config
from guardata.client.types import (
    BackendActionAddr,
    BackendInvitationAddr,
    BackendOrganizationBootstrapAddr,
    BackendOrganizationFileLinkAddr,
)
from guardata.api.protocol import InvitationType
from guardata.client.gui.lang import translate as _
from guardata.client.gui.instance_widget import InstanceWidget
from guardata.client.gui.guardata_application import guardataApp
from guardata.client.gui import desktop

# from guardata.client.gui.changelog_widget import ChangelogWidget
from guardata.client.gui.bootstrap_organization_widget import BootstrapOrganizationWidget
from guardata.client.gui.claim_user_widget import ClaimUserWidget
from guardata.client.gui.claim_device_widget import ClaimDeviceWidget
from guardata.client.gui.license_widget import LicenseWidget
from guardata.client.gui.about_widget import AboutWidget
from guardata.client.gui.settings_widget import SettingsWidget
from guardata.client.gui.custom_dialogs import (
    ask_question,
    show_error,
    GreyedDialog,
    get_text_input,
)
from guardata.client.gui.custom_widgets import Button
from guardata.client.gui.create_org_widget import CreateOrgWidget
from guardata.client.gui import validators
from guardata.client.gui.ui.main_window import Ui_MainWindow


logger = get_logger()


class MainWindow(QMainWindow, Ui_MainWindow):
    foreground_needed = pyqtSignal()
    new_instance_needed = pyqtSignal(object)
    systray_notification = pyqtSignal(str, str, int)

    TAB_NOTIFICATION_COLOR = QColor(46, 146, 208)
    TAB_NOT_SELECTED_COLOR = QColor(123, 132, 163)
    TAB_SELECTED_COLOR = QColor(12, 65, 159)

    def __init__(self, jobs_ctx, event_bus, config, minimize_on_close: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

        self.setMenuBar(None)
        self.jobs_ctx = jobs_ctx
        self.event_bus = event_bus
        self.config = config
        self.minimize_on_close = minimize_on_close
        # Explain only once that the app stays in background
        self.minimize_on_close_notif_already_send = False
        self.force_close = False
        self.need_close = False
        self.event_bus.connect(ClientEvent.GUI_CONFIG_CHANGED, self.on_config_updated)
        self.setWindowTitle(
            _("TEXT_GUARDATA_WINDOW_TITLE_version").format(version=GUARDATA_VERSION)
        )
        self.foreground_needed.connect(self._on_foreground_needed)
        self.new_instance_needed.connect(self._on_new_instance_needed)
        self.tab_center.tabCloseRequested.connect(self.close_tab)

        self.menu_button = Button()
        self.menu_button.setCursor(Qt.PointingHandCursor)
        self.menu_button.setIcon(QIcon(":/icons/images/material/menu.svg"))
        self.menu_button.setIconSize(QSize(24, 24))
        self.menu_button.setText(_("ACTION_MAIN_MENU_SHOW"))
        self.menu_button.setObjectName("MenuButton")
        self.menu_button.setProperty("color", QColor(0x00, 0x92, 0xFF))
        self.menu_button.setProperty("hover_color", QColor(0x00, 0x70, 0xDD))
        self.menu_button.setStyleSheet(
            "#MenuButton {background: none; border: none; color: #2185d0;}"
            "#MenuButton:hover {color: #0070DD;}"
        )
        self.menu_button.apply_style()
        self.menu_button.clicked.connect(self._show_menu)
        self.tab_center.setCornerWidget(self.menu_button, Qt.TopRightCorner)

        self.add_tab_button = Button()
        self.add_tab_button.setCursor(Qt.PointingHandCursor)
        self.add_tab_button.setIcon(QIcon(":/icons/images/material/add.svg"))
        self.add_tab_button.setIconSize(QSize(24, 24))
        self.add_tab_button.setProperty("color", QColor(0x00, 0x92, 0xFF))
        self.add_tab_button.setProperty("hover_color", QColor(0x00, 0x70, 0xDD))
        self.add_tab_button.setStyleSheet("background: none; border: none;")
        self.add_tab_button.apply_style()
        self.add_tab_button.clicked.connect(self._on_add_instance_clicked)
        self.tab_center.setCornerWidget(self.add_tab_button, Qt.TopLeftCorner)

        self.tab_center.currentChanged.connect(self.on_current_tab_changed)
        self._define_shortcuts()
        self.ensurePolished()

    def _define_shortcuts(self):
        self.shortcut_close = QShortcut(QKeySequence(QKeySequence.Close), self)
        self.shortcut_close.activated.connect(self._shortcut_proxy(self.close_current_tab))
        self.shortcut_new_tab = QShortcut(QKeySequence(QKeySequence.AddTab), self)
        self.shortcut_new_tab.activated.connect(self._shortcut_proxy(self._on_add_instance_clicked))
        self.shortcut_settings = QShortcut(QKeySequence(_("Ctrl+K")), self)
        self.shortcut_settings.activated.connect(self._shortcut_proxy(self._show_settings))
        self.shortcut_menu = QShortcut(QKeySequence(_("Alt+E")), self)
        self.shortcut_menu.activated.connect(self._shortcut_proxy(self._show_menu))
        # self.shortcut_help = QShortcut(QKeySequence(QKeySequence.HelpContents), self)
        # self.shortcut_help.activated.connect(self._shortcut_proxy(self._on_show_doc_clicked))
        self.shortcut_quit = QShortcut(QKeySequence(QKeySequence.Quit), self)
        self.shortcut_quit.activated.connect(self._shortcut_proxy(self.close_app))
        self.shortcut_create_org = QShortcut(QKeySequence(QKeySequence.New), self)
        self.shortcut_create_org.activated.connect(
            self._shortcut_proxy(self._on_create_org_clicked)
        )
        self.shortcut_join_org = QShortcut(QKeySequence(QKeySequence.Open), self)
        self.shortcut_join_org.activated.connect(self._shortcut_proxy(self._on_join_org_clicked))
        shortcut = QShortcut(QKeySequence(QKeySequence.NextChild), self)
        shortcut.activated.connect(self._shortcut_proxy(self._cycle_tabs(1)))
        shortcut = QShortcut(QKeySequence(QKeySequence.PreviousChild), self)
        shortcut.activated.connect(self._shortcut_proxy(self._cycle_tabs(-1)))

    def _shortcut_proxy(self, funct):
        def _inner_proxy():
            if guardataApp.has_active_modal():
                return
            funct()

        return _inner_proxy

    def _cycle_tabs(self, offset):
        def _inner_cycle_tabs():
            idx = self.tab_center.currentIndex()
            idx += offset
            if idx >= self.tab_center.count():
                idx = 0
            if idx < 0:
                idx = self.tab_center.count() - 1
            self.switch_to_tab(idx)

        return _inner_cycle_tabs

    def _toggle_add_tab_button(self):
        if self._get_login_tab_index() == -1:
            self.add_tab_button.setDisabled(False)
        else:
            self.add_tab_button.setDisabled(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for win in self.children():
            if win.objectName() == "GreyedDialog":
                win.resize(event.size())
                win.move(0, 0)

    def _show_menu(self):
        menu = QMenu(self)
        menu.setObjectName("MainMenu")
        action = None

        idx = self._get_login_tab_index()
        action = menu.addAction(_("ACTION_MAIN_MENU_ADD_INSTANCE"))
        action.triggered.connect(self._on_add_instance_clicked)
        action.setShortcut(self.shortcut_new_tab.key())
        action.setShortcutVisibleInContextMenu(True)

        if idx != -1:
            action.setDisabled(True)

        action = menu.addAction(_("ACTION_MAIN_MENU_CREATE_ORGANIZATION"))
        action.triggered.connect(self._on_create_org_clicked)
        action.setShortcut(self.shortcut_create_org.key())
        action.setShortcutVisibleInContextMenu(True)

        action = menu.addAction(_("ACTION_MAIN_MENU_JOIN_ORGANIZATION"))
        action.triggered.connect(self._on_join_org_clicked)
        action.setShortcut(self.shortcut_join_org.key())
        action.setShortcutVisibleInContextMenu(True)

        menu.addSeparator()

        action = menu.addAction(_("ACTION_MAIN_MENU_SETTINGS"))
        action.triggered.connect(self._show_settings)
        action.setShortcut(self.shortcut_settings.key())
        action.setShortcutVisibleInContextMenu(True)

        # action = menu.addAction(_("ACTION_MAIN_MENU_OPEN_DOCUMENTATION"))
        # action.triggered.connect(self._on_show_doc_clicked)
        # action.setShortcut(self.shortcut_help.key())
        # action.setShortcutVisibleInContextMenu(True)

        action = menu.addAction(_("ACTION_MAIN_MENU_ABOUT"))
        action.triggered.connect(self._show_about)
        # action = menu.addAction(_("ACTION_MAIN_MENU_CHANGELOG"))
        # action.triggered.connect(self._show_changelog)
        action = menu.addAction(_("ACTION_MAIN_MENU_LICENSE"))
        action.triggered.connect(self._show_license)
        action = menu.addAction(_("ACTION_MAIN_MENU_FEEDBACK_SEND"))
        action.triggered.connect(self._on_send_feedback_clicked)
        menu.addSeparator()
        action = menu.addAction(_("ACTION_MAIN_MENU_QUIT_guardata"))
        action.triggered.connect(self.close_app)
        action.setShortcut(self.shortcut_quit.key())
        action.setShortcutVisibleInContextMenu(True)

        pos = self.menu_button.pos()
        pos.setY(pos.y() + self.menu_button.size().height())
        pos = self.mapToGlobal(pos)
        menu.exec_(pos)
        menu.setParent(None)

    def _show_about(self):
        w = AboutWidget()
        d = GreyedDialog(w, title="", parent=self, width=1000)
        d.exec_()

    def _show_license(self):
        w = LicenseWidget()
        d = GreyedDialog(w, title=_("TEXT_LICENSE_TITLE"), parent=self, width=1000)
        d.exec_()

    # def _show_changelog(self):
    # w = ChangelogWidget()
    # d = GreyedDialog(w, title=_("TEXT_CHANGELOG_TITLE"), parent=self, width=1000)
    # d.exec_()

    def _show_settings(self):
        w = SettingsWidget(self.config, self.jobs_ctx, self.event_bus)
        d = GreyedDialog(w, title=_("TEXT_SETTINGS_TITLE"), parent=self, width=1000)
        d.exec_()

    # def _on_show_doc_clicked(self):
    # desktop.open_doc_link()

    def _on_send_feedback_clicked(self):
        desktop.open_feedback_link()

    def _on_add_instance_clicked(self):
        self.add_instance()

    def _on_create_org_clicked(self):
        def _on_finished(action_addr):
            if action_addr is None:
                return
            self._on_bootstrap_org_clicked(action_addr)

        CreateOrgWidget.show_modal(self.jobs_ctx, self, on_finished=_on_finished)

    def _on_join_org_clicked(self):
        url = get_text_input(
            parent=self,
            title=_("TEXT_JOIN_ORG_URL_TITLE"),
            message=_("TEXT_JOIN_ORG_URL_INSTRUCTIONS"),
            placeholder=_("TEXT_JOIN_ORG_URL_PLACEHOLDER"),
        )
        if url is None:
            return
        elif url == "":
            show_error(self, _("TEXT_JOIN_ORG_INVALID_URL"))
            return

        action_addr = None
        try:
            action_addr = BackendActionAddr.from_url(url)
        except ValueError as exc:
            show_error(self, _("TEXT_INVALID_URL"), exception=exc)
            return

        if isinstance(action_addr, BackendOrganizationBootstrapAddr):
            self._on_bootstrap_org_clicked(action_addr)
        elif isinstance(action_addr, BackendInvitationAddr):
            if action_addr.invitation_type == InvitationType.USER:
                self._on_claim_user_clicked(action_addr)
            elif action_addr.invitation_type == InvitationType.DEVICE:
                self._on_claim_device_clicked(action_addr)
            else:
                show_error(self, _("TEXT_INVALID_URL"))
                return
        else:
            show_error(self, _("TEXT_INVALID_URL"))
            return

    def _on_bootstrap_org_clicked(self, action_addr=None):
        if not action_addr:
            url = get_text_input(
                parent=self,
                title=_("TEXT_BOOTSTRAP_ORG_URL_TITLE"),
                message=_("TEXT_BOOTSTRAP_ORG_URL_INSTRUCTIONS"),
                placeholder=_("TEXT_BOOTSTRAP_ORG_URL_PLACEHOLDER"),
                validator=validators.BackendOrganizationBootstrapAddrValidator(),
            )
            if url is None:
                return
            elif url == "":
                show_error(self, _("TEXT_BOOTSTRAP_ORG_INVALID_URL"))
                return

            action_addr = None
            try:
                action_addr = BackendOrganizationBootstrapAddr.from_url(url)
            except ValueError as exc:
                show_error(self, _("TEXT_BOOTSTRAP_ORG_INVALID_URL"), exception=exc)
                return

        def _on_finished(ret):
            if ret:
                self.reload_login_devices()
                self.try_login(ret[0], ret[1])

        BootstrapOrganizationWidget.show_modal(
            jobs_ctx=self.jobs_ctx,
            config=self.config,
            addr=action_addr,
            parent=self,
            on_finished=_on_finished,
        )

    def _on_claim_user_clicked(self, action_addr):
        widget = None

        def _on_finished():
            nonlocal widget
            if not widget.status:
                return
            login, password = widget.status
            self.reload_login_devices()
            self.try_login(login, password)

        widget = ClaimUserWidget.show_modal(
            jobs_ctx=self.jobs_ctx,
            config=self.config,
            addr=action_addr,
            parent=self,
            on_finished=_on_finished,
        )

    def _on_claim_device_clicked(self, action_addr):
        widget = None

        def _on_finished():
            nonlocal widget
            if not widget.status:
                return
            login, password = widget.status
            self.reload_login_devices()
            self.try_login(login, password)

        widget = ClaimDeviceWidget.show_modal(
            jobs_ctx=self.jobs_ctx,
            config=self.config,
            addr=action_addr,
            parent=self,
            on_finished=_on_finished,
        )

    def try_login(self, device, password):
        idx = self._get_login_tab_index()
        tab = None
        if idx == -1:
            tab = self.add_new_tab()
        else:
            tab = self.tab_center.widget(idx)
        kf = get_key_file(self.config.config_dir, device)
        tab.login_with_password(kf, password)

    def reload_login_devices(self):
        idx = self._get_login_tab_index()
        if idx == -1:
            return
        w = self.tab_center.widget(idx)
        if not w:
            return
        w.show_login_widget()

    def on_current_tab_changed(self, index):
        for i in range(self.tab_center.tabBar().count()):
            if i != index:
                if self.tab_center.tabBar().tabTextColor(i) != MainWindow.TAB_NOTIFICATION_COLOR:
                    self.tab_center.tabBar().setTabTextColor(i, MainWindow.TAB_NOT_SELECTED_COLOR)
            else:
                self.tab_center.tabBar().setTabTextColor(i, MainWindow.TAB_SELECTED_COLOR)

    def _on_foreground_needed(self):
        self.show_top()

    def _on_new_instance_needed(self, start_arg):
        self.add_instance(start_arg)
        self.show_top()

    def on_config_updated(self, event, **kwargs):
        self.config = self.config.evolve(**kwargs)
        save_config(self.config)

    def showMaximized(self, skip_dialogs=False, invitation_link=""):
        super().showMaximized()
        QCoreApplication.processEvents()

        # Used with the --diagnose option
        if skip_dialogs:
            return

        # At the very first launch
        if self.config.gui_first_launch:
            self.event_bus.send(
                ClientEvent.GUI_CONFIG_CHANGED,
                gui_first_launch=False,
                gui_last_version=GUARDATA_VERSION,
            )

        # For each guardata update
        if self.config.gui_last_version and self.config.gui_last_version != GUARDATA_VERSION:

            # Acknowledge the changes
            self.event_bus.send(ClientEvent.GUI_CONFIG_CHANGED, gui_last_version=GUARDATA_VERSION)

        devices = list_available_devices(self.config.config_dir)
        if not len(devices) and not invitation_link:
            r = ask_question(
                self,
                _("TEXT_KICKSTART_GUARDATA_WHAT_TO_DO_TITLE"),
                _("TEXT_KICKSTART_GUARDATA_WHAT_TO_DO_INSTRUCTIONS"),
                [
                    _("ACTION_NO_DEVICE_CREATE_ORGANIZATION"),
                    _("ACTION_NO_DEVICE_JOIN_ORGANIZATION"),
                ],
                radio_mode=True,
            )
            if r == _("ACTION_NO_DEVICE_JOIN_ORGANIZATION"):
                self._on_join_org_clicked()
            elif r == _("ACTION_NO_DEVICE_CREATE_ORGANIZATION"):
                self._on_create_org_clicked()

    def show_top(self):
        self.activateWindow()
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.raise_()
        self.show()

    def on_tab_state_changed(self, tab, state):
        idx = self.tab_center.indexOf(tab)
        if idx == -1:
            return
        if state == "login":
            if self._get_login_tab_index() != -1:
                self.tab_center.removeTab(idx)
            else:
                self.tab_center.setTabToolTip(idx, _("TEXT_TAB_TITLE_LOG_IN_SCREEN"))
                self.tab_center.setTabText(idx, _("TEXT_TAB_TITLE_LOG_IN_SCREEN"))
        elif state == "logout":
            self.tab_center.removeTab(idx)
            if self._get_login_tab_index() == -1:
                self.add_instance()
        elif state == "connected":
            device = tab.current_device
            tab_name = (
                f"{device.organization_id} - {device.short_user_display} - {device.device_display}"
            )
            self.tab_center.setTabToolTip(idx, tab_name)
            self.tab_center.setTabText(idx, tab_name)
        if self.tab_center.count() == 1:
            self.tab_center.setTabsClosable(False)
        self._toggle_add_tab_button()

    def on_tab_notification(self, widget, event):
        idx = self.tab_center.indexOf(widget)
        if idx == -1 or idx == self.tab_center.currentIndex():
            return
        if event == ClientEvent.SHARING_UPDATED:
            self.tab_center.tabBar().setTabTextColor(idx, MainWindow.TAB_NOTIFICATION_COLOR)

    def _get_login_tab_index(self):
        for idx in range(self.tab_center.count()):
            if self.tab_center.tabText(idx) == _("TEXT_TAB_TITLE_LOG_IN_SCREEN"):
                return idx
        return -1

    def add_new_tab(self):
        tab = InstanceWidget(self.jobs_ctx, self.event_bus, self.config, self.systray_notification)
        tab.join_organization_clicked.connect(self._on_join_org_clicked)
        tab.create_organization_clicked.connect(self._on_create_org_clicked)
        idx = self.tab_center.addTab(tab, "")
        tab.state_changed.connect(self.on_tab_state_changed)
        self.tab_center.setCurrentIndex(idx)
        if self.tab_center.count() > 1:
            self.tab_center.setTabsClosable(True)
        else:
            self.tab_center.setTabsClosable(False)
        return tab

    def switch_to_tab(self, idx):
        if not guardataApp.has_active_modal():
            self.tab_center.setCurrentIndex(idx)

    def switch_to_login_tab(self):
        idx = self._get_login_tab_index()
        if idx != -1:
            self.switch_to_tab(idx)
        else:
            tab = self.add_new_tab()
            tab.show_login_widget()
            self.on_tab_state_changed(tab, "login")
            self.switch_to_tab(self.tab_center.count() - 1)
            idx = self.tab_center.count() - 1

    def go_to_file_link(self, action_addr):
        devices = list_available_devices(self.config.config_dir)
        found_org = False
        for available_device in devices:
            if available_device.organization_id == action_addr.organization_id:
                found_org = True
                break

        if not found_org:
            show_error(
                self,
                _("TEXT_FILE_LINK_NOT_IN_ORG_organization").format(
                    organization=action_addr.organization_id
                ),
            )
            return

        for idx in range(self.tab_center.count()):
            if self.tab_center.tabText(idx) == _("TEXT_TAB_TITLE_LOG_IN_SCREEN"):
                continue
            w = self.tab_center.widget(idx)
            if (
                not w
                or not w.client
                or w.client.device.organization_addr.organization_id != action_addr.organization_id
            ):
                continue
            user_manifest = w.client.user_fs.get_user_manifest()
            found_workspace = False
            for wk in user_manifest.workspaces:
                if not wk.role:
                    continue
                if wk.id == action_addr.workspace_id:
                    found_workspace = True
                    central_widget = w.get_central_widget()
                    try:
                        central_widget.show_mount_widget()
                        central_widget.mount_widget.show_files_widget(
                            w.client.user_fs.get_workspace(wk.id), action_addr.path, selected=True
                        )
                        self.switch_to_tab(idx)
                    except AttributeError:
                        logger.exception("Central widget is not available")
                    return
            if not found_workspace:
                show_error(
                    self,
                    _("TEXT_FILE_LINK_WORKSPACE_NOT_FOUND_organization").format(
                        organization=action_addr.organization_id
                    ),
                )
                return
        show_error(
            self,
            _("TEXT_FILE_LINK_PLEASE_LOG_IN_organization").format(
                organization=action_addr.organization_id
            ),
        )
        self.switch_to_login_tab()

    def add_instance(self, start_arg: Optional[str] = None):
        action_addr = None
        if start_arg:
            try:
                action_addr = BackendActionAddr.from_url(start_arg)
            except ValueError as exc:
                show_error(self, _("TEXT_INVALID_URL"), exception=exc)

        # Do not open a new logging widget if the organisation is already opened
        if (
            action_addr
            and isinstance(action_addr, BackendOrganizationFileLinkAddr)
            and self.tab_center.count()
        ):
            self.go_to_file_link(action_addr)
            return

        self.switch_to_login_tab()

        self.show_top()
        if action_addr and isinstance(action_addr, BackendOrganizationFileLinkAddr):
            # Organization is not connected, login is required
            return
        elif action_addr:
            if isinstance(action_addr, BackendOrganizationBootstrapAddr):
                self._on_bootstrap_org_clicked(action_addr)
            elif isinstance(action_addr, BackendInvitationAddr):
                if action_addr.invitation_type == InvitationType.USER:
                    self._on_claim_user_clicked(action_addr)
                elif action_addr.invitation_type == InvitationType.DEVICE:
                    self._on_claim_device_clicked(action_addr)
                else:
                    show_error(self, _("TEXT_INVALID_URL"))
                    return

    def close_current_tab(self, force=False):
        if self.tab_center.count() == 1:
            self.close_app()
        else:
            idx = self.tab_center.currentIndex()
            self.close_tab(idx, force=force)

    def close_app(self, force=False):
        self.show_top()
        self.need_close = True
        self.force_close = force
        self.close()

    def close_all_tabs(self):
        for idx in range(self.tab_center.count()):
            self.close_tab(idx, force=True)

    def close_tab(self, index, force=False):
        tab = self.tab_center.widget(index)
        if not force:
            r = _("ACTION_TAB_CLOSE_CONFIRM")
            if tab and tab.is_logged_in:
                r = ask_question(
                    self,
                    _("TEXT_TAB_CLOSE_TITLE"),
                    _("TEXT_TAB_CLOSE_INSTRUCTIONS_device").format(
                        device=f"{tab.core.device.short_user_display} - {tab.core.device.device_display}"
                    ),
                    [_("ACTION_TAB_CLOSE_CONFIRM"), _("ACTION_CANCEL")],
                )
            if r != _("ACTION_TAB_CLOSE_CONFIRM"):
                return
        self.tab_center.removeTab(index)
        if not tab:
            return
        tab.logout()
        self.reload_login_devices()
        if self.tab_center.count() == 1:
            self.tab_center.setTabsClosable(False)
        self._toggle_add_tab_button()

    def closeEvent(self, event):
        if self.minimize_on_close and not self.need_close:
            self.hide()
            event.ignore()
            if not self.minimize_on_close_notif_already_send:
                self.minimize_on_close_notif_already_send = True
                self.systray_notification.emit(
                    "guardata", _("TEXT_TRAY_GUARDATA_STILL_RUNNING_MESSAGE"), 2000
                )
        else:
            if self.config.gui_confirmation_before_close and not self.force_close:
                result = ask_question(
                    self if self.isVisible() else None,
                    _("TEXT_GUARDATA_QUIT_TITLE"),
                    _("TEXT_GUARDATA_QUIT_INSTRUCTIONS"),
                    [_("ACTION_GUARDATA_QUIT_CONFIRM"), _("ACTION_CANCEL")],
                )
                if result != _("ACTION_GUARDATA_QUIT_CONFIRM"):
                    event.ignore()
                    self.force_close = False
                    self.need_close = False
                    return

            self.close_all_tabs()
            event.accept()
            QApplication.quit()
