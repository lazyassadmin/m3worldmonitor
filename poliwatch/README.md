# PoliWatch

**Open-source congressional stock trade accountability dashboard.**

Ingests STOCK Act filings, correlates trades with legislation and committee assignments, flags statistically suspicious trades, and sends alerts.

![Dashboard screenshot placeholder](docs/screenshot.png)

---

## Quick Start

```bash
git clone https://github.com/your-org/poliwatch
cd poliwatch
cp .env.example .env
# Fill in CONGRESS_API_KEY (free from https://api.congress.gov/sign-up/)
docker-compose up
```

- **Dashboard:** http://localhost:8501
- **API:** http://localhost:8000
- **API docs:** http://localhost:8000/docs

### Without Docker

```bash
pip install uv
uv pip install -e .
cp .env.example .env
# Edit .env with your API keys
poliwatch ingest          # fetch initial data
poliwatch serve &         # start API
poliwatch dashboard       # launch Streamlit
```

### Backfill historical data (2012–present)

```bash
poliwatch ingest --backfill
```

---

## How the Suspicion Score Works

Each trade receives a 0–100 suspicion score based on five factors:

| Factor | Points | Trigger |
|--------|--------|---------|
| Disclosure delay | +20 | Filed >30 days after trade (STOCK Act limit) |
| Disclosure delay | +35 | Filed >45 days after trade |
| Committee overlap | +25 | Member sits on committee overseeing the traded company's sector |
| Bill timing | +25 | Trade within 14 days of a related bill's major action |
| Trade size | +10 | Transaction >$50,000 |
| Trade size | +15 | Transaction >$250,000 |
| Pattern | +10 | 3+ trades in same ticker within 90 days |

Scores ≥ 60 trigger email and/or webhook alerts.

---

## Data Sources

| Source | URL | Notes |
|--------|-----|-------|
| Quiver Quantitative | https://api.quiverquant.com/beta/live/congresstrading | Free, no key required |
| House STOCK Act PTRs | https://disclosures-clerk.house.gov/FinancialDisclosure | Bulk XML downloads |
| Senate eFD | https://efts.senate.gov/LATEST/search-index | Full-text search API |
| Congress.gov API | https://api.congress.gov/v3/ | Free, key required |
| ProPublica Congress API | https://www.propublica.org/datastore/api/propublica-congress-api | Free, key required |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CONGRESS_API_KEY` | Yes | Congress.gov API key |
| `DATABASE_URL` | No | SQLite (default) or PostgreSQL |
| `PROPUBLICA_API_KEY` | No | Vote data |
| `OPENSECRETS_API_KEY` | No | Campaign finance (Phase 2) |
| `SUSPICION_ALERT_THRESHOLD` | No | Default: 60 |
| `DATA_REFRESH_INTERVAL_HOURS` | No | Default: 6 |
| `ALERT_EMAIL_*` / `SMTP_*` | No | Email notifications |
| `DISCORD_WEBHOOK_URL` | No | Discord alerts |
| `SLACK_WEBHOOK_URL` | No | Slack alerts |

---

## Project Structure

```
poliwatch/
├── poliwatch/
│   ├── config.py           # Pydantic settings
│   ├── database.py         # SQLAlchemy async engine
│   ├── models/             # ORM models (member, trade, bill, vote, alert)
│   ├── ingestion/          # Data fetchers (Quiver, House, Senate, Congress.gov)
│   ├── analysis/           # Correlation engine + suspicion scoring
│   ├── api/                # FastAPI routes
│   ├── dashboard/          # Streamlit 6-page dashboard
│   └── alerts/             # Email + webhook notifier
├── tests/                  # pytest test suite
├── alembic/                # DB migrations
├── docker-compose.yml
└── pyproject.toml
```

---

## Contributing

1. Fork and clone
2. `uv pip install -e ".[dev]"`
3. Make changes, run `pytest`
4. Open a pull request

Please keep all API keys in environment variables. Never commit `.env`.

---

## License

MIT — see [LICENSE](LICENSE).
