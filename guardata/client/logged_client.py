# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import re
import attr
import fnmatch
from uuid import UUID
from pathlib import Path
import importlib_resources
from pendulum import now as pendulum_now
from typing import Optional, Tuple, List, Pattern
from structlog import get_logger
from functools import partial
from async_generator import asynccontextmanager

from guardata.event_bus import EventBus
from guardata.api.protocol import UserID, InvitationType, InvitationDeletedReason
from guardata.api.data import RevokedUserCertificateContent
import guardata.client.resources
from guardata.client.types import LocalDevice, UserInfo, DeviceInfo, BackendInvitationAddr
from guardata.client.config import ClientConfig
from guardata.client.backend_connection import (
    BackendAuthenticatedConn,
    BackendConnectionError,
    BackendNotFoundError,
    BackendConnStatus,
    BackendNotAvailable,
)
from guardata.client.invite import (
    UserGreetInitialCtx,
    UserGreetInProgress1Ctx,
    DeviceGreetInitialCtx,
    DeviceGreetInProgress1Ctx,
    InviteAlreadyMemberError,
)
from guardata.client.remote_devices_manager import (
    RemoteDevicesManager,
    RemoteDevicesManagerError,
    RemoteDevicesManagerBackendOfflineError,
    RemoteDevicesManagerNotFoundError,
)
from guardata.client.mountpoint import mountpoint_manager_factory, MountpointManager
from guardata.client.messages_monitor import monitor_messages
from guardata.client.sync_monitor import monitor_sync
from guardata.client.fs import UserFS


logger = get_logger()

FAILSAFE_PATTERN_FILTER = re.compile(r"\~\$|\.\~|.*\.tmp$")


