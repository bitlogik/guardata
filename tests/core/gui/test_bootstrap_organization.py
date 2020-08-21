# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest
from PyQt5 import QtCore

from guardata.api.protocol import OrganizationID
from guardata.client.types import BackendOrganizationBootstrapAddr
from guardata.client.invite.exceptions import InviteNotFoundError, InviteAlreadyUsedError
from guardata.client.gui.bootstrap_organization_widget import BootstrapOrganizationWidget


@pytest.fixture
def catch_bootstrap_organization_widget(widget_catcher_factory):
    return widget_catcher_factory(
        "guardata.client.gui.bootstrap_organization_widget.BootstrapOrganizationWidget"
    )


@pytest.fixture
async def organization_bootstrap_addr(running_backend):
    org_id = OrganizationID("NewOrg")
    org_token = "123456"
    await running_backend.backend.organization.create(org_id, org_token)
    return BackendOrganizationBootstrapAddr.build(running_backend.addr, org_id, org_token)


@pytest.fixture
async def gui_ready_for_bootstrap(
    aqtbot, gui_factory, organization_bootstrap_addr, catch_bootstrap_organization_widget
):
    gui = await gui_factory(start_arg=organization_bootstrap_addr.to_url())

    bo_w = await catch_bootstrap_organization_widget()
    assert isinstance(bo_w, BootstrapOrganizationWidget)

    def _bootstrap_org_displayed():
        tab = gui.test_get_tab()
        assert tab and tab.isVisible()
        assert bo_w.isVisible()
        assert bo_w.dialog.label_title.text() == "Bootstrap the organization"

    await aqtbot.wait_until(_bootstrap_org_displayed)
    return gui, bo_w


async def proceed_to_bootstrap(aqtbot, bo_w):
    await aqtbot.key_clicks(bo_w.line_edit_login, "Zack")
    await aqtbot.key_clicks(bo_w.line_edit_email, "zack@host.com")
    await aqtbot.key_clicks(bo_w.line_edit_device, "pc1")
    await aqtbot.key_clicks(bo_w.line_edit_password, "S4cr3t!P@ss")
    await aqtbot.key_clicks(bo_w.line_edit_password_check, "S4cr3t!P@ss")
    await aqtbot.wait(100)
    await aqtbot.mouse_click(bo_w.button_bootstrap, QtCore.Qt.LeftButton)


@pytest.mark.gui
@pytest.mark.trio
async def test_bootstrap_organization(aqtbot, backend, gui_ready_for_bootstrap, autoclose_dialog):
    gui, bo_w = gui_ready_for_bootstrap
    await proceed_to_bootstrap(aqtbot, bo_w)

    def _bootstrap_done():
        assert not bo_w.isVisible()
        # Should be logged in with the new device
        central_widget = gui.test_get_central_widget()
        assert central_widget and central_widget.isVisible()
        assert autoclose_dialog.dialogs == [
            (
                "",
                "Your organization <b>NewOrg</b> has been created!<br />\n<br />\n"
                "You will now be automatically logged in.<br />\n<br />\n",
            )
        ]

    await aqtbot.wait_until(_bootstrap_done)

    # Also make sure the backend has received a device/user with human_handle and device_label
    device = gui.test_get_core().device
    remote_user, remote_device = await backend.user.get_user_with_device(
        organization_id=device.organization_id, device_id=device.device_id
    )
    assert remote_user.human_handle.email == device.human_handle.email
    assert remote_user.human_handle.label == device.human_handle.label
    assert remote_device.device_label == device.device_label


@pytest.mark.gui
@pytest.mark.trio
async def test_bootstrap_org_missing_fields(aqtbot, gui_ready_for_bootstrap, autoclose_dialog):
    gui, bo_w = gui_ready_for_bootstrap

    assert bo_w.button_bootstrap.isEnabled() is False

    await aqtbot.key_clicks(bo_w.line_edit_login, "login")
    assert bo_w.button_bootstrap.isEnabled() is False

    await aqtbot.key_clicks(bo_w.line_edit_device, "device")
    assert bo_w.button_bootstrap.isEnabled() is False

    await aqtbot.key_clicks(bo_w.line_edit_email, "user@host.com")
    assert bo_w.button_bootstrap.isEnabled() is False

    await aqtbot.key_clicks(bo_w.line_edit_password, "passwor")
    assert bo_w.button_bootstrap.isEnabled() is False

    await aqtbot.key_clicks(bo_w.line_edit_password, "d")
    assert bo_w.button_bootstrap.isEnabled() is False

    await aqtbot.key_clicks(bo_w.line_edit_password_check, "pass4wor11!d")
    await aqtbot.wait(250)
    assert bo_w.button_bootstrap.isEnabled() is False

    await aqtbot.key_click(bo_w.line_edit_password, QtCore.Qt.Key_Backspace)
    assert bo_w.button_bootstrap.isEnabled() is False


