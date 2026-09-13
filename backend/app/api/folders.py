"""文件夹与分类路由。"""
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Category, Feature, Folder
from app.schemas import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    FolderCreate,
    FolderOut,
    FolderUpdate,
    MessageOut,
)
from app.services.audit import log_audit
from app.services.permissions import WRITE_FEATURES, require_member, require_role

router = APIRouter(tags=["folders"])


# ---------- 文件夹 ----------
@router.get("/projects/{project_id}/folders", response_model=list[FolderOut])
async def list_folders(project_id: str, user: CurrentUser, db: DbSession) -> list[Folder]:
    await require_member(db, project_id, user.id)
    result = await db.execute(
        select(Folder).where(Folder.project_id == project_id, Folder.deleted_at.is_(None)).order_by(Folder.sort_order, Folder.created_at)
    )
    return list(result.scalars().all())


@router.post("/projects/{project_id}/folders", response_model=FolderOut, status_code=201)
async def create_folder(project_id: str, body: FolderCreate, user: CurrentUser, db: DbSession) -> Folder:
    await require_role(db, project_id, user.id, WRITE_FEATURES)
    if body.parent_id:
        parent = await db.get(Folder, body.parent_id)
        if parent is None or parent.project_id != project_id:
            raise HTTPException(status_code=422, detail="父文件夹不属于该项目")
    folder = Folder(
        project_id=project_id,
        parent_id=body.parent_id,
        name=body.name,
        sort_order=body.sort_order,
        created_by=user.id,
    )
    db.add(folder)
    await log_audit(db, project_id=project_id, user_id=user.id, action="folder.create", target_type="folder", target_id=folder.id)
    await db.commit()
    await db.refresh(folder)
    return folder


@router.patch("/folders/{folder_id}", response_model=FolderOut)
async def update_folder(folder_id: str, body: FolderUpdate, user: CurrentUser, db: DbSession) -> Folder:
    folder = await db.get(Folder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    await require_role(db, folder.project_id, user.id, WRITE_FEATURES)
    if body.parent_id is not None:
        parent = await db.get(Folder, body.parent_id)
        if parent is None or parent.project_id != folder.project_id or parent.id == folder.id:
            raise HTTPException(status_code=422, detail="父文件夹无效")
        folder.parent_id = body.parent_id
    data = body.model_dump(exclude_unset=True, exclude={"parent_id"})
    for field, value in data.items():
        setattr(folder, field, value)
    await log_audit(db, project_id=folder.project_id, user_id=user.id, action="folder.update", target_type="folder", target_id=folder.id)
    await db.commit()
    await db.refresh(folder)
    return folder


@router.delete("/folders/{folder_id}", response_model=MessageOut)
async def delete_folder(folder_id: str, user: CurrentUser, db: DbSession) -> MessageOut:
    folder = await db.get(Folder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    await require_role(db, folder.project_id, user.id, WRITE_FEATURES)
    now = datetime.now(UTC)
    folder.deleted_at = now
    # 文件夹删除：其下对象保留，置为未分组
    await db.execute(Feature.__table__.update().where(Feature.folder_id == folder_id).values(folder_id=None))
    await log_audit(db, project_id=folder.project_id, user_id=user.id, action="folder.delete", target_type="folder", target_id=folder.id)
    await db.commit()
    return MessageOut(msg="文件夹已删除")


# ---------- 分类 ----------
@router.get("/projects/{project_id}/categories", response_model=list[CategoryOut])
async def list_categories(project_id: str, user: CurrentUser, db: DbSession) -> list[Category]:
    await require_member(db, project_id, user.id)
    result = await db.execute(
        select(Category).where(Category.project_id == project_id).order_by(Category.sort_order, Category.id)
    )
    return list(result.scalars().all())


@router.post("/projects/{project_id}/categories", response_model=CategoryOut, status_code=201)
async def create_category(project_id: str, body: CategoryCreate, user: CurrentUser, db: DbSession) -> Category:
    await require_role(db, project_id, user.id, WRITE_FEATURES)
    category = Category(project_id=project_id, **body.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def update_category(category_id: str, body: CategoryUpdate, user: CurrentUser, db: DbSession) -> Category:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    await require_role(db, category.project_id, user.id, WRITE_FEATURES)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(category, field, value)
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/categories/{category_id}", response_model=MessageOut)
async def delete_category(category_id: str, user: CurrentUser, db: DbSession) -> MessageOut:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    await require_role(db, category.project_id, user.id, WRITE_FEATURES)
    await db.execute(Feature.__table__.update().where(Feature.category_id == category_id).values(category_id=None))
    await db.delete(category)
    await db.commit()
    return MessageOut(msg="分类已删除")
