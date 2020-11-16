# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest

from PyQt5 import QtCore, QtWidgets

from guardata.client.types import WorkspaceRole
from guardata.client.local_device import save_device_with_password
from guardata.client.gui.workspace_button import WorkspaceButton
from guardata.client.gui.lang import translate
from guardata.client.gui.login_widget import LoginPasswordInputWidget

from tests.common import customize_fixtures


@pytest.fixture
def catch_share_workspace_widget(widget_catcher_factory):
    return widget_catcher_factory(
        "guardata.client.gui.workspace_sharing_widget.WorkspaceSharingWidget"
    )


@pytest.fixture
async def gui_workspace_sharing(
    logged_gui, catch_share_workspace_widget, monkeypatch, aqtbot, autoclose_dialog, input_patcher
):
    w_w = await logged_gui.test_switch_to_workspaces_widget()

    input_patcher.patch_text_input(
        "guardata.client.gui.workspaces_widget.get_text_input",
        QtWidgets.QDialog.Accepted,
        "Workspace",
    )
    await aqtbot.mouse_click(w_w.button_add_workspace, QtCore.Qt.LeftButton)

    def _workspace_added():
        assert w_w.layout_workspaces.count() == 1
        wk_button = w_w.layout_workspaces.itemAt(0).widget()
        assert isinstance(wk_button, WorkspaceButton)
        assert wk_button.name == "Workspace"
        assert wk_button.label_title.toolTip() == "Workspace (private)"
        assert wk_button.label_title.text() == "Workspace (private)"
        assert not autoclose_dialog.dialogs

    await aqtbot.wait_until(_workspace_added, timeout=4000)
    wk_button = w_w.layout_workspaces.itemAt(0).widget()

    await aqtbot.mouse_click(wk_button.button_share, QtCore.Qt.LeftButton)
    share_w_w = await catch_share_workspace_widget()
    async with aqtbot.wait_exposed(share_w_w):
        pass
    yield logged_gui, w_w, share_w_w


@pytest.mark.gui
@pytest.mark.trio
async def test_workspace_sharing_list_users(
    aqtbot, running_backend, gui_workspace_sharing, autoclose_dialog
):
    logged_gui, w_w, share_w_w = gui_workspace_sharing

    def _users_listed():
        assert share_w_w.scroll_content.layout().count() == 4

    await aqtbot.wait_until(_users_listed)

    main_user_w = share_w_w.scroll_content.layout().itemAt(0).widget()
    assert main_user_w.user_info.short_user_display == "Boby McBobFace"
    assert main_user_w.label_name.text() == "<b>Boby McBobFace</b>"
    assert main_user_w.label_email.text() == "bob@example.com"
    assert main_user_w.combo_role.currentIndex() == 4
    assert main_user_w.combo_role.currentText() == translate("TEXT_WORKSPACE_ROLE_OWNER")

    for i in range(1, 3):
        user_w = share_w_w.scroll_content.layout().itemAt(i).widget()
        assert user_w.combo_role.currentIndex() == 0
        assert user_w.combo_role.currentText() == translate("TEXT_WORKSPACE_ROLE_NOT_SHARED")
        assert user_w.isEnabled() is True


