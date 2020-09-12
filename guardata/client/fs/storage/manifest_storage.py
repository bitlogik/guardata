# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import re

import trio
from structlog import get_logger
from typing import Dict, Tuple, Set, Optional, Union, Pattern
from async_generator import asynccontextmanager

from guardata.client.fs.exceptions import FSLocalMissError
from guardata.client.types import EntryID, ChunkID, LocalDevice, BaseLocalManifest, BlockID
from guardata.client.fs.storage.local_database import LocalDatabase

logger = get_logger()

EMPTY_PATTERN = r"^/b$"  # Do not match anything


class ManifestStorage:
    """Persistent storage with cache for storing manifests.

    Also stores the checkpoint.
    """

    def __init__(self, device: LocalDevice, localdb: LocalDatabase, realm_id: EntryID):
        self.device = device
        self.localdb = localdb
        self.realm_id = realm_id

        # This cache contains all the manifests that have been set or accessed
        # since the last call to `clear_memory_cache`
        self._cache: Dict[EntryID, BaseLocalManifest] = {}

        # This dictionnary keeps track of all the entry ids of the manifests
        # that have been added to the cache but still needs to be written to
        # the localdb. The corresponding value is a set with the ids of all
        # the chunks that needs to be removed from the localdb after the
        # manifest is written. Note: this set might be empty but the manifest
        # still requires to be flushed.
        self._cache_ahead_of_localdb: Dict[EntryID, Set[Union[ChunkID, BlockID]]] = {}

    @property
    def path(self):
        return self.localdb.path

    @classmethod
    @asynccontextmanager
    async def run(cls, *args, **kwargs):
        self = cls(*args, **kwargs)
        await self._create_db()
        try:
            yield self
        finally:
            with trio.CancelScope(shield=True):
                await self._flush_cache_ahead_of_persistance()

    def _open_cursor(self):
        # We want the manifest to be written to the disk as soon as possible
        # (unless they are purposely kept out of the local database)
        return self.localdb.open_cursor(commit=True)

    async def clear_memory_cache(self, flush=True):
        if flush:
            await self._flush_cache_ahead_of_persistance()
        self._cache_ahead_of_localdb.clear()
        self._cache.clear()

    # Database initialization

    async def _create_db(self):
        async with self._open_cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS vlobs
                (
                  vlob_id BLOB PRIMARY KEY NOT NULL, -- UUID
                  base_version INTEGER NOT NULL,
                  remote_version INTEGER NOT NULL,
                  need_sync INTEGER NOT NULL,  -- Boolean
                  blob BLOB NOT NULL
                );
                """
            )

            # Singleton storing the checkpoint
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS realm_checkpoint
                (
                  _id INTEGER PRIMARY KEY NOT NULL,
                  checkpoint INTEGER NOT NULL
                );
                """
            )
            # Singleton storing the pattern_filter
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pattern_filter
                (
                  _id INTEGER PRIMARY KEY NOT NULL,
                  pattern TEXT NOT NULL,
                  fully_applied INTEGER NOT NULL  -- Boolean
                );
                """
            )
            # Set the default pattern filter if it doesn't exist
            cursor.execute(
                """
                INSERT OR IGNORE INTO pattern_filter(_id, pattern, fully_applied)
                VALUES (0, ?, 0)""",
                (EMPTY_PATTERN,),
            )

    # Pattern filter operations

    async def get_pattern_filter(self) -> Tuple[Pattern, bool]:
        async with self._open_cursor() as cursor:
            cursor.execute("SELECT pattern, fully_applied FROM pattern_filter WHERE _id = 0")
            reply = cursor.fetchone()
            pattern, fully_applied = reply
            return (re.compile(pattern), bool(fully_applied))

    async def set_pattern_filter(self, pattern: Pattern):
        async with self._open_cursor() as cursor:
            cursor.execute(
                """UPDATE pattern_filter SET pattern = ?, fully_applied = 0 WHERE _id = 0 AND pattern != ?""",
                (pattern.pattern, pattern.pattern),
            )

    async def set_pattern_filter_fully_applied(self, pattern):
        async with self._open_cursor() as cursor:
            cursor.execute(
                """UPDATE pattern_filter SET fully_applied = 1 WHERE _id = 0 AND pattern = ?""",
                (pattern.pattern,),
            )

    # Checkpoint operations

    async def get_realm_checkpoint(self) -> int:
        """
        Raises: Nothing !
        """
        async with self._open_cursor() as cursor:
            cursor.execute("SELECT checkpoint FROM realm_checkpoint WHERE _id = 0")
            rep = cursor.fetchone()
            return rep[0] if rep else 0

    async def update_realm_checkpoint(
        self, new_checkpoint: int, changed_vlobs: Dict[EntryID, int]
    ) -> None:
        """
        Raises: Nothing !
        """
        async with self._open_cursor() as cursor:
            cursor.executemany(
                "UPDATE vlobs SET remote_version = ? WHERE vlob_id = ?",
                ((version, entry_id.bytes) for entry_id, version in changed_vlobs.items()),
            )
            cursor.execute(
                """INSERT OR REPLACE INTO realm_checkpoint(_id, checkpoint)
                VALUES (0, ?)""",
                (new_checkpoint,),
            )

    async def get_need_sync_entries(self) -> Tuple[Set[EntryID], Set[EntryID]]:
        """
        Raises: Nothing !
        """
        remote_changes = set()
        local_changes = {
            entry_id for entry_id, manifest in self._cache.items() if manifest.need_sync
        }

        async with self._open_cursor() as cursor:
            cursor.execute(
                "SELECT vlob_id, need_sync, base_version, remote_version "
                "FROM vlobs WHERE need_sync = 1 OR base_version != remote_version"
            )
            for manifest_id, need_sync, bv, rv in cursor.fetchall():
                manifest_id = EntryID(manifest_id)
                if need_sync:
                    local_changes.add(manifest_id)
                if bv != rv:
                    remote_changes.add(manifest_id)
            return local_changes, remote_changes

    # Manifest operations

    async def get_manifest(self, entry_id: EntryID) -> BaseLocalManifest:
        """
        Raises:
            FSLocalMissError
        """
        # Look in cache first
        try:
            return self._cache[entry_id]
        except KeyError:
            pass

        # Look into the database
        async with self._open_cursor() as cursor:
            cursor.execute("SELECT blob FROM vlobs WHERE vlob_id = ?", (entry_id.bytes,))
            manifest_row = cursor.fetchone()

        # Not found
        if not manifest_row:
            raise FSLocalMissError(entry_id)

        # Safely fill the cache
        if entry_id not in self._cache:
            self._cache[entry_id] = BaseLocalManifest.decrypt_and_load(
                manifest_row[0], key=self.device.local_symkey
            )

        # Always return the cached value
        return self._cache[entry_id]

    async def set_manifest(
        self,
        entry_id: EntryID,
        manifest: BaseLocalManifest,
        cache_only: bool = False,
        removed_ids: Optional[Set[Union[ChunkID, BlockID]]] = None,
    ) -> None:
        """
        Raises: Nothing !
        """
        assert isinstance(entry_id, EntryID)

        # Set the cache first
        self._cache[entry_id] = manifest

        # Tag the entry as ahead of localdb
        self._cache_ahead_of_localdb.setdefault(entry_id, set())

        # Cleanup
        if removed_ids:
            self._cache_ahead_of_localdb[entry_id] |= removed_ids

        # Flush the cached value to the localdb
        if not cache_only:
            await self._ensure_manifest_persistent(entry_id)

    async def _ensure_manifest_persistent(self, entry_id: EntryID) -> None:

        # Get cursor
        async with self._open_cursor() as cursor:

            # Flushing is not necessary
            if entry_id not in self._cache_ahead_of_localdb:
                return

            # Safely get the manifest
            manifest = self._cache[entry_id]

            # Dump and decrypt the manifest
            ciphered = manifest.dump_and_encrypt(self.device.local_symkey)

            # Insert into the local database
            cursor.execute(
                """INSERT OR REPLACE INTO vlobs (vlob_id, blob, need_sync, base_version, remote_version)
                VALUES (
                    ?, ?, ?, ?,
                    max(
                        ?,
                        IFNULL((SELECT remote_version FROM vlobs WHERE vlob_id=?), 0)
                    )
                )""",
                (
                    entry_id.bytes,
                    ciphered,
                    manifest.need_sync,
                    manifest.base_version,
                    manifest.base_version,
                    entry_id.bytes,
                ),
            )

            # Clean all the pending chunks
            for chunk_id in self._cache_ahead_of_localdb[entry_id]:
                cursor.execute("DELETE FROM chunks WHERE chunk_id = ?", (chunk_id.bytes,))

            # Safely tag entry as up-to-date
            self._cache_ahead_of_localdb.pop(entry_id)

    async def ensure_manifest_persistent(self, entry_id: EntryID) -> None:
        """
        Raises: Nothing !
        """
        assert isinstance(entry_id, EntryID)
        # Flush if necessary
        if entry_id in self._cache_ahead_of_localdb:
            await self._ensure_manifest_persistent(entry_id)

    async def _flush_cache_ahead_of_persistance(self) -> None:
        # Flush until the all the cache is gone
        while self._cache_ahead_of_localdb:
            entry_id = next(iter(self._cache_ahead_of_localdb))
            await self._ensure_manifest_persistent(entry_id)

    # This method is not used in the code base but it is still tested
    # as it might come handy in a cleanup routine later

    async def clear_manifest(self, entry_id: EntryID) -> None:
        """
        Raises:
            FSLocalMissError
        """

        async with self._open_cursor() as cursor:

            # Safely remove from cache
            in_cache = bool(self._cache.pop(entry_id, None))

            # Remove from local database
            cursor.execute("DELETE FROM vlobs WHERE vlob_id = ?", (entry_id.bytes,))
            cursor.execute("SELECT changes()")
            (deleted,) = cursor.fetchone()

            # Clean all the pending chunks
            # TODO: should also add the content of the popped manifest
            pending_chunk_ids = self._cache_ahead_of_localdb.pop(entry_id, ())
            for chunk_id in pending_chunk_ids:
                cursor.execute("DELETE FROM chunks WHERE chunk_id = ?", (chunk_id.bytes,))

        # Raise a miss if the entry wasn't found
        if not deleted and not in_cache:
            raise FSLocalMissError(entry_id)
