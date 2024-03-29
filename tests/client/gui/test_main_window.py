# Parsec Cloud (https://guardata.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest
import sys
from pathlib import Path
from PyQt5 import QtCore, QtWidgets

from guardata.client.gui.lang import translate
from guardata.client.types import BackendOrganizationFileLinkAddr
from guardata.client.local_device import (
    AvailableDevice,
    _save_device_with_password,
    save_device_with_password,
)


@pytest.fixture
async def logged_gui_with_files(
    aqtbot, running_backend, backend, autoclose_dialog, logged_gui, bob, monkeypatch, input_patcher
):
    w_w = await logged_gui.test_switch_to_workspaces_widget()

    assert logged_gui.tab_center.count() == 1

    input_patcher.patch_text_input(
        "guardata.client.gui.workspaces_widget.get_text_input", QtWidgets.QDialog.Accepted, "w1"
    )
    input_patcher.patch_text_input(
        "guardata.client.gui.files_widget.get_text_input", QtWidgets.QDialog.Accepted, "dir1"
    )

    await aqtbot.mouse_click(w_w.button_add_workspace, QtCore.Qt.LeftButton)

    def workspace_button_ready():
        assert w_w.layout_workspaces.count() == 1
        wk_button = w_w.layout_workspaces.itemAt(0).widget()
        assert not isinstance(wk_button, QtWidgets.QLabel)

    await aqtbot.wait(500)

    await aqtbot.wait_until(workspace_button_ready, timeout=5000)

    f_w = logged_gui.test_get_files_widget()
    wk_button = w_w.layout_workspaces.itemAt(0).widget()
    async with aqtbot.wait_exposed(f_w), aqtbot.wait_signal(f_w.folder_changed, timeout=15000):
        if sys.platform == "win32":
            wk_button.button_open_gui_clicked()
        else:
            await aqtbot.mouse_click(wk_button, QtCore.Qt.LeftButton)

    def _entry_available():
        assert f_w.workspace_fs.get_workspace_name() == "w1"
        assert f_w.table_files.rowCount() == 1

    await aqtbot.wait(200)

    await aqtbot.wait_until(_entry_available, timeout=2000)

    def folder_ready():
        assert f_w.isVisible()
        assert f_w.table_files.rowCount() == 2
        folder = f_w.table_files.item(1, 1)
        assert folder
        assert folder.text() == "dir1"

    await aqtbot.wait(2000)
    async with aqtbot.wait_signal(f_w.folder_stat_success, timeout=3000):
        await aqtbot.mouse_click(f_w.button_create_folder, QtCore.Qt.LeftButton)

    await aqtbot.wait(200)

    await aqtbot.wait_until(folder_ready, timeout=2000)

    d_w = await logged_gui.test_switch_to_devices_widget()

    def device_widget_ready():
        assert d_w.isVisible()

    await aqtbot.wait(200)

    await aqtbot.wait_until(device_widget_ready, timeout=2000)

    return logged_gui, w_w, f_w


@pytest.fixture
def bob_available_device(bob, tmpdir):
    key_file_path = Path(tmpdir) / "bob_device.key"
    _save_device_with_password(key_file=key_file_path, device=bob, password="")
    return AvailableDevice(
        key_file_path=key_file_path,
        organization_id=bob.organization_id,
        device_id=bob.device_id,
        human_handle=bob.human_handle,
        device_label=bob.device_label,
        root_verify_key_hash=bob.root_verify_key_hash,
    )


@pytest.fixture
@pytest.mark.skipif(sys.platform == "darwin", reason="Test not reliable on Mac")
@pytest.mark.gui
@pytest.mark.trio
async def test_file_link(
    aqtbot, running_backend, backend, autoclose_dialog, logged_gui_with_files, bob, monkeypatch
):
    logged_gui, w_w, f_w = logged_gui_with_files
    url = BackendOrganizationFileLinkAddr.build(
        f_w.client.device.organization_addr, f_w.workspace_fs.workspace_id, f_w.current_directory
    )

    class AvailableDevice:
        def __init__(self, org_id):
            self.organization_id = org_id

    device = AvailableDevice(bob.organization_id)
    monkeypatch.setattr(
        "guardata.client.gui.main_window.list_available_devices", lambda *args, **kwargs: [device]
    )

    await aqtbot.run(logged_gui.add_instance, str(url))

    def folder_ready():
        assert f_w.isVisible()
        assert f_w.table_files.rowCount() == 2
        folder = f_w.table_files.item(1, 1)
        assert folder
        assert folder.text() == "dir1"

    await aqtbot.wait(200)

    await aqtbot.wait_until(folder_ready, timeout=3000)

    assert logged_gui.tab_center.count() == 1


