# 系统架构说明

## 1. 总体架构

```text
                   ┌──────────────┐
                   │  Browser A   │  (Chrome / Edge / Safari)
                   └──────┬───────┘
                          │  HTTPS (WSS for WS)
                          ▼
              ┌───────────────────────┐
              │   Nginx               │  静态资源 / 反向代理 / TLS / 高德代理
              └──────────┬────────────┘
                         │ /api /ws
                         ▼
              ┌───────────────────────┐
              │   FastAPI (uvicorn)   │  REST API + WebSocket + 权限 + 审计
              └──┬───────────────┬────┘
                 │ SQLAlchemy    │ redis.asyncio
                 ▼               ▼
        ┌─────────────┐  ┌─────────────┐
        │ PostgreSQL  │  │    Redis    │  Pub/Sub 广播、编辑锁、在线状态、限流
        │ + PostGIS   │  └─────────────┘
        └─────────────┘
```

模块化单体部署：5 个容器（frontend / backend / postgres / redis / nginx），
外加 certbot（HTTPS 续期）与 backup（定时备份）。

## 2. 请求链路（REST）

```text
浏览器 → Nginx → FastAPI (路由 → 权限 → 业务服务 → SQLAlchemy → PostgreSQL)
                                     │
                                     ├→ 写 AuditLog
                                     └→ 成功 → Redis Publish → WebSocket → 在线用户
```

## 3. 实时协作（WebSocket）

- 客户端连接 `/ws/projects/{id}?token=`，服务端校验 JWT + 项目成员
- 每个项目一个 Redis 频道 `project:{id}`，多实例共享（可水平扩展）
- 事件统一格式：`{event, project_id, user_id, data}`
- 心跳 20s 维持在线状态；断线自动重连（指数退避，最长 15s）
- 编辑锁：Redis `SET NX EX 30`，编辑中客户端每 15s 续期，断线 TTL 自动释放

## 4. 数据一致性（乐观锁）

```text
更新请求 { version: 8 }
   └─ 数据库 version == 8 ?
        ├─ 是 → 保存旧值到 feature_versions → version=9 → 广播 feature.updated
        └─ 否 → 409 Conflict → 前端提示"已被他人修改，请重新加载"
```

## 5. 坐标系

```text
导入 WGS84 ──convert──▶ GCJ02 (geometry_display) + 保留 original
           ┌──────────────────────────────────────────────┐
           │ geometry_display: GCJ02  (前端/高德渲染)      │
           │ geometry_original: WGS84 (导入源数据,可还原)  │
           └──────────────────────────────────────────────┘
```

## 6. 可扩展性

- 多后端实例：Redis Pub/Sub 天然支持跨实例广播
- 超 1 万对象：前端按视野加载 + Marker 聚合；后续可切矢量图层 + PostGIS 查询
- 换地图引擎：前端 `MapService` 抽象层（`services/MapService.ts`）隔离 AMap，可平滑换 MapLibre

## 7. 安全

- JWT Access(60m) + Refresh(14d, 单次使用, 库内 hash) + Argon2id
- 每次对象操作服务端校验：成员资格 + 角色权限（四层角色表）
- 登录限流（IP+username，Redis 计数）
- 参数化 SQL（SQLAlchemy）；输出转义（Vue 默认）；CORS 白名单
- 高德 Key/安全码只存服务端 `.env`，搜索走 `/api/v1/amap-proxy`