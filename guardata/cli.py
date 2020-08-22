# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import click
import sys
import os

from guardata._version import __version__
from guardata.cli_utils import generate_not_available_cmd


try:
    from guardata.client.cli import client_cmd
except ImportError as exc:
    client_cmd = generate_not_available_cmd(exc)


try:
    from backendService.cli import backend_cmd
except ImportError as exc:
    backend_cmd = generate_not_available_cmd(exc)


@click.group()
@click.version_option(version=__version__, prog_name="guardata")
def cli():
    pass


cli.add_command(client_cmd, "client")
cli.add_command(backend_cmd, "backend")

# Add support for GUARDATA_CMD_ARGS env var

vanilla_cli_main = cli.main


def patched_cli_main(args=None, **kwargs):
    if args is None:
        args = sys.argv[1:]

    raw_extra_args = os.environ.get("GUARDATA_CMD_ARGS", "")
    args += [os.path.expandvars(x) for x in raw_extra_args.split()]

    return vanilla_cli_main(args=args, **kwargs)


cli.main = patched_cli_main


if __name__ == "__main__":
    cli()
