# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import click

from guardata.client.cli import list_devices, status_organization

from guardata.client.cli import invitation
from guardata.client.cli import create_organization
from guardata.client.cli import stats_organization
from guardata.client.cli import create_workspace
from guardata.client.cli import share_workspace
from guardata.client.cli import bootstrap_organization
from guardata.client.cli import run


__all__ = ("client_cmd",)


@click.group()
def client_cmd():
    pass


client_cmd.add_command(run.run_gui, "gui")
client_cmd.add_command(run.run_mountpoint, "run")
client_cmd.add_command(create_workspace.create_workspace, "create_workspace")
client_cmd.add_command(share_workspace.share_workspace, "share_workspace")
client_cmd.add_command(list_devices.list_devices, "list_devices")

client_cmd.add_command(invitation.invite_user, "invite_user")
client_cmd.add_command(invitation.invite_device, "invite_device")
client_cmd.add_command(invitation.list_invitations, "list_invitations")
client_cmd.add_command(invitation.greet_invitation, "greet_invitation")
client_cmd.add_command(invitation.claim_invitation, "claim_invitation")
client_cmd.add_command(invitation.cancel_invitation, "cancel_invitation")

client_cmd.add_command(create_organization.create_organization, "create_organization")
client_cmd.add_command(stats_organization.stats_organization, "stats_organization")
client_cmd.add_command(status_organization.status_organization, "status_organization")
client_cmd.add_command(bootstrap_organization.bootstrap_organization, "bootstrap_organization")
