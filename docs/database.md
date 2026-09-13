# 数据库设计（ER）

## 关系概览

```text
users 1 ──── N project_members N ──── 1 projects
users 1 ──── N projects (owner_id)
projects 1 ──── N folders (parent_id 自引用)
projects 1 ──── N categories
projects 1 ──── N features
features 1 ──── N feature_versions
projects 1 ──── N audit_logs
users 1 ──── N audit_logs
users 1 ──── N refresh_tokens
```

## 表结构

### users
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID PK | |
| username | varchar(64) UNIQUE | |
| email | varchar(255) UNIQUE | |
| password_hash | varchar(255) | Argon2id |
| display_name | varchar(64) | |
| is_active | bool | |
| is_admin | bool | 平台管理员（创建者） |
| created_at / updated_at | timestamptz | |

### projects
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID PK | |
| name | varchar(128) | |
| description | text | |
| owner_id | UUID FK users | |
| default_center | jsonb | 初始地图中心 [lng,lat] |
| default_zoom | int | |

### project_members
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID PK | |
| project_id | UUID FK | UNIQUE(project_id,user_id) |
| user_id | UUID FK | |
| role | varchar(16) | owner/admin/editor/viewer |

### folders
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID PK | |
| project_id | UUID FK | |
| parent_id | UUID FK 自引用 | 多级 |
| name | varchar(128) | |
| sort_order | int | |
| visible | bool | 显示/隐藏及继承 |
| created_by | UUID FK | |
| deleted_at | timestamptz | 软删除 |

### categories
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID PK | |
| project_id | UUID FK | |
| name | varchar(64) | 如 病例/学校 |
| color | varchar(16) | |
| icon | varchar(64) | |
| sort_order | int | |

### features
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID PK | |
| project_id | UUID FK | 数据隔离 |
| folder_id | UUID FK | 可空=未分组 |
| category_id | UUID FK | 可空 |
| name | varchar(128) | |
| feature_type | varchar(16) | point/circle/polyline/polygon |
| geometry_display | jsonb | GCJ-02 显示几何（GeoJSON 或 Circle） |
| coordinate_system_display | varchar(8) | GCJ02 |
| geometry_original / coordinate_system_original | jsonb / varchar(8) | 导入源，保留 |
| properties | jsonb | 地址/备注/自定义 |
| style | jsonb | 颜色/透明度 |
| version | int | 乐观锁 |
| created_by / updated_by | UUID FK | |
| deleted_at / deleted_by | timestamptz / UUID | 软删除（回收站） |

### feature_versions
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID PK | |
| feature_id | UUID FK | |
| version | int | |
| geometry / properties / style | jsonb | 每版快照 |
| created_by | UUID FK | 谁产生的该版本 |

### audit_logs
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID PK | |
| project_id | UUID ** | |
| user_id | UUID FK | |
| action | varchar(32) | create/update/delete/move/restore/import… |
| target_type / target_id | | |
| before / after | jsonb | 变更前后摘要（不含敏感数据） |
| ip / user_agent | varchar | |
| created_at | timestamptz | 索引(project_id,created_at) |

### refresh_tokens
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID PK | |
| user_id | UUID FK | |
| token_hash | varchar(128) UNIQUE | 只存哈希 |
| expires_at | timestamptz | 滚动轮换 |
| revoked_at | timestamptz | 登出/重用后失效 |
| created_at | timestamptz | |

> 真实表定义见 `backend/app/models/models.py`，迁移脚本在 `backend/alembic/versions/`。