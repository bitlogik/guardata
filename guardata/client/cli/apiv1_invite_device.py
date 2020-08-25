# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import click

from guardata.utils import trio_run
from guardata.cli_utils import spinner, cli_exception_handler
from guardata.api.protocol import DeviceName
from guardata.client.types import BackendOrganizationClaimDeviceAddr
from guardata.client.invite_claim import generate_invitation_token, invite_and_create_device
from guardata.client.cli.utils import client_config_and_device_options


async def _invite_device(config, device, new_device_name):
    action_addr = BackendOrganizationClaimDeviceAddr.build(
        organization_addr=device.organization_addr,
        device_id=device.user_id.to_device_id(new_device_name),
    )
    token = generate_invitation_token()

    action_addr_display = click.style(action_addr.to_url(), fg="yellow")
    token_display = click.style(token, fg="yellow")
    click.echo(f"url: {action_addr_display}")
    click.echo(f"token: {token_display}")

    async with spinner("Waiting for invitation reply"):
        await invite_and_create_device(
            device=device,
            new_device_name=new_device_name,
            token=token,
            keepalive=config.backend_connection_keepalive,
        )

    display_device = click.style(f"{device.device_name}@{new_device_name}", fg="yellow")
    click.echo(f"Device {display_device} is ready !")


@click.command()
@client_config_and_device_options
@click.argument("new_device_name", type=DeviceName, required=True)
def invite_device(config, device, new_device_name, **kwargs):
    with cli_exception_handler(config.debug):
        trio_run(_invite_device, config, device, new_device_name)
