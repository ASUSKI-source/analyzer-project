import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock everything needed BEFORE importing app.services.ai_analyzer
from unittest.mock import MagicMock
sys.modules["redis"] = MagicMock()
sys.modules["redis.asyncio"] = MagicMock()
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["sqlalchemy.ext.asyncio"] = MagicMock()
sys.modules["ta"] = MagicMock()
sys.modules["ta.momentum"] = MagicMock()
sys.modules["ta.trend"] = MagicMock()
sys.modules["ta.volatility"] = MagicMock()
sys.modules["pandas"] = MagicMock()

from app.services.ai_analyzer import generate_watchlist_report

async def test_cooldown_logic():
    print("Testing Cooldown Logic (Error Case)...")
    
    # Mock cache_client
    with patch("app.services.ai_analyzer.cache_client") as mock_cache:
        mock_cache.get.return_value = None # Cache miss
        mock_cache.get_ttl.return_value = 0 # No cooldown
        mock_cache.set = AsyncMock()
        
        # Mock _assemble_data_context
        with patch("app.services.ai_analyzer._assemble_data_context") as mock_assemble:
            mock_assemble.return_value = {"assets": []}
            
            # Mock _call_anthropic to return an error
            with patch("app.services.ai_analyzer._call_anthropic") as mock_ai:
                mock_ai.return_value = {"error": "Timeout occurred"}
                
                # Run the report generation
                result = await generate_watchlist_report(["AAPL"], "user123", None)
                
                # Verify that cooldown was NOT set
                # cooldown_key is ai_generation_cooldown:user123
                called_keys = [call.args[0] for call in mock_cache.set.call_args_list]
                cooldown_set = any("ai_generation_cooldown" in k for k in called_keys)
                
                print(f"Error returned: {result.get('error')}")
                print(f"Cooldown set after error? {cooldown_set} (Expected: False)")
                
                if not cooldown_set and result.get("error"):
                    print("\nSUCCESS: Cooldown logic verified (Error does not trigger block).")
                else:
                    print("\nFAILURE: Cooldown logic failed.")

async def test_cooldown_success():
    print("\nTesting Cooldown Logic (Success Case)...")
    
    with patch("app.services.ai_analyzer.cache_client") as mock_cache:
        mock_cache.get.return_value = None
        mock_cache.get_ttl.return_value = 0
        mock_cache.set = AsyncMock()
        
        with patch("app.services.ai_analyzer._assemble_data_context") as mock_assemble:
            mock_assemble.return_value = {"assets": []}
            with patch("app.services.ai_analyzer._call_anthropic") as mock_ai:
                mock_ai.return_value = {"market_summary": "Good"}
                
                await generate_watchlist_report(["AAPL"], "user123", None)
                
                called_keys = [call.args[0] for call in mock_cache.set.call_args_list]
                cooldown_set = any("ai_generation_cooldown" in k for k in called_keys)
                
                print(f"Cooldown set after success? {cooldown_set} (Expected: True)")
                if cooldown_set:
                    print("\nSUCCESS: Cooldown logic verified (Success triggers block).")

if __name__ == "__main__":
    asyncio.run(test_cooldown_logic())
    asyncio.run(test_cooldown_success())
