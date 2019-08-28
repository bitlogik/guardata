# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import attr
import functools
from typing import Optional, Tuple
from pendulum import Pendulum, now as pendulum_now
from hashlib import sha256

from parsec.types import UUID4
from parsec.crypto import SecretKey
from parsec.serde import fields, OneOfSchema, validate, post_load
from parsec.api.protocol import DeviceID, RealmRole
from parsec.api.data import (
    BaseSchema,
    BaseData,
    WorkspaceEntry,
    BlockAccess,
    BlockID,
    UserManifest as RemoteUserManifest,
    Manifest as RemoteManifest,
)
from parsec.core.types import EntryID, EntryIDField


__all__ = (
    "WorkspaceEntry",  # noqa: Republishing
    "BlockAccess",  # noqa: Republishing
    "BlockID",  # noqa: Republishing
    "WorkspaceRole",
)


# Cheap rename
WorkspaceRole = RealmRole


class ChunkID(UUID4):
    pass


ChunkIDField = fields.uuid_based_field_factory(ChunkID)


@functools.total_ordering
class Chunk(BaseData):
    """Represents a chunk of a data in file manifest.

    The raw data is identified by its `id` attribute and is aligned using the
    `raw_offset` attribute with respect to the file addressing. The raw data
    size is stored as `raw_size`.

    The `start` and `stop` attributes then describes the span of the actual data
    still with respect to the file addressing.

    This means the following rule applies:
        raw_offset <= start < stop <= raw_start + raw_size

    Access is an optional block access that can be used to produce a remote manifest
    when the chunk corresponds to an actual block within the context of this manifest.
    """

    class SCHEMA_CLS(BaseSchema):
        id = ChunkIDField(required=True)
        start = fields.Integer(required=True, validate=validate.Range(min=0))
        stop = fields.Integer(required=True, validate=validate.Range(min=1))
        raw_offset = fields.Integer(required=True, validate=validate.Range(min=0))
        raw_size = fields.Integer(required=True, validate=validate.Range(min=1))
        access = fields.Nested(BlockAccess.SCHEMA_CLS, required=True, allow_none=True)

        @post_load
        def make_obj(self, data):
            return Chunk(**data)

    id: ChunkID
    start: int
    stop: int
    raw_offset: int
    raw_size: int
    access: Optional[BlockAccess]

    # Ordering

    def __lt__(self, other: object) -> bool:
        if isinstance(other, int):
            return self.start.__lt__(other)
        raise TypeError

    def __eq__(self, other: object) -> bool:
        if isinstance(other, int):
            return self.start.__eq__(other)
        if isinstance(other, Chunk):
            return attr.astuple(self).__eq__(attr.astuple(other))
        raise TypeError

    # Properties

    @property
    def is_block(self):
        # Requires an access
        if self.access is None:
            return False
        # Pseudo block
        if not self.is_pseudo_block:
            return False
        # Offset inconsistent
        if self.raw_offset != self.access.offset:
            return False
        # Size inconsistent
        if self.raw_size != self.access.size:
            return False
        return True

    @property
    def is_pseudo_block(self):
        # Not left aligned
        if self.start != self.raw_offset:
            return False
        # Not right aligned
        if self.stop != self.raw_offset + self.raw_size:
            return False
        return True

    # Create

    @classmethod
    def new(cls, start: int, stop: int) -> "Chunk":
        assert start < stop
        return cls(
            id=ChunkID(),
            start=start,
            stop=stop,
            raw_offset=start,
            raw_size=stop - start,
            access=None,
        )

    @classmethod
    def from_block_acess(cls, block_access: BlockAccess):
        return cls(
            id=ChunkID(block_access.id),
            raw_offset=block_access.offset,
            raw_size=block_access.size,
            start=block_access.offset,
            stop=block_access.offset + block_access.size,
            access=block_access,
        )

    # Evolve

    def evolve_as_block(self, data: bytes) -> "Chunk":
        # No-op
        if self.is_block:
            return self

        # Check alignement
        if self.raw_offset != self.start:
            raise TypeError("This chunk is not aligned")

        # Craft access
        access = BlockAccess(
            id=BlockID(self.id),
            key=SecretKey.generate(),
            offset=self.start,
            size=self.stop - self.start,
            digest=sha256(data).digest(),
        )

        # Evolve
        return self.evolve(access=access)

    # Export

    def get_block_access(self) -> BlockAccess:
        if not self.is_block:
            raise TypeError("This chunk does not correspond to a block")
        return self.access


