# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import trio
from async_generator import asynccontextmanager

from guardata.event_bus import EventBus
from guardata.backend.config import BackendConfig
from guardata.backend.events import EventsComponent
from guardata.backend.blockstore import blockstore_factory
from guardata.backend.webhooks import WebhooksComponent
from guardata.backend.http import HTTPComponent
from guardata.backend.postgresql.handler import PGHandler
from guardata.backend.postgresql.organization import PGOrganizationComponent
from guardata.backend.postgresql.ping import PGPingComponent
from guardata.backend.postgresql.user import PGUserComponent
from guardata.backend.postgresql.invite import PGInviteComponent
from guardata.backend.postgresql.message import PGMessageComponent
from guardata.backend.postgresql.realm import PGRealmComponent
from guardata.backend.postgresql.vlob import PGVlobComponent
from guardata.backend.postgresql.block import PGBlockComponent


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
