# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import click
import platform

from guardata.utils import trio_run
from guardata.cli_utils import spinner, operation, cli_exception_handler, aprompt
from guardata.api.protocol import HumanHandle
from guardata.client.types import BackendOrganizationBootstrapAddr
from guardata.client.backend_connection import apiv1_backend_anonymous_cmds_factory
from guardata.client.local_device import save_device_with_password
from guardata.client.invite import bootstrap_organization as do_bootstrap_organization
from guardata.client.cli.utils import client_config_options


async def _bootstrap_organization(config, addr, password, force):
    label = await aprompt("User fullname")
    email = await aprompt("User email")
    human_handle = HumanHandle(email=email, label=label)
    device_label = await aprompt("Device label", default=platform.node())

    async with apiv1_backend_anonymous_cmds_factory(addr=addr) as cmds:
        async with spinner("Bootstrapping organization in the backend"):
            new_device = await do_bootstrap_organization(
                cmds=cmds, human_handle=human_handle, device_label=device_label
            )

        device_display = click.style(new_device.slughash, fg="yellow")
        with operation(f"Saving device {device_display}"):
            save_device_with_password(
                config_dir=config.config_dir, device=new_device, password=password, force=force
            )


@click.command(short_help="configure new organization")
@client_config_options
@click.argument("addr", type=BackendOrganizationBootstrapAddr.from_url)
@click.password_option(prompt="Choose a password for the device")
@click.option("--force", is_flag=True)
def bootstrap_organization(config, addr, password, force, **kwargs):
    """
    Configure the organization and register it first user&device.
    """
    with cli_exception_handler(config.debug):
        # Disable task monitoring given user prompt will block the coroutine
        trio_run(_bootstrap_organization, config, addr, password, force)
