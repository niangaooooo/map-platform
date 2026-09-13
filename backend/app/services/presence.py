"""在线状态、编辑锁、项目广播（Redis Pub/Sub）。

Key 设计：
- presence:{project_id}       -> Hash { user_id: json(user) }，无 TTL，靠心跳剔除
- presence:last:{project_id}  -> Hash { user_id: ts }
- feature_lock:{feature_id}   -> json({user_id, username, display_name})，TTL 30s 自动续期
- pubsub channel: project:{project_id}
"""
import json
import time
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.db.redis import get_redis

HEARTBEAT_TTL = 60


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def unix_ms() -> int:
    return int(time.time() * 1000)


class PresenceHub:
    """管理在线成员与编辑锁（Redis）。"""

    def __init__(self) -> None:
        self._redis = None

    @property
    def redis(self):
        if self._redis is None:
            self._redis = get_redis()
        return self._redis

    # ---------- 在线成员 ----------
    async def join(self, project_id: str, user_id: str, username: str, display_name: str) -> None:
        data = {"id": user_id, "username": username, "display_name": display_name, "ts": now_iso()}
        await self.redis.hset(self._presence_key(project_id), user_id, json.dumps(data, ensure_ascii=False))
        await self.redis.hset(self._last_key(project_id), user_id, str(unix_ms()))

    async def heartbeat(self, project_id: str, user_id: str) -> None:
        await self.redis.hset(self._last_key(project_id), user_id, str(unix_ms()))

    async def leave(self, project_id: str, user_id: str) -> None:
        await self.redis.hdel(self._presence_key(project_id), user_id)
        await self.redis.hdel(self._last_key(project_id), user_id)

    async def online_members(self, project_id: str) -> list[dict[str, Any]]:
        raw = await self.redis.hgetall(self._presence_key(project_id))
        members: list[dict[str, Any]] = []
        for _uid, payload in raw.items():
            try:
                members.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
        members.sort(key=lambda m: m.get("username", ""))
        return members

    async def prune_stale(self, project_id: str) -> None:
        """清理超过 HEARTBEAT_TTL 未心跳的成员。"""
        last = await self.redis.hgetall(self._last_key(project_id))
        now = unix_ms()
        stale = [uid for uid, ts in last.items() if now - int(ts) > HEARTBEAT_TTL * 1000]
        if stale:
            await self.redis.hdel(self._presence_key(project_id), *stale)
            await self.redis.hdel(self._last_key(project_id), *stale)

    # ---------- 编辑锁 ----------
    async def acquire_lock(self, project_id: str, feature_id: str, user_id: str, username: str, display_name: str) -> bool:
        settings = get_settings()
        ok = await self.redis.set(
            self._lock_key(project_id, feature_id),
            json.dumps({"user_id": user_id, "username": username, "display_name": display_name}, ensure_ascii=False),
            nx=True,
            ex=settings.LOCK_TTL_SECONDS,
        )
        return bool(ok)

    async def renew_lock(self, project_id: str, feature_id: str, user_id: str) -> bool:
        raw = await self.redis.get(self._lock_key(project_id, feature_id))
        if not raw:
            return False
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            return False
        if info.get("user_id") != user_id:
            return False
        settings = get_settings()
        await self.redis.expire(self._lock_key(project_id, feature_id), settings.LOCK_TTL_SECONDS)
        return True

    async def unlock(self, project_id: str, feature_id: str, user_id: str | None = None) -> bool:
        """user_id 为空时强制解锁（仅 owner/admin）。"""
        key = self._lock_key(project_id, feature_id)
        if user_id is None:
            return bool(await self.redis.delete(key))
        raw = await self.redis.get(key)
        if not raw:
            return False
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            return False
        if info.get("user_id") == user_id:
            return bool(await self.redis.delete(key))
        return False

    async def get_lock(self, project_id: str, feature_id: str) -> dict[str, Any] | None:
        raw = await self.redis.get(self._lock_key(project_id, feature_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    # ---------- 广播 ----------
    async def broadcast(self, project_id: str, event: str, data: dict[str, Any], sender_user_id: str | None = None) -> None:
        payload = {"event": event, "project_id": project_id, "user_id": sender_user_id, "data": data}
        await self.redis.publish(f"project:{project_id}", json.dumps(payload, ensure_ascii=False, default=str))

    # ---------- keys ----------
    def _presence_key(self, project_id: str) -> str:
        return f"presence:{project_id}"

    def _last_key(self, project_id: str) -> str:
        return f"presence:last:{project_id}"

    def _lock_key(self, project_id: str, feature_id: str) -> str:
        return f"feature_lock:{feature_id}"


hub = PresenceHub()
