import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.handlers import app_exception_handler, general_exception_handler
from app.core.errors import AppException
from app.api.router import api_router
from app.core.config import settings

# Configure basic logging for the entire app to catch errors clearly
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Main FastAPI server instance
app = FastAPI(title="Stocks/Crypto AI Analyzer")

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

# Set up CORS for the Next.js frontend
# IMPORTANT: The CORS spec forbids allow_origins=["*"] with allow_credentials=True.
# Using allow_origin_regex to match all origins while still echoing back the specific
# requesting origin, which is required when credentials (cookies/auth headers) are involved.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register global exception handlers according to CONVENTIONS.md
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Register the main API router with the V1 prefix
app.include_router(api_router, prefix="/api/v1")

from app.core.cache import cache_client

@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up...")
    await cache_client.connect()

@app.on_event("shutdown")
async def shutdown_event():
    await cache_client.close()

@app.get("/")
def read_root():
    return {"message": "Welcome to the Stocks/Crypto AI Analyzer API. Visit /docs for the swagger UI."}
