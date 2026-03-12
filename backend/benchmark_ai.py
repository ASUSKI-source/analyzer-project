import asyncio
import time
import json
from app.services.ai_analyzer import _assemble_data_context
from app.core.database import AsyncSessionLocal
import logging

# Mute noisy logs
logging.getLogger("app.services").setLevel(logging.INFO)

async def benchmark():
    symbols = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "BTC", "ETH"]
    print(f"Starting benchmark for {len(symbols)} symbols...")
    
    async with AsyncSessionLocal() as db:
        start_time = time.time()
        try:
            context = await _assemble_data_context(symbols, db)
            duration = time.time() - start_time
            
            summary = {
                "status": "success",
                "duration_seconds": duration,
                "asset_count": len(context.get("assets", [])),
                "assets": []
            }
            
            for asset in context.get("assets", []):
                sym = asset["symbol"]
                has_fundamentals = bool(asset.get("fundamentals"))
                has_news = bool(asset.get("news_sentiment", {}).get("trending_topics"))
                summary["assets"].append({
                    "symbol": sym,
                    "price": asset.get("price"),
                    "has_fundamentals": has_fundamentals,
                    "has_news": has_news
                })
                
            with open("benchmark_results.json", "w") as f:
                json.dump(summary, f, indent=2)
            
            print(f"DONE. Duration: {duration:.2f}s. Results written to benchmark_results.json")
                
        except Exception as e:
            print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(benchmark())
