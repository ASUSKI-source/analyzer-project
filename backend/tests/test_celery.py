import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.tasks.market_tasks import _sync_all_assets_async, sync_all_assets_task

@pytest.mark.asyncio
async def test_sync_all_assets_happy_path():
    """
    TESTING REQUIREMENT: Positive test showing valid execution.
    """
    with patch("app.tasks.market_tasks.AsyncSessionLocal") as mock_session_maker:
        
        # Configure a fake active asset
        mock_asset = MagicMock()
        mock_asset.symbol = "NVDA"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_asset]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session_maker.return_value.__aenter__.return_value = mock_session
        
        with patch("app.tasks.market_tasks.sync_asset_history", new_callable=AsyncMock) as mock_sync:
            mock_sync.return_value = 5  # Simulated 5 candles returned
            
            results = await _sync_all_assets_async()
            
            # Ensure it actually successfully returned the parsed array
            assert results == ["NVDA: 5 candles"]
            mock_sync.assert_called_once_with(db=mock_session, symbol="NVDA", days=2)

@pytest.mark.asyncio
async def test_sync_all_assets_failure():
    """
    TESTING REQUIREMENT: Negative test proving observability logic.
    Ensures exceptions are logged appropriately and not silently swallowed!
    """
    with patch("app.tasks.market_tasks.AsyncSessionLocal") as mock_session_maker:
        
        mock_asset = MagicMock()
        mock_asset.symbol = "TSLA"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_asset]
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session_maker.return_value.__aenter__.return_value = mock_session
        
        with patch("app.tasks.market_tasks.sync_asset_history", new_callable=AsyncMock) as mock_sync:
            # Inject a fatal application error (e.g. timeout or database crash)
            mock_sync.side_effect = Exception("API Connection Timeout")
            
            with patch("app.tasks.market_tasks.logger.error") as mock_logger:
                results = await _sync_all_assets_async()
                
                # Should return an empty array indicating 0 successes
                assert results == []
                
                # OBSERVABILITY VALIDATION
                mock_logger.assert_called_once()
                args, kwargs = mock_logger.call_args
                assert "Failed to sync asset TSLA" in args[0]
                assert kwargs.get("exc_info") is True

def test_celery_task_wrapper_happy_path():
    """
    Tests the Synchronous Celery interface successfully bridges the Async void
    """
    with patch("app.tasks.market_tasks._sync_all_assets_async", new_callable=AsyncMock) as mock_async:
        mock_async.return_value = ["SUCCESSFULLY SYNCED"]
        result = sync_all_assets_task()
        
        assert result["status"] == "success"
        assert result["results"] == ["SUCCESSFULLY SYNCED"]
