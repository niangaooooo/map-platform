"""导入导出（CSV / GeoJSON）。

坐标系约定：
- 导入 WGS84 数据时转换为 GCJ02 存入 display，WGS84 原样存入 original；
- 导出 original 时按原始坐标系，导出 GCJ02/WGS84 时强制转换。
"""
import csv
import io
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.geoutil import transform_geometry
from app.models import Category, Feature, Folder, Project, ProjectMember
from app.schemas import ImportResult


async def _query_features(
    db: AsyncSession, project_id: str, folder_id: str | None, feature_ids: list[str]
) -> list[Feature]:
    stmt = select(Feature).where(Feature.project_id == project_id, Feature.deleted_at.is_(None))
    if folder_id:
        stmt = stmt.where(Feature.folder_id == folder_id)
    if feature_ids:
        stmt = stmt.where(Feature.id.in_(feature_ids))
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _feature_to_geojson_feature(feature: Feature, crs: str, folder_path: str = "") -> dict:
    if crs == "original":
        geo = feature.geometry_original or feature.geometry_display
        cs = feature.coordinate_system_original or feature.coordinate_system_display
    else:
        geo = feature.geometry_display
        cs = "GCJ02"
        if crs == "WGS84":
            geo = transform_geometry(geo, to_gcj=False)
            cs = "WGS84"
    props = dict(feature.properties or {})
    props.update(
        name=feature.name,
        feature_type=feature.feature_type,
        style=feature.style,
        coordinate_system=cs,
        # 保留原要素 ID 与归属，便于无损还原/去重
        map_feature_id=feature.id,
    )
    if feature.category_id:
        props["category_id"] = feature.category_id
    if folder_path:
        props["folder"] = folder_path
    return {"type": "Feature", "id": feature.id, "properties": props, "geometry": geo}


async def _folder_paths(db: AsyncSession, project_id: str) -> dict[str, str]:
    """folder_id → 用「/」拼接的完整路径（含层级），供导出还原分组。"""
    result = await db.execute(
        select(Folder).where(Folder.project_id == project_id, Folder.deleted_at.is_(None))
    )
    folders = list(result.scalars().all())
    by_id = {f.id: f for f in folders}
    paths: dict[str, str] = {}

    def resolve(fid: str | None) -> str:
        if not fid:
            return ""
        if fid in paths:
            return paths[fid]
        f = by_id.get(fid)
        if not f:
            return ""
        parent = resolve(f.parent_id)
        p = f"{parent}/{f.name}" if parent else f.name
        paths[fid] = p
        return p

    for f in folders:
        resolve(f.id)
    return paths


async def export_geojson(
    db: AsyncSession, project_id: str, folder_id: str | None, feature_ids: list[str], crs: str
) -> str:
    features = await _query_features(db, project_id, folder_id, feature_ids)
    fpaths = await _folder_paths(db, project_id)
    fc = [_feature_to_geojson_feature(f, crs, fpaths.get(f.folder_id or "", "")) for f in features]
    return json.dumps({"type": "FeatureCollection", "features": fc}, ensure_ascii=False, indent=2)


async def export_csv(
    db: AsyncSession, project_id: str, folder_id: str | None, feature_ids: list[str], crs: str
) -> str:
    features = await _query_features(db, project_id, folder_id, feature_ids)
    fpaths = await _folder_paths(db, project_id)
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["name", "feature_type", "longitude", "latitude", "radius", "address", "category", "folder", "coordinate_system", "remark"],
    )
    writer.writeheader()
    for feature in features:
        geo = feature.geometry_display or {}
        if crs == "WGS84":
            geo = transform_geometry(geo, to_gcj=False)
        lng, lat, radius = "", "", ""
        if feature.feature_type == "point":
            coords = geo.get("coordinates") or []
            if len(coords) >= 2:
                lng, lat = coords[0], coords[1]
        elif feature.feature_type == "circle":
            center = geo.get("center") or []
            if center:
                lng, lat = center[0], center[1]
            radius = geo.get("radius", "")
        props = feature.properties or {}
        writer.writerow(
            {
                "name": feature.name,
                "feature_type": feature.feature_type,
                "longitude": lng,
                "latitude": lat,
                "radius": radius,
                "address": props.get("address", ""),
                "category": props.get("category", ""),
                "folder": fpaths.get(feature.folder_id or "", ""),
                "coordinate_system": crs if crs != "original" else feature.coordinate_system_display,
                "remark": props.get("remark", ""),
            }
        )
    return buf.getvalue()


