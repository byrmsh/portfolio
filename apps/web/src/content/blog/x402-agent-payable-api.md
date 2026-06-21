---
title: 'An agent-payable API with x402: two chains, REST, and MCP'
graphLabel: 'x402 agent-payable API'
description: 'A FastAPI service that sells data to AI agents over x402, paid in testnet USDC on Base and Solana and served as both REST and MCP. The hard parts: settling on Solana with no SOL, and wiring MCP payments against an SDK whose docs do not match the installed code.'
pubDate: '21 Jun 2026'
draft: false
tags:
  - x402
  - MCP
  - FastAPI
  - Solana
  - Base
  - USDC
  - Python
---

I built a small API that sells data to autonomous agents and bills them per request, in stablecoins, with no account and no API key. An agent requests a resource, gets back HTTP 402 with a price and a list of chains it can pay on, signs a payment, and retries; a facilitator settles it on-chain and fronts the gas, so the agent only ever spends USDC. Taking the payment is the easy half. The harder half is what the protocol's edges cost: settling on Solana without the payer holding any native token, getting a paid MCP tool to run against an SDK whose docs describe code that is not in the package, and two things that worked on localhost and broke the moment the service sat behind a real hostname.

This is a testnet-only proof of concept. Every payment here is Base Sepolia or Solana devnet USDC, zero real money, so read it as a design note rather than a production claim. The data it sells is the SEC EDGAR ticker-to-CIK reference set, which is public and key-free; the dataset is a stand-in, the payment rails are the point.

### The 402 handshake

[x402](https://x402.org) is Coinbase's revival of HTTP 402 Payment Required for machine-to-machine payments. The exchange is the protocol:

1. The client GETs a paid resource with no payment header.
2. The server answers 402 with what it accepts: scheme, price, asset, and CAIP-2 network, one entry per chain.
3. The client picks a chain, signs a stablecoin transfer authorization, and retries with the signed payload in a header.
4. A facilitator verifies the payload and settles it on-chain, and the server returns the data.

The server never holds a private key and never touches a chain. The facilitator does the verify-and-settle and pays the gas, and the public `x402.org/facilitator` is keyless on both testnets, which is what makes a server-side-keyless POC possible at all.

### One service, two surfaces

The same data is sold two ways from one process: a REST endpoint and an MCP tool. The REST side is a FastAPI app with the x402 ASGI middleware gating two routes. A 402 from a route that has a wallet on both chains lists both options, so one endpoint is dual-chain and the client decides where to pay.

The MCP side puts the same rails behind Model Context Protocol tools, so an agent runtime discovers, pays for, and calls them natively. Rather than run a second process, the MCP server mounts onto the same FastAPI app. The one wrinkle is that the streamable-HTTP MCP app owns a session manager that has to run inside the host app's lifespan:

```python
def create_app() -> FastAPI:
    server = build_server()
    server.initialize()           # one facilitator round-trip, shared by both surfaces
    mcp = build_mcp(server)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db(settings.database_url)
        async with mcp.session_manager.run():     # MCP's session loop, inside the host lifespan
            yield
        await close_db()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(PaymentMiddlewareASGI, routes=build_routes(), server=server)
    app.include_router(router)
    app.mount("/", mcp.streamable_http_app())     # MCP at /mcp; the API's own routes match first
    return app
```

One resource server backs both. The REST middleware and the MCP tools call the same verify and settle methods, and one receipts hook fires for either.

### Gasless on Solana, and the account that must exist first

On Base the payer signs an EIP-3009 `transferWithAuthorization`, gasless by design: the facilitator submits the transaction and pays the ETH. Solana's exact scheme is gasless too, by a different route. The facilitator advertises itself as the transaction fee payer and co-signs, so the paying agent needs no SOL at all; it signs for the token transfer, the facilitator covers the network fee.

The catch is one account that has to exist before any USDC can land: the receiver's associated token account. An SPL transfer fails if the destination has no account for that mint, and the facilitator pays fees but does not create accounts. Creating one normally costs a little SOL for rent, which loops straight back to the native token the gasless design just removed. The devnet SOL airdrop would not cooperate either: the public RPC was rate-limited to failure, and the web faucet rejected the account behind it for too few public repositories.

The way out skips SOL entirely. Dripping Circle's devnet USDC to the receiver address creates its token account as a side effect of the transfer, for free. After that the settlement has somewhere to land, and the payer never needed a single lamport.

```
settled on solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1
tx: 3beBZXavcD5Z6zqSiZfxiv3Y5zhaa38i8pLZLj5k1rP8eZ4rX2UNwe4soTD8e5WJisJU2mWzVyrE68opjwCufg5M
```

### MCP payments, where the docs and installed code disagree

Most of the time went into getting a paid MCP tool working against `x402` 2.13.1 and the bundled `mcp` 1.28.0, because the package's docs and examples describe an API the installed code does not have. The entry point they point at raises an ImportError on a clean install. The one that works is a similarly named function in a different module, applied as a decorator stacked under `@mcp.tool`:

```python
@mcp.tool(name="get_company", description="...")   # outer
@paid                                              # inner: x402.mcp.create_payment_wrapper(...)
async def get_company(ticker: str) -> str:
    return json.dumps(await lookup(ticker))
```

The recurring trap was name collisions. A schema class and a client factory each exist under the same name in two different modules, and the wrong import fails a different way each time: an `AttributeError` mid-request in one case, and in another a silently dropped settlement, where the payment clears on-chain but the client is told nothing happened. Untangling it meant reading the package in the virtualenv instead of the docs. When the two disagree, the installed code wins.

A paid tool call then settles the same way a REST call does, on-chain:

```
tools: get_company, search_companies
payment_made: True
settled on eip155:84532
tx: 0xc62f5961cbc7f3ddba1569db5e55f807fb4a67809d6fba19f1c40cba53678b1b
```

### Deploying it

Two things worked on localhost and broke the moment the service ran behind a real hostname.

The 402 challenge started advertising its resource URL as `http`. Behind a proxy that terminates TLS, the app sees the internal hop, not the public origin, so the scheme it reports is wrong. Running uvicorn with `--proxy-headers` tells it to trust the forwarded protocol, and the challenge reads `https` again.

The MCP endpoint was louder: every request came back `421 Misdirected Request` while the REST routes stayed fine. MCP's server defaults its host to `127.0.0.1`, and that default quietly turns on DNS-rebinding protection with an allow-list of localhost only. On localhost every call passes; behind a real domain the Host header is not on the list, so the server rejects each request before the tool runs. The guard exists to stop a web page from rebinding DNS to a localhost server, which is not how a public API is reached, so the fix is to set the transport security explicitly and turn it off:

```python
mcp = FastMCP(
    "x402-agent-api",
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
```

Both are one-line changes, and neither shows up until the service runs somewhere that is not localhost.

### Receipts after the fact

Settlement lands after the route handler returns, so the receipt cannot be written in the handler. x402 fires an `on_after_settle` hook once the payment clears, and it records the transaction, chain, payer, amount, and resource; a free `/v1/receipts` endpoint serves that as an on-chain audit trail. The same hook covers both surfaces, since REST and MCP share the one resource server. The resource path is only present for REST calls, so it is read defensively and left null for tool calls.

### What it is and is not

It is a working demonstration that an API can charge agents per request across two chains and two protocols, with on-chain settlement and no keys held server-side. It is not a production service: testnet only, a public dataset standing in for whatever a real one would sell, and the public facilitator rather than a self-hosted one. Swapping the dataset is two functions, and pointing at a private facilitator is one setting. The code is on [GitHub](https://github.com/byrmsh/x402-agent-api).
