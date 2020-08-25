# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from pathlib import Path
from collections import defaultdict
from typing import Dict, Tuple, Set, Optional, Union, AsyncIterator, NoReturn, Pattern

import trio
from trio import hazmat
from pendulum import Pendulum
from structlog import get_logger
from async_generator import asynccontextmanager

from guardata.client.types import (
    EntryID,
    BlockID,
    ChunkID,
    LocalDevice,
    FileDescriptor,
    BaseLocalManifest,
    LocalFileManifest,
)
from guardata.client.fs.exceptions import FSError, FSLocalMissError, FSInvalidFileDescriptor

from guardata.client.fs.storage.local_database import LocalDatabase
from guardata.client.fs.storage.manifest_storage import ManifestStorage
from guardata.client.fs.storage.chunk_storage import ChunkStorage, BlockStorage
from guardata.client.fs.storage.version import (
    WORKSPACE_DATA_STORAGE_NAME,
    WORKSPACE_CACHE_STORAGE_NAME,
)


logger = get_logger()

# TODO: should be in config.py
DEFAULT_BLOCK_CACHE_SIZE = 512 * 1024 * 1024
DEFAULT_CHUNK_VACUUM_THRESHOLD = 512 * 1024 * 1024


class BaseWorkspaceStorage:
    """ Common base class for WorkspaceStorage and WorkspaceStorageTimestamped
    Can not be instanciated
    """

    def __init__(
        self,
        device: LocalDevice,
        path: Path,
        workspace_id: EntryID,
        block_storage: ChunkStorage,
        chunk_storage: ChunkStorage,
    ):
        self.path = path
        self.device = device
        self.device_id = device.device_id
        self.workspace_id = workspace_id

        # File descriptors
        self.open_fds: Dict[FileDescriptor, EntryID] = {}
        self.fd_counter = 0

        # Locking structures
        self.locking_tasks: Dict[EntryID, hazmat.Task] = {}
        self.entry_locks: Dict[EntryID, trio.Lock] = defaultdict(trio.Lock)

        # Manifest and block storage
        self.block_storage = block_storage
        self.chunk_storage = chunk_storage

        # Pattern attributes
        self._pattern_filter: Optional[Pattern] = None
        self._pattern_filter_fully_applied: bool = False

    def _get_next_fd(self) -> FileDescriptor:
        self.fd_counter += 1
        return FileDescriptor(self.fd_counter)

    async def get_manifest(self, entry_id: EntryID) -> BaseLocalManifest:
        raise NotImplementedError

    # Locking helpers

    @asynccontextmanager
    async def lock_entry_id(self, entry_id: EntryID) -> AsyncIterator[EntryID]:
        async with self.entry_locks[entry_id]:
            try:
                self.locking_tasks[entry_id] = hazmat.current_task()
                yield entry_id
            finally:
                del self.locking_tasks[entry_id]

    @asynccontextmanager
    async def lock_manifest(self, entry_id: EntryID) -> AsyncIterator[BaseLocalManifest]:
        async with self.lock_entry_id(entry_id):
            yield await self.get_manifest(entry_id)

    def _check_lock_status(self, entry_id: EntryID) -> None:
        task = self.locking_tasks.get(entry_id)
        if task != hazmat.current_task():
            raise RuntimeError(f"Entry `{entry_id}` modified without beeing locked")

    # File management interface

    def create_file_descriptor(self, manifest: LocalFileManifest) -> FileDescriptor:
        assert isinstance(manifest, LocalFileManifest)
        fd = self._get_next_fd()
        self.open_fds[fd] = manifest.id
        return fd

    async def load_file_descriptor(self, fd: FileDescriptor) -> LocalFileManifest:
        try:
            entry_id = self.open_fds[fd]
        except KeyError:
            raise FSInvalidFileDescriptor(fd)
        manifest = await self.get_manifest(entry_id)
        assert isinstance(manifest, LocalFileManifest)
        return manifest

    def remove_file_descriptor(self, fd: FileDescriptor) -> None:
        try:
            self.open_fds.pop(fd)
        except KeyError:
            raise FSInvalidFileDescriptor(fd)

    # Block interface

    async def set_clean_block(self, block_id: BlockID, block: bytes) -> None:
        assert isinstance(block_id, BlockID)
        return await self.block_storage.set_chunk(ChunkID(block_id), block)

    async def clear_clean_block(self, block_id: BlockID) -> None:
        assert isinstance(block_id, BlockID)
        try:
            await self.block_storage.clear_chunk(ChunkID(block_id))
        except FSLocalMissError:
            pass

    async def get_dirty_block(self, block_id: BlockID) -> bytes:
        return await self.chunk_storage.get_chunk(ChunkID(block_id))

    # Chunk interface

    async def get_chunk(self, chunk_id: ChunkID) -> bytes:
        assert isinstance(chunk_id, ChunkID)
        try:
            return await self.chunk_storage.get_chunk(chunk_id)
        except FSLocalMissError:
            return await self.block_storage.get_chunk(chunk_id)

    async def set_chunk(self, chunk_id: ChunkID, block: bytes) -> None:
        assert isinstance(chunk_id, ChunkID)
        return await self.chunk_storage.set_chunk(chunk_id, block)

    async def clear_chunk(self, chunk_id: ChunkID, miss_ok: bool = False) -> None:
        assert isinstance(chunk_id, ChunkID)
        try:
            await self.chunk_storage.clear_chunk(chunk_id)
        except FSLocalMissError:
            if not miss_ok:
                raise

    # Pattern filter interface

    def get_pattern_filter(self) -> Pattern:
        assert self._pattern_filter is not None
        return self._pattern_filter

    def get_pattern_filter_fully_applied(self) -> bool:
        return self._pattern_filter_fully_applied


