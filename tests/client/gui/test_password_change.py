# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest
from PyQt5 import QtCore
from guardata.client.gui.login_widget import LoginPasswordInputWidget


@pytest.fixture
def catch_password_change_widget(widget_catcher_factory):
    return widget_catcher_factory("guardata.client.gui.password_change_widget.PasswordChangeWidget")


@pytest.mark.gui
@pytest.mark.trio
async def test_change_password_invalid_old_password(
    aqtbot,
    running_backend,
    logged_gui,
    catch_password_change_widget,
    autoclose_dialog,
    qt_thread_gateway,
):
    c_w = logged_gui.test_get_central_widget()

    assert c_w is not None

    def _trigger_password_change():
        c_w.button_user.menu().actions()[0].trigger()

    await qt_thread_gateway.send_action(_trigger_password_change)

    await aqtbot.wait(250)
    pc_w = await catch_password_change_widget()

    await aqtbot.key_clicks(pc_w.line_edit_old_password, "0123456789")
    await aqtbot.key_clicks(pc_w.line_edit_password, "P2ssxdor!s32")
    await aqtbot.key_clicks(pc_w.line_edit_password_check, "P2ssxdor!s32")
    await aqtbot.wait(250)
    await aqtbot.mouse_click(pc_w.button_change, QtCore.Qt.LeftButton)

    assert autoclose_dialog.dialogs[0] == (
        "Error",
        "You did not provide the right password for this device.",
    )


@pytest.mark.gui
@pytest.mark.trio
async def test_change_password_invalid_password_check(
    aqtbot,
    running_backend,
    logged_gui,
    catch_password_change_widget,
    autoclose_dialog,
    qt_thread_gateway,
):
    c_w = logged_gui.test_get_central_widget()

    assert c_w is not None

    def _trigger_password_change():
        c_w.button_user.menu().actions()[0].trigger()

    await qt_thread_gateway.send_action(_trigger_password_change)

    await aqtbot.wait(250)
    pc_w = await catch_password_change_widget()

    await aqtbot.key_clicks(pc_w.line_edit_old_password, "P2ssxdor!s3")
    await aqtbot.key_clicks(pc_w.line_edit_password, "P2ssxdor!s32")
    await aqtbot.key_clicks(pc_w.line_edit_password_check, "P2ssxdor!s33")
    await aqtbot.wait(500)
    assert not pc_w.button_change.isEnabled()


@pytest.mark.gui
@pytest.mark.trio
async def test_change_password_success(
    aqtbot,
    running_backend,
    logged_gui,
    catch_password_change_widget,
    autoclose_dialog,
    qt_thread_gateway,
):
    c_w = logged_gui.test_get_central_widget()

    assert c_w is not None

    def _trigger_password_change():
        c_w.button_user.menu().actions()[0].trigger()

    await qt_thread_gateway.send_action(_trigger_password_change)

    await aqtbot.wait(250)
    pc_w = await catch_password_change_widget()

    await aqtbot.key_clicks(pc_w.line_edit_old_password, "P2ssxdor!s3")
    await aqtbot.key_clicks(pc_w.line_edit_password, "P2ssxdor!s32")
    await aqtbot.key_clicks(pc_w.line_edit_password_check, "P2ssxdor!s32")
    await aqtbot.wait(500)
    assert pc_w.button_change.isEnabled()
    await aqtbot.mouse_click(pc_w.button_change, QtCore.Qt.LeftButton)

    def _wait_confirmation_shown():
        assert len(autoclose_dialog.dialogs) == 1
        assert autoclose_dialog.dialogs[0] == ("", "The password has been successfully changed.")

    await aqtbot.wait_until(_wait_confirmation_shown)
    autoclose_dialog.reset()

    # Retry to login...
    await logged_gui.test_logout_and_switch_to_login_widget()

    # ...with old password...
    await logged_gui.test_proceed_to_login("P2ssxdor!s3", error=True)
    assert autoclose_dialog.dialogs == [("Error", "The password is incorrect.")]

    # ...and new password
    l_w = logged_gui.test_get_login_widget()
    password_w = l_w.widget.layout().itemAt(0).widget()
    assert isinstance(password_w, LoginPasswordInputWidget)

    await aqtbot.key_clicks(password_w.line_edit_password, "P2ssxdor!s32")

    tabw = logged_gui.test_get_tab()

    async with aqtbot.wait_signals([l_w.login_with_password_clicked, tabw.logged_in]):
        await aqtbot.mouse_click(password_w.button_login, QtCore.Qt.LeftButton)

    def _wait_logged_in():
        assert not l_w.isVisible()
        c_w = logged_gui.test_get_central_widget()
        assert c_w.isVisible()

    await aqtbot.wait(200)

    await aqtbot.wait_until(_wait_logged_in)
