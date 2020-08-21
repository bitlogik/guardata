# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3


class BackendConnectionError(Exception):
    pass


class BackendProtocolError(BackendConnectionError):
    pass


class BackendNotAvailable(BackendConnectionError):
    pass


class BackendConnectionRefused(BackendConnectionError):
    pass


# TODO: hack needed by `LoggedClient.get_user_info`
class BackendNotFoundError(BackendConnectionError):
    pass
