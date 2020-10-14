# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest
from PyQt5 import QtCore, QtWidgets
from sys import platform

from guardata.client.local_device import save_device_with_password
from guardata.client.gui.central_widget import CentralWidget
from guardata.client.gui.login_widget import (
    LoginPasswordInputWidget,
    LoginAccountsWidget,
    LoginNoDevicesWidget,
    LoginWidget,
)


@pytest.mark.gui
@pytest.mark.trio
async def test_login(aqtbot, gui_factory, autoclose_dialog, client_config, alice):
    # Create an existing device before starting the gui
    password = "P2ssxdor!s3"
    save_device_with_password(client_config.config_dir, alice, password)

    gui = await gui_factory()
    lw = gui.test_get_login_widget()
    tabw = gui.test_get_tab()

    accounts_w = lw.widget.layout().itemAt(0).widget()
    assert accounts_w

    def _password_widget_shown():
        assert isinstance(lw.widget.layout().itemAt(0).widget(), LoginPasswordInputWidget)

    await aqtbot.wait_until(_password_widget_shown)

    password_w = lw.widget.layout().itemAt(0).widget()

    await aqtbot.key_clicks(password_w.line_edit_password, "P2ssxdor!s3")

    async with aqtbot.wait_signals([lw.login_with_password_clicked, tabw.logged_in]):
        await aqtbot.mouse_click(password_w.button_login, QtCore.Qt.LeftButton)

    central_widget = gui.test_get_central_widget()
    assert central_widget
    with aqtbot.qtbot.waitExposed(central_widget):
        assert (
            central_widget.button_user.text()
            == f"{alice.organization_id}\n{alice.short_user_display}"
        )
        assert (
            gui.tab_center.tabText(0)
            == f"{alice.organization_id} - {alice.short_user_display} - {alice.device_display}"
        )


@pytest.mark.gui
@pytest.mark.trio
async def test_login_back_to_account_list(
    aqtbot, gui_factory, autoclose_dialog, client_config, alice, bob
):
    # Create an existing device before starting the gui
    password = "P2ssxdor!s3"
    save_device_with_password(client_config.config_dir, alice, password)
    save_device_with_password(client_config.config_dir, bob, password)

    gui = await gui_factory()
    lw = gui.test_get_login_widget()

    accounts_w = lw.widget.layout().itemAt(0).widget()
    assert accounts_w

    async with aqtbot.wait_signal(accounts_w.account_clicked):
        await aqtbot.mouse_click(
            accounts_w.accounts_widget.layout().itemAt(0).widget(), QtCore.Qt.LeftButton
        )

    def _password_widget_shown():
        assert isinstance(lw.widget.layout().itemAt(0).widget(), LoginPasswordInputWidget)

    await aqtbot.wait_until(_password_widget_shown)

    password_w = lw.widget.layout().itemAt(0).widget()

    async with aqtbot.wait_signal(password_w.back_clicked):
        await aqtbot.mouse_click(password_w.button_back, QtCore.Qt.LeftButton)

    def _account_widget_shown():
        assert isinstance(lw.widget.layout().itemAt(0).widget(), LoginAccountsWidget)


@pytest.mark.gui
@pytest.mark.trio
async def test_login_no_devices(aqtbot, gui_factory, autoclose_dialog, client_config):
    gui = await gui_factory()
    lw = gui.test_get_login_widget()

    no_device_w = lw.widget.layout().itemAt(0).widget()
    assert isinstance(no_device_w, LoginNoDevicesWidget)


