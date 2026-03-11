
import os
import sys
sys.path.append(os.getcwd())
from app.core.config import settings
print(f"FINNHUB_API_KEY: {settings.FINNHUB_API_KEY}")
print(f"POLYGON_API_KEY: {settings.POLYGON_API_KEY}")
