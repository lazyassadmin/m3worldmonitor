# CLAUDE.md

AI assistant entry point for World Monitor. Read this file before touching any code. Then follow links to `AGENTS.md` and `ARCHITECTURE.md` for deeper reference.

## What This Project Is

Real-time global intelligence dashboard. TypeScript SPA (Vite, no UI framework) with 86+ panel components, 60+ Vercel Edge API endpoints, a Tauri v2 desktop app with a Node.js sidecar, and a Railway relay/seed service. Aggregates 30+ external data sources: geopolitics, military, financial markets, cyber threats, climate, maritime, aviation.

**Version**: `2.6.7` (AGPL-3.0-only)
**Node**: see `.nvmrc` (20.x)
**Package manager**: npm

---

## Repository Map

```
.
├── src/                    # Browser SPA (TypeScript, class-based)
│   ├── app/                # App orchestration (data-loader, refresh-scheduler, panel-layout)
│   ├── components/         # 86 UI panels + map components (Panel subclasses)
│   ├── config/             # Variant configs, panel/layer definitions, market symbols
│   ├── services/           # Business logic (~120 files, organized by domain)
│   ├── types/              # TypeScript type definitions
│   ├── utils/              # Shared utilities (circuit-breaker, theme, URL state, DOM)
│   ├── workers/            # Web Workers (analysis, ML/ONNX, vector DB)
│   ├── generated/          # Proto-generated stubs — DO NOT EDIT
│   ├── locales/            # i18n JSON files (14 languages)
│   └── App.ts              # Main application entry
├── api/                    # Vercel Edge Functions (self-contained plain JS)
│   ├── _*.js               # Shared helpers: CORS, rate-limit, API key, relay
│   ├── health/             # Health check endpoints
│   ├── bootstrap.js        # Bulk Redis hydration endpoint
│   └── <domain>/           # Domain endpoints (aviation/, climate/, conflict/, ...)
├── server/                 # Server-side code (bundled INTO Edge Functions)
│   ├── _shared/            # Redis client, rate limiting, LLM helpers, caching
│   ├── gateway.ts          # Domain gateway factory (CORS, auth, cache, ETag)
│   ├── router.ts           # Route matching
│   └── worldmonitor/       # RPC handlers per domain (mirrors proto structure)
├── proto/                  # Protobuf definitions (sebuf framework)
│   └── worldmonitor/       # Service definitions with HTTP annotations
├── shared/                 # Cross-platform JSON configs (markets, RSS domains)
├── scripts/                # Seed scripts, build helpers, relay service (ais-relay.cjs)
├── src-tauri/              # Tauri desktop shell (Rust) + Node.js sidecar
├── convex/                 # Convex backend (contact form, waitlist only)
├── tests/                  # Unit/integration tests (node:test runner)
├── e2e/                    # Playwright E2E specs
├── docs/                   # Mintlify documentation site
├── blog-site/              # Static blog (built into public/blog/)
└── data/                   # Static JSON datasets
```

---

## Development Commands

A `Justfile` is the single entry point for all common tasks. Run `just` or `just --list` to see everything. The recipes below are the most frequently used.

```bash
# Setup
just install             # everything: buf CLI, sebuf plugins, npm deps, Playwright
just deps                # npm install only

# Dev server
just dev                 # full variant (default)
just dev-tech            # tech variant
just dev-finance         # finance variant

# Formatting (Biome — enabled, indentStyle: tab, lineWidth: 100)
just format              # rewrite files in place
just format-check        # CI-safe dry-run (no writes)
npm run format           # same as just format
npm run format:check     # same as just format-check

# Type checking
just typecheck-all       # src/ + api/ together
npm run typecheck        # src/ only
npm run typecheck:api    # api/ only (separate tsconfig)

# Linting
just lint                # Biome lint
just lint-fix            # Biome lint + auto-fix
just lint-boundaries     # Architectural boundary enforcement
just lint-md             # Markdown lint
just lint-all            # All lint checks combined

# Full quality gate (format-check + typecheck + lint + boundaries)
just check

# Testing
just test                # Unit/integration tests (node:test runner)
just test-sidecar        # Sidecar + API handler tests
just test-convex         # Convex unit tests (vitest)
just test-e2e            # Playwright E2E (all variants)
just test-visual         # Visual regression (golden screenshots)
just test-all            # Unit + sidecar + convex (fast suite)

# Build
just build               # full variant
just build-tech
just build-finance
just build-all           # all variants

# Proto code generation (requires buf + sebuf plugins)
just generate            # Regenerate src/generated/ and docs/api/
just proto-lint          # Lint proto files
just proto-breaking      # Check for breaking changes vs main
```

