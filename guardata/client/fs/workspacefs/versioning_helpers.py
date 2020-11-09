# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

"""Versioning helpers

This file implements the algorithm needed to reconstruct the history of a path. For that, we
recursively list versions and download manifests that matches the path for a given timeframe.

As a path can be valid or not during a timeframe depending on the fact that all the manifests
composing it can change, and as a manifest can also represent different files during it's life,
this implementation is quite complex.

This recursive implementation using tasks which are attributed a timestamp facilitates the
development of different loading strategies, concerning whether the possibility to prioritize
the download of the soonest needed manifests (which is already implemented), or the number of
concurrent downloads (which will be implemented in a next version).
"""

from heapq import heappush, heappop
import attr
import math
import trio
from functools import partial, total_ordering
from typing import List, Tuple, NamedTuple, Optional, Union, cast, Dict
from pendulum import DateTime

from guardata.api.protocol import DeviceID
from guardata.client.types import FsPath, EntryID
from guardata.client.fs.utils import is_file_manifest, is_folder_manifest, is_workspace_manifest
from guardata.client.fs.exceptions import FSRemoteManifestNotFound
from guardata.api.data import FileManifest, UserManifest, FolderManifest, WorkspaceManifest

RemoteManifest = Union[FileManifest, FolderManifest, UserManifest, WorkspaceManifest]


class EntryNotFound(Exception):
    pass


class ManifestCacheNotFound(Exception):
    pass


class ManifestCacheDownloadLimitReached(Exception):
    pass


class HistoryInconsistent(Exception):
    pass


class ManifestCacheInconsistent(HistoryInconsistent):
    pass


class VersionsListInconsistent(HistoryInconsistent):
    pass


class VersionListerTaskListNodeMissingParent(Exception):
    pass


SYNC_GUESSED_TIME_FRAME = 30


class TimestampBoundedData(NamedTuple):
    id: EntryID
    version: int
    early: DateTime
    late: DateTime
    creator: DeviceID
    updated: DateTime
    is_folder: bool
    size: Optional[int]
    source: Optional[FsPath]
    destination: Optional[FsPath]


class TimestampBoundedEntry(NamedTuple):
    id: EntryID
    version: int
    early: DateTime
    late: DateTime


class ManifestData(NamedTuple):
    creator: DeviceID
    updated: DateTime
    is_folder: bool
    size: Optional[int]


class ManifestDataAndPaths(NamedTuple):
    data: ManifestData
    source: Optional[FsPath]
    destination: Optional[FsPath]


@total_ordering
class TaskNode:
    def __init__(self, callable, timestamp, parent=None, children=[], completed=False):
        self.callable = callable
        self.timestamp = timestamp
        self.parent = parent
        self.children = []
        self.completed = False
        if self.parent:
            self.parent.children.append(self)

    def mark_complete(self):
        self.completed = True
        if self.parent:
            for brother in self.parent.children:
                if not brother.completed:
                    return
            self.parent.mark_complete()

    def get_earliest_completed_consecutive_timestamp(self):
        if self.completed:
            return self.timestamp
        results = []
        for child in self.children:
            results.append((child.get_earliest_completed_consecutive_timestamp(), child.completed))
        latest_invalid = max([r[0] for r in results if not r[1]], default=None)
        if not latest_invalid:
            return self.timestamp  # Special case where a job stopped before parent was updated
        return min(
            [r[0] for r in results if r[1] and r[0] > latest_invalid], default=latest_invalid
        )

    async def run(self):
        await self.callable(parent=self)  # Add current TaskNode as parent of the child
        for child in self.children:
            if not child.completed:
                return
        self.mark_complete()

    def __lt__(self, other):
        return self.timestamp < other.timestamp