def _dt(o) -> str | None:
    return o.isoformat() if hasattr(o, "isoformat") else o


async def export_project_backup(
    db: AsyncSession, project_id: str, folder_id: str | None, feature_ids: list[str], crs: str
) -> str:
    """完整项目备份（单一 JSON）：项目信息 + 文件夹树 + 分类 + 要素全字段。

    与 GeoJSON 不同：它保留文件夹层级、分类、坐标双体系与所有 properties，
    可在将来（或手工）完整还原整个项目结构。
    """
    blob = await build_project_backup(db, project_id, folder_id, feature_ids, crs)
    return json.dumps(blob, ensure_ascii=False, indent=2, default=_dt)


async def build_project_backup(
    db: AsyncSession, project_id: str, folder_id: str | None, feature_ids: list[str], crs: str
) -> dict:
    """构造完整项目备份 dict（供导出下载 / 一键同步复用）。"""
    project = await db.get(Project, project_id)
    folders = (
        await db.execute(
            select(Folder)
            .where(Folder.project_id == project_id, Folder.deleted_at.is_(None))
            .order_by(Folder.sort_order)
        )
    ).scalars().all()
    categories = (
        await db.execute(select(Category).where(Category.project_id == project_id).order_by(Category.sort_order))
    ).scalars().all()
    features = await _query_features(db, project_id, folder_id, feature_ids)
    folder_names = {f.id: _folder_full_path(folders, f.id) for f in folders}
    cat_names = {c.id: c.name for c in categories}

    def fdict(f: Feature) -> dict:
        g = f.geometry_original or f.geometry_display if crs == "original" else f.geometry_display
        cs = f.coordinate_system_original or f.coordinate_system_display if crs == "original" else ("WGS84" if crs == "WGS84" else "GCJ02")
        if crs == "WGS84":
            g = transform_geometry(g, to_gcj=False)
        return {
            "map_feature_id": f.id,
            "folder_path": folder_names.get(f.folder_id or "", ""),
            "category_name": cat_names.get(f.category_id, "") if f.category_id else "",
            "name": f.name,
            "feature_type": f.feature_type,
            "geometry": g,
            "coordinate_system": cs,
            "properties": f.properties or {},
            "style": f.style or {},
        }

    blob = {
        "backup_type": "map_project_backup",
        "version": 1,
        "project_name": project.name if project else "",
        "exported_at": None,
        "folders": [
            {
                "id": f.id,
                "name": f.name,
                "parent_id": f.parent_id,
                "parent_path": _folder_full_path(folders, f.parent_id) if f.parent_id else "",
                "sort_order": f.sort_order,
                "visible": f.visible,
            }
            for f in folders
        ],
        "categories": [{"id": c.id, "name": c.name, "color": c.color, "icon": c.icon, "sort_order": c.sort_order} for c in categories],
        "features": [fdict(f) for f in features],
    }
    return blob


def _folder_full_path(folders: list[Folder], fid: str) -> str:
    by_id = {f.id: f for f in folders}

    def walk(f: Folder | None) -> str:
        if not f:
            return ""
        parent = by_id.get(f.parent_id) if f.parent_id else None
        p = walk(parent)
        return f"{p}/{f.name}" if p else f.name

    return walk(by_id.get(fid))