---

## Architecture Rules — Non-Negotiable

### Dependency Direction

```
types → config → services → components → app → App.ts
```

- `types/` has **zero** internal imports
- `config/` imports only from `types/`
- `services/` imports from `types/` and `config/`
- `components/` imports from all above
- Enforced by `npm run lint:boundaries` and `tests/edge-functions.test.mjs`

### API Layer Hard Constraints

- `api/*.js` are **Vercel Edge Functions** — they run in a different runtime than `src/` or `server/`
- They **cannot** import from `../src/` or `../server/`
- They **cannot** use `node:http`, `node:https`, `node:zlib`
- Only same-directory `_*.js` helpers and npm packages allowed
- Enforced by `tests/edge-functions.test.mjs` + pre-push esbuild bundle check
- If you break this constraint, Vercel deployment will fail

### Server Layer

- `server/` is bundled INTO Edge Functions at deploy time via the gateway factory
- `server/_shared/` contains Redis client, rate limiting, LLM helpers
- `server/worldmonitor/<domain>/v1/handler.ts` implements RPC handlers per domain
- Use `cachedFetchJson()` for all on-demand fetches — it coalesces concurrent cache misses

---

## Key Patterns

### Panel Pattern

All UI panels extend the `Panel` base class in `src/components/Panel.ts`:

```typescript
class MyPanel extends Panel {
  async fetchData(): Promise<boolean> {
    // fetch data, call this.setContent(html) on success
    // call this.showError(msg, retry) on failure
    // return true if data was successfully displayed
  }
}
```

- Use `this.setContent(html)` — it's debounced 150ms and handles DOM updates
- Use `this.showError(msg, retry)` for error states
- Guard against overwriting good data: use a `_hasData` boolean flag — do not replace live data with an error on retry
- Register in `src/config/panels.ts` and relevant variant configs in `src/config/variants/`
- Wire data loading in `src/app/data-loader.ts`
- Register in `src/app/panel-layout.ts`

### Adding a New API Endpoint (Sebuf/Proto flow)

1. Define proto message in `proto/worldmonitor/<domain>/v1/`
2. Add RPC with `(sebuf.http.config)` annotation
3. Run `make generate` to regenerate stubs in `src/generated/`
4. Implement handler in `server/worldmonitor/<domain>/v1/handler.ts`
5. Wire in domain's `api/<domain>/v1/<rpc>.ts`
6. Use `cachedFetchJson()` — always include request-varying params in the cache key

For non-JSON payloads (XML, HTML embeds, binary), use a standalone Edge Function in `api/` instead.

### Proto Conventions

- Time fields: use `int64` (Unix epoch ms), not `google.protobuf.Timestamp`
- Apply `[(sebuf.http.int64_encoding) = INT64_ENCODING_NUMBER]` on time fields so TypeScript gets `number` not `string`
- GET fields need `(sebuf.http.query)` annotation
- `repeated string` fields need `parseStringArray()` in the handler
- Every RPC needs `option (sebuf.http.config) = { path: "...", method: POST }`

### Caching

```
Bootstrap seed (Railway → Redis on schedule)
  ↓ miss
In-memory (per Vercel instance, short TTL)
  ↓ miss
Redis/Upstash (cachedFetchJson coalesces concurrent misses)
  ↓ miss
Upstream API (result written back to Redis + seed-meta)
```

Cache tiers (s-maxage):

