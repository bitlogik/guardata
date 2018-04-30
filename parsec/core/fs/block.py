import attr
import nacl.encoding
import nacl.hash
from nacl.bindings.utils import sodium_memcmp
from uuid import uuid4

from parsec.utils import generate_sym_key
from parsec.core.fs.base import SecurityError
from parsec.core.fs.access import BaseAccess


class BlockHashError(SecurityError):
    status = "invalid_hash"


@attr.s(slots=True, frozen=True)
class BaseBlockAccess(BaseAccess):
    id = attr.ib()
    key = attr.ib()
    offset = attr.ib()
    size = attr.ib()
    digest = attr.ib()

    async def fetch(self):
        # First look into local storage
        block = await self._fs.blocks_manager.fetch_from_local(self.id, self.key)
        if not block:
            # Go the much slower way of asking backend
            # Note this can raise a `BackendOfflineError` exception
            block = await self._fs.blocks_manager.fetch_from_backend(self.id, self.key)
            # TODO: save block as cache local storage ?
            if not block:
                raise RuntimeError("No block with access %s" % self)

            digest = nacl.hash.sha256(block, encoder=nacl.encoding.Base64Encoder)
            if not sodium_memcmp(digest, self.digest):
                raise BlockHashError("Digest error for block with access %s" % self)

        return block

    def dump(self):
        return {
            "id": self.id,
            "key": self.key,
            "offset": self.offset,
            "size": self.size,
            "digest": self.digest,
        }


@attr.s(slots=True, frozen=True)
class BaseDirtyBlockAccess(BaseAccess):
    id = attr.ib(default=attr.Factory(lambda: uuid4().hex))
    key = attr.ib(default=attr.Factory(generate_sym_key))
    offset = attr.ib(default=0)
    size = attr.ib(default=0)
    digest = attr.ib(default=None)

    async def fetch(self):
        # Dirty blocks are only stored into the local storage
        block = await self._fs.blocks_manager.fetch_from_local(self.id, self.key)
        if not block:
            raise RuntimeError("No block with access %s" % self)

            digest = nacl.hash.sha256(block, encoder=nacl.encoding.Base64Encoder)
            if not sodium_memcmp(digest, self.digest):
                raise BlockHashError("Digest error for block with access %s" % self)

        return block

    def dump(self):
        return {
            "id": self.id,
            "key": self.key,
            "offset": self.offset,
            "size": self.size,
            "digest": self.digest,
        }


class BaseBlock:

    def __init__(self, access, data=None):
        self._access = access
        self._data = data

    def need_flush(self):
        return bool(self._data)

    @property
    def offset(self):
        return self._access.offset

    @property
    def size(self):
        return self._access.size

    @property
    def end(self):
        return self.offset + self.size

    @property
    def _fs(self):
        raise NotImplementedError()

    async def sync(self):
        if not self.is_dirty:
            return

        if not self._data:
            raise RuntimeError("Nothing to sync")

        dirty_access = self._access
        # TODO: add a lock ? should be more secure, but on the other hand
        # a block is sync only once, really close to where is has been created.
        id = await self._fs.blocks_manager.sync_new_block_with_backend(dirty_access.key, self._data)
        self._access = self._fs._block_access_cls(
            id, dirty_access.key, dirty_access.offset, dirty_access.size, dirty_access.digest
        )

    def is_dirty(self):
        return isinstance(self._access, BaseDirtyBlockAccess)

    async def flush_data(self):
        if self._data is None:
            return

        await self._fs.blocks_manager.flush_on_local(self._access.id, self._access.key, self._data)
        self._data = None

    async def fetch_data(self):
        if self._data is not None:
            return self._data

        return await self._access.fetch()