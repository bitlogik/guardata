# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import os
import click

from guardata.utils import trio_run
from guardata.cli_utils import spinner, operation, cli_exception_handler
from guardata.client.types import BackendOrganizationClaimDeviceAddr
from guardata.client.cli.utils import client_config_options
from guardata.client.local_device import save_device_with_password
from guardata.client.invite_claim import claim_device as actual_claim_device


async def _claim_device(config, organization_addr, new_device_id, token, password):
    async with spinner("Waiting for referee to reply"):
        device = await actual_claim_device(
            organization_addr=organization_addr,
            new_device_id=new_device_id,
            token=token,
            keepalive=config.backend_connection_keepalive,
        )

    device_display = click.style(new_device_id, fg="yellow")
    with operation(f"Saving locally {device_display}"):
        save_device_with_password(config.config_dir, device, password)


@click.command()
@client_config_options
@click.option("--addr", required=True, type=BackendOrganizationClaimDeviceAddr.from_url)
@click.option("--token")
@click.password_option()
def claim_device(config, addr, token, password, **kwargs):
    if token and addr.token:
        raise SystemExit("token already specified in the addr option")
    token = token or addr.token
    if not token:
        raise SystemExit("Missing token value")

    debug = "DEBUG" in os.environ
    with cli_exception_handler(debug):
        trio_run(
            _claim_device, config, addr.to_organization_addr(), addr.device_id, token, password
        )