@attr.s
class ManifestDataAndMutablePaths:
    """
    Contains a manifest and his known current, previous and next paths.
    Unlike ManifestDataAndPaths, attributes are mutable.
    """

    manifest: ManifestData = attr.ib()
    source_path: FsPath = attr.ib(default=None)
    destination_path: FsPath = attr.ib(default=None)
    current_path: FsPath = attr.ib(default=None)

    async def try_get_path_at_timestamp(
        self, manifest_cache, entry_id: EntryID, timestamp: DateTime
    ) -> Optional[FsPath]:
        try:
            return await manifest_cache.get_path_at_timestamp(entry_id, timestamp)
        except EntryNotFound:
            return None  # Just ignore when path is inconsistent

    async def populate_source_path(self, manifest_cache, entry_id, timestamp):
        self.source_path = await self.try_get_path_at_timestamp(manifest_cache, entry_id, timestamp)

    async def populate_destination_path(self, manifest_cache, entry_id, timestamp):
        self.destination_path = await self.try_get_path_at_timestamp(
            manifest_cache, entry_id, timestamp
        )

    async def populate_current_path(self, manifest_cache, entry_id, timestamp):
        self.current_path = await self.try_get_path_at_timestamp(
            manifest_cache, entry_id, timestamp
        )

    async def populate_paths(
        self, manifest_cache, entry_id: EntryID, early: DateTime, late: DateTime
    ):
        # TODO : Use future manifest source field to follow files and directories
        async with trio.open_service_nursery() as child_nursery:
            child_nursery.start_soon(
                self.populate_source_path, manifest_cache, entry_id, early.add(microseconds=-1)
            )
            child_nursery.start_soon(self.populate_destination_path, manifest_cache, entry_id, late)
            child_nursery.start_soon(self.populate_current_path, manifest_cache, entry_id, early)


class CacheEntry(NamedTuple):
    """
    Contains a manifest and the earliest and last timestamp for which its version has been returned
    """

    early: DateTime
    late: DateTime
    manifest: RemoteManifest


