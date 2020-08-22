# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import trio
import math
from async_generator import asynccontextmanager

from guardata.event_bus import EventBus
from backendService.config import BackendConfig
from backendService.blockstore import blockstore_factory
from backendService.events import EventsComponent
from backendService.memory.organization import MemoryOrganizationComponent
from backendService.memory.ping import MemoryPingComponent
from backendService.memory.user import MemoryUserComponent
from backendService.memory.invite import MemoryInviteComponent
from backendService.memory.message import MemoryMessageComponent
from backendService.memory.realm import MemoryRealmComponent
from backendService.memory.vlob import MemoryVlobComponent
from backendService.memory.block import MemoryBlockComponent
from backendService.webhooks import WebhooksComponent
from backendService.http import HTTPComponent


@asynccontextmanager
async def components_factory(config: BackendConfig, event_bus: EventBus):
    (send_events_channel, receive_events_channel) = trio.open_memory_channel(math.inf)

    async def _send_event(event: str, **kwargs):
        await send_events_channel.send((event, kwargs))

    async def _dispatch_event():
        async for event, kwargs in receive_events_channel:
            await trio.sleep(0)
            event_bus.send(event, **kwargs)

    webhooks = WebhooksComponent(config)
    http = HTTPComponent(config)
    organization = MemoryOrganizationComponent(webhooks)
    user = MemoryUserComponent(_send_event, event_bus)
    invite = MemoryInviteComponent(_send_event, event_bus, config)
    message = MemoryMessageComponent(_send_event)
    realm = MemoryRealmComponent(_send_event)
    vlob = MemoryVlobComponent(_send_event)
    ping = MemoryPingComponent(_send_event)
    block = MemoryBlockComponent()
    blockstore = blockstore_factory(config.blockstore_config)
    events = EventsComponent(realm)

    components = {
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
    for component in (organization, user, invite, message, realm, vlob, ping, block):
        component.register_components(**components)

    async with trio.open_service_nursery() as nursery:
        nursery.start_soon(_dispatch_event)
        try:
            yield components

        finally:
            nursery.cancel_scope.cancel()
