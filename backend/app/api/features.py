"""Feature 路由：CRUD、乐观锁、版本历史、回收站、附近/圈内查询、编辑锁。"""

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, DbSession, ip_of
from app.core.geoutil import haversine_meters
from app.models import Feature, FeatureVersion, Folder
from app.schemas import (
    FeatureCreate,
    FeatureMove,
    FeatureOut,
    FeatureUpdate,
    FeatureVersionOut,
    MessageOut,
    NearbyOut,
    NearbyResult,
)
from app.services.audit import log_audit
from app.services.feature_service import (
    create_feature,
    delete_feature,
    get_feature_or_404,
    get_live_feature,
    restore_feature,
    update_feature,
)
from app.services.permissions import (
    PERMANENT_DELETE,
    RECOVER_DATA,
    WRITE_FEATURES,
    require_member,
    require_role,
)
from app.services.presence import hub

router = APIRouter(tags=["features"])


def _point_of(feature: Feature) -> tuple[float, float] | None:
    """取对象代表点（点坐标或圆心）。"""
    geo = feature.geometry_display or {}
    if feature.feature_type == "point":
        coords = geo.get("coordinates")
        if coords:
            return float(coords[0]), float(coords[1])
    elif feature.feature_type == "circle":
        center = geo.get("center")
        if center:
            return float(center[0]), float(center[1])
    return None


