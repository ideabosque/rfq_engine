# RFQ Engine — KGE to `knowledge_engine` Migration Development Plan

> Project: `rfq_engine`
> Goal: replace the `knowledge_graph_engine` (KGE, `silvaengine/knowledge_graph_engine`) catalog integration with the new Banyanos `knowledge_engine` (`C:\Users\bibo7\gitrepo\banyanos\knowledge_engine`, v3.0.0), and add a new RFQ → knowledge ingestion bridge (a capability that does not exist today).
> Status: **In progress — Phases 1–3 implemented (inquiry swap, ingestion bridge, unit tests, SOP); Phase 0/4 operational tasks pending. See §13.**
> Last reviewed: 2026-10-19
> Verified against source on: 2026-10-19 (`rfq_engine` handlers/queries/types/tests, `banyanos/knowledge_engine` schema/main/mutations/types, both engines' integration SOPs)

---

## 1. Executive Summary

The RFQ Engine currently touches the knowledge layer in exactly one place: the
**`inquire_catalog`** GraphQL query, backed by `handlers/catalog/handler.py`, which invokes the
KGE `search` query in-process via `Invoker.invoke_funct_on_local`. The integration is
**read-only** — there is no function from RFQ Engine that ingests data into the knowledge
engine (the KGE `executeExtract` mutation is never called from this codebase).

We will replace KGE with the Banyanos `knowledge_engine` (KE) module and, in the same
program, deliver the **ingestion bridge** requested by the business: RFQ Engine mutations
that push catalog/pricing/RFQ data into the knowledge engine's managed knowledge
lifecycle (domains, types, versions, PII masking, graph + vector extraction).

Key drivers:

- **Ingestion capability**: KGE only exposed `executeExtract(text)`; KE exposes a full
  knowledge lifecycle (`createKnowledge`, `importKnowledge`, `importKnowledgeFromUrl`,
  `refreshKnowledge`) with domains, types, versions, publish review, and PII masking.
- **Same tenant model**: KE isolates by `partition_key` from `info.context["partition_key"]`
  (`endpoint_id#part_id`) — identical to RFQ Engine, so tenant context carries over 1:1.
- **Same deployment fabric**: KE is a SilvaEngine `Graphql` module
  (`knowledge_engine.main:dispatch_graphql`) mounted on `silvaengine_gateway` with a route
  manifest — the `Invoker.invoke_funct_on_local` pattern continues to work with a new funct key.
- **Richer inquiry**: KE offers semantic search (`searchKnowledges`), GraphRAG Q&A
  (`askKnowledgeBase`), graph visualization (`knowledgeGraph`), and Cypher query
  (`knowledgeGraphByCypher`) — enabling the currently-unsupported node-by-id inquiry.

The plan is phased: **Phase 0** (readiness) → **Phase 1** (inquiry swap) → **Phase 2**
(ingestion bridge, new capability) → **Phase 3** (tests & certification) → **Phase 4**
(cutover, data backfill, KGE decommission).

---

## 2. Current State — KGE Integration Inventory (verified 2026-10-19)

The entire RFQ → KGE surface. Every item below must be touched or re-verified.

| # | Artifact | Location | Role |
|---|---|---|---|
| C1 | `_KGE_SEARCH_QUERY` | `rfq_engine/handlers/catalog/handler.py` (~L46–L70) | GraphQL document executing KGE `search(queryText, searchMode, indexName, retrievalQuery, filters, topK, page, limit) { results query total page limit }` |
| C2 | `_search_inquiry()` | `rfq_engine/handlers/catalog/handler.py` (~L76) | Invokes KGE in-process: `Invoker.invoke_funct_on_local(logger, kge_setting, "knowledge_graph_graphql", query=..., variables=..., endpoint_id=..., part_id=...)`; wraps result into `CatalogResponse {ref, payload, fetched_at, ttl_seconds}` |
| C3 | `dispatch_inquire()` | `rfq_engine/handlers/catalog/handler.py` (~L163) | Public telemetry-wrapped entry; **raises `OperationUnsupportedError` for `node_id` inquiry** (KGE has no node-by-id query) |
| C4 | `resolve_inquire_catalog` | `rfq_engine/queries/catalog_inquiry.py` | GraphQL resolver for `query inquire_catalog`; translates `CatalogHandlerError` subclasses into in-band `error_code` / `error_message` |
| C5 | `CatalogInquiryResultType` | `rfq_engine/types/catalog_inquiry.py` | `{namespace, node_id, payload, fetched_at, ttl_seconds, error_code, error_message}` — **client-facing contract, must stay stable** |
| C6 | Settings | `handlers/config.py` + deployment settings | `functs_on_local.knowledge_graph_graphql` (required check in C2); `kge_pg_table_prefix` (copied into `kge_setting["pg_table_prefix"]` to survive Invoker Config re-initialization) |
| C7 | `ItemCatalogRef` entity | `models/{dynamodb,postgresql}/item_catalog_ref.py`, `migration/alembic/versions/0010_create_item_catalog_refs.py`, queries/mutations/types | Maps external KGE node (`node_id`) ↔ internal RFQ entity (`item_uuid` / optional `provider_item_uuid`) |
| C8 | Unit tests | `rfq_engine/tests/test_catalog_handler.py` (105L), `rfq_engine/tests/test_inquire_catalog.py` (414L) | KGE-mocked handler/resolver tests; INT-019 scenario |
| C9 | Test data script | `rfq_engine/tests/prepare_test_data/prepare_catalog_refs.py` | Builds `catalog_refs.json` from `products.json` + KGE (optional, "needs KGE") |
| C10 | Docs | `docs/INTEGRATION_SCENARIOS_SOP.md` (INT-019), `docs/ARCHITECTURE_AND_ER_DIAGRAMS*.md` references | KGE integration scenarios, mocked-live scope |
| C11 | Module docstring | `rfq_engine/handlers/catalog/__init__.py` | "Catalog inquiry invoked through the knowledge_graph_engine public API." |

**Confirmed non-integrations** (no action, recorded to prevent re-litigation):
full-tree grep shows **zero** calls to KGE `executeExtract`, `insertUpdateDocument`,
`insertUpdateGraphSchema`, or any KGE mutation from `rfq_engine`. Ingestion today is
done by direct clients of KGE (e.g., `mcp_kg_inquirer`, gateway routes), not by RFQ Engine.

---

## 3. Target State — Banyanos `knowledge_engine` (verified 2026-10-19)

### 3.1 Module identity

| Attribute | Value |
|---|---|
| Path | `C:\Users\bibo7\gitrepo\banyanos\knowledge_engine` (package `knowledge_engine`, v3.0.0) |
| Engine class | `KnowledgeEngine(Graphql)` — `knowledge_engine/main.py` |
| GraphQL entry / funct key | `knowledge_engine_graphql` |
| Gateway dispatch | `knowledge_engine.main:dispatch_graphql`; route `POST /{endpoint_id}/knowledge_engine_graphql`; route manifest `silvaengine_gateway/silvaengine_gateway/module_routes/knowledge_engine.yaml` (`handler_type: graphql`, `config_init_style: kwargs`) |
| API surface | 31 queries / 42 mutations; **every mutation requires `idempotencyKey: ID!`** |
| Error contract | `BusinessModuleError` subclasses, error codes `BIZ_KNOWLEDGE_*` (050001–050999) |
| Storage | PostgreSQL `tenant_knowledge_*` (14 tables, composite PK `(partition_key, id)`); Neo4j (graph + vector, **no PG graph fallback** — driver down = graph/vector queries raise); object storage (MinIO, S3 fallback); Elasticsearch BM25 (ILIKE fallback) |
| Tenant isolation | `partition_key` from `info.context["partition_key"]` — **identical model to RFQ Engine** |
| Config groups | `knowledge.default.embedding`, `llm` (+cross-encoder), `elasticsearch`, `neo4j`, `minio`, `knowledge.rls`, `knowledge.sync.outbox` — injected via gateway kwargs |

### 3.2 API mapping — KGE → knowledge_engine

| Capability | KGE (current) | knowledge_engine (target) | Migration note |
|---|---|---|---|
| Semantic search | `search(queryText, searchMode, ...)` → `{results, query, total, page, limit}` | `searchKnowledges(query: String!, limit: Int, domainIds: [ID])` → `[KnowledgeType]` | Primary replacement for `_KGE_SEARCH_QUERY`; response shape changes — adapter required (Phase 1, T1.2) |
| GraphRAG Q&A | `rag(queryText, prompt, topK)` | `askKnowledgeBase(question, domainIds, maxHops, topK, rerankTopK, sourceLevels)` → `AskResultType {answer, confidence, sources, graphPaths, retrievedChunks, usage}` | New optional mode behind `query.search_mode` |
| Graph visualization | (embedded in search payload) | `knowledgeGraph(domainIds, depth, limit)` → nodes + edges + degree | New optional mode |
| Cypher / text2cypher | `search(searchMode: "text2cypher", retrievalQuery)` | `knowledgeGraphByCypher(cypher: String!, limit)` → `KnowledgeGraphType` | `retrieval_query` argument maps to `cypher` |
| Node-by-id lookup | ❌ not exposed (C3 raises `OperationUnsupportedError`) | ✅ `knowledge(id: ID!)` → `KnowledgeType` | **Lift the restriction** (Phase 1, T1.3) |
| Ingest text | `executeExtract(text, graphSchema, ...)` | `createKnowledge(code, name, typeId, domainId, content, metadata, tags, automaticVectorization, ..., idempotencyKey)` | Foundation of the new ingestion bridge (Phase 2) |
| Ingest file | ❌ (`parse_file.py` only in KGE tests) | `importKnowledge(fileContent(base64), fileName, fileFormat, knowledgeTypeId, domainId, extractionRuleId, cleaningRuleId, idempotencyKey)` | Maps RFQ `File` entity (Phase 2, T2.6) |
| Ingest URL | ❌ | `importKnowledgeFromUrl(url, knowledgeTypeId, domainId, idempotencyKey)` | Presigned-S3-URL option for RFQ documents (Phase 2, decision D2) |
| Re-process | — | `refreshKnowledge(sourceId, mode, idempotencyKey)` | Re-extraction after rule changes |
| Schema mgmt | `insertUpdateGraphSchema` | `saveGraphSchema` (tenant singleton) | RFQ never calls this today; no RFQ-side change |
| Tenant node↔item mapping | `ItemCatalogRef.node_id` (KGE graph node) | `ItemCatalogRef.node_id` → now holds **KE `knowledge_id`** | Semantics change; keep table, update docs + test data (Phase 2, T2.7) |

### 3.3 Prerequisites imposed by KE (new, vs. KGE)

1. **`typeId` and `domainId` are required** by every ingestion mutation. RFQ Engine must
   reference a provisioned knowledge domain (e.g., `rfq-catalog`) and knowledge types
   (e.g., `product`, `provider-item`, `request`, `quote`, `bundle`, `discount-prompt`).
   Provisioned once per tenant in Phase 0 (T0.2), never created ad hoc by RFQ at runtime.
2. **Idempotency keys are mandatory** on mutations. RFQ must derive deterministic keys
   (see T2.4) or pass through client-supplied keys.
3. **LLM/embedding/Neo4j must be operational** for ingestion (extraction, vectorization)
   and for semantic search. Staging/dev config must include the `llm` and `neo4j` groups.
4. **Graph/vector queries fail hard** when Neo4j is unavailable (no PG fallback). The
   catalog handler must map these to in-band errors rather than 500s (T1.5).

---

## 4. Gap Analysis

| Gap | Impact | Resolution |
|---|---|---|
| Response shapes differ (`{results, total, page, limit}` vs `[KnowledgeType]`) | RFQ clients consume `inquire_catalog.payload` verbatim | Adapter in handler projects KE results to the existing payload envelope; `total` derived from list length when KE omits it |
| `search_mode` vocabulary differs (`text2cypher`, `vector`, `hybrid` vs `ask`/`graph`/`cypher`/`semantic`) | `query.search_mode` is client-visible | Keep RFQ-side mode names; add mapping table (T1.4); default mode `semantic` → `searchKnowledges` |
| No ingestion path exists at all | The requested business capability is new | Phase 2 delivers new mutations + handler + tests |
| `kge_pg_table_prefix` handling (Config re-init by Invoker) | KE tables are native `tenant_knowledge_*`; KE config is gateway kwargs-style | Re-verify Invoker re-init behavior against KE; if KE Config re-initialization with RFQ's setting dict breaks KE, keep an analogous `ke_setting` copy with KE-specific keys. Remove `kge_pg_table_prefix` after verification (T1.6, R4) |
| Timeout detection is string-sniffing (`"timeout" in message`) | KE raises structured `BIZ_KNOWLEDGE_*` errors | Prefer KE error codes; keep string sniff as belt-and-braces (T1.5) |
| ItemCatalogRef `node_id` semantics | Existing rows reference KGE nodes | Data backfill task (T4.2) re-points rows to KE knowledge IDs; docs updated |
| KGE `filters`/`indexName` arguments have no direct KE equivalent | Minor client-visible loss | Map `filters.domain_ids` → `domainIds`; document unsupported arguments in SOP |

---

## 5. Phased Plan

### Phase 0 — Environment & Deployment Readiness (no RFQ code changes)

| Task | Description | Acceptance |
|---|---|---|
| T0.1 Gateway mount | Add/verify `module_routes/knowledge_engine.yaml` (dispatch `knowledge_engine.main:dispatch_graphql`, `config_init_style: kwargs`, auth on). KE auto-discovers via sibling-repo scan — confirm `banyanos/knowledge_engine` lands on `sys.path` | `POST /{endpoint_id}/knowledge_engine_graphql` executes `knowledgeModuleConfig` in dev/staging; gateway `/health` 200 |
| T0.2 Tenant provisioning | Per staging tenant (`endpoint_id#part_id`): `createKnowledgeDomain` (e.g., `rfq-catalog`, domain type per KE enum) and `createKnowledgeType` entries for each RFQ entity type to be ingested. Record the returned `domainId`/`typeId` in rfq settings | Query `knowledgeDomains` / `knowledgeTypesTree` shows provisioned entries for both staging tenants (mirrors KE SOP tenants) |
| T0.3 RFQ settings | Add `functs_on_local.knowledge_engine_graphql` (same shape as the KGE entry). Keep the KGE entry during transition (dual-run, R1) | Handler config check passes; in-process `Invoker.invoke_funct_on_local` smoke query returns KE data |
| T0.4 KE baseline | Run KE's own suite (`pytest tests/unit tests/e2e -q`, 365-pass baseline) and its HTTP integration SOP in staging | KE green in staging; record version hash in the certification report |

### Phase 1 — Inquiry Swap (read path)

| Task | Description | Acceptance |
|---|---|---|
| T1.1 Query documents | Replace `_KGE_SEARCH_QUERY` with `_KE_SEARCH_QUERY` (`searchKnowledges`) plus `_KE_KNOWLEDGE_QUERY` (`knowledge(id)`), `_KE_ASK_QUERY` (`askKnowledgeBase`), `_KE_GRAPH_QUERY` (`knowledgeGraph`), `_KE_CYPHER_QUERY` (`knowledgeGraphByCypher`) | All documents execute verbatim against staging KE |
| T1.2 Search adapter | Rename `_search_inquiry` → routes by `query.search_mode` (default `semantic`); project `[KnowledgeType]` into the existing payload envelope `{results, total}`; keep `fetched_at` / `ttl_seconds`; `filters.domain_ids` → `domainIds` | `inquire_catalog` response is byte-shape-compatible for existing clients (same fields at top level) |
| T1.3 Node inquiry | Implement `node_id` inquiry via `knowledge(id)`; remove the `OperationUnsupportedError` branch in `dispatch_inquire` | `inquire_catalog(nodeId: ...)` returns a node payload; SOP updated |
| T1.4 Mode mapping | RFQ mode → KE field: `semantic`→`searchKnowledges`; `ask`→`askKnowledgeBase` (`query_text`→`question`); `graph`→`knowledgeGraph`; `cypher`→`knowledgeGraphByCypher` (`retrieval_query`→`cypher`); legacy KGE modes (`text2cypher`, `vector`, `hybrid`) map to nearest KE mode and are logged | Mapping unit-tested; unknown mode returns in-band `operation_unsupported` |
| T1.5 Error mapping | `BIZ_KNOWLEDGE_*` / `BusinessModuleError` → `CatalogHandlerError` subclasses (`system_error`, `system_timeout`, `operation_unsupported`); keep timeout string sniff as fallback; never raise out of the resolver (in-band contract, C4/C5) | Injected KE errors surface as `error_code`/`error_message`, no exceptions; KE-down and Neo4j-down drills pass |
| T1.6 Config cleanup | Verify Invoker Config re-init behavior against KE (see Gap R4). Remove `kge_pg_table_prefix` once verified; if needed, introduce `knowledge_engine_setting` overrides dict | Documented decision in this file; unit tests updated |
| T1.7 Tests | Update `test_catalog_handler.py` and `test_inquire_catalog.py`: mock `Invoker` with KE response shapes (KnowledgeType list, AskResultType, error dict with `BIZ_KNOWLEDGE_*`); add node-inquiry case | Unit suite green; INT-019 rewritten (T3.3) covers all modes |

### Phase 2 — Ingestion Bridge (NEW capability)

> This is the RFQ → knowledge-engine ingestion function requested by the business —
> it does not exist against KGE either (see §2, confirmed non-integrations).

| Task | Description | Acceptance |
|---|---|---|
| T2.1 Handler module | New `handlers/catalog/ingest.py` (or `handlers/knowledge_ingest/`): `dispatch_ingest_knowledge(info, ...)` with telemetry (`measure_handler_duration`, operation=`ingest`); reuses the same `Invoker` + setting-handling pattern as `_search_inquiry` | Handler unit-tested in isolation with mocked Invoker |
| T2.2 Mutation surface | New mutations wired into `schema.py` `Mutations` + `mutations/knowledge_ingest.py` + `types/knowledge_ingest.py`:<br>• `ingestKnowledgeFromRfq(entityType, uuid, idempotencyKey?)` — single entity<br>• `ingestCatalogToKnowledge(itemUuids, idempotencyKey?)` — batch (items + their provider items)<br>• `ingestRfqFileToKnowledge(requestUuid, fileName, idempotencyKey?)` — RFQ `File` → KE document import<br>Result type `KnowledgeIngestResultType {status, knowledgeId, domainId, typeId, errorCode, errorMessage, idempotencyKey}` — in-band errors, same philosophy as `CatalogInquiryResultType` | Schema introspection shows the new mutations; smoke in staging creates a real KE knowledge entry |
| T2.3 Content projection | Project RFQ entities to `KnowledgeCreateInput`:<br>`code` = `{entity_type}-{uuid}` (unique per tenant, mirrors KE `(partition_key, code)` UNIQUE); `name` = item/quote title; `content` = serialized entity (JSON or markdown projection — decision D1); `typeId`/`domainId` = from settings (T0.2); `metadata` = `{source: "rfq_engine", entity_type, uuid, endpoint_id, updated_at}`; `tags` = `[entity_type, item_type?, provider_corp_external_id?]`; `automaticVectorization` = true | Projection unit-tested per entity type; KE `knowledges(filter: {code})` finds the ingested entity |
| T2.4 Idempotency | Derive `idempotencyKey` = `rfq:{partition_key}:{entity_type}:{uuid}:{updated_at-hash}` when client omits it — deterministic, replay-safe on retry after `updated_at` changes | Replay same mutation twice → single KE entry (KE idempotency honored); second response returns existing state |
| T2.5 Batch semantics | `ingestCatalogToKnowledge` iterates with bounded concurrency (respect KE `max_concurrent_imports`, default 10); per-item in-band result rows (six-key honest accounting like KE `batchDeleteKnowledges`): `ok / not_found / access_denied / error / ...` | Batch of 50 items ingests in staging; partial-failure drill returns per-item attribution |
| T2.6 File ingestion | RFQ `File` records (S3/attachments on requests) → `importKnowledge` with base64 `fileContent` **or** `importKnowledgeFromUrl` with a presigned URL (decision D2); parse/chunk/PII-mask handled by KE pipeline | Sample request file round-trips: `knowledgeSources` shows the source; chunks present in PG/ES |
| T2.7 ItemCatalogRef sync | On successful ingestion, optionally auto-create `ItemCatalogRef` rows (`node_id` = KE `knowledge_id`); `node_id` semantics documented as KE knowledge ID | Ingestion then `inquire_catalog(nodeId: knowledgeId)` resolves end-to-end (write→read loop closed) |
| T2.8 Sync vs async | `createKnowledge` is synchronous but extraction/publishing is lifecycle-managed (`DRAFT → PROCESSING → PUBLISHED`); mutation returns KE status; re-sync/repair path = `refreshKnowledge` via a follow-up `refreshKnowledgeFromRfq` (stretch) | Documented status mapping in result type; PROCESSING states visible to callers |

### Phase 3 — Tests & Certification

| Task | Description | Acceptance |
|---|---|---|
| T3.1 Unit tests | New: `test_knowledge_ingest.py` (handler + projection + idempotency + error mapping, all mocked). Updated: catalog handler/inquiry tests (Phase 1) | `pytest rfq_engine/tests/ -q` green |
| T3.2 Test data | Update `prepare_catalog_refs.py` to emit KE-shaped `catalog_refs.json` (knowledge IDs); add ingestion fixtures | Test-data pipeline runs clean |
| T3.3 Integration SOP | Rewrite `docs/INTEGRATION_SCENARIOS_SOP.md`: **INT-019** = inquire via KE (all modes + node inquiry + failure injection); new **INT-020** = ingestion bridge (single/batch/file, idempotent replay, partial failure); new **INT-021** = resilience drills (KE unreachable, Neo4j down, LLM/embedding down, timeout) | SOP rows updated in the dependency/readiness tables; scenarios executable |
| T3.4 Certification report | Publish `docs/integration_certification_report_knowledge_engine.md` (mirror the existing DynamoDB/PostgreSQL certification reports): environment, versions, scenario results, gaps, sign-off | Report reviewed; live-KE sign-off obtained (INT-019/020/021 executed against staging) |
| T3.5 Regression sweep | Full grep: no `knowledge_graph_engine` / `kge` references in `rfq_engine` source (post Phase 4); all existing suites pass | Grep clean except this plan document |

### Phase 4 — Cutover, Backfill & Decommission

| Task | Description | Acceptance |
|---|---|---|
| T4.1 Dual-run flag | Transitional setting `catalog_knowledge_backend: "kge" | "knowledge_engine"` (default `kge` until certified); shadow-compare payloads in staging for N days | Shadow log shows ≥1:1 result coverage with no contract breaks |
| T4.2 Data backfill | Export existing KGE graph/document data per tenant → replay into KE via ingestion mutations (or KE-side loader); re-point `ItemCatalogRef.node_id` rows to KE knowledge IDs; verify counts | Backfill reconciliation report: entity/chunk/edge counts reconcile; spot-checked inquiries return equivalent results |
| T4.3 Hard cutover | Flip default to `knowledge_engine`; remove `_KGE_SEARCH_QUERY`, `functs_on_local.knowledge_graph_graphql`, `kge_pg_table_prefix`, and KGE mentions in docs (C10, C11) after one stabilization week | Grep clean; staging + production smoke green |
| T4.4 Rollback | Until T4.3, rollback = one setting flip back to `kge` (both entries kept). After T4.3, rollback = redeploy previous tag | Rollback rehearsed once in staging |

---

## 6. Code Change Inventory (by file)

| File | Change | Phase |
|---|---|---|
| `handlers/catalog/handler.py` | Replace KGE query documents; mode routing; payload adapter; error mapping; remove node_id restriction | 1 |
| `handlers/catalog/__init__.py` | Docstring: "knowledge_engine public API" | 1 |
| `handlers/catalog/ingest.py` *(new)* | `dispatch_ingest_knowledge` + projection + idempotency + batch + telemetry | 2 |
| `queries/catalog_inquiry.py` | No signature change; verify in-band error translation still holds | 1 |
| `types/catalog_inquiry.py` | Unchanged (contract stability); possibly widen docstring for new modes | 1 |
| `types/knowledge_ingest.py` *(new)* | `KnowledgeIngestResultType` + inputs | 2 |
| `mutations/knowledge_ingest.py` *(new)* | `IngestKnowledgeFromRfq`, `IngestCatalogToKnowledge`, `IngestRfqFileToKnowledge` | 2 |
| `schema.py` | Register new mutations in `Mutations`; docstring/query docs for new modes | 2 |
| `handlers/config.py` | `functs_on_local.knowledge_engine_graphql` required-check for ingest path; transitional `catalog_knowledge_backend` flag; remove KGE keys in Phase 4 | 1–4 |
| `main.py` (deploy manifest) | Add the new mutation actions (and fix pre-existing `discountRule`/`itemPriceTieList` label drift opportunistically) | 2 |
| `tests/test_catalog_handler.py`, `tests/test_inquire_catalog.py` | KE-shaped mocks; mode matrix; node inquiry | 1, 3 |
| `tests/test_knowledge_ingest.py` *(new)* | Ingestion handler/mutation tests | 2, 3 |
| `tests/prepare_test_data/prepare_catalog_refs.py` | KE knowledge IDs | 3 |
| `docs/INTEGRATION_SCENARIOS_SOP.md`, new certification report, this plan | SOP rows INT-019/020/021; certification; status updates | 3, 4 |

---

## 7. Test Matrix

| Suite | Scope | Backend |
|---|---|---|
| `test_catalog_handler.py` | Handler logic: mode routing, payload adapter, error mapping, timeout sniff, setting checks | Mocked `Invoker` |
| `test_inquire_catalog.py` | Resolver contract: top-level fields stable, in-band errors, node inquiry, all modes | Mocked `Invoker` |
| `test_knowledge_ingest.py` | Projection per entity, deterministic idempotency keys, batch accounting, KE error mapping, file ingestion | Mocked `Invoker` |
| INT-019/020/021 | Live staging: KE mounted on gateway, real PostgreSQL + Neo4j (+ ES/MinIO where configured), both staging tenants for isolation | Live |
| Full regression | `pytest rfq_engine/tests/ -q` plus KE's own 365-test baseline | Both |

---

## 8. Risks & Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | KE inquiry semantics differ enough to break existing `inquire_catalog` consumers | Keep `CatalogInquiryResultType` contract; payload adapter + dual-run shadow comparison (T4.1); SOP documents unsupported legacy arguments |
| R2 | Missing `domainId`/`typeId` prerequisites make ingestion fail at runtime | Provision in Phase 0 (T0.2); handler fails fast with in-band `configuration_error` if settings lack them; never auto-create domains/types from RFQ at runtime |
| R3 | Neo4j/LLM outages: KE fails hard (no PG graph fallback), degrading catalog inquiry and ingestion | In-band error mapping (T1.5); resilience drills (INT-021); optional `catalog_knowledge_backend` flag to disable inquiry gracefully |
| R4 | Invoker Config re-initialization clobbers KE config (the reason `kge_pg_table_prefix` existed) | Verify explicitly in Phase 1 (T1.6) against KE `config_init_style: kwargs`; keep an isolated `ke_setting` dict if confirmed |
| R5 | Idempotency key collisions / replay storms | Deterministic key derivation (T2.4) + KE idempotency window (`knowledge.sync.outbox`, 24h default); key includes `updated_at` hash so retries of stale writes are rejected, not deduped |
| R6 | Data backfill gaps (KGE graph → KE knowledge) | Reconciliation counts + spot-checks (T4.2); keep KGE read path available until sign-off |
| R7 | Batch ingestion overload on KE (extraction is LLM-driven) | Bounded concurrency ≤ KE `max_concurrent_imports`; per-item accounting; consider outbox/scheduled mode later |
| R8 | `ItemCatalogRef.node_id` semantics change confuses integrators | Migration note in SOP + this doc; backfill re-points rows; optional auto-sync on ingestion (T2.7) |

---

## 9. Decisions Required

| # | Decision | Options / Recommendation |
|---|---|---|
| D1 | Ingested `content` format | (a) JSON dump of entity fields, (b) Markdown projection for better LLM extraction. **Recommend (b) markdown** — KE's extraction/embedding pipeline is text-oriented |
| D2 | RFQ `File` ingestion transport | (a) base64 inline via `importKnowledge`, (b) presigned S3 URL via `importKnowledgeFromUrl`. **Recommend (b)** for size safety; fall back to (a) for small files |
| D3 | Which modes back `inquire_catalog` at GA | Minimum: `semantic` + `cypher` + node inquiry. `ask`/`graph` behind the same field — **recommend shipping all four**, they are one handler route each |
| D4 | Domain topology | Single `rfq-catalog` domain per tenant vs. per-endpoint domains. **Recommend single domain + KE domain members** to start |
| D5 | Sync vs async ingestion default | Synchronous mutation returning KE lifecycle status (`PROCESSING`) with `refreshKnowledge` for repair. Async/scheduled ingestion via KE outbox later if volume demands |

---

## 10. Acceptance Criteria (Definition of Done)

1. `query inquire_catalog` executes against `knowledge_engine` in staging for all shipped
   modes, including `nodeId` inquiry, with the existing `CatalogInquiryResultType` contract
   unchanged at the top level.
2. New ingestion mutations are certified live: single, batch (≥50 items with partial-failure
   drill), and file import, with idempotent replay producing no duplicates.
3. `ItemCatalogRef` rows are re-pointed to KE knowledge IDs; write→read loop
   (`ingest → inquire_catalog(nodeId)`) verified end-to-end.
4. INT-019/020/021 executed and documented; certification report published with live sign-off.
5. Full RFQ regression suite green; KE baseline suite green in the shared staging environment.
6. Grep of `rfq_engine` shows no functional references to `knowledge_graph_engine`
   (this plan and the certification report may retain historical mentions).
7. Rollback rehearsed (pre-decommission: single setting flip; post-decommission: tag redeploy).

---

## 11. Timeline (indicative, single engineer)

| Phase | Duration | Notes |
|---|---|---|
| 0 — Readiness | 0.5–1 wk | Gateway mount, provisioning, settings, KE baseline |
| 1 — Inquiry swap | 1–1.5 wk | Handler rewrite + tests |
| 2 — Ingestion bridge | 1.5–2 wk | New handler, mutations, projection, idempotency, batch |
| 3 — Tests & certification | 1 wk | SOP + certification + drills |
| 4 — Cutover & decommission | 1–2 wk (incl. soak) | Dual-run soak, backfill, cleanup |

---

## 12. Change Log

| Date | Author | Change |
|---|---|---|
| 2026-10-19 | goose (via bibow) | Initial plan drafted from source audit of `rfq_engine` (KGE integration inventory) and `banyanos/knowledge_engine` v3.0.0 (API surface, deployment, prerequisites) |
| 2026-10-19 | goose (via bibow) | Delivered Phase-4 tooling + green baseline: KE suite fully green after installing `capability_engine` (592/592 unit + 42/42 e2e); T4.1 shadow-comparison script (contract + coverage verdict per case); T4.2 backfill/reconciliation script (batched bridge replay + ref re-point + KE domain counts, dry-run mode); 6 more GraphQL documents schema-validated. |
| 2026-10-19 | goose (via bibow) | Delivered operational tooling + offline certification: KE provisioning script (T0.2), gateway manifest verified (T0.1), KE baseline executed (T0.4: 590/592 unit + 42/42 e2e, 2 env failures), `prepare_catalog_refs.py` re-pointed to the KE bridge (T3.2), certification report skeleton (T3.4) with 19 offline function results. |
| 2026-10-19 | goose (via bibow) | Implemented Phases 1–3 in `rfq_engine`: KE inquiry handler (all modes + node lookup + error mapping + dual-run flag), ingestion bridge (upsert-by-code, deterministic idempotency, batch accounting, file import, catalog-ref sync), 59 unit tests (27 handler + 32 ingest, all green; full-suite regressions identical to baseline), KE document validation against the live KE schema, SOP INT-019 rewrite + INT-020/021, deploy-manifest actions + label-drift fix. See §13 for resolved decisions and deviations. |

---

## 13. Implementation Log (2026-10-19, Phases 1–3)

### 13.1 Delivered

| Area | Files | Notes |
|---|---|---|
| Inquiry swap (T1.1–T1.6) | `handlers/catalog/handler.py` (rewritten) | KE query documents for `searchKnowledges`, `knowledge`, `askKnowledgeBase`, `knowledgeGraph`, `knowledgeGraphByCypher`; mode router (default `semantic`); legacy KGE mode aliases (`text2cypher`/`vector`/`hybrid`) logged + remapped; node-by-id inquiry lifts the `OperationUnsupportedError` restriction; `BIZ_KNOWLEDGE_*` error mapping (`system_timeout`/`not_found`/`access_denied`/`system_error`) with timeout string-sniff fallback; `filters.domain_ids` → `domainIds`; search limit clamped to KE max 100; legacy `{results, total, page, limit}` envelope preserved |
| Dual-run / rollback (T4.1/T4.4) | `handlers/catalog/handler.py` | `catalog_knowledge_backend` setting selects `"knowledge_engine"` (default) or the retained KGE path; R4-mitigated `_ke_setting()` strips RFQ backend keys and merges `knowledge_engine_setting` overrides; identity claims (user/tenant_id/roles/permissions) forwarded to KE context |
| Ingestion bridge (T2.1–T2.7) | `handlers/catalog/ingest.py` (new) | `dispatch_ingest_knowledge` / `dispatch_ingest_catalog` / `dispatch_ingest_file`; upsert-by-code with optimistic-lock retry and lost-race convergence; deterministic idempotency keys `rfq:{partition_key}:{entity_type}:{uuid}:{updated_at/content hash}`; markdown projection (D1); bounded-concurrency batch with per-item accounting; file transport via presigned URL (D2) or inline base64 with validation; `ItemCatalogRef` auto-sync (`node_id` = KE knowledge id, best-effort); settings fail-fast `configuration_error` (R2) |
| Mutation surface (T2.2) | `mutations/knowledge_ingest.py`, `types/knowledge_ingest.py` (new), `schema.py`, `main.py` | `ingestKnowledgeFromRfq`, `ingestCatalogToKnowledge`, `ingestRfqFileToKnowledge` registered in schema + deploy manifest; in-band `KnowledgeIngestResultType`/`KnowledgeIngestBatchType`; pre-existing manifest label drift fixed (`itemPriceTieList`→`itemPriceTierList`, `discountRule`→`discountPrompt`) |
| Tests (T1.7, T3.1) | `tests/test_catalog_handler.py` (rewritten, 27), `tests/test_knowledge_ingest.py` (new, 32), `tests/test_inquire_catalog.py` (rewritten, KE integration) | All green; full-suite run identical to pre-change baseline (526 passed; the 2 cache-management failures and 12 SafeFloat errors reproduce on unmodified `HEAD`) |
| Document validation (T1.1) | — | All 10 RFQ-side GraphQL documents validate against the real `knowledge_engine` schema (graphene `validate`) |
| SOP (T3.3) | `docs/INTEGRATION_SCENARIOS_SOP.md` | INT-019 rewritten for KE (all modes + node inquiry + failure injection); INT-020 (ingestion bridge) and INT-021 (resilience drills) added; readiness/cadence/evidence tables updated |
| Provisioning tooling (T0.2) | `rfq_engine/tests/prepare_test_data/prepare_ke_provisioning.py` (new) | Idempotent tenant provisioning: ensures KE domain `rfq-catalog` + 6 knowledge types via `createKnowledgeDomain`/`createKnowledgeType` (deterministic idempotency keys, code-matched reuse); emits the `knowledge_engine_ingest` settings block + `ke_*` env lines; all 4 GraphQL documents validate against the KE schema. Execution against staging is the remaining ops step. |
| Gateway mount verification (T0.1) | — | `silvaengine_gateway/module_routes/knowledge_engine.yaml` already present with the exact expected dispatch (`knowledge_engine.main:dispatch_graphql`, `config_init_style: kwargs`, `POST /{endpoint_id}/knowledge_engine_graphql`) — verified, no change needed |
| Seed-script re-point (T3.2) | `rfq_engine/tests/prepare_test_data/prepare_catalog_refs.py` (rewritten) | KGE `executeExtract` path removed; ingestion now goes through the RFQ bridge mutation `ingestKnowledgeFromRfq` (markdown projection + idempotency + upsert owned by the bridge); `node_id` = KE `knowledgeId`; link-only mode searches KE via `inquireCatalog` (semantic) with exact-`code` preference; external-id fallback removed (KE node ids are knowledge UUIDs); all 3 documents validate against the RFQ schema |
| Dual-run shadow tooling (T4.1) | `rfq_engine/tests/prepare_test_data/shadow_compare_catalog_inquiry.py` (new) | Runs the same `inquire_catalog` through both backends (`catalog_knowledge_backend` injected per call), records per-backend error codes + payload key sets + totals, checks the legacy `{results, total}` contract on both, flags coverage shortfalls (`ke_total < kge_total * SHADOW_COVERAGE_RATIO`), and writes `shadow_report.json` with a PASS/REVIEW verdict for the T4.1 soak acceptance |
| Backfill + reconciliation tooling (T4.2) | `rfq_engine/tests/prepare_test_data/backfill_catalog_to_knowledge.py` (new) | Lists all items (`itemList` pages) → replays in batches through `ingestCatalogToKnowledge` (bridge owns projection/idempotency/upsert/auto-sync) → lists all `ItemCatalogRef` rows and re-points stale `node_id`s to KE knowledge ids (dry-run mode) → reads KE `knowledgeDomain` entity/relation/vector counts → writes `backfill_reconciliation.json` (entity counts reconcile + refs re-pointed). All 6 documents schema-validated |
| KE baseline green (T0.4 closure) | — | Installed the missing sibling `capability_engine` package into the shared venv; KE suite now fully green: `tests/unit` **592/592**, `tests/e2e` **42/42** (2026-10-19) |
| Certification report (T3.4 skeleton) | `docs/integration_certification_report_knowledge_engine.md` (new) | Mirrors the existing certification reports: offline stages certified (19 function results, resilience matrix, defect log), live staging stages marked pending; blocks final certification on INT-019/020/021 + backfill reconciliation |

### 13.2 Resolved decisions

| # | Decision (options in §9) | Resolution |
|---|---|---|
| D1 | Ingested content format | **(b) Markdown** — `# {Entity}: {label}` + labeled field bullets + prose description blocks |
| D2 | File transport | **(b) presigned URL** (`importKnowledgeFromUrl`) with inline base64 fallback (`importKnowledge`, validated) and an optional `knowledge_engine_ingest.file_bucket` presign convention |
| D3 | Modes at GA | **All four** — `semantic`, `ask`, `graph`, `cypher` + node-by-id; legacy KGE mode names accepted as aliases |
| D4 | Domain topology | Single `rfq-catalog` domain per tenant (per `knowledge_engine_ingest.domain_id` setting) |
| D5 | Sync vs async | Synchronous mutations returning in-band status; repair path = re-ingest (upsert) or KE `refreshKnowledge` |

### 13.3 Deviations / corrections discovered during implementation

1. **KE tenant model (§3.1 correction):** KE v3.0.0 isolates rows by the
   `tenant_id` **claim** (plus fail-closed PDP/owner access checks), not by
   `info.context["partition_key"]` as originally recorded. The RFQ handler
   forwards the caller's identity claims (`user`, `tenant_id`, `user_id`,
   `roles`, `permissions`, `is_admin`) into the KE GraphQL context so
   access control and tenant scoping carry over; `endpoint_id`/`part_id`
   continue to flow as top-level Invoker params as with KGE.
