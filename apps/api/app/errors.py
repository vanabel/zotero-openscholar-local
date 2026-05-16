from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """统一 API 错误；由全局 handler 转为 JSON。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}


def error_body(code: str, message: str, detail: dict[str, Any] | None = None) -> dict:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "detail": detail or {},
        },
    }


def classify_exception(exc: BaseException) -> tuple[int, str, str, dict[str, Any]]:
    msg = str(exc) or exc.__class__.__name__
    low = msg.lower()
    if isinstance(exc, AppError):
        return exc.status_code, exc.code, exc.message, exc.detail
    if "mineru" in low or "min er u" in low:
        return 502, "mineru_error", msg, {}
    if "openscholar" in low or "retriever" in low or "reranker" in low:
        return 503, "openscholar_error", msg, {}
    if "ollama" in low or "embedding" in low or "openai" in low or "api key" in low:
        return 503, "llm_error", msg, {}
    if "document.md" in low or "markdown" in low and "无" in msg:
        return 404, "document_missing", msg, {}
    return 500, "internal_error", msg, {}


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.detail),
    )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("msg") or detail)
        extra = {k: v for k, v in detail.items() if k not in ("message", "msg")}
    else:
        message = str(detail)
        extra = {}
    code = "not_found" if exc.status_code == 404 else "bad_request"
    if exc.status_code >= 500:
        code = "internal_error"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message, extra or None),
    )


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", "请求参数无效", {"errors": exc.errors()}),
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    status, code, message, detail = classify_exception(exc)
    return JSONResponse(
        status_code=status,
        content=error_body(code, message, detail),
    )