@pytest.mark.gui
@pytest.mark.trio
async def test_login_device_list(aqtbot, gui_factory, autoclose_dialog, client_config, alice, bob):
    password = "P2ssxdor!s3"
    save_device_with_password(client_config.config_dir, alice, password)
    save_device_with_password(client_config.config_dir, bob, password)

    gui = await gui_factory()
    lw = gui.test_get_login_widget()

    accounts_w = lw.widget.layout().itemAt(0).widget()
    assert accounts_w

    assert accounts_w.accounts_widget.layout().count() == 3
    dev1_w = accounts_w.accounts_widget.layout().itemAt(0).widget()
    dev2_w = accounts_w.accounts_widget.layout().itemAt(1).widget()

    case1 = (
        dev1_w.label_name.text() == "Alicey McAliceFace"
        and dev2_w.label_name.text() == "Boby McBobFace"
    )
    case2 = (
        dev2_w.label_name.text() == "Alicey McAliceFace"
        and dev1_w.label_name.text() == "Boby McBobFace"
    )
    assert case1 ^ case2
    assert dev1_w.label_device.text() == "My dev1 machine"
    assert dev1_w.label_organization.text() == "CoolOrg"
    assert dev2_w.label_device.text() == "My dev1 machine"
    assert dev2_w.label_organization.text() == "CoolOrg"


@pytest.mark.skipif(platform == "darwin", reason="Crash on Mac, cant switch_to_main_tab at the end")
@pytest.mark.gui
@pytest.mark.trio
async def test_login_logout_account_list_refresh(
    aqtbot, gui_factory, autoclose_dialog, client_config, alice, bob
):
    # Create two devices before starting the gui
    password = "P2ssxdor!s1"
    save_device_with_password(client_config.config_dir, alice, password)
    save_device_with_password(client_config.config_dir, bob, password)

    gui = await gui_factory()
    lw = gui.test_get_login_widget()
    tabw = gui.test_get_tab()

    acc_w = lw.widget.layout().itemAt(0).widget()
    assert acc_w

    # 3 because we have a spacer
    assert acc_w.accounts_widget.layout().count() == 3

    async with aqtbot.wait_signal(acc_w.account_clicked):
        await aqtbot.mouse_click(
            acc_w.accounts_widget.layout().itemAt(0).widget(), QtCore.Qt.LeftButton
        )

    def _password_widget_shown():
        assert isinstance(lw.widget.layout().itemAt(0).widget(), LoginPasswordInputWidget)

    await aqtbot.wait_until(_password_widget_shown)

    password_w = lw.widget.layout().itemAt(0).widget()

    await aqtbot.key_clicks(password_w.line_edit_password, password)

    async with aqtbot.wait_signals([lw.login_with_password_clicked, tabw.logged_in]):
        await aqtbot.mouse_click(password_w.button_login, QtCore.Qt.LeftButton)

    central_widget = gui.test_get_central_widget()
    assert central_widget is not None
    corner_widget = gui.tab_center.cornerWidget(QtCore.Qt.TopLeftCorner)
    assert isinstance(corner_widget, QtWidgets.QPushButton)
    assert corner_widget.isVisible()

    # Now add a new tab
    await aqtbot.mouse_click(corner_widget, QtCore.Qt.LeftButton)

    def _switch_to_login_tab():
        assert gui.tab_center.count() == 2
        gui.tab_center.setCurrentIndex(1)
        assert isinstance(gui.test_get_login_widget(), LoginWidget)

    await aqtbot.wait_until(_switch_to_login_tab)

    acc_w = gui.test_get_login_widget().widget.layout().itemAt(0).widget()
    assert isinstance(acc_w, LoginPasswordInputWidget)
    assert not acc_w.button_back.isVisible()

    def _switch_to_main_tab():
        gui.tab_center.setCurrentIndex(0)
        assert isinstance(gui.test_get_central_widget(), CentralWidget)

    await aqtbot.wait(200)

    await aqtbot.wait_until(_switch_to_main_tab)
    await gui.test_logout()

    assert gui.tab_center.count() == 1

    def _wait_devices_refreshed():
        acc_w = gui.test_get_login_widget().widget.layout().itemAt(0).widget()
        assert acc_w.accounts_widget.layout().count() == 3

    await aqtbot.wait_until(_wait_devices_refreshed)
