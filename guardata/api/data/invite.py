# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import re
from typing import Optional, Tuple, List
from random import shuffle
from secrets import randbelow

from guardata.crypto import VerifyKey, PublicKey, PrivateKey, SecretKey, derivate_secret_from_keys
from guardata.serde import fields, post_load
from guardata.api.protocol import DeviceID, DeviceIDField, HumanHandle, HumanHandleField
from guardata.api.data.base import BaseAPIData, BaseSchema
from guardata.api.data.entry import EntryID, EntryIDField
from guardata.api.data.certif import UserProfile, UserProfileField
import attr


class SASCode(str):
    # Short Authentication Strings
    __slots__ = ()
    length = 5
    symbols = "123456789ABCDEFGHJKLMNPRSTUVWXYZ"
    regex = re.compile(rf"^[{symbols}]{{{length}}}$")

    def __init__(self, raw):
        if not isinstance(raw, str) or not self.regex.match(raw):
            raise ValueError("Invalid SAS code")

    def __repr__(self):
        return f"<SASCode {super().__repr__()}>"

    @classmethod
    def from_int(cls, num):
        if num < 0:
            raise ValueError("Provided integer is negative")
        result = ""
        for _ in range(cls.length):
            result += cls.symbols[num % len(cls.symbols)]
            num //= len(cls.symbols)
        if num != 0:
            raise ValueError("Provided integer is too large")
        return cls(result)


def generate_sas_codes(
    claimer_nonce: bytes, greeter_nonce: bytes, shared_secret_key: SecretKey
) -> Tuple[SASCode, SASCode]:
    # Computes combined KDF
    combined_nonce = claimer_nonce + greeter_nonce
    # Digest size of 8 bytes can be split between two 25bits SAS
    # KDF is argon2id(pwd=combined_nonce+1half_shared_secret_key, salt=2half_shared_secret_key,, "moderate")
    combined_kdf = derivate_secret_from_keys(
        combined_nonce + shared_secret_key[:16], shared_secret_key[16:]
    )

    mac_as_int = int.from_bytes(combined_kdf[:8], "big")
    # Big endian number extracted from bits [0, 25[
    claimer_sas = mac_as_int % 2 ** 25
    # Big endian number extracted from bits [25, 50[
    greeter_sas = (mac_as_int >> 25) % 2 ** 25

    return SASCode.from_int(claimer_sas), SASCode.from_int(greeter_sas)


def generate_sas_code_candidates(valid_sas: SASCode, size: int = 3) -> List[SASCode]:
    candidates = {valid_sas}
    while len(candidates) < size:
        candidates.add(SASCode.from_int(randbelow(2 ** 25)))
    ordered_candidates = list(candidates)
    shuffle(ordered_candidates)
    return ordered_candidates


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class InviteUserData(BaseAPIData):
    class SCHEMA_CLS(BaseSchema):
        type = fields.CheckedConstant("invite_user_data", required=True)
        # Claimer ask for device_label/human_handle, but greeter has final word on this
        requested_device_label = fields.String(allow_none=True, missing=None)
        requested_human_handle = HumanHandleField(allow_none=True, missing=None)
        # Note claiming user also imply creating a first device
        public_key = fields.PublicKey(required=True)
        verify_key = fields.VerifyKey(required=True)

        @post_load
        def make_obj(self, data):
            data.pop("type")
            return InviteUserData(**data)

    requested_device_label: Optional[str]
    requested_human_handle: Optional[HumanHandle]
    public_key: PublicKey
    verify_key: VerifyKey


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class InviteUserConfirmation(BaseAPIData):
    class SCHEMA_CLS(BaseSchema):
        type = fields.CheckedConstant("invite_user_confirmation", required=True)
        device_id = DeviceIDField(required=True)
        device_label = fields.String(allow_none=True, missing=None)
        human_handle = HumanHandleField(allow_none=True, missing=None)
        profile = UserProfileField(required=True)
        root_verify_key = fields.VerifyKey(required=True)

        @post_load
        def make_obj(self, data):
            data.pop("type")
            return InviteUserConfirmation(**data)

    device_id: DeviceID
    device_label: Optional[str]
    human_handle: Optional[HumanHandle]
    profile: UserProfile
    root_verify_key: VerifyKey


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class InviteDeviceData(BaseAPIData):
    class SCHEMA_CLS(BaseSchema):
        type = fields.CheckedConstant("invite_device_data", required=True)
        # Claimer ask for device_label, but greeter has final word on this
        requested_device_label = fields.String(allow_none=True, missing=None)
        verify_key = fields.VerifyKey(required=True)

        @post_load
        def make_obj(self, data):
            data.pop("type")
            return InviteDeviceData(**data)

    requested_device_label: Optional[str]
    verify_key: VerifyKey


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class InviteDeviceConfirmation(BaseAPIData):
    class SCHEMA_CLS(BaseSchema):
        type = fields.CheckedConstant("invite_device_confirmation", required=True)
        device_id = DeviceIDField(required=True)
        device_label = fields.String(allow_none=True, missing=None)
        human_handle = HumanHandleField(allow_none=True, missing=None)
        profile = UserProfileField(required=True)
        private_key = fields.PrivateKey(required=True)
        user_manifest_id = EntryIDField(required=True)
        user_manifest_key = fields.SecretKey(required=True)
        root_verify_key = fields.VerifyKey(required=True)

        @post_load
        def make_obj(self, data):
            data.pop("type")
            return InviteDeviceConfirmation(**data)

    device_id: DeviceID
    device_label: Optional[str]
    human_handle: Optional[HumanHandle]
    profile: UserProfile
    private_key: PrivateKey
    user_manifest_id: EntryID
    user_manifest_key: SecretKey
    root_verify_key: VerifyKey
