"""统一接口错误外层与机器码映射（契约 v1.0 通用传输约定第 2 节）。

错误响应 JSON 固定为::

    {"code": "<字符串机器码>", "message": "<中文安全摘要>", "details": {}}

- details 可选键：field（请求字段路径，数组下标用点号）、item_id、reason；
- 不得包含堆栈、SQL、服务器绝对路径、密钥或命令行细节（含 DEBUG 模式）；
- 成功响应仍由 ResponseModel(code/message/data) 构造，本模块不参与；
- 错误码表见 docs/contracts/README.md 第 2 节：
  400 VALIDATION_ERROR、401 UNAUTHENTICATED、403 FORBIDDEN、404 NOT_FOUND、
  409 CONFLICT、500 INTERNAL_ERROR、503 SERVICE_UNAVAILABLE；
  RequestValidationError 的 422 归并为 HTTP 400 + VALIDATION_ERROR。
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# HTTP 状态码 → 契约机器码（docs/contracts/README.md 第 2 节通用错误码表）
STATUS_TO_CODE = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    503: "SERVICE_UNAVAILABLE",
}

GENERIC_INTERNAL_MESSAGE = "服务器内部错误，请稍后重试"
VALIDATION_MESSAGE = "请求参数校验失败"
UNAUTHENTICATED_MESSAGE = "未认证或凭据无效"

# FastAPI HTTPBearer(auto_error=True) 在缺少 Authorization 头时抛出的
# 403 "Not authenticated" 与契约“未认证为 401”不符（HTTP 方案层面无凭据可协商），
# 在错误外层统一归并为 401 UNAUTHENTICATED；已认证但权限不足仍保持 403 FORBIDDEN。
_NOT_AUTHENTICATED_DETAIL = "Not authenticated"


def build_error_body(code: str, message: str, details: dict = None) -> dict:
    """构造契约错误外层 body；details 无内容时固定为空对象。"""
    return {"code": code, "message": message, "details": details or {}}


def _code_for_status(status_code: int) -> str:
    """按错误码表映射机器码；表外 5xx 归 INTERNAL_ERROR，其余 4xx 归 VALIDATION_ERROR。"""
    if status_code == 422:
        return "VALIDATION_ERROR"
    code = STATUS_TO_CODE.get(status_code)
    if code:
        return code
    if status_code >= 500:
        return "INTERNAL_ERROR"
    return "VALIDATION_ERROR"


def _field_path(loc: tuple) -> str:
    """把 pydantic 错误 loc 转成契约字段路径，去掉请求位置前缀，数组下标用点号。

    例：(body, custom_parameters, 12, count) -> custom_parameters.12.count
    """
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header", "cookie")]
    return ".".join(parts)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """fastapi/starlette HTTPException → 契约错误外层。"""
    status_code = exc.status_code
    detail = exc.detail if isinstance(exc.detail, str) else ""
    headers = getattr(exc, "headers", None)

    # 422 归并为 400 VALIDATION_ERROR（契约）
    if status_code == 422:
        status_code = 400

    if status_code == 403 and detail == _NOT_AUTHENTICATED_DETAIL:
        # HTTPBearer 无凭据抛 403：按契约归并为 401，不回显方案层细节
        status_code = 401
        body = build_error_body("UNAUTHENTICATED", UNAUTHENTICATED_MESSAGE)
    elif status_code == 401:
        # 保留业务层固定的中文安全摘要（如“无效的认证凭据”），同时保留 WWW-Authenticate 头
        body = build_error_body("UNAUTHENTICATED", detail or UNAUTHENTICATED_MESSAGE)
    elif status_code in STATUS_TO_CODE:
        # 契约表内状态码（含 503 SERVICE_UNAVAILABLE、400 VALIDATION_ERROR）
        body = build_error_body(STATUS_TO_CODE[status_code], detail or "请求处理失败")
    elif status_code >= 500:
        # 表外 5xx（如 500/501）一律返回通用摘要：detail 可能携带依赖/异常文本
        # （如缺依赖、转换异常），完整原因只进服务端日志，响应不回显（DEBUG 也不泄密）
        logger.error(
            "HTTP %s at %s %s: %s", status_code, request.method, request.url.path, detail
        )
        body = build_error_body("INTERNAL_ERROR", GENERIC_INTERNAL_MESSAGE)
    else:
        body = build_error_body(_code_for_status(status_code), detail or "请求处理失败")

    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """RequestValidationError（原 422）→ HTTP 400 VALIDATION_ERROR，details.field 反映字段路径。"""
    details = {}
    errors = exc.errors()
    if errors:
        # details 仅描述首个错误：field 为字段路径（数组下标用点号），
        # reason 用 pydantic 校验消息模板（不含输入值/内部数据）
        first = errors[0]
        field = _field_path(first.get("loc", ()))
        if field:
            details["field"] = field
        msg = first.get("msg")
        if isinstance(msg, str) and msg:
            details["reason"] = msg
    return JSONResponse(status_code=400, content=build_error_body("VALIDATION_ERROR", VALIDATION_MESSAGE, details))


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """未预期异常 → 500 INTERNAL_ERROR。

    完整堆栈只进服务端日志（logger）；响应固定通用摘要，
    绝不返回异常文本/堆栈/SQL/路径（DEBUG 也不泄密）。
    """
    logger.error(
        "未预期异常 at %s %s: %s", request.method, request.url.path, exc, exc_info=exc
    )
    return JSONResponse(
        status_code=500,
        content=build_error_body("INTERNAL_ERROR", GENERIC_INTERNAL_MESSAGE),
    )


def register_error_handlers(app: FastAPI) -> None:
    """在 FastAPI 应用上注册统一错误处理器（成功外层 ResponseModel 不受影响）。"""
    # fastapi.HTTPException 是 starlette HTTPException 的子类，注册父类同时覆盖两者
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
