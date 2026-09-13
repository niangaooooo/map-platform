"""测试板块地图后端入口（独立进程，端口 8081，仅服务 /map-test/ 前缀）。

与正式网关（gateway.py）的差异：
- 独立进程、独立测试库、独立前端产物 dist-test
- 只处理 /map-test/*（其余 404），不桥接 Flask 工作台
- pythonw 无控制台 → log_config 纯 FileHandler

配置：复制 backend/.env.test.example 为 backend/.env.test 并填写（该文件不入库）。
本机若无 .env.test，则使用下方默认值（最小可跑配置）。
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

# 测试环境配置：backend/.env.test（不入库）逐行写入 os.environ。
# 用 setdefault 是为了让"已在进程环境里的变量"优先，且 pydantic-settings 的
# 环境变量优先级高于 backend/.env —— 从而让测试实例与正式实例配置隔离。
_env_test = BACKEND_DIR / ".env.test"
if _env_test.exists():
    for _line in _env_test.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

# 默认值：不依赖 .env.test 也能启动（指向本机测试库与 dist-test）
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:5432/map_platform_test")
os.environ.setdefault("SERVE_STATIC_DIR", str(PROJECT_ROOT / "frontend" / "dist-test"))
os.environ.setdefault("REDIS_URL", "fakeredis://local")
os.environ.setdefault("ALLOW_REGISTER", "true")
os.environ.setdefault("SYNC_PROD_URL", "http://127.0.0.1:8080/map/api/v1")

sys.path.insert(0, str(BACKEND_DIR))

from app.main import app as map_app  # noqa: E402

PREFIX = "/map-test"
LOG_FILE = PROJECT_ROOT / "map-test-backend.log"


async def app(scope, receive, send):
    """剥离 /map-test 前缀后交给地图后端（HTTP 与 WebSocket 均适用）。"""
    path = scope.get("path") or ""
    if not (path == PREFIX or path.startswith(PREFIX + "/")):
        # 非 /map-test 前缀：404
        if scope.get("type") == "http":
            await send({
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            })
            await send({"type": "http.response.body", "body": b"not found"})
        else:
            await send({"type": "websocket.close", "code": 4404})
        return
    child = dict(scope)
    child["path"] = path[len(PREFIX):] or "/"
    child["raw_path"] = child["path"].encode("utf-8")
    child["root_path"] = ""
    await map_app(child, receive, send)


if __name__ == "__main__":
    import logging

    import uvicorn

    log_file = LOG_FILE
    _log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
        },
        "handlers": {
            "file": {
                "class": "logging.FileHandler",
                "filename": str(log_file),
                "encoding": "utf-8",
                "formatter": "default",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["file"], "level": "INFO"},
            "uvicorn.error": {"handlers": ["file"], "level": "INFO"},
            "uvicorn.access": {"handlers": ["file"], "level": "INFO"},
        },
        "root": {"handlers": ["file"], "level": "INFO"},
    }
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8081,
            log_level="info",
            access_log=False,
            log_config=_log_config,
        )
    except Exception:
        import traceback

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write("\n[FATAL] map-test 后端启动失败:\n")
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise
