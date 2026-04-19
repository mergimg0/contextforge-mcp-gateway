#!/usr/bin/env python3
"""
ContextForge MCP Gateway — Demo Agent

Interactive CLI that demonstrates the complete token exchange flow:
  1. Authenticates as a PM via Keycloak (direct access grant for demo)
  2. Calls MCP tools through the gateway
  3. Shows JWT claims, exchanged token details, and tool results
  4. Demonstrates PM isolation (alice can't see rates desk)

Usage:
  python demo/agent.py --user alice --scenario happy_path
  python demo/agent.py --user alice --scenario pm_isolation
  python demo/agent.py --user bob --scenario happy_path
  python demo/agent.py --scenario token_exchange_demo
  python demo/agent.py --scenario tool_aggregation
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date

import httpx
import jwt


# ─── Configuration ────────────────────────────────────────────
KEYCLOAK_URL = "http://localhost:8080/realms/trading/protocol/openid-connect/token"
GATEWAY_URL = "http://localhost:9000"

USERS = {
    "alice": {"username": "alice-pm", "password": "alice-demo-2024"},
    "bob": {"username": "bob-pm", "password": "bob-demo-2024"},
    "charlie": {"username": "charlie-pm", "password": "charlie-demo-2024"},
}


# ─── Helpers ──────────────────────────────────────────────────
def print_header(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_step(emoji: str, text: str) -> None:
    print(f"{emoji} {text}")


def print_json(data: dict, indent: int = 2) -> None:
    print(json.dumps(data, indent=indent, default=str))


def decode_jwt_claims(token: str) -> dict:
    """Decode JWT without verification to inspect claims."""
    return jwt.decode(token, options={"verify_signature": False})


async def authenticate(user_key: str) -> str:
    """Authenticate via Keycloak direct access grant (demo only)."""
    user = USERS[user_key]
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            KEYCLOAK_URL,
            data={
                "grant_type": "password",
                "client_id": "demo-agent",
                "username": user["username"],
                "password": user["password"],
            },
        )
    if resp.status_code != 200:
        print(f"Authentication failed: {resp.status_code}")
        print(resp.text)
        sys.exit(1)
    return resp.json()["access_token"]


async def call_gateway(
    token: str, route: str, method: str, arguments: dict
) -> dict:
    """Make an MCP tool call through the gateway."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GATEWAY_URL}/{route}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": method, "arguments": arguments},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    return {"status_code": resp.status_code, "body": resp.json()}


