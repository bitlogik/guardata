# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import click

from backendService.cli.run import run_cmd
from backendService.cli.migration import migrate


__all__ = ("backend_cmd",)


@click.group()
def backend_cmd():
    pass


backend_cmd.add_command(run_cmd, "run")
backend_cmd.add_command(migrate, "migrate")
