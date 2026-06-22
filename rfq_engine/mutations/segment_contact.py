# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict

from graphene import Boolean, Field, Mutation, String

from ..models.repositories import get_repo
from ..types.segment_contact import SegmentContactType


class InsertUpdateSegmentContact(Mutation):
    segment_contact = Field(SegmentContactType)

    class Arguments:
        segment_uuid = String(required=True)
        email = String(required=True)
        contact_uuid = String(required=False)
        consumer_corp_external_id = String(required=False)
        updated_by = String(required=True)

    @staticmethod
    def mutate(
        root: Any, info: Any, **kwargs: Dict[str, Any]
    ) -> "InsertUpdateSegmentContact":
        try:
            segment_contact = get_repo("segment_contact").insert_update(info, **kwargs)
        except Exception as e:
            log = traceback.format_exc()
            info.context.get("logger").error(log)
            raise e

        return InsertUpdateSegmentContact(segment_contact=segment_contact)


class DeleteSegmentContact(Mutation):
    ok = Boolean()

    class Arguments:
        segment_uuid = String(required=True)
        email = String(required=True)

    @staticmethod
    def mutate(
        root: Any, info: Any, **kwargs: Dict[str, Any]
    ) -> "DeleteSegmentContact":
        try:
            ok = get_repo("segment_contact").delete(info, **kwargs)
        except Exception as e:
            log = traceback.format_exc()
            info.context.get("logger").error(log)
            raise e

        return DeleteSegmentContact(ok=ok)
