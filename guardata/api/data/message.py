# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from pendulum import Pendulum

from enum import Enum
import attr
from guardata.crypto import SecretKey
from guardata.serde import fields, post_load, OneOfSchema
from guardata.api.data.entry import EntryID, EntryIDField
from guardata.api.data.base import BaseAPISignedData, BaseSignedDataSchema, DeviceIDField
from guardata.api.protocol import DeviceID


class MessageContentType(Enum):
    SHARING_GRANTED = "sharing.granted"
    SHARING_REENCRYPTED = "sharing.reencrypted"
    SHARING_REVOKED = "sharing.revoked"
    PING = "ping"


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class BaseMessageContent(BaseAPISignedData):
    class SCHEMA_CLS(OneOfSchema, BaseSignedDataSchema):
        type_field = "type"
        author = DeviceIDField(required=True, allow_none=False)

        @property
        def type_schemas(self):
            return {
                MessageContentType.SHARING_GRANTED: SharingGrantedMessageContent.SCHEMA_CLS,
                MessageContentType.SHARING_REENCRYPTED: SharingReencryptedMessageContent.SCHEMA_CLS,
                MessageContentType.SHARING_REVOKED: SharingRevokedMessageContent.SCHEMA_CLS,
                MessageContentType.PING: PingMessageContent.SCHEMA_CLS,
            }

        def get_obj_type(self, obj):
            return obj["type"]

    author: DeviceID


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class SharingGrantedMessageContent(BaseMessageContent):
    class SCHEMA_CLS(BaseSignedDataSchema):
        type = fields.EnumCheckedConstant(MessageContentType.SHARING_GRANTED, required=True)
        name = fields.String(required=True)
        author = DeviceIDField(required=True, allow_none=False)
        id = EntryIDField(required=True)
        encryption_revision = fields.Integer(required=True)
        encrypted_on = fields.DateTime(required=True)
        key = fields.SecretKey(required=True)
        # Don't include role given the only reliable way to get this information
        # is to fetch the realm role certificate from the backend.
        # Besides, we will also need the message sender's realm role certificate
        # to make sure he is an owner.

        @post_load
        def make_obj(self, data):
            data.pop("type")
            return SharingGrantedMessageContent(**data)

    name: str
    id: EntryID
    encryption_revision: int
    encrypted_on: Pendulum
    key: SecretKey


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class SharingReencryptedMessageContent(SharingGrantedMessageContent):
    class SCHEMA_CLS(SharingGrantedMessageContent.SCHEMA_CLS):
        type = fields.EnumCheckedConstant(MessageContentType.SHARING_REENCRYPTED, required=True)
        # This message is similar to `sharing.granted`. Hence both can be processed
        # interchangeably, which avoid possible concurrency issues when a sharing
        # occurs right before a reencryption.

        @post_load
        def make_obj(self, data):
            data.pop("type")
            return SharingReencryptedMessageContent(**data)


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class SharingRevokedMessageContent(BaseMessageContent):
    class SCHEMA_CLS(BaseSignedDataSchema):
        type = fields.EnumCheckedConstant(MessageContentType.SHARING_REVOKED, required=True)
        id = EntryIDField(required=True)

        @post_load
        def make_obj(self, data):
            data.pop("type")
            return SharingRevokedMessageContent(**data)

    id: EntryID


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class PingMessageContent(BaseMessageContent):
    class SCHEMA_CLS(BaseSignedDataSchema):
        type = fields.EnumCheckedConstant(MessageContentType.PING, required=True)
        ping = fields.String(required=True)

        @post_load
        def make_obj(self, data):
            data.pop("type")
            return PingMessageContent(**data)

    ping: str
