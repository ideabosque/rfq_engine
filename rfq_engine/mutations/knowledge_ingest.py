#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Mutations for the RFQ → knowledge-engine ingestion bridge (Phase 2).

All three mutations return in-band results: handler-level failures are
reported through ``status`` / ``error_code`` / ``error_message`` on the
result type rather than raised as GraphQL errors. Only hard precondition
violations (missing arguments, missing partition key) raise, matching
the rest of the mutation surface.
"""
from __future__ import annotations

__author__ = "bibow"

import traceback
from typing import Any, Dict

from graphene import Boolean, Field, List, Mutation, String

from ..handlers.catalog.ingest import (
    dispatch_ingest_catalog,
    dispatch_ingest_file,
    dispatch_ingest_knowledge,
)
from ..types.knowledge_ingest import (
    KnowledgeIngestBatchType,
    KnowledgeIngestResultType,
)


class IngestKnowledgeFromRfq(Mutation):
    """Ingest a single RFQ entity into the knowledge engine."""

    result = Field(KnowledgeIngestResultType)

    class Arguments:
        entity_type = String(
            required=True,
            description="One of: item, provider_item, request, quote, "
            "bundle, discount_prompt",
        )
        uuid = String(
            required=True,
            description="Entity uuid (quote also requires parent_uuid)",
        )
        parent_uuid = String(
            required=False,
            description="Parent uuid (request_uuid for quote entities)",
        )
        idempotency_key = String(
            required=False,
            description="Optional client key; derived keys are prefixed "
            "with it when supplied",
        )

    @staticmethod
    def mutate(
        root: Any, info: Any, **kwargs: Dict[str, Any]
    ) -> "IngestKnowledgeFromRfq":
        try:
            result = dispatch_ingest_knowledge(info, **kwargs)
        except Exception as e:
            log = traceback.format_exc()
            info.context.get("logger").error(log)
            raise e

        return IngestKnowledgeFromRfq(result=KnowledgeIngestResultType(**result))


class IngestCatalogToKnowledge(Mutation):
    """Batch-ingest catalog items (plus their provider items)."""

    result = Field(KnowledgeIngestBatchType)

    class Arguments:
        item_uuids = List(String, required=True)
        include_provider_items = Boolean(required=False, default_value=True)
        idempotency_key = String(required=False)

    @staticmethod
    def mutate(
        root: Any, info: Any, **kwargs: Dict[str, Any]
    ) -> "IngestCatalogToKnowledge":
        try:
            batch = dispatch_ingest_catalog(info, **kwargs)
        except Exception as e:
            log = traceback.format_exc()
            info.context.get("logger").error(log)
            raise e

        results = [
            KnowledgeIngestResultType(**row) for row in batch.get("results", [])
        ]
        return IngestCatalogToKnowledge(
            result=KnowledgeIngestBatchType(
                requested=batch.get("requested"),
                ingested=batch.get("ingested"),
                failed=batch.get("failed"),
                results=results,
            )
        )


class IngestRfqFileToKnowledge(Mutation):
    """Import one RFQ request file into the knowledge engine."""

    result = Field(KnowledgeIngestResultType)

    class Arguments:
        request_uuid = String(required=True)
        file_name = String(required=True)
        file_url = String(
            required=False,
            description="Presigned URL (recommended transport, D2)",
        )
        file_content = String(
            required=False,
            description="Inline base64 file content (small files)",
        )
        file_format = String(
            required=False,
            description="MIME type for inline content",
        )
        idempotency_key = String(required=False)

    @staticmethod
    def mutate(
        root: Any, info: Any, **kwargs: Dict[str, Any]
    ) -> "IngestRfqFileToKnowledge":
        try:
            result = dispatch_ingest_file(info, **kwargs)
        except Exception as e:
            log = traceback.format_exc()
            info.context.get("logger").error(log)
            raise e

        return IngestRfqFileToKnowledge(result=KnowledgeIngestResultType(**result))