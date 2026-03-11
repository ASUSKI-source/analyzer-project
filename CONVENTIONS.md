# Stocks/Crypto AI Analyzer: Engineering Conventions & Project Structure

This document is the absolute source of truth for our engineering standards. All future code must adhere to these patterns to ensure maintainability at scale.

## 1. Complete Folder Structure

We are using a decoupled monolithic repository structure (one repo, two main sub-projects).

```text
/analyzer-project
├── /frontend                  # Next.js Application (React + TypeScript)
│   ├── /app                   # Next.js App Router (Pages & Layouts)
│   │   ├── /(auth)            # Auth-protected route groups
│   │   ├── /api               # Next.js internal API (fetching from Python backend)
│   │   └── /dashboard         # Main application routes
│   ├── /components            # Reusable UI components
│   │   ├── /ui                # Generic UI (Buttons, Inputs - e.g. shadcn/ui)
│   │   └── /features          # Domain-specific components (e.g. ChartWidget, AssetTable)
│   ├── /lib                   # Frontend utilities (formatters, constants)
│   ├── /hooks                 # Custom React hooks (e.g. useWebSocket, useAuth)
│   ├── /services              # API client wrapper for the Python backend
│   └── /types                 # Shared TypeScript interfaces
│
├── /backend                   # Python FastAPI Application
│   ├── /app                   # Main application code
│   │   ├── /api               # API Routers (v1)
│   │   │   └── /routes        # Route handlers (Controllers)
│   │   ├── /core              # App settings, DB connections, Lifespan events
│   │   ├── /models            # SQLAlchemy DB Models (ORM)
│   │   ├── /schemas           # Pydantic validation schemas (Input/Output)
│   │   ├── /services          # CORE BUSINESS LOGIC lives here
│   │   ├── /tasks             # Celery background workers (Polling data, heavy crunching)
│   │   ├── /ai                # LLM/LangChain integration and prompts
│   │   └── /utils             # Helper functions (Math, formatting)
│   ├── /alembic               # Database migration scripts
│   ├── /tests                 # Pytest suite
│   ├── main.py                # FastAPI entry point
│   ├── requirements.txt       # Python dependencies
│   └── alembic.ini            # Alembic config
│
├── /docker                    # Docker Compose files for local dev (Timescale, Redis)
├── .gitignore
├── README.md
└── CONVENTIONS.md             # This file
```

---

## 2. Business Logic vs. Route Handlers

This is the most critical convention for the Python backend. **Route handlers must be dumb.**

*   **Bad Pattern (The "Fat Route"):** Doing database queries, calculating RSI, validating external API shapes, and handling HTTP errors all inside the `@app.get` function in `/api/routes/`.
*   **Good Pattern (The "Service Layer"):**
    1.  **Route (`/api/routes`):** Exists *only* to take the HTTP request, validate the payload via Pydantic (Schema), pass it to a Service function, and return the output via an HTTP response.
    2.  **Service (`/services`):** The heavy lifting lives here. This is where we query TimescaleDB, calculate the indicator arrays, ping the AI, and apply business rules.
    3.  **Why:** If we ever want to run a calculation from a Celery background worker, or from a CLI script, we can simply import the Service function. If logic lives in the HTTP route, background workers cannot use it.

## 3. Naming Conventions

*   **Python (Backend):** 
    *   Variables/Functions: `snake_case` (e.g. `calculate_rsi()`)
    *   Classes/Models: `PascalCase` (e.g. `AssetCandle`)
    *   Files/Modules: `snake_case.py` (e.g. `market_data.py`)
*   **TypeScript/React (Frontend):**
    *   Variables/Functions: `camelCase` (e.g. `fetchPortfolio()`)
    *   React Components: `PascalCase` (e.g. `PriceChart.tsx`)
    *   Files (Non-Component): `camelCase.ts` or `kebab-case.ts` (e.g. `api-client.ts`)
*   **Database (TimescaleDB):**
    *   Tables & Columns: `snake_case` (e.g. `user_portfolios`, `asset_symbol`)

## 4. Error Handling Pattern

*   **Backend (Python):** 
    *   Do not return generic `500 Internal Server Error` to the frontend without logging. 
    *   Services should raise specialized Python Exceptions (e.g., `DataNotReadyException`, `AssetNotFoundException`).
    *   The FastAPI layer will use a global `Exception Handler` to catch these custom exceptions and map them to standard HTTP codes (400, 404, 429) alongside a standardized JSON error shape:
      ```json
      {
        "error": "AssetNotFound",
        "message": "The ticker AAPL is not supported in the free tier.",
        "status_code": 404
      }
      ```
*   **Frontend (Next.js):**
    *   API wrappers must catch these JSON errors and throw them locally.
    *   React components must use Error Boundaries or `try/catch` blocks inside `useEffect` (or React Query) to display user-friendly Toast notifications, rather than crashing the UI.

## 5. Database Migrations

*   **Tool:** We use **Alembic** for Python/SQLAlchemy.
*   **Pattern:** We NEVER manually edit table schemas in the database. 
*   **Workflow:**
    1.  Modify the SQLAlchemy model class in `/backend/app/models/`.
    2.  Run `alembic revision --autogenerate -m "added_portfolio_table"`.
    3.  Review the generated SQL inside `/backend/alembic/versions/` (Ensure it handles TimescaleDB hypertables correctly, as `--autogenerate` sometimes misses time-series specific indexing).
    4.  Run `alembic upgrade head`.

## 6. Environment Variable Naming

All variables must use upper `SNAKE_CASE` and be prefixed predictably based on where they belong to prevent secure keys from leaking to the browser.

*   **Backend/Secret Configs:**
    *   `DATABASE_URL="postgresql://user:pass...`
    *   `REDIS_URL="redis://localhost:6379"`
    *   `ANTHROPIC_API_KEY="sk-ant..."`
    *   `POLYGON_API_KEY="poly..."`
*   **Frontend Configs:**
    *   Next.js variables exposed to the browser MUST start with `NEXT_PUBLIC_`.
    *   `NEXT_PUBLIC_SUPABASE_URL="https://xxx.supabase.co"`
    *   `NEXT_PUBLIC_SUPABASE_ANON_KEY="..."`
    *   `NEXT_PUBLIC_API_BASE_URL="http://localhost:8000/api/v1"`

---

## 7. Feature Acceptance Criteria ("Definition of Done")

For every feature we build, the following 6 pillars MUST be verified before the feature is marked complete:

1.  **Security:** Input validation (via Pydantic/Zod), parameterized queries (native to SQLAlchemy), no secrets hardcoded, auth checks on every protected route, and rate limiting considered for public endpoints.
2.  **Observability:** Errors must be logged with context (e.g., `logger.error(f"Failed to fetch asset {ticker}: {e}")`) and never swallowed silently with empty `except:` blocks.
3.  **Reversibility:** Every database schema change must have a corresponding, testable Alembic migration. No manual or non-destructive operations are permitted outside of migrations.
4.  **Config:** All environment-specific values must reside in `.env` (or Railway variables) and never be hardcoded into the source logic.
5.  **Testing:** Every core service/utility must have, at bare minimum, one test for the happy path (expected success) and one test for standard failure cases.
6.  **Docs:** Any non-obvious engineering or business logic decision must have a clear inline comment explaining *why* it was done that way (e.g., `# Using iterrows here because Pandas vectorization fails on calculating the custom proprietary VWAP...`).
