"""项目与成员管理路由。"""
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import Category, Feature, FeatureVersion, Folder, Project, ProjectMember, User
from app.schemas import (
    MemberAdd,
    MemberOut,
    MessageOut,
    ProjectCreate,
    ProjectDetail,
    ProjectOut,
    ProjectStats,
    ProjectUpdate,
)
from app.services.audit import log_audit
from app.services.permissions import (
    DEFAULT_PUBLIC_ROLE,
    DELETE_PROJECT,
    MANAGE_MEMBERS,
    MANAGE_PROJECT,
    require_member,
    require_role,
)

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------- 项目 ----------
@router.get("", response_model=list[ProjectOut])
async def list_projects(user: CurrentUser, db: DbSession) -> list[ProjectOut]:
    """协作模式：返回全部项目（对所有登录用户公开），并计算当前用户的角色。

    有成员记录 → 用记录角色；无记录 → 项目创建者本人按 owner，其余按 editor。
    """
    # 当前用户在所有项目的真实成员角色
    mine = await db.execute(
        select(ProjectMember.project_id, ProjectMember.role).where(ProjectMember.user_id == user.id)
    )
    role_map = {pid: role for pid, role in mine.all()}

    result = await db.execute(
        select(Project, User.display_name, User.username)
        .join(User, User.id == Project.owner_id)
        .order_by(Project.updated_at.desc())
    )
    out = []
    for project, disp, uname in result.all():
        item = ProjectOut.model_validate(project)
        item.role = role_map.get(project.id) or ("owner" if project.owner_id == user.id else DEFAULT_PUBLIC_ROLE)
        item.owner_name = disp or uname
        out.append(item)
    return out


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, user: CurrentUser, db: DbSession) -> Project:
    project = Project(name=body.name, description=body.description, owner_id=user.id)
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    await log_audit(db, project_id=project.id, user_id=user.id, action="create", target_type="project", target_id=project.id)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: str, user: CurrentUser, db: DbSession) -> ProjectDetail:
    member = await require_member(db, project_id, user.id)
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    fcount = await db.execute(
        select(func.count()).select_from(Feature).where(Feature.project_id == project_id, Feature.deleted_at.is_(None))
    )
    ldcnt = await db.execute(
        select(func.count()).select_from(Folder).where(Folder.project_id == project_id, Folder.deleted_at.is_(None))
    )
    mcount = await db.execute(
        select(func.count()).select_from(ProjectMember).where(ProjectMember.project_id == project_id)
    )
    last = await db.execute(
        select(func.max(Feature.updated_at)).where(Feature.project_id == project_id, Feature.deleted_at.is_(None))
    )
    stats = ProjectStats(
        feature_count=int(fcount.scalar_one()),
        folder_count=int(ldcnt.scalar_one()),
        member_count=int(mcount.scalar_one()),
        last_updated=last.scalar_one(),
    )
    detail = ProjectDetail.model_validate(project)
    detail.role = member.role
    detail.stats = stats
    return detail


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str, body: ProjectUpdate, user: CurrentUser, db: DbSession, request: Request
) -> Project:
    await require_role(db, project_id, user.id, MANAGE_PROJECT)
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(project, field, value)
    await log_audit(db, project_id=project_id, user_id=user.id, action="update", target_type="project", target_id=project_id)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", response_model=MessageOut)
