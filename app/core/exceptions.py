class AppBaseException(Exception):
    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred"
    details: list | None = None

    def __init__(self, message: str | None = None, details: list | None = None):
        if message:
            self.message = message
        if details:
            self.details = details


class NotFoundException(AppBaseException):
    status_code = 404
    code = "not_found"


class UnauthorizedException(AppBaseException):
    status_code = 401
    code = "unauthorized"
    message = "Not authenticated"


class ForbiddenException(AppBaseException):
    status_code = 403
    code = "forbidden"
    message = "Insufficient permissions"


class BadRequestException(AppBaseException):
    status_code = 400
    code = "bad_request"


class ConflictException(AppBaseException):
    status_code = 409
    code = "conflict"


class ValidationException(AppBaseException):
    status_code = 422
    code = "validation_error"
