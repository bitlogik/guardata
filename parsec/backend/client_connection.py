import attr
import random
import string
import asyncio
from logbook import Logger
from blinker import signal
from websockets import ConnectionClosed
from effect2 import TypeDispatcher, ComposedDispatcher, asyncio_perform

from parsec.tools import ejson_dumps
from parsec.base import base_dispatcher
from parsec.backend.session import SessionComponent, handshake_io_dispatcher_factory
from parsec.exceptions import HandshakeError


@attr.s
class EPushClientMsg:
    payload = attr.ib()


@attr.s
class EClientSubscribeEvent:
    event = attr.ib()
    sender = attr.ib()


@attr.s
class EClientUnsubscribeEvent:
    event = attr.ib()
    sender = attr.ib()


def _unique_enough_id():
    # Colision risk is high, but this is pretty fine (and much more readable
    # than a uuid4) for giving id to connections
    return ''.join([random.choice(string.ascii_letters + string.digits) for ch in range(4)])


@attr.s
class WebsocketClientConnectionContext:
    ws = attr.ib()
    queued_pushed_events = attr.ib(default=attr.Factory(asyncio.Queue))
    logger = attr.ib(default=attr.Factory(
        lambda: Logger('Connection ' + _unique_enough_id())))
    subscribed_events = attr.ib(default=attr.Factory(dict))

    async def recv(self):
        return await self.ws.recv()

    async def send(self, body):
        return await self.ws.send(body)


def client_dispatcher_factory(client_context):
    def perform_push_client_msg(intent):
        client_context.queued_pushed_events.put_nowait(intent.payload)

    def perform_client_subscribe_event(intent):
        key = (intent.event, intent.sender)

        def on_event(sender):
            payload = ejson_dumps({'event': intent.event, 'sender': sender})
            client_context.queued_pushed_events.put_nowait(payload)

        # Attach the callbacks to the client context to make them have the same
        # lifetime given event registration expires when callback is destroyed
        # TODO: allow a subset of the possible events
        client_context.subscribed_events[key] = on_event
        signal(intent.event).connect(on_event, sender=intent.sender)

    def perform_client_unsubscribe_event(intent):
        key = (intent.event, intent.sender)
        try:
            del client_context.subscribed_events[key]
        except KeyError:
            pass

    return TypeDispatcher({
        EPushClientMsg: perform_push_client_msg,
        EClientSubscribeEvent: perform_client_subscribe_event,
        EClientUnsubscribeEvent: perform_client_unsubscribe_event
    })


def on_connection_factory(execute_cmd, base_dispatcher=base_dispatcher):

    async def on_connection(websocket, path):
        context = WebsocketClientConnectionContext(websocket)
        client_dispatcher = client_dispatcher_factory(context)
        session = SessionComponent()
        dispatcher = ComposedDispatcher([
            base_dispatcher, client_dispatcher, session.get_dispatcher()])
        context.logger.info('Connection started')
        # Handshake
        try:
            handshake_dispatcher = ComposedDispatcher([
                dispatcher, handshake_io_dispatcher_factory(context)])
            await asyncio_perform(handshake_dispatcher, session.handshake())
        except HandshakeError:
            return
        context.logger.debug('Handshake done, `%s` is authenticated.' % session.id)
        # Wait for two things:
        # - User's command (incomming request)
        # - Event subscribed by user (pushed to client requests)
        # Note user's command should have been replied before sending an event notification
        get_event = asyncio.ensure_future(context.queued_pushed_events.get())
        get_cmd = asyncio.ensure_future(context.recv())
        try:
            while True:
                done, pending = await asyncio.wait((get_event, get_cmd),
                                                   return_when='FIRST_COMPLETED')
                if get_event in done:
                    payload = get_event.result()
                    context.logger.debug('Got event: %s' % payload)
                    await context.send(payload)
                    # Restart watch on incoming notifications
                    get_event = asyncio.ensure_future(context.queued_pushed_events.get())
                else:
                    raw_cmd = get_cmd.result()
                    if not raw_cmd:
                        context.logger.debug('Connection stopped')
                        return
                    context.logger.debug('Received: %r' % raw_cmd)
                    intent = execute_cmd(raw_cmd)
                    raw_resp = await asyncio_perform(dispatcher, intent)
                    context.logger.debug('Replied: %r' % raw_resp)
                    await context.send(raw_resp)
                    # Restart watch on incoming messages
                    get_cmd = asyncio.ensure_future(context.recv())
        except ConnectionClosed:
            context.logger.info('Connection closed')
        finally:
            get_event.cancel()
            get_cmd.cancel()

    return on_connection
