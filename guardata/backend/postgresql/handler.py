# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import trio
import attr
import re
from pendulum import now as pendulum_now
import triopg
from typing import List, Tuple, Optional

from triopg import UniqueViolationError, UndefinedTableError, PostgresError
from uuid import uuid4
from functools import wraps
from structlog import get_logger
from base64 import b64decode, b64encode
import importlib_resources

from guardata.event_bus import EventBus
from guardata.serde import packb, unpackb
from guardata.utils import start_task, TaskStatus
from guardata.backend.postgresql.utils import (
    STR_TO_REALM_ROLE,
    STR_TO_INVITATION_STATUS,
    STR_TO_BACKEND_EVENTS,
)
from guardata.backend.postgresql import migrations as migrations_module
from guardata.backend.backend_events import BackendEvent


logger = get_logger()

CREATE_MIGRATION_TABLE_ID = 2
MIGRATION_FILE_PATTERN = r"^(?P<id>\d{4})_(?P<name>\w*).sql$"


async def retry_postgres(function, *args, **kwargs):
    postgres_initial_connect_failed = False
    tries_number = kwargs["tries_number"]
    tries_sleep = kwargs["tries_sleep"]
    kwargs = {k: v for k, v in kwargs.items() if k not in ["tries_number", "tries_sleep"]}
    while True:
        try:
            return await function(
                *args, **kwargs, postgres_initial_connect_failed=postgres_initial_connect_failed
            )

        except OSError:
            postgres_initial_connect_failed = True
            if tries_number == 1:
                logger.error("initial db connection failed", tries_remaining=0)
                raise
            if tries_number > 1:
                tries_number -= 1
            logger.warning(
                "initial db connection failed",
                tries_remaining=tries_number if tries_number else "unlimited",
                wait_time=tries_sleep,
            )
            await trio.sleep(tries_sleep)


@attr.s(slots=True, auto_attribs=True)
class MigrationItem:
    idx: int
    name: str
    file_name: str
    sql: str


def retrieve_migrations() -> List[MigrationItem]:
    migrations = []
    ids = []
    for file_name in importlib_resources.contents(migrations_module):
        match = re.search(MIGRATION_FILE_PATTERN, file_name)
        if match:
            idx = int(match.group("id"))
            # Sanity check
            if idx in ids:
                raise AssertionError(
                    f"Inconsistent package (multiples migrations with {idx} as id)"
                )
            ids.append(idx)
            sql = importlib_resources.read_text(migrations_module, file_name)
            if not sql:
                raise AssertionError(f"Empty migration file {file_name}")
            migrations.append(
                MigrationItem(idx=idx, name=match.group("name"), file_name=file_name, sql=sql)
            )

    return sorted(migrations, key=lambda item: item.idx)


@attr.s(slots=True, auto_attribs=True)
class MigrationResult:
    already_applied: List[MigrationItem]
    new_apply: List[MigrationItem]
    error: Optional[Tuple[MigrationItem, str]]


async def apply_migrations(
    url: str,
    first_tries_number: int,
    first_tries_sleep: int,
    migrations: List[MigrationItem],
    dry_run: bool,
) -> MigrationResult:
    """
    Returns: MigrationResult
    """

    async def _retryable(url, migrations, dry_run, postgres_initial_connect_failed=False):
        async with triopg.connect(url) as conn:
            if postgres_initial_connect_failed:
                logger.warning("db connection established after initial failure")
            return await _apply_migrations(conn, migrations, dry_run)

    return await retry_postgres(
        _retryable,
        url,
        migrations,
        dry_run,
        tries_number=first_tries_number,
        tries_sleep=first_tries_sleep,
    )


async def _apply_migrations(
    conn, migrations: Tuple[MigrationItem], dry_run: bool
) -> MigrationResult:
    error = None
    already_applied = []
    new_apply = []

    idx_limit = await _idx_limit(conn)
    for migration in migrations:
        if migration.idx <= idx_limit:
            already_applied.append(migration)
        else:
            if not dry_run:
                try:
                    await _apply_migration(conn, migration)
                except PostgresError as e:
                    error = (migration, e.message)
                    break
            new_apply.append(migration)

    return MigrationResult(already_applied=already_applied, new_apply=new_apply, error=error)


