# API 文档

前缀：`/api/v1` · 认证：`Authorization: Bearer <access_token>`

交互式文档：启动后访问 `/api/docs`（Swagger）与 `/api/redoc`。

## 认证 Auth

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /auth/login | `{username,password}` → `{access_token,refresh_token}` |
| POST | /auth/register | `{username,email,password,display_name?}`（需 ALLOW_REGISTER=true） |
| POST | /auth/refresh | `{refresh_token}` → 轮换新对（refresh 单次使用） |
| POST | /auth/logout | `{refresh_token}` 吊销 |
| GET | /auth/me | 当前用户 |

## 项目 Projects

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /projects | 我参与的项目 |
| POST | /projects | `{name,description?}` |
| GET | /projects/{id} | 详情 + 我的角色 + 统计 |
| PATCH | /projects/{id} | 编辑（owner/admin） |
| DELETE | /projects/{id} | 删除（owner） |

## 成员 Members

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /projects/{id}/members | 列表 |
| POST | /projects/{id}/members | `{username?/email?, role}`（owner/admin） |
| PATCH | /projects/{id}/members/{user_id} | 改角色 |
| DELETE | /projects/{id}/members/{user_id} | 移除 |

## 文件夹 Folders

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /projects/{id}/folders | 树（平铺，前端组树） |
| POST | /projects/{id}/folders | `{name, parent_id?, sort_order?}` |
| PATCH | /folders/{id} | `{name?, parent_id?, sort_order?, visible?}` |
| DELETE | /folders/{id} | 软删除（对象置未分组） |

## 分类 Categories

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /projects/{id}/categories | |
| POST | /projects/{id}/categories | `{name,color?,icon?,sort_order?}` |
| PATCH | /categories/{id} | |
| DELETE | /categories/{id} | 对象 category 置空 |

## 地图对象 Features

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /projects/{id}/features?folder_id=&include_deleted= | 列表 |
| POST | /projects/{id}/features | 创建（editor+） |
| GET | /features/{id} | 详情 |
| PATCH | /features/{id} | 更新，**必须带 version**（409 冲突） |
| POST | /features/{id}/move | `{folder_id, version}` |
| DELETE | /features/{id} | 软删除 → 回收站 |
| POST | /features/{id}/restore | 恢复 |
| DELETE | /features/{id}/permanent | 永久删除（owner/admin） |
| GET | /features/{id}/versions | 历史版本 |
| POST | /features/{id}/versions/{v}/restore | 恢复历史版本（产生新版本） |
| GET | /projects/{id}/trash | 回收站列表（owner/admin） |
| GET | /projects/{id}/features/nearby?lng=&lat=&radius= | 附近对象（前端/PG 双模式） |
| POST | /features/{id}/lock | 获取编辑锁（423 被占） |
| POST | /features/{id}/unlock | 释放锁 |

**创建/更新几何示例**

```jsonc
// Point
{"type": "Point", "coordinates": [113.261, 23.182]}
// LineString
{"type": "LineString", "coordinates": [[113.261,23.182],[113.262,23.184]]}
// Polygon（闭合环）
{"type": "Polygon", "coordinates": [[[113.26,23.18],[113.27,23.18],[113.27,23.19],[113.26,23.18]]]}
// Circle（扩展类型, 半径米）
{"type": "Circle", "center": [113.261, 23.182], "radius": 500}
```

## 导入导出

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /projects/{id}/import | multipart：`file` + `crs=GCJ02/WGS84`；支持 .csv/.geojson/.json |
| GET | /projects/{id}/export | `?format=geojson|csv&scope=project\|folder&folder_id=&feature_ids=&crs=original\|GCJ02\|WGS84` |

## 其它

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /projects/{id}/audit?page=&page_size= | 操作日志 |
| GET | /projects/{id}/online | 在线成员（HTTP 兜底） |
| POST | /amap-proxy | `{path, params}` 高德 REST 代理（登录态，不暴露 Key） |
| GET | /api/health | 健康检查 |

## WebSocket

```text
连接：ws(s)://host/ws/projects/{project_id}?token=<access_token>
```

心跳：客户端每 20s 发 `{"type":"ping"}` → `{"type":"pong"}`。

**服务端 → 客户端事件**

```json
{"event":"feature.created","project_id":"…","user_id":"…","data":{"feature":{…}}}
{"event":"feature.updated","project_id":"…","user_id":"…","data":{"feature":{…}}}
{"event":"feature.deleted","project_id":"…","user_id":"…","data":{"id":"…"}}
{"event":"folder.created|updated|deleted", …}
{"event":"member.joined","data":{"user":{…}}}
{"event":"member.left","data":{"user_id":"…"}}
{"event":"feature.locked","data":{"id":"…","user_id":"…","username":"…"}}
{"event":"feature.unlocked","data":{"id":"…","user_id":"…"}}
{"event":"presence","data":{"user_id":"…","username":"…","activity":"…","ts":…}}
```

客户端可发：`{"type":"presence","activity":"正在编辑病例001","ts":…}`

**关闭码**：4401 未认证 / 4403 无权限 / 1000 正常。

## 错误码约定

| Code | 含义 |
| --- | --- |
| 400 | 参数/业务错误 |
| 401 | 未登录/token 失效（前端自动刷新后重试一次） |
| 403 | 无权访问/操作（Test 5/6/7） |
| 409 | 版本冲突（Test 8） |
| 422 | 几何/字段校验失败 |
| 423 | 对象被他人锁定编辑 |
| 429 | 限流（登录） |
| 500 | 服务器异常 |