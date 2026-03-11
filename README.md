# Stocks & Crypto AI Analyzer

A sophisticated, real-time market analysis platform that combines traditional financial indicators with artificial intelligence to help investors make data-driven decisions.

## 1. PROJECT OVERVIEW

The **Stocks & Crypto AI Analyzer** is a web-based tool designed to provide a unified "command center" for tracking both traditional stock markets and the volatile world of cryptocurrency. It simplifies complex financial data into actionable insights by aggregating multiple data sources into a single, beautiful dashboard.

**Who it is for:**
- **New Investors:** Those who feel overwhelmed by professional trading terminals but want better data than simple price apps.
- **Data-Driven Traders:** Engineers and analysts who want to see technical indicators (like RSI or SMA) and AI-generated sentiment scores alongside real-time charts.
- **The Curious:** Anyone looking to understand how modern financial applications are built using a high-performance, asynchronous tech stack.

### High-Level System Diagram

```text
[   Frontend (Next.js)   ]  <-- React App with Live Charts
           |
           v
[     Backend (FastAPI)   ]  <-- High-Speed Python API
           |
     -----------------
     |               |
[  Redis Cache  ] [ TimescaleDB ]  <-- Blazing Fast Time-Series Data
     |               |
     -----------------
           |
     [ External APIs ]      <-- Polygon.io, Finnhub, CoinGecko, Binance
```

---

## 2. TECHNOLOGY STACK

We chose a high-performance "Decoupled Monolith" architecture, separating the visual interface from the data logic for maximum speed and scalability.

### Frontend Layer
- **Next.js (React Framework):** A framework used to build modern websites. It handles our "User Interface" (what you see on the screen). We chose it for its "Server-Side Rendering" capabilities, which make the app feel extremely fast.
- **Tailwind CSS:** A "Utility-First CSS" tool used to design the look and feel (colors, spacing, layout). It allows for rapid, consistent styling without writing thousands of lines of custom style code.
- **Lightweight Charts (by TradingView):** A specialized library for drawing financial price charts. It is perfect for this project because it is extremely fast and works well on mobile devices.
- **Lucide Icons:** A library of clean, consistent icons used for buttons and visual labels (like the refresh icon or the up/down arrows).

### Backend Layer
- **FastAPI (Python):** A modern, high-performance "Web Framework" for building the API (the brain of the app). It is "Asynchronous," meaning it can handle hundreds of users simultaneously without slowing down while it waits for external data.
- **Pydantic:** A library used to ensure data is "Valid." It checks that every piece of information moving through the system is in the correct format (e.g., ensuring a price is a number and not a word).
- **SQLAlchemy:** A "Database Toolkit" that lets our Python code talk to the database. It prevents many security risks (like SQL Injection) and makes the code more readable.
- **Celery:** A "Task Queue" used for background work. For example, when we need to download thousands of historical price points, Celery does this in the "background" so the user's dashboard doesn't freeze.

### Data Storage & Infrastructure
- **PostgreSQL with TimescaleDB:** Our primary database. **TimescaleDB** is a special extension designed specifically for "Time-Series" data (like stock prices that change every second). It is significantly faster than standard databases for this specific task.
- **Redis:** A "Key-Value Store" used for caching. We call our implementation the "Price Shield." It saves the latest prices for 10 seconds so that if 100 people look at the same stock, we only have to ask the external API for the price once.
- **Docker:** A "Containerization" platform. It packages the entire application into an "Image" so it runs exactly the same on your computer as it does on the production server.

---

## 3. ARCHITECTURE DEEP DIVE

### End-to-End Request Flow
1.  **User Action:** A user clicks on "BTC" in their watchlist.
2.  **Frontend Request:** The React app sends a request to the backend at `/market/assets/BTC/analysis`.
3.  **Backend Aggregation:** The FastAPI backend receives the request and starts four "Jobs" at the exact same time:
    -   Job A: Fetch current price from Binance.
    -   Job B: Fetch 365 days of history from TimescaleDB.
    -   Job C: Fetch fundamental data (like Market Cap) from Finnhub.
    -   Job D: Fetch the latest news and ask the AI for a sentiment score.
4.  **Concurrent Processing:** Because the backend is "Asynchronous," it waits for all four jobs to finish in parallel rather than one after another.
5.  **Response Construction:** The backend packages all this data into a single JSON object (a structured text format) and sends it back.
6.  **UI Update:** The frontend receives the data and instantly updates the Price Chart, the Sentiment Indicator, and the Stats cards.