| Tier | TTL | Use case |
|------|-----|----------|
| fast | 5m | Live event streams, flight status |
| medium | 10m | Market quotes |
| slow | 30m | ACLED events, cyber threats |
| static | 2h | Humanitarian summaries, ETF flows |
| daily | 24h | Critical minerals, static reference |
| no-store | 0 | Vessel snapshots, aircraft tracking |

**Cache key rule**: ALWAYS include every request-varying parameter in the cache key. Missing a param causes cross-request data leakage.

### Seed Scripts

`scripts/seed-*.mjs` use `runSeed(domain, name, key, fetchFn, options)` from `scripts/_seed-utils.mjs`:

- TTL must be ≥ 3× seed interval
- Atomic publish acquires a Redis lock (SET NX), validates, writes cache key and `seed-meta:<key>` with `{ fetchedAt, recordCount }`
- Every new data source MUST also be wired into `api/bootstrap.js` for hydration

### Circuit Breakers

- `src/utils/circuit-breaker.ts` — one breaker instance per data domain
- Used in data loaders to prevent cascade failures on repeated upstream errors

---

## Variant System

The app ships multiple variants from the same source. Controlled by `VITE_VARIANT` env var or hostname:

| Variant | Command | Hostname | Focus |
|---------|---------|----------|-------|
| `full` | `npm run dev` | worldmonitor.app | All features |
| `tech` | `npm run dev:tech` | tech.worldmonitor.app | Technology/AI/cybersecurity |
| `finance` | `npm run dev:finance` | finance.worldmonitor.app | Financial markets |
| `commodity` | `npm run dev:commodity` | — | Commodity markets |
| `happy` | `npm run dev:happy` | — | Positive news only |

Configs live in `src/config/variants/`. Variant change resets all settings to defaults.

---

## Testing

| Suite | Command | Runner | What |
|-------|---------|--------|------|
| Unit/Integration | `npm run test:data` | `node:test` | Handlers, cache keying, circuit breakers, data validation |
| Sidecar/API | `npm run test:sidecar` | `node:test` | CORS, Edge Functions, sidecar behavior |
| E2E | `npm run test:e2e` | Playwright | Theme, circuit breaker persistence, mobile interactions |
| Visual regression | `npm run test:e2e:visual` | Playwright | Golden screenshot comparison per variant |
| Convex | `npm run test:convex` | vitest | Convex backend functions |

Test files:
- `tests/*.test.{mjs,mts}` — unit/integration
- `api/*.test.mjs` — API handler tests
- `src-tauri/sidecar/*.test.mjs` — sidecar tests
- `e2e/*.spec.ts` — Playwright specs

---

## Pre-Push Hook (runs before every `git push`)

The `.husky/pre-push` hook runs these checks in order — all must pass:

1. TypeScript check (`npm run typecheck` + `npm run typecheck:api`)
2. CJS syntax validation (`node -c` on `scripts/*.cjs`)
3. Unicode safety check
4. Architectural boundary check (`npm run lint:boundaries`)
5. Edge function esbuild bundle check (each `api/*.js` must bundle without errors)
6. Unit tests (`npm run test:data`)
7. Edge function import guardrails (`tests/edge-functions.test.mjs`)
8. Markdown lint (`npm run lint:md`)
9. MDX lint (Mintlify compatibility)
10. Proto freshness check (if proto files changed: `make generate` and verify no diff)
11. Version sync check (`npm run version:check`)

Additionally, push is blocked if:
- The PR for the branch is already MERGED or CLOSED
- The branch is more than 20 commits ahead of `origin/main` (branch contamination guard)
- `scripts/package.json` changed but `scripts/package-lock.json` was not committed

---

## CI/CD (GitHub Actions)

| Workflow | Trigger | Checks |
|----------|---------|--------|
| `typecheck.yml` | PR + push to main | `tsc --noEmit` for src and API |
| `lint.yml` | PR (markdown changes) | markdownlint-cli2 |
| `proto-check.yml` | PR (proto changes) | Generated code freshness |
| `build-desktop.yml` | Release tag / manual | 5-platform Tauri matrix build |
| `docker-publish.yml` | Release / manual | Multi-arch Docker image (GHCR) |
| `test-linux-app.yml` | Manual | AppImage smoke test |

