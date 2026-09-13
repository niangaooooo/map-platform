"""FastAPI 应用入口。"""
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, features, folders, io, projects, ws
from app.core.config import get_settings
from app.core.static_host import mount_frontend
from app.db.redis import close_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("应用启动")
    yield
    await close_redis()
    logger.info("应用关闭")


settings = get_settings()
app = FastAPI(
    title="多用户协作地图标绘系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(folders.router, prefix=API_PREFIX)
app.include_router(features.router, prefix=API_PREFIX)
app.include_router(io.router, prefix=API_PREFIX)
app.include_router(ws.router)

# 单端口部署：若配置了 SERVE_STATIC_DIR（frontend/dist），则由后端托管前端页面。
# 必须在 API 路由注册之后挂载，避免 /{full_path} 捕获 /api 请求。
mount_frontend(app)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "app": "map-platform"}


# 校验错误（422）汉化：把 Pydantic 错误转成用户友好的中文
_VALIDATION_MSG_MAP = {
    "String should have at least": "长度不足",
    "String should have at most": "超出最大长度",
    "value is not a valid email address": "邮箱格式不正确",
    "Input should be a valid string": "必须是字符串",
    "Required": "不能为空",
}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for e in exc.errors():
        field = (e.get("loc") or ["body"])[-1]
        raw_msg = e.get("msg", "")
        msg = raw_msg
        for key, zh in _VALIDATION_MSG_MAP.items():
            if key in raw_msg:
                msg = zh
                break
        errors.append({"field": str(field), "msg": msg})
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})
