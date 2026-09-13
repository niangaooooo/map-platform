"""前端静态托管（Windows 单端口部署模式）。

内网穿透 / 无 nginx 场景：由 FastAPI 直接托管前端构建产物 (frontend/dist)，
实现「一个 8000 端口 = 页面 + API + WebSocket」：

- GET /            -> dist/index.html
- GET /assets/*    -> 静态资源
- 其余非 /api /ws 前缀路径 -> 回退 index.html（SPA 路由）
- /api/*、/ws/*    -> 完全交给 FastAPI 路由

用「HTTP 中间件 + 仅托管静态文件」而非「通配路由」实现，避免通配路由
遮蔽 /api/health 等 API 端点（此前 Route 顺序问题的根因）。

用法：uvicorn 启动前设置环境变量 SERVE_STATIC_DIR=/path/to/dist。
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings


def mount_frontend(app: FastAPI, dist_dir: str | None = None) -> bool:
    settings = get_settings()
    dir_str = dist_dir or settings.SERVE_STATIC_DIR
    if not dir_str:
        return False
    static_dir = Path(dir_str)
    index_file = static_dir / "index.html"
    if not (static_dir.is_dir() and index_file.is_file()):
        return False

    # 静态资源目录（/assets 等）用 Mount 挂载，不影响 API 路由
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="site-assets")

    @app.middleware("http")
    async def spa_fallback(request, call_next):
        path = request.url.path
        # API / WebSocket / 已挂载的静态目录 → 走正常 FastAPI 路由/挂载
        if path.startswith(("/api/", "/ws/", "/assets/")) or path == "/api":
            return await call_next(request)
        # 命中真实文件则直出；否则回退 index.html（SPA）
        relative = path.lstrip("/")
        candidate = static_dir / relative if relative else index_file
        if relative and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)

    return True