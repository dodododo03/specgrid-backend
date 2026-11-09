"""Domain errors raised by services and turned into HTTP responses in main.py.

Services stay HTTP-agnostic; the response body is always {"code": ..., "message": ...}.
"""


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthorized"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "forbidden"


class InvalidImageError(AppError):
    status_code = 422
    code = "invalid_image"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class TooManyRequestsError(AppError):
    status_code = 429
    code = "too_many_requests"

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
