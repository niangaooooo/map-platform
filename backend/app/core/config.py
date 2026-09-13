"""应用配置：所有配置均来自环境变量，保留默认值方便本地开发。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 优先读取 backend/.env，其次项目根目录 .env（本地开发；Docker 直接用环境变量）
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
_PROJECT_ROOT = _BACKEND_DIR.parent  # 项目根
_candidate_env_files = [str(p) for p in (_BACKEND_DIR / ".env", _PROJECT_ROOT / ".env") if p.exists()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=tuple(_candidate_env_files) or None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "dev-secret-key-change-me"
    ALLOW_REGISTER: bool = False

    # 数据库/Redis
    DATABASE_URL: str = "postgresql+asyncpg://map:map@localhost:5432/map_platform"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Token
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # 高德地图
    AMAP_KEY: str = ""
    AMAP_SECURITY_CODE: str = ""
    AMAP_PROXY_SECRET: str = ""  # 提供给前端调用安全验证代理的共享密钥

    # CORS（逗号分隔）
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8080"

    # 前端静态目录（可选）：设置后后端同时托管前端 dist，实现单端口部署
    SERVE_STATIC_DIR: str = ""

    # 限流
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 10

    # 编辑锁
    LOCK_TTL_SECONDS: int = 30

    # 测试→正式 同步（仅测试板块配置）
    SYNC_PROD_URL: str = ""  # 正式端 import-backup 地址（测试端设置）
    SYNC_SHARED_SECRET: str = ""  # 两端一致的共享密钥（正式端校验，测试端请求携带）

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def deep_link_secret_ok(self) -> bool:
        """开启极简安全代理模式的开关：AMAP_PROXY_SECRET 非空即启用。"""
        return bool(self.AMAP_PROXY_SECRET)


@lru_cache
def get_settings() -> Settings:
    return Settings()