def _get_pattern_filter(pattern_filter_path: Path) -> Optional[Pattern]:
    try:
        data = pattern_filter_path.read_text()
    except OSError as exc:
        logger.warning(
            f"Path to the file containing the filename patterns "
            f"to ignore is not properly defined: {exc}"
        )
        return None
    try:
        regex = "|".join(
            fnmatch.translate(line.strip())
            for line in data.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    except ValueError as exc:
        logger.warning(
            f"Could not parse the file containing the filename patterns " f"to ignore: {exc}"
        )
        return None
    try:
        return re.compile(regex)
    except re.error as exc:
        logger.warning(
            f"Could not compile the file containing the filename patterns "
            f"to ignore into a regex pattern: {exc}"
        )
        return None


def get_pattern_filter(pattern_filter_path: Optional[Path] = None) -> Pattern:
    pattern = None
    # Get the pattern from the path defined in the client config
    if pattern_filter_path is not None:
        pattern = _get_pattern_filter(pattern_filter_path)
    # Default to the pattern from the ignore file in the client resources
    if pattern is None:
        try:
            with importlib_resources.path(
                guardata.client.resources, "default_pattern.ignore"
            ) as path:
                pattern = _get_pattern_filter(path)
        except OSError:
            pass
    # As a last resort use the failsafe
    if pattern is None:
        return FAILSAFE_PATTERN_FILTER
    return pattern


@attr.s(frozen=True, slots=True, auto_attribs=True)
class OrganizationStats:
    users: int
    data_size: int
    metadata_size: int


@attr.s(frozen=True, slots=True, auto_attribs=True)
class LoggedClient:
    config: ClientConfig
    device: LocalDevice
    event_bus: EventBus
    mountpoint_manager: MountpointManager
    user_fs: UserFS
    _remote_devices_manager: RemoteDevicesManager
    _backend_conn: BackendAuthenticatedConn

    def are_monitors_idle(self) -> bool:
        return self._backend_conn.are_monitors_idle()

    async def wait_idle_monitors(self) -> None:
        await self._backend_conn.wait_idle_monitors()

    @property
    def backend_status(self) -> BackendConnStatus:
        return self._backend_conn.status

    @property
    def backend_status_exc(self) -> Optional[Exception]:
        return self._backend_conn.status_exc

    async def find_humans(
        self,
        query: str = None,
        page: int = 1,
        per_page: int = 100,
        omit_revoked: bool = False,
        omit_non_human: bool = False,
    ) -> Tuple[List[UserInfo], int]:
        """
        Raises:
            BackendConnectionError
        """
        rep = await self._backend_conn.cmds.human_find(
            query=query,
            page=page,
            per_page=per_page,
            omit_revoked=omit_revoked,
            omit_non_human=omit_non_human,
        )
        if rep["status"] != "ok":
            raise BackendConnectionError(f"Backend error: {rep}")
        results = []
        for item in rep["results"]:
            user_info = await self.get_user_info(item["user_id"])
            results.append(user_info)
        return (results, rep["total"])

    async def get_organization_stats(self) -> OrganizationStats:
        """
        Raises:
            BackendConnectionError
        """
        rep = await self._backend_conn.cmds.organization_stats()
        if rep["status"] != "ok":
            raise BackendConnectionError(f"Backend error: {rep}")
        return OrganizationStats(
            users=rep["users"], data_size=rep["data_size"], metadata_size=rep["metadata_size"]
        )

    async def get_user_info(self, user_id: UserID) -> UserInfo:
        """
        Raises:
            BackendConnectionError
        """
        try:
            user_certif, revoked_user_certif = await self._remote_devices_manager.get_user(user_id)
        except RemoteDevicesManagerBackendOfflineError as exc:
            raise BackendNotAvailable(str(exc)) from exc
        except RemoteDevicesManagerNotFoundError as exc:
            raise BackendNotFoundError(str(exc)) from exc
        except RemoteDevicesManagerError as exc:
            # TODO: we should be using our own kind of exception instead of borowing BackendConnectionError...
            raise BackendConnectionError(
                f"Error while fetching user {user_id} certificates"
            ) from exc
        return UserInfo(
            user_id=user_certif.user_id,
            human_handle=user_certif.human_handle,
            profile=user_certif.profile,
            revoked_on=revoked_user_certif.timestamp if revoked_user_certif else None,
            created_on=user_certif.timestamp,
        )

    async def get_user_devices_info(
        self, user_id: UserID = None, page: int = 1, per_page: int = 100
    ) -> List[DeviceInfo]:
        """
        Raises:
            BackendConnectionError
        """
        user_id = user_id or self.device.user_id
        try:
            (
                user_certif,
                revoked_user_certif,
                device_certifs,
            ) = await self._remote_devices_manager.get_user_and_devices(user_id, no_cache=True)
        except RemoteDevicesManagerBackendOfflineError as exc:
            raise BackendNotAvailable(str(exc)) from exc
        except RemoteDevicesManagerNotFoundError as exc:
            raise BackendNotFoundError(str(exc)) from exc
        except RemoteDevicesManagerError as exc:
            # TODO: we should be using our own kind of exception instead of borowing BackendConnectionError...
            raise BackendConnectionError(
                f"Error while fetching user {user_id} certificates"
            ) from exc
        results = []
        for device_certif in device_certifs:
            results.append(
                DeviceInfo(
                    device_id=device_certif.device_id,
                    device_label=device_certif.device_label,
                    created_on=device_certif.timestamp,
                )
            )
        total = len(results)
        result_page = results[(page - 1) * per_page : page * per_page]
        return result_page, total

    async def revoke_user(self, user_id: UserID) -> None:
        """
        Raises:
            BackendConnectionError
        """
        now = pendulum_now()
        revoked_user_certificate = RevokedUserCertificateContent(
            author=self.device.device_id, timestamp=now, user_id=user_id
        ).dump_and_sign(self.device.signing_key)
        rep = await self._backend_conn.cmds.user_revoke(
            revoked_user_certificate=revoked_user_certificate
        )
        if rep["status"] != "ok":
            raise BackendConnectionError(f"Error while trying to revoke user {user_id}: {rep}")

        # Invalidate potential cache to avoid displaying the user as not-revoked
        self._remote_devices_manager.invalidate_user_cache(user_id)

    async def new_user_invitation(self, email: str, send_email: bool) -> BackendInvitationAddr:
        """
        Raises:
            BackendConnectionError
        """
        rep = await self._backend_conn.cmds.invite_new(
            type=InvitationType.USER, claimer_email=email, send_email=send_email
        )
        if rep["status"] == "already_member":
            raise InviteAlreadyMemberError()
        elif rep["status"] != "ok":
            raise BackendConnectionError(f"Backend error: {rep}")
        return BackendInvitationAddr.build(
            backend_addr=self.device.organization_addr,
            organization_id=self.device.organization_id,
            invitation_type=InvitationType.USER,
            token=rep["token"],
        )

    async def new_device_invitation(self, send_email: bool) -> BackendInvitationAddr:
        """
        Raises:
            BackendConnectionError
        """
        rep = await self._backend_conn.cmds.invite_new(
            type=InvitationType.DEVICE, send_email=send_email
        )
        if rep["status"] != "ok":
            raise BackendConnectionError(f"Backend error: {rep}")
        return BackendInvitationAddr.build(
            backend_addr=self.device.organization_addr,
            organization_id=self.device.organization_id,
            invitation_type=InvitationType.DEVICE,
            token=rep["token"],
        )

    async def delete_invitation(
        self, token: UUID, reason: InvitationDeletedReason = InvitationDeletedReason.CANCELLED
    ) -> None:
        """
        Raises:
            BackendConnectionError
        """
        rep = await self._backend_conn.cmds.invite_delete(token=token, reason=reason)
        if rep["status"] != "ok":
            raise BackendConnectionError(f"Backend error: {rep}")

    async def list_invitations(self) -> List[dict]:  # TODO: better return type
        """
        Raises:
            BackendConnectionError
        """
        rep = await self._backend_conn.cmds.invite_list()
        if rep["status"] != "ok":
            raise BackendConnectionError(f"Backend error: {rep}")
        return rep["invitations"]

    async def start_greeting_user(self, token: UUID) -> UserGreetInProgress1Ctx:
        """
        Raises:
            BackendConnectionError
            InviteError
        """
        initial_ctx = UserGreetInitialCtx(cmds=self._backend_conn.cmds, token=token)
        return await initial_ctx.do_wait_peer()

    async def start_greeting_device(self, token: UUID) -> DeviceGreetInProgress1Ctx:
        """
        Raises:
            BackendConnectionError
            InviteError
        """
        initial_ctx = DeviceGreetInitialCtx(cmds=self._backend_conn.cmds, token=token)
        return await initial_ctx.do_wait_peer()


@asynccontextmanager
async def logged_client_factory(
    config: ClientConfig, device: LocalDevice, event_bus: Optional[EventBus] = None
):
    event_bus = event_bus or EventBus()

    # Get the pattern filter
    if config.pattern_filter is None:
        pattern_filter = get_pattern_filter(config.pattern_filter_path)
    else:
        try:
            pattern_filter = re.compile(config.pattern_filter)
        except re.error:
            pattern_filter = get_pattern_filter(config.pattern_filter_path)

    backend_conn = BackendAuthenticatedConn(
        addr=device.organization_addr,
        device_id=device.device_id,
        signing_key=device.signing_key,
        event_bus=event_bus,
        max_cooldown=config.backend_max_cooldown,
        max_pool=config.backend_max_connections,
        keepalive=config.backend_connection_keepalive,
    )

    path = config.data_base_dir / device.slug
    remote_devices_manager = RemoteDevicesManager(backend_conn.cmds, device.root_verify_key)
    async with UserFS.run(
        device, path, backend_conn.cmds, remote_devices_manager, event_bus, pattern_filter
    ) as user_fs:

        backend_conn.register_monitor(partial(monitor_messages, user_fs, event_bus))
        backend_conn.register_monitor(partial(monitor_sync, user_fs, event_bus))

        async with backend_conn.run():
            async with mountpoint_manager_factory(
                user_fs,
                event_bus,
                config.mountpoint_base_dir,
                mount_all=config.mountpoint_enabled,
                mount_on_workspace_created=config.mountpoint_enabled,
                mount_on_workspace_shared=config.mountpoint_enabled,
                unmount_on_workspace_revoked=config.mountpoint_enabled,
                exclude_from_mount_all=config.disabled_workspaces,
            ) as mountpoint_manager:

                yield LoggedClient(
                    config=config,
                    device=device,
                    event_bus=event_bus,
                    mountpoint_manager=mountpoint_manager,
                    user_fs=user_fs,
                    remote_devices_manager=remote_devices_manager,
                    backend_conn=backend_conn,
                )
