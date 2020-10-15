# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from guardata.client.client_events import ClientEvent
import pytest
import trio
from unittest.mock import ANY
from pendulum import datetime, now as pendulum_now

from tests.common import create_shared_workspace, freeze_time

from guardata.api.data import PingMessageContent
from guardata.client.types import WorkspaceEntry, WorkspaceRole
from guardata.client.backend_connection import BackendConnStatus


@pytest.mark.trio
async def test_monitors_idle(running_backend, alice_client):
    assert alice_client.are_monitors_idle()

    # Force wakeup of the message monitor
    alice_client.event_bus.send(ClientEvent.BACKEND_MESSAGE_RECEIVED, index=42)
    assert not alice_client.are_monitors_idle()
    await alice_client.wait_idle_monitors()
    assert alice_client.are_monitors_idle()


async def _send_msg(backend, author, recipient, ping="ping"):
    now = pendulum_now()
    message = PingMessageContent(author=author.device_id, timestamp=now, ping=ping)
    ciphered_message = message.dump_sign_and_encrypt_for(
        author_signkey=author.signing_key, recipient_pubkey=recipient.public_key
    )
    await backend.message.send(
        organization_id=recipient.organization_id,
        sender=author.device_id,
        recipient=recipient.user_id,
        timestamp=now,
        body=ciphered_message,
    )


@pytest.mark.trio
async def test_process_while_offline(
    autojump_clock, running_backend, alice_client, bob_user_fs, alice, bob
):
    assert alice_client.backend_status == BackendConnStatus.READY

    with running_backend.offline():
        with alice_client.event_bus.listen() as spy:
            # Force wakeup of the message monitor
            alice_client.event_bus.send(ClientEvent.BACKEND_MESSAGE_RECEIVED, index=42)
            assert not alice_client.are_monitors_idle()

            with trio.fail_after(60):  # autojump, so not *really* 60s
                await spy.wait(
                    ClientEvent.BACKEND_CONNECTION_CHANGED,
                    {"status": BackendConnStatus.LOST, "status_exc": spy.ANY},
                )
                await alice_client.wait_idle_monitors()
            assert alice_client.backend_status == BackendConnStatus.LOST

        # Send message while alice is offline
        await _send_msg(
            backend=running_backend.backend, author=bob, recipient=alice, ping="hello from Bob !"
        )

    with alice_client.event_bus.listen() as spy:
        # Alice is back online, should retrieve Bob's message fine
        with trio.fail_after(60):  # autojump, so not *really* 60s
            await spy.wait(
                ClientEvent.BACKEND_CONNECTION_CHANGED,
                {"status": BackendConnStatus.READY, "status_exc": None},
            )
            await alice_client.wait_idle_monitors()
        assert alice_client.backend_status == BackendConnStatus.READY
        spy.assert_event_occured(ClientEvent.MESSAGE_PINGED, {"ping": "hello from Bob !"})


@pytest.mark.trio
async def test_new_sharing_trigger_event(alice_client, bob_client, running_backend):
    # First, create a folder and sync it on backend
    with freeze_time("2000-01-01"):
        wid = await alice_client.user_fs.workspace_create("foo")
    workspace = alice_client.user_fs.get_workspace(wid)
    with freeze_time("2000-01-02"):
        await workspace.sync()

    # Now we can share this workspace with Bob
    with bob_client.event_bus.listen() as spy:
        with freeze_time("2000-01-03"):
            await alice_client.user_fs.workspace_share(
                wid, recipient="bob", role=WorkspaceRole.MANAGER
            )

        # Bob should get a notification
        await spy.wait_with_timeout(
            ClientEvent.SHARING_UPDATED,
            {
                "new_entry": WorkspaceEntry(
                    name="foo",
                    id=wid,
                    key=ANY,
                    encryption_revision=1,
                    encrypted_on=datetime(2000, 1, 1),
                    role_cached_on=ANY,
                    role=WorkspaceRole.MANAGER,
                ),
                "previous_entry": None,
            },
            timeout=3,
        )


@pytest.mark.trio
async def test_revoke_sharing_trigger_event(alice_client, bob_client, running_backend):
    with freeze_time("2000-01-02"):
        wid = await create_shared_workspace("w", alice_client, bob_client)

    with bob_client.event_bus.listen() as spy:
        with freeze_time("2000-01-03"):
            await alice_client.user_fs.workspace_share(wid, recipient="bob", role=None)

        # Each workspace participant should get the message
        await spy.wait_with_timeout(
            ClientEvent.SHARING_UPDATED,
            {
                "new_entry": WorkspaceEntry(
                    name="w",
                    id=wid,
                    key=ANY,
                    encryption_revision=1,
                    encrypted_on=datetime(2000, 1, 2),
                    role_cached_on=ANY,
                    role=None,
                ),
                "previous_entry": WorkspaceEntry(
                    name="w",
                    id=wid,
                    key=ANY,
                    encryption_revision=1,
                    encrypted_on=datetime(2000, 1, 2),
                    role_cached_on=ANY,
                    role=WorkspaceRole.MANAGER,
                ),
            },
            timeout=3,
        )


@pytest.mark.trio
async def test_new_reencryption_trigger_event(alice_client, bob_client, running_backend):
    with freeze_time("2000-01-02"):
        wid = await create_shared_workspace("w", alice_client, bob_client)

    with alice_client.event_bus.listen() as aspy, bob_client.event_bus.listen() as bspy:
        with freeze_time("2000-01-03"):
            await alice_client.user_fs.workspace_start_reencryption(wid)

        # Each workspace participant should get the message
        await aspy.wait_with_timeout(
            ClientEvent.SHARING_UPDATED,
            {
                "new_entry": WorkspaceEntry(
                    name="w",
                    id=wid,
                    key=ANY,
                    encryption_revision=2,
                    encrypted_on=datetime(2000, 1, 3),
                    role_cached_on=ANY,
                    role=WorkspaceRole.OWNER,
                ),
                "previous_entry": WorkspaceEntry(
                    name="w",
                    id=wid,
                    key=ANY,
                    encryption_revision=1,
                    encrypted_on=datetime(2000, 1, 2),
                    role_cached_on=ANY,
                    role=WorkspaceRole.OWNER,
                ),
            },
            timeout=3,
        )
        await bspy.wait_with_timeout(
            ClientEvent.SHARING_UPDATED,
            {
                "new_entry": WorkspaceEntry(
                    name="w",
                    id=wid,
                    key=ANY,
                    encryption_revision=2,
                    encrypted_on=datetime(2000, 1, 3),
                    role_cached_on=ANY,
                    role=WorkspaceRole.MANAGER,
                ),
                "previous_entry": WorkspaceEntry(
                    name="w",
                    id=wid,
                    key=ANY,
                    encryption_revision=1,
                    encrypted_on=datetime(2000, 1, 2),
                    role_cached_on=ANY,
                    role=WorkspaceRole.MANAGER,
                ),
            },
            timeout=3,
        )
