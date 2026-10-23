#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Register + bootstrap the gateway admin used by the RFQ gateway-E2E run.

One-time per fresh docker-banyanos-gateway deployment:

    1. registers the admin through user_engine (``registerUser``);
    2. calls ``docker-banyanos-gateway/scripts/bootstrap_platform_admin.py``
       to activate the user, assign the preset ``platform:super_admin`` role,
       and register permission resources.

Reads credentials from the gateway ``.env`` (``ADMIN_PASSWORD`` is the
PostgreSQL/bootstrap credential, not a user password); the admin password
for the user account defaults to ``E2E_ADMIN_PASSWORD`` (>= 12 chars).

Usage::

    python register_gateway_admin.py
"""
from __future__ import annotations

__author__ = "bibow"

import json
import os
import subprocess
import sys

import httpx
from dotenv import dotenv_values

GATEWAY_ENV_PATH = os.getenv(
    "E2E_GATEWAY_ENV",
    "C:/Users/bibo7/gitrepo/banyanos/docker-banyanos-gateway/.env",
)
GATEWAY_ENV = dotenv_values(GATEWAY_ENV_PATH)

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:18000")
ENDPOINT_ID = os.getenv("E2E_ENDPOINT_ID", "banyan")
PART_ID = os.getenv("E2E_PART_ID", str(GATEWAY_ENV.get("TENANT_PART_ID") or "nestaging"))
ADMIN_EMAIL = os.getenv("E2E_ADMIN_EMAIL", "admin@ideabosque-e2e.local")
ADMIN_PASSWORD = os.getenv("E2E_ADMIN_PASSWORD", "Gateway-E2E-2026!")


def register() -> bool:
    """Register the admin through user_engine; True when the user exists."""
    response = httpx.post(
        f"{BASE_URL}/{ENDPOINT_ID}/user_engine_graphql",
        json={
            "query": (
                "mutation Register($input: UserRegisterInput!, $k: ID!) {"
                "    registerUser(input: $input, idempotencyKey: $k) { __typename }"
                "}"
            ),
            "variables": {
                "input": {
                    "email": ADMIN_EMAIL,
                    "username": ADMIN_EMAIL.split("@")[0],
                    "password": ADMIN_PASSWORD,
                    "displayName": "E2E Admin",
                },
                "k": "e2e-register:" + ADMIN_EMAIL,
            },
        },
        headers={"Part-Id": PART_ID},
        timeout=60,
    )
    body = response.json() if response.content else {}
    errors = body.get("errors") or []
    if not errors:
        return True
    message = json.dumps(errors, ensure_ascii=False).lower()
    if any(word in message for word in ("already", "unique", "exists", "注册")):
        return True
    print("register errors:", json.dumps(errors)[:400], file=sys.stderr)
    return False


def bootstrap() -> int:
    """Activate + assign the platform admin role via the gateway helper."""
    gw_root = os.path.dirname(GATEWAY_ENV_PATH)
    env = dict(os.environ)
    env["BANYAN_ADMIN_PASSWORD"] = ADMIN_PASSWORD
    env["SE_CONFIGDATA_DATABASE_URL"] = (
        f"postgresql+psycopg://{GATEWAY_ENV['POSTGRES_USER']}:{GATEWAY_ENV['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{GATEWAY_ENV['POSTGRES_HOST_PORT']}/{GATEWAY_ENV['POSTGRES_DB']}"
    )
    result = subprocess.run(
        [
            sys.executable,
            os.path.join(gw_root, "scripts", "bootstrap_platform_admin.py"),
            "--email",
            ADMIN_EMAIL,
            "--gateway-url",
            f"{BASE_URL}/beta/core/{ENDPOINT_ID}",
            "--part-id",
            PART_ID,
        ],
        env=env,
    )
    return result.returncode


def main() -> int:
    if not register():
        return 1
    return bootstrap()


if __name__ == "__main__":
    print(f"gateway: {BASE_URL} part: {PART_ID} admin: {ADMIN_EMAIL}")
    raise SystemExit(main())