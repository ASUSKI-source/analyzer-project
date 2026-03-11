import httpx
from typing import Optional

_shared_client: Optional[httpx.AsyncClient] = None

def get_http_client() -> httpx.AsyncClient:
    """
    Get or create a global shared AsyncClient instance.
    This enables connection pooling and reduces handshake overhead.
    """
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            headers={"User-Agent": "MarketAnalyzer/1.0.0"}
        )
    return _shared_client

async def close_http_client():
    """Close the shared client instance."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None