2. **Upsert, not blind create (T2.3/T2.4 refinement):** KE
   `KnowledgeRepository.insert` raises `BIZ_KNOWLEDGE_ALREADY_EXISTS` on a
   duplicate `code` (the `autoOverDuplicates` flag is metadata-only in
   v3.0.0). The bridge therefore performs lookup-by-code →
   create-or-update, retries once on `BIZ_KNOWLEDGE_VERSION_CONFLICT`, and
   treats unchanged content as a replay no-op.
3. **Backend flag default:** `catalog_knowledge_backend` defaults to
   `knowledge_engine` from Phase 1 (T4.1 suggested defaulting to `kge`
   until certification). The flag still flips back to the retained KGE
   path for rollback rehearsals (T4.4); flip the default at hard cutover
   sign-off if a slower soak is preferred.
4. **R4 resolution:** KE's `Config.initialize` is `_initialized`-guarded,
   so gateway-initialized KE is never clobbered by the Invoker's
   per-call instantiation. As belt-and-braces, RFQ passes a sanitized
   setting copy (`db_backend`/`initialize_tables`/`pg_table_prefix`
   stripped) plus `knowledge_engine_setting` overrides.
   `kge_pg_table_prefix` is kept for the legacy path only and is removed
   at T4.3.

### 13.4 Remaining (operational)

