# Integration Certification Report — RFQ Engine ↔ knowledge_engine Migration (KGE → KE)

> Status: **Gateway E2E certified — docker-banyanos-gateway live run of INT-019/020 battery (13/13) on travel sample data; full staging run + sign-off still pending.**
> Scope: `docs/KGE_TO_KNOWLEDGE_ENGINE_MIGRATION_PLAN.md` Phases 0–4
> Report date: 2026-10-19
> Environment: dev (offline verification) / staging (live stages pending)
> Related SOP: `docs/INTEGRATION_SCENARIOS_SOP.md` INT-019 / INT-020 / INT-021

---

## Executive Summary

The RFQ Engine's knowledge-layer integration was migrated from
`knowledge_graph_engine` (KGE) to the Banyanos `knowledge_engine` (KE, v3.0.0),
and a new RFQ → KE ingestion bridge was delivered. This report certifies the
migration in two stages:

1. **Offline verification (complete)** — handler/mutation code, unit tests,
   GraphQL-document validation against the live KE schema, deploy-manifest
   actions, and the KE baseline suite.
2. **Live staging certification (pending)** — INT-019 (inquiry, all modes),
   INT-020 (ingestion bridge), INT-021 (resilience drills) executed against
   staging KE with real PostgreSQL/Neo4j/LLM.

Certification is **blocked** on the live stages and the data-backfill
reconciliation (plan T4.2).

## Scope

