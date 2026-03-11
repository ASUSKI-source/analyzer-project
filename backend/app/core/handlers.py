import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.errors import AppException

logger = logging.getLogger(__name__)

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    Global exception handler for AppException.
    Matches the pattern required by CONVENTIONS.md.
    """
    logger.error(f"AppException: {exc.error_code} - {exc.message} on path {request.url.path}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "status_code": exc.status_code
        }
    )

async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Fallback exception handler for unhandled exceptions.
    Prevents 500s from leaking sensitive stack traces to the client and logs the error.
    """
    logger.error(f"Unhandled Exception on {request.url.path}: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred. Please try again later.",
            "status_code": 500
        }
    )
