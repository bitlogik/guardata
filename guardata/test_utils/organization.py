# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS


import os
import random
from typing import Tuple, Optional
from pathlib import Path
from pendulum import now as pendulum_now
from uuid import uuid4

from guardata.logging import configure_logging
from guardata.client import logged_client_factory
from guardata.api.data import (
    UserProfile,
    UserCertificateContent,
    DeviceCertificateContent,
    EntryID,
)
from guardata.api.protocol import OrganizationID, DeviceID, HumanHandle, DeviceName
from guardata.client.logged_client import LoggedClient
from guardata.client.types import (
    WorkspaceRole,
    BackendAddr,
    BackendOrganizationBootstrapAddr,
    LocalDevice,
)
from guardata.client.config import load_config
from guardata.client.backend_connection import (
    BackendAuthenticatedCmds,
    apiv1_backend_administration_cmds_factory,
    apiv1_backend_anonymous_cmds_factory,
    backend_authenticated_cmds_factory,
)
from guardata.client.local_device import generate_new_device, save_device_with_password
from guardata.client.invite import (
    bootstrap_organization,
    DeviceGreetInitialCtx,
    UserGreetInitialCtx,
    claimer_retrieve_info,
)
from guardata.crypto import SigningKey


async def initialize_test_organization(
    config_dir: Path,
    backend_address: BackendAddr,
    password: str,
    administration_token: str,
    force: bool,
    additional_users_number: int,
    additional_devices_number: int,
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
    # Bootstrap organization and Alice user and create device "laptop" for Alice

    async with apiv1_backend_anonymous_cmds_factory(organization_bootstrap_addr) as anonymous_cmds:
        alice_device = await bootstrap_organization(
            cmds=anonymous_cmds,
            human_handle=HumanHandle(label="Alice", email="alice@example.com"),
            device_label="laptop",
        )
        save_device_with_password(config_dir, alice_device, password, force=force)

    config = load_config(config_dir, debug="DEBUG" in os.environ)
    # Create context manager, alice_client will be needed for the rest of the script
    async with logged_client_factory(config, alice_device) as alice_client:
        async with backend_authenticated_cmds_factory(
            addr=alice_device.organization_addr,
            device_id=alice_device.device_id,
            signing_key=alice_device.signing_key,
        ) as alice_cmds:

            # Create new device "pc" for Alice
            other_alice_device = await _register_new_device(
                cmds=alice_cmds, author=alice_device, device_label="pc"
            )
            save_device_with_password(config_dir, other_alice_device, password, force=force)
            # Add additional random device for alice
            if additional_devices_number > 0:
                print(f"Adding {additional_devices_number} devices in the test group")
                print(" ... please wait ...")
                await _add_random_device(
                    cmds=alice_cmds,
                    config_dir=config_dir,
                    force=force,
                    password=password,
                    device=alice_device,
                    additional_devices_number=additional_devices_number,
                )
                print(" Done ")
            # Invite Bob in organization
            bob_device = await _register_new_user(
                cmds=alice_cmds,
                author=alice_device,
                device_label="laptop",
                human_handle=HumanHandle(email="bob@example.com", label="Bob"),
                profile=UserProfile.STANDARD,
            )
            save_device_with_password(config_dir, bob_device, password, force=force)
            # Create Alice workspace
            alice_ws_id = await alice_client.user_fs.workspace_create("alice_workspace")
            # Create context manager
            async with logged_client_factory(config, bob_device) as bob_client:
                # Create Bob workspace
                bob_ws_id = await bob_client.user_fs.workspace_create("bob_workspace")
                # Bob share workspace with Alice
                await bob_client.user_fs.workspace_share(
                    bob_ws_id, alice_device.user_id, WorkspaceRole.MANAGER
                )
                # Alice share workspace with Bob
                await alice_client.user_fs.workspace_share(
                    alice_ws_id, bob_device.user_id, WorkspaceRole.MANAGER
                )
                # Add additional random users
                if additional_users_number > 0:
                    print(f"Adding {additional_users_number} users in the test group")
                    print(" ... please wait ...")
                    await _add_random_users(
                        cmds=alice_cmds,
                        author=alice_device,
                        alice_client=alice_client,
                        bob_client=bob_client,
                        alice_ws_id=alice_ws_id,
                        bob_ws_id=bob_ws_id,
                        additional_users_number=additional_users_number,
                    )
                    print(" Done ")

    # Synchronize every device
    for device in (alice_device, other_alice_device, bob_device):
        async with logged_client_factory(config, device) as client:
            await client.user_fs.process_last_messages()
            await client.user_fs.sync()
    return (alice_device, other_alice_device, bob_device)


async def _add_random_device(cmds, password, config_dir, device, force, additional_devices_number):
    for _ in range(additional_devices_number):
        requested_device_label = "device_" + str(uuid4())[:8]
        new_device = await _register_new_device(
            cmds=cmds, author=device, device_label=requested_device_label
        )
        save_device_with_password(config_dir, new_device, password, force=force)


async def _add_random_users(
    cmds: BackendAuthenticatedCmds,
    author: LocalDevice,
    alice_client: LoggedClient,
    bob_client: LoggedClient,
    alice_ws_id: EntryID,
    bob_ws_id: EntryID,
    additional_users_number: int,
):
    """Add random number of users with random role, and share workspaces with them.
    1 out of 10 users will be revoked from organization.
    """
    for _ in range(additional_users_number):
        name = "test_" + str(uuid4())[:8]
        user_profile = random.choice(list(UserProfile))
        realm_role = random.choice(list(WorkspaceRole))
        if user_profile == UserProfile.OUTSIDER:
            realm_role = random.choice([WorkspaceRole.READER, WorkspaceRole.CONTRIBUTOR])
        else:
            realm_role = random.choice(list(WorkspaceRole))
        # Workspace_choice :
        #  0 = add user to first_ws, 1 = add to second_ws, 2 = add in both workspace, other = nothing
        workspace_choice = random.randint(0, 3)
        # invite user to organization
        user_device = await _register_new_user(
            cmds=cmds,
            author=author,
            device_label="desktop",
            human_handle=HumanHandle(email=f"{name}@gmail.com", label=name),
            profile=user_profile,
        )
        # Share workspace with new user
        if workspace_choice == 0 or workspace_choice == 2:
            await alice_client.user_fs.workspace_share(alice_ws_id, user_device.user_id, realm_role)
        if workspace_choice == 1 or workspace_choice == 2:
            await bob_client.user_fs.workspace_share(bob_ws_id, user_device.user_id, realm_role)
        # One chance out of 10 to be revoked from organization
        if not random.randint(0, 9):
            await alice_client.revoke_user(user_device.user_id)


async def _init_ctx_create(cmds, token):
    initial_ctx = UserGreetInitialCtx(cmds=cmds, token=token)
    in_progress_ctx = await initial_ctx.do_wait_peer()
    in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()
    in_progress_ctx = await in_progress_ctx.do_signify_trust()
    in_progress_ctx = await in_progress_ctx.do_get_claim_requests()
    return in_progress_ctx


async def _init_ctx_claim(cmds):
    initial_ctx = await claimer_retrieve_info(cmds=cmds)
    in_progress_ctx = await initial_ctx.do_wait_peer()
    in_progress_ctx = await in_progress_ctx.do_signify_trust()
    in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()
    return in_progress_ctx


async def _invite_user_task(cmds, token, host_device, profile: UserProfile = UserProfile.STANDARD):
    in_progress_ctx = await _init_ctx_create(cmds=cmds, token=token)
    await in_progress_ctx.do_create_new_user(
        author=host_device,
        human_handle=in_progress_ctx.requested_human_handle,
        device_label=in_progress_ctx.requested_device_label,
        profile=profile,
    )


async def _invite_device_task(cmds, device, device_label, token):
    initial_ctx = DeviceGreetInitialCtx(cmds=cmds, token=token)
    in_progress_ctx = await initial_ctx.do_wait_peer()
    in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()
    in_progress_ctx = await in_progress_ctx.do_signify_trust()
    in_progress_ctx = await in_progress_ctx.do_get_claim_requests()
    await in_progress_ctx.do_create_new_device(
        author=device, device_label=in_progress_ctx.requested_device_label
    )


async def _claim_user(cmds, claimer_email, requested_device_label, requested_user_label):
    in_progress_ctx = await _init_ctx_claim(cmds)
    new_device = await in_progress_ctx.do_claim_user(
        requested_human_handle=HumanHandle(label=requested_user_label, email=claimer_email),
        requested_device_label=requested_device_label,
    )
    return new_device


async def _claim_device(cmds, requested_device_label):
    initial_ctx = await claimer_retrieve_info(cmds=cmds)
    in_progress_ctx = await initial_ctx.do_wait_peer()
    in_progress_ctx = await in_progress_ctx.do_signify_trust()
    in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()
    new_device = await in_progress_ctx.do_claim_device(
        requested_device_label=requested_device_label
    )
    return new_device


async def _register_new_user(
    cmds: BackendAuthenticatedCmds,
    author: LocalDevice,
    device_label: Optional[str],
    human_handle: Optional[HumanHandle],
    profile: UserProfile,
) -> LocalDevice:
    new_device = generate_new_device(
        organization_addr=cmds.addr,
        device_label=device_label,
        human_handle=human_handle,
        profile=profile,
    )
    now = pendulum_now()

    user_certificate = UserCertificateContent(
        author=author.device_id,
        timestamp=now,
        user_id=new_device.device_id.user_id,
        human_handle=new_device.human_handle,
        public_key=new_device.public_key,
        profile=new_device.profile,
    )
    redacted_user_certificate = user_certificate.evolve(human_handle=None)

    device_certificate = DeviceCertificateContent(
        author=author.device_id,
        timestamp=now,
        device_id=new_device.device_id,
        device_label=new_device.device_label,
        verify_key=new_device.verify_key,
    )
    redacted_device_certificate = device_certificate.evolve(device_label=None)

    user_certificate = user_certificate.dump_and_sign(author.signing_key)
    redacted_user_certificate = redacted_user_certificate.dump_and_sign(author.signing_key)
    device_certificate = device_certificate.dump_and_sign(author.signing_key)
    redacted_device_certificate = redacted_device_certificate.dump_and_sign(author.signing_key)

    rep = await cmds.user_create(
        user_certificate=user_certificate,
        device_certificate=device_certificate,
        redacted_user_certificate=redacted_user_certificate,
        redacted_device_certificate=redacted_device_certificate,
    )
    if rep["status"] != "ok":
        raise RuntimeError(f"Cannot create user: {rep}")

    return new_device


async def _register_new_device(
    cmds: BackendAuthenticatedCmds, author: LocalDevice, device_label: Optional[str]
):
    new_device = LocalDevice(
        organization_addr=author.organization_addr,
        device_id=DeviceID(f"{author.user_id}@{DeviceName.new()}"),
        device_label=device_label,
        human_handle=author.human_handle,
        profile=author.profile,
        private_key=author.private_key,
        signing_key=SigningKey.generate(),
        user_manifest_id=author.user_manifest_id,
        user_manifest_key=author.user_manifest_key,
        local_symkey=author.local_symkey,
    )
    now = pendulum_now()

    device_certificate = DeviceCertificateContent(
        author=author.device_id,
        timestamp=now,
        device_id=new_device.device_id,
        device_label=new_device.device_label,
        verify_key=new_device.verify_key,
    )
    redacted_device_certificate = device_certificate.evolve(device_label=None)

    device_certificate = device_certificate.dump_and_sign(author.signing_key)
    redacted_device_certificate = redacted_device_certificate.dump_and_sign(author.signing_key)

    rep = await cmds.device_create(
        device_certificate=device_certificate,
        redacted_device_certificate=redacted_device_certificate,
    )

    if rep["status"] != "ok":
        raise RuntimeError(f"Cannot create device: {rep}")

    return new_device
