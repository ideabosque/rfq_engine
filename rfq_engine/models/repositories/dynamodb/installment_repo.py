# -*- coding: utf-8 -*-
"""DynamoDB repository for Installment entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import installment as _installment_mod

class InstallmentRepository(EntityRepository):
    """DynamoDB repository for Installment entity."""

    @property
    def entity_type(self) -> str:
        return "installment"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        quote_uuid = keys.get("quote_uuid")
        installment_uuid = keys.get("installment_uuid")
        if not quote_uuid or not installment_uuid:
            return None
        count = _installment_mod.get_installment_count(
            quote_uuid, installment_uuid
        )
        if count == 0:
            return None
        return _normalize(
            _installment_mod.get_installment(quote_uuid, installment_uuid)
        )

    def count(self, **keys: Any) -> int:
        quote_uuid = keys.get("quote_uuid")
        installment_uuid = keys.get("installment_uuid")
        if not quote_uuid or not installment_uuid:
            return 0
        return _installment_mod.get_installment_count(quote_uuid, installment_uuid)

    def list(self, info: Any, **filters: Any) -> Any:
        return _installment_mod.resolve_installment_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _installment_mod.insert_update_installment(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _installment_mod.delete_installment(info, **kwargs)

    def get_type(self, info: Any, installment: Any) -> Any:
        return _installment_mod.get_installment_type(info, installment)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _installment_mod.resolve_installment(info, **kwargs)
