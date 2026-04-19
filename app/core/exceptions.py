from fastapi import HTTPException, status


class LLMUnavailableError(Exception):
    """Raised when the LLM backend is unreachable or returns an error."""


class ServiceError(Exception):
    """Raised for unrecoverable service-layer errors."""


def llm_unavailable_handler() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="LLM service is currently unavailable. Please try again later.",
    )
