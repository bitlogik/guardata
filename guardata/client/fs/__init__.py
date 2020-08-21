# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from guardata.client.fs.userfs import UserFS
from guardata.client.fs.exceptions import (
    # Generic classes
    FSError,
    FSOperationError,
    FSLocalOperationError,
    FSRemoteOperationError,
    # Misc errors
    FSWorkspaceNotFoundError,
    FSWorkspaceTimestampedTooEarly,
    # Local operation errors
    FSPermissionError,
    FSNoAccessError,
    FSReadOnlyError,
    FSNotADirectoryError,
    FSFileNotFoundError,
    FSCrossDeviceError,
    FSFileExistsError,
    FSIsADirectoryError,
    FSDirectoryNotEmptyError,
    FSInvalidFileDescriptor,
    FSInvalidArgumentError,
    FSEndOfFileError,
    # Remote operation errors
    FSBackendOfflineError,
    FSRemoteManifestNotFound,
    FSRemoteManifestNotFoundBadVersion,
    FSRemoteManifestNotFoundBadTimestamp,
    FSRemoteBlockNotFound,
    FSRemoteSyncError,
    FSBadEncryptionRevision,
    FSSharingNotAllowedError,
    FSWorkspaceNoAccess,
    FSWorkspaceNoReadAccess,
    FSWorkspaceNoWriteAccess,
    FSWorkspaceNotInMaintenance,
    FSWorkspaceInMaintenance,
    FSUserNotFoundError,
    FSDeviceNotFoundError,
    FSInvalidTrustchainEror,
)
from guardata.client.fs.workspacefs import WorkspaceFS, WorkspaceFSTimestamped


__all__ = (
    "UserFS",
    "WorkspaceFS",
    "WorkspaceFSTimestamped",
    # Generic error classes
    "FSError",
    "FSOperationError",
    "FSLocalOperationError",
    "FSRemoteOperationError",
    # Misc errors
    "FSWorkspaceNotFoundError",
    "FSWorkspaceTimestampedTooEarly",
    # Local operation errors
    "FSPermissionError",
    "FSNoAccessError",
    "FSReadOnlyError",
    "FSNotADirectoryError",
    "FSFileNotFoundError",
    "FSCrossDeviceError",
    "FSFileExistsError",
    "FSIsADirectoryError",
    "FSDirectoryNotEmptyError",
    "FSInvalidFileDescriptor",
    "FSInvalidArgumentError",
    "FSEndOfFileError",
    # Remote operation error
    "FSBackendOfflineError",
    "FSRemoteManifestNotFound",
    "FSRemoteManifestNotFoundBadVersion",
    "FSRemoteManifestNotFoundBadTimestamp",
    "FSRemoteBlockNotFound",
    "FSRemoteSyncError",
    "FSBadEncryptionRevision",
    "FSSharingNotAllowedError",
    "FSWorkspaceNoAccess",
    "FSWorkspaceNoReadAccess",
    "FSWorkspaceNoWriteAccess",
    "FSWorkspaceNotInMaintenance",
    "FSWorkspaceInMaintenance",
    "FSUserNotFoundError",
    "FSDeviceNotFoundError",
    "FSInvalidTrustchainEror",
)
