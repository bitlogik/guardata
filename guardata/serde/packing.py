# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from uuid import UUID
from pendulum import Pendulum
from datetime import datetime
from struct import pack as struct_pack, unpack as struct_unpack
from msgpack import (
    packb as msgpack_packb,
    unpackb as msgpack_unpackb,
    Unpacker as msgpack_Unpacker,
    ExtType,
)
from msgpack.exceptions import ExtraData, FormatError, StackError

from guardata.serde.exceptions import SerdePackingError


MAX_BIN_LEN = 8 * 1024 * 1024  # 2*4 MB (>150% 4MB)


def packb(data: dict, exc_cls=SerdePackingError) -> bytes:
    """
    Raises:
        SerdePackingError
    """

    def _default(obj):
        # TODO: we should be only testing against pendulum.Pendulum, but
        # asyncpg returns datetime
        if isinstance(obj, datetime):
            return ExtType(1, struct_pack("!d", obj.timestamp()))
        elif isinstance(obj, UUID):
            return ExtType(2, obj.bytes)

        raise TypeError("Unknown type: %r" % (obj,))

    try:
        return msgpack_packb(data, default=_default, use_bin_type=True)

    except (ExtraData, ValueError, FormatError, StackError) as exc:
        raise exc_cls(f"Invalid msgpack data: {exc}") from exc


def _unpackb_ext_hook(code, data):
    if code == 1:
        return Pendulum.utcfromtimestamp(struct_unpack("!d", data)[0])
    elif code == 2:
        return UUID(bytes=data)

    return ExtType(code, data)


def unpackb(raw_data: bytes, exc_cls=SerdePackingError) -> dict:
    """
    Raises:
        SerdePackingError
    """

    try:
        return msgpack_unpackb(
            raw_data, ext_hook=_unpackb_ext_hook, raw=False, max_bin_len=MAX_BIN_LEN
        )

    except (ExtraData, ValueError, FormatError, StackError) as exc:
        raise exc_cls(f"Invalid msgpack data: {exc}") from exc


class Unpacker:
    def __init__(self, exc_cls=SerdePackingError):
        self._unpacker = msgpack_Unpacker(
            ext_hook=_unpackb_ext_hook, raw=False, max_bin_len=MAX_BIN_LEN
        )
        self._exc_cls = exc_cls

    def feed(self, data):
        self._unpacker.feed(data)

    def __next__(self):
        try:
            return next(self._unpacker)
        except (ExtraData, ValueError, FormatError, StackError) as exc:
            raise self._exc_cls(f"Invalid msgpack data: {exc}") from exc

    def __iter__(self):
        return self
