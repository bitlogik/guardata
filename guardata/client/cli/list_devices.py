# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import os
import click
from pathlib import Path

from guardata.client.config import get_default_config_dir
from guardata.client.local_device import list_available_devices
from guardata.client.cli.utils import format_available_devices


@click.command()
@click.option("--config-dir", type=click.Path(exists=True, file_okay=False))
def list_devices(config_dir):
    config_dir = Path(config_dir) if config_dir else get_default_config_dir(os.environ)
    devices = list_available_devices(config_dir)
    num_devices_display = click.style(str(len(devices)), fg="green")
    config_dir_display = click.style(str(config_dir), fg="yellow")
    click.echo(f"Found {num_devices_display} device(s) in {config_dir_display}:")
    click.echo(format_available_devices(devices))
