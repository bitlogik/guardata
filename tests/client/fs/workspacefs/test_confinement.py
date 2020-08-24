# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import re
import pytest

from guardata.client.types import FsPath
from tests.common import create_shared_workspace


async def assert_path_info(workspace, path, **kwargs):
    info = await workspace.path_info(path)
    for key, value in kwargs.items():
        assert info[key] == value, key


@pytest.mark.trio
async def test_confined_entries(alice_workspace, running_backend):

    # Apply a *.tmp filter
    pattern = re.compile(r".*\.tmp$")
    await alice_workspace.set_and_apply_pattern_filter(pattern)
    assert alice_workspace.local_storage.get_pattern_filter() == pattern
    assert alice_workspace.local_storage.get_pattern_filter_fully_applied()

    # Use foo as working directory
    await assert_path_info(alice_workspace, "/foo", confined=False, need_sync=False)

    # Create a temporary file and temporary folder
    await alice_workspace.mkdir("/foo/x.tmp")
    await alice_workspace.touch("/foo/y.tmp")

    # Check status
    await assert_path_info(alice_workspace, "/foo", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/foo/x.tmp", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/foo/y.tmp", confined=True, need_sync=True)

    # Force a sync
    await alice_workspace.sync()

    # There should be nothing to synchronize
    await assert_path_info(alice_workspace, "/foo", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/foo/x.tmp", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/foo/y.tmp", confined=True, need_sync=True)

    # Create a non-temporary file
    await alice_workspace.touch("/foo/z.txt")

    # Check status
    await assert_path_info(alice_workspace, "/foo", confined=False, need_sync=True)
    await assert_path_info(alice_workspace, "/foo/x.tmp", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/foo/y.tmp", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/foo/z.txt", confined=False, need_sync=True)

    # Force a sync
    await alice_workspace.sync()

    # Check status
    await assert_path_info(alice_workspace, "/foo", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/foo/x.tmp", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/foo/y.tmp", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/foo/z.txt", confined=False, need_sync=False)

    # Remove a temporary file
    await alice_workspace.rmdir("/foo/x.tmp")
    assert not await alice_workspace.exists("/foo/x.tmp")

    # Check status
    await assert_path_info(alice_workspace, "/foo", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/foo/y.tmp", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/foo/z.txt", confined=False, need_sync=False)

    # Force a sync
    await alice_workspace.sync()

    # Nothing has changed
    await assert_path_info(alice_workspace, "/foo", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/foo/y.tmp", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/foo/z.txt", confined=False, need_sync=False)

    # Rename a temporary file
    await alice_workspace.rename("/foo/y.tmp", "/foo/y.txt")
    assert not await alice_workspace.exists("/foo/y.tmp")

    # Check status
    await assert_path_info(alice_workspace, "/foo", confined=False, need_sync=True)
    await assert_path_info(alice_workspace, "/foo/y.txt", confined=False, need_sync=True)
    await assert_path_info(alice_workspace, "/foo/z.txt", confined=False, need_sync=False)

    # Force a sync
    await alice_workspace.sync()

    # Check status
    await assert_path_info(alice_workspace, "/foo", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/foo/y.txt", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/foo/z.txt", confined=False, need_sync=False)


@pytest.mark.trio
async def test_sync_with_different_filters(running_backend, alice_user_fs, alice2_user_fs):
    wid = await create_shared_workspace("w", alice_user_fs, alice2_user_fs)
    workspace1 = alice_user_fs.get_workspace(wid)
    workspace2 = alice2_user_fs.get_workspace(wid)

    # Workspace 1 filters .tmp files
    pattern1 = re.compile(r".*\.tmp$")
    await workspace1.set_and_apply_pattern_filter(pattern1)
    await workspace1.sync()

    # Workspace 2 filters ~ files
    pattern2 = re.compile(r".*~$")
    await workspace2.set_and_apply_pattern_filter(pattern2)
    await workspace2.sync()

    # Workspace 1 create some files and directories
    await workspace1.mkdir("/foo/xyz.tmp/bar", parents=True)
    await workspace1.mkdir("/foo/xyz~/bar", parents=True)
    await workspace1.mkdir("/foo/xyz/bar", parents=True)
    await workspace1.write_bytes("/foo/xyz.tmp/bar/test.txt", b"a1")
    await workspace1.write_bytes("/foo/xyz~/bar/test.txt", b"b1")
    await workspace1.write_bytes("/foo/xyz/bar/test.txt", b"c1")

    # Both workspaces sync
    await workspace1.sync()
    await workspace2.sync()

    # Check workspace 2
    assert await workspace2.listdir("/") == [FsPath("/foo")]
    assert await workspace2.listdir("/foo") == [FsPath("/foo/xyz")]
    assert await workspace2.listdir("/foo/xyz") == [FsPath("/foo/xyz/bar")]
    assert await workspace2.listdir("/foo/xyz/bar") == [FsPath("/foo/xyz/bar/test.txt")]

    # Check file content
    assert await workspace2.read_bytes("/foo/xyz/bar/test.txt") == b"c1"

    # Workspace 2 create the same files and directories
    await workspace2.mkdir("/foo/xyz.tmp/bar", parents=True)
    await workspace2.mkdir("/foo/xyz~/bar", parents=True)
    await workspace2.write_bytes("/foo/xyz.tmp/bar/test.txt", b"a2")
    await workspace2.write_bytes("/foo/xyz~/bar/test.txt", b"b2")
    await workspace2.write_bytes("/foo/xyz/bar/test.txt", b"c2")

    # Both workspaces sync
    await workspace2.sync()
    await workspace1.sync()

    # Check both workspaces
    for workspace in (workspace1, workspace2):
        assert await workspace.listdir("/") == [FsPath("/foo")]
        assert await workspace.listdir("/foo") == [
            FsPath("/foo/xyz"),
            FsPath("/foo/xyz.tmp"),
            FsPath("/foo/xyz~"),
        ]
        assert await workspace.listdir("/foo/xyz") == [FsPath("/foo/xyz/bar")]
        assert await workspace.listdir("/foo/xyz.tmp") == [FsPath("/foo/xyz.tmp/bar")]
        assert await workspace.listdir("/foo/xyz~") == [FsPath("/foo/xyz~/bar")]
        assert await workspace.listdir("/foo/xyz/bar") == [FsPath("/foo/xyz/bar/test.txt")]
        assert await workspace.listdir("/foo/xyz.tmp/bar") == [FsPath("/foo/xyz.tmp/bar/test.txt")]
        assert await workspace.listdir("/foo/xyz~/bar") == [FsPath("/foo/xyz~/bar/test.txt")]

    # Check file contents
    assert await workspace1.read_bytes("/foo/xyz.tmp/bar/test.txt") == b"a1"
    assert await workspace1.read_bytes("/foo/xyz~/bar/test.txt") == b"b1"
    assert await workspace1.read_bytes("/foo/xyz/bar/test.txt") == b"c2"
    assert await workspace2.read_bytes("/foo/xyz.tmp/bar/test.txt") == b"a2"
    assert await workspace2.read_bytes("/foo/xyz~/bar/test.txt") == b"b2"
    assert await workspace2.read_bytes("/foo/xyz/bar/test.txt") == b"c2"


@pytest.mark.trio
async def test_change_filter(alice_workspace, running_backend):

    # Apply a *.x filter
    pattern = re.compile(r".*\.x$")
    await alice_workspace.set_and_apply_pattern_filter(pattern)
    assert alice_workspace.local_storage.get_pattern_filter() == pattern
    assert alice_workspace.local_storage.get_pattern_filter_fully_applied()

    # Create x, y and z files
    await alice_workspace.touch("/test1.x")
    await alice_workspace.touch("/test1.y")
    await alice_workspace.touch("/test1.z")

    # Check status
    await assert_path_info(alice_workspace, "/test1.x", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/test1.y", confined=False, need_sync=True)
    await assert_path_info(alice_workspace, "/test1.z", confined=False, need_sync=True)

    # Synchronize then create more x, y and z files
    await alice_workspace.sync()
    await alice_workspace.touch("/test2.x")
    await alice_workspace.touch("/test2.y")
    await alice_workspace.touch("/test2.z")

    # Check status
    await assert_path_info(alice_workspace, "/test1.x", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/test1.y", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/test1.z", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/test2.x", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/test2.y", confined=False, need_sync=True)
    await assert_path_info(alice_workspace, "/test2.y", confined=False, need_sync=True)

    # Appy Y filter
    pattern = re.compile(r".*\.y$")
    await alice_workspace.set_and_apply_pattern_filter(pattern)
    assert alice_workspace.local_storage.get_pattern_filter() == pattern
    assert alice_workspace.local_storage.get_pattern_filter_fully_applied()

    # Check status
    await assert_path_info(alice_workspace, "/test1.x", confined=False, need_sync=True)
    await assert_path_info(alice_workspace, "/test1.y", confined=True, need_sync=False)
    await assert_path_info(alice_workspace, "/test1.z", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/test2.x", confined=False, need_sync=True)
    await assert_path_info(alice_workspace, "/test2.y", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/test2.z", confined=False, need_sync=True)

    # Synchronize the workspace
    await alice_workspace.sync()

    await assert_path_info(alice_workspace, "/test1.x", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/test1.y", confined=True, need_sync=False)
    await assert_path_info(alice_workspace, "/test1.z", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/test2.x", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/test2.y", confined=True, need_sync=True)
    await assert_path_info(alice_workspace, "/test2.z", confined=False, need_sync=False)

    # Rollback to X filter
    pattern = re.compile(r".*\.x$")
    await alice_workspace.set_and_apply_pattern_filter(pattern)
    assert alice_workspace.local_storage.get_pattern_filter() == pattern
    assert alice_workspace.local_storage.get_pattern_filter_fully_applied()

    # Check status
    await assert_path_info(alice_workspace, "/test1.x", confined=True, need_sync=False)
    await assert_path_info(alice_workspace, "/test1.y", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/test1.z", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/test2.x", confined=True, need_sync=False)
    await assert_path_info(alice_workspace, "/test2.y", confined=False, need_sync=True)
    await assert_path_info(alice_workspace, "/test2.z", confined=False, need_sync=False)

    # Synchronize the workspace
    await alice_workspace.sync()

    await assert_path_info(alice_workspace, "/test1.x", confined=True, need_sync=False)
    await assert_path_info(alice_workspace, "/test1.y", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/test1.z", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/test2.x", confined=True, need_sync=False)
    await assert_path_info(alice_workspace, "/test2.y", confined=False, need_sync=False)
    await assert_path_info(alice_workspace, "/test2.z", confined=False, need_sync=False)


@pytest.mark.trio
async def test_common_temporary_files(alice_workspace):
    file_list = ["test.txt", "test" "t" ".test"]
    for path in file_list:
        path = "/" + path
        await alice_workspace.touch(path)
        await assert_path_info(alice_workspace, path, confined=False)

    confined_file_list = [
        "test.tmp",
        "test.temp",
        "test.swp",
        "test~",
        ".fuse_hidden000001",
        ".directory",
        ".Trash-0001",
        ".nfsxxx",
        ".goutputstream-U6EGP0",
        ".DS_Store",
        ".AppleDouble",
        ".LSOverride",
        "._test",
        "etc/ssh/ssh_host_rsa_key"
        "Thumbs.db",
        "test.stackdump",
        "Desktop.ini",
        "desktop.ini",
        "$RECYCLE.BIN",
        "test.lnk",
        ".~test",
        "~$test",
    ]
    for path in confined_file_list:
        path = "/" + path
        await alice_workspace.touch(path)
        await assert_path_info(alice_workspace, path, confined=True)
