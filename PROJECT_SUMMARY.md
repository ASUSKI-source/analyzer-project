# Project Summary: Stocks/Crypto AI Analyzer

## 🌟 Mission
The **Stocks/Crypto AI Analyzer** is a high-performance web application designed to bridge the gap between raw market data and actionable investment insights. It provides real-time tracking of assets (Stocks & Crypto) paired with a sophisticated "Hybrid AI" engine that synthesizes technical signals, fundamental health, and news sentiment into human-readable strategic reports.

---

## 🚀 Core Features
- **Real-time Dashboard:** Live price tracking for Stocks (Polygon.io) and Crypto (Binance/CoinGecko) with sub-10s latency.
- **AI-Powered Watchlist Reports:** A "full-stack" analysis engine that uses Anthropic's Claude to generate structured, professional-grade market reports.
- **Intraday Technicals:** Advanced charting using TradingView's Lightweight Charts, supporting 1h, 1d, 1w, and 1m timeframes.
- **Multi-Horizon Synthesis:** AI analysis that balances tactical momentum (1h/1d) against strategic structural health (1w/1m).
- **Snapshot Infrastructure:** Background workers (Celery) that pre-calculate and cache technical/fundamental "snapshots" to ensure AI reports are lightning-fast.
- **Resilient Fallbacks:** Robust error handling that serves "last good" reports if API providers (Finnhub/Polygon) time out or hit rate limits.

---

## 🛠️ Technology Stack

### Backend (Python / FastAPI)
- **Framework:** FastAPI (Asynchronous API)
- **Database:** PostgreSQL + TimescaleDB (Time-series optimization)
- **Cache & Queue:** Redis
- **Background Tasks:** Celery (Enrichment & Polling)
- **AI Engine:** LangChain + Anthropic (Claude 3.5 Haiku)
- **ORM:** SQLAlchemy 2.0 (Async) + Alembic (Migrations)

### Frontend (TypeScript / Next.js)
- **Framework:** Next.js 16 (App Router)
- **UI Library:** React 19 + Framer Motion (Animations)
- **Styling:** Tailwind CSS 4 (Custom Design System with Glassmorphism)
- **Charting:** Lightweight Charts (High-performance Canvas-based)
- **State Management:** React Context + Custom Hooks

---

## 📂 Project Structure
```text
/
├── /backend                   # Python FastAPI Application
│   ├── /app                   # Main logic (api, services, tasks, ai)
│   ├── /alembic               # DB migrations
│   └── main.py                # Server entry point
├── /frontend                  # Next.js Application
│   ├── /app                   # Pages & Layouts
│   ├── /components            # UI & Feature components
│   └── /services              # API Client
├── /docker                    # Dev infrastructure (Redis, Timescale)
├── /tmp                       # Temporary scratchpad
├── CONVENTIONS.md             # Coding standards & Architecture rules
└── railway.json               # Production deployment config
```

---

## 🚦 Getting Started
1. **Infrastructure:** Start the dev stack via `docker-compose up -d` (Postgres/Redis).
2. **Backend:**
   - `cd backend`
   - `pip install -r requirements.txt`
   - `uvicorn main:app --reload`
3. **Frontend:**
   - `cd frontend`
   - `npm install`
   - `npm run dev`
4. **Environment:** Ensure `.env` files are populated with `ANTHROPIC_API_KEY`, `POLYGON_API_KEY`, and `FINNHUB_API_KEY`.
