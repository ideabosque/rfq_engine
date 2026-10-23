"""Isolated fault-gateway tests supplementing INT-021; preserves the main gateway."""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(os.environ.get("AIT_OUTPUT_DIR", REPO / "docs/test_results/fixes_20261020"))
ROOT.mkdir(parents=True, exist_ok=True)
ASSETS = Path(__file__).resolve().parent / "gateway_fault_assets"
sys.path.insert(0, str(REPO / "rfq_engine/tests/prepare_test_data"))
import run_gateway_e2e as gateway

GW = Path(gateway.GATEWAY_ENV_PATH).resolve().parent
COMPOSE = ["docker", "compose", "-p", "docker-banyanos-gateway", "--env-file", str(GW / ".env")]
for path in [GW / "docker-compose.yml", GW / "docker-compose.override.yml", ASSETS / "compose.fault.yml"]:
    COMPOSE.extend(["-f", str(path)])
calls, results = [], []
token = None


def save():
    (ROOT / "additional_drills.json").write_text(json.dumps({"results": results, "calls": calls}, indent=2, ensure_ascii=False), encoding="utf-8")


def command(args, mode="baseline"):
    start = time.monotonic()
    proc = subprocess.run(args, env={**os.environ, "RFQ_E2E_FAULT_MODE": mode,
                                   "RFQ_E2E_REPO_ROOT": REPO.as_posix(),
                                   "RFQ_E2E_GATEWAY_ROOT": GW.as_posix()},
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    calls.append({"method": "subprocess", "arguments": {"command": args, "fault_mode": mode}, "elapsed_ms": round((time.monotonic()-start)*1000), "status": "pass" if proc.returncode == 0 else "fail", "output": {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}})
    save()
    if proc.returncode:
        raise RuntimeError(proc.stderr[-600:])
    return proc.stdout


def launch(mode):
    cmd = list(COMPOSE)
    if mode == "ke_unmounted":
        cmd.extend(["-f", str(ASSETS / "compose.ke-unmounted.yml")])
    command(cmd + ["up", "-d", "--no-build", "--no-deps", "--force-recreate", "rfq_fault"], mode)
    for attempt in range(40):
        try:
            if httpx.get("http://127.0.0.1:18001/health", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("fault gateway failed readiness")


def gql(query, variables, label, port=18001, auth=True):
    start = time.monotonic()
    headers = {"Part-Id": gateway.PART_ID}
    if auth:
        headers["Authorization"] = "Bearer " + token
    url = f"http://127.0.0.1:{port}/banyan/rfq_graphql"
    response = httpx.post(url, json={"query": query, "variables": variables}, headers=headers, timeout=45)
    body = response.json()
    if isinstance(body, dict) and isinstance(body.get("body"), str):
        body = json.loads(body["body"])
    calls.append({"method": "POST " + url, "description": label, "arguments": {"query": query, "variables": variables, "authenticated": auth}, "elapsed_ms": round((time.monotonic()-start)*1000), "status": "pass" if response.status_code == 200 and not body.get("errors") else "fail", "output": {"http_status": response.status_code, "body": body}})
    save()
    return response.status_code, body


def result(name, passed, detail):
    results.append({"name": name, "status": "pass" if passed else "fail", "detail": detail})
    save()
    print(f"[{results[-1]['status'].upper()}] {name}: {detail}", flush=True)


def inquiry(mode, extra=None):
    return gql(gateway._INQUIRE_MUTATION_PAYLOAD, {"query": {"queryText": "flight", "searchMode": mode, **(extra or {})}}, mode + " inquiry")


def core_write(mode):
    marker = "fault-core-" + uuid.uuid4().hex
    status, body = gql('mutation($name:String){insertUpdateItem(itemType:"flight",itemName:$name,uom:"seat",updatedBy:"e2e_fault"){item{itemUuid itemName}}}', {"name": marker}, mode + " core create")
    item = (body.get("data") or {}).get("insertUpdateItem", {}).get("item") or {}
    ident = item.get("itemUuid")
    if not ident:
        result(mode + " core CRUD", False, body)
        return
    try:
        _, body = gql('query($id:String!){item(itemUuid:$id){itemUuid itemName}}', {"id": ident}, mode + " core read")
        result(mode + " core CRUD", (body.get("data") or {}).get("item", {}).get("itemName") == marker, {"created_and_read": ident})
    finally:
        _, deleted = gql('mutation($id:String!){deleteItem(itemUuid:$id){ok}}', {"id": ident}, mode + " core delete")
        if not (deleted.get("data") or {}).get("deleteItem", {}).get("ok"):
            result(mode + " cleanup", False, deleted)


def main():
    global token
    token = gateway.login()
    source = json.loads((REPO / "rfq_engine/tests/prepare_test_data/travel/products.json").read_text(encoding="utf-8"))
    item_id = source["items"][0]["itemUuid"]
    try:
        launch("baseline")
        status, body = inquiry("graph", {"depth": 1, "limit": 2})
        node = (body.get("data") or {}).get("inquireCatalog") or {}
        result("isolated gateway baseline", status == 200 and not body.get("errors") and not node.get("errorCode") and isinstance(node.get("payload"), dict), node)
        status, body = gql("query { ping }", {}, "missing bearer", port=18000, auth=False)
        result("unauthenticated request rejected", status in (401, 403), {"http_status": status, "body": body})
        # Legacy KGE rollback is explicitly outside the user-approved scope.
        for mode in ("ke_unmounted", "timeout_sniff", "timeout_code", "llm_down"):
            launch(mode)
            if mode == "ke_unmounted":
                absent = command(["docker", "exec", "banyanos-rfq-fault", "python", "-c", "import importlib.util; print(importlib.util.find_spec('knowledge_engine') is None)"])
                status, body = inquiry("semantic")
                node = (body.get("data") or {}).get("inquireCatalog") or {}
                result("KE module actually unmounted / inquiry", absent.strip() == "True" and status == 200 and not body.get("errors") and node.get("errorCode") in ("configuration_error", "system_error"), node)
            elif mode.startswith("timeout_"):
                status, body = inquiry("semantic")
                node = (body.get("data") or {}).get("inquireCatalog") or {}
                result(mode + " inquiry mapping", status == 200 and not body.get("errors") and node.get("errorCode") == "system_timeout", node)
            elif mode == "llm_down":
                status, body = inquiry("ask", {"queryText": "flight E2E outage " + uuid.uuid4().hex})
                node = (body.get("data") or {}).get("inquireCatalog") or {}
                result("LLM outage query reports failure in-band", status == 200 and not body.get("errors") and node.get("errorCode") == "system_error" and node.get("payload") is None, node)
                proc = subprocess.run(["docker", "logs", "--tail", "500", "banyanos-rfq-fault"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
                filtered = [line for line in (proc.stdout + proc.stderr).splitlines() if "Connection refused" in line or "127.0.0.1:9/" in line]
                calls.append({"method": "docker logs (filtered diagnostics)", "arguments": {"container": "banyanos-rfq-fault", "tail": 500, "filter": ["Connection refused", "127.0.0.1:9/"]}, "status": "pass" if filtered else "fail", "elapsed_ms": 0, "output": {"matching_lines": filtered, "other_lines": "omitted"}})
                result("LLM connection refusal observed", bool(filtered), filtered)
            if mode != "kge":
                document = gateway._INGEST_MUTATION.replace("knowledgeId errorCode", "knowledgeId processingStage errorCode")
                status, body = gql(document, {"entityType": "item", "uuid": item_id}, mode + " ingestion")
                node = ((body.get("data") or {}).get("ingestKnowledgeFromRfq") or {}).get("result") or {}
                if mode == "llm_down":
                    wanted = node.get("status") == "ok" and node.get("processingStage") == "metadata_stored" and bool(node.get("knowledgeId"))
                    label = "LLM outage metadata ingestion reports completed stage"
                else:
                    wanted = (node.get("errorCode") == "system_timeout") if mode.startswith("timeout_") else node.get("status") in ("error", "configuration_error")
                    label = mode + " ingestion failure signalled"
                result(label, status == 200 and not body.get("errors") and wanted, node)
            core_write(mode)
        launch("baseline")
        status, body = inquiry("graph", {"depth": 1, "limit": 2})
        node = (body.get("data") or {}).get("inquireCatalog") or {}
        result("restore KE backend after all faults", status == 200 and not body.get("errors") and not node.get("errorCode"), node)
    finally:
        command(COMPOSE + ["rm", "-s", "-f", "rfq_fault"])
        save()
    return 1 if any(r["status"] == "fail" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
