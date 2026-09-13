"""Feature 业务逻辑：创建、更新（乐观锁）、删除（软删除）、恢复、版本。"""
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Feature, FeatureVersion, Folder


def normalize_geometry(geometry: dict, feature_type: str) -> dict:
    """校验并按 GeoJSON 规范整理几何。"""
    if not isinstance(geometry, dict):
        raise HTTPException(status_code=422, detail="geometry 必须是对象")
    gt = geometry.get("type")
    if feature_type == "circle":
        center = geometry.get("center")
        radius = geometry.get("radius")
        if not (isinstance(center, (list, tuple)) and len(center) >= 2 and isinstance(radius, (int, float)) and radius > 0):
            raise HTTPException(status_code=422, detail="Circle 需要 {center:[lng,lat], radius:米}")
        return {"type": "Circle", "center": [float(center[0]), float(center[1])], "radius": float(radius)}
    expected = {
        "point": "Point",
        "polyline": "LineString",
        "polygon": "Polygon",
    }
    target = expected.get(feature_type)
    if target is None:
        raise HTTPException(status_code=422, detail=f"不支持的 feature_type: {feature_type}")
    if gt != target:
        raise HTTPException(status_code=422, detail=f"feature_type={feature_type} 需要 {target} 几何，收到 {gt}")
    if not geometry.get("coordinates"):
        raise HTTPException(status_code=422, detail="几何缺少 coordinates")
    return {"type": target, "coordinates": geometry["coordinates"]}


async def get_feature_or_404(db: AsyncSession, feature_id: str) -> Feature:
    feature = await db.get(Feature, feature_id)
    if feature is None:
        raise HTTPException(status_code=404, detail="对象不存在")
    return feature


async def get_live_feature(db: AsyncSession, feature_id: str) -> Feature:
    """获取未删除的 Feature，已删除返回 404。"""
    feature = await get_feature_or_404(db, feature_id)
    if feature.deleted_at is not None:
        raise HTTPException(status_code=404, detail="对象已删除")
    return feature


async def create_feature(
    db: AsyncSession,
    *,
    project_id: str,
    user_id: str,
    name: str,
    feature_type: str,
    geometry: dict,
    coordinate_system: str,
    folder_id: str | None,
    category_id: str | None,
    properties: dict,
    style: dict,
) -> Feature:
    geo = normalize_geometry(geometry, feature_type)
    if folder_id:
        folder = await db.get(Folder, folder_id)
        if folder is None or folder.project_id != project_id:
            raise HTTPException(status_code=422, detail="文件夹不属于该项目")
    feature = Feature(
        project_id=project_id,
        folder_id=folder_id,
        category_id=category_id,
        name=name,
        feature_type=feature_type,
        geometry_display=geo,
        coordinate_system_display="GCJ02",  # 高德创建/编辑均为 GCJ02
        geometry_original=geometry if coordinate_system == "WGS84" else None,
        coordinate_system_original=coordinate_system if coordinate_system == "WGS84" else None,
        properties=properties or {},
        style=style or {},
        version=1,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(feature)
    return feature


async def update_feature(
    db: AsyncSession,
    feature: Feature,
    *,
    user_id: str,
    version: int,
    name: str | None,
    geometry: dict | None,
    folder_id: str | None,
    category_id: str | None,
    properties: dict | None,
    style: dict | None,
) -> Feature:
    """乐观锁更新：version 不匹配返回 409。"""
    if feature.version != version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该对象刚刚被其他用户修改，请重新加载最新版本。",
        )
    # 保存当前状态到历史版本
    db.add(
        FeatureVersion(
            feature_id=feature.id,
            version=feature.version,
            geometry=feature.geometry_display,
            properties=feature.properties,
            style=feature.style,
            name=feature.name,
            created_by=feature.updated_by,
        )
    )
    if name is not None:
        feature.name = name
    if geometry is not None:
        feature.geometry_display = normalize_geometry(geometry, feature.feature_type)
        feature.coordinate_system_display = "GCJ02"
    if folder_id is not None:
        folder = await db.get(Folder, folder_id)
        if folder is None or folder.project_id != feature.project_id:
            raise HTTPException(status_code=422, detail="所选文件夹不属于该项目")
        feature.folder_id = folder_id
    if category_id is not None:
        feature.category_id = category_id
    if properties is not None:
        feature.properties = properties
    if style is not None:
        feature.style = style
    feature.updated_by = user_id
    feature.version += 1
    feature.updated_at = datetime.now(UTC)
    return feature


async def delete_feature(db: AsyncSession, feature: Feature, *, user_id: str) -> None:
    if feature.deleted_at is not None:
        return
    feature.deleted_at = datetime.now(UTC)
    feature.deleted_by = user_id
    feature.updated_by = user_id
    feature.version += 1


async def restore_feature(db: AsyncSession, feature: Feature, *, user_id: str) -> None:
    if feature.deleted_at is None:
        return
    feature.deleted_at = None
    feature.deleted_by = None
    feature.updated_by = user_id


async def total_count(db: AsyncSession, project_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(Feature).where(Feature.project_id == project_id, Feature.deleted_at.is_(None))
    )
    return int(result.scalar_one())
