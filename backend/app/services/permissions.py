"""权限校验：项目对全站用户公开，非成员按默认角色访问。

协作模式说明（2026-09-06 起）：
- 任何登录用户都能看到所有项目、进入任意项目并标注（无需被邀请）。
- 权限通过"项目成员表"判定：有记录则用记录角色；没有记录的，
  项目创建者按 owner，其他用户按 DEFAULT_PUBLIC_ROLE（editor，可标注）。
- 管理操作（删除项目、管理成员）仍要求真实角色为 owner/admin。
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, ProjectMember, User

ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2, "owner": 3}

# 全站公开时，非成员用户进入项目获得的默认角色
DEFAULT_PUBLIC_ROLE = "editor"

# 允许各角色执行的操作（服务端强制校验，不依赖前端）
MANAGE_MEMBERS = {"owner", "admin"}
MANAGE_PROJECT = {"owner", "admin"}
DELETE_PROJECT = {"owner"}
RECOVER_DATA = {"owner", "admin", "editor"}
IMPORT_ALLOWED = {"owner", "admin", "editor"}
EXPORT_ALLOWED = {"owner", "admin", "editor", "viewer"}
WRITE_FEATURES = {"owner", "admin", "editor"}
PERMANENT_DELETE = {"owner", "admin"}


async def get_membership(db: AsyncSession, project_id: str, user_id: str) -> ProjectMember | None:
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def require_member(db: AsyncSession, project_id: str, user_id: str) -> ProjectMember:
    """校验用户可访问项目，并返回其（真实或默认）成员身份。

    项目对所有登录用户公开：无成员记录时，返回一个非持久化的默认成员
    （owner 本人按 owner，其余按 DEFAULT_PUBLIC_ROLE）。项目不存在则 404。
    """
    member = await get_membership(db, project_id, user_id)
    if member is not None:
        return member
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    role = "owner" if project.owner_id == user_id else DEFAULT_PUBLIC_ROLE
    return ProjectMember(project_id=project_id, user_id=user_id, role=role)


async def require_role(db: AsyncSession, project_id: str, user_id: str, allowed: set[str]) -> ProjectMember:
    member = await require_member(db, project_id, user_id)
    if member.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色不允许该操作")
    return member


async def get_user(db: AsyncSession, user_id: str) -> User | None:
    return await db.get(User, user_id)
