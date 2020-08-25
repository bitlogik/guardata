# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import trio
from async_generator import asynccontextmanager
from typing import Optional, AsyncGenerator

from guardata.api.protocol import INVITED_CMDS
from guardata.client.types import BackendInvitationAddr
from guardata.client.backend_connection.transport import connect_as_invited
from guardata.client.backend_connection.exceptions import BackendNotAvailable
from guardata.client.backend_connection.expose_cmds import expose_cmds


class BackendInvitedCmds:
    def __init__(self, addr, acquire_transport):
        self.addr = addr
        self.acquire_transport = acquire_transport

    for cmd_name in INVITED_CMDS:
        vars()[cmd_name] = expose_cmds(cmd_name)


@asynccontextmanager
async def backend_invited_cmds_factory(
    addr: BackendInvitationAddr, keepalive: Optional[int] = None
) -> AsyncGenerator[BackendInvitedCmds, None]:
    """
    Raises:
        BackendConnectionError
    """
    transport_lock = trio.Lock()
    transport = None
    closed = False

    async def _init_transport():
        nonlocal transport
        if not transport:
            if closed:
                raise trio.ClosedResourceError
            transport = await connect_as_invited(addr, keepalive=keepalive)
            transport.logger = transport.logger.bind(auth="<invited>")

    async def _destroy_transport():
        nonlocal transport
        if transport:
            await transport.aclose()
            transport = None

    @asynccontextmanager
    async def _acquire_transport(**kwargs):
        nonlocal transport

        async with transport_lock:
            await _init_transport()
            try:
                yield transport
            except BackendNotAvailable:
                await _destroy_transport()
                raise

    try:
        yield BackendInvitedCmds(addr, _acquire_transport)

    finally:
        async with transport_lock:
            closed = True
            await _destroy_transport()