@pytest.mark.gui
@pytest.mark.trio
async def test_bootstrap_organization_backend_offline(
    aqtbot, running_backend, gui_ready_for_bootstrap, autoclose_dialog
):
    gui, bo_w = gui_ready_for_bootstrap

    with running_backend.offline():
        await proceed_to_bootstrap(aqtbot, bo_w)

        def _bootstrap_done():
            # No logged in should have occured, should go back to login page
            assert not bo_w.isVisible()
            l_w = gui.test_get_login_widget()
            assert l_w.isVisible()
            assert autoclose_dialog.dialogs == [
                ("Error", "The server is offline or you have no access to the internet.")
            ]

        await aqtbot.wait_until(_bootstrap_done)


@pytest.mark.gui
@pytest.mark.trio
async def test_bootstrap_organization_invite_already_used(
    aqtbot, gui_ready_for_bootstrap, autoclose_dialog, monkeypatch
):
    gui, bo_w = gui_ready_for_bootstrap

    def _raise_already_used(*args, **kwargs):
        raise InviteAlreadyUsedError()

    monkeypatch.setattr(
        "guardata.client.gui.bootstrap_organization_widget.bootstrap_organization",
        _raise_already_used,
    )

    await proceed_to_bootstrap(aqtbot, bo_w)

    def _bootstrap_done():
        # No logged in should have occured, should go back to login page
        assert not bo_w.isVisible()
        l_w = gui.test_get_login_widget()
        assert l_w.isVisible()
        assert autoclose_dialog.dialogs == [
            ("Error", "This organization has already been bootstrapped.")
        ]

    await aqtbot.wait_until(_bootstrap_done)


@pytest.mark.gui
@pytest.mark.trio
async def test_bootstrap_organization_invite_not_found(
    aqtbot, gui_ready_for_bootstrap, autoclose_dialog, monkeypatch
):
    gui, bo_w = gui_ready_for_bootstrap

    def _raise_already_used(*args, **kwargs):
        raise InviteNotFoundError()

    monkeypatch.setattr(
        "guardata.client.gui.bootstrap_organization_widget.bootstrap_organization",
        _raise_already_used,
    )

    await proceed_to_bootstrap(aqtbot, bo_w)

    def _bootstrap_done():
        # No logged in should have occured, should go back to login page
        assert not bo_w.isVisible()
        l_w = gui.test_get_login_widget()
        assert l_w.isVisible()
        assert autoclose_dialog.dialogs == [
            ("Error", "There are no organization to bootstrap with this link.")
        ]

    await aqtbot.wait_until(_bootstrap_done)


@pytest.mark.gui
@pytest.mark.trio
async def test_bootstrap_organization_unknown_error(
    aqtbot, gui_ready_for_bootstrap, autoclose_dialog, monkeypatch
):
    gui, bo_w = gui_ready_for_bootstrap

    def _raise_already_used(*args, **kwargs):
        raise RuntimeError()

    monkeypatch.setattr(
        "guardata.client.gui.bootstrap_organization_widget.bootstrap_organization",
        _raise_already_used,
    )

    await proceed_to_bootstrap(aqtbot, bo_w)

    def _bootstrap_done():
        # No logged in should have occured, should go back to login page
        assert not bo_w.isVisible()
        l_w = gui.test_get_login_widget()
        assert l_w.isVisible()
        assert autoclose_dialog.dialogs == [("Error", "Could not bootstrap the organization.")]

    await aqtbot.wait_until(_bootstrap_done)


@pytest.mark.gui
@pytest.mark.trio
async def test_bootstrap_organization_with_bad_start_arg(aqtbot, gui_factory, autoclose_dialog):
    bad_start_arg = "parsec://example.com:9999/NewOrg?action=dummy&token=123456&no_ssl=true"

    gui = await gui_factory(start_arg=bad_start_arg)

    def _bootstrap_aborted():
        # Should go back to login page
        l_w = gui.test_get_login_widget()
        assert l_w.isVisible()
        assert autoclose_dialog.dialogs == [("Error", "The link is invalid.")]

    await aqtbot.wait_until(_bootstrap_aborted)
