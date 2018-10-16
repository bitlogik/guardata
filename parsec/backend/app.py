import attr
import trio
import logbook
import traceback
from nacl.public import PublicKey
from nacl.signing import VerifyKey
from json import JSONDecodeError

from parsec.event_bus import EventBus
from parsec.utils import ParsecError
from parsec.networking import CookedSocket
from parsec.handshake import HandshakeFormatError, ServerHandshake
from parsec.schema import BaseCmdSchema, fields, OneOfSchema

from parsec.backend.drivers.memory import (
    MemoryUserComponent,
    MemoryVlobComponent,
    MemoryMessageComponent,
    MemoryBlockStoreComponent,
    MemoryBeaconComponent,
)
from parsec.backend.drivers.postgresql import (
    PGHandler,
    PGUserComponent,
    PGVlobComponent,
    PGMessageComponent,
    PGBlockStoreComponent,
    PGBeaconComponent,
)

from parsec.backend.exceptions import NotFoundError


logger = logbook.Logger("parsec.backend.app")


def blockstore_factory(config, postgresql_dbh=None):
    blockstore_type = config.blockstore_type
    if blockstore_type == "MOCKED":
        return MemoryBlockStoreComponent()

    elif blockstore_type == "POSTGRESQL":
        if not postgresql_dbh:
            raise ValueError("PostgreSQL blockstore is not available")
        return PGBlockStoreComponent(postgresql_dbh)

    elif blockstore_type == "S3":
        try:
            from parsec.backend.s3_blockstore import S3BlockStoreComponent

            return S3BlockStoreComponent(
                config.s3_region, config.s3_bucket, config.s3_key, config.s3_secret
            )
        except ImportError:
            raise ValueError("S3 blockstore is not available")

    elif blockstore_type == "SWIFT":
        try:
            from parsec.backend.swift_blockstore import SwiftBlockStoreComponent

            return SwiftBlockStoreComponent(
                config.swift_authurl,
                config.swift_tenant,
                config.swift_container,
                config.swift_user,
                config.swift_password,
            )
        except ImportError:
            raise ValueError("Swift blockstore is not available")

    else:
        raise ValueError(f"Unknown blockstore type `{blockstore_type}`")


class _cmd_PING_Schema(BaseCmdSchema):
    ping = fields.String(required=True)


cmd_PING_Schema = _cmd_PING_Schema()


class _cmd_EVENT_SUBSCRIBE_BeaconUpdatedSchema(BaseCmdSchema):
    event = fields.CheckedConstant("beacon.updated")
    beacon_id = fields.UUID(missing=None)


cmd_EVENT_SUBSCRIBE_BeaconUpdatedSchema = _cmd_EVENT_SUBSCRIBE_BeaconUpdatedSchema()


class _cmd_EVENT_SUBSCRIBE_MessageReceivedSchema(BaseCmdSchema):
    event = fields.CheckedConstant("message.received")


cmd_EVENT_SUBSCRIBE_MessageReceivedSchema = _cmd_EVENT_SUBSCRIBE_MessageReceivedSchema()


class _cmd_EVENT_SUBSCRIBE_DeviceTryclaimSubmittedSchema(BaseCmdSchema):
    event = fields.CheckedConstant("device.try_claim_submitted")


cmd_EVENT_SUBSCRIBE_DeviceTryclaimSubmittedSchema = (
    _cmd_EVENT_SUBSCRIBE_DeviceTryclaimSubmittedSchema()
)


class _cmd_EVENT_SUBSCRIBE_PingedSchema(BaseCmdSchema):
    event = fields.CheckedConstant("pinged")
    ping = fields.String(missing=None)


cmd_EVENT_SUBSCRIBE_PingedSchema = _cmd_EVENT_SUBSCRIBE_PingedSchema()


class _cmd_EVENT_SUBSCRIBE_Schema(BaseCmdSchema, OneOfSchema):
    type_field = "event"
    type_field_remove = False
    type_schemas = {
        "beacon.updated": cmd_EVENT_SUBSCRIBE_BeaconUpdatedSchema,
        "message.received": cmd_EVENT_SUBSCRIBE_MessageReceivedSchema,
        "device.try_claim_submitted": cmd_EVENT_SUBSCRIBE_DeviceTryclaimSubmittedSchema,
        "pinged": cmd_EVENT_SUBSCRIBE_PingedSchema,
    }

    def get_obj_type(self, obj):
        return obj["event"]


cmd_EVENT_SUBSCRIBE_Schema = _cmd_EVENT_SUBSCRIBE_Schema()


class _cmd_EVENT_LISTEN_Schema(BaseCmdSchema):
    wait = fields.Boolean(missing=True)


cmd_EVENT_LISTEN_Schema = _cmd_EVENT_LISTEN_Schema()


cmd_EVENT_LIST_SUBSCRIBED = BaseCmdSchema()