class ManifestCache:
    """
    Caches manifest through their version number, and the timeframe for which they could be
    obtained.
    """

    def __init__(self, remote_loader):
        self._manifest_cache = {}
        self._remote_loader = remote_loader

    def get(
        self, entry_id: EntryID, version=None, timestamp=None, expected_backend_timestamp=None
    ) -> RemoteManifest:
        """
        Tries to find specified manifest in cache, raises ManifestCacheNotFound otherwise

        Raises:
            ManifestCacheNotFound
        """
        if version:
            try:
                return self._manifest_cache[entry_id][version].manifest
            except KeyError:
                raise ManifestCacheNotFound
        elif timestamp:
            try:
                return next(
                    t.manifest
                    for t in self._manifest_cache[entry_id].values()
                    if t.early and t.late and t.early <= timestamp <= t.late
                )
            except (KeyError, StopIteration):
                raise ManifestCacheNotFound
        else:
            raise ManifestCacheNotFound

    def update(self, manifest: RemoteManifest, entry_id: EntryID, version=None, timestamp=None):
        """
        Updates manifest cache, increasing timeframe for a specified version if possible

        Raises:
            ManifestCacheNotFound
            ManifestCacheInconsistent
        """
        if manifest.id not in self._manifest_cache:
            self._manifest_cache[manifest.id] = {}
        cache_for_id = self._manifest_cache[manifest.id]
        if manifest.version not in cache_for_id:
            cache_for_id[manifest.version] = CacheEntry(timestamp, timestamp, manifest)
        elif timestamp:
            if (
                cache_for_id[manifest.version].late is None
                or timestamp > cache_for_id[manifest.version].late
            ):
                cache_for_id[manifest.version] = CacheEntry(
                    cache_for_id[manifest.version].early, timestamp, manifest
                )
            if (
                cache_for_id[manifest.version].early is None
                or timestamp < cache_for_id[manifest.version].early
            ):
                cache_for_id[manifest.version] = CacheEntry(
                    timestamp, cache_for_id[manifest.version].late, manifest
                )
        # Check inconsistency
        keys = sorted([*cache_for_id.keys()])
        index = keys.index(manifest.version)
        if (
            index > 0
            and cache_for_id[keys[index - 1]].late is not None
            and cache_for_id[manifest.version].early is not None
            and cache_for_id[keys[index - 1]].late > cache_for_id[manifest.version].early
        ):
            raise ManifestCacheInconsistent
        if (
            index < len(keys) - 1
            and cache_for_id[keys[index + 1]].early is not None
            and cache_for_id[manifest.version].late is not None
            and cache_for_id[keys[index + 1]].early < cache_for_id[manifest.version].late
        ):
            raise ManifestCacheInconsistent

    async def load(
        self,
        entry_id: EntryID,
        version: Optional[int] = None,
        timestamp: DateTime = None,
        expected_backend_timestamp: DateTime = None,
    ) -> Tuple[RemoteManifest, bool]:
        """
        Tries to find specified manifest in cache, tries to download it otherwise and updates cache

        Returns:
            A tuple containing the manifest that has been downloaded or retrieved from then cache,
            and a boolean indicating if a download was required

        Raises:
            FSError
            FSBackendOfflineError
            FSWorkspaceInMaintenance
            FSRemoteManifestNotFound
            FSBadEncryptionRevision
            FSWorkspaceNoAccess
        """
        try:
            return (
                self.get(
                    entry_id,
                    version=version,
                    timestamp=timestamp,
                    expected_backend_timestamp=expected_backend_timestamp,
                ),
                False,
            )
        except ManifestCacheNotFound:
            pass
        manifest = await self._remote_loader.load_manifest(
            entry_id,
            version=version,
            timestamp=timestamp,
            expected_backend_timestamp=expected_backend_timestamp,
        )
        self.update(manifest, entry_id, version=version, timestamp=timestamp)
        return (manifest, True)

    async def get_path_at_timestamp(self, entry_id: EntryID, timestamp: DateTime) -> FsPath:
        """
        Find a path for an entry_id at a specific timestamp.

        If the path is broken, will raise an EntryNotFound exception. All the other exceptions are
        thrown by the ManifestCache.

        Raises:
            FSError
            FSBackendOfflineError
            FSWorkspaceInMaintenance
            FSBadEncryptionRevision
            FSWorkspaceNoAccess
            EntryNotFound
        """
        # Get first manifest
        try:
            current_id = entry_id
            current_manifest, _ = await self.load(current_id, timestamp=timestamp)
        except FSRemoteManifestNotFound:
            raise EntryNotFound(entry_id)

        # Loop over parts
        parts = []
        while not is_workspace_manifest(current_manifest):
            # Get the manifest
            try:
                current_manifest = cast(Union[FolderManifest, FileManifest], current_manifest)
                parent_manifest, _ = await self.load(current_manifest.parent, timestamp=timestamp)
                parent_manifest = cast(Union[FolderManifest, WorkspaceManifest], parent_manifest)
            except FSRemoteManifestNotFound:
                raise EntryNotFound(entry_id)

            # Find the child name
            for name, child_id in parent_manifest.children.items():
                if child_id == current_id:
                    parts.append(name)
                    break
            else:
                raise EntryNotFound(entry_id)

            # Continue until root is found
            current_id = current_manifest.parent
            current_manifest = parent_manifest

        # Return the path
        return FsPath("/" + "/".join(reversed(parts)))


