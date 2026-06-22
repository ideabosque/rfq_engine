# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict

from graphene import Boolean, Field, Mutation, String
from silvaengine_utility import JSONCamelCase
from silvaengine_utility import SafeFloat as Float

from ..models.repositories import get_repo
from ..types.provider_item import ProviderItemType


class InsertUpdateProviderItem(Mutation):
    provider_item = Field(ProviderItemType)

    class Arguments:
        provider_item_uuid = String(required=False)
        item_uuid = String(required=False)
        provider_corp_external_id = String(required=False)
        provider_item_external_id = String(required=False)
        base_price_per_uom = Float(required=False)
        item_spec = JSONCamelCase(required=False)
        availability_mode = String(required=False)
        updated_by = String(required=True)

    @staticmethod
    def mutate(
        root: Any, info: Any, **kwargs: Dict[str, Any]
    ) -> "InsertUpdateProviderItem":
        try:
            provider_item = get_repo("provider_item").insert_update(info, **kwargs)
        except Exception as e:
            log = traceback.format_exc()
            info.context.get("logger").error(log)
            raise e

        return InsertUpdateProviderItem(provider_item=provider_item)


class DeleteProviderItem(Mutation):
    ok = Boolean()

    class Arguments:
        provider_item_uuid = String(required=True)

    @staticmethod
    def mutate(root: Any, info: Any, **kwargs: Dict[str, Any]) -> "DeleteProviderItem":
        try:
            ok = get_repo("provider_item").delete(info, **kwargs)
        except Exception as e:
            log = traceback.format_exc()
            info.context.get("logger").error(log)
            raise e

        return DeleteProviderItem(ok=ok)
