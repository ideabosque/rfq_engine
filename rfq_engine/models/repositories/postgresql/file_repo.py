# -*- coding: utf-8 -*-
"""PostgreSQL repository for File entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL FileModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.file import FileListType, FileType
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.file import FileModel


class FilePGRepository(EntityRepository):
    """PostgreSQL repository for File entity."""

    @property
    def entity_type(self) -> str:
        return "file"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        request_uuid = keys.get("request_uuid")
        file_name = keys.get("file_name")
        if not request_uuid or not file_name:
            return None
        session = Config.db_session
        row = (
            session.query(FileModel)
            .filter(
                FileModel.request_uuid == request_uuid,
                FileModel.file_name == file_name,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        request_uuid = keys.get("request_uuid")
        file_name = keys.get("file_name")
        if not request_uuid or not file_name:
            return 0
        session = Config.db_session
        return (
            session.query(FileModel)
            .filter(
                FileModel.request_uuid == request_uuid,
                FileModel.file_name == file_name,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated file list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        request_uuid = filters.get("request_uuid")
        email = filters.get("email")

        query = session.query(FileModel)
        if request_uuid:
            query = query.filter(FileModel.request_uuid == request_uuid)
        if email:
            query = query.filter(FileModel.email == email)
        if partition_key:
            query = query.filter(FileModel.partition_key == partition_key)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(FileModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        file_list = [self.get_type(info, row) for row in rows]
        return FileListType(file_list=file_list, total=total)

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        request_uuid = kwargs.get("request_uuid")
        file_name = kwargs.get("file_name")

        try:
            if file_name:
                # Update existing (composite PK: request_uuid + file_name)
                row = (
                    session.query(FileModel)
                    .filter(
                        FileModel.request_uuid == request_uuid,
                        FileModel.file_name == file_name,
                    )
                    .first()
                )
                if not row:
                    # Create new with explicit file_name (no server default)
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    field_map = [
                        "email",
                        "partition_key",
                    ]
                    for field in field_map:
                        if field in kwargs:
                            val = kwargs[field]
                            setattr(
                                row,
                                field,
                                None if val == "null" else val,
                            )
                    row.updated_by = kwargs["updated_by"]
                    row.updated_at = pendulum.now("UTC")
            else:
                # file_name is required (part of PK, no server default)
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
        finally:
            Config.db_session.remove()

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> FileModel:
        partition_key = kwargs.get("partition_key") or info.context.get("partition_key")

        cols = {
            "request_uuid": kwargs["request_uuid"],
            "file_name": kwargs["file_name"],
            "email": kwargs.get("email"),
            "partition_key": partition_key,
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        return FileModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        request_uuid = kwargs.get("request_uuid")
        file_name = kwargs.get("file_name")

        try:
            # No child dependencies for files
            row = (
                session.query(FileModel)
                .filter(
                    FileModel.request_uuid == request_uuid,
                    FileModel.file_name == file_name,
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
        finally:
            Config.db_session.remove()

    def get_type(self, info: ResolveInfo, row: Any) -> FileType | None:
        """Convert a SQLAlchemy row to FileType."""
        data = normalize_row(row)
        if data is None:
            return None
        return FileType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[FileType]:
        """Resolve a single file by request_uuid and file_name."""
        request_uuid = kwargs.get("request_uuid")
        file_name = kwargs.get("file_name")
        if not request_uuid or not file_name:
            return None

        count = self.count(
            request_uuid=request_uuid, file_name=file_name
        )
        if count == 0:
            return None

        row = (
            Config.db_session.query(FileModel)
            .filter(
                FileModel.request_uuid == request_uuid,
                FileModel.file_name == file_name,
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["FilePGRepository"]