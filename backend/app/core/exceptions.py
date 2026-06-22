class AppException(Exception):
    def __init__(self, message: str, code: str, status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class TenantNotFoundError(AppException):
    def __init__(self, phone_number_id: str):
        super().__init__(
            message=f"Tenant not found for phone_number_id: {phone_number_id}",
            code="TENANT_NOT_FOUND",
            status_code=404,
        )


class WebhookValidationError(AppException):
    def __init__(self, detail: str = "Invalid webhook signature"):
        super().__init__(
            message=detail,
            code="WEBHOOK_VALIDATION_ERROR",
            status_code=400,
        )


class AIServiceError(AppException):
    def __init__(self, detail: str = "AI service error"):
        super().__init__(
            message=detail,
            code="AI_SERVICE_ERROR",
            status_code=502,
        )


class SessionNotFoundError(AppException):
    def __init__(self, session_id: str):
        super().__init__(
            message=f"Session not found: {session_id}",
            code="SESSION_NOT_FOUND",
            status_code=404,
        )


class MediaProcessingError(AppException):
    def __init__(self, detail: str = "Media processing failed"):
        super().__init__(
            message=detail,
            code="MEDIA_PROCESSING_ERROR",
            status_code=400,
        )