async def _apply_migration(conn, migration: MigrationItem):
    async with conn.transaction():
        await conn.execute(migration.sql)
        if migration.idx >= CREATE_MIGRATION_TABLE_ID:
            # The migration table is created in the second migration
            sql = "INSERT INTO migration (_id, name, applied) VALUES ($1, $2, $3)"
            await conn.execute(sql, migration.idx, migration.name, pendulum_now())


async def _last_migration_row(conn):
    query = "SELECT _id FROM migration ORDER BY applied desc LIMIT 1"
    return await conn.fetchval(query)


async def _is_initial_migration_applied(conn):
    query = "SELECT _id FROM organization LIMIT 1"
    try:
        await conn.fetchval(query)
    except UndefinedTableError:
        return False
    else:
        return True


async def _idx_limit(conn):
    idx_limit = 0
    try:
        idx_limit = await _last_migration_row(conn)
    except UndefinedTableError:
        # The migration table is created in the second migration
        if await _is_initial_migration_applied(conn):
            # The initial table may be created before the migrate command with the old way
            idx_limit = 1
    return idx_limit


def retry_on_unique_violation(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        while True:
            try:
                return await fn(*args, **kwargs)
            except UniqueViolationError as exc:
                logger.warning("unique violation error, retrying...", exc_info=exc)

    return wrapper


# TODO: replace by a fonction
class PGHandler:
    def __init__(
        self,
        url: str,
        min_connections: int,
        max_connections: int,
        first_tries_number: int,
        first_tries_sleep: int,
        event_bus: EventBus,
    ):
        self.url = url
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.first_tries_number = first_tries_number
        self.first_tries_sleep = first_tries_sleep
        self.event_bus = event_bus
        self.pool: triopg.TrioPoolProxy
        self.notification_conn: triopg.TrioConnectionProxy
        self._task_status: Optional[TaskStatus] = None

    async def init(self, nursery):
        self._task_status = await start_task(nursery, self._run_connections)

    async def _run_connections(self, task_status=trio.TASK_STATUS_IGNORED):
        async def _retryable(self, task_status, postgres_initial_connect_failed=False):
            async with triopg.create_pool(
                self.url, min_size=self.min_connections, max_size=self.max_connections
            ) as self.pool:
                # This connection is dedicated to the notifications listening, so it
                # would only complicate stuff to include it into the connection pool
                async with triopg.connect(self.url) as self.notification_conn:
                    await self.notification_conn.add_listener(
                        "app_notification", self._on_notification
                    )
                    task_status.started()
                    if postgres_initial_connect_failed:
                        logger.warning("db connection established after initial failure")
                    await trio.sleep_forever()

        await retry_postgres(
            _retryable,
            self,
            task_status,
            tries_number=self.first_tries_number,
            tries_sleep=self.first_tries_sleep,
        )

    def _on_notification(self, connection, pid, channel, payload):
        data = unpackb(b64decode(payload.encode("ascii")))
        data.pop("__id__")  # Simply discard the notification id
        signal = data.pop("__signal__")
        logger.debug("notif received", pid=pid, channel=channel, payload=payload)
        # Convert strings to enums
        signal = STR_TO_BACKEND_EVENTS[signal]
        # Kind of a hack, but fine enough for the moment
        if signal == BackendEvent.REALM_ROLES_UPDATED:
            data["role"] = STR_TO_REALM_ROLE.get(data.pop("role_str"))
        elif signal == BackendEvent.INVITE_STATUS_CHANGED:
            data["status"] = STR_TO_INVITATION_STATUS.get(data.pop("status_str"))
        self.event_bus.send(signal, **data)

    async def teardown(self):
        if self._task_status:
            await self._task_status.cancel_and_join()


async def send_signal(conn, signal, **kwargs):
    # PostgreSQL's NOTIFY only accept string as payload, hence we must
    # use base64 on our payload...

    # Add UUID to ensure the payload is unique given it seems Postgresql can
    # drop duplicated NOTIFY (same channel/payload)
    # see: https://github.com/Scille/parsec-cloud/issues/199
    raw_data = b64encode(
        packb({"__id__": uuid4().hex, "__signal__": signal.value, **kwargs})
    ).decode("ascii")
    await conn.execute("SELECT pg_notify($1, $2)", "app_notification", raw_data)
    logger.debug("notif sent", signal=signal, kwargs=kwargs)