- **T0.2 (execution)** — run `prepare_ke_provisioning.py` per staging
  tenant and paste the emitted `knowledge_engine_ingest` block into the
  RFQ deployment settings (tooling delivered; script + documents
  schema-validated).
- **T0.4 (baseline recorded, fully green)** — KE's own suite executed
  on 2026-10-19: `tests/unit` **592/592**, `tests/e2e` **42/42** after
  installing the missing sibling `capability_engine` package into the
  shared venv (the 2 prior failures were environmental and are resolved).
  No PostgreSQL/Neo4j/LLM failures.
- **T3.4 (live execution)** — run INT-019/020/021 against staging and
  fill the live-staging section of
  `docs/integration_certification_report_knowledge_engine.md`
  (offline stages already certified there).
- **T4.1/T4.2 (tooling delivered)** — run
  `shadow_compare_catalog_inquiry.py` over the soak window for the
  dual-run evidence, and `backfill_catalog_to_knowledge.py` for the
  catalog replay + `ItemCatalogRef.node_id` re-point reconciliation.
- **T4.3/T4.4 (pending certification)** — after INT-019/020/021 pass and
  the backfill reconciles: remove the legacy KGE path +
  `kge_pg_table_prefix` + `functs_on_local.knowledge_graph_graphql`
  (grep-clean per DoD #6), flip the flag, rehearse rollback.
