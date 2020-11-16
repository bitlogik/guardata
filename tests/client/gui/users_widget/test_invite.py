# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest

# from unittest.mock import ANY
from PyQt5 import QtCore, QtWidgets

# from guardata.client.gui.users_widget import UserInvitationButton
from guardata.client.gui.lang import translate as _

from tests.common import customize_fixtures


@pytest.mark.gui
@pytest.mark.trio
@pytest.mark.parametrize("online", (True, False))
@customize_fixtures(backend_has_email=True, logged_gui_as_admin=True)
async def test_invite_user(
    aqtbot,
    logged_gui,
    bob,
    running_backend,
    monkeypatch,
    autoclose_dialog,
    email_letterbox,
    online,
    input_patcher,
):
    u_w = await logged_gui.test_switch_to_users_widget()

    assert u_w.layout_users.count() == 3

    input_patcher.patch_text_input(
        "guardata.client.gui.users_widget.get_text_input",
        QtWidgets.QDialog.Accepted,
        "hubert.farnsworth@pe.com",
    )

    with running_backend.offline():
        await aqtbot.mouse_click(u_w.button_add_user, QtCore.Qt.LeftButton)

        def _email_send_failed():
            assert autoclose_dialog.dialogs == [
                ("Error", "The server is offline or you have no access to the internet.")
            ]

        await aqtbot.wait_until(_email_send_failed)
        assert not email_letterbox.emails


@pytest.mark.gui
@pytest.mark.trio
async def test_invite_user_not_allowed(logged_gui, running_backend):
    u_w = await logged_gui.test_switch_to_users_widget()

    # Just make sure the button is not available
    assert not u_w.button_add_user.isVisible()


@pytest.mark.gui
@pytest.mark.trio
@pytest.mark.parametrize("online", (True, False))
@customize_fixtures(logged_gui_as_admin=True)
async def test_revoke_user(
    aqtbot, running_backend, autoclose_dialog, monkeypatch, logged_gui, online, input_patcher
):
    u_w = await logged_gui.test_switch_to_users_widget()

    assert u_w.layout_users.count() == 3
    bob_w = u_w.layout_users.itemAt(2).widget()
    assert bob_w.label_username.text() == "Boby McBobFace"
    assert bob_w.label_email.text() == "bob@example.com"
    assert bob_w.user_info.is_revoked is False

    input_patcher.patch_question(
        "guardata.client.gui.users_widget.ask_question",
        QtWidgets.QDialog.Accepted,
        _("ACTION_USER_REVOCATION_CONFIRM"),
    )

    if online:
        await aqtbot.run(bob_w.revoke_clicked.emit, bob_w.user_info)

        def _revocation_done():
            assert bob_w.user_info.is_revoked is True
            assert autoclose_dialog.dialogs == [
                (
                    "",
                    "The user <b>Boby McBobFace</b> has been successfully revoked. Do no forget to reencrypt the workspaces that were shared with them.",
                )
            ]

        await aqtbot.wait_until(_revocation_done)

    else:
        with running_backend.offline():
            await aqtbot.run(bob_w.revoke_clicked.emit, bob_w.user_info)

            def _revocation_error():
                assert bob_w.user_info.is_revoked is False
                assert autoclose_dialog.dialogs == [
                    ("Error", "The server is offline or you have no access to the internet.")
                ]

            await aqtbot.wait_until(_revocation_error)


@pytest.mark.gui
@pytest.mark.trio
async def test_revoke_user_not_allowed(
    aqtbot, running_backend, autoclose_dialog, monkeypatch, logged_gui, input_patcher
):
    u_w = await logged_gui.test_switch_to_users_widget()

    assert u_w.layout_users.count() == 3
    alice_w = u_w.layout_users.itemAt(1).widget()
    assert alice_w.label_email.text() == "alice@example.com"
    assert alice_w.user_info.is_revoked is False

    # TODO: we should instead check that the menu giving access to revocation button is hidden...

    input_patcher.patch_question(
        "guardata.client.gui.users_widget.ask_question",
        QtWidgets.QDialog.Accepted,
        _("ACTION_USER_REVOCATION_CONFIRM"),
    )

    await aqtbot.run(alice_w.revoke_clicked.emit, alice_w.user_info)

    def _revocation_error():
        assert alice_w.user_info.is_revoked is False
        assert autoclose_dialog.dialogs == [("Error", "Could not revoke this user.")]

    await aqtbot.wait_until(_revocation_error)


@pytest.mark.gui
@pytest.mark.trio
@customize_fixtures(backend_has_email=True, logged_gui_as_admin=True)
async def test_cancel_user_invitation(
    aqtbot,
    logged_gui,
    running_backend,
    backend,
    autoclose_dialog,
    monkeypatch,
    alice,
    email_letterbox,
    input_patcher,
):

    email = "i@like.coffee"

    # Patch dialogs
    input_patcher.patch_text_input(
        "guardata.client.gui.users_widget.get_text_input", QtWidgets.QDialog.Accepted, email
    )
    input_patcher.patch_question(
        "guardata.client.gui.users_widget.ask_question",
        QtWidgets.QDialog.Accepted,
        _("TEXT_USER_INVITE_CANCEL_INVITE_ACCEPT"),
    )
    u_w = await logged_gui.test_switch_to_users_widget()

    # Invite new user
    await aqtbot.mouse_click(u_w.button_add_user, QtCore.Qt.LeftButton)

    # def _new_invitation_displayed():
    #     assert u_w.layout_users.count() == 4
    #     assert autoclose_dialog.dialogs == [
    #         ("", f"Invitation to join the group was successfuly sent to { email }",)
    #     ]

    # await aqtbot.wait_until(_new_invitation_displayed)
    # autoclose_dialog.reset()
    # user_invitation_w = u_w.layout_users.itemAt(0).widget()
    # assert user_invitation_w.email == email

    # # Cancel invitation
    # await aqtbot.mouse_click(user_invitation_w.button_cancel, QtCore.Qt.LeftButton)

    # def _new_invitation_removed():
    #     assert u_w.layout_users.count() == 3

    # await aqtbot.wait_until(_new_invitation_removed)
    # assert not autoclose_dialog.dialogs