@router.get("/projects/{project_id}/features", response_model=list[FeatureOut])
async def list_features(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    folder_id: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
) -> list[Feature]:
    await require_member(db, project_id, user.id)
    stmt = select(Feature).where(Feature.project_id == project_id)
    if folder_id:
        stmt = stmt.where(Feature.folder_id == folder_id)
    if not include_deleted:
        stmt = stmt.where(Feature.deleted_at.is_(None))
    stmt = stmt.order_by(Feature.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/projects/{project_id}/features", response_model=FeatureOut, status_code=201)
async def create_feature_route(
    project_id: str, body: FeatureCreate, user: CurrentUser, db: DbSession, request: Request
) -> Feature:
    await require_role(db, project_id, user.id, WRITE_FEATURES)
    feature = await create_feature(
        db,
        project_id=project_id,
        user_id=user.id,
        name=body.name,
        feature_type=body.feature_type,
        geometry=body.geometry,
        coordinate_system=body.coordinate_system,
        folder_id=body.folder_id,
        category_id=body.category_id,
        properties=body.properties,
        style=body.style,
    )
    await log_audit(
        db,
        project_id=project_id,
        user_id=user.id,
        action="create",
        target_type="feature",
        target_id=feature.id,
        after={"name": feature.name, "type": feature.feature_type},
        ip=ip_of(request),
        user_agent=request.headers.get("user-agent", "")[:256],
    )
    await db.commit()
    await db.refresh(feature)
    await hub.broadcast(
        feature.project_id, "feature.created", {"feature": FeatureOut.model_validate(feature).model_dump(mode="json")}, user.id
    )
    return feature


@router.get("/features/{feature_id}", response_model=FeatureOut)
async def get_feature(feature_id: str, user: CurrentUser, db: DbSession) -> Feature:
    feature = await get_feature_or_404(db, feature_id)
    await require_member(db, feature.project_id, user.id)
    return feature


@router.patch("/features/{feature_id}", response_model=FeatureOut)
async def update_feature_route(
    feature_id: str, body: FeatureUpdate, user: CurrentUser, db: DbSession, request: Request
) -> Feature:
    feature = await get_live_feature(db, feature_id)
    await require_role(db, feature.project_id, user.id, WRITE_FEATURES)
    before = {"name": feature.name, "geometry": feature.geometry_display, "style": feature.style, "version": feature.version}
    feature = await update_feature(
        db,
        feature,
        user_id=user.id,
        version=body.version,
        name=body.name,
        geometry=body.geometry,
        folder_id=body.folder_id,
        category_id=body.category_id,
        properties=body.properties,
        style=body.style,
    )
    await log_audit(
        db,
        project_id=feature.project_id,
        user_id=user.id,
        action="update",
        target_type="feature",
        target_id=feature.id,
        before=before,
        after={"name": feature.name, "version": feature.version},
        ip=ip_of(request),
        user_agent=request.headers.get("user-agent", "")[:256],
    )
    await db.commit()
    await db.refresh(feature)
    await hub.broadcast(
        feature.project_id, "feature.updated", {"feature": FeatureOut.model_validate(feature).model_dump(mode="json")}, user.id
    )
    return feature


@router.post("/features/{feature_id}/move", response_model=FeatureOut)
async def move_feature(feature_id: str, body: FeatureMove, user: CurrentUser, db: DbSession) -> Feature:
    feature = await get_live_feature(db, feature_id)
    await require_role(db, feature.project_id, user.id, WRITE_FEATURES)
    if feature.version != body.version:
        raise HTTPException(status_code=409, detail="该对象刚刚被其他用户修改，请重新加载最新版本。")
    if body.folder_id:
        folder = await db.get(Folder, body.folder_id)
        if folder is None or folder.project_id != feature.project_id:
            raise HTTPException(status_code=422, detail="文件夹不属于该项目")
    feature.folder_id = body.folder_id
    feature.updated_by = user.id
    feature.version += 1
    await log_audit(db, project_id=feature.project_id, user_id=user.id, action="move", target_type="feature", target_id=feature.id)
    await db.commit()
    await db.refresh(feature)
    await hub.broadcast(
        feature.project_id, "feature.updated", {"feature": FeatureOut.model_validate(feature).model_dump(mode="json")}, user.id
    )
    return feature


@router.delete("/features/{feature_id}", response_model=MessageOut)
async def soft_delete_feature(feature_id: str, user: CurrentUser, db: DbSession, request: Request) -> MessageOut:
    feature = await get_live_feature(db, feature_id)
    await require_role(db, feature.project_id, user.id, WRITE_FEATURES)
    await delete_feature(db, feature, user_id=user.id)
    await log_audit(db, project_id=feature.project_id, user_id=user.id, action="delete", target_type="feature", target_id=feature.id)
    await db.commit()
    await hub.broadcast(feature.project_id, "feature.deleted", {"id": feature.id}, user.id)
    return MessageOut(msg="已移至回收站")


@router.post("/features/{feature_id}/restore", response_model=FeatureOut)
async def restore_feature_route(feature_id: str, user: CurrentUser, db: DbSession) -> Feature:
    feature = await get_feature_or_404(db, feature_id)
    if feature.deleted_at is None:
        raise HTTPException(status_code=400, detail="对象未删除")
    await require_role(db, feature.project_id, user.id, RECOVER_DATA)
    await restore_feature(db, feature, user_id=user.id)
    await log_audit(db, project_id=feature.project_id, user_id=user.id, action="restore", target_type="feature", target_id=feature.id)
    await db.commit()
    await db.refresh(feature)
    await hub.broadcast(
        feature.project_id, "feature.updated", {"feature": FeatureOut.model_validate(feature).model_dump(mode="json")}, user.id
    )
    return feature


@router.delete("/features/{feature_id}/permanent", response_model=MessageOut)
async def permanent_delete_feature(feature_id: str, user: CurrentUser, db: DbSession) -> MessageOut:
    feature = await get_feature_or_404(db, feature_id)
    await require_role(db, feature.project_id, user.id, PERMANENT_DELETE)
    # 先删版本历史，避免 FeatureVersion.feature_id 外键约束导致删除失败
    await db.execute(delete(FeatureVersion).where(FeatureVersion.feature_id == feature_id))
    await db.delete(feature)
    await log_audit(db, project_id=feature.project_id, user_id=user.id, action="delete.permanent", target_type="feature", target_id=feature.id)
    await db.commit()
    await hub.broadcast(feature.project_id, "feature.deleted", {"id": feature.id}, user.id)
    return MessageOut(msg="已永久删除")


# ---------- 版本历史 ----------
@router.get("/features/{feature_id}/versions", response_model=list[FeatureVersionOut])
async def list_versions(feature_id: str, user: CurrentUser, db: DbSession) -> list[FeatureVersion]:
    feature = await get_feature_or_404(db, feature_id)
    await require_member(db, feature.project_id, user.id)
    result = await db.execute(
        select(FeatureVersion).where(FeatureVersion.feature_id == feature_id).order_by(FeatureVersion.version.desc())
    )
    return list(result.scalars().all())


@router.post("/features/{feature_id}/versions/{version}/restore", response_model=FeatureOut)
async def restore_version(feature_id: str, version: int, user: CurrentUser, db: DbSession) -> Feature:
    feature = await get_live_feature(db, feature_id)
    await require_role(db, feature.project_id, user.id, RECOVER_DATA)
    result = await db.execute(
        select(FeatureVersion).where(FeatureVersion.feature_id == feature_id, FeatureVersion.version == version)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    db.add(
        FeatureVersion(
            feature_id=feature.id,
            version=feature.version,
            geometry=feature.geometry_display,
            properties=feature.properties,
            style=feature.style,
            name=feature.name,
            created_by=user.id,
        )
    )
    feature.geometry_display = snapshot.geometry
    feature.properties = snapshot.properties or {}
    feature.style = snapshot.style or {}
    feature.name = snapshot.name or feature.name
    feature.updated_by = user.id
    feature.version += 1
    await log_audit(db, project_id=feature.project_id, user_id=user.id, action="restore", target_type="feature", target_id=feature.id)
    await db.commit()
    await db.refresh(feature)
    await hub.broadcast(
        feature.project_id, "feature.updated", {"feature": FeatureOut.model_validate(feature).model_dump(mode="json")}, user.id
    )
    return feature


# ---------- 回收站 ----------
@router.get("/projects/{project_id}/trash", response_model=list[FeatureOut])
async def list_trash(project_id: str, user: CurrentUser, db: DbSession) -> list[Feature]:
    await require_role(db, project_id, user.id, RECOVER_DATA)
    result = await db.execute(select(Feature).where(Feature.project_id == project_id, Feature.deleted_at.is_not(None)))
    return list(result.scalars().all())


# ---------- 附近与圈内查询 ----------
@router.get("/projects/{project_id}/features/nearby", response_model=NearbyOut)
async def nearby_features(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    lng: float = Query(...),
    lat: float = Query(...),
    radius: float = Query(..., gt=0, le=50000),
) -> NearbyOut:
    await require_member(db, project_id, user.id)
    result = await db.execute(select(Feature).where(Feature.project_id == project_id, Feature.deleted_at.is_(None)))
    items: list[NearbyResult] = []
    for feature in result.scalars().all():
        pt = _point_of(feature)
        if not pt:
            continue
        dist = haversine_meters(lng, lat, pt[0], pt[1])
        if dist <= radius:
            items.append(
                NearbyResult(
                    feature_id=feature.id,
                    name=feature.name,
                    feature_type=feature.feature_type,
                    distance_m=round(dist, 1),
                    category_id=feature.category_id,
                )
            )
    items.sort(key=lambda r: r.distance_m)
    return NearbyOut(center=[lng, lat], radius=radius, items=items[:200])


# ---------- 编辑锁 ----------
@router.post("/features/{feature_id}/lock", response_model=MessageOut)
async def lock_feature(feature_id: str, user: CurrentUser, db: DbSession) -> MessageOut:
    feature = await get_live_feature(db, feature_id)
    await require_member(db, feature.project_id, user.id)
    ok = await hub.acquire_lock(feature.project_id, feature_id, user.id, user.username, user.display_name)
    if not ok:
        # 若锁由当前用户自己持有（如同步竞态中重复加锁），视为续期成功，正常放行
        lock = await hub.get_lock(feature.project_id, feature_id)
        if lock and lock.get("user_id") == user.id:
            await hub.renew_lock(feature.project_id, feature_id, user.id)
            await hub.broadcast(
                feature.project_id, "feature.locked", {"id": feature_id, "user_id": user.id, "username": user.username}, user.id
            )
            return MessageOut(msg="已锁定")
        holder = lock.get("username") if lock else "其他用户"
        raise HTTPException(status_code=423, detail=f"{holder} 正在编辑该对象")
    await hub.broadcast(
        feature.project_id, "feature.locked", {"id": feature_id, "user_id": user.id, "username": user.username}, user.id
    )
    return MessageOut(msg="已锁定")


@router.post("/features/{feature_id}/unlock", response_model=MessageOut)
async def unlock_feature(feature_id: str, user: CurrentUser, db: DbSession) -> MessageOut:
    feature = await get_feature_or_404(db, feature_id)
    await require_member(db, feature.project_id, user.id)
    await hub.unlock(feature.project_id, feature_id, user.id)
    await hub.broadcast(feature.project_id, "feature.unlocked", {"id": feature_id, "user_id": user.id}, user.id)
    return MessageOut(msg="已解锁")
