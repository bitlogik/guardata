# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from itertools import count
from typing import Optional, List, Dict, AsyncIterator, cast, Tuple, Any, Union, Pattern

from pendulum import now as pendulum_now

from guardata.api.protocol import DeviceID
from guardata.client.client_events import ClientEvent
from guardata.api.data import BaseManifest as BaseRemoteManifest
from guardata.client.types import (
    Chunk,
    EntryID,
    EntryName,
    BaseLocalManifest,
    LocalFileManifest,
    LocalFolderManifest,
    LocalFolderishManifests,
    RemoteFolderishManifests,
)

from guardata.client.fs.workspacefs.entry_transactions import EntryTransactions
from guardata.client.fs.exceptions import (
    FSFileConflictError,
    FSReshapingRequiredError,
    FSLocalMissError,
)

from guardata.client.fs.utils import is_file_manifest, is_workspace_manifest, is_folderish_manifest

__all__ = "SyncTransactions"

DEFAULT_BLOCK_SIZE = 4096 * 1024  # 4 MB


# Helpers


def get_filename(manifest: LocalFolderishManifests, entry_id: EntryID) -> Optional[EntryName]:
    gen = (name for name, child_id in manifest.children.items() if child_id == entry_id)
    return next(gen, None)


def get_conflict_filename(
    filename: EntryName, filenames: List[EntryName], author: Optional[DeviceID]
):
    counter = count(2)
    new_filename = full_name(filename, [f"conflicting with {author}"])
    while new_filename in filenames:
        new_filename = full_name(filename, [f"conflicting with {author} - {next(counter)}"])
    return new_filename


def full_name(name: EntryName, suffixes: List[str]) -> EntryName:
    # No suffix
    if not suffixes:
        return name

    # No extension
    suffix_string = "".join(f" ({suffix})" for suffix in suffixes)
    if "." not in name[1:]:
        return EntryName(name + suffix_string)

    # Extension
    first_name, *ext = name.split(".")
    return EntryName(".".join([first_name + suffix_string, *ext]))


# Merging helpers


def merge_folder_children(
    base_children: Dict[EntryName, EntryID],
    local_children: Dict[EntryName, EntryID],
    remote_children: Dict[EntryName, EntryID],
    remote_device_name: Optional[DeviceID],
):
    # Prepare lookups
    base_reversed = {entry_id: name for name, entry_id in base_children.items()}
    local_reversed = {entry_id: name for name, entry_id in local_children.items()}
    remote_reversed = {entry_id: name for name, entry_id in remote_children.items()}

    # All ids that might remain
    ids = set(local_reversed) | set(remote_reversed)

    # First map all ids to their rightful name
    solved_local_children: Dict[EntryName, Any] = {}
    solved_remote_children: Dict[EntryName, Any] = {}
    for id in ids:
        base_name = base_reversed.get(id)
        local_name = local_reversed.get(id)
        remote_name = remote_reversed.get(id)

        # Added locally
        if base_name is None and local_name is not None:
            solved_local_children[local_name] = (local_children[local_name],)

        # Added remotely
        elif base_name is None and remote_name is not None:
            solved_remote_children[remote_name] = (remote_children[remote_name],)

        # Removed locally
        elif local_name is None:
            # Note that locally removed children might not be synchronized at this point
            pass

        # Removed remotely
        elif remote_name is None:
            # Note that we're blindly removing children just because the remote said so
            # This is OK as long as users have a way to recover their local changes
            pass

        # Preserved remotely and locally with the same naming
        elif local_name == remote_name:
            solved_local_children[local_name] = (local_children[local_name],)

        # Name changed locally
        elif base_name == remote_name:
            solved_local_children[local_name] = (local_children[local_name],)

        # Name changed remotely
        elif base_name == local_name:
            solved_remote_children[remote_name] = (remote_children[remote_name],)

        # Name changed both locally and remotely
        else:
            suffix = f"renamed by {remote_device_name}"
            solved_remote_children[remote_name] = remote_children[remote_name], suffix

    # Merge mappings and fix conflicting names
    children = {}
    for name, (entry_id, *suffixes) in solved_remote_children.items():
        children[full_name(name, suffixes)] = entry_id
    for name, (entry_id, *suffixes) in solved_local_children.items():
        if name in children:
            suffixes = *suffixes, f"conflicting with {remote_device_name}"
        children[full_name(name, suffixes)] = entry_id

    # Return
    return children


