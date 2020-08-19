# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import zlib
import json

from marshmallow import ValidationError

from parsec.serde.packing import packb, unpackb, SerdePackingError
from parsec.serde.exceptions import SerdeValidationError


class BaseSerializer:
    def __repr__(self):
        return f"{self.__class__.__name__}(schema={self.schema.__class__.__name__})"

    def __init__(
        self, schema_cls, validation_exc=SerdeValidationError, packing_exc=SerdePackingError
    ):
        if isinstance(validation_exc, SerdeValidationError):
            raise ValueError("validation_exc must subclass SerdeValidationError")
        if isinstance(packing_exc, SerdePackingError):
            raise ValueError("packing_exc must subclass SerdePackingError")

        self.validation_exc = validation_exc
        self.packing_exc = packing_exc
        self.schema = schema_cls(strict=True)

    def load(self, data: dict):
        """
        Raises:
            SerdeValidationError
        """
        try:
            return self.schema.load(data).data

        except ValidationError as exc:
            raise self.validation_exc(exc.messages) from exc

    def dump(self, data) -> dict:
        """
        Raises:
            SerdeValidationError
        """
        try:
            return self.schema.dump(data).data

        except ValidationError as exc:
            raise self.validation_exc(exc.messages) from exc

    def loads(self, data: bytes) -> dict:
        raise NotImplementedError

    def dumps(self, data: dict) -> bytes:
        raise NotImplementedError


class JSONSerializer(BaseSerializer):
    def loads(self, data: bytes) -> dict:
        """
        Raises:
            SerdeValidationError
            SerdePackingError
        """
        try:
            decoded_data = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise self.packing_exc from exc
        return self.load(decoded_data)

    def dumps(self, data: dict) -> bytes:
        """
        Raises:
            SerdeValidationError
            SerdePackingError
        """
        return json.dumps(self.dump(data)).encode("utf-8")


class MsgpackSerializer(BaseSerializer):
    def loads(self, data: bytes) -> dict:
        """
        Raises:
            SerdeValidationError
            SerdePackingError
        """
        return self.load(unpackb(data, self.packing_exc))

    def dumps(self, data: dict) -> bytes:
        """
        Raises:
            SerdeValidationError
            SerdePackingError
        """
        return packb(self.dump(data), self.packing_exc)


class ZipMsgpackSerializer(MsgpackSerializer):
    def loads(self, data: bytes) -> dict:
        """
        Raises:
            SerdeValidationError
            SerdePackingError
        """
        try:
            unzipped = zlib.decompress(data)
        except zlib.error as exc:
            raise self.packing_exc(str(exc)) from exc
        return super().loads(unzipped)

    def dumps(self, data: dict) -> bytes:
        """
        Raises:
            SerdeValidationError
            SerdePackingError
        """
        return zlib.compress(super().dumps(data))
