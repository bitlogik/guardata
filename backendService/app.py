# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from typing import Optional
import trio
from structlog import get_logger
from logging import DEBUG as LOG_LEVEL_DEBUG
from async_generator import asynccontextmanager
import h11

from guardata._version import __version__ as guardata_version
from backendService.backend_events import BackendEvent
from guardata.event_bus import EventBus
from guardata.logging import get_log_level
from guardata.api.transport import TransportError, TransportClosedByPeer, Transport
from guardata.api.protocol import (
    packb,
    unpackb,
    ProtocolError,
    MessageSerializationError,
    InvalidMessageError,
    InvitationStatus,
)
from backendService.utils import CancelledByNewRequest, collect_apis
from backendService.config import BackendConfig
from backendService.client_context import AuthenticatedClientContext, InvitedClientContext
from backendService.handshake import do_handshake
from backendService.memory import components_factory as mocked_components_factory
from backendService.postgresql import components_factory as postgresql_components_factory
from backendService.http import HTTPRequest


logger = get_logger()


DISABLE_STRICT_AUTH_CHECK = False


def _filter_binary_fields(data):
    return {k: v if not isinstance(v, bytes) else b"[...]" for k, v in data.items()}


def _get_header(zhds, hkey: bytes) -> bytes:
    if hkey not in zhds:
        return b""
    return zhds[hkey].lower()


@asynccontextmanager
async def backend_app_factory(config: BackendConfig, event_bus: Optional[EventBus] = None):
    event_bus = event_bus or EventBus()

    if config.db_url == "MOCKED":
        components_factory = mocked_components_factory
    else:
        components_factory = postgresql_components_factory

    async with components_factory(config=config, event_bus=event_bus) as components:
        yield BackendApp(
            config=config,
            event_bus=event_bus,
            webhooks=components["webhooks"],
            http=components["http"],
            user=components["user"],
            invite=components["invite"],
            organization=components["organization"],
            message=components["message"],
            realm=components["realm"],
            vlob=components["vlob"],
            ping=components["ping"],
            blockstore=components["blockstore"],
            block=components["block"],
            events=components["events"],
        )


