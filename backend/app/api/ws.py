"""WebSocket 实时协作端点。

- 连接: /ws/projects/{project_id}?token=<JWT access token>
- 校验 JWT + 项目成员身份后加入房间
- 订阅 Redis Pub/Sub channel project:{project_id}，向房间内连接转发
- 心跳: 客户端每 25s 发送 {type:"ping"}，服务端回 {type:"pong"}，同时更新在线状态
"""
import asyncio
import json
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.db.redis import get_redis
from app.db.session import SessionLocal
from app.models import Project, User
from app.services.presence import hub

router = APIRouter(tags=["ws"])


async def _authenticate(token: str) -> User | None:
    try:
        payload = decode_token(token)
    except Exception:
        return None
    if payload.get("type") != "access":
        return None
    async with SessionLocal() as db:
        user = await db.get(User, payload.get("sub"))
        return user if user and user.is_active else None


async def _project_exists(project_id: str) -> bool:
    """协作模式：项目对所有登录用户开放，只需项目存在即可连 WS。"""
    async with SessionLocal() as db:
        project = await db.get(Project, project_id)
        return project is not None


@router.websocket("/ws/projects/{project_id}")
async def project_ws(websocket: WebSocket, project_id: str, token: str = Query(...)) -> None:
    user = await _authenticate(token)
    if user is None:
        await websocket.close(code=4401, reason="unauthorized")
        return
    if not await _project_exists(project_id):
        await websocket.close(code=4404, reason="not found")
        return

    await websocket.accept()

    # 加入房间与在线状态
    channel = f"project:{project_id}"
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    await hub.join(project_id, user.id, user.username, user.display_name)
    await hub.broadcast(project_id, "member.joined", {"user": {"id": user.id, "username": user.username, "display_name": user.display_name}}, None)

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)

    async def read_redis() -> None:
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                payload = json.loads(message["data"])
                # 不把自己广播的事件回传给发送者（避免重复）
                if payload.get("user_id") == user.id:
                    continue
                if payload.get("event") in ("feature.locked", "feature.unlocked") and payload.get("user_id") == user.id:
                    continue
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    reader_task = asyncio.create_task(read_redis())

    async def ping_loop() -> None:
        while True:
            await asyncio.sleep(20)
            try:
                await hub.heartbeat(project_id, user.id)
            except Exception:
                pass

    ping_task = asyncio.create_task(ping_loop())

    try:
        # 回复 pong；把排队事件发回
        receiver = asyncio.create_task(_pump(websocket, queue))

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                msg = {}
            mtype = msg.get("type")
            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
            elif mtype == "presence":
                # 广播给房间其他成员：最近协作活动
                await hub.broadcast(
                    project_id,
                    "presence",
                    {"user_id": user.id, "username": user.username, "activity": (msg.get("activity") or "")[:60], "ts": msg.get("ts")},
                    user.id,
                )
    except WebSocketDisconnect:
        pass
    finally:
        receiver.cancel() if "receiver" in locals() else None
        reader_task.cancel()
        ping_task.cancel()
        await pubsub.unsubscribe(channel)
        await hub.leave(project_id, user.id)
        await hub.broadcast(project_id, "member.left", {"user_id": user.id, "username": user.username}, user.id)
        try:
            await websocket.close()
        except Exception:
            pass


async def _pump(websocket: WebSocket, queue: asyncio.Queue[dict[str, Any]]) -> None:
    try:
        while True:
            item = await queue.get()
            await websocket.send_json(item)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass
