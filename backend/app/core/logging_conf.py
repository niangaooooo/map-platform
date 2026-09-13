"""结构化 JSON 日志配置。

- 每条日志输出 request_id / user_id / ip / endpoint / status / duration
- 绝不记录 password / token / security code
"""
import json
import logging
import sys

from fastapi import Request

SENSITIVE_KEYS = {"password", "token", "access_token", "refresh_token", "security_code", "amap_security_code"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "user_id", "ip", "endpoint", "status", "duration_ms"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


def request_logger(request: Request, user_id: str | None = None, status: int = 0, duration_ms: float = 0) -> None:
    logger = logging.getLogger("app.request")
    logger.info(
        "request",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "user_id": user_id,
            "ip": request.client.host if request.client else None,
            "endpoint": f"{request.method} {request.url.path}",
            "status": status,
            "duration_ms": round(duration_ms, 1),
        },
    )
