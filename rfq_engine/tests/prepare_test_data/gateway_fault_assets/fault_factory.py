"""Isolated E2E fault gateway. No live configuration or credentials are written.

The timeout modes deliberately inject exceptions at the KE invocation boundary;
they validate gateway/handler error mapping, not a real remote network timeout.
"""
import os


class TimeoutEngine:
    def __init__(self, logger, **setting):
        self.logger = logger

    def knowledge_engine_graphql(self, **params):
        if os.environ.get("RFQ_E2E_FAULT_MODE") == "timeout_code":
            raise RuntimeError("BIZ_KNOWLEDGE_TIMEOUT: controlled E2E fault")
        raise TimeoutError("controlled E2E knowledge invocation timed out")


def create_app_from_env():
    from scripts.gateway_app import build_setting
    from silvaengine_gateway.app import create_app

    setting = build_setting()
    mode = os.environ.get("RFQ_E2E_FAULT_MODE", "baseline")
    if mode.startswith("timeout_"):
        import scripts
        scripts.TimeoutEngine = TimeoutEngine
        setting["functs_on_local"]["knowledge_engine_graphql"] = {
            "module_name": "scripts",
            "class_name": "TimeoutEngine",
        }
    elif mode == "llm_down":
        setting["llm"] = dict(setting.get("llm") or {})
        setting["llm"].update({"api_base_url": "http://127.0.0.1:9/v1",
                               "api_key": "local-fault-placeholder", "timeout": 1000})
    return create_app(setting)
