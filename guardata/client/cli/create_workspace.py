# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import click

from guardata.utils import trio_run
from guardata.cli_utils import cli_exception_handler
from guardata.client import logged_client_factory
from guardata.client.cli.utils import client_config_and_device_options


async def _create_workspace(config, device, name):
    async with logged_client_factory(config, device) as client:
        await client.user_fs.workspace_create(f"{name}")


@click.command(short_help="create workspace")
@client_config_and_device_options
@click.argument("name")
def create_workspace(config, device, name, **kwargs):
    """
    Create a new workspace for the given device.
    """
    with cli_exception_handler(config.debug):
        trio_run(_create_workspace, config, device, name)
