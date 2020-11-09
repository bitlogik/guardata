# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from typing import Iterator

import trio
import outcome
from async_generator import asynccontextmanager
from sqlite3 import OperationalError, connect as sqlite_connect

from guardata.client.fs.exceptions import FSLocalStorageClosedError, FSLocalStorageOperationalError


@asynccontextmanager
async def thread_pool_runner(max_workers=None):
    """A trio-managed thread pool.

    This should be removed if trio decides to add support for thread pools:
    https://github.com/python-trio/trio/blob/c5497c5ac4/trio/_threads.py#L32-L128
    """
    executor = ThreadPoolExecutor(max_workers=max_workers)
    trio_token = trio.lowlevel.current_trio_token()

    async def run_in_thread(fn, *args):
        send_channel, receive_channel = trio.open_memory_channel(1)

        def target():
            result = outcome.capture(fn, *args)
            trio.from_thread.run_sync(send_channel.send_nowait, result, trio_token=trio_token)

        executor.submit(target)
        result = await receive_channel.receive()
        return result.unwrap()

    # The thread pool executor cannot be used as a sync context here, as it would
    # block the trio loop. Instead, we shut the executor down in a worker thread.
    try:
        yield run_in_thread
    finally:
        with trio.CancelScope(shield=True):
            await trio.to_thread.run_sync(executor.shutdown)


class LocalDatabase:
    """Base class for managing an sqlite3 connection."""

    def __init__(self, path, vacuum_threshold=None):
        self._conn = None
        self._lock = trio.Lock()
        self._run_in_thread = None

        self.path = trio.Path(path)
        self.vacuum_threshold = vacuum_threshold

    @classmethod
    @asynccontextmanager
    async def run(cls, *args, **kwargs):
        # Instanciate the local database
        self = cls(*args, **kwargs)

        # Run a pool with single worker thread
        # (although the lock already protects against concurrent access to the pool)
        async with thread_pool_runner(max_workers=1) as self._run_in_thread:

            # Create the connection to the sqlite database
            try:
                await self._connect()

                # Yield the instance
                yield self

            # Safely flush and close the connection
            finally:
                with trio.CancelScope(shield=True):
                    try:
                        await self._close()
                    except FSLocalStorageClosedError:
                        pass

    # Operational error protection

    @contextmanager
    def _manage_operational_error(self, allow_commit: bool = False) -> Iterator[None]:
        """Close the local database when an operational error is detected.
        Operational errors have to be treated with care since they usually indicate
        that the current transaction has been rolled back. Since guardata has its own
        in-memory cache for manifests, this can lead to complicated bugs and possibly
        database corruptions, in the sense that a committed manifest might reference a
        chunk of data that has not been successfully committed.
        If an operational error is detected it simply closes the connection and invalidates
        the local database object while raising an FSLocalStorageOperationalError exception.
        This way, it forces the core to create some new workspace storage objects and
        therefore discarding any uncommited data.
        """
        in_transaction_before = self._conn.in_transaction
        # Safe context for operational errors
        try:
            try:
                yield

            # Extra checks for end of transaction
            finally:
                end_of_transaction_detected = (
                    in_transaction_before and not self._conn.in_transaction
                )
                if not allow_commit and end_of_transaction_detected:
                    raise OperationalError("A forbidden commit/rollback has been detected")

        # An operational error has been detected
        except OperationalError as exception:

            # Close the sqlite3 connection
            try:
                self._conn.close()

            # Ignore second operational error (it should not happen though)
            except OperationalError:
                pass

            # Mark the local database as closed
            finally:
                del self._conn

            # Raise the dedicated operational error
            raise FSLocalStorageOperationalError from exception

    # Life cycle

    async def _create_connection(self):
        # Create directories
        await self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Create sqlite connection
        self._conn = sqlite_connect(str(self.path), check_same_thread=False)

        # The default isolation level ("") lets python manage the transaction
        # so we can periodically commit the pending changes.
        assert self._conn.isolation_level == ""

        # The combination of WAL journal mode and NORMAL synchronous mode
        # is a great combination: it allows for fast commits (~10 us compare
        # to 15 ms the default mode) but still protects the database against
        # corruption in the case of OS crash or power failure.
        with self._manage_operational_error():
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")

    async def _connect(self):
        async with self._lock:
            # Connect and initialize database
            await self._create_connection()

    async def _close(self):
        async with self._lock:

            # Local database is already closed
            if self._is_closed():
                return

            # Commit the current transaction
            try:
                await self._commit()

            finally:
                # Local database is already closed
                if self._is_closed():
                    return

                # Close the sqlite3 connection
                try:
                    self._conn.close()

                # Mark the local database as closed
                finally:
                    del self._conn

    async def _commit(self) -> None:
        # Close the local database if an operational error is detected
        with self._manage_operational_error(allow_commit=True):
            await self._run_in_thread(self._conn.commit)

    def _is_closed(self) -> bool:
        return not hasattr(self, "_conn")

    def _check_open(self) -> None:
        if self._is_closed():
            raise FSLocalStorageClosedError

    # Cursor management

    @asynccontextmanager
    async def open_cursor(self, commit=True):
        async with self._lock:
            # Check connection state
            self._check_open()

            # Close the local database if an operational error is detected
            with self._manage_operational_error():

                # Execute SQL commands
                cursor = self._conn.cursor()
                try:
                    yield cursor
                finally:
                    cursor.close()

            # Commit the transaction when finished
            if commit and self._conn.in_transaction:
                await self._commit()

    async def commit(self):
        async with self._lock:
            await self._commit()

    # Vacuum

    async def get_disk_usage(self):
        disk_usage = 0
        for suffix in (".sqlite", ".sqlite-wal", ".sqlite-shm"):
            try:
                stat = await self.path.with_suffix(suffix).stat()
            except OSError:
                pass
            else:
                disk_usage += stat.st_size
        return disk_usage

    async def run_vacuum(self):
        async with self._lock:

            # Check connection state
            self._check_open()

            # Vacuum disabled
            if self.vacuum_threshold is None:
                return

            # Flush to disk before computing disk usage
            await self._commit()

            # No reason to vacuum yet
            if await self.get_disk_usage() < self.vacuum_threshold:
                return

            # Run vacuum
            await self._run_in_thread(self._conn.execute, "VACUUM")

            # The connection needs to be recreated
            try:
                self._conn.close()
            finally:
                await self._create_connection()
