"""操作日志写入。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def log_audit(
    db: AsyncSession,
    *,
    project_id: str | None,
    user_id: str | None,
    action: str,
    target_type: str = "",
    target_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip: str = "",
    user_agent: str = "",
) -> None:
    db.add(
        AuditLog(
            project_id=project_id,
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=before or {},
            after=after or {},
            ip=ip[:64],
            user_agent=user_agent[:256],
        )
    )
    # 不在此处 commit，由调用方统一提交
