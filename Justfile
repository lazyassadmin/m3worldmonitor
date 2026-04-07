# World Monitor — command runner
# Install: https://just.systems  |  Usage: just <recipe>  |  List: just --list

set dotenv-load := true

# Show available recipes
default:
    @just --list

# ── Setup ────────────────────────────────────────────────────────────────────

# Install everything (buf, sebuf plugins, npm deps, Playwright)
install:
    make install

# Install npm deps only
deps:
    npm install

# ── Development ──────────────────────────────────────────────────────────────

# Start dev server — full variant (default)
dev:
    npm run dev

# Start dev server — tech variant
dev-tech:
    npm run dev:tech

# Start dev server — finance variant
dev-finance:
    npm run dev:finance

# Start dev server — commodity variant
dev-commodity:
    npm run dev:commodity

# Start dev server — happy variant
dev-happy:
    npm run dev:happy

# Preview production build locally
preview:
    npm run preview

# ── Code Quality ─────────────────────────────────────────────────────────────

# Format all source files (Biome)
format:
    npx biome format --write ./src ./server ./api ./tests ./e2e ./scripts ./middleware.ts

# Check formatting without writing (CI-safe)
format-check:
    npx biome format ./src ./server ./api ./tests ./e2e ./scripts ./middleware.ts

# Lint all source files (Biome)
lint:
    npm run lint

# Lint and auto-fix
lint-fix:
    npm run lint:fix

# Check architectural import boundaries
lint-boundaries:
    npm run lint:boundaries

# Lint markdown files
lint-md:
    npm run lint:md

# Run all lint checks
lint-all: lint lint-boundaries lint-md

# TypeScript check — src/
typecheck:
    npm run typecheck

# TypeScript check — api/
typecheck-api:
    npm run typecheck:api

# TypeScript check — everything
typecheck-all:
    npm run typecheck:all

# Full quality gate (format-check + typecheck + lint + boundaries)
check: format-check typecheck-all lint-all

# ── Testing ───────────────────────────────────────────────────────────────────

# Unit + integration tests
test:
    npm run test:data

# Sidecar + API handler tests
test-sidecar:
    npm run test:sidecar

# Convex backend tests
test-convex:
    npm run test:convex

# E2E tests — all variants
test-e2e:
    npm run test:e2e

# E2E tests — full variant only
test-e2e-full:
    npm run test:e2e:full

# E2E tests — tech variant only
test-e2e-tech:
    npm run test:e2e:tech

# Visual regression tests
test-visual:
    npm run test:e2e:visual

# Update visual regression golden screenshots
test-visual-update:
    npm run test:e2e:visual:update

# Validate RSS feeds
test-feeds:
    npm run test:feeds

# Run all fast tests (unit + sidecar + convex)
test-all: test test-sidecar test-convex

# ── Build ─────────────────────────────────────────────────────────────────────

# Build — full variant
build:
    npm run build

# Build — tech variant
build-tech:
    npm run build:tech

# Build — finance variant
build-finance:
    npm run build:finance

# Build — all variants
build-all: build build-tech build-finance

# ── Proto / Code Generation ───────────────────────────────────────────────────

# Regenerate proto stubs (requires buf + sebuf plugins)
generate:
    make generate

# Lint proto files
proto-lint:
    make lint

# Check for breaking proto changes vs main
proto-breaking:
    make breaking

# ── Desktop ───────────────────────────────────────────────────────────────────

# Start desktop dev (with devtools)
desktop-dev:
    npm run desktop:dev

# Build desktop — full variant
desktop-build:
    npm run desktop:build:full

# Build desktop — tech variant
desktop-build-tech:
    npm run desktop:build:tech

# ── Deployment ────────────────────────────────────────────────────────────────

# Sync version across desktop manifests
version-sync:
    npm run version:sync

# Verify version is in sync (CI-safe)
version-check:
    npm run version:check