class BackendApp:
    def __init__(
        self,
        config,
        event_bus,
        webhooks,
        http,
        user,
        invite,
        organization,
        message,
        realm,
        vlob,
        ping,
        blockstore,
        block,
        events,
    ):
        self.host_domain = None
        if config.backend_addr:
            if config.backend_addr._hostname:
                self.host_domain = config.backend_addr._hostname.encode("idna")
        self.config = config
        self.event_bus = event_bus

        self.webhooks = webhooks
        self.http = http
        self.user = user
        self.invite = invite
        self.organization = organization
        self.message = message
        self.realm = realm
        self.vlob = vlob
        self.ping = ping
        self.blockstore = blockstore
        self.block = block
        self.events = events

        self.apis = collect_apis(
            user, invite, organization, message, realm, vlob, ping, blockstore, block, events
        )

    async def handle_client_websocket(self, stream, event, first_request_data=None):
        selected_logger = logger

        try:
            transport = await Transport.init_for_server(
                stream, first_request_data=first_request_data
            )

        except TransportClosedByPeer as exc:
            selected_logger.info("Connection dropped: client has left", reason=str(exc))
            return

        except TransportError as exc:
            selected_logger.info("Connection dropped: websocket error", reason=str(exc))
            return

        selected_logger = transport.logger

        try:
            client_ctx, error_infos = await do_handshake(self, transport)
            if not client_ctx:
                # Invalid handshake
                selected_logger.info("Connection dropped: bad handshake", **error_infos)
                return

            selected_logger = client_ctx.logger
            selected_logger.info("Connection established")

            if isinstance(client_ctx, AuthenticatedClientContext):
                with trio.CancelScope() as cancel_scope:
                    with self.event_bus.connection_context() as client_ctx.event_bus_ctx:

                        def _on_revoked(event, organization_id, user_id):
                            if (
                                organization_id == client_ctx.organization_id
                                and user_id == client_ctx.user_id
                            ):
                                cancel_scope.cancel()

                        client_ctx.event_bus_ctx.connect(BackendEvent.USER_REVOKED, _on_revoked)
                        await self._handle_client_loop(transport, client_ctx)

            elif isinstance(client_ctx, InvitedClientContext):
                await self.invite.claimer_joined(
                    organization_id=client_ctx.organization_id,
                    greeter=client_ctx.invitation.greeter_user_id,
                    token=client_ctx.invitation.token,
                )
                try:
                    with trio.CancelScope() as cancel_scope:
                        with self.event_bus.connection_context() as event_bus_ctx:

                            def _on_invite_status_changed(
                                event, organization_id, greeter, token, status
                            ):
                                if (
                                    status == InvitationStatus.DELETED
                                    and organization_id == client_ctx.organization_id
                                    and token == client_ctx.invitation.token
                                ):
                                    cancel_scope.cancel()

                            event_bus_ctx.connect(
                                BackendEvent.INVITE_STATUS_CHANGED, _on_invite_status_changed
                            )
                            await self._handle_client_loop(transport, client_ctx)
                finally:
                    with trio.CancelScope(shield=True):
                        await self.invite.claimer_left(
                            organization_id=client_ctx.organization_id,
                            greeter=client_ctx.invitation.greeter_user_id,
                            token=client_ctx.invitation.token,
                        )

            else:
                await self._handle_client_loop(transport, client_ctx)

            await transport.aclose()

        except TransportClosedByPeer as exc:
            selected_logger.info("Connection dropped: client has left", reason=str(exc))

        except (TransportError, MessageSerializationError) as exc:
            rep = {"status": "invalid_msg_format", "reason": "Invalid message format"}
            try:
                await transport.send(packb(rep))
            except TransportError:
                pass
            await transport.aclose()
            selected_logger.info("Connection dropped: invalid data", reason=str(exc))

    async def handle_client(self, stream):
        MAX_RECV = 1024
        try:
            conn = h11.Connection(h11.SERVER)
            first_request_data = b""

            while True:
                if conn.they_are_waiting_for_100_continue:
                    self.info("Sending 100 Continue")
                    go_ahead = h11.InformationalResponse(
                        status_code=100, headers=self.basic_headers()
                    )
                    await self.send(go_ahead)
                try:
                    data = await stream.receive_some(MAX_RECV)
                    first_request_data += data

                except ConnectionError:
                    # They've stopped listening. Not much we can do about it here.
                    data = b""
                conn.receive_data(data)

                event = conn.next_event()
                if event is not h11.NEED_DATA:
                    break

            if not isinstance(event, h11.Request):
                await stream.aclose()
                return

            # get headers as a dict
            headers = dict(event.headers)

            # Websocket upgrade, else HTTP
            host_rcvd = _get_header(headers, b"host")
            if (
                event.http_version == b"1.1"
                and event.method == b"GET"
                and event.target == b"/ws"
                and _get_header(headers, b"connection") == b"upgrade"
                and _get_header(headers, b"upgrade") == b"websocket"
                and (
                    (len(host_rcvd) > 3 and host_rcvd == self.host_domain)
                    or DISABLE_STRICT_AUTH_CHECK
                )
            ):
                await self.handle_client_websocket(
                    stream, event, first_request_data=first_request_data
                )
            else:
                await self.handle_client_http(stream, event, conn)

        except h11.RemoteProtocolError:
            pass

        finally:
            try:
                await stream.aclose()
            except trio.BrokenResourceError:
                # They're already gone, nothing to do
                pass

    async def handle_client_http(self, stream, event, conn):
        # TODO: right now we handle a single request then close the connection
        # hence HTTP 1.1 keep-alive is not supported
        req = HTTPRequest.from_h11_req(event)
        rep = await self.http.handle_request(req)

        if self.config.debug:
            server_header = f"guardata/{guardata_version} {h11.PRODUCT_ID}"
        else:
            server_header = "guardata"
        rep.headers.append(("server", server_header))
        # Tell no support for keep-alive (h11 will know what to do from there)
        rep.headers.append(("connection", "close"))

        try:
            response_data = bytearray(
                conn.send(
                    h11.Response(
                        status_code=rep.status_code, headers=rep.headers, reason=rep.reason
                    )
                )
            )
            if rep.data:
                response_data += conn.send(h11.Data(data=rep.data))
            response_data += conn.send(h11.EndOfMessage())
            await stream.send_all(response_data)
        except trio.BrokenResourceError:
            # Peer is already gone, nothing to do
            pass

    async def _handle_client_loop(self, transport, client_ctx):
        # Retrieve the allowed commands according to api version and auth type
        api_cmds = self.apis[client_ctx.handshake_type]

        raw_req = None
        while True:
            # raw_req can be already defined if we received a new request
            # while processing a command
            raw_req = raw_req or await transport.recv()
            req = unpackb(raw_req)
            if get_log_level() <= LOG_LEVEL_DEBUG:
                client_ctx.logger.debug("Request", req=_filter_binary_fields(req))
            try:
                cmd = req.get("cmd", "<missing>")
                if not isinstance(cmd, str):
                    raise KeyError()

                cmd_func = api_cmds[cmd]

            except KeyError:
                rep = {"status": "unknown_command", "reason": "Unknown command"}

            else:
                try:
                    rep = await cmd_func(client_ctx, req)

                except InvalidMessageError as exc:
                    rep = {
                        "status": "bad_message",
                        "errors": exc.errors,
                        "reason": "Invalid message.",
                    }

                except ProtocolError as exc:
                    rep = {"status": "bad_message", "reason": str(exc)}

                except CancelledByNewRequest as exc:
                    # Long command handling such as message_get can be cancelled
                    # when the peer send a new request
                    raw_req = exc.new_raw_req
                    continue

            if get_log_level() <= LOG_LEVEL_DEBUG:
                client_ctx.logger.debug("Response", rep=_filter_binary_fields(rep))
            else:
                client_ctx.logger.info("Request", cmd=cmd, status=rep["status"])
            raw_rep = packb(rep)
            await transport.send(raw_rep)
            raw_req = None
