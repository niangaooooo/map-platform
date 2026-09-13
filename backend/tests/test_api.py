"""端到端测试：认证、权限矩阵、乐观锁 409、WS 认证。

依赖外部 PostgreSQL + Redis 可用（docker compose up postgres redis 即可）。
无外部依赖时，DB 相关用例自动 skip；WS 认证与坐标转换用例始终运行。
"""
import os

os.environ.setdefault("APP_ENV", "test")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.geoutil import gcj02_to_wgs84, haversine_meters, wgs84_to_gcj02
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models import Project, ProjectMember, User

P = "/api/v1"

# DB 不可用时跳过端到端用例（本机无 PostgreSQL/Redis 时生效）
require_db = pytest.mark.skipif(
    not os.environ.get("TEST_DB_AVAILABLE", "0") == "1",
    reason="需要 PostgreSQL + Redis（docker compose up postgres redis 后设置 TEST_DB_AVAILABLE=1 运行）",
)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create_user(username: str, email: str) -> User:
    async with SessionLocal() as db:
        user = User(username=username, email=email, password_hash=hash_password("test-password-123"), display_name=username)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def _create_project(owner_id: str) -> Project:
    async with SessionLocal() as db:
        p = Project(name="测试项目", owner_id=owner_id)
        db.add(p)
        await db.flush()
        db.add(ProjectMember(project_id=p.id, user_id=owner_id, role="owner"))
        await db.commit()
        await db.refresh(p)
        return p


async def _login(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post(f"{P}/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
@require_db
async def test_login_success(client: AsyncClient) -> None:
    await _create_user("loginuser", "loginuser@test.com")
    token = await _login(client, "loginuser", "test-password-123")
    assert token


@pytest.mark.asyncio
@require_db
async def test_viewer_cannot_create_feature(client: AsyncClient) -> None:
    """Test 6: viewer 调用写接口返回 403"""
    owner = await _create_user("owner_a", "owner_a@test.com")
    project = await _create_project(owner.id)
    viewer = await _create_user("viewer_a", "viewer_a@test.com")
    async with SessionLocal() as db:
        db.add(ProjectMember(project_id=project.id, user_id=viewer.id, role="viewer"))
        await db.commit()
    token = await _login(client, "viewer_a", "test-password-123")
    resp = await client.post(
        f"{P}/projects/{project.id}/features",
        json={"name": "x", "feature_type": "point", "geometry": {"type": "Point", "coordinates": [113, 23]}},
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
@require_db
async def test_user_not_in_project_forbidden(client: AsyncClient) -> None:
    """Test 7: 不属于项目的用户访问 features 返回 403"""
    owner = await _create_user("owner_b", "owner_b@test.com")
    project = await _create_project(owner.id)
    await _create_user("outsider", "outsider@test.com")
    token = await _login(client, "outsider", "test-password-123")
    resp = await client.get(f"{P}/projects/{project.id}/features", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
@require_db
async def test_version_conflict_409(client: AsyncClient) -> None:
    """Test 8: 并发修改 version 冲突返回 409"""
    owner = await _create_user("owner_c", "owner_c@test.com")
    project = await _create_project(owner.id)
    token = await _login(client, "owner_c", "test-password-123")
    resp = await client.post(
        f"{P}/projects/{project.id}/features",
        json={"name": "病例001", "feature_type": "point", "geometry": {"type": "Point", "coordinates": [113.26, 23.18]}},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    fid = resp.json()["id"]
    v1 = resp.json()["version"]
    resp2 = await client.patch(f"{P}/features/{fid}", json={"version": v1, "name": "改一"}, headers=_auth(token))
    assert resp2.status_code == 200, resp2.text
    resp3 = await client.patch(f"{P}/features/{fid}", json={"version": v1, "name": "改二旧版本"}, headers=_auth(token))
    assert resp3.status_code == 409


@pytest.mark.asyncio
async def test_ws_auth_rejects_bad_token() -> None:
    """Test: WS 无效 token 被拒绝（4401）"""
    from app.api.ws import _authenticate

    assert await _authenticate("bad-token") is None
    assert await _authenticate("") is None


# ---------- 离线单元测试（不依赖 DB / Redis） ----------

def test_wgs84_to_gcj02_known_point() -> None:
    """北京天安门近似坐标：WGS84 → GCJ02 偏移应在数十米量级。"""
    # 天安门 WGS84 约 (116.3974, 39.9093)
    lng, lat = wgs84_to_gcj02(116.3974, 39.9093)
    # 转换后应仍在北京市区范围且与原始坐标偏差 < 0.01 度（约 1km）
    assert abs(lng - 116.3974) < 0.01
    assert abs(lat - 39.9093) < 0.01
    # 转换结果不应为 NaN
    assert lng == lng and lat == lat


def test_gcj02_wgs84_roundtrip() -> None:
    """GCJ02 → WGS84 → GCJ02 往返应基本还原（误差 < 1e-5 度）"""
    lng, lat = 113.26, 23.18  # 广州
    w_lng, w_lat = gcj02_to_wgs84(lng, lat)
    back_lng, back_lat = wgs84_to_gcj02(w_lng, w_lat)
    assert abs(back_lng - lng) < 1e-5
    assert abs(back_lat - lat) < 1e-5


def test_haversine_distance() -> None:
    """已知两点距离验证（广州 ↔ 深圳约 100km 量级）"""
    d = haversine_meters(113.26, 23.18, 114.06, 22.55)
    assert 90000 < d < 130000