def merge_manifests(
    local_author: DeviceID,
    pattern_filter: Pattern,
    local_manifest: BaseLocalManifest,
    remote_manifest: Optional[BaseRemoteManifest] = None,
    force_filter: Optional[bool] = False,
):
    # Start by re-applying filter (idempotent)
    if is_folderish_manifest(local_manifest) and force_filter:
        local_manifest = cast(LocalFolderishManifests, local_manifest).apply_filter(pattern_filter)

    # The remote hasn't changed
    if remote_manifest is None or remote_manifest.version <= local_manifest.base_version:
        return local_manifest
    remote_manifest = cast(BaseRemoteManifest, remote_manifest)

    # Exctract versions
    assert remote_manifest is not None
    remote_version = remote_manifest.version
    local_version = local_manifest.base_version
    local_from_remote = BaseLocalManifest.from_remote(
        remote_manifest, pattern_filter, local_manifest
    )

    # Only the remote has changed
    if not local_manifest.need_sync:
        return local_from_remote

    # Both the remote and the local have changed
    assert remote_version > local_version and local_manifest.need_sync

    # All the local changes have been successfully uploaded
    if local_manifest.match_remote(remote_manifest):
        return local_from_remote

    # The remote changes are ours, simply acknowledge them and keep our local changes
    if remote_manifest.author == local_author:
        return local_manifest.evolve(base=remote_manifest)

    # The remote has been updated by some other device
    assert remote_manifest.author != local_author

    # Cannot solve a file conflict directly
    if is_file_manifest(local_manifest):
        raise FSFileConflictError(local_manifest, remote_manifest)

    # Solve the folder conflict
    new_children = merge_folder_children(
        cast(LocalFolderishManifests, local_manifest).base.children,
        cast(LocalFolderishManifests, local_manifest).children,
        cast(LocalFolderishManifests, local_from_remote).children,
        remote_manifest.author,
    )

    # Mark as updated
    return local_from_remote.evolve_and_mark_updated(children=new_children)