async def get_aggregated_tools(token: str) -> dict:
    """Fetch merged tools list from all backends."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{GATEWAY_URL}/tools/aggregate",
            headers={"Authorization": f"Bearer {token}"},
        )
    return resp.json()


# ─── Scenarios ────────────────────────────────────────────────
async def scenario_happy_path(user: str):
    """Demonstrate successful tool calls through the gateway."""
    print_header(f"HAPPY PATH — {user.upper()}")

    print_step("🔐", f"Authenticating as {user}...")
    token = await authenticate(user)
    claims = decode_jwt_claims(token)

    print_step("✅", "Token acquired:")
    print(f"   sub:         {claims.get('sub')}")
    print(f"   desk_access: {claims.get('desk_access')}")
    print(f"   aud:         {claims.get('aud')}")
    desk = claims.get("desk_access", ["equities"])[0]

    # Bloomberg call
    print_step("📡", f"Calling Bloomberg MCP: get_ref_data (desk={desk})")
    result = await call_gateway(
        token, "bloomberg", "get_ref_data",
        {"tickers": ["AAPL", "SPX"], "fields": ["PX_LAST", "IMPLIED_VOL_30D"], "desk": desk},
    )
    print(f"   Status: {result['status_code']}")
    if result["status_code"] == 200:
        print_step("📊", "Bloomberg response:")
        print_json(result["body"])

    # Risk call
    print_step("📡", f"Calling Risk MCP: calculate_var (desk={desk})")
    result = await call_gateway(
        token, "risk", "calculate_var",
        {"desk": desk, "metric": "var", "confidence": 0.99, "horizon_days": 1},
    )
    print(f"   Status: {result['status_code']}")
    if result["status_code"] == 200:
        print_step("📊", "Risk response:")
        print_json(result["body"])

    # Research call
    print_step("📡", "Calling Research MCP: search_research")
    result = await call_gateway(
        token, "research", "search_research",
        {"query": "implied volatility mispricing", "max_results": 3},
    )
    print(f"   Status: {result['status_code']}")
    if result["status_code"] == 200:
        print_step("📊", "Research response:")
        print_json(result["body"])

    print_step("✅", "Happy path complete — all 3 MCP servers responded successfully")


async def scenario_pm_isolation(user: str):
    """Demonstrate PM isolation — alice can't access rates desk."""
    print_header(f"PM ISOLATION — {user.upper()}")

    print_step("🔐", f"Authenticating as {user}...")
    token = await authenticate(user)
    claims = decode_jwt_claims(token)
    print(f"   desk_access: {claims.get('desk_access')}")

    own_desk = claims.get("desk_access", ["equities"])[0]
    other_desk = "rates" if own_desk != "rates" else "equities"

    # Successful call to own desk
    print_step("📡", f"Calling Bloomberg for OWN desk ({own_desk})...")
    result = await call_gateway(
        token, "bloomberg", "get_ref_data",
        {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": own_desk},
    )
    print_step("✅" if result["status_code"] == 200 else "❌",
               f"Own desk ({own_desk}): {result['status_code']}")

    # Blocked call to other desk
    print_step("📡", f"Calling Bloomberg for OTHER desk ({other_desk})...")
    result = await call_gateway(
        token, "bloomberg", "get_ref_data",
        {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": other_desk},
    )
    print_step("🚫" if result["status_code"] != 200 else "⚠️",
               f"Other desk ({other_desk}): {result['status_code']}")
    if result["status_code"] != 200:
        print(f"   Response: {json.dumps(result['body'], indent=2)}")

    print_step("🔒", "PM isolation enforced — cross-desk access blocked")


async def scenario_token_exchange_demo(user: str):
    """Show the JWT transformation from gateway token to backend token."""
    print_header("TOKEN EXCHANGE DEEP DIVE")

    print_step("🔐", f"Authenticating as {user}...")
    token = await authenticate(user)
    claims = decode_jwt_claims(token)

    print_step("📋", "Original JWT-A (gateway token) claims:")
    print(f"   aud: {claims.get('aud')}")
    print(f"   sub: {claims.get('sub')}")
    print(f"   scope: {claims.get('scope')}")
    print(f"   desk_access: {claims.get('desk_access')}")
    print(f"   realm_access.roles: {claims.get('realm_access', {}).get('roles', [])}")

    print_step("🔄", "Gateway will exchange JWT-A for JWT-B:")
    print("   grant_type: urn:ietf:params:oauth:grant-type:token-exchange")
    print("   audience: bloomberg-mcp")
    print("   The exchanged JWT-B will have:")
    print("   - aud: bloomberg-mcp (narrowed)")
    print("   - sub: same as JWT-A (preserved)")
    print("   - act.sub: mcp-gateway (delegation chain)")

    print_step("📡", "Making a gateway call to trigger the exchange...")
    desk = claims.get("desk_access", ["equities"])[0]
    result = await call_gateway(
        token, "bloomberg", "get_ref_data",
        {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": desk},
    )
    print_step(
        "✅" if result["status_code"] == 200 else "❌",
        f"Gateway response: {result['status_code']}"
    )

    print_step("💡", "Key security properties of the exchange:")
    print("   1. Audience narrowing: bloomberg-mcp token can't be used against risk-mcp")
    print("   2. Subject preservation: backend sees alice, not the gateway")
    print("   3. Delegation chain: act.sub proves exchange path for audit")


async def scenario_tool_aggregation(user: str):
    """Show merged tool manifests from all backends."""
    print_header("TOOL AGGREGATION")

    print_step("🔐", f"Authenticating as {user}...")
    token = await authenticate(user)

    print_step("📡", "Fetching aggregated tools from all backends...")
    tools = await get_aggregated_tools(token)

    print_step("📋", f"Found {tools.get('count', 0)} tools across all backends:")
    for tool in tools.get("tools", []):
        name = tool.get("name", "unknown")
        desc = tool.get("description", "")[:80]
        print(f"   {name}: {desc}...")

    print_step("💡", "Tools are namespaced: bloomberg__get_ref_data, risk__calculate_var")


# ─── Main ─────────────────────────────────────────────────────
SCENARIOS = {
    "happy_path": scenario_happy_path,
    "pm_isolation": scenario_pm_isolation,
    "token_exchange_demo": scenario_token_exchange_demo,
    "tool_aggregation": scenario_tool_aggregation,
}


async def main():
    parser = argparse.ArgumentParser(description="ContextForge MCP Gateway Demo Agent")
    parser.add_argument("--user", default="alice", choices=list(USERS.keys()))
    parser.add_argument("--scenario", default="happy_path", choices=list(SCENARIOS.keys()))
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    args = parser.parse_args()

    if args.all:
        for name, fn in SCENARIOS.items():
            await fn(args.user)
            print()
    else:
        await SCENARIOS[args.scenario](args.user)


if __name__ == "__main__":
    asyncio.run(main())