@pytest.mark.gui
@pytest.mark.skipif(sys.platform == "darwin", reason="Test not reliable on Mac")
@pytest.mark.trio
async def test_link_file_unmounted(
    aqtbot,
    running_backend,
    backend,
    autoclose_dialog,
    logged_gui_with_files,
    bob,
    monkeypatch,
    bob_available_device,
):
    logged_gui, w_w, f_w = logged_gui_with_files

    client = logged_gui.test_get_client()
    url = BackendOrganizationFileLinkAddr.build(
        f_w.client.device.organization_addr, f_w.workspace_fs.workspace_id, f_w.current_directory
    )

    monkeypatch.setattr(
        "guardata.client.gui.main_window.list_available_devices",
        lambda *args, **kwargs: [bob_available_device],
    )

    await aqtbot.run(logged_gui.add_instance, str(url))

    def _folder_ready():
        assert f_w.isVisible()
        assert f_w.table_files.rowCount() == 2
        folder = f_w.table_files.item(1, 1)
        assert folder
        assert folder.text() == "dir1"

    await aqtbot.wait_until(_folder_ready)

    assert logged_gui.tab_center.count() == 1

    def _mounted():
        assert client.mountpoint_manager.is_workspace_mounted(f_w.workspace_fs.workspace_id)

    await aqtbot.wait_until(_mounted)
    await client.mountpoint_manager.unmount_workspace(f_w.workspace_fs.workspace_id)

    def _unmounted():
        assert not client.mountpoint_manager.is_workspace_mounted(f_w.workspace_fs.workspace_id)

    await aqtbot.wait_until(_unmounted)

    await aqtbot.run(logged_gui.add_instance, str(url))

    await aqtbot.wait_until(_mounted)


@pytest.mark.skipif(sys.platform == "darwin", reason="Test not reliable on Mac")
@pytest.mark.gui
@pytest.mark.trio
async def test_file_link_invalid_path(
    aqtbot, running_backend, backend, autoclose_dialog, logged_gui_with_files, bob, monkeypatch
):
    logged_gui, w_w, f_w = logged_gui_with_files
    url = BackendOrganizationFileLinkAddr.build(
        f_w.client.device.organization_addr, f_w.workspace_fs.workspace_id, "/not_a_valid_path"
    )

    class AvailableDevice:
        def __init__(self, org_id):
            self.organization_id = org_id

    device = AvailableDevice(bob.organization_id)
    monkeypatch.setattr(
        "guardata.client.gui.main_window.list_available_devices", lambda *args, **kwargs: [device]
    )

    await aqtbot.run(logged_gui.add_instance, str(url))

    def assert_dialogs():
        assert len(autoclose_dialog.dialogs) == 1
        assert autoclose_dialog.dialogs == [("Error", translate("TEXT_FILE_GOTO_LINK_NOT_FOUND"))]

    await aqtbot.wait(200)

    await aqtbot.wait_until(assert_dialogs, timeout=3000)

    assert logged_gui.tab_center.count() == 1


@pytest.mark.skipif(sys.platform == "darwin", reason="Test not reliable on Mac")
@pytest.mark.gui
@pytest.mark.trio
async def test_file_link_invalid_workspace(
    aqtbot, running_backend, backend, autoclose_dialog, logged_gui_with_files, bob, monkeypatch
):
    logged_gui, w_w, f_w = logged_gui_with_files
    url = BackendOrganizationFileLinkAddr.build(
        f_w.client.device.organization_addr, "not_a_workspace", "/dir1"
    )

    class AvailableDevice:
        def __init__(self, org_id):
            self.organization_id = org_id

    device = AvailableDevice(bob.organization_id)
    monkeypatch.setattr(
        "guardata.client.gui.main_window.list_available_devices", lambda *args, **kwargs: [device]
    )

    await aqtbot.run(logged_gui.add_instance, str(url))

    def assert_dialogs():
        assert len(autoclose_dialog.dialogs) == 1
        assert autoclose_dialog.dialogs == [("Error", translate("TEXT_INVALID_URL"))]

    await aqtbot.wait(200)

    await aqtbot.wait_until(assert_dialogs, timeout=3000)