@pytest.mark.gui
@pytest.mark.trio
async def test_share_workspace(
    aqtbot,
    running_backend,
    gui_workspace_sharing,
    autoclose_dialog,
    client_config,
    alice,
    adam,
    catch_share_workspace_widget,
    qt_thread_gateway,
):
    password = "P2ssxdor!s3"
    save_device_with_password(client_config.config_dir, alice, password)
    save_device_with_password(client_config.config_dir, adam, password)

    logged_gui, w_w, share_w_w = gui_workspace_sharing

    def _users_listed():
        assert share_w_w.scroll_content.layout().count() == 4

    await aqtbot.wait_until(_users_listed)

    user_w = share_w_w.scroll_content.layout().itemAt(1).widget()
    assert user_w.combo_role.currentIndex() == 0
    user_name = user_w.user_info.short_user_display

    def _set_manager():
        user_w.combo_role.setCurrentIndex(3)

    async with aqtbot.wait_signal(share_w_w.share_success):
        await qt_thread_gateway.send_action(_set_manager)

    async with aqtbot.wait_signals([share_w_w.parent().parent().closing, w_w.list_success]):

        def _close_dialog():
            share_w_w.parent().parent().reject()

        await qt_thread_gateway.send_action(_close_dialog)

    autoclose_dialog.reset()

    def _workspace_listed():
        assert w_w.layout_workspaces.count() == 1
        wk_button = w_w.layout_workspaces.itemAt(0).widget()
        assert isinstance(wk_button, WorkspaceButton)
        assert wk_button.name == "Workspace"
        assert wk_button.label_title.toolTip() == "Workspace (shared with Adamy McAdamFace)"
        assert wk_button.label_title.text() == "Workspace (shared wi..."
        assert not autoclose_dialog.dialogs

    await aqtbot.wait_until(_workspace_listed, timeout=3000)

    login_w = await logged_gui.test_logout_and_switch_to_login_widget()

    accounts_w = login_w.widget.layout().itemAt(0).widget()

    for i in range(accounts_w.accounts_widget.layout().count() - 1):
        acc_w = accounts_w.accounts_widget.layout().itemAt(i).widget()
        if acc_w.label_name.text() == user_name:
            async with aqtbot.wait_signal(accounts_w.account_clicked):
                await aqtbot.mouse_click(acc_w, QtCore.Qt.LeftButton)
            break

    def _password_widget_shown():
        assert isinstance(login_w.widget.layout().itemAt(0).widget(), LoginPasswordInputWidget)

    await aqtbot.wait_until(_password_widget_shown, timeout=4000)

    password_w = login_w.widget.layout().itemAt(0).widget()
    await aqtbot.key_clicks(password_w.line_edit_password, password)

    tabw = logged_gui.test_get_tab()

    async with aqtbot.wait_signals([login_w.login_with_password_clicked, tabw.logged_in]):
        await aqtbot.mouse_click(password_w.button_login, QtCore.Qt.LeftButton)

    w_w = await logged_gui.test_switch_to_workspaces_widget()

    def _workspace_listed():
        assert w_w.layout_workspaces.count() == 1
        wk_button = w_w.layout_workspaces.itemAt(0).widget()
        assert isinstance(wk_button, WorkspaceButton)
        assert wk_button.name == "Workspace"
        assert not autoclose_dialog.dialogs

    await aqtbot.wait_until(_workspace_listed, timeout=4000)

    w_b = w_w.layout_workspaces.itemAt(0).widget()
    assert isinstance(w_b, WorkspaceButton)
    assert w_b.workspace_name == "Workspace"
    assert w_b.is_owner is False

    await aqtbot.mouse_click(w_b.button_share, QtCore.Qt.LeftButton)
    share_w_w = await catch_share_workspace_widget()

    def _users_listed():
        assert share_w_w.scroll_content.layout().count() == 4

    await aqtbot.wait_until(_users_listed)

    user_w = share_w_w.scroll_content.layout().itemAt(0).widget()
    assert user_w.combo_role.currentIndex() == 4
    assert user_w.isEnabled() is False

    user_w = share_w_w.scroll_content.layout().itemAt(1).widget()
    assert user_w.combo_role.currentIndex() == 3
    assert user_w.isEnabled() is False

    user_w = share_w_w.scroll_content.layout().itemAt(2).widget()
    assert user_w.combo_role.currentIndex() == 0
    assert user_w.isEnabled() is True


