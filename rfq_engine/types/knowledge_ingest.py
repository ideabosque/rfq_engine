#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
GraphQL types for the RFQ → knowledge-engine ingestion bridge.

Errors are returned in-band as ``status`` / ``error_code`` /
``error_message`` rather than raised as GraphQL errors — the same
philosophy as ``CatalogInquiryResultType``.
"""
from __future__ import annotations

__author__ = "bibow"

from graphene import Int, List, ObjectType, String


class KnowledgeIngestResultType(ObjectType):
    """
    In-band result for one ingested unit.

    ``status`` is one of ``ok`` / ``skipped`` / ``not_found`` /
    ``not_supported`` / ``configuration_error`` / ``access_denied`` /
    ``system_timeout`` / ``error`` (honest per-item accounting, T2.5).
    For file ingestion ``source_id`` carries the KE knowledge-source id
    instead of ``knowledge_id``.
    """

    status = String()
    entity_type = String()
    entity_uuid = String()
    knowledge_id = String()
    source_id = String()
    domain_id = String()
    type_id = String()
    idempotency_key = String()
    error_code = String()
    error_message = String()
    processing_stage = String(
        description="metadata_stored for entity upserts; import_submitted for "
        "file import acknowledgement. Neither guarantees LLM processing or embeddings."
    )


class KnowledgeIngestBatchType(ObjectType):
    """Batch envelope: counters plus per-item result rows (T2.5)."""

    requested = Int()
    ingested = Int()
    failed = Int()
    results = List(KnowledgeIngestResultType)
