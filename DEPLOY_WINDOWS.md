# Windows 主机部署指南（Cloudflare 内网穿透，无 Docker）

适用场景：另一台 **Windows 电脑** 上用 `cloudflared` 内网穿透对外提供访问，不用 Docker / nginx。
本项目已内置「单端口模式」：**FastAPI 一个 8000 端口同时托管前端页面 + REST API + WebSocket**，
cloudflared 只需映射这一个端口即可。

> 无需 PostGIS！项目几何字段为 JSONB，普通 PostgreSQL 即可（15/16 均可）。

---

## 一、部署机需要准备的东西

| 组件 | 说明 |
|---|---|
| Python 3.12+ | 安装时勾选 "Add to PATH" |
| PostgreSQL 15/16 | 普通版即可（装装时记下密码，端口默认 5432） |
| Node.js 20+（只需首次构建前端，可选） | 如果直接用随包提供的 `frontend/dist` 则可跳过 |
| cloudflared.exe | https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ |

---

## 二、一次性安装（首次）

### 1. 解压放到目录

把压缩包解压到 `D:\map-platform`（任意无空格纯英文路径，避免中文/空格导致 Python 路径问题）。

### 2. 配置后端

在项目根目录创建 `backend\.env`（或复制 `..\.env.example` 到项目根）：

```ini
# backend/.env
APP_ENV=production
SECRET_KEY=<用 openssl rand -hex 32 生成，或任意长随机串>
ALLOW_REGISTER=false

# 本地 PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:你的数据库密码@127.0.0.1:5432/map_platform

# 无 Redis：使用内存版 fakeredis（单进程足够；多进程需真 Redis）
REDIS_URL=fakeredis://local

# 高德地图（后端搜索代理用）
AMAP_KEY=你的高德Web服务Key

# CORS：本机穿透域名留空或填本地
CORS_ORIGINS=http://localhost:8000
```

> `DATABASE_URL` 先建好库：pgAdmin 或 psql 执行 `CREATE DATABASE map_platform;`

### 3. 安装后端依赖 + 建表 + 建管理员

```bat
cd C:\map-platform\backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m app.cli create-admin --username admin --email a@b.c --password 你的密码
```

### 4. 准备前端（二选一）

- **A. 直接用自带的 `frontend\dist`**（压缩包已含高德 Key 注入的构建产物，无需 Node）：跳过本步。
- B. 如需重新构建：
  ```bat
  cd C:\map-platform\frontend
  npm ci
  set VITE_AMAP_KEY=你的高德JS_API_Key
  npm run build
  ```

### 5. 启动后端（单端口托管一切）

```bat
cd C:\map-platform\backend
set SERVE_STATIC_DIR=C:\map-platform\frontend\dist
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

- 打开 http://localhost:8000 应看到登录页
- `/api/health` 返回 `{"status":"ok"}`

> 生产建议：`--workers 1`（fakeredis 内存态多进程会各自独立导致协作状态不一致）；若要多进程需接真 Redis。

---

## 三、接入 Cloudflare 内网穿透

### 用 Quick Tunnel（免配置，最快验证）

```bat
cloudflared tunnel --url http://localhost:8000
```
会得到一个 `https://xxx-random.trycloudflare.com` 网址，直接访问即可。

> 注意：Quick Tunnel 地址随机，重启后变化，适合临时演示。

### 用命名隧道（稳定域名，推荐）

```bat
cloudflared tunnel login                 # 首次授权
cloudflared tunnel create map-platform  # 建隧道，得到 tunnel_id
cloudflared tunnel route dns map-platform 你的域名.map.example
```

写配置文件 `%USERPROFILE%\.cloudflared\config.yml`：

```yml
tunnel: map-platform
credentials-file: C:\Users\你\.cloudflared\<tunnel-id>.json

ingress:
  - hostname: 你的域名.example.com
    service: http://localhost:8000
  - service: http_status:404
```

启动：

```bat
cloudflared tunnel run map-platform
```

### 3. 高德域名白名单（必须！）

登录 https://console.amap.com/ → 应用管理 → 你的 Web端(JS API) 应用 → 配置：
**「域名白名单」添加你的穿透域名**（如 `https://你的域名.example.com` 或
`https://xxx.trycloudflare.com`），否则前端地图加载报 `INVALID_USER_KEY`。

---

## 四、开机自启（可选）

用 `nssm`（https://nssm.cc/）或计划任务把以下两条设为自启服务：

1. `cloudflared.exe tunnel run map-platform`
2. `uvicorn` 后端

或写一个 `start.bat`：

```bat
@echo off
cd /d C:\map-platform\backend
set SERVE_STATIC_DIR=C:\map-platform\frontend\dist
start "map-backend" .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
start "map-tunnel" C:\cloudflared\cloudflared.exe tunnel run map-platform
```

---

## 五、常见问题

| 现象 | 处理 |
|---|---|
| 地图空白 / 高德 INVALID_USER_KEY | 域名白名单未加，或加了没等生效（几分钟） |
| WebSocket 连不上（左下角"连接中…"） | 确认走的是 cloudflared http 服务（隧道自动支持 ws）；Quick Tunnel 亦支持 |
| 保存报「其他用户修改」409 | 正常并发保护，通常无需处理；重试即可 |
| 中文路径 | 部署目录用 `C:\map-platform` 这类纯英文路径 |

---

## 六、更新部署

```bat
:: 停掉旧后端进程（Ctrl+C 或 taskkill）
:: 覆盖解压新包（保留 .env）
cd C:\map-platform\backend
.venv\Scripts\python -m alembic upgrade head   # 如数据库有迁移
set SERVE_STATIC_DIR=C:\map-platform\frontend\dist
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```