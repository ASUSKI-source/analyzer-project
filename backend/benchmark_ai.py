import asyncio
import json
import time
import uuid
from statistics import mean

from app.services.ai_analyzer import generate_watchlist_report
from app.core.database import AsyncSessionLocal
import logging

# Mute noisy logs
logging.getLogger("app.services").setLevel(logging.INFO)

def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((q / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


async def run_case(db, symbols: list[str], refresh: bool, runs: int) -> dict:
    durations = []
    sample_response = None
    errors = 0

    for i in range(runs):
        user_id = f"bench-{len(symbols)}-{refresh}-{i}-{uuid.uuid4().hex[:8]}"
        started = time.time()
        try:
            response = await generate_watchlist_report(
                symbols=symbols,
                user_id=user_id,
                db=db,
                refresh=refresh,
                request_id=f"bench-{uuid.uuid4().hex[:8]}",
            )
            sample_response = response
            durations.append(time.time() - started)
        except Exception:
            errors += 1

    return {
        "symbols": symbols,
        "symbol_count": len(symbols),
        "refresh": refresh,
        "runs": runs,
        "errors": errors,
        "p50_seconds": round(percentile(durations, 50), 3),
        "p95_seconds": round(percentile(durations, 95), 3),
        "mean_seconds": round(mean(durations), 3) if durations else 0.0,
        "sample_parse_error": sample_response.get("parse_error") if isinstance(sample_response, dict) else None,
        "sample_timeout": sample_response.get("_timeout") if isinstance(sample_response, dict) else None,
    }


async def benchmark():
    scenarios = [
        ["AAPL", "MSFT", "NVDA"],
        ["AAPL", "MSFT", "NVDA", "GOOGL", "AMD"],
        ["AAPL", "MSFT", "NVDA", "GOOGL", "AMD", "TSLA", "META", "AMZN", "NFLX", "BTC"],
    ]
    runs = 5

    print("Starting AI benchmark matrix (3/5/10 symbols, refresh false/true)")
    async with AsyncSessionLocal() as db:
        results = []
        for symbols in scenarios:
            results.append(await run_case(db, symbols, refresh=False, runs=runs))
            results.append(await run_case(db, symbols, refresh=True, runs=runs))

    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runs_per_case": runs,
        "results": results,
    }
    with open("benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print("DONE. Wrote benchmark_results.json")

if __name__ == "__main__":
    asyncio.run(benchmark())
