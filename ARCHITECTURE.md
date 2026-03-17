# Architecture Deep Dive: Stocks/Crypto AI Analyzer

## 🏗️ System Overview
The application follows a **decoupled monolith** architecture. The frontend (Next.js) handles the user interface and real-time visualization, while the backend (FastAPI) orchestrates data ingestion, technical analysis, and AI synthesis.

### 🌐 Deployment Model
- **Platform:** Railway (PaaS)
- **Networking:** Backend is proxied through Railway's edge (25s timeout limit).
- **Persistence:** TimescaleDB for historical OHLCV data.
- **Ephemera:** Redis for global rate-limiting, "Heat Cache" (5m), and AI result caching (8h).

---

## 📊 Data Pipeline Architecture

### 1. Market Data Ingestion
The system uses a multi-tier provider strategy to ensure maximum uptime and data quality:
- **Tier 1 (Polygon.io):** Primary source for Stocks historical and real-time data.
- **Tier 2 (Binance.us / CoinGecko):** Primary sources for Cryptocurrency data.
- **Tier 3 (Finnhub):** Used for fundamental data, earnings, and news sentiment.
- **Fallback Layer:** Synthetic data generation is triggered only if all providers fail, ensuring the UI remains interactive.

### 2. Time-Series Storage (TimescaleDB)
Market candles are stored in the `asset_candles` table. 
- **Timeframes:** 1h, 1d, 1w.
- **Optimization:** Uses TimescaleDB hypertables with indexing on `(asset_id, timestamp, timeframe)` to allow sub-millisecond lookups for historical charts.
- **Migrations:** Managed via Alembic; strictly follows the schema defined in `backend/app/models/market.py`.

---

## 🧠 AI Analysis Pipeline ("The Brain")

The AI engine lives in `backend/app/services/ai_analyzer.py` and is designed for **Reliability and Budgeting**.

### 1. Budgeted Execution
To avoid Railway proxy timeouts (30s), the AI pipeline enforces a strict internal budget:
- **Total Budget:** 24s.
- **Assembly (Data Gathering):** 5s budget. If data lags, we ship a "Partial Context."
- **Model Inference (Anthropic):** 17s budget.
- **Parsing/Formatting:** 1.5s.

### 2. The "Map-Reduce" AI Pattern
For small watchlists (1-2 symbols), a single direct call to Anthropic is used. For larger watchlists (3-20 symbols), the system switches to a two-stage process:
1. **Map:** Concurrent per-asset summaries (What does Symbol X look like?).
2. **Reduce:** A final synthesis call that takes the per-asset summaries and generates the portfolio-wide "Overall Insight."

### 3. Context Pruning
Before sending data to the LLM, the system runs `_prune_context()`. This ensures we don't exceed token limits by removing redundant technical fields and trimming news descriptions, keeping the payload under 8k tokens for maximum speed.

---

## ⚡ Background Workers & Enrichment
The `Celery` worker (`backend/app/tasks`) runs on a schedule to "pre-warm" the system:
- **Snapshot Tasks:** Runs every hour to calculate RSP/SMA/EMA for all active assets.
- **Fundamental Enrichment:** Refreshes earnings and balance sheet data every 12 hours.
- **Analysis Jobs:** Long-running AI reports can be backgrounded and polled via the `/ai/watchlist-analysis/jobs` endpoints.

---

## 🔐 Engineering Conventions
- **Fat Services, Thin Routes:** All business logic must live in `/services`. Routes should only handle DTO validation and response mapping.
- **Standardized Error Shape:** All errors return a JSON object with `error`, `message`, and `status_code` to allow the frontend to display graceful toasts.
- **Rate-Limiting Rails:** The `PolygonRateLimiter` (Leaky Bucket) prevents API keys from being suspended during heavy dashboard usage.

---

## 🔄 Interaction Flow (Sequence)
1. **Frontend:** User opens dashboard -> `useDashboardPulse` hits `/market/quotes`.
2. **Backend:** Checks Redis for "Heat Cache" (10s). If miss, pings Polygon/Binance.
3. **Frontend:** User clicks "Analyze Watchlist" -> UI shows AI loading state.
4. **Backend:** Starts AI Pipeline (Assembles DB + Live Context -> Prunes -> LLM Call -> Caches -> Returns).
5. **Frontend:** Renders the structured JSON via `AnalysisReportPanel`.
