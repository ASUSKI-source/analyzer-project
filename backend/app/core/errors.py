from typing import Optional

class AppException(Exception):
    """Base exception for all application-level errors."""
    def __init__(self, message: str, status_code: int = 400, error_code: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        super().__init__(self.message)

class AssetNotFoundException(AppException):
    def __init__(self, message: str = "The requested asset was not found."):
        super().__init__(message=message, status_code=404)

class DataNotReadyException(AppException):
    def __init__(self, message: str = "The data for this asset is not yet ready."):
        super().__init__(message=message, status_code=409)

class UnauthorizedException(AppException):
    def __init__(self, message: str = "Unauthorized access."):
        super().__init__(message=message, status_code=401)
