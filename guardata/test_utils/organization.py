# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS


import os
import trio
from typing import Tuple
from pathlib import Path
from uuid import uuid4
from typing import Optional
import random

from guardata.logging import configure_logging
from guardata.core import logged_core_factory
from guardata.api.data import UserProfile
from guardata.api.protocol import OrganizationID, HumanHandle, InvitationType
from guardata.core.types import (
    WorkspaceRole,
    BackendAddr,
    BackendOrganizationBootstrapAddr,
    BackendInvitationAddr,
    LocalDevice,
)
from guardata.core.config import load_config
from guardata.core.backend_connection import (
    apiv1_backend_administration_cmds_factory,
    apiv1_backend_anonymous_cmds_factory,
    backend_authenticated_cmds_factory,
    backend_invited_cmds_factory,
)
from guardata.core.local_device import save_device_with_password
from guardata.core.invite import (
    bootstrap_organization,
    DeviceGreetInitialCtx,
    UserGreetInitialCtx,
    claimer_retrieve_info,
)


async def initialize_test_organization(
    config_dir: Path,
    backend_address: BackendAddr,
    password: str,
    administration_token: str,
    force: bool,
    add_random_users: int,
) -> Tuple[LocalDevice, LocalDevice, LocalDevice]:

    configure_logging("WARNING")

    organization_id = OrganizationID("Org")

    # Create organization

    async with apiv1_backend_administration_cmds_factory(
        backend_address, administration_token
    ) as administration_cmds:

        rep = await administration_cmds.organization_create(organization_id)
        assert rep["status"] == "ok"
        bootstrap_token = rep["bootstrap_token"]

        organization_bootstrap_addr = BackendOrganizationBootstrapAddr.build(
            backend_address, organization_id, bootstrap_token
        )

    # Bootstrap organization and Alice user

    async with apiv1_backend_anonymous_cmds_factory(organization_bootstrap_addr) as anonymous_cmds:
        alice_device = await bootstrap_organization(
            cmds=anonymous_cmds,
            human_handle=HumanHandle(label="Alice", email="alice@example.com"),
            device_label="laptop",
        )
        save_device_with_password(config_dir, alice_device, password, force=force)

    # Create a workspace for Alice

    config = load_config(config_dir, debug="DEBUG" in os.environ)
    async with logged_core_factory(config, alice_device) as core:
        alice_ws_id = await core.user_fs.workspace_create("alice_workspace")
        await core.user_fs.sync()

    # Register a new device for Alice

    other_alice_device = None
    async with backend_authenticated_cmds_factory(
        addr=alice_device.organization_addr,
        device_id=alice_device.device_id,
        signing_key=alice_device.signing_key,
    ) as alice_cmds:

        other_alice_device = await _invite_user_to_organization(
            alice_cmds=alice_cmds,
            alice_device=alice_device,
            config_dir=config_dir,
            password=password,
            force=force,
            device_label="pc",
            claim="device",
        )

        # Invite Bob in
        bob_device = await _invite_user_to_organization(
            alice_cmds=alice_cmds,
            alice_device=alice_device,
            config_dir=config_dir,
            password=password,
            force=force,
            claimer_email="bob@example.com",
            label="Bob",
            device_label="laptop",
            claim="user",
        )

        # Add more users to workspace if add_random_users > 0
        await _add_random_users_to_organization(
            config=config,
            alice_cmds=alice_cmds,
            config_dir=config_dir,
            password=password,
            force=force,
            add_random_users=add_random_users,
            alice_ws_id=alice_ws_id,
            alice_device=alice_device,
        )

    # Create bob workspace and share with Alice

    async with logged_core_factory(config, bob_device) as core:
        bob_ws_id = await core.user_fs.workspace_create("bob_workspace")
        await core.user_fs.workspace_share(bob_ws_id, alice_device.user_id, WorkspaceRole.MANAGER)

    # Share Alice workspace with bob

    await _share_workspace_with_user(
        config=config,
        host_device=alice_device,
        workspace_id=alice_ws_id,
        invited_device=bob_device,
        role=None,
    )

    # Synchronize every device
    for device in (alice_device, other_alice_device, bob_device):
        async with logged_core_factory(config, device) as core:
            await core.user_fs.process_last_messages()
            await core.user_fs.sync()

    return (alice_device, other_alice_device, bob_device)


