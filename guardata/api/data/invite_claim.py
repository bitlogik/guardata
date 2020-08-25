# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from guardata.crypto import VerifyKey, PublicKey, PrivateKey, SecretKey
from guardata.serde import fields, post_load
from guardata.api.protocol import DeviceID, DeviceIDField
from guardata.api.data.base import BaseAPIData, BaseSchema
from guardata.api.data.entry import EntryID, EntryIDField
import attr


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class APIV1_UserClaimContent(BaseAPIData):
    class SCHEMA_CLS(BaseSchema):
        type = fields.CheckedConstant("user_claim", required=True)
        token = fields.String(required=True)
        # Note claiming user also imply creating a first device
        device_id = DeviceIDField(required=True)
        public_key = fields.PublicKey(required=True)
        verify_key = fields.VerifyKey(required=True)

        @post_load
        def make_obj(self, data):
            data.pop("type")
            return APIV1_UserClaimContent(**data)

    token: str
    device_id: DeviceID
    public_key: PublicKey
    verify_key: VerifyKey


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class APIV1_DeviceClaimContent(BaseAPIData):
    class SCHEMA_CLS(BaseSchema):
        type = fields.CheckedConstant("device_claim", required=True)
        token = fields.String(required=True)
        device_id = DeviceIDField(required=True)
        verify_key = fields.VerifyKey(required=True)
        answer_public_key = fields.PublicKey(required=True)

        @post_load
        def make_obj(self, data):
            data.pop("type")
            return APIV1_DeviceClaimContent(**data)

    token: str
    device_id: DeviceID
    verify_key: VerifyKey
    answer_public_key: PublicKey


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class APIV1_DeviceClaimAnswerContent(BaseAPIData):
    class SCHEMA_CLS(BaseSchema):
        type = fields.CheckedConstant("device_claim_answer", required=True)
        private_key = fields.PrivateKey(required=True)
        user_manifest_id = EntryIDField(required=True)
        user_manifest_key = fields.SecretKey(required=True)

        @post_load
        def make_obj(self, data):
            data.pop("type")
            return APIV1_DeviceClaimAnswerContent(**data)

    private_key: PrivateKey
    user_manifest_id: EntryID
    user_manifest_key: SecretKey