@pytest.mark.gui
@pytest.mark.trio
async def test_tab_login_logout(
    aqtbot, running_backend, gui_factory, autoclose_dialog, client_config, alice
):
    password = "P2ssxdor!s3"
    save_device_with_password(client_config.config_dir, alice, password)
    gui = await gui_factory()

    assert gui.tab_center.count() == 1
    assert gui.tab_center.tabText(0) == translate("TEXT_TAB_TITLE_LOG_IN_SCREEN")
    assert not gui.add_tab_button.isEnabled()
    first_created_tab = gui.test_get_tab()

    await gui.test_switch_to_logged_in(alice)
    assert gui.tab_center.count() == 1
    assert gui.tab_center.tabText(0) == "CoolOrg - Alicey McAliceFace - My dev1 machine"
    assert gui.add_tab_button.isEnabled()
    assert gui.test_get_tab() == first_created_tab

    await gui.test_logout()
    assert gui.tab_center.count() == 1
    assert gui.tab_center.tabText(0) == translate("TEXT_TAB_TITLE_LOG_IN_SCREEN")
    assert not gui.add_tab_button.isEnabled()
    assert gui.test_get_tab() != first_created_tab


@pytest.mark.gui
@pytest.mark.trio
async def test_tab_login_logout_two_tabs(
    aqtbot, running_backend, gui_factory, autoclose_dialog, client_config, alice
):
    password = "P2ssxdor!s3"
    save_device_with_password(client_config.config_dir, alice, password)
    gui = await gui_factory()

    assert gui.tab_center.count() == 1
    assert gui.tab_center.tabText(0) == translate("TEXT_TAB_TITLE_LOG_IN_SCREEN")
    first_created_tab = gui.test_get_tab()

    await gui.test_switch_to_logged_in(alice)
    assert gui.tab_center.count() == 1
    assert gui.tab_center.tabText(0) == "CoolOrg - Alicey McAliceFace - My dev1 machine"
    logged_tab = gui.test_get_tab()

    await aqtbot.mouse_click(gui.add_tab_button, QtCore.Qt.LeftButton)
    assert gui.tab_center.count() == 2
    assert gui.tab_center.tabText(0) == "CoolOrg - Alicey McAliceFace - My dev1 machine"
    assert gui.tab_center.tabText(1) == translate("TEXT_TAB_TITLE_LOG_IN_SCREEN")

    gui.switch_to_tab(0)

    def _logged_tab_displayed():
        assert logged_tab == gui.test_get_tab()

    await aqtbot.wait(200)

    await aqtbot.wait_until(_logged_tab_displayed)
    await gui.test_logout()
    assert gui.tab_center.count() == 1
    assert gui.tab_center.tabText(0) == translate("TEXT_TAB_TITLE_LOG_IN_SCREEN")
    assert gui.test_get_tab() != first_created_tab


@pytest.mark.gui
@pytest.mark.trio
async def test_tab_login_logout_two_tabs_logged_in(
    aqtbot, running_backend, gui_factory, autoclose_dialog, client_config, alice, bob
):
    password = "P2ssxdor!s3"
    save_device_with_password(client_config.config_dir, alice, password)
    gui = await gui_factory()

    assert gui.tab_center.count() == 1
    assert gui.tab_center.tabText(0) == translate("TEXT_TAB_TITLE_LOG_IN_SCREEN")

    await gui.test_switch_to_logged_in(alice)
    assert gui.tab_center.count() == 1
    assert gui.tab_center.tabText(0) == "CoolOrg - Alicey McAliceFace - My dev1 machine"
    alice_logged_tab = gui.test_get_tab()

    await aqtbot.mouse_click(gui.add_tab_button, QtCore.Qt.LeftButton)
    assert gui.tab_center.count() == 2
    assert gui.tab_center.tabText(0) == "CoolOrg - Alicey McAliceFace - My dev1 machine"
    assert gui.tab_center.tabText(1) == translate("TEXT_TAB_TITLE_LOG_IN_SCREEN")

    save_device_with_password(client_config.config_dir, bob, password)
    await gui.test_switch_to_logged_in(bob)
    assert gui.tab_center.count() == 2
    assert gui.tab_center.tabText(0) == "CoolOrg - Alicey McAliceFace - My dev1 machine"
    assert gui.tab_center.tabText(1) == "CoolOrg - Boby McBobFace - My dev1 machine"
    bob_logged_tab = gui.test_get_tab()
    assert bob_logged_tab != alice_logged_tab

    gui.switch_to_tab(0)

    def _logged_tab_displayed():
        assert alice_logged_tab == gui.test_get_tab()

    await aqtbot.wait(200)

    await aqtbot.wait_until(_logged_tab_displayed)

    await gui.test_logout()
    assert gui.tab_center.count() == 2
    assert gui.tab_center.tabText(0) == "CoolOrg - Boby McBobFace - My dev1 machine"
    assert gui.tab_center.tabText(1) == translate("TEXT_TAB_TITLE_LOG_IN_SCREEN")
