# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import re
import trio
import pytest
from unittest.mock import ANY

from guardata.client.backend_connection import BackendConnStatus
from backendService.backend_events import BackendEvent
from guardata.client.client_events import ClientEvent
from guardata.client.types import WorkspaceRole
from guardata.client.fs.exceptions import FSReadOnlyError

from tests.common import create_shared_workspace


@pytest.mark.trio
async def test_monitors_idle(autojump_clock, running_backend, alice_client, alice):
    assert alice_client.are_monitors_idle()

    # Force wakeup of the sync monitor
    alice_client.event_bus.send(ClientEvent.FS_ENTRY_UPDATED, id=alice.user_manifest_id)
    assert not alice_client.are_monitors_idle()
    with trio.fail_after(60):  # autojump, so not *really* 60s
        await alice_client.wait_idle_monitors()
    assert alice_client.are_monitors_idle()


@pytest.mark.trio
async def test_monitor_switch_offline(autojump_clock, running_backend, alice_client, alice):
    assert alice_client.are_monitors_idle()
    assert alice_client.backend_status == BackendConnStatus.READY

    with alice_client.event_bus.listen() as spy:
        with running_backend.offline():
            await spy.wait_with_timeout(
                ClientEvent.BACKEND_CONNECTION_CHANGED,
                {"status": BackendConnStatus.LOST, "status_exc": spy.ANY},
                timeout=60,  # autojump, so not *really* 60s
            )
            await alice_client.wait_idle_monitors()
            assert alice_client.backend_status == BackendConnStatus.LOST

        # Switch backend online

        await spy.wait_with_timeout(
            ClientEvent.BACKEND_CONNECTION_CHANGED,
            {"status": BackendConnStatus.READY, "status_exc": None},
            timeout=60,  # autojump, so not *really* 60s
        )
        await alice_client.wait_idle_monitors()
        assert alice_client.backend_status == BackendConnStatus.READY


@pytest.mark.trio
async def test_process_while_offline(
    autojump_clock, running_backend, alice_client, bob_user_fs, alice, bob
):
    assert alice_client.backend_status == BackendConnStatus.READY

    with running_backend.offline():
        with alice_client.event_bus.listen() as spy:
            # Force wakeup of the sync monitor
            alice_client.event_bus.send(ClientEvent.FS_ENTRY_UPDATED, id=alice.user_manifest_id)
            assert not alice_client.are_monitors_idle()

            with trio.fail_after(60):  # autojump, so not *really* 60s
                await spy.wait(
                    ClientEvent.BACKEND_CONNECTION_CHANGED,
                    {"status": BackendConnStatus.LOST, "status_exc": spy.ANY},
                )
                await alice_client.wait_idle_monitors()
            assert alice_client.backend_status == BackendConnStatus.LOST


@pytest.mark.trio
async def test_autosync_on_modification(
    autojump_clock, running_backend, alice, alice_client, alice2_user_fs
):
    with alice_client.event_bus.listen() as spy:
        wid = await alice_client.user_fs.workspace_create("w")
        workspace = alice_client.user_fs.get_workspace(wid)
        # Wait for the sync monitor to sync the new workspace
        with trio.fail_after(60):  # autojump, so not *really* 60s
            await alice_client.wait_idle_monitors()
        spy.assert_events_occured(
            [
                (ClientEvent.FS_ENTRY_SYNCED, {"id": alice.user_manifest_id}),
                (ClientEvent.FS_ENTRY_SYNCED, {"workspace_id": wid, "id": wid}),
            ],
            in_order=False,
        )

    with alice_client.event_bus.listen() as spy:
        await workspace.mkdir("/foo")
        foo_id = await workspace.path_id("/foo")
        # Wait for the sync monitor to sync the new folder
        with trio.fail_after(60):  # autojump, so not *really* 60s
            await alice_client.wait_idle_monitors()
        spy.assert_events_occured(
            [
                (ClientEvent.FS_ENTRY_SYNCED, {"workspace_id": wid, "id": foo_id}),
                (ClientEvent.FS_ENTRY_SYNCED, {"workspace_id": wid, "id": wid}),
            ],
            in_order=False,
        )

    # Check workspace and folder have been correctly synced
    await alice2_user_fs.sync()
    workspace2 = alice2_user_fs.get_workspace(wid)
    path_info = await workspace.path_info("/foo")
    path_info2 = await workspace2.path_info("/foo")
    assert path_info == path_info2