class ManifestCacheCounter:
    """
    Exposes a ManifestCache but simplifies the count of backend calls

    The number of downloads allowed is unlimited if limit is None or 0

    Raises:
        ManifestCacheDownloadLimitReached
    """

    def __init__(self, manifest_cache: ManifestCache, limit: Optional[int]):
        self._manifest_cache = manifest_cache
        self.counter = 0
        self.limit = limit or math.inf

    async def load(
        self, entry_id: EntryID, version=None, timestamp=None, expected_backend_timestamp=None
    ) -> RemoteManifest:
        if self.counter >= self.limit:
            raise ManifestCacheDownloadLimitReached
        manifest, was_downloaded = await self._manifest_cache.load(
            entry_id, version, timestamp, expected_backend_timestamp
        )
        if was_downloaded:
            self.counter += 1
        return manifest

    async def get_path_at_timestamp(self, entry_id: EntryID, timestamp: DateTime) -> FsPath:
        """
        Simpler not to count manifest used for pathfinding as they are probably already cached
        """
        return await self._manifest_cache.get_path_at_timestamp(entry_id, timestamp)


class VersionsListCache:
    """
    Caches results of the remote_loader.list_versions calls (working on EntryIDs).

    Caches thoses in the instance of this class. No garbage collection is done for now, as this
    class is only instanciated during the list_versions execution.
    """

    def __init__(self, remote_loader):
        self._versions_list_cache = {}
        self._remote_loader = remote_loader

    async def load(self, entry_id: EntryID):
        """
        Raises:
            FSError
            FSBackendOfflineError
            FSWorkspaceInMaintenance
            FSRemoteManifestNotFound
        """
        if entry_id in self._versions_list_cache:
            return self._versions_list_cache[entry_id]
        self._versions_list_cache[entry_id] = await self._remote_loader.list_versions(entry_id)
        return self._versions_list_cache[entry_id]


class VersionListerTaskList:
    """
    Enables prioritization of tasks, as it is better to be able to configure it that way

    This class uses both an heapq to enables us to always access the latest timestamp of the tasks
    in linear time, and a tree to keep track of completed and uncompleted task
    This tree is useful when the detection of the last valid date at which we can provide a
    continuous list is required
    """

    def __init__(self, manifest_cache, versions_list_cache):
        self.heapq_tasks = []
        self.task_tree = None
        self.manifest_cache = manifest_cache
        self.versions_list_cache = versions_list_cache
        self.workers = 0

    def add(self, node_task):
        heappush(self.heapq_tasks, node_task)
        if not node_task.parent:
            if self.task_tree:
                raise VersionListerTaskListNodeMissingParent
            self.task_tree = node_task

    def is_empty(self):
        return self.heapq_tasks == []

    async def execute_one(self):
        try:
            task = heappop(self.heapq_tasks)
        except IndexError:
            return
        await task.run()

    async def execute_worker(self, workers_limit, nursery):
        if self.workers == workers_limit or self.is_empty():
            return
        self.workers += 1
        while not self.is_empty():
            if self.workers < workers_limit:
                nursery.start_soon(self.execute_worker, workers_limit, nursery)
            await self.execute_one()
        self.workers -= 1

    async def execute(self, workers=1):
        async with trio.open_service_nursery() as nursery:
            nursery.start_soon(self.execute_worker, workers, nursery)