class SyncTransactions(EntryTransactions):

    # Public read-only helpers

    async def get_placeholder_children(
        self, remote_manifest: RemoteFolderishManifests
    ) -> AsyncIterator[EntryID]:
        # Check children placeholder
        for chield_entry_id in remote_manifest.children.values():
            try:
                child_manifest = await self.local_storage.get_manifest(chield_entry_id)
            except FSLocalMissError:
                continue
            if child_manifest.is_placeholder:
                yield chield_entry_id

    async def get_minimal_remote_manifest(self, entry_id: EntryID) -> Optional[BaseRemoteManifest]:
        manifest = await self.local_storage.get_manifest(entry_id)
        if not manifest.is_placeholder:
            return None
        return manifest.base.evolve(author=self.local_author, timestamp=pendulum_now(), version=1)

    # Atomic transactions

    async def apply_filter(self, entry_id: EntryID, pattern_filter: Pattern) -> None:
        # Fetch and lock
        async with self.local_storage.lock_manifest(entry_id) as local_manifest:

            # Craft new local manifest
            new_local_manifest = local_manifest.apply_filter(pattern_filter)

            # Set the new base manifest
            if new_local_manifest != local_manifest:
                await self.local_storage.set_manifest(entry_id, new_local_manifest)

    async def synchronization_step(
        self,
        entry_id: EntryID,
        remote_manifest: Optional[BaseRemoteManifest] = None,
        final: bool = False,
    ) -> Optional[BaseRemoteManifest]:
        """Perform a synchronization step.

        This step is meant to be called several times until the right state is reached.
        It takes the current remote manifest as an argument and returns the new remote
        manifest to upload. When the manifest is successfully uploaded, this method has
        to be called once again with the new remote manifest as an argument. When there
        is no more changes to upload, this method returns None. The `final` argument can
        be set to true to indicate that the caller has no intention to upload a new
        manifest. This also causes the method to return None.
        """

        # Fetch and lock
        async with self.local_storage.lock_manifest(entry_id) as local_manifest:

            # Go through the parent chain
            current_manifest = local_manifest
            while not is_workspace_manifest(current_manifest):
                parent_manifest = await self.local_storage.get_manifest(current_manifest.parent)
                parent_manifest = cast(LocalFolderishManifests, parent_manifest)

                # The entry is not confined
                if current_manifest.id not in parent_manifest.confined_entries:
                    current_manifest = parent_manifest
                    continue

                # Send synced event
                self._send_event(
                    ClientEvent.FS_ENTRY_CONFINED, entry_id=entry_id, cause_id=parent_manifest.id
                )
                return None

            # Sync cannot be performed yet
            if not final and is_file_manifest(local_manifest) and not local_manifest.is_reshaped():

                # Try a quick reshape (without downloading any block)
                missing = await self._manifest_reshape(local_manifest)

                # Downloading block is necessary for this reshape
                if missing:
                    raise FSReshapingRequiredError(entry_id)

                # The manifest should be reshaped by now
                local_manifest = await self.local_storage.get_manifest(entry_id)
                assert local_manifest.is_reshaped()

            # Merge manifests
            pattern_filter = self.local_storage.get_pattern_filter()
            force_filter = not self.local_storage.get_pattern_filter_fully_applied()
            new_local_manifest = merge_manifests(
                self.local_author, pattern_filter, local_manifest, remote_manifest, force_filter
            )

            # Extract authors
            base_author = local_manifest.base.author
            remote_author = base_author if remote_manifest is None else remote_manifest.author

            # Extract versions
            base_version = local_manifest.base_version
            new_base_version = new_local_manifest.base_version

            # Set the new base manifest
            if new_local_manifest != local_manifest:
                await self.local_storage.set_manifest(entry_id, new_local_manifest)

            # Send downsynced event
            if base_version != new_base_version and remote_author != self.local_author:
                self._send_event(ClientEvent.FS_ENTRY_DOWNSYNCED, id=entry_id)

            # Send synced event
            if local_manifest.need_sync and not new_local_manifest.need_sync:
                self._send_event(ClientEvent.FS_ENTRY_SYNCED, id=entry_id)

            # Nothing new to upload
            if final or not new_local_manifest.need_sync:
                return None

            # Produce the new remote manifest to upload
            return new_local_manifest.to_remote(self.local_author, pendulum_now())

    async def file_reshape(self, entry_id: EntryID) -> None:

        # Loop over attemps
        while True:

            # Fetch and lock
            async with self.local_storage.lock_manifest(entry_id) as manifest:

                # Normalize
                missing = await self._manifest_reshape(manifest)

            # Done
            if not missing:
                return

            # Load missing blocks
            await self.remote_loader.load_blocks(missing)

    async def file_conflict(
        self,
        entry_id: EntryID,
        local_manifest: Union[LocalFolderManifest, LocalFileManifest],
        remote_manifest: BaseRemoteManifest,
    ) -> None:
        # This is the only transaction that affects more than one manifests
        # That's because the local version of the file has to be registered in the
        # parent as a new child while the remote version has to be set as the actual
        # version. In practice, this should not be an issue.

        # Lock parent then child
        parent_id = local_manifest.parent
        async with self.local_storage.lock_manifest(parent_id) as parent_manifest:
            async with self.local_storage.lock_manifest(entry_id) as current_manifest:

                # Make sure the file still exists
                filename = get_filename(parent_manifest, entry_id)
                if filename is None:
                    return

                # Copy blocks
                new_blocks = []
                for chunks in current_manifest.blocks:
                    new_chunks = []
                    for chunk in chunks:
                        data = await self.local_storage.get_chunk(chunk.id)
                        new_chunk = Chunk.new(chunk.start, chunk.stop)
                        await self.local_storage.set_chunk(new_chunk.id, data)
                        if len(chunks) == 1:
                            new_chunk = new_chunk.evolve_as_block(data)
                        new_chunks.append(chunk)
                    new_blocks.append(tuple(new_chunks))
                new_blocks: Tuple[Tuple[Any, ...], ...] = tuple(new_blocks)

                # Prepare
                new_name = get_conflict_filename(
                    filename, list(parent_manifest.children), remote_manifest.author
                )
                new_manifest = LocalFileManifest.new_placeholder(
                    self.local_author, parent=parent_id
                ).evolve(size=current_manifest.size, blocks=new_blocks)
                new_parent_manifest = parent_manifest.evolve_children_and_mark_updated(
                    {new_name: new_manifest.id},
                    pattern_filter=self.local_storage.get_pattern_filter(),
                )
                other_manifest = BaseLocalManifest.from_remote(remote_manifest)

                # Set manifests
                await self.local_storage.set_manifest(
                    new_manifest.id, new_manifest, check_lock_status=False
                )
                await self.local_storage.set_manifest(parent_id, new_parent_manifest)
                await self.local_storage.set_manifest(entry_id, other_manifest)

                self._send_event(ClientEvent.FS_ENTRY_UPDATED, id=new_manifest.id)
                self._send_event(ClientEvent.FS_ENTRY_UPDATED, id=parent_id)
                self._send_event(
                    ClientEvent.FS_ENTRY_FILE_CONFLICT_RESOLVED,
                    id=entry_id,
                    backup_id=new_manifest.id,
                )
