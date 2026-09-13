"""文件导入 / 导出 / 审计日志 / 在线成员 / 高德代理 路由。"""
import io
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, ip_of
from app.core.config import get_settings
from app.models import AuditLog, Project, User
from app.schemas import AmapProxyRequest, AuditLogEntry, AuditLogPage, ImportResult
from app.services.audit import log_audit
from app.services.io_service import (
    build_project_backup,
    export_csv,
    export_geojson,
    export_project_backup,
    import_csv_file,
    import_geojson,
    restore_project_backup,
)
from app.services.permissions import EXPORT_ALLOWED, IMPORT_ALLOWED, require_member, require_role
from app.services.presence import hub

router = APIRouter(tags=["io"])


# ---------- 导入 ----------
@router.post("/projects/{project_id}/import", response_model=ImportResult)
async def import_file(
    project_id: str,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    crs: str = Form(default="GCJ02", pattern="^(GCJ02|WGS84)$"),
) -> ImportResult:
    await require_role(db, project_id, user.id, IMPORT_ALLOWED)
    filename = (file.filename or "").lower()
    raw = await file.read()
    if filename.endswith(".geojson") or filename.endswith(".json"):
        result = await import_geojson(db, project_id, user.id, raw, crs)
    elif filename.endswith(".csv"):
        result = await import_csv_file(db, project_id, user.id, raw, crs)
    else:
        raise HTTPException(status_code=422, detail="仅支持 CSV / GeoJSON 文件")
    await log_audit(
        db,
        project_id=project_id,
        user_id=user.id,
        action="import",
        target_type="project",
        target_id=project_id,
        after={"created": result.created, "skipped": result.skipped},
        ip=ip_of(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    await db.commit()
    return result


# ---------- 导出 ----------
def _content_disposition(filename: str) -> str:
    """中文文件名：ASCII fallback + RFC5987 filename*。"""
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "export"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


# ---------- 测试板块 → 正式板块 一键同步 ----------
# 安全模型：正式端校验 X-Sync-Key（与 SYNC_SHARED_SECRET 一致），
# 并把项目归到 X-Sync-User 指定的正式端账号下（两库用户需同名）。
async def _sync_user(db: DbSession, username: str | None):
    if not username:
        raise HTTPException(status_code=401, detail="缺少 X-Sync-User")
    from app.models import User

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail=f"正式端不存在同名账号：{username}，请先在正式端注册后再同步")
    return user


@router.post("/projects/import-project", response_model=dict)
async def import_project_from_sync(
    request: Request,
    db: DbSession,
    body: dict,
) -> dict:
    """正式端：接收测试板块推送的项目备份，还原为当前账号下的新项目。"""
    from app.core.config import get_settings

    settings = get_settings()
    key = request.headers.get("X-Sync-Key", "")
    if not settings.SYNC_SHARED_SECRET or key != settings.SYNC_SHARED_SECRET:
        raise HTTPException(status_code=403, detail="同步密钥无效")
    user = await _sync_user(db, request.headers.get("X-Sync-User"))
    if (body or {}).get("backup_type") != "map_project_backup":
        raise HTTPException(status_code=422, detail="不是有效的项目备份")
    result = await restore_project_backup(db, user.id, body)
    from app.services.audit import log_audit

    await log_audit(
        db,
        project_id=result["project_id"],
        user_id=user.id,
        action="import.sync",
        target_type="project",
        target_id=result["project_id"],
        after={"from_backup": body.get("project_name")},
    )
    await db.commit()
    return result


@router.post("/projects/{project_id}/sync-to-prod", response_model=dict)
async def sync_project_to_prod(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    request: Request,
) -> dict:
    """测试板块：把本项目备份并推送到正式板块（要求本端账号与正式端同名）。"""
    import httpx

    from app.core.config import get_settings

    settings = get_settings()
    if not settings.SYNC_PROD_URL or not settings.SYNC_SHARED_SECRET:
        raise HTTPException(status_code=503, detail="当前环境未配置正式板块同步地址")
    await require_role(db, project_id, user.id, EXPORT_ALLOWED)
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    blob = await build_project_backup(db, project_id, None, [], "original")
    url = f"{settings.SYNC_PROD_URL.rstrip('/')}/projects/import-project"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            url,
            json=blob,
            headers={
                "X-Sync-Key": settings.SYNC_SHARED_SECRET,
                "X-Sync-User": user.username,
            },
        )
    if resp.status_code >= 400:
        detail = resp.text[:300]
        raise HTTPException(status_code=502, detail=f"正式板块同步失败({resp.status_code})：{detail}")
    return resp.json()


@router.get("/projects/{project_id}/export")
async def export_project(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    scope: str = Query(default="project"),
    folder_id: str | None = Query(default=None),
    feature_ids: str = Query(default=""),
    crs: str = Query(default="original"),
    format: str = Query(default="geojson"),
) -> StreamingResponse:
    await require_role(db, project_id, user.id, EXPORT_ALLOWED)
    project = await db.get(Project, project_id)
    base = (project.name if project else "项目").replace("/", "_")
    ids = [x for x in feature_ids.split(",") if x]
    if format == "csv":
        content = await export_csv(db, project_id, folder_id, ids, crs)
        media = "text/csv; charset=utf-8"
        filename = f"{base}_数据_{now_str()}.csv"
    elif format == "backup":
        content = await export_project_backup(db, project_id, folder_id, ids, crs)
        media = "application/json; charset=utf-8"
        filename = f"{base}_完整备份_{now_str()}.json"
    else:
        content = await export_geojson(db, project_id, folder_id, ids, crs)
        media = "application/geo+json; charset=utf-8"
        filename = f"{base}_数据_{now_str()}.geojson"
    return StreamingResponse(
        io.StringIO(content),
        media_type=media,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


def now_str() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ---------- 审计日志 ----------
@router.get("/projects/{project_id}/audit", response_model=AuditLogPage)
async def audit_logs(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> AuditLogPage:
    await require_member(db, project_id, user.id)
    total = await db.execute(select(func.count()).select_from(AuditLog).where(AuditLog.project_id == project_id))
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.project_id == project_id)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.scalars().all()
    items = []
    for row in rows:
        u = await db.get(User, row.user_id) if row.user_id else None
        items.append(
            AuditLogEntry(
                id=row.id,
                action=row.action,
                target_type=row.target_type,
                target_id=row.target_id,
                before=row.before,
                after=row.after,
                created_at=row.created_at,
                username=u.username if u else None,
                user_display_name=u.display_name if u else None,
            )
        )
    return AuditLogPage(items=items, total=int(total.scalar_one()))


# ---------- 在线成员 ----------
@router.get("/projects/{project_id}/online")
async def online_members(project_id: str, user: CurrentUser) -> list[dict]:
    members = await hub.online_members(project_id)
    return members


# ---------- 高德安全代理 ----------
@router.post("/amap-proxy")
async def amap_proxy(req: AmapProxyRequest, user: CurrentUser):
    import httpx

    settings = get_settings()
    if not settings.AMAP_KEY:
        raise HTTPException(status_code=503, detail="服务器未配置高德 API Key")
    params = dict(req.params)
    params["key"] = settings.AMAP_KEY
    url = f"https://restapi.amap.com{req.path}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
    return JSONResponse(content=resp.json(), status_code=resp.status_code)