class VersionLister:
    """
    This class builds a version tree of a path to allow obtention of a version list.

    As we both have multiple versions of manifests for the same entry_id, and in some conditions
    entry_ids that change paths, we need a way to keep track of all those changes.
    So, we need to list versions of the different manifests composing the path, and the children of
    the dir matching pathname, recursively. By that we must also keep track of timeframes at which
    a manifest at a specific version corresponds to a part of the path.
    We also prioritize obtention of the latest used manifests at specific versions so that if a
    download cache limit is set, as many version entries as possible will be available. It is then
    also possible to re-launch the algorithm another time, using the same cache, which enables it
    to continue the download of the manifests where it stopped.
    """

    def __init__(
        self,
        workspace_fs,
        manifest_cache: Optional[ManifestCache] = None,
        versions_list_cache: Optional[VersionsListCache] = None,
    ):
        self.manifest_cache = manifest_cache or ManifestCache(workspace_fs.remote_loader)
        self.versions_list_cache = versions_list_cache or VersionsListCache(
            workspace_fs.remote_loader
        )
        self.workspace_fs = workspace_fs

    async def list(
        self,
        path: FsPath,
        skip_minimal_sync: bool = True,
        starting_timestamp: Optional[DateTime] = None,
        ending_timestamp: Optional[DateTime] = None,
        max_manifest_queries: Optional[int] = None,
        workers: int = 0,
    ) -> Tuple[List[TimestampBoundedData], bool]:
        """
        Returns:
            A tuple containing a list of TimestampBoundedData and a bool indicating wether the
            download limit has been reached.
            If workers is 0, start adaptive behaviour
        Raises:
            FSError
            FSBackendOfflineError
            FSWorkspaceInMaintenance
            FSRemoteManifestNotFound
            ManifestCacheInconsistent
            VersionsListInconsistent
        """
        version_lister_one_shot = VersionListerOneShot(
            self.workspace_fs, path, self.manifest_cache, self.versions_list_cache
        )
        return await version_lister_one_shot.list(
            path,
            skip_minimal_sync=skip_minimal_sync,
            starting_timestamp=starting_timestamp,
            ending_timestamp=ending_timestamp,
            max_manifest_queries=max_manifest_queries,
            workers=workers,
        )


