# 多用户协作地图标绘系统

基于 **Vue 3 + FastAPI + PostgreSQL (PostGIS) + Redis** 的多人协作地图标绘平台。
在高德地图上搜索定位、标点、画圆/线/多边形、测距测面积，按文件夹组织对象，
多人实时同步编辑，带权限管理、操作日志、历史版本、回收站与 CSV/GeoJSON 导入导出。

> 目标：做一个"任何普通工作人员打开浏览器就会用"的多人协作地图标绘平台。

---

## 功能总览

| 模块 | 说明 |
| --- | --- |
| 地图 | 高德 JS API 2.0（GCJ-02），搜索 / 定位 / 标点 / 画圆 / 画线 / 画多边形 / 测距 / 测面积 |
| 协作 | WebSocket 实时同步（创建/修改/删除秒级可见）、在线成员、编辑锁、活动提示 |
| 数据 | 文件夹（多级/拖拽/显隐）、分类与颜色、对象详情、附近点 / 圈内查询 |
| 管理 | 四级角色（owner/admin/editor/viewer）、成员管理、操作日志 |
| 版本 | Feature 历史版本、一键恢复（恢复本身产生新版本）、回收站（软删除可恢复） |
| 导入导出 | CSV / GeoJSON 导入（含 WGS84→GCJ-02 自动转换），GeoJSON / CSV 导出 |
| 部署 | Docker Compose + Nginx + HTTPS (Let's Encrypt) + 自动备份 |

## 技术栈

- **前端**：Vue 3 · TypeScript (strict) · Vite · Pinia · Vue Router · Element Plus · Axios · 高德 JS API 2.0
- **后端**：Python 3.12 · FastAPI · SQLAlchemy 2.x (async) · Alembic · Pydantic 2 · Argon2id · JWT (access + refresh)
- **存储**：PostgreSQL + PostGIS · Redis（Pub/Sub 广播、编辑锁、在线状态、限流）
- **架构**：模块化单体（非微服务），Redis Pub/Sub 保证多实例可平滑扩展

---

## 目录结构

```text
/opt/map-platform/
├── docker-compose.yml
├── .env.example          # 环境变量示例（复制为 .env）
├── nginx/                # Nginx 配置（HTTP->HTTPS、静态、API、WS）
├── scripts/backup.sh     # pg_dump 备份（7日/4周/6月）
├── backend/
│   ├── app/
│   │   ├── main.py       # FastAPI 入口
│   │   ├── api/          # 路由（auth/projects/folders/features/io/ws）
│   │   ├── models/       # SQLAlchemy 模型
│   │   ├── schemas/      # Pydantic 模型
│   │   ├── services/     # 业务逻辑（feature/权限/审计/导入导出/在线协作）
│   │   └── core/         # 配置/安全/坐标转换/日志
│   ├── alembic/          # 数据库迁移
│   ├── tests/            # Pytest（权限/409/WS）
│   └── Dockerfile
└── frontend/
    ├── src/
    │   ├── services/      # MapService 抽象（未来可换 MapLibre）
    │   ├── stores/        # Pinia（auth/project/folder/feature/ui/collaboration）
    │   ├── views/         # 登录/注册/项目列表/地图主界面
    │   └── components/    # 属性面板/绘制对话框/文件夹/导入导出
    └── Dockerfile
```

---

## 环境要求

- Docker + Docker Compose v2
- 服务器：2 核 2G 以上（生产建议 4 核 4G）
- 域名（可选，但 HTTPS 生产环境必需），如 `map.example.com`
- 高德开放平台账号：申请 **Web端(JS API)** Key 与 Security Js Code

---

## 配置高德 API

1. 前往 https://console.amap.com/ 创建应用，添加 **Web端(JS API)**，获得：
   - `Key`（形如 `f0a3...`）
   - `安全密钥 Security Js Code`（形如 `e5c8...`）
2. 填入项目 `.env`：

```env
AMAP_KEY=你的Key
AMAP_SECURITY_CODE=你的安全密钥
```

3. 前端构建时注入 Key，`index.html` 中保留 `<meta name="amap-key">` 占位，由 Vite 在构建期替换：
   - **Docker 部署**：把 `AMAP_KEY` / `AMAP_SECURITY_CODE` 写进项目根 `.env`，`docker compose` 会作为构建参数传给前端镜像。
   - **本地/非 Docker 构建**：复制 `frontend/.env.local.example` 为 `frontend/.env.local` 并填入
     `VITE_AMAP_KEY` / `VITE_AMAP_SECURITY_CODE`，然后 `npm run build`。

> `AMAP_KEY` / `AMAP_SECURITY_CODE` 属于敏感信息，请只写在 `.env` / `.env.local`（均已被 `.gitignore` 忽略），**不要提交到 Git**。
> 搜索接口默认走后端代理 `/api/v1/amap-proxy`（需要登录态），密钥不暴露给浏览器。

---

## 首次启动

### 1. 准备环境

```bash
cd /opt/map-platform
cp .env.example .env
# 编辑 .env：SECRET_KEY（openssl rand -hex 32）、POSTGRES_PASSWORD、AMAP_KEY、域名等
```

### 2. 构建并启动

```bash
docker compose up -d --build
```

> 前端镜像构建时会自动从根 `.env` 读取 `AMAP_KEY` / `AMAP_SECURITY_CODE` 注入到页面，
> 因此确保 `.env` 已填好这两个值再执行构建。

### 3. 初始化数据库

Compose 中 backend 启动即自动执行 `alembic upgrade head`；如手动初始化：

```bash
docker compose exec backend alembic upgrade head
```

### 4. 创建管理员

```bash
docker compose exec backend python -m app.cli create-admin
# 依次输入 username / email / password
```

### 5. 访问

- https://map.example.com （生产，域名需解析到本机）
- 本地开发：后端 `uvicorn app.main:app --reload --port 8000`，前端 `npm run dev`

> **默认不开放注册**（`ALLOW_REGISTER=false`），成员账号由管理员创建：
> 管理 → 项目 → 成员 → 添加成员（通过用户名/邮箱 + 角色）。

---

## 本地开发（无 Docker）

```bash
# 数据库
docker run -d --name map-pg -e POSTGRES_PASSWORD=map_password -p 5432:5432 postgis/postgis:16-3.4
docker run -d --name map-redis -p 6379:6379 redis:7-alpine

# 后端
cd backend
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
python -m app.cli create-admin
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev   # http://localhost:5173 （/api 与 /ws 已代理到 8000）
```

---

## 数据库迁移（Alembic）

所有表结构变更必须走迁移：

```bash
docker compose exec backend alembic revision --autogenerate -m "描述"
docker compose exec backend alembic upgrade head
```

> 不要手工修改生产数据库。

---

## 备份与恢复

备份由 `backup` 容器执行，策略：

- 每日备份保留 7 份（`backups/daily/`）
- 每周一额外复制为周备份，保留 4 份（`backups/weekly/`）
- 每月 1 日复制为月备份，保留 6 份（`backups/monthly/`）
- 全部 `.sql.gz` 压缩；备份目录 `./backups` 独立于 postgres 数据卷

手动执行一次备份：

```bash
docker compose exec backup sh /backups/backup.sh
```

恢复：

```bash
gunzip -c backups/daily/backup_xxxx.sql.gz | docker compose exec -T postgres psql -U map -d map_platform
```

> 备份目录与数据库 data 卷分离，建议把 `./backups` 挂到独立磁盘 / NAS。

---

## HTTPS（Let's Encrypt）

`nginx/conf.d/map.conf` 已配置 HTTPS 与 ACME HTTP-01 验证（`certbot` 容器每 12h 自动续期）。

首次申请证书：

```bash
# 确保域名 DNS 指向本机、80 端口可达后：
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d map.example.com \
  --email admin@example.com --agree-tos --no-eff-email
```

若要全自动，可先临时让 nginx 用 `/.well-known/acme-challenge/` 放行（配置已含），
再执行上述命令即可。证书路径应符合 `nginx/conf.d/map.conf` 中的 `live/map.example.com`。

---

## 日志

- 后端：结构化 JSON 日志（stdout，容器内 `/var/log/` 由 Docker 收集）
  - 字段：`request_id / level / msg / user_id / ip / endpoint / status / duration_ms`
  - **不会记录**：密码、token、安全密钥
- Nginx：`/var/log/nginx/access.log`

查看：

```bash
docker compose logs -f backend
docker compose logs -f nginx
```

---

## 更新版本

```bash
git pull
docker compose build
docker compose up -d
docker compose exec backend alembic upgrade head   # 如有迁移
```

---

## API 文档

启动后访问：

- Swagger UI：`https://YourHost/api/docs`
- ReDoc：`https://YourHost/api/redoc`

或查看本仓库 `docs/api.md`（REST + WebSocket 协议说明）。

---

## 权限矩阵

| 操作 | owner | admin | editor | viewer |
| --- | --- | --- | --- | --- |
| 浏览地图 / 搜索 / 测距 | ✅ | ✅ | ✅ | ✅ |
| 查看对象详情 | ✅ | ✅ | ✅ | ✅ |
| 创建/编辑/删除对象 | ✅ | ✅ | ✅ | ❌ 403 |
| 创建/移动文件夹 | ✅ | ✅ | ✅ | ❌ |
| 导入 | ✅ | ✅ | ✅ | ❌ |
| 导出 | ✅ | ✅ | ✅ | ✅ |
| 成员管理 | ✅ | ✅ | ❌ | ❌ |
| 项目设置 | ✅ | ✅ | ❌ | ❌ |
| 删除项目 | ✅ | ❌ | ❌ | ❌ |
| 恢复历史版本 / 回收站恢复 | ✅ | ✅ | ❌ | ❌ |
| 永久删除 | ✅ | ✅ | ❌ | ❌ |

> 权限在**服务端强制校验**（`app/services/permissions.py`），不依赖前端隐藏。

---

## 实时协作协议摘要

- WebSocket：`ws(s)://host/ws/projects/{project_id}?token=<access_token>`
- 加入即校验 JWT + 项目成员，通过后订阅 Redis 频道 `project:{id}` 广播
- 客户端心跳 `{"type":"ping"}` → 服务端 `{"type":"pong"}`（20s），更新在线状态
- 事件格式：`{"event":"feature.updated","project_id":"…","user_id":"…","data":{…}}`
- 事件：`feature.created/updated/deleted`、`folder.*`、`member.joined/left`、`feature.locked/unlocked`、`presence`

**并发控制**：Feature 带 `version` 乐观锁（不一致返回 `409`），配 Redis 编辑锁
（key `feature_lock:{feature_id}`，TTL 30s，编辑中自动续期，断线自动释放）。

---

## 测试

```bash
# 需要 PostgreSQL 与 Redis（见"本地开发"）
cd backend
pytest -ra
```

核心覆盖：注册/登录、viewer 写操作 403、乐观锁 409、WS 认证拒绝。

---

## FAQ

**为什么前端不用纯本地保存？**
所有写操作必须先经服务端持久化成功再广播，避免多端数据分叉（见"数据可靠性"章节）。

**坐标系为什么存两套？**
高德使用 GCJ-02；导入 GPS/WGS-84 数据时自动转换显示，同时保留原始坐标，避免未来 GIS 分析混淆。

**超过 1 万个对象怎么办？**
第一阶段按视野加载 + Marker 聚合已能覆盖 1 万内。更大规模可切换到矢量图层 + PostGIS 空间查询。

---

## License

内部使用，保留项目全部责任约束；部署请遵守高德开放平台使用条款。