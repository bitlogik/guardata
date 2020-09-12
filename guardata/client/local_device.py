# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import attr
from pathlib import Path
from nacl.hashlib import blake2b
from typing import List, Optional, Iterator
from os import fspath
from os import name as osname

from guardata.serde import BaseSchema, fields, MsgpackSerializer
from guardata.crypto import (
    SecretKey,
    SigningKey,
    PrivateKey,
    CryptoError,
    derivate_secret_key_from_password,
)
from guardata.api.protocol import (
    OrganizationID,
    DeviceID,
    HumanHandle,
    HumanHandleField,
    OrganizationIDField,
    DeviceIDField,
)
from guardata.api.data import DataError, UserProfile
from guardata.client.types import EntryID, LocalDevice, BackendOrganizationAddr


class LocalDeviceError(Exception):
    pass


class LocalDeviceCryptoError(LocalDeviceError):
    pass


class LocalDeviceNotFoundError(LocalDeviceError):
    pass


class LocalDeviceAlreadyExistsError(LocalDeviceError):
    pass


class LocalDeviceValidationError(LocalDeviceError):
    pass


class LocalDevicePackingError(LocalDeviceError):
    pass


class DeviceFileSchema(BaseSchema):
    type = fields.CheckedConstant("password", required=True)
    salt = fields.Bytes(required=True)
    ciphertext = fields.Bytes(required=True)

    # Since human_handle/device_label has been introduced, device_id is
    # redacted (i.e. user_id and device_name are 2 random uuids), hence
    # those fields have been added to the device file so the login page in
    # the GUI can use them to provide useful information.
    human_handle = HumanHandleField(allow_none=True, missing=None)
    device_label = fields.String(allow_none=True, missing=None)

    # Store device and organization ID in the device file
    # For legacy versions, this information is available in the file name
    device_id = DeviceIDField(allow_none=True, missing=None)
    organization_id = OrganizationIDField(allow_none=True, missing=None)
    root_verify_key_hash = fields.String(allow_none=True, missing=None)


key_file_serializer = MsgpackSerializer(
    DeviceFileSchema, validation_exc=LocalDeviceValidationError, packing_exc=LocalDevicePackingError
)


def generate_new_device(
    device_id: DeviceID,
    organization_addr: BackendOrganizationAddr,
    profile: UserProfile = UserProfile.STANDARD,
    human_handle: Optional[HumanHandle] = None,
    device_label: Optional[str] = None,
    signing_key: Optional[SigningKey] = None,
    private_key: Optional[PrivateKey] = None,
) -> LocalDevice:
    return LocalDevice(
        organization_addr=organization_addr,
        device_id=device_id,
        device_label=device_label,
        human_handle=human_handle,
        signing_key=signing_key or SigningKey.generate(),
        private_key=private_key or PrivateKey.generate(),
        profile=profile,
        user_manifest_id=EntryID(),
        user_manifest_key=SecretKey.generate(),
        local_symkey=SecretKey.generate(),
    )


def fix_dir_win(path: Path) -> Path:
    if osname == "nt":
        path_str = fspath(path)
        if not path_str.startswith("\\\\?\\"):
            path_str = "\\\\?\\" + path_str
            return Path(path_str)
    return path


def decorator_fix_windir(func):
    def wrapper(*args, **kwargs):
        path = func(*args, **kwargs)
        return fix_dir_win(path)

    return wrapper


@decorator_fix_windir
def get_key_file(config_dir: Path, device: LocalDevice) -> Path:
    key_path = ""
    for available_device in _iter_available_devices(config_dir):
        if available_device.slug == device.slug:
            key_path = available_device.key_file_path
            break
    if key_path:
        return key_path
    raise FileNotFoundError


@decorator_fix_windir
def get_default_key_file(config_dir: Path, device: LocalDevice) -> Path:
    """Return the default keyfile path for a given device.

    Note that the filename does not carry any intrinsic meaning.
    Here, we simply use the slughash to avoid name collision.
    """
    return get_devices_dir(config_dir) / f"{device.slughash}.keys"


@decorator_fix_windir
def get_devices_dir(config_dir: Path) -> Path:
    return config_dir / "devices"


@attr.s(slots=True, frozen=True, auto_attribs=True)
class AvailableDevice:
    key_file_path: Path
    organization_id: OrganizationID
    device_id: DeviceID
    human_handle: Optional[HumanHandle]
    device_label: Optional[str]
    root_verify_key_hash: str

    @property
    def user_display(self) -> str:
        return str(self.human_handle or self.device_id.user_id)

    @property
    def short_user_display(self) -> str:
        return str(self.human_handle.label if self.human_handle else self.device_id.user_id)

    @property
    def device_display(self) -> str:
        return self.device_label or str(self.device_id.device_name)

    @property
    def slug(self) -> str:
        # Identical to LocalDevice
        return f"{self.root_verify_key_hash}#{self.organization_id}#{self.device_id}"

    @property
    def slughash(self) -> str:
        return blake2b(self.slug.encode()).hexdigest()


