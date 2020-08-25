# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import trio
from async_generator import asynccontextmanager

from guardata.event_bus import EventBus
from backendService.config import BackendConfig
from backendService.events import EventsComponent
from backendService.blockstore import blockstore_factory
from backendService.webhooks import WebhooksComponent
from backendService.http import HTTPComponent
from backendService.postgresql.handler import PGHandler
from backendService.postgresql.organization import PGOrganizationComponent
from backendService.postgresql.ping import PGPingComponent
from backendService.postgresql.user import PGUserComponent
from backendService.postgresql.invite import PGInviteComponent
from backendService.postgresql.message import PGMessageComponent
from backendService.postgresql.realm import PGRealmComponent
from backendService.postgresql.vlob import PGVlobComponent
from backendService.postgresql.block import PGBlockComponent


@asynccontextmanager
async def components_factory(config: BackendConfig, event_bus: EventBus):
    dbh = PGHandler(
        config.db_url,
        config.db_min_connections,
        config.db_max_connections,
        config.db_first_tries_number,
        config.db_first_tries_sleep,
        event_bus,
    )

    webhooks = WebhooksComponent(config)
    organization = PGOrganizationComponent(dbh, webhooks)
    http = HTTPComponent(config, organization)
    user = PGUserComponent(dbh, event_bus)
    invite = PGInviteComponent(dbh, event_bus, config)
    message = PGMessageComponent(dbh)
    realm = PGRealmComponent(dbh)
    vlob = PGVlobComponent(dbh)
    ping = PGPingComponent(dbh)
    blockstore = blockstore_factory(config.blockstore_config, postgresql_dbh=dbh)
    block = PGBlockComponent(dbh, blockstore, vlob)
    events = EventsComponent(realm)

    async with trio.open_service_nursery() as nursery:
        await dbh.init(nursery)
        try:
            yield {
                "events": events,
                "webhooks": webhooks,
                "http": http,
                "organization": organization,
                "user": user,
                "invite": invite,
                "message": message,
                "realm": realm,
                "vlob": vlob,
                "ping": ping,
                "block": block,
                "blockstore": blockstore,
            }

        finally:
            await dbh.teardown()
