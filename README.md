# ContextForge MCP Gateway

A production-grade MCP (Model Context Protocol) gateway demonstrating enterprise-grade OAuth security with RFC 8693 token exchange, PM-level data isolation, and intelligent tool orchestration.

Reference architecture: Keycloak 26.2 identity layer, path-based MCP routing, and per-PM desk isolation enforced at every layer.

## Architecture

```
                    ┌─────────────────────────────────┐
                    │         Keycloak 26.2            │
                    │     Realm: trading               │
                    │     RFC 8693 Token Exchange       │
                    └───────────────┬─────────────────┘
                                    │
┌───────────┐       ┌───────────────▼─────────────────┐
│ AI Agent  │──────►│        MCP Gateway :9000         │
│ (Bearer   │       │  JWT Validation → Scope Check    │
│  JWT-A)   │       │  → Token Exchange → Path Route   │
└───────────┘       └──┬──────────┬──────────┬────────┘
                       │          │          │
                ┌──────▼───┐ ┌───▼────┐ ┌───▼──────┐
                │Bloomberg │ │ Risk   │ │ Research │
                │MCP :8010 │ │MCP:8011│ │MCP :8012 │
                └──────────┘ └────────┘ └──────────┘
```

## Three Phases

| Phase | Component | Port | Description |
|-------|-----------|------|-------------|
| **1** | MCP Gateway | 9000 | RFC 8693 token exchange, path routing, tool aggregation |
| **1** | Bloomberg MCP | 8010 | Reference data, history, security search |
| **1** | Risk MCP | 8011 | VaR, Greeks, stress scenarios |
| **1** | Research MCP | 8012 | Document search, retrieval, summarization |
| **2** | Cognitive MCP | 8013 | PM interaction tracking, ECEF cognitive modeling |
| **3** | Thesis Validator | 8014 | Multi-agent investment thesis validation |

## Quick Start

```bash
# Phase 1 only (gateway + 3 MCP servers)
make up-phase1

# Full stack (all 3 phases)
make up-all

# Run demo
make demo                    # Happy path: Alice queries all 3 servers
make demo-isolation          # PM isolation: Alice blocked from rates desk

# Health check
make health
```

## Demo Users

| User | Desk | desk_access |
|------|------|-------------|
| alice-pm | Equities | `["equities"]` |
| bob-pm | Rates | `["rates"]` |
| charlie-pm | Multi-desk | `["equities", "vol"]` |

## Key Security Features

- **RFC 8693 Token Exchange**: Gateway exchanges broad JWT-A for narrowed JWT-B per backend
- **PM Isolation**: desk_access claim enforced at gateway (scope), tool (claim check), and data layer
- **Delegation Chain**: `act` claim proves exchange path (alice → mcp-gateway → bloomberg-mcp)
- **Zero Trust**: Every hop validates JWT — no implicit trust from network location

## Tests

```bash
make test-e2e    # Full end-to-end test suite (requires running stack)
```