async def _share_workspace_with_user(
    config, host_device, workspace_id, invited_device, role: Optional[WorkspaceRole]
):
    async with logged_core_factory(config, host_device) as core:
        await core.user_fs.workspace_share(workspace_id, invited_device.user_id, role)


async def _invite_user_to_organization(
    alice_cmds,
    alice_device,
    config_dir,
    password,
    force,
    claim,
    device_label,
    claimer_email=None,
    label=None,
):
    device = None
    rep = None
    Invitation_type = None
    if claim == "user":
        Invitation_type = InvitationType.USER
        rep = await alice_cmds.invite_new(type=Invitation_type, claimer_email=claimer_email)
    elif claim == "device":
        Invitation_type = InvitationType.DEVICE
        rep = await alice_cmds.invite_new(type=Invitation_type)
    else:
        return
    assert rep["status"] == "ok"
    invitation_addr = BackendInvitationAddr.build(
        backend_addr=alice_device.organization_addr,
        organization_id=alice_device.organization_id,
        invitation_type=Invitation_type,
        token=rep["token"],
    )
    async with backend_invited_cmds_factory(addr=invitation_addr) as invited_cmds:

        async def invite_task():

            if claim == "user":
                initial_ctx = UserGreetInitialCtx(cmds=alice_cmds, token=invitation_addr.token)
                in_progress_ctx = await initial_ctx.do_wait_peer()
                in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()
                in_progress_ctx = await in_progress_ctx.do_signify_trust()
                in_progress_ctx = await in_progress_ctx.do_get_claim_requests()
                await in_progress_ctx.do_create_new_user(
                    author=alice_device,
                    human_handle=in_progress_ctx.requested_human_handle,
                    device_label=in_progress_ctx.requested_device_label,
                    profile=UserProfile.STANDARD,
                )
            elif claim == "device":
                initial_ctx = DeviceGreetInitialCtx(cmds=alice_cmds, token=invitation_addr.token)
                in_progress_ctx = await initial_ctx.do_wait_peer()
                in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()
                in_progress_ctx = await in_progress_ctx.do_signify_trust()
                in_progress_ctx = await in_progress_ctx.do_get_claim_requests()
                await in_progress_ctx.do_create_new_device(
                    author=alice_device, device_label=in_progress_ctx.requested_device_label
                )

        async def claim_task():
            nonlocal device
            initial_ctx = await claimer_retrieve_info(cmds=invited_cmds)
            in_progress_ctx = await initial_ctx.do_wait_peer()
            in_progress_ctx = await in_progress_ctx.do_signify_trust()
            in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()
            if claim == "user":
                device = await in_progress_ctx.do_claim_user(
                    requested_human_handle=HumanHandle(label=label, email=claimer_email),
                    requested_device_label=device_label,
                )
            elif claim == "device":
                device = await in_progress_ctx.do_claim_device(requested_device_label=device_label)

        async with trio.open_service_nursery() as nursery:
            nursery.start_soon(invite_task)
            nursery.start_soon(claim_task)
        if device_label != "no_device":
            save_device_with_password(config_dir, device, password, force=force)

    return device


async def _add_random_users_to_organization(
    alice_cmds,
    config,
    config_dir: Path,
    password: str,
    force: bool,
    add_random_users: int,
    alice_device,
    alice_ws_id,
):

    if add_random_users <= 0:
        return
    if add_random_users > 200:
        add_random_users = 200
    while add_random_users > 0:
        name = "test_" + str(uuid4())[:9]
        device = await _invite_user_to_organization(
            alice_cmds=alice_cmds,
            alice_device=alice_device,
            config_dir=config_dir,
            force=force,
            password=password,
            claimer_email=f"{name}@gmail.com",
            label=name,
            claim="user",
            device_label="no_device",
        )
        realm_role = random.choice(list(WorkspaceRole))
        await _share_workspace_with_user(
            config=config,
            host_device=alice_device,
            workspace_id=alice_ws_id,
            invited_device=device,
            role=realm_role,
        )
        add_random_users = add_random_users - 1
