"""命令行工具。

用法：
    python -m app.cli create-admin   # 交互式创建管理员
    python -m app.cli create-admin --username admin --email a@b.c --password xxx
"""
import asyncio

import typer

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User
from app.services.audit import log_audit

cli = typer.Typer(help="地图标绘系统管理命令")


@cli.command("create-admin")
def create_admin(
    username: str = typer.Option(None, "--username", help="管理员用户名"),
    email: str = typer.Option(None, "--email", help="邮箱"),
    password: str = typer.Option(None, "--password", help="密码（不推荐命令行传入）"),
) -> None:
    async def _run() -> None:
        async with SessionLocal() as db:
            from sqlalchemy import select

            # 交互收集
            u = username or typer.prompt("用户名")
            e = email or typer.prompt("邮箱")
            p = password or typer.prompt("密码", hide_input=True, confirmation_prompt=True)

            result = await db.execute(select(User).where(User.username == u))
            if result.scalar_one_or_none() is not None:
                typer.echo(f"错误：用户名 {u} 已存在")
                raise typer.Exit(1)
            user = User(
                username=u,
                email=e,
                password_hash=hash_password(p),
                display_name=u,
                is_admin=True,
            )
            db.add(user)
            await db.commit()
            await log_audit(db, project_id=None, user_id=user.id, action="user.create", target_type="user")
            await db.commit()
        typer.echo(f"管理员 {u} 创建成功")

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