@pytest.mark.trio
async def test_autosync_on_remote_modifications(
    autojump_clock, running_backend, alice, alice_client, alice2_user_fs
):
    with alice_client.event_bus.listen() as spy:
        wid = await alice2_user_fs.workspace_create("w")
        await alice2_user_fs.sync()

        # Wait for event to come back to alice_client
        await spy.wait_multiple_with_timeout(
            [
                (
                    ClientEvent.BACKEND_REALM_VLOBS_UPDATED,
                    {
                        "realm_id": alice.user_manifest_id,
                        "checkpoint": 2,
                        "src_id": alice.user_manifest_id,
                        "src_version": 2,
                    },
                ),
                (ClientEvent.FS_ENTRY_REMOTE_CHANGED, {"id": alice.user_manifest_id, "path": "/"}),
            ],
            timeout=60,  # autojump, so not *really* 60s
        )
        # Now wait for alice_client's sync
        with trio.fail_after(60):  # autojump, so not *really* 60s
            await alice_client.wait_idle_monitors()
        # Check workspace has been correctly synced
        alice_w = alice_client.user_fs.get_workspace(wid)

        alice2_w = alice2_user_fs.get_workspace(wid)
        await alice2_w.mkdir("/foo")
        foo_id = await alice2_w.path_id("/foo")
        await alice2_w.sync()

        # Wait for event to come back to alice_client
        await spy.wait_multiple_with_timeout(
            [
                (
                    ClientEvent.BACKEND_REALM_VLOBS_UPDATED,
                    {"realm_id": wid, "checkpoint": 2, "src_id": foo_id, "src_version": 1},
                ),
                (
                    ClientEvent.BACKEND_REALM_VLOBS_UPDATED,
                    {"realm_id": wid, "checkpoint": 3, "src_id": wid, "src_version": 2},
                ),
            ],
            timeout=60,  # autojump, so not *really* 60s
        )
        with trio.fail_after(60):  # autojump, so not *really* 60s
            await alice_client.wait_idle_monitors()
        # Check folder has been correctly synced
        path_info = await alice_w.path_info("/foo")
        path_info2 = await alice2_w.path_info("/foo")
        assert path_info == path_info2


@pytest.mark.trio
async def test_reconnect_with_remote_changes(
    autojump_clock, alice2, running_backend, alice_client, alice2_user_fs
):
    wid = await alice_client.user_fs.workspace_create("w")
    alice_w = alice_client.user_fs.get_workspace(wid)
    await alice_w.mkdir("/foo")
    await alice_w.touch("/bar.txt")
    # Wait for sync monitor to do it job
    await alice_client.wait_idle_monitors()

    with running_backend.offline_for(alice_client.device.device_id):
        # Get back modifications from alice
        await alice2_user_fs.sync()
        alice2_w = alice2_user_fs.get_workspace(wid)
        # Modify the workspace while alice is offline
        await alice2_w.mkdir("/foo/spam")
        await alice2_w.write_bytes("/bar.txt", b"v2")

        foo_id = await alice2_w.path_id("/foo")
        spam_id = await alice2_w.path_id("/foo/spam")
        bar_id = await alice2_w.path_id("/bar.txt")

        with running_backend.backend.event_bus.listen() as spy:
            await alice2_w.sync()
            # Alice misses the vlob updated events before being back online
            await spy.wait_multiple_with_timeout(
                [
                    (
                        BackendEvent.REALM_VLOBS_UPDATED,
                        {
                            "organization_id": alice2.organization_id,
                            "author": alice2.device_id,
                            "realm_id": wid,
                            "checkpoint": ANY,
                            "src_id": spam_id,
                            "src_version": 1,
                        },
                    ),
                    (
                        BackendEvent.REALM_VLOBS_UPDATED,
                        {
                            "organization_id": alice2.organization_id,
                            "author": alice2.device_id,
                            "realm_id": wid,
                            "checkpoint": ANY,
                            "src_id": foo_id,
                            "src_version": 2,
                        },
                    ),
                    (
                        BackendEvent.REALM_VLOBS_UPDATED,
                        {
                            "organization_id": alice2.organization_id,
                            "author": alice2.device_id,
                            "realm_id": wid,
                            "checkpoint": ANY,
                            "src_id": bar_id,
                            "src_version": 2,
                        },
                    ),
                ],
                in_order=False,
            )

    with alice_client.event_bus.listen() as spy:
        # Now alice should sync back the changes
        await spy.wait_with_timeout(
            ClientEvent.BACKEND_CONNECTION_CHANGED,
            {"status": BackendConnStatus.READY, "status_exc": spy.ANY},
            timeout=60,  # autojump, so not *really* 60s
        )
        await spy.wait_multiple_with_timeout(
            [
                (ClientEvent.FS_ENTRY_DOWNSYNCED, {"workspace_id": wid, "id": foo_id}),
                (ClientEvent.FS_ENTRY_DOWNSYNCED, {"workspace_id": wid, "id": bar_id}),
            ],
            in_order=False,
            timeout=60,  # autojump, so not *really* 60s
        )


