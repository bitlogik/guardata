# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from uuid import UUID

from guardata.api.protocol import OrganizationID
from guardata.backend.config import BaseBlockStoreConfig


class BaseBlockStoreComponent:
    async def read(self, organization_id: OrganizationID, id: UUID) -> bytes:
        """
        Raises:
            BlockNotFoundError
            BlockTimeoutError
        """
        raise NotImplementedError()

    async def create(self, organization_id: OrganizationID, id: UUID, block: bytes) -> None:
        """
        Raises:
            BlockAlreadyExistsError
            BlockTimeoutError
        """
        raise NotImplementedError()


def blockstore_factory(
    config: BaseBlockStoreConfig, postgresql_dbh=None
) -> BaseBlockStoreComponent:
    if config.type == "MOCKED":
        from guardata.backend.memory import MemoryBlockStoreComponent

        return MemoryBlockStoreComponent()

    elif config.type == "POSTGRESQL":
        from guardata.backend.postgresql import PGBlockStoreComponent

        if not postgresql_dbh:
            raise ValueError("PostgreSQL block store is not available")
        return PGBlockStoreComponent(postgresql_dbh)

    elif config.type == "S3":
        try:
            from guardata.backend.s3_blockstore import S3BlockStoreComponent

            return S3BlockStoreComponent(
                config.s3_region,
                config.s3_bucket,
                config.s3_key,
                config.s3_secret,
                config.s3_endpoint_url,
            )
        except ImportError as exc:
            raise ValueError("S3 block store is not available") from exc

    elif config.type == "SWIFT":
        try:
            from guardata.backend.swift_blockstore import SwiftBlockStoreComponent

            return SwiftBlockStoreComponent(
                config.swift_authurl,
                config.swift_tenant,
                config.swift_container,
                config.swift_user,
                config.swift_password,
            )
        except ImportError as exc:
            raise ValueError("Swift block store is not available") from exc

    elif config.type == "RAID1":
        from guardata.backend.raid1_blockstore import RAID1BlockStoreComponent

        blocks = [blockstore_factory(subconf, postgresql_dbh) for subconf in config.blockstores]

        return RAID1BlockStoreComponent(blocks)

    elif config.type == "RAID0":
        from guardata.backend.raid0_blockstore import RAID0BlockStoreComponent

        blocks = [blockstore_factory(subconf, postgresql_dbh) for subconf in config.blockstores]

        return RAID0BlockStoreComponent(blocks)

    elif config.type == "RAID5":
        from guardata.backend.raid5_blockstore import RAID5BlockStoreComponent

        if len(config.blockstores) < 3:
            raise ValueError(f"RAID5 block store needs at least 3 nodes")

        blocks = [blockstore_factory(subconf, postgresql_dbh) for subconf in config.blockstores]

        return RAID5BlockStoreComponent(blocks)

    else:
        raise ValueError(f"Unknown block store type `{config.type}`")