class WorkspaceStorage(BaseWorkspaceStorage):
    """Manage the access to the local storage.

    That includes:
    - a cache in memory for fast access to deserialized data
    - the persistent storage to keep serialized data on the disk
    - a lock mecanism to protect against race conditions
    """

    def __init__(
        self,
        device: LocalDevice,
        path: Path,
        workspace_id: EntryID,
        data_localdb: LocalDatabase,
        cache_localdb: LocalDatabase,
        block_storage: ChunkStorage,
        chunk_storage: ChunkStorage,
        manifest_storage: ManifestStorage,
    ):
        super().__init__(device, path, workspace_id, block_storage, chunk_storage)
        self.data_localdb = data_localdb
        self.cache_localdb = cache_localdb
        self.manifest_storage = manifest_storage

    @classmethod
    @asynccontextmanager
    async def run(
        cls,
        device: LocalDevice,
        path: Path,
        workspace_id: EntryID,
        cache_size=DEFAULT_BLOCK_CACHE_SIZE,
        vacuum_threshold=DEFAULT_CHUNK_VACUUM_THRESHOLD,
    ):
        data_path = path / WORKSPACE_DATA_STORAGE_NAME
        cache_path = path / WORKSPACE_CACHE_STORAGE_NAME

        # Local cache storage service
        async with LocalDatabase.run(cache_path) as cache_localdb:

            # Local data storage service
            async with LocalDatabase.run(
                data_path, vacuum_threshold=vacuum_threshold
            ) as data_localdb:

                # Block storage service
                async with BlockStorage.run(
                    device, cache_localdb, cache_size=cache_size
                ) as block_storage:

                    # Manifest storage service
                    async with ManifestStorage.run(
                        device, data_localdb, workspace_id
                    ) as manifest_storage:

                        # Chunk storage service
                        async with ChunkStorage.run(device, data_localdb) as chunk_storage:

                            # Instanciate workspace storage
                            instance = cls(
                                device,
                                path,
                                workspace_id,
                                data_localdb=data_localdb,
                                cache_localdb=cache_localdb,
                                block_storage=block_storage,
                                chunk_storage=chunk_storage,
                                manifest_storage=manifest_storage,
                            )

                            # Load pattern filter
                            await instance._load_pattern_filter()

                            # Yield point
                            yield instance

    # Helpers

    async def clear_memory_cache(self, flush=True) -> None:
        await self.manifest_storage.clear_memory_cache(flush=flush)

    # Checkpoint interface

    async def get_realm_checkpoint(self) -> int:
        return await self.manifest_storage.get_realm_checkpoint()

    async def update_realm_checkpoint(
        self, new_checkpoint: int, changed_vlobs: Dict[EntryID, int]
    ) -> None:
        """
        Raises: Nothing !
        """
        await self.manifest_storage.update_realm_checkpoint(new_checkpoint, changed_vlobs)

    async def get_need_sync_entries(self) -> Tuple[Set[EntryID], Set[EntryID]]:
        return await self.manifest_storage.get_need_sync_entries()

    # Manifest interface

    async def get_manifest(self, entry_id: EntryID) -> BaseLocalManifest:
        """Raises: FSLocalMissError"""
        return await self.manifest_storage.get_manifest(entry_id)

    async def set_manifest(
        self,
        entry_id: EntryID,
        manifest: BaseLocalManifest,
        cache_only: bool = False,
        check_lock_status: bool = True,
        removed_ids: Optional[Set[Union[BlockID, ChunkID]]] = None,
    ) -> None:
        if check_lock_status:
            self._check_lock_status(entry_id)
        await self.manifest_storage.set_manifest(
            entry_id, manifest, cache_only=cache_only, removed_ids=removed_ids
        )

    async def ensure_manifest_persistent(self, entry_id: EntryID) -> None:
        self._check_lock_status(entry_id)
        await self.manifest_storage.ensure_manifest_persistent(entry_id)

    async def clear_manifest(self, entry_id: EntryID) -> None:
        self._check_lock_status(entry_id)
        await self.manifest_storage.clear_manifest(entry_id)

    # Pattern filter interface

    async def _load_pattern_filter(self) -> None:
        (
            self._pattern_filter,
            self._pattern_filter_fully_applied,
        ) = await self.manifest_storage.get_pattern_filter()

    async def set_pattern_filter(self, pattern: Pattern) -> None:
        await self.manifest_storage.set_pattern_filter(pattern)
        await self._load_pattern_filter()

    async def set_pattern_filter_fully_applied(self, pattern: Pattern):
        await self.manifest_storage.set_pattern_filter_fully_applied(pattern)
        await self._load_pattern_filter()

    # Vacuum

    async def run_vacuum(self) -> None:
        # Only the data storage needs to get vacuuumed
        await self.data_localdb.run_vacuum()

    # Timestamped workspace

    def to_timestamped(self, timestamp: Pendulum) -> "WorkspaceStorageTimestamped":
        return WorkspaceStorageTimestamped(self, timestamp)