class VersionListerOneShot:
    def __init__(
        self,
        workspace_fs,
        path,
        manifest_cache: Optional[ManifestCache] = None,
        versions_list_cache: Optional[VersionsListCache] = None,
    ):
        self.manifest_cache = manifest_cache or ManifestCache(workspace_fs.remote_loader)
        self.versions_list_cache = versions_list_cache or VersionsListCache(
            workspace_fs.remote_loader
        )
        self.workspace_fs = workspace_fs
        self.target = path
        self.return_dict: Dict[TimestampBoundedEntry, ManifestDataAndPaths] = {}

    async def list(
        self,
        path: FsPath,
        skip_minimal_sync: bool = True,
        starting_timestamp: Optional[DateTime] = None,
        ending_timestamp: Optional[DateTime] = None,
        max_manifest_queries: Optional[int] = None,
        workers: int = 0,
    ) -> Tuple[List[TimestampBoundedData], bool]:
        """
        Returns:
            A tuple containing a list of TimestampBoundedData and a bool indicating wether the
            download limit has been reached.
            If workers is 0, start adaptive behaviour
        Raises:
            FSError
            FSBackendOfflineError
            FSWorkspaceInMaintenance
            FSRemoteManifestNotFound
        """
        if workers == 0:
            distance = len(path.parts)
            if distance < 2:
                workers = 3
            elif distance == 2:
                workers = 5
            else:
                workers = 10
        root_manifest = await self.workspace_fs.transactions._get_manifest(
            self.workspace_fs.workspace_id
        )
        download_limit_reached = True
        download_limit = None
        try:
            self.task_list = VersionListerTaskList(
                ManifestCacheCounter(self.manifest_cache, max_manifest_queries),
                self.versions_list_cache,
            )
            self.task_list.add(
                TaskNode(
                    partial(
                        self._populate_tree_list_versions,
                        0,
                        root_manifest.id,
                        starting_timestamp or root_manifest.created,
                        ending_timestamp or DateTime.now(),
                    ),
                    starting_timestamp or root_manifest.created,
                )
            )
            await self.task_list.execute(workers=workers)
        except ManifestCacheDownloadLimitReached:
            download_limit_reached = self.task_list.task_tree.completed
            download_limit = self.task_list.task_tree.get_earliest_completed_consecutive_timestamp()
        versions_list = [
            TimestampBoundedData(
                id=id,
                version=version,
                early=early,
                late=late,
                creator=value.data.creator,
                updated=value.data.updated,
                is_folder=value.data.is_folder,
                size=value.data.size,
                source=value.source,
                destination=value.destination,
            )
            for (id, version, early, late), value in sorted(
                self.return_dict.items(),
                key=lambda item: (item[0].late, item[0].id, item[0].version),
            )
            if download_limit_reached or (download_limit and early < download_limit)
        ]
        return (self._sanitize_list(versions_list, skip_minimal_sync), download_limit_reached)

    def _sanitize_list(self, versions_list, skip_minimal_sync):
        previous = None
        new_list = []
        # Merge duplicates with overlapping time frames as it can be caused by an update of a
        # parent dir, also, if option is set, remove what can be guessed as empty manifests set
        # before parent during sync
        for item in versions_list:
            if previous is not None:
                # If same entry_id and version
                if previous.id == item.id and previous.version == item.version:
                    # If same timestamp, only parent directory updated
                    if previous.late == item.early:
                        # Update source FsPath for current entry
                        previous = TimestampBoundedData(
                            id=item.id,
                            version=item.version,
                            early=previous.early,
                            late=item.late,
                            creator=item.creator,
                            updated=item.updated,
                            is_folder=item.is_folder,
                            size=item.size,
                            source=previous.source,
                            destination=item.destination,
                        )
                        continue
                # If option is set, same entry_id, previous version is 0 bytes
                if (
                    skip_minimal_sync
                    and previous.id == item.id
                    and previous.version == item.version - 1
                    and previous.version == 1
                    and previous.size == 0  # Empty file (would be None for dir)
                    and previous.is_folder == item.is_folder
                    and previous.late == item.early
                    and previous.late < previous.early.add(seconds=SYNC_GUESSED_TIME_FRAME)
                    and not previous.source
                ):
                    previous = item
                    continue
                new_list.append(previous)
            previous = item
        if previous:
            new_list.append(previous)
        return new_list

    async def _populate_tree_load(
        self,
        path_level: int,
        entry_id: EntryID,
        early: DateTime,
        late: DateTime,
        version_number: int,
        expected_timestamp: DateTime,
        next_version_number: int,
        parent: TaskNode,
    ):
        if early > late:
            return
        manifest = await self.task_list.manifest_cache.load(
            entry_id, version=version_number, expected_backend_timestamp=expected_timestamp
        )
        data = ManifestDataAndMutablePaths(
            ManifestData(
                manifest.author,
                manifest.updated,
                is_folder_manifest(manifest),
                None if not is_file_manifest(manifest) else manifest.size,
            )
        )
        if len(self.target.parts) == path_level:
            await data.populate_paths(self.task_list.manifest_cache, entry_id, early, late)
            self.return_dict[
                TimestampBoundedEntry(manifest.id, manifest.version, early, late)
            ] = ManifestDataAndPaths(
                data=data.manifest,
                source=data.source_path if data.source_path != data.current_path else None,
                destination=data.destination_path
                if data.destination_path != data.current_path
                else None,
            )
        else:
            if not is_file_manifest(manifest):  # If it is a file, just ignores current path
                for child_name, child_id in manifest.children.items():
                    if child_name == self.target.parts[path_level]:
                        return await self._populate_tree_list_versions(
                            path_level + 1, child_id, early, late, parent
                        )

    async def _populate_tree_list_versions(
        self,
        path_level: int,
        entry_id: EntryID,
        early: DateTime,
        late: DateTime,
        parent: Optional[TaskNode],
    ):
        # TODO : Check if directory, melt the same entries through different parent
        versions = await self.task_list.versions_list_cache.load(entry_id)
        for version, (timestamp, creator) in versions.items():
            next_version = min((v for v in versions if v > version), default=None)
            if next_version and next_version != version + 1:
                raise VersionsListInconsistent
            self.task_list.add(
                TaskNode(
                    partial(
                        self._populate_tree_load,
                        path_level=path_level,
                        entry_id=entry_id,
                        early=max(early, timestamp),
                        late=late
                        if next_version not in versions
                        else min(late, versions[next_version][0]),
                        version_number=version,
                        expected_timestamp=timestamp,
                        next_version_number=next_version,
                    ),
                    max(early, timestamp),
                    parent=parent,
                )
            )
