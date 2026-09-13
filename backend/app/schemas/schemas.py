"""Pydantic Schemas。"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

RoleType = Literal["owner", "admin", "editor", "viewer"]
FeatureType = Literal["point", "circle", "polyline", "polygon"]
CoordinateSystem = Literal["GCJ02", "WGS84"]


# ---------- Auth ----------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=4, max_length=64, pattern=r"^[a-zA-Z0-9_\u4e00-\u9fa5]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=64)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    display_name: str
    is_active: bool
    created_at: datetime


# ---------- Projects ----------
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    default_center: list | None = None
    default_zoom: int | None = Field(default=None, ge=1, le=20)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    owner_id: str
    owner_name: str = ""  # 创建者显示名（列表接口填充，便于协作认领）
    default_center: list | None = None
    default_zoom: int
    created_at: datetime
    updated_at: datetime
    role: str = "viewer"  # 当前用户在该项目中的角色（列表接口填充）


class ProjectStats(BaseModel):
    feature_count: int = 0
    folder_count: int = 0
    member_count: int = 0
    last_updated: datetime | None = None


class ProjectDetail(ProjectOut):
    role: str = "viewer"
    stats: ProjectStats = ProjectStats()


# ---------- Members ----------
class MemberAdd(BaseModel):
    username: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = None
    role: RoleType = "viewer"


class MemberUpdate(BaseModel):
    role: RoleType


class MemberOut(BaseModel):
    user_id: str
    username: str
    display_name: str
    email: str
    role: str
    joined_at: datetime


# ---------- Folders ----------
class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    parent_id: str | None = None
    sort_order: int = 0


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: str | None = None
    sort_order: int | None = None
    visible: bool | None = None


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    parent_id: str | None = None
    name: str
    sort_order: int
    visible: bool
    created_at: datetime
    updated_at: datetime


# ---------- Categories ----------
class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str = Field(default="#FF5A5F", max_length=16)
    icon: str = Field(default="", max_length=64)
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=16)
    icon: str | None = Field(default=None, max_length=64)
    sort_order: int | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    color: str
    icon: str
    sort_order: int


# ---------- Features ----------
class FeatureCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    feature_type: FeatureType
    geometry: dict = Field(..., description="GeoJSON 几何；Circle 为 {center:[lng,lat], radius:米}")
    coordinate_system: CoordinateSystem = "GCJ02"
    folder_id: str | None = None
    category_id: str | None = None
    properties: dict = Field(default_factory=dict)
    style: dict = Field(default_factory=dict)


class FeatureUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    version: int = Field(..., ge=0, description="乐观锁：必须与服务器当前版本一致")
    geometry: dict | None = None
    folder_id: str | None = None
    category_id: str | None = None
    properties: dict | None = None
    style: dict | None = None


class FeatureMove(BaseModel):
    folder_id: str | None = None
    version: int = Field(..., ge=0)


class FeatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    folder_id: str | None = None
    category_id: str | None = None
    name: str
    feature_type: str
    geometry_display: dict | None = None
    coordinate_system_display: str
    geometry_original: dict | None = None
    coordinate_system_original: str | None = None
    properties: dict
    style: dict
    version: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class FeatureVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    feature_id: str
    version: int
    geometry: dict | None = None
    properties: dict | None = None
    style: dict | None = None
    name: str
    created_by: str
    created_at: datetime


class RestoreRequest(BaseModel):
    version: int = Field(..., ge=1)


# ---------- Nearby / Range query ----------
class NearbyResult(BaseModel):
    feature_id: str
    name: str
    feature_type: str
    distance_m: float
    category_id: str | None = None


class NearbyOut(BaseModel):
    center: list[float]
    radius: float
    items: list[NearbyResult]


# ---------- Audit ----------
class AuditLogEntry(BaseModel):
    id: str
    action: str
    target_type: str = ""
    target_id: str | None = None
    before: dict | None = None
    after: dict | None = None
    created_at: datetime
    username: str | None = None
    user_display_name: str | None = None


class AuditLogPage(BaseModel):
    items: list[AuditLogEntry]
    total: int


# ---------- Import / Export ----------
class ImportResult(BaseModel):
    created: int = 0
    skipped: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)


class ExportOptions(BaseModel):
    scope: Literal["project", "folder", "selection"] = "project"
    folder_id: str | None = None
    feature_ids: list[str] = Field(default_factory=list)
    crs: Literal["original", "GCJ02", "WGS84"] = "original"
    format: Literal["geojson", "csv"] = "geojson"


# ---------- Misc ----------
class MessageOut(BaseModel):
    ok: bool = True
    msg: str = "ok"


class AmapProxyRequest(BaseModel):
    path: str = Field(..., description="高德 API 子路径，如 /v3/place/text")
    params: dict[str, Any] = Field(default_factory=dict)
