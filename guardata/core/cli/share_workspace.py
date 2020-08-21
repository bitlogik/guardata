# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import click

from guardata.utils import trio_run
from guardata.api.protocol import UserID
from guardata.cli_utils import cli_exception_handler
from guardata.core import logged_core_factory
from guardata.core.cli.utils import core_config_and_device_options


async def _share_workspace(config, device, name, user_id):
    async with logged_core_factory(config, device) as core:
        await core.user_fs.workspace_share(f"/{name}", user_id)


@click.command(short_help="share workspace")
@core_config_and_device_options
@click.argument("workspace_name")
@click.argument("user_id", type=UserID, required=True)
def share_workspace(config, device, workspace_name, user_id, **kwargs):
    """
    Create a new workspace for the given device.
    """
    with cli_exception_handler(config.debug):
        trio_run(_share_workspace, config, device, workspace_name, user_id)