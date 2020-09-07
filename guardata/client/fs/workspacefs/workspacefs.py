# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import attr
import trio
from collections import defaultdict
from typing import Union, List, Dict, Tuple, AsyncIterator, cast, Pattern
from pendulum import Pendulum, now as pendulum_now

from guardata.api.data import BaseManifest as BaseRemoteManifest
from guardata.api.data import FileManifest as RemoteFileManifest
from guardata.api.protocol import UserID, MaintenanceType
from guardata.client.types import (
    FsPath,
    EntryID,
    LocalDevice,
    WorkspaceRole,
    RemoteFolderishManifests,
    DEFAULT_BLOCK_SIZE,
)
from guardata.client.backend_connection import BackendNotAvailable, BackendConnectionError
from guardata.client.fs.remote_loader import RemoteLoader
from guardata.client.fs import (
    workspacefs,
)  # Needed to break cyclic import with WorkspaceFSTimestamped
from guardata.client.fs.workspacefs.sync_transactions import SyncTransactions
from guardata.client.fs.workspacefs.versioning_helpers import VersionLister
from guardata.client.fs.utils import is_file_manifest, is_folderish_manifest
from guardata.client.fs.exceptions import (
    FSRemoteManifestNotFound,
    FSRemoteManifestNotFoundBadVersion,
    FSRemoteSyncError,
    FSNoSynchronizationRequired,
    FSFileConflictError,
    FSReshapingRequiredError,
    FSWorkspaceNoAccess,
    FSWorkspaceTimestampedTooEarly,
    FSLocalMissError,
    FSInvalidArgumentError,
    FSNotADirectoryError,
    FSBackendOfflineError,
    FSError,
)

from guardata.client.fs.workspacefs.workspacefile import WorkspaceFile

AnyPath = Union[FsPath, str]


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ReencryptionNeed:
    user_revoked: Tuple[UserID, ...]
    role_revoked: Tuple[UserID, ...]
    reencryption_already_in_progress: bool = False

    @property
    def need_reencryption(self):
        return self.role_revoked or self.user_revoked or self.reencryption_already_in_progress


