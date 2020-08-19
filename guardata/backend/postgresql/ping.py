# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from guardata.backend.backend_events import BackendEvent
from guardata.api.protocol import DeviceID, OrganizationID
from guardata.backend.ping import BasePingComponent
from guardata.backend.postgresql.handler import send_signal, PGHandler


class PGPingComponent(BasePingComponent):
    def __init__(self, dbh: PGHandler):
        self.dbh = dbh

    async def ping(self, organization_id: OrganizationID, author: DeviceID, ping: str) -> None:
        if not author:
            return
        async with self.dbh.pool.acquire() as conn:
            await send_signal(
                conn, BackendEvent.PINGED, organization_id=organization_id, author=author, ping=ping
            )