| In | Out |
|---|---|
| `inquire_catalog` read path (semantic/ask/graph/cypher + node-by-id) | KE-internal certification (KE's own suite is a dependency, not in scope) |
| Ingestion bridge (single/batch/file mutations) | KGE decommission execution (tracked as plan T4.3) |
| `ItemCatalogRef` node_id re-pointing + write→read loop | Live backfill of historical KGE content (plan T4.2) |
| Error mapping / resilience behavior | |

## Dependency Readiness

| Dependency | Status | Evidence |
|---|---|---|
| Gateway route manifest `module_routes/knowledge_engine.yaml` (T0.1) | **Verified + booted** | Manifest exists: `POST /{endpoint_id}/knowledge_engine_graphql`, `dispatch: knowledge_engine.main:dispatch_graphql`, `config_init_style: kwargs`, auth bridge `banyan` |
| RFQ setting `functs_on_local.knowledge_engine_graphql` (T0.3) | Code-ready | Handler checks + fails fast with in-band `configuration_error`; staging value to be set by ops |
| Tenant provisioning: KE domain `rfq-catalog` + 6 knowledge types (T0.2) | **Tooling delivered — execution pending** | `rfq_engine/tests/prepare_test_data/prepare_ke_provisioning.py` (idempotent; emits `knowledge_engine_ingest` settings + `ke_*` env lines) |
| KE baseline suite (T0.4) | **Executed — fully green** | `tests/unit`: **592/592**; `tests/e2e`: **42/42** (banyanos venv, 2026-10-19, after installing the sibling `capability_engine` package that the 2 earlier failures were missing). No PostgreSQL/Neo4j/LLM connection failures. |
| RFQ unit suites | **Executed** | 27 handler tests + 32 ingestion tests green; full RFQ suite parity with pre-change baseline (526 passed; pre-existing cache-management/SafeFloat issues unchanged on `HEAD`) |
| GraphQL documents vs KE schema (T1.1) | **Verified** | All 10 RFQ-side documents + 4 provisioning documents + 3 seed-script documents + 6 backfill/shadow-script documents validate against the live graphene schemas (23 total) |
| Dual-run shadow tooling (T4.1) | **Delivered — soak pending** | `prepare_test_data/shadow_compare_catalog_inquiry.py`: per-case contract check (legacy `{results, total}` envelope on both backends), error-code diff, coverage ratio (`SHADOW_COVERAGE_RATIO`), `shadow_report.json` PASS/REVIEW verdict |
| Backfill + reconciliation tooling (T4.2) | **Delivered — execution pending** | `prepare_test_data/backfill_catalog_to_knowledge.py`: batched bridge replay of all items + provider items, `ItemCatalogRef.node_id` re-point with dry-run mode, KE `knowledgeDomain` entity/relation/vector counts, `backfill_reconciliation.json` output |

## Function Results (offline)

| # | Function | Result |
|---|---|---|
| 1 | `inquire_catalog` semantic mode → KE `searchKnowledges`, legacy `{results, total, page, limit}` envelope | **PASS** (unit: envelope + invocation variables asserted) |
| 2 | `inquire_catalog` ask / graph / cypher modes | **PASS** (unit: routing + payload passthrough) |
| 3 | `inquire_catalog(nodeId)` → KE `knowledge(id)` | **PASS** (unit: restriction lifted; payload asserted) |
| 4 | Legacy KGE mode aliases (`text2cypher`/`vector`/`hybrid`) | **PASS** (unit: remapped + logged) |
| 5 | Unknown mode → in-band `operation_unsupported` | **PASS** |
| 6 | Missing `queryText` → in-band `system_error` | **PASS** |
| 7 | `BIZ_KNOWLEDGE_*` error mapping (timeout/not-found/access-denied/validation) | **PASS** (unit matrix) |
| 8 | Backend flag `catalog_knowledge_backend` → KGE dual-run path | **PASS** (unit: legacy path + node-lookup rejection preserved) |
| 9 | `ingestKnowledgeFromRfq` create path (code/name/markdown/tags/metadata/derived key) | **PASS** |
| 10 | Upsert-by-code: changed entity → `updateKnowledge` with `expectedUpdatedAt` | **PASS** |
| 11 | Replay of unchanged entity → no-op (no duplicate KE entry) | **PASS** |
| 12 | Lost create race / version conflict → converge via retry | **PASS** |
| 13 | Settings fail-fast (`configuration_error`) when `knowledge_engine_ingest` missing | **PASS** |
| 14 | `ingestCatalogToKnowledge` batch accounting (requested/ingested/failed + per-item rows) | **PASS** |
| 15 | `ingestRfqFileToKnowledge` presigned-URL and base64 transports; no-transport → `configuration_error` | **PASS** |
| 16 | `ItemCatalogRef` auto-sync (`node_id` = KE knowledge id; disable flag; sync failure non-fatal) | **PASS** |
| 17 | Deploy manifest actions registered; label drift fixed (`itemPriceTierList`, `discountPrompt`) | **PASS** |
| 18 | Provisioning script documents vs KE schema | **PASS** |
| 19 | Seed script (catalog_refs) documents vs RFQ schema | **PASS** |
| 20 | **LIVE gateway E2E battery (S1–S13, travel sample)** — single ingest, idempotent replay, write→read loop, semantic envelope, batch (10/10), partial-failure attribution, in-band errors, ask/graph/cypher contracts, inline-base64 file import | **13/13 PASS** (docker-banyanos-gateway; report: `gateway_e2e_report.json`) |
| 21 | **LIVE KE provisioning via gateway** — domain `rfq-catalog` + 6 knowledge types through `knowledge_engine_graphql` with the platform admin | **PASS** |

## Live Staging Results (pending)

| Scenario | Status | Notes |
|---|---|---|
| INT-019 inquire_catalog against KE (all modes + node inquiry) | **PASS (gateway E2E, 2026-10-20)** | docker-banyanos-gateway live run: semantic envelope {results,total,page,limit} ok, graph/cypher return nodes/edges, in-band error contracts verified (unknown mode, missing node) — 13/13 battery on travel sample data (`rfq_engine/tests/prepare_test_data/gateway_e2e_report.json`) |
| INT-020 ingestion bridge (single/batch with partial-failure drill/file/idempotent replay) | **PASS (gateway E2E, 2026-10-20)** | Single ingest ok; idempotent replay returned the same knowledgeId; write→read loop closed via nodeId inquiry; batch of 5 items × (item+provider item) = 10/10 ok; bogus-uuid partial failure attributed in-band as not_found; inline-base64 file import returned sourceId; catalog-ref auto-sync present | Requires T0.2 provisioning + KE write permission for the RFQ operator |
| INT-021 resilience drills (KE down / Neo4j down / LLM down / timeout / backend flag flip) | **PENDING** | Requires staging fault injection |
| T4.1 dual-run shadow comparison (N days) | **PENDING** | Flag supports `"kge"` ↔ `"knowledge_engine"`; run `shadow_compare_catalog_inquiry.py` over the soak window for per-case contract/coverage evidence |
| T4.2 data backfill + `ItemCatalogRef` re-point reconciliation | **PENDING** | Run `backfill_catalog_to_knowledge.py` (batched bridge replay + ref re-point + KE domain counts); verify `backfill_reconciliation.json` |

## Failure and Resilience Results (offline)

| Injected fault | Expected behavior | Result |
|---|---|---|
| KE funct unconfigured | In-band `configuration_error` (no transport error) | **PASS** (unit) |
| KE invocation raises `BIZ_KNOWLEDGE_TIMEOUT` / timeout string | In-band `system_timeout` | **PASS** (unit) |
| KE invocation raises `BIZ_KNOWLEDGE_NOT_FOUND` | In-band `not_found` | **PASS** (unit) |
| KE invocation raises `BIZ_KNOWLEDGE_ACCESS_DENIED` / `_PERMISSION` | In-band `access_denied` | **PASS** (unit) |
| Other KE business errors | In-band `system_error` with engine code in message | **PASS** (unit) |
| Batch partial failure | Per-item `not_found`/`error` rows; healthy items unaffected | **PASS** (unit) |
| Catalog-ref sync failure | Logged warning; ingestion result unaffected | **PASS** (unit) |

## Defect Analysis

| ID | Severity | Description | Status |
|---|---|---|---|
| KEM-001 | Info | KE baseline: 2 unit-test failures due to missing sibling `capability_engine` package (graceful `PENDING_MANUAL` fallback); no KE code defect | **Resolved** — `capability_engine` installed into the shared venv; suite re-run green (592/592 unit + 42/42 e2e) |
| KEM-003 | Medium | KE's GraphQL error envelope drops the structured ``BIZ_KNOWLEDGE_*`` code (only the human message survives serialization), so RFQ-side error granularity degrades to ``system_error`` for not-found/access cases (in-band contract still holds) | Open — KE-side fix recommended (embed ``error_code`` in the message or as a GraphQL extension); RFQ's code-based mapping activates automatically once codes are present |
| KEM-004 | Info | KE ``ImportTaskType``/``RefreshTaskType`` lack the defensive datetime coercion ``KnowledgeType`` already has; a space-separated timestamp can fail graphene DateTime serialization and poison the import response | Open — worked around in RFQ by selecting a minimal field set (no ``createdAt``) in the import documents; KE-side fix recommended |
| KEM-005 | High (fixed) | ``docker-banyanos-gateway/docker-compose.yml`` mounted the pg volume at ``/var/lib/postgresql`` while the image's ``VOLUME`` lives at ``/var/lib/postgresql/data``; an anonymous volume shadowed the data path so **every container recreate wiped the entire database** | **Fixed** — volume retargeted to ``/var/lib/postgresql/data``; data now survives recreates |
| KEM-006 | Medium (fixed) | RFQ's gateway manifest lacked ``auth_bridge: banyan``: only FlexJWT ran, so ``state.user`` carried raw token claims without roles and every in-process RFQ→KE mutation failed with ``knowledge:write`` denied | **Fixed** — ``auth_bridge: banyan`` added to ``module_routes/rfq_engine.yaml`` (local gateway overlay); E2E confirms role resolution + PDP grants flow |
| KEM-002 | Accepted-risk | RFQ pre-existing failures (2 × cache-management, 12 × SafeFloat integration errors) reproduce identically on unmodified `HEAD`; out of migration scope | Tracked separately |

## Open Risks and Mitigation Plan

| Risk | Mitigation | Owner |
|---|---|---|
| R1 inquiry contract drift for existing consumers | `CatalogInquiryResultType` unchanged; envelope adapter; dual-run shadow (T4.1) before cutover | Ops + eng |
| R2 missing KE domain/type ids at runtime | Provisioning script + fail-fast `configuration_error`; never auto-create at runtime | Ops |
| R3 Neo4j/LLM outage degrades KE (no PG graph fallback) | In-band error mapping; INT-021 drills; backend flag flip | Ops |
| R7 batch ingestion overload (LLM-driven extraction) | Bounded concurrency (≤10); per-item accounting; scheduled mode later | Eng |
| R8 `node_id` semantics change confuses integrators | SOP notes + backfill re-points rows + auto-sync on ingestion | Eng + docs |

## Certification Decision

**Conditional — offline stages certified, live stages pending.** The inquiry
swap and ingestion bridge are code-complete, unit-certified, and
schema-validated. Final certification requires: T0.2 provisioning executed per
staging tenant, INT-019/020/021 executed live with evidence per the SOP's
GraphQL-call recording rules, and the backfill reconciliation clean.

## Sign-off

| Role | Name | Status |
|---|---|---|
| Engineering | | Pending live stages |
| Operations (KE owner) | | Pending |
| Quality | | Pending |