# ---------- 导入 ----------
async def _find_folder_by_name(db: AsyncSession, project_id: str, name: str) -> Folder | None:
    if not name:
        return None
    result = await db.execute(
        select(Folder).where(Folder.project_id == project_id, Folder.name == name, Folder.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


def _feature_type_of(geom_type: str) -> str | None:
    mapping = {"Point": "point", "LineString": "polyline", "Polygon": "polygon", "Circle": "circle"}
    return mapping.get(geom_type)


async def import_geojson(
    db: AsyncSession, project_id: str, user_id: str, raw: bytes, imported_crs: str
) -> ImportResult:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="无效的 JSON / GeoJSON 文件") from None
    features = data.get("features", []) if isinstance(data, dict) else data
    if not isinstance(features, list) or not features:
        raise HTTPException(status_code=422, detail="文件中没有 Feature")
    return await import_many_features(db, project_id, user_id, features, imported_crs)


async def import_many_features(
    db: AsyncSession, project_id: str, user_id: str, features: list[dict], imported_crs: str
) -> ImportResult:
    result = ImportResult()
    for item in features:
        try:
            geom = item.get("geometry") or {}
            feature_type = _feature_type_of(geom.get("type"))
            if feature_type is None:
                raise ValueError(f"不支持的几何类型: {geom.get('type')}")
            geometry = dict(geom)
            if imported_crs == "WGS84":
                geometry = transform_geometry(geometry, to_gcj=True)
            props = item.get("properties") or {}
            folder_id = None
            folder_name = props.get("folder", "")
            if folder_name:
                folder = await _find_folder_by_name(db, project_id, folder_name)
                folder_id = folder.id if folder else None
            await _create_imported_feature(
                db,
                project_id=project_id,
                user_id=user_id,
                name=props.get("name") or "未命名",
                feature_type=feature_type,
                geometry=geometry,
                folder_id=folder_id,
                category_id=(props.get("category_id") or None),
                properties={k: v for k, v in props.items() if k not in ("name", "folder")},
            )
            result.created += 1
        except Exception as exc:
            result.errors.append({"name": (item.get("properties") or {}).get("name", ""), "error": str(exc)})
            result.skipped += 1
    return result


async def import_csv_file(
    db: AsyncSession, project_id: str, user_id: str, raw: bytes, imported_crs: str
) -> ImportResult:
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    result = ImportResult()
    for row in reader:
        try:
            name = (row.get("name") or "").strip() or "未命名"
            lng = (row.get("longitude") or "").strip()
            lat = (row.get("latitude") or "").strip()
            if not lng or not lat:
                raise ValueError("缺少经纬度")
            lng, lat = float(lng), float(lat)
            geometry = {"type": "Point", "coordinates": [lng, lat]}
            if imported_crs == "WGS84":
                geometry = transform_geometry(geometry, to_gcj=True)
            folder_id = None
            folder_name = (row.get("folder") or "").strip()
            if folder_name:
                folder = await _find_folder_by_name(db, project_id, folder_name)
                folder_id = folder.id if folder else None
            props = {
                "address": row.get("address", ""),
                "category": row.get("category", ""),
                "remark": row.get("remark", ""),
            }
            await _create_imported_feature(
                db,
                project_id=project_id,
                user_id=user_id,
                name=name,
                feature_type="point",
                geometry=geometry,
                folder_id=folder_id,
                category_id=None,
                properties=props,
            )
            result.created += 1
        except Exception as exc:
            result.errors.append({"name": row.get("name", ""), "error": str(exc)})
            result.skipped += 1
    return result


async def _create_imported_feature(
    db: AsyncSession,
    *,
    project_id: str,
    user_id: str,
    name: str,
    feature_type: str,
    geometry: dict,
    folder_id: str | None,
    category_id: str | None,
    properties: dict,
) -> Feature:
    from app.services.feature_service import create_feature

    return await create_feature(
        db,
        project_id=project_id,
        user_id=user_id,
        name=name,
        feature_type=feature_type,
        geometry=geometry,
        coordinate_system="GCJ02",  # 已在导入时转换
        folder_id=folder_id,
        category_id=category_id,
        properties=properties,
        style={},
    )


async def restore_project_backup(
    db: AsyncSession, user_id: str, blob: dict
) -> dict:
    """把一个项目完整备份还原成【新项目】（用于测试板块一键同步到正式）。

    保留：项目名/说明、文件夹树（含层级）、分类、要素（含 properties/style/
    隐藏标记/坐标）。要素的 folder/category 通过名称路径还原；若重名已存在则
    新建同名副本，不覆盖正式端任何已有数据。
    返回 {"project_id":..., "name":...}。
    """
    from datetime import UTC, datetime

    from app.models import Category as _Cat, Folder as _Fld

    name = str((blob.get("project_name") or "未命名项目"))[:120]

    # 同名项目已存在 → 加时间后缀（不覆盖，便于区分同步结果）
    exists = await db.execute(select(Project.id).where(Project.name == name).limit(1))
    if exists.scalar_one_or_none() is not None:
        name = f"{name}（同步 {datetime.now(UTC).strftime('%m-%d %H:%M')}）"[:120]

    project = Project(name=name, description=blob.get("project_name") or "", owner_id=user_id)
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user_id, role="owner"))
    await db.flush()

    # 1) 文件夹：先建全量（扁平），再用 parent_path 建立层级
    folders = blob.get("folders") or []
    folder_name_to_new = {}  # 原完整路径 → 新 id
    new_folders: list[_Fld] = []
    for f in folders:
        nf = _Fld(
            project_id=project.id,
            parent_id=None,
            name=str(f.get("name") or "文件夹")[:128],
            sort_order=int(f.get("sort_order") or 0),
            visible=bool(f.get("visible", True)),
            created_by=user_id,
        )
        db.add(nf)
        new_folders.append(nf)
    await db.flush()
    # 第二遍建立父子关系（按原 parent_path 前缀匹配完整路径）
    for f, nf in zip(folders, new_folders):
        parent_path = f.get("parent_path") or ""
        name2 = str(f.get("name") or "")
        if parent_path:
            full = f"{parent_path}/{name2}"
        else:
            full = name2
        folder_name_to_new[full] = nf.id
    for f, nf in zip(folders, new_folders):
        parent_path = f.get("parent_path") or ""
        if parent_path and parent_path in folder_name_to_new:
            nf.parent_id = folder_name_to_new[parent_path]
    await db.flush()

    # 2) 分类
    categories = blob.get("categories") or []
    cat_name_to_new = {}
    for c in categories:
        nc = _Cat(
            project_id=project.id,
            name=str(c.get("name") or "分类")[:64],
            color=str(c.get("color") or "#FF5A5F")[:16],
            icon=str(c.get("icon") or "")[:64],
            sort_order=int(c.get("sort_order") or 0),
        )
        db.add(nc)
        await db.flush()
        cat_name_to_new[str(c.get("name") or "")] = nc.id

    # 3) 要素
    # 先全部创建（含旧 id→新 id 映射），最后统一修正圆绑定 parent_point_id——
    # 绑定字段里存的是备份源项目的旧要素 id，必须重映射到新 id，否则绑定断链。
    features = blob.get("features") or []
    errors = []
    created = 0
    old_to_new: dict[str, str] = {}
    new_circle_feats: list[tuple[Feature, dict]] = []  # (新 Feature, 原始 fe dict)

    for fe in features:
        try:
            geom = fe.get("geometry") or {}
            feature_type = _feature_type_of(geom.get("type"))
            if feature_type is None:
                raise ValueError(f"不支持的几何类型: {geom.get('type')}")
            folder_id = None
            fpath = fe.get("folder_path") or ""
            if fpath:
                # 兼容导出：路径在 folder_name_to_new；若不存在则忽略（放未分组）
                if fpath in folder_name_to_new:
                    folder_id = folder_name_to_new[fpath]
            category_id = None
            cname = fe.get("category_name") or ""
            if cname and cname in cat_name_to_new:
                category_id = cat_name_to_new[cname]
            created_feature = await _create_imported_feature(
                db,
                project_id=project.id,
                user_id=user_id,
                name=str(fe.get("name") or "未命名")[:128],
                feature_type=feature_type,
                geometry=dict(geom),
                folder_id=folder_id,
                category_id=category_id,
                properties=dict(fe.get("properties") or {}),
            )
            created_feature.style = fe.get("style") or {}
            await db.flush()
            # 记录旧源要素 id → 新要素 id（parent_point_id 等跨要素引用依赖它）
            old_id = fe.get("map_feature_id")
            if old_id:
                old_to_new[str(old_id)] = str(created_feature.id)
            created += 1
            if feature_type == "circle":
                new_circle_feats.append((created_feature, fe))
        except Exception as exc:  # noqa: BLE001
            errors.append({"name": fe.get("name", ""), "error": str(exc)})

    # 圆绑定父标点重映射：properties.parent_point_id 旧 id → 新 id
    for cf, fe in new_circle_feats:
        props = dict(cf.properties or {})
        old_parent = props.get("parent_point_id")
        if old_parent and str(old_parent) in old_to_new:
            props["parent_point_id"] = old_to_new[str(old_parent)]
            cf.properties = props

    await db.flush()
    return {"project_id": str(project.id), "name": project.name, "created": created, "errors": errors}
