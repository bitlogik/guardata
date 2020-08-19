# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from typing import Union, NewType

from guardata.api.data import EntryID, EntryIDField, EntryName, EntryNameField

from guardata.core.types.base import FsPath

from guardata.core.types.backend_address import (
    BackendAddr,
    BackendOrganizationAddr,
    BackendActionAddr,
    BackendOrganizationBootstrapAddr,
    BackendOrganizationClaimUserAddr,
    BackendOrganizationClaimDeviceAddr,
    BackendOrganizationAddrField,
    BackendOrganizationFileLinkAddr,
    BackendInvitationAddr,
)
from guardata.core.types.local_device import LocalDevice, UserInfo, DeviceInfo
from guardata.core.types.manifest import (
    DEFAULT_BLOCK_SIZE,
    LocalFileManifest,
    LocalFolderManifest,
    LocalWorkspaceManifest,
)
from guardata.core.types.manifest import (
    LocalUserManifest,
    BaseLocalManifest,
    WorkspaceEntry,
    WorkspaceRole,
    BlockAccess,
    BlockID,
    Chunk,
    ChunkID,
)
from guardata.api.data import WorkspaceManifest as RemoteWorkspaceManifest
from guardata.api.data import FolderManifest as RemoteFolderManifest

FileDescriptor = NewType("FileDescriptor", int)
LocalFolderishManifests = Union[LocalFolderManifest, LocalWorkspaceManifest]
RemoteFolderishManifests = Union[RemoteFolderManifest, RemoteWorkspaceManifest]


__all__ = (
    "FileDescriptor",
    "LocalFolderishManifests",
    "RemoteFolderishManifests",
    # Base
    "FsPath",
    # Entry
    "EntryID",
    "EntryIDField",
    "EntryName",
    "EntryNameField",
    # Backend address
    "BackendAddr",
    "BackendOrganizationAddr",
    "BackendActionAddr",
    "BackendOrganizationBootstrapAddr",
    "BackendOrganizationClaimUserAddr",
    "BackendOrganizationClaimDeviceAddr",
    "BackendOrganizationAddrField",
    "BackendOrganizationFileLinkAddr",
    "BackendInvitationAddr",
    # local_device
    "LocalDevice",
    "UserInfo",
    "DeviceInfo",
    # "manifest"
    "DEFAULT_BLOCK_SIZE",
    "LocalFileManifest",
    "LocalFolderManifest",
    "LocalWorkspaceManifest",
    "LocalUserManifest",
    "BaseLocalManifest",
    "WorkspaceEntry",
    "WorkspaceRole",
    "BlockAccess",
    "BlockID",
    "Chunk",
    "ChunkID",
)