@attr.s
class AnonymousClientContext:
    id = "anonymous"
    anonymous = True


@attr.s
class ClientContext:
    anonymous = False
    id = attr.ib()
    broadcast_key = attr.ib()
    verify_key = attr.ib()
    subscribed_events = attr.ib(default=attr.Factory(dict), init=False)
    events = attr.ib(default=attr.Factory(lambda: trio.Queue(100)), init=False)

    @property
    def user_id(self):
        return self.id.split("@")[0]

    @property
    def device_name(self):
        return self.id.split("@")[1]


class BackendApp:
    def __init__(self, config, event_bus=None):
        self.event_bus = event_bus or EventBus()
        self.config = config
        self.nursery = None
        self.dbh = None

        if self.config.db_url == "MOCKED":
            self.user = MemoryUserComponent(self.event_bus)
            self.message = MemoryMessageComponent(self.event_bus)
            self.beacon = MemoryBeaconComponent(self.event_bus)
            self.vlob = MemoryVlobComponent(self.event_bus, self.beacon)

            self.blockstore = blockstore_factory(self.config)
        else:
            self.dbh = PGHandler(self.config.db_url, self.event_bus)
            self.user = PGUserComponent(self.dbh, self.event_bus)
            self.message = PGMessageComponent(self.dbh, self.event_bus)
            self.beacon = PGBeaconComponent(self.dbh, self.event_bus)
            self.vlob = PGVlobComponent(self.dbh, self.event_bus, self.beacon)

            self.blockstore = blockstore_factory(self.config, postgresql_dbh=self.dbh)

        self.anonymous_cmds = {
            "user_claim": self.user.api_user_claim,
            "device_configure": self.user.api_device_configure,
            "ping": self._api_ping,
        }

        self.cmds = {
            "event_subscribe": self._api_event_subscribe,
            "event_unsubscribe": self._api_event_unsubscribe,
            "event_listen": self._api_event_listen,
            "event_list_subscribed": self._api_event_list_subscribed,
            "user_get": self.user.api_user_get,
            "user_invite": self.user.api_user_invite,
            "device_declare": self.user.api_device_declare,
            "device_get_configuration_try": self.user.api_device_get_configuration_try,
            "device_accept_configuration_try": self.user.api_device_accept_configuration_try,
            "device_refuse_configuration_try": self.user.api_device_refuse_configuration_try,
            "blockstore_post": self._api_blockstore_post,
            "blockstore_get": self._api_blockstore_get,
            "vlob_group_check": self.vlob.api_vlob_group_check,
            "vlob_create": self.vlob.api_vlob_create,
            "vlob_read": self.vlob.api_vlob_read,
            "vlob_update": self.vlob.api_vlob_update,
            "beacon_read": self.beacon.api_beacon_read,
            "message_get": self.message.api_message_get,
            "message_new": self.message.api_message_new,
            "ping": self._api_ping,
        }

    async def init(self, nursery):
        self.nursery = nursery
        if self.dbh:
            await self.dbh.init(nursery)

    async def teardown(self):
        if self.dbh:
            await self.dbh.teardown()

    async def _api_ping(self, client_ctx, msg):
        msg = cmd_PING_Schema.load_or_abort(msg)
        if self.dbh:
            await self.dbh.ping(author=client_ctx.id, ping=msg["ping"])
        else:
            self.event_bus.send("pinged", author=client_ctx.id, ping=msg["ping"])
        return {"status": "ok", "pong": msg["ping"]}

    async def _api_blockstore_post(self, client_ctx, msg):
        if not self.blockstore:
            return {"status": "not_available", "reason": "Blockstore not available"}

        return await self.blockstore.api_blockstore_post(client_ctx, msg)

    async def _api_blockstore_get(self, client_ctx, msg):
        if not self.blockstore:
            return {"status": "not_available", "reason": "Blockstore not available"}

        return await self.blockstore.api_blockstore_get(client_ctx, msg)

    async def _api_event_subscribe(self, client_ctx, msg):
        msg = cmd_EVENT_SUBSCRIBE_Schema.load_or_abort(msg)
        event = msg["event"]

        if event == "beacon.updated":
            expected_beacon_id = msg["beacon_id"]
            key = (event, expected_beacon_id)

            def _build_event_msg(author, beacon_id, index, src_id, src_version):
                if beacon_id != expected_beacon_id:
                    return None
                return {
                    "event": event,
                    "beacon_id": beacon_id,
                    "index": index,
                    "src_id": src_id,
                    "src_version": src_version,
                }

        elif event == "message.received":
            key = event

            def _build_event_msg(author, recipient, index):
                if recipient != client_ctx.user_id:
                    return None
                return {"event": event, "index": index}

        elif event == "device.try_claim_submitted":
            key = event

            def _build_event_msg(author, user_id, device_name, config_try_id):
                if user_id != client_ctx.user_id:
                    return None
                return {"event": event, "device_name": device_name, "config_try_id": config_try_id}

        elif event == "pinged":
            expected_ping = msg["ping"]
            key = (event, expected_ping)

            def _build_event_msg(author, ping):
                if expected_ping and ping != expected_ping:
                    return None
                return {"event": event, "ping": ping}

        def _handle_event(sender, author, **kwargs):
            if author == client_ctx.id:
                return
            try:
                msg = _build_event_msg(author, **kwargs)
                if msg:
                    client_ctx.events.put_nowait(msg)
            except trio.WouldBlock:
                logger.warning("event queue is full for %s" % client_ctx.id)

        client_ctx.subscribed_events[key] = _handle_event
        self.event_bus.connect(event, _handle_event, weak=True)
        return {"status": "ok"}

    async def _api_event_unsubscribe(self, client_ctx, msg):
        msg = cmd_EVENT_SUBSCRIBE_Schema.load_or_abort(msg)
        if msg["event"] == "pinged":
            key = (msg["event"], msg["ping"])
        elif msg["event"] == "beacon.updated":
            key = (msg["event"], msg["beacon_id"])
        else:
            key = msg["event"]

        try:
            del client_ctx.subscribed_events[key]
        except KeyError:
            return {"status": "not_subscribed", "reason": f"Not subscribed to {key!r}"}

        return {"status": "ok"}

    async def _api_event_listen(self, client_ctx, msg):
        msg = cmd_EVENT_LISTEN_Schema.load_or_abort(msg)
        if msg["wait"]:
            event_data = await client_ctx.events.get()
        else:
            try:
                event_data = client_ctx.events.get_nowait()
            except trio.WouldBlock:
                return {"status": "no_events"}

        return {"status": "ok", **event_data}

    async def _api_event_list_subscribed(self, client_ctx, msg):
        cmd_EVENT_LIST_SUBSCRIBED.load_or_abort(msg)  # empty msg expected
        return {"status": "ok", "subscribed": list(client_ctx.subscribed_events.keys())}

    async def _do_handshake(self, sock):
        context = None
        try:
            hs = ServerHandshake(self.config.handshake_challenge_size)
            challenge_req = hs.build_challenge_req()
            await sock.send(challenge_req)
            answer_req = await sock.recv()

            hs.process_answer_req(answer_req)
            if hs.identity == "anonymous":
                context = AnonymousClientContext()
                result_req = hs.build_result_req()
            else:
                try:
                    userid, deviceid = hs.identity.split("@")
                except ValueError:
                    raise HandshakeFormatError()

                try:
                    user = await self.user.get(userid)
                    device = user["devices"][deviceid]
                except (NotFoundError, KeyError):
                    result_req = hs.build_bad_identity_result_req()
                else:
                    broadcast_key = PublicKey(user["broadcast_key"])
                    verify_key = VerifyKey(device["verify_key"])
                    context = ClientContext(hs.identity, broadcast_key, verify_key)
                    result_req = hs.build_result_req(verify_key)

        except HandshakeFormatError:
            result_req = hs.build_bad_format_result_req()
        await sock.send(result_req)
        return context

    async def handle_client(self, sockstream):
        sock = CookedSocket(sockstream)
        try:
            logger.debug("START HANDSHAKE")
            client_ctx = await self._do_handshake(sock)
            if not client_ctx:
                # Invalid handshake
                logger.debug("BAD HANDSHAKE")
                return

            logger.debug("HANDSHAKE DONE, CLIENT IS `%s`" % client_ctx.id)

            await self._handle_client_loop(sock, client_ctx)

        except trio.BrokenStreamError:
            # Client has closed connection
            pass
        except Exception as exc:
            # If we are here, something unexpected happened...
            logger.error(traceback.format_exc())
            await sock.aclose()
            raise

    async def _handle_client_loop(self, sock, client_ctx):
        while True:
            try:
                req = await sock.recv()
            except JSONDecodeError:
                rep = {"status": "invalid_msg_format", "reason": "Invalid message format"}
                await sock.send(rep)
                continue

            if not req:  # Client disconnected
                logger.debug("CLIENT DISCONNECTED")
                break

            logger.debug("REQ %s" % req)
            # TODO: handle bad msg
            try:
                cmd = req.get("cmd", "<missing>")
                if client_ctx.anonymous:
                    cmd_func = self.anonymous_cmds[cmd]
                else:
                    cmd_func = self.cmds[cmd]
            except KeyError:
                rep = {"status": "unknown_command", "reason": "Unknown command"}
            else:
                try:
                    rep = await cmd_func(client_ctx, req)
                except ParsecError as err:
                    rep = err.to_dict()
            logger.debug("REP %s" % rep)
            await sock.send(rep)
