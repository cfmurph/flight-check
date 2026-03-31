# Canadian Flight Deal Scanner

A Python tool that scans domestic Canadian flight routes via the [Amadeus API](https://developers.amadeus.com) and reports the best deals, ranked by a composite scoring model that weighs price discounts, absolute fare cost, non-stop preference, seat scarcity, and booking-window timing.

---

## Features

- **Automatic route generation** across 22 Canadian airports in three tiers (major hubs → regional)
- **Composite deal scoring** (0–100) combining discount %, absolute price, non-stop bonus, seat urgency, and advance-booking window
- **Rich terminal tables** with colour-coded scores and deal tags (`NONSTOP`, `FLASH_SALE`, `GREAT_DEAL`, `SUB_$100`, `ALMOST_FULL`, …)
- **JSON & CSV report files** saved per scan run
- **Watch mode** – re-scans on a configurable interval (default 6 h) and saves fresh reports
- **Fully configurable** via CLI flags or environment variables

---

## Quickstart

### 1. Get a free SerpApi key

Sign up at <https://serpapi.com/users/sign_up> — **100 free searches/month**, no credit card required.  
SerpApi provides real-time Google Flights data for all Canadian routes.

> **Note on Amadeus:** The Amadeus Self-Service API is being decommissioned on **July 17 2026**.  
> The scanner still supports Amadeus as a fallback (set `AMADEUS_CLIENT_ID` + `AMADEUS_CLIENT_SECRET`),  
> but SerpApi is now the recommended and default provider.

### 2. Install

```bash
pip install -r requirements.txt
pip install -e .
```

### 3. Configure credentials

```bash
cp .env.example .env
# Edit .env and set SERPAPI_KEY=your_key_here
```

### 4. Run a scan

```bash
# Scan all Tier-1→Tier-2 routes, 90 days ahead (default)
canada-flights scan

# Scan specific origins only
canada-flights scan --origins YYZ,YUL --days 60

# Scan a single route with tight filters
canada-flights scan --origins YVR --destinations YYZ --max-price 250 --min-discount 20

# All airports (slow – many API calls)
canada-flights scan --tier 3 --date-step 7
```

### 5. Watch mode (continuous scanning)

```bash
canada-flights watch --interval 6 --origins YYZ,YVR,YUL
```

### 6. List supported airports

```bash
canada-flights airports
canada-flights airports --tier 1
```

---

## CLI reference

```
canada-flights scan [OPTIONS]

  Options:
    -o, --origins TEXT       Comma-separated IATA origin codes (e.g. YYZ,YVR)
    -d, --destinations TEXT  Comma-separated IATA destination codes
    -n, --days INTEGER       Days ahead to scan  [default: 90]
    --max-price FLOAT        Max price CAD to consider a deal  [default: 500.0]
    --min-discount FLOAT     Min discount % vs average  [default: 15.0]
    --tier [1|2|3]           Max destination tier  [default: 2]
    --date-step INTEGER      Scan every N days  [default: 3]
    --top INTEGER            Deals to display  [default: 30]
    --output-dir TEXT        Report directory  [default: ./reports]
    --no-file                Skip saving report files
    -v, --verbose            Enable debug logging

canada-flights watch [OPTIONS]
canada-flights airports [--tier 1|2|3]
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SERPAPI_KEY` | *(recommended)* | SerpApi key — Google Flights data, 100 free/month |
| `AMADEUS_CLIENT_ID` | *(legacy, deprecated Jul 2026)* | Amadeus API client ID |
| `AMADEUS_CLIENT_SECRET` | *(legacy, deprecated Jul 2026)* | Amadeus API client secret |
| `AMADEUS_ENV` | `test` | `test` or `production` (Amadeus only) |
| `SCAN_ORIGINS` | Tier-1 airports | Comma-separated IATA origins |
| `SCAN_DAYS_AHEAD` | `90` | Days ahead to search |
| `DEAL_PRICE_THRESHOLD` | `500` | Max deal price in CAD |
| `DEAL_DISCOUNT_PCT` | `15` | Min % discount vs average |
| `REPORT_DIR` | `./reports` | Output directory for reports |

The scanner automatically picks the best available client: `SERPAPI_KEY` takes priority; it falls back to Amadeus credentials if SerpApi is not configured.

---

## Deal scoring model

Each offer is given a composite score (0–100):

| Component | Weight | Description |
|---|---|---|
| Price discount vs average | 45% | How far below the route average this fare is |
| Absolute price | 25% | Fares ≤$50 = perfect; ≥$400 = zero |
| Non-stop bonus | 15% | Direct flights score higher |
| Seat scarcity | 10% | ≤2 seats left = urgency bonus |
| Advance window | 5% | Sweet spot: 3–8 weeks before departure |

Deals are also tagged for quick identification: `NONSTOP`, `FLASH_SALE` (≥40% off), `GREAT_DEAL` (≥25% off), `GOOD_DEAL` (≥15% off), `ALMOST_FULL` (≤3 seats), `SUB_$100`, `UNDER_$150`.

---

## Project structure

```
canada_flight_scanner/
├── airports.py        – Airport catalogue and route generation
├── client_factory.py  – Auto-selects SerpApi or Amadeus based on available credentials
├── serpapi_client.py  – SerpApi (Google Flights) client — recommended
├── api_client.py      – Amadeus SDK wrapper — legacy fallback
├── models.py          – Data classes (FlightOffer, FlightDeal, ScanResult, …)
├── deal_engine.py     – Scoring logic and deal identification
├── scanner.py         – Orchestrator (iterates routes + dates)
├── reporter.py        – Rich console tables + JSON/CSV file output
├── scheduler.py       – Recurring watch-mode scheduler
└── cli.py             – Click CLI entry point
tests/
├── test_airports.py
├── test_api_client.py
├── test_client_factory.py
├── test_serpapi_client.py
├── test_deal_engine.py
└── test_models.py
reports/               – Auto-created; scan results saved here
```

---

## Running tests

```bash
pytest
```

---

## Notes on the free tier

### SerpApi (recommended)
- **100 searches/month** free, no credit card required
- Returns live Google Flights prices
- Rate limit: no hard limit, but the scanner pauses 0.5 s between requests by default
- Paid plans start at $50/month for 5,000 searches if you need more volume

### Amadeus (legacy — decommissioned July 17 2026)
- The Amadeus Self-Service API will shut down on **July 17 2026**
- Until then it still works; the scanner emits a deprecation warning when using it
- For post-July access, Amadeus requires an Enterprise contract (paid)
