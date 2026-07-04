from typing import Any


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred"
    details: list[Any] | None = None

    def __init__(self, message: str | None = None, details: list[Any] | None = None):
        if message:
            self.message = message
        if details:
            self.details = details

    def __str__(self) -> str:
        return f"[{self.status_code}] {self.code}: {self.message}"


class NotFoundException(AppError):
    status_code = 404
    code = "not_found"


class UnauthorizedException(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Not authenticated"


class ForbiddenException(AppError):
    status_code = 403
    code = "forbidden"
    message = "Insufficient permissions"


class BadRequestException(AppError):
    status_code = 400
    code = "bad_request"


class ConflictException(AppError):
    status_code = 409
    code = "conflict"


class ValidationException(AppError):
    status_code = 422
    code = "validation_error"
