#! /usr/bin/env python3
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS


import os
import trio

from tqdm import tqdm
from humanize import naturalsize

from guardata.logging import configure_logging
from guardata.client.logged_core import logged_core_factory
from guardata.client.types import FsPath
from guardata.client.config import get_default_config_dir, load_config
from guardata.client.local_device import list_available_devices, load_device_with_password
from guardata.test_utils import (
    make_workspace_dir_inconsistent as make_workspace_dir_inconsistent_helper,
    make_workspace_dir_complex_versions as make_workspace_dir_complex_versions_helper,
    make_workspace_dir_simple_versions as make_workspace_dir_simple_versions_helper,
)


LOG_LEVEL = "WARNING"
DEVICE_ID = "alice@laptop"
PASSWORD = "test"


async def make_workspace_dir_inconsistent(device, workspace, corrupted_path):
    await make_workspace_dir_inconsistent_helper(workspace, FsPath(corrupted_path))
    print(f"{device.device_id} | {workspace.get_workspace_name()} | {corrupted_path}")


async def make_workspace_dir_simple_versions(device, workspace, path):
    await make_workspace_dir_simple_versions_helper(workspace, FsPath(path))
    print(f"{device.device_id} | {workspace.get_workspace_name()} | {path}")


async def make_workspace_dir_complex_versions(device, workspace, path):
    await make_workspace_dir_complex_versions_helper(workspace, FsPath(path))
    print(f"{device.device_id} | {workspace.get_workspace_name()} | {path}")


async def benchmark_file_writing(device, workspace):
    # Touch file
    path = "/foo"
    block_size = 4096 * 1024
    file_size = 64 * 1024 * 1024
    await workspace.touch(path)
    info = await workspace.path_info(path)

    # Log
    print(f"{device.device_id} | {workspace.get_workspace_name()} | {path}")

    # Write file
    start = info["size"] // block_size
    stop = file_size // block_size
    for i in tqdm(range(start, stop)):
        await workspace.write_bytes(path, b"\x00" * block_size, offset=i * block_size)

    # Sync
    await workspace.sync()

    # Serialize
    manifest = await workspace.local_storage.get_manifest(info["id"])
    raw = manifest.dump()

    # Printout
    print(f"File size: {naturalsize(file_size)}")
    print(f"Manifest size: {naturalsize(len(raw))}")

    # Let sync monitor finish
    await trio.sleep(2)


async def main():

    # Config
    configure_logging(LOG_LEVEL)
    config_dir = get_default_config_dir(os.environ)
    config = load_config(config_dir)
    devices = list_available_devices(config_dir)
    key_file = next(key_file for _, device_id, _, key_file in devices if device_id == DEVICE_ID)
    device = load_device_with_password(key_file, PASSWORD)

    # Log in
    async with logged_core_factory(config, device) as client:

        # Get workspace
        user_manifest = client.user_fs.get_user_manifest()
        workspace_entry = user_manifest.workspaces[0]
        workspace = client.user_fs.get_workspace(workspace_entry.id)

        # await make_workspace_dir_inconsistent(device, workspace, "/bar")
        await make_workspace_dir_simple_versions(device, workspace, "/foo")
        # await make_workspace_dir_complex_versions(device, workspace, "/foo")
        # await benchmark_file_writing(device, workspace)


if __name__ == "__main__":
    trio.run(main)
