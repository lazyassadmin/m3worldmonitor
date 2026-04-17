# PoliWatch

> Open-source political accountability dashboard — correlate congressional stock trades with the legislation members help write, the committees they sit on, and the votes they cast.

![screenshot placeholder](docs/screenshot.png)

PoliWatch ingests STOCK Act disclosures (House PTRs, Senate eFD, Quiver Quantitative), cross-references them against real-time data from the [Congress.gov API](https://api.congress.gov/), scores each trade for suspicious timing, and ships the results to an interactive dashboard and (optionally) your inbox.

It is 100% self-hosted and built on free, publicly available data. No paywalls. No API gatekeepers.

---

## Quick Start

```bash
git clone https://github.com/your-org/poliwatch.git
cd poliwatch
cp .env.example .env
# Fill in CONGRESS_API_KEY (free at https://api.congress.gov/sign-up/)
docker compose up --build
```

Then open:

| Service | URL |
|---|---|
| Dashboard (Streamlit) | http://localhost:8501 |
| REST API (FastAPI) | http://localhost:8000/docs |

### Run without Docker (dev)

```bash
# One-time
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head

# Run each in its own terminal
uvicorn poliwatch.api.main:app --reload
streamlit run poliwatch/dashboard/app.py
python -m poliwatch.ingestion.scheduler         # periodic jobs
python -m poliwatch.ingestion.scheduler --backfill   # pull historical data (2012+)
```

---

## How the Suspicion Score Is Calculated

Every trade gets a score from **0 to 100**. Higher = more suspicious timing / context.

| Factor | Points | Rationale |
|---|---|---|
| Disclosure delay > 30 days | +20 | STOCK Act requires disclosure within 30 days of awareness |
| Disclosure delay > 45 days | +35 | Hard statutory cap — past this is a likely violation |
| Committee overlap with traded sector | +25 | Member sits on a committee overseeing the company's industry |
| Bill timing within 14 days of trade | +25 | Trade clustered around related-bill action (intro, markup, vote) |
| Trade size > $50,000 | +10 | Higher-dollar trades carry more signal |
| Trade size > $250,000 | +15 (instead of +10) | Very large trades are noteworthy on their own |
| Pattern: 3+ trades in same ticker within 90 days | +10 | Coordinated accumulation or unwinding |

Scoring lives in `poliwatch/analysis/scoring.py`. Correlation lives in `poliwatch/analysis/correlation.py`. Both are deterministic and unit-tested.

Trades that score at or above `SUSPICION_ALERT_THRESHOLD` (default **60**) trigger an alert via email and any configured webhooks.

---

## Data Sources

All sources are free and public.

| Source | Purpose | Key required |
|---|---|---|
| [Congress.gov API](https://api.congress.gov/) | Bills, votes, members, committee assignments | Yes (free) |
| [House Financial Disclosures](https://disclosures-clerk.house.gov/FinancialDisclosure) | House PTR XML + PDFs | No |
| [Senate eFD](https://efts.senate.gov/) | Senate periodic transaction reports | No |
| [Quiver Quantitative](https://api.quiverquant.com/beta/live/congresstrading) | Aggregated congressional trades (fallback) | No (basic endpoints) |
| [ProPublica Congress API](https://www.propublica.org/datastore/api/propublica-congress-api) | Supplemental member/vote data | Optional |
| [OpenSecrets API](https://www.opensecrets.org/api/) | Campaign finance (Phase 2) | Optional |

The app degrades gracefully — it runs with only `CONGRESS_API_KEY` set; every optional source is skipped if its key is missing.

---

## Architecture

```
┌──────────────┐   ┌───────────────┐   ┌────────────────┐
│  Ingestion   │──▶│   SQLite /    │──▶│    Analysis    │
│ (APScheduler)│   │  PostgreSQL   │   │ (correlation + │
└──────────────┘   └───────────────┘   │   scoring)     │
       ▲                 ▲             └────────┬───────┘
       │                 │                      │
   House / Senate   FastAPI REST API            ▼
   STOCK Act + Quiver ◀─────────────── Streamlit dashboard
                          │                     │
                          └──▶ SMTP / Discord / Slack alerts
```

- **Ingestion** — `poliwatch/ingestion/` — async `httpx` clients + APScheduler jobs, idempotent re-ingestion.
- **Storage** — SQLAlchemy 2.0 ORM, Alembic migrations, SQLite by default, PostgreSQL via `DATABASE_URL`.
- **Analysis** — `poliwatch/analysis/` — trade↔bill correlation, statistical anomaly detection, suspicion scoring.
- **API** — `poliwatch/api/` — FastAPI with `/members`, `/trades`, `/alerts` routes.
- **Dashboard** — `poliwatch/dashboard/app.py` — 6 Streamlit pages (Overview, Member Explorer, Trade Feed, Ticker Deep Dive, Alerts, Statistics).
- **Alerts** — `poliwatch/alerts/notifier.py` — SMTP + Discord + Slack.

---

## Project Layout

```
poliwatch/
├── alembic/                  # DB migrations
├── data/                     # Downloaded disclosures + SQLite DB (gitignored)
├── poliwatch/
│   ├── config.py             # Pydantic settings from env vars
│   ├── database.py           # SQLAlchemy engine + session
│   ├── models/               # ORM models
│   ├── ingestion/            # Data pipelines
│   ├── analysis/             # Correlation + scoring
│   ├── api/                  # FastAPI app + routes
│   ├── dashboard/            # Streamlit UI
│   └── alerts/               # Email + webhook notifiers
├── tests/                    # pytest suites
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## Environment Variables

Copy `.env.example` to `.env`. Required: `CONGRESS_API_KEY`. Everything else is optional. See `.env.example` for the full list.

---

## Contributing

Contributions welcome! To get started:

1. Fork the repo and create a feature branch.
2. Run `uv pip install -e ".[dev]"` and `pytest` to make sure the suite is green.
3. Add tests for your change (see `tests/`).
4. Run `ruff check . && ruff format .`.
5. Open a PR with a clear description of the change.

Good first issues are labelled [`good-first-issue`](../../labels/good-first-issue).

---

## License

MIT — see [LICENSE](LICENSE).

---

## Disclaimer

PoliWatch produces *signals*, not verdicts. A high suspicion score is a prompt to investigate, not proof of wrongdoing. All underlying data comes from primary public sources linked from every trade row in the dashboard.