### Database Schema (Plain English)
-   **User Table:** Stores login names and passwords (securely scrambled).
-   **Asset Table:** Stores static info about stocks/crypto (e.g., Symbol: AAPL, Name: Apple Inc).
-   **AssetCandle Table:** Our "Hypertable." It stores the "Candlesticks" (Open, High, Low, Close, Volume) for every asset over time. It is organized by "Time," which makes searching through years of data instantaneous.
-   **Watchlist Table:** A linking table that remembers which users are following which assets.

---

## 4. FEATURES

### Dynamic Dashboard Pulse
-   **User Experience:** You see a live "Ticker" at the top showing SPY, QQQ, BTC, and ETH. Every 10 seconds, the cards "shimmer," and numbers pulse blue when they change.
-   **Technical Detail:** The frontend uses the `useDashboardPulse` hook to poll the `/dashboard-pulse` endpoint. The backend uses the `AggregatorService` to hit external APIs in parallel. Results are cached in Redis to protect against API rate limits.

### Asset Watchlist
-   **User Experience:** Use the search bar to add any stock symbol. Your custom list is saved and shows live prices and AI sentiment "Bullish" or "Bearish" badges.
-   **Technical Detail:** Stores associations in the `user_watchlist_association` table. Price data is pulled from Polygon.io as a backup if the primary provider is unavailable.

### AI Sentiment Analysis
-   **User Experience:** A badge showing "Bullish" or "Bearish" based on recent news.
-   **Technical Detail:** Powered by **LangChain** and Anthropic's Claude. The system fetches the last 10 news headlines for a symbol, sends them to the AI, and asks for a normalized score between -1.0 (very negative) and 1.0 (very positive).

---

## 5. SECURITY

### Authentication (How we know who you are)
We use **JWT (JSON Web Tokens)**. When you log in, the server gives you a "Digital Passport" (the token). Your browser includes this passport in the "Header" of every request. This is "Stateless," meaning the server doesn't have to remember your session in a database, making it faster and more scalable.

### Authorization (What you are allowed to do)
We use **Dependencies** in FastAPI to check your passport before you can access certain data. For example, you can only delete items from *your* watchlist because the code checks if the `user_id` in the database matches the `id` in your Passport.

### Data Protection
-   **At Rest:** Passwords are never stored as plain text. We use **bcrypt**, a "scrambling" algorithm that is mathematically impossible to un-scramble.
-   **In Transit:** In production, all data is forced through **HTTPS (SSL/TLS)**, which encrypts the invisible "conversations" between your computer and our server.
-   **Input Validation:** We use **Pydantic Schemas**. If a hacker tries to send a "Command" as a stock symbol, the system will reject it because it doesn't match the required "String" pattern.

---

## 6. SETUP AND INSTALLATION

### Prerequisites
-   **Python 3.10+**: The programming language for the backend.
-   **Node.js 18+**: The engine that runs the frontend.
-   **PostgreSQL**: The database.
-   **Redis**: For caching.

### Local Setup Steps

1.  **Clone the Repository:**
    ```powershell
    git clone https://github.com/ASUSKI-source/analyzer-project.git
    cd analyzer-project
    ```

2.  **Backend Configuration:**
    ```powershell
    cd backend
    python -m venv venv
    .\venv\Scripts\Activate.ps1 # On Windows
    pip install -r requirements.txt
    ```
    Create a `.env` file in the `backend/` folder using the variables listed below.

3.  **Frontend Configuration:**
    ```powershell
    cd ../frontend
    npm install
    ```

