from fastapi import Request, status
from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional

class BriefAppException(Exception):
    """Base exception for the application."""
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class GCSOperationError(BriefAppException):
    """Exception raised for Google Cloud Storage errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=status.HTTP_502_BAD_GATEWAY, details=details)

class ValidationException(BriefAppException):
    """Exception raised for validation errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, details=details)

async def global_exception_handler(request: Request, exc: BriefAppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.message,
            "details": exc.details
        }
    )