**Deployment**:
- **Web**: Vercel (auto-deploy on push to main), Edge Functions
- **Relay/Seeds**: Railway (Docker, cron services)
- **Desktop**: Tauri via GitHub Actions (macOS ARM64/x64, Windows x64, Linux x64/ARM64)
- **Docs**: Mintlify (proxied at `/docs`)

---

## Critical Conventions — Must Follow

### Banned Patterns

```typescript
// BANNED — causes issues in some edge runtimes
fetch.bind(globalThis)

// CORRECT alternative
(...args) => globalThis.fetch(...args)
```

### Must-Do Rules

- Always include `User-Agent` header in all server-side fetch calls
- Yahoo Finance requests must be staggered with 150ms delays between calls
- Every new data source MUST have bootstrap hydration wired in `api/bootstrap.js`
- Every Redis seed script MUST write `seed-meta:<key>` for health monitoring
- `src/generated/` files are auto-generated — **never edit by hand**
- CSP must be kept in sync across three locations: `index.html`, `vercel.json`, and `src-tauri/tauri.conf.json`
- When modifying `scripts/package.json`, always commit the updated `scripts/package-lock.json`

### TypeScript Strictness

- Strict mode is on (`tsconfig.json`): `strict`, `noUnusedLocals`, `noUnusedParameters`, `noUncheckedIndexedAccess`
- Avoid `any` — use proper types or `unknown` with type guards
- `@/` path alias maps to `src/`

### Code Style (Biome)

- `noVar`: error — always use `const`/`let`
- `noFallthroughSwitchClause`: error
- `noGlobalAssign`: error
- `useConst`: warning — prefer `const`
- `noExcessiveCognitiveComplexity`: warning at 50
- Formatter is **disabled** — Biome is linter-only here

---

## Desktop Architecture (Tauri)

The desktop app is Tauri v2 (Rust shell) + a Node.js sidecar:

- **Sidecar** (`src-tauri/sidecar/local-api-server.mjs`): Runs on a dynamic port, dynamically loads `api/` Edge Function handlers, injects secrets from platform keyring, monkey-patches `globalThis.fetch` to force IPv4 (many government APIs have broken IPv6)
- **Fetch patching** (`src/services/runtime.ts`): On desktop, all `/api/*` requests route to the sidecar with a short-TTL bearer token from Tauri IPC. Falls back to cloud API if sidecar fails
- **Secret storage**: Platform keyring (macOS Keychain, Windows Credential Manager, Linux keyring) — never plaintext

---

## Environment Variables

Copy `.env.example` to `.env.local`. All keys are optional — the app runs without them but those features will be disabled.

Key categories:
- `GROQ_API_KEY` / `OPENROUTER_API_KEY` — AI summarization (LLM)
- `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` — cross-user Redis cache
- `FINNHUB_API_KEY` — market data
- `EIA_API_KEY` — energy data
- `FRED_API_KEY` — economic data (FRED)
- Various other external API keys (see `.env.example` for full list)

---

## Development Branch

Current active development branch: `claude/add-claude-documentation-IybEA`

Always branch from `origin/main`, not from a local main that may have unmerged feature branches. Branches must stay within 20 commits of `origin/main` (enforced by pre-push hook).

---

## Further Reading

- [`AGENTS.md`](AGENTS.md) — condensed agent entry point with repository map and key patterns
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — deep system reference (deployment topology, caching, security model, testing)
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — PR process, coding standards, adding data sources
- [`docs/architecture.mdx`](docs/architecture.mdx) — design philosophy and why decisions were made
- [`docs/data-sources.mdx`](docs/data-sources.mdx) — full data sources catalog
- [`docs/adding-endpoints.mdx`](docs/adding-endpoints.mdx) — step-by-step endpoint guide
- [`compound-engineering.local.md`](compound-engineering.local.md) — review agent context (Panel patterns, seed patterns, RPC patterns)
