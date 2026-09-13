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

    # index.html 必须每次向服务器校验（no-cache + ETag）：
    # 否则浏览器启发式缓存旧页面，而构建产物的 JS 名带 hash —— 重建后旧 hash 文件已不存在，
    # 用户会拿到"引用已删除 JS 的旧 HTML"→ 整页白屏。带 hash 的 /assets 则长缓存（内容变则文件名变）。
    _INDEX_HEADERS = {"Cache-Control": "no-cache"}
    _ASSET_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}

    @app.middleware("http")
    async def spa_fallback(request, call_next):
        path = request.url.path
        # API / WebSocket → 走正常 FastAPI 路由
        if path.startswith(("/api/", "/ws/")) or path == "/api":
            return await call_next(request)
        # 已挂载的静态资源（带 hash）→ 长缓存
        if path.startswith("/assets/"):
            resp = await call_next(request)
            resp.headers.setdefault("Cache-Control", _ASSET_HEADERS["Cache-Control"])
            return resp
        # 命中真实文件则直出；否则回退 index.html（SPA）
        relative = path.lstrip("/")
        candidate = static_dir / relative if relative else index_file
        if relative and candidate.is_file():
            # 非 hash 命名的根级文件（favicon 等）：短缓存 + 校验
            return FileResponse(candidate, headers=_INDEX_HEADERS)
        return FileResponse(index_file, headers=_INDEX_HEADERS)

    return True