class WorkspaceStorageTimestamped(BaseWorkspaceStorage):
    """Timestamped version to access a local storage as it was at a given timestamp

    That includes:
    - another cache in memory for fast access to deserialized data
    - the timestamped persistent storage to keep serialized data on the disk :
      vlobs are in common, not manifests. Actually only vlobs are used, manifests are mocked
    - the same lock mecanism to protect against race conditions, although it is useless there
    """

    def __init__(self, workspace_storage: BaseWorkspaceStorage, timestamp: Pendulum):
        super().__init__(
            workspace_storage.device,
            workspace_storage.path,
            workspace_storage.workspace_id,
            block_storage=workspace_storage.block_storage,
            chunk_storage=workspace_storage.chunk_storage,
        )

        self._cache: Dict[EntryID, BaseLocalManifest] = {}
        self.timestamp = timestamp
        self.manifest_storage = None

        self._pattern_filter = workspace_storage._pattern_filter
        self._pattern_filter_fully_applied = workspace_storage._pattern_filter_fully_applied

    async def set_chunk(self, chunk_id: ChunkID, block: bytes) -> NoReturn:
        self._throw_permission_error()

    async def clear_chunk(self, chunk_id: ChunkID, miss_ok: bool = False) -> NoReturn:
        self._throw_permission_error()

    async def clear_manifest(self, entry_id: EntryID) -> NoReturn:
        self._throw_permission_error()

    async def run_vacuum(self) -> NoReturn:
        self._throw_permission_error()

    async def get_need_sync_entries(self) -> NoReturn:
        self._throw_permission_error()

    async def get_realm_checkpoint(self) -> NoReturn:
        self._throw_permission_error()

    async def clear_memory_cache(self, flush=True) -> NoReturn:
        self._throw_permission_error()

    async def update_realm_checkpoint(
        self, new_checkpoint: int, changed_vlobs: Dict[EntryID, int]
    ) -> NoReturn:
        self._throw_permission_error()

    def _throw_permission_error(*args, **kwargs) -> NoReturn:
        raise FSError("Not implemented : WorkspaceStorage is timestamped")

    # Manifest interface

    async def get_manifest(self, entry_id: EntryID) -> BaseLocalManifest:
        """Raises: FSLocalMissError"""
        assert isinstance(entry_id, EntryID)
        try:
            return self._cache[entry_id]
        except KeyError:
            raise FSLocalMissError(entry_id)

    async def set_manifest(
        self, entry_id: EntryID, manifest: BaseLocalManifest, cache_only: bool = False
    ) -> None:  # initially for clean
        assert isinstance(entry_id, EntryID)
        if manifest.need_sync:
            self._throw_permission_error()
        self._check_lock_status(entry_id)
        self._cache[entry_id] = manifest

    async def ensure_manifest_persistent(self, entry_id: EntryID) -> None:
        pass

    def to_timestamped(self, timestamp: Pendulum) -> "WorkspaceStorageTimestamped":
        return WorkspaceStorageTimestamped(self, timestamp)
