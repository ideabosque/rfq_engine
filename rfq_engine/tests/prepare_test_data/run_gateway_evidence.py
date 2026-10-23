"""Run SOP scenarios with per-call evidence for nested seed and KE battery calls."""
import time

import run_sop_scenarios as sop


def main():
    original = sop.e2e.graphql

    def recorded(route, query, variables, token, timeout=180.0):
        started = time.monotonic()
        output = None
        try:
            output = original(route, query, variables, token, timeout=timeout)
            return output
        except Exception as exc:
            output = {"errors": [{"message": str(exc)}]}
            raise
        finally:
            sop.log_call("GatewayEvidence", "POST " + sop.e2e._graphql_route_urls[route],
                         "Gateway GraphQL operation (including nested seed/battery calls)",
                         "fail" if (output or {}).get("errors") else "pass",
                         round((time.monotonic() - started) * 1000), "gateway-call",
                         {"query": query, "variables": variables}, output)

    sop.e2e.graphql = recorded
    return sop.main()


if __name__ == "__main__":
    raise SystemExit(main())