@pytest.mark.trio
async def test_sync_confined_children_after_rename(
    autojump_clock, alice, running_backend, alice_client
):
    # Create a workspace
    wid = await alice_client.user_fs.workspace_create("w")
    alice_w = alice_client.user_fs.get_workspace(wid)

    # Set a filter
    pattern = re.compile(r".*\.tmp$")
    await alice_w.set_and_apply_pattern_filter(pattern)

    # Create a confined path
    await alice_w.mkdir("/test.tmp/a/b/c", parents=True)

    # Wait for sync monitor to be idle
    await alice_client.wait_idle_monitors()

    # Make sure the root is synced
    info = await alice_w.path_info("/")
    assert not info["need_sync"]
    assert not info["confined"]

    # Make sure the rest of the path is confined
    for path in ["/test.tmp", "/test.tmp/a", "/test.tmp/a/b", "/test.tmp/a/b/c"]:
        info = await alice_w.path_info(path)
        assert info["need_sync"]
        assert info["confined"]

    # Rename to another confined path
    await alice_w.rename("/test.tmp", "/test2.tmp")

    # Wait for sync monitor to be idle
    await alice_client.wait_idle_monitors()

    # Make sure the root is synced
    info = await alice_w.path_info("/")
    assert not info["need_sync"]
    assert not info["confined"]

    # Make sure the rest of the path is confined
    for path in ["/test2.tmp", "/test2.tmp/a", "/test2.tmp/a/b", "/test2.tmp/a/b/c"]:
        info = await alice_w.path_info(path)
        assert info["need_sync"]
        assert info["confined"]

    # Rename to non-confined path
    await alice_w.rename("/test2.tmp", "/test2")

    # Wait for sync monitor to be idle
    await alice_client.wait_idle_monitors()

    # Make sure the root is synced
    info = await alice_w.path_info("/")
    assert not info["need_sync"]
    assert not info["confined"]

    # Make sure the rest of the path is confined
    for path in ["/test2", "/test2/a", "/test2/a/b", "/test2/a/b/c"]:
        info = await alice_w.path_info(path)
        assert not info["need_sync"]
        assert not info["confined"]

    # Rename to a confined path
    await alice_w.rename("/test2", "/test3.tmp")

    # Wait for sync monitor to be idle
    await alice_client.wait_idle_monitors()

    # Make sure the root is synced
    info = await alice_w.path_info("/")
    assert not info["need_sync"]
    assert not info["confined"]

    # Make sure the rest of the path is confined
    for path in ["/test3.tmp", "/test3.tmp/a", "/test3.tmp/a/b", "/test3.tmp/a/b/c"]:
        info = await alice_w.path_info(path)
        assert not info["need_sync"]
        assert info["confined"]


@pytest.mark.trio
async def test_sync_monitor_while_changing_roles(
    running_backend, alice_client, bob_client, autojump_clock
):
    # Create a shared workspace
    wid = await create_shared_workspace("w", alice_client, bob_client)
    alice_workspace = alice_client.user_fs.get_workspace(wid)
    bob_workspace = bob_client.user_fs.get_workspace(wid)

    # Alice creates a files, let it sync
    await alice_workspace.write_bytes("/test.txt", b"test")
    await alice_client.wait_idle_monitors()
    await bob_client.wait_idle_monitors()

    # Bob edit the files..
    assert await bob_workspace.read_bytes("/test.txt") == b"test"
    await bob_workspace.write_bytes("/test.txt", b"test2")

    # But gets his role changed to READER
    with bob_client.event_bus.listen() as spy:
        await alice_client.user_fs.workspace_share(
            wid, bob_client.device.user_id, WorkspaceRole.READER
        )
        await spy.wait(ClientEvent.SHARING_UPDATED)
        await bob_client.wait_idle_monitors()

    # The file cannot be synced
    info = await bob_workspace.path_info("/test.txt")
    assert info["need_sync"]

    # And the workspace is now read-only
    with pytest.raises(FSReadOnlyError):
        await bob_workspace.write_bytes("/this-should-fail", b"abc")

    # Alice restores CONTRIBUTOR rights to Bob
    with bob_client.event_bus.listen() as spy:
        await alice_client.user_fs.workspace_share(
            wid, bob_client.device.user_id, WorkspaceRole.CONTRIBUTOR
        )
        await spy.wait(ClientEvent.SHARING_UPDATED)
        await bob_client.wait_idle_monitors()

    # The edit file has been synced
    info = await bob_workspace.path_info("/test.txt")
    assert not info["need_sync"]

    # So Alice can read it
    await alice_client.wait_idle_monitors()
    assert await alice_workspace.read_bytes("/test.txt") == b"test2"

    # The workspace can be written again
    await bob_workspace.write_bytes("/this-should-not-fail", b"abc")
    await bob_client.wait_idle_monitors()
    info = await bob_workspace.path_info("/this-should-not-fail")
    assert not info["need_sync"]
