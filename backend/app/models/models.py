"""SQLAlchemy 2.x 声明式模型。

- 主键统一 UUID 字符串
- 时间列统一带时区
- 空间数据 JSONB；geometry_display 为显示坐标（GCJ02），geometry_original 保留原始导入坐标
- Feature 软删除（deleted_at），版本号乐观锁（version）
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))


def utc_now_col(**kw) -> Mapped[datetime]:
    kw.setdefault("nullable", False)
    return mapped_column(DateTime(timezone=True), server_default=func.now(), **kw)


def updated_col(**kw) -> Mapped[datetime]:
    kw.setdefault("nullable", False)
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), **kw)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: Mapped[str] = uuid_pk()
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = utc_now_col()
    updated_at: Mapped[datetime] = updated_col()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    owner_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    default_center: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    default_zoom: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    created_at: Mapped[datetime] = utc_now_col()
    updated_at: Mapped[datetime] = updated_col()


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_member_project_user"),)

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    created_at: Mapped[datetime] = utc_now_col()


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (Index("ix_folders_project_parent", "project_id", "parent_id"),)

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = utc_now_col()
    updated_at: Mapped[datetime] = updated_col()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False, server_default="#FF5A5F")
    icon: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (
        Index("ix_features_project_folder", "project_id", "folder_id"),
        Index("ix_features_deleted_at", "deleted_at"),
    )

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=False)
    folder_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("folders.id"), nullable=True)
    category_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("categories.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_type: Mapped[str] = mapped_column(String(16), nullable=False)  # point|circle|polyline|polygon
    geometry_display: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    coordinate_system_display: Mapped[str] = mapped_column(String(8), nullable=False, server_default="GCJ02")
    geometry_original: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    coordinate_system_original: Mapped[str | None] = mapped_column(String(8), nullable=True)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    style: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = utc_now_col()
    updated_at: Mapped[datetime] = updated_col()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)


class FeatureVersion(Base):
    __tablename__ = "feature_versions"

    id: Mapped[str] = uuid_pk()
    feature_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("features.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    style: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = utc_now_col()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_project_created", "project_id", "created_at"),)

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="")
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    user_agent: Mapped[str] = mapped_column(String(256), nullable=False, server_default="")
    created_at: Mapped[datetime] = utc_now_col()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = utc_now_col()