@pytest.mark.gui
@pytest.mark.trio
async def test_share_workspace_offline(
    aqtbot, running_backend, gui_workspace_sharing, autoclose_dialog, qt_thread_gateway
):
    logged_gui, w_w, share_w_w = gui_workspace_sharing

    def _users_listed():
        assert share_w_w.scroll_content.layout().count() == 4

    await aqtbot.wait_until(_users_listed)

    user_w = share_w_w.scroll_content.layout().itemAt(1).widget()
    assert user_w.combo_role.currentIndex() == 0

    def _set_manager():
        user_w.combo_role.setCurrentIndex(3)

    with running_backend.offline():
        await qt_thread_gateway.send_action(_set_manager)

    def _error_shown():
        assert len(autoclose_dialog.dialogs) == 1
        assert autoclose_dialog.dialogs[0] == ("Error", translate("TEXT_WORKSPACE_SHARING_OFFLINE"))

    await aqtbot.wait_until(_error_shown)


@pytest.mark.gui
@pytest.mark.trio
async def test_workspace_sharing_filter_users(
    aqtbot, running_backend, gui_workspace_sharing, autoclose_dialog, qt_thread_gateway
):
    logged_gui, w_w, share_w_w = gui_workspace_sharing

    def _users_listed():
        assert share_w_w.scroll_content.layout().count() == 4

    await aqtbot.wait_until(_users_listed)

    def _users_visible():
        visible = 0
        for i in range(share_w_w.scroll_content.layout().count() - 1):
            print(share_w_w.scroll_content.layout().itemAt(i).widget().label_name.text())
            if share_w_w.scroll_content.layout().itemAt(i).widget().isVisible():
                visible += 1
        return visible

    def _reset_input():
        share_w_w.line_edit_filter.setText("")

    assert _users_visible() == 3

    await aqtbot.key_clicks(share_w_w.line_edit_filter, "face")
    assert _users_visible() == 3
    await qt_thread_gateway.send_action(_reset_input)

    await aqtbot.key_clicks(share_w_w.line_edit_filter, "mca")
    assert _users_visible() == 2
    await qt_thread_gateway.send_action(_reset_input)

    await aqtbot.key_clicks(share_w_w.line_edit_filter, "bob")
    assert _users_visible() == 1
    await qt_thread_gateway.send_action(_reset_input)

    await aqtbot.key_clicks(share_w_w.line_edit_filter, "zoidberg")
    assert _users_visible() == 0


@customize_fixtures(logged_gui_as_admin=True)
@pytest.mark.gui
@pytest.mark.trio
async def test_rename_workspace_when_revoked(
    aqtbot, running_backend, logged_gui, autoclose_dialog, qt_thread_gateway, bob, monkeypatch
):
    w_w = await logged_gui.test_switch_to_workspaces_widget()

    client = logged_gui.test_get_tab().client
    wid = await client.user_fs.workspace_create("Workspace")

    def _workspace_not_shared_listed():
        assert w_w.layout_workspaces.count() == 1
        wk_button = w_w.layout_workspaces.itemAt(0).widget()
        assert isinstance(wk_button, WorkspaceButton)
        assert wk_button.label_title.text() == "Workspace (private)"
        assert wk_button.label_title.toolTip() == "Workspace (private)"
        assert not wk_button.is_shared
        wk_button.name == "Workspace"

    await aqtbot.wait_until(_workspace_not_shared_listed, timeout=4000)

    wid = w_w.layout_workspaces.itemAt(0).widget().workspace_fs.workspace_id
    await client.user_fs.workspace_share(wid, bob.user_id, WorkspaceRole.MANAGER)

    w_w = await logged_gui.test_switch_to_workspaces_widget()

    def _workspace_shared_listed():
        assert w_w.layout_workspaces.count() == 1
        wk_button = w_w.layout_workspaces.itemAt(0).widget()
        assert isinstance(wk_button, WorkspaceButton)
        assert wk_button.is_shared
        assert wk_button.name == "Workspace"
        assert wk_button.label_title.toolTip() == "Workspace (shared with Boby McBobFace)"
        assert wk_button.label_title.text() == "Workspace (shared wi..."

    await aqtbot.wait_until(_workspace_shared_listed, timeout=4000)

    await client.revoke_user(bob.user_id)

    await logged_gui.test_switch_to_users_widget()
    w_w = await logged_gui.test_switch_to_workspaces_widget()

    await aqtbot.wait_until(_workspace_not_shared_listed, timeout=4000)