class WorkspaceFS:
    def __init__(
        self,
        workspace_id: EntryID,
        get_workspace_entry,
        device: LocalDevice,
        local_storage,
        backend_cmds,
        event_bus,
        remote_devices_manager,
    ):
        self.workspace_id = workspace_id
        self.get_workspace_entry = get_workspace_entry
        self.device = device
        self.local_storage = local_storage
        self.backend_cmds = backend_cmds
        self.event_bus = event_bus
        self.remote_devices_manager = remote_devices_manager
        self.sync_locks: Dict[EntryID, trio.Lock] = defaultdict(trio.Lock)

        self.remote_loader = RemoteLoader(
            self.device,
            self.workspace_id,
            self.get_workspace_entry,
            self.backend_cmds,
            self.remote_devices_manager,
            self.local_storage,
        )
        self.transactions = SyncTransactions(
            self.workspace_id,
            self.get_workspace_entry,
            self.device,
            self.local_storage,
            self.remote_loader,
            self.event_bus,
        )

    def __repr__(self):
        try:
            name = self.get_workspace_name()
        except Exception:
            name = "<could not retrieve name>"
        return f"<{type(self).__name__}(id={self.workspace_id!r}, name={name!r})>"

    def get_workspace_name(self) -> str:
        return self.get_workspace_entry().name

    def get_encryption_revision(self) -> int:
        return self.get_workspace_entry().encryption_revision

    def is_read_only(self) -> bool:
        return self.get_workspace_entry().role == WorkspaceRole.READER

    def is_revoked(self) -> bool:
        return self.get_workspace_entry().role is None

    # Information

    async def path_info(self, path: AnyPath) -> dict:
        """
        Raises:
            FSError
        """
        return await self.transactions.entry_info(FsPath(path))

    async def path_id(self, path: AnyPath) -> EntryID:
        """
        Raises:
            FSError
        """
        info = await self.transactions.entry_info(FsPath(path))
        return info["id"]

    async def get_user_roles(self) -> Dict[UserID, WorkspaceRole]:
        """
        Raises:
            FSError
            FSBackendOfflineError
        """
        try:
            workspace_manifest = await self.local_storage.get_manifest(self.workspace_id)
            if workspace_manifest.is_placeholder:
                return {self.device.user_id: WorkspaceRole.OWNER}

        except FSLocalMissError:
            pass

        try:
            return await self.remote_loader.load_realm_current_roles()

        except FSWorkspaceNoAccess:
            # Seems we lost all the access roles
            return {}

    async def get_reencryption_need(self) -> ReencryptionNeed:
        """
        Raises:
            FSError
            FSBackendOfflineError
            FSWorkspaceNoAccess
        """
        wentry = self.get_workspace_entry()
        try:
            workspace_manifest = await self.local_storage.get_manifest(self.workspace_id)
            if workspace_manifest.is_placeholder:
                return ReencryptionNeed(
                    user_revoked=(), role_revoked=(), reencryption_already_in_progress=False
                )

        except FSLocalMissError:
            pass

        try:
            rep = await self.backend_cmds.realm_status(self.workspace_id)

        except BackendNotAvailable as exc:
            raise FSBackendOfflineError(str(exc)) from exc

        except BackendConnectionError as exc:
            raise FSError(
                f"Cannot retrieve the remote status for workspace {self.workspace_id}: {exc}"
            ) from exc

        reencryption_already_in_progress = (
            rep["in_maintenance"] and rep["maintenance_type"] == MaintenanceType.REENCRYPTION
        )

        certificates = await self.remote_loader.load_realm_role_certificates()
        has_role = set()
        role_revoked = set()
        for certif in certificates:
            if certif.role is None:
                if certif.timestamp > wentry.encrypted_on:
                    role_revoked.add(certif.user_id)
                has_role.discard(certif.user_id)
            else:
                role_revoked.discard(certif.user_id)
                has_role.add(certif.user_id)

        user_revoked = []
        for user_id in has_role:
            _, revoked_user = await self.remote_loader.get_user(user_id, no_cache=True)
            if revoked_user and revoked_user.timestamp > wentry.encrypted_on:
                user_revoked.append(user_id)

        return ReencryptionNeed(
            user_revoked=tuple(user_revoked),
            role_revoked=tuple(role_revoked),
            reencryption_already_in_progress=reencryption_already_in_progress,
        )

    # Versioning

    async def get_earliest_timestamp(self) -> Pendulum:
        """
        Get the earliest timestamp from which we can obtain a timestamped workspace

        Verify the obtained timestamp is in the ballpark of the manifest at version 0

        Raises:
            FSError
        """
        manifest = await self.remote_loader.load_manifest(self.get_workspace_entry().id, version=1)
        return manifest.timestamp

    def get_version_lister(self):
        return VersionLister(self)

    # Timestamped version

    async def to_timestamped(self, timestamp: Pendulum):
        workspace = workspacefs.WorkspaceFSTimestamped(self, timestamp)
        try:
            await workspace.path_info("/")
        except FSRemoteManifestNotFoundBadVersion as exc:
            raise FSWorkspaceTimestampedTooEarly from exc

        return workspace

    # Pathlib-like interface

    async def exists(self, path: AnyPath) -> bool:
        """
        Raises:
            FSError
        """
        path = FsPath(path)
        try:
            await self.transactions.entry_info(path)
        except (FileNotFoundError, NotADirectoryError):
            return False
        return True

    async def is_dir(self, path: AnyPath) -> bool:
        """
        Raises:
            FSError
        """
        path = FsPath(path)
        info = await self.transactions.entry_info(path)
        return info["type"] == "folder"

    async def is_file(self, path: AnyPath) -> bool:
        """
        Raises:
            FSError
        """
        path = FsPath(path)
        info = await self.transactions.entry_info(FsPath(path))
        return info["type"] == "file"

    async def iterdir(self, path: AnyPath) -> AsyncIterator[FsPath]:
        """
        Raises:
            FSError
        """
        path = FsPath(path)
        info = await self.transactions.entry_info(path)
        if "children" not in info:
            raise FSNotADirectoryError(filename=str(path))
        for child in info["children"]:
            yield path / child

    async def listdir(self, path: AnyPath) -> List[FsPath]:
        """
        Raises:
            FSError
        """
        return [child async for child in self.iterdir(path)]

    async def rename(self, source: AnyPath, destination: AnyPath, overwrite: bool = True) -> None:
        """
        Raises:
            FSError
        """
        source = FsPath(source)
        destination = FsPath(destination)
        await self.transactions.entry_rename(source, destination, overwrite=overwrite)

    async def mkdir(self, path: AnyPath, parents: bool = False, exist_ok: bool = False) -> None:
        """
        Raises:
            FSError
        """
        path = FsPath(path)
        if path.is_root() and exist_ok:
            return
        try:
            await self.transactions.folder_create(path)
        except FileNotFoundError:
            if not parents or path.parent == path:
                raise
            await self.mkdir(path.parent, parents=True, exist_ok=True)
            await self.mkdir(path, parents=False, exist_ok=exist_ok)
        except FileExistsError:
            if not exist_ok or not await self.is_dir(path):
                raise

    async def rmdir(self, path: AnyPath) -> None:
        """
        Raises:
            FSError
        """
        path = FsPath(path)
        await self.transactions.folder_delete(path)

    async def touch(self, path: AnyPath, exist_ok: bool = True) -> None:
        """
        Raises:
            FSError
        """
        path = FsPath(path)
        try:
            await self.transactions.file_create(path, open=False)
        except FileExistsError:
            if not exist_ok:
                raise

    async def unlink(self, path: AnyPath) -> None:
        """
        Raises:
            FSError
        """
        path = FsPath(path)
        await self.transactions.file_delete(path)

    async def truncate(self, path: AnyPath, length: int) -> None:
        """
        Raises:
            FSError
        """
        path = FsPath(path)
        await self.transactions.file_resize(path, length)

    async def read_bytes(self, path: AnyPath, size: int = -1, offset: int = 0) -> bytes:
        """
        Raises:
            FSError
        """
        path = FsPath(path)
        _, fd = await self.transactions.file_open(path, "r")
        try:
            return await self.transactions.fd_read(fd, size, offset)
        finally:
            await self.transactions.fd_close(fd)

    async def open_file(self, path: AnyPath, mode="r"):
        path = FsPath(path)
        # check if file exist, if not and a writting mode is set, then create the file
        if "x" in mode:
            try:
                _, fd = await self.transactions.file_create(path, open=True)
            except FileExistsError:
                raise
        elif not await self.exists(path) and sum(c in mode for c in "aw") == 1:
            _, fd = await self.transactions.file_create(path, open=True)
        else:
            _, fd = await self.transactions.file_open(path, mode)
        assert fd is not None
        f = WorkspaceFile(fd, self.transactions, mode=mode, path=path)
        await f.ainit()
        return f

    async def write_bytes(
        self, path: AnyPath, data: bytes, offset: int = 0, truncate: bool = True
    ) -> int:
        """
        The offset value is used to determine the index of the writing operation.
        If the offset is negative, we append the new bytes to the current content.
        If the truncate argument is set to True, the offset argument is also used to resize the file.
        Raises:
            FSError
        """
        path = FsPath(path)
        try:
            _, fd = await self.transactions.file_create(path, open=True)
            assert fd is not None  # Because `open=True` has been provided
        except FileExistsError:
            _, fd = await self.transactions.file_open(path, "w")
        try:
            if offset >= 0 and truncate:
                await self.transactions.fd_resize(fd, offset)
            return await self.transactions.fd_write(fd, data, offset)
        finally:
            await self.transactions.fd_close(fd)

    # Shutil-like interface

    async def move(self, source: AnyPath, destination: AnyPath):
        """
        Raises:
            FSError
        """
        source = FsPath(source)
        destination = FsPath(destination)
        real_destination = destination

        if source.parts == destination.parts[: len(source.parts)]:
            raise FSInvalidArgumentError(
                f"Cannot move a directory {source} into itself {destination}"
            )
        try:
            if await self.is_dir(destination):
                real_destination = destination / source.name
                if await self.exists(real_destination):
                    raise FileExistsError
        # At this point, real_destination is the target either representing :
        # - the destination path if it didn't already exist,
        # - a new entry with the same name as source, but inside the destination directory
        except FileNotFoundError:
            pass

        # Rename if possible
        if source.parent == real_destination.parent:
            return await self.rename(source, real_destination)

        # Copy directory
        if await self.is_dir(source):
            await self.copytree(source, real_destination)
            await self.rmtree(source)
            return

        # Copy file
        await self.copyfile(source, real_destination)
        await self.unlink(source)

    async def copytree(self, source_path: AnyPath, target_path: AnyPath):
        source_path = FsPath(source_path)
        target_path = FsPath(target_path)
        source_files = await self.listdir(source_path)
        await self.mkdir(target_path)
        for source_file in source_files:
            target_file = target_path / source_file.name
            if await self.is_dir(source_file):
                await self.copytree(source_file, target_file)
            elif await self.is_file(source_file):
                await self.copyfile(source_file, target_file)

    async def copyfile(
        self,
        source_path: AnyPath,
        target_path: AnyPath,
        length=DEFAULT_BLOCK_SIZE,
        exist_ok: bool = False,
    ):
        """
        Raises:
            FSError
        """
        await self.touch(target_path, exist_ok=exist_ok)
        offset = 0
        while True:
            buff = await self.read_bytes(source_path, length, offset * length)
            if not buff:
                break
            await self.write_bytes(target_path, buff, offset * length)
            offset += 1

    async def rmtree(self, path: AnyPath):
        """
        Raises:
            FSError
        """
        path = FsPath(path)
        async for child in self.iterdir(path):
            if await self.is_dir(child):
                await self.rmtree(child)
            else:
                await self.unlink(child)
        await self.rmdir(path)

    # Sync helpers

    async def _synchronize_placeholders(self, manifest: RemoteFolderishManifests) -> None:
        async for child in self.transactions.get_placeholder_children(manifest):
            await self.minimal_sync(child)

    async def _upload_blocks(self, manifest: RemoteFileManifest) -> None:
        for access in manifest.blocks:
            try:
                data = await self.local_storage.get_dirty_block(access.id)
            except FSLocalMissError:
                continue
            await self.remote_loader.upload_block(access, data)

    async def minimal_sync(self, entry_id: EntryID) -> None:
        """
        Raises:
            FSError
        """
        # Make sure the corresponding realm exists
        await self._create_realm_if_needed()

        # Get a minimal manifest to upload
        try:
            remote_manifest = await self.transactions.get_minimal_remote_manifest(entry_id)
        # Not available locally so nothing to synchronize
        except FSLocalMissError:
            return

        # No miminal manifest to upload, the entry is not a placeholder
        if remote_manifest is None:
            return

        # Upload the miminal manifest
        try:
            await self.remote_loader.upload_manifest(entry_id, remote_manifest)
        # The upload has failed: download the latest remote manifest
        except FSRemoteSyncError:
            remote_manifest = await self.remote_loader.load_manifest(entry_id)

        # Register the manifest to unset the placeholder tag
        try:
            await self.transactions.synchronization_step(entry_id, remote_manifest, final=True)
        # Not available locally so nothing to synchronize
        except FSLocalMissError:
            pass

    async def _sync_by_id(
        self, entry_id: EntryID, remote_changed: bool = True
    ) -> BaseRemoteManifest:
        """
        Synchronize the entry corresponding to a specific ID.

        This method keeps performing synchronization steps on the given ID until one of
        those two conditions is met:
        - there is no more changes to upload
        - one upload operation has succeeded and has been acknowledged

        This guarantees that any change prior to the call is saved remotely when this
        method returns.
        """
        # Get the current remote manifest if it has changed
        remote_manifest = None
        if remote_changed:
            try:
                remote_manifest = await self.remote_loader.load_manifest(entry_id)
            except FSRemoteManifestNotFound:
                pass

        # Loop over sync transactions
        final = False
        while True:

            # Protect against race conditions on the entry id
            try:

                # Perform the sync step transaction
                try:
                    new_remote_manifest = await self.transactions.synchronization_step(
                        entry_id, remote_manifest, final
                    )

                # The entry first requires reshaping
                except FSReshapingRequiredError:
                    await self.transactions.file_reshape(entry_id)
                    continue

            # The manifest doesn't exist locally
            except FSLocalMissError:
                raise FSNoSynchronizationRequired(entry_id)

            # No new manifest to upload, the entry is synced!
            if new_remote_manifest is None:
                return remote_manifest or (await self.local_storage.get_manifest(entry_id)).base

            # Synchronize placeholder children
            if is_folderish_manifest(new_remote_manifest):
                await self._synchronize_placeholders(
                    cast(RemoteFolderishManifests, new_remote_manifest)
                )

            # Upload blocks
            if is_file_manifest(new_remote_manifest):
                await self._upload_blocks(cast(RemoteFileManifest, new_remote_manifest))

            # Restamp the remote manifest
            new_remote_manifest = new_remote_manifest.evolve(timestamp=pendulum_now())

            # Upload the new manifest containing the latest changes
            try:
                await self.remote_loader.upload_manifest(entry_id, new_remote_manifest)

            # The upload has failed: download the latest remote manifest
            except FSRemoteSyncError:
                remote_manifest = await self.remote_loader.load_manifest(entry_id)

            # The upload has succeeded: loop one last time to acknowledge this new version
            else:
                final = True
                remote_manifest = new_remote_manifest

    async def _create_realm_if_needed(self):
        # Get workspace manifest
        try:
            workspace_manifest = await self.local_storage.get_manifest(self.workspace_id)

        # Cannot be a placeholder if we know about it but don't have it in local
        except FSLocalMissError:
            return

        if workspace_manifest.is_placeholder:
            await self.remote_loader.create_realm(self.workspace_id)

    async def sync_by_id(
        self, entry_id: EntryID, remote_changed: bool = True, recursive: bool = True
    ):
        """
        Raises:
            FSError
        """
        # Make sure the corresponding realm exists
        await self._create_realm_if_needed()

        # Sync parent first
        try:
            async with self.sync_locks[entry_id]:
                manifest = await self._sync_by_id(entry_id, remote_changed=remote_changed)

        # Nothing to synchronize if the manifest does not exist locally
        except FSNoSynchronizationRequired:
            return

        # A file conflict needs to be adressed first
        except FSFileConflictError as exc:
            local_manifest, remote_manifest = exc.args
            # Only file manifest have synchronization conflict
            assert is_file_manifest(local_manifest)
            await self.transactions.file_conflict(entry_id, local_manifest, remote_manifest)
            return await self.sync_by_id(local_manifest.parent)

        # Non-recursive
        if not recursive or is_file_manifest(manifest):
            return

        # Synchronize children
        for name, entry_id in cast(RemoteFolderishManifests, manifest).children.items():
            await self.sync_by_id(entry_id, remote_changed=remote_changed, recursive=True)

    async def sync(self, *, remote_changed: bool = True) -> None:
        """
        Raises:
            FSError
        """
        await self.sync_by_id(self.workspace_id, remote_changed=remote_changed, recursive=True)

    # Apply filter

    async def _recursive_apply_filter(self, entry_id: EntryID, pattern_filter: Pattern):
        # Load manifest
        try:
            manifest = await self.local_storage.get_manifest(entry_id)
        # Not stored locally, nothing to do
        except FSLocalMissError:
            return

        # A file manifest, nothing to do
        if is_file_manifest(manifest):
            return

        # Apply filter (idempotent)
        await self.transactions.apply_filter(entry_id, pattern_filter)

        # Synchronize children
        for name, child_entry_id in manifest.children.items():
            await self._recursive_apply_filter(child_entry_id, pattern_filter)

    async def apply_pattern_filter(self, pattern: Pattern):
        # Fully apply pattern filter
        await self._recursive_apply_filter(self.workspace_id, pattern)
        # Acknowledge pattern filter
        await self.local_storage.set_pattern_filter_fully_applied(pattern)

    async def set_pattern_filter(self, pattern: Pattern):
        await self.local_storage.set_pattern_filter(pattern)

    async def set_and_apply_pattern_filter(self, pattern: Pattern):
        await self.set_pattern_filter(pattern)
        if not self.local_storage.get_pattern_filter_fully_applied():
            await self.apply_pattern_filter(self.local_storage.get_pattern_filter())

    # Debugging helper

    async def dump(self):
        async def rec(entry_id):
            result = {"id": entry_id}
            try:
                manifest = await self.local_storage.get_manifest(entry_id)
            except FSLocalMissError:
                return result

            result.update(manifest.asdict())
            try:
                children = manifest.children
            except AttributeError:
                return result

            for key, value in children.items():
                result["children"][key] = await rec(value)
            return result

        return await rec(self.workspace_id)