async def delete_project(project_id: str, user: CurrentUser, db: DbSession) -> MessageOut:
    """彻底删除项目（仅 owner）。

    早期实现只软删了 Feature/Folder，Project 行仍在库中，导致项目依旧出现在列表里
    （表现为"删了项目但项目还在，只是里面空了"）。这里改为真正删除：
    按外键依赖顺序清除子表数据，最后删除项目本体。
    审计日志保留（audit_logs.project_id 无外键约束），以便追溯"谁删了哪个项目"。
    """
    await require_role(db, project_id, user.id, DELETE_PROJECT)
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 1) 要素历史版本（依赖 features，必须最先删）
    await db.execute(
        FeatureVersion.__table__.delete().where(
            FeatureVersion.feature_id.in_(select(Feature.id).where(Feature.project_id == project_id))
        )
    )
    # 2) 要素（依赖 folders / categories，必须先于它们）
    await db.execute(Feature.__table__.delete().where(Feature.project_id == project_id))
    # 3) 文件夹：先解除自引用 parent_id，避免父子同批删除时触发外键冲突
    await db.execute(
        Folder.__table__.update().where(Folder.project_id == project_id).values(parent_id=None)
    )
    await db.execute(Folder.__table__.delete().where(Folder.project_id == project_id))
    # 4) 分类
    await db.execute(Category.__table__.delete().where(Category.project_id == project_id))
    # 5) 成员
    await db.execute(ProjectMember.__table__.delete().where(ProjectMember.project_id == project_id))
    # 6) 项目本体
    await db.delete(project)

    await log_audit(db, project_id=project_id, user_id=user.id, action="delete", target_type="project", target_id=project_id)
    await db.commit()
    return MessageOut(msg="项目已彻底删除")


# ---------- 成员 ----------
@router.get("/{project_id}/members", response_model=list[MemberOut])
async def list_members(project_id: str, user: CurrentUser, db: DbSession) -> list[MemberOut]:
    await require_member(db, project_id, user.id)
    result = await db.execute(
        select(ProjectMember, User.username, User.display_name, User.email)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
    )
    out = []
    for member, username, display_name, email in result.all():
        out.append(
            MemberOut(
                user_id=member.user_id,
                username=username,
                display_name=display_name,
                email=email,
                role=member.role,
                joined_at=member.created_at,
            )
        )
    return out


@router.post("/{project_id}/members", response_model=MemberOut, status_code=201)
async def add_member(
    project_id: str, body: MemberAdd, user: CurrentUser, db: DbSession, request: Request
) -> MemberOut:
    await require_role(db, project_id, user.id, MANAGE_MEMBERS)
    target = None
    if body.username:
        result = await db.execute(select(User).where(User.username == body.username))
        target = result.scalar_one_or_none()
    elif body.email:
        result = await db.execute(select(User).where(User.email == body.email))
        target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="未找到该用户")
    existing = await db.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == target.id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="该用户已是项目成员")
    db.add(ProjectMember(project_id=project_id, user_id=target.id, role=body.role))
    await log_audit(db, project_id=project_id, user_id=user.id, action="member.add", target_type="user", target_id=target.id)
    await db.commit()
    return MemberOut(
        user_id=target.id,
        username=target.username,
        display_name=target.display_name,
        email=target.email,
        role=body.role,
        joined_at=func.now(),
    )


@router.patch("/{project_id}/members/{member_user_id}", response_model=MemberOut)
async def update_member(
    project_id: str, member_user_id: str, body: MemberAdd, user: CurrentUser, db: DbSession
) -> MemberOut:
    await require_role(db, project_id, user.id, MANAGE_MEMBERS)
    result = await db.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == member_user_id)
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="成员不存在")
    member.role = body.role
    target = await db.get(User, member_user_id)
    await log_audit(db, project_id=project_id, user_id=user.id, action="member.update", target_type="user", target_id=member_user_id)
    await db.commit()
    return MemberOut(
        user_id=member.user_id,
        username=target.username if target else "",
        display_name=target.display_name if target else "",
        email=target.email if target else "",
        role=member.role,
        joined_at=member.created_at,
    )


@router.delete("/{project_id}/members/{member_user_id}", response_model=MessageOut)
async def remove_member(project_id: str, member_user_id: str, user: CurrentUser, db: DbSession) -> MessageOut:
    await require_role(db, project_id, user.id, MANAGE_MEMBERS)
    project = await db.get(Project, project_id)
    if project and project.owner_id == member_user_id:
        raise HTTPException(status_code=400, detail="不能移除项目所有者")
    result = await db.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == member_user_id)
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="成员不存在")
    await db.delete(member)
    await log_audit(db, project_id=project_id, user_id=user.id, action="member.remove", target_type="user", target_id=member_user_id)
    await db.commit()
    return MessageOut(msg="成员已移除")
