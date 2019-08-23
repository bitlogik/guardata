# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest

from parsec.core.fs.local_storage import LocalStorage
from parsec.core.fs import FSLocalMissError
from parsec.core.types import (
    LocalUserManifest,
    LocalWorkspaceManifest,
    LocalFolderManifest,
    LocalFileManifest,
    EntryID,
    Chunk,
)


def create_entry(device, type=LocalUserManifest):
    entry_id = EntryID()
    if type is LocalUserManifest:
        manifest = LocalUserManifest(
            author=device.device_id, base_version=0, is_placeholder=True, need_sync=True
        )
    elif type is LocalWorkspaceManifest:
        manifest = type.make_placeholder(entry_id=entry_id, author=device.device_id)
    else:
        manifest = type.make_placeholder(
            entry_id=entry_id, author=device.device_id, parent_id=EntryID()
        )
    return entry_id, manifest


@pytest.mark.trio
async def test_lock_required(tmpdir, alice):
    entry_id, manifest = create_entry(alice)

    with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als:

        msg = f"Entry `{entry_id}` modified without beeing locked"

        with pytest.raises(RuntimeError) as exc:
            als.set_manifest(entry_id, manifest)
        assert str(exc.value) == msg

        with pytest.raises(RuntimeError) as exc:
            als.ensure_manifest_persistent(entry_id)
        assert str(exc.value) == msg

        with pytest.raises(RuntimeError) as exc:
            als.clear_manifest(entry_id)
        assert str(exc.value) == msg

        # Note: `get_manifest` doesn't need a lock before use


@pytest.mark.trio
async def test_basic_set_get_clear(tmpdir, alice):
    entry_id, manifest = create_entry(alice)

    with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als:

        async with als.lock_entry_id(entry_id):

            # 1) No data
            with pytest.raises(FSLocalMissError):
                als.get_manifest(entry_id)

            # 2) Set data
            als.set_manifest(entry_id, manifest)
            assert als.get_manifest(entry_id) == manifest
            # Make sure data are not only stored in cache
            with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als2:
                assert als2.get_manifest(entry_id) == manifest

            # 3) Clear data
            als.clear_manifest(entry_id)
            with pytest.raises(FSLocalMissError):
                als.get_manifest(entry_id)
            with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als3:
                with pytest.raises(FSLocalMissError):
                    assert als3.get_manifest(entry_id) == manifest


@pytest.mark.trio
async def test_cache_set_get(tmpdir, alice):
    entry_id, manifest = create_entry(alice)

    with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als:

        async with als.lock_entry_id(entry_id):

            # 1) Set data
            als.set_manifest(entry_id, manifest, cache_only=True)
            assert als.get_manifest(entry_id) == manifest
            with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als2:
                with pytest.raises(FSLocalMissError):
                    als2.get_manifest(entry_id)

            # 2) Clear should work as expected
            als.clear_manifest(entry_id)
            with pytest.raises(FSLocalMissError):
                als.get_manifest(entry_id)

            # 3) Re-set data
            als.set_manifest(entry_id, manifest, cache_only=True)
            assert als.get_manifest(entry_id) == manifest
            with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als3:
                with pytest.raises(FSLocalMissError):
                    als3.get_manifest(entry_id)

            # 4) Flush data
            als.ensure_manifest_persistent(entry_id)
            assert als.get_manifest(entry_id) == manifest
            with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als4:
                assert als4.get_manifest(entry_id) == manifest


@pytest.mark.trio
async def test_cache_flushed_on_exit(tmpdir, alice):
    entry_id, manifest = create_entry(alice)

    with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als:
        async with als.lock_entry_id(entry_id):
            als.set_manifest(entry_id, manifest, cache_only=True)

    with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als2:
        assert als2.get_manifest(entry_id) == manifest


@pytest.mark.trio
async def test_clear_cache(tmpdir, alice):
    entry_id1, manifest1 = create_entry(alice)
    entry_id2, manifest2 = create_entry(alice)

    with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als:
        async with als.lock_entry_id(entry_id1):
            als.set_manifest(entry_id1, manifest1)
        async with als.lock_entry_id(entry_id2):
            als.set_manifest(entry_id2, manifest2, cache_only=True)

        als.clear_memory_cache()

        assert als.get_manifest(entry_id1) == manifest1
        with pytest.raises(FSLocalMissError):
            als.get_manifest(entry_id2)


@pytest.mark.parametrize(
    "type", [LocalUserManifest, LocalWorkspaceManifest, LocalFolderManifest, LocalFileManifest]
)
@pytest.mark.trio
async def test_serialize_types(tmpdir, alice, type):
    entry_id, manifest = create_entry(alice, type)
    with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als:
        async with als.lock_entry_id(entry_id):
            als.set_manifest(entry_id, manifest)

    with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als2:
        assert als2.get_manifest(entry_id) == manifest


@pytest.mark.trio
async def test_serialize_non_empty_local_file_manifest(tmpdir, alice):
    entry_id, manifest = create_entry(alice, LocalFileManifest)
    chunk1 = Chunk.new_chunk(0, 7).evolve_as_block(b"0123456")
    chunk2 = Chunk.new_chunk(7, 8)
    chunk3 = Chunk.new_chunk(8, 10)
    blocks = (chunk1, chunk2), (chunk3,)
    manifest = manifest.evolve_and_mark_updated(blocksize=8, size=10, blocks=blocks)
    manifest.assert_integrity()
    with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als:
        async with als.lock_entry_id(entry_id):
            als.set_manifest(entry_id, manifest)

    with LocalStorage(alice.device_id, alice.local_symkey, tmpdir) as als2:
        assert als2.get_manifest(entry_id) == manifest