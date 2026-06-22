# -*- coding: utf-8 -*-
"""PostgreSQL repository for ItemCatalogRef entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL ItemCatalogRefModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, List, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.item_catalog_ref import (
    ItemCatalogRefListType,
    ItemCatalogRefType,
)
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.item_catalog_ref import ItemCatalogRefModel


class ItemCatalogRefPGRepository(EntityRepository):
    """PostgreSQL repository for ItemCatalogRef entity."""

    @property
    def entity_type(self) -> str:
        return "item_catalog_ref"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        catalog_ref_uuid = keys.get("catalog_ref_uuid")
        if not partition_key or not catalog_ref_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(ItemCatalogRefModel)
            .filter(
                ItemCatalogRefModel.partition_key == partition_key,
                ItemCatalogRefModel.catalog_ref_uuid == catalog_ref_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        catalog_ref_uuid = keys.get("catalog_ref_uuid")
        if not partition_key or not catalog_ref_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(ItemCatalogRefModel)
            .filter(
                ItemCatalogRefModel.partition_key == partition_key,
                ItemCatalogRefModel.catalog_ref_uuid == catalog_ref_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated item_catalog_ref list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        namespace = filters.get("namespace")
        item_uuid = filters.get("item_uuid")
        status = filters.get("status")

        query = session.query(ItemCatalogRefModel)
        if partition_key:
            query = query.filter(ItemCatalogRefModel.partition_key == partition_key)
        if namespace:
            query = query.filter(ItemCatalogRefModel.namespace == namespace)
        if item_uuid:
            query = query.filter(ItemCatalogRefModel.item_uuid == item_uuid)
        if status:
            query = query.filter(ItemCatalogRefModel.status == status)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(ItemCatalogRefModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        ref_list = [self.get_type(info, row) for row in rows]
        return ItemCatalogRefListType(item_catalog_ref_list=ref_list, total=total)

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        catalog_ref_uuid = kwargs.get("catalog_ref_uuid")

        try:
            if catalog_ref_uuid:
                # Update existing
                row = (
                    session.query(ItemCatalogRefModel)
                    .filter(
                        ItemCatalogRefModel.partition_key == partition_key,
                        ItemCatalogRefModel.catalog_ref_uuid == catalog_ref_uuid,
                    )
                    .first()
                )
                if not row:
                    # Create new with explicit UUID
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    # Update fields
                    field_map = [
                        "namespace",
                        "node_id",
                        "item_uuid",
                        "provider_item_uuid",
                        "extra",
                        "status",
                    ]
                    for field in field_map:
                        if field in kwargs:
                            val = kwargs[field]
                            setattr(
                                row,
                                field,
                                None if val == "null" else val,
                            )
                    # Recompute the index key whenever its identity components change.
                    if any(k in kwargs for k in ("namespace", "node_id")):
                        ns = kwargs.get("namespace", getattr(row, "namespace", "DEFAULT"))
                        nid = kwargs.get("node_id", getattr(row, "node_id", ""))
                        row.namespace_node_key = f"{ns}#{nid}"
                    if "item_uuid" in kwargs:
                        row.item_lookup_key = kwargs["item_uuid"]
                    row.updated_by = kwargs["updated_by"]
                    row.updated_at = pendulum.now("UTC")
            else:
                # Create new with server-generated UUID
                row = self._create_row(info, **kwargs)
                session.add(row)

            session.commit()
            session.refresh(row)
            return normalize_row(row)

        except Exception as e:
            session.rollback()
            if logger:
                logger.error(traceback.format_exc())
            raise e

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> ItemCatalogRefModel:
        partition_key = info.context.get("partition_key")
        catalog_ref_uuid = kwargs.get("catalog_ref_uuid")
        namespace = kwargs.get("namespace", "DEFAULT")
        node_id = kwargs.get("node_id", "")
        item_uuid = kwargs.get("item_uuid", "")

        cols = {
            "partition_key": partition_key,
            "updated_by": kwargs["updated_by"],
            "namespace": namespace,
            "node_id": node_id,
            "namespace_node_key": f"{namespace}#{node_id}",
            "item_uuid": item_uuid,
            "item_lookup_key": item_uuid,
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "provider_item_uuid",
            "extra",
            "status",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        if catalog_ref_uuid:
            cols["catalog_ref_uuid"] = catalog_ref_uuid

        return ItemCatalogRefModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        catalog_ref_uuid = kwargs.get("catalog_ref_uuid")

        try:
            # No child dependencies for ItemCatalogRef
            row = (
                session.query(ItemCatalogRefModel)
                .filter(
                    ItemCatalogRefModel.partition_key == partition_key,
                    ItemCatalogRefModel.catalog_ref_uuid == catalog_ref_uuid,
                )
                .first()
            )
            if not row:
                return True  # Already deleted

            session.delete(row)
            session.commit()
            return True

        except Exception as e:
            session.rollback()
            if logger:
                logger.error(traceback.format_exc())
            raise e

    def get_type(self, info: ResolveInfo, row: Any) -> ItemCatalogRefType:
        """Convert a SQLAlchemy row to ItemCatalogRefType."""
        data = normalize_row(row)
        if data is None:
            return None
        return ItemCatalogRefType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[ItemCatalogRefType]:
        """Resolve a single item_catalog_ref by catalog_ref_uuid."""
        session = Config.db_session
        partition_key = info.context.get("partition_key")

        if "catalog_ref_uuid" not in kwargs:
            return None

        count = self.count(
            partition_key=partition_key, catalog_ref_uuid=kwargs["catalog_ref_uuid"]
        )
        if count == 0:
            return None

        row = (
            session.query(ItemCatalogRefModel)
            .filter(
                ItemCatalogRefModel.partition_key == partition_key,
                ItemCatalogRefModel.catalog_ref_uuid == kwargs["catalog_ref_uuid"],
            )
            .first()
        )
        return self.get_type(info, row) if row else None

    def find_refs(
        self,
        info: ResolveInfo,
        node_ids: List[str],
        namespace: str = "DEFAULT",
        status: str = "active",
    ) -> List[ItemCatalogRefType]:
        """Find item catalog refs by node_ids within a namespace.

        Mirrors the DynamoDB find_item_catalog_refs helper using the
        namespace_node_key composite index.
        """
        session = Config.db_session
        partition_key = info.context.get("partition_key")
        refs: List[ItemCatalogRefType] = []

        for node_id in node_ids:
            namespace_node_key = f"{namespace}#{node_id}"
            query = session.query(ItemCatalogRefModel).filter(
                ItemCatalogRefModel.partition_key == partition_key,
                ItemCatalogRefModel.namespace_node_key == namespace_node_key,
            )
            if status is not None:
                query = query.filter(ItemCatalogRefModel.status == status)

            for row in query.all():
                refs.append(self.get_type(info, row))

        return refs


__all__ = ["ItemCatalogRefPGRepository"]