def _iter_available_devices(config_dir: Path) -> Iterator[AvailableDevice]:
    try:
        device_dir = get_devices_dir(config_dir)
        key_files = device_dir.rglob("*.keys")
    except FileNotFoundError:
        return

    # Sanity checks
    for key_file in key_files:

        key_file_path = fix_dir_win(device_dir / key_file)
        try:
            data = key_file_serializer.loads(key_file_path.read_bytes())
        except (FileNotFoundError, LocalDeviceError):
            # Not a valid keys file, ignore this folder
            continue

        # Legacy device file
        if data["organization_id"] is None or data["device_id"] is None:
            try:
                rvk_hash, organization_id, device_id = LocalDevice.load_slug(key_file_path.stem)
            except ValueError:
                # Not a valid slug, ignore this keys file
                continue
            else:
                data["organization_id"] = organization_id
                data["device_id"] = device_id
                data["root_verify_key_hash"] = rvk_hash

        yield AvailableDevice(
            key_file_path=key_file_path,
            organization_id=data["organization_id"],
            device_id=data["device_id"],
            human_handle=data["human_handle"],
            device_label=data["device_label"],
            root_verify_key_hash=data["root_verify_key_hash"],
        )


def list_available_devices(config_dir: Path) -> List[AvailableDevice]:
    return list(_iter_available_devices(config_dir))


def load_device_with_password(key_file: Path, password: str) -> LocalDevice:
    """
        LocalDeviceNotFoundError
        LocalDeviceCryptoError
        LocalDeviceValidationError
        LocalDevicePackingError
    """
    try:
        ciphertext = key_file.read_bytes()
    except OSError as exc:
        raise LocalDeviceNotFoundError(f"Config file `{key_file}` is missing") from exc

    try:
        data = key_file_serializer.loads(ciphertext)
    except DataError as exc:
        raise LocalDeviceValidationError(f"Cannot load local device: {exc}") from exc

    try:
        key, _ = derivate_secret_key_from_password(password, data["salt"])
        plaintext = key.decrypt(data["ciphertext"])
    except CryptoError as exc:
        raise LocalDeviceCryptoError(str(exc)) from exc

    try:
        return LocalDevice.load(plaintext)

    except DataError as exc:
        raise LocalDeviceValidationError(f"Cannot load local device: {exc}") from exc


def save_device_with_password(
    config_dir: Path, device: LocalDevice, password: str, force: bool = False
) -> AvailableDevice:
    """
        LocalDeviceError
        LocalDeviceNotFoundError
        LocalDeviceCryptoError
        LocalDeviceValidationError
        LocalDevicePackingError
    """
    key_file = get_default_key_file(config_dir, device)
    _save_device_with_password(key_file, device, password, force=force)
    return key_file


def _save_device_with_password(
    key_file: Path, device: LocalDevice, password: str, force: bool = False
) -> None:
    if key_file.exists() and not force:
        raise LocalDeviceAlreadyExistsError(f"Device key file `{key_file}` already exists")

    try:
        key, salt = derivate_secret_key_from_password(password)
        ciphertext = key.encrypt(device.dump())

    except (CryptoError, DataError) as exc:
        raise LocalDeviceValidationError(f"Cannot dump local device: {exc}") from exc

    key_file_content = key_file_serializer.dumps(
        {
            "salt": salt,
            "ciphertext": ciphertext,
            "human_handle": device.human_handle,
            "device_label": device.device_label,
            "organization_id": device.organization_id,
            "device_id": device.device_id,
            "root_verify_key_hash": device.root_verify_key_hash,
        }
    )

    try:
        key_file.parent.mkdir(mode=0o700, exist_ok=True, parents=True)
        key_file.write_bytes(key_file_content)

    except OSError as exc:
        raise LocalDeviceError(f"Cannot save {key_file}: {exc}") from exc


def change_device_password(key_file: Path, old_password: str, new_password: str) -> None:
    """
        LocalDeviceError
        LocalDeviceNotFoundError
        LocalDeviceCryptoError
        LocalDeviceValidationError
        LocalDevicePackingError
    """
    device = load_device_with_password(key_file, password=old_password)
    _save_device_with_password(key_file, device, password=new_password, force=True)