class LocalUserManifestSchema(BaseSchema):
    type = fields.CheckedConstant("local_user_manifest", required=True)
    base = fields.Nested(RemoteUserManifest.SCHEMA_CLS, required=True, allow_none=True)
    id = EntryIDField(required=True)
    need_sync = fields.Boolean(required=True)
    updated = fields.DateTime(required=True)
    last_processed_message = fields.Integer(required=True, validate=validate.Range(min=0))
    workspaces = fields.FrozenList(fields.Nested(WorkspaceEntry.SCHEMA_CLS), required=True)

    @post_load
    def make_obj(self, data):
        data.pop("type")
        return LocalUserManifest(**data)


class LocalManifest(BaseData):
    class SCHEMA_CLS(OneOfSchema):
        type_field = "type"
        type_field_remove = False
        type_schemas = {
            "local_user_manifest": LocalUserManifestSchema,
            # "local_workspace_manifest": LocalWorkspaceManifestSchema,
            # "local_file_manifest": LocalFileManifestSchema,
            # "local_folder_manifest": LocalFolderManifestSchema,
        }

        def get_obj_type(self, obj):
            return obj["type"]

    @classmethod
    def from_remote(cls, remote: RemoteManifest):
        # TODO: temporary hack
        from parsec.api.data import (
            FileManifest as RemoteFileManifest,
            FolderManifest as RemoteFolderManifest,
            WorkspaceManifest as RemoteWorkspaceManifest,
        )
        from parsec.core.types import LocalFileManifest, LocalFolderManifest, LocalWorkspaceManifest

        if isinstance(remote, RemoteFileManifest):
            return LocalFileManifest.from_remote(remote)
        elif isinstance(remote, RemoteFolderManifest):
            return LocalFolderManifest.from_remote(remote)
        elif isinstance(remote, RemoteWorkspaceManifest):
            return LocalWorkspaceManifest.from_remote(remote)
        else:
            return LocalUserManifest.from_remote(remote)


class LocalUserManifest(LocalManifest):
    SCHEMA_CLS = LocalUserManifestSchema

    base: Optional[RemoteUserManifest]
    id: EntryID
    need_sync: bool
    updated: Pendulum
    last_processed_message: int
    workspaces: Tuple[WorkspaceEntry, ...]

    @classmethod
    def new_placeholder(cls, id: EntryID = None) -> "LocalUserManifest":
        return cls(
            base=None,
            id=id or EntryID(),
            need_sync=True,
            updated=pendulum_now(),
            last_processed_message=0,
            workspaces=(),
        )

    @property
    def created(self):
        return self.base.created if self.base else self.updated

    @property
    def base_version(self):
        return self.base.version if self.base else 0

    @property
    def is_placeholder(self):
        return self.base is None

    @classmethod
    def from_remote(cls, remote: RemoteUserManifest) -> "LocalUserManifest":
        return cls(
            base=remote,
            id=remote.id,
            need_sync=False,
            updated=remote.updated,
            last_processed_message=remote.last_processed_message,
            workspaces=remote.workspaces,
        )

    def to_remote(self, author: DeviceID, timestamp: Pendulum) -> RemoteUserManifest:
        return RemoteUserManifest(
            author=author,
            timestamp=timestamp,
            id=self.id,
            version=self.base_version + 1,
            created=self.created,
            updated=self.updated,
            last_processed_message=self.last_processed_message,
            workspaces=self.workspaces,
        )

    def get_workspace_entry(self, workspace_id: EntryID) -> WorkspaceEntry:
        return next((w for w in self.workspaces if w.id == workspace_id), None)

    def evolve_and_mark_updated(self, **data) -> "LocalUserManifest":
        if "updated" not in data:
            data["updated"] = pendulum_now()
        data.setdefault("need_sync", True)
        return attr.evolve(self, **data)

    def evolve_workspaces_and_mark_updated(self, *data) -> "LocalUserManifest":
        workspaces = {**{w.id: w for w in self.workspaces}, **{w.id: w for w in data}}
        return self.evolve_and_mark_updated(workspaces=tuple(workspaces.values()))

    def evolve_workspaces(self, *data) -> "LocalUserManifest":
        workspaces = {**{w.id: w for w in self.workspaces}, **{w.id: w for w in data}}
        return self.evolve(workspaces=tuple(workspaces.values()))
