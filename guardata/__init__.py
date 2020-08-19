# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from guardata._version import __version__

# The guardata.utils module includes a bit of patching, let's make sure it is imported
import guardata.utils  # noqa

__all__ = ("__version__",)