### Required Environment Variables
| Variable Name | Description | Required | Example |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | Connection string for PostgreSQL | Yes | `postgresql://user:pass@localhost:5432/db` |
| `REDIS_URL` | Connection string for Redis | Optional | `redis://localhost:6379` |
| `SECRET_KEY` | Random string for securing Tokens | Yes | `any-long-random-string` |
| `POLYGON_API_KEY` | Key from [polygon.io](https://polygon.io/) | Yes | `AbC123XyZ...` |
| `FINNHUB_API_KEY` | Key from [finnhub.io](https://finnhub.io/) | Yes | `c8b123...` |
| `ANTHROPIC_API_KEY`| Key from [anthropic.com](https://anthropic.com/) | Yes | `sk-ant-api03-...` |

---

## 7. HOW TO RUN THE PROJECT

### Development Mode (Both at once)
We have provided a helper script to start the whole system with one command.
```powershell
./dev.ps1
```
-   **Backend** starts at [http://localhost:8000/docs](http://localhost:8000/docs) (Interactive API docs).
-   **Frontend** starts at [http://localhost:3000](http://localhost:3000).

### Common Startup Errors
-   **"Redis Connection Failed":** This is normal if you don't have Redis installed locally. The app will automatically fall back to an "In-Memory" cache (slower, but it works).
-   **"DATABASE_URL not found":** Ensure your `.env` file is in the `backend/` folder, not the project root.

---

## 8. DEPLOYMENT

This application is designed to be deployed on **Railway**.

### The Deployment Process
1.  **GitHub Connect:** Link your repository to a new Railway project.
2.  **Dual Services:** Create two separate "Services" in Railway:
    -   **Backend Service:** Point it to the `/backend` subdirectory. It uses the `Procfile` to know how to start.
    -   **Frontend Service:** Point it to the `/frontend` subdirectory.
3.  **Environment Variables:** Copy all your `.env` variables into the Railway Dashboard (Variables tab).

### Rollbacks
If a deployment fails, Railway allows you to "Rollback" to any previous version with a single click in their dashboard.

---

## 9. API REFERENCE

### Market Data Endpoints
-   **GET `/market/dashboard-pulse`**
    -   *Auth:* None
    -   *What:* Returns the top card data and AI sentiment.
-   **GET `/market/prices?symbols=AAPL,BTC`**
    -   *Auth:* None
    -   *What:* Returns current price/change for a list of symbols.
-   **GET `/market/assets/{symbol}/analysis`**
    -   *Auth:* Required (JWT)
    -   *What:* Deep-dive data including technical indicators.

---

## 10. KEY CONCEPTS AND PATTERNS

### The "Price Shield" (Caching)
**What it is:** A combination of a Global `CacheClient` and a 10-second TTL (Time to Live).
**Why:** Many financial APIs limit you to 60 calls per minute. The Price Shield ensures that if our frontend polls every 10 seconds, we never exceed that limit, even with many active users.
**Where to find it:** [backend/app/core/cache.py](backend/app/core/cache.py)

### The "Aggregator Pattern"
**What it is:** A service that gathers data from 3+ unrelated sources and merges them into one tidy object.
**Why:** It keeps the "API Routes" clean and simple. The route doesn't need to know *how* to talk to Binance or Polygon; it just asks the Aggregator for "The Pulse."
**Where to find it:** [backend/app/services/aggregator.py](backend/app/services/aggregator.py)

---

## 11. KNOWN LIMITATIONS AND FUTURE IMPROVEMENTS

-   **Seed Data:** Currently, historical charts for some assets use a "Random Walk" fallback if the database is empty. We would like to add a full historical sync for every asset on first add.
-   **Mobile UI:** The dashboard is responsive, but the TradingView charts can be difficult to navigate on small screens.
-   **Portfolio Tracking:** We have the database tables for portfolios, but the frontend UI for "Buying/Selling" simulation is not yet implemented.

---

## 12. GLOSSARY

-   **API (Application Programming Interface):** A set of rules that allows two pieces of software (like our frontend and backend) to talk to each other.
-   **Asynchronous (Async):** A programming style where the code can "wait" for something (like a slow API response) without stopping the whole program.
-   **Bullish/Bearish:** Financial terms. "Bullish" means prices are expected to go up; "Bearish" means they are expected to go down.
-   **Endpoint:** A specific URL path in the API (like `/prices`) that performs a specific task.
-   **Glassmorphism:** A design style (used in our dashboard) that uses transparency and blur to make elements look like frosted glass.
-   **JWT (JSON Web Token):** A secure way to transmit information between parties as a JSON object.
-   **SPA (Single Page Application):** A web application that updates the current page rather than loading whole new pages from a server.
-   **SQL Injection:** A common cyberattack where someone tries to "inject" malicious database commands into a search bar. Our system prevents this automatically.
-   **Time-Series Data:** Any data that is indexed by time (e.g., "The price of Gold at 9:00 AM, 9:01 AM...").
