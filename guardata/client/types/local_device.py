# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import attr
from typing import Tuple, Optional
from nacl.hashlib import blake2b
from marshmallow import ValidationError
from pendulum import Pendulum, now as pendulum_now

from guardata.crypto import SecretKey, PrivateKey, SigningKey
from guardata.serde import fields, post_load
from guardata.api.protocol import (
    UserID,
    DeviceID,
    OrganizationID,
    HumanHandle,
    DeviceIDField,
    HumanHandleField,
)
from guardata.api.data import BaseSchema, EntryID, EntryIDField, UserProfile, UserProfileField
from guardata.client.types.base import BaseLocalData
from guardata.client.types.backend_address import (
    BackendOrganizationAddr,
    BackendOrganizationAddrField,
)


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class LocalDevice(BaseLocalData):
    class SCHEMA_CLS(BaseSchema):
        organization_addr = BackendOrganizationAddrField(required=True)
        device_id = DeviceIDField(required=True)
        device_label = fields.String(allow_none=True, missing=None)
        human_handle = HumanHandleField(allow_none=True, missing=None)
        signing_key = fields.SigningKey(required=True)
        private_key = fields.PrivateKey(required=True)
        # `profile` replaces `is_admin` field (which is still required for backward
        # compatibility), hence `None` is not allowed
        is_admin = fields.Boolean(required=True)
        profile = UserProfileField(allow_none=False)
        user_manifest_id = EntryIDField(required=True)
        user_manifest_key = fields.SecretKey(required=True)
        local_symkey = fields.SecretKey(required=True)

        @post_load
        def make_obj(self, data):
            # Handle legacy `is_admin` field
            default_profile = UserProfile.ADMIN if data.pop("is_admin") else UserProfile.STANDARD
            try:
                profile = data["profile"]
            except KeyError:
                data["profile"] = default_profile
            else:
                if default_profile == UserProfile.ADMIN and profile != UserProfile.ADMIN:
                    raise ValidationError(
                        "Fields `profile` and `is_admin` have incompatible values"
                    )

            return LocalDevice(**data)

    organization_addr: BackendOrganizationAddr
    device_id: DeviceID
    device_label: Optional[str]
    human_handle: Optional[HumanHandle]
    signing_key: SigningKey
    private_key: PrivateKey
    profile: UserProfile
    user_manifest_id: EntryID
    user_manifest_key: SecretKey
    local_symkey: SecretKey

    # Only used during schema serialization
    @property
    def is_admin(self) -> bool:
        return self.profile == UserProfile.ADMIN

    def __repr__(self):
        return f"{self.__class__.__name__}({self.device_id})"

    @property
    def slug(self) -> str:
        # Add a hash to avoid clash when the backend is reset
        # and we recreate a device with same organization/device_id
        # organization and device_id than a previous one
        return f"{self.root_verify_key_hash}#{self.organization_id}#{self.device_id}"

    @property
    def slughash(self) -> str:
        """
        Slug is long and not readable enough (given device_id is made of uuids).
        Hence it's often simpler to rely on it hash instead (e.g. select the
        device to use in the CLI by providing the beginning of the hash)
        """
        return blake2b(self.slug.encode()).hexdigest()

    @staticmethod
    def load_slug(slug: str) -> Tuple[str, OrganizationID, DeviceID]:
        """
        Raises: ValueError
        """
        rvk_hash, raw_org_id, raw_device_id = slug.split("#")
        return rvk_hash, OrganizationID(raw_org_id), DeviceID(raw_device_id)

    @property
    def root_verify_key(self):
        return self.organization_addr.root_verify_key

    @property
    def root_verify_key_hash(self):
        return blake2b(self.root_verify_key.encode()).hexdigest()[:10]

    @property
    def organization_id(self):
        return self.organization_addr.organization_id

    @property
    def device_name(self):
        return self.device_id.device_name

    @property
    def user_id(self):
        return self.device_id.user_id

    @property
    def verify_key(self):
        return self.signing_key.verify_key

    @property
    def public_key(self):
        return self.private_key.public_key

    @property
    def user_display(self) -> str:
        return str(self.human_handle or self.user_id)

    @property
    def short_user_display(self) -> str:
        return str(self.human_handle.label if self.human_handle else self.user_id)

    @property
    def device_display(self) -> str:
        return str(self.device_label or self.device_id.device_name)


@attr.s(slots=True, frozen=True, auto_attribs=True)
class UserInfo:
    user_id: UserID
    human_handle: Optional[HumanHandle]
    profile: UserProfile
    created_on: Pendulum
    revoked_on: Optional[Pendulum]

    @property
    def user_display(self) -> str:
        return str(self.human_handle or self.user_id)

    @property
    def short_user_display(self) -> str:
        return str(self.human_handle.label if self.human_handle else self.user_id)

    @property
    def is_revoked(self):
        return pendulum_now() >= self.revoked_on if self.revoked_on else False

    def __repr__(self):
        return f"<UserInfo {self.user_display}>"


@attr.s(slots=True, frozen=True, auto_attribs=True)
class DeviceInfo:
    device_id: DeviceID
    device_label: Optional[str]
    created_on: Pendulum

    @property
    def device_name(self):
        return self.device_id.device_name

    @property
    def device_display(self) -> str:
        return str(self.device_label or self.device_id.device_name)

    def __repr__(self):
        return f"DeviceInfo({self.device_